# -*- coding: utf-8 -*-
"""Grafico destacado de la portada (seccion Estudios).

Escribe el grafico como SVG dentro de index.html, entre las marcas
<!-- grafico-destacado --> y <!-- /grafico-destacado -->. Va inline y no como
imagen porque cada barra muestra su valor al pasar el mouse, y eso necesita
hover sobre la barra: una <img> no lo da. De paso el texto queda en la
tipografia del sitio, se traduce al ingles y lo lee un lector de pantalla.

El titulo, la unidad y la fuente siguen siendo texto HTML, fuera del SVG.

No lo corre la automatizacion: el grafico destacado es una decision editorial y
se cambia a mano cuando sale un estudio nuevo. Para regenerarlo:

    python _automatizacion/graficos/destacado.py

Si se cambia el grafico, hay que cambiar tambien el titulo y la bajada en
index.html, que son los que dicen la conclusion.
"""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PAGINA = RAIZ / "index.html"
INI, FIN = "<!-- grafico-destacado -->", "<!-- /grafico-destacado -->"

# Manual de marca: marino la serie, bronce el ultimo dato, piedra el eje.
MARINO, BRONCE, PIZARRA, PIEDRA, MARFIL = "#1a2233", "#b8874a", "#6a7382", "#ddd6c9", "#f7f4ee"

MES_ES = "ene feb mar abr may jun jul ago sep oct nov dic".split()
MES_EN = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
INICIAL_ES, INICIAL_EN = "EFMAMJJASOND", "JFMAMJJASOND"

ANCHO, ALTO = 1000, 400                  # unidades del viewBox; la figura escala al ancho
IZQ, DER, ARR, ABA = 40, 8, 34, 56       # margenes: izq para el eje, arr para el rotulo bronce
PLANCHO, PALTO = ANCHO - IZQ - DER, ALTO - ARR - ABA
BASE = ARR + PALTO


def serie_ipc(n=24):
    """Ultimos n meses del IPC, del mismo archivo que alimenta el tablero."""
    texto = (RAIZ / "tablero" / "datos.js").read_text(encoding="utf-8")
    datos = json.loads(texto[texto.index("{"):texto.rindex(";")])
    s = datos["secciones"]["precios"]["mensual"]["Nivel general"]
    return list(zip(s["x"][-n:], s["y"][-n:]))


def num(v, dec=1, en=False):
    t = "%.*f" % (dec, v)
    return t if en else t.replace(".", ",")


def dibujar(datos):
    tope = max(v for _, v in datos) * 1.16
    paso, ab = PLANCHO / len(datos), PLANCHO / len(datos) * .66
    p = []

    # Eje vertical: solo los rotulos y la linea del cero. Sin lineas horizontales
    # de guia: con 24 barras ya se lee el nivel, y el fondo queda limpio.
    for t in range(int(tope) + 1):
        y = BASE - t / tope * PALTO
        p.append(f'<text class="gd-ej gd-es" x="{IZQ - 10}" y="{y + 4:.1f}">{num(t)}</text>'
                 f'<text class="gd-ej gd-en" x="{IZQ - 10}" y="{y + 4:.1f}">{num(t, en=True)}</text>')
    p.append(f'<line x1="{IZQ - 6}" y1="{BASE}" x2="{ANCHO - DER}" y2="{BASE}" stroke="{PIEDRA}"/>')

    for i, (f, v) in enumerate(datos):
        anio, mes = int(f[:4]), int(f[5:7])
        cx = IZQ + paso * (i + .5)
        h = v / tope * PALTO
        y = BASE - h
        ultimo = i == len(datos) - 1
        es, en = f"{MES_ES[mes - 1]}-{str(anio)[2:]}", f"{MES_EN[mes - 1]}-{str(anio)[2:]}"

        # La leyenda se centra en la barra, pero no se sale del dibujo.
        tx = min(max(cx - 54, 2), ANCHO - 110)
        ty = y - 40

        p.append(f'<g class="gd-b" role="img" aria-label="{es}: {num(v)}%">')
        p.append(f'<rect class="gd-hit" x="{cx - paso / 2:.1f}" y="{ARR}" width="{paso:.1f}" height="{PALTO + 8}"/>')
        p.append(f'<rect class="gd-bar" x="{cx - ab / 2:.1f}" y="{y:.1f}" width="{ab:.1f}" height="{h:.1f}" '
                 f'fill="{BRONCE if ultimo else MARINO}"/>')
        if ultimo:                        # el dato nuevo lleva su cifra a la vista
            p.append(f'<text class="gd-etq gd-es" x="{cx:.1f}" y="{y - 9:.1f}">{num(v)}%</text>'
                     f'<text class="gd-etq gd-en" x="{cx:.1f}" y="{y - 9:.1f}">{num(v, en=True)}%</text>')
        p.append(f'<g class="gd-tip"><rect x="{tx:.1f}" y="{ty:.1f}" width="108" height="28" rx="4" fill="{MARINO}"/>'
                 f'<text class="gd-tt gd-es" x="{tx + 54:.1f}" y="{ty + 18.5:.1f}">{es} &#183; {num(v)}%</text>'
                 f'<text class="gd-tt gd-en" x="{tx + 54:.1f}" y="{ty + 18.5:.1f}">{en} &#183; {num(v, en=True)}%</text>'
                 '</g></g>')

        p.append(f'<text class="gd-mes gd-es" x="{cx:.1f}" y="{BASE + 22}">{INICIAL_ES[mes - 1]}</text>'
                 f'<text class="gd-mes gd-en" x="{cx:.1f}" y="{BASE + 22}">{INICIAL_EN[mes - 1]}</text>')
        if mes == 1 or i == 0:            # el anio, una vez, debajo de enero
            p.append(f'<text class="gd-anio" x="{cx:.1f}" y="{BASE + 44}">{anio}</text>')

    return "\n".join(p)


ESTILO = f"""<style>
  .gd-ej,.gd-mes,.gd-anio{{fill:{PIZARRA};font-size:12px}}
  .gd-ej{{text-anchor:end}}
  .gd-mes,.gd-anio{{text-anchor:middle}}
  .gd-etq{{fill:{BRONCE};font-size:14px;font-weight:600;text-anchor:middle;transition:opacity .12s}}
  .gd-hit{{fill:#fff;fill-opacity:0}}
  .gd-bar{{transition:fill-opacity .12s}}
  .gd-tip{{opacity:0;transition:opacity .12s;pointer-events:none}}
  .gd-tt{{fill:{MARFIL};font-size:13px;font-weight:500;text-anchor:middle}}
  .gd-b:hover .gd-tip{{opacity:1}}
  .gd-b:hover .gd-bar{{fill-opacity:.8}}
  .gd-b:hover .gd-etq{{opacity:0}}
  .gd-en{{display:none}}
  html[data-lang="en"] .gd-es{{display:none}}
  html[data-lang="en"] .gd-en{{display:inline}}
</style>"""


def main():
    datos = serie_ipc()
    ultimo = datos[-1][0]
    svg = (f'<svg viewBox="0 0 {ANCHO} {ALTO}" role="img" '
           f'aria-label="Inflaci&#243;n mensual de los &#250;ltimos dos a&#241;os, '
           f'en porcentaje; el &#250;ltimo dato es de {MES_ES[int(ultimo[5:7]) - 1]}-{ultimo[2:4]}" '
           f'style="display:block;width:100%;height:auto;margin:clamp(14px,2vw,22px) 0 10px;'
           f'font-family:Manrope,system-ui,sans-serif">\n{ESTILO}\n{dibujar(datos)}\n</svg>')

    pagina = PAGINA.read_text(encoding="utf-8")
    a, b = pagina.index(INI), pagina.index(FIN)
    PAGINA.write_text(pagina[:a + len(INI)] + "\n" + svg + "\n          " + pagina[b:], encoding="utf-8")
    print("Escrito en index.html:", len(svg), "caracteres, ultimo dato", ultimo)


if __name__ == "__main__":
    main()
