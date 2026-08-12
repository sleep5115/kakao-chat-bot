# KakaoTalk Playground Bot — 프로젝트 컨텍스트

최종 갱신: 2026-08-12

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

## 현재 상태 — 루팅 완료

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

## 현재 재개 지점

- KakaoTalk: 공장초기화 후 아직 설치/로그인 완료되지 않음
- Iris: 공식 최신 안정 릴리스 `v0.32` 다운로드와 SHA-256 검증까지만 완료, 기기에서 아직 실행하지 않음
- 마지막 확인 Wi-Fi IPv4: `172.16.11.47` (DHCP 주소이므로 재개 시 다시 조회)
- 공장초기화 직후 시스템이 기본 앱을 `dex2oat`로 최적화하며 일시적으로 매우 느렸음
- 당시 높은 CPU 사용 주체는 `system_server`, Google Play 서비스와 기본 앱 최적화였고 root 실패 징후는 없었음

Iris 공식 파일 검증값:

```text
Iris.apk
SHA-256: 00eaa7800f904b7e3082277525adbbc0581ffe9efdb1c7a475561361f918eab0

iris_control.ps1
SHA-256: 3d6f970c41b340d785a6d5823d2f149d08f3c1d87f93ef1e9c9ca9e68eef8db8
```

`iris_control.ps1`도 검토했다. APK를 `/data/local/tmp/Iris.apk`로 복사하고 root `app_process`로 `party.qwer.iris.Main`을 실행하는 구조다.

## 주말 재개 순서

### 1. 기기와 root 재확인

```powershell
$adb = 'C:\Users\Administrator\Desktop\platform-tools\adb.exe'
& $adb devices -l
& $adb shell magisk -c
& $adb shell su -c id
```

기대 결과에 `30.7`과 `uid=0(root)`가 있어야 한다.

### 2. 기기 안정화 확인

초기 최적화가 끝났는지 다음으로 확인한다.

```powershell
& $adb shell uptime
& $adb shell top -b -n 1 -m 10
```

`dex2oat`가 계속 높은 CPU를 사용하면 충전 상태로 잠시 더 둔다.

### 3. KakaoTalk 준비

1. Google Play 또는 Galaxy Store의 공식 KakaoTalk 설치
2. 개인 메인 계정이 아닌 봇 전용 Kakao 계정으로 로그인
3. KakaoTalk 채팅 목록까지 정상 진입 확인
4. 봇을 사용할 테스트 채팅방 준비

계정 인증과 약관 동의는 사용자가 직접 수행한다.

### 4. Iris 설치와 실행

공식 저장소의 최신 릴리스가 여전히 `v0.32`인지 먼저 확인한다. 버전이 바뀌었다면 공식 GitHub의 릴리스 자산과 digest를 다시 검증한다.

준비된 검증 APK 경로:

```text
C:\Users\Administrator\Android\SM-J600L\tools\iris\v0.32\Iris.apk
```

공식 방식대로 APK를 `/data/local/tmp/Iris.apk`에 복사하고 `iris_control.ps1`로 start/status를 수행한다. Superuser 팝업이 나오면 Iris 관련 요청인지 확인한 뒤 허용한다.

### 5. Dashboard 확인

기기 IP를 다시 구한다.

```powershell
& $adb shell ip -4 addr show wlan0
```

PC 브라우저에서 다음에 접속한다.

```text
http://[ANDROID_IP]:3000/dashboard
```

Iris 포트 `3000`은 인터넷에 직접 노출하지 않는다.

### 6. 첫 통합 테스트

```text
KakaoTalk: !핑
→ Iris
→ Local FastAPI
→ Iris
→ KakaoTalk: 퐁
```

통신이 확인된 뒤 room_id/sender_id 확인, PostgreSQL 메시지 저장, 입퇴장 관리, 게임 API, AI 기능 순으로 확장한다.

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
