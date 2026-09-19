"""Esquema Pydantic de salida para el Pipeline de Extracción de Entidades Técnicas."""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field, field_validator


class NivelCriticidad(str, Enum):
    """Qué tan crítica es la situación descrita en el texto analizado."""

    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"


TERMINOS_GENERICOS_PROHIBIDOS = {
    "sistema",
    "aplicacion",
    "aplicación",
    "plataforma",
    "programa",
    "software",
    "herramienta",
    "servicio",
    "proyecto",
    "codigo",
    "código",
}


class EntidadesTecnicas(BaseModel):
    """Estructura validada que el LLM debe completar a partir de un texto técnico
    (una descripción de arquitectura, un log de error, etc.)."""

    tecnologias: List[str] = Field(
        ...,
        min_length=1,
        description=(
            "Tecnologías, frameworks, lenguajes o herramientas ESPECÍFICAS "
            "mencionadas o claramente implicadas en el texto (ej. 'FastAPI', "
            "'Redis'). Prohibido usar términos genéricos como 'sistema', "
            "'aplicación' o 'plataforma' -- si no hay ninguna tecnología "
            "nombrada, inferí la categoría más específica y plausible según "
            "el contexto (ej. 'backend de e-commerce' en vez de 'sistema')."
        ),
    )
    nivel_de_criticidad: NivelCriticidad = Field(
        ...,
        description=(
            "Qué tan crítica es la situación descrita: 'baja' si es informativo "
            "o menor, 'media' si afecta funcionalidad parcialmente, 'alta' si "
            "hay una falla grave, caída de servicio o riesgo de seguridad."
        ),
    )
    resumen_tecnico: str = Field(
        ...,
        min_length=10,
        description="Resumen técnico breve (1-2 oraciones) de la situación descrita.",
    )

    @field_validator("tecnologias")
    @classmethod
    def limpiar_y_validar_tecnologias(cls, valor: List[str]) -> List[str]:
        """Descarta strings vacíos/duplicados, confirma que quede al menos una
        tecnología real, y RECHAZA términos genéricos (fuerza un reintento del
        LLM vía .with_retry() en vez de aceptar un placeholder sin valor real)."""
        limpio = []
        vistos = set()
        for item in valor:
            nombre = item.strip()
            if nombre and nombre.lower() not in vistos:
                limpio.append(nombre)
                vistos.add(nombre.lower())
        if not limpio:
            raise ValueError("La lista de tecnologías no puede quedar vacía tras limpiarla.")

        genericos_encontrados = [t for t in limpio if t.lower() in TERMINOS_GENERICOS_PROHIBIDOS]
        if genericos_encontrados:
            raise ValueError(
                f"'{genericos_encontrados[0]}' es un término genérico, no una tecnología "
                "específica. Inferí algo más concreto según el contexto del texto."
            )
        return limpio
