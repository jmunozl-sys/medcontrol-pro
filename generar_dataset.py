"""
generar_dataset.py
==================================================================
Script INDEPENDIENTE y ADITIVO para MedControl / HDAC.
No importa ni modifica nada de tu app.py ni de tu base de datos
operativa: solo LEE (opcionalmente) la conexión que ya usas para
crear una tabla nueva y aislada `ML_Pacientes_Data`, y además deja
siempre un respaldo en CSV que no depende de SQL Server.

USO:
    python generar_dataset.py                # genera CSV solamente
    python generar_dataset.py --con-sql       # además inserta en SQL Server

Salida:
    dataset_medcontrol_2000.csv   (2000 filas, 8 columnas + objetivo)
==================================================================
"""

import argparse
import numpy as np
import pandas as pd

N_REGISTROS = 2000
SEED = 42
CSV_SALIDA = "dataset_medcontrol_2000.csv"


def generar_dataframe(n=N_REGISTROS, seed=SEED) -> pd.DataFrame:
    """
    Genera un DataFrame sintético con variables clínicas realistas.
    El riesgo de reingreso (0/1) se calcula a partir de una combinación
    lineal ponderada de las variables + ruido aleatorio, de modo que el
    dataset tenga un patrón real y aprendible por un modelo de ML
    (no es puro ruido, pero tampoco es determinista al 100%).
    """
    rng = np.random.default_rng(seed)

    # --- Variables clínicas base ---
    edad = rng.normal(loc=55, scale=18, size=n).clip(1, 99).round(0)

    presion_sistolica = rng.normal(loc=125, scale=18, size=n).clip(80, 220).round(0)
    presion_diastolica = (presion_sistolica * 0.62 + rng.normal(0, 6, n)).clip(50, 140).round(0)

    frecuencia_cardiaca = rng.normal(loc=80, scale=15, size=n).clip(40, 180).round(0)

    glucosa = rng.normal(loc=105, scale=35, size=n).clip(60, 400).round(0)

    temperatura = rng.normal(loc=36.7, scale=0.6, size=n).clip(34.5, 40.5).round(1)

    # Nivel de triaje: 1 = Emergencia (más grave) ... 5 = No urgente
    nivel_triaje = rng.choice([1, 2, 3, 4, 5], size=n, p=[0.08, 0.17, 0.35, 0.25, 0.15])

    # Número de comorbilidades (0 a 4): diabetes, hipertensión, obesidad, cardiopatía
    comorbilidades = rng.choice([0, 1, 2, 3, 4], size=n, p=[0.35, 0.30, 0.20, 0.10, 0.05])

    # --- Cálculo del riesgo real de reingreso (variable objetivo) ---
    urgencia = (5 - nivel_triaje)  # invertido: más urgente => valor más alto
    score = (
        -4.0
        + 0.035 * (edad - 40)
        + 0.030 * (presion_sistolica - 120)
        + 0.025 * (frecuencia_cardiaca - 75)
        + 0.020 * (glucosa - 100)
        + 0.55 * urgencia
        + 0.65 * comorbilidades
        + 0.10 * (temperatura - 36.7) * 10
        + rng.normal(0, 1.1, n)  # ruido para simular incertidumbre clínica real
    )
    probabilidad = 1 / (1 + np.exp(-score))
    riesgo_reingreso = (rng.random(n) < probabilidad).astype(int)

    df = pd.DataFrame({
        "edad": edad.astype(int),
        "presion_sistolica": presion_sistolica.astype(int),
        "presion_diastolica": presion_diastolica.astype(int),
        "frecuencia_cardiaca": frecuencia_cardiaca.astype(int),
        "glucosa": glucosa.astype(int),
        "temperatura": temperatura,
        "nivel_triaje": nivel_triaje.astype(int),
        "comorbilidades": comorbilidades.astype(int),
        "riesgo_reingreso": riesgo_reingreso
    })
    return df


def guardar_csv(df: pd.DataFrame, ruta: str = CSV_SALIDA):
    df.to_csv(ruta, index=False, encoding="utf-8")
    print(f"[OK] CSV generado: {ruta}  ({len(df)} filas)")


def guardar_en_sql_server(df: pd.DataFrame):
    """
    Inserta el dataset en una tabla NUEVA y AISLADA (ML_Pacientes_Data),
    totalmente separada de tus tablas operativas (Pacientes, Citas, etc.).
    Si algo falla (driver no instalado, credenciales distintas, etc.) el
    script NO se detiene: el CSV ya quedó guardado de todas formas.
    """
    try:
        import pyodbc
        import os

        SERVER = os.getenv('DB_SERVER', 'DESKTOP-PEB6BCK')
        DATABASE = os.getenv('DB_NAME', 'HDAC_Hospital_DB')
        DB_USER = os.getenv('DB_USER', 'sa')
        DB_PASSWORD = os.getenv('DB_PASSWORD', 'tu_contraseña_aqui')

        try:
            conn = pyodbc.connect(
                f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};'
                f'DATABASE={DATABASE};Trusted_Connection=yes;', timeout=5)
        except Exception:
            conn = pyodbc.connect(
                f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};'
                f'DATABASE={DATABASE};UID={DB_USER};PWD={DB_PASSWORD};', timeout=5)

        cursor = conn.cursor()
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ML_Pacientes_Data')
            CREATE TABLE dbo.ML_Pacientes_Data (
                id INT IDENTITY(1,1) PRIMARY KEY,
                edad INT, presion_sistolica INT, presion_diastolica INT,
                frecuencia_cardiaca INT, glucosa INT, temperatura DECIMAL(4,1),
                nivel_triaje INT, comorbilidades INT, riesgo_reingreso BIT,
                fecha_generacion DATETIME DEFAULT GETDATE()
            )
        """)
        conn.commit()

        # Limpiar dataset anterior de ML antes de recargar (tabla aislada, no toca nada más)
        cursor.execute("TRUNCATE TABLE dbo.ML_Pacientes_Data")
        conn.commit()

        rows = [tuple(r) for r in df.itertuples(index=False, name=None)]
        cursor.executemany("""
            INSERT INTO dbo.ML_Pacientes_Data
            (edad, presion_sistolica, presion_diastolica, frecuencia_cardiaca,
             glucosa, temperatura, nivel_triaje, comorbilidades, riesgo_reingreso)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
        conn.close()
        print(f"[OK] {len(df)} registros insertados en dbo.ML_Pacientes_Data (SQL Server)")
    except Exception as e:
        print(f"[AVISO] No se pudo insertar en SQL Server ({e}). "
              f"El CSV ya fue generado correctamente, así que el resto del módulo "
              f"puede seguir funcionando sin problema.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generador de dataset sintético MedControl ML")
    parser.add_argument("--con-sql", action="store_true",
                         help="Además de generar el CSV, intenta insertar en SQL Server (tabla ML_Pacientes_Data)")
    args = parser.parse_args()

    df = generar_dataframe()
    guardar_csv(df)

    print("\nDistribución de la variable objetivo (riesgo_reingreso):")
    print(df["riesgo_reingreso"].value_counts(normalize=True).round(3))

    if args.con_sql:
        guardar_en_sql_server(df)
