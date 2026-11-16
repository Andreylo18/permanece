"""Acceso, permisos por rol, aislamiento entre colegios, estudiantes, seguimiento e indicadores."""
from app.dashboard.routes import calcular_indicadores
from app.extensions import db
from app.models import Asignacion, Estudiante, Institucion, Intervencion, Materia, Usuario

from .conftest import ESTUDIANTE_OK, inst_id, login, logout


def _crear(client, datos=None):
    client.post("/estudiantes/nuevo", data=datos or ESTUDIANTE_OK)
    return db.session.execute(db.select(Estudiante).order_by(Estudiante.id.desc())).scalars().first()


# ---------- BE-02: acceso ----------
def test_rutas_protegidas_redirigen_a_login(client):
    for url in ("/dashboard", "/estudiantes/", "/usuarios/", "/colegios/"):
        r = client.get(url)
        assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_login_incorrecto(client):
    assert "Correo o contraseña incorrectos" in login(client, "admin@t.co", "mala").get_data(as_text=True)


def test_contrasena_guardada_con_hash(app):
    u = db.session.execute(db.select(Usuario).filter_by(email="admin@t.co")).scalar_one()
    assert u.password_hash != "Clave2026*" and u.check_password("Clave2026*")


def test_logout_bloquea_rutas(admin):
    admin.post("/logout")
    assert admin.get("/dashboard").status_code == 302


def test_usuario_inactivo_no_entra(client):
    u = db.session.execute(db.select(Usuario).filter_by(email="docente@t.co")).scalar_one()
    u.activo = False
    db.session.commit()
    assert "desactivado" in login(client, "docente@t.co").get_data(as_text=True)


def test_colegio_inactivo_bloquea_a_sus_usuarios(client):
    db.session.get(Institucion, inst_id("Colegio A")).activa = False
    db.session.commit()
    assert "colegio está desactivado" in login(client, "docente@t.co").get_data(as_text=True)
    assert client.get("/dashboard").status_code == 302


def test_no_redireccion_abierta(client):
    r = client.post("/login?next=https://malicioso.com", data={"email": "admin@t.co", "password": "Clave2026*"})
    assert "malicioso" not in r.headers["Location"]


# ---------- Roles ----------
def test_solo_admin_gestiona_colegios(client):
    for email in ("colegio.a@t.co", "docente@t.co"):
        login(client, email)
        assert client.get("/colegios/").status_code == 403
        assert client.get("/colegios/nueva").status_code == 403
        logout(client)


def test_admin_crea_colegio_con_credenciales(admin, client):
    r = admin.post("/colegios/nueva", data={
        "nombre": "IED Nueva", "municipio": "Sopó", "sector": "oficial", "activa": "y",
        "usuario_nombre": "Coordinación", "usuario_email": "nueva@t.co", "usuario_password": "Segura2026"})
    assert r.status_code == 302
    u = db.session.execute(db.select(Usuario).filter_by(email="nueva@t.co")).scalar_one()
    assert u.rol == "colegio" and u.institucion.nombre == "IED Nueva"
    # Se envía (o simula) el correo de invitación con enlace para definir contraseña
    correos = admin.application.extensions.get("correos_simulados", [])
    assert correos and correos[-1]["para"] == "nueva@t.co" and "/definir-contrasena/" in correos[-1]["enlace"]
    logout(admin)
    html = login(client, "nueva@t.co", "Segura2026").get_data(as_text=True)
    assert "IED Nueva" in html


def test_crear_colegio_exige_credenciales(admin):
    html = admin.post("/colegios/nueva", data={"nombre": "X", "municipio": "Sopó", "sector": "oficial"}
                      ).get_data(as_text=True)
    assert "Este campo es obligatorio" in html
    assert db.session.execute(db.select(Institucion).filter_by(nombre="X")).scalar() is None


def test_docente_no_gestiona_usuarios_ni_estudiantes(docente):
    assert docente.get("/usuarios/").status_code == 403
    assert docente.get("/estudiantes/nuevo").status_code == 403
    assert docente.post("/estudiantes/nuevo", data=ESTUDIANTE_OK).status_code == 403


def test_colegio_solo_crea_docentes_de_su_colegio(colegio):
    # Intenta crear un admin en otro colegio: se fuerza docente del colegio A
    colegio.post("/usuarios/nuevo", data={
        "nombre": "Profe", "email": "profe@t.co", "rol": "admin", "institucion_id": str(inst_id("Colegio B")),
        "activo": "y", "password": "Segura2026", "confirmar": "Segura2026"})
    u = db.session.execute(db.select(Usuario).filter_by(email="profe@t.co")).scalar_one()
    assert u.rol == "docente" and u.institucion.nombre == "Colegio A"


def test_colegio_no_ve_ni_edita_usuarios_de_otro_colegio(colegio):
    html = colegio.get("/usuarios/").get_data(as_text=True)
    assert "docente@t.co" in html and "docente.b@t.co" not in html
    otro = db.session.execute(db.select(Usuario).filter_by(email="docente.b@t.co")).scalar_one()
    assert colegio.get(f"/usuarios/{otro.id}/editar").status_code == 404


# ---------- BE-03: estudiantes y aislamiento ----------
def test_colegio_registra_estudiante_en_su_colegio(colegio):
    # Aunque envíe el id de otro colegio, queda en el suyo
    est = _crear(colegio, dict(ESTUDIANTE_OK, institucion_id=str(inst_id("Colegio B"))))
    assert est.institucion.nombre == "Colegio A" and est.municipio == "Chía"


def test_admin_debe_elegir_colegio(admin):
    html = admin.post("/estudiantes/nuevo", data=dict(ESTUDIANTE_OK, institucion_id="999")).get_data(as_text=True)
    assert "Selecciona un colegio válido" in html
    est = _crear(admin, dict(ESTUDIANTE_OK, institucion_id=str(inst_id("Colegio B"))))
    assert est.institucion.nombre == "Colegio B"


def _asignar(email_docente, grado=9, grupo="A", materia="Matemáticas"):
    doc = db.session.execute(db.select(Usuario).filter_by(email=email_docente)).scalar_one()
    mat = Materia(institucion_id=doc.institucion_id, nombre=materia)
    db.session.add(mat)
    db.session.flush()
    db.session.add(Asignacion(institucion_id=doc.institucion_id, materia_id=mat.id, docente_id=doc.id,
                              grado=grado, grupo=grupo))
    db.session.commit()


def test_docente_solo_ve_estudiantes_de_sus_cursos(client):
    login(client, "colegio.a@t.co")
    mio = _crear(client)                                            # 9° A
    otro = _crear(client, dict(ESTUDIANTE_OK, documento="1000999888", apellidos="Otro Curso", grado="7"))
    logout(client)
    _asignar("docente@t.co")                                        # dicta en 9° A
    login(client, "docente@t.co")
    listado = client.get("/estudiantes/").get_data(as_text=True)
    assert "Prueba Uno" in listado and "Otro Curso" not in listado
    assert client.get(f"/estudiantes/{mio.id}").status_code == 200
    assert client.get(f"/estudiantes/{otro.id}").status_code == 404
    assert client.get(f"/estudiantes/{otro.id}/intervenciones/nueva").status_code == 404
    assert client.get(f"/estudiantes/{otro.id}/factores").status_code == 404


def test_docente_no_ve_estudiantes_de_otro_colegio(client):
    login(client, "colegio.a@t.co")
    est = _crear(client)
    logout(client)
    login(client, "docente.b@t.co")
    assert client.get(f"/estudiantes/{est.id}").status_code == 404
    assert client.get(f"/estudiantes/{est.id}/factores").status_code == 404
    assert client.get(f"/estudiantes/{est.id}/intervenciones/nueva").status_code == 404
    assert "Prueba Uno" not in client.get("/estudiantes/").get_data(as_text=True)
    logout(client)
    _asignar("docente@t.co")
    login(client, "docente@t.co")  # mismo colegio y dicta en su curso: sí lo ve
    assert client.get(f"/estudiantes/{est.id}").status_code == 200


def test_mismo_documento_en_colegios_distintos(client):
    login(client, "colegio.a@t.co")
    _crear(client)
    logout(client)
    login(client, "colegio.b@t.co")
    _crear(client)
    assert db.session.execute(db.select(db.func.count(Estudiante.id))).scalar() == 2


def test_documento_duplicado_en_mismo_colegio(colegio):
    _crear(colegio)
    r = colegio.post("/estudiantes/nuevo", data=ESTUDIANTE_OK)
    assert "Ya existe un estudiante con este documento" in r.get_data(as_text=True)


def test_datos_invalidos_conservan_validos(colegio):
    html = colegio.post("/estudiantes/nuevo", data=dict(ESTUDIANTE_OK, documento="12")).get_data(as_text=True)
    assert "Revisa los campos marcados" in html and 'value="Laura"' in html


# ---------- BE-04: clasificación ----------
def test_factores_sin_periodo_activo_avisa(colegio):
    est = _crear(colegio)
    html = colegio.get(f"/estudiantes/{est.id}/factores", follow_redirects=True).get_data(as_text=True)
    assert "no tiene un periodo activo" in html


def test_factores_manuales_marcan_incompleto(colegio):
    from datetime import date, timedelta
    from app.models import Periodo
    db.session.add(Periodo(institucion_id=inst_id("Colegio A"), nombre="2026-P4", activo=True,
                           fecha_inicio=date.today() - timedelta(days=10), fecha_fin=date.today() + timedelta(days=10)))
    db.session.commit()
    est = _crear(colegio)
    colegio.post(f"/estudiantes/{est.id}/factores", data={"apoyo_familiar": "insuficiente", "reporte_activo": "1"})
    db.session.refresh(est)
    # Sin notas ni asistencia: solo suman apoyo (15) + reporte (10) y queda incompleto
    assert (est.puntaje_actual, est.nivel_actual, est.datos_incompletos) == (25, "bajo", True)


# ---------- BE-05: seguimiento e indicadores ----------
def test_intervencion_conserva_autor_y_fecha(client):
    login(client, "colegio.a@t.co")
    est = _crear(client)
    logout(client)
    _asignar("docente@t.co")
    login(client, "docente@t.co")
    client.post(f"/estudiantes/{est.id}/intervenciones/nueva", data={
        "fecha": "2026-11-01", "tipo": "tutoria", "estado": "abierta",
        "descripcion": "Tutoría de matemáticas con plan de refuerzo."})
    inter = db.session.execute(db.select(Intervencion)).scalar_one()
    assert inter.responsable.email == "docente@t.co" and str(inter.fecha) == "2026-11-01"


def test_dashboard_por_colegio(client, app):
    from app.cli import sembrar_datos
    sembrar_datos(30)
    login(client, "admin@t.co")
    with app.test_request_context():
        from flask_login import login_user
        admin = db.session.execute(db.select(Usuario).filter_by(email="admin@t.co")).scalar_one()
        login_user(admin)
        d = calcular_indicadores({})
        assert d["total"] == 30 == sum(d["por_nivel"].values())
        assert sum(sum(f.values()) for f in d["matriz"].values()) == 30
        assert sum(sum(f.values()) for f in d["por_colegio"].values()) == 30
        assert d["por_nivel"]["alto"] > 0
        assert 0 < d["asistencia_promedio"] <= 100 and 0 < d["promedio_general"] <= 5
        assert d["sin_intervencion"] >= len(d["prioritarios"]) and len(d["prioritarios"]) <= 5
        inst = db.session.execute(db.select(Institucion).filter_by(municipio="Chía", nombre="Institución Educativa San Gabriel")).scalar_one()
        assert calcular_indicadores({"institucion": str(inst.id)})["total"] == 10
        assert calcular_indicadores({"grado": "0"})["total"] == 0

        # Un docente solo cuenta los de su colegio, aunque pida otro
        doc = db.session.execute(db.select(Usuario).filter_by(email="docente.sangabriel@permanece.example")).scalar_one()
        login_user(doc)
        otro = db.session.execute(db.select(Institucion).filter_by(nombre="Colegio La Sabana")).scalar_one()
        propios = calcular_indicadores({})["total"]       # solo sus cursos (6° a 8°)
        assert 0 < propios <= 10
        assert calcular_indicadores({"institucion": str(otro.id)})["total"] == 0


def test_paginas_principales_cargan(client, app):
    from app.cli import sembrar_datos
    sembrar_datos(20)
    est = db.session.execute(db.select(Estudiante).filter(Estudiante.nivel_actual.is_not(None))).scalars().first()
    inst = est.institucion_id
    login(client, "admin@t.co")
    for url in ("/dashboard", f"/dashboard?institucion={inst}&nivel=alto", "/estudiantes/",
                f"/estudiantes/?institucion={inst}&orden=nombre", f"/estudiantes/{est.id}",
                f"/estudiantes/{est.id}/factores", f"/estudiantes/{est.id}/editar", "/estudiantes/nuevo",
                f"/estudiantes/{est.id}/intervenciones/nueva", "/usuarios/", f"/usuarios/?institucion={inst}",
                "/usuarios/nuevo", "/colegios/", "/colegios/nueva", f"/colegios/{inst}/editar"):
        assert client.get(url).status_code == 200, url
    assert client.get("/estudiantes/99999").status_code == 404
    logout(client)
    coord = db.session.execute(db.select(Usuario).filter_by(rol="colegio", institucion_id=inst)).scalars().first()
    login(client, coord.email, "Colegio2026*")
    asig = db.session.execute(db.select(Asignacion).filter_by(institucion_id=inst)).scalars().first()
    for url in ("/dashboard", "/estudiantes/", "/estudiantes/nuevo", f"/estudiantes/{est.id}/editar",
                f"/estudiantes/{est.id}", f"/estudiantes/{est.id}/factores",
                "/usuarios/", "/usuarios/nuevo", "/academico/periodos", "/academico/materias", "/academico/cursos",
                "/academico/mis-cursos", f"/academico/cursos/{asig.id}/notas", f"/academico/cursos/{asig.id}/asistencia",
                f"/academico/cursos/{asig.id}/asistencia/tomar"):
        assert client.get(url).status_code == 200, url
    logout(client)
    login(client, asig.docente.email, "Docente2026*")
    alumno = asig.estudiantes()[0]
    for url in ("/dashboard", "/academico/mis-cursos", f"/academico/cursos/{asig.id}/notas",
                f"/academico/cursos/{asig.id}/asistencia/tomar", f"/estudiantes/{alumno.id}"):
        assert client.get(url).status_code == 200, url


def test_documento_colombiano(colegio):
    from app.documentos import formatear, validar
    from datetime import date
    assert validar("TI", "1.012.345.678") is None
    assert validar("TI", "12345") and validar("PEP", "123") and validar("XX", "123")
    assert validar("CC", "1012345678", date(2012, 5, 1))          # menor de edad con cédula
    assert validar("RC", "1012345678", date(2012, 5, 1))          # 14 años con registro civil
    assert validar("TI", "1012345678", date(2012, 5, 1)) is None
    assert formatear("TI", "1012345678") == "TI 1.012.345.678"
    r = colegio.post("/estudiantes/nuevo", data=dict(ESTUDIANTE_OK, tipo_documento="CC", fecha_nacimiento="2012-05-01"))
    assert "cédula" in r.get_data(as_text=True) and db.session.execute(db.select(Estudiante)).first() is None
    colegio.post("/estudiantes/nuevo", data=dict(ESTUDIANTE_OK, tipo_documento="TI", documento="1.000.123.456"))
    est = db.session.execute(db.select(Estudiante)).scalar_one()
    assert est.documento == "1000123456" and est.tipo_documento == "TI"


def test_demo_sin_ficticio_y_docente_por_cursos(app):
    from app.cli import sembrar_datos
    from app.documentos import validar
    sembrar_datos(24)
    nombres = [i.nombre for i in db.session.execute(db.select(Institucion)).scalars()]
    assert not any("ficti" in n.lower() for n in nombres)
    for e in db.session.execute(db.select(Estudiante)).scalars():
        assert validar(e.tipo_documento, e.documento, e.fecha_nacimiento) is None
    doc = db.session.execute(db.select(Usuario).filter(Usuario.email.like("docente.%"))).scalars().first()
    assert {a.grado for a in db.session.execute(db.select(Asignacion).filter_by(docente_id=doc.id)).scalars()} <= {6, 7, 8}


def test_perfil_cambia_datos_y_contrasena(docente, client):
    assert client.get("/perfil").status_code == 200
    # contraseña actual incorrecta: no cambia nada
    r = client.post("/perfil", data={"c-actual": "mala", "c-nueva": "NuevaClave1*", "c-confirmar": "NuevaClave1*",
                                     "c-cambiar_clave": "1"})
    assert "no es correcta" in r.get_data(as_text=True)
    client.post("/perfil", data={"c-actual": "Clave2026*", "c-nueva": "NuevaClave1*", "c-confirmar": "NuevaClave1*",
                                 "c-cambiar_clave": "1"})
    u = db.session.execute(db.select(Usuario).filter_by(email="docente@t.co")).scalar_one()
    assert u.check_password("NuevaClave1*") and not u.check_password("Clave2026*")
    # correo ya usado por otro usuario
    r = client.post("/perfil", data={"d-nombre": "Profe", "d-email": "admin@t.co", "d-password_actual": "NuevaClave1*",
                                     "d-guardar_datos": "1"})
    assert "ya lo usa otro" in r.get_data(as_text=True)
    client.post("/perfil", data={"d-nombre": "Profe Nuevo", "d-email": "Profe@T.co", "d-password_actual": "NuevaClave1*",
                                 "d-guardar_datos": "1"})
    db.session.refresh(u)
    assert u.nombre == "Profe Nuevo" and u.email == "profe@t.co"
    logout(client)
    login(client, "profe@t.co", "NuevaClave1*")
    assert client.get("/perfil").status_code == 200


def _excel(filas, encabezados=None):
    from io import BytesIO
    from openpyxl import Workbook
    from app.importacion import COLUMNAS
    wb = Workbook()
    ws = wb.active
    ws.append(encabezados or [t for _, t, _, _ in COLUMNAS])
    for f in filas:
        ws.append(f)
    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out


def test_plantilla_e_importacion(colegio):
    from openpyxl import load_workbook
    from io import BytesIO
    r = colegio.get("/estudiantes/plantilla.xlsx")
    assert r.status_code == 200
    assert load_workbook(BytesIO(r.data)).sheetnames == ["Estudiantes", "Instrucciones"]

    # con errores: no se guarda nada
    malo = _excel([
        ["TI", "1.012.345.678", "Laura", "Gómez", "15/03/2012", "8", "a", "María", "3001234567", "m@gmail.com"],
        ["CC", 1012345679, "Pedro", "Ruiz", "15/03/2012", 9, "B", None, None, None],          # menor con CC
        ["TI", "1012345678", "Repetida", "Doc", None, 9, "B", None, None, None],               # repetido
        ["TI", "1012345680", "", "Sin nombre", None, "doce", None, None, "12", "no-es-correo"],
    ])
    r = colegio.post("/estudiantes/importar", data={"archivo": (malo, "e.xlsx")},
                     content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    assert "cédula" in html and "Repetido en el archivo" in html and "Grado no válido" in html
    assert "Correo no válido" in html and "Teléfono no válido" in html
    assert db.session.execute(db.select(Estudiante)).first() is None

    filas_ok = [
        ["TI", "1.012.345.678", "Laura  Sofía", "Gómez", "15/03/2012", "8°", "a", "María", "3001234567", "M@Gmail.com"],
        ["Tarjeta de identidad", 1012345679, "Pedro", "Ruiz", None, "noveno", "B", None, None, None],
    ]
    bueno = _excel(filas_ok)
    r = colegio.post("/estudiantes/importar", data={"archivo": (bueno, "e.xlsx")},
                     content_type="multipart/form-data", follow_redirects=True)
    assert "Se importaron 2" in r.get_data(as_text=True)
    laura = db.session.execute(db.select(Estudiante).filter_by(documento="1012345678")).scalar_one()
    assert (laura.nombres, laura.grado, laura.grupo, laura.email_acudiente) == ("Laura Sofía", 8, "A", "m@gmail.com")
    assert str(laura.fecha_nacimiento) == "2012-03-15" and laura.institucion_id == inst_id("Colegio A")

    # volver a subir: sin la opción son error; con ella se omiten
    r = colegio.post("/estudiantes/importar", data={"archivo": (_excel(filas_ok), "e.xlsx")},
                     content_type="multipart/form-data")
    assert "Ya está registrado" in r.get_data(as_text=True)
    r = colegio.post("/estudiantes/importar", data={"archivo": (_excel(filas_ok), "e.xlsx"), "omitir_existentes": "y"},
                     content_type="multipart/form-data", follow_redirects=True)
    assert "no tiene estudiantes nuevos" in r.get_data(as_text=True)


def test_importar_falta_columna_y_permisos(colegio, client):
    r = colegio.post("/estudiantes/importar", data={"archivo": (_excel([], ["Nombres", "Apellidos"]), "e.xlsx")},
                     content_type="multipart/form-data")
    assert "Falta esta columna" in r.get_data(as_text=True)
    r = colegio.post("/estudiantes/importar", data={"archivo": (_excel([]), "e.csv")}, content_type="multipart/form-data")
    assert "Debe ser un archivo de Excel" in r.get_data(as_text=True)
    logout(colegio)
    login(client, "docente@t.co")
    assert client.get("/estudiantes/importar").status_code in (302, 403)
