# agent.py — QUANT STATION PRO v3.0 (Smart Money Squeeze Model)
import time
import json
import os
import requests
import pandas as pd
from datetime import datetime, timedelta
import FinanceDataReader as fdr
from kis_client import (
    get_price_kr, get_price_us,
    get_balance_kr, get_balance_us,
    place_order_kr, place_order_us,
    IS_MOCK
)
from strategy import (
    get_final_signal, get_vix, check_market_regime,
    calc_atr, calc_kelly, calc_correlation,
    check_r_multiple, check_news_sentiment,
    check_time_filter, calc_rsi, calc_bollinger,
    calc_momentum_score,
    # ─── 최강 퀀트 알고리즘 함수들 (strategy.py에 있어야 함) ───
    calc_price_acceleration, calc_volatility_adjusted_momentum,
    calc_obv_trend, check_volatility_squeeze 
)

# ══════════════════════════════════════════════
# 설정
# ══════════════════════════════════════════════
TAKE_PROFIT_R    = 2.0
MAX_POSITIONS_KR = 2
MAX_POSITIONS_US = 2
DAILY_LOSS_LIMIT = -0.05
LOG_FILE         = "trades.json"
HISTORY_DAYS     = 40

SCAN_MIN_PRICE   = 1000
SCAN_MAX_PRICE   = 200000
SCAN_MIN_VOLUME  = 30000 
SCAN_MIN_CHANGE  = -3.0
SCAN_MAX_CHANGE  = 12.0

US_UNIVERSE = {
    "NVDA":"NVIDIA","AMD":"AMD","AVGO":"Broadcom","MRVL":"Marvell",
    "MSFT":"Microsoft","META":"Meta","GOOGL":"Google","AMZN":"Amazon",
    "TSLA":"Tesla","PLTR":"Palantir","CRWD":"CrowdStrike","NET":"Cloudflare",
    "DDOG":"Datadog","SNOW":"Snowflake","UBER":"Uber","COIN":"Coinbase",
    "MRNA":"Moderna","XOM":"ExxonMobil",
    "SOXL":"반도체3x","TQQQ":"나스닥3x",
}

# ══════════════════════════════════════════════
# 에이전트 상태
# ══════════════════════════════════════════════
class AgentState:
    def __init__(self):
        self.positions_kr     = {}
        self.positions_us     = {}
        self.price_history    = {}
        self.volume_history   = {}
        self.high_history     = {}
        self.low_history      = {}
        self.prev_close       = {}
        self.returns_history  = {}
        self.trade_log        = []
        self.daily_pnl        = 0.0
        self.start_cash_krw   = 0
        self.start_cash_usd   = 0
        self.win_trades       = 0
        self.loss_trades      = 0
        self.total_win_pct    = 0.0
        self.total_loss_pct   = 0.0
        self.recent_news_tags = []
        self.day_blocked      = False
        self.running          = False
        self.last_scan_time   = 0
        self.scan_candidates  = []

    def update_history(self, code, price, volume, high=0, low=0):
        for d, v in [
            (self.price_history,  float(price)),
            (self.volume_history, int(volume)),
            (self.high_history,   float(high or price)),
            (self.low_history,    float(low or price)),
        ]:
            d.setdefault(code, []).append(v)
            if len(d[code]) > 120:
                d[code].pop(0)
        ph = self.price_history[code]
        if len(ph) >= 2:
            ret = (ph[-1] - ph[-2]) / ph[-2]
            self.returns_history.setdefault(code, []).append(ret)
            if len(self.returns_history[code]) > 60:
                self.returns_history[code].pop(0)

    def preload(self, code, df):
        if df is None or len(df) < 5:
            return
        self.price_history[code]  = df["Close"].tolist()
        self.volume_history[code] = df["Volume"].tolist()
        self.high_history[code]   = df["High"].tolist()
        self.low_history[code]    = df["Low"].tolist()
        closes = df["Close"].tolist()
        if len(closes) >= 2:
            self.returns_history[code] = [
                (closes[i]-closes[i-1])/closes[i-1]
                for i in range(1, len(closes))
            ]
        if closes:
            self.prev_close[code] = float(closes[-1])

    def log_trade(self, action, code, name, qty, price, reason, currency="KRW", pnl=0):
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action, "code": code, "name": name,
            "qty": qty, "price": price,
            "currency": currency, "reason": reason, "pnl": pnl
        }
        self.trade_log.append(entry)
        if pnl > 0:
            self.win_trades += 1
            self.total_win_pct += abs(pnl/(price*qty))*100 if qty > 0 else 0
        elif pnl < 0:
            self.loss_trades += 1
            self.total_loss_pct += abs(pnl/(price*qty))*100 if qty > 0 else 0
        with open(LOG_FILE, "w") as f:
            json.dump(self.trade_log, f, ensure_ascii=False, indent=2)
        icon = "🟢" if action == "BUY" else "🔴"
        pnl_str = f" PNL:{pnl:+,.0f}{currency}" if pnl != 0 else ""
        print(f"  {icon} [{action}] {name}({code}) {qty}주 @ {price}{pnl_str}")
        print(f"     └ {reason}")

    @property
    def win_rate(self):
        t = self.win_trades + self.loss_trades
        return self.win_trades / t if t > 0 else 0.5

    @property
    def avg_win(self):
        return self.total_win_pct / self.win_trades if self.win_trades > 0 else 2.0

    @property
    def avg_loss(self):
        return self.total_loss_pct / self.loss_trades if self.loss_trades > 0 else 1.0

state = AgentState()

def load_history(code: str) -> bool:
    try:
        end   = datetime.now()
        start = end - timedelta(days=HISTORY_DAYS + 10)
        df = fdr.DataReader(code, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if df is None or len(df) < 5:
            return False
        df = df.tail(HISTORY_DAYS)
        state.preload(code, df)
        return True
    except:
        return False

def preload_all():
    print("\n  📚 퀀트 엔진: 전 종목(KOSPI/KOSDAQ/ETF) 데이터 스캔 준비 중...")
    end   = datetime.now()
    start = end - timedelta(days=5)

    all_codes = {}
    try:
        # KRX 전체 포섭 (코스피, 코스닥, ETF)
        listing = fdr.StockListing('KRX')
        listing.columns = [c.strip() for c in listing.columns]
        code_col = next((c for c in listing.columns if "Code" in c or "종목코드" in c), None)
        name_col = next((c for c in listing.columns if "Name" in c or "종목명" in c), None)
        
        for _, row in listing.iterrows():
            code = str(row[code_col]).zfill(6)
            name = str(row[name_col])
            all_codes[code] = name
            
        print(f"  ✅ 전체 시장 {len(all_codes)}개 종목 타겟팅 완료.")
    except Exception as e:
        print(f"  ⚠ 종목 리스트 로드 실패: {e}")

    return all_codes

def scan_kr_market(all_codes: dict) -> list:
    from strategy import (
        calc_obv_trend, 
        check_volatility_squeeze,
        calc_kalman_kinematics # 방금 만든 통합 엔진
    )
    
    print("  🔭 [Apex Model 가동] 칼만 필터 노이즈 제거 및 미적분 타점 포착 중...")
    candidates = []
    today = datetime.now()
    start = today - timedelta(days=60)

    scanned = 0
    for code, name in list(all_codes.items())[:1000]: 
        try:
            df = fdr.DataReader(code, start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
            if df is None or len(df) < 30:
                continue

            close  = float(df["Close"].iloc[-1])
            volume = int(df["Volume"].iloc[-1])

            if not (1000 <= close <= 200000): continue
            if volume < 30000: continue

            state.preload(code, df.tail(HISTORY_DAYS))
            ph = state.price_history.get(code, [])
            vh = state.volume_history.get(code, [])
            hh = state.high_history.get(code, [])
            lh = state.low_history.get(code, [])

            if len(ph) < 20: continue

            # ─── 통합 알고리즘 적용 ───
            # 1. 횡보하며 에너지가 응축되었는가?
            is_squeezed = check_volatility_squeeze(ph, hh, lh, period=20)
            
            # 2. 기관 매집이 있는가?
            obv_trend = calc_obv_trend(ph, vh, period=14)
            
            # 3. 칼만 필터 기반의 진짜 속도와 가속도 추출
            kinematics = calc_kalman_kinematics(ph)
            vel = kinematics["velocity"]
            acc = kinematics["acceleration"]

            # [최종 타점 조건]
            # 노이즈를 걷어낸 상태에서 가속도(acc)가 위로 강하게 꺾이고(>0.1),
            # 에너지가 응축(is_squeezed)되어 있거나 기관 매집(obv_trend > 0.02)이 확인된 경우
            if acc > 0.1 and (is_squeezed or obv_trend > 0.02):
                
                # 속도(방향성)와 가속도(폭발력)에 비례하여 스코어링
                score = (acc * 5.0) + (obv_trend * 10.0) + (vel * 2.0)
                if is_squeezed: score += 2.0
                
                reason = f"Kalman Acc:{acc:.2f} | Vel:{vel:.2f} | OBV:{obv_trend:.3f} | SQZ:{'ON' if is_squeezed else 'OFF'}"
                candidates.append((code, name, score, reason))
                
            scanned += 1

        except Exception:
            continue

    candidates.sort(key=lambda x: x[2], reverse=True)
    top = candidates[:5]

    print(f"  ✅ {scanned}개 스캔 완료 → [칼만-키네마틱 타점] {len(top)}개 락온")
    for code, name, score, reason in top:
        print(f"     🎯 {name}({code}) [SCORE: {score:.2f}] {reason}")

    return top

def scan_us_market(regime_mult: float) -> list:
    candidates = []
    for ticker, name in US_UNIVERSE.items():
        try:
            ph = state.price_history.get(ticker, [])
            vh = state.volume_history.get(ticker, [])

            if len(ph) < 10:
                end   = datetime.now()
                start = end - timedelta(days=HISTORY_DAYS+5)
                df = fdr.DataReader(ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
                if df is not None and len(df) >= 5:
                    state.preload(ticker, df.tail(HISTORY_DAYS))
                    ph = state.price_history.get(ticker, [])
                    vh = state.volume_history.get(ticker, [])

            if len(ph) < 5:
                score = 0.2 if ticker in ["SOXL","TQQQ"] and regime_mult < 1.0 else 0.4
                candidates.append((ticker, name, score, "데이터부족"))
                continue

            mom      = calc_momentum_score(ph, vh)
            rsi      = calc_rsi(ph)
            bb       = calc_bollinger(ph)
            rsi_b    = 0.2 if rsi < 35 else (-0.15 if rsi > 75 else 0)
            bb_b     = 0.15 if bb["pct_b"] < 0.25 else 0
            lev_pen  = -0.25 if ticker in ["SOXL","TQQQ","FNGU","LABU"] and regime_mult < 1.0 else 0
            score    = mom + rsi_b + bb_b + lev_pen
            reason   = f"Mom:{mom:.2f} RSI:{rsi:.0f} BB:{bb['pct_b']:.2f}"
            candidates.append((ticker, name, score, reason))
        except Exception as e:
            candidates.append((ticker, name, 0.3, "오류"))

    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates[:5]

def is_kr_open():
    now = datetime.now()
    if now.weekday() >= 5: return False
    h, m = now.hour, now.minute
    return (9 <= h < 15) or (h == 15 and m <= 20)

def is_us_open():
    now = datetime.now()
    if now.weekday() >= 5: return False
    return now.hour >= 22 or now.hour < 5

def is_any_open():
    return is_kr_open() or is_us_open()

def calc_size(cash, price, regime_mult):
    kelly = calc_kelly(state.win_rate, state.avg_win, state.avg_loss)
    ratio = max(min(kelly * regime_mult, 0.35), 0.05)
    return max(int(cash * ratio / price), 0)

def calc_stops(code, entry):
    """
    [목표 2~3% 스나이퍼 셋팅]
    기존 ATR 변동성 기반을 버리고, 진입가 대비 정확히 +2.5%에서 익절, -1.5%에서 손절합니다.
    ETF나 대형주 스윙에 매우 적합한 짧고 확실한 타겟팅입니다.
    """
    take_profit_pct = 0.025  # +2.5% 도달 시 기계적 매도 (익절)
    stop_loss_pct   = 0.015  # -1.5% 도달 시 기계적 매도 (손절 - 뼈를 내주고 생존)
    
    return {
        "stop_loss":   round(entry * (1 - stop_loss_pct), 4),
        "take_profit": round(entry * (1 + take_profit_pct), 4),
        "pct":         round(take_profit_pct * 100, 2),
    }

def is_correlated(code):
    new_r = state.returns_history.get(code, [])
    if not new_r: return False
    for held in list(state.positions_kr) + list(state.positions_us):
        corr = calc_correlation(new_r, state.returns_history.get(held, []))
        if corr > 0.7:
            print(f"  ⚠ Rule4: {code}↔{held} 상관{corr:.2f} 차단")
            return True
    return False

def try_buy_kr(code, name, scan_reason, cash, regime):
    try:
        if len(state.price_history.get(code, [])) < 20:
            load_history(code)

        cur = get_price_kr(code)
        state.update_history(code, cur["price"], cur["volume"], cur["high"], cur["low"])

        if is_correlated(code): return
        if check_news_sentiment(state.recent_news_tags)["blocked"]:
            print(f"  ⚠ Rule10: {name}"); return

        sig = get_final_signal(
            state.price_history.get(code, []),
            state.volume_history.get(code, []),
            cur, state.prev_close.get(code, 0), "KR"
        )
        if sig.get("block_reason"):
            print(f"  ⛔ {name}: {sig['block_reason']}"); return

        v = f"B:{sig['buy_votes']} S:{sig['sell_votes']}"
        print(f"  🔍 {name}({code}): {sig['final_signal']} ({v}) | {scan_reason}")

        if sig["final_signal"] != "BUY" or cash < 50000: return

        stops   = calc_stops(code, cur["price"])
        r_check = check_r_multiple(cur["price"], stops["stop_loss"], stops["take_profit"])
        if not r_check["ok"]:
            print(f"  ❌ Rule12: {name} {r_check['reason']}"); return

        qty = calc_size(cash, cur["price"], regime["position_mult"])
        if qty <= 0: return

        order_res = place_order_kr(code, qty, cur["price"], "BUY")
        if order_res.get("rt_cd") != "0":
            print(f"  ❌ KIS 매수 실패: {order_res.get('msg1')}")
            return

        state.positions_kr[code] = {
            "name": name, "qty": qty,
            "buy_price": cur["price"],
            "buy_time":  datetime.now().isoformat(),
            "stop_loss": stops["stop_loss"],
            "take_profit": stops["take_profit"],
        }
        buy_r = " | ".join(s["reason"] for s in sig["strategies"] if s["signal"]=="BUY")
        state.log_trade("BUY", code, name, qty, cur["price"],
                        f"{scan_reason} | {buy_r} | R:{r_check['r']}", "KRW")
    except Exception as e:
        print(f"  ⚠ KR {name}({code}): {e}")

def try_buy_us(ticker, name, scan_reason, cash, regime):
    try:
        cur = get_price_us(ticker)
        state.update_history(ticker, cur["price"], cur["volume"], cur["high"], cur["low"])

        if is_correlated(ticker): return
        if check_news_sentiment(state.recent_news_tags)["blocked"]:
            print(f"  ⚠ Rule10: {name}"); return

        sig = get_final_signal(
            state.price_history.get(ticker, []),
            state.volume_history.get(ticker, []),
            cur, state.prev_close.get(ticker, 0), "US"
        )
        if sig.get("block_reason"):
            print(f"  ⛔ {name}: {sig['block_reason']}"); return

        v = f"B:{sig['buy_votes']} S:{sig['sell_votes']}"
        print(f"  🔍 {name}({ticker}): {sig['final_signal']} ({v}) | {scan_reason}")

        if sig["final_signal"] != "BUY" or cash < 10: return

        stops   = calc_stops(ticker, cur["price"])
        r_check = check_r_multiple(cur["price"], stops["stop_loss"], stops["take_profit"])
        if not r_check["ok"]:
            print(f"  ❌ Rule12: {name} {r_check['reason']}"); return

        qty = max(calc_size(cash, cur["price"], regime["position_mult"]), 1)
        
        order_res = place_order_us(ticker, qty, cur["price"], "BUY")
        if order_res.get("rt_cd") != "0":
            print(f"  ❌ KIS US 매수 실패: {order_res.get('msg1')}")
            return

        state.positions_us[ticker] = {
            "name": name, "qty": qty,
            "buy_price": cur["price"],
            "buy_time":  datetime.now().isoformat(),
            "stop_loss": stops["stop_loss"],
            "take_profit": stops["take_profit"],
        }
        state.log_trade("BUY", ticker, name, qty, cur["price"],
                        f"{scan_reason} | R:{r_check['r']}", "USD")
    except Exception as e:
        print(f"  ⚠ US {name}({ticker}): {e}")

def check_positions_kr():
    for code in list(state.positions_kr):
        try:
            pos   = state.positions_kr[code]
            cur   = get_price_kr(code)
            price = cur["price"]
            state.update_history(code, price, cur["volume"], cur["high"], cur["low"])
            pnl = (price - pos["buy_price"]) * pos["qty"]
            pct = (price - pos["buy_price"]) / pos["buy_price"] * 100

            if price <= pos["stop_loss"]:
                res = place_order_kr(code, pos["qty"], price, "SELL")
                if res.get("rt_cd") == "0":
                    state.daily_pnl += pnl
                    state.log_trade("SELL", code, pos["name"], pos["qty"], price,
                                    f"Rule6 ATR손절 ({pct:+.2f}%)", "KRW", pnl)
                    del state.positions_kr[code]
            elif price >= pos["take_profit"]:
                res = place_order_kr(code, pos["qty"], price, "SELL")
                if res.get("rt_cd") == "0":
                    state.daily_pnl += pnl
                    state.log_trade("SELL", code, pos["name"], pos["qty"], price,
                                    f"Rule12 {TAKE_PROFIT_R}R익절 ({pct:+.2f}%)", "KRW", pnl)
                    del state.positions_kr[code]
            else:
                print(f"  📌 KR {pos['name']}: {pct:+.2f}% | 손절:{pos['stop_loss']:,.0f} 목표:{pos['take_profit']:,.0f}")
            time.sleep(0.8)
        except Exception as e:
            print(f"  ⚠ KR포지션 오류 {code}: {e}")

def check_positions_us():
    for ticker in list(state.positions_us):
        try:
            pos   = state.positions_us[ticker]
            cur   = get_price_us(ticker)
            price = cur["price"]
            state.update_history(ticker, price, cur["volume"], cur["high"], cur["low"])
            pnl = (price - pos["buy_price"]) * pos["qty"]
            pct = (price - pos["buy_price"]) / pos["buy_price"] * 100

            if price <= pos["stop_loss"]:
                res = place_order_us(ticker, pos["qty"], price, "SELL")
                if res.get("rt_cd") == "0":
                    state.daily_pnl += pnl * 1400
                    state.log_trade("SELL", ticker, pos["name"], pos["qty"], price,
                                    f"Rule6 ATR손절 ({pct:+.2f}%)", "USD", pnl)
                    del state.positions_us[ticker]
            elif price >= pos["take_profit"]:
                res = place_order_us(ticker, pos["qty"], price, "SELL")
                if res.get("rt_cd") == "0":
                    state.daily_pnl += pnl * 1400
                    state.log_trade("SELL", ticker, pos["name"], pos["qty"], price,
                                    f"Rule12 {TAKE_PROFIT_R}R익절 ({pct:+.2f}%)", "USD", pnl)
                    del state.positions_us[ticker]
            else:
                print(f"  📌 US {pos['name']}: {pct:+.2f}% | 손절:${pos['stop_loss']:.2f} 목표:${pos['take_profit']:.2f}")
            time.sleep(0.8)
        except Exception as e:
            print(f"  ⚠ US포지션 오류 {ticker}: {e}")

def run_agent():
    print("=" * 62)
    print("  ⚡ QUANT STATION PRO v3.0 [스마트머니 락온 모드]")
    print(f"  모드: {'모의투자' if IS_MOCK else '🔴 실전투자'}")
    print("  엔진: 변동성 스퀴즈 + OBV 기관 매집 + 가격 가속도")
    print("  R1~R12 전략 활성 | KR+US 동시 운용")
    print("=" * 62)

    state.running = True

    try:
        state.start_cash_krw = get_balance_kr()["available_cash_krw"]
        print(f"\n💰 시작 KRW: {state.start_cash_krw:,}원")
    except Exception as e:
        print(f"KRW 잔고 오류: {e}")
    try:
        state.start_cash_usd = get_balance_us()["available_cash_usd"]
        print(f"💵 시작 USD: ${state.start_cash_usd:,.2f}")
    except:
        print("💵 USD: 장외시간 (정상)")

    all_codes = preload_all()

    cycle = 0
    while state.running:
        try:
            if not is_any_open():
                now = datetime.now()
                print(f"[{now.strftime('%H:%M')}] 장 외 대기...")
                if now.hour == 0 and now.minute < 1:
                    state.daily_pnl      = 0
                    state.day_blocked    = False
                    state.scan_candidates = []
                    state.last_scan_time  = 0
                    print("  🔄 일일 리셋")
                time.sleep(60)
                continue

            cycle += 1
            print(f"\n{'='*62}")
            print(f"  Cycle {cycle} | {datetime.now().strftime('%H:%M:%S')} "
                  f"| KR:{'🟢' if is_kr_open() else '⚫'} "
                  f"US:{'🟢' if is_us_open() else '⚫'}")

            if state.day_blocked:
                print("  🚨 Rule8: 거래 중단")
                time.sleep(60); continue

            vix    = get_vix()
            regime = check_market_regime(vix)
            print(f"  📊 {regime['regime']} | {regime['reason']}")

            cash_krw = 0; cash_usd = 0
            try: cash_krw = get_balance_kr()["available_cash_krw"]
            except: pass
            try: cash_usd = get_balance_us()["available_cash_usd"]
            except: pass

            print(f"  💰 KRW:{cash_krw:,}원 | USD:${cash_usd:.2f} | "
                  f"KR:{len(state.positions_kr)}/{MAX_POSITIONS_KR} "
                  f"US:{len(state.positions_us)}/{MAX_POSITIONS_US}")
            print(f"  📈 손익:{state.daily_pnl:+,.0f}원 | "
                  f"승률:{state.win_rate*100:.1f}% | "
                  f"켈리R:{state.avg_win/max(state.avg_loss,0.1):.2f}")

            if state.start_cash_krw > 0:
                if state.daily_pnl / state.start_cash_krw <= DAILY_LOSS_LIMIT:
                    print("  🚨 Rule8: 일손실 한도 도달")
                    state.day_blocked = True; continue

            if is_kr_open() and not check_time_filter("KR")["blocked"]:
                print(f"\n  ━━ 한국 장 ━━")
                check_positions_kr()

                if len(state.positions_kr) < MAX_POSITIONS_KR and regime["allow_buy"]:
                    if time.time() - state.last_scan_time > 600:
                        state.scan_candidates = scan_kr_market(all_codes)
                        state.last_scan_time  = time.time()

                    if not state.scan_candidates:
                        print("  ⚠ 스캔 후보 없음")
                    else:
                        for code, name, score, reason in state.scan_candidates:
                            if len(state.positions_kr) >= MAX_POSITIONS_KR: break
                            try_buy_kr(code, name, reason, cash_krw, regime)
                            time.sleep(1.2)

            if is_us_open() and not check_time_filter("US")["blocked"]:
                print(f"\n  ━━ 미국 장 ━━")
                check_positions_us()

                if len(state.positions_us) < MAX_POSITIONS_US and regime["allow_buy"]:
                    us_top = scan_us_market(regime["position_mult"])
                    print(f"  🔭 US 선정: {[(t,f'{s:.2f}') for t,n,s,r in us_top[:4]]}")
                    for ticker, name, score, reason in us_top:
                        if len(state.positions_us) >= MAX_POSITIONS_US: break
                        try_buy_us(ticker, name, reason, cash_usd, regime)
                        time.sleep(1.2)

            time.sleep(30)

        except KeyboardInterrupt:
            print("\n\n⛔ 에이전트 종료")
            state.running = False
            print(f"\n── 최종 통계 ──")
            print(f"  총 거래: {len(state.trade_log)}건")
            print(f"  승률:    {state.win_rate*100:.1f}%")
            print(f"  손익:    {state.daily_pnl:+,.0f}원")
            print(f"  KR: {list(state.positions_kr.keys())}")
            print(f"  US: {list(state.positions_us.keys())}")
            break
        except Exception as e:
            print(f"\n루프 오류: {e}")
            import traceback; traceback.print_exc()
            time.sleep(10)

if __name__ == "__main__":
    run_agent()