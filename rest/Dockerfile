FROM python:3.12-slim

ARG USER_ID=1000
ARG GROUP_ID=1000

RUN groupadd -g ${GROUP_ID} domino && \
    useradd -m -u ${USER_ID} -g ${GROUP_ID} domino && \

WORKDIR /rest

USER domino

COPY . .

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
