import pytest

from app import create_app
from app.extensions import db
from app.models import Institucion, Usuario

CLAVE = "Clave2026*"


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        a = Institucion(nombre="Colegio A", municipio="Chía")
        b = Institucion(nombre="Colegio B", municipio="Cota")
        db.session.add_all([a, b])
        db.session.flush()
        for email, rol, inst in (("admin@t.co", "admin", None),
                                 ("colegio.a@t.co", "colegio", a),
                                 ("docente@t.co", "docente", a),
                                 ("colegio.b@t.co", "colegio", b),
                                 ("docente.b@t.co", "docente", b)):
            u = Usuario(nombre=email.split("@")[0], email=email, rol=rol, institucion=inst)
            u.set_password(CLAVE)
            db.session.add(u)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, email, clave=CLAVE):
    return client.post("/login", data={"email": email, "password": clave}, follow_redirects=True)


def logout(client):
    client.post("/logout")


@pytest.fixture
def admin(client):
    login(client, "admin@t.co")
    return client


@pytest.fixture
def colegio(client):
    login(client, "colegio.a@t.co")
    return client


@pytest.fixture
def docente(client):
    login(client, "docente@t.co")
    return client


def inst_id(nombre):
    return db.session.execute(db.select(Institucion.id).filter_by(nombre=nombre)).scalar_one()


ESTUDIANTE_OK = {
    "tipo_documento": "TI", "documento": "1000123456", "nombres": "Laura", "apellidos": "Prueba Uno",
    "grado": "9", "grupo": "A",
}
