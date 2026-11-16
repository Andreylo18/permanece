"""Envío de correos con Brevo por su API HTTPS.

Render (plan gratis) bloquea los puertos SMTP, por eso se usa la API REST.
Sin BREVO_API_KEY (desarrollo local o pruebas) los correos NO se envían: se
guardan en `current_app.extensions["correos_simulados"]` y se escriben en el log.
Un fallo de correo nunca rompe la operación principal.
"""
import logging

import requests
from flask import current_app, render_template, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .extensions import db
from .models import Usuario

log = logging.getLogger(__name__)
BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def correo_configurado():
    cfg = current_app.config
    return bool(cfg.get("BREVO_API_KEY") and cfg.get("CORREO_REMITENTE"))


def enviar(destinatario, asunto, plantilla, **contexto):
    """Envía un correo HTML. Devuelve True si Brevo lo aceptó."""
    if not destinatario:
        return False
    html = render_template(f"correos/{plantilla}.html", asunto=asunto, **contexto)
    cfg = current_app.config
    if not correo_configurado():
        current_app.extensions.setdefault("correos_simulados", []).append(
            {"para": destinatario, "asunto": asunto, "html": html, **contexto})
        log.warning("Correo NO enviado (Brevo sin configurar) -> %s: %s", destinatario, asunto)
        return False
    try:
        r = requests.post(BREVO_URL, timeout=10, headers={
            "api-key": cfg["BREVO_API_KEY"], "accept": "application/json", "content-type": "application/json",
        }, json={
            "sender": {"email": cfg["CORREO_REMITENTE"], "name": cfg["CORREO_NOMBRE"]},
            "to": [{"email": destinatario}],
            "subject": asunto,
            "htmlContent": html,
        })
        if r.status_code >= 300:
            log.error("Brevo respondió %s: %s", r.status_code, r.text[:300])
            return False
        return True
    except requests.RequestException as e:
        log.error("No se pudo contactar a Brevo: %s", e)
        return False


def url_absoluta(endpoint, **valores):
    base = current_app.config.get("APP_URL")
    if base:
        return base + url_for(endpoint, **valores)
    return url_for(endpoint, _external=True, **valores)


# ---------------- Enlaces para definir / restablecer contraseña ----------------

def _serializador():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="permanece-contrasena")


def generar_token(usuario):
    # Incluye parte del hash actual: el enlace deja de servir cuando se cambia la contraseña
    return _serializador().dumps({"u": usuario.id, "h": usuario.password_hash[-16:]})


def usuario_desde_token(token):
    horas = current_app.config.get("HORAS_VALIDEZ_ENLACE", 72)
    try:
        datos = _serializador().loads(token, max_age=horas * 3600)
    except (SignatureExpired, BadSignature):
        return None
    usuario = db.session.get(Usuario, datos.get("u"))
    if usuario is None or usuario.password_hash[-16:] != datos.get("h") or not usuario.is_active:
        return None
    return usuario


def enlace_contrasena(usuario):
    return url_absoluta("auth.definir_contrasena", token=generar_token(usuario))


def enviar_invitacion(usuario, creado_por):
    """Bienvenida con enlace para que el usuario defina su contraseña."""
    enlace = enlace_contrasena(usuario)
    ok = enviar(usuario.email, "Tu acceso a PERMANECE", "invitacion", usuario=usuario,
                creado_por=creado_por, enlace=enlace,
                horas=current_app.config.get("HORAS_VALIDEZ_ENLACE", 72))
    return ok, enlace


def avisar_invitacion(usuario, creado_por):
    """Envía la invitación y deja un mensaje en pantalla según el resultado."""
    from flask import flash
    from markupsafe import Markup, escape
    ok, enlace = enviar_invitacion(usuario, creado_por)
    if ok:
        flash(f"Se envió un correo a {usuario.email} para que defina su contraseña.", "success")
    else:
        flash(Markup("No se pudo enviar el correo de invitación (envío no configurado o con error). "
                     "Comparte este enlace con la persona; vence en "
                     f"{current_app.config.get('HORAS_VALIDEZ_ENLACE', 72)} horas:<br>"
                     f"<code class='user-select-all'>{escape(enlace)}</code>"), "warning")


def enviar_recuperacion(usuario):
    return enviar(usuario.email, "Restablece tu contraseña de PERMANECE", "recuperar",
                  usuario=usuario, enlace=enlace_contrasena(usuario),
                  horas=current_app.config.get("HORAS_VALIDEZ_ENLACE", 72))


# ---------------- Alerta de riesgo alto ----------------

def notificar_riesgo_alto(est):
    """Avisa a la coordinación del colegio y al acudiente (si tiene correo).

    Al acudiente NO se le envían puntajes ni detalles: solo una invitación a
    comunicarse con el colegio. Los detalles quedan para el personal autorizado.
    """
    coordinadores = db.session.execute(
        db.select(Usuario).filter_by(institucion_id=est.institucion_id, rol="colegio", activo=True)
    ).scalars().all()
    reg = est.registro_vigente
    resultado = reg.resultado() if reg else None
    try:
        enlace = url_absoluta("estudiantes.detalle", estudiante_id=est.id)
    except RuntimeError:  # sin contexto de petición (p. ej. comando de consola sin APP_URL)
        enlace = None
    for u in coordinadores:
        enviar(u.email, f"Alerta PERMANECE: {est.nombre_completo} en riesgo alto", "alerta_colegio",
               est=est, resultado=resultado, enlace=enlace)
    if est.email_acudiente:
        enviar(est.email_acudiente, f"{est.institucion.nombre}: seguimiento académico de {est.nombres}",
               "alerta_acudiente", est=est)
