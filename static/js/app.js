/**
 * MedControl Pro - Sistema de Gestión Hospitalaria
 * app.js — Todas las operaciones leen/escriben en SQL Server a través de la API Flask.
 * No usa localStorage: cada acción hace fetch() a /api/... .
 */

const API = '/api';

// Caches en memoria (solo para poblar selects sin re-consultar constantemente)
let cachePacientes = [];
let cacheMedicos = [];
let cacheCitas = [];
let cacheEspecialidades = [];
let cacheCamasDisponibles = [];

// ==========================================
// HELPERS DE RED
// ==========================================
async function apiGet(path) {
    const res = await fetch(`${API}${path}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Error al consultar el servidor');
    return data;
}

async function apiSend(path, method, body) {
    const res = await fetch(`${API}${path}`, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Error al guardar en el servidor');
    return data;
}

function mostrarError(err) {
    console.error(err);
    Swal.fire('Error', err.message || 'Ocurrió un problema al conectar con el servidor', 'error');
}

// ==========================================
// NAVEGACIÓN DE MÓDULOS
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    const navLinks = document.querySelectorAll('#menu-items .nav-link');
    const modulos = document.querySelectorAll('.modulo-sec');
    const titleModulo = document.getElementById('title-modulo');

    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            navLinks.forEach(l => l.classList.remove('active'));
            modulos.forEach(m => m.classList.add('d-none'));

            link.classList.add('active');
            const secId = link.getAttribute('data-sec');
            const targetSec = document.getElementById(`sec-${secId}`);
            if (targetSec) targetSec.classList.remove('d-none');

            titleModulo.innerText = link.innerText.trim();

            if (secId === 'dashboard') {
                setTimeout(() => mapaDashboard && mapaDashboard.invalidateSize(), 150);
            }
        });
    });

    inicializarMapaDashboard();
    activarAutocompleteDireccion('p-direccion', 'p-direccion-list', 'p-lat', 'p-lng');
    activarAutocompleteCie10();
    cargarTodo();
});

async function cargarTodo() {
    try {
        await Promise.all([
            cargarEspecialidades(),
            renderPacientes(),
            renderMedicos(),
            renderCitas(),
            renderTriaje(),
            renderHistorial(),
            renderFacturacion(),
            renderFarmacia(),
            renderLaboratorio(),
            renderHospitalizacion(),
            renderNotificaciones()
        ]);
        await actualizarDashboard();
    } catch (err) {
        mostrarError(err);
    }
}

// ==========================================
// DASHBOARD
// ==========================================
async function actualizarDashboard() {
    try {
        const d = await apiGet('/dashboard');
        document.getElementById('dash-pacientes').innerText = d.pacientes ?? 0;
        document.getElementById('dash-citas').innerText = d.citas ?? 0;
        document.getElementById('dash-medicos').innerText = d.medicos ?? 0;
        document.getElementById('dash-ingresos').innerText = (d.ingresos ?? 0).toFixed(2);
        actualizarMarcadoresPacientes(cachePacientes);
    } catch (err) {
        mostrarError(err);
    }
}

// ==========================================
// AUTOCOMPLETADO CIE-10 (API pública NLM Clinical Tables, gratuita, sin API key)
// https://clinicaltables.nlm.nih.gov/apidoc/icd10cm/v3/doc.html
// ==========================================
function activarAutocompleteCie10() {
    const input = document.getElementById('h-cie10');
    const lista = document.getElementById('h-cie10-list');
    if (!input || !lista) return;

    let timeoutId = null;
    input.addEventListener('input', () => {
        clearTimeout(timeoutId);
        const termino = input.value.trim();
        if (termino.length < 2) { lista.classList.add('d-none'); return; }
        timeoutId = setTimeout(async () => {
            try {
                const url = `https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search?sf=code,name&terms=${encodeURIComponent(termino)}`;
                const res = await fetch(url);
                if (!res.ok) return;
                const data = await res.json();
                const resultados = data[3] || []; // formato: [total, codes, extra, [ [code, name], ... ] ]
                if (resultados.length === 0) { lista.classList.add('d-none'); return; }
                lista.innerHTML = resultados.map(r =>
                    `<div data-code="${r[0]}">${r[0]} — ${r[1]}</div>`
                ).join('');
                lista.classList.remove('d-none');
            } catch (e) {
                console.error('Error consultando CIE-10:', e);
            }
        }, 400);
    });

    lista.addEventListener('click', (e) => {
        const item = e.target.closest('div[data-code]');
        if (!item) return;
        input.value = item.getAttribute('data-code');
        lista.classList.add('d-none');
    });

    document.addEventListener('click', (e) => {
        if (!lista.contains(e.target) && e.target !== input) lista.classList.add('d-none');
    });
}

// ==========================================
// BÚSQUEDA REAL DE RENIEC (a través del backend Flask)
// ==========================================
async function buscarDniReniec() {
    const dni = document.getElementById('p-dni').value.trim();
    if (dni.length !== 8) return Swal.fire('Error', 'Ingrese un DNI válido de 8 dígitos', 'warning');

    Swal.fire({ title: 'Consultando RENIEC...', allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
        const data = await apiGet(`/reniec/${dni}`);
        document.getElementById('p-nombre').value = data.nombres || '';
        document.getElementById('p-apellido').value = data.apellidos || '';
        Swal.fire('Éxito', 'Datos obtenidos de RENIEC correctamente', 'success');
    } catch (err) {
        Swal.fire('Sin resultados', err.message, 'warning');
    }
}

async function buscarDniReniecMedico() {
    const dni = document.getElementById('m-dni').value.trim();
    if (dni.length !== 8) return Swal.fire('Error', 'Ingrese un DNI válido de 8 dígitos', 'warning');

    Swal.fire({ title: 'Consultando RENIEC...', allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
        const data = await apiGet(`/reniec/${dni}`);
        document.getElementById('m-nombre').value = data.nombres || '';
        document.getElementById('m-apellido').value = data.apellidos || '';
        Swal.fire('Éxito', 'Datos de médico obtenidos correctamente', 'success');
    } catch (err) {
        Swal.fire('Sin resultados', err.message, 'warning');
    }
}

// ==========================================
// SELECTS DINÁMICOS (poblados desde la BD real)
// ==========================================
async function cargarEspecialidades() {
    cacheEspecialidades = await apiGet('/especialidades');
    const select = document.getElementById('m-especialidad');
    select.innerHTML = '<option value="">Seleccione Especialidad</option>' +
        cacheEspecialidades.map(e => `<option value="${e.id}">${e.nombre}</option>`).join('');
}

function actualizarSelectsDependientes() {
    const pacienteOptions = cachePacientes.map(p => `<option value="${p.id}">${p.nombre} ${p.apellido} (${p.dni})</option>`).join('');
    ['c-paciente', 'f-paciente', 'lab-paciente', 'hosp-paciente'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<option value="">Seleccione Paciente</option>' + pacienteOptions;
    });

    const medicoOptions = cacheMedicos.map(m => `<option value="${m.id}">Dr(a). ${m.nombre} ${m.apellido} - ${m.especialidad || ''}</option>`).join('');
    ['c-medico', 'lab-medico', 'hosp-medico'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<option value="">Seleccione Médico</option>' + medicoOptions;
    });

    const citaOptions = cacheCitas.map(c => {
        return `<option value="${c.id}">Cita #${c.id} - ${c.paciente_nombre || ''} (${c.fecha})</option>`;
    }).join('');
    ['t-cita', 'h-cita'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<option value="">Seleccione Cita</option>' + citaOptions;
    });
}

async function cargarCamasDisponibles(seleccionarId = null) {
    cacheCamasDisponibles = await apiGet('/camas-disponibles');
    const select = document.getElementById('hosp-cama');
    select.innerHTML = '<option value="">Seleccione Cama Disponible</option>' +
        cacheCamasDisponibles.map(c => `<option value="${c.id}">Piso ${c.piso} - Hab. ${c.numero_habitacion} - ${c.numero_cama} (${c.tipo})</option>`).join('');
    if (seleccionarId) select.value = seleccionarId;
}

// ==========================================
// 1. CRUD: PACIENTES
// ==========================================
async function renderPacientes() {
    cachePacientes = await apiGet('/pacientes');
    const tbody = document.querySelector('#tabla-pacientes tbody');
    tbody.innerHTML = cachePacientes.map(p => `
        <tr>
            <td>${p.id}</td>
            <td><strong>${p.nombre} ${p.apellido}</strong></td>
            <td>${p.dni}</td>
            <td>${p.telefono || '-'}</td>
            <td>${p.email || '-'}</td>
            <td class="text-center">
                <button class="btn btn-sm btn-outline-warning me-1" onclick="abrirModalPaciente(${p.id})"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-outline-danger" onclick="eliminarPaciente(${p.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>
    `).join('');
    actualizarSelectsDependientes();
}

function abrirModalPaciente(id = null) {
    document.getElementById('form-paciente').reset();
    document.getElementById('p-id').value = id || '';
    document.getElementById('p-lat').value = '';
    document.getElementById('p-lng').value = '';
    if (id) {
        const p = cachePacientes.find(x => x.id === id);
        if (p) {
            document.getElementById('p-dni').value = p.dni;
            document.getElementById('p-nombre').value = p.nombre;
            document.getElementById('p-apellido').value = p.apellido;
            document.getElementById('p-fnac').value = p.fnac;
            document.getElementById('p-genero').value = p.genero || 'Masculino';
            document.getElementById('p-tel').value = p.telefono;
            document.getElementById('p-email').value = p.email;
            document.getElementById('p-direccion').value = p.direccion || '';
            document.getElementById('p-lat').value = p.latitud || '';
            document.getElementById('p-lng').value = p.longitud || '';
            document.getElementById('p-grupo').value = p.grupo_sanguineo || '';
            document.getElementById('p-alergias').value = p.alergias || '';
        }
    }
    new bootstrap.Modal(document.getElementById('modalPaciente')).show();
}

document.getElementById('form-paciente').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('p-id').value;
    const data = {
        id: id ? parseInt(id) : null,
        dni: document.getElementById('p-dni').value,
        nombre: document.getElementById('p-nombre').value,
        apellido: document.getElementById('p-apellido').value,
        fnac: document.getElementById('p-fnac').value,
        genero: document.getElementById('p-genero').value,
        tel: document.getElementById('p-tel').value,
        email: document.getElementById('p-email').value,
        direccion: document.getElementById('p-direccion').value,
        latitud: document.getElementById('p-lat').value || null,
        longitud: document.getElementById('p-lng').value || null,
        grupo_sanguineo: document.getElementById('p-grupo').value,
        alergias: document.getElementById('p-alergias').value
    };

    try {
        await apiSend('/pacientes', 'POST', data);
        await renderPacientes();
        await actualizarDashboard();
        bootstrap.Modal.getInstance(document.getElementById('modalPaciente')).hide();
        Swal.fire('Guardado', 'Paciente registrado con éxito en SQL Server', 'success');
    } catch (err) {
        mostrarError(err);
    }
});

function eliminarPaciente(id) {
    Swal.fire({
        title: '¿Eliminar paciente?', text: 'Esta acción no se puede deshacer', icon: 'warning',
        showCancelButton: true, confirmButtonText: 'Sí, eliminar'
    }).then(async (res) => {
        if (!res.isConfirmed) return;
        try {
            await apiSend(`/pacientes/${id}`, 'DELETE');
            await renderPacientes();
            await actualizarDashboard();
            Swal.fire('Eliminado', 'Paciente eliminado correctamente', 'success');
        } catch (err) { mostrarError(err); }
    });
}

// ==========================================
// 2. CRUD: PERSONAL MÉDICO
// ==========================================
async function renderMedicos() {
    cacheMedicos = await apiGet('/medicos');
    const tbody = document.querySelector('#tabla-medicos tbody');
    tbody.innerHTML = cacheMedicos.map(m => `
        <tr>
            <td>${m.id}</td>
            <td><strong>Dr(a). ${m.nombre} ${m.apellido}</strong></td>
            <td>${m.cmp}</td>
            <td><span class="badge bg-info text-dark">${m.especialidad || '-'}</span></td>
            <td>${m.tel || '-'}</td>
            <td class="text-center">
                <button class="btn btn-sm btn-outline-warning me-1" onclick="abrirModalMedico(${m.id})"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-outline-danger" onclick="eliminarMedico(${m.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>
    `).join('');
    actualizarSelectsDependientes();
}

function abrirModalMedico(id = null) {
    document.getElementById('form-medico').reset();
    document.getElementById('m-id').value = id || '';
    if (id) {
        const m = cacheMedicos.find(x => x.id === id);
        if (m) {
            document.getElementById('m-dni').value = m.dni;
            document.getElementById('m-nombre').value = m.nombre;
            document.getElementById('m-apellido').value = m.apellido;
            document.getElementById('m-cmp').value = m.cmp;
            document.getElementById('m-especialidad').value = m.especialidad_id;
            document.getElementById('m-tel').value = m.tel;
            document.getElementById('m-email').value = m.email;
        }
    }
    new bootstrap.Modal(document.getElementById('modalMedico')).show();
}

document.getElementById('form-medico').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('m-id').value;
    const data = {
        id: id ? parseInt(id) : null,
        dni: document.getElementById('m-dni').value,
        nombre: document.getElementById('m-nombre').value,
        apellido: document.getElementById('m-apellido').value,
        cmp: document.getElementById('m-cmp').value,
        especialidad_id: parseInt(document.getElementById('m-especialidad').value),
        tel: document.getElementById('m-tel').value,
        email: document.getElementById('m-email').value
    };
    try {
        await apiSend('/medicos', 'POST', data);
        await renderMedicos();
        await actualizarDashboard();
        bootstrap.Modal.getInstance(document.getElementById('modalMedico')).hide();
        Swal.fire('Guardado', 'Médico registrado con éxito', 'success');
    } catch (err) { mostrarError(err); }
});

function eliminarMedico(id) {
    Swal.fire({ title: '¿Eliminar médico?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' }).then(async (res) => {
        if (!res.isConfirmed) return;
        try {
            await apiSend(`/medicos/${id}`, 'DELETE');
            await renderMedicos();
            await actualizarDashboard();
            Swal.fire('Eliminado', 'Registro de médico eliminado', 'success');
        } catch (err) { mostrarError(err); }
    });
}

// ==========================================
// 3. CRUD: CITAS
// ==========================================
async function renderCitas() {
    cacheCitas = await apiGet('/citas');
    const tbody = document.querySelector('#tabla-citas tbody');
    tbody.innerHTML = cacheCitas.map(c => `
        <tr>
            <td>${c.id}</td>
            <td>${c.paciente_nombre || 'N/A'}</td>
            <td>${c.medico_nombre || 'N/A'}</td>
            <td>${c.fecha} ${c.hora}</td>
            <td>${c.motivo || '-'}</td>
            <td><span class="badge ${c.estado === 'Programada' ? 'bg-primary' : c.estado === 'Completada' || c.estado === 'Atendido' ? 'bg-success' : c.estado === 'Cancelada' ? 'bg-danger' : 'bg-secondary'}">${c.estado}</span></td>
            <td class="text-center">
                <button class="btn btn-sm btn-outline-warning me-1" onclick="abrirModalCita(${c.id})"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-outline-danger" onclick="eliminarCita(${c.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>
    `).join('');
    actualizarSelectsDependientes();
}

function abrirModalCita(id = null) {
    document.getElementById('form-cita').reset();
    document.getElementById('c-id').value = id || '';
    if (id) {
        const c = cacheCitas.find(x => x.id === id);
        if (c) {
            document.getElementById('c-paciente').value = c.paciente_id;
            document.getElementById('c-medico').value = c.medico_id;
            document.getElementById('c-fecha').value = c.fecha;
            document.getElementById('c-hora').value = c.hora;
            document.getElementById('c-estado').value = c.estado;
            document.getElementById('c-motivo').value = c.motivo || '';
        }
    }
    new bootstrap.Modal(document.getElementById('modalCita')).show();
}

document.getElementById('form-cita').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('c-id').value;
    const data = {
        id: id ? parseInt(id) : null,
        paciente_id: parseInt(document.getElementById('c-paciente').value),
        medico_id: parseInt(document.getElementById('c-medico').value),
        fecha: document.getElementById('c-fecha').value,
        hora: document.getElementById('c-hora').value,
        estado: document.getElementById('c-estado').value,
        motivo: document.getElementById('c-motivo').value
    };
    try {
        await apiSend('/citas', 'POST', data);
        await renderCitas();
        await actualizarDashboard();
        bootstrap.Modal.getInstance(document.getElementById('modalCita')).hide();
        Swal.fire('Guardado', 'Cita guardada correctamente', 'success');
    } catch (err) { mostrarError(err); }
});

function eliminarCita(id) {
    Swal.fire({ title: '¿Eliminar cita?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' }).then(async (res) => {
        if (!res.isConfirmed) return;
        try {
            await apiSend(`/citas/${id}`, 'DELETE');
            await renderCitas();
            await actualizarDashboard();
            Swal.fire('Eliminada', 'Cita eliminada correctamente', 'success');
        } catch (err) { mostrarError(err); }
    });
}

// ==========================================
// 4. CRUD: TRIAJE
// ==========================================
let cacheTriaje = [];

async function renderTriaje() {
    cacheTriaje = await apiGet('/triaje');
    const tbody = document.querySelector('#tabla-triaje tbody');
    tbody.innerHTML = cacheTriaje.map(t => `
        <tr>
            <td>${t.id}</td>
            <td>${t.paciente || 'N/A'}</td>
            <td>${t.presion} mmHg</td>
            <td>${t.temp} °C</td>
            <td>${t.so2}%</td>
            <td><span class="badge bg-secondary">${t.imc}</span></td>
            <td class="text-center">
                <button class="btn btn-sm btn-outline-warning me-1" onclick="abrirModalTriaje(${t.id})"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-outline-danger" onclick="eliminarTriaje(${t.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>
    `).join('');
}

function abrirModalTriaje(id = null) {
    document.getElementById('form-triaje').reset();
    document.getElementById('t-id').value = id || '';
    if (id) {
        const t = cacheTriaje.find(x => x.id === id);
        if (t) {
            document.getElementById('t-cita').value = t.cita_id || '';
            document.getElementById('t-presion').value = t.presion;
            document.getElementById('t-temp').value = t.temp;
            document.getElementById('t-fc').value = t.fc;
            document.getElementById('t-so2').value = t.so2;
            document.getElementById('t-peso').value = t.peso;
            document.getElementById('t-talla').value = t.talla;
        }
    }
    new bootstrap.Modal(document.getElementById('modalTriaje')).show();
}

document.getElementById('form-triaje').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('t-id').value;
    const data = {
        id: id ? parseInt(id) : null,
        cita_id: parseInt(document.getElementById('t-cita').value),
        presion: document.getElementById('t-presion').value,
        temp: parseFloat(document.getElementById('t-temp').value),
        fc: parseInt(document.getElementById('t-fc').value),
        so2: parseInt(document.getElementById('t-so2').value),
        peso: parseFloat(document.getElementById('t-peso').value),
        talla: parseFloat(document.getElementById('t-talla').value)
    };
    try {
        await apiSend('/triaje', 'POST', data);
        await renderTriaje();
        await renderCitas();
        bootstrap.Modal.getInstance(document.getElementById('modalTriaje')).hide();
        Swal.fire('Guardado', 'Triaje guardado correctamente', 'success');
    } catch (err) { mostrarError(err); }
});

function eliminarTriaje(id) {
    Swal.fire({ title: '¿Eliminar triaje?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' }).then(async (res) => {
        if (!res.isConfirmed) return;
        try {
            await apiSend(`/triaje/${id}`, 'DELETE');
            await renderTriaje();
            Swal.fire('Eliminado', 'Triaje eliminado', 'success');
        } catch (err) { mostrarError(err); }
    });
}

// ==========================================
// 5. CRUD: HISTORIAL CLÍNICO
// ==========================================
let cacheHistorial = [];

async function renderHistorial() {
    cacheHistorial = await apiGet('/historial');
    const tbody = document.querySelector('#tabla-historial tbody');
    tbody.innerHTML = cacheHistorial.map(h => `
        <tr>
            <td>${h.id}</td>
            <td>${h.paciente || 'N/A'}</td>
            <td>${h.medico || 'N/A'}</td>
            <td>${h.diagnostico}</td>
            <td><span class="badge bg-dark">${h.cie10 || '-'}</span></td>
            <td class="text-center">
                <button class="btn btn-sm btn-outline-warning me-1" onclick="abrirModalHistorial(${h.id})"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-outline-danger" onclick="eliminarHistorial(${h.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>
    `).join('');
}

function abrirModalHistorial(id = null) {
    document.getElementById('form-historial').reset();
    document.getElementById('h-id').value = id || '';
    if (id) {
        const h = cacheHistorial.find(x => x.id === id);
        if (h) {
            document.getElementById('h-cita').value = h.cita_id || '';
            document.getElementById('h-sintomas').value = h.sintomas;
            document.getElementById('h-diagnostico').value = h.diagnostico;
            document.getElementById('h-cie10').value = h.cie10 || '';
            document.getElementById('h-tratamiento').value = h.tratamiento;
        }
    }
    new bootstrap.Modal(document.getElementById('modalHistorial')).show();
}

document.getElementById('form-historial').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('h-id').value;
    const data = {
        id: id ? parseInt(id) : null,
        cita_id: parseInt(document.getElementById('h-cita').value),
        sintomas: document.getElementById('h-sintomas').value,
        diagnostico: document.getElementById('h-diagnostico').value,
        cie10: document.getElementById('h-cie10').value,
        tratamiento: document.getElementById('h-tratamiento').value
    };
    try {
        await apiSend('/historial', 'POST', data);
        await renderHistorial();
        await renderCitas();
        bootstrap.Modal.getInstance(document.getElementById('modalHistorial')).hide();
        Swal.fire('Guardado', 'Consulta clínica registrada', 'success');
    } catch (err) { mostrarError(err); }
});

function eliminarHistorial(id) {
    Swal.fire({ title: '¿Eliminar registro?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' }).then(async (res) => {
        if (!res.isConfirmed) return;
        try {
            await apiSend(`/historial/${id}`, 'DELETE');
            await renderHistorial();
            Swal.fire('Eliminado', 'Registro eliminado del historial', 'success');
        } catch (err) { mostrarError(err); }
    });
}

// ==========================================
// 6. CRUD: CAJA Y FACTURACIÓN
// ==========================================
let cacheFacturas = [];

async function renderFacturacion() {
    cacheFacturas = await apiGet('/facturacion');
    const tbody = document.querySelector('#tabla-facturacion tbody');
    tbody.innerHTML = cacheFacturas.map(f => `
        <tr>
            <td>${f.id}</td>
            <td>${f.paciente || 'N/A'}</td>
            <td><strong>${f.tipo} ${f.serie}-${f.correlativo}</strong></td>
            <td class="text-success fw-bold">S/ ${parseFloat(f.monto).toFixed(2)}</td>
            <td>${f.metodo}</td>
            <td><span class="badge ${f.estado === 'Anulado' ? 'bg-danger' : 'bg-success'}">${f.estado}</span></td>
            <td>${f.fecha}</td>
            <td class="text-center">
                <button class="btn btn-sm btn-outline-warning me-1" onclick="abrirModalFacturacion(${f.id})"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-outline-danger" onclick="eliminarFactura(${f.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>
    `).join('');
}

function abrirModalFacturacion(id = null) {
    document.getElementById('form-facturacion').reset();
    document.getElementById('f-id').value = id || '';
    document.getElementById('f-serie').value = 'B001';
    if (id) {
        const f = cacheFacturas.find(x => x.id === id);
        if (f) {
            document.getElementById('f-paciente').value = f.paciente_id;
            document.getElementById('f-tipo').value = f.tipo;
            document.getElementById('f-serie').value = f.serie;
            document.getElementById('f-correlativo').value = f.correlativo;
            document.getElementById('f-monto').value = f.monto;
            document.getElementById('f-metodo').value = f.metodo;
        }
    }
    new bootstrap.Modal(document.getElementById('modalFacturacion')).show();
}

document.getElementById('form-facturacion').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('f-id').value;
    const data = {
        id: id ? parseInt(id) : null,
        paciente_id: parseInt(document.getElementById('f-paciente').value),
        tipo: document.getElementById('f-tipo').value,
        serie: document.getElementById('f-serie').value,
        correlativo: document.getElementById('f-correlativo').value,
        monto: parseFloat(document.getElementById('f-monto').value),
        metodo: document.getElementById('f-metodo').value
    };
    try {
        await apiSend('/facturacion', 'POST', data);
        await renderFacturacion();
        await actualizarDashboard();
        bootstrap.Modal.getInstance(document.getElementById('modalFacturacion')).hide();
        Swal.fire('Guardado', 'Comprobante de pago emitido', 'success');
    } catch (err) { mostrarError(err); }
});

function eliminarFactura(id) {
    Swal.fire({ title: '¿Anular comprobante?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, anular' }).then(async (res) => {
        if (!res.isConfirmed) return;
        try {
            await apiSend(`/facturacion/${id}`, 'DELETE');
            await renderFacturacion();
            await actualizarDashboard();
            Swal.fire('Anulado', 'Comprobante anulado', 'success');
        } catch (err) { mostrarError(err); }
    });
}

// ==========================================
// 7. CRUD: FARMACIA
// ==========================================
let cacheFarmacia = [];

async function renderFarmacia() {
    cacheFarmacia = await apiGet('/farmacia');
    const tbody = document.querySelector('#tabla-farmacia tbody');
    tbody.innerHTML = cacheFarmacia.map(f => `
        <tr>
            <td>${f.id}</td>
            <td><code>${f.codigo}</code></td>
            <td><strong>${f.nombre}</strong></td>
            <td>${f.tipo || '-'}</td>
            <td><span class="badge ${f.stock < 10 ? 'bg-danger' : 'bg-success'}">${f.stock}</span></td>
            <td>S/ ${parseFloat(f.precio).toFixed(2)}</td>
            <td class="text-center">
                <button class="btn btn-sm btn-outline-warning me-1" onclick="abrirModalFarmacia(${f.id})"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-outline-danger" onclick="eliminarFarmacia(${f.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>
    `).join('');
}

function abrirModalFarmacia(id = null) {
    document.getElementById('form-farmacia').reset();
    document.getElementById('far-id').value = id || '';
    if (id) {
        const f = cacheFarmacia.find(x => x.id === id);
        if (f) {
            document.getElementById('far-codigo').value = f.codigo;
            document.getElementById('far-nombre').value = f.nombre;
            document.getElementById('far-tipo').value = f.tipo;
            document.getElementById('far-stock').value = f.stock;
            document.getElementById('far-precio').value = f.precio;
            document.getElementById('far-vencimiento').value = f.vencimiento;
        }
    }
    new bootstrap.Modal(document.getElementById('modalFarmacia')).show();
}

document.getElementById('form-farmacia').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('far-id').value;
    const data = {
        id: id ? parseInt(id) : null,
        codigo: document.getElementById('far-codigo').value,
        nombre: document.getElementById('far-nombre').value,
        tipo: document.getElementById('far-tipo').value,
        stock: parseInt(document.getElementById('far-stock').value),
        precio: parseFloat(document.getElementById('far-precio').value),
        vencimiento: document.getElementById('far-vencimiento').value
    };
    try {
        await apiSend('/farmacia', 'POST', data);
        await renderFarmacia();
        bootstrap.Modal.getInstance(document.getElementById('modalFarmacia')).hide();
        Swal.fire('Guardado', 'Medicamento registrado', 'success');
    } catch (err) { mostrarError(err); }
});

function eliminarFarmacia(id) {
    Swal.fire({ title: '¿Eliminar producto?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' }).then(async (res) => {
        if (!res.isConfirmed) return;
        try {
            await apiSend(`/farmacia/${id}`, 'DELETE');
            await renderFarmacia();
            Swal.fire('Eliminado', 'Producto eliminado de inventario', 'success');
        } catch (err) { mostrarError(err); }
    });
}

// ==========================================
// 8. CRUD: LABORATORIO
// ==========================================
let cacheLaboratorio = [];

async function renderLaboratorio() {
    cacheLaboratorio = await apiGet('/laboratorio');
    const tbody = document.querySelector('#tabla-laboratorio tbody');
    tbody.innerHTML = cacheLaboratorio.map(l => `
        <tr>
            <td>${l.id}</td>
            <td>${l.paciente || 'N/A'}</td>
            <td><strong>${l.examen}</strong></td>
            <td><span class="badge ${l.estado === 'Completado' ? 'bg-success' : l.estado === 'En Proceso' ? 'bg-info text-dark' : 'bg-warning text-dark'}">${l.estado}</span></td>
            <td>${l.resultado || '-'}</td>
            <td class="text-center">
                <button class="btn btn-sm btn-outline-warning me-1" onclick="abrirModalLaboratorio(${l.id})"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-outline-danger" onclick="eliminarLaboratorio(${l.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>
    `).join('');
}

function abrirModalLaboratorio(id = null) {
    document.getElementById('form-laboratorio').reset();
    document.getElementById('lab-id').value = id || '';
    if (id) {
        const l = cacheLaboratorio.find(x => x.id === id);
        if (l) {
            document.getElementById('lab-paciente').value = l.paciente_id;
            document.getElementById('lab-medico').value = l.medico_id;
            document.getElementById('lab-examen').value = l.examen;
            document.getElementById('lab-estado').value = l.estado;
            document.getElementById('lab-resultado').value = l.resultado || '';
        }
    }
    new bootstrap.Modal(document.getElementById('modalLaboratorio')).show();
}

document.getElementById('form-laboratorio').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('lab-id').value;
    const data = {
        id: id ? parseInt(id) : null,
        paciente_id: parseInt(document.getElementById('lab-paciente').value),
        medico_id: parseInt(document.getElementById('lab-medico').value),
        examen: document.getElementById('lab-examen').value,
        estado: document.getElementById('lab-estado').value,
        resultado: document.getElementById('lab-resultado').value
    };
    try {
        await apiSend('/laboratorio', 'POST', data);
        await renderLaboratorio();
        bootstrap.Modal.getInstance(document.getElementById('modalLaboratorio')).hide();
        Swal.fire('Guardado', 'Orden de laboratorio guardada', 'success');
    } catch (err) { mostrarError(err); }
});

function eliminarLaboratorio(id) {
    Swal.fire({ title: '¿Eliminar orden?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' }).then(async (res) => {
        if (!res.isConfirmed) return;
        try {
            await apiSend(`/laboratorio/${id}`, 'DELETE');
            await renderLaboratorio();
            Swal.fire('Eliminada', 'Orden de laboratorio eliminada', 'success');
        } catch (err) { mostrarError(err); }
    });
}

// ==========================================
// 9. CRUD: HOSPITALIZACIÓN (con camas reales)
// ==========================================
let cacheHospitalizaciones = [];

async function renderHospitalizacion() {
    cacheHospitalizaciones = await apiGet('/hospitalizacion');
    const tbody = document.querySelector('#tabla-hospitalizacion tbody');
    tbody.innerHTML = cacheHospitalizaciones.map(h => `
        <tr>
            <td>${h.id}</td>
            <td>${h.paciente || 'N/A'}</td>
            <td><span class="badge bg-info text-dark">${h.cama || '-'}</span></td>
            <td>${h.medico || 'N/A'}</td>
            <td><span class="badge ${h.estado === 'Activo' ? 'bg-primary' : 'bg-success'}">${h.estado}</span></td>
            <td class="text-center">
                ${h.estado === 'Activo' ? `<button class="btn btn-sm btn-outline-success me-1" onclick="darAlta(${h.id})" title="Dar de alta"><i class="bi bi-box-arrow-right"></i></button>` : ''}
                <button class="btn btn-sm btn-outline-danger" onclick="eliminarHospitalizacion(${h.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>
    `).join('');
}

async function abrirModalHospitalizacion(id = null) {
    document.getElementById('form-hospitalizacion').reset();
    document.getElementById('hosp-id').value = id || '';
    await cargarCamasDisponibles();
    new bootstrap.Modal(document.getElementById('modalHospitalizacion')).show();
}

document.getElementById('form-hospitalizacion').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('hosp-id').value;
    const data = {
        id: id ? parseInt(id) : null,
        paciente_id: parseInt(document.getElementById('hosp-paciente').value),
        medico_id: parseInt(document.getElementById('hosp-medico').value),
        cama_id: parseInt(document.getElementById('hosp-cama').value),
        diag: document.getElementById('hosp-diag').value
    };
    try {
        await apiSend('/hospitalizacion', 'POST', data);
        await renderHospitalizacion();
        await actualizarDashboard();
        bootstrap.Modal.getInstance(document.getElementById('modalHospitalizacion')).hide();
        Swal.fire('Guardado', 'Paciente hospitalizado y cama asignada', 'success');
    } catch (err) { mostrarError(err); }
});

function darAlta(id) {
    Swal.fire({ title: '¿Dar de alta al paciente?', text: 'La cama quedará disponible nuevamente', icon: 'question', showCancelButton: true, confirmButtonText: 'Sí, dar de alta' }).then(async (res) => {
        if (!res.isConfirmed) return;
        try {
            await apiSend(`/hospitalizacion/${id}/alta`, 'POST');
            await renderHospitalizacion();
            Swal.fire('Completado', 'Paciente dado de alta, cama liberada', 'success');
        } catch (err) { mostrarError(err); }
    });
}

function eliminarHospitalizacion(id) {
    Swal.fire({ title: '¿Eliminar registro?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' }).then(async (res) => {
        if (!res.isConfirmed) return;
        try {
            await apiSend(`/hospitalizacion/${id}`, 'DELETE');
            await renderHospitalizacion();
            Swal.fire('Eliminado', 'Registro de hospitalización eliminado', 'success');
        } catch (err) { mostrarError(err); }
    });
}

// ==========================================
// 10. CRUD: NOTIFICACIONES
// ==========================================
let cacheNotificaciones = [];

async function renderNotificaciones() {
    cacheNotificaciones = await apiGet('/notificaciones');
    const tbody = document.querySelector('#tabla-notificaciones tbody');
    tbody.innerHTML = cacheNotificaciones.map(n => `
        <tr>
            <td>${n.id}</td>
            <td>${n.email}</td>
            <td><strong>${n.asunto}</strong></td>
            <td>${n.mensaje}</td>
            <td>${n.fecha}</td>
            <td class="text-center">
                <button class="btn btn-sm btn-outline-danger" onclick="eliminarNotificacion(${n.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>
    `).join('');
}

function abrirModalNotificacion(id = null) {
    document.getElementById('form-notificacion').reset();
    document.getElementById('not-id').value = id || '';
    new bootstrap.Modal(document.getElementById('modalNotificacion')).show();
}

document.getElementById('form-notificacion').addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = {
        email: document.getElementById('not-email').value,
        asunto: document.getElementById('not-asunto').value,
        mensaje: document.getElementById('not-mensaje').value
    };
    try {
        await apiSend('/notificaciones', 'POST', data);
        await renderNotificaciones();
        bootstrap.Modal.getInstance(document.getElementById('modalNotificacion')).hide();
        Swal.fire('Enviado', 'La notificación fue registrada con éxito', 'success');
    } catch (err) { mostrarError(err); }
});

function eliminarNotificacion(id) {
    Swal.fire({ title: '¿Eliminar notificación?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' }).then(async (res) => {
        if (!res.isConfirmed) return;
        try {
            await apiSend(`/notificaciones/${id}`, 'DELETE');
            await renderNotificaciones();
            Swal.fire('Eliminada', 'Notificación eliminada', 'success');
        } catch (err) { mostrarError(err); }
    });
}
