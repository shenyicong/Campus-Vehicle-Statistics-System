"""生成无需启动 Flask 服务的数据驾驶舱静态预览快照。

把 /api/stats、/api/parking_zones、/api/parking_plan 三份数据内联进页面，
并用 mock fetch 替换接口请求，因此 file:// 直接打开即可看到完整视图。

用法:
  python tools/make_dashboard_snapshot.py
  python tools/make_dashboard_snapshot.py --out data/reports/dashboard_preview.html

注意: 快照是只读的，场地车位设置里的「保存」会返回提示，
      真正修改配置请运行 python web_dashboard.py 后在浏览器打开。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import web_dashboard as wd  # noqa: E402


def build(out_path):
    client = wd.app.test_client()
    data = {
        "stats": client.get("/api/stats").get_json(),
        "zones": client.get("/api/parking_zones").get_json(),
        "plan": client.get("/api/parking_plan").get_json(),
    }
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

    inject = """<script>
window.__SNAP__ = %s;
window.fetch = function(url, opts){
  if(opts && opts.method === 'POST'){
    return Promise.resolve({json:function(){return Promise.resolve({
      ok:false, error:'这是静态预览快照，不能保存。请运行 python web_dashboard.py 后在浏览器中修改。'
    });}});
  }
  var key = url.indexOf('/api/stats') >= 0 ? 'stats'
          : (url.indexOf('/api/parking_zones') >= 0 ? 'zones' : 'plan');
  return Promise.resolve({json:function(){return Promise.resolve(window.__SNAP__[key]);}});
};
</script>
""" % payload

    banner = (
        "<div style=\"position:sticky;top:0;z-index:50;background:#B45309;color:#fff;"
        "padding:7px 22px;font-size:12px;text-align:center;letter-spacing:.3px\">"
        "静态预览快照 · 数据已内联，无需启动服务；场地车位设置中的「保存」在此页不可用</div>"
    )
    html = wd.HTML
    html = html.replace("</head>", inject + "</head>", 1)
    html = html.replace("<body>", "<body>" + banner, 1)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    z = data["plan"]["zones"]
    print("静态快照:", out_path, os.path.getsize(out_path), "bytes")
    print("内联数据: 进 %d / 出 %d / 总通行 %d 辆次" % (
        sum(data["stats"]["total"]["enter"].values()),
        sum(data["stats"]["total"]["exit"].values()),
        sum(data["stats"]["total"]["enter"].values())
        + sum(data["stats"]["total"]["exit"].values())))
    print("场地: %s | 实有车位 %d | 需求 %d | 余量 %+d | 饱和度 %s%%" % (
        z["site_name"], z["supply_total"], z["required_total"],
        z["gap_total"], z["saturation_pct"]))
    print("小时桶:", data["plan"]["hours"], " 高峰:", data["plan"]["peak_hour"])
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(config.REPORT_DIR, "dashboard_preview.html"))
    args = ap.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
