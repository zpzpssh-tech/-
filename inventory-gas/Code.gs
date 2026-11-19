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
  SKU: { name: 'SKU', head: ['코드', '상품명', '부위', '옵션', '안전재고', '리드타임(일)', '사용', '수정일', '기준원가', '소매가', '도매가'] },
  PARTNER: { name: '거래처', head: ['이름', '기본 단가', '메모', '수정일'] },
  MOVE: { name: '기록', head: ['ID', '날짜', '종류', '위치', 'SKU', '수량', '메모', '묶음ID', '묶음이름', '기록시각', '기록자', '거래처', '단가', '외화단가(USD)', '환율'] },
  MAP: { name: '연결표', head: ['ID', '주문서 상품명·옵션', 'SKU', '배수', '수정일'] },
  RULE: { name: '매칭규칙', head: ['ID', '상품명에 포함', '옵션에 포함', 'SKU', '배수', '메모', '수정일'] },
  MEMO: { name: '메모', head: ['내용', '수정시각', '수정자'] },
  PHOTO: { name: '상품사진', head: ['상품키', '상품명', '사진', '수정시각'] },
  CONF: { name: '설정', head: ['항목', '값', '수정시각'] },
  QUOTE: { name: '견적서', head: ['견적번호', '견적일', '받는 곳', '합계(부가세포함)', '공급가액', '부가세', '내용(JSON)', '작성자', '작성시각'] },
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

function book_() {
  const id = PropertiesService.getScriptProperties().getProperty('SHEET_ID');
  const ss = id ? SpreadsheetApp.openById(id) : SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) throw new Error('재고DB 시트를 찾지 못했습니다. Apps Script 편집기에서 setup 함수를 한 번 실행해 주세요.');
  return ss;
}
function tab_(ss, t) {
  let sh = ss.getSheetByName(t.name);
  if (!sh) {
    sh = ss.insertSheet(t.name);
    sh.getRange(1, 1, 1, t.head.length).setValues([t.head]).setFontWeight('bold');
    sh.setFrozenRows(1);
    // 날짜·코드가 자동으로 숫자/날짜로 바뀌지 않게 글자 형식으로 고정
    sh.getRange(1, 1, sh.getMaxRows(), t.head.length).setNumberFormat('@');
  } else {
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
  const n = sh.getLastRow() - 1;
  if (n < 1) return [];
  return sh.getRange(2, 1, n, t.head.length).getValues();
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
  try { return fn(); } finally { lock.releaseLock(); }
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
    cost: num_(r[8]), retail: num_(r[9]), wholesale: num_(r[10]),
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
  const photos = {};
  rows_(TABS.PHOTO).forEach((r) => { if (str_(r[0]) && r[2]) photos[str_(r[0])] = String(r[2]); });
  const conf = {};
  rows_(TABS.CONF).forEach((r) => { if (str_(r[0])) conf[str_(r[0])] = String(r[1] === null || r[1] === undefined ? '' : r[1]); });
  const quotes = rows_(TABS.QUOTE).filter((r) => str_(r[0])).map((r) => ({ no: str_(r[0]), date: str_(r[1]), to: str_(r[2]), total: num_(r[3]), body: String(r[6] || ''), by: str_(r[7]), at: str_(r[8]) }));
  return { skus, partners, moves, maps, uploads, rules, memo, conf, quotes, photos, me: me_(), sheetUrl: book_().getUrl(), appUrl: appUrl_() };
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
        s.active === false ? 'N' : 'Y', now_(), num_(s.cost) || '', num_(s.retail) || '', num_(s.wholesale) || ''];
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
function savePhoto(key, name, data) {
  return withLock_(() => {
    if (String(data || '').length > 49000) throw new Error('사진이 너무 큽니다. 다른 사진으로 다시 시도해 주세요.');
    const vals = rows_(TABS.PHOTO);
    const i = vals.findIndex((r) => str_(r[0]) === key);
    const row = [key, name || '', data || '', now_()];
    if (i >= 0) putRow_(TABS.PHOTO, i, row); else append_(TABS.PHOTO, [row]);
    return getData();
  });
}
function deletePhoto(key) {
  return withLock_(() => {
    const sh = tab_(book_(), TABS.PHOTO);
    const vals = rows_(TABS.PHOTO);
    for (let i = vals.length - 1; i >= 0; i--) if (str_(vals[i][0]) === key) sh.deleteRow(i + 2);
    return getData();
  });
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
function applyUpload(list, newMaps, sig, file, label) {
  return withLock_(() => {
    const at = now_();
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
