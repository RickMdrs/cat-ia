from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fpdf import FPDF
import shutil, os, sqlite3, fitz

from servico_ia import extrair_art_do_documento, analisar_documento_com_catia, analisar_fraude_completa

app = FastAPI(title="CAT.IA - Auditoria e Perícia Forense")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def extrair_texto_pdf(caminho):
    texto = ""
    with fitz.open(caminho) as doc:
        for p in doc: texto += p.get_text()
    return texto

def init_db():
    conn = sqlite3.connect('auditoria_catia.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS analises (id INTEGER PRIMARY KEY AUTOINCREMENT, processo TEXT, art TEXT, profissional TEXT, status TEXT, data_hora DATETIME DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS arts_oficiais (numero_processo TEXT, numero_art TEXT PRIMARY KEY, nome_profissional TEXT, cnpj_contratante TEXT, escopo TEXT, data_inicio TEXT, data_fim TEXT, valor TEXT)')
    cursor.execute("DELETE FROM arts_oficiais")
    # Registros para os testes
    # Registros fictícios de demonstração (simulam a base oficial do SITAC)
    cursor.execute("INSERT INTO arts_oficiais VALUES ('2026/001', 'MA20250000001', 'JOÃO DA SILVA (EXEMPLO)', '00.000.000/0001-00', 'PROJETO DE 50 PONTOS DE ILUMINAÇÃO PÚBLICA', '2025-05-12', '2025-06-24', '5000.00')")
    cursor.execute("INSERT INTO arts_oficiais VALUES ('2026/002', 'MA20250000002', 'MARIA SOUZA (EXEMPLO)', '11.111.111/0001-11', 'CONSTRUÇÃO DE UNIDADE BÁSICA DE SAÚDE', '2025-02-21', '2025-10-30', '818582.00')")
    conn.commit()
    conn.close()

init_db()

@app.get("/api/v1/historico")
async def buscar_historico():
    conn = sqlite3.connect('auditoria_catia.db')
    cursor = conn.cursor()
    cursor.execute('SELECT processo, art, profissional, status, data_hora FROM analises ORDER BY data_hora DESC LIMIT 10')
    linhas = cursor.fetchall()
    conn.close()
    return [{"processo": l[0], "art": l[1], "profissional": l[2], "status": l[3], "data": l[4]} for l in linhas]

@app.post("/api/v1/analisar-documento-autonomo")
async def processar_documento_autonomo(arquivo: UploadFile = File(...)):
    os.makedirs("temp_docs", exist_ok=True)
    caminho = f"temp_docs/{arquivo.filename}"
    with open(caminho, "wb") as buffer: shutil.copyfileobj(arquivo.file, buffer)
    
    try:
        # FASE 1: Extração e Identificação
        # FASE 1: Extração e Identificação
        texto = extrair_texto_pdf(caminho)
        art = extrair_art_do_documento(texto)
        
        conn = sqlite3.connect('auditoria_catia.db')
        cursor = conn.cursor()
        
        # Tratamento seguro caso a ART venha nula
        art_busca = art if art else ""
        cursor.execute("SELECT * FROM arts_oficiais WHERE numero_art LIKE ?", (f"%{art_busca[-10:]}%",))
        linha = cursor.fetchone()
        
        # LIMPEZA: Remove pedidos de desculpas da IA
        art_limpa = art if art else "Não Localizada no Documento"
        if len(art_limpa) > 25 or "não" in art_limpa.lower() or "desculpe" in art_limpa.lower():
            art_limpa = "Não Localizada no Documento"

        if linha:
            art_valida = True
            dados = {"numero_processo": linha[0], "numero_art": linha[1], "nome_profissional": linha[2], "cnpj_contratante": linha[3], "escopo": linha[4], "data_inicio": linha[5], "data_fim": linha[6]}
        else:
            art_valida = False
            # Cria um perfil vazio para obrigar a IA a ler o documento e montar a tabela
            dados = {"numero_processo": "Sem Registro", "numero_art": art_limpa, "nome_profissional": "DESCONHECIDO (NÃO CONSTA NO SITAC)", "cnpj_contratante": "-", "escopo": "-", "data_inicio": "2000-01-01", "data_fim": "2099-12-31"}
        
        # FASE 2: Auditoria de Conformidade (Anexo IV)
        # Chama a IA para ler TUDO, mesmo se a ART for falsa
        resultado = analisar_documento_com_catia(texto, dados)
        
        # REGRA DE NEGÓCIO: Se a ART não existia, FORÇA a reprovação mantendo a tabela
        # 6. REGRA DE NEGÓCIO: Se a ART não existia, FORÇAMOS a reprovação total da tabela
        if not art_valida:
            resultado["classificacao_final"] = "Indeferido"
            resultado["parecer_auditoria"] = "O documento foi lido com sucesso, porém os dados NÃO possuem validade legal pois a ART informada é inexistente na base oficial (SITAC)."
            
            # --- O PULO DO GATO: Reprova cada linha individualmente ---
            if "relatorio_detalhado" in resultado:
                for linha_tabela in resultado["relatorio_detalhado"]:
                    # Mantemos o dado que a IA leu, mas invalidamos o status
                    linha_tabela["status"] = "Divergente"
                    original = linha_tabela.get("extraido", "")
                    linha_tabela["extraido"] = f"{original} ❌ (NÃO VALIDADO PELO SITAC)"
            
            mensagem_alerta = f"🚫 FRAUDE OU ERRO GRAVE: A ART '{art_limpa}' não possui registro oficial. Nenhuma informação deste atestado pode ser considerada aderente."
            if "analise_comparativa" not in resultado:
                resultado["analise_comparativa"] = {"divergencias_encontradas": []}
            if mensagem_alerta not in resultado["analise_comparativa"]["divergencias_encontradas"]:
                resultado["analise_comparativa"]["divergencias_encontradas"].insert(0, mensagem_alerta)
        
        # FASE 4: Salva no Banco de Dados
        cursor.execute('INSERT INTO analises (processo, art, profissional, status) VALUES (?, ?, ?, ?)', (dados['numero_processo'], dados['numero_art'], dados['nome_profissional'], resultado['classificacao_final']))
        conn.commit()
        conn.close()
        
        return {"status": "sucesso", "art_encontrada_pela_ia": art_limpa, "dados_oficiais_banco": dados, "analise": resultado}
        
    finally:
        if os.path.exists(caminho): os.remove(caminho)

@app.post("/api/v1/gerar-relatorio")
async def gerar_relatorio(dados: dict):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "LAUDO DE AUDITORIA E PERÍCIA - CAT.IA", ln=True, align='C')
    caminho_pdf = "temp_docs/laudo_auditoria.pdf"
    pdf.output(caminho_pdf)
    return FileResponse(caminho_pdf, filename="Laudo_CATIA.pdf")

@app.post("/api/v1/pericia-visual-assinatura")
async def pericia_visual_assinatura(arquivo: UploadFile = File(...)):
    """
    Rota exclusiva para o Botão 'Scanner Forense'. 
    Devolve o laudo detalhado e a IMAGEM da assinatura para renderizar na tela.
    """
    os.makedirs("temp_docs", exist_ok=True)
    caminho = f"temp_docs/forense_{arquivo.filename}"
    with open(caminho, "wb") as buffer: 
        shutil.copyfileobj(arquivo.file, buffer)
    
    try:
        # Chama a função que você já tem no servico_ia.py
        laudo_forense = analisar_fraude_completa(caminho)
        return {"status": "sucesso", "pericia": laudo_forense}
    finally:
        if os.path.exists(caminho): os.remove(caminho)