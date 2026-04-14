import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time

st.set_page_config(page_title="Trade Bot PRO MAX", layout="wide")

st.title("🚀 Trade Bot PRO MAX - Institutional System")

symbols = ["BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD"]
timeframe = st.selectbox("Timeframe", ["5m","15m","1h"])

# =========================
# DATA FETCH
# =========================
@st.cache_data
def get_data(symbol, timeframe):
    try:
        df = yf.download(
            tickers=symbol,
            period="7d",
            interval=timeframe
        )

        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })

        df = df.reset_index()
        return df

    except Exception as e:
        st.warning(f"Data error: {e}")
        return pd.DataFrame()

# =========================
# INDICATORS
# =========================
def add_indicators(df):
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()

    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()

    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(abs(df['high'] - df['close'].shift()),
                   abs(df['low'] - df['close'].shift()))
    )
    df['atr'] = df['tr'].rolling(14).mean()

    df['vol_ma'] = df['volume'].rolling(20).mean()

    return df

# =========================
# SMART MONEY LOGIC
# =========================
def detect_liquidity(df):
    df['prev_high'] = df['high'].rolling(5).max().shift(1)
    df['prev_low'] = df['low'].rolling(5).min().shift(1)
    last = df.iloc[-1]

    if last['high'] > last['prev_high'] and last['close'] < last['prev_high']:
        return "bearish_sweep"
    if last['low'] < last['prev_low'] and last['close'] > last['prev_low']:
        return "bullish_sweep"
    return None

def detect_order_block(df):
    candle = df.iloc[-3]
    if candle['close'] < candle['open']:
        return "bearish_ob"
    if candle['close'] > candle['open']:
        return "bullish_ob"
    return None

def detect_bos(df):
    highs = df['high'].rolling(10).max()
    lows = df['low'].rolling(10).min()
    last = df.iloc[-1]

    if last['close'] > highs.iloc[-2]:
        return "bullish_bos"
    if last['close'] < lows.iloc[-2]:
        return "bearish_bos"
    return None

def volume_strength(df):
    return df.iloc[-1]['volume'] > df['volume'].rolling(30).mean().iloc[-1]

# =========================
# SIGNAL ENGINE
# =========================
def generate_signal(df):
    last = df.iloc[-1]

    sweep = detect_liquidity(df)
    ob = detect_order_block(df)
    bos = detect_bos(df)

    score = 0

    if last['close'] > last['ema200']:
        score += 2

    if 40 < last['rsi'] < 60:
        score += 1

    if last['macd'] > last['macd_signal']:
        score += 1

    if volume_strength(df):
        score += 1

    if last['atr'] > df['atr'].rolling(20).mean().iloc[-1]:
        score += 1

    if bos == "bullish_bos":
        score += 1

    if sweep == "bullish_sweep" and ob == "bullish_ob" and score >= 5:
        return "🚀 ULTRA ELITE LONG"

    if sweep == "bearish_sweep" and ob == "bearish_ob" and score >= 5:
        return "🚀 ULTRA ELITE SHORT"

    return "❌ NO TRADE"

# =========================
# RISK
# =========================
def risk(df):
    last = df.iloc[-1]
    price = last['close']
    atr = last['atr']

    sl = price - (2 * atr)
    tp = price + (4 * atr)
    rr = (tp - price) / (price - sl)

    return price, sl, tp, rr

# =========================
# SCANNER
# =========================
st.subheader("🔍 Multi-Coin Scanner")

results = []

for sym in symbols:
    df = get_data(sym, timeframe)

    if df.empty or 'close' not in df.columns:
        continue

    df = add_indicators(df)

    signal = generate_signal(df)
    price, sl, tp, rr = risk(df)

    results.append({
        "Pair": sym,
        "Signal": signal,
        "Price": round(price, 2),
        "RR": round(rr, 2)
    })

    time.sleep(0.2)

scan_df = pd.DataFrame(results)
st.dataframe(scan_df)

# =========================
# SINGLE CHART
# =========================
st.subheader("📊 Chart")

selected = st.selectbox("Select Pair", symbols)

df = get_data(selected, timeframe)

if not df.empty and 'close' in df.columns:
    df = add_indicators(df)

    price, sl, tp, rr = risk(df)
    signal = generate_signal(df)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Price", round(price,2))
    col2.metric("Signal", signal)
    col3.metric("Stop Loss", round(sl,2))
    col4.metric("RR", round(rr,2))

    st.line_chart(df[['close','ema50','ema200']])
    st.dataframe(df.tail(20))
else:
    st.warning("No data available")
