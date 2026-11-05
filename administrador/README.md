# Hotel Las Colinas — Administración y API

La aplicación de escritorio y la web usan la misma base de datos MySQL alojada en Aiven (`defaultdb`). Las credenciales se guardan localmente en `administrador/.env` y no se envían al navegador ni se suben a Git.

## Base de datos Aiven

La instancia actual ya contiene datos y tablas con nombres antiguos en inglés. Para conservarlos y pasarlos al esquema español:

1. Detén temporalmente la API web y cierra la aplicación de escritorio.
2. Guarda un respaldo de `defaultdb`.
3. Desde MySQL Workbench conectado a Aiven, abre y ejecuta **una sola vez** `sql/04_traducir_esquema_aiven.sql`.
4. Comprueba que aparezcan `usuarios_app`, `huespedes`, `habitaciones`, `reservas`, `pagos`, `permisos`, `roles`, `fotos_habitacion`, `archivos_foto_habitacion`, `usuarios_permisos` y `bloqueos_reserva`.
5. Inicia la API y luego Administración/Recepción.

El script cambia nombres conservando filas, IDs y relaciones; también traduce los códigos de permisos. No vuelvas a ejecutar el script de migración después de completarlo.

`sql/01_crear_esquema.sql` es solo para una base `defaultdb` vacía. No lo ejecutes sobre la base actual con datos. Los scripts `02` y `03` son actualizaciones puntuales para esquemas ya traducidos.

## Configuración y ejecución

1. Copia `.env.example` como `.env` y completa los valores de conexión de Aiven, incluido TLS y su certificado CA.
2. Instala las dependencias con `python -m pip install -r requirements.txt`.
3. Inicia la API con `INICIAR_API.cmd`.
4. Inicia el escritorio con `python main.py` desde esta carpeta.

Al iniciar, la aplicación valida que las tablas, columnas, roles y permisos estén presentes. No crea tablas parciales automáticamente. En `hotel_admin/models.py`, los atributos de Python conservan nombres internos estables y se asignan a nombres de tablas y columnas en español en MySQL.

## Roles

- **Administrador:** acceso completo y administración de cuentas de recepción y sus permisos.
- **Recepcionista:** acceso al panel y a las secciones habilitadas por el administrador.
- **Usuario:** cuenta de huésped que usa la web.

Las contraseñas se guardan como hashes. `.env` está excluido de Git; no lo compartas ni lo publiques.

## Archivos principales

- `main.py`: punto de entrada del escritorio.
- `hotel_admin/models.py`: modelos y correspondencia entre la aplicación y el esquema español.
- `hotel_admin/database.py`: conexión y validación del esquema.
- `hotel_admin/repositories.py`: consultas y operaciones de la aplicación.
- `hotel_admin/web_api.py`: API consumida por la web.
- `sql/01_crear_esquema.sql`: creación inicial en una base vacía.
- `sql/04_traducir_esquema_aiven.sql`: traducción única del esquema inglés existente en Aiven.
