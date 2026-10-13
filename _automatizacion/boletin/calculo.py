"""Transformaciones estándar e indicadores del Boletín.

Todas las cifras que aparecen en los textos salen de `indicadores()`: el texto usa
marcadores {clave} y nunca números tipeados a mano.
"""
from __future__ import annotations

import pandas as pd

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
MES3 = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MENOS = "−"


# ---------- formato ----------
def num(x, dec=1, signo=False) -> str:
    if x is None or pd.isna(x):
        return "s.d."
    s = f"{abs(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if x < 0 and round(abs(x), dec) != 0:
        return MENOS + s
    return ("+" + s) if signo else s


def pct(x, dec=1, signo=True) -> str:
    return num(x, dec, signo) + "%"


def mes(t: pd.Timestamp, corto=False, anio=True) -> str:
    m = (MES3 if corto else MESES)[t.month - 1]
    if not anio:
        return m
    return f"{m}-{str(t.year)[2:]}" if corto else f"{m} de {t.year}"


def fecha_larga(t: pd.Timestamp) -> str:
    return f"{t.day} de {MESES[t.month - 1]} de {t.year}"


# ---------- transformaciones ----------
def mensual(s: pd.Series) -> pd.Series:
    """Promedio mensual (para series diarias del BCRA)."""
    return s.resample("MS").mean().dropna()


def var(s: pd.Series, n=1) -> pd.Series:
    return (s / s.shift(n) - 1) * 100


def ia(s: pd.Series) -> pd.Series:
    return var(s, 12)


def acum_anio(s: pd.Series) -> pd.Series:
    """Variación acumulada en el año respecto de diciembre previo (para índices de precios)."""
    base = s.reindex([pd.Timestamp(t.year - 1, 12, 1) for t in s.index]).values
    return (s / base - 1) * 100


def ia_acum(s: pd.Series) -> float:
    """Var. % del acumulado enero-último mes contra igual período del año anterior."""
    t = s.index[-1]
    act = s[(s.index.year == t.year) & (s.index.month <= t.month)].sum()
    ant = s[(s.index.year == t.year - 1) & (s.index.month <= t.month)].sum()
    return (act / ant - 1) * 100


def real(nominal_ia: pd.Series, ipc: pd.Series) -> pd.Series:
    p = ia(ipc).reindex(nominal_ia.index)
    return ((1 + nominal_ia / 100) / (1 + p / 100) - 1) * 100


# ---------- indicadores ----------
SECTORES = ["s_agro", "s_pesca", "s_minas", "s_ind", "s_egas", "s_const", "s_com", "s_hot",
            "s_trans", "s_fin", "s_inmo", "s_adm", "s_ens", "s_salud", "s_otros"]


def indicadores(d: dict[str, pd.Series], cat: pd.DataFrame) -> dict:
    """Devuelve {clave: texto formateado} más algunos valores crudos con prefijo '_'."""
    v: dict = {}

    def ult(s):
        return s.dropna().index[-1]

    # Actividad
    e, ed, et = d["emae"], d["emae_de"], d["emae_tc"]
    v["emae_mes"] = mes(ult(e))
    v["emae_mes_c"] = mes(ult(e), corto=True)
    v["emae_mm"] = pct(var(ed).iloc[-1])
    v["emae_mm_ant"] = pct(var(ed).iloc[-2])
    v["emae_ia"] = pct(ia(e).iloc[-1])
    v["emae_acum"] = pct(ia_acum(e))
    v["emae_tc_mm"] = pct(var(et).iloc[-1], 2)
    v["emae_tc_ia"] = pct(ia(et).iloc[-1])
    pico = ed["2022":].idxmax()
    v["emae_vs_pico"] = pct((ed.iloc[-1] / ed.max() - 1) * 100)
    v["emae_pico_mes"] = mes(pico)
    v["emae_nivel_desde"] = mes(ed[ed <= ed.iloc[-1]].index[-2]) if (ed <= ed.iloc[-1]).sum() > 1 else "s.d."
    v["_emae_mm"] = var(ed).iloc[-1]
    mme = var(ed).dropna()
    peores = mme[mme <= mme.iloc[-1]]
    v["emae_caida_desde"] = mes(peores.index[-2]) if len(peores) > 1 else "el inicio de la serie"
    mejores = mme[mme >= mme.iloc[-1]]
    v["emae_suba_desde"] = mes(mejores.index[-2]) if len(mejores) > 1 else "el inicio de la serie"

    ia_sec = pd.Series({k: ia(d[k]).iloc[-1] for k in SECTORES})
    nombres = cat.loc[SECTORES, "nombre"]
    sube = ia_sec[ia_sec > 0].drop("s_pesca", errors="ignore")
    v["sec_suben"] = str(int((ia_sec > 0).sum()))
    v["sec_bajan"] = str(int((ia_sec < 0).sum()))
    orden = ia_sec.drop("s_pesca").sort_values()
    v["sec_peor1"] = f"{nombres[orden.index[0]].lower()} ({pct(orden.iloc[0])})"
    v["sec_peor2"] = f"{nombres[orden.index[1]].lower()} ({pct(orden.iloc[1])})"
    v["sec_peor3"] = f"{nombres[orden.index[2]].lower()} ({pct(orden.iloc[2])})"
    v["sec_mejor1"] = f"{nombres[orden.index[-1]].lower()} ({pct(orden.iloc[-1])})"
    v["sec_mejor2"] = f"{nombres[orden.index[-2]].lower()} ({pct(orden.iloc[-2])})"
    v["pesca_ia"] = pct(ia_sec["s_pesca"], 0)
    v["_ia_sec"] = ia_sec

    for k in ["ipi", "isac", "super"]:
        v[f"{k}_ia"] = pct(ia(d[k]).iloc[-1])
        v[f"{k}_acum"] = pct(ia_acum(d[k]))
        v[f"{k}_mes"] = mes(ult(d[k]))
    v["ipi_mm"] = pct(var(d["ipi_de"]).iloc[-1])

    # Precios
    p = d["ipc"]
    v["ipc_mes"] = mes(ult(p))
    v["ipc_mes_c"] = mes(ult(p), corto=True)
    v["ipc_mes_ant"] = mes(p.index[-2], anio=False)
    v["ipc_mm"] = pct(var(p).iloc[-1], signo=False)
    v["ipc_mm_ant"] = pct(var(p).iloc[-2], signo=False)
    v["ipc_ia"] = pct(ia(p).iloc[-1], signo=False)
    v["ipc_acum"] = pct(acum_anio(p).iloc[-1], signo=False)
    mm = var(p).dropna()
    menor = mm[mm <= mm.iloc[-1]]
    v["ipc_mm_minimo_desde"] = mes(menor.index[-2]) if len(menor) > 1 else "s.d."
    mayor = mm[mm >= mm.iloc[-1]]
    v["ipc_mm_maximo_desde"] = mes(mayor.index[-2]) if len(mayor) > 1 else "s.d."
    v["ipc_mm_prom3"] = pct(((p.iloc[-1] / p.iloc[-4]) ** (1 / 3) - 1) * 100, signo=False)
    v["ipc_anualizado3"] = pct(((p.iloc[-1] / p.iloc[-4]) ** 4 - 1) * 100, 0, signo=False)
    for k, n in [("ipc_nucleo", "nuc"), ("ipc_reg", "reg"), ("ipc_est", "est")]:
        v[f"{n}_mm"] = pct(var(d[k]).iloc[-1], signo=False)
        v[f"{n}_ia"] = pct(ia(d[k]).iloc[-1], signo=False)
        v[f"{n}_acum"] = pct(acum_anio(d[k]).iloc[-1], signo=False)
    v["nuc_trim"] = pct(((1 + var(d["ipc_nucleo"]).iloc[-1] / 100) ** 3 - 1) * 100, signo=False)
    v["rem12_mensual"] = pct(((1 + d["rem_ipc12"].iloc[-1] / 100) ** (1 / 12) - 1) * 100, signo=False)
    v["nuc_mm_ant"] = pct(var(d["ipc_nucleo"]).iloc[-2], signo=False)
    v["reg_vs_nuc_ia"] = num(ia(d["ipc_reg"]).iloc[-1] - ia(d["ipc_nucleo"]).iloc[-1], 1) + " p.p."
    rem = d["rem_ipc12"]
    v["rem12"] = pct(rem.iloc[-1], signo=False)
    v["rem12_mes"] = mes(ult(rem))
    hace6 = rem[:ult(rem) - pd.DateOffset(months=6)]
    v["rem12_hace6"] = pct(hace6.iloc[-1], signo=False) if len(hace6) else "s.d."
    v["rem12_hace6_mes"] = mes(hace6.index[-1], anio=False) if len(hace6) else "s.d."

    # Laboral, externo, fiscal, monetario (tablero)
    w = d["salarios"]
    v["sal_ia"] = pct(ia(w).iloc[-1], signo=False)
    v["sal_real_ia"] = pct(real(ia(w), p).iloc[-1])
    v["sal_mes"] = mes(ult(w))
    sal = (d["expo"] - d["impo"]).dropna()
    v["saldo_com"] = "US$ " + num(sal.iloc[-1], 0) + " M"
    v["saldo_com_acum"] = "US$ " + num(sal[sal.index.year == sal.index[-1].year].sum(), 0) + " M"
    v["expo_ia"] = pct(ia(d["expo"]).iloc[-1])
    v["impo_ia"] = pct(ia(d["impo"]).iloc[-1])
    v["com_mes"] = mes(ult(sal))
    rec = d["recaudacion"] * 100
    v["rec_ia"] = pct(rec.iloc[-1])
    v["rec_mes"] = mes(ult(rec))
    tc = d["tc_may"]
    tcm = mensual(tc)
    v["tc"] = "$ " + num(tc.iloc[-1], 2)
    v["tc_fecha"] = f"{tc.index[-1].day}-{MES3[tc.index[-1].month - 1]}-{str(tc.index[-1].year)[2:]}"
    v["tc_mm"] = pct(var(tcm).iloc[-2])   # último mes completo
    v["tc_ia"] = pct(ia(tcm).iloc[-2])
    v["tc_mes_completo"] = mes(tcm.index[-2])
    r = d["reservas"]
    v["reservas"] = "US$ " + num(r.iloc[-1], 0) + " M"
    v["reservas_fecha"] = f"{r.index[-1].day}-{MES3[r.index[-1].month - 1]}-{str(r.index[-1].year)[2:]}"
    v["reservas_var_mes"] = ("+" if r.iloc[-1] >= r[:r.index[-1] - pd.Timedelta(days=28)].iloc[-1] else MENOS) + \
        "US$ " + num(abs(r.iloc[-1] - r[:r.index[-1] - pd.Timedelta(days=28)].iloc[-1]), 0) + " M"
    t = d["tamar"]
    v["tamar"] = num(t.iloc[-1], 1) + "%"
    v["tamar_fecha"] = f"{t.index[-1].day}-{MES3[t.index[-1].month - 1]}-{str(t.index[-1].year)[2:]}"
    v["badlar"] = num(d["badlar"].iloc[-1], 1) + "%"
    # tasa real ex ante aproximada: TAMAR TNA -> TEA vs inflación esperada 12m
    tea = ((1 + t.iloc[-1] / 100 / 12) ** 12 - 1) * 100
    v["tamar_real"] = pct(((1 + tea / 100) / (1 + rem.iloc[-1] / 100) - 1) * 100)
    # variantes sin signo, para frases con verbo ("cayó 2,9%", no "cayó −2,9%")
    for k, x in list(v.items()):
        if isinstance(x, str) and x[:1] in ("+", MENOS):
            v[k + "_abs"] = x[1:]
    return v
