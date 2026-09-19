"""Mini-script de prueba: corre el pipeline sobre varios textos de ejemplo,
incluyendo un caso ambiguo (la "prueba de estrés" que sugiere el enunciado)."""

import asyncio

from chain import process_text

TEXTOS_DE_PRUEBA = [
    (
        "Arquitectura clara",
        "Nuestra API está construida con FastAPI, usa Redis como caché de "
        "sesiones y PostgreSQL para persistencia. Detectamos un cuello de "
        "botella en el pool de conexiones a la base de datos bajo carga alta, "
        "lo que está afectando la disponibilidad del servicio.",
    ),
    (
        "Texto ambiguo (prueba de estrés)",
        "El sistema tuvo un problema ayer. Algunas cosas dejaron de andar "
        "bien por un rato, pero ya se solucionó.",
    ),
    (
        "Log de error",
        "[ERROR] 2026-09-05 03:14:07 - ConnectionTimeoutError en el pool de "
        "MongoDB después de 30s. El servicio de checkout devolvió 503 a los "
        "clientes durante 4 minutos hasta que el circuit breaker cortó el "
        "tráfico hacia ese nodo.",
    ),
]


async def main() -> None:
    for titulo, texto in TEXTOS_DE_PRUEBA:
        print(f"\n{'=' * 60}\n{titulo}\n{'=' * 60}")
        print(f"Texto de entrada: {texto}\n")
        try:
            resultado = await process_text(texto)
            print("Resultado validado:")
            print(resultado.model_dump_json(indent=2))
        except Exception as e:
            print(f"El pipeline no pudo procesar este texto tras los reintentos: {e}")


if __name__ == "__main__":
    asyncio.run(main())
