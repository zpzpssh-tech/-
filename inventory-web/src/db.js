/*
 * 올투게더나우 재고관리 — 데이터 연결 (Supabase)
 *
 * 예전 프로그램의 Code.gs(구글 시트에 읽고 쓰던 부분)를 대신합니다.
 * 화면(index.html)은 예전처럼 api('함수이름', ...) 으로 부르고, 여기서 데이터베이스에 읽고 씁니다.
 * 함수 이름과 돌려주는 모양은 예전과 똑같이 맞춰 두어서, 화면 코드는 거의 그대로 씁니다.
 */
(function () {
  'use strict';
  const CFG = window.APP_CONFIG || {};
  const sb = window.supabase && CFG.supabaseUrl ? window.supabase.createClient(CFG.supabaseUrl, CFG.supabaseAnonKey) : null;
  const CODE_RE = /^[A-Z0-9][A-Z0-9_\-.]{0,39}$/;
  const num = (v) => { const n = Number(String(v ?? '').replace(/[^\d.-]/g, '')); return Number.isFinite(n) ? n : 0; };
  const str = (v) => String(v ?? '').trim();
  const nowIso = () => new Date().toISOString();
  const newId = () => (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now()).replace(/-/g, '').slice(0, 13);
  const HASH = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(36); };
  const FAM_TAIL = /^(?:(?:x{0,3}s|m|x{0,3}l|[2-5]xl|free|f|프리|소|중|대|특대|소형|중형|대형|\d+\s*p|\d+\s*개입?|\d+\s*쌍|set|세트|한쪽|양쪽|한팔|양팔|좌|우|왼쪽|오른쪽|블랙|검정|화이트|흰색|그레이|회색|네이비|베이지|블루|레드|핑크|스킨|그린|브라운|퍼플|옐로우)(?:\(.*\))?|\(.*\)|\[.*\])$/i;
  function famName(name) {
    const t = String(name || '').replace(/\s+/g, ' ').trim().split(' ');
    while (t.length > 1 && FAM_TAIL.test(t[t.length - 1])) t.pop();
    let s = t.join(' ');
    const m = s.match(/^(.*[가-힣])(?:x{0,3}s|m|x{0,3}l|[2-5]xl)$/i);
    if (m && m[1].trim()) s = m[1];
    return s.trim().toLowerCase();
  }

  let ME = '', ROLE = null, LITE = false;

  function need() { if (!sb) throw new Error('데이터베이스 설정(SUPABASE_URL)이 없습니다. Vercel 환경 변수를 확인해 주세요.'); }
  function canWrite() { if (ROLE !== 'owner' && ROLE !== 'staff') throw new Error('보기 전용 권한이라 기록할 수 없습니다 (permission)'); }
  async function q(p) { const { data, error } = await p; if (error) throw new Error(error.message || String(error)); return data; }
  // 1000줄 넘는 표도 끝까지 읽기
  async function all(table, cols, order) {
    const out = []; const step = 1000;
    for (let from = 0; ; from += step) {
      let p = sb.from(table).select(cols || '*').range(from, from + step - 1);
      if (order) p = p.order(order, { ascending: true });
      const rows = await q(p);
      out.push(...rows);
      if (rows.length < step) break;
    }
    return out;
  }
  async function chunked(rows, fn, size = 500) { for (let i = 0; i < rows.length; i += size) await fn(rows.slice(i, i + size)); }

  /* ---------- 로그인 ---------- */
  async function session() { need(); const { data } = await sb.auth.getSession(); return data.session; }
  async function signIn(email) {
    need();
    const { error } = await sb.auth.signInWithOtp({ email, options: { emailRedirectTo: location.origin + location.pathname } });
    if (error) throw new Error(error.message);
  }
  async function signOut() { if (sb) await sb.auth.signOut(); }
  async function whoami() {
    const s = await session(); if (!s) return null;
    ME = s.user.email || '';
    const r = await q(sb.from('allowed_users').select('role').ilike('email', ME).maybeSingle());
    ROLE = r ? r.role : null;
    return { email: ME, role: ROLE };
  }

  /* ---------- 읽기: 예전 getData와 같은 모양 ---------- */
  async function getData() {
    need();
    const [skus, partners, moves, maps, uploads, rules, memoRows, conf, quotes, orders, photos] = await Promise.all([
      all('skus', '*', 'code'), all('partners', '*', 'name'), all('moves', '*', 'at'), all('maps', '*'), all('uploads', '*', 'at'), all('rules', '*', 'updated_at'),
      q(sb.from('memo').select('*').limit(1)), all('conf', 'key,value'), all('quotes', '*', 'at'),
      all('orders_done', 'order_key,day', 'at'), LITE ? Promise.resolve(null) : all('photos', 'key,name,data'),
    ]);
    const d = {
      skus: skus.map((s) => ({ code: s.code, name: s.name, part: s.part, option: s.option, safety: num(s.safety), lead: num(s.lead) || 50, active: s.active !== false, cost: num(s.cost), retail: num(s.retail), wholesale: num(s.wholesale), costUsd: num(s.cost_usd) })),
      partners: partners.map((p) => ({ name: p.name, basis: p.basis || '직접입력', memo: p.memo || '' })),
      moves: moves.map((m) => ({ id: m.id, date: m.date, type: m.type, loc: m.loc, sku: m.sku, qty: num(m.qty), memo: m.memo, batch: m.batch || m.id, batchLabel: m.batch_label, at: m.at, by: m.by, partner: m.partner, price: num(m.price), usd: num(m.usd), fx: num(m.fx) })),
      maps: maps.map((m) => ({ id: m.id, key: m.key, sku: m.sku, mult: num(m.mult) || 1 })),
      uploads: uploads.map((u) => ({ sig: u.sig, file: u.file, units: num(u.units), at: u.at })),
      rules: rules.map((r) => ({ id: r.id, name: r.name, opt: r.opt, sku: String(r.sku).toUpperCase(), mult: num(r.mult) || 1, memo: r.memo })),
      memo: memoRows[0] ? { text: memoRows[0].text, at: memoRows[0].at, by: memoRows[0].by } : { text: '', at: '', by: '' },
      conf: Object.fromEntries(conf.map((c) => [c.key, c.value])),
      quotes: quotes.map((x) => ({ no: x.no, date: x.date, to: x.to_name, total: num(x.total), body: typeof x.body === 'string' ? x.body : JSON.stringify(x.body || {}), by: x.by, at: x.at })),
      orderDone: orders.slice(-20000).map((o) => o.order_key),
      orderDays: orders.reduce((a, o) => { if (o.day) a[o.day] = (a[o.day] || 0) + 1; return a; }, {}),
      me: ME, role: ROLE, canWrite: ROLE === 'owner' || ROLE === 'staff', sheetUrl: '', appUrl: location.origin,
    };
    if (photos) { d.photos = {}; d.photoNames = {}; photos.forEach((p) => { d.photos[p.key] = p.data; d.photoNames[p.key] = p.name; }); }
    return d;
  }
  // 저장 뒤에는 사진을 빼고 다시 읽음 (빠르게)
  async function lite(fn) { LITE = true; try { await fn(); return await getData(); } finally { LITE = false; } }

  /* ---------- 쓰기 ---------- */
  function moveRows(list, label) {
    const batch = newId(), at = nowIso();
    return list.map((m) => ({ id: newId(), date: m.date, type: m.type, loc: m.loc, sku: m.sku, qty: Number(m.qty), memo: m.memo || '', batch, batch_label: label || '', partner: m.partner || '', price: Number(m.price) || 0, usd: Number(m.usd) || 0, fx: Number(m.fx) || 0, at, by: ME }));
  }
  const API = {
    getData,
    addMoves: (list, label) => lite(async () => { canWrite(); await q(sb.from('moves').insert(moveRows(list, label))); }),
    deleteBatch: (batch) => lite(async () => { canWrite(); await q(sb.from('moves').delete().or(`batch.eq.${batch},id.eq.${batch}`)); }),
    saveSkus: (list) => lite(async () => {
      canWrite();
      const have = new Set((await all('skus', 'code')).map((s) => s.code));
      const rows = []; const seen = new Set();
      for (const s of list) {
        const code = str(s.code).toUpperCase();
        if (!CODE_RE.test(code) || !str(s.name) || seen.has(code)) continue;
        seen.add(code);
        const row = { code, name: str(s.name), part: str(s.part), option: str(s.option), safety: Math.max(0, num(s.safety)), lead: Math.max(1, num(s.lead) || 50), active: s.active !== false, retail: num(s.retail), wholesale: num(s.wholesale), updated_at: nowIso() };
        if (!have.has(code) || s.cost !== undefined) { row.cost = num(s.cost); row.cost_usd = num(s.costUsd); }
        rows.push(row);
      }
      await chunked(rows, (c) => q(sb.from('skus').upsert(c, { onConflict: 'code' })));
    }),
    deleteSku: (code) => lite(async () => {
      canWrite(); code = str(code).toUpperCase();
      const { count } = await sb.from('moves').select('id', { count: 'exact', head: true }).eq('sku', code);
      if (count) throw new Error(`${code}는 입출고 기록이 ${count}건 있어서 지울 수 없습니다. 수정에서 '사용 중' 체크를 풀어 숨겨 주세요.`);
      await q(sb.from('skus').delete().eq('code', code));
      await q(sb.from('maps').delete().eq('sku', code));
    }),
    deleteAllSkus: async (opt) => {
      canWrite(); opt = opt || {};
      // 지우기 전에 지금 내용을 파일로 내려받아 둠 (되살리기용)
      const backup = await getData();
      const blob = new Blob([JSON.stringify(backup)], { type: 'application/json' });
      const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '');
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `재고관리_백업_${stamp}.json`; a.click();
      const wipe = (t, col) => q(sb.from(t).delete().neq(col, '__none__'));
      await wipe('skus', 'code');
      if (opt.moves) { await wipe('moves', 'id'); await wipe('orders_done', 'order_key'); await wipe('uploads', 'sig'); }
      if (opt.maps) { await wipe('maps', 'id'); await wipe('rules', 'id'); }
      if (opt.photos) await wipe('photos', 'key');
      const d = await getData(); d.deleted = { backup: `재고관리_백업_${stamp}.json (내려받기 폴더)` }; return d;
    },
    editSku: async (oldCode, s) => {
      canWrite();
      oldCode = str(oldCode).toUpperCase();
      const code = str(s.code).toUpperCase(), name = str(s.name);
      if (!CODE_RE.test(code)) throw new Error('코드는 영문 대문자·숫자·하이픈(-)만 쓸 수 있습니다.');
      if (!name) throw new Error('상품명을 적어 주세요.');
      const old = await q(sb.from('skus').select('*').eq('code', oldCode).maybeSingle());
      if (!old) throw new Error('수정할 상품을 찾지 못했습니다. 새로고침 후 다시 시도해 주세요.');
      if (code !== oldCode) await q(sb.rpc('rename_sku', { old_code: oldCode, new_code: code }));
      await q(sb.from('skus').update({ name, part: str(s.part), option: str(s.option), safety: Math.max(0, num(s.safety)), lead: Math.max(1, num(s.lead) || 50), active: s.active !== false,
        retail: s.retail === undefined ? old.retail : num(s.retail), wholesale: s.wholesale === undefined ? old.wholesale : num(s.wholesale), updated_at: nowIso() }).eq('code', code));
      // 상품명이 다른 묶음으로 바뀌면 사진을 새 묶음으로 복사
      const fk = (nm) => 'f' + HASH(famName(nm));
      const oldKey = fk(old.name), newKey = fk(name), oldLegacy = 'p' + HASH(`${old.part || '기타'}|${old.name}`);
      if (oldKey !== newKey) {
        const has = await q(sb.from('photos').select('key').eq('key', newKey).maybeSingle());
        if (!has) {
          const src = (await q(sb.from('photos').select('data').eq('key', oldKey).maybeSingle())) || (await q(sb.from('photos').select('data').eq('key', oldLegacy).maybeSingle()));
          if (src) await q(sb.from('photos').insert({ key: newKey, name, data: src.data }));
        }
      }
      return getData();
    },
    savePartner: (p, oldName) => lite(async () => {
      canWrite(); const name = str(p.name); if (!name) throw new Error('거래처 이름을 적어 주세요');
      if (oldName && oldName !== name) await q(sb.from('partners').delete().eq('name', oldName));
      await q(sb.from('partners').upsert({ name, basis: p.basis || '직접입력', memo: p.memo || '', updated_at: nowIso() }));
    }),
    deletePartner: (name) => lite(async () => { canWrite(); await q(sb.from('partners').delete().eq('name', name)); }),
    saveRules: (list) => lite(async () => {
      canWrite();
      const rows = (list || []).filter((x) => x.id && x.sku).map((x) => ({ id: x.id, name: x.name || '', opt: x.opt || '', sku: String(x.sku).toUpperCase(), mult: Math.max(1, num(x.mult) || 1), memo: x.memo || '', updated_at: nowIso() }));
      await chunked(rows, (c) => q(sb.from('rules').upsert(c)));
    }),
    deleteRule: (id) => lite(async () => { canWrite(); await q(sb.from('rules').delete().eq('id', id)); }),
    saveConf: (obj) => lite(async () => {
      canWrite();
      const rows = Object.keys(obj || {}).map((k) => ({ key: k, value: String(obj[k] ?? ''), updated_at: nowIso() }));
      if (rows.some((r) => r.value.length > 200000)) throw new Error('이미지가 너무 큽니다. 작은 이미지로 올려 주세요.');
      if (rows.length) await q(sb.from('conf').upsert(rows));
    }),
    deleteConf: (key) => lite(async () => { canWrite(); await q(sb.from('conf').delete().eq('key', key)); }),
    saveQuote: (x) => lite(async () => {
      canWrite();
      await q(sb.from('quotes').upsert({ no: x.no, date: x.date || null, to_name: x.to || '', total: num(x.total), supply: num(x.supply), vat: num(x.vat), body: x.body || {}, by: ME, at: nowIso() }));
    }),
    deleteQuote: (no) => lite(async () => { canWrite(); await q(sb.from('quotes').delete().eq('no', no)); }),
    saveMemo: (text) => lite(async () => { canWrite(); await q(sb.from('memo').upsert({ id: 1, text: String(text || '').slice(0, 5000), at: nowIso(), by: ME })); }),
    saveMaps: (list) => lite(async () => {
      canWrite();
      const rows = (list || []).map((m) => ({ id: m.id, key: m.key, sku: m.sku, mult: Math.max(1, num(m.mult) || 1), updated_at: nowIso() }));
      await chunked(rows, (c) => q(sb.from('maps').upsert(c)));
    }),
    deleteMap: (id) => lite(async () => { canWrite(); await q(sb.from('maps').delete().eq('id', id)); }),
    // 주문서 차감: 기록 + 처리한 주문 + 새 연결 + 파일 서명을 한 번에 (중간에 실패하면 전부 취소)
    applyUpload: (list, newMaps, sig, file, label, orderNos, orderDay) => lite(async () => {
      canWrite();
      const moves = moveRows(list, label || '주문서 차감');
      const orders = (orderNos || []).map((n) => (typeof n === 'object' ? { no: n.no, day: n.day || orderDay || '', file } : { no: n, day: orderDay || '', file }));
      const units = list.filter((m) => m.loc !== 'pending').reduce((a, m) => a + Math.abs(Number(m.qty)), 0);
      await q(sb.rpc('apply_upload', { p_moves: moves, p_maps: (newMaps || []).map((m) => ({ id: m.id, key: m.key, sku: m.sku, mult: Math.max(1, num(m.mult) || 1) })), p_orders: orders, p_upload: { sig: sig || newId(), file: file || '', units, by: ME } }));
    }),
    savePhoto: async (key, name, data) => {
      canWrite();
      if (String(data || '').length > 200000) throw new Error('사진이 너무 큽니다. 다른 사진으로 다시 시도해 주세요.');
      await q(sb.from('photos').upsert({ key, name: name || '', data, updated_at: nowIso() }));
      return { ok: true, key };
    },
    deletePhoto: async (key) => { canWrite(); await q(sb.from('photos').delete().in('key', [].concat(key))); return { ok: true }; },
    // 오늘 달러 환율 (유럽중앙은행 기준 공개 환율)
    getFx: async () => {
      const r = await fetch('https://api.frankfurter.app/latest?from=USD&to=KRW');
      if (!r.ok) throw new Error('환율을 가져오지 못했습니다');
      const j = await r.json(); return Math.round(j.rates.KRW * 100) / 100;
    },
    // 견적서 PDF: 구글 드라이브 대신 바로 내려받기
    savePdf: async (b64, filename) => {
      const bin = atob(b64), u8 = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
      const url = URL.createObjectURL(new Blob([u8], { type: 'application/pdf' }));
      const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
      return url;
    },
    // 아래 기능은 다음 단계(네이버 연결)에서 새로 만듭니다
    readNaverSheet: async () => { throw new Error('새 프로그램에서는 구글 시트 대신 네이버 주문 엑셀 파일을 올려 주세요. (네이버 자동 연결은 준비 중입니다)'); },
    runAutoNaver: async () => { throw new Error('네이버 자동 출고는 네이버 API 연결 후 사용할 수 있습니다 (준비 중)'); },
    setAutoNaver: async () => { throw new Error('네이버 자동 출고는 네이버 API 연결 후 사용할 수 있습니다 (준비 중)'); },
    exportSheet: async () => { throw new Error('새 프로그램에서는 엑셀 파일로 내려받아 주세요'); },
  };

  /* ---------- 예전 프로그램(구글 시트)에서 옮겨 오기 ----------
   * 재고DB 구글 시트에서 [파일 → 다운로드 → Microsoft Excel(.xlsx)]로 받은 파일을 그대로 읽습니다. */
  const MOVE_CODE = { '발주 등록': 'order', '입고': 'inbound', '파스토 이동(출)': 'fassto_out', '파스토 이동(입)': 'fassto_in', '로켓 출고': 'rocket', '거래처 출고': 'b2b', '개별 출고': 'ship', 'N배송 판매': 'nsale', '반품 입고': 'return', '불량·폐기': 'loss', '실사 조정': 'adjust' };
  const LOC_CODE = { '본사창고': 'hq', '파스토': 'fassto', '입고예정': 'pending' };
  const dayStr = (v) => { const t = str(v); const m = t.match(/(\d{4})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})/); if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`; const m2 = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})/); if (m2) return `${m2[3].length === 2 ? '20' + m2[3] : m2[3]}-${m2[1].padStart(2, '0')}-${m2[2].padStart(2, '0')}`; return null; };
  const tsStr = (v) => { const t = str(v); if (!t) return nowIso(); const d = new Date(t.replace(' ', 'T')); return isNaN(d) ? nowIso() : d.toISOString(); };
  function planImport(wb, XLSX) {
    const tab = (n) => { const ws = wb.Sheets[n]; if (!ws) return []; return XLSX.utils.sheet_to_json(ws, { header: 1, defval: '', raw: false }).slice(1).filter((r) => r.some((c) => str(c))); };
    const P = {};
    P.skus = tab('SKU').filter((r) => CODE_RE.test(str(r[0]).toUpperCase()) && str(r[1])).map((r) => ({ code: str(r[0]).toUpperCase(), name: str(r[1]), part: str(r[2]), option: str(r[3]), safety: Math.max(0, num(r[4])), lead: Math.max(1, num(r[5]) || 50), active: str(r[6]) !== 'N', cost: num(r[8]), retail: num(r[9]), wholesale: num(r[10]), cost_usd: num(r[11]) }));
    P.partners = tab('거래처').filter((r) => str(r[0])).map((r) => ({ name: str(r[0]), basis: str(r[1]) || '직접입력', memo: str(r[2]) }));
    P.moves = tab('기록').filter((r) => str(r[0]) && dayStr(r[1]) && str(r[4])).map((r) => ({ id: str(r[0]), date: dayStr(r[1]), type: MOVE_CODE[str(r[2])] || str(r[2]), loc: LOC_CODE[str(r[3])] || str(r[3]), sku: str(r[4]).toUpperCase(), qty: num(r[5]), memo: str(r[6]), batch: str(r[7]), batch_label: str(r[8]), at: tsStr(r[9]), by: str(r[10]), partner: str(r[11]), price: num(r[12]), usd: num(r[13]), fx: num(r[14]) }));
    P.maps = tab('연결표').filter((r) => str(r[0]) && str(r[2])).map((r) => ({ id: str(r[0]), key: str(r[1]), sku: str(r[2]), mult: Math.max(1, num(r[3]) || 1) }));
    P.rules = tab('매칭규칙').filter((r) => str(r[0]) && str(r[3])).map((r) => ({ id: str(r[0]), name: str(r[1]), opt: str(r[2]), sku: str(r[3]).toUpperCase(), mult: Math.max(1, num(r[4]) || 1), memo: str(r[5]) }));
    P.photos = tab('상품사진').filter((r) => str(r[0]) && /^data:image\//.test(str(r[2]))).map((r) => ({ key: str(r[0]), name: str(r[1]), data: str(r[2]) }));
    P.conf = tab('설정').filter((r) => str(r[0])).map((r) => ({ key: str(r[0]), value: String(r[1] ?? '') }));
    P.quotes = tab('견적서').filter((r) => str(r[0])).map((r) => { let body = {}; try { body = JSON.parse(String(r[6] || '{}')); } catch (e) { /* 깨진 내용은 비움 */ } return { no: str(r[0]), date: dayStr(r[1]), to_name: str(r[2]), total: num(r[3]), supply: num(r[4]), vat: num(r[5]), body, by: str(r[7]), at: tsStr(r[8]) }; });
    P.orders_done = [...new Map(tab('처리주문').filter((r) => str(r[0])).map((r) => [str(r[0]), { order_key: str(r[0]), day: dayStr(r[1]), file: str(r[2]), at: tsStr(r[3]) }])).values()];
    P.uploads = [...new Map(tab('업로드').filter((r) => str(r[0])).map((r) => [str(r[0]), { sig: str(r[0]), file: str(r[1]), units: num(r[2]), at: tsStr(r[3]), by: str(r[4]) }])).values()];
    const memo = tab('메모')[0]; P.memo = memo ? [{ id: 1, text: str(memo[0]), at: tsStr(memo[1]), by: str(memo[2]) }] : [];
    // 이름이 겹치는 줄은 마지막 것만
    for (const [k, pk] of [['skus', 'code'], ['partners', 'name'], ['moves', 'id'], ['maps', 'id'], ['rules', 'id'], ['photos', 'key'], ['conf', 'key'], ['quotes', 'no']]) P[k] = [...new Map(P[k].map((x) => [x[pk], x])).values()];
    return P;
  }
  async function runImport(P, onStep) {
    canWrite();
    if (ROLE !== 'owner') throw new Error('옮기기는 대표(owner) 계정만 할 수 있습니다');
    const order = ['skus', 'partners', 'maps', 'rules', 'conf', 'quotes', 'orders_done', 'uploads', 'memo', 'moves', 'photos'];
    const pk = { skus: 'code', partners: 'name', maps: 'id', rules: 'id', conf: 'key', quotes: 'no', orders_done: 'order_key', uploads: 'sig', memo: 'id', moves: 'id', photos: 'key' };
    for (const t of order) {
      const rows = P[t] || [];
      if (onStep) onStep(t, rows.length);
      await chunked(rows, (c) => q(sb.from(t).upsert(c, { onConflict: pk[t] })), t === 'photos' ? 50 : 500);
    }
    return getData();
  }

  window.DB = { API, session, signIn, signOut, whoami, planImport, runImport, ready: !!sb, onAuth: (fn) => sb && sb.auth.onAuthStateChange(fn) };
})();
