// La palabra AXIA va siempre en la letra del logotipo, como pide el manual de marca:
// Spectral 700 con 0,045 em de espaciado. Este script envuelve cada aparicion visible en
// <span class="axia">, tambien en lo que las paginas dibujan despues de cargar (tarjetas de
// estudios, Panorama en la portada, el tablero). Se incluye una sola vez por pagina:
//   <script src="/marca/axia.js" defer></script>
// La fuente tiene que estar cargada (Spectral:wght@700 en el enlace de Google Fonts).
(function(){
  var estilo = document.createElement("style");
  // Spectral tiene mayusculas mas bajas que Sora y Manrope a igual cuerpo: se agranda un
  // poco para que AXIA no quede mas chica que las palabras de al lado.
  estilo.textContent = '.axia{font-family:"Spectral",Georgia,serif;font-weight:700;font-style:normal;' +
                       'letter-spacing:.045em;font-size:1.06em;line-height:1}';
  document.head.appendChild(estilo);

  var PALABRA = /\bAXIA\b/;
  var EXCLUIR = "script,style,textarea,title,noscript,svg,canvas,option,.axia,[contenteditable]";

  function envolverNodo(n){
    var p = n.parentElement;
    if (!p || p.closest(EXCLUIR) || !PALABRA.test(n.nodeValue)) return;
    var partes = n.nodeValue.split(/\b(AXIA)\b/);
    var frag = document.createDocumentFragment();
    partes.forEach(function(t, i){
      if (i % 2) { var s = document.createElement("span"); s.className = "axia"; s.textContent = t; frag.appendChild(s); }
      else if (t) frag.appendChild(document.createTextNode(t));
    });
    p.replaceChild(frag, n);
  }

  function recorrer(raiz){
    if (raiz.nodeType === 3) { envolverNodo(raiz); return; }
    if (raiz.nodeType !== 1 || raiz.closest(EXCLUIR)) return;
    var w = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT), lista = [];
    for (var n; (n = w.nextNode());) if (PALABRA.test(n.nodeValue)) lista.push(n);
    lista.forEach(envolverNodo);
  }

  // Lo que se agrega o cambia despues se procesa apenas aparece. No se espera al proximo
  // cuadro (requestAnimationFrame): en una pestana en segundo plano ese cuadro no llega y la
  // palabra quedaba sin cambiar. Los span que agrega este script no vuelven a disparar nada:
  // estan excluidos y el texto que queda alrededor ya no dice AXIA.
  function empezar(){
    recorrer(document.body);
    new MutationObserver(function(cambios){
      cambios.forEach(function(c){
        if (c.type === "characterData") { if (c.target.isConnected) recorrer(c.target); }
        else c.addedNodes.forEach(function(n){ if (n.isConnected) recorrer(n); });
      });
    }).observe(document.body, {childList:true, subtree:true, characterData:true});
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", empezar);
  else empezar();
})();
