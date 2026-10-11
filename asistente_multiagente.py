"""
asistente_multiagente.py
==================================================================
Sistema Multiagente Clínico para MedControl Pro usando OpenAI GPT.
==================================================================
"""
import os
from openai import OpenAI

# Inicialización del cliente de OpenAI
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ------------------------------------------------------------------
# AGENTE 1: DIAGNÓSTICO Y SÍNTOMAS
# ------------------------------------------------------------------
def agente_diagnostico(caso_clinico):
    prompt = f"""
    Eres un Agente Especialista en Medicina Interna y Diagnóstico Diferencial.
    Analiza el siguiente caso y genera:
    1. Resumen sucinto de síntomas clave.
    2. Top 3 diagnósticos diferenciales posibles.

    Caso del paciente:
    {caso_clinico}
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return response.choices[0].message.content


# ------------------------------------------------------------------
# AGENTE 2: RIESGO VITAL Y TRIAJE
# ------------------------------------------------------------------
def agente_riesgo_vital(caso_clinico):
    prompt = f"""
    Eres un Agente Especialista en Medicina de Urgencias y Triaje.
    Evalúa si hay signos de alarma en los signos vitales o estado general del caso.
    Clasifica el nivel de urgencia (Nivel 1: Resucitación a Nivel 5: No urgente) y justifica.

    Caso del paciente:
    {caso_clinico}
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return response.choices[0].message.content


# ------------------------------------------------------------------
# AGENTE 3: PROTOCOLOS Y TRATAMIENTO
# ------------------------------------------------------------------
def agente_protocolos(caso_clinico, diagnostico_previo):
    prompt = f"""
    Eres un Agente Especialista en Farmacología Clínica y Guías Médicas.
    Con base en el caso y el análisis diagnóstico previo:
    1. Sugiere 3 pruebas auxiliares o exámenes de laboratorio a solicitar.
    2. Sugiere líneas generales de tratamiento inicial de acuerdo con guías internacionales.

    Caso: {caso_clinico}
    Diagnóstico preliminar: {diagnostico_previo}
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return response.choices[0].message.content


# ------------------------------------------------------------------
# AGENTE ORQUESTADOR: SUPERVISOR CLINICO
# ------------------------------------------------------------------
def evaluar_caso_multiagente(caso_clinico):
    """
    Orquesta la ejecución secuencial/paralela de los 3 agentes
    y sintetiza el informe final.
    """
    # 1. Ejecución de agentes especializados
    analisis_dx = agente_diagnostico(caso_clinico)
    analisis_riesgo = agente_riesgo_vital(caso_clinico)
    analisis_tx = agente_protocolos(caso_clinico, analisis_dx)

    # 2. Consolidación por el Agente Orquestador
    prompt_orquestador = f"""
    Eres el Director Médico y Agente Orquestador de MedControl Pro.
    Has recibido informes de 3 agentes especializados para el siguiente caso:

    === CASO INGRESADO ===
    {caso_clinico}

    === INFORME AGENTE DIAGNÓSTICO ===
    {analisis_dx}

    === INFORME AGENTE RIESGO Y TRIAJE ===
    {analisis_riesgo}

    === INFORME AGENTE PROTOCOLOS Y TRATAMIENTO ===
    {analisis_tx}

    Sintetiza estos informes en un ÚNICO reporte clínico ejecutivo bien estructurado en Markdown con las siguientes secciones:
    ### 🏥 Evaluación Consolidada Multiagente
    - **Nivel de Triaje y Riesgo Vital:** (Breve resumen)
    - **Diagnósticos Diferenciales a Considerar:** (Puntos clave)
    - **Plan de Acción Recomendado:** (Exámenes y manejo inicial)
    - **Notas de Atención:** (Alertas o banderas rojas)
    """

    informe_final = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt_orquestador}],
        temperature=0.4
    )

    return informe_final.choices[0].message.content