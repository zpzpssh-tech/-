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

const TABS = {
  SKU: { name: 'SKU', head: ['코드', '상품명', '부위', '옵션', '안전재고', '리드타임(일)', '사용', '수정일', '기준원가', '소매가', '도매가'] },
  PARTNER: { name: '거래처', head: ['이름', '기본 단가', '메모', '수정일'] },
  MOVE: { name: '기록', head: ['ID', '날짜', '종류', '위치', 'SKU', '수량', '메모', '묶음ID', '묶음이름', '기록시각', '기록자', '거래처', '단가'] },
  MAP: { name: '연결표', head: ['ID', '주문서 상품명·옵션', 'SKU', '배수', '수정일'] },
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
const rev = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [v, k]));
const MOVE_CODE = rev(MOVE_LABEL), LOC_CODE = rev(LOC_LABEL);

/* ---------- 웹페이지 열기 ---------- */
function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('올투게더나우 재고관리')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/* ---------- 처음 한 번: 시트 탭 만들기 ---------- */
function setup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  PropertiesService.getScriptProperties().setProperty('SHEET_ID', ss.getId());
  Object.values(TABS).forEach((t) => tab_(ss, t));
  if (!rows_(TABS.PARTNER).length) append_(TABS.PARTNER, DEFAULT_PARTNERS.map((p) => [p[0], p[1], p[2], now_()]));
  return '준비 완료: ' + ss.getName();
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
    at: str_(r[9]), by: str_(r[10]), partner: str_(r[11]), price: num_(r[12]),
  }));
  const maps = rows_(TABS.MAP).filter((r) => str_(r[0])).map((r) => ({ id: str_(r[0]), key: str_(r[1]), sku: str_(r[2]), mult: num_(r[3]) || 1 }));
  const uploads = rows_(TABS.UPLOAD).filter((r) => str_(r[0])).map((r) => ({ sig: str_(r[0]), file: str_(r[1]), units: num_(r[2]), at: str_(r[3]) }));
  return { skus, partners, moves, maps, uploads, me: me_(), sheetUrl: book_().getUrl(), appUrl: appUrl_() };
}

/* ---------- 쓰기 ---------- */
function moveRows_(list, batchLabel) {
  const batch = Utilities.getUuid().slice(0, 13), at = now_(), by = me_();
  return list.map((m) => [
    Utilities.getUuid().slice(0, 13), m.date, MOVE_LABEL[m.type] || m.type, LOC_LABEL[m.loc] || m.loc,
    m.sku, Number(m.qty), m.memo || '', batch, batchLabel || '', at, by, m.partner || '', Number(m.price) || '',
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
function deleteMap(id) {
  return withLock_(() => {
    const sh = tab_(book_(), TABS.MAP);
    const vals = rows_(TABS.MAP);
    for (let i = vals.length - 1; i >= 0; i--) if (str_(vals[i][0]) === id) sh.deleteRow(i + 2);
    return getData();
  });
}
/** 주문서 차감: 기록 + 새 연결 + 중복 방지용 서명을 한 번에 저장 */
function applyUpload(list, newMaps, sig, file) {
  return withLock_(() => {
    const at = now_();
    append_(TABS.MOVE, moveRows_(list, '주문서 차감'));
    append_(TABS.UPLOAD, [[sig, file, list.reduce((a, m) => a - Number(m.qty), 0), at, me_()]]);
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
