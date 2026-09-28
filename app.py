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
if "current_index" not in st.session_state:
    st.session_state.current_index = 0

symbols = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
    "MATIC/USDT", "NEAR/USDT", "LTC/USDT", "SUI/USDT", "APT/USDT",
    "OP/USDT", "ARBV/USDT", "INJ/USDT"
]

# Controles
col1, col2 = st.columns(2)
with col1:
    if st.button("▶️ Iniciar Bot", type="primary", use_container_width=True):
        st.session_state.is_running = True
        st.session_state.current_index = 0
        st.rerun()

with col2:
    if st.button("⏹️ Detener Bot", type="secondary", use_container_width=True):
        st.session_state.is_running = False
        st.rerun()

if st.session_state.is_running:
    current_symbol = symbols[st.session_state.current_index]
    st.success(f"🟢 Bot en ejecución | Procesando: **{current_symbol}** ({st.session_state.current_index + 1}/{len(symbols)})")
else:
    st.info("🔴 Bot detenido.")

st.divider()

col_left, col_right = st.columns([1, 1])

# Instancia del motor
bot_instance = getattr(engine, 'bot', None) or (engine.TradingEngine() if hasattr(engine, 'TradingEngine') else None)

with col_left:
    st.subheader("📊 Estado del Mercado")
    if bot_instance and hasattr(bot_instance, 'get_status_dataframe'):
        try:
            df = bot_instance.get_status_dataframe()
            st.dataframe(df, use_container_width=True)
        except Exception:
            st.write("Cargando datos del mercado...")
    else:
        st.write("Cargando datos del mercado...")

with col_right:
    st.subheader("📝 Bitácora de Decisiones de la IA")
    current_logs = []
    if bot_instance and hasattr(bot_instance, 'logs'):
        current_logs = bot_instance.logs
    elif hasattr(engine, 'logs'):
        current_logs = engine.logs
    
    log_text = "\n".join(current_logs[-15:][::-1]) if current_logs else "Esperando primer análisis..."
    st.text_area("Logs:", value=log_text, height=250, disabled=True)

# Ejecutar el ciclo par por par de forma continua
if st.session_state.is_running:
    target_symbol = symbols[st.session_state.current_index]
    
    print(f"=== PROCESANDO PAR: {target_symbol} ===", flush=True)
    
    try:
        if bot_instance:
            bot_instance.run_cycle_for_symbol(target_symbol)
        elif hasattr(engine, 'run_cycle_for_symbol'):
            engine.run_cycle_for_symbol(target_symbol)
    except Exception as e:
        print(f"Error en {target_symbol}: {e}", flush=True)

    # Avanzar al siguiente símbolo para la próxima recarga
    st.session_state.current_index = (st.session_state.current_index + 1) % len(symbols)
    time.sleep(1)
    st.rerun()
