import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, jsonify, current_app
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ==========================================
# CONFIGURACIÓN DE CONEXIÓN A SQLITE
# ==========================================
DB_FILE = os.getenv('DB_FILE', 'hospital.db')


def get_db_connection():
    """Conecta a la base de datos SQLite local."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Retorna resultados como diccionarios
    return conn


def db_query(query, params=(), commit=False, fetch=True):
    """Ejecuta consultas en SQLite y retorna filas como diccionarios."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)

        if commit:
            conn.commit()

        if fetch:
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        return None
    except Exception as e:
        if conn and commit:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()


def db_query_get_id(query, params=()):
    """Ejecuta un INSERT y devuelve el último ID generado."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        new_id = cursor.lastrowid
        conn.commit()
        return new_id
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()


def init_sqlite_db():
    """Crea la estructura de tablas e inserta datos iniciales si no existen."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS Pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dni TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            fecha_nacimiento TEXT,
            genero TEXT,
            telefono TEXT,
            email TEXT,
            direccion TEXT,
            latitud REAL,
            longitud REAL,
            grupo_sanguineo TEXT,
            alergias TEXT
        );

        CREATE TABLE IF NOT EXISTS Especialidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            descripcion TEXT
        );

        CREATE TABLE IF NOT EXISTS PersonalMedico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dni TEXT UNIQUE,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            colegiatura_cmp TEXT,
            especialidad_id INTEGER,
            telefono TEXT,
            email TEXT,
            FOREIGN KEY (especialidad_id) REFERENCES Especialidades(id)
        );

        CREATE TABLE IF NOT EXISTS CitasMedicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            medico_id INTEGER NOT NULL,
            fecha_cita TEXT NOT NULL,
            hora_cita TEXT NOT NULL,
            estado TEXT DEFAULT 'Programada',
            motivo TEXT,
            FOREIGN KEY (paciente_id) REFERENCES Pacientes(id),
            FOREIGN KEY (medico_id) REFERENCES PersonalMedico(id)
        );

        CREATE TABLE IF NOT EXISTS Triaje (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cita_id INTEGER,
            paciente_id INTEGER,
            presion_arterial TEXT,
            temperatura REAL,
            frecuencia_cardiaca INTEGER,
            frecuencia_respiratoria INTEGER,
            saturacion_oxigeno REAL,
            peso_kg REAL,
            talla_cm REAL,
            imc REAL,
            FOREIGN KEY (cita_id) REFERENCES CitasMedicas(id),
            FOREIGN KEY (paciente_id) REFERENCES Pacientes(id)
        );

        CREATE TABLE IF NOT EXISTS HistorialClinico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cita_id INTEGER,
            paciente_id INTEGER,
            medico_id INTEGER,
            motivo_consulta TEXT,
            sintomas TEXT,
            diagnostico TEXT,
            codigo_cie10 TEXT,
            tratamiento TEXT,
            observaciones TEXT,
            fecha_atencion TEXT DEFAULT (DATETIME('now', 'localtime')),
            FOREIGN KEY (cita_id) REFERENCES CitasMedicas(id),
            FOREIGN KEY (paciente_id) REFERENCES Pacientes(id),
            FOREIGN KEY (medico_id) REFERENCES PersonalMedico(id)
        );

        CREATE TABLE IF NOT EXISTS ComprobantesFacturacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER,
            tipo_comprobante TEXT,
            numero_serie TEXT,
            numero_correlativo TEXT,
            monto_subtotal REAL,
            monto_igv REAL,
            monto_total REAL,
            metodo_pago TEXT,
            estado TEXT DEFAULT 'Emitido',
            fecha_emision TEXT DEFAULT (DATETIME('now', 'localtime')),
            FOREIGN KEY (paciente_id) REFERENCES Pacientes(id)
        );

        CREATE TABLE IF NOT EXISTS FarmaciaInsumos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            stock INTEGER DEFAULT 0,
            precio_unitario REAL DEFAULT 0.0,
            fecha_vencimiento TEXT
        );

        CREATE TABLE IF NOT EXISTS ExamenesLaboratorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER,
            medico_id INTEGER,
            nombre_examen TEXT,
            estado TEXT DEFAULT 'Pendiente',
            resultado TEXT,
            fecha_resultado TEXT,
            FOREIGN KEY (paciente_id) REFERENCES Pacientes(id),
            FOREIGN KEY (medico_id) REFERENCES PersonalMedico(id)
        );

        CREATE TABLE IF NOT EXISTS Habitaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_habitacion TEXT NOT NULL,
            piso INTEGER,
            tipo TEXT
        );

        CREATE TABLE IF NOT EXISTS Camas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habitacion_id INTEGER,
            numero_cama TEXT NOT NULL,
            estado TEXT DEFAULT 'Disponible',
            FOREIGN KEY (habitacion_id) REFERENCES Habitaciones(id)
        );

        CREATE TABLE IF NOT EXISTS Hospitalizacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER,
            medico_tratante_id INTEGER,
            cama_id INTEGER,
            diagnostico_ingreso TEXT,
            estado TEXT DEFAULT 'Activo',
            fecha_ingreso TEXT DEFAULT (DATETIME('now', 'localtime')),
            fecha_alta TEXT,
            FOREIGN KEY (paciente_id) REFERENCES Pacientes(id),
            FOREIGN KEY (medico_tratante_id) REFERENCES PersonalMedico(id),
            FOREIGN KEY (cama_id) REFERENCES Camas(id)
        );

        CREATE TABLE IF NOT EXISTS Notificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            destinatario_email TEXT,
            asunto TEXT,
            mensaje TEXT,
            tipo TEXT,
            enviado INTEGER DEFAULT 1,
            fecha_envio TEXT DEFAULT (DATETIME('now', 'localtime'))
        );
    """)
    conn.commit()
    conn.close()


# Inicializar la base de datos SQLite al arrancar la aplicación
init_sqlite_db()

# ---- INICIO: Módulo ML + GPT ----
try:
    import ml_store
    ml_store.configurar(lambda: get_db_connection())
    from blueprint_ml_gpt import ml_gpt_bp
    app.register_blueprint(ml_gpt_bp)
except Exception as e:
    print(f"Aviso al cargar módulo ML/GPT: {e}")
# ---- FIN: Módulo ML + GPT ----


# ==========================================
# RUTA PRINCIPAL
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')


# ==========================================
# API CONSULTA RENIEC EN TIEMPO REAL
# ==========================================
@app.route('/api/reniec/<dni>', methods=['GET'])
def buscar_reniec(dni):
    if len(dni) != 8 or not dni.isdigit():
        return jsonify({'error': 'El DNI debe contener exactamente 8 dígitos numéricos'}), 400

    token_decolecta = os.getenv('RENIEC_TOKEN_DECOLECTA', '').strip()
    token_apisperu = os.getenv('RENIEC_TOKEN_APISPERU', os.getenv('RENIEC_TOKEN', '')).strip()

    if not token_decolecta and not token_apisperu:
        return jsonify({'error': 'La consulta RENIEC requiere un token en las variables de entorno.'}), 503

    if token_decolecta:
        try:
            res1 = requests.get(
                f'https://api.decolecta.com/v1/reniec/dni?numero={dni}',
                headers={'Authorization': f'Bearer {token_decolecta}', 'Accept': 'application/json'},
                timeout=5
            )
            if res1.status_code == 200:
                data = res1.json()
                nombre_completo = data.get('full_name') or ''
                paterno = data.get('first_last_name', '')
                materno = data.get('second_last_name', '')
                nombres = data.get('first_name') or nombre_completo.replace(paterno, '').replace(materno, '').strip()
                return jsonify({
                    'dni': dni,
                    'nombres': nombres,
                    'apellidoPaterno': paterno,
                    'apellidoMaterno': materno,
                    'apellidos': f"{paterno} {materno}".strip()
                })
        except Exception as e:
            current_app.logger.warning(f'Error en Decolecta: {e}')

    if token_apisperu:
        try:
            res2 = requests.get(
                f'https://dniruc.apisperu.com/api/v1/dni/{dni}',
                params={'token': token_apisperu},
                timeout=5
            )
            if res2.status_code == 200:
                data = res2.json()
                paterno = data.get('apellidoPaterno', '')
                materno = data.get('apellidoMaterno', '')
                return jsonify({
                    'dni': dni,
                    'nombres': data.get('nombres', ''),
                    'apellidoPaterno': paterno,
                    'apellidoMaterno': materno,
                    'apellidos': f"{paterno} {materno}".strip()
                })
        except Exception as e:
            current_app.logger.warning(f'Error en ApisPerú: {e}')

    return jsonify({'error': 'No se encontraron datos para el DNI especificado.'}), 404


# ==========================================
# API DASHBOARD
# ==========================================
@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    try:
        p_count = db_query("SELECT COUNT(*) AS total FROM Pacientes")[0]['total']
        c_count = db_query("SELECT COUNT(*) AS total FROM CitasMedicas")[0]['total']
        m_count = db_query("SELECT COUNT(*) AS total FROM PersonalMedico")[0]['total']
        h_count = db_query("SELECT COUNT(*) AS total FROM Hospitalizacion WHERE estado='Activo'")[0]['total']
        ing_row = db_query("""
            SELECT SUM(monto_total) AS total FROM ComprobantesFacturacion
            WHERE DATE(fecha_emision) = DATE('now')
        """)
        ingresos = float(ing_row[0]['total']) if ing_row and ing_row[0]['total'] else 0.0

        return jsonify({
            'pacientes': p_count,
            'citas': c_count,
            'medicos': m_count,
            'hospitalizados': h_count,
            'ingresos': ingresos
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# 1. MÓDULO PACIENTES
# ==========================================
@app.route('/api/pacientes', methods=['GET'])
def get_pacientes():
    try:
        rows = db_query("""
            SELECT id, dni, nombre, apellido, fecha_nacimiento AS fnac,
                   genero, telefono, email, direccion, latitud, longitud,
                   grupo_sanguineo, alergias
            FROM Pacientes ORDER BY id DESC
        """)
        return jsonify(rows or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pacientes', methods=['POST'])
def save_paciente():
    try:
        data = request.json or {}
        p_id = data.get('id')
        dni = str(data.get('dni', '')).strip() if data.get('dni') else None

        if not dni:
            return jsonify({'error': 'El DNI es requerido.'}), 400

        if not p_id:
            existente = db_query("SELECT id FROM Pacientes WHERE TRIM(dni) = TRIM(?)", (dni,))
            if existente:
                p_id = existente[0]['id']

        if p_id:
            db_query("""
                UPDATE Pacientes
                SET dni=?, nombre=?, apellido=?, fecha_nacimiento=?, genero=?, telefono=?, email=?,
                    direccion=?, latitud=?, longitud=?, grupo_sanguineo=?, alergias=?
                WHERE id=?
            """, (dni, data.get('nombre'), data.get('apellido'), data.get('fnac') or None,
                  data.get('genero'), data.get('tel'), data.get('email'), data.get('direccion'),
                  data.get('latitud'), data.get('longitud'), data.get('grupo_sanguineo'),
                  data.get('alergias'), p_id), commit=True)
            return jsonify({'message': 'Paciente actualizado exitosamente', 'id': p_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO Pacientes (dni, nombre, apellido, fecha_nacimiento, genero, telefono, email,
                                       direccion, latitud, longitud, grupo_sanguineo, alergias)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (dni, data.get('nombre'), data.get('apellido'), data.get('fnac') or None,
                  data.get('genero'), data.get('tel'), data.get('email'), data.get('direccion'),
                  data.get('latitud'), data.get('longitud'), data.get('grupo_sanguineo'), data.get('alergias')))
            return jsonify({'message': 'Paciente guardado exitosamente', 'id': new_id})
    except Exception as e:
        error_msg = str(e)
        if 'UNIQUE' in error_msg.upper():
            return jsonify({'error': f'El DNI {data.get("dni")} ya se encuentra registrado.'}), 400
        return jsonify({'error': error_msg}), 500


@app.route('/api/pacientes/<int:id>', methods=['DELETE'])
def delete_paciente(id):
    try:
        db_query("DELETE FROM Pacientes WHERE id=?", (id,), commit=True)
        return jsonify({'message': 'Paciente eliminado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# 2. MÓDULO ESPECIALIDADES
# ==========================================
@app.route('/api/especialidades', methods=['GET'])
def get_especialidades():
    try:
        rows = db_query("SELECT id, nombre, descripcion FROM Especialidades ORDER BY nombre")
        return jsonify(rows or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# 3. MÓDULO PERSONAL MÉDICO
# ==========================================
@app.route('/api/medicos', methods=['GET'])
def get_medicos():
    try:
        rows = db_query("""
            SELECT m.id, m.dni, m.nombre, m.apellido, m.colegiatura_cmp AS cmp,
                   m.especialidad_id, e.nombre AS especialidad, m.telefono AS tel, m.email
            FROM PersonalMedico m
            LEFT JOIN Especialidades e ON m.especialidad_id = e.id
            ORDER BY m.id DESC
        """)
        return jsonify(rows or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/medicos', methods=['POST'])
def save_medico():
    try:
        data = request.json or {}
        m_id = data.get('id')
        dni = str(data.get('dni', '')).strip() if data.get('dni') else None

        if not m_id and dni:
            existente = db_query("SELECT id FROM PersonalMedico WHERE TRIM(dni) = TRIM(?)", (dni,))
            if existente:
                m_id = existente[0]['id']

        if m_id:
            db_query("""
                UPDATE PersonalMedico
                SET dni=?, nombre=?, apellido=?, colegiatura_cmp=?, especialidad_id=?, telefono=?, email=?
                WHERE id=?
            """, (dni, data.get('nombre'), data.get('apellido'), data.get('cmp'),
                  data.get('especialidad_id'), data.get('tel'), data.get('email'), m_id), commit=True)
            return jsonify({'message': 'Personal médico actualizado exitosamente', 'id': m_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO PersonalMedico (dni, nombre, apellido, colegiatura_cmp, especialidad_id, telefono, email)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (dni, data.get('nombre'), data.get('apellido'), data.get('cmp'),
                  data.get('especialidad_id'), data.get('tel'), data.get('email')))
            return jsonify({'message': 'Personal médico guardado exitosamente', 'id': new_id})
    except Exception as e:
        error_msg = str(e)
        if 'UNIQUE' in error_msg.upper():
            return jsonify({'error': 'El DNI o número de CMP ya se encuentra registrado.'}), 400
        return jsonify({'error': error_msg}), 500


@app.route('/api/medicos/<int:id>', methods=['DELETE'])
def delete_medico(id):
    try:
        db_query("DELETE FROM PersonalMedico WHERE id=?", (id,), commit=True)
        return jsonify({'message': 'Personal médico eliminado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# 4. MÓDULO CITAS MÉDICAS
# ==========================================
@app.route('/api/citas', methods=['GET'])
def get_citas():
    try:
        rows = db_query("""
            SELECT c.id, c.paciente_id, c.medico_id, c.fecha_cita AS fecha, c.hora_cita AS hora,
                   c.estado, c.motivo,
                   (p.nombre || ' ' || p.apellido) AS paciente_nombre,
                   ('Dr(a). ' || m.nombre || ' ' || m.apellido) AS medico_nombre
            FROM CitasMedicas c
            LEFT JOIN Pacientes p ON c.paciente_id = p.id
            LEFT JOIN PersonalMedico m ON c.medico_id = m.id
            ORDER BY c.fecha_cita DESC, c.hora_cita DESC
        """)
        return jsonify(rows or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/citas', methods=['POST'])
def save_cita():
    try:
        data = request.json or {}
        c_id = data.get('id')
        if c_id:
            db_query("""
                UPDATE CitasMedicas
                SET paciente_id=?, medico_id=?, fecha_cita=?, hora_cita=?, estado=?, motivo=?
                WHERE id=?
            """, (data.get('paciente_id'), data.get('medico_id'), data.get('fecha'), data.get('hora'),
                  data.get('estado'), data.get('motivo'), c_id), commit=True)
            return jsonify({'message': 'Cita médica actualizada exitosamente', 'id': c_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO CitasMedicas (paciente_id, medico_id, fecha_cita, hora_cita, estado, motivo)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (data.get('paciente_id'), data.get('medico_id'), data.get('fecha'), data.get('hora'),
                  data.get('estado', 'Programada'), data.get('motivo')))
            return jsonify({'message': 'Cita médica guardada exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/citas/<int:id>', methods=['DELETE'])
def delete_cita(id):
    try:
        db_query("DELETE FROM CitasMedicas WHERE id=?", (id,), commit=True)
        return jsonify({'message': 'Cita eliminada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# 5. MÓDULO TRIAJE
# ==========================================
@app.route('/api/triaje', methods=['GET'])
def get_triaje():
    try:
        rows = db_query("""
            SELECT t.id, t.cita_id, t.paciente_id, t.presion_arterial AS presion, t.temperatura AS temp,
                   t.frecuencia_cardiaca AS fc, t.frecuencia_respiratoria AS fr,
                   t.saturacion_oxigeno AS so2, t.peso_kg AS peso, t.talla_cm AS talla, t.imc,
                   (p.nombre || ' ' || p.apellido) AS paciente
            FROM Triaje t
            LEFT JOIN Pacientes p ON t.paciente_id = p.id
            ORDER BY t.id DESC
        """)
        return jsonify(rows or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/triaje', methods=['POST'])
def save_triaje():
    try:
        data = request.json or {}
        t_id = data.get('id')

        peso = float(data.get('peso', 0) or 0)
        talla_m = float(data.get('talla', 1) or 1) / 100
        imc = round(peso / (talla_m * talla_m), 2) if talla_m > 0 else 0

        cita_id = data.get('cita_id')
        cita_row = db_query("SELECT paciente_id FROM CitasMedicas WHERE id=?", (cita_id,))
        paciente_id = cita_row[0]['paciente_id'] if cita_row else data.get('paciente_id')

        if t_id:
            db_query("""
                UPDATE Triaje
                SET cita_id=?, paciente_id=?, presion_arterial=?, temperatura=?, frecuencia_cardiaca=?,
                    saturacion_oxigeno=?, peso_kg=?, talla_cm=?, imc=?
                WHERE id=?
            """, (cita_id, paciente_id, data.get('presion'), data.get('temp'), data.get('fc'),
                  data.get('so2'), data.get('peso'), data.get('talla'), imc, t_id), commit=True)
            return jsonify({'message': 'Triaje actualizado exitosamente', 'id': t_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO Triaje (cita_id, paciente_id, presion_arterial, temperatura,
                                    frecuencia_cardiaca, saturacion_oxigeno, peso_kg, talla_cm, imc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (cita_id, paciente_id, data.get('presion'), data.get('temp'), data.get('fc'),
                  data.get('so2'), data.get('peso'), data.get('talla'), imc))
            
            if cita_id:
                db_query("UPDATE CitasMedicas SET estado='En Triaje' WHERE id=?", (cita_id,), commit=True, fetch=False)
            return jsonify({'message': 'Triaje guardado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/triaje/<int:id>', methods=['DELETE'])
def delete_triaje(id):
    try:
        db_query("DELETE FROM Triaje WHERE id=?", (id,), commit=True)
        return jsonify({'message': 'Triaje eliminado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# 6. MÓDULO HISTORIAL CLÍNICO
# ==========================================
@app.route('/api/historial', methods=['GET'])
def get_historial():
    try:
        rows = db_query("""
            SELECT h.id, h.cita_id, h.paciente_id, h.medico_id, h.motivo_consulta, h.sintomas,
                   h.diagnostico, h.codigo_cie10 AS cie10, h.tratamiento, h.observaciones,
                   h.fecha_atencion AS fecha,
                   (p.nombre || ' ' || p.apellido) AS paciente,
                   ('Dr(a). ' || m.nombre || ' ' || m.apellido) AS medico
            FROM HistorialClinico h
            LEFT JOIN Pacientes p ON h.paciente_id = p.id
            LEFT JOIN PersonalMedico m ON h.medico_id = m.id
            ORDER BY h.id DESC
        """)
        return jsonify(rows or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/historial', methods=['POST'])
def save_historial():
    try:
        data = request.json or {}
        h_id = data.get('id')
        cita_id = data.get('cita_id')

        cita_row = db_query("SELECT paciente_id, medico_id FROM CitasMedicas WHERE id=?", (cita_id,))
        if not cita_row:
            return jsonify({'error': 'La cita seleccionada no existe'}), 400
        paciente_id = cita_row[0]['paciente_id']
        medico_id = cita_row[0]['medico_id']

        if h_id:
            db_query("""
                UPDATE HistorialClinico
                SET cita_id=?, paciente_id=?, medico_id=?, sintomas=?, diagnostico=?, codigo_cie10=?, tratamiento=?
                WHERE id=?
            """, (cita_id, paciente_id, medico_id, data.get('sintomas'), data.get('diagnostico'),
                  data.get('cie10'), data.get('tratamiento'), h_id), commit=True)
            return jsonify({'message': 'Historial clínico actualizado exitosamente', 'id': h_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO HistorialClinico (cita_id, paciente_id, medico_id, sintomas, diagnostico,
                                              codigo_cie10, tratamiento)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (cita_id, paciente_id, medico_id, data.get('sintomas'), data.get('diagnostico'),
                  data.get('cie10'), data.get('tratamiento')))
            db_query("UPDATE CitasMedicas SET estado='Atendido' WHERE id=?", (cita_id,), commit=True, fetch=False)
            return jsonify({'message': 'Historial clínico guardado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/historial/<int:id>', methods=['DELETE'])
def delete_historial(id):
    try:
        db_query("DELETE FROM HistorialClinico WHERE id=?", (id,), commit=True)
        return jsonify({'message': 'Historial eliminado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# 7. MÓDULO CAJA Y FACTURACIÓN
# ==========================================
@app.route('/api/facturacion', methods=['GET'])
def get_facturacion():
    try:
        rows = db_query("""
            SELECT f.id, f.paciente_id, f.tipo_comprobante AS tipo, f.numero_serie AS serie,
                   f.numero_correlativo AS correlativo, f.monto_subtotal, f.monto_igv,
                   f.monto_total AS monto, f.metodo_pago AS metodo, f.estado,
                   f.fecha_emision AS fecha,
                   (p.nombre || ' ' || p.apellido) AS paciente
            FROM ComprobantesFacturacion f
            LEFT JOIN Pacientes p ON f.paciente_id = p.id
            ORDER BY f.id DESC
        """)
        return jsonify(rows or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/facturacion', methods=['POST'])
def save_facturacion():
    try:
        data = request.json or {}
        f_id = data.get('id')

        monto_total = float(data.get('monto', 0) or 0)
        monto_subtotal = round(monto_total / 1.18, 2)
        monto_igv = round(monto_total - monto_subtotal, 2)

        if f_id:
            db_query("""
                UPDATE ComprobantesFacturacion
                SET paciente_id=?, tipo_comprobante=?, numero_serie=?, numero_correlativo=?,
                    monto_subtotal=?, monto_igv=?, monto_total=?, metodo_pago=?
                WHERE id=?
            """, (data.get('paciente_id'), data.get('tipo'), data.get('serie'), data.get('correlativo'),
                  monto_subtotal, monto_igv, monto_total, data.get('metodo'), f_id), commit=True)
            return jsonify({'message': 'Comprobante actualizado exitosamente', 'id': f_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO ComprobantesFacturacion (paciente_id, tipo_comprobante, numero_serie,
                    numero_correlativo, monto_subtotal, monto_igv, monto_total, metodo_pago)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (data.get('paciente_id'), data.get('tipo'), data.get('serie'), data.get('correlativo'),
                  monto_subtotal, monto_igv, monto_total, data.get('metodo')))
            return jsonify({'message': 'Comprobante registrado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/facturacion/<int:id>', methods=['DELETE'])
def delete_facturacion(id):
    try:
        db_query("UPDATE ComprobantesFacturacion SET estado='Anulado' WHERE id=?", (id,), commit=True)
        return jsonify({'message': 'Comprobante anulado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# 8. MÓDULO FARMACIA
# ==========================================
@app.route('/api/farmacia', methods=['GET'])
def get_farmacia():
    try:
        rows = db_query("""
            SELECT id, codigo, nombre, descripcion AS tipo, stock, precio_unitario AS precio,
                   fecha_vencimiento AS vencimiento
            FROM FarmaciaInsumos ORDER BY id DESC
        """)
        return jsonify(rows or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/farmacia', methods=['POST'])
def save_farmacia():
    try:
        data = request.json or {}
        far_id = data.get('id')
        if far_id:
            db_query("""
                UPDATE FarmaciaInsumos
                SET codigo=?, nombre=?, descripcion=?, stock=?, precio_unitario=?, fecha_vencimiento=?
                WHERE id=?
            """, (data.get('codigo'), data.get('nombre'), data.get('tipo'), data.get('stock'),
                  data.get('precio'), data.get('vencimiento'), far_id), commit=True)
            return jsonify({'message': 'Producto actualizado exitosamente', 'id': far_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO FarmaciaInsumos (codigo, nombre, descripcion, stock, precio_unitario, fecha_vencimiento)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (data.get('codigo'), data.get('nombre'), data.get('tipo'), data.get('stock'),
                  data.get('precio'), data.get('vencimiento')))
            return jsonify({'message': 'Producto de farmacia guardado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/farmacia/<int:id>', methods=['DELETE'])
def delete_farmacia(id):
    try:
        db_query("DELETE FROM FarmaciaInsumos WHERE id=?", (id,), commit=True)
        return jsonify({'message': 'Producto eliminado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# 9. MÓDULO LABORATORIO
# ==========================================
@app.route('/api/laboratorio', methods=['GET'])
def get_laboratorio():
    try:
        rows = db_query("""
            SELECT l.id, l.paciente_id, l.medico_id, l.nombre_examen AS examen, l.estado, l.resultado,
                   (p.nombre || ' ' || p.apellido) AS paciente
            FROM ExamenesLaboratorio l
            LEFT JOIN Pacientes p ON l.paciente_id = p.id
            ORDER BY l.id DESC
        """)
        return jsonify(rows or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/laboratorio', methods=['POST'])
def save_laboratorio():
    try:
        data = request.json or {}
        lab_id = data.get('id')
        fecha_resultado = datetime.now().strftime('%Y-%m-%d %H:%M:%S') if data.get('estado') == 'Completado' else None

        if lab_id:
            db_query("""
                UPDATE ExamenesLaboratorio
                SET paciente_id=?, medico_id=?, nombre_examen=?, estado=?, resultado=?, fecha_resultado=?
                WHERE id=?
            """, (data.get('paciente_id'), data.get('medico_id'), data.get('examen'), data.get('estado'),
                  data.get('resultado'), fecha_resultado, lab_id), commit=True)
            return jsonify({'message': 'Examen actualizado exitosamente', 'id': lab_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO ExamenesLaboratorio (paciente_id, medico_id, nombre_examen, estado, resultado)
                VALUES (?, ?, ?, ?, ?)
            """, (data.get('paciente_id'), data.get('medico_id'), data.get('examen'),
                  data.get('estado', 'Pendiente'), data.get('resultado')))
            return jsonify({'message': 'Examen guardado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/laboratorio/<int:id>', methods=['DELETE'])
def delete_laboratorio(id):
    try:
        db_query("DELETE FROM ExamenesLaboratorio WHERE id=?", (id,), commit=True)
        return jsonify({'message': 'Examen eliminado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# 10. MÓDULO HOSPITALIZACIÓN
# ==========================================
@app.route('/api/camas-disponibles', methods=['GET'])
def get_camas_disponibles():
    try:
        rows = db_query("""
            SELECT c.id, c.numero_cama, h.numero_habitacion, h.piso, h.tipo
            FROM Camas c
            JOIN Habitaciones h ON c.habitacion_id = h.id
            WHERE c.estado = 'Disponible'
            ORDER BY h.piso, h.numero_habitacion
        """)
        return jsonify(rows or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/hospitalizacion', methods=['GET'])
def get_hospitalizacion():
    try:
        rows = db_query("""
            SELECT h.id, h.paciente_id, h.medico_tratante_id AS medico_id, h.cama_id,
                   h.diagnostico_ingreso AS diag, h.estado, h.fecha_ingreso AS fecha,
                   (p.nombre || ' ' || p.apellido) AS paciente,
                   ('Dr(a). ' || m.nombre || ' ' || m.apellido) AS medico,
                   (hab.numero_habitacion || ' - ' || c.numero_cama) AS cama
            FROM Hospitalizacion h
            LEFT JOIN Pacientes p ON h.paciente_id = p.id
            LEFT JOIN PersonalMedico m ON h.medico_tratante_id = m.id
            LEFT JOIN Camas c ON h.cama_id = c.id
            LEFT JOIN Habitaciones hab ON c.habitacion_id = hab.id
            ORDER BY h.id DESC
        """)
        return jsonify(rows or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/hospitalizacion', methods=['POST'])
def save_hospitalizacion():
    try:
        data = request.json or {}
        hosp_id = data.get('id')

        if hosp_id:
            db_query("""
                UPDATE Hospitalizacion
                SET paciente_id=?, medico_tratante_id=?, cama_id=?, diagnostico_ingreso=?
                WHERE id=?
            """, (data.get('paciente_id'), data.get('medico_id'), data.get('cama_id'),
                  data.get('diag'), hosp_id), commit=True)
            return jsonify({'message': 'Hospitalización actualizada exitosamente', 'id': hosp_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO Hospitalizacion (paciente_id, medico_tratante_id, cama_id, diagnostico_ingreso)
                VALUES (?, ?, ?, ?)
            """, (data.get('paciente_id'), data.get('medico_id'), data.get('cama_id'), data.get('diag')))
            db_query("UPDATE Camas SET estado='Ocupada' WHERE id=?", (data.get('cama_id'),), commit=True, fetch=False)
            return jsonify({'message': 'Paciente hospitalizado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/hospitalizacion/<int:id>/alta', methods=['POST'])
def dar_alta(id):
    try:
        row = db_query("SELECT cama_id FROM Hospitalizacion WHERE id=?", (id,))
        if not row:
            return jsonify({'error': 'Registro no encontrado'}), 404
        cama_id = row[0]['cama_id']

        db_query("""
            UPDATE Hospitalizacion SET estado='Alta', fecha_alta=DATETIME('now', 'localtime') WHERE id=?
        """, (id,), commit=True, fetch=False)
        
        if cama_id:
            db_query("UPDATE Camas SET estado='Disponible' WHERE id=?", (cama_id,), commit=True, fetch=False)
            
        return jsonify({'message': 'Paciente dado de alta y cama liberada exitosamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/hospitalizacion/<int:id>', methods=['DELETE'])
def delete_hospitalizacion(id):
    try:
        row = db_query("SELECT cama_id FROM Hospitalizacion WHERE id=?", (id,))
        db_query("DELETE FROM Hospitalizacion WHERE id=?", (id,), commit=True)
        if row and row[0]['cama_id']:
            db_query("UPDATE Camas SET estado='Disponible' WHERE id=?", (row[0]['cama_id'],), commit=True, fetch=False)
        return jsonify({'message': 'Registro de hospitalización eliminado y cama liberada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# 11. MÓDULO NOTIFICACIONES
# ==========================================
@app.route('/api/notificaciones', methods=['GET'])
def get_notificaciones():
    try:
        rows = db_query("""
            SELECT id, destinatario_email AS email, asunto, mensaje, tipo, fecha_envio AS fecha
            FROM Notificaciones ORDER BY id DESC
        """)
        return jsonify(rows or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/notificaciones', methods=['POST'])
def save_notificacion():
    try:
        data = request.json or {}
        new_id = db_query_get_id("""
            INSERT INTO Notificaciones (destinatario_email, asunto, mensaje, tipo, enviado)
            VALUES (?, ?, ?, 'Email', 1)
        """, (data.get('email'), data.get('asunto'), data.get('mensaje')))
        return jsonify({'message': 'Notificación enviada y registrada exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/notificaciones/<int:id>', methods=['DELETE'])
def delete_notificacion(id):
    try:
        db_query("DELETE FROM Notificaciones WHERE id=?", (id,), commit=True)
        return jsonify({'message': 'Notificación eliminada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# EJECUCIÓN DEL SERVIDOR
# ==========================================
if __name__ == '__main__':
    app.run(debug=True, port=5000)