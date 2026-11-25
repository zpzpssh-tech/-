// Vercel이 배포할 때 실행: src/ 를 public/ 으로 복사하고, 환경 변수로 config.js 를 만듦
// (데이터베이스 주소·공개 키는 코드에 적지 않고 Vercel 설정에만 넣기 위해)
const fs = require('fs');
const path = require('path');

const src = path.join(__dirname, 'src');
const out = path.join(__dirname, 'public');
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });
for (const f of fs.readdirSync(src)) fs.copyFileSync(path.join(src, f), path.join(out, f));

const cfg = {
  supabaseUrl: process.env.SUPABASE_URL || '',
  supabaseAnonKey: process.env.SUPABASE_ANON_KEY || '',
};
if (!cfg.supabaseUrl || !cfg.supabaseAnonKey) console.warn('⚠️  SUPABASE_URL / SUPABASE_ANON_KEY 환경 변수가 없습니다. 화면에 "설정이 필요합니다"가 표시됩니다.');
fs.writeFileSync(path.join(out, 'config.js'), `window.APP_CONFIG = ${JSON.stringify(cfg)};\n`);
console.log('build ok →', out);
