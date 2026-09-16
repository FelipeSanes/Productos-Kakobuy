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
3a. **Para wearables electrónicos (smartwatches, trackers), 1688 suele
   tener solo accesorios (correas/fundas/protectores de pantalla), no el
   dispositivo en sí — patrón confirmado con 2 marcas distintas, no es
   un caso aislado.**
   - WHOOP 5.0: docenas de variantes en chino ("本体"/cuerpo principal,
     "主机"/host, "传感器"/sensor, "含传感器"/con sensor) devolvieron 0
     resultados, ruido total (sensores de pesas de cocina, repuestos de
     auto) o, en el mejor caso, únicamente correas de repuesto. Búsqueda
     por imagen con foto del sensor solo tampoco ayudó (matcheó por
     forma con power banks).
   - Amazfit (marca china real, no debería tener filtro de marca):
     "amazfit" solo → 10 resultados, TODOS accesorios (protectores de
     pantalla templados, correas) para modelos Active/T-Rex/GTR. "华米"
     (nombre del fabricante) → 3 resultados, también todo correas. Ni un
     solo reloj real en ninguna variante probada.
   - Conclusión: parece que 1688/Kakobuy está mucho mejor surtido para
     moda/accesorios (ropa, calzado, carteras, fundas, correas) que para
     el dispositivo electrónico en sí — sea porque el accesorio es más
     fácil/barato de fabricar sin infringir nada, sea porque el
     electrónico genuino se vende por canales mayoristas distintos a los
     que indexa esta búsqueda. Si el usuario pidió explícitamente el
     dispositivo (no el accesorio) y después de ~10 variantes solo
     aparecen correas/fundas/protectores, decilo así de claro en vez de
     ofrecer un accesorio como si fuera el producto.

3. **Productos muy nuevos/nicho pueden no tener inventario todavía.** Para
   un producto lanzado hace pocos meses (probado con un dispositivo
   electrónico de 2026), decenas de variantes de texto en chino (incluso
   sin nombrar la marca) devolvieron 0 resultados o matches totalmente
   irrelevantes (el buscador degrada a matchear solo la palabra genérica
   más común de la query, ej. "手环"/pulsera, ignorando el resto). Esto es
   distinto al bloqueo de marca del punto 1: acá simplemente no hay
   listados reales todavía porque las cadenas de réplica china no
   alcanzaron a fabricar ese producto puntual. Si después de ~5-6
   variantes de texto razonables seguís sin nada relevante, es más
   probable que sea esto que un problema de tu query — decilo
   explícitamente al usuario en vez de seguir generando variantes ad
   infinitum.

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
