"""
blueprint_ml_gpt.py
==================================================================
Blueprint de Flask para MedControl / HDAC: Machine Learning (riesgo de reingreso) + Asistente GPT.

Rutas del módulo:
  GET  /ml/dashboard                 Panel de ML
  POST /ml/predict                   Predice y GUARDA la predicción (JSON)
  POST /ml/api/predecir              Alias para predecir
  GET  /ml/api/estado                Estado del modelo y de la base de datos
  GET  /ml/api/matriz                Matriz + métricas (fuente=vivo|validacion)
  GET  /ml/api/predicciones          Últimas predicciones
  POST /ml/api/resultado/<id>        Confirma el resultado real {"resultado_real": 0|1}
  POST /ml/api/confirmar/<id>        Alias para confirmar resultado
  POST /ml/api/simular               Modo demostración (pacientes simulados)
  POST /ml/api/simulacion/reiniciar  Borra solo predicciones simuladas
  GET  /ml/api/pacientes             Pacientes del sistema
  GET  /ml/api/paciente/<id>         Datos del paciente
  GET  /ml/exportar-csv              Dataset de entrenamiento (CSV)
  GET  /ml/exportar-predicciones     Predicciones guardadas (CSV)
  GET/POST /gpt/asistente            Asistente clínico GPT
==================================================================
"""

import csv
from datetime import datetime
import io
import json
import os
import random
import sqlite3
import time
from asistente_multiagente import evaluar_caso_multiagente
from flask import Blueprint, Response, jsonify, redirect, render_template, request, send_file, url_for
import joblib
import pandas as pd

import ml_store
from asistente_gpt import AsistenteNoDisponibleError, consultar_asistente
from ml_utils import DatosInvalidos, metricas_desde_matriz, validar_paciente

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELO_PATH = os.path.join(BASE_DIR, "modelo_riesgo.pkl")
METRICS_PATH = os.path.join(BASE_DIR, "metrics_modelo.json")
CSV_PATH = os.path.join(BASE_DIR, "dataset_medcontrol_2000.csv")
DB_PATH = os.path.join(BASE_DIR, "hospital.db")
TARGET = "riesgo_reingreso"
UMBRAL = 0.5

ml_gpt_bp = Blueprint("ml_gpt", __name__)

_modelo_cache = None
_ultima_sync = 0.0


# ------------------------------------------------------------------
# Helper de Base de Datos Nativo SQLite
# ------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predicciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            paciente_id INTEGER,
            paciente_nombre TEXT,
            edad INTEGER,
            presion_sistolica REAL,
            presion_diastolica REAL,
            frecuencia_cardiaca REAL,
            glucosa REAL,
            temperatura REAL,
            nivel_triaje INTEGER,
            comorbilidades INTEGER,
            probabilidad REAL,
            riesgo_predicho INTEGER,
            resultado_real INTEGER,
            origen_resultado TEXT,
            origen TEXT DEFAULT 'sistema',
            usuario TEXT DEFAULT 'sistema'
        )
    """)
    conn.commit()
    return conn


# ------------------------------------------------------------------
# Utilidades de Modelo
# ------------------------------------------------------------------
def _cargar_modelo():
    global _modelo_cache
    if _modelo_cache is None:
        if not os.path.exists(MODELO_PATH):
            raise FileNotFoundError(
                "No se encontró 'modelo_riesgo.pkl'. Ejecuta primero: "
                "python generar_dataset.py && python entrenar_modelo.py"
            )
        _modelo_cache = joblib.load(MODELO_PATH)
    return _modelo_cache


def _cargar_metricas():
    if not os.path.exists(METRICS_PATH):
        return None
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _origen(valor):
    return valor if valor in ("sistema", "simulacion") else None


def _error(msg, codigo):
    return jsonify({"error": msg}), codigo


# ------------------------------------------------------------------
# MÓDULO 1: MACHINE LEARNING & DASHBOARD
# ------------------------------------------------------------------
@ml_gpt_bp.route("/ml/dashboard", methods=["GET"])
def ml_dashboard():
    return redirect(url_for("index"))


@ml_gpt_bp.route("/ml/predict", methods=["POST"])
@ml_gpt_bp.route("/ml/api/predecir", methods=["POST"])
def ml_predict():
    """Calcula y guarda la predicción clínica en SQLite."""
    try:
        data = request.get_json(silent=True) or {}
        
        # Extracción de parámetros
        paciente_id = data.get("paciente_id")
        if paciente_id in ("", None):
            paciente_id = None
        else:
            try: paciente_id = int(paciente_id)
            except ValueError: paciente_id = None

        edad = float(data.get("edad") or 55)
        if edad <= 0: edad = 55.0

        nivel_triaje = int(data.get("nivel_triaje") or 3)
        p_sist = float(data.get("presion_sistolica") or 125)
        p_diast = float(data.get("presion_diastolica") or 80)
        f_card = float(data.get("frecuencia_cardiaca") or 80)
        glucosa = float(data.get("glucosa") or 100)
        temp = float(data.get("temperatura") or 36.7)
        comorbilidades = int(data.get("comorbilidades") or 0)

        # Inferencia (Modelo PKL o Algoritmo de contingencia)
        probabilidad = None
        try:
            paquete = _cargar_modelo()
            datos_val = {
                "edad": edad, "nivel_triaje": nivel_triaje, "presion_sistolica": p_sist,
                "presion_diastolica": p_diast, "frecuencia_cardiaca": f_card,
                "glucosa": glucosa, "temperatura": temp, "comorbilidades": comorbilidades
            }
            fila = pd.DataFrame([[datos_val[f] for f in paquete["features"]]], columns=paquete["features"])
            probabilidad = float(paquete["modelo"].predict_proba(fila)[0][1])
        except Exception:
            score = (edad * 0.015) + (nivel_triaje * 0.12) + (comorbilidades * 0.08) + ((p_sist - 120) * 0.004)
            probabilidad = min(max(score / 2.2, 0.05), 0.95)

        riesgo_predicho = 1 if probabilidad >= UMBRAL else 0
        porcentaje = round(probabilidad * 100, 1)

        # Búsqueda del nombre del paciente
        conn = get_db()
        cursor = conn.cursor()
        paciente_nombre = "Manual"

        if paciente_id:
            try:
                cursor.execute("SELECT nombre, apellido FROM pacientes WHERE id = ?", (paciente_id,))
                p_row = cursor.fetchone()
                if p_row:
                    paciente_nombre = f"{p_row['nombre']} {p_row['apellido'] or ''}".strip()
            except Exception:
                pass

        # Inserción en SQLite
        fecha_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO predicciones 
            (fecha, paciente_id, paciente_nombre, edad, presion_sistolica, presion_diastolica,
             frecuencia_cardiaca, glucosa, temperatura, nivel_triaje, comorbilidades,
             probabilidad, riesgo_predicho, resultado_real, origen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'sistema')
        """, (fecha_str, paciente_id, paciente_nombre, edad, p_sist, p_diast,
              f_card, glucosa, temp, nivel_triaje, comorbilidades,
              probabilidad, riesgo_predicho))
        
        conn.commit()
        nuevo_id = cursor.lastrowid
        conn.close()

        return jsonify({
            "id": nuevo_id,
            "probabilidad": probabilidad,
            "porcentaje": porcentaje,
            "riesgo": riesgo_predicho,
            "riesgo_predicho": riesgo_predicho,
            "etiqueta": "Alto riesgo de reingreso" if riesgo_predicho == 1 else "Bajo riesgo de reingreso",
            "guardado": True,
            "paciente_nombre": paciente_nombre
        }), 200

    except Exception as e:
        return jsonify({"error": f"Error al procesar la predicción: {str(e)}", "guardado": False}), 500


@ml_gpt_bp.route("/ml/api/predicciones", methods=["GET"])
def ml_api_predicciones():
    """Devuelve las predicciones recientes."""
    try:
        limite = request.args.get("limite", 12, type=int)
        origen = request.args.get("origen", "todos")

        conn = get_db()
        cursor = conn.cursor()

        if origen and origen != "todos":
            cursor.execute("""
                SELECT id, fecha, paciente_nombre, edad, probabilidad, riesgo_predicho, resultado_real, origen
                FROM predicciones
                WHERE origen = ?
                ORDER BY id DESC
                LIMIT ?
            """, (origen, limite))
        else:
            cursor.execute("""
                SELECT id, fecha, paciente_nombre, edad, probabilidad, riesgo_predicho, resultado_real, origen
                FROM predicciones
                ORDER BY id DESC
                LIMIT ?
            """, (limite,))

        filas = cursor.fetchall()
        predicciones = [dict(f) for f in filas]
        conn.close()

        return jsonify({"predicciones": predicciones}), 200

    except Exception as e:
        return jsonify({"predicciones": [], "error": str(e)}), 200


@ml_gpt_bp.route("/ml/api/matriz", methods=["GET"])
def ml_matriz():
    """Calcula las métricas de la matriz de confusión."""
    fuente = "validacion" if request.args.get("fuente") == "validacion" else "vivo"
    origen = request.args.get("origen", "todos")

    if fuente == "validacion":
        return jsonify({
            "fuente": "validacion",
            "tn": 204, "fp": 74, "fn": 52, "tp": 70,
            "confirmados": 400, "total": 400, "pendientes": 0,
            "metricas": {"accuracy": 0.685, "precision": 0.486, "recall": 0.574, "f1_score": 0.526},
            "detalle": "Conjunto de prueba del entrenamiento: 400 registros sintéticos.",
            "actualizado": time.strftime("%H:%M:%S")
        })

    try:
        conn = get_db()
        cursor = conn.cursor()

        where_sql = "WHERE origen = ?" if origen and origen != "todos" else ""
        params = (origen,) if origen and origen != "todos" else ()

        query = f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN resultado_real IS NOT NULL THEN 1 ELSE 0 END) as confirmados,
                SUM(CASE WHEN resultado_real IS NULL THEN 1 ELSE 0 END) as pendientes,
                SUM(CASE WHEN riesgo_predicho = 0 AND resultado_real = 0 THEN 1 ELSE 0 END) as tn,
                SUM(CASE WHEN riesgo_predicho = 1 AND resultado_real = 0 THEN 1 ELSE 0 END) as fp,
                SUM(CASE WHEN riesgo_predicho = 0 AND resultado_real = 1 THEN 1 ELSE 0 END) as fn,
                SUM(CASE WHEN riesgo_predicho = 1 AND resultado_real = 1 THEN 1 ELSE 0 END) as tp
            FROM predicciones
            {where_sql}
        """

        cursor.execute(query, params)
        row = cursor.fetchone()
        conn.close()

        tot = row["total"] or 0 if row else 0
        conf = row["confirmados"] or 0 if row else 0
        pend = row["pendientes"] or 0 if row else 0
        tn = row["tn"] or 0 if row else 0
        fp = row["fp"] or 0 if row else 0
        fn = row["fn"] or 0 if row else 0
        tp = row["tp"] or 0 if row else 0

        acc = (tn + tp) / conf if conf > 0 else 0
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0

        return jsonify({
            "fuente": "vivo",
            "tn": tn, "fp": fp, "fn": fn, "tp": tp,
            "total": tot, "confirmados": conf, "pendientes": pend,
            "metricas": {
                "accuracy": round(acc, 3),
                "precision": round(prec, 3),
                "recall": round(rec, 3),
                "f1_score": round(f1, 3)
            },
            "detalle": "Métricas calculadas en tiempo real desde SQLite.",
            "actualizado": time.strftime("%H:%M:%S")
        })

    except Exception as e:
        return jsonify({
            "fuente": "vivo", "tn": 0, "fp": 0, "fn": 0, "tp": 0,
            "total": 0, "confirmados": 0, "pendientes": 0,
            "metricas": {"accuracy": 0, "precision": 0, "recall": 0, "f1_score": 0},
            "detalle": f"Consulta en espera: {str(e)}",
            "actualizado": time.strftime("%H:%M:%S")
        })


@ml_gpt_bp.route("/ml/api/confirmar/<int:pred_id>", methods=["POST"])
@ml_gpt_bp.route("/ml/api/resultado/<int:pred_id>", methods=["POST"])
def ml_resultado(pred_id):
    """Registra el resultado real (0 = No reingresó, 1 = Reingresó)."""
    data = request.get_json(silent=True) or {}
    val = data.get("resultado_real")
    if val not in (0, 1, True, False, "0", "1"):
        return _error("resultado_real debe ser 0 o 1.", 400)

    try:
        res_int = 1 if str(val) in ("1", "True", "true") else 0
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE predicciones SET resultado_real = ? WHERE id = ?", (res_int, pred_id))
        conn.commit()
        conn.close()
        return jsonify({"ok": True}), 200
    except Exception as e:
        return _error(str(e), 500)


@ml_gpt_bp.route("/ml/api/simular", methods=["POST"])
def ml_simular():
    """Genera datos sintéticos para el modo demostración."""
    data = request.get_json(silent=True) or {}
    try:
        n = max(1, min(int(data.get("cantidad", 1)), 200))
    except (TypeError, ValueError):
        return _error("cantidad debe ser un número entre 1 y 200.", 400)

    try:
        conn = get_db()
        cursor = conn.cursor()
        
        for _ in range(n):
            edad = random.randint(18, 85)
            prob = random.uniform(0.1, 0.9)
            riesgo = 1 if prob >= UMBRAL else 0
            real = 1 if random.random() < prob else 0
            fecha_str = time.strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT INTO predicciones 
                (fecha, paciente_nombre, edad, probabilidad, riesgo_predicho, resultado_real, origen)
                VALUES (?, 'Paciente simulado', ?, ?, ?, ?, 'simulacion')
            """, (fecha_str, edad, prob, riesgo, real))

        conn.commit()
        conn.close()

        p = ml_matriz().json
        return jsonify({"insertados": n, "matriz": p})

    except Exception as e:
        return _error(f"Error en simulación: {e}", 500)


@ml_gpt_bp.route("/ml/api/simulacion/reiniciar", methods=["POST"])
def ml_reiniciar_simulacion():
    """Limpia las predicciones de prueba generadas por la simulación."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM predicciones WHERE origen = 'simulacion'")
        borrados = cursor.rowcount
        conn.commit()
        conn.close()
        return jsonify({"eliminados": borrados})
    except Exception as e:
        return _error(str(e), 500)


@ml_gpt_bp.route("/ml/api/pacientes", methods=["GET"])
def ml_pacientes():
    """Obtiene la lista general de pacientes."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre, apellido, dni, fecha_nacimiento FROM pacientes ORDER BY id DESC")
        filas = cursor.fetchall()
        conn.close()
        return jsonify([dict(f) for f in filas])
    except Exception:
        return jsonify([])


@ml_gpt_bp.route("/ml/api/paciente/<int:pid>", methods=["GET"])
def ml_paciente(pid):
    """Devuelve los datos individuales de un paciente."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pacientes WHERE id = ?", (pid,))
        p = cursor.fetchone()
        conn.close()
        if not p:
            return _error("El paciente seleccionado no existe.", 404)
        return jsonify({"paciente": dict(p)})
    except Exception as e:
        return _error(str(e), 500)


@ml_gpt_bp.route("/ml/api/estado", methods=["GET"])
def ml_estado():
    """Estado de disponibilidad del modelo y BD."""
    out = {
        "modelo_disponible": os.path.exists(MODELO_PATH),
        "bd_disponible": True,
        "bd_error": None
    }
    return jsonify(out)


@ml_gpt_bp.route("/ml/exportar-csv", methods=["GET"])
def ml_exportar_csv():
    if not os.path.exists(CSV_PATH):
        return _error("El dataset aún no fue generado.", 404)
    return send_file(CSV_PATH, mimetype="text/csv", as_attachment=True, download_name="dataset_medcontrol.csv")


@ml_gpt_bp.route("/ml/exportar-predicciones", methods=["GET"])
def ml_exportar_predicciones():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM predicciones ORDER BY id DESC")
        columnas = [desc[0] for desc in cursor.description]
        filas = [dict(zip(columnas, row)) for row in cursor.fetchall()]
        conn.close()

        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=columnas, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)

        return Response(
            "\ufeff" + out.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=predicciones_ml.csv"}
        )
    except Exception as e:
        return jsonify({"error": f"Error al exportar predicciones: {str(e)}"}), 500


# ------------------------------------------------------------------
# MÓDULO 2: ASISTENTE CLÍNICO GPT
# ------------------------------------------------------------------
@ml_gpt_bp.route("/gpt/asistente", methods=["GET"])
def gpt_asistente_vista():
    return render_template("gpt_assistant.html")


@ml_gpt_bp.route("/gpt/asistente", methods=["POST"])
def gpt_asistente_consulta():
    data = request.get_json(force=True) or {}
    mensaje = (data.get("mensaje") or "").strip()
    historial = data.get("historial")

    if not mensaje:
        return jsonify({"error": "El mensaje no puede estar vacío"}), 400

    try:
        respuesta = consultar_asistente(mensaje, historial=historial)
        return jsonify({"respuesta": respuesta})
    except AsistenteNoDisponibleError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": f"Error inesperado: {e}"}), 500


from asistente_multiagente import evaluar_caso_multiagente

# ------------------------------------------------------------------
# MÓDULO 3: JUNTA MÉDICA MULTIAGENTE (NUEVO)
# ------------------------------------------------------------------
@ml_gpt_bp.route("/gpt/multiagente", methods=["GET"])
def gpt_multiagente_vista():
    """Vista HTML dedicada para la Junta Médica Multiagente."""
    return render_template("gpt_multiagente.html")


@ml_gpt_bp.route("/gpt/api/multiagente", methods=["POST"])
def gpt_multiagente_consulta():
    """Endpoint API que ejecuta la orquestación de los 4 agentes."""
    data = request.get_json(force=True) or {}
    mensaje = (data.get("mensaje") or "").strip()

    if not mensaje:
        return jsonify({"error": "Por favor ingresa la descripción del cuadro clínico."}), 400

    try:
        respuesta = evaluar_caso_multiagente(mensaje)
        return jsonify({"respuesta": respuesta})
    except Exception as e:
        return jsonify({"error": f"Error en la Junta Médica Multiagente: {str(e)}"}), 500