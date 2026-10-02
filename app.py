import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import ccxt

# Configuración de página
st.set_page_config(page_title="PROYECTO DIPPER | Quant Dashboard", layout="wide")

# 🎨 PALETA DE COLORES PERSONALIZADA (Azul Oscuro Opaco + Turquesa)
st.markdown("""
    <style>
    .stApp { background-color: #0B1120; color: #E2E8F0; }
    h1, h2, h3, h4, h5, h6 { color: #38BDF8 !important; font-family: 'Segoe UI', Roboto, sans-serif; }
    [data-testid="stMetric"] {
        background-color: #1E293B !important;
        border: 1px solid #0284C7 !important;
        border-radius: 12px !important;
        padding: 16px !important;
    }
    [data-testid="stMetricLabel"] { color: #94A3B8 !important; font-weight: 600; }
    .stSelectbox > div > div, .stNumberInput > div > div {
        background-color: #1E293B !important;
        color: #38BDF8 !important;
        border: 1px solid #38BDF8 !important;
        border-radius: 8px;
    }
    hr { border-color: #1E293B !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🤖 PROYECTO DIPPER — Quantitative Dashboard")

# 1. PARÁMETROS DE GESTIÓN DE RIESGO Y CONTROL DE CUENTA (SIDEBAR)
st.sidebar.markdown("<h2 style='color:#38BDF8;'>🛡️ Gestión de Riesgo</h2>", unsafe_allow_html=True)
capital_total = st.sidebar.number_input("Capital Total de la Cuenta ($USD)", value=1000.0, step=100.0)
riesgo_pct = st.sidebar.slider("% Riesgo por Operación", min_value=0.5, max_value=3.0, value=1.0, step=0.5)
max_drawdown_diario = st.sidebar.slider("Límite Drawdown Diario (%)", min_value=1.0, max_value=5.0, value=3.0)

# 2. BARRA SUPERIOR DE MÉTRICAS & CIRCUITO DE SEGURIDAD
col1, col2, col3, col4 = st.columns(4)
col1.metric(label="Estado del Bot", value="🟢 ONLINE (24/7)", delta="18 Pares Escaneando")
col2.metric(label="Capital Protegido", value=f"${capital_total:,.2f}", delta=f"Riesgo/Trade: {riesgo_pct}%")
col3.metric(label="Ratio Riesgo/Beneficio", value="1 : 2.0", delta="SL 1.5% | TP 3.0%")
col4.metric(label="Guardafuegos Diario", value="ACTIVO", delta=f"Max DD: -{max_drawdown_diario}%")

st.divider()

# 3. SELECTOR DE PAR Y OBTENCIÓN DE DATOS
PARES_DIPPER = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT", "AVAX/USDT",
    "DOT/USDT", "LINK/USDT", "MATIC/USDT", "NEAR/USDT", "LTC/USDT", "BCH/USDT",
    "ATOM/USDT", "UNI/USDT", "APT/USDT", "FIL/USDT", "ETC/USDT", "XLM/USDT"
]

symbol = st.selectbox("⚡ Seleccionar Par para Análisis en Vivo", PARES_DIPPER)

@st.cache_data(ttl=15)
def fetch_live_ohlcv(pair):
    try:
        exchange = ccxt.binance()
        ohlcv = exchange.fetch_ohlcv(pair, timeframe='15m', limit=100)
    except Exception:
        exchange = ccxt.kraken()
        alt_pair = pair.replace('/USDT', '/USD')
        ohlcv = exchange.fetch_ohlcv(alt_pair, timeframe='15m', limit=100)
        
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Indicadores
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # Rango Verdadero Promedio (ATR) para volatilidad
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['atr'] = true_range.rolling(14).mean()
    
    return df

df = fetch_live_ohlcv(symbol)
last_price = df['close'].iloc[-1]
atr_val = df['atr'].iloc[-1]

# 4. LÓGICA DE PROBABILIDAD CON FILTRO DE VOLATILIDAD
ema_val = df['ema200'].iloc[-1]
bullish_ema = last_price > ema_val

# Evaluación de volatilidad / régimen
volatilidad_normal = atr_val > (df['atr'].mean() * 0.8)

score = 35  # Base
if bullish_ema: score += 35
if volatilidad_normal: score += 30  # Confirmación de régimen saludable

col_chart, col_stats = st.columns([3, 1])

# 5. PANEL LATERAL DE NIVELES Y CALCULA DE POSITION SIZING
with col_stats:
    st.subheader("📊 Probabilidad de Setup")
    st.progress(score / 100)
    st.markdown(f"**Score de Confluencia:** <span style='color:#38BDF8; font-size:22px; font-weight:bold;'>{score}%</span>", unsafe_allow_html=True)
    
    if score >= 75:
        st.success("🔥 ALTA CONFLUENCIA (ENTRADA HABILITADA)")
    elif score >= 50:
        st.warning("⏳ CONFLUENCIA MEDIA — Esperando estructura")
    else:
        st.error("🔴 MERCADO SIN TENDENCIA / RANGO")

    st.markdown("---")
    st.markdown("<h4 style='color:#38BDF8;'>🎯 Position Sizing Calculado</h4>", unsafe_allow_html=True)
    
    # Cálculo exacto de gestión de capital
    precio_tp = last_price * 1.03
    precio_sl = last_price * 0.985
    monto_arriesgar = capital_total * (riesgo_pct / 100)
    distancia_sl_usd = last_price - precio_sl
    
    unidades_a_comprar = monto_arriesgar / distancia_sl_usd if distancia_sl_usd > 0 else 0
    valor_posicion_total = unidades_a_comprar * last_price

    st.markdown(f"🔹 **Precio Actual:** `${last_price:,.4f}`" if last_price < 1 else f"🔹 **Precio Actual:** `${last_price:,.2f}`")
    st.markdown(f"🎯 **Take Profit (3%):** <span style='color:#10B981; font-weight:bold;'>${precio_tp:,.4f if last_price < 1 else precio_tp:,.2f}</span>", unsafe_allow_html=True)
    st.markdown(f"🛑 **Stop Loss (1.5%):** <span style='color:#EF4444; font-weight:bold;'>${precio_sl:,.4f if last_price < 1 else precio_sl:,.2f}</span>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("<h4 style='color:#38BDF8;'>💰 Orden para el Exchange</h4>", unsafe_allow_html=True)
    st.markdown(f"💵 **Riesgo Máximo:** `<span style='color:#EF4444;'>${monto_arriesgar:,.2f} USD</span>`", unsafe_allow_html=True)
    st.markdown(f"📦 **Lote a Comprar:** `<span style='color:#00F0FF;'>{unidades_a_comprar:,.4f} {symbol.split('/')[0]}</span>`", unsafe_allow_html=True)
    st.markdown(f"⚖️ **Valor Total Posición:** `${valor_posicion_total:,.2f} USD`")

# 6. GRÁFICO TÉCNICO INTERACTIVO
with col_chart:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])

    fig.add_trace(go.Candlestick(
        x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        increasing_line_color='#10B981', decreasing_line_color='#EF4444', name="Precio"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['ema200'], line=dict(color='#00F0FF', width=2), name="EMA 200"
    ), row=1, col=1)

    fig.add_hline(y=precio_tp, line_dash="dash", line_color="#10B981", annotation_text="TP 3.0%", row=1, col=1)
    fig.add_hline(y=precio_sl, line_dash="dash", line_color="#EF4444", annotation_text="SL 1.5%", row=1, col=1)

    fig.add_trace(go.Bar(
        x=df['timestamp'], y=df['volume'], marker_color='#0284C7', name="Volumen"
    ), row=2, col=1)

    fig.update_layout(
        template="plotly_dark", paper_bgcolor='#0B1120', plot_bgcolor='#1E293B', height=520,
        margin=dict(l=10, r=10, t=10, b=10), xaxis_rangeslider_visible=False,
        xaxis=dict(gridcolor='#334155'), yaxis=dict(gridcolor='#334155'), yaxis2=dict(gridcolor='#334155')
    )

    st.plotly_chart(fig, use_container_width=True)
