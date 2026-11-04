# Publicación de la API

Estado: archivos preparados; servicios remotos todavía no creados ni enlazados.

La web sigue en GitHub Pages. Render ejecuta la API Python y Aiven aloja una única base MySQL compartida con administración y recepción. Seleccionar los planes Free; no activar pruebas de planes de pago.

## Archivos

- Dockerfile: inicia la API sin instalar la interfaz gráfica de escritorio.
- render.yaml: servicio Free, una instancia, puerto PORT y comprobación /api/health.
- usuario/js/configuracion.js: única dirección de API para toda la web, incluida la liberación de habitaciones al abandonar el pago. Mientras publishedApiUrl esté vacío, solamente las páginas locales usan 127.0.0.1.
- administrador/.env.example: configuración de CORS, origen público de fotografías y TLS de MySQL. Las credenciales reales nunca se incluyen en Git ni en JavaScript.

## Pasos pendientes con las cuentas

1. Crear MySQL Free en Aiven. Guardar de forma privada host, puerto, usuario, contraseña, base y certificado CA. Importar el esquema y los datos existentes de hotel_reservas; no comenzar con una base vacía que pierda las habitaciones y cuentas.
2. Configurar variables privadas del servicio Render usando esos datos. MYSQL_SSL=true y MYSQL_SSL_CA_PEM contiene el certificado CA. HOTEL_ALLOWED_ORIGINS incluye https://jordy052.github.io (sin ruta de repositorio).
3. Configurar HOTEL_PUBLIC_BASE_URL con el origen HTTPS real asignado por Render. Poner esa misma dirección terminada en /api como publishedApiUrl en configuracion.js.
4. Comprobar /api/health, listado y fotografías, acceso de invitados, autenticación, registro con código, reserva y cancelación antes de declarar la publicación terminada.
5. Conectar las aplicaciones de administración y recepción a la MISMA base MySQL remota mediante TLS; mantener respaldo local y no borrar la base anterior durante la migración.

## Dependencias que también requieren adaptación

- Fotografías: actualmente sus rutas apuntan a archivos locales de Windows. El disco gratuito de Render es temporal. Hay que migrar esas imágenes a almacenamiento persistente y adaptar la carga desde administración; copiar solo las tablas no basta.
- Correo: Render Free bloquea los puertos SMTP 25, 465 y 587. El envío actual por Gmail debe usar un transporte HTTPS autorizado antes de que el registro y la recuperación funcionen en ese alojamiento. No desactivar los códigos para evitar esta limitación.
- Sesiones y códigos: la API los conserva en memoria; usar una sola instancia. Reiniciar o suspender el servicio cierra esas sesiones y descarta códigos pendientes; para conservarlos entre reinicios hace falta almacenamiento compartido.
- Render Free se suspende tras inactividad y puede tardar cerca de un minuto en despertar. Aiven Free tiene límites de almacenamiento y conexiones. Son planes para pruebas y demostraciones, no una garantía de disponibilidad continua.

Referencias: https://render.com/docs/free · https://render.com/docs/web-services · https://aiven.io/docs/products/mysql/concepts/mysql-free-tier
