# 网页数据驾驶舱: Flask + 纯 SVG 自绘图表（零外部依赖），读取报表 CSV 实时展示。
# 同时提供「场地车位设置」：本地人员按实际场地录入分区 / 适用车型 / 实有车位数量。
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


# 说明: 整页模板为单一数据源，静态快照脚本 tools/make_dashboard_snapshot.py
#       直接复用本常量并内联三份 API 数据，因此离线预览与在线看板完全一致。
HTML = r"""<!doctype html>
<html lang="zh-CN" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>车辆智能统计 · 数据驾驶舱</title>
<style>
*{box-sizing:border-box}
:root{
  --bg:#070E1B; --bg2:#0B1424; --panel:#101C30; --panel2:#14243C; --panel3:#182C47;
  --line:#1D3352; --line2:#264168; --text:#EAF2FC; --muted:#8AA3C2; --dim:#5C7698;
  --blue:#3B82F6; --cyan:#22D3EE; --amber:#FBBF24; --violet:#A78BFA;
  --green:#34D399; --red:#F87171; --enter:#3B82F6; --exit:#FBBF24;
  --shadow:0 10px 30px rgba(0,0,0,.28); --grid:rgba(255,255,255,.035);
}
html[data-theme="light"]{
  --bg:#EFF3F9; --bg2:#F7F9FD; --panel:#FFFFFF; --panel2:#F5F8FD; --panel3:#EAF1FA;
  --line:#DCE6F2; --line2:#C7D7EA; --text:#102A48; --muted:#5C7391; --dim:#8397AE;
  --blue:#2563EB; --cyan:#0891B2; --amber:#D97706; --violet:#7C3AED;
  --green:#059669; --red:#DC2626; --enter:#2563EB; --exit:#EA9A0B;
  --shadow:0 8px 24px rgba(20,50,90,.09); --grid:rgba(16,42,72,.03);
}
html,body{margin:0;padding:0}
body{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;
  background:var(--bg);color:var(--text);min-height:100vh;
  background-image:radial-gradient(circle at 12% -8%,rgba(59,130,246,.13),transparent 42%),
                   radial-gradient(circle at 92% 4%,rgba(34,211,238,.10),transparent 38%),
                   linear-gradient(var(--grid) 1px,transparent 1px),
                   linear-gradient(90deg,var(--grid) 1px,transparent 1px);
  background-size:auto,auto,44px 44px,44px 44px;
  -webkit-font-smoothing:antialiased;
}
.num{font-variant-numeric:tabular-nums;font-feature-settings:'tnum'}
.wrap{max-width:1560px;margin:0 auto;padding:0 22px 34px}

/* ---------- 顶栏 ---------- */
header{
  position:sticky;top:0;z-index:30;display:flex;align-items:center;gap:16px;
  padding:14px 26px;background:var(--bg2);
  backdrop-filter:blur(14px);border-bottom:1px solid var(--line);
}
.brand{display:flex;align-items:center;gap:12px;min-width:0}
.logo{
  width:38px;height:38px;border-radius:11px;flex:none;
  background:linear-gradient(135deg,var(--blue),var(--cyan));
  display:flex;align-items:center;justify-content:center;color:#fff;
  box-shadow:0 4px 16px rgba(59,130,246,.38);
}
.logo svg{width:21px;height:21px}
.brand h1{margin:0;font-size:16px;font-weight:700;letter-spacing:.4px;white-space:nowrap}
.brand p{margin:3px 0 0;font-size:11px;color:var(--muted);letter-spacing:.6px;white-space:nowrap}
.hspacer{flex:1}
.live{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted);white-space:nowrap}
.live i{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 0 4px rgba(52,211,153,.14);animation:pulse 2.2s infinite}
@keyframes pulse{50%{box-shadow:0 0 0 8px rgba(52,211,153,0)}}
.clock{font-size:13px;color:var(--text);letter-spacing:.5px;white-space:nowrap}
.clock small{color:var(--muted);font-size:11px;margin-right:6px}
.tbtn{
  border:1px solid var(--line2);background:var(--panel);color:var(--text);
  border-radius:9px;padding:8px 13px;font-size:12px;cursor:pointer;font-family:inherit;
  display:flex;align-items:center;gap:7px;white-space:nowrap;transition:.18s;
}
.tbtn:hover{border-color:var(--blue);transform:translateY(-1px)}
.tbtn.primary{background:linear-gradient(135deg,var(--blue),#1D4ED8);border-color:transparent;color:#fff}
.tbtn svg{width:14px;height:14px}
.cd{font-size:11px;color:var(--dim);white-space:nowrap}

/* ---------- 栅格 ---------- */
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px;margin-top:18px}
.panel{
  background:linear-gradient(160deg,var(--panel),var(--bg2));
  border:1px solid var(--line);border-radius:16px;padding:18px 20px;
  box-shadow:var(--shadow);position:relative;overflow:hidden;
}
html[data-theme="light"] .panel{background:var(--panel)}
.panel::before{content:'';position:absolute;inset:0 0 auto;height:1px;
  background:linear-gradient(90deg,transparent,var(--blue),var(--cyan),transparent);opacity:.55}
.p-h{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:14px}
.p-h h2{margin:0;font-size:14px;font-weight:700;letter-spacing:.3px}
.p-h .sub{font-size:11px;color:var(--muted)}
.p-h .tag{font-size:10px;color:var(--cyan);border:1px solid var(--line2);border-radius:20px;padding:3px 9px;white-space:nowrap}

/* ---------- KPI ---------- */
.kpi{grid-column:span 2;padding:16px 17px 14px}
.kpi .top{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:11.5px;letter-spacing:.3px}
.kpi .ico{width:25px;height:25px;border-radius:8px;display:flex;align-items:center;justify-content:center;flex:none}
.kpi .ico svg{width:14px;height:14px}
.kpi .val{font-size:30px;font-weight:750;line-height:1.15;margin:12px 0 2px;letter-spacing:-.5px}
.kpi .val u{font-size:12px;font-weight:500;text-decoration:none;color:var(--muted);margin-left:5px}
.kpi .foot{display:flex;justify-content:space-between;font-size:10.5px;color:var(--dim);margin-bottom:9px}
.kpi .bar{height:4px;border-radius:4px;background:var(--panel3);overflow:hidden}
.kpi .bar i{display:block;height:100%;border-radius:4px;transition:width .8s cubic-bezier(.2,.8,.2,1)}
.kpi{transition:transform .2s ease,border-color .2s ease}
.kpi:hover{transform:translateY(-3px);border-color:var(--line2)}

/* ---------- 图表通用 ---------- */
svg{display:block;width:100%;height:auto;overflow:visible}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:var(--muted);margin-top:6px}
.legend span{display:flex;align-items:center;gap:6px}
.legend i{width:9px;height:9px;border-radius:3px;display:inline-block}
.tip{cursor:default}
#tooltip{
  position:fixed;z-index:99;pointer-events:none;opacity:0;transition:opacity .12s;
  background:#0B1728;color:#EAF2FC;border:1px solid #2A4467;border-radius:9px;
  padding:9px 12px;font-size:12px;line-height:1.6;box-shadow:0 12px 30px rgba(0,0,0,.4);
  white-space:nowrap;
}
html[data-theme="light"] #tooltip{background:#102A48;color:#F2F7FF;border-color:#3B5E8C}
#tooltip b{color:#7DD3FC}

/* ---------- 主图 / 环图 ---------- */
.chart-main{grid-column:span 8;min-height:342px}
.chart-donut{grid-column:span 4;min-height:342px}
.donut-wrap{display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.donut-svg{max-width:220px;flex:1 1 190px}
.donut-center{font-size:26px;font-weight:750;fill:var(--text)}
.donut-sub{font-size:10px;fill:var(--muted);letter-spacing:1px}
.dlist{flex:1 1 150px;display:flex;flex-direction:column;gap:10px}
.drow{display:flex;align-items:center;gap:8px;font-size:12px}
.drow i{width:8px;height:8px;border-radius:50%;flex:none}
.drow .nm{color:var(--muted);flex:1}
.drow .v{font-weight:700}
.drow .p{color:var(--dim);font-size:10.5px;min-width:38px;text-align:right}

/* ---------- 热力 / 供需 ---------- */
.heat{grid-column:span 7;min-height:224px}
.supply{grid-column:span 5;min-height:224px}
.heat-grid{display:grid;grid-template-columns:repeat(24,1fr);gap:5px;margin-top:8px}
.hcell{height:34px;border-radius:5px;background:var(--panel3);position:relative;transition:.2s}
.hcell.on{background:linear-gradient(180deg,var(--cyan),var(--blue));box-shadow:0 0 14px rgba(34,211,238,.4)}
.hcell:hover{transform:translateY(-3px)}
.haxis{display:flex;justify-content:space-between;font-size:10px;color:var(--dim);margin-top:9px}
.heat-note{font-size:11px;color:var(--muted);margin-top:12px;line-height:1.8}
.heat-note b{color:var(--amber)}
.supply-flex{display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.ring-svg{max-width:150px;flex:0 0 140px}
.sup-metrics{flex:1 1 160px;display:flex;flex-direction:column;gap:11px}
.sup-row{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px dashed var(--line);padding-bottom:9px}
.sup-row:last-child{border:0;padding-bottom:0}
.sup-row .k{font-size:11px;color:var(--muted)}
.sup-row .v{font-size:19px;font-weight:750}

/* ---------- 分区供需卡 ---------- */
.zones{grid-column:span 12}
.zgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.zcard{background:var(--panel2);border:1px solid var(--line);border-radius:13px;padding:16px 17px}
.zcard .zh{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:6px}
.zcard .zn{font-size:14px;font-weight:700}
.zcard .zc{font-size:11px;color:var(--muted);margin-bottom:14px}
.badge{font-size:10px;padding:3px 9px;border-radius:20px;white-space:nowrap}
.badge.ok{background:rgba(52,211,153,.14);color:var(--green)}
.badge.warn{background:rgba(251,191,36,.16);color:var(--amber)}
.badge.bad{background:rgba(248,113,113,.16);color:var(--red)}
.ztrack{height:9px;border-radius:9px;background:var(--panel3);overflow:hidden;position:relative}
.ztrack i{display:block;height:100%;border-radius:9px;background:linear-gradient(90deg,var(--blue),var(--cyan))}
.ztrack i.hot{background:linear-gradient(90deg,var(--amber),var(--red))}
.znums{display:flex;gap:18px;flex-wrap:wrap;margin-top:14px}
.znums div{min-width:60px}
.znums .k{font-size:10px;color:var(--dim)}
.znums .v{font-size:17px;font-weight:700;margin-top:2px}
.znums .v.pos{color:var(--green)} .znums .v.neg{color:var(--red)}

/* ---------- 表格 ---------- */
.tblpanel{grid-column:span 12}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;color:var(--muted);font-weight:600;font-size:10.5px;letter-spacing:.6px;
   padding:10px 12px;border-bottom:1px solid var(--line2);text-transform:uppercase}
td{padding:11px 12px;border-bottom:1px solid var(--line);color:var(--text)}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--panel2)}
.inline-bar{height:5px;border-radius:5px;background:var(--panel3);overflow:hidden;min-width:90px}
.inline-bar i{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--cyan));border-radius:5px}
.mini{grid-column:span 12;display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}
.mini .panel{padding:15px 17px}
.mini .k{font-size:10.5px;color:var(--muted)}
.mini .v{font-size:22px;font-weight:750;margin-top:6px}
.hints{grid-column:span 12;background:rgba(251,191,36,.07);border:1px solid rgba(251,191,36,.25);
  border-radius:13px;padding:14px 18px;font-size:12px;color:var(--muted);line-height:1.9}
.hints b{color:var(--amber)}
footer{grid-column:span 12;margin-top:8px;padding-top:16px;border-top:1px solid var(--line);
  display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--dim);line-height:1.8}

/* ---------- 抽屉 ---------- */
.mask{position:fixed;inset:0;background:rgba(3,9,18,.62);backdrop-filter:blur(3px);
  opacity:0;pointer-events:none;transition:.25s;z-index:40}
.mask.on{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;right:0;bottom:0;width:min(560px,94vw);z-index:41;
  background:var(--bg2);border-left:1px solid var(--line2);box-shadow:-20px 0 50px rgba(0,0,0,.4);
  transform:translateX(101%);transition:transform .3s cubic-bezier(.2,.8,.2,1);
  display:flex;flex-direction:column}
.drawer.on{transform:none}
.dh{padding:20px 24px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between}
.dh h2{margin:0;font-size:16px} .dh p{margin:5px 0 0;font-size:11px;color:var(--muted)}
.dbody{padding:20px 24px;overflow:auto;flex:1}
.dfoot{padding:16px 24px;border-top:1px solid var(--line);display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.field{margin-bottom:18px}
.field>label{display:block;font-size:11px;color:var(--muted);margin-bottom:7px;letter-spacing:.4px}
input[type=text],input[type=number]{
  width:100%;background:var(--panel);border:1px solid var(--line2);color:var(--text);
  border-radius:8px;padding:9px 11px;font-size:12.5px;font-family:inherit;outline:none}
input:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(59,130,246,.14)}
.zrow{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:13px;margin-bottom:10px}
.zrow .r1{display:flex;gap:9px;align-items:center;margin-bottom:10px}
.zrow .r1 input.z-name{flex:1}
.zrow .r1 input.z-slots{width:96px}
.chks{display:flex;gap:12px;flex-wrap:wrap;font-size:11.5px;color:var(--muted)}
.chks label{display:flex;align-items:center;gap:5px;cursor:pointer}
.chks input{accent-color:var(--blue)}
.zrow .r2{display:flex;gap:9px;align-items:center;margin-top:10px}
.zrow .r2 input{flex:1}
.btn{border:1px solid var(--line2);background:var(--panel);color:var(--text);border-radius:8px;
  padding:9px 14px;font-size:12px;cursor:pointer;font-family:inherit;transition:.18s}
.btn:hover{border-color:var(--blue)}
.btn.pri{background:linear-gradient(135deg,var(--blue),#1D4ED8);border-color:transparent;color:#fff}
.btn.danger{color:var(--red)}
.btn svg{width:13px;height:13px;vertical-align:-2px}
.msg{font-size:11.5px;line-height:1.7;flex:1;min-width:140px}
.msg.ok{color:var(--green)} .msg.err{color:var(--red)} .msg.info{color:var(--muted)}
.hintbox{font-size:11px;color:var(--dim);line-height:1.9;background:var(--panel);
  border-radius:9px;padding:12px 14px;margin-top:14px;border:1px solid var(--line)}
code{background:var(--panel3);padding:1px 5px;border-radius:4px;font-size:11px}

@media(max-width:1240px){.kpi{grid-column:span 4}.chart-main,.chart-donut,.heat,.supply{grid-column:span 12}}
@media(max-width:760px){
  .wrap{padding:0 12px 28px} header{padding:12px 14px;gap:10px;flex-wrap:wrap}
  .brand p,.live,.cd{display:none} .kpi{grid-column:span 6} .clock{font-size:11px}
  .panel{padding:15px} .hspacer{display:none}
}
</style></head>
<body>

<header>
  <div class="brand">
    <div class="logo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 16l1.6-5.2A2 2 0 0 1 6.5 9.4h11a2 2 0 0 1 1.9 1.4L21 16"/><path d="M3 16h18v3H3z"/><circle cx="7" cy="19" r="1.4"/><circle cx="17" cy="19" r="1.4"/><path d="M8 6h8"/></svg></div>
    <div><h1>车辆智能统计 · 数据驾驶舱</h1><p>CAMPUS VEHICLE ANALYTICS / REAL-TIME MONITOR</p></div>
  </div>
  <div class="hspacer"></div>
  <div class="live"><i></i><span>数据在线</span></div>
  <div class="clock"><small>本地时间</small><span id="clock" class="num">--:--:--</span></div>
  <div class="cd" id="cd">5s 后刷新</div>
  <button class="tbtn" id="btnRefresh"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 11a8 8 0 1 0-2 6"/><path d="M20 5v6h-6"/></svg>刷新</button>
  <button class="tbtn" id="btnTheme"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg><span id="themeTxt">浅色</span></button>
  <button class="tbtn primary" id="btnZones"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21H10v-.1A1.7 1.7 0 0 0 7.1 19.7l-.1.1L4.2 17l.1-.1A1.7 1.7 0 0 0 3 14H3v-4h.1A1.7 1.7 0 0 0 4.3 7.1L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 10 4V4h4v.1a1.7 1.7 0 0 0 2.9 1.2l.1-.1 2.8 2.8-.1.1a1.7 1.7 0 0 0 1.2 2.9H21v4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>场地车位设置</button>
</header>

<div class="wrap">
  <div class="grid" id="grid">

    <div class="grid" id="kpis" style="grid-column:span 12;gap:14px;margin:0"></div>

    <section class="panel chart-main">
      <div class="p-h"><h2>分车型进出流量</h2><span class="tag">VEHICLE FLOW / 辆次</span></div>
      <div id="barsSvg"></div>
      <div class="legend"><span><i style="background:var(--enter)"></i>进入</span><span><i style="background:var(--exit)"></i>驶出</span><span class="sub" id="barsNote"></span></div>
    </section>

    <section class="panel chart-donut">
      <div class="p-h"><h2>车型结构占比</h2><span class="sub">按进出总量</span></div>
      <div class="donut-wrap">
        <div class="donut-svg" id="donutSvg"></div>
        <div class="dlist" id="donutList"></div>
      </div>
    </section>

    <section class="panel heat">
      <div class="p-h"><h2>24 小时通行热力</h2><span class="tag" id="heatTag">00:00 — 23:00</span></div>
      <div class="heat-grid" id="heatGrid"></div>
      <div class="haxis"><span>00</span><span>04</span><span>08</span><span>12</span><span>16</span><span>20</span><span>23</span></div>
      <div class="heat-note" id="heatNote"></div>
    </section>

    <section class="panel supply">
      <div class="p-h"><h2>停车供需总览</h2><span class="sub" id="siteTag"></span></div>
      <div class="supply-flex">
        <div class="ring-svg" id="ringSvg"></div>
        <div class="sup-metrics" id="supMetrics"></div>
      </div>
    </section>

    <section class="panel zones">
      <div class="p-h"><h2>分区供需对比</h2><span class="sub">实有车位（供给侧） vs 峰值在场推算需求（需求侧）</span></div>
      <div class="zgrid" id="zgrid"></div>
    </section>

    <section class="panel tblpanel">
      <div class="p-h"><h2>逐时段明细</h2><span class="sub">来源 hourly.csv · 每行为一个统计小时桶</span></div>
      <table id="tbl"><thead></thead><tbody></tbody></table>
    </section>

    <div class="mini" id="mini"></div>
    <div class="hints" id="hints"></div>

    <footer>
      <span>口径：虚拟线穿越计数 → 分车型进出聚合 → 峰值在场推算（周转余量 20%、通道系数 1.35）→ 与本地录入车位做供需对比。</span>
      <span id="footNote"></span>
    </footer>
  </div>
</div>

<!-- 场地车位设置抽屉 -->
<div class="mask" id="mask"></div>
<aside class="drawer" id="drawer">
  <div class="dh"><div><h2>场地车位设置</h2><p>由本地人员按实际场地录入；分区数量、适用车型、车位数量均可改</p></div>
    <button class="btn" id="btnClose">关闭</button></div>
  <div class="dbody">
    <div class="field"><label>场地名称</label><input type="text" id="siteName"></div>
    <div class="field"><label>停车分区 <span style="color:var(--dim)">（配置文件：<code id="zonePath">-</code>）</span></label>
      <div id="zoneRows"></div>
      <button class="btn" id="addZone" style="margin-top:4px">+ 添加分区</button>
    </div>
    <div class="hintbox">
      示例：A 区停轿车 / SUV 共 360 位，B 区停客车 / 货车共 180 位。<br>
      同一车型被多个分区服务时需求会重复计入；未被覆盖的车型不参与供需对比，系统都会给出提示。<br>
      自动刷新<strong>不会</strong>打断正在编辑的表单。
    </div>
    <div style="margin-top:14px"><span id="zoneMsg" class="msg info"></span></div>
  </div>
  <div class="dfoot">
    <button class="btn pri" id="saveZones">保存场地配置</button>
    <button class="btn" id="resetZones">放弃修改</button>
  </div>
</aside>

<div id="tooltip"></div>

<script>
/* ============ 全局状态 ============ */
let S=null, Z=null, P=null, CLS=[], CN={};
const COLORS=['#3B82F6','#22D3EE','#FBBF24','#A78BFA'];
let theme = (function(){ try{return localStorage.getItem('cv_theme')||'dark';}catch(e){return 'dark';} })();
let cd=5, editing=false;
const $ = id => document.getElementById(id);
const esc = s => String(s==null?'':s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const n = v => Number(v||0);
const icon = (p,c) => `<span class="ico" style="background:${c}1f;color:${c}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg></span>`;
const ICO = {
  in:  icon('<path d="M4 12h14m-5-5 5 5-5 5"/>','#3B82F6'),
  out: icon('<path d="M20 12H6m5-5-5 5 5 5"/>','#FBBF24'),
  net: icon('<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>','#34D399'),
  sum: icon('<path d="M4 6h16M4 12h16M4 18h10"/>','#22D3EE'),
  peak:icon('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>','#A78BFA'),
  occ: icon('<path d="M3 19V9l9-6 9 6v10"/><path d="M9 19v-6h6v6"/>','#F87171')
};

/* ============ 主题 / 时钟 ============ */
function applyTheme(){
  document.documentElement.setAttribute('data-theme',theme);
  $('themeTxt').textContent = theme==='dark' ? '浅色' : '深色';
  try{ localStorage.setItem('cv_theme',theme); }catch(e){}
  if(S) renderAll();
}
$('btnTheme').onclick=()=>{ theme = theme==='dark'?'light':'dark'; applyTheme(); };
function tickClock(){
  const d=new Date();
  $('clock').textContent=[d.getHours(),d.getMinutes(),d.getSeconds()].map(x=>String(x).padStart(2,'0')).join(':');
}
setInterval(tickClock,1000); tickClock();
setInterval(()=>{
  cd--; if(cd<=0){ cd=5; refreshData(); }
  $('cd').textContent=cd+'s 后刷新';
},1000);
$('btnRefresh').onclick=()=>{ cd=5; refreshData(); };

/* ============ tooltip ============ */
const tipEl=$('tooltip');
document.addEventListener('mouseover',e=>{
  const t=e.target.closest && e.target.closest('[data-tip]');
  if(!t) return;
  tipEl.innerHTML=t.getAttribute('data-tip'); tipEl.style.opacity='1';
});
document.addEventListener('mousemove',e=>{
  if(tipEl.style.opacity!=='1') return;
  tipEl.style.left=Math.min(e.clientX+14,window.innerWidth-240)+'px';
  tipEl.style.top=Math.max(e.clientY-46,8)+'px';
});
document.addEventListener('mouseout',e=>{
  if(e.target.closest && e.target.closest('[data-tip]')) tipEl.style.opacity='0';
});

/* ============ 数据 ============ */
async function refreshData(){
  try{
    const [a,c]=await Promise.all([
      fetch('/api/stats').then(r=>r.json()),
      fetch('/api/parking_plan').then(r=>r.json())
    ]);
    S=a; P=c; CLS=a.classes||['sedan','suv','truck','bus']; CN=a.class_cn||{};
    renderAll();
    $('siteTag').textContent = (c.zones&&c.zones.site_name)||'场地';
    $('footNote').textContent = '样本区间 '+(c.date_from||'-')+' ~ '+(c.date_to||'-')+' · '+(c.hours||0)+' 个小时桶 · 自动生成';
  }catch(err){ console.warn('数据读取失败',err); }
}
async function loadZones(msg){
  try{
    const d=await fetch('/api/parking_zones').then(r=>r.json());
    Z=d; $('siteName').value=d.site_name||''; $('zonePath').textContent=d.source||'内置示例（保存后生成本地配置）';
    renderZoneForm(d.zones||[]);
    setMsg(msg || ((d.warnings||[]).length?d.warnings:['场地配置已加载']), msg?'ok':'info');
  }catch(err){ setMsg(['配置读取失败：'+err],'err'); }
}
function setMsg(lines,kind){
  const el=$('zoneMsg'); el.className='msg '+(kind||'info');
  el.innerHTML=(lines||[]).map(esc).join(' &nbsp;·&nbsp; ');
}

/* ============ KPI ============ */
function renderKPI(){
  const ent=CLS.map(c=>n(S.total.enter[c])), ext=CLS.map(c=>n(S.total.exit[c]));
  const te=ent.reduce((a,b)=>a+b,0), tx=ext.reduce((a,b)=>a+b,0);
  const tot=te+tx, net=te-tx;
  const peak=(P.peak_hour&&P.peak_hour.throughput)||0;
  const occ=(P.zones&&P.zones.peak_total)||0;
  const items=[
    {i:ICO.in,  l:'今日进入总数', v:te,  u:'辆', f:`占总通行 ${tot?Math.round(te/tot*100):0}%`, p:tot?te/tot*100:0, c:'var(--enter)'},
    {i:ICO.out, l:'今日驶出总数', v:tx,  u:'辆', f:`占总通行 ${tot?Math.round(tx/tot*100):0}%`, p:tot?tx/tot*100:0, c:'var(--exit)'},
    {i:ICO.net, l:'净流入',       v:(net>=0?'+':'')+net, u:'辆', f:net>=0?'在场车辆净增加':'在场车辆净减少', p:Math.min(100,Math.abs(net)/Math.max(tot,1)*100), c:'var(--green)'},
    {i:ICO.sum, l:'总通行量',     v:tot, u:'辆次', f:'进入 + 驶出', p:100, c:'var(--cyan)'},
    {i:ICO.peak,l:'高峰小时通行', v:peak,u:'辆次', f:(P.peak_hour&&P.peak_hour.period)||'-', p:100, c:'var(--violet)'},
    {i:ICO.occ, l:'峰值在场',     v:occ, u:'辆', f:'四类车合计', p:100, c:'var(--red)'}
  ];
  $('kpis').innerHTML=items.map(x=>`<div class="panel kpi">
    <div class="top">${x.i}<span>${x.l}</span></div>
    <div class="val num" style="color:${x.c}">${x.v}<u>${x.u}</u></div>
    <div class="foot"><span>${esc(x.f)}</span></div>
    <div class="bar"><i style="width:${Math.max(3,Math.min(100,x.p))}%;background:linear-gradient(90deg,${x.c},var(--cyan))"></i></div>
  </div>`).join('');
}

/* ============ 分组柱状图（纯 SVG） ============ */
function renderBars(){
  const W=860,H=290,L=48,R=16,T=18,B=44;
  const iw=W-L-R, ih=H-T-B;
  const ent=CLS.map(c=>n(S.total.enter[c])), ext=CLS.map(c=>n(S.total.exit[c]));
  const max=Math.max(1,...ent,...ext);
  const nice=Math.ceil(max/10)*10||10;
  const dark=theme==='dark';
  const AX=dark?'#7E96B4':'#6B7C8D', GRID=dark?'#1D3352':'#DCE6F2';
  let g='';
  for(let k=0;k<=4;k++){
    const y=T+ih-ih*k/4, v=Math.round(nice*k/4);
    g+=`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="${GRID}" stroke-dasharray="3 5"/>`;
    g+=`<text x="${L-10}" y="${y+4}" text-anchor="end" font-size="10" fill="${AX}">${v}</text>`;
  }
  const gw=iw/CLS.length, bw=Math.min(34,gw/3.4), gap=8;
  CLS.forEach((c,i)=>{
    const cx=L+gw*i+gw/2;
    const pairs=[[ent[i],'var(--enter)','进入','gIn'],[ext[i],'var(--exit)','驶出','gOut']];
    pairs.forEach((p,j)=>{
      const v=p[0], h=Math.max(v>0?3:0,ih*v/nice);
      const x=cx-(j===0?bw+gap/2:-gap/2), y=T+ih-h;
      const col=j===0?'#3B82F6':'#F59E0B';
      g+=`<rect class="tip" data-tip="<b>${esc(CN[c]||c)} · ${p[2]}</b><br>${v} 辆" x="${x}" y="${y}" width="${bw}" height="${h}" rx="5" fill="url(#${p[3]})" opacity=".95"/>`;
      if(v>0) g+=`<text x="${x+bw/2}" y="${y-7}" text-anchor="middle" font-size="11" font-weight="700" fill="${col}">${v}</text>`;
    });
    g+=`<text x="${cx}" y="${H-16}" text-anchor="middle" font-size="12" fill="${AX}" font-weight="600">${esc(CN[c]||c)}</text>`;
  });
  g+=`<line x1="${L}" y1="${T+ih}" x2="${W-R}" y2="${T+ih}" stroke="${GRID}"/>`;
  $('barsSvg').innerHTML=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="gIn" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#60A5FA"/><stop offset="1" stop-color="#1D4ED8"/></linearGradient>
      <linearGradient id="gOut" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FCD34D"/><stop offset="1" stop-color="#D97706"/></linearGradient>
    </defs>${g}</svg>`;
  $('barsNote').textContent='共 '+CLS.length+' 类车型 · 最大刻度 '+nice+' 辆';
}

/* ============ 车型结构环图 ============ */
function renderDonut(){
  const vals=CLS.map(c=>n(S.total.enter[c])+n(S.total.exit[c]));
  const tot=vals.reduce((a,b)=>a+b,0)||1;
  const C=2*Math.PI*76; let off=0, seg='';
  vals.forEach((v,i)=>{
    const len=C*v/tot;
    if(len>0){
      seg+=`<circle class="tip" data-tip="<b>${esc(CN[CLS[i]]||CLS[i])}</b><br>${v} 辆次 · ${(v/tot*100).toFixed(1)}%" cx="110" cy="110" r="76" fill="none" stroke="${COLORS[i%4]}" stroke-width="19" stroke-dasharray="${Math.max(0,len-4)} ${C-Math.max(0,len-4)}" stroke-dashoffset="${-off}" transform="rotate(-90 110 110)"/>`;
    }
    off+=len;
  });
  const dark=theme==='dark';
  $('donutSvg').innerHTML=`<svg viewBox="0 0 220 220">
    <circle cx="110" cy="110" r="76" fill="none" stroke="${dark?'#1D3352':'#E4ECF5'}" stroke-width="19"/>
    ${seg}
    <text class="donut-center num" x="110" y="108" text-anchor="middle">${tot}</text>
    <text class="donut-sub" x="110" y="128" text-anchor="middle">TOTAL 辆次</text>
  </svg>`;
  $('donutList').innerHTML=CLS.map((c,i)=>`<div class="drow">
    <i style="background:${COLORS[i%4]}"></i><span class="nm">${esc(CN[c]||c)}</span>
    <span class="v num">${vals[i]}</span><span class="p num">${(vals[i]/tot*100).toFixed(1)}%</span>
  </div>`).join('');
}

/* ============ 24 小时热力 ============ */
function renderHeat(){
  const hrs=Array(24).fill(0);
  (S.hourly||[]).forEach(r=>{
    const m=/\s(\d{1,2}):\d{2}/.exec(r.period||'');
    const h=m?parseInt(m[1],10):12;
    let v=0; CLS.forEach(c=>{v+=n(r['enter_'+c])+n(r['exit_'+c]);});
    hrs[Math.min(23,Math.max(0,h))]+=v;
  });
  const mx=Math.max(1,...hrs), covered=hrs.filter(v=>v>0).length;
  $('heatGrid').innerHTML=hrs.map((v,h)=>{
    const a=v>0?(0.45+0.55*v/mx):0;
    const tip=`<b>${String(h).padStart(2,'0')}:00 — ${String(h).padStart(2,'0')}:59</b><br>通行 ${v} 辆次`;
    return `<div class="hcell ${v>0?'on':''} tip" style="${v>0?`opacity:${a};`:''}" data-tip="${tip}"></div>`;
  }).join('');
  const peakH=covered?hrs.indexOf(mx):-1;
  $('heatTag').textContent='覆盖 '+covered+' / 24 小时';
  $('heatNote').innerHTML=peakH>=0
    ? `样本覆盖 <b>${covered}</b> 个小时桶，最高峰 <b>${String(peakH).padStart(2,'0')}:00</b> 通行 <b>${mx}</b> 辆次。`+
      (covered<6?' 当前为短视频样本，空白时段不代表无车流，<b>不能据此判断全天分布</b>。':' 可用于识别早晚高峰与疏导时段。')
    : '暂无时段数据，请先运行 main.py 生成 hourly.csv。';
}

/* ============ 供需总览环 ============ */
function renderSupply(){
  const z=P.zones||{};
  const sat=Math.max(0,Math.min(100,n(z.saturation_pct)));
  const C=2*Math.PI*62;
  const len=C*sat/100;
  const dark=theme==='dark';
  const col=sat>85?'#F87171':(sat>60?'#FBBF24':'#34D399');
  $('ringSvg').innerHTML=`<svg viewBox="0 0 160 160">
    <circle cx="80" cy="80" r="62" fill="none" stroke="${dark?'#1D3352':'#E4ECF5'}" stroke-width="14"/>
    <circle cx="80" cy="80" r="62" fill="none" stroke="${col}" stroke-width="14" stroke-linecap="round"
      stroke-dasharray="${len} ${C-len}" transform="rotate(-90 80 80)"/>
    <text class="donut-center num" x="80" y="76" text-anchor="middle" style="font-size:23px">${sat.toFixed(1)}%</text>
    <text class="donut-sub" x="80" y="96" text-anchor="middle">峰值饱和度</text>
  </svg>`;
  const gap=n(z.gap_total);
  $('supMetrics').innerHTML=`
    <div class="sup-row"><span class="k">实有车位合计</span><span class="v num" style="color:var(--blue)">${n(z.supply_total)}</span></div>
    <div class="sup-row"><span class="k">需求泊位合计</span><span class="v num" style="color:var(--cyan)">${n(z.required_total)}</span></div>
    <div class="sup-row"><span class="k">总体余量 / 缺口</span><span class="v num" style="color:${gap>=0?'var(--green)':'var(--red)'}">${gap>=0?'+':''}${gap}</span></div>`;
}

/* ============ 分区供需卡 ============ */
function badge(s){
  const k=s==='供给充足'?'ok':((s||'').indexOf('不足')>=0||(s||'').indexOf('超负荷')>=0?'bad':'warn');
  return `<span class="badge ${k}">${esc(s||'未配置')}</span>`;
}
function renderZoneCards(){
  const items=(P.zones&&P.zones.items)||[];
  $('zgrid').innerHTML=items.map(i=>{
    const sat=Math.max(0,Math.min(100,n(i.saturation_pct)));
    const gap=n(i.gap_slots);
    return `<div class="zcard">
      <div class="zh"><span class="zn">${esc(i.name)}</span>${badge(i.status)}</div>
      <div class="zc">适用车型：${(i.classes_cn||i.classes||[]).map(esc).join(' / ')||'-'}</div>
      <div class="ztrack"><i class="${sat>70?'hot':''}" style="width:${Math.max(2,sat)}%"></i></div>
      <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--dim);margin-top:7px">
        <span>峰值饱和度 ${i.saturation_pct}%</span><span>需求占用率 ${i.utilization_pct}%</span></div>
      <div class="znums">
        <div><div class="k">实有车位</div><div class="v num">${i.supply_slots}</div></div>
        <div><div class="k">峰值在场</div><div class="v num">${i.peak_occupancy}</div></div>
        <div><div class="k">需求泊位</div><div class="v num">${i.required_slots}</div></div>
        <div><div class="k">余量 / 缺口</div><div class="v num ${gap>=0?'pos':'neg'}">${gap>=0?'+':''}${gap}</div></div>
      </div>
    </div>`;
  }).join('') || '<div class="hintbox">尚未配置分区，点右上角「场地车位设置」录入。</div>';
}

/* ============ 明细表 / 小卡 / 提示 ============ */
function renderTable(){
  const rows=S.hourly||[];
  const head=['时段','进入','驶出','净流入','通行量','强度'];
  let max=1;
  const calc=rows.map(r=>{
    let e=0,x=0; CLS.forEach(c=>{e+=n(r['enter_'+c]);x+=n(r['exit_'+c]);});
    max=Math.max(max,e+x); return {p:r.period,e,x,net:e-x,tot:e+x};
  });
  $('tbl').tHead.innerHTML='<tr>'+head.map(h=>`<th>${h}</th>`).join('')+'</tr>';
  $('tbl').tBodies[0].innerHTML=calc.map(r=>`<tr>
    <td class="num">${esc(r.p)}</td><td class="num" style="color:var(--enter)">${r.e}</td>
    <td class="num" style="color:var(--exit)">${r.x}</td>
    <td class="num" style="color:${r.net>=0?'var(--green)':'var(--red)'}">${r.net>=0?'+':''}${r.net}</td>
    <td class="num"><b>${r.tot}</b></td>
    <td><div class="inline-bar"><i style="width:${r.tot/max*100}%"></i></div></td>
  </tr>`).join('') || '<tr><td colspan="6" style="color:var(--dim)">暂无时段数据</td></tr>';
  const g=P.groups||{}, ph=P.peak_hour||{};
  $('mini').innerHTML=`
    <div class="panel"><div class="k">建议小车位（轿车 / SUV）</div><div class="v num" style="color:var(--blue)">${(g.small&&g.small.recommended_slots)||0}</div><div class="k">占比 ${(g.small&&g.small.share_pct)||0}%</div></div>
    <div class="panel"><div class="k">建议大车位（货车 / 客车）</div><div class="v num" style="color:var(--amber)">${(g.large&&g.large.recommended_slots)||0}</div><div class="k">占比 ${(g.large&&g.large.share_pct)||0}%</div></div>
    <div class="panel"><div class="k">规划用地（含通道）</div><div class="v num" style="color:var(--cyan)">${P.total_area_sqm||0}<span style="font-size:12px;color:var(--muted)"> ㎡</span></div><div class="k">通道系数 ${P.aisle_factor}</div></div>
    <div class="panel"><div class="k">高峰小时通行</div><div class="v num" style="color:var(--violet)">${ph.throughput||0}<span style="font-size:12px;color:var(--muted)"> 辆次</span></div><div class="k">${esc(ph.period||'-')}</div></div>`;
  const warns=(P.zones&&P.zones.warnings)||[];
  $('hints').innerHTML=warns.length?'<b>规划提示 · </b>'+warns.map(esc).join(' &nbsp;·&nbsp; '):'<b>规划提示 · </b>当前分区配置未见异常。';
}

function renderAll(){ renderKPI(); renderBars(); renderDonut(); renderHeat(); renderSupply(); renderZoneCards(); renderTable(); }

/* ============ 场地配置表单 ============ */
function collectZones(){
  return [...document.querySelectorAll('#zoneRows .zrow')].map((d,i)=>({
    id:d.dataset.id||'Z'+(i+1),
    name:d.querySelector('.z-name').value.trim(),
    classes:[...d.querySelectorAll('.z-cls:checked')].map(x=>x.value),
    slots:parseInt(d.querySelector('.z-slots').value||'0',10),
    note:d.querySelector('.z-note').value.trim()
  }));
}
function renderZoneForm(zones){
  $('zoneRows').innerHTML=(zones||[]).map((z,i)=>`<div class="zrow" data-id="${esc(z.id||('Z'+(i+1)))}">
    <div class="r1"><input type="text" class="z-name" value="${esc(z.name)}" placeholder="分区名称">
      <input type="number" class="z-slots" min="0" step="1" value="${n(z.slots)}" title="实有车位"></div>
    <div class="chks">${CLS.map(c=>`<label><input type="checkbox" class="z-cls" value="${c}" ${(z.classes||[]).indexOf(c)>=0?'checked':''}>${esc(CN[c]||c)}</label>`).join('')}</div>
    <div class="r2"><input type="text" class="z-note" value="${esc(z.note||'')}" placeholder="备注（选填）">
      <button class="btn danger del">删除</button></div>
  </div>`).join('') || '<div class="hintbox">暂无分区，点「+ 添加分区」新增。</div>';
  document.querySelectorAll('#zoneRows .del').forEach(b=>b.onclick=()=>{
    const cur=collectZones(); cur.splice([...document.querySelectorAll('#zoneRows .zrow')].indexOf(b.closest('.zrow')),1);
    renderZoneForm(cur); setMsg(['已删除分区，记得点「保存场地配置」'],'info');
  });
}
function openDrawer(){ editing=true; $('drawer').classList.add('on'); $('mask').classList.add('on'); }
function closeDrawer(){ editing=false; $('drawer').classList.remove('on'); $('mask').classList.remove('on'); }
$('btnZones').onclick=openDrawer; $('btnClose').onclick=closeDrawer; $('mask').onclick=closeDrawer;
document.addEventListener('keydown',e=>{ if(e.key==='Escape') closeDrawer(); });
$('addZone').onclick=()=>{
  const cur=collectZones();
  cur.push({id:'Z'+Date.now().toString().slice(-6),name:'新分区 '+(cur.length+1),classes:[CLS[0]],slots:0,note:''});
  renderZoneForm(cur); setMsg(['已新增分区，记得点「保存场地配置」'],'info');
};
$('resetZones').onclick=()=>loadZones(['已放弃修改，还原为上次保存的配置']);
$('saveZones').onclick=async()=>{
  const payload={site_name:$('siteName').value.trim(),zones:collectZones()};
  try{
    const r=await fetch('/api/parking_zones',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const d=await r.json();
    if(!d.ok){ setMsg(['保存失败：'+(d.error||'未知错误')],'err'); return; }
    setMsg(['已保存场地配置'].concat(d.warnings||[]),'ok');
    await loadZones(['已保存场地配置'].concat(d.warnings||[]));
    await refreshData();
  }catch(err){ setMsg(['保存失败：'+err],'err'); }
};

/* ============ 启动 ============ */
(async function init(){
  applyTheme();
  await loadZones();
  await refreshData();
})();
</script>
</body></html>"""


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
