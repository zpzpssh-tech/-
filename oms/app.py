"""
올투게더나우 통합 주문·재고 관리 (OMS)
=====================================
실행:  python3 oms/app.py      → 브라우저가 자동으로 열립니다 (http://127.0.0.1:8765)
끄기:  터미널에서 Ctrl + C

이 파일은 '가게 카운터' 역할입니다. 화면(브라우저)이 요청을 보내면
store.py(장부)와 connectors.py(쇼핑몰 연결)에 일을 시키고 결과를 돌려줍니다.
외부에서 접속할 수 없도록 내 컴퓨터(127.0.0.1)에서만 열립니다.
"""
import csv
import io
import json
import sys
import threading
import time
import webbrowser
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import connectors  # noqa: E402
import demo  # noqa: E402
import store  # noqa: E402

HERE = Path(__file__).resolve().parent
SETTINGS_PATH = HERE / "설정" / "계정.json"
PORT = 8765

DEFAULT_SETTINGS = {
    "데모모드": True,
    "자동수집_분": 10,
    "첫수집_일수": 3,
    "기본택배사": "CJ대한통운",
    "계정": {
        "NAV": {"client_id": "", "client_secret": "", "n배송_속성": ["ARRIVAL_GUARANTEE"]},
        "CPG": {"vendor_id": "", "access_key": "", "secret_key": ""},
        "HCK": {"vendor_id": "", "access_key": "", "secret_key": "", "판매자배송": False, "로켓그로스": True},
        "YCU": {"vendor_id": "", "access_key": "", "secret_key": "", "판매자배송": False, "로켓그로스": True},
    },
}
SECRET_FIELDS = ("client_secret", "secret_key", "access_key")


# ─────────────────────────────── 설정 파일 ───────────────────────────────

def load_settings():
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    if SETTINGS_PATH.exists():
        try:
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            for k, v in saved.items():
                if k == "계정":
                    for acc, cfg in v.items():
                        s["계정"].setdefault(acc, {}).update(cfg)
                else:
                    s[k] = v
        except json.JSONDecodeError as e:
            store.log(f"설정 파일을 읽지 못했습니다 (JSON 형식 오류): {e}", "error")
    return s


def save_settings(s):
    SETTINGS_PATH.parent.mkdir(exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def public_settings():
    """화면에 보여줄 설정 — 비밀키는 끝 4자리만 보여줍니다."""
    s = load_settings()
    out = {k: v for k, v in s.items() if k != "계정"}
    out["계정"] = {}
    amap = store.account_map()
    for acc, cfg in s["계정"].items():
        c = {}
        for k, v in cfg.items():
            if k in SECRET_FIELDS and v:
                c[k] = "••••" + str(v)[-4:]
            else:
                c[k] = v
        a = amap.get(acc, {})
        c["_connected"] = connectors.has_keys(a.get("channel", ""), cfg)
        out["계정"][acc] = c
    return out


def update_settings(d):
    s = load_settings()
    for k in ("데모모드", "자동수집_분", "첫수집_일수", "기본택배사"):
        if k in d:
            s[k] = d[k]
    for acc, cfg in (d.get("계정") or {}).items():
        cur = s["계정"].setdefault(acc, {})
        for k, v in cfg.items():
            if k.startswith("_"):
                continue
            if k in SECRET_FIELDS and isinstance(v, str) and v.startswith("••••"):
                continue          # 가려진 값 그대로면 바꾸지 않음
            cur[k] = v.strip() if isinstance(v, str) else v
    save_settings(s)
    return public_settings()


# ─────────────────────────────── 수집·전송 ───────────────────────────────

_collect_lock = threading.Lock()


def collect_all():
    """모든 계정에서 주문을 가져옵니다. 데모 모드면 가짜 주문을 만듭니다."""
    if not _collect_lock.acquire(blocking=False):
        return {"ok": False, "msg": "이미 수집 중입니다"}
    try:
        s = load_settings()
        results = []
        if s.get("데모모드"):
            lines = demo.new_orders()
            n_new, n_chg = store.upsert_orders(lines)
            results.append(f"데모: 새 주문 {n_new}건")
        else:
            last = store.get_meta("last_collect_ts")
            since = (store.now() - timedelta(days=int(s.get("첫수집_일수") or 3))) if not last else \
                store.now() - timedelta(seconds=max(0, time.time() - last) + 3600)   # 1시간 겹쳐서 누락 방지
            for a in store.accounts():
                con = connectors.build(a["code"], s)
                if not con:
                    continue
                try:
                    lines = con.collect(since)
                    n_new, n_chg = store.upsert_orders(lines)
                    results.append(f"{a['name']}: 새 주문 {n_new}건, 상태변경 {n_chg}건")
                except Exception as e:  # noqa: BLE001 — 한 계정이 실패해도 나머지는 계속
                    store.log(f"[{a['name']}] 수집 실패: {e}", "error")
                    results.append(f"{a['name']}: 실패 ({e})")
            store.set_meta("last_collect_ts", time.time())
        store.set_meta("last_collect", store.now_str())
        msg = " · ".join(results) or "연결된 계정이 없습니다. 설정에서 API 키를 넣거나 데모 모드를 켜 주세요"
        store.log("주문 수집 — " + msg)
        return {"ok": True, "msg": msg}
    finally:
        _collect_lock.release()


def _by_account(orders):
    g = {}
    for o in orders:
        g.setdefault(o["account"], []).append(o)
    return g


def channel_action(ids, action):
    """발주확인·송장전송을 쇼핑몰에 반영합니다. 데모 모드거나 직접 등록한 주문은 우리 장부만 바꿉니다."""
    s = load_settings()
    orders = store.get_orders(ids)
    done, fails = [], []
    for acc, lst in _by_account(orders).items():
        con = None if s.get("데모모드") else connectors.build(acc, s)
        manual = [o for o in lst if o["channel_status"] in ("직접등록", "발주서", "데모") or con is None]
        remote = [o for o in lst if o not in manual]
        done += [o["id"] for o in manual]
        if remote:
            try:
                getattr(con, action)(remote)
                done += [o["id"] for o in remote]
            except Exception as e:  # noqa: BLE001
                fails.append(f"{acc}: {e}")
                store.log(f"[{acc}] {'발주확인' if action == 'confirm' else '송장전송'} 실패: {e}", "error")
    return done, fails


def auto_collect_loop():
    while True:
        s = load_settings()
        mins = int(s.get("자동수집_분") or 0)
        if mins > 0:
            time.sleep(mins * 60)
            try:
                collect_all()
            except Exception as e:  # noqa: BLE001
                store.log(f"자동 수집 오류: {e}", "error")
        else:
            time.sleep(60)


# ─────────────────────────────── 엑셀(CSV) ───────────────────────────────

def courier_csv(ids):
    """택배사 프로그램에 올릴 출고 파일 (엑셀에서 바로 열리는 CSV)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["주문번호", "받는분", "전화번호", "우편번호", "주소", "상품명", "옵션", "수량", "배송메모", "계정"])
    names = {a["code"]: a["name"] for a in store.accounts()}
    m = store.mapping_dict()
    for o in store.get_orders(ids):
        skus = " + ".join(f"{s}×{q * o['qty']}" for s, q in m.get((o["account"], o["item_key"]), []))
        w.writerow([o["order_no"], o["receiver"], o["phone"], o["zipcode"], o["address"],
                    o["product_name"], o["option_name"] + (f" [{skus}]" if skus else ""), o["qty"],
                    o["memo"], names.get(o["account"], o["account"])])
    return "﻿" + buf.getvalue()     # ﻿: 엑셀에서 한글이 깨지지 않게 하는 표시


def inventory_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    whs = store.warehouses()
    w.writerow(["SKU", "상품명", "분류", "안전재고"] + [x["name"] for x in whs] +
               ["총재고", "예약", "가용", "하루판매", "소진예상일"])
    for s in store.inventory():
        w.writerow([s["code"], s["name"], s["category"], s["safety"]] +
                   [s["wh"][x["code"]]["on_hand"] for x in whs] +
                   [s["total"], s["reserved"], s["avail"], s["daily"], s["days"] if s["days"] is not None else ""])
    return "﻿" + buf.getvalue()


# ─────────────────────────────── 웹 요청 처리 ───────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        data = body if isinstance(body, bytes) else (
            body.encode("utf-8") if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode("utf-8"))
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self._send(200, (HERE / "static" / "index.html").read_bytes(), "text/html; charset=utf-8")
            routes = {
                "/api/summary": lambda: store.summary(),
                "/api/orders": lambda: store.query_orders(q),
                "/api/inventory": lambda: {"items": store.inventory(), "warehouses": store.warehouses()},
                "/api/movements": lambda: store.movements(q.get("sku")),
                "/api/skus": lambda: store.skus(include_inactive=True),
                "/api/mappings": lambda: store.mapping_list(),
                "/api/settings": lambda: public_settings(),
                "/api/meta": lambda: {"accounts": store.accounts(), "warehouses": store.warehouses(),
                                      "skus": store.skus(), "couriers": list(connectors.COURIERS),
                                      "demo": load_settings().get("데모모드")},
                "/api/logs": lambda: store.rows("SELECT * FROM logs ORDER BY id DESC LIMIT 200"),
            }
            if u.path in routes:
                return self._send(200, routes[u.path]())
            if u.path == "/api/export/courier.csv":
                ids = [int(x) for x in q.get("ids", "").split(",") if x]
                return self._send(200, courier_csv(ids), "text/csv; charset=utf-8",
                                  {"Content-Disposition": "attachment; filename*=UTF-8''%EC%B6%9C%EA%B3%A0%EB%AA%A9%EB%A1%9D.csv"})
            if u.path == "/api/export/inventory.csv":
                return self._send(200, inventory_csv(), "text/csv; charset=utf-8",
                                  {"Content-Disposition": "attachment; filename*=UTF-8''%EC%9E%AC%EA%B3%A0%ED%98%84%ED%99%A9.csv"})
            self._send(404, {"error": "없는 주소입니다"})
        except Exception as e:  # noqa: BLE001
            store.log(f"화면 요청 오류 {u.path}: {e}", "error")
            self._send(500, {"error": str(e)})

    def do_POST(self):
        u = urlparse(self.path)
        try:
            d = self._json()
            p = u.path
            if p == "/api/collect":
                return self._send(200, collect_all())
            if p == "/api/orders/confirm":
                ids = [o["id"] for o in store.get_orders(d["ids"]) if o["status"] == store.ST_NEW]
                done, fails = channel_action(ids, "confirm")
                store.set_status(done, store.ST_CONFIRM)
                return self._send(200, {"ok": True, "done": len(done), "fails": fails})
            if p == "/api/orders/tracking":
                default = load_settings().get("기본택배사", "CJ대한통운")
                for e in d.get("rows", []):
                    e["courier"] = e.get("courier") or default
                ok, miss = store.apply_tracking(d.get("rows", []))
                store.log(f"송장 입력 {ok}건" + (f", 못 찾은 주문 {len(miss)}건" if miss else ""))
                return self._send(200, {"ok": True, "done": ok, "miss": miss})
            if p == "/api/orders/send":
                targets = [o for o in store.get_orders(d["ids"]) if o["tracking"] and o["status"] != store.ST_CANCEL]
                done, fails = channel_action([o["id"] for o in targets], "dispatch")
                store.set_status(done, store.ST_DONE, {"sent": 1})
                store.log(f"송장 전송·출고완료 {len(done)}건" + (f", 실패 {len(fails)}" if fails else ""))
                return self._send(200, {"ok": True, "done": len(done), "fails": fails,
                                        "skipped": len(d["ids"]) - len(targets)})
            if p == "/api/orders/ship":       # 송장 없이 출고완료 (로켓 납품, 직접 전달 등)
                ids = [o["id"] for o in store.get_orders(d["ids"]) if o["status"] in store.RESERVE_STATES]
                store.set_status(ids, store.ST_DONE)
                return self._send(200, {"ok": True, "done": len(ids)})
            if p == "/api/orders/cancel":
                store.set_status(d["ids"], store.ST_CANCEL)
                store.log(f"주문 취소 처리 {len(d['ids'])}건 (재고 원복)")
                return self._send(200, {"ok": True, "done": len(d["ids"])})
            if p == "/api/orders/manual":
                store.add_manual_order(d)
                return self._send(200, {"ok": True})
            if p == "/api/stock":
                store.stock_move(d)
                return self._send(200, {"ok": True})
            if p == "/api/skus":
                return self._send(200, {"ok": True, "code": store.upsert_sku(d)})
            if p == "/api/mappings":
                n = store.set_mapping(d["account"], d["item_key"], d.get("items", []))
                return self._send(200, {"ok": True, "orders": n})
            if p == "/api/settings":
                return self._send(200, update_settings(d))
            if p == "/api/test":
                con = connectors.build(d["account"], load_settings())
                if not con:
                    return self._send(200, {"ok": False, "msg": "키가 비어 있습니다"})
                try:
                    return self._send(200, {"ok": True, "msg": con.test()})
                except Exception as e:  # noqa: BLE001
                    return self._send(200, {"ok": False, "msg": str(e)})
            if p == "/api/demo/reset":
                demo.seed()
                return self._send(200, {"ok": True})
            self._send(404, {"error": "없는 주소입니다"})
        except ValueError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            store.log(f"처리 오류 {u.path}: {e}", "error")
            self._send(500, {"error": str(e)})


def main():
    store.db()
    s = load_settings()
    if not SETTINGS_PATH.exists():
        save_settings(s)
    if s.get("데모모드") and not store.rows("SELECT id FROM orders LIMIT 1"):
        print("데모 데이터를 만드는 중...")
        demo.seed()
    threading.Thread(target=auto_collect_loop, daemon=True).start()
    port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else PORT
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"\n  올투게더나우 통합관리가 켜졌습니다 → {url}\n  끄려면 이 창에서 Ctrl + C\n")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("종료합니다.")


if __name__ == "__main__":
    main()
