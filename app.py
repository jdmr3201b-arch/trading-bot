import streamlit as st
import time
import engine

st.set_page_config(
    page_title="Bot de Trading - PROYECTO DIPPER",
    layout="wide"
)

st.title("🤖 Bot de Trading - PROYECTO DIPPER")

# Inicializar estado de ejecución
if "is_running" not in st.session_state:
    st.session_state.is_running = False

# Controles principales
col1, col2 = st.columns(2)

with col1:
    if st.button("▶️ Iniciar Bot", type="primary", use_container_width=True):
        st.session_state.is_running = True
        st.rerun()

with col2:
    if st.button("⏹️ Detener Bot", type="secondary", use_container_width=True):
        st.session_state.is_running = False
        st.rerun()

# Estado actual
if st.session_state.is_running:
    st.success("🟢 Bot en ejecución...")
else:
    st.info("🔴 Bot detenido.")

st.divider()

# Sección de métricas y logs
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("📊 Estado del Mercado")
    if hasattr(engine, 'get_status_dataframe'):
        df = engine.get_status_dataframe()
        st.dataframe(df, use_container_width=True)
    else:
        st.write("Cargando datos del mercado...")

with col_right:
    st.subheader("📝 Bitácora de Decisiones de la IA")
    log_text = "\n".join(engine.logs[-10:][::-1]) if hasattr(engine, 'logs') else "Sin eventos aún."
    st.text_area("Logs:", value=log_text, height=220, disabled=True)

# Bucle de ejecución
if st.session_state.is_running:
    symbols = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
        "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
        "MATIC/USDT", "NEAR/USDT", "LTC/USDT", "SUI/USDT", "APT/USDT",
        "OP/USDT", "ARBV/USDT", "INJ/USDT"
    ]

    # Crear instancia del motor si existe la clase TradingEngine
    bot_instance = getattr(engine, 'bot', None) or (engine.TradingEngine() if hasattr(engine, 'TradingEngine') else None)

    for selected_symbol in symbols:
        if bot_instance:
            bot_instance.run_cycle_for_symbol(selected_symbol)
        elif hasattr(engine, 'run_cycle_for_symbol'):
            engine.run_cycle_for_symbol(selected_symbol)

    time.sleep(5)
    st.rerun()
