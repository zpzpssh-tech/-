"""
데모(연습용) 데이터
------------------
API 키가 없어도 프로그램을 눌러볼 수 있게 가짜 주문을 만듭니다.
상품명·옵션은 실제 판매 데이터에서 많이 팔린 것을 참고했고, 고객 정보는 모두 가짜입니다.
"""
import random
from datetime import timedelta

import store

SKUS = [
    # 코드, 이름, 분류, 안전재고, 원가
    ("KNEE-ST-BK", "슬개건 스트랩 무릎보호대 블랙", "무릎", 300, 2200),
    ("KNEE-ST-BL", "슬개건 스트랩 무릎보호대 블루", "무릎", 40, 2200),
    ("KNEE-4G-M", "4세대 영자 무릎보호대 M", "무릎", 30, 4000),
    ("KNEE-4G-XL", "4세대 영자 무릎보호대 XL", "무릎", 20, 4000),
    ("BALL", "마사지볼 (사은품)", "부속", 200, 350),
    ("WRIST-TFCC", "TFCC 손목보호대 일자형", "손목", 150, 1800),
    ("WRIST-ZZ-BK", "쫀쫀 손목보호대 블랙 (낱개)", "손목", 80, 900),
    ("ELBOW-BK", "엘보 팔꿈치보호대 블랙 FREE", "팔꿈치", 120, 2100),
    ("ELBOW-ZZ", "쫀쫀 엘보 팔꿈치보호대 30x20", "팔꿈치", 80, 1500),
    ("WAIST-BR-M", "디스크 바른요 허리보호대 회색 M", "허리", 30, 7800),
    ("WAIST-BR-L", "디스크 바른요 허리보호대 회색 L", "허리", 40, 7800),
    ("WAIST-BR-XL", "디스크 바른요 허리보호대 회색 XL", "허리", 60, 7800),
    ("WAIST-MD-L", "의료용 허리보호대 L", "허리", 20, 8200),
    ("WAIST-DP-L", "이중압박 허리보호대 L", "허리", 20, 7400),
    ("SHOULDER", "어깨 보호대 회전근개 밴드", "어깨", 20, 5200),
    ("ARCH", "주상골 아치패드 (1세트)", "발", 120, 1300),
]

# 계정: [(상품키, 상품명, 옵션, 하루 평균 주문수, 판매가, 매핑 or None)]  — None은 '미매칭' 연습용
CATALOG = {
    "NAV": [
        ("5799070116|BK2", "올투게더나우 무릎보호대 슬개건 슬개골 러닝 보호대", "색상: 블랙 + 마사지볼 / 수량: 양쪽", 9.0, 29800, [("KNEE-ST-BK", 2), ("BALL", 1)]),
        ("5799070116|BK1", "올투게더나우 무릎보호대 슬개건 슬개골 러닝 보호대", "색상: 블랙 + 마사지볼 / 수량: 한쪽", 1.6, 17800, [("KNEE-ST-BK", 1), ("BALL", 1)]),
        ("5799070116|BL2", "올투게더나우 무릎보호대 슬개건 슬개골 러닝 보호대", "색상: 블루 + 마사지볼 / 수량: 양쪽", 0.6, 29800, [("KNEE-ST-BL", 2), ("BALL", 1)]),
        ("6379382624|2", "올투게더나우 손목보호대 손목 팔목 아대 TFCC 밴드", "수량: 일자형 양쪽", 2.8, 23800, [("WRIST-TFCC", 2)]),
        ("6379382624|1", "올투게더나우 손목보호대 손목 팔목 아대 TFCC 밴드", "수량: 일자형 한쪽", 2.0, 13900, [("WRIST-TFCC", 1)]),
        ("8605463656|BK", "물리치료사가 판매하는 올투게더나우 쫀쫀 손목 보호대 2p 1set", "색상: 블랙", 1.2, 15900, [("WRIST-ZZ-BK", 2)]),
        ("6362662029|M", "디스크 바른요 허리보호대 허리 복대", "사이즈: 회색M", 0.8, 39800, [("WAIST-BR-M", 1)]),
        ("6362662029|L", "디스크 바른요 허리보호대 허리 복대", "사이즈: 회색L", 1.2, 39800, [("WAIST-BR-L", 1)]),
        ("6362662029|XL", "디스크 바른요 허리보호대 허리 복대", "사이즈: 회색XL", 1.2, 39800, [("WAIST-BR-XL", 1)]),
        ("5798987044|1", "올투게더나우 팔꿈치보호대 테니스 배드민턴 엘보우", "색상: 블랙 한팔 + 마사지볼", 1.1, 16800, [("ELBOW-BK", 1), ("BALL", 1)]),
        ("5798987044|2", "올투게더나우 팔꿈치보호대 테니스 배드민턴 엘보우", "색상: 블랙 양팔 + 마사지볼", 0.6, 29800, [("ELBOW-BK", 2), ("BALL", 1)]),
        ("6520261103|1p", "올투게더나우 어깨 보호대 밴드 회전근개 쇄골 아대", "수량: 1p", 0.5, 25900, None),
        ("5524199797|1", "올투게더나우 발아치패드 주상골 발바닥 패드", "수량: 1세트", 0.5, 12900, [("ARCH", 1)]),
    ],
    "CPG": [
        ("70011001", "올투게더나우 팔꿈치 엘보 보호대", "블랙, 1개, FREE", 3.5, 14900, [("ELBOW-BK", 1)]),
        ("70011002", "올투게더나우 팔꿈치 엘보 보호대", "블랙, 2개, FREE", 0.9, 26900, [("ELBOW-BK", 2)]),
        ("70012001", "올투게더나우 4세대 영자 무릎보호대 아대 블랙", "M, 2개", 0.4, 33900, [("KNEE-4G-M", 2)]),
        ("70012002", "올투게더나우 4세대 영자 무릎보호대 아대 블랙", "XL, 1개", 0.3, 18900, [("KNEE-4G-XL", 1)]),
        ("70013001", "올투게더나우 허리보호대 복대", "L, 1개", 0.4, 32900, [("WAIST-BR-L", 1)]),
        ("70013002", "올투게더나우 허리보호대 복대", "XL, 1개", 0.4, 32900, None),
    ],
    "HCK": [
        ("80021001", "휴책 보호대연구소 무릎보호대 슬개건 슬개골 보호대", "2개, 블랙", 7.0, 27900, [("KNEE-ST-BK", 2)]),
        ("80021002", "휴책 보호대연구소 무릎보호대 슬개건 슬개골 보호대", "1개, 블랙", 0.9, 15900, [("KNEE-ST-BK", 1)]),
        ("80022001", "보호대연구소 쫀쫀 손목 보호대 아대 2p", "블랙, 1세트, free", 0.9, 15900, [("WRIST-ZZ-BK", 2)]),
        ("80023001", "휴책 보호대연구소 의료용 허리보호대 복대", "1개, L", 0.4, 35900, [("WAIST-MD-L", 1)]),
    ],
    "YCU": [
        ("90031001", "유큐어 쫀쫀 엘보 팔꿈치 보호대 엘보우 압박 아대", "30 x 20 cm, 2개", 2.3, 19900, [("ELBOW-ZZ", 2)]),
        ("90031002", "유큐어 쫀쫀 엘보 팔꿈치 보호대 엘보우 압박 아대", "30 x 20 cm, 1개", 1.1, 11900, [("ELBOW-ZZ", 1)]),
        ("90032001", "유큐어 팔꿈치보호대 전완근 엘보 압박 아대", "FREE, 1개", 1.6, 13900, [("ELBOW-BK", 1)]),
        ("90033001", "유큐어 손목보호대 TFCC 팔목 아대 일자형", "29.5 x 5 cm, 2개", 1.5, 21900, [("WRIST-TFCC", 2)]),
        ("90033002", "유큐어 손목보호대 TFCC 팔목 아대 일자형", "29.5 x 5 cm, 1개", 1.1, 12900, [("WRIST-TFCC", 1)]),
        ("90034001", "유큐어 이중압박 허리 보호대 요추 척추 복대", "1개, L", 0.3, 34900, [("WAIST-DP-L", 1)]),
    ],
}
ROCKET = ("RK-18464826", "올투게더나우 무릎 보호대, 블랙", "로켓배송 발주", 6175, [("KNEE-ST-BK", 1)])

# 창고별로 남겨둘 재고 일수 (일부러 몇 개는 부족하게 → 경고 화면 연습용)
COVER = {"HQ": 45, "NFA": 18, "RG-HCK": 20, "RG-YCU": 20}
LOW = {("RG-HCK", "KNEE-ST-BK"): 3.5, ("NFA", "WRIST-TFCC"): 4, ("HQ", "WAIST-BR-XL"): 6,
       ("RG-YCU", "ELBOW-ZZ"): 5}

SURNAMES = "김이박최정강조윤장임한오서신권황안송류홍"
GIVEN = "민서지수하윤도현예준서연지호수빈현우유진채원시우은서건우"
ADDR = ["서울 강남구 테헤란로 123", "서울 마포구 월드컵북로 45", "경기 성남시 분당구 판교역로 166",
        "부산 해운대구 센텀중앙로 79", "대구 수성구 동대구로 300", "인천 연수구 송도과학로 32",
        "광주 서구 상무중앙로 61", "대전 유성구 대학로 99", "경기 수원시 영통구 광교중앙로 140",
        "울산 남구 삼산로 274", "경기 고양시 일산동구 중앙로 1275", "제주 제주시 연북로 60"]


def _name(r):
    return r.choice(SURNAMES) + "*" + r.choice(GIVEN)


def _pick(r, items):
    total = sum(i[3] for i in items)
    x = r.uniform(0, total)
    for it in items:
        x -= it[3]
        if x <= 0:
            return it
    return items[-1]


def _ship_for(r, acc):
    if acc == "NAV":
        return store.SHIP_NFA if r.random() < 0.8 else store.SHIP_SELF   # 실제 비율(약 8:2) 참고
    return {"CPG": store.SHIP_SELF, "HCK": store.SHIP_GROWTH, "YCU": store.SHIP_GROWTH}[acc]


def _make_line(r, acc, it, when, seq, status=None):
    key, pname, opt, _, price, _m = it
    ship = _ship_for(r, acc)
    qty = 1 if r.random() < 0.9 else 2
    n = _name(r)
    if status is None:
        status = store.ST_PARTNER if ship in (store.SHIP_NFA, store.SHIP_GROWTH) else store.ST_NEW
    order_no = f"{when:%Y%m%d}{seq:06d}" if acc == "NAV" else f"3{when:%m%d}{seq:07d}"
    return {
        "account": acc, "line_id": f"{order_no}{'' if acc == 'NAV' else '-' + key}",
        "order_no": order_no, "ordered_at": when.strftime("%Y-%m-%d %H:%M"),
        "item_key": key, "product_name": pname, "option_name": opt, "qty": qty, "amount": price * qty,
        "buyer": n, "receiver": n, "phone": f"050-{r.randint(1000, 9999)}-{r.randint(1000, 9999)}",
        "zipcode": f"{r.randint(10000, 63999)}", "address": f"{r.choice(ADDR)} {r.randint(1, 30)}층",
        "memo": r.choice(["", "", "", "문 앞에 놓아주세요", "경비실에 맡겨주세요"]),
        "ship_type": ship, "status": status, "channel_status": "데모",
    }


def seed(days=30):
    """연습용 데이터를 처음부터 다시 만듭니다."""
    r = random.Random(20261125)
    store.reset_all()
    for code, name, cat, safety, cost in SKUS:
        store.upsert_sku({"code": code, "name": name, "category": cat, "safety": safety, "cost": cost})
    for acc, items in CATALOG.items():
        for it in items:
            if it[5]:
                store.set_mapping(acc, it[0], [{"sku": s, "qty": q} for s, q in it[5]])
    store.set_mapping("RKT", ROCKET[0], [{"sku": s, "qty": q} for s, q in ROCKET[4]])

    now = store.now()
    start = (now - timedelta(days=days)).replace(hour=9, minute=0)
    lines, seq = [], 1
    for d in range(days + 1):
        day = start + timedelta(days=d)
        is_today = d == days
        for acc, items in CATALOG.items():
            daily = sum(i[3] for i in items)
            n = max(0, int(r.gauss(daily, daily ** 0.5)))
            if is_today:
                n = int(n * min(1, (now.hour + 1) / 24) + 2)
            for _ in range(n):
                when = day.replace(hour=0) + timedelta(minutes=r.randint(0, 24 * 60 - 1))
                if when > now:
                    when = now - timedelta(minutes=r.randint(1, 300))
                ln = _make_line(r, acc, _pick(r, items), when, seq)
                seq += 1
                age_h = (now - when).total_seconds() / 3600
                if ln["ship_type"] == store.SHIP_SELF:
                    # 오래된 판매자배송 주문은 이미 출고된 것으로
                    if age_h > 30:
                        ln.update(status=store.ST_DONE, courier="CJ대한통운",
                                  tracking=f"5{r.randint(10**10, 10**11 - 1)}", sent=1,
                                  shipped_at=(when + timedelta(hours=r.randint(4, 26))).strftime("%Y-%m-%d %H:%M"))
                    elif age_h > 16 and r.random() < 0.6:
                        ln["status"] = store.ST_CONFIRM
                if r.random() < 0.025:
                    ln["status"] = store.ST_CANCEL
                lines.append(ln)
        if d % 6 == 2 or is_today:   # 로켓배송 발주 (며칠에 한 번)
            key, pname, opt, price, _ = ROCKET
            q = r.choice([30, 40, 50, 60])
            when = day.replace(hour=10, minute=r.randint(0, 50))
            done = not is_today
            lines.append({
                "account": "RKT", "line_id": f"PO{when:%Y%m%d}", "order_no": f"PO{when:%Y%m%d}{r.randint(100, 999)}",
                "ordered_at": when.strftime("%Y-%m-%d %H:%M"), "item_key": key, "product_name": pname,
                "option_name": opt, "qty": q, "amount": price * q, "buyer": "쿠팡(주)", "receiver": "쿠팡 고양FC",
                "address": "경기 고양시 덕양구 (쿠팡 물류센터)", "ship_type": store.SHIP_ROCKET,
                "status": store.ST_DONE if done else store.ST_NEW, "channel_status": "발주서",
                "shipped_at": (when + timedelta(days=1)).strftime("%Y-%m-%d %H:%M") if done else ""})
    lines.sort(key=lambda x: x["ordered_at"])

    # 주문을 저장하기 전에, 팔린 만큼 + 남길 만큼 미리 입고해 둡니다 (재고가 마이너스가 되지 않게)
    m = store.mapping_dict()
    use = {}
    for ln in lines:
        if ln["status"] == store.ST_CANCEL:
            continue
        wh = store.wh_for(ln["account"], ln["ship_type"])
        for sku, q in m.get((ln["account"], ln["item_key"]), []):
            use[(wh, sku)] = use.get((wh, sku), 0) + q * ln["qty"]
    t0 = (start - timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
    t1 = (start - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    hq_in = {}
    for (wh, sku), used in use.items():
        daily = used / days
        keep = int(daily * LOW.get((wh, sku), COVER[wh])) + (0 if (wh, sku) in LOW else r.randint(5, 30))
        need = used + keep
        if wh == "HQ":
            hq_in[sku] = hq_in.get(sku, 0) + need
        else:
            hq_in[sku] = hq_in.get(sku, 0) + need
            store.add_movement(sku, "HQ", -need, "이동출고", f"→ {wh} 입고", ts=t1)
            store.add_movement(sku, wh, need, "이동입고", "본사창고에서 입고", ts=t1)
    for code, *_ in SKUS:
        extra = r.randint(40, 200) if (("HQ", code) not in LOW) else 0
        if code == "SHOULDER":
            extra = 115
        total = hq_in.get(code, 0) + extra
        if total:
            store.add_movement(code, "HQ", total, "입고", "중국 공장 입고 (데모)", ts=t0)
    # 아직 매핑 안 된 어깨보호대도 N배송창고에 일부 보내 둡니다 (매핑하면 바로 차감되는 걸 볼 수 있게)
    store.add_movement("SHOULDER", "HQ", -30, "이동출고", "→ NFA 입고", ts=t1)
    store.add_movement("SHOULDER", "NFA", 30, "이동입고", "본사창고에서 입고", ts=t1)
    store.upsert_orders(lines)
    store.log(f"데모 데이터 생성: 주문 {len(lines)}건, SKU {len(SKUS)}개", "info")
    store.set_meta("last_collect", store.now_str())
    store.set_meta("demo_seq", seq)


def new_orders():
    """'지금 수집'을 누르면 새 주문 몇 건이 들어온 것처럼 만듭니다."""
    r = random.Random()
    seq = store.get_meta("demo_seq", 900000) or 900000
    now = store.now()
    lines = []
    for acc, items in CATALOG.items():
        for _ in range(r.choice([0, 1, 1, 2, 3])):
            lines.append(_make_line(r, acc, _pick(r, items), now - timedelta(minutes=r.randint(0, 9)), seq))
            seq += 1
    store.set_meta("demo_seq", seq)
    return lines
