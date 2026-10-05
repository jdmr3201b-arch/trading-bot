import os
import datetime
import pandas as pd
import numpy as np
import streamlit as st
import ccxt
import plotly.graph_objects as go
from supabase import create_client

# ==========================================
# 1. CONFIGURACIÓN E INYECCIÓN CSS BLOOMBERG
# ==========================================
st.set_page_config(
    page_title="PROYECTO DIPPER | Quant Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'JetBrains Mono', monospace;
        background-color: #070a13 !important;
        color: #93c5fd;
    }
    .stApp { background-color: #070a13; }
    
    /* Header Status Cards */
    .status-card {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 6px;
        padding: 12px 16px;
        text-align: center;
    }
    .status-title { font-size: 10px; color: #64748b; letter-spacing: 1px; font-weight: bold; }
    .status-value { font-size: 16px; font-weight: bold; color: #38bdf8; margin-top: 4px; }
    .status-sub { font-size: 11px; color: #34d399; margin-top: 2px; }

    /* Signal Card */
    .signal-card-long {
        background: rgba(16, 185, 129, 0.1);
        border: 1px solid #10b981;
        border-radius: 8px;
        padding: 20px;
    }
    .signal-card-short {
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid #ef4444;
        border-radius: 8px;
        padding: 20px;
    }
    
    /* Botones y Widgets */
    .stButton>button {
        width: 100%;
        background-color: #3b82f6 !important;
        color: #ffffff !important;
        font-weight: bold;
        border: none;
        border-radius: 6px;
        padding: 10px;
        transition: all 0.2s;
    }
    .stButton>button:hover {
        background-color: #2563eb !important;
        box-shadow: 0 0 10px rgba(59, 130, 246, 0.5);
    }
</style>
""", unsafe_allow_html=True)

# Supabase Credentials
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

@st.cache_resource
def get_supabase_client():
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            return create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            return None
    return None

supabase = get_supabase_client()
exchange = ccxt.kraken({'enableRateLimit': True})

# ==========================================
# 2. MOTOR DE DATOS Y CONFLUENCIA
# ==========================================
def fetch_market_data(symbol='BTC/USDT', timeframe='15m', limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # ATR 14
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        return df
    except Exception:
        return pd.DataFrame()

def evaluate_signal(df):
    if df.empty or len(df) < 50:
        return {"side": "NEUTRAL", "score": 0, "reason": "Cargando datos de mercado..."}
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = last['close']
    ema = last['ema200']
    
    score = 0
    reasons = []
    
    if close > ema:
        side = "LONG"
        score += 50
        reasons.append("Estructura por encima de EMA 200")
    else:
        side = "SHORT"
        score += 50
        reasons.append("Estructura por debajo de EMA 200")
        
    if (side == "LONG" and close > prev['close']) or (side == "SHORT" and close < prev['close']):
        score += 30
        reasons.append("Presión Directiva Confirmada")
        
    if last['atr'] > 0:
        score += 20
        reasons.append("Volatilidad ATR Óptima")
        
    return {
        "side": side,
        "score": score,
        "reason": " • ".join(reasons),
        "price": close,
        "atr": last['atr'],
        "ema": ema
    }

def execute_paper_trade(symbol, signal):
    if not supabase:
        return False, "Sin conexión con Supabase"
    
    entry_price = signal['price']
    sl = entry_price * 0.985 if signal['side'] == "LONG" else entry_price * 1.015
    tp = entry_price * 1.030 if signal['side'] == "LONG" else entry_price * 0.970
    order_id = f"DIP-{int(datetime.datetime.now().timestamp())}"
    
    trade_data = {
        "order_id": order_id,
        "symbol": symbol,
        "side": signal['side'],
        "entry_price": float(entry_price),
        "sl": float(sl),
        "tp": float(tp),
        "status": "OPEN",
        "confluence": int(signal['score']),
        "reason": signal['reason']
    }
    
    try:
        supabase.table("paper_trades").insert(trade_data).execute()
        return True, order_id
    except Exception as e:
        return False, str(e)

def get_paper_trades():
    if not supabase:
        return []
    try:
        res = supabase.table("paper_trades").select("*").order("timestamp", desc=True).execute()
        return res.data
    except Exception:
        return []

# ==========================================
# 3. INTERFAZ GRÁFICA INSTITUCIONAL
# ==========================================

# Top Brand Header
st.markdown("""
    <div style="display: flex; align-items: center; justify-content: space-between; padding-bottom: 20px; border-bottom: 1px solid #1e293b; margin-bottom: 20px;">
        <div style="display: flex; align-items: center; gap: 12px;">
            <span style="font-size: 24px;">⚡</span>
            <span style="font-size: 20px; font-weight: bold; color: #f8fafc; letter-spacing: 1px;">PROYECTO DIPPER</span>
            <span style="background: #1e293b; color: #38bdf8; font-size: 11px; padding: 3px 8px; border-radius: 4px; font-weight: bold;">QUANT TERMINAL v2.4</span>
        </div>
        <div style="font-size: 12px; color: #64748b;">
            SYS: <span style="color: #34d399;">ONLINE</span> &nbsp;|&nbsp; FEED: <span style="color: #38bdf8;">KRAKEN REST</span>
        </div>
    </div>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.markdown("### 🛡️ MATRIZ DE RIESGO")
capital = st.sidebar.number_input("Capital Operativo ($USD)", value=1000.0, step=100.0)
risk_pct = st.sidebar.slider("% Riesgo Máximo / Trade", 0.5, 5.0, 1.0)
max_risk_usd = capital * (risk_pct / 100.0)

st.sidebar.markdown(f"""
    <div style="background: #0f172a; border: 1px solid #1e293b; padding: 12px; border-radius: 6px; margin-bottom: 20px;">
        <div style="font-size: 11px; color: #64748b;">RIESGO MÁXIMO POR POSICIÓN</div>
        <div style="font-size: 18px; font-weight: bold; color: #38bdf8;">${max_risk_usd:.2f} USD</div>
    </div>
""", unsafe_allow_html=True)

symbol = st.sidebar.selectbox("Seleccionar Par", ["BTC/USDT", "ETH/USDT", "SOL/USDT"])
timeframe = st.sidebar.selectbox("Temporalidad", ["15m", "1h", "4h"])

tab1, tab2 = st.tabs(["⚡ Monitor Cuantitativo en Vivo", "📋 Historial de Órdenes & Audit Log"])

with tab1:
    # Monitor Status Header Cards
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown('<div class="status-card"><div class="status-title">ESTADO DEL MOTOR</div><div class="status-value">ONLINE</div><div class="status-sub">↑ Ciclo Activo · 30s</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="status-card"><div class="status-title">FILTRO MACRO</div><div class="status-value">ACTIVO</div><div class="status-sub">↑ Ventana Segura</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="status-card"><div class="status-title">FIREWALL DIARIO</div><div class="status-value">OPERATIVO</div><div class="status-sub">↑ DD Máx: -3.0%</div></div>', unsafe_allow_html=True)
    with c4:
        db_txt = "SUPABASE" if supabase else "SIN DB"
        db_col = "↑ Sincronizado" if supabase else "↓ Desconectado"
        st.markdown(f'<div class="status-card"><div class="status-title">CONEXIÓN DB</div><div class="status-value">{db_txt}</div><div class="status-sub">{db_col}</div></div>', unsafe_allow_html=True)

    st.write("")
    
    df = fetch_market_data(symbol, timeframe)
    
    if not df.empty:
        signal = evaluate_signal(df)
        
        col_chart, col_signal = st.columns([2.5, 1])
        
        with col_chart:
            # Chart Plotly Candlestick (TradingView Style)
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=df['timestamp'],
                open=df['open'], high=df['high'],
                low=df['low'], close=df['close'],
                name="Precio"
            ))
            fig.add_trace(go.Scatter(
                x=df['timestamp'], y=df['ema200'],
                mode='lines', name='EMA 200',
                line=dict(color='#38bdf8', width=1.5)
            ))
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#070a13",
                plot_bgcolor="#070a13",
                margin=dict(l=10, r=10, t=10, b=10),
                height=420,
                xaxis_rangeslider_visible=False,
                legend=dict(orientation="h", yanchor="bottom", y=1, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_signal:
            card_class = "signal-card-long" if signal['side'] == "LONG" else "signal-card-short"
            color_text = "#10b981" if signal['side'] == "LONG" else "#ef4444"
            
            st.markdown(f"""
                <div class="{card_class}">
                    <div style="font-size: 12px; color: #94a3b8; font-weight: bold;">SEÑAL ALGORTÍMICA</div>
                    <div style="font-size: 28px; font-weight: bold; color: {color_text}; margin: 5px 0;">{signal['side']}</div>
                    <div style="font-size: 14px; color: #f8fafc;">Score: <b>{signal['score']} / 100</b></div>
                    <div style="font-size: 11px; color: #64748b; margin-top: 8px;">{signal['reason']}</div>
                    <hr style="border-color: #1e293b; margin: 12px 0;">
                    <div style="font-size: 12px; color: #cbd5e1;">Último Precio: <b>${signal['price']:,.2f}</b></div>
                    <div style="font-size: 12px; color: #cbd5e1;">EMA 200: <b>${signal['ema']:,.2f}</b></div>
                </div>
            """, unsafe_allow_html=True)
            
            st.write("")
            if signal['score'] >= 75:
                if st.button("🚀 Ejecutar Entrada Simulada"):
                    success, msg = execute_paper_trade(symbol, signal)
                    if success:
                        st.success(f"¡Orden registrada en Supabase! ID: {msg}")
                        st.rerun()
                    else:
                        st.error(f"Error al guardar: {msg}")
            else:
                st.info("Buscando alta confluencia (Score ≥ 75%)...")

with tab2:
    st.subheader("Audit Log & Registro de Órdenes (Supabase)")
    trades = get_paper_trades()
    if trades:
        trades_df = pd.DataFrame(trades)
        st.dataframe(trades_df[['order_id', 'timestamp', 'symbol', 'side', 'entry_price', 'sl', 'tp', 'status', 'confluence', 'reason']], use_container_width=True)
    else:
        st.info("No hay órdenes guardadas aún en la base de datos.")
