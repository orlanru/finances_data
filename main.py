"""
Resumen diario de mercado -> Telegram + Dashboard web

Datos:
  - Indices, materias primas, divisas y cripto: yfinance (sin clave)
  - Sentimiento de mercado: indice Fear & Greed de CNN, con desglose por
    subindicador e historico de 1 ano (sin clave, endpoint no oficial)
  - Titulares: feeds RSS financieros (sin clave)

La UNICA credencial necesaria es el token del bot de Telegram. Todo lo demas es sin registro.
Todas las claves se leen de variables de entorno (Secrets), nunca van en el codigo.

Cada ejecucion:
  1. Envia el resumen en texto y un grafico por Telegram.
  2. Regenera docs/index.html, un dashboard web con graficos en SVG
     renderizados en el servidor (sin JS ni CDN externo; se publica solo
     si GitHub Pages esta activado sobre la carpeta docs/).
"""

import os
import io
import html
import math
import datetime

import yfinance as yf
import feedparser
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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

# URL publica del dashboard (GitHub Pages, carpeta docs/). Ajusta si cambias de repo/usuario.
DASHBOARD_URL = "https://orlanru.github.io/finances_data/"

# Activos a seguir, agrupados por categoria: (etiqueta, simbolo de Yahoo Finance).
ASSET_GROUPS = [
    ("Indices", [
        ("S&P 500", "^GSPC"),
        ("Nasdaq", "^IXIC"),
        ("Dow Jones", "^DJI"),
        ("IBEX 35", "^IBEX"),
        ("Euro Stoxx 50", "^STOXX50E"),
    ]),
    ("Volatilidad", [
        ("VIX", "^VIX"),
    ]),
    ("Materias primas", [
        ("Oro", "GC=F"),
        ("Petroleo WTI", "CL=F"),
    ]),
    ("Divisas", [
        ("EUR/USD", "EURUSD=X"),
    ]),
    ("Cripto", [
        ("Bitcoin", "BTC-USD"),
    ]),
]

# Subindicadores que componen el Fear & Greed de CNN.
FEAR_GREED_SUBINDICATORS = [
    ("Momentum del S&P 500", "market_momentum_sp500"),
    ("Fortaleza de precios", "stock_price_strength"),
    ("Amplitud de precios", "stock_price_breadth"),
    ("Opciones put/call", "put_call_options"),
    ("Volatilidad (VIX)", "market_volatility_vix"),
    ("Demanda de bonos basura", "junk_bond_demand"),
    ("Demanda de refugio seguro", "safe_haven_demand"),
]

# Feeds de noticias (sin clave). Se usa el primero que responda.
NEWS_FEEDS = [
    "https://www.cnbc.com/id/10000664/device/rss/rss.html",  # CNBC Markets
    "http://feeds.marketwatch.com/marketwatch/topstories/",   # MarketWatch
]
MAX_HEADLINES = 5

DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")


def fetch_asset(symbol):
    """Devuelve (prev, last, serie de cierres de 1 mes) para un simbolo de Yahoo Finance."""
    t = yf.Ticker(symbol)
    prev = last = math.nan
    closes = []
    try:
        hist = t.history(period="1mo")
        if len(hist) >= 2:
            closes = [float(c) for c in hist["Close"].tolist()]
            prev, last = closes[-2], closes[-1]
    except Exception:
        pass
    if math.isnan(prev) or math.isnan(last):
        try:
            # yfinance a veces devuelve closes vacios/NaN; fast_info es el respaldo.
            info = t.fast_info
            prev = float(info["previous_close"])
            last = float(info["last_price"])
        except Exception:
            pass
    return prev, last, closes


def format_price(value):
    if value >= 1000:
        return f"{value:,.0f}"
    if value >= 10:
        return f"{value:,.2f}"
    return f"{value:,.4f}"


def get_market_data():
    """Obtiene precio actual, variacion y serie de 1 mes de todos los activos seguidos."""
    data = []
    for group_name, assets in ASSET_GROUPS:
        rows = []
        for label, symbol in assets:
            prev, last, closes = fetch_asset(symbol)
            ok = not (math.isnan(prev) or math.isnan(last) or prev == 0)
            pct = (last - prev) / prev * 100 if ok else math.nan
            rows.append({
                "label": label, "symbol": symbol,
                "prev": prev, "last": last, "pct": pct, "closes": closes,
            })
        data.append((group_name, rows))
    return data


def market_lines(data):
    # parse_mode=HTML: escapamos todo el texto dinamico (las etiquetas llevan '&', '/', etc.).
    lines = []
    for group_name, rows in data:
        lines.append(f"<b>{html.escape(group_name)}</b>")
        for r in rows:
            label = html.escape(r["label"])
            if math.isnan(r["last"]) or math.isnan(r["pct"]):
                lines.append(f"• {label}: s/d")
            else:
                arrow = "🟢▲" if r["pct"] >= 0 else "🔴▼"
                lines.append(f"{arrow} {label}: {format_price(r['last'])} ({r['pct']:+.2f}%)")
        lines.append("")
    return lines


def get_fear_greed():
    """Indice Fear & Greed de CNN: score actual, desglose por subindicador e historico de 1 ano."""
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
        payload = r.json()
        d = payload["fear_and_greed"]
        history = [(int(p["x"]), round(float(p["y"]), 1))
                   for p in payload.get("fear_and_greed_historical", {}).get("data", [])]
        subindicators = []
        for label, key in FEAR_GREED_SUBINDICATORS:
            try:
                s = payload[key]
                subindicators.append({
                    "label": label,
                    "score": round(float(s["score"]), 1),
                    "rating": str(s["rating"]).capitalize(),
                })
            except Exception:
                continue
        return {
            "score": round(float(d["score"])),
            "rating": str(d["rating"]).capitalize(),
            "previous_close": round(float(d["previous_close"])),
            "previous_1_week": round(float(d["previous_1_week"])),
            "previous_1_month": round(float(d["previous_1_month"])),
            "previous_1_year": round(float(d["previous_1_year"])),
            "history": history,
            "subindicators": subindicators,
        }
    except Exception:
        return None


def fear_greed_lines(fg):
    if not fg:
        return []
    lines = ["<b>Sentimiento de mercado</b>"]
    lines.append(f"😨↔️🤑 Fear &amp; Greed: {fg['score']}/100 ({html.escape(fg['rating'])})")
    lines.append(
        f"   Ayer {fg['previous_close']} · Semana pasada {fg['previous_1_week']} · "
        f"Mes pasado {fg['previous_1_month']}"
    )
    lines.append("")
    return lines


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
                return [
                    {"title": e.title.strip(), "link": e.get("link", ""), "tag": _tag(e.title)}
                    for e in parsed.entries[:MAX_HEADLINES]
                ]
        except Exception:
            continue
    return []


def news_lines(items):
    if not items:
        return ["• Sin titulares disponibles ahora."]
    # Titulares de feeds externos: se escapan para no romper el parse_mode=HTML.
    return [f"{it['tag']} {html.escape(it['title'])}" for it in items]


def build_message(data, fg, news_items):
    today = datetime.datetime.now().strftime("%d/%m/%Y")
    parts = [f"📊 <b>Resumen de mercado</b> — {today}", ""]
    parts += market_lines(data)
    parts += fear_greed_lines(fg)
    parts.append("<b>Titulares</b>")
    parts += news_lines(news_items)
    parts.append("")
    parts.append(f"🌐 Dashboard completo: {DASHBOARD_URL}")

    msg = "\n".join(parts)
    # Telegram: limite de 4096 caracteres por mensaje.
    return msg[:4000]


def build_chart_png(data):
    """Grafico de evolucion relativa (%) del ultimo mes de todos los activos seguidos."""
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
    colors = ["#4FC3F7", "#81C784", "#FFB74D", "#E57373", "#BA68C8",
              "#4DB6AC", "#FFD54F", "#F06292", "#90A4AE", "#A1887F"]
    color_i = 0
    for _group_name, rows in data:
        for r in rows:
            closes = r["closes"]
            if len(closes) < 2 or not closes[0]:
                continue
            base = closes[0]
            pct_series = [(c - base) / base * 100 for c in closes]
            ax.plot(pct_series, label=r["label"], color=colors[color_i % len(colors)], linewidth=2)
            color_i += 1
    ax.axhline(0, color="white", linewidth=0.6, alpha=0.4)
    ax.set_title("Evolucion del ultimo mes (%)", fontsize=14, color="white")
    ax.set_xlabel("Sesiones")
    ax.set_ylabel("Variacion %")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.3, ncols=2)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        try:
            r = requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            r.raise_for_status()
            print(f"Enviado a {chat_id}")
        except Exception as e:
            print(f"No se pudo enviar a {chat_id}: {e}")


def send_photo(png_bytes, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    for chat_id in CHAT_IDS:
        try:
            r = requests.post(
                url,
                data={"chat_id": chat_id, "caption": caption[:1024]},
                files={"photo": ("grafico.png", png_bytes, "image/png")},
                timeout=30,
            )
            r.raise_for_status()
            print(f"Grafico enviado a {chat_id}")
        except Exception as e:
            print(f"No se pudo enviar el grafico a {chat_id}: {e}")


def _polar(cx, cy, r, theta_deg):
    rad = math.radians(theta_deg)
    return cx + r * math.cos(rad), cy - r * math.sin(rad)


def _svg_sparkline(closes, up, width=200, height=50):
    """Mini grafico de linea en SVG puro (sin JS ni CDN)."""
    lo, hi = min(closes), max(closes)
    rng = (hi - lo) or 1.0
    n = len(closes)
    pts = [
        f"{(i / (n - 1)) * width:.1f},{height - ((c - lo) / rng) * height:.1f}"
        for i, c in enumerate(closes)
    ]
    path = " ".join(pts)
    color = "#4caf50" if up else "#f44336"
    fill = "rgba(76,175,80,0.12)" if up else "rgba(244,67,54,0.12)"
    fill_pts = f"0,{height} {path} {width},{height}"
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
        f'<polyline points="{fill_pts}" fill="{fill}" stroke="none" />'
        f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="2" '
        'stroke-linejoin="round" stroke-linecap="round" />'
        '</svg>'
    )


def _gauge_band_path(cx, cy, r, theta_start, theta_end, steps=10):
    pts = []
    for i in range(steps + 1):
        t = theta_start + (theta_end - theta_start) * i / steps
        x, y = _polar(cx, cy, r, t)
        pts.append(f"{x:.2f},{y:.2f}")
    return "M " + " L ".join(pts)


def _svg_gauge(score, width=280, height=160):
    """Medidor Fear & Greed en SVG puro (sin JS ni CDN)."""
    cx, cy = width / 2, height - 14
    r = min(width / 2, height) - 24
    bands = [
        (0, 25, "#b71c1c"), (25, 45, "#e65100"), (45, 55, "#616161"),
        (55, 75, "#33691e"), (75, 100, "#1b5e20"),
    ]

    def theta_of(s):
        return 180 - (max(0, min(100, s)) / 100) * 180

    parts = [
        f'<path d="{_gauge_band_path(cx, cy, r, theta_of(s0), theta_of(s1))}" '
        f'fill="none" stroke="{color}" stroke-width="16" />'
        for s0, s1, color in bands
    ]
    nx, ny = _polar(cx, cy, r - 28, theta_of(score))
    parts.append(
        f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{nx:.1f}" y2="{ny:.1f}" '
        'stroke="#e6e6e6" stroke-width="3" stroke-linecap="round" />'
    )
    parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" fill="#e6e6e6" />')
    parts.append(
        f'<text x="{cx:.1f}" y="{cy - r * 0.5:.1f}" text-anchor="middle" class="gauge-score">{score}</text>'
    )
    parts.append(f'<text x="{cx - r:.1f}" y="{cy + 11:.1f}" text-anchor="middle" class="gauge-tick">0</text>')
    parts.append(f'<text x="{cx + r:.1f}" y="{cy + 11:.1f}" text-anchor="middle" class="gauge-tick">100</text>')
    return f'<svg viewBox="0 0 {width} {height}">' + "".join(parts) + '</svg>'


def _svg_history_chart(history, width=600, height=220):
    """Historico Fear & Greed (1 ano) en SVG puro (sin JS ni CDN)."""
    pad_l, pad_r, pad_t, pad_b = 30, 10, 16, 16
    w, h = width - pad_l - pad_r, height - pad_t - pad_b
    xs = [p[0] for p in history]
    ys = [p[1] for p in history]
    xr = (xs[-1] - xs[0]) or 1
    pts = [
        f"{pad_l + (x - xs[0]) / xr * w:.1f},{pad_t + (1 - y / 100) * h:.1f}"
        for x, y in zip(xs, ys)
    ]
    path = " ".join(pts)
    grid = []
    for v in (0, 25, 50, 75, 100):
        gy = pad_t + (1 - v / 100) * h
        grid.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l + w}" y2="{gy:.1f}" stroke="#262b38" />'
            f'<text x="{pad_l - 6}" y="{gy + 3:.1f}" text-anchor="end" class="chart-axis">{v}</text>'
        )
    last_x, last_y = pts[-1].split(",")
    return (
        f'<svg viewBox="0 0 {width} {height}">'
        + "".join(grid)
        + f'<polyline points="{path}" fill="none" stroke="#FFD54F" stroke-width="2" stroke-linejoin="round" />'
        + f'<circle cx="{last_x}" cy="{last_y}" r="3.5" fill="#FFD54F" />'
        + '</svg>'
    )


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard de mercado</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px; background: #0f1117; color: #e6e6e6;
    font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  }
  h1 { font-size: 1.6rem; margin-bottom: 0; }
  .subtitle { color: #9aa0ab; margin-top: 4px; margin-bottom: 24px; }
  h2 { font-size: 1.1rem; border-left: 4px solid #4FC3F7; padding-left: 10px; margin-top: 36px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
  .card {
    background: #171a23; border-radius: 12px; padding: 14px 16px;
    border: 1px solid #262b38;
  }
  .card .group { font-size: 0.72rem; color: #767d8a; text-transform: uppercase; letter-spacing: .05em; }
  .card .label { font-size: 1rem; font-weight: 600; margin: 2px 0 8px; }
  .card .price { font-size: 1.3rem; font-weight: 700; }
  .pct-up { color: #4caf50; }
  .pct-down { color: #f44336; }
  .spark { height: 50px; margin-top: 6px; }
  .spark svg, .fg-gauge svg, .fg-hist svg { width: 100%; height: 100%; display: block; }
  .gauge-score { font-size: 26px; font-weight: 800; fill: #FFD54F; }
  .gauge-tick, .chart-axis { font-size: 11px; fill: #767d8a; }
  .fg-summary { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 16px; margin-top: 12px; }
  .fg-score { font-size: 2.6rem; font-weight: 800; color: #FFD54F; line-height: 1; }
  .fg-max { font-size: 1rem; font-weight: 500; color: #767d8a; }
  .fg-rating { font-size: 1.1rem; font-weight: 600; }
  .fg-prev { width: 100%; color: #9aa0ab; font-size: 0.85rem; }
  .fg-wrap { display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; margin-top: 16px; }
  .fg-gauge, .fg-hist { flex: 1 1 320px; min-width: 280px; height: 240px; }
  .chart-ph { color: #4a505c; font-size: 0.8rem; }
  .sub-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; margin-top: 12px; }
  .sub-card { background: #171a23; border: 1px solid #262b38; border-radius: 10px; padding: 10px 12px; font-size: 0.85rem; }
  .sub-card .score { font-size: 1.1rem; font-weight: 700; }
  .news-list { list-style: none; padding: 0; margin-top: 12px; }
  .news-list li {
    background: #171a23; border: 1px solid #262b38; border-radius: 10px;
    padding: 10px 14px; margin-bottom: 8px; display: flex; gap: 10px; align-items: baseline;
  }
  .news-list a { color: #e6e6e6; text-decoration: none; }
  .news-list a:hover { text-decoration: underline; }
  footer { margin-top: 40px; color: #767d8a; font-size: 0.8rem; }
  footer a { color: #4FC3F7; }
</style>
</head>
<body>
  <h1>📊 Dashboard de mercado</h1>
  <div class="subtitle">Actualizado __TODAY__</div>

  <h2>Mercados</h2>
  <div class="grid">__CARDS__</div>

  <h2>Sentimiento de mercado — Fear &amp; Greed (CNN)</h2>
  __FG_SECTION__

  <h2>Titulares</h2>
  <ul class="news-list">__NEWS__</ul>

  <footer>
    Generado automaticamente cada dia por GitHub Actions ·
    <a href="https://github.com/orlanru/finances_data" target="_blank">codigo fuente</a>
  </footer>
</body>
</html>
"""


def build_html(data, fg, news_items):
    """Genera docs/index.html. Todo -- texto y graficos -- se renderiza en el
    servidor (HTML + SVG), asi se ve igual en cualquier navegador sin depender
    de JavaScript ni de CDNs externos."""
    today = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    # --- Tarjetas de mercado, con sparkline en SVG ---
    cards = []
    for group_name, rows in data:
        for r in rows:
            last, pct = r["last"], r["pct"]
            price_text = "s/d" if math.isnan(last) else format_price(last)
            if math.isnan(last) or math.isnan(pct):
                pct_class, pct_text = "", "s/d"
            else:
                pct_class = "pct-up" if pct >= 0 else "pct-down"
                pct_text = f"{'▲' if pct >= 0 else '▼'} {pct:+.2f}%"
            closes = r["closes"]
            if closes and len(closes) > 1:
                spark_svg = _svg_sparkline(closes, closes[-1] >= closes[0])
            else:
                spark_svg = '<span class="chart-ph">Sin datos</span>'
            cards.append(
                '<div class="card">'
                f'<div class="group">{html.escape(group_name)}</div>'
                f'<div class="label">{html.escape(r["label"])}</div>'
                f'<div class="price">{price_text} <span class="{pct_class}">{pct_text}</span></div>'
                f'<div class="spark">{spark_svg}</div>'
                '</div>'
            )
    cards_html = "\n    ".join(cards)

    # --- Fear & Greed, con medidor e historico en SVG ---
    if fg:
        sub_cards = "\n    ".join(
            f'<div class="sub-card"><div>{html.escape(s["label"])}</div>'
            f'<div class="score">{s["score"]} · {html.escape(s["rating"])}</div></div>'
            for s in fg.get("subindicators", [])
        )
        history = fg.get("history", [])
        gauge_svg = _svg_gauge(fg["score"])
        hist_svg = (
            _svg_history_chart(history) if len(history) > 1
            else '<span class="chart-ph">Histórico no disponible.</span>'
        )
        fg_section = (
            '<div class="fg-summary">'
            f'<span class="fg-score">{fg["score"]}<span class="fg-max">/100</span></span>'
            f'<span class="fg-rating">{html.escape(fg["rating"])}</span>'
            f'<span class="fg-prev">Ayer {fg["previous_close"]} · Semana pasada {fg["previous_1_week"]} · '
            f'Mes pasado {fg["previous_1_month"]} · Año pasado {fg["previous_1_year"]}</span>'
            '</div>'
            '<div class="fg-wrap">'
            f'<div class="fg-gauge">{gauge_svg}</div>'
            f'<div class="fg-hist">{hist_svg}</div>'
            '</div>'
            f'<div class="sub-grid">{sub_cards}</div>'
        )
    else:
        fg_section = '<p class="subtitle">Sentimiento no disponible ahora.</p>'

    # --- Titulares (renderizados en el servidor; texto escapado, solo enlaces http) ---
    if news_items:
        items = []
        for n in news_items:
            link = n.get("link", "")
            safe_link = link if isinstance(link, str) and link.startswith("http") else "#"
            items.append(
                f'<li><span>{html.escape(n["tag"])}</span>'
                f'<a href="{html.escape(safe_link)}" target="_blank" rel="noopener noreferrer">'
                f'{html.escape(n["title"])}</a></li>'
            )
        news_html = "\n    ".join(items)
    else:
        news_html = "<li>Sin titulares disponibles ahora.</li>"

    html_doc = (
        _HTML_TEMPLATE
        .replace("__TODAY__", html.escape(today))
        .replace("__CARDS__", cards_html)
        .replace("__FG_SECTION__", fg_section)
        .replace("__NEWS__", news_html)
    )

    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_doc)


def run_digest():
    data = get_market_data()
    fg = get_fear_greed()
    news_items = get_news()

    msg = build_message(data, fg, news_items)
    print(msg)  # util para ver el resultado en los logs
    send(msg)

    chart = build_chart_png(data)
    send_photo(chart, caption="Evolucion del ultimo mes")

    build_html(data, fg, news_items)


if __name__ == "__main__":
    run_digest()
