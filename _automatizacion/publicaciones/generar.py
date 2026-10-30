#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera la seccion /publicaciones del sitio de AXIA.

Que hace
--------
Lee estudios.txt (el mismo archivo que alimenta la seccion Estudios de la
portada) y escribe:

    publicaciones/index.html          indice con todos los estudios
    publicaciones/<slug>.html         una pagina por estudio

Cada pagina usa el encabezado, el pie y los estilos de index.html, asi que
si cambia el diseno de la portada, basta con volver a correr este script
para que las paginas queden iguales.

Como se corre
-------------
    python3 generar.py            (desde esta carpeta)

Ademas actualiza sitemap.xml: deja las direcciones fijas del sitio y vuelve a
escribir las de /publicaciones.

No toca index.html ni estudios.txt.
"""

import datetime
import html
import os
import re
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, "..", ".."))
SALIDA = os.path.join(RAIZ, "publicaciones")
SITIO = "https://axiaeconomia.ar"


# ---------------------------------------------------------------- utilidades

def slug(texto):
    """Convierte un titulo en un nombre de archivo: sin tildes, con guiones."""
    t = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:60] or "estudio"


def esc(t):
    return html.escape(t or "", quote=True)


def dos_idiomas(es, en, etiqueta="span"):
    """Devuelve el par de <span> que el sitio usa para alternar idioma."""
    en = en or es
    return ('<{t} data-es>{a}</{t}><{t} data-en>{b}</{t}>'
            .format(t=etiqueta, a=esc(es), b=esc(en)))


# ------------------------------------------------------------ leer estudios

def leer_estudios(ruta):
    with open(ruta, encoding="utf-8") as f:
        crudo = f.read()
    estudios = []
    for bloque in re.split(r"^\s*---\s*$", crudo, flags=re.M):
        datos = {}
        for linea in bloque.splitlines():
            if linea.strip().startswith("#"):
                continue
            if ":" not in linea:
                continue
            clave, valor = linea.split(":", 1)
            clave = unicodedata.normalize("NFD", clave.strip().lower())
            clave = clave.encode("ascii", "ignore").decode()
            datos[clave] = valor.strip()
        if datos.get("titulo"):
            datos["slug"] = datos.get("visor") or slug(datos["titulo"])
            estudios.append(datos)
    return estudios


# ------------------------------------------ piezas tomadas de la portada

def piezas_de_la_portada():
    """Saca el <head>, el <header> y el <footer> de index.html."""
    with open(os.path.join(RAIZ, "index.html"), encoding="utf-8") as f:
        s = f.read()
    cabeza = s[s.index("<head>") + len("<head>"):s.index("</head>")]
    encabezado = s[s.index("<header"):s.index("</header>") + len("</header>")]
    pie = s[s.index("<footer"):s.index("</footer>") + len("</footer>")]

    # en una subcarpeta, los enlaces de la portada necesitan subir un nivel
    def subir(t):
        t = t.replace('href="#', 'href="../#')
        t = t.replace('href="tablero/', 'href="../tablero/')
        t = t.replace('href="boletin/', 'href="../boletin/')
        t = t.replace('href="../#inicio"', 'href="../"')
        return t

    # el <head> de la portada trae etiquetas propias de la home
    cabeza = re.sub(r'\s*<meta property="og:(title|description|url)"[^>]*>', "", cabeza)
    cabeza = re.sub(r"\s*<title>.*?</title>", "", cabeza, flags=re.S)
    return cabeza, subir(encabezado), subir(pie)


GUION_IDIOMA = """
  <script>
  /* Alterna espanol / ingles, igual que la portada, y recuerda la eleccion. */
  (function(){
    function poner(l){
      document.documentElement.setAttribute('data-lang', l);
      document.documentElement.lang = l;
      try { localStorage.setItem('axia-lang', l); } catch(e){}
    }
    var guardado = null;
    try { guardado = localStorage.getItem('axia-lang'); } catch(e){}
    poner(guardado === 'en' ? 'en' : 'es');
    var b = document.getElementById('lang');
    if (b) b.addEventListener('click', function(){
      poner(document.documentElement.getAttribute('data-lang') === 'en' ? 'es' : 'en');
    });
  })();
  </script>
"""

ESTILO_PAGINA = """
  <style>
    .pub-envoltorio{max-width:860px;margin:0 auto;padding:clamp(48px,7vw,96px) clamp(20px,5vw,56px)}
    .pub-volver{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:600;color:#b8874a;text-decoration:none}
    .pub-sector{display:block;margin-top:clamp(28px,4vw,44px);font-size:11px;font-weight:600;letter-spacing:.24em;text-transform:uppercase;color:#b8874a}
    .pub-titulo{margin-top:14px;font-family:"Cormorant Garamond",Georgia,serif;font-weight:500;color:#1a2233;font-size:clamp(30px,4.4vw,50px);line-height:1.08;letter-spacing:-.01em;text-wrap:balance}
    .pub-fecha{display:block;margin-top:14px;font-size:13px;color:#6a7382;letter-spacing:.04em}
    .pub-resumen{margin-top:clamp(24px,3vw,34px);font-size:clamp(17px,1.4vw,19px);color:#49536a;line-height:1.75;text-wrap:pretty}
    .pub-acciones{margin-top:clamp(28px,3.4vw,40px);display:flex;flex-wrap:wrap;gap:14px;align-items:center}
    .pub-boton{display:inline-flex;align-items:center;gap:9px;border:1px solid #b8874a;border-radius:2px;color:#b8874a;font-size:14px;font-weight:600;padding:11px 18px;text-decoration:none;background:none}
    .pub-boton:hover{background:#b8874a;color:#fff}
    .pub-nota{margin-top:clamp(36px,4vw,52px);padding-top:22px;border-top:1px solid #ddd6c9;font-size:14px;color:#6a7382;text-wrap:pretty}
    .pub-lista{max-width:1160px;margin:0 auto;padding:clamp(48px,7vw,96px) clamp(20px,5vw,56px)}
    .pub-fila{display:grid;grid-template-columns:clamp(48px,6vw,86px) minmax(0,1fr) minmax(0,1.35fr);gap:clamp(16px,3vw,44px);padding:clamp(26px,3vw,38px) 0;border-top:1px solid #ddd6c9;align-items:start}
    .pub-fila:last-child{border-bottom:1px solid #ddd6c9}
    .pub-anio{font-family:"Cormorant Garamond",Georgia,serif;font-size:22px;color:#b8874a;line-height:1.3}
    .pub-fila h2{font-family:"Cormorant Garamond",Georgia,serif;font-weight:500;color:#1a2233;font-size:clamp(22px,2vw,27px);line-height:1.18}
    .pub-fila h2 a{color:inherit;text-decoration:none;border-bottom:1px solid #ddd6c9}
    .pub-fila h2 a:hover{border-bottom-color:#b8874a}
    .pub-fila .sec{display:block;margin-top:10px;font-size:11px;font-weight:600;letter-spacing:.2em;text-transform:uppercase;color:#6a7382}
    .pub-fila p{font-size:16px;color:#5d6676;text-wrap:pretty}
    @media (max-width:760px){
      .pub-fila{grid-template-columns:40px minmax(0,1fr);row-gap:10px}
      .pub-fila > :last-child{grid-column:2}
    }
  </style>
"""


MEDICION = """<!-- Medicion de visitas: Cloudflare Web Analytics (sin cookies) --><script type="module" src="https://static.cloudflareinsights.com/beacon.min.js" data-cf-beacon='{"token": "c58d5d2b14c147cebd409da8f1533168"}'></script>"""


def pagina(titulo_pestana, descripcion, url, cuerpo, cabeza, encabezado, pie):
    return """<!DOCTYPE html>
<html lang="es" data-lang="es">
<head>
<title>{titulo}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{titulo}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
{cabeza}
{estilo}
</head>
<body>
<div style="background:#f7f4ee;color:#232b3b;font-family:Manrope,system-ui,sans-serif;line-height:1.6">
{encabezado}
<main>
{cuerpo}
</main>
{pie}
</div>
{idioma}
{medicion}
</body>
</html>
""".format(titulo=esc(titulo_pestana), desc=esc(descripcion), url=esc(url),
           cabeza=cabeza.strip(), estilo=ESTILO_PAGINA, encabezado=encabezado,
           cuerpo=cuerpo, pie=pie, idioma=GUION_IDIOMA, medicion=MEDICION)


# ------------------------------------------------------------ armar paginas

def cuerpo_estudio(e):
    acciones = []
    if e.get("visor"):
        acciones.append(
            '<a class="pub-boton" href="../#estudio={slug}">'
            '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">'
            '<rect x="2.5" y="4" width="19" height="13.5" rx="1"></rect><path d="M9 21h6"></path><path d="M12 17.5V21"></path></svg>'
            '{texto}</a>'.format(
                slug=esc(e["visor"]),
                texto=dos_idiomas("Ver el estudio online", "View the study online")))
    for archivo in [a.strip() for a in (e.get("archivo") or "").split(";") if a.strip()]:
        acciones.append(
            '<a class="pub-boton" href="../estudios/{a}" target="_blank" rel="noopener">↓ {n}</a>'
            .format(a=esc(archivo), n=esc(archivo)))
    acciones.append('<a class="pub-boton" href="../#contacto">{}</a>'.format(
        dos_idiomas("Consultar por este estudio", "Ask about this study")))

    return """  <article class="pub-envoltorio">
    <a class="pub-volver" href="./">← {volver}</a>
    <span class="pub-sector">{sector}</span>
    <h1 class="pub-titulo">{titulo}</h1>
    <span class="pub-fecha">{anio}</span>
    <p class="pub-resumen">{resumen}</p>
    <div class="pub-acciones">{acciones}</div>
    <p class="pub-nota">{nota}</p>
  </article>
""".format(
        volver=dos_idiomas("Todos los estudios", "All studies"),
        sector=dos_idiomas(e.get("sector", ""), e.get("sector en", "")),
        titulo=dos_idiomas(e.get("titulo", ""), e.get("title", ""), "span"),
        anio=esc(e.get("ano") or e.get("anio") or ""),
        resumen=dos_idiomas(e.get("resumen", ""), e.get("summary", "")),
        acciones="\n      ".join(acciones),
        nota=dos_idiomas(
            "AXIA publica el resumen de cada estudio. El informe completo se entrega a los clientes del trabajo.",
            "AXIA publishes a summary of each study. The full report is delivered to the client of the engagement."))


def cuerpo_indice(estudios):
    filas = []
    for e in estudios:
        filas.append("""      <article class="pub-fila">
        <span class="pub-anio">{anio}</span>
        <div>
          <h2><a href="{slug}.html">{titulo}</a></h2>
          <span class="sec">{sector}</span>
        </div>
        <p>{resumen}</p>
      </article>""".format(
            anio=esc(e.get("ano") or e.get("anio") or "—"),
            slug=esc(e["slug"]),
            titulo=dos_idiomas(e.get("titulo", ""), e.get("title", "")),
            sector=dos_idiomas(e.get("sector", ""), e.get("sector en", "")),
            resumen=dos_idiomas(e.get("resumen", ""), e.get("summary", ""))))

    return """  <div class="pub-lista">
    <a class="pub-volver" href="../">← {volver}</a>
    <span class="pub-sector">{kicker}</span>
    <h1 class="pub-titulo">{titulo}</h1>
    <p class="pub-resumen" style="max-width:62ch">{bajada}</p>
    <div style="margin-top:clamp(32px,4vw,52px)">
{filas}
    </div>
  </div>
""".format(
        volver=dos_idiomas("Inicio", "Home"),
        kicker=dos_idiomas("Estudios", "Studies"),
        titulo=dos_idiomas("Estudios de AXIA", "AXIA studies"),
        bajada=dos_idiomas(
            "Resúmenes de los estudios realizados por AXIA. Cada ficha enlaza al resumen completo; el informe original se entrega al cliente del trabajo.",
            "Summaries of the studies carried out by AXIA. Each entry links to the full summary; the original report is delivered to the client of the engagement."),
        filas="\n".join(filas))


def actualizar_sitemap(estudios):
    """Reescribe en sitemap.xml las direcciones de /publicaciones."""
    ruta = os.path.join(RAIZ, "sitemap.xml")
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding="utf-8") as f:
        xml = f.read()
    hoy = datetime.date.today().isoformat()
    # se borran las lineas de publicaciones que haya y se vuelven a escribir
    xml = re.sub(r"\s*<url><loc>[^<]*?/publicaciones/[^<]*</loc>.*?</url>", "", xml)
    filas = ['  <url><loc>{}/publicaciones/</loc><lastmod>{}</lastmod><priority>0.8</priority></url>'
             .format(SITIO, hoy)]
    for e in estudios:
        filas.append('  <url><loc>{}/publicaciones/{}.html</loc><lastmod>{}</lastmod><priority>0.7</priority></url>'
                     .format(SITIO, e["slug"], hoy))
    xml = xml.replace("</urlset>", "\n".join(filas) + "\n</urlset>")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(xml)
    return len(filas)


def main():
    estudios = leer_estudios(os.path.join(RAIZ, "estudios.txt"))
    if not estudios:
        print("estudios.txt no tiene ningun estudio cargado. No se genero nada.")
        return
    cabeza, encabezado, pie = piezas_de_la_portada()
    os.makedirs(SALIDA, exist_ok=True)

    escritos = []
    for e in estudios:
        destino = os.path.join(SALIDA, e["slug"] + ".html")
        with open(destino, "w", encoding="utf-8") as f:
            f.write(pagina(
                "{} | AXIA".format(e["titulo"]),
                (e.get("resumen", "")[:180]).strip(),
                "{}/publicaciones/{}.html".format(SITIO, e["slug"]),
                cuerpo_estudio(e), cabeza, encabezado, pie))
        escritos.append(os.path.basename(destino))

    with open(os.path.join(SALIDA, "index.html"), "w", encoding="utf-8") as f:
        f.write(pagina(
            "Estudios | AXIA Consultora Económica",
            "Resúmenes de los estudios de mercado, sectoriales y de coyuntura realizados por AXIA.",
            "{}/publicaciones/".format(SITIO),
            cuerpo_indice(estudios), cabeza, encabezado, pie))
    escritos.append("index.html")

    cuantas = actualizar_sitemap(estudios)

    print("Generado en publicaciones/:")
    for n in escritos:
        print("  -", n)
    if cuantas:
        print("sitemap.xml actualizado:", cuantas, "direcciones de /publicaciones")


if __name__ == "__main__":
    main()
