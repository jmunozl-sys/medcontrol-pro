"""
entrenar_modelo.py
==================================================================
Script INDEPENDIENTE y ADITIVO. No modifica nada de MedControl.

Lee `dataset_medcontrol_2000.csv` (lo genera automáticamente con
generar_dataset.py si no existe), entrena un Random Forest, calcula
métricas y guarda:

    - modelo_riesgo.pkl                    (modelo entrenado + metadata)
    - static/img/matriz_confusion.png      (imagen para el dashboard)
    - metrics_modelo.json                  (métricas + matriz de confusión numérica para el dashboard)

USO:
    python entrenar_modelo.py
==================================================================
"""

import json
import os
import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # backend sin pantalla, necesario en servidores
import matplotlib.pyplot as plt

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    confusion_matrix, accuracy_score, precision_score,
    recall_score, f1_score, ConfusionMatrixDisplay
)

CSV_DATASET = "dataset_medcontrol_2000.csv"
MODELO_SALIDA = "modelo_riesgo.pkl"
IMG_MATRIZ = os.path.join("static", "img", "matriz_confusion.png")
METRICS_JSON = "metrics_modelo.json"

FEATURES = [
    "edad", "presion_sistolica", "presion_diastolica",
    "frecuencia_cardiaca", "glucosa", "temperatura",
    "nivel_triaje", "comorbilidades"
]
TARGET = "riesgo_reingreso"


def cargar_dataset() -> pd.DataFrame:
    if not os.path.exists(CSV_DATASET):
        print(f"[INFO] No se encontró {CSV_DATASET}, generándolo automáticamente...")
        from generar_dataset import generar_dataframe, guardar_csv
        df = generar_dataframe()
        guardar_csv(df, CSV_DATASET)
        return df
    return pd.read_csv(CSV_DATASET)


def entrenar():
    df = cargar_dataset()
    X = df[FEATURES]
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    modelo = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=5,
        random_state=42,
        class_weight="balanced"
    )
    modelo.fit(X_train, y_train)

    y_pred = modelo.predict(X_test)

    # --- Métricas ---
    metricas = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
        "f1_score": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
        "n_entrenamiento": int(len(X_train)),
        "n_prueba": int(len(X_test)),
        "features": FEATURES
    }

    print("\n=== MÉTRICAS DEL MODELO ===")
    for k, v in metricas.items():
        print(f"  {k}: {v}")

    # --- Matriz de confusión (imagen) ---
    os.makedirs(os.path.dirname(IMG_MATRIZ), exist_ok=True)
    cm = confusion_matrix(y_test, y_pred, labels=[0, 1])
    fig, ax = plt.subplots(figsize=(5.5, 5))
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=["Bajo riesgo", "Alto riesgo"])
    disp.plot(ax=ax, cmap="Blues", colorbar=False, values_format="d")
    ax.set_title("Matriz de Confusión — Riesgo de Reingreso")
    plt.tight_layout()
    plt.savefig(IMG_MATRIZ, dpi=150)
    plt.close(fig)
    print(f"[OK] Matriz de confusión guardada en: {IMG_MATRIZ}")

    # --- Matriz de confusión numérica: el dashboard la lee de aquí (ya no depende de la imagen) ---
    tn, fp, fn, tp = (int(v) for v in cm.ravel())
    metricas["matriz_confusion"] = {"tn": tn, "fp": fp, "fn": fn, "tp": tp}
    print(f"[OK] Matriz de confusión: TN={tn} FP={fp} FN={fn} TP={tp}")

    # --- Guardar modelo + metadata en un solo .pkl ---
    paquete = {
        "modelo": modelo,
        "features": FEATURES,
        "metricas": metricas
    }
    joblib.dump(paquete, MODELO_SALIDA)
    print(f"[OK] Modelo guardado en: {MODELO_SALIDA}")

    # --- Guardar métricas para que el dashboard las lea sin re-entrenar ---
    with open(METRICS_JSON, "w", encoding="utf-8") as f:
        json.dump(metricas, f, indent=2, ensure_ascii=False)
    print(f"[OK] Métricas guardadas en: {METRICS_JSON}")

    # Importancia de variables (bonus: útil para explicar el modelo al médico)
    importancias = dict(zip(FEATURES, modelo.feature_importances_.round(4).tolist()))
    importancias_ordenadas = dict(sorted(importancias.items(), key=lambda x: x[1], reverse=True))
    print("\n=== IMPORTANCIA DE VARIABLES ===")
    for k, v in importancias_ordenadas.items():
        print(f"  {k}: {v}")

    return metricas


if __name__ == "__main__":
    entrenar()
