from copy import deepcopy


EXPERIMENTS = (
    {
        "id": "rlc_series",
        "name": "RLC 串联电路幅频特性",
        "summary": "通过扫频观察串联谐振附近的电流或电阻电压峰值，并分析品质因数。",
        "safety": "接线或更换元件前断电；从较小输入幅值开始，出现发热、异味或异常读数立即断电。",
        "steps": (
            {"title": "核对元件", "detail": "记录 R、L、C 标称值，确认信号源、示波器与电路共地。"},
            {"title": "完成串联接线", "detail": "在断电状态下连接 R、L、C 和测量端，先请同伴复核极性与公共地。"},
            {"title": "低幅值上电", "detail": "设置较小正弦输入和限流条件，确认波形稳定后再开始扫频。"},
            {"title": "扫频记录", "detail": "在预估谐振频率附近缩小频率步长，记录频率、电阻电压或电流及相位。"},
            {"title": "分析结果", "detail": "用峰值频率估计谐振频率；以半功率点带宽估算 Q 值，并注明测量误差来源。"},
        ),
        "data_columns": ("频率 Hz", "电阻电压 V", "电流 A", "相位差 °"),
    },
    {
        "id": "rlc_transient",
        "name": "RLC 暂态过程",
        "summary": "观察开关动作后的阻尼振荡或非振荡响应，比较电阻改变对暂态过程的影响。",
        "safety": "切换开关和调整元件前先断电；确认电容额定电压，避免带电改线与电容反接。",
        "steps": (
            {"title": "设定初始条件", "detail": "断电接线，确认电容初始电压与开关位置，检查示波器探头地线。"},
            {"title": "配置采样", "detail": "设置合适的时基、触发沿和量程，使完整暂态波形位于屏幕范围内。"},
            {"title": "执行单次切换", "detail": "仅在接线确认后切换开关，保存一次完整波形，避免反复带电插拔。"},
            {"title": "改变阻尼条件", "detail": "在断电后改变电阻，重复测量并标记欠阻尼、临界阻尼或过阻尼特征。"},
            {"title": "整理参数", "detail": "记录时间、电容电压或电流峰值；比较周期、衰减和电阻变化的关系。"},
        ),
        "data_columns": ("时间 ms", "电容电压 V", "电流 A", "实验条件"),
    },
    {
        "id": "wheatstone_bridge",
        "name": "惠斯通电桥测量电阻",
        "summary": "调节桥臂使检流计接近零位，并由平衡条件计算待测电阻。",
        "safety": "接线前断电；电桥平衡前使用较小电源电压，避免检流计过偏和待测电阻过热。",
        "steps": (
            {"title": "识别桥臂", "detail": "核对比例臂、标准电阻、待测电阻和检流计端子，记录各电阻标称值。"},
            {"title": "断电接线", "detail": "按电桥拓扑连接四个桥臂和检流计，确认电源与检流计没有接反或短接。"},
            {"title": "低压粗调", "detail": "从低电压开始，逐步调节标准电阻或比例臂，使检流计偏转减小。"},
            {"title": "平衡读数", "detail": "在零位附近细调，记录比例臂和标准电阻读数，重复至少三次。"},
            {"title": "计算与误差", "detail": "按实验接线对应的平衡公式计算待测电阻，并说明接触电阻和读数分辨率影响。"},
        ),
        "data_columns": ("比例臂 R1 Ω", "比例臂 R2 Ω", "标准电阻 R3 Ω", "待测电阻 Rx Ω"),
    },
)


def experiment_ids() -> set[str]:
    return {item["id"] for item in EXPERIMENTS}


def get_experiment(experiment_id: str) -> dict | None:
    for experiment in EXPERIMENTS:
        if experiment["id"] == experiment_id:
            return deepcopy(experiment)
    return None


def all_experiments() -> list[dict]:
    return [deepcopy(experiment) for experiment in EXPERIMENTS]
