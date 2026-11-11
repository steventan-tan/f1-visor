# 历史文件与实验记录 / Source history

本页记录 2026-11-11 补充提供的历史文件。经作者授权，原位置的文件现已改为统一工作流或兼容入口；修改前源码与输出归档在作者本地 `.local-history/pre-alignment-sources.zip`。本页及校验清单描述的是修改前快照。历史输出是旧 Notebook 保存的记录，没有用原数据重新评测，也没有据此给当前部署权重背书。

## 文件迁移

| 原文件 | 原用途 / 发现 | 整理后入口 |
| --- | --- | --- |
| `f1_image_collect.ipynb` | Edge 搜索 Google/Bing；含网页 `eval()`、格式后缀不一致、重复下载日志；首格说明文字误标成代码 | `collect_images.py`、[采集说明](COLLECTION.md) |
| `f1-aimodel.ipynb` | 初始 EfficientNet-B0 / ResNet18 分类器、中心裁剪、按验证 AP 选模型；后续单元使用未定义的 `evaluate_collect` 名称，依赖交互历史 | `train.py` 的单一训练入口，保留来源说明 |
| `f1-aimodel-v2.ipynb` | Dropout、AMP、验证损失早停，并重新加载最佳模型 | 统一到 `train.py` 的早停与检查点选择 |
| `f1-aimodel-v3.ipynb` | 自适应池化、等比填充；损坏图片被替换成带原标签的灰图；声明早停参数却未执行早停/最佳检查点保存 | `f1visor/vision.py` 与 `train.py`，坏图明确报错 |
| `image_prediction.py` | 从 v3 抽出的随机图片测试，依赖 Notebook 全局变量 | `detect_video.py --image` / `--image-dir --seed` |
| `evaluation_plots.py` | 旧版依赖 `OUT_DIR`、`test_set` 等全局变量，部分名称在导入前使用 | 根目录同名独立命令，读取保存的预测与元信息 |
| `camera_test.py` | 初始架构的摄像头测试、EMA、按帧计数、截图 | `detect_video.py --camera 0 --snapshots data/cam_snaps` |

旧摄像头脚本的模型键名和中心裁剪不能直接用于当前自适应池化权重；因此不复制另一套模型定义。新版显示未经 EMA 平滑的模型概率和实际帧率；树莓派触发仍由独立的持续时间/冷却逻辑负责。截图保存原始帧，不把屏幕文字烧进后续可用的图片。

## 保存的历史结果

以下均为**使用各自验证集选定阈值后的测试结果**，不是这次整理产生的新成绩。类别顺序在三个 Notebook 输出中均为 `clean=0, stain=1`。

| 历史版本 | 训练样本数（clean / stain） | 测试样本数（clean / stain） | 阈值 | 测试准确率 | stain 召回率 |
| --- | --- | --- | --- | --- | --- |
| 初版 | 23 / 114 | 6 / 26 | 0.97216796875 | 81.25% | 76.92% |
| v2 | 23 / 114 | 6 / 26 | 0.91162109375 | 93.75% | 92.31% |
| v3 | 69 / 133 | 16 / 29 | 0.94921875 | 93.33% | 89.66% |

初版证据来自零基 cell 7、15、17；v2 来自 cell 2、6；v3 来自 cell 1、2、4、5。v3 划分日志共 289 张：训练 202、验证 42、测试 45。没有原始图片、分割清单和逐张历史预测来独立核验这些记录。

v2 同时打印过 `Test acc: 1.0`，这是 argmax 分类结果；使用选定阈值后是 93.75%。v3 的 `Final Test acc: 0.955555...` 同样是 argmax 结果，阈值分类报告是 93.33%。两种决策规则不能混写。`0.98` 是验证召回目标，不是准确率，也不是已经实现的测试召回率。

各版本的数据量、预处理和模型选择规则不同，不能据此宣称 v2 一定优于 v3。现有 `best_safe.pt` 也没有能与这些输出一一对应的训练记录；不把上述成绩写成它的模型指标。

## 当前整合版本的评估

新训练会保存 `predictions.csv`、包含准确率的 `history.csv`、模型元信息和 `metrics.json`。运行：

```bash
python -m pip install -r requirements-analysis.txt
python evaluation_plots.py --run runs/experiment-01 --data data/split
```

输出损失/准确率曲线、PR、ROC、混淆矩阵、概率分布、分类报告和难例列表。`--data` 可选，提供后增加难例图片页。阈值读取验证阶段保存的值，不在测试集上重新调参；PR 图的阈值点用该阈值的精确分类结果绘制。

与旧脚本相比，省去小样本下不稳定的 KDE 曲线，保留直方图。历史 `.npy` 数组及逐张预测未提供，不能由分类报告反推出真实 PR/ROC 曲线；旧日志不伪装成新训练输出。

修改前快照的文件校验值及选定输出见 [source_inventory.json](history/source_inventory.json)。它不包含个人电脑路径、堆栈或原始图片。
