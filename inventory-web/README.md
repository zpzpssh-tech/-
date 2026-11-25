# 올투게더나우 재고관리 (웹 프로그램판)

구글 시트·Apps Script 없이 돌아가는 버전입니다.

- **화면**: Vercel. 이 저장소에 코드가 올라가면 자동으로 새 버전이 배포됩니다 (코드 붙여넣기 필요 없음)
- **데이터**: Supabase (전용 데이터베이스, 자동 백업)
- **로그인**: 이메일로 받은 로그인 링크 (비밀번호 없음). `allowed_users` 표에 등록된 이메일만 들어올 수 있음

## 처음 한 번 설정

### 1. Supabase (데이터베이스)
1. supabase.com → **GitHub 계정으로 로그인** → **New project**
   - Name: `atgn-inventory` / Region: **Northeast Asia (Seoul)** / Database Password: 따로 적어 두기 (어디에도 붙여넣지 않기)
2. 왼쪽 **SQL Editor** → **New query** → `supabase/schema.sql` 내용을 통째로 붙여넣고 **Run**
3. 같은 곳에서 아래 한 줄을 대표님 이메일로 바꿔 **Run** (대표님을 관리자로 등록)
   ```sql
   insert into allowed_users (email, role) values ('대표님이메일@gmail.com', 'owner');
   ```
   직원은 `'staff'`(기록 가능), 보기만 할 사람은 `'viewer'`로 같은 방식으로 추가합니다.
4. **Project Settings → API** 에서 두 값을 확인해 둡니다 (Vercel에 넣을 값)
   - `Project URL`
   - `anon` `public` 키 (⚠️ `service_role` 키는 절대 쓰지 않기)

### 2. Vercel (화면)
1. Vercel → **Add New… → Project** → 이 GitHub 저장소 **Import**
2. **Root Directory**: `inventory-web` (Edit 눌러서 선택)
3. **Environment Variables** 두 개 추가
   - `SUPABASE_URL` = Supabase의 Project URL
   - `SUPABASE_ANON_KEY` = Supabase의 anon public 키
4. **Deploy** → 끝나면 나오는 주소(…vercel.app)를 복사

### 3. 로그인 링크 주소 맞추기
Supabase → **Authentication → URL Configuration**
- **Site URL**: Vercel 주소 (예: `https://atgn-inventory.vercel.app`)
- **Redirect URLs**: 같은 주소 추가

### 4. 데이터 옮기기
1. 예전 재고DB 구글 시트 → **파일 → 다운로드 → Microsoft Excel (.xlsx)**
2. 새 프로그램 → **엑셀 불러오기/내보내기 → 예전 프로그램(구글 시트)에서 옮겨 오기** → 파일 올리기 → **이대로 옮기기**

## 폴더
- `src/index.html` — 화면
- `src/db.js` — 데이터베이스 읽기·쓰기 (예전 Code.gs 역할)
- `supabase/schema.sql` — 데이터베이스 표 · 권한 · 한 번에 저장하는 기능
- `build.js` — 배포할 때 `public/` 폴더와 설정 파일(config.js)을 만듦

## 아직 예전 프로그램에만 있는 것 (다음 단계)
- 네이버 '원가 관리' 시트 읽기와 매일 자동 출고 → **네이버 커머스 API 직접 연결**로 새로 만들 예정
- 견적서 PDF는 구글 드라이브 저장 대신 **내려받기**로 바뀜
