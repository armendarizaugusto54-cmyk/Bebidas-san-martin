from datetime import datetime
import os
import shutil
import sqlite3

from flask import Flask, jsonify, redirect, render_template, request, session, url_for


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bebidas.db")

app = Flask(__name__)
app.secret_key = os.environ.get("BEBIDAS_SECRET", "cambiar-esta-clave")

TABLE_MODULES = {
    "productos": "Productos",
    "clientes": "Clientes",
    "categorias": "Categorias",
    "marcas": "Marcas",
    "proveedores": "Proveedores",
    "compras": "Compras",
    "ventas": "Ventas",
    "caja": "Caja",
    "reportes": "Reportes",
    "configuracion": "Configuracion",
    "usuarios": "Usuarios",
}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rows(sql, params=()):
    with db() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def one(sql, params=()):
    with db() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def execute(sql, params=()):
    with db() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def ensure_schema():
    with db() as conn:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(clientes)")}
        if "whatsapp" not in cols:
            conn.execute("ALTER TABLE clientes ADD COLUMN whatsapp TEXT")
        conn.commit()


def money(value):
    try:
        return float(str(value or 0).replace(",", "."))
    except ValueError:
        return 0.0


def require_login():
    return "user" in session


def permissions_for(user):
    modules = [
        "Dashboard",
        "Ventas",
        "Productos",
        "Clientes",
        "Caja",
        "Categorias",
        "Marcas",
        "Proveedores",
        "Compras",
        "Reportes",
        "Usuarios",
        "Configuracion",
    ]
    if user["rol"] == "ADMIN":
        return {
            module: {"ver": 1, "agregar": 1, "modificar": 1, "eliminar": 1}
            for module in modules
        }
    perms = {
        module: {"ver": 0, "agregar": 0, "modificar": 0, "eliminar": 0}
        for module in modules
    }
    for row in rows(
        """
        SELECT modulo,ver,agregar,modificar,eliminar
        FROM permisos
        WHERE usuario_id=?
        """,
        (user["id"],),
    ):
        perms[row["modulo"]] = {
            "ver": int(row["ver"] or 0),
            "agregar": int(row["agregar"] or 0),
            "modificar": int(row["modificar"] or 0),
            "eliminar": int(row["eliminar"] or 0),
        }
    return perms


def can(module, action="ver"):
    user = session.get("user")
    if not user:
        return False
    if user["rol"] == "ADMIN":
        return True
    return permissions_for(user).get(module, {}).get(action, 0) == 1


def forbidden():
    return jsonify({"error": "No tenes permiso para esta accion."}), 403


@app.before_request
def guard():
    public = {"login", "static"}
    if request.endpoint not in public and not require_login():
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        user = one(
            "SELECT * FROM usuarios WHERE usuario=? AND password=? AND activo=1",
            (usuario, password),
        )
        if user:
            session["user"] = {
                "id": user["id"],
                "nombre": user["nombre"],
                "usuario": user["usuario"],
                "rol": user["rol"],
            }
            return redirect(url_for("index"))
        error = "Usuario o contrasena incorrectos."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    return render_template("index.html", user=session["user"])


@app.get("/api/me")
def me():
    return jsonify({"user": session["user"], "permisos": permissions_for(session["user"])})


@app.get("/api/dashboard")
def dashboard():
    if not can("Dashboard"):
        return forbidden()
    ventas_hoy = one(
        "SELECT COALESCE(SUM(total),0) total FROM ventas WHERE date(fecha)=date('now')"
    )["total"]
    return jsonify(
        {
            "productos": one("SELECT COUNT(*) cantidad FROM productos")["cantidad"],
            "clientes": one("SELECT COUNT(*) cantidad FROM clientes WHERE activo=1")[
                "cantidad"
            ],
            "ventasHoy": ventas_hoy,
            "stockBajo": one(
                "SELECT COUNT(*) cantidad FROM productos WHERE stock <= stock_minimo"
            )["cantidad"],
            "inventario": one(
                "SELECT COALESCE(SUM(stock * precio_compra),0) total FROM productos"
            )["total"],
            "bajos": rows(
                """
                SELECT codigo,nombre,marca,stock,stock_minimo
                FROM productos
                WHERE stock <= stock_minimo
                ORDER BY stock ASC, nombre
                LIMIT 12
                """
            ),
        }
    )


@app.get("/api/options")
def options():
    allowed = {
        "categorias": can("Categorias") or can("Productos") or can("Ventas") or can("Compras"),
        "marcas": can("Marcas") or can("Productos") or can("Ventas") or can("Compras"),
        "clientes": can("Clientes") or can("Ventas"),
        "proveedores": can("Proveedores") or can("Productos") or can("Compras"),
        "productos": can("Productos") or can("Ventas") or can("Compras"),
    }
    result = {}
    if allowed["categorias"]:
        result["categorias"] = rows("SELECT id,nombre,ganancia FROM categorias ORDER BY nombre")
    if allowed["marcas"]:
        result["marcas"] = rows("SELECT id,nombre FROM marcas ORDER BY nombre")
    if allowed["clientes"]:
        result["clientes"] = rows(
            "SELECT id,nombre,saldo FROM clientes WHERE activo=1 ORDER BY nombre"
        )
    if allowed["proveedores"]:
        result["proveedores"] = rows("SELECT id,nombre FROM proveedores ORDER BY nombre")
    if allowed["productos"]:
        result["productos"] = rows(
            """
            SELECT p.*, c.nombre categoria_nombre
            FROM productos p
            LEFT JOIN categorias c ON c.id=p.categoria_id
            ORDER BY p.nombre
            """
        )
    return jsonify(result)


@app.get("/api/<table>")
def list_table(table):
    queries = {
        "productos": """
            SELECT p.*, c.nombre categoria_nombre
            FROM productos p
            LEFT JOIN categorias c ON c.id=p.categoria_id
            ORDER BY p.nombre
        """,
        "clientes": "SELECT * FROM clientes ORDER BY nombre",
        "categorias": "SELECT * FROM categorias ORDER BY nombre",
        "marcas": "SELECT * FROM marcas ORDER BY nombre",
        "proveedores": "SELECT * FROM proveedores ORDER BY nombre",
        "compras": """
            SELECT c.*, p.nombre proveedor
            FROM compras c
            LEFT JOIN proveedores p ON p.id=c.proveedor_id
            ORDER BY c.id DESC
            LIMIT 100
        """,
        "ventas": """
            SELECT v.*, c.nombre cliente
            FROM ventas v
            LEFT JOIN clientes c ON c.id=v.cliente_id
            ORDER BY v.id DESC
            LIMIT 100
        """,
        "caja": "SELECT * FROM caja ORDER BY id DESC LIMIT 100",
        "usuarios": "SELECT id,nombre,usuario,rol,activo FROM usuarios ORDER BY nombre",
    }
    if table not in queries:
        return jsonify({"error": "Tabla no disponible"}), 404
    module = TABLE_MODULES[table]
    if not can(module):
        return forbidden()
    return jsonify(rows(queries[table]))


@app.post("/api/productos")
def save_producto():
    data = request.json or {}
    producto_id = data.get("id")
    if not can("Productos", "modificar" if producto_id else "agregar"):
        return forbidden()
    categoria_id = data.get("categoria_id") or None
    categoria = one("SELECT nombre, ganancia FROM categorias WHERE id=?", (categoria_id,))
    ganancia = money(data.get("ganancia", categoria["ganancia"] if categoria else 30))
    compra = money(data.get("precio_compra"))
    venta = money(data.get("precio_venta")) or compra + (compra * ganancia / 100)
    params = (
        data.get("codigo", "").strip(),
        data.get("nombre", "").strip(),
        categoria["nombre"] if categoria else "",
        data.get("marca", "").strip(),
        data.get("proveedor_id") or None,
        compra,
        venta,
        money(data.get("stock")),
        money(data.get("stock_minimo")),
        data.get("ubicacion", "").strip(),
        ganancia,
        categoria_id,
    )
    if not params[0] or not params[1]:
        return jsonify({"error": "Codigo y nombre son obligatorios."}), 400
    if producto_id:
        execute(
            """
            UPDATE productos
            SET codigo=?, nombre=?, categoria=?, marca=?, proveedor_id=?,
                precio_compra=?, precio_venta=?, stock=?, stock_minimo=?,
                ubicacion=?, ganancia=?, categoria_id=?
            WHERE id=?
            """,
            params + (producto_id,),
        )
    else:
        execute(
            """
            INSERT INTO productos
            (codigo,nombre,categoria,marca,proveedor_id,precio_compra,precio_venta,
             stock,stock_minimo,ubicacion,ganancia,categoria_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            params,
        )
    return jsonify({"ok": True})


@app.post("/api/clientes")
def save_cliente():
    data = request.json or {}
    if not can("Clientes", "modificar" if data.get("id") else "agregar"):
        return forbidden()
    params = (
        data.get("nombre", "").strip(),
        data.get("telefono", "").strip(),
        data.get("whatsapp", "").strip(),
        data.get("direccion", "").strip(),
        data.get("localidad", "").strip(),
        data.get("cuit", "").strip(),
        data.get("email", "").strip(),
        money(data.get("limite_credito")),
    )
    if not params[0]:
        return jsonify({"error": "El nombre es obligatorio."}), 400
    if data.get("id"):
        execute(
            """
            UPDATE clientes
            SET nombre=?, telefono=?, whatsapp=?, direccion=?, localidad=?,
                cuit=?, email=?, limite_credito=?
            WHERE id=?
            """,
            params + (data["id"],),
        )
    else:
        execute(
            """
            INSERT INTO clientes
            (nombre,telefono,whatsapp,direccion,localidad,cuit,email,limite_credito,saldo,activo)
            VALUES(?,?,?,?,?,?,?,?,0,1)
            """,
            params,
        )
    return jsonify({"ok": True})


@app.post("/api/simple/<table>")
def save_simple(table):
    allowed = {"categorias", "marcas"}
    if table not in allowed:
        return jsonify({"error": "No disponible"}), 404
    data = request.json or {}
    module = TABLE_MODULES[table]
    if not can(module, "modificar" if data.get("id") else "agregar"):
        return forbidden()
    nombre = data.get("nombre", "").strip()
    if not nombre:
        return jsonify({"error": "El nombre es obligatorio."}), 400
    if table == "categorias":
        params = (nombre, money(data.get("ganancia", 30)))
        if data.get("id"):
            execute("UPDATE categorias SET nombre=?, ganancia=? WHERE id=?", params + (data["id"],))
        else:
            execute("INSERT INTO categorias(nombre,ganancia) VALUES(?,?)", params)
    else:
        if data.get("id"):
            execute("UPDATE marcas SET nombre=? WHERE id=?", (nombre, data["id"]))
        else:
            execute("INSERT INTO marcas(nombre) VALUES(?)", (nombre,))
    return jsonify({"ok": True})


@app.post("/api/compras")
def save_compra():
    if not can("Compras", "agregar"):
        return forbidden()
    data = request.json or {}
    proveedor_id = data.get("proveedor_id") or None
    producto_id = data.get("producto_id")
    cantidad = money(data.get("cantidad"))
    precio = money(data.get("precio"))
    factura = data.get("factura", "").strip()
    observaciones = data.get("observaciones", "").strip()
    if not producto_id or cantidad <= 0:
        return jsonify({"error": "Seleccione producto y cantidad."}), 400
    total = cantidad * precio
    with db() as conn:
        try:
            conn.execute("BEGIN")
            compra_id = conn.execute(
                """
                INSERT INTO compras(fecha,proveedor_id,factura,total,observaciones)
                VALUES(?,?,?,?,?)
                """,
                (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    proveedor_id,
                    factura,
                    total,
                    observaciones,
                ),
            ).lastrowid
            stock = conn.execute(
                "SELECT stock FROM productos WHERE id=?", (producto_id,)
            ).fetchone()
            if not stock:
                raise ValueError("Producto inexistente.")
            stock_anterior = float(stock["stock"] or 0)
            stock_nuevo = stock_anterior + cantidad
            conn.execute(
                """
                INSERT INTO detalle_compras(compra_id,producto_id,cantidad,precio,subtotal)
                VALUES(?,?,?,?,?)
                """,
                (compra_id, producto_id, cantidad, precio, total),
            )
            conn.execute(
                """
                UPDATE productos
                SET stock=?, precio_compra=?
                WHERE id=?
                """,
                (stock_nuevo, precio, producto_id),
            )
            conn.execute(
                """
                INSERT INTO movimientos_stock
                (fecha,producto_id,tipo,cantidad,stock_anterior,stock_nuevo,observacion)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    producto_id,
                    "COMPRA",
                    cantidad,
                    stock_anterior,
                    stock_nuevo,
                    f"Compra {compra_id}",
                ),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "compra_id": compra_id})


@app.post("/api/proveedores")
def save_proveedor():
    data = request.json or {}
    if not can("Proveedores", "modificar" if data.get("id") else "agregar"):
        return forbidden()
    params = (
        data.get("nombre", "").strip(),
        data.get("contacto", "").strip(),
        data.get("telefono", "").strip(),
        data.get("email", "").strip(),
        data.get("direccion", "").strip(),
        data.get("localidad", "").strip(),
        data.get("cuit", "").strip(),
        data.get("observaciones", "").strip(),
    )
    if not params[0]:
        return jsonify({"error": "El nombre es obligatorio."}), 400
    if data.get("id"):
        execute(
            """
            UPDATE proveedores
            SET nombre=?, contacto=?, telefono=?, email=?, direccion=?,
                localidad=?, cuit=?, observaciones=?
            WHERE id=?
            """,
            params + (data["id"],),
        )
    else:
        execute(
            """
            INSERT INTO proveedores
            (nombre,contacto,telefono,email,direccion,localidad,cuit,observaciones)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            params,
        )
    return jsonify({"ok": True})


@app.delete("/api/<table>/<int:item_id>")
def delete_row(table, item_id):
    allowed = {"productos", "clientes", "categorias", "marcas", "proveedores", "usuarios"}
    if table not in allowed:
        return jsonify({"error": "No disponible"}), 404
    if not can(TABLE_MODULES[table], "eliminar"):
        return forbidden()
    if table == "clientes":
        execute("UPDATE clientes SET activo=0 WHERE id=?", (item_id,))
    elif table == "usuarios":
        execute("UPDATE usuarios SET activo=0 WHERE id=?", (item_id,))
    else:
        execute(f"DELETE FROM {table} WHERE id=?", (item_id,))
    return jsonify({"ok": True})


@app.post("/api/ventas")
def save_venta():
    if not can("Ventas", "agregar"):
        return forbidden()
    data = request.json or {}
    items = data.get("items") or []
    cliente_id = data.get("cliente_id")
    tipo = data.get("tipo", "EFECTIVO")
    if not cliente_id or not items:
        return jsonify({"error": "Seleccione cliente y productos."}), 400
    total = sum(money(i.get("subtotal")) for i in items)
    with db() as conn:
        try:
            conn.execute("BEGIN")
            venta_id = conn.execute(
                """
                INSERT INTO ventas(fecha,cliente_id,tipo,total,usuario)
                VALUES(?,?,?,?,?)
                """,
                (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    cliente_id,
                    tipo,
                    total,
                    session["user"]["usuario"],
                ),
            ).lastrowid
            for item in items:
                product = conn.execute(
                    "SELECT stock FROM productos WHERE id=?", (item["producto_id"],)
                ).fetchone()
                cantidad = money(item.get("cantidad"))
                if not product or float(product["stock"]) < cantidad:
                    raise ValueError("No hay stock suficiente.")
                precio = money(item.get("precio"))
                subtotal = cantidad * precio
                conn.execute(
                    """
                    INSERT INTO detalle_ventas
                    (venta_id,producto_id,cantidad,precio,subtotal)
                    VALUES(?,?,?,?,?)
                    """,
                    (venta_id, item["producto_id"], cantidad, precio, subtotal),
                )
                conn.execute(
                    "UPDATE productos SET stock=stock-? WHERE id=?",
                    (cantidad, item["producto_id"]),
                )
                conn.execute(
                    """
                    INSERT INTO movimientos_stock
                    (fecha,producto_id,tipo,cantidad,stock_anterior,stock_nuevo,observacion)
                    VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        item["producto_id"],
                        "VENTA",
                        cantidad,
                        float(product["stock"] or 0),
                        float(product["stock"] or 0) - cantidad,
                        f"Venta {venta_id}",
                    ),
                )
            if tipo == "CUENTA CORRIENTE":
                saldo = conn.execute(
                    "SELECT saldo FROM clientes WHERE id=?", (cliente_id,)
                ).fetchone()["saldo"]
                nuevo = float(saldo or 0) + total
                conn.execute("UPDATE clientes SET saldo=? WHERE id=?", (nuevo, cliente_id))
                conn.execute(
                    """
                    INSERT INTO cuenta_corriente
                    (cliente_id,fecha,comprobante,concepto,debe,haber,saldo,observaciones)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        cliente_id,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        str(venta_id),
                        "VENTA",
                        total,
                        0,
                        nuevo,
                        "",
                    ),
                )
            else:
                abierta = conn.execute(
                    "SELECT * FROM caja WHERE estado='ABIERTA' ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if abierta:
                    campo = {
                        "EFECTIVO": "efectivo",
                        "TRANSFERENCIA": "transferencia",
                        "DEBITO": "debito",
                        "CREDITO": "credito",
                        "POSNET": "posnet",
                    }.get(tipo, "efectivo")
                    conn.execute(
                        f"UPDATE caja SET {campo}=COALESCE({campo},0)+? WHERE id=?",
                        (total, abierta["id"]),
                    )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "venta_id": venta_id, "total": total})


@app.get("/api/ventas/<int:venta_id>/detalle")
def venta_detalle(venta_id):
    if not can("Ventas"):
        return forbidden()
    venta = one(
        """
        SELECT v.*, c.nombre cliente
        FROM ventas v
        LEFT JOIN clientes c ON c.id=v.cliente_id
        WHERE v.id=?
        """,
        (venta_id,),
    )
    if not venta:
        return jsonify({"error": "Venta inexistente."}), 404
    detalle = rows(
        """
        SELECT d.*, p.codigo, p.nombre producto
        FROM detalle_ventas d
        LEFT JOIN productos p ON p.id=d.producto_id
        WHERE d.venta_id=?
        ORDER BY d.id
        """,
        (venta_id,),
    )
    return jsonify({"venta": venta, "detalle": detalle})


@app.get("/api/reportes")
def reportes():
    if not can("Reportes"):
        return forbidden()
    desde = request.args.get("desde") or datetime.now().strftime("%Y-%m-%d")
    hasta = request.args.get("hasta") or desde
    params = (desde, hasta)
    resumen = one(
        """
        SELECT COUNT(*) ventas, COALESCE(SUM(total),0) total
        FROM ventas
        WHERE date(fecha) BETWEEN date(?) AND date(?)
        """,
        params,
    )
    medios = rows(
        """
        SELECT tipo, COUNT(*) cantidad, COALESCE(SUM(total),0) total
        FROM ventas
        WHERE date(fecha) BETWEEN date(?) AND date(?)
        GROUP BY tipo
        ORDER BY total DESC
        """,
        params,
    )
    top = rows(
        """
        SELECT p.codigo, p.nombre, SUM(d.cantidad) cantidad, SUM(d.subtotal) total
        FROM detalle_ventas d
        JOIN ventas v ON v.id=d.venta_id
        LEFT JOIN productos p ON p.id=d.producto_id
        WHERE date(v.fecha) BETWEEN date(?) AND date(?)
        GROUP BY d.producto_id
        ORDER BY cantidad DESC
        LIMIT 10
        """,
        params,
    )
    bajos = rows(
        """
        SELECT codigo,nombre,marca,stock,stock_minimo
        FROM productos
        WHERE stock <= stock_minimo
        ORDER BY stock ASC,nombre
        """
    )
    movimientos = rows(
        """
        SELECT m.fecha,m.tipo,m.cantidad,m.stock_anterior,m.stock_nuevo,
               m.observacion,p.codigo,p.nombre producto
        FROM movimientos_stock m
        LEFT JOIN productos p ON p.id=m.producto_id
        ORDER BY m.id DESC
        LIMIT 30
        """
    )
    return jsonify(
        {
            "resumen": resumen,
            "medios": medios,
            "top": top,
            "bajos": bajos,
            "movimientos": movimientos,
        }
    )


@app.get("/api/usuarios/<int:user_id>/permisos")
def usuario_permisos(user_id):
    if not can("Usuarios"):
        return forbidden()
    return jsonify(
        rows(
            """
            SELECT modulo,ver,agregar,modificar,eliminar
            FROM permisos
            WHERE usuario_id=?
            ORDER BY modulo
            """,
            (user_id,),
        )
    )


@app.post("/api/usuarios")
def save_usuario():
    data = request.json or {}
    usuario_id = data.get("id")
    if not can("Usuarios", "modificar" if usuario_id else "agregar"):
        return forbidden()
    params = (
        data.get("nombre", "").strip(),
        data.get("usuario", "").strip(),
        data.get("password", "").strip(),
        data.get("rol", "CAJERO").strip() or "CAJERO",
        int(data.get("activo", 1) or 0),
    )
    if not params[0] or not params[1] or (not usuario_id and not params[2]):
        return jsonify({"error": "Nombre, usuario y contrasena son obligatorios."}), 400
    if usuario_id:
        if params[2]:
            execute(
                """
                UPDATE usuarios
                SET nombre=?, usuario=?, password=?, rol=?, activo=?
                WHERE id=?
                """,
                params + (usuario_id,),
            )
        else:
            execute(
                """
                UPDATE usuarios
                SET nombre=?, usuario=?, rol=?, activo=?
                WHERE id=?
                """,
                (params[0], params[1], params[3], params[4], usuario_id),
            )
    else:
        execute(
            """
            INSERT INTO usuarios(nombre,usuario,password,rol,activo)
            VALUES(?,?,?,?,?)
            """,
            params,
        )
    return jsonify({"ok": True})


@app.post("/api/usuarios/<int:user_id>/permisos")
def save_usuario_permisos(user_id):
    if not can("Usuarios", "modificar"):
        return forbidden()
    data = request.json or {}
    permisos = data.get("permisos") or []
    with db() as conn:
        conn.execute("DELETE FROM permisos WHERE usuario_id=?", (user_id,))
        for permiso in permisos:
            conn.execute(
                """
                INSERT INTO permisos(usuario_id,modulo,ver,agregar,modificar,eliminar)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    user_id,
                    permiso.get("modulo"),
                    int(permiso.get("ver") or 0),
                    int(permiso.get("agregar") or 0),
                    int(permiso.get("modificar") or 0),
                    int(permiso.get("eliminar") or 0),
                ),
            )
        conn.commit()
    return jsonify({"ok": True})


@app.get("/api/caja/actual")
def caja_actual():
    if not can("Caja"):
        return forbidden()
    caja = one("SELECT * FROM caja WHERE estado='ABIERTA' ORDER BY id DESC LIMIT 1")
    return jsonify(caja or {})


@app.post("/api/caja/abrir")
def abrir_caja():
    if not can("Caja", "agregar"):
        return forbidden()
    data = request.json or {}
    existe = one("SELECT id FROM caja WHERE estado='ABIERTA' LIMIT 1")
    if existe:
        return jsonify({"error": "Ya existe una caja abierta."}), 400
    execute(
        "INSERT INTO caja(fecha,apertura,estado) VALUES(?,?,?)",
        (datetime.now().strftime("%Y-%m-%d"), money(data.get("apertura")), "ABIERTA"),
    )
    return jsonify({"ok": True})


@app.post("/api/caja/movimiento")
def caja_movimiento():
    if not can("Caja", "agregar"):
        return forbidden()
    data = request.json or {}
    caja = one("SELECT id FROM caja WHERE estado='ABIERTA' ORDER BY id DESC LIMIT 1")
    if not caja:
        return jsonify({"error": "No hay caja abierta."}), 400
    importe = money(data.get("importe"))
    tipo = data.get("tipo")
    if tipo == "gasto":
        execute(
            "INSERT INTO gastos(fecha,descripcion,importe,caja_id) VALUES(date('now'),?,?,?)",
            (data.get("descripcion", "Gasto"), importe, caja["id"]),
        )
        execute("UPDATE caja SET gastos=COALESCE(gastos,0)+? WHERE id=?", (importe, caja["id"]))
    else:
        execute(
            "UPDATE caja SET ingresos=COALESCE(ingresos,0)+? WHERE id=?",
            (importe, caja["id"]),
        )
    return jsonify({"ok": True})


@app.post("/api/caja/cerrar")
def cerrar_caja():
    if not can("Caja", "modificar"):
        return forbidden()
    data = request.json or {}
    caja = one("SELECT * FROM caja WHERE estado='ABIERTA' ORDER BY id DESC LIMIT 1")
    if not caja:
        return jsonify({"error": "No hay caja abierta."}), 400
    sistema = {
        "efectivo": money(caja.get("apertura"))
        + money(caja.get("efectivo"))
        + money(caja.get("ingresos"))
        - money(caja.get("gastos")),
        "transferencia": money(caja.get("transferencia")),
        "debito": money(caja.get("debito")),
        "credito": money(caja.get("credito")),
        "posnet": money(caja.get("posnet")),
    }
    contado = {
        "efectivo": money(data.get("efectivo_contado", data.get("cierre"))),
        "transferencia": money(data.get("transferencia_contado")),
        "debito": money(data.get("debito_contado")),
        "credito": money(data.get("credito_contado")),
        "posnet": money(data.get("posnet_contado")),
    }
    teorico = sum(sistema.values())
    cierre = sum(contado.values())
    diferencia = cierre - teorico
    observaciones = data.get("observaciones", "").strip()
    execute(
        "UPDATE caja SET cierre=?, diferencia=?, estado='CERRADA' WHERE id=?",
        (cierre, diferencia, caja["id"]),
    )
    execute(
        """
        INSERT INTO arqueo_caja
        (fecha,usuario,apertura,efectivo_sistema,efectivo_contado,
         diferencia_efectivo,posnet_sistema,posnet_contado,diferencia_posnet,
         observaciones,estado,caja_id)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            session["user"]["usuario"],
            money(caja.get("apertura")),
            sistema["efectivo"],
            contado["efectivo"],
            contado["efectivo"] - sistema["efectivo"],
            sistema["posnet"],
            contado["posnet"],
            contado["posnet"] - sistema["posnet"],
            (
                f"{observaciones} | "
                f"Transferencia sis/cont/dif: {sistema['transferencia']}/{contado['transferencia']}/{contado['transferencia'] - sistema['transferencia']}; "
                f"Debito sis/cont/dif: {sistema['debito']}/{contado['debito']}/{contado['debito'] - sistema['debito']}; "
                f"Credito sis/cont/dif: {sistema['credito']}/{contado['credito']}/{contado['credito'] - sistema['credito']}; "
                f"Total sis/cont/dif: {teorico}/{cierre}/{diferencia}"
            ).strip(),
            "CERRADA",
            caja["id"],
        ),
    )
    return jsonify({"ok": True, "sistema": teorico, "contado": cierre, "diferencia": diferencia})


def caja_sistema_por_medio(caja):
    return {
        "efectivo": money(caja.get("apertura"))
        + money(caja.get("efectivo"))
        + money(caja.get("ingresos"))
        - money(caja.get("gastos")),
        "transferencia": money(caja.get("transferencia")),
        "debito": money(caja.get("debito")),
        "credito": money(caja.get("credito")),
        "posnet": money(caja.get("posnet")),
    }


@app.get("/api/caja/ultimo-arqueo")
def ultimo_arqueo():
    if session["user"]["rol"] != "ADMIN":
        return forbidden()
    caja = one("SELECT * FROM caja WHERE estado='CERRADA' ORDER BY id DESC LIMIT 1")
    if not caja:
        return jsonify({})
    arqueo = one(
        "SELECT * FROM arqueo_caja WHERE caja_id=? ORDER BY id DESC LIMIT 1",
        (caja["id"],),
    )
    sistema = caja_sistema_por_medio(caja)
    contado = {
        "efectivo": money(arqueo.get("efectivo_contado")) if arqueo else money(caja.get("cierre")),
        "transferencia": 0,
        "debito": 0,
        "credito": 0,
        "posnet": money(arqueo.get("posnet_contado")) if arqueo else 0,
    }
    if arqueo and arqueo.get("observaciones"):
        # Los medios no contemplados por columnas propias se guardan en observaciones;
        # para corregir se cargan de nuevo desde cero.
        contado["transferencia"] = sistema["transferencia"]
        contado["debito"] = sistema["debito"]
        contado["credito"] = sistema["credito"]
    return jsonify({"caja": caja, "arqueo": arqueo or {}, "sistema": sistema, "contado": contado})


@app.post("/api/caja/corregir-arqueo")
def corregir_arqueo():
    if session["user"]["rol"] != "ADMIN":
        return forbidden()
    data = request.json or {}
    caja_id = data.get("caja_id")
    arqueo_id = data.get("arqueo_id")
    motivo = data.get("motivo", "").strip()
    if not caja_id or not motivo:
        return jsonify({"error": "Caja y motivo son obligatorios."}), 400
    caja = one("SELECT * FROM caja WHERE id=? AND estado='CERRADA'", (caja_id,))
    if not caja:
        return jsonify({"error": "Caja cerrada inexistente."}), 404
    sistema = caja_sistema_por_medio(caja)
    contado = {
        "efectivo": money(data.get("efectivo_contado")),
        "transferencia": money(data.get("transferencia_contado")),
        "debito": money(data.get("debito_contado")),
        "credito": money(data.get("credito_contado")),
        "posnet": money(data.get("posnet_contado")),
    }
    total_sistema = sum(sistema.values())
    total_contado = sum(contado.values())
    diferencia = total_contado - total_sistema
    execute(
        "UPDATE caja SET cierre=?, diferencia=? WHERE id=?",
        (total_contado, diferencia, caja_id),
    )
    obs = (
        f"CORRECCION: {motivo} | "
        f"Efectivo sis/cont/dif: {sistema['efectivo']}/{contado['efectivo']}/{contado['efectivo'] - sistema['efectivo']}; "
        f"Transferencia sis/cont/dif: {sistema['transferencia']}/{contado['transferencia']}/{contado['transferencia'] - sistema['transferencia']}; "
        f"Debito sis/cont/dif: {sistema['debito']}/{contado['debito']}/{contado['debito'] - sistema['debito']}; "
        f"Credito sis/cont/dif: {sistema['credito']}/{contado['credito']}/{contado['credito'] - sistema['credito']}; "
        f"Posnet sis/cont/dif: {sistema['posnet']}/{contado['posnet']}/{contado['posnet'] - sistema['posnet']}; "
        f"Total sis/cont/dif: {total_sistema}/{total_contado}/{diferencia}"
    )
    if arqueo_id:
        execute(
            """
            UPDATE arqueo_caja
            SET efectivo_sistema=?, efectivo_contado=?, diferencia_efectivo=?,
                posnet_sistema=?, posnet_contado=?, diferencia_posnet=?,
                observaciones=?, corregido=1, usuario_correccion=?,
                fecha_correccion=?, motivo_correccion=?, motivo=?
            WHERE id=?
            """,
            (
                sistema["efectivo"],
                contado["efectivo"],
                contado["efectivo"] - sistema["efectivo"],
                sistema["posnet"],
                contado["posnet"],
                contado["posnet"] - sistema["posnet"],
                obs,
                session["user"]["usuario"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                motivo,
                motivo,
                arqueo_id,
            ),
        )
    else:
        execute(
            """
            INSERT INTO arqueo_caja
            (fecha,usuario,apertura,efectivo_sistema,efectivo_contado,
             diferencia_efectivo,posnet_sistema,posnet_contado,diferencia_posnet,
             observaciones,estado,caja_id,corregido,usuario_correccion,
             fecha_correccion,motivo_correccion,motivo)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                session["user"]["usuario"],
                money(caja.get("apertura")),
                sistema["efectivo"],
                contado["efectivo"],
                contado["efectivo"] - sistema["efectivo"],
                sistema["posnet"],
                contado["posnet"],
                contado["posnet"] - sistema["posnet"],
                obs,
                "CERRADA",
                caja_id,
                1,
                session["user"]["usuario"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                motivo,
                motivo,
            ),
        )
    return jsonify({"ok": True, "sistema": total_sistema, "contado": total_contado, "diferencia": diferencia})


@app.post("/api/backup")
def backup():
    if not can("Configuracion", "agregar") and not can("Configuracion", "modificar"):
        return forbidden()
    backup_dir = os.path.join(BASE_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    filename = f"bebidas_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    target = os.path.join(backup_dir, filename)
    shutil.copy2(DB_PATH, target)
    return jsonify({"ok": True, "archivo": os.path.join("backups", filename)})


if __name__ == "__main__":
    ensure_schema()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
