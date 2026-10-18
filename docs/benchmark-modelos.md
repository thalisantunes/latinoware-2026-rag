# Benchmark de LLMs para o RAG Latinoware 2026

Data: 2026-10-18. Legenda: [V] verificado em fonte citada; [S] estimativa minha (não medido); [NV] não verificado.
Hardware: RTX 5060 Ti 16 GB (448 GB/s). Já ocupam VRAM: bge-m3 ~1,2 GB + reranker ~1 GB. Sobram ~13,5 GB para LLM + KV (num_ctx 16384 hoje).
Base atual (qwen3:14b, ~9 GB Q4): referência de controle no benchmark.

## 1. Candidatos

Velocidade = decode em tokens/s, estimada por banda de memória (modelo denso: ~0,5-0,6 x 448 / tamanho GB) [S]. Só o gpt-oss tem medição citada [V].

| # | Tag Ollama | VRAM (pesos) | tok/s [S] | Qualidade (fonte) | pt-BR | Licença |
|---|---|---|---|---|---|---|
| 1 | `qwen3.5:9b` (q4_K_M) | 6,6 GB [V] | 45-55 | IFEval 91,5; MMLU-Pro 82,5; MMMLU 81,2; MMLU-ProX 76,3 (card HF) [V] | sim, 201 idiomas [V] | Apache-2.0 [V] |
| 2 | `qwen3.5:4b` (q4_K_M) | 3,3 GB [V] | 90-110 | mesma família, menor; sem tabela lida [NV] | sim | Apache-2.0 |
| 3 | `gemma4:12b-it-qat` | 7,2 GB [V] | 40-50 | MMLU-Pro 77,2; MMMLU 83,4 (card HF) [V]; IFEval não reportado | sim, 35+ idiomas nativos [V] | Apache-2.0 [V] |
| 4 | `gemma4:e4b-it-qat` | 6,1 GB [V] (4,5B efetivos) | 70-90 | MMLU-Pro 69,4; MMMLU 76,6 [V] | sim [V] | Apache-2.0 [V] |
| 5 | `ministral-3:8b` (alt. `ministral-3:14b`, 9,1 GB) | 6,0 GB [V] | 50-60 (14b: 30-35) | Sem número no texto lido (só gráfico GPQA) [NV] | sim, pt listado [V] | Apache-2.0 [V] |
| 6 | `granite4.2:8b` | 5,3 GB [V] | 55-65 | Foco em RAG/tool use da IBM; sem benchmark lido [NV] | "multilíngue", pt não confirmado na página [NV] | Apache-2.0 [V] |
| 7 | `gpt-oss:20b` (MXFP4) | 14 GB [V] | ~44 (medido, ctx 128k) [V] | Sem número lido [NV]; raciocínio forte, pt mediano [S] | pt não confirmado [NV] | Apache-2.0 [V] |

Cabe? 1-6 sim (com 3 GB de folga: #3 e #5-14b ficam ~11-12 GB com KV 16k). #7 NÃO: 14 GB + 2,2 GB de bge-m3/reranker > 16 GB; só com embedder em CPU. Excluir.
Descartados por tamanho: `qwen3.5:27b` (17 GB), `qwen3.5:35b-a3b` (22 GB), `gemma4:26b-a4b-it-qat` (16 GB), `nemotron-3.5-lightning` (19 GB), `granite4.2:30b`, `qwen3.6`/`qwen3.8` (27-35b) [V pela listagem do Ollama]. Mistral-small3.2 (24b) e Phi-4 (14b, 2024) são pesados/antigos. Sailor2 é sudeste-asiático; Tucano/SmolLM3/EXAONE não aparecem na biblioteca Ollama [V] (EXAONE: só 3.5/Deep, coreano-inglês).
Notas: Qwen3.5 liga o thinking por padrão e não aceita `/nothink`; usar `"think": false` na API do Ollama [V no card; comportamento no Ollama: NV, testar]. Gemma 4 liga/desliga via `<|think|>` no system prompt [V].

## 2. Recomendação: 3 para o benchmark final

1. `qwen3.5:9b`: maior IFEval e MMLU-Pro da lista, 6,6 GB (sobra 2,4 GB vs qwen3:14b), 201 idiomas. Principal candidato a substituir o qwen3:14b com ganho de tempo ~40%.
2. `gemma4:12b-it-qat`: melhor MMMLU (83,4), QAT preserva qualidade em 7,2 GB; costuma respeitar bem nomes próprios e idioma da pergunta [S]. Teto de qualidade.
3. `ministral-3:8b`: família diferente (Mistral), pt explícito, 6 GB, rápido; diversifica o risco de ambos Qwen/Gemma falharem em citação.
Reserva de velocidade (rodar só se 1-3 ficarem > 6 s): `gemma4:e4b-it-qat` e `qwen3.5:4b`. Controle: `qwen3:14b` atual e `qwen2.5:14b` do lab (só leitura, sem baixar nada).

## 3. Reescrita de pergunta (≤ 2 GB)

- `qwen3.5:2b-q4_K_M` (1,9 GB [V]), think=false, temperature 0, num_predict 64.
- `qwen3.5:0.8b-q8_0` (1,0 GB [V]): mais rápido, mais risco de perder nomes próprios; medir.
Ambos Apache-2.0 [V]. Alternativa `granite4.2:3b-q3_K_L` (2,0 GB) fica no limite. Critério: manter nomes ("maddog", "Home Assistant"), mesmo idioma, <1 s [S].

## 4. Reranker

Manter `BAAI/bge-reranker-v2-m3` (0,6B, Apache-2.0 [S]) como padrão. Tabela do card do jina-reranker-v3 [V]: MIRACL bge-v2-m3 69,32; jina-v3 66,83; Qwen3-Reranker-0.6B 57,70. O card do Qwen3-Reranker-0.6B [V] mostra o inverso em MMTEB-R (66,36 vs 58,36) e MLDR (67,28 vs 59,51): protocolos distintos, conflito sem arbitragem; MIRACL é o mais próximo de pt/es/en curto.
- `jina-reranker-v3`: CC BY-NC 4.0 [V]; evitar (licença não permissiva).
- `mxbai-rerank-base-v2`: Apache-2.0, mas score multilíngue 28,56 no card [V]; fraco fora de en/zh.
- `Qwen3-Reranker-0.6B`: Apache-2.0 [V]; único desafiante plausível; A/B contra o bge usando recall@8 nas 30 perguntas.
Serviço: Ollama não tem `/api/rerank` nativo (buscas não achei evidência) [NV]; usar `sentence-transformers` CrossEncoder (fp16, ~1,1 GB) ou TEI. O Qwen3-Reranker precisa de vLLM ou sentence-transformers; GGUF de terceiros [NV].

## 5. Protocolo

Perguntas: as 10 de `06_avaliar_busca.py` (o script tem 10, não 20; conferir se há mais no gabarito) + 20 novas (7 pt, 7 en, 6 es), incluindo: 5 com nome próprio (maddog, Home Assistant), 5 sem resposta no corpus (deve recusar), 5 cruzando idioma (pergunta en, palestra pt), 5 que exigem 2+ trechos. Total 30, arquivo fixo `data/perguntas_bench.json` com idioma esperado e trechos-gabarito.
Fixar: mesmos 8 trechos por pergunta (congelar a saída da busca+rerank), temperature 0.2, num_ctx 16384, num_predict 800, think=false, `keep_alive` longo.
Execução: 1 aquecimento descartado, depois 3 execuções por modelo e pergunta (30 x 3 x 4 modelos = 360 chamadas), `stream: true`.
Métricas:
1. TTFT (s) e tempo total (s), p50 e p95.
2. tokens/s = `eval_count / eval_duration` do Ollama (e `prompt_eval_duration` à parte).
3. VRAM pico: `nvidia-smi --query-gpu=memory.used -l 1` durante a rodada, com bge-m3 e reranker carregados.
4. Idioma correto: `langdetect` + checagem de nomes próprios preservados (regex).
5. Fidelidade e citações [n]: juiz Claude via Agent (modelo Sonnet, 1 agent por modelo testado, cego ao nome do modelo). Rubrica 0-2: afirmações sustentadas pelos trechos; [n] aponta para o trecho certo; recusa correta quando falta evidência; sem invenção. Checagem automática extra: todo [n] existe (1-8).
Aprovação: fidelidade média >= a do qwen3:14b menos 0,1, idioma 100%, total p50 <= 8 s (meta p95 <= 12 s). Desempate: menor VRAM.
Custo do juiz: 360 respostas em lotes de ~30 por agent; reduzir a 1 execução julgada por pergunta se pesar (as 3 execuções servem a latência).

Fontes: ollama.com/library (listagem e tags de qwen3.5, gemma4, granite4.2, ministral-3, gpt-oss); huggingface.co/Qwen/Qwen3.5-9B; huggingface.co/google/gemma-4-12b-it; huggingface.co/jinaai/jina-reranker-v3; huggingface.co/Qwen/Qwen3-Reranker-0.6B; huggingface.co/mixedbread-ai/mxbai-rerank-base-v2; Hardware Corner (gpt-oss 20b, 43,8 tok/s).

## 6. Resultado (2026-10-18, medido)

Protocolo: `09_benchmark_llm.py` (`make benchmark MODELOS="..."`), 30 perguntas de `tests/perguntas_bench.json`
(10 do gabarito, 5 com nome próprio, 5 sem resposta, 5 de idioma cruzado, 5 com vários trechos), contexto
congelado (mesmos 8 trechos e prompt da API), 1 aquecimento + 3 rodadas, temperature 0,2, num_ctx 16384,
think=false. Qualidade: juiz Claude Sonnet cego (respostas A-D embaralhadas por pergunta), 1ª rodada,
notas 0-2 em fidelidade, citações e utilidade (soma 0-6).

| modelo | 1º token p50 | total p50 | total p95 | tokens/s | VRAM pico | idioma | [n] válidos | qualidade (0-6) | sem resposta | cruzado |
|---|---|---|---|---|---|---|---|---|---|---|
| qwen3:14b (atual) | 2,9 s | 7,1 s | 22,0 s | 42 | 13,4 GB | 100% | 100% | 5,03 | 5,6 | 4,2 |
| qwen3.5:9b | 0,7 s | 4,5 s | 12,5 s | 68 | 8,3 GB | 100% | 100% | 5,33 | 5,0 | 4,4 |
| gemma4:12b-it-qat | 2,2 s | 7,5 s | 13,6 s | 48 | 9,7 GB | 100% | 100% | 5,90 | 6,0 | 5,8 |
| ministral-3:8b | 1,7 s | 7,9 s | 13,8 s | 68 | 9,5 GB | 100% | 100% | 4,03 | 5,4 | 3,2 |

Caso dirigido (trecho fora da grade, "Quem falou sobre Nova Porteirinha?" em pt/en/es, 3× cada): o modelo
deve dar o instante do vídeo que está no cabeçalho do trecho. Acertos: qwen3:14b 9/9, gemma4 7/9,
qwen3.5:9b 4/9 (omite ou inventa o horário).

Decisão pela regra (qualidade igual ou melhor e tempo total ≥30% menor): **nenhum candidato passa; fica o
qwen3:14b**. O qwen3.5:9b é 37% mais rápido e tem nota geral maior, mas falha no caso dirigido e recusa pior
quando não há resposta. O gemma4 tem a melhor qualidade em todos os tipos e usa 3,7 GB a menos de VRAM
(liberaria a GPU para o reranker), sem ganho de tempo no p50 (p95 bem melhor): candidato se a prioridade for
qualidade. Removidos do disco: qwen3.5:9b e ministral-3:8b. Limites: 30 perguntas, 1 juiz, 1 rodada julgada.
