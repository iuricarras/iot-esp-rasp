import paho.mqtt.client as mqtt
import dotenv
import os
import signal
import sys
import threading
from proxmoxer import ProxmoxAPI


from gateway import load_or_generate_gateway_id, initialize_gateway, wait_for_gateway_linked
from config import fetch_and_cache_config, initialize_vms_from_config
from control import set_state_variables, set_config_variables
import mqtt as mqtt_module

# ----------------------
# Estado Global 
# ----------------------
state_temperatures = {} # guarda a ultima temperatura de cada rack
state_cpus = {}         # guarda a ultima CPU de cada VM em cada rack
state_fans = {}         # guarda o estado atual das ventoinhas de cada rack
controllers = []        # lista de ESP32s (rackIDs) associados ao gateway
vms = {}                # conjunto de vms em cada rack

# ----------------------
# Variáveis de Ambiente
# ----------------------
dotenv.load_dotenv()
BACKEND_API_URL = os.getenv("BACKEND_API_URL")
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT"))
MQTT_TOPIC_TEMP = os.getenv("MQTT_TOPIC_TEMP")
MQTT_TOPIC_CPU = os.getenv("MQTT_TOPIC_CPU")

# ---------------------
# Inicialização
# ---------------------
print("\n" + "="*50)
print("[SISTEMA] Inicializando Gateway...")
print("="*50)

# Gerar/carregar GATEWAY_ID
GATEWAY_ID = load_or_generate_gateway_id(BACKEND_API_URL)
print(f"\n[SISTEMA] Gateway ID: {GATEWAY_ID}")
print("="*50)

# -----------------------------------------
# Handler para desligar o gateway ao encerrar
# -----------------------------------------
def signal_handler(sig, frame):
    print("\n[SHUTDOWN] Encerrando sistema...")
    print(f"[GATEWAY] Encerrando gateway...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Inicializar gateway
gateway_ready = initialize_gateway(GATEWAY_ID, BACKEND_API_URL)
if not gateway_ready:
    print("\n[AVISO] Falha ao inicializar gateway.")
    print("[AVISO] O sistema vai continuar, mas sem acesso ao backend.\n")
    # Continuar sem backend
    TEMP_HIGH = float(os.getenv("TEMP_HIGH", 20.0))
    CPU_HIGH = float(os.getenv("CPU_HIGH", 90.0))
    FAN_SPEED = float(os.getenv("FAN_SPEED", 150.0))
    RACK_CRITICO = float(os.getenv("RACK_CRITICO", 75.0))
    
    set_config_variables(TEMP_HIGH, CPU_HIGH, FAN_SPEED, RACK_CRITICO)
else:
    print("[GATEWAY] Gateway inicializado com sucesso!")
    # Esperar até o gateway ser linked
    wait_for_gateway_linked(GATEWAY_ID, BACKEND_API_URL)
    
    # Buscar configurações do backend
    print("\n[GATEWAY] Carregando configurações de controlo...")
    fetch_and_cache_config(GATEWAY_ID, BACKEND_API_URL)
    
    # Recarregar as variáveis de ambiente após guardar
    dotenv.load_dotenv(override=True)
    TEMP_HIGH = float(os.getenv("TEMP_HIGH", 20.0))
    CPU_HIGH = float(os.getenv("CPU_HIGH", 90.0))
    FAN_SPEED = float(os.getenv("FAN_SPEED", 150.0))
    RACK_CRITICO = float(os.getenv("RACK_CRITICO", 75.0))
    
    # Inicializar módulo de controlo com variáveis de configuração
    set_config_variables(TEMP_HIGH, CPU_HIGH, FAN_SPEED, RACK_CRITICO)


# Inicializar vms e controllers com informação de rack.json
rack_config = initialize_vms_from_config(vms, controllers, GATEWAY_ID, BACKEND_API_URL)
print(f"[SISTEMA] Racks associados: {list(rack_config.keys())}")
for rack_id, hosts in rack_config.items():
    print(f"  - {rack_id}: {hosts}")
print("="*50 + "\n")


# -------------------
# MQTT Client Setup 
# -------------------
def on_message(client, userdata, msg):
    mqtt_module.on_message(client, userdata, msg, GATEWAY_ID, BACKEND_API_URL, controllers,
                           state_temperatures, state_cpus, state_fans,
                           MQTT_TOPIC_TEMP, MQTT_TOPIC_CPU, CPU_HIGH, RACK_CRITICO)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "RaspPi")
client.on_message = on_message

print("\n" + "="*50)
print("Conectando ao broker MQTT...")
print("="*50)
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.subscribe(MQTT_TOPIC_TEMP)
client.subscribe(MQTT_TOPIC_CPU)
print(f"Subscrito ao tópico '{MQTT_TOPIC_TEMP}' e '{MQTT_TOPIC_CPU}'")

print("\n" + "="*50)
print("Dados serão recebidos a cada 5 segundos...")
print("Dados serão guardados a cada 1 minuto...")
print("="*50 + "\n")

# -----------------------------------------
# Thread para enviar dados periodicamente (minuto a minuto)
# -----------------------------------------
data_thread = threading.Thread(
    target=mqtt_module.send_data_periodic,
    args=(GATEWAY_ID, BACKEND_API_URL, state_temperatures, state_cpus, state_fans),
    daemon=True
)
data_thread.start()

client.loop_forever()