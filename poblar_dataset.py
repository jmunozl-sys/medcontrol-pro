import sqlite3
import pandas as pd
import os

# 1. Cargar el dataset
csv_path = "dataset_medcontrol_2000.csv"
if not os.path.exists(csv_path):
    print("❌ No se encontró el archivo dataset_medcontrol_2000.csv")
    exit()

df = pd.read_csv(csv_path)
print(f"📊 Dataset cargado correctamente con {len(df)} registros.")

db_files = ["medcontrol.db", "hospital.db"]

for db_file in db_files:
    if not os.path.exists(db_file):
        continue
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    print(f"\n📂 Procesando base de datos: {db_file}")

    tables = [t[0] for t in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

    # --- A) POBLAR TABLA PACIENTES ---
    if "pacientes" in tables:
        try:
            cols_info = cursor.execute("PRAGMA table_info(pacientes)").fetchall()
            col_names = [c[1] for c in cols_info]
            
            cursor.execute("SELECT COUNT(*) FROM pacientes")
            count = cursor.fetchone()[0]
            
            if count < 50:
                print(f"⏳ Poblando tabla 'pacientes' en {db_file}...")
                for i, row in df.iterrows():
                    dni = str(10000000 + i)
                    telefono = f"9{i:08d}"[:9]
                    email = f"paciente{i+1}@medcontrol.pe"
                    
                    data_dict = {}
                    if "id" in col_names:
                        data_dict["id"] = i + 10
                    if "dni" in col_names:
                        data_dict["dni"] = dni
                    if "telefono" in col_names:
                        data_dict["telefono"] = telefono
                    if "email" in col_names:
                        data_dict["email"] = email
                    
                    if "nombre" in col_names:
                        data_dict["nombre"] = f"Paciente Dataset #{i+1}"
                    elif "nombres" in col_names:
                        data_dict["nombres"] = f"Paciente #{i+1}"
                        if "apellidos" in col_names:
                            data_dict["apellidos"] = "Dataset"
                    elif "nombre_completo" in col_names:
                        data_dict["nombre_completo"] = f"Paciente Dataset #{i+1}"
                        
                    keys = ", ".join(data_dict.keys())
                    placeholders = ", ".join(["?"] * len(data_dict))
                    values = tuple(data_dict.values())
                    
                    cursor.execute(f"INSERT OR IGNORE INTO pacientes ({keys}) VALUES ({placeholders})", values)
                print("✅ Tabla 'pacientes' poblada correctamente.")
        except Exception as e:
            print(f"⚠️ Nota pacientes ({db_file}): {e}")

    # --- B) POBLAR TABLAS DE TRIAJE / EVALUACIONES / PREDICCIONES ---
    for t_name in ["predicciones", "evaluaciones", "evaluaciones_ia", "triaje"]:
        if t_name in tables:
            try:
                cols_info = cursor.execute(f"PRAGMA table_info({t_name})").fetchall()
                col_names = [c[1] for c in cols_info]
                
                print(f"⏳ Cargando datos en tabla '{t_name}' ({db_file})...")
                for i, row in df.iterrows():
                    val_dict = {}
                    for c in col_names:
                        if c == "id":
                            continue
                        elif c in row:
                            val_dict[c] = float(row[c]) if isinstance(row[c], float) else int(row[c])
                        elif c in ["riesgo_predicho", "prediccion", "pred", "resultado"]:
                            val_dict[c] = int(row['riesgo_reingreso'])
                        elif c in ["riesgo_real", "real", "es_reingreso", "target", "reingreso"]:
                            val_dict[c] = int(row['riesgo_reingreso'])
                        elif c == "paciente_id":
                            val_dict[c] = i + 10
                    
                    if val_dict:
                        keys = ", ".join(val_dict.keys())
                        placeholders = ", ".join(["?"] * len(val_dict))
                        values = tuple(val_dict.values())
                        cursor.execute(f"INSERT OR IGNORE INTO {t_name} ({keys}) VALUES ({placeholders})", values)
                print(f"✅ Tabla '{t_name}' poblada con éxito.")
            except Exception as e:
                print(f"⚠️ Nota tabla '{t_name}' ({db_file}): {e}")

    conn.commit()
    conn.close()

print("\n🎉 ¡Proceso completado! Las bases de datos se han sincronizado con el dataset.")