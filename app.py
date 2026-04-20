import requests
import pandas as pd
import numpy as np
import os
import datetime
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange

# =========================
# OLLAMA (LOCAL AI)
# =========================
def ollama_generate(prompt, model="llama3"):
    try:
        res = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=20
        )
        return res.json().get("response", "")
    except Exception as e:
        return f"AI error: {e}"

# =========================
# CONFIG
# =========================
SYMBOL = "BTCUSDT"
LIMIT = 300
RISK_REWARD_MIN = 2

# =========================
# DATA
# =========================
def get_binance_data(symbol, interval, limit):
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        data = requests.get(url, params=params, timeout=10).json()

        if not isinstance(data, list):
            return pd.DataFrame()

        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume",
            "close_time","qav","trades","tbbav","tbqav","ignore"
        ])

        for col in ["open","high","low","close","volume"]:
            df[col] = df[col].astype(float)

        return df

    except:
        return pd.DataFrame()

def get_funding_rate():
    try:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT"
        return float(requests.get(url, timeout=5).json().get("lastFundingRate", 0))
    except:
        return 0

# =========================
# INDICATORS
# =========================
def apply_indicators(df):
    if df.empty or len(df) < 50:
        return df

    df["ema_50"] = EMAIndicator(df["close"], 50).ema_indicator()
    df["ema_200"] = EMAIndicator(df["close"], 200).ema_indicator()
    df["rsi"] = RSIIndicator(df["close"], 14).rsi()
    df["atr"] = AverageTrueRange(df["high"], df["low"], df["close"]).average_true_range()

    df = df.dropna()
    return df

# =========================
# MULTI TIMEFRAME
# =========================
def get_multi_tf():
    df_1h = apply_indicators(get_binance_data(SYMBOL, "1h", LIMIT))
    df_4h = apply_indicators(get_binance_data(SYMBOL, "4h", LIMIT))
    df_1d = apply_indicators(get_binance_data(SYMBOL, "1d", LIMIT))
    return df_1h, df_4h, df_1d

def get_trend(df):
    if df.empty:
        return "neutral"

    if df["ema_50"].iloc[-1] > df["ema_200"].iloc[-1]:
        return "bullish"
    elif df["ema_50"].iloc[-1] < df["ema_200"].iloc[-1]:
        return "bearish"
    return "neutral"

def mtf_filter(df_4h, df_1d, decision):
    t4 = get_trend(df_4h)
    t1 = get_trend(df_1d)

    if "LONG" in decision and (t4 != "bullish" or t1 != "bullish"):
        return "NO TRADE"
    if "SHORT" in decision and (t4 != "bearish" or t1 != "bearish"):
        return "NO TRADE"

    return decision

# =========================
# ENGINES
# =========================
def safe_len(df, n):
    return len(df) >= n

def price_action(df):
    if not safe_len(df, 5):
        return 0

    score = 0
    if df["high"].iloc[-1] > df["high"].iloc[-5]:
        score += 2
    if df["low"].iloc[-1] > df["low"].iloc[-5]:
        score += 1
    if df["high"].iloc[-1] < df["high"].iloc[-5]:
        score -= 2

    return score

def structure(df):
    if not safe_len(df, 10):
        return 0

    high = df["high"].iloc[-10:-1].max()
    low = df["low"].iloc[-10:-1].min()
    price = df["close"].iloc[-1]

    if price > high:
        return 3
    elif price < low:
        return -3
    return 0

def volume(df):
    if not safe_len(df, 20):
        return 0

    avg = df["volume"].rolling(20).mean().iloc[-1]
    v = df["volume"].iloc[-1]

    if v > avg * 1.5:
        return 2
    elif v < avg * 0.7:
        return -1
    return 0

def liquidity(df):
    if not safe_len(df, 30):
        return 0

    high = df["high"].rolling(30).max().iloc[-2]
    low = df["low"].rolling(30).min().iloc[-2]

    if df["high"].iloc[-1] > high:
        return -2
    if df["low"].iloc[-1] < low:
        return 2
    return 0

def order_block(df):
    if not safe_len(df, 6):
        return 0

    score = 0
    for i in range(-5, -1):
        c = df.iloc[i]
        n = df.iloc[i+1]

        if c["close"] < c["open"] and n["close"] > n["open"]:
            score += 1
        if c["close"] > c["open"] and n["close"] < n["open"]:
            score -= 1

    return score

def fvg(df):
    if not safe_len(df, 20):
        return 0

    score = 0
    recent = df.tail(20)

    for i in range(2, len(recent)):
        if recent["low"].iloc[i] > recent["high"].iloc[i-2]:
            score += 1
        if recent["high"].iloc[i] < recent["low"].iloc[i-2]:
            score -= 1

    return score

def indicators(df):
    score = 0

    if df["close"].iloc[-1] > df["ema_50"].iloc[-1]:
        score += 1

    if df["rsi"].iloc[-1] > 60:
        score += 1
    elif df["rsi"].iloc[-1] < 40:
        score -= 1

    return score

def sentiment():
    f = get_funding_rate()
    if f > 0.01:
        return -2
    elif f < -0.01:
        return 2
    return 0

def liquidation():
    try:
        url = "https://fapi.binance.com/fapi/v1/forceOrders?symbol=BTCUSDT&limit=50"
        data = requests.get(url, timeout=5).json()

        if not isinstance(data, list):
            return 0

        long_liq = 0
        short_liq = 0

        for order in data:
            qty = float(order.get("origQty", 0))
            if order.get("side") == "SELL":
                long_liq += qty
            else:
                short_liq += qty

        if long_liq > short_liq * 1.5:
            return -2
        elif short_liq > long_liq * 1.5:
            return 2

        return 0
    except:
        return 0

# =========================
# FILTERS
# =========================
def volatility_ok(df):
    if not safe_len(df, 50):
        return False

    atr = df["atr"].iloc[-1]
    avg = df["atr"].rolling(50).mean().iloc[-1]

    return atr > avg * 0.7

def entry_confirm(df):
    if not safe_len(df, 20):
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    avg_vol = df["volume"].rolling(20).mean().iloc[-1]
    vol_spike = df["volume"].iloc[-1] > avg_vol * 1.5

    if last["close"] > last["open"] and prev["close"] < prev["open"] and vol_spike:
        return "LONG"

    if last["close"] < last["open"] and prev["close"] > prev["open"] and vol_spike:
        return "SHORT"

    return None

# =========================
# DECISION
# =========================
def decide(scores):
    total = max(min(sum(scores.values()), 10), -10)

    if total >= 6:
        return "STRONG LONG", total
    elif total >= 3:
        return "LONG", total
    elif total <= -6:
        return "STRONG SHORT", total
    elif total <= -3:
        return "SHORT", total
    return "NO TRADE", total

# =========================
# RISK
# =========================
def risk(df, decision):
    price = df["close"].iloc[-1]
    atr = df["atr"].iloc[-1]

    if "LONG" in decision:
        sl = price - atr * 1.5
        tp1 = price + atr * 1.5
        tp2 = price + atr * 3
    elif "SHORT" in decision:
        sl = price + atr * 1.5
        tp1 = price - atr * 1.5
        tp2 = price - atr * 3
    else:
        return None

    rr = abs((tp2 - price) / (price - sl))

    if rr < RISK_REWARD_MIN:
        return None

    return {
        "entry": price,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "rr": rr
    }

# =========================
# AI + LOGGING
# =========================
def load_trade_memory(file="trades.csv", limit=20):
    if not os.path.exists(file):
        return "No past trades."

    try:
        df = pd.read_csv(file)
        return df.tail(limit).to_string(index=False)
    except:
        return "Memory error"

def ai_explain(scores, decision):
    memory = load_trade_memory()

    prompt = f"""
You are a trading analyst.

Past trades:
{memory}

Scores: {scores}
Decision: {decision}

Explain the setup briefly.
"""
    return ollama_generate(prompt)

def log_trade(data, file="trades.csv"):
    df = pd.DataFrame([data])
    df.to_csv(file, mode="a", header=not os.path.exists(file), index=False)

# =========================
# MAIN
# =========================
def run():
    df, df4, df1 = get_multi_tf()

    if df.empty or len(df) < 100:
        print("Not enough data")
        return

    if not volatility_ok(df):
        print("Low volatility → NO TRADE")
        return

    scores = {
        "pa": price_action(df),
        "structure": structure(df),
        "volume": volume(df),
        "liquidity": liquidity(df),
        "ob": order_block(df),
        "fvg": fvg(df),
        "ind": indicators(df),
        "sentiment": sentiment(),
        "liq_data": liquidation()
    }

    decision, total = decide(scores)
    decision = mtf_filter(df4, df1, decision)

    confirm = entry_confirm(df)

    if decision == "LONG" and confirm != "LONG":
        scores["entry_penalty"] = -2
    elif decision == "SHORT" and confirm != "SHORT":
        scores["entry_penalty"] = -2
    else:
        scores["entry_penalty"] = 0

    decision, total = decide(scores)

    trade = risk(df, decision)

    print("\n===== OUTPUT =====")
    print("Scores:", scores)
    print("Total:", total)
    print("Decision:", decision)

    if trade:
        print("\nTrade Setup:")
        print(f"Entry: {trade['entry']}")
        print(f"SL: {trade['sl']}")
        print(f"TP1: {trade['tp1']}")
        print(f"TP2: {trade['tp2']}")
        print(f"R:R: {trade['rr']:.2f}")
    else:
        print("No valid trade")

    print("\nAI:")
    print(ai_explain(scores, decision))

    log_trade({
        "decision": decision,
        "score_total": total,
        "scores": str(scores)
    })
    
import pandas as pd
import numpy as np
import requests
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange

# =========================
# CONFIG
# =========================
SYMBOL = "BTCUSDT"
INITIAL_BALANCE = 1000
RISK_PER_TRADE = 0.01
FEE = 0.0004  # 0.04% per trade

# =========================
# DATA
# =========================
def get_data(symbol="BTCUSDT", interval="1h", limit=1500):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    data = requests.get(url, params=params).json()

    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "ct","qav","trades","tb","tq","ignore"
    ])

    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)

    return df

# =========================
# INDICATORS
# =========================
def add_indicators(df):
    df["ema50"] = EMAIndicator(df["close"], 50).ema_indicator()
    df["ema200"] = EMAIndicator(df["close"], 200).ema_indicator()
    df["rsi"] = RSIIndicator(df["close"], 14).rsi()
    df["atr"] = AverageTrueRange(df["high"], df["low"], df["close"]).average_true_range()
    return df.dropna()

# =========================
# SIGNAL (NON-SUBJECTIVE)
# =========================
def generate_signal(df, i):
    row = df.iloc[i]

    trend = row["ema50"] > row["ema200"]
    momentum = row["rsi"] > 55
    pullback = df["close"].iloc[i-1] < df["ema50"].iloc[i-1]

    short_trend = row["ema50"] < row["ema200"]
    short_momentum = row["rsi"] < 45
    short_pullback = df["close"].iloc[i-1] > df["ema50"].iloc[i-1]

    if trend and momentum and pullback:
        return "LONG"
    elif short_trend and short_momentum and short_pullback:
        return "SHORT"

    return None

# =========================
# POSITION SIZE
# =========================
def position_size(balance, entry, sl):
    risk = balance * RISK_PER_TRADE
    dist = abs(entry - sl)
    if dist == 0:
        return 0
    return risk / dist

# =========================
# TRADE SIM
# =========================
def simulate(df, i, direction, entry, sl, tp):
    for j in range(i+1, len(df)):
        high = df["high"].iloc[j]
        low = df["low"].iloc[j]

        if direction == "LONG":
            if low <= sl:
                return sl, "LOSS"
            if high >= tp:
                return tp, "WIN"

        if direction == "SHORT":
            if high >= sl:
                return sl, "LOSS"
            if low <= tp:
                return tp, "WIN"

    return entry, "OPEN"

# =========================
# BACKTEST
# =========================
def backtest(df):
    balance = INITIAL_BALANCE
    equity = [balance]

    wins = 0
    losses = 0
    trades = []

    for i in range(200, len(df)-1):
        signal = generate_signal(df, i)

        if not signal:
            continue

        price = df["close"].iloc[i]
        atr = df["atr"].iloc[i]

        if signal == "LONG":
            sl = price - atr * 1.5
            tp = price + atr * 3
        else:
            sl = price + atr * 1.5
            tp = price - atr * 3

        size = position_size(balance, price, sl)
        if size == 0:
            continue

        exit_price, result = simulate(df, i, signal, price, sl, tp)

        if result == "OPEN":
            continue

        # Apply fees
        fee_cost = price * size * FEE * 2

        if signal == "LONG":
            pnl = (exit_price - price) * size - fee_cost
        else:
            pnl = (price - exit_price) * size - fee_cost

        balance += pnl
        equity.append(balance)

        if pnl > 0:
            wins += 1
        else:
            losses += 1

        trades.append(pnl)

    return trades, equity, wins, losses

# =========================
# METRICS
# =========================
def metrics(trades, equity, wins, losses):
    if len(trades) == 0:
        print("No trades")
        return

    winrate = wins / len(trades) * 100

    avg_win = np.mean([t for t in trades if t > 0])
    avg_loss = np.mean([t for t in trades if t < 0])

    peak = equity[0]
    dd = []

    for x in equity:
        peak = max(peak, x)
        dd.append((peak - x) / peak)

    print("\n===== RESULTS =====")
    print(f"Trades: {len(trades)}")
    print(f"Winrate: {winrate:.2f}%")
    print(f"Avg Win: {avg_win:.2f}")
    print(f"Avg Loss: {avg_loss:.2f}")
    print(f"Max DD: {max(dd)*100:.2f}%")
    print(f"Final Balance: {equity[-1]:.2f}")

# =========================
# RUN
# =========================
df = get_data()
df = add_indicators(df)

trades, equity, wins, losses = backtest(df)
metrics(trades, equity, wins, losses)

# =========================
# RUN
# =========================
run_backtest()
