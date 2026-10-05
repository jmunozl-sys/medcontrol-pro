# MedControl Pro / HDAC — con Matriz de Confusión EN VIVO

## Novedad: el módulo de IA ya no es estático

Antes la matriz de confusión era una **imagen PNG fija** creada al entrenar. Ahora el dashboard
(`/ml/dashboard`) la calcula **en cada consulta** desde SQL Server y se refresca sola cada 4 segundos.

**Cómo funciona (una matriz de confusión necesita el resultado REAL, no solo la predicción):**

1. Cada predicción (`POST /ml/predict`) se guarda en la tabla nueva `dbo.ML_Predicciones`
   (puedes elegir un paciente del sistema y se autocompleta con su triaje, laboratorio e historial CIE-10).
2. El resultado real se registra de 3 formas:
   - **Manual:** botones "Reingresó / No reingresó" en el dashboard.
   - **Automática:** si el paciente tiene un nuevo ingreso en `Hospitalizacion` dentro de 30 días de la
     predicción => reingresó (1); si pasan 30 días sin ingreso => no reingresó (0).
   - **Simulación (modo demostración):** pacientes sintéticos NUEVOS, marcados como `simulacion`.
3. La matriz y las métricas (Accuracy, Precision, Recall, F1) se recalculan con las predicciones
   que ya tienen resultado confirmado. Los botones superiores permiten ver:
   - **En vivo** (resultados confirmados; filtrable por Sistema / Simulación), o
   - **Validación del entrenamiento** (conjunto de prueba; datos sintéticos).

> Aviso: el modelo se entrenó con datos **sintéticos**. Las métricas con pacientes simulados no son
> desempeño clínico real; con pocos casos confirmados las métricas en vivo varían bastante.
> "Reingreso" se aproxima como "nuevo ingreso en Hospitalizacion dentro de 30 días".

### Archivos nuevos / modificados
- `ml_utils.py` (nuevo): validación y métricas. `ml_store.py` (nuevo): acceso a SQL Server.
- `blueprint_ml_gpt.py`: nuevos endpoints `/ml/api/...` (matriz, predicciones, resultado, simular, paciente).
- `templates/ml_dashboard.html` + `static/js/ml_dashboard.js`: matriz HTML en vivo.
- `entrenar_modelo.py`: ahora guarda la matriz numérica en `metrics_modelo.json`.
- `app.py`: 2 líneas para que el módulo use TU conexión a SQL Server.
- `schema.sql`: tabla `ML_Predicciones` (la app también la crea sola).
- `templates/index.html`: icono de Laboratorio corregido (`bi-vial` no existe).
- `.env.example` (nuevo). No se agregaron librerías: `requirements.txt` igual.

### Uso rápido
```
python -m pip install -r requirements.txt
python app.py        # abre http://127.0.0.1:5000/ml/dashboard
```
Prueba: activa "Simulación continua" y mira la matriz moverse; o elige un paciente, calcula el riesgo
y confirma qué ocurrió.

---

# MedControl Pro / HDAC — Sistema completo (base + IA + Asistente GPT)

> **Esta versión ya trae integrados los módulos de Machine Learning y
> Asistente Clínico GPT.** El `app.py` ya tiene las 2 líneas de registro
> del Blueprint aplicadas — no necesitas tocar nada para que funcionen.
>
> - `http://127.0.0.1:5000/` → Sistema MedControl (Pacientes, Citas, etc.)
> - `http://127.0.0.1:5000/ml/dashboard` → Panel de IA (riesgo de reingreso)
> - `http://127.0.0.1:5000/gpt/asistente` → Asistente clínico con GPT
>
> El dataset (2,000 registros), el modelo entrenado y la matriz de
> confusión **ya vienen generados** dentro del ZIP. Si quieres
> regenerarlos o re-entrenar con datos nuevos:
> ```bash
> python generar_dataset.py
> python entrenar_modelo.py
> ```
>
> Para el Asistente GPT, copia `.env.example` como `.env` y coloca tu
> clave real de OpenAI en `OPENAI_API_KEY`. Sin esa clave, el resto del
> sistema (incluido el módulo de IA/ML) funciona con total normalidad;
> solo el chat GPT mostrará un aviso pidiendo configurarla.

---

## ⚠️ IMPORTANTE: el Asistente GPT necesita tu clave REAL de OpenAI

Si tu `.env` todavía tiene literalmente esta línea:
```
OPENAI_API_KEY=sk-tu-clave-de-openai-aqui
```
eso es el **valor de ejemplo**, no una clave real — el chat nunca va a
responder de verdad hasta que la reemplaces. El sistema ahora lo detecta
automáticamente y te lo dice en el chat en vez de fallar en silencio.

**Cómo obtener tu clave real (gratis para probar, con créditos de cortesía
o tarjeta según tu cuenta OpenAI):**

1. Entra a https://platform.openai.com/api-keys (crea una cuenta si no tienes).
2. Clic en "Create new secret key", cópiala (empieza con `sk-...`).
3. Pégala en tu `.env`:
   ```
   OPENAI_API_KEY=sk-tu-clave-real-copiada-aqui
   ```
4. Reinicia `python app.py`.

El resto del sistema (Pacientes, Citas, Mapa, IA/ML, Matriz de Confusión)
**no depende de esta clave** y sigue funcionando al 100% sin ella.

---

## ⚠️ IMPORTANTE: activar la consulta RENIEC (cambio de 2026)

Las dos APIs gratuitas de RENIEC que usaba el sistema (`apis.net.pe` y
`apisperu.com`) **migraron a un esquema de token obligatorio** — ya no
existe ninguna API pública de RENIEC 100% anónima. Por eso, sin configurar
nada, el botón "RENIEC" siempre mostrará "Sin resultados".

**Solución (gratis, 5 minutos):**

1. Regístrate en **una** de estas dos (no necesitas tarjeta de crédito):
   - https://decolecta.com — genera tu token en tu panel.
   - https://apisperu.com — plan gratis de 1,500 a 2,000 consultas/mes.
2. Copia `.env.example` como `.env` (si no lo has hecho ya).
3. Pega tu token en la variable correspondiente:
   ```
   RENIEC_TOKEN_DECOLECTA=tu_token_aqui
   ```
   o
   ```
   RENIEC_TOKEN_APISPERU=tu_token_aqui
   ```
   Con configurar **una sola** de las dos basta.
4. Reinicia `python app.py` y el botón RENIEC ya consultará datos reales.

Si no configuras ningún token, el sistema ahora te lo dice claramente con
un mensaje explicativo (en vez de fallar en silencio como antes), y puedes
seguir registrando pacientes escribiendo los datos a mano sin problema.

---


## Qué estaba fallando

1. **`app.js` nunca llamaba al backend Flask.** Todo se guardaba en `localStorage`
   del navegador. Por eso veías datos en la interfaz, pero la base SQL Server
   se quedaba casi vacía (solo lo que probaste manualmente, como en tu captura
   de SSMS con 2 pacientes).
2. **`database.py` usaba nombres de columna distintos a los de tu `schema.sql`**
   (ej. `hora` en vez de `hora_cita`, `serie` en vez de `numero_serie`, `precio`
   en vez de `precio_unitario`). Aunque el frontend hubiera llamado a la API,
   las consultas SQL habrían fallado.
3. El RENIEC del frontend era una simulación con `setTimeout` (datos falsos
   fijos), no llamaba al endpoint real `/api/reniec/<dni>` que sí existía en
   el backend.
4. El módulo de Hospitalización usaba un campo de texto libre para la cama en
   vez de usar las tablas reales `Habitaciones`/`Camas`.
5. Personal Médico guardaba el nombre de la especialidad como texto en vez del
   `especialidad_id` (FK real de la tabla `Especialidades`).

## Qué se corrigió

- **`app.py`** (antes `database.py`): todas las consultas usan exactamente las
  columnas de `schema.sql`. Se agregaron endpoints nuevos:
  - `GET /api/especialidades` — para poblar el select de especialidades.
  - `GET /api/camas-disponibles` — camas libres para hospitalizar.
  - `POST /api/hospitalizacion/<id>/alta` — da de alta y libera la cama.
  - El dashboard ahora calcula ingresos **del día actual**, no el total histórico.
- **`schema.sql`**: se agregó la columna `latitud`/`longitud` a `Pacientes`
  (para el mapa) y `destinatario_email` a `Notificaciones`. Es seguro volver a
  ejecutar este script; usa `IF NOT EXISTS` en cada tabla.
- **`static/js/app.js`**: reescrito por completo. Cada acción (guardar, listar,
  editar, eliminar) hace `fetch()` real contra `/api/...`, es decir, contra tu
  SQL Server. Ya no hay `localStorage`.
- **`static/js/mapa.js`** (nuevo): mapa del Dashboard con **Leaflet +
  OpenStreetMap** (100% gratis, sin API key) que muestra un marcador por cada
  paciente con dirección geolocalizada.
- **RENIEC**: el frontend ahora llama a `/api/reniec/<dni>`, que ya tenías
  implementado en el backend con dos proveedores gratuitos como respaldo.
- **CIE-10**: autocompletado en Historial Clínico usando la API pública y
  gratuita de la National Library of Medicine (EE.UU.) — no requiere key:
  `https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search`
- **Geocodificación de direcciones**: al escribir la dirección de un paciente,
  se autocompleta con la API gratuita de Nominatim (OpenStreetMap) y guarda
  lat/lng para ubicarlo en el mapa.

## APIs utilizadas (todas gratuitas)

| Función | API | Requiere key |
|---|---|---|
| Mapa del dashboard | OpenStreetMap tiles + Leaflet.js | No |
| Buscar dirección → coordenadas | Nominatim (OpenStreetMap) | No |
| Consulta DNI | api.apis.net.pe / dniruc.apisperu.com (RENIEC Perú) | No (uso limitado) |
| Autocompletar diagnóstico CIE-10 | NLM Clinical Tables (EE.UU.) | No |

## Cómo instalarlo

1. Ejecuta `schema.sql` en tu SQL Server Management Studio (es seguro
   volver a correrlo sobre la base existente).
2. Copia estos archivos reemplazando los tuyos, respetando la misma
   estructura de carpetas (`static/js/app.js`, `static/js/mapa.js`,
   `templates/index.html`, `app.py`, `requirements.txt`).
3. Instala dependencias:
   ```
   pip install -r requirements.txt
   ```
   (Necesitas también el **ODBC Driver 17 for SQL Server** instalado en Windows.)
4. Ajusta las variables de entorno si tu servidor/usuario no son los de
   ejemplo (`DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) o edítalas
   directamente en `app.py`.
5. Ejecuta:
   ```
   python app.py
   ```
6. Abre `http://127.0.0.1:5000` y prueba: registra un paciente con dirección
   (verás el autocompletado de Nominatim), guárdalo y comprueba en SSMS que
   apareció en `dbo.Pacientes`. Lo mismo aplica para cada módulo.

## Nota sobre RENIEC

Las APIs gratuitas de consulta DNI (`apis.net.pe`, `apisperu.com`) tienen
límites de uso y a veces requieren un token gratuito registrándote en su
web para mayor estabilidad. Si notas que dejan de responder, es por eso,
no por un error del código.
