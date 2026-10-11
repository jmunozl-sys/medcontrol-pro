/**
 * ml_dashboard.js
 * Dashboard de IA de MedControl Pro.
 * Sincronización automática de métricas, matriz de confusión y predicciones en tiempo real.
 */
(function () {
    'use strict';

    // Helpers seguros de selección y manipulación del DOM
    const $ = (id) => document.getElementById(id);
    const setTxt = (id, txt) => { const el = $(id); if (el) el.textContent = txt; };
    const setHTML = (id, html) => { const el = $(id); if (el) el.innerHTML = html; };
    const toggleClass = (id, cls, state) => { const el = $(id); if (el) el.classList.toggle(cls, state); };

    const POLL_MS = 5000; // Refresco automático cada 5 segundos
    const SIM_MS = 2000;

    let fuente = 'vivo';
    let origen = 'todos';
    let ultimoIdPred = null;       // ID de predicción recién realizada
    let timerPoll = null, timerSim = null;
    let cargando = false;
    let eligioFuenteManual = false;
    let previo = {};

    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const pct = (v) => (v === null || v === undefined) ? '—' : (v * 100).toFixed(1) + '%';

    async function api(path, opciones) {
        let res;
        try { 
            res = await fetch(path, opciones); 
        } catch (e) { 
            throw new Error('No se pudo conectar con el servidor. ¿Está Flask en ejecución?'); 
        }
        
        let data = null;
        try { 
            data = await res.json(); 
        } catch (e) { 
            throw new Error('Respuesta inválida del servidor (HTTP ' + res.status + ').'); 
        }
        
        if (!res.ok) { 
            const err = new Error(data.error || 'Error del servidor'); 
            err.detalles = data.detalles; 
            throw err; 
        }
        return data;
    }

    function marcarVivo(ok, texto) {
        toggleClass('live-dot', 'off', !ok);
        setTxt('estado-live', texto);
    }

    // ------------------------------------------------------------------
    // Matriz de Confusión y Métricas
    // ------------------------------------------------------------------
    function pintarMatriz(d) {
        if (!d) return;

        const celdas = { tn: d.tn || 0, fp: d.fp || 0, fn: d.fn || 0, tp: d.tp || 0 };
        const filaBajo = celdas.tn + celdas.fp;
        const filaAlto = celdas.fn + celdas.tp;
        const denom = { tn: filaBajo, fp: filaBajo, fn: filaAlto, tp: filaAlto };

        Object.keys(celdas).forEach((k) => {
            const n = $('c-' + k);
            if (n) {
                if (previo[k] !== undefined && previo[k] !== celdas[k]) {
                    const td = n.closest('td');
                    if (td) {
                        td.classList.remove('flash'); 
                        void td.offsetWidth; 
                        td.classList.add('flash');
                    }
                }
                n.textContent = celdas[k];
            }
            setTxt('p-' + k, denom[k] ? ((celdas[k] / denom[k]) * 100).toFixed(1) + '%' : '');
        });

        previo = { ...celdas };
        toggleClass('cm', 'vacio', d.confirmados === 0);

        const m = d.metricas || {};
        setTxt('m-accuracy', pct(m.accuracy));
        setTxt('m-precision', pct(m.precision));
        setTxt('m-recall', pct(m.recall));
        setTxt('m-f1', pct(m.f1_score || m.f1));

        const badgeFuente = $('badge-fuente');
        if (badgeFuente) {
            badgeFuente.textContent = d.fuente === 'vivo' ? 'EN VIVO' : 'VALIDACIÓN';
            badgeFuente.className = 'badge fw-normal ' + (d.fuente === 'vivo' ? 'bg-danger' : 'bg-secondary');
        }

        let detalle = d.detalle || '';
        if (d.fuente === 'vivo' && d.confirmados === 0) {
            detalle = 'Aún no hay predicciones con resultado real confirmado. Haz una predicción y confirma qué ocurrió, o activa la simulación.';
        }
        setTxt('detalle-matriz', detalle);

        toggleClass('filtro-origen-box', 'd-none', d.fuente !== 'vivo');

        const textoResumen = d.fuente === 'vivo'
            ? `Guardadas: <strong>${d.total || 0}</strong> · Confirmadas: <strong>${d.confirmados || 0}</strong> · Pendientes: <strong>${d.pendientes || 0}</strong>`
            : 'Mostrando la validación del entrenamiento.';
        setHTML('resumen-conteo', textoResumen);

        marcarVivo(true, (d.fuente === 'vivo' ? 'Actualización automática cada 5 s · ' : '') + 'última: ' + (d.actualizado || ''));
    }

    async function cargarMatriz() {
        if (cargando) return;
        cargando = true;
        try {
            const q = new URLSearchParams({ fuente });
            if (fuente === 'vivo' && origen !== 'todos') q.set('origen', origen);
            
            const d = await api('/ml/api/matriz?' + q.toString());
            setHTML('aviso-global', '');

            // Si es la primera carga y no hay confirmaciones en vivo, mostrar la validación por defecto
            if (fuente === 'vivo' && d.confirmados === 0 && !eligioFuenteManual && !cargarMatriz.yaCambio) {
                cargarMatriz.yaCambio = true;
                const radioVal = $('fuente-validacion');
                if (radioVal) radioVal.checked = true;
                fuente = 'validacion';
                cargando = false;
                return cargarMatriz();
            }

            pintarMatriz(d);
        } catch (e) {
            marcarVivo(false, 'Sin conexión');
            setHTML('aviso-global', `<div class="alert alert-warning small"><i class="bi bi-exclamation-triangle"></i> ${esc(e.message)}</div>`);
        } finally {
            cargando = false;
        }
    }

    // ------------------------------------------------------------------
    // Historial y Tabla de Predicciones
    // ------------------------------------------------------------------
    function badgeEstado(p) {
        if (p.resultado_real === null || p.resultado_real === undefined) {
            return '<span class="badge bg-secondary">Pendiente</span>';
        }
        return p.resultado_real === p.riesgo_predicho
            ? '<span class="badge bg-success">Acierto</span>' 
            : '<span class="badge bg-danger">Error</span>';
    }

    async function cargarPredicciones() {
        const tb = $('tabla-predicciones') || document.querySelector('#tabla-pred tbody');
        const badgeTotal = $('badge-total-predicciones');
        if (!tb) return;

        try {
            const q = new URLSearchParams({ limite: 12 });
            if (origen !== 'todos' && fuente === 'vivo') q.set('origen', origen);

            const r = await api('/ml/api/predicciones?' + q.toString());
            const lista = r.predicciones || [];

            if (badgeTotal) badgeTotal.textContent = `${lista.length} registros`;

            if (!lista.length) {
                tb.innerHTML = '<tr><td colspan="8" class="text-muted text-center py-3">Aún no hay predicciones guardadas.</td></tr>';
                return;
            }

            tb.innerHTML = lista.map((p) => {
                const real = (p.resultado_real === null || p.resultado_real === undefined)
                    ? `<div class="btn-group btn-group-sm">
                           <button class="btn btn-outline-danger py-0 btn-sm" data-real="1" data-id="${p.id}" title="Reingresó"><i class="bi bi-x-lg"></i> Reingresó</button>
                           <button class="btn btn-outline-success py-0 btn-sm" data-real="0" data-id="${p.id}" title="No reingresó"><i class="bi bi-check-lg"></i> No reingresó</button>
                       </div>`
                    : (p.resultado_real === 1 
                        ? '<span class="badge bg-danger"><i class="bi bi-exclamation-triangle-fill me-1"></i>Reingresó</span>' 
                        : '<span class="badge bg-success"><i class="bi bi-check-circle-fill me-1"></i>No reingresó</span>');

                const probVal = typeof p.probabilidad === 'number' 
                    ? (p.probabilidad > 1 ? p.probabilidad : p.probabilidad * 100).toFixed(1) 
                    : '0.0';

                return `<tr>
                    <td><strong>#${p.id}</strong></td>
                    <td><small class="text-muted">${esc(p.fecha)}</small></td>
                    <td>
                        ${p.paciente_nombre ? esc(p.paciente_nombre) : '<span class="text-muted">Manual</span>'}
                        ${p.origen === 'simulacion' ? '<span class="badge bg-warning text-dark ms-1">sim</span>' : ''}
                    </td>
                    <td><span class="badge ${p.riesgo_predicho ? 'bg-danger' : 'bg-success'}">${p.riesgo_predicho ? 'Alto Riesgo' : 'Bajo Riesgo'}</span></td>
                    <td><strong>${probVal}%</strong></td>
                    <td>${real}</td>
                    <td>${badgeEstado(p)}</td>
                </tr>`;
            }).join('');
        } catch (e) {
            tb.innerHTML = `<tr><td colspan="7" class="text-danger text-center py-3">${esc(e.message)}</td></tr>`;
        }
    }

    async function confirmar(id, valor) {
        if (id === null || id === undefined) return;
        try {
            // Intenta el endpoint estándar /ml/api/confirmar/<id>, si no existe usa /ml/api/resultado/<id>
            try {
                await api(`/ml/api/confirmar/${id}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ resultado_real: valor })
                });
            } catch (err) {
                await api(`/ml/api/resultado/${id}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ resultado_real: valor })
                });
            }

            if (id === ultimoIdPred) toggleClass('confirmar-box', 'd-none', true);
            refrescar();
        } catch (e) {
            if (typeof Swal !== 'undefined') Swal.fire('No se pudo confirmar', e.message, 'error');
            else alert('Error: ' + e.message);
        }
    }

    function refrescar() { 
        cargarMatriz(); 
        cargarPredicciones(); 
    }

    // ------------------------------------------------------------------
    // Formulario de Predicción
    // ------------------------------------------------------------------
    const CAMPOS = ['edad', 'presion_sistolica', 'presion_diastolica', 'frecuencia_cardiaca',
        'glucosa', 'temperatura', 'nivel_triaje', 'comorbilidades'];

    async function cargarPacientes() {
        const select = $('paciente_id');
        if (!select) return;

        try {
            let res = await fetch('/api/pacientes');
            if (!res.ok) res = await fetch('/ml/api/pacientes');

            const lista = await res.json();
            const pacientes = Array.isArray(lista) ? lista : (lista.pacientes || []);

            if (pacientes.length === 0) {
                select.innerHTML = '<option value="">— Sin pacientes registrados —</option>';
                return;
            }

            select.innerHTML = '<option value="">— Selección Manual (o elija un paciente) —</option>' +
                pacientes.map((p) => {
                    const nom = `${p.nombre || ''} ${p.apellido || ''}`.trim() || 'Paciente';
                    const dni = p.dni ? ` (DNI: ${esc(p.dni)})` : '';
                    return `<option value="${p.id}">${esc(nom)}${dni}</option>`;
                }).join('');

        } catch (e) {
            setTxt('info-paciente', 'No se pudo cargar la lista de pacientes: ' + e.message);
        }
    }

    // 1. Función auxiliar para parsear fechas de forma segura
function calcularEdadDesdeFecha(fechaStr) {
    if (!fechaStr) return null;
    let nac = null;
    
    if (typeof fechaStr === 'string' && fechaStr.includes('-')) {
        const partes = fechaStr.split('T')[0].split('-');
        if (partes.length === 3) {
            nac = new Date(parseInt(partes[0], 10), parseInt(partes[1], 10) - 1, parseInt(partes[2], 10));
        }
    } else if (typeof fechaStr === 'string' && fechaStr.includes('/')) {
        const partes = fechaStr.split('/');
        if (partes.length === 3) {
            if (partes[0].length === 4) {
                nac = new Date(parseInt(partes[0], 10), parseInt(partes[1], 10) - 1, parseInt(partes[2], 10));
            } else {
                nac = new Date(parseInt(partes[2], 10), parseInt(partes[1], 10) - 1, parseInt(partes[0], 10));
            }
        }
    } else {
        nac = new Date(fechaStr);
    }

    if (!nac || isNaN(nac.getTime())) return null;

    const hoy = new Date();
    let edad = hoy.getFullYear() - nac.getFullYear();
    const m = hoy.getMonth() - nac.getMonth();
    if (m < 0 || (m === 0 && hoy.getDate() < nac.getDate())) {
        edad--;
    }
    return (edad >= 0 && edad <= 120) ? edad : null;
}

// 2. Nueva función alElegirPaciente reemplazada
async function alElegirPaciente() {
    const pidEl = $('paciente_id');
    if (!pidEl) return;

    const id = pidEl.value;
    const info = $('info-paciente');

    if (info) info.className = 'form-text';

    if (!id) { 
        if (info) info.textContent = ''; 
        return; 
    }

    if (info) info.textContent = 'Buscando datos del paciente…';

    try {
        let p = null;

        // Intentar obtener el paciente desde el dataset del <option>
        const optSeleccionada = pidEl.options[pidEl.selectedIndex];
        if (optSeleccionada && optSeleccionada.dataset && optSeleccionada.dataset.paciente) {
            try { p = JSON.parse(optSeleccionada.dataset.paciente); } catch (e) {}
        }

        // Si no estaba en el dataset, consultar la API general de pacientes
        if (!p) {
            const res = await fetch('/api/pacientes');
            if (res.ok) {
                const lista = await res.json();
                const pacientes = Array.isArray(lista) ? lista : (lista.pacientes || []);
                p = pacientes.find(item => String(item.id) === String(id));
            }
        }

        if (p) {
            // Probar todas las posibles variantes de clave de fecha de nacimiento
            const fechaStr = p.fecha_nacimiento || p.fnac || p.fecha_nac || p.f_nac || p.fechaNacimiento;
            const edadCalculada = calcularEdadDesdeFecha(fechaStr);

            const edadInput = $('edad');
            if (edadInput) {
                if (edadCalculada !== null) {
                    edadInput.value = edadCalculada;
                } else if (p.edad && !isNaN(p.edad)) {
                    edadInput.value = p.edad;
                }
            }

            if (info) {
                const nombreCompleto = `${p.nombre || ''} ${p.apellido || ''}`.trim() || 'Paciente seleccionado';
                const msjEdad = (edadCalculada !== null) 
                    ? `Edad calculada automáticamente (${edadCalculada} años).` 
                    : 'Fecha no registrada; ingresa la edad manualmente.';
                info.textContent = `Paciente: ${nombreCompleto}. ${msjEdad}`;
                info.className = 'form-text text-success fw-semibold';
            }
        }
    } catch (e) {
        console.error('Error al autocompletar paciente:', e);
        if (info) {
            info.textContent = 'No se completaron datos automáticos. Puedes ingresarlos manualmente.';
            info.className = 'form-text text-muted';
        }
    }
}
    async function enviarPrediccion(e) {
        if (e && e.preventDefault) e.preventDefault();

        const payload = {};
        CAMPOS.forEach((c) => { 
            const input = $(c);
            payload[c] = (input && input.value !== '') ? parseFloat(input.value) : null; 
        });

        const pidEl = $('paciente_id');
        if (pidEl && pidEl.value) payload.paciente_id = parseInt(pidEl.value, 10);

        const errorBox = $('error-predict');
        const resultBox = $('resultado-predict');
        if (errorBox) errorBox.classList.add('d-none');

        const btn = $('btn-predecir');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Calculando…';
        }

        try {
            let data;
            try {
                data = await api('/ml/api/predecir', {
                    method: 'POST', 
                    headers: { 'Content-Type': 'application/json' }, 
                    body: JSON.stringify(payload)
                });
            } catch (err) {
                data = await api('/ml/predict', {
                    method: 'POST', 
                    headers: { 'Content-Type': 'application/json' }, 
                    body: JSON.stringify(payload)
                });
            }

            if (resultBox) resultBox.classList.remove('d-none');

            const barra = $('barra-probabilidad');
            const etiqueta = $('resultado-etiqueta');
            const prob = data.porcentaje || Math.round((data.probabilidad || 0) > 1 ? data.probabilidad : (data.probabilidad || 0) * 100);
            const esAlto = data.riesgo === 1 || data.riesgo_predicho === 1 || data.prediccion === 1 || prob >= 50;

            if (barra) {
                barra.style.width = prob + '%';
                barra.innerText = prob + '%';
                barra.className = 'progress-bar ' + (esAlto ? 'bg-danger' : 'bg-success');
            }

            if (etiqueta) {
                etiqueta.innerText = data.etiqueta || (esAlto ? 'Alto riesgo de reingreso' : 'Bajo riesgo de reingreso');
                etiqueta.className = 'form-label fw-bold ' + (esAlto ? 'text-danger' : 'text-success');
            }

            if (data.guardado || data.id) {
                ultimoIdPred = data.id;
                toggleClass('confirmar-box', 'd-none', false);
                setTxt('guardado-info', 'Predicción #' + data.id + ' guardada en el historial.');
            }

            refrescar();
        } catch (err) {
            if (errorBox) {
                errorBox.textContent = err.message + (err.detalles ? ' ' + Object.values(err.detalles).join(' ') : '');
                errorBox.classList.remove('d-none');
            } else {
                alert('Error al predecir: ' + err.message);
            }
            if (resultBox) resultBox.classList.add('d-none');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-lightning-charge me-1"></i> Calcular Riesgo';
            }
        }
    }

    // ------------------------------------------------------------------
    // Modo Simulación / Demostración
    // ------------------------------------------------------------------
    async function simular(n) {
        try {
            const d = await api('/ml/api/simular?' + (origen !== 'todos' ? 'origen=' + origen : ''), {
                method: 'POST', 
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cantidad: n })
            });
            if (fuente === 'vivo') pintarMatriz(d.matriz);
            cargarPredicciones();
        } catch (e) {
            detenerSimulacion();
            if (typeof Swal !== 'undefined') Swal.fire('No se pudo simular', e.message, 'error');
        }
    }

    function detenerSimulacion() {
        if (timerSim) {
            clearInterval(timerSim); 
            timerSim = null;
        }
        const sw = $('sw-sim');
        if (sw) sw.checked = false;
    }

    function alCambiarSwitch() {
        const sw = $('sw-sim');
        if (sw && sw.checked) {
            if (fuente !== 'vivo') {
                const radioVivo = $('fuente-vivo');
                if (radioVivo) radioVivo.checked = true;
                fuente = 'vivo'; 
                eligioFuenteManual = true; 
            }
            simular(1);
            timerSim = setInterval(() => simular(1), SIM_MS);
        } else {
            detenerSimulacion();
        }
    }

    async function reiniciarSimulacion() {
        let esConfirmado = false;
        if (typeof Swal !== 'undefined') {
            const res = await Swal.fire({
                title: '¿Borrar la simulación?', 
                text: 'Solo se eliminan las predicciones simuladas. Las de pacientes reales no se alteran.',
                icon: 'warning', 
                showCancelButton: true, 
                confirmButtonText: 'Sí, borrar'
            });
            esConfirmado = res.isConfirmed;
        } else {
            esConfirmado = confirm('¿Borrar las predicciones simuladas?');
        }

        if (!esConfirmado) return;

        try {
            detenerSimulacion();
            const r = await api('/ml/api/simulacion/reiniciar', { method: 'POST' });
            if (typeof Swal !== 'undefined') Swal.fire('Listo', (r.eliminados || 0) + ' predicciones simuladas eliminadas.', 'success');
            refrescar();
        } catch (e) { 
            if (typeof Swal !== 'undefined') Swal.fire('Error', e.message, 'error'); 
        }
    }

    // ------------------------------------------------------------------
    // Eventos e Inicialización Única
    // ------------------------------------------------------------------
    function iniciarPolling() {
        if (timerPoll) clearInterval(timerPoll);
        timerPoll = setInterval(() => { 
            if (document.visibilityState === 'visible') refrescar(); 
        }, POLL_MS);
    }

    document.addEventListener('DOMContentLoaded', () => {
        // Radios de Fuente (En Vivo / Validación)
        document.querySelectorAll('input[name="fuente"]').forEach((r) => {
            r.addEventListener('change', () => {
                fuente = r.value; 
                eligioFuenteManual = true; 
                previo = {}; 
                refrescar();
            });
        });

        // Eventos con validación defensiva
        const selectOrigen = $('filtro-origen');
        if (selectOrigen) selectOrigen.addEventListener('change', (e) => { origen = e.target.value; previo = {}; refrescar(); });

        const formPredict = $('form-predict');
        if (formPredict) formPredict.addEventListener('submit', enviarPrediccion);

        const selectPac = $('paciente_id');
        if (selectPac) selectPac.addEventListener('change', alElegirPaciente);

        const btnReal1 = $('btn-real-1');
        if (btnReal1) btnReal1.addEventListener('click', () => ultimoIdPred && confirmar(ultimoIdPred, 1));

        const btnReal0 = $('btn-real-0');
        if (btnReal0) btnReal0.addEventListener('click', () => ultimoIdPred && confirmar(ultimoIdPred, 0));

        const swSim = $('sw-sim');
        if (swSim) swSim.addEventListener('change', alCambiarSwitch);

        const btnSim50 = $('btn-sim-50');
        if (btnSim50) btnSim50.addEventListener('click', () => simular(50));

        const btnSimReset = $('btn-sim-reset');
        if (btnSimReset) btnSimReset.addEventListener('click', reiniciarSimulacion);

        // Delegación de clics en la tabla de predicciones
        const contenedorTabla = $('tabla-predicciones') || document.querySelector('#tabla-pred tbody');
        if (contenedorTabla) {
            contenedorTabla.addEventListener('click', (e) => {
                const b = e.target.closest('button[data-id]');
                if (b) {
                    confirmar(parseInt(b.dataset.id, 10), parseInt(b.dataset.real, 10));
                }
            });
        }

        // Carga inicial
        cargarPacientes();
        refrescar();
        iniciarPolling();
    });
})();