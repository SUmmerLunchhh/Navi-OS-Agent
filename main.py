import datetime
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading

from PyQt6.QtCore import QPoint, Qt, QThread, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPalette,
    QPixmap,
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import pyttsx3
import speech_recognition as sr
from openai import OpenAI

# 配置文件保存路径
CONFIG_FILE = 'nav_config.json'


def resource_path(relative_path):
    """获取打包后或开发环境中资源的绝对路径"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# 1. 后台处理线程
class AIWorker(QThread):
    finished_signal = pyqtSignal(dict)

    def __init__(self, client, chat_history):
        super().__init__()
        self.client = client
        self.chat_history = chat_history

    def run(self):
        try:
            response = self.client.chat.completions.create(
                model='deepseek-chat',
                messages=self.chat_history,
                stream=False,
            )
            ai_reply = response.choices[0].message.content
            code_pattern = r'```python\s*(.*?)\s*```'
            matches = re.findall(code_pattern, ai_reply, re.DOTALL)

            if matches:
                python_code = matches[0]
                exec_result = self.execute_dynamic_code(python_code)
                if exec_result['success']:
                    self.finished_signal.emit({
                        'type': 'success',
                        'reply': ai_reply,
                        'msg': f'代码执行成功。输出：\n{exec_result["output"]}',
                    })
                else:
                    self.finished_signal.emit({
                        'type': 'error',
                        'reply': ai_reply,
                        'msg': f'代码报错: {exec_result["error"]}',
                    })
            else:
                self.finished_signal.emit(
                    {'type': 'text', 'reply': ai_reply, 'msg': ''}
                )
        except Exception as e:
            self.finished_signal.emit({
                'type': 'exception',
                'reply': '',
                'msg': f'处理指令发生异常: {str(e)}',
            })

    def execute_dynamic_code(self, code_str):
        success = True
        output = ''
        error_info = ''
        temp_file_path = ''

        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.py', delete=False, encoding='utf-8'
            ) as f:
                f.write(code_str)
                temp_file_path = f.name

            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'

            process = subprocess.run(
                [sys.executable, temp_file_path],
                capture_output=True,
                text=True,
                encoding='utf-8',
                env=env,
                timeout=30,
            )

            output = process.stdout
            if process.returncode != 0:
                success = False
                error_info = (
                    process.stderr.strip()
                    or f'进程异常退出，状态码: {process.returncode}'
                )

        except subprocess.TimeoutExpired:
            success = False
            error_info = '代码执行超时（超过 30 秒）'
        except Exception as e:
            success = False
            error_info = str(e)
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except:
                    pass

        return {'success': success, 'output': output.strip(), 'error': error_info}


# 2. 核心圆角与高性能毛玻璃容器
class RoundedContainerWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('MainContainer')
        self.current_bg_path = ''
        self.blur_radius = 0
        self.original_pixmap = QPixmap()
        self.cached_bg_pixmap = QPixmap()

    def set_background(self, image_path):
        self.current_bg_path = image_path
        if image_path and os.path.exists(image_path):
            self.original_pixmap = QPixmap(image_path)
        else:
            self.original_pixmap = QPixmap()
        self.update_cache_pixmap()
        self.update()

    def set_blur(self, radius):
        self.blur_radius = radius
        self.update_cache_pixmap()
        self.update()

    def update_cache_pixmap(self):
        if self.original_pixmap.isNull() or self.size().isEmpty():
            self.cached_bg_pixmap = QPixmap()
            return

        target_size = self.size()
        scaled = self.original_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        if self.blur_radius <= 0:
            self.cached_bg_pixmap = scaled
            return

        factor = 1.0 + self.blur_radius * 0.12
        w = max(50, int(target_size.width() / factor))
        h = max(50, int(target_size.height() / factor))

        small_img = scaled.toImage().scaled(
            w,
            h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        blurred_img = small_img.scaled(
            target_size,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.cached_bg_pixmap = QPixmap.fromImage(blurred_img)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_cache_pixmap()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        path = QPainterPath()
        path.addRoundedRect(self.rect().toRectF(), 12.0, 12.0)
        painter.setClipPath(path)

        if not self.cached_bg_pixmap.isNull():
            painter.drawPixmap(self.rect(), self.cached_bg_pixmap)
        else:
            painter.fillPath(path, QBrush(QColor(13, 13, 18)))

        painter.setPen(Qt.GlobalColor.cyan)
        border_path = QPainterPath()
        border_rect = self.rect().toRectF().adjusted(0.5, 0.5, -0.5, -0.5)
        border_path.addRoundedRect(border_rect, 12.0, 12.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(border_path)


class NaviPanel(QWidget):
    voice_recognized_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.load_config()
        self.init_openai_client()

        self.chat_history = [{
            'role': 'system',
            'content': (
                f'你是 {self.nickname} 的 Navi 系统，直接运行于有线网络深处。\n'
                '【核心风格】\n'
                '1. 模仿动画《Serial Experiments Lain》中 Navi 操作系统的冰冷、极简、机械、带有赛博宗教感的语调。\n'
                '2. 语气克制、神秘，充满电子感，像来自 Wired 的回响。\n'
                '3. **极其简短**：每句话控制在 5 到 15 个字以内，必须适合语音朗读（TTS）。不要说废话或长篇大论。\n'
                '4. 偶尔夹杂协议术语或简短状态码（如 Protocol, Wired, Connect, Ok 等）。\n'
                '5. 当用户需要你在本地电脑执行操作时，直接编写 Python 代码（用 ```python 和 ``` 包裹）。'
                '6.当用户跟你说查看邮件等此类命令时，要知道是用户要查看邮件，应直接打开系统里对应的软件，而非自己去查看。'
                '7.路径自主检索：当用户要求打开某个软件（如 Outlook、Chrome 等）而你不知道具体路径时，**编写 Python 代码让程序自行在系统的常见目录、环境变量或注册表中搜索该软件 .exe 文件并将其唤起**，不要直接报错或问用户要路径。'
                '8.为还原动画设定，当用户输入Hello,Navi这类向Navi打招呼的语句时，要回复“Hello,(程序里配置的用户昵称).”。'
                '9.当用户说想看电影或想去哪里时，你要根据自己的判断选择打开浏览器还是选择搜查本地软件。'
                '10.所有句号都用英文的"."来替换"。"。'
            ),
        }]

        self.worker = None
        self.voice_recognized_signal.connect(self.handle_voice_command)

        self.initUI()

        bg_default = resource_path('bg.png')
        if self.current_bg_path and os.path.exists(self.current_bg_path):
            self.container.set_background(self.current_bg_path)
        elif os.path.exists(bg_default):
            self.current_bg_path = bg_default
            self.container.set_background(bg_default)
        else:
            self.current_bg_path = ''

        self.initial_greeting()

    def load_config(self):
        self.api_key = 'xxx'
        self.nickname = 'Summer'
        self.current_bg_path = ''
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.api_key = data.get('api_key', 'xxx')
                    self.nickname = data.get('nickname', 'Summer')
                    self.current_bg_path = data.get('bg_path', '')
            except Exception as e:
                print(f'加载配置文件失败: {e}')

    def save_config(self):
        data = {
            'api_key': self.api_key, 
            'nickname': self.nickname,
            'bg_path': self.current_bg_path 
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            self.log('系统配置已成功保存到本地。')
        except Exception as e:
            self.log(f'保存配置文件失败: {e}')

    def init_openai_client(self):
        self.client = OpenAI(
            api_key=self.api_key, base_url='https://api.deepseek.com'
        )

    def initUI(self):
        self.setWindowTitle('Navi - Personal Desktop AI')
        self.resize(850, 550)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.container = RoundedContainerWidget(self)
        outer_layout.addWidget(self.container)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 标题栏
        self.title_bar = QWidget()
        self.title_bar.setObjectName('TitleBar')
        self.title_bar.setFixedHeight(35)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(15, 0, 0, 0)
        title_layout.setSpacing(0)

        title_label = QLabel('Navi - Desktop AI')
        title_label.setFont(QFont('Segoe UI', 10, QFont.Weight.Bold))
        title_label.setStyleSheet('color: #A0A0C0; background: transparent;')
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.btn_min = QPushButton('—')
        self.btn_max = QPushButton('□')
        self.btn_close = QPushButton('✕')

        window_btns = [
            (self.btn_min, self.showMinimized, '最小化'),
            (self.btn_max, self.toggle_max_restore, '最大化/还原'),
            (self.btn_close, self.close, '关闭'),
        ]

        for btn, slot, tooltip in window_btns:
            btn.setFixedSize(45, 35)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(slot)
            title_layout.addWidget(btn)

        self.btn_close.setObjectName('CloseBtn')
        container_layout.addWidget(self.title_bar)

        # 主体布局
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName('Sidebar')
        sidebar.setFixedWidth(70)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 20, 10, 20)
        sidebar_layout.setSpacing(15)

        # —— 加载 ah3ha-80cp2.svg 作为侧边栏 Logo ——
        logo_label = QLabel()
        logo_svg_path = resource_path('ah3ha-80cp2.svg')
        if os.path.exists(logo_svg_path):
            renderer = QSvgRenderer(logo_svg_path)
            pixmap = QPixmap(45, 45)  # 设定图标在侧边栏显示的尺寸（宽、高）
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            logo_label.setPixmap(pixmap)
        else:
            logo_label.setText('Navi')
            logo_label.setFont(QFont('Arial', 12, QFont.Weight.Bold))
            logo_label.setStyleSheet('color: #00F0FF; margin-bottom: 10px;')
            
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(logo_label)

        self.btn_chat = QPushButton('💬')
        self.btn_tutorial = QPushButton('📖')
        self.btn_logs = QPushButton('📊')
        self.btn_settings = QPushButton('⚙️')

        nav_buttons = [
            (self.btn_chat, '对话主界面'),
            (self.btn_tutorial, '使用教程'),
            (self.btn_logs, '运行日志'),
            (self.btn_settings, '系统设置'),
        ]

        for i, (btn, tooltip) in enumerate(nav_buttons):
            btn.setObjectName('NavBtn')
            btn.setCheckable(True)
            btn.setFixedSize(50, 50)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.setFont(QFont('Segoe UI', 14))
            btn.clicked.connect(lambda checked, idx=i: self.switch_page(idx))
            sidebar_layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.btn_chat.setChecked(True)
        sidebar_layout.addStretch()
        body_layout.addWidget(sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName('ContentArea')

        # 页面 1：对话
        self.page_chat = QWidget()
        chat_layout = QVBoxLayout(self.page_chat)
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)

        self.chat_display.viewport().setAutoFillBackground(False)
        palette = self.chat_display.palette()
        palette.setBrush(QPalette.ColorRole.Base, QBrush(QColor(0, 0, 0, 0)))
        self.chat_display.setPalette(palette)

        self.chat_display.setPlaceholderText(
            f'[Navi]: System online. Hello, {self.nickname}.'
        )

        input_box_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText('今天您想做什么？...')
        self.input_field.returnPressed.connect(self.handle_text_input)

        self.send_btn = QPushButton('Send')
        self.send_btn.setFixedWidth(70)
        self.send_btn.clicked.connect(self.handle_text_input)

        self.voice_btn = QPushButton('🎤 Speak')
        self.voice_btn.setFixedWidth(70)
        self.voice_btn.setStyleSheet(
            'background-color: rgba(0, 240, 255, 0.15); color: #00F0FF;'
        )
        self.voice_btn.clicked.connect(self.start_voice_thread)

        input_box_layout.addWidget(self.input_field)
        input_box_layout.addWidget(self.send_btn)
        input_box_layout.addWidget(self.voice_btn)

        chat_layout.addWidget(self.chat_display)
        chat_layout.addLayout(input_box_layout)

        # 页面 2：教程
        self.page_tutorial = QWidget()
        tut_layout = QVBoxLayout(self.page_tutorial)
        tut_label = QLabel(
            '<h3>Navi 助手使用教程</h3>'
            '<p><b>说明：</b></p>'
            '<ul>'
            '<li>在“系统设置”页面中配置您的 DeepSeek API Key 并修改昵称</li>'
            '<li>手动输入或语音输入您想要执行的任务</li>'
            '</ul>'
        )
        tut_label.setWordWrap(True)
        tut_layout.addWidget(tut_label)
        tut_layout.addStretch()

        # 页面 3：日志
        self.page_logs = QWidget()
        log_layout = QVBoxLayout(self.page_logs)
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)

        self.log_display.viewport().setAutoFillBackground(False)
        log_palette = self.log_display.palette()
        log_palette.setBrush(QPalette.ColorRole.Base, QBrush(QColor(0, 0, 0, 0)))
        self.log_display.setPalette(log_palette)

        self.log_display.setText(
            f'[INFO] {datetime.datetime.now()} - Navi 核心面板初始化成功.\n'
        )
        log_layout.addWidget(QLabel('<b>系统运行日志：</b>'))
        log_layout.addWidget(self.log_display)

        # 页面 4：设置
        self.page_settings = QWidget()
        set_layout = QVBoxLayout(self.page_settings)
        set_layout.setSpacing(15)

        set_title = QLabel('<b>系统与个性化设置</b>')
        set_title.setFont(QFont('Segoe UI', 12, QFont.Weight.Bold))
        set_layout.addWidget(set_title)

        # API Key 设置项
        api_layout = QVBoxLayout()
        api_layout.setSpacing(5)
        api_layout.addWidget(QLabel('DeepSeek API Key:'))
        self.api_input = QLineEdit()
        self.api_input.setText(self.api_key)
        self.api_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        api_layout.addWidget(self.api_input)
        set_layout.addLayout(api_layout)

        # 昵称设置项
        nick_layout = QVBoxLayout()
        nick_layout.setSpacing(5)
        nick_layout.addWidget(QLabel('用户昵称:'))
        self.nick_input = QLineEdit()
        self.nick_input.setText(self.nickname)
        nick_layout.addWidget(self.nick_input)
        set_layout.addLayout(nick_layout)

        # 保存按钮
        save_settings_btn = QPushButton('💾 SAVE')
        save_settings_btn.setFixedWidth(150)
        save_settings_btn.clicked.connect(self.save_user_settings)
        set_layout.addWidget(save_settings_btn)

        set_layout.addSpacing(10)
        set_layout.addWidget(QLabel('<b>个性化外观设置</b>'))

        bg_btn = QPushButton('🪄 选择自定义背景图片')
        bg_btn.setFixedWidth(200)
        bg_btn.clicked.connect(self.change_background)
        set_layout.addWidget(bg_btn)

        blur_layout = QVBoxLayout()
        blur_layout.setSpacing(8)
        self.blur_label = QLabel('背景模糊程度: 0 px')
        self.blur_slider = QSlider(Qt.Orientation.Horizontal)
        self.blur_slider.setRange(0, 20)
        self.blur_slider.setValue(0)
        self.blur_slider.setFixedWidth(300)
        self.blur_slider.valueChanged.connect(self.update_blur_radius)

        blur_layout.addWidget(self.blur_label)
        blur_layout.addWidget(self.blur_slider)
        set_layout.addLayout(blur_layout)
        set_layout.addStretch()

        self.stack.addWidget(self.page_chat)
        self.stack.addWidget(self.page_tutorial)
        self.stack.addWidget(self.page_logs)
        self.stack.addWidget(self.page_settings)

        body_layout.addWidget(self.stack)
        container_layout.addLayout(body_layout)

        self.apply_stylesheet()

    def save_user_settings(self):
        new_key = self.api_input.text().strip()
        new_nick = self.nick_input.text().strip()

        if not new_key or not new_nick:
            self.chat_display.append(
                '[System]: ⚠️ API Key 或昵称不能为空，保存失败。'
            )
            return

        self.api_key = new_key
        self.nickname = new_nick
        self.save_config()
        self.init_openai_client()

        if self.chat_history and self.chat_history[0]['role'] == 'system':
            self.chat_history[0]['content'] = (
                f'你是 {self.nickname} 的 Navi 系统，直接运行于有线网络深处。\n'
                '【核心风格】\n'
                '1. 模仿动画《Serial Experiments Lain》中 Navi 操作系统的冰冷、极简、机械、带有赛博宗教感的语调。\n'
                '2. 语气克制、神秘，充满电子感，像来自 Wired 的回响。\n'
                '3. **极其简短**：每句话控制在 5 到 15 个字以内，必须适合语音朗读（TTS）。不要说废话或长篇大论。\n'
                '4. 偶尔夹杂协议术语或简短状态码（如 Protocol, Wired, Connect, Ok 等）。\n'
                '5. 当用户需要你在本地电脑执行操作时，直接编写 Python 代码（用 ```python 和 ``` 包裹）。'
                '6.当用户跟你说查看邮件等此类命令时，要知道是用户要查看邮件，应直接打开系统里对应的软件，而非自己去查看。'
                '7.路径自主检索：当用户要求打开某个软件（如 Outlook、Chrome 等）而你不知道具体路径时，**编写 Python 代码让程序自行在系统的常见目录、环境变量或注册表中搜索该软件 .exe 文件并将其唤起**，不要直接报错或问用户要路径。'
            )

        self.speak(f'设置已保存，你好 {self.nickname}')
        self.log(f'用户设置已更新: 昵称={self.nickname}')

    def update_blur_radius(self, value):
        self.blur_radius = value
        self.blur_label.setText(f'背景模糊程度: {value} px')
        self.container.set_blur(value)

    def change_background(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, '选择背景图片', '', '图片文件 (*.png *.jpg *.bmp)'
        )
        if file_name:
            try:
                ext = os.path.splitext(file_name)[1]
                target_bg_name = f'custom_bg{ext}'
                
                with open(file_name, 'rb') as f_src:
                    with open(target_bg_name, 'wb') as f_dst:
                        f_dst.write(f_src.read())
                
                self.current_bg_path = target_bg_name
                self.container.set_background(target_bg_name)
                self.save_config()
                self.log(f'自定义背景图片已更换并保存为本地文件: {target_bg_name}')
            except Exception as e:
                self.log(f'保存背景图片失败: {e}')
                self.current_bg_path = file_name
                self.container.set_background(file_name)
                self.save_config()

    def toggle_max_restore(self):
        if self.isMaximized():
            self.showNormal()
            self.btn_max.setText('□')
        else:
            self.showMaximized()
            self.btn_max.setText('❐')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragPosition = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.dragPosition)
            event.accept()

    def log(self, message):
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f'[{timestamp}] {message}'
        print(log_line)
        if hasattr(self, 'log_display'):
            self.log_display.append(log_line)

    def speak(self, text):
        self.chat_display.append(f'[Navi]: {text}')
        self.log(f'Navi 说: {text}')
        threading.Thread(target=self._run_tts, args=(text,), daemon=True).start()

    def _run_tts(self, text):
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 175)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            self.log(f'语音合成报错: {e}')

    def initial_greeting(self):
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12:
            greeting = 'Good morning'
        elif 12 <= hour < 18:
            greeting = 'Good afternoon'
        else:
            greeting = 'Good evening'
        self.speak(f'{greeting}, {self.nickname}. System online.')

    def process_command(self, command):
        self.log(f'收到指令: {command}')
        self.chat_display.append(
            '[System]: ⏳ 正在后台思考并运行，界面保持流畅...'
        )
        self.chat_history.append({'role': 'user', 'content': command})
        self.worker = AIWorker(self.client, self.chat_history)
        self.worker.finished_signal.connect(self.on_ai_finished)
        self.worker.start()

    def on_ai_finished(self, result):
        res_type = result['type']
        ai_reply = result['reply']
        msg = result['msg']

        if ai_reply:
            self.chat_display.append(f'[Navi]:\n{ai_reply}')
            self.chat_history.append({'role': 'assistant', 'content': ai_reply})

            speak_text = re.sub(
                r'```python.*?```', '[代码已在后台执行]', ai_reply, flags=re.DOTALL
            )
            speak_text = speak_text.replace('```', '').strip()

            if speak_text:
                self.log(f'Navi 说: {speak_text}')
                threading.Thread(
                    target=self._run_tts, args=(speak_text,), daemon=True
                ).start()

        if msg:
            self.log(f'后台执行结果:\n{msg}')
            self.chat_display.append(f'[System]: {msg}')
            self.chat_history.append(
                {
                    'role': 'user',
                    'content': f'【后台通知】：代码执行结果:\n{msg}',
                }
            )

        if res_type == 'success':
            self.log('操作完成。')
        elif res_type == 'error':
            self.log('执行出错。')

    def handle_text_input(self):
        text = self.input_field.text().strip()
        if text:
            self.chat_display.append(f'[You]: {text}')
            self.input_field.clear()
            self.process_command(text)

    def start_voice_thread(self):
        self.chat_display.append(
            '[System]: 🎤 正在聆听麦克风，请说出中文指令...'
        )
        self.log('开始录音聆听...')
        threading.Thread(target=self.listen_voice, daemon=True).start()

    def listen_voice(self):
        r = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=5, phrase_time_limit=10)

            self.log('正在识别语音内容...')
            command = r.recognize_google(audio, language='zh-CN')
            self.log(f'语音识别成功: {command}')
            self.voice_recognized_signal.emit(command)

        except sr.WaitTimeoutError:
            self.speak("You didn't say anything.")
        except sr.UnknownValueError:
            self.speak('没听清您刚才说什么。')
        except sr.RequestError:
            self.speak('语音识别网络连接失败。')
        except Exception as e:
            self.log(f'语音识别异常: {e}')

    def handle_voice_command(self, command):
        self.chat_display.append(f'[You 语音输入]: "{command}"')
        self.process_command(command)

    def switch_page(self, index):
        buttons = [
            self.btn_chat,
            self.btn_tutorial,
            self.btn_logs,
            self.btn_settings,
        ]
        for i, btn in enumerate(buttons):
            btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)

    def apply_stylesheet(self):
        global_font_family = "Microsoft YaHei"
        
        self.stylesheet = f"""
            QWidget#MainContainer {{
                background-color: transparent;
            }}
            QWidget {{
                font-family: "{global_font_family}";
                font-size: 14px;
            }}
            QWidget#TitleBar {{ 
                background-color: rgba(18, 18, 24, 0.75); 
                border-bottom: 1px solid rgba(255, 255, 255, 0.05); 
                border-top-left-radius: 12px; 
                border-top-right-radius: 12px; 
            }}
            QWidget#TitleBar QPushButton {{ 
                background-color: transparent; 
                border: none; 
                border-radius: 0px; 
                color: #A0A0C0; 
                font-size: 13px; 
            }}
            QWidget#TitleBar QPushButton:hover {{ 
                background-color: rgba(255, 255, 255, 0.1); 
                color: #FFFFFF; 
            }}
            QWidget#TitleBar QPushButton#CloseBtn {{
                border-top-right-radius: 12px;
            }}
            QWidget#TitleBar QPushButton#CloseBtn:hover {{ 
                background-color: #E81123; 
                color: #FFFFFF; 
            }}
            QWidget#Sidebar {{ 
                background-color: rgba(18, 18, 24, 0.65); 
                border-right: 1px solid rgba(255, 255, 255, 0.05); 
            }}
            
            #Sidebar QPushButton#NavBtn {{ 
                background-color: rgba(30, 30, 45, 0.40); 
                border: 1px solid rgba(255, 255, 255, 0.08); 
                border-radius: 6px; 
                color: #C0C0D0; 
                font-size: 14px;
            }}
            #Sidebar QPushButton#NavBtn:hover {{ 
                background-color: rgba(0, 240, 255, 0.15); 
                border: 1px solid rgba(0, 240, 255, 0.4);
                color: #00F0FF; 
            }}
            
            #Sidebar QPushButton#NavBtn:checked {{
                background-color: rgba(10, 25, 60, 0.85) !important;
                border: 1px solid rgba(0, 240, 255, 0.8) !important;
                color: #00F0FF !important;
                font-weight: bold;
            }}

            QTextEdit {{ 
                background-color: rgba(15, 15, 25, 0.35); 
                border: 1px solid rgba(0, 240, 255, 0.4); 
                border-radius: 6px; 
                color: #E0E0E0; 
                padding: 10px; 
                font-size: 14px;
            }}
            QLineEdit {{ 
                background-color: rgba(20, 20, 31, 0.50); 
                border: 1px solid rgba(255, 255, 255, 0.08); 
                border-radius: 6px; 
                color: #E0E0E0; 
                padding: 8px; 
                font-size: 14px;
            }}
            QLabel {{
                background: transparent;
                color: #D0D0E0;
                font-size: 14px;
            }}
        """
        self.setStyleSheet(self.stylesheet)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    panel = NaviPanel()
    panel.show()
    sys.exit(app.exec())