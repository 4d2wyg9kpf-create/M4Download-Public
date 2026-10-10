#!/usr/bin/env python3
"""Build the published M4Download source on a standard Xcode 27 macOS runner.

The source's codec recipes, features and SIMD checks remain in use. Only the
Linux host tools and the SDK layout are adapted for an installed native Xcode.
No SDK, credentials or signing identity is downloaded or published.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "ci/source.json").read_text())
WORK = ROOT / ".build"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def capture(*args):
    return subprocess.check_output(args, text=True).strip()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("The build input changed; review the native adapter: " + old[:100])
    return text.replace(old, new, 1)


def extract_source(archive):
    if digest(archive) != SPEC["sha256"]:
        raise RuntimeError("Source SHA-256 mismatch")
    destination = WORK / "source"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as incoming:
        if incoming.testzip() is not None:
            raise RuntimeError("Source ZIP integrity check failed")
        for item in incoming.infolist():
            target = (destination / item.filename).resolve()
            if not target.is_relative_to(destination.resolve()) or stat.S_ISLNK(item.external_attr >> 16):
                raise RuntimeError("Unexpected path or symlink in source archive")
        incoming.extractall(destination)
    source = destination / SPEC["root"]
    manifest = (source / "M4Download.swiftpm/Package.swift").read_text()
    for key, expected in (("displayVersion", SPEC["version"]), ("bundleVersion", SPEC["build"])):
        match = re.search(key + r':\s*"([^"]+)"', manifest)
        if not match or match[1] != expected:
            raise RuntimeError("Unexpected app version: " + key)
    return source


def native_recipe(source):
    recipe = source / "BuildTools/FullMedia/full_media.py"
    code = recipe.read_text()
    start = code.index(" # Every archive, including bundled build tools")
    end = code.index(" env['PKG_CONFIG_PATH']=", start)
    host = ''' # Validate all bundled inputs; use macOS host tools from the runner/venv.
 for name,p in packages.items():
  f=archives/p['archive']
  if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=p['sha256']:
   raise RuntimeError('Library source verification failed: '+name)
 env=os.environ.copy()
 pkgconf=shutil.which('pkgconf') or shutil.which('pkg-config')
 if not pkgconf:raise RuntimeError('A native pkg-config tool is required')
 bin_dir=tools/'usr/bin';bin_dir.mkdir(parents=True,exist_ok=True)
 for name in ['pkgconf','pkg-config']:
  alias=bin_dir/name
  if alias.is_symlink() or alias.exists():alias.unlink()
  alias.symlink_to(pkgconf)
 env['PKG_CONFIG']=str(bin_dir/'pkgconf')
'''
    code = code[:start] + host + code[end:]
    code = replace_once(code,
                        "env['CC_FOR_BUILD']=shutil.which('clang') if sdk else shutil.which('gcc')",
                        "env['CC_FOR_BUILD']=os.environ['M4_NATIVE_CC']")
    code = replace_once(code,
                        "env['CXX_FOR_BUILD']=shutil.which('clang++') if sdk else shutil.which('g++')",
                        "env['CXX_FOR_BUILD']=os.environ['M4_NATIVE_CXX']")
    # LLVM ar retains the Darwin archive/MRI support expected by the recipe.
    # The existing recipe supplies target, SDK and deployment flags to Clang.
    compile(code, str(recipe), "exec")
    return recipe, code


def parse_project(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[{}()=;,]|[0-9]+', text.split("\n", 1)[1])
    position = 0

    def take(expected=None):
        nonlocal position
        value = tokens[position]
        position += 1
        if expected is not None and value != expected:
            raise RuntimeError("Unexpected Xcode project token")
        return value

    def value():
        token = take()
        if token == "{":
            result = {}
            while tokens[position] != "}":
                key = json.loads(take())
                if key in result:
                    raise RuntimeError("Duplicate Xcode project key")
                take("=")
                result[key] = value()
                take(";")
            take("}")
            return result
        if token == "(":
            result = []
            while tokens[position] != ")":
                result.append(value())
                take(",")
            take(")")
            return result
        return json.loads(token) if token.startswith('"') else int(token)

    result = value()
    if position != len(tokens):
        raise RuntimeError("Trailing Xcode project tokens")
    return result


def format_project(value, level=0):
    indent = "\t" * level
    if isinstance(value, dict):
        return "{\n" + "".join(indent + "\t" + json.dumps(key) + " = " +
                               format_project(item, level + 1) + ";\n"
                               for key, item in value.items()) + indent + "}"
    if isinstance(value, list):
        return "(\n" + "".join(indent + "\t" + format_project(item, level + 1) + ",\n"
                               for item in value) + indent + ")"
    return json.dumps(value, ensure_ascii=False)


def sync_xcode_sources(source):
    """Include the same complete app source inventory used by the WSL builder."""
    path = source / "M4Download.xcodeproj/project.pbxproj"
    project = parse_project(path.read_text())
    objects = project["objects"]
    targets = [obj for obj in objects.values() if obj["isa"] == "PBXNativeTarget"]
    if len(targets) != 1:
        raise RuntimeError("Expected one app target")
    target = targets[0]
    phase = next(objects[key] for key in target["buildPhases"]
                 if objects[key]["isa"] == "PBXSourcesBuildPhase")
    group = next(obj for obj in objects.values() if obj["isa"] == "PBXGroup" and
                 obj.get("path") == "M4Download.swiftpm/Sources/AppModule")
    app_source = source / group["path"]
    expected = {path.relative_to(app_source).as_posix() for path in app_source.rglob("*.swift")}
    actual = {objects[objects[key]["fileRef"]]["path"] for key in phase["files"]}
    if actual - expected:
        raise RuntimeError("Xcode references removed sources; review before building")
    missing = sorted(expected - actual)
    for relative in missing:
        ref = hashlib.sha256(("m4-native-file:" + relative).encode()).hexdigest()[:24].upper()
        build = hashlib.sha256(("m4-native-build:" + relative).encode()).hexdigest()[:24].upper()
        if ref in objects or build in objects:
            raise RuntimeError("Xcode object identifier collision")
        objects[ref] = {"isa": "PBXFileReference", "lastKnownFileType": "sourcecode.swift",
                        "path": relative, "sourceTree": "<group>"}
        objects[build] = {"isa": "PBXBuildFile", "fileRef": ref}
        group["children"].append(ref)
        phase["files"].append(build)
    rendered = "// !$*UTF8*$!\n" + format_project(project) + "\n"
    if parse_project(rendered) != project:
        raise RuntimeError("Xcode project serialization changed its structure")
    path.write_text(rendered)
    print("Xcode app sources:", len(expected), "added:", missing, flush=True)


def adapt_packager(source):
    script = source / "Scripts/build_ios.py"
    code = script.read_text()
    code = replace_once(code, 'set(info.get("UIBackgroundModes", [])) - {"processing"}',
                        'set(info.get("UIBackgroundModes", [])) - {"processing", "audio"}')
    code = replace_once(code, '"COMPILER_INDEX_STORE_ENABLE=NO", "build",',
                        '"COMPILER_INDEX_STORE_ENABLE=NO", "-jobs", "2", "build",')
    code = replace_once(code, '"0.6.2 enhancements removed; pre-enhancement lifecycle restored"',
                        '"player audio/PiP and conversion processing preserved"')
    compile(code, str(script), "exec")
    script.write_text(code)


def link(target, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.exists():
        destination.unlink()
    destination.symlink_to(target)


def prepare_native_sdk():
    sdk_path = Path(capture("xcrun", "--sdk", "iphoneos", "--show-sdk-path"))
    sdk_version = capture("xcrun", "--sdk", "iphoneos", "--show-sdk-version")
    if sdk_version.split(".")[0] != "27":
        raise RuntimeError("Use the standard xcode-27 runner with an iOS 27 SDK")
    clang = Path(capture("xcrun", "--find", "clang"))
    clangxx = Path(capture("xcrun", "--find", "clang++"))
    linker = Path(capture("xcrun", "--find", "ld"))
    resource = Path(capture(str(clang), "-print-resource-dir"))
    llvm_prefix = Path(capture("brew", "--prefix", "llvm@20"))
    binaries = {"clang": clang, "clang++": clangxx}
    for name in ("llvm-ar", "llvm-ranlib", "llvm-nm", "llvm-strip"):
        binaries[name] = llvm_prefix / "bin" / name
    host_bin = WORK / "mac-host/bin"
    for name, binary in binaries.items():
        if not binary.is_file():
            raise RuntimeError("Missing native tool: " + str(binary))
        link(binary, host_bin / name)
    os.environ["PATH"] = str(host_bin) + os.pathsep + os.environ["PATH"]
    os.environ["IPHONEOS_DEPLOYMENT_TARGET"] = "18.0"
    sdk = WORK / "native-sdk-view"
    developer = sdk / "Developer"
    link(sdk_path, developer / "Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS27.0.sdk")
    toolchain = developer / "Toolchains/XcodeDefault.xctoolchain/usr"
    link(resource, toolchain / "lib/swift/clang")
    cxx_candidates = [sdk_path / "usr/include/c++/v1",
                      clang.resolve().parent.parent / "include/c++/v1"]
    cxx_headers = next((path for path in cxx_candidates if (path / "vector").is_file()), None)
    if cxx_headers is None:
        raise RuntimeError("The native Xcode C++ headers are required: " +
                           ", ".join(map(str, cxx_candidates)))
    print("Native SDK:", sdk_path, "C++ headers:", cxx_headers, flush=True)
    link(cxx_headers, toolchain / "include/c++/v1")
    link(linker, sdk / "toolset/bin/ld64.lld")
    (sdk / "darwin-sdk-version.txt").write_text(capture("xcodebuild", "-version") + "\n")
    return sdk


def build_media(source, jobs):
    sdk = prepare_native_sdk()
    recipe, code = native_recipe(source)
    sys.path.insert(0, str(recipe.parent))
    namespace = {"__file__": str(recipe), "__name__": "m4_macos_full_media"}
    exec(compile(code, str(recipe), "exec"), namespace)
    mac_sdk = capture("xcrun", "--sdk", "macosx", "--show-sdk-path")
    host_flags = ["-target", platform.machine() + "-apple-macos" + platform.mac_ver()[0],
                  "-isysroot", mac_sdk]
    for key, compiler, name in (("M4_NATIVE_CC", "clang", "mac-cc"),
                                ("M4_NATIVE_CXX", "clang++", "mac-cxx")):
        wrapper = WORK / "mac-host/bin" / name
        namespace["write_compiler_wrapper"](wrapper, capture("xcrun", "--find", compiler),
                                              host_flags, [])
        os.environ[key] = str(wrapper)
    cache = WORK / "media-cache" / digest(__file__)[:12]
    prefix = namespace["prepare"](recipe.parent, cache, sdk, jobs)
    config = prefix / "FullMediaPaths.json"
    shutil.copy2(config, source / "M4Download.swiftpm/Vendor/MediaCore/FullMediaPaths.json")
    return prefix


def verify_ipa(source, output):
    ipas = list(output.glob("*.ipa"))
    if len(ipas) != 1:
        raise RuntimeError("Exactly one newly built IPA is required")
    ipa = ipas[0]
    resource_root = source / "M4Download.swiftpm/Sources/AppModule/Captions/Resources/MediaRuntime"
    with zipfile.ZipFile(ipa) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("IPA ZIP integrity check failed")
        app = "Payload/M4Download.app/"
        info = plistlib.loads(archive.read(app + "Info.plist"))
        if (info["CFBundleShortVersionString"], info["CFBundleVersion"]) != (SPEC["version"], SPEC["build"]):
            raise RuntimeError("IPA version does not match the source")
        if info["CFBundleIdentifier"] != "com.wooseok.m4download":
            raise RuntimeError("IPA bundle identifier changed")
        count = 0
        for path in resource_root.rglob("*"):
            if path.is_file():
                member = app + "MediaRuntime/" + path.relative_to(resource_root).as_posix()
                if hashlib.sha256(archive.read(member)).hexdigest() != digest(path):
                    raise RuntimeError("Bundled resource mismatch: " + member)
                count += 1
    report = {"source": SPEC, "ipa": ipa.name, "sha256": digest(ipa),
              "resources_verified": count, "signing": "unsigned",
              "device_execution": "not tested", "runner": "standard xcode-27"}
    (output / "PUBLIC_BUILD_INFO.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    WORK.mkdir(exist_ok=True)
    archive = args.archive
    if archive is None:
        archive = WORK / SPEC["asset"]
        repository = os.environ.get("GITHUB_REPOSITORY", "4d2wyg9kpf-create/M4Download-Public")
        url = f"https://github.com/{repository}/releases/download/{SPEC['release']}/{SPEC['asset']}"
        urllib.request.urlretrieve(url, archive)
    source = extract_source(archive)
    native_recipe(source)
    sync_xcode_sources(source)
    adapt_packager(source)
    print("Verified source and prepared native build inputs:", source, flush=True)
    if args.prepare_only:
        return
    if platform.system() != "Darwin":
        raise RuntimeError("Run the full build on the standard xcode-27 macOS runner")
    prefix = build_media(source, max(1, min(args.jobs, 3)))
    subprocess.run([sys.executable, str(source / "Scripts/build_ios.py")], cwd=source, check=True)
    runs = list((source / "build/ios").glob("run-*"))
    if len(runs) != 1:
        raise RuntimeError("Cannot identify the new build outputs")
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    for path in runs[0].iterdir():
        if path.is_file() and (path.suffix in (".ipa", ".sha256", ".json", ".txt")):
            shutil.copy2(path, output / path.name)
    shutil.copy2(prefix / "full-media-build.json", output / "full-media-build.json")
    verify_ipa(source, output)


if __name__ == "__main__":
    main()
