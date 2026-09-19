"""Cadena LCEL: Prompt -> LLM con salida estructurada -> validación -> reintento."""

import logging
import os

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from schemas import EntidadesTecnicas

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pipeline")

# finish_reason que indican que la respuesta se cortó por límite de tokens.
# OpenAI usa "length"; Anthropic usa "max_tokens".
FINISH_REASONS_TRUNCADOS = {"length", "max_tokens"}

SYSTEM_PROMPT = """Sos un analista técnico. Tu tarea es leer un texto (puede ser \
una descripción de arquitectura de software o un log de error) y extraer de forma \
precisa:

- Las tecnologías, frameworks, lenguajes o herramientas mencionadas o claramente \
implicadas.
- El nivel de criticidad de la situación descrita (baja, media o alta).
- Un resumen técnico breve y concreto (1-2 oraciones).
Reglas importantes para el campo "tecnologias":
- Nombrá tecnologías CONCRETAS y específicas (ej. "FastAPI", "Redis", "Kubernetes"),
nunca palabras genéricas tomadas literalmente del texto de entrada como "sistema",
"aplicación", "plataforma" o "programa".
- Si el texto no nombra ninguna tecnología explícita, inferí la categoría más
específica y plausible que el contexto sugiera (ej. si se habla de un "checkout"
con errores, "backend de e-commerce" es más específico que "sistema"). Basate
solo en pistas reales del texto -- no inventes marcas o productos puntuales
(como "Kubernetes" o "AWS") si no hay ninguna base en el texto para eso.

Si el texto es ambiguo en general, hacé la mejor inferencia razonable a partir \
de lo que está escrito. No inventes hechos que no estén mencionados ni implícitos."""

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", "Texto a analizar:\n\n{texto}"),
    ]
)


def _build_model():
    """Instancia el modelo según PROVIDER, respetando las diferencias entre
    proveedores que ya documentamos en el Módulo 1 (ver README de ese ejercicio)."""
    provider = os.getenv("PROVIDER", "openai").lower()

    if provider == "openai":
        return ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

    if provider == "anthropic":
        # Los modelos recientes de Anthropic (4.7+, incluido claude-sonnet-5) ya
        # no aceptan `temperature` explícito -> no lo pasamos acá para evitar el
        # mismo error que documentamos en el Módulo 1.
        return ChatAnthropic(model="claude-sonnet-5")

    raise ValueError(f"Proveedor '{provider}' no soportado en este pipeline.")


def _validar_respuesta_completa(resultado: dict) -> EntidadesTecnicas:
    """Revisa la respuesta CRUDA antes de confiar en el objeto ya parseado.

    Esto cubre el error común de "ignorar el finish_reason": un JSON puede
    parecer válido pero estar truncado porque el modelo se quedó sin tokens
    a mitad de la respuesta. Si no chequeamos esto explícitamente, un objeto
    incompleto podría colarse como si estuviera bien.
    """
    raw = resultado.get("raw")
    finish_reason = None
    if raw is not None:
        finish_reason = (raw.response_metadata or {}).get("finish_reason")

    if finish_reason in FINISH_REASONS_TRUNCADOS:
        logger.warning("Respuesta truncada por límite de tokens (finish_reason=%s)", finish_reason)
        raise OutputParserException(
            f"La respuesta del modelo se cortó por límite de tokens (finish_reason={finish_reason})."
        )

    if resultado.get("parsing_error") is not None:
        logger.warning("Error de parseo/validación: %s", resultado["parsing_error"])
        raise resultado["parsing_error"]

    parsed = resultado.get("parsed")
    if parsed is None:
        raise OutputParserException("El modelo no devolvió un objeto parseable.")

    return parsed


_model = _build_model()
# include_raw=True es clave: nos da acceso al finish_reason Y al error de
# parseo sin que la excepción se pierda, para poder decidir nosotros cuándo
# reintentar en vez de dejarlo librado al comportamiento por defecto.
_structured_model = _model.with_structured_output(EntidadesTecnicas, include_raw=True)

# Cadena LCEL: prompt | modelo con salida estructurada | validación propia,
# con reintento automático ante JSON mal formado, incompleto, o que no pasa
# las validaciones de schemas.py.
chain: Runnable = (prompt | _structured_model | RunnableLambda(_validar_respuesta_completa)).with_retry(
    retry_if_exception_type=(OutputParserException, ValidationError),
    stop_after_attempt=3,
    wait_exponential_jitter=True,
)


async def process_text(text: str) -> EntidadesTecnicas:
    """Ejecuta el pipeline completo de forma asíncrona y devuelve el objeto validado."""
    logger.info("Procesando texto (%d caracteres)...", len(text))
    resultado = await chain.ainvoke({"texto": text})
    logger.info("Extracción validada OK -> %s", resultado.model_dump())
    return resultado
