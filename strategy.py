# strategy.py — 퀀트 전략 엔진 (12가지 매매 원칙 내장)
import numpy as np
import pandas as pd
from datetime import datetime
import requests

# ══════════════════════════════════════════════
# 기술 지표 계산
# ══════════════════════════════════════════════

def calc_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    s = pd.Series(prices)
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)

def calc_bollinger(prices: list, period: int = 20, std_mult: float = 2.0) -> dict:
    if len(prices) < period:
        return {"upper": 0, "mid": 0, "lower": 0, "pct_b": 0.5}
    s = pd.Series(prices)
    mid   = s.rolling(period).mean().iloc[-1]
    std   = s.rolling(period).std().iloc[-1]
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    price = prices[-1]
    pct_b = (price - lower) / (upper - lower) if (upper - lower) > 0 else 0.5
    return {"upper": upper, "mid": mid, "lower": lower, "pct_b": round(pct_b, 3)}

def calc_atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """Average True Range — 동적 손절폭 계산용"""
    if len(closes) < period + 1:
        return closes[-1] * 0.02 if closes else 0
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        trs.append(tr)
    return float(np.mean(trs[-period:]))

def calc_momentum_score(price_history: list, volume_history: list) -> float:
    """
    Rule 9: 모멘텀 점수 = 수익률×0.4 + 거래량비율×0.3 + RSI역수×0.3
    """
    if len(price_history) < 20:
        return 0.0
    # 20일 수익률
    ret_20 = (price_history[-1] - price_history[-20]) / price_history[-20] * 100
    ret_score = min(max(ret_20 / 10, -1), 1)  # -1 ~ 1 정규화

    # 거래량 비율
    avg_vol = np.mean(volume_history[-20:]) if len(volume_history) >= 20 else 1
    vol_ratio = volume_history[-1] / avg_vol if avg_vol > 0 else 1
    vol_score = min(vol_ratio / 3, 1)  # 0 ~ 1

    # RSI 역수 (낮을수록 매수 매력)
    rsi = calc_rsi(price_history)
    rsi_score = (100 - rsi) / 100  # 0 ~ 1

    score = ret_score * 0.4 + vol_score * 0.3 + rsi_score * 0.3
    return round(score, 4)

def calc_kelly(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Rule 3: 켈리 공식 f* = (bp - q) / b
    win_rate: 승률 (0~1)
    avg_win: 평균 수익률
    avg_loss: 평균 손실률 (양수)
    """
    if avg_loss == 0:
        return 0.25
    b = avg_win / avg_loss  # 손익비
    p = win_rate
    q = 1 - win_rate
    kelly = (b * p - q) / b
    # 켈리의 절반만 사용 (Half-Kelly — 실전 퀀트 표준)
    half_kelly = kelly / 2
    return round(max(min(half_kelly, 0.40), 0.05), 3)  # 5%~40% 범위 제한

def calc_correlation(returns_a: list, returns_b: list) -> float:
    """Rule 4: 상관계수 계산"""
    if len(returns_a) < 5 or len(returns_b) < 5:
        return 0.0
    n = min(len(returns_a), len(returns_b))
    a = np.array(returns_a[-n:])
    b = np.array(returns_b[-n:])
    if np.std(a) == 0 or np.std(b) == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])

# ══════════════════════════════════════════════
# Rule 1: VIX 시장 국면 필터
# ══════════════════════════════════════════════
def get_vix() -> float:
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1m&range=1d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        meta = r.json()["chart"]["result"][0]["meta"]
        return float(meta.get("regularMarketPrice", 20))
    except:
        return 20.0

def check_market_regime(vix: float) -> dict:
    """
    Rule 1: VIX 기반 시장 국면
    VIX < 15: 강세장 — 풀 포지션
    VIX 15~25: 보통 — 정상 운영
    VIX 25~35: 위험 — 포지션 50% 축소
    VIX > 35: 극도 공포 — 매수 중단
    """
    if vix > 35:
        return {"regime": "EXTREME_FEAR", "position_mult": 0.0, "allow_buy": False,
                "reason": f"VIX {vix:.1f} > 35 — 매수 전면 중단"}
    elif vix > 25:
        return {"regime": "FEAR", "position_mult": 0.5, "allow_buy": True,
                "reason": f"VIX {vix:.1f} > 25 — 포지션 50% 축소"}
    elif vix > 15:
        return {"regime": "NORMAL", "position_mult": 1.0, "allow_buy": True,
                "reason": f"VIX {vix:.1f} 정상 구간"}
    else:
        return {"regime": "BULL", "position_mult": 1.2, "allow_buy": True,
                "reason": f"VIX {vix:.1f} < 15 — 강세장 공격적 운영"}

# ══════════════════════════════════════════════
# Rule 2: 갭 다운 차단
# ══════════════════════════════════════════════
def check_gap_down(open_price: float, prev_close: float, threshold: float = -0.02) -> dict:
    if prev_close <= 0:
        return {"blocked": False, "gap_pct": 0}
    gap = (open_price - prev_close) / prev_close
    blocked = gap <= threshold
    return {
        "blocked": blocked,
        "gap_pct": round(gap * 100, 2),
        "reason": f"갭 다운 {gap*100:.2f}% — 당일 매수 차단" if blocked else ""
    }

# ══════════════════════════════════════════════
# Rule 7: 시간대 필터
# ══════════════════════════════════════════════
def check_time_filter(market: str = "KR") -> dict:
    now = datetime.now()
    h, m = now.hour, now.minute
    total_min = h * 60 + m

    if market == "KR":
        # 동시호가 09:00~09:10, 마감변동 14:50~15:20
        if (9 * 60 <= total_min <= 9 * 60 + 10) or \
           (14 * 60 + 50 <= total_min <= 15 * 60 + 20):
            return {"blocked": True, "reason": f"KR 시간 필터 차단 ({h:02d}:{m:02d})"}
    elif market == "US":
        # 뉴욕 개장 첫 15분: 한국시간 22:30~22:45 (서머타임 21:30~21:45)
        us_open_start = 22 * 60 + 30
        us_open_end   = 22 * 60 + 45
        if us_open_start <= total_min <= us_open_end:
            return {"blocked": True, "reason": f"US 개장 변동성 구간 차단 ({h:02d}:{m:02d})"}

    return {"blocked": False, "reason": ""}

# ══════════════════════════════════════════════
# Rule 10: 뉴스 센티멘트 차단
# ══════════════════════════════════════════════
def check_news_sentiment(recent_news_tags: list) -> dict:
    """
    최근 10분 뉴스 WAR/OIL 태그 3개 이상 → 매수 차단
    """
    risk_count = sum(1 for tag in recent_news_tags if tag in ["WAR", "OIL"])
    if risk_count >= 3:
        return {"blocked": True,
                "reason": f"리스크 뉴스 {risk_count}건 감지 — 매수 일시 중단"}
    return {"blocked": False, "reason": ""}

# ══════════════════════════════════════════════
# Rule 5: 볼린저 + RSI + 거래량 3중 조건
# ══════════════════════════════════════════════
def strategy_triple_confirm(price_history: list, volume_history: list,
                             current: dict) -> dict:
    """
    매수: 볼린저 하단 이탈(pct_b < 0.2) + RSI < 35 + 거래량 > 평균 150%
    매도: 볼린저 상단 돌파(pct_b > 0.8) + RSI > 65
    """
    bb   = calc_bollinger(price_history)
    rsi  = calc_rsi(price_history)
    avg_vol = np.mean(volume_history[-20:]) if len(volume_history) >= 20 else 0
    vol_ratio = current["volume"] / avg_vol if avg_vol > 0 else 1

    signal = "HOLD"
    reason = f"BB:{bb['pct_b']:.2f} RSI:{rsi:.1f} VOL:{vol_ratio:.1f}x"
    confidence = 0.0

    # 매수 조건
    if bb["pct_b"] < 0.2 and rsi < 35 and vol_ratio > 1.5:
        signal = "BUY"
        confidence = (0.2 - bb["pct_b"]) * 2 + (35 - rsi) / 35 + min(vol_ratio / 3, 1)
        reason = f"3중확인 매수 — BB:{bb['pct_b']:.2f} RSI:{rsi:.1f} VOL:{vol_ratio:.1f}x"
    # 매도 조건
    elif bb["pct_b"] > 0.8 and rsi > 65:
        signal = "SELL"
        confidence = (bb["pct_b"] - 0.8) * 2 + (rsi - 65) / 35
        reason = f"3중확인 매도 — BB:{bb['pct_b']:.2f} RSI:{rsi:.1f}"

    return {"strategy": "TRIPLE_CONFIRM", "signal": signal,
            "reason": reason, "confidence": round(confidence, 3)}

# ══════════════════════════════════════════════
# Rule 9: 모멘텀 기반 동적 종목 선정
# ══════════════════════════════════════════════
def rank_by_momentum(candidates: dict, price_histories: dict,
                     volume_histories: dict) -> list:
    """
    candidates: {code: name}
    반환: 모멘텀 점수 상위 종목 순서 [(code, name, score)]
    """
    scored = []
    for code, name in candidates.items():
        ph = price_histories.get(code, [])
        vh = volume_histories.get(code, [])
        score = calc_momentum_score(ph, vh)
        scored.append((code, name, score))
    scored.sort(key=lambda x: x[2], reverse=True)
    return scored

# ══════════════════════════════════════════════
# Rule 12: R-Multiple 체크 (기대값 양수 필터)
# ══════════════════════════════════════════════
def check_r_multiple(entry: float, stop: float, target: float,
                     min_r: float = 2.0) -> dict:
    """
    R = (target - entry) / (entry - stop)
    R >= 2.0 이상일 때만 진입 허용
    """
    risk   = entry - stop
    reward = target - entry
    if risk <= 0:
        return {"ok": False, "r": 0, "reason": "손절가 설정 오류"}
    r = reward / risk
    ok = r >= min_r
    return {
        "ok": ok,
        "r":  round(r, 2),
        "reason": f"R-Multiple {r:.2f} {'✅' if ok else f'❌ (최소 {min_r}R 필요)'}"
    }

# ══════════════════════════════════════════════
# 통합 시그널 생성
# ══════════════════════════════════════════════
def get_final_signal(price_history: list, volume_history: list,
                     current: dict, prev_close: float,
                     market: str = "KR") -> dict:
    """
    전략 통합 + Rule 2,5,7 적용
    """
    # Rule 7: 시간 필터
    time_check = check_time_filter(market)
    if time_check["blocked"]:
        return {"final_signal": "HOLD", "buy_votes": 0, "sell_votes": 0,
                "strategies": [], "block_reason": time_check["reason"]}

    # Rule 2: 갭 다운
    gap_check = check_gap_down(current.get("open", current["price"]), prev_close)
    if gap_check["blocked"]:
        return {"final_signal": "HOLD", "buy_votes": 0, "sell_votes": 0,
                "strategies": [], "block_reason": gap_check["reason"]}

    # Rule 5: 3중 확인 전략
    s1 = strategy_triple_confirm(price_history, volume_history, current)

    # 기존 RSI 단독 (보조)
    rsi = calc_rsi(price_history)
    rsi_signal = "BUY" if rsi < 30 else ("SELL" if rsi > 70 else "HOLD")
    s2 = {"strategy": "RSI_SOLO", "signal": rsi_signal,
          "reason": f"RSI {rsi:.1f}", "confidence": 0.5}

    # 갭 전략 (보조)
    gap_pct = gap_check.get("gap_pct", 0)
    gap_signal = "BUY" if gap_pct >= 2.0 else "HOLD"
    s3 = {"strategy": "GAP", "signal": gap_signal,
          "reason": f"갭 {gap_pct:+.1f}%", "confidence": 0.4}

    strategies = [s1, s2, s3]
    buy_votes  = sum(1 for s in strategies if s["signal"] == "BUY")
    sell_votes = sum(1 for s in strategies if s["signal"] == "SELL")

    # 3중 확인이 BUY면 단독으로도 매수 (신뢰도 높음)
    if s1["signal"] == "BUY":
        final = "BUY"
    elif buy_votes >= 2:
        final = "BUY"
    elif sell_votes >= 2 or s1["signal"] == "SELL":
        final = "SELL"
    else:
        final = "HOLD"

    return {
        "final_signal": final,
        "buy_votes":    buy_votes,
        "sell_votes":   sell_votes,
        "strategies":   strategies,
        "block_reason": ""
    }