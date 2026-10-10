# M4Download public builds

M4Download iPhone/iPad 소스 배포 및 서명 전 IPA 빌드용 저장소입니다.

현재 배포 버전은 **0.9.10 (74)**입니다.
[공개 릴리스](https://github.com/4d2wyg9kpf-create/M4Download-Public/releases/tag/v0.9.10-74-source)에서
`M4Download-0.9.10-74-unsigned.ipa`와 원본 소스 ZIP을 내려받을 수 있습니다.

## 빌드

`Build M4Download IPA` 워크플로는 GitHub의 **표준 `xcode-27` 실행 환경**을
사용합니다. 공개 저장소의 표준 실행 환경은 무료이며 유료 대형 실행 환경은
사용하지 않습니다. [GitHub 공식 안내](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

소스 릴리스 게시 또는 Actions의 수동 실행으로 시작합니다. 원본 ZIP의
SHA-256을 확인하고, 원본에 포함된 코덱 레시피와 ARM64 최적화 검사를 사용해
라이브러리를 컴파일한 뒤 Xcode로 앱을 빌드합니다.

macOS용 어댑터는 Linux 실행 도구 대신 macOS 도구를 선택하고 설치된 Xcode의
SDK를 연결합니다. 앱의 코덱·AI 모델을 포함합니다. 패키징 검사는 플레이어의
audio와 변환의 processing 백그라운드 항목을 함께 허용합니다.

성공한 실행의 `M4Download-0.9.10-74-unsigned` 결과물에도 IPA와 검증 기록이 있습니다.
IPA는 별도 서명이 필요하며 이 자동 빌드는 실제 기기 설치·실행을 시험하지 않습니다.
업데이트 설치 시 기존과 같은 최종 앱 식별자와 서명 계정을 유지하세요.

## 검증 상태

2026-10-10 [빌드 #6](https://github.com/4d2wyg9kpf-create/M4Download-Public/actions/runs/38020131250)이 성공했습니다.
빌드 설정 커밋은 `aedbd03ddf82620a8033adca3759362a474c785c`입니다.

- 대상: iPhone·iPad, iOS 18.0 이상, ARM64
- 전체 코덱·앱 컴파일 및 ARM64 최적화 검사 통과
- IPA 구조·체크섬과 원본 MediaRuntime 리소스 27개 일치 확인
- IPA 크기: 63,497,322 bytes
- IPA SHA-256: `37736a7a875d31d13fa0c12edcb12fbbc137d263c2c0f685707f8c96fcb64aa7`
- 실제 기기 설치·실행은 미검증

원본 소스 배포 파일은 `M4Download-0.9.10-74-source.zip`이며
태그 `v0.9.10-74-source`는 최초 소스 배포를 가리킵니다.
IPA는 위의 성공한 빌드 설정 커밋에서 원본 ZIP을 검증한 뒤 생성했습니다.

소스·코덱·모델의 라이선스는 배포 ZIP 안의 `THIRD_PARTY_LICENSES.md`,
`Licenses` 및 개별 라이선스 파일을 따릅니다.
