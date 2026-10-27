"""Capa de datos del Boletín: baja las series del catálogo desde las APIs oficiales.

- API Series de Tiempo (datos.gob.ar): https://apis.datos.gob.ar/series/api/
- API Estadísticas Monetarias v4 del BCRA: https://api.bcra.gob.ar/estadisticas/v4.0/

Cada descarga se guarda como "vintage" en datos/vintages/AAAA-MM-DD.csv (formato largo:
fecha, clave, valor). Así se pueden comparar ediciones y detectar revisiones.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import time
from pathlib import Path

import pandas as pd
import requests
import urllib3

urllib3.disable_warnings()

AQUI = Path(__file__).parent
CATALOGO = AQUI / "catalogo.csv"
VINTAGES = AQUI / "datos" / "vintages"
DESDE = "2015-01-01"


def catalogo() -> pd.DataFrame:
    return pd.read_csv(CATALOGO, dtype=str).set_index("clave")


# Cuanto se espera entre intentos de descarga. Las caidas de apis.datos.gob.ar y del BCRA
# suelen durar unos minutos: con esperas de segundos, la corrida se perdia por nada.
ESPERAS = (30, 120, 300)


def _get(url, params, verify=True, headers=None, intentos=4):
    for i in range(intentos):
        try:
            r = requests.get(url, params=params, timeout=90, verify=verify, headers=headers)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if i == intentos - 1:
                raise
            espera = ESPERAS[min(i, len(ESPERAS) - 1)]
            print("   %s no responde (%s): reintento en %d s" % (url.split("/")[2], type(e).__name__, espera),
                  flush=True)
            time.sleep(espera)


def api_series(ids: list[str], desde=DESDE) -> pd.DataFrame:
    """Series de datos.gob.ar; la API admite hasta 40 ids por consulta."""
    frames = []
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        r = _get("https://apis.datos.gob.ar/series/api/series/",
                 {"ids": ",".join(chunk), "format": "csv", "limit": 5000, "start_date": desde})
        df = pd.read_csv(io.StringIO(r.text), parse_dates=["indice_tiempo"]).set_index("indice_tiempo")
        df.columns = chunk
        # La API a veces devuelve huecos internos (o la serie vacía), y guarda en su caché la respuesta de cada URL
        # exacta aunque venga incompleta: esas series se vuelven a pedir solas, cambiando el parámetro limit en cada
        # intento (5000, 4999...; más de 5000 da error) para forzar una respuesta nueva. Queda la más completa.
        for sid in chunk:
            if _huecos(df[sid]):
                s1 = _serie_sola(sid, desde)
                if s1 is not None and _huecos(s1) < _huecos(df[sid]):
                    df = df.reindex(df.index.union(s1.index))
                    df[sid] = s1.reindex(df.index)
        frames.append(df)
    return pd.concat(frames, axis=1)


def _huecos(s: pd.Series) -> int:
    """Datos faltantes entre el primero y el último válido (la serie entera si está vacía)."""
    if not s.notna().any():
        return 10 ** 6
    return int(s.loc[s.first_valid_index():s.last_valid_index()].isna().sum())


def _serie_sola(sid: str, desde, intentos=5):
    mejor = None
    for i in range(intentos):
        try:
            r = _get("https://apis.datos.gob.ar/series/api/series/",
                     {"ids": sid, "format": "csv", "limit": 5000 - i, "start_date": desde}, intentos=1)
            s = pd.read_csv(io.StringIO(r.text), parse_dates=["indice_tiempo"]).set_index("indice_tiempo").iloc[:, 0]
        except Exception:  # noqa: BLE001
            continue
        if mejor is None or _huecos(s) < _huecos(mejor):
            mejor = s
        if _huecos(mejor) == 0:
            break
    return mejor


def api_bcra(var_id: int, desde=DESDE) -> pd.Series:
    """Variable de la API de Estadísticas Monetarias v4 del BCRA (paginada de a 3000)."""
    out, offset = [], 0
    hasta = dt.date.today().isoformat()
    while True:
        js = _get(f"https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/{var_id}",
                  {"desde": desde, "hasta": hasta, "limit": 3000, "offset": offset}, verify=False).json()
        det = js["results"][0]["detalle"] if js.get("results") else []
        out += det
        offset += 3000
        if offset >= js["metadata"]["resultset"]["count"] or not det:
            break
    s = pd.Series({pd.Timestamp(d["fecha"]): d["valor"] for d in out}, dtype=float)
    return s.sort_index()


H = {"User-Agent": "Mozilla/5.0"}


def api_fred(serie: str, desde=DESDE) -> pd.Series:
    r = _get("https://fred.stlouisfed.org/graph/fredgraph.csv", {"id": serie, "cosd": desde})
    df = pd.read_csv(io.StringIO(r.text))
    s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values, index=pd.to_datetime(df.iloc[:, 0]))
    return s.dropna()


def api_yahoo(ticker: str, desde=DESDE) -> pd.Series:
    """Cierres diarios ajustados (splits y dividendos) de Yahoo Finance."""
    p1 = int(pd.Timestamp(desde).timestamp())
    r = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
             {"period1": p1, "period2": int(time.time()), "interval": "1d"}, headers=H)
    res = r.json()["chart"]["result"][0]
    ind = res["indicators"]
    vals = ind.get("adjclose", [{}])[0].get("adjclose") or ind["quote"][0]["close"]
    idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
    s = pd.Series(vals, index=idx, dtype=float).dropna()
    return s[~s.index.duplicated(keep="last")]


def api_argdatos(ruta: str) -> pd.Series:
    """ArgentinaDatos (cotizaciones del dólar y riesgo país)."""
    js = _get(f"https://api.argentinadatos.com/v1/{ruta}", {}).json()
    campo = "venta" if "venta" in js[0] else "valor"
    s = pd.Series({pd.Timestamp(x["fecha"]): x[campo] for x in js}, dtype=float)
    return s.sort_index()[DESDE:]


def rem() -> pd.DataFrame:
    """Medianas de la última planilla del REM (BCRA): bloque, período, mediana."""
    html = requests.get("https://www.bcra.gob.ar/relevamiento-expectativas-mercado-rem/",
                        headers=H, verify=False, timeout=90).text
    m = re.search(r'href="([^"]*(?:tablas-relevamiento-expectativas-mercado-|'
                  r'relevamiento-expectativas-mercado-tablas-)[^"]+\.xlsx)"', html)
    url = m[1] if m[1].startswith("http") else "https://www.bcra.gob.ar" + m[1]
    return _parse_rem(requests.get(url, headers=H, verify=False, timeout=90).content)


MES_ABR = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
REM_DIR = AQUI / "datos" / "rem"


def rem_mes(mes: pd.Period) -> pd.DataFrame:
    """Planilla del REM de un mes de relevamiento dado (con caché en datos/rem/rem_AAAA-MM.csv).
    El BCRA cambió el nombre del archivo en 2026; se prueban los dos formatos."""
    REM_DIR.mkdir(parents=True, exist_ok=True)
    cache = REM_DIR / f"rem_{mes}.csv"
    if cache.exists():
        return pd.read_csv(cache, dtype={"periodo": str})
    base = "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/"
    for nombre in (f"informes/relevamiento-expectativas-mercado-tablas-{mes}.xlsx",
                   f"informes/tablas-relevamiento-expectativas-mercado-{MES_ABR[mes.month - 1]}-{mes.year}.xlsx",
                   f"tablas-relevamiento-expectativas-mercado-{MES_ABR[mes.month - 1]}-{mes.year}.xlsx"):
        r = requests.get(base + nombre, headers=H, verify=False, timeout=90)
        if r.ok and r.content[:2] == b"PK":
            out = _parse_rem(r.content)
            out.assign(titulo=out.attrs.get("titulo", "")).to_csv(cache, index=False)
            return pd.read_csv(cache, dtype={"periodo": str})
    raise FileNotFoundError(f"No se encontró la planilla del REM de {mes}")


def _parse_rem(contenido: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(contenido), sheet_name=0, header=None)
    filas, bloque, titulo = [], None, ""
    for _, f in df.iterrows():
        b, med = f[1], f[3]
        if isinstance(b, str) and pd.isna(f[2]):
            bloque = b.strip()
            if "Relevamiento" in b:
                titulo = b.strip()
            continue
        if bloque and isinstance(med, (int, float)) and pd.notna(med):
            per = pd.Timestamp(b).strftime("%Y-%m") if not isinstance(b, str) else str(b).strip()
            filas.append({"bloque": bloque, "periodo": per, "mediana": float(med)})
    out = pd.DataFrame(filas)
    out.attrs["titulo"] = titulo
    return out


LIBRO_LABORAL = AQUI.parent / "salida" / "laboral-social.xlsx"
POBREZA_CSV = AQUI.parent / "datos_locales" / "pobreza.csv"   # copia de la serie para GitHub Actions (sin el Excel)


def pobreza() -> pd.Series:
    """Pobreza en personas, total país (INDEC), desde el libro laboral-social del Boletín.
    Donde no está el Excel (GitHub Actions) usa la copia datos_locales/pobreza.csv que sube tablero/vigilar_excel.py."""
    if not LIBRO_LABORAL.exists() and POBREZA_CSV.exists():
        c = pd.read_csv(POBREZA_CSV, parse_dates=["fecha"])
        return pd.Series(c.valor.values, index=c.fecha).sort_index()
    if not LIBRO_LABORAL.exists():
        return pd.Series(dtype=float)   # sin el Excel (GitHub): la serie la completa indec.integrar() con el informe del INDEC
    x = pd.read_excel(LIBRO_LABORAL, sheet_name="Pobreza Nueva met", header=None)
    anios = x.iloc[3].ffill()
    sem = x.iloc[4].ffill()
    fila = x[x[1].astype(str).str.strip() == "Total País"].iloc[0]
    out = {}
    for c in range(2, x.shape[1]):
        if str(x.iat[5, c]).strip() != "Personas" or pd.isna(fila[c]):
            continue
        mes = 1 if str(sem[c]).startswith("1") else 7
        out[pd.Timestamp(int(anios[c]), mes, 1)] = float(str(fila[c]).replace(",", "."))
    return pd.Series(out).sort_index()


def descargar() -> pd.DataFrame:
    """Baja todo el catálogo y devuelve el formato largo (fecha, clave, valor)."""
    cat = catalogo()
    largo = []

    def agregar(clave, s):
        largo.append(pd.DataFrame({"fecha": s.index, "clave": clave, "valor": s.values}))

    # la API de series agrega a la frecuencia más baja si se mezclan: se pide por frecuencia
    for frec, ser in cat[cat.fuente == "series"].groupby("frec"):
        df = api_series(list(ser.id))
        for clave, sid in ser.id.items():
            agregar(clave, df[sid])
    fetch = {"bcra": lambda i: api_bcra(int(i)), "fred": api_fred, "yahoo": api_yahoo,
             "argdatos": api_argdatos, "libro": lambda i: pobreza()}
    for clave, fila in cat[cat.fuente != "series"].iterrows():
        try:
            agregar(clave, fetch[fila.fuente](fila.id))
        except Exception as e:  # una fuente caída no frena la edición
            print(f"AVISO: no se pudo bajar {clave} ({fila.fuente} {fila.id}): {e}")
    out = pd.concat(largo, ignore_index=True).dropna(subset=["valor"])
    return out.sort_values(["clave", "fecha"]).reset_index(drop=True)


def completar_con_anterior(nuevo: pd.DataFrame, ruta: Path) -> pd.DataFrame:
    """La API de series a veces devuelve una serie vacía o con meses en blanco (y al día siguiente vuelve):
    lo que falte respecto del vintage anterior se toma de ese vintage, con aviso. Así un día malo de la API
    nunca deja datos peores que los del día anterior."""
    previos = [p for p in sorted(VINTAGES.glob("2*.csv")) if p.name <= ruta.name]   # incluye una descarga anterior del mismo día
    if not previos:
        return nuevo
    viejo = pd.read_csv(previos[-1], parse_dates=["fecha"])
    viejo = viejo[viejo.clave.isin(catalogo().index)]
    nuevo = nuevo.assign(fecha=pd.to_datetime(nuevo.fecha))
    clave_fecha = pd.MultiIndex.from_frame(nuevo[["clave", "fecha"]])
    faltan = viejo[~pd.MultiIndex.from_frame(viejo[["clave", "fecha"]]).isin(clave_fecha)]
    for clave, n in faltan.groupby("clave").size().items():
        print(f"AVISO: {clave}: {n} dato(s) que la API no devolvió hoy; se toman del vintage {previos[-1].stem}")
    return pd.concat([nuevo, faltan], ignore_index=True).sort_values(["clave", "fecha"]).reset_index(drop=True)


def actualizar(forzar=False) -> Path:
    """Descarga y guarda el vintage del día (reutiliza el del día si ya existe), con el REM aparte."""
    VINTAGES.mkdir(parents=True, exist_ok=True)
    ruta = VINTAGES / f"{dt.date.today().isoformat()}.csv"
    if forzar or not ruta.exists():
        import indec   # series del INDEC desde sus propios archivos: el último dato el mismo día de la publicación
        df = completar_con_anterior(descargar(), ruta)
        claves = list(catalogo().query("organismo.str.contains('INDEC', na=False)").index)
        indec.integrar(df, claves).to_csv(ruta, index=False)
    ruta_rem = ruta.with_name("rem_" + ruta.name)
    if forzar or not ruta_rem.exists():
        try:
            r = rem()
            r.assign(titulo=r.attrs.get("titulo", "")).to_csv(ruta_rem, index=False)
        except Exception as e:
            print(f"AVISO: REM: {e}")
    return ruta


def cargar_rem(ruta: Path) -> pd.DataFrame:
    r = ruta.with_name("rem_" + ruta.name)
    if not r.exists():
        previos = sorted(VINTAGES.glob("rem_*.csv"))
        if not previos:
            return pd.DataFrame(columns=["bloque", "periodo", "mediana", "titulo"])
        r = previos[-1]
    return pd.read_csv(r, dtype={"periodo": str})


def cargar(ruta: Path | None = None) -> dict[str, pd.Series]:
    """Último vintage como diccionario clave -> serie."""
    ruta = ruta or sorted(VINTAGES.glob("2*.csv"))[-1]
    df = pd.read_csv(ruta, parse_dates=["fecha"])
    return {k: g.set_index("fecha")["valor"].sort_index() for k, g in df.groupby("clave")}


def recortar(d: dict[str, pd.Series], corte: pd.Timestamp, ref: pd.Timestamp) -> dict[str, pd.Series]:
    """Datos "en tiempo real" a la fecha `corte`, a partir de un vintage descargado el día `ref`.

    El rezago de publicación de cada serie se mide en el vintage de referencia y se aplica igual
    al corte histórico:
    - series mensuales, trimestrales o semestrales: rezago en meses entre `ref` y el último dato
      (por ejemplo, el EMAE de julio al 4 de octubre: 3 meses);
    - series diarias: rezago en días.
    Limitación: los valores son los vigentes hoy (con revisiones); las APIs no guardan versiones viejas.
    """
    out = {}
    mref = ref.to_period("M")
    mcor = corte.to_period("M")
    for k, s in d.items():
        s = s.dropna()
        if len(s) < 3:
            out[k] = s
            continue
        paso = (s.index[-1] - s.index[0]).days / (len(s) - 1)
        if paso > 20:
            rezago = (mref - s.index[-1].to_period("M")).n
            limite = (mcor - rezago).to_timestamp(how="end")
            out[k] = s[s.index <= limite]
        else:
            rezago = min(max((ref - s.index[-1]).days, 0), 10)
            out[k] = s[s.index <= corte - pd.Timedelta(days=rezago)]
    return out


def rem_para_corte(corte: pd.Timestamp) -> pd.DataFrame:
    """REM disponible a la fecha de corte: el relevado dos meses antes (se publica en los primeros
    días hábiles del mes siguiente al relevamiento)."""
    return rem_mes(corte.to_period("M") - 2)


def revisiones(n_meses=6) -> pd.DataFrame:
    """Compara los dos últimos vintages y lista los valores revisados (>0,05%)."""
    rutas = sorted(VINTAGES.glob("2*.csv"))
    if len(rutas) < 2:
        return pd.DataFrame(columns=["clave", "fecha", "antes", "ahora", "dif_%"])
    a, b = (pd.read_csv(r, parse_dates=["fecha"]) for r in rutas[-2:])
    m = a.merge(b, on=["fecha", "clave"], suffixes=("_antes", "_ahora"))
    m["dif_%"] = (m.valor_ahora / m.valor_antes - 1) * 100
    m = m[m["dif_%"].abs() > 0.05]
    corte = b.fecha.max() - pd.DateOffset(months=n_meses)
    return m[m.fecha >= corte].rename(columns={"valor_antes": "antes", "valor_ahora": "ahora"})


if __name__ == "__main__":
    ruta = actualizar(forzar=True)
    d = cargar(ruta)
    cat = catalogo()
    for k, s in d.items():
        print(f"{k:12s} {s.index[-1].date()}  {s.iloc[-1]:>14,.2f}  {cat.loc[k, 'nombre']}")
    faltan = set(cat.index) - set(d)
    if faltan:
        print("SIN DATOS:", ", ".join(sorted(faltan)))
