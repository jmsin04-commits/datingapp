# 설레임 소개팅

조건에 맞는 사람들을 목록으로 보고 마음에 드는 사람에게 ♥, 서로 ♥하면 매칭되어 1:1 채팅을 할 수 있는 웹 소개팅 앱입니다.

- 화면: GitHub Pages (무료, 24시간)
- 회원가입 · 프로필 · 매칭 · 실시간 채팅: Supabase (무료 DB + 로그인)

## 기능

- 이메일 회원가입 / 로그인
- 나이 제한: **19~35세**만 가입·검색 가능 (서버에서도 막음)
- 프로필: 사진(최대 4장), 이름, 태어난 해, 성별, 만나고 싶은 성별, 지역, 관심사(최대 5개), 자기소개
- 탐색: 필터에 맞는 사람들을 목록으로 (폰 3명, PC 5명씩) 보고 바로 ♥
- 프로필 자세히 보기: 목록에서 사람을 누르면 크게 열림 → 사진 좌/우 탭으로 넘기기, ✕ / ♥
- 서로 좋아요 → 매칭 팝업 → 바로 채팅
- 실시간 1:1 채팅, 새 메시지/새 매칭 알림 점
- 필터: 나이 범위, 지역, 관심사(여러 개) → 적용하면 맞는 사람들을 목록으로 보여주고 인원수·조건 표시

## 파일

- `index.html`: 앱 전체 (화면, 디자인, 동작 코드, Supabase 설정)
  - Supabase 주소/키: `window.DATING_CONFIG`
  - 지역/관심사 목록: `REGIONS`, `INTERESTS`
- `supabase-setup.sql`: Supabase에 한 번 실행할 DB 설정 (사이트에는 필요 없음)

`DATING_CONFIG`가 비어 있으면 **데모 모드**로 동작합니다. 19~35세 가짜 프로필 43명이 들어 있고,
좋아요를 누르면 일부와 매칭되며, 채팅하면 자동으로 답장이 옵니다. 데이터는 내 브라우저에만 저장됩니다.

## 1. Supabase 설정 (한 번만)

밸런스 게임에서 쓰던 프로젝트를 그대로 써도 되고, 새 프로젝트를 만들어도 됩니다.

1. https://supabase.com → 프로젝트 선택 (또는 **New project**, Region은 Seoul 추천)
2. 왼쪽 메뉴 **SQL Editor** → `supabase-setup.sql` 내용을 붙여넣고 **Run**
   (사진용 Storage 버킷 `photos`도 함께 만들어집니다. 파일이 바뀌면 다시 Run 해도 안전합니다)
3. **Authentication → Sign In / Providers → Email**
   - 테스트할 때는 **Confirm email** 을 끄면 가입 즉시 로그인됩니다.
   - 켜두려면 **Authentication → URL Configuration → Site URL** 을 배포 주소
     (`https://<내아이디>.github.io/datingapp/`)로 바꿔야 인증 메일 링크가 제대로 열립니다.
4. **Project Settings → API** 에서 두 값을 복사해 `index.html`의 `DATING_CONFIG`에 붙여넣기
   - Project URL → `SUPABASE_URL`
   - `anon` / `publishable` 키 → `SUPABASE_KEY`
   - ⚠️ `service_role` / `secret` 키는 절대 넣지 마세요

### 보안 구조

- 프로필은 로그인한 사람만 볼 수 있고, 수정은 본인 것만 가능
- 좋아요/넘기기는 `swipe()` 함수로만 기록되며, **누가 나를 좋아했는지는 볼 수 없음**
- 매칭은 서로 좋아요일 때만 서버에서 생성 (브라우저에서 직접 만들 수 없음)
- 채팅 메시지는 그 매칭의 두 사람만 읽고 쓸 수 있음
- 사진은 자기 폴더(`photos/<내 id>/`)에만 올리고 지울 수 있음. 프로필에는 자기 폴더의 사진만 등록 가능
- 사진은 올리기 전에 브라우저에서 긴 변 1080px JPEG로 줄여서 올림 → 용량 절약 + **촬영 위치(GPS) 등 메타데이터 제거**

## 2. GitHub에 올리기

1. https://github.com/new 에서 새 저장소 생성 (예: `datingapp`, **Public**)
2. 이 폴더에서:

   ```bash
   git init -b main
   git add .
   git commit -m "소개팅 앱"
   git remote add origin https://github.com/<내아이디>/datingapp.git
   git push -u origin main
   ```

3. 저장소 → **Settings → Pages** → Source: **Deploy from a branch** → Branch: `main` / `/ (root)` → **Save**

1~2분 뒤 `https://<내아이디>.github.io/datingapp/` 로 접속할 수 있습니다.

## 로컬 LLM으로 데모 채팅 상대 똑똑하게 하기 (선택)

데모 모드의 채팅 상대는 기본적으로 정해진 규칙으로 답합니다.
`../local-llm`의 Qwen2.5 모델을 켜 두면, 상대가 **자기 프로필(나이·직업·관심사·자기소개)대로 행동하는 사람처럼** 대답합니다.

가장 쉬운 방법: 앱 + LLM 서버를 한 번에 켜기

```bash
./run_local.sh                         # → 브라우저에서 http://localhost:8000 (종료: Ctrl+C)
```

따로 켜려면:

```bash
pip install llama-cpp-python flask     # 처음 한 번 (local-llm 때 설치했다면 생략)
python3 llm_server.py                  # 3B 모델, http://localhost:7861
python3 llm_server.py --model 1.5b     # 더 빠르지만 덜 자연스러움
```

- 서버를 켠 **같은 PC의 브라우저**에서 앱을 열면 자동 연결되고, 제목 옆에 `데모 · AI 대화`가 표시됩니다.
  (GitHub Pages 주소로 열어도, 로컬 `python3 -m http.server`로 열어도 됩니다)
- 서버가 꺼져 있으면 기존 규칙 기반 답장으로 자동 전환됩니다.

### 폰에서도 LLM 대화 쓰기 (같은 와이파이)

GitHub Pages 주소를 폰에서 열면 폰은 PC의 LLM에 닿을 수 없어서 규칙 기반 답장이 나옵니다.
PC와 폰이 **같은 와이파이**라면, LLM 서버가 앱 화면까지 보내 주는 방식으로 폰에서도 LLM과 대화할 수 있습니다.

1. PC에서 `./run_local.sh --lan` (또는 `python3 llm_server.py --lan`)
   - 포트를 바꾸려면 `./run_local.sh --lan --port 5000` → 주소가 `http://<PC IP>:5000` (아래 7861도 5000으로)
2. Windows 설정 (처음 한 번):
   - VS Code 설정(`Ctrl+,`)에서 **Remote: Local Port Host** → `allInterfaces`
     (Dev Container의 포트를 Windows의 모든 네트워크에 연결. 바꾼 뒤 VS Code 창 다시 열기)
   - **관리자 PowerShell**에서 방화벽 허용 — **같은 와이파이(같은 서브넷)의 기기만**, '개인' 네트워크에서만:
     ```powershell
     New-NetFirewallRule -DisplayName "datingapp LLM" -Direction Inbound -Protocol TCP -LocalPort 7861 -Action Allow -Profile Private -RemoteAddress LocalSubnet
     ```
     (이미 예전 명령으로 만들었다면: `Set-NetFirewallRule -DisplayName "datingapp LLM" -RemoteAddress LocalSubnet`)
   - 와이파이가 '공용 네트워크'로 되어 있으면 Windows 설정 → 네트워크 → 해당 와이파이 → **개인 네트워크**로 변경
3. PowerShell에서 `ipconfig` → Wi-Fi의 **IPv4 주소** 확인 (예: `192.168.0.12`)
4. 폰 브라우저에서 `http://192.168.0.12:7861` → 제목 옆에 `데모 · AI 대화`가 뜨면 성공

- 접속 제한: Windows 방화벽이 **같은 와이파이의 기기만** 통과시키고, 서버도 사설 IP(192.168.x.x 등)가 아닌 접속은 거부합니다.
  공유기에서 포트포워딩을 하지 않는 한 바깥 인터넷에서는 들어올 수 없습니다.
- 같은 와이파이의 다른 사람은 접속할 수 있으니, 다 쓰면 서버를 끄세요 (Ctrl+C).
  필요 없으면 방화벽 규칙은 `Remove-NetFirewallRule -DisplayName "datingapp LLM"` 으로 지웁니다.
- 서버는 앱 화면(`index.html`)과 LLM 요청만 받고, 다른 파일은 보내지 않습니다.
- 답장은 문장 단위로 바로바로 보여줍니다: 첫 문장 약 2~4초, 전체 4~8초. 남은 문장을 쓰는 동안 "입력 중…"이 표시됩니다.
  (채팅방을 열면 그 사람의 프로필을 미리 읽어 두므로, 첫 메시지를 쓰는 동안 준비가 끝납니다. 서버 시작은 30초 정도)
- 대화 내용은 내 PC 밖으로 나가지 않습니다. 서버는 이 PC 안(127.0.0.1)에서만 열리고,
  이 앱 주소(GitHub Pages, localhost)에서 온 요청만 받습니다.
- 크롬이 "로컬 네트워크의 기기에 접근" 허용을 물으면 **허용**을 누르세요.
- 끄고 싶으면 `index.html`의 `LLM_URL`을 `""`로 바꾸세요.

## 로컬에서 미리 보기

```bash
python3 -m http.server 8000
```

→ 브라우저에서 http://localhost:8000

실제 매칭/채팅을 테스트하려면 **브라우저 두 개**(예: 일반 창 + 시크릿 창)에서 서로 다른 계정으로
가입한 뒤, 서로 상대에게 ♥를 누르세요.

## 참고

- 사진이 없으면 이름 첫 글자 + 색 그라데이션으로 대신 표시합니다.
- 사진 링크는 공개(public)라서 주소를 아는 사람은 로그인 없이도 볼 수 있습니다.
- 데모 모드에서는 사진을 작게 줄여 브라우저에 저장합니다.
- 나이는 `올해 - 태어난 해`로 계산합니다.
- 테스트 데이터 초기화 (SQL Editor):

  ```sql
  truncate public.messages, public.matches, public.likes;   -- 매칭/채팅만
  delete from public.profiles;                               -- 프로필까지
  ```
