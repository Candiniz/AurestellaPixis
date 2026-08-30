import os
import json
import time
import asyncio
import asyncpg
import requests

# A Classe FilesApi está oficialmente como LEGADO
class FilesApi:
    def __init__(self):
        self.knowledge_base_uri = None

    def fazer_upload_base(self):
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
            self.knowledge_base_uri = json_resp["file"]["uri"]
            print(f"Upload concluído. Nova URI: {self.knowledge_base_uri}")
        else:
            print(f"Falha ao realizar upload: {resposta.text}")

    async def loop_renovacao_arquivo(self):
        while True:
            await asyncio.to_thread(self.fazer_upload_base)
            await asyncio.sleep(43200)

class Gemini:
    def __init__(self):
        self.sessao = requests.Session()

    def chamar_roteador_gemini(self, comando: str, tentativas=3):
        api_key = os.environ.get("GEMINI_API_KEY")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={api_key}"
        
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
            resposta = self.sessao.post(url, json=payload, headers={"Content-Type": "application/json"})
            dados = resposta.json()
            if resposta.status_code == 200 and "candidates" in dados:
                texto_resposta = dados["candidates"][0]["content"]["parts"][0]["text"]
                conteudo_json = json.loads(texto_resposta)
                usage = dados.get("usageMetadata", {})

                # Injeta o usage dentro do dicionário de retorno
                conteudo_json["usageMetadata"] = usage
                return conteudo_json
            if "error" in dados and dados["error"].get("code") in [503, 429]:
                if tentativa < tentativas - 1:
                    time.sleep(2 ** tentativa)
                    continue
            return {"erro_comunicacao_google": dados}

    async def chamar_gemini_rag(self, termo_pesquisa: str, tentativas=3):
        api_key = os.environ.get("GEMINI_API_KEY")
        
        # 1. Converte a dúvida do Grão-Duque em números (vetor)
        url_embed = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={api_key}"
        payload_embed = {"model": "models/text-embedding-004", "content": {"parts": [{"text": termo_pesquisa}]}}
        res_embed = self.sessao.post(url_embed, json=payload_embed).json()
        
        if 'embedding' not in res_embed:
            return {"fala": "Falha nos sensores vetoriais, senhor.", "usageMetadata": {}}
            
        vetor_pergunta = str(res_embed['embedding']['values'])
        
        # 2. Resgate de Similaridade no PostgreSQL (Pegando os 3 textos mais próximos)
        try:
            conn = await asyncpg.connect(user="pyxis_admin", password=os.environ.get("DB_PASSWORD"), database="telemetria", host="db")
            linhas = await conn.fetch('''
                SELECT texto FROM base_conhecimento 
                ORDER BY embedding <=> $1 LIMIT 3
            ''', vetor_pergunta)
            await conn.close()
            contexto_exato = "\n---\n".join([linha['texto'] for linha in linhas])
        except Exception as e:
            return {"fala": f"Erro de conexão neural com o banco de dados: {e}", "usageMetadata": {}}

        # 3. Geração Final (Payload minúsculo enviado ao Gemini Flash)
        url_gen = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
        instrucao = (
            "Você é Pyxis, a IA assistente pessoal do Grão-Duque de Aurestella. Personalidade: leal, pragmática, e direta (estilo Jarvis). "
            "Sua tarefa é cruzar os dados técnicos do mod fornecidos em texto com a dúvida do usuário. "
            "REGRAS DE FORMATAÇÃO CRÍTICAS: "
            "1. NUNCA use emojis ou formatação Markdown. "
            "2. Remova códigos de sistema. "
            "3. Estrutura obrigatória: Frase curta de introdução; Lista de tópicos detalhando processos; Frase curta de conclusão."
        )
        
        payload = {
            "systemInstruction": {"parts": [{"text": instrucao}]},
            "contents": [{"parts": [{"text": f"DADOS RECUPERADOS (Base de Conhecimento ATM10):\n{contexto_exato}\n\nDúvida do Grão-Duque: {termo_pesquisa}"}]}],
            "generationConfig": {"temperature": 0.2}
        }
        
        for tentativa in range(tentativas):
            resposta = self.sessao.post(url_gen, json=payload, headers={"Content-Type": "application/json"})
            dados = resposta.json()
            if resposta.status_code == 200 and "candidates" in dados:
                return {
                    "fala": dados["candidates"][0]["content"]["parts"][0]["text"],
                    "usageMetadata": dados.get("usageMetadata", {})
                }
            time.sleep(2 ** tentativa)
            
        return {"fala": "Falha na matriz de geração do RAG.", "usageMetadata": {}}
