# finances_data — Resumen diario de mercado por WhatsApp

Bot que envía un resumen diario de mercado por WhatsApp (vía Twilio), con:

- **Índices**: principales índices bursátiles (S&P 500, Nasdaq, Dow Jones, IBEX 35, Euro Stoxx 50), obtenidos con `yfinance` (sin clave).
- **Sentimiento de mercado**: índice Fear & Greed de CNN (endpoint no oficial, sin clave).
- **Titulares**: últimas noticias financieras vía feeds RSS (sin clave).

Todo se envía por WhatsApp usando la API de Twilio.

## Variables de entorno

La configuración se hace mediante variables de entorno (en Replit, mediante *Secrets*). Nunca van en el código. Mira `.env.example` para la plantilla con placeholders.

| Variable | Descripción |
|---|---|
| `TWILIO_ACCOUNT_SID` | SID de tu cuenta de Twilio. |
| `TWILIO_AUTH_TOKEN` | Token de autenticación de tu cuenta de Twilio. |
| `TWILIO_WHATSAPP_FROM` | Número público del sandbox de WhatsApp de Twilio, en formato `whatsapp:+14155238886`. Confírmalo en tu consola de Twilio. |
| `WHATSAPP_TO` | Uno o varios números destinatarios en formato internacional, separados por coma (ej. `+34600111222,+34600333444`). |

## Ejecutar en local

```bash
pip install -r requirements.txt
```

Exporta las variables de entorno necesarias (o usa [`python-dotenv`](https://pypi.org/project/python-dotenv/) con un archivo `.env` local que **no se sube** al repositorio):

```bash
export TWILIO_ACCOUNT_SID=...
export TWILIO_AUTH_TOKEN=...
export TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
export WHATSAPP_TO=+34600111222
```

Y ejecuta:

```bash
python main.py
```

## Desplegar en Replit

1. Importa este repositorio de GitHub en Replit (*Create Repl → Import from GitHub*).
2. Ve a *Tools → Secrets* y añade las cuatro variables de entorno descritas arriba (en Secrets, **nunca** en el código).
3. Pulsa *Run*.

El comando de ejecución (`python3 main.py`) está definido en `.replit`. Si el formato de `.replit` cambia en tu versión de Replit, también puedes fijar el comando de ejecución directamente desde la interfaz de Replit.

## Conectar Twilio

1. Crea una cuenta gratuita en [Twilio](https://www.twilio.com/).
2. Ve a *Messaging → Try it out → WhatsApp sandbox*.
3. Desde cada número de WhatsApp destinatario, envía `join <código>` al número del sandbox para activarlo.

### Nota sobre la ventana de 24h

En el sandbox de Twilio, los envíos automáticos solo llegan si están dentro de las 24h desde el último mensaje que el destinatario envió al bot. Responder al resumen cada día mantiene la ventana abierta. Para un modo 100% manos libres (sin depender de responder), se necesita un número de WhatsApp Business verificado con una plantilla de mensaje aprobada.

## Programarlo a diario

- **Opción A**: usar el *Scheduled Deployment* de Replit para ejecutar el script cada día a una hora fija. No expone ninguna URL pública.
- **Opción B**: disparar la ejecución desde un Atajo de iPhone (Shortcuts) contra un endpoint propio protegido por token.
