# API local de la web

La web de huéspedes usa la misma base MySQL que Administración y Recepción. El navegador consume esta API local; las credenciales MySQL permanecen en `administrador/.env` y nunca se envían al navegador.

## Inicio

1. Inicia el servidor MySQL configurado en `administrador/.env`.
2. Ejecuta `INICIAR_API.cmd` desde la carpeta `administrador` y deja esa ventana abierta.
3. Abre `usuario/html/acceso.html` con Live Server en el puerto 5500.
4. Registra una cuenta desde la web o inicia sesión con una cuenta de rol `Usuario` ya existente.

Las cuentas de `Administrador` y `Recepcionista` se rechazan en el portal de huéspedes. Las reservas web se guardan en `reservations` con origen `Web`, y el pago simulado completo se registra en `payments`. Cada apartado conserva una clave que impide crear pagos duplicados. Administración y Recepción leen esos mismos registros desde MySQL.

## Restablecer contraseña por correo

La página `usuario/html/cambiar-clave.html` permite recuperar una cuenta de huésped sin iniciar sesión. La API envía un código de seis dígitos que vence en 10 minutos y solo se puede usar una vez. Hay un máximo de cinco intentos de validación y se limita la frecuencia de solicitudes. Al cambiar la clave se invalidan las sesiones web anteriores.

Para habilitar el envío, configura estas variables en `administrador/.env` y reinicia la API:

```dotenv
HOTEL_SMTP_HOST=smtp.gmail.com
HOTEL_SMTP_PORT=587
HOTEL_SMTP_USERNAME=tu-correo@gmail.com
HOTEL_SMTP_PASSWORD=tu-contrasena-de-aplicacion
HOTEL_SMTP_FROM=tu-correo@gmail.com
HOTEL_SMTP_STARTTLS=true
HOTEL_PASSWORD_RESET_SECRET=una-clave-aleatoria-larga-y-privada
```

Con Gmail se debe usar una contraseña de aplicación. El puerto `587` usa STARTTLS; el puerto `465` usa TLS implícito. No compartas ni publiques el archivo `.env`.

La API expone `POST /api/auth/password-reset/request` para enviar el código y `POST /api/auth/password-reset/confirm` para validarlo y guardar la contraseña nueva. La respuesta de solicitud no revela si el correo está registrado.

El checkout simula pagos completos y reembolsos; no mueve dinero real. Para cobrar en producción hace falta integrar una pasarela de pago. El alta web exige confirmar un código de correo antes de crear la cuenta o vincular un huésped registrado en recepción.
