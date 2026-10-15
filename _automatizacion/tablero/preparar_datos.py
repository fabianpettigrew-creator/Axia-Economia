"""Datos del tablero web de AXIA: toma el último vintage del Boletín y escribe demo/datos.js.

    py preparar_datos.py
    py preparar_datos.py --sitio "B:/Onedrive/Logos/Fabian Pettigrew/Sitio web AXIA"   # además lo copia a <sitio>/tablero/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "boletin"))
import calculo as C  # noqa: E402
import datos  # noqa: E402
import secciones as SB  # noqa: E402  (funciones del boletín: real_ia, ipc_extendido, etc.)
from g20_ultimos import ultimos as g20_ultimos  # noqa: E402


def serie(s: pd.Series, dec=2):
    s = s.dropna()
    return {"x": [t.strftime("%Y-%m-%d") for t in s.index], "y": [round(float(v), dec) for v in s.values]}


def alinear(series: dict[str, pd.Series], desde: str) -> dict[str, pd.Series]:
    """Series diarias llevadas a un mismo calendario (días con dato en la primera serie), con arrastre."""
    base = series[next(iter(series))][desde:].dropna().index
    out = {}
    for n, s in series.items():
        s = s.dropna()
        out[n] = s.reindex(s.index.union(base)).ffill().reindex(base)
    return out


def ult(s: pd.Series, dec=2):
    s = s.dropna()
    return {"fecha": s.index[-1].strftime("%Y-%m-%d"), "valor": round(float(s.iloc[-1]), dec)}


def kv(fecha, valor, dec=2):
    return {"fecha": pd.Timestamp(fecha).strftime("%Y-%m-%d"), "valor": round(float(valor), dec)}


# ---------- IPC por divisiones, grupos y clases (archivos del INDEC; la API de series tiene huecos en Vivienda)
URL_INDEC = "https://www.indec.gob.ar/ftp/cuadros/economia/"
ARCHIVOS_IPC = {"divisiones": "serie_ipc_divisiones.csv",   # nivel general y 12 divisiones, nacional y 6 regiones
                "aperturas": "serie_ipc_aperturas.csv"}     # 20 grupos y 12 clases, solo por región
DIVISIONES = {"01": "Alimentos y bebidas", "02": "Bebidas alcohólicas y tabaco", "03": "Prendas y calzado",
              "04": "Vivienda, agua, luz y gas", "05": "Equipamiento del hogar", "06": "Salud", "07": "Transporte",
              "08": "Comunicación", "09": "Recreación y cultura", "10": "Educación", "11": "Restaurantes y hoteles",
              "12": "Bienes y servicios varios"}
GRUPOS = {"01.1": "Alimentos", "01.2": "Bebidas no alcohólicas", "02.1": "Bebidas alcohólicas", "02.2": "Tabaco",
          "03.1": "Prendas de vestir", "03.2": "Calzado", "04.1": "Alquiler y gastos conexos",
          "04.3": "Mantenimiento de la vivienda", "04.5": "Electricidad, gas y combustibles",
          "05.6": "Conservación del hogar", "06.1": "Medicamentos y artefactos de salud", "07.1": "Adquisición de vehículos",
          "07.2": "Funcionamiento de vehículos", "07.3": "Transporte público", "08.3": "Telefonía e internet",
          "09.1": "Equipos audiovisuales e informática", "09.4": "Servicios recreativos y culturales",
          "09.5": "Diarios, libros y papelería", "11.1": "Comidas fuera del hogar", "12.1": "Cuidado personal"}
CLASES = {"01.1.1": "Pan y cereales", "01.1.2": "Carnes y derivados", "01.1.4": "Lácteos y huevos",
          "01.1.5": "Aceites, grasas y manteca", "01.1.6": "Frutas", "01.1.7": "Verduras y legumbres",
          "01.1.8": "Azúcar, dulces y golosinas", "01.2.1": "Café, té, yerba y cacao", "01.2.2": "Aguas, gaseosas y jugos",
          "04.1.1": "Alquiler de la vivienda", "06.4.1": "Prepagas", "07.2.2": "Combustibles y lubricantes"}
REGIONES = ["Nacional", "GBA", "Pampeana", "Noreste", "Noroeste", "Cuyo", "Patagonia"]


def ipc_indec(cual: str, horas=1) -> pd.DataFrame:
    """Archivo de series del IPC del INDEC (caché local; si falla la descarga se usa la copia guardada).
    Devuelve columnas Codigo, Region, fecha, v (índice dic-2016 = 100)."""
    import requests
    archivo = ARCHIVOS_IPC[cual]
    cache = AQUI / "cache" / archivo
    viejo = not cache.exists() or (pd.Timestamp.now() - pd.Timestamp(cache.stat().st_mtime, unit="s")).total_seconds() > horas * 3600
    if viejo:
        try:
            r = requests.get(URL_INDEC + archivo, timeout=180, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            if r.content.lstrip()[:1] == b"<":   # el servidor devuelve una página HTML cuando el archivo no existe
                raise ValueError("el INDEC devolvió una página en lugar del CSV")
            cache.parent.mkdir(exist_ok=True)
            cache.write_bytes(r.content)
        except Exception as e:
            if not cache.exists():
                raise
            print(f"Aviso: no se pudo actualizar {archivo} del INDEC, uso la copia guardada -", e)
    df = pd.read_csv(cache, sep=";", encoding="latin-1", dtype={"Codigo": str, "Periodo": str})
    df["fecha"] = pd.to_datetime(df.Periodo, format="%Y%m")
    df["v"] = pd.to_numeric(df.Indice_IPC.astype(str).str.replace(",", "."), errors="coerce")
    return df[["Codigo", "Region", "fecha", "v"]]


def ipc_categorias_regiones(horas=1) -> dict:
    """Núcleo, regulados y estacionales por región, del cuadro del INDEC sh_ipc_divisiones.xls (o, de respaldo, el
    fechado sh_ipc_MM_AA.xls). Devuelve {región: {categoría: serie}}."""
    import requests
    cache = AQUI / "cache" / "sh_ipc.xls"
    viejo = not cache.exists() or (pd.Timestamp.now() - pd.Timestamp(cache.stat().st_mtime, unit="s")).total_seconds() > horas * 3600
    if viejo:
        hoy = pd.Timestamp.now()
        nombres = ["sh_ipc_divisiones.xls"] + [f"sh_ipc_{m:%m}_{m:%y}.xls" for m in (hoy - pd.DateOffset(months=k) for k in range(4))]
        for nombre in nombres:   # nombre fijo primero; los fechados quedan de respaldo
            try:
                r = requests.get(f"{URL_INDEC}{nombre}", timeout=180, headers={"User-Agent": "Mozilla/5.0"})
                if r.ok and r.content[:4] == b"\xd0\xcf\x11\xe0":   # archivo Excel (si no existe, el INDEC devuelve una página HTML)
                    cache.parent.mkdir(exist_ok=True)
                    cache.write_bytes(r.content)
                    break
            except Exception as e:
                print(f"Aviso: no se pudo bajar {nombre} del INDEC -", e)
        else:
            if not cache.exists():
                raise RuntimeError("No hay cuadro sh_ipc del INDEC ni copia guardada")
            print("Aviso: uso la copia guardada del cuadro sh_ipc del INDEC")
    xl = pd.ExcelFile(cache)
    hoja = next(h for h in xl.sheet_names if h.startswith("Índices IPC"))
    df = pd.read_excel(xl, hoja, header=None)
    fila_fechas = df.index[df.iloc[:, 0].astype(str).str.strip() == "Total nacional"][0]
    fechas = pd.to_datetime(df.iloc[fila_fechas, 1:], errors="coerce")
    nombres = {"Estacional": "Estacionales", "Núcleo": "Núcleo", "Regulados": "Regulados"}
    out, reg = {}, None
    for _, fila in df.iterrows():
        etiqueta = str(fila.iloc[0]).strip()
        if etiqueta == "Total nacional" or etiqueta.startswith("Región "):
            reg = "Nacional" if etiqueta == "Total nacional" else etiqueta.removeprefix("Región ")
        elif reg and etiqueta in nombres:
            s = pd.Series(pd.to_numeric(fila.iloc[1:].values, errors="coerce"), index=fechas.values).dropna()
            out.setdefault(reg, {})[nombres[etiqueta]] = s[s.index.notna()]
    return out


def brechas(d) -> dict:
    """Índices del IPC para las solapas Por categoría y Brechas.
    Nacional: nivel general, 3 categorías y 12 divisiones. Cada región: además, 20 grupos y 12 clases."""
    div, ape = ipc_indec("divisiones"), ipc_indec("aperturas")
    try:
        cats = ipc_categorias_regiones()
    except Exception as e:
        print("Aviso: sin categorías por región -", e)
        cats = {}
    serie = lambda df, reg, cod: df[(df.Region == reg) & (df.Codigo == cod)].set_index("fecha").v.sort_index()
    regiones = {}
    for reg in REGIONES:
        comp = {k: cats[reg][k] for k in ("Núcleo", "Regulados", "Estacionales") if k in cats.get(reg, {})}   # cuadro sh_ipc del INDEC
        if reg == "Nacional" and not comp:
            comp = {"Núcleo": d["ipc_nucleo"], "Regulados": d["ipc_reg"], "Estacionales": d["ipc_est"]}
        comp.update({n: serie(div, reg, c) for c, n in DIVISIONES.items()})
        if reg != "Nacional":
            for tabla in (GRUPOS, CLASES):
                comp.update({n: s for c, n in tabla.items() if len(s := serie(ape, reg, c).dropna())})
        regiones[reg] = {"general": serie(div, reg, "0"), "comp": comp}
    fin = min(r["general"].dropna().index[-1] for r in regiones.values())
    idx = pd.date_range("2017-01-01", fin, freq="MS")   # desde 2017: interanuales desde 2018
    r2 = lambda s: [None if pd.isna(v) else round(float(v), 2) for v in s.reindex(idx)]
    grupo = {**{n: "Categorías" for n in ("Núcleo", "Regulados", "Estacionales")}, **{n: "Divisiones" for n in DIVISIONES.values()},
             **{n: "Grupos" for n in GRUPOS.values()}, **{n: "Clases" for n in CLASES.values()}}
    return {"x": [t.strftime("%Y-%m-%d") for t in idx], "grupo": grupo,
            "reg": {reg: {"general": r2(r["general"]), "comp": {n: r2(s) for n, s in r["comp"].items()}} for reg, r in regiones.items()}}


# ---------- G20: World Economic Outlook del FMI (API DataMapper, anual, con proyecciones)
G20 = {"ARG": "Argentina", "AUS": "Australia", "BRA": "Brasil", "CAN": "Canadá", "CHN": "China", "FRA": "Francia",
       "DEU": "Alemania", "IND": "India", "IDN": "Indonesia", "ITA": "Italia", "JPN": "Japón", "KOR": "Corea del Sur",
       "MEX": "México", "RUS": "Rusia", "SAU": "Arabia Saudita", "ZAF": "Sudáfrica", "TUR": "Turquía",
       "GBR": "Reino Unido", "USA": "Estados Unidos", "EU": "Unión Europea", "WEOWORLD": "Mundo"}
WEO = {  # clave: (código FMI, nombre, unidad, decimales)
    "crec": ("NGDP_RPCH", "Crecimiento del PIB", "%", 1),
    "infl": ("PCPIEPCH", "Inflación (diciembre contra diciembre)", "%", 1),
    "desemp": ("LUR", "Desempleo", "%", 1),
    "fiscal": ("GGXCNL_NGDP", "Resultado fiscal del gobierno general", "% PIB", 1),
    "deuda": ("GGXWDG_NGDP", "Deuda pública bruta", "% PIB", 1),
    "cc": ("BCA_NGDPD", "Cuenta corriente", "% PIB", 1),
    "pibpc": ("NGDPDPC", "PIB per cápita", "US$", 0),
    "pibppa": ("PPPPC", "PIB per cápita (paridad de poder adquisitivo)", "US$ PPA", 0),
    "pib": ("NGDPD", "PIB en dólares", "US$ miles de M", 0),
}
CACHE_WEO = AQUI / "cache" / "fmi_weo.json"


def g20(hoy: pd.Timestamp) -> dict:
    """Indicadores anuales del WEO para el G20. Se baja una vez por semana; si falla la red usa la copia guardada."""
    import requests
    crudo = json.loads(CACHE_WEO.read_text(encoding="utf-8")) if CACHE_WEO.exists() else None
    viejo = (crudo is None or (pd.Timestamp.now() - pd.Timestamp(crudo["bajado"])).days >= 7
             or any(cod not in crudo["valores"] for cod, *_ in WEO.values()))  # se agregó un indicador
    if viejo:
        try:
            nuevo = {"bajado": pd.Timestamp.now().isoformat(timespec="seconds"), "valores": {}}
            for cod, *_ in WEO.values():
                r = requests.get(f"https://www.imf.org/external/datamapper/api/v1/{cod}", timeout=90)
                r.raise_for_status()
                v = r.json()["values"][cod]
                nuevo["valores"][cod] = {p: v.get(p, {}) for p in G20}
            CACHE_WEO.parent.mkdir(exist_ok=True)
            CACHE_WEO.write_text(json.dumps(nuevo, ensure_ascii=False), encoding="utf-8")
            crudo = nuevo
        except Exception as e:  # sin red: seguir con la copia anterior
            if crudo is None:
                raise
            print("Aviso: no se pudo actualizar el WEO del FMI, uso la copia del", crudo["bajado"][:10], "-", e)
    anios = [str(a) for a in range(2000, hoy.year + 6)]
    ind = {}
    for k, (cod, nombre, u, dec) in WEO.items():
        val = crudo["valores"][cod]
        ind[k] = {"n": nombre, "u": u, "dec": dec,
                  "v": {p: [None if val[p].get(a) is None else round(float(val[p][a]), dec if dec else 0) for a in anios] for p in G20}}
    # Desde el año en curso las cifras son proyecciones del FMI.
    return {"paises": G20, "anios": [int(a) for a in anios], "proy_desde": hoy.year, "ind": ind, "bajado": crudo["bajado"][:10]}


def main():
    vint = sorted(datos.VINTAGES.glob("2*.csv"))[-1]
    d, cat = datos.cargar(vint), datos.catalogo()
    R = datos.cargar_rem(vint)
    ipc_e = SB.ipc_extendido(d["ipc"], R)
    mens, fin, suma = SB.mens, SB.fin, SB.suma
    import datetime as _dt
    # hora de la corrida (hora de Argentina): el tablero se actualiza varias veces por día con las series diarias
    hora = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=3)).strftime("%H:%M")
    out = {"actualizado": vint.stem, "hora": hora, "secciones": {}}
    sec = out["secciones"]

    # ================= tipo de cambio
    tcs = alinear({"Mayorista (A3500)": d["tc_may"], "Contado con liqui": d["ccl"], "Informal": d["blue"]}, "2023")
    tc, ccl, blue = tcs.values()
    brecha = (ccl / tc - 1) * 100
    sec["tipo-cambio"] = {
        "kpis": {"oficial": ult(tc), "ccl": ult(ccl, 0), "blue": ult(blue, 0), "brecha": ult(brecha, 1),
                 "oficial_30d": round(float(tc.iloc[-1] / tc[: tc.index[-1] - pd.Timedelta(days=30)].iloc[-1] - 1) * 100, 2)},
        "cotizaciones": {n: serie(s) for n, s in tcs.items()},
        "brecha": {"Brecha CCL / mayorista": serie(brecha, 1)},
    }

    # ================= precios
    ipc = d["ipc"]
    sec["precios"] = {
        "kpis": {"mensual": kv(ipc.index[-1], C.var(ipc).iloc[-1]), "interanual": kv(ipc.index[-1], C.ia(ipc).iloc[-1]),
                 "nucleo": ult(C.var(d["ipc_nucleo"])), "rem12": ult(d["rem_ipc12"], 1)},
        "mensual": {"Nivel general": serie(C.var(ipc)["2017":], 1)},
        "brechas": brechas(d),
    }

    # ================= actividad
    ed = d["emae_de"]
    ia_sec = {cat.loc[k, "nombre"]: round(float(C.ia(d[k]).iloc[-1]), 1) for k in C.SECTORES}
    sec["actividad"] = {
        "kpis": {"emae_mm": kv(ed.index[-1], C.var(ed).iloc[-1]), "emae_ia": kv(ed.index[-1], C.ia(d["emae"]).iloc[-1]),
                 "ipi_ia": kv(d["ipi"].index[-1], C.ia(d["ipi"]).iloc[-1]), "isac_ia": kv(d["isac"].index[-1], C.ia(d["isac"]).iloc[-1])},
        "emae": {"Desestacionalizado": serie(ed["2016":], 1), "Tendencia-ciclo": serie(d["emae_tc"]["2016":], 1)},
        # sectores con variaciones extremas por efecto base (p. ej. pesca) quedan fuera del gráfico, con nota
        "sectores": dict(sorted(((k, v) for k, v in ia_sec.items() if abs(v) <= 60), key=lambda x: -x[1])),
        "sectores_fuera": {k: v for k, v in ia_sec.items() if abs(v) > 60},
        "indicadores": {"EMAE": serie(C.ia(d["emae"])["2018":], 1), "Industria (IPI)": serie(C.ia(d["ipi"])["2018":], 1),
                        "Construcción (ISAC)": serie(C.ia(d["isac"])["2018":], 1)},
        "mes_sectores": ed.index[-1].strftime("%Y-%m-%d"),
    }

    # ================= empleo y salarios
    ipc_ = d["ipc"]
    sal = {}
    for k, n in [("sal_priv", "Registrado privado"), ("sal_pub", "Registrado público")]:
        s = d[k].dropna()
        r = s / ipc_.reindex(s.index)
        sal[n] = r / r["2023-12"].iloc[0] * 100
    sp = d["sipa_priv"].dropna()
    de = d["eph_desoc"].dropna() * 100
    pob = d["pobreza"].dropna()
    sec["empleo"] = {
        "kpis": {"desoc": kv(de.index[-1], de.iloc[-1], 1), "desoc_ant": round(float(de.iloc[-5]), 1),
                 "sal_real": kv(d["sal_priv"].dropna().index[-1], C.real(C.ia(d["sal_priv"].dropna()), ipc_).iloc[-1], 1),
                 "sipa": kv(sp.index[-1], sp.iloc[-1], 0), "sipa_var": round(float(sp.iloc[-1] - sp.iloc[-13]), 0),
                 "pobreza": kv(pob.index[-1], pob.iloc[-1], 1)},
        "eph": {n: serie(d[k].dropna()["2017":] * 100, 1) for k, n in
                [("eph_activ", "Tasa de actividad"), ("eph_empleo", "Tasa de empleo"), ("eph_desoc", "Tasa de desocupación")]},
        "salario": {n: serie(s["2023-12":], 1) for n, s in sal.items()},
        "sipa": {"Asalariados registrados privados": serie(sp["2018":], 0)},
        "pobreza": {"Pobreza (personas)": serie(pob["2016-07":], 1)},
    }

    # ================= comercio exterior
    x, m = d["expo"].dropna(), d["impo"].dropna()
    saldo = x - m
    t = x.index[-1]
    acum = lambda z: z[(z.index.year == t.year) & (z.index.month <= t.month)].sum()
    sec["comercio"] = {
        "kpis": {"expo": kv(t, x.iloc[-1], 0), "expo_ia": round(float(C.ia(x).iloc[-1]), 1), "impo": kv(t, m.iloc[-1], 0),
                 "impo_ia": round(float(C.ia(m).iloc[-1]), 1), "saldo": kv(t, saldo.iloc[-1], 0), "saldo_acum": kv(t, acum(saldo), 0)},
        "doce": {"Exportaciones": serie(x.rolling(12).sum()["2016":] / 1e3, 1), "Importaciones": serie(m.rolling(12).sum()["2016":] / 1e3, 1)},
        "saldo": {"Saldo comercial": serie(saldo["2019":], 0)},
        "rubros": {n: serie(d[k].dropna().rolling(12).sum()["2016":] / 1e3, 2) for k, n in
                   [("x_pp", "Productos primarios"), ("x_moa", "Manuf. agropecuarias"), ("x_moi", "Manuf. industriales"), ("x_cye", "Combustibles y energía")]},
        "usos": {n: serie(d[k].dropna().rolling(12).sum()["2016":] / 1e3, 2) for k, n in
                 [("m_bi", "Bienes intermedios"), ("m_bk", "Bienes de capital"), ("m_pzas", "Piezas y accesorios"), ("m_bc", "Bienes de consumo")]},
    }

    # ================= monetarias
    r = d["reservas"].dropna()
    comp = suma(d["compras"].dropna())
    mc = comp.index[-1] if d["compras"].dropna().index[-1].day > 25 else comp.index[-2]
    sec["monetarias"] = {
        "kpis": {"reservas": ult(r, 0), "compras_mes": kv(mc, comp[mc], 0), "compras_anio": round(float(comp[str(mc.year)].sum()), 0),
                 "tamar": ult(d["tamar"], 1), "m2_real": kv(mc, SB.real_ia(mens(d["m2"]), ipc_e)[mc], 1)},
        "reservas": {"Reservas brutas": serie(r["2022":], 0)},
        "compras": {"Compras netas del BCRA": serie(comp["2024":], 0)},
        "tasas": {"TAMAR": serie(mens(d["tamar"])["2025":], 1), "BADLAR": serie(mens(d["badlar"])["2025":], 1),
                  "Plazo fijo 30 días": serie(mens(d["tasa_pf"])["2025":], 1), "Inflación esperada (REM)": serie(mens(d["rem_ipc12"])["2025":], 1),
                  "Inflación interanual (INDEC)": serie(C.ia(d["ipc"])["2025":], 1)},
        "credito": {n: serie(SB.real_ia(mens(d[k]), ipc_e)["2019":], 1) for k, n in
                    [("prest_priv", "Préstamos en $"), ("dep_priv", "Depósitos privados en $"), ("m2", "M2 privado")]},
        "dolares": {"Préstamos en dólares": serie(fin(d["prest_usd"])["2019":], 0), "Depósitos en dólares": serie(fin(d["dep_usd"])["2019":], 0)},
    }

    # ================= mercados
    ccl_ = d["ccl"].dropna()
    mu = SB.en_ccl(d["merval"].dropna(), ccl_)
    hoy = pd.Timestamp(vint.stem)
    rend = {}
    for k in SB.ACC:
        if k in d:
            m1, ytd, a12 = SB.var_periodos(SB.en_ccl(d[k].dropna(), ccl_), hoy)
            rend[cat.loc[k, "nombre"]] = {"mes": round(m1, 1), "anio": round(ytd, 1), "doce": round(a12, 1)}
    rp = d["riesgo"].dropna()
    sec["mercados"] = {
        "kpis": {"riesgo": ult(rp, 0), "riesgo_30d": round(float(rp.iloc[-1] - rp[: rp.index[-1] - pd.Timedelta(days=30)].iloc[-1]), 0),
                 "merval_usd": ult(mu, 0), "merval_usd_ytd": round(SB.var_periodos(mu, hoy)[1], 1),
                 "merval": ult(d["merval"], 0)},
        "riesgo": {"Riesgo país": serie(rp["2022":], 0)},
        "merval": {"Merval en dólares (CCL)": serie(mu["2020":], 0)},
        "acciones_anio": dict(sorted(((n, v["anio"]) for n, v in rend.items()), key=lambda x: -x[1])),
        "acciones_doce": dict(sorted(((n, v["doce"]) for n, v in rend.items()), key=lambda x: -x[1])),
    }

    # ================= internacional
    tasas = alinear({"Fondos federales": d["fed"], "Tesoro 2 años": d["ust2"], "Tesoro 10 años": d["ust10"]}, "2022")
    com = alinear({"Soja": d["soja"], "Maíz": d["maiz"], "Trigo": d["trigo"], "Petróleo Brent": d["brent"]}, "2022")
    mon = alinear({"Índice dólar (DXY)": d["dxy"], "Real (BRL por USD)": d["brl"], "Euro (USD por EUR)": d["eurusd"]}, "2022")
    bol = alinear({"S&P 500": d["spx"], "Bovespa": d["bvsp"]}, "2022")
    sec["internacional"] = {
        "kpis": {"fed": ult(d["fed"]), "ust10": ult(d["ust10"]), "brent": ult(d["brent"], 1), "soja": ult(d["soja"], 1),
                 "brent_ytd": round(SB.var_periodos(d["brent"].dropna(), hoy)[1], 1), "soja_ytd": round(SB.var_periodos(d["soja"].dropna(), hoy)[1], 1)},
        "tasas": {n: serie(s) for n, s in tasas.items()},
        "commodities": {n: serie(s) for n, s in com.items()},
        "monedas": {n: serie(s, 3) for n, s in mon.items()},
        "bolsas": {n: serie(s, 0) for n, s in bol.items()},
        "g20": g20(pd.Timestamp(hoy)),
    }
    sec["internacional"]["g20_ult"] = g20_ultimos(sec["internacional"]["g20"], d["eph_desoc"] * 100, sec["precios"]["kpis"]["interanual"])

    destino = AQUI / "demo" / "datos.js"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text("window.DATOS = " + json.dumps(out, ensure_ascii=False) + ";\n", encoding="utf-8")
    print("Escrito:", destino, f"({destino.stat().st_size / 1024:.0f} KB)")
    # index.html carga datos.js?v=<hash>: así el navegador no muestra datos viejos de su caché
    import hashlib
    import re
    h = hashlib.md5(destino.read_bytes()).hexdigest()[:8]
    pagina = destino.parent / "index.html"
    html = pagina.read_text(encoding="utf-8")
    h_en = hashlib.md5((destino.parent / "i18n_en.js").read_bytes()).hexdigest()[:8]
    html = re.sub(r'src="datos\.js(\?v=\w+)?"', f'src="datos.js?v={h}"', html)
    html = re.sub(r'src="i18n_en\.js(\?v=\w+)?"', f'src="i18n_en.js?v={h_en}"', html)
    pagina.write_text(html, encoding="utf-8")


def publicar(sitio: Path):
    """Copia la página y los datos a <sitio>/tablero/ (el commit y el push se hacen aparte)."""
    import shutil
    dest = sitio / "tablero"
    dest.mkdir(exist_ok=True)
    for f in ("index.html", "datos.js", "i18n_en.js"):
        shutil.copy2(AQUI / "demo" / f, dest / f)
    print("Copiado a", dest)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--sitio", type=Path, default=None, help="carpeta del repositorio del sitio de AXIA")
    a = ap.parse_args()
    main()
    if a.sitio:
        publicar(a.sitio)
