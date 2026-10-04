# 🤖 Bot Mediación Usted

Bot automatizado que monitorea el portal [Mediación Chile](https://pmf.mediacionchile.gob.cl) en busca de citaciones agendadas y envía alertas en tiempo real a Discord.

## ¿Qué hace?

El bot se conecta periódicamente al portal de mediación del Poder Judicial de Chile, inicia sesión con Segunda Clave, y verifica si existen citaciones pendientes. Si detecta un cambio (por ejemplo, una sesión agendada), envía una notificación al canal de Discord configurado.

```
Portal Mediación Chile
        ↓ (scraping autenticado)
   Detección de cambio
        ↓
  Firestore (estado)  →  Discord (alerta)
```

## Arquitectura

```
bot-mediacion-usted/
├── main.py              # Punto de entrada y orquestador principal
├── scraper.py           # Login y scraping del portal mediacionchile.gob.cl
├── db_handler.py        # Lectura/escritura de estado en Firestore
├── discord_notifier.py  # Envío de alertas vía webhook de Discord
├── Dockerfile           # Imagen Docker (python:3.10-slim, usuario no-root)
└── requirements.txt     # Dependencias Python
```

## Servicios de GCP utilizados

| Servicio | Uso |
|---|---|
| **Cloud Run Jobs** | Ejecuta el container del bot de forma periódica (serverless, sin servidor siempre activo) |
| **Firestore** (`wawitadb`) | Persiste el estado actual de las citaciones y el historial de ejecuciones. Colecciones: `mediation_state`, `execution_logs` |
| **Secret Manager** | Almacena de forma segura las credenciales del portal y el webhook de Discord |
| **Artifact Registry** | Almacena la imagen Docker del bot |
| **Cloud Scheduler** | *(recomendado)* Dispara el Cloud Run Job en intervalos regulares (ej: cada 30 minutos) |

### Service Account requerida

La SA del Job necesita los siguientes roles:

| Rol IAM | Para qué |
|---|---|
| `roles/secretmanager.secretAccessor` | Leer los secretos en runtime |
| `roles/datastore.user` | Leer y escribir en Firestore |
| `roles/artifactregistry.reader` | Descargar la imagen Docker |

## Variables de entorno / Secretos

Configurar en **Secret Manager** y mapear como variables de entorno en el Cloud Run Job:

| Variable | Descripción | Requerida |
|---|---|---|
| `MEDIACION_RUN` | RUN chileno sin puntos ni guión (ej: `12345678K`) | ✅ |
| `MEDIACION_PASSWORD` | Segunda Clave del portal Mediación Chile | ✅ |
| `DISCORD_WEBHOOK_URL` | URL completa del webhook de Discord | ✅ |
| `MEDIACION_COOKIE` | Cookie `ASP.NET_SessionId` (alternativa a RUN+PASSWORD si se usa ClaveÚnica) | ⬜ |
| `GOOGLE_APPLICATION_CREDENTIALS` | Ruta al JSON de service account (solo desarrollo local) | ⬜ |

> En producción (Cloud Run), **no** se usa `GOOGLE_APPLICATION_CREDENTIALS` — las credenciales de Firestore se obtienen automáticamente via Application Default Credentials (ADC) desde la SA asignada al Job.

## Librerías Python

| Librería | Uso |
|---|---|
| `google-cloud-firestore` | Cliente de Firestore para persistir estado y logs |
| `requests` | HTTP client para el scraping del portal y envío de webhooks a Discord |
| `beautifulsoup4` | Parsing del HTML del portal para extraer texto de citaciones |
| `python-dotenv` | Carga de variables desde `.env` en desarrollo local |

## Seguridad

- El container corre con **usuario no privilegiado** (`botuser`, sin root)
- Las credenciales **nunca se bakean** en la imagen Docker
- Todos los logs sanitizan datos sensibles (RUN, cookies, webhooks) antes de escribirlos
- Verificación SSL siempre activa (`session.verify = True`)
- Validación de dominio en redirecciones HTTP (solo acepta `pmf.mediacionchile.gob.cl`)
- Límite de tamaño de respuesta HTTP: 512 KB (protección contra respuestas maliciosas)

## Desarrollo local

### Requisitos
- Python 3.11+
- Docker (opcional)
- Acceso a un proyecto GCP con Firestore habilitado

### Setup

```bash
# 1. Clonar y entrar al proyecto
git clone <repo-url>
cd bot-mediacion-usted

# 2. Crear entorno virtual e instalar dependencias
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales reales

# 4. Ejecutar
python main.py
```

### Con Docker

```bash
# Build
docker build -t bot-mediacion .

# Run (pasando el .env)
docker run --env-file .env bot-mediacion
```

## Deploy en GCP

### Build y push de imagen

```bash
# Configurar Docker para usar Artifact Registry
gcloud auth configure-docker southamerica-west1-docker.pkg.dev

# Build y push
docker build -t southamerica-west1-docker.pkg.dev/bot-sitio-mediacion-valecita/bot-mediacion/bot:latest .
docker push southamerica-west1-docker.pkg.dev/bot-sitio-mediacion-valecita/bot-mediacion/bot:latest
```

### Actualizar el Job

```bash
gcloud run jobs update bot-mediacion \
  --image southamerica-west1-docker.pkg.dev/bot-sitio-mediacion-valecita/bot-mediacion/bot:latest \
  --region us-central1
```

### Ejecutar manualmente

```bash
gcloud run jobs execute bot-mediacion --region us-central1
```

## Flujo de ejecución

```
main.py::run_check()
  │
  ├─ MediationScraper.check_citations()
  │     ├─ GET /MisCitaciones  →  si redirige al login:
  │     │     └─ login() con MEDIACION_RUN + MEDIACION_PASSWORD
  │     └─ Parsea HTML con BeautifulSoup
  │           ├─ "no posee sesiones"  →  has_date=False
  │           └─ otro contenido       →  has_date=True
  │
  ├─ MediationDB.update_state_if_changed()
  │     └─ Compara con estado anterior en Firestore
  │           └─ should_notify=True si es cambio nuevo y no notificado
  │
  ├─ [si should_notify] DiscordNotifier.send_change_alert()
  │     └─ POST webhook Discord con embed formateado
  │
  └─ MediationDB.log_execution()
        └─ Escribe log de auditoría en colección execution_logs
```

## Licencia

Ver [LICENSE](LICENSE).
