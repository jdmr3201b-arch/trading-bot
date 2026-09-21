# app.py
import streamlit as st
import pandas as pd
import time
from engine import AutoTradingEngine
import config

st.set_page_config(
    page_title="Trading Bot AI Dashboard",
    page_icon="📈",
    layout="wide"
)

# Inicializar motor en la sesión de Streamlit
if "engine" not in st.session_state:
    st.session_state.engine = AutoTradingEngine()

if "is_running" not in st.session_state:
    st.session_state.is_running = False

engine = st.session_state.engine

# --- PANEL LATERAL ---
st.sidebar.title("🤖 Panel de Control")
st.sidebar.markdown("---")

if st.session_state.is_running:
    st.sidebar.success("🟢 BOT EN EJECUCIÓN (Autónomo)")
else:
    st.sidebar.error("🔴 BOT DETENIDO")

col_start, col_stop = st.sidebar.columns(2)
if col_start.button("▶️ Iniciar Bot", use_container_width=True):
    st.session_state.is_running = True
    st.rerun()

if col_stop.button("⏹️ Detener Bot", use_container_width=True):
    st.session_state.is_running = False
    st.rerun()

st.sidebar.markdown("---")
symbol = st.sidebar.selectbox("Par a analizar", ["BTC/USDT", "ETH/USDT", "SOL/USDT"])
risk_pct = st.sidebar.slider("Riesgo por Operación (%)", 0.5, 5.0, float(config.RISK_PER_TRADE_PCT), step=0.5)

config.SYMBOL = symbol
config.RISK_PER_TRADE_PCT = risk_pct

# --- CUERPO PRINCIPAL ---
st.title("📈 Dashboard de Trading 100% Automático")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Balance Total (USDT)", f"${engine.balance:.2f}")
kpi2.metric("Equity", f"${engine.equity:.2f}")
kpi3.metric("Posiciones Abiertas", len(engine.positions))
kpi4.metric("Operaciones Totales", len(engine.trade_history))

st.markdown("---")
st.subheader(f"📊 Mercado en Vivo: {config.SYMBOL}")

df_market = engine.fetch_market_data(config.SYMBOL)
if not df_market.empty:
    chart_data = df_market.set_index('timestamp')[['close', 'EMA_200']]
    st.line_chart(chart_data)

col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("📋 Órdenes Ejecutadas Automáticamente")
    if len(engine.positions) > 0:
        st.dataframe(pd.DataFrame(engine.positions), use_container_width=True)
    else:
        st.info("Sin posiciones abiertas por la IA.")

with col_right:
    st.subheader("📝 Bitácora de Decisiones de la IA")
    log_text = "\n".join(engine.logs[-10:][::-1])
    st.text_area("Logs:", value=log_text, height=220, disabled=True)

# Bucle de ejecución
if st.session_state.is_running:
    # 1. Lista con tus 18 criptomonedas
symbols = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
    "MATIC/USDT", "NEAR/USDT", "LTC/USDT", "SUI/USDT", "APT/USDT",
    "OP/USDT", "ARBV/USDT", "INJ/USDT"
]

# 2. Recorrer y analizar cada una
    for selected_symbol in symbols:
        engine.run_cycle_for_symbol(selected_symbol)

    time.sleep(5)
    st.rerun()
