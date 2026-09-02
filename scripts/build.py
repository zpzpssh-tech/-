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
import importlib.util
import json
import sys
from collections import defaultdict
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
            to_num(r.get("총매출"), f"sales.csv {i}행 총매출", 0) or to_num(r["매출"], "", 0),
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

    daily_orders, daily_ships = {}, {}
    dop = DATA / "일별주문.csv"
    if dop.exists():
        with open(dop, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                key = r[list(r.keys())[0]].strip()
                daily_orders[key] = to_num(r["주문건수"], "일별주문.csv", 0)
                daily_ships[key] = to_num(r.get("배송건수"), "일별주문.csv", 0)

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

    # ── 일별 광고비 ──
    ad_daily = {}
    adp = DATA / "일별광고비.csv"
    if adp.exists():
        with open(adp, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = {c.lstrip("\ufeff"): v for c, v in r.items()}
                ad_daily[k["날짜"].strip()] = to_num(k["광고비"], "일별광고비.csv", 0)

    # ── 고객 지표 ──
    cust = {}
    cp2 = DATA / "고객지표.csv"
    if cp2.exists():
        with open(cp2, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = list(r.values())
                cust[str(k[0]).strip()] = float(str(k[1]).replace(",", "") or 0)

    # ── 쿠팡 데이터 ──
    cp_daily, cp_cost, cp_opt = [], [], []
    f1 = DATA / "쿠팡_일별.csv"
    if f1.exists():
        with open(f1, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = {c.lstrip("\ufeff"): v for c, v in r.items()}
                cp_daily.append({
                    "날짜": k["날짜"].strip(), "계정": k["계정"].strip(),
                    "주문": to_num(k["주문"], "쿠팡_일별.csv", 0),
                    "판매량": to_num(k["판매량"], "쿠팡_일별.csv", 0),
                    "총매출": to_num(k["총매출"], "쿠팡_일별.csv", 0),
                    "원가": to_num(k["원가"], "쿠팡_일별.csv", 0),
                    "원가추정": to_num(k["원가추정"], "쿠팡_일별.csv", 0),
                    "방문자": to_num(k.get("방문자"), "쿠팡_일별.csv", 0),
                })
    f2 = DATA / "쿠팡_비용.csv"
    if f2.exists():
        with open(f2, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = {c.lstrip("\ufeff"): v for c, v in r.items()}
                cp_cost.append([k["기간"].strip(), k["단위"].strip(), k["계정"].strip(),
                                k["항목"].strip(), to_num(k["금액"], "쿠팡_비용.csv", 0)])
    # 로켓배송(직매입)은 발주서에서 온 별도 계정입니다. 매출·원가만 있고 수수료·물류비는 없습니다.
    f_rkt = DATA / "로켓_일별.csv"
    if f_rkt.exists():
        rkt_n = 0
        with open(f_rkt, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = {c.lstrip("\ufeff"): v for c, v in r.items()}
                cp_daily.append({
                    "날짜": k["날짜"].strip(), "계정": k["계정"].strip(),
                    "주문": to_num(k["발주건수"], "로켓_일별.csv", 0),
                    "판매량": to_num(k["판매량"], "로켓_일별.csv", 0),
                    "총매출": to_num(k["총매출"], "로켓_일별.csv", 0),
                    "원가": to_num(k["원가"], "로켓_일별.csv", 0),
                    "원가추정": 0, "방문자": 0,
                })
                rkt_n += 1
        print(f"  로켓배송 발주서 반영: {rkt_n}일")

    # 쿠팡 광고 리포트가 있는 달은 워크북에 손으로 적은 광고비 대신 리포트를 씁니다.
    # 리포트가 하루 단위 실제 집행 내역이라 더 정확합니다.
    f_ad = DATA / "쿠팡광고.csv"
    ad_rows, ad_cover = [], set()
    if f_ad.exists():
        with open(f_ad, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = {c.lstrip("\ufeff"): v for c, v in r.items()}
                d, acct = k["날짜"].strip(), k["계정"].strip()
                # 로켓 광고는 로켓배송 계정 매출에 붙는 비용이라 그쪽으로 보냅니다
                rocket = k["구분"].strip() == "로켓"
                target = "로켓배송" if rocket else acct
                ad_rows.append([d, "일", target, "광고비(SELLER)",
                                to_num(k["광고비"], "쿠팡광고.csv", 0)])
                ad_cover.add((target, d[:7]))
                ad_cover.add((acct, d[:7]))
    if ad_rows:
        before = sum(c[4] for c in cp_cost
                     if c[3].startswith("광고비") and (c[2], c[0][:7]) in ad_cover)
        cp_cost = [c for c in cp_cost
                   if not (c[3].startswith("광고비") and (c[2], c[0][:7]) in ad_cover)]
        cp_cost += ad_rows
        after = sum(c[4] for c in ad_rows)
        print(f"  쿠팡 광고 리포트 반영: {len({m for _, m in ad_cover})}개월 · "
              f"워크북 {before:,.0f} → 리포트 {after:,.0f} (차이 {after - before:+,.0f})")

    f3 = DATA / "쿠팡_옵션.csv"
    if f3.exists():
        with open(f3, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = {c.lstrip("\ufeff"): v for c, v in r.items()}
                cp_opt.append([k["월"].strip(), k["계정"].strip(), k["상품명"].strip(),
                               k["옵션명"].strip(), to_num(k["매출"], "쿠팡_옵션.csv", 0),
                               to_num(k["주문"], "쿠팡_옵션.csv", 0),
                               to_num(k["판매량"], "쿠팡_옵션.csv", 0),
                               to_num(k["원가합계"], "쿠팡_옵션.csv", 0)])

    # ── 통합 품목별 월 판매량 (재고 발주용) ──
    # 채널마다 상품 이름이 조금씩 달라서, 규칙으로 같은 품목끼리 묶습니다.
    spec = importlib.util.spec_from_file_location("품목분류", ROOT / "scripts" / "품목분류.py")
    CLS = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(CLS)

    override = {}
    ov = DATA / "품목_수정.csv"
    if ov.exists():
        with open(ov, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = {(c or "").lstrip("\ufeff").strip(): (v if isinstance(v, str) else "")
                     for c, v in r.items()}
                if k.get("상품명") and k.get("통합품목"):
                    override[k["상품명"].strip()] = k["통합품목"].strip()

    def group_of(name):
        return override.get((name or "").strip()) or CLS.classify(name)

    name_by_pid = {}
    for pr in products:
        no = (pr.get("상품번호") or "").strip()
        if no:
            name_by_pid[no] = pr.get("정산상품명") or pr.get("상품명") or ""

    items = defaultdict(lambda: {"m": defaultdict(int), "ch": set()})
    seen_names = {}
    op2 = DATA / "옵션판매.csv"
    if op2.exists():
        with open(op2, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = {c.lstrip("\ufeff"): v for c, v in r.items()}
                nm = name_by_pid.get(k["상품번호"].strip(), "")
                # '아치업 깔창: L' 처럼 같이 산 다른 상품(추가구성)은 그 상품으로 셉니다
                add = CLS.addon(k["옵션정보"])
                if add:
                    g = group_of(add[0])
                    seen_names[add[0]] = g
                    var = CLS.variant(add[0] + " " + add[1], g)
                else:
                    g = group_of(nm)
                    seen_names[nm] = g
                    var = CLS.variant(k["옵션정보"], g, nm)
                key = (g, var)
                it = items[key]
                it["m"][k["월"].strip()] += to_num(k["수량"], "옵션판매.csv", 0)
                it["ch"].add("네이버")
    for row in cp_opt:
        m, acct, prod, opt, _rev, _ord, qty, _cg = row
        g = group_of(prod)
        seen_names[prod] = g
        key = (g, CLS.variant(opt, g))
        it = items[key]
        it["m"][m] += int(qty)
        it["ch"].add(acct)

    # 사이즈가 있는 상품은 거의 모든 판매가 사이즈를 답니다. 어쩌다 한두 건만 사이즈가
    # 붙은 품목(슬개건처럼 원래 한쪽·양쪽만 있는 것)은 남의 옵션이 섞인 것이므로 사이즈를 뗍니다.
    sized_ratio = defaultdict(lambda: [0, 0])
    for (g, v), d in items.items():
        q = sum(d["m"].values())
        sized_ratio[g][0] += q
        if " · " in v or CLS.SIZE.fullmatch(v):
            sized_ratio[g][1] += q
    merged = defaultdict(lambda: {"m": defaultdict(int), "ch": set()})
    for (g, v), d in items.items():
        tot, sized = sized_ratio[g]
        if tot and sized / tot < 0.10:
            v = v.split(" · ")[0] if " · " in v else ("구분 없음" if CLS.SIZE.fullmatch(v) else v)
        t = merged[(g, v)]
        for m_, q in d["m"].items():
            t["m"][m_] += q
        t["ch"] |= d["ch"]
    items = merged

    item_rows = [{"품목": g, "변형": v, "채널": sorted(d["ch"]), "월": dict(d["m"])}
                 for (g, v), d in items.items() if sum(d["m"].values()) > 0]
    item_rows.sort(key=lambda x: -sum(x["월"].values()))

    with open(DATA / "품목분류.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["상품명", "통합품목"])
        for nm, g in sorted(seen_names.items(), key=lambda x: (x[1], x[0])):
            w.writerow([nm, g])

    dates = sorted({s[0] for s in sales} | {d["날짜"] for d in cp_daily})
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
        "일별배송": daily_ships,
        "원가": cogs_rows,
        "옵션판매": opt_sales,
        "품목예측": item_rows,
        "광고지표": ad_stats,
        "일별광고비": ad_daily,
        "쿠팡일별": cp_daily,
        "쿠팡비용": cp_cost,
        "쿠팡옵션": cp_opt,
        "고객지표": cust,
        "부가세": settings.get("부가세", {}),
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
    if item_rows:
        multi = sum(1 for r in item_rows if len(r["채널"]) > 1)
        print(f"  통합 품목 {len({r['품목'] for r in item_rows})}종 · 옵션 {len(item_rows)}줄 "
              f"(채널 2개 이상 묶인 줄 {multi}개) → data/품목분류.csv")
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
    if cp_daily:
        print()
        acct_cfg = {a["계정"]: a for a in accounts}
        rng = (dates[0], dates[-1])
        print(f"  {'계정':<12}{'총매출':>15}{'수수료':>13}{'원가':>13}{'물류비':>13}{'광고비':>13}{'남는 돈':>14}")
        for a in accounts:
            name = a["계정"]
            if a.get("채널") != "쿠팡":
                continue
            rows = [d for d in cp_daily if d["계정"] == name and rng[0] <= d["날짜"] <= rng[1]]
            gross = sum(d["총매출"] for d in rows)
            cg = sum(d["원가"] for d in rows)
            orders = sum(d["주문"] for d in rows)
            def cost_of(item):
                return sum(c[4] for c in cp_cost if c[2] == name and c[3] == item
                           and rng[0][:7] <= c[0][:7] <= rng[1][:7])
            fee = cost_of("수수료") or round(gross * float(a.get("수수료율", 0) or 0))
            logi = cost_of("입출고비") or round(orders * float(a.get("건당배송비", 0) or 0))
            coupon = cost_of("쿠폰")
            ad = sum(c[4] for c in cp_cost if c[2] == name and c[3].startswith("광고비")
                     and rng[0][:7] <= c[0][:7] <= rng[1][:7])
            left = gross - fee - cg - logi - coupon - ad
            print(f"  {name:<12}{gross:>15,}{fee:>13,}{cg:>13,}{logi:>13,}{ad:>13,}{left:>14,}")

    if not costs:
        print("  고정지출·마케팅비가 비어 있어 영업이익은 아직 계산하지 않습니다.")
    else:
        from calendar import monthrange

        def prorate(kind, has_acct):
            """월 단위 비용을 기간에 걸친 날짜 수만큼 나눠 더합니다."""
            total = 0.0
            for ym, k, _, acct, amt in costs:
                if k != kind or bool(acct) != has_acct:
                    continue
                y, m = int(ym[:4]), int(ym[5:7])
                dim = monthrange(y, m)[1]
                ms, me = f"{ym}-01", f"{ym}-{dim:02d}"
                a = max(dates[0], ms)
                b = min(dates[-1], me)
                if a > b:
                    continue
                span = (int(b[8:]) - int(a[8:]) + 1)
                total += amt * span / dim
            return round(total)

        cg = sum(r[3] for r in cogs_rows if dates[0] <= r[0] <= dates[-1])
        orders = sum(v for k, v in daily_orders.items() if dates[0] <= k <= dates[-1])
        ships = sum(v for k, v in daily_ships.items() if dates[0] <= k <= dates[-1]) or orders
        shipping = ships * ship_unit
        ad = prorate("마케팅비", True)
        common_mkt = prorate("마케팅비", False)
        fixed = prorate("고정지출", False)
        contrib = total - cg - shipping - ad
        print(f"  택배비: ₩{shipping:,} (배송 {ships:,}건 × ₩{ship_unit:,}) · 주문은 {orders:,}건")
        print(f"  채널 광고비: ₩{ad:,} · 공통 마케팅비: ₩{common_mkt:,} · 고정지출: ₩{fixed:,}")
        print(f"  네이버 기여이익: ₩{contrib:,} ({contrib / total * 100:.1f}%)")
        print(f"  영업이익(회사 공통비 전액 반영): ₩{contrib - common_mkt - fixed:,}")


if __name__ == "__main__":
    main()
