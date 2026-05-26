#include <WiFi.h>
#include <PubSubClient.h>
#include "cred.h"

// ==========================================
// Topic Configs
// ==========================================
const char* topico_out = "rack/temperatura";      
const char* topico_in = "rack/controlo";    
const char* rackId = "1";

// ==========================================
// Hardware Configs (Sensor e Ventoinha)
// ==========================================
#define ADC_VREF_mV    3300.0 // em milivolts
#define ADC_RESOLUTION 4096.0
#define PIN_LM35       34 // Pino GIOP34 (ADC1) ligado ao LM35

#define PIN_FAN_1      32 // Pino 1 de controlo da ventoinha (PWM)
#define PIN_FAN_2      33 // Pino 2 de controlo da ventoinha

// Controlo de Ventoinhas - Incremento Gradual
float velocidade_atual = 0.0;        // Velocidade atual (0-255)
float velocidade_alvo = 0.0;         // Velocidade alvo (0-255)
unsigned long ultimo_update_fan = 0;
const unsigned long INTERVALO_UPDATE_FAN = 500; // Atualizar velocidade a cada 500ms

const float INCREMENTO_UP = 12.75;   // ~30 unidades por 2s (150/255 * 30 / 4 = 12.75 por 500ms)
const float INCREMENTO_DOWN = 4.25;  // ~10 unidades por 2s (150/255 * 5 / 4 = 4.25 por 500ms)

// Timers com millis()
unsigned long ultimoEnvio = 0;
const unsigned long INTERVALO_ENVIO = 5000; // Envia e lê a cada 5 segundos

WiFiClient espClient;
PubSubClient client(espClient);


void setup_wifi(){
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Connecting to broker MQTT...");
    String clientId = "ESP32-LM35-";
    clientId += String(random(0, 0xffff), HEX);
    
    if (client.connect(clientId.c_str())) {
      Serial.println("Connected!");
      client.subscribe(topico_in);
    } else {
      Serial.print("Failed, state=");
      Serial.print(client.state());
      delay(5000);
    }
  }
}

// ==========================================
// Controlo de Ventoinhas - Incremento Gradual
// ==========================================
void atualizar_velocidade_ventoinha() {
  unsigned long tempoAtual = millis();
  
  // Atualizar apenas a cada INTERVALO_UPDATE_FAN
  if (tempoAtual - ultimo_update_fan < INTERVALO_UPDATE_FAN) {
    return;
  }
  ultimo_update_fan = tempoAtual;
  
  // Lógica de incremento/decremento gradual
  if (velocidade_atual < velocidade_alvo) {
    // Aumentar gradualmente
    velocidade_atual = min(velocidade_atual + INCREMENTO_UP, velocidade_alvo);
    Serial.print("[FAN] Aumentando: ");
    Serial.println(velocidade_atual);
  } 
  else if (velocidade_atual > velocidade_alvo) {
    // Diminuir gradualmente
    velocidade_atual = max(velocidade_atual - INCREMENTO_DOWN, velocidade_alvo);
    Serial.print("[FAN] Diminuindo: ");
    Serial.println(velocidade_atual);
  }
  
  // Aplicar PWM
  int pwm_value = (int)velocidade_atual;
  analogWrite(PIN_FAN_1, pwm_value);
  digitalWrite(PIN_FAN_2, LOW);
}

void callback(char* topic, byte* payload, unsigned int length) {
  String mensagem = "";
  for (int i = 0; i < length; i++) {
    mensagem += (char)payload[i];
  }
  
  Serial.print("==== COMANDO RECEBIDO EM ");
  Serial.print(topic);
  Serial.println(" ====");
  Serial.print("Mensagem: ");
  Serial.println(mensagem);

  // Parsing: "INCREASE_TO:150" ou "DECREASE_TO:0"
  if (mensagem.startsWith("INCREASE_TO:")) {
    velocidade_alvo = mensagem.substring(12).toFloat();
    velocidade_alvo = constrain(velocidade_alvo, 0, 255);
    Serial.print("-> AÇÃO: Aumentar para ");
    Serial.println(velocidade_alvo);
  } 
  else if (mensagem.startsWith("DECREASE_TO:")) {
    velocidade_alvo = mensagem.substring(12).toFloat();
    velocidade_alvo = constrain(velocidade_alvo, 0, 255);
    Serial.print("-> AÇÃO: Diminuir para ");
    Serial.println(velocidade_alvo);
  }
  Serial.println("=============================================");
}

void setup() {
  Serial.begin(9600);

  // Inicializa os pinos da ventoinha
  pinMode(PIN_FAN_1, OUTPUT);
  pinMode(PIN_FAN_2, OUTPUT);
  
  // Garante que a ventoinha começa desligada
  digitalWrite(PIN_FAN_1, LOW);
  digitalWrite(PIN_FAN_2, LOW);

  setup_wifi();
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}


void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // Atualizar velocidade da ventoinha (incremento gradual)
  atualizar_velocidade_ventoinha();

  unsigned long tempoAtual = millis();

  // Rotina simplificada: lê e envia estritamente a cada 5 segundos
  if (tempoAtual - ultimoEnvio >= INTERVALO_ENVIO) {
    ultimoEnvio = tempoAtual;

    // 1. Leitura do Sensor
    int adcVal = analogRead(PIN_LM35);
    float milliVolt = adcVal * (ADC_VREF_mV / ADC_RESOLUTION);
    float tempC = milliVolt / 10.0;
    
    // 2. Print de Monitorização Local
    Serial.print("Temperature: ");
    Serial.print(tempC);
    Serial.println("°C");

    // 3. Envio dos dados via MQTT
    String message = "{\"rack_id\": \"" + String(rackId) + "\", \"temperatura\": " + String(tempC) + "}";
    
    Serial.println("A enviar temperatura para o Raspberry Pi...");
    client.publish(topico_out, message.c_str());
  }
}