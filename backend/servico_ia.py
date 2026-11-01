import json
import logging
import time
import re
from datetime import datetime
from openai import OpenAI
import base64
import os
import fitz  # PyMuPDF
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURAÇÃO GITHUB MODELS (GPT-4o) ---
# O token fica no arquivo .env (veja o .env.example), nunca no código.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise RuntimeError("Defina GITHUB_TOKEN no arquivo .env (veja o .env.example).")
client_ai = OpenAI(api_key=GITHUB_TOKEN, base_url="https://models.inference.ai.azure.com")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def extrair_art_do_documento(texto_pdf: str) -> str:
    """Extração rápida do código da ART via GPT-4o"""
    try:
        response = client_ai.chat.completions.create(
            messages=[
                {"role": "system", "content": "Você é um extrator de dados. Retorne APENAS o código da ART encontrado no texto. Exemplo: MA20250929762. Não converse."},
                {"role": "user", "content": f"Extraia a ART deste texto: {texto_pdf[:3000]}"}
            ],
            model="gpt-4o",
            temperature=0.0,
        )
        return response.choices[0].message.content.strip().replace(" ", "").replace("\n", "")
    except Exception as e:
        logging.error(f"Erro na extração de ART: {e}")
        return ""

def analisar_documento_com_catia(texto_pdf: str, dados_banco: dict) -> dict:
    """Auditoria Full Resolução 1137 com Detalhamento Extremo via GPT-4o"""
    
    prompt_especialista = f"""
    VOCÊ É A CAT.IA, AUDITORA SÊNIOR DO CREA-MA COM PODER DE DISCERNIMENTO E FOCO EM DETALHAMENTO EXTREMO.
    Sua missão é realizar uma auditoria COMPLETA e INTELIGENTE baseada no ANEXO IV da Resolução 1137/2023.

    DADOS OFICIAIS (SITAC):
    - Profissional: {dados_banco.get('nome_profissional')}
    - CNPJ/CPF Contratante: {dados_banco.get('cnpj_contratante')}
    - Prazo Limite ART: {dados_banco.get('data_fim')}
    - Escopo ART: {dados_banco.get('escopo')}

    ALGORITMO DE FLEXIBILIZAÇÃO E REGRAS DE OURO (NÃO IGNORE):
    1. PRAZO DE EXECUÇÃO: Identifique a data final do 'Período de Realização/Execução' (ex: 24/06/2025). Use APENAS esta data para comparar com o prazo da ART.
    2. DATA DE ASSINATURA/EXPEDIÇÃO: NUNCA use datas de 2026 que pertençam à assinatura digital ou expedição do atestado para o cálculo de prazo excedido. Use apenas a data da obra.
    3. FLEXIBILIDADE DE AUTÔNOMO: Se o profissional (Pessoa Física) prestou serviço direto para o cliente sem empresa intermediária, o campo '1.3 - Empresa Contratada' é IRRELEVANTE. Marque como 'Aderente' e explique: 'Contratação direta de profissional autônomo validada'.
    4. DETALHAMENTO EXTREMO: No campo 'extraido', coloque o dado lido no documento E uma breve observação técnica fundamentada se for Aprovado ou Divergente.

    STATUS PERMITIDOS: 'Aderente', 'Divergente', 'Pendente'.

    RETORNE OBRIGATORIAMENTE ESTE JSON EXATO E VÁLIDO:
    {{
        "data_conclusao_tecnica": "DD/MM/AAAA (Apenas a data fim da execução técnica)",
        "relatorio_detalhado": [
            {{"item": "1.1 - Local da Obra/Serviço", "extraido": ".", "status": "."}},
            {{"item": "1.1 - Período de Realização", "extraido": ".", "status": "."}},
            {{"item": "1.2 - Contratante (Razão/CNPJ/CPF)", "extraido": ".", "status": "."}},
            {{"item": "1.3 - Empresa Contratada (Razão/CNPJ)", "extraido": ".", "status": "."}},
            {{"item": "1.4 - Responsável Técnico", "extraido": ".", "status": "."}},
            {{"item": "1.5 - Descrição e Quantitativos", "extraido": ".", "status": "."}},
            {{"item": "1.6 - Identificação do Signatário", "extraido": ".", "status": "."}},
            {{"item": "Obs 3 - Papel Timbrado / Carimbo de CNPJ", "extraido": ".", "status": "."}},
            {{"item": "Obs 3 - Ausência de Rasuras e Adulterações", "extraido": ".", "status": "."}},
            {{"item": "Obs 3 - Local e Data de Expedição", "extraido": ".", "status": "."}}
        ],
        "analise_comparativa": {{"divergencias_encontradas": []}},
        "classificacao_final": "Aderente",
        "parecer_auditoria": "Laudo profissional justificando as isenções aplicadas e a conformidade técnica fundamentada na lei."
    }}
    """

    for tentativa in range(2):
        try:
            logging.info(f"🧠 CAT.IA acionando motor GPT-4o da GitHub (Tentativa {tentativa+1})...")
            response = client_ai.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Auditor Governamental Full Detail. Responda apenas com JSON estruturado."},
                    {"role": "user", "content": f"{prompt_especialista}\n\nDocumento: {texto_pdf}"}
                ],
                model="gpt-4o",
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            res = json.loads(response.choices[0].message.content)
            
            # Validação Matemática de Prazo (Python)
            try:
                data_limite_art = datetime.strptime(dados_banco.get('data_fim'), "%Y-%m-%d")
                match = re.search(r'(\d{2}/\d{2}/\d{4})', res.get("data_conclusao_tecnica", ""))
                if match:
                    data_final_obra = datetime.strptime(match.group(1), "%d/%m/%Y")
                    if data_final_obra > data_limite_art:
                        res["classificacao_final"] = "Indeferido"
                        res["analise_comparativa"]["divergencias_encontradas"].append(
                            f"🔴 PRAZO EXCEDIDO: A execução findou em {match.group(1)}, após o limite legal da ART ({data_limite_art.strftime('%d/%m/%Y')})."
                        )
            except Exception as e:
                logging.error(f"Erro no cálculo de data: {e}")

            if any(l['status'] in ['Divergente', 'Pendente'] for l in res.get('relatorio_detalhado', [])):
                res["classificacao_final"] = "Indeferido"
            
            return res
            
        except Exception as e:
            logging.warning(f"Falha na API: {e}")
            time.sleep(1.5)
            continue
            
    return {
        "classificacao_final": "Erro de API",
        "relatorio_detalhado": [
            {"item": "Erro do Sistema", "extraido": "Falha de conexão com a Inteligência Artificial", "status": "Divergente"}
        ],
        "analise_comparativa": {"divergencias_encontradas": ["A API da IA recusou a conexão. Verifique o seu token do GitHub."]},
        "parecer_auditoria": "ATENÇÃO: Não foi possível processar o documento."
    }

def analisar_fraude_completa(caminho_pdf):
    """
    Perícia Forense Avançada com Filtro de Assinatura Digital de Sistema.
    Diferencia colagem maliciosa de assinaturas digitais legítimas (ex: Adobe/Gov.br).
    """
    logging.info("🕵️ Iniciando Varredura Forense Híbrida...")

    # --- CAMADA 1: METADADOS E CRIPTOGRAFIA ---
    tem_criptografia = False
    try:
        with open(caminho_pdf, 'rb') as f:
            conteudo = f.read()
            tem_criptografia = b"/ByteRange" in conteudo and b"/Contents" in conteudo
    except Exception as e:
        logging.error(f"Erro na Camada 1: {e}")

    # --- CAMADA 2: ENGENHARIA REVERSA DE OBJETOS ---
    img_b64 = ""
    colagem_detectada = False
    assinatura_sistema_detectada = False
    documento_nato_digital = False

    try:
        doc = fitz.open(caminho_pdf)
        pagina = doc[-1]
        texto_pagina = pagina.get_text("text")

        if len(texto_pagina.strip()) > 100:
            documento_nato_digital = True

        # Busca por termos de assinaturas digitais legítimas no texto
        termos_seguranca = [
            "assinado de forma digital",
            "digitally signed",
            "dados:",
            "assinado digitalmente",
            "validar em"
        ]
        if any(termo in texto_pagina.lower() for termo in termos_seguranca):
            assinatura_sistema_detectada = True

        lista_imagens = pagina.get_images(full=True)
        if documento_nato_digital and len(lista_imagens) > 0:
            for img in lista_imagens:
                xref = img[0]
                base_image = doc.extract_image(xref)

                # Se houver uma imagem pequena E não houver texto de assinatura de sistema -> RISCO DE COLAGEM
                if base_image["width"] < pagina.rect.width * 0.9 and not assinatura_sistema_detectada:
                    colagem_detectada = True
                    break

        # Extração da imagem para exibição
        rect = pagina.rect
        clip = fitz.Rect(0, rect.height * 0.6, rect.width, rect.height)
        pix = pagina.get_pixmap(clip=clip, matrix=fitz.Matrix(2, 2))
        img_b64 = base64.b64encode(pix.tobytes("jpeg")).decode("utf-8")
        doc.close()
    except Exception as e:
        logging.error(f"Erro na extração: {e}")

    # --- PREPARAÇÃO DE VARIÁVEIS ---
    status_final_sugerido = "Autêntico"
    if colagem_detectada:
        status_final_sugerido = "Fraude"
    elif not tem_criptografia and documento_nato_digital and not assinatura_sistema_detectada:
        status_final_sugerido = "Suspeito"
    elif assinatura_sistema_detectada:
        status_final_sugerido = "Autêntico"

    # --- CAMADA 3: O PARECER DA IA ---
    prompt = f"""
    Atue como Perito de Metadados. Julgue o documento com base nestas evidências:
    1. Criptografia ICP-Brasil: {'Sim' if tem_criptografia else 'Não'}
    2. Documento Nato-Digital: {'Sim' if documento_nato_digital else 'Não'}
    3. Elemento de Imagem Colado: {'Sim' if colagem_detectada else 'Não'}
    4. Texto de Assinatura de Sistema (Ex: 'Assinado Digitalmente'): {'Detectado' if assinatura_sistema_detectada else 'Ausente'}

    [REGRAS]:
    - Se houver 'Texto de Assinatura de Sistema', o veredicto deve ser 'Autêntico' (Assinatura Digital de Sistema), mesmo sem ICP-Brasil.
    - Se for Digital, tiver Imagem Colada e NÃO tiver Texto de Assinatura de Sistema, é 'Fraude'.
    - Se for Papel Escaneado sem colagens, é 'Autêntico'.

    Retorne JSON:
    {{
        "status_forense": "{status_final_sugerido}",
        "grau_risco": "{'Baixo' if status_final_sugerido == 'Autêntico' else 'Alto'}",
        "dados_tecnicos": {{
            "criptografia_detectada": "{'Sim' if tem_criptografia else 'Não'}",
            "colagem_detectada": "{'Sim' if colagem_detectada else 'Não'}",
            "tipo_assinatura": "{'Digital de Sistema' if assinatura_sistema_detectada else 'Manual/Imagem'}"
        }},
        "parecer_pericial": "Sua explicação baseada no cruzamento de imagem e texto de segurança.",
        "indicios_fraude": []
    }}
    """

    try:
        response = client_ai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Você é um juiz que emite JSON estrito com base em evidências computacionais."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=400,
            temperature=0.0
        )

        texto_resposta = response.choices[0].message.content.strip()
        texto_resposta = re.sub(r"^```json\s*|\s*```$", "", texto_resposta, flags=re.DOTALL).strip()
        resultado = json.loads(texto_resposta)

        return {
            "status_forense": resultado.get("status_forense", status_final_sugerido),
            "grau_risco": resultado.get("grau_risco", "Baixo" if status_final_sugerido == "Autêntico" else "Alto"),
            "dados_tecnicos": resultado.get("dados_tecnicos", {
                "criptografia_detectada": "Sim" if tem_criptografia else "Não",
                "colagem_detectada": "Sim" if colagem_detectada else "Não",
                "tipo_assinatura": "Digital de Sistema" if assinatura_sistema_detectada else "Manual/Imagem"
            }),
            "parecer_pericial": resultado.get("parecer_pericial", ""),
            "indicios_fraude": resultado.get("indicios_fraude", []),
            "imagem_base64": img_b64,
            "provas_motor_python": {
                "criptografia_detectada": tem_criptografia,
                "documento_nato_digital": documento_nato_digital,
                "colagem_detectada": colagem_detectada,
                "assinatura_sistema_detectada": assinatura_sistema_detectada
            }
        }

    except Exception as e:
        logging.error(f"Erro na análise forense: {e}")
        return {
            "status_forense": "Erro",
            "grau_risco": "Indeterminado",
            "dados_tecnicos": {
                "criptografia_detectada": "Sim" if tem_criptografia else "Não",
                "colagem_detectada": "Sim" if colagem_detectada else "Não",
                "tipo_assinatura": "Digital de Sistema" if assinatura_sistema_detectada else "Manual/Imagem"
            },
            "parecer_pericial": f"Falha ao processar a análise forense: {e}",
            "indicios_fraude": ["Falha no processamento da resposta da IA"],
            "imagem_base64": img_b64,
            "provas_motor_python": {
                "criptografia_detectada": tem_criptografia,
                "documento_nato_digital": documento_nato_digital,
                "colagem_detectada": colagem_detectada,
                "assinatura_sistema_detectada": assinatura_sistema_detectada
            }
        }
