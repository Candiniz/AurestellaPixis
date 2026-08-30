import os
import json
import asyncio
import asyncpg
from fastapi import FastAPI, Response, Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from contextlib import asynccontextmanager
from lib.gemini.MetodosGemini import Gemini, FilesApi


files_api = FilesApi()
gemini = Gemini(files_api)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(files_api.loop_renovacao_arquivo())

    # Conecta no PostgreSQL e garante a criação da tabela
    # Tenta conectar ao banco até 5 vezes, esperando 3 segundos entre cada tentativa
    for tentativa in range(5):
        try:
            conn = await asyncpg.connect(
                user="pyxis_admin",
                password=os.environ.get("DB_PASSWORD"),
                database="telemetria",
                host="db"
            )
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS consumo_tokens (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    endpoint VARCHAR(50) NOT NULL,
                    latencia_ms REAL,
                    prompt_tokens INTEGER,
                    output_tokens INTEGER,
                    total_tokens INTEGER
                );
            ''')
            await conn.close()
            print("Tabela de telemetria verificada/criada com sucesso.")
            break  # Sai do laço se a conexão for um sucesso
        except Exception as e:
            print(f"Aguardando banco de dados (Tentativa {tentativa+1}/5)...")
            await asyncio.sleep(3)
        
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

NOME_CABECALHO_API = "X-Pyxis-Key"
CHAVE_SECRETA = os.environ.get("PYXIS_API_KEY")
api_key_header = APIKeyHeader(name=NOME_CABECALHO_API, auto_error=False)

async def verificar_api_key(api_key: str = Security(api_key_header)):
    if api_key != CHAVE_SECRETA:
        raise HTTPException(
            status_code=403, 
            detail="Acesso Negado: Você não é o Grão-Duque."
        )
    return api_key

class RequisicaoMinecraft(BaseModel):
    comando: str

import time
from fastapi import BackgroundTasks  # <-- 1. Importe o BackgroundTasks

# Função auxiliar assíncrona para gravar no banco sem travar a resposta
async def registrar_telemetria(endpoint: str, latencia: float, usage: dict):
    if not usage:
        return
    try:
        conn = await asyncpg.connect(
            user="pyxis_admin",
            password=os.environ.get("DB_PASSWORD"),
            database="telemetria",
            host="db"
        )
        await conn.execute('''
            INSERT INTO consumo_tokens (endpoint, latencia_ms, prompt_tokens, output_tokens, total_tokens)
            VALUES ($1, $2, $3, $4, $5)
        ''', 
            endpoint, 
            latencia * 1000,  # Convertendo para milissegundos
            usage.get("promptTokenCount", 0),
            usage.get("candidatesTokenCount", 0),
            usage.get("totalTokenCount", 0)
        )
        await conn.close()
    except Exception as e:
        print(f"Erro ao salvar telemetria no banco: {e}")

@app.post("/agente")
def processar_comando(
    req: RequisicaoMinecraft, 
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verificar_api_key)
):
    inicio = time.time()

    # Executa o roteador (3.5 Flash-Lite)
    resultado_roteador = gemini.chamar_roteador_gemini(req.comando)
    # Capturando metadados
    usage = resultado_roteador.pop("usageMetadata", {}) 
    
    fim = time.time()
    latencia = fim - inicio

    # 3. Dispara a gravação em segundo plano após a resposta já ter sido enviada
    background_tasks.add_task(registrar_telemetria, "/agente-roteador", latencia, usage)

    # Executa o rag (3.5 Flash)
    if resultado_roteador.get("acao") == "consultarBase":
        resposta_rag = gemini.chamar_gemini_rag(
            termo_pesquisa=resultado_roteador["termo_pesquisa"],
            fonte=resultado_roteador.get("fonte", "none")
        )
        fala_rag = resposta_rag.get("fala", "")
        usage_rag = resposta_rag.get("usageMetadata", {})
        background_tasks.add_task(registrar_telemetria, "/agente-rag", latencia, usage_rag)

        resposta_final = {
            "fala": fala_rag,
            "acao": "none"
        }
        return Response(content=json.dumps(resposta_final, ensure_ascii=True), media_type="application/json")
    
    return Response(content=json.dumps(resultado_roteador, ensure_ascii=True), media_type="application/json")

@app.get("/telemetria")
async def obter_telemetria(api_key: str = Depends(verificar_api_key)):
    try:
        conn = await asyncpg.connect(
            user="pyxis_admin",
            password=os.environ.get("DB_PASSWORD"),
            database="telemetria",
            host="db"
        )
        # Busca a soma total e a última requisição
        registro = await conn.fetchrow('''
            SELECT 
                SUM(total_tokens) as tokens_gastos,
                COUNT(id) as total_requisicoes
            FROM consumo_tokens
        ''')
        await conn.close()

        return {
            "tokens_totais": registro["tokens_gastos"] or 0,
            "requisicoes": registro["total_requisicoes"] or 0
        }
    except Exception as e:
        return {"erro": str(e)}