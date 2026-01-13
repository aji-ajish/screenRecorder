import sys
import os
import webbrowser
import platform
import threading

from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QLabel,
    QSystemTrayIcon, QMenu, QAction, QComboBox, QDialog, QHBoxLayout,
    QMessageBox, QListWidget, QListWidgetItem, QGroupBox, QSizePolicy, QStyle # QStyle imported for fallback icon
)
from PyQt5.QtGui import QIcon, QScreen, QPixmap
from PyQt5.QtCore import Qt, QRunnable, QThreadPool, pyqtSignal, QObject, QSettings # QSettings imported

from recorder import ScreenRecorder
import subprocess

# main.py
import logging

# Configure logging
# ✅ லாக் ஃபைல் பாத்தை /tmp/ டைரக்டரிக்கு மாற்றவும்
log_file_path = os.path.join("/tmp", "simple_screen_recorder_debug.log") 
logging.basicConfig(
    level=logging.DEBUG, # Set to DEBUG to see all debug messages
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=log_file_path,
    filemode='a' # Append to file
)
logger = logging.getLogger(__name__) # Get a logger instance
# ---------------------------------------
# Application stylesheet (CSS-like)
APP_STYLE_SHEET = """
QWidget {
    font-family: Arial;
    font-size: 14px;
}
QPushButton {
    background-color: #4CAF50; /* Green */
    color: white;
    padding: 10px 20px;
    border: none;
    border-radius: 5px;
    margin: 5px;
}
QPushButton:hover {
    background-color: #45a049;
}
QPushButton:disabled {
    background-color: #cccccc;
    color: #666666;
}
QLabel {
    padding: 5px;
}
QGroupBox {
    border: 1px solid #ccc;
    border-radius: 5px;
    margin-top: 1ex; /* Adjust as needed */
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left; /* Position at top left */
    padding: 0 3px;
    background-color: #f0f0f0;
}
QListWidget {
    background-color: #f8f8f8;
    border: 1px solid #ddd;
    border-radius: 5px;
    padding: 5px;
}
QListWidget::item {
    padding: 8px;
    border-bottom: 1px solid #eee;
}
QListWidget::item:selected {
    background-color: #e0f2f7; /* Light blue for selected item */
}
"""

# ThumbnailGenerator - for generating thumbnails in background
class ThumbnailGenerator(QRunnable):
    def __init__(self, video_path, thumbnail_dir, item):
        super().__init__()
        self.video_path = video_path
        self.thumbnail_dir = thumbnail_dir
        self.item = item
        self.signals = ThumbnailSignals()

    def run(self):
        video_filename = os.path.basename(self.video_path)
        thumbnail_filename = f"{os.path.splitext(video_filename)[0]}.jpg"
        thumbnail_path = os.path.join(self.thumbnail_dir, thumbnail_filename)

        if not os.path.exists(thumbnail_path): # Generate only if not exists
            if not ScreenRecorder.generate_thumbnail(self.video_path, thumbnail_path):
                # If thumbnail generation fails, still emit signal to update with a default icon
                self.signals.thumbnail_generated.emit(self.item, None)
                return

        if os.path.exists(thumbnail_path):
            self.signals.thumbnail_generated.emit(self.item, thumbnail_path)
        else:
            self.signals.thumbnail_generated.emit(self.item, None) # No thumbnail generated

class ThumbnailSignals(QObject):
    thumbnail_generated = pyqtSignal(QListWidgetItem, str) # item, thumbnail_path

# RecordingsListDialog Class
class RecordingsListDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Your Recordings")
        self.setGeometry(200, 200, 650, 450)
        
        self.layout = QVBoxLayout()

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.open_selected_recording)
        self.layout.addWidget(self.list_widget)

        button_layout = QHBoxLayout()
        open_folder_button = QPushButton("Open Recordings Folder")
        open_folder_button.clicked.connect(self.open_recordings_folder)
        button_layout.addWidget(open_folder_button)

        refresh_button = QPushButton("Refresh List")
        refresh_button.clicked.connect(self.load_recordings)
        button_layout.addWidget(refresh_button)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)

        self.layout.addLayout(button_layout)
        self.setLayout(self.layout)

        self.thumbnail_dir = os.path.join(self.get_recordings_folder(), ".thumbnails")
        os.makedirs(self.thumbnail_dir, exist_ok=True) # Ensure thumbnail dir exists

        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(threading.active_count() + 2) # Adjust max threads

        self.load_recordings()

    def get_recordings_folder(self):
        if platform.system() == "Windows":
            return os.path.join(os.path.expanduser("~"), "Videos")
        else:
            return os.path.expanduser("~/Videos")

    def load_recordings(self):
        self.list_widget.clear()
        recordings_dir = self.get_recordings_folder()
        
        if not os.path.exists(recordings_dir):
            QMessageBox.warning(self, "Folder Not Found", f"Recordings folder not found: {recordings_dir}")
            return

        # Default icon for items without thumbnail (or while loading)
        default_icon_path = os.path.join(os.path.dirname(__file__), "assets", "default_video_icon.png") # Create this default icon
        if not os.path.exists(default_icon_path):
            # Fallback if default_video_icon.png is not provided
            default_icon = QApplication.style().standardIcon(QStyle.SP_FileIcon) 
        else:
            default_icon = QIcon(default_icon_path)

        video_files = [f for f in os.listdir(recordings_dir) if f.endswith(".mp4")]
        if not video_files:
            self.list_widget.addItem(QListWidgetItem("No recordings found."))
            return

        for filename in sorted(video_files, reverse=True): # Sort by date (latest first)
            filepath = os.path.join(recordings_dir, filename)
            item = QListWidgetItem(default_icon, filename) # Set default icon initially
            item.setData(Qt.UserRole, filepath)
            self.list_widget.addItem(item)
            
            # Start thumbnail generation in a separate thread
            generator = ThumbnailGenerator(filepath, self.thumbnail_dir, item)
            generator.signals.thumbnail_generated.connect(self.update_thumbnail)
            self.thread_pool.start(generator)
        
    def update_thumbnail(self, item, thumbnail_path):
        if thumbnail_path and os.path.exists(thumbnail_path):
            pixmap = QPixmap(thumbnail_path)
            if not pixmap.isNull():
                item.setIcon(QIcon(pixmap.scaled(120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))) # Scale to desired size
        else:
            # Fallback to a default error icon or no icon if thumbnail generation failed
            default_icon_path = os.path.join(os.path.dirname(__file__), "assets", "default_video_icon.png")
            if os.path.exists(default_icon_path):
                item.setIcon(QIcon(default_icon_path))
            else:
                item.setIcon(QApplication.style().standardIcon(QStyle.SP_FileIcon))


    def open_selected_recording(self, item):
        filepath = item.data(Qt.UserRole)
        if filepath and os.path.exists(filepath):
            try:
                if platform.system() == "Windows":
                    os.startfile(filepath)
                elif platform.system() == "Darwin":
                    subprocess.run(["open", filepath])
                else:
                    subprocess.run(["xdg-open", filepath])
            except Exception as e:
                QMessageBox.critical(self, "Error Opening File", f"Could not open file: {e}")
        else:
            QMessageBox.warning(self, "File Not Found", "Selected recording file does not exist.")

    def open_recordings_folder(self):
        recordings_dir = self.get_recordings_folder()
        if os.path.exists(recordings_dir):
            try:
                if platform.system() == "Windows":
                    os.startfile(recordings_dir)
                elif platform.system() == "Darwin":
                    subprocess.run(["open", recordings_dir])
                else:
                    subprocess.run(["xdg-open", recordings_dir])
            except Exception as e:
                QMessageBox.critical(self, "Error Opening Folder", f"Could not open folder: {e}")
        else:
            QMessageBox.warning(self, "Folder Not Found", "Recordings folder does not exist.")


# SettingsDialog Class
class SettingsDialog(QDialog):
    # Added settings_instance to constructor to handle QSettings
    def __init__(self, parent=None, recorder_instance=None, settings_instance=None):
        super().__init__(parent)
        self.setWindowTitle("Recorder Settings")
        self.setGeometry(200, 200, 400, 250)
        self.recorder = recorder_instance
        self.settings = settings_instance # Assign QSettings instance here
        self.layout = QVBoxLayout()

        self.ffmpeg_status_label = QLabel("FFmpeg Status: Checking...")
        self.layout.addWidget(self.ffmpeg_status_label)

        if not self.recorder.is_ffmpeg_available():
            self.ffmpeg_status_label.setText("FFmpeg Status: Not Found!")
            ffmpeg_install_button = QPushButton("Install FFmpeg (Click for Guide)")
            ffmpeg_install_button.clicked.connect(self.open_ffmpeg_guide)
            self.layout.addWidget(ffmpeg_install_button)
            self.layout.addWidget(QLabel("Please install FFmpeg to use recording features."))
        else:
            self.ffmpeg_status_label.setText("FFmpeg Status: Found!")

        self.layout.addSpacing(15)

        self.layout.addWidget(QLabel("Select Microphone:"))
        self.mic_combo = QComboBox()
        self.layout.addWidget(self.mic_combo)

        self.layout.addWidget(QLabel("Select Internal Audio (Monitor/Stereo Mix):"))
        self.internal_audio_combo = QComboBox()
        self.layout.addWidget(self.internal_audio_combo)

        self.load_audio_devices() # Loads devices into combo boxes
        self.load_ui_settings() # Loads saved settings into UI

        save_button = QPushButton("Save Settings")
        save_button.clicked.connect(self.save_settings)
        self.layout.addWidget(save_button)

        self.setLayout(self.layout)

    def open_ffmpeg_guide(self):
        if platform.system() == "Windows":
            webbrowser.open("https://www.gyan.dev/ffmpeg/builds/")
            QMessageBox.information(self, "FFmpeg Installation", 
                "Please download FFmpeg from the opened link and add it to your system's PATH environment variable."
                "\n\nFor more detailed guide, search online for 'install ffmpeg windows path'."
            )
        elif platform.system() == "Linux":
            QMessageBox.information(self, "FFmpeg Installation",
                "Please open your terminal and run:\n\nsudo apt update && sudo apt install ffmpeg\n\n(For Ubuntu/Debian based systems)"
            )
        else:
            QMessageBox.information(self, "FFmpeg Installation", "Please search online for 'install ffmpeg' on your operating system.")

    def load_audio_devices(self):
        devices = self.recorder.list_audio_devices()
        
        self.mic_combo.clear()
        self.mic_combo.addItems(devices["microphones"])
        
        self.internal_audio_combo.clear()
        self.internal_audio_combo.addItems(devices["internal_audio_monitors"])

        # Note: Initial selection will be handled by load_ui_settings()

    def load_ui_settings(self):
        mic_device_from_settings = self.recorder.mic_device
        internal_audio_device_from_settings = self.recorder.internal_audio_device

        print(f"DEBUG: Mic from recorder: '{mic_device_from_settings}'")
        print(f"DEBUG: Internal audio from recorder: '{internal_audio_device_from_settings}'")
        
        current_mic_items = [self.mic_combo.itemText(i) for i in range(self.mic_combo.count())]
        current_internal_audio_items = [self.internal_audio_combo.itemText(i) for i in range(self.internal_audio_combo.count())]

        print(f"DEBUG: Current mic combo items: {current_mic_items}")
        print(f"DEBUG: Current internal audio combo items: {current_internal_audio_items}")

        if mic_device_from_settings in current_mic_items:
            self.mic_combo.setCurrentText(mic_device_from_settings)
            print(f"DEBUG: Mic combo set to: '{self.mic_combo.currentText()}'")
        else:
            print(f"DEBUG: Saved mic '{mic_device_from_settings}' NOT found in combo items.")
            if "None" in current_mic_items:
                self.mic_combo.setCurrentText("None")
                print(f"DEBUG: Mic combo set to default 'None'.")
            elif self.mic_combo.count() > 0:
                self.mic_combo.setCurrentIndex(0)
                print(f"DEBUG: Mic combo set to first item: '{self.mic_combo.currentText()}'")


        if internal_audio_device_from_settings in current_internal_audio_items:
            self.internal_audio_combo.setCurrentText(internal_audio_device_from_settings)
            print(f"DEBUG: Internal audio combo set to: '{self.internal_audio_combo.currentText()}'")
        else:
            print(f"DEBUG: Saved internal audio '{internal_audio_device_from_settings}' NOT found in combo items.")
            if "None" in current_internal_audio_items:
                self.internal_audio_combo.setCurrentText("None")
                print(f"DEBUG: Internal audio combo set to default 'None'.")
            elif self.internal_audio_combo.count() > 0:
                self.internal_audio_combo.setCurrentIndex(0)
                print(f"DEBUG: Internal audio combo set to first item: '{self.internal_audio_combo.currentText()}'")
        
        print(f"Loaded settings into UI (final): Mic='{self.mic_combo.currentText()}', Internal='{self.internal_audio_combo.currentText()}'")


    def save_settings(self):
        # Update recorder instance with current UI selections
        self.recorder.mic_device = self.mic_combo.currentText()
        self.recorder.internal_audio_device = self.internal_audio_combo.currentText()
        
        # Call the save_recorder_settings method from the parent (RecorderApp)
        if self.parent() and hasattr(self.parent(), 'save_recorder_settings'):
            self.parent().save_recorder_settings() 

        QMessageBox.information(self, "Settings Saved", "Your audio recording settings have been saved.")
        self.accept()

# RecorderApp Class
class RecorderApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simple Screen Recorder")
        self.setGeometry(100, 100, 350, 250)
        self.hide() # Hide on startup, use tray icon
        # Ensure settings are saved when the app truly quits
        QApplication.instance().aboutToQuit.connect(self.save_recorder_settings)

        # --- Icon path fix starts here ---
        # 1. First, assume the .deb installation path (with _internal)
        self.icon_path = "/opt/simple-screen-recorder/_internal/assets/screenrecord.png"
        
        # 2. If the .deb path doesn't exist, check for PyInstaller or direct execution paths
        if not os.path.exists(self.icon_path):
            if getattr(sys, 'frozen', False):
                # For PyInstaller builds, assets are usually in sys._MEIPASS
                self.icon_path = os.path.join(sys._MEIPASS, "assets", "screenrecord.png")
            else:
                # For direct Python execution (development)
                self.icon_path = os.path.join(os.path.dirname(__file__), "assets", "screenrecord.png")

        # 3. Apply the icon if found, otherwise use a fallback
        if os.path.exists(self.icon_path):
            self.setWindowIcon(QIcon(self.icon_path))
            # Also set the application-wide icon for consistency across environments
            QApplication.instance().setWindowIcon(QIcon(self.icon_path)) 
        else:
            logger.warning(f"App icon file not found at {self.icon_path}. Using default system icon.")
            self.setWindowIcon(QApplication.style().standardIcon(QStyle.SP_ComputerIcon)) # Fallback icon
            QApplication.instance().setWindowIcon(QApplication.style().standardIcon(QStyle.SP_ComputerIcon)) # Set app icon fallback
        # --- Icon path fix ends here ---

        QApplication.instance().setStyleSheet(APP_STYLE_SHEET)

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        self.status_group = QGroupBox("Recording Status")
        status_layout = QVBoxLayout()
        self.status_label = QLabel("Status: Not Recording")
        self.status_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.status_label)
        self.status_group.setLayout(status_layout)
        self.main_layout.addWidget(self.status_group)

        self.control_group = QGroupBox("Controls")
        control_layout = QVBoxLayout()
        
        self.start_button = QPushButton("Start Recording")
        self.start_button.clicked.connect(self.start_recording)
        control_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop Recording")
        self.stop_button.clicked.connect(self.stop_recording)
        self.stop_button.setEnabled(False)
        control_layout.addWidget(self.stop_button)

        self.control_group.setLayout(control_layout)
        self.main_layout.addWidget(self.control_group)

        self.utility_group = QGroupBox("Utilities")
        utility_layout = QHBoxLayout()

        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        utility_layout.addWidget(self.settings_button)

        self.view_recordings_button = QPushButton("View Recordings")
        self.view_recordings_button.clicked.connect(self.open_recordings_list)
        utility_layout.addWidget(self.view_recordings_button)

        self.utility_group.setLayout(utility_layout)
        self.main_layout.addWidget(self.utility_group)

        self.main_layout.addStretch(1)

        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        self.screen_width = screen_geometry.width()
        self.screen_height = screen_geometry.height()

        # Initialize QSettings for the application
        self.settings = QSettings("Ajish", "SimpleScreenRecorder") # IMPORTANT: Use unique names

        self.recorder = ScreenRecorder(output_file="recording.mp4",
                                       screen_width=self.screen_width,
                                       screen_height=self.screen_height)
        
        # Load recorder settings from QSettings
        self.load_recorder_settings()

        self.create_tray_icon()
        self.check_ffmpeg_on_startup()

    def load_recorder_settings(self):
        # Explicitly read as string, and provide a default string "None"
        mic = self.settings.value("micDevice", "None", type=str) 
        internal_audio = self.settings.value("internalAudioDevice", "None", type=str) 
        
        # Apply loaded settings to the recorder instance
        self.recorder.mic_device = mic
        self.recorder.internal_audio_device = internal_audio
        
        print(f"Loaded settings into recorder: Mic='{self.recorder.mic_device}', Internal='{self.recorder.internal_audio_device}'")

    def save_recorder_settings(self):
        # Save mic and internal audio device settings from recorder to QSettings
        # Ensure values are strings, convert None to "None" string if necessary
        mic_to_save = str(self.recorder.mic_device) if self.recorder.mic_device is not None else "None"
        internal_audio_to_save = str(self.recorder.internal_audio_device) if self.recorder.internal_audio_device is not None else "None"

        self.settings.setValue("micDevice", mic_to_save)
        self.settings.setValue("internalAudioDevice", internal_audio_to_save)
        self.settings.sync() # Ensures settings are written to disk immediately
        print(f"Settings saved to QSettings: Mic='{mic_to_save}', Internal='{internal_audio_to_save}'")



    def create_tray_icon(self):
        # Use the determined self.icon_path for the tray icon
        if os.path.exists(self.icon_path):
            self.tray_icon = QSystemTrayIcon(QIcon(self.icon_path), self)
        else:
            print(f"Warning: Tray icon file not found at {self.icon_path}. Using default.")
            self.tray_icon = QSystemTrayIcon(self) # Fallback to default system tray icon
        
        self.tray_icon.setToolTip("Simple Screen Recorder")

        self.tray_menu = QMenu()
        self.show_action = QAction("Show Window", self)
        self.show_action.triggered.connect(self.show_window)
        self.tray_menu.addAction(self.show_action)

        self.start_record_action = QAction("Start Recording", self)
        self.start_record_action.triggered.connect(self.start_recording)
        self.tray_menu.addAction(self.start_record_action)

        self.stop_record_action = QAction("Stop Recording", self)
        self.stop_record_action.triggered.connect(self.stop_recording)
        self.stop_record_action.setEnabled(False)
        self.tray_menu.addAction(self.stop_record_action)

        self.tray_menu.addSeparator()

        self.tray_settings_action = QAction("Settings", self)
        self.tray_settings_action.triggered.connect(self.open_settings)
        self.tray_menu.addAction(self.tray_settings_action)

        self.tray_view_recordings_action = QAction("View Recordings", self)
        self.tray_view_recordings_action.triggered.connect(self.open_recordings_list)
        self.tray_menu.addAction(self.tray_view_recordings_action)

        self.tray_menu.addSeparator()

        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(QApplication.instance().quit)
        self.tray_menu.addAction(self.exit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_window()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def check_ffmpeg_on_startup(self):
        if not self.recorder.is_ffmpeg_available():
            QMessageBox.warning(self, "FFmpeg Not Found",
                "FFmpeg is not installed on your system. Recording features will not work.\n"
                "Please go to Settings to install FFmpeg."
            )
            self.start_button.setEnabled(False)
            self.start_record_action.setEnabled(False)

    def start_recording(self):
        if not self.recorder.is_ffmpeg_available():
            QMessageBox.critical(self, "Error", "FFmpeg is not installed. Cannot start recording.")
            return

        self.recorder.start_recording()
        self.status_label.setText("Status: Recording...")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.start_record_action.setEnabled(False)
        self.stop_record_action.setEnabled(True)
        print("Recording started from UI or Tray.")

    def stop_recording(self):
        self.recorder.stop_recording()
        self.status_label.setText("Status: Recording Stopped")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.start_record_action.setEnabled(True)
        self.stop_record_action.setEnabled(True) # Should be false after stopping
        print("Recording stopped from UI or Tray.")

    def open_settings(self):
        # Pass both recorder_instance and settings_instance to SettingsDialog
        dialog = SettingsDialog(self, recorder_instance=self.recorder, settings_instance=self.settings)
        dialog.exec_()
        if self.recorder.is_ffmpeg_available():
            self.start_button.setEnabled(True)
            self.start_record_action.setEnabled(True)

    def open_recordings_list(self):
        dialog = RecordingsListDialog(self)
        dialog.exec_()

    def closeEvent(self, event):
        # When the main window is closed, hide it to tray instead of quitting
        # Also, ensure settings are saved when the app is truly closing (e.g. from tray menu Exit)
        self.hide()
        event.ignore() # This ensures the application does not quit immediately

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set organization and application names BEFORE QSettings is used for the first time
    # These names determine the path where settings are stored (e.g., ~/.config/YourOrganization/SimpleScreenRecorder.conf)
    app.setOrganizationName("Ajish") # Replace with YOUR organization name (e.g., "AjishDev")
    app.setApplicationName("SimpleScreenRecorder") # Replace with YOUR app name (e.g., "SSR")

    # This ensures the application doesn't quit when the last window is closed, but stays in the tray
    app.setQuitOnLastWindowClosed(False) 
    
    window = RecorderApp()
    sys.exit(app.exec_())