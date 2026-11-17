"""Schema comum das vagas e utilitários de rede usados por todos os coletores."""
import gzip
import re
import time
import unicodedata
import urllib.request
from dataclasses import asdict, dataclass, field

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


@dataclass
class Job:
    id: str            # único entre fontes, ex.: "gupy:123"; no LinkedIn é o número puro (compatível com o legado)
    fonte: str
    titulo: str
    empresa: str = ""
    local: str = ""
    modalidade: str = ""   # presencial | hibrido | remoto | "" (desconhecida)
    senioridade: str = ""
    publicada: str = ""    # AAAA-MM-DD quando a fonte informa
    prazo: str = ""        # AAAA-MM-DD quando a fonte informa
    url: str = ""
    descricao: str = ""
    extra: dict = field(default_factory=dict)  # dados específicos da fonte (ex.: cat do filtro legado)

    def to_dict(self):
        return asdict(self)

    def chave_legada(self):
        """Chave título + empresa usada pelo monitor antigo para não repetir alertas entre portais."""
        return "k:" + alnum(self.titulo) + "|" + alnum(self.empresa)[:12]


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def alnum(s):
    return re.sub(r"[^a-z0-9]", "", norm(s))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", norm(s)).strip("-")


class Bloqueado(Exception):
    pass


def decodificar(dados):
    """Alguns sites (ex.: Ipea) mandam gzip mesmo sem o cliente pedir; detecta pela assinatura do arquivo."""
    if dados[:2] == b"\x1f\x8b":
        dados = gzip.decompress(dados)
    return dados.decode("utf-8", "replace")


def fetch_status(url):
    """Uma tentativa; devolve (código HTTP, texto). Código 0 = erro de rede/bloqueio sem resposta."""
    import urllib.error
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, decodificar(r.read())
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def fetch(url, tentativas=2, espera=60):
    for _ in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return decodificar(r.read())
        except Exception:
            time.sleep(espera)
    raise Bloqueado(url)
