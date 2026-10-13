"""Secciones 3 a 9 del Boletín: valores para los textos y armado de gráficos y cuadros.

Cada sección tiene dos funciones:
- valores_X(c) -> dict con los marcadores {clave} de los textos (ya formateados).
- html_X(c) -> str con el cuerpo de la sección (textos + gráficos + cuadros).
`c` es el contexto de la edición (ver generar.Contexto).
"""
from __future__ import annotations

import glob
import os
import re
from pathlib import Path

import pandas as pd

import calculo as C
import graficos as G

MODELO_PIB = Path(__file__).parent.parent / "modelo_pib" / "salida"


# ---------------------------------------------------------------- utilidades
def mens(s):
    return s.resample("MS").mean().dropna()


def fin(s):
    return s.resample("MS").last().dropna()


def suma(s):
    return s.resample("MS").sum()


def al(s, t):
    """Último valor disponible al día t."""
    s = s.dropna()[:t]
    return s.iloc[-1] if len(s) else float("nan")


def fecha_c(t):
    return f"{t.day}-{C.MES3[t.month - 1]}-{str(t.year)[2:]}"


def pp(x, dec=1):
    return C.num(x, dec, True) + " p.p."


def usd_m(x, dec=0):
    return (C.MENOS if x < 0 else "") + "US$ " + C.num(abs(x), dec) + " M"


def usd_mm(x, dec=1):
    """De millones a miles de millones de dólares."""
    return (C.MENOS if x < 0 else "") + "US$ " + C.num(abs(x) / 1e3, dec) + " mil M"


def billones(x, dec=2):
    """De millones a billones de pesos. El signo va adelante ("−$ 2,88 billones") para que
    exista la variante sin signo (_abs) en los textos."""
    return (C.MENOS if x < 0 else "") + "$ " + C.num(abs(x) / 1e6, dec) + " billones"


def ipc_extendido(ipc: pd.Series, R: pd.DataFrame) -> pd.Series:
    """IPC observado, extendido con la trayectoria mensual esperada por el REM (para
    deflactar meses que el INDEC todavía no publicó)."""
    ipc = ipc.dropna().copy()
    tray = R[R.bloque.str.contains("IPC nivel general") & R.periodo.str.match(r"^\d{4}-\d{2}$")]
    for _, f in tray.sort_values("periodo").iterrows():
        t = pd.Timestamp(f.periodo + "-01")
        if t > ipc.index[-1] and t - pd.DateOffset(months=1) == ipc.index[-1]:
            ipc.loc[t] = ipc.iloc[-1] * (1 + f.mediana / 100)
    return ipc


def real_ia(s_mens: pd.Series, ipc_e: pd.Series) -> pd.Series:
    p = ipc_e.reindex(s_mens.index)
    return ((s_mens / s_mens.shift(12)) / (p / p.shift(12)) - 1) * 100


def rem(R, bloque, periodo):
    f = R[R.bloque.str.contains(bloque, regex=False) & (R.periodo == str(periodo))]
    return float(f.mediana.iloc[0]) if len(f) else None


def anio_base(hoy: pd.Timestamp) -> int:
    """Primer año de las proyecciones: el del corte del modelo (mes anterior a la edición)."""
    return (hoy.to_period("M") - 1).year


def modelo_pib(c):
    """Pronóstico del modelo propio del mes anterior a la edición
    (modelo_pib/salida/pronostico_pib_AAAA-MM.xlsx, que genera `run.py`)."""
    corte = c.hoy.to_period("M") - 1
    ruta = MODELO_PIB / f"pronostico_pib_{corte}.xlsx"
    if not ruta.exists():
        return None
    df = pd.read_excel(ruta, sheet_name="Resumen", header=None)
    fila_tit = df.index[df[0].astype(str).str.strip() == "Período"][0]
    cab = df.iloc[fila_tit].tolist()
    out = {}
    for _, f in df.iloc[fila_tit + 1:].iterrows():
        if isinstance(f[0], str):
            per = f[0].split(" (")[0]
            if "Q" in per:
                a, q = per.split("Q")
                r = rem(c.R, "PIB a precios constantes", f"Trim. {['I', 'II', 'III', 'IV'][int(q) - 1]}-{a[2:]}")
            else:
                r = rem(c.R, "PIB a precios constantes", per)
            out[per] = {"combinado": f[cab.index("COMBINADO")], "rem": r}
    return {"datos": out, "corte": corte.to_timestamp()}


def trim_txt(per: str) -> str:
    """'2026Q3' -> 'III-26'."""
    a, q = per.split("Q")
    return f"{['I', 'II', 'III', 'IV'][int(q) - 1]}-{a[2:]}"


def var_periodos(s, t):
    """Variaciones % a 1 mes, en el año y a 12 meses al día t."""
    ult = al(s, t)
    return (ult / al(s, t - pd.Timedelta(days=30)) - 1) * 100, \
           (ult / al(s, pd.Timestamp(t.year - 1, 12, 31)) - 1) * 100, \
           (ult / al(s, t - pd.Timedelta(days=365)) - 1) * 100


def dif_periodos(s, t):
    """Diferencias (en las unidades de la serie) a 1 mes, en el año y a 12 meses."""
    ult = al(s, t)
    return ult - al(s, t - pd.Timedelta(days=30)), ult - al(s, pd.Timestamp(t.year - 1, 12, 31)), \
        ult - al(s, t - pd.Timedelta(days=365))


def meses_tabla(idx_fin: pd.Timestamp, n=6):
    return pd.date_range(end=idx_fin, periods=n, freq="MS")


# ================================================================ 3. Monetario y cambiario
def valores_monetario(c) -> dict:
    d, R, hoy = c.d, c.R, c.hoy
    v = {}
    mc = (hoy.to_period("M") - 1).to_timestamp()  # último mes completo
    c.mc = mc
    ipc_e = ipc_extendido(d["ipc"], R)
    c.ipc_e = ipc_e
    v["mon_mes"] = C.mes(mc, anio=False)
    v["mon_mes_ant"] = C.mes(mc - pd.DateOffset(months=1), anio=False)
    tc, ccl, blue = d["tc_may"], d["ccl"], d["blue"]
    tcm = mens(tc)
    v["cam_a3500"] = "$ " + C.num(tc.iloc[-1], 2)
    v["cam_fecha"] = fecha_c(tc.index[-1])
    v["cam_a3500_mm"] = C.pct(C.var(tcm)[mc])
    v["cam_a3500_ytd"] = C.pct((tc.iloc[-1] / al(tc, pd.Timestamp(hoy.year - 1, 12, 31)) - 1) * 100)
    v["cam_a3500_ia"] = C.pct((tc.iloc[-1] / al(tc, hoy - pd.Timedelta(days=365)) - 1) * 100)
    v["cam_ccl"] = "$ " + C.num(ccl.iloc[-1], 0)
    v["cam_blue"] = "$ " + C.num(blue.iloc[-1], 0)
    brecha = (ccl / tc.reindex(ccl.index, method="ffill") - 1).dropna() * 100
    v["cam_brecha"] = C.pct(brecha.iloc[-1], signo=False)
    v["cam_brecha_prom"] = C.pct(mens(brecha)[mc], signo=False)
    v["cam_brecha_max12"] = C.pct(brecha[hoy - pd.Timedelta(days=365):].max(), signo=False)
    r = d["reservas"]
    rf = fin(r)
    v["res_ult"] = usd_m(r.iloc[-1])
    v["res_fecha"] = fecha_c(r.index[-1])
    v["res_var_mes"] = C.num(rf[mc] - rf[mc - pd.DateOffset(months=1)], 0, True).replace("+", "+US$ ").replace(C.MENOS, C.MENOS + "US$ ") + " M"
    v["res_var_anio"] = C.num(r.iloc[-1] - al(r, pd.Timestamp(r.index[-1].year - 1, 12, 31)), 0, True).replace("+", "+US$ ").replace(C.MENOS, C.MENOS + "US$ ") + " M"
    v["res_max"] = usd_m(r[str(r.index[-1].year)].max())
    v["res_max_fecha"] = fecha_c(r[str(r.index[-1].year)].idxmax())
    comp = suma(d["compras"])
    v["compras_mes"] = usd_m(comp[mc])
    v["compras_anio"] = usd_m(comp[str(mc.year)].sum())
    cm = comp[str(mc.year)]
    v["compras_max"] = usd_m(cm.max())
    v["compras_max_mes"] = C.mes(cm.idxmax(), anio=False)
    for k, n in [("tamar", "tamar"), ("tasa_pf", "pf"), ("tasa_pers", "pers")]:
        v[f"tasa_{n}"] = C.num(mens(d[k])[mc], 1) + "%"
    pf = mens(d["tasa_pf"])[mc]
    tea = ((1 + pf / 100 / 12) ** 12 - 1) * 100
    v["tasa_pf_real"] = C.pct(((1 + tea / 100) / (1 + d["rem_ipc12"].iloc[-1] / 100) - 1) * 100)
    for k in ["m2", "dep_priv", "prest_priv", "base"]:
        v[f"{k}_real_ia"] = C.pct(real_ia(mens(d[k]), ipc_e)[mc])
    for k in ["prest_usd", "dep_usd"]:
        v[f"{k}_ia"] = C.pct(C.ia(mens(d[k]))[mc])
        v[f"{k}_ult"] = usd_m(d[k].iloc[-1])
    v["mon_estimado"] = "sí" if mc > d["ipc"].dropna().index[-1] else "no"
    return v


def html_monetario(c) -> str:
    d, N, hoy, mc = c.d, c.N, c.hoy, c.mc
    desde = pd.Timestamp(hoy.year - 1, 1, 1)
    g_tc = G.lineas([
        {"nombre": "Mayorista (A3500)", "s": d["tc_may"][desde:], "color": "var(--s1)"},
        {"nombre": "Contado con liqui", "s": d["ccl"][desde:], "color": "var(--s2)"},
        {"nombre": "Informal", "s": d["blue"][desde:], "color": "var(--s3)"}],
        unidad="$", dec_lbl=0, titulo_aria="Tipo de cambio mayorista, CCL e informal")
    g_res = G.lineas([{"nombre": "Reservas brutas", "s": d["reservas"]["2024":], "color": "var(--s1)"}],
                     unidad="US$ M", dec_lbl=0, alto=220, titulo_aria="Reservas internacionales del BCRA")
    desde_t = max(hoy - pd.DateOffset(months=27), pd.Timestamp("2025-01-01"))  # sin el pico de 2024
    g_tasas = G.lineas([
        {"nombre": "TAMAR", "s": mens(d["tamar"])[desde_t:mc], "color": "var(--s1)"},
        {"nombre": "Plazo fijo 30 días", "s": mens(d["tasa_pf"])[desde_t:mc], "color": "var(--s2)"},
        {"nombre": "Inflación esperada (REM)", "s": mens(d["rem_ipc12"])[desde_t:], "color": "var(--s3)"}],
        titulo_aria="Tasas de interés e inflación esperada")
    meses = meses_tabla(mc)
    col = [C.mes(t, corto=True) for t in meses]
    ipc_e = c.ipc_e
    tc, ccl = d["tc_may"], d["ccl"]
    brecha = mens((ccl / tc.reindex(ccl.index, method="ffill") - 1).dropna() * 100)

    def f(s, dec=0, signo=False):
        return [C.num(s.get(t), dec, signo) for t in meses]
    filas = [
        ("Dólar mayorista <small>($/USD, prom.)</small>", f(mens(tc), 1), ""),
        ("Dólar CCL <small>($/USD, prom.)</small>", f(mens(ccl), 1), ""),
        ("Brecha CCL <small>(%, prom.)</small>", f(brecha, 1), ""),
        ("Reservas <small>(US$ M, fin de mes)</small>", f(fin(d["reservas"])), "sep-top"),
        ("Compras del BCRA <small>(US$ M en el mes)</small>", f(suma(d["compras"]), 0, True), ""),
        ("TAMAR <small>(% TNA, prom.)</small>", f(mens(d["tamar"]), 1), "sep-top"),
        ("Plazo fijo 30 días <small>(% TNA, prom.)</small>", f(mens(d["tasa_pf"]), 1), ""),
        ("M2 privado <small>(var. % real i.a.)</small>", f(real_ia(mens(d["m2"]), ipc_e), 1, True), "sep-top"),
        ("Depósitos privados en $ <small>(var. % real i.a.)</small>", f(real_ia(mens(d["dep_priv"]), ipc_e), 1, True), ""),
        ("Préstamos privados en $ <small>(var. % real i.a.)</small>", f(real_ia(mens(d["prest_priv"]), ipc_e), 1, True), ""),
        ("Préstamos en dólares <small>(var. % i.a.)</small>", f(C.ia(mens(d["prest_usd"])), 1, True), ""),
    ]
    nota = "Promedios mensuales salvo indicación."
    if mc > d["ipc"].dropna().index[-1]:
        nota += f" Variaciones reales de {C.mes(mc, corto=True)} estimadas con la inflación mensual esperada por el REM."
    return (c.M("monetario_1") + N.fig("Tipo de cambio", "Pesos por dólar, datos diarios", g_tc, c.fuente(["tc_may", "ccl", "blue"]))
            + c.M("monetario_2")
            + N.fig("Reservas internacionales del BCRA", "Millones de dólares, datos diarios", g_res, c.fuente(["reservas"]))
            + N.fig("Tasas de interés e inflación esperada", "%, promedios mensuales (tasas en TNA)", g_tasas,
                    c.fuente(["tamar", "rem_ipc12"]), "Inflación esperada: mediana del REM para los próximos 12 meses.")
            + c.M("monetario_3")
            + N.cuadro("Indicadores monetarios y cambiarios", "Datos mensuales", G_tabla(filas, col), c.fuente(["tc_may", "ccl", "ipc"]), nota)
            + c.pyme("monetario_pyme"))


# ================================================================ 4. Fiscal
REC = [("rec_iva", "IVA"), ("rec_gan", "Ganancias"), ("rec_ss", "Seguridad social"),
       ("rec_cheq", "Débitos y créditos"), ("rec_dexp", "Derechos de exportación"),
       ("rec_comb", "Combustibles"), ("rec_bp", "Bienes personales"), ("rec_total", "Total")]


def _recaudacion(d):
    out = {k: d[k] for k, _ in REC if k in d}
    out["rec_ss"] = d["rec_aport"].add(d["rec_contr"], fill_value=0)
    return out


def valores_fiscal(c) -> dict:
    d, ipc_e, hoy = c.d, c.ipc_e, c.hoy
    v = {}
    p, f, i = d["primario"].dropna(), d["financiero"].dropna(), d["intereses"].dropna()
    t = p.index[-1]
    v["fis_mes"] = C.mes(t)
    v["fis_mes_c"] = C.mes(t, anio=False)
    v["fis_prim_mes"] = billones(p.iloc[-1])
    v["fis_fin_mes"] = billones(f.iloc[-1])
    v["fis_int_mes"] = billones(i.iloc[-1])
    a = lambda s, y: s[(s.index.year == y) & (s.index.month <= t.month)]
    v["fis_prim_acum"] = billones(a(p, t.year).sum())
    v["fis_fin_acum"] = billones(a(f, t.year).sum())
    v["fis_int_acum"] = billones(a(i, t.year).sum())
    real = lambda s: s * ipc_e[t] / ipc_e.reindex(s.index)
    v["fis_prim_acum_real_var"] = C.pct((a(real(p), t.year).sum() / a(real(p), t.year - 1).sum() - 1) * 100)
    v["fis_fin_acum_ant"] = billones(a(f, t.year - 1).sum())
    neg = p[str(t.year)][p[str(t.year)] < 0]
    v["fis_meses_def"] = ", ".join(C.mes(x, anio=False) for x in neg.index) if len(neg) else "ninguno"
    prim12 = real(p).rolling(12).sum()
    v["fis_prim12_real"] = billones(prim12.iloc[-1])
    v["fis_prim12_real_hace12"] = billones(prim12.iloc[-13])
    # recaudación
    rec = _recaudacion(d)
    tr = rec["rec_total"].dropna().index[-1]
    v["rec_mes2"] = C.mes(tr, anio=False)
    v["rec_mes2_largo"] = C.mes(tr)
    ria = {k: real_ia(s.dropna(), ipc_e).get(tr) for k, s in rec.items()}
    c.rec_ria = ria
    c.rec_t = tr
    v["rec_total_real_ia"] = C.pct(ria["rec_total"])
    tot = rec["rec_total"].dropna()
    acum = lambda y: (tot * ipc_e[tr] / ipc_e.reindex(tot.index))[(tot.index.year == y) & (tot.index.month <= tr.month)].sum()
    v["rec_acum_real_ia"] = C.pct((acum(tr.year) / acum(tr.year - 1) - 1) * 100)
    orden = sorted([(ria[k], n) for k, n in REC if k != "rec_total" and ria.get(k) is not None])
    v["rec_mejor"] = f"{orden[-1][1]} ({C.pct(orden[-1][0])})"
    v["rec_mejor2"] = f"{orden[-2][1]} ({C.pct(orden[-2][0])})"
    v["rec_peor"] = f"{orden[0][1]} ({C.pct(orden[0][0])})"
    v["rec_peor2"] = f"{orden[1][1]} ({C.pct(orden[1][0])})"
    v["rec_iva_real_ia"] = C.pct(ria["rec_iva"])
    v["rec_gan_real_ia"] = C.pct(ria["rec_gan"])
    v["rec_estimado"] = "sí" if tr > d["ipc"].dropna().index[-1] else "no"
    return v


def html_fiscal(c) -> str:
    d, N, ipc_e = c.d, c.N, c.ipc_e
    p, f = d["primario"].dropna(), d["financiero"].dropna()
    t = p.index[-1]
    real = lambda s: s * ipc_e[t] / ipc_e.reindex(s.index)
    desde = t - pd.DateOffset(months=33)
    g12 = G.lineas([
        {"nombre": "Resultado primario", "s": (real(p).rolling(12).sum() / 1e6)[desde:], "color": "var(--s1)"},
        {"nombre": "Resultado financiero", "s": (real(f).rolling(12).sum() / 1e6)[desde:], "color": "var(--s2)"}],
        unidad="billones", dec_lbl=1, cero=True, titulo_aria="Resultado fiscal acumulado en 12 meses")
    ria = c.rec_ria
    pares = sorted([(n, ria[k]) for k, n in REC if ria.get(k) is not None], key=lambda x: -x[1])
    g_rec = G.barras_h([n for n, _ in pares], [x for _, x in pares], titulo_aria="Recaudación por impuesto, var. real i.a.", ml=190)
    meses = meses_tabla(t)
    col = [C.mes(x, corto=True) for x in meses] + [f"Ene–{C.MES3[t.month - 1]} {t.year}", f"Ene–{C.MES3[t.month - 1]} {t.year - 1}"]
    a = lambda s, y: s[(s.index.year == y) & (s.index.month <= t.month)].sum()

    def fila(s, nombre, cls=""):
        vals = [C.num(s.get(x, float("nan")) / 1e6, 2) for x in meses] + [C.num(a(s, t.year) / 1e6, 2), C.num(a(s, t.year - 1) / 1e6, 2)]
        return (nombre, vals, cls)
    filas = [fila(p, "Resultado primario"), fila(d["intereses"].dropna(), "Intereses netos", "sub"),
             fila(f, "Resultado financiero", "tot")]
    sub_rec = f"Variación % real interanual, {C.mes(c.rec_t)}"
    nota_rec = "Seguridad social: aportes personales y contribuciones patronales."
    if c.rec_t > d["ipc"].dropna().index[-1]:
        nota_rec += " Deflactado con la inflación esperada por el REM para el mes."
    return (c.M("fiscal_1")
            + N.fig("Resultado fiscal del Sector Público Nacional", f"Acumulado 12 meses, billones de pesos de {C.mes(t, corto=True)}",
                    g12, c.fuente(["primario"]), "Base caja. Valores deflactados por el IPC.")
            + c.M("fiscal_2")
            + N.fig("Recaudación tributaria por impuesto", sub_rec, g_rec, c.fuente(["rec_total", "ipc"]), nota_rec)
            + N.cuadro("Resultado fiscal del Sector Público Nacional", "Billones de pesos corrientes, base caja", G_tabla(filas, col, sep=6),
                       c.fuente(["primario"]))
            + c.pyme("fiscal_pyme"))


# ================================================================ 5. Externo
X_RUB = [("x_pp", "Productos primarios"), ("x_moa", "Manufacturas agropecuarias"),
         ("x_moi", "Manufacturas industriales"), ("x_cye", "Combustibles y energía")]
M_RUB = [("m_bk", "Bienes de capital"), ("m_bi", "Bienes intermedios"), ("m_cyl", "Combustibles y lubricantes"),
         ("m_pzas", "Piezas y accesorios"), ("m_bc", "Bienes de consumo"), ("m_auto", "Vehículos de pasajeros")]


def valores_externo(c) -> dict:
    d, R = c.d, c.R
    v = {}
    x, m = d["expo"].dropna(), d["impo"].dropna()
    t = x.index[-1]
    s = x - m
    v["ext_mes"] = C.mes(t)
    v["ext_mes_c"] = C.mes(t, anio=False)
    v["ext_expo"] = usd_m(x.iloc[-1])
    v["ext_impo"] = usd_m(m.iloc[-1])
    v["ext_saldo"] = usd_m(s.iloc[-1])
    v["ext_saldo_ant"] = usd_m(s.iloc[-13])
    v["ext_expo_ia"] = C.pct(C.ia(x).iloc[-1])
    v["ext_impo_ia"] = C.pct(C.ia(m).iloc[-1])
    a = lambda z, y: z[(z.index.year == y) & (z.index.month <= t.month)].sum()
    v["ext_expo_acum"] = usd_mm(a(x, t.year))
    v["ext_impo_acum"] = usd_mm(a(m, t.year))
    v["ext_saldo_acum"] = usd_mm(a(s, t.year))
    v["ext_saldo_acum_ant"] = usd_mm(a(s, t.year - 1))
    v["ext_expo_acum_ia"] = C.pct(C.ia_acum(x))
    v["ext_impo_acum_ia"] = C.pct(C.ia_acum(m))
    v["ext_expo_12m"] = usd_mm(x.iloc[-12:].sum())
    v["ext_saldo_12m"] = usd_mm(s.iloc[-12:].sum())
    rub = {n: C.ia_acum(d[k].dropna()) for k, n in X_RUB}
    c.ext_x = rub
    o = sorted(rub.items(), key=lambda z: z[1])
    v["ext_x_mejor"] = f"{o[-1][0].lower()} ({C.pct(o[-1][1])})"
    v["ext_x_peor"] = f"{o[0][0].lower()} ({C.pct(o[0][1])})"
    v["ext_cye_part"] = C.pct(a(d["x_cye"], t.year) / a(x, t.year) * 100, signo=False)
    v["ext_cye_part_ant"] = C.pct(a(d["x_cye"], t.year - 1) / a(x, t.year - 1) * 100, signo=False)
    rubm = {n: C.ia_acum(d[k].dropna()) for k, n in M_RUB}
    c.ext_m = rubm
    om = sorted(rubm.items(), key=lambda z: z[1])
    v["ext_m_mejor"] = f"{om[-1][0].lower()} ({C.pct(om[-1][1])})"
    v["ext_m_peor"] = f"{om[0][0].lower()} ({C.pct(om[0][1])})"
    e26, i26 = rem(R, "Exportaciones", t.year), rem(R, "Importaciones", t.year)
    v["rem_expo_anio"] = usd_mm(e26) if e26 else "s.d."
    v["rem_impo_anio"] = usd_mm(i26) if i26 else "s.d."
    v["rem_saldo_anio"] = usd_mm(e26 - i26) if e26 and i26 else "s.d."
    return v


def html_externo(c) -> str:
    d, N = c.d, c.N
    x, m = d["expo"].dropna(), d["impo"].dropna()
    t = x.index[-1]
    desde = pd.Timestamp(t.year - 4, 12, 1)
    g12 = G.lineas([
        {"nombre": "Exportaciones", "s": (x.rolling(12).sum() / 1e3)[desde:], "color": "var(--s1)"},
        {"nombre": "Importaciones", "s": (m.rolling(12).sum() / 1e3)[desde:], "color": "var(--s2)"}],
        unidad="US$ mil M", dec_lbl=1, titulo_aria="Exportaciones e importaciones acumuladas 12 meses")
    cats = [f"Expo · {n}" for n in c.ext_x] + [f"Impo · {n}" for n in c.ext_m]
    vals = list(c.ext_x.values()) + list(c.ext_m.values())
    g_rub = G.barras_h(cats, vals, titulo_aria="Comercio exterior por rubro y uso", ml=250)
    meses = meses_tabla(t)
    col = [C.mes(z, corto=True) for z in meses] + ["Acum. año"]
    a = lambda z, y: z[(z.index.year == y) & (z.index.month <= t.month)].sum()
    s = x - m
    filas = [
        ("Exportaciones <small>(US$ M)</small>", [C.num(x.get(z), 0) for z in meses] + [C.num(a(x, t.year), 0)], ""),
        ("Importaciones <small>(US$ M)</small>", [C.num(m.get(z), 0) for z in meses] + [C.num(a(m, t.year), 0)], ""),
        ("Saldo comercial <small>(US$ M)</small>", [C.num(s.get(z), 0, True) for z in meses] + [C.num(a(s, t.year), 0, True)], "tot"),
        ("Exportaciones <small>(var. % i.a.)</small>", [C.num(C.ia(x).get(z), 1, True) for z in meses] + [C.num(C.ia_acum(x), 1, True)], "sub sep-top"),
        ("Importaciones <small>(var. % i.a.)</small>", [C.num(C.ia(m).get(z), 1, True) for z in meses] + [C.num(C.ia_acum(m), 1, True)], "sub"),
    ]
    return (c.M("externo_1")
            + N.fig("Exportaciones e importaciones de bienes", "Acumulado 12 meses, miles de millones de dólares", g12, c.fuente(["expo"]))
            + c.M("externo_2")
            + N.fig(f"Comercio exterior por rubro y uso, enero–{C.mes(t, anio=False)} {t.year}",
                    "Variación % interanual del acumulado del año", g_rub, c.fuente(["expo"]))
            + N.cuadro("Intercambio comercial argentino", "Millones de dólares y variación %", G_tabla(filas, col, sep=6), c.fuente(["expo"]))
            + c.pyme("externo_pyme"))


# ================================================================ 6. Laboral y social
# El índice de no registrados se excluye: según la nota metodológica del INDEC refleja salarios
# de 5 meses antes (promedios trimestrales móviles de la EPH), así que no es comparable con el IPC del mes.
SAL = [("sal_priv", "Registrado privado"), ("sal_pub", "Registrado público")]


def valores_laboral(c) -> dict:
    d = c.d
    v = {}
    ipc = d["ipc"]
    t = d["sal_priv"].dropna().index[-1]
    v["lab_sal_mes"] = C.mes(t)
    for k, _ in SAL:
        s = d[k].dropna()
        v[f"{k}_real_ia"] = C.pct(C.real(C.ia(s), ipc).iloc[-1])
        r = s / ipc.reindex(s.index)
        v[f"{k}_vs_dic23"] = C.pct((r.iloc[-1] / r["2023-12"].iloc[0] - 1) * 100)
    sp = d["sipa_priv"].dropna()
    ts = sp.index[-1]
    v["sipa_mes"] = C.mes(ts)
    v["sipa_priv"] = C.num(sp.iloc[-1], 0) + " mil"
    dif = sp.iloc[-1] - sp.iloc[-13]
    v["sipa_priv_var12"] = C.num(dif, 0, True) + " mil"
    v["sipa_priv_var12_abs"] = C.num(abs(dif), 0) + " mil"
    v["sipa_priv_var12_pct"] = C.pct((sp.iloc[-1] / sp.iloc[-13] - 1) * 100)
    pico = sp["2023":].idxmax()
    v["sipa_pico_mes"] = C.mes(pico)
    v["sipa_desde_pico"] = C.num(sp.iloc[-1] - sp[pico], 0, True) + " mil"
    v["sipa_desde_pico_abs"] = C.num(abs(sp.iloc[-1] - sp[pico]), 0) + " mil"
    caidas = (sp.diff() < 0)[-12:].sum()
    v["sipa_meses_caida"] = str(int(caidas))
    de = d["eph_desoc"].dropna() * 100
    tq = de.index[-1]
    q = lambda t_: f"{['I', 'II', 'III', 'IV'][(t_.month - 1) // 3]}-{str(t_.year)[2:]}"
    c.q = q
    v["eph_trim"] = q(tq)
    v["eph_trim_largo"] = f"{['primer', 'segundo', 'tercer', 'cuarto'][(tq.month - 1) // 3]} trimestre de {tq.year}"
    v["eph_desoc"] = C.num(de.iloc[-1], 1) + "%"
    v["eph_desoc_ant"] = C.num(de.iloc[-5], 1) + "%"
    v["eph_desoc_trim_ant"] = C.num(de.iloc[-2], 1) + "%"
    v["eph_empleo"] = C.num(d["eph_empleo"].dropna().iloc[-1] * 100, 1) + "%"
    v["eph_activ"] = C.num(d["eph_activ"].dropna().iloc[-1] * 100, 1) + "%"
    pob = d["pobreza"].dropna()
    sem = lambda t_: f"{'primer' if t_.month == 1 else 'segundo'} semestre de {t_.year}"
    v["pob_ult"] = C.num(pob.iloc[-1], 1) + "%"
    v["pob_sem"] = sem(pob.index[-1])
    v["pob_ant"] = C.num(pob.iloc[-2], 1) + "%"
    v["pob_sem_ant"] = sem(pob.index[-2])
    v["pob_hace1"] = C.num(pob.iloc[-3], 1) + "%"
    v["pob_var"] = pp(pob.iloc[-1] - pob.iloc[-2])
    v["pob_min"] = C.num(pob["2017":].min(), 1) + "%"
    v["pob_min_sem"] = sem(pob["2017":].idxmin())
    return v


def html_laboral(c) -> str:
    d, N = c.d, c.N
    ipc = d["ipc"]
    series = []
    for (k, n), col in zip(SAL, ["var(--s1)", "var(--s2)", "var(--s3)"]):
        s = d[k].dropna()
        r = s / ipc.reindex(s.index)
        r = r / r["2023-12"].iloc[0] * 100
        series.append({"nombre": n, "s": r["2023-12":], "color": col})
    g_sal = G.lineas(series, unidad="índice", dec_lbl=1, titulo_aria="Salario real por sector")
    sp = d["sipa_priv"].dropna()
    g_sipa = G.lineas([{"nombre": "Asalariados privados", "s": sp["2022":], "color": "var(--s1)"}],
                      unidad="miles", dec_lbl=0, alto=220, titulo_aria="Empleo asalariado registrado privado")
    pob = d["pobreza"].dropna()["2016-07":]
    g_pob = G.columnas(pob, unidad="%", alto=200, nombre="Pobreza (personas)",
                       etiqueta_x=lambda t: f"{'1S' if t.month == 1 else '2S'}-{str(t.year)[2:]}" if t.month == 1 or t == pob.index[-1] else None,
                       titulo_aria="Pobreza en personas por semestre")
    trims = (d["eph_desoc"].dropna().index[-5:])
    col = [c.q(t) for t in trims]
    filas = [(n, [C.num(d[k].get(t) * 100, 1) for t in trims], cls) for k, n, cls in
             [("eph_activ", "Tasa de actividad", ""), ("eph_empleo", "Tasa de empleo", ""), ("eph_desoc", "Tasa de desocupación", "tot")]]
    return (c.M("laboral_1")
            + N.fig("Salario real por sector", "Índice diciembre 2023 = 100, deflactado por el IPC", g_sal, c.fuente(["salarios"]),
                    "Sector registrado. No incluye el índice de salarios no registrados, que refleja con 5 meses de rezago.")
            + c.M("laboral_2")
            + N.fig("Empleo asalariado registrado en el sector privado", "Miles de personas, serie sin estacionalidad", g_sipa,
                    "Axia en base a datos del SIPA (Ministerio de Capital Humano)")
            + N.cuadro("Principales tasas del mercado de trabajo", "% de la población, 31 aglomerados urbanos", G_tabla(filas, col),
                       c.fuente(["eph_desoc"]))
            + c.M("laboral_3")
            + N.fig("Pobreza", "% de personas bajo la línea de pobreza, 31 aglomerados urbanos", g_pob, c.fuente(["pobreza"]))
            + c.pyme("laboral_pyme"))


# ================================================================ 7. Internacional
INTL = [("fed", "Tasa de fondos federales", "tasa"), ("ust2", "Tesoro EE.UU. 2 años", "tasa"),
        ("ust10", "Tesoro EE.UU. 10 años", "tasa"), ("dxy", "Índice dólar (DXY)", "px"),
        ("eurusd", "Euro (USD por EUR)", "px"), ("brl", "Real (BRL por USD)", "px"),
        ("spx", "S&P 500", "px"), ("bvsp", "Bovespa", "px"), ("soja", "Soja (USc/bu)", "px"),
        ("maiz", "Maíz (USc/bu)", "px"), ("trigo", "Trigo (USc/bu)", "px"), ("brent", "Petróleo Brent (USD/bbl)", "px"),
        ("oro", "Oro (USD/oz)", "px")]


def valores_internacional(c) -> dict:
    d, hoy = c.d, c.hoy
    v = {}
    for k, _, tipo in INTL:
        s = d[k].dropna()
        v[f"i_{k}"] = C.num(s.iloc[-1], 2 if tipo == "tasa" or s.iloc[-1] < 10 else (1 if s.iloc[-1] < 1000 else 0)) + ("%" if tipo == "tasa" else "")
        if tipo == "tasa":
            m1, ytd, a12 = dif_periodos(s, hoy)
            v[f"i_{k}_ytd"], v[f"i_{k}_12m"], v[f"i_{k}_1m"] = pp(ytd, 2), pp(a12, 2), pp(m1, 2)
        else:
            m1, ytd, a12 = var_periodos(s, hoy)
            v[f"i_{k}_ytd"], v[f"i_{k}_12m"], v[f"i_{k}_1m"] = C.pct(ytd), C.pct(a12), C.pct(m1)
    curva = d["ust10"].dropna().iloc[-1] - d["ust2"].dropna().iloc[-1]
    v["i_pendiente"] = pp(curva, 2)
    return v


def html_internacional(c) -> str:
    d, N, hoy = c.d, c.N, c.hoy
    desde = pd.Timestamp(hoy.year - 2, 1, 1)
    g_tasas = G.lineas([
        {"nombre": "Fondos federales", "s": d["fed"][desde:], "color": "var(--s1)"},
        {"nombre": "Tesoro 2 años", "s": d["ust2"][desde:], "color": "var(--s2)"},
        {"nombre": "Tesoro 10 años", "s": d["ust10"][desde:], "color": "var(--s3)"}],
        dec_lbl=2, titulo_aria="Tasas de interés de Estados Unidos")
    base = pd.Timestamp(hoy.year - 1, 12, 31)
    desde_c = pd.Timestamp(hoy.year - 1, 1, 1)
    com = []
    for (k, n), col in zip([("soja", "Soja"), ("maiz", "Maíz"), ("trigo", "Trigo"), ("brent", "Petróleo Brent")],
                           ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"]):
        s = d[k].dropna()
        com.append({"nombre": n, "s": (s / al(s, base) * 100)[desde_c:], "color": col})
    g_com = G.lineas(com, unidad="índice", dec_lbl=0, titulo_aria="Precios de commodities")
    filas = []
    for k, n, tipo in INTL:
        s = d[k].dropna()
        if tipo == "tasa":
            vs = dif_periodos(s, hoy)
            vals = [C.num(s.iloc[-1], 2)] + [C.num(x, 2, True) for x in vs]
        else:
            vs = var_periodos(s, hoy)
            vals = [C.num(s.iloc[-1], 2 if s.iloc[-1] < 10 else (1 if s.iloc[-1] < 1000 else 0))] + [C.num(x, 1, True) for x in vs]
        cls = "sep-top" if k in ("dxy", "spx", "soja") else ""
        filas.append((n, vals, cls))
    return (c.M("internacional_1")
            + N.fig("Tasas de interés de Estados Unidos", "%, datos diarios", g_tasas, c.fuente(["fed"]))
            + c.M("internacional_2")
            + N.fig("Precios internacionales de commodities", f"Índice 31-dic-{str(hoy.year - 1)[2:]} = 100, datos diarios", g_com,
                    "Axia en base a datos de CME Group y ICE (vía Yahoo Finance)")
            + N.cuadro("Mercados internacionales", f"Último dato al {C.fecha_larga(hoy)}",
                       G_tabla(filas, ["Último", "Var. 1 mes", "Var. en el año", "Var. 12 meses"]),
                       "Axia en base a datos de la Reserva Federal (FRED) y Yahoo Finance",
                       "Tasas: variaciones en puntos porcentuales. Resto: variaciones %.")
            + c.pyme("internacional_pyme"))


# ================================================================ 8. Mercados
ACC = ["a_ggal", "a_ypf", "a_pamp", "a_bma", "a_txar", "a_alua", "a_cepu", "a_tgs", "a_loma", "a_bbar", "a_teco", "a_supv"]


def en_ccl(s, ccl):
    return (s / ccl.reindex(s.index, method="ffill")).dropna()


def valores_mercados(c) -> dict:
    d, hoy = c.d, c.hoy
    v = {}
    r = d["riesgo"].dropna()
    v["riesgo"] = C.num(r.iloc[-1], 0) + " pb"
    v["riesgo_fecha"] = fecha_c(r.index[-1])
    m1, ytd, a12 = dif_periodos(r, hoy)
    v["riesgo_1m"] = C.num(m1, 0, True) + " pb"
    v["riesgo_ytd"] = C.num(ytd, 0, True) + " pb"
    anio = r[str(r.index[-1].year)]
    v["riesgo_min"] = C.num(anio.min(), 0) + " pb"
    v["riesgo_min_fecha"] = fecha_c(anio.idxmin())
    v["riesgo_desde_min"] = C.num(r.iloc[-1] - anio.min(), 0, True) + " pb"
    mu = en_ccl(d["merval"].dropna(), d["ccl"])
    v["merval_usd"] = "US$ " + C.num(mu.iloc[-1], 0)
    m1, ytd, a12 = var_periodos(mu, hoy)
    v["merval_usd_1m"], v["merval_usd_ytd"], v["merval_usd_12m"] = C.pct(m1), C.pct(ytd), C.pct(a12)
    v["merval_usd_max"] = "US$ " + C.num(mu["2023":].max(), 0)
    v["merval_usd_max_fecha"] = C.mes(mu["2023":].idxmax())
    m1, ytd, a12 = var_periodos(d["merval"].dropna(), hoy)
    v["merval_ars_ytd"] = C.pct(ytd)
    rend = {}
    for k in ACC:
        if k in d:
            rend[k] = var_periodos(en_ccl(d[k].dropna(), d["ccl"]), hoy)
    c.rend = rend
    cat = c.cat
    o = sorted(rend.items(), key=lambda z: z[1][1])
    v["acc_mejor"] = f"{cat.loc[o[-1][0], 'nombre']} ({C.pct(o[-1][1][1])})"
    v["acc_peor"] = f"{cat.loc[o[0][0], 'nombre']} ({C.pct(o[0][1][1])})"
    v["acc_suben_ytd"] = str(sum(1 for x in rend.values() if x[1] > 0))
    v["acc_total"] = str(len(rend))
    return v


def html_mercados(c) -> str:
    d, N, hoy = c.d, c.N, c.hoy
    r = d["riesgo"].dropna()
    g_r = G.lineas([{"nombre": "Riesgo país", "s": r[pd.Timestamp(hoy.year - 2, 1, 1):], "color": "var(--s1)"}],
                   unidad="pb", dec_lbl=0, alto=220, titulo_aria="Riesgo país")
    mu = en_ccl(d["merval"].dropna(), d["ccl"])
    g_m = G.lineas([{"nombre": "Merval en dólares", "s": mu[pd.Timestamp(hoy.year - 3, 1, 1):], "color": "var(--s1)"}],
                   unidad="US$", dec_lbl=0, alto=220, titulo_aria="S&P Merval en dólares CCL")
    filas = []
    for k, (m1, ytd, a12) in sorted(c.rend.items(), key=lambda z: -z[1][1]):
        tk = c.cat.loc[k, "id"].replace(".BA", "")
        filas.append((f"{c.cat.loc[k, 'nombre']} <small>({tk})</small>",
                      [C.num(d[k].dropna().iloc[-1], 0), C.num(m1, 1, True), C.num(ytd, 1, True), C.num(a12, 1, True)], ""))
    return (c.M("mercados_1")
            + N.fig("Riesgo país", "Puntos básicos (EMBI Argentina), datos diarios", g_r,
                    "Axia en base a datos de JP Morgan (vía ArgentinaDatos)")
            + c.M("mercados_2")
            + N.fig("S&P Merval en dólares", "Índice convertido al dólar contado con liquidación", g_m,
                    "Axia en base a datos de BYMA y ArgentinaDatos")
            + N.cuadro("Acciones líderes", "Precio en pesos y rendimiento % en dólares CCL",
                       G_tabla(filas, ["Precio ($)", "1 mes", "En el año", "12 meses"]),
                       "Axia en base a datos de BYMA (vía Yahoo Finance) y ArgentinaDatos",
                       "Precios ajustados por dividendos y splits. Ordenado por rendimiento en el año.")
            + c.pyme("mercados_pyme"))


# ================================================================ 9. Proyecciones
REM_TABLA = [("PIB a precios constantes", "PIB <small>(var. % real)</small>", 1, 1),
             ("IPC nivel general", "Inflación <small>(% dic./dic.)</small>", 1, 1),
             ("IPC núcleo", "Inflación núcleo <small>(% dic./dic.)</small>", 1, 1),
             ("Tipo de cambio nominal", "Dólar mayorista <small>($/USD, dic.)</small>", 0, 1),
             ("Tasa de interés (TAMAR)", "TAMAR <small>(% TNA, dic.)</small>", 1, 1),
             ("Exportaciones", "Exportaciones <small>(US$ mil M)</small>", 1, 1e3),
             ("Importaciones", "Importaciones <small>(US$ mil M)</small>", 1, 1e3),
             ("Resultado Primario del SPNF", "Resultado primario SPNF <small>($ billones)</small>", 1, 1e3),
             ("Desocupación abierta", "Desocupación <small>(%, prom. anual)</small>", 1, 1)]


def valores_proyecciones(c) -> dict:
    R, hoy = c.R, c.hoy
    v = {}
    tit = R.titulo.iloc[0] if "titulo" in R and len(R) else ""
    m = re.search(r"-\s*([A-Za-zé]+)\s+(\d{4})\s*$", tit)
    v["rem_edicion"] = f"{m[1].lower()} de {m[2]}" if m else "último disponible"
    y = anio_base(hoy)
    for b, k in [("PIB a precios constantes", "pib"), ("IPC nivel general", "ipc"), ("IPC núcleo", "nuc"),
                 ("Tipo de cambio nominal", "tc"), ("Tasa de interés (TAMAR)", "tamar"), ("Desocupación abierta", "desoc")]:
        for a in (y, y + 1):
            x = rem(R, b, a)
            dec = 0 if k == "tc" else 1
            v[f"rem_{k}_{a}"] = ("$ " if k == "tc" else "") + C.num(x, dec) + ("" if k == "tc" else "%") if x is not None else "s.d."
    for a in (y, y + 1):
        p = rem(R, "Resultado Primario", a)
        v[f"rem_prim_{a}"] = "$ " + C.num(p / 1e3, 1) + " billones" if p else "s.d."
        e, i = rem(R, "Exportaciones", a), rem(R, "Importaciones", a)
        v[f"rem_saldo_{a}"] = usd_mm(e - i) if e and i else "s.d."
    for k in list(v):   # alias genéricos por año: _a1 (año base) y _a2 (año siguiente)
        for sufijo, anio in (("_a1", y), ("_a2", y + 1)):
            if k.endswith(f"_{anio}"):
                v[k[: -len(str(anio)) - 1] + sufijo] = v[k]
    v["anio1"], v["anio2"] = str(y), str(y + 1)
    v["rem_ipc12"] = C.num(c.d["rem_ipc12"].iloc[-1], 1) + "%"
    v["rem_ipc24"] = C.num(rem(R, "IPC nivel general", "próx. 24 meses") or float("nan"), 1) + "%"
    tray = R[R.bloque.str.contains("IPC nivel general") & R.periodo.str.match(r"^\d{4}-\d{2}$")].sort_values("periodo")
    ult_obs = c.d["ipc"].dropna().index[-1]
    fut = tray[tray.periodo > ult_obs.strftime("%Y-%m")]
    v["rem_ipc_prox"] = C.num(fut.mediana.iloc[0], 1) + "%" if len(fut) else "s.d."
    v["rem_ipc_prox_mes"] = C.mes(pd.Timestamp(fut.periodo.iloc[0] + "-01"), anio=False) if len(fut) else "s.d."
    v["rem_ipc_fin_tray"] = C.num(fut.mediana.iloc[-1], 1) + "%" if len(fut) else "s.d."
    v["rem_ipc_fin_tray_mes"] = C.mes(pd.Timestamp(fut.periodo.iloc[-1] + "-01")) if len(fut) else "s.d."
    mp = modelo_pib(c)
    c.modelo = mp
    if mp:
        D = mp["datos"]
        trims = [k for k in D if "Q" in k]
        v["mod_corte"] = C.mes(mp["corte"])
        v["mod_trim1"] = trim_txt(trims[0])
        v["mod_trim2"] = trim_txt(trims[1])
        v["mod_q1"] = C.pct(D[trims[0]]["combinado"])
        v["mod_q2"] = C.pct(D[trims[1]]["combinado"])
        v["rem_q1"] = C.pct(D[trims[0]]["rem"])
        v["rem_q2"] = C.pct(D[trims[1]]["rem"])
        v["mod_anio"] = C.pct(D[str(y)]["combinado"])
        v["mod_anio2"] = C.pct(D[str(y + 1)]["combinado"])
        v["mod_vs_rem_anio"] = pp(D[str(y)]["combinado"] - rem(R, "PIB a precios constantes", y))
    return v


def html_proyecciones(c) -> str:
    d, R, N, hoy = c.d, c.R, c.N, c.hoy
    y = anio_base(hoy)
    partes = [c.M("proyecciones_1")]
    if c.modelo:
        D = c.modelo["datos"]
        trims = [k for k in D if "Q" in k][:2]
        cats = [f"{trim_txt(t)} (t/t)" for t in trims] + [str(y), str(y + 1)]
        mod = [D[t]["combinado"] for t in trims] + [D[str(y)]["combinado"], D[str(y + 1)]["combinado"]]
        remv = [D[t]["rem"] for t in trims] + [rem(R, "PIB a precios constantes", y), rem(R, "PIB a precios constantes", y + 1)]
        remv = [None if (x is None or pd.isna(x)) else float(x) for x in remv]
        g = G.columnas_grupo(cats, [{"nombre": "Modelo Axia", "v": [float(x) for x in mod], "color": "var(--s1)"},
                                    {"nombre": "REM (mediana)", "v": remv, "color": "var(--s2)"}],
                             titulo_aria="Pronósticos del PIB: modelo Axia y REM")
        partes.append(N.fig("Pronósticos de crecimiento del PIB", "Var. % trimestral desestacionalizada y var. % anual",
                            g, "Axia en base a modelo propio y REM del BCRA",
                            f"Modelo Axia: combinación de modelos autorregresivo, puente con el EMAE y de factores dinámicos (corte {C.mes(c.modelo['corte'], corto=True)})."))
    obs = C.var(d["ipc"]).dropna()[-13:]
    tray = R[R.bloque.str.contains("IPC nivel general") & R.periodo.str.match(r"^\d{4}-\d{2}$")].sort_values("periodo")
    fut = pd.Series({pd.Timestamp(p + "-01"): m for p, m in zip(tray.periodo, tray.mediana)})
    fut = fut[fut.index > obs.index[-1]]
    fut = pd.concat([obs.iloc[-1:], fut])
    g_ipc = G.lineas([{"nombre": "Observado", "s": obs, "color": "var(--s1)", "etiqueta": False},
                      {"nombre": "Esperado (REM)", "s": fut, "color": "var(--s2)", "dash": True}],
                     titulo_aria="Inflación mensual observada y esperada", leyenda=True)
    partes.append(c.M("proyecciones_2"))
    partes.append(N.fig("Inflación mensual: observada y esperada", "IPC nacional, var. % mensual", g_ipc,
                        "Axia en base a datos de INDEC y REM del BCRA", "Esperada: mediana del REM."))
    filas = []
    for b, n, dec, div in REM_TABLA:
        vals = []
        for a in (y, y + 1):
            x = rem(R, b, a)
            vals.append(C.num(x / div, dec) if x is not None else "s.d.")
        filas.append((n, vals, ""))
    e = [rem(R, "Exportaciones", a) for a in (y, y + 1)]
    i = [rem(R, "Importaciones", a) for a in (y, y + 1)]
    filas.insert(7, ("Saldo comercial <small>(US$ mil M)</small>", [C.num((a - b) / 1e3, 1) if a and b else "s.d." for a, b in zip(e, i)], "sub"))
    if c.modelo:
        D = c.modelo["datos"]
        filas.insert(1, ("PIB · Modelo Axia <small>(var. % real)</small>", [C.num(D[str(y)]["combinado"], 1), C.num(D[str(y + 1)]["combinado"], 1)], "sub"))
    partes.append(N.cuadro("Expectativas macroeconómicas", f"Mediana del REM del BCRA ({c.v['rem_edicion']})",
                           G_tabla(filas, [str(y), str(y + 1)]), "Axia en base a REM del BCRA y modelo propio"))
    partes.append(c.pyme("proyecciones_pyme"))
    return "".join(partes)


# ---------------------------------------------------------------- tabla
def G_tabla(filas, columnas, sep=None):
    """Cuadro estándar. `columnas` son solo las de datos; `sep` (índice de columna de datos)
    agrega un separador vertical antes de esa columna."""
    grupos = {sep + 1: "sep"} if sep is not None else {}
    th = "".join(f'<th class="{grupos.get(i, "")}">{x}</th>' for i, x in enumerate([""] + list(columnas)))
    trs = []
    for et, vals, cls in filas:
        tds = "".join(f'<td class="{grupos.get(i + 1, "")}">{x}</td>' for i, x in enumerate(vals))
        trs.append(f'<tr class="{cls}"><th scope="row">{et}</th>{tds}</tr>')
    return f'<table><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table>'


SECCIONES = [
    ("monetario", "Monetario y cambiario", valores_monetario, html_monetario),
    ("fiscal", "Fiscal", valores_fiscal, html_fiscal),
    ("externo", "Sector externo", valores_externo, html_externo),
    ("laboral", "Laboral y social", valores_laboral, html_laboral),
    ("internacional", "Internacional", valores_internacional, html_internacional),
    ("mercados", "Mercados", valores_mercados, html_mercados),
    ("proyecciones", "Proyecciones", valores_proyecciones, html_proyecciones),
]
