"""Diagnóstico de la conexión a la base de datos (Neon).

Uso:  python probar_conexion.py
"""
import socket
import sys
import time
from urllib.parse import urlsplit

import config  # carga el .env

url = config.Config.SQLALCHEMY_DATABASE_URI
if not url.startswith("postgresql"):
    print(f"DATABASE_URL no apunta a PostgreSQL (se usará: {url.split(':')[0]}). Revisa tu .env.")
    sys.exit(1)

partes = urlsplit(url.replace("postgresql+psycopg://", "postgresql://"))
host, puerto = partes.hostname, partes.port or 5432
print(f"Servidor: {host}  puerto: {puerto}\n")

# 1) ¿Se resuelve el nombre?
try:
    ip = socket.gethostbyname(host)
    print(f"[OK]  1. El nombre del servidor se resuelve ({ip}).")
except OSError as e:
    print(f"[X]   1. No se pudo resolver el nombre del servidor: {e}")
    print("      Revisa que la cadena de Neon esté bien copiada y que tengas internet.")
    sys.exit(1)

# 2) ¿Se puede abrir el puerto 5432?
inicio = time.time()
try:
    with socket.create_connection((host, puerto), timeout=8):
        pass
    print(f"[OK]  2. El puerto {puerto} está abierto ({time.time() - inicio:.1f} s).")
except OSError as e:
    print(f"[X]   2. No se pudo abrir el puerto {puerto}: {e}")
    print("      La red en la que estás (universidad, empresa) probablemente BLOQUEA PostgreSQL.")
    print("      Prueba con otra red, por ejemplo compartiendo datos desde tu celular.")
    sys.exit(1)

# 3) ¿Acepta el usuario y la contraseña?
try:
    import psycopg
    inicio = time.time()
    with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=20) as conn:
        version = conn.execute("select version()").fetchone()[0].split(",")[0]
    print(f"[OK]  3. Conexión exitosa a la base ({time.time() - inicio:.1f} s): {version}")
    print("\nTodo bien. Ya puedes ejecutar:  flask --app run seed --n 90 --reset")
except Exception as e:  # noqa: BLE001
    print(f"[X]   3. El servidor respondió pero rechazó la conexión:\n      {e}")
    print("      Revisa el usuario y la contraseña de DATABASE_URL en tu .env (vuelve a copiarla desde Neon).")
    sys.exit(1)
