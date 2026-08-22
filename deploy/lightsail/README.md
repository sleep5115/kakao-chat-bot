# Lightsail deployment

Kakao Bot은 Pickty와 코드·컨테이너·database/user를 분리하고 아래 인프라만
공유합니다.

- Docker network: `pickty-infra_default`
- PostgreSQL container: `pickty-postgres`
- PostgreSQL database/user: `kakao_bot` / `kakao_bot_app`

봇은 공용 HTTP 포트를 열지 않으며 Pickty Nginx 설정에도 추가하지 않습니다.
Compose의 상태 확인은 컨테이너 내부 `/health/live`만 사용합니다.

Discord `/카톡` 브리지는 `discord-kakao-bot` 별도 컨테이너로 실행됩니다. Discord
Gateway에는 outbound WebSocket으로 연결하고, 카카오봇에는 Docker 내부 주소
`http://kakao-bot:8000`으로 전달하므로 이 서비스에도 공용 포트가 없습니다.

## 운영 서버 현황

2026-08-22 Lightsail에 다음 항목을 생성하고 실제 비밀번호 접속까지 검증했습니다.

- `kakao_bot_app` 로그인 역할
- `kakao_bot` database (`kakao_bot_app` 소유)
- `registered_rooms` 최소 등록 테이블
- `/home/ubuntu/.config/kakao-bot/runtime.env` (`ubuntu:ubuntu`, mode `600`)

Pickty의 `pickty`, `pickty_dev`, `pickty_prod` database와 기존 역할은 변경하지
않았습니다. 운영 비밀번호는 Git이나 이 문서에 기록하지 않습니다.

같은 날 현재 소스로 Lightsail에서 `kakao-chat-bot:predeploy` 이미지를 빌드했고,
이미지 내부 Psycopg를 사용해 운영 DB의 활성 등록 1건을 읽는 통합 검증도
통과했습니다.

Tailscale 인증 후 운영 Compose도 실제 기동했습니다. Compose 프로젝트명은
`kakao-chat-bot`으로 고정해 같은 서버의 Pickty Compose와 orphan 범위가 겹치지
않습니다. 검증 결과는 다음과 같습니다.

- `kakao-bot`: running / healthy / restart 0
- `/health/ready`: HTTP 200, `iris_connected=true`
- Lightsail container → Android Iris `/config`: HTTP 200
- 운영 KakaoTalk `!핑 → 퐁`: Iris `/reply` HTTP 200
- Pickty API/Nginx: 재시작 없이 기존 상태 유지

## 필수 환경변수

서버의 `/home/ubuntu/.config/kakao-bot/runtime.env`에 아래 키를 둡니다.

```dotenv
ROOM_DATABASE_URL=postgresql://kakao_bot_app:<secret>@pickty-postgres:5432/kakao_bot
IRIS_BASE_URL=http://<private-iris-endpoint>:3000
DISCORD_BOT_TOKEN=<discord-bot-token>
DISCORD_GUILD_ID=<allowed-guild-id>
DISCORD_CHANNEL_ID=
DISCORD_ALLOWED_USER_IDS=
DISCORD_ALLOWED_ROLE_IDS=
DISCORD_KAKAO_ROOM_ID=<registered-kakao-room-id>
DISCORD_BRIDGE_SECRET=<random-internal-secret>
```

`IRIS_BASE_URL`은 휴대폰과 Lightsail 사이의 Tailscale 또는 인증된 reverse
tunnel을 구성한 후 넣습니다. Iris 3000 포트를 공용 인터넷에 직접 열지 않습니다.

## Tailscale 상태

2026-08-22 공식 안정판 `1.102.3`을 Lightsail과 Samsung Galaxy J6에 설치했습니다.
Lightsail의 `tailscaled`는 enabled/active이고, Android APK는 공식 GitHub release의
SHA-256을 검증했습니다. 두 장치는 같은 tailnet에 연결됐습니다.

- Android `galaxy-j6`: `100.78.245.68`
- Lightsail `kakao-bot-lightsail`: `100.86.128.124`

Android는 Tailscale을 Always-on VPN으로 지정하고 배터리 절전 예외에 추가했습니다.
VPN lockdown은 꺼서 Tailscale 장애 시 일반 인터넷까지 차단하지 않습니다. 현재
두 장치 간 경로는 직접 연결이 아닌 Tailscale DERP 릴레이이며 실측 지연은
약 106–182ms, Iris HTTP 응답은 약 0.15초였습니다.

`galaxy-j6`와 `kakao-bot-lightsail`은 전용 운영 장치이므로 관리자 콘솔에서
`Disable key expiry`를 적용했고, 두 장치 모두 `KeyExpiry=None`을 확인했습니다.
장치를 분실하거나 교체하면 Machines에서 즉시 제거합니다.

연결 점검 시 Lightsail에서 휴대폰 Tailscale IPv4와 Iris 응답을 확인합니다.

```bash
tailscale status
curl --fail --show-error http://<android-tailscale-ip>:3000/config
```

확인되면 `runtime.env`에 다음 값을 추가합니다.

```dotenv
IRIS_BASE_URL=http://<android-tailscale-ip>:3000
```

```bash
chmod 600 /home/ubuntu/.config/kakao-bot/runtime.env
```

## 실행

서버에 이 저장소를 clone한 뒤 실행합니다.

```bash
cd ~/kakao-chat-bot
docker compose -f deploy/lightsail/docker-compose.yml up -d --build
docker compose -f deploy/lightsail/docker-compose.yml ps
docker exec kakao-bot python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/live').read().decode())"
```

`/health/ready`는 Iris WebSocket이 연결돼야 200을 반환합니다.

```bash
docker exec kakao-bot python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready').read().decode())"
```

## 자동 배포

`main`에 봇 코드·테스트·Docker·Compose 변경을 push하면
`.github/workflows/deploy.yml`이 다음 순서로 실행됩니다.

1. Python 3.12에서 전체 테스트
2. Lightsail SSH 접속
3. `~/kakao-chat-bot`에서 `git pull --ff-only`
4. 봇 전용 Compose build/up
5. Kakao bot container health와 Iris readiness 검증
6. Discord bot의 Gateway 연결 health 검증

GitHub 저장소에는 아래 Actions secrets가 필요합니다.

- `LIGHTSAIL_HOST`
- `LIGHTSAIL_USERNAME`
- `LIGHTSAIL_SSH_KEY`

운영 DB URL과 Iris URL은 GitHub에 복제하지 않고 서버의 mode `600` 환경파일을
계속 사용합니다.

첫 운영 자동배포와 Node 24 기반 최종 무경고 재실행을 통과했습니다. 서버의
`~/kakao-chat-bot`은 Git clone이며, 전환 전 수동 배포본은
`~/kakao-chat-bot.manual-backup-20260822`에 보존돼 있습니다.

## 기존 SQLite 등록 이전

SQLite 파일이 있는 PC에서 PostgreSQL에 접근 가능한 안전한 경로를 연 뒤 실행합니다.
이 명령은 활성 등록 방만 upsert하고 각 방의 이전 결과를 다시 확인합니다. 방 ID는
출력하지 않고 건수만 출력합니다.

```powershell
$env:ROOM_DATABASE_URL = 'postgresql://kakao_bot_app:<secret>@<private-db-endpoint>:5432/kakao_bot'
.\.venv\Scripts\python.exe -m kakao_bot.migrate_registry --sqlite-path data/kakao_bot.db
```

비밀번호가 포함된 URL을 PowerShell 기록이나 Git 파일에 저장하지 않습니다.
