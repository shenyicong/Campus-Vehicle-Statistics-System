"""全局配置的一致性约束：类别顺序是检测 / 标注 / 报表 / 看板的唯一准绳。"""
import config


def test_class_order_matches_trained_model():
    assert config.CLASSES == ["sedan", "suv", "truck", "bus"]


def test_chinese_labels_cover_every_class():
    assert set(config.CLASS_CN) == set(config.CLASSES)


def test_project_paths_are_absolute():
    assert config.PROJECT_DIR
    assert config.DATA_DIR.startswith(config.PROJECT_DIR)
    assert config.YOLO_ONNX.startswith(config.PROJECT_DIR)


def test_thresholds_are_in_valid_range():
    assert 0.0 < config.CONF_THRES <= 1.0
    assert 0.0 < config.IOU_THRES <= 1.0
    assert 0.0 <= config.LINE_Y <= 1.0
