// <latinoware-catalogo src="catalogo.json" lang="pt" api="https://rag.ilove.the.br" perguntar>
// Catálogo de palestras da Latinoware com filtros e link para o instante na live.
// Atributos: src (obrigatório), lang (pt|en|es), api (opcional: liga a pergunta à IA),
// fotos (opcional: URL de fotos.json, galeria "Fotos no evento" na visão de cada palestrante),
// perguntar (opcional: mostra "Resumo com IA" e só emite o evento "perguntar" para a página).
// Sem dependências e sem build. Projeto pessoal e não oficial: github.com/thalisantunes/latinoware-2026-rag
(() => {
  const VERSAO = 1; // igual à "versao" de catalogo.json
  const P = "lw_"; // prefixo dos filtros na URL, para não colidir com a página que hospeda

  const T = {
    pt: {
      busca: "Buscar", buscaPh: "título, palestrante, tema…", data: "Dia", espaco: "Espaço", trilha: "Temática",
      palestrante: "Palestrante", todos: "Todos", soVideo: "Só com vídeo", limpar: "Limpar filtros",
      contador: n => n === 1 ? "1 atividade" : `${n} atividades`, nenhum: "Nenhuma atividade com esses filtros.",
      carregando: "Carregando programação…", erroCarga: "Não foi possível carregar a programação.",
      assistir: "Assistir no YouTube", estimado: "horário estimado", semGravacao: "Sem gravação",
      noSite: "Resumo completo no site", perguntarIA: "Resumo com IA",
      pergunta: (t, p) => `Resuma a palestra "${t}"${p ? ` de ${p}` : ""}`,
      perguntaRotulo: "Pergunte sobre as palestras", enviar: "Perguntar", aguarde: "Buscando e escrevendo a resposta…",
      ocupado: "Muitas perguntas agora. Tente de novo em instantes.", demorou: "A resposta demorou demais. Tente de novo.",
      erro: "Não foi possível responder agora.", fontes: "Fontes", video: "Vídeo",
      copiar: "Copiar resposta", compartilhar: "Compartilhar", paginaSite: "Página no site da Latinoware", fotosEvento: "Fotos no evento", foto: "Foto",
      fotoDe: n => `${n} na Latinoware`, remover: "Quer remover uma foto? Escreva para",
      copiado: "Resposta copiada.", linkCopiado: "Link copiado.", naoCopiou: "Não foi possível copiar.",
    },
    en: {
      busca: "Search", buscaPh: "title, speaker, topic…", data: "Day", espaco: "Room", trilha: "Track",
      palestrante: "Speaker", todos: "All", soVideo: "Only with video", limpar: "Clear filters",
      contador: n => n === 1 ? "1 activity" : `${n} activities`, nenhum: "No activities match these filters.",
      carregando: "Loading schedule…", erroCarga: "Could not load the schedule.",
      assistir: "Watch on YouTube", estimado: "estimated time", semGravacao: "No recording",
      noSite: "Full abstract on the website", perguntarIA: "AI summary",
      pergunta: (t, p) => `Summarize the talk "${t}"${p ? ` by ${p}` : ""}`,
      perguntaRotulo: "Ask about the talks", enviar: "Ask", aguarde: "Searching and writing the answer…",
      ocupado: "Too many questions right now. Try again shortly.", demorou: "The answer took too long. Try again.",
      erro: "Could not answer right now.", fontes: "Sources", video: "Video",
      copiar: "Copy answer", compartilhar: "Share", paginaSite: "Page on the Latinoware website", fotosEvento: "Photos at the event", foto: "Photo",
      fotoDe: n => `${n} at Latinoware`, remover: "Want a photo removed? Write to",
      copiado: "Answer copied.", linkCopiado: "Link copied.", naoCopiou: "Could not copy.",
    },
    es: {
      busca: "Buscar", buscaPh: "título, ponente, tema…", data: "Día", espaco: "Espacio", trilha: "Temática",
      palestrante: "Ponente", todos: "Todos", soVideo: "Solo con video", limpar: "Limpiar filtros",
      contador: n => n === 1 ? "1 actividad" : `${n} actividades`, nenhum: "Ninguna actividad con estos filtros.",
      carregando: "Cargando programación…", erroCarga: "No se pudo cargar la programación.",
      assistir: "Ver en YouTube", estimado: "hora estimada", semGravacao: "Sin grabación",
      noSite: "Resumen completo en el sitio", perguntarIA: "Resumen con IA",
      pergunta: (t, p) => `Resume la charla "${t}"${p ? ` de ${p}` : ""}`,
      perguntaRotulo: "Pregunta sobre las charlas", enviar: "Preguntar", aguarde: "Buscando y escribiendo la respuesta…",
      ocupado: "Demasiadas preguntas ahora. Inténtalo de nuevo en breve.", demorou: "La respuesta tardó demasiado. Inténtalo de nuevo.",
      erro: "No se pudo responder ahora.", fontes: "Fuentes", video: "Video",
      copiar: "Copiar respuesta", compartilhar: "Compartir", paginaSite: "Página en el sitio de Latinoware", fotosEvento: "Fotos en el evento", foto: "Foto",
      fotoDe: n => `${n} en Latinoware`, remover: "¿Quieres quitar una foto? Escribe a",
      copiado: "Respuesta copiada.", linkCopiado: "Enlace copiado.", naoCopiou: "No se pudo copiar.",
    },
  };

  const CSS = `
    :host { display: block; font: inherit; color: inherit;
      --a: var(--lw-accent, var(--accent, light-dark(#17694a, #5cc595)));
      --af: var(--lw-accent-fg, var(--accent-fg, light-dark(#fff, #0d1f16)));
      --l: var(--lw-line, color-mix(in srgb, currentColor 22%, transparent));
      --m: var(--lw-muted, color-mix(in srgb, currentColor 70%, transparent));
      --s: var(--lw-surface, transparent); --r: var(--lw-radius, 12px); --f: var(--lw-focus, var(--focus, light-dark(#1d5fd1, #8ab4ff))); }
    [hidden] { display: none !important; }
    * { box-sizing: border-box; }
    a { color: var(--a); text-underline-offset: 2px; }
    :focus-visible { outline: 2px solid var(--f); outline-offset: 2px; }
    .filtros { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 140px), 1fr)); align-items: end; }
    .busca { grid-column: 1 / -1; }
    label { display: grid; gap: 4px; font-size: .85rem; color: var(--m); }
    input[type=search], select, textarea { font: inherit; color: inherit; background: var(--s); border: 1px solid var(--l);
      border-radius: 8px; padding: 8px 10px; min-height: 44px; width: 100%; }
    .linha { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; justify-content: space-between; margin: 12px 0; }
    .check { display: flex; align-items: center; gap: 8px; min-height: 44px; font-size: .95rem; color: inherit; }
    .check input { width: 20px; height: 20px; accent-color: var(--a); }
    button, .btn { font-family: inherit; font-weight: 600; font-size: .9rem; line-height: 1.2; border-radius: 999px; padding: 10px 14px; min-height: 44px;
      cursor: pointer; display: inline-flex; align-items: center; gap: 6px; text-decoration: none; }
    .sec { border: 1px solid var(--l); background: transparent; color: inherit; }
    .pri { border: 0; background: var(--a); color: var(--af); }
    .cont { color: var(--m); font-size: .9rem; }
    h2 { font-size: .8rem; letter-spacing: .06em; text-transform: uppercase; color: var(--m); margin: 28px 0 10px; font-weight: 600; }
    ul.lista { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }
    article { border: 1px solid var(--l); border-radius: var(--r); background: var(--s); padding: 14px 16px; scroll-margin-top: 16px; }
    article:focus { outline: 2px solid var(--a); outline-offset: 2px; }
    h3 { margin: 0 0 4px; font-size: 1.05rem; line-height: 1.35; overflow-wrap: anywhere; }
    .pes, .meta { margin: 0 0 6px; font-size: .9rem; }
    .meta { color: var(--m); display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: center; }
    .chip { border: 1px solid var(--l); border-radius: 999px; padding: 2px 8px; font-size: .78rem; }
    .resumo { margin: 8px 0; font-size: .95rem; overflow-wrap: anywhere; }
    .acoes { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 10px; }
    .sem { color: var(--m); font-size: .9rem; }
    .est { color: var(--m); font-size: .8rem; }
    .ia { border: 1px solid var(--l); border-radius: var(--r); padding: 12px; margin-bottom: 16px; }
    .ia textarea { min-height: 72px; resize: vertical; }
    .ia .resp { white-space: pre-wrap; margin: 12px 0 0; }
    .ia ol { margin: 8px 0 0; padding-left: 1.4em; font-size: .9rem; }
    .msg { color: var(--m); }
    .pessoa { display: grid; grid-template-columns: auto 1fr; gap: 12px 16px; align-items: center; border: 1px solid var(--l);
      border-radius: var(--r); padding: 16px; margin: 4px 0 16px; }
    .pessoa h2 { all: unset; display: block; font-size: 1.2rem; font-weight: 700; }
    .pessoa p { margin: 4px 0 0; }
    .pessoa > h3, .pessoa > ul, .pessoa > .sem { grid-column: 1 / -1; margin: 0; }
    .rosto { width: 96px; height: 96px; border-radius: 50%; object-fit: cover; }
    .galeria { list-style: none; padding: 0; display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); }
    .galeria img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px; display: block; }
    .galeria small { color: var(--m); font-size: .75rem; }
    .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
    @media (prefers-reduced-motion: no-preference) { article { transition: border-color .15s; } }
  `;

  const norm = s => (s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`);
  // só http(s): o catálogo pode vir de outro site e as fontes, da API
  const url = u => /^https?:\/\//i.test(u || "") ? esc(u) : "#";
  const hms = s => {
    const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, ss = String(s % 60).padStart(2, "0");
    return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
  };
  const sala = e => e.replace(/\s+[–-]\s+.*$/, ""); // "Espaço Haiti – LatinScience" -> "Espaço Haiti"

  class LatinowareCatalogo extends HTMLElement {
    static observedAttributes = ["lang", "src"];

    connectedCallback() {
      this.aoHash ||= () => this.irPara(location.hash);
      addEventListener("hashchange", this.aoHash);
      if (this.shadowRoot) return; // reinserido na página: já montado
      this.attachShadow({ mode: "open" });
      this.idioma = this.lerIdioma();
      this.carregar();
    }

    disconnectedCallback() { removeEventListener("hashchange", this.aoHash); }

    attributeChangedCallback(nome, antes, depois) {
      if (!this.shadowRoot || antes === depois) return;
      if (nome === "lang") this.idioma = this.lerIdioma();
      if (nome === "src") this.carregar(); else if (this.dados) this.montar();
    }

    // lido só na montagem e quando o atributo muda: tradutores de página trocam <html lang> depois
    lerIdioma() {
      const l = (this.getAttribute("lang") || document.documentElement.lang || navigator.language || "pt").slice(0, 2);
      return T[l] ? l : "pt";
    }

    get t() { return T[this.idioma]; }

    async carregar() {
      const vez = this.vez = (this.vez || 0) + 1; // src trocado no meio do fetch: vale o último
      this.shadowRoot.innerHTML = `<style>${CSS}</style><p class="msg" role="status">${esc(this.t.carregando)}</p>`;
      try {
        const r = await fetch(new URL(this.getAttribute("src") || "catalogo.json", document.baseURI));
        if (!r.ok) throw new Error(r.status);
        const dados = await r.json();
        if (vez !== this.vez) return;
        this.dados = dados;
        this.pessoas = new Map((dados.palestrantes || []).map(p => [p.url, p]));
        this.fotos = {};
        if (this.getAttribute("fotos")) { // opcional: sem fotos.json a visão do palestrante fica sem galeria
          try {
            const f = await (await fetch(new URL(this.getAttribute("fotos"), document.baseURI))).json();
            for (const p of f.palestrantes || []) this.fotos[p.palestrante_id] = p.fotos;
          } catch (e) { console.warn("latinoware-catalogo: fotos indisponíveis", e); }
        }
        if (this.dados.versao !== VERSAO) console.warn(`latinoware-catalogo: catálogo versão ${this.dados.versao}, componente ${VERSAO}`);
        this.grupos = this.agrupar(this.dados.palestras);
        this.montar();
      } catch (e) {
        console.error("latinoware-catalogo:", e);
        this.shadowRoot.innerHTML = `<style>${CSS}</style><p class="msg" role="alert">${esc(this.t.erroCarga)}</p>`;
      }
    }

    // keynotes e repetições da grade: mesmo título, dia e hora viram um card com todos os espaços
    agrupar(palestras) {
      const grupos = new Map();
      for (const p of palestras) {
        const k = `${norm(p.titulo).replace(/[^\p{L}\p{N}]/gu, "")}|${p.data}|${p.hora_inicio}`;
        const g = grupos.get(k) || grupos.set(k, { ...p, espacos: [], uids: [], video: null }).get(k);
        g.espacos.push(p.espaco);
        g.uids.push(p.uid);
        if (p.url_video && (!g.video || g.video.alinhamento === "estimado")) g.video = p;
      }
      for (const g of grupos.values()) {
        g.texto = norm([g.titulo, g.resumo_curto, g.trilha, ...g.espacos, ...g.palestrantes.map(s => s.nome)].join(" "));
        g.salas = [...new Set(g.espacos.map(sala))];
      }
      return [...grupos.values()];
    }

    montar() {
      const t = this.t, d = this.dados, api = this.getAttribute("api");
      const opcoes = (vals, rot = v => v) => `<option value="">${esc(t.todos)}</option>` +
        vals.map(v => `<option value="${esc(v)}">${esc(rot(v))}</option>`).join("");
      const fmtDia = new Intl.DateTimeFormat(this.idioma, { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
      const dia = v => fmtDia.format(new Date(`${v}T12:00:00Z`));
      const fmtCurto = new Intl.DateTimeFormat(this.idioma, { day: "numeric", month: "short", timeZone: "UTC" });
      const salas = [...new Set(this.grupos.flatMap(g => g.salas))].sort((a, b) => a.localeCompare(b));
      const trilhas = [...new Set(this.grupos.map(g => g.trilha))].sort((a, b) => a.localeCompare(b));
      const pessoas = new Map();
      for (const g of this.grupos) for (const s of g.palestrantes) pessoas.set(s.url || s.nome, s.nome);
      const nomes = [...pessoas].sort((a, b) => a[1].localeCompare(b[1]));
      const perguntar = api || this.hasAttribute("perguntar");

      let html = `<style>${CSS}</style>`;
      if (api) html += `<form class="ia" part="ia"><label>${esc(t.perguntaRotulo)}<textarea name="q" required minlength="3" maxlength="1000"></textarea></label>
        <div class="linha"><span></span><button class="pri" type="submit">${esc(t.enviar)}</button></div><div class="out"></div><p class="sr" role="status"></p></form>`;
      html += `<div class="filtros" part="filtros">
        <label class="busca">${esc(t.busca)}<input type="search" name="busca" placeholder="${esc(t.buscaPh)}"></label>
        <label>${esc(t.data)}<select name="data">${opcoes(d.evento.datas, dia)}</select></label>
        <label>${esc(t.espaco)}<select name="espaco">${opcoes(salas)}</select></label>
        <label>${esc(t.trilha)}<select name="trilha">${opcoes(trilhas)}</select></label>
        <label>${esc(t.palestrante)}<select name="palestrante"><option value="">${esc(t.todos)}</option>${
          nomes.map(([u, n]) => `<option value="${esc(u)}">${esc(n)}</option>`).join("")}</select></label></div>
        <div class="linha"><label class="check"><input type="checkbox" name="video">${esc(t.soVideo)}</label>
        <button type="button" class="sec limpar">${esc(t.limpar)}</button></div>
        <p class="cont" role="status"></p><section class="pessoa" hidden tabindex="-1" aria-labelledby="pessoa-nome"></section><p class="msg vazio" hidden>${esc(t.nenhum)}</p>`;
      let atual = null, i = 0;
      for (const g of this.grupos) {
        if (g.data !== atual) {
          if (atual) html += "</ul></section>";
          atual = g.data;
          html += `<section data-dia="${esc(g.data)}"><h2>${esc(dia(g.data))}</h2><ul class="lista">`;
        }
        const v = g.video, id = `t${i++}`;
        // o nome abre a visão do palestrante aqui; Ctrl/⌘-clique ainda vai à página do site
        const pes = g.palestrantes.map(s => s.url ? `<a href="${url(s.url)}" data-pessoa="${esc(s.url)}">${esc(s.nome)}</a>` : esc(s.nome)).join(", ");
        html += `<li data-i="${i - 1}"><article id="palestra-${esc(g.uids[0])}" tabindex="-1" aria-labelledby="${id}">
          <h3 id="${id}">${esc(g.titulo)}</h3>${pes ? `<p class="pes">${pes}</p>` : ""}
          <p class="meta"><span>${esc(g.salas.join(" · "))}</span><span>${esc(fmtCurto.format(new Date(`${g.data}T12:00:00Z`)))}, ${esc(g.hora_inicio)}–${esc(g.hora_fim)}</span>
          <span class="chip">${esc(g.trilha)}</span></p>
          <p class="resumo">${esc(g.resumo_curto)} <a href="${url(g.url_site)}">${esc(t.noSite)}</a></p>
          <div class="acoes">${v
            ? `<a class="btn pri" href="${url(v.url_video)}" target="_blank" rel="noopener" aria-describedby="${id}">▶ ${esc(t.assistir)} (${hms(v.t_inicio)})</a>${
              v.alinhamento === "estimado" ? `<span class="est">${esc(t.estimado)}</span>` : ""}`
            : `<span class="sem">${esc(t.semGravacao)}</span>`}${
            perguntar ? `<button type="button" class="sec perg" aria-describedby="${id}">${esc(t.perguntarIA)}</button>` : ""}</div>
        </article></li>`;
      }
      if (atual) html += "</ul></section>";
      const raiz = this.shadowRoot;
      raiz.innerHTML = html;
      this.cards = [...raiz.querySelectorAll("li[data-i]")];
      this.campos = Object.fromEntries([...raiz.querySelectorAll(".filtros [name], [name=video]")].map(c => [c.name, c]));

      const q = new URLSearchParams(location.search);
      for (const [n, c] of Object.entries(this.campos)) {
        if (c.type === "checkbox") c.checked = q.get(P + n) === "1"; else if (q.has(P + n)) c.value = q.get(P + n);
      }
      raiz.querySelector(".filtros").addEventListener("input", () => this.filtrar(true));
      this.campos.video.addEventListener("change", () => this.filtrar(true));
      raiz.querySelector(".limpar").addEventListener("click", () => this.limpar());
      if (!this.cliques) { // o shadowRoot sobrevive a montar(): um listener só
        this.cliques = e => {
          const b = e.target.closest(".perg"), a = e.target.closest("a[data-pessoa]");
          if (b) this.perguntar(this.grupos[b.closest("li").dataset.i]);
          if (a && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
            e.preventDefault();
            this.campos.palestrante.value = a.dataset.pessoa;
            this.filtrar(true);
            const caixa = this.shadowRoot.querySelector(".pessoa");
            caixa.scrollIntoView({ block: "start" });
            caixa.focus({ preventScroll: true }); // teclado e leitor de tela vão junto para a visão
          }
        };
        raiz.addEventListener("click", this.cliques);
      }
      if (api) {
        const f = raiz.querySelector(".ia");
        f.addEventListener("submit", e => { e.preventDefault(); this.enviar(); });
        f.q.value = (q.get(P + "pergunta") || "").slice(0, 1000);
      }
      this.filtrar(false);
      this.irPara(location.hash);
    }

    filtrar(gravar) {
      const c = this.campos, busca = norm(c.busca.value).trim().split(/\s+/).filter(Boolean);
      let n = 0;
      this.cards.forEach(li => {
        const g = this.grupos[li.dataset.i];
        const ok = busca.every(p => g.texto.includes(p)) && (!c.data.value || g.data === c.data.value)
          && (!c.espaco.value || g.salas.includes(c.espaco.value)) && (!c.trilha.value || g.trilha === c.trilha.value)
          && (!c.palestrante.value || g.palestrantes.some(s => (s.url || s.nome) === c.palestrante.value)) && (!c.video.checked || !!g.video);
        li.hidden = !ok;
        n += ok;
      });
      for (const s of this.shadowRoot.querySelectorAll("section[data-dia]")) s.hidden = !s.querySelector("li:not([hidden])");
      this.shadowRoot.querySelector(".cont").textContent = this.t.contador(n);
      this.shadowRoot.querySelector(".vazio").hidden = n > 0;
      this.mostrarPessoa(c.palestrante.value);
      if (!gravar) return;
      const q = new URLSearchParams(location.search);
      for (const [nome, campo] of Object.entries(c)) {
        const v = campo.type === "checkbox" ? (campo.checked ? "1" : "") : campo.value.trim();
        v ? q.set(P + nome, v) : q.delete(P + nome);
      }
      const qs = q.toString();
      try { // o Safari limita replaceState a ~100 chamadas em 30 s
        history.replaceState(history.state, "", `${location.pathname}${qs ? `?${qs}` : ""}${location.hash}`);
      } catch { /* o filtro vale, só não fica na URL */ }
    }

    // visão do palestrante: foto do site, dados, link, galeria do Flickr oficial com crédito e canal de remoção
    mostrarPessoa(chave) {
      const caixa = this.shadowRoot.querySelector(".pessoa"), p = this.pessoas.get(chave), t = this.t;
      caixa.hidden = !p;
      if (!p) return;
      const fotos = this.fotos[String(p.id)] || [];
      caixa.innerHTML = `${p.foto ? `<img class="rosto" src="${url(p.foto)}" alt="" width="96" height="96">` : ""}
        <div><h2 id="pessoa-nome">${esc(p.nome)}</h2><p class="sem">${esc([p.organizacao, p.pais].filter(Boolean).join(" · "))}</p>
        <p><a href="${url(p.url)}">${esc(t.paginaSite)}</a></p></div>${fotos.length ? `<h3>${esc(t.fotosEvento)}</h3>
        <ul class="galeria">${fotos.map(f => `<li><a href="${url(f.url_pagina)}" target="_blank" rel="noopener"><img
          src="${url(f.url_thumb)}" alt="${esc(t.fotoDe(p.nome))} (Flickr)" loading="lazy" width="150" height="150"></a>
          <small>${esc(t.foto)}: ${esc(f.autor)}/Latinoware${f.licenca_nome ? ` · ${esc(f.licenca_nome)}` : ""}</small></li>`).join("")}</ul>` : ""}
        <p class="sem">${esc(t.remover)} <a href="mailto:privacidade@ilove.the.br">privacidade@ilove.the.br</a></p>`;
    }

    limpar() {
      for (const c of Object.values(this.campos)) c.type === "checkbox" ? (c.checked = false) : (c.value = "");
      this.filtrar(true);
    }

    // a âncora #palestra-<uid> não atravessa o shadow DOM: rolar e focar à mão
    irPara(hash) {
      if (!hash.startsWith("#palestra-") || !this.cards) return;
      let uid = hash.slice(10);
      try { uid = decodeURIComponent(uid); } catch { /* hash malformado: usa cru */ }
      const li = this.cards.find(li => this.grupos[li.dataset.i].uids.includes(uid));
      if (!li) return;
      li.hidden = li.closest("section").hidden = false; // mostra o card sem apagar os filtros
      this.shadowRoot.querySelector(".cont").textContent = this.t.contador(this.cards.filter(c => !c.hidden).length);
      const art = li.querySelector("article");
      art.scrollIntoView({ block: "start" });
      art.focus({ preventScroll: true });
    }

    perguntar(g) {
      const pergunta = this.t.pergunta(g.titulo, g.palestrantes.map(s => s.nome).join(", "));
      // a versão da sala com vídeo é a que tem transcrição no índice
      const palestra_id = (g.video || g).id;
      const ev = new CustomEvent("perguntar", { bubbles: true, composed: true, cancelable: true,
        detail: { pergunta, palestra_id, uid: g.uids[0], titulo: g.titulo, palestrantes: g.palestrantes } });
      if (!this.dispatchEvent(ev) || !this.getAttribute("api")) return; // a página tratou
      const f = this.shadowRoot.querySelector(".ia");
      f.q.value = pergunta;
      f.scrollIntoView({ block: "start" });
      this.enviar(palestra_id);
    }

    // copiar (resposta + fontes em texto) e compartilhar (Web Share ou link copiado), com aviso para leitor de tela
    partilha(out, pergunta, resposta, fontes) {
      const t = this.t, aviso = this.shadowRoot.querySelector(".ia .sr");
      const avisar = msg => { aviso.textContent = ""; setTimeout(() => { aviso.textContent = msg; }, 50); };
      const copiar = (texto, ok) => Promise.resolve().then(() => navigator.clipboard.writeText(texto))
        .then(() => avisar(ok), () => avisar(t.naoCopiou));
      const caixa = document.createElement("div");
      caixa.className = "acoes";
      caixa.innerHTML = `<button type="button" class="sec">${esc(t.copiar)}</button><button type="button" class="sec">${esc(t.compartilhar)}</button>`;
      const [bCopiar, bPartilhar] = caixa.children;
      bCopiar.onclick = () => copiar(`${pergunta}\n\n${resposta}\n\n${fontes}`, t.copiado);
      const link = new URL(location.href);
      link.searchParams.set(P + "pergunta", pergunta); // quem abrir o link encontra a pergunta preenchida
      bPartilhar.onclick = () => navigator.share
        ? navigator.share({ title: document.title, text: pergunta, url: link.href })
          .catch(e => { if (e.name !== "AbortError") copiar(link.href, t.linkCopiado); })
        : copiar(link.href, t.linkCopiado);
      out.querySelector(".resp").after(caixa);
    }

    async enviar(palestra_id) {
      const t = this.t, f = this.shadowRoot.querySelector(".ia"), out = f.querySelector(".out");
      const pergunta = f.q.value.trim();
      if (pergunta.length < 3 || this.ocupado) return;
      this.ocupado = true;
      out.innerHTML = `<p class="msg">${esc(t.aguarde)}</p><p class="resp"></p><div class="fts"></div>`;
      const resp = out.querySelector(".resp"), fts = out.querySelector(".fts");
      let dadosFontes = [];
      const listar = fontes => (dadosFontes = fontes, `<h2>${esc(t.fontes)}</h2><ol>${fontes.map(s => {
        const link = s.url_video ? `<a href="${url(s.url_video)}" target="_blank" rel="noopener">▶ ${esc(t.video)} ${hms(+s.video_t || 0)}</a>`
          : `<a href="${url(s.url)}">${esc(/^https?:\/\/([^/]+)/i.exec(s.url || "")?.[1] || s.url)}</a>`;
        return `<li>${esc(s.titulo)}${s.palestrantes ? ` (${esc(s.palestrantes)})` : ""} · ${link}</li>`;
      }).join("")}</ol>`);
      const pedir = rota => fetch(`${this.getAttribute("api").replace(/\/$/, "")}${rota}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pergunta, idioma: this.idioma, ...(palestra_id && { palestra_id }) }),
        signal: AbortSignal.timeout(90000) });
      try {
        let r = await pedir("/ask/stream"), d;
        if (r.status === 404 || r.status === 405) r = await pedir("/ask"); // API sem streaming
        if (!r.ok) throw new Error(r.status === 429 ? "ocupado" : "erro");
        if (r.headers.get("content-type")?.startsWith("text/event-stream")) {
          // SSE: fontes chegam antes do texto, que vem em pedaços
          const leitor = r.body.pipeThrough(new TextDecoderStream()).getReader();
          let buf = "";
          try { for (let fim = false; !fim;) {
            const { value, done } = await leitor.read();
            if (done) break;
            buf += value.replace(/\r\n/g, "\n");
            for (let i; (i = buf.indexOf("\n\n")) >= 0; buf = buf.slice(i + 2)) {
              const b = buf.slice(0, i), ev = /^event: (.*)$/m.exec(b)?.[1], x = JSON.parse(/^data: (.*)$/m.exec(b)?.[1] || "{}");
              if (ev === "fontes") fts.innerHTML = listar(x.fontes || []);
              else if (ev === "token") resp.append(x.t);
              else if (ev === "fim") { d = x; fim = true; }
              else if (ev === "erro") throw new Error(x.status === 429 ? "ocupado" : "erro");
            }
          } } finally { leitor.cancel().catch(() => {}); }
        } else {
          d = await r.json();
          fts.innerHTML = listar(d.fontes || []);
        }
        if (!d) throw new Error("erro");
        out.querySelector(".msg").remove();
        resp.lang = d.idioma || "";
        resp.textContent = d.resposta;
        this.partilha(out, pergunta, d.resposta, `${t.fontes}:\n${dadosFontes.map(s =>
          `[${s.n}] ${s.titulo}${s.palestrantes ? ` (${s.palestrantes})` : ""} ${s.url_video || s.url}`).join("\n")}`);
      } catch (e) {
        const msg = e.name === "TimeoutError" ? t.demorou : e.message === "ocupado" ? t.ocupado : t.erro;
        out.innerHTML = `<p class="msg" role="alert">${esc(msg)}</p>`;
      } finally {
        this.ocupado = false;
      }
    }

  }

  if (!customElements.get("latinoware-catalogo")) customElements.define("latinoware-catalogo", LatinowareCatalogo);
})();
