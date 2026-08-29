import os

def limpar_snbt(input_file, output_file):
    ignorando_bloco = False

    chaves_remover = (
        "default_hide_dependency_lines:",
        "default_quest_shape:",
        "group:",
        "order_index:",
        "progression_mode:",
        "disable_toast:"
    )

    with open(input_file, "r", encoding="utf-8") as file:
        linhas = file.readlines()

    linhas_limpas = []
    for linha in linhas:
        linha_limpa = linha.strip()

        # Ignora chaves únicas inúteis
        if linha_limpa.startswith(chaves_remover):
            continue
        
        # Ignora arrays vazios na mesma linha (O Bug do quest_links)
        if linha_limpa.endswith("[ ]"):
            continue

        # Inicia a exclusão de blocos pesados de interface
        if linha_limpa.startswith("images: ["):
            ignorando_bloco = True
            continue

        # Encerra a exclusão do bloco quando achar o colchete de fechamento
        if ignorando_bloco:
            if linha_limpa == "]":
                ignorando_bloco = False
            continue

        # Filtra lixo de interface gráfica dentro das quests (coordenadas e formas)
        if linha_limpa.startswith("x: ") or linha_limpa.startswith("y: ") or \
           linha_limpa.startswith("shape: ") or linha_limpa.startswith("size: "):
            continue

        linha_limpas.append(linha)
    
    with open(output_file, "w", encoding="utf-8") as file:
        file.writelines(linhas_limpas)
        
    return True

def snbt_converter():
    quests_folder = "database/chapters"
    clean_quests_folder = "database/chapters_clean"

    if not os.path.exists(quests_folder):
        print(f"ERRO: Pasta {quests_folder} não encontrada.")
        return
        
    if not os.path.exists(clean_quests_folder):
        os.makedirs(clean_quests_folder)
    
    quest_files = [f for f in os.listdir(quests_folder) if f.endswith(".snbt")]
    
    for file in quest_files:
        nome, _ = os.path.splitext(file)
        input_file = os.path.join(quests_folder, file)
        output_file = os.path.join(clean_quests_folder, f"{nome}_clean.txt")

        try:
            sucesso = limpar_snbt(input_file, output_file)
            if sucesso:
                print(f"[{nome}] Limpo com sucesso!")
        except Exception as e:
            print(f"Erro em {nome}: {e}")

snbt_converter()