/**
 * MedControl Pro - Sistema de Gestión Hospitalaria
 * app.js — Controlador centralizado, limpio y optimizado para SPA.
 */

const API = '/api';

// Caches globales en memoria
window.cachePacientes = [];
window.cacheMedicos = [];
window.cacheCitas = [];
window.cacheTriaje = [];
window.cacheHistorial = [];
window.cacheFacturas = [];
window.cacheFarmacia = [];
window.cacheLaboratorio = [];
window.cacheHospitalizaciones = [];
window.cacheNotificaciones = [];
window.cacheEspecialidades = [];
window.cacheCamasDisponibles = [];

// ==========================================
// 1. HELPERS DE RED Y MODALES
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
    if (!res.ok) throw new Error(data.error || 'Error al procesar solicitud');
    return data;
}

function mostrarError(err) {
    console.error(err);
    if (typeof Swal !== 'undefined') {
        Swal.fire('Error', err.message || 'Ocurrió un problema con el servidor', 'error');
    } else {
        alert('Error: ' + (err.message || 'Error en el servidor'));
    }
}

function abrirModal(modalId) {
    const el = document.getElementById(modalId);
    if (!el) return;
    if (window.bootstrap && bootstrap.Modal) {
        const m = bootstrap.Modal.getInstance(el) || new bootstrap.Modal(el);
        m.show();
    }
}

function cerrarModal(modalId) {
    const el = document.getElementById(modalId);
    if (!el) return;
    if (window.bootstrap && bootstrap.Modal) {
        const m = bootstrap.Modal.getInstance(el);
        if (m) m.hide();
    }
}

// ==========================================
// 2. NAVEGACIÓN SPA Y CARGA INICIAL
// ==========================================
function mostrarSeccion(secId) {
    const navLinks = document.querySelectorAll('#menu-items .nav-link');
    const modulos = document.querySelectorAll('.modulo-sec');
    const titleModulo = document.getElementById('title-modulo');

    modulos.forEach(m => m.classList.add('d-none'));
    navLinks.forEach(l => {
        if (l.getAttribute('data-sec') === secId) {
            l.classList.add('active');
            if (titleModulo) titleModulo.innerText = l.innerText.trim();
        } else {
            l.classList.remove('active');
        }
    });

    const targetSec = document.getElementById(`sec-${secId}`);
    if (targetSec) targetSec.classList.remove('d-none');

    if (secId === 'dashboard' && typeof mapaDashboard !== 'undefined' && mapaDashboard) {
        setTimeout(() => mapaDashboard.invalidateSize(), 150);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Menú de navegación lateral
    const navLinks = document.querySelectorAll('#menu-items .nav-link[data-sec]');
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const secId = link.getAttribute('data-sec');
            if (secId) mostrarSeccion(secId);
        });
    });

    // Submits de formularios
    inicializarFormularios();

    // Inicializaciones auxiliares
    if (typeof inicializarMapaDashboard === 'function') {
        try { inicializarMapaDashboard(); } catch (e) { console.warn('Aviso Mapa:', e); }
    }
    if (typeof activarAutocompleteDireccion === 'function') {
        try { activarAutocompleteDireccion('p-direccion', 'p-direccion-list', 'p-lat', 'p-lng'); } catch (e) { console.warn(e); }
    }
    activarAutocompleteCie10();

    // Carga inicial
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
// 3. DASHBOARD Y SERVICIOS EXTERNOS
// ==========================================
async function actualizarDashboard() {
    try {
        const d = await apiGet('/dashboard');
        if (document.getElementById('dash-pacientes')) document.getElementById('dash-pacientes').innerText = d.pacientes ?? 0;
        if (document.getElementById('dash-citas')) document.getElementById('dash-citas').innerText = d.citas ?? 0;
        if (document.getElementById('dash-medicos')) document.getElementById('dash-medicos').innerText = d.medicos ?? 0;
        if (document.getElementById('dash-ingresos')) document.getElementById('dash-ingresos').innerText = (d.ingresos ?? 0).toFixed(2);

        if (typeof actualizarMarcadoresPacientes === 'function') {
            actualizarMarcadoresPacientes(window.cachePacientes);
        }
    } catch (err) {
        mostrarError(err);
    }
}

async function buscarDniReniec() {
    const dniInput = document.getElementById('p-dni');
    if (!dniInput) return;
    const dni = dniInput.value.trim();
    if (dni.length !== 8) return Swal.fire('Error', 'Ingrese un DNI válido de 8 dígitos', 'warning');

    Swal.fire({ title: 'Consultando RENIEC...', allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
        const data = await apiGet(`/reniec/${dni}`);
        document.getElementById('p-nombre').value = data.nombres || '';
        document.getElementById('p-apellido').value = data.apellidos || `${data.apellidoPaterno || ''} ${data.apellidoMaterno || ''}`.trim();
        Swal.fire('Éxito', 'Datos obtenidos de RENIEC', 'success');
    } catch (err) {
        Swal.fire('Sin resultados', err.message, 'warning');
    }
}

async function buscarDniReniecMedico() {
    const dniInput = document.getElementById('m-dni');
    if (!dniInput) return;
    const dni = dniInput.value.trim();
    if (dni.length !== 8) return Swal.fire('Error', 'Ingrese un DNI válido de 8 dígitos', 'warning');

    Swal.fire({ title: 'Consultando RENIEC...', allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
        const data = await apiGet(`/reniec/${dni}`);
        document.getElementById('m-nombre').value = data.nombres || '';
        document.getElementById('m-apellido').value = data.apellidos || `${data.apellidoPaterno || ''} ${data.apellidoMaterno || ''}`.trim();
        Swal.fire('Éxito', 'Datos obtenidos de RENIEC', 'success');
    } catch (err) {
        Swal.fire('Sin resultados', err.message, 'warning');
    }
}

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
                const resultados = data[3] || [];
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
// 4. DESPLEGABLES DINÁMICOS (SELECTS)
// ==========================================
async function cargarEspecialidades() {
    try {
        window.cacheEspecialidades = await apiGet('/especialidades');
        const sel = document.getElementById('m-especialidad');
        if (sel) {
            sel.innerHTML = '<option value="">Seleccione Especialidad</option>' +
                window.cacheEspecialidades.map(e => `<option value="${e.id}">${e.nombre}</option>`).join('');
        }
    } catch (e) { console.warn('Error especialidades:', e); }
}

async function cargarCamasDisponibles(seleccionarId = null) {
    try {
        window.cacheCamasDisponibles = await apiGet('/camas-disponibles');
        const sel = document.getElementById('hosp-cama');
        if (sel) {
            sel.innerHTML = '<option value="">Seleccione Cama Disponible</option>' +
                window.cacheCamasDisponibles.map(c => `<option value="${c.id}">Hab. ${c.numero_habitacion} - Cama ${c.numero_cama} (${c.tipo})</option>`).join('');
            if (seleccionarId) sel.value = seleccionarId;
        }
    } catch (e) { console.warn('Error camas:', e); }
}

function actualizarSelectsDependientes() {
    const pacienteOptions = window.cachePacientes.map(p => `<option value="${p.id}">${p.nombre} ${p.apellido} (DNI: ${p.dni})</option>`).join('');
    ['c-paciente', 'f-paciente', 'lab-paciente', 'hosp-paciente'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<option value="">Seleccione Paciente</option>' + pacienteOptions;
    });

    const medicoOptions = window.cacheMedicos.map(m => `<option value="${m.id}">Dr(a). ${m.nombre} ${m.apellido} (${m.especialidad || 'Gral'})</option>`).join('');
    ['c-medico', 'lab-medico', 'hosp-medico'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<option value="">Seleccione Médico</option>' + medicoOptions;
    });

    const citaOptions = window.cacheCitas.map(c => `<option value="${c.id}">Cita #${c.id} - ${c.paciente_nombre || 'Paciente'} (${c.fecha})</option>`).join('');
    ['t-cita', 'h-cita'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<option value="">Seleccione Cita</option>' + citaOptions;
    });
}

// ==========================================
// 5. MÓDULOS CRUD
// ==========================================

// --- PACIENTES ---
async function renderPacientes() {
    window.cachePacientes = await apiGet('/pacientes');
    const tbody = document.querySelector('#tabla-pacientes tbody');
    if (!tbody) return;

    tbody.innerHTML = window.cachePacientes.length === 0 ?
        '<tr><td colspan="6" class="text-center text-muted py-3">No hay pacientes registrados</td></tr>' :
        window.cachePacientes.map(p => `
            <tr>
                <td>${p.id}</td>
                <td class="fw-semibold">${p.nombre} ${p.apellido}</td>
                <td>${p.dni}</td>
                <td>${p.telefono || '-'}</td>
                <td>${p.email || '-'}</td>
                <td class="text-center">
                    <button class="btn btn-sm btn-outline-warning me-1" onclick="editarPaciente(${p.id})"><i class="bi bi-pencil"></i></button>
                    <button class="btn btn-sm btn-outline-danger" onclick="eliminarPaciente(${p.id})"><i class="bi bi-trash"></i></button>
                </td>
            </tr>
        `).join('');
    actualizarSelectsDependientes();
}

function abrirModalPaciente(esEdicion = false) {
    if (!esEdicion) {
        const form = document.getElementById('form-paciente');
        if (form) form.reset();
        document.getElementById('p-id').value = '';
    }
    abrirModal('modalPaciente');
}

function editarPaciente(id) {
    const p = window.cachePacientes.find(x => x.id === id);
    if (!p) return;
    document.getElementById('p-id').value = p.id;
    document.getElementById('p-dni').value = p.dni || '';
    document.getElementById('p-nombre').value = p.nombre || '';
    document.getElementById('p-apellido').value = p.apellido || '';
    document.getElementById('p-fnac').value = p.fnac || '';
    document.getElementById('p-genero').value = p.genero || 'Masculino';
    document.getElementById('p-tel').value = p.telefono || p.tel || '';
    document.getElementById('p-email').value = p.email || '';
    document.getElementById('p-direccion').value = p.direccion || '';
    document.getElementById('p-grupo').value = p.grupo_sanguineo || '';
    document.getElementById('p-alergias').value = p.alergias || '';
    abrirModalPaciente(true);
}

async function guardarPaciente(e) {
    if (e && e.preventDefault) e.preventDefault();
    const id = document.getElementById('p-id').value;
    const payload = {
        id: id ? parseInt(id) : null,
        dni: document.getElementById('p-dni').value.trim(),
        nombre: document.getElementById('p-nombre').value.trim(),
        apellido: document.getElementById('p-apellido').value.trim(),
        fnac: document.getElementById('p-fnac').value,
        genero: document.getElementById('p-genero').value,
        tel: document.getElementById('p-tel').value.trim(),
        email: document.getElementById('p-email').value.trim(),
        direccion: document.getElementById('p-direccion').value.trim(),
        grupo_sanguineo: document.getElementById('p-grupo').value.trim(),
        alergias: document.getElementById('p-alergias').value.trim()
    };

    try {
        await apiSend('/pacientes', 'POST', payload);
        cerrarModal('modalPaciente');
        await renderPacientes();
        await actualizarDashboard();
        Swal.fire('Guardado', 'Paciente registrado correctamente', 'success');
    } catch (err) { mostrarError(err); }
}

async function eliminarPaciente(id) {
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

// --- PERSONAL MÉDICO ---
async function renderMedicos() {
    window.cacheMedicos = await apiGet('/medicos');
    const tbody = document.querySelector('#tabla-medicos tbody');
    if (!tbody) return;

    tbody.innerHTML = window.cacheMedicos.length === 0 ?
        '<tr><td colspan="6" class="text-center text-muted py-3">No hay médicos registrados</td></tr>' :
        window.cacheMedicos.map(m => `
            <tr>
                <td>${m.id}</td>
                <td class="fw-semibold">Dr(a). ${m.nombre} ${m.apellido}</td>
                <td>${m.cmp || '-'}</td>
                <td><span class="badge bg-info text-dark">${m.especialidad || 'General'}</span></td>
                <td>${m.tel || '-'}</td>
                <td class="text-center">
                    <button class="btn btn-sm btn-outline-warning me-1" onclick="editarMedico(${m.id})"><i class="bi bi-pencil"></i></button>
                    <button class="btn btn-sm btn-outline-danger" onclick="eliminarMedico(${m.id})"><i class="bi bi-trash"></i></button>
                </td>
            </tr>
        `).join('');
    actualizarSelectsDependientes();
}

async function abrirModalMedico(esEdicion = false) {
    await cargarEspecialidades();
    if (!esEdicion) {
        const form = document.getElementById('form-medico');
        if (form) form.reset();
        document.getElementById('m-id').value = '';
    }
    abrirModal('modalMedico');
}

function editarMedico(id) {
    const m = window.cacheMedicos.find(x => x.id === id);
    if (!m) return;
    abrirModalMedico(true);
    document.getElementById('m-id').value = m.id;
    document.getElementById('m-dni').value = m.dni || '';
    document.getElementById('m-nombre').value = m.nombre || '';
    document.getElementById('m-apellido').value = m.apellido || '';
    document.getElementById('m-cmp').value = m.cmp || '';
    document.getElementById('m-especialidad').value = m.especialidad_id || '';
    document.getElementById('m-tel').value = m.tel || '';
    document.getElementById('m-email').value = m.email || '';
}

async function guardarMedico(e) {
    if (e && e.preventDefault) e.preventDefault();
    const id = document.getElementById('m-id').value;
    const payload = {
        id: id ? parseInt(id) : null,
        dni: document.getElementById('m-dni').value.trim(),
        nombre: document.getElementById('m-nombre').value.trim(),
        apellido: document.getElementById('m-apellido').value.trim(),
        cmp: document.getElementById('m-cmp').value.trim(),
        especialidad_id: parseInt(document.getElementById('m-especialidad').value),
        tel: document.getElementById('m-tel').value.trim(),
        email: document.getElementById('m-email').value.trim()
    };

    try {
        await apiSend('/medicos', 'POST', payload);
        cerrarModal('modalMedico');
        await renderMedicos();
        await actualizarDashboard();
        Swal.fire('Guardado', 'Médico registrado con éxito', 'success');
    } catch (err) { mostrarError(err); }
}

async function eliminarMedico(id) {
    Swal.fire({ title: '¿Eliminar médico?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' })
        .then(async (res) => {
            if (!res.isConfirmed) return;
            try {
                await apiSend(`/medicos/${id}`, 'DELETE');
                await renderMedicos();
                await actualizarDashboard();
                Swal.fire('Eliminado', 'Médico eliminado', 'success');
            } catch (err) { mostrarError(err); }
        });
}

// --- CITAS MÉDICAS ---
async function renderCitas() {
    window.cacheCitas = await apiGet('/citas');
    const tbody = document.querySelector('#tabla-citas tbody');
    if (!tbody) return;

    tbody.innerHTML = window.cacheCitas.length === 0 ?
        '<tr><td colspan="7" class="text-center text-muted py-3">No hay citas registradas</td></tr>' :
        window.cacheCitas.map(c => `
            <tr>
                <td>${c.id}</td>
                <td class="fw-semibold">${c.paciente_nombre || 'N/A'}</td>
                <td>${c.medico_nombre || 'N/A'}</td>
                <td>${c.fecha} ${c.hora}</td>
                <td>${c.motivo || '-'}</td>
                <td><span class="badge bg-${c.estado === 'Atendido' || c.estado === 'Completada' ? 'success' : c.estado === 'Cancelada' ? 'danger' : 'primary'}">${c.estado}</span></td>
                <td class="text-center">
                    <button class="btn btn-sm btn-outline-warning me-1" onclick="editarCita(${c.id})"><i class="bi bi-pencil"></i></button>
                    <button class="btn btn-sm btn-outline-danger" onclick="eliminarCita(${c.id})"><i class="bi bi-trash"></i></button>
                </td>
            </tr>
        `).join('');
    actualizarSelectsDependientes();
}

function abrirModalCita(esEdicion = false) {
    actualizarSelectsDependientes();
    if (!esEdicion) {
        const form = document.getElementById('form-cita');
        if (form) form.reset();
        document.getElementById('c-id').value = '';
    }
    abrirModal('modalCita');
}

function editarCita(id) {
    const c = window.cacheCitas.find(x => x.id === id);
    if (!c) return;
    abrirModalCita(true);
    document.getElementById('c-id').value = c.id;
    document.getElementById('c-paciente').value = c.paciente_id;
    document.getElementById('c-medico').value = c.medico_id;
    document.getElementById('c-fecha').value = c.fecha;
    document.getElementById('c-hora').value = c.hora;
    document.getElementById('c-estado').value = c.estado;
    document.getElementById('c-motivo').value = c.motivo || '';
}

async function guardarCita(e) {
    if (e && e.preventDefault) e.preventDefault();
    const id = document.getElementById('c-id').value;
    const payload = {
        id: id ? parseInt(id) : null,
        paciente_id: parseInt(document.getElementById('c-paciente').value),
        medico_id: parseInt(document.getElementById('c-medico').value),
        fecha: document.getElementById('c-fecha').value,
        hora: document.getElementById('c-hora').value,
        estado: document.getElementById('c-estado').value,
        motivo: document.getElementById('c-motivo').value.trim()
    };

    try {
        await apiSend('/citas', 'POST', payload);
        cerrarModal('modalCita');
        await renderCitas();
        await actualizarDashboard();
        Swal.fire('Guardado', 'Cita médica guardada', 'success');
    } catch (err) { mostrarError(err); }
}

async function eliminarCita(id) {
    Swal.fire({ title: '¿Eliminar cita?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' })
        .then(async (res) => {
            if (!res.isConfirmed) return;
            try {
                await apiSend(`/citas/${id}`, 'DELETE');
                await renderCitas();
                await actualizarDashboard();
                Swal.fire('Eliminado', 'Cita eliminada', 'success');
            } catch (err) { mostrarError(err); }
        });
}

// --- TRIAJE ---
async function renderTriaje() {
    window.cacheTriaje = await apiGet('/triaje');
    const tbody = document.querySelector('#tabla-triaje tbody');
    if (!tbody) return;

    tbody.innerHTML = window.cacheTriaje.length === 0 ?
        '<tr><td colspan="7" class="text-center text-muted py-3">No hay registros de triaje</td></tr>' :
        window.cacheTriaje.map(t => `
            <tr>
                <td>${t.id}</td>
                <td class="fw-semibold">${t.paciente || 'N/A'}</td>
                <td>${t.presion || '-'} mmHg</td>
                <td>${t.temp ? t.temp + ' °C' : '-'}</td>
                <td>${t.so2 ? t.so2 + ' %' : '-'}</td>
                <td><span class="badge bg-secondary">${t.imc || '-'}</span></td>
                <td class="text-center">
                    <button class="btn btn-sm btn-outline-warning me-1" onclick="editarTriaje(${t.id})"><i class="bi bi-pencil"></i></button>
                    <button class="btn btn-sm btn-outline-danger" onclick="eliminarTriaje(${t.id})"><i class="bi bi-trash"></i></button>
                </td>
            </tr>
        `).join('');
}

function abrirModalTriaje(esEdicion = false) {
    actualizarSelectsDependientes();
    if (!esEdicion) {
        const form = document.getElementById('form-triaje');
        if (form) form.reset();
        document.getElementById('t-id').value = '';
    }
    abrirModal('modalTriaje');
}

function editarTriaje(id) {
    const t = window.cacheTriaje.find(x => x.id === id);
    if (!t) return;
    abrirModalTriaje(true);
    document.getElementById('t-id').value = t.id;
    document.getElementById('t-cita').value = t.cita_id || '';
    document.getElementById('t-presion').value = t.presion || '';
    document.getElementById('t-temp').value = t.temp || '';
    document.getElementById('t-fc').value = t.fc || '';
    document.getElementById('t-so2').value = t.so2 || '';
    document.getElementById('t-peso').value = t.peso || '';
    document.getElementById('t-talla').value = t.talla || '';
}

async function guardarTriaje(e) {
    if (e && e.preventDefault) e.preventDefault();
    const id = document.getElementById('t-id').value;
    const payload = {
        id: id ? parseInt(id) : null,
        cita_id: parseInt(document.getElementById('t-cita').value),
        presion: document.getElementById('t-presion').value.trim(),
        temp: parseFloat(document.getElementById('t-temp').value),
        fc: parseInt(document.getElementById('t-fc').value),
        so2: parseInt(document.getElementById('t-so2').value),
        peso: parseFloat(document.getElementById('t-peso').value),
        talla: parseFloat(document.getElementById('t-talla').value)
    };

    try {
        await apiSend('/triaje', 'POST', payload);
        cerrarModal('modalTriaje');
        await renderTriaje();
        await renderCitas();
        Swal.fire('Guardado', 'Triaje guardado correctamente', 'success');
    } catch (err) { mostrarError(err); }
}

async function eliminarTriaje(id) {
    Swal.fire({ title: '¿Eliminar triaje?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' })
        .then(async (res) => {
            if (!res.isConfirmed) return;
            try {
                await apiSend(`/triaje/${id}`, 'DELETE');
                await renderTriaje();
                Swal.fire('Eliminado', 'Triaje eliminado', 'success');
            } catch (err) { mostrarError(err); }
        });
}

// --- HISTORIAL CLÍNICO ---
async function renderHistorial() {
    window.cacheHistorial = await apiGet('/historial');
    const tbody = document.querySelector('#tabla-historial tbody');
    if (!tbody) return;

    tbody.innerHTML = window.cacheHistorial.length === 0 ?
        '<tr><td colspan="6" class="text-center text-muted py-3">No hay historiales registrados</td></tr>' :
        window.cacheHistorial.map(h => `
            <tr>
                <td>${h.id}</td>
                <td class="fw-semibold">${h.paciente || 'N/A'}</td>
                <td>${h.medico || 'N/A'}</td>
                <td>${h.diagnostico}</td>
                <td><span class="badge bg-dark">${h.cie10 || '-'}</span></td>
                <td class="text-center">
                    <button class="btn btn-sm btn-outline-warning me-1" onclick="editarHistorial(${h.id})"><i class="bi bi-pencil"></i></button>
                    <button class="btn btn-sm btn-outline-danger" onclick="eliminarHistorial(${h.id})"><i class="bi bi-trash"></i></button>
                </td>
            </tr>
        `).join('');
}

function abrirModalHistorial(esEdicion = false) {
    actualizarSelectsDependientes();
    if (!esEdicion) {
        const form = document.getElementById('form-historial');
        if (form) form.reset();
        document.getElementById('h-id').value = '';
    }
    abrirModal('modalHistorial');
}

function editarHistorial(id) {
    const h = window.cacheHistorial.find(x => x.id === id);
    if (!h) return;
    abrirModalHistorial(true);
    document.getElementById('h-id').value = h.id;
    document.getElementById('h-cita').value = h.cita_id || '';
    document.getElementById('h-sintomas').value = h.sintomas || '';
    document.getElementById('h-diagnostico').value = h.diagnostico || '';
    document.getElementById('h-cie10').value = h.cie10 || '';
    document.getElementById('h-tratamiento').value = h.tratamiento || '';
}

async function guardarHistorial(e) {
    if (e && e.preventDefault) e.preventDefault();
    const id = document.getElementById('h-id').value;
    const payload = {
        id: id ? parseInt(id) : null,
        cita_id: parseInt(document.getElementById('h-cita').value),
        sintomas: document.getElementById('h-sintomas').value.trim(),
        diagnostico: document.getElementById('h-diagnostico').value.trim(),
        cie10: document.getElementById('h-cie10').value.trim(),
        tratamiento: document.getElementById('h-tratamiento').value.trim()
    };

    try {
        await apiSend('/historial', 'POST', payload);
        cerrarModal('modalHistorial');
        await renderHistorial();
        await renderCitas();
        Swal.fire('Guardado', 'Consulta registrada en el historial', 'success');
    } catch (err) { mostrarError(err); }
}

async function eliminarHistorial(id) {
    Swal.fire({ title: '¿Eliminar registro?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' })
        .then(async (res) => {
            if (!res.isConfirmed) return;
            try {
                await apiSend(`/historial/${id}`, 'DELETE');
                await renderHistorial();
                Swal.fire('Eliminado', 'Registro eliminado del historial', 'success');
            } catch (err) { mostrarError(err); }
        });
}

// --- CAJA Y FACTURACIÓN ---
async function renderFacturacion() {
    window.cacheFacturas = await apiGet('/facturacion');
    const tbody = document.querySelector('#tabla-facturacion tbody');
    if (!tbody) return;

    tbody.innerHTML = window.cacheFacturas.length === 0 ?
        '<tr><td colspan="8" class="text-center text-muted py-3">No hay comprobantes emitidos</td></tr>' :
        window.cacheFacturas.map(f => `
            <tr>
                <td>${f.id}</td>
                <td class="fw-semibold">${f.paciente || 'Cliente Varios'}</td>
                <td><strong>${f.tipo} ${f.serie}-${f.correlativo}</strong></td>
                <td class="text-success fw-bold">S/ ${parseFloat(f.monto || 0).toFixed(2)}</td>
                <td>${f.metodo}</td>
                <td><span class="badge bg-${f.estado === 'Anulado' ? 'danger' : 'success'}">${f.estado}</span></td>
                <td>${f.fecha || '-'}</td>
                <td class="text-center">
                    <a href="/api/facturacion/${f.id}/pdf" target="_blank" class="btn btn-sm btn-outline-primary me-1" title="Descargar PDF"><i class="bi bi-file-pdf"></i></a>
                    ${f.estado !== 'Anulado' ? `<button class="btn btn-sm btn-outline-danger" onclick="eliminarFactura(${f.id})" title="Anular"><i class="bi bi-x-circle"></i></button>` : ''}
                </td>
            </tr>
        `).join('');
}

function abrirModalFacturacion() {
    actualizarSelectsDependientes();
    const form = document.getElementById('form-facturacion');
    if (form) form.reset();
    document.getElementById('f-id').value = '';
    document.getElementById('f-serie').value = 'B001';
    abrirModal('modalFacturacion');
}

async function guardarFacturacion(e) {
    if (e && e.preventDefault) e.preventDefault();
    const id = document.getElementById('f-id').value;
    const payload = {
        id: id ? parseInt(id) : null,
        paciente_id: parseInt(document.getElementById('f-paciente').value),
        tipo: document.getElementById('f-tipo').value,
        serie: document.getElementById('f-serie').value.trim(),
        correlativo: document.getElementById('f-correlativo').value.trim(),
        monto: parseFloat(document.getElementById('f-monto').value),
        metodo: document.getElementById('f-metodo').value
    };

    try {
        await apiSend('/facturacion', 'POST', payload);
        cerrarModal('modalFacturacion');
        await renderFacturacion();
        await actualizarDashboard();
        Swal.fire('Guardado', 'Comprobante emitido correctamente', 'success');
    } catch (err) { mostrarError(err); }
}

async function eliminarFactura(id) {
    Swal.fire({ title: '¿Anular comprobante?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, anular' })
        .then(async (res) => {
            if (!res.isConfirmed) return;
            try {
                await apiSend(`/facturacion/${id}`, 'DELETE');
                await renderFacturacion();
                await actualizarDashboard();
                Swal.fire('Anulado', 'Comprobante anulado', 'success');
            } catch (err) { mostrarError(err); }
        });
}

// --- FARMACIA ---
async function renderFarmacia() {
    window.cacheFarmacia = await apiGet('/farmacia');
    const tbody = document.querySelector('#tabla-farmacia tbody');
    if (!tbody) return;

    tbody.innerHTML = window.cacheFarmacia.length === 0 ?
        '<tr><td colspan="7" class="text-center text-muted py-3">No hay productos en inventario</td></tr>' :
        window.cacheFarmacia.map(f => `
            <tr>
                <td>${f.id}</td>
                <td><code>${f.codigo || '-'}</code></td>
                <td class="fw-semibold">${f.nombre}</td>
                <td>${f.tipo || '-'}</td>
                <td><span class="badge bg-${f.stock < 10 ? 'danger' : 'success'}">${f.stock}</span></td>
                <td>S/ ${parseFloat(f.precio || 0).toFixed(2)}</td>
                <td class="text-center">
                    <button class="btn btn-sm btn-outline-warning me-1" onclick="editarFarmacia(${f.id})"><i class="bi bi-pencil"></i></button>
                    <button class="btn btn-sm btn-outline-danger" onclick="eliminarFarmacia(${f.id})"><i class="bi bi-trash"></i></button>
                </td>
            </tr>
        `).join('');
}

function abrirModalFarmacia(esEdicion = false) {
    if (!esEdicion) {
        const form = document.getElementById('form-farmacia');
        if (form) form.reset();
        document.getElementById('far-id').value = '';
    }
    abrirModal('modalFarmacia');
}

function editarFarmacia(id) {
    const f = window.cacheFarmacia.find(x => x.id === id);
    if (!f) return;
    abrirModalFarmacia(true);
    document.getElementById('far-id').value = f.id;
    document.getElementById('far-codigo').value = f.codigo || '';
    document.getElementById('far-nombre').value = f.nombre || '';
    document.getElementById('far-tipo').value = f.tipo || '';
    document.getElementById('far-stock').value = f.stock || 0;
    document.getElementById('far-precio').value = f.precio || 0;
    document.getElementById('far-vencimiento').value = f.vencimiento || '';
}

async function guardarFarmacia(e) {
    if (e && e.preventDefault) e.preventDefault();
    const id = document.getElementById('far-id').value;
    const payload = {
        id: id ? parseInt(id) : null,
        codigo: document.getElementById('far-codigo').value.trim(),
        nombre: document.getElementById('far-nombre').value.trim(),
        tipo: document.getElementById('far-tipo').value.trim(),
        stock: parseInt(document.getElementById('far-stock').value),
        precio: parseFloat(document.getElementById('far-precio').value),
        vencimiento: document.getElementById('far-vencimiento').value
    };

    try {
        await apiSend('/farmacia', 'POST', payload);
        cerrarModal('modalFarmacia');
        await renderFarmacia();
        Swal.fire('Guardado', 'Medicamento guardado en inventario', 'success');
    } catch (err) { mostrarError(err); }
}

async function eliminarFarmacia(id) {
    Swal.fire({ title: '¿Eliminar producto?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' })
        .then(async (res) => {
            if (!res.isConfirmed) return;
            try {
                await apiSend(`/farmacia/${id}`, 'DELETE');
                await renderFarmacia();
                Swal.fire('Eliminado', 'Producto eliminado', 'success');
            } catch (err) { mostrarError(err); }
        });
}

// --- LABORATORIO ---
async function renderLaboratorio() {
    window.cacheLaboratorio = await apiGet('/laboratorio');
    const tbody = document.querySelector('#tabla-laboratorio tbody');
    if (!tbody) return;

    tbody.innerHTML = window.cacheLaboratorio.length === 0 ?
        '<tr><td colspan="6" class="text-center text-muted py-3">No hay órdenes de laboratorio</td></tr>' :
        window.cacheLaboratorio.map(l => `
            <tr>
                <td>${l.id}</td>
                <td class="fw-semibold">${l.paciente || 'N/A'}</td>
                <td><strong>${l.examen}</strong></td>
                <td><span class="badge bg-${l.estado === 'Completado' ? 'success' : l.estado === 'En Proceso' ? 'info text-dark' : 'warning text-dark'}">${l.estado}</span></td>
                <td>${l.resultado || 'En espera'}</td>
                <td class="text-center">
                    <button class="btn btn-sm btn-outline-warning me-1" onclick="editarLaboratorio(${l.id})"><i class="bi bi-pencil"></i></button>
                    <button class="btn btn-sm btn-outline-danger" onclick="eliminarLaboratorio(${l.id})"><i class="bi bi-trash"></i></button>
                </td>
            </tr>
        `).join('');
}

function abrirModalLaboratorio(esEdicion = false) {
    actualizarSelectsDependientes();
    if (!esEdicion) {
        const form = document.getElementById('form-laboratorio');
        if (form) form.reset();
        document.getElementById('lab-id').value = '';
    }
    abrirModal('modalLaboratorio');
}

function editarLaboratorio(id) {
    const l = window.cacheLaboratorio.find(x => x.id === id);
    if (!l) return;
    abrirModalLaboratorio(true);
    document.getElementById('lab-id').value = l.id;
    document.getElementById('lab-paciente').value = l.paciente_id;
    document.getElementById('lab-medico').value = l.medico_id;
    document.getElementById('lab-examen').value = l.examen || '';
    document.getElementById('lab-estado').value = l.estado || 'Pendiente';
    document.getElementById('lab-resultado').value = l.resultado || '';
}

async function guardarLaboratorio(e) {
    if (e && e.preventDefault) e.preventDefault();
    const id = document.getElementById('lab-id').value;
    const payload = {
        id: id ? parseInt(id) : null,
        paciente_id: parseInt(document.getElementById('lab-paciente').value),
        medico_id: parseInt(document.getElementById('lab-medico').value),
        examen: document.getElementById('lab-examen').value.trim(),
        estado: document.getElementById('lab-estado').value,
        resultado: document.getElementById('lab-resultado').value.trim()
    };

    try {
        await apiSend('/laboratorio', 'POST', payload);
        cerrarModal('modalLaboratorio');
        await renderLaboratorio();
        Swal.fire('Guardado', 'Orden de laboratorio guardada', 'success');
    } catch (err) { mostrarError(err); }
}

async function eliminarLaboratorio(id) {
    Swal.fire({ title: '¿Eliminar orden?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' })
        .then(async (res) => {
            if (!res.isConfirmed) return;
            try {
                await apiSend(`/laboratorio/${id}`, 'DELETE');
                await renderLaboratorio();
                Swal.fire('Eliminado', 'Orden eliminada', 'success');
            } catch (err) { mostrarError(err); }
        });
}

// --- HOSPITALIZACIÓN ---
async function renderHospitalizacion() {
    window.cacheHospitalizaciones = await apiGet('/hospitalizacion');
    const tbody = document.querySelector('#tabla-hospitalizacion tbody');
    if (!tbody) return;

    tbody.innerHTML = window.cacheHospitalizaciones.length === 0 ?
        '<tr><td colspan="6" class="text-center text-muted py-3">No hay pacientes hospitalizados</td></tr>' :
        window.cacheHospitalizaciones.map(h => `
            <tr>
                <td>${h.id}</td>
                <td class="fw-semibold">${h.paciente || 'N/A'}</td>
                <td><span class="badge bg-info text-dark">${h.cama || '-'}</span></td>
                <td>${h.medico || 'N/A'}</td>
                <td><span class="badge bg-${h.estado === 'Activo' ? 'primary' : 'success'}">${h.estado}</span></td>
                <td class="text-center">
                    ${h.estado === 'Activo' ? `<button class="btn btn-sm btn-outline-success me-1" onclick="darAlta(${h.id})" title="Dar de alta"><i class="bi bi-box-arrow-right"></i> Alta</button>` : ''}
                    <button class="btn btn-sm btn-outline-danger" onclick="eliminarHospitalizacion(${h.id})"><i class="bi bi-trash"></i></button>
                </td>
            </tr>
        `).join('');
}

async function abrirModalHospitalizacion() {
    actualizarSelectsDependientes();
    await cargarCamasDisponibles();
    const form = document.getElementById('form-hospitalizacion');
    if (form) form.reset();
    document.getElementById('hosp-id').value = '';
    abrirModal('modalHospitalizacion');
}

async function guardarHospitalizacion(e) {
    if (e && e.preventDefault) e.preventDefault();
    const id = document.getElementById('hosp-id').value;
    const payload = {
        id: id ? parseInt(id) : null,
        paciente_id: parseInt(document.getElementById('hosp-paciente').value),
        medico_id: parseInt(document.getElementById('hosp-medico').value),
        cama_id: parseInt(document.getElementById('hosp-cama').value),
        diag: document.getElementById('hosp-diag').value.trim()
    };

    try {
        await apiSend('/hospitalizacion', 'POST', payload);
        cerrarModal('modalHospitalizacion');
        await renderHospitalizacion();
        await actualizarDashboard();
        Swal.fire('Guardado', 'Paciente hospitalizado y cama asignada', 'success');
    } catch (err) { mostrarError(err); }
}

async function darAlta(id) {
    Swal.fire({
        title: '¿Dar de alta al paciente?', text: 'La cama quedará libre nuevamente', icon: 'question',
        showCancelButton: true, confirmButtonText: 'Sí, dar de alta'
    }).then(async (res) => {
        if (!res.isConfirmed) return;
        try {
            await apiSend(`/hospitalizacion/${id}/alta`, 'POST');
            await renderHospitalizacion();
            Swal.fire('Completado', 'Paciente dado de alta, cama liberada', 'success');
        } catch (err) { mostrarError(err); }
    });
}

async function eliminarHospitalizacion(id) {
    Swal.fire({ title: '¿Eliminar registro?', icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, eliminar' })
        .then(async (res) => {
            if (!res.isConfirmed) return;
            try {
                await apiSend(`/hospitalizacion/${id}`, 'DELETE');
                await renderHospitalizacion();
                Swal.fire('Eliminado', 'Registro de hospitalización eliminado', 'success');
            } catch (err) { mostrarError(err); }
        });
}

// --- NOTIFICACIONES (EMAIL + WHATSAPP) ---
async function renderNotificaciones() {
    window.cacheNotificaciones = await apiGet('/notificaciones');
    const tbody = document.querySelector('#tabla-notificaciones tbody');
    if (!tbody) return;

    tbody.innerHTML = window.cacheNotificaciones.length === 0 ?
        '<tr><td colspan="8" class="text-center text-muted py-3">No hay notificaciones enviadas</td></tr>' :
        window.cacheNotificaciones.map(n => {
            let badgeCanal = '<span class="badge bg-primary"><i class="bi bi-envelope"></i> Email</span>';
            if (n.tipo === 'WhatsApp') {
                badgeCanal = '<span class="badge bg-success"><i class="bi bi-whatsapp"></i> WhatsApp</span>';
            } else if (n.tipo === 'Ambos') {
                badgeCanal = '<span class="badge bg-dark"><i class="bi bi-envelope"></i> + <i class="bi bi-whatsapp"></i> Ambos</span>';
            }

            return `
                <tr>
                    <td>${n.id}</td>
                    <td>${badgeCanal}</td>
                    <td>${n.email || n.telefono || 'N/A'}</td>
                    <td class="fw-bold">${n.asunto}</td>
                    <td><small class="text-secondary">${n.mensaje}</small></td>
                    <td><span class="badge bg-success">Enviado</span></td>
                    <td><small>${n.fecha || ''}</small></td>
                    <td class="text-center">
                        <button class="btn btn-sm btn-outline-warning me-1" onclick="abrirModalEditarNotificacion(${n.id})" title="Editar"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-sm btn-outline-danger" onclick="eliminarNotificacion(${n.id})" title="Eliminar"><i class="bi bi-trash"></i></button>
                    </td>
                </tr>
            `;
        }).join('');
}

function cambiarCanalNotificacion() {
    const canalEl = document.getElementById('n-canal');
    if (!canalEl) return;
    const canal = canalEl.value;
    const groupEmail = document.getElementById('group-email');
    const groupTel = document.getElementById('group-telefono');

    if (canal === 'Email') {
        if (groupEmail) groupEmail.classList.remove('d-none');
        if (groupTel) groupTel.classList.add('d-none');
    } else if (canal === 'WhatsApp') {
        if (groupEmail) groupEmail.classList.add('d-none');
        if (groupTel) groupTel.classList.remove('d-none');
    } else {
        if (groupEmail) groupEmail.classList.remove('d-none');
        if (groupTel) groupTel.classList.remove('d-none');
    }
}

function abrirModalNotificacion() {
    const form = document.getElementById('form-notificacion');
    if (form) form.reset();
    cambiarCanalNotificacion();
    abrirModal('modalNotificacion');
}

function abrirModalEditarNotificacion(id) {
    const notif = window.cacheNotificaciones.find(n => n.id === id);
    if (!notif) return;

    document.getElementById('edit-n-id').value = notif.id;
    document.getElementById('edit-n-asunto').value = notif.asunto || '';
    document.getElementById('edit-n-mensaje').value = notif.mensaje || '';

    abrirModal('modalEditarNotificacion');
}

async function guardarNotificacion(e) {
    if (e && e.preventDefault) e.preventDefault();
    const payload = {
        canal: document.getElementById('n-canal').value,
        email: document.getElementById('n-destinatario') ? document.getElementById('n-destinatario').value.trim() : '',
        telefono: document.getElementById('n-telefono') ? document.getElementById('n-telefono').value.trim() : '',
        asunto: document.getElementById('n-asunto').value.trim(),
        mensaje: document.getElementById('n-mensaje').value.trim()
    };

    try {
        const res = await apiSend('/notificaciones', 'POST', payload);
        if (res.whatsapp_url) {
            window.open(res.whatsapp_url, '_blank');
        }
        cerrarModal('modalNotificacion');
        await renderNotificaciones();

        if (res.error) {
            Swal.fire('Atención', `Registrado con advertencia: ${res.error}`, 'warning');
        } else {
            Swal.fire('Enviado', 'Notificación procesada y enviada correctamente', 'success');
        }
    } catch (err) { mostrarError(err); }
}

async function guardarEdicionNotificacion(e) {
    if (e && e.preventDefault) e.preventDefault();
    const id = document.getElementById('edit-n-id').value;
    const payload = {
        asunto: document.getElementById('edit-n-asunto').value.trim(),
        mensaje: document.getElementById('edit-n-mensaje').value.trim()
    };

    try {
        await apiSend(`/notificaciones/${id}`, 'PUT', payload);
        cerrarModal('modalEditarNotificacion');
        await renderNotificaciones();
        Swal.fire('Actualizado', 'Notificación modificada correctamente', 'success');
    } catch (err) { mostrarError(err); }
}

async function eliminarNotificacion(id) {
    Swal.fire({
        title: '¿Eliminar notificación?', text: 'Se borrará permanentemente', icon: 'warning',
        showCancelButton: true, confirmButtonText: 'Sí, eliminar'
    }).then(async (res) => {
        if (!res.isConfirmed) return;
        try {
            await apiSend(`/notificaciones/${id}`, 'DELETE');
            await renderNotificaciones();
            Swal.fire('Eliminada', 'Notificación eliminada correctamente', 'success');
        } catch (err) { mostrarError(err); }
    });
}

// ==========================================
// 6. ENLAZADO DE EVENTOS SUBMIT DE FORMULARIOS
// ==========================================
function inicializarFormularios() {
    const bindSubmit = (id, fn) => {
        const el = document.getElementById(id);
        if (el) {
            el.removeEventListener('submit', fn);
            el.addEventListener('submit', fn);
        }
    };

    bindSubmit('form-paciente', guardarPaciente);
    bindSubmit('form-medico', guardarMedico);
    bindSubmit('form-cita', guardarCita);
    bindSubmit('form-triaje', guardarTriaje);
    bindSubmit('form-historial', guardarHistorial);
    bindSubmit('form-facturacion', guardarFacturacion);
    bindSubmit('form-farmacia', guardarFarmacia);
    bindSubmit('form-laboratorio', guardarLaboratorio);
    bindSubmit('form-hospitalizacion', guardarHospitalizacion);
    bindSubmit('form-notificacion', guardarNotificacion);
    bindSubmit('form-editar-notificacion', guardarEdicionNotificacion);
}

// ==========================================
// 7. EXPOSICIÓN GLOBAL A WINDOW
// ==========================================
window.mostrarSeccion = mostrarSeccion;
window.abrirModal = abrirModal;
window.cerrarModal = cerrarModal;
window.buscarDniReniec = buscarDniReniec;
window.buscarDniReniecMedico = buscarDniReniecMedico;

// Pacientes
window.renderPacientes = renderPacientes;
window.abrirModalPaciente = abrirModalPaciente;
window.editarPaciente = editarPaciente;
window.guardarPaciente = guardarPaciente;
window.eliminarPaciente = eliminarPaciente;

// Médicos
window.renderMedicos = renderMedicos;
window.abrirModalMedico = abrirModalMedico;
window.editarMedico = editarMedico;
window.guardarMedico = guardarMedico;
window.eliminarMedico = eliminarMedico;

// Citas
window.renderCitas = renderCitas;
window.abrirModalCita = abrirModalCita;
window.editarCita = editarCita;
window.guardarCita = guardarCita;
window.eliminarCita = eliminarCita;

// Triaje
window.renderTriaje = renderTriaje;
window.abrirModalTriaje = abrirModalTriaje;
window.editarTriaje = editarTriaje;
window.guardarTriaje = guardarTriaje;
window.eliminarTriaje = eliminarTriaje;

// Historial
window.renderHistorial = renderHistorial;
window.abrirModalHistorial = abrirModalHistorial;
window.editarHistorial = editarHistorial;
window.guardarHistorial = guardarHistorial;
window.eliminarHistorial = eliminarHistorial;

// Facturación
window.renderFacturacion = renderFacturacion;
window.abrirModalFacturacion = abrirModalFacturacion;
window.guardarFacturacion = guardarFacturacion;
window.eliminarFactura = eliminarFactura;

// Farmacia
window.renderFarmacia = renderFarmacia;
window.abrirModalFarmacia = abrirModalFarmacia;
window.editarFarmacia = editarFarmacia;
window.guardarFarmacia = guardarFarmacia;
window.eliminarFarmacia = eliminarFarmacia;

// Laboratorio
window.renderLaboratorio = renderLaboratorio;
window.abrirModalLaboratorio = abrirModalLaboratorio;
window.editarLaboratorio = editarLaboratorio;
window.guardarLaboratorio = guardarLaboratorio;
window.eliminarLaboratorio = eliminarLaboratorio;

// Hospitalización
window.renderHospitalizacion = renderHospitalizacion;
window.abrirModalHospitalizacion = abrirModalHospitalizacion;
window.guardarHospitalizacion = guardarHospitalizacion;
window.darAlta = darAlta;
window.eliminarHospitalizacion = eliminarHospitalizacion;

// Notificaciones
window.renderNotificaciones = renderNotificaciones;
window.cambiarCanalNotificacion = cambiarCanalNotificacion;
window.abrirModalNotificacion = abrirModalNotificacion;
window.abrirModalEditarNotificacion = abrirModalEditarNotificacion;
window.guardarNotificacion = guardarNotificacion;
window.guardarEdicionNotificacion = guardarEdicionNotificacion;
window.eliminarNotificacion = eliminarNotificacion;