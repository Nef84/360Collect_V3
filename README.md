# 360CollectPlus v2.0

**Plataforma de cobranza omnicanal con IA predictiva, segmentación inteligente y operación por roles.**

---

## Qué incluye esta versión

| Área | Mejoras v2.0 |
|------|-------------|
| **Seguridad** | Secretos en `.env`, sin credenciales en código. JWT access (15 min) + refresh token (7 días). Rate limiting en login (10 intentos/min). |
| **Backend modular** | `main.py` dividido en `config.py`, `database.py`, `models.py`, `schemas.py`, `security.py`, `omnichannel_channels.py` |
| **Omnicanalidad** | 4 canales completos: WhatsApp (Twilio), Email (Resend gratis), SMS (TextBelt gratis), CallBot IVR (Twilio Voice) |
| **Frontend** | Logo oficial integrado en todas las pantallas, diseño mejorado con Plus Jakarta Sans, headers de marca, tarjetas mejoradas, panel omnicanal con 4 demos |
| **Docker** | `restart: unless-stopped` en todos los servicios, variables de entorno 100% parametrizadas |
| **API** | 50+ endpoints documentados en `/docs` |

---

## Requisitos

- **Docker Desktop** instalado y en ejecución
- Docker Compose v2 (`docker compose version`)
- Windows 10/11, macOS o Linux con virtualización habilitada
- Conexión a internet (primera vez para descargar imágenes base)

---

## Instalación paso a paso

### 1. Descomprimir el proyecto

```
Extrae el ZIP en la carpeta de tu elección.
```

### 2. Crear el archivo de variables de entorno

```powershell
# Windows PowerShell
Copy-Item .env.example .env
notepad .env
```

```bash
# macOS / Linux
cp .env.example .env
nano .env   # o code .env
```

**Edita obligatoriamente estas 3 variables:**

```env
POSTGRES_PASSWORD=pon_una_contraseña_segura_aqui
JWT_SECRET_KEY=clave_aleatoria_larga_minimo_32_caracteres
JWT_REFRESH_SECRET_KEY=otra_clave_diferente_minimo_32_caracteres
```

**Generar claves seguras:**

```powershell
# PowerShell
[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

```bash
# Linux / macOS
openssl rand -hex 32
```

> ⚠️ El sistema **no arrancará** si estas variables están vacías. Ese comportamiento es intencional para evitar deploys con credenciales por defecto.

### 3. Primer arranque

```bash
docker compose up --build
```

La primera vez descarga las imágenes base de Python, Node y PostgreSQL (~500 MB). Tarda 3–8 minutos según tu conexión. Verás los tres servicios iniciando en paralelo.

**El sistema está listo cuando veas:**

```
collectplus-backend  | INFO:     Application startup complete.
```

### 4. Acceder al sistema

| Servicio | URL |
|----------|-----|
| Frontend (interfaz) | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Swagger (documentación API) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

---

## Publicar en Render

El proyecto ya incluye:

- [render.yaml](/C:/Users/abc/OneDrive/Documentos/360CollectPlus_V3/render.yaml)
- [backend/Dockerfile.render](/C:/Users/abc/OneDrive/Documentos/360CollectPlus_V3/backend/Dockerfile.render)

### Qué crea Render

- Base PostgreSQL administrada: `db-360collect`
- API pública: `api-360collect`
- Frontend público: `app-360collect`

### Pasos

1. Sube estos cambios a tu repo GitHub.
2. Entra a [Render](https://render.com/).
3. Haz clic en `New +` → `Blueprint`.
4. Conecta el repo `Nef84/360Collect_V3`.
5. Selecciona el archivo `render.yaml`.
6. Confirma el despliegue.

### Importante

- El backend ahora puede sembrar una base vacía automáticamente usando `database/init.sql`.
- El frontend en Render se construye con la URL pública del backend mediante `VITE_API_URL=https://$BACKEND_HOST`.
- El primer despliegue puede tardar varios minutos mientras Render crea la base, construye la API y compila el frontend.

### URLs esperadas

- Frontend: `https://app-360collect.onrender.com`
- Backend: `https://api-360collect.onrender.com`
- Health: `https://api-360collect.onrender.com/health`

---

## Usuarios de prueba

Todos usan la contraseña: `Password123!`

| Rol | Usuarios disponibles |
|-----|---------------------|
| Admin | `admin`, `admin2` |
| Collector | `collector1`, `collector2`, `collector3` |
| Supervisor | `supervisor1`, `supervisor2` |
| Auditor | `auditor1`, `auditor2` |
| GestorUsuarios | `gestor1`, `gestor2` |

---

## Comandos del día a día

```bash
# Apagar sin borrar datos
docker compose down

# Volver a levantar (sin rebuild)
docker compose up

# Rebuild si cambiaste código Python o JSX
docker compose up --build

# Ver logs en tiempo real
docker compose logs -f

# Ver logs solo del backend
docker compose logs -f backend

# Reset COMPLETO — borra base de datos y vuelve al estado inicial
docker compose down -v
docker compose up --build
```

---

## Configurar canales omnicanal

Entra como `admin` y ve a **Consola administrativa → Centro omnicanal**.

### WhatsApp Bot (Twilio — ya configurado)

1. Ingresa `twilio_account_sid` y `twilio_auth_token` de tu cuenta Twilio
2. `twilio_whatsapp_from`: `whatsapp:+14155238886` (sandbox Twilio)
3. Guarda y prueba con el botón "Enviar demo por WhatsApp"

### Email — Resend.com (gratis 100/día)

1. Registra en [resend.com/signup](https://resend.com/signup) (solo email, sin tarjeta)
2. Crea una API key en [resend.com/api-keys](https://resend.com/api-keys)
3. Ingresa la key en el campo `resend_api_key`
4. Pon tu email en `email_from` (ej: `cobranza@tudominio.com`)
5. Prueba con el botón "Enviar email de prueba"

> Alternativa SMTP: usa Gmail (`smtp.gmail.com:587`) con una [contraseña de aplicación](https://myaccount.google.com/apppasswords).

### SMS — TextBelt (gratis sin cuenta)

- Para demo: el campo `textbelt_api_key` ya tiene `textbelt` (1 SMS gratis/día por IP)
- Para producción: compra créditos en [textbelt.com](https://textbelt.com) (~$0.01/SMS)
- El número destino debe incluir código de país: `+50312345678`

### CallBot IVR — Twilio Voice (trial gratis)

1. En tu cuenta Twilio, obtén un número con capacidad de voz
2. Ingresa ese número en `twilio_voice_from` (ej: `+15551234567`)
3. Para pruebas locales, expón el backend con ngrok:
   ```bash
   ngrok http 8000
   ```
4. Copia la URL ngrok al campo `callbot_webhook_url` (ej: `https://abc123.ngrok.io`)
5. Prueba con "Iniciar llamada de prueba"

> Con cuenta trial solo puedes llamar a números verificados en la consola Twilio.

---

## Estructura del proyecto

```
360CollectPlus/
├── .env.example              ← Plantilla de variables (copia como .env)
├── .gitignore                ← Excluye venv/, node_modules/, .env, etc.
├── docker-compose.yml        ← Orquestación de los 3 servicios
├── README.md                 ← Este archivo
│
├── backend/
│   ├── main.py               ← FastAPI app + 50+ rutas
│   ├── config.py             ← Settings (pydantic-settings + .env)
│   ├── database.py           ← Engine + sesión SQLAlchemy
│   ├── models.py             ← Modelos ORM (10 tablas)
│   ├── schemas.py            ← Schemas Pydantic request/response
│   ├── security.py           ← JWT, hashing, rate limiting
│   ├── omnichannel_channels.py ← Email, SMS, CallBot IVR
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example          ← Variables del backend
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx           ← UI React completa (5 roles)
│   │   ├── index.css         ← Estilos globales + Plus Jakarta Sans
│   │   └── assets/
│   │       └── collectplus-logo.png ← Logo oficial
│   ├── package.json
│   ├── tailwind.config.js
│   ├── vite.config.js
│   └── Dockerfile
│
└── database/
    └── init.sql              ← Schema PostgreSQL + datos semilla
```

---

## Solución de problemas frecuentes

### "POSTGRES_PASSWORD must be set"
No existe el archivo `.env` o le falta esa variable. Ejecuta el paso 2.

### El login falla con "Credenciales inválidas"
- Verifica que el backend esté corriendo: `http://localhost:8000/health`
- Si cambiaste `init.sql` o `.env`, recrea el volumen:
  ```bash
  docker compose down -v && docker compose up --build
  ```

### Cambios en `init.sql` no se reflejan
PostgreSQL no re-ejecuta `init.sql` si el volumen ya existe. Siempre:
```bash
docker compose down -v
docker compose up --build
```

### Puerto 5173 o 8000 ocupado
Cambia en `.env`:
```env
BACKEND_PORT=8001
FRONTEND_PORT=5174
```

### CallBot no responde / "callbot_webhook_url no configurado"
Twilio necesita una URL pública para llamar al webhook. En desarrollo:
```bash
ngrok http 8000
# Copia la URL https://... al campo callbot_webhook_url en el admin
```

### Pantalla en blanco en el frontend
```bash
docker compose up --build frontend
```
Abre la consola del navegador (F12) para ver el error específico.

---

## Variables de entorno completas

| Variable | Descripción | Valor por defecto |
|----------|-------------|-------------------|
| `POSTGRES_DB` | Nombre de la base | `collectplus` |
| `POSTGRES_USER` | Usuario PostgreSQL | `postgres` |
| `POSTGRES_PASSWORD` | **Cambiar — obligatorio** | *(vacío)* |
| `DB_PORT` | Puerto PostgreSQL en host | `55432` |
| `JWT_SECRET_KEY` | **Cambiar — obligatorio** | *(vacío)* |
| `JWT_REFRESH_SECRET_KEY` | **Cambiar — obligatorio** | *(vacío)* |
| `JWT_EXPIRE_MINUTES` | Duración access token | `15` |
| `JWT_REFRESH_EXPIRE_DAYS` | Duración refresh token | `7` |
| `CORS_ORIGINS` | Orígenes CORS permitidos | `localhost:5173` |
| `BACKEND_PORT` | Puerto backend en host | `8000` |
| `FRONTEND_PORT` | Puerto frontend en host | `5173` |
| `RESEND_API_KEY` | API key de Resend.com | *(vacío)* |
| `EMAIL_FROM` | Dirección de envío de emails | *(vacío)* |
| `TEXTBELT_API_KEY` | Key TextBelt (`textbelt` = gratis) | `textbelt` |

---

## Seguridad en producción

- [ ] Cambiar `POSTGRES_PASSWORD`, `JWT_SECRET_KEY` y `JWT_REFRESH_SECRET_KEY`
- [ ] Nunca subir `.env` al repositorio (está en `.gitignore`)
- [ ] Restringir `CORS_ORIGINS` a tu dominio real
- [ ] Poner un reverse proxy (nginx) con HTTPS delante de los contenedores
- [ ] Habilitar backups automáticos del volumen PostgreSQL
- [ ] Cambiar las contraseñas de todos los usuarios demo antes de usar en producción

---

## Documentación incluida

En la carpeta `docs/` encontrarás:

- `01_360CollectPlus_Presentacion_Comercial.pdf` — Presentación de ventas
- `02_Manual_Collector.pdf` — Manual del gestor de cobranza
- `03_Manual_Supervisor.pdf` — Manual del supervisor
- `04_Manual_Administrador.pdf` — Manual completo del administrador
- `05_Resumen_Ejecutivo_360Collect_V3.md` — Documento ejecutivo para comité y presentación comercial
- `06_Presentacion_Ejecutiva_360Collect_V3.md` — Presentación ejecutiva base de 10 diapositivas
- `07_Guion_Video_Ejecutivo_360Collect_V3.md` — Guion ejecutivo para video comercial/presentación

---

## Publicación recomendada

La forma más simple de dejar este proyecto funcional en internet es con Render:

- Frontend: `https://app-360collect.onrender.com`
- Backend API: `https://api-360collect.onrender.com`

### Qué hace el archivo `render.yaml`

Se agregó [render.yaml](/C:/Users/abc/OneDrive/Documentos/360CollectPlus_V3/render.yaml) para desplegar:

- un frontend estático en Render
- un backend FastAPI en Render
- una base PostgreSQL administrada en Render

### Cómo publicarlo

1. Sube este proyecto a GitHub en `https://github.com/Nef84/360Collect`
2. Crea una cuenta en [Render](https://render.com/)
3. En Render, elige `New +` → `Blueprint`
4. Conecta el repo `Nef84/360Collect`
5. Render detectará `render.yaml` y propondrá:
   - `app-360collect`
   - `api-360collect`
   - `db-360collect`
6. Confirma el deploy

### Notas

- Los subdominios `onrender.com` son gratuitos y suficientes para dejarlo publicado.
- Si luego compras tu propio dominio, puedes apuntar:
  - `app.tudominio.com` al frontend
  - `api.tudominio.com` al backend
- La base gratis de Render expira a los 30 días si no la actualizas a un plan pagado.
