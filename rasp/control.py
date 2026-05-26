import time
import os
from proxmoxer import ProxmoxAPI

state_temperatures = {}
state_cpus = {}
state_fans = {}
fan_pending_actions = {}
fan_speeds = {}  # Rastreia a velocidade atual de cada ventoinha (0 a FAN_SPEED)
fan_control_confirmation = {}  # Rastreia ações em confirmação (aguardando 10s)

# Configurações (do .env)
TEMP_HIGH = float(os.getenv("TEMP_HIGH", 18.0))
CPU_HIGH = float(os.getenv("CPU_HIGH", 90.0))
FAN_SPEED = float(os.getenv("FAN_SPEED", 150.0))
RACK_CRITICO = float(os.getenv("RACK_CRITICO", 75.0))

def set_state_variables(temps, cpus, fans, pending_actions):
    """
    Define as variáveis de estado global para uso nas funções de controlo
    """
    global state_temperatures, state_cpus, state_fans, fan_pending_actions, fan_speeds, fan_control_confirmation
    state_temperatures = temps
    state_cpus = cpus
    state_fans = fans
    fan_pending_actions = pending_actions
    fan_control_confirmation = {}  # Limpar confirmações ao reiniciar
    # Inicializar velocidades das ventoinhas a 0
    for rack_id in fans:
        if rack_id not in fan_speeds:
            fan_speeds[rack_id] = 0.0

def set_config_variables(temp_high, cpu_high, fan_speed, rack_critico):
    """
    Define as variáveis de configuração para uso nas funções de controlo
    """
    global TEMP_HIGH, CPU_HIGH, FAN_SPEED, RACK_CRITICO
    TEMP_HIGH = temp_high
    CPU_HIGH = cpu_high
    FAN_SPEED = fan_speed
    RACK_CRITICO = rack_critico

# -----------------------------------------
# Funções de Controlo de Ventoinhas
# -----------------------------------------
def get_media_cpu_rack(rack_id):
    """
    Calcula a média de CPU de todas as VMs num rack
    """
    if rack_id not in state_cpus or not state_cpus[rack_id]:
        return 0.0
    vms_no_rack = state_cpus[rack_id]
    total_cpu = sum(vms_no_rack.values())
    return total_cpu / len(vms_no_rack)

def control_fan(rack_id, client, gateway_id=None, backend_api_url=None, state_temps=None, state_cpus_dict=None, state_fans_dict=None):
    """
    Controla as ventoinhas de um rack via ESP32
    - Aguarda 10 segundos de confirmação antes de enviar comando
    - Envia comando "INCREASE_TO:150" se temperatura/CPU se mantiver alta
    - Envia comando "DECREASE_TO:0" se temperatura/CPU se mantiver normal
    O ESP32 é responsável por incrementar/decrementar gradualmente
    
    Parâmetros opcionais para envio imediato ao backend em caso crítico:
    - gateway_id, backend_api_url: para envio imediato
    - state_temps, state_cpus_dict, state_fans_dict: dados do sistema
    """
    global fan_control_confirmation
    from mqtt import send_critical_data
    
    temp_atual = state_temperatures.get(rack_id, 0)
    media_cpu = get_media_cpu_rack(rack_id)
    current_time = time.time()
    
    # Verificar condições de aumentar/diminuir
    should_speed_up = temp_atual >= TEMP_HIGH or media_cpu >= RACK_CRITICO
    should_speed_down = temp_atual < TEMP_HIGH and media_cpu < RACK_CRITICO
    
    # ========================================
    # LÓGICA DE CONFIRMAÇÃO (10 segundos)
    # ========================================
    
    # Se deve aumentar velocidade
    if should_speed_up:
        motivo = "Temperatura Crítica" if temp_atual >= TEMP_HIGH else "Prevenção por Sobrecarga de CPU"
        
        # Verificar se já está em confirmação
        if rack_id not in fan_control_confirmation:
            # Iniciar confirmação
            fan_control_confirmation[rack_id] = {
                "action": "increase",
                "start_time": current_time,
                "motivo": motivo,
                "initial_temp": temp_atual,
                "initial_cpu": media_cpu
            }
            print(f"[CONFIRMAÇÃO RACK {rack_id}] Aguardando 10s para confirmar ação: AUMENTAR. Motivo: {motivo}")
        else:
            conf = fan_control_confirmation[rack_id]
            tempo_decorrido = current_time - conf["start_time"]
            
            # Se 10 segundos decorreram e condição se mantém
            if tempo_decorrido >= 10:
                # Executar ação confirmada
                topico_controlo = f"rack/{rack_id}/controlo"
                client.publish(topico_controlo, f"INCREASE_TO:{int(FAN_SPEED)}")
                state_fans[rack_id] = FAN_SPEED  # Atualizar estado da ventoinha
                print(f"[AÇÃO RACK {rack_id}] ✓ CONFIRMADO! Comando: AUMENTAR para {int(FAN_SPEED)}. Motivo: {conf['motivo']}")
                
                # Enviar dados críticos ao backend
                send_critical_data(gateway_id, backend_api_url, state_temps, state_cpus_dict or {}, state_fans_dict or {}, conf["motivo"])
                
                # Limpar confirmação após ação
                del fan_control_confirmation[rack_id]
    
    # Se deve diminuir velocidade
    elif should_speed_down:
        if rack_id not in fan_control_confirmation:
            # Iniciar confirmação
            fan_control_confirmation[rack_id] = {
                "action": "decrease",
                "start_time": current_time
            }
            print(f"[CONFIRMAÇÃO RACK {rack_id}] Aguardando 10s para confirmar ação: DIMINUIR")
        else:
            conf = fan_control_confirmation[rack_id]
            tempo_decorrido = current_time - conf["start_time"]
            
            # Se 10 segundos decorreram e condição se mantém
            if tempo_decorrido >= 10:
                topico_controlo = f"rack/{rack_id}/controlo"
                client.publish(topico_controlo, "DECREASE_TO:0")
                state_fans[rack_id] = 0  # Atualizar estado da ventoinha
                print(f"[AÇÃO RACK {rack_id}] ✓ CONFIRMADO! Comando: DIMINUIR para 0")

                # TODO: enviar info ao backend que voltou ao normal e ventoinha a desligar
                # TODO: esp pode enviar a velocidade da ventoinha quando envia a temperatura (para atualizar o state_fans de forma correta)
                
                # Limpar confirmação após ação
                del fan_control_confirmation[rack_id]
    
    # Se nenhuma ação é necessária, limpar confirmação pendente
    else:
        if rack_id in fan_control_confirmation:
            conf = fan_control_confirmation[rack_id]
            print(f"[CANCELAMENTO RACK {rack_id}] Condição normalizada. Ação {conf['action']} cancelada.")
            del fan_control_confirmation[rack_id]

# -----------------------------------------
# Funções de Migração de VMs
# -----------------------------------------
def get_best_host_in_rack(rack_id):
    """
    Encontra o hostname com menor nível de CPU num rack
    """
    if rack_id not in state_cpus or not state_cpus[rack_id]:
        return None
    
    vms_no_rack = state_cpus[rack_id]
    host_com_menor_cpu = min(vms_no_rack.items(), key=lambda x: x[1])
    return host_com_menor_cpu[0]  # Retorna o hostname

def find_migration_target(rack_origem):
    """
    Encontra o melhor rack destino para migração de VMs
    Prioridade: menor carga de CPU, depois menor temperatura
    
    Critérios de benefício:
    - Rack destino deve ter < RACK_CRITICO de CPU (segurança)
    - Deve ter pelo menos 20% menos CPU que o rack origem 
    """
    # Obter dados do rack de origem
    cpu_origem = get_media_cpu_rack(rack_origem)
    temp_origem = state_temperatures.get(rack_origem, 0)
    
    DIFERENCA_CPU_MINIMA = cpu_origem * 0.20  
    
    rack_destino = None
    menor_carga = 100.0
    menor_temp = float('inf')
    
    for rack_id in state_temperatures:
        if rack_id == rack_origem:
            continue
        
        temp_rack = state_temperatures.get(rack_id, 0)
        media_cpu = get_media_cpu_rack(rack_id)
        
        # Verificar se rack é viável para receber a VM
        if media_cpu >= RACK_CRITICO:
            continue  # Rack já está crítico
        
        # Verificar se há benefício suficiente
        economia_cpu = cpu_origem - media_cpu
        
        if economia_cpu < DIFERENCA_CPU_MINIMA:
            continue  # Não há benefício suficiente
        
        # Seleccionar o rack com menor carga (prioridade) e menor temperatura 
        if media_cpu < menor_carga or (media_cpu == menor_carga and temp_rack < menor_temp):
            rack_destino = rack_id
            menor_carga = media_cpu
            menor_temp = temp_rack
    
    return rack_destino

def migrate_vm(vm_hostname, destination_hostname):
    """
    Migra uma VM para um node de destino no Proxmox
    Credenciais lidas do .env (PROXMOX_USER, PROXMOX_PASSWORD, PROXMOX_HOST)
    """
    print(f"[MIGRAÇÃO] Iniciando migração de {vm_hostname} para {destination_hostname}...")
    PROXMOX_USER = os.getenv("PROXMOX_USER")
    PROXMOX_PASSWORD = os.getenv("PROXMOX_PASSWORD")
    PROXMOX_HOST = os.getenv("PROXMOX_HOST", "192.168.33.128")
    
    if not PROXMOX_USER or not PROXMOX_PASSWORD:
        print("[MIGRAÇÃO] Credenciais de Proxmox não configuradas no .env")
        return
    
    try:
        proxmox = ProxmoxAPI(PROXMOX_HOST, user=PROXMOX_USER, password=PROXMOX_PASSWORD, verify_ssl=False)

        vm_id = None
        for node in proxmox.nodes.get():
            node_name = node['node']
            vms = proxmox.nodes(node_name).qemu.get()
            for vm in vms:
                if vm['name'] == vm_hostname:
                    vm_id = vm['vmid']
                    break
            if vm_id:
                break
        
        if not vm_id:
            print(f"[MIGRAÇÃO] VM {vm_hostname} não encontrada.")
            return

        proxmox.nodes(node_name).qemu(vm_id).migrate.post(target=destination_hostname, online=1)
        print(f"[MIGRAÇÃO] Migração de {vm_hostname} para {destination_hostname} iniciada com sucesso.")
    
    except Exception as e:
        print(f"[MIGRAÇÃO] Falha ao iniciar migração: {e}")


def migrar(vm_hostname, rack_origem):
    """
    Encontra o melhor rack destino e o host com menor CPU
    Depois migra a VM para lá
    """
    # 1. Encontrar o melhor rack destino
    rack_destino = find_migration_target(rack_origem)
    if not rack_destino:
        print(f"[MIGRAÇÃO] Nenhum rack válido encontrado para migrar {vm_hostname}")
        return False
    
    print(f"[MIGRAÇÃO] Rack destino selecionado: {rack_destino}")
    
    # 2. Encontrar o host com menor CPU nesse rack
    destination_hostname = get_best_host_in_rack(rack_destino)
    if not destination_hostname:
        print(f"[MIGRAÇÃO] Nenhum host disponível no rack {rack_destino}")
        return False
    
    cpu_destino = state_cpus[rack_destino].get(destination_hostname, 0)
    print(f"[MIGRAÇÃO] Host selecionado: {destination_hostname} (CPU: {cpu_destino:.1f}%)")
    
    # 3. Executar a migração
    migrate_vm(vm_hostname, destination_hostname)
    return True