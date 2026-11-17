"""Gera relatorios/vagas.html: um arquivo único e offline (sem CDN) com abas Hoje / Ativas / Arquivadas, busca,
filtros, ordenação, detalhes ao clicar na linha e status salvo no navegador (localStorage), exportável em JSON
para o script importar no SQLite."""
import json
from datetime import datetime

TRILHAS = {"macro_research": "Macro/Research", "asset_fundos": "Asset/Fundos",
           "trading_commodities": "Trading/Commodities", "backoffice_middle": "Back/Middle office",
           "credito_risco": "Crédito/Risco", "consultoria": "Consultoria", "trainee_generalista": "Trainee",
           "inteligencia_mercado_fpa": "Intel. mercado/FP&A", "outro": "Outro"}


def gerar(linhas, prefs, destino, hoje):
    meta = {"hoje": hoje, "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "destaque": prefs["limiares"]["destaque"], "urgente": prefs["limiares"]["urgente"],
            "prazo_dias": prefs["limiares"]["prazo_dias"], "trilhas": TRILHAS,
            "pesos": prefs["trilhas"]}
    dados = json.dumps({"meta": meta, "vagas": linhas}, ensure_ascii=False).replace("</", "<\\/")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(MODELO.replace("__DADOS__", dados), "utf-8")
    return destino


MODELO = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vagas do João</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--tx:#1b1f24;--mut:#5b6470;--lin:#e3e6ea;--pri:#1f5fbf;--pri-tx:#fff;
--ok:#137a3a;--ok-bg:#e3f4ea;--bom:#3a7d1e;--bom-bg:#eef7e6;--med:#8a5a00;--med-bg:#fdf3dc;--bx:#6b7280;--bx-bg:#eef0f3;
--rd:#b42318;--rd-bg:#fde8e7;--sel:#eef4ff}
@media (prefers-color-scheme:dark){:root{--bg:#111418;--card:#1a1e24;--tx:#e8eaed;--mut:#9aa3ae;--lin:#2c323a;
--pri:#6aa0ff;--pri-tx:#0d1117;--ok:#5fd38d;--ok-bg:#163524;--bom:#9bd36a;--bom-bg:#22301a;--med:#f0c060;--med-bg:#3a2f12;
--bx:#a3acb8;--bx-bg:#262b33;--rd:#ff8a80;--rd-bg:#3d1f1d;--sel:#1d2633}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:20px 24px 8px;max-width:1500px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--mut);font-size:13px}
main{max-width:1500px;margin:0 auto;padding:0 24px 40px}
.abas{display:flex;gap:6px;margin:14px 0 10px;flex-wrap:wrap}
.aba{border:1px solid var(--lin);background:var(--card);color:var(--tx);padding:7px 14px;border-radius:8px;cursor:pointer;font-size:14px}
.aba[aria-selected=true]{background:var(--pri);color:var(--pri-tx);border-color:var(--pri);font-weight:600}
.ctl{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
.ctl input,.ctl select,.ctl button{font:inherit;padding:7px 10px;border:1px solid var(--lin);border-radius:8px;background:var(--card);color:var(--tx)}
.ctl input[type=search]{min-width:260px;flex:1}
.ctl button{cursor:pointer}
.ctl .dir{margin-left:auto}
.tabwrap{background:var(--card);border:1px solid var(--lin);border-radius:10px;overflow-x:auto}
table{border-collapse:collapse;width:100%;min-width:1100px}
th,td{padding:9px 10px;text-align:left;border-bottom:1px solid var(--lin);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:var(--mut);cursor:pointer;user-select:none;white-space:nowrap;position:sticky;top:0;background:var(--card)}
th.ord::after{content:" ↓"}th.ord.asc::after{content:" ↑"}
tr.l{cursor:pointer}tr.l:hover{background:var(--sel)}
.nota{display:inline-block;min-width:38px;text-align:center;font-weight:700;padding:2px 6px;border-radius:6px}
.n-top{color:var(--ok);background:var(--ok-bg)}.n-bom{color:var(--bom);background:var(--bom-bg)}
.n-med{color:var(--med);background:var(--med-bg)}.n-bx{color:var(--bx);background:var(--bx-bg)}
.pre{display:block;font-size:11px;color:var(--mut);font-weight:400}
.cargo{font-weight:600}.emp{color:var(--mut)}
.flag{color:var(--rd);font-size:12px;margin-left:6px;white-space:nowrap}
.prazo-urg{color:var(--rd);font-weight:700}.prazo-venc{color:var(--rd);text-decoration:line-through}
.tag{font-size:12px;padding:1px 7px;border-radius:999px;background:var(--bx-bg);color:var(--tx);white-space:nowrap}
a.cand{display:inline-block;background:var(--pri);color:var(--pri-tx);text-decoration:none;padding:5px 10px;border-radius:7px;font-weight:600;white-space:nowrap}
select.st{font:inherit;padding:4px 6px;border:1px solid var(--lin);border-radius:6px;background:var(--card);color:var(--tx)}
tr.det td{background:var(--bg);padding:14px 18px}
.det-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
.det-grid h4{margin:0 0 4px;font-size:12px;text-transform:uppercase;color:var(--mut);letter-spacing:.03em}
.det-grid ul{margin:0;padding-left:18px}.red li{color:var(--rd)}
.desc{white-space:pre-wrap;color:var(--mut);font-size:13px;margin-top:10px}
.vazio{padding:40px;text-align:center;color:var(--mut)}
.leg{color:var(--mut);font-size:12px;margin-top:10px}
</style>
</head>
<body>
<header>
  <h1>Vagas do João</h1>
  <div class="sub" id="sub"></div>
</header>
<main>
  <div class="abas" role="tablist" id="abas"></div>
  <div class="ctl">
    <input type="search" id="busca" placeholder="Buscar cargo, empresa, local, motivo…" aria-label="Buscar">
    <select id="f-trilha" aria-label="Trilha"></select>
    <select id="f-modalidade" aria-label="Modalidade"></select>
    <select id="f-fonte" aria-label="Fonte"></select>
    <select id="f-status" aria-label="Status"></select>
    <label class="sub"><input type="checkbox" id="f-nota"> só com nota</label>
    <button class="dir" id="exportar" title="Baixa um arquivo com os status que você marcou, para o sistema guardar no banco">Exportar status (JSON)</button>
  </div>
  <div class="tabwrap"><table>
    <thead><tr id="cab"></tr></thead>
    <tbody id="corpo"></tbody>
  </table></div>
  <div class="leg" id="leg"></div>
</main>
<script id="dados" type="application/json">__DADOS__</script>
<script>
(function(){
const D = JSON.parse(document.getElementById('dados').textContent);
const M = D.meta, V = D.vagas;
const CHAVE = 'jobhunter_status';
let local = {};
try { local = JSON.parse(localStorage.getItem(CHAVE) || '{}'); } catch(e) { local = {}; }
function salvarLocal(){ try { localStorage.setItem(CHAVE, JSON.stringify(local)); } catch(e) {} }
function status(v){ const l = local[v.id]; return (l && (!v.status_em || l.quando > v.status_em)) ? l.status : v.status; }

const COLS = [
  ['nota','Nota'],['cargo','Cargo / empresa'],['trilha','Trilha'],['local','Local'],['modalidade','Modalidade'],
  ['fonte','Fonte'],['prazo','Prazo'],['status','Status'],['link','']];
const MOD = {presencial:'Presencial', hibrido:'Híbrido', remoto:'Remoto', '':'—'};
let aba = 'hoje', ord = {col:'nota', asc:false}, abertos = new Set();
const $ = id => document.getElementById(id);
const VAZIO = '__vazio__';
const bate = (filtro, valor) => !filtro || (filtro === VAZIO ? !valor : valor === filtro);
// horário local no mesmo formato do banco (AAAA-MM-DDTHH:MM:SS), para comparar qual edição é mais recente
const agoraLocal = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 19); };
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function naAba(v, a){
  const st = status(v);
  if (a === 'hoje') return v.hoje && v.aba === 'ativa';
  if (a === 'arquivada') return v.aba === 'arquivada' || st === 'descartei';
  return v.aba === 'ativa' && st !== 'descartei';
}
function cls(n){ if (n == null) return 'n-bx'; if (n >= M.urgente) return 'n-top'; if (n >= M.destaque) return 'n-bom'; if (n >= 50) return 'n-med'; return 'n-bx'; }

function opcoes(sel, rotulo, valores, nomes){
  sel.innerHTML = '<option value="">' + rotulo + ': todas</option>' +
    valores.map(x => '<option value="' + (x === '' ? VAZIO : esc(x)) + '">' + esc((nomes && nomes[x]) || x || '—') + '</option>').join('');
}
function montarFiltros(){
  const uniq = k => [...new Set(V.map(v => v[k]))].sort();
  opcoes($('f-trilha'), 'Trilha', uniq('trilha'), Object.assign({'':'sem triagem'}, M.trilhas));
  opcoes($('f-modalidade'), 'Modalidade', uniq('modalidade'), MOD);
  opcoes($('f-fonte'), 'Fonte', uniq('fonte'));
  opcoes($('f-status'), 'Status', ['', 'interessado', 'apliquei', 'descartei'], {'':'sem status'});
}
function filtradas(){
  const q = $('busca').value.trim().toLowerCase();
  const f = {trilha:$('f-trilha').value, modalidade:$('f-modalidade').value, fonte:$('f-fonte').value, status:$('f-status').value};
  return V.filter(v => naAba(v, aba)
    && (!q || [v.cargo, v.empresa, v.local, v.encaixe, v.fonte, (v.red_flags||[]).join(' ')].join(' ').toLowerCase().includes(q))
    && bate(f.trilha, v.trilha) && bate(f.modalidade, v.modalidade) && bate(f.fonte, v.fonte) && bate(f.status, status(v))
    && (!$('f-nota').checked || v.nota != null));
}
function valorOrd(v, c){
  if (c === 'nota') return v.nota != null ? v.nota : (v.score_pre != null ? v.score_pre / 1000 - 1 : -2);
  if (c === 'prazo') return v.prazo || '9999';
  if (c === 'status') return status(v);
  if (c === 'cargo') return (v.cargo || '').toLowerCase();
  return String(v[c] || '').toLowerCase();
}
function ordenar(lista){
  const {col, asc} = ord;
  return lista.sort((a, b) => { const x = valorOrd(a, col), y = valorOrd(b, col); return (x < y ? -1 : x > y ? 1 : 0) * (asc ? 1 : -1); });
}
function celNota(v){
  if (v.nota == null) return '<span class="nota n-bx">—</span>' + (v.score_pre != null ? '<span class="pre">pré ' + Math.round(v.score_pre) + '</span>' : '');
  return '<span class="nota ' + cls(v.nota) + '">' + v.nota + '</span>';
}
function celPrazo(v){
  if (!v.prazo) return '<span class="emp">—</span>';
  const d = v.prazo.split('-').reverse().join('/');
  if (v.dias_prazo < 0) return '<span class="prazo-venc">' + d + '</span>';
  if (v.urgente_prazo) return '<span class="prazo-urg">' + d + ' (' + (v.dias_prazo === 0 ? 'hoje' : v.dias_prazo + 'd') + ')</span>';
  return d;
}
function linha(v){
  const st = status(v), rf = (v.red_flags || []).length;
  return '<tr class="l" data-id="' + esc(v.id) + '">' +
    '<td>' + celNota(v) + '</td>' +
    '<td><span class="cargo">' + esc(v.cargo) + '</span>' + (rf ? '<span class="flag">⚠ ' + rf + '</span>' : '') +
      (v.aberta === 0 ? '<span class="flag">encerrada</span>' : '') + '<br><span class="emp">' + esc(v.empresa) + '</span></td>' +
    '<td>' + (v.trilha ? '<span class="tag">' + esc(M.trilhas[v.trilha] || v.trilha) + '</span>' : '<span class="emp">—</span>') + '</td>' +
    '<td>' + esc(v.local) + '</td><td>' + esc(MOD[v.modalidade] || v.modalidade) + '</td>' +
    '<td>' + esc(v.fonte) + '</td><td>' + celPrazo(v) + '</td>' +
    '<td><select class="st" data-id="' + esc(v.id) + '" aria-label="Status">' +
      ['', 'interessado', 'apliquei', 'descartei'].map(s => '<option value="' + s + '"' + (s === st ? ' selected' : '') + '>' + (s || '—') + '</option>').join('') +
    '</select></td>' +
    '<td><a class="cand" href="' + esc(v.url) + '" target="_blank" rel="noopener">Candidatar</a></td></tr>' +
    (abertos.has(v.id) ? detalhe(v) : '');
}
function situacao(v){
  if (v.aberta === 0) return '<b class="flag" style="margin:0">Encerrada</b> — ' + esc(v.situacao) + '<br>';
  if (v.aberta === 1) return '<b style="color:var(--ok)">✓ Aberta</b> — ' + esc(v.situacao) + (v.verificada_em ? ' (conferida em ' + esc(v.verificada_em.split('-').reverse().join('/')) + ')' : '') + '<br>';
  return '<span class="emp">Ainda não conferida se está aberta.</span><br>';
}
function lista(t, itens, classe){ return itens && itens.length ? '<h4>' + t + '</h4><ul class="' + (classe||'') + '">' + itens.map(x => '<li>' + esc(x) + '</li>').join('') + '</ul>' : ''; }
function detalhe(v){
  const peso = v.trilha && M.pesos[v.trilha] != null ? ' (base ' + v.nota_base + ' × peso ' + M.pesos[v.trilha] + ')' : '';
  return '<tr class="det"><td colspan="' + COLS.length + '"><div class="det-grid">' +
    '<div><h4>Por que encaixa' + esc(peso) + '</h4>' + (v.encaixe ? esc(v.encaixe) : '<span class="emp">Ainda sem triagem.</span>') + '</div>' +
    '<div>' + lista('O que falta', v.falta) + lista('Red flags', v.red_flags, 'red') + '</div>' +
    '<div><h4>Detalhes</h4>' + situacao(v) + 'Publicada: ' + esc(v.publicada || '—') + ' · vista em ' + esc(v.visto_em || '—') +
      (v.senioridade ? '<br>Tipo: ' + esc(v.senioridade) : '') + (v.motivo_filtro ? '<br>Filtro: ' + esc(v.motivo_filtro) : '') + '</div>' +
    '</div>' + (v.descricao ? '<div class="desc">' + esc(v.descricao) + (v.descricao.length >= 900 ? '…' : '') + '</div>' : '') + '</td></tr>';
}
function render(){
  const conta = a => V.filter(v => naAba(v, a)).length;
  $('abas').innerHTML = [['hoje','Hoje'],['ativa','Ativas'],['arquivada','Arquivadas']].map(([a, n]) =>
    '<button class="aba" role="tab" aria-selected="' + (a === aba) + '" data-aba="' + a + '">' + n + ' (' + conta(a) + ')</button>').join('');
  $('cab').innerHTML = COLS.map(([c, n]) => '<th data-col="' + c + '" class="' + (ord.col === c ? 'ord' + (ord.asc ? ' asc' : '') : '') + '">' + n + '</th>').join('');
  const l = ordenar(filtradas());
  $('corpo').innerHTML = l.length ? l.map(linha).join('') :
    '<tr><td colspan="' + COLS.length + '" class="vazio">' + (aba === 'hoje' ? 'Nenhuma vaga nova hoje (ou a rodada das 8h ainda não aconteceu).' : 'Nenhuma vaga com esses filtros.') + '</td></tr>';
  $('leg').textContent = l.length + ' vagas nesta visão. Nota: ≥' + M.urgente + ' excelente · ≥' + M.destaque + ' destaque · "pré" = nota prévia por similaridade, antes da triagem. Clique numa linha para ver os motivos.';
}
$('sub').textContent = 'Atualizado em ' + M.gerado_em + ' · ' + V.length + ' vagas no total · status salvo neste navegador';
montarFiltros(); render();
$('abas').addEventListener('click', e => { const b = e.target.closest('[data-aba]'); if (b) { aba = b.dataset.aba; render(); } });
$('cab').addEventListener('click', e => { const th = e.target.closest('th[data-col]'); if (!th || th.dataset.col === 'link') return;
  const c = th.dataset.col; ord = {col:c, asc: ord.col === c ? !ord.asc : (c !== 'nota')}; render(); });
['busca','f-trilha','f-modalidade','f-fonte','f-status','f-nota'].forEach(id => $(id).addEventListener('input', render));
$('corpo').addEventListener('click', e => {
  if (e.target.closest('a,select')) return;
  const tr = e.target.closest('tr.l'); if (!tr) return;
  const id = tr.dataset.id; abertos.has(id) ? abertos.delete(id) : abertos.add(id); render();
});
$('corpo').addEventListener('change', e => {
  const s = e.target.closest('select.st'); if (!s) return;
  local[s.dataset.id] = {status: s.value, quando: agoraLocal()}; salvarLocal(); render();
});
$('exportar').addEventListener('click', () => {
  const itens = Object.entries(local).map(([id, x]) => ({id, status: x.status, quando: x.quando}));
  const blob = new Blob([JSON.stringify(itens, null, 1)], {type: 'application/json'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'status_vagas_' + agoraLocal().slice(0, 10) + '.json'; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});
})();
</script>
</body>
</html>
"""
