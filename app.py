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
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


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
        conn.commit()


ensure_schema()


def can(module, action="ver"):
    user = session.get("user")
    if not user:
        return False
    if user["rol"] == "ADMIN":
        return True
    if action in {"ver", "agregar"} and module in {"Dashboard", "Ventas", "Productos", "Clientes", "Caja", "Reportes"}:
        return True
    return False


def forbidden():
    return jsonify({"error": "No tenes permiso para esta accion."}), 403


@app.before_request
def guard():
    if request.endpoint in {"login", "static"}:
        return None
    if "user" not in session:
        return redirect(url_for("login"))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        user = one("SELECT * FROM usuarios WHERE usuario=? AND activo=1", (usuario,))
        if user and verify_password(password, user["password"]):
            session["user"] = {"id": user["id"], "nombre": user["nombre"], "usuario": user["usuario"], "rol": user["rol"]}
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
    return render_template("index.html", user=session["user"])


@app.get("/api/me")
def me():
    return jsonify({"user": session["user"]})


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
        }
    )


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
