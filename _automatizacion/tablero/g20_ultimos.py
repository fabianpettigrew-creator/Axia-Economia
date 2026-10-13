"""Últimos datos de alta frecuencia para los países del G20 (solapa "Últimos datos" del tablero).

Cada variable toma el dato más reciente de una fuente oficial con cobertura internacional:
  crec   PIB real, % interanual del último trimestre ......... OCDE (cuentas nacionales trimestrales G20)
  infl   IPC, % interanual del último mes .................... BIS (Eurostat para la Unión Europea)
  desemp tasa de desempleo, último mes o trimestre ........... OCDE; OIT para emergentes; INDEC para Argentina
  cc     cuenta corriente, % del PIB del último trimestre .... OCDE (balanza de pagos)
Lo que no tiene dato de alta frecuencia (y las variables anuales) cae al último año observado del FMI (WEO).
Cada fuente se guarda en cache/; si una descarga falla se usa la copia anterior de esa fuente.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import requests

AQUI = Path(__file__).parent
CACHE = AQUI / "cache" / "g20_ultimos.json"
OECD = "https://sdmx.oecd.org/public/rest/data/"
CSV = {"Accept": "application/vnd.sdmx.data+csv; charset=utf-8"}

PAISES = ["ARG", "AUS", "BRA", "CAN", "CHN", "FRA", "DEU", "IND", "IDN", "ITA", "JPN", "KOR", "MEX", "RUS",
          "SAU", "ZAF", "TUR", "GBR", "USA", "EU"]
ISO2 = {"AR": "ARG", "AU": "AUS", "BR": "BRA", "CA": "CAN", "CN": "CHN", "FR": "FRA", "DE": "DEU", "IN": "IND",
        "ID": "IDN", "IT": "ITA", "JP": "JPN", "KR": "KOR", "MX": "MEX", "RU": "RUS", "SA": "SAU", "ZA": "ZAF",
        "TR": "TUR", "GB": "GBR", "US": "USA"}


def _csv(url: str, **kw) -> pd.DataFrame:
    r = requests.get(url, timeout=180, **kw)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))


def _ultimo(df: pd.DataFrame, area="REF_AREA", t="TIME_PERIOD", v="OBS_VALUE", orden=None) -> dict:
    """{país: (período, valor)} con la observación más reciente de cada país."""
    df = df.dropna(subset=[v]).copy()
    df["_t"] = df[t].astype(str).str.replace("-Q", "Q").str.replace("-", "M")   # 2026Q2 / 2026M08: ordenan bien
    if orden:  # desempate por preferencia (p. ej. desestacionalizado antes que original)
        df["_o"] = df[orden[0]].map({x: i for i, x in enumerate(orden[1])}).fillna(9)
        df = df.sort_values(["_t", "_o"], ascending=[True, False])
    else:
        df = df.sort_values("_t")
    return {a: (g.iloc[-1][t], float(g.iloc[-1][v])) for a, g in df.groupby(area)}


def _per(p) -> str:
    """Etiqueta corta del período: 2026-Q2 -> T2-26, 2026-08 -> ago-26, 2026Q1 -> T1-26, 2025M12 -> dic-25."""
    p = str(p).replace("-Q", "Q")
    if "Q" in p:
        a, q = p.split("Q")
        return f"T{q}-{a[2:]}"
    p = p.replace("M", "-")
    if "-" in p:
        a, m = p.split("-")[:2]
        return ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"][int(m) - 1] + "-" + a[2:]
    return p


# ---------- descargas por fuente (cada una devuelve {país: [período, valor]})
def bajar_pib():
    df = _csv(OECD + "OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_G20,/Q.............?startPeriod=2024-Q1"
              "&dimensionAtObservation=AllDimensions", headers=CSV)
    df = df[(df.TRANSACTION == "B1GQ") & (df.TRANSFORMATION == "GY") & (df.SECTOR == "S1")]
    return _ultimo(df)


def bajar_ipc():
    df = _csv("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_LONG_CPI/1.0/M..771?startPeriod=2025-01&format=csv")
    out = {ISO2[a]: x for a, x in _ultimo(df).items() if a in ISO2}
    # Unión Europea: HICP de Eurostat, variación interanual (desde 2026 en el dataset ECOICOP 2, prc_hicp_minr)
    r = requests.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_minr",
                     params={"geo": "EU", "coicop18": "TOTAL", "unit": "RCH_A", "lastTimePeriod": 4}, timeout=120)
    r.raise_for_status()
    j = r.json()
    tiempos = {i: t for t, i in j["dimension"]["time"]["category"]["index"].items()}
    i = max(int(k) for k in j["value"])   # último período con valor publicado
    out["EU"] = (tiempos[i], float(j["value"][str(i)]))
    return out


def bajar_desempleo():
    base = OECD + "OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_{f},/..._Z.Y._T.Y_GE15..{f}?startPeriod=2025-01&dimensionAtObservation=AllDimensions"
    m = _ultimo(_csv(base.format(f="M").replace("2025-01", "2025-06"), headers=CSV))
    q = _ultimo(_csv(base.format(f="Q").replace("2025-01", "2025-Q1"), headers=CSV))
    out = {}
    for a in set(m) | set(q):  # el más reciente entre mensual y trimestral
        cands = [x for x in (m.get(a), q.get(a)) if x]
        out[a] = max(cands, key=lambda x: _fin_periodo(x[0]))
    ilo = _csv("https://rplumber.ilo.org/data/indicator/?id=UNE_DEAP_SEX_AGE_RT_Q&ref_area=BRA+CHN+IND+IDN+RUS+SAU+ZAF"
               "&sex=SEX_T&classif1=AGE_YTHADULT_YGE15&timefrom=2024&type=code&format=.csv")
    for a, x in _ultimo(ilo, area="ref_area", t="time", v="obs_value").items():
        out.setdefault(a, x)
    return out


def bajar_cc():
    paises = "+".join(p for p in PAISES if p != "EU")
    df = _csv(OECD + f"OECD.SDD.TPS,DSD_BOP@DF_BOP,/{paises}+EU27_2020.WXD.CA.B.T.Q.PT_B1GQ.?startPeriod=2024-Q1"
              "&dimensionAtObservation=AllDimensions", headers=CSV)
    df["REF_AREA"] = df.REF_AREA.replace({"EU27_2020": "EU"})
    return _ultimo(df, orden=("ADJUSTMENT", ["Y", "N"]))


def _fin_periodo(p) -> pd.Timestamp:
    p = str(p).replace("-Q", "Q")
    if "Q" in p:
        a, q = p.split("Q")
        return pd.Period(f"{a}Q{q}", "Q").end_time
    return pd.Period(p.replace("M", "-")[:7], "M").end_time


FUENTES = {"crec": bajar_pib, "infl": bajar_ipc, "desemp": bajar_desempleo, "cc": bajar_cc}
NOMBRE_FUENTE = {"crec": "OCDE", "infl": "BIS", "desemp": "OCDE", "cc": "OCDE"}


def ultimos(weo: dict, desoc_arg: pd.Series | None = None, ipc_arg: dict | None = None, horas=12) -> dict:
    """weo = bloque g20 del tablero (FMI). Devuelve {var: {país: {"v", "p", "f"}}} y la fecha de consulta."""
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {"fuentes": {}}
    for k, fn in FUENTES.items():
        viejo = cache["fuentes"].get(k)
        if viejo and (pd.Timestamp.now() - pd.Timestamp(viejo["bajado"])).total_seconds() < horas * 3600:
            continue
        try:
            datos = {a: [str(p), round(v, 2)] for a, (p, v) in fn().items()}
            cache["fuentes"][k] = {"bajado": pd.Timestamp.now().isoformat(timespec="seconds"), "datos": datos}
        except Exception as e:
            print(f"Aviso: no se pudo actualizar '{k}' ({e}); uso la copia guardada" if viejo else f"Aviso: sin datos para '{k}': {e}")
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    anios, ind = weo["anios"], weo["ind"]
    i_ult = anios.index(weo["proy_desde"] - 1)   # último año no proyectado del WEO
    out = {}
    for k in ind:
        alta = cache["fuentes"].get(k, {}).get("datos", {})
        col = {}
        for p in PAISES:
            if p in alta:
                per, v = alta[p]
                fuente = NOMBRE_FUENTE[k]
                if k == "infl" and p == "EU":
                    fuente = "Eurostat"
                if k == "desemp" and p in ("BRA", "CHN", "IND", "IDN", "RUS", "SAU", "ZAF"):
                    fuente = "OIT"
                col[p] = {"v": round(v, 1), "p": _per(per), "f": fuente, "t": str(_fin_periodo(per).date())}
            else:
                v = ind[k]["v"][p][i_ult]
                if v is not None:
                    col[p] = {"v": v, "p": str(anios[i_ult]), "f": "FMI", "t": f"{anios[i_ult]}-12-31"}
        out[k] = col
    # Argentina: desempleo directo del INDEC (EPH), más reciente que la OIT
    if desoc_arg is not None and len(desoc_arg.dropna()):
        s = desoc_arg.dropna()
        q = pd.Period(s.index[-1], "Q")
        out["desemp"]["ARG"] = {"v": round(float(s.iloc[-1]), 1), "p": f"T{q.quarter}-{str(q.year)[2:]}", "f": "INDEC",
                                "t": str(q.end_time.date())}
    # Argentina: inflación del INDEC tal como figura en la sección Precios del tablero
    if ipc_arg:
        f = pd.Timestamp(ipc_arg["fecha"])
        out["infl"]["ARG"] = {"v": round(ipc_arg["valor"], 1), "p": _per(f.strftime("%Y-%m")), "f": "INDEC",
                              "t": str(pd.Period(f, "M").end_time.date())}
    return {"v": out, "consulta": pd.Timestamp.now().strftime("%Y-%m-%d")}
