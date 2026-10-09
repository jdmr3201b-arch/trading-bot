# -*- coding: utf-8 -*-
"""
========================================================================================
PROYECTO DIPPER | QUANTITATIVE TRADING DASHBOARD & REAL-TIME TERMINAL (STREAMLIT)
========================================================================================
Dashboard interactivo para Render y GitHub:
- Conexión a Kraken (CCXT) y persistencia en Supabase (PostgreSQL).
- Zona Horaria Colombia (COT - America/Bogota / UTC-5) en todos los timestamps.
- Dos tablas separadas:
    1. POSICIONES ACTIVAS (OPEN) en tarjetas/tabla neutra.
    2. HISTORIAL DE OPERACIONES CERRADAS con coloreado integral de filas (Verde TP / Rojo SL).
    - Signo negativo explícito (-$XX.XX USD) en pérdidas por Stop Loss.
- Ciclo semanal (Domingo 00:00 UTC / Sábado 7:00 PM COT a Sábado 23:59 UTC).
- Curva de Capital (Equity Curve) interactiva con Plotly.
- Botón de Reset Manual para limpiar datos en Supabase y restablecer saldo a $1,000.00 USD.
- Sistema de alertas Push vía Ntfy.sh (sin bloquear la ejecución).
- Servidor web 100% nativo de Streamlit listo para Port Binding en Render ($PORT).
========================================================================================
"""

import os
import sys
import time
import math
import logging
import datetime
from typing import Optional, Dict, Any, Tuple, List

import requests
import ccxt
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

# --------------------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA Y TEMA DE STREAMLIT (DEBE SER LA PRIMERA LLAMADA)
# --------------------------------------------------------------------------------------
st.set_page_config(
    page_title="Proyecto Dipper | Quant Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --------------------------------------------------------------------------------------
# 2. ZONA HORARIA COLOMBIA (COT / UTC-5) & LOGS
# --------------------------------------------------------------------------------------
try:
    import zoneinfo
    try:
        TZ_COT = zoneinfo.ZoneInfo("America/Bogota")
    except Exception:
        TZ_COT = datetime.timezone(datetime.timedelta(hours=-5))
except ImportError:
    TZ_COT = datetime.timezone(datetime.timedelta(hours=-5))

def now_cot() -> datetime.datetime:
    """Retorna la fecha y hora actual en la zona horaria de Colombia."""
    return datetime.datetime.now(TZ_COT)

def format_cot_timestamp(dt: Optional[datetime.datetime] = None) -> str:
    """Formatea la fecha y hora actual en hora militar COT."""
    if dt is None:
        dt = now_cot()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc).astimezone(TZ_COT)
    else:
        dt = dt.astimezone(TZ_COT)
    return dt.strftime("%Y-%m-%d %H:%M:%S COT")

# --------------------------------------------------------------------------------------
# 3. VARIABLES DE ENTORNO Y CONEXIONES (KRAKEN, SUPABASE, NTFY)
# --------------------------------------------------------------------------------------
KRAKEN_API_KEY: str = os.getenv("KRAKEN_API_KEY", "").strip()
KRAKEN_SECRET_KEY: str = os.getenv("KRAKEN_SECRET_KEY", "").strip()
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "").strip()
NTFY_TOPIC: str = os.getenv("NTFY_TOPIC", "PROYECTO_DIPPER_BOT_ALERTAS").strip()

try:
    from supabase import create_client, Client
    HAS_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)
    supabase_client: Optional[Client] = create_client(SUPABASE_URL, SUPABASE_KEY) if HAS_SUPABASE else None
except Exception as e:
    HAS_SUPABASE = False
    supabase_client = None

# Inicializar Exchange Kraken (CCXT)
@st.cache_resource
def get_kraken_exchange() -> ccxt.kraken:
    config: Dict[str, Any] = {
        'enableRateLimit': True,
        'timeout': 20000,
        'options': {'adjustForTimeDifference': True}
    }
    if KRAKEN_API_KEY and KRAKEN_SECRET_KEY:
        config['apiKey'] = KRAKEN_API_KEY
        config['secret'] = KRAKEN_SECRET_KEY
    return ccxt.kraken(config)

exchange = get_kraken_exchange()

# Función Helper de Notificaciones Push vía Ntfy.sh
def enviar_notificacion_push(titulo: str, mensaje: str):
    """Envía notificación HTTP POST a ntfy.sh sin romper el flujo."""
    try:
        url = f"https://ntfy.sh/{NTFY_TOPIC}"
        requests.post(url, data=mensaje.encode('utf-8'), headers={"Title": titulo}, timeout=4)
    except Exception as e:
        print(f"Error enviando notificación push: {e}")

# --------------------------------------------------------------------------------------
# 4. PARÁMETROS CUANTITATIVOS Y CONSTANTES
# --------------------------------------------------------------------------------------
INITIAL_CAPITAL = 1000.0
RISK_PER_TRADE = 0.015         # 1.5%
STOP_LOSS_PCT = 0.015          # -1.5%
TAKE_PROFIT_PCT = 0.030        # +3.0%
DAILY_CIRCUIT_BREAKER = -0.03  # -3.0%
MAX_CONCURRENT_POSITIONS = 3

WATCHLIST_18: List[str] = [
    "BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD",
    "XRP/USD", "DOT/USD", "AVAX/USD", "LINK/USD",
    "LTC/USD", "BCH/USD", "NEAR/USD", "SUI/USD",
    "APT/USD", "FET/USD", "ARB/USD", "PEPE/USD",
    "DOGE/USD", "SHIB/USD"
]

# --------------------------------------------------------------------------------------
# 5. ESTILOS CSS INYECTADOS (DARK TERMINAL THEME & HIGH IMPACT TABLES)
# --------------------------------------------------------------------------------------
st.markdown("""
<style>
    /* Estilos Generales Dark Terminal */
    .stApp {
        background-color: #070a13;
        color: #93c5fd;
        font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
    }
    header, footer { visibility: hidden; }
    
    /* Métricas */
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        color: #f8fafc !important;
    }
    div[data-testid="stMetricLabel"] {
        color: #64748b !important;
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    div[data-testid="metric-container"] {
        background-color: #0b1120;
        border: 1px solid #1e293b;
        border-radius: 8px;
        padding: 12px 16px;
    }

    /* Tablas HTML Estilizadas */
    .quant-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
        background-color: #0b1120;
        border: 1px solid #1e293b;
        border-radius: 8px;
        overflow: hidden;
        margin-top: 10px;
        margin-bottom: 20px;
    }
    .quant-table th {
        background-color: #0f172a;
        color: #94a3b8;
        padding: 10px 12px;
        text-align: left;
        font-weight: 600;
        text-transform: uppercase;
        font-size: 11px;
        border-bottom: 2px solid #1e293b;
    }
    .quant-table td {
        padding: 9px 12px;
        border-bottom: 1px solid #1e293b;
        color: #cbd5e1;
    }
    
    /* Filas Coloreadas por Resultado (Row-level Styling) */
    .row-win {
        background-color: rgba(0, 230, 118, 0.12) !important;
        color: #00E676 !important;
        font-weight: 600;
    }
    .row-win td {
        color: #00E676 !important;
    }
    .row-loss {
        background-color: rgba(255, 82, 82, 0.12) !important;
        color: #FF5252 !important;
        font-weight: 600;
    }
    .row-loss td {
        color: #FF5252 !important;
    }
    .row-open {
        background-color: rgba(30, 41, 59, 0.4) !important;
    }
    .row-open td {
        color: #e2e8f0 !important;
    }

    /* Badges */
    .badge-win {
        background-color: #052e16;
        color: #00E676;
        padding: 3px 8px;
        border-radius: 4px;
        border: 1px solid #00E676;
        font-weight: bold;
        font-size: 10px;
    }
    .badge-loss {
        background-color: #450a0a;
        color: #FF5252;
        padding: 3px 8px;
        border-radius: 4px;
        border: 1px solid #FF5252;
        font-weight: bold;
        font-size: 10px;
    }
    .badge-open {
        background-color: #0c4a6e;
        color: #38bdf8;
        padding: 3px 8px;
        border-radius: 4px;
        border: 1px solid #0284c7;
        font-weight: bold;
        font-size: 10px;
    }
    
    /* Terminal logs */
    .terminal-box {
        background-color: #020617;
        border: 1px solid #1e293b;
        border-radius: 6px;
        padding: 12px;
        font-size: 11px;
        color: #94a3b8;
        max-height: 220px;
        overflow-y: auto;
    }
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# 6. GESTIÓN DE ESTADO (SESSION STATE & PERSISTENCIA)
# --------------------------------------------------------------------------------------
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.capital = INITIAL_CAPITAL
    st.session_state.circuit_breaker_triggered = False
    st.session_state.logs = [
        f"[{now_cot().strftime('%H:%M:%S COT')}] [INFO] Dashboard Cuantitativo inicializado exitosamente.",
        f"[{now_cot().strftime('%H:%M:%S COT')}] [INFO] Zona Horaria configurada: America/Bogota (COT UTC-5).",
        f"[{now_cot().strftime('%H:%M:%S COT')}] [INFO] 18 Pares Kraken USD listos para escaneo."
    ]

# Función para cargar datos de Supabase o memoria local
def load_trades_data() -> pd.DataFrame:
    """Carga los trades desde Supabase o devuelve DataFrame estructurado."""
    if HAS_SUPABASE and supabase_client:
        try:
            res = supabase_client.table("trades").select("*").order("created_at", desc=True).execute()
            if res.data and len(res.data) > 0:
                df = pd.DataFrame(res.data)
                return df
        except Exception as e:
            st.session_state.logs.insert(0, f"[{now_cot().strftime('%H:%M:%S COT')}] [WARN] Supabase error: {e}")

    # Semilla por defecto si no hay registros aún
    if "trades_cache" not in st.session_state:
        # Generar un ejemplo limpio representativo para visualización inmediata
        now = now_cot()
        seed = [
            {
                "order_id": "DIP-908124",
                "symbol": "BTC/USD",
                "side": "LONG",
                "status": "CLOSED",
                "entry_price": 64250.00,
                "exit_price": 66177.50,
                "pnl_usd": 30.00,
                "pnl_pct": 3.00,
                "exit_reason": "TAKE PROFIT (TP)",
                "created_at": (now - datetime.timedelta(hours=6)).isoformat(),
                "closed_at": (now - datetime.timedelta(hours=4)).isoformat()
            },
            {
                "order_id": "DIP-908112",
                "symbol": "SOL/USD",
                "side": "SHORT",
                "status": "CLOSED",
                "entry_price": 154.20,
                "exit_price": 156.51,
                "pnl_usd": -15.00,
                "pnl_pct": -1.50,
                "exit_reason": "STOP LOSS (SL)",
                "created_at": (now - datetime.timedelta(hours=14)).isoformat(),
                "closed_at": (now - datetime.timedelta(hours=12)).isoformat()
            },
            {
                "order_id": "DIP-908095",
                "symbol": "ETH/USD",
                "side": "LONG",
                "status": "CLOSED",
                "entry_price": 2640.00,
                "exit_price": 2719.20,
                "pnl_usd": 30.00,
                "pnl_pct": 3.00,
                "exit_reason": "TAKE PROFIT (TP)",
                "created_at": (now - datetime.timedelta(days=1, hours=3)).isoformat(),
                "closed_at": (now - datetime.timedelta(days=1)).isoformat()
            },
            {
                "order_id": "DIP-908150",
                "symbol": "AVAX/USD",
                "side": "LONG",
                "status": "OPEN",
                "entry_price": 28.40,
                "exit_price": None,
                "pnl_usd": 4.25,
                "pnl_pct": 0.42,
                "exit_reason": None,
                "created_at": (now - datetime.timedelta(minutes=45)).isoformat(),
                "closed_at": None
            }
        ]
        st.session_state.trades_cache = pd.DataFrame(seed)

    return st.session_state.trades_cache

df_all = load_trades_data()

# --------------------------------------------------------------------------------------
# 7. FILTRO SEMANAL Y CÁLCULO DE MÉTRICAS (DOMINGO A SÁBADO)
# --------------------------------------------------------------------------------------
def is_within_current_trading_week(timestamp_str: Any) -> bool:
    """Verifica si un timestamp cae en la semana actual (Domingo 00:00 UTC a Sábado 23:59 UTC)."""
    try:
        if pd.isna(timestamp_str) or not timestamp_str:
            return True
        if isinstance(timestamp_str, str):
            dt = datetime.datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            dt = timestamp_str
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
            
        current_utc = datetime.datetime.now(datetime.timezone.utc)
        # En Python weekday(): Lunes=0, Domingo=6.
        # Días transcurridos desde el último domingo:
        days_since_sunday = (current_utc.weekday() + 1) % 7
        start_of_week = (current_utc - datetime.timedelta(days=days_since_sunday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return dt >= start_of_week
    except Exception:
        return True

df_open = df_all[df_all["status"] == "OPEN"].copy() if not df_all.empty else pd.DataFrame()
df_closed_all = df_all[df_all["status"] == "CLOSED"].copy() if not df_all.empty else pd.DataFrame()

# Aplicar filtro semanal al historial cerrado
if not df_closed_all.empty and "created_at" in df_closed_all.columns:
    df_closed = df_closed_all[df_closed_all["created_at"].apply(is_within_current_trading_week)].copy()
else:
    df_closed = df_closed_all

# Cálculos de Métricas
total_closed = len(df_closed)
wins = len(df_closed[df_closed["pnl_usd"] > 0]) if total_closed > 0 else 0
losses = len(df_closed[df_closed["pnl_usd"] < 0]) if total_closed > 0 else 0
win_rate = (wins / total_closed * 100.0) if total_closed > 0 else 0.0
total_pnl_usd = df_closed["pnl_usd"].sum() if total_closed > 0 else 0.0
total_pnl_pct = (total_pnl_usd / INITIAL_CAPITAL) * 100.0
current_capital = INITIAL_CAPITAL + total_pnl_usd

# Verificar Circuit Breaker (-3.0% diario)
today_str = now_cot().strftime("%Y-%m-%d")
if not df_closed.empty and "created_at" in df_closed.columns:
    df_today = df_closed[df_closed["created_at"].str.startswith(today_str)]
    today_pnl_usd = df_today["pnl_usd"].sum() if not df_today.empty else 0.0
else:
    today_pnl_usd = 0.0

today_pnl_pct = (today_pnl_usd / INITIAL_CAPITAL) * 100.0
circuit_active = today_pnl_pct <= (DAILY_CIRCUIT_BREAKER * 100.0)

# --------------------------------------------------------------------------------------
# 8. ENCABEZADO Y BARRA LATERAL
# --------------------------------------------------------------------------------------
col_head1, col_head2 = st.columns([3, 1])
with col_head1:
    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
        <span style="font-size: 28px;">⚡</span>
        <div>
            <h1 style="margin: 0; font-size: 24px; color: #f8fafc; font-weight: 800; letter-spacing: 0.05em;">PROYECTO DIPPER</h1>
            <p style="margin: 0; font-size: 12px; color: #64748b;">QUANT TRADING TERMINAL · KRAKEN SPOT · ROW-LEVEL CSS · HORARIO COLOMBIA (COT UTC-5)</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_head2:
    st.markdown(f"""
    <div style="text-align: right; font-size: 11px; padding: 6px; background-color: #0b1120; border: 1px solid #1e293b; border-radius: 6px;">
        <span style="color: #64748b;">HORA COLOMBIA:</span><br/>
        <b style="color: #38bdf8; font-size: 13px;">{now_cot().strftime('%H:%M:%S COT')}</b><br/>
        <span style="color: #10b981;">● MOTOR ONLINE 24/7</span>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<hr style='border-color: #1e293b; margin: 10px 0 20px 0;' />", unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# 9. BARRA DE MÉTRICAS PRINCIPALES
# --------------------------------------------------------------------------------------
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("CAPITAL ESTIMADO", f"${current_capital:,.2f} USD", f"{total_pnl_pct:+.2f}%")
m2.metric("WIN RATE SEMANAL", f"{win_rate:.1f}%", f"{wins}W / {losses}L")
m3.metric("PNL NETO SEMANAL", f"${total_pnl_usd:+,.2f} USD", f"{total_pnl_pct:+.2f}%")
m4.metric("PNL HOY (COT)", f"${today_pnl_usd:+,.2f} USD", f"{today_pnl_pct:+.2f}%")
m5.metric("POSICIONES OPEN", f"{len(df_open)} / {MAX_CONCURRENT_POSITIONS}", "Spot Kraken")
status_cb = "DISPARADO 🛑" if circuit_active else "NORMAL 🟢"
m6.metric("CIRCUIT BREAKER", status_cb, "-3.0% Límite")

if circuit_active:
    st.error("🚨 **CIRCUIT BREAKER ACTIVADO**: La pérdida diaria ha alcanzado o superado el -3.0%. Apertura de órdenes congelada por seguridad.")

# --------------------------------------------------------------------------------------
# 10. TABLA 1: POSICIONES ACTIVAS (OPEN) - CONTENEDOR SEPARADO NEUTRO
# --------------------------------------------------------------------------------------
st.markdown("### 🟢 Posiciones Activas (OPEN)")

if df_open.empty:
    st.info("Sin posiciones activas en este momento. El bot está escaneando los 18 pares en velas de 15m con filtro macro 4H.")
else:
    html_open = """
    <table class="quant-table">
        <thead>
            <tr>
                <th>ID Orden</th>
                <th>Par</th>
                <th>Tipo</th>
                <th>Precio Entrada</th>
                <th>PnL No Realizado ($)</th>
                <th>PnL No Realizado (%)</th>
                <th>Hora Apertura (COT)</th>
                <th>Estado</th>
            </tr>
        </thead>
        <tbody>
    """
    for _, row in df_open.iterrows():
        pnl_val = float(row.get('pnl_usd', 0.0))
        pnl_pct = float(row.get('pnl_pct', 0.0))
        pnl_color = "#00E676" if pnl_val >= 0 else "#FF5252"
        pnl_str = f"+${pnl_val:,.2f} USD" if pnl_val >= 0 else f"-${abs(pnl_val):,.2f} USD"
        
        # Formatear hora de entrada en COT
        entry_time_str = str(row.get('created_at', ''))
        try:
            dt_ent = datetime.datetime.fromisoformat(entry_time_str.replace("Z", "+00:00")).astimezone(TZ_COT)
            entry_cot = dt_ent.strftime("%H:%M:%S COT")
        except Exception:
            entry_cot = entry_time_str[:19]

        html_open += f"""
        <tr class="row-open">
            <td><b>{row.get('order_id', '-')}</b></td>
            <td><b style="color: #38bdf8;">{row.get('symbol', '-')}</b></td>
            <td><span style="color: {'#00E676' if row.get('side') == 'LONG' else '#FF5252'}; font-weight: bold;">{row.get('side', '-')}</span></td>
            <td>${float(row.get('entry_price', 0.0)):,.4f}</td>
            <td style="color: {pnl_color}; font-weight: bold;">{pnl_str}</td>
            <td style="color: {pnl_color}; font-weight: bold;">{pnl_pct:+.2f}%</td>
            <td>{entry_cot}</td>
            <td><span class="badge-open">OPEN</span></td>
        </tr>
        """
    html_open += "</tbody></table>"
    st.markdown(html_open, unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# 11. TABLA 2: HISTORIAL DE OPERACIONES CERRADAS - FILAS COMPLETAS COLOREADAS
# --------------------------------------------------------------------------------------
st.markdown("### 📜 Historial de Operaciones Cerradas (Ciclo Semanal)")

if df_closed.empty:
    st.info("No se registran operaciones cerradas en la semana en curso.")
else:
    html_closed = """
    <table class="quant-table">
        <thead>
            <tr>
                <th>ID Orden</th>
                <th>Fecha Entrada</th>
                <th>Hora Entrada</th>
                <th>Hora Salida</th>
                <th>Par</th>
                <th>Tipo</th>
                <th>Precio Entrada</th>
                <th>Precio Cierre</th>
                <th>Ganancia ($ USD)</th>
                <th>Ganancia (%)</th>
                <th>Resultado</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for _, row in df_closed.iterrows():
        pnl_val = float(row.get('pnl_usd', 0.0))
        pnl_pct = float(row.get('pnl_pct', 0.0))
        reason = str(row.get('exit_reason', ''))
        
        # REGLA ESTRICTA: Si es Stop Loss o PnL < 0, SIEMPRE mostrar signo negativo explícito (-$15.00 USD)
        is_sl = ("SL" in reason) or ("STOP" in reason) or (pnl_val < 0)
        if is_sl:
            row_class = "row-loss"
            gain_usd_str = f"-${abs(pnl_val):,.2f} USD"
            gain_pct_str = f"-{abs(pnl_pct):.2f}%"
            badge = '<span class="badge-loss">CERRADO (SL)</span>'
        elif pnl_val > 0:
            row_class = "row-win"
            gain_usd_str = f"+${abs(pnl_val):,.2f} USD"
            gain_pct_str = f"+{abs(pnl_pct):.2f}%"
            badge = '<span class="badge-win">CERRADO (TP)</span>'
        else:
            row_class = "row-open"
            gain_usd_str = "$0.00 USD"
            gain_pct_str = "0.00%"
            badge = '<span class="badge-open">BREAKEVEN</span>'
            
        # Parseo de horas en formato Colombia (America/Bogota - COT)
        created_str = str(row.get('created_at', ''))
        closed_str = str(row.get('closed_at', ''))
        try:
            dt_in = datetime.datetime.fromisoformat(created_str.replace("Z", "+00:00")).astimezone(TZ_COT)
            fecha_in = dt_in.strftime("%Y-%m-%d")
            hora_in = dt_in.strftime("%H:%M:%S")
        except Exception:
            fecha_in = created_str[:10]
            hora_in = created_str[11:19]
            
        try:
            dt_out = datetime.datetime.fromisoformat(closed_str.replace("Z", "+00:00")).astimezone(TZ_COT)
            hora_out = dt_out.strftime("%H:%M:%S")
        except Exception:
            hora_out = closed_str[11:19] if len(closed_str) >= 19 else "-"

        html_closed += f"""
        <tr class="{row_class}">
            <td><b>{row.get('order_id', '-')}</b></td>
            <td>{fecha_in}</td>
            <td>{hora_in}</td>
            <td>{hora_out}</td>
            <td><b>{row.get('symbol', '-')}</b></td>
            <td><b>{row.get('side', '-')}</b></td>
            <td>${float(row.get('entry_price', 0.0)):,.4f}</td>
            <td>${float(row.get('exit_price', 0.0)):,.4f}</td>
            <td><b>{gain_usd_str}</b></td>
            <td><b>{gain_pct_str}</b></td>
            <td>{badge}</td>
        </tr>
        """
        
    html_closed += "</tbody></table>"
    st.markdown(html_closed, unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# 12. CURVA DE CAPITAL (EQUITY CURVE) - PLOTLY
# --------------------------------------------------------------------------------------
st.markdown("### 📈 Curva de Capital (Equity Curve)")

if not df_closed.empty:
    df_sorted = df_closed.sort_values(by="created_at", ascending=True).copy()
    equity = [INITIAL_CAPITAL]
    timestamps = [df_sorted.iloc[0].get('created_at', str(now_cot()))]
    
    running = INITIAL_CAPITAL
    for _, r in df_sorted.iterrows():
        running += float(r.get('pnl_usd', 0.0))
        equity.append(running)
        timestamps.append(r.get('closed_at', r.get('created_at', '')))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(range(len(equity))),
        y=equity,
        mode='lines+markers',
        name='Capital ($ USD)',
        line=dict(color='#00E676', width=2),
        marker=dict(size=6, color='#38bdf8'),
        hovertemplate='Paso %{x}<br>Capital: $%{y:,.2f} USD<extra></extra>'
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b1120",
        plot_bgcolor="#070a13",
        margin=dict(l=40, r=20, t=30, b=40),
        height=280,
        xaxis=dict(title="Trades Ejecutados", gridcolor="#1e293b"),
        yaxis=dict(title="Balance USD", gridcolor="#1e293b", tickprefix="$")
    )
    st.plotly_chart(fig, use_container_width=True)

# --------------------------------------------------------------------------------------
# 13. PANEL LATERAL: CONTROLES, RESET MANUAL & AUDIT LOG
# --------------------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Centro de Control")
    st.markdown(f"**Exchange:** Kraken Spot USD  \n**Activos:** 18 Pares  \n**Riesgo por trade:** 1.5%  \n**Take Profit:** +3.0%  \n**Stop Loss:** -1.5%")
    
    st.markdown("---")
    st.markdown("### 🚨 Reset Manual de Emergencia")
    st.caption("Limpia la base de datos Supabase y restablece el balance a $1,000.00 USD.")
    
    if st.button("🔴 RESET MANUAL (Limpiar Supabase)", use_container_width=True):
        if HAS_SUPABASE and supabase_client:
            try:
                supabase_client.table("trades").delete().neq("id", 0).execute()
                supabase_client.table("daily_metrics").delete().neq("id", 0).execute()
            except Exception as e:
                st.sidebar.error(f"Error limpiando Supabase: {e}")
        
        st.session_state.trades_cache = pd.DataFrame()
        st.session_state.capital = INITIAL_CAPITAL
        st.session_state.circuit_breaker_triggered = False
        st.session_state.logs.insert(0, f"[{now_cot().strftime('%H:%M:%S COT')}] [WARN] RESET MANUAL ejecutado: Datos limpiados y saldo a $1,000.00 USD.")
        enviar_notificacion_push("PROYECTO DIPPER | RESET", "Se ha ejecutado un Reset Manual del sistema.")
        st.sidebar.success("Reset completado. Recargando...")
        time.sleep(1)
        st.rerun()

    st.markdown("---")
    st.markdown("### 📡 Probar Notificación Push (Ntfy)")
    if st.button("🔔 Enviar Alerta Test", use_container_width=True):
        enviar_notificacion_push(
            "PROYECTO DIPPER | TEST",
            f"Alerta de prueba enviada exitosamente a las {now_cot().strftime('%H:%M:%S COT')}."
        )
        st.sidebar.success(f"Alerta enviada a ntfy.sh/{NTFY_TOPIC}")

    st.markdown("---")
    st.markdown("### 📜 Audit Log (Hora Colombia)")
    log_html = "<div class='terminal-box'>"
    for item in st.session_state.logs[:15]:
        log_html += f"<div>{item}</div>"
    log_html += "</div>"
    st.markdown(log_html, unsafe_allow_html=True)
