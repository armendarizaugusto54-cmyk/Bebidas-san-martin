const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];
const money = (n) => `$${Number(n || 0).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
let state = { options: {}, productos: [], ticket: [], current: "inicio", permisos: {}, user: null, selectedProductId: null, lastSale: null, lastReport: null };
let cajaActual = {};
let correccionCaja = null;
const viewModules = {
  inicio: "Dashboard",
  ventas: "Ventas",
  compras: "Compras",
  productos: "Productos",
  clientes: "Clientes",
  caja: "Caja",
  categorias: "Categorias",
  marcas: "Marcas",
  proveedores: "Proveedores",
  reportes: "Reportes",
  configuracion: "Configuracion",
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

function currentProduct() {
  const id = state.selectedProductId || $("#venta-producto")?.value;
  return state.productos.find((x) => String(x.id) === String(id));
}

function setVentaProduct(product) {
  if (!product) return;
  state.selectedProductId = product.id;
  $("#venta-producto").value = product.id;
  $("#venta-producto-nombre").value = `${product.codigo} - ${product.nombre} (${money(product.precio_venta)})`;
  $("#venta-cantidad").focus();
}

function renderProductSearch() {
  const q = $("#producto-modal-search").value.trim().toLowerCase();
  const productos = state.productos
    .filter((p) => [p.codigo, p.nombre, p.marca, p.categoria_nombre].join(" ").toLowerCase().includes(q))
    .slice(0, 80);
  $("#producto-modal-table").innerHTML = `
    <thead>
      <tr><th>Codigo</th><th>Producto</th><th>Marca</th><th>Precio</th><th>Stock</th><th></th></tr>
    </thead>
    <tbody>
      ${productos.map((p) => `
        <tr data-product-row="${p.id}">
          <td>${p.codigo || ""}</td>
          <td>${p.nombre || ""}</td>
          <td>${p.marca || ""}</td>
          <td>${money(p.precio_venta)}</td>
          <td>${p.stock ?? ""}</td>
          <td><button type="button" data-select-product="${p.id}">Seleccionar</button></td>
        </tr>`).join("") || `<tr><td colspan="6">Sin productos</td></tr>`}
    </tbody>`;
}

function openProductSearch() {
  if (state.current !== "ventas") return;
  $("#producto-modal").hidden = false;
  $("#producto-modal-search").value = "";
  renderProductSearch();
  $("#producto-modal-search").focus();
}

function closeProductSearch() {
  $("#producto-modal").hidden = true;
}

function shouldOpenProductSearch(ev) {
  if (state.current !== "ventas") return false;
  if (!$("#producto-modal").hidden) return false;
  const tag = ev.target?.tagName?.toLowerCase();
  const typing = tag === "input" || tag === "textarea" || tag === "select";
  if (ev.key === "F3") return true;
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") return true;
  if (ev.key === "/" && !typing) return true;
  return false;
}

function ticketTotal() {
  return state.ticket.reduce((a, i) => a + Number(i.subtotal), 0);
}

function ticketQuantityFor(productId) {
  return state.ticket
    .filter((i) => String(i.producto_id) === String(productId))
    .reduce((a, i) => a + Number(i.cantidad), 0);
}

function downloadText(filename, text) {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function toCsv(rows) {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0]);
  const esc = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  return [headers.join(","), ...rows.map((row) => headers.map((h) => esc(row[h])).join(","))].join("\n");
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
  clienteSelect.innerHTML = (state.options.clientes || []).map((c) => `<option value="${c.id}">${c.nombre}</option>`).join("");
  $("#venta-producto").innerHTML = state.productos.map((p) => `<option value="${p.id}">${p.codigo} - ${p.nombre} (${money(p.precio_venta)})</option>`).join("");
  if (!currentProduct() && state.productos.length) {
    setVentaProduct(state.productos[0]);
  } else if (currentProduct()) {
    setVentaProduct(currentProduct());
  }
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
  const total = ticketTotal();
  const items = state.ticket.reduce((a, i) => a + Number(i.cantidad), 0);
  const pago = Number($("#venta-pago").value || 0);
  $("#ticket-total").textContent = `TOTAL: ${money(total)}`;
  $("#ticket-items").textContent = `${items} item${items === 1 ? "" : "s"}`;
  $("#ticket-vuelto").textContent = `Vuelto: ${money(Math.max(pago - total, 0))}`;
}

async function loadCompras() {
  await loadOptions();
  $("#compra-form").elements.proveedor_id.innerHTML = (state.options.proveedores || []).map((p) => `<option value="${p.id}">${p.nombre}</option>`).join("");
  $("#compra-form").elements.producto_id.innerHTML = state.productos.map((p) => `<option value="${p.id}">${p.codigo} - ${p.nombre}</option>`).join("");
  const compras = await api("/api/compras");
  table($("#tabla-compras"), [
    { key: "id", label: "Nro" },
    { key: "fecha", label: "Fecha" },
    { key: "proveedor", label: "Proveedor" },
    { key: "factura", label: "Factura" },
    { key: "total", label: "Total", format: money },
    { key: "observaciones", label: "Observaciones" },
  ], compras);
}

async function loadCaja() {
  const actual = await api("/api/caja/actual");
  cajaActual = actual || {};
  const cajas = await api("/api/caja");
  const entradas = Number(actual.efectivo || 0) + Number(actual.transferencia || 0) + Number(actual.debito || 0) + Number(actual.credito || 0) + Number(actual.posnet || 0) + Number(actual.ingresos || 0);
  const total = Number(actual.apertura || 0) + entradas - Number(actual.gastos || 0);
  $("#caja-estado").textContent = actual.id ? "Abierta" : "Cerrada";
  $("#caja-apertura").textContent = money(actual.apertura);
  $("#caja-entradas").textContent = money(entradas);
  $("#caja-total").textContent = money(total);
  renderArqueo();
  table($("#tabla-caja"), [
    { key: "fecha", label: "Fecha" },
    { key: "estado", label: "Estado" },
    { key: "apertura", label: "Apertura", format: money },
    { key: "efectivo", label: "Efectivo", format: money },
    { key: "transferencia", label: "Transferencia", format: money },
    { key: "gastos", label: "Gastos", format: money },
    { key: "cierre", label: "Cierre", format: money },
    { key: "diferencia", label: "Diferencia", format: money },
  ], cajas, (r) => state.user?.rol === "ADMIN" ? `<button type="button" class="secondary" data-cargar-cierre="${r.id}">Modificar</button>` : "");
  await loadCierresAdmin();
}

function arqueoSistema() {
  return {
    efectivo: Number(cajaActual.apertura || 0) + Number(cajaActual.efectivo || 0) + Number(cajaActual.ingresos || 0) - Number(cajaActual.gastos || 0),
    transferencia: Number(cajaActual.transferencia || 0),
    debito: Number(cajaActual.debito || 0),
    credito: Number(cajaActual.credito || 0),
    posnet: Number(cajaActual.posnet || 0),
  };
}

function renderArqueo() {
  const sistema = arqueoSistema();
  const form = $("#cierre-form");
  if (!form) return;
  let totalSistema = 0;
  let totalContado = 0;
  ["efectivo", "transferencia", "debito", "credito", "posnet"].forEach((medio) => {
    const esperado = sistema[medio] || 0;
    const contado = Number(form.elements[`${medio}_contado`]?.value || 0);
    totalSistema += esperado;
    totalContado += contado;
    $(`#sis-${medio}`).textContent = money(esperado);
    const dif = contado - esperado;
    const difEl = $(`#dif-${medio}`);
    difEl.textContent = money(dif);
    difEl.classList.toggle("diff-ok", Math.abs(dif) < 0.01);
    difEl.classList.toggle("diff-bad", Math.abs(dif) >= 0.01);
  });
  const totalDif = totalContado - totalSistema;
  $("#arqueo-sistema").textContent = money(totalSistema);
  $("#arqueo-contado").textContent = money(totalContado);
  $("#arqueo-diferencia").textContent = money(totalDif);
  $("#arqueo-diferencia").classList.toggle("diff-ok", Math.abs(totalDif) < 0.01);
  $("#arqueo-diferencia").classList.toggle("diff-bad", Math.abs(totalDif) >= 0.01);
}

async function loadCierresAdmin() {
  const panel = $("#buscar-cierres-admin");
  const form = $("#corregir-arqueo-form");
  if (!panel || !form) return;
  if (state.user?.rol !== "ADMIN") {
    panel.hidden = true;
    form.hidden = true;
    return;
  }
  panel.hidden = false;
  const q = encodeURIComponent($("#buscar-cierre-texto")?.value || "");
  const cierres = await api(`/api/caja/cierres?q=${q}`);
  table($("#tabla-cierres-admin"), [
    { key: "id", label: "Nro" },
    { key: "fecha", label: "Fecha" },
    { key: "estado", label: "Estado" },
    { key: "cierre", label: "Contado", format: money },
    { key: "diferencia", label: "Dif.", format: money },
    { key: "usuario", label: "Cerro" },
    { key: "corregido", label: "Corregido", format: (v) => Number(v || 0) === 1 ? "Si" : "No" },
    { key: "usuario_correccion", label: "Corrigio" },
  ], cierres, (r) => `<button type="button" data-cargar-cierre="${r.id}">Modificar</button>`);
}

async function loadCorreccionArqueo(cajaId = "") {
  const form = $("#corregir-arqueo-form");
  if (!form) return;
  if (state.user?.rol !== "ADMIN") {
    form.hidden = true;
    return;
  }
  const suffix = cajaId ? `?caja_id=${encodeURIComponent(cajaId)}` : "";
  const data = await api(`/api/caja/ultimo-arqueo${suffix}`);
  correccionCaja = data;
  if (!data.caja?.id) {
    form.hidden = true;
    return;
  }
  form.hidden = false;
  $("#correccion-titulo").textContent = `Modificar caja Nro ${data.caja.id}`;
  $("#correccion-ayuda").textContent = `Caja ${data.caja.estado || ""} del ${data.caja.fecha || ""}. Ajusta los importes y guarda el motivo.`;
  form.elements.caja_id.value = data.caja.id;
  form.elements.arqueo_id.value = data.arqueo?.id || "";
  ["efectivo", "transferencia", "debito", "credito", "posnet"].forEach((medio) => {
    form.elements[`${medio}_contado`].value = Number(data.contado?.[medio] || 0).toFixed(2);
  });
  renderCorreccionArqueo();
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderCorreccionArqueo() {
  const form = $("#corregir-arqueo-form");
  if (!form || !correccionCaja?.sistema) return;
  let totalSistema = 0;
  let totalContado = 0;
  ["efectivo", "transferencia", "debito", "credito", "posnet"].forEach((medio) => {
    const esperado = Number(correccionCaja.sistema[medio] || 0);
    const contado = Number(form.elements[`${medio}_contado`]?.value || 0);
    totalSistema += esperado;
    totalContado += contado;
    $(`#corr-sis-${medio}`).textContent = money(esperado);
    const dif = contado - esperado;
    const difEl = $(`#corr-dif-${medio}`);
    difEl.textContent = money(dif);
    difEl.classList.toggle("diff-ok", Math.abs(dif) < 0.01);
    difEl.classList.toggle("diff-bad", Math.abs(dif) >= 0.01);
  });
  const totalDif = totalContado - totalSistema;
  $("#corr-sistema").textContent = money(totalSistema);
  $("#corr-contado").textContent = money(totalContado);
  $("#corr-diferencia").textContent = money(totalDif);
  $("#corr-diferencia").classList.toggle("diff-ok", Math.abs(totalDif) < 0.01);
  $("#corr-diferencia").classList.toggle("diff-bad", Math.abs(totalDif) >= 0.01);
}

async function loadReportes(ev) {
  if (ev) ev.preventDefault();
  const formData = Object.fromEntries(new FormData($("#reportes-form")));
  const today = new Date().toISOString().slice(0, 10);
  const desde = formData.desde || today;
  const hasta = formData.hasta || desde;
  $("#reportes-form").elements.desde.value = desde;
  $("#reportes-form").elements.hasta.value = hasta;
  const data = await api(`/api/reportes?desde=${encodeURIComponent(desde)}&hasta=${encodeURIComponent(hasta)}`);
  state.lastReport = data;
  $("#rep-ventas").textContent = data.resumen.ventas || 0;
  $("#rep-total").textContent = money(data.resumen.total);
  $("#rep-bajos").textContent = data.bajos.length;
  $("#rep-top").textContent = data.top[0]?.nombre || "-";
  table($("#tabla-medios"), [
    { key: "tipo", label: "Medio" },
    { key: "cantidad", label: "Ventas" },
    { key: "total", label: "Total", format: money },
  ], data.medios);
  table($("#tabla-top"), [
    { key: "codigo", label: "Codigo" },
    { key: "nombre", label: "Producto" },
    { key: "cantidad", label: "Cantidad" },
    { key: "total", label: "Total", format: money },
  ], data.top);
  table($("#tabla-movimientos"), [
    { key: "fecha", label: "Fecha" },
    { key: "tipo", label: "Tipo" },
    { key: "producto", label: "Producto" },
    { key: "cantidad", label: "Cantidad" },
    { key: "stock_anterior", label: "Antes" },
    { key: "stock_nuevo", label: "Despues" },
    { key: "observacion", label: "Obs." },
  ], data.movimientos);
  table($("#tabla-reporte-bajos"), [
    { key: "codigo", label: "Codigo" },
    { key: "nombre", label: "Producto" },
    { key: "marca", label: "Marca" },
    { key: "stock", label: "Stock" },
    { key: "stock_minimo", label: "Minimo" },
  ], data.bajos);
}

async function refresh() {
  const current = state.current;
  if (!canView(current)) return;
  if (current === "inicio") return loadDashboard();
  if (current === "productos") return loadProductos();
  if (current === "clientes") return loadClientes();
  if (current === "ventas") return loadVentas();
  if (current === "compras") return loadCompras();
  if (current === "caja") return loadCaja();
  if (current === "proveedores") return loadProveedor();
  if (current === "usuarios") return loadUsuarios();
  if (current === "reportes") return loadReportes();
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

  $("#compra-form").onsubmit = async (ev) => {
    ev.preventDefault();
    await api("/api/compras", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
    ev.target.reset();
    await loadCompras();
    await loadDashboard();
    alert("Compra registrada.");
  };
  $("#reportes-form").onsubmit = loadReportes;
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
  const selectProduct = ev.target.dataset.selectProduct;
  if (selectProduct) {
    const product = state.productos.find((p) => String(p.id) === String(selectProduct));
    setVentaProduct(product);
    closeProductSearch();
  }
  if (ev.target.closest("[data-product-row]") && !ev.target.dataset.selectProduct) {
    const product = state.productos.find((p) => String(p.id) === String(ev.target.closest("[data-product-row]").dataset.productRow));
    setVentaProduct(product);
    closeProductSearch();
  }
  const cargarCierre = ev.target.dataset.cargarCierre;
  if (cargarCierre) {
    await loadCorreccionArqueo(cargarCierre);
  }
});

$("#search").addEventListener("input", refresh);
$("#venta-pago").addEventListener("input", renderTicket);
$("#venta-codigo").addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter") return;
  ev.preventDefault();
  const code = ev.target.value.trim().toLowerCase();
  const product = state.productos.find((p) => String(p.codigo || "").toLowerCase() === code);
  if (!product) return alert("Producto no encontrado.");
  setVentaProduct(product);
  $("#add-item").click();
  ev.target.value = "";
});
$("#buscar-producto").addEventListener("click", openProductSearch);
$("#cerrar-producto-modal").addEventListener("click", closeProductSearch);
$("#producto-modal-search").addEventListener("input", renderProductSearch);
$("#producto-modal").addEventListener("click", (ev) => {
  if (ev.target.id === "producto-modal") closeProductSearch();
});
document.addEventListener("keydown", (ev) => {
  if (shouldOpenProductSearch(ev)) {
    ev.preventDefault();
    ev.stopPropagation();
    openProductSearch();
  }
  if (ev.key === "Escape" && !$("#producto-modal").hidden) {
    closeProductSearch();
  }
}, true);

$("#add-item").onclick = () => {
  const p = currentProduct();
  if (!p) return;
  const cantidad = Number($("#venta-cantidad").value || 1);
  if (cantidad <= 0) return alert("Ingrese una cantidad valida.");
  if (ticketQuantityFor(p.id) + cantidad > Number(p.stock || 0)) {
    return alert(`Stock insuficiente. Disponible: ${p.stock}`);
  }
  const found = state.ticket.find((i) => String(i.producto_id) === String(p.id));
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
  if (!state.ticket.length) return alert("Agregue productos al ticket.");
  const data = Object.fromEntries(new FormData(ev.target));
  data.items = state.ticket;
  const result = await api("/api/ventas", { method: "POST", body: JSON.stringify(data) });
  state.lastSale = await api(`/api/ventas/${result.venta_id}/detalle`);
  state.ticket = [];
  await loadVentas();
  await loadDashboard();
  alert(`Venta registrada. Nro ${result.venta_id}`);
};

$("#print-ticket").onclick = () => {
  if (!state.lastSale) return alert("Todavia no hay un ticket para imprimir.");
  const sale = state.lastSale.venta;
  const lines = state.lastSale.detalle.map((item) => `
    <tr>
      <td>${item.cantidad}</td>
      <td>${item.producto}</td>
      <td>${money(item.precio)}</td>
      <td>${money(item.subtotal)}</td>
    </tr>`).join("");
  const win = window.open("", "ticket", "width=420,height=650");
  win.document.write(`
    <title>Ticket ${sale.id}</title>
    <style>
      body{font-family:Arial,sans-serif;padding:16px}
      h1{font-size:20px;margin:0 0 8px}
      table{width:100%;border-collapse:collapse;font-size:13px}
      td,th{border-bottom:1px solid #ddd;padding:6px;text-align:left}
      .total{text-align:right;font-size:18px;font-weight:bold;margin-top:12px}
    </style>
    <h1>Bebidas San Martin</h1>
    <p>Ticket Nro ${sale.id}<br>Fecha: ${sale.fecha}<br>Cliente: ${sale.cliente || ""}<br>Medio: ${sale.tipo}</p>
    <table><thead><tr><th>Cant</th><th>Producto</th><th>Precio</th><th>Subt.</th></tr></thead><tbody>${lines}</tbody></table>
    <div class="total">TOTAL ${money(sale.total)}</div>
  `);
  win.document.close();
  win.print();
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
$("#cierre-form").addEventListener("input", renderArqueo);
$("#buscar-cierre-texto").addEventListener("input", loadCierresAdmin);
$("#actualizar-cierres").addEventListener("click", loadCierresAdmin);
$("#corregir-arqueo-form").addEventListener("input", renderCorreccionArqueo);
$("#corregir-arqueo-form").onsubmit = async (ev) => {
  ev.preventDefault();
  const data = Object.fromEntries(new FormData(ev.target));
  if (!data.caja_id) return alert("Primero elegi una caja para modificar.");
  if (!data.motivo?.trim()) return alert("Ingrese el motivo de correccion.");
  await api("/api/caja/corregir-arqueo", { method: "POST", body: JSON.stringify(data) });
  ev.target.elements.motivo.value = "";
  await loadCaja();
  alert("Correccion guardada.");
};

$("#crear-backup").onclick = async () => {
  const result = await api("/api/backup", { method: "POST", body: "{}" });
  $("#backup-status").textContent = `Backup creado: ${result.archivo}`;
};

$("#export-productos").onclick = () => {
  downloadText("productos.csv", toCsv(state.productos));
};

$("#export-report").onclick = () => {
  if (!state.lastReport) return alert("Actualiza el reporte primero.");
  const rows = [
    ...state.lastReport.medios.map((r) => ({ tipo: "medio_pago", ...r })),
    ...state.lastReport.top.map((r) => ({ tipo: "producto_vendido", ...r })),
    ...state.lastReport.bajos.map((r) => ({ tipo: "stock_bajo", ...r })),
  ];
  downloadText("reporte.csv", toCsv(rows));
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
