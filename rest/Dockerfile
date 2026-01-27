FROM python:3.12-slim

ARG USER_ID=1000
ARG GROUP_ID=1000

RUN pip install --upgrade pip

RUN groupadd -g ${GROUP_ID} domino && \
    useradd -m -u ${USER_ID} -g ${GROUP_ID} domino

USER domino

WORKDIR /rest

COPY . .

ENV PATH="/home/domino/.local/bin:$PATH"

RUN pip install --no-cache-dir --user -r requirements.txt

EXPOSE 8000

#CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--proxy-headers", "--log-level", "debug", "--port", "8000"]
CMD ["python", "main.py"]
