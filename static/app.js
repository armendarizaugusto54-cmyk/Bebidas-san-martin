const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];
const money = (n) => `$${Number(n || 0).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
let state = { options: {}, productos: [], ticket: [], current: "inicio", permisos: {}, user: null };
const viewModules = {
  inicio: "Dashboard",
  ventas: "Ventas",
  productos: "Productos",
  clientes: "Clientes",
  caja: "Caja",
  categorias: "Categorias",
  marcas: "Marcas",
  proveedores: "Proveedores",
  usuarios: "Usuarios",
};
const permissionModules = ["Dashboard", "Ventas", "Productos", "Clientes", "Caja", "Categorias", "Marcas", "Proveedores", "Compras", "Reportes", "Usuarios", "Configuracion"];

async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "No se pudo completar la accion.");
  return data;
}

function can(module, action = "ver") {
  return state.user?.rol === "ADMIN" || Number(state.permisos[module]?.[action] || 0) === 1;
}

function canView(view) {
  return can(viewModules[view] || view);
}

function applyPermissions() {
  $$("aside button[data-view]").forEach((button) => {
    button.hidden = !canView(button.dataset.view);
  });
  const activeVisible = $(`aside button[data-view="${state.current}"]:not([hidden])`);
  const firstVisible = $("aside button[data-view]:not([hidden])");
  if (!activeVisible && firstVisible) {
    state.current = firstVisible.dataset.view;
  }
}

function table(el, columns, data, actions) {
  const q = $("#search").value.trim().toLowerCase();
  const filtered = q
    ? data.filter((row) => Object.values(row).join(" ").toLowerCase().includes(q))
    : data;
  el.innerHTML = `
    <thead><tr>${columns.map((c) => `<th>${c.label}</th>`).join("")}${actions ? "<th></th>" : ""}</tr></thead>
    <tbody>
      ${filtered.map((row) => `
        <tr>
          ${columns.map((c) => `<td>${c.format ? c.format(row[c.key], row) : row[c.key] ?? ""}</td>`).join("")}
          ${actions ? `<td class="actions">${actions(row)}</td>` : ""}
        </tr>`).join("") || `<tr><td colspan="${columns.length + (actions ? 1 : 0)}">Sin datos</td></tr>`}
    </tbody>`;
}

function form(el, fields, saveText = "Guardar") {
  el.innerHTML = fields.map((f) => {
    if (f.type === "select") {
      return `<label>${f.label}<select name="${f.name}">${f.options().map((o) => `<option value="${o.value}">${o.label}</option>`).join("")}</select></label>`;
    }
    return `<label>${f.label}<input name="${f.name}" type="${f.type || "text"}" step="${f.step || "any"}" value="${f.value ?? ""}"></label>`;
  }).join("") + `<input type="hidden" name="id"><div class="actions"><button>${saveText}</button><button type="button" class="secondary" data-clear>Nuevo</button></div>`;
  $("[data-clear]", el).onclick = () => el.reset();
}

function fillForm(id, row) {
  const el = $(id);
  Object.entries(row).forEach(([k, v]) => {
    const input = el.elements[k];
    if (input) input.value = v ?? "";
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadOptions() {
  state.options = await api("/api/options");
  state.productos = state.options.productos || [];
}

async function loadDashboard() {
  const d = await api("/api/dashboard");
  $("#card-productos").textContent = d.productos;
  $("#card-ventas").textContent = money(d.ventasHoy);
  $("#card-stock").textContent = d.stockBajo;
  $("#card-inventario").textContent = money(d.inventario);
  table($("#tabla-bajos"), [
    { key: "codigo", label: "Codigo" },
    { key: "nombre", label: "Producto" },
    { key: "marca", label: "Marca" },
    { key: "stock", label: "Stock" },
    { key: "stock_minimo", label: "Minimo" },
  ], d.bajos);
}

async function loadProductos() {
  await loadOptions();
  table($("#tabla-productos"), [
    { key: "codigo", label: "Codigo" },
    { key: "nombre", label: "Producto" },
    { key: "categoria_nombre", label: "Categoria" },
    { key: "marca", label: "Marca" },
    { key: "precio_compra", label: "Compra", format: money },
    { key: "precio_venta", label: "Venta", format: money },
    { key: "stock", label: "Stock" },
  ], state.productos, (r) => [
    can("Productos", "modificar") ? `<button data-edit-producto="${r.id}">Editar</button>` : "",
    can("Productos", "eliminar") ? `<button class="danger" data-del="productos:${r.id}">Borrar</button>` : "",
  ].join(""));
}

async function loadClientes() {
  const data = await api("/api/clientes");
  table($("#tabla-clientes"), [
    { key: "nombre", label: "Nombre" },
    { key: "telefono", label: "Telefono" },
    { key: "whatsapp", label: "WhatsApp" },
    { key: "localidad", label: "Localidad" },
    { key: "cuit", label: "CUIT/DNI" },
    { key: "saldo", label: "Saldo", format: money },
  ], data, (r) => [
    can("Clientes", "modificar") ? `<button data-edit-cliente="${r.id}">Editar</button>` : "",
    can("Clientes", "eliminar") ? `<button class="danger" data-del="clientes:${r.id}">Borrar</button>` : "",
  ].join(""));
}

async function loadProveedor() {
  const data = await api("/api/proveedores");
  table($("#tabla-proveedores"), [
    { key: "nombre", label: "Proveedor" },
    { key: "contacto", label: "Contacto" },
    { key: "telefono", label: "Telefono" },
    { key: "email", label: "Email" },
    { key: "localidad", label: "Localidad" },
  ], data, (r) => [
    can("Proveedores", "modificar") ? `<button data-edit-proveedor="${r.id}">Editar</button>` : "",
    can("Proveedores", "eliminar") ? `<button class="danger" data-del="proveedores:${r.id}">Borrar</button>` : "",
  ].join(""));
}

async function loadUsuarios() {
  const data = await api("/api/usuarios");
  table($("#tabla-usuarios"), [
    { key: "nombre", label: "Nombre" },
    { key: "usuario", label: "Usuario" },
    { key: "rol", label: "Rol" },
    { key: "activo", label: "Activo", format: (v) => Number(v) === 1 ? "Si" : "No" },
  ], data, (r) => [
    can("Usuarios", "modificar") ? `<button data-edit-usuario="${r.id}">Editar</button>` : "",
    can("Usuarios", "modificar") ? `<button data-permisos="${r.id}">Permisos</button>` : "",
    can("Usuarios", "eliminar") ? `<button class="danger" data-del="usuarios:${r.id}">Borrar</button>` : "",
  ].join(""));
}

async function loadPermisos(userId) {
  const permisos = await api(`/api/usuarios/${userId}/permisos`);
  const byModule = Object.fromEntries(permisos.map((p) => [p.modulo, p]));
  $("#permisos-form").elements.usuario_id.value = userId;
  $("#permisos-list").innerHTML = `
    <table>
      <thead><tr><th>Modulo</th><th>Ver</th><th>Agregar</th><th>Modificar</th><th>Eliminar</th></tr></thead>
      <tbody>
        ${permissionModules.map((module) => {
          const p = byModule[module] || {};
          return `<tr data-module="${module}">
            <td>${module}</td>
            ${["ver", "agregar", "modificar", "eliminar"].map((action) => `<td><input type="checkbox" data-action="${action}" ${Number(p[action] || 0) === 1 ? "checked" : ""}></td>`).join("")}
          </tr>`;
        }).join("")}
      </tbody>
    </table>`;
}

async function loadSimple(kind) {
  const section = $(`#${kind}`);
  section.innerHTML = `
    <form class="panel grid-form" id="${kind}-form">
      <label>Nombre<input name="nombre" required></label>
      ${kind === "categorias" ? `<label>Ganancia %<input name="ganancia" type="number" step="0.01" value="30"></label>` : ""}
      <input type="hidden" name="id">
      <div class="actions"><button>Guardar</button><button type="button" class="secondary" data-clear>Nuevo</button></div>
    </form>
    <div class="panel"><table id="tabla-${kind}"></table></div>`;
  const data = await api(`/api/${kind}`);
  table($(`#tabla-${kind}`), kind === "categorias"
    ? [{ key: "nombre", label: "Categoria" }, { key: "ganancia", label: "Ganancia %" }]
    : [{ key: "nombre", label: "Marca" }],
    data,
    (r) => {
      const module = viewModules[kind];
      return [
        can(module, "modificar") ? `<button data-edit-simple="${kind}:${r.id}">Editar</button>` : "",
        can(module, "eliminar") ? `<button class="danger" data-del="${kind}:${r.id}">Borrar</button>` : "",
      ].join("");
    }
  );
  $(`#${kind}-form`).onsubmit = async (ev) => {
    ev.preventDefault();
    await api(`/api/simple/${kind}`, { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
    await refresh();
  };
  if (!can(viewModules[kind], "agregar")) {
    $$("input,select,button", $(`#${kind}-form`)).forEach((el) => el.disabled = true);
  }
  $("[data-clear]", section).onclick = () => $(`#${kind}-form`).reset();
}

async function loadVentas() {
  await loadOptions();
  const clienteSelect = $("#venta-form").elements.cliente_id;
  clienteSelect.innerHTML = state.options.clientes.map((c) => `<option value="${c.id}">${c.nombre}</option>`).join("");
  $("#venta-producto").innerHTML = state.productos.map((p) => `<option value="${p.id}">${p.codigo} - ${p.nombre} (${money(p.precio_venta)})</option>`).join("");
  const ventas = await api("/api/ventas");
  table($("#tabla-ventas"), [
    { key: "id", label: "Nro" },
    { key: "fecha", label: "Fecha" },
    { key: "cliente", label: "Cliente" },
    { key: "tipo", label: "Tipo" },
    { key: "total", label: "Total", format: money },
  ], ventas);
  renderTicket();
}

function renderTicket() {
  table($("#ticket"), [
    { key: "nombre", label: "Producto" },
    { key: "cantidad", label: "Cant." },
    { key: "precio", label: "Precio", format: money },
    { key: "subtotal", label: "Subtotal", format: money },
  ], state.ticket, (r) => `<button class="danger" data-remove-item="${r.producto_id}">Quitar</button>`);
  $("#ticket-total").textContent = `TOTAL: ${money(state.ticket.reduce((a, i) => a + Number(i.subtotal), 0))}`;
}

async function loadCaja() {
  const actual = await api("/api/caja/actual");
  const entradas = Number(actual.efectivo || 0) + Number(actual.transferencia || 0) + Number(actual.debito || 0) + Number(actual.credito || 0) + Number(actual.posnet || 0) + Number(actual.ingresos || 0);
  const total = Number(actual.apertura || 0) + entradas - Number(actual.gastos || 0);
  $("#caja-estado").textContent = actual.id ? "Abierta" : "Cerrada";
  $("#caja-apertura").textContent = money(actual.apertura);
  $("#caja-entradas").textContent = money(entradas);
  $("#caja-total").textContent = money(total);
  table($("#tabla-caja"), [
    { key: "fecha", label: "Fecha" },
    { key: "estado", label: "Estado" },
    { key: "apertura", label: "Apertura", format: money },
    { key: "efectivo", label: "Efectivo", format: money },
    { key: "transferencia", label: "Transferencia", format: money },
    { key: "gastos", label: "Gastos", format: money },
    { key: "cierre", label: "Cierre", format: money },
    { key: "diferencia", label: "Diferencia", format: money },
  ], await api("/api/caja"));
}

async function refresh() {
  const current = state.current;
  if (!canView(current)) return;
  if (current === "inicio") return loadDashboard();
  if (current === "productos") return loadProductos();
  if (current === "clientes") return loadClientes();
  if (current === "ventas") return loadVentas();
  if (current === "caja") return loadCaja();
  if (current === "proveedores") return loadProveedor();
  if (current === "usuarios") return loadUsuarios();
  if (current === "categorias" || current === "marcas") return loadSimple(current);
}

function setupForms() {
  form($("#producto-form"), [
    { name: "codigo", label: "Codigo" },
    { name: "nombre", label: "Nombre" },
    { name: "categoria_id", label: "Categoria", type: "select", options: () => (state.options.categorias || []).map((c) => ({ value: c.id, label: c.nombre })) },
    { name: "marca", label: "Marca", type: "select", options: () => (state.options.marcas || []).map((m) => ({ value: m.nombre, label: m.nombre })) },
    { name: "precio_compra", label: "Compra", type: "number" },
    { name: "ganancia", label: "Ganancia %", type: "number" },
    { name: "precio_venta", label: "Venta", type: "number" },
    { name: "stock", label: "Stock", type: "number" },
    { name: "stock_minimo", label: "Stock minimo", type: "number" },
    { name: "ubicacion", label: "Ubicacion" },
  ]);
  $("#producto-form").onsubmit = async (ev) => {
    ev.preventDefault();
    await api("/api/productos", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
    ev.target.reset();
    await loadProductos();
    await loadDashboard();
  };
  if (!can("Productos", "agregar") && !can("Productos", "modificar")) {
    $$("input,select,button", $("#producto-form")).forEach((el) => el.disabled = true);
  }

  form($("#cliente-form"), [
    { name: "nombre", label: "Nombre" },
    { name: "telefono", label: "Telefono" },
    { name: "whatsapp", label: "WhatsApp" },
    { name: "direccion", label: "Direccion" },
    { name: "localidad", label: "Localidad" },
    { name: "cuit", label: "CUIT/DNI" },
    { name: "email", label: "Email" },
    { name: "limite_credito", label: "Limite credito", type: "number" },
  ]);
  $("#cliente-form").onsubmit = async (ev) => {
    ev.preventDefault();
    await api("/api/clientes", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
    ev.target.reset();
    await loadClientes();
  };
  if (!can("Clientes", "agregar") && !can("Clientes", "modificar")) {
    $$("input,select,button", $("#cliente-form")).forEach((el) => el.disabled = true);
  }

  form($("#proveedor-form"), [
    { name: "nombre", label: "Nombre" },
    { name: "contacto", label: "Contacto" },
    { name: "telefono", label: "Telefono" },
    { name: "email", label: "Email" },
    { name: "direccion", label: "Direccion" },
    { name: "localidad", label: "Localidad" },
    { name: "cuit", label: "CUIT" },
    { name: "observaciones", label: "Observaciones" },
  ]);
  $("#proveedor-form").onsubmit = async (ev) => {
    ev.preventDefault();
    await api("/api/proveedores", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
    ev.target.reset();
    await loadProveedor();
  };
  if (!can("Proveedores", "agregar") && !can("Proveedores", "modificar")) {
    $$("input,select,button", $("#proveedor-form")).forEach((el) => el.disabled = true);
  }

  form($("#usuario-form"), [
    { name: "nombre", label: "Nombre" },
    { name: "usuario", label: "Usuario" },
    { name: "password", label: "Contrasena" },
    { name: "rol", label: "Rol", type: "select", options: () => [{ value: "ADMIN", label: "ADMIN" }, { value: "CAJERO", label: "CAJERO" }] },
    { name: "activo", label: "Activo", type: "select", options: () => [{ value: 1, label: "Si" }, { value: 0, label: "No" }] },
  ]);
  $("#usuario-form").onsubmit = async (ev) => {
    ev.preventDefault();
    await api("/api/usuarios", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
    ev.target.reset();
    await loadUsuarios();
  };
  $("#permisos-form").onsubmit = async (ev) => {
    ev.preventDefault();
    const userId = ev.target.elements.usuario_id.value;
    if (!userId) return alert("Elegi un usuario primero.");
    const permisos = $$("#permisos-list tr[data-module]").map((row) => {
      const permiso = { modulo: row.dataset.module };
      $$("input[type='checkbox']", row).forEach((input) => {
        permiso[input.dataset.action] = input.checked ? 1 : 0;
      });
      return permiso;
    });
    await api(`/api/usuarios/${userId}/permisos`, { method: "POST", body: JSON.stringify({ permisos }) });
    alert("Permisos guardados.");
  };
  if (!can("Usuarios", "agregar") && !can("Usuarios", "modificar")) {
    $$("input,select,button", $("#usuario-form")).forEach((el) => el.disabled = true);
    $$("input,select,button", $("#permisos-form")).forEach((el) => el.disabled = true);
  }
}

document.addEventListener("click", async (ev) => {
  const nav = ev.target.closest("aside button");
  if (nav) {
    if (!canView(nav.dataset.view)) return;
    $$("aside button").forEach((b) => b.classList.toggle("active", b === nav));
    $$(".view").forEach((v) => v.classList.remove("active"));
    state.current = nav.dataset.view;
    $(`#${state.current}`).classList.add("active");
    $("#search").value = "";
    await refresh();
  }
  const del = ev.target.dataset.del;
  if (del && confirm("Seguro que queres borrar este registro?")) {
    const [tableName, id] = del.split(":");
    await api(`/api/${tableName}/${id}`, { method: "DELETE" });
    await refresh();
  }
  const productEdit = ev.target.dataset.editProducto;
  if (productEdit) fillForm("#producto-form", state.productos.find((p) => String(p.id) === productEdit));
  const clientEdit = ev.target.dataset.editCliente;
  if (clientEdit) fillForm("#cliente-form", (await api("/api/clientes")).find((c) => String(c.id) === clientEdit));
  const provEdit = ev.target.dataset.editProveedor;
  if (provEdit) fillForm("#proveedor-form", (await api("/api/proveedores")).find((p) => String(p.id) === provEdit));
  const userEdit = ev.target.dataset.editUsuario;
  if (userEdit) {
    const user = (await api("/api/usuarios")).find((u) => String(u.id) === userEdit);
    user.password = "";
    fillForm("#usuario-form", user);
  }
  const permisosUser = ev.target.dataset.permisos;
  if (permisosUser) await loadPermisos(permisosUser);
  const simpleEdit = ev.target.dataset.editSimple;
  if (simpleEdit) {
    const [kind, id] = simpleEdit.split(":");
    fillForm(`#${kind}-form`, (await api(`/api/${kind}`)).find((r) => String(r.id) === id));
  }
  const remove = ev.target.dataset.removeItem;
  if (remove) {
    state.ticket = state.ticket.filter((i) => String(i.producto_id) !== remove);
    renderTicket();
  }
});

$("#search").addEventListener("input", refresh);

$("#add-item").onclick = () => {
  const id = $("#venta-producto").value;
  const p = state.productos.find((x) => String(x.id) === String(id));
  if (!p) return;
  const cantidad = Number($("#venta-cantidad").value || 1);
  const found = state.ticket.find((i) => String(i.producto_id) === String(id));
  if (found) {
    found.cantidad += cantidad;
    found.subtotal = found.cantidad * found.precio;
  } else {
    state.ticket.push({ producto_id: p.id, nombre: p.nombre, cantidad, precio: Number(p.precio_venta || 0), subtotal: cantidad * Number(p.precio_venta || 0) });
  }
  renderTicket();
};

$("#venta-form").onsubmit = async (ev) => {
  ev.preventDefault();
  const data = Object.fromEntries(new FormData(ev.target));
  data.items = state.ticket;
  await api("/api/ventas", { method: "POST", body: JSON.stringify(data) });
  state.ticket = [];
  await loadVentas();
  await loadDashboard();
  alert("Venta registrada.");
};

$("#caja-form").onsubmit = async (ev) => {
  ev.preventDefault();
  await api("/api/caja/abrir", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
  await loadCaja();
};
$("#mov-form").onsubmit = async (ev) => {
  ev.preventDefault();
  await api("/api/caja/movimiento", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
  ev.target.reset();
  await loadCaja();
};
$("#cierre-form").onsubmit = async (ev) => {
  ev.preventDefault();
  await api("/api/caja/cerrar", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
  ev.target.reset();
  await loadCaja();
};

(async function init() {
  const me = await api("/api/me");
  state.user = me.user;
  state.permisos = me.permisos;
  applyPermissions();
  await loadOptions();
  setupForms();
  $$(".view").forEach((v) => v.classList.remove("active"));
  $(`#${state.current}`).classList.add("active");
  $$("aside button").forEach((b) => b.classList.toggle("active", b.dataset.view === state.current));
  await refresh();
})();
