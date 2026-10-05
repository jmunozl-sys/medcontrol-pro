"""
ml_store.py
Persistencia (SQL Server) del módulo de Machine Learning: guarda cada predicción, registra el
resultado REAL cuando se conoce y calcula la matriz de confusión directamente desde la base de datos.

Tabla nueva y aislada: dbo.ML_Predicciones (no modifica ninguna tabla existente).

Cómo se obtiene el resultado real (resultado_real = 1 si hubo reingreso):
  * 'manual'          -> el personal confirma el resultado desde el dashboard.
  * 'hospitalizacion' -> automático: el paciente tiene un nuevo ingreso en dbo.Hospitalizacion
                         dentro de VENTANA_DIAS días posteriores a la predicción.
  * 'ventana_30d'     -> automático: pasó la ventana sin nuevo ingreso => resultado 0.
  * 'simulacion'      -> pacientes simulados (modo demostración), siempre marcados como tales.
"""
import os
from ml_utils import comorbilidades_desde_cie10, edad_desde_fecha, extraer_glucosa, parsear_presion

VENTANA_DIAS = 30

_fabrica_conexion = None
_tabla_lista = False


class BaseDatosError(Exception):
    """No se pudo usar SQL Server (conexión o consulta)."""


def configurar(fabrica):
    """app.py entrega su propia get_db_connection para reutilizar la misma configuración."""
    global _fabrica_conexion
    _fabrica_conexion = fabrica


def _abrir():
    try:
        if _fabrica_conexion:
            return _fabrica_conexion()
        import pyodbc
        srv = os.getenv("DB_SERVER", "DESKTOP-PEB6BCK")
        db = os.getenv("DB_NAME", "HDAC_Hospital_DB")
        base = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={srv};DATABASE={db};"
        try:
            return pyodbc.connect(base + "Trusted_Connection=yes;", timeout=5)
        except Exception:
            return pyodbc.connect(
                base + f"UID={os.getenv('DB_USER', 'sa')};PWD={os.getenv('DB_PASSWORD', '')};", timeout=5)
    except Exception as e:
        raise BaseDatosError(f"No se pudo conectar a SQL Server: {str(e)[:200]}")


def _ejecutar(sql, params=(), commit=False, fetch=True, devolver_id=False):
    conn = _abrir()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        nuevo_id = None
        if devolver_id:
            cur.execute("SELECT SCOPE_IDENTITY()")
            fila = cur.fetchone()
            nuevo_id = int(fila[0]) if fila and fila[0] is not None else None
        filas = None
        if fetch and cur.description:
            cols = [c[0] for c in cur.description]
            filas = [dict(zip(cols, r)) for r in cur.fetchall()]
        if commit or devolver_id:
            conn.commit()
        return nuevo_id if devolver_id else filas
    except BaseDatosError:
        raise
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        raise BaseDatosError(f"Error SQL: {str(e)[:200]}")
    finally:
        conn.close()


DDL = """
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ML_Predicciones')
CREATE TABLE dbo.ML_Predicciones (
    id INT IDENTITY(1,1) PRIMARY KEY,
    paciente_id INT NULL,
    paciente_nombre VARCHAR(160) NULL,
    fecha_prediccion DATETIME NOT NULL DEFAULT GETDATE(),
    edad INT NOT NULL,
    presion_sistolica INT NOT NULL,
    presion_diastolica INT NOT NULL,
    frecuencia_cardiaca INT NOT NULL,
    glucosa INT NOT NULL,
    temperatura DECIMAL(4,1) NOT NULL,
    nivel_triaje INT NOT NULL,
    comorbilidades INT NOT NULL,
    probabilidad DECIMAL(5,4) NOT NULL,
    riesgo_predicho BIT NOT NULL,
    resultado_real BIT NULL,
    fecha_resultado DATETIME NULL,
    origen_resultado VARCHAR(20) NULL,
    origen VARCHAR(12) NOT NULL DEFAULT 'sistema',
    usuario VARCHAR(50) NOT NULL DEFAULT 'admin',
    CONSTRAINT FK_ML_Predicciones_Pacientes FOREIGN KEY (paciente_id)
        REFERENCES dbo.Pacientes(id) ON DELETE SET NULL
)
"""


def asegurar_tabla():
    global _tabla_lista
    if not _tabla_lista:
        _ejecutar(DDL, commit=True, fetch=False)
        _tabla_lista = True


COLUMNAS_INSERT = ("""
    INSERT INTO dbo.ML_Predicciones (paciente_id, paciente_nombre, edad, presion_sistolica,
        presion_diastolica, frecuencia_cardiaca, glucosa, temperatura, nivel_triaje, comorbilidades,
        probabilidad, riesgo_predicho, resultado_real, fecha_resultado, origen_resultado, origen, usuario)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {fecha}, ?, ?, ?)
""")


def _params_insert(r):
    return (r.get("paciente_id"), r.get("paciente_nombre"), int(r["edad"]), int(r["presion_sistolica"]),
            int(r["presion_diastolica"]), int(r["frecuencia_cardiaca"]), int(r["glucosa"]),
            float(r["temperatura"]), int(r["nivel_triaje"]), int(r["comorbilidades"]),
            float(r["probabilidad"]), int(r["riesgo_predicho"]), r.get("resultado_real"),
            r.get("origen_resultado"), r.get("origen", "sistema"), r.get("usuario", "admin"))


def _sql_insert(r):
    # fecha_resultado se fija con GETDATE() solo cuando ya se conoce el resultado real
    return COLUMNAS_INSERT.format(fecha="GETDATE()" if r.get("resultado_real") is not None else "NULL")


def guardar_prediccion(r):
    """Guarda una predicción individual (resultado_real normalmente NULL = pendiente). Devuelve el id."""
    asegurar_tabla()
    return _ejecutar(_sql_insert(r), _params_insert(r), devolver_id=True)


def guardar_lote(filas):
    """Inserta varias predicciones (simulación) en una sola conexión/transacción."""
    if not filas:
        return 0
    asegurar_tabla()
    conn = _abrir()
    try:
        cur = conn.cursor()
        for r in filas:
            cur.execute(_sql_insert(r), _params_insert(r))
        conn.commit()
        return len(filas)
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        raise BaseDatosError(f"Error SQL: {str(e)[:200]}")
    finally:
        conn.close()


def registrar_resultado(pred_id, resultado, origen="manual"):
    """Confirma el resultado real de una predicción. Devuelve False si el id no existe."""
    asegurar_tabla()
    existe = _ejecutar("SELECT id FROM dbo.ML_Predicciones WHERE id=?", (pred_id,))
    if not existe:
        return False
    _ejecutar("""UPDATE dbo.ML_Predicciones
                 SET resultado_real=?, fecha_resultado=GETDATE(), origen_resultado=?
                 WHERE id=?""", (1 if resultado else 0, origen, pred_id), commit=True, fetch=False)
    return True


def sincronizar_resultados(dias=VENTANA_DIAS):
    """Resuelve automáticamente predicciones pendientes de pacientes registrados usando dbo.Hospitalizacion."""
    asegurar_tabla()
    conn = _abrir()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE p SET resultado_real = 1, fecha_resultado = GETDATE(), origen_resultado = 'hospitalizacion'
            FROM dbo.ML_Predicciones p
            WHERE p.resultado_real IS NULL AND p.paciente_id IS NOT NULL AND p.origen = 'sistema'
              AND EXISTS (SELECT 1 FROM dbo.Hospitalizacion h
                          WHERE h.paciente_id = p.paciente_id
                            AND h.fecha_ingreso > p.fecha_prediccion
                            AND h.fecha_ingreso <= DATEADD(DAY, ?, p.fecha_prediccion))
        """, (dias,))
        cur.execute("""
            UPDATE dbo.ML_Predicciones
            SET resultado_real = 0, fecha_resultado = GETDATE(), origen_resultado = 'ventana_30d'
            WHERE resultado_real IS NULL AND paciente_id IS NOT NULL AND origen = 'sistema'
              AND DATEADD(DAY, ?, fecha_prediccion) < GETDATE()
        """, (dias,))
        conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        raise BaseDatosError(f"Error SQL: {str(e)[:200]}")
    finally:
        conn.close()


def conteos(origen=None):
    """Totales de la matriz de confusión calculados en SQL a partir de los resultados confirmados."""
    asegurar_tabla()
    filtro, params = "", ()
    if origen in ("sistema", "simulacion"):
        filtro, params = "WHERE origen = ?", (origen,)
    r = _ejecutar(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN resultado_real IS NULL THEN 1 ELSE 0 END) AS pendientes,
               SUM(CASE WHEN riesgo_predicho = 0 AND resultado_real = 0 THEN 1 ELSE 0 END) AS tn,
               SUM(CASE WHEN riesgo_predicho = 1 AND resultado_real = 0 THEN 1 ELSE 0 END) AS fp,
               SUM(CASE WHEN riesgo_predicho = 0 AND resultado_real = 1 THEN 1 ELSE 0 END) AS fn,
               SUM(CASE WHEN riesgo_predicho = 1 AND resultado_real = 1 THEN 1 ELSE 0 END) AS tp
        FROM dbo.ML_Predicciones {filtro}
    """, params)[0]
    return {k: int(r[k] or 0) for k in ("total", "pendientes", "tn", "fp", "fn", "tp")}


def listar(limite=15, origen=None):
    asegurar_tabla()
    limite = max(1, min(int(limite), 500))
    filtro, params = "", ()
    if origen in ("sistema", "simulacion"):
        filtro, params = "WHERE origen = ?", (origen,)
    filas = _ejecutar(f"""
        SELECT TOP {limite} id, paciente_id, paciente_nombre,
               CONVERT(VARCHAR(19), fecha_prediccion, 120) AS fecha, edad, presion_sistolica,
               presion_diastolica, frecuencia_cardiaca, glucosa, temperatura, nivel_triaje,
               comorbilidades, probabilidad, riesgo_predicho, resultado_real, origen_resultado,
               origen, usuario
        FROM dbo.ML_Predicciones {filtro} ORDER BY id DESC
    """, params) or []
    for f in filas:
        f["temperatura"] = float(f["temperatura"])
        f["probabilidad"] = float(f["probabilidad"])
        f["riesgo_predicho"] = int(bool(f["riesgo_predicho"]))
        f["resultado_real"] = None if f["resultado_real"] is None else int(bool(f["resultado_real"]))
    return filas


def exportar_todo():
    return listar(500)


def reiniciar_simulacion():
    """Borra SOLO las predicciones simuladas; nunca toca las del sistema real."""
    asegurar_tabla()
    n = _ejecutar("SELECT COUNT(*) AS n FROM dbo.ML_Predicciones WHERE origen='simulacion'")[0]["n"]
    _ejecutar("DELETE FROM dbo.ML_Predicciones WHERE origen='simulacion'", commit=True, fetch=False)
    return int(n)


def listar_pacientes():
    filas = _ejecutar("SELECT id, dni, nombre, apellido FROM dbo.Pacientes ORDER BY id DESC") or []
    return [{"id": f["id"], "dni": f["dni"], "nombre": f"{f['nombre']} {f['apellido']}"} for f in filas]


def datos_paciente(pid):
    """Recupera del sistema lo que se pueda para el modelo. Devuelve None si el paciente no existe."""
    p = _ejecutar("""SELECT id, dni, nombre, apellido, fecha_nacimiento
                     FROM dbo.Pacientes WHERE id=?""", (pid,))
    if not p:
        return None
    p = p[0]
    datos, fuentes = {}, {}

    edad = edad_desde_fecha(p.get("fecha_nacimiento"))
    if edad is not None:
        datos["edad"], fuentes["edad"] = edad, "fecha de nacimiento"

    t = _ejecutar("""SELECT TOP 1 presion_arterial, temperatura, frecuencia_cardiaca,
                            CONVERT(VARCHAR(19), fecha_registro, 120) AS fecha
                     FROM dbo.Triaje WHERE paciente_id=? ORDER BY id DESC""", (pid,))
    if t:
        t = t[0]
        pa = parsear_presion(t.get("presion_arterial"))
        if pa:
            datos["presion_sistolica"], datos["presion_diastolica"] = pa
            fuentes["presion"] = f"triaje {t['fecha']}"
        if t.get("temperatura") is not None:
            datos["temperatura"] = float(t["temperatura"])
            fuentes["temperatura"] = f"triaje {t['fecha']}"
        if t.get("frecuencia_cardiaca") is not None:
            datos["frecuencia_cardiaca"] = int(t["frecuencia_cardiaca"])
            fuentes["frecuencia_cardiaca"] = f"triaje {t['fecha']}"

    try:
        g = _ejecutar("""SELECT TOP 1 resultado FROM dbo.ExamenesLaboratorio
                         WHERE paciente_id=? AND estado='Completado' AND nombre_examen LIKE '%gluc%'
                         ORDER BY id DESC""", (pid,))
        if g:
            val = extraer_glucosa(g[0].get("resultado"))
            if val:
                datos["glucosa"], fuentes["glucosa"] = val, "laboratorio"
    except BaseDatosError:
        pass

    try:
        codigos = _ejecutar("""SELECT DISTINCT codigo_cie10 FROM dbo.HistorialClinico
                               WHERE paciente_id=? AND codigo_cie10 IS NOT NULL""", (pid,))
        datos["comorbilidades"] = comorbilidades_desde_cie10([c["codigo_cie10"] for c in codigos or []])
        fuentes["comorbilidades"] = "diagnósticos CIE-10 del historial clínico"
    except BaseDatosError:
        pass

    return {"paciente": {"id": p["id"], "dni": p["dni"], "nombre": f"{p['nombre']} {p['apellido']}"},
            "datos": datos, "fuentes": fuentes}
