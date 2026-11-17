"""Pré-ranqueamento local com embeddings (sentence-transformers, roda no PC, sem custo): similaridade entre
cada vaga e o docs/perfil.md, mais bônus pelo Rio de Janeiro e por sinais de nível de entrada."""
import re

from sources.base import norm

MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
BONUS_LOCAL_PREFERIDO = 3.0
BONUS_ENTRADA = 2.0
_modelo = None


def modelo():
    global _modelo
    if _modelo is None:
        from sentence_transformers import SentenceTransformer  # import pesado: só quando for ranquear
        _modelo = SentenceTransformer(MODELO, device="cpu")
    return _modelo


def texto_perfil(perfil_md, prefs):
    return perfil_md + "\n\nVagas de interesse: " + ", ".join(prefs["termos"])


def texto_vaga(job):
    desc = re.sub(r"\s+", " ", job.descricao or "")[:1500]
    return f"{job.titulo}. {job.empresa}. {desc}"


def bonus(job, prefs):
    b = 0.0
    loc = norm(job.local)
    if any(l.get("preferido") and norm(l["nome"]) in loc for l in prefs["locais"]):
        b += BONUS_LOCAL_PREFERIDO
    t = norm(job.titulo)
    if any(re.search(rf"\b{re.escape(norm(i))}", t) for i in prefs["incluir"]) or job.senioridade == "trainee":
        b += BONUS_ENTRADA
    return b


def pontuar(jobs, perfil_md, prefs, codificar=None):
    """Devolve [(score, job)] do maior para o menor. score = 100 x similaridade de cosseno + bônus.
    `codificar(textos) -> vetores normalizados` pode ser trocado nos testes."""
    if not jobs:
        return []
    if codificar is None:
        codificar = lambda textos: modelo().encode(textos, normalize_embeddings=True, batch_size=32,
                                                  show_progress_bar=False)
    vetores = codificar([texto_perfil(perfil_md, prefs)] + [texto_vaga(j) for j in jobs])
    perfil, vagas = vetores[0], vetores[1:]
    res = []
    for j, v in zip(jobs, vagas):
        sim = float(sum(a * b for a, b in zip(perfil, v)))
        res.append((round(100 * sim + bonus(j, prefs), 1), j))
    return sorted(res, key=lambda x: x[0], reverse=True)
