import os

pasta = "database/chapters_clean"

for arquivo in os.listdir(pasta):
    nome, extensao = os.path.splitext(arquivo)

    if nome.endswith("_clean"):
        novo_nome = nome[:-6] + extensao

        caminho_antigo = os.path.join(pasta, arquivo)
        caminho_novo = os.path.join(pasta, novo_nome)

        os.rename(caminho_antigo, caminho_novo)

        print(f"{arquivo} -> {novo_nome}")
            