import streamlit as st
import time
import engine

st.set_page_config(
    page_title="Bot de Trading - PROYECTO DIPPER",
    layout="wide"
)

st.title("🤖 Bot de Trading - PROYECTO DIPPER")

# Inicializar estados de sesión
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "logs" not in st.session_state:
    st.session_state.logs = []

# Controles
col1, col2 = st.columns(2)
with col1:
    if st.button("▶️ Iniciar Bot", type="primary", use_container_width=True):
        st.session_state.is_running = True
        st.rerun()

with col2:
    if st.button("⏹️ Detener Bot", type="secondary", use_container_width=True):
        st.session_state.is_running = False
        st.rerun()

if st.session_state.is_running:
    st.success("🟢 Bot en ejecución...")
else:
    st.info("🔴 Bot detenido.")

st.divider()

col_left, col_right = st.columns([1, 1])

# Instancia del motor
bot_instance = getattr(engine, 'bot', None) or (engine.TradingEngine() if hasattr(engine, 'TradingEngine') else None)

with col_left:
    st.subheader("📊 Estado del Mercado")
    if bot_instance and hasattr(bot_instance, 'get_status_dataframe'):
        df = bot_instance.get_status_dataframe()
        st.dataframe(df, use_container_width=True)
    elif hasattr(engine, 'get_status_dataframe'):
        st.dataframe(engine.get_status_dataframe(), use_container_width=True)
    else:
        st.write("Cargando datos del mercado...")

with col_right:
    st.subheader("📝 Bitácora de Decisiones de la IA")
    # Intentar obtener logs desde el bot o la sesión
    current_logs = []
    if bot_instance and hasattr(bot_instance, 'logs'):
        current_logs = bot_instance.logs
    elif hasattr(engine, 'logs'):
        current_logs = engine.logs
    
    log_text = "\n".join(current_logs[-15:][::-1]) if current_logs else "Ejecutando análisis de mercado..."
    st.text_area("Logs:", value=log_text, height=250, disabled=True)

# Ejecución ciclo a ciclo
if st.session_state.is_running:
    symbols = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
        "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
        "MATIC/USDT", "NEAR/USDT", "LTC/USDT", "SUI/USDT", "APT/USDT",
        "OP/USDT", "ARBV/USDT", "INJ/USDT"
    ]

    status_placeholder = st.empty()
    
    for selected_symbol in symbols:
        status_placeholder.info(f"🔎 Analizando {selected_symbol}...")
        try:
            if bot_instance:
                bot_instance.run_cycle_for_symbol(selected_symbol)
            elif hasattr(engine, 'run_cycle_for_symbol'):
                engine.run_cycle_for_symbol(selected_symbol)
        except Exception as e:
            st.warning(f"Error procesando {selected_symbol}: {e}")

    status_placeholder.empty()
    time.sleep(3)
    st.rerun()
