# CAT.IA

**Auditoria automatizada de atestados técnicos com Inteligência Artificial.**
Projeto desenvolvido em equipe no **Hackathon CREA Maranhão 2025**, premiado com **menção honrosa**.

## O problema

Para emitir uma Certidão de Acervo Técnico (CAT), o CREA precisa conferir se o atestado apresentado pelo
profissional bate com a ART registrada e se cumpre todos os requisitos da Resolução 1137/2023. Essa conferência é
manual, demorada e sujeita a erro, e documentos adulterados podem passar despercebidos.

## A solução

A CAT.IA lê o atestado em PDF e faz a auditoria sozinha, em segundos:

1. **Identifica a ART** citada no documento, usando IA para extrair o número
2. **Cruza com a base oficial** (simulando o SITAC) para confirmar se a ART existe e a quem pertence
3. **Audita item por item** os requisitos do Anexo IV da Resolução 1137/2023: local, período, contratante,
   responsável técnico, quantitativos, signatário, carimbo, rasuras e data de expedição
4. **Confere o prazo** com cálculo de datas em Python, sem depender da IA
5. **Emite o parecer** (Aderente ou Indeferido), com a lista de divergências
6. **Perícia da assinatura:** um scanner forense analisa a estrutura do PDF para diferenciar assinatura digital
   legítima de imagem colada, e mostra o trecho da assinatura na tela

Se a ART não existe na base oficial, o documento é lido mesmo assim, mas todos os itens são reprovados
automaticamente, porque nenhum dado dele tem validade legal.

## Destaques técnicos

- **IA com regras de negócio:** o GPT-4o lê e interpreta o documento, mas as decisões críticas
  (prazo e existência da ART) são validadas em código, e não confiadas ao modelo
- **Respostas estruturadas:** a IA devolve JSON em um formato fixo, que o sistema valida antes de usar
- **Perícia em camadas:** metadados de criptografia, análise dos objetos do PDF e parecer da IA
- **Histórico das análises** salvo em banco local (SQLite)

**Stack:** Python · FastAPI · OpenAI SDK (GPT-4o via GitHub Models) · PyMuPDF · SQLite · HTML/CSS/JavaScript

## Como rodar

Requisitos: **Python 3.11+** e um token do GitHub com acesso ao GitHub Models.

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # cole o seu token em GITHUB_TOKEN
uvicorn main:app --reload   # API em http://127.0.0.1:8000
```

Depois, abra o `frontend/index.html` no navegador e envie um atestado em PDF.

> A base "oficial" de ARTs é simulada com **dados fictícios** de demonstração, criados ao iniciar o backend.

## Estrutura

```
backend/main.py         API (FastAPI): análise, perícia, histórico e laudo
backend/servico_ia.py   extração da ART, auditoria do Anexo IV e perícia forense
frontend/index.html     interface de envio e relatório da auditoria
```
