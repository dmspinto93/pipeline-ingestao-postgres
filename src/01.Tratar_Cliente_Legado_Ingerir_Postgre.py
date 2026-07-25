import pandas as pd
import psycopg2
import numpy as np

# 1. LÊ O ARQUIVO CSV
# Usando o pandas para carregar os dados
df_clientes = pd.read_csv('/app/data/clientes_legado.csv', sep=';',
                          encoding='latin1')

# 2. TRATA OS DADOS NO CÓDIGO (PIPELINE)
# Limpa o CPF deixando só os números
df_clientes['cpf_limpo'] = df_clientes['cpf'].astype(str).str.replace(r'\D', '', regex=True)

# Adiciona zeros à esquerda para CPFs que perderam o zero no sistema legado
df_clientes['cpf_limpo'] = df_clientes['cpf_limpo'].str.zfill(11)

# Remove as linhas com CPF duplicado, mantendo apenas a última ocorrência
df_clientes = df_clientes.drop_duplicates(subset=['cpf_limpo'], keep='last')

# Transforma o "-" em NaN antes de converter tudo para None
df_clientes['email'] = df_clientes['email'].replace(['-', '', ' '], np.nan)

# Remove acentos dos e-mails mantendo como string normal
df_clientes['email'] = df_clientes['email'].str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode(
    'utf-8')

# Troca todos os 'NaN' (Not a Number) por None (que vira NULL no banco)
df_clientes = df_clientes.replace({np.nan: None})

# Arruma a data para o padrão ISO (YYYY-MM-DD)
df_clientes['dt_cadastro_iso'] = pd.to_datetime(df_clientes['dt_cadastro'], format='mixed', dayfirst=True).dt.strftime(
    '%Y-%m-%d')

# 3. CONECTA NO BANCO E PREPARA INSERÇÃO
# Abre a conexão com o seu Postgres 16
conexao = psycopg2.connect(host="host.docker.internal", database="legado", user="postgres", password="Dsl@0194")
cursor = conexao.cursor()

# A query SQL para a tabela principal
query_sql = """
            INSERT INTO clientes_legado (id_legado, cpf, nome, email, cidade, dt_cadastro)
            VALUES (%(id_legado)s, %(cpf_limpo)s, TRIM(%(nome)s), TRIM(LOWER(%(email)s)), INITCAP(TRIM(%(cidade)s)), \
                    %(dt_cadastro_iso)s::DATE) ON CONFLICT (id_legado) DO \
            UPDATE \
                SET cpf = EXCLUDED.cpf, nome = EXCLUDED.nome, email = EXCLUDED.email, cidade = EXCLUDED.cidade, dt_cadastro = EXCLUDED.dt_cadastro; \
            """

# LISTA DE QUARENTENA: vai armazenar os dicionários das linhas que derem erro
linhas_rejeitadas = []

# 4. LOOP DE INSERÇÃO NA TABELA PRINCIPAL
for index, linha in df_clientes.iterrows():
    try:
        # Tenta inserir no banco
        cursor.execute(query_sql, linha.to_dict())
        # Comita a cada linha para isolar os sucessos das falhas
        conexao.commit()

    except Exception as erro:
        # 1. DESTRAVA O BANCO: Desfaz a transação falha para permitir a próxima tentativa
        conexao.rollback()

        # 2. Mostra o motivo REAL pelo qual essa linha foi rejeitada
        print(f"❌ Falha no cliente {linha['id_legado']}: {erro}")

        # 3. PREPARA PARA A QUARENTENA:
        linha_falha = linha.to_dict()
        linha_falha['motivo_falha'] = str(erro).strip()  # Salva a mensagem de erro do Postgres
        linhas_rejeitadas.append(linha_falha)

# 5. PROCESSA A QUARENTENA (Se houver erros)
if linhas_rejeitadas:
    df_falhas = pd.DataFrame(linhas_rejeitadas)
    print(f"\n⚠️ Total de registros enviados para a quarentena: {len(df_falhas)}")

    query_falha_sql = """
                      INSERT INTO clientes_legado_com_falha
                          (id_legado, cpf, nome, email, cidade, dt_cadastro, motivo_falha)
                      VALUES (%(id_legado)s, %(cpf_limpo)s, %(nome)s, %(email)s, %(cidade)s, %(dt_cadastro)s, \
                              %(motivo_falha)s); \
                      """

    for _, linha_rejeitada in df_falhas.iterrows():
        try:
            cursor.execute(query_falha_sql, linha_rejeitada.to_dict())
            conexao.commit()
        except Exception as erro_critico:
            conexao.rollback()
            print(f"Erro CRÍTICO ao salvar o id {linha_rejeitada['id_legado']} na quarentena: {erro_critico}")

else:
    print("\n✅ Carga concluída com 100% de sucesso. Nenhum registro foi para a quarentena.")

# 6. FECHA AS CONEXÕES
cursor.close()
conexao.close()