import os
import json
import time
import asyncio
import requests
import difflib
from fastapi import FastAPI
from pydantic import BaseModel
from contextlib import asynccontextmanager

sessao = requests.Session()

# Variável global para armazenar a URI do arquivo de linguagem (en_us)
KNOWLEDGE_BASE_URI = None

def fazer_upload_base():
    global KNOWLEDGE_BASE_URI
    api_key = os.environ.get("GEMINI_API_KEY")
    caminho_arquivo = "database/atm10_knowledge_base.txt"
    
    if not os.path.exists(caminho_arquivo):
        print(f"ERRO CRÍTICO: Arquivo {caminho_arquivo} não encontrado.")
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
        print(f"Upload concluído. Nova URI: {KNOWLEDGE_BASE_URI}")
    else:
        print(f"Falha ao realizar upload: {resposta.text}")

async def loop_renovacao_arquivo():
    while True:
        await asyncio.to_thread(fazer_upload_base)
        await asyncio.sleep(43200)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(loop_renovacao_arquivo())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

class RequisicaoMinecraft(BaseModel):
    comando: str

def chamar_roteador_gemini(comando: str, tentativas=3):
    api_key = os.environ.get("GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
    
    instrucao = (
        "Você é Pyxis, a IA assistente pessoal do Grão-Duque de Aurestella (o jogador). "
        "Sua personalidade é semelhante ao Jarvis: leal, pragmático e direto ao ponto. "
        "Se o usuário pedir algo físico na base, mapeie 'acao' para 'lightsOn', 'lightsOff' ou 'openDoor', 'fala' com uma confirmação respeitosa, e mapeie 'termo_pesquisa' e 'fonte' como 'none'. "
        "Se o usuário pedir ajuda sobre mods ou itens, mapeie 'acao' para 'consultarBase', preencha 'termo_pesquisa' com o assunto, e preencha 'fonte' com o nome exato do mod no padrão 'snake_case.txt'. "
        "Exemplo: 'Como faço um Diamond Bee?' -> acao: 'consultarBase', termo_pesquisa: 'Criação do Diamond Bee', fonte: 'productive_bees.txt'."
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
                    "termo_pesquisa": {"type": "STRING"},
                    "fonte": {"type": "STRING"}
                },
                "required": ["fala", "acao", "termo_pesquisa", "fonte"]
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

def chamar_gemini_rag(termo_pesquisa: str, fonte: str, tentativas=3):
    global KNOWLEDGE_BASE_URI
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not KNOWLEDGE_BASE_URI:
        return "Meus registros estão nebulosos. Tente em alguns segundos."
        
    # Lógica de Fuzzy Matching para encontrar o arquivo local do mod
    conteudo_mod_local = "Arquivo técnico do mod não localizado."
    caminho_quests = "database/chapters_clean"
    
    if fonte and fonte != "none" and os.path.exists(caminho_quests):
        arquivos_disponiveis = os.listdir(caminho_quests)
        matches = difflib.get_close_matches(fonte, arquivos_disponiveis, n=1, cutoff=0.5)
        
        if matches:
            with open(os.path.join(caminho_quests, matches[0]), "r", encoding="utf-8") as f:
                conteudo_mod_local = f.read()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
    
    instrucao = (
        "Você é Pyxis, a IA assistente pessoal do Grão-Duque de Aurestella. Personalidade: leal, pragmática, e direta (estilo Jarvis). "
        "Sua tarefa é cruzar os dados técnicos do mod fornecidos em texto com as descrições no arquivo anexo. Use os IDs para conectar as informações. "
        "REGRAS DE FORMATAÇÃO CRÍTICAS: "
        "1. NUNCA use emojis ou formatação Markdown (asteriscos, hashtags, negrito). "
        "2. Remova códigos de sistema como &a, &l, ou IDs brutos (quest.123). "
        "3. Estrutura obrigatória: Frase curta de introdução; Lista de tópicos com prefixo '-' detalhando materiais ou processos; Frase curta de conclusão. "
        "Traduza livremente a lógica estrutural para um passo a passo fluido em português, mas mantenha os nomes dos ítens no idioma original (inglês)"
    )
    
    payload = {
        "systemInstruction": {"parts": [{"text": instrucao}]},
        "contents": [
            {
                "parts": [
                    {"fileData": {"mimeType": "text/plain", "fileUri": KNOWLEDGE_BASE_URI}},
                    {"text": f"DADOS TÉCNICOS DO MOD (Requisitos e dependências):\n{conteudo_mod_local}\n\nDúvida do Grão-Duque: {termo_pesquisa}"}
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
        return f"Houve uma falha na matriz de dados, Vossa Graça: {dados}"

@app.post("/agente")
def processar_comando(req: RequisicaoMinecraft):
    resultado_roteador = chamar_roteador_gemini(req.comando)
    
    if resultado_roteador.get("acao") == "consultarBase":
        resposta_rag = chamar_gemini_rag(
            termo_pesquisa=resultado_roteador["termo_pesquisa"],
            fonte=resultado_roteador.get("fonte", "none")
        )
        return {
            "fala": resposta_rag,
            "acao": "none"
        }
    
    return resultado_roteador