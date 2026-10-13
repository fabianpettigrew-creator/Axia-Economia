"""Actualización diaria del tablero de axiaeconomia.ar.

Corre en dos lugares con el mismo código:
  - GitHub Actions (principal): .github/workflows/tablero.yml del repositorio del sitio, sobre la copia en
    _automatizacion/ que deja `sincronizar_ci.py`. Ahí el commit y el push los hace el workflow.
  - Esta computadora (respaldo): tarea de Windows "AXIA - Tablero diario".

    py actualizar_diario.py               # baja datos, regenera, copia al sitio, commit y push
    py actualizar_diario.py --sin-push    # todo menos el push (para probar)
    python actualizar_diario.py --sitio . --sin-git   # modo GitHub Actions: sin git y con salida por consola

Pasos: 1) vintage del día del Boletín (APIs), 2) preparar_datos.py, 3) controles mínimos, 4) copia a
<sitio>/tablero/, 5) commit y push solo de tablero/. Si algo falla, no publica.
En la computadora deja un registro en tablero/logs/AAAA-MM-DD.log (se guardan los últimos 30).
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

AQUI = Path(__file__).parent
SITIO = Path("B:/Onedrive/Logos/Fabian Pettigrew/Sitio web AXIA")
LOGS = AQUI / "logs"
SEMILLA = AQUI.parent / "semilla"   # solo en _automatizacion/: último vintage conocido, para el primer uso en GitHub
sys.path.insert(0, str(AQUI.parent / "boletin"))
for _s in (sys.stdout, sys.stderr):   # con pyw.exe (sin ventana) no hay consola: todo va al log
    if _s is not None:
        _s.reconfigure(encoding="utf-8")


def git(*args) -> str:
    r = subprocess.run(["git", "-C", str(SITIO), *args], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def controlar(hoy: str):
    """Antes de publicar: datos.js completo, del día y con todas las secciones."""
    t = (AQUI / "demo" / "datos.js").read_text(encoding="utf-8")
    d = json.loads(t[len("window.DATOS = "):].rstrip().rstrip(";"))
    faltan = {"tipo-cambio", "precios", "actividad", "empleo", "comercio", "monetarias", "mercados", "internacional"} - set(d["secciones"])
    if faltan:
        raise RuntimeError(f"faltan secciones en datos.js: {sorted(faltan)}")
    if d["actualizado"] != hoy:
        raise RuntimeError(f"datos.js dice {d['actualizado']}, se esperaba {hoy}")
    if len(t) < 500_000:
        raise RuntimeError(f"datos.js demasiado chico ({len(t)} bytes)")


def sembrar(vintages: Path):
    """Sin vintages previos (primer uso en GitHub o caché vencida): parte del último vintage conocido,
    para poder rellenar lo que la API no devuelva y las series que solo existen en la computadora (pobreza)."""
    if any(vintages.glob("2*.csv")) or not SEMILLA.exists():
        return
    vintages.mkdir(parents=True, exist_ok=True)
    for gz in SEMILLA.glob("*.csv.gz"):
        with gzip.open(gz, "rb") as f, open(vintages / gz.name.removesuffix(".gz"), "wb") as g:
            shutil.copyfileobj(f, g)
        print("Semilla:", gz.name)


def podar(vintages: Path, dejar=3):
    """En GitHub los vintages viven en la caché de Actions: alcanza con los últimos días."""
    for patron in ("2*.csv", "rem_2*.csv"):
        for viejo in sorted(vintages.glob(patron))[:-dejar]:
            viejo.unlink()


class Avisos:
    """Copia la salida al destino de siempre y junta las líneas AVISO (series que no respondieron)."""
    def __init__(self, destino):
        self.destino, self.lineas, self._buf = destino, [], ""
    def write(self, t):
        self.destino.write(t)
        self._buf += t
        *completas, self._buf = self._buf.split("\n")
        self.lineas += [x.strip() for x in completas if x.startswith("AVISO")]
    def flush(self):
        self.destino.flush()


def escribir_estado(avisos: list[str], origen: str):
    """tablero/estado.json: cuándo y dónde corrió la actualización y qué series se rellenaron con el día anterior."""
    import re
    rellenas = sorted({m.group(1) for a in avisos if (m := re.match(r"AVISO: (\w+): \d+ dato", a))})
    estado = {"actualizado": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "origen": origen,
              "series_rellenas_con_el_dia_anterior": rellenas,
              "otros_avisos": [a for a in avisos if not re.match(r"AVISO: \w+: \d+ dato", a)]}
    (SITIO / "tablero" / "estado.json").write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")


def main(push: bool, usar_git: bool, nube: bool):
    import datos
    import preparar_datos

    hoy = dt.date.today().isoformat()
    print(f"== Actualización del tablero {dt.datetime.now():%Y-%m-%d %H:%M}")
    if usar_git:
        git("pull", "--ff-only", "-q")        # por si se subieron cambios al sitio desde otro lado
    sembrar(datos.VINTAGES)
    avisos = Avisos(sys.stdout)
    sys.stdout = avisos
    try:
        print("Vintage:", datos.actualizar(forzar=True))
    finally:
        sys.stdout = avisos.destino
    preparar_datos.main()
    controlar(hoy)
    preparar_datos.publicar(SITIO)
    escribir_estado(avisos.lineas, "GitHub Actions" if nube else "computadora de AXIA")
    if nube:
        podar(datos.VINTAGES)
    if not usar_git:
        return
    git("add", "tablero/index.html", "tablero/datos.js", "tablero/estado.json")
    if not git("diff", "--cached", "--name-only"):
        print("Sin cambios en el tablero: no hay nada que publicar")
    else:
        git("commit", "-q", "-m", f"Tablero: datos al {hoy} (actualización automática)")
        print("Commit:", git("log", "--oneline", "-1"))
    if push and git("rev-list", "--count", "origin/main..HEAD") != "0":
        git("push", "-q", "origin", "main")
        print("Push hecho: axiaeconomia.ar/tablero/ se actualiza en uno o dos minutos")
    elif not push:
        print("Sin push (--sin-push)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-push", action="store_true")
    ap.add_argument("--sin-git", action="store_true", help="no hace pull/commit/push (en GitHub los hace el workflow)")
    ap.add_argument("--sitio", type=Path, default=None, help="raíz del sitio (por defecto, la copia local)")
    a = ap.parse_args()
    if a.sitio:
        SITIO = a.sitio.resolve()
    if a.sin_git:   # modo GitHub Actions: salida por consola, error = workflow en rojo
        main(push=False, usar_git=False, nube=True)
        sys.exit(0)
    LOGS.mkdir(exist_ok=True)
    log = LOGS / f"{dt.date.today().isoformat()}.log"
    with open(log, "a", encoding="utf-8") as f:
        sys.stdout = sys.stderr = f
        try:
            main(push=not a.sin_push, usar_git=True, nube=False)
            print("OK")
        except Exception:
            print("ERROR: no se publicó nada nuevo")
            traceback.print_exc()
            sys.exit(1)
        finally:
            for viejo in sorted(LOGS.glob("*.log"))[:-30]:
                viejo.unlink()
