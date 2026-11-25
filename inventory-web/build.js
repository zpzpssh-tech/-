// Vercel이 배포할 때 실행됩니다.
//  1) src/ 를 public/ 으로 복사
//  2) Vercel 환경 변수로 config.js 를 만듦 (데이터베이스 주소·공개 키는 코드에 적지 않음)
//  3) Vercel에서 Supabase를 연결해 두었으면(POSTGRES_URL 이 있으면) 데이터베이스 표를 자동으로 만들거나 최신으로 맞춤
//     → 대표님이 SQL을 직접 붙여넣을 필요 없음
const fs = require('fs');
const path = require('path');

const env = process.env;
const pick = (...names) => { for (const n of names) if (env[n]) return env[n]; return ''; };

async function main() {
  const src = path.join(__dirname, 'src');
  const out = path.join(__dirname, 'public');
  fs.rmSync(out, { recursive: true, force: true });
  fs.mkdirSync(out, { recursive: true });
  for (const f of fs.readdirSync(src)) fs.copyFileSync(path.join(src, f), path.join(out, f));

  // 공개용 값만 화면에 넣음 (service_role 같은 비밀 키는 절대 넣지 않음)
  const cfg = {
    supabaseUrl: pick('SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_URL'),
    supabaseAnonKey: pick('SUPABASE_ANON_KEY', 'NEXT_PUBLIC_SUPABASE_ANON_KEY', 'SUPABASE_PUBLISHABLE_KEY', 'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY'),
  };
  if (/service_role|sb_secret_/.test(cfg.supabaseAnonKey) || (cfg.supabaseAnonKey && cfg.supabaseAnonKey === env.SUPABASE_SERVICE_ROLE_KEY)) {
    throw new Error('SUPABASE_ANON_KEY 에 비밀(service_role/secret) 키가 들어 있습니다. 공개(anon/publishable) 키로 바꿔 주세요.');
  }
  if (!cfg.supabaseUrl || !cfg.supabaseAnonKey) console.warn('⚠️  Supabase 주소/공개 키가 없습니다. 화면에 "설정이 필요합니다"가 표시됩니다.');
  fs.writeFileSync(path.join(out, 'config.js'), `window.APP_CONFIG = ${JSON.stringify(cfg)};\n`);

  // 데이터베이스 표 자동 설치
  const dbUrl = pick('POSTGRES_URL_NON_POOLING', 'POSTGRES_URL', 'DATABASE_URL');
  if (!dbUrl) { console.log('ℹ️  POSTGRES_URL 이 없어 표 자동 설치는 건너뜁니다.'); return; }
  let pg;
  try { pg = require('pg'); } catch (e) { console.warn('⚠️  pg 모듈이 없어 표 자동 설치를 건너뜁니다.'); return; }
  const url = dbUrl.replace(/([?&])sslmode=[^&]*/g, '$1').replace(/[?&]$/, '');
  const client = new pg.Client({ connectionString: url, ssl: /localhost|127\.0\.0\.1/.test(url) ? false : { rejectUnauthorized: false } });
  try {
    await client.connect();
    await client.query(fs.readFileSync(path.join(__dirname, 'supabase', 'schema.sql'), 'utf8'));
    const owner = (env.OWNER_EMAIL || '').trim().toLowerCase();
    if (owner) await client.query("insert into allowed_users (email, role) values ($1, 'owner') on conflict (email) do update set role = 'owner'", [owner]);
    console.log('✅ 데이터베이스 표를 최신으로 맞췄습니다.');
  } catch (e) {
    console.warn('⚠️  데이터베이스 표 설치 실패: ' + e.message);
  } finally {
    await client.end().catch(() => {});
  }
}
main().then(() => console.log('build ok')).catch((e) => { console.error('❌ ' + e.message); process.exit(1); });
