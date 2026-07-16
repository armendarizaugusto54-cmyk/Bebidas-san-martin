from datetime import datetime
import hashlib
import hmac
import os
import secrets
import shutil
import sqlite3

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bebidas.db")

app = Flask(__name__)
app.secret_key = os.environ.get("BEBIDAS_SECRET", "cambiar-esta-clave")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RENDER") == "true",
    SESSION_PERMANENT=False,
)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rows(sql, params=()):
    with db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def one(sql, params=()):
    with db() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def execute(sql, params=()):
    with db() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def money(value):
    try:
        return float(str(value or 0).replace(",", "."))
    except ValueError:
        return 0.0


def calcular_precio_venta(precio_compra, ganancia, redondear=False):
    precio = money(precio_compra) * (1 + money(ganancia) / 100)
    return float(round(precio)) if redondear else round(precio, 2)


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password, stored):
    stored = stored or ""
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, salt, digest = stored.split("$", 2)
        except ValueError:
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
        return hmac.compare_digest(candidate, digest)
    return hmac.compare_digest(password, stored)


def audit(action, detail=""):
    user = session.get("user") or {}
    execute(
        "INSERT INTO auditoria(fecha,usuario,accion,detalle) VALUES(?,?,?,?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user.get("usuario", "sistema"), action, str(detail)[:500]),
    )


def ensure_column(conn, table, column, definition):
    columnas = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columnas:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_schema():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                usuario TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                rol TEXT NOT NULL DEFAULT 'CAJERO',
                activo INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                ganancia REAL DEFAULT 30
            );
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                categoria_id INTEGER,
                marca TEXT,
                precio_compra REAL DEFAULT 0,
                precio_venta REAL DEFAULT 0,
                stock REAL DEFAULT 0,
                stock_minimo REAL DEFAULT 0,
                activo INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT,
                whatsapp TEXT,
                direccion TEXT,
                localidad TEXT,
                cuit TEXT,
                email TEXT,
                limite_credito REAL DEFAULT 0,
                saldo REAL DEFAULT 0,
                activo INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                cliente_id INTEGER,
                tipo TEXT,
                total REAL,
                usuario TEXT
            );
            CREATE TABLE IF NOT EXISTS venta_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venta_id INTEGER,
                producto_id INTEGER,
                cantidad REAL,
                precio REAL,
                subtotal REAL
            );
            CREATE TABLE IF NOT EXISTS cuenta_corriente (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER,
                fecha TEXT,
                comprobante TEXT,
                concepto TEXT,
                debe REAL DEFAULT 0,
                haber REAL DEFAULT 0,
                saldo REAL DEFAULT 0,
                observaciones TEXT
            );
            CREATE TABLE IF NOT EXISTS caja (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                estado TEXT DEFAULT 'ABIERTA',
                apertura REAL DEFAULT 0,
                efectivo REAL DEFAULT 0,
                transferencia REAL DEFAULT 0,
                debito REAL DEFAULT 0,
                credito REAL DEFAULT 0,
                posnet REAL DEFAULT 0,
                cuenta_corriente REAL DEFAULT 0,
                ingresos REAL DEFAULT 0,
                gastos REAL DEFAULT 0,
                cierre REAL DEFAULT 0,
                diferencia REAL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS caja_movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                caja_id INTEGER,
                fecha TEXT,
                tipo TEXT,
                descripcion TEXT,
                importe REAL
            );
            CREATE TABLE IF NOT EXISTS caja_arqueos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                caja_id INTEGER,
                fecha TEXT,
                usuario TEXT,
                efectivo_sistema REAL,
                efectivo_contado REAL,
                transferencia_sistema REAL,
                transferencia_contado REAL,
                debito_sistema REAL,
                debito_contado REAL,
                credito_sistema REAL,
                credito_contado REAL,
                posnet_sistema REAL,
                posnet_contado REAL,
                total_sistema REAL,
                total_contado REAL,
                diferencia REAL,
                observaciones TEXT,
                corregido INTEGER DEFAULT 0,
                usuario_correccion TEXT,
                motivo_correccion TEXT
            );
            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                usuario TEXT,
                accion TEXT,
                detalle TEXT
            );
            CREATE TABLE IF NOT EXISTS permisos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                modulo TEXT NOT NULL,
                ver INTEGER NOT NULL DEFAULT 0,
                agregar INTEGER NOT NULL DEFAULT 0,
                editar INTEGER NOT NULL DEFAULT 0,
                eliminar INTEGER NOT NULL DEFAULT 0,
                UNIQUE(usuario_id, modulo)
            );

            CREATE TABLE IF NOT EXISTS proveedores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                cuit TEXT,
                telefono TEXT,
                whatsapp TEXT,
                direccion TEXT,
                localidad TEXT,
                email TEXT,
                observaciones TEXT,
                saldo REAL DEFAULT 0,
                activo INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS compras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                proveedor_id INTEGER,
                comprobante TEXT,
                tipo_pago TEXT,
                total REAL DEFAULT 0,
                estado TEXT DEFAULT 'ACTIVA',
                usuario TEXT,
                observaciones TEXT,
                motivo_anulacion TEXT,
                usuario_anulacion TEXT,
                fecha_anulacion TEXT
            );
            CREATE TABLE IF NOT EXISTS compra_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                compra_id INTEGER,
                producto_id INTEGER,
                cantidad REAL DEFAULT 0,
                costo REAL DEFAULT 0,
                subtotal REAL DEFAULT 0,
                costo_anterior REAL DEFAULT 0,
                venta_anterior REAL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS proveedor_cuenta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proveedor_id INTEGER,
                fecha TEXT,
                comprobante TEXT,
                concepto TEXT,
                debe REAL DEFAULT 0,
                haber REAL DEFAULT 0,
                saldo REAL DEFAULT 0,
                observaciones TEXT
            );
            """
        )
        if not conn.execute("SELECT id FROM usuarios LIMIT 1").fetchone():
            conn.execute(
                "INSERT INTO usuarios(nombre,usuario,password,rol,activo) VALUES(?,?,?,?,1)",
                ("Selene", "selene", hash_password("1234"), "ADMIN"),
            )
            conn.execute(
                "INSERT INTO usuarios(nombre,usuario,password,rol,activo) VALUES(?,?,?,?,1)",
                ("Vale", "vale", hash_password("12345"), "CAJERO"),
            )
        if not conn.execute("SELECT id FROM categorias LIMIT 1").fetchone():
            conn.execute("INSERT INTO categorias(nombre,ganancia) VALUES('Bebidas',30)")
            conn.execute("INSERT INTO categorias(nombre,ganancia) VALUES('Cervezas',35)")

        ensure_column(conn, "caja", "usuario_apertura", "TEXT")
        ensure_column(conn, "caja", "usuario_cierre", "TEXT")
        ensure_column(conn, "caja", "hora_apertura", "TEXT")
        ensure_column(conn, "caja", "hora_cierre", "TEXT")
        ensure_column(conn, "caja", "observaciones_apertura", "TEXT")

        ensure_column(conn, "caja_arqueos", "cuenta_corriente_sistema", "REAL DEFAULT 0")
        ensure_column(conn, "caja_arqueos", "cuenta_corriente_contado", "REAL DEFAULT 0")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS caja_billetes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                caja_id INTEGER,
                denominacion REAL,
                cantidad INTEGER DEFAULT 0,
                subtotal REAL DEFAULT 0
            )
            """
        )

        modulos = ("Dashboard", "Ventas", "Productos", "Clientes", "Caja", "Compras", "Proveedores", "Reportes", "Usuarios")
        usuarios_existentes = conn.execute("SELECT id,rol FROM usuarios").fetchall()
        for usuario in usuarios_existentes:
            for modulo in modulos:
                existe = conn.execute(
                    "SELECT id FROM permisos WHERE usuario_id=? AND modulo=?",
                    (usuario["id"], modulo),
                ).fetchone()
                if existe:
                    continue

                if usuario["rol"] == "ADMIN":
                    valores = (1, 1, 1, 1)
                else:
                    if modulo in {"Dashboard", "Ventas", "Productos", "Clientes", "Caja", "Compras", "Proveedores", "Reportes"}:
                        valores = (1, 1, 0, 0)
                    else:
                        valores = (0, 0, 0, 0)

                conn.execute(
                    """
                    INSERT INTO permisos(usuario_id,modulo,ver,agregar,editar,eliminar)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (usuario["id"], modulo, *valores),
                )
        conn.commit()


ensure_schema()


def user_permissions(usuario_id):
    permisos = rows(
        """
        SELECT modulo,ver,agregar,editar,eliminar
        FROM permisos
        WHERE usuario_id=?
        ORDER BY modulo
        """,
        (usuario_id,),
    )
    return {
        permiso["modulo"]: {
            "ver": bool(permiso["ver"]),
            "agregar": bool(permiso["agregar"]),
            "editar": bool(permiso["editar"]),
            "eliminar": bool(permiso["eliminar"]),
        }
        for permiso in permisos
    }


def can(module, action="ver"):
    user = session.get("user")
    if not user:
        return False

    if user["rol"] == "ADMIN":
        return True

    action = "editar" if action == "modificar" else action
    if action not in {"ver", "agregar", "editar", "eliminar"}:
        return False

    permiso = one(
        f"SELECT {action} permitido FROM permisos WHERE usuario_id=? AND modulo=?",
        (user["id"], module),
    )
    return bool(permiso and permiso["permitido"])


def forbidden():
    return jsonify({"error": "No tenes permiso para esta accion."}), 403


@app.before_request
def guard():
    if request.endpoint in {"login", "static"}:
        return None
    if "user" not in session:
        return redirect(url_for("login"))
    return None


@app.after_request
def no_cache_paginas_privadas(response):
    if session.get("user"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        user = one("SELECT * FROM usuarios WHERE usuario=? AND activo=1", (usuario,))
        if user and verify_password(password, user["password"]):
            session.clear()
            session.permanent = False
            session["user"] = {
                "id": user["id"],
                "nombre": user["nombre"],
                "usuario": user["usuario"],
                "rol": user["rol"],
            }
            session["fresh_login"] = True
            audit("login", "Ingreso correcto")
            return redirect(url_for("index"))
        audit("login_fallido", usuario)
        error = "Usuario o contrasena incorrectos."
    return render_template("login.html", error=error)


@app.get("/logout")
def logout():
    audit("logout", "Salida")
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
def index():
    fresh_login = bool(session.pop("fresh_login", False))
    return render_template(
        "index.html",
        user=session["user"],
        fresh_login=fresh_login,
    )


@app.get("/api/me")
def me():
    user = session["user"]
    return jsonify({
        "user": user,
        "permissions": user_permissions(user["id"]),
    })


MODULOS_PERMISOS = (
    "Dashboard",
    "Ventas",
    "Productos",
    "Clientes",
    "Caja",
    "Reportes",
    "Compras",
    "Proveedores",
    "Usuarios",
)


def require_admin():
    return bool(session.get("user") and session["user"]["rol"] == "ADMIN")


@app.get("/api/usuarios")
def listar_usuarios():
    if not require_admin():
        return forbidden()

    usuarios = rows(
        """
        SELECT id,nombre,usuario,rol,activo
        FROM usuarios
        ORDER BY nombre
        """
    )

    for usuario in usuarios:
        usuario["permisos"] = user_permissions(usuario["id"])

    return jsonify(usuarios)


@app.post("/api/usuarios")
def guardar_usuario():
    if not require_admin():
        return forbidden()

    data = request.json or {}
    usuario_id = data.get("id")
    nombre = data.get("nombre", "").strip()
    usuario = data.get("usuario", "").strip()
    password = data.get("password", "")
    rol = data.get("rol", "CAJERO").upper()
    activo = 1 if int(data.get("activo", 1) or 0) else 0

    if not nombre or not usuario:
        return jsonify({"error": "Nombre y usuario son obligatorios."}), 400
    if rol not in {"ADMIN", "CAJERO"}:
        return jsonify({"error": "Rol inválido."}), 400
    if not usuario_id and not password:
        return jsonify({"error": "Ingrese una contraseña para el usuario nuevo."}), 400

    if usuario_id and int(usuario_id) == int(session["user"]["id"]):
        if not activo:
            return jsonify({"error": "No puede desactivar su propio usuario."}), 400
        if rol != "ADMIN":
            return jsonify({"error": "No puede quitarse su propio rol de administrador."}), 400

    try:
        with db() as conn:
            if usuario_id:
                if password:
                    conn.execute(
                        """
                        UPDATE usuarios
                        SET nombre=?,usuario=?,password=?,rol=?,activo=?
                        WHERE id=?
                        """,
                        (nombre, usuario, hash_password(password), rol, activo, usuario_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE usuarios
                        SET nombre=?,usuario=?,rol=?,activo=?
                        WHERE id=?
                        """,
                        (nombre, usuario, rol, activo, usuario_id),
                    )
            else:
                usuario_id = conn.execute(
                    """
                    INSERT INTO usuarios(nombre,usuario,password,rol,activo)
                    VALUES(?,?,?,?,?)
                    """,
                    (nombre, usuario, hash_password(password), rol, activo),
                ).lastrowid

                for modulo in MODULOS_PERMISOS:
                    valores = (1, 1, 1, 1) if rol == "ADMIN" else (
                        (1, 1, 0, 0)
                        if modulo in {"Dashboard", "Ventas", "Productos", "Clientes", "Caja", "Compras", "Proveedores", "Reportes"}
                        else (0, 0, 0, 0)
                    )
                    conn.execute(
                        """
                        INSERT INTO permisos(usuario_id,modulo,ver,agregar,editar,eliminar)
                        VALUES(?,?,?,?,?,?)
                        """,
                        (usuario_id, modulo, *valores),
                    )

            if rol == "ADMIN":
                for modulo in MODULOS_PERMISOS:
                    conn.execute(
                        """
                        INSERT INTO permisos(usuario_id,modulo,ver,agregar,editar,eliminar)
                        VALUES(?,?,1,1,1,1)
                        ON CONFLICT(usuario_id,modulo)
                        DO UPDATE SET ver=1,agregar=1,editar=1,eliminar=1
                        """,
                        (usuario_id, modulo),
                    )

            conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Ese nombre de usuario ya existe."}), 400

    audit("usuario_guardado", f"{usuario} - {rol} - activo {activo}")
    return jsonify({"ok": True, "id": usuario_id})


@app.delete("/api/usuarios/<int:usuario_id>")
def eliminar_usuario(usuario_id):
    if not require_admin():
        return forbidden()

    if usuario_id == int(session["user"]["id"]):
        return jsonify({"error": "No puede eliminar su propio usuario."}), 400

    usuario = one("SELECT * FROM usuarios WHERE id=?", (usuario_id,))
    if not usuario:
        return jsonify({"error": "Usuario inexistente."}), 404

    with db() as conn:
        conn.execute("DELETE FROM permisos WHERE usuario_id=?", (usuario_id,))
        conn.execute("DELETE FROM usuarios WHERE id=?", (usuario_id,))
        conn.commit()

    audit("usuario_eliminado", usuario["usuario"])
    return jsonify({"ok": True})


@app.put("/api/usuarios/<int:usuario_id>/permisos")
def guardar_permisos(usuario_id):
    if not require_admin():
        return forbidden()

    usuario = one("SELECT * FROM usuarios WHERE id=?", (usuario_id,))
    if not usuario:
        return jsonify({"error": "Usuario inexistente."}), 404

    data = request.json or {}
    permisos = data.get("permisos") or {}

    if usuario["rol"] == "ADMIN":
        permisos = {
            modulo: {"ver": 1, "agregar": 1, "editar": 1, "eliminar": 1}
            for modulo in MODULOS_PERMISOS
        }

    with db() as conn:
        for modulo in MODULOS_PERMISOS:
            valores = permisos.get(modulo) or {}
            ver = 1 if valores.get("ver") else 0
            agregar = 1 if valores.get("agregar") else 0
            editar = 1 if valores.get("editar") else 0
            eliminar = 1 if valores.get("eliminar") else 0

            if not ver:
                agregar = editar = eliminar = 0

            conn.execute(
                """
                INSERT INTO permisos(usuario_id,modulo,ver,agregar,editar,eliminar)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(usuario_id,modulo)
                DO UPDATE SET
                    ver=excluded.ver,
                    agregar=excluded.agregar,
                    editar=excluded.editar,
                    eliminar=excluded.eliminar
                """,
                (usuario_id, modulo, ver, agregar, editar, eliminar),
            )
        conn.commit()

    audit("permisos_actualizados", f"Usuario {usuario['usuario']}")
    return jsonify({"ok": True})


@app.get("/api/options")
def options():
    return jsonify(
        {
            "categorias": rows("SELECT * FROM categorias ORDER BY nombre"),
            "clientes": rows("SELECT id,nombre,saldo,limite_credito FROM clientes WHERE activo=1 ORDER BY nombre"),
            "productos": rows(
                """
                SELECT p.*, c.nombre categoria, COALESCE(c.ganancia,0) ganancia_categoria
                FROM productos p
                LEFT JOIN categorias c ON c.id=p.categoria_id
                WHERE p.activo=1
                ORDER BY p.nombre
                """
            ),
            "proveedores": rows(
                "SELECT id,nombre,saldo FROM proveedores WHERE activo=1 ORDER BY nombre"
            ),
        }
    )



@app.get("/api/proveedores")
def listar_proveedores():
    if not can("Proveedores"):
        return forbidden()

    return jsonify(rows(
        """
        SELECT p.*,
               COALESCE((SELECT COUNT(*) FROM compras c WHERE c.proveedor_id=p.id AND c.estado='ACTIVA'),0) compras,
               COALESCE((SELECT SUM(total) FROM compras c WHERE c.proveedor_id=p.id AND c.estado='ACTIVA'),0) total_comprado
        FROM proveedores p
        WHERE p.activo=1
        ORDER BY p.nombre
        """
    ))


@app.post("/api/proveedores")
def guardar_proveedor():
    if not can("Proveedores", "agregar"):
        return forbidden()

    data = request.json or {}
    proveedor_id = data.get("id")
    nombre = data.get("nombre", "").strip()
    cuit = data.get("cuit", "").strip()

    if not nombre:
        return jsonify({"error": "El nombre del proveedor es obligatorio."}), 400

    if cuit:
        duplicado = one(
            "SELECT id FROM proveedores WHERE cuit=? AND activo=1 AND id<>COALESCE(?,0)",
            (cuit, proveedor_id),
        )
        if duplicado:
            return jsonify({"error": "Ya existe un proveedor activo con ese CUIT."}), 400

    params = (
        nombre,
        cuit,
        data.get("telefono", "").strip(),
        data.get("whatsapp", "").strip(),
        data.get("direccion", "").strip(),
        data.get("localidad", "").strip(),
        data.get("email", "").strip(),
        data.get("observaciones", "").strip(),
    )

    if proveedor_id:
        if not can("Proveedores", "editar"):
            return forbidden()
        execute(
            """
            UPDATE proveedores
            SET nombre=?,cuit=?,telefono=?,whatsapp=?,direccion=?,localidad=?,email=?,observaciones=?
            WHERE id=?
            """,
            params + (proveedor_id,),
        )
        audit("proveedor_editado", nombre)
    else:
        proveedor_id = execute(
            """
            INSERT INTO proveedores(nombre,cuit,telefono,whatsapp,direccion,localidad,email,observaciones,saldo,activo)
            VALUES(?,?,?,?,?,?,?,?,0,1)
            """,
            params,
        )
        audit("proveedor_creado", nombre)

    return jsonify({"ok": True, "id": proveedor_id})


@app.delete("/api/proveedores/<int:proveedor_id>")
def baja_proveedor(proveedor_id):
    if not can("Proveedores", "eliminar"):
        return forbidden()

    proveedor = one("SELECT * FROM proveedores WHERE id=?", (proveedor_id,))
    if not proveedor:
        return jsonify({"error": "Proveedor inexistente."}), 404
    if abs(money(proveedor["saldo"])) > 0.009:
        return jsonify({"error": "No se puede dar de baja un proveedor con saldo pendiente."}), 400

    execute("UPDATE proveedores SET activo=0 WHERE id=?", (proveedor_id,))
    audit("proveedor_baja", proveedor["nombre"])
    return jsonify({"ok": True})


@app.get("/api/proveedores/<int:proveedor_id>/cuenta")
def cuenta_proveedor(proveedor_id):
    if not can("Proveedores"):
        return forbidden()

    proveedor = one("SELECT * FROM proveedores WHERE id=?", (proveedor_id,))
    if not proveedor:
        return jsonify({"error": "Proveedor inexistente."}), 404

    movimientos = rows(
        """
        SELECT *
        FROM proveedor_cuenta
        WHERE proveedor_id=?
        ORDER BY datetime(fecha) DESC, id DESC
        """,
        (proveedor_id,),
    )

    resumen = one(
        """
        SELECT COALESCE(SUM(debe),0) debe,
               COALESCE(SUM(haber),0) haber,
               COUNT(*) movimientos
        FROM proveedor_cuenta
        WHERE proveedor_id=?
        """,
        (proveedor_id,),
    )

    compras = rows(
        """
        SELECT id,fecha,comprobante,tipo_pago,total,estado,usuario
        FROM compras
        WHERE proveedor_id=?
        ORDER BY datetime(fecha) DESC,id DESC
        LIMIT 100
        """,
        (proveedor_id,),
    )

    return jsonify({
        "proveedor": proveedor,
        "movimientos": movimientos,
        "resumen": resumen,
        "compras": compras,
    })


@app.post("/api/proveedores/<int:proveedor_id>/pago")
def pago_proveedor(proveedor_id):
    if not can("Proveedores", "agregar"):
        return forbidden()

    proveedor = one("SELECT * FROM proveedores WHERE id=? AND activo=1", (proveedor_id,))
    if not proveedor:
        return jsonify({"error": "Proveedor inexistente."}), 404

    data = request.json or {}
    importe = money(data.get("importe"))
    if importe <= 0:
        return jsonify({"error": "El importe debe ser mayor a cero."}), 400

    saldo_nuevo = round(money(proveedor["saldo"]) - importe, 2)

    with db() as conn:
        conn.execute("UPDATE proveedores SET saldo=? WHERE id=?", (saldo_nuevo, proveedor_id))
        conn.execute(
            """
            INSERT INTO proveedor_cuenta
            (proveedor_id,fecha,comprobante,concepto,debe,haber,saldo,observaciones)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                proveedor_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                data.get("comprobante", "").strip(),
                "PAGO",
                0,
                importe,
                saldo_nuevo,
                data.get("observaciones", "").strip(),
            ),
        )
        conn.commit()

    audit("pago_proveedor", f"{proveedor['nombre']} - {importe}")
    return jsonify({"ok": True, "saldo": saldo_nuevo})


@app.get("/api/compras")
def listar_compras():
    if not can("Compras"):
        return forbidden()

    proveedor_id = request.args.get("proveedor_id")
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")

    filtros = ["1=1"]
    params = []

    if proveedor_id:
        filtros.append("c.proveedor_id=?")
        params.append(proveedor_id)
    if desde:
        filtros.append("date(c.fecha)>=date(?)")
        params.append(desde)
    if hasta:
        filtros.append("date(c.fecha)<=date(?)")
        params.append(hasta)

    return jsonify(rows(
        f"""
        SELECT c.*,p.nombre proveedor
        FROM compras c
        JOIN proveedores p ON p.id=c.proveedor_id
        WHERE {' AND '.join(filtros)}
        ORDER BY datetime(c.fecha) DESC,c.id DESC
        LIMIT 300
        """,
        params,
    ))


@app.post("/api/compras")
def guardar_compra():
    if not can("Compras", "agregar"):
        return forbidden()

    data = request.json or {}
    proveedor_id = data.get("proveedor_id")
    items = data.get("items") or []
    tipo_pago = data.get("tipo_pago", "EFECTIVO").upper()
    actualizar_costos = bool(data.get("actualizar_costos", True))
    recalcular_venta = bool(data.get("recalcular_venta", True))

    if not proveedor_id:
        return jsonify({"error": "Seleccione un proveedor."}), 400
    if not items:
        return jsonify({"error": "Agregue al menos un producto a la compra."}), 400
    if tipo_pago not in {"EFECTIVO", "TRANSFERENCIA", "CUENTA CORRIENTE", "OTRO"}:
        return jsonify({"error": "Forma de pago inválida."}), 400

    proveedor = one("SELECT * FROM proveedores WHERE id=? AND activo=1", (proveedor_id,))
    if not proveedor:
        return jsonify({"error": "Proveedor inexistente."}), 404

    productos_validos = []
    total = 0

    for item in items:
        producto = one(
            """
            SELECT p.*,COALESCE(c.ganancia,0) ganancia_categoria
            FROM productos p
            LEFT JOIN categorias c ON c.id=p.categoria_id
            WHERE p.id=? AND p.activo=1
            """,
            (item.get("producto_id"),),
        )
        if not producto:
            return jsonify({"error": "Uno de los productos ya no existe."}), 400

        cantidad = money(item.get("cantidad"))
        costo = money(item.get("costo"))
        if cantidad <= 0 or costo < 0:
            return jsonify({"error": f"Cantidad o costo inválido para {producto['nombre']}."}), 400

        subtotal = round(cantidad * costo, 2)
        total += subtotal
        productos_validos.append((producto, cantidad, costo, subtotal))

    total = round(total, 2)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with db() as conn:
        compra_id = conn.execute(
            """
            INSERT INTO compras
            (fecha,proveedor_id,comprobante,tipo_pago,total,estado,usuario,observaciones)
            VALUES(?,?,?,?,?,'ACTIVA',?,?)
            """,
            (
                ahora,
                proveedor_id,
                data.get("comprobante", "").strip(),
                tipo_pago,
                total,
                session["user"]["usuario"],
                data.get("observaciones", "").strip(),
            ),
        ).lastrowid

        for producto, cantidad, costo, subtotal in productos_validos:
            conn.execute(
                """
                INSERT INTO compra_items
                (compra_id,producto_id,cantidad,costo,subtotal,costo_anterior,venta_anterior)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    compra_id,
                    producto["id"],
                    cantidad,
                    costo,
                    subtotal,
                    money(producto["precio_compra"]),
                    money(producto["precio_venta"]),
                ),
            )

            nuevo_costo = costo if actualizar_costos else money(producto["precio_compra"])
            nueva_venta = money(producto["precio_venta"])

            if actualizar_costos and recalcular_venta:
                nueva_venta = calcular_precio_venta(
                    nuevo_costo,
                    money(producto["ganancia_categoria"]),
                )

            conn.execute(
                """
                UPDATE productos
                SET stock=COALESCE(stock,0)+?,
                    precio_compra=?,
                    precio_venta=?
                WHERE id=?
                """,
                (cantidad, nuevo_costo, nueva_venta, producto["id"]),
            )

        if tipo_pago == "CUENTA CORRIENTE":
            saldo_nuevo = round(money(proveedor["saldo"]) + total, 2)
            conn.execute("UPDATE proveedores SET saldo=? WHERE id=?", (saldo_nuevo, proveedor_id))
            conn.execute(
                """
                INSERT INTO proveedor_cuenta
                (proveedor_id,fecha,comprobante,concepto,debe,haber,saldo,observaciones)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    proveedor_id,
                    ahora,
                    str(compra_id),
                    "COMPRA",
                    total,
                    0,
                    saldo_nuevo,
                    data.get("observaciones", "").strip(),
                ),
            )

        conn.commit()

    audit("compra_registrada", f"Compra {compra_id} - {proveedor['nombre']} - {total}")
    return jsonify({"ok": True, "compra_id": compra_id, "total": total})


@app.get("/api/compras/<int:compra_id>")
def detalle_compra(compra_id):
    if not can("Compras"):
        return forbidden()

    compra = one(
        """
        SELECT c.*,p.nombre proveedor,p.cuit proveedor_cuit,p.telefono proveedor_telefono
        FROM compras c
        JOIN proveedores p ON p.id=c.proveedor_id
        WHERE c.id=?
        """,
        (compra_id,),
    )
    if not compra:
        return jsonify({"error": "Compra inexistente."}), 404

    items = rows(
        """
        SELECT i.*,p.codigo,p.nombre producto
        FROM compra_items i
        JOIN productos p ON p.id=i.producto_id
        WHERE i.compra_id=?
        ORDER BY i.id
        """,
        (compra_id,),
    )

    return jsonify({"compra": compra, "items": items})


@app.post("/api/compras/<int:compra_id>/anular")
def anular_compra(compra_id):
    if not can("Compras", "eliminar"):
        return forbidden()

    data = request.json or {}
    motivo = data.get("motivo", "").strip()
    if not motivo:
        return jsonify({"error": "Ingrese el motivo de la anulación."}), 400

    compra = one("SELECT * FROM compras WHERE id=?", (compra_id,))
    if not compra:
        return jsonify({"error": "Compra inexistente."}), 404
    if compra["estado"] == "ANULADA":
        return jsonify({"error": "La compra ya está anulada."}), 400

    items = rows("SELECT * FROM compra_items WHERE compra_id=?", (compra_id,))
    proveedor = one("SELECT * FROM proveedores WHERE id=?", (compra["proveedor_id"],))

    with db() as conn:
        for item in items:
            producto = conn.execute("SELECT stock FROM productos WHERE id=?", (item["producto_id"],)).fetchone()
            stock_actual = money(producto["stock"]) if producto else 0
            if stock_actual < money(item["cantidad"]):
                return jsonify({
                    "error": "No se puede anular: uno de los productos ya no tiene stock suficiente para devolver."
                }), 400

        for item in items:
            conn.execute(
                """
                UPDATE productos
                SET stock=stock-?,
                    precio_compra=?,
                    precio_venta=?
                WHERE id=?
                """,
                (
                    item["cantidad"],
                    item["costo_anterior"],
                    item["venta_anterior"],
                    item["producto_id"],
                ),
            )

        if compra["tipo_pago"] == "CUENTA CORRIENTE" and proveedor:
            saldo_nuevo = round(money(proveedor["saldo"]) - money(compra["total"]), 2)
            conn.execute("UPDATE proveedores SET saldo=? WHERE id=?", (saldo_nuevo, proveedor["id"]))
            conn.execute(
                """
                INSERT INTO proveedor_cuenta
                (proveedor_id,fecha,comprobante,concepto,debe,haber,saldo,observaciones)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    proveedor["id"],
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    str(compra_id),
                    "ANULACIÓN DE COMPRA",
                    0,
                    compra["total"],
                    saldo_nuevo,
                    motivo,
                ),
            )

        conn.execute(
            """
            UPDATE compras
            SET estado='ANULADA',motivo_anulacion=?,usuario_anulacion=?,fecha_anulacion=?
            WHERE id=?
            """,
            (
                motivo,
                session["user"]["usuario"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                compra_id,
            ),
        )
        conn.commit()

    audit("compra_anulada", f"Compra {compra_id} - {motivo}")
    return jsonify({"ok": True})


@app.get("/api/dashboard")
def dashboard():
    today = datetime.now().strftime("%Y-%m-%d")
    ventas = one("SELECT COUNT(*) cantidad, COALESCE(SUM(total),0) total FROM ventas WHERE date(fecha)=date(?)", (today,))
    caja = one("SELECT * FROM caja WHERE estado='ABIERTA' ORDER BY id DESC LIMIT 1")
    return jsonify(
        {
            "ventas": ventas,
            "productos": one("SELECT COUNT(*) cantidad FROM productos WHERE activo=1")["cantidad"],
            "clientes": one("SELECT COUNT(*) cantidad FROM clientes WHERE activo=1")["cantidad"],
            "stock_bajo": one("SELECT COUNT(*) cantidad FROM productos WHERE activo=1 AND stock<=stock_minimo")["cantidad"],
            "caja": caja or {},
            "top": rows(
                """
                SELECT p.nombre, SUM(i.cantidad) cantidad, SUM(i.subtotal) total
                FROM venta_items i
                JOIN ventas v ON v.id=i.venta_id
                JOIN productos p ON p.id=i.producto_id
                WHERE date(v.fecha)=date(?)
                GROUP BY p.id
                ORDER BY cantidad DESC
                LIMIT 5
                """,
                (today,),
            ),
        }
    )


@app.get("/api/productos")
def productos():
    if not can("Productos"):
        return forbidden()
    return jsonify(rows(
        """
        SELECT p.*, c.nombre categoria, COALESCE(c.ganancia,0) ganancia_categoria
        FROM productos p
        LEFT JOIN categorias c ON c.id=p.categoria_id
        WHERE p.activo=1
        ORDER BY p.nombre
        """
    ))


@app.post("/api/productos")
def save_producto():
    if not can("Productos", "agregar"):
        return forbidden()

    data = request.json or {}
    producto_id = data.get("id")
    codigo = data.get("codigo", "").strip()
    nombre = data.get("nombre", "").strip()
    categoria_id = data.get("categoria_id") or None
    precio_compra = money(data.get("precio_compra"))

    if not codigo or not nombre:
        return jsonify({"error": "Código y nombre son obligatorios."}), 400
    if not categoria_id:
        return jsonify({"error": "Seleccione una categoría."}), 400
    if precio_compra < 0:
        return jsonify({"error": "El precio de compra no puede ser negativo."}), 400

    categoria = one("SELECT id,nombre,ganancia FROM categorias WHERE id=?", (categoria_id,))
    if not categoria:
        return jsonify({"error": "La categoría seleccionada no existe."}), 400

    precio_venta = calcular_precio_venta(precio_compra, categoria["ganancia"])
    params = (
        codigo,
        nombre,
        categoria_id,
        data.get("marca", "").strip(),
        precio_compra,
        precio_venta,
        money(data.get("stock")),
        money(data.get("stock_minimo")),
    )

    try:
        if producto_id:
            execute(
                """
                UPDATE productos
                SET codigo=?,nombre=?,categoria_id=?,marca=?,precio_compra=?,precio_venta=?,stock=?,stock_minimo=?
                WHERE id=?
                """,
                params + (producto_id,),
            )
            audit("producto_editado", f"{nombre} - {categoria['nombre']} - venta {precio_venta}")
        else:
            execute(
                """
                INSERT INTO productos(codigo,nombre,categoria_id,marca,precio_compra,precio_venta,stock,stock_minimo)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                params,
            )
            audit("producto_creado", f"{nombre} - {categoria['nombre']} - venta {precio_venta}")
    except sqlite3.IntegrityError:
        return jsonify({"error": "Ya existe un producto con ese código."}), 400

    return jsonify({
        "ok": True,
        "precio_venta": precio_venta,
        "ganancia": money(categoria["ganancia"]),
    })


@app.delete("/api/productos/<int:producto_id>")
def delete_producto(producto_id):
    if not can("Productos", "eliminar"):
        return forbidden()
    execute("UPDATE productos SET activo=0 WHERE id=?", (producto_id,))
    audit("producto_borrado", producto_id)
    return jsonify({"ok": True})


@app.post("/api/precios/categoria")
def precios_categoria():
    if not can("Productos", "agregar"):
        return forbidden()

    data = request.json or {}
    categoria_id = data.get("categoria_id")
    ganancia = money(data.get("ganancia", data.get("porcentaje")))
    aplicar = int(data.get("aplicar", 0) or 0) == 1
    redondear = int(data.get("redondear", 1) or 0) == 1

    if not categoria_id:
        return jsonify({"error": "Seleccione una categoría."}), 400
    if ganancia < 0:
        return jsonify({"error": "La ganancia no puede ser negativa."}), 400

    categoria = one("SELECT * FROM categorias WHERE id=?", (categoria_id,))
    if not categoria:
        return jsonify({"error": "Categoría inexistente."}), 404

    productos = rows(
        """
        SELECT id,codigo,nombre,precio_compra,precio_venta
        FROM productos
        WHERE activo=1 AND categoria_id=?
        ORDER BY nombre
        """,
        (categoria_id,),
    )

    cambios = []
    for producto in productos:
        anterior = money(producto["precio_venta"])
        nuevo = calcular_precio_venta(producto["precio_compra"], ganancia, redondear)
        cambios.append({
            **producto,
            "anterior": anterior,
            "nuevo": nuevo,
            "diferencia": round(nuevo - anterior, 2),
        })

    if aplicar:
        with db() as conn:
            conn.execute("UPDATE categorias SET ganancia=? WHERE id=?", (ganancia, categoria_id))
            for item in cambios:
                conn.execute(
                    "UPDATE productos SET precio_venta=? WHERE id=?",
                    (item["nuevo"], item["id"]),
                )
            conn.commit()
        audit(
            "categoria_precios_recalculados",
            f"{categoria['nombre']} - ganancia {ganancia}% - {len(cambios)} productos",
        )

    return jsonify({
        "categoria": categoria["nombre"],
        "categoria_id": categoria_id,
        "ganancia": ganancia,
        "cantidad": len(cambios),
        "cambios": cambios,
        "aplicado": aplicar,
    })


@app.get("/api/categorias")
def categorias():
    return jsonify(rows(
        """
        SELECT c.*,
               COUNT(p.id) productos
        FROM categorias c
        LEFT JOIN productos p ON p.categoria_id=c.id AND p.activo=1
        GROUP BY c.id
        ORDER BY c.nombre
        """
    ))


@app.post("/api/categorias")
def save_categoria():
    if not can("Productos", "agregar"):
        return forbidden()

    data = request.json or {}
    categoria_id = data.get("id")
    nombre = data.get("nombre", "").strip()
    ganancia = money(data.get("ganancia", 30))

    if not nombre:
        return jsonify({"error": "El nombre es obligatorio."}), 400
    if ganancia < 0:
        return jsonify({"error": "La ganancia no puede ser negativa."}), 400

    try:
        if categoria_id:
            execute(
                "UPDATE categorias SET nombre=?, ganancia=? WHERE id=?",
                (nombre, ganancia, categoria_id),
            )
            audit("categoria_editada", f"{nombre} - {ganancia}%")
        else:
            categoria_id = execute(
                "INSERT INTO categorias(nombre,ganancia) VALUES(?,?)",
                (nombre, ganancia),
            )
            audit("categoria_creada", f"{nombre} - {ganancia}%")
    except sqlite3.IntegrityError:
        return jsonify({"error": "Ya existe una categoría con ese nombre."}), 400

    return jsonify({"ok": True, "id": categoria_id})


@app.delete("/api/categorias/<int:categoria_id>")
def delete_categoria(categoria_id):
    if not can("Productos", "eliminar"):
        return forbidden()

    categoria = one("SELECT * FROM categorias WHERE id=?", (categoria_id,))
    if not categoria:
        return jsonify({"error": "Categoría inexistente."}), 404

    cantidad = one(
        "SELECT COUNT(*) cantidad FROM productos WHERE categoria_id=? AND activo=1",
        (categoria_id,),
    )["cantidad"]

    if cantidad:
        return jsonify({
            "error": f"No se puede borrar: la categoría tiene {cantidad} producto(s) activo(s)."
        }), 400

    execute("DELETE FROM categorias WHERE id=?", (categoria_id,))
    audit("categoria_borrada", categoria["nombre"])
    return jsonify({"ok": True})


@app.get("/api/clientes")
def clientes():
    if not can("Clientes"):
        return forbidden()

    return jsonify(rows(
        """
        SELECT c.*,
               COALESCE((SELECT COUNT(*) FROM ventas v WHERE v.cliente_id=c.id),0) compras,
               CASE
                   WHEN COALESCE(c.limite_credito,0) <= 0 THEN 0
                   ELSE MAX(COALESCE(c.limite_credito,0) - COALESCE(c.saldo,0), 0)
               END credito_disponible
        FROM clientes c
        WHERE c.activo=1
        ORDER BY c.nombre
        """
    ))


@app.post("/api/clientes")
def save_cliente():
    if not can("Clientes", "agregar"):
        return forbidden()

    data = request.json or {}
    cliente_id = data.get("id")
    nombre = data.get("nombre", "").strip()
    cuit = data.get("cuit", "").strip()
    limite_credito = money(data.get("limite_credito"))

    if not nombre:
        return jsonify({"error": "El nombre es obligatorio."}), 400
    if limite_credito < 0:
        return jsonify({"error": "El límite de crédito no puede ser negativo."}), 400

    params = (
        nombre,
        data.get("telefono", "").strip(),
        data.get("whatsapp", "").strip(),
        data.get("direccion", "").strip(),
        data.get("localidad", "").strip(),
        cuit,
        data.get("email", "").strip(),
        limite_credito,
    )

    if cuit:
        duplicado = one(
            "SELECT id FROM clientes WHERE cuit=? AND activo=1 AND id<>COALESCE(?,0)",
            (cuit, cliente_id),
        )
        if duplicado:
            return jsonify({"error": "Ya existe un cliente activo con ese CUIT/DNI."}), 400

    if cliente_id:
        execute(
            """
            UPDATE clientes
            SET nombre=?,telefono=?,whatsapp=?,direccion=?,localidad=?,cuit=?,email=?,limite_credito=?
            WHERE id=?
            """,
            params + (cliente_id,),
        )
        audit("cliente_editado", nombre)
    else:
        cliente_id = execute(
            """
            INSERT INTO clientes(nombre,telefono,whatsapp,direccion,localidad,cuit,email,limite_credito,saldo,activo)
            VALUES(?,?,?,?,?,?,?,?,0,1)
            """,
            params,
        )
        audit("cliente_creado", nombre)

    return jsonify({"ok": True, "id": cliente_id})


@app.delete("/api/clientes/<int:cliente_id>")
def delete_cliente(cliente_id):
    if not can("Clientes", "eliminar"):
        return forbidden()

    cliente = one("SELECT * FROM clientes WHERE id=?", (cliente_id,))
    if not cliente:
        return jsonify({"error": "Cliente inexistente."}), 404

    if abs(money(cliente["saldo"])) > 0.009:
        return jsonify({"error": "No se puede dar de baja un cliente con saldo pendiente."}), 400

    execute("UPDATE clientes SET activo=0 WHERE id=?", (cliente_id,))
    audit("cliente_baja", cliente["nombre"])
    return jsonify({"ok": True})


@app.get("/api/clientes/<int:cliente_id>/cuenta")
def cuenta(cliente_id):
    cliente = one("SELECT * FROM clientes WHERE id=?", (cliente_id,))
    if not cliente:
        return jsonify({"error": "Cliente inexistente."}), 404

    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()

    filtros = ["cliente_id=?"]
    params = [cliente_id]

    if desde:
        filtros.append("date(fecha)>=date(?)")
        params.append(desde)
    if hasta:
        filtros.append("date(fecha)<=date(?)")
        params.append(hasta)

    where = " AND ".join(filtros)

    movimientos = rows(
        f"""
        SELECT *
        FROM cuenta_corriente
        WHERE {where}
        ORDER BY datetime(fecha) DESC, id DESC
        """,
        params,
    )

    resumen_total = one(
        """
        SELECT COALESCE(SUM(debe),0) debe,
               COALESCE(SUM(haber),0) haber,
               COUNT(*) movimientos
        FROM cuenta_corriente
        WHERE cliente_id=?
        """,
        (cliente_id,),
    )

    ventas_cliente = rows(
        """
        SELECT id,fecha,tipo,total,usuario
        FROM ventas
        WHERE cliente_id=?
        ORDER BY datetime(fecha) DESC, id DESC
        LIMIT 100
        """,
        (cliente_id,),
    )

    limite = money(cliente["limite_credito"])
    saldo = money(cliente["saldo"])
    disponible = max(limite - saldo, 0) if limite > 0 else 0

    return jsonify({
        "cliente": cliente,
        "movimientos": movimientos,
        "resumen": resumen_total,
        "ventas": ventas_cliente,
        "credito_disponible": disponible,
        "filtros": {"desde": desde, "hasta": hasta},
    })


@app.post("/api/clientes/<int:cliente_id>/pago")
def pago_cliente(cliente_id):
    if not can("Clientes", "agregar"):
        return forbidden()

    data = request.json or {}
    importe = money(data.get("importe"))

    if importe <= 0:
        return jsonify({"error": "El importe debe ser mayor a cero."}), 400

    cliente = one("SELECT * FROM clientes WHERE id=? AND activo=1", (cliente_id,))
    if not cliente:
        return jsonify({"error": "Cliente inexistente."}), 404

    saldo_actual = money(cliente["saldo"])
    saldo_nuevo = round(saldo_actual - importe, 2)

    with db() as conn:
        conn.execute("UPDATE clientes SET saldo=? WHERE id=?", (saldo_nuevo, cliente_id))
        conn.execute(
            """
            INSERT INTO cuenta_corriente
            (cliente_id,fecha,comprobante,concepto,debe,haber,saldo,observaciones)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                cliente_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                data.get("comprobante", "").strip(),
                "PAGO",
                0,
                importe,
                saldo_nuevo,
                data.get("observaciones", "").strip(),
            ),
        )
        conn.commit()

    audit("pago_cuenta_corriente", f"{cliente['nombre']} - {importe}")
    return jsonify({"ok": True, "saldo": saldo_nuevo})


@app.post("/api/clientes/<int:cliente_id>/ajuste")
def ajuste_cliente(cliente_id):
    if not can("Clientes", "agregar"):
        return forbidden()

    data = request.json or {}
    tipo = data.get("tipo", "DEBE").upper()
    importe = money(data.get("importe"))
    concepto = data.get("concepto", "").strip()

    if tipo not in {"DEBE", "HABER"}:
        return jsonify({"error": "Tipo de ajuste inválido."}), 400
    if importe <= 0:
        return jsonify({"error": "El importe debe ser mayor a cero."}), 400
    if not concepto:
        return jsonify({"error": "Ingrese un concepto."}), 400

    cliente = one("SELECT * FROM clientes WHERE id=? AND activo=1", (cliente_id,))
    if not cliente:
        return jsonify({"error": "Cliente inexistente."}), 404

    debe = importe if tipo == "DEBE" else 0
    haber = importe if tipo == "HABER" else 0
    saldo_nuevo = round(money(cliente["saldo"]) + debe - haber, 2)

    with db() as conn:
        conn.execute("UPDATE clientes SET saldo=? WHERE id=?", (saldo_nuevo, cliente_id))
        conn.execute(
            """
            INSERT INTO cuenta_corriente
            (cliente_id,fecha,comprobante,concepto,debe,haber,saldo,observaciones)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                cliente_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "",
                concepto,
                debe,
                haber,
                saldo_nuevo,
                data.get("observaciones", "").strip(),
            ),
        )
        conn.commit()

    audit("ajuste_cuenta_corriente", f"{cliente['nombre']} - {tipo} {importe}")
    return jsonify({"ok": True, "saldo": saldo_nuevo})


def caja_actual():
    return one("SELECT * FROM caja WHERE estado='ABIERTA' ORDER BY id DESC LIMIT 1")


def sistema_caja(caja):
    return {
        "efectivo": money(caja.get("apertura")) + money(caja.get("efectivo")) + money(caja.get("ingresos")) - money(caja.get("gastos")),
        "transferencia": money(caja.get("transferencia")),
        "debito": money(caja.get("debito")),
        "credito": money(caja.get("credito")),
        "posnet": money(caja.get("posnet")),
        "cuenta_corriente": money(caja.get("cuenta_corriente")),
    }


@app.get("/api/caja/actual")
def api_caja_actual():
    caja = caja_actual()
    if not caja:
        return jsonify({"caja": {}, "sistema": {}})
    return jsonify({"caja": caja, "sistema": sistema_caja(caja)})


@app.post("/api/caja/abrir")
def abrir_caja():
    if caja_actual():
        return jsonify({"error": "Ya hay una caja abierta."}), 400

    data = request.json or {}
    apertura = money(data.get("apertura"))
    if apertura < 0:
        return jsonify({"error": "La apertura no puede ser negativa."}), 400

    ahora = datetime.now()
    caja_id = execute(
        """
        INSERT INTO caja
        (fecha,estado,apertura,usuario_apertura,hora_apertura,observaciones_apertura)
        VALUES(?,?,?,?,?,?)
        """,
        (
            ahora.strftime("%Y-%m-%d"),
            "ABIERTA",
            apertura,
            session["user"]["usuario"],
            ahora.strftime("%Y-%m-%d %H:%M:%S"),
            data.get("observaciones", "").strip(),
        ),
    )
    audit("caja_abierta", f"Caja {caja_id} - apertura {apertura}")
    return jsonify({"ok": True, "caja_id": caja_id})


@app.post("/api/caja/movimiento")
def caja_movimiento():
    caja = caja_actual()
    if not caja:
        return jsonify({"error": "No hay caja abierta."}), 400

    data = request.json or {}
    importe = money(data.get("importe"))
    tipo = data.get("tipo", "ingreso").lower()
    descripcion = data.get("descripcion", "").strip()

    if tipo not in {"ingreso", "aporte", "gasto", "retiro"}:
        return jsonify({"error": "Tipo de movimiento inválido."}), 400
    if importe <= 0:
        return jsonify({"error": "El importe debe ser mayor a cero."}), 400
    if not descripcion:
        return jsonify({"error": "Ingrese una descripción."}), 400

    campo = "ingresos" if tipo in {"ingreso", "aporte"} else "gastos"

    with db() as conn:
        conn.execute(
            f"UPDATE caja SET {campo}=COALESCE({campo},0)+? WHERE id=?",
            (importe, caja["id"]),
        )
        conn.execute(
            """
            INSERT INTO caja_movimientos(caja_id,fecha,tipo,descripcion,importe)
            VALUES(?,?,?,?,?)
            """,
            (
                caja["id"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                tipo.upper(),
                descripcion,
                importe,
            ),
        )
        conn.commit()

    audit("movimiento_caja", f"Caja {caja['id']} - {tipo} {importe} - {descripcion}")
    return jsonify({"ok": True})


@app.post("/api/caja/forzar-cierre")
def forzar_cierre_caja():
    if session["user"]["rol"] != "ADMIN":
        return forbidden()

    caja = caja_actual()
    if not caja:
        return jsonify({"error": "No hay ninguna caja abierta para forzar el cierre."}), 400

    data = request.json or {}
    motivo = data.get("motivo", "").strip()

    if not motivo:
        return jsonify({"error": "Debe ingresar el motivo del cierre forzado."}), 400

    sistema = sistema_caja(caja)
    total_sistema = round(sum(sistema.values()), 2)
    ahora = datetime.now()

    with db() as conn:
        conn.execute(
            """
            UPDATE caja
            SET estado='CERRADA',
                cierre=?,
                diferencia=0,
                usuario_cierre=?,
                hora_cierre=?
            WHERE id=?
            """,
            (
                total_sistema,
                session["user"]["usuario"],
                ahora.strftime("%Y-%m-%d %H:%M:%S"),
                caja["id"],
            ),
        )

        conn.execute(
            """
            INSERT INTO caja_arqueos
            (
                caja_id,fecha,usuario,
                efectivo_sistema,efectivo_contado,
                transferencia_sistema,transferencia_contado,
                debito_sistema,debito_contado,
                credito_sistema,credito_contado,
                posnet_sistema,posnet_contado,
                cuenta_corriente_sistema,cuenta_corriente_contado,
                total_sistema,total_contado,diferencia,observaciones,
                corregido,usuario_correccion,motivo_correccion
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                caja["id"],
                ahora.strftime("%Y-%m-%d %H:%M:%S"),
                session["user"]["usuario"],
                sistema["efectivo"], sistema["efectivo"],
                sistema["transferencia"], sistema["transferencia"],
                sistema["debito"], sistema["debito"],
                sistema["credito"], sistema["credito"],
                sistema["posnet"], sistema["posnet"],
                sistema["cuenta_corriente"], sistema["cuenta_corriente"],
                total_sistema, total_sistema, 0,
                f"CIERRE FORZADO: {motivo}",
                1,
                session["user"]["usuario"],
                motivo,
            ),
        )
        conn.commit()

    audit(
        "caja_cierre_forzado",
        f"Caja {caja['id']} - usuario {session['user']['usuario']} - motivo: {motivo}",
    )

    return jsonify({
        "ok": True,
        "caja_id": caja["id"],
        "total": total_sistema,
    })


@app.post("/api/caja/cerrar")
def cerrar_caja():
    caja = caja_actual()
    if not caja:
        return jsonify({"error": "No hay caja abierta."}), 400

    data = request.json or {}
    sistema = sistema_caja(caja)
    medios = ["efectivo", "transferencia", "debito", "credito", "posnet", "cuenta_corriente"]

    faltantes = [medio for medio in medios if f"{medio}_contado" not in data]
    if faltantes:
        return jsonify({"error": "Complete todos los importes contados."}), 400

    contado = {medio: money(data.get(f"{medio}_contado")) for medio in medios}
    total_sistema = round(sum(sistema.values()), 2)
    total_contado = round(sum(contado.values()), 2)
    diferencia = round(total_contado - total_sistema, 2)
    ahora = datetime.now()

    billetes = data.get("billetes") or []

    with db() as conn:
        conn.execute(
            """
            UPDATE caja
            SET estado='CERRADA', cierre=?, diferencia=?,
                usuario_cierre=?, hora_cierre=?
            WHERE id=?
            """,
            (
                total_contado,
                diferencia,
                session["user"]["usuario"],
                ahora.strftime("%Y-%m-%d %H:%M:%S"),
                caja["id"],
            ),
        )

        conn.execute(
            """
            INSERT INTO caja_arqueos
            (
                caja_id,fecha,usuario,
                efectivo_sistema,efectivo_contado,
                transferencia_sistema,transferencia_contado,
                debito_sistema,debito_contado,
                credito_sistema,credito_contado,
                posnet_sistema,posnet_contado,
                cuenta_corriente_sistema,cuenta_corriente_contado,
                total_sistema,total_contado,diferencia,observaciones
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                caja["id"],
                ahora.strftime("%Y-%m-%d %H:%M:%S"),
                session["user"]["usuario"],
                sistema["efectivo"], contado["efectivo"],
                sistema["transferencia"], contado["transferencia"],
                sistema["debito"], contado["debito"],
                sistema["credito"], contado["credito"],
                sistema["posnet"], contado["posnet"],
                sistema["cuenta_corriente"], contado["cuenta_corriente"],
                total_sistema, total_contado, diferencia,
                data.get("observaciones", "").strip(),
            ),
        )

        conn.execute("DELETE FROM caja_billetes WHERE caja_id=?", (caja["id"],))
        for item in billetes:
            denominacion = money(item.get("denominacion"))
            cantidad = int(item.get("cantidad") or 0)
            if denominacion > 0 and cantidad > 0:
                conn.execute(
                    """
                    INSERT INTO caja_billetes(caja_id,denominacion,cantidad,subtotal)
                    VALUES(?,?,?,?)
                    """,
                    (caja["id"], denominacion, cantidad, denominacion * cantidad),
                )

        conn.commit()

    audit("caja_cerrada", f"Caja {caja['id']} - diferencia {diferencia}")
    return jsonify({"ok": True, "diferencia": diferencia, "caja_id": caja["id"]})


@app.get("/api/caja")
def listar_caja():
    return jsonify(rows(
        """
        SELECT c.*,
               COALESCE(a.total_sistema,0) total_sistema,
               COALESCE(a.total_contado,c.cierre,0) total_contado,
               COALESCE(a.corregido,0) corregido,
               a.usuario_correccion,
               a.motivo_correccion
        FROM caja c
        LEFT JOIN caja_arqueos a ON a.id=(
            SELECT id FROM caja_arqueos
            WHERE caja_id=c.id
            ORDER BY id DESC LIMIT 1
        )
        ORDER BY c.id DESC
        LIMIT 100
        """
    ))


@app.get("/api/caja/<int:caja_id>")
def detalle_caja(caja_id):
    caja = one("SELECT * FROM caja WHERE id=?", (caja_id,))
    if not caja:
        return jsonify({"error": "Caja inexistente."}), 404

    arqueo = one(
        "SELECT * FROM caja_arqueos WHERE caja_id=? ORDER BY id DESC LIMIT 1",
        (caja_id,),
    ) or {}
    movimientos = rows(
        "SELECT * FROM caja_movimientos WHERE caja_id=? ORDER BY id DESC",
        (caja_id,),
    )
    billetes = rows(
        "SELECT * FROM caja_billetes WHERE caja_id=? ORDER BY denominacion DESC",
        (caja_id,),
    )

    return jsonify({
        "caja": caja,
        "arqueo": arqueo,
        "movimientos": movimientos,
        "billetes": billetes,
        "sistema": sistema_caja(caja),
    })


@app.patch("/api/caja/<int:caja_id>/corregir")
def corregir_caja(caja_id):
    if session["user"]["rol"] != "ADMIN":
        return forbidden()

    data = request.json or {}
    motivo = data.get("motivo", "").strip()
    if not motivo:
        return jsonify({"error": "Ingrese el motivo de la corrección."}), 400

    arqueo = one(
        "SELECT * FROM caja_arqueos WHERE caja_id=? ORDER BY id DESC LIMIT 1",
        (caja_id,),
    )
    if not arqueo:
        return jsonify({"error": "La caja no tiene un arqueo para corregir."}), 404

    medios = ["efectivo", "transferencia", "debito", "credito", "posnet", "cuenta_corriente"]
    contado = {
        medio: money(data.get(f"{medio}_contado", arqueo.get(f"{medio}_contado", 0)))
        for medio in medios
    }
    total_contado = round(sum(contado.values()), 2)
    total_sistema = money(arqueo["total_sistema"])
    diferencia = round(total_contado - total_sistema, 2)

    with db() as conn:
        conn.execute(
            """
            UPDATE caja_arqueos
            SET efectivo_contado=?,
                transferencia_contado=?,
                debito_contado=?,
                credito_contado=?,
                posnet_contado=?,
                cuenta_corriente_contado=?,
                total_contado=?,
                diferencia=?,
                corregido=1,
                usuario_correccion=?,
                motivo_correccion=?
            WHERE id=?
            """,
            (
                contado["efectivo"],
                contado["transferencia"],
                contado["debito"],
                contado["credito"],
                contado["posnet"],
                contado["cuenta_corriente"],
                total_contado,
                diferencia,
                session["user"]["usuario"],
                motivo,
                arqueo["id"],
            ),
        )
        conn.execute(
            "UPDATE caja SET cierre=?, diferencia=? WHERE id=?",
            (total_contado, diferencia, caja_id),
        )
        conn.commit()

    audit(
        "caja_corregida",
        f"Caja {caja_id} - diferencia {diferencia} - motivo: {motivo}",
    )
    return jsonify({"ok": True, "diferencia": diferencia})


@app.get("/api/reportes")
def reportes():
    desde = request.args.get("desde") or datetime.now().strftime("%Y-%m-%d")
    hasta = request.args.get("hasta") or desde
    params = (desde, hasta)
    resumen = one("SELECT COUNT(*) ventas, COALESCE(SUM(total),0) total FROM ventas WHERE date(fecha) BETWEEN date(?) AND date(?)", params)
    medios = rows("SELECT tipo, COUNT(*) cantidad, COALESCE(SUM(total),0) total FROM ventas WHERE date(fecha) BETWEEN date(?) AND date(?) GROUP BY tipo ORDER BY total DESC", params)
    top = rows(
        """
        SELECT p.codigo,p.nombre,SUM(i.cantidad) cantidad,SUM(i.subtotal) total
        FROM venta_items i
        JOIN ventas v ON v.id=i.venta_id
        LEFT JOIN productos p ON p.id=i.producto_id
        WHERE date(v.fecha) BETWEEN date(?) AND date(?)
        GROUP BY p.id
        ORDER BY cantidad DESC
        LIMIT 10
        """,
        params,
    )
    bajos = rows("SELECT codigo,nombre,stock,stock_minimo FROM productos WHERE activo=1 AND stock<=stock_minimo ORDER BY stock")
    return jsonify({"periodo": {"desde": desde, "hasta": hasta}, "resumen": resumen, "medios": medios, "top": top, "bajos": bajos})


@app.post("/api/backup")
def crear_backup():
    backup_dir = os.path.join(BASE_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    filename = f"bebidas_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    target = os.path.join(backup_dir, filename)
    shutil.copy2(DB_PATH, target)
    audit("backup_creado", filename)
    return jsonify({"ok": True, "archivo": filename})


@app.get("/api/backups")
def backups():
    backup_dir = os.path.join(BASE_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    data = []
    for name in os.listdir(backup_dir):
        if name.endswith(".db"):
            path = os.path.join(backup_dir, name)
            data.append({"archivo": name, "fecha": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"), "tamano": os.path.getsize(path)})
    return jsonify(sorted(data, key=lambda x: x["fecha"], reverse=True))


@app.get("/api/backups/<path:name>")
def download_backup(name):
    safe = os.path.basename(name)
    path = os.path.join(BASE_DIR, "backups", safe)
    if not os.path.exists(path):
        return jsonify({"error": "No existe."}), 404
    return send_file(path, as_attachment=True, download_name=safe)


@app.get("/api/auditoria")
def auditoria():
    if session["user"]["rol"] != "ADMIN":
        return forbidden()
    return jsonify(rows("SELECT * FROM auditoria ORDER BY id DESC LIMIT 100"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
