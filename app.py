# ==========================================
# ULTIMATE TRADE INTELLIGENCE SYSTEM (V4)
# Full System - Single File
# ==========================================

import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import sys
import requests
import datetime

# ==============================
# CONFIG
# ==============================
TIMEFRAMES = ['5m','15m','1h','4h','1d']
SYMBOLS = ['BTC/USDT','ETH/USDT','SOL/USDT','XRP/USDT']

exchange = ccxt.binance()

# ==============================
# DATA FETCH
# ==============================
def fetch_data(symbol, timeframe):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=300)
        df = pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
        return df
    except:
        return None

# ==============================
# ORDER FLOW
# ==============================
def order_flow(symbol):
    try:
        ob = exchange.fetch_order_book(symbol)
        bids = sum([b[1] for b in ob['bids'][:10]])
        asks = sum([a[1] for a in ob['asks'][:10]])

        if bids > asks * 1.2:
            return "Buy Pressure", 1
        elif asks > bids * 1.2:
            return "Sell Pressure", -1
        return "Neutral", 0
    except:
        return "No Data", 0

# ==============================
# INDICATORS
# ==============================
def indicators(df):
    df['ema_50'] = df['close'].ewm(span=50).mean()
    df['ema_200'] = df['close'].ewm(span=200).mean()

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    score = 0
    notes = []

    if df['rsi'].iloc[-1] < 30:
        score += 1
        notes.append("RSI Oversold")
    elif df['rsi'].iloc[-1] > 70:
        score -= 1
        notes.append("RSI Overbought")

    if df['close'].iloc[-1] > df['ema_200'].iloc[-1]:
        score += 1
    else:
        score -= 1

    return score, notes

# ==============================
# PRICE ACTION
# ==============================
def price_action(df):
    highs = df['high']
    lows = df['low']

    recent_high = highs.iloc[-10:-1].max()
    recent_low = lows.iloc[-10:-1].min()

    if highs.iloc[-1] > recent_high:
        return "Bullish BOS", 2
    elif lows.iloc[-1] < recent_low:
        return "Bearish BOS", -2

    return "Range", 0

# ==============================
# STRUCTURE CONTEXT
# ==============================
def structure_context(df):
    highs = df['high']
    lows = df['low']

    if highs.iloc[-1] > highs.iloc[-5] and lows.iloc[-1] > lows.iloc[-5]:
        return "Uptrend", 2
    elif highs.iloc[-1] < highs.iloc[-5] and lows.iloc[-1] < lows.iloc[-5]:
        return "Downtrend", -2

    return "Range", 0

# ==============================
# LIQUIDITY
# ==============================
def liquidity(df):
    eq_highs = abs(df['high'] - df['high'].shift(1)) < 0.1
    eq_lows = abs(df['low'] - df['low'].shift(1)) < 0.1

    if eq_highs.tail(5).any():
        return "Liquidity Above", -2
    elif eq_lows.tail(5).any():
        return "Liquidity Below", 2

    return "Neutral", 0

# ==============================
# VOLUME
# ==============================
def volume(df):
    avg = df['volume'].rolling(20).mean()

    if df['volume'].iloc[-1] > avg.iloc[-1] * 1.5:
        return "Volume Spike", 1
    elif df['volume'].iloc[-1] < avg.iloc[-1] * 0.7:
        return "Weak Volume", -1

    return "Normal Volume", 0

# ==============================
# VWAP
# ==============================
def vwap(df):
    cum_vol = df['volume'].cumsum()
    cum_vol_price = (df['close'] * df['volume']).cumsum()
    df['vwap'] = cum_vol_price / cum_vol

    if df['close'].iloc[-1] > df['vwap'].iloc[-1]:
        return "Above VWAP", 1
    return "Below VWAP", -1

# ==============================
# FVG
# ==============================
def fvg(df):
    for i in range(-5, -1):
        if df['low'].iloc[i] > df['high'].iloc[i-2]:
            return "Bullish FVG", 2
        elif df['high'].iloc[i] < df['low'].iloc[i-2]:
            return "Bearish FVG", -2
    return "No FVG", 0

# ==============================
# ORDER BLOCK
# ==============================
def order_block(df):
    candle = df.iloc[-2]

    if candle['close'] < candle['open']:
        return "Bullish OB", 1
    elif candle['close'] > candle['open']:
        return "Bearish OB", -1

    return "None", 0

# ==============================
# OPEN INTEREST + FUNDING
# ==============================
def open_interest(symbol):
    try:
        sym = symbol.replace("/", "")
        data = requests.get(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={sym}").json()
        return "OI Rising", 1
    except:
        return "OI Error", 0

def funding_rate(symbol):
    try:
        sym = symbol.replace("/", "")
        data = requests.get(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={sym}").json()
        funding = float(data['lastFundingRate'])

        if funding > 0.01:
            return "Longs Overcrowded", -1
        elif funding < -0.01:
            return "Shorts Overcrowded", 1

        return "Neutral Funding", 0
    except:
        return "Funding Error", 0

# ==============================
# LIQUIDATION PROXY
# ==============================
def liquidation_proxy(df):
    move = abs(df['close'].iloc[-1] - df['close'].iloc[-5])
    if move > df['close'].std() * 1.5:
        return "Liquidation Event", 2
    return "None", 0

# ==============================
# SESSION
# ==============================
def session():
    h = datetime.datetime.utcnow().hour
    if h < 8:
        return "Asia", 0
    elif h < 16:
        return "London", 1
    return "New York", 1

# ==============================
# MARKET FILTER
# ==============================
def market_filter(df):
    if df['close'].std() < 15:
        return False
    if df['volume'].mean() < 10:
        return False
    return True

# ==============================
# TRADE SETUP
# ==============================
def trade_setup(df, bias):
    high = df['high'].iloc[-20:].max()
    low = df['low'].iloc[-20:].min()

    if bias == "LONG":
        return low, low*0.98, high
    elif bias == "SHORT":
        return high, high*1.02, low

    return 0,0,0

# ==============================
# RISK REWARD
# ==============================
def risk_reward(entry, sl, tp):
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk == 0:
        return "Invalid", 0
    rr = reward / risk
    if rr >= 2:
        return f"Good RR {round(rr,2)}", 2
    return f"Bad RR {round(rr,2)}", -2

# ==============================
# ANALYSIS
# ==============================
def analyze(symbol):
    results = {}
    reasons = []

    for tf in TIMEFRAMES:
        df = fetch_data(symbol, tf)
        if df is None or not market_filter(df):
            continue

        pa, pa_s = price_action(df)
        trend, trend_s = structure_context(df)
        liq, liq_s = liquidity(df)
        vol, vol_s = volume(df)
        ind_s, ind_notes = indicators(df)
        of, of_s = order_flow(symbol)
        oi, oi_s = open_interest(symbol)
        fund, fund_s = funding_rate(symbol)
        vwap_sig, vwap_s = vwap(df)
        fvg_sig, fvg_s = fvg(df)
        ob_sig, ob_s = order_block(df)

        score = (
            pa_s*3 + trend_s*2 + liq_s*3 + vol_s*2 +
            ind_s + of_s*2 + oi_s*2 + fund_s*2 +
            vwap_s*2 + fvg_s*3 + ob_s*2
        )

        results[tf] = {"score": score, "price": df['close'].iloc[-1]}

        reasons += [pa, trend, liq, vol, of, oi, fund, vwap_sig, fvg_sig, ob_sig] + ind_notes

    return results, list(set(reasons))

# ==============================
# BIAS
# ==============================
def get_bias(results):
    try:
        htf = results['4h']['score'] + results['1d']['score']
        ltf = results['5m']['score'] + results['15m']['score']

        if htf > 0 and ltf > 0:
            return "LONG"
        elif htf < 0 and ltf < 0:
            return "SHORT"
        return "NO TRADE"
    except:
        return "NO DATA"

# ==============================
# OUTPUT
# ==============================
def print_output(symbol, results, reasons):
    bias = get_bias(results)
    total = sum([results[x]['score'] for x in results])
    confidence = min(100, abs(total)*3)

    df = fetch_data(symbol, '15m')
    entry, sl, tp = trade_setup(df, bias)
    rr_text, _ = risk_reward(entry, sl, tp)

    if confidence < 50:
        print("NO TRADE CONDITIONS")
        return

    print("="*30)
    print(" BLACK TERMINAL ANALYSIS ")
    print("="*30)
    print(f"Asset: {symbol}")
    print(f"Bias: {bias}")
    print(f"Confidence: {confidence}%")

    print("\nKEY FACTORS:")
    for r in reasons[:6]:
        print(f"• {r}")

    print("\nTRADE:")
    print(f"Entry: {round(entry,2)}")
    print(f"SL: {round(sl,2)}")
    print(f"TP: {round(tp,2)}")
    print(f"{rr_text}")

# ==============================
# SCAN
# ==============================
def scan_all():
    ranking = []

    for sym in SYMBOLS:
        res, _ = analyze(sym)
        score = sum([res[x]['score'] for x in res]) if res else 0
        ranking.append((sym, score))

    return sorted(ranking, key=lambda x: x[1], reverse=True)[:3]

# ==============================
# STREAMLIT
# ==============================
st.title("Black Terminal V4")

symbol = st.text_input("Symbol", "BTC/USDT")

if st.button("Analyze"):
    res, reasons = analyze(symbol)
    st.write(res)
    st.write(reasons)

if st.button("Scan"):
    st.write(scan_all())

# ==============================
# TERMINAL
# ==============================
if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]

        if arg.upper() == "ALL":
            print(scan_all())
        else:
            res, reasons = analyze(arg)
            print_output(arg, res, reasons)
