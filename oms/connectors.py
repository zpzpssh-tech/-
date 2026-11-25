"""
쇼핑몰 연결 (네이버 커머스API · 쿠팡 WING 오픈API)
-------------------------------------------------
쇼핑몰마다 '주문 가져오기 / 발주확인 / 송장 보내기' 방식이 달라서,
여기서 각 쇼핑몰 말투를 우리 프로그램 공통 말투(주문 한 줄 = dict)로 바꿔 줍니다.

⚠ 이 파일의 실제 API 호출은 각 쇼핑몰 공개 문서대로 작성했지만,
  실제 API 키로는 아직 시험하지 않았습니다. 처음 연결할 때 화면의 '연결 테스트'로 먼저 확인하세요.
  (키가 없으면 데모 모드로 돌아갑니다)

필요한 키 (설정 화면 또는 oms/설정/계정.json)
  네이버  : 애플리케이션 ID(client_id), 시크릿(client_secret)  ← 커머스API센터에서 발급
           ※ 네이버 서명에 bcrypt가 필요합니다:  pip install bcrypt
  쿠팡    : 업체코드(vendor_id), Access Key, Secret Key        ← WING > 판매자정보 > 오픈API
"""
import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import store

KST = timezone(timedelta(hours=9))

# 택배사 이름 → 쇼핑몰 코드 (네이버·쿠팡 공통으로 쓰이는 코드)
COURIERS = {
    "CJ대한통운": "CJGLS",
    "한진택배": "HANJIN",
    "롯데택배": "HYUNDAI",     # 롯데택배는 옛 이름(현대택배) 코드를 그대로 씁니다
    "우체국택배": "EPOST",
    "로젠택배": "LOGEN",
    "경동택배": "KDEXP",
}


class ApiError(Exception):
    pass


def _http(method, url, headers=None, body=None, form=False, timeout=20):
    data = None
    headers = dict(headers or {})
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json;charset=UTF-8"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8")
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "ignore")[:400]
        raise ApiError(f"{e.code} {msg}")
    except urllib.error.URLError as e:
        raise ApiError(f"접속 실패: {e.reason}")


def _kst(s):
    """'2026-11-25T10:20:30.0+09:00' 같은 시각을 '2026-11-25 10:20' 으로."""
    if not s:
        return store.now_str()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return s[:16].replace("T", " ")


# ═════════════════════════════════ 네이버 ═════════════════════════════════

class Naver:
    BASE = "https://api.commerce.naver.com/external"
    STATUS = {   # 네이버 상품주문 상태 → 우리 상태
        "PAYED": store.ST_NEW, "DELIVERING": store.ST_DONE, "DELIVERED": store.ST_DONE,
        "PURCHASE_DECIDED": store.ST_DONE, "EXCHANGED": store.ST_DONE,
        "CANCELED": store.ST_CANCEL, "RETURNED": store.ST_CANCEL, "CANCELED_BY_NOPAYMENT": store.ST_CANCEL,
    }

    def __init__(self, account, cfg):
        self.account, self.cfg = account, cfg
        self._token, self._exp = None, 0

    def token(self):
        if self._token and time.time() < self._exp - 60:
            return self._token
        try:
            import bcrypt
        except ImportError:
            raise ApiError("네이버 연결에는 bcrypt가 필요합니다. 터미널에서  pip install bcrypt  를 실행해 주세요")
        cid, secret = self.cfg["client_id"], self.cfg["client_secret"]
        ts = str(int(time.time() * 1000))
        hashed = bcrypt.hashpw(f"{cid}_{ts}".encode(), secret.encode())
        sign = base64.b64encode(hashed).decode()
        r = _http("POST", f"{self.BASE}/v1/oauth2/token", body={
            "client_id": cid, "timestamp": ts, "client_secret_sign": sign,
            "grant_type": "client_credentials", "type": "SELF"}, form=True)
        self._token, self._exp = r["access_token"], time.time() + int(r.get("expires_in", 3600))
        return self._token

    def _h(self):
        return {"Authorization": f"Bearer {self.token()}"}

    def test(self):
        self.token()
        return "토큰 발급 성공"

    def collect(self, since):
        """since 이후 바뀐 상품주문을 가져옵니다. 네이버는 한 번에 24시간까지만 조회돼서 하루씩 나눕니다."""
        ids, start, end = [], since, datetime.now(KST)
        while start < end:
            frm = start.isoformat(timespec="milliseconds")
            to = min(start + timedelta(hours=24), end).isoformat(timespec="milliseconds")
            q = urllib.parse.urlencode({"lastChangedFrom": frm, "lastChangedTo": to})
            r = _http("GET", f"{self.BASE}/v1/pay-order/seller/product-orders/last-changed-statuses?{q}",
                      headers=self._h())
            for s in (r.get("data") or {}).get("lastChangeStatuses", []):
                ids.append(s["productOrderId"])
            start += timedelta(hours=24)
        lines = []
        ids = list(dict.fromkeys(ids))
        for i in range(0, len(ids), 300):     # 상세 조회는 300건씩
            r = _http("POST", f"{self.BASE}/v1/pay-order/seller/product-orders/query",
                      headers=self._h(), body={"productOrderIds": ids[i:i + 300]})
            for d in r.get("data") or []:
                ln = self._line(d)
                if ln:
                    lines.append(ln)
        return lines

    def _line(self, d):
        o, p = d.get("order") or {}, d.get("productOrder") or {}
        st = p.get("productOrderStatus")
        if st == "PAYMENT_WAITING":
            return None
        status = self.STATUS.get(st, store.ST_NEW)
        if status == store.ST_NEW and p.get("placeOrderStatus") == "OK":
            status = store.ST_CONFIRM
        attr = p.get("deliveryAttributeType") or ""
        nfa_attrs = self.cfg.get("n배송_속성") or ["ARRIVAL_GUARANTEE"]
        ship = store.SHIP_NFA if attr in nfa_attrs else store.SHIP_SELF
        if ship == store.SHIP_NFA and status not in (store.ST_CANCEL,):
            status = store.ST_PARTNER     # N배송은 풀필먼트 창고에서 알아서 나갑니다
        addr = p.get("shippingAddress") or {}
        dlv = d.get("delivery") or {}
        option_key = p.get("optionCode") or p.get("optionManageCode") or p.get("productOption") or ""
        return {
            "account": self.account, "line_id": str(p.get("productOrderId")),
            "order_no": str(o.get("orderId", "")), "ordered_at": _kst(o.get("paymentDate") or o.get("orderDate")),
            "item_key": f"{p.get('originalProductId') or p.get('productId')}|{option_key}",
            "product_name": p.get("productName", ""), "option_name": p.get("productOption", ""),
            "qty": p.get("quantity", 1), "amount": p.get("totalPaymentAmount", 0),
            "buyer": o.get("ordererName", ""), "receiver": addr.get("name", ""),
            "phone": addr.get("tel1", ""), "zipcode": addr.get("zipCode", ""),
            "address": f"{addr.get('baseAddress', '')} {addr.get('detailedAddress', '')}".strip(),
            "memo": p.get("shippingMemo", ""), "ship_type": ship, "status": status,
            "channel_status": st, "tracking": dlv.get("trackingNumber", ""),
            "shipped_at": _kst(dlv.get("sendDate")) if dlv.get("sendDate") else "",
        }

    def confirm(self, orders):
        ids = [o["line_id"] for o in orders]
        _http("POST", f"{self.BASE}/v1/pay-order/seller/product-orders/confirm",
              headers=self._h(), body={"productOrderIds": ids})

    def dispatch(self, orders):
        now = datetime.now(KST).isoformat(timespec="milliseconds")
        body = {"dispatchProductOrders": [{
            "productOrderId": o["line_id"], "deliveryMethod": "DELIVERY",
            "deliveryCompanyCode": COURIERS.get(o["courier"], o["courier"]),
            "trackingNumber": o["tracking"], "dispatchDate": now} for o in orders]}
        r = _http("POST", f"{self.BASE}/v1/pay-order/seller/product-orders/dispatch", headers=self._h(), body=body)
        fails = ((r.get("data") or {}).get("failProductOrderInfos") or [])
        if fails:
            raise ApiError(f"일부 실패: {fails[:3]}")


# ═════════════════════════════════ 쿠팡 ═════════════════════════════════

class Coupang:
    HOST = "https://api-gateway.coupang.com"
    STATUS = {"ACCEPT": store.ST_NEW, "INSTRUCT": store.ST_CONFIRM, "DEPARTURE": store.ST_DONE,
              "DELIVERING": store.ST_DONE, "FINAL_DELIVERY": store.ST_DONE, "NONE_TRACKING": store.ST_DONE}

    def __init__(self, account, cfg, ship_type):
        self.account, self.cfg, self.ship_type = account, cfg, ship_type

    def _call(self, method, path, query=None, body=None):
        """쿠팡은 요청마다 Secret Key로 서명(HMAC)을 만들어 붙여야 합니다. 일종의 '도장'입니다."""
        qs = urllib.parse.urlencode(query or {})
        dt = datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")
        msg = dt + method + path + qs
        sig = hmac.new(self.cfg["secret_key"].encode(), msg.encode(), hashlib.sha256).hexdigest()
        auth = (f"CEA algorithm=HmacSHA256, access-key={self.cfg['access_key']}, "
                f"signed-date={dt}, signature={sig}")
        url = self.HOST + path + (f"?{qs}" if qs else "")
        return _http(method, url, headers={"Authorization": auth, "X-EXTENDED-TIMEOUT": "90000"}, body=body)

    @property
    def vid(self):
        return self.cfg["vendor_id"]

    def test(self):
        today = datetime.now(KST).strftime("%Y-%m-%d")
        self._call("GET", f"/v2/providers/openapi/apis/api/v4/vendors/{self.vid}/ordersheets",
                   {"createdAtFrom": today, "createdAtTo": today, "status": "ACCEPT", "maxPerPage": 1})
        return "주문 조회 성공"

    def collect(self, since):
        lines = []
        use_self = self.cfg.get("판매자배송", self.ship_type == store.SHIP_SELF)
        use_rg = self.cfg.get("로켓그로스", self.ship_type == store.SHIP_GROWTH)
        if use_self:
            lines += self._collect_self(since)
        if use_rg:
            lines += self._collect_growth(since)
        return lines

    def _collect_self(self, since):
        out = []
        frm = since.strftime("%Y-%m-%d")
        to = datetime.now(KST).strftime("%Y-%m-%d")
        for status in ("ACCEPT", "INSTRUCT", "DEPARTURE", "DELIVERING", "FINAL_DELIVERY"):
            token = ""
            while True:
                q = {"createdAtFrom": frm, "createdAtTo": to, "status": status, "maxPerPage": 50}
                if token:
                    q["nextToken"] = token
                r = self._call("GET", f"/v2/providers/openapi/apis/api/v4/vendors/{self.vid}/ordersheets", q)
                for sheet in r.get("data") or []:
                    out += self._lines_self(sheet)
                token = r.get("nextToken") or ""
                if not token:
                    break
        return out

    def _lines_self(self, s):
        rc, orderer = s.get("receiver") or {}, s.get("orderer") or {}
        st = s.get("status", "")
        out = []
        for it in s.get("orderItems") or []:
            status = store.ST_CANCEL if it.get("canceled") else self.STATUS.get(st, store.ST_NEW)
            out.append({
                "account": self.account, "line_id": f"{s.get('shipmentBoxId')}-{it.get('vendorItemId')}",
                "order_no": str(s.get("orderId", "")), "ordered_at": _kst(s.get("orderedAt") or s.get("paidAt")),
                "item_key": str(it.get("vendorItemId")),
                "product_name": it.get("sellerProductName") or it.get("vendorItemName", ""),
                "option_name": it.get("sellerProductItemName") or it.get("vendorItemName", ""),
                "qty": it.get("shippingCount", 1), "amount": it.get("orderPrice", 0),
                "buyer": orderer.get("name", ""), "receiver": rc.get("name", ""),
                "phone": rc.get("safeNumber", ""), "zipcode": rc.get("postCode", ""),
                "address": f"{rc.get('addr1', '')} {rc.get('addr2', '')}".strip(),
                "memo": s.get("parcelPrintMessage", ""), "ship_type": store.SHIP_SELF, "status": status,
                "channel_status": st, "tracking": s.get("invoiceNumber", "") or "",
                "_box": s.get("shipmentBoxId"), "_vitem": it.get("vendorItemId"),
            })
        return out

    def _collect_growth(self, since):
        """
        로켓그로스 주문 조회. 그로스는 쿠팡 창고에서 출고되므로 우리는 '재고 차감'만 하면 됩니다.
        ⚠ 로켓그로스 API는 계정별로 사용 신청이 필요할 수 있습니다. 실패하면 로그에 이유가 남습니다.
        """
        out, token = [], ""
        q = {"paidDateFrom": since.strftime("%Y%m%d"), "paidDateTo": datetime.now(KST).strftime("%Y%m%d")}
        while True:
            if token:
                q["nextToken"] = token
            r = self._call("GET", f"/v2/providers/rg_open_api/apis/api/v1/vendors/{self.vid}/rg/orders", q)
            for o in r.get("data") or []:
                for it in o.get("orderItems") or []:
                    qty = it.get("salesQuantity", 1)
                    out.append({
                        "account": self.account, "line_id": f"RG{o.get('orderId')}-{it.get('vendorItemId')}",
                        "order_no": str(o.get("orderId", "")),
                        "ordered_at": _kst(str(o.get("paidAt", ""))) if o.get("paidAt") else store.now_str(),
                        "item_key": str(it.get("vendorItemId")),
                        "product_name": it.get("productName", ""), "option_name": it.get("productName", ""),
                        "qty": qty, "amount": int(it.get("unitSalesPrice", 0)) * qty,
                        "ship_type": store.SHIP_GROWTH, "status": store.ST_PARTNER, "channel_status": "RG",
                    })
            token = r.get("nextToken") or ""
            if not token:
                break
        return out

    def confirm(self, orders):
        boxes = list({int(o["line_id"].split("-")[0]) for o in orders})
        self._call("PUT", f"/v2/providers/openapi/apis/api/v4/vendors/{self.vid}/ordersheets/acknowledgement",
                   body={"vendorId": self.vid, "shipmentBoxIds": boxes})

    def dispatch(self, orders):
        dtos = []
        for o in orders:
            box, vitem = o["line_id"].split("-", 1)
            dtos.append({"shipmentBoxId": int(box), "orderId": int(o["order_no"]), "vendorItemId": int(vitem),
                         "deliveryCompanyCode": COURIERS.get(o["courier"], o["courier"]),
                         "invoiceNumber": o["tracking"], "splitShipping": False,
                         "preSplitShipped": False, "estimatedShippingDate": ""})
        r = self._call("POST", f"/v2/providers/openapi/apis/api/v4/vendors/{self.vid}/orders/invoices",
                       body={"vendorId": self.vid, "orderSheetInvoiceApplyDtos": dtos})
        fails = [x for x in ((r.get("data") or {}).get("responseList") or []) if not x.get("succeed", True)]
        if fails:
            raise ApiError(f"일부 실패: {fails[:3]}")


# ═════════════════════════════════ 공통 ═════════════════════════════════

def has_keys(channel, cfg):
    need = ("client_id", "client_secret") if channel == "네이버" else ("vendor_id", "access_key", "secret_key")
    return all((cfg or {}).get(k) for k in need)


def build(account, settings):
    """계정 코드로 연결 객체를 만듭니다. 키가 없으면 None."""
    a = store.account_map().get(account)
    cfg = (settings.get("계정") or {}).get(account) or {}
    if not a or not has_keys(a["channel"], cfg):
        return None
    if a["channel"] == "네이버":
        return Naver(account, cfg)
    if a["ship_type"] == store.SHIP_ROCKET:
        return None   # 로켓배송(직매입) 발주는 오픈API가 없어 직접 등록합니다
    return Coupang(account, cfg, a["ship_type"])
