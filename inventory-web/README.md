# 올투게더나우 재고관리 (웹 프로그램판)

구글 시트·Apps Script 없이 돌아가는 버전입니다.

- **화면**: Vercel. 이 저장소에 코드가 올라가면 자동으로 새 버전이 배포됩니다 (코드 붙여넣기 필요 없음)
- **데이터**: Supabase (전용 데이터베이스, 자동 백업)
- **로그인**: 이메일로 받은 로그인 링크 (비밀번호 없음). `allowed_users` 표에 등록된 이메일만 들어올 수 있음

## 처음 한 번 설정 (Vercel 안에서 버튼으로)

1. 이 저장소를 Vercel 프로젝트로 가져오기 (Root Directory 는 비워 둬도 됨 — 맨 위 vercel.json 이 알아서 이 폴더를 배포)
2. Vercel 프로젝트 → **Storage** → **Create Database** → **Supabase** → Region **Seoul** → 이 프로젝트에 **Connect**
   - 주소·공개 키·데이터베이스 접속 정보가 환경 변수로 **자동으로** 들어감 (복사·붙여넣기 없음)
3. **Deployments → Redeploy** — 배포하면서 데이터베이스 표가 **자동으로** 만들어짐
4. Supabase 화면(Storage 에서 Open in Supabase) → **Authentication → URL Configuration → Site URL** 에 Vercel 주소 입력
5. 프로그램 주소로 들어가 이메일 로그인 → **처음 로그인한 사람이 자동으로 대표(owner)** 가 됨
   - 다른 사람이 먼저 들어오는 것을 막으려면 Vercel 환경 변수 `OWNER_EMAIL` 에 대표님 이메일을 넣어 두면 됨

> 직접 만든 Supabase 프로젝트를 쓸 때는 `SUPABASE_URL`, `SUPABASE_ANON_KEY`(공개 키), `POSTGRES_URL` 을 환경 변수로 넣으면 똑같이 동작합니다.
> ⚠️ `service_role`/secret 키는 화면에 들어가지 않도록 막아 두었습니다.

### 데이터 옮기기
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
