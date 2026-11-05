import os
import requests
from google import genai

LAT = -33.4402
LON = -70.7828
CAPACIDAD_KWP = 6.96   # 12 paneles de 580W
PERFORMANCE_RATIO = 0.82

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def obtener_pronostico():
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&hourly=shortwave_radiation&timezone=America%2FSantiago&forecast_days=1"
    res = requests.get(url).json()
    
    horas = res["hourly"]["time"]
    radiacion = res["hourly"]["shortwave_radiation"]
    
    generacion_por_hora = {}
    horas_peak = []
    
    for h_str, rad in zip(horas, radiacion):
        hora = int(h_str.split("T")[1].split(":")[0])
        kw = (rad / 1000.0) * CAPACIDAD_KWP * PERFORMANCE_RATIO
        generacion_por_hora[hora] = kw
        if kw >= 3.0:
            horas_peak.append(hora)
            
    total_kwh = sum(generacion_por_hora.values())
    ventana = f"{min(horas_peak)}:00 a {max(horas_peak)+1}:00 hrs" if horas_peak else "Sin ventana sobre 3 kW"
    return round(total_kwh, 1), ventana

def generar_mensaje(kwh_dia, ventana):
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
    Eres un asistente de energía solar para una casa en Pudahuel, Santiago.
    Datos proyectados para hoy:
    - Generación estimada: {kwh_dia} kWh
    - Ventana óptima (>3 kW solar): {ventana}

    Redacta una notificación para Telegram muy directa al grano, en español, de máximo 3 o 4 líneas.
    Indica la producción estimada y recomienda aprovechar la ventana óptima para consumos intensivos (lavado, climatización o recarga EV). Usa viñetas breves.
    """
    res = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt
    )
    return res.text.strip()

def enviar_telegram(texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"☀️ *Pronóstico Solar Pudahuel*\n\n{texto}",
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

if __name__ == "__main__":
    kwh, ventana = obtener_pronostico()
    mensaje = generar_mensaje(kwh, ventana)
    enviar_telegram(mensaje)
  
