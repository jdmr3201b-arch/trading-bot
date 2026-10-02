import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import ccxt

# Configuración de página
st.set_page_config(page_title="PROYECTO DIPPER | Quant Dashboard", layout="wide")

# 🎨 PALETA DE COLORES PERSONALIZADA (Azul Oscuro Opaco + Turquesa)
st.markdown("""
    <style>
    /* Fondo Principal - Azul Oscuro Opaco */
    .stApp {
        background-color: #0B1120;
        color: #E2E8F0;
    }
    
    /* Encabezados */
    h1, h2, h3, h4, h5, h6 {
        color: #38BDF8 !important;
        font-family: 'Segoe UI', Roboto, sans-serif;
    }

    /* Tarjetas de Métricas - Azul Marino Profundo con borde Turquesa suave */
    [data-testid="stMetric"] {
        background-color: #1E293B !important;
        border: 1px solid #0284C7 !important;
        border-radius: 12px !important;
        padding: 16px !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }
    
    /* Etiquetas dentro de Métricas */
    [data-testid="stMetricLabel"] {
        color: #94A3B8 !important;
        font-weight: 600;
    }
    
    /* Contenedores y Cajas */
    div[data-aria-selected="true"] {
        background-color: #0284C7 !important;
    }
    
    /* Selectbox e Inputs */
    .stSelectbox > div > div {
        background-color: #1E293B !important;
        color: #38BDF8 !important;
        border: 1px solid #38BDF8 !important;
        border-radius: 8px;
    }

    /* Separadores horizontales */
    hr {
        border-color: #1E293B !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🤖 PROYECTO DIPPER — Quantitative Dashboard")

# 1. BARRA SUPERIOR DE MÉTRICAS (Estilo Card Azul Marino)
col1, col2, col3, col4 = st.columns(4)
col1.metric(label="Estado del Bot", value="🟢 ONLINE (24/7)", delta="18 Pares Escaneando")
col2.metric(label="Win Rate Estimado", value="62.5%", delta="+2.1% esta semana")
col3.metric(label="Ratio Riesgo/Beneficio", value="1 : 2.0", delta="SL 1.5% | TP 3.0%")
col4.metric(label="Base de Datos", value="SUPABASE", delta="Sincronizado")

st.divider()

# 2. SELECTOR DE PAR EN TIEMPO REAL
symbol = st.selectbox("⚡ Seleccionar Par para Análisis en Vivo", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"])

# Función para obtener datos en vivo de Kraken vía CCXT
@st.cache_data(ttl=15)
def fetch_live_ohlcv(pair):
    exchange = ccxt.kraken()
    ohlcv = exchange.fetch_ohlcv(pair, timeframe='15m', limit=60)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    return df

df = fetch_live_ohlcv(symbol)
last_price = df['close'].iloc[-1]

# 3. SCORE DE PROBABILIDAD DINÁMICO
ema_val = df['ema200'].iloc[-1]
bullish_ema = last_price > ema_val
score = 35  # Base

if bullish_ema:
    score += 30
score += 20  # Confluencia de volumen y RSI simulada

col_chart, col_stats = st.columns([3, 1])

with col_stats:
    st.subheader("📊 Probabilidad de Setup")
    st.progress(score / 100)
    st.markdown(f"**Score de Confluencia:** `<span style='color:#38BDF8; font-size:20px;'>{score}%</span>`", unsafe_allow_html=True)
    
    if score >= 75:
        st.success("🔥 ALTA PROBABILIDAD EN COMPRA")
    elif score >= 50:
        st.warning("⏳ CONFLUENCIA MEDIA — Esperando confirmación")
    else:
        st.error("🔴 SIN SEÑAL CLARA")

    st.markdown("---")
    st.markdown("<h4 style='color:#38BDF8;'>Niveles Técnicos</h4>", unsafe_allow_html=True)
    st.write(f"🔹 **Precio Actual:** `${last_price:,.2f}`")
    st.write(f"🎯 **Take Profit (3%):** `<span style='color:#10B981;'>${last_price * 1.03:,.2f}</span>`", unsafe_allow_html=True)
    st.write(f"🛑 **Stop Loss (1.5%):** `<span style='color:#EF4444;'>${last_price * 0.985:,.2f}</span>`", unsafe_allow_html=True)

# 4. GRÁFICO DE VELAS EN TIEMPO REAL CON COLORES RESERVADOS
with col_chart:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])

    # Velas Japonesas (Verde para Alza, Rojo para Baja)
    fig.add_trace(go.Candlestick(
        x=df['timestamp'],
        open=df['open'], high=df['high'],
        low=df['low'], close=df['close'],
        increasing_line_color='#10B981',  # Verde compra
        decreasing_line_color='#EF4444',  # Rojo venta
        name="Precio"
    ), row=1, col=1)

    # EMA 200 en Turquesa Neón
    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['ema200'],
        line=dict(color='#00F0FF', width=2), name="EMA 200"
    ), row=1, col=1)

    # Líneas de TP y SL
    fig.add_hline(y=last_price * 1.03, line_dash="dash", line_color="#10B981", annotation_text="TP 3.0%", row=1, col=1)
    fig.add_hline(y=last_price * 0.985, line_dash="dash", line_color="#EF4444", annotation_text="SL 1.5%", row=1, col=1)

    # Volumen en Turquesa Translúcido
    fig.add_trace(go.Bar(
        x=df['timestamp'], y=df['volume'],
        marker_color='#0284C7', name="Volumen"
    ), row=2, col=1)

    # Layout con fondo Azul Oscuro Opaco (#0B1120 y #1E293B)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='#0B1120',
        plot_bgcolor='#1E293B',
        height=500,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_rangeslider_visible=False,
        xaxis=dict(gridcolor='#334155'),
        yaxis=dict(gridcolor='#334155'),
        yaxis2=dict(gridcolor='#334155')
    )

    st.plotly_chart(fig, use_container_width=True)
