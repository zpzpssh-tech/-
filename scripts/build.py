"""
대시보드 빌드 스크립트
----------------------
data/ 폴더의 CSV·설정을 읽어서 dashboard/index.html 한 파일로 만듭니다.
만들어진 파일은 인터넷 없이도 브라우저에서 바로 열립니다.

실행:  python3 scripts/build.py

읽는 파일
  data/sales.csv     날짜, 채널, 계정, 상품코드, 주문건수, 판매수량, 매출
  data/products.csv  상품코드, 상품명, 카테고리, 원가, 포장비 (원가는 비워둬도 됩니다)
  data/costs.csv     월(YYYY-MM), 구분(고정지출|마케팅비), 항목, 계정(비우면 공통), 금액
  data/settings.json 계정별 수수료율·건당배송비·수수료차감됨
  data/정산요약.csv   (있으면) 정산상태별 반영 내역
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TEMPLATE = ROOT / "templates" / "dashboard.html"
OUT = ROOT / "dashboard" / "index.html"


def read_csv(path, required, allow_empty=False):
    if not path.exists():
        sys.exit(f"[오류] 파일이 없습니다: {path}")
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
        f.seek(0)
        header = next(csv.reader(f), [])
    header = [h.lstrip("﻿").strip() for h in header]
    missing = [c for c in required if c not in header]
    if missing:
        sys.exit(f"[오류] {path.name}에 열이 없습니다: {', '.join(missing)}\n"
                 f"       현재 열: {', '.join(header)}")
    if not rows and not allow_empty:
        sys.exit(f"[오류] {path.name}에 데이터가 한 줄도 없습니다.")
    return rows


def to_num(value, where, blank=None):
    s = str(value or "").replace(",", "").replace("₩", "").strip()
    if s == "":
        return blank
    try:
        return int(round(float(s)))
    except ValueError:
        sys.exit(f"[오류] 숫자가 아닌 값이 있습니다 ({where}): '{value}'")


def main():
    settings = json.loads((DATA / "settings.json").read_text(encoding="utf-8"))
    accounts = settings["계정"]
    ship = settings.get("택배비", {})
    n_rate = float(ship.get("N배송비율", 0) or 0)
    if not 0 <= n_rate <= 1:
        sys.exit(f"[오류] settings.json의 N배송비율은 0~1 사이여야 합니다. 현재: {n_rate}")
    ship_unit = round(n_rate * float(ship.get("N배송단가", 0) or 0)
                      + (1 - n_rate) * float(ship.get("판매자배송단가", 0) or 0))
    account_names = {a["계정"] for a in accounts}

    products = read_csv(DATA / "products.csv", ["상품코드", "상품명", "카테고리"])
    product_map = {}
    for p in products:
        code = p["상품코드"].strip()
        cost = to_num(p.get("원가"), f"products.csv {code} 원가", blank=None)
        pack = to_num(p.get("포장비"), f"products.csv {code} 포장비", blank=None)
        product_map[code] = {
            "상품명": p["상품명"].strip(),
            "카테고리": p["카테고리"].strip(),
            "원가": cost,
            "포장비": pack or 0,
            "원가있음": cost is not None,
        }

    sales_rows = read_csv(DATA / "sales.csv", ["날짜", "채널", "계정", "상품코드", "주문건수", "판매수량", "매출"])
    sales = []
    unknown_products, unknown_accounts = set(), set()
    for i, r in enumerate(sales_rows, start=2):
        code, acct = r["상품코드"].strip(), r["계정"].strip()
        if code not in product_map:
            unknown_products.add(code)
        if acct not in account_names:
            unknown_accounts.add(acct)
        try:
            datetime.strptime(r["날짜"].strip(), "%Y-%m-%d")
        except ValueError:
            sys.exit(f"[오류] sales.csv {i}행 날짜 형식이 YYYY-MM-DD가 아닙니다: '{r['날짜']}'")
        sales.append([
            r["날짜"].strip(), acct, code,
            to_num(r["주문건수"], f"sales.csv {i}행 주문건수", 0),
            to_num(r["판매수량"], f"sales.csv {i}행 판매수량", 0),
            to_num(r["매출"], f"sales.csv {i}행 매출", 0),
        ])
    if unknown_products:
        sys.exit(f"[오류] products.csv에 없는 상품코드가 sales.csv에 있습니다: {', '.join(sorted(unknown_products))}\n"
                 f"       scripts/import_naver.py 를 다시 실행하면 자동으로 등록됩니다.")
    if unknown_accounts:
        sys.exit(f"[오류] settings.json에 없는 계정이 sales.csv에 있습니다: {', '.join(sorted(unknown_accounts))}")

    cost_rows = read_csv(DATA / "costs.csv", ["월", "구분", "항목", "계정", "금액"], allow_empty=True)
    costs = []
    for i, r in enumerate(cost_rows, start=2):
        kind = r["구분"].strip()
        if kind not in ("고정지출", "마케팅비"):
            sys.exit(f"[오류] costs.csv {i}행 구분은 '고정지출' 또는 '마케팅비'여야 합니다: '{kind}'")
        acct = r["계정"].strip()
        if acct and acct not in account_names:
            sys.exit(f"[오류] costs.csv {i}행 계정이 settings.json에 없습니다: '{acct}'")
        costs.append([r["월"].strip(), kind, r["항목"].strip(), acct,
                      to_num(r["금액"], f"costs.csv {i}행 금액", 0)])

    # ── 원가일계.csv (import_costs.py가 만든 날짜·상품번호별 원가) ──
    pid2code = {}
    for pr in products:
        no = (pr.get("상품번호") or "").strip()
        if no:
            pid2code[no] = pr["상품코드"].strip()
    cogs_rows, cogs_unmapped = [], set()
    cp = DATA / "원가일계.csv"
    if cp.exists():
        with open(cp, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                keys = {k.lstrip("\ufeff"): v for k, v in r.items()}
                no = keys["상품번호"].strip()
                code = pid2code.get(no)
                if not code:
                    cogs_unmapped.add(no)
                    continue
                cogs_rows.append([
                    keys["날짜"].strip(), code,
                    to_num(keys["수량"], "원가일계.csv 수량", 0),
                    to_num(keys["원가합계"], "원가일계.csv 원가합계", 0),
                    to_num(keys["원가미상수량"], "원가일계.csv 원가미상수량", 0),
                ])

    settle = []
    sp = DATA / "정산요약.csv"
    if sp.exists():
        with open(sp, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                settle.append({k.lstrip("﻿"): (to_num(v, "정산요약.csv", 0) if k != "파일" else v)
                               for k, v in r.items()})

    daily_orders = {}
    dop = DATA / "일별주문.csv"
    if dop.exists():
        with open(dop, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                key = r[list(r.keys())[0]].strip()
                daily_orders[key] = to_num(r["주문건수"], "일별주문.csv", 0)

    # ── 옵션별 월 판매량 (재고 예측용) ──
    opt_sales = []
    op = DATA / "옵션판매.csv"
    if op.exists():
        with open(op, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = {c.lstrip("\ufeff"): v for c, v in r.items()}
                code = pid2code.get(k["상품번호"].strip())
                if not code:
                    continue
                opt_sales.append([k["월"].strip(), code, k["옵션정보"].strip(),
                                  to_num(k["수량"], "옵션판매.csv 수량", 0),
                                  to_num(k["원가합계"], "옵션판매.csv 원가합계", 0)])

    # ── 광고 지표 (ROAS 계산용) ──
    ad_stats = []
    ap = DATA / "광고지표.csv"
    if ap.exists():
        with open(ap, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = {c.lstrip("\ufeff"): v for c, v in r.items()}
                ad_stats.append([k["월"].strip(), k["계정"].strip(),
                                 to_num(k["광고비"], "광고지표.csv", 0),
                                 to_num(k["광고전환수"], "광고지표.csv", 0),
                                 to_num(k["광고전환매출"], "광고지표.csv", 0)])

    # ── 고객 지표 ──
    cust = {}
    cp2 = DATA / "고객지표.csv"
    if cp2.exists():
        with open(cp2, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = list(r.values())
                cust[str(k[0]).strip()] = float(str(k[1]).replace(",", "") or 0)

    dates = sorted({s[0] for s in sales})
    used_codes = {s[2] for s in sales}
    need_cost = sorted(c for c in used_codes if not product_map[c]["원가있음"] and c not in ("SHIP", "OPT"))

    payload = {
        "브랜드": settings.get("브랜드", ""),
        "메모": settings.get("메모", ""),
        "예시데이터": bool(settings.get("예시데이터", False)),
        "생성시각": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "기간": {"시작": dates[0], "끝": dates[-1], "일수": len(dates)},
        "계정": accounts,
        "상품": product_map,
        "매출": sales,
        "비용": costs,
        "정산요약": settle,
        "원가없는상품": need_cost,
        "일별주문": daily_orders,
        "원가": cogs_rows,
        "옵션판매": opt_sales,
        "광고지표": ad_stats,
        "고객지표": cust,
        "택배비": {"건당단가": ship_unit, "N배송단가": ship.get("N배송단가", 0),
                 "판매자배송단가": ship.get("판매자배송단가", 0), "N배송비율": n_rate},
    }

    template = TEMPLATE.read_text(encoding="utf-8")
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = template.replace("__DASHBOARD_DATA__", data_json)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")

    total = sum(s[5] for s in sales)
    print(f"대시보드 생성 완료 → {OUT.relative_to(ROOT)}")
    print(f"  기간: {dates[0]} ~ {dates[-1]} ({len(dates)}일)")
    print(f"  매출 행 {len(sales):,} · 상품 {len(used_codes)}개 · 비용 {len(costs)}건")
    print(f"  총매출: ₩{total:,}")
    if cogs_rows:
        in_range = [r for r in cogs_rows if dates[0] <= r[0] <= dates[-1]]
        q = sum(r[2] for r in in_range); unk = sum(r[4] for r in in_range)
        cg = sum(r[3] for r in in_range)
        print(f"  원가: ₩{cg:,} · 수량 {q:,}개 · 원가 반영률 {(q - unk) / q * 100:.1f}%" if q else "  원가: 없음")
        print(f"  매출총이익(매출 − 원가): ₩{total - cg:,}  ({(total - cg) / total * 100:.1f}%)")
        if cogs_unmapped:
            print(f"  매출에 없는 상품번호 {len(cogs_unmapped)}개는 원가에서 제외했습니다.")
    else:
        print("  원가일계.csv 가 없습니다. scripts/import_costs.py 를 먼저 실행해 주세요.")
    if not costs:
        print("  고정지출·마케팅비가 비어 있어 영업이익은 아직 계산하지 않습니다.")
    else:
        months_in = sorted({d[:7] for d in dates})
        cg = sum(r[3] for r in cogs_rows if dates[0] <= r[0] <= dates[-1])
        orders = sum(v for k, v in daily_orders.items() if dates[0] <= k <= dates[-1])
        shipping = orders * ship_unit
        ad = sum(c[4] for c in costs if c[0] in months_in and c[1] == "마케팅비" and c[3])
        common_mkt = sum(c[4] for c in costs if c[0] in months_in and c[1] == "마케팅비" and not c[3])
        fixed = sum(c[4] for c in costs if c[0] in months_in and c[1] == "고정지출")
        contrib = total - cg - shipping - ad
        print(f"  택배비: ₩{shipping:,} (주문 {orders:,}건 × ₩{ship_unit:,})")
        print(f"  채널 광고비: ₩{ad:,} · 공통 마케팅비: ₩{common_mkt:,} · 고정지출: ₩{fixed:,}")
        print(f"  네이버 기여이익: ₩{contrib:,} ({contrib / total * 100:.1f}%)")
        print(f"  영업이익(회사 공통비 전액 반영): ₩{contrib - common_mkt - fixed:,}")


if __name__ == "__main__":
    main()
