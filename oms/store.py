"""
데이터 저장소 (주문·재고·상품매핑)
--------------------------------
모든 데이터는 oms/oms.db 파일 하나(SQLite)에 저장됩니다.
엑셀 파일 하나에 시트가 여러 개 있는 것과 비슷하다고 생각하면 됩니다.

핵심 규칙
  · 재고 = '재고 장부(movements)'의 합계.  입고 +, 출고 −, 이동은 −/+ 한 쌍.
    장부를 더해서 재고를 계산하기 때문에 숫자가 어긋날 일이 없습니다.
  · 주문이 들어오면 '상품매핑'으로 우리 SKU(실물 상품)와 개수를 찾습니다.
    예) 쿠팡 '무릎보호대 2개' 1건 → 무릎보호대 블랙 SKU 2개
  · 판매자배송 주문은 출고완료 전까지 '예약'만 걸고(가용재고에서 빠짐),
    출고완료가 되면 장부에 출고로 적습니다.
  · N배송·로켓그로스처럼 남의 창고에서 나가는 주문은 들어오는 즉시 그 창고 재고에서 뺍니다.
"""
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
DB_PATH = Path(__file__).resolve().parent / "oms.db"
_lock = threading.RLock()

# 주문 상태 (진행 순서대로)
ST_NEW, ST_CONFIRM, ST_TRACK, ST_DONE, ST_PARTNER, ST_CANCEL = (
    "신규", "발주확인", "송장입력", "출고완료", "위탁배송", "취소")
STATUS_RANK = {ST_NEW: 0, ST_CONFIRM: 1, ST_TRACK: 2, ST_DONE: 3, ST_PARTNER: 3, ST_CANCEL: 9}
RESERVE_STATES = (ST_NEW, ST_CONFIRM, ST_TRACK)   # 아직 안 나갔지만 팔린 것 → 예약
DEDUCT_STATES = (ST_DONE, ST_PARTNER)             # 실제로 나간 것 → 장부에서 차감

# 배송방식 → 재고가 빠지는 창고
SHIP_SELF, SHIP_NFA, SHIP_GROWTH, SHIP_ROCKET = "판매자배송", "N배송", "로켓그로스", "로켓납품"

DEFAULT_WAREHOUSES = [
    ("HQ", "본사창고", "우리가 직접 출고하는 창고 (판매자배송·로켓배송 납품)"),
    ("NFA", "네이버 N배송창고", "네이버 도착보장(N배송) 풀필먼트 창고"),
    ("RG-HCK", "쿠팡그로스·휴책", "휴책 계정 로켓그로스 입고분"),
    ("RG-YCU", "쿠팡그로스·유큐어", "유큐어 계정 로켓그로스 입고분"),
]
# 코드, 채널, 이름, 기본 배송방식, 그로스 창고
DEFAULT_ACCOUNTS = [
    ("NAV", "네이버", "올투게더나우 스마트스토어", SHIP_NFA, ""),
    ("CPG", "쿠팡", "올투게더나우", SHIP_SELF, ""),
    ("HCK", "쿠팡", "휴책", SHIP_GROWTH, "RG-HCK"),
    ("YCU", "쿠팡", "유큐어", SHIP_GROWTH, "RG-YCU"),
    ("RKT", "쿠팡", "로켓배송", SHIP_ROCKET, ""),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS warehouses (code TEXT PRIMARY KEY, name TEXT, memo TEXT, sort INTEGER);
CREATE TABLE IF NOT EXISTS accounts (code TEXT PRIMARY KEY, channel TEXT, name TEXT,
    ship_type TEXT, growth_wh TEXT, sort INTEGER);
CREATE TABLE IF NOT EXISTS skus (code TEXT PRIMARY KEY, name TEXT, category TEXT,
    safety INTEGER DEFAULT 0, cost INTEGER DEFAULT 0, memo TEXT DEFAULT '', active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS mappings (account TEXT, item_key TEXT, sku TEXT, qty INTEGER,
    PRIMARY KEY (account, item_key, sku));
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT, line_id TEXT, order_no TEXT, ordered_at TEXT,
    item_key TEXT, product_name TEXT, option_name TEXT, qty INTEGER, amount INTEGER,
    buyer TEXT, receiver TEXT, phone TEXT, zipcode TEXT, address TEXT, memo TEXT,
    ship_type TEXT, wh TEXT, status TEXT, channel_status TEXT,
    courier TEXT DEFAULT '', tracking TEXT DEFAULT '', sent INTEGER DEFAULT 0,
    shipped_at TEXT DEFAULT '', updated_at TEXT,
    UNIQUE (account, line_id));
CREATE INDEX IF NOT EXISTS ix_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS ix_orders_date ON orders(ordered_at);
CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, sku TEXT, wh TEXT, qty INTEGER,
    kind TEXT, ref TEXT DEFAULT '', memo TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_mv_ref ON movements(ref);
CREATE INDEX IF NOT EXISTS ix_mv_sku ON movements(sku, wh);
CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, level TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def now():
    return datetime.now(KST)


def now_str():
    return now().strftime("%Y-%m-%d %H:%M")


def connect():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


_con = None


def db():
    global _con
    if _con is None:
        _con = connect()
        _con.executescript(SCHEMA)
        seed_defaults(_con)
    return _con


def rows(sql, args=()):
    with _lock:
        return [dict(r) for r in db().execute(sql, args).fetchall()]


def one(sql, args=()):
    with _lock:
        r = db().execute(sql, args).fetchone()
        return dict(r) if r else None


def seed_defaults(con):
    if con.execute("SELECT COUNT(*) FROM warehouses").fetchone()[0] == 0:
        con.executemany("INSERT INTO warehouses VALUES (?,?,?,?)",
                        [(c, n, m, i) for i, (c, n, m) in enumerate(DEFAULT_WAREHOUSES)])
    if con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
        con.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?)",
                        [(*a, i) for i, a in enumerate(DEFAULT_ACCOUNTS)])
    con.commit()


def log(text, level="info"):
    with _lock:
        db().execute("INSERT INTO logs (ts, level, text) VALUES (?,?,?)", (now_str(), level, text))
        db().commit()


def get_meta(k, default=None):
    r = one("SELECT v FROM meta WHERE k=?", (k,))
    return json.loads(r["v"]) if r else default


def set_meta(k, v):
    with _lock:
        db().execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, json.dumps(v, ensure_ascii=False)))
        db().commit()


# ─────────────────────────────── 기준 정보 ───────────────────────────────

def accounts():
    return rows("SELECT * FROM accounts ORDER BY sort")


def warehouses():
    return rows("SELECT * FROM warehouses ORDER BY sort")


def account_map():
    return {a["code"]: a for a in accounts()}


def wh_for(account, ship_type):
    """주문의 배송방식으로 재고가 빠질 창고를 정합니다."""
    if ship_type == SHIP_NFA:
        return "NFA"
    if ship_type == SHIP_GROWTH:
        a = account_map().get(account) or {}
        return a.get("growth_wh") or "HQ"
    return "HQ"


def skus(include_inactive=False):
    q = "SELECT * FROM skus" + ("" if include_inactive else " WHERE active=1") + " ORDER BY category, code"
    return rows(q)


def upsert_sku(d):
    code = (d.get("code") or "").strip().upper()
    if not code:
        raise ValueError("SKU 코드를 입력해 주세요")
    with _lock:
        db().execute("""INSERT INTO skus (code, name, category, safety, cost, memo, active)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET
            name=excluded.name, category=excluded.category, safety=excluded.safety,
            cost=excluded.cost, memo=excluded.memo, active=excluded.active""",
                     (code, d.get("name", "").strip() or code, d.get("category", "").strip(),
                      int(d.get("safety") or 0), int(d.get("cost") or 0), d.get("memo", ""),
                      0 if d.get("active") in (0, False, "0") else 1))
        db().commit()
    return code


# ─────────────────────────────── 상품 매핑 ───────────────────────────────

def mapping_dict():
    """{(계정, 상품키): [(SKU, 개수), ...]}"""
    out = {}
    for r in rows("SELECT * FROM mappings"):
        out.setdefault((r["account"], r["item_key"]), []).append((r["sku"], r["qty"]))
    return out


def set_mapping(account, item_key, items):
    """items: [{sku, qty}] — 빈 목록이면 매핑을 지웁니다."""
    with _lock:
        con = db()
        con.execute("DELETE FROM mappings WHERE account=? AND item_key=?", (account, item_key))
        for it in items:
            sku, q = (it.get("sku") or "").strip().upper(), int(it.get("qty") or 0)
            if sku and q > 0:
                con.execute("INSERT OR REPLACE INTO mappings VALUES (?,?,?,?)", (account, item_key, sku, q))
        con.commit()
        ids = [r["id"] for r in rows("SELECT id FROM orders WHERE account=? AND item_key=?", (account, item_key))]
    sync_stock(ids)
    return len(ids)


def mapping_list():
    """주문에 나온 판매상품 목록 + 매핑 상태 (미매칭 먼저)."""
    m = mapping_dict()
    items = rows("""SELECT account, item_key, MAX(product_name) product_name, MAX(option_name) option_name,
                    COUNT(*) orders, SUM(qty) qty, MAX(ordered_at) last_at
                    FROM orders GROUP BY account, item_key""")
    seen = set()
    for it in items:
        k = (it["account"], it["item_key"])
        seen.add(k)
        it["map"] = [{"sku": s, "qty": q} for s, q in m.get(k, [])]
    for (acc, key), lst in m.items():      # 매핑만 있고 아직 주문이 없는 상품
        if (acc, key) not in seen:
            items.append({"account": acc, "item_key": key, "product_name": "", "option_name": "",
                          "orders": 0, "qty": 0, "last_at": "", "map": [{"sku": s, "qty": q} for s, q in lst]})
    items.sort(key=lambda x: (bool(x["map"]), -(x["qty"] or 0)))
    return items


# ─────────────────────────────── 재고 장부 ───────────────────────────────

def add_movement(sku, wh, qty, kind, memo="", ref="", ts=None):
    with _lock:
        db().execute("INSERT INTO movements (ts, sku, wh, qty, kind, ref, memo) VALUES (?,?,?,?,?,?,?)",
                     (ts or now_str(), sku, wh, int(qty), kind, ref, memo))
        db().commit()


def stock_move(d):
    """화면에서 입고/이동/조정 등록."""
    kind, sku, qty = d.get("kind"), (d.get("sku") or "").upper(), int(d.get("qty") or 0)
    wh, to_wh, memo = d.get("wh"), d.get("to_wh"), d.get("memo", "")
    if not one("SELECT code FROM skus WHERE code=?", (sku,)):
        raise ValueError("등록되지 않은 SKU입니다")
    if kind == "입고":
        if qty <= 0:
            raise ValueError("입고 수량은 1개 이상이어야 합니다")
        add_movement(sku, wh, qty, "입고", memo)
    elif kind == "이동":
        if qty <= 0 or not to_wh or to_wh == wh:
            raise ValueError("보내는 창고와 받는 창고, 수량을 확인해 주세요")
        ts = now_str()
        add_movement(sku, wh, -qty, "이동출고", memo or f"→ {to_wh}", ts=ts)
        add_movement(sku, to_wh, qty, "이동입고", memo or f"← {wh}", ts=ts)
    elif kind == "조정":   # 실사 결과로 맞추기: qty = 실제 수량
        cur = (one("SELECT COALESCE(SUM(qty),0) s FROM movements WHERE sku=? AND wh=?", (sku, wh)) or {}).get("s", 0)
        diff = qty - cur
        if diff:
            add_movement(sku, wh, diff, "재고조정", memo or f"실사 {qty}개로 맞춤 (이전 {cur}개)")
    elif kind == "출고":   # 샘플·불량폐기·B2B 등 수동 출고
        if qty <= 0:
            raise ValueError("출고 수량은 1개 이상이어야 합니다")
        add_movement(sku, wh, -qty, "수동출고", memo)
    else:
        raise ValueError("알 수 없는 작업입니다")


def sync_stock(order_ids=None):
    """
    주문 상태에 맞게 재고 장부를 다시 맞춥니다.
    주문마다 '이 주문 때문에 나간 재고'를 지우고 다시 적기 때문에 몇 번을 돌려도 결과가 같습니다.
    (매핑을 나중에 고쳐도 과거 주문까지 자동으로 바로잡힙니다)
    """
    m = mapping_dict()
    with _lock:
        con = db()
        if order_ids is None:
            targets = con.execute("SELECT * FROM orders").fetchall()
        else:
            if not order_ids:
                return
            ph = ",".join("?" * len(order_ids))
            targets = con.execute(f"SELECT * FROM orders WHERE id IN ({ph})", list(order_ids)).fetchall()
        for o in targets:
            ref = f"order:{o['id']}"
            con.execute("DELETE FROM movements WHERE ref=?", (ref,))
            if o["status"] not in DEDUCT_STATES:
                continue
            kind = "판매출고" if o["ship_type"] in (SHIP_SELF, SHIP_ROCKET) else "위탁출고"
            ts = o["shipped_at"] or o["ordered_at"]
            for sku, q in m.get((o["account"], o["item_key"]), []):
                con.execute("INSERT INTO movements (ts, sku, wh, qty, kind, ref, memo) VALUES (?,?,?,?,?,?,?)",
                            (ts, sku, o["wh"], -q * o["qty"], kind, ref, f"{o['account']} {o['order_no']}"))
        con.commit()


def inventory():
    """SKU × 창고 재고표 + 예약·가용·최근 판매속도·소진 예상일."""
    whs = [w["code"] for w in warehouses()]
    m = mapping_dict()
    on_hand, reserved, sold = {}, {}, {}
    for r in rows("SELECT sku, wh, SUM(qty) q FROM movements GROUP BY sku, wh"):
        on_hand[(r["sku"], r["wh"])] = r["q"]
    for o in rows(f"SELECT account, item_key, wh, SUM(qty) q FROM orders WHERE status IN "
                  f"({','.join('?' * len(RESERVE_STATES))}) GROUP BY account, item_key, wh", RESERVE_STATES):
        for sku, q in m.get((o["account"], o["item_key"]), []):
            reserved[(sku, o["wh"])] = reserved.get((sku, o["wh"]), 0) + q * o["q"]
    since = (now() - timedelta(days=14)).strftime("%Y-%m-%d %H:%M")
    for r in rows("SELECT sku, wh, -SUM(qty) q FROM movements WHERE kind IN ('판매출고','위탁출고') "
                  "AND ts>=? GROUP BY sku, wh", (since,)):
        sold[(r["sku"], r["wh"])] = r["q"]
    out = []
    for s in skus():
        row = {**s, "wh": {}, "total": 0, "avail": 0, "reserved": 0, "daily": 0.0}
        for w in whs:
            k = (s["code"], w)
            oh, rs, d = on_hand.get(k, 0), reserved.get(k, 0), sold.get(k, 0) / 14
            av = oh - rs
            row["wh"][w] = {"on_hand": oh, "reserved": rs, "avail": av, "daily": round(d, 1),
                            "days": (round(av / d, 1) if d > 0 else None)}
            row["total"] += oh
            row["reserved"] += rs
            row["avail"] += av
            row["daily"] += d
        row["daily"] = round(row["daily"], 1)
        row["days"] = round(row["avail"] / row["daily"], 1) if row["daily"] > 0 else None
        row["low"] = row["avail"] <= s["safety"]
        # 남의 창고(N배송·그로스) 중 7일 안에 바닥나는 곳 → 입고(이동) 필요
        row["refill"] = [w for w in whs if w != "HQ" and row["wh"][w]["days"] is not None
                         and row["wh"][w]["days"] < 7]
        out.append(row)
    return out


def movements(sku=None, limit=300):
    if sku:
        return rows("SELECT * FROM movements WHERE sku=? ORDER BY ts DESC, id DESC LIMIT ?", (sku, limit))
    return rows("SELECT * FROM movements WHERE kind NOT IN ('판매출고','위탁출고') "
                "ORDER BY ts DESC, id DESC LIMIT ?", (limit,))


# ─────────────────────────────── 주문 ───────────────────────────────

def upsert_orders(lines):
    """
    쇼핑몰에서 가져온 주문을 저장합니다.
    이미 있는 주문이면 상태만 앞으로 진행시킵니다 (우리가 먼저 처리한 걸 되돌리지 않음).
    단, 쇼핑몰에서 취소된 주문은 무조건 취소로 바꿉니다.
    """
    new_ids, changed_ids = [], []
    with _lock:
        con = db()
        for ln in lines:
            ex = con.execute("SELECT * FROM orders WHERE account=? AND line_id=?",
                             (ln["account"], ln["line_id"])).fetchone()
            ship = ln.get("ship_type") or SHIP_SELF
            wh = ln.get("wh") or wh_for(ln["account"], ship)
            st = ln.get("status") or ST_NEW
            if ex is None:
                cur = con.execute("""INSERT INTO orders (account, line_id, order_no, ordered_at, item_key,
                    product_name, option_name, qty, amount, buyer, receiver, phone, zipcode, address, memo,
                    ship_type, wh, status, channel_status, courier, tracking, sent, shipped_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                  (ln["account"], ln["line_id"], ln.get("order_no", ""), ln.get("ordered_at", now_str()),
                                   ln.get("item_key", ""), ln.get("product_name", ""), ln.get("option_name", ""),
                                   int(ln.get("qty") or 1), int(ln.get("amount") or 0), ln.get("buyer", ""),
                                   ln.get("receiver", ""), ln.get("phone", ""), ln.get("zipcode", ""),
                                   ln.get("address", ""), ln.get("memo", ""), ship, wh, st,
                                   ln.get("channel_status", ""), ln.get("courier", ""), ln.get("tracking", ""),
                                   int(ln.get("sent") or 0), ln.get("shipped_at", ""), now_str()))
                new_ids.append(cur.lastrowid)
            else:
                old = ex["status"]
                if st == ST_CANCEL or STATUS_RANK.get(st, 0) > STATUS_RANK.get(old, 0):
                    newst = st
                else:
                    newst = old
                tracking = ex["tracking"] or ln.get("tracking", "")
                courier = ex["courier"] or ln.get("courier", "")
                con.execute("""UPDATE orders SET status=?, channel_status=?, tracking=?, courier=?,
                               shipped_at=CASE WHEN shipped_at='' THEN ? ELSE shipped_at END, updated_at=?
                               WHERE id=?""",
                            (newst, ln.get("channel_status", ""), tracking, courier,
                             ln.get("shipped_at", ""), now_str(), ex["id"]))
                if newst != old:
                    changed_ids.append(ex["id"])
        con.commit()
    sync_stock(new_ids + changed_ids)
    return len(new_ids), len(changed_ids)


def query_orders(f):
    where, args = ["1=1"], []
    if f.get("account"):
        where.append("account=?"); args.append(f["account"])
    if f.get("status"):
        if f["status"] == "처리대기":
            where.append(f"status IN ({','.join('?' * len(RESERVE_STATES))})"); args += list(RESERVE_STATES)
        else:
            where.append("status=?"); args.append(f["status"])
    if f.get("ship_type"):
        where.append("ship_type=?"); args.append(f["ship_type"])
    if f.get("from"):
        where.append("ordered_at>=?"); args.append(f["from"])
    if f.get("to"):
        where.append("ordered_at<=?"); args.append(f["to"] + " 23:59")
    if f.get("q"):
        q = f"%{f['q']}%"
        where.append("(order_no LIKE ? OR product_name LIKE ? OR option_name LIKE ? OR receiver LIKE ? "
                     "OR tracking LIKE ? OR buyer LIKE ?)")
        args += [q] * 6
    m = mapping_dict()
    limit = min(int(f.get("limit") or 500), 3000)
    out = rows(f"SELECT * FROM orders WHERE {' AND '.join(where)} ORDER BY ordered_at DESC, id DESC LIMIT ?",
               args + [limit])
    if f.get("unmapped"):
        out = [o for o in out if (o["account"], o["item_key"]) not in m]
    for o in out:
        o["map"] = [{"sku": s, "qty": q} for s, q in m.get((o["account"], o["item_key"]), [])]
    return out


def get_orders(ids):
    if not ids:
        return []
    return rows(f"SELECT * FROM orders WHERE id IN ({','.join('?' * len(ids))})", list(ids))


def set_status(ids, status, extra=None):
    with _lock:
        con = db()
        for i in ids:
            sets, args = ["status=?", "updated_at=?"], [status, now_str()]
            if status == ST_DONE:
                sets.append("shipped_at=CASE WHEN shipped_at='' THEN ? ELSE shipped_at END")
                args.append(now_str())
            for k, v in (extra or {}).items():
                sets.append(f"{k}=?"); args.append(v)
            con.execute(f"UPDATE orders SET {', '.join(sets)} WHERE id=?", args + [i])
        con.commit()
    sync_stock(ids)


def apply_tracking(entries):
    """
    송장 일괄 입력. entries: [{key, courier, tracking}]
    key는 주문번호 또는 상품주문번호. 같은 주문번호에 상품이 여러 줄이면 모두 같은 송장을 붙입니다.
    """
    ok, miss = 0, []
    with _lock:
        con = db()
        for e in entries:
            key, trk = str(e.get("key", "")).strip(), str(e.get("tracking", "")).strip()
            if not key or not trk:
                continue
            found = con.execute("SELECT id, status FROM orders WHERE (order_no=? OR line_id=?) "
                                "AND ship_type IN (?,?)", (key, key, SHIP_SELF, SHIP_ROCKET)).fetchall()
            if not found:
                miss.append(key)
                continue
            for r in found:
                st = r["status"] if r["status"] in (ST_DONE, ST_CANCEL) else ST_TRACK
                con.execute("UPDATE orders SET courier=?, tracking=?, status=?, sent=0, updated_at=? WHERE id=?",
                            (e.get("courier") or "CJ대한통운", trk, st, now_str(), r["id"]))
                ok += 1
        con.commit()
    return ok, miss


def add_manual_order(d):
    """전화·B2B·로켓배송 발주 등 직접 등록."""
    acc = d.get("account") or "RKT"
    a = account_map().get(acc)
    if not a:
        raise ValueError("계정을 선택해 주세요")
    ship = d.get("ship_type") or (SHIP_ROCKET if acc == "RKT" else SHIP_SELF)
    sku, qty = (d.get("sku") or "").upper(), int(d.get("qty") or 0)
    if qty <= 0:
        raise ValueError("수량을 입력해 주세요")
    stamp = now().strftime("%Y%m%d%H%M%S")
    item_key = d.get("item_key") or (f"직접:{sku}" if sku else f"직접:{d.get('product_name', '')}")
    if sku and not mapping_dict().get((acc, item_key)):
        set_mapping(acc, item_key, [{"sku": sku, "qty": 1}])
    name = d.get("product_name") or (one("SELECT name FROM skus WHERE code=?", (sku,)) or {}).get("name", sku)
    upsert_orders([{
        "account": acc, "line_id": f"M{stamp}", "order_no": d.get("order_no") or f"M{stamp}",
        "ordered_at": now_str(), "item_key": item_key, "product_name": name,
        "option_name": d.get("option_name", ""), "qty": qty, "amount": int(d.get("amount") or 0),
        "buyer": d.get("buyer", ""), "receiver": d.get("receiver", ""), "phone": d.get("phone", ""),
        "zipcode": d.get("zipcode", ""), "address": d.get("address", ""), "memo": d.get("memo", ""),
        "ship_type": ship, "status": ST_NEW, "channel_status": "직접등록"}])


# ─────────────────────────────── 요약 ───────────────────────────────

def summary():
    today = now().strftime("%Y-%m-%d")
    d7 = (now() - timedelta(days=6)).strftime("%Y-%m-%d")
    m = mapping_dict()
    acc_rows = []
    for a in accounts():
        r = one("""SELECT
            SUM(CASE WHEN ordered_at>=? AND status!='취소' THEN 1 ELSE 0 END) today_cnt,
            SUM(CASE WHEN ordered_at>=? AND status!='취소' THEN amount ELSE 0 END) today_amt,
            SUM(CASE WHEN ordered_at>=? AND status!='취소' THEN 1 ELSE 0 END) w_cnt,
            SUM(CASE WHEN ordered_at>=? AND status!='취소' THEN amount ELSE 0 END) w_amt,
            SUM(CASE WHEN status IN ('신규','발주확인','송장입력') THEN 1 ELSE 0 END) pending
            FROM orders WHERE account=?""", (today, today, d7, d7, a["code"]))
        acc_rows.append({**a, **{k: (v or 0) for k, v in r.items()}})
    pend = {s: 0 for s in RESERVE_STATES}
    for r in rows("SELECT status, COUNT(*) c FROM orders WHERE status IN ('신규','발주확인','송장입력') GROUP BY status"):
        pend[r["status"]] = r["c"]
    unsent = (one("SELECT COUNT(*) c FROM orders WHERE tracking!='' AND sent=0 AND status!='취소' "
                  "AND channel_status!='직접등록'") or {}).get("c", 0)
    keys = rows("SELECT DISTINCT account, item_key FROM orders WHERE status!='취소'")
    unmapped = sum(1 for k in keys if (k["account"], k["item_key"]) not in m)
    inv = inventory()
    daily = rows("""SELECT substr(ordered_at,1,10) d, account, COUNT(*) c, SUM(amount) amt FROM orders
                    WHERE status!='취소' AND ordered_at>=? GROUP BY d, account ORDER BY d""",
                 ((now() - timedelta(days=13)).strftime("%Y-%m-%d"),))
    return {
        "today": today,
        "accounts": acc_rows,
        "pending": pend,
        "unsent": unsent,
        "unmapped": unmapped,
        "low": [{"code": s["code"], "name": s["name"], "avail": s["avail"], "safety": s["safety"],
                 "days": s["days"]} for s in inv if s["low"]],
        "refill": [{"code": s["code"], "name": s["name"],
                    "wh": [{"wh": w, "avail": s["wh"][w]["avail"], "days": s["wh"][w]["days"]} for w in s["refill"]]}
                   for s in inv if s["refill"]],
        "daily": daily,
        "logs": rows("SELECT * FROM logs ORDER BY id DESC LIMIT 12"),
        "last_collect": get_meta("last_collect"),
    }


def reset_all():
    with _lock:
        con = db()
        for t in ("orders", "movements", "mappings", "skus", "logs", "meta"):
            con.execute(f"DELETE FROM {t}")
        con.commit()
