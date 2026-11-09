# -*- coding: utf-8 -*-
"""
把本地 YOLO 数据集 ZIP 上传到 Ultralytics Platform（官方 REST API）。

流程（官方文档 https://docs.ultralytics.com/zh/platform/api）：
  1. POST /api/datasets                         创建数据集（固定类别顺序）
  2. POST /api/upload/signed-url               申请签名直传 URL
  3. PUT  uploadUrl                            把 ZIP 直传到云存储
  4. POST /api/upload/complete                 完成上传会话（带 MD5 校验）
  5. POST /api/datasets/{owner}/{ds}/ingest    触发解析导入
  6. GET  /api/datasets/{owner}/{ds}           轮询直到处理完成

用法：
  # 离线自检，只需校验 ZIP，不需要密钥
  python tools/upload_dataset_platform.py --check-only

  # 正式上传（推荐：密钥放本地文件，不出现在对话 / 命令行历史里）
  python tools/upload_dataset_platform.py --api-key-file D:\\YOLO\\platform_api_key.txt

  # 也可用环境变量或命令行参数（脚本不会回显密钥内容）
  set ULTRALYTICS_API_KEY=ul_xxx && python tools/upload_dataset_platform.py
  python tools/upload_dataset_platform.py --api-key ul_xxxxxxxx...

API Key 在平台 Settings > API Keys > Add Key 创建，格式 ul_ + 40 位十六进制。
安全约定：脚本从不打印、不保存密钥明文；上传记录 JSON 里也不含密钥。
"""

import argparse
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
import zipfile

API = "https://platform.ultralytics.com/api"
UA = "campus-vehicle-uploader/1.0"


def log(step, msg):
    print("[%s] %s" % (step, msg), flush=True)


def request_json(method, path, api_key, body=None, timeout=60):
    """调用平台 JSON API，返回 (status_code, dict)。"""
    url = API + path if path.startswith("/") else path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {
        "Authorization": "Bearer " + api_key,
        "Accept": "application/json",
        "User-Agent": UA,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw)
        except Exception:
            detail = {"raw": raw[:600]}
        return e.code, detail
    except Exception as e:
        return -1, {"error": "%s: %s" % (type(e).__name__, e)}


def check_zip(path):
    """上传前本地校验：完整性、切分、data.yaml、类别 id、空标签。"""
    import collections

    if not os.path.isfile(path):
        raise SystemExit("ZIP 不存在: " + path)
    size = os.path.getsize(path)
    log("校验", "文件 %s  %.2f MB" % (os.path.basename(path), size / 1048576))
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            raise SystemExit("ZIP 损坏，首个坏文件: " + bad)
        names = z.namelist()
        imgs = [n for n in names if n.lower().endswith((".jpg", ".jpeg", ".png"))]
        labs = [n for n in names if n.endswith(".txt")]
        tr = [n for n in imgs if n.startswith("images/train/")]
        va = [n for n in imgs if n.startswith("images/val/")]
        if "data.yaml" not in names:
            raise SystemExit("缺少 data.yaml")
        yaml_text = z.read("data.yaml").decode("utf-8")
        if any(l.startswith("path:") for l in yaml_text.splitlines()):
            raise SystemExit("data.yaml 含本地绝对路径 path:，平台会解析失败")
        cnt = collections.Counter()
        empty = 0
        for n in labs:
            lines = [l for l in z.read(n).decode("utf-8").splitlines() if l.strip()]
            if not lines:
                empty += 1
            for l in lines:
                a = l.split()
                if len(a) != 5:
                    raise SystemExit("标签格式错误 %s: %s" % (n, l))
                cid = int(a[0])
                cnt[cid] += 1
                for v in map(float, a[1:]):
                    if not 0.0 <= v <= 1.0:
                        raise SystemExit("标签坐标未归一化 %s: %s" % (n, l))
    info = {
        "zip": path,
        "bytes": size,
        "md5": hashlib.md5(open(path, "rb").read()).hexdigest(),
        "images": len(imgs),
        "labels": len(labs),
        "train": len(tr),
        "val": len(va),
        "empty_labels": empty,
        "annotations": sum(cnt.values()),
        "class_ids": dict(sorted(cnt.items())),
        "data_yaml": yaml_text.strip(),
    }
    log("校验", "ZIP 完整 | 图片 %d 标签 %d | train %d val %d | 标注 %d | 空标签 %d"
        % (len(imgs), len(labs), len(tr), len(va), info["annotations"], empty))
    log("校验", "类别 id 分布 %s" % info["class_ids"])
    log("校验", "MD5 %s" % info["md5"])
    if len(imgs) != len(labs):
        raise SystemExit("图片数与标签数不一致")
    if not tr or not va:
        raise SystemExit("train / val 必须都有图片，否则数据集不会 Ready")
    if max(cnt.keys()) != 3 or len(cnt) != 4:
        raise SystemExit("类别 id 必须是 0/1/2/3 四类，实际: %s" % dict(cnt))
    return info


def main():
    p = argparse.ArgumentParser(description="上传 YOLO 数据集 ZIP 到 Ultralytics Platform")
    p.add_argument("--zip", default=r"D:\YOLO\car_dataset_v2_ultralytics_platform.zip")
    p.add_argument("--api-key", default=os.environ.get("ULTRALYTICS_API_KEY", ""))
    p.add_argument("--api-key-file", default="", help="从本地文件读密钥（推荐，避免明文出现在对话/命令历史）")
    p.add_argument("--owner", default="rabbit-42")
    p.add_argument("--dataset", default="campus-vehicle-4class-v2")
    p.add_argument("--name", default="Campus Vehicle 4-Class v2")
    p.add_argument("--classes", default="轿车,SUV,货车,客车")
    p.add_argument("--visibility", default="private", choices=["private", "public"])
    p.add_argument("--description", default=(
        "校园车辆四类检测数据集 v2：698 张 640x640 图像，train 558 / val 140；"
        "在原 298 张单车特写基础上补充 260 张多车同框与 140 张远景小目标合成图，"
        "含 142 张不标注硬负样本（玩具车 / 中文贴字），用于改善多车漏检、远景小目标与误检。"
        "类别顺序 0=轿车 / 1=SUV / 2=货车 / 3=客车，与 data.yaml、config.CLASSES 一致。"
    ))
    p.add_argument("--check-only", action="store_true", help="只做本地 ZIP 校验，不联网")
    p.add_argument("--reuse", action="store_true", help="数据集已存在时复用（不重新创建）")
    p.add_argument("--wait", type=int, default=180, help="导入后最长轮询秒数")
    a = p.parse_args()

    info = check_zip(a.zip)
    if a.check_only:
        log("完成", "离线自检通过，未联网、未上传。")
        return 0

    key = (a.api_key or "").strip()
    if a.api_key_file:
        kf = os.path.abspath(a.api_key_file)
        if not os.path.isfile(kf):
            log("错误", "密钥文件不存在: " + kf)
            log("提示", "把 API Key 单独一行存到该文件即可，脚本不会回显内容。")
            return 2
        key = open(kf, encoding="utf-8").read().strip()
        log("鉴权", "已从本地文件读取密钥（长度 %d，内容不回显）" % len(key))
    if not key:
        log("错误", "缺少 API Key。推荐 --api-key-file，或用环境变量 ULTRALYTICS_API_KEY。")
        log("提示", "平台 Settings > API Keys > Add Key 创建，格式 ul_ + 40 位十六进制。")
        return 2
    if not (key.startswith("ul_") and len(key) == 43):
        log("警告", "密钥格式看起来不像官方 ul_ + 40 位十六进制，仍会尝试。")

    owner, ds = a.owner, a.dataset
    classes = a.classes.split(",")

    # 1. 创建数据集（显式给 classNames，锁定 id 顺序，避免平台按名称重排）
    dataset_id = None
    if a.reuse:
        st, r = request_json("GET", "/datasets/%s/%s" % (owner, ds), key)
        dataset_id = (r.get("dataset") or {}).get("id") if isinstance(r.get("dataset"), dict) else r.get("id")
        log("1/6", "复用已有数据集 HTTP %s，id=%s" % (st, dataset_id))
        if not dataset_id:
            log("错误", "复用失败：%s" % json.dumps(r, ensure_ascii=False)[:400])
            return 3
    else:
        body = {
            "dataset": ds,
            "name": a.name,
            "task": "detect",
            "format": "yolo",
            "description": a.description,
            "classNames": classes,
            "visibility": a.visibility,
            # 个人工作区不要传 owner：该字段在 API 里表示「团队工作区标识」，
            # 省略时自动落到 API Key 所属的个人工作区 rabbit-42。
        }
        st, r = request_json("POST", "/datasets", key, body)
        log("1/6", "创建数据集 HTTP %s -> %s" % (st, json.dumps(r, ensure_ascii=False)[:300]))
        if st == 409:
            log("提示", "同名数据集已存在，请加 --reuse 复用，或换 --dataset 名称。")
            return 3
        if st not in (200, 201):
            return 3
        dataset_id = r.get("id")
    if not dataset_id:
        log("错误", "未拿到数据集 id，无法继续。")
        return 3

    # 2. 申请签名直传 URL
    body = {
        "assetType": "datasets",
        "assetId": dataset_id,
        "filename": os.path.basename(a.zip),
        "contentType": "application/zip",
        "totalBytes": info["bytes"],
    }
    st, signed = request_json("POST", "/upload/signed-url", key, body)
    log("2/6", "申请签名 URL HTTP %s" % st)
    if st not in (200, 201) or "uploadUrl" not in signed:
        log("错误", json.dumps(signed, ensure_ascii=False)[:500])
        return 4
    session_id = signed["sessionId"]
    log("2/6", "sessionId=%s  有效期至 %s" % (session_id, signed.get("expiresAt", "?")))

    # 3. PUT 直传（签名 URL 只能用一次，必须带上返回的所有 headers）
    headers = {"Content-Type": "application/zip", "User-Agent": UA}
    headers.update(signed.get("headers") or {})
    payload = open(a.zip, "rb").read()
    req = urllib.request.Request(signed["uploadUrl"], data=payload, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=600, context=ssl.create_default_context()) as resp:
            log("3/6", "ZIP 直传 HTTP %s，已发送 %d bytes" % (resp.status, len(payload)))
    except urllib.error.HTTPError as e:
        log("错误", "直传失败 HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:400]))
        return 5
    except Exception as e:
        log("错误", "直传异常 %s: %s" % (type(e).__name__, e))
        return 5

    # 4. 完成上传会话（带 MD5，平台会与存储对象核对）
    st, comp = request_json("POST", "/upload/complete", key,
                            {"sessionId": session_id, "md5": info["md5"]})
    log("4/6", "完成上传 HTTP %s -> %s" % (st, json.dumps(comp, ensure_ascii=False)[:300]))
    if st not in (200, 201, 204):
        return 6

    # 5. 触发导入（不传 targetSplit，让 ZIP 内 images/train、images/val 生效）
    st, ing = request_json("POST", "/datasets/%s/%s/ingest" % (owner, ds), key,
                           {"sessionId": session_id, "classMapping": {c: i for i, c in enumerate(classes)}})
    log("5/6", "触发导入 HTTP %s -> %s" % (st, json.dumps(ing, ensure_ascii=False)[:300]))
    if st not in (200, 201, 202):
        return 7

    # 6. 轮询数据集详情，等待处理完成
    deadline = time.time() + a.wait
    last = {}
    while time.time() < deadline:
        time.sleep(8)
        st, d = request_json("GET", "/datasets/%s/%s" % (owner, ds), key)
        last = d
        core = d.get("dataset") if isinstance(d.get("dataset"), dict) else d
        prog = core.get("processingProgress") or {}
        state = core.get("status") or core.get("state") or ""
        log("6/6", "轮询 HTTP %s  status=%s  progress=%s"
            % (st, state, json.dumps(prog, ensure_ascii=False)[:160]))
        ic = core.get("imageCount") or core.get("imagesCount") or 0
        done = (not prog) or prog.get("status") in ("done", "complete", "completed") \
            or prog.get("pending", 0) == 0
        # 平台字段名可能与文档略有差异，故只在明确拿到 imageCount 时才要求达到 698
        if st == 200 and done and (not ic or ic >= info["images"]):
            break
    else:
        log("提示", "轮询超时，导入可能仍在后台处理，稍后到平台数据集页查看。")

    core = last.get("dataset") if isinstance(last.get("dataset"), dict) else last
    log("结果", "数据集: https://platform.ultralytics.com/%s/datasets/%s" % (owner, ds))
    log("结果", "imageCount=%s  classNames=%s  splits=%s"
        % (core.get("imageCount"), core.get("classNames"), core.get("splits")))

    out = os.path.join(os.path.dirname(a.zip), "upload_v2_result.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"local": info, "dataset_id": dataset_id, "session_id": session_id,
                   "ingest": ing, "final": core}, f, ensure_ascii=False, indent=2)
    log("完成", "上传记录已保存 " + out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
