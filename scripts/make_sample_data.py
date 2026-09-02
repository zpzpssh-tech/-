"""
샘플 데이터 생성기
------------------
실제 정산 파일이 준비되기 전까지 대시보드 구조를 확인하기 위한 "예시 데이터"를 만듭니다.
실제 데이터가 준비되면 data/ 폴더의 CSV를 실제 파일로 바꾸고, 이 스크립트는 지우셔도 됩니다.

실행:  python3 scripts/make_sample_data.py
"""
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
random.seed(20260902)

START = date(2026, 1, 1)
END = date(2026, 9, 1)  # 244일

# ── 상품 (판매가·원가는 예시값) ─────────────────────────────────────────
PRODUCTS = [
    # 코드,      이름,                    카테고리, 판매가, 원가(제조+운송+관세), 포장비
    ("KN-01", "무릎보호대 스탠다드",       "무릎",   19900,  6200, 500),
    ("KN-02", "무릎보호대 프리미엄 힌지",  "무릎",   34900, 12800, 700),
    ("EL-01", "팔꿈치보호대 테니스엘보",   "팔꿈치", 14900,  4100, 400),
    ("WR-01", "손목보호대 엄지고정",       "손목",   12900,  3600, 400),
    ("WR-02", "손목보호대 얇은형 2입",     "손목",    9900,  4900, 400),  # 마진 얇은 상품
    ("BK-01", "허리보호대 복대형",         "허리",   29900,  9800, 700),
    ("IN-01", "발바닥 깔창 아치서포트",    "깔창",   16900,  5200, 500),
    ("IN-02", "발바닥 깔창 젤쿠션",        "깔창",   11900,  7400, 500),  # 마진 얇은 상품
]

# ── 계정별 하루 평균 주문 규모와 성장 추세 (예시) ───────────────────────
ACCOUNTS = {
    # 계정:           (채널,   하루평균주문, 후반기 성장배수)
    "네이버":        ("네이버", 240, 1.15),
    "올투게더나우":  ("쿠팡",   40, 1.05),
    "휴책":          ("쿠팡",   70, 2.6),   # 급성장 계정
    "유큐어":        ("쿠팡",   75, 1.0),
    "기타사이트":    ("기타",   35, 1.1),
}

# 계정마다 잘 팔리는 상품이 다르다고 가정한 가중치
MIX = {
    "네이버":       [3, 2, 2, 2, 1, 2, 2, 1],
    "올투게더나우": [2, 1, 1, 3, 2, 1, 1, 1],
    "휴책":         [3, 3, 1, 1, 1, 2, 1, 1],
    "유큐어":       [1, 1, 2, 2, 3, 1, 2, 2],
    "기타사이트":   [2, 2, 1, 1, 1, 2, 2, 1],
}


def write_products():
    with open(DATA / "products.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["상품코드", "상품명", "카테고리", "판매가", "원가", "포장비"])
        for row in PRODUCTS:
            w.writerow(row)


def write_sales():
    days = (END - START).days + 1
    rows = []
    for i in range(days):
        d = START + timedelta(days=i)
        progress = i / (days - 1)
        weekday_factor = 0.75 if d.weekday() >= 5 else 1.0
        for acct, (channel, base, growth) in ACCOUNTS.items():
            scale = base * (1 + (growth - 1) * progress) * weekday_factor
            scale *= random.uniform(0.7, 1.3)
            weights = MIX[acct]
            # 하루 주문을 상품별로 나눔
            total_orders = max(1, int(round(scale)))
            picks = random.choices(range(len(PRODUCTS)), weights=weights, k=total_orders)
            counts = {}
            for p in picks:
                counts[p] = counts.get(p, 0) + 1
            for p, orders in counts.items():
                code, _, _, price, _, _ = PRODUCTS[p]
                qty = orders + sum(1 for _ in range(orders) if random.random() < 0.12)  # 일부 2개 구매
                # 채널별 할인율 차이 (예시)
                discount = {"네이버": 0.06, "쿠팡": 0.10, "기타": 0.03}[channel]
                revenue = int(round(qty * price * (1 - discount)))
                rows.append([d.isoformat(), channel, acct, code, orders, qty, revenue])
    with open(DATA / "sales.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["날짜", "채널", "계정", "상품코드", "주문건수", "판매수량", "매출"])
        w.writerows(rows)
    return len(rows)


def write_costs():
    months = []
    d = START
    while d <= END:
        months.append(d.strftime("%Y-%m"))
        d = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
    rows = []
    for m in months:
        # 고정지출 (계정 비워두면 회사 공통)
        rows += [
            [m, "고정지출", "인건비", "", 16500000],
            [m, "고정지출", "창고·사무실 임대", "", 4200000],
            [m, "고정지출", "물류 시스템·솔루션", "", 1300000],
            [m, "고정지출", "기타 운영비", "", 2500000],
        ]
        # 마케팅비 (계정별로 나눠 적으면 계정 이익에 반영)
        rows += [
            [m, "마케팅비", "네이버 검색광고", "네이버", 4200000],
            [m, "마케팅비", "쿠팡 광고", "휴책", 3100000],
            [m, "마케팅비", "쿠팡 광고", "유큐어", 1500000],
            [m, "마케팅비", "쿠팡 광고", "올투게더나우", 600000],
            [m, "마케팅비", "인플루언서·콘텐츠 제작", "", 900000],
        ]
    with open(DATA / "costs.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["월", "구분", "항목", "계정", "금액"])
        w.writerows(rows)


def write_settings():
    settings = {
        "브랜드": "올투게더나우",
        "예시데이터": True,
        "메모": "수수료율과 건당 배송비는 예시값입니다. 실제 정산 기준으로 바꿔 주세요.",
        "계정": [
            {"계정": "네이버",       "채널": "네이버", "수수료율": 0.055, "건당배송비": 2800},
            {"계정": "올투게더나우", "채널": "쿠팡",   "수수료율": 0.108, "건당배송비": 2800},
            {"계정": "휴책",         "채널": "쿠팡",   "수수료율": 0.108, "건당배송비": 2800},
            {"계정": "유큐어",       "채널": "쿠팡",   "수수료율": 0.108, "건당배송비": 2800},
            {"계정": "기타사이트",   "채널": "기타",   "수수료율": 0.150, "건당배송비": 2800},
        ],
    }
    with open(DATA / "settings.json", "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    DATA.mkdir(exist_ok=True)
    write_products()
    n = write_sales()
    write_costs()
    write_settings()
    print(f"샘플 데이터 생성 완료: sales.csv {n}행, products.csv {len(PRODUCTS)}개 상품")
