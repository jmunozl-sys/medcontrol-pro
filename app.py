import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, current_app
import pyodbc
import requests
from dotenv import load_dotenv

load_dotenv()  # Carga variables desde el archivo .env

app = Flask(__name__)

# ---- INICIO: Integración del módulo ML + GPT ----
import ml_store
ml_store.configurar(lambda: get_db_connection())  # Reutiliza la conexión a la BD
from blueprint_ml_gpt import ml_gpt_bp
app.register_blueprint(ml_gpt_bp)
# ---- FIN: Integración del módulo ML + GPT ----

# ==========================================
# CONFIGURACIÓN DE CONEXIÓN A SQL SERVER
# ==========================================
SERVER = os.getenv('DB_SERVER', 'DESKTOP-PEB6BCK')
DATABASE = os.getenv('DB_NAME', 'HDAC_Hospital_DB')
DB_USER = os.getenv('DB_USER', 'sa')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'tu_contraseña_aqui')


def get_db_connection():
    """Conecta a SQL Server. Si falla o falta el driver en Linux/Render, retorna None de forma segura."""
    try:
        conn_str = (
            f'DRIVER={{ODBC Driver 17 for SQL Server}};'
            f'SERVER={SERVER};'
            f'DATABASE={DATABASE};'
            'Trusted_Connection=yes;'
        )
        return pyodbc.connect(conn_str, timeout=3)
    except Exception:
        pass

    try:
        conn_str = (
            f'DRIVER={{ODBC Driver 17 for SQL Server}};'
            f'SERVER={SERVER};'
            f'DATABASE={DATABASE};'
            f'UID={DB_USER};PWD={DB_PASSWORD};'
        )
        return pyodbc.connect(conn_str, timeout=3)
    except Exception as e:
        print(f"Aviso BD (Modo Offline activo): {e}")
        return None


def db_query(query, params=(), commit=False, fetch=True):
    """Ejecuta consultas en SQL Server. Retorna [] o False si la BD no está accesible."""
    conn = get_db_connection()
    if conn is None:
        return [] if fetch else False

    try:
        cursor = conn.cursor()
        cursor.execute(query, params)

        result = True if commit else None
        if fetch and cursor.description:
            columns = [col[0] for col in cursor.description]
            result = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if commit:
            conn.commit()

        return result if result is not None else []
    except Exception as e:
        if conn and commit:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"Error en consulta SQL: {e}")
        return [] if fetch else False
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def db_query_get_id(query, params=()):
    """Ejecuta un INSERT y devuelve el ID generado. Retorna None si la BD no está accesible."""
    conn = get_db_connection()
    if conn is None:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        cursor.execute("SELECT SCOPE_IDENTITY() AS id")
        row = cursor.fetchone()
        new_id = int(row[0]) if row and row[0] is not None else None
        conn.commit()
        return new_id
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"Error en INSERT SQL: {e}")
        return None
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


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
    """Consulta DNI mediante APIs Perú o Decolecta."""
    if len(dni) != 8 or not dni.isdigit():
        return jsonify({'error': 'El DNI debe contener exactamente 8 dígitos numéricos'}), 400

    token_decolecta = os.getenv('RENIEC_TOKEN_DECOLECTA', '').strip()
    token_apisperu = os.getenv('RENIEC_TOKEN_APISPERU', os.getenv('RENIEC_TOKEN', '')).strip()

    if not token_decolecta and not token_apisperu:
        return jsonify({
            'error': 'La consulta RENIEC requiere un token configurado en el archivo .env.'
        }), 503

    # Proveedor 1: Decolecta
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

    # Proveedor 2: ApisPerú
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
        p_rows = db_query("SELECT COUNT(*) AS total FROM dbo.Pacientes")
        c_rows = db_query("SELECT COUNT(*) AS total FROM dbo.CitasMedicas")
        m_rows = db_query("SELECT COUNT(*) AS total FROM dbo.PersonalMedico")
        h_rows = db_query("SELECT COUNT(*) AS total FROM dbo.Hospitalizacion WHERE estado='Activo'")
        ing_rows = db_query("""
            SELECT SUM(monto_total) AS total FROM dbo.ComprobantesFacturacion
            WHERE CAST(fecha_emision AS DATE) = CAST(GETDATE() AS DATE)
        """)

        p_count = p_rows[0]['total'] if p_rows and len(p_rows) > 0 else 0
        c_count = c_rows[0]['total'] if c_rows and len(c_rows) > 0 else 0
        m_count = m_rows[0]['total'] if m_rows and len(m_rows) > 0 else 0
        h_count = h_rows[0]['total'] if h_rows and len(h_rows) > 0 else 0
        ingresos = float(ing_rows[0]['total']) if ing_rows and len(ing_rows) > 0 and ing_rows[0]['total'] else 0.0

        return jsonify({
            'pacientes': p_count,
            'citas': c_count,
            'medicos': m_count,
            'hospitalizados': h_count,
            'ingresos': ingresos
        })
    except Exception as e:
        print(f"Error en Dashboard: {e}")
        return jsonify({'pacientes': 0, 'citas': 0, 'medicos': 0, 'hospitalizados': 0, 'ingresos': 0.0})


# ==========================================
# 1. MÓDULO PACIENTES
# ==========================================
@app.route('/api/pacientes', methods=['GET'])
def get_pacientes():
    rows = db_query("""
        SELECT id, dni, nombre, apellido,
               CONVERT(VARCHAR(10), fecha_nacimiento, 120) AS fnac,
               genero, telefono, email, direccion, latitud, longitud,
               grupo_sanguineo, alergias
        FROM dbo.Pacientes ORDER BY id DESC
    """)
    return jsonify(rows if isinstance(rows, list) else [])


@app.route('/api/pacientes', methods=['POST'])
def save_paciente():
    try:
        data = request.json or {}
        p_id = data.get('id')
        if p_id:
            db_query("""
                UPDATE dbo.Pacientes
                SET dni=?, nombre=?, apellido=?, fecha_nacimiento=?, genero=?, telefono=?, email=?,
                    direccion=?, latitud=?, longitud=?, grupo_sanguineo=?, alergias=?
                WHERE id=?
            """, (data.get('dni'), data.get('nombre'), data.get('apellido'), data.get('fnac') or None,
                  data.get('genero'), data.get('tel'), data.get('email'), data.get('direccion'),
                  data.get('latitud'), data.get('longitud'), data.get('grupo_sanguineo'),
                  data.get('alergias'), p_id), commit=True)
            return jsonify({'message': 'Paciente actualizado exitosamente', 'id': p_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO dbo.Pacientes (dni, nombre, apellido, fecha_nacimiento, genero, telefono, email,
                                            direccion, latitud, longitud, grupo_sanguineo, alergias)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data.get('dni'), data.get('nombre'), data.get('apellido'), data.get('fnac') or None,
                  data.get('genero'), data.get('tel'), data.get('email'), data.get('direccion'),
                  data.get('latitud'), data.get('longitud'), data.get('grupo_sanguineo'), data.get('alergias')))
            return jsonify({'message': 'Paciente guardado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pacientes/<int:id>', methods=['DELETE'])
def delete_paciente(id):
    db_query("DELETE FROM dbo.Pacientes WHERE id=?", (id,), commit=True)
    return jsonify({'message': 'Paciente eliminado de SQL Server'})


# ==========================================
# 2. MÓDULO ESPECIALIDADES
# ==========================================
@app.route('/api/especialidades', methods=['GET'])
def get_especialidades():
    rows = db_query("SELECT id, nombre, descripcion FROM dbo.Especialidades ORDER BY nombre")
    return jsonify(rows if isinstance(rows, list) else [])


# ==========================================
# 3. MÓDULO PERSONAL MÉDICO
# ==========================================
@app.route('/api/medicos', methods=['GET'])
def get_medicos():
    rows = db_query("""
        SELECT m.id, m.dni, m.nombre, m.apellido, m.colegiatura_cmp AS cmp,
               m.especialidad_id, e.nombre AS especialidad, m.telefono AS tel, m.email
        FROM dbo.PersonalMedico m
        LEFT JOIN dbo.Especialidades e ON m.especialidad_id = e.id
        ORDER BY m.id DESC
    """)
    return jsonify(rows if isinstance(rows, list) else [])


@app.route('/api/medicos', methods=['POST'])
def save_medico():
    try:
        data = request.json or {}
        m_id = data.get('id')
        if m_id:
            db_query("""
                UPDATE dbo.PersonalMedico
                SET dni=?, nombre=?, apellido=?, colegiatura_cmp=?, especialidad_id=?, telefono=?, email=?
                WHERE id=?
            """, (data.get('dni'), data.get('nombre'), data.get('apellido'), data.get('cmp'),
                  data.get('especialidad_id'), data.get('tel'), data.get('email'), m_id), commit=True)
            return jsonify({'message': 'Personal médico actualizado exitosamente', 'id': m_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO dbo.PersonalMedico (dni, nombre, apellido, colegiatura_cmp, especialidad_id, telefono, email)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (data.get('dni'), data.get('nombre'), data.get('apellido'), data.get('cmp'),
                  data.get('especialidad_id'), data.get('tel'), data.get('email')))
            return jsonify({'message': 'Personal médico guardado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/medicos/<int:id>', methods=['DELETE'])
def delete_medico(id):
    db_query("DELETE FROM dbo.PersonalMedico WHERE id=?", (id,), commit=True)
    return jsonify({'message': 'Personal médico eliminado'})


# ==========================================
# 4. MÓDULO CITAS MÉDICAS
# ==========================================
@app.route('/api/citas', methods=['GET'])
def get_citas():
    rows = db_query("""
        SELECT c.id, c.paciente_id, c.medico_id,
               CONVERT(VARCHAR(10), c.fecha_cita, 120) AS fecha,
               CONVERT(VARCHAR(5), c.hora_cita, 108) AS hora,
               c.estado, c.motivo,
               CONCAT(p.nombre, ' ', p.apellido) AS paciente_nombre,
               CONCAT('Dr(a). ', m.nombre, ' ', m.apellido) AS medico_nombre
        FROM dbo.CitasMedicas c
        LEFT JOIN dbo.Pacientes p ON c.paciente_id = p.id
        LEFT JOIN dbo.PersonalMedico m ON c.medico_id = m.id
        ORDER BY c.fecha_cita DESC, c.hora_cita DESC
    """)
    return jsonify(rows if isinstance(rows, list) else [])


@app.route('/api/citas', methods=['POST'])
def save_cita():
    try:
        data = request.json or {}
        c_id = data.get('id')
        if c_id:
            db_query("""
                UPDATE dbo.CitasMedicas
                SET paciente_id=?, medico_id=?, fecha_cita=?, hora_cita=?, estado=?, motivo=?
                WHERE id=?
            """, (data.get('paciente_id'), data.get('medico_id'), data.get('fecha'), data.get('hora'),
                  data.get('estado'), data.get('motivo'), c_id), commit=True)
            return jsonify({'message': 'Cita médica actualizada exitosamente', 'id': c_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO dbo.CitasMedicas (paciente_id, medico_id, fecha_cita, hora_cita, estado, motivo)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (data.get('paciente_id'), data.get('medico_id'), data.get('fecha'), data.get('hora'),
                  data.get('estado', 'Programada'), data.get('motivo')))
            return jsonify({'message': 'Cita médica guardada exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/citas/<int:id>', methods=['DELETE'])
def delete_cita(id):
    db_query("DELETE FROM dbo.CitasMedicas WHERE id=?", (id,), commit=True)
    return jsonify({'message': 'Cita eliminada'})


# ==========================================
# 5. MÓDULO TRIAJE
# ==========================================
@app.route('/api/triaje', methods=['GET'])
def get_triaje():
    rows = db_query("""
        SELECT t.id, t.cita_id, t.paciente_id, t.presion_arterial AS presion, t.temperatura AS temp,
               t.frecuencia_cardiaca AS fc, t.frecuencia_respiratoria AS fr,
               t.saturacion_oxigeno AS so2, t.peso_kg AS peso, t.talla_cm AS talla, t.imc,
               CONCAT(p.nombre, ' ', p.apellido) AS paciente
        FROM dbo.Triaje t
        LEFT JOIN dbo.Pacientes p ON t.paciente_id = p.id
        ORDER BY t.id DESC
    """)
    return jsonify(rows if isinstance(rows, list) else [])


@app.route('/api/triaje', methods=['POST'])
def save_triaje():
    try:
        data = request.json or {}
        t_id = data.get('id')

        peso = float(data.get('peso', 0) or 0)
        talla_m = float(data.get('talla', 1) or 1) / 100
        imc = round(peso / (talla_m * talla_m), 2) if talla_m > 0 else 0

        cita_id = data.get('cita_id')
        cita_row = db_query("SELECT paciente_id FROM dbo.CitasMedicas WHERE id=?", (cita_id,))
        paciente_id = cita_row[0]['paciente_id'] if cita_row and len(cita_row) > 0 else data.get('paciente_id')

        if t_id:
            db_query("""
                UPDATE dbo.Triaje
                SET cita_id=?, paciente_id=?, presion_arterial=?, temperatura=?, frecuencia_cardiaca=?,
                    saturacion_oxigeno=?, peso_kg=?, talla_cm=?, imc=?
                WHERE id=?
            """, (cita_id, paciente_id, data.get('presion'), data.get('temp'), data.get('fc'),
                  data.get('so2'), data.get('peso'), data.get('talla'), imc, t_id), commit=True)
            return jsonify({'message': 'Triaje actualizado exitosamente', 'id': t_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO dbo.Triaje (cita_id, paciente_id, presion_arterial, temperatura,
                                         frecuencia_cardiaca, saturacion_oxigeno, peso_kg, talla_cm, imc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (cita_id, paciente_id, data.get('presion'), data.get('temp'), data.get('fc'),
                  data.get('so2'), data.get('peso'), data.get('talla'), imc))

            if cita_id:
                db_query("UPDATE dbo.CitasMedicas SET estado='En Triaje' WHERE id=?", (cita_id,), commit=True, fetch=False)
            return jsonify({'message': 'Triaje guardado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/triaje/<int:id>', methods=['DELETE'])
def delete_triaje(id):
    db_query("DELETE FROM dbo.Triaje WHERE id=?", (id,), commit=True)
    return jsonify({'message': 'Triaje eliminado'})


# ==========================================
# 6. MÓDULO HISTORIAL CLÍNICO
# ==========================================
@app.route('/api/historial', methods=['GET'])
def get_historial():
    rows = db_query("""
        SELECT h.id, h.cita_id, h.paciente_id, h.medico_id, h.motivo_consulta, h.sintomas,
               h.diagnostico, h.codigo_cie10 AS cie10, h.tratamiento, h.observaciones,
               CONVERT(VARCHAR(19), h.fecha_atencion, 120) AS fecha,
               CONCAT(p.nombre, ' ', p.apellido) AS paciente,
               CONCAT('Dr(a). ', m.nombre, ' ', m.apellido) AS medico
        FROM dbo.HistorialClinico h
        LEFT JOIN dbo.Pacientes p ON h.paciente_id = p.id
        LEFT JOIN dbo.PersonalMedico m ON h.medico_id = m.id
        ORDER BY h.id DESC
    """)
    return jsonify(rows if isinstance(rows, list) else [])


@app.route('/api/historial', methods=['POST'])
def save_historial():
    try:
        data = request.json or {}
        h_id = data.get('id')
        cita_id = data.get('cita_id')

        cita_row = db_query("SELECT paciente_id, medico_id FROM dbo.CitasMedicas WHERE id=?", (cita_id,))
        if not cita_row or len(cita_row) == 0:
            return jsonify({'error': 'La cita seleccionada no existe o no hay conexión con la base de datos'}), 400
        paciente_id = cita_row[0]['paciente_id']
        medico_id = cita_row[0]['medico_id']

        if h_id:
            db_query("""
                UPDATE dbo.HistorialClinico
                SET cita_id=?, paciente_id=?, medico_id=?, sintomas=?, diagnostico=?, codigo_cie10=?, tratamiento=?
                WHERE id=?
            """, (cita_id, paciente_id, medico_id, data.get('sintomas'), data.get('diagnostico'),
                  data.get('cie10'), data.get('tratamiento'), h_id), commit=True)
            return jsonify({'message': 'Historial clínico actualizado exitosamente', 'id': h_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO dbo.HistorialClinico (cita_id, paciente_id, medico_id, sintomas, diagnostico,
                                                   codigo_cie10, tratamiento)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (cita_id, paciente_id, medico_id, data.get('sintomas'), data.get('diagnostico'),
                  data.get('cie10'), data.get('tratamiento')))
            db_query("UPDATE dbo.CitasMedicas SET estado='Atendido' WHERE id=?", (cita_id,), commit=True, fetch=False)
            return jsonify({'message': 'Historial clínico guardado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/historial/<int:id>', methods=['DELETE'])
def delete_historial(id):
    db_query("DELETE FROM dbo.HistorialClinico WHERE id=?", (id,), commit=True)
    return jsonify({'message': 'Historial eliminado'})


# ==========================================
# 7. MÓDULO CAJA Y FACTURACIÓN
# ==========================================
@app.route('/api/facturacion', methods=['GET'])
def get_facturacion():
    rows = db_query("""
        SELECT f.id, f.paciente_id, f.tipo_comprobante AS tipo, f.numero_serie AS serie,
               f.numero_correlativo AS correlativo, f.monto_subtotal, f.monto_igv,
               f.monto_total AS monto, f.metodo_pago AS metodo, f.estado,
               CONVERT(VARCHAR(19), f.fecha_emision, 120) AS fecha,
               CONCAT(p.nombre, ' ', p.apellido) AS paciente
        FROM dbo.ComprobantesFacturacion f
        LEFT JOIN dbo.Pacientes p ON f.paciente_id = p.id
        ORDER BY f.id DESC
    """)
    return jsonify(rows if isinstance(rows, list) else [])


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
                UPDATE dbo.ComprobantesFacturacion
                SET paciente_id=?, tipo_comprobante=?, numero_serie=?, numero_correlativo=?,
                    monto_subtotal=?, monto_igv=?, monto_total=?, metodo_pago=?
                WHERE id=?
            """, (data.get('paciente_id'), data.get('tipo'), data.get('serie'), data.get('correlativo'),
                  monto_subtotal, monto_igv, monto_total, data.get('metodo'), f_id), commit=True)
            return jsonify({'message': 'Comprobante actualizado exitosamente', 'id': f_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO dbo.ComprobantesFacturacion (paciente_id, tipo_comprobante, numero_serie,
                    numero_correlativo, monto_subtotal, monto_igv, monto_total, metodo_pago)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (data.get('paciente_id'), data.get('tipo'), data.get('serie'), data.get('correlativo'),
                  monto_subtotal, monto_igv, monto_total, data.get('metodo')))
            return jsonify({'message': 'Comprobante registrado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/facturacion/<int:id>', methods=['DELETE'])
def delete_facturacion(id):
    db_query("UPDATE dbo.ComprobantesFacturacion SET estado='Anulado' WHERE id=?", (id,), commit=True)
    return jsonify({'message': 'Comprobante anulado'})


# ==========================================
# 8. MÓDULO FARMACIA
# ==========================================
@app.route('/api/farmacia', methods=['GET'])
def get_farmacia():
    rows = db_query("""
        SELECT id, codigo, nombre, descripcion AS tipo, stock, precio_unitario AS precio,
               CONVERT(VARCHAR(10), fecha_vencimiento, 120) AS vencimiento
        FROM dbo.FarmaciaInsumos ORDER BY id DESC
    """)
    return jsonify(rows if isinstance(rows, list) else [])


@app.route('/api/farmacia', methods=['POST'])
def save_farmacia():
    try:
        data = request.json or {}
        far_id = data.get('id')
        if far_id:
            db_query("""
                UPDATE dbo.FarmaciaInsumos
                SET codigo=?, nombre=?, descripcion=?, stock=?, precio_unitario=?, fecha_vencimiento=?
                WHERE id=?
            """, (data.get('codigo'), data.get('nombre'), data.get('tipo'), data.get('stock'),
                  data.get('precio'), data.get('vencimiento'), far_id), commit=True)
            return jsonify({'message': 'Producto actualizado exitosamente', 'id': far_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO dbo.FarmaciaInsumos (codigo, nombre, descripcion, stock, precio_unitario, fecha_vencimiento)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (data.get('codigo'), data.get('nombre'), data.get('tipo'), data.get('stock'),
                  data.get('precio'), data.get('vencimiento')))
            return jsonify({'message': 'Producto de farmacia guardado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/farmacia/<int:id>', methods=['DELETE'])
def delete_farmacia(id):
    db_query("DELETE FROM dbo.FarmaciaInsumos WHERE id=?", (id,), commit=True)
    return jsonify({'message': 'Producto eliminado'})


# ==========================================
# 9. MÓDULO LABORATORIO
# ==========================================
@app.route('/api/laboratorio', methods=['GET'])
def get_laboratorio():
    rows = db_query("""
        SELECT l.id, l.paciente_id, l.medico_id, l.nombre_examen AS examen, l.estado, l.resultado,
               CONCAT(p.nombre, ' ', p.apellido) AS paciente
        FROM dbo.ExamenesLaboratorio l
        LEFT JOIN dbo.Pacientes p ON l.paciente_id = p.id
        ORDER BY l.id DESC
    """)
    return jsonify(rows if isinstance(rows, list) else [])


@app.route('/api/laboratorio', methods=['POST'])
def save_laboratorio():
    try:
        data = request.json or {}
        lab_id = data.get('id')
        fecha_resultado = datetime.now().strftime('%Y-%m-%d %H:%M:%S') if data.get('estado') == 'Completado' else None

        if lab_id:
            db_query("""
                UPDATE dbo.ExamenesLaboratorio
                SET paciente_id=?, medico_id=?, nombre_examen=?, estado=?, resultado=?, fecha_resultado=?
                WHERE id=?
            """, (data.get('paciente_id'), data.get('medico_id'), data.get('examen'), data.get('estado'),
                  data.get('resultado'), fecha_resultado, lab_id), commit=True)
            return jsonify({'message': 'Examen actualizado exitosamente', 'id': lab_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO dbo.ExamenesLaboratorio (paciente_id, medico_id, nombre_examen, estado, resultado)
                VALUES (?, ?, ?, ?, ?)
            """, (data.get('paciente_id'), data.get('medico_id'), data.get('examen'),
                  data.get('estado', 'Pendiente'), data.get('resultado')))
            return jsonify({'message': 'Examen guardado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/laboratorio/<int:id>', methods=['DELETE'])
def delete_laboratorio(id):
    db_query("DELETE FROM dbo.ExamenesLaboratorio WHERE id=?", (id,), commit=True)
    return jsonify({'message': 'Examen eliminado'})


# ==========================================
# 10. MÓDULO HOSPITALIZACIÓN (con camas reales)
# ==========================================
@app.route('/api/camas-disponibles', methods=['GET'])
def get_camas_disponibles():
    rows = db_query("""
        SELECT c.id, c.numero_cama, h.numero_habitacion, h.piso, h.tipo
        FROM dbo.Camas c
        JOIN dbo.Habitaciones h ON c.habitacion_id = h.id
        WHERE c.estado = 'Disponible'
        ORDER BY h.piso, h.numero_habitacion
    """)
    return jsonify(rows if isinstance(rows, list) else [])


@app.route('/api/hospitalizacion', methods=['GET'])
def get_hospitalizacion():
    rows = db_query("""
        SELECT h.id, h.paciente_id, h.medico_tratante_id AS medico_id, h.cama_id,
               h.diagnostico_ingreso AS diag, h.estado,
               CONVERT(VARCHAR(19), h.fecha_ingreso, 120) AS fecha,
               CONCAT(p.nombre, ' ', p.apellido) AS paciente,
               CONCAT('Dr(a). ', m.nombre, ' ', m.apellido) AS medico,
               CONCAT(hab.numero_habitacion, ' - ', c.numero_cama) AS cama
        FROM dbo.Hospitalizacion h
        LEFT JOIN dbo.Pacientes p ON h.paciente_id = p.id
        LEFT JOIN dbo.PersonalMedico m ON h.medico_tratante_id = m.id
        LEFT JOIN dbo.Camas c ON h.cama_id = c.id
        LEFT JOIN dbo.Habitaciones hab ON c.habitacion_id = hab.id
        ORDER BY h.id DESC
    """)
    return jsonify(rows if isinstance(rows, list) else [])


@app.route('/api/hospitalizacion', methods=['POST'])
def save_hospitalizacion():
    try:
        data = request.json or {}
        hosp_id = data.get('id')

        if hosp_id:
            db_query("""
                UPDATE dbo.Hospitalizacion
                SET paciente_id=?, medico_tratante_id=?, cama_id=?, diagnostico_ingreso=?
                WHERE id=?
            """, (data.get('paciente_id'), data.get('medico_id'), data.get('cama_id'),
                  data.get('diag'), hosp_id), commit=True)
            return jsonify({'message': 'Hospitalización actualizada exitosamente', 'id': hosp_id})
        else:
            new_id = db_query_get_id("""
                INSERT INTO dbo.Hospitalizacion (paciente_id, medico_tratante_id, cama_id, diagnostico_ingreso)
                VALUES (?, ?, ?, ?)
            """, (data.get('paciente_id'), data.get('medico_id'), data.get('cama_id'), data.get('diag')))
            db_query("UPDATE dbo.Camas SET estado='Ocupada' WHERE id=?", (data.get('cama_id'),), commit=True, fetch=False)
            return jsonify({'message': 'Paciente hospitalizado exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/hospitalizacion/<int:id>/alta', methods=['POST'])
def dar_alta(id):
    """Da de alta a un paciente y libera la cama."""
    try:
        row = db_query("SELECT cama_id FROM dbo.Hospitalizacion WHERE id=?", (id,))
        if not row or len(row) == 0:
            return jsonify({'error': 'Registro no encontrado'}), 404
        cama_id = row[0]['cama_id']

        db_query("""
            UPDATE dbo.Hospitalizacion SET estado='Alta', fecha_alta=GETDATE() WHERE id=?
        """, (id,), commit=True, fetch=False)

        if cama_id:
            db_query("UPDATE dbo.Camas SET estado='Disponible' WHERE id=?", (cama_id,), commit=True, fetch=False)

        return jsonify({'message': 'Paciente dado de alta y cama liberada exitosamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/hospitalizacion/<int:id>', methods=['DELETE'])
def delete_hospitalizacion(id):
    try:
        row = db_query("SELECT cama_id FROM dbo.Hospitalizacion WHERE id=?", (id,))
        db_query("DELETE FROM dbo.Hospitalizacion WHERE id=?", (id,), commit=True)
        if row and len(row) > 0 and row[0].get('cama_id'):
            db_query("UPDATE dbo.Camas SET estado='Disponible' WHERE id=?", (row[0]['cama_id'],), commit=True, fetch=False)
        return jsonify({'message': 'Registro de hospitalización eliminado y cama liberada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# 11. MÓDULO NOTIFICACIONES
# ==========================================
@app.route('/api/notificaciones', methods=['GET'])
def get_notificaciones():
    rows = db_query("""
        SELECT id, destinatario_email AS email, asunto, mensaje, tipo,
               CONVERT(VARCHAR(19), fecha_envio, 120) AS fecha
        FROM dbo.Notificaciones ORDER BY id DESC
    """)
    return jsonify(rows if isinstance(rows, list) else [])


@app.route('/api/notificaciones', methods=['POST'])
def save_notificacion():
    try:
        data = request.json or {}
        new_id = db_query_get_id("""
            INSERT INTO dbo.Notificaciones (destinatario_email, asunto, mensaje, tipo, enviado)
            VALUES (?, ?, ?, 'Email', 1)
        """, (data.get('email'), data.get('asunto'), data.get('mensaje')))
        return jsonify({'message': 'Notificación enviada y registrada exitosamente', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/notificaciones/<int:id>', methods=['DELETE'])
def delete_notificacion(id):
    db_query("DELETE FROM dbo.Notificaciones WHERE id=?", (id,), commit=True)
    return jsonify({'message': 'Notificación eliminada'})


# ==========================================
# EJECUCIÓN DEL SERVIDOR
# ==========================================
if __name__ == '__main__':
    app.run(debug=True, port=5000)