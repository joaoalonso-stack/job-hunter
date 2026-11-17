# Job Hunter

Pipeline em Python que, todo dia, coleta vagas de emprego de várias fontes públicas, filtra pelo meu perfil
(economista recém-formado, foco em macro, mercado financeiro e asset), dá uma nota a cada vaga e entrega uma
página HTML, uma planilha e alertas no celular com o link para eu me candidatar.

**O sistema nunca se candidata a nada:** ele só encontra, organiza e prioriza; a candidatura é sempre minha.
**Custo zero:** só APIs e páginas públicas (sem login, sem cookie, respeitando o `robots.txt`), um modelo de
embeddings que roda localmente e a triagem feita pelo Claude Code na minha assinatura pessoal, sem API paga.

## O que ele faz

```
Coleta ──► Filtro ──► Dedup ──► Vaga ainda aberta? ──► Ranking ──► Triagem ──► Página / planilha / celular
~1.500/dia   ~250       ~220          ~170               top 60      nota 0–100       top 5 do dia
```

1. **Coleta** (`sources/`): API pública do portal da Gupy (busca por termos + lista de empresas acompanhadas),
   busca pública do LinkedIn, Vagas.com.br, Catho, Glassdoor (RJ), concursos (PCI) e bolsas do Ipea. Cada fonte é
   um coletor independente que devolve o mesmo `Job` normalizado; se uma fonte bloqueia ou cai, as outras seguem.
2. **Filtro duro** (`pipeline/filtro.py`): regras do `config/preferencias.yaml` — local (RJ/SP ou remoto),
   nível (exclui sênior, pleno, estágio…), vendas disfarçadas de "analista" e área de interesse no título.
3. **Deduplicação** (`pipeline/dedup.py`): a mesma vaga publicada em várias fontes vira uma só (similaridade de
   título e empresa com `rapidfuzz`), preferindo a fonte original da empresa.
4. **Vaga ainda aberta?** (`pipeline/abertas.py`): descarta vaga com prazo vencido, marcada como encerrada na
   página ou que sumiu da listagem da fonte.
5. **Ranking semântico** (`pipeline/ranking.py`): similaridade entre a descrição da vaga e o meu perfil
   (`docs/perfil.md`) com `sentence-transformers` multilíngue rodando em CPU; as 60 melhores seguem.
6. **Triagem com LLM** (`triagem.py` + `.claude/commands/triagem.md`): o Claude Code avalia cada vaga com uma
   rubrica explícita e devolve JSON com nota 0–100, trilha de carreira, por que encaixa, o que falta e red flags
   (senioridade disfarçada, PJ, "remoto" que não é remoto, prazo vencido…). A nota final é ponderada pelo peso
   da trilha definido nas preferências.
7. **Saídas** (`saidas/`, `notify.py`):
   - página HTML única e offline, com abas Hoje / Ativas / Arquivadas, busca, filtros e detalhes da nota;
   - planilha Excel com links, formatação condicional e colunas editáveis de acompanhamento (status, data em que
     apliquei, observações), que a rodada seguinte lê de volta para o banco;
   - alerta no celular (ntfy) com as 5 melhores do dia, só acima de uma nota mínima.

Tudo fica num SQLite (`data/jobhunter.db`), que guarda histórico, triagens e o status de cada candidatura.
A rodada é agendada no Agendador de Tarefas do Windows, com nova tentativa automática por etapa e log em arquivo.

## Decisões de projeto
- **Fontes públicas e educadas:** sem login, pausas entre requisições, limite de páginas e parada imediata da
  fonte ao primeiro sinal de bloqueio (HTTP 429).
- **Regras editáveis, não código:** locais, termos, exclusões, pesos e limiares ficam no YAML.
- **LLM como avaliador, não como decisor:** a rubrica é explícita, a saída é JSON validado e a nota final é
  recalculada no código; se a triagem falhar, o relatório sai com a nota do ranking e a vaga é triada no dia seguinte.
- **Testado:** 87 testes (`pytest`) com páginas reais salvas como fixtures, sem acesso à rede.

## Stack
Python 3.12 · SQLite · rapidfuzz · sentence-transformers (PyTorch CPU) · openpyxl · PyYAML · pytest ·
Claude Code (`claude -p`) · ntfy · Agendador de Tarefas do Windows

## Como rodar
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config\ntfy_topic.exemplo.txt config\ntfy_topic.txt   # e coloque o seu tópico do ntfy
.venv\Scripts\python run.py                  # rodada completa
.venv\Scripts\python run.py --sem-triagem    # sem chamar o Claude Code
.venv\Scripts\python run.py --so-relatorios  # só refaz página e planilha
.venv\Scripts\python -m pytest -q            # testes
```
O perfil (`docs/perfil.md`) e as preferências (`config/preferencias.yaml`) são os meus; troque pelos seus.

`monitor_vagas.py` é a primeira versão do projeto (alertas imediatos a cada 3 horas com filtro por regex), mantida
em paralelo enquanto a versão nova amadurece.
