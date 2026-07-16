const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];
const money = (n) => `$${Number(n || 0).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let state = { user: null, options: {}, productos: [], ticket: [], current: "inicio", lastReport: null, cuenta: null };

async function api(url, opts = {}) {
  const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "No se pudo completar la accion.");
  return data;
}

function table(el, columns, data, actions) {
  const q = $("#search").value.trim().toLowerCase();
  const filtered = q ? data.filter((row) => Object.values(row).join(" ").toLowerCase().includes(q)) : data;
  el.innerHTML = `
    <thead><tr>${columns.map((c) => `<th>${c.label}</th>`).join("")}${actions ? "<th></th>" : ""}</tr></thead>
    <tbody>
      ${filtered.map((row) => `
        <tr>
          ${columns.map((c) => `<td>${c.format ? c.format(row[c.key], row) : escapeHtml(row[c.key] ?? "")}</td>`).join("")}
          ${actions ? `<td class="actions">${actions(row)}</td>` : ""}
        </tr>`).join("") || `<tr><td colspan="${columns.length + (actions ? 1 : 0)}">Sin datos</td></tr>`}
    </tbody>`;
}

function fillForm(selector, row) {
  const form = $(selector);
  Object.entries(row).forEach(([key, value]) => {
    if (form.elements[key]) form.elements[key].value = value ?? "";
  });
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadOptions() {
  state.options = await api("/api/options");
  state.productos = state.options.productos || [];
  const catOptions = [`<option value="">Sin categoria</option>`, ...(state.options.categorias || []).map((c) => `<option value="${c.id}">${c.nombre}</option>`)].join("");
  $("#producto-form").elements.categoria_id.innerHTML = catOptions;
  $("#precios-form").elements.categoria_id.innerHTML = [`<option value="__all__">Todas</option>`, `<option value="__none__">Sin categoria</option>`, ...(state.options.categorias || []).map((c) => `<option value="${c.id}">${c.nombre}</option>`)].join("");
  $("#venta-form").elements.cliente_id.innerHTML = [`<option value="">Consumidor final</option>`, ...(state.options.clientes || []).map((c) => `<option value="${c.id}">${c.nombre} (${money(c.saldo)})</option>`)].join("");
  $("#venta-producto").innerHTML = state.productos.map((p) => `<option value="${p.id}">${p.codigo} - ${p.nombre} - ${money(p.precio_venta)}</option>`).join("");
}

async function loadDashboard() {
  const d = await api("/api/dashboard");
  $("#dash-ventas").textContent = money(d.ventas.total);
  $("#dash-cant").textContent = `${d.ventas.cantidad || 0} operaciones`;
  $("#dash-productos").textContent = d.productos;
  $("#dash-clientes").textContent = d.clientes;
  $("#dash-stock").textContent = d.stock_bajo;
  $("#dash-caja").innerHTML = d.caja?.id
    ? `<strong>Abierta</strong><span>Apertura: ${money(d.caja.apertura)}</span><span>Efectivo: ${money(d.caja.efectivo)}</span>`
    : `<strong>Cerrada</strong><span>No hay caja abierta.</span>`;
  table($("#tabla-dash-top"), [
    { key: "nombre", label: "Producto" },
    { key: "cantidad", label: "Cant." },
    { key: "total", label: "Total", format: money },
  ], d.top || []);
}

async function loadProductos() {
  await loadOptions();
  const data = await api("/api/productos");
  table($("#tabla-productos"), [
    { key: "codigo", label: "Codigo" },
    { key: "nombre", label: "Producto" },
    { key: "categoria", label: "Categoria" },
    { key: "marca", label: "Marca" },
    { key: "precio_venta", label: "Venta", format: money },
    { key: "stock", label: "Stock" },
  ], data, (r) => `<button data-edit-producto="${r.id}">Editar</button><button class="danger" data-del-producto="${r.id}">Borrar</button>`);
}

async function loadClientes() {
  await loadOptions();
  const data = await api("/api/clientes");
  table($("#tabla-clientes"), [
    { key: "nombre", label: "Cliente" },
    { key: "telefono", label: "Telefono" },
    { key: "whatsapp", label: "WhatsApp" },
    { key: "localidad", label: "Localidad" },
    { key: "saldo", label: "Saldo", format: money },
  ], data, (r) => `<button data-cuenta="${r.id}">Cuenta</button><button data-edit-cliente="${r.id}">Editar</button>`);
}

async function loadCuenta(clienteId, scroll = true) {
  const data = await api(`/api/clientes/${clienteId}/cuenta`);
  state.cuenta = data;
  $("#cuenta-panel").hidden = false;
  $("#cuenta-title").textContent = `Cuenta corriente - ${data.cliente.nombre}`;
  $("#cuenta-sub").textContent = `${data.cliente.telefono || ""} ${data.cliente.cuit ? " - " + data.cliente.cuit : ""}`;
  $("#cuenta-saldo").textContent = money(data.cliente.saldo);
  $("#cuenta-debe").textContent = money(data.resumen.debe);
  $("#cuenta-haber").textContent = money(data.resumen.haber);
  $("#cuenta-movs").textContent = data.resumen.movimientos || 0;
  $("#pago-form").elements.cliente_id.value = data.cliente.id;
  table($("#tabla-cuenta"), [
    { key: "fecha", label: "Fecha" },
    { key: "comprobante", label: "Comprobante" },
    { key: "concepto", label: "Concepto" },
    { key: "debe", label: "Debe", format: money },
    { key: "haber", label: "Haber", format: money },
    { key: "saldo", label: "Saldo", format: money },
  ], data.movimientos || []);
  if (scroll) $("#cuenta-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

function printWindow(title, body) {
  const win = window.open("", title.toLowerCase(), "width=850,height=760");
  win.document.write(`
    <title>${escapeHtml(title)}</title>
    <style>
      body{font-family:Arial,sans-serif;padding:24px;color:#172033}
      .head{display:flex;justify-content:space-between;border-bottom:3px solid #1463d8;padding-bottom:16px;margin-bottom:18px}
      .brand{font-weight:bold;font-size:22px}.brand small{display:block;color:#64748b;font-size:13px;margin-top:4px}
      h1{margin:0;font-size:28px} table{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px}
      td,th{border-bottom:1px solid #ddd;padding:7px;text-align:left} th{background:#eef3f8}.total{text-align:right;font-size:22px;font-weight:bold;margin-top:18px}
    </style>
    <div class="head"><div><div class="brand">Bebidas San Martin<small>Sistema de gestion</small></div><h1>${escapeHtml(title)}</h1></div><div>${escapeHtml(new Date().toLocaleString("es-AR"))}</div></div>
    ${body}
  `);
  win.document.close();
  win.focus();
  win.print();
}

function ticketTotal() {
  return state.ticket.reduce((sum, item) => sum + Number(item.subtotal || 0), 0);
}

function renderTicket() {
  table($("#ticket"), [
    { key: "nombre", label: "Producto" },
    { key: "cantidad", label: "Cant." },
    { key: "precio", label: "Precio", format: money },
    { key: "subtotal", label: "Subtotal", format: money },
  ], state.ticket, (r) => `<button class="danger" data-remove="${r.producto_id}">Quitar</button>`);
  $("#ticket-total").textContent = `TOTAL: ${money(ticketTotal())}`;
}

async function loadVentas() {
  await loadOptions();
  const data = await api("/api/ventas");
  table($("#tabla-ventas"), [
    { key: "id", label: "Nro" },
    { key: "fecha", label: "Fecha" },
    { key: "cliente", label: "Cliente" },
    { key: "tipo", label: "Medio" },
    { key: "total", label: "Total", format: money },
  ], data, (r) => `<button data-print-ticket="${r.id}">Ticket</button>`);
  renderTicket();
}

function sistemaCaja(caja) {
  return {
    efectivo: Number(caja.apertura || 0) + Number(caja.efectivo || 0) + Number(caja.ingresos || 0) - Number(caja.gastos || 0),
    transferencia: Number(caja.transferencia || 0),
    debito: Number(caja.debito || 0),
    credito: Number(caja.credito || 0),
    posnet: Number(caja.posnet || 0),
  };
}

async function loadCaja() {
  const actual = await api("/api/caja/actual");
  const sistema = sistemaCaja(actual || {});
  const total = Object.values(sistema).reduce((a, b) => a + b, 0);
  $("#caja-estado").textContent = actual.id ? "Abierta" : "Cerrada";
  $("#caja-apertura").textContent = money(actual.apertura);
  $("#caja-entradas").textContent = money(Number(actual.efectivo || 0) + Number(actual.transferencia || 0) + Number(actual.debito || 0) + Number(actual.credito || 0) + Number(actual.posnet || 0) + Number(actual.ingresos || 0));
  $("#caja-total").textContent = money(total);
  $("#arqueo-grid").innerHTML = ["efectivo", "transferencia", "debito", "credito", "posnet"].map((m) => `<label>${m}</label><strong>${money(sistema[m])}</strong><input name="${m}_contado" type="number" step="0.01" value="${sistema[m].toFixed(2)}">`).join("");
  const cajas = await api("/api/caja");
  table($("#tabla-caja"), [
    { key: "fecha", label: "Fecha" },
    { key: "estado", label: "Estado" },
    { key: "apertura", label: "Apertura", format: money },
    { key: "cierre", label: "Cierre", format: money },
    { key: "diferencia", label: "Diferencia", format: money },
  ], cajas);
}

async function loadReportes(ev) {
  if (ev) ev.preventDefault();
  const today = new Date().toISOString().slice(0, 10);
  const form = $("#reportes-form");
  const desde = form.elements.desde.value || today;
  const hasta = form.elements.hasta.value || desde;
  form.elements.desde.value = desde;
  form.elements.hasta.value = hasta;
  const data = await api(`/api/reportes?desde=${encodeURIComponent(desde)}&hasta=${encodeURIComponent(hasta)}`);
  state.lastReport = data;
  $("#rep-ventas").textContent = data.resumen.ventas || 0;
  $("#rep-total").textContent = money(data.resumen.total);
  $("#rep-stock").textContent = data.bajos.length;
  $("#rep-periodo").textContent = `${desde} / ${hasta}`;
  table($("#tabla-medios"), [{ key: "tipo", label: "Medio" }, { key: "cantidad", label: "Ventas" }, { key: "total", label: "Total", format: money }], data.medios);
  table($("#tabla-top"), [{ key: "codigo", label: "Codigo" }, { key: "nombre", label: "Producto" }, { key: "cantidad", label: "Cant." }, { key: "total", label: "Total", format: money }], data.top);
  table($("#tabla-bajos"), [{ key: "codigo", label: "Codigo" }, { key: "nombre", label: "Producto" }, { key: "stock", label: "Stock" }, { key: "stock_minimo", label: "Minimo" }], data.bajos);
}

async function loadHerramientas() {
  await loadOptions();
  const backups = await api("/api/backups");
  table($("#tabla-backups"), [{ key: "archivo", label: "Archivo" }, { key: "fecha", label: "Fecha" }, { key: "tamano", label: "Tamano", format: (v) => `${(Number(v) / 1024).toFixed(1)} KB` }], backups, (r) => `<button data-backup="${r.archivo}">Descargar</button>`);
  if (state.user?.rol === "ADMIN") {
    const aud = await api("/api/auditoria");
    table($("#tabla-auditoria"), [{ key: "fecha", label: "Fecha" }, { key: "usuario", label: "Usuario" }, { key: "accion", label: "Accion" }, { key: "detalle", label: "Detalle" }], aud);
  } else {
    $("#auditoria-box").hidden = true;
  }
}

async function refresh() {
  if (state.current === "inicio") return loadDashboard();
  if (state.current === "productos") return loadProductos();
  if (state.current === "clientes") return loadClientes();
  if (state.current === "ventas") return loadVentas();
  if (state.current === "caja") return loadCaja();
  if (state.current === "reportes") return loadReportes();
  if (state.current === "herramientas") return loadHerramientas();
}

document.addEventListener("click", async (ev) => {
  const nav = ev.target.closest("aside button");
  if (nav) {
    $$("aside button").forEach((b) => b.classList.toggle("active", b === nav));
    $$(".view").forEach((v) => v.classList.remove("active"));
    state.current = nav.dataset.view;
    $(`#${state.current}`).classList.add("active");
    $("#search").value = "";
    await refresh();
  }
  if (ev.target.dataset.editProducto) fillForm("#producto-form", state.productos.find((p) => String(p.id) === ev.target.dataset.editProducto));
  if (ev.target.dataset.delProducto && confirm("Borrar producto?")) {
    await api(`/api/productos/${ev.target.dataset.delProducto}`, { method: "DELETE" });
    await loadProductos();
  }
  if (ev.target.dataset.editCliente) fillForm("#cliente-form", (await api("/api/clientes")).find((c) => String(c.id) === ev.target.dataset.editCliente));
  if (ev.target.dataset.cuenta) await loadCuenta(ev.target.dataset.cuenta);
  if (ev.target.dataset.remove) {
    state.ticket = state.ticket.filter((item) => String(item.producto_id) !== ev.target.dataset.remove);
    renderTicket();
  }
  if (ev.target.dataset.printTicket) {
    const data = await api(`/api/ventas/${ev.target.dataset.printTicket}`);
    printVenta("Ticket", data, false);
  }
  if (ev.target.dataset.backup) window.location.href = `/api/backups/${encodeURIComponent(ev.target.dataset.backup)}`;
});

$("#search").addEventListener("input", refresh);

$("#producto-form").onsubmit = async (ev) => {
  ev.preventDefault();
  await api("/api/productos", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
  ev.target.reset();
  await loadProductos();
};

$("#cliente-form").onsubmit = async (ev) => {
  ev.preventDefault();
  await api("/api/clientes", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
  ev.target.reset();
  await loadClientes();
};

$("#pago-form").onsubmit = async (ev) => {
  ev.preventDefault();
  const data = Object.fromEntries(new FormData(ev.target));
  await api(`/api/clientes/${data.cliente_id}/pago`, { method: "POST", body: JSON.stringify(data) });
  ev.target.reset();
  await loadClientes();
  await loadCuenta(data.cliente_id, false);
};

$("#print-cuenta").onclick = () => {
  const d = state.cuenta;
  if (!d) return;
  const rows = (d.movimientos || []).map((m) => `<tr><td>${escapeHtml(m.fecha)}</td><td>${escapeHtml(m.comprobante)}</td><td>${escapeHtml(m.concepto)}</td><td>${money(m.debe)}</td><td>${money(m.haber)}</td><td>${money(m.saldo)}</td></tr>`).join("");
  printWindow(`Cuenta corriente - ${d.cliente.nombre}`, `<p>Cliente: ${escapeHtml(d.cliente.nombre)}</p><div class="total">Saldo ${money(d.cliente.saldo)}</div><table><thead><tr><th>Fecha</th><th>Comp.</th><th>Concepto</th><th>Debe</th><th>Haber</th><th>Saldo</th></tr></thead><tbody>${rows}</tbody></table>`);
};

$("#add-item").onclick = () => {
  const p = state.productos.find((x) => String(x.id) === $("#venta-producto").value);
  if (!p) return;
  const cantidad = Number($("#venta-cantidad").value || 1);
  if (cantidad <= 0) return alert("Cantidad invalida.");
  const found = state.ticket.find((i) => String(i.producto_id) === String(p.id));
  if (found) {
    found.cantidad += cantidad;
    found.subtotal = found.cantidad * found.precio;
  } else {
    state.ticket.push({ producto_id: p.id, nombre: p.nombre, cantidad, precio: Number(p.precio_venta || 0), subtotal: cantidad * Number(p.precio_venta || 0) });
  }
  renderTicket();
};

function ventaDesdeTicket() {
  const form = $("#venta-form");
  const cliente = form.elements.cliente_id.options[form.elements.cliente_id.selectedIndex]?.text || "Consumidor final";
  return { venta: { id: "-", fecha: new Date().toLocaleString("es-AR"), cliente, tipo: form.elements.tipo.value, total: ticketTotal() }, detalle: state.ticket.map((i) => ({ producto: i.nombre, cantidad: i.cantidad, precio: i.precio, subtotal: i.subtotal })) };
}

function printVenta(title, data, remito) {
  const rows = (data.detalle || []).map((i) => `<tr><td>${i.cantidad}</td><td>${escapeHtml(i.producto)}</td>${remito ? "" : `<td>${money(i.precio)}</td><td>${money(i.subtotal)}</td>`}</tr>`).join("");
  printWindow(title, `<p>Cliente: ${escapeHtml(data.venta.cliente || "")}<br>Medio: ${escapeHtml(data.venta.tipo || "")}</p><table><thead><tr><th>Cant.</th><th>Producto</th>${remito ? "" : "<th>Precio</th><th>Subtotal</th>"}</tr></thead><tbody>${rows}</tbody></table>${remito ? "" : `<div class="total">TOTAL ${money(data.venta.total)}</div>`}`);
}

$("#print-presupuesto").onclick = () => {
  if (!state.ticket.length) return alert("Agregue productos.");
  printVenta("Presupuesto", ventaDesdeTicket(), false);
};
$("#print-remito").onclick = () => {
  if (!state.ticket.length) return alert("Agregue productos.");
  printVenta("Remito", ventaDesdeTicket(), true);
};

$("#venta-form").onsubmit = async (ev) => {
  ev.preventDefault();
  if (!state.ticket.length) return alert("Agregue productos.");
  const data = Object.fromEntries(new FormData(ev.target));
  data.items = state.ticket;
  const result = await api("/api/ventas", { method: "POST", body: JSON.stringify(data) });
  state.ticket = [];
  renderTicket();
  await loadVentas();
  await loadDashboard();
  alert(`Venta registrada Nro ${result.venta_id}`);
};

$("#abrir-caja-form").onsubmit = async (ev) => {
  ev.preventDefault();
  await api("/api/caja/abrir", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
  await loadCaja();
};
$("#mov-caja-form").onsubmit = async (ev) => {
  ev.preventDefault();
  await api("/api/caja/movimiento", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
  ev.target.reset();
  await loadCaja();
};
$("#cerrar-caja-form").onsubmit = async (ev) => {
  ev.preventDefault();
  await api("/api/caja/cerrar", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(ev.target))) });
  ev.target.reset();
  await loadCaja();
};

$("#reportes-form").onsubmit = loadReportes;
$("#print-report").onclick = () => {
  if (!state.lastReport) return alert("Actualice el reporte.");
  printWindow("Reporte comercial", `<div class="total">Total vendido ${money(state.lastReport.resumen.total)}</div><h2>Medios</h2>${$("#tabla-medios").outerHTML}<h2>Top productos</h2>${$("#tabla-top").outerHTML}`);
};

async function previewPrecios(aplicar) {
  const data = Object.fromEntries(new FormData($("#precios-form")));
  data.redondear = $("#precios-form").elements.redondear.checked ? 1 : 0;
  data.aplicar = aplicar ? 1 : 0;
  if (aplicar && !confirm("Aplicar cambios de precios?")) return;
  const result = await api("/api/precios/categoria", { method: "POST", body: JSON.stringify(data) });
  $("#precios-status").textContent = `${result.aplicado ? "Aplicado" : "Vista previa"}: ${result.cantidad} productos en ${result.categoria}.`;
  table($("#tabla-precios"), [{ key: "codigo", label: "Codigo" }, { key: "nombre", label: "Producto" }, { key: "anterior", label: "Antes", format: money }, { key: "nuevo", label: "Nuevo", format: money }], result.cambios);
  if (aplicar) await loadOptions();
}
$("#preview-precios").onclick = () => previewPrecios(false);
$("#precios-form").onsubmit = async (ev) => {
  ev.preventDefault();
  await previewPrecios(true);
};

$("#crear-backup").onclick = async () => {
  await api("/api/backup", { method: "POST", body: "{}" });
  await loadHerramientas();
};
document.addEventListener("keydown", (ev) => {
  if (state.current !== "ventas") return;
  if (ev.key !== "F3") return;

  ev.preventDefault();

  const q = prompt("Buscar producto por codigo, nombre o marca:");
  if (!q) return;

  const texto = q.trim().toLowerCase();
  const encontrados = state.productos.filter((p) =>
    [p.codigo, p.nombre, p.marca, p.categoria]
      .join(" ")
      .toLowerCase()
      .includes(texto)
  );

  if (!encontrados.length) {
    alert("No se encontraron productos.");
    return;
  }

  const elegido = encontrados[0];
  $("#venta-producto").value = elegido.id;
  $("#venta-cantidad").focus();
});
(async function init() {
  const me = await api("/api/me");
  state.user = me.user;
  await loadOptions();
  await refresh();
})();
