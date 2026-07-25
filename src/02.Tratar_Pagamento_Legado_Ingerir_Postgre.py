import pandas as pd
import psycopg2
import numpy as np

# 1. LÊ O ARQUIVO CSV
file_path = '/app/data/pagamentos_legado.csv'
df_pagamentos = pd.read_csv(file_path, sep=';', encoding='latin1')

# 2. TRATA OS DADOS (PIPELINE DE SANEAMENTO E VALIDAÇÃO)
# Padronização de Método de Pagamento
mapping_metodo = {
    'cartão': 'CARTAO', 'cartao': 'CARTAO',
    'pix': 'PIX', 'PIX': 'PIX',
    'boleto': 'BOLETO', 'Boleto': 'BOLETO'
}
df_pagamentos['metodo'] = df_pagamentos['metodo'].replace(mapping_metodo)

# --- INÍCIO DAS VALIDAÇÕES ---
# Criamos uma coluna vazia para acumular os motivos de falha
df_pagamentos['motivo_falha'] = ""

# Regra 1: Valores negativos
df_pagamentos.loc[df_pagamentos['valor_pago'] < 0, 'motivo_falha'] += "Valor negativo; "

# Regra 4: Data inválida
# O parâmetro 'errors='coerce'' é fundamental aqui. Ele converte datas impossíveis (como 30/02/2026) em NaT (Not a Time) em vez de quebrar o script.
datas_convertidas = pd.to_datetime(df_pagamentos['dt_pagto'], format='mixed', dayfirst=True, errors='coerce')
df_pagamentos.loc[datas_convertidas.isna(), 'motivo_falha'] += "Data inválida; "

# Criamos a data no padrão ISO apenas para os registros válidos
df_pagamentos['dt_pagto_iso'] = datas_convertidas.dt.strftime('%Y-%m-%d')
# Substitui NaT por None para evitar erros do psycopg2 caso a linha escape
df_pagamentos['dt_pagto_iso'] = df_pagamentos['dt_pagto_iso'].replace({np.nan: None})

# Regra 2: Pagamento duplicado (id_pagto) dentro do arquivo
# keep=False marca TODAS as ocorrências da duplicidade como erro
dup_id = df_pagamentos.duplicated(subset=['id_pagto'], keep=False)
df_pagamentos.loc[dup_id, 'motivo_falha'] += "ID de pagamento duplicado no arquivo; "

# Regra 3: Pagamento duplicado por pedido (num_pedido)
#dup_pedido = df_pagamentos.duplicated(subset=['num_pedido'], keep=False)
#df_pagamentos.loc[dup_pedido, 'motivo_falha'] += "Mais de um pagamento para o mesmo pedido; "

# Limpa a formatação (tira ponto e vírgula e espaços sobrando no final)
df_pagamentos['motivo_falha'] = df_pagamentos['motivo_falha'].str.strip('; ')
# --- FIM DAS VALIDAÇÕES ---


# 3. CONEXÃO E INSERÇÃO
conexao = psycopg2.connect(host="host.docker.internal", database="legado", user="postgres", password="Dsl@0194")
cursor = conexao.cursor()

query_sql = """
            INSERT INTO pagamentos_legado (id_pagto, num_pedido, valor_pago, metodo, dt_pagto)
            VALUES (%(id_pagto)s, %(num_pedido)s, %(valor_pago)s, %(metodo)s, %(dt_pagto_iso)s::DATE);
            """

linhas_rejeitadas = []

print("Iniciando carga de pagamentos...")

for index, linha in df_pagamentos.iterrows():
    linha_dict = linha.to_dict()

    # Se a linha já falhou na validação do Pandas, mandamos direto pra quarentena
    if linha_dict['motivo_falha'] != "":
        print(f"❌ Falha prévia no pagamento {linha['id_pagto']}: {linha_dict['motivo_falha']}")
        linhas_rejeitadas.append(linha_dict)
        continue  # Pula a tentativa de inserção na tabela principal

    try:
        cursor.execute(query_sql, linha_dict)
        conexao.commit()
    except Exception as erro:
        conexao.rollback()

        # Fallback: Captura erros que só o Banco de Dados pegou (ex: ID que já existia lá antes de rodar o CSV)
        erro_msg = str(erro).strip()
        if "chk_valor_positivo" in erro_msg:
            motivo = "Valor do pagamento deve ser positivo (BD)."
        elif "unique_violation" in erro_msg:
            motivo = "ID de pagamento duplicado (BD)."
        else:
            motivo = erro_msg[:250]  # Pega o erro genérico limitado a 250 caracteres

        print(f"❌ Falha no banco para o pagamento {linha['id_pagto']}: {motivo}")
        linha_dict['motivo_falha'] = motivo
        linhas_rejeitadas.append(linha_dict)

# 4. SALVA FALHAS NA QUARENTENA
if linhas_rejeitadas:
    df_falhas = pd.DataFrame(linhas_rejeitadas)

    # Nota importante: Note que aqui passamos %(dt_pagto)s e não %(dt_pagto_iso)s.
    # Isso garante que a string original (ex: '30/02/2026') seja salva na quarentena para auditoria.
    query_falha_sql = """
                      INSERT INTO pagamentos_legado_com_falha
                          (id_pagto, num_pedido, valor_pago, metodo, dt_pagto, motivo_falha)
                      VALUES (%(id_pagto)s, %(num_pedido)s, %(valor_pago)s, %(metodo)s, %(dt_pagto)s, %(motivo_falha)s);
                      """

    print(f"\nSalvando {len(df_falhas)} registros com erro na quarentena...")
    for _, linha_rejeitada in df_falhas.iterrows():
        try:
            cursor.execute(query_falha_sql, linha_rejeitada.to_dict())
            conexao.commit()
        except Exception as erro_critico:
            conexao.rollback()
            print(f"Erro CRÍTICO ao salvar na quarentena o ID {linha_rejeitada.get('id_pagto')}: {erro_critico}")

print("\nProcesso finalizado.")
cursor.close()
conexao.close()