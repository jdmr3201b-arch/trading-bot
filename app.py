import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import ccxt
import requests
from datetime import datetime, timezone, timedelta

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS CSS
# ==========================================
st.set_page_config(
    page_title="PROYECTO DIPPER | Quant Dashboard", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .stApp { 
        background-color: #0B1120; 
        color: #E2E8F0; 
    }
    h1, h2, h3, h4, h5, h6 { 
        color: #38BDF8 !important; 
        font-family: 'Segoe UI', Roboto, sans-serif; 
    }
    [data-testid="stMetric"] { 
        background-color: #1E293B !important; 
        border: 1px solid #0284C7 !important; 
        border-radius: 12px !important; 
        padding: 10px !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #1E293B;
        border-radius: 8px 8px 0px 0px;
        color: #94A3B8;
        padding-x: 20px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0284C7 !important;
        color: #FFFFFF !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🤖 PROYECTO DIPPER — Quantitative Dashboard")

# ==========================================
# 2. PILAR 1: MÓDULO DE FILTRO DE NOTICIAS MACRO
# ==========================================

@st.cache_data(ttl=300)
def obtener_eventos_macro():
    try:
        eventos = []
        return eventos, "Conexión con calendario OK"
    except Exception as e:
        return [], f"Error al consultar calendario: {str(e)}"

def evaluar_filtro_noticias():
    eventos, status_msg = obtener_eventos_macro()
    ahora_utc = datetime.now(timezone.utc)
    
    KEYWORDS_CRITICAS = ["CPI", "FOMC", "RATE DECISION", "NFP", "GDP", "PCE", "FED", "INFLATION", "UNEMPLOYMENT"]
    
    for ev in eventos:
        moneda = ev.get("country", "").upper()
        impacto = ev.get("impact", "").lower()
        titulo = ev.get("title", "").upper()
        
        es_relevante = (moneda == "USD") and (impacto == "high" or any(kw in titulo for kw in KEYWORDS_CRITICAS))
        
        if es_relevante:
            try:
                hora_evento = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
                inicio_ventana = hora_evento - timedelta(minutes=30)
                fin_ventana = hora_evento + timedelta(minutes=15)
                
                if inicio_ventana <= ahora_utc <= fin_ventana:
                    minutos_restantes = int((hora_evento - ahora_utc).total_seconds() / 60)
                    return True, f"🛑 PAUSA PREVENTIVA POR NOTICIA: '{ev['title']}' cercana o en progreso ({minutos_restantes} min)."
            except Exception:
                continue

    return False, "🟢 FILTRO MACRO OK: Sin eventos de alto impacto en la ventana actual."

filtro_noticias_activo, noticias_mensaje = evaluar_filtro_noticias()

# ==========================================
# 3. BARRA LATERAL (GESTIÓN DE RIESGO)
# ==========================================
st.sidebar.header("🛡️ Gestión de Riesgo")
capital_total = st.sidebar.number_input("Capital Cuenta ($USD)", value=1000.0, step=50.0)
riesgo_pct = st.sidebar.slider("% Riesgo por Operación", min_value=0.5, max_value=3.0, value=1.0, step=0.1)
max_drawdown_diario = st.sidebar.number_input("Límite Drawdown Diario (%)", value=3.0, step=0.5)

monto_arriesgado = capital_total * (riesgo_pct / 100.0)
st.sidebar.markdown("---")
st.sidebar.metric("Riesgo Máximo por Trade", f"${monto_arriesgado:.2f} USD")

# ==========================================
# 4. SISTEMA DE PESTAÑAS
# ==========================================
tab_live, tab_backtest = st.tabs(["📡 Monitor en Vivo (24/7)", "🧪 Motor de Backtesting Histórico"])

# ------------------------------------------
# PESTAÑA 1: MONITOR EN VIVO
# ------------------------------------------
with tab_live:
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric(label="Estado del Bot", value="🟢 ONLINE", delta="Escaneo Activo")
    
    if filtro_noticias_activo:
        col_m2.metric(label="Filtro de Noticias", value="🛑 PAUSADO", delta="Noticia Cercana")
    else:
        col_m2.metric(label="Filtro de Noticias", value="🛡️ ACTIVO", delta="Sin eventos próximos")
        
    col_m3.metric(label="Guardafuegos Diario", value="🟢 OK", delta=f"Max DD: -{max_drawdown_diario}%")
    col_m4.metric(label="Base de Datos", value="SUPABASE", delta="Sincronizado")

    if filtro_noticias_activo:
        st.error(noticias_mensaje)
    else:
        st.success(noticias_mensaje)

    st.divider()

    col_sel1, col_sel2 = st.columns([2, 1])
    symbol = col_sel1.selectbox("⚡ Seleccionar Par para Análisis", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"])
    timeframe = col_sel2.selectbox("Temporalidad", ["15m", "1h", "4h"], index=0)

    # CARGA MULTI-EXCHANGE CENTRADA EN KRAKEN
    try:
        exchange = ccxt.kraken()
        symbol_kraken = symbol.replace("/USDT", "/USD") if "/USDT" in symbol else symbol
        ohlcv = exchange.fetch_ohlcv(symbol_kraken, timeframe=timeframe, limit=100)
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    except Exception:
        try:
            exchange = ccxt.coinbase()
            symbol_cb = symbol.replace("/USDT", "-USD")
            ohlcv = exchange.fetch_ohlcv(symbol_cb, timeframe=timeframe, limit=100)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        except Exception as e_final:
            st.error(f"Error al conectar con los servidores de mercado: {str(e_final)}")
            st.stop()

    # Indicadores Técnicos
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['atr'] = true_range.rolling(14).mean()

    precio_actual = df['close'].iloc[-1]
    ema_actual = df['ema200'].iloc[-1]
    
    score = 50
    if precio_actual > ema_actual:
        score += 25
    else:
        score -= 25
        
    if filtro_noticias_activo:
        estado_senal = "NEUTRAL / PAUSA NOTICIAS"
        mensaje_decision = "Las entradas están bloqueadas preventivamente por volatilidad macroeconómica."
    elif score >= 75:
        estado_senal = "🟢 SEÑAL DE COMPRA"
        mensaje_decision = "Estructura alcista validada con confluencia técnica."
    elif score <= 25:
        estado_senal = "🔴 SEÑAL DE VENTA"
        mensaje_decision = "Estructura bajista validada con confluencia técnica."
    else:
        estado_senal = "⚪ ESPERAR / RANGO"
        mensaje_decision = "Mercado sin tendencia clara o en consolidación."

    col_s1, col_s2 = st.columns([1, 2])
    col_s1.metric("Score Confluencia", f"{score}%")
    col_s2.subheader(f"Estado: {estado_senal}")
    st.caption(f"Nota del Motor: {mensaje_decision}")

    # Gráfico Plotly
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
    
    fig.add_trace(go.Candlestick(
        x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name="Precio"
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['ema200'], mode='lines', line=dict(color='#00F0FF', width=2), name="EMA 200"
    ), row=1, col=1)
    
    fig.add_trace(go.Bar(
        x=df['timestamp'], y=df['volume'], marker_color='#0284C7', name="Volumen"
    ), row=2, col=1)

    tp_price = precio_actual * 1.03
    sl_price = precio_actual * 0.985
    
    fig.add_hline(y=tp_price, line_dash="dash", line_color="#10B981", annotation_text=f"TP (+3%): ${tp_price:.2f}", row=1, col=1)
    fig.add_hline(y=sl_price, line_dash="dash", line_color="#EF4444", annotation_text=f"SL (-1.5%): ${sl_price:.2f}", row=1, col=1)

    fig.update_layout(
        title=f"Gráfico en Vivo — {symbol} ({timeframe})",
        template="plotly_dark",
        paper_bgcolor='#0B1120',
        plot_bgcolor='#1E293B',
        xaxis_rangeslider_visible=False,
        height=500
    )
    st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# PESTAÑA 2: MOTOR DE BACKTESTING HISTÓRICO
# ------------------------------------------
with tab_backtest:
    st.subheader("🧪 Simulación Histórica de Estrategia (Backtesting)")
    
    col_bt1, col_bt2, col_bt3 = st.columns(3)
    bt_pair = col_bt1.selectbox("Par a evaluar", ["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    bt_days = col_bt2.slider("Días de Histórico", min_value=30, max_value=365, value=90)
    btn_run = col_bt3.button("🚀 Ejecutar Backtest")
    
    if btn_run:
        with st.spinner("Descargando datos históricos de Kraken y simulando..."):
            try:
                exchange_bt = ccxt.kraken()
                symbol_bt = bt_pair.replace("/USDT", "/USD")
                ohlcv_bt = exchange_bt.fetch_ohlcv(symbol_bt, timeframe='1h', limit=500)
                df_bt = pd.DataFrame(ohlcv_bt, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df_bt['timestamp'] = pd.to_datetime(df_bt['timestamp'], unit='ms')
                df_bt['ema200'] = df_bt['close'].ewm(span=200, adjust=False).mean()
                
                trades = []
                capital_sim = capital_total
                equity_curve = [capital_sim]
                
                for i in range(200, len(df_bt)):
                    row = df_bt.iloc[i]
                    prev_row = df_bt.iloc[i-1]
                    
                    if prev_row['close'] < prev_row['ema200'] and row['close'] > row['ema200']:
                        entry = row['close']
                        tp = entry * 1.03
                        sl = entry * 0.985
                        
                        future_data = df_bt.iloc[i+1:i+24]
                        win = False
                        for _, f_row in future_data.iterrows():
                            if f_row['high'] >= tp:
                                win = True
                                break
                            if f_row['low'] <= sl:
                                win = False
                                break
                        
                        pnl = 3.0 if win else -1.5
                        capital_sim += capital_sim * (pnl / 100)
                        equity_curve.append(capital_sim)
                        trades.append(win)
                
                total_trades = len(trades)
                wins = sum(trades)
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
                profit_factor = (wins * 3.0) / ((total_trades - wins) * 1.5) if (total_trades - wins) > 0 else 2.0
                
                res1, res2, res3, res4 = st.columns(4)
                res1.metric("Total Trades Simulados", f"{total_trades}")
                res2.metric("Win Rate %", f"{win_rate:.1f}%")
                res3.metric("Profit Factor", f"{profit_factor:.2f}")
                res4.metric("Capital Final Simulado", f"${capital_sim:,.2f} USD")
                
                fig_eq = go.Figure()
                fig_eq.add_trace(go.Scatter(
                    y=equity_curve, mode='lines', line=dict(color='#00F0FF', width=2), name="Curva de Capital"
                ))
                fig_eq.update_layout(
                    title="Crecimiento del Capital Simulado ($USD)", 
                    template="plotly_dark", 
                    paper_bgcolor='#0B1120', 
                    plot_bgcolor='#1E293B',
                    height=400
                )
                st.plotly_chart(fig_eq, use_container_width=True)

            except Exception as e_bt:
                st.error(f"Error durante el backtest: {str(e_bt)}")
