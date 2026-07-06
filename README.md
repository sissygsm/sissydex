# sissydex

## File System

```
root/
├── backend/                  # Tu carpeta actual vacía
│   ├── app.py                # Servidor principal (Flask/FastAPI)
│   ├── config.py             # Configuración de rutas y variables
│   ├── services/
│   │   └── document_logic.py # Lógica de metadatos, OCR o indexación
│   └── requirements.txt       # Dependencias de Python
│
├── frontend/                 # Tu carpeta actual
│   ├── miniBL/               # Lógica del cliente
│   │   └── app.js            # Control de eventos, peticiones API
│   ├── style/
│   │   └── style.css         # Estilos de la interfaz del DMS
│   └── templates/            # Movido aquí (Buenas prácticas)
│       └── index.html        # UI principal (Buscador, visor de archivos)
│
├── storage_database/         # Renombrado de media_database
│   ├── core/                 # Archivos del sistema
│   │   ├── catalogo_archivos.db # Movido aquí (Tu base de datos SQLite)
│   │   └── dbManager.py      # Movido aquí (Script de gestión de BD)
│   └── documents_pool/       # Directorio raíz donde se guardarán los PDFs/DOCXs reales
│       └── data1.png         # Tu archivo actual guardado
│
├── venv/                     # Tu entorno virtual actual (Python)
└── .gitignore                # Reglas para no subir el venv ni la base de datos
```
