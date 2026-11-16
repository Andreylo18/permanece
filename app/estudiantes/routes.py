"""Gestión de estudiantes y factores de riesgo (RF-05 a RF-11, RF-15)."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, or_, true

from ..extensions import db
from ..forms import EstudianteForm, FactoresForm, ImportarEstudiantesForm
from ..academico import periodo_activo, periodos_de, recalcular_estudiante, resumen_academico
from ..models import GRADOS, MUNICIPIOS_SABANA_CENTRO, Estudiante, Institucion, Periodo
from ..documentos import normalizar as normalizar_documento
from ..importacion import COLUMNAS, MAX_FILAS, leer_estudiantes, plantilla
from ..permisos import (gestion_estudiantes_requerida, limitar_a_institucion, limitar_estudiantes,
                        verificar_estudiante)
from ..riesgo import calcular_riesgo

bp = Blueprint("estudiantes", __name__)


def _get_estudiante(estudiante_id):
    est = db.session.get(Estudiante, estudiante_id)
    if est is None:
        abort(404)
    verificar_estudiante(est)  # otro colegio, o curso que el docente no dicta -> 404
    return est


def instituciones_visibles(solo_activas=False):
    """Colegios que el usuario puede ver (todos para el admin, el suyo para los demás)."""
    q = limitar_a_institucion(db.select(Institucion), Institucion.id)
    if solo_activas:
        q = q.filter(Institucion.activa == true())
    return db.session.execute(q.order_by(Institucion.nombre)).scalars().all()


def consulta_filtrada(args):
    """Aplica los filtros comunes (listado y dashboard) — RF-11."""
    q = db.select(Estudiante).join(Estudiante.institucion)
    q = limitar_estudiantes(q)   # colegio del usuario; docente: solo sus cursos

    colegio = args.get("institucion", "")
    if colegio.isdigit():
        q = q.filter(Estudiante.institucion_id == int(colegio))

    if args.get("inactivos") != "1":
        q = q.filter(Estudiante.activo == true())

    texto = (args.get("q") or "").strip()
    if texto:
        patron = f"%{texto}%"
        q = q.filter(or_(Estudiante.nombres.ilike(patron), Estudiante.apellidos.ilike(patron),
                         Estudiante.documento.ilike(f"%{normalizar_documento(texto)}%")))

    grado = args.get("grado", "")
    if grado.isdigit() and int(grado) in GRADOS:
        q = q.filter(Estudiante.grado == int(grado))

    nivel = args.get("nivel", "")
    if nivel in ("bajo", "medio", "alto"):
        q = q.filter(Estudiante.nivel_actual == nivel)
    elif nivel == "sin":
        q = q.filter(Estudiante.nivel_actual.is_(None))

    municipio = args.get("municipio", "")
    if municipio in MUNICIPIOS_SABANA_CENTRO:
        q = q.filter(Institucion.municipio == municipio)

    if args.get("incompletos") == "1":
        q = q.filter(Estudiante.datos_incompletos == true())
    return q


@bp.route("/")
@login_required
def listado():
    q = consulta_filtrada(request.args)
    orden = request.args.get("orden", "riesgo")
    if orden == "nombre":
        q = q.order_by(Estudiante.apellidos, Estudiante.nombres)
    elif orden == "grado":
        q = q.order_by(Estudiante.grado, Estudiante.apellidos)
    else:  # mayor riesgo primero; sin clasificar al final
        sin_puntaje = case((Estudiante.puntaje_actual.is_(None), 1), else_=0)  # sin clasificar al final
        q = q.order_by(sin_puntaje, Estudiante.puntaje_actual.desc(),
                       Estudiante.apellidos)

    pagina = db.paginate(q, page=request.args.get("page", 1, type=int),
                         per_page=current_app.config["ITEMS_POR_PAGINA"], error_out=False)
    return render_template("estudiantes/listado.html", pagina=pagina, grados=GRADOS,
                           municipios=MUNICIPIOS_SABANA_CENTRO, instituciones=instituciones_visibles())


def _documento_duplicado(documento, institucion_id, excluir_id=None):
    q = db.select(Estudiante.id).filter(Estudiante.documento == documento,
                                        Estudiante.institucion_id == institucion_id)
    if excluir_id:
        q = q.filter(Estudiante.id != excluir_id)
    return db.session.execute(q).first() is not None


def _preparar_colegio(form):
    """Admin elige el colegio; un colegio siempre registra en el suyo."""
    if current_user.es_admin:
        form.institucion_id.choices = [(i.id, f"{i.nombre} · {i.municipio}")
                                       for i in instituciones_visibles(solo_activas=True)]
    else:
        form.institucion_id.choices = [(current_user.institucion_id, current_user.institucion.nombre)]
        form.institucion_id.data = current_user.institucion_id


def _colegio_valido(form):
    ids = {c[0] for c in form.institucion_id.choices}
    if form.institucion_id.data not in ids:
        form.institucion_id.errors = list(form.institucion_id.errors) + ["Selecciona un colegio válido."]
        return False
    return True


@bp.route("/plantilla.xlsx")
@gestion_estudiantes_requerida
def plantilla_excel():
    return send_file(plantilla(), as_attachment=True, download_name="plantilla_estudiantes_permanece.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/importar", methods=["GET", "POST"])
@gestion_estudiantes_requerida
def importar():
    form = ImportarEstudiantesForm()
    _preparar_colegio(form)
    resultado = None
    if form.validate_on_submit() and _colegio_valido(form):
        inst_id = form.institucion_id.data
        existentes = set(db.session.execute(
            db.select(Estudiante.documento).filter_by(institucion_id=inst_id)).scalars())
        resultado = leer_estudiantes(form.archivo.data, existentes, form.omitir_existentes.data)
        if not resultado.errores and not resultado.filas:
            flash("No se importó nada: el archivo no tiene estudiantes nuevos." if resultado.omitidos
                  else "El archivo no tiene estudiantes (llena desde la fila 2).", "warning")
        elif not resultado.errores:
            db.session.add_all([Estudiante(institucion_id=inst_id, creado_por_id=current_user.id, **datos)
                                for datos in resultado.filas])
            db.session.commit()
            extra = f" Se omitieron {resultado.omitidos} que ya estaban registrados." if resultado.omitidos else ""
            flash(f"Se importaron {len(resultado.filas)} estudiante(s).{extra}", "success")
            return redirect(url_for("estudiantes.listado", institucion=inst_id if current_user.es_admin else None))
        else:
            flash("No se guardó ningún estudiante. Corrige las filas indicadas y vuelve a subir el archivo.", "danger")
    elif form.is_submitted():
        flash("Revisa los campos marcados.", "danger")
    return render_template("estudiantes/importar.html", form=form, resultado=resultado, columnas=COLUMNAS,
                           max_filas=MAX_FILAS)


@bp.route("/nuevo", methods=["GET", "POST"])
@gestion_estudiantes_requerida
def nuevo():
    form = EstudianteForm()
    _preparar_colegio(form)
    if not form.institucion_id.choices:
        flash("Primero debe existir al menos un colegio activo.", "warning")
        return redirect(url_for("instituciones.nueva") if current_user.es_admin else url_for("estudiantes.listado"))
    if form.validate_on_submit() and _colegio_valido(form):
        documento = normalizar_documento(form.documento.data)
        if _documento_duplicado(documento, form.institucion_id.data):
            form.documento.errors.append("Ya existe un estudiante con este documento en el colegio.")
        else:
            est = Estudiante(creado_por_id=current_user.id)
            form.populate_obj(est)
            est.documento = documento
            est.nombres, est.apellidos = est.nombres.strip(), est.apellidos.strip()
            db.session.add(est)
            db.session.commit()
            flash("Estudiante registrado. Sus notas y asistencia las registran los docentes de su curso.", "success")
            return redirect(url_for("estudiantes.detalle", estudiante_id=est.id))
    elif form.is_submitted():
        flash("Revisa los campos marcados.", "danger")
    return render_template("estudiantes/formulario.html", form=form, estudiante=None)


@bp.route("/<int:estudiante_id>/editar", methods=["GET", "POST"])
@gestion_estudiantes_requerida
def editar(estudiante_id):
    est = _get_estudiante(estudiante_id)
    form = EstudianteForm(obj=est)
    _preparar_colegio(form)
    if current_user.es_admin and est.institucion_id not in {c[0] for c in form.institucion_id.choices}:
        form.institucion_id.choices.append((est.institucion_id, est.institucion.nombre))  # colegio inactivo
    if form.validate_on_submit() and _colegio_valido(form):
        documento = normalizar_documento(form.documento.data)
        if _documento_duplicado(documento, form.institucion_id.data, excluir_id=est.id):
            form.documento.errors.append("Ya existe otro estudiante con este documento en el colegio.")
        else:
            form.populate_obj(est)
            est.documento = documento
            db.session.commit()
            flash("Cambios guardados.", "success")
            return redirect(url_for("estudiantes.detalle", estudiante_id=est.id))
    elif form.is_submitted():
        flash("Revisa los campos marcados.", "danger")
    return render_template("estudiantes/formulario.html", form=form, estudiante=est)


def _periodo_elegido(est):
    """Periodo pedido en ?periodo=<id> (del colegio del estudiante) o el activo."""
    pid = request.args.get("periodo", type=int)
    if pid:
        p = db.session.get(Periodo, pid)
        if p is not None and p.institucion_id == est.institucion_id:
            return p
    return periodo_activo(est.institucion_id)


@bp.route("/<int:estudiante_id>")
@login_required
def detalle(estudiante_id):
    est = _get_estudiante(estudiante_id)
    periodo = _periodo_elegido(est)
    reg = est.registro_de(periodo.nombre) if periodo else est.registro_vigente
    resultado = reg.resultado() if reg else None
    academico = resumen_academico(est, periodo)
    return render_template("estudiantes/detalle.html", est=est, registro=reg, resultado=resultado,
                           periodo=periodo, periodos=periodos_de(est.institucion_id), academico=academico)


@bp.route("/<int:estudiante_id>/factores", methods=["GET", "POST"])
@login_required
def factores(estudiante_id):
    """Factores no académicos + recálculo del riesgo en el periodo activo (RF-08, RF-09).

    Asistencia, promedio y reprobadas NO se digitan aquí: salen de las notas y
    la asistencia que registran los docentes.
    """
    est = _get_estudiante(estudiante_id)
    periodo = periodo_activo(est.institucion_id)
    if periodo is None:
        flash("El colegio no tiene un periodo activo. La coordinación debe crearlo en Académico → Periodos.", "warning")
        return redirect(url_for("estudiantes.detalle", estudiante_id=est.id))
    reg = est.registro_de(periodo.nombre)
    form = FactoresForm()
    if request.method == "GET" and reg is not None:
        form.apoyo_familiar.data = reg.apoyo_familiar or ""
        form.reporte_activo.data = "" if reg.reporte_activo is None else ("1" if reg.reporte_activo else "0")
        form.observaciones.data = reg.observaciones

    if form.validate_on_submit():
        resultado, paso_a_alto = recalcular_estudiante(
            est, periodo, usuario=current_user,
            apoyo_familiar=form.apoyo_familiar.data or None,
            reporte_activo=None if form.reporte_activo.data == "" else form.reporte_activo.data == "1",
            observaciones=form.observaciones.data or None)
        db.session.commit()
        msg = f"Riesgo recalculado: {resultado.nivel.upper()} ({resultado.puntaje}/100)."
        if resultado.datos_incompletos:
            msg += " Hay datos sin registrar: el caso queda marcado para revisión."
        flash(msg, "warning" if resultado.nivel != "bajo" or resultado.datos_incompletos else "success")
        if paso_a_alto:
            flash("Se notificó a la coordinación" + (" y al acudiente." if est.email_acudiente else "."), "info")
        return redirect(url_for("estudiantes.detalle", estudiante_id=est.id))
    elif form.is_submitted():
        flash("Revisa los campos marcados.", "danger")

    return render_template("estudiantes/factores.html", form=form, est=est, periodo=periodo,
                           academico=resumen_academico(est, periodo))


@bp.route("/vista-previa-riesgo", methods=["POST"])
@login_required
def vista_previa_riesgo():
    """Cálculo en vivo para el formulario de factores (no guarda nada)."""
    def num(nombre, tipo=float):
        v = (request.form.get(nombre) or "").replace(",", ".").strip()
        try:
            return tipo(v) if v != "" else None
        except ValueError:
            return None
    rep = request.form.get("reporte_activo", "")
    r = calcular_riesgo(num("asistencia_pct"), num("asignaturas_reprobadas", int), num("promedio"),
                        request.form.get("apoyo_familiar") or None,
                        None if rep == "" else rep == "1")
    return {"puntaje": r.puntaje, "nivel": r.nivel, "incompleto": r.datos_incompletos,
            "factores": [f.nombre for f in r.factores_que_aplican]}


@bp.route("/<int:estudiante_id>/estado", methods=["POST"])
@gestion_estudiantes_requerida
def cambiar_estado(estudiante_id):
    """Desactiva/reactiva (no se borra: se conserva el historial)."""
    est = _get_estudiante(estudiante_id)
    est.activo = not est.activo
    db.session.commit()
    flash("Estudiante " + ("reactivado." if est.activo else "desactivado."), "info")
    return redirect(url_for("estudiantes.detalle", estudiante_id=est.id))
