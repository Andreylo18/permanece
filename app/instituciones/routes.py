"""Gestión de colegios (solo administrador general).

Al crear un colegio se crean también sus credenciales de acceso (rol "colegio").
Con ellas el colegio registra sus estudiantes y crea a sus docentes.
"""
import secrets

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy import func

from ..correo import avisar_invitacion
from ..extensions import db
from ..forms import InstitucionForm
from ..models import Estudiante, Institucion, Usuario
from ..permisos import admin_requerido

bp = Blueprint("instituciones", __name__)


@bp.route("/")
@admin_requerido
def listado():
    instituciones = db.session.execute(db.select(Institucion).order_by(Institucion.nombre)).scalars().all()

    def conteo(consulta):
        return dict(db.session.execute(consulta).all())

    estudiantes = conteo(db.select(Estudiante.institucion_id, func.count())
                         .where(Estudiante.activo == True)  # noqa: E712
                         .group_by(Estudiante.institucion_id))
    altos = conteo(db.select(Estudiante.institucion_id, func.count())
                   .where(Estudiante.activo == True, Estudiante.nivel_actual == "alto")  # noqa: E712
                   .group_by(Estudiante.institucion_id))
    docentes = conteo(db.select(Usuario.institucion_id, func.count())
                      .where(Usuario.rol == "docente").group_by(Usuario.institucion_id))
    return render_template("instituciones/listado.html", instituciones=instituciones,
                           estudiantes=estudiantes, altos=altos, docentes=docentes)


def _codigo_dane_en_uso(codigo, excluir_id=None):
    if not codigo:
        return False
    q = db.select(Institucion.id).filter(Institucion.codigo_dane == codigo)
    if excluir_id:
        q = q.filter(Institucion.id != excluir_id)
    return db.session.execute(q).first() is not None


def _email_en_uso(email):
    return db.session.execute(db.select(Usuario.id).filter(Usuario.email == email)).first() is not None


@bp.route("/nueva", methods=["GET", "POST"])
@admin_requerido
def nueva():
    form = InstitucionForm()
    if form.validate_on_submit():
        ok = True
        codigo = (form.codigo_dane.data or "").strip() or None
        if _codigo_dane_en_uso(codigo):
            form.codigo_dane.errors.append("Ya existe un colegio con este código DANE.")
            ok = False
        # Credenciales del colegio: obligatorias al crear
        email = (form.usuario_email.data or "").strip().lower()
        for campo in (form.usuario_nombre, form.usuario_email):
            if not campo.data:
                campo.errors = list(campo.errors) + ["Este campo es obligatorio."]
                ok = False
        if email and _email_en_uso(email):
            form.usuario_email.errors = list(form.usuario_email.errors) + ["Ya existe un usuario con este correo."]
            ok = False

        if ok:
            inst = Institucion(nombre=form.nombre.data.strip(), codigo_dane=codigo,
                               municipio=form.municipio.data, sector=form.sector.data,
                               direccion=form.direccion.data or None, telefono=form.telefono.data or None,
                               activa=form.activa.data)
            usuario = Usuario(nombre=form.usuario_nombre.data.strip(), email=email, rol="colegio",
                              institucion=inst)
            usuario.set_password(form.usuario_password.data or secrets.token_urlsafe(32))
            db.session.add_all([inst, usuario])
            db.session.commit()
            flash(f"Colegio {inst.nombre} creado con el usuario {email}.", "success")
            avisar_invitacion(usuario, current_user)
            return redirect(url_for("instituciones.listado"))
    if form.is_submitted() and form.errors:
        flash("Revisa los campos marcados.", "danger")
    return render_template("instituciones/formulario.html", form=form, institucion=None)


@bp.route("/<int:institucion_id>/editar", methods=["GET", "POST"])
@admin_requerido
def editar(institucion_id):
    inst = db.session.get(Institucion, institucion_id) or abort(404)
    form = InstitucionForm(obj=inst)
    if form.validate_on_submit():
        codigo = (form.codigo_dane.data or "").strip() or None
        if _codigo_dane_en_uso(codigo, excluir_id=inst.id):
            form.codigo_dane.errors.append("Ya existe un colegio con este código DANE.")
        else:
            inst.nombre, inst.codigo_dane = form.nombre.data.strip(), codigo
            inst.municipio, inst.sector = form.municipio.data, form.sector.data
            inst.direccion, inst.telefono = form.direccion.data or None, form.telefono.data or None
            inst.activa = form.activa.data
            db.session.commit()
            flash("Colegio actualizado." + ("" if inst.activa else
                  " Al estar inactivo, sus usuarios no pueden iniciar sesión."), "success")
            return redirect(url_for("instituciones.listado"))
    elif form.is_submitted():
        flash("Revisa los campos marcados.", "danger")
    return render_template("instituciones/formulario.html", form=form, institucion=inst)
