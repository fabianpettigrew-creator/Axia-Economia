# -*- coding: utf-8 -*-
"""Grafico destacado de la portada (seccion Estudios).

Dibuja solo el area de datos: el titulo, la unidad y la fuente son texto HTML en
index.html, asi quedan en la tipografia del sitio, se traducen al ingles y los lee
un lector de pantalla. El estilo sale de axia_marca.py, el del manual de marca.

No lo corre la automatizacion: el grafico destacado es una decision editorial y se
cambia a mano cuando sale un estudio nuevo. Para regenerarlo hay que usar el Python
que tiene matplotlib instalado, el de AppData\\Local\\Python\\bin:

    python _automatizacion/graficos/destacado.py

Si se cambia el grafico, hay que cambiar tambien el titulo y la bajada en
index.html, que son los que dicen la conclusion.
"""
import json
import sys
from pathlib import Path

MANUAL = Path("B:/Onedrive/Logos/Fabian Pettigrew/Logo para consultora econ\u00f3mica/Manual de marca")
sys.path.append(str(MANUAL))

import axia_marca  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "graficos" / "ipc-mensual.png"
MESES = ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]


def serie_ipc(n=24):
    """Ultimos n meses del IPC, del mismo archivo que alimenta el tablero."""
    texto = (RAIZ / "tablero" / "datos.js").read_text(encoding="utf-8")
    datos = json.loads(texto[texto.index("{"):texto.rindex(";")])
    s = datos["secciones"]["precios"]["mensual"]["Nivel general"]
    return s["x"][-n:], s["y"][-n:]


def main():
    x, y = serie_ipc()
    axia_marca.aplicar()
    fig, ax = plt.subplots(figsize=(9.6, 3.4))

    colores = [axia_marca.MARINO] * len(y)
    colores[-1] = axia_marca.BRONCE          # el ultimo dato, en acento
    ax.bar(range(len(y)), y, color=colores, width=.66)

    ax.set_xticks(range(len(y)))
    ax.set_xticklabels([MESES[int(f.split("-")[1]) - 1] for f in x], fontsize=9)
    for i, f in enumerate(x):                # el anio, una vez, debajo de enero
        if f.endswith("-01-01") or i == 0:
            ax.annotate(f[:4], (i, 0), xytext=(0, -27), textcoords="offset points",
                        ha="center", fontsize=9, color=axia_marca.PIZARRA)

    ax.yaxis.set_major_formatter(axia_marca.coma_decimal(1))
    ax.set_ylim(0, max(y) * 1.16)
    ax.annotate(("%.1f" % y[-1]).replace(".", ",") + "%", (len(y) - 1, y[-1]),
                xytext=(0, 7), textcoords="offset points", ha="center",
                fontsize=11, fontweight=600, color=axia_marca.BRONCE)

    SALIDA.parent.mkdir(exist_ok=True)
    fig.savefig(SALIDA, dpi=190, bbox_inches="tight", facecolor="white", pad_inches=.12)
    print("Escrito:", SALIDA, "(%.0f KB)" % (SALIDA.stat().st_size / 1024))


if __name__ == "__main__":
    main()
