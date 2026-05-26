import requests
import os
import json
from gateway import save_to_env

# ------------------------------
# Carregar Configuração de Uso
# ------------------------------
def fetch_and_cache_config(gateway_id, backend_api_url):
    try:
        headers = {}
        
        # Enviar linkCode no header Authorization
        link_code = os.getenv("LINK_CODE")
        if link_code:
            headers['Authorization'] = link_code
        
        response = requests.get(f"{backend_api_url}/actions/{gateway_id}", headers=headers, timeout=5)
        
        if response.status_code == 200:
            actions = response.json().get('actions', [])
            
            if actions:
                action = actions[0]
                config_values = {
                    'TEMP_HIGH': float(action.get('temp', 20.0)),
                    'CPU_HIGH': float(action.get('cpu', 90.0)),
                    'SPEED': float(action.get('speed', 150.0)),
                }
                
                # Guardar no .env
                for key, value in config_values.items():
                    save_to_env(key, value)
                
                print("[SISTEMA] Configurações carregadas com sucesso!")
                print(f"  - TEMPERATURE LIMIT: {config_values['TEMP_HIGH']}")
                print(f"  - CPU LIMIT: {config_values['CPU_HIGH']}")
                print(f"  - MAX FAN SPEED: {config_values['SPEED']}")
                
                return config_values
        else:
            print(f"[AVISO] Falha ao ler configurações: {response.status_code}")
            print(f"[AVISO] Utilizando configurações locais")
            
    except requests.exceptions.RequestException as e:
        print(f"[AVISO] Erro ao ler configurações do backend: {e}")
        print(f"[AVISO] Utilizando configurações locais")
    
    return None

# ------------------------------
# Carregar Configuração de Racks
# ------------------------------
def update_gateway_controllers(gateway_id, backend_api_url, controllers):
    """Atualiza a lista de controllers (ESP32s) no backend."""
    try:
        gateway_update = {
            "controllers": controllers
        }
        headers = {}
        
        # Enviar linkCode no header Authorization
        link_code = os.getenv("LINK_CODE")
        if link_code:
            headers['Authorization'] = link_code
        
        response = requests.patch(
            f"{backend_api_url}/gateways/{gateway_id}",
            json=gateway_update,
            headers=headers,
            timeout=5
        )
        
        if response.status_code != 200:
            print(f"[ERRO] Falha ao atualizar controllers: {response.status_code}")
            print(f"[ERRO] Resposta: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"[ERRO] Falha ao atualizar controllers: {e}")

def load_rack_config():
    """Carrega a configuração de racks do ficheiro rack.json."""
    try:
        rack_file = os.path.join(os.path.dirname(__file__), 'rack.json')
        if os.path.exists(rack_file):
            with open(rack_file, 'r') as f:
                return json.load(f)
        else:
            print(f"[AVISO] Ficheiro rack.json não encontrado em {rack_file}")
            return {}
    except Exception as e:
        print(f"[ERRO] Falha ao carregar rack.json: {e}")
        return {}

def initialize_vms_from_config(vms_dict, controllers, gateway_id, backend_api_url):
    """Inicializa o dicionário de VMs com informação de rack.json."""
    rack_config = load_rack_config()
    for rack_id, hosts in rack_config.items():
        vms_dict[rack_id] = {}
        controllers.append(rack_id)
        for host in hosts:
            vms_dict[rack_id][host] = 0.0  # Inicializar com CPU 0%

    update_gateway_controllers(gateway_id, backend_api_url, controllers)
    return rack_config
