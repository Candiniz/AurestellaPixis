import os
import json
import time
import asyncio
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from contextlib import asynccontextmanager

sessao = requests.Session()

# Variável global para armazenar a URI do arquivo
KNOWLEDGE_BASE_URI = None

def fazer_upload_base():
    global KNOWLEDGE_BASE_URI
    api_key = os.environ.get("GEMINI_API_KEY")
    caminho_arquivo = "atm10_knowledge_base.txt"
    
    if not os.path.exists(caminho_arquivo):
        print(f"ERRO CRÍTICO: Arquivo {caminho_arquivo} não encontrado na raiz.")
        return
        
    url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}"
    headers = {
        "X-Goog-Upload-Protocol": "raw",
        "X-Goog-Upload-File-Name": caminho_arquivo,
        "Content-Type": "text/plain"
    }
    
    print("Iniciando upload da base de conhecimento do ATM10...")
    with open(caminho_arquivo, "rb") as f:
        dados = f.read()
        
    resposta = requests.post(url, headers=headers, data=dados)
    if resposta.status_code == 200:
        json_resp = resposta.json()
        KNOWLEDGE_BASE_URI = json_resp["file"]["uri"]
        print(f"Upload concluído com sucesso. Nova URI ativada: {KNOWLEDGE_BASE_URI}")
    else:
        print(f"Falha ao realizar upload para a File API: {resposta.text}")

async def loop_renovacao_arquivo():
    while True:
        # Executa o upload síncrono em uma thread separada para não travar a API
        await asyncio.to_thread(fazer_upload_base)
        # Suspende a rotina por 47 horas (169200 segundos)
        await asyncio.sleep(169200)

# Gerencia o que acontece quando o servidor liga e desliga
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicia a tarefa de upload em segundo plano assim que o Uvicorn subir
    task = asyncio.create_task(loop_renovacao_arquivo())
    yield
    # Cancela a tarefa caso o contêiner seja parado
    task.cancel()

app = FastAPI(lifespan=lifespan)

class RequisicaoMinecraft(BaseModel):
    comando: str

def chamar_roteador_gemini(comando: str, tentativas=3):
    api_key = os.environ.get("GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
    
    instrucao = (
        "Você é Aurestella, a IA central sarcástica de uma base no Minecraft. "
        "Sua função é atuar como um roteador de intenções. "
        "Se o usuário pedir algo físico na base, mapeie para 'lightsOn', 'lightsOff' ou 'openDoor'. "
        "Se o usuário pedir ajuda, dicas, ou explicações sobre mods, mapeie para 'consultarBase' e preencha o 'termo_pesquisa'."
    )
    
    payload = {
        "systemInstruction": {"parts": [{"text": instrucao}]},
        "contents": [{"parts": [{"text": comando}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "fala": {"type": "STRING"},
                    "acao": {"type": "STRING", "enum": ["lightsOn", "lightsOff", "openDoor", "consultarBase", "none"]},
                    "termo_pesquisa": {"type": "STRING"}
                },
                "required": ["fala", "acao", "termo_pesquisa"]
            }
        }
    }
    
    for tentativa in range(tentativas):
        resposta = sessao.post(url, json=payload, headers={"Content-Type": "application/json"})
        dados = resposta.json()
        if resposta.status_code == 200 and "candidates" in dados:
            return json.loads(dados["candidates"][0]["content"]["parts"][0]["text"])
        if "error" in dados and dados["error"].get("code") in [503, 429]:
            if tentativa < tentativas - 1:
                time.sleep(2 ** tentativa)
                continue
        return {"erro_comunicacao_google": dados}

def chamar_gemini_rag(termo_pesquisa: str, tentativas=3):
    global KNOWLEDGE_BASE_URI
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not KNOWLEDGE_BASE_URI:
        return "Meus arquivos ainda estão sendo carregados para a nuvem. Tente novamente em alguns segundos."
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={api_key}"
    
    instrucao = (
        "Você é Pyxis, a IA assistente pessoal do Grão-Duque de Aurestella (o jogador). "
        "Sua personalidade é semelhante ao Jarvis: extremamente leal, íntimo, pragmático e direto ao ponto. Sem bajulação ou drama. "
        "Baseie sua resposta EXCLUSIVAMENTE no documento anexo. "
        "REGRAS DE FORMATAÇÃO CRÍTICAS: "
        "1. Remova completamente códigos de configuração do jogo (ex: &a, &l, &r, quest.123.title, etc). Leia os dados, mas fale em português natural. "
        "2. NUNCA use emojis ou formatação Markdown (asteriscos, hashtags). "
        "3. Estruture sua resposta em três partes: Uma frase curta de introdução; uma lista direta com o prefixo '-' para ingredientes ou passos; uma frase curta de encerramento. "
        "Se a informação não estiver no documento, informe polidamente que os registros locais não possuem esses dados."
    )
    
    payload = {
        "systemInstruction": {"parts": [{"text": instrucao}]},
        "contents": [
            {
                "parts": [
                    {"fileData": {"mimeType": "text/plain", "fileUri": KNOWLEDGE_BASE_URI}},
                    {"text": f"Dúvida do usuário: {termo_pesquisa}"}
                ]
            }
        ],
        "generationConfig": {"temperature": 0.2}
    }
    
    for tentativa in range(tentativas):
        resposta = sessao.post(url, json=payload, headers={"Content-Type": "application/json"})
        dados = resposta.json()
        if resposta.status_code == 200 and "candidates" in dados:
            return dados["candidates"][0]["content"]["parts"][0]["text"]
        if "error" in dados and dados["error"].get("code") in [503, 429]:
            if tentativa < tentativas - 1:
                time.sleep(2 ** tentativa)
                continue
        return f"Erro nos bancos de dados corporativos: {dados}"

@app.post("/agente")
def processar_comando(req: RequisicaoMinecraft):
    resultado_roteador = chamar_roteador_gemini(req.comando)
    
    if resultado_roteador.get("acao") == "consultarBase":
        resposta_rag = chamar_gemini_rag(resultado_roteador["termo_pesquisa"])
        return {
            "fala": resposta_rag,
            "acao": "none"
        }
    
    return resultado_roteador