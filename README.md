# PERMANECE

MVP web para identificar y hacer seguimiento a estudiantes en riesgo académico en Sabana Centro.

Según el informe *Sabana Centro Cómo Vamos*, en 2024 la tasa de deserción escolar del consolidado Sabana Centro fue del 3,5 %, por encima de la de Cundinamarca (3,2 %). El mismo informe señala que el aumento de la deserción y la repitencia obliga a replantear la permanencia escolar. PERMANECE reúne en un solo flujo los datos del estudiante, sus factores de riesgo y las intervenciones que se han hecho, para que docentes y orientadores puedan decidir qué casos atender primero.

> El puntaje **orienta la revisión** y debe complementarse con valoración humana. **No** es una predicción validada de deserción.

**Stack:** Python · Flask · Jinja2 · Bootstrap 5 · Chart.js · SQLAlchemy · PostgreSQL (Neon) · Flask-Login · Flask-WTF (CSRF) · Brevo (correos) · Render (hosting).

---

## 1. Instalación rápida (desarrollo)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # en Windows: copy .env.example .env

flask --app run seed --n 90 --reset   # borra y recrea tablas + datos FICTICIOS
flask --app run run --debug     # http://127.0.0.1:5000
```

Usuarios de demostración que crea `seed` (3 colegios ficticios):

| Rol | Correo | Contraseña |
|---|---|---|
| Administrador general | admin@permanece.example | Admin2026* |
| Colegio (coordinación) | sangabriel@ · lasabana@ · elprado@permanece.example | Colegio2026* |
| Docente / orientador | docente.sangabriel@ · docente.lasabana@ · docente.elprado@permanece.example | Docente2026* |

## Roles y flujo por colegio

| Rol | Qué puede hacer |
|---|---|
| **Administrador general** | Crea colegios con sus credenciales, ve y filtra todos los colegios, gestiona cualquier usuario y puede intervenir en cualquier caso. |
| **Colegio** | Registra y edita a sus estudiantes, crea a sus docentes y hace seguimiento. Solo ve su colegio. |
| **Docente / orientador** | Ve el dashboard y los estudiantes de su colegio, registra factores e intervenciones. No crea estudiantes ni usuarios. |

Un usuario que no es administrador **nunca** ve datos de otro colegio: si intenta abrir un registro ajeno recibe 404. Si un colegio se desactiva, sus usuarios no pueden iniciar sesión. El documento del estudiante es único **dentro de cada colegio**.

Sin `DATABASE_URL` en el `.env`, la aplicación usa SQLite (`permanece_dev.db`). Sirve para desarrollar sin instalar nada más.

## 2. Módulo académico (de dónde sale el riesgo)

1. **Colegio** → *Académico*: crea el **periodo activo**, las **materias** y los **cursos** (materia + docente + grado/grupo).
2. **Docente** → *Mis cursos*: crea actividades con su **porcentaje** (ej. Taller 30 %, Quiz 20 %, Examen 50 %), califica y **toma asistencia** por clase.
3. Al guardar, PERMANECE calcula para cada estudiante:
   - **Nota de la materia** = promedio ponderado de las actividades calificadas; reprobada si < 3,0.
   - **Promedio del periodo** = promedio de las materias.
   - **Asistencia** = (presente + tarde) ÷ (clases − ausencias con excusa).
4. Con eso y lo que registra orientación (apoyo familiar, reporte activo) se **recalcula el riesgo**.
   Si un estudiante **pasa a riesgo alto**, se envía un correo a la coordinación y al acudiente
   (al acudiente sin puntajes: solo la invitación a comunicarse con el colegio).

## 3. Despliegue gratis: Render + Neon + Brevo

| Pieza | Servicio | Costo |
|---|---|---|
| App | Render (plan Free) → `https://<nombre>.onrender.com` con HTTPS automático | $0 |
| Base de datos | Neon (PostgreSQL, plan Free, sin vencimiento) | $0 |
| Correos | Brevo (API HTTPS, 300/día) | $0 |

1. **GitHub**: sube el proyecto a un repositorio (el `.gitignore` ya excluye `.env`, `.venv` y la base local).
2. **Neon** (neon.tech): crea un proyecto en la región *AWS US East (N. Virginia)* y copia la *connection string*.
3. **Brevo** (brevo.com): crea la cuenta, verifica tu correo remitente (*Senders*) y genera una *API key* (*SMTP & API → API Keys*).
4. **Render** (render.com): *New + → Blueprint* → elige el repositorio (usa `render.yaml`). Completa las variables:
   `DATABASE_URL` (Neon), `APP_URL` (`https://<nombre>.onrender.com`), `BREVO_API_KEY`, `CORREO_REMITENTE`,
   `ADMIN_EMAIL`, `ADMIN_PASSWORD` (crea el administrador en el primer arranque).
5. **Datos de demostración en Neon** (opcional, desde tu PC): pon la URL de Neon en `DATABASE_URL` del `.env`
   y ejecuta `flask --app run seed --n 90`. Luego vuelve a comentar esa línea para trabajar en local con SQLite.

> El plan Free de Render se duerme tras 15 min sin visitas y tarda ~1 min en despertar: ábrela unos minutos antes de una demo.
> Render Free bloquea los puertos SMTP; por eso los correos van por la API de Brevo.

## 4. Pruebas

```bash
python -m pytest -q
```
Hay 61 pruebas: reglas de riesgo con valores límite, permisos por rol y aislamiento entre colegios, estudiantes, notas ponderadas, asistencia con excusas, recálculo del riesgo, alertas por correo (una sola vez), invitaciones y recuperación de contraseña. Para correrlas contra PostgreSQL: `TEST_DATABASE_URL=postgresql+psycopg://... python -m pytest`.

## 5. Estructura

```
permanece/
├── run.py                  # punto de entrada (flask / gunicorn)
├── config.py               # configuración por entorno (lee .env)
├── app/
│   ├── __init__.py         # create_app, blueprints, cabeceras de seguridad
│   ├── models.py           # Usuario, Estudiante, RegistroFactores, Intervencion
│   ├── riesgo.py           # ★ reglas de clasificación (puras, sin Flask)
│   ├── academico.py        # ★ cálculo de notas, asistencia y recálculo del riesgo
│   ├── academico_routes.py # periodos, materias, cursos, planilla de notas y asistencia
│   ├── correo.py           # Brevo: invitaciones, recuperar contraseña, alertas
│   ├── forms.py            # formularios y validaciones en servidor
│   ├── permisos.py         # decoradores por rol
│   ├── cli.py              # init-db, crear-admin, seed
│   ├── auth/               # login / logout
│   ├── estudiantes/        # CRUD, factores, filtros
│   ├── seguimiento/        # intervenciones
│   ├── dashboard/          # indicadores agregados
│   ├── instituciones/      # colegios y sus credenciales (solo admin)
│   ├── usuarios/           # usuarios (admin) y docentes (colegio)
│   ├── templates/          # Jinja2 + Bootstrap
│   └── static/             # css, js y librerías locales (sin CDN)
├── sql/schema_postgres.sql  # referencia del esquema (init-db lo crea)
├── render.yaml             # despliegue en Render
└── tests/
```

## 6. Reglas de riesgo (propuesta inicial, `app/riesgo.py`)

| Factor | Puntos |
|---|---|
| Asistencia inferior al 80 % | 30 |
| 3 o más asignaturas reprobadas | 25 |
| Promedio inferior a 3,0 / 5,0 | 20 |
| Apoyo familiar insuficiente | 15 |
| Reporte de seguimiento activo | 10 |

**Bajo** 0–29 · **Medio** 30–59 · **Alto** 60–100.
Si falta un dato, ese factor no suma puntos, pero el caso queda marcado como **datos incompletos**: la falta de información no se toma como ausencia de riesgo.
Para cambiar pesos o umbrales después de la revisión AN-02, basta con editar las constantes al inicio de `riesgo.py` y actualizar las pruebas.

## 7. Trazabilidad requisitos → código

| Requisito | Dónde |
|---|---|
| RF-01/02 Inicio y cierre de sesión | `auth/routes.py` |
| RF-03 Administración de usuarios | `usuarios/routes.py`, `instituciones/routes.py` |
| RF-04 Permisos por rol | `permisos.py` (admin / colegio / docente, con alcance por colegio) |
| RF-05/06/07 Registro, edición y consulta de estudiantes | `estudiantes/routes.py` |
| RF-08 Factores de riesgo por periodo | `estudiantes/routes.py::factores` |
| RF-09/10 Cálculo y visualización del nivel | `riesgo.py`, `estudiantes/detalle.html` |
| RF-11 Filtros por grado y riesgo | `estudiantes/routes.py::consulta_filtrada` |
| RF-12/13 Seguimientos y cronología | `seguimiento/routes.py`, `detalle.html` |
| RF-14 Dashboard por grado | `dashboard/routes.py` + Chart.js |
| RF-15 Validación y mensajes | `forms.py`, macro `campo` |
| RNF-01 Seguridad | hash de contraseñas, CSRF, cookies `Secure` en producción, `ProxyFix`, sin redirección abierta |
| RNF-02 Datos personales | datos ficticios en `seed`, `Cache-Control: no-store` |
| RNF-03 Responsivo | tabla en escritorio y tarjetas en celular; sin scroll horizontal a 360 px |
| RNF-05 Respaldo | Neon guarda historial (point-in-time restore) de la base |
| RNF-06 Riesgo explicado | color + icono + texto + factores en cada nivel |

## 8. Decisiones pendientes (AN-02)

- Definir qué se considera "apoyo familiar insuficiente" (hoy hay tres categorías: adecuado, parcial e insuficiente).
- Definir qué cuenta como "reporte de seguimiento activo" (hoy es un Sí/No registrado con los factores).
- Validar los pesos y umbrales con un docente u orientador y dejar registrados los ajustes.
- Acordar si el periodo de asistencia es el bimestre o el acumulado del año.
