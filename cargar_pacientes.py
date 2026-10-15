import sqlite3
import pandas as pd
import os

df = pd.read_csv('dataset_medcontrol_2000.csv')

for db_file in ['medcontrol.db', 'hospital.db']:
    if not os.path.exists(db_file):
        continue
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cols = [c[1] for c in cursor.execute("PRAGMA table_info(pacientes)").fetchall()]
    
    print(f"📂 {db_file} - Columnas en 'pacientes':", cols)
    
    for i, row in df.iterrows():
        dni = str(10000000 + i)
        tel = f"9{i:08d}"[:9]
        email = f"paciente{i+1}@medcontrol.pe"
        
        if 'nombres' in cols and 'apellidos' in cols:
            cursor.execute("""
                INSERT OR REPLACE INTO pacientes (dni, nombres, apellidos, telefono, email)
                VALUES (?, ?, ?, ?, ?)
            """, (dni, f"Paciente #{i+1}", "Dataset", tel, email))
        elif 'nombre' in cols and 'apellido' in cols:
            cursor.execute("""
                INSERT OR REPLACE INTO pacientes (dni, nombre, apellido, telefono, email)
                VALUES (?, ?, ?, ?, ?)
            """, (dni, f"Paciente #{i+1}", "Dataset", tel, email))
        elif 'nombre' in cols:
            cursor.execute("""
                INSERT OR REPLACE INTO pacientes (dni, nombre, telefono, email)
                VALUES (?, ?, ?, ?)
            """, (dni, f"Paciente Dataset #{i+1}", tel, email))
            
    conn.commit()
    count = cursor.execute("SELECT COUNT(*) FROM pacientes").fetchone()[0]
    print(f"✅ {db_file}: Total de pacientes = {count}")
    conn.close()