# 설레임 소개팅

카드를 좌우로 넘기며 마음에 드는 사람에게 ♥, 서로 ♥하면 매칭되어 1:1 채팅을 할 수 있는 웹 소개팅 앱입니다.

- 화면: GitHub Pages (무료, 24시간)
- 회원가입 · 프로필 · 매칭 · 실시간 채팅: Supabase (무료 DB + 로그인)

## 기능

- 이메일 회원가입 / 로그인
- 프로필: 이름, 태어난 해, 성별, 만나고 싶은 성별, 지역, 관심사(최대 5개), 자기소개
- 스와이프: 카드를 드래그하거나 ✕ / ♥ 버튼 (PC는 ← / → 키)
- 서로 좋아요 → 매칭 팝업 → 바로 채팅
- 실시간 1:1 채팅, 새 메시지/새 매칭 알림 점
- 필터: 나이 범위, 지역, 관심사

## 파일

- `index.html`: 앱 전체 (화면, 디자인, 동작 코드, Supabase 설정)
  - Supabase 주소/키: `window.DATING_CONFIG`
  - 지역/관심사 목록: `REGIONS`, `INTERESTS`
- `supabase-setup.sql`: Supabase에 한 번 실행할 DB 설정 (사이트에는 필요 없음)

`DATING_CONFIG`가 비어 있으면 **데모 모드**로 동작합니다. 가짜 프로필 16명이 들어 있고,
좋아요를 누르면 일부와 매칭되며, 채팅하면 자동으로 답장이 옵니다. 데이터는 내 브라우저에만 저장됩니다.

## 1. Supabase 설정 (한 번만)

밸런스 게임에서 쓰던 프로젝트를 그대로 써도 되고, 새 프로젝트를 만들어도 됩니다.

1. https://supabase.com → 프로젝트 선택 (또는 **New project**, Region은 Seoul 추천)
2. 왼쪽 메뉴 **SQL Editor** → `supabase-setup.sql` 내용을 붙여넣고 **Run**
3. **Authentication → Sign In / Providers → Email**
   - 테스트할 때는 **Confirm email** 을 끄면 가입 즉시 로그인됩니다.
   - 켜두려면 **Authentication → URL Configuration → Site URL** 을 배포 주소
     (`https://<내아이디>.github.io/dating-app/`)로 바꿔야 인증 메일 링크가 제대로 열립니다.
4. **Project Settings → API** 에서 두 값을 복사해 `index.html`의 `DATING_CONFIG`에 붙여넣기
   - Project URL → `SUPABASE_URL`
   - `anon` / `publishable` 키 → `SUPABASE_KEY`
   - ⚠️ `service_role` / `secret` 키는 절대 넣지 마세요

### 보안 구조

- 프로필은 로그인한 사람만 볼 수 있고, 수정은 본인 것만 가능
- 좋아요/넘기기는 `swipe()` 함수로만 기록되며, **누가 나를 좋아했는지는 볼 수 없음**
- 매칭은 서로 좋아요일 때만 서버에서 생성 (브라우저에서 직접 만들 수 없음)
- 채팅 메시지는 그 매칭의 두 사람만 읽고 쓸 수 있음

## 2. GitHub에 올리기

1. https://github.com/new 에서 새 저장소 생성 (예: `dating-app`, **Public**)
2. 이 폴더에서:

   ```bash
   git init -b main
   git add .
   git commit -m "소개팅 앱"
   git remote add origin https://github.com/<내아이디>/dating-app.git
   git push -u origin main
   ```

3. 저장소 → **Settings → Pages** → Source: **Deploy from a branch** → Branch: `main` / `/ (root)` → **Save**

1~2분 뒤 `https://<내아이디>.github.io/dating-app/` 로 접속할 수 있습니다.

## 로컬에서 미리 보기

```bash
python3 -m http.server 8000
```

→ 브라우저에서 http://localhost:8000

실제 매칭/채팅을 테스트하려면 **브라우저 두 개**(예: 일반 창 + 시크릿 창)에서 서로 다른 계정으로
가입한 뒤, 서로 상대에게 ♥를 누르세요.

## 참고

- 사진 업로드는 없고, 이름 첫 글자 + 색 그라데이션으로 프로필 이미지를 대신합니다.
- 나이는 `올해 - 태어난 해`로 계산합니다.
- 테스트 데이터 초기화 (SQL Editor):

  ```sql
  truncate public.messages, public.matches, public.likes;   -- 매칭/채팅만
  delete from public.profiles;                               -- 프로필까지
  ```
