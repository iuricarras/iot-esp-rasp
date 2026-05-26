import json
import requests
import time
import os
from control import get_media_cpu_rack, find_migration_target, control_fan, migrate_vm

# ----------------------
# Gestão de Estado MQTT
# ----------------------
class MQTTState:
    """Gerencia o estado necessário para o MQTT."""
    def __init__(self):
        self.last_send_time = 0
        self.send_interval = 60
        
    def update_send_time(self, current_time):
        self.last_send_time = current_time

# Estado global do MQTT
mqtt_state = MQTTState()

# ----------------------
# Envio de Dados ao Backend (a cada 1 minuto)
# ----------------------
def send_latest_data(gateway_id, backend_api_url, state_temperatures, state_cpus, state_fans):
    """Envia dados para o backend."""
    current_time = time.time()
    if current_time - mqtt_state.last_send_time >= mqtt_state.send_interval:
        payload = {
            "gatewayID": gateway_id,
            "timestamp": int(time.time()),
            "temperature_data": state_temperatures,
            "cpu_data": state_cpus,
            "fan_status": state_fans
        }
        
        try:
            response = requests.post(
                f"{backend_api_url}/data",
                json=payload,
                timeout=5
            )
            
            if response.status_code == 201:
                print(f"[DATA] Dados enviados com sucesso!")
                print() 
                mqtt_state.update_send_time(current_time)
            else:
                print(f"[DATA] Falha ao enviar dados: {response.status_code}")
                print(f"[DATA] Resposta: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"[DATA] Falha ao enviar dados: {e}")

# ----------------------
# Envio de Dados Críticos ao Backend
# ----------------------
def send_critical_data(gateway_id, backend_api_url, state_temperatures, state_cpus, state_fans, critical_reason):
    """Envia dados críticos imediatamente para o backend."""
    if not gateway_id or not backend_api_url:
        print("[ALERTA] Gateway ID ou Backend URL não configurados para envio crítico")
        return
    
    payload = {
        "gatewayID": gateway_id,
        "timestamp": int(time.time()),
        "temperature_data": state_temperatures,
        "cpu_data": state_cpus or {},
        "fan_status": state_fans or {},
        "critical": True,
        "critical_reason": critical_reason
    }
    
    try:
        response = requests.post(
            f"{backend_api_url}/data",
            json=payload,
            headers={"Authorization": os.getenv("LINK_CODE", "")}
        )
        
        if response.status_code == 201:
            print(f"[ALERTA] Dados críticos enviados ao backend: {critical_reason}")
        else:
            print(f"[AVISO] Falha ao enviar dados críticos ({response.status_code})")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar alerta crítico: {e}")

# ----------------------
# Tratamento das Mensagens (MQTT)
# ----------------------
def on_message(client, userdata, msg, gateway_id, backend_api_url, controllers, 
               state_temperatures, state_cpus, state_fans,
               mqtt_topic_temp, mqtt_topic_cpu, cpu_high, rack_critico):
    """Callback de recebimento de mensagens MQTT."""
    message = msg.payload.decode("utf-8")

    if msg.topic == mqtt_topic_temp:
        try:
            dados = json.loads(message)
            temperatura = float(dados.get("temperatura"))
            rack_id = str(dados.get("rack_id"))

            state_temperatures[rack_id] = temperatura
            control_fan(rack_id, client, gateway_id, backend_api_url, state_temperatures, state_cpus, state_fans)
            
        except Exception as e:
            print(f"[ERRO MQTT] Falha ao ler dados de temperatura: {e}")

    elif msg.topic == mqtt_topic_cpu:
        try:
            dados = json.loads(message)
            vm_id = dados.get("vm_id")
            cpu_usage = float(dados.get("cpu", 0))
            temperatura = float(dados.get("temp", 0))
            
            rack_id = None
            for r_id, vms in vms.items():
                if vm_id in vms:
                    rack_id = r_id
                    break

            if rack_id is None:
                print(f"[ERRO] VM {vm_id} não encontrada em nenhum rack.")
                return

            if rack_id not in state_cpus:
                state_cpus[rack_id] = {}
            state_cpus[rack_id][vm_id] = cpu_usage
            
            # Prevenção de carga alta
            if cpu_usage >= cpu_high:
                media_rack = get_media_cpu_rack(rack_id)
                print(f"[ALERTA] {vm_id} no Rack {rack_id} com {cpu_usage}% de CPU. (Média do Rack: {media_rack:.1f}%)")
                
                # Se o rack estiver muito carregado
                if media_rack >= rack_critico:
                    migrar = find_migration_target(rack_id)
                    migrate_vm(vm_id, rack_id, migrar)
            
            control_fan(rack_id, client, gateway_id, backend_api_url, state_temperatures, state_cpus, state_fans)
            
        except Exception as e:
            print(f"[ERRO MQTT] Falha ao ler dados de CPU: {e}")

# ----------------------
# Thread para enviar dados para o backend periodicamente
# ----------------------
def send_data_periodic(gateway_id, backend_api_url, state_temperatures, state_cpus, state_fans):
    """Envia dados a cada minuto, independentemente de mensagens MQTT."""
    while True:
        time.sleep(mqtt_state.send_interval)
        send_latest_data(gateway_id, backend_api_url, state_temperatures, state_cpus, state_fans)
