# A Classe FilesApi está oficialmente como LEGADO
import asyncio
import os
import requests


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