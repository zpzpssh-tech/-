"""
대시보드 빌드 스크립트
----------------------
data/ 폴더의 CSV·설정을 읽어서 dashboard/index.html 한 파일로 만듭니다.
만들어진 파일은 인터넷 없이도 브라우저에서 바로 열립니다.

실행:  python3 scripts/build.py

데이터 파일 형식 (첫 줄은 열 이름):
  data/sales.csv     날짜, 채널, 계정, 상품코드, 주문건수, 판매수량, 매출
  data/products.csv  상품코드, 상품명, 카테고리, 판매가, 원가, 포장비
  data/costs.csv     월(YYYY-MM), 구분(고정지출|마케팅비), 항목, 계정(비우면 공통), 금액
  data/settings.json 계정별 수수료율·건당 배송비
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


def read_csv(path, required):
    if not path.exists():
        sys.exit(f"[오류] 파일이 없습니다: {path}")
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit(f"[오류] 파일이 비어 있습니다: {path}")
    missing = [c for c in required if c not in rows[0]]
    if missing:
        sys.exit(f"[오류] {path.name}에 열이 없습니다: {', '.join(missing)}\n"
                 f"       현재 열: {', '.join(rows[0].keys())}")
    return rows


def to_int(value, where):
    s = str(value).replace(",", "").replace("₩", "").strip()
    if s == "":
        return 0
    try:
        return int(round(float(s)))
    except ValueError:
        sys.exit(f"[오류] 숫자가 아닌 값이 있습니다 ({where}): '{value}'")


def main():
    settings = json.loads((DATA / "settings.json").read_text(encoding="utf-8"))
    account_names = {a["계정"] for a in settings["계정"]}

    products = read_csv(DATA / "products.csv", ["상품코드", "상품명", "카테고리", "판매가", "원가", "포장비"])
    product_map = {}
    for p in products:
        code = p["상품코드"].strip()
        product_map[code] = {
            "상품명": p["상품명"].strip(),
            "카테고리": p["카테고리"].strip(),
            "판매가": to_int(p["판매가"], f"products.csv {code} 판매가"),
            "원가": to_int(p["원가"], f"products.csv {code} 원가"),
            "포장비": to_int(p["포장비"], f"products.csv {code} 포장비"),
        }

    sales_rows = read_csv(DATA / "sales.csv", ["날짜", "채널", "계정", "상품코드", "주문건수", "판매수량", "매출"])
    sales = []
    unknown_products, unknown_accounts = set(), set()
    for i, r in enumerate(sales_rows, start=2):
        code = r["상품코드"].strip()
        acct = r["계정"].strip()
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
            to_int(r["주문건수"], f"sales.csv {i}행 주문건수"),
            to_int(r["판매수량"], f"sales.csv {i}행 판매수량"),
            to_int(r["매출"], f"sales.csv {i}행 매출"),
        ])
    if unknown_products:
        sys.exit(f"[오류] products.csv에 없는 상품코드가 sales.csv에 있습니다: {', '.join(sorted(unknown_products))}")
    if unknown_accounts:
        sys.exit(f"[오류] settings.json에 없는 계정이 sales.csv에 있습니다: {', '.join(sorted(unknown_accounts))}")

    cost_rows = read_csv(DATA / "costs.csv", ["월", "구분", "항목", "계정", "금액"])
    costs = []
    for i, r in enumerate(cost_rows, start=2):
        kind = r["구분"].strip()
        if kind not in ("고정지출", "마케팅비"):
            sys.exit(f"[오류] costs.csv {i}행 구분은 '고정지출' 또는 '마케팅비'여야 합니다: '{kind}'")
        acct = r["계정"].strip()
        if acct and acct not in account_names:
            sys.exit(f"[오류] costs.csv {i}행 계정이 settings.json에 없습니다: '{acct}'")
        costs.append([r["월"].strip(), kind, r["항목"].strip(), acct, to_int(r["금액"], f"costs.csv {i}행 금액")])

    dates = sorted({s[0] for s in sales})
    payload = {
        "브랜드": settings.get("브랜드", ""),
        "예시데이터": bool(settings.get("예시데이터", False)),
        "생성시각": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "기간": {"시작": dates[0], "끝": dates[-1], "일수": len(dates)},
        "계정": settings["계정"],
        "상품": product_map,
        "매출": sales,       # [날짜, 계정, 상품코드, 주문건수, 판매수량, 매출]
        "비용": costs,       # [월, 구분, 항목, 계정, 금액]
    }

    template = TEMPLATE.read_text(encoding="utf-8")
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = template.replace("__DASHBOARD_DATA__", data_json)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")

    total = sum(s[5] for s in sales)
    print(f"대시보드 생성 완료 → {OUT.relative_to(ROOT)}")
    print(f"  기간: {dates[0]} ~ {dates[-1]} ({len(dates)}일)")
    print(f"  매출 행: {len(sales):,}  · 상품 {len(product_map)}개 · 비용 항목 {len(costs)}건")
    print(f"  총매출: ₩{total:,}")


if __name__ == "__main__":
    main()
