import os
import requests
from datetime import datetime, timezone, timedelta

# Variables desde Secrets del repositorio
KIOSK_KEY = os.environ.get("KIOSK_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

URL_HUAWEI = "https://la5.fusionsolar.huawei.com/rest/pvms/web/kiosk/v1/station/kiosk-data"

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    try:
        resp = requests.post(url, json=data, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"Error Telegram: {e}")
        return False

def obtener_telemetria():
    params = {"kk": KIOSK_KEY}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        resp = requests.post(URL_HUAWEI, params=params, json={}, headers=headers, timeout=15)
        if resp.status_code == 200:
            kpi = resp.json().get("data", {}).get("realKpi", {})
            potencia_kw = float(kpi.get("realTimePower", 0.0))
            kwh_hoy = float(kpi.get("dayPower", 0.0))
            return potencia_kw, kwh_hoy
    except Exception as e:
        print(f"Error consultando FusionSolar: {e}")
    return None, None

def evaluar_y_notificar():
    # Hora de Santiago de Chile (UTC-3)
    tz_chile = timezone(timedelta(hours=-3))
    ahora = datetime.now(tz_chile)
    hora_dec = ahora.hour + ahora.minute / 60.0

    print(f"Ejecutando evaluación: {ahora.strftime('%H:%M:%S')} (Hora Chile)")

    potencia_kw, kwh_hoy = obtener_telemetria()
    if potencia_kw is None:
        print("No se pudo obtener datos del Kiosk.")
        return

    print(f"Telemetría obtenida: Potencia = {potencia_kw:.2f} kW | Acumulado = {kwh_hoy:.2f} kWh")

    # Regla 1: Pico Solar (11:30 - 15:30)
    if 11.5 <= hora_dec <= 15.5 and potencia_kw >= 5.0:
        enviar_telegram(
            f"☀️ *Pico Solar Activo ({potencia_kw:.2f} kW)*\n"
            f"Acumulado hoy: {kwh_hoy:.1f} kWh.\n\n"
            f"👉 *Momento óptimo:* Sube el cargador a *18.00 A* (si la casa está en consumo basal)."
        )

    # Regla 2: Descenso de Tarde (15:30 - 16:30)
    elif 15.5 < hora_dec <= 16.5 and potencia_kw < 4.2:
        enviar_telegram(
            f"⚠️ *Descenso de Tarde ({potencia_kw:.2f} kW)*\n"
            f"El string Oriente perdió radiación.\n\n"
            f"👉 *Acción sugerida:* Baja el cargador a *12.00 A o 14.00 A* para evitar comprar a la red."
        )

    # Regla 3: Cierre Solar (16:30 - 17:15)
    elif 16.5 < hora_dec <= 17.25 and potencia_kw < 2.8:
        enviar_telegram(
            f"🔻 *Cierre Solar ({potencia_kw:.2f} kW)*\n\n"
            f"👉 *Acción sugerida:* Baja el cargador al mínimo técnico (*6.00 A*)."
        )

    # Regla 4: Fin de Generación (> 17:15)
    elif hora_dec > 17.25 and potencia_kw < 1.5:
        enviar_telegram(
            f"🛑 *Fin de Ventana Solar ({potencia_kw:.2f} kW)*\n"
            f"Generación total hoy: {kwh_hoy:.2f} kWh.\n\n"
            f"👉 *Detén la carga del auto* para no comprar energía diurna a la red."
        )

if __name__ == "__main__":
    evaluar_y_notificar()
  
