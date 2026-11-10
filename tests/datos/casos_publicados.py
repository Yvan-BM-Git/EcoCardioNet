# Casos clínicos publicados (PDF en Papers/). Solo cifras reportadas por los autores.
# "derivado" = calculado a partir de cifras del artículo (indicado en la nota).
from datetime import date

CASOS = [
    dict(id="A", archivo="A_Taniguchi_EA_paradojica_IM_EHJCR2023.pdf",
         titulo="EA bajo flujo-bajo gradiente paradójica + IM funcional",
         rut="21.000.001-6", nombre="Caso A", sexo="Masculino", nac=date(1937, 1, 1),  # 86 años (2023)
         ritmo=None, fc=None, pas=None, pad=None,
         autores=["EA severa de bajo flujo y bajo gradiente paradójica (FEVI 52 %)",
                  "IM moderada a severa por dilatación anular", "IAo leve a moderada"],
         clave_esperada=["bajo flujo y bajo gradiente", "Insuficiencia mitral", "Insuficiencia aórtica"],
         v=dict(FEVI=52, VOLUMEN_FIN_DIASTOLE_VI=118, VELOCIDAD_PICO_AORTICA=3.0, GRADIENTE_MEDIO_AORTICO=20.7,
                AREA_VALVULAR_AORTICA_CONTINUIDAD=0.78, VOLUMEN_LATIDO_INDEXADO_AORTICO=26.2, PROTESIS_AORTICA="Ausente",
                GRADO_REFLUJO_MITRAL="Moderada-Severa", EROA_MITRAL=0.24, VOLUMEN_REGURGITANTE_MITRAL=43,
                PROTESIS_MITRAL="Ausente", GRADO_REFLUJO_AORTICO="Leve-Moderada", VENA_CONTRACTA_AORTICA=4.6)),
    dict(id="B", archivo="B_EA_bajo_flujo_clasica_sin_reserva_EHJCR2022.pdf",
         titulo="EA bajo flujo-bajo gradiente clásica sin reserva contráctil",
         rut="21.000.002-4", nombre="Caso B", sexo="Femenino", nac=date(1949, 1, 1),  # 73 años
         ritmo="Fibrilación auricular", fc=90, pas=97, pad=80,
         autores=["EA severa de bajo flujo y bajo gradiente clásica (FEVI 22 %)", "VI dilatado", "Fibrilación auricular"],
         clave_esperada=["bajo flujo y bajo gradiente", "FEVI de 22", "Dilatación", "fibrilación auricular"],
         # Vmax derivado: √(gradiente máximo 33 mmHg / 4) = 2,87 m/s
         v=dict(FEVI=22, DIAMETRO_VI_DIASTOLICO=69.9, SEPTUM_INTERVENTRICULAR=11.4, PARED_POSTERIOR_VI=13,
                GRADIENTE_MEDIO_AORTICO=21, VELOCIDAD_PICO_AORTICA=2.87, VOLUMEN_LATIDO_INDEXADO_AORTICO=16,
                AREA_VALVULAR_AORTICA_CONTINUIDAD=0.6, VTI_TSVI=11.2, VTI_AORTICO=59.6, INDICE_VELOCIDAD_DOPPLER=0.19,
                PROTESIS_AORTICA="Ausente")),
    dict(id="C", archivo="C_HTP_tromboembolica_Liu_EurJMedRes2015.pdf",
         titulo="HTP tromboembólica crónica (control abril 2012)",
         rut="21.000.003-2", nombre="Caso C", sexo="Femenino", nac=date(1939, 1, 1),  # 68 años en 2007
         ritmo=None, fc=None, pas=None, pad=None,
         autores=["HTP severa (PSAP 86 mmHg)", "VD y AD muy dilatados", "Disfunción del VD (TAPSE 13 mm)",
                  "RVP elevada (3,34 UW)", "FEVI normal"],
         clave_esperada=["86 mmHg", "Dilatación del ventrículo derecho", "TAPSE 13", "Desacoplamiento"],
         v=dict(DIAMETRO_VI_DIASTOLICO=37, SEPTUM_INTERVENTRICULAR=8, DIAMETRO_VD_BASAL=51, AREA_AD_4_CAMARAS=30,
                FEVI=85, TAPSE=13, VELOCIDAD_MAXIMA_IT=4.2, GRADIENTE_MAXIMO_IT=71, VTI_TSVD=12.0,
                RESISTENCIA_VASCULAR_PULMONAR=3.34, PSAP=86, TRONCO_ARTERIA_PULMONAR=25, MAGNITUD_DERRAME_PERICARDICO=0)),
    dict(id="D", archivo="D_Estenosis_mitral_reumatica_Wilkins9_PMC10939169.pdf",
         titulo="Estenosis mitral reumática con prótesis aórtica mecánica",
         rut="21.000.004-0", nombre="Caso D", sexo="Femenino", nac=date(1950, 1, 1),  # 74 años
         ritmo="Fibrilación auricular", fc=90, pas=None, pad=None,
         autores=["EM clínicamente significativa (AVM 1,0 cm²; GM 10 mmHg)", "Wilkins 9",
                  "IM trivial", "IT moderada", "PSAP 48 mmHg", "Prótesis aórtica mecánica", "FA"],
         clave_esperada=["Estenosis mitral", "Wilkins 9", "tricuspídea moderada", "48 mmHg", "fibrilación auricular"],
         v=dict(AREA_MITRAL=1.0, GRADIENTE_MEDIO_MITRAL=10, SCORE_WILKINS=9, MOVILIDAD_VELOS_MITRALES=3,
                ENGROSAMIENTO_VELOS_MITRALES=2, CALCIFICACION_MITRAL=3, ENGROSAMIENTO_SUBVALVULAR=1,
                GRADO_REFLUJO_MITRAL="Mínima", PROTESIS_MITRAL="Ausente", GRADO_REFLUJO_TRICUSPIDEO="Moderada",
                PSAP=48, VOLUMEN_LATIDO_INDEXADO_AORTICO=28, PROTESIS_AORTICA="Mecánica")),
    dict(id="E", archivo="E_IAo_Takayasu_Murayama_CASE2018.pdf",
         titulo="IAo severa por arteritis de Takayasu",
         rut="21.000.005-9", nombre="Caso E", sexo="Masculino", nac=date(1976, 1, 1),  # 42 años
         ritmo="Sinusal", fc=None, pas=104, pad=44,
         autores=["IAo severa (VC 11 mm, PHT 174 ms, Vol Rg 70 mL)", "VI dilatado con hipertrofia excéntrica",
                  "FEVI conservada con GLS reducido (-14 %)", "Raíz aórtica dilatada (seno 43 mm)"],
         clave_esperada=["aórtica severa", "excéntrica", "subclínica", "Dilatación de la aorta"],
         v=dict(FEVI=66, DIAMETRO_VI_DIASTOLICO=61, GROSOR_PARIETAL_RELATIVO=0.26, MASA_VI_INDEXADA=121,
                STRAIN_LONGITUDINAL_GLOBAL_VI=-14, GRADO_REFLUJO_AORTICO="Severa", VENA_CONTRACTA_AORTICA=11,
                TIEMPO_HEMIPRESION_AORTICO=174, RAIZ_AORTICA=43, AORTA_ASCENDENTE=42, PROTESIS_AORTICA="Ausente")),
    dict(id="F", archivo="F_Protesis_mecanica_trombosis_EHJCR2022.pdf",
         titulo="Trombosis de prótesis aórtica mecánica en embarazo",
         rut="21.000.006-7", nombre="Caso F", sexo="Femenino", nac=date(1999, 1, 1),  # 23 años
         ritmo=None, fc=None, pas=None, pad=None,
         autores=["Obstrucción de prótesis aórtica mecánica por trombosis (GM 58 mmHg; DVI 0,24; TA 130 ms)",
                  "IAo trivial (esperable)"],
         clave_esperada=["obstrucción"],
         # Vmax derivado: √(gradiente máximo 87 mmHg / 4) = 4,66 m/s
         v=dict(PROTESIS_AORTICA="Mecánica", GRADIENTE_MEDIO_AORTICO=58, VELOCIDAD_PICO_AORTICA=4.66,
                INDICE_VELOCIDAD_DOPPLER=0.24, GRADO_REFLUJO_AORTICO="Mínima")),
    dict(id="G", archivo="G_Taponamiento_lupus_Cureus2022.pdf",
         titulo="Taponamiento cardíaco como debut de lupus",
         rut="21.000.007-5", nombre="Caso G", sexo="Femenino", nac=date(1984, 1, 1),  # 38 años
         ritmo="Taquicardia sinusal", fc=115, pas=90, pad=60,
         autores=["Derrame pericárdico grande (27 mm) con taponamiento", "Taquicardia sinusal"],
         clave_esperada=["Taponamiento", "severo", "taquicardia sinusal"],
         v=dict(MAGNITUD_DERRAME_PERICARDICO=27, GRADO_DERRAME_PERICARDICO="Severo", TAPONAMIENTO_CARDIACO="Sí")),
]
