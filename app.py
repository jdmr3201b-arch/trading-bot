import streamlit as st
import pandas as pd
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
if "market_data" not in st.session_state:
    st.session_state.market_data = {}
if "logs" not in st.session_state:
    st.session_state.logs = []

symbols = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
    "MATIC/USDT", "NEAR/USDT", "LTC/USDT", "SUI/USDT", "APT/USDT",
    "OP/USDT", "ARBV/USDT", "INJ/USDT"
]

# Controles de inicio / parada
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
    st.success(f"🟢 Bot en ejecución | Analizando: **{current_symbol}** ({st.session_state.current_index + 1}/{len(symbols)})")
else:
    st.info("🔴 Bot detenido.")

st.divider()

col_left, col_right = st.columns([1, 1])

# Instancia del motor
bot_instance = getattr(engine, 'bot', None) or (engine.TradingEngine() if hasattr(engine, 'TradingEngine') else None)

with col_left:
    st.subheader("📊 Estado del Mercado")
    if st.session_state.market_data:
        # Convertir diccionario a DataFrame para la tabla
        df = pd.DataFrame.from_dict(st.session_state.market_data, orient='index')
        st.dataframe(df, use_container_width=True)
    else:
        st.write("Cargando datos del mercado...")

with col_right:
    st.subheader("📝 Bitácora de Decisiones de la IA")
    # Obtener logs acumulados
    current_logs = st.session_state.logs
    if bot_instance and hasattr(bot_instance, 'logs') and bot_instance.logs:
        current_logs = bot_instance.logs
    elif hasattr(engine, 'logs') and engine.logs:
        current_logs = engine.logs

    log_text = "\n".join(current_logs[-15:][::-1]) if current_logs else "Esperando primer análisis..."
    st.text_area("Logs:", value=log_text, height=250, disabled=True)

# Bucle de ejecución
if st.session_state.is_running:
    target_symbol = symbols[st.session_state.current_index]
    
    try:
        result = None
        if bot_instance and hasattr(bot_instance, 'run_cycle_for_symbol'):
            result = bot_instance.run_cycle_for_symbol(target_symbol)
        elif hasattr(engine, 'run_cycle_for_symbol'):
            result = engine.run_cycle_for_symbol(target_symbol)
            
        # Extraer resultado estructurado del par
        if isinstance(result, dict):
            st.session_state.market_data[target_symbol] = result
        else:
            # Si el motor guarda un estado interno por par, lo extraemos
            status_dict = getattr(bot_instance, 'latest_status', {}) if bot_instance else getattr(engine, 'latest_status', {})
            if target_symbol in status_dict:
                st.session_state.market_data[target_symbol] = status_dict[target_symbol]
            else:
                st.session_state.market_data[target_symbol] = {
                    "Símbolo": target_symbol,
                    "Estado": "Monitoreando",
                    "Última Actualización": time.strftime("%H:%M:%S")
                }

        # Sincronizar logs acumulados
        if bot_instance and hasattr(bot_instance, 'logs') and bot_instance.logs:
            st.session_state.logs = bot_instance.logs
        elif hasattr(engine, 'logs') and engine.logs:
            st.session_state.logs = engine.logs

    except Exception as e:
        error_msg = f"⚠️ Error en {target_symbol}: {str(e)}"
        if error_msg not in st.session_state.logs:
            st.session_state.logs.append(error_msg)

    # Pasar al siguiente par
    st.session_state.current_index = (st.session_state.current_index + 1) % len(symbols)
    time.sleep(1)
    st.rerun()
