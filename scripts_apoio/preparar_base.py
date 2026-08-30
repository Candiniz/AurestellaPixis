import os
import requests
import asyncpg
import asyncio
import re

API_KEY = os.environ.get("GEMINI_API_KEY")
URL_EMBEDDING = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={API_KEY}"

def fatiar_texto_logico(texto):
    # Separa os blocos usando "quest." para manter o contexto lógico de cada missão
    chunks = re.split(r'(?=quest\.)', texto)
    return [c.strip() for c in chunks if len(c.strip()) > 50]

async def popular_banco():
    with open("database/atm10_knowledge_base.txt", "r", encoding="utf-8") as f:
        texto_completo = f.read()

    chunks = fatiar_texto_logico(texto_completo)
    
    # O host é 'localhost' se você for rodar este script por dentro da VPS.
    conn = await asyncpg.connect(user="pyxis_admin", password=os.environ.get("DB_PASSWORD"), database="telemetria", host="db")
    
    print(f"Total de fragmentos lógicos gerados: {len(chunks)}")
    
    # Fazendo um teste com o primeiro fragmento para medir o custo
    payload_teste = {"model": "models/text-embedding-004", "content": {"parts": [{"text": chunks[0]}]}}
    res_teste = requests.post(URL_EMBEDDING, json=payload_teste).json()
    
    uso = res_teste.get("usageMetadata", {})
    tokens_teste = uso.get("totalTokenCount", 0)
    print(f"\n[TESTE DE CUSTO] O fragmento 1 consumiu {tokens_teste} tokens para gerar os embeddings.")
    print(f"Estimativa para o arquivo todo ({len(chunks)} fragmentos): ~{tokens_teste * len(chunks)} tokens.")
    
    confirmar = input("Deseja iniciar a vetorização completa e salvar no banco? (s/n): ")
    if confirmar.lower() != 's':
        await conn.close()
        return

    print("Iniciando injeção vetorial...")
    for chunk in chunks:
        payload = {"model": "models/text-embedding-004", "content": {"parts": [{"text": chunk}]}}
        resposta = requests.post(URL_EMBEDDING, json=payload).json()
        
        if 'embedding' in resposta:
            vetor = resposta['embedding']['values'] 
            await conn.execute("INSERT INTO base_conhecimento (texto, embedding) VALUES ($1, $2)", chunk, str(vetor))
            
    await conn.close()
    print("Base vetorizada com sucesso, Vossa Graça!")

if __name__ == "__main__":
    asyncio.run(popular_banco())