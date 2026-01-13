import subprocess
import os
from datetime import datetime
import platform

class ScreenRecorder:
    def __init__(self, output_file="recording.mp4", screen_width=1920, screen_height=1080):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"recording_{timestamp}.mp4"

        if platform.system() == "Windows":
            videos_dir = os.path.join(os.path.expanduser("~"), "Videos")
        else: # Linux and macOS
            videos_dir = os.path.expanduser("~/Videos")

        if not os.path.exists(videos_dir):
            os.makedirs(videos_dir)

        self.output_file = os.path.join(videos_dir, filename)
        self.process = None
        self.screen_width = screen_width
        self.screen_height = screen_height

        # These will be loaded from QSettings by RecorderApp
        self.mic_device = "default" if platform.system() == "Linux" else "None" # Default to "None" if not set
        self.internal_audio_device = "None" # Default to "None" if not set

    @staticmethod
    def is_ffmpeg_available():
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def list_audio_devices():
        devices = {"microphones": [], "internal_audio_monitors": []}
        system = platform.system()

        if not ScreenRecorder.is_ffmpeg_available():
            print("FFmpeg not found. Cannot list devices.")
            return devices

        try:
            if system == "Windows":
                command = ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
                result = subprocess.run(command, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                output = result.stderr

                current_section = None
                for line in output.splitlines():
                    if "[dshow @ " in line and "audio devices" in line:
                        current_section = "audio"
                        continue
                    if current_section == "audio":
                        if "Alternative name" in line:
                            current_section = None
                            continue
                        if "]  \"" in line and "(audio)" in line:
                            device_name = line.split("]  \"")[1].split("\"")[0]
                            if "Stereo Mix" in device_name or "What U Hear" in device_name or "CABLE Output" in device_name:
                                devices["internal_audio_monitors"].append(device_name)
                            else:
                                devices["microphones"].append(device_name)
                
                if not devices["microphones"] and not devices["internal_audio_monitors"]: # Fallback if no specific devices found
                     devices["microphones"].append("Default Microphone (Auto)")


            elif system == "Linux":
                mic_command = ["pactl", "list", "short", "sources"]
                mic_result = subprocess.run(mic_command, capture_output=True, text=True, check=True)
                for line in mic_result.stdout.splitlines():
                    if "RUNNING" in line or "SUSPENDED" in line:
                        parts = line.split('\t')
                        if len(parts) > 1:
                            source_name = parts[1].strip()
                            if ".monitor" not in source_name: # Exclude monitor devices from microphones
                                devices["microphones"].append(source_name)
                
                monitor_command = ["pactl", "list", "short", "sources"]
                monitor_result = subprocess.run(monitor_command, capture_output=True, text=True, check=True)
                for line in monitor_result.stdout.splitlines():
                    if ".monitor" in line:
                        parts = line.split('\t')
                        if len(parts) > 1:
                            monitor_name = parts[1].strip()
                            devices["internal_audio_monitors"].append(monitor_name)
                
                if not devices["microphones"]: # Fallback if no specific microphones found
                    devices["microphones"].append("default")


            devices["microphones"].insert(0, "None") # Always add "None" option
            devices["internal_audio_monitors"].insert(0, "None") # Always add "None" option

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error listing audio devices: {e}")
            print("Please ensure FFmpeg (and PulseAudio tools on Linux) is correctly installed and configured.")
        
        return devices

    @staticmethod
    def generate_thumbnail(video_path, thumbnail_path, size="120x90"):
        if not ScreenRecorder.is_ffmpeg_available():
            print("FFmpeg not found. Cannot generate thumbnail.")
            return False
        
        try:
            # -ss 00:00:01 - seeks to 1 second into the video
            # -vframes 1 - grabs only one frame
            # -q:v 2 - video quality control (faster with lower quality for thumbnail)
            # -vf scale=... - scales the image
            command = [
                "ffmpeg",
                "-y", # overwrite output file if it exists
                "-i", video_path,
                "-ss", "00:00:01",
                "-vframes", "1",
                "-q:v", "2",
                "-vf", f"scale={size}:force_original_aspect_ratio=decrease,pad={size}:(ow-iw)/2:(oh-ih)/2", # Scale and pad to fill requested size
                thumbnail_path
            ]
            
            # Prevent console window from opening on Windows
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            
            subprocess.run(command, check=True, capture_output=True, creationflags=creationflags)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error generating thumbnail for {video_path}: {e.stderr.decode()}")
            return False
        except FileNotFoundError:
            print("FFmpeg not found. Cannot generate thumbnail.")
            return False

    def start_recording(self):
        resolution = f"{self.screen_width}x{self.screen_height}"
        mic_input = self.mic_device if self.mic_device != "None" else None
        internal_audio_input = self.internal_audio_device if self.internal_audio_device != "None" else None

        self.command = ["ffmpeg", "-y"]

        if platform.system() == "Windows":
            video_device = "screen-capture-recorder"
            if mic_input:
                self.command.extend(["-f", "dshow", "-i", f"video={video_device}:audio={mic_input}"])
            else:
                self.command.extend(["-f", "dshow", "-i", f"video={video_device}"])

            if internal_audio_input:
                self.command.extend(["-f", "dshow", "-i", f"audio={internal_audio_input}"])
            
            if mic_input and internal_audio_input:
                self.command.extend(["-filter_complex", "[0:a][1:a]amix=inputs=2[a]", "-map", "0:v", "-map", "[a]"])
            elif mic_input:
                self.command.extend(["-map", "0:v", "-map", "0:a"])
            elif internal_audio_input:
                self.command.extend(["-map", "0:v", "-map", "1:a"])
            else:
                self.command.extend(["-map", "0:v"])

            self.command.extend([
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-video_size", resolution,
                self.output_file
            ])


        elif platform.system() == "Linux":
            self.command.extend([
                "-video_size", resolution,
                "-framerate", "30",
                "-f", "x11grab",
                "-i", ":0.0",
            ])
            
            audio_inputs = []
            if mic_input:
                self.command.extend(["-f", "pulse", "-i", mic_input])
                audio_inputs.append("mic")
            if internal_audio_input:
                self.command.extend(["-f", "pulse", "-i", internal_audio_input])
                audio_inputs.append("internal")

            if len(audio_inputs) == 2:
                self.command.extend(["-filter_complex", "[1:a][2:a]amix=inputs=2[a]", "-map", "0:v", "-map", "[a]"])
            elif len(audio_inputs) == 1:
                if audio_inputs[0] == "mic":
                    self.command.extend(["-map", "0:v", "-map", "1:a"])
                else:
                    self.command.extend(["-map", "0:v", "-map", "1:a"])
            else:
                self.command.extend(["-map", "0:v"])

            self.command.extend([
                "-c:v", "libx264",
                "-preset", "ultrafast",
                self.output_file
            ])
        else:
            print("Unsupported operating system for recording.")
            return

        print("FFmpeg Command:", " ".join(self.command))
        self.process = subprocess.Popen(self.command)

    def stop_recording(self):
        if self.process:
            self.process.terminate()
            stdout, stderr = self.process.communicate()
            self.process.wait()
            self.process = None
            print("FFmpeg Stdout:", stdout)
            print("FFmpeg Stderr:", stderr)