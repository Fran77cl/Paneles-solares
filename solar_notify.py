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
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
        f"&hourly=shortwave_radiation"
        f"&daily=weather_code,precipitation_sum"
        f"&timezone=America%2FSantiago&forecast_days=1"
    )
    res = requests.get(url).json()
    
    # 1. Detección meteorológica adversa
    daily = res.get("daily", {})
    wmo_code = daily.get("weather_code", [0])[0]
    lluvia_mm = daily.get("precipitation_sum", [0.0])[0]
    
    alerta_clima = None
    if wmo_code in [95, 96, 99]:
        alerta_clima = f"⚡ Tormenta eléctrica ({lluvia_mm} mm proyectados)"
    elif wmo_code in [51, 53, 55, 61, 63, 65, 80, 81, 82] or lluvia_mm >= 1.0:
        alerta_clima = f"🌧️ Lluvia estimada: {lluvia_mm} mm"
    elif wmo_code == 3:
        alerta_clima = "☁️ Cielo completamente nublado / baja radiación"

    # 2. Curva solar hora a hora
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
    
    return round(total_kwh, 1), ventana, alerta_clima

def generar_mensaje(kwh_dia, ventana, alerta_clima):
    aviso_texto = f"⚠️ *Alerta Clima:* {alerta_clima}\n" if alerta_clima else ""
    
    texto_fallback = (
        f"{aviso_texto}"
        f"• Generación estimada: {kwh_dia} kWh\n"
        f"• Ventana óptima (>3 kW): {ventana}\n"
        f"• Sugerencia: " + (
            "Evitar grandes consumos diurnos (dependerá de la red)." 
            if alerta_clima else 
            "Aprovechar ventana para climatización, lavado o recarga EV."
        )
    )
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Eres un asistente de energía solar para una casa en Pudahuel, Santiago.
        Datos proyectados para hoy:
        - Condición climática especial: {alerta_clima if alerta_clima else 'Despejado / Buen tiempo'}
        - Generación solar estimada: {kwh_dia} kWh
        - Ventana óptima (>3 kW solar): {ventana}

        Redacta una notificación para Telegram muy concisa, en español, de máximo 3 o 4 líneas.
        Si hay lluvia o nubosidad densa, incluye una advertencia al inicio avisando que la generación será baja y recomendando cuidar los consumos en horario punta o postergar cargas pesadas. Si el tiempo es óptimo, recomienda la ventana para lavado o carga EV. Usa viñetas breves.
        """
        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return f"{aviso_texto}{res.text.strip()}"
    except Exception as e:
        print(f"Aviso API: {e}. Usando fallback.")
        return texto_fallback

def enviar_telegram(texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"☀️ *Pronóstico Solar Pudahuel*\n\n{texto}",
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

if __name__ == "__main__":
    kwh, ventana, alerta = obtener_pronostico()
    mensaje = generar_mensaje(kwh, ventana, alerta)
    enviar_telegram(mensaje)
    
