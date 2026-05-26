#!/usr/bin/env python3
"""
Script de Teste MQTT - Simula envio de mensagens de temperatura do ESP32 para o Rasp
Testa o tópico: rack/temperatura
"""

import paho.mqtt.client as mqtt
import json
import time
import sys
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC_TEMP = os.getenv("MQTT_TOPIC_TEMP", "rack/temperatura")

def on_connect(client, userdata, flags, rc, properties=None):
    """Callback chamado quando conecta ao broker"""
    if rc == 0:
        print(f"[✓] Conectado ao broker MQTT: {MQTT_BROKER}:{MQTT_PORT}")
    else:
        print(f"[✗] Falha ao conectar. Código: {rc}")
        sys.exit(1)

def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
    """Callback chamado quando desconecta"""
    if reason_code == 0:
        print("[✓] Desconectado do broker MQTT")
    else:
        print(f"[✗] Desconexão inesperada. Código: {reason_code}")

def send_temperatura(client, rack_id, temperatura):
    """Envia mensagem de temperatura"""
    payload = json.dumps({
        "rack_id": rack_id,
        "temperatura": temperatura
    })
    client.publish(MQTT_TOPIC_TEMP, payload)
    print(f"[TEMP] {MQTT_TOPIC_TEMP} - Rack: {rack_id}, Temp: {temperatura}°C")

def test_basic():
    """Teste básico - envia uma mensagem de temperatura"""
    print("\n" + "="*60)
    print("TESTE: Envio de Mensagem de Temperatura")
    print("="*60)
    
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "TestClient_Basic")
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    
    time.sleep(1)  # Esperar conexão
    
    # Enviar mensagem de temperatura
    send_temperatura(client, "rack1", 22.5)
    
    time.sleep(1)
    client.disconnect()
    client.loop_stop()


if __name__ == "__main__":
    test_basic()
