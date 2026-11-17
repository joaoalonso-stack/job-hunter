"""Filtro duro do pipeline diário, guiado pelo config/preferencias.yaml. Devolve (aceita, motivo).
O "incluir" do YAML não é obrigatório (descartaria "Economista", "Middle Office"...): vira bônus no ranking."""
import re

from pipeline import filtro_legado
from sources.base import norm

# O YAML lista os termos em português; vagas em inglês usam estes equivalentes.
SINONIMOS = {
    "senior": ["senior", "sr"], "pleno": ["pleno", "mid-level", "mid level", "pl"], "especialista": ["specialist"],
    "coordenador": ["coordinator", "coordenacao"], "gerente": ["manager"], "head": ["head"],
    "diretor": ["director", "diretoria"], "estagio": ["estagiari", "intern", "internship"],
}
# Áreas de interesse do usuário (macro/research, investimentos, asset/fundos, crédito/risco, trading/commodities,
# consultoria, inteligência de mercado, FP&A, setor público, trainee, back/middle office), além dos termos do YAML.
AREAS_RE = re.compile(
    r"econom|macro|research|investiment|investment|\basset|fundos?\b|\bfunds?\b|credito|credit|risco|\brisk|"
    r"trading|trader|commodit|\bmercado|\bmarkets?\b|fp&a|planejamento financeiro|tesouraria|treasury|liquidacao|"
    r"custodia|precifica|pricing de ativos|passivo|regulat|middle|back ?office|backoffice|trainee|"
    r"programa de formacao|cambio|renda fixa|fixed income|derivativ|wealth|portfolio|\bfidc|cotas|"
    r"inteligencia de mercado|estudos economicos|consultoria economica|politica (monetaria|fiscal)|"
    r"\boperacoes financeiras|controle de fundos|gestao de recursos"
)
SENIORIDADE_FORA = {"estágio", "aprendiz", "banco de talentos", "docente"}


def _padrao_excluir(termos):
    pals = set()
    for t in termos:
        n = norm(t)
        pals.add(n)
        pals.update(SINONIMOS.get(n, []))
    # prefixo com fronteira de palavra: "coordenador" pega "coordenador(a)"; "sr" e "pl" só como palavra inteira
    partes = [rf"\b{re.escape(p)}\b" if len(p) <= 3 else rf"\b{re.escape(p)}" for p in sorted(pals)]
    return re.compile("|".join(partes))


def _padroes_locais(prefs):
    pads = []
    for loc in prefs["locais"]:
        n = norm(loc["nome"])
        pads.append(n)
        if n == "rio de janeiro":
            pads += ["niteroi", r"^rj$"]
        if n == "sao paulo":
            pads.append(r"^sp$")
    return re.compile("|".join(pads))


class Filtro:
    def __init__(self, prefs):
        self.prefs = prefs
        self.excluir = _padrao_excluir(prefs["excluir"])
        self.locais = _padroes_locais(prefs)
        self.termos = [norm(t) for t in prefs["termos"]]
        self.remoto_ok = prefs["modalidade"].get("remoto_qualquer_lugar_do_brasil", True)
        self.aceitas = set(prefs["modalidade"]["aceitas"])

    def local_ok(self, job):
        loc = norm(job.local).strip()
        if job.modalidade == "remoto" or "remot" in loc or "home office" in loc:
            return self.remoto_ok and "remoto" in self.aceitas, "remoto"
        if job.modalidade and job.modalidade not in self.aceitas:
            return False, f"modalidade {job.modalidade} não aceita"
        if self.locais.search(loc):
            return True, ""
        if loc in ("", "brasil", "brazil", "nacional"):
            return True, "local indefinido (a /triagem confere)"
        return False, f"presencial/híbrido fora de RJ/SP ({job.local})"

    def relevante(self, job):
        t = norm(job.titulo)
        return (filtro_legado.classifica(job) is not None or any(term in t for term in self.termos)
                or bool(AREAS_RE.search(t)))

    def avaliar(self, job):
        publico = job.extra.get("cat") == "PUBLICO"
        t = norm(job.titulo)
        if not publico and self.excluir.search(t):
            return False, "senioridade/área excluída no título"
        if job.senioridade in SENIORIDADE_FORA:
            return False, f"tipo de vaga: {job.senioridade}"
        if publico:
            return True, "setor público"
        ok, motivo = self.local_ok(job)
        if not ok:
            return False, motivo
        if not self.relevante(job):
            return False, "fora das áreas de interesse"
        return True, motivo
