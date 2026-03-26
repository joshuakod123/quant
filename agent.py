# agent.py — QUANT STATION PRO v4.2 (Real-time HUD Dashboard)
import time
import json
import os
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
    get_vix, check_market_regime, calc_atr, calc_kelly, calc_correlation,
    check_r_multiple, check_news_sentiment, check_time_filter, check_gap_down,
    calc_momentum_score, calc_rsi, calc_bollinger,
    calc_price_acceleration, calc_volatility_adjusted_momentum,
    calc_obv_trend, check_volatility_squeeze, calc_kalman_kinematics
)
import ml_engine 

# ══════════════════════════════════════════════
# 설정
# ══════════════════════════════════════════════
MAX_POSITIONS_KR = 2
MAX_POSITIONS_US = 2
DAILY_LOSS_LIMIT = -0.05
LOG_FILE         = "trades.json"
HISTORY_DAYS     = 40

US_UNIVERSE = {
    "NVDA":"NVIDIA","AMD":"AMD","MSFT":"Microsoft","META":"Meta","AAPL":"Apple",
    "TSLA":"Tesla","SOXL":"반도체3x","TQQQ":"나스닥3x","COIN":"Coinbase"
}

ml_config = ml_engine.load_config()

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

    def update_history(self, code, price, volume, high=0, low=0):
        for d, v in [(self.price_history, float(price)), (self.volume_history, int(volume)),
                     (self.high_history, float(high or price)), (self.low_history, float(low or price))]:
            d.setdefault(code, []).append(v)
            if len(d[code]) > 120: d[code].pop(0)
        ph = self.price_history[code]
        if len(ph) >= 2:
            self.returns_history.setdefault(code, []).append((ph[-1] - ph[-2]) / ph[-2])
            if len(self.returns_history[code]) > 60: self.returns_history[code].pop(0)

    def preload(self, code, df):
        if df is None or len(df) < 5: return
        self.price_history[code]  = df["Close"].tolist()
        self.volume_history[code] = df["Volume"].tolist()
        self.high_history[code]   = df["High"].tolist()
        self.low_history[code]    = df["Low"].tolist()
        closes = df["Close"].tolist()
        if len(closes) >= 2:
            self.returns_history[code] = [(closes[i]-closes[i-1])/closes[i-1] for i in range(1, len(closes))]
        if closes: self.prev_close[code] = float(closes[-1])

    def log_trade(self, action, code, name, qty, price, reason, currency="KRW", pnl=0):
        entry = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "action": action, "code": code, "name": name,
                 "qty": qty, "price": price, "currency": currency, "reason": reason, "pnl": pnl}
        self.trade_log.append(entry)
        if pnl > 0:
            self.win_trades += 1
            self.total_win_pct += abs(pnl/(price*qty))*100 if qty > 0 else 0
        elif pnl < 0:
            self.loss_trades += 1
            self.total_loss_pct += abs(pnl/(price*qty))*100 if qty > 0 else 0
        with open(LOG_FILE, "w") as f:
            json.dump(self.trade_log, f, ensure_ascii=False, indent=2)

    @property
    def win_rate(self): return self.win_trades / (self.win_trades + self.loss_trades) if (self.win_trades + self.loss_trades) > 0 else 0.5
    @property
    def avg_win(self): return self.total_win_pct / self.win_trades if self.win_trades > 0 else 1.0
    @property
    def avg_loss(self): return self.total_loss_pct / self.loss_trades if self.loss_trades > 0 else 0.6

state = AgentState()

def load_history(code: str) -> bool:
    try:
        df = fdr.DataReader(code, (datetime.now() - timedelta(days=HISTORY_DAYS + 10)).strftime("%Y-%m-%d"), datetime.now().strftime("%Y-%m-%d"))
        if df is None or len(df) < 5: return False
        state.preload(code, df.tail(HISTORY_DAYS))
        return True
    except: return False

def preload_all():
    print("\n  📚 퀀트 엔진: 전 종목 스캔 준비 중...")
    try:
        listing = fdr.StockListing('KRX')
        listing.columns = [c.strip() for c in listing.columns]
        c_col = next((c for c in listing.columns if "Code" in c or "종목코드" in c), None)
        n_col = next((c for c in listing.columns if "Name" in c or "종목명" in c), None)
        all_codes = {str(row[c_col]).zfill(6): str(row[n_col]) for _, row in listing.iterrows()}
        
        if len(all_codes) < 100: raise ValueError("데이터 제공자 오류: 종목 수 부족")
            
        print(f"  ✅ 전체 시장 {len(all_codes)}개 타겟팅 완료.")
        return all_codes
    except Exception as e:
        print(f"  ⚠ 서버 에러 감지: {e}\n  🔄 플랜 B 가동: 비상 풀(Pool) 전환")
        return {
            "005930":"삼성전자","000660":"SK하이닉스","042700":"한미반도체",
            "005380":"현대차","069500":"KODEX 200","122630":"KODEX 레버리지",
            "133690":"TIGER 미국나스닥100", "028260":"삼성물산", "105560":"KB금융"
        }

def scan_kr_market(all_codes: dict) -> list:
    global ml_config
    print("  🔭 [Apex Model] ML 자가학습 컷오프 적용 스캔 중...")
    candidates = []
    start = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")

    target_obv = ml_config.get("min_obv_trend", 0.02)
    target_acc = ml_config.get("min_acceleration", 0.1)

    scanned = 0
    for code, name in list(all_codes.items())[:1000]: 
        try:
            df = fdr.DataReader(code, start, today)
            if df is None or len(df) < 30: continue
            close, volume = float(df["Close"].iloc[-1]), int(df["Volume"].iloc[-1])
            if not (1000 <= close <= 200000) or volume < 30000: continue

            state.preload(code, df.tail(HISTORY_DAYS))
            ph = state.price_history.get(code, [])
            vh = state.volume_history.get(code, [])
            hh = state.high_history.get(code, [])
            lh = state.low_history.get(code, [])

            if len(ph) < 20: continue

            is_squeezed = check_volatility_squeeze(ph, hh, lh, period=20)
            obv_trend = calc_obv_trend(ph, vh, period=14)
            kinematics = calc_kalman_kinematics(ph)
            vel, acc = kinematics["velocity"], kinematics["acceleration"]

            if acc > target_acc and (is_squeezed or obv_trend > target_obv):
                score = (acc * 5.0) + (obv_trend * 10.0) + (vel * 2.0) + (2.0 if is_squeezed else 0)
                reason = f"OBV:{obv_trend:.3f} | Accel:{acc:.2f} | SQZ:{'ON' if is_squeezed else 'OFF'}"
                candidates.append((code, name, score, reason))
            scanned += 1
        except: continue

    candidates.sort(key=lambda x: x[2], reverse=True)
    top = candidates[:5]
    print(f"  ✅ {scanned}개 스캔 완료 → 락온 타점 {len(top)}개 발견")
    return top

def scan_us_market(regime_mult: float) -> list:
    candidates = []
    start = (datetime.now() - timedelta(days=HISTORY_DAYS+5)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    for ticker, name in US_UNIVERSE.items():
        try:
            df = fdr.DataReader(ticker, start, today)
            if df is not None and len(df) >= 5: state.preload(ticker, df.tail(HISTORY_DAYS))
            ph, vh = state.price_history.get(ticker, []), state.volume_history.get(ticker, [])
            if len(ph) < 5: continue
            mom, rsi, bb = calc_momentum_score(ph, vh), calc_rsi(ph), calc_bollinger(ph)
            score = mom + (0.2 if rsi < 35 else (-0.15 if rsi > 75 else 0)) + (0.15 if bb["pct_b"] < 0.25 else 0)
            candidates.append((ticker, name, score, f"Mom:{mom:.2f} RSI:{rsi:.0f}"))
        except: continue
    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates[:5]

def is_any_open():
    now = datetime.now()
    if now.weekday() >= 5: return False
    kr_open = (9 <= now.hour < 15) or (now.hour == 15 and now.minute <= 20)
    us_open = now.hour >= 22 or now.hour < 5
    return kr_open or us_open

def is_kr_open():
    now = datetime.now()
    return not (now.weekday() >= 5) and ((9 <= now.hour < 15) or (now.hour == 15 and now.minute <= 20))

def is_us_open():
    now = datetime.now()
    return not (now.weekday() >= 5) and (now.hour >= 22 or now.hour < 5)

def calc_size(cash, price, regime_mult):
    kelly = calc_kelly(state.win_rate, state.avg_win, state.avg_loss)
    return max(int(cash * max(min(kelly * regime_mult, 0.35), 0.05) / price), 0)

def is_correlated(code):
    new_r = state.returns_history.get(code, [])
    if not new_r: return False
    for held in list(state.positions_kr) + list(state.positions_us):
        if calc_correlation(new_r, state.returns_history.get(held, [])) > 0.7: return True
    return False

def try_buy_kr(code, name, scan_reason, cash, regime):
    try:
        if len(state.price_history.get(code, [])) < 20: load_history(code)
        cur = get_price_kr(code)
        state.update_history(code, cur["price"], cur["volume"], cur["high"], cur["low"])
        
        if is_correlated(code): return print(f"     👉 [패스] {name}: 상관성 초과")
        if check_news_sentiment(state.recent_news_tags)["blocked"]: return print(f"     👉 [패스] {name}: 뉴스 리스크")
        if check_time_filter("KR")["blocked"]: return print(f"     👉 [패스] {name}: 장초/장막판")
        if check_gap_down(cur.get("open", cur["price"]), state.prev_close.get(code, 0))["blocked"]: return print(f"     👉 [패스] {name}: 갭다운")
        if cash < 50000: return print(f"     👉 [패스] {name}: 예수금 부족")

        qty = calc_size(cash, cur["price"], regime["position_mult"])
        if qty <= 0: return

        order_res = place_order_kr(code, qty, cur["price"], "BUY")
        if order_res.get("rt_cd") != "0": return print(f"     ❌ 매수 거절: {order_res.get('msg1')}")

        state.positions_kr[code] = {
            "name": name, "qty": qty, "buy_price": cur["price"],
            "stop_loss": cur["price"] * 0.994,     
            "take_profit": cur["price"] * 1.010,   
            "highest_price": cur["price"]          
        }
        state.log_trade("BUY", code, name, qty, cur["price"], scan_reason, "KRW")
        print(f"     🚀 [매수 체결] {name}({code}) {qty}주 @ {cur['price']:,}원")
    except Exception as e: print(f"  ⚠ KR 오류: {e}")

def try_buy_us(ticker, name, scan_reason, cash, regime):
    try:
        cur = get_price_us(ticker)
        state.update_history(ticker, cur["price"], cur["volume"], cur["high"], cur["low"])
        
        if is_correlated(ticker) or check_news_sentiment(state.recent_news_tags)["blocked"] or check_time_filter("US")["blocked"] or cash < 10: return
        qty = max(calc_size(cash, cur["price"], regime["position_mult"]), 1)
        
        order_res = place_order_us(ticker, qty, cur["price"], "BUY")
        if order_res.get("rt_cd") != "0": return

        state.positions_us[ticker] = {
            "name": name, "qty": qty, "buy_price": cur["price"],
            "stop_loss": cur["price"] * 0.994, 
            "take_profit": cur["price"] * 1.010,
            "highest_price": cur["price"]
        }
        state.log_trade("BUY", ticker, name, qty, cur["price"], scan_reason, "USD")
        print(f"     🚀 [매수 체결] {name}({ticker}) {qty}주 @ ${cur['price']:.2f}")
    except Exception as e: print(f"  ⚠ US 오류: {e}")

def check_positions_kr():
    if not state.positions_kr:
        print("  📦 보유 종목: 없음")
        return

    print(f"  📦 보유 종목 ({len(state.positions_kr)}/{MAX_POSITIONS_KR})")
    for code in list(state.positions_kr):
        try:
            pos = state.positions_kr[code]
            cur = get_price_kr(code)
            price = cur["price"]
            state.update_history(code, price, cur["volume"], cur["high"], cur["low"])
            
            if price > pos.get("highest_price", price): pos["highest_price"] = price
            pnl = (price - pos["buy_price"]) * pos["qty"]
            pct = (price - pos["buy_price"]) / pos["buy_price"] * 100

            kinematics = calc_kalman_kinematics(state.price_history.get(code, []))
            acc = kinematics["acceleration"]

            # 매도 조건 체크
            sold = False
            if pct < -0.2 and acc < -0.2:
                res = place_order_kr(code, pos["qty"], 0, "SELL") 
                if res.get("rt_cd") == "0":
                    state.daily_pnl += pnl
                    state.log_trade("SELL", code, pos["name"], pos["qty"], price, f"조기 손절(Early Cut)", "KRW", pnl)
                    del state.positions_kr[code]; state.last_scan_time = 0; sold = True
                    print(f"     🔴 [청산] {pos['name']} 가속도 붕괴 조기 손절 ({pct:+.2f}%)")
            
            elif price <= pos["stop_loss"] and not sold:
                res = place_order_kr(code, pos["qty"], 0, "SELL") 
                if res.get("rt_cd") == "0":
                    state.daily_pnl += pnl
                    state.log_trade("SELL", code, pos["name"], pos["qty"], price, f"하드 손절 (-0.6%)", "KRW", pnl)
                    del state.positions_kr[code]; state.last_scan_time = 0; sold = True
                    print(f"     🔴 [청산] {pos['name']} 하드 손절 도달 ({pct:+.2f}%)")
            
            elif price >= pos["take_profit"] and not sold:
                if acc > 0.05: 
                    pos["take_profit"] = price * 1.01
                    pos["stop_loss"] = price * 0.995 
                    print(f"     🔥 [돌파] {pos['name']} 수익률 {pct:+.2f}% 돌파! 가속도 양호, 목표가 상향 (Trailing)")
                else: 
                    res = place_order_kr(code, pos["qty"], 0, "SELL")
                    if res.get("rt_cd") == "0":
                        state.daily_pnl += pnl
                        state.log_trade("SELL", code, pos["name"], pos["qty"], price, f"기계적 익절 (+1.0%)", "KRW", pnl)
                        del state.positions_kr[code]; state.last_scan_time = 0; sold = True
                        print(f"     🟢 [청산] {pos['name']} 기계적 익절 완료 ({pct:+.2f}%)")
            
            if not sold:
                print(f"     📌 {pos['name']} | 수익: {pct:+.2f}% | 현재가: {price:,}원 (목표: {pos['take_profit']:,.0f} / 손절: {pos['stop_loss']:,.0f}) | Acc: {acc:.2f}")
            time.sleep(0.5)
        except Exception as e: print(f"  ⚠ KR포지션 오류 {code}: {e}")

def check_positions_us():
    if not state.positions_us:
        print("  📦 보유 종목: 없음")
        return

    print(f"  📦 보유 종목 ({len(state.positions_us)}/{MAX_POSITIONS_US})")
    for ticker in list(state.positions_us):
        try:
            pos = state.positions_us[ticker]
            cur = get_price_us(ticker)
            price = cur["price"]
            state.update_history(ticker, price, cur["volume"], cur["high"], cur["low"])
            
            if price > pos.get("highest_price", price): pos["highest_price"] = price
            pnl = (price - pos["buy_price"]) * pos["qty"]
            pct = (price - pos["buy_price"]) / pos["buy_price"] * 100

            kinematics = calc_kalman_kinematics(state.price_history.get(ticker, []))
            acc = kinematics["acceleration"]

            sold = False
            if pct < -0.2 and acc < -0.2:
                res = place_order_us(ticker, pos["qty"], price, "SELL")
                if res.get("rt_cd") == "0":
                    state.daily_pnl += pnl * 1400
                    state.log_trade("SELL", ticker, pos["name"], pos["qty"], price, f"조기 손절", "USD", pnl)
                    del state.positions_us[ticker]; state.last_scan_time = 0; sold = True
            elif price <= pos["stop_loss"] and not sold:
                res = place_order_us(ticker, pos["qty"], price, "SELL")
                if res.get("rt_cd") == "0":
                    state.daily_pnl += pnl * 1400
                    state.log_trade("SELL", ticker, pos["name"], pos["qty"], price, f"하드 손절 (-0.6%)", "USD", pnl)
                    del state.positions_us[ticker]; state.last_scan_time = 0; sold = True
            elif price >= pos["take_profit"] and not sold:
                if acc > 0.05:
                    pos["take_profit"] = price * 1.01
                    pos["stop_loss"] = price * 0.995 
                else:
                    res = place_order_us(ticker, pos["qty"], price, "SELL")
                    if res.get("rt_cd") == "0":
                        state.daily_pnl += pnl * 1400
                        state.log_trade("SELL", ticker, pos["name"], pos["qty"], price, f"기계적 익절 (+1.0%)", "USD", pnl)
                        del state.positions_us[ticker]; state.last_scan_time = 0; sold = True
            
            if not sold:
                print(f"     📌 {pos['name']} | 수익: {pct:+.2f}% | 현재가: ${price:.2f} (목표: ${pos['take_profit']:.2f} / 손절: ${pos['stop_loss']:.2f}) | Acc: {acc:.2f}")
            time.sleep(0.5)
        except Exception as e: print(f"  ⚠ US포지션 오류 {ticker}: {e}")

def run_agent():
    global ml_config
    print("\n\n" + "=" * 65)
    print("  ⚡ QUANT STATION PRO v4.2 [Real-time HUD Dashboard]")
    print(f"  모드: {'모의투자' if IS_MOCK else '🔴 실전투자'}")
    print(f"  엔진: 칼만 필터 + 1.0% 초단타 + 트레일링 스탑")
    print("=" * 65)

    state.running = True
    all_codes = preload_all()

    cycle = 0
    while state.running:
        try:
            now = datetime.now()
            
            # 자정 ML 엔진 구동
            if now.hour == 0 and now.minute < 1:
                ml_config = ml_engine.optimize_model()
                state.daily_pnl = 0; state.day_blocked = False
                time.sleep(60) 
                continue

            if not is_any_open():
                print(f"[{now.strftime('%H:%M')}] 장 외 대기 중...")
                time.sleep(60)
                continue

            cycle += 1
            vix = get_vix()
            regime = check_market_regime(vix)
            
            try: cash_krw = get_balance_kr()["available_cash_krw"]
            except: cash_krw = 0
            try: cash_usd = get_balance_us()["available_cash_usd"]
            except: cash_usd = 0

            # ─── 대시보드 헤더 출력 ───
            print(f"\n\n{'='*65}")
            print(f" 🕒 Cycle {cycle} | {now.strftime('%H:%M:%S')} | KR:{'🟢' if is_kr_open() else '⚫'} US:{'🟢' if is_us_open() else '⚫'}")
            print(f" 📊 {regime['regime']} | {regime['reason']}")
            print(f" 💰 예수금: {cash_krw:,}원 / ${cash_usd:,.2f} | 📈 오늘 누적 손익: {state.daily_pnl:+,.0f}원")
            print(f"{'-'*65}")

            if state.day_blocked:
                print("  🚨 Rule8: 일일 손실 한도로 거래 중단"); time.sleep(60); continue

            # ─── 한국장 ───
            if is_kr_open():
                print(f"  [🇰🇷 한국 장 실시간 모니터링]")
                check_positions_kr()
                
                if len(state.positions_kr) >= MAX_POSITIONS_KR:
                    print(f"  🔒 포지션 한도 도달 ({MAX_POSITIONS_KR}/{MAX_POSITIONS_KR}) - 신규 매수 차단")
                elif regime["allow_buy"]:
                    time_left = 600 - (time.time() - state.last_scan_time)
                    if time_left <= 0:
                        candidates = scan_kr_market(all_codes)
                        state.last_scan_time = time.time()
                        
                        if not candidates:
                            print("  💤 현재 시장에 조건(ML컷오프)을 만족하는 타점이 없습니다.")
                            
                        for code, name, score, reason in candidates:
                            if len(state.positions_kr) >= MAX_POSITIONS_KR: break
                            try_buy_kr(code, name, reason, cash_krw, regime)
                            time.sleep(1.0)
                    else:
                        print(f"  ⏳ 다음 전체 스캔까지 {int(time_left)}초 남음...")
                print(f"{'-'*65}")

            # ─── 미국장 ───
            if is_us_open():
                print(f"  [🇺🇸 미국 장 실시간 모니터링]")
                check_positions_us()
                
                if len(state.positions_us) >= MAX_POSITIONS_US:
                    print(f"  🔒 포지션 한도 도달 ({MAX_POSITIONS_US}/{MAX_POSITIONS_US})")
                elif regime["allow_buy"]:
                    time_left = 600 - (time.time() - state.last_scan_time)
                    if time_left <= 0:
                        candidates = scan_us_market(regime["position_mult"])
                        for ticker, name, score, reason in candidates:
                            if len(state.positions_us) >= MAX_POSITIONS_US: break
                            try_buy_us(ticker, name, reason, cash_usd, regime)
                            time.sleep(1.0)
                    else:
                        print(f"  ⏳ 다음 전체 스캔까지 {int(time_left)}초 남음...")
                print(f"{'-'*65}")

            time.sleep(30)

        except KeyboardInterrupt:
            state.running = False
            print(f"\n\n⛔ 에이전트 종료\n── 최종 통계 ──\n  총 거래: {len(state.trade_log)}건\n  승률: {state.win_rate*100:.1f}%\n  손익: {state.daily_pnl:+,.0f}원")
            break
        except Exception as e:
            print(f"\n루프 오류: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_agent()