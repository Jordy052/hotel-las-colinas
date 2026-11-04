# Administración de reservas de hotel

Aplicación de escritorio administrativa en PySide6. La información operativa y las cuentas se guardan en MySQL mediante SQLAlchemy ORM y PyMySQL. No se usa SQLite ni se cargan datos de demostración al iniciar.

## Preparar MySQL

1. Inicia MySQL Server.
2. Abre sql/01_crear_esquema.sql en MySQL Workbench y ejecútalo. Crea el esquema hotel_reservas.
3. Copia .env.example como .env y completa la clave de tu servidor MySQL y una contraseña segura para la cuenta inicial de la aplicación.
4. Instala dependencias con python -m pip install -r requirements.txt.
5. Inicia desde esta carpeta con python main.py.

Al iniciar, la aplicación se conecta a MySQL y valida el esquema creado desde Workbench. Si falta la tabla de apartados temporales `booking_holds`, la crea sin modificar las tablas existentes. Si la base ya existía antes del campo de cédula del personal, ejecuta sql/03_agregar_cedula_personal.sql en Workbench antes de abrir la aplicación. Si todavía no existe una cuenta administradora, registra la cuenta inicial con HOTEL_BOOTSTRAP_ADMIN_EMAIL y HOTEL_BOOTSTRAP_ADMIN_PASSWORD de .env; después, el administrador puede crear cuentas de recepción y asignarles secciones desde Personal. Las contraseñas se almacenan como hash seguro. Las cuentas con rol Usuario usan la web y no pueden entrar al escritorio administrativo.

La clave de MYSQL_PASSWORD es la del servidor MySQL. La clave HOTEL_BOOTSTRAP_ADMIN_PASSWORD es independiente y sirve para entrar a la aplicación. .env está excluido de Git; no compartas ni subas ese archivo.

## Roles

- Administrador: acceso completo, incluye administración de cuentas de recepción y permisos.
- Recepcionista: acceso al panel de recepción y a las secciones que el administrador habilite en su cuenta.

La validación del rol y los permisos se realiza contra las tablas de MySQL en cada inicio de sesión. Si se suspende una cuenta, se bloquea el siguiente acceso.

## Estructura

- main.py: punto de entrada de la aplicación.
- hotel_admin/ui.py: interfaz PySide6 y estilos QSS.
- hotel_admin/models.py: entidades SQLAlchemy y relaciones.
- hotel_admin/database.py: conexión MySQL y validación del esquema de Workbench.
- hotel_admin/auth.py y hotel_admin/security.py: autenticación y hash de contraseñas.
- hotel_admin/repositories.py: consultas ORM y operaciones transaccionales.
- hotel_admin/workers.py: tareas de fondo con QThread; los hilos no modifican widgets.
- hotel_admin/exporters.py: exportaciones a PDF y Excel.
- sql/01_crear_esquema.sql: creación del esquema en MySQL Workbench.
- sql/03_agregar_cedula_personal.sql: migración para agregar la cédula a una base existente.
