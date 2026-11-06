# 网页仪表盘: Flask + chart.js，读取报表 CSV 实时展示各车型进出统计
import os
import csv
import json

import config

try:
    from flask import Flask, jsonify, Response
except ImportError:
    Flask = None

app = Flask(__name__) if Flask else None


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
 .wrap{max-width:1000px;margin:20px auto;padding:0 16px}
 .cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}
 .card{flex:1;min-width:140px;background:#fff;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
 .card .n{font-size:26px;font-weight:600;color:#185FA5}
 .card .l{font-size:13px;color:#666;margin-top:4px}
 table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden}
 th,td{padding:10px 12px;border-bottom:1px solid #eee;font-size:13px;text-align:center}
 th{background:#f0f4f8;color:#444}
 .chart-box{background:#fff;border-radius:12px;padding:16px;margin-top:20px}
</style></head>
<body>
<header>校园车辆智能统计系统 · 校门进出实时看板</header>
<div class="wrap">
  <div class="cards" id="cards"></div>
  <div class="chart-box"><canvas id="bar"></canvas></div>
  <h3 style="margin-top:24px">每小时明细</h3>
  <table id="tbl"><thead></thead><tbody></tbody></table>
</div>
<script>
async function load(){
  const r = await fetch('/api/stats'); const d = await r.json();
  const cls = d.classes, cn = d.class_cn;
  let te=0, tx=0;
  cls.forEach(c=>{te+=d.total.enter[c]; tx+=d.total.exit[c];});
  document.getElementById('cards').innerHTML =
    `<div class='card'><div class='n'>${te}</div><div class='l'>今日进校总数</div></div>`+
    `<div class='card'><div class='n'>${tx}</div><div class='l'>今日出校总数</div></div>`+
    cls.map(c=>`<div class='card'><div class='n'>${d.total.enter[c]+d.total.exit[c]}</div><div class='l'>${cn[c]} 进出</div></div>`).join('');
  const labels = cls.map(c=>cn[c]);
  new Chart(document.getElementById('bar'),{type:'bar',data:{labels,datasets:[
    {label:'进校',data:cls.map(c=>d.total.enter[c]),backgroundColor:'#185FA5'},
    {label:'出校',data:cls.map(c=>d.total.exit[c]),backgroundColor:'#E24B4A'}]},
    options:{responsive:true,plugins:{title:{display:true,text:'各车型进出数量'}}}});
  const rows = d.hourly;
  if(rows.length){ const cols=Object.keys(rows[0]);
    document.querySelector('#tbl thead').innerHTML='<tr>'+cols.map(c=>`<th>${c}</th>`).join('')+'</tr>';
    document.querySelector('#tbl tbody').innerHTML=rows.map(r=>'<tr>'+cols.map(c=>`<td>${r[c]}</td>`).join('')+'</tr>').join('');
  }
}
load(); setInterval(load, 5000);
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


def run():
    if not app:
        raise SystemExit("Flask 未安装，请先: uv pip install flask")
    app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=False)


if __name__ == "__main__":
    run()
