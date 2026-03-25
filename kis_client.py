# kis_client.py — KR+US 통합 (디버그 모드)
import os, requests, json
import time as _time
from dotenv import load_dotenv

load_dotenv()

APP_KEY    = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")
ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO")
PROD_CD    = os.getenv("KIS_ACCOUNT_PROD_CD", "01")
IS_MOCK    = os.getenv("IS_MOCK", "true").lower() == "true"

KR_BASE = "https://openapivts.koreainvestment.com:29443" if IS_MOCK \
          else "https://openapi.koreainvestment.com:9443"
US_BASE = KR_BASE

TOKEN_FILE = ".token_cache.json"

# ── 토큰 발급 ──────────────────────────────────
def get_token() -> str:
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                cache = json.load(f)
            if _time.time() < cache.get("expires_at", 0) - 600:
                return cache["token"]
        except:
            pass
    res = requests.post(f"{KR_BASE}/oauth2/tokenP", json={
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    })
    res.raise_for_status()
    data = res.json()
    cache = {
        "token":      data["access_token"],
        "expires_at": _time.time() + data.get("expires_in", 86400)
    }
    with open(TOKEN_FILE, "w") as f:
        json.dump(cache, f)
    print("✅ 토큰 발급 완료")
    return cache["token"]

# ── Hashkey ────────────────────────────────────
def get_hashkey(data: dict) -> str:
    try:
        res = requests.post(
            f"{KR_BASE}/uapi/hashkey",
            headers={
                "Content-Type": "application/json",
                "appkey":       APP_KEY,
                "appsecret":    APP_SECRET,
            },
            json=data
        )
        return res.json().get("HASH", "")
    except Exception as e:
        print(f"⚠ hashkey 발급 실패: {e}")
        return ""

# ── 헤더 ───────────────────────────────────────
def get_headers(tr_id: str) -> dict:
    return {
        "Content-Type":  "application/json",
        "authorization": f"Bearer {get_token()}",
        "appkey":        APP_KEY,
        "appsecret":     APP_SECRET,
        "tr_id":         tr_id,
        "custtype":      "P",
    }

def get_order_headers(tr_id: str, body: dict) -> dict:
    headers = get_headers(tr_id)
    headers["hashkey"] = get_hashkey(body)
    return headers

# ══════════════════════════════════════════════
# 한국 주식
# ══════════════════════════════════════════════
def get_price_kr(stock_code: str) -> dict:
    res = requests.get(
        f"{KR_BASE}/uapi/domestic-stock/v1/quotations/inquire-price",
        headers=get_headers("FHKST01010100"),
        params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code}
    )
    res.raise_for_status()
    d = res.json()["output"]
    return {
        "code":        stock_code,
        "market":      "KR",
        "price":       int(d["stck_prpr"]),
        "open":        int(d["stck_oprc"]),
        "high":        int(d["stck_hgpr"]),
        "low":         int(d["stck_lwpr"]),
        "volume":      int(d["acml_vol"]),
        "change_rate": float(d["prdy_ctrt"]),
        "currency":    "KRW"
    }

def get_price(stock_code: str) -> dict:
    return get_price_kr(stock_code)

def get_balance_kr() -> dict:
    res = requests.get(
        f"{KR_BASE}/uapi/domestic-stock/v1/trading/inquire-balance",
        headers=get_headers("VTTC8434R" if IS_MOCK else "TTTC8434R"),
        params={
            "CANO": ACCOUNT_NO, "ACNT_PRDT_CD": PROD_CD,
            "AFHR_FLPR_YN": "N", "OFL_YN": "N", "INQR_DVSN": "02",
            "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""
        }
    )
    res.raise_for_status()
    o = res.json()["output2"][0]
    return {"available_cash_krw": int(o["dnca_tot_amt"])}

def get_balance() -> dict:
    return get_balance_kr()

def place_order_kr(stock_code: str, qty: int, price: int, side: str) -> dict:
    tr_id = ("VTTC0802U" if IS_MOCK else "TTTC0802U") if side == "BUY" \
            else ("VTTC0801U" if IS_MOCK else "TTTC0801U")

    # [수정됨] 가격이 0원이면 시장가("01"), 아니면 지정가("00")
    ord_dvsn = "01" if price == 0 else "00"
    ord_unpr = "0" if price == 0 else str(price)

    body = {
        "CANO":         ACCOUNT_NO,
        "ACNT_PRDT_CD": PROD_CD,
        "PDNO":         stock_code,
        "ORD_DVSN":     ord_dvsn,
        "ORD_QTY":      str(qty),
        "ORD_UNPR":     ord_unpr,
    }

    headers = get_order_headers(tr_id, body)

    # ── 디버그: 요청 내용 출력 ──
    print(f"\n[DEBUG] URL: {KR_BASE}/uapi/domestic-stock/v1/trading/order-cash")
    print(f"[DEBUG] tr_id: {tr_id}")
    print(f"[DEBUG] CANO: {ACCOUNT_NO} / PROD_CD: {PROD_CD}")
    print(f"[DEBUG] body: {json.dumps(body, ensure_ascii=False)}")

    res = requests.post(
        f"{KR_BASE}/uapi/domestic-stock/v1/trading/order-cash",
        headers=headers,
        json=body
    )

    print(f"[DEBUG] HTTP Status: {res.status_code}")
    print(f"[DEBUG] RAW Response: {res.text}")

    try:
        result = res.json()
    except:
        result = {"rt_cd": "9", "msg1": "JSON 파싱 실패"}

    if result.get("rt_cd") == "0":
        icon = "🟢" if side == "BUY" else "🔴"
        print(f"{icon} [KR {side}] {stock_code} {qty}주 @ {price:,}원 ✅")
    else:
        print(f"⚠ [KR {side}] 주문 실패: {result.get('msg1','')}")

    return result

# ══════════════════════════════════════════════
# 미국 주식
# ══════════════════════════════════════════════
US_EXCHANGE_MAP = {
    "NVDA":"NAS","AMD":"NAS","AAPL":"NAS","MSFT":"NAS","GOOGL":"NAS",
    "META":"NAS","TSLA":"NAS","AMZN":"NAS","TQQQ":"NAS","SOXL":"NAS",
    "PLTR":"NAS","CRWD":"NAS","NET":"NAS","DDOG":"NAS","SNOW":"NAS",
    "COIN":"NAS","MRVL":"NAS","AVGO":"NAS","UBER":"NAS","MRNA":"NAS",
    "BNTX":"NAS","INTC":"NAS","QCOM":"NAS",
    "TSM":"NYS","JPM":"NYS","BAC":"NYS","XOM":"NYS","CVX":"NYS","GS":"NYS",
    "FNGU":"NYS","LABU":"NYS",
}

def get_exchange(ticker: str) -> str:
    return US_EXCHANGE_MAP.get(ticker.upper(), "NAS")

def get_price_us(ticker: str) -> dict:
    excd  = get_exchange(ticker)
    res = requests.get(
        f"{US_BASE}/uapi/overseas-price/v1/quotations/price",
        headers=get_headers("HHDFS76200200"),
        params={"AUTH": "", "EXCD": excd, "SYMB": ticker.upper()}
    )
    res.raise_for_status()
    d     = res.json()["output"]
    price = float(d.get("last", 0) or 0)
    prev  = float(d.get("base", price) or price)
    chg   = ((price - prev) / prev * 100) if prev else 0
    return {
        "code":        ticker.upper(),
        "market":      "US",
        "price":       price,
        "open":        float(d.get("open", 0) or 0),
        "high":        float(d.get("high", 0) or 0),
        "low":         float(d.get("low",  0) or 0),
        "volume":      int(d.get("tvol", 0) or 0),
        "change_rate": round(chg, 2),
        "currency":    "USD",
        "exchange":    excd
    }

def get_balance_us() -> dict:
    tr_id = "VTTS3012R" if IS_MOCK else "TTTS3012R"
    res = requests.get(
        f"{US_BASE}/uapi/overseas-stock/v1/trading/inquire-balance",
        headers=get_headers(tr_id),
        params={
            "CANO": ACCOUNT_NO, "ACNT_PRDT_CD": PROD_CD,
            "OVRS_EXCG_CD": "NASD", "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""
        }
    )
    res.raise_for_status()
    output2 = res.json().get("output2", {})
    return {"available_cash_usd": float(output2.get("ovrs_ord_psbl_amt", 0) or 0)}

def place_order_us(ticker: str, qty: int, price: float, side: str) -> dict:
    excd  = get_exchange(ticker)
    tr_id = ("VTTT1002U" if IS_MOCK else "TTTT1002U") if side == "BUY" \
            else ("VTTT1001U" if IS_MOCK else "TTTT1001U")

    body = {
        "CANO":            ACCOUNT_NO,
        "ACNT_PRDT_CD":    PROD_CD,
        "OVRS_EXCG_CD":    excd,
        "PDNO":            ticker.upper(),
        "ORD_QTY":         str(qty),
        "OVRS_ORD_UNPR":   f"{price:.2f}",
        "ORD_SVR_DVSN_CD": "0",
        "ORD_DVSN":        "00"
    }

    res = requests.post(
        f"{US_BASE}/uapi/overseas-stock/v1/trading/order",
        headers=get_order_headers(tr_id, body),
        json=body
    )

    print(f"[DEBUG US] HTTP: {res.status_code} | {res.text[:200]}")

    try:
        result = res.json()
    except:
        result = {"rt_cd": "9", "msg1": "JSON 파싱 실패"}

    if result.get("rt_cd") == "0":
        icon = "🟢" if side == "BUY" else "🔴"
        print(f"{icon} [US {side}] {ticker} {qty}주 @ ${price:.2f} ✅")
    else:
        print(f"⚠ [US {side}] 주문 실패: {result.get('msg1','')}")

    return result

# ── 통합 인터페이스 ────────────────────────────
def get_price_any(code: str) -> dict:
    return get_price_kr(code) if code.isdigit() else get_price_us(code)

def place_order_any(code: str, qty: int, price: float, side: str) -> dict:
    if code.isdigit():
        return place_order_kr(code, qty, int(price), side)
    return place_order_us(code, qty, price, side)

# ── 테스트 ────────────────────────────────────
if __name__ == "__main__":
    print(f"=== KIS API 테스트 ({'모의투자' if IS_MOCK else '실전'}) ===\n")

    print("[한국 주식]")
    kr = get_price_kr("005930")
    print(f"삼성전자: {kr['price']:,}원 ({kr['change_rate']:+.2f}%)")

    bal = get_balance_kr()
    print(f"KRW 잔고: {bal['available_cash_krw']:,}원\n")

    print("[주문 테스트 — 삼성전자 1주 시장가]")
    # [수정됨] 이제 시장가(0원) 입력 시 자동으로 ORD_DVSN을 01로 전송합니다.
    result = place_order_kr("005930", 1, 0, "BUY")
    print(f"\n최종결과: rt_cd={result.get('rt_cd')} | {result.get('msg1','')}")