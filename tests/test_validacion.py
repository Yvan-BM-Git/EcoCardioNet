"""utils/validacion.py: validación de campos numéricos."""
import pytest

from utils.validacion import (
    DECIMALES_MAX, advertencia_rango, clase_widget, normalizar_texto_numero,
    permite_negativo, texto_normalizado, validar_numero,
)


@pytest.mark.parametrize("codigo, esperado", [
    ("STRAIN_LONGITUDINAL_GLOBAL_VI", True),
    ("STRAIN_VD_PARED_LIBRE", True),
    ("STRAIN_AI_LASR", False),      # el strain auricular es positivo
    ("FEVI", False),
    (None, False),
    ("", False),
])
def test_permite_negativo(codigo, esperado):
    assert permite_negativo(codigo) is esperado


@pytest.mark.parametrize("entrada, esperado", [
    ("12,5", "12.5"), ("  70 ", "70"), ("1 234", "1234"), (None, ""), (60, "60"),
])
def test_normalizar_texto_numero(entrada, esperado):
    assert normalizar_texto_numero(entrada) == esperado


@pytest.mark.parametrize("valor, kwargs, numero", [
    ("70", {}, 70),
    ("12,5", {}, 12.5),
    ("12.34", {}, 12.34),
    ("-18", {"permitir_negativo": True}, -18),
    ("120", {"decimales": 0}, 120),
    (55, {}, 55),
    (55.5, {}, 55.5),
    ("", {}, None),
    (None, {}, None),
])
def test_validar_numero_validos(valor, kwargs, numero):
    resultado, error = validar_numero(valor, **kwargs)
    assert error is None
    assert resultado == numero
    if numero is not None:
        assert type(resultado) is type(numero)  # entero sigue entero


@pytest.mark.parametrize("valor, kwargs, fragmento", [
    ("-5", {}, "negativo"),
    (-5, {}, "negativo"),
    ("12.345", {}, f"máximo {DECIMALES_MAX} decimales"),
    ("120,5", {"decimales": 0}, "entero"),
    (120.5, {"decimales": 0}, "entero"),
    ("abc", {}, "no es un número"),
    ("1e3", {}, "no es un número"),
    ("12..5", {}, "no es un número"),
])
def test_validar_numero_invalidos(valor, kwargs, fragmento):
    resultado, error = validar_numero(valor, nombre="FEVI", **kwargs)
    assert resultado is None
    assert fragmento in error


def test_validar_numero_bool_no_es_numero():
    assert validar_numero(True) == (None, None)


@pytest.mark.parametrize("numero, original, esperado", [
    (12.5, "12,5", "12.5"), (70, "70", "70"), (None, "x", ""), (12.0, "12.0", "12.0"),
    (12, "12.", "12"), (0.5, ".5", "0.5"), (-0.5, "-.5", "-0.5"),
])
def test_texto_normalizado(numero, original, esperado):
    assert texto_normalizado(numero, original) == esperado


def test_advertencia_rango():
    assert advertencia_rango(5, 10, 90, "%") .startswith("Valor bajo el mínimo plausible (10 %)")
    assert "máximo plausible (90" in advertencia_rango(95, 10, 90)
    assert advertencia_rango(50, 10, 90) is None
    assert advertencia_rango(50, None, None) is None      # sin límites en el Excel
    assert advertencia_rango(None, 10, 90) is None
    assert advertencia_rango(5, "", "") is None            # celdas vacías


def test_clase_widget():
    assert clase_widget("var_FEVI") == "st-key-var_FEVI"
    assert clase_widget(" peso input ") == "st-key-peso-input"
