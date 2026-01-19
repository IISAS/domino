FROM python:3.12-slim
#FROM python:3.12-slim-bookworm
#FROM python:3.12.12

ARG USER_ID=1000
ARG GROUP_ID=1000

RUN apt update && \
    apt install sudo procps net-tools iputils-ping curl vim -y

RUN pip install --upgrade pip

RUN groupadd -g ${GROUP_ID} domino && \
    useradd --system -m -u ${USER_ID} -g ${GROUP_ID} domino && \
    usermod -a -G root domino && \
    adduser domino sudo

RUN echo '%sudo ALL=(ALL:ALL) NOPASSWD:ALL' >> /etc/sudoers ;

#RUN echo "domino:domino" | chpasswd

USER domino

WORKDIR /rest

COPY . .

RUN pip install --no-cache-dir --user -r requirements.txt

ENV PATH="/home/domino/.local/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--proxy-headers", "--reload", "--log-level", "debug", "--host", "0.0.0.0", "--port", "8000"]
