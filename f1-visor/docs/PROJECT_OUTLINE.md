# 项目大纲与实现对照

对照依据：作者提供的 `f1.pdf`，第 1 页项目目标、第 3 页技术研究、第 4 页实现过程、第 5 页原型、第 6 页交互与后续方向。核对日期：2026-11-11。

**结论：现有项目符合“视觉判断遮挡 + 自动卷膜 + 蓝牙按钮手动触发”的核心原型大纲。它是整图二分类驱动的交互原型，不是污渍定位系统，也不是具备在线学习或远程管理的完整产品。**

## 主线与代码入口

| 大纲环节 | 当前实现 | 证据与状态 |
| --- | --- | --- |
| 问题：泥点、水渍影响头盔视野 | README 的设计问题、原型图、演示视频 | 对应 PDF 第 1、5、6 页；设计与原型证据 |
| 图片收集与训练数据 | `collect_images.py` → 人工标注 → `prepare_data.py` | 来源记录、文件校验、去重与划分有自动测试；新版在线搜索未实测 |
| 选择模型并训练 | `train.py`、`notebooks/training.ipynb` | EfficientNet-B0、自适应池化、迁移学习、CUDA AMP、早停；对应第 4 页 |
| 电脑测试与阈值选择 | `detect_video.py`、`evaluation_plots.py` | 阈值来自验证集；测试输出和导出模型均可复现；合成数据流程已测试 |
| 导出并部署至树莓派 | `export_model.py`、模型 `.pt` / `.json`、`config.local.json` | 模型尺寸/类别/阈值/哈希随模型传递；当前本地原始 FP32 模型可加载 |
| 视觉触发舵机卷膜 | `detect.py`、`DetectionGate`、`ServoController` | 持续识别、动作互斥、冷却、异常停止；没有卷膜完成的机械反馈 |
| Arduino Nano 蓝牙按钮 | `firmware/nano_button/nano_button.ino` → HC-06 → 树莓派串口 | D2 按钮、9600 UART、`S` / `s`；作者确认原型链路已验证，参考程序逻辑有测试 |
| 装配、展示、验证 | `servo_test.py`、硬件文档、systemd 模板、演示视频 | 对应第 4–6 页；新整理控制器仍需装配后回归 |

`clean` 表示视野未被目标污渍遮挡，`stain` 表示泥点、水渍等造成的遮挡。现在只输出这两类，不分别判断“泥”和“水”。F1 赛道/驾驶舱照片仅是候选素材；没有污渍的赛车照片不能因为搜索关键词而标成 `stain`。采样视角应与原型摄像头保持一致。

当前开源交付范围是原型的软件。PDF 中的产品建模有展示图，但这批文件没有机械 CAD、打印模型、卷轴尺寸或完整装配图，不能宣称仅凭仓库就能原样制造机械装置。

## PDF 中需要收窄的表述

第 3 页技术调研写到了 AI 相机的一般潜力，但以下能力没有在本仓库实现，不应作为当前原型成果列出：

| 原表述含义 | 与当前实现的差异 | 适合当前作品集的表述 |
| --- | --- | --- |
| 直接识别污渍形状、位置、范围 | 没有边框、分割掩码或面积输出 | 对摄像头画面进行 clean / stain 二分类 |
| 随环境持续学习、自动调整识别 | 没有在线训练、漂移检测或自动校准 | 离线训练后部署固定模型；环境变化需要重新评估 |
| 支持后台/远程管理 | 只有本地日志与 systemd，没有远程监控平台 | 支持本地终端状态观察和运行日志 |
| 高准确率、少误报、持续可靠运行 | 只有小样本历史实验记录，缺少当前部署分辨率下的独立实测 | 在既有原型上探索可行性，后续量化误触发、漏检与时延 |
| 实时分析 | 循环推理已实现，但没有目标树莓派端到端时延实测 | 持续采集并分析图像；设备侧实时性仍需测量 |

可替换第 3 页 AI camera 能力段的英文文案：

> The prototype uses a camera and an offline-trained EfficientNet-B0 model to classify each frame as clean or stained. A sustained positive result requests servo-driven film advancement, while a Bluetooth button provides a separate manual trigger. This implementation does not localize stains, learn online or provide a remote monitoring platform. Recognition quality and end-to-end latency require evaluation under the intended camera and lighting conditions.

第 6 页的混合传感、其他应用场景与更高可靠性属于 Future Work，可以保留为研究方向。没有为了补齐愿景而擅自加入远程平台、传感器或在线训练。

## 当前闭环与模型衔接

```text
收集候选图片 → 人工标注与场景划分 → 训练 → 验证阈值 → 留出测试
                                                     ↓
                                   导出同名 .pt + .json
                                                     ↓
摄像头 → 概率判断 → 持续时间门限 ────────────────→ 共用舵机入口
Nano 按钮 → HC-06 → 树莓派串口 ────────────────→ 共用舵机入口
                                                     ↓
                                          定时转动 → 中位停止
```

这是“检测—动作”的原型流程。由于没有编码器/行程开关，软件知道发出了动作，不能证明膜已推进指定长度或视野已恢复。手动与自动路径共用树莓派、供电和执行器；手动按钮不是独立硬件故障保护。

建议先完成 224 像素实验，统一电脑测试与树莓派部署：

```bash
python train.py --data data/split --output runs/pi-224-01 --image-size 224
python evaluation_plots.py --run runs/pi-224-01 --data data/split
python export_model.py --checkpoint runs/pi-224-01/best.pt --output models/pi-224-01.pt
python detect_video.py --model models/pi-224-01.pt --camera 0
```

然后在 `config.local.json` 中将 `model` 改为 `models/pi-224-01.pt`，把同名 JSON 一起部署。不要训练完新模型后仍使用默认旧权重，也不要把历史 384 像素实验阈值直接填到另一份 224 像素模型上。

## 提交前真正剩余的证据

软件整理不能代替以下实物测量；它们是后续验证项，不是源码缺少的功能承诺：

| 验证项 | 应记录的结果 |
| --- | --- |
| 与目标视角一致的 clean / 泥点 / 水渍 / 反光样本 | 来源、类别、拍摄场景、会话划分与数量 |
| 部署分辨率下的识别 | 误触发率、漏检、精确率/召回率、困难样本 |
| 自动卷膜 | 从出现遮挡到动作的时间、推进效果、污渍持续时是否重复卷动 |
| 手动按钮与自动判断同时出现 | 单次动作互斥、没有基于旧画面的紧接重复动作 |
| 树莓派部署 | OS/架构、内存占用、推理时间、运行时长与功耗 |
| 断线和停止 | 相机断线、蓝牙断线、Ctrl+C/systemd stop/restart 后的行为 |

作品集可写“实现了视觉识别与手动触发两条路径，并完成原型演示”；不要写成“所有情况下都能保障驾驶安全”。历史成绩、作者原型验证和本次软件测试分别见 [HISTORY.md](HISTORY.md)、[HARDWARE.md](HARDWARE.md)、[VERIFICATION.md](VERIFICATION.md)。
