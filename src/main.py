import subprocess
import sys

print("Iniciando o Pipeline de Ingestão de Dados...\n")

# Lista com o caminho dos seus scripts na ordem exata de execução
# Atenção: Se você salvou com outros nomes, atualize a lista abaixo
scripts = [
    "src/01.Tratar_Cliente_Legado_Ingerir_Postgre.py",
    "src/02.Tratar_Pagamento_Legado_Ingerir_Postgre.py",
    "src/03.Tratar_Pedido_Legado_Ingerir_Postgre.py"
]

for script in scripts:
    print(f"--- Executando: {script} ---")

    # O subprocess.run roda o arquivo e espera ele terminar
    resultado = subprocess.run([sys.executable, script])

    # Verifica se o script rodou sem falhas críticas (returncode 0 = Sucesso)
    if resultado.returncode != 0:
        print(f"\n❌ Erro crítico ao executar {script}.")
        print("Interrompendo o pipeline para evitar dados inconsistentes.")
        sys.exit(1)

    print(f"✅ {script} concluído com sucesso.\n")

print("🎉 Pipeline completo finalizado 100%!")