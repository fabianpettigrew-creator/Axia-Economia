"""Series del INDEC tomadas de la API oficial (api.indec.gob.ar/v1, en etapa beta desde noviembre de 2026).

Respaldo de boletin/indec.py: devuelve las mismas claves que sus LECTORES ({clave: [serie]}), para usarla cuando un
archivo del INDEC no se puede bajar o cambió de formato. La API es PostgREST: filtros como parámetros
(campo=eq.valor), sumas en el servidor (select=campo,v:valor.sum()) y páginas de hasta 1000 filas.

La clave personal va en la variable de entorno de usuario INDEC_API_TOKEN (nunca en el código). Vence el 02/05/2027.
"""
from __future__ import annotations

import os

import pandas as pd
import requests

URL = "https://api.indec.gob.ar/v1/"
PAGINA = 1000
LETRAS_EMAE = {"A": "s_agro", "B": "s_pesca", "C": "s_minas", "D": "s_ind", "E": "s_egas", "F": "s_const", "G": "s_com",
               "H": "s_hot", "I": "s_trans", "J": "s_fin", "K": "s_inmo", "L": "s_adm", "M": "s_ens", "N": "s_salud", "O": "s_otros"}


def token() -> str:
    t = os.environ.get("INDEC_API_TOKEN", "").strip()
    if not t and os.name == "nt":                       # procesos abiertos antes de guardar la variable
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                t = str(winreg.QueryValueEx(k, "INDEC_API_TOKEN")[0]).strip()
        except OSError:
            t = ""
    if not t:
        raise RuntimeError("falta la clave de la API del INDEC (variable de entorno INDEC_API_TOKEN)")
    return t


def consultar(conjunto: str, **params) -> list[dict]:
    """Todas las filas de una consulta, página por página."""
    cab = {"Authorization": f"Bearer {token()}", "User-Agent": "AXIA-boletin"}
    filas, desde = [], 0
    while True:
        r = requests.get(URL + conjunto, params={**params, "limit": PAGINA, "offset": desde}, headers=cab, timeout=90)
        if r.status_code >= 400:
            raise RuntimeError(f"API del INDEC, {conjunto}: HTTP {r.status_code} {r.text[:200]}")
        lote = r.json()
        filas += lote
        if len(lote) < PAGINA:
            return filas
        desde += PAGINA


def _serie(filas: list[dict], fecha="periodo", valor="valor", escala=1.0) -> pd.Series:
    d = {pd.Timestamp(int(str(f[fecha])[:4]), int(str(f[fecha])[4:6]), 1): float(f[valor]) * escala
         for f in filas if f.get(valor) is not None}
    return pd.Series(d, dtype=float).sort_index()


# ---------- lectores (mismas claves que boletin/indec.py)
def ipc() -> dict:
    out = {}
    for clave, clasif, cod in (("ipc", "IPC", "0"), ("ipc_nucleo", "Estacional, Núcleo y Regulados", "N"),
                               ("ipc_reg", "Estacional, Núcleo y Regulados", "R"),
                               ("ipc_est", "Estacional, Núcleo y Regulados", "E")):
        out[clave] = [_serie(consultar("ipc_nacional", select="periodo,valor", region="eq.Nacional", clasificador=f"eq.{clasif}",
                                       codigo=f"eq.{cod}", tipo_de_indicador="eq.Indice", order="periodo.asc"))]
    return out


def emae() -> dict:
    out = {}
    for clave, desc in (("emae", "Índice serie original"), ("emae_de", "Índice serie desestacionalizada"),
                        ("emae_tc", "Índice serie tendencia-ciclo")):
        out[clave] = [_serie(consultar("estimador-mensual-de-actividad-economica-nivel-general", select="periodo,valor",
                                       tipo_de_indicador_descripcion=f"eq.{desc}", order="periodo.asc"))]
    filas = consultar("estimador-mensual-de-actividad-economica-sectores", select="codigo,periodo,valor",
                      tipo_de_indicador="eq.Índice base 2004=100", order="codigo.asc,periodo.asc")
    for letra, clave in LETRAS_EMAE.items():
        out[clave] = [_serie([f for f in filas if f["codigo"] == letra])]
    return out


def ipi() -> dict:
    out = {}
    for clave, serie in (("ipi", "Serie original"), ("ipi_de", "Serie desestacionalizada")):
        out[clave] = [_serie(consultar("ipi_manufacturero", select="periodo,valor", codigo_CLaNAE_2004="eq.D",
                                       descripcion="eq.IPI Manufacturero - Nivel general", serie=f"eq.{serie}",
                                       tipo_de_indicador="eq.Índice", order="periodo.asc"))]
    return out


def comercio() -> dict:
    """Exportaciones FOB e importaciones CIF totales, millones de US$ (suma por mes en el servidor)."""
    out = {}
    for clave, conjunto, campo in (("expo", "comercio_exterior_exportacion_bienes", "valor_FOB"),
                                   ("impo", "comercio_exterior_importacion_bienes", "valor_CIF")):
        out[clave] = [_serie(consultar(conjunto, select=f"Periodo,v:{campo}.sum()", order="Periodo.asc"),
                             fecha="Periodo", valor="v", escala=1e-6)]
    return out


def salarios() -> dict:
    filas = consultar("indice_salarios", select="codigo,periodo,valor", tipo_de_indicador="eq.Indice", order="codigo.asc,periodo.asc")
    s = lambda cod: [_serie([f for f in filas if str(f["codigo"]) == cod])]
    return {"salarios": s("0"), "sal_priv": s("110"), "sal_pub": s("120"), "sal_nreg": s("200")}


LECTORES = {"IPC": ipc, "EMAE": emae, "IPI, ISAC y supermercados": ipi, "comercio exterior": comercio, "salarios": salarios}


# ---------- series del catálogo del Boletín con fuente = indec_api (02/11/2026): id = clave de SERIES
SERIES = {
    "ipim": ("sipm_precios_mayoristas", dict(indicador="eq.IPIM", codigo_apertura="eq.NG", region="eq.Total del país", tipo_de_indicador="eq.Indice")),
    "ipib": ("sipm_precios_mayoristas", dict(indicador="eq.IPIB", codigo_apertura="eq.NG", region="eq.Total del país", tipo_de_indicador="eq.Indice")),
    "ipp": ("sipm_precios_mayoristas", dict(indicador="eq.IPP", codigo_apertura="eq.NG", region="eq.Total del país", tipo_de_indicador="eq.Indice")),
    "icc": ("icc_precios_construccion", dict(codigo_apertura="eq.0", region="eq.GBA", tipo_de_indicador="eq.Indice")),
    "icc_mat": ("icc_precios_construccion", dict(codigo_apertura="eq.01", region="eq.GBA", tipo_de_indicador="eq.Indice")),
    "icc_mo": ("icc_precios_construccion", dict(codigo_apertura="eq.02", region="eq.GBA", tipo_de_indicador="eq.Indice")),
    "icc_gg": ("icc_precios_construccion", dict(codigo_apertura="eq.03", region="eq.GBA", tipo_de_indicador="eq.Indice")),
    "cba": ("valorizacion_canastas_cba_cbt", dict(codigo="eq.CBA", tipo_de_indicador="eq.CBA", region="eq.GBA")),
    "cbt": ("valorizacion_canastas_cba_cbt", dict(codigo="eq.CBT", tipo_de_indicador="eq.CBT", region="eq.GBA")),
}


def serie(clave: str) -> pd.Series:
    """Una serie mensual del catálogo del Boletín (fuente indec_api)."""
    conjunto, filtros = SERIES[clave]
    return _serie(consultar(conjunto, select="periodo,valor", order="periodo.asc", **filtros))
