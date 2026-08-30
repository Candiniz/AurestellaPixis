import os
import requests
import asyncpg
import asyncio
import re
import sys

API_KEY = os.environ.get("GEMINI_API_KEY")

URL_COUNT_TOKENS = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:countTokens?key={API_KEY}"
URL_EMBEDDING = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={API_KEY}"

def fatiar_texto_logico(texto):
    chunks = re.split(r'(?=quest\.)', texto)
    return [c.strip() for c in chunks if len(c.strip()) > 50]

def contar_tokens(chunk):
    payload = {"contents": [{"parts": [{"text": chunk}]}]}
    resposta = requests.post(URL_COUNT_TOKENS, json=payload, headers={"Content-Type": "application/json"}, timeout=60)
    
    if not resposta.ok:
        print(f"Erro CountTokens HTTP {resposta.status_code}: {resposta.text}", flush=True)
        resposta.raise_for_status()

    return resposta.json().get("totalTokens", 0)

def gerar_embedding(chunk):
    payload = {"model": "models/text-embedding-004", "content": {"parts": [{"text": chunk}]}}
    resposta = requests.post(URL_EMBEDDING, json=payload, headers={"Content-Type": "application/json"}, timeout=60)
    
    if not resposta.ok:
        print(f"Erro Embedding HTTP {resposta.status_code}: {resposta.text}", flush=True)
        resposta.raise_for_status()

    dados = resposta.json()
    return dados["embedding"]["values"], dados

async def popular_banco():
    caminho = "database/atm10_knowledge_base.txt"
    if not os.path.exists(caminho):
        print(f"Erro: O arquivo {caminho} não foi encontrado no container.", flush=True)
        return

    with open(caminho, "r", encoding="utf-8") as f:
        texto_completo = f.read()

    chunks = fatiar_texto_logico(texto_completo)
    print(f"Total de fragmentos lógicos gerados: {len(chunks):,}", flush=True)

    if not chunks:
        print("Nenhum chunk encontrado.", flush=True)
        return

    amostra = chunks[:10]
    print(f"\nContando tokens de {len(amostra)} chunks para estimar o total...", flush=True)

    tokens_amostra = 0
    for i, chunk in enumerate(amostra, start=1):
        try:
            tokens = contar_tokens(chunk)
            tokens_amostra += tokens
            print(f"Chunk {i}/{len(amostra)}: {tokens} tokens.", flush=True)
        except Exception as e:
            print(f"Falha no chunk {i}: {e}", flush=True)
            return

    media = tokens_amostra / len(amostra)
    estimativa_total = media * len(chunks)

    print("\n========== ESTIMATIVA ==========")
    print(f"Chunks totais:       {len(chunks):,}")
    print(f"Média:               {media:.2f} tokens/chunk")
    print(f"Estimativa total:    {estimativa_total:,.0f} tokens")
    print("================================")

    confirmar = input("\nGerar embedding APENAS do primeiro chunk e inserir no banco? [s/N]: ").strip().lower()
    if confirmar != "s":
        print("Operação cancelada.")
        return

    primeiro_chunk = chunks[0]
    print("\nGerando embedding do primeiro bloco...")
    vetor, resposta_embedding = gerar_embedding(primeiro_chunk)

    print(f"Dimensão do vetor gerado: {len(vetor)} (Primeiros 3: {vetor[:3]})")

    conn = await asyncpg.connect(user="pyxis_admin", password=os.environ.get("DB_PASSWORD"), database="telemetria", host="db")
    try:
        vetor_pgvector = "[" + ",".join(str(float(x)) for x in vetor) + "]"
        
        resultado = await conn.fetchrow("""
            INSERT INTO base_conhecimento (texto, embedding)
            VALUES ($1, $2::vector) RETURNING id
        """, primeiro_chunk, vetor_pgvector)
        
        print(f"\nSucesso absoluto. ID inserido na tabela vetorial: {resultado['id']}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(popular_banco())