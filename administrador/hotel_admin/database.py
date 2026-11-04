import ssl
from sqlalchemy import URL, create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from hotel_admin import config
from hotel_admin.models import AppUser, Base, Permission, Role, BookingHold, RoomPhotoAsset
from hotel_admin.security import hash_password


engine: Engine | None = None
SessionLocal = sessionmaker(expire_on_commit=False)

REQUIRED_ROLE_NAMES = ("Usuario", "Administrador", "Recepcionista")
RECEPTION_PERMISSION_CODES = ("reservations", "rooms", "guests", "payments")


def _database_url() -> URL:
    if config.DATABASE_URL:
        url = make_url(config.DATABASE_URL)
        if url.drivername != "mysql+pymysql":
            raise RuntimeError("Esta aplicación solo admite MySQL mediante PyMySQL.")
        return url
    if not config.MYSQL_USER:
        raise RuntimeError(
            "Falta configurar MYSQL_USER en el archivo .env. "
            "Configura los datos del servidor MySQL y vuelve a iniciar la aplicación."
        )
    if not config.MYSQL_DATABASE:
        raise RuntimeError("Falta configurar MYSQL_DATABASE en el archivo .env.")
    return URL.create(
        "mysql+pymysql",
        username=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        database=config.MYSQL_DATABASE,
        query={"charset": "utf8mb4"},
    )


def _connection_options() -> dict:
    options = {"connect_timeout": config.MYSQL_CONNECT_TIMEOUT}
    if config.MYSQL_SSL:
        context = ssl.create_default_context(cafile=config.MYSQL_SSL_CA or None)
        if config.MYSQL_SSL_CA_PEM:
            context.load_verify_locations(cadata=config.MYSQL_SSL_CA_PEM)
        # Keep certificate and hostname verification enabled for the remote database.
        options["ssl"] = context
    return options


def initialize_database() -> None:
    """Conecta con MySQL y valida el esquema creado desde MySQL Workbench."""
    global engine
    candidate = create_engine(
        _database_url(),
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args=_connection_options(),
    )
    try:
        with candidate.connect() as connection:
            connection.execute(text("SELECT 1"))
        BookingHold.__table__.create(candidate, checkfirst=True)
        RoomPhotoAsset.__table__.create(candidate, checkfirst=True)
        _validate_existing_schema(candidate)
        _ensure_initial_admin(candidate)
    except Exception:
        candidate.dispose()
        raise
    engine = candidate
    SessionLocal.configure(bind=candidate)
    from hotel_admin.billing import convert_legacy_simulations
    result = convert_legacy_simulations(SessionLocal)
    if result["converted"]:
        print(f"Simulación: {result['converted']} reservas anteriores convertidas; {result['refunded']} reembolsos completos reconstruidos.")


def _validate_existing_schema(database_engine: Engine) -> None:
    inspector = inspect(database_engine)
    existing_tables = set(inspector.get_table_names())
    required_tables = set(Base.metadata.tables)
    missing_tables = sorted(required_tables - existing_tables)
    if missing_tables:
        names = ", ".join(missing_tables)
        raise RuntimeError(
            f"Faltan tablas en MySQL: {names}. "
            "Ejecuta sql/01_crear_esquema.sql desde MySQL Workbench."
        )

    missing_columns: list[str] = []
    for table_name, model_table in Base.metadata.tables.items():
        actual_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        absent = sorted(set(model_table.columns.keys()) - actual_columns)
        if absent:
            missing_columns.append(f"{table_name}: {', '.join(absent)}")
    if missing_columns:
        details = "; ".join(missing_columns)
        raise RuntimeError(
            f"El esquema MySQL no coincide con los modelos de la app ({details}). "
            "Revisa sql/01_crear_esquema.sql en MySQL Workbench."
        )

    with Session(database_engine) as session:
        roles = set(session.scalars(select(Role.name)).all())
        missing_roles = sorted(set(REQUIRED_ROLE_NAMES) - roles)
        permissions = set(session.scalars(select(Permission.code)).all())
        missing_permissions = sorted(set(RECEPTION_PERMISSION_CODES) - permissions)
    if missing_roles or missing_permissions:
        details = []
        if missing_roles:
            details.append(f"roles: {', '.join(missing_roles)}")
        if missing_permissions:
            details.append(f"permisos: {', '.join(missing_permissions)}")
        raise RuntimeError(
            f"Faltan datos de configuración en MySQL ({'; '.join(details)}). "
            "Ejecuta el script desde MySQL Workbench."
        )


def _ensure_initial_admin(database_engine: Engine) -> None:
    """Crea la primera cuenta administradora sin modificar el esquema ni los roles."""
    with Session(database_engine) as session:
        admin_role = session.scalar(
            select(Role).where(Role.name == "Administrador")
        )
        existing_admin = session.scalar(
            select(AppUser.id)
            .where(AppUser.role_id == admin_role.id)
            .limit(1)
        )
        if existing_admin is not None:
            return
        if not config.BOOTSTRAP_ADMIN_PASSWORD:
            raise RuntimeError(
                "MySQL está conectado, pero aún no hay una cuenta administradora. "
                "Define HOTEL_BOOTSTRAP_ADMIN_PASSWORD en .env para crear la cuenta inicial."
            )
        collision = session.scalar(
            select(AppUser.id).where(
                func.lower(AppUser.email) == config.BOOTSTRAP_ADMIN_EMAIL
            )
        )
        if collision is not None:
            raise RuntimeError(
                "El correo inicial ya existe con otro rol. "
                "El administrador debe tener un correo propio."
            )
        session.add(
            AppUser(
                username=config.BOOTSTRAP_ADMIN_NAME,
                email=config.BOOTSTRAP_ADMIN_EMAIL,
                password_hash=hash_password(config.BOOTSTRAP_ADMIN_PASSWORD),
                phone=None,
                active=True,
                role=admin_role,
            )
        )
        session.commit()
