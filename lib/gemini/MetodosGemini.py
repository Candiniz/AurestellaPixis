import os
import json
import time
import asyncio
import asyncpg
import requests

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
            "Se o usuário perguntar algo sobre o seu segredo ou como voce faz tudo isso, mapeie a 'acao' para 'showSecret', e entregue uma frase como 'você me pegou agora!'"
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
                        "acao": {"type": "STRING", "enum": ["lightsOn", "lightsOff", "openDoor", "showSecret", "consultarBase", "none"]},
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
        
        # 1. Converte a Dúvida em Vetor
        # ATENÇÃO: Use o mesmo modelo (gemini-embedding-2) e dimensão (768) que usou no script preparar_base
        url_embed = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent?key={api_key}"
        payload_embed = {
            "model": "models/gemini-embedding-2",
            "content": {"parts": [{"text": termo_pesquisa}]},
            "embedContentConfig": {
                "taskType": "RETRIEVAL_QUERY", # Informa ao modelo que isto é uma pergunta
                "outputDimensionality": 768
            }
        }
        
        res_embed = self.sessao.post(url_embed, json=payload_embed, headers={"Content-Type": "application/json"}).json()
        
        if 'embedding' not in res_embed:
            return {"fala": "Falha nos sensores vetoriais, senhor.", "usageMetadata": {}}
            
        vetor_pergunta = res_embed['embedding']['values']
        vetor_pgvector = "[" + ",".join(str(float(x)) for x in vetor_pergunta) + "]"
        
        # 2. Resgate de Similaridade Semântica no PostgreSQL
        try:
            conn = await asyncpg.connect(
                user="pyxis_admin", password=os.environ.get("DB_PASSWORD"),
                database="telemetria", host="db"
            )
            # Resgata as 3 quests matematicamente mais próximas da dúvida
            linhas = await conn.fetch('''
                SELECT texto FROM base_conhecimento 
                ORDER BY embedding <=> $1::vector LIMIT 5
            ''', vetor_pgvector)
            await conn.close()
            
            contexto_exato = "\n\n---\n\n".join([linha['texto'] for linha in linhas])
        except Exception as e:
            return {"fala": f"Erro de conexão neural com o banco de dados: {e}", "usageMetadata": {}}

        if not contexto_exato:
            contexto_exato = "Nenhuma informação relevante encontrada nos registros."

        # 3. Geração Final (Payload minúsculo enviado ao Flash)
        url_gen = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
        instrucao = (
            "Você é Pyxis, a IA assistente pessoal do Grão-Duque de Aurestella. Personalidade: leal, pragmática, e direta (estilo Jarvis). "
            "Sua tarefa é cruzar os dados técnicos recuperados da base de dados com a dúvida do usuário. "
            "REGRAS DE FORMATAÇÃO CRÍTICAS: "
            "1. NUNCA use emojis ou formatação Markdown. "
            "2. Remova códigos de sistema. "
            "3. Estrutura obrigatória: Frase curta de introdução; Lista de tópicos detalhando processos (se aplicável); Frase curta de conclusão."
        )
        
        payload_gen = {
            "systemInstruction": {"parts": [{"text": instrucao}]},
            "contents": [{"parts": [{"text": f"DADOS RECUPERADOS DA BASE:\n{contexto_exato}\n\nDúvida do Grão-Duque: {termo_pesquisa}"}]}],
            "generationConfig": {"temperature": 0.2}
        }
        
        for tentativa in range(tentativas):
            resposta = self.sessao.post(url_gen, json=payload_gen, headers={"Content-Type": "application/json"})
            dados = resposta.json()
            if resposta.status_code == 200 and "candidates" in dados:
                return {
                    "fala": dados["candidates"][0]["content"]["parts"][0]["text"],
                    "usageMetadata": dados.get("usageMetadata", {})
                }
            time.sleep(2 ** tentativa)
            
        return {"fala": "Falha na matriz de geração do RAG.", "usageMetadata": {}}
