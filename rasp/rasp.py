import paho.mqtt.client as mqtt
import json
import requests
from datetime import datetime
import time

# ----------------------
# Configs de Controlo - ir buscar com @api_bp.get('/actions/<gateway_id>')
# ----------------------
# temperatura maxima e velocidade de ventoinhas definidas pelo utilizador
#TEMP_HIGH = 
#CPU_HIGH =
#SPEED =

TEMP_HIGH = 18.0
TEMP_LOW = 16.0
VM_CRITICA = 90.0
RACK_CRITICO = 75.0

# ----------------------
# Estado Global (Mapas) - recebe info a cada 15 segundos
# ----------------------
state_temperatures = {} # guarda a ultima temperatura de cada rack
state_cpus = {}         # guarda a ultima CPU de cada VM em cada rack
state_fans = {}         # guarda o estado atual das ventoinhas de cada rack

# ----------------------
# Controlo de Envios (a cada 1 minuto)
# ----------------------
last_send_time = 0  
send_interval = 60  

# ----------------------
# Configs de Topicos
# ----------------------
topic_temp = "rack/temperatura"
topic_cpu =  "vm/cpu"

# -----------------------------------------
# Funções de Controlo
# -----------------------------------------
def get_media_cpu_rack(rack_id):
    if rack_id not in state_cpus or not state_cpus[rack_id]:
        return 0.0
    vms_no_rack = state_cpus[rack_id]
    total_cpu = sum(vms_no_rack.values())
    return total_cpu / len(vms_no_rack)

def find_migration_target(rack_origem):
    rack_destino = None
    menor_carga = 100.0
    menor_temp = float('inf')
    
    for rack_id in state_temperatures:
        if rack_id == rack_origem:
            continue
        
        temp_rack = state_temperatures.get(rack_id, 0)
        media_cpu = get_media_cpu_rack(rack_id)
        
        # Encontrar o rack com menor carga (prioridade) e menor temperatura 
        # TODO: quão menor para realmente compensar trocar??
        if media_cpu < menor_carga or (media_cpu == menor_carga and temp_rack < menor_temp):
            rack_destino = rack_id
            menor_carga = media_cpu
            menor_temp = temp_rack
    
    if rack_destino and menor_carga < RACK_CRITICO:
        return rack_destino
    else:
        return None
    
def control_fan(rack_id, client):
    temp_atual = state_temperatures.get(rack_id, 0)
    media_cpu = get_media_cpu_rack(rack_id)
    ventoinha_ligada = state_fans.get(rack_id, False)
    
    topico_controlo = f"rack/{rack_id}/controlo"
    
    # TODO: logica do tempo
    # Ligar/Aumentar: Temp alta ou normal mas carga alta e sem migração possível (durante 10 segundos)
    if temp_atual >= TEMP_HIGH or media_cpu >= RACK_CRITICO:
        if not ventoinha_ligada:
            motivo = "Temperatura Crítica" if temp_atual >= TEMP_HIGH else "Prevenção por Sobrecarga de CPU"
            print(f"[AÇÃO RACK {rack_id}] LIGAR ventoinhas! Motivo: {motivo}")
            client.publish(topico_controlo, "1")
            state_fans[rack_id] = True
            
    # Desligar/Diminuir: Temp baixou e carga normalizou (durante 5 segundos)
    elif temp_atual <= TEMP_LOW and media_cpu < RACK_CRITICO:
        if ventoinha_ligada:
            print(f"[AÇÃO RACK {rack_id}] DESLIGAR ventoinhas.")
            client.publish(topico_controlo, "0")
            state_fans[rack_id] = False

# -----------------------------------------
# Envio de Dados (a cada 1 minuto)
# -----------------------------------------
def send_latest_data():
    global last_send_time
    
    current_time = time.time()
    if current_time - last_send_time >= send_interval:
        payload = {
            "timestamp": datetime.now().isoformat(),
            "temperature_data": state_temperatures,
            "cpu_data": state_cpus,
            "fan_status": state_fans
        }
        
        try:
            # TODO: enviar para o @api_bp.post('/data') do backend
            print(f"Dados enviados com sucesso!")
            last_send_time = current_time 
        except requests.exceptions.RequestException as e:
            print(f"Falha ao enviar dados: {e}")

# -----------------------------------------
# Tratamento das Mensagens (MQTT)
# -----------------------------------------
def on_message(client, userdata, msg):
    message = msg.payload.decode("utf-8")

    if msg.topic == topic_temp:
        try:
            dados = json.loads(message)
            temperatura = float(dados.get("temperatura"))
            rack_id = str(dados.get("rack_id"))

            state_temperatures[rack_id] = temperatura
            send_latest_data()
            control_fan(rack_id, client)
            
        except Exception as e:
            print(f"[ERRO MQTT] Falha ao ler dados: {e}")

    elif msg.topic == topic_cpu:
        try:
            dados = json.loads(message)
            vm_id = dados.get("vm_id")
            cpu_usage = float(dados.get("cpu", 0))
            temperatura = float(dados.get("temp", 0))

            # ir ao id_rack.json buscar o rack_id do vm_id
            rack_id = "rack1" # TODO: substituir por leitura do ficheiro json

            if rack_id not in state_cpus:
                state_cpus[rack_id] = {}
            state_cpus[rack_id][vm_id] = cpu_usage

            send_latest_data()
            
            # prevenão
            if cpu_usage >= VM_CRITICA:
                media_rack = get_media_cpu_rack(rack_id)
                print(f"[ALERTA] {vm_id} no Rack {rack_id} com {cpu_usage}% de CPU. (Média do Rack: {media_rack:.1f}%)")
                
                # se o rack estiver muito carregado
                if media_rack >= RACK_CRITICO:
                    migrar = find_migration_target(rack_id)
            
            control_fan(rack_id, client)
            
        except Exception as e:
            print(f"[ERRO MQTT] Falha ao ler dados: {e}")

# TODO
# na inicialização fazer post do gateway proprio (link code nº random base64)
# file json com id rack (controladr) ----> hostname do hypervisor
# ir buscar info a base de dados para configs de cada cliente  guarcdar estas configs e o gateway num fichiro caso seja preciso reconectar

client = mqtt.Client("RaspPi")
client.on_message = on_message

print("Connecting to MQTT broker...")
client.connect("localhost", 1883, 60)
client.subscribe(topic_temp)
client.subscribe(topic_cpu)
print(f"Subscribed to topic '{topic_temp}' and '{topic_cpu}'")

last_send_time = time.time()
print("Sistema pronto. Dados serão enviados a cada 1 minuto...\n")

client.loop_forever()


