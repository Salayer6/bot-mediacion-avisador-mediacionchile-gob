FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar solo el código fuente — las credenciales se inyectan en runtime
# mediante variables de entorno o Docker secrets, NUNCA se bakean en la imagen.
COPY main.py db_handler.py discord_notifier.py scraper.py ./

# Crear usuario no privilegiado: el proceso NO debe correr como root
RUN addgroup --system botgroup && adduser --system --ingroup botgroup botuser
USER botuser

CMD ["python", "main.py"]