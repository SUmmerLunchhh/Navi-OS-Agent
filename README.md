#Navi-OS-Agent
> *"Let's all love lain."*
<p align="center">
<img src="https://github.com/SUmmerLunchhh/AAA-/blob/main/imgs/%E5%B1%8F%E5%B9%95%E6%88%AA%E5%9B%BE%202026-09-27%20174114.png" height="300">
</p>
**Navi-OS-Agent** 是一款向经典的 《Serial Experiments Lain》（玲音）中 **Navi** 操作系统致敬的桌面 AI 智能体项目。本项目基于 Python、PyQt6 构建，融合了语音识别、TTS 语音合成以及动态本地代码执行能力。

---
##  项目结构

```text
Navi-OS-Agent/
├── .github/workflows/   # GitHub Actions 自动打包工作流
├── main.py              # 主程序入口（PyQt6 界面与逻辑）
├── Navi.ico             # 应用图标
├── bg.png               # 背景静态资源
├── ah3ha-80cp2.svg      # SVG 矢量渲染资源
└── nav_config.json      # 配置文件
```
# 获取构建版本 [📥Downloads](https://github.com/SUmmerLunchhh/Navi-OS-Agent/releases/download/main/Navi-OS-Agent-Windows.zip)
如果你不想在本地从源码运行，可以直接前往右侧的[Releases](https://github.com/SUmmerLunchhh/Navi-OS-Agent/releases/tag/main)页面，下载最新编译好的 Windows 独立压缩包（Navi-OS-Agent-Windows.zip），解压后即可直接双击exe文件运行。

# 本地运行与开发
如果你希望在本地运行或调试源码，请按以下步骤操作：

1.克隆仓库：

```Bash
git clone [https://github.com/SUmmerLunchhh/Navi-OS-Agent.git](https://github.com/SUmmerLunchhh/Navi-OS-Agent.git)
cd Navi-OS-Agent
```
2.安装依赖：
```Bash
pip install PyQt6 openai SpeechRecognition pyttsx3 pyinstaller
```
3.运行程序：
```Bash
python main.py
```

