/**
 * mapa.js
 * Mapa del Dashboard (Leaflet + OpenStreetMap) y geocodificación de direcciones
 * usando la API pública y gratuita de Nominatim (OpenStreetMap), sin necesidad de API key.
 */

let mapaDashboard = null;
let capaMarcadores = null;

// Coordenadas por defecto: Ica, Perú (ajusta según la ciudad de tu hospital)
const COORD_DEFECTO = { lat: -14.0678, lng: -75.7286 };

function inicializarMapaDashboard() {
    const contenedor = document.getElementById('mapa-dashboard');
    if (!contenedor || mapaDashboard) return;

    mapaDashboard = L.map('mapa-dashboard').setView([COORD_DEFECTO.lat, COORD_DEFECTO.lng], 13);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(mapaDashboard);

    capaMarcadores = L.layerGroup().addTo(mapaDashboard);
}

/**
 * Pinta en el mapa todos los pacientes que tengan latitud/longitud guardadas.
 */
function actualizarMarcadoresPacientes(listaPacientes) {
    if (!mapaDashboard || !capaMarcadores) return;
    capaMarcadores.clearLayers();

    const conUbicacion = (listaPacientes || []).filter(p => p.latitud && p.longitud);

    if (conUbicacion.length === 0) return;

    const puntos = [];
    conUbicacion.forEach(p => {
        const marker = L.marker([p.latitud, p.longitud]).addTo(capaMarcadores);
        marker.bindPopup(`<strong>${p.nombre} ${p.apellido}</strong><br>DNI: ${p.dni}<br>${p.direccion || ''}`);
        puntos.push([p.latitud, p.longitud]);
    });

    if (puntos.length > 0) {
        mapaDashboard.fitBounds(puntos, { padding: [40, 40], maxZoom: 15 });
    }
}

/**
 * Geocodifica una dirección de texto a coordenadas usando Nominatim (OpenStreetMap).
 * API gratuita: https://nominatim.org/release-docs/latest/api/Search/
 */
async function geocodificarDireccion(texto) {
    if (!texto || texto.trim().length < 4) return [];
    try {
        const url = `https://nominatim.openstreetmap.org/search?format=json&limit=5&addressdetails=1&q=${encodeURIComponent(texto)}`;
        const res = await fetch(url, { headers: { 'Accept-Language': 'es' } });
        if (!res.ok) return [];
        return await res.json();
    } catch (e) {
        console.error('Error geocodificando dirección:', e);
        return [];
    }
}

/**
 * Conecta un input de dirección con un autocompletado que usa Nominatim,
 * y guarda lat/lng en los inputs ocultos indicados al seleccionar una opción.
 */
function activarAutocompleteDireccion(inputId, listaId, latId, lngId) {
    const input = document.getElementById(inputId);
    const lista = document.getElementById(listaId);
    if (!input || !lista) return;

    let timeoutId = null;

    input.addEventListener('input', () => {
        clearTimeout(timeoutId);
        const valor = input.value;
        timeoutId = setTimeout(async () => {
            const resultados = await geocodificarDireccion(valor);
            if (resultados.length === 0) {
                lista.classList.add('d-none');
                lista.innerHTML = '';
                return;
            }
            lista.innerHTML = resultados.map(r =>
                `<div data-lat="${r.lat}" data-lng="${r.lon}" data-label="${r.display_name.replace(/"/g, '&quot;')}">${r.display_name}</div>`
            ).join('');
            lista.classList.remove('d-none');
        }, 500); // debounce para no saturar la API gratuita
    });

    lista.addEventListener('click', (e) => {
        const item = e.target.closest('div[data-lat]');
        if (!item) return;
        input.value = item.getAttribute('data-label');
        document.getElementById(latId).value = item.getAttribute('data-lat');
        document.getElementById(lngId).value = item.getAttribute('data-lng');
        lista.classList.add('d-none');
        lista.innerHTML = '';
    });

    document.addEventListener('click', (e) => {
        if (!lista.contains(e.target) && e.target !== input) {
            lista.classList.add('d-none');
        }
    });
}
