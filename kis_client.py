# kis_client.py — 한국 + 미국 주식 통합 클라이언트
import os, requests, json
import time as _time
from dotenv import load_dotenv

load_dotenv()

APP_KEY    = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")
ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO")
PROD_CD    = os.getenv("KIS_ACCOUNT_PROD_CD", "01")
IS_MOCK    = os.getenv("IS_MOCK", "true").lower() == "true"

# 한국 / 미국 BASE URL
KR_BASE = "https://openapivts.koreainvestment.com:29443" if IS_MOCK \
          else "https://openapi.koreainvestment.com:9443"
US_BASE = "https://openapivts.koreainvestment.com:29443" if IS_MOCK \
          else "https://openapi.koreainvestment.com:9443"

TOKEN_FILE = ".token_cache.json"

# ── 토큰 (파일 캐시) ──────────────────────────
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

def get_headers(tr_id: str) -> dict:
    return {
        "Content-Type":  "application/json",
        "authorization": f"Bearer {get_token()}",
        "appkey":        APP_KEY,
        "appsecret":     APP_SECRET,
        "tr_id":         tr_id,
        "custtype":      "P"
    }

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

# get_price 는 하위 호환용 alias
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
    res = requests.post(
        f"{KR_BASE}/uapi/domestic-stock/v1/trading/order-cash",
        headers=get_headers(tr_id),
        json={
            "CANO": ACCOUNT_NO, "ACNT_PRDT_CD": PROD_CD,
            "PDNO": stock_code, "ORD_DVSN": "00",
            "ORD_QTY": str(qty), "ORD_UNPR": str(price)
        }
    )
    res.raise_for_status()
    icon = "🟢" if side == "BUY" else "🔴"
    print(f"{icon} [KR] {side} {stock_code} {qty}주 @ {price:,}원")
    return res.json()

# ══════════════════════════════════════════════
# 미국 주식
# ══════════════════════════════════════════════

# 거래소 코드 매핑
US_EXCHANGE_MAP = {
    # NASDAQ
    "NVDA":"NAS","AMD":"NAS","AAPL":"NAS","MSFT":"NAS","GOOGL":"NAS",
    "META":"NAS","TSLA":"NAS","AMZN":"NAS","TQQQ":"NAS","SOXL":"NAS",
    "INTC":"NAS","QCOM":"NAS","AVGO":"NAS",
    # NYSE
    "TSM":"NYS","JPM":"NYS","BAC":"NYS","XOM":"NYS","GS":"NYS",
}

def get_exchange(ticker: str) -> str:
    return US_EXCHANGE_MAP.get(ticker.upper(), "NAS")

def get_price_us(ticker: str) -> dict:
    """미국 주식 현재가 조회"""
    excd = get_exchange(ticker)
    tr_id = "HHDFS76200200"  # 해외주식 현재가 (모의/실전 동일)
    res = requests.get(
        f"{US_BASE}/uapi/overseas-price/v1/quotations/price",
        headers=get_headers(tr_id),
        params={
            "AUTH":  "",
            "EXCD":  excd,
            "SYMB":  ticker.upper()
        }
    )
    res.raise_for_status()
    d = res.json()["output"]
    price = float(d.get("last", 0) or 0)
    open_ = float(d.get("open", 0) or 0)
    high  = float(d.get("high", 0) or 0)
    low   = float(d.get("low",  0) or 0)
    prev  = float(d.get("base", price) or price)
    vol   = int(d.get("tvol", 0) or 0)
    chg   = ((price - prev) / prev * 100) if prev else 0
    return {
        "code":        ticker.upper(),
        "market":      "US",
        "price":       price,
        "open":        open_,
        "high":        high,
        "low":         low,
        "volume":      vol,
        "change_rate": round(chg, 2),
        "currency":    "USD",
        "exchange":    excd
    }

def get_balance_us() -> dict:
    """미국 주식 잔고/예수금 조회"""
    tr_id = "VTTS3012R" if IS_MOCK else "TTTS3012R"
    res = requests.get(
        f"{US_BASE}/uapi/overseas-stock/v1/trading/inquire-balance",
        headers=get_headers(tr_id),
        params={
            "CANO":           ACCOUNT_NO,
            "ACNT_PRDT_CD":   PROD_CD,
            "OVRS_EXCG_CD":   "NASD",
            "TR_CRCY_CD":     "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }
    )
    res.raise_for_status()
    data = res.json()
    output2 = data.get("output2", {})
    available_usd = float(output2.get("ovrs_ord_psbl_amt", 0) or 0)
    return {"available_cash_usd": available_usd}

def place_order_us(ticker: str, qty: int, price: float, side: str) -> dict:
    """미국 주식 주문"""
    excd = get_exchange(ticker)
    if side == "BUY":
        tr_id = "VTTT1002U" if IS_MOCK else "TTTT1002U"
    else:
        tr_id = "VTTT1001U" if IS_MOCK else "TTTT1001U"

    res = requests.post(
        f"{US_BASE}/uapi/overseas-stock/v1/trading/order",
        headers=get_headers(tr_id),
        json={
            "CANO":         ACCOUNT_NO,
            "ACNT_PRDT_CD": PROD_CD,
            "OVRS_EXCG_CD": excd,
            "PDNO":         ticker.upper(),
            "ORD_QTY":      str(qty),
            "OVRS_ORD_UNPR": f"{price:.2f}",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN":     "00"  # 지정가
        }
    )
    res.raise_for_status()
    icon = "🟢" if side == "BUY" else "🔴"
    print(f"{icon} [US] {side} {ticker} {qty}주 @ ${price:.2f}")
    return res.json()

# ══════════════════════════════════════════════
# 통합 인터페이스
# ══════════════════════════════════════════════
def get_price_any(code: str) -> dict:
    """종목코드가 숫자면 KR, 영문이면 US"""
    if code.isdigit():
        return get_price_kr(code)
    else:
        return get_price_us(code)

def place_order_any(code: str, qty: int, price: float, side: str) -> dict:
    if code.isdigit():
        return place_order_kr(code, qty, int(price), side)
    else:
        return place_order_us(code, qty, price, side)

# ── 테스트 ────────────────────────────────────
if __name__ == "__main__":
    print("=== KIS API 통합 테스트 ===")
    print(f"환경: {'모의투자' if IS_MOCK else '실전투자'}\n")

    print("[ 한국 주식 ]")
    kr = get_price_kr("005930")
    print(f"삼성전자: {kr['price']:,}원 ({kr['change_rate']:+.2f}%)")

    bal_kr = get_balance_kr()
    print(f"KRW 예수금: {bal_kr['available_cash_krw']:,}원\n")

    print("[ 미국 주식 ]")
    try:
        us = get_price_us("NVDA")
        print(f"NVIDIA: ${us['price']:.2f} ({us['change_rate']:+.2f}%)")
        bal_us = get_balance_us()
        print(f"USD 예수금: ${bal_us['available_cash_usd']:.2f}")
    except Exception as e:
        print(f"미국 주식 조회 오류: {e}")
        print("→ KIS Developers에서 해외주식 모의투자 신청 확인 필요")