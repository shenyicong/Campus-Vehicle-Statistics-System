# 视频输入: 本地文件 或 RTSP 实时流（一行切换）
import cv2


def open_source(use_rtsp=False, rtsp_url="", video_path=""):
    src = rtsp_url if use_rtsp else video_path
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise IOError(f"无法打开视频源: {src}")
    return cap


def read_frame(cap):
    ok, frame = cap.read()
    return ok, frame
