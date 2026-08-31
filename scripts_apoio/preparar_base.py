import os
import re
import requests
import asyncpg
import asyncio


API_KEY = os.environ["GEMINI_API_KEY"]

MODEL = "gemini-embedding-2"
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

    pattern = re.compile(
        r'quest\.([0-9A-Fa-f]{16})\.(quest_desc|quest_subtitle|title):'
    )

    quests = {}

    def limpar_descricao(texto):
        if not texto:
            return texto

        texto = re.sub(r'\{image:[^}]*\}', '', texto)

        # Remove espaços/quebras de linha excessivos deixados pela remoção
        texto = re.sub(r'\n\s*\n+', '\n\n', texto)

        return texto.strip()

    for match in pattern.finditer(texto):
        quest_id = match.group(1)
        campo = match.group(2)

        inicio_valor = match.end()

        # Procura o início da próxima propriedade.
        proximo = pattern.search(texto, inicio_valor)

        if proximo:
            fim_valor = proximo.start()
        else:
            fim_valor = len(texto)

        valor = texto[inicio_valor:fim_valor].strip()

        if quest_id not in quests:
            quests[quest_id] = {
                "quest_id": quest_id,
                "title": None,
                "subtitle": None,
                "description": None,
            }

        if campo == "title":
            match_valor = re.match(r'"([^"]*)"', valor)

            if match_valor:
                quests[quest_id]["title"] = match_valor.group(1)

        elif campo == "quest_subtitle":
            match_valor = re.match(r'"([^"]*)"', valor)

            if match_valor:
                quests[quest_id]["subtitle"] = match_valor.group(1)

        elif campo == "quest_desc":
            match_valor = re.match(
                r'\[(.*?)\]',
                valor,
                re.DOTALL,
            )

            if match_valor:
                descricao = match_valor.group(1)
                descricao = re.sub(
                    r'\{image:[^}]*\}',
                    '',
                    descricao,
                )
                quests[quest_id]["description"] = (match_valor.group(1))

    return list(quests.values())


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
        "embedContentConfig": {
            "taskType": "RETRIEVAL_DOCUMENT",
            "outputDimensionality": 768,
        },
    }

    if title:
        payload["embedContentConfig"]["title"] = title

    resposta = requests.post(
        URL_EMBEDDING,
        json=payload,
        headers={
            "Content-Type": "application/json"
        },
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

    amostra = quests[:4160]

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

        print("\n" + "=" * 60, flush=True) 
        print("INÍCIO DA IMPORTAÇÃO", flush=True) 
        print("=" * 60, flush=True)
        print(f"Total de quests encontradas: {len(quests):,}", flush=True) 
        print(f"Total a processar: {len(amostra):,}", flush=True) 
        print("Quests já existentes serão ignoradas antes da geração do embedding.", flush=True) 
        print("=" * 60 + "\n", flush=True)

        processadas = 0 
        puladas = 0 
        inseridas = 0 
        erros = 0

        for i, quest in enumerate(amostra, start=1):
            quest_id = quest["quest_id"] 
            print( f"\n[{i}/{len(amostra)}] Quest {quest_id}", flush=True, )
            
            try:
                existe = await conn.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1
                        FROM base_conhecimento
                        WHERE quest_id = $1
                    )
                    """,
                    quest["quest_id"],
                )

                if existe:
                    print( " → Já existe no banco. " "Pulando geração do embedding.", flush=True, )
                    continue

                texto_embedding = montar_texto_embedding(quest)
                print( " → Quest nova. Gerando embedding...", flush=True, )
                
                vetor = gerar_embedding(
                    texto_embedding,
                    title=quest["title"],
                )

                print( f" → Embedding gerado: " f"{len(vetor)} dimensões", flush=True, )

                vetor_pgvector = (
                    "["
                    + ",".join(str(float(x)) for x in vetor)
                    + "]"
                )

                resultado = await conn.fetchrow(
                    """
                    INSERT INTO base_conhecimento (quest_id, texto, embedding)
                    VALUES ($1, $2, $3::vector)
                    ON CONFLICT (quest_id) DO NOTHING
                    RETURNING id
                    """,
                    quest["quest_id"],
                    texto_embedding,
                    vetor_pgvector,
                )

                if resultado:
                    print(
                        f"Salvo no PostgreSQL. ID: {resultado['id']}",
                        flush=True,
                    )
                else:
                    print(
                        f"Quest {quest['quest_id']} já existe. Pulando.",
                        flush=True,
                    )

            except Exception as e:

                print(
                    f"\nFalha ao processar "
                    f"quest {i}: {e}",
                    flush=True,
                )

        # ========================================================= 
        # RESUMO FINAL 
        # ========================================================= 
        print("\n" + "=" * 60, flush=True) 
        print("IMPORTAÇÃO CONCLUÍDA", flush=True) 
        print("=" * 60, flush=True) 
        print( f"Total encontrado: {len(quests):,}", flush=True, ) 
        print( f"Total processado: {len(amostra):,}", flush=True, ) 
        print( f"Embeddings gerados: {processadas:,}", flush=True, ) 
        print( f"Já existentes/pulados: {puladas:,}", flush=True, ) 
        print( f"Inseridos com sucesso: {inseridas:,}", flush=True, ) 
        print( f"Erros: {erros:,}", flush=True, ) 
        print("=" * 60, flush=True)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(popular_banco())

