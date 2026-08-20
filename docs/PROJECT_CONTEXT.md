# KakaoTalk Playground Bot — 프로젝트 컨텍스트

최종 갱신: 2026-08-20

## 프로젝트 기준

- 실제 프로젝트 경로: `C:\Users\Administrator\CursorProjects\kakaobot`
- GitHub: `https://github.com/sleep5115/kakao-chat-bot`
- 기본 브랜치: `main`
- Pickty와 분리된 독립 프로젝트 및 Git 저장소로 관리한다.
- 코드와 저장소는 분리하되 필요하면 기존 Lightsail/Nginx/PostgreSQL 인프라는 공유한다.

## 목표

```text
KakaoTalk
  ↕
Samsung Galaxy J6 (SM-J600L) + Iris
  ↕ HTTP/WebSocket
Python/FastAPI Backend
  ↕
PostgreSQL / 외부 API / AI API
```

Android와 Iris는 KakaoTalk Gateway로 사용하고 명령 처리, 비즈니스 로직, 권한 통제와 데이터 보존은 Backend가 담당한다.

## 현재 상태 — 루팅 및 Iris Gateway 준비 완료

기기:

- Samsung Galaxy J6 / `SM-J600L` / LG U+
- Android 10
- Build/PDA/Bootloader: `J600LKLS5CUL1`
- CSC: `LUC`
- ADB 장치 ID: `52009585febd3541`
- ADB Platform Tools: `C:\Users\Administrator\Desktop\platform-tools`

2026-08-12 검증 결과:

```text
ro.boot.flash.locked = 0
ro.boot.verifiedbootstate = orange
ro.boot.warranty_bit = 1
ro.vendor.boot.warranty_bit = 1
Magisk = 30.7:MAGISK:R (30700)
root = uid=0(root) gid=0(root) groups=0(root) context=u:r:magisk:s0
```

- Bootloader Unlock 완료
- OEM 잠금 해제 ON (`부트스트랩 로더 잠금 해제됨` 표시 확인)
- Magisk 앱 및 데몬 `30.7` 설치 완료
- Magisk 추가 설정과 자동 재부팅 완료
- ADB shell의 Superuser 요청을 `모두 허용`으로 승인
- Knox Warranty Bit는 예상대로 `0 → 1`로 영구 변경됨
- Odin Flash, Recovery의 공장초기화, Android 초기 설정 완료
- 개발자 옵션 및 USB 디버깅 다시 활성화 완료

루팅은 끝난 상태다. 같은 절차를 다시 Flash하지 않는다.

## 루팅 작업 기록

1. ADB로 모델, 빌드, CSC와 Bootloader Unlock 상태 재검증
2. 공식 Bifrost `2.1.3`으로 Samsung 서버에서 다음 펌웨어 다운로드

```text
SM-J600L / LUC
J600LKLS5CUL1 / J600LLUC5CUL1
Android 10 / Bootloader revision 5
```

3. 압축 내부의 BL/AP/CP/CSC/HOME_CSC 다섯 파일에 대해 Samsung 내장 MD5 검증 통과
4. 공식 Magisk `30.7` APK의 GitHub SHA-256 검증 후 기기에 설치
5. 순정 AP를 해당 SM-J600L 기기의 Magisk에서 직접 패치
6. 패치 TAR를 MTP가 아닌 ADB로 PC에 회수하고 파일 크기/TAR 구조 검증
7. Magisk 공식 Samsung 절차대로 Odin `3.14.4`에서 아래 구성으로 Flash

```text
BL  = 순정 BL
AP  = magisk_patched-30700_Lwq6z.tar
CP  = 순정 CP
CSC = 순정 CSC_OMC_LUC (HOME_CSC 아님)

Auto Reboot  = ON
F. Reset Time = ON
Re-Partition = OFF
Nand Erase   = OFF
Flash Lock   = OFF
```

8. Odin `PASS!` 확인
9. Android Recovery에서 `Wipe data/factory reset` 실행 후 `Data wipe complete.` 확인
10. 정상 부팅, Magisk 추가 설정, `su -c id` root 검증 완료

## 로컬 작업 산출물 — Git 저장소 밖

펌웨어와 도구는 Git에 커밋하지 않는다.

```text
C:\Users\Administrator\Android\SM-J600L\firmware\J600LKLS5CUL1_LUC
├ stock_files\
│  ├ BL_J600LKLS5CUL1_...tar.md5
│  ├ AP_J600LKLS5CUL1_...OS10.tar.md5
│  ├ CP_J600LKLS5CUL1_...tar.md5
│  ├ CSC_OMC_LUC_J600LLUC5CUL1_...tar.md5
│  └ HOME_CSC_OMC_LUC_J600LLUC5CUL1_...tar.md5
└ patched_files\
   └ magisk_patched-30700_Lwq6z.tar
```

패치 AP:

```text
크기: 2,593,518,080 bytes
SHA-256: 11C9B838DD9E6663F9874400E3E4CD810DB9103EFFB04EAD1F97E036B6910FE9
```

준비된 도구:

```text
C:\Users\Administrator\Android\SM-J600L\tools\odin
C:\Users\Administrator\Android\SM-J600L\tools\iris\v0.32
```

## KakaoTalk 및 Iris 구성 완료

2026-08-20 완료 및 검증 내용:

- 공식 KakaoTalk 설치 및 봇 계정 로그인 완료
- 확인 당시 KakaoTalk 패키지 `com.kakao.talk`, 앱 버전 `26.7.1`
- 나와의 채팅과 테스트 오픈채팅에서 메시지 생성 완료
- 공식 Iris `v0.32` APK를 `/data/local/tmp/Iris.apk`에 설치
- Iris를 root `app_process`의 `party.qwer.iris.Main`으로 실행
- Iris가 KakaoTalk DB를 읽어 테스트 메시지를 감지하는 것 확인
- 봇 사용자 ID 자동 탐지 및 Iris 설정 반영 완료
- Iris WebSocket에서 실시간 메시지 이벤트 수신 확인
- 나와의 채팅에 Iris `/reply` API로 `Iris 양방향 연결 테스트 성공` 전송 확인
- Dashboard와 `/config` 응답 확인

테스트 중 채팅 내용이나 방 이름은 로그 및 문서에 저장하지 않았다. 봇 사용자 ID도 저장소에 기록하지 않는다.

## Iris 자동 시작

Magisk의 공식 `service.d` 방식으로 다음 스크립트를 기기에 설치했다.

```text
/data/adb/service.d/iris.sh
소유자: root:root
권한: 0755
SELinux context: u:object_r:adb_data_file:s0
```

스크립트 동작:

1. Android의 `sys.boot_completed=1`을 기다림
2. 추가로 15초 대기
3. `/data/local/tmp/Iris.apk` 존재 여부 확인
4. 기존 `party.qwer.iris.Main` 프로세스가 있으면 중복 실행하지 않음
5. 없으면 root `app_process`로 Iris 실행
6. 로그와 PID를 각각 아래 경로에 기록

```text
/data/local/tmp/iris-autostart.log
/data/local/tmp/iris.pid
```

수동 재시작 테스트와 실제 휴대폰 재부팅 테스트를 모두 완료했다. 재부팅 후 다음을 확인했다.

```text
Magisk root 정상
Iris 자동 실행 정상
TCP 3000 listen 정상
/config 응답 및 기존 botId 복원 정상
DB Polling / DBObserver / Notification Poller 시작 정상
```

재부팅 후 CPU는 8코어 합계 기준 약 94.5% idle이었고 Iris 메모리 사용량은 약 28 MiB였다. 초기 부팅 직후의 일시적인 느려짐 외에 Iris가 CPU를 지속 점유하는 상태는 아니었다.

주의: `/data/local/tmp/Iris.apk`를 삭제하거나 이동하면 자동 시작이 실패한다.

## Iris 접속 방식

Iris는 휴대폰 화면에 일반 앱 UI를 띄우는 방식이 아니라 root 권한의 백그라운드 프로세스로 실행된다. USB 케이블이나 PC는 설치, 제어, 로그 확인과 개발 중 포트 전달에 편리하지만 Iris 실행 자체에는 필요하지 않다.

USB 연결 중 PC에서 Dashboard를 사용할 때:

```powershell
$adb = 'C:\Users\Administrator\Desktop\platform-tools\adb.exe'
& $adb forward tcp:3000 tcp:3000
```

```text
http://127.0.0.1:3000/dashboard
```

같은 Wi-Fi에서는 휴대폰의 현재 IP를 확인한 뒤 다음 주소를 사용한다.

```text
http://[ANDROID_IP]:3000/dashboard
```

마지막으로 확인한 회사 Wi-Fi 주소는 `172.16.11.47`이었지만 DHCP 주소이므로 다시 확인해야 한다. 회사 Wi-Fi에서는 약 50% 패킷 손실과 약 971 ms 지연이 관측되어 직접 접속이 불안정했다. 개인 Wi-Fi에서는 다시 측정한다.

Lightsail 같은 외부 서버에서는 휴대폰의 사설 IP로 직접 접근할 수 없다. Iris의 3000 포트를 공용 인터넷에 노출하지 말고, 배포 단계에서 휴대폰의 outbound push, Tailscale 또는 인증된 reverse tunnel 중 하나를 선택한다.

## 현재 재개 지점

- 루팅, Magisk, KakaoTalk 로그인, Iris 설치, 양방향 통신과 재부팅 자동 시작까지 완료
- 오늘 마지막 실기기 검증 시 root, Iris 프로세스, TCP 3000, `/config`가 모두 정상이었음
- 문서 갱신 시점에는 USB가 분리되어 `adb devices`에 기기가 나타나지 않았음
- Python/FastAPI Backend 코드는 아직 작성하지 않음
- 다음 작업은 로컬 MVP Backend를 만들고 `!핑 → 퐁` 왕복을 구현하는 것

Iris 공식 파일 검증값:

```text
Iris.apk
SHA-256: 00eaa7800f904b7e3082277525adbbc0581ffe9efdb1c7a475561361f918eab0

iris_control.ps1
SHA-256: 3d6f970c41b340d785a6d5823d2f149d08f3c1d87f93ef1e9c9ca9e68eef8db8
```

`iris_control.ps1`도 검토했다. APK를 `/data/local/tmp/Iris.apk`로 복사하고 root `app_process`로 `party.qwer.iris.Main`을 실행하는 구조다.

## 다음 작업 순서

### 1. 기기 연결 시 상태 재확인

```powershell
$adb = 'C:\Users\Administrator\Desktop\platform-tools\adb.exe'
& $adb devices -l
& $adb shell magisk -c
& $adb shell su -c id
& $adb shell su -c 'ss -ltnp'
```

기대 결과에 `30.7`, `uid=0(root)`와 TCP `3000` listen 상태가 있어야 한다. Iris가 이미 자동 실행되므로 APK 설치나 수동 실행을 반복하지 않는다.

### 2. 개발 중 USB 포트 전달

```powershell
& $adb forward tcp:3000 tcp:3000
```

### 3. 첫 Backend MVP

```text
KakaoTalk 테스트방: !핑
→ Iris
→ Local FastAPI
→ Iris
→ KakaoTalk: 퐁
```

FastAPI에서 Iris WebSocket에 연결해 이벤트를 받고, `!핑` 명령만 식별한 뒤 Iris `/reply`를 호출한다. 먼저 나와의 채팅이나 테스트방에서만 검증한다.

### 4. 기능 확장

통신이 확인된 뒤 다음 순서로 확장한다.

1. 환경설정 및 비밀값 분리
2. `room_id` / `sender_id` 기반 허용 목록과 권한 관리
3. PostgreSQL 메시지 저장 및 보존 정책
4. 입퇴장 관리와 게임 API
5. AI API 연동
6. Docker 구성과 Lightsail 배포
7. 휴대폰과 외부 Backend 사이의 안전한 네트워크 경로 구성

## 안전 규칙

- OEM 잠금 해제를 끄거나 Bootloader를 다시 잠그지 않는다.
- 순정 AP, 패치 AP, Firmware, Odin, APK와 API secret을 Git에 커밋하지 않는다.
- Root 상태에서 Samsung OTA 업데이트를 적용하지 않는다. 업데이트가 필요하면 현재 기기에 맞는 새 순정 AP를 같은 기기에서 다시 패치하는 공식 절차를 따른다.
- 모델, CSC와 Bootloader revision이 불확실하면 Firmware Flash를 진행하지 않는다.
- Iris의 HTTP 포트나 KakaoTalk 데이터베이스 접근 기능을 공용 인터넷에 직접 노출하지 않는다.
- 실제 채팅 저장 전 저장 여부 고지, 보존 기간, 최소 수집과 AI API 전달 범위를 정한다.
- 채팅방은 이름이 아니라 Iris가 제공하는 `room_id/chat_id`를 기준으로 식별한다.

## 공식 참고 자료

- Magisk 설치: `https://topjohnwu.github.io/Magisk/install.html`
- Magisk 저장소: `https://github.com/topjohnwu/Magisk`
- Bifrost: `https://github.com/zacharee/Bifrost`
- Iris: `https://github.com/dolidolih/Iris`
- Iris v0.32: `https://github.com/dolidolih/Iris/releases/tag/v0.32`
