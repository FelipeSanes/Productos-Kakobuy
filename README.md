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
- [x] Login a Kakobuy (`auth/login.py`) — probado end-to-end, incluye el
      código de verificación por email (OTP) que pide el sitio además de
      usuario/contraseña
- [x] Selectores reales de búsqueda (texto e imagen) y extracción de
      producto, verificados contra el sitio real — no hay anti-bot
      bloqueando estos flujos
- [x] Primera corrida end-to-end de una búsqueda de texto (`kakobuy_searcher.py`
      + `kakobuy_product_extract.py`), de punta a punta
- [ ] Correr el skill `kakobuy-buscar` completo (con Reference Finder y
      Product Vetter reales) para una búsqueda de usuario

**Hallazgos importantes de la inspección (ver `docs/guia-agente-kakobuy.md`
para el diseño original, y los comentarios en cada script para el detalle):**
- El buscador de Kakobuy agrega resultados de 1688 y Taobao/Weidian; no hay
  challenge de Cloudflare bloqueando la búsqueda ni la extracción.
- Las cards de resultado no tienen `href`: hay que clickearlas y capturar la
  URL de la pestaña que abren (`kakobuy_searcher.py` ya lo hace).
- Kakobuy no expone fotos de QC de compradores ni rating de vendedor en su
  propia página de producto. La descripción es una imagen, no texto.
- El contador de "Sales" en la página de detalle del producto es **falso**
  (cambia aleatoriamente en cada carga) — el contador confiable es el que
  aparece en el listado de búsqueda.

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium  # si no está ya instalado en el entorno

KAKOBUY_EMAIL=... KAKOBUY_PASSWORD=... python auth/login.py request
# revisar el email por el código y completar:
KAKOBUY_EMAIL=... KAKOBUY_PASSWORD=... python auth/login.py verify <codigo>
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
