import os
import requests
import asyncpg
import asyncio
import re

API_KEY = os.environ.get("GEMINI_API_KEY")

URL_COUNT_TOKENS = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/text-embedding-004:countTokens?key={API_KEY}"
)

URL_EMBEDDING = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/text-embedding-004:embedContent?key={API_KEY}"
)


def fatiar_texto_logico(texto):
    # Separa os blocos usando "quest." para manter o contexto lógico de cada missão
    chunks = re.split(r'(?=quest\.)', texto)
    return [c.strip() for c in chunks if len(c.strip()) > 50]


def contar_tokens(chunk):
    payload = {
        "model": "models/text-embedding-004",
        "contents": [
            {
                "parts": [
                    {"text": chunk}
                ]
            }
        ]
    }

    resposta = requests.post(
        URL_COUNT_TOKENS,
        json=payload,
        timeout=60
    )

    print(f"CountTokens HTTP {resposta.status_code}")

    if not resposta.ok:
        print("Resposta da API:")
        print(resposta.text)
        resposta.raise_for_status()

    dados = resposta.json()

    if "totalTokens" not in dados:
        raise RuntimeError(
            f"API não retornou totalTokens: {dados}"
        )

    return dados["totalTokens"]


def gerar_embedding(chunk):
    payload = {
        "model": "models/text-embedding-004",
        "content": {
            "parts": [
                {"text": chunk}
            ]
        }
    }

    resposta = requests.post(
        URL_EMBEDDING,
        json=payload,
        timeout=60
    )

    print(f"Embedding HTTP {resposta.status_code}")

    if not resposta.ok:
        print("Resposta da API:")
        print(resposta.text)
        resposta.raise_for_status()

    dados = resposta.json()

    if "embedding" not in dados:
        raise RuntimeError(
            f"API não retornou embedding: {dados}"
        )

    vetor = dados["embedding"]["values"]

    return vetor, dados


async def popular_banco():

    with open(
        "database/atm10_knowledge_base.txt",
        "r",
        encoding="utf-8"
    ) as f:
        texto_completo = f.read()

    chunks = fatiar_texto_logico(texto_completo)

    print(
        f"Total de fragmentos lógicos gerados: "
        f"{len(chunks):,}"
    )

    if not chunks:
        print("Nenhum chunk encontrado.")
        return

    # ---------------------------------------------------------
    # 1. TESTE DE TOKENS
    # ---------------------------------------------------------

    amostra = chunks[:100]

    print(
        f"\nContando tokens de {len(amostra)} chunks "
        "para estimar o total..."
    )

    tokens_amostra = 0

    for i, chunk in enumerate(amostra, start=1):

        print(
            f"\n[DEBUG] Iniciando chunk {i}/{len(amostra)} "
            f"({len(chunk)} caracteres)",
            flush=True
        )

        try:
            tokens = contar_tokens(chunk)

            print(
                f"[DEBUG] API retornou {tokens} tokens",
                flush=True
            )

            tokens_amostra += tokens

        except Exception as e:
            print(
                f"\n[ERRO] Falha no chunk {i}",
                flush=True
            )
            print(
                f"[ERRO] Tipo: {type(e).__name__}",
                flush=True
            )
            print(
                f"[ERRO] Mensagem: {e}",
                flush=True
            )
            raise

        if i % 10 == 0 or i == len(amostra):
            print(
                f"  {i:3}/{len(amostra)} chunks | "
                f"{tokens_amostra:,} tokens",
                flush=True
            )

    media = tokens_amostra / len(amostra)
    estimativa_total = media * len(chunks)

    print("\n========== ESTIMATIVA ==========")
    print(f"Chunks totais:       {len(chunks):,}")
    print(f"Chunks amostrados:   {len(amostra):,}")
    print(f"Média:               {media:.2f} tokens/chunk")
    print(f"Estimativa total:    {estimativa_total:,.0f} tokens")
    print("================================")

    # ---------------------------------------------------------
    # 2. CONFIRMAÇÃO
    # ---------------------------------------------------------

    confirmar = input(
        "\nGerar embedding APENAS do primeiro chunk "
        "e inserir no banco? [s/N]: "
    ).strip().lower()

    if confirmar != "s":
        print("Operação cancelada.")
        return

    # ---------------------------------------------------------
    # 3. PRIMEIRO CHUNK
    # ---------------------------------------------------------

    primeiro_chunk = chunks[0]

    print("\n========== PRIMEIRO CHUNK ==========")
    print(primeiro_chunk)
    print("====================================")

    tokens_primeiro = contar_tokens(primeiro_chunk)

    print(
        f"\nTokens do primeiro chunk: "
        f"{tokens_primeiro}"
    )

    # ---------------------------------------------------------
    # 4. GERAR EMBEDDING
    # ---------------------------------------------------------

    print("\nGerando embedding...")

    vetor, resposta_embedding = gerar_embedding(
        primeiro_chunk
    )

    print("\n========== EMBEDDING ==========")
    print(f"Tipo:       {type(vetor)}")
    print(f"Dimensão:   {len(vetor)}")
    print(f"Primeiros 10 valores:")
    print(vetor[:10])
    print(f"Últimos 10 valores:")
    print(vetor[-10:])
    print("===============================")

    print("\nResposta completa da API:")
    print(resposta_embedding)

    # ---------------------------------------------------------
    # 5. CONECTAR AO POSTGRES
    # ---------------------------------------------------------

    conn = await asyncpg.connect(
        user="pyxis_admin",
        password=os.environ.get("DB_PASSWORD"),
        database="telemetria",
        host="db"
    )

    try:

        print("\nConectado ao PostgreSQL.")

        # -----------------------------------------------------
        # 6. INSERIR PRIMEIRO CHUNK
        # -----------------------------------------------------

        # ATENÇÃO:
        # Aqui usamos a representação textual do pgvector.
        # Exemplo:
        # [0.123,0.456,-0.789,...]

        vetor_pgvector = "[" + ",".join(
            str(float(x)) for x in vetor
        ) + "]"

        resultado = await conn.fetchrow(
            """
            INSERT INTO base_conhecimento
                (texto, embedding)
            VALUES
                ($1, $2::vector)
            RETURNING id, texto, embedding
            """,
            primeiro_chunk,
            vetor_pgvector
        )

        print("\n========== INSERÇÃO ==========")
        print(f"ID inserido: {resultado['id']}")
        print(f"Texto armazenado:")
        print(resultado["texto"])

        embedding_banco = resultado["embedding"]

        print("\nEmbedding retornado pelo PostgreSQL:")
        print(embedding_banco)

        print("==============================")

        print(
            "\nTeste concluído: primeiro chunk "
            "vetorizado e armazenado com sucesso."
        )

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(popular_banco())