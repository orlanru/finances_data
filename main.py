"""
Resumen diario de mercado -> Telegram

Datos:
  - Indices: yfinance (sin clave)
  - Sentimiento de mercado: indice Fear & Greed de CNN (sin clave, no oficial)
  - Titulares: feeds RSS financieros (sin clave)

La UNICA credencial necesaria es el token del bot de Telegram. Todo lo demas es sin registro.
Todas las claves se leen de variables de entorno (Secrets), nunca van en el codigo.
"""

import os
import math
import datetime

import yfinance as yf
import feedparser
import requests

# Sentimiento de titulares (offline, sin clave). Si no esta instalado, se omite.
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _vader = SentimentIntensityAnalyzer()
except Exception:
    _vader = None


# ------------------- Configuracion (desde Secrets) -------------------
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
# Uno o varios chat_id de Telegram, separados por coma.
CHAT_IDS = [c.strip() for c in os.environ["TELEGRAM_CHAT_ID"].split(",") if c.strip()]

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
            prev = last = math.nan
            hist = t.history(period="2d")
            if len(hist) >= 2:
                prev = float(hist["Close"].iloc[-2])
                last = float(hist["Close"].iloc[-1])
            if math.isnan(prev) or math.isnan(last):
                # yfinance a veces devuelve closes vacios/NaN; fast_info es el respaldo.
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
        # CNN bloquea con 418 las peticiones sin pinta de navegador real.
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.cnn.com/markets/fear-and-greed",
        }
        r = requests.get(url, headers=headers, timeout=15)
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
    # Telegram: limite de 4096 caracteres por mensaje.
    return msg[:4000]


def send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        try:
            r = requests.post(
                url,
                data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=15,
            )
            r.raise_for_status()
            print(f"Enviado a {chat_id}")
        except Exception as e:
            print(f"No se pudo enviar a {chat_id}: {e}")


def run_digest():
    msg = build_message()
    print(msg)          # util para ver el resultado en los logs
    send(msg)


if __name__ == "__main__":
    run_digest()
