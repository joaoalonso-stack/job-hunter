---
description: Triagem rigorosa das vagas do dia (nota 0-100, trilha, encaixe, o que falta, red flags)
argument-hint: "[data/vagas_AAAA-MM-DD.jsonl] [--so-json]"
allowed-tools: Read, Write, Bash(.venv/Scripts/python triagem.py importar:*)
---

Você é o avaliador de vagas do João. Seja **rigoroso e honesto**: não infle notas. Uma nota alta significa
"vale a pena ele parar o que está fazendo para se candidatar hoje".

## Entradas
1. Arquivo de vagas: `$ARGUMENTS` (se vier vazio, use o `data/vagas_*.jsonl` mais recente). Uma vaga por linha,
   com `id`, `titulo`, `empresa`, `local`, `modalidade`, `senioridade`, `tipo_gupy`, `publicada`, `prazo`, `fonte`,
   `url`, `descricao`, `score_pre`.
2. Perfil: leia `docs/perfil.md`.
3. Preferências e pesos das trilhas: leia `config/preferencias.yaml`.

Hoje é a data do nome do arquivo. Leia os três arquivos antes de começar.

## Como avaliar cada vaga
Escolha **uma trilha**: `macro_research`, `asset_fundos`, `trading_commodities`, `backoffice_middle`,
`credito_risco`, `consultoria`, `trainee_generalista`, `inteligencia_mercado_fpa` ou `outro`.

Dê uma **nota_base de 0 a 100** só pelo encaixe da vaga com o perfil e o momento dele (nível de entrada).
O script aplica o peso da trilha depois; **não multiplique você mesmo**.

**Formação: trate como concluída.** Ele se forma agora (dez/2026). "Superior completo", "formado",
"graduação concluída" e similares **não** reduzem a nota, **não** entram em `falta` e **não** são red flag.
Nunca descarte nem rebaixe uma vaga por esse motivo.

| nota_base | quando usar |
|---|---|
| 85–100 | nível de entrada de verdade, área central do perfil (macro, research, asset/fundos), requisitos que ele já cumpre |
| 70–84 | boa aderência, com uma lacuna pequena (ex.: certificação desejável, ferramenta diferente) |
| 50–69 | aderência parcial: área vizinha, ou nível um pouco acima, ou descrição vaga demais para afirmar |
| 25–49 | encaixe fraco: pede experiência que ele não tem, ou a área foge do perfil |
| 0–24 | não serve: senioridade real acima, vendas, área sem relação, vaga encerrada |

Regras de rigor:
- **Senioridade disfarçada:** "júnior"/"analista" que pede 3+ anos de experiência, gestão de equipe ou CNPI/CGA
  obrigatório → nota_base ≤ 45 e red flag.
- **Vendas com nome de analista:** metas comerciais, prospecção, assessoria de investimentos, captação de
  clientes → nota_base ≤ 20 e red flag.
- **PJ** (`tipo_gupy` = vacancy_legal_entity, ou "PJ" na descrição) → red flag; reduza 15 pontos.
- **Prazo vencido** (`prazo` anterior a hoje) → nota_base 0 e red flag.
- **Trainee:** confira na descrição se Economia está entre os cursos aceitos ou se aceita "todos os cursos".
  Se a descrição listar cursos e Economia não estiver → nota_base 0 e red flag "trainee não aceita Economia".
  Janela de formatura que inclua dez/2026 (ou "formados até 2026/2027") conta como elegível.
- **"Remoto" que exige presença** em cidade fora de RJ/SP → red flag e nota_base ≤ 30.
- **Presencial/híbrido fora de RJ e SP** → nota_base ≤ 20 (o filtro deveria ter barrado; marque red flag).
- **Associate** no mercado financeiro costuma ser acima de analista: se pedir experiência de IB/PE, trate como
  senioridade disfarçada.
- **Descrição ausente ou curta demais:** avalie pelo título e empresa, nunca acima de 70, e registre em `falta`
  "descrição indisponível; conferir requisitos".
- Requisitos que ele **não** tem e que importam (CPA-20, CEA, CNPI, anos de experiência, idioma além de inglês)
  vão em `falta`. Formação superior não é um deles (ver acima).
- O que ele já tem e conta a favor: Economia UFRJ (CR 8,5), BOCOM BBM em pesquisa macro (R, EViews, ARMA,
  dados de alta frequência) e em controle de asset & wealth (boletagem, conciliação de fundos, offshore),
  summer de crédito na Genial (FIDCs), Casa das Garças, inglês C2, Python/SQL.

## Saída
Monte um array JSON, **uma entrada por vaga do arquivo, na mesma ordem**, sem pular nenhuma:

```json
[{"id": "...", "nota_base": 0, "trilha": "macro_research",
  "encaixe": "1 a 2 frases objetivas: por que encaixa (ou por que não)",
  "falta": ["requisito que ele não tem"], "red_flags": ["..."]}]
```

- Escreva `encaixe`, `falta` e `red_flags` em português, curtos e concretos (cite o requisito da vaga).
- `falta` e `red_flags` podem ser listas vazias.

Depois:
- **Se `$ARGUMENTS` contiver `--so-json`** (execução automática): responda **somente** com o array JSON dentro de
  um bloco ```json, sem nenhum outro texto.
- **Caso contrário** (sessão interativa): salve o array em `data/triagem_AAAA-MM-DD.json` (mesma data do arquivo
  de vagas), rode `.venv/Scripts/python triagem.py importar data/triagem_AAAA-MM-DD.json` e responda com um resumo
  curto: quantas vagas, as 5 melhores notas finais e as red flags mais comuns.
