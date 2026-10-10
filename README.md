# M4Download public builds

M4Download iPhone/iPad 소스 배포 및 서명 전 IPA 빌드용 저장소입니다.

현재 대상은 **0.9.10 (74)**입니다. 원본 소스 배포 파일은
`M4Download-0.9.10-74-source.zip`, 태그는 `v0.9.10-74-source`입니다.
소스 파일이 해당 릴리스에 공개된 후 빌드할 수 있습니다.

## 빌드

`Build M4Download IPA` 워크플로는 GitHub의 **표준 `xcode-27` 실행 환경**을
사용합니다. 공개 저장소의 표준 실행 환경은 무료이며 유료 대형 실행 환경은
사용하지 않습니다. [GitHub 공식 안내](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

소스 릴리스 게시 또는 Actions의 수동 실행으로 시작합니다. 원본 ZIP의
SHA-256을 확인하고, 원본에 포함된 코덱 레시피와 ARM64 최적화 검사를 사용해
라이브러리를 컴파일한 뒤 Xcode로 앱을 빌드합니다.

macOS용 어댑터는 Linux 실행 도구 대신 macOS 도구를 선택하고 설치된 Xcode의
SDK를 연결합니다. 앱의 코덱·AI 모델을 생략하지 않습니다. 패키징 검사는 플레이어의
audio와 변환의 processing 백그라운드 항목을 함께 허용합니다.

성공한 실행의 `M4Download-0.9.10-74-unsigned` 결과물에 IPA와 검증 기록이 있습니다.
IPA는 별도 서명이 필요하며 이 자동 빌드는 실제 기기 설치·실행을 시험하지 않습니다.
업데이트 설치 시 기존과 같은 최종 앱 식별자와 서명 계정을 유지하세요.

## 검증 상태

현재 빌드 설정과 소스 입력 준비만 확인했습니다. GitHub에서 전체 컴파일이
성공하기 전에는 이 설정으로 IPA가 완성됐다고 간주하지 않습니다.

소스·코덱·모델의 라이선스는 배포 ZIP 안의 `THIRD_PARTY_LICENSES.md`,
`Licenses` 및 개별 라이선스 파일을 따릅니다.
