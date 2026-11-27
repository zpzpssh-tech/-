/**
 * 올투게더나우 재고관리 — 자동 최신 버전 로더
 *
 * 이 파일 하나만 Apps Script에 붙여 두면 끝입니다. (Index.html 파일은 지워도 됩니다)
 * 프로그램을 열 때마다 GitHub에 올라간 최신 프로그램(Code.gs · Index.html)을 받아서 실행하므로
 * 앞으로 코드를 붙여넣거나 업데이트 버튼을 누를 필요가 없습니다. (새 버전은 10분 안에 자동 반영)
 * 받아 온 프로그램은 잠시 기억해 두고(캐시), 구글 드라이브에도 백업해 두어 GitHub가 잠깐 안 돼도 열립니다.
 */
var L_SRC = 'https://raw.githubusercontent.com/zpzpssh-tech/-/refs/heads/claude/fervent-wozniak-wow6ha/inventory-gas/';
var L_FILES = ['Code.gs', 'Index.html'];
var L_CHUNK = 25000;   // 캐시 한 칸에 넣는 글자 수 (구글 캐시 한 칸 = 최대 100KB)
var L_FRESH = 600;     // 10분마다 새 버전 확인
var L_KEEP = 21600;    // 받아 온 코드는 6시간 기억

/* ---------- 구글이 직접 부르는 입구 ---------- */
function doGet(e) { return L_run('doGet', [e]); }
function rpc(fn, args) { return L_run('rpc', [fn, args]); }               // 화면(Index.html)이 부르는 모든 기능
function setup() { return L_run('setup', []); }                            // 처음 한 번 (편집기에서 실행)
function autoNaverTrigger(e) { return L_run('autoNaverTrigger', [e]); }    // 네이버 자동 출고 예약
function autoUpdateTrigger() {                                              // 예전 자동 업데이트 예약 → 이제 필요 없으니 지움
  ScriptApp.getProjectTriggers().forEach(function (t) { if (t.getHandlerFunction() === 'autoUpdateTrigger') ScriptApp.deleteTrigger(t); });
}
/** 지금 바로 최신 버전 받기 (편집기에서 실행하면 10분 기다리지 않고 즉시 반영) */
function refreshNow() { CacheService.getScriptCache().remove('L:fresh'); var s = L_sources(); return '최신 버전: ' + ((s['Code.gs'].match(/const APP_VERSION = '([^']+)'/) || [])[1] || '?'); }

/* ---------- 로더 내부 ---------- */
var L_GET = null;
function L_html() { return L_sources()['Index.html']; }   // 프로그램(Code.gs)의 doGet이 화면을 만들 때 씀
function L_run(name, args) {
  if (!L_GET) L_GET = (0, eval)(L_sources()['Code.gs'] + '\n;(function (n) { return eval(n); })');
  return L_GET(name).apply(null, args);
}
function L_sources() {
  var c = CacheService.getScriptCache(), out = L_fromCache(c);
  if (out && c.get('L:fresh')) return out;
  var fresh = L_fetch();
  if (fresh) {
    var ver = (fresh['Code.gs'].match(/const APP_VERSION = '([^']+)'/) || [])[1] || '';
    L_toCache(c, fresh); c.put('L:fresh', ver, L_FRESH);
    if (ver !== PropertiesService.getScriptProperties().getProperty('L_VER')) L_backup(fresh, ver);
    return fresh;
  }
  if (out) { c.put('L:fresh', 'old', 120); return out; }          // GitHub가 잠깐 안 되면 기억해 둔 것으로
  var b = L_restore();                                             // 캐시도 없으면 드라이브 백업으로
  if (b) { L_toCache(c, b); c.put('L:fresh', 'backup', 120); return b; }
  throw new Error('최신 프로그램을 받지 못했습니다. 인터넷 연결을 확인하고 잠시 후 다시 열어 주세요.');
}
function L_fetch() {
  try {
    var t = Date.now();
    var rs = UrlFetchApp.fetchAll(L_FILES.map(function (f) { return { url: L_SRC + f + '?t=' + t, muteHttpExceptions: true }; }));
    var out = {};
    for (var i = 0; i < L_FILES.length; i++) { if (rs[i].getResponseCode() !== 200) return null; out[L_FILES[i]] = rs[i].getContentText('UTF-8'); }
    if (out['Code.gs'].indexOf('function rpc(') < 0 || out['Index.html'].indexOf('</html>') < 0) return null;   // 덜 받은 파일은 안 씀
    return out;
  } catch (e) { return null; }
}
function L_toCache(c, src) {
  var put = {};
  L_FILES.forEach(function (f) {
    var s = src[f], n = Math.ceil(s.length / L_CHUNK);
    for (var i = 0; i < n; i++) put['L:' + f + ':' + i] = s.slice(i * L_CHUNK, (i + 1) * L_CHUNK);
    put['L:' + f + ':n'] = String(n);
  });
  c.putAll(put, L_KEEP);
}
function L_fromCache(c) {
  var heads = c.getAll(L_FILES.map(function (f) { return 'L:' + f + ':n'; })), keys = [];
  for (var k = 0; k < L_FILES.length; k++) { var n = Number(heads['L:' + L_FILES[k] + ':n'] || 0); if (!n) return null; for (var i = 0; i < n; i++) keys.push('L:' + L_FILES[k] + ':' + i); }
  var got = c.getAll(keys), out = {};
  for (var j = 0; j < L_FILES.length; j++) {
    var f = L_FILES[j], m = Number(heads['L:' + f + ':n']), parts = [];
    for (var p = 0; p < m; p++) { var v = got['L:' + f + ':' + p]; if (v == null) return null; parts.push(v); }
    out[f] = parts.join('');
  }
  return out;
}
function L_backup(src, ver) {
  try {
    var P = PropertiesService.getScriptProperties(), id = P.getProperty('L_BACKUP'), body = JSON.stringify(src), file = null;
    if (id) { try { file = DriveApp.getFileById(id); file.setContent(body); } catch (e) { file = null; } }
    if (!file) { file = DriveApp.createFile('올투게더나우_재고관리_프로그램백업.json', body, 'application/json'); P.setProperty('L_BACKUP', file.getId()); }
    P.setProperty('L_VER', ver);
  } catch (e) { /* 백업 실패는 무시 */ }
}
function L_restore() {
  try { var id = PropertiesService.getScriptProperties().getProperty('L_BACKUP'); return id ? JSON.parse(DriveApp.getFileById(id).getBlob().getDataAsString('UTF-8')) : null; } catch (e) { return null; }
}
