# strategy.py — 퀀트 전략 엔진 (12가지 매매 원칙 내장)
import numpy as np
import pandas as pd
from datetime import datetime
import requests

# ══════════════════════════════════════════════
# 기술 지표 계산
# ══════════════════════════════════════════════
def calc_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1: return 50.0
    s = pd.Series(prices)
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)

def calc_bollinger(prices: list, period: int = 20, std_mult: float = 2.0) -> dict:
    if len(prices) < period: return {"upper": 0, "mid": 0, "lower": 0, "pct_b": 0.5}
    s = pd.Series(prices)
    mid   = s.rolling(period).mean().iloc[-1]
    std   = s.rolling(period).std().iloc[-1]
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    price = prices[-1]
    pct_b = (price - lower) / (upper - lower) if (upper - lower) > 0 else 0.5
    return {"upper": upper, "mid": mid, "lower": lower, "pct_b": round(pct_b, 3)}

def calc_atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    if len(closes) < period + 1: return closes[-1] * 0.02 if closes else 0
    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, len(closes))]
    return float(np.mean(trs[-period:]))

def calc_momentum_score(price_history: list, volume_history: list) -> float:
    if len(price_history) < 20: return 0.0
    ret_20 = (price_history[-1] - price_history[-20]) / price_history[-20] * 100
    ret_score = min(max(ret_20 / 10, -1), 1)
    avg_vol = np.mean(volume_history[-20:]) if len(volume_history) >= 20 else 1
    vol_ratio = volume_history[-1] / avg_vol if avg_vol > 0 else 1
    vol_score = min(vol_ratio / 3, 1)
    rsi_score = (100 - calc_rsi(price_history)) / 100
    return round(ret_score * 0.4 + vol_score * 0.3 + rsi_score * 0.3, 4)

def calc_kelly(win_rate: float, avg_win: float, avg_loss: float) -> float:
    if avg_loss == 0: return 0.25
    b = avg_win / avg_loss
    kelly = (b * win_rate - (1 - win_rate)) / b
    return round(max(min(kelly / 2, 0.40), 0.05), 3)

def calc_correlation(returns_a: list, returns_b: list) -> float:
    if len(returns_a) < 5 or len(returns_b) < 5: return 0.0
    n = min(len(returns_a), len(returns_b))
    a, b = np.array(returns_a[-n:]), np.array(returns_b[-n:])
    if np.std(a) == 0 or np.std(b) == 0: return 0.0
    return float(np.corrcoef(a, b)[0, 1])

# ══════════════════════════════════════════════
# Rule 1~12 조건 필터
# ══════════════════════════════════════════════
def get_vix() -> float:
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1m&range=1d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        return float(r.json()["chart"]["result"][0]["meta"].get("regularMarketPrice", 20))
    except: return 20.0

def check_market_regime(vix: float) -> dict:
    if vix > 35: return {"regime": "EXTREME_FEAR", "position_mult": 0.0, "allow_buy": False, "reason": f"VIX {vix:.1f} > 35"}
    elif vix > 25: return {"regime": "FEAR", "position_mult": 0.5, "allow_buy": True, "reason": f"VIX {vix:.1f} > 25"}
    elif vix > 15: return {"regime": "NORMAL", "position_mult": 1.0, "allow_buy": True, "reason": f"VIX {vix:.1f} 정상"}
    else: return {"regime": "BULL", "position_mult": 1.2, "allow_buy": True, "reason": f"VIX {vix:.1f} < 15 강세장"}

def check_gap_down(open_price: float, prev_close: float, threshold: float = -0.02) -> dict:
    if prev_close <= 0: return {"blocked": False, "gap_pct": 0}
    gap = (open_price - prev_close) / prev_close
    return {"blocked": gap <= threshold, "gap_pct": round(gap * 100, 2), "reason": f"갭 다운 {gap*100:.2f}%" if gap <= threshold else ""}

def check_time_filter(market: str = "KR") -> dict:
    now = datetime.now()
    total_min = now.hour * 60 + now.minute
    if market == "KR":
        if (9*60 <= total_min <= 9*60+10) or (14*60+50 <= total_min <= 15*60+20):
            return {"blocked": True, "reason": "KR 시간 변동성 필터"}
    elif market == "US":
        if 22*60+30 <= total_min <= 22*60+45:
            return {"blocked": True, "reason": "US 시간 변동성 필터"}
    return {"blocked": False, "reason": ""}

def check_news_sentiment(recent_news_tags: list) -> dict:
    risk_count = sum(1 for tag in recent_news_tags if tag in ["WAR", "OIL"])
    if risk_count >= 3: return {"blocked": True, "reason": f"리스크 뉴스 {risk_count}건"}
    return {"blocked": False, "reason": ""}

def check_r_multiple(entry: float, stop: float, target: float, min_r: float = 2.0) -> dict:
    risk = entry - stop
    reward = target - entry
    if risk <= 0: return {"ok": False, "r": 0, "reason": "손절가 오류"}
    r = reward / risk
    ok = r >= min_r
    return {"ok": ok, "r": round(r, 2), "reason": f"R-Multiple {r:.2f}"}

def strategy_triple_confirm(price_history: list, volume_history: list, current: dict) -> dict:
    bb = calc_bollinger(price_history)
    rsi = calc_rsi(price_history)
    avg_vol = np.mean(volume_history[-20:]) if len(volume_history) >= 20 else 0
    vol_ratio = current["volume"] / avg_vol if avg_vol > 0 else 1

    signal, confidence = "HOLD", 0.0
    if bb["pct_b"] < 0.2 and rsi < 35 and vol_ratio > 1.5:
        signal = "BUY"
        confidence = (0.2 - bb["pct_b"]) * 2 + (35 - rsi) / 35 + min(vol_ratio / 3, 1)
    elif bb["pct_b"] > 0.8 and rsi > 65:
        signal = "SELL"
    return {"strategy": "TRIPLE_CONFIRM", "signal": signal, "reason": f"BB:{bb['pct_b']:.2f} RSI:{rsi:.1f} VOL:{vol_ratio:.1f}x", "confidence": round(confidence, 3)}

def get_final_signal(price_history: list, volume_history: list, current: dict, prev_close: float, market: str = "KR") -> dict:
    if check_time_filter(market)["blocked"]: return {"final_signal": "HOLD", "block_reason": "시간 필터"}
    if check_gap_down(current.get("open", current["price"]), prev_close)["blocked"]: return {"final_signal": "HOLD", "block_reason": "갭 다운"}

    s1 = strategy_triple_confirm(price_history, volume_history, current)
    rsi = calc_rsi(price_history)
    s2 = {"strategy": "RSI_SOLO", "signal": "BUY" if rsi < 30 else ("SELL" if rsi > 70 else "HOLD"), "reason": f"RSI {rsi:.1f}"}

    strategies = [s1, s2]
    buy_votes = sum(1 for s in strategies if s["signal"] == "BUY")
    
    final = "BUY" if s1["signal"] == "BUY" or buy_votes >= 2 else "HOLD"
    return {"final_signal": final, "buy_votes": buy_votes, "sell_votes": sum(1 for s in strategies if s["signal"] == "SELL"), "strategies": strategies, "block_reason": ""}

# ══════════════════════════════════════════════
# 퀀트 심화 엔진 (Kalman Squeeze)
# ══════════════════════════════════════════════
def calc_price_acceleration(prices: list, period: int = 5) -> float:
    if len(prices) < period * 2: return 0.0
    v1 = (prices[-1] - prices[-period]) / prices[-period]
    v2 = (prices[-period] - prices[-period*2]) / prices[-period*2]
    return round((v1 - v2) * 100, 3)

def calc_volatility_adjusted_momentum(prices: list, period: int = 20) -> float:
    if len(prices) < period + 1: return 0.0
    returns = np.diff(prices[-period-1:]) / prices[-period-1:-1]
    vol = np.std(returns)
    if vol == 0: return 0.0
    return round(float((np.mean(returns) / vol) * np.sqrt(252)), 3)

def calc_obv_trend(prices: list, volumes: list, period: int = 20) -> float:
    if len(prices) < period + 1 or len(volumes) < period + 1: return 0.0
    obv = [0]
    for i in range(1, len(prices)):
        if prices[i] > prices[i-1]: obv.append(obv[-1] + volumes[i])
        elif prices[i] < prices[i-1]: obv.append(obv[-1] - volumes[i])
        else: obv.append(obv[-1])
    recent = obv[-period:]
    if recent[0] == 0: return 0.0
    return round((recent[-1] - recent[0]) / (abs(recent[0]) + 1), 3)

def check_volatility_squeeze(prices: list, highs: list, lows: list, period: int = 20) -> bool:
    if len(prices) < period + 1: return False
    sma, std = np.mean(prices[-period:]), np.std(prices[-period:])
    bb_upper, bb_lower = sma + (2 * std), sma - (2 * std)
    trs = [max(highs[i] - lows[i], abs(highs[i] - prices[i-1]), abs(lows[i] - prices[i-1])) for i in range(len(prices)-period, len(prices))]
    atr = np.mean(trs)
    kc_upper, kc_lower = sma + (1.5 * atr), sma - (1.5 * atr)
    return (bb_upper < kc_upper) and (bb_lower > kc_lower)

def apply_kalman_filter(prices: list) -> np.ndarray:
    n_iter = len(prices)
    sz = (n_iter,)
    Q, R = 1e-5, 0.01
    xhat, P, xhatminus, Pminus, K = np.zeros(sz), np.zeros(sz), np.zeros(sz), np.zeros(sz), np.zeros(sz)
    xhat[0], P[0] = prices[0], 1.0
    for k in range(1, n_iter):
        xhatminus[k] = xhat[k-1]
        Pminus[k] = P[k-1] + Q
        K[k] = Pminus[k] / (Pminus[k] + R)
        xhat[k] = xhatminus[k] + K[k] * (prices[k] - xhatminus[k])
        P[k] = (1 - K[k]) * Pminus[k]
    return xhat

def calc_kalman_kinematics(prices: list) -> dict:
    if len(prices) < 5: return {"velocity": 0.0, "acceleration": 0.0}
    smoothed = apply_kalman_filter(prices)
    v1 = (smoothed[-1] - smoothed[-2]) / smoothed[-2]
    v2 = (smoothed[-2] - smoothed[-3]) / smoothed[-3]
    return {"velocity": round(v1 * 100, 3), "acceleration": round((v1 - v2) * 100, 3)}