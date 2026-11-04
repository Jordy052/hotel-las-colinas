# Hotel Las Colinas

Sistema de gestión hotelera para **Hotel Las Colinas, Puerto Cabezas, Nicaragua**. Comparte una base MySQL entre el portal web de huéspedes y la aplicación de escritorio de administración y recepción.

## Funciones

- Registro de huéspedes con verificación de correo y vinculación con perfiles creados en recepción.
- Inicio de sesión, recuperación de contraseña por correo y teléfono de contacto.
- Habitaciones con fotografías, disponibilidad por fechas, capacidad, tarifas y comodidades.
- Apartados de diez minutos, liberación al abandonar la reserva y protección contra pagos duplicados.
- Estados Confirmada, En camino, Hospedado, Cancelada y Finalizada.
- Pagos, reembolsos y cargos de cancelación; distinción entre tarjeta web y tarjeta presencial por TPV/POS.
- Exportaciones filtradas a Excel y PDF por estado, fecha y método de pago.
- Cuentas del personal con permisos y autocompletado mediante el almacén de credenciales de Windows.

## Tecnologías

- Web: HTML, CSS y JavaScript.
- Escritorio: Python y PySide6.
- API local: Python, puerto `8765`.
- Persistencia: MySQL 8, SQLAlchemy y PyMySQL.
- Archivos: openpyxl y ReportLab.

## Requisitos

- Windows, Python 3.11 o posterior y MySQL 8.
- VS Code con Live Server para servir el portal en `http://127.0.0.1:5500`.
- Un remitente SMTP para enviar los códigos de registro y recuperación.

## Instalación

Desde PowerShell, en la carpeta del proyecto:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\administrador\requirements.txt
Copy-Item .\administrador\.env.example .\administrador\.env
```

1. Abre `administrador/sql/01_crear_esquema.sql` en MySQL Workbench y ejecútalo en tu servidor local.
2. Completa `administrador/.env` con tus credenciales MySQL, la contraseña de la cuenta administradora inicial y los datos SMTP. Usa una contraseña de aplicación si el remitente es Gmail.
3. Genera `HOTEL_PASSWORD_RESET_SECRET` con una clave privada aleatoria, por ejemplo con `py -c "import secrets; print(secrets.token_urlsafe(48))"`.
4. Inicia MySQL antes de abrir la aplicación o la API.

### Escritorio de administración y recepción

```powershell
.\.venv\Scripts\python.exe .\administrador\main.py
```

La primera cuenta administradora se configura en `.env`. El administrador crea las cuentas de recepción y asigna sus permisos desde **Personal**. Las cuentas de huéspedes acceden al portal web.

### API del portal

En otra terminal:

```powershell
Set-Location .\administrador
..\.venv\Scripts\python.exe -m hotel_admin.web_api
```

Mantén la API en ejecución mientras uses la web. Abre la raíz del proyecto en VS Code y sirve `usuario/html/index.html` con Live Server, en el puerto `5500`.

También se incluye `administrador/INICIAR_API.cmd` para el entorno local existente.

## Política de reservas

- Entrada desde las 14:00; salida hasta las 12:00, hora de Nicaragua.
- Se permiten estancias dentro de los próximos ocho meses del calendario.
- El plazo de cancelación gratuita equivale a `3/7` del tiempo entre la creación de la reserva y su entrada.
- Después del plazo, se retiene el 30 % y se registra un reembolso del 70 %.
- Los cargos retenidos forman parte del pago original y no se suman dos veces a los ingresos.

## Alcance de los pagos

El procesamiento de pagos y reembolsos de este proyecto es **simulado**: registra operaciones en la base de datos y no mueve dinero real. No incluye integración bancaria, pasarela de tarjetas ni validación automática de transferencias. La comprobación presencial de transferencias se realiza manualmente.

Para probar el formulario se admiten los números públicos de prueba `5200 8282 8282 8210` y `4242 4242 4242 4242`, código `123` y una fecha futura. El número de tarjeta y el código de seguridad no se envían a la API ni se guardan en MySQL.

## Archivos excluidos

El repositorio no contiene `.env`, contraseñas, registros de huéspedes, bases de datos, exportaciones ni las fotografías cargadas localmente en `administrador/storage`. El esquema SQL contiene estructura, roles y permisos; cada instalación configura sus propias cuentas y datos.

## Estructura

```text
administrador/
  hotel_admin/       API, escritorio, autenticación y lógica del hotel
  sql/               Esquema y migraciones para MySQL
  .env.example       Plantilla sin credenciales
  main.py            Entrada al escritorio
  requirements.txt   Dependencias Python
usuario/
  html/              Páginas del portal
  css/               Estilos
  js/                Comportamiento y llamadas a la API
  img/               Logo e imágenes incluidas en el proyecto
```


## Sitio web en GitHub Pages

La entrada pública es https://jordy052.github.io/hotel-las-colinas/ . El `index.html` de la raíz presenta el logo durante dos segundos y redirige a `usuario/html/index.html`. El enlace «Entrar ahora» permite omitir la presentación.

GitHub Pages publica HTML, CSS, JavaScript e imágenes. Las funciones de inicio de sesión, registro y reservas requieren una API accesible por internet y su base MySQL; la configuración de este repositorio sigue apuntando a la API local. Publicar la web estática no despliega esa API ni MySQL.
