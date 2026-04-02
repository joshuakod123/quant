# ml_engine.py — QUANT AI ENGINE (Adam Optimizer & Weighted Gradient)
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
    # [Adam 옵티마이저를 위한 메모리 변수 초기화]
    default_config = {
        "min_obv_trend": 0.0100, 
        "min_acceleration": 0.0150, 
        "m_obv": 0.0, "v_obv": 0.0, 
        "m_acc": 0.0, "v_acc": 0.0,
        "t": 0, 
        "last_trained": ""
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
                for k in default_config:
                    if k not in cfg: cfg[k] = default_config[k]
                return cfg
        except: pass
    return default_config

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def optimize_model():
    print("\n  🧠 [Quant AI Engine] 가동: Adam 기반 하이퍼파라미터 최적화")
    trades = load_trades()
    config = load_config()
    
    # [개선] 3개월 실전 모의를 위한 유연성 (최소 3건의 거래만 있어도 학습 진행)
    if len(trades) < 3:
        print("  🧠 [Quant AI Engine] 표본 부족 (최소 3건). 기존의 정예 컷오프를 유지합니다.")
        return config

    wins, losses = [], []

    for t in trades:
        if t.get("action") != "BUY": continue
        reason = t.get("reason", "")
        if "OBV" not in reason or "Accel" not in reason: continue
            
        try:
            obv_val = float(reason.split("|")[0].split(":")[1].strip())
            acc_val = float(reason.split("|")[1].split(":")[1].strip())
            
            pnl_pct = 0
            for sell_t in trades:
                if sell_t.get("action") == "SELL" and sell_t.get("code") == t.get("code") and sell_t.get("time") > t.get("time"):
                    # [핵심] 단순 승패가 아닌 실제 획득한 % 수익률을 계산
                    pnl_pct = float(sell_t.get("pnl", 0)) / (float(t.get("price", 1)) * float(t.get("qty", 1)))
                    break
            
            if pnl_pct > 0: wins.append([obv_val, acc_val, pnl_pct])
            elif pnl_pct < 0: losses.append([obv_val, acc_val, pnl_pct])
        except: continue

    if not wins or not losses:
        print("  🧠 [Quant AI Engine] 승/패 표본 불균형. 편향 방지를 위해 모델을 동결합니다.")
        return config

    # ─── [수익률 가중치 계산 (Weighted Gradient Ascent)] ───
    win_obvs, win_accs = [w[0] for w in wins], [w[1] for w in wins]
    win_pnls = [w[2] for w in wins]
    
    # 수익률이 높았던 타점일수록 더 강하게 끌어당김 (가중 평균)
    target_obv = np.average(win_obvs, weights=win_pnls)
    target_acc = np.average(win_accs, weights=win_pnls)
    
    # 현재 설정값과의 오차(Gradient)
    grad_obv = target_obv - config["min_obv_trend"]
    grad_acc = target_acc - config["min_acceleration"]

    # ─── [Adam 옵티마이저 알고리즘 (과적합 방지 및 수렴)] ───
    beta1, beta2, lr, eps = 0.9, 0.999, 0.005, 1e-8
    
    config["t"] += 1
    t = config["t"]

    config["m_obv"] = beta1 * config["m_obv"] + (1 - beta1) * grad_obv
    config["v_obv"] = beta2 * config["v_obv"] + (1 - beta2) * (grad_obv ** 2)
    m_hat_obv = config["m_obv"] / (1 - beta1 ** t)
    v_hat_obv = config["v_obv"] / (1 - beta2 ** t)

    config["m_acc"] = beta1 * config["m_acc"] + (1 - beta1) * grad_acc
    config["v_acc"] = beta2 * config["v_acc"] + (1 - beta2) * (grad_acc ** 2)
    m_hat_acc = config["m_acc"] / (1 - beta1 ** t)
    v_hat_acc = config["v_acc"] / (1 - beta2 ** t)

    # 파라미터 업데이트
    new_obv = config["min_obv_trend"] + lr * m_hat_obv / (np.sqrt(v_hat_obv) + eps)
    new_acc = config["min_acceleration"] + lr * m_hat_acc / (np.sqrt(v_hat_acc) + eps)

    # [절대 방어선] 시장이 아무리 좋아도 수학적 한계선(노이즈) 밑으로는 타협 불가
    config["min_obv_trend"] = round(max(min(new_obv, 0.05), 0.005), 4)
    config["min_acceleration"] = round(max(min(new_acc, 0.04), 0.015), 4)
    config["last_trained"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    save_config(config)
    
    print(f"  ✅ [딥러닝 완료] 내일 시장을 파괴할 최적의 락온(Lock-on) 수치:")
    print(f"     - 매집강도(OBV): {config['min_obv_trend']} (변화량: {grad_obv:+.4f})")
    print(f"     - 폭발력(Accel): {config['min_acceleration']} (변화량: {grad_acc:+.4f})")

    return config

if __name__ == "__main__":
    optimize_model()