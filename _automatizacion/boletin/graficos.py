"""Gráficos SVG del Boletín (sin dependencias: SVG a mano).

Los colores son variables CSS (--s1, --s2, ..., --pos, --neg), así el mismo SVG
sirve para la web (con modo oscuro) y para el PDF. Cada gráfico lleva sus datos
en `data-chart` para el tooltip de la versión web.
"""
from __future__ import annotations

import html
import json
import math

import pandas as pd

from calculo import MES3, num


def _ticks(lo, hi, n=5):
    if hi == lo:
        hi = lo + 1
    paso = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(paso))
    paso = min([1, 2, 5, 10], key=lambda m: abs(m * mag - paso)) * mag
    a = math.floor(lo / paso) * paso
    b = math.ceil(hi / paso) * paso
    out, x = [], a
    while x <= b + paso / 1e6:
        out.append(round(x, 10))
        x += paso
    return out


def _dec(ticks):
    paso = ticks[1] - ticks[0] if len(ticks) > 1 else 1
    return 0 if paso >= 1 else (1 if paso >= 0.1 else 2)


def _esc(t):
    return html.escape(str(t), quote=True)


def _diaria(idx: pd.DatetimeIndex) -> bool:
    return len(idx) > 2 and (idx[-1] - idx[0]).days / (len(idx) - 1) < 20


def _lbl_fecha(t, diaria):
    base = f"{MES3[t.month - 1]}-{str(t.year)[2:]}"
    return f"{t.day}-{base}" if diaria else base


def _xticks(idx: pd.DatetimeIndex):
    """Marcas en el primer dato de cada año (series largas) o de cada trimestre (cortas)."""
    anios = sorted(set(idx.year))
    if len(anios) >= 3:
        cand = [(pd.Timestamp(a, 1, 1), str(a)) for a in anios]
    else:
        cand = [(pd.Timestamp(a, m, 1), f"{MES3[m - 1]}-{str(a)[2:]}") for a in anios for m in (1, 4, 7, 10)]
    out = []
    for c, lbl in cand:
        pos = idx.searchsorted(c)
        if pos < len(idx) and (idx[pos] - c).days < 20:
            out.append((idx[pos], lbl))
    return out


def _payload(idx, series, unidad):
    diaria = _diaria(idx)
    return _esc(json.dumps({
        "x": [_lbl_fecha(t, diaria) for t in idx],
        "u": unidad,
        "s": [{"n": s["nombre"], "c": s["color"],
               "v": [None if pd.isna(v) else round(float(v), 2) for v in s["s"].reindex(idx)]}
              for s in series]}, ensure_ascii=False))


def _margen_izq(textos):
    return 14 + 6.6 * max(len(t) for t in textos)


def lineas(series: list[dict], unidad="%", alto=250, ancho=640, cero=False, dec_lbl=1,
           titulo_aria="", sufijo=None, leyenda=False) -> str:
    """Gráfico de líneas. series = [{"nombre", "s": pd.Series, "color": "var(--s1)", "dash": bool}].
    leyenda=True agrega una leyenda arriba (útil cuando una serie no lleva etiqueta al final)."""
    sufijo = ("%" if unidad == "%" else "") if sufijo is None else sufijo
    idx = series[0]["s"].dropna().index
    for s in series[1:]:
        idx = idx.union(s["s"].dropna().index)
    vals = pd.concat([s["s"] for s in series]).dropna()
    lo, hi = vals.min(), vals.max()
    if cero:
        lo, hi = min(lo, 0), max(hi, 0)
    yt = _ticks(lo, hi)
    d = _dec(yt)
    ml = _margen_izq([num(v, d) for v in yt])
    mr, mt, mb = 150, (34 if leyenda else 12), 26
    w, h = ancho - ml - mr, alto - mt - mb
    y0, y1 = yt[0], yt[-1]
    X = lambda t: ml + w * (idx.get_loc(t)) / max(len(idx) - 1, 1)
    Y = lambda v: mt + h * (1 - (v - y0) / (y1 - y0))
    out = [f'<svg class="chart" viewBox="0 0 {ancho} {alto}" role="img" aria-label="{_esc(titulo_aria)}" '
           f'data-chart="{_payload(idx, series, unidad)}" data-ml="{ml:.0f}" data-mr="{mr}" data-mt="{mt}" data-h="{h}">']
    if leyenda:
        lx = ml
        for s in series:
            muestra = (f'<line x1="{lx:.0f}" x2="{lx + 18:.0f}" y1="10" y2="10" style="stroke:{s["color"]};stroke-width:2"'
                       + (' stroke-dasharray="5 4"' if s.get("dash") else "") + "/>")
            out.append(muestra + f'<text class="lbl-nom" x="{lx + 24:.0f}" y="14">{_esc(s["nombre"])}</text>')
            lx += 40 + 6.2 * len(s["nombre"])
    for v in yt:
        y = Y(v)
        cls = "zero" if abs(v) < 1e-9 else "grid"
        out.append(f'<line class="{cls}" x1="{ml:.0f}" x2="{ml + w:.0f}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(f'<text class="tick" x="{ml - 6:.0f}" y="{y + 4:.1f}" text-anchor="end">{num(v, d)}</text>')
    for t, lbl in _xticks(idx):
        x = X(t)
        out.append(f'<line class="xtick" x1="{x:.1f}" x2="{x:.1f}" y1="{mt + h}" y2="{mt + h + 4}"/>')
        out.append(f'<text class="tick" x="{x:.1f}" y="{mt + h + 17}" text-anchor="middle">{lbl}</text>')
    finales = []
    for s in series:
        ss = s["s"].dropna()
        pts = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in ss.items())
        dash = ' stroke-dasharray="5 4"' if s.get("dash") else ""
        out.append(f'<polyline class="serie" style="stroke:{s["color"]}"{dash} points="{pts}"/>')
        if s.get("etiqueta", True):
            finales.append([Y(ss.iloc[-1]), s, ss])
    finales.sort(key=lambda f: f[0])
    pos = [f[0] for f in finales]
    for i in range(1, len(pos)):
        pos[i] = max(pos[i], pos[i - 1] + 26)
    exceso = pos[-1] - (mt + h + 4) if pos else 0
    if exceso > 0:
        pos = [p - exceso for p in pos]
        for i in range(len(pos) - 2, -1, -1):
            pos[i] = min(pos[i], pos[i + 1] - 26)
    for (yv, s, ss), yl in zip(finales, pos):
        x = X(ss.index[-1])
        out.append(f'<circle class="punto" cx="{x:.1f}" cy="{yv:.1f}" r="4" style="fill:{s["color"]}"/>')
        out.append(f'<text class="lbl-val" x="{x + 10:.1f}" y="{yl + 1:.1f}">{num(ss.iloc[-1], dec_lbl)}{_esc(sufijo)}</text>')
        out.append(f'<text class="lbl-nom" x="{x + 10:.1f}" y="{yl + 13:.1f}">'
                   f'<tspan class="sw" style="fill:{s["color"]}">■</tspan> {_esc(s["nombre"])}</text>')
    out.append(f'<rect class="hit" x="{ml:.0f}" y="{mt}" width="{w:.0f}" height="{h}"/>')
    out.append("</svg>")
    return "".join(out)


def columnas(s: pd.Series, unidad="%", alto=220, ancho=640, dec=1, titulo_aria="",
             nombre="Variación mensual", etiqueta_x=None) -> str:
    """Columnas por período; la última se destaca y lleva etiqueta.
    etiqueta_x(t) -> texto o None decide qué períodos llevan rótulo en el eje."""
    s = s.dropna()
    idx = s.index
    etiqueta_x = etiqueta_x or (lambda t: f"{MES3[t.month - 1]}-{str(t.year)[2:]}" if t.month in (1, 4, 7, 10) else None)
    yt = _ticks(min(0, s.min()), max(0, s.max()))
    d = _dec(yt)
    ml = _margen_izq([num(v, d) for v in yt])
    mr, mt, mb = 16, 18, 26
    w, h = ancho - ml - mr, alto - mt - mb
    y0, y1 = yt[0], yt[-1]
    Y = lambda v: mt + h * (1 - (v - y0) / (y1 - y0))
    paso = w / len(s)
    bw = max(paso - 2, 1)  # 2px de separación entre barras
    serie = [{"nombre": nombre, "s": s, "color": "var(--s1)"}]
    out = [f'<svg class="chart" viewBox="0 0 {ancho} {alto}" role="img" aria-label="{_esc(titulo_aria)}" '
           f'data-chart="{_payload(idx, serie, unidad)}" data-ml="{ml:.0f}" data-mr="{mr}" data-mt="{mt}" data-h="{h}" data-bars="1">']
    for v in yt:
        y = Y(v)
        out.append(f'<line class="{"zero" if abs(v) < 1e-9 else "grid"}" x1="{ml:.0f}" x2="{ml + w:.0f}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(f'<text class="tick" x="{ml - 6:.0f}" y="{y + 4:.1f}" text-anchor="end">{num(v, d)}</text>')
    rotulos = []
    for i, (t, v) in enumerate(s.items()):
        x = ml + i * paso + 1
        ya, yb = sorted([Y(v), Y(0)])
        r = min(3, bw / 2, yb - ya)
        cls = "bar ult" if i == len(s) - 1 else "bar"
        if v >= 0:
            p = (f"M{x:.1f},{yb:.1f} V{ya + r:.1f} Q{x:.1f},{ya:.1f} {x + r:.1f},{ya:.1f} "
                 f"H{x + bw - r:.1f} Q{x + bw:.1f},{ya:.1f} {x + bw:.1f},{ya + r:.1f} V{yb:.1f} Z")
        else:
            p = (f"M{x:.1f},{ya:.1f} V{yb - r:.1f} Q{x:.1f},{yb:.1f} {x + r:.1f},{yb:.1f} "
                 f"H{x + bw - r:.1f} Q{x + bw:.1f},{yb:.1f} {x + bw:.1f},{yb - r:.1f} V{ya:.1f} Z")
        out.append(f'<path class="{cls}" d="{p}"/>')
        lbl = etiqueta_x(t)
        if lbl:
            rotulos.append((x + bw / 2, lbl))
    # rótulos del eje: si dos se pisan, se descarta el anterior (el del último dato siempre queda)
    libre = float("inf")
    for cx, lbl in reversed(rotulos):
        mitad = len(lbl) * 3.6 + 3          # ancho aproximado del texto a 11 px, más un margen
        if cx + mitad <= libre:
            out.append(f'<text class="tick" x="{cx:.1f}" y="{mt + h + 17}" text-anchor="middle">{lbl}</text>')
            libre = cx - mitad
    xv = ml + (len(s) - 1) * paso + 1 + bw / 2
    yv = Y(max(s.iloc[-1], 0)) - 5 if s.iloc[-1] >= 0 else Y(s.iloc[-1]) + 14
    out.append(f'<text class="lbl-val" x="{xv:.1f}" y="{yv:.1f}" text-anchor="middle">{num(s.iloc[-1], dec)}</text>')
    out.append(f'<rect class="hit" x="{ml:.0f}" y="{mt}" width="{w:.0f}" height="{h}"/>')
    out.append("</svg>")
    return "".join(out)


def columnas_grupo(cats: list[str], series: list[dict], unidad="%", alto=230, ancho=640, dec=1,
                   titulo_aria="") -> str:
    """Columnas agrupadas por categoría. series = [{"nombre", "v": [..], "color"}]; None = sin dato."""
    vals = [v for s in series for v in s["v"] if v is not None]
    yt = _ticks(min(0, min(vals)), max(0, max(vals)))
    d = _dec(yt)
    ml = _margen_izq([num(v, d) for v in yt])
    mr, mt, mb = 16, 34, 26
    w, h = ancho - ml - mr, alto - mt - mb
    y0, y1 = yt[0], yt[-1]
    Y = lambda v: mt + h * (1 - (v - y0) / (y1 - y0))
    out = [f'<svg class="chart" viewBox="0 0 {ancho} {alto}" role="img" aria-label="{_esc(titulo_aria)}">']
    # leyenda arriba
    lx = ml
    for s in series:
        out.append(f'<text class="lbl-nom" x="{lx:.0f}" y="14"><tspan style="fill:{s["color"]}">■</tspan> {_esc(s["nombre"])}</text>')
        lx += 22 + 6.2 * len(s["nombre"])
    for v in yt:
        y = Y(v)
        out.append(f'<line class="{"zero" if abs(v) < 1e-9 else "grid"}" x1="{ml:.0f}" x2="{ml + w:.0f}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(f'<text class="tick" x="{ml - 6:.0f}" y="{y + 4:.1f}" text-anchor="end">{num(v, d)}</text>')
    grupo = w / len(cats)
    bw = min(46, (grupo * 0.7) / len(series) - 2)
    for i, c in enumerate(cats):
        x0 = ml + i * grupo + (grupo - (bw + 2) * len(series)) / 2
        out.append(f'<text class="tick" x="{ml + (i + .5) * grupo:.1f}" y="{mt + h + 17}" text-anchor="middle">{_esc(c)}</text>')
        for j, s in enumerate(series):
            v = s["v"][i]
            if v is None:
                continue
            x = x0 + j * (bw + 2)
            ya, yb = sorted([Y(v), Y(0)])
            r = min(3, bw / 2, yb - ya)
            if v >= 0:
                p = (f"M{x:.1f},{yb:.1f} V{ya + r:.1f} Q{x:.1f},{ya:.1f} {x + r:.1f},{ya:.1f} "
                     f"H{x + bw - r:.1f} Q{x + bw:.1f},{ya:.1f} {x + bw:.1f},{ya + r:.1f} V{yb:.1f} Z")
                yl = ya - 5
            else:
                p = (f"M{x:.1f},{ya:.1f} V{yb - r:.1f} Q{x:.1f},{yb:.1f} {x + r:.1f},{yb:.1f} "
                     f"H{x + bw - r:.1f} Q{x + bw:.1f},{yb:.1f} {x + bw:.1f},{yb - r:.1f} V{ya:.1f} Z")
                yl = yb + 13
            out.append(f'<path d="{p}" style="fill:{s["color"]}"><title>{_esc(s["nombre"])} · {_esc(c)}: {num(v, dec, True)}</title></path>')
            out.append(f'<text class="lbl-val" x="{x + bw / 2:.1f}" y="{yl:.1f}" text-anchor="middle">{num(v, dec, True)}</text>')
    out.append("</svg>")
    return "".join(out)


def barras_h(cats: list[str], vals: list[float], unidad="%", ancho=640, dec=1, titulo_aria="",
             notas: dict | None = None, ml=230) -> str:
    """Barras horizontales con polaridad (azul positivo, rojo negativo), ordenadas."""
    notas = notas or {}
    fila = 22
    mr, mt, mb = 60, 6, 22
    alto = mt + mb + fila * len(cats)
    w = ancho - ml - mr
    finitos = [v for c, v in zip(cats, vals) if c not in notas]
    lo, hi = min(0, min(finitos)), max(0, max(finitos))
    pad = (hi - lo) * 0.12   # aire para las etiquetas de valor en los extremos
    xt = _ticks(lo - (pad if lo < 0 else 0), hi + (pad if hi > 0 else 0), 4)
    x0, x1 = xt[0], xt[-1]
    X = lambda v: ml + w * (v - x0) / (x1 - x0)
    out = [f'<svg class="chart" viewBox="0 0 {ancho} {alto}" role="img" aria-label="{_esc(titulo_aria)}">']
    for v in xt:
        out.append(f'<line class="{"zero" if abs(v) < 1e-9 else "grid"}" x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{mt}" y2="{alto - mb}"/>')
        out.append(f'<text class="tick" x="{X(v):.1f}" y="{alto - mb + 15}" text-anchor="middle">{num(v, _dec(xt))}</text>')
    for i, (c, v) in enumerate(zip(cats, vals)):
        y = mt + i * fila + 3
        bh = fila - 6
        out.append(f'<text class="cat" x="{ml - 8}" y="{y + bh / 2 + 4:.1f}" text-anchor="end">{_esc(c)}</text>')
        if c in notas:
            out.append(f'<text class="lbl-nota" x="{X(0) + 6:.1f}" y="{y + bh / 2 + 4:.1f}">{_esc(notas[c])}</text>')
            continue
        xa, xb = sorted([X(0), X(v)])
        r = min(3, (xb - xa) / 2, bh / 2)
        if v >= 0:
            p = (f"M{xa:.1f},{y:.1f} H{xb - r:.1f} Q{xb:.1f},{y:.1f} {xb:.1f},{y + r:.1f} "
                 f"V{y + bh - r:.1f} Q{xb:.1f},{y + bh:.1f} {xb - r:.1f},{y + bh:.1f} H{xa:.1f} Z")
            lx, anc = xb + 5, "start"
        else:
            p = (f"M{xb:.1f},{y:.1f} H{xa + r:.1f} Q{xa:.1f},{y:.1f} {xa:.1f},{y + r:.1f} "
                 f"V{y + bh - r:.1f} Q{xa:.1f},{y + bh:.1f} {xa + r:.1f},{y + bh:.1f} H{xb:.1f} Z")
            lx, anc = xa - 5, "end"
        cls = "pos" if v >= 0 else "neg"
        out.append(f'<path class="hbar {cls}" d="{p}"><title>{_esc(c)}: {num(v, dec, True)}{unidad}</title></path>')
        out.append(f'<text class="lbl-val" x="{lx:.1f}" y="{y + bh / 2 + 4:.1f}" text-anchor="{anc}">{num(v, dec, True)}</text>')
    out.append("</svg>")
    return "".join(out)


def barras_nivel(cats: list[str], vals: list[float], previos: list[float], nombre_ref: str, ref: float,
                 nombre_actual: str, nombre_previo: str, unidad="%", ancho=640, dec=1, titulo_aria="", ml=230,
                 destacar: str | None = None) -> str:
    """Barras horizontales de nivel (0 a 100), con una marca para el valor previo de cada categoría y una
    línea vertical de referencia (por ejemplo, el nivel general). `destacar` pinta esa categoría distinta."""
    fila = 22
    mr, mt, mb = 40, 34, 22
    alto = mt + mb + fila * len(cats)
    w = ancho - ml - mr
    x0, x1 = 0, 100
    X = lambda v: ml + w * (v - x0) / (x1 - x0)
    out = [f'<svg class="chart" viewBox="0 0 {ancho} {alto}" role="img" aria-label="{_esc(titulo_aria)}">']
    out.append(f'<text class="lbl-nom" x="{ml}" y="14"><tspan style="fill:var(--s1)">■</tspan> {_esc(nombre_actual)}</text>')
    lx = ml + 30 + 6.2 * len(nombre_actual)
    out.append(f'<text class="lbl-nom" x="{lx:.0f}" y="14"><tspan style="fill:var(--ink)">┃</tspan> {_esc(nombre_previo)}</text>')
    lx += 30 + 6.2 * len(nombre_previo)
    out.append(f'<text class="lbl-nom" x="{lx:.0f}" y="14"><tspan style="fill:var(--s2)">┆</tspan> {_esc(nombre_ref)} ({num(ref, dec)})</text>')
    for v in range(0, 101, 20):
        out.append(f'<line class="{"zero" if v == 0 else "grid"}" x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{mt}" y2="{alto - mb}"/>')
        out.append(f'<text class="tick" x="{X(v):.1f}" y="{alto - mb + 15}" text-anchor="middle">{v}</text>')
    out.append(f'<line x1="{X(ref):.1f}" x2="{X(ref):.1f}" y1="{mt - 4}" y2="{alto - mb}" '
               f'style="stroke:var(--s2);stroke-width:1.5;stroke-dasharray:4 3"/>')
    for i, (c, v, p) in enumerate(zip(cats, vals, previos)):
        y = mt + i * fila + 3
        bh = fila - 6
        out.append(f'<text class="cat" x="{ml - 8}" y="{y + bh / 2 + 4:.1f}" text-anchor="end">{_esc(c)}</text>')
        xa, xb = X(0), X(v)
        r = min(3, (xb - xa) / 2, bh / 2)
        d = (f"M{xa:.1f},{y:.1f} H{xb - r:.1f} Q{xb:.1f},{y:.1f} {xb:.1f},{y + r:.1f} "
             f"V{y + bh - r:.1f} Q{xb:.1f},{y + bh:.1f} {xb - r:.1f},{y + bh:.1f} H{xa:.1f} Z")
        color = "var(--s4)" if c == destacar else "var(--s1)"
        tip = f"{_esc(c)}: {num(v, dec)}{unidad}" + (f" (un año antes: {num(p, dec)}{unidad})" if p is not None else "")
        out.append(f'<path d="{d}" style="fill:{color}"><title>{tip}</title></path>')
        if p is not None and not math.isnan(p):
            out.append(f'<line x1="{X(p):.1f}" x2="{X(p):.1f}" y1="{y - 2:.1f}" y2="{y + bh + 2:.1f}" '
                       f'style="stroke:var(--ink);stroke-width:2"/>')
        lx = max(xb, X(p) if p is not None else xb) + 6
        etiqueta = num(v, dec)
        # fondo del color del papel: tapa la línea de referencia que pasa por detrás de la etiqueta
        out.append(f'<rect x="{lx - 2:.1f}" y="{y:.1f}" width="{7.5 * len(etiqueta) + 4:.1f}" height="{bh:.1f}" '
                   f'style="fill:var(--paper)"/>')
        out.append(f'<text class="lbl-val" x="{lx:.1f}" y="{y + bh / 2 + 4:.1f}">{etiqueta}</text>')
    out.append("</svg>")
    return "".join(out)


def chispa(s: pd.Series, ancho=120, alto=30) -> str:
    """Sparkline para el tablero."""
    s = s.dropna()
    lo, hi = s.min(), s.max()
    hi = hi if hi > lo else lo + 1
    pts = [(2 + (ancho - 6) * i / max(len(s) - 1, 1), 3 + (alto - 6) * (1 - (v - lo) / (hi - lo)))
           for i, v in enumerate(s.values)]
    p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    x, y = pts[-1]
    return (f'<svg class="chispa" viewBox="0 0 {ancho} {alto}" aria-hidden="true">'
            f'<polyline points="{p}"/><circle cx="{x:.1f}" cy="{y:.1f}" r="2.6"/></svg>')
