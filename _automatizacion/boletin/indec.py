"""Series del INDEC tomadas directamente de los archivos que publica el INDEC.

La API de datos.gob.ar replica los datos del INDEC con horas o días de demora. Para que el Boletín y el tablero
muestren el último dato el mismo día de la publicación, `integrar(df)` reemplaza cada serie del catálogo cuyo
organismo es el INDEC por la versión del archivo del INDEC (incluidas sus revisiones), siempre que coincida con la
serie ya cargada en los meses en común (misma base y unidad). Si no coincide o el archivo no se puede leer, deja la
serie como estaba y avisa: un cambio de formato del INDEC nunca publica un dato equivocado.

Archivos (www.indec.gob.ar/ftp/cuadros/...): los de nombre fijo se piden directo; los que cambian de nombre con cada
publicación (p. ej. cuadros_informe_pobreza_09_26.xls) se buscan en la página del tema (/Nivel4/Tema/...).
"""
from __future__ import annotations

import io
import re
import time
import unicodedata

import pandas as pd
import requests

FTP = "https://www.indec.gob.ar/ftp/cuadros/"
TEMA = "https://www.indec.gob.ar/Nivel4/Tema/"
HDR = {"User-Agent": "Mozilla/5.0"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
LETRAS_EMAE = {"A": "s_agro", "B": "s_pesca", "C": "s_minas", "D": "s_ind", "E": "s_egas", "F": "s_const", "G": "s_com",
               "H": "s_hot", "I": "s_trans", "J": "s_fin", "K": "s_inmo", "L": "s_adm", "M": "s_ens", "N": "s_salud", "O": "s_otros"}
RUBROS_EXPO = {"productos primarios": "x_pp", "manufacturas de origen agropecuario": "x_moa",
               "manufacturas de origen industrial": "x_moi", "combustibles y energia": "x_cye"}
USOS_IMPO = {"bienes de capital": "m_bk", "bienes intermedios": "m_bi", "combustibles y lubricantes": "m_cyl",
             "piezas y accesorios": "m_pzas", "bienes de consumo": "m_bc", "vehiculos automotores": "m_auto"}


# ---------- utilidades
def _norm(x) -> str:
    s = unicodedata.normalize("NFD", str(x)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def _bajar(url: str) -> bytes:
    for intento in range(4):
        try:
            r = requests.get(url, headers=HDR, timeout=90)
            r.raise_for_status()
            if r.content.lstrip()[:1] == b"<":   # el INDEC devuelve una página HTML cuando el archivo no existe
                raise FileNotFoundError(url)
            return r.content
        except FileNotFoundError:
            raise
        except Exception:
            if intento == 3:
                raise
            time.sleep(5 * (intento + 1))


def _excel(rel: str, hoja):
    return pd.read_excel(io.BytesIO(_bajar(FTP + rel)), sheet_name=hoja, header=None)


def _vinculo(tema: str, patron: str) -> str:
    """Primer archivo de la página del tema cuyo nombre cumple el patrón (la página lista el más reciente primero)."""
    r = requests.get(TEMA + tema, headers=HDR, timeout=90)
    r.raise_for_status()
    for v in re.findall(r"ftp/cuadros/([\w/]+\.(?:xlsx?|csv))", r.text):
        if re.search(patron, v):
            return v
    raise FileNotFoundError(f"no hay {patron} en el tema {tema}")


def _mes(x):
    """Número de mes de una etiqueta como 'Agosto', 'Agostoe', 'Ago*' o 'sep'; None si no es un mes."""
    t = re.sub(r"[^a-z]", "", _norm(x))
    for i, m in enumerate(MESES):
        if len(t) >= 3 and (t.startswith(m) or m.startswith(t) or (t[:3] == m[:3] and len(t) <= len(m) + 1)):
            return i + 1
    return None


def _filas_mensuales(df: pd.DataFrame, col_anio: int, col_mes: int) -> list[tuple[pd.Timestamp, int]]:
    """Filas de una tabla con año (solo en enero) y mes en columnas separadas; o fecha completa en col_mes."""
    out, anio = [], None
    for i in range(len(df)):
        a, m = df.iat[i, col_anio], df.iat[i, col_mes]
        if isinstance(m, (pd.Timestamp,)) or (hasattr(m, "year") and hasattr(m, "month")):
            out.append((pd.Timestamp(m.year, m.month, 1), i))
            continue
        try:
            if pd.notna(a) and 1900 < float(str(a).strip("* ")) < 2100:
                anio = int(float(str(a).strip("* ")))
        except ValueError:
            pass
        n = _mes(m) if pd.notna(m) else None
        if anio and n:
            out.append((pd.Timestamp(anio, n, 1), i))
    return out


def _serie(df, filas, col) -> pd.Series:
    s = pd.Series({f: pd.to_numeric(df.iat[i, col], errors="coerce") for f, i in filas}, dtype=float)
    return s.dropna().sort_index()


def _col(df, fila: int, texto: str) -> int:
    """Columna cuyo encabezado (en la fila dada) empieza con el texto."""
    for c in range(df.shape[1]):
        if _norm(df.iat[fila, c]).startswith(_norm(texto)):
            return c
    raise KeyError(texto)


# ---------- lectores por tema: cada uno devuelve {clave: [series candidatas]}
def ipc() -> dict:
    out = {}
    c = pd.read_csv(io.BytesIO(_bajar(FTP + "economia/serie_ipc_divisiones.csv")), sep=";", encoding="latin-1",
                    dtype={"Codigo": str, "Periodo": str})
    c = c[(c.Codigo == "0") & (c.Region == "Nacional")]
    out["ipc"] = [pd.Series(pd.to_numeric(c.Indice_IPC.str.replace(",", "."), errors="coerce").values,
                            index=pd.to_datetime(c.Periodo, format="%Y%m")).dropna()]
    hoy = pd.Timestamp.today()
    for k in range(3):                                   # sh_ipc_MM_AA.xls: MM_AA = mes de publicación
        m = hoy - pd.DateOffset(months=k)
        try:
            x = _excel(f"economia/sh_ipc_{m:%m}_{m:%y}.xls", 2)
        except FileNotFoundError:
            continue
        fila0 = x.index[x.iloc[:, 0].astype(str).str.strip() == "Total nacional"][0]
        fin = x.index[x.iloc[:, 0].astype(str).str.startswith("Región")][0]
        fechas = pd.to_datetime(x.iloc[fila0, 1:], errors="coerce")
        for clave, etiqueta in (("ipc_nucleo", "Núcleo"), ("ipc_reg", "Regulados"), ("ipc_est", "Estacional")):
            f = x.loc[fila0:fin][x.loc[fila0:fin].iloc[:, 0].astype(str).str.strip() == etiqueta].iloc[0]
            s = pd.Series(pd.to_numeric(f.iloc[1:].values, errors="coerce"), index=fechas.values)
            out[clave] = [s[s.index.notna()].dropna()]
        break
    return out


def emae() -> dict:
    out = {}
    x = _excel("economia/sh_emae_mensual_base2004.xls", 0)
    filas = _filas_mensuales(x, 0, 1)
    for clave, txt in (("emae", "indice serie original"), ("emae_de", "indice serie desestacionalizada"),
                       ("emae_tc", "indice serie tendencia")):
        out[clave] = [_serie(x, filas, _col(x, 2, txt))]
    x = _excel("economia/sh_emae_actividad_base2004.xls", 0)
    filas = _filas_mensuales(x, 0, 1)
    for c in range(2, x.shape[1]):
        letra = str(x.iat[2, c]).strip()[:1]
        if letra in LETRAS_EMAE and re.match(r"^[A-Z]\s*-", str(x.iat[2, c]).strip()):
            out[LETRAS_EMAE[letra]] = [_serie(x, filas, c)]
    return out


def ipi_isac_super() -> dict:
    out = {}
    anio = pd.Timestamp.today().year
    for a in (anio, anio - 1):                          # el archivo lleva el año en el nombre
        try:
            x = _excel(f"economia/sh_ipi_manufacturero_{a}.xls", "Cuadro 1")
            break
        except FileNotFoundError:
            x = None
    if x is not None:
        filas = _filas_mensuales(x, 1, 2)
        out["ipi"] = [_serie(x, filas, _col(x, 3, "serie original"))]
        out["ipi_de"] = [_serie(x, filas, _col(x, 3, "serie desestacionalizada"))]
    for a in (anio, anio - 1):
        try:
            x = _excel(f"economia/sh_isac_{a}.xls", "Cuadro 1")
            break
        except FileNotFoundError:
            x = None
    if x is not None:
        out["isac"] = [_serie(x, _filas_mensuales(x, 0, 1), _col(x, 2, "serie original"))]
    x = _excel("economia/serie_supermercados.xlsx", None)
    cands = []
    for hoja, col in (("Cuadro 1", 1), ("Cuadro 3.", 2), ("Cuadro 2", 5)):
        if hoja in x:
            t = x[hoja]
            cands.append(_serie(t, _filas_mensuales(t, 0, 0), col))
    out["super"] = cands
    return out


def comercio() -> dict:
    out = {}
    x = _excel("economia/balanmensual.xls", 0)
    filas = _filas_mensuales(x, 0, 1)
    out["expo"] = [_serie(x, filas, _col(x, 2, "exportaciones"))]
    out["impo"] = [_serie(x, filas, _col(x, 2, "importaciones"))]
    for patron, mapa, col_mes in ((r"expo_grandes_rubros_\d{4}_\d{4}", RUBROS_EXPO, 1),
                                  (r"impo_uso_economico_\d{4}_\d{4}", USOS_IMPO, 0)):
        t = _excel(_vinculo("3/2/40", patron), 0)
        fila_anio = next(i for i in range(15) if any(re.match(r"ano \d{4}", _norm(v)) for v in t.iloc[i]))
        rubro = None
        series = {}
        for c in range(t.shape[1]):
            for i in range(fila_anio):                   # nombre del rubro: última celda con texto arriba del año
                if pd.notna(t.iat[i, c]) and str(t.iat[i, c]).strip():
                    rubro = _norm(t.iat[i, c])
            m = re.match(r"ano (\d{4})", _norm(t.iat[fila_anio, c]))
            if not m or rubro is None:
                continue
            clave = next((v for k, v in mapa.items() if rubro.startswith(k)), None)
            if clave is None:
                continue
            for i in range(fila_anio + 1, len(t)):
                n = _mes(t.iat[i, col_mes])
                v = pd.to_numeric(t.iat[i, c], errors="coerce")
                if n and pd.notna(v):
                    series.setdefault(clave, {})[pd.Timestamp(int(m.group(1)), n, 1)] = float(v)
        for clave, d in series.items():
            out[clave] = [pd.Series(d).sort_index()]
    return out


def salarios() -> dict:
    c = pd.read_csv(io.BytesIO(_bajar(FTP + "sociedad/indice_salarios.csv")), sep=";", encoding="latin-1", na_values=["NA"])
    idx = pd.to_datetime(c.periodo, format="%d/%m/%Y")
    s = lambda col: [pd.Series(pd.to_numeric(c[col].astype(str).str.replace(",", "."), errors="coerce").values, index=idx).dropna()]
    return {"salarios": s("IS_indice_total"), "sal_priv": s("IS_sector_privado_registrado"),
            "sal_pub": s("IS_sector_publico"), "sal_nreg": s("IS_sector_no_registrado")}


def eph() -> dict:
    x = _excel(_vinculo("4/31/58", r"cuadros_tasas_indicadores_eph_\d\d_\d\d"), "Cuadro 1.1")
    # fila de trimestres: varias celdas tipo "1° trimestre" (el título del cuadro también dice "trimestre")
    fila_t = next(i for i in range(15) if sum(bool(re.match(r"\d\S* trimestre", _norm(v))) for v in x.iloc[i]) >= 2)
    anio, fechas = None, {}
    for c in range(x.shape[1]):
        a = re.search(r"(\d{4})", _norm(x.iat[fila_t - 1, c]))
        if a:
            anio = int(a.group(1))
        q = re.match(r"(\d)", _norm(x.iat[fila_t, c]))
        if anio and q:
            fechas[c] = pd.Timestamp(anio, 3 * (int(q.group(1)) - 1) + 1, 1)
    out = {}
    for clave, etiqueta in (("eph_activ", "actividad"), ("eph_empleo", "empleo"), ("eph_desoc", "desocupacion abierta")):
        fila = next(i for i in range(len(x)) if _norm(x.iat[i, 0]) == etiqueta)
        s = pd.Series({f: pd.to_numeric(x.iat[fila, c], errors="coerce") for c, f in fechas.items()}, dtype=float).dropna()
        out[clave] = [s, s / 100]                        # la API la publica en proporción; se elige la que coincide
    return out


def pobreza() -> dict:
    x = _excel(_vinculo("4/46/152", r"cuadros_informe_pobreza_\d\d_\d\d"), "Cuadro 1")
    fila_p = next(i for i in range(len(x)) if _norm(x.iat[i, 0]) == "pobreza")
    fila = next(i for i in range(fila_p + 1, len(x)) if _norm(x.iat[i, 0]) == "personas")
    d = {}
    for c in range(1, x.shape[1]):
        m = re.search(r"(1er|2do)\.? semestre (\d{4})", _norm(x.iat[2, c]))
        v = pd.to_numeric(x.iat[fila, c], errors="coerce")
        if m and pd.notna(v):
            d[pd.Timestamp(int(m.group(2)), 1 if m.group(1) == "1er" else 7, 1)] = float(v)
    return {"pobreza": [pd.Series(d).sort_index()]}


LECTORES = {"IPC": ipc, "EMAE": emae, "IPI, ISAC y supermercados": ipi_isac_super, "comercio exterior": comercio,
            "salarios": salarios, "EPH": eph, "pobreza": pobreza}


# ---------- integración con el vintage
def _coincide(cand: pd.Series, ref: pd.Series) -> float | None:
    """Diferencia relativa mediana en los meses en común (los últimos 24); None si hay menos de 4 en común."""
    comun = ref.index.intersection(cand.index)[-24:]
    if len(comun) < 4:
        return None
    r, c = ref[comun].astype(float), cand[comun].astype(float)
    return float(((c - r).abs() / r.abs().clip(lower=1e-9)).median())


def integrar(df: pd.DataFrame, claves_indec: list[str], tolerancia=0.02) -> pd.DataFrame:
    """df: vintage en formato largo (fecha, clave, valor). Reemplaza las series del INDEC por las del archivo del
    INDEC cuando coinciden con la cargada; la historia anterior a la cobertura del archivo queda como estaba."""
    df = df.assign(fecha=pd.to_datetime(df.fecha))
    candidatas = {}
    for tema, f in LECTORES.items():
        try:
            for k, v in f().items():
                candidatas.setdefault(k, []).extend(v)
        except Exception as e:
            print(f"AVISO: INDEC {tema}: no se pudo leer el archivo ({e.__class__.__name__}: {e}); se usa la API")
    partes, reemplazadas = [df], set()
    for clave in claves_indec:
        cands = [c for c in candidatas.get(clave, []) if len(c)]
        if not cands:
            continue
        ref = df[df.clave == clave].set_index("fecha").valor.sort_index()
        if ref.empty:
            continue
        evaluadas = [(d, c) for c in cands if (d := _coincide(c, ref)) is not None]
        if not evaluadas or min(evaluadas, key=lambda t: t[0])[0] > tolerancia:
            print(f"AVISO: INDEC {clave}: el archivo no coincide con la serie cargada; se deja la de la API")
            continue
        mejor = min(evaluadas, key=lambda t: t[0])[1]
        nueva = pd.concat([ref[ref.index < mejor.index[0]], mejor]).sort_index()
        nueva = nueva[~nueva.index.duplicated(keep="last")]
        if nueva.index[-1] > ref.index[-1]:
            print(f"INDEC: {clave} con dato a {nueva.index[-1]:%Y-%m} (la API llegaba a {ref.index[-1]:%Y-%m})")
        partes.append(pd.DataFrame({"fecha": nueva.index, "clave": clave, "valor": nueva.values}))
        reemplazadas.add(clave)
    partes[0] = df[~df.clave.isin(reemplazadas)]
    return pd.concat(partes, ignore_index=True).sort_values(["clave", "fecha"]).reset_index(drop=True)
