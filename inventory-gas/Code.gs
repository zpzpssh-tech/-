/**
 * 올투게더나우 재고관리 — 구글 Apps Script 서버 코드
 *
 * 이 파일은 "재고DB" 구글 시트에 붙어서 돌아갑니다.
 * 화면(Index.html)이 여기 있는 함수들을 불러 시트를 읽고 씁니다.
 * 모든 기록은 시트 탭(SKU / 거래처 / 기록 / 연결표 / 업로드)에 한 줄씩 쌓이므로,
 * 프로그램이 없어도 시트만 열면 내용을 그대로 볼 수 있습니다.
 *
 * 열은 항상 "맨 뒤에" 추가합니다. 예전 버전으로 만든 시트도 그대로 쓸 수 있습니다.
 */

/* ---------- 처음 한 번: 시트 탭 만들기 ----------
 * 편집기 위쪽 선택칸에서 'setup'을 고르고 ▶ 실행하세요.
 * (이름 끝에 _ 가 붙은 함수는 내부용이라 선택칸에 나오지 않습니다) */
function setup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  PropertiesService.getScriptProperties().setProperty('SHEET_ID', ss.getId());
  Object.values(TABS).forEach((t) => tab_(ss, t));
  if (!rows_(TABS.PARTNER).length) append_(TABS.PARTNER, DEFAULT_PARTNERS.map((p) => [p[0], p[1], p[2], now_()]));
  return '준비 완료: ' + ss.getName();
}
const TABS = {
  SKU: { name: 'SKU', head: ['코드', '상품명', '부위', '옵션', '안전재고', '리드타임(일)', '사용', '수정일', '기준원가', '소매가', '도매가', '기준원가(USD)'] },
  PARTNER: { name: '거래처', head: ['이름', '기본 단가', '메모', '수정일'] },
  MOVE: { name: '기록', head: ['ID', '날짜', '종류', '위치', 'SKU', '수량', '메모', '묶음ID', '묶음이름', '기록시각', '기록자', '거래처', '단가', '외화단가(USD)', '환율'] },
  MAP: { name: '연결표', head: ['ID', '주문서 상품명·옵션', 'SKU', '배수', '수정일'] },
  RULE: { name: '매칭규칙', head: ['ID', '상품명에 포함', '옵션에 포함', 'SKU', '배수', '메모', '수정일'] },
  MEMO: { name: '메모', head: ['내용', '수정시각', '수정자'] },
  PHOTO: { name: '상품사진', head: ['상품키', '상품명', '사진', '수정시각'] },
  CONF: { name: '설정', head: ['항목', '값', '수정시각'] },
  QUOTE: { name: '견적서', head: ['견적번호', '견적일', '받는 곳', '합계(부가세포함)', '공급가액', '부가세', '내용(JSON)', '작성자', '작성시각'] },
  ORDER: { name: '처리주문', head: ['상품주문번호', '출고일', '파일', '기록시각'] },
  UPLOAD: { name: '업로드', head: ['서명', '파일명', '차감수량', '기록시각', '기록자'] },
};
// 시트에는 사람이 읽기 쉬운 한글로 저장하고, 프로그램 안에서는 코드로 씁니다.
const MOVE_LABEL = {
  order: '발주 등록', inbound: '입고', fassto_out: '파스토 이동(출)', fassto_in: '파스토 이동(입)',
  rocket: '로켓 출고', b2b: '거래처 출고', ship: '개별 출고', nsale: 'N배송 판매', return: '반품 입고', loss: '불량·폐기', adjust: '실사 조정',
};
const LOC_LABEL = { hq: '본사창고', fassto: '파스토', pending: '입고예정' };
// 처음 설치할 때 넣어 두는 판매 채널 (대표님 채널 기준, 시트에서 자유롭게 수정 가능)
const DEFAULT_PARTNERS = [
  ['쿠팡 로켓배송', '도매가', '쿠팡 매입(RKT)'],
  ['네이버 스마트스토어', '소매가', ''],
  ['쿠팡 올투게더나우', '소매가', 'CPG'],
  ['쿠팡 휴책', '소매가', 'HCK'],
  ['쿠팡 유큐어', '소매가', 'YCU'],
  ['도매 거래처', '도매가', '병원·센터 등 B2B'],
];
const rev_ = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [v, k]));
const MOVE_CODE = rev_(MOVE_LABEL), LOC_CODE = rev_(LOC_LABEL);

/* ---------- 웹페이지 열기 ---------- */
function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('올투게더나우 재고관리')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// 속도: 시트 열기와 탭 찾기는 한 번 실행 안에서 한 번만 하고 다시 씀 (예전엔 탭마다 시트를 새로 열었음)
let BOOK_ = null;
const SHEET_ = {};
let LITE_ = false;
// 탭 제목줄 점검은 프로그램이 바뀌었을 때 한 번만 (매번 하면 탭마다 읽기가 한 번씩 늘어남). 탭/열을 추가하면 이 값을 바꿀 것.
const SCHEMA_VER = '2026-11-23';
let SCHEMA_OK_ = null;
function schemaOk_() { if (SCHEMA_OK_ === null) SCHEMA_OK_ = PropertiesService.getScriptProperties().getProperty('SCHEMA') === SCHEMA_VER; return SCHEMA_OK_; }   // true면 getData가 사진을 빼고 보냄 (저장할 때마다 큰 사진을 다시 받지 않도록)
function book_() {
  if (BOOK_) return BOOK_;
  const id = PropertiesService.getScriptProperties().getProperty('SHEET_ID');
  const ss = id ? SpreadsheetApp.openById(id) : SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) throw new Error('재고DB 시트를 찾지 못했습니다. Apps Script 편집기에서 setup 함수를 한 번 실행해 주세요.');
  BOOK_ = ss;
  return ss;
}
function tab_(ss, t) {
  if (SHEET_[t.name]) return SHEET_[t.name];
  const sh0 = tabOpen_(ss, t);
  SHEET_[t.name] = sh0;
  return sh0;
}
function tabOpen_(ss, t) {
  let sh = ss.getSheetByName(t.name);
  if (!sh) {
    sh = ss.insertSheet(t.name);
    sh.getRange(1, 1, 1, t.head.length).setValues([t.head]).setFontWeight('bold');
    sh.setFrozenRows(1);
    // 날짜·코드가 자동으로 숫자/날짜로 바뀌지 않게 글자 형식으로 고정
    sh.getRange(1, 1, sh.getMaxRows(), t.head.length).setNumberFormat('@');
  } else if (!schemaOk_()) {
    // 예전 버전 시트: 새로 생긴 열 제목만 뒤에 채워 넣기
    const cur = sh.getRange(1, 1, 1, t.head.length).getValues()[0];
    if (String(cur[t.head.length - 1] || '') === '') {
      sh.getRange(1, 1, 1, t.head.length).setValues([t.head]).setFontWeight('bold');
      sh.getRange(1, 1, sh.getMaxRows(), t.head.length).setNumberFormat('@');
    }
  }
  return sh;
}
function rows_(t) {
  const sh = tab_(book_(), t);
  const v = sh.getDataRange().getValues();
  if (v.length < 2) return [];
  const w = t.head.length;
  return v.slice(1).map((r) => (r.length === w ? r : r.length > w ? r.slice(0, w) : r.concat(new Array(w - r.length).fill(''))));
}
function append_(t, rows) {
  if (!rows.length) return;
  const sh = tab_(book_(), t);
  const start = sh.getLastRow() + 1;
  const rng = sh.getRange(start, 1, rows.length, t.head.length);
  rng.setNumberFormat('@');
  rng.setValues(rows.map((r) => r.map((c) => (c === null || c === undefined ? '' : String(c)))));
}
function putRow_(t, rowIndex0, row) {
  const r = tab_(book_(), t).getRange(rowIndex0 + 2, 1, 1, row.length);
  r.setNumberFormat('@');
  r.setValues([row.map((c) => (c === null || c === undefined ? '' : String(c)))]);
}
function withLock_(fn) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) throw new Error('다른 사람이 기록 중입니다. 잠시 후 다시 시도해 주세요.');
  LITE_ = true;
  try { return fn(); } finally { lock.releaseLock(); LITE_ = false; }
}
const str_ = (v) => {
  if (v instanceof Date) return Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyy-MM-dd');
  return String(v === null || v === undefined ? '' : v).trim();
};
const num_ = (v) => Number(String(v === null || v === undefined ? '' : v).replace(/[^\d.-]/g, '')) || 0;
const now_ = () => Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss');
const me_ = () => { try { return Session.getActiveUser().getEmail() || ''; } catch (e) { return ''; } };
const appUrl_ = () => { try { return ScriptApp.getService().getUrl() || ''; } catch (e) { return ''; } };

/* ---------- 읽기: 화면이 쓰는 데이터 전체 ---------- */
function getData() {
  const skus = rows_(TABS.SKU).filter((r) => str_(r[0])).map((r) => ({
    code: str_(r[0]), name: str_(r[1]), part: str_(r[2]), option: str_(r[3]),
    safety: num_(r[4]), lead: num_(r[5]) || 50, active: str_(r[6]) !== 'N',
    cost: num_(r[8]), retail: num_(r[9]), wholesale: num_(r[10]), costUsd: num_(r[11]),
  }));
  const partners = rows_(TABS.PARTNER).filter((r) => str_(r[0])).map((r) => ({ name: str_(r[0]), basis: str_(r[1]) || '직접입력', memo: str_(r[2]) }));
  const moves = rows_(TABS.MOVE).filter((r) => str_(r[0])).map((r) => ({
    id: str_(r[0]), date: str_(r[1]), type: MOVE_CODE[str_(r[2])] || str_(r[2]), loc: LOC_CODE[str_(r[3])] || str_(r[3]),
    sku: str_(r[4]), qty: num_(r[5]), memo: str_(r[6]), batch: str_(r[7]) || str_(r[0]), batchLabel: str_(r[8]),
    at: str_(r[9]), by: str_(r[10]), partner: str_(r[11]), price: num_(r[12]), usd: num_(r[13]), fx: num_(r[14]),
  }));
  const maps = rows_(TABS.MAP).filter((r) => str_(r[0])).map((r) => ({ id: str_(r[0]), key: str_(r[1]), sku: str_(r[2]), mult: num_(r[3]) || 1 }));
  const uploads = rows_(TABS.UPLOAD).filter((r) => str_(r[0])).map((r) => ({ sig: str_(r[0]), file: str_(r[1]), units: num_(r[2]), at: str_(r[3]) }));
  const rules = rows_(TABS.RULE).filter((r) => str_(r[0]) && str_(r[3])).map((r) => ({ id: str_(r[0]), name: str_(r[1]), opt: str_(r[2]), sku: str_(r[3]).toUpperCase(), mult: num_(r[4]) || 1, memo: str_(r[5]) }));
  const mr = rows_(TABS.MEMO)[0] || [];
  const memo = { text: str_(mr[0]), at: str_(mr[1]), by: str_(mr[2]) };
  let photos;
  if (!LITE_) { photos = {}; rows_(TABS.PHOTO).forEach((r) => { if (str_(r[0]) && r[2]) photos[str_(r[0])] = String(r[2]); }); }
  const conf = {};
  rows_(TABS.CONF).forEach((r) => { if (str_(r[0])) conf[str_(r[0])] = String(r[1] === null || r[1] === undefined ? '' : r[1]); });
  const quotes = rows_(TABS.QUOTE).filter((r) => str_(r[0])).map((r) => ({ no: str_(r[0]), date: str_(r[1]), to: str_(r[2]), total: num_(r[3]), body: String(r[6] || ''), by: str_(r[7]), at: str_(r[8]) }));
  // 이미 재고에서 뺀 주문번호 (최근 것만 보내도 충분: 최대 2만 건)
  const orderRows = rows_(TABS.ORDER).slice(-20000);
  const orderDone = orderRows.map((r) => str_(r[0])).filter(Boolean);
  const orderDays = {}; orderRows.forEach((r) => { const d = str_(r[1]); if (d) orderDays[d] = (orderDays[d] || 0) + 1; });
  if (!LITE_ && !schemaOk_()) { PropertiesService.getScriptProperties().setProperty('SCHEMA', SCHEMA_VER); SCHEMA_OK_ = true; }
  return { skus, partners, moves, maps, uploads, rules, memo, conf, quotes, photos, orderDone, orderDays, me: me_(), sheetUrl: book_().getUrl(), appUrl: appUrl_() };
}

/* ---------- 쓰기 ---------- */
function moveRows_(list, batchLabel) {
  const batch = Utilities.getUuid().slice(0, 13), at = now_(), by = me_();
  return list.map((m) => [
    Utilities.getUuid().slice(0, 13), m.date, MOVE_LABEL[m.type] || m.type, LOC_LABEL[m.loc] || m.loc,
    m.sku, Number(m.qty), m.memo || '', batch, batchLabel || '', at, by, m.partner || '', Number(m.price) || '', Number(m.usd) || '', Number(m.fx) || '',
  ]);
}
function addMoves(list, batchLabel) {
  return withLock_(() => { append_(TABS.MOVE, moveRows_(list, batchLabel)); return getData(); });
}
function deleteBatch(batch) {
  return withLock_(() => {
    const sh = tab_(book_(), TABS.MOVE);
    const vals = rows_(TABS.MOVE);
    for (let i = vals.length - 1; i >= 0; i--) {
      if (str_(vals[i][7]) === batch || (!str_(vals[i][7]) && str_(vals[i][0]) === batch)) sh.deleteRow(i + 2);
    }
    return getData();
  });
}
function saveSkus(list) {
  return withLock_(() => {
    const vals = rows_(TABS.SKU);
    const idx = new Map(vals.map((r, i) => [str_(r[0]).toUpperCase(), i]));
    const add = [];
    list.forEach((s) => {
      const code = String(s.code || '').trim().toUpperCase();
      if (!/^[A-Z0-9][A-Z0-9_\-.]{0,39}$/.test(code) || !String(s.name || '').trim()) return;
      const row = [code, s.name, s.part || '', s.option || '', Math.max(0, num_(s.safety)), Math.max(1, num_(s.lead) || 50),
        s.active === false ? 'N' : 'Y', now_(), num_(s.cost) || '', num_(s.retail) || '', num_(s.wholesale) || '', num_(s.costUsd) || ''];
      if (idx.has(code) && idx.get(code) >= 0) putRow_(TABS.SKU, idx.get(code), row);
      else if (!idx.has(code)) { add.push(row); idx.set(code, -1); }
    });
    append_(TABS.SKU, add);
    return getData();
  });
}
/** SKU 삭제: 기록이 하나도 없는 SKU만 지울 수 있음 (있으면 '미사용'으로 숨기기) */
function deleteSku(code) {
  return withLock_(() => {
    code = String(code || '').trim().toUpperCase();
    const used = rows_(TABS.MOVE).filter((r) => str_(r[4]).toUpperCase() === code).length;
    if (used) throw new Error(`${code}는 입출고 기록이 ${used}건 있어서 지울 수 없습니다. 수정에서 '사용 중' 체크를 풀어 숨겨 주세요.`);
    const sh = tab_(book_(), TABS.SKU);
    const vals = rows_(TABS.SKU);
    for (let i = vals.length - 1; i >= 0; i--) if (str_(vals[i][0]).toUpperCase() === code) sh.deleteRow(i + 2);
    // 이 SKU로 연결해 둔 주문서 연결도 함께 정리
    const msh = tab_(book_(), TABS.MAP);
    const mv = rows_(TABS.MAP);
    for (let i = mv.length - 1; i >= 0; i--) if (str_(mv[i][2]).toUpperCase() === code) msh.deleteRow(i + 2);
    return getData();
  });
}
function savePartner(p, oldName) {
  return withLock_(() => {
    const name = String(p.name || '').trim();
    if (!name) throw new Error('거래처 이름을 적어 주세요');
    const vals = rows_(TABS.PARTNER);
    const i = vals.findIndex((r) => str_(r[0]) === (oldName || name));
    const row = [name, p.basis || '직접입력', p.memo || '', now_()];
    if (i >= 0) putRow_(TABS.PARTNER, i, row); else append_(TABS.PARTNER, [row]);
    return getData();
  });
}
function deletePartner(name) {
  return withLock_(() => {
    const sh = tab_(book_(), TABS.PARTNER);
    const vals = rows_(TABS.PARTNER);
    for (let i = vals.length - 1; i >= 0; i--) if (str_(vals[i][0]) === name) sh.deleteRow(i + 2);
    return getData();
  });
}
function upsertMaps_(list, at) {
  const vals = rows_(TABS.MAP);
  const idx = new Map(vals.map((r, i) => [str_(r[0]), i]));
  const add = [];
  (list || []).forEach((m) => {
    const row = [m.id, m.key, m.sku, Math.max(1, num_(m.mult) || 1), at];
    if (idx.has(m.id) && idx.get(m.id) >= 0) putRow_(TABS.MAP, idx.get(m.id), row);
    else if (!idx.has(m.id)) { add.push(row); idx.set(m.id, -1); }
  });
  append_(TABS.MAP, add);
}
/** 매칭 규칙 저장 (같은 ID면 고쳐 쓰기) */
function saveRules(list) {
  return withLock_(() => {
    const vals = rows_(TABS.RULE);
    const idx = new Map(vals.map((r, i) => [str_(r[0]), i]));
    const add = [], at = now_();
    (list || []).forEach((x) => {
      if (!x.id || !x.sku) return;
      const row = [x.id, x.name || '', x.opt || '', String(x.sku).toUpperCase(), Math.max(1, num_(x.mult) || 1), x.memo || '', at];
      if (idx.has(x.id) && idx.get(x.id) >= 0) putRow_(TABS.RULE, idx.get(x.id), row);
      else if (!idx.has(x.id)) { add.push(row); idx.set(x.id, -1); }
    });
    append_(TABS.RULE, add);
    return getData();
  });
}
function deleteRule(id) {
  return withLock_(() => {
    const sh = tab_(book_(), TABS.RULE);
    const vals = rows_(TABS.RULE);
    for (let i = vals.length - 1; i >= 0; i--) if (str_(vals[i][0]) === id) sh.deleteRow(i + 2);
    return getData();
  });
}
/** 홈 화면 메모 (모두가 같이 보는 메모 한 장) */
/** 설정(회사 정보·도장 등) 저장: 항목별로 고쳐 쓰기 */
function saveConf(obj) {
  return withLock_(() => {
    const vals = rows_(TABS.CONF);
    const idx = new Map(vals.map((r, i) => [str_(r[0]), i]));
    const add = [], at = now_();
    Object.keys(obj || {}).forEach((k) => {
      const v = String(obj[k] === null || obj[k] === undefined ? '' : obj[k]);
      if (v.length > 49000) throw new Error('도장 이미지가 너무 큽니다. 200KB 이하의 작은 이미지로 올려 주세요.');
      if (idx.has(k)) putRow_(TABS.CONF, idx.get(k), [k, v, at]); else add.push([k, v, at]);
    });
    append_(TABS.CONF, add);
    return getData();
  });
}
/** 상품 사진 저장 (상품 하나에 한 장, 화면에서 작게 줄여서 보냄) */
/** 상품 정보 수정 (재고 보기 카드에서). 코드를 바꾸면 기록·연결표·매칭규칙의 코드도 같이 바꿉니다. 숨겨 둔 원가 칸은 그대로 둡니다. */
function editSku(oldCode, s) {
  return withLock_(() => {
    oldCode = String(oldCode || '').trim().toUpperCase();
    const code = String(s.code || '').trim().toUpperCase(), name = String(s.name || '').trim();
    if (!/^[A-Z0-9][A-Z0-9_\-.]{0,39}$/.test(code)) throw new Error('코드는 영문 대문자·숫자·하이픈(-)만 쓸 수 있습니다.');
    if (!name) throw new Error('상품명을 적어 주세요.');
    const vals = rows_(TABS.SKU);
    const i = vals.findIndex((r) => str_(r[0]).toUpperCase() === oldCode);
    if (i < 0) throw new Error('수정할 상품을 찾지 못했습니다. 새로고침 후 다시 시도해 주세요.');
    if (code !== oldCode && vals.some((r) => str_(r[0]).toUpperCase() === code)) throw new Error(`${code} 코드는 이미 다른 상품이 쓰고 있습니다.`);
    const o = vals[i];
    // 사진은 같은 상품 묶음('f' + 묶음 이름)으로 저장됨. 예전 사진은 'p' + (부위|상품명)
    const fk = (nm) => 'f' + HASH_(famName_(nm));
    const oldKey = fk(str_(o[1])), newKey = fk(name), oldLegacy = 'p' + HASH_(`${str_(o[2]) || '기타'}|${str_(o[1])}`);
    putRow_(TABS.SKU, i, [code, name, String(s.part || '').trim(), String(s.option || '').trim(), Math.max(0, num_(s.safety)), Math.max(1, num_(s.lead) || 50),
      s.active === false ? 'N' : 'Y', now_(), o[8], s.retail === undefined ? o[9] : num_(s.retail) || '', s.wholesale === undefined ? o[10] : num_(s.wholesale) || '', o[11]]);
    if (code !== oldCode) {
      // 기록(SKU 5번째 칸) · 연결표(3번째) · 매칭규칙(4번째)의 코드 바꾸기
      [[TABS.MOVE, 5], [TABS.MAP, 3], [TABS.RULE, 4]].forEach(([t, col]) => {
        const sh = tab_(book_(), t), n = sh.getLastRow() - 1;
        if (n < 1) return;
        const rng = sh.getRange(2, col, n, 1), v = rng.getValues();
        let changed = false;
        v.forEach((r) => { if (String(r[0]).trim().toUpperCase() === oldCode) { r[0] = code; changed = true; } });
        if (changed) rng.setValues(v);
      });
    }
    // 상품명이 다른 묶음으로 바뀌면, 새 묶음에 사진이 없을 때 지금 사진을 복사해 붙임
    if (oldKey !== newKey) {
      LITE_ = false;
      const ph = rows_(TABS.PHOTO);
      if (!ph.some((r) => str_(r[0]) === newKey)) {
        const src = ph.find((r) => str_(r[0]) === oldKey) || ph.find((r) => str_(r[0]) === oldLegacy);
        if (src) append_(TABS.PHOTO, [[newKey, name, src[2], now_()]]);
      }
    }
    return getData();
  });
}
function savePhoto(key, name, data) {
  return withLock_(() => {
    if (String(data || '').length > 49000) throw new Error('사진이 너무 큽니다. 다른 사진으로 다시 시도해 주세요.');
    // 속도: 다른 사진들(큰 글자 덩어리)은 읽지 않고 '상품키' 칸만 읽어서 자리를 찾음. 전체 데이터도 다시 보내지 않음
    const i = photoKeys_().indexOf(key);
    const row = [key, name || '', data || '', now_()];
    if (i >= 0) putRow_(TABS.PHOTO, i, row); else append_(TABS.PHOTO, [row]);
    return { ok: true, key: key };
  });
}
function deletePhoto(key) {
  return withLock_(() => {
    const sh = tab_(book_(), TABS.PHOTO);
    const del = new Set([].concat(key));
    const keys = photoKeys_();
    for (let i = keys.length - 1; i >= 0; i--) if (del.has(keys[i])) sh.deleteRow(i + 2);
    return { ok: true, key: key };
  });
}
function photoKeys_() {
  const sh = tab_(book_(), TABS.PHOTO), n = sh.getLastRow() - 1;
  return n < 1 ? [] : sh.getRange(2, 1, n, 1).getValues().map((r) => str_(r[0]));
}
/** 오늘 달러 환율 (구글 파이낸스): 설정 탭 빈 칸에 잠깐 수식을 넣어 읽고 지움 */
function getFx() {
  const sh = tab_(book_(), TABS.CONF);
  const cell = sh.getRange('F1');
  cell.setFormula('=GOOGLEFINANCE("CURRENCY:USDKRW")');
  SpreadsheetApp.flush();
  let v = Number(cell.getValue());
  for (let k = 0; k < 3 && !(v > 0); k++) { Utilities.sleep(800); SpreadsheetApp.flush(); v = Number(cell.getValue()); }
  cell.clearContent();
  if (!(v > 0)) throw new Error('오늘 환율을 가져오지 못했습니다. 환율 칸에 직접 입력해 주세요.');
  return Math.round(v * 100) / 100;
}
/** 설정 항목 지우기 (예: 공급자 회사 삭제) */
function deleteConf(key) {
  return withLock_(() => {
    const sh = tab_(book_(), TABS.CONF);
    const vals = rows_(TABS.CONF);
    for (let i = vals.length - 1; i >= 0; i--) if (str_(vals[i][0]) === key) sh.deleteRow(i + 2);
    return getData();
  });
}
/** 견적서 저장 (같은 번호면 고쳐 쓰기) */
function saveQuote(q) {
  return withLock_(() => {
    const vals = rows_(TABS.QUOTE);
    const i = vals.findIndex((r) => str_(r[0]) === q.no);
    const row = [q.no, q.date, q.to, num_(q.total), num_(q.supply), num_(q.vat), JSON.stringify(q.body || {}), me_(), now_()];
    if (i >= 0) putRow_(TABS.QUOTE, i, row); else append_(TABS.QUOTE, [row]);
    return getData();
  });
}
function deleteQuote(no) {
  return withLock_(() => {
    const sh = tab_(book_(), TABS.QUOTE);
    const vals = rows_(TABS.QUOTE);
    for (let i = vals.length - 1; i >= 0; i--) if (str_(vals[i][0]) === no) sh.deleteRow(i + 2);
    return getData();
  });
}
/** 견적서 PDF를 구글 드라이브 '올투게더나우 견적서' 폴더에 저장하고 주소를 돌려줌 */
function savePdf(base64, filename) {
  const name = '올투게더나우 견적서';
  const it = DriveApp.getFoldersByName(name);
  const folder = it.hasNext() ? it.next() : DriveApp.createFolder(name);
  const blob = Utilities.newBlob(Utilities.base64Decode(base64), 'application/pdf', filename);
  return folder.createFile(blob).getUrl();
}
/** 네이버 원가 관리 시트에서 시작일~종료일이 걸친 달 탭(예: '202610월', '202611월')을 읽어 한 표로 합쳐 돌려줌 (날짜 거르기는 화면에서) */
function readNaverSheet(url, from, to) {
  const id = (String(url || '').match(/[-\w]{25,}/) || [])[0];
  if (!id) throw new Error('구글 시트 주소를 확인해 주세요.');
  let ss;
  try { ss = SpreadsheetApp.openById(id); } catch (e) { throw new Error('시트를 열 수 없습니다. 주소와 공유 권한을 확인해 주세요.'); }
  to = to || from;
  const months = [];
  let y = Number(String(from).slice(0, 4)), m = Number(String(from).slice(5, 7));
  const ey = Number(String(to).slice(0, 4)), em = Number(String(to).slice(5, 7));
  for (let k = 0; k < 24 && (y < ey || (y === ey && m <= em)); k++) { months.push(String(y) + String(m).padStart(2, '0')); m++; if (m > 12) { m = 1; y++; } }
  const sheets = ss.getSheets(), tabs = [], missing = [];
  let base = null; const out = [];
  months.forEach((ym) => {
    // 탭 이름 모양이 달라도 찾음: 202611월 · 2026/11월 · 2026-11 · 2026.11 · 2026년 11월
    const sh = sheets.find((x) => { const m = x.getName().match(/^\s*(20\d{2})\s*[\/.\-_년]?\s*(\d{1,2})(?!\d)/); return m && m[1] + m[2].padStart(2, '0') === ym; });
    if (!sh) { missing.push(ym); return; }
    tabs.push(sh.getName());
    const v = sh.getDataRange().getDisplayValues();
    if (!v.length) return;
    if (!base) { base = v[0].map((h) => String(h).trim()); out.push(base); }
    // 달마다 열 순서가 달라도 제목 이름으로 맞춰 붙임
    const idx = base.map((h) => v[0].map((x) => String(x).trim()).indexOf(h));
    for (let r = 1; r < v.length; r++) out.push(idx.map((c) => (c >= 0 ? v[r][c] : '')));
  });
  if (!tabs.length) throw new Error(`${months.map((x) => x.slice(0, 4) + '/' + x.slice(4) + '월').join(', ')} 탭을 찾지 못했습니다. 시트에 그 달 탭이 있는지 확인해 주세요.`);
  return { title: ss.getName(), tab: tabs.join(' + '), missing: missing, values: out };
}

/* ===================== 네이버 자동 출고 =====================
 * 매일 정해진 시각에 autoNaverTrigger 가 실행됩니다 (켜기: 화면의 '매일 자동 출고 켜기').
 * 화면(Index.html)의 주문서 출고와 같은 규칙으로 처리합니다:
 *   주문일시로 날짜 거르기 · 취소/반품/교환 제외 · 이미 뺀 주문(주문열쇠) 제외 · 연결표 → SKU 코드 → 매칭 규칙 순으로 SKU 찾기
 * 연결 못 한 주문은 빼지 않고 '확인 필요'로 남깁니다 (화면에서 한 번 연결하면 다음부터 자동).
 */
/** 옵션 글자로 실제 개수 짐작: 한쪽·한팔·1p = 1개 · 1쌍·양쪽·양팔 = 2개 · 2쌍 = 4개 · 3p/3개 = 3개 (연결표에 저장된 배수가 있으면 그게 우선) */
function packMult(name, opt) {
  const f = (t) => {
    t = String(t || ''); let m = t.match(/(\d+)\s*쌍/);
    if (m && Number(m[1])) return Number(m[1]) * 2;
    if (/양쪽|양팔|양발|양손|한\s*쌍/.test(t)) return 2;
    if (/한쪽|한팔|한발|한손|외발/.test(t)) return 1;
    m = t.match(/(\d+)\s*(?:p|pcs|ea|개입|개)(?![a-z])/i);
    if (m && Number(m[1]) >= 1 && Number(m[1]) <= 10) return Number(m[1]);
    return 0;
  };
  return f(opt) || (String(name || '').length <= 20 ? f(name) : 0) || 1;
}
// 같은 상품 묶음 이름: 끝에 붙은 사이즈·색상·수량 글자를 뗌 (예: '바른요 허리 XL' → '바른요 허리', '엘보 보호대 SET' → '엘보 보호대')
const FAM_TAIL_ = /^(?:(?:x{0,3}s|m|x{0,3}l|[2-5]xl|free|f|프리|소|중|대|특대|소형|중형|대형|\d+\s*p|\d+\s*개입?|\d+\s*쌍|set|세트|한쪽|양쪽|한팔|양팔|좌|우|왼쪽|오른쪽|블랙|검정|화이트|흰색|그레이|회색|네이비|베이지|블루|레드|핑크|스킨|그린|브라운|퍼플|옐로우)(?:\(.*\))?|\(.*\)|\[.*\])$/i;
function famName_(name) {
  const t = String(name || '').replace(/\s+/g, ' ').trim().split(' ');
  while (t.length > 1 && FAM_TAIL_.test(t[t.length - 1])) t.pop();
  let s = t.join(' ');
  const m = s.match(/^(.*[가-힣])(?:x{0,3}s|m|x{0,3}l|[2-5]xl)$/i);   // 붙여 쓴 사이즈: '허리XL' → '허리'
  if (m && m[1].trim()) s = m[1];
  return s.trim().toLowerCase();
}
const HASH_ = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(36); };
const NORM_ = (s) => String(s === null || s === undefined ? '' : s).replace(/\s+/g, ' ').trim();
function dayOf_(v) {
  const t = NORM_(v); let m = t.match(/(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})/);
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
  m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})/); if (m) return `${m[3].length === 2 ? '20' + m[3] : m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}`;
  return '';
}
function confMap_() { const c = {}; rows_(TABS.CONF).forEach((r) => { if (str_(r[0])) c[str_(r[0])] = String(r[1] === null || r[1] === undefined ? '' : r[1]); }); return c; }
function dayShift_(d, n) { const x = new Date(d + 'T12:00:00'); x.setDate(x.getDate() + n); return Utilities.formatDate(x, Session.getScriptTimeZone(), 'yyyy-MM-dd').slice(0, 10); }
function autoNaverShip_(opt) {
  opt = opt || {};
  const conf = confMap_();
  if (!conf.naverSheet) throw new Error('네이버 원가 관리 시트 주소가 저장되어 있지 않습니다. 엑셀 입출고 화면에서 한 번 [시트에서 가져오기]를 해 주세요.');
  const yest = opt.to || dayShift_(Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd').slice(0, 10), -1);
  let from = opt.from || (conf.naverAutoLast ? dayShift_(conf.naverAutoLast, 1) : yest);
  const floor = dayShift_(yest, -13); if (from < floor) from = floor;
  if (from > yest) return { from, to: yest, units: 0, moves: 0, pending: [], note: '처리할 새 날짜가 없습니다' };
  const sheet = readNaverSheet(conf.naverSheet, from, yest), v = sheet.values;
  const head = (v[0] || []).map(NORM_);
  const col = (names) => { for (const n of names) { const i = head.indexOf(n); if (i >= 0) return i; } for (const n of names) { const i = head.findIndex((h) => h.indexOf(n) >= 0); if (i >= 0) return i; } return -1; };
  const cDate = col(['발송처리일', '발송일', '발송일시', '출고일', '배송시작일', '주문일시', '주문일', '결제일']), cStatus = col(['상품주문상태', '주문상태', '배송상태']), cClaim = col(['클레임상태']);
  const cPno = col(['상품번호']), cName = col(['상품명', '노출상품명', '등록상품명', '제품명', '품명']), cOpt = col(['옵션정보', '등록옵션명', '노출옵션명', '옵션명', '옵션']), cQty = col(['수량', '구매수(수량)', '주문수량', '구매수량']);
  const cNo = col(['상품주문번호']), cAttr = col(['배송속성', '배송구분', '배송방법']);
  if (cDate < 0 || cName < 0 || cQty < 0) throw new Error('시트에서 주문일시·상품명·수량 열을 찾지 못했습니다.');
  const done = new Set(rows_(TABS.ORDER).map((r) => str_(r[0])));
  const skus = new Set(rows_(TABS.SKU).map((r) => str_(r[0]).toUpperCase()).filter(Boolean));
  const maps = new Map(rows_(TABS.MAP).filter((r) => str_(r[0])).map((r) => [str_(r[0]), { sku: str_(r[2]), mult: num_(r[3]) || 1 }]));
  const rules = rows_(TABS.RULE).filter((r) => str_(r[0]) && str_(r[3])).map((r) => ({ name: str_(r[1]).toLowerCase(), opt: str_(r[2]).toLowerCase(), sku: str_(r[3]).toUpperCase(), mult: num_(r[4]) || 1 }));
  const words = (s) => s.split(' ').filter(Boolean);
  const seen = new Map(), agg = new Map(), orderNos = [], pending = [];
  let rowsUsed = 0;
  for (let i = 1; i < v.length; i++) {
    const r = v[i];
    if (!r.some((c) => NORM_(c))) continue;
    // 화면과 같은 주문열쇠: 주문일시·상품번호·상품명·옵션·수량 + 같은 줄 순번
    let key;
    if (cNo >= 0) key = NORM_(r[cNo]);
    else { const base = [cDate, cPno, cName, cOpt, cQty].map((c) => (c >= 0 ? NORM_(r[c]) : '')).join('|'); const k = (seen.get(base) || 0) + 1; seen.set(base, k); key = 'S' + HASH_(base) + '-' + k; }
    const d = dayOf_(r[cDate]); if (!d || d < from || d > yest) continue;
    if (/취소|반품|교환|환불/.test(`${cStatus >= 0 ? r[cStatus] : ''} ${cClaim >= 0 ? r[cClaim] : ''}`)) continue;
    if (key && done.has(key)) continue;
    const name = NORM_(r[cName]), op = cOpt >= 0 ? NORM_(r[cOpt]) : '', qty = num_(r[cQty]);
    if (!name || !qty) continue;
    const mkey = op ? `${name} ¦ ${op}` : name;
    let hit = maps.get(HASH_(mkey));
    if (!hit) { const t = (`${name} ${op}`.toUpperCase().match(/[A-Z0-9][A-Z0-9_\-.]*/g) || []).find((x) => skus.has(x)); if (t) hit = { sku: t, mult: packMult(name, op) }; }
    if (!hit) { const n = name.toLowerCase(), o = op.toLowerCase(); const rule = rules.find((x) => skus.has(x.sku) && (x.name || x.opt) && words(x.name).every((w) => n.indexOf(w) >= 0) && words(x.opt).every((w) => o.indexOf(w) >= 0)); if (rule) hit = { sku: rule.sku, mult: rule.mult > 1 ? rule.mult : packMult(name, op) }; }
    if (!hit || !hit.sku) { pending.push({ day: d, name, opt: op, qty }); continue; }
    rowsUsed++;
    if (key) orderNos.push({ no: key, day: d });
    if (hit.sku === '__skip') continue;
    const loc = cAttr >= 0 && /N\s*배송|풀필먼트|NFA|파스토|FASSTO/i.test(NORM_(r[cAttr])) ? 'fassto' : 'hq';
    const ak = hit.sku + '|' + loc + '|' + d;
    agg.set(ak, (agg.get(ak) || 0) + qty * hit.mult);
  }
  const list = [...agg].map(([k, q]) => { const [sku, loc, d] = k.split('|'); return { sku, loc, qty: -q, type: loc === 'fassto' ? 'nsale' : 'ship', date: d, memo: `네이버 원가 관리 · ${d.slice(5)} 주문분 (자동)` }; }).sort((a, b) => a.date.localeCompare(b.date));
  const units = list.reduce((a, m) => a - m.qty, 0);
  withLock_(() => {
    const at = now_();
    if (list.length) append_(TABS.MOVE, moveRows_(list, `네이버 자동 출고 (${from === yest ? yest : from + '~' + yest})`));
    if (orderNos.length) append_(TABS.ORDER, orderNos.map((n) => [n.no, n.day, '네이버 자동 출고', at]));
  });
  const log = { at: now_(), from, to: yest, units, moves: list.length, orders: rowsUsed, pending: pending.slice(0, 200), pendingCount: pending.length, tab: sheet.tab };
  saveConf({ naverAutoLast: yest, naverAutoLog: JSON.stringify(log) });
  return log;
}
/** 시간 트리거가 부르는 함수 (실패해도 기록만 남김) */
function autoNaverTrigger() {
  try { autoNaverShip_({}); }
  catch (e) { try { saveConf({ naverAutoLog: JSON.stringify({ at: now_(), error: String(e && e.message || e) }) }); } catch (e2) { /* 무시 */ } }
}
/** 화면: 지금 바로 자동 출고 실행 */
function runAutoNaver(from, to) { const res = autoNaverShip_({ from: from || '', to: to || '' }); const d = getData(); d.autoResult = res; return d; }
/** 화면: 매일 자동 출고 켜기/끄기 */
function setAutoNaver(on, hour) {
  ScriptApp.getProjectTriggers().filter((t) => t.getHandlerFunction() === 'autoNaverTrigger').forEach((t) => ScriptApp.deleteTrigger(t));
  if (on) ScriptApp.newTrigger('autoNaverTrigger').timeBased().everyDays(1).atHour(Math.max(0, Math.min(23, Number(hour) || 9))).create();
  saveConf({ naverAuto: on ? 'on' : 'off', naverAutoHour: String(Number(hour) || 9) });
  return getData();
}

function saveMemo(text) {
  return withLock_(() => { putRow_(TABS.MEMO, 0, [String(text || '').slice(0, 5000), now_(), me_()]); return getData(); });
}
/** 연결표 여러 개 저장 (인보이스 원가 계산 등에서 고른 연결 기억) */
function saveMaps(list) {
  return withLock_(() => { upsertMaps_(list, now_()); return getData(); });
}
function deleteMap(id) {
  return withLock_(() => {
    const sh = tab_(book_(), TABS.MAP);
    const vals = rows_(TABS.MAP);
    for (let i = vals.length - 1; i >= 0; i--) if (str_(vals[i][0]) === id) sh.deleteRow(i + 2);
    return getData();
  });
}
/** 주문서 차감: 기록 + 새 연결 + 중복 방지용 서명을 한 번에 저장 */
function applyUpload(list, newMaps, sig, file, label, orderNos, orderDay) {
  return withLock_(() => {
    const at = now_();
    if (orderNos && orderNos.length) append_(TABS.ORDER, orderNos.map((n) => (typeof n === 'object' ? [n.no, n.day || orderDay || '', file, at] : [n, orderDay || '', file, at])));
    append_(TABS.MOVE, moveRows_(list, label || '주문서 차감'));
    append_(TABS.UPLOAD, [[sig, file, list.filter((m) => m.loc !== 'pending').reduce((a, m) => a + Math.abs(Number(m.qty)), 0), at, me_()]]);
    upsertMaps_(newMaps, at);
    return getData();
  });
}
/** 표를 재고DB 시트의 탭으로 저장 (엑셀 다운로드는 시트에서 파일 → 다운로드) */
function exportSheet(name, aoa) {
  const ss = book_();
  let sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name); else sh.clear();
  const w = Math.max(...aoa.map((r) => r.length));
  const rows = aoa.map((r) => { const x = r.slice(); while (x.length < w) x.push(''); return x; });
  sh.getRange(1, 1, rows.length, w).setValues(rows);
  sh.getRange(1, 1, 1, w).setFontWeight('bold');
  sh.getRange(rows.length + 2, 1).setValue('작성: ' + now_());
  sh.setFrozenRows(1);
  return ss.getUrl() + '#gid=' + sh.getSheetId();
}
