import os
import re
import requests
import asyncpg
import asyncio


API_KEY = os.environ["GEMINI_API_KEY"]

MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768

URL_EMBEDDING = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/{MODEL}:embedContent?key={API_KEY}"
)


QUEST_START = re.compile(
    r"quest\.([0-9A-Fa-f]{16})\."
)


def parsear_quests(texto):
    """
    Agrupa todas as propriedades pertencentes ao mesmo quest_id.
    """

    matches = list(QUEST_START.finditer(texto))
    quests = []

    for i, match in enumerate(matches):
        quest_id = match.group(1)

        inicio = match.start()

        if i + 1 < len(matches):
            fim = matches[i + 1].start()
        else:
            fim = len(texto)

        bloco = texto[inicio:fim]

        quest = {
            "quest_id": quest_id,
            "title": None,
            "subtitle": None,
            "description": None,
        }

        title_match = re.search(
            rf"quest\.{quest_id}\.title:\s*\"([^\"]*)\"",
            bloco,
        )

        if title_match:
            quest["title"] = title_match.group(1)

        subtitle_match = re.search(
            rf"quest\.{quest_id}\.quest_subtitle:\s*\"([^\"]*)\"",
            bloco,
        )

        if subtitle_match:
            quest["subtitle"] = subtitle_match.group(1)

        desc_match = re.search(
            rf"quest\.{quest_id}\.quest_desc:\s*\[(.*?)\]",
            bloco,
            re.DOTALL,
        )

        if desc_match:
            quest["description"] = desc_match.group(1)

        quests.append(quest)

    return quests


def montar_texto_embedding(quest):
    """
    Cria uma representação limpa da quest para o embedding.
    """

    partes = []

    if quest["title"]:
        partes.append(f"Title: {quest['title']}")

    if quest["subtitle"]:
        partes.append(f"Subtitle: {quest['subtitle']}")

    if quest["description"]:
        partes.append(f"Description: {quest['description']}")

    return "\n\n".join(partes)


def gerar_embedding(texto, title=None):
    payload = {
        "model": f"models/{MODEL}",
        "content": {
            "parts": [
                {"text": texto}
            ]
        },
        "taskType": "RETRIEVAL_DOCUMENT",
    }

    if title:
        payload["title"] = title

    resposta = requests.post(
        URL_EMBEDDING,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60,
    )

    resposta.raise_for_status()

    dados = resposta.json()

    if "embedding" not in dados:
        raise RuntimeError(
            f"API não retornou embedding: {dados}"
        )

    vetor = dados["embedding"]["values"]

    if len(vetor) != EMBEDDING_DIMENSIONS:
        raise RuntimeError(
            f"Dimensão inesperada: {len(vetor)}. "
            f"Esperado: {EMBEDDING_DIMENSIONS}."
        )

    return vetor


async def popular_banco():

    caminho = "/app/database/atm10_knowledge_base.txt"

    if not os.path.exists(caminho):
        print(
            f"Erro crítico: Arquivo {caminho} não encontrado.",
            flush=True,
        )
        return

    with open(
        caminho,
        "r",
        encoding="utf-8",
    ) as f:
        texto_completo = f.read()

    quests = parsear_quests(texto_completo)

    if not quests:
        print(
            "Nenhuma quest encontrada. "
            "Verifique a estrutura do arquivo.",
            flush=True,
        )
        return

    amostra = quests[:10]

    print(
        f"\nTotal de quests encontradas: {len(quests):,}",
        flush=True,
    )

    print(
        f"Testando os primeiros {len(amostra)} registros...\n",
        flush=True,
    )

    conn = await asyncpg.connect(
        user="pyxis_admin",
        password=os.environ.get("DB_PASSWORD"),
        database="telemetria",
        host="db",
    )

    try:

        for i, quest in enumerate(amostra, start=1):

            try:

                texto_embedding = montar_texto_embedding(quest)

                print("=" * 60)
                print(f"QUEST {i}/{len(amostra)}")
                print("=" * 60)

                print(f"ID: {quest['quest_id']}")
                print(f"Title: {quest['title']}")
                print(f"Subtitle: {quest['subtitle']}")

                print("\nTexto enviado ao embedding:")
                print(texto_embedding)

                vetor = gerar_embedding(
                    texto_embedding,
                    title=quest["title"],
                )

                print(
                    f"\nEmbedding gerado: "
                    f"{len(vetor)} dimensões"
                )

                vetor_pgvector = (
                    "["
                    + ",".join(str(float(x)) for x in vetor)
                    + "]"
                )

                resultado = await conn.fetchrow(
                    """
                    INSERT INTO base_conhecimento
                        (texto, embedding)
                    VALUES
                        ($1, $2::vector)
                    RETURNING id
                    """,
                    texto_embedding,
                    vetor_pgvector,
                )

                print(
                    f"Salvo no PostgreSQL. "
                    f"ID: {resultado['id']}",
                    flush=True,
                )

            except Exception as e:

                print(
                    f"\nFalha ao processar "
                    f"quest {i}: {e}",
                    flush=True,
                )

        print(
            "\nTeste concluído.",
            flush=True,
        )

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(popular_banco())

