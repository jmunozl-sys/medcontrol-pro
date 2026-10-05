"""
asistente_gpt.py
==================================================================
Módulo INDEPENDIENTE y ADITIVO. No modifica nada de MedControl.

Define la función `consultar_asistente()` que recibe la sintomatología
o los datos clínicos de un paciente y devuelve un análisis preliminar
generado por un modelo de OpenAI (gpt-4o-mini por defecto).

La clave de API se lee SIEMPRE desde variables de entorno (.env),
nunca se escribe en el código fuente.

USO (desde cualquier otro script o desde el Blueprint):
    from asistente_gpt import consultar_asistente
    respuesta = consultar_asistente("Paciente de 68 años con fiebre y tos seca de 3 días...")
==================================================================
"""

import os
from dotenv import load_dotenv

load_dotenv()  # carga variables desde un archivo .env si existe

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = (
    "Eres un asistente clínico de apoyo para el personal médico del sistema "
    "hospitalario MedControl / HDAC. Tu función es ofrecer un ANÁLISIS "
    "PRELIMINAR orientativo, resúmenes de síntomas, posibles diagnósticos "
    "diferenciales a considerar y recomendaciones generales de manejo. "
    "SIEMPRE debes aclarar que tu respuesta es un apoyo a la decisión y NO "
    "reemplaza el juicio clínico del médico tratante. No das dosis exactas "
    "de medicamentos controlados sin indicar que deben ser verificadas por "
    "el profesional. Responde en español, de forma clara, profesional y "
    "estructurada (usa listas cuando ayude a la lectura)."
)


class AsistenteNoDisponibleError(Exception):
    """Se lanza cuando no hay API key configurada o la librería no está instalada."""
    pass


_PLACEHOLDERS = {"sk-tu-clave-de-openai-aqui", "tu-clave-de-openai-aqui", ""}


def _obtener_cliente():
    if not OPENAI_API_KEY or OPENAI_API_KEY.strip() in _PLACEHOLDERS or "tu-clave" in OPENAI_API_KEY or "tu_clave" in OPENAI_API_KEY:
        raise AsistenteNoDisponibleError(
            "El archivo .env todavía tiene la clave de EJEMPLO (sk-tu-clave-de-openai-aqui) "
            "en vez de tu clave real de OpenAI. Genera una en https://platform.openai.com/api-keys "
            "y reemplaza el valor de OPENAI_API_KEY en tu archivo .env (luego reinicia 'python app.py')."
        )
    if not OPENAI_API_KEY.startswith("sk-"):
        raise AsistenteNoDisponibleError(
            "OPENAI_API_KEY no tiene el formato esperado de una clave de OpenAI (debe empezar con 'sk-'). "
            "Verifica que copiaste la clave completa en tu archivo .env."
        )
    try:
        from openai import OpenAI
    except ImportError:
        raise AsistenteNoDisponibleError(
            "La librería 'openai' no está instalada. Ejecuta: pip install openai"
        )
    return OpenAI(api_key=OPENAI_API_KEY)


def consultar_asistente(mensaje_usuario: str, historial: list | None = None) -> str:
    """
    Envía la consulta clínica al modelo de OpenAI y devuelve el texto de respuesta.

    Parámetros:
        mensaje_usuario: texto con la sintomatología, datos del paciente o
                          pregunta del médico.
        historial: lista opcional de mensajes previos del chat, en formato
                   [{"role": "user"/"assistant", "content": "..."}], para dar
                   contexto de conversación continua.

    Retorna:
        str con la respuesta del asistente.

    Lanza:
        AsistenteNoDisponibleError si no hay clave configurada o falta la librería.
    """
    if not mensaje_usuario or not mensaje_usuario.strip():
        return "Por favor ingresa la sintomatología o la consulta del paciente."

    cliente = _obtener_cliente()

    mensajes = [{"role": "system", "content": SYSTEM_PROMPT}]
    if historial:
        mensajes.extend(historial[-10:])  # limitar contexto a los últimos 10 turnos
    mensajes.append({"role": "user", "content": mensaje_usuario})

    try:
        respuesta = cliente.chat.completions.create(
            model=OPENAI_MODEL,
            messages=mensajes,
            temperature=0.4,
            max_tokens=700
        )
        return respuesta.choices[0].message.content.strip()
    except Exception as e:
        return (
            f"⚠️ No se pudo obtener respuesta del asistente en este momento "
            f"({type(e).__name__}). Verifica tu conexión y tu clave de API. "
            f"Detalle técnico: {e}"
        )


if __name__ == "__main__":
    # Prueba rápida por consola
    print(consultar_asistente(
        "Paciente varón de 68 años, antecedente de diabetes tipo 2, acude con "
        "fiebre de 38.9°C, tos productiva de 4 días y saturación de oxígeno de 91%."
    ))
