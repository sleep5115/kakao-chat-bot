# KakaoTalk Playground Bot

Samsung Galaxy J6에서 실행 중인 Iris와 연결하는 Python/FastAPI 백엔드입니다.
등록된 KakaoTalk 채팅방에서 정확한 `!핑` 메시지를 받으면 같은 방에 `퐁`을
전송합니다. 미등록 방에서는 일반 명령을 처리하지 않습니다.

## 동작 구조

```text
KakaoTalk !핑
  -> Iris /ws
  -> FastAPI 백그라운드 워커
  -> Iris /reply (json.chat_id 사용)
  -> KakaoTalk 퐁
```

Iris의 3000 포트를 공용 인터넷에 직접 노출하지 않습니다. 로컬 개발에서는
ADB 포트 전달을 사용하고, Lightsail 배포 시에는 Tailscale 또는 인증된 reverse
tunnel처럼 휴대폰에서 시작하는 안전한 연결 경로를 사용합니다.

## 채팅방 등록

`나와의 채팅`은 다른 사용자가 접근할 수 없는 관리자 콘솔로 사용합니다.

1. 나와의 채팅에서 `!등록코드`를 보냅니다.
2. 봇이 복사하기 쉬운 두 개의 말풍선으로 명령과 안내를 보냅니다.

   ```text
   !봇등록 949998
   ```

   ```text
   10분 안에 위 명령을 등록할 채팅방에 입력하세요.
   ```

3. 첫 번째 말풍선을 복사해 대상 방에 보냅니다.
4. `봇 등록이 완료되었습니다.`가 오면 해당 방에서 일반 명령을 사용할 수 있습니다.
5. 이어지는 개인정보 안내에서 저장 항목과 삭제 방법을 확인합니다.

등록 코드는 6자리 숫자이며 10분 동안 한 번만 사용할 수 있습니다. 새 코드를
발급하면 이전 코드는 폐기됩니다. `DirectChat`, `MultiChat`, `OD`, `OM` 방만
등록할 수 있고 `MemoChat`은 관리자용, `PlusChat`은 항상 등록 대상에서 제외됩니다.

등록정보는 로컬에서 기본적으로 `data/kakao_bot.db`에 저장되며 방 ID, 방 유형,
등록 시각만 보관합니다. 방 이름, 사용자 ID와 메시지 내용은 저장하지 않습니다.
이 파일은 Git에서 제외됩니다. 운영에서는 `ROOM_DATABASE_URL`을 지정하면 같은
스키마를 봇 전용 PostgreSQL database에 저장합니다.

등록 정보는 방이 등록된 동안만 보관합니다. 등록된 방에서 `!봇해제`를 입력하면
해당 방의 등록 정보를 즉시 삭제하고 이후 명령 처리를 중단합니다. `!봇정보`를
입력하면 현재 저장 정책을 다시 확인할 수 있습니다.

## 로컬 실행

Python 3.11 이상과 Android Platform Tools가 필요합니다.

```powershell
adb devices -l
adb shell magisk -c
adb shell su -c id
adb shell su -c 'ss -ltnp'
adb forward tcp:3000 tcp:3000

py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m kakao_bot
```

기본 설정은 `http://127.0.0.1:3000`의 Iris에 연결합니다. 다른 값이 필요하면
[`.env.example`](.env.example)을 참고해 PowerShell 환경변수로 지정합니다.

```powershell
$env:IRIS_BASE_URL = 'http://127.0.0.1:3000'
$env:BOT_ALLOWED_ROOM_IDS = '1234567890'
$env:BOT_ALLOWED_SENDER_IDS = '9876543210'
$env:ROOM_DATABASE_PATH = 'data/kakao_bot.db'
```

환경변수 허용 목록은 등록 시스템 위에 추가로 적용하는 긴급 제한 기능입니다.
기본값인 빈 상태에서는 SQLite에 등록된 방과 `MemoChat`만 명령을 사용할 수
있습니다. 새 방을 추가할 때 환경변수 변경이나 서버 재시작은 필요하지 않습니다.

PostgreSQL 전환 시에는 비밀번호를 Git 파일에 기록하지 않고 운영 환경변수로만
전달합니다.

```powershell
$env:ROOM_DATABASE_URL = 'postgresql://kakao_bot_app:<secret>@<private-host>:5432/kakao_bot'
```

SQLite 등록 이전 명령과 Lightsail 실행 방법은
[`deploy/lightsail/README.md`](deploy/lightsail/README.md)를 참고합니다.

상태 확인:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

`ready`가 HTTP 200과 `iris_connected: true`를 반환하면 Iris WebSocket 연결이
완료된 상태입니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Docker

운영 Compose는 기존 Pickty의 `pickty-infra_default` 네트워크만 공유하고 공용
포트를 열지 않습니다.

```bash
docker compose -f deploy/lightsail/docker-compose.yml up -d --build
```
