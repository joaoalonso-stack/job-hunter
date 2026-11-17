"""SQLite como fonte da verdade: vagas, triagens, status das candidaturas, alertas e execuções."""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "jobhunter.db"
LOG_PATH = BASE / "vagas_encontradas.md"

SCHEMA = """
CREATE TABLE IF NOT EXISTS vagas (
    id TEXT PRIMARY KEY,
    fonte TEXT, titulo TEXT, empresa TEXT, local TEXT, modalidade TEXT, senioridade TEXT,
    publicada TEXT, prazo TEXT, url TEXT, descricao TEXT, extra TEXT,
    primeira_vez TEXT, ultima_vez TEXT
);
CREATE TABLE IF NOT EXISTS triagens (
    vaga_id TEXT PRIMARY KEY REFERENCES vagas(id),
    nota INTEGER, trilha TEXT, encaixe TEXT, falta TEXT, red_flags TEXT, triada_em TEXT
);
CREATE TABLE IF NOT EXISTS status (
    vaga_id TEXT PRIMARY KEY REFERENCES vagas(id),
    status TEXT, data_aplicacao TEXT, observacoes TEXT, atualizado_em TEXT
);
-- Chaves (id da vaga ou título+empresa) que já viraram alerta no monitor de 3 em 3 horas.
CREATE TABLE IF NOT EXISTS vistas (chave TEXT PRIMARY KEY, registrada_em TEXT);
-- Alertas ainda não enviados ao ntfy (falha de rede ou limite por rodada).
CREATE TABLE IF NOT EXISTS fila_ntfy (vaga_id TEXT PRIMARY KEY, payload TEXT, criado_em TEXT);
CREATE TABLE IF NOT EXISTS execucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, etapa TEXT, inicio TEXT, fim TEXT, ok INTEGER, detalhe TEXT
);
"""

COLS = ["id", "fonte", "titulo", "empresa", "local", "modalidade", "senioridade", "publicada", "prazo", "url",
        "descricao", "extra"]


def agora():
    return datetime.now().isoformat(timespec="seconds")


# Resultado do pipeline diário em cada vaga (acrescentadas depois da etapa 1, por isso via ALTER TABLE).
COLUNAS_PIPELINE = {"filtro_ok": "INTEGER", "motivo_filtro": "TEXT", "duplicata_de": "TEXT", "score_pre": "REAL",
                    "rodada": "TEXT", "aberta": "INTEGER", "verificada_em": "TEXT", "situacao": "TEXT"}


def conectar(path=None):
    path = path or DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    existentes = {r[1] for r in conn.execute("PRAGMA table_info(vagas)")}
    for col, tipo in COLUNAS_PIPELINE.items():
        if col not in existentes:
            conn.execute(f"ALTER TABLE vagas ADD COLUMN {col} {tipo}")
    if "nota_base" not in {r[1] for r in conn.execute("PRAGMA table_info(triagens)")}:
        conn.execute("ALTER TABLE triagens ADD COLUMN nota_base INTEGER")
    conn.commit()
    return conn


def atualizar_pipeline(conn, vaga_id, **campos):
    campos = {k: v for k, v in campos.items() if k in COLUNAS_PIPELINE}
    if campos:
        conn.execute(f"UPDATE vagas SET {', '.join(f'{k}=?' for k in campos)} WHERE id=?", [*campos.values(), vaga_id])


def salvar_triagens(conn, itens):
    """Grava as notas da /triagem (uma linha por vaga; uma nova triagem substitui a anterior)."""
    ts = agora()
    for t in itens:
        conn.execute(
            "INSERT INTO triagens (vaga_id, nota, trilha, encaixe, falta, red_flags, triada_em, nota_base)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(vaga_id) DO UPDATE SET nota=excluded.nota,"
            " trilha=excluded.trilha, encaixe=excluded.encaixe, falta=excluded.falta, red_flags=excluded.red_flags,"
            " triada_em=excluded.triada_em, nota_base=excluded.nota_base",
            (t["id"], int(t["nota"]), t.get("trilha", "outro"), t.get("encaixe", ""),
             json.dumps(t.get("falta", []), ensure_ascii=False), json.dumps(t.get("red_flags", []), ensure_ascii=False),
             t.get("triada_em", ts), t.get("nota_base", t["nota"])))
    conn.commit()


def ids_triados(conn):
    return {r[0] for r in conn.execute("SELECT vaga_id FROM triagens")}


STATUS_VALIDOS = {"", "interessado", "apliquei", "descartei"}


def salvar_status(conn, vaga_id, status=None, data_aplicacao=None, observacoes=None, quando=None):
    """Atualiza o acompanhamento da candidatura. Campos None ficam como estão; vale a edição mais recente
    (o HTML e a planilha mandam o horário da edição em `quando`)."""
    quando = quando or agora()
    atual = conn.execute("SELECT * FROM status WHERE vaga_id=?", (vaga_id,)).fetchone()
    if atual and atual["atualizado_em"] and atual["atualizado_em"] > quando:
        return False
    if status is not None and status not in STATUS_VALIDOS:
        raise ValueError(f"status inválido: {status!r}")
    novo = {"status": status, "data_aplicacao": data_aplicacao, "observacoes": observacoes}
    if atual:
        novo = {k: (v if v is not None else atual[k]) for k, v in novo.items()}
    conn.execute("INSERT INTO status VALUES (?, ?, ?, ?, ?) ON CONFLICT(vaga_id) DO UPDATE SET status=excluded.status,"
                 " data_aplicacao=excluded.data_aplicacao, observacoes=excluded.observacoes,"
                 " atualizado_em=excluded.atualizado_em",
                 (vaga_id, novo["status"] or "", novo["data_aplicacao"] or "", novo["observacoes"] or "", quando))
    conn.commit()
    return True


def upsert_vagas(conn, jobs):
    """Grava as vagas coletadas; numa vaga já conhecida só atualiza os campos e a última aparição."""
    ts = agora()
    for j in jobs:
        d = j.to_dict()
        d["extra"] = json.dumps(d["extra"], ensure_ascii=False)
        conn.execute(
            f"INSERT INTO vagas ({','.join(COLS)}, primeira_vez, ultima_vez) VALUES ({','.join('?' * len(COLS))}, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in COLS[1:] if c != "descricao")
            + ", descricao=CASE WHEN excluded.descricao<>'' THEN excluded.descricao ELSE vagas.descricao END"
            + ", ultima_vez=excluded.ultima_vez",
            [d[c] for c in COLS] + [ts, ts])
    conn.commit()


def vaga_de_linha(row):
    from sources.base import Job
    d = {c: row[c] or "" for c in COLS}
    d["extra"] = json.loads(d["extra"] or "{}")
    return Job(**d)


def carregar_vagas(conn, onde="1=1", params=()):
    return [vaga_de_linha(r) for r in conn.execute(f"SELECT * FROM vagas WHERE {onde}", params)]


def ja_vistas(conn, chaves):
    chaves = list(chaves)
    if not chaves:
        return set()
    achadas = set()
    for i in range(0, len(chaves), 500):
        lote = chaves[i:i + 500]
        rows = conn.execute(f"SELECT chave FROM vistas WHERE chave IN ({','.join('?' * len(lote))})", lote)
        achadas.update(r[0] for r in rows)
    return achadas


def marcar_vistas(conn, chaves):
    ts = agora()
    conn.executemany("INSERT OR IGNORE INTO vistas VALUES (?, ?)", [(c, ts) for c in chaves])
    conn.commit()


def fila_adicionar(conn, payloads):
    ts = agora()
    conn.executemany("INSERT OR IGNORE INTO fila_ntfy VALUES (?, ?, ?)",
                     [(p["id"], json.dumps(p, ensure_ascii=False), ts) for p in payloads])
    conn.commit()


def fila_listar(conn):
    return [json.loads(r[0]) for r in conn.execute("SELECT payload FROM fila_ntfy ORDER BY criado_em")]


def fila_remover(conn, vaga_id):
    conn.execute("DELETE FROM fila_ntfy WHERE vaga_id=?", (vaga_id,))
    conn.commit()


def registrar_execucao(conn, etapa, inicio, ok, detalhe=""):
    conn.execute("INSERT INTO execucoes (etapa, inicio, fim, ok, detalhe) VALUES (?, ?, ?, ?, ?)",
                 (etapa, inicio, agora(), int(ok), detalhe))
    conn.commit()


LOG_LINHA_RE = re.compile(r"^- \[(\w+)\] \[(.+)\]\((\S+)\) — (.*)$")
FONTE_POR_DOMINIO = [("linkedin.com", "LinkedIn"), ("gupy.io", "Gupy"), ("vagas.com.br", "Vagas.com.br"),
                     ("catho.com.br", "Catho"), ("glassdoor", "Glassdoor"), ("pciconcursos", "PCI Concursos"),
                     ("ipea.gov.br", "Ipea")]


FONTES_CONHECIDAS = {nome for _, nome in FONTE_POR_DOMINIO} | {"FGV", "FCC"}


def _fonte_do_historico(partes, url):
    """Usa a fonte escrita na linha quando é uma fonte conhecida; nas linhas antigas (sem fonte, ou com
    "·" dentro do título/empresa, que desalinha as colunas) deduz pelo domínio da URL."""
    escrita = next((p.strip(" ·") for p in partes[2:] if p.strip(" ·") in FONTES_CONHECIDAS), "")
    return escrita or next((nome for dom, nome in FONTE_POR_DOMINIO if dom in url), "")


def migrar_legado(conn, base=None):
    """Importa uma única vez o estado do monitor antigo: vistas.json, fila.json e o histórico
    vagas_encontradas.md (vira vagas já conhecidas). Os JSON são renomeados para .migrado."""
    base = Path(base or BASE)
    feito = []
    vistas = base / "vistas.json"
    if vistas.exists():
        marcar_vistas(conn, json.loads(vistas.read_text("utf-8")))
        vistas.rename(vistas.with_suffix(".json.migrado"))
        feito.append("vistas")
    fila = base / "fila.json"
    if fila.exists():
        itens = json.loads(fila.read_text("utf-8"))
        fila_adicionar(conn, [{**v, "id": v["id"]} for v in itens])
        fila.rename(fila.with_suffix(".json.migrado"))
        feito.append("fila")
    log = base / "vagas_encontradas.md"
    if log.exists() and not conn.execute("SELECT 1 FROM vagas WHERE fonte LIKE 'historico:%' LIMIT 1").fetchone():
        data = ""
        for linha in log.read_text("utf-8").splitlines():
            if linha.startswith("## "):
                m = re.match(r"## (\d\d)/(\d\d)/(\d{4}) (\d\d:\d\d)", linha)
                data = f"{m.group(3)}-{m.group(2)}-{m.group(1)}T{m.group(4)}:00" if m else data
                continue
            m = LOG_LINHA_RE.match(linha.strip())
            if not m:
                continue
            cat, titulo, url, resto = m.groups()
            partes = [p.strip() for p in resto.split(" · ")]
            fonte = _fonte_do_historico(partes, url)
            conn.execute(
                "INSERT OR IGNORE INTO vagas (id, fonte, titulo, empresa, local, url, extra, primeira_vez, ultima_vez)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("hist:" + url, "historico:" + fonte, titulo, partes[0] if partes else "",
                 partes[1] if len(partes) > 1 else "", url, json.dumps({"cat": cat}), data, data))
        conn.commit()
        feito.append("historico")
    return feito
