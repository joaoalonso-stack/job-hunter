import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(RAIZ))


@pytest.fixture
def fixture_txt():
    return lambda nome: (FIXTURES / nome).read_text("utf-8", errors="replace")


@pytest.fixture
def conn(tmp_path):
    import db
    c = db.conectar(tmp_path / "teste.db")
    yield c
    c.close()
