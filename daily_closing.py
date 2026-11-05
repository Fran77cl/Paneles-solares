import os
import requests
from google import genai

LAT = -33.4402
LON = -70.7828
CAPACIDAD_KWP = 6.96   # 12 paneles de 580W
PERFORMANCE_RATIO = 0.82

# Tarifas THRP-T6 Enel Distribución
PRECIO_DIURNO = 291.0   # $/kWh base diurno
PRECIO_INYECCION = 72.0 # $/kWh valorización excedentes Net Billing

# Consumo base estimado de tu casa durante horas de sol (kWh)
# ~0.5 kW promedio entre 08:00 y 19:00 hrs (~5.5 kWh)
CONSUMO_SOLAR_ESTIMADO = 5.5

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def obtener_generacion_dia():
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
        f"&hourly=shortwave_radiation"
        f"&timezone=America%2FSantiago&forecast_days=1"
    )
    res = requests.get(url).json()
    radiacion = res["hourly"]["shortwave_radiation"]
    
    # Sumar kWh generados en todas las horas del día
    total_kwh = sum((rad / 1000.0) * CAPACIDAD_KWP * PERFORMANCE_RATIO for rad in radiacion)
    total_kwh = round(total_kwh, 1)
    
    # Estimación de balance y valorización
    autoconsumo_kwh = min(total_kwh, CONSUMO_SOLAR_ESTIMADO)
    inyeccion_kwh = max(0.0, round(total_kwh - autoconsumo_kwh, 1))
    
    ahorro_autoconsumo = int(autoconsumo_kwh * PRECIO_DIURNO)
    abono_inyeccion = int(inyeccion_kwh * PRECIO_INYECCION)
    beneficio_total = ahorro_autoconsumo + abono_inyeccion
    
    return total_kwh, autoconsumo_kwh, inyeccion_kwh, ahorro_autoconsumo, abono_inyeccion, beneficio_total

def redactar_cierre_ia(total_kwh, auto_kwh, iny_kwh, ahorro_auto, abono_iny, total_pesos):
    texto_fallback = (
        f"• Generación total: {total_kwh} kWh\n"
        f"• Autoconsumo estimado: ~{auto_kwh} kWh (${ahorro_auto:,} CLP ahorrados)\n"
        f"• Inyección a red: ~{iny_kwh} kWh (${abono_iny:,} CLP a favor)\n"
        f"• Beneficio económico hoy: ~${total_pesos:,} CLP"
    ).replace(",", ".")

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Eres el asistente de gestión energética para una casa en Pudahuel, Santiago.
        Datos de cierre solar de hoy:
        - Producción solar total: {total_kwh} kWh
        - Autoconsumo directo: ~{auto_kwh} kWh (ahorro evitado de comprar a la red: ${ahorro_auto} CLP)
        - Excedentes inyectados a red: ~{iny_kwh} kWh (valorizados a Enel: ${abono_iny} CLP)
        - Beneficio económico acumulado del día: ${total_pesos} CLP

        Escribe un mensaje de cierre nocturno para Telegram muy directo al grano, en español, de 3 o 4 líneas.
        Usa viñetas breves con números formateados. Incluye una frase final breve sobre el balance del día.
        """
        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return res.text.strip()
    except Exception as e:
        print(f"Aviso API: {e}. Usando texto base.")
        return texto_fallback

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"📊 *Cierre Solar Diario - Pudahuel*\n\n{mensaje}",
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

if __name__ == "__main__":
    tot, aut, iny, ah_aut, ab_iny, tot_p = obtener_generacion_dia()
    resumen = redactar_cierre_ia(tot, aut, iny, ah_aut, ab_iny, tot_p)
    enviar_telegram(resumen)
  
