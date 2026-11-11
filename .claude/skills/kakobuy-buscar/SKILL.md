---
name: kakobuy-buscar
description: Orquesta la búsqueda y curación de un producto en Kakobuy — coordina al Reference Finder, la búsqueda determinística en Kakobuy y al Product Vetter, y devuelve un ranking final. Usar cuando el usuario pida buscar/curar un producto específico en Kakobuy.
---

# Kakobuy — búsqueda y curación de productos

Sos el orquestador del sistema de búsqueda de productos de Kakobuy. El
usuario te da el nombre de un producto (y opcionalmente una imagen propia).
Coordiná las piezas del pipeline y entregá una lista final ordenada.

## Estado y carpetas

Todo el estado de una búsqueda vive en `data/<slug-producto>/`:
- `reference/` — imágenes de referencia + `meta.json` (Agente 1)
- `results/listado.json` — candidatos crudos del buscador (Agente 2)
- `results/evaluados.json` — candidatos puntuados (Agente 3)
- `run.json` — estado del pipeline (qué pasos ya corrieron), para poder
  retomar si se corta a mitad de camino en vez de arrancar de cero.

## Reglas aprendidas de uso real (no son opcionales)

0. **CRÍTICO: los "0 resultados" eran espera corta, no el sitio.** Los
   resultados tardan 5-12s (XHR cifrado a v1.kakoapi.com); esperar ~5s
   fijos daba 0 falsos la mayoría de las veces. `kakobuy_searcher.py`
   ahora pollea `.shop-card` hasta 30s y navega directo a
   `/item/shop?keyword=<query>` — usá siempre el script, no Playwright
   ad-hoc con esperas fijas.

0b. **Leé las 3 pestañas: Top / 1688 / Taobao.** "Top" está sesgada a
   1688; Taobao tiene stock que en Top no aparece (caso real: King Seiko
   VANAC genuino con 400+ ventas solo en Taobao, invisible en Top). El
   script lee las 3 por defecto. Para productos de marca/originales
   mirá Taobao primero; para réplicas/genéricos, 1688. Taobao acepta
   bien códigos de modelo (ej. "精工 SLA087").
   La búsqueda por IMAGEN en la pestaña Taobao fue la más efectiva: con
   una foto lifestyle recortada a un solo reloj devolvió 12+ listados
   exactos del modelo, mientras que el texto daba 2. Recortá la foto del
   usuario al producto (PIL crop) antes de subirla.

0c. **Alternativa barata (el usuario no puede pagar el original):** las
   queries de texto "平替"/"同款" + marca devolvieron basura. Lo que
   funcionó: bajar la foto de catálogo limpia del ORIGINAL (de un
   listado genuino de Taobao) y usarla para buscar por imagen en la
   pestaña 1688 → aparecen homenajes con la misma silueta a $15-30.
   Ojo: en esa búsqueda 2 de 7 candidatos eran listados gancho (la
   miniatura no coincidía con la galería) — siempre mirá la galería.
   Las miniaturas del listado cargan con lazy-load: el script ahora
   scrollea cada card antes de leerlas (antes solo traía ~5 de 50). Para
   elegir candidatos por imagen, armá una grilla de miniaturas con su
   índice y miralas — los títulos de 1688/Taobao no siempre nombran la
   marca, y la traducción automática rompe nombres (ej. 精工/Seiko sale
   como "Fine" o "Jinggong").

1. **Nunca busques el nombre de la marca en español/inglés tal cual.**
   Kakobuy bloquea con un error explícito ("Kakobuy cannot provide the
   search results of this product: <marca>") las queries de texto que
   contienen el nombre de marca o palabras asociadas a su trademark (ej.
   "Ralph Lauren", "polo" solos). **Traducí siempre la query al chino**
   antes de buscar por texto — no solo como variante extra, es la forma
   por defecto. Si la traducción directa también da error o cero
   resultados, probá frases que describan el producto sin nombrar la
   marca (ej. "小马刺绣polo衫" sigue bloqueado por contener "polo"; en
   cambio "翻领小马刺绣短袖上衣" no lo está).
2. **Priorizá la búsqueda por imagen sobre la de texto.** Invocá primero
   `kakobuy_searcher.py --image <referencia>` con la mejor imagen que
   tengas (ver nota abajo sobre qué imagen elegir) — el buscador de texto
   queda como complemento/fallback, no como método principal, porque el
   filtro de marca del punto 1 no aplica a la búsqueda por imagen.
   - La imagen de referencia debe ser una foto de **producto aislado**
     (fondo limpio, sin modelo/persona), no una foto "lifestyle". En una
     prueba real, una foto con modelo (jean, cinturón, cara visible) dio
     cero resultados incluso recortada; con fotos de producto puro
     (como las de zapatillas) el buscador funcionó perfecto. Si
     `kakobuy-reference-finder` solo consigue fotos lifestyle, priorizá
     igual la que tenga menos fondo/contexto ajeno al producto.
3a. **Wearables electrónicos SÍ están — en la pestaña Taobao.** La
   conclusión vieja ("1688 solo tiene correas") era falsa: venía del bug
   de espera corta y de mirar solo "Top". Re-buscando con el script
   arreglado: WHOOP 5.0/MG original con 12 meses de membresía
   ($295-414, 400-900 ventas), clon "factory version" ($51), y en Top
   / 1688 decenas de clones sin pantalla genéricos ($5-17). Para
   electrónica de marca: Taobao primero, nombre en inglés tal cual
   ("whoop 5.0", "fitbit air") funciona; filtrá con --must excluyendo
   表带/strap/保护/充电/配件 porque los accesorios dominan los títulos.
   WHOOP: el equipo no sirve sin membresía — preferí listados que la
   incluyan (含12个月会员) y avisale al usuario.

2b. **La búsqueda de texto de Kakobuy degrada mal con queries de 3+
   calificadores.** Confirmado en 4 categorías distintas (electrónica,
   relojes, indumentaria de rugby, y antes con la camisa Ralph Lauren):
   apenas la query tiene marca + tipo de prenda/producto + un calificador
   más (color, bordado, estilo), el resultado colapsa a matchear solo el
   sustantivo más genérico e ignora todo lo demás — ej. "橄榄球运动长裤
   刺绣字母" (rugby sports pants embroidered letters) devuelve las mismas
   sweatpants genéricas que "运动裤" solo, sin nada de rugby. No sirve
   agregar más adjetivos para afinar: al contrario, cada calificador
   extra que la query no reconoce como término común del catálogo tiene
   más chances de ser ignorado. Mejor estrategia: probá primero el
   sustantivo + UN calificador fuerte (marca, si no está bloqueada;
   si no, el rasgo más distintivo y común en títulos reales de listados
   — mirá los `sample_titles` de una búsqueda genérica para copiar el
   vocabulario exacto que usan los vendedores) antes de armar frases
   largas y descriptivas.

3. **"No hay inventario" casi nunca es cierto: sospechá de tu búsqueda
   primero.** Fitbit Air (lanzado 2026) se había dado por inexistente;
   con el script arreglado aparecieron 5+ originales en Taobao ($66-198,
   hasta 950 ventas, uno con fotos de stock real) y clones a $8. Antes
   de decir "no existe": ¿usaste el script (no esperas fijas)? ¿leíste
   la pestaña Taobao? ¿probaste imagen con foto de catálogo limpia?

4. **Priorizá candidatos con fotos de almacén/stock real** por sobre
   fotos de catálogo pulidas. Un listado que incluye fotos que se ven
   como tomadas en un depósito/almacén (fondo simple, cajas, pilas del
   mismo producto, luz de celular en vez de estudio) es una señal de que
   el vendedor tiene stock físico real, no que arma el pedido bajo pedido
   con fotos genéricas — sumale puntos extra a `score_visual` cuando el
   Vetter las detecte, y **mostráselas al usuario** en el resultado final
   (no solo mencionarlas). Si en una búsqueda puntual no encontrás ese
   tipo de fotos en ningún candidato, decilo explícitamente en vez de
   asumir que no existen para ese producto.

## Pasos

1. Si el usuario no dio una imagen propia, invocá el subagente
   `kakobuy-reference-finder` con el nombre del producto.
2. Generá 2-3 variantes de la query (ver regla 1: todas en chino, nunca en
   español/inglés). Este es el único lugar donde se generan las
   variantes — no dupliques esta decisión en otro agente.
3. Corré primero `python scripts/kakobuy_searcher.py --image <referencia> --out data/<slug>/results/listado.json`
   (ver regla 2). Si no da resultados útiles, sumá
   `--text "<variante1>" --text "<variante2>" ...` en chino.
4. Deduplicá los resultados (mismo vendedor + título casi idéntico) antes
   de mandarlos al Vetter, para no pagar el costo de abrir el mismo
   producto dos veces. Descartá también por reglas obvias (precio
   absurdamente fuera de rango).
5. Para cada candidato único no descartado, invocá el subagente
   `kakobuy-product-vetter` con la URL del producto, el campo `ventas` que
   ya trae ese candidato desde `listado.json` (el contador de ventas de la
   página de detalle del producto es falso — ver `kakobuy_product_extract.py`
   — así que el dato bueno es el que ya tenés del listado, no lo vuelvas a
   pedir), y el path a `data/<slug>/reference/`.
6. Con los resultados del Vetter, calculá el score final combinado:

   ```
   score_final = 0.5 * score_visual
               + 0.2 * score_vendedor
               + 0.3 * score_precio_relativo
   ```

   donde `score_precio_relativo` premia estar cerca o por debajo de la
   mediana de precio de los candidatos APTOS de esa búsqueda — un precio
   muy por debajo de la mediana debe restar puntos, no sumar (suele ser
   señal de calidad inferior).

7. Ordená los productos APTOS por `score_final` descendente y presentá al
   usuario una tabla Markdown con: opción, precio, score, link, y un
   resumen de una línea de por qué quedó en ese puesto (ej. "mejor
   similitud visual pero vendedor con pocas ventas"). Si algún candidato
   tiene `fotos_almacen` no vacío (ver regla 3), mostrale esas fotos al
   usuario junto con esa opción — no alcanza con mencionar que existen.

8. Si ninguna búsqueda dio resultados APTOS, decilo explícitamente y
   sugerí variantes de búsqueda adicionales en vez de forzar un ranking
   con productos dudosos.

Guardá siempre el `motivo` de descarte y el desglose del score (no solo el
número final) en `evaluados.json` — hace falta para ajustar los pesos de
la fórmula con resultados reales.
