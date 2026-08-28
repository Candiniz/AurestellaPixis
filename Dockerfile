# Usa uma imagem oficial e enxuta do Python
FROM python:3.9-slim

# Define o diretório de trabalho dentro do contêiner
WORKDIR /app

# Copia apenas os requisitos primeiro (otimiza o cache do Docker)
COPY requirements.txt .

# Instala as dependências sem armazenar cache para economizar espaço
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código para o contêiner
COPY . .

# Sinaliza a porta que a aplicação vai utilizar
EXPOSE 8000

# Comando para iniciar o servidor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]