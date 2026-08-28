import os
import json
import requests
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# Sessão global instanciada fora da rota para manter a conexão TCP aberta
sessao = requests.Session()

class RequisicaoMinecraft(BaseModel):
    comando: str

@app.post("/agente")
def processar_comando(req: RequisicaoMinecraft):
    api_key = os.environ.get("GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.7-flash:generateContent?key={api_key}"
    
    # Instruções do sistema com Few-Shot Prompting (Exemplos de mapeamento)
    instrucao = (
        "Você é a IA central de uma base no Minecraft. "
        "Sua função é mapear a intenção do usuário para UMA ação da lista permitida. "
        "Seja sarcástico na fala. "
        "Exemplos de mapeamento:\n"
        "- Usuário: 'Não enxergo nada.' -> Ação: 'lightsOn'\n"
        "- Usuário: 'Hora de dormir.' -> Ação: 'lightsOff'\n"
        "- Usuário: 'Abre aí, cheguei.' -> Ação: 'openDoor'"
    )
    
    payload = {
        "systemInstruction": {
            "parts": [{"text": instrucao}]
        },
        "contents": [
            {"parts": [{"text": req.comando}]}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "fala": {"type": "STRING"},
                    "acao": {
                        "type": "STRING",
                        "enum": ["lightsOn", "lightsOff", "openDoor", "none"]
                    }
                },
                "required": ["fala", "acao"]
            }
        }
    }
    
    resposta = sessao.post(url, json=payload, headers={"Content-Type": "application/json"})
    dados = resposta.json()
    
    if "candidates" not in dados:
        return {"erro_comunicacao_google": dados}
        
    texto_gerado = dados["candidates"][0]["content"]["parts"][0]["text"]
    
    return json.loads(texto_gerado)