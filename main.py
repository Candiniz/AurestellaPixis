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
    try:
        # O 'host' é "db", que é exatamente o nome do serviço no docker-compose.yml
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
    except Exception as e:
        print(f"Aviso: Não foi possível conectar ao banco de dados: {e}")
        
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

@app.post("/agente")
def processar_comando(req: RequisicaoMinecraft, api_key: str = Depends(verificar_api_key)):
    resultado_roteador = gemini.chamar_roteador_gemini(req.comando)
    
    if resultado_roteador.get("acao") == "consultarBase":
        resposta_rag = gemini.chamar_gemini_rag(
            termo_pesquisa=resultado_roteador["termo_pesquisa"],
            fonte=resultado_roteador.get("fonte", "none")
        )
        resposta_final = {
            "fala": resposta_rag,
            "acao": "none"
        }
        return Response(content=json.dumps(resposta_final, ensure_ascii=True), media_type="application/json")
    
    return Response(content=json.dumps(resultado_roteador, ensure_ascii=True), media_type="application/json")
