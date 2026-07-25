# 1. Pega um "computador" virgem só com Python instalado
FROM python:3.11-slim

# 2. Cria uma pasta chamada /app lá dentro e entra nela
WORKDIR /app

# 3. Copia o seu requirements.txt para dentro dele e instala tudo
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copia a sua pasta src (com seus códigos) para lá
COPY src/ ./src/