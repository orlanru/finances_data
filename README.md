# finances_data — Resumen diario de mercado por Telegram

Bot que envía un resumen diario de mercado por Telegram, con:

- **Índices**: principales índices bursátiles (S&P 500, Nasdaq, Dow Jones, IBEX 35, Euro Stoxx 50), obtenidos con `yfinance` (sin clave).
- **Sentimiento de mercado**: índice Fear & Greed de CNN (endpoint no oficial, sin clave).
- **Titulares**: últimas noticias financieras vía feeds RSS (sin clave).

Todo se envía por Telegram usando un bot propio, gratis y sin límites de uso.

## Variables de entorno

La configuración se hace mediante variables de entorno (en Replit, mediante *Secrets*; en GitHub Actions, mediante *Repository secrets*). Nunca van en el código. Mira `.env.example` para la plantilla con placeholders.

| Variable | Descripción |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram, obtenido desde `@BotFather`. |
| `TELEGRAM_CHAT_ID` | Uno o varios `chat_id` destinatarios, separados por coma (ej. `111111111,222222222`). |

## Ejecutar en local

```bash
pip install -r requirements.txt
```

Exporta las variables de entorno necesarias (o usa [`python-dotenv`](https://pypi.org/project/python-dotenv/) con un archivo `.env` local que **no se sube** al repositorio):

```bash
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=123456789
```

Y ejecuta:

```bash
python main.py
```

## Desplegar en Replit

1. Importa este repositorio de GitHub en Replit (*Create Repl → Import from GitHub*).
2. Ve a *Tools → Secrets* y añade las dos variables de entorno descritas arriba (en Secrets, **nunca** en el código).
3. Pulsa *Run*.

El comando de ejecución (`python3 main.py`) está definido en `.replit`. Si el formato de `.replit` cambia en tu versión de Replit, también puedes fijar el comando de ejecución directamente desde la interfaz de Replit.

## Conectar Telegram

1. Abre Telegram y busca `@BotFather`.
2. Envíale `/newbot` y sigue las instrucciones (nombre y usuario del bot). Al terminar te dará el **token** del bot — esto es `TELEGRAM_BOT_TOKEN`.
3. Envía cualquier mensaje a tu bot recién creado (para que exista una conversación).
4. Visita en el navegador `https://api.telegram.org/bot<TOKEN>/getUpdates` (sustituyendo `<TOKEN>` por el tuyo) y busca el campo `"chat":{"id": ...}` — ese número es tu `TELEGRAM_CHAT_ID`.
5. Si quieres enviarlo a un grupo en vez de a un chat privado, añade el bot al grupo, escribe algo en el grupo y repite el paso 4 (el `chat_id` de un grupo suele ser negativo).

A diferencia de WhatsApp/Twilio, Telegram no tiene sandbox, ni ventana de 24h, ni coste por mensaje: una vez tienes el token y el `chat_id`, funciona indefinidamente sin mantenimiento.

## Programarlo a diario

- **Opción A (recomendada): GitHub Actions.** El repo incluye `.github/workflows/daily-digest.yml`, que ejecuta `main.py` automáticamente todos los días a las 08:00 UTC y además se puede disparar manualmente en cualquier momento. Es gratis, no requiere ningún servidor ni Repl encendido, y los secretos viven en el propio repo de GitHub.

  1. Ve a *Settings → Secrets and variables → Actions* en GitHub y añade las dos variables (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) como *Repository secrets*.
  2. El workflow ya queda activo con el push a `main`; se ejecutará solo cada día a la hora configurada.
  3. Para ajustar la hora, edita la línea `cron: "0 8 * * *"` (formato UTC, minuto hora * * *).
  4. Para lanzarlo manualmente "a consulta" (sin esperar al schedule):
     - Desde la web: pestaña *Actions → Daily market digest → Run workflow*.
     - Desde la terminal, con [GitHub CLI](https://cli.github.com/) autenticado: `gh workflow run daily-digest.yml`.
     - Los logs de cada ejecución (programada o manual) quedan en la pestaña *Actions*.

- **Opción B**: usar el *Scheduled Deployment* de Replit para ejecutar el script cada día a una hora fija. No expone ninguna URL pública.
- **Opción C**: disparar la ejecución desde un Atajo de iPhone (Shortcuts) contra un endpoint propio protegido por token.
