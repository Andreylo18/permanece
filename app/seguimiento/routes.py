"""Registro de intervenciones y cronología (RF-12, RF-13)."""
from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..correo import enviar
from ..extensions import db
from ..forms import IntervencionForm
from ..models import Estudiante, Intervencion
from ..permisos import verificar_institucion

bp = Blueprint("seguimiento", __name__)


@bp.route("/<int:estudiante_id>/intervenciones/nueva", methods=["GET", "POST"])
@login_required
def nueva(estudiante_id):
    est = db.session.get(Estudiante, estudiante_id) or abort(404)
    verificar_institucion(est.institucion_id)
    form = IntervencionForm()
    if form.validate_on_submit():
        inter = Intervencion(estudiante=est, responsable_id=current_user.id, fecha=form.fecha.data,
                             tipo=form.tipo.data, descripcion=form.descripcion.data,
                             compromisos=form.compromisos.data or None, estado=form.estado.data)
        db.session.add(inter)
        db.session.commit()
        flash("Intervención registrada.", "success")
        if form.notificar_acudiente.data and est.email_acudiente:
            if enviar(est.email_acudiente, f"{est.institucion.nombre}: seguimiento de {est.nombres}",
                      "intervencion_acudiente", est=est, inter=inter):
                flash(f"Se envió el resumen al acudiente ({est.email_acudiente}).", "info")
            else:
                flash("No se pudo enviar el correo al acudiente (envío no configurado o con error).", "warning")
        return redirect(url_for("estudiantes.detalle", estudiante_id=est.id, _anchor="cronologia"))
    elif form.is_submitted():
        flash("Revisa los campos marcados.", "danger")
    return render_template("seguimiento/formulario.html", form=form, est=est)


@bp.route("/intervenciones/<int:intervencion_id>/estado", methods=["POST"])
@login_required
def cambiar_estado(intervencion_id):
    inter = db.session.get(Intervencion, intervencion_id) or abort(404)
    verificar_institucion(inter.estudiante.institucion_id)
    # Pueden cerrar/reabrir: el responsable, la coordinación del colegio o el administrador
    if not (current_user.es_admin or current_user.es_colegio or inter.responsable_id == current_user.id):
        abort(403)
    inter.estado = "cerrada" if inter.estado == "abierta" else "abierta"
    db.session.commit()
    flash(f"Intervención marcada como {inter.estado}.", "info")
    return redirect(url_for("estudiantes.detalle", estudiante_id=inter.estudiante_id, _anchor="cronologia"))
