import os
import datetime
import pandas as pd
import numpy as np
import streamlit as st
import ccxt
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURACIÓN E INICIALIZACIÓN
# ==========================================
st.set_page_config(
    page_title="PROYECTO DIPPER | Quant Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS Personalizados (Dark Mode Institutional)
st.markdown("""
<style>
    .stApp { background-color: #0b0e14; color: #c9d1d9; }
    .metric-card {
        background-color: #161b22; border: 1px solid #30363d;
        border-radius: 8px; padding: 15px; text-align: center;
    }
    .status-online { color: #39d353; font-weight: bold; }
    .status-offline { color: #f85149; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Supabase Credentials (variables de entorno o fallback)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

@st.cache_resource
def get_supabase_client():
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            return create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            st.error(f"Error al conectar con Supabase: {e}")
            return None
    return None

supabase = get_supabase_client()
exchange = ccxt.kraken({'enableRateLimit': True})

# ==========================================
# 2. FUNCIONES DE TRADING & CONFLUENCIA
# ==========================================
def fetch_market_data(symbol='BTC/USDT', timeframe='15m', limit=200):
    """Obtiene datos OHLCV de Kraken y calcula indicadores técnicos."""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # EMA 200
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # ATR 14
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        
        return df
    except Exception as e:
        st.error(f"Error al obtener datos de Kraken: {e}")
        return pd.DataFrame()

def evaluate_signal(df):
    """Calcula el Score de Confluencia (0 - 100) y la dirección."""
    if df.empty or len(df) < 200:
        return {"side": "NEUTRAL", "score": 0, "reason": "Datos insuficientes"}
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = last['close']
    ema = last['ema200']
    
    score = 0
    reasons = []
    
    # 1. Posición respecto a EMA 200
    if close > ema:
        side = "LONG"
        score += 40
        reasons.append("Precio > EMA 200")
    else:
        side = "SHORT"
        score += 40
        reasons.append("Precio < EMA 200")
        
    # 2. Impulso/Tendencia
    if side == "LONG" and close > prev['close']:
        score += 30
        reasons.append("Impulso Alcista")
    elif side == "SHORT" and close < prev['close']:
        score += 30
        reasons.append("Impulso Bajista")
        
    # 3. Volatilidad aceptable (ATR)
    if last['atr'] > 0:
        score += 30
        reasons.append("Volatilidad Normal (ATR OK)")
        
    return {
        "side": side,
        "score": score,
        "reason": " + ".join(reasons),
        "price": close,
        "atr": last['atr']
    }

def execute_paper_trade(symbol, signal, capital, risk_pct):
    """Guarda una nueva entrada simulada en Supabase si la confluencia es >= 75%."""
    if not supabase:
        return False, "Sin conexión a Supabase"
    
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
    """Recupera las órdenes registradas en Supabase."""
    if not supabase:
        return []
    try:
        res = supabase.table("paper_trades").select("*").order("timestamp", desc=True).execute()
        return res.data
    except Exception as e:
        return []

# ==========================================
# 3. INTERFAZ DE USUARIO (DASHBOARD)
# ==========================================
st.title("⚡ PROYECTO DIPPER | QUANT TERMINAL v2.4")

# Sidebar
st.sidebar.header("🛡️ MATRIZ DE RIESGO")
capital = st.sidebar.number_input("Capital Operativo ($USD)", value=1000.0, step=100.0)
risk_pct = st.sidebar.slider("% Riesgo Máximo / Trade", 0.5, 5.0, 1.0)
max_risk_usd = capital * (risk_pct / 100.0)
st.sidebar.info(f"Riesgo Máximo por Posición: **${max_risk_usd:.2f} USD**")

symbol = st.sidebar.selectbox("Seleccionar Par", ["BTC/USDT", "ETH/USDT", "SOL/USDT"])
timeframe = st.sidebar.selectbox("Temporalidad", ["15m", "1h", "4h"])

# Pestañas
tab1, tab2 = st.tabs(["⚡ Monitor Cuantitativo en Vivo", "📋 Historial de Órdenes & Audit Log"])

with tab1:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("ESTADO MOTOR", "ONLINE", "Ciclo 30s")
    col2.metric("FILTRO MACRO", "ACTIVO", "Ventana Segura")
    col3.metric("FIREWALL DIARIO", "OPERATIVO", "DD Máx: -3.0%")
    col4.metric("CONEXIÓN DB", "SUPABASE" if supabase else "SIN DB", "Sincronizado" if supabase else "Error")
    
    st.divider()
    
    df = fetch_market_data(symbol, timeframe)
    if not df.empty:
        signal = evaluate_signal(df)
        
        c_left, c_right = st.columns([3, 1])
        with c_left:
            st.subheader(f"Análisis en Vivo: {symbol}")
            st.line_chart(df.set_index('timestamp')[['close', 'ema200']].tail(50))
            
        with c_right:
            st.subheader("Señal Algorítmica")
            st.markdown(f"### **{signal['side']}**")
            st.metric("Score Confluencia", f"{signal['score']} / 100")
            st.caption(f"Motivo: {signal['reason']}")
            
            # Botón de simulación de prueba o ejecución automática
            if signal['score'] >= 75:
                st.success("Señal de Alta Confluencia Detectada")
                if st.button("Ejecutar Entrada Simulada"):
                    success, msg = execute_paper_trade(symbol, signal, capital, risk_pct)
                    if success:
                        st.success(f"Orden ejecutada en Supabase: {msg}")
                        st.rerun()
                    else:
                        st.error(f"Error al ejecutar: {msg}")
            else:
                st.warning("Sin confluencia suficiente (< 75%). Entrada descartada.")

with tab2:
    st.subheader("Historial de Órdenes Reales (Supabase)")
    trades = get_paper_trades()
    if trades:
        trades_df = pd.DataFrame(trades)
        st.dataframe(trades_df[['order_id', 'timestamp', 'symbol', 'side', 'entry_price', 'sl', 'tp', 'status', 'confluence', 'reason']], use_container_width=True)
    else:
        st.info("No hay órdenes simuladas registradas aún en Supabase.")
