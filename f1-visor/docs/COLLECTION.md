# 图片采集 / Image collection

`collect_images.py` 整理自作者提供的 `f1_image_collect.ipynb`。原 Notebook 使用 Edge + Selenium 搜索 Google/Bing，再并行下载图片。保存的日志中 Google 返回 0 张，Bing 有候选图片；新版保留 Bing 搜索路径，并支持自行提供图片 URL 清单。

## 1. 搜索候选图片

安装 Microsoft Edge，然后在项目虚拟环境中运行：

```bash
python -m pip install -r requirements-collect.txt
python collect_images.py search --query "F1 helmet cam view" --query "Formula 1 cockpit view helmet" --limit 50 --output data/candidates.jsonl
```

Selenium 管理 Edge 驱动，首次运行可能需要下载对应驱动。搜索仅保存候选 URL，不下载图片；输出文件已存在时会拒绝覆盖。关键词可重复传入，`--limit` 是每个关键词的候选上限，不是保证成功下载数量。

搜索依赖 Bing 的网页结构。没有结果、网络限制或页面变化时会报错；不绕过验证码或访问限制。新版搜索没有在本次整理中联网实测，离线解析测试不等于搜索引擎可用性验证。可以改用下面的 URL 清单入口。

## 2. 下载 URL 清单

候选文件为 UTF-8 JSONL，一行一张图片。也可以直接创建自己的清单：

```json
{"image_url":"https://example.org/photo.jpg","source_page":"https://example.org/article","query":"helmet view","license_status":"unreviewed"}
```

示例域名只是格式演示。检查实际来源页面、图片相关性与使用条件，保留适合项目的候选，然后执行：

```bash
python collect_images.py download --input data/candidates.jsonl --output data/unreviewed
```

默认要求至少 800×600 像素、最多 10 MiB 下载内容和 2500 万解码像素。可用 `--min-width`、`--min-height`、`--max-mb` 调整前三项。默认每次请求处理后间隔 1 秒，按顺序下载，避免原并发下载的重复写入问题。

- 只接受 HTTP(S)；拒绝内嵌账号和本地/私有网络地址，逐跳检查重定向。
- 使用连接/读取超时和下载大小限制，校验真实图片格式及可解码性。
- 按真实格式保存 `.jpg` / `.png` / `.webp` / `.bmp`，不再把 PNG 内容伪装成 JPEG。
- SHA-256 命名并去重，以临时文件完成写入后再替换目标路径。
- `manifest.jsonl` 记录来源页、图片 URL、搜索词、时间、哈希、尺寸及失败原因。
- 再次运行相同命令会校验已成功文件并跳过，失败项会重新尝试。有失败时命令返回非零，已成功文件保留。不要同时向同一输出目录运行多个采集进程。

HTTP 状态错误、过小图片或格式不合格都会进入失败日志。若手动编辑损坏了清单，修复 JSONL 后再恢复；不会静默丢弃无法解析的记录。下载器不读取本地 `.netrc` 凭据或环境代理设置，仅用于公开图片。

## 3. 人工标注后再训练

采集器不根据搜索词自动赋予 `clean` 或 `stain` 标签，清单中初始 `label` 为 `null`。将人工确认的图片复制到 `data/raw/clean/` 或 `data/raw/stain/`，保存来源清单，再运行：

```bash
python prepare_data.py --source data/raw --output data/split
python train.py --data data/split --output runs/experiment-01
```

相同场景/视频连续帧应按拍摄会话整体划分，避免泄漏到训练与测试两侧。搜索结果可下载不等于拥有重新分发许可；原图片仍不随公开源码包发布。采集日志也不能证明旧模型实际使用了其中哪些图片。

## Technical references

- [Selenium Edge support](https://www.selenium.dev/documentation/webdriver/browsers/edge/)
- [Requests streaming, timeouts and response handling](https://requests.readthedocs.io/en/latest/user/quickstart/)

The tool separates discovery from download, preserves source metadata and leaves labeling to a human. Offline tests cover parsing, redirects, size limits, format validation, deduplication and resume behavior; live search availability is not asserted.
