"""
blueprint_ml_gpt.py
==================================================================
Blueprint de Flask para MedControl / HDAC: Machine Learning (riesgo de reingreso) + Asistente GPT.

La matriz de confusión del dashboard YA NO es una imagen fija: se calcula en cada consulta a partir
de las predicciones guardadas en SQL Server (dbo.ML_Predicciones) y de sus resultados reales
confirmados. Ver ml_store.py para saber cómo se obtiene el resultado real.

Rutas:
  GET  /ml/dashboard                   Panel de ML
  POST /ml/predict                     Predice y GUARDA la predicción (JSON)
  GET  /ml/api/estado                  Estado del modelo y de la base de datos
  GET  /ml/api/matriz                  Matriz + métricas (fuente=vivo|validacion, origen=todos|sistema|simulacion)
  GET  /ml/api/predicciones            Últimas predicciones
  POST /ml/api/resultado/<id>          Confirma el resultado real {"resultado_real": 0|1}
  POST /ml/api/simular                 Modo demostración: pacientes simulados {"cantidad": 1..200}
  POST /ml/api/simulacion/reiniciar    Borra solo las predicciones simuladas
  GET  /ml/api/pacientes               Pacientes del sistema (selector)
  GET  /ml/api/paciente/<id>           Datos del paciente para autocompletar el formulario
  GET  /ml/exportar-csv                Dataset de entrenamiento
  GET  /ml/exportar-predicciones       Predicciones guardadas (CSV)
  GET/POST /gpt/asistente              Asistente clínico GPT
==================================================================
"""

import csv
import io
import json
import os
import random
import time

import joblib
import pandas as pd
from flask import Blueprint, Response, jsonify, render_template, request, send_file

import ml_store
from asistente_gpt import AsistenteNoDisponibleError, consultar_asistente
from ml_utils import DatosInvalidos, metricas_desde_matriz, validar_paciente

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELO_PATH = os.path.join(BASE_DIR, "modelo_riesgo.pkl")
METRICS_PATH = os.path.join(BASE_DIR, "metrics_modelo.json")
CSV_PATH = os.path.join(BASE_DIR, "dataset_medcontrol_2000.csv")
TARGET = "riesgo_reingreso"
UMBRAL = 0.5

ml_gpt_bp = Blueprint("ml_gpt", __name__)

_modelo_cache = None
_ultima_sync = 0.0


# ------------------------------------------------------------------
# Utilidades
# ------------------------------------------------------------------
def _cargar_modelo():
    global _modelo_cache
    if _modelo_cache is None:
        if not os.path.exists(MODELO_PATH):
            raise FileNotFoundError(
                "No se encontró 'modelo_riesgo.pkl'. Ejecuta primero: "
                "python generar_dataset.py && python entrenar_modelo.py")
        _modelo_cache = joblib.load(MODELO_PATH)
    return _modelo_cache


def _cargar_metricas():
    if not os.path.exists(METRICS_PATH):
        return None
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _validacion():
    """Matriz de confusión del conjunto de prueba (datos que el modelo NO vio al entrenar).
    Sale de metrics_modelo.json; si el JSON es antiguo, se recalcula con el mismo split (80/20,
    random_state=42, stratify) y se guarda para la próxima vez."""
    m = _cargar_metricas()
    if m is None:
        return None
    if "matriz_confusion" in m:
        return m
    from sklearn.metrics import confusion_matrix
    from sklearn.model_selection import train_test_split
    paquete = _cargar_modelo()
    feats = paquete["features"]
    df = pd.read_csv(CSV_PATH)
    _, X_te, _, y_te = train_test_split(df[feats], df[TARGET], test_size=0.20,
                                        random_state=42, stratify=df[TARGET])
    tn, fp, fn, tp = (int(v) for v in confusion_matrix(y_te, paquete["modelo"].predict(X_te),
                                                       labels=[0, 1]).ravel())
    m["matriz_confusion"] = {"tn": tn, "fp": fp, "fn": fn, "tp": tp}
    try:
        with open(METRICS_PATH, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
    return m


def _origen(valor):
    return valor if valor in ("sistema", "simulacion") else None


def _payload_matriz(fuente, origen):
    if fuente == "validacion":
        v = _validacion()
        if v is None:
            raise FileNotFoundError("Modelo no entrenado. Ejecuta: python entrenar_modelo.py")
        c = v["matriz_confusion"]
        tn, fp, fn, tp = c["tn"], c["fp"], c["fn"], c["tp"]
        return {"fuente": "validacion", "tn": tn, "fp": fp, "fn": fn, "tp": tp,
                "confirmados": tn + fp + fn + tp, "pendientes": 0, "total": tn + fp + fn + tp,
                "metricas": metricas_desde_matriz(tn, fp, fn, tp),
                "detalle": (f"Conjunto de prueba del entrenamiento: {v.get('n_prueba', tn + fp + fn + tp)} "
                            f"registros que el modelo no vio al entrenar (dataset sintético).")}
    global _ultima_sync
    if time.time() - _ultima_sync > 20:           # resolver resultados automáticos como máximo cada 20 s
        ml_store.sincronizar_resultados()
        _ultima_sync = time.time()
    c = ml_store.conteos(_origen(origen))
    conf = c["tn"] + c["fp"] + c["fn"] + c["tp"]
    return {"fuente": "vivo", "origen": origen or "todos", **c, "confirmados": conf,
            "metricas": metricas_desde_matriz(c["tn"], c["fp"], c["fn"], c["tp"]),
            "detalle": (f"{conf} predicciones con resultado real confirmado de {c['total']} guardadas "
                        f"({c['pendientes']} pendientes de confirmar).")}


def _error(msg, codigo):
    return jsonify({"error": msg}), codigo


# ------------------------------------------------------------------
# MÓDULO 1: MACHINE LEARNING
# ------------------------------------------------------------------
@ml_gpt_bp.route("/ml/dashboard", methods=["GET"])
def ml_dashboard():
    metricas = _cargar_metricas()
    modelo_disponible = metricas is not None and os.path.exists(MODELO_PATH)
    return render_template("ml_dashboard.html", metricas=metricas, modelo_disponible=modelo_disponible)


@ml_gpt_bp.route("/ml/predict", methods=["POST"])
def ml_predict():
    """JSON con las 8 variables (+ opcional paciente_id, guardar=false).
    Devuelve riesgo, probabilidad y el id con el que quedó guardada la predicción."""
    try:
        paquete = _cargar_modelo()
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return _error("Se esperaba un JSON con los datos clínicos.", 400)
        datos = validar_paciente(data)

        fila = pd.DataFrame([[datos[f] for f in paquete["features"]]], columns=paquete["features"])
        probabilidad = float(paquete["modelo"].predict_proba(fila)[0][1])
        riesgo = int(probabilidad >= UMBRAL)

        resp = {"riesgo": riesgo, "probabilidad": round(probabilidad, 4),
                "porcentaje": round(probabilidad * 100, 1),
                "etiqueta": "Alto riesgo de reingreso" if riesgo == 1 else "Bajo riesgo de reingreso",
                "guardado": False, "id": None}

        if data.get("guardar", True):
            try:
                pid = data.get("paciente_id")
                nombre = None
                if pid not in (None, ""):
                    info = ml_store.datos_paciente(int(pid))
                    if info is None:
                        return _error("El paciente seleccionado no existe.", 404)
                    pid, nombre = int(pid), info["paciente"]["nombre"]
                else:
                    pid = None
                resp["id"] = ml_store.guardar_prediccion({
                    **datos, "paciente_id": pid, "paciente_nombre": nombre,
                    "probabilidad": probabilidad, "riesgo_predicho": riesgo, "origen": "sistema"})
                resp["guardado"] = True
            except ml_store.BaseDatosError as e:
                resp["aviso_guardado"] = f"La predicción se calculó pero no se guardó: {e}"
        return jsonify(resp)
    except DatosInvalidos as e:
        return jsonify({"error": "Datos inválidos: " + "; ".join(e.errores.values()),
                        "detalles": e.errores}), 400
    except FileNotFoundError as e:
        return _error(str(e), 503)
    except (ValueError, TypeError) as e:
        return _error(f"Datos inválidos: {e}", 400)
    except Exception as e:
        return _error(f"Error inesperado: {e}", 500)


@ml_gpt_bp.route("/ml/api/estado", methods=["GET"])
def ml_estado():
    out = {"modelo_disponible": os.path.exists(MODELO_PATH) and os.path.exists(METRICS_PATH),
           "bd_disponible": False, "bd_error": None}
    try:
        ml_store.asegurar_tabla()
        out["bd_disponible"] = True
    except ml_store.BaseDatosError as e:
        out["bd_error"] = str(e)
    return jsonify(out)


@ml_gpt_bp.route("/ml/api/matriz", methods=["GET"])
def ml_matriz():
    fuente = "validacion" if request.args.get("fuente") == "validacion" else "vivo"
    try:
        p = _payload_matriz(fuente, request.args.get("origen"))
        p["actualizado"] = time.strftime("%H:%M:%S")
        return jsonify(p)
    except FileNotFoundError as e:
        return _error(str(e), 503)
    except ml_store.BaseDatosError as e:
        return _error(str(e), 503)
    except Exception as e:
        return _error(f"Error inesperado: {e}", 500)


@ml_gpt_bp.route("/ml/api/predicciones", methods=["GET"])
def ml_predicciones():
    try:
        limite = int(request.args.get("limite", 15))
    except ValueError:
        limite = 15
    try:
        return jsonify({"predicciones": ml_store.listar(limite, _origen(request.args.get("origen")))})
    except ml_store.BaseDatosError as e:
        return _error(str(e), 503)


@ml_gpt_bp.route("/ml/api/resultado/<int:pred_id>", methods=["POST"])
def ml_resultado(pred_id):
    data = request.get_json(silent=True) or {}
    if data.get("resultado_real") not in (0, 1, True, False, "0", "1"):
        return _error("resultado_real debe ser 0 (no reingresó) o 1 (reingresó).", 400)
    try:
        if not ml_store.registrar_resultado(pred_id, str(data["resultado_real"]) in ("1", "True", "true")):
            return _error("La predicción indicada no existe.", 404)
        return jsonify({"ok": True})
    except ml_store.BaseDatosError as e:
        return _error(str(e), 503)


@ml_gpt_bp.route("/ml/api/simular", methods=["POST"])
def ml_simular():
    """MODO DEMOSTRACIÓN: genera pacientes sintéticos NUEVOS (semilla aleatoria, nunca vistos en el
    entrenamiento), los pasa por el modelo y guarda predicción + resultado real simulado.
    Quedan marcados como origen='simulacion' y se pueden filtrar o borrar."""
    data = request.get_json(silent=True) or {}
    try:
        n = max(1, min(int(data.get("cantidad", 1)), 200))
    except (TypeError, ValueError):
        return _error("cantidad debe ser un número entre 1 y 200.", 400)
    try:
        from generar_dataset import generar_dataframe
        paquete = _cargar_modelo()
        feats = paquete["features"]
        df = generar_dataframe(n=n, seed=random.randrange(1, 2**31))
        probs = paquete["modelo"].predict_proba(df[feats])[:, 1]
        filas = []
        for i, (_, r) in enumerate(df.iterrows()):
            filas.append({**{f: r[f] for f in feats}, "paciente_id": None,
                          "paciente_nombre": "Paciente simulado", "probabilidad": float(probs[i]),
                          "riesgo_predicho": int(probs[i] >= UMBRAL), "resultado_real": int(r[TARGET]),
                          "origen_resultado": "simulacion", "origen": "simulacion", "usuario": "simulador"})
        ml_store.guardar_lote(filas)
        p = _payload_matriz("vivo", request.args.get("origen"))
        p["actualizado"] = time.strftime("%H:%M:%S")
        return jsonify({"insertados": n, "matriz": p})
    except FileNotFoundError as e:
        return _error(str(e), 503)
    except ml_store.BaseDatosError as e:
        return _error(str(e), 503)
    except Exception as e:
        return _error(f"Error inesperado: {e}", 500)


@ml_gpt_bp.route("/ml/api/simulacion/reiniciar", methods=["POST"])
def ml_reiniciar_simulacion():
    try:
        return jsonify({"eliminados": ml_store.reiniciar_simulacion()})
    except ml_store.BaseDatosError as e:
        return _error(str(e), 503)


@ml_gpt_bp.route("/ml/api/pacientes", methods=["GET"])
def ml_pacientes():
    try:
        return jsonify(ml_store.listar_pacientes())
    except ml_store.BaseDatosError as e:
        return _error(str(e), 503)


@ml_gpt_bp.route("/ml/api/paciente/<int:pid>", methods=["GET"])
def ml_paciente(pid):
    try:
        info = ml_store.datos_paciente(pid)
    except ml_store.BaseDatosError as e:
        return _error(str(e), 503)
    if info is None:
        return _error("El paciente seleccionado no existe.", 404)
    from ml_utils import FEATURES
    info["faltantes"] = [f for f in FEATURES if f not in info["datos"]]
    return jsonify(info)


@ml_gpt_bp.route("/ml/exportar-csv", methods=["GET"])
def ml_exportar_csv():
    if not os.path.exists(CSV_PATH):
        return _error("El dataset aún no fue generado. Ejecuta generar_dataset.py", 404)
    return send_file(CSV_PATH, mimetype="text/csv", as_attachment=True,
                     download_name="dataset_medcontrol_2000.csv")


@ml_gpt_bp.route("/ml/exportar-predicciones", methods=["GET"])
def ml_exportar_predicciones():
    try:
        filas = ml_store.exportar_todo()
    except ml_store.BaseDatosError as e:
        return _error(str(e), 503)
    out = io.StringIO()
    cols = ["id", "fecha", "paciente_nombre", "origen", "edad", "presion_sistolica", "presion_diastolica",
            "frecuencia_cardiaca", "glucosa", "temperatura", "nivel_triaje", "comorbilidades",
            "probabilidad", "riesgo_predicho", "resultado_real", "origen_resultado", "usuario"]
    w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(filas)
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=predicciones_ml.csv"})


# ------------------------------------------------------------------
# MÓDULO 2: ASISTENTE CLÍNICO GPT (sin cambios)
# ------------------------------------------------------------------
@ml_gpt_bp.route("/gpt/asistente", methods=["GET"])
def gpt_asistente_vista():
    return render_template("gpt_assistant.html")


@ml_gpt_bp.route("/gpt/asistente", methods=["POST"])
def gpt_asistente_consulta():
    """Espera JSON: { "mensaje": "...", "historial": [ {role, content}, ... ] (opcional) }"""
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
