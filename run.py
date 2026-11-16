"""Punto de entrada.

Desarrollo:   flask --app run run --debug
Producción:   gunicorn -w 3 -b 0.0.0.0:8000 "run:app"   (con FLASK_ENV_NAME=production)
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
