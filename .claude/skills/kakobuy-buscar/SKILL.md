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

## Pasos

1. Si el usuario no dio una imagen propia, invocá el subagente
   `kakobuy-reference-finder` con el nombre del producto.
2. Generá 2-3 variantes de la query de texto (traducción al chino si es
   una marca occidental, sinónimos, con y sin talla/color). Este es el
   único lugar donde se generan las variantes — no dupliques esta
   decisión en otro agente.
3. Corré `python scripts/kakobuy_searcher.py --text "<variante1>" --text "<variante2>" ... [--image <ref>] --out data/<slug>/results/listado.json`.
4. Deduplicá los resultados (mismo vendedor + título casi idéntico) antes
   de mandarlos al Vetter, para no pagar el costo de abrir el mismo
   producto dos veces. Descartá también por reglas obvias (precio
   absurdamente fuera de rango).
5. Para cada candidato único no descartado, invocá el subagente
   `kakobuy-product-vetter` con la URL del producto y el path a
   `data/<slug>/reference/`.
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
   similitud visual pero vendedor con pocas ventas").

8. Si ninguna búsqueda dio resultados APTOS, decilo explícitamente y
   sugerí variantes de búsqueda adicionales en vez de forzar un ranking
   con productos dudosos.

Guardá siempre el `motivo` de descarte y el desglose del score (no solo el
número final) en `evaluados.json` — hace falta para ajustar los pesos de
la fórmula con resultados reales.
