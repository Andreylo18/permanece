import os

from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from config import config_por_nombre
from .extensions import csrf, db, login_manager


def create_app(nombre_config=None):
    nombre_config = nombre_config or os.environ.get("FLASK_ENV_NAME", "development")
    app = Flask(__name__)
    app.config.from_object(config_por_nombre[nombre_config])

    if nombre_config == "production":
        # Detrás de un proxy HTTPS (Nginx, Render, Azure...): respeta X-Forwarded-*
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        if app.config["SECRET_KEY"].startswith("cambia-esta"):
            raise RuntimeError("Define SECRET_KEY en el entorno de producción.")

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .models import Usuario

    @login_manager.user_loader
    def cargar_usuario(user_id):
        return db.session.get(Usuario, int(user_id))

    from .academico_routes import bp as academico_bp
    from .auth.routes import bp as auth_bp
    from .dashboard.routes import bp as dashboard_bp
    from .estudiantes.routes import bp as estudiantes_bp
    from .instituciones.routes import bp as instituciones_bp
    from .seguimiento.routes import bp as seguimiento_bp
    from .usuarios.routes import bp as usuarios_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(estudiantes_bp, url_prefix="/estudiantes")
    app.register_blueprint(seguimiento_bp, url_prefix="/estudiantes")
    app.register_blueprint(usuarios_bp, url_prefix="/usuarios")
    app.register_blueprint(instituciones_bp, url_prefix="/colegios")
    app.register_blueprint(academico_bp, url_prefix="/academico")

    from .models import nombre_grado
    from .riesgo import NIVELES

    @app.context_processor
    def utilidades_plantillas():
        return {"nombre_grado": nombre_grado, "NIVELES": NIVELES, "periodo_nav": _periodo_nav()}

    def _periodo_nav():
        """Periodo activo del colegio del usuario y su avance en semanas (para el menú)."""
        from datetime import date
        from flask_login import current_user
        if not current_user.is_authenticated or not current_user.institucion_id:
            return None
        from .academico import periodo_activo
        p = periodo_activo(current_user.institucion_id)
        if p is None:
            return None
        total = max(1, -(-((p.fecha_fin - p.fecha_inicio).days + 1) // 7))
        actual = min(total, max(1, (date.today() - p.fecha_inicio).days // 7 + 1))
        return {"nombre": p.nombre, "semana": actual, "semanas": total,
                "avance": round(actual * 100 / total)}

    from datetime import timezone
    from zoneinfo import ZoneInfo
    zona = ZoneInfo(app.config.get("ZONA_HORARIA", "America/Bogota"))

    @app.template_filter("hora_local")
    def hora_local(dt, formato="%d/%m/%Y %H:%M"):
        """Las fechas se guardan en UTC; se muestran en hora de Colombia."""
        return dt.replace(tzinfo=timezone.utc).astimezone(zona).strftime(formato) if dt else ""

    @app.after_request
    def cabeceras_seguridad(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        # Las páginas contienen datos personales de menores: no cachear
        if resp.mimetype == "text/html":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    for codigo in (403, 404, 500):
        app.register_error_handler(
            codigo, lambda e, c=codigo: (render_template(f"errores/{c}.html"), c))

    from .cli import registrar_comandos
    registrar_comandos(app)

    return app
