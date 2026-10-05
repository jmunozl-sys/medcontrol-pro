import os
import sqlite3
import requests
from flask import Flask, render_template, request, jsonify

# Importación opcional de pyodbc para entorno Windows local
try:
    import pyodbc
    HAS_PYODBC = True
except ImportError:
    HAS_PYODBC = False

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "medcontrol_secret_key_2026")

# Detección del entorno Render y ruta de la BD SQLite
IS_RENDER = os.environ.get("RENDER") is not None
SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), "medcontrol.db")

# ==========================================
# HELPER DE RENDERIZADO SEGURO DE PLANTILLAS
# ==========================================
def safe_render_template(template_name, **context):
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    target_path = os.path.join(templates_dir, template_name)
    
    if os.path.exists(target_path):
        return render_template(template_name, **context)
    
    for fallback in ['index.html', 'pacientes.html']:
        if os.path.exists(os.path.join(templates_dir, fallback)):
            return render_template(fallback, **context)
            
    return (
        f"<h2>MedControl Pro Activo</h2>"
        f"<p>No se encontró la plantilla <code>{template_name}</code> en la carpeta <code>templates/</code>.</p>", 200
    )

# ==========================================
# INICIALIZACIÓN Y AUTO-MIGRACIÓN DE BD
# ==========================================
def init_sqlite_db():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    
    # Tabla Pacientes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dni TEXT UNIQUE NOT NULL,
            nombres TEXT,
            apellidos TEXT,
            telefono TEXT,
            email TEXT,
            direccion TEXT,
            fecha_nacimiento TEXT,
            genero TEXT,
            grupo_sanguineo TEXT,
            alergias TEXT,
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migración automática de columnas para bases de datos existentes
    cursor.execute("PRAGMA table_info(Pacientes)")
    existing_cols = [column[1] for column in cursor.fetchall()]
    required_cols = {
        "telefono": "TEXT",
        "email": "TEXT",
        "direccion": "TEXT",
        "fecha_nacimiento": "TEXT",
        "genero": "TEXT",
        "grupo_sanguineo": "TEXT",
        "alergias": "TEXT"
    }
    for col, col_type in required_cols.items():
        if col not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE Pacientes ADD COLUMN {col} {col_type}")
            except Exception as e:
                print(f"[DB Migration Warning]: {e}")

    # Tabla Personal Médico
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS PersonalMedico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dni TEXT UNIQUE NOT NULL,
            nombres TEXT,
            apellidos TEXT,
            colegiatura TEXT,
            especialidad TEXT,
            telefono TEXT,
            email TEXT,
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Tabla Citas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Citas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER,
            medico_id INTEGER,
            fecha TEXT,
            hora TEXT,
            motivo TEXT,
            estado TEXT DEFAULT 'Pendiente',
            FOREIGN KEY (paciente_id) REFERENCES Pacientes (id),
            FOREIGN KEY (medico_id) REFERENCES PersonalMedico (id)
        )
    ''')

    conn.commit()
    conn.close()

init_sqlite_db()

# ==========================================
# CONEXIÓN Y CONSULTAS A LA BASE DE DATOS
# ==========================================
def get_db_connection():
    if IS_RENDER or not HAS_PYODBC:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

    try:
        server = os.environ.get("DB_SERVER", "localhost\\SQLEXPRESS")
        database = os.environ.get("DB_NAME", "MedControlDB")
        conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};Trusted_Connection=yes;"
        conn = pyodbc.connect(conn_str, timeout=3)
        return conn, "sqlserver"
    except Exception as e:
        print(f"[DB Warning] SQL Server no accesible ({e}). Usando SQLite.")
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    result = None

    try:
        exec_query = query
        if db_type == "sqlserver":
            exec_query = query.replace("AUTOINCREMENT", "IDENTITY(1,1)")

        cursor.execute(exec_query, params)

        if commit:
            conn.commit()
            result = True
        elif fetchone:
            row = cursor.fetchone()
            if row:
                result = dict(row) if db_type == "sqlite" else dict(zip([column[0] for column in cursor.description], row))
        elif fetchall:
            rows = cursor.fetchall()
            if rows:
                if db_type == "sqlite":
                    result = [dict(row) for row in rows]
                else:
                    columns = [column[0] for column in cursor.description]
                    result = [dict(zip(columns, row)) for row in rows]
            else:
                result = []
    except Exception as e:
        print(f"[DB Error] Fallo en la consulta ({db_type}): {e}")
        if commit:
            conn.rollback()
        result = [] if fetchall else None
    finally:
        conn.close()

    return result

# ==========================================
# INTEGRACIÓN API RENIEC
# ==========================================
@app.route('/api/reniec/<dni>', methods=['GET'])
@app.route('/api/reniec', methods=['GET'])
@app.route('/reniec/<dni>', methods=['GET'])
def consultar_reniec(dni=None):
    if not dni:
        dni = request.args.get('dni') or request.args.get('numero')

    if not dni or len(dni) != 8 or not dni.isdigit():
        return jsonify({"success": False, "message": "El DNI debe contener exactamente 8 dígitos numéricos."}), 400

    token_decolecta = os.environ.get("RENIEC_TOKEN_DECOLECTA")
    token_apisperu = os.environ.get("RENIEC_TOKEN_APISPERU")

    # 1. Probar API Decolecta
    if token_decolecta:
        try:
            url = f"https://api.decolecta.com/v1/reniec/dni?numero={dni}"
            headers = {"Authorization": f"Bearer {token_decolecta}", "Accept": "application/json"}
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                nombres = data.get("nombres") or data.get("first_name", "")
                paterno = data.get("apellidoPaterno") or data.get("first_last_name", "")
                materno = data.get("apellidoMaterno") or data.get("second_last_name", "")
                if nombres:
                    return jsonify({
                        "success": True,
                        "nombres": nombres.strip(),
                        "apellidos": f"{paterno} {materno}".strip(),
                        "source": "Decolecta"
                    }), 200
        except Exception as e:
            print(f"[RENIEC Decolecta Error]: {e}")

    # 2. Probar API ApisPerú
    if token_apisperu:
        try:
            url = f"https://dniruc.apisperu.com/api/v1/dni/{dni}?token={token_apisperu}"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get("nombres"):
                    return jsonify({
                        "success": True,
                        "nombres": data.get("nombres", "").strip(),
                        "apellidos": f"{data.get('apellidoPaterno', '')} {data.get('apellidoMaterno', '')}".strip(),
                        "source": "ApisPerú"
                    }), 200
        except Exception as e:
            print(f"[RENIEC ApisPerú Error]: {e}")

    return jsonify({"success": False, "message": f"No se encontraron datos para el DNI {dni}."}), 404

# ==========================================
# ENDPOINTS UNIFICADOS DE PACIENTES (UPSERT)
# ==========================================
@app.route('/pacientes')
def vista_pacientes():
    return safe_render_template('pacientes.html')

@app.route('/api/pacientes', methods=['GET', 'POST'])
@app.route('/api/pacientes/guardar', methods=['POST'])
def gestionar_pacientes():
    if request.method == 'POST':
        data = request.json or request.form or {}
        dni = data.get('dni')
        nombres = data.get('nombres')
        apellidos = data.get('apellidos')
        telefono = data.get('telefono', '')
        email = data.get('email', '')
        direccion = data.get('direccion', '')
        fecha_nac = data.get('fecha_nacimiento') or data.get('fecha_nac', '')
        genero = data.get('genero', '')
        grupo_sangre = data.get('grupo_sanguineo') or data.get('grupo_sangre', '')
        alergias = data.get('alergias', '')

        if not dni or not nombres or not apellidos:
            return jsonify({"success": False, "message": "DNI, nombres y apellidos son requeridos."}), 400

        # Verificar si el paciente ya existe para actualizarlo o insertarlo
        existente = db_query("SELECT id FROM Pacientes WHERE dni = ?", (dni,), fetchone=True)

        if existente:
            query = '''
                UPDATE Pacientes 
                SET nombres=?, apellidos=?, telefono=?, email=?, direccion=?, fecha_nacimiento=?, genero=?, grupo_sanguineo=?, alergias=?
                WHERE dni=?
            '''
            params = (nombres, apellidos, telefono, email, direccion, fecha_nac, genero, grupo_sangre, alergias, dni)
            msg = "Paciente actualizado correctamente."
        else:
            query = '''
                INSERT INTO Pacientes (dni, nombres, apellidos, telefono, email, direccion, fecha_nacimiento, genero, grupo_sanguineo, alergias)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            params = (dni, nombres, apellidos, telefono, email, direccion, fecha_nac, genero, grupo_sangre, alergias)
            msg = "Paciente registrado con éxito."
        
        exito = db_query(query, params, commit=True)
        if exito:
            return jsonify({"success": True, "message": msg}), 200
        else:
            return jsonify({"success": False, "message": "No se pudo guardar la información en la base de datos."}), 500

    # Método GET: Listar pacientes
    query = "SELECT id, dni, nombres, apellidos, telefono, email FROM Pacientes ORDER BY id DESC"
    pacientes = db_query(query, fetchall=True) or []
    return jsonify({"success": True, "data": pacientes}), 200

# ==========================================
# ENDPOINTS UNIFICADOS DE PERSONAL MÉDICO
# ==========================================
@app.route('/personal_medico')
def vista_personal_medico():
    return safe_render_template('personal_medico.html')

@app.route('/api/personal_medico', methods=['GET', 'POST'])
@app.route('/api/personal_medico/guardar', methods=['POST'])
def gestionar_personal_medico():
    if request.method == 'POST':
        data = request.json or request.form or {}
        dni = data.get('dni')
        nombres = data.get('nombres')
        apellidos = data.get('apellidos')
        colegiatura = data.get('colegiatura', '')
        especialidad = data.get('especialidad', '')
        telefono = data.get('telefono', '')
        email = data.get('email', '')

        if not dni or not nombres or not apellidos:
            return jsonify({"success": False, "message": "DNI, nombres y apellidos son requeridos."}), 400

        existente = db_query("SELECT id FROM PersonalMedico WHERE dni = ?", (dni,), fetchone=True)

        if existente:
            query = '''
                UPDATE PersonalMedico
                SET nombres=?, apellidos=?, colegiatura=?, especialidad=?, telefono=?, email=?
                WHERE dni=?
            '''
            params = (nombres, apellidos, colegiatura, especialidad, telefono, email, dni)
            msg = "Personal médico actualizado con éxito."
        else:
            query = '''
                INSERT INTO PersonalMedico (dni, nombres, apellidos, colegiatura, especialidad, telefono, email)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            '''
            params = (dni, nombres, apellidos, colegiatura, especialidad, telefono, email)
            msg = "Personal médico registrado con éxito."

        exito = db_query(query, params, commit=True)
        if exito:
            return jsonify({"success": True, "message": msg}), 200
        else:
            return jsonify({"success": False, "message": "No se pudo guardar la información del personal médico."}), 500

    # Método GET: Listar médicos
    query = "SELECT id, dni, nombres, apellidos, colegiatura, especialidad, telefono, email FROM PersonalMedico ORDER BY id DESC"
    medicos = db_query(query, fetchall=True) or []
    return jsonify({"success": True, "data": medicos}), 200

# ==========================================
# ENDPOINTS DE RESPALDO
# ==========================================
@app.route('/api/citas', methods=['GET', 'POST'])
def api_citas():
    return jsonify({"success": True, "data": []}), 200

@app.route('/api/facturacion', methods=['GET', 'POST'])
def api_facturacion():
    return jsonify({"success": True, "data": []}), 200

@app.route('/api/laboratorio', methods=['GET', 'POST'])
def api_laboratorio():
    return jsonify({"success": True, "data": []}), 200

@app.route('/api/notificaciones', methods=['GET', 'POST'])
def api_notificaciones():
    return jsonify({"success": True, "data": []}), 200

# ==========================================
# RUTAS DE VISTAS DE NAVEGACIÓN
# ==========================================
@app.route('/')
@app.route('/dashboard')
def dashboard():
    return safe_render_template('dashboard.html')

@app.route('/citas')
def citas():
    return safe_render_template('citas.html')

@app.route('/triaje')
def triaje():
    return safe_render_template('triaje.html')

@app.route('/historial')
def historial():
    return safe_render_template('historial.html')

@app.route('/facturacion')
def facturacion():
    return safe_render_template('facturacion.html')

@app.route('/farmacia')
def farmacia():
    return safe_render_template('farmacia.html')

@app.route('/laboratorio')
def laboratorio():
    return safe_render_template('laboratorio.html')

@app.route('/hospitalizacion')
def hospitalizacion():
    return safe_render_template('hospitalizacion.html')

# ==========================================
# MANEJADORES DE ERRORES INTELIGENTES
# ==========================================
@app.errorhandler(405)
def method_not_allowed(e):
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "message": f"Método HTTP {request.method} no permitido."}), 405
    return "<h2>Método no permitido (405)</h2>", 405

@app.errorhandler(500)
def server_error(e):
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "message": f"Error interno en la API: {str(e)}"}), 500
    return f"<h2>Error Interno del Servidor (500)</h2><p>{str(e)}</p>", 500

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "message": "Endpoint de API no encontrado."}), 404
    return "<h2>Página no encontrada (404)</h2><p>La ruta especificada no existe.</p>", 404

# ==========================================
# INICIO DEL SERVIDOR
# ==========================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=not IS_RENDER)