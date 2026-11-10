"""
Extracción asistida de datos desde informes de ecocardiograma en PDF
(texto, no imágenes escaneadas). Funciones puras: no usan Streamlit,
por lo que se pueden probar por separado (tests/test_importar_pdf.py).
"""
import re
import unicodedata

import pdfplumber


def _normalizar(txt):
    """Minúsculas, sin tildes, espacios colapsados. Facilita el matching por texto."""
    if not txt:
        return ""
    txt = unicodedata.normalize('NFKD', txt)
    txt = ''.join(c for c in txt if not unicodedata.combining(c))
    txt = txt.lower()
    txt = re.sub(r'\s+', ' ', txt)
    return txt.strip()


def extraer_texto_pdf(archivo_subido):
    """Extrae el texto plano de un PDF (informe basado en texto, no imagen escaneada)."""
    texto_total = ""
    with pdfplumber.open(archivo_subido) as pdf:
        for pagina in pdf.pages:
            texto_pagina = pagina.extract_text() or ""
            texto_total += texto_pagina + "\n"
    return texto_total


_NUM = r'(-?\d+[.,]?\d*)'
_INICIO = r'(?<![a-z0-9])'   # la etiqueta no puede ser el final de otra palabra
_FIN = r'(?![a-z])'          # ni el comienzo de otra más larga

# Alias de etiquetas conocidas en informes ya vistos, mapeadas al código de Variable.
# IMPORTANTE: cada equipo/clínica formatea distinto -> esta lista es de "mejor esfuerzo"
# y conviene seguir ampliándola a medida que aparezcan nuevos formatos de informe.
ALIASES_MEDICIONES = {
    "FEVI": [
        "fe(teich)", "fe (teich)", "fe teich",
        "fe estimada por simpson del", "fe estimada por 2d del",
        "fraccion de eyeccion", "frac. eyeccion", "frac eyeccion",
    ],
    "TAPSE": ["tapse"],
    "ONDA_S_PRIMA": ["tv s'", "onda s'", "s' promedio"],
    "GROSOR_PARIETAL_RELATIVO": ["gpr", "grosor parietal relativo"],
    "MASA_VI_INDEXADA": ["masa vi/asc", "masa vi indexada"],
    "PSAP": ["presion sist. ap", "presion sistolica de arteria pulmonar", "psap"],
    "VELOCIDAD_PICO_AORTICA": ["vmax va", "v. max ao", "vel. maxima ao"],
    "GRADIENTE_MEDIO_AORTICO": ["va gpmax", "gradiente medio ao", "gdte medio ao"],
    "TIEMPO_ACELERACION_PULMONAR": ["tap"],
    "AREA_MITRAL": ["area valvular mitral"],
    "VENA_CONTRACTA_MITRAL": ["vena contracta mitral"],
    "EROA_MITRAL": ["eroa mitral"],
    "VOLUMEN_REGURGITANTE_MITRAL": ["volumen regurgitante mitral"],
}


def _buscar_valor(texto_normalizado, etiquetas):
    """Busca la primera etiqueta que matchee y devuelve el número más cercano a la derecha."""
    for etiqueta in etiquetas:
        et_norm = _normalizar(etiqueta)
        # La etiqueta debe ser una palabra completa: "tap" no debe leer "tapse".
        patron = _INICIO + re.escape(et_norm) + _FIN + r'[^0-9\-]{0,15}' + _NUM
        m = re.search(patron, texto_normalizado)
        if m:
            return m.group(1).replace(",", ".")
    return None


def _buscar_valor_categorico(texto_normalizado, etiqueta, opciones):
    """Busca la etiqueta y verifica si alguna de las opciones conocidas aparece cerca."""
    et_norm = _normalizar(etiqueta)
    idx = texto_normalizado.find(et_norm)
    if idx == -1:
        return None
    ventana = texto_normalizado[idx: idx + len(et_norm) + 40]
    for opcion in opciones:
        if _normalizar(opcion) in ventana:
            return opcion
    return None


def extraer_mediciones(texto, variables_por_codigo):
    """
    Intenta extraer valores del texto de un informe y mapearlos a los códigos
    de la tabla Variable, respetando el tipo de cada variable (numero, categoria,
    texto). Devuelve {codigo: valor_str}.
    No pretende ser exhaustivo: el usuario revisa/corrige antes de guardar.
    """
    texto_norm = _normalizar(texto)
    resultados = {}

    # 1. Alias conocidos (numéricas, curadas a mano) — más confiables
    for codigo, etiquetas in ALIASES_MEDICIONES.items():
        var = variables_por_codigo.get(codigo)
        if not var or var.tipo != "numero":
            continue
        valor = _buscar_valor(texto_norm, etiquetas)
        if valor:
            resultados[codigo] = valor

    # 2. Fallback genérico por nombre de Variable, respetando el tipo
    for codigo, var in variables_por_codigo.items():
        if codigo in resultados:
            continue
        nombre_norm = _normalizar(var.nombre or "")
        if not nombre_norm or len(nombre_norm) < 3:
            continue

        if var.tipo == "numero":
            patron = _INICIO + re.escape(nombre_norm) + _FIN + r'[^0-9\-]{0,15}' + _NUM
            m = re.search(patron, texto_norm)
            if m:
                resultados[codigo] = m.group(1).replace(",", ".")

        elif var.tipo == "categoria":
            opciones = [
                o.strip() for o in (getattr(var, "opciones", "") or "").split(";")
                if o.strip()
            ]
            if opciones:
                valor = _buscar_valor_categorico(texto_norm, nombre_norm, opciones)
                if valor:
                    resultados[codigo] = valor

        # "texto" se deja fuera de la extracción automática: el riesgo de falsos
        # positivos es alto y no aporta valor real revisarlo/corregirlo a ciegas.

    return resultados

def extraer_nombre_paciente(texto):
    """
    Extrae el nombre completo del paciente desde el texto del informe.

    Soporta dos formatos:
    - "Paciente : NOMBRES APELLIDO_PATERNO APELLIDO_MATERNO" (formato chileno habitual,
      sin coma).
    - "Name APELLIDO_PATERNO APELLIDO_MATERNO, NOMBRES" (equipos GE Healthcare / informes
      en inglés, con coma). En este caso las palabras ANTES de la coma son los apellidos
      (paterno y materno) y las palabras DESPUÉS de la coma son los nombres. Se descartan
      palabras de relleno como "Image" que a veces quedan intercaladas por el layout del PDF.
    """
    # Normalizar espacios y eliminar caracteres no imprimibles (la coma se conserva:
    # es parte del rango ASCII imprimible \x20-\x7E)
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'[^\x20-\x7E\u00C0-\u00FF]', '', texto)

    # --- Caso con coma: "APELLIDOS, NOMBRES" ---
    patron_coma = r'(?i)(?:paciente|nombre|patient|name)\s*:?\s*([A-ZÁÉÍÓÚÑa-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑa-záéíóúñ]+)?)\s*,'
    m_coma = re.search(patron_coma, texto)
    if m_coma:
        apellidos = [p for p in re.findall(r'[A-ZÁÉÍÓÚÑa-záéíóúñ]+', m_coma.group(1)) if len(p) >= 2]

        # Texto restante después de la coma, hasta el próximo separador de campo conocido
        resto = texto[m_coma.end():]
        m_fin = re.search(r'(?i)(?:r\.?u\.?t|rut|edad|años|patient\s*id)', resto)
        resto = resto[:m_fin.start()] if m_fin else resto

        # Descartar palabras de relleno tipo "Image 1", "Image 2" (ruido de layout del PDF)
        resto_limpio = re.sub(r'(?i)\bimage\s*\d*\b', ' ', resto)
        nombres = [p for p in re.findall(r'[A-ZÁÉÍÓÚÑa-záéíóúñ]+', resto_limpio) if len(p) >= 2]

        if not nombres or not apellidos:
            return None

        ap_paterno = apellidos[0]
        ap_materno = apellidos[1] if len(apellidos) >= 2 else ""

        # Se reordena a formato chileno (Nombres Apellido_Paterno Apellido_Materno)
        # para mantener compatibilidad con dividir_nombre_completo().
        partes_final = nombres[:2] + [p for p in (ap_paterno, ap_materno) if p]
        return " ".join(partes_final).title()

    # --- Caso sin coma: heurística chilena habitual (Nombres Apellido_Paterno Apellido_Materno) ---
    patron = r'(?i)(?:paciente|nombre|patient|name)\s*:?\s*([^:]+?)(?=\s*(?:r\.?u\.?t|rut|edad|años|\d))'
    m = re.search(patron, texto)
    if not m:
        return None

    raw = m.group(1).strip()

    # Extraer todas las palabras alfabéticas (ignora puntos, comas, etc.)
    palabras = re.findall(r'[A-ZÁÉÍÓÚÑa-záéíóúñ]+', raw)

    # Filtrar palabras de una sola letra (como la 'R' suelta)
    palabras_limpias = [p for p in palabras if len(p) >= 2]

    if len(palabras_limpias) >= 3:
        # Nombres (1 o 2) + dos apellidos; máximo 5 palabras para no arrastrar texto
        # ajeno. Antes se cortaba en 3 y "Juan Carlos Pérez Soto" perdía el materno.
        nombre_final = " ".join(palabras_limpias[:5])
    elif len(palabras_limpias) == 2:
        nombre_final = " ".join(palabras_limpias[:2])  # Solo nombres + paterno
    else:
        return None

    return nombre_final.title()

def dividir_nombre_completo(nombre_completo):
    """
    Separa el nombre completo en:
    - Nombres
    - Apellido paterno
    - Apellido materno
    Asume el formato chileno: [Nombres] [Apellido Paterno] [Apellido Materno]
    """
    if not nombre_completo:
        return "", "", ""
    partes = nombre_completo.split()
    if len(partes) == 1:
        return partes[0], "", ""
    elif len(partes) == 2:
        return partes[0], partes[1], ""
    else:
        # El último es materno, el penúltimo paterno, el resto nombres
        return " ".join(partes[:-2]), partes[-2], partes[-1]
    
def extraer_datos_generales(texto):
    """Intenta detectar RUT, nombre, fecha, peso, talla, FC, ritmo, sexo y médico del informe."""
    datos = {}
    texto_norm = _normalizar(texto)

    m_rut = re.search(r'r\.?u\.?t\.?\s*:?\s*(\d{1,2}\.?\d{3}\.?\d{3}-[\dk])', texto_norm)
    if not m_rut:
        m_rut = re.search(r'patient id\s*(\d{1,8}-[\dk])', texto_norm)
    if m_rut:
        datos["rut"] = m_rut.group(1).upper()

    m_fecha = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', texto)
    if m_fecha:
        datos["fecha_texto"] = m_fecha.group(1)

    m_nac = re.search(r'birthdate\s+(\d{1,2}/\d{1,2}/\d{2,4})', texto_norm)
    if m_nac:
        datos["fecha_nacimiento_texto"] = m_nac.group(1)

    m_genero = re.search(r'gender\s+(masculino|femenino|male|female)|sexo\s*:?\s*(masculino|femenino)', texto_norm)
    if m_genero:
        g = (m_genero.group(1) or m_genero.group(2) or "").strip()
        if g:
            datos["sexo"] = "Masculino" if g in ("masculino", "male") else "Femenino"

    m_peso = re.search(r'(?:weight|peso)\s*:?\s*' + _NUM, texto_norm)
    if m_peso:
        datos["peso"] = m_peso.group(1).replace(",", ".")

    m_talla = re.search(r'(?:height|talla)\s*:?\s*' + _NUM, texto_norm)
    if m_talla:
        datos["talla"] = m_talla.group(1).replace(",", ".")

    m_fc = re.search(r'(\d{2,3})\s*lpm', texto_norm)
    if m_fc:
        datos["fcia"] = m_fc.group(1)

    if re.search(r'ritmo\s*:?\s*sinusal', texto_norm):
        datos["ritmo"] = "Sinusal"

    # Línea por línea: en el texto normalizado los saltos de línea se pierden
    # y el nombre del médico arrastraba palabras de la línea siguiente.
    for linea in (texto or "").splitlines():
        m_medico = re.search(r'(?<![a-z])dr\.?a?\.?\s+[a-z]+(?:\s+[a-z]+){1,3}', _normalizar(linea))
        if m_medico:
            datos["medico_sugerido"] = m_medico.group(0).title()
            break

    nombre_detectado = extraer_nombre_paciente(texto)
    if nombre_detectado:
        datos["nombre_completo"] = nombre_detectado

    return datos
