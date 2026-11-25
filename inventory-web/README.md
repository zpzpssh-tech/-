# 올투게더나우 재고관리 (웹 프로그램판)

구글 시트·Apps Script 없이 돌아가는 버전입니다.

- **화면**: Vercel (이 저장소에 코드가 올라가면 자동으로 새 버전이 배포됨 → 코드 붙여넣기 필요 없음)
- **데이터**: Supabase (전용 데이터베이스, 자동 백업)
- **로그인**: 구글 계정. `allowed_users` 표에 등록된 이메일만 들어올 수 있음

## 처음 한 번 설정 (대표님)

1. **Supabase** (supabase.com) → GitHub 계정으로 가입 → New project
   - 이름: `atgn-inventory`, 지역: Northeast Asia (Seoul), 데이터베이스 비밀번호는 따로 적어 두기 (채팅에 붙여넣지 않기)
2. 왼쪽 **SQL Editor** → `supabase/schema.sql` 내용을 붙여넣고 **Run**
   - 맨 아래 줄의 이메일을 대표님 구글 이메일로 바꿔 한 번 더 실행
3. **Authentication → Providers → Google** 켜기 (안내 문서 따라 진행)
4. **Vercel** (vercel.com) → GitHub 계정으로 가입 → Add New Project → 이 저장소 선택
   - Root Directory: `inventory-web`
   - Environment Variables: `SUPABASE_URL`, `SUPABASE_ANON_KEY` (Supabase → Project Settings → API 에 있는 값)
5. 배포가 끝나면 나오는 주소(…vercel.app)로 접속

## 데이터 옮기기

지금 재고DB 구글 시트 → 새 데이터베이스로 한 번에 옮기는 기능을 프로그램 안에 넣을 예정입니다
(시트의 탭을 그대로 읽어서 표에 넣음).

## 폴더

- `supabase/schema.sql` — 데이터베이스 표 · 권한
- (진행 중) 화면 코드, 데이터 연결, 시트에서 옮기기
