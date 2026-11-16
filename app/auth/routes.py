"""Inicio y cierre de sesión (RF-01, RF-02)."""
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..correo import correo_configurado, enviar_recuperacion, usuario_desde_token
from ..forms import CambiarContrasenaForm, DefinirContrasenaForm, LoginForm, OlvideForm, PerfilForm
from ..models import Usuario

bp = Blueprint("auth", __name__)


def _destino_seguro(destino):
    """Evita redirecciones abiertas: solo rutas internas."""
    if not destino:
        return None
    partes = urlsplit(destino)
    if partes.netloc or partes.scheme or not destino.startswith("/"):
        return None
    return destino


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.inicio"))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        usuario = db.session.execute(db.select(Usuario).filter_by(email=email)).scalar_one_or_none()
        # Mensaje genérico: no revelar si el correo existe
        if usuario is None or not usuario.check_password(form.password.data):
            flash("Correo o contraseña incorrectos.", "danger")
        elif not usuario.activo:
            flash("Tu usuario está desactivado. Contacta al administrador.", "danger")
        elif usuario.institucion is not None and not usuario.institucion.activa:
            flash("Tu colegio está desactivado en PERMANECE. Contacta al administrador.", "danger")
        else:
            session.clear()  # evita fijación de sesión
            login_user(usuario, remember=form.recordar.data)
            session.permanent = True
            flash(f"Bienvenido, {usuario.nombre}.", "success")
            return redirect(_destino_seguro(request.args.get("next")) or url_for("dashboard.inicio"))
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/olvide-mi-contrasena", methods=["GET", "POST"])
def olvide():
    form = OlvideForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        usuario = db.session.execute(db.select(Usuario).filter_by(email=email)).scalar_one_or_none()
        if usuario is not None and usuario.is_active:
            enviar_recuperacion(usuario)
        # Mismo mensaje exista o no el correo: no se revela quién tiene cuenta
        flash("Si el correo está registrado, te enviamos un enlace para restablecer la contraseña. "
              "Revisa también la carpeta de spam.", "info")
        if not correo_configurado():
            flash("Modo desarrollo: el envío de correos no está configurado (BREVO_API_KEY).", "warning")
        return redirect(url_for("auth.login"))
    return render_template("auth/olvide.html", form=form)


@bp.route("/definir-contrasena/<token>", methods=["GET", "POST"])
def definir_contrasena(token):
    """Sirve para la invitación inicial y para restablecer la contraseña."""
    usuario = usuario_desde_token(token)
    if usuario is None:
        flash("El enlace no es válido o ya expiró. Solicita uno nuevo.", "danger")
        return redirect(url_for("auth.olvide"))
    form = DefinirContrasenaForm()
    if form.validate_on_submit():
        usuario.set_password(form.password.data)
        db.session.commit()
        flash("Contraseña guardada. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/definir.html", form=form, usuario=usuario)


@bp.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    """Mis datos y cambio de contraseña (cualquier rol)."""
    # Cada formulario solo lee el POST si fue el que se envió (así el otro no se vacía)
    enviado = request.form if request.method == "POST" else None
    datos = PerfilForm(prefix="d", obj=current_user,
                       formdata=enviado if enviado and "d-guardar_datos" in enviado else None)
    clave = CambiarContrasenaForm(prefix="c", formdata=enviado if enviado and "c-cambiar_clave" in enviado else None)

    if datos.guardar_datos.data and datos.validate_on_submit():
        email = datos.email.data.strip().lower()
        otro = db.session.execute(db.select(Usuario.id).filter(Usuario.email == email,
                                                               Usuario.id != current_user.id)).first()
        if not current_user.check_password(datos.password_actual.data):
            datos.password_actual.errors.append("La contraseña actual no es correcta.")
        elif otro:
            datos.email.errors.append("Ese correo ya lo usa otro usuario.")
        else:
            current_user.nombre, current_user.email = datos.nombre.data.strip(), email
            db.session.commit()
            flash("Tus datos se guardaron.", "success")
            return redirect(url_for("auth.perfil"))

    elif clave.cambiar_clave.data and clave.validate_on_submit():
        if not current_user.check_password(clave.actual.data):
            clave.actual.errors.append("La contraseña actual no es correcta.")
        else:
            current_user.set_password(clave.nueva.data)   # invalida enlaces de invitación/recuperación pendientes
            db.session.commit()
            flash("Contraseña cambiada. Úsala la próxima vez que ingreses.", "success")
            return redirect(url_for("auth.perfil"))

    return render_template("auth/perfil.html", datos=datos, clave=clave)
