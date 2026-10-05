import os
import sqlite3
import requests
from flask import Flask, render_template, request, jsonify

# Opcional: PyODBC para conexión local a SQL Server
try:
    import pyodbc
    HAS_PYODBC = True
except ImportError:
    HAS_PYODBC = False

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "medcontrol_secret_key_2026")

# Detectar entorno de ejecución
IS_RENDER = os.environ.get("RENDER") is not None
SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), "medcontrol.db")

# ==========================================
# INICIALIZACIÓN DE BASE DE DATOS SQLITE
# ==========================================
def init_sqlite_db():
    """Crea la estructura de tablas necesarias en SQLite si no existen."""
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

# Ejecutar creación de tablas al iniciar
init_sqlite_db()

# ==========================================
# CONEXIÓN Y CONSULTAS A LA BASE DE DATOS
# ==========================================
def get_db_connection():
    """Conecta a SQL Server local o commuta a SQLite si está en Render o falla SQL Server."""
    if IS_RENDER or not HAS_PYODBC:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

    # Intentar conexión a SQL Server Local
    try:
        server = os.environ.get("DB_SERVER", "localhost\\SQLEXPRESS")
        database = os.environ.get("DB_NAME", "MedControlDB")
        conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};Trusted_Connection=yes;"
        conn = pyodbc.connect(conn_str, timeout=3)
        return conn, "sqlserver"
    except Exception as e:
        print(f"[DB Warning] No se pudo conectar a SQL Server ({e}). Usando SQLite local.")
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    """Ejecuta consultas de manera agnóstica para SQLite y SQL Server."""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    result = None

    try:
        # Adaptación ligera de sintaxis entre motores si fuera necesario
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
# INTEGRACIÓN API RENIEC (Decolecta / ApisPerú)
# ==========================================
@app.route('/api/reniec/<dni>', methods=['GET'])
def consultar_reniec(dni):
    if len(dni) != 8 or not dni.isdigit():
        return jsonify({"success": False, "message": "DNI debe tener 8 dígitos numéricos."}), 400

    token_decolecta = os.environ.get("RENIEC_TOKEN_DECOLECTA")
    token_apisperu = os.environ.get("RENIEC_TOKEN_APISPERU")

    # 1. Intentar con Decolecta
    if token_decolecta:
        try:
            url = f"https://api.decolecta.com/v1/reniec/dni?numero={dni}"
            headers = {"Authorization": f"Bearer {token_decolecta}", "Accept": "application/json"}
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if "nombres" in data or "first_name" in data:
                    nombres = data.get("nombres") or data.get("first_name", "")
                    apellido_paterno = data.get("apellidoPaterno") or data.get("first_last_name", "")
                    apellido_materno = data.get("apellidoMaterno") or data.get("second_last_name", "")
                    return jsonify({
                        "success": True,
                        "nombres": nombres.strip(),
                        "apellidos": f"{apellido_paterno} {apellido_materno}".strip(),
                        "source": "Decolecta"
                    })
        except Exception as e:
            print(f"[RENIEC Decolecta Error]: {e}")

    # 2. Intentar con ApisPerú
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
                    })
        except Exception as e:
            print(f"[RENIEC ApisPerú Error]: {e}")

    return jsonify({"success": False, "message": "No se encontraron datos para el DNI especificado."}), 404

# ==========================================
# RUTAS DE PACIENTES
# ==========================================
@app.route('/pacientes')
def vista_pacientes():
    return render_template('pacientes.html')

@app.route('/api/pacientes', methods=['GET'])
def listar_pacientes():
    query = "SELECT id, dni, nombres, apellidos, telefono, email FROM Pacientes ORDER BY id DESC"
    pacientes = db_query(query, fetchall=True) or []
    return jsonify({"success": True, "data": pacientes})

@app.route('/api/pacientes/guardar', methods=['POST'])
def guardar_paciente():
    data = request.json or request.form
    dni = data.get('dni')
    nombres = data.get('nombres')
    apellidos = data.get('apellidos')
    telefono = data.get('telefono', '')
    email = data.get('email', '')
    direccion = data.get('direccion', '')
    fecha_nac = data.get('fecha_nacimiento', '')
    genero = data.get('genero', '')
    grupo_sangre = data.get('grupo_sanguineo', '')
    alergias = data.get('alergias', '')

    if not dni or not nombres or not apellidos:
        return jsonify({"success": False, "message": "DNI, nombres y apellidos son requeridos."}), 400

    query = '''
        INSERT INTO Pacientes (dni, nombres, apellidos, telefono, email, direccion, fecha_nacimiento, genero, grupo_sanguineo, alergias)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    params = (dni, nombres, apellidos, telefono, email, direccion, fecha_nac, genero, grupo_sangre, alergias)
    
    exito = db_query(query, params, commit=True)
    if exito:
        return jsonify({"success": True, "message": "Paciente registrado con éxito."})
    else:
        return jsonify({"success": False, "message": "Error al guardar el paciente en la base de datos (posible DNI duplicado)."}), 500

# ==========================================
# RUTAS DE PERSONAL MÉDICO
# ==========================================
@app.route('/personal_medico')
def vista_personal_medico():
    return render_template('personal_medico.html')

@app.route('/api/personal_medico', methods=['GET'])
def listar_personal_medico():
    query = "SELECT id, dni, nombres, apellidos, colegiatura, especialidad, telefono, email FROM PersonalMedico ORDER BY id DESC"
    medicos = db_query(query, fetchall=True) or []
    return jsonify({"success": True, "data": medicos})

@app.route('/api/personal_medico/guardar', methods=['POST'])
def guardar_personal_medico():
    data = request.json or request.form
    dni = data.get('dni')
    nombres = data.get('nombres')
    apellidos = data.get('apellidos')
    colegiatura = data.get('colegiatura', '')
    especialidad = data.get('especialidad', '')
    telefono = data.get('telefono', '')
    email = data.get('email', '')

    if not dni or not nombres or not apellidos:
        return jsonify({"success": False, "message": "DNI, nombres y apellidos son requeridos."}), 400

    query = '''
        INSERT INTO PersonalMedico (dni, nombres, apellidos, colegiatura, especialidad, telefono, email)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    '''
    params = (dni, nombres, apellidos, colegiatura, especialidad, telefono, email)

    exito = db_query(query, params, commit=True)
    if exito:
        return jsonify({"success": True, "message": "Personal médico registrado con éxito."})
    else:
        return jsonify({"success": False, "message": "Error al guardar personal médico."}), 500

# ==========================================
# RUTAS SECUNDARIAS / VISTAS DEL SISTEMA
# ==========================================
@app.route('/')
@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/citas')
def citas():
    return render_template('citas.html')

@app.route('/triaje')
def triaje():
    return render_template('triaje.html')

@app.route('/historial')
def historial():
    return render_template('historial.html')

@app.route('/facturacion')
def facturacion():
    return render_template('facturacion.html')

@app.route('/farmacia')
def farmacia():
    return render_template('farmacia.html')

@app.route('/laboratorio')
def laboratorio():
    return render_template('laboratorio.html')

@app.route('/hospitalizacion')
def hospitalizacion():
    return render_template('hospitalizacion.html')

# ==========================================
# EJECUCIÓN DEL SERVIDOR
# ==========================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=not IS_RENDER)