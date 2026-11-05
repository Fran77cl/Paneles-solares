import os
import requests
from google import genai

LAT = -33.4402
LON = -70.7828
CAPACIDAD_KWP = 6.96   # 12 paneles de 580W
PERFORMANCE_RATIO = 0.82

# Parámetros tarifarios THRP-T6 (Enel)
TARIFA_VALLE = 212.26   # $/kWh nocturno (00:00 - 08:00)
TARIFA_DIA = 291.00     # $/kWh base diurno
TARIFA_PUNTA = 370.26   # $/kWh punta (18:00 - 22:00)

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
    
    # 1. Detección meteorológica (filtrando lloviznas irrelevantes < 1.5 mm)
    daily = res.get("daily", {})
    wmo_code = daily.get("weather_code", [0])[0]
    lluvia_mm = daily.get("precipitation_sum", [0.0])[0]
    
    alerta_clima = None
    if wmo_code in [95, 96, 99]:
        alerta_clima = f"⚡ Tormenta eléctrica ({lluvia_mm} mm proyectados)"
    elif (wmo_code in [61, 63, 65, 81, 82] or lluvia_mm >= 1.5):
        alerta_clima = f"🌧️ Lluvia estimada: {lluvia_mm} mm"
    elif wmo_code == 3 and lluvia_mm >= 1.0:
        alerta_clima = "☁️ Cielo completamente cubierto"

    # 2. Estimación solar y horas peak
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
    duracion_peak = len(horas_peak)
    
    if duracion_peak > 0:
        ventana = f"{min(horas_peak)}:00 a {max(horas_peak)+1}:00 hrs"
    else:
        ventana = "Sin ventana sobre 3 kW"
        
    # 3. Lógica técnica de recomendación EV (Cargador 7 kW)
    if duracion_peak >= 5 and total_kwh >= 35:
        recomendacion_ev = (
            f"🚗 *Recarga EV Solar:* Conviene enchufar entre las {min(horas_peak)+1}:00 y {max(horas_peak)-1}:00 hrs. "
            f"Absorberás ~15-20 kWh a $0 CLP directamente del sol."
        )
    elif duracion_peak >= 3:
        recomendacion_ev = (
            f"🚗 *Recarga EV Parcial:* Ventana solar moderada ({ventana}). Si requieres carga completa, "
            f"es preferible programar el cargador para horario Valle nocturno (00:00 a 08:00 a ${TARIFA_VALLE:.0f}/kWh)."
        )
    else:
        recomendacion_ev = (
            f"🚗 *Recarga EV Nocturna:* Baja radiación diurna. No cargar de día ($291/kWh) ni en punta ($370/kWh). "
            f"Cargar exclusivamente en bloque nocturno 00:00 - 08:00 hrs ($212/kWh)."
        )

    return round(total_kwh, 1), ventana, alerta_clima, recomendacion_ev

def generar_mensaje(kwh_dia, ventana, alerta_clima, recomendacion_ev):
    aviso_texto = f"⚠️ *Alerta Clima:* {alerta_clima}\n" if alerta_clima else ""
    
    texto_fallback = (
        f"{aviso_texto}"
        f"• Generación estimada: {kwh_dia} kWh\n"
        f"• Ventana óptima (>3 kW): {ventana}\n"
        f"• {recomendacion_ev}"
    )
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Eres un asistente de energía solar y movilidad eléctrica para una casa en Pudahuel, Santiago con tarifa THRP-T6.
        Datos proyectados para hoy:
        - Condición climática: {alerta_clima if alerta_clima else 'Despejado / Buen tiempo'}
        - Generación solar estimada: {kwh_dia} kWh
        - Ventana solar óptima (>3 kW): {ventana}
        - Directriz para auto eléctrico: {recomendacion_ev}

        Redacta una notificación para Telegram muy concisa, profesional y directa al grano, de máximo 4 líneas.
        Usa viñetas breves:
        1. Producción solar estimada.
        2. Ventana horaria peak.
        3. Recomendación de carga EV clara y con horas exactas.
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
        "text": f"☀️ *Pronóstico Solar & Carga EV - Pudahuel*\n\n{texto}",
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

if __name__ == "__main__":
    kwh, ventana, alerta, rec_ev = obtener_pronostico()
    mensaje = generar_mensaje(kwh, ventana, alerta, rec_ev)
    enviar_telegram(mensaje)
    
