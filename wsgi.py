"""
Point d'entrée WSGI pour les plateformes comme PythonAnywhere.
FastAPI étant basé sur ASGI, nous utilisons le middleware ASGIMiddleware (a2wsgi)
pour exposer l'objet WSGI standard `application`.
"""
import sys
from pathlib import Path

# S'assurer que le répertoire racine du projet est dans sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from a2wsgi import ASGIMiddleware
from app.main import app

# PythonAnywhere cherche l'objet `application`
application = ASGIMiddleware(app)
