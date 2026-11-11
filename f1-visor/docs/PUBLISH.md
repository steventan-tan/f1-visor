# 上传到 GitHub

建议仓库名：`f1-visor`。About 可以使用：

> AI-assisted visor film-changing prototype with EfficientNet-B0, Raspberry Pi vision and Arduino Nano Bluetooth control.

建议 Topics：`computer-vision`、`raspberry-pi`、`arduino`、`pytorch`、`wearable`、`interaction-design`、`prototyping`。

## 最方便的方式：上传源码包中的内容

1. 解压交付的 `f1-visor-github.zip`。
2. 在 GitHub 创建空仓库。不要重复生成 README 或 License，本项目已包含。
3. 上传解压出的 `f1-visor/` **里面的文件**，使 `README.md` 直接位于仓库根目录。不要把 ZIP 本身作为唯一文件上传。
4. 确认 `.github/workflows/checks.yml`、`.gitignore`、`.gitattributes` 一并上传。在 macOS Finder 可按 `Command + Shift + .` 显示隐藏文件。
5. 提交后检查 README 图片、视频链接及 Actions 运行结果。这里提供了 CI 配置，未预先声称云端运行成功。

只上传这个整理后的目录；上一级包含兼容入口、权重与本地修改前归档，不属于公开仓库。

## 使用 Git

在整理后的 `f1-visor/` 目录执行，替换示例仓库地址：

```bash
git init
git add .
git status --short
git commit -m "Publish F1 visor research prototype"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/f1-visor.git
git push -u origin main
```

`.gitignore` 排除了模型权重、模型侧边 JSON、数据集、训练输出、虚拟环境和 `config.local.json`。检查暂存列表中没有个人配置或数据。源码包使用相同范围，不包含原始 PDF，只包含一张项目原型页面预览。

## 作品集展示建议

README 首页已放置设计问题、原型图、演示视频、系统关系和代码入口。仓库配套项目说明时，展示「设计问题 → 视觉判断 → 自动/手动交互 → 实物演示 → 限制」即可。不要将目标 recall 0.98 写成“识别准确率 98%”；也不要把合成数据自检写成真实评测结果。

若之后整理出有授权的训练数据和可复现测试报告，再将权重与配套 JSON 作为独立 Release 资产发布，并更新模型说明。现有源码可以先公开，权重不受本仓库 MIT 自动覆盖。
