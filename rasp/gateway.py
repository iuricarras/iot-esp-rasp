import os
import secrets
import base64
import requests
import string
import time

# ----------------------
# Funções Auxiliares
# ----------------------
def save_to_env(key, value):
    """Guarda uma variável no arquivo .env."""
    env_file = '.env'
    
    # Verificar se a chave já existe no arquivo
    try:
        with open(env_file, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []
    
    # Procurar se a chave já existe
    key_found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            key_found = True
            break
    
    # Se não existe, adicionar ao fim
    if not key_found:
        if lines and not lines[-1].endswith('\n'):
            lines.append('\n')
        lines.append(f"{key}={value}\n")
    
    # Guardar no arquivo
    with open(env_file, 'w') as f:
        f.writelines(lines)

# ----------------------
# ID do Gateway 
# ----------------------
def load_or_generate_gateway_id(backend_api_url):
    """Carrega GATEWAY_ID do .env ou gera um novo aleatoriamente.
    Verifica se o ID gerado já existe no backend."""
    gateway_id = os.getenv("GATEWAY_ID")
    
    if gateway_id:
        return gateway_id
    
    # Gerar ID aleatório que não exista no backend
    while True:
        random_id = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(20))
        
        # Verificar se ID já existe no backend
        try:
            response = requests.head(
                f"{backend_api_url}/gateway/{random_id}",
                timeout=5
            )
            
            if response.status_code == 404:
                # Gateway não existe, pode usar
                break
            elif response.status_code == 200:
                # Gateway já existe, gerar outro
                print(f"[AVISO] ID {random_id} já existe. Gerando novo...")
                continue
            else:
                # Outro status, usar mesmo assim
                break
                
        except requests.exceptions.RequestException:
            # Erro de conexão, usar este ID
            print(f"[AVISO] Não conseguiu verificar ID no backend. Usando mesmo assim.")
            break
    
    # Guardar no .env
    save_to_env("GATEWAY_ID", random_id)
    
    return random_id

# ----------------------
# Função de Registro
# ----------------------
def register_gateway(gateway_id, backend_api_url):
    """Registra um novo gateway no backend."""
    try:
        random_bytes = secrets.token_bytes(12)
        link_code = base64.b64encode(random_bytes).decode('utf-8')

        gateway_data = {
            "id": gateway_id,
            "linkCode": link_code,
            "linked": False,
            "userID": None
        }
        
        response = requests.post(
            f"{backend_api_url}/gateways",
            json=gateway_data,
            timeout=5
        )
        
        if response.status_code == 201:
            # Guardar linkCode no .env
            save_to_env("LINK_CODE", link_code)
            
            print(f"[GATEWAY] Gateway registado com sucesso!")
            print(f"[GATEWAY] ID: {gateway_id}")
            print(f"\n[AÇÃO REQUERIDA] Por favor, vá à sua aplicação e use o Link Code abaixo para ligar este gateway:")
            print(f"[GATEWAY] Link Code: {link_code}\n")
            return link_code
        else:
            print(f"[ERRO] Falha ao registar gateway: {response.status_code}")
            print(f"[ERRO] Resposta: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"[ERRO] Não foi possível conectar ao backend em {backend_api_url}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"[ERRO] Erro ao registar gateway: {e}")
        return None

# ----------------------
# Inicializar Gateway
# ----------------------
def initialize_gateway(gateway_id, backend_api_url):
    """Verifica se gateway existe. Se não, registra novo."""
    try:
        # Verificar se gateway já existe
        link_code = os.getenv("LINK_CODE")
        headers = {}
        if link_code:
            headers['Authorization'] = link_code
        
        response = requests.get(
            f"{backend_api_url}/gateway/{gateway_id}",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            print(f"[GATEWAY] Gateway já registado!")
            return True
        elif response.status_code == 404:
            print(f"[GATEWAY] Gateway novo. Registando...")
            result = register_gateway(gateway_id, backend_api_url)
            return result is not None
        else:
            print(f"[ERRO] Erro ao verificar gateway: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"[ERRO] Falha ao inicializar gateway: {e}")
        return False

def check_gateway_linked(gateway_id, backend_api_url):
    """Verifica se o gateway está linked e retorna dados do gateway.
    Usa linkCode para autenticação."""
    try:
        link_code = os.getenv("LINK_CODE")
        headers = {}
        if link_code:
            headers['Authorization'] = link_code
        
        response = requests.get(
            f"{backend_api_url}/gateway/{gateway_id}",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            gateway_data = response.json().get('gateway', {})
            return gateway_data
        return None
            
    except requests.exceptions.RequestException:
        return None

def wait_for_gateway_linked(gateway_id, backend_api_url, max_wait=300):
    """Aguarda até o gateway ser linked (máximo 5 minutos) e retorna o userID."""
    # Verificar se já está linked
    gateway_data = check_gateway_linked(gateway_id, backend_api_url)
    if gateway_data and gateway_data.get('linked', False):
        print(f"[GATEWAY] Gateway já está associado à conta!")
        return gateway_data.get('userID')
    
    # Se não estiver linked, mostrar mensagem e esperar
    print(f"\n[GATEWAY] À espera que o Gateway seja associado à conta...\n")
    
    elapsed = 0
    check_interval = 10
    
    while elapsed < max_wait:
        gateway_data = check_gateway_linked(gateway_id, backend_api_url)
        if gateway_data and gateway_data.get('linked', False):
            print(f"[GATEWAY] Gateway foi associado com sucesso!")
            return gateway_data.get('userID')
        
        elapsed += check_interval
        time.sleep(check_interval)
    
    print(f"[AVISO] Timeout: Gateway não foi associado. Reinicie.")
    return None
