"""Módulo académico: notas ponderadas, asistencia, recálculo del riesgo, permisos y correos."""
from datetime import date, timedelta

import pytest

from app.academico import resumen_academico
from app.correo import generar_token
from app.extensions import db
from app.models import (Actividad, Asignacion, Estudiante, Materia, Nota, Periodo, SesionClase, Usuario)

from .conftest import inst_id, login, logout

HOY = date.today()


@pytest.fixture
def curso(app):
    """Colegio A con periodo activo, materia Matemáticas 9A dictada por docente@t.co y 2 estudiantes."""
    a = inst_id("Colegio A")
    doc = db.session.execute(db.select(Usuario).filter_by(email="docente@t.co")).scalar_one()
    per = Periodo(institucion_id=a, nombre="2026-P4", activo=True,
                  fecha_inicio=HOY - timedelta(days=30), fecha_fin=HOY + timedelta(days=30))
    mat = Materia(institucion_id=a, nombre="Matemáticas")
    db.session.add_all([per, mat])
    db.session.flush()
    asig = Asignacion(institucion_id=a, materia_id=mat.id, docente_id=doc.id, grado=9, grupo="A")
    e1 = Estudiante(institucion_id=a, documento="E1", nombres="Ana", apellidos="Uno", grado=9, grupo="A",
                    email_acudiente="mama.ana@t.co")
    e2 = Estudiante(institucion_id=a, documento="E2", nombres="Beto", apellidos="Dos", grado=9, grupo="A")
    otro = Estudiante(institucion_id=a, documento="E3", nombres="Otro", apellidos="Curso", grado=9, grupo="B")
    db.session.add_all([asig, e1, e2, otro])
    db.session.commit()
    return {"asig": asig, "per": per, "e1": e1, "e2": e2, "otro": otro}


def _actividades(client, asig, *pares):
    for nombre, pct in pares:
        client.post(f"/academico/cursos/{asig.id}/actividades", data={"nombre": nombre, "porcentaje": pct})
    return db.session.execute(db.select(Actividad).filter_by(asignacion_id=asig.id)
                              .order_by(Actividad.id)).scalars().all()


def test_curso_incluye_solo_su_grado_y_grupo(curso):
    assert [e.documento for e in curso["asig"].estudiantes()] == ["E2", "E1"]  # orden por apellido


def test_nota_ponderada_y_reprobadas(docente, curso):
    asig, e1, e2 = curso["asig"], curso["e1"], curso["e2"]
    taller, examen = _actividades(docente, asig, ("Taller", 40), ("Examen", 60))
    r = docente.post(f"/academico/cursos/{asig.id}/notas", data={
        f"n_{taller.id}_{e1.id}": "4,0", f"n_{examen.id}_{e1.id}": "3.5",
        f"n_{taller.id}_{e2.id}": "2", f"n_{examen.id}_{e2.id}": ""})
    assert r.status_code == 302
    res1 = resumen_academico(e1, curso["per"])
    assert res1.materias[0].nota == 3.7          # 4,0×40 % + 3,5×60 %
    res2 = resumen_academico(e2, curso["per"])
    assert res2.materias[0].nota == 2.0 and res2.materias[0].porcentaje_evaluado == 40   # examen sin calificar
    assert (res2.promedio, res2.reprobadas) == (2.0, 1)
    db.session.refresh(e2)
    assert e2.registro_de("2026-P4").promedio is not None   # se recalculó al guardar


def test_nota_invalida_no_guarda_nada(docente, curso):
    asig, e1 = curso["asig"], curso["e1"]
    (taller,) = _actividades(docente, asig, ("Taller", 100))
    html = docente.post(f"/academico/cursos/{asig.id}/notas", data={
        f"n_{taller.id}_{e1.id}": "7", f"n_{taller.id}_{curso['e2'].id}": "4"}).get_data(as_text=True)
    assert "No se guardó nada" in html and "is-invalid" in html
    assert db.session.execute(db.select(db.func.count(Nota.id))).scalar() == 0


def test_porcentaje_no_supera_100(docente, curso):
    acts = _actividades(docente, curso["asig"], ("A", 70), ("B", 40))
    assert [a.nombre for a in acts] == ["A"]


def test_asistencia_excusa_no_baja_porcentaje(docente, curso):
    asig, e1, e2 = curso["asig"], curso["e1"], curso["e2"]
    estados_e1 = ["presente", "ausente", "excusa", "tarde"]
    for k, estado in enumerate(estados_e1):
        r = docente.post(f"/academico/cursos/{asig.id}/asistencia/tomar", data={
            "fecha": (HOY - timedelta(days=k + 1)).isoformat(), f"e_{e1.id}": estado, f"e_{e2.id}": "presente"})
        assert r.status_code == 302
    res = resumen_academico(e1, curso["per"])
    # presente + tarde = 2 asistidas; base = 4 clases − 1 excusa = 3
    assert (res.clases, res.ausencias, res.excusas, res.asistencia_pct) == (4, 1, 1, 66.7)
    assert resumen_academico(e2, curso["per"]).asistencia_pct == 100.0


def test_misma_fecha_actualiza_la_clase(docente, curso):
    asig, e1 = curso["asig"], curso["e1"]
    f = (HOY - timedelta(days=1)).isoformat()
    docente.post(f"/academico/cursos/{asig.id}/asistencia/tomar", data={"fecha": f, f"e_{e1.id}": "ausente"})
    docente.post(f"/academico/cursos/{asig.id}/asistencia/tomar", data={"fecha": f, f"e_{e1.id}": "presente"})
    assert db.session.execute(db.select(db.func.count(SesionClase.id))).scalar() == 1
    assert resumen_academico(e1, curso["per"]).asistencia_pct == 100.0


def test_fecha_fuera_del_periodo(docente, curso):
    html = docente.post(f"/academico/cursos/{curso['asig'].id}/asistencia/tomar",
                        data={"fecha": (HOY - timedelta(days=90)).isoformat()}).get_data(as_text=True)
    assert "dentro del periodo" in html


def test_alerta_riesgo_alto_una_sola_vez(app, docente, curso):
    asig, e1 = curso["asig"], curso["e1"]
    (examen,) = _actividades(docente, asig, ("Examen", 100))
    app.extensions["correos_simulados"] = []
    # 4 clases: 3 fallas -> asistencia 25 % (30) ; nota 1,0 -> promedio (20) ; 1 reprobada
    for k in range(4):
        docente.post(f"/academico/cursos/{asig.id}/asistencia/tomar", data={
            "fecha": (HOY - timedelta(days=k + 1)).isoformat(), f"e_{e1.id}": "presente" if k == 0 else "ausente"})
    docente.post(f"/academico/cursos/{asig.id}/notas", data={f"n_{examen.id}_{e1.id}": "1"})
    # apoyo familiar insuficiente (15) -> 65 = alto
    login(docente, "docente@t.co")
    docente.post(f"/estudiantes/{e1.id}/factores", data={"apoyo_familiar": "insuficiente", "reporte_activo": "0"})
    db.session.refresh(e1)
    assert e1.nivel_actual == "alto"
    para = [c["para"] for c in app.extensions["correos_simulados"]]
    assert para.count("colegio.a@t.co") == 1 and para.count("mama.ana@t.co") == 1
    acudiente = next(c for c in app.extensions["correos_simulados"] if c["para"] == "mama.ana@t.co")
    assert "/100" not in acudiente["html"]          # al acudiente no se le envían puntajes
    # Nuevos guardados sin cambio de nivel no repiten la alerta
    docente.post(f"/academico/cursos/{asig.id}/notas", data={f"n_{examen.id}_{e1.id}": "1,2"})
    assert len(app.extensions["correos_simulados"]) == 2


def test_docente_no_entra_a_curso_ajeno(client, curso):
    login(client, "docente.b@t.co")
    assert client.get(f"/academico/cursos/{curso['asig'].id}/notas").status_code == 404
    assert client.get(f"/academico/cursos/{curso['asig'].id}/asistencia/tomar").status_code == 404


def test_configuracion_academica_solo_colegio(client, curso):
    login(client, "docente@t.co")
    for url in ("/academico/periodos", "/academico/materias", "/academico/cursos"):
        assert client.get(url).status_code == 403
    logout(client)
    login(client, "colegio.a@t.co")
    assert "Matemáticas" in client.get("/academico/cursos").get_data(as_text=True)
    assert client.get(f"/academico/cursos/{curso['asig'].id}/notas").status_code == 200


def test_colegio_crea_periodo_materia_y_curso(colegio):
    colegio.post("/academico/periodos", data={"nombre": "2027-P1", "fecha_inicio": "2027-01-20",
                                              "fecha_fin": "2027-04-10", "activo": "y"})
    colegio.post("/academico/materias", data={"nombre": "Inglés"})
    mat = db.session.execute(db.select(Materia).filter_by(nombre="Inglés")).scalar_one()
    doc = db.session.execute(db.select(Usuario).filter_by(email="docente@t.co")).scalar_one()
    colegio.post("/academico/cursos", data={"materia_id": mat.id, "docente_id": doc.id, "grado": 7, "grupo": "b"})
    asig = db.session.execute(db.select(Asignacion).filter_by(materia_id=mat.id)).scalar_one()
    assert (asig.grado, asig.grupo, asig.docente_id) == (7, "B", doc.id)
    # Un docente de otro colegio no se puede asignar
    otro = db.session.execute(db.select(Usuario).filter_by(email="docente.b@t.co")).scalar_one()
    colegio.post("/academico/cursos", data={"materia_id": mat.id, "docente_id": otro.id, "grado": 8, "grupo": "A"})
    assert db.session.execute(db.select(db.func.count(Asignacion.id))).scalar() == 1


# ---------------- Correos y contraseñas ----------------

def test_recuperar_contrasena(app, client):
    app.extensions["correos_simulados"] = []
    client.post("/olvide-mi-contrasena", data={"email": "docente@t.co"})
    client.post("/olvide-mi-contrasena", data={"email": "noexiste@t.co"})   # mismo mensaje, sin correo
    correos = app.extensions["correos_simulados"]
    assert len(correos) == 1 and correos[0]["para"] == "docente@t.co"
    ruta = correos[0]["enlace"].replace("http://localhost", "")
    assert client.post(ruta, data={"password": "NuevaClave1", "confirmar": "NuevaClave1"}).status_code == 302
    assert "Bienvenido" in login(client, "docente@t.co", "NuevaClave1").get_data(as_text=True)
    logout(client)
    # El enlace ya no sirve después de usarlo
    html = client.get(ruta, follow_redirects=True).get_data(as_text=True)
    assert "no es válido" in html


def test_token_alterado_no_sirve(client):
    u = db.session.execute(db.select(Usuario).filter_by(email="docente@t.co")).scalar_one()
    token = generar_token(u)
    html = client.get(f"/definir-contrasena/{token[:-3]}xyz", follow_redirects=True).get_data(as_text=True)
    assert "no es válido" in html


def test_colegio_crea_docente_sin_contrasena_y_recibe_invitacion(app, colegio, client):
    app.extensions["correos_simulados"] = []
    colegio.post("/usuarios/nuevo", data={"nombre": "Profe Nuevo", "email": "nuevo@t.co", "activo": "y"})
    correo = app.extensions["correos_simulados"][-1]
    assert correo["para"] == "nuevo@t.co"
    logout(colegio)
    client.post(correo["enlace"].replace("http://localhost", ""),
                data={"password": "Clave12345", "confirmar": "Clave12345"})
    assert "Bienvenido" in login(client, "nuevo@t.co", "Clave12345").get_data(as_text=True)


def test_intervencion_se_envia_al_acudiente(app, docente, curso):
    app.extensions["correos_simulados"] = []
    docente.post(f"/estudiantes/{curso['e1'].id}/intervenciones/nueva", data={
        "fecha": HOY.isoformat(), "tipo": "reunion_acudiente", "estado": "abierta",
        "descripcion": "Reunión para acordar plan de refuerzo en matemáticas.", "notificar_acudiente": "y"})
    correos = app.extensions["correos_simulados"]
    assert len(correos) == 1 and correos[0]["para"] == "mama.ana@t.co" and "plan de refuerzo" in correos[0]["html"]


def test_correo_acudiente_invalido(colegio):
    from .conftest import ESTUDIANTE_OK
    html = colegio.post("/estudiantes/nuevo", data=dict(ESTUDIANTE_OK, email_acudiente="no-es-correo")
                        ).get_data(as_text=True)
    assert "Correo no válido" in html
