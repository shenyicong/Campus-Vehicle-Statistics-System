# 用 D:\car 的车型图片合成"模拟校门监控"测试视频
import os
import glob
import sys
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


def main():
    imgs = sorted(glob.glob(os.path.join(config.SOURCE_DIR, "*.jpg")))
    if not imgs:
        raise SystemExit("未找到图片: " + config.SOURCE_DIR)
    os.makedirs(os.path.dirname(config.TEST_VIDEO), exist_ok=True)

    sample = cv2.imread(imgs[0])
    h, w = sample.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    fps = 10
    vw = cv2.VideoWriter(config.TEST_VIDEO, fourcc, fps, (w, h))
    frames_per_img = 4
    for p in imgs:
        img = cv2.imread(p)
        if img is None:
            continue
        img = cv2.resize(img, (w, h))
        for k in range(frames_per_img):
            dx = int(8 * np.sin(k / frames_per_img * np.pi))
            dy = int(6 * np.cos(k / frames_per_img * np.pi))
            M = np.float32([[1, 0, dx], [0, 1, dy]])
            shifted = cv2.warpAffine(img, M, (w, h))
            vw.write(shifted)
    vw.release()
    print("已生成测试视频:", config.TEST_VIDEO, " 帧数约", len(imgs) * frames_per_img)


if __name__ == "__main__":
    main()
