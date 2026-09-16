# Guía de arquitectura: Agente de búsqueda y curación de productos en Kakobuy

## 0. Filosofía del diseño

Regla general: **usar código determinístico (Playwright, parsers, funciones de scoring) para todo lo que no requiera criterio, y reservar las llamadas a Claude (visión o texto) solo para las decisiones que realmente lo necesitan.**

Esto es lo que mantiene el gasto limitado a tu suscripción/uso de Claude Code:
- Playwright, Node/Python, y las librerías de scraping son gratis y corren localmente.
- No se usa ninguna API de búsqueda de imágenes de pago (Google Custom Search, SerpAPI, Bing API). Para conseguir imágenes de referencia se usa la herramienta de **web search / web fetch nativa de Claude Code**, que ya está incluida en tu uso normal del agente.
- La comparación visual usa la **visión multimodal de Claude** (ya incluida). Si en algún momento el volumen de productos a comparar es muy alto y querés bajar el consumo de tokens, hay una opción local 100% gratuita (CLIP) que se menciona como optimización opcional, no como requisito.

El sistema se divide en 4 agentes/skills independientes + 1 orquestador. Cada uno se puede implementar como un subagente de Claude Code, un skill, o simplemente un script que Claude Code invoca — vos decidís el empaquetado, acá te dejo el contrato de cada uno (input/output/responsabilidad) para que la integración sea prolija.

---

## 1. Herramientas y setup previo

| Herramienta | Para qué | Costo |
|---|---|---|
| Playwright (Python o Node) | Controlar el navegador: buscar por texto, subir imagen, abrir productos | Gratis, self-host |
| Playwright MCP server (opcional) | Exponer Playwright como tool nativo dentro de Claude Code, en vez de que Claude escriba scripts sueltos | Gratis, open source |
| Claude Code (web_search / web_fetch integrados) | Conseguir imágenes de referencia del producto | Incluido en tu uso normal |
| Visión de Claude (pasar screenshots/imágenes en el prompt) | Comparar fotos de listados vs referencia, leer descripciones | Incluido en tu uso normal |
| CLIP local (opcional, `sentence-transformers` o `open_clip`) | Prefiltrar similitud visual sin gastar tokens de Claude en cada foto | Gratis, corre en tu CPU/GPU |
| SQLite o un JSON/CSV simple | Guardar resultados y estado entre búsquedas | Gratis |

**Antes de escribir una línea de agente**, hacé esto a mano una vez:
1. Entrá a kakobuy, hacé una búsqueda por texto y una por imagen, y mirá en las DevTools (Network) si hay anti-bot (Cloudflare challenge) o si el buscador de imagen pega a un endpoint separado.
2. Si necesitás login para buscar, logueate una vez con Playwright y guardá el `storage_state` (cookies) en un archivo, así los agentes no repiten el login.
3. Confirmá el patrón de URL de la búsqueda por texto (para poder armarla programáticamente) y el selector del input de subida de imagen.

Esto define si el Agente 2 puede ser 100% determinístico (ideal) o necesita ayuda de un LLM para navegar cuando el layout es inestable.

---

## 2. Agente 1 — Reference Finder (conseguir imágenes de referencia)

**Responsabilidad:** dado el nombre de un producto (texto que vos le pasás), conseguir entre 3 y 6 imágenes de referencia "oficiales" del producto real, para usarlas después como vara de comparación.

**Input:** nombre/descripción del producto (string). Opcional: una imagen que el usuario ya tenga.

**Herramientas:** `web_search` + `web_fetch` (nativas de Claude Code) para encontrar páginas oficiales o de retailers reconocidos, extraer las URLs de imagen, y descargarlas con un script simple (`requests`/`httpx`).

**Instrucciones para el agente:**
```
Sos el agente "Reference Finder". Tu única tarea es conseguir imágenes de
referencia confiables de un producto específico.

1. Buscá el producto por su nombre exacto usando web search, priorizando
   el sitio oficial de la marca o retailers reconocidos (no marketplaces
   de terceros).
2. De los resultados, elegí 3 a 6 imágenes que muestren el producto desde
   ángulos distintos (frente, lateral, detalle de logo/etiqueta si aplica).
3. Descargá esas imágenes a la carpeta de referencia del producto
   (una carpeta por producto, nombrada con un slug del nombre).
4. Devolvé un JSON con: nombre del producto, lista de paths locales de las
   imágenes descargadas, y la fuente (URL) de cada una.
5. Si no encontrás imágenes confiables, decilo explícitamente en vez de
   usar la primera imagen que aparezca — una referencia mala arruina
   todo el chequeo de calidad después.
```

**Output:** `reference/<slug-producto>/{img1.jpg, ...}` + `reference/<slug-producto>/meta.json`

---

## 3. Agente 2 — Kakobuy Searcher (búsqueda por texto y por imagen)

**Responsabilidad:** ejecutar la búsqueda dentro de kakobuy (texto y/o imagen) y devolver la lista de resultados (links + thumbnail + precio + vendedor tal como aparece en el listado). **No abre cada producto todavía** — esto es solo el listado.

**Herramientas:** Playwright (vía MCP server si lo configuraste, o vía scripts que Claude Code ejecuta con bash). Nada de LLM acá si el sitio es estable — es automatización pura.

**Instrucciones para el agente:**
```
Sos el agente "Kakobuy Searcher". Recibís una query de texto y/o una ruta
de imagen de referencia. Tu tarea es SOLO obtener la lista de resultados,
no evaluar nada todavía.

1. Si hay imagen: abrí el buscador visual de kakobuy y subí la imagen
   de referencia.
2. Si hay texto: ejecutá la búsqueda por palabra clave. Probá también
   con variantes (traducción al chino si el nombre es de una marca
   occidental, sinónimos, con y sin talla/color) — generá 2-3 variantes
   de la query, no solo una.
3. Para cada búsqueda, extraé de la página de resultados: título del
   listado, precio, URL del producto, thumbnail, y rating/ventas del
   vendedor si aparece en la vista de lista.
4. Devolvé todos los resultados como una lista de objetos JSON,
   incluyendo de qué variante de búsqueda salió cada uno (para poder
   deduplicar después).
5. No abras cada producto individual: eso lo hace el siguiente agente.
```

**Output:** `results/<slug-producto>/listado.json` (lista de candidatos)

---

## 4. Agente 3 — Product Vetter (abrir, chequear y puntuar cada producto)

**Responsabilidad:** este es el corazón del proyecto. Abre cada producto candidato, extrae los datos completos, compara visualmente contra las referencias, y calcula un score.

**Herramientas:** Playwright para abrir y extraer la página; visión de Claude para comparar imágenes y leer descripción; (opcional) CLIP local como prefiltro antes de gastar visión de Claude en cada candidato.

**Instrucciones para el agente:**
```
Sos el agente "Product Vetter". Recibís un link de producto de kakobuy y
las imágenes de referencia del producto original. Tu tarea es decidir
qué tan confiable/fiel es ese listado específico.

1. Abrí la página del producto y extraé: todas las fotos del listado,
   precio final (con envío si está disponible), descripción completa,
   rating y cantidad de ventas del vendedor, y si hay fotos de "QC"
   (quality control) subidas por compradores reales — esas fotos valen
   más que las fotos de catálogo del vendedor.
2. Comparación visual: compará las fotos reales del listado (priorizando
   fotos de QC si existen) contra las imágenes de referencia. Puntuá la
   similitud de 0 a 100. Prestá atención a detalles que delatan una
   réplica de baja calidad: logo mal proporcionado, materiales que se ven
   distintos, costuras, empaque.
3. Leé la descripción y buscá menciones explícitas de "batch", "versión",
   o calidad (ej. "1:1", "OG", nombres de fábrica) — resumí esto en una
   frase, no lo copies textual.
4. Calculá un score de vendedor a partir de rating y volumen de ventas
   (normalizado 0-100).
5. Marcá el producto como DESCARTADO si detectás alguna señal fuerte de
   alerta (fotos que no coinciden en absoluto con la referencia, vendedor
   sin ventas ni rating, descripción que contradice lo buscado) — no
   hace falta llevarlo al ranking final.
6. Devolvé un JSON por producto con: url, precio, score_visual,
   score_vendedor, resumen_descripcion, fotos_qc_encontradas (bool),
   estado (APTO / DESCARTADO), y motivo si fue descartado.
```

**Optimización opcional (para no gastar visión de Claude en cada foto):** correr primero un filtro local con CLIP que descarte automáticamente los candidatos con similitud embedding muy baja contra la referencia, y mandar a Claude solo los que pasan ese filtro. Esto es puramente para ahorrar tokens en catálogos grandes, no es necesario si el volumen de candidatos por búsqueda es bajo (decenas, no miles).

**Output:** `results/<slug-producto>/evaluados.json`

---

## 5. Orquestador — el loop general

**Responsabilidad:** coordinar los 3 agentes anteriores, manejar las búsquedas múltiples, y armar el ranking final. Este es el que vos vas a invocar directamente en Claude Code.

**Instrucciones para el agente:**
```
Sos el orquestador del sistema de búsqueda de productos. El usuario te da
el nombre de un producto (y opcionalmente una imagen). Tu trabajo es
coordinar a los otros tres agentes y entregar una lista final ordenada.

1. Invocá al Reference Finder con el nombre del producto (salvo que el
   usuario ya haya dado una imagen propia).
2. Invocá al Kakobuy Searcher con el texto y la imagen de referencia.
   Generá vos las 2-3 variantes de búsqueda antes de invocarlo, o dejá
   que el propio Searcher las genere (ver su instrucción arriba) —
   elegí un solo lugar para esta decisión y no lo dupliques.
3. Deduplicá los resultados del listado (mismo vendedor + mismo título
   casi idéntico) antes de mandarlos al Vetter, para no pagar el costo
   de abrir el mismo producto dos veces.
4. Invocá al Product Vetter para cada candidato único que no haya sido
   descartado por reglas obvias (precio absurdamente fuera de rango,
   por ejemplo).
5. Con los resultados del Vetter, calculá un score final combinado:

     score_final = 0.5 * score_visual
                 + 0.2 * score_vendedor
                 + 0.3 * score_precio_relativo

   donde score_precio_relativo premia estar cerca o por debajo de la
   mediana de precio de los candidatos APTOS de esa búsqueda (no premia
   el más barato a cualquier costo: un precio muy por debajo de la
   mediana debe restar puntos, no sumar, porque suele ser señal de
   calidad inferior).

6. Ordená los productos APTOS por score_final descendente y devolvé al
   usuario una lista con: opción, precio, score, link, y un resumen de
   una línea de por qué quedó en ese puesto (ej. "mejor similitud visual
   pero vendedor con pocas ventas" / "buen balance calidad-precio").
7. Si ninguna búsqueda dio resultados APTOS, decilo explícitamente y
   sugerí variantes de búsqueda adicionales en vez de forzar un ranking
   con productos dudosos.
```

**Output final al usuario:** tabla ordenada (podés pedirle a Claude Code que la imprima como Markdown o la guarde como CSV) con las mejores opciones balanceando calidad y precio.

---

## 6. Notas de integración con Claude Code

- Cada agente de arriba puede vivir como un **subagente** separado (con su propio prompt de sistema, tal como están escritos) o como **skills** invocadas por el orquestador — la ventaja de separarlos es que podés iterar el prompt del Vetter (que es el más delicado) sin tocar el resto.
- Convención de datos: usá una carpeta por producto buscado (`/data/<slug>/`) con subcarpetas `reference/`, `results/`, y un `run.json` que trackee el estado del pipeline — así si se corta a mitad de camino, el orquestador puede retomar en vez de arrancar de cero.
- Empezá probando el pipeline completo con **una sola búsqueda de texto, sin imagen y sin variantes**, para validar que las 4 piezas encastran, antes de sumar las búsquedas múltiples y el filtro CLIP.
- Guardá siempre el `motivo` de descarte y el desglose del score (no solo el número final) — vas a necesitarlo para ajustar los pesos de la fórmula una vez que veas resultados reales.

## 7. Recordatorio legal/práctico

Kakobuy opera en una zona gris según el país (importación de réplicas). Esta guía cubre la parte de **búsqueda y evaluación**, no la de compra automatizada. Si en algún momento pensás que el agente ejecute compras, revisá los Términos de Servicio del sitio y la normativa de importación de tu país antes de automatizar esa parte.
