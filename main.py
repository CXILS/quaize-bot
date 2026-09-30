# main.py
import os
import subprocess
import threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.core.window import Window

# Указываем путь к Chromium в Android (для Playwright)
# Это нужно, чтобы Playwright использовал системный браузер, а не пытался скачать свой.
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '0'
CHROMIUM_PATH = "/data/data/com.termux/files/usr/bin/chromium-browser"

class BotApp(App):
    def build(self):
        Window.size = (400, 700)
        self.bot_process = None
        self.is_running = False

        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # Заголовок
        layout.add_widget(Label(text="Quaize Bot", font_size='24sp', size_hint_y=0.1))

        # Кнопка Старт/Стоп
        self.toggle_btn = Button(text="▶️ Запустить бота", font_size='20sp', size_hint_y=0.15)
        self.toggle_btn.bind(on_press=self.toggle_bot)
        layout.add_widget(self.toggle_btn)

        # Область логов
        self.log_label = Label(text="Логи появятся здесь...", size_hint_y=None, halign='left', valign='top')
        self.log_label.bind(width=lambda *x: self.log_label.setter('text_size')(self.log_label, (self.log_label.width, None)))
        
        scroll = ScrollView()
        scroll.add_widget(self.log_label)
        layout.add_widget(scroll)
        
        # Регулярное обновление логов
        Clock.schedule_interval(self.update_logs, 1.0)

        return layout

    def toggle_bot(self, instance):
        if not self.is_running:
            self.start_bot()
        else:
            self.stop_bot()

    def start_bot(self):
        self.is_running = True
        self.toggle_btn.text = "⏹️ Остановить бота"
        self.log_label.text = "Запуск бота...\n"
        
        # Запускаем playwrite.py как отдельный процесс
        # Важно: передаем путь к Chromium через переменную окружения или аргумент
        def run_bot():
            try:
                # Запускаем скрипт в отдельном процессе
                self.bot_process = subprocess.Popen(
                    ['python', 'playwrite.py'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                # Читаем вывод в реальном времени
                for line in self.bot_process.stdout:
                    self.log_label.text += line
                    # Прокручиваем вниз
                    self.log_label.text_size = (self.log_label.width, None)
            except Exception as e:
                self.log_label.text += f"\nОшибка запуска: {e}"
            finally:
                self.is_running = False
                self.toggle_btn.text = "▶️ Запустить бота"

        threading.Thread(target=run_bot, daemon=True).start()

    def stop_bot(self):
        if self.bot_process:
            self.bot_process.terminate()
            self.bot_process = None
        self.is_running = False
        self.toggle_btn.text = "▶️ Запустить бота"
        self.log_label.text += "\n--- Бот остановлен ---\n"

    def update_logs(self, dt):
        # Прокрутка вниз при обновлении
        pass

if __name__ == '__main__':
    BotApp().run()
