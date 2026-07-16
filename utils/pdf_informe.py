# Archivo: utils/pdf_informe.py
"""
Generación del PDF del informe ecocardiográfico.

Esta es la versión canónica (originada en pages/estudios.py), usada tanto
para el PDF que se genera al crear/previsualizar un estudio nuevo como para
el que se regenera desde el historial clínico de un paciente.
"""
import io
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


def generar_pdf_desde_historial(estudio, paciente, mediciones_estudio):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )

    # Estilos
    styles = getSampleStyleSheet()
    style_h1 = ParagraphStyle('Header1', fontName='Helvetica-Bold', fontSize=12, leading=14, spaceAfter=10)
    style_h2 = ParagraphStyle('Header2', fontName='Helvetica-Bold', fontSize=10, leading=12, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#1A365D"))
    style_body = ParagraphStyle('Body', fontName='Helvetica', fontSize=9, leading=12)
    style_body_bold = ParagraphStyle('BodyBold', fontName='Helvetica-Bold', fontSize=9, leading=12)
    
    story = []

    # Título
    story.append(Paragraph("<b>Ecocardiograma con EcoCardioNet</b>", style_h1))
    story.append(Spacer(1, 6))

    # Fecha y hora del estudio
    hora_estudio = (estudio.fecha_creacion.strftime('%H:%M') if hasattr(estudio, 'fecha_creacion') and estudio.fecha_creacion else "")
    fecha_str = estudio.fecha_estudio.strftime('%d/%m/%Y')
    
    if hora_estudio:
        texto_fecha = f"<b>Fecha:</b> {fecha_str} &nbsp;&nbsp;&nbsp; <b>Hora:</b> {hora_estudio}"
    else:
        texto_fecha = f"<b>Fecha:</b> {fecha_str}"
        
    story.append(Paragraph(texto_fecha, style_body))
    story.append(Spacer(1, 6))  

    # Header del Paciente
    nombre_p = f"{paciente.nombres} {paciente.apellido_paterno} {paciente.apellido_materno or ''}".strip().upper()
    edad_p = ((datetime.today().date() - paciente.fecha_nacimiento).days // 365 if paciente.fecha_nacimiento else "—")
    prevision_p = paciente.prevision if hasattr(paciente, 'prevision') and paciente.prevision else "—"
    
    # CORRECCIÓN: Se extrae desde 'estudio', no desde 'paciente'
    ficha_clinica_p = estudio.ficha_clinica if hasattr(estudio, 'ficha_clinica') and estudio.ficha_clinica else "—"
    
    asc_val = f"{estudio.asc_valor} m2" if hasattr(estudio, 'asc_valor') and estudio.asc_valor else "—"
    imc_val = f"{estudio.imc} kg/m2" if hasattr(estudio, 'imc') and estudio.imc else "—"
    ritmo_val = estudio.ritmo if hasattr(estudio, 'ritmo') and estudio.ritmo else "—"
    fcia_val = f"{estudio.fcia} Lpm" if hasattr(estudio, 'fcia') and estudio.fcia else "—"
    pas_val = estudio.pas if hasattr(estudio, 'pas') and estudio.pas else "___"
    pad_val = estudio.pad if hasattr(estudio, 'pad') and estudio.pad else "___"

    # Matriz reorganizada para balancear perfectamente ambos lados
    data_header = [
        [Paragraph(f"<b>Paciente:</b> {nombre_p}", style_body), Paragraph(f"<b>R.U.T:</b> {paciente.rut}", style_body)],
        [Paragraph(f"<b>ASC:</b> {asc_val}", style_body), Paragraph(f"<b>IMC:</b> {imc_val} &nbsp;&nbsp; <b>Ritmo:</b> {ritmo_val} &nbsp;&nbsp; <b>FC:</b> {fcia_val}", style_body)],
        [Paragraph(f"<b>Edad:</b> {edad_p} Años &nbsp;&nbsp;&nbsp;", style_body), Paragraph(f"<b>Previsión:</b> {prevision_p}", style_body)],
        [Paragraph(f"<b>Dg.:</b> {estudio.diagnostico or '—'}", style_body), Paragraph(f"<b>PA:</b> {pas_val} / {pad_val} mm Hg", style_body)],
        [Paragraph(f"<b>Procedencia:</b> {estudio.procedencia or '—'}", style_body), Paragraph(f"<b>Ficha Clínica:</b> {ficha_clinica_p}", style_body)]
    ]  

    t_header = Table(data_header, colWidths=[3.5*inch, 3.5*inch])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(t_header)
    story.append(Spacer(1, 15))
    story.append(Paragraph("<b>Mediciones y Descripción</b>", style_h1))
    story.append(Spacer(1, 5))

    # Agrupar mediciones por categoría
    categorias_pdf = {
        "AORTA Y VÁLVULA AÓRTICA": [],
        "AURÍCULAS Y SEPTUM IA": [],
        "VENTRÍCULO IZQUIERDO": [],
        "VENTRÍCULO DERECHO": [],
        "VÁLVULA MITRAL": [],
        "VÁLVULA TRICÚSPIDE": [],
        "VÁLVULA PULMONAR": [],
        "PERICARDIO": [],
        "OTROS": []
    }

    # Mapeo de categorías
    for m, v in mediciones_estudio:
        cat_orig = (v.categoria or "").upper()
        valor_str = str(m.valor_num) if m.valor_num is not None else (m.valor_texto or "")
        unidad = v.unidad if v and v.unidad else ""
        nombre = v.nombre if v and v.nombre else m.codigo_variable

        dest_cat = "OTROS"
        if "AORTA" in cat_orig and "VÁLVULA" not in cat_orig: dest_cat = "AORTA Y VÁLVULA AÓRTICA"
        elif "AURICULA" in cat_orig or "AURÍCULA" in cat_orig: dest_cat = "AURÍCULAS Y SEPTUM IA"
        elif "IZQUIERDO" in cat_orig: dest_cat = "VENTRÍCULO IZQUIERDO"
        elif "DERECHO" in cat_orig: dest_cat = "VENTRÍCULO DERECHO"
        elif "MITRAL" in cat_orig: dest_cat = "VÁLVULA MITRAL"
        elif "TRICUSP" in cat_orig or "TRICÚSP" in cat_orig: dest_cat = "VÁLVULA TRICÚSPIDE"
        elif "PULMONAR" in cat_orig: dest_cat = "VÁLVULA PULMONAR"
        elif "PERICARDIO" in cat_orig: dest_cat = "PERICARDIO"
        elif "AORTIC" in cat_orig or "AÓRTIC" in cat_orig: dest_cat = "AORTA Y VÁLVULA AÓRTICA"
        
        categorias_pdf[dest_cat].append((nombre, valor_str, unidad))

    # Parsear los "Hallazgos" 
    obs_completas = estudio.observaciones or ""
    hallazgos_str = ""
    conclusiones_str = ""
    
    if "[HALLAZGOS]:" in obs_completas:
        partes = obs_completas.split("[HALLAZGOS]:")
        resto = partes[1]
        if "[CONCLUSIONES]:" in resto:
            hallazgos_str = resto.split("[CONCLUSIONES]:")[0].strip()
            conclusiones_str = resto.split("[CONCLUSIONES]:")[1].strip()
        else:
            hallazgos_str = resto.strip()
    else:
        hallazgos_str = obs_completas

    dict_descripciones = {k: [] for k in categorias_pdf.keys()}
    current_key = "OTROS"

    mapeo_desc = {
        "ventrículo izquierdo": "VENTRÍCULO IZQUIERDO",
        "ventrículo derecho": "VENTRÍCULO DERECHO",
        "aurículas y septum": "AURÍCULAS Y SEPTUM IA",
        "aorta y v. aorta": "AORTA Y VÁLVULA AÓRTICA",
        "válvula mitral": "VÁLVULA MITRAL",
        "válvula tricúspide": "VÁLVULA TRICÚSPIDE",
        "válvula pulmonar": "VÁLVULA PULMONAR",
        "pericardio": "PERICARDIO"
    }

    for linea in hallazgos_str.split('\n'):
        if not linea.strip(): continue
        encontrado = False
        for prefijo, cat_pdf in mapeo_desc.items():
            if linea.lower().startswith(prefijo.lower() + ":"):
                current_key = cat_pdf
                dict_descripciones[current_key].append(linea[len(prefijo)+1:].strip())
                encontrado = True
                break
        
        if not encontrado:
            dict_descripciones[current_key].append(linea.strip())

    for cat, variables in categorias_pdf.items():
        textos_cat = dict_descripciones.get(cat, [])
        if not variables and not textos_cat:
            continue

        story.append(Paragraph(cat, style_h2))

        if variables:
            data_var = []
            for nombre, valor, unidad in variables:
                data_var.append([Paragraph(nombre, style_body), Paragraph(f"<b>{valor}</b>", style_body), Paragraph(unidad, style_body)])
            
            t_var = Table(data_var, colWidths=[2.5*inch, 1*inch, 1.5*inch])
            t_var.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 1),
                ('TOPPADDING', (0,0), (-1,-1), 1),
            ]))
            story.append(t_var)
            story.append(Spacer(1, 4))

        if textos_cat:
            texto_unido = " ".join(textos_cat)
            story.append(Paragraph(texto_unido, style_body))
            story.append(Spacer(1, 6))

    # CONCLUSIONES
    story.append(Spacer(1, 15))
    story.append(Paragraph("<b>Conclusiones:</b>", style_h1))
    
    if conclusiones_str:
        for linea in conclusiones_str.split('\n'):
            if linea.strip():
                story.append(Paragraph(linea.strip(), style_body))
    else:
        story.append(Paragraph("Sin conclusiones registradas.", style_body))

    # FIRMA MEDICO
    story.append(Spacer(1, 50))
    medico_firma = estudio.medico if estudio.medico else "Dr. Eric Fuentes Latorre"
    story.append(Paragraph(f"<b>{medico_firma}</b>", style_body))
    story.append(Paragraph("Cardiólogo Ecocardiografista", style_body))
    story.append(Paragraph("Imagen Cardiaca Avanzada", style_body))

    doc.build(story)
    buffer.seek(0)
    return buffer