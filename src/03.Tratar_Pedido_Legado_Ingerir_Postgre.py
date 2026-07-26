import pandas as pd
import psycopg2
import numpy as np
from dotenv import load_dotenv

# 0. Carrega as informações do arquivo .env para a memória do Python
load_dotenv()

# 0.1. Busca os dados de conexão de forma segura
db_host = os.getenv("DB_HOST")
db_name = os.getenv("DB_NAME")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")

# 1. LEITURA
df_pedidos = pd.read_csv('/app/data/pedidos_legado.csv', sep=';', encoding='latin1')

# 2. SANEAMENTO E FILTRAGEM
# Conversão de datas (o que falhar vira NaT)
df_pedidos['dt_convertida'] = pd.to_datetime(df_pedidos['dt_pedido'], format='mixed', dayfirst=True, errors='coerce')

# Identifica erros (datas inválidas ou duplicidade de chave primária)
filtro_datas_invalidas = df_pedidos['dt_convertida'].isna()
filtro_duplicados = df_pedidos.duplicated(subset=['num_pedido'], keep='first')

# Separa limpos de sujos
df_limpo = df_pedidos[~filtro_datas_invalidas & ~filtro_duplicados].copy()
df_sujo = df_pedidos[filtro_datas_invalidas | filtro_duplicados].copy().reset_index(drop=True)

# Cria motivo de falha para os registros sujos
df_sujo['motivo_falha'] = np.where(filtro_datas_invalidas[filtro_datas_invalidas | filtro_duplicados], 'Data inválida', 'Pedido duplicado')

# Limpeza final dos dados limpos
df_limpo['cpf_limpo'] = df_limpo['cpf_cliente'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(11)
df_limpo['valor_limpo'] = df_limpo['valor_total'].astype(str).str.replace('.', '').str.replace(',', '.').astype(float)
df_limpo['status_limpo'] = df_limpo['status'].str.upper().str.strip().replace({'CANC': 'CANCELADO', 'PG': 'PAGO'})
df_limpo['canal_limpo'] = df_limpo['canal'].str.upper()

# 3. INSERÇÃO NO BANCO
conexao = psycopg2.connect(
    host=db_host,
    database=db_name,
    user=db_user,
    password=db_password
)
cursor = conexao.cursor()

# Inserção dos dados limpos
query_ins = """
    INSERT INTO pedidos_legado (num_pedido, cpf_cliente, status, valor_total, dt_pedido, canal)
    VALUES (%(num_pedido)s, %(cpf_limpo)s, %(status_limpo)s, %(valor_limpo)s, %(dt_convertida)s, %(canal_limpo)s);
"""

for _, linha in df_limpo.iterrows():
    try:
        cursor.execute(query_ins, linha.to_dict())
        conexao.commit()
    except Exception as e:
        conexao.rollback()
        print(f"Erro na inserção do pedido {linha['num_pedido']}: {e}")

# Inserção dos dados sujos na quarentena
query_falha = """
    INSERT INTO pedidos_legado_com_falha 
    (num_pedido, cpf_cliente, status, valor_total, dt_pedido, canal, motivo_falha)
    VALUES (%(num_pedido)s, %(cpf_cliente)s, %(status)s, %(valor_total)s, %(dt_pedido)s, %(canal)s, %(motivo_falha)s);
"""

for _, linha in df_sujo.iterrows():
    cursor.execute(query_falha, linha.to_dict())
    conexao.commit()

cursor.close()
conexao.close()
print("Pipeline de pedidos finalizado com sucesso.")