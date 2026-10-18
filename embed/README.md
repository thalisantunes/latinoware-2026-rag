**[English](#english) · [Español](#español) · [Português](#português)**

# `<latinoware-catalogo>`

## English

A web component that shows the Latinoware schedule with search, filters and a link to the exact moment of each
talk in the recorded livestream. No build step, no dependencies, about 25 KB. Personal and **unofficial**
project, not affiliated with the Latinoware organizers.

### Use

```html
<script src="https://cdn.jsdelivr.net/gh/thalisantunes/latinoware-2026-rag@v1.0.0/web/latinoware-catalogo.js" defer></script>
<latinoware-catalogo src="https://ilove.the.br/latinoware/2026/rag/catalogo.json" lang="en"></latinoware-catalogo>
```

jsDelivr also serves a minified copy if you replace `.js` with `.min.js`.

### Attributes

| attribute | required | meaning |
|---|---|---|
| `src` | yes | URL of `catalogo.json` (served with `Access-Control-Allow-Origin: *`) |
| `lang` | no | `pt`, `en` or `es`; default: page `<html lang>`, then the browser language. Read on load and when the attribute changes, not when page translators change `<html lang>`, so languages do not mix |
| `api` | no | RAG API URL (e.g. `https://rag.ilove.the.br`). Adds an "Ask about the talks" box and the "AI summary" button on each card. Without it, the component is a plain catalogue |
| `fotos` | no | URL of `fotos.json`: "Photos at the event" gallery in each speaker's view (Flickr thumbnail, credit, removal contact) |
| `perguntar` | no | shows "AI summary" and fires the `perguntar` event (bubbles, composed, cancelable; `detail.pergunta`, `palestra_id`, `uid`, `titulo`, `palestrantes`) for the host page; with `api`, calling `preventDefault()` turns off the built-in answer box |

The API runs on a home GPU with no uptime guarantee; when it is down, the component says so and hides the AI
buttons, and the catalogue keeps working. Leave `api` out if the page must not depend on it.
Filters are kept in the URL with the `lw_` prefix (`lw_data`, `lw_espaco`, `lw_busca`…), and `#palestra-<uid>`
opens a specific talk.

### Styling

The component inherits the page font and colour. Optional CSS custom properties: `--lw-accent`,
`--lw-accent-fg`, `--lw-line`, `--lw-muted`, `--lw-surface`, `--lw-radius`, `--lw-focus`.

### iframe alternative

```html
<!-- <iframe src="https://ilove.the.br/latinoware/2026/rag/#catalogo" title="Latinoware schedule" style="width:100%;height:80vh;border:0"></iframe> -->
```

### Regenerating the data

`make coletar catalogo` (schedule from latinoware.org) or `make tudo` (with recordings and transcripts).
`catalogo.json` carries only metadata, a short abstract (up to 280 characters) with a link to the full text on
the website, and the link to the moment in the livestream.

## Español

Un componente web que muestra la programación de Latinoware con búsqueda, filtros y un enlace al momento exacto
de cada charla en la transmisión grabada. Sin compilación ni dependencias, unos 25 KB. Proyecto personal y
**no oficial**, sin relación con la organización de Latinoware.

### Uso

```html
<script src="https://cdn.jsdelivr.net/gh/thalisantunes/latinoware-2026-rag@v1.0.0/web/latinoware-catalogo.js" defer></script>
<latinoware-catalogo src="https://ilove.the.br/latinoware/2026/rag/catalogo.json" lang="es"></latinoware-catalogo>
```

jsDelivr también sirve una copia minificada si cambias `.js` por `.min.js`.

### Atributos

| atributo | obligatorio | significado |
|---|---|---|
| `src` | sí | URL de `catalogo.json` (servido con `Access-Control-Allow-Origin: *`) |
| `lang` | no | `pt`, `en` o `es`; por defecto, el `<html lang>` de la página y después el idioma del navegador. Se lee al cargar y cuando cambia el atributo, no cuando un traductor cambia el `<html lang>`, para no mezclar idiomas |
| `api` | no | URL de la API de la RAG (p. ej. `https://rag.ilove.the.br`). Agrega una caja de preguntas y el botón "Resumen con IA" en cada tarjeta. Sin él, el componente es solo un catálogo |
| `fotos` | no | URL de `fotos.json`: galería "Fotos en el evento" en la vista de cada ponente (miniatura de Flickr, crédito, contacto para retirar) |
| `perguntar` | no | muestra "Resumen con IA" y dispara el evento `perguntar` (bubbles, composed, cancelable; `detail.pergunta`, `palestra_id`, `uid`, `titulo`, `palestrantes`) para la página; con `api`, `preventDefault()` desactiva la caja de respuesta propia |

La API corre en una GPU doméstica, sin garantía de disponibilidad; cuando cae, el componente lo avisa y oculta
los botones de IA, y el catálogo sigue funcionando. Omite `api` si la página no puede depender de ella. Los filtros quedan en la URL con el prefijo `lw_` (`lw_data`, `lw_espaco`, `lw_busca`…) y
`#palestra-<uid>` abre una charla.

### Estilo

El componente hereda la fuente y el color de la página. Propiedades CSS opcionales: `--lw-accent`,
`--lw-accent-fg`, `--lw-line`, `--lw-muted`, `--lw-surface`, `--lw-radius`, `--lw-focus`.

### Alternativa con iframe

```html
<!-- <iframe src="https://ilove.the.br/latinoware/2026/rag/#catalogo" title="Programación de Latinoware" style="width:100%;height:80vh;border:0"></iframe> -->
```

### Regenerar los datos

`make coletar catalogo` (programación de latinoware.org) o `make tudo` (con grabaciones y transcripciones).
`catalogo.json` solo lleva metadatos, un resumen corto (hasta 280 caracteres) con enlace al texto completo en el
sitio y el enlace al momento en la transmisión.

## Português

Um componente web que mostra a programação da Latinoware com busca, filtros e link para o instante de cada
palestra na live gravada. Sem build nem dependências, cerca de 25 KB. Projeto pessoal e **não oficial**, sem
vínculo com a organização da Latinoware.

### Uso

```html
<script src="https://cdn.jsdelivr.net/gh/thalisantunes/latinoware-2026-rag@v1.0.0/web/latinoware-catalogo.js" defer></script>
<latinoware-catalogo src="https://ilove.the.br/latinoware/2026/rag/catalogo.json" lang="pt"></latinoware-catalogo>
```

O jsDelivr também serve uma cópia minificada trocando `.js` por `.min.js`.

### Atributos

| atributo | obrigatório | significado |
|---|---|---|
| `src` | sim | URL do `catalogo.json` (servido com `Access-Control-Allow-Origin: *`) |
| `lang` | não | `pt`, `en` ou `es`; padrão: `<html lang>` da página e depois a língua do navegador. Lido ao carregar e quando o atributo muda, não quando um tradutor troca o `<html lang>`, para não misturar línguas |
| `api` | não | URL da API da RAG (ex.: `https://rag.ilove.the.br`). Acrescenta uma caixa de perguntas e o botão "Resumo com IA" em cada card. Sem ele, o componente é só catálogo |
| `fotos` | não | URL do `fotos.json`: galeria "Fotos no evento" na visão de cada palestrante (miniatura do Flickr, crédito, contato para remoção) |
| `perguntar` | não | mostra "Resumo com IA" e dispara o evento `perguntar` (bubbles, composed, cancelável; `detail.pergunta`, `palestra_id`, `uid`, `titulo`, `palestrantes`) para a página; com `api`, `preventDefault()` desliga a caixa de resposta própria |

A API roda numa GPU doméstica, sem garantia de disponibilidade; quando ela cai, o componente avisa e esconde os
botões de IA, e o catálogo continua funcionando. Deixe `api` de fora se a página não puder depender dela. Os filtros ficam na URL com prefixo `lw_` (`lw_data`, `lw_espaco`, `lw_busca`…) e
`#palestra-<uid>` abre uma palestra.

### Estilo

O componente herda a fonte e a cor da página. Propriedades CSS opcionais: `--lw-accent`, `--lw-accent-fg`,
`--lw-line`, `--lw-muted`, `--lw-surface`, `--lw-radius`, `--lw-focus`.

### Alternativa com iframe

```html
<!-- <iframe src="https://ilove.the.br/latinoware/2026/rag/#catalogo" title="Programação da Latinoware" style="width:100%;height:80vh;border:0"></iframe> -->
```

### Regenerar os dados

`make coletar catalogo` (grade de latinoware.org) ou `make tudo` (com gravações e transcrições).
O `catalogo.json` traz só metadados, um resumo curto (até 280 caracteres) com link para o texto completo no site
e o link para o instante na live.
