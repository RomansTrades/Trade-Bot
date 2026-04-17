import streamlit as st
from PIL import Image
import base64
import os
import io
from dotenv import load_dotenv
from openai import OpenAI

import ccxt
import pandas as pd
import ta

# ==============================
# LOAD ENV
# ==============================
load_dotenv()
client = OpenAI(api_key=os.getenv("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"))

# ==============================
# PAGE CONFIG
# ==============================
st.set_page_config(page_title="AI Trade Analyst PRO", layout="wide")
st.title("🧠 AI Trade Analyst PRO (Multi-Timeframe Engine)")

# ==============================
# SIDEBAR
# ==============================
st.sidebar.header("⚙️ Settings")

model = st.sidebar.selectbox("Model", ["gpt-5.0", "gpt-4o"])
symbol = st.sidebar.text_input("Symbol", "BTC/USDT")

# ==============================
# USER INPUT
# ==============================
uploaded_file = st.file_uploader("📈 Upload Chart (Optional)", type=["png","jpg","jpeg"])

user_thoughts = st.text_area(
    "💭 Your Trade Idea",
    placeholder="Explain your setup..."
)

analyze_btn = st.button("🚀 Run Analysis")

# ==============================
# IMAGE ENCODER
# ==============================
def encode_image(image):
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()

# ==============================
# MULTI-TIMEFRAME ENGINE
# ==============================
def get_mtf_data(symbol):
    exchange = ccxt.binance()

    timeframes = {
        "5m": 1,
        "15m": 2,
        "1h": 3,
        "4h": 4,
        "1d": 5
    }

    results = {}

    for tf, weight in timeframes.items():
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=200)
            df = pd.DataFrame(ohlcv, columns=["time","open","high","low","close","volume"])

            # Indicators
            df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()

            macd = ta.trend.MACD(df["close"])
            df["macd"] = macd.macd()
            df["macd_signal"] = macd.macd_signal()

            df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
            df["ema200"] = ta.trend.EMAIndicator(df["close"], window=200).ema_indicator()

            latest = df.iloc[-1]

            score = 0

            # Trend
            if latest["ema50"] > latest["ema200"]:
                score += 25
                trend = "Bullish"
            else:
                score -= 25
                trend = "Bearish"

            # RSI
            if latest["rsi"] > 55:
                score += 15
            elif latest["rsi"] < 45:
                score -= 15

            # MACD
            if latest["macd"] > latest["macd_signal"]:
                score += 15
            else:
                score -= 15

            # Volume
            vol_mean = df["volume"].rolling(20).mean().iloc[-1]
            if latest["volume"] > vol_mean:
                score += 10

            results[tf] = {
                "score": score,
                "weight": weight,
                "trend": trend,
                "price": float(latest["close"]),
                "rsi": float(latest["rsi"])
            }

        except Exception as e:
            results[tf] = {"error": str(e)}

    return results

# ==============================
# FINAL SCORE
# ==============================
def calculate_final_score(mtf_data):
    total = 0
    max_score = 0

    for tf in mtf_data:
        if "error" in mtf_data[tf]:
            continue

        weight = mtf_data[tf]["weight"]
        score = mtf_data[tf]["score"]

        total += score * weight
        max_score += 50 * weight

    if max_score == 0:
        return 0

    return round((total / max_score) * 100, 2)

# ==============================
# ANALYSIS
# ==============================
if analyze_btn:

    with st.spinner("Running multi-timeframe analysis..."):

        mtf_data = get_mtf_data(symbol)
        final_score = calculate_final_score(mtf_data)

    # ==============================
    # DISPLAY DATA
    # ==============================
    st.subheader("📊 Multi-Timeframe Breakdown")

    for tf in mtf_data:
        if "error" in mtf_data[tf]:
            st.write(f"{tf}: ERROR")
        else:
            data = mtf_data[tf]
            st.write(f"{tf} → Score: {data['score']} | Trend: {data['trend']} | RSI: {round(data['rsi'],2)}")

    st.metric("🔥 Final Confluence Score", f"{final_score}/100")

    # ==============================
    # AI INTERPRETATION (CONTROLLED)
    # ==============================
    image_part = None

    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption="Uploaded Chart", use_container_width=True)
        image_part = {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{encode_image(image)}"}
        }

    with st.spinner("Generating professional analysis..."):

        prompt = f"""
You are a quantitative trading analyst.

STRICT RULES:
- Do NOT guess from the chart
- Use ONLY structured data
- Be conservative
- If unclear → NO TRADE

DATA:
{mtf_data}

FINAL SCORE: {final_score}

USER IDEA:
{user_thoughts}

LOGIC:
- >65 = Strong bias
- 55–65 = Weak bias
- <55 = No trade

OUTPUT:

1. Bias (Bullish / Bearish / Neutral)
2. Timeframe alignment summary
3. Trade decision (TAKE / NO TRADE)
4. If TAKE:
   - Entry
   - Stop Loss
   - Take Profit
   - Reason
5. Risks
6. What could invalidate this
"""

        message_content = [{"type": "text", "text": prompt}]

        if image_part:
            message_content.append(image_part)

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": message_content}],
            max_tokens=800
        )

        output = response.choices[0].message.content

    st.markdown("### 🧠 AI Decision")
    st.write(output)

# ==============================
# FOOTER
# ==============================
st.markdown("---")
st.caption("Multi-Timeframe Quant Engine | Data > Opinions")
