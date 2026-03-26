# ml_engine.py — QUANT 자가학습 최적화 엔진 (Post-Market ML)
import json
import os
import numpy as np
from datetime import datetime

TRADE_LOG_FILE = "trades.json"
CONFIG_FILE = "ml_config.json"

def load_trades():
    if not os.path.exists(TRADE_LOG_FILE): return []
    try:
        with open(TRADE_LOG_FILE, "r") as f:
            return json.load(f)
    except: return []

def load_config():
    default_config = {"min_obv_trend": 0.02, "min_acceleration": 0.1, "learning_rate": 0.1, "last_trained": ""}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except: pass
    return default_config

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def optimize_model():
    print("\n  🧠 [ML Engine] 자가학습 및 파라미터 최적화 시작...")
    trades = load_trades()
    config = load_config()
    
    if len(trades) < 5:
        print("  🧠 [ML Engine] 데이터 부족 (최소 5건 필요). 기존 설정 유지.")
        return config

    win_obvs, win_accs = [], []
    loss_obvs, loss_accs = [], []

    for t in trades:
        if t.get("action") != "BUY": continue
        
        reason = t.get("reason", "")
        
        # [안전장치] 미국 주식 로그(Mom:.. RSI:..)가 섞여 들어오면 학습 생략 
        if "OBV" not in reason or "Accel" not in reason:
            continue
            
        try:
            parts = reason.split("|")
            obv_val = float(parts[0].split(":")[1].strip())
            acc_val = float(parts[1].split(":")[1].strip())
            
            pnl = 0
            for sell_t in trades:
                if sell_t.get("action") == "SELL" and sell_t.get("code") == t.get("code") and sell_t.get("time") > t.get("time"):
                    pnl = sell_t.get("pnl", 0)
                    break
            
            if pnl > 0:
                win_obvs.append(obv_val)
                win_accs.append(acc_val)
            elif pnl < 0:
                loss_obvs.append(obv_val)
                loss_accs.append(acc_val)
        except:
            continue

    lr = config["learning_rate"]
    
    if win_obvs and win_accs:
        avg_win_obv = np.mean(win_obvs)
        avg_win_acc = np.mean(win_accs)
        
        new_obv = config["min_obv_trend"] + lr * (avg_win_obv - config["min_obv_trend"])
        new_acc = config["min_acceleration"] + lr * (avg_win_acc - config["min_acceleration"])
        
        config["min_obv_trend"] = round(max(min(new_obv, 0.1), 0.01), 4)
        config["min_acceleration"] = round(max(min(new_acc, 1.0), 0.05), 4)
        config["last_trained"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        save_config(config)
        
        print(f"  ✅ [ML 학습 완료] 내일의 최적화된 매수 컷오프:")
        print(f"     - 필요 매집강도(OBV): {config['min_obv_trend']:.4f}")
        print(f"     - 필요 폭발력(Accel): {config['min_acceleration']:.4f}")
    else:
        print("  🧠 [ML Engine] 의미 있는 승리 패턴 추출 실패. 유지.")

    return config

if __name__ == "__main__":
    optimize_model()