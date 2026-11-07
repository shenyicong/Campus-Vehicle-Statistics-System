# 网页仪表盘: Flask + chart.js，读取报表 CSV 实时展示各车型进出统计
# 并提供「场地车位设置」：本地人员按场地录入分区 / 适用车型 / 实有车位数量。
import os
import csv

import config
import parking_plan

try:
    from flask import Flask, jsonify, request, Response
except ImportError:
    Flask = None
    request = jsonify = Response = None


class _NoApp:
    """Flask 未安装时的占位对象，保证模块可被导入 / 被其他脚本安全引用"""
    def route(self, *args, **kwargs):
        return lambda f: f


app = Flask(__name__) if Flask else _NoApp()


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>校园车辆智能统计</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
 body{font-family:system-ui,'Microsoft YaHei',sans-serif;margin:0;background:#f5f6f8;color:#222}
 header{background:#185FA5;color:#fff;padding:16px 24px;font-size:18px}
 .wrap{max-width:1000px;margin:20px auto;padding:0 16px 40px}
 .cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}
 .card{flex:1;min-width:140px;background:#fff;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
 .card .n{font-size:26px;font-weight:600;color:#185FA5}
 .card .l{font-size:13px;color:#666;margin-top:4px}
 table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden}
 th,td{padding:10px 12px;border-bottom:1px solid #eee;font-size:13px;text-align:center}
 th{background:#f0f4f8;color:#444}
 .chart-box{background:#fff;border-radius:12px;padding:16px;margin-top:20px}
 h3{margin:26px 0 10px;font-size:16px}
 h3 small{font-weight:400;color:#888;font-size:12px}
 .panel{background:#fff;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
 .form-row{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:12px;font-size:13px}
 .hint{font-size:12px;color:#888}
 input[type=text],input[type=number]{border:1px solid #d0d7de;border-radius:6px;padding:6px 8px;font-size:13px}
 #zoneForm input.z-name{width:110px} #zoneForm input.z-slots{width:80px} #zoneForm input.z-note{width:160px}
 .chk label{margin-right:8px;white-space:nowrap;font-size:13px}
 .chk{text-align:left}
 button{border:1px solid #d0d7de;background:#fff;border-radius:6px;padding:7px 14px;cursor:pointer;font-size:13px}
 button.primary{background:#185FA5;color:#fff;border-color:#185FA5}
 button:hover{opacity:.85}
 .btns{display:flex;gap:10px;align-items:center;margin-top:12px;flex-wrap:wrap}
 .msg{font-size:13px} .msg.ok{color:#137333} .msg.err{color:#c5221f} .msg.info{color:#666}
 .badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px}
 .badge.ok{background:#e6f4ea;color:#137333}
 .badge.warn{background:#fef7e0;color:#b06000}
 .badge.bad{background:#fce8e6;color:#c5221f}
 code{background:#f0f4f8;padding:1px 5px;border-radius:4px}
</style></head>
<body>
<header>校园车辆智能统计系统 · 校门 / 停车场进出看板</header>
<div class="wrap">
  <div class="cards" id="cards"></div>
  <div class="chart-box"><canvas id="bar"></canvas></div>

  <h3>场地车位设置 <small>由本地人员按实际场地录入；分区数量、适用车型、车位数量均可改</small></h3>
  <div class="panel">
    <div class="form-row">
      <label>场地名称 <input type="text" id="siteName" style="width:140px"></label>
      <span class="hint">配置文件：<code id="zonePath">-</code></span>
    </div>
    <table id="zoneForm">
      <thead><tr><th style="width:130px">分区名称</th><th>适用车型（可多选）</th>
        <th style="width:100px">实有车位</th><th style="width:180px">备注</th><th style="width:70px">操作</th></tr></thead>
      <tbody id="zoneRows"></tbody>
    </table>
    <div class="btns">
      <button id="addZone">+ 添加分区</button>
      <button id="saveZones" class="primary">保存场地配置</button>
      <button id="resetZones">放弃修改</button>
      <span id="zoneMsg" class="msg info"></span>
    </div>
    <div class="hint" style="margin-top:8px">
      示例：A 区停轿车 / SUV 共 360 位，B 区停客车 / 货车共 180 位。
      同一车型被多个分区服务时需求会重复计入，未被覆盖的车型不参与供需对比，系统都会给出提示。
    </div>
  </div>

  <h3>车位供需对比 <small>场地实有车位（供给侧） vs 通行流量推算需求（需求侧）</small></h3>
  <div class="cards" id="zoneCards"></div>
  <table id="zoneTbl"><thead></thead><tbody></tbody></table>
  <div id="planHints" class="hint" style="margin-top:8px;line-height:1.8"></div>

  <h3>车位配比建议 <small>需求侧参考口径，由分车型进出量推导</small></h3>
  <div class="cards" id="planCards"></div>
  <table id="planTbl"><thead></thead><tbody></tbody></table>

  <h3 style="margin-top:24px">每小时明细</h3>
  <table id="tbl"><thead></thead><tbody></tbody></table>
</div>
<script>
let chart=null, CLS=['sedan','suv','truck','bus'], CN={sedan:'轿车',suv:'SUV',truck:'货车',bus:'客车'};

function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function setMsg(lines, kind){
  const el=document.getElementById('zoneMsg');
  el.className='msg '+(kind||'info');
  el.innerHTML=(lines||[]).map(esc).join(' &nbsp;·&nbsp; ');
}
function badge(s){
  const k = s==='供给充足' ? 'ok' : (s.indexOf('不足')>=0 || s.indexOf('超负荷')>=0 ? 'bad' : 'warn');
  return `<span class="badge ${k}">${esc(s)}</span>`;
}

async function load(){
  const r = await fetch('/api/stats'); const d = await r.json();
  CLS = d.classes; CN = d.class_cn;
  let te=0, tx=0;
  CLS.forEach(c=>{te+=d.total.enter[c]; tx+=d.total.exit[c];});
  document.getElementById('cards').innerHTML =
    `<div class='card'><div class='n'>${te}</div><div class='l'>今日进入总数</div></div>`+
    `<div class='card'><div class='n'>${tx}</div><div class='l'>今日驶出总数</div></div>`+
    CLS.map(c=>`<div class='card'><div class='n'>${d.total.enter[c]+d.total.exit[c]}</div><div class='l'>${CN[c]} 进出</div></div>`).join('');
  const labels = CLS.map(c=>CN[c]);
  const cfg={type:'bar',data:{labels,datasets:[
    {label:'进入',data:CLS.map(c=>d.total.enter[c]),backgroundColor:'#185FA5'},
    {label:'驶出',data:CLS.map(c=>d.total.exit[c]),backgroundColor:'#E24B4A'}]},
    options:{responsive:true,plugins:{title:{display:true,text:'各车型进出数量'}}}};
  // 定时刷新时复用同一个 Chart 实例，避免 "Canvas is already in use"；
  // 离线 / CDN 不可用时跳过图表，不影响车位设置与供需表格
  if(typeof Chart!=='undefined'){
    if(chart){ chart.data=cfg.data; chart.update(); }
    else { chart=new Chart(document.getElementById('bar'),cfg); }
  }
  const rows = d.hourly;
  if(rows.length){ const cols=Object.keys(rows[0]);
    document.querySelector('#tbl thead').innerHTML='<tr>'+cols.map(c=>`<th>${c}</th>`).join('')+'</tr>';
    document.querySelector('#tbl tbody').innerHTML=rows.map(r=>'<tr>'+cols.map(c=>`<td>${r[c]}</td>`).join('')+'</tr>').join('');
  }
}

function collectZones(){
  return [...document.querySelectorAll('#zoneRows tr[data-i]')].map((tr,idx)=>({
    id:tr.dataset.id || 'Z'+(idx+1),
    name:tr.querySelector('.z-name').value.trim(),
    classes:[...tr.querySelectorAll('.z-cls:checked')].map(c=>c.value),
    slots:parseInt(tr.querySelector('.z-slots').value||'0',10),
    note:tr.querySelector('.z-note').value.trim()
  }));
}
function renderZoneForm(zones){
  const rows=(zones||[]).map((z,i)=>`<tr data-i="${i}" data-id="${esc(z.id||('Z'+(i+1)))}">
      <td><input type="text" class="z-name" value="${esc(z.name)}"></td>
      <td class="chk">${CLS.map(c=>`<label><input type="checkbox" class="z-cls" value="${c}" ${(z.classes||[]).indexOf(c)>=0?'checked':''}>${esc(CN[c]||c)}</label>`).join('')}</td>
      <td><input type="number" class="z-slots" min="0" step="1" value="${Number(z.slots)||0}"></td>
      <td><input type="text" class="z-note" value="${esc(z.note||'')}" placeholder="选填"></td>
      <td><button class="del" data-i="${i}">删除</button></td></tr>`).join('');
  document.getElementById('zoneRows').innerHTML = rows ||
    '<tr><td colspan="5" class="hint">暂无分区，点「+ 添加分区」新增</td></tr>';
  document.querySelectorAll('#zoneRows .del').forEach(b=>b.onclick=()=>{
    const cur=collectZones(); cur.splice(Number(b.dataset.i),1); renderZoneForm(cur);
    setMsg(['已删除分区，记得点「保存场地配置」'],'info');
  });
}
async function loadZones(msg){
  const r = await fetch('/api/parking_zones'); const d = await r.json();
  document.getElementById('siteName').value = d.site_name||'';
  document.getElementById('zonePath').textContent = d.source || '内置示例（保存后生成本地配置）';
  renderZoneForm(d.zones||[]);
  setMsg(msg || ((d.warnings||[]).length ? d.warnings : ['场地配置已加载']), msg?'ok':'info');
}

async function loadPlan(){
  const r = await fetch('/api/parking_plan'); const p = await r.json();
  const g=p.groups, ph=p.peak_hour, z=p.zones||{items:[],supply_total:0,required_total:0,gap_total:0,saturation_pct:0};
  document.getElementById('zoneCards').innerHTML =
    `<div class='card'><div class='n'>${z.supply_total}</div><div class='l'>实有车位合计（${esc(z.site_name||'场地')}）</div></div>`+
    `<div class='card'><div class='n'>${z.required_total}</div><div class='l'>需求泊位合计</div></div>`+
    `<div class='card'><div class='n'>${z.gap_total>=0?'+':''}${z.gap_total}</div><div class='l'>总体余量 / 缺口</div></div>`+
    `<div class='card'><div class='n'>${z.saturation_pct}%</div><div class='l'>峰值饱和度</div></div>`;
  const zc=['分区','适用车型','实有车位','峰值在场','需求泊位(含余量)','余量 / 缺口','峰值饱和度','需求占用率','状态'];
  const zr=(z.items||[]).map(i=>[
    esc(i.name), (i.classes_cn||i.classes||[]).map(esc).join(' / '),
    `<b>${i.supply_slots}</b>`, i.peak_occupancy, i.required_slots,
    `<b>${i.gap_slots>=0?'+':''}${i.gap_slots}</b>`,
    i.saturation_pct+'%', i.utilization_pct+'%', badge(i.status)]);
  document.querySelector('#zoneTbl thead').innerHTML='<tr>'+zc.map(c=>`<th>${c}</th>`).join('')+'</tr>';
  document.querySelector('#zoneTbl tbody').innerHTML=zr.map(r=>'<tr>'+r.map(c=>`<td>${c}</td>`).join('')+'</tr>').join('') ||
    '<tr><td colspan="9" class="hint">尚未配置分区</td></tr>';
  const hints=z.warnings||[];
  document.getElementById('planHints').innerHTML = hints.length
    ? '<b>规划提示：</b>'+hints.map(esc).join(' &nbsp;·&nbsp; ') : '';
  document.getElementById('planCards').innerHTML =
    `<div class='card'><div class='n'>${g.small.recommended_slots}</div><div class='l'>建议小车位（轿车 / SUV）</div></div>`+
    `<div class='card'><div class='n'>${g.large.recommended_slots}</div><div class='l'>建议大车位（货车 / 客车）</div></div>`+
    `<div class='card'><div class='n'>${p.total_area_sqm}</div><div class='l'>规划用地约 ㎡</div></div>`+
    `<div class='card'><div class='n'>${ph?ph.throughput:'-'}</div><div class='l'>高峰小时通行辆次 ${ph?ph.period:''}</div></div>`;
  const cols=['分区','对应车型','峰值在场数','建议泊位数','单车位面积(㎡)','含通道用地(㎡)','占比'];
  const rows=[
    ['小车位','轿车 / SUV',g.small.peak_occupancy,g.small.recommended_slots,g.small.slot_area_sqm,g.small.area_with_aisle_sqm,g.small.share_pct+'%'],
    ['大车位','货车 / 客车',g.large.peak_occupancy,g.large.recommended_slots,g.large.slot_area_sqm,g.large.area_with_aisle_sqm,g.large.share_pct+'%']
  ];
  document.querySelector('#planTbl thead').innerHTML='<tr>'+cols.map(c=>`<th>${c}</th>`).join('')+'</tr>';
  document.querySelector('#planTbl tbody').innerHTML=rows.map(r=>'<tr>'+r.map(c=>`<td>${c}</td>`).join('')+'</tr>').join('');
}

document.getElementById('addZone').onclick=()=>{
  const cur=collectZones();
  cur.push({id:'Z'+Date.now().toString().slice(-6),
            name:'新分区 '+(cur.length+1),classes:[CLS[0]],slots:0,note:''});
  renderZoneForm(cur); setMsg(['已新增分区，记得点「保存场地配置」'],'info');
};
document.getElementById('resetZones').onclick=()=>loadZones(['已放弃修改，还原为上次保存的配置']);
document.getElementById('saveZones').onclick=async()=>{
  const payload={site_name:document.getElementById('siteName').value.trim(),zones:collectZones()};
  const r=await fetch('/api/parking_zones',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const d=await r.json();
  if(!d.ok){ setMsg(['保存失败：'+(d.error||'未知错误')],'err'); return; }
  const msg=['已保存场地配置'].concat(d.warnings||[]);
  await loadZones(msg);
  await loadPlan();
};

// 自动刷新只更新统计数据，不重建表单，避免打断本地人员正在进行的编辑
async function init(){ await load(); await loadZones(); await loadPlan();
  setInterval(()=>{load();loadPlan();},5000); }
init();
</script></body></html>"""


@app.route("/")
def index():
    return Response(HTML, mimetype="text/html")


@app.route("/api/stats")
def api_stats():
    hourly = load_csv(config.HOURLY_CSV)
    daily = load_csv(config.DAILY_CSV)
    total = {"enter": {c: 0 for c in config.CLASSES}, "exit": {c: 0 for c in config.CLASSES}}
    for row in daily:
        for c in config.CLASSES:
            total["enter"][c] += int(row.get(f"enter_{c}", 0) or 0)
            total["exit"][c] += int(row.get(f"exit_{c}", 0) or 0)
    return jsonify({"classes": config.CLASSES, "class_cn": config.CLASS_CN,
                    "total": total, "hourly": hourly, "daily": daily})


@app.route("/api/parking_zones", methods=["GET", "POST"])
def api_parking_zones():
    """GET 读取本地场地配置；POST 由本地人员保存分区 / 适用车型 / 车位数量"""
    if request.method == "GET":
        return jsonify(parking_plan.load_zones(config.PARKING_ZONES_JSON))
    data = request.get_json(silent=True) or {}
    try:
        cfg, warnings = parking_plan.validate_zones(data, config.CLASSES)
        parking_plan.save_zones(cfg, config.PARKING_ZONES_JSON, config.CLASSES)
        return jsonify({"ok": True, "zones": cfg, "warnings": warnings,
                        "path": config.PARKING_ZONES_JSON})
    except (ValueError, TypeError, OSError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/parking_plan")
def api_parking_plan():
    """把分车型进出量换算成泊位需求，并与录入的实有车位做供需对比"""
    zones = parking_plan.load_zones(config.PARKING_ZONES_JSON)
    result = parking_plan.compute(load_csv(config.HOURLY_CSV),
                                  classes=config.CLASSES, zones=zones)
    return jsonify({k: v for k, v in result.items() if k != "timeline"})


def run():
    if not Flask:
        raise SystemExit("Flask 未安装，请先: pip install flask")
    app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=False)


if __name__ == "__main__":
    run()
