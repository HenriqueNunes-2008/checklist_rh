import os
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader

# --- CONSTANTES DE LAYOUT ---
HEADER_MARGIN_X = 30
HEADER_MARGIN_TOP = 20
LEFT_IMAGE_HEIGHT = 70
RIGHT_IMAGE_HEIGHT = 220
FOOTER_Y = 20
FOOTER_FONT = "Helvetica"
FOOTER_FONT_SIZE = 10
FOOTER_COLOR = HexColor("#8a8a8a")
DEFAULT_FOOTER_TEXT = "R. José Antônio Valadares, 285 - Vila Liviero, São Paulo - SP, 04185-020"

def _asset_path(filename: str) -> str:
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))
    return os.path.join(base, filename)

def _load_image(filename: str) -> ImageReader | None:
    path = _asset_path(filename)
    if not os.path.exists(path):
        return None
    try:
        return ImageReader(path)
    except Exception:
        return None

def draw_header_footer(c, width, height, footer_text=DEFAULT_FOOTER_TEXT):
    left_img = _load_image("LogoFlexcolor.png")
    right_img = _load_image("Kure.png")

    if left_img:
        iw, ih = left_img.getSize()
        scale = LEFT_IMAGE_HEIGHT / float(ih)
        w = float(iw) * scale
        c.saveState()
        if hasattr(c, "setFillAlpha"): c.setFillAlpha(0.5)  # 0.3 para transparência suave
        c.drawImage(left_img, HEADER_MARGIN_X, height - HEADER_MARGIN_TOP - LEFT_IMAGE_HEIGHT + 12, width=w, height=LEFT_IMAGE_HEIGHT, mask="auto")
        c.restoreState()

    if right_img:
        iw, ih = right_img.getSize()
        scale = RIGHT_IMAGE_HEIGHT / float(ih)
        w = float(iw) * scale
        c.saveState()
        if hasattr(c, "setFillAlpha"): c.setFillAlpha(0.5)  # Aplica a mesma transparência à direita
        c.drawImage(right_img, width - HEADER_MARGIN_X - w + 47, height - HEADER_MARGIN_TOP - RIGHT_IMAGE_HEIGHT + 97, width=w, height=RIGHT_IMAGE_HEIGHT, mask="auto")
        c.restoreState()

    c.setFont(FOOTER_FONT, FOOTER_FONT_SIZE)
    c.setFillColor(FOOTER_COLOR)
    text_w = c.stringWidth(footer_text, FOOTER_FONT, FOOTER_FONT_SIZE)
    c.drawString((width - text_w) / 2, FOOTER_Y, footer_text)
    c.setFillColor(HexColor("#000000"))

def criar_pdf_buffer(funcionario, checklists, tipo_processo=""):
    buffer = io.BytesIO()
    width, height = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"Checklist_{tipo_processo}_{funcionario['nome']}")

    draw_header_footer(c, width, height)

    y = height - 160
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(HexColor("#000000"))
    c.drawString(30, y, f"CHECKLIST DE CONTROLE - {tipo_processo.upper()}")
    
    y -= 30
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(HexColor("#475569"))
    c.drawString(30, y, "FUNCIONÁRIO: ")
    c.setFont("Helvetica", 10)
    c.drawString(110, y, funcionario['nome'].upper())
    
    c.setFont("Helvetica-Bold", 10)
    c.drawString(350, y, "CPF: ")
    c.setFont("Helvetica", 10)
    c.drawString(385, y, funcionario['cpf'])
    
    y -= 15
    c.setLineWidth(0.5)
    c.setStrokeColor(HexColor("#cbd5e1"))
    c.line(30, y, width - 30, y)

    # Cabeçalho da Tabela Atualizado
    y -= 35
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(HexColor("#000000"))
    c.drawString(35, y, "DESCRIÇÃO DO ITEM")
    c.drawString(350, y, "STATUS") # Coluna de status unificada
    c.drawString(450, y, "VALIDAÇÃO") # Ajuste de nome conforme solicitado
    
    y -= 8
    c.setLineWidth(1)
    c.line(30, y, width - 30, y)
    y -= 20

    c.setFont("Helvetica", 9)
    for item in checklists:
        descricao = item.get('checklist_modelos', {}).get('descricao', 'N/A')
        
        # Lógica de Validação: Se RH OU Administrativo validaram, está CONCLUÍDO
        foi_validado = item.get('validado_rh') or item.get('validado_executivo')
        
        c.setFillColor(HexColor("#334155"))
        c.drawString(35, y, descricao[:60] + "..." if len(descricao) > 60 else descricao)
        
        if foi_validado:
            c.setFillColor(HexColor("#16a34a")) # Verde
            status_texto = "CONCLUÍDO"
        else:
            c.setFillColor(HexColor("#ef4444")) # Vermelho
            status_texto = "PENDENTE"
            
        c.drawString(350, y, status_texto)
        
        # Colunas individuais caso queira manter o registro de QUEM validou (opcional)
        # Se preferir remover os checks individuais e deixar só o status geral, apague as linhas abaixo
        c.setFont("Helvetica", 8)
        if item.get('validado_rh'): c.drawString(465, y, "[RH]")
        if item.get('validado_executivo'): c.drawString(465, y, "[ADM]")
        c.setFont("Helvetica", 9)

        y -= 18
        if y < 80:
            c.showPage()
            draw_header_footer(c, width, height)
            y = height - 100
            c.setFont("Helvetica", 9)

    c.save()
    buffer.seek(0)
    return buffer