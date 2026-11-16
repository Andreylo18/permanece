"""Comandos de consola:

    flask --app run init-db          crea las tablas (y el admin inicial si se definen
                                     ADMIN_EMAIL y ADMIN_PASSWORD en el entorno)
    flask --app run crear-admin      crea un administrador (pide los datos)
    flask --app run seed             carga datos FICTICIOS de prueba (RNF-02)
"""
import os
import random
from datetime import date, timedelta

import click

from .extensions import db
from .models import (TIPOS_INTERVENCION, Actividad, Asignacion, Asistencia, Estudiante, Institucion,
                     Intervencion, Materia, Nota, Periodo, RegistroFactores, SesionClase, Usuario)


def registrar_comandos(app):

    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        click.echo("Tablas listas.")
        email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        clave = os.environ.get("ADMIN_PASSWORD", "")
        hay_admin = db.session.execute(db.select(Usuario.id).filter_by(rol="admin")).first()
        if email and clave and not hay_admin:
            u = Usuario(nombre=os.environ.get("ADMIN_NOMBRE", "Administración PERMANECE"), email=email, rol="admin")
            u.set_password(clave)
            db.session.add(u)
            db.session.commit()
            click.echo(f"Administrador inicial creado: {email}")

    @app.cli.command("crear-admin")
    @click.option("--nombre", prompt="Nombre")
    @click.option("--email", prompt="Correo")
    @click.option("--password", prompt="Contraseña", hide_input=True, confirmation_prompt=True)
    def crear_admin(nombre, email, password):
        if len(password) < 8:
            raise click.ClickException("La contraseña debe tener al menos 8 caracteres.")
        email = email.strip().lower()
        if db.session.execute(db.select(Usuario).filter_by(email=email)).scalar():
            raise click.ClickException("Ese correo ya existe.")
        u = Usuario(nombre=nombre, email=email, rol="admin")
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        click.echo(f"Administrador {email} creado.")

    @app.cli.command("seed")
    @click.option("--n", default=90, help="Número de estudiantes ficticios.")
    @click.option("--reset", is_flag=True, help="Borra y recrea todas las tablas antes. ¡Elimina los datos!")
    def seed(n, reset):
        if reset:
            click.confirm("Esto BORRA todos los datos de la base configurada. ¿Continuar?", abort=True)
            db.drop_all()
        db.create_all()
        sembrar_datos(n)
        click.echo(f"Datos ficticios cargados ({n} estudiantes, con notas y asistencia).")
        click.echo("Usuarios demo (contraseña entre paréntesis):")
        click.echo("  Administrador general: admin@permanece.example (Admin2026*)")
        for slug, nombre, _ in COLEGIOS_DEMO:
            click.echo(f"  {nombre}: colegio {slug}@permanece.example (Colegio2026*) · "
                       f"docentes docente.{slug}@ y docente2.{slug}@permanece.example (Docente2026*)")


NOMBRES = ["Valentina", "Santiago", "Mariana", "Samuel", "Isabella", "Matías", "Sofía", "Emiliano",
           "Luciana", "Tomás", "Gabriela", "Juan José", "Salomé", "Martín", "Antonella", "Jerónimo",
           "Daniela", "Nicolás", "Sara", "Andrés", "Laura", "David", "Manuela", "Felipe"]
APELLIDOS = ["Rodríguez", "Gómez", "Martínez", "Rincón", "Forero", "Castañeda", "Moreno", "Cárdenas",
             "Pinzón", "Garzón", "Rojas", "Bernal", "Sánchez", "Ramírez", "Torres", "Peña", "Ávila",
             "Cruz", "Vargas", "Suárez", "Beltrán", "Quintero"]
MATERIAS_DEMO = ["Matemáticas", "Lengua Castellana", "Ciencias Naturales", "Ciencias Sociales", "Inglés",
                 "Educación Física"]
ACTIVIDADES_DEMO = [("Taller", 30), ("Quiz", 20), ("Examen", 50)]

# (identificador, nombre, municipio) — colegios FICTICIOS
COLEGIOS_DEMO = [
    ("sangabriel", "I.E.D. Ficticia San Gabriel", "Chía"),
    ("lasabana", "Colegio Ficticio La Sabana", "Zipaquirá"),
    ("elprado", "I.E.D. Ficticia El Prado", "Cajicá"),
]


def _usuario(email, nombre, rol, clave, institucion=None):
    u = db.session.execute(db.select(Usuario).filter_by(email=email)).scalar()
    if not u:
        u = Usuario(email=email, nombre=nombre, rol=rol, institucion=institucion)
        u.set_password(clave)
        db.session.add(u)
    return u


def _institucion(nombre, municipio):
    i = db.session.execute(db.select(Institucion).filter_by(nombre=nombre)).scalar()
    if not i:
        i = Institucion(nombre=nombre, municipio=municipio, sector="oficial")
        db.session.add(i)
    return i


def _dias_habiles(inicio, fin, cantidad, rnd):
    dias = [inicio + timedelta(d) for d in range((fin - inicio).days + 1)]
    dias = [d for d in dias if d.weekday() < 5]
    return sorted(rnd.sample(dias, min(cantidad, len(dias))))


def sembrar_datos(n=90, semilla=2026):
    """Colegios, docentes, materias, cursos, estudiantes, notas y asistencia ficticios.

    Pensado para una base remota (Neon): arma todo en memoria y lo inserta por
    lotes, con pocos viajes a la base. El riesgo se calcula con las MISMAS reglas
    de la app (academico.py / riesgo.py) a partir de las notas y la asistencia
    generadas; una prueba verifica que coincide con recalcular_estudiante().
    """
    from .academico import NOTA_APROBATORIA

    rnd = random.Random(semilla)
    _usuario("admin@permanece.example", "Administración PERMANECE", "admin", "Admin2026*")
    hoy = date.today()
    inicio_p = hoy - timedelta(days=45)
    fin_p = hoy + timedelta(days=30)
    contexto = []
    for slug, nombre, municipio in COLEGIOS_DEMO:
        inst = _institucion(nombre, municipio)
        coord = _usuario(f"{slug}@permanece.example", f"Coordinación {nombre}", "colegio", "Colegio2026*", inst)
        docs = [_usuario(f"docente.{slug}@permanece.example", "Docente Ciencias (demo)", "docente", "Docente2026*", inst),
                _usuario(f"docente2.{slug}@permanece.example", "Docente Humanidades (demo)", "docente", "Docente2026*", inst)]
        contexto.append([inst, coord, docs, None, None])
    db.session.flush()

    for c in contexto:
        inst = c[0]
        periodo = db.session.execute(db.select(Periodo).filter_by(institucion_id=inst.id, activo=True)).scalar()
        if periodo is None:
            db.session.add(Periodo(institucion_id=inst.id, nombre=f"{hoy.year}-P3", activo=False,
                                   fecha_inicio=inicio_p - timedelta(days=80), fecha_fin=inicio_p - timedelta(days=10)))
            periodo = Periodo(institucion_id=inst.id, nombre=f"{hoy.year}-P4", fecha_inicio=inicio_p,
                              fecha_fin=fin_p, activo=True)
            db.session.add(periodo)
        existentes_m = {m.nombre: m for m in db.session.execute(
            db.select(Materia).filter_by(institucion_id=inst.id)).scalars()}
        materias = []
        for m in MATERIAS_DEMO:
            if m not in existentes_m:
                existentes_m[m] = Materia(institucion_id=inst.id, nombre=m)
                db.session.add(existentes_m[m])
            materias.append(existentes_m[m])
        c[3], c[4] = periodo, materias
    db.session.flush()

    # ---- Estudiantes (un solo lote)
    base_doc = db.session.execute(db.select(db.func.count(Estudiante.id))).scalar()
    perfiles = {}
    for i in range(n):
        inst, coord, docs, periodo, materias = contexto[i % len(contexto)]
        apellido = rnd.choice(APELLIDOS)
        est = Estudiante(
            institucion_id=inst.id, documento=f"FIC{base_doc + i + 1:06d}",
            nombres=rnd.choice(NOMBRES), apellidos=f"{apellido} {rnd.choice(APELLIDOS)}",
            grado=rnd.randint(6, 11), grupo=rnd.choice(["A", "B"]),
            acudiente=f"{rnd.choice(NOMBRES)} {apellido}",
            telefono_acudiente=f"300{rnd.randint(1000000, 9999999)}",
            email_acudiente=f"acudiente{base_doc + i + 1}@ejemplo.example" if rnd.random() < 0.7 else None,
            creado_por_id=coord.id,
        )
        db.session.add(est)
        # 0 = va bien, 1 = algo de dificultad, 2 = en riesgo
        perfiles[est] = rnd.choices([0, 1, 2], weights=[55, 25, 20])[0]
    db.session.flush()

    # ---- Cursos, actividades, notas y asistencia (en memoria; se insertan por lotes)
    asignaciones = {(a.materia_id, a.grado, a.grupo): a for a in db.session.execute(db.select(Asignacion)).scalars()}
    # acumuladores por estudiante: materia -> [suma ponderada, % calificado] ; conteo de asistencia
    notas_est = {e: {} for e in perfiles}
    asis_est = {e: {"presente": 0, "tarde": 0, "ausente": 0, "excusa": 0} for e in perfiles}
    for inst, coord, docs, periodo, materias in contexto:
        cursos = sorted({(e.grado, e.grupo) for e in perfiles if e.institucion_id == inst.id})
        for grado, grupo in cursos:
            alumnos = [e for e in perfiles if e.institucion_id == inst.id and e.grado == grado and e.grupo == grupo]
            for k, mat in enumerate(materias):
                asig = asignaciones.get((mat.id, grado, grupo))
                if asig is None:
                    asig = Asignacion(institucion_id=inst.id, materia_id=mat.id, docente_id=docs[k % 2].id,
                                      grado=grado, grupo=grupo)
                    db.session.add(asig)
                    asignaciones[(mat.id, grado, grupo)] = asig
                calificar_examen = rnd.random() < 0.6
                for nombre, pct in ACTIVIDADES_DEMO:
                    act = Actividad(asignacion=asig, periodo_id=periodo.id, nombre=nombre, porcentaje=pct)
                    db.session.add(act)
                    if nombre == "Examen" and not calificar_examen:
                        continue
                    for e in alumnos:
                        media = {0: 4.0, 1: 3.2, 2: 2.5}[perfiles[e]]
                        v = round(max(0.0, min(5.0, rnd.gauss(media, 0.6))), 1)
                        act.notas.append(Nota(estudiante_id=e.id, valor=v))
                        acc = notas_est[e].setdefault(mat.id, [0.0, 0])
                        acc[0] += v * pct
                        acc[1] += pct
                for fecha in _dias_habiles(periodo.fecha_inicio, min(hoy, periodo.fecha_fin), 8, rnd):
                    ses = SesionClase(asignacion=asig, periodo_id=periodo.id, fecha=fecha)
                    db.session.add(ses)
                    for e in alumnos:
                        p_falla = {0: 0.04, 1: 0.12, 2: 0.3}[perfiles[e]]
                        r = rnd.random()
                        estado = ("ausente" if r < p_falla else "excusa" if r < p_falla + 0.03
                                  else "tarde" if r < p_falla + 0.08 else "presente")
                        ses.asistencias.append(Asistencia(estudiante_id=e.id, estado=estado))
                        asis_est[e][estado] += 1

    # ---- Riesgo: mismas reglas que academico.resumen_academico()
    for e, perfil in perfiles.items():
        inst, coord, docs, periodo, materias = next(c for c in contexto if c[0].id == e.institucion_id)
        notas_mat = [round(s_ / p_, 2) for s_, p_ in notas_est[e].values() if p_]
        promedio = round(sum(notas_mat) / len(notas_mat), 2) if notas_mat else None
        reprobadas = sum(1 for x in notas_mat if x < NOTA_APROBATORIA) if notas_mat else None
        a = asis_est[e]
        base = sum(a.values()) - a["excusa"]
        asistencia = round((a["presente"] + a["tarde"]) * 100 / base, 1) if base > 0 else None
        apoyo = rnd.choice(["insuficiente", "parcial"] if perfil == 2 else ["adecuado", "parcial"])
        if rnd.random() < 0.1:
            apoyo = None   # algunos casos quedan con datos incompletos
        ant = RegistroFactores(estudiante=e, periodo=f"{hoy.year}-P3",
                               asistencia_pct=round(rnd.uniform(70, 99), 1),
                               asignaturas_reprobadas=rnd.randint(0, 4 if perfil == 2 else 2),
                               promedio=round(rnd.uniform(2.5, 4.5), 2),
                               apoyo_familiar=rnd.choice(["adecuado", "parcial", "insuficiente"]),
                               reporte_activo=rnd.random() < 0.15)
        ant.recalcular()
        actual = RegistroFactores(estudiante=e, periodo=periodo.nombre, registrado_por_id=docs[0].id,
                                  asistencia_pct=asistencia, promedio=promedio, asignaturas_reprobadas=reprobadas,
                                  apoyo_familiar=apoyo, reporte_activo=rnd.random() < (0.5 if perfil == 2 else 0.08))
        r = actual.recalcular()
        db.session.add_all([ant, actual])
        e.puntaje_actual, e.nivel_actual, e.datos_incompletos = r.puntaje, r.nivel, r.datos_incompletos

        if e.nivel_actual in ("medio", "alto") and rnd.random() < 0.6:
            for k in range(rnd.randint(1, 3)):
                db.session.add(Intervencion(
                    estudiante=e, responsable_id=docs[0].id,
                    fecha=hoy - timedelta(days=rnd.randint(1, 40)),
                    tipo=rnd.choice(TIPOS_INTERVENCION)[0],
                    descripcion="Intervención de prueba con datos ficticios para la demostración del MVP.",
                    compromisos="Revisar avance en la próxima semana.",
                    estado="cerrada" if k else rnd.choice(["abierta", "cerrada"]),
                ))
    db.session.commit()
