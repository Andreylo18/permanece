"""Administración de usuarios (RF-03).

- Administrador: gestiona cualquier usuario de cualquier colegio.
- Colegio: gestiona únicamente a los docentes de su propio colegio.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

import secrets

from ..correo import avisar_invitacion
from ..extensions import db
from ..forms import UsuarioForm
from ..models import ROLES, Institucion, Usuario
from ..permisos import gestion_usuarios_requerida, limitar_a_institucion

bp = Blueprint("usuarios", __name__)


@bp.route("/")
@gestion_usuarios_requerida
def listado():
    q = limitar_a_institucion(db.select(Usuario), Usuario.institucion_id)
    colegio = request.args.get("institucion", "")
    if current_user.es_admin and colegio.isdigit():
        q = q.filter(Usuario.institucion_id == int(colegio))
    usuarios = db.session.execute(q.order_by(Usuario.rol, Usuario.nombre)).scalars().all()
    instituciones = (db.session.execute(db.select(Institucion).order_by(Institucion.nombre)).scalars().all()
                     if current_user.es_admin else [])
    return render_template("usuarios/listado.html", usuarios=usuarios, instituciones=instituciones)


def _email_en_uso(email, excluir_id=None):
    q = db.select(Usuario.id).filter(Usuario.email == email)
    if excluir_id:
        q = q.filter(Usuario.id != excluir_id)
    return db.session.execute(q).first() is not None


def _preparar(form):
    """Opciones de rol y colegio según quién crea el usuario."""
    if current_user.es_admin:
        form.rol.choices = list(ROLES)
        colegios = db.session.execute(db.select(Institucion).order_by(Institucion.nombre)).scalars().all()
        form.institucion_id.choices = [(0, "— Ninguno (solo administrador general) —")] + \
            [(i.id, f"{i.nombre} · {i.municipio}") for i in colegios]
    else:  # colegio: solo crea docentes de su colegio
        form.rol.choices = [("docente", "Docente / orientador")]
        form.rol.data = "docente"
        form.institucion_id.choices = [(current_user.institucion_id, current_user.institucion.nombre)]
        form.institucion_id.data = current_user.institucion_id


def _validar_rol_colegio(form):
    """Admin sin colegio; colegio y docente siempre con colegio."""
    ids = {c[0] for c in form.institucion_id.choices}
    if form.institucion_id.data not in ids:
        form.institucion_id.errors = list(form.institucion_id.errors) + ["Selecciona un colegio válido."]
        return False
    if form.rol.data == "admin" and form.institucion_id.data:
        form.institucion_id.errors = list(form.institucion_id.errors) + [
            "El administrador general no pertenece a un colegio."]
        return False
    if form.rol.data != "admin" and not form.institucion_id.data:
        form.institucion_id.errors = list(form.institucion_id.errors) + [
            "Los usuarios de colegio y los docentes deben pertenecer a un colegio."]
        return False
    return True


@bp.route("/nuevo", methods=["GET", "POST"])
@gestion_usuarios_requerida
def nuevo():
    form = UsuarioForm()
    _preparar(form)
    if request.method == "GET" and current_user.es_admin and request.args.get("institucion", "").isdigit():
        form.institucion_id.data = int(request.args["institucion"])
    if form.validate_on_submit() and _validar_rol_colegio(form):
        email = form.email.data.strip().lower()
        if _email_en_uso(email):
            form.email.errors.append("Ya existe un usuario con este correo.")
        else:
            u = Usuario(nombre=form.nombre.data.strip(), email=email, rol=form.rol.data,
                        institucion_id=form.institucion_id.data or None, activo=form.activo.data)
            # Sin contraseña: la persona la define desde el enlace del correo de invitación
            u.set_password(form.password.data or secrets.token_urlsafe(32))
            db.session.add(u)
            db.session.commit()
            flash(f"Usuario {email} creado.", "success")
            avisar_invitacion(u, current_user)
            return redirect(url_for("usuarios.listado"))
    return render_template("usuarios/formulario.html", form=form, usuario=None)


def _usuario_editable(usuario_id):
    u = db.session.get(Usuario, usuario_id) or abort(404)
    if current_user.es_admin:
        return u
    # El colegio solo edita docentes de su propio colegio
    if u.institucion_id != current_user.institucion_id:
        abort(404)
    if u.rol != "docente":
        abort(403)
    return u


@bp.route("/<int:usuario_id>/reenviar", methods=["POST"])
@gestion_usuarios_requerida
def reenviar_invitacion(usuario_id):
    u = _usuario_editable(usuario_id)
    avisar_invitacion(u, current_user)
    return redirect(url_for("usuarios.listado"))


@bp.route("/<int:usuario_id>/editar", methods=["GET", "POST"])
@gestion_usuarios_requerida
def editar(usuario_id):
    u = _usuario_editable(usuario_id)
    form = UsuarioForm(obj=u)
    _preparar(form)
    if request.method == "GET" and current_user.es_admin:
        form.institucion_id.data = u.institucion_id or 0
    if form.validate_on_submit() and _validar_rol_colegio(form):
        email = form.email.data.strip().lower()
        es_yo = u.id == current_user.id
        if _email_en_uso(email, excluir_id=u.id):
            form.email.errors.append("Ya existe un usuario con este correo.")
        elif es_yo and (form.rol.data != u.rol or not form.activo.data):
            flash("No puedes cambiar tu propio rol ni desactivarte.", "danger")
        else:
            u.nombre, u.email, u.rol, u.activo = form.nombre.data.strip(), email, form.rol.data, form.activo.data
            u.institucion_id = form.institucion_id.data or None
            if form.password.data:
                u.set_password(form.password.data)
            db.session.commit()
            flash("Usuario actualizado.", "success")
            return redirect(url_for("usuarios.listado"))
    return render_template("usuarios/formulario.html", form=form, usuario=u)
