"""
ml_utils.py
Funciones PURAS (sin base de datos) del módulo de Machine Learning de MedControl:
validación de datos clínicos, métricas a partir de la matriz de confusión y
derivación de variables desde los datos reales del sistema (edad, CIE-10, laboratorio).
"""
import re
from datetime import date, datetime

FEATURES = [
    "edad", "presion_sistolica", "presion_diastolica", "frecuencia_cardiaca",
    "glucosa", "temperatura", "nivel_triaje", "comorbilidades"
]

RANGOS = {
    "edad": (0, 120),
    "presion_sistolica": (60, 260),
    "presion_diastolica": (30, 160),
    "frecuencia_cardiaca": (30, 220),
    "glucosa": (30, 600),
    "temperatura": (32.0, 43.0),
    "nivel_triaje": (1, 5),
    "comorbilidades": (0, 10),
}

ETIQUETAS = {
    "edad": "Edad", "presion_sistolica": "Presión sistólica",
    "presion_diastolica": "Presión diastólica", "frecuencia_cardiaca": "Frecuencia cardíaca",
    "glucosa": "Glucosa", "temperatura": "Temperatura",
    "nivel_triaje": "Nivel de triaje", "comorbilidades": "Comorbilidades",
}


class DatosInvalidos(ValueError):
    def __init__(self, errores):
        self.errores = errores
        super().__init__("; ".join(errores.values()))


def validar_paciente(data):
    """Valida el JSON recibido. Devuelve un dict con las 8 variables (float) o lanza DatosInvalidos."""
    errores, limpio = {}, {}
    for campo in FEATURES:
        valor = data.get(campo) if isinstance(data, dict) else None
        if valor is None or (isinstance(valor, str) and not valor.strip()) or isinstance(valor, bool):
            errores[campo] = f"{ETIQUETAS[campo]}: es obligatorio."
            continue
        try:
            n = float(str(valor).replace(",", "."))
        except ValueError:
            errores[campo] = f"{ETIQUETAS[campo]}: debe ser numérico."
            continue
        if n != n or n in (float("inf"), float("-inf")):
            errores[campo] = f"{ETIQUETAS[campo]}: valor no válido."
            continue
        lo, hi = RANGOS[campo]
        if not lo <= n <= hi:
            errores[campo] = f"{ETIQUETAS[campo]}: debe estar entre {lo} y {hi}."
            continue
        limpio[campo] = n
    if not errores and limpio["presion_sistolica"] <= limpio["presion_diastolica"]:
        errores["presion_sistolica"] = "La presión sistólica debe ser mayor que la diastólica."
    if errores:
        raise DatosInvalidos(errores)
    return limpio


def metricas_desde_matriz(tn, fp, fn, tp):
    """Accuracy, precision, recall, F1 y especificidad calculados desde la matriz. None si no se pueden calcular."""
    def div(a, b):
        return round(a / b, 4) if b else None
    total = tn + fp + fn + tp
    precision = div(tp, tp + fp)
    recall = div(tp, tp + fn)
    f1 = None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = round(2 * precision * recall / (precision + recall), 4)
    return {
        "accuracy": div(tn + tp, total),
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "especificidad": div(tn, tn + fp),
    }


def parsear_presion(texto):
    m = re.match(r"^\s*(\d{2,3})\s*/\s*(\d{2,3})\s*$", str(texto or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def edad_desde_fecha(f):
    if not f:
        return None
    if isinstance(f, datetime):
        f = f.date()
    if not isinstance(f, date):
        try:
            f = datetime.strptime(str(f)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    hoy = date.today()
    return hoy.year - f.year - ((hoy.month, hoy.day) < (f.month, f.day))


def extraer_glucosa(texto):
    """Primer número plausible (30-600) dentro del resultado de laboratorio, o None."""
    for m in re.finditer(r"\d{2,3}(?:[.,]\d+)?", str(texto or "")):
        v = float(m.group(0).replace(",", "."))
        if 30 <= v <= 600:
            return int(round(v))
    return None


# Categorías de comorbilidad usadas por el dataset: diabetes, hipertensión, obesidad, cardiopatía
def comorbilidades_desde_cie10(codigos):
    """Cuenta cuántas de las 4 categorías aparecen en los códigos CIE-10 del historial clínico."""
    categorias = set()
    for c in codigos or []:
        c = str(c or "").strip().upper()
        if len(c) < 3 or not c[0].isalpha() or not c[1:3].isdigit():
            continue
        letra, num = c[0], int(c[1:3])
        if letra == "E" and 10 <= num <= 14:
            categorias.add("diabetes")
        elif letra == "I" and 10 <= num <= 15:
            categorias.add("hipertension")
        elif letra == "E" and num == 66:
            categorias.add("obesidad")
        elif letra == "I" and (20 <= num <= 25 or num == 50):
            categorias.add("cardiopatia")
    return len(categorias)
