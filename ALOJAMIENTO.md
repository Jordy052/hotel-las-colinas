# Alojamiento de Hotel Las Colinas

Estado al 4 de noviembre de 2026:

- Web: https://jordy052.github.io/hotel-las-colinas/
- API HTTPS: https://hotel-las-colinas-api.onrender.com/api
- Servicio Render: hotel-las-colinas-api, plan Free, una instancia.
- MySQL Aiven: hotel-las-colinas-mysql, plan Free. Es la base única compartida por web, administración y recepción.
- Migración: 11 habitaciones, cuentas, huéspedes, reservas, pagos y permisos copiados y comparados con el respaldo. Las 22 fotografías están almacenadas en MySQL con verificación SHA-256.
- Correo: transporte HTTPS preparado con Google Apps Script. Pendiente autorizar el proyecto con la cuenta remitente y configurar su URL privada. Brevo queda como alternativa mientras su soporte revisa la verificación SMS.

## Configuración

usuario/js/configuracion.js contiene únicamente la dirección pública de la API. Los datos de MySQL y las claves de servicios se guardan en variables privadas de Render y archivos .env excluidos de GitHub. No se deben copiar contraseñas a JavaScript ni a este documento.

administrador/.env apunta a la base remota usando TLS y certificado CA verificado. Es necesario cerrar y volver a abrir las aplicaciones de administración y recepción para cargar esa configuración. La base local y su configuración anterior se conservaron como respaldo dentro de administrador/storage/backups/.

Las fotos se guardan en room_photo_assets y se relacionan con room_photos. El escritorio mantiene una caché local para mostrarlas; la API las sirve desde MySQL. Se admiten imágenes de hasta 8 MB. El disco temporal de Render no es el almacenamiento principal.

## Comprobaciones realizadas

HTTPS, CORS de GitHub Pages, MySQL TLS, listado de habitaciones y fotos, inicio de sesión, perfil, bloqueo temporal de habitación, repetición del pago sin duplicar registros, cancelación y reembolso, cierre de sesión. Los registros temporales de las pruebas se eliminaron. No se realizaron cobros externos ni se enviaron correos de prueba.

## Límites del plan gratuito

Render Free se suspende tras inactividad y puede tardar cerca de un minuto en despertar. Las sesiones y los códigos de verificación están en memoria y se pierden cuando se reinicia el proceso; en ese caso se inicia sesión o se solicita otro código. Se usa una sola instancia.

Render Free bloquea SMTP en los puertos 25, 465 y 587. Por eso el correo remoto utilizará Google Apps Script mediante HTTPS al completar la autorización; Brevo también está disponible como alternativa. La instalación local conserva su transporte SMTP.

Aiven Free tiene límites de almacenamiento y conexiones y puede apagarse por inactividad. Estos planes sirven para pruebas y demostraciones; no garantizan disponibilidad continua.

Referencias: https://render.com/docs/free · https://aiven.io/docs/products/mysql/concepts/mysql-free-tier · https://developers.brevo.com/docs/send-a-transactional-email

El proyecto público de Apps Script está en administrador/apps_script/. Es una plantilla sin claves. El archivo preparado con la clave privada se guarda en administrador/storage/deployment/ y está excluido de GitHub. Las cuentas Gmail personales tienen una cuota de 100 destinatarios diarios.
