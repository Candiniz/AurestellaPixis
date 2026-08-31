<div align="center"><img src="https://i.imgur.com/C5HzS6l.png" width="500"></div>

Bem-vindo ao repositorio do Aurestella Pyxis, um agente de Inteligencia Artificial integrado nativamente ao Minecraft (modpack ATM10). Projetado para atuar como assistente pessoal do Grao-Duque da Cidade-Estado de Aurestella (o jogador), o Pyxis transcende os chatbots comuns: ele interpreta intencoes por chat, controla estruturas fisicas da base via redstone e consulta uma base de conhecimentos de forma dinamica para auxiliar em automacoes complexas.

---

## Arquitetura do Sistema

End-to-End Agent Pipeline: fluxo completo de execução, desde a captura da intenção no cliente Minecraft até o processamento da requisição, tomada de decisão, recuperação de contexto e geração da resposta.

* **Front-end (Minecraft / ComputerCraft):** Um script Lua assincrono rodando em um Advanced Computer com Chat Box e Advanced Monitors. Possui uma maquina de estados que exibe uma interface animada (um rosto reagindo e mensagens de carregamento) enquanto processa os chamados simultaneamente. O front-end captura gatilhos no chat e aciona o back-end via requisicao HTTP POST.
* **Back-end (FastAPI / Python):** Um servidor orquestrador hospedado em uma VPS Oracle via Docker. Ele recebe o comando, verifica a seguranca (API Key via header) e inicia o pipeline cognitivo.
* **Pipeline de Inteligencia Artificial (Agentic Routing & RAG Hibrido):**
  1. **Roteador de Intencoes:** Gemini Flash-Lite classifica a intenção do usuário e produz uma resposta estruturada via JSON Schema, determinando a ação a executar e, para consultas cognitivas, os parâmetros de recuperação.
  2. **RAG Vetorial Dinamico:** Se for uma duvida, o sistema aciona o banco de dados PostgreSQL. Atraves da extensao pgvector e Busca vetorial por distância de cosseno usando pgvector, extrai os paragrafos matematicamente relevantes da wiki do jogo. Em paralelo, utiliza Fuzzy Matching no Python para resgatar o contexto de arvores de dependencias locais, enviando um payload enxuto ao modelo.
* **Telemetria Assincrona:** A cada requisicao finalizada, o uso de tokens (prompt, output) e a latencia (ms) sao registrados silenciosamente (via BackgroundTasks do FastAPI) na base de dados para exibicao em monitores in-game.


---


```
# FLUXOGRAMA DO AGENTE
[Usuário in-game] -- "Pyxis, como faço uma ATM Star?" --> [Lua (ComputerCraft)]
   | (Animação de rosto em loop paralelo via `parallel.waitForAny()`)
   v
[HTTP POST Assíncrono] --> [Internet]
   |
[Domínio DuckDNS + HTTPS]
   v
[Proxy Reverso: Nginx (Porta 443)] -- Descriptografa SSL e repassa --> [Docker: FastAPI-based REST API (Porta 8000)]
   |
[Segurança] -- Valida Header `X-Pyxis-Key` via `Depends()`
   |
[Roteador: Gemini Flash-Lite] -- Analisa intenção (JSON Schema Forçado)
   |
BIFURCAÇÃO DE INTENÇÃO:
├──> 1. AÇÃO FÍSICA (`lightsOn`, `openDoor`, `lightsOff`)
│     └──> Resposta Imediata --> Lua ativa blocos de Redstone (Simulação IoT)
│
└──> 2. CONSULTA COGNITIVA (`consultarBase` + `termo_pesquisa`)
      ├──> A. Gemini Embedding vetoriza o termo de pesquisa
      ├──> B. PostgreSQL (pgvector) faz busca semântica por cosseno (LIMIT 8)
      ├──> C. Gemini 3.5 Flash recebe os fragmentos do banco e sintetiza o contexto
      └──> Resposta Textual --> Lua formata caracteres e imprime na tela
   |
[BackgroundTasks (FastAPI)] --> Captura `usageMetadata` (Tokens) e Latência -> Grava no PostgreSQL sem bloquear a thread de resposta ao usuário.
```

---

## Tech Stack

**Infraestrutura & DevOps:**
* Oracle Cloud VPS (Always Free)
* Docker & Docker Compose
* DuckDNS & Let's Encrypt (HTTPS)
* Nginx (Proxy Reverso)

**Back-end & IA:**
* Python 3.9-slim
* FastAPI & Uvicorn
* Google Gemini API (gemini-3.5-flash-lite, gemini-3.5-flash, text-embedding-2)
* Pydantic

**Banco de Dados:**
* PostgreSQL (Container Alpine)
* pgvector
* asyncpg

**Front-end (In-Game):**
* ComputerCraft (Lua 5.1)
* Advanced Peripherals

---
