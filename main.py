"""
Resumen diario de mercado -> WhatsApp (via Twilio)

Datos:
  - Indices: yfinance (sin clave)
  - Sentimiento de mercado: indice Fear & Greed de CNN (sin clave, no oficial)
  - Titulares: feeds RSS financieros (sin clave)

La UNICA credencial necesaria es la de Twilio. Todo lo demas es sin registro.
Todas las claves se leen de variables de entorno (Secrets de Replit), nunca van en el codigo.
"""

import os
import datetime

import yfinance as yf
import feedparser
import requests
from twilio.rest import Client

# Sentimiento de titulares (offline, sin clave). Si no esta instalado, se omite.
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _vader = SentimentIntensityAnalyzer()
except Exception:
    _vader = None


# ------------------- Configuracion (desde Secrets) -------------------
TWILIO_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
# Numero del sandbox de Twilio. Confirmalo en tu consola (suele ser este).
TWILIO_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
# Uno o varios destinatarios en formato internacional, separados por coma.
# Ej: +34600111222,+34600333444
RECIPIENTS = [n.strip() for n in os.environ["WHATSAPP_TO"].split(",") if n.strip()]

# Indices a seguir: (etiqueta, simbolo de Yahoo Finance). Edita a tu gusto.
INDICES = [
    ("S&P 500", "^GSPC"),
    ("Nasdaq", "^IXIC"),
    ("Dow Jones", "^DJI"),
    ("IBEX 35", "^IBEX"),
    ("Euro Stoxx 50", "^STOXX50E"),
]

# Feeds de noticias (sin clave). Se usa el primero que responda.
NEWS_FEEDS = [
    "https://www.cnbc.com/id/10000664/device/rss/rss.html",  # CNBC Markets
    "http://feeds.marketwatch.com/marketwatch/topstories/",   # MarketWatch
]
MAX_HEADLINES = 5


def get_indices():
    lines = []
    for label, symbol in INDICES:
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="2d")
            if len(hist) >= 2:
                prev = float(hist["Close"].iloc[-2])
                last = float(hist["Close"].iloc[-1])
            else:
                info = t.fast_info
                prev = float(info["previous_close"])
                last = float(info["last_price"])
            pct = (last - prev) / prev * 100
            arrow = "🟢▲" if pct >= 0 else "🔴▼"
            lines.append(f"{arrow} {label}: {last:,.0f} ({pct:+.2f}%)")
        except Exception:
            lines.append(f"• {label}: s/d")
    return lines


def get_fear_greed():
    """Indice Fear & Greed de CNN. Sin clave, endpoint no oficial."""
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        d = r.json()["fear_and_greed"]
        score = round(float(d["score"]))
        label = str(d["rating"]).capitalize()
        return f"😨↔️🤑 Fear & Greed: {score}/100 ({label})"
    except Exception:
        return None


def _tag(text):
    """Etiqueta de sentimiento para un titular (verde/amarillo/rojo)."""
    if not _vader:
        return "•"
    score = _vader.polarity_scores(text)["compound"]
    if score >= 0.25:
        return "🟢"
    if score <= -0.25:
        return "🔴"
    return "🟡"


def get_news():
    for feed in NEWS_FEEDS:
        try:
            parsed = feedparser.parse(feed)
            if parsed.entries:
                return [f"{_tag(e.title)} {e.title.strip()}"
                        for e in parsed.entries[:MAX_HEADLINES]]
        except Exception:
            continue
    return ["• Sin titulares disponibles ahora."]


def build_message():
    today = datetime.datetime.now().strftime("%d/%m/%Y")
    parts = [f"📊 *Resumen de mercado* — {today}", ""]

    parts.append("*Indices*")
    parts += get_indices()
    parts.append("")

    fg = get_fear_greed()
    if fg:
        parts.append("*Sentimiento de mercado*")
        parts.append(fg)
        parts.append("")

    parts.append("*Titulares*")
    parts += get_news()

    msg = "\n".join(parts)
    # Twilio/WhatsApp: limite de 1600 caracteres por mensaje.
    return msg[:1550]


def send(msg):
    client = Client(TWILIO_SID, TWILIO_TOKEN)
    for number in RECIPIENTS:
        try:
            client.messages.create(from_=TWILIO_FROM, to=f"whatsapp:{number}", body=msg)
            print(f"Enviado a {number}")
        except Exception as e:
            print(f"No se pudo enviar a {number}: {e}")
            print("Si es por la ventana de 24h, responde cualquier mensaje "
                  "al bot del sandbox y vuelve a ejecutarlo.")


def run_digest():
    msg = build_message()
    print(msg)          # util para ver el resultado en los logs
    send(msg)


if __name__ == "__main__":
    run_digest()
