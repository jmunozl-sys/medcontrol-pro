/**
 * ml_dashboard.js
 * Dashboard de IA de MedControl. La matriz de confusión y las métricas se piden al servidor
 * (/ml/api/matriz) y se refrescan solas cada 4 s: salen de las predicciones guardadas en SQL Server
 * y de sus resultados reales confirmados. No hay números fijos en la interfaz.
 */
(function () {
    'use strict';

    const $ = (id) => document.getElementById(id);
    const POLL_MS = 4000;
    const SIM_MS = 2000;

    let fuente = 'vivo';
    let origen = 'todos';
    let ultimoIdPred = null;       // predicción recién hecha en el formulario
    let timerPoll = null, timerSim = null;
    let cargando = false;
    let eligioFuenteManual = false;
    let previo = {};

    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const pct = (v) => (v === null || v === undefined) ? '—' : (v * 100).toFixed(1) + '%';

    async function api(path, opciones) {
        let res;
        try { res = await fetch(path, opciones); }
        catch (e) { throw new Error('No se pudo conectar con el servidor. ¿Está Flask en ejecución?'); }
        let data = null;
        try { data = await res.json(); } catch (e) { throw new Error('Respuesta inválida del servidor (HTTP ' + res.status + ').'); }
        if (!res.ok) { const err = new Error(data.error || 'Error del servidor'); err.detalles = data.detalles; throw err; }
        return data;
    }

    function marcarVivo(ok, texto) {
        $('live-dot').classList.toggle('off', !ok);
        $('estado-live').textContent = texto;
    }

    // ------------------------------------------------------------------
    // Matriz y métricas
    // ------------------------------------------------------------------
    function pintarMatriz(d) {
        const celdas = { tn: d.tn, fp: d.fp, fn: d.fn, tp: d.tp };
        const filaBajo = d.tn + d.fp, filaAlto = d.fn + d.tp;
        const denom = { tn: filaBajo, fp: filaBajo, fn: filaAlto, tp: filaAlto };
        Object.keys(celdas).forEach((k) => {
            const n = $('c-' + k);
            if (previo[k] !== undefined && previo[k] !== celdas[k]) {
                const td = n.closest('td');
                td.classList.remove('flash'); void td.offsetWidth; td.classList.add('flash');
            }
            n.textContent = celdas[k];
            $('p-' + k).textContent = denom[k] ? ((celdas[k] / denom[k]) * 100).toFixed(1) + '%' : '';
        });
        previo = { ...celdas };
        $('cm').classList.toggle('vacio', d.confirmados === 0);

        const m = d.metricas || {};
        $('m-accuracy').textContent = pct(m.accuracy);
        $('m-precision').textContent = pct(m.precision);
        $('m-recall').textContent = pct(m.recall);
        $('m-f1').textContent = pct(m.f1_score);

        $('badge-fuente').textContent = d.fuente === 'vivo' ? 'EN VIVO' : 'VALIDACIÓN';
        $('badge-fuente').className = 'badge fw-normal ' + (d.fuente === 'vivo' ? 'bg-danger' : 'bg-secondary');
        let detalle = d.detalle;
        if (d.fuente === 'vivo' && d.confirmados === 0) {
            detalle = 'Aún no hay predicciones con resultado real confirmado. Haz una predicción y confirma qué ocurrió, o activa el modo demostración.';
        }
        $('detalle-matriz').textContent = detalle;
        $('filtro-origen-box').classList.toggle('d-none', d.fuente !== 'vivo');
        $('resumen-conteo').innerHTML = d.fuente === 'vivo'
            ? `Guardadas: <strong>${d.total}</strong> · Confirmadas: <strong>${d.confirmados}</strong> · Pendientes: <strong>${d.pendientes}</strong>`
            : 'Mostrando la validación del entrenamiento.';
        marcarVivo(true, (d.fuente === 'vivo' ? 'Actualización automática cada 4 s · ' : '') + 'última: ' + (d.actualizado || ''));
    }

    async function cargarMatriz() {
        if (cargando) return;
        cargando = true;
        try {
            const q = new URLSearchParams({ fuente });
            if (fuente === 'vivo' && origen !== 'todos') q.set('origen', origen);
            const d = await api('/ml/api/matriz?' + q.toString());
            $('aviso-global').innerHTML = '';
            // Primera carga: si aún no hay datos en vivo, mostrar la validación para no dejar la pantalla vacía
            if (fuente === 'vivo' && d.confirmados === 0 && !eligioFuenteManual && !cargarMatriz.yaCambio) {
                cargarMatriz.yaCambio = true;
                $('fuente-validacion').checked = true;
                fuente = 'validacion';
                cargando = false;
                return cargarMatriz();
            }
            pintarMatriz(d);
        } catch (e) {
            marcarVivo(false, 'Sin conexión');
            $('aviso-global').innerHTML = `<div class="alert alert-warning small"><i class="bi bi-exclamation-triangle"></i> ${esc(e.message)}</div>`;
        } finally {
            cargando = false;
        }
    }

    // ------------------------------------------------------------------
    // Últimas predicciones
    // ------------------------------------------------------------------
    function badgeEstado(p) {
        if (p.resultado_real === null) return '<span class="badge bg-secondary">Pendiente</span>';
        return p.resultado_real === p.riesgo_predicho
            ? '<span class="badge bg-success">Acierto</span>' : '<span class="badge bg-danger">Error</span>';
    }

    async function cargarPredicciones() {
        const tb = document.querySelector('#tabla-pred tbody');
        try {
            const q = new URLSearchParams({ limite: 12 });
            if (origen !== 'todos' && fuente === 'vivo') q.set('origen', origen);
            const r = await api('/ml/api/predicciones?' + q.toString());
            if (!r.predicciones.length) {
                tb.innerHTML = '<tr><td colspan="8" class="text-muted text-center">Aún no hay predicciones guardadas.</td></tr>';
                return;
            }
            tb.innerHTML = r.predicciones.map((p) => {
                const real = p.resultado_real === null
                    ? `<div class="btn-group btn-group-sm">
                           <button class="btn btn-outline-danger py-0" data-real="1" data-id="${p.id}" title="Reingresó">Sí</button>
                           <button class="btn btn-outline-success py-0" data-real="0" data-id="${p.id}" title="No reingresó">No</button>
                       </div>`
                    : (p.resultado_real ? 'Reingresó' : 'No reingresó');
                return `<tr>
                    <td>${p.id}</td><td>${esc(p.fecha)}</td>
                    <td>${p.paciente_nombre ? esc(p.paciente_nombre) : '<span class="text-muted">Manual</span>'}
                        ${p.origen === 'simulacion' ? '<span class="badge bg-warning text-dark">sim</span>' : ''}</td>
                    <td>${p.edad}</td><td>${(p.probabilidad * 100).toFixed(1)}%</td>
                    <td><span class="badge ${p.riesgo_predicho ? 'bg-danger' : 'bg-success'}">${p.riesgo_predicho ? 'Alto' : 'Bajo'}</span></td>
                    <td>${real}</td><td>${badgeEstado(p)}</td></tr>`;
            }).join('');
        } catch (e) {
            tb.innerHTML = `<tr><td colspan="8" class="text-danger">${esc(e.message)}</td></tr>`;
        }
    }

    async function confirmar(id, valor) {
        try {
            await api('/ml/api/resultado/' + id, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ resultado_real: valor })
            });
            if (id === ultimoIdPred) $('confirmar-box').classList.add('d-none');
            refrescar();
        } catch (e) {
            Swal.fire('No se pudo confirmar', e.message, 'error');
        }
    }

    function refrescar() { cargarMatriz(); cargarPredicciones(); }

    // ------------------------------------------------------------------
    // Formulario de predicción
    // ------------------------------------------------------------------
    const CAMPOS = ['edad', 'presion_sistolica', 'presion_diastolica', 'frecuencia_cardiaca',
        'glucosa', 'temperatura', 'nivel_triaje', 'comorbilidades'];

    async function cargarPacientes() {
        try {
            const lista = await api('/ml/api/pacientes');
            $('paciente_id').innerHTML = '<option value="">— Ingresar datos manualmente —</option>' +
                lista.map((p) => `<option value="${p.id}">${esc(p.nombre)} (${esc(p.dni)})</option>`).join('');
        } catch (e) {
            $('info-paciente').textContent = 'No se pudo cargar la lista de pacientes: ' + e.message;
        }
    }

    async function alElegirPaciente() {
        const id = $('paciente_id').value;
        const info = $('info-paciente');
        info.className = 'form-text';
        if (!id) { info.textContent = ''; return; }
        info.textContent = 'Buscando datos del paciente…';
        try {
            const r = await api('/ml/api/paciente/' + encodeURIComponent(id));
            CAMPOS.forEach((c) => { if (r.datos[c] !== undefined) $(c).value = r.datos[c]; });
            const falta = r.faltantes.map((f) => f.replace('_', ' '));
            info.textContent = 'Datos cargados desde el sistema.' +
                (falta.length ? ' Complete manualmente: ' + falta.join(', ') + '.' : '') +
                ' El nivel de triaje se indica a mano.';
            info.className = 'form-text ' + (falta.length ? 'text-warning' : 'text-success');
        } catch (e) {
            info.textContent = e.message;
            info.className = 'form-text text-danger';
        }
    }

    async function enviarPrediccion(e) {
        e.preventDefault();
        const payload = {};
        CAMPOS.forEach((c) => { payload[c] = $(c).value === '' ? null : parseFloat($(c).value); });
        const pid = $('paciente_id').value;
        if (pid) payload.paciente_id = parseInt(pid, 10);

        const errorBox = $('error-predict'), resultBox = $('resultado-predict');
        errorBox.classList.add('d-none');
        const btn = $('btn-predecir');
        btn.disabled = true;
        try {
            const data = await api('/ml/predict', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
            });
            resultBox.classList.remove('d-none');
            const barra = $('barra-probabilidad'), etiqueta = $('resultado-etiqueta');
            barra.style.width = data.porcentaje + '%';
            barra.innerText = data.porcentaje + '%';
            barra.className = 'progress-bar ' + (data.riesgo === 1 ? 'bg-danger' : 'bg-success');
            etiqueta.innerText = data.etiqueta;
            etiqueta.className = 'form-label fw-bold ' + (data.riesgo === 1 ? 'text-danger' : 'text-success');

            if (data.guardado) {
                ultimoIdPred = data.id;
                $('confirmar-box').classList.remove('d-none');
                $('guardado-info').textContent = 'Predicción #' + data.id + ' guardada en el historial.';
            } else {
                ultimoIdPred = null;
                $('confirmar-box').classList.add('d-none');
                if (data.aviso_guardado) {
                    errorBox.textContent = data.aviso_guardado;
                    errorBox.classList.remove('d-none');
                }
            }
            refrescar();
        } catch (err) {
            errorBox.textContent = err.message + (err.detalles ? ' ' + Object.values(err.detalles).join(' ') : '');
            errorBox.classList.remove('d-none');
            resultBox.classList.add('d-none');
        } finally {
            btn.disabled = false;
        }
    }

    // ------------------------------------------------------------------
    // Modo demostración
    // ------------------------------------------------------------------
    async function simular(n) {
        try {
            const d = await api('/ml/api/simular?' + (origen !== 'todos' ? 'origen=' + origen : ''), {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cantidad: n })
            });
            if (fuente === 'vivo') pintarMatriz(d.matriz);
            cargarPredicciones();
        } catch (e) {
            detenerSimulacion();
            Swal.fire('No se pudo simular', e.message, 'error');
        }
    }

    function detenerSimulacion() {
        clearInterval(timerSim); timerSim = null;
        $('sw-sim').checked = false;
    }

    function alCambiarSwitch() {
        if ($('sw-sim').checked) {
            if (fuente !== 'vivo') { $('fuente-vivo').checked = true; fuente = 'vivo'; eligioFuenteManual = true; }
            simular(1);
            timerSim = setInterval(() => simular(1), SIM_MS);
        } else {
            detenerSimulacion();
        }
    }

    async function reiniciarSimulacion() {
        const ok = await Swal.fire({
            title: '¿Borrar la simulación?', text: 'Solo se eliminan las predicciones simuladas. Las de pacientes reales no se tocan.',
            icon: 'warning', showCancelButton: true, confirmButtonText: 'Sí, borrar'
        });
        if (!ok.isConfirmed) return;
        try {
            detenerSimulacion();
            const r = await api('/ml/api/simulacion/reiniciar', { method: 'POST' });
            Swal.fire('Listo', r.eliminados + ' predicciones simuladas eliminadas.', 'success');
            refrescar();
        } catch (e) { Swal.fire('Error', e.message, 'error'); }
    }

    // ------------------------------------------------------------------
    // Inicio
    // ------------------------------------------------------------------
    function iniciarPolling() {
        clearInterval(timerPoll);
        timerPoll = setInterval(() => { if (document.visibilityState === 'visible') refrescar(); }, POLL_MS);
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (!$('form-predict')) return;
        document.querySelectorAll('input[name="fuente"]').forEach((r) => r.addEventListener('change', () => {
            fuente = r.value; eligioFuenteManual = true; previo = {}; refrescar();
        }));
        $('filtro-origen').addEventListener('change', (e) => { origen = e.target.value; previo = {}; refrescar(); });
        $('form-predict').addEventListener('submit', enviarPrediccion);
        $('paciente_id').addEventListener('change', alElegirPaciente);
        $('btn-real-1').addEventListener('click', () => ultimoIdPred && confirmar(ultimoIdPred, 1));
        $('btn-real-0').addEventListener('click', () => ultimoIdPred && confirmar(ultimoIdPred, 0));
        $('sw-sim').addEventListener('change', alCambiarSwitch);
        $('btn-sim-50').addEventListener('click', () => simular(50));
        $('btn-sim-reset').addEventListener('click', reiniciarSimulacion);
        document.querySelector('#tabla-pred tbody').addEventListener('click', (e) => {
            const b = e.target.closest('button[data-id]');
            if (b) confirmar(parseInt(b.dataset.id, 10), parseInt(b.dataset.real, 10));
        });

        cargarPacientes();
        refrescar();
        iniciarPolling();
    });
})();
