FROM python:3.14-slim

WORKDIR /app

# Copiar e instalar dependencias primero para aprovechar la caché de capas
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# document_logic.py calcula PROJECT_ROOT subiendo 3 niveles desde
# backend/services/, así que espera ver frontend/ y storage_database/ como
# directorios hermanos de backend/ -no alcanza con copiar solo backend/-.
COPY backend/ backend/
COPY frontend/ frontend/
COPY storage_database/ storage_database/

EXPOSE 5000

CMD ["python", "backend/app.py"]
