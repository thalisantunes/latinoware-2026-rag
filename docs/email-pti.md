# RASCUNHO: e-mail ao Itaipu Parquetec (não enviado)

Rascunho para o Thalis revisar e enviar se quiser. Sem nomes nem endereços de terceiros aqui (repositório público): preencher
os campos entre colchetes antes de enviar.

---

**Assunto:** Catálogo das palestras da Latinoware 2026 com busca e link para o instante de cada vídeo

Olá, [nome do contato no Itaipu Parquetec],

Obrigado pela conversa sobre as gravações e as fotos. Enquanto vocês preparam os vídeos individuais, montei
um catálogo aberto das palestras da Latinoware 2026, que já está no ar:

- Página: https://ilove.the.br/latinoware/2026/rag/
- Código (livre, MIT): https://github.com/thalisantunes/latinoware-2026-rag

O que ele faz:
- Programação completa com busca e filtros por dia, espaço, temática e palestrante.
- Para as palestras que caíram nas lives do canal Itaipu Parquetec, um botão leva ao instante em que a
  palestra começa no vídeo (lido da transcrição, não só do horário da grade).
- Perguntas em português, inglês ou espanhol, respondidas por um modelo de linguagem livre rodando numa GPU
  doméstica, com as fontes citadas.

Se for útil para o site do evento, o catálogo pode ser incluído com 2 linhas, sem depender da nossa GPU:

```html
<script src="https://cdn.jsdelivr.net/gh/thalisantunes/latinoware-2026-rag@v1.0.0/web/latinoware-catalogo.js" defer></script>
<latinoware-catalogo src="https://ilove.the.br/latinoware/2026/rag/catalogo.json" lang="pt"></latinoware-catalogo>
```

É um projeto pessoal, sem fins lucrativos e sem vínculo oficial com a organização; a página diz isso
claramente. Se preferirem outro texto, logo ou que alguma palestra saia, é só pedir.

Quatro pedidos, quando der:

1. **Vídeos do Espaço Iguaçu.** Três lives aparecem nas playlists oficiais, mas o YouTube mostra "vídeo
   indisponível": `9Dck3H7xOGE` e `GSUcnRPFDpE` (16/10) e `KGIWmBq2t_A` (15/10); ao menos uma aparece com
   reivindicação de conteúdo da SME. Se for possível contestar a reivindicação ou republicar sem o trecho reivindicado, elas entram no
   catálogo. O vídeo `bBumpPxxsQk` está privado; se puder ser público, também entra.
2. **Espaço Argentina e demais salas sem live.** Se houver gravação (ou quando saírem os vídeos individuais),
   peço o link da playlist para ligar cada palestra ao seu vídeo.
3. **Fotos do Flickr.** Para mostrar fotos de cada palestrante no catálogo, preciso dos links dos álbuns e da
   licença de uso das fotos (para exibir com crédito "Foto: [autor]/Latinoware" e link de volta ao Flickr).
   Como o Flickr não emite mais chave de API gratuita, o mais simples é uma **pasta com os originais** de cada
   álbum (link de download, como Google Drive ou WeTransfer), com os mesmos nomes de arquivo publicados no Flickr;
   assim cada foto fica ligada à sua página no Flickr sem precisar de chave.
4. **Reconhecimento facial para achar as fotos de cada palestrante.** A ideia de vocês é ótima, mas foto de
   rosto é dado biométrico, sensível pela LGPD (art. 11). Antes de rodar, preciso:
   - o OK por escrito do Itaipu Parquetec;
   - definir quem é o controlador desse tratamento e a base legal (o mais seguro é o consentimento dos
     palestrantes, ou o próprio Parquetec rodar o código, que fica pronto e aberto);
   - concordância com as salvaguardas: vetores faciais só em memória e nunca gravados, publicação só de fotos
     públicas e com o palestrante em foco, revisão humana de cada foto e canal de remoção (opt-out) na página.

Obrigado de novo pelo evento. Ele continua rendendo depois que acaba.

Abraço,
Thalis Antunes de Souza
