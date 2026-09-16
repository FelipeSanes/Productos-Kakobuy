# Productos-Kakobuy

Agente de búsqueda y curación de productos en Kakobuy: dado el nombre de un
producto, busca candidatos en Kakobuy (texto y/o imagen), los compara
visualmente contra referencias del producto original, y devuelve un
ranking balanceando fidelidad visual, confiabilidad del vendedor y precio.

Arquitectura completa: ver la guía en `docs/guia-agente-kakobuy.md` (o el
instructivo original compartido). Resumen: 4 piezas — Reference Finder,
Kakobuy Searcher, Product Vetter y un Orquestador — donde todo lo
determinístico (navegación, extracción, scoring) es código/Playwright, y
Claude solo interviene donde hace falta criterio (elegir buenas imágenes
de referencia, comparar visualmente, leer descripciones).

## Estado actual

- [x] Estructura de carpetas y scaffolding
- [x] Subagentes `kakobuy-reference-finder` y `kakobuy-product-vetter` (`.claude/agents/`)
- [x] Skill orquestador `kakobuy-buscar` (`.claude/skills/kakobuy-buscar/`)
- [ ] Login a Kakobuy (`auth/login.py`) — pendiente de credenciales y de
      confirmar los selectores reales del formulario
- [ ] Selectores reales de búsqueda y extracción de producto en
      `scripts/kakobuy_searcher.py` y `scripts/kakobuy_product_extract.py`
      — pendiente de inspección manual del sitio (anti-bot, endpoint de
      búsqueda por imagen, patrón de URL de búsqueda por texto)
- [ ] Primera corrida end-to-end con una sola búsqueda de texto, sin
      imagen y sin variantes

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium  # si no está ya instalado en el entorno

KAKOBUY_EMAIL=... KAKOBUY_PASSWORD=... python auth/login.py
```

Después de loguear una vez, invocá el skill orquestador:

```
/kakobuy-buscar nombre del producto
```

## Estructura de datos

```
data/<slug-producto>/
  reference/       # imágenes de referencia + meta.json
  results/
    listado.json    # candidatos crudos del buscador
    evaluados.json  # candidatos puntuados (APTO/DESCARTADO)
  run.json          # estado del pipeline
```

`data/` no se commitea (ver `.gitignore`) — es contenido generado por cada
búsqueda, no código.

## Nota legal

Kakobuy opera en una zona gris según el país (importación de réplicas).
Este proyecto cubre solo la parte de búsqueda y evaluación, no la de
compra automatizada.
