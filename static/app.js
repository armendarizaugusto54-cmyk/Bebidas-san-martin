const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];
const money = (n) => `$${Number(n || 0).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let state = { user: null, options: {}, productos: [], categorias: [], clientes: [], ticket: [], current: "inicio", lastReport: null, cuenta: null, cajaActual: null, cajaDetalle: null, productosFiltrados: [], clientesFiltrados: [] };

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

function currentProduct() {
  return state.productos.find((x) => String(x.id) === String($("#venta-producto").value));
}

function setVentaProduct(product) {
  if (!product) return;
  $("#venta-producto").value = product.id;
  $("#venta-producto-nombre").value = `${product.codigo || ""} - ${product.nombre} - ${money(product.precio_venta)} | Stock: ${product.stock ?? 0}`;
  $("#venta-cantidad").focus();
  $("#venta-cantidad").select();
}

function renderProductSearch() {
  const q = $("#producto-modal-search").value.trim().toLowerCase();
  const productos = state.productos
    .filter((p) => [p.codigo, p.nombre, p.marca, p.categoria].join(" ").toLowerCase().includes(q))
    .slice(0, 80);
  table($("#producto-modal-table"), [
    { key: "codigo", label: "Codigo" },
    { key: "nombre", label: "Producto" },
    { key: "marca", label: "Marca" },
    { key: "precio_venta", label: "Precio", format: money },
    { key: "stock", label: "Stock" },
  ], productos, (r) => `<button type="button" data-select-product="${r.id}">Elegir</button>`);
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

async function loadOptions() {
  state.options = await api("/api/options");
  state.productos = state.options.productos || [];
  state.categorias = state.options.categorias || [];

  const categoriasProducto = [
    `<option value="">Seleccione categoría</option>`,
    ...state.categorias.map((c) => `<option value="${c.id}">${escapeHtml(c.nombre)} (${Number(c.ganancia || 0)}%)</option>`)
  ].join("");

  const productoForm = $("#producto-form");
  if (productoForm) productoForm.elements.categoria_id.innerHTML = categoriasProducto;

  const recalculoForm = $("#recalcular-categoria-form");
  if (recalculoForm) {
    recalculoForm.elements.categoria_id.innerHTML = [
      `<option value="">Seleccione categoría</option>`,
      ...state.categorias.map((c) => `<option value="${c.id}">${escapeHtml(c.nombre)}</option>`)
    ].join("");
  }

  const preciosForm = $("#precios-form");
  if (preciosForm) {
    preciosForm.elements.categoria_id.innerHTML = [
      `<option value="">Seleccione categoría</option>`,
      ...state.categorias.map((c) => `<option value="${c.id}">${escapeHtml(c.nombre)}</option>`)
    ].join("");
  }

  const filtroCategoria = $("#filtro-categoria-productos");
  if (filtroCategoria) {
    const valorActual = filtroCategoria.value;
    filtroCategoria.innerHTML = [
      `<option value="">Todas las categorías</option>`,
      ...state.categorias.map((c) => `<option value="${c.id}">${escapeHtml(c.nombre)}</option>`)
    ].join("");
    filtroCategoria.value = valorActual;
  }

  $("#venta-form").elements.cliente_id.innerHTML = [
    `<option value="">Consumidor final</option>`,
    ...(state.options.clientes || []).map((c) => `<option value="${c.id}">${escapeHtml(c.nombre)} (${money(c.saldo)})</option>`)
  ].join("");

  $("#venta-producto").innerHTML = state.productos
    .map((p) => `<option value="${p.id}">${escapeHtml(p.codigo)} - ${escapeHtml(p.nombre)} - ${money(p.precio_venta)}</option>`)
    .join("");

  if (state.current === "ventas" && state.productos.length && !currentProduct()) {
    setVentaProduct(state.productos[0]);
  }
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

function calcularVentaProducto() {
  const form = $("#producto-form");
  if (!form) return;

  const categoria = state.categorias.find(
    (c) => String(c.id) === String(form.elements.categoria_id.value)
  );
  const compra = Number(form.elements.precio_compra.value || 0);
  const ganancia = Number(categoria?.ganancia || 0);
  const venta = Math.round((compra * (1 + ganancia / 100) + Number.EPSILON) * 100) / 100;

  $("#producto-ganancia").value = ganancia;
  form.elements.precio_venta.value = venta.toFixed(2);
  $("#preview-compra").textContent = money(compra);
  $("#preview-ganancia").textContent = `${ganancia}%`;
  $("#preview-venta").textContent = money(venta);
}

function resetProductoForm() {
  const form = $("#producto-form");
  form.reset();
  form.elements.id.value = "";
  form.elements.precio_compra.value = "0";
  form.elements.precio_venta.value = "0.00";
  form.elements.stock.value = "0";
  form.elements.stock_minimo.value = "0";
  $("#producto-form-title").textContent = "Nuevo producto";
  calcularVentaProducto();
}

function editarProducto(producto) {
  if (!producto) return;
  const form = $("#producto-form");

  Object.entries(producto).forEach(([key, value]) => {
    if (form.elements[key]) form.elements[key].value = value ?? "";
  });

  $("#producto-form-title").textContent = `Editar producto: ${producto.nombre}`;
  calcularVentaProducto();
  form.scrollIntoView({ behavior: "smooth", block: "start" });
  form.elements.codigo.focus();
}

function renderCategorias() {
  table($("#tabla-categorias"), [
    { key: "nombre", label: "Categoría" },
    { key: "ganancia", label: "Ganancia", format: (v) => `${Number(v || 0)}%` },
    { key: "productos", label: "Productos" },
  ], state.categorias, (r) => `
    <button type="button" data-edit-categoria="${r.id}">Editar</button>
    <button type="button" class="danger" data-del-categoria="${r.id}">Borrar</button>
  `);
}

function renderProductosLocal() {
  const categoriaId = $("#filtro-categoria-productos")?.value || "";
  const busqueda = ($("#buscar-productos-local")?.value || "").trim().toLowerCase();

  const data = state.productos.filter((p) => {
    const coincideCategoria = !categoriaId || String(p.categoria_id) === String(categoriaId);
    const texto = [p.codigo, p.nombre, p.marca, p.categoria].join(" ").toLowerCase();
    return coincideCategoria && (!busqueda || texto.includes(busqueda));
  });

  state.productosFiltrados = data;
  $("#productos-contador").textContent = `${data.length} producto${data.length === 1 ? "" : "s"}`;

  table($("#tabla-productos"), [
    { key: "codigo", label: "Código" },
    { key: "nombre", label: "Producto" },
    { key: "categoria", label: "Categoría" },
    { key: "marca", label: "Marca" },
    { key: "precio_compra", label: "Compra", format: money },
    { key: "ganancia_categoria", label: "Ganancia", format: (v) => `${Number(v || 0)}%` },
    { key: "precio_venta", label: "Venta", format: money },
    { key: "stock", label: "Stock" },
    { key: "stock_minimo", label: "Mínimo" },
  ], data, (r) => `
    <button type="button" data-edit-producto="${r.id}">Editar</button>
    <button type="button" class="danger" data-del-producto="${r.id}">Borrar</button>
  `);
}

async function loadProductos() {
  await loadOptions();
  state.productos = await api("/api/productos");
  state.options.productos = state.productos;
  state.categorias = await api("/api/categorias");
  state.options.categorias = state.categorias;

  await loadOptions();
  renderCategorias();
  renderProductosLocal();
  calcularVentaProducto();
}

function resetClienteForm() {
  const form = $("#cliente-form");
  form.reset();
  form.elements.id.value = "";
  form.elements.limite_credito.value = "0";
  $("#cliente-form-title").textContent = "Nuevo cliente";
}

function editarCliente(cliente) {
  if (!cliente) return;

  const form = $("#cliente-form");
  Object.entries(cliente).forEach(([key, value]) => {
    if (form.elements[key]) form.elements[key].value = value ?? "";
  });

  $("#cliente-form-title").textContent = `Editar cliente: ${cliente.nombre}`;
  form.scrollIntoView({ behavior: "smooth", block: "start" });
  form.elements.nombre.focus();
}

function renderClientesLocal() {
  const q = ($("#buscar-clientes-local")?.value || "").trim().toLowerCase();

  const data = state.clientes.filter((cliente) => {
    const texto = [
      cliente.nombre,
      cliente.telefono,
      cliente.whatsapp,
      cliente.cuit,
      cliente.localidad,
      cliente.direccion,
      cliente.email,
    ].join(" ").toLowerCase();

    return !q || texto.includes(q);
  });

  state.clientesFiltrados = data;
  $("#clientes-contador").textContent = `${data.length} cliente${data.length === 1 ? "" : "s"}`;

  table($("#tabla-clientes"), [
    { key: "nombre", label: "Cliente" },
    { key: "telefono", label: "Teléfono" },
    { key: "whatsapp", label: "WhatsApp" },
    { key: "localidad", label: "Localidad" },
    { key: "cuit", label: "CUIT / DNI" },
    { key: "limite_credito", label: "Límite", format: money },
    { key: "saldo", label: "Saldo", format: money },
    { key: "credito_disponible", label: "Disponible", format: money },
  ], data, (r) => `
    <button type="button" data-cuenta="${r.id}">Cuenta</button>
    <button type="button" data-edit-cliente="${r.id}">Editar</button>
    <button type="button" class="danger" data-del-cliente="${r.id}">Baja</button>
  `);

  const saldoTotal = state.clientes.reduce((sum, c) => sum + Number(c.saldo || 0), 0);
  const conDeuda = state.clientes.filter((c) => Number(c.saldo || 0) > 0.009).length;
  const creditoDisponible = state.clientes.reduce((sum, c) => sum + Number(c.credito_disponible || 0), 0);

  $("#clientes-total").textContent = state.clientes.length;
  $("#clientes-saldo-total").textContent = money(saldoTotal);
  $("#clientes-con-deuda").textContent = conDeuda;
  $("#clientes-credito-disponible").textContent = money(creditoDisponible);
}

async function loadClientes() {
  await loadOptions();
  state.clientes = await api("/api/clientes");
  renderClientesLocal();
}

async function loadCuenta(clienteId, scroll = true, filtros = {}) {
  const params = new URLSearchParams();
  if (filtros.desde) params.set("desde", filtros.desde);
  if (filtros.hasta) params.set("hasta", filtros.hasta);

  const url = `/api/clientes/${clienteId}/cuenta${params.toString() ? "?" + params.toString() : ""}`;
  const data = await api(url);

  state.cuenta = data;

  $("#cuenta-panel").hidden = false;
  $("#cuenta-title").textContent = `Cuenta corriente - ${data.cliente.nombre}`;
  $("#cuenta-sub").textContent = [
    data.cliente.telefono || "",
    data.cliente.cuit ? `CUIT/DNI: ${data.cliente.cuit}` : "",
    data.cliente.localidad || "",
  ].filter(Boolean).join(" · ");

  $("#cuenta-saldo").textContent = money(data.cliente.saldo);
  $("#cuenta-debe").textContent = money(data.resumen.debe);
  $("#cuenta-haber").textContent = money(data.resumen.haber);
  $("#cuenta-limite").textContent = money(data.cliente.limite_credito);
  $("#cuenta-disponible").textContent = money(data.credito_disponible);
  $("#cuenta-movs").textContent = data.resumen.movimientos || 0;

  $("#pago-form").elements.cliente_id.value = data.cliente.id;
  $("#ajuste-cuenta-form").elements.cliente_id.value = data.cliente.id;

  const saldo = Number(data.cliente.saldo || 0);
  const limite = Number(data.cliente.limite_credito || 0);
  const alerta = $("#cuenta-alerta");

  if (saldo <= 0) {
    alerta.className = "cuenta-alerta cuenta-alerta-ok";
    alerta.textContent = saldo < 0
      ? `El cliente tiene saldo a favor de ${money(Math.abs(saldo))}.`
      : "La cuenta se encuentra al día.";
  } else if (limite > 0 && saldo >= limite) {
    alerta.className = "cuenta-alerta cuenta-alerta-bad";
    alerta.textContent = `Límite alcanzado: saldo ${money(saldo)} sobre ${money(limite)}.`;
  } else {
    alerta.className = "cuenta-alerta cuenta-alerta-warn";
    alerta.textContent = `Saldo pendiente: ${money(saldo)}.`;
  }

  table($("#tabla-cuenta"), [
    { key: "fecha", label: "Fecha" },
    { key: "comprobante", label: "Comprobante" },
    { key: "concepto", label: "Concepto" },
    { key: "debe", label: "Debe", format: money },
    { key: "haber", label: "Haber", format: money },
    { key: "saldo", label: "Saldo", format: money },
    { key: "observaciones", label: "Observaciones" },
  ], data.movimientos || []);

  table($("#tabla-cliente-ventas"), [
    { key: "id", label: "Venta" },
    { key: "fecha", label: "Fecha" },
    { key: "tipo", label: "Medio" },
    { key: "total", label: "Total", format: money },
    { key: "usuario", label: "Usuario" },
  ], data.ventas || [], (r) => `<button type="button" data-print-ticket="${r.id}">Ticket</button>`);

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
  const ticket = $("#ticket");

  ticket.innerHTML = `
    <thead>
      <tr>
        <th>Producto</th>
        <th>Cantidad</th>
        <th>Precio</th>
        <th>Subtotal</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      ${state.ticket.map((item, index) => `
        <tr data-ticket-index="${index}">
          <td><strong>${escapeHtml(item.nombre)}</strong></td>
          <td>
            <input
              class="ticket-qty"
              data-ticket-qty="${index}"
              type="number"
              min="1"
              step="1"
              value="${Number(item.cantidad || 1)}"
              title="Cambiar cantidad"
            >
          </td>
          <td>${money(item.precio)}</td>
          <td><strong>${money(item.subtotal)}</strong></td>
          <td>
            <button
              type="button"
              class="danger ticket-remove"
              data-remove-index="${index}"
              title="Quitar producto"
            >Quitar</button>
          </td>
        </tr>
      `).join("") || `<tr><td colspan="5">Todavía no agregó productos al ticket.</td></tr>`}
    </tbody>
  `;

  const total = ticketTotal();
  const items = state.ticket.reduce((sum, item) => sum + Number(item.cantidad || 0), 0);

  $("#ticket-total").textContent = `TOTAL: ${money(total)}`;
  $("#ticket-total-inline").textContent = money(total);
  $("#venta-total-top").textContent = money(total);
  $("#ticket-items").textContent = `${items} unidad${items === 1 ? "" : "es"}`;

  const resumen = $("#ticket-productos-resumen");
  if (resumen) resumen.textContent = `${items} unidad${items === 1 ? "" : "es"} en ${state.ticket.length} producto${state.ticket.length === 1 ? "" : "s"}`;
}

async function loadVentas() {
  await loadOptions();
  if (state.productos.length) setVentaProduct(currentProduct() || state.productos[0]);
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

const CAJA_MEDIOS = [
  ["efectivo", "Efectivo"],
  ["transferencia", "Transferencia"],
  ["debito", "Débito"],
  ["credito", "Crédito"],
  ["posnet", "Posnet"],
  ["cuenta_corriente", "Cuenta corriente"],
];

const DENOMINACIONES = [20000, 10000, 5000, 2000, 1000, 500, 200, 100, 50, 20, 10];

function diferenciaClase(valor) {
  const n = Number(valor || 0);
  if (Math.abs(n) < 0.01) return "diff-ok";
  return n < 0 ? "diff-bad" : "diff-sobra";
}

function actualizarArqueo() {
  let totalSistema = 0;
  let totalContado = 0;

  CAJA_MEDIOS.forEach(([medio]) => {
    const sistema = Number($(`[data-sistema="${medio}"]`)?.dataset.valor || 0);
    const input = $(`[name="${medio}_contado"]`);
    const contado = Number(input?.value || 0);
    const diferencia = contado - sistema;

    totalSistema += sistema;
    totalContado += contado;

    const celda = $(`[data-diferencia="${medio}"]`);
    if (celda) {
      celda.textContent = money(diferencia);
      celda.className = diferenciaClase(diferencia);
    }
  });

  const diferenciaTotal = totalContado - totalSistema;
  $("#arqueo-total-sistema").textContent = money(totalSistema);
  $("#arqueo-total-contado").textContent = money(totalContado);
  $("#arqueo-total-diferencia").textContent = money(diferenciaTotal);
  $("#arqueo-total-diferencia").className = diferenciaClase(diferenciaTotal);

  const resultado = $("#arqueo-resultado");
  if (Math.abs(diferenciaTotal) < 0.01) {
    resultado.className = "arqueo-resultado correcto";
    resultado.textContent = "Caja correcta: no hay diferencias.";
  } else if (diferenciaTotal < 0) {
    resultado.className = "arqueo-resultado faltante";
    resultado.textContent = `Faltante de ${money(Math.abs(diferenciaTotal))}.`;
  } else {
    resultado.className = "arqueo-resultado sobrante";
    resultado.textContent = `Sobrante de ${money(diferenciaTotal)}.`;
  }
}

function renderBilletes() {
  $("#billetes-grid").innerHTML = DENOMINACIONES.map((denominacion) => `
    <label>
      <span>${money(denominacion)}</span>
      <input type="number" min="0" step="1" value="0" data-billete="${denominacion}">
      <strong data-billete-subtotal="${denominacion}">$0.00</strong>
    </label>
  `).join("");
  $("#billetes-total").textContent = money(0);
}

function actualizarBilletes() {
  let total = 0;

  $$("[data-billete]").forEach((input) => {
    const denominacion = Number(input.dataset.billete);
    const cantidad = Number(input.value || 0);
    const subtotal = denominacion * cantidad;
    total += subtotal;
    $(`[data-billete-subtotal="${denominacion}"]`).textContent = money(subtotal);
  });

  $("#billetes-total").textContent = money(total);
  const efectivo = $('[name="efectivo_contado"]');
  if (efectivo) {
    efectivo.value = total.toFixed(2);
    actualizarArqueo();
  }
}

function renderArqueo(sistema = {}) {
  $("#arqueo-grid").innerHTML = CAJA_MEDIOS.map(([medio, etiqueta]) => {
    const valor = Number(sistema[medio] || 0);
    return `
      <tr>
        <td><strong>${etiqueta}</strong></td>
        <td data-sistema="${medio}" data-valor="${valor}">${money(valor)}</td>
        <td>
          <input
            name="${medio}_contado"
            type="number"
            min="0"
            step="0.01"
            value="${valor.toFixed(2)}"
            required
          >
        </td>
        <td data-diferencia="${medio}" class="diff-ok">${money(0)}</td>
      </tr>
    `;
  }).join("");

  actualizarArqueo();
}

async function loadCaja() {
  const actual = await api("/api/caja/actual");
  state.cajaActual = actual;

  const caja = actual.caja || {};
  const sistema = actual.sistema || {};
  const abierta = Boolean(caja.id);

  $("#caja-estado-badge").textContent = abierta ? "ABIERTA" : "CERRADA";
  $("#caja-estado-badge").className = `caja-estado-badge ${abierta ? "abierta" : "cerrada"}`;
  $("#caja-apertura").textContent = money(caja.apertura);
  $("#caja-entradas").textContent = money(
    Number(caja.efectivo || 0) +
    Number(caja.transferencia || 0) +
    Number(caja.debito || 0) +
    Number(caja.credito || 0) +
    Number(caja.posnet || 0) +
    Number(caja.cuenta_corriente || 0) +
    Number(caja.ingresos || 0) -
    Number(caja.gastos || 0)
  );
  $("#caja-total").textContent = money(Object.values(sistema).reduce((a, b) => a + Number(b || 0), 0));

  $("#abrir-caja-form").hidden = abierta;
  $("#mov-caja-form").hidden = !abierta;
  $("#cerrar-caja-form").hidden = !abierta;

  const adminAlerta = $("#caja-admin-alerta");
  if (adminAlerta) {
    adminAlerta.hidden = !(abierta && state.user?.rol === "ADMIN");
  }

  if (abierta) {
    renderArqueo(sistema);
    renderBilletes();
  }

  const cajas = await api("/api/caja");
  const ultimaCerrada = cajas.find((c) => c.estado === "CERRADA");
  $("#caja-diferencia").textContent = money(ultimaCerrada?.diferencia || 0);
  $("#caja-diferencia").className = diferenciaClase(ultimaCerrada?.diferencia || 0);

  table($("#tabla-caja"), [
    { key: "id", label: "N.º" },
    { key: "fecha", label: "Fecha" },
    { key: "estado", label: "Estado" },
    { key: "usuario_apertura", label: "Abrió" },
    { key: "usuario_cierre", label: "Cerró" },
    { key: "apertura", label: "Apertura", format: money },
    { key: "total_sistema", label: "Sistema", format: money },
    { key: "total_contado", label: "Contado", format: money },
    { key: "diferencia", label: "Diferencia", format: (v) => `<span class="${diferenciaClase(v)}">${money(v)}</span>` },
    { key: "corregido", label: "Corregida", format: (v) => Number(v) ? "Sí" : "No" },
  ], cajas, (r) => `<button type="button" data-ver-caja="${r.id}">Ver detalle</button>`);
}

function cajaDetalleFilas(data) {
  const arqueo = data.arqueo || {};
  return CAJA_MEDIOS.map(([medio, etiqueta]) => {
    const sistema = Number(arqueo[`${medio}_sistema`] ?? data.sistema?.[medio] ?? 0);
    const contado = Number(arqueo[`${medio}_contado`] ?? 0);
    const diferencia = contado - sistema;
    return { medio: etiqueta, sistema, contado, diferencia };
  });
}

async function verDetalleCaja(cajaId) {
  const data = await api(`/api/caja/${cajaId}`);
  state.cajaDetalle = data;

  $("#caja-detalle-panel").hidden = false;
  $("#caja-detalle-title").textContent = `Detalle de caja N.º ${data.caja.id}`;
  $("#caja-detalle-sub").textContent =
    `${data.caja.fecha || ""} · Abrió: ${data.caja.usuario_apertura || "-"} · Cerró: ${data.caja.usuario_cierre || "-"}`;

  const filas = cajaDetalleFilas(data);
  const totalSistema = filas.reduce((sum, f) => sum + f.sistema, 0);
  const totalContado = filas.reduce((sum, f) => sum + f.contado, 0);
  const diferencia = totalContado - totalSistema;

  $("#caja-detalle-resumen").innerHTML = `
    <article><span>Sistema</span><strong>${money(totalSistema)}</strong></article>
    <article><span>Contado</span><strong>${money(totalContado)}</strong></article>
    <article><span>Diferencia</span><strong class="${diferenciaClase(diferencia)}">${money(diferencia)}</strong></article>
    <article><span>Estado</span><strong>${data.caja.estado}</strong></article>
  `;

  table($("#tabla-caja-detalle"), [
    { key: "medio", label: "Medio" },
    { key: "sistema", label: "Sistema", format: money },
    { key: "contado", label: "Contado", format: money },
    { key: "diferencia", label: "Diferencia", format: (v) => `<span class="${diferenciaClase(v)}">${money(v)}</span>` },
  ], filas);

  table($("#tabla-caja-movimientos"), [
    { key: "fecha", label: "Fecha" },
    { key: "tipo", label: "Tipo" },
    { key: "descripcion", label: "Descripción" },
    { key: "importe", label: "Importe", format: money },
  ], data.movimientos || []);

  const form = $("#corregir-caja-form");
  form.hidden = state.user?.rol !== "ADMIN" || data.caja.estado !== "CERRADA";
  form.elements.caja_id.value = data.caja.id;

  if (!form.hidden) {
    $("#correccion-grid").innerHTML = filas.map((fila, index) => {
      const medio = CAJA_MEDIOS[index][0];
      return `
        <label>${fila.medio}
          <input name="${medio}_contado" type="number" min="0" step="0.01" value="${fila.contado.toFixed(2)}" required>
        </label>
      `;
    }).join("");
    form.elements.motivo.value = "";
  }

  $("#caja-detalle-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

function imprimirCierreCaja() {
  const data = state.cajaDetalle;
  if (!data) return;

  const filas = cajaDetalleFilas(data);
  const cuerpo = filas.map((f) => `
    <tr>
      <td>${escapeHtml(f.medio)}</td>
      <td>${money(f.sistema)}</td>
      <td>${money(f.contado)}</td>
      <td>${money(f.diferencia)}</td>
    </tr>
  `).join("");

  const totalSistema = filas.reduce((s, f) => s + f.sistema, 0);
  const totalContado = filas.reduce((s, f) => s + f.contado, 0);

  printWindow(
    `Cierre de caja N.º ${data.caja.id}`,
    `
      <p>
        Fecha: ${escapeHtml(data.caja.fecha || "")}<br>
        Usuario apertura: ${escapeHtml(data.caja.usuario_apertura || "-")}<br>
        Usuario cierre: ${escapeHtml(data.caja.usuario_cierre || "-")}
      </p>
      <table>
        <thead><tr><th>Medio</th><th>Sistema</th><th>Contado</th><th>Diferencia</th></tr></thead>
        <tbody>${cuerpo}</tbody>
      </table>
      <div class="total">Sistema ${money(totalSistema)}</div>
      <div class="total">Contado ${money(totalContado)}</div>
      <div class="total">Diferencia ${money(totalContado - totalSistema)}</div>
      <p>Observaciones: ${escapeHtml(data.arqueo?.observaciones || "-")}</p>
      ${data.arqueo?.corregido ? `<p><strong>Corregida por ${escapeHtml(data.arqueo.usuario_correccion || "")}</strong><br>${escapeHtml(data.arqueo.motivo_correccion || "")}</p>` : ""}
    `
  );
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
  if (ev.target.dataset.editProducto) editarProducto(state.productos.find((p) => String(p.id) === ev.target.dataset.editProducto));
  if (ev.target.dataset.delProducto && confirm("Borrar producto?")) {
    await api(`/api/productos/${ev.target.dataset.delProducto}`, { method: "DELETE" });
    await loadProductos();
  }
  if (ev.target.dataset.editCategoria) {
    const categoria = state.categorias.find((c) => String(c.id) === String(ev.target.dataset.editCategoria));
    if (categoria) {
      const form = $("#categoria-form");
      form.elements.id.value = categoria.id;
      form.elements.nombre.value = categoria.nombre;
      form.elements.ganancia.value = categoria.ganancia;
      form.elements.nombre.focus();
    }
  }
  if (ev.target.dataset.delCategoria) {
    const categoria = state.categorias.find((c) => String(c.id) === String(ev.target.dataset.delCategoria));
    if (categoria && confirm(`¿Borrar la categoría "${categoria.nombre}"?`)) {
      try {
        await api(`/api/categorias/${categoria.id}`, { method: "DELETE" });
        await loadProductos();
      } catch (error) {
        alert(error.message);
      }
    }
  }
  if (ev.target.dataset.editCliente) editarCliente(state.clientes.find((c) => String(c.id) === String(ev.target.dataset.editCliente)));
  if (ev.target.dataset.cuenta) await loadCuenta(ev.target.dataset.cuenta);
  if (ev.target.dataset.delCliente) {
    const cliente = state.clientes.find((c) => String(c.id) === String(ev.target.dataset.delCliente));
    if (cliente && confirm(`¿Dar de baja al cliente "${cliente.nombre}"?`)) {
      try {
        await api(`/api/clientes/${cliente.id}`, { method: "DELETE" });
        await loadClientes();
      } catch (error) {
        alert(error.message);
      }
    }
  }
  if (ev.target.dataset.removeIndex !== undefined) {
    const index = Number(ev.target.dataset.removeIndex);
    state.ticket.splice(index, 1);
    renderTicket();
    $("#venta-cantidad").focus();
  }
  if (ev.target.dataset.selectProduct) {
    const product = state.productos.find((p) => String(p.id) === String(ev.target.dataset.selectProduct));
    setVentaProduct(product);
    closeProductSearch();
  }
  if (ev.target.dataset.printTicket) {
    const data = await api(`/api/ventas/${ev.target.dataset.printTicket}`);
    printVenta("Ticket", data, false);
  }
  if (ev.target.dataset.verCaja) await verDetalleCaja(ev.target.dataset.verCaja);
  if (ev.target.dataset.backup) window.location.href = `/api/backups/${encodeURIComponent(ev.target.dataset.backup)}`;
});

$("#search").addEventListener("input", refresh);
$("#buscar-producto").addEventListener("click", openProductSearch);
$("#cerrar-producto-modal").addEventListener("click", closeProductSearch);
$("#producto-modal-search").addEventListener("input", renderProductSearch);
$("#producto-modal").addEventListener("click", (ev) => {
  if (ev.target.id === "producto-modal") closeProductSearch();
});
document.addEventListener("keydown", (ev) => {
  if (state.current !== "ventas") return;

  const modalAbierto = !$("#producto-modal").hidden;

  if (ev.key === "F3") {
    ev.preventDefault();
    openProductSearch();
    return;
  }

  if (ev.key === "Escape" && modalAbierto) {
    ev.preventDefault();
    closeProductSearch();
    return;
  }

  if (ev.key === "Enter" && modalAbierto) {
    ev.preventDefault();
    const primerBoton = $("#producto-modal-table [data-select-product]");
    if (primerBoton) primerBoton.click();
    return;
  }

  if (ev.key === "F4" && !modalAbierto) {
    ev.preventDefault();
    $("#venta-form").requestSubmit();
    return;
  }

  if (ev.key === "F8" && !modalAbierto) {
    ev.preventDefault();

    if (!state.ticket.length) return;

    if (!confirm("¿Vaciar todos los productos del ticket?")) return;

    state.ticket = [];
    renderTicket();
    $("#venta-cantidad").value = 1;
    openProductSearch();
    return;
  }

  if (ev.key === "Delete" && !modalAbierto) {
    const seleccionada = $("#ticket tbody tr.ticket-selected");
    if (seleccionada) {
      ev.preventDefault();
      const index = Number(seleccionada.dataset.ticketIndex);
      state.ticket.splice(index, 1);
      renderTicket();
    }
  }
});

$("#producto-form").onsubmit = async (ev) => {
  ev.preventDefault();

  try {
    const data = Object.fromEntries(new FormData(ev.target));
    const result = await api("/api/productos", {
      method: "POST",
      body: JSON.stringify(data),
    });

    alert(`Producto guardado. Precio de venta: ${money(result.precio_venta)}`);
    resetProductoForm();
    await loadProductos();
  } catch (error) {
    alert(error.message);
  }
};

$("#producto-form").elements.precio_compra.addEventListener("input", calcularVentaProducto);
$("#producto-form").elements.categoria_id.addEventListener("change", calcularVentaProducto);
$("#nuevo-producto").onclick = () => {
  resetProductoForm();
  $("#producto-form").scrollIntoView({ behavior: "smooth", block: "start" });
  $("#producto-form").elements.codigo.focus();
};
$("#cancelar-producto").onclick = resetProductoForm;

$("#filtro-categoria-productos").addEventListener("change", renderProductosLocal);
$("#buscar-productos-local").addEventListener("input", renderProductosLocal);

$("#categoria-form").onsubmit = async (ev) => {
  ev.preventDefault();

  try {
    await api("/api/categorias", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(new FormData(ev.target))),
    });
    ev.target.reset();
    ev.target.elements.id.value = "";
    ev.target.elements.ganancia.value = "30";
    await loadProductos();
  } catch (error) {
    alert(error.message);
  }
};

$("#cancelar-categoria").onclick = () => {
  const form = $("#categoria-form");
  form.reset();
  form.elements.id.value = "";
  form.elements.ganancia.value = "30";
};

function cargarGananciaRecalculo() {
  const form = $("#recalcular-categoria-form");
  const categoria = state.categorias.find(
    (c) => String(c.id) === String(form.elements.categoria_id.value)
  );
  form.elements.ganancia.value = categoria ? Number(categoria.ganancia || 0) : "";
  $("#recalculo-status").textContent = "";
  $("#tabla-recalculo").innerHTML = "";
}

$("#recalcular-categoria-form").elements.categoria_id.addEventListener("change", cargarGananciaRecalculo);

async function recalcularCategoria(aplicar) {
  const form = $("#recalcular-categoria-form");
  const data = Object.fromEntries(new FormData(form));
  data.redondear = form.elements.redondear.checked ? 1 : 0;
  data.aplicar = aplicar ? 1 : 0;

  if (!data.categoria_id) return alert("Seleccione una categoría.");
  if (aplicar && !confirm("¿Aplicar el nuevo porcentaje a todos los productos de la categoría?")) return;

  try {
    const result = await api("/api/precios/categoria", {
      method: "POST",
      body: JSON.stringify(data),
    });

    $("#recalculo-status").textContent =
      `${result.aplicado ? "Actualizado" : "Vista previa"}: ${result.cantidad} producto(s) de ${result.categoria}, ganancia ${result.ganancia}%.`;

    table($("#tabla-recalculo"), [
      { key: "codigo", label: "Código" },
      { key: "nombre", label: "Producto" },
      { key: "precio_compra", label: "Compra", format: money },
      { key: "anterior", label: "Venta anterior", format: money },
      { key: "nuevo", label: "Venta nueva", format: money },
      { key: "diferencia", label: "Diferencia", format: money },
    ], result.cambios || []);

    if (aplicar) await loadProductos();
  } catch (error) {
    alert(error.message);
  }
}

$("#preview-recalculo").onclick = () => recalcularCategoria(false);
$("#recalcular-categoria-form").onsubmit = async (ev) => {
  ev.preventDefault();
  await recalcularCategoria(true);
};

$("#cliente-form").onsubmit = async (ev) => {
  ev.preventDefault();

  try {
    await api("/api/clientes", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(new FormData(ev.target))),
    });
    resetClienteForm();
    await loadClientes();
  } catch (error) {
    alert(error.message);
  }
};

$("#nuevo-cliente").onclick = () => {
  resetClienteForm();
  $("#cliente-form").scrollIntoView({ behavior: "smooth", block: "start" });
  $("#cliente-form").elements.nombre.focus();
};

$("#cancelar-cliente").onclick = resetClienteForm;
$("#buscar-clientes-local").addEventListener("input", renderClientesLocal);

$("#pago-form").onsubmit = async (ev) => {
  ev.preventDefault();
  const data = Object.fromEntries(new FormData(ev.target));

  try {
    await api(`/api/clientes/${data.cliente_id}/pago`, {
      method: "POST",
      body: JSON.stringify(data),
    });
    ev.target.reset();
    ev.target.elements.cliente_id.value = data.cliente_id;
    await loadClientes();
    await loadCuenta(data.cliente_id, false);
  } catch (error) {
    alert(error.message);
  }
};

$("#ajuste-cuenta-form").onsubmit = async (ev) => {
  ev.preventDefault();
  const data = Object.fromEntries(new FormData(ev.target));

  try {
    await api(`/api/clientes/${data.cliente_id}/ajuste`, {
      method: "POST",
      body: JSON.stringify(data),
    });
    ev.target.reset();
    ev.target.elements.cliente_id.value = data.cliente_id;
    await loadClientes();
    await loadCuenta(data.cliente_id, false);
  } catch (error) {
    alert(error.message);
  }
};

$("#filtrar-cuenta").onclick = async () => {
  if (!state.cuenta) return;
  await loadCuenta(state.cuenta.cliente.id, false, {
    desde: $("#cuenta-desde").value,
    hasta: $("#cuenta-hasta").value,
  });
};

$("#limpiar-filtro-cuenta").onclick = async () => {
  if (!state.cuenta) return;
  $("#cuenta-desde").value = "";
  $("#cuenta-hasta").value = "";
  await loadCuenta(state.cuenta.cliente.id, false);
};

$("#cerrar-cuenta-panel").onclick = () => {
  $("#cuenta-panel").hidden = true;
  state.cuenta = null;
};

$("#whatsapp-cliente").onclick = () => {
  if (!state.cuenta) return;

  const numero = String(state.cuenta.cliente.whatsapp || state.cuenta.cliente.telefono || "")
    .replace(/\D/g, "");

  if (!numero) return alert("El cliente no tiene WhatsApp o teléfono cargado.");

  const saldo = money(state.cuenta.cliente.saldo);
  const texto = encodeURIComponent(
    `Hola ${state.cuenta.cliente.nombre}. Su saldo actual en Bebidas San Martín es ${saldo}.`
  );

  window.open(`https://wa.me/${numero}?text=${texto}`, "_blank");
};

$("#print-cuenta").onclick = () => {
  const d = state.cuenta;
  if (!d) return;

  const movimientos = (d.movimientos || []).map((m) => `
    <tr>
      <td>${escapeHtml(m.fecha)}</td>
      <td>${escapeHtml(m.comprobante)}</td>
      <td>${escapeHtml(m.concepto)}</td>
      <td>${money(m.debe)}</td>
      <td>${money(m.haber)}</td>
      <td>${money(m.saldo)}</td>
    </tr>
  `).join("");

  printWindow(
    `Cuenta corriente - ${d.cliente.nombre}`,
    `
      <p>
        Cliente: ${escapeHtml(d.cliente.nombre)}<br>
        CUIT/DNI: ${escapeHtml(d.cliente.cuit || "-")}<br>
        Teléfono: ${escapeHtml(d.cliente.telefono || "-")}
      </p>
      <div class="total">Saldo ${money(d.cliente.saldo)}</div>
      <p>Límite: ${money(d.cliente.limite_credito)} · Disponible: ${money(d.credito_disponible)}</p>
      <table>
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Comp.</th>
            <th>Concepto</th>
            <th>Debe</th>
            <th>Haber</th>
            <th>Saldo</th>
          </tr>
        </thead>
        <tbody>${movimientos}</tbody>
      </table>
    `
  );
};

function agregarProductoAlTicket() {
  const p = currentProduct();
  if (!p) {
    alert("Seleccione un producto con F3.");
    openProductSearch();
    return;
  }

  const cantidad = Number($("#venta-cantidad").value || 1);
  if (!Number.isFinite(cantidad) || cantidad <= 0) {
    alert("Cantidad inválida.");
    $("#venta-cantidad").focus();
    return;
  }

  const yaCargado = state.ticket
    .filter((i) => String(i.producto_id) === String(p.id))
    .reduce((sum, item) => sum + Number(item.cantidad || 0), 0);

  if (yaCargado + cantidad > Number(p.stock || 0)) {
    alert(`Stock insuficiente. Disponible: ${p.stock}`);
    $("#venta-cantidad").focus();
    return;
  }

  const found = state.ticket.find((i) => String(i.producto_id) === String(p.id));

  if (found) {
    found.cantidad = Number(found.cantidad) + cantidad;
    found.subtotal = found.cantidad * found.precio;
  } else {
    state.ticket.push({
      producto_id: p.id,
      nombre: p.nombre,
      cantidad,
      precio: Number(p.precio_venta || 0),
      subtotal: cantidad * Number(p.precio_venta || 0),
    });
  }

  $("#venta-cantidad").value = 1;
  renderTicket();

  // Flujo rápido: después de agregar vuelve a abrir el F3 para buscar el próximo.
  openProductSearch();
}

$("#add-item").onclick = agregarProductoAlTicket;

$("#venta-cantidad").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") {
    ev.preventDefault();
    agregarProductoAlTicket();
  }
});

$("#vaciar-ticket").onclick = () => {
  if (!state.ticket.length) return;
  if (!confirm("¿Vaciar todos los productos del ticket?")) return;
  state.ticket = [];
  renderTicket();
  $("#venta-cantidad").value = 1;
  openProductSearch();
};

$("#ticket").addEventListener("click", (ev) => {
  const fila = ev.target.closest("tr[data-ticket-index]");
  if (!fila) return;
  $$("#ticket tbody tr").forEach((tr) => tr.classList.remove("ticket-selected"));
  fila.classList.add("ticket-selected");
});

$("#ticket").addEventListener("change", (ev) => {
  if (!ev.target.matches("[data-ticket-qty]")) return;

  const index = Number(ev.target.dataset.ticketQty);
  const item = state.ticket[index];
  const cantidad = Number(ev.target.value);

  if (!item || !Number.isFinite(cantidad) || cantidad <= 0) {
    alert("Cantidad inválida.");
    renderTicket();
    return;
  }

  const producto = state.productos.find((p) => String(p.id) === String(item.producto_id));
  if (producto && cantidad > Number(producto.stock || 0)) {
    alert(`Stock insuficiente. Disponible: ${producto.stock}`);
    renderTicket();
    return;
  }

  item.cantidad = cantidad;
  item.subtotal = cantidad * item.precio;
  renderTicket();
});

$("#ticket").addEventListener("dblclick", (ev) => {
  const fila = ev.target.closest("tr[data-ticket-index]");
  if (!fila || ev.target.matches("button, input")) return;

  const index = Number(fila.dataset.ticketIndex);
  const item = state.ticket[index];
  if (!item) return;

  const valor = prompt(`Nueva cantidad para ${item.nombre}:`, item.cantidad);
  if (valor === null) return;

  const cantidad = Number(valor);
  const producto = state.productos.find((p) => String(p.id) === String(item.producto_id));

  if (!Number.isFinite(cantidad) || cantidad <= 0) {
    alert("Cantidad inválida.");
    return;
  }

  if (producto && cantidad > Number(producto.stock || 0)) {
    alert(`Stock insuficiente. Disponible: ${producto.stock}`);
    return;
  }

  item.cantidad = cantidad;
  item.subtotal = cantidad * item.precio;
  renderTicket();
});

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
  $("#venta-cantidad").value = 1;
  openProductSearch();
};

$("#abrir-caja-form").onsubmit = async (ev) => {
  ev.preventDefault();

  try {
    await api("/api/caja/abrir", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(new FormData(ev.target))),
    });

    ev.target.reset();
    ev.target.elements.apertura.value = "0";
    await loadCaja();
  } catch (error) {
    if (String(error.message).includes("Ya hay una caja abierta")) {
      alert(
        state.user?.rol === "ADMIN"
          ? "Ya existe una caja abierta. Puede cerrarla normalmente o usar Forzar cierre si quedó trabada."
          : "Ya existe una caja abierta. Ingrese a Caja para continuar trabajando o cerrarla."
      );
      await loadCaja();
      return;
    }

    alert(error.message);
  }
};

$("#mov-caja-form").onsubmit = async (ev) => {
  ev.preventDefault();
  try {
    await api("/api/caja/movimiento", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(new FormData(ev.target))),
    });
    ev.target.reset();
    await loadCaja();
  } catch (error) {
    alert(error.message);
  }
};

$("#cerrar-caja-form").addEventListener("input", (ev) => {
  if (ev.target.matches("[name$='_contado']")) actualizarArqueo();
});

$("#billetes-grid").addEventListener("input", (ev) => {
  if (ev.target.matches("[data-billete]")) actualizarBilletes();
});

$("#cerrar-caja-form").onsubmit = async (ev) => {
  ev.preventDefault();

  if (!confirm("¿Confirma el cierre de caja con los importes contados?")) return;

  const data = Object.fromEntries(new FormData(ev.target));
  data.billetes = $$("[data-billete]").map((input) => ({
    denominacion: Number(input.dataset.billete),
    cantidad: Number(input.value || 0),
  }));

  try {
    const result = await api("/api/caja/cerrar", {
      method: "POST",
      body: JSON.stringify(data),
    });

    alert(
      Math.abs(Number(result.diferencia || 0)) < 0.01
        ? "Caja cerrada correctamente, sin diferencias."
        : `Caja cerrada con diferencia de ${money(result.diferencia)}.`
    );

    ev.target.reset();
    await loadCaja();
    await verDetalleCaja(result.caja_id);
  } catch (error) {
    alert(error.message);
  }
};

$("#forzar-cierre-form").onsubmit = async (ev) => {
  ev.preventDefault();

  if (state.user?.rol !== "ADMIN") {
    return alert("Solo el administrador puede forzar el cierre.");
  }

  const data = Object.fromEntries(new FormData(ev.target));

  if (!data.motivo?.trim()) {
    return alert("Ingrese el motivo del cierre forzado.");
  }

  if (!confirm(
    "¿Confirma el cierre forzado?\n\n" +
    "Se cerrará la caja usando los importes del sistema y la acción quedará registrada."
  )) return;

  try {
    const result = await api("/api/caja/forzar-cierre", {
      method: "POST",
      body: JSON.stringify(data),
    });

    alert(`Caja N.º ${result.caja_id} cerrada de forma administrativa.`);
    ev.target.reset();
    await loadCaja();
    await verDetalleCaja(result.caja_id);
  } catch (error) {
    alert(error.message);
  }
};

$("#corregir-caja-form").onsubmit = async (ev) => {
  ev.preventDefault();

  if (state.user?.rol !== "ADMIN") return alert("Solo el administrador puede corregir una caja.");
  if (!confirm("¿Guardar la corrección administrativa de esta caja?")) return;

  const data = Object.fromEntries(new FormData(ev.target));
  const cajaId = data.caja_id;
  delete data.caja_id;

  try {
    await api(`/api/caja/${cajaId}/corregir`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
    alert("Caja corregida correctamente. La modificación quedó auditada.");
    await loadCaja();
    await verDetalleCaja(cajaId);
  } catch (error) {
    alert(error.message);
  }
};

$("#cerrar-detalle-caja").onclick = () => {
  $("#caja-detalle-panel").hidden = true;
  state.cajaDetalle = null;
};

$("#imprimir-cierre").onclick = imprimirCierreCaja;

$("#reportes-form").onsubmit = loadReportes;
$("#print-report").onclick = () => {
  if (!state.lastReport) return alert("Actualice el reporte.");
  printWindow("Reporte comercial", `<div class="total">Total vendido ${money(state.lastReport.resumen.total)}</div><h2>Medios</h2>${$("#tabla-medios").outerHTML}<h2>Top productos</h2>${$("#tabla-top").outerHTML}`);
};

async function previewPrecios(aplicar) {
  const data = Object.fromEntries(new FormData($("#precios-form")));
  data.redondear = $("#precios-form").elements.redondear.checked ? 1 : 0;
  data.ganancia = data.porcentaje;
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

(async function init() {
  const me = await api("/api/me");
  state.user = me.user;
  await loadOptions();
  await refresh();
})();
