# client_qt_fixed_complete.py
import sys
import socket
import json
import datetime
import base64
import os
import pickle
import pyaudio
import threading
import time

# 自动设置QT平台插件路径
def set_qt_plugin_path():
    """自动设置QT平台插件路径，解决插件未找到的问题"""
    if 'QT_QPA_PLATFORM_PLUGIN_PATH' not in os.environ:
        plugin_path = os.path.join('venv', 'Lib', 'site-packages', 'PyQt5', 'Qt5', 'plugins')
        if not os.path.exists(plugin_path):
            current_dir = os.path.dirname(os.path.abspath(__file__))
            plugin_path = os.path.join(current_dir, 'venv', 'Lib', 'site-packages', 'PyQt5', 'Qt5', 'plugins')
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path
        print(f"自动设置QT平台插件路径: {plugin_path}")

set_qt_plugin_path()
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QTextBrowser, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QInputDialog, QMessageBox,
    QLabel, QFrame, QListWidget, QListWidgetItem, QDialog, QSplitter,
    QGroupBox, QStatusBar, QAction, QMenu, QMenuBar, QToolButton,
    QSystemTrayIcon, QComboBox, QFontDialog, QFileDialog, QDialogButtonBox,
    QProgressBar, QStackedWidget, QTabWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize, QDateTime, QMetaObject
from PyQt5.QtGui import QFont, QIcon, QTextCursor, QPalette, QColor

class VoiceClient(QThread):
    """语音客户端类 - 修复版本"""
    # 定义信号
    call_incoming = pyqtSignal(str)
    call_accepted = pyqtSignal(str)
    call_rejected = pyqtSignal(str)
    call_ended = pyqtSignal(str)
    
    def __init__(self, host, port, username, input_device_index=-1, output_device_index=-1):
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.voice_socket = None
        self.voice_thread = None
        self.audio_thread = None
        self.running = False
        self.connected = False
        
        # PyAudio参数
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 44100
        
        # 音频流
        self.p = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        
        # 音频设备索引
        self.input_device_index = input_device_index  # -1 表示使用默认设备
        self.output_device_index = output_device_index  # -1 表示使用默认设备
        
        # 状态
        self.in_call = False
        self.in_room = False
        self.current_room = None
        self.current_call_partner = None
        self.is_call_accepted = False
        
        # 线程同步
        self.audio_lock = threading.Lock()
        self.state_lock = threading.Lock()
        
    def connect(self):
        """连接到语音服务器"""
        try:
            print(f"[语音] 连接到语音服务器 {self.host}:{self.port}")
            
            # 清理现有连接
            self.disconnect()
            
            # 创建新连接
            self.voice_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.voice_socket.settimeout(5)
            self.voice_socket.connect((self.host, self.port))
            self.voice_socket.settimeout(None)
            
            # 发送用户名
            username_data = self.username.encode()
            import struct
            length_prefix = struct.pack('>I', len(username_data))
            self.voice_socket.sendall(length_prefix + username_data)
            
            # 启动接收线程
            self.running = True
            self.connected = True
            
            self.voice_thread = threading.Thread(target=self.receive_voice_commands)
            self.voice_thread.daemon = True
            self.voice_thread.start()
            
            print(f"[语音] 连接成功")
            return True
            
        except socket.timeout:
            print(f"[语音] 连接超时")
            return False
        except ConnectionRefusedError:
            print(f"[语音] 连接被拒绝")
            return False
        except Exception as e:
            print(f"[语音] 连接失败: {e}")
            return False
    
    def receive_voice_commands(self):
        """接收语音命令"""
        while self.running and self.connected:
            try:
                # 设置超时避免阻塞
                self.voice_socket.settimeout(1.0)
                
                # 接收长度前缀
                length_prefix = self.voice_socket.recv(4)
                if not length_prefix:
                    print("[语音] 服务器关闭连接")
                    self.connected = False
                    break
                
                # 解析长度
                import struct
                try:
                    data_length = struct.unpack('>I', length_prefix)[0]
                except struct.error:
                    print("[语音] 无效的长度前缀")
                    continue
                
                # 接收完整数据
                data = b''
                while len(data) < data_length:
                    remaining = data_length - len(data)
                    chunk = self.voice_socket.recv(min(4096, remaining))
                    if not chunk:
                        break
                    data += chunk
                
                if len(data) != data_length:
                    print(f"[语音] 数据不完整: 预期{data_length}, 实际{len(data)}")
                    continue
                
                # 反序列化命令
                try:
                    command = pickle.loads(data)
                except Exception as e:
                    print(f"[语音] 反序列化失败: {e}")
                    continue
                
                cmd_type = command.get('type')
                print(f"[语音] 收到命令: {cmd_type}")
                
                # 处理命令
                self.process_voice_command(cmd_type, command)
                    
            except socket.timeout:
                continue
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
                print(f"[语音] 连接错误: {e}")
                self.connected = False
                break
            except Exception as e:
                if self.running:
                    print(f"[语音] 接收错误: {e}")
                continue
            finally:
                try:
                    self.voice_socket.settimeout(None)
                except:
                    pass
        
        print("[语音] 接收线程结束")
        self.connected = False
    
    def process_voice_command(self, cmd_type, command):
        """处理语音命令"""
        try:
            print(f"[语音] 收到命令: {cmd_type}, 参数: {command}")
            if cmd_type == 'incoming_call':
                caller = command.get('caller')
                print(f"[语音] 来电: {caller}")
                # 发射信号代替回调
                self.call_incoming.emit(caller)
                    
            elif cmd_type == 'call_accepted':
                callee = command.get('callee')
                print(f"[语音] 通话被接受: {callee}, 当前用户名: {self.username}")
                with self.state_lock:
                    self.current_call_partner = callee
                    self.in_call = True
                    self.is_call_accepted = True
                # 启动音频流 - 无论是发起方还是接收方都需要启动
                self.start_audio()
                print(f"[语音] 音频流已启动 for {self.username}")
                # 发射信号代替回调
                self.call_accepted.emit(callee)
                    
            elif cmd_type == 'call_rejected':
                callee = command.get('callee')
                print(f"[语音] 通话被拒绝: {callee}")
                with self.state_lock:
                    self.in_call = False
                    self.current_call_partner = None
                    self.is_call_accepted = False
                # 发射信号代替回调
                self.call_rejected.emit(callee)
                    
            elif cmd_type == 'call_ended':
                user = command.get('user')
                print(f"[语音] 通话结束: {user}")
                # 先更新通话状态
                with self.state_lock:
                    self.in_call = False
                    self.current_call_partner = None
                    self.is_call_accepted = False
                # 再结束音频流
                self.safe_end_audio()
                # 发射信号代替回调
                self.call_ended.emit(user)
                    
            elif cmd_type == 'audio_data':
                # 首先检查是否在通话或房间中，不在则直接返回
                with self.state_lock:
                    if not (self.in_call or self.in_room):
                        print("[语音] 不在通话或房间中，忽略音频数据")
                        return
                
                audio_data = command.get('audio_data')
                print(f"[语音] 收到音频数据，大小: {len(audio_data) if audio_data else 0} bytes")
                print(f"[语音] 输出流状态: {self.output_stream}, 通话状态: {self.in_call}, 房间状态: {self.in_room}")
                
                with self.audio_lock:
                    # 确保音频流有效
                    if not self.output_stream:
                        print("[语音] 输出流未初始化，忽略音频数据")
                        return
                    
                    try:
                        # 检查流是否已经关闭
                        if hasattr(self.output_stream, '_stream') and self.output_stream._stream is None:
                            print("[语音] 输出流已关闭，忽略音频数据")
                            return
                        
                        # 确保流未停止
                        if self.output_stream.is_stopped():
                            print("[语音] 输出流已停止，忽略音频数据")
                            return
                            
                        self.output_stream.write(audio_data)
                    except (IOError, OSError) as e:
                        print(f"[语音] 播放音频失败: {e}")
                        # 发生错误时安全结束音频流，不尝试重新启动
                        self.safe_end_audio()
                        
        except Exception as e:
            print(f"[语音] 处理命令失败: {e}")
    
    def start_audio(self):
        """开始音频传输"""
        with self.audio_lock:
            if self.audio_thread and self.audio_thread.is_alive():
                return
            
            print("[语音] 启动音频线程")
            self.audio_thread = threading.Thread(target=self.audio_loop)
            # 不设置为守护线程，确保音频线程在通话期间保持运行
            self.audio_thread.daemon = False
            self.audio_thread.start()
    
    def audio_loop(self):
        """音频循环"""
        try:
            print("[语音] 进入音频循环")
            
            # 确保PyAudio实例已创建
            import pyaudio
            if not hasattr(self, 'p') or not self.p:
                self.p = pyaudio.PyAudio()
            
            # 调试信息：列出所有可用设备
            device_count = self.p.get_device_count()
            print(f"[语音] 检测到 {device_count} 个音频设备")
            for i in range(device_count):
                device_info = self.p.get_device_info_by_index(i)
                device_name = device_info['name']
                device_type = "输入" if device_info['maxInputChannels'] > 0 else "输出"
                print(f"[语音] 设备 {i}: {device_name} ({device_type})")
            
            # 检查通话状态
            if not (self.in_call or self.in_room):
                print("[语音] 不在通话或房间中，退出音频循环")
                return
            
            # 打开音频流
            input_params = {
                'format': self.FORMAT,
                'channels': self.CHANNELS,
                'rate': self.RATE,
                'input': True,
                'frames_per_buffer': self.CHUNK
            }
            # 验证输入设备索引
            if self.input_device_index != -1:
                try:
                    device_count = self.p.get_device_count()
                    if 0 <= self.input_device_index < device_count:
                        input_params['input_device_index'] = self.input_device_index
                        print(f"[语音] 使用指定输入设备: {self.input_device_index}")
                    else:
                        print(f"[语音] 输入设备索引 {self.input_device_index} 无效，使用默认设备")
                        input_params['input_device_index'] = None
                except Exception as e:
                    print(f"[语音] 验证输入设备索引失败: {e}，使用默认设备")
                    input_params['input_device_index'] = None
            else:
                input_params['input_device_index'] = None
            
            output_params = {
                'format': self.FORMAT,
                'channels': self.CHANNELS,
                'rate': self.RATE,
                'output': True,
                'frames_per_buffer': self.CHUNK
            }
            # 验证输出设备索引
            if self.output_device_index != -1:
                try:
                    device_count = self.p.get_device_count()
                    if 0 <= self.output_device_index < device_count:
                        output_params['output_device_index'] = self.output_device_index
                        print(f"[语音] 使用指定输出设备: {self.output_device_index}")
                    else:
                        print(f"[语音] 输出设备索引 {self.output_device_index} 无效，使用默认设备")
                        output_params['output_device_index'] = None
                except Exception as e:
                    print(f"[语音] 验证输出设备索引失败: {e}，使用默认设备")
                    output_params['output_device_index'] = None
            else:
                output_params['output_device_index'] = None
            
            # 尝试打开输入流
            self.input_stream = None
            try:
                self.input_stream = self.p.open(**input_params)
                print("[语音] 输入音频流已打开")
            except Exception as e:
                print(f"[语音] 打开输入音频流失败: {e}")
                # 如果输入流打开失败，尝试使用默认设备
                input_params.pop('input_device_index', None)
                try:
                    self.input_stream = self.p.open(**input_params)
                    print("[语音] 尝试使用默认输入设备成功")
                except Exception as e2:
                    print(f"[语音] 打开默认输入设备失败: {e2}")
                    # 不抛出异常，继续尝试打开输出流
            
            # 尝试打开输出流
            self.output_stream = None
            try:
                self.output_stream = self.p.open(**output_params)
                print("[语音] 输出音频流已打开")
            except Exception as e:
                print(f"[语音] 打开输出音频流失败: {e}")
                # 如果输出流打开失败，尝试使用默认设备
                output_params.pop('output_device_index', None)
                try:
                    self.output_stream = self.p.open(**output_params)
                    print("[语音] 尝试使用默认输出设备成功")
                except Exception as e2:
                    print(f"[语音] 打开默认输出设备失败: {e2}")
                    # 不抛出异常，继续执行
            
            # 检查是否至少有一个流打开成功
            if not self.input_stream and not self.output_stream:
                print("[语音] 无法打开任何音频流，请检查音频设备配置")
                raise Exception("无法打开任何音频流")
            
            print("[语音] 音频流初始化完成")
            
            print("[语音] 音频流已全部打开")
            
            while self.running and (self.in_call or self.in_room):
                try:
                    # 检查音频流状态 - 更加健壮的检查方式
                    if not self.input_stream or not self.output_stream:
                        print("[语音] 音频流无效，退出循环")
                        break
                    # 如果流被停止，尝试重新启动
                    if self.input_stream.is_stopped():
                        try:
                            self.input_stream.start_stream()
                            print("[语音] 重新启动输入流")
                        except Exception as e:
                            print(f"[语音] 重新启动输入流失败: {e}")
                            break
                    if self.output_stream.is_stopped():
                        try:
                            self.output_stream.start_stream()
                            print("[语音] 重新启动输出流")
                        except Exception as e:
                            print(f"[语音] 重新启动输出流失败: {e}")
                            break
                    
                    # 录制前再次检查状态
                    with self.state_lock:
                        call_active = self.in_call
                        room_active = self.in_room
                    if not (call_active or room_active):
                        print("[语音] 通话或房间状态已改变，退出音频循环")
                        break
                    
                    # 录制音频
                    audio_data = None
                    if self.input_stream:
                        try:
                            audio_data = self.input_stream.read(self.CHUNK, exception_on_overflow=False)
                            if not audio_data:
                                continue
                            print(f"[语音] 录制音频数据，大小: {len(audio_data)} bytes")
                        except Exception as e:
                            print(f"[语音] 录制音频失败: {e}")
                            continue
                    
                    # 发送音频数据前再次检查状态
                    with self.state_lock:
                        call_active = self.in_call
                        room_active = self.in_room
                    
                    if (call_active and self.current_call_partner and audio_data) or (room_active and self.current_room and audio_data):
                        if call_active and self.current_call_partner:
                            cmd = pickle.dumps({
                                'type': 'audio_data',
                                'audio_data': audio_data
                            })
                            print(f"[语音] 发送音频数据到 {self.current_call_partner}, 大小: {len(audio_data)} bytes")
                        elif room_active and self.current_room:
                            cmd = pickle.dumps({
                                'type': 'audio_data',
                                'room_id': self.current_room,
                                'audio_data': audio_data
                            })
                            print(f"[语音] 发送音频数据到房间 {self.current_room}, 大小: {len(audio_data)} bytes")
                        
                        # 发送数据
                        import struct
                        length_prefix = struct.pack('>I', len(cmd))
                        
                        if self.voice_socket and self.running:
                            try:
                                self.voice_socket.sendall(length_prefix + cmd)
                            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
                                print(f"[语音] 发送音频失败: {e}")
                                break
                    else:
                        # 如果状态已经改变，立即退出循环
                        with self.state_lock:
                            if not (self.in_call or self.in_room):
                                print("[语音] 通话或房间状态已改变，退出音频循环")
                                break
                        continue
                    
                except Exception as e:
                    print(f"[语音] 音频循环错误: {e}")
                    break
                    
        except Exception as e:
            print(f"[语音] 音频循环初始化失败: {e}")
        finally:
            self.safe_end_audio()
            print("[语音] 音频循环结束")
    
    def safe_end_audio(self):
        """安全结束音频传输"""
        print("[语音] 结束音频传输")
        
        with self.audio_lock:
            # 关闭输入流
            if self.input_stream:
                try:
                    if not self.input_stream.is_stopped():
                        self.input_stream.stop_stream()
                    self.input_stream.close()
                    print("[语音] 输入流已关闭")
                except Exception as e:
                    print(f"[语音] 关闭输入流失败: {e}")
                finally:
                    self.input_stream = None
            
            # 关闭输出流
            if self.output_stream:
                try:
                    if not self.output_stream.is_stopped():
                        self.output_stream.stop_stream()
                    self.output_stream.close()
                    print("[语音] 输出流已关闭")
                except Exception as e:
                    print(f"[语音] 关闭输出流失败: {e}")
                finally:
                    self.output_stream = None
            
            # 关闭PyAudio实例
            if hasattr(self, 'p') and self.p:
                try:
                    self.p.terminate()
                    print("[语音] PyAudio实例已关闭")
                except Exception as e:
                    print(f"[语音] 关闭PyAudio实例失败: {e}")
                finally:
                    self.p = None
    
    def join_room(self, room_id='public'):
        """加入语音房间"""
        try:
            with self.state_lock:
                if self.in_room or self.in_call:
                    return False
                
                cmd = pickle.dumps({
                    'type': 'join_room',
                    'room_id': room_id
                })
                
                import struct
                length_prefix = struct.pack('>I', len(cmd))
                self.voice_socket.sendall(length_prefix + cmd)
                
                self.in_room = True
                self.current_room = room_id
                self.start_audio()
                
                print(f"[语音] 加入房间: {room_id}")
                return True
                
        except Exception as e:
            print(f"[语音] 加入房间失败: {e}")
            return False
    
    def leave_room(self):
        """离开语音房间"""
        try:
            with self.state_lock:
                if not self.in_room:
                    return True
                
                if self.current_room:
                    cmd = pickle.dumps({
                        'type': 'leave_room',
                        'room_id': self.current_room
                    })
                    
                    import struct
                    length_prefix = struct.pack('>I', len(cmd))
                    self.voice_socket.sendall(length_prefix + cmd)
                
                self.safe_end_audio()
                self.in_room = False
                self.current_room = None
                
                print("[语音] 离开房间")
                return True
                
        except Exception as e:
            print(f"[语音] 离开房间失败: {e}")
            return False
    
    def start_private_call(self, callee):
        """发起私人通话"""
        try:
            with self.state_lock:
                if self.in_call or self.in_room:
                    return False
                
                cmd = pickle.dumps({
                    'type': 'start_private_call',
                    'callee': callee
                })
                
                import struct
                length_prefix = struct.pack('>I', len(cmd))
                self.voice_socket.sendall(length_prefix + cmd)
                
                self.current_call_partner = callee
                # 不要立即设置in_call=True，等待对方接受后再设置
                # 只设置call_accepted=False表示正在等待响应
                self.is_call_accepted = False
                
                print(f"[语音] 呼叫: {callee}")
                return True
                
        except Exception as e:
            print(f"[语音] 发起通话失败: {e}")
            return False
    
    def accept_call(self, caller):
        """接受通话"""
        try:
            with self.state_lock:
                if self.in_call or self.in_room:
                    return False
                
                cmd = pickle.dumps({
                    'type': 'accept_call',
                    'caller': caller
                })
                
                import struct
                length_prefix = struct.pack('>I', len(cmd))
                self.voice_socket.sendall(length_prefix + cmd)
                
                self.in_call = True
                self.current_call_partner = caller
                
                # 立即启动音频流
                self.start_audio()
                print(f"[语音] 接受通话: {caller}，音频流已启动")
                return True
                
        except Exception as e:
            print(f"[语音] 接受通话失败: {e}")
            return False
    
    def reject_call(self, caller):
        """拒绝通话"""
        try:
            cmd = pickle.dumps({
                'type': 'reject_call',
                'caller': caller
            })
            
            import struct
            length_prefix = struct.pack('>I', len(cmd))
            self.voice_socket.sendall(length_prefix + cmd)
            
            print(f"[语音] 拒绝通话: {caller}")
            return True
            
        except Exception as e:
            print(f"[语音] 拒绝通话失败: {e}")
            return False
    
    def end_call(self):
        """结束通话"""
        try:
            print("[语音] 结束通话")
            
            with self.state_lock:
                was_in_call = self.in_call
                partner = self.current_call_partner
                
                # 更新状态
                self.in_call = False
                self.current_call_partner = None
                self.is_call_accepted = False
                
                # 结束音频
                self.safe_end_audio()
                
                # 发送结束命令
                if was_in_call:
                    cmd = pickle.dumps({
                        'type': 'end_call'
                    })
                    
                    import struct
                    length_prefix = struct.pack('>I', len(cmd))
                    
                    if self.voice_socket and self.running:
                        try:
                            self.voice_socket.sendall(length_prefix + cmd)
                            print("[语音] 已发送结束命令")
                        except Exception as e:
                            print(f"[语音] 发送结束命令失败: {e}")
            
            print("[语音] 通话结束完成")
            return True
            
        except Exception as e:
            print(f"[语音] 结束通话失败: {e}")
            return False
    
    def disconnect(self):
        """断开语音连接"""
        print("[语音] 断开连接")
        
        self.running = False
        
        # 离开房间
        if self.in_room:
            self.leave_room()
        
        # 结束通话
        if self.in_call:
            self.end_call()
        
        # 关闭音频
        self.safe_end_audio()
        
        # 关闭socket
        if self.voice_socket:
            try:
                self.voice_socket.close()
            except:
                pass
            self.voice_socket = None
        
        # 终止PyAudio
        if self.p:
            try:
                self.p.terminate()
            except:
                pass
        
        self.connected = False
        print("[语音] 连接已断开")

class ReceiveThread(QThread):
    """接收消息线程"""
    message_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    connection_closed = pyqtSignal()
    
    def __init__(self, socket):
        super().__init__()
        self.socket = socket
        self.running = True
    
    def receive_complete_message(self, sock):
        """接收完整的JSON消息"""
        buffer = b""
        while True:
            try:
                data = sock.recv(1024)
                if not data:
                    return None
                
                buffer += data
                try:
                    message = json.loads(buffer.decode())
                    return message
                except json.JSONDecodeError:
                    continue
            except:
                return None

    def run(self):
        try:
            while self.running:
                message = self.receive_complete_message(self.socket)
                if message:
                    self.message_received.emit(message)
                else:
                    self.connection_closed.emit()
                    break
        except Exception as e:
            if self.running:
                self.error_occurred.emit(str(e))
    
    def stop(self):
        self.running = False

class UserListWidget(QWidget):
    """用户列表组件"""
    user_clicked = pyqtSignal(str)
    voice_call_clicked = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()
        self.user_list.itemClicked.connect(self.on_user_clicked)
    
    def on_user_clicked(self, item):
        username = item.text()
        self.user_clicked.emit(username)
    
    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.title_label = QLabel("在线用户 (0)")
        self.title_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 14px;
                color: #5d4037;
                padding: 10px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #f5deb3, stop:1 #d2b48c);
                border-bottom: 2px solid #a1887f;
            }
        """)
        layout.addWidget(self.title_label)
        
        # 语音控制按钮
        voice_control_layout = QHBoxLayout()
        
        self.join_room_btn = QPushButton("加入语音房间")
        self.join_room_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #4CAF50, stop:1 #2E7D32);
                color: white;
                border: 1px solid #2E7D32;
                border-radius: 5px;
                padding: 5px;
                font-size: 12px;
                margin: 2px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #66BB6A, stop:1 #388E3C);
            }
        """)
        voice_control_layout.addWidget(self.join_room_btn)
        
        self.leave_room_btn = QPushButton("离开房间")
        self.leave_room_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #f44336, stop:1 #c62828);
                color: white;
                border: 1px solid #c62828;
                border-radius: 5px;
                padding: 5px;
                font-size: 12px;
                margin: 2px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #ef5350, stop:1 #d32f2f);
            }
        """)
        voice_control_layout.addWidget(self.leave_room_btn)
        
        layout.addLayout(voice_control_layout)
        
        self.user_list = QListWidget()
        self.user_list.setStyleSheet("""
            QListWidget {
                background-color: rgba(255, 255, 255, 0.8);
                border: 1px solid #d4b88c;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-bottom: 1px solid #d4b88c;
                color: #5d4037;
                height: 60px;
            }
            QListWidget::item:hover {
                background-color: #f5deb3;
            }
            QListWidget::item:selected {
                background-color: #8b4513;
                color: white;
            }
        """)
        layout.addWidget(self.user_list)
        
        # 连接按钮信号
        self.join_room_btn.clicked.connect(self.join_voice_room)
        self.leave_room_btn.clicked.connect(self.leave_voice_room)
    
    def join_voice_room(self):
        self.voice_call_clicked.emit("join_room")
    
    def leave_voice_room(self):
        self.voice_call_clicked.emit("leave_room")
    
    def update_users(self, users, current_user):
        users_list = list(users)
        
        if current_user and current_user not in users_list:
            users_list.append(current_user)
        
        self.title_label.setText(f"在线用户 ({len(users_list)})")
        self.user_list.clear()
        
        # 添加聊天室选项
        chat_room_item = QListWidgetItem("聊天室")
        chat_room_item.setForeground(Qt.blue)
        chat_room_item.setFont(QFont("Arial", 14, QFont.Bold))
        self.user_list.addItem(chat_room_item)
        
        # 添加语音房间选项
        voice_room_item = QListWidgetItem("语音聊天室")
        voice_room_item.setForeground(Qt.darkGreen)
        voice_room_item.setFont(QFont("Arial", 14, QFont.Bold))
        self.user_list.addItem(voice_room_item)
        
        separator_item = QListWidgetItem()
        separator_item.setFlags(Qt.NoItemFlags)
        separator_item.setSizeHint(QSize(10, 5))
        self.user_list.addItem(separator_item)
        
        # 添加在线用户
        for user in users_list:
            item = QListWidgetItem(user)
            if user == current_user:
                item.setText(f"{user} (我)")
                item.setForeground(Qt.green)
            
            item.setData(Qt.UserRole, user)
            self.user_list.addItem(item)

class VoiceCallDialog(QDialog):
    """语音通话对话框"""
    accepted = pyqtSignal()
    rejected = pyqtSignal()
    ended = pyqtSignal()
    
    def __init__(self, parent=None, caller=None, is_incoming=False):
        super().__init__(parent)
        self.caller = caller
        self.is_incoming = is_incoming
        self.parent_window = parent
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle("语音通话")
        self.setFixedSize(300, 200)
        
        layout = QVBoxLayout(self)
        
        # 显示通话信息
        if self.is_incoming:
            info_text = f"来电: {self.caller}"
        else:
            info_text = f"正在呼叫: {self.caller}"
        
        self.info_label = QLabel(info_text)
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #333;
                padding: 20px;
            }
        """)
        layout.addWidget(self.info_label)
        
        # 计时器标签
        self.timer_label = QLabel("00:00")
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #4CAF50;
            }
        """)
        self.timer_label.hide()
        layout.addWidget(self.timer_label)
        
        # 按钮布局
        self.button_layout = QHBoxLayout()
        
        if self.is_incoming:
            # 来电界面
            self.accept_btn = QPushButton("接听")
            self.accept_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                              stop:0 #4CAF50, stop:1 #2E7D32);
                    color: white;
                    border-radius: 20px;
                    padding: 10px 20px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                              stop:0 #66BB6A, stop:1 #388E3C);
                }
            """)
            self.button_layout.addWidget(self.accept_btn)
            
            self.reject_btn = QPushButton("拒绝")
            self.reject_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                              stop:0 #f44336, stop:1 #c62828);
                    color: white;
                    border-radius: 20px;
                    padding: 10px 20px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                              stop:0 #ef5350, stop:1 #d32f2f);
                }
            """)
            self.button_layout.addWidget(self.reject_btn)
            
        else:
            # 去电界面
            self.end_btn = QPushButton("挂断")
            self.end_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                              stop:0 #f44336, stop:1 #c62828);
                    color: white;
                    border-radius: 20px;
                    padding: 10px 20px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                              stop:0 #ef5350, stop:1 #d32f2f);
                }
            """)
            self.button_layout.addWidget(self.end_btn)
        
        layout.addLayout(self.button_layout)
        
        # 状态标签
        self.status_label = QLabel("等待响应..." if not self.is_incoming else "来电中...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 计时器
        self.call_start_time = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)
        
        # 连接信号
        if self.is_incoming:
            self.accept_btn.clicked.connect(self.accept_call)
            self.reject_btn.clicked.connect(self.reject_call)
        else:
            self.end_btn.clicked.connect(self.end_call)
    
    def start_timer(self):
        """开始计时"""
        self.call_start_time = QDateTime.currentDateTime()
        self.timer.start(1000)
    
    def update_timer(self):
        """更新计时器"""
        if self.call_start_time:
            elapsed = self.call_start_time.secsTo(QDateTime.currentDateTime())
            minutes = elapsed // 60
            seconds = elapsed % 60
            self.timer_label.setText(f"{minutes:02d}:{seconds:02d}")
    
    def accept_call(self):
        """接听电话（来电对话框）或确认通话接受（去电对话框）"""
        # 防止重复调用
        if hasattr(self, '_call_accepted') and self._call_accepted:
            return
        self._call_accepted = True
        
        print("[对话框] 通话被接受")
        
        # 更新信息标签
        self.info_label.setText(f"与 {self.caller} 通话中...")
        self.timer_label.show()
        self.start_timer()
        
        if self.is_incoming:
            # 来电对话框：将接受/拒绝按钮替换为挂断按钮
            if hasattr(self, 'accept_btn') and hasattr(self, 'reject_btn'):
                # 隐藏接受和拒绝按钮
                self.accept_btn.hide()
                self.reject_btn.hide()
                
                # 创建挂断按钮
                self.end_btn = QPushButton("挂断")
                self.end_btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                  stop:0 #f44336, stop:1 #c62828);
                        color: white;
                        border-radius: 20px;
                        padding: 10px 20px;
                        font-size: 14px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                  stop:0 #ef5350, stop:1 #d32f2f);
                    }
                """)
                
                # 添加挂断按钮到按钮布局
                self.button_layout.addWidget(self.end_btn)
                
                # 连接挂断信号
                self.end_btn.clicked.connect(self.end_call)
            
            self.accepted.emit()
        else:
            # 去电对话框：不需要修改按钮，已经有挂断按钮
            print("[对话框] 去电对话框确认通话接受")
    
    def reject_call(self):
        """拒绝电话"""
        print("[对话框] 用户拒绝电话")
        self.info_label.setText("已拒绝")
        self.rejected.emit()
        self.close()
    
    def end_call(self):
        """结束电话"""
        print("[对话框] 用户结束通话")
        self.info_label.setText("通话结束")
        
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
        
        self.ended.emit()
        self.close()
    
    def closeEvent(self, event):
        """关闭事件"""
        print("[对话框] 对话框关闭")
        if hasattr(self, 'timer') and self.timer and self.timer.isActive():
            self.timer.stop()
        super().closeEvent(event)

class ChatClient(QMainWindow):
    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.username = None
        self.socket = None
        self.receive_thread = None
        self.connection_status = False
        self.message_count = 0
        self.is_dark_theme = False
        self.received_files = {}
        
        # 语音相关
        self.voice_client = None
        self.voice_port = None
        self.in_voice_call = False
        self.in_voice_room = False
        self.current_call_dialog = None
        self.is_calling = False
        self.is_receiving_call = False
        
        # 音频设备索引
        self.audio_input_device_index = -1
        self.audio_output_device_index = -1
        
        self.messages = {
            "chat_room": [],
            "private": {}
        }
        
        self.initUI()
    
    def initUI(self):
        """初始化用户界面"""
        self.setWindowTitle("精美网络聊天室 - 语音版")
        self.setGeometry(100, 100, 1100, 750)
        self.setMinimumSize(900, 650)
        
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #f4e3c9,
                                          stop:0.25 #e6c89e,
                                          stop:0.5 #f4e3c9,
                                          stop:0.75 #e6c89e,
                                          stop:1 #f4e3c9);
                background-repeat: repeat;
            }
            * {
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            }
        """)
        
        # 创建菜单栏
        self.createMenuBar()
        
        # 创建状态栏
        self.createStatusBar()
        
        # 主容器
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        central_widget.setStyleSheet("""
            QWidget#centralWidget {
                background-color: white;
                border-radius: 15px;
                margin: 10px;
            }
        """)
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧聊天区域
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(20, 20, 20, 20)
        chat_layout.setSpacing(15)
        
        # 标题区域
        title_frame = QFrame()
        title_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                          stop:0 #8d6e63, stop:1 #6d4c41);
                border: 2px solid #a1887f;
                border-radius: 10px;
                padding: 10px;
            }
        """)
        title_layout = QHBoxLayout(title_frame)
        
        title_icon = QLabel("💬")
        title_icon.setStyleSheet("font-size: 24px;")
        title_layout.addWidget(title_icon)
        
        self.title_label = QLabel("网络聊天室")
        self.title_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: white;
                padding-left: 10px;
            }
        """)
        title_layout.addWidget(self.title_label)
        
        title_layout.addStretch()
        
        # 语音状态指示器
        self.voice_status_label = QLabel("🔇")
        self.voice_status_label.setStyleSheet("""
            QLabel {
                font-size: 20px;
                color: #666;
                padding: 0 10px;
            }
        """)
        self.voice_status_label.setToolTip("语音状态: 未连接")
        title_layout.addWidget(self.voice_status_label)
        
        # 连接状态指示器
        self.connection_indicator = QLabel("●")
        self.connection_indicator.setStyleSheet("""
            QLabel {
                font-size: 20px;
                color: #ff6b6b;
            }
        """)
        title_layout.addWidget(self.connection_indicator)
        
        chat_layout.addWidget(title_frame)
        
        # 消息显示区域
        message_group = QGroupBox("聊天记录")
        message_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #5d4037;
                border: 2px solid #d4b88c;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
                background-color: rgba(255, 255, 255, 0.8);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
            }
        """)
        message_layout = QVBoxLayout(message_group)
        
        self.message_area = QTextBrowser()
        self.message_area.setReadOnly(True)
        self.message_area.setStyleSheet("""
            QTextBrowser {
                background-color: #fafafa;
                border: 1px solid #d4b88c;
                border-radius: 8px;
                font-size: 14px;
                padding: 10px;
                selection-background-color: #8b4513;
            }
        """)
        self.message_area.setLineWrapMode(QTextBrowser.WidgetWidth)
        self.message_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.message_area.anchorClicked.connect(self.handle_anchor_click)
        message_layout.addWidget(self.message_area)
        
        chat_layout.addWidget(message_group)
        
        # 输入区域
        input_group = QGroupBox("发送消息")
        input_group.setStyleSheet(message_group.styleSheet())
        input_layout = QVBoxLayout(input_group)
        
        # 消息输入框
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("请输入消息... (按Ctrl+Enter换行，Enter发送)")
        self.input_edit.setStyleSheet("""
            QLineEdit {
                background-color: white;
                border: 2px solid #d4b88c;
                border-radius: 8px;
                font-size: 14px;
                padding: 12px;
                selection-background-color: #8b4513;
            }
            QLineEdit:focus {
                border-color: #8b4513;
            }
        """)
        self.input_edit.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_edit)
        
        # 按钮工具栏
        button_toolbar = QHBoxLayout()
        
        self.send_btn = QPushButton("发送消息")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #8d6e63, stop:1 #5d4037);
                color: white;
                border: 2px solid #a1887f;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #a1887f, stop:1 #6d4c41);
                border-color: #8b4513;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #5d4037, stop:1 #8d6e63);
            }
            QPushButton:disabled {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #d7ccc8, stop:1 #bcaaa4);
                border-color: #a1887f;
                color: #bdbdbd;
            }
        """)
        self.send_btn.clicked.connect(self.send_message)
        button_toolbar.addWidget(self.send_btn)
        
        # 语音通话按钮
        self.voice_call_btn = QToolButton()
        self.voice_call_btn.setText("语音通话")
        self.voice_call_btn.setToolTip("发起语音通话")
        self.voice_call_btn.setStyleSheet("""
            QToolButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #2196F3, stop:1 #1976D2);
                border: 1px solid #1976D2;
                border-radius: 6px;
                padding: 8px;
                margin: 2px;
                color: white;
                font-weight: bold;
            }
            QToolButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #42A5F5, stop:1 #2196F3);
            }
        """)
        self.voice_call_btn.clicked.connect(self.start_voice_call)
        button_toolbar.addWidget(self.voice_call_btn)
        
        button_style = """
            QToolButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #f5deb3, stop:1 #d2b48c);
                border: 1px solid #a1887f;
                border-radius: 6px;
                padding: 8px;
                margin: 2px;
                color: #5d4037;
                font-weight: bold;
            }
            QToolButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #d2b48c, stop:1 #a1887f);
                color: white;
            }
            QToolButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #a1887f, stop:1 #8d6e63);
                color: white;
            }
        """
        
        self.users_btn = QToolButton()
        self.users_btn.setText("用户")
        self.users_btn.setToolTip("查看在线用户")
        self.users_btn.setStyleSheet(button_style)
        self.users_btn.clicked.connect(self.show_online_users)
        button_toolbar.addWidget(self.users_btn)
        
        self.private_btn = QToolButton()
        self.private_btn.setText("私聊")
        self.private_btn.setToolTip("开始私聊")
        self.private_btn.setStyleSheet(button_style)
        self.private_btn.clicked.connect(self.start_private_chat)
        button_toolbar.addWidget(self.private_btn)
        
        self.clear_btn = QToolButton()
        self.clear_btn.setText("清空")
        self.clear_btn.setToolTip("清空聊天记录")
        self.clear_btn.setStyleSheet(button_style)
        self.clear_btn.clicked.connect(self.clear_chat)
        button_toolbar.addWidget(self.clear_btn)
        
        self.emoji_btn = QToolButton()
        self.emoji_btn.setText("表情")
        self.emoji_btn.setToolTip("选择表情")
        self.emoji_btn.setStyleSheet(button_style)
        self.emoji_btn.clicked.connect(self.show_emoji_picker)
        button_toolbar.addWidget(self.emoji_btn)
        
        self.image_btn = QToolButton()
        self.image_btn.setText("图片")
        self.image_btn.setToolTip("发送图片")
        self.image_btn.setStyleSheet(button_style)
        self.image_btn.clicked.connect(self.upload_image)
        button_toolbar.addWidget(self.image_btn)
        
        self.file_btn = QToolButton()
        self.file_btn.setText("文件")
        self.file_btn.setToolTip("发送文件")
        self.file_btn.setStyleSheet(button_style)
        self.file_btn.clicked.connect(self.upload_file)
        button_toolbar.addWidget(self.file_btn)
        
        button_toolbar.addStretch()
        
        # 消息统计
        self.message_counter = QLabel("消息: 0")
        self.message_counter.setStyleSheet("color: #666; font-size: 12px;")
        button_toolbar.addWidget(self.message_counter)
        
        input_layout.addLayout(button_toolbar)
        
        chat_layout.addWidget(input_group)
        
        # 将聊天区域添加到分割器
        splitter.addWidget(chat_widget)
        
        # 右侧用户列表区域
        self.user_list_widget = UserListWidget()
        self.user_list_widget.user_clicked.connect(self.on_user_clicked)
        self.user_list_widget.voice_call_clicked.connect(self.on_voice_action)
        
        # 用户列表右键菜单
        self.user_list_widget.user_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.user_list_widget.user_list.customContextMenuRequested.connect(self.show_user_context_menu)
        
        user_container = QWidget()
        user_layout = QVBoxLayout(user_container)
        user_layout.setContentsMargins(10, 10, 10, 10)
        user_layout.addWidget(self.user_list_widget)
        
        splitter.addWidget(user_container)
        
        self.chat_mode = "chat_room"
        self.current_chat_partner = None
        splitter.setSizes([750, 250])
        
        main_layout.addWidget(splitter)
        
        # 创建系统托盘图标
        self.createSystemTray()
        
        # 初始化定时器
        self.user_refresh_timer = QTimer(self)
        self.user_refresh_timer.timeout.connect(self.show_online_users)
        self.user_refresh_timer.start(5000)
    
    def createMenuBar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #f5deb3, stop:1 #d2b48c);
                padding: 5px;
                border-bottom: 2px solid #a1887f;
            }
            QMenuBar::item {
                padding: 8px 15px;
                border-radius: 4px;
                color: #5d4037;
            }
            QMenuBar::item:selected {
                background-color: #d2b48c;
                color: #3d2e22;
            }
            QMenu {
                background-color: rgba(255, 255, 255, 0.9);
                border: 1px solid #d4b88c;
                border-radius: 5px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 25px 8px 20px;
                color: #5d4037;
            }
            QMenu::item:selected {
                background-color: #8b4513;
                color: white;
            }
        """)
        
        # 文件菜单
        file_menu = menubar.addMenu('文件')
        
        connect_action = QAction('连接服务器', self)
        connect_action.triggered.connect(self.reconnect)
        file_menu.addAction(connect_action)
        
        disconnect_action = QAction('断开连接', self)
        disconnect_action.triggered.connect(self.disconnect)
        file_menu.addAction(disconnect_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('退出', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 语音菜单
        voice_menu = menubar.addMenu('语音')
        
        voice_call_action = QAction('发起语音通话', self)
        voice_call_action.triggered.connect(self.start_voice_call)
        voice_menu.addAction(voice_call_action)
        
        join_room_action = QAction('加入语音房间', self)
        join_room_action.triggered.connect(self.join_voice_room)
        voice_menu.addAction(join_room_action)
        
        leave_room_action = QAction('离开语音房间', self)
        leave_room_action.triggered.connect(self.leave_voice_room)
        voice_menu.addAction(leave_room_action)
        
        voice_menu.addSeparator()
        
        # 新增：音频设备配置
        audio_devices_action = QAction('音频设备信息', self)
        audio_devices_action.triggered.connect(self.test_audio_devices)
        voice_menu.addAction(audio_devices_action)
        
        config_audio_action = QAction('配置音频设备', self)
        config_audio_action.triggered.connect(self.configure_audio_devices)
        voice_menu.addAction(config_audio_action)
        

        
        
        # 视图菜单
        view_menu = menubar.addMenu('视图')
        
        theme_action = QAction('切换主题', self)
        theme_action.triggered.connect(self.toggle_theme)
        view_menu.addAction(theme_action)
        
        font_action = QAction('字体设置', self)
        font_action.triggered.connect(self.change_font)
        view_menu.addAction(font_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu('帮助')
        
        about_action = QAction('关于', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def createStatusBar(self):
        """创建状态栏"""
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # 连接状态
        self.status_label = QLabel("未连接")
        self.status_label.setStyleSheet("color: #666; padding: 5px;")
        self.statusBar.addWidget(self.status_label)
        
        # 语音状态
        self.voice_status = QLabel("🔇 语音: 离线")
        self.voice_status.setStyleSheet("color: #666; padding: 5px;")
        self.statusBar.addWidget(self.voice_status)
        
        self.statusBar.addPermanentWidget(QLabel("|"))
        
        # 用户信息
        self.user_label = QLabel("用户: 未登录")
        self.user_label.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 14px; padding: 5px;")
        self.statusBar.addPermanentWidget(self.user_label)
        
        self.statusBar.addPermanentWidget(QLabel("|"))
        
        # 时间显示
        self.time_label = QLabel()
        self.time_label.setStyleSheet("color: #2196F3; font-weight: bold; font-size: 14px; padding: 5px;")
        self.statusBar.addPermanentWidget(self.time_label)
        
        # 更新时间
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
    
    def update_time(self):
        """更新时间显示"""
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.setText(current_time)
    
    def update_connection_status(self, connected):
        """更新连接状态显示"""
        self.connection_status = connected
        if connected:
            self.status_label.setText("已连接")
            self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold; padding: 5px;")
            self.connection_indicator.setStyleSheet("color: #4CAF50; font-size: 20px;")
            self.send_btn.setEnabled(True)
        else:
            self.status_label.setText("未连接")
            self.status_label.setStyleSheet("color: #ff6b6b; font-weight: bold; padding: 5px;")
            self.connection_indicator.setStyleSheet("color: #ff6b6b; font-size: 20px;")
            self.send_btn.setEnabled(False)
    
    def update_voice_status(self, status, color="#666"):
        """更新语音状态显示"""
        status_icons = {
            "离线": "🔇",
            "连接中": "🔊",
            "通话中": "📞",
            "在房间中": "🏠"
        }
        
        icon = status_icons.get(status, "🔊")
        self.voice_status.setText(f"{icon} 语音: {status}")
        self.voice_status.setStyleSheet(f"color: {color}; font-weight: bold; padding: 5px;")
        self.voice_status_label.setText(icon)
    
    def connect_to_server(self):
        """连接到服务器"""
        try:
            self.update_connection_status(False)
            
            # 清理现有连接
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            
            if self.receive_thread:
                self.receive_thread.stop()
                self.receive_thread = None
            
            # 创建新连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            
            try:
                sock.connect((self.host, self.port))
                sock.settimeout(None)
                
                # 获取用户名
                username, ok = QInputDialog.getText(
                    self, "用户名", "请输入用户名:", QLineEdit.Normal, ""
                )
                if not ok:
                    sock.close()
                    return
                
                username = username.strip()
                if not username:
                    QMessageBox.warning(self, "警告", "用户名不能为空")
                    sock.close()
                    return
                
                # 发送用户名
                sock.sendall(json.dumps({'username': username}).encode())
                
                # 接收响应
                buffer = b""
                while True:
                    data = sock.recv(1024)
                    if not data:
                        QMessageBox.warning(self, "错误", "连接失败")
                        sock.close()
                        return
                    
                    buffer += data
                    try:
                        resp_data = json.loads(buffer.decode())
                        
                        if resp_data.get('status') == 'success':
                            self.username = username
                            self.user_label.setText(f"用户: {username}")
                            self.socket = sock
                            
                            # 获取语音服务器端口
                            self.voice_port = resp_data.get('voice_port', 8889)
                            
                            # 连接到语音服务器
                            self.connect_to_voice_server()
                            
                            # 启动接收线程
                            self.receive_thread = ReceiveThread(self.socket)
                            self.receive_thread.message_received.connect(self.handle_server_message)
                            self.receive_thread.error_occurred.connect(self.handle_error)
                            self.receive_thread.connection_closed.connect(self.on_connection_closed)
                            self.receive_thread.start()
                            
                            self.update_connection_status(True)
                            self.display_message({
                                'sender': "系统",
                                'message': resp_data.get('message', '连接成功'),
                                'type': 'system',
                                'timestamp': datetime.datetime.now().isoformat()
                            })
                            
                            self.user_list_widget.update_users([], self.username)
                            self.show_online_users()
                            
                            return
                        else:
                            error_msg = resp_data.get('message', '连接失败')
                            QMessageBox.warning(self, "错误", error_msg)
                            sock.close()
                            return
                    except json.JSONDecodeError:
                        continue
                            
            except socket.timeout:
                QMessageBox.critical(self, "连接错误", "连接超时")
                sock.close()
            except ConnectionRefusedError:
                QMessageBox.critical(self, "连接错误", "无法连接到服务器")
                sock.close()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"连接失败: {str(e)}")
                sock.close()
                
        except Exception as e:
            QMessageBox.critical(self, "连接错误", f"连接过程中发生错误: {str(e)}")
    
    def connect_to_voice_server(self):
        """连接到语音服务器"""
        try:
            # 先断开旧的信号连接（如果存在）
            if hasattr(self, 'voice_client') and self.voice_client:
                try:
                    self.voice_client.call_incoming.disconnect(self.on_call_incoming)
                except:
                    pass
                try:
                    self.voice_client.call_accepted.disconnect(self.on_call_accepted)
                except:
                    pass
                try:
                    self.voice_client.call_rejected.disconnect(self.on_call_rejected)
                except:
                    pass
                try:
                    self.voice_client.call_ended.disconnect(self.on_call_ended)
                except:
                    pass
                # 断开旧的连接
                self.voice_client.disconnect()
            
            print(f"[主程序] 连接到语音服务器: {self.host}:{self.voice_port}")
            # 将用户选择的音频设备索引传递给VoiceClient
            self.voice_client = VoiceClient(self.host, self.voice_port, self.username, 
                                          self.audio_input_device_index, 
                                          self.audio_output_device_index)
            
            # 连接新的信号
            self.voice_client.call_incoming.connect(self.on_call_incoming)
            self.voice_client.call_accepted.connect(self.on_call_accepted)
            self.voice_client.call_rejected.connect(self.on_call_rejected)
            self.voice_client.call_ended.connect(self.on_call_ended)
            
            if self.voice_client.connect():
                self.update_voice_status("连接中", "#2196F3")
                QTimer.singleShot(1000, lambda: self.update_voice_status("离线", "#4CAF50"))
                print("[主程序] 语音服务器连接成功")
            else:
                self.update_voice_status("离线", "#f44336")
                QMessageBox.warning(self, "警告", "语音服务器连接失败，语音功能不可用")
                
        except Exception as e:
            print(f"[主程序] 语音服务器连接错误: {e}")
            self.update_voice_status("离线", "#f44336")
    
    def on_call_incoming(self, caller):
        """处理来电"""
        print(f"[主程序] 来电: {caller}")
        
        # 检查是否已在通话中
        if self.in_voice_call:
            print("[主程序] 已在通话中，忽略来电")
            return
        
        # 检查是否正在呼叫
        if self.is_calling:
            print("[主程序] 正在呼叫他人，忽略来电")
            return
        
        # 检查是否已收到来电
        if self.is_receiving_call:
            print("[主程序] 已收到来电，忽略新来电")
            return
        
        # 激活主窗口
        self.showNormal()
        self.activateWindow()
        self.raise_()
        
        # 接受来电
        QTimer.singleShot(0, lambda: self.accept_incoming_call(caller))
    
    def on_call_accepted(self, callee):
        """通话被接受"""
        print(f"[主程序] 通话被接受: {callee}")
        print(f"[主程序] 当前通话对话框: {self.current_call_dialog}")
        print(f"[主程序] 呼叫状态: {self.is_calling}")
        print(f"[主程序] 通话状态: {self.in_voice_call}")
        
        # 直接在回调中更新状态，不依赖UI线程
        self.in_voice_call = True
        self.is_calling = False
        
        # 更新UI状态（这里可以直接调用，因为已经在主线程中）
        try:
            print(f"[主程序] 正在更新UI: {callee}")
            self.update_voice_status("通话中", "#4CAF50")
            print(f"[主程序] 更新后的呼叫状态: {self.is_calling}")
            print(f"[主程序] 更新后的通话状态: {self.in_voice_call}")
            
            # 更新通话对话框（如果存在）
            if self.current_call_dialog is not None:
                print(f"[主程序] 正在更新通话对话框状态: {self.current_call_dialog}")
                self.current_call_dialog.accept_call()
                print(f"[主程序] 通话对话框状态更新完成")
            else:
                print(f"[主程序] 通话对话框不存在，仅更新状态")
            
            # 显示通知
            QMessageBox.information(self, "提示", f"{callee} 已接听您的通话")
            print(f"[主程序] 通话状态更新完成")
        except Exception as e:
            print(f"[主程序] 更新UI失败: {e}")
            import traceback
            traceback.print_exc()
    
    def on_call_rejected(self, callee):
        """通话被拒绝"""
        print(f"[主程序] 通话被拒绝: {callee}")
        
        # 更新状态
        self.is_calling = False
        
        # 清理对话框
        if self.current_call_dialog:
            def cleanup_dialog():
                try:
                    self.current_call_dialog.close()
                except:
                    pass
                finally:
                    self.current_call_dialog = None
            
            QTimer.singleShot(0, cleanup_dialog)
        
        # 显示通知
        QMessageBox.information(self, "提示", f"{callee} 拒绝了您的通话请求")
    
    def on_call_ended(self, user):
        """通话结束"""
        print(f"[主程序] 通话结束: {user}")
        
        # 安全结束音频流（与主动挂断逻辑保持一致）
        if self.voice_client:
            print("[主程序] 被动挂断时安全结束音频流")
            try:
                self.voice_client.safe_end_audio()
            except Exception as e:
                print(f"[主程序] 结束音频流时出错: {e}")
                import traceback
                traceback.print_exc()
        
        # 确保在主线程中更新UI和状态
        def update_ui():
            try:
                # 更新状态
                self.in_voice_call = False
                self.is_calling = False
                self.is_receiving_call = False
                self.update_voice_status("离线", "#666")
                
                # 清理对话框（如果存在）
                dialog_closed = False
                if hasattr(self, 'current_call_dialog') and self.current_call_dialog is not None:
                        try:
                            # 更安全的方式检查Qt对象是否仍然有效
                            from PyQt5.QtCore import QObject
                            if isinstance(self.current_call_dialog, QObject):
                                # 检查对话框是否仍然存在且可见
                                if hasattr(self.current_call_dialog, 'isVisible') and callable(getattr(self.current_call_dialog, 'isVisible')):
                                    try:
                                        self.current_call_dialog.close()
                                        dialog_closed = True
                                    except RuntimeError as e:
                                        # 捕获Qt对象已被销毁的异常
                                        print(f"[主程序] 对话框已被销毁: {e}")
                        except RuntimeError as e:
                            # 捕获Qt对象已被销毁的异常
                            print(f"[主程序] 对话框已被销毁: {e}")
                        except Exception as e:
                            print(f"[主程序] 关闭对话框失败: {e}")
                        finally:
                            self.current_call_dialog = None
                
                # 只有在对话框未关闭时才显示通知（防止重复通知）
                if not dialog_closed:
                    QMessageBox.information(self, "提示", f"与 {user} 的通话已结束")
                print(f"[主程序] 通话结束状态更新完成")
            except Exception as e:
                print(f"[主程序] 更新UI失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 使用QTimer确保在主线程执行
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, update_ui)
    
    def accept_incoming_call(self, caller):
        """接受来电"""
        if not self.voice_client:
            QMessageBox.warning(self, "错误", "语音服务未连接")
            return
        
        if self.in_voice_call:
            QMessageBox.information(self, "提示", "您已经在通话中")
            return
        
        # 设置接收状态
        self.is_receiving_call = True
        
        # 创建通话对话框
        self.current_call_dialog = VoiceCallDialog(self, caller, True)
        
        # 连接信号
        def on_dialog_accepted():
            print(f"[主程序] 用户接受来电: {caller}")
            if self.voice_client.accept_call(caller):
                self.in_voice_call = True
                self.is_receiving_call = False
                self.update_voice_status("通话中", "#4CAF50")
                print(f"[主程序] 已接受与 {caller} 的通话")
            else:
                QMessageBox.warning(self, "错误", "接受通话失败")
                self.is_receiving_call = False
                self.current_call_dialog = None
        
        def on_dialog_rejected():
            print(f"[主程序] 用户拒绝来电: {caller}")
            if self.voice_client.reject_call(caller):
                self.is_receiving_call = False
                self.current_call_dialog = None
            else:
                QMessageBox.warning(self, "错误", "拒绝通话失败")
        
        def on_dialog_ended():
            print(f"[主程序] 来电对话框结束")
            self.end_current_call()
        
        self.current_call_dialog.accepted.connect(on_dialog_accepted)
        self.current_call_dialog.rejected.connect(on_dialog_rejected)
        self.current_call_dialog.ended.connect(on_dialog_ended)
        self.current_call_dialog.show()
    
    def handle_server_message(self, message_data):
        """处理来自服务器的消息"""
        msg_type = message_data.get('type', 'broadcast')
        
        if msg_type == 'system':
            msg = {
                'sender': "系统",
                'message': message_data.get('message', ''),
                'type': 'system',
                'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat())
            }
            self.messages["chat_room"].append(msg)
            
            if self.chat_mode == "chat_room":
                self.display_message(msg)
                
        elif msg_type == 'voice_status':
            sender = message_data.get('sender', '')
            status = message_data.get('status', '')
            target = message_data.get('target', '')
            
            if target == self.username:
                status_msg = {
                    'sender': "系统",
                    'message': f"{sender} {status}",
                    'type': 'system',
                    'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat())
                }
                self.display_message(status_msg)
                
                # 检查是否是来电通知
                if status == "正在呼叫您":
                    print(f"[主程序] 收到语音呼叫通知: {sender}")
                    QTimer.singleShot(0, lambda s=sender: self.on_call_incoming(s))
                
        elif msg_type == 'private':
            sender = message_data.get('sender', '')
            msg = {
                'sender': sender,
                'message': message_data.get('message', ''),
                'type': 'private',
                'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat())
            }
            
            if sender not in self.messages["private"]:
                self.messages["private"][sender] = []
            self.messages["private"][sender].append(msg)
            
            if self.chat_mode == "private" and self.current_chat_partner == sender:
                self.display_message(msg)
            else:
                self.display_message({
                    'sender': "系统",
                    'message': f"💬 您收到了来自 {sender} 的私聊消息，请点击用户列表查看",
                    'type': 'system',
                    'timestamp': datetime.datetime.now().isoformat()
                })
                
        elif msg_type == 'private_sent':
            target = message_data.get('target', '')
            msg = {
                'sender': "系统",
                'message': message_data.get('message', ''),
                'type': 'private',
                'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat())
            }
            
            if target not in self.messages["private"]:
                self.messages["private"][target] = []
            self.messages["private"][target].append(msg)
            
            if self.chat_mode == "private" and self.current_chat_partner == target:
                self.display_message(msg)
                
        elif msg_type == 'users':
            users = message_data.get('users', [])
            self.user_list_widget.update_users(users, self.username)
            
        elif msg_type in ['broadcast', 'message']:
            msg = {
                'sender': message_data.get('sender', '未知'),
                'message': message_data.get('message', ''),
                'type': 'broadcast',
                'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat())
            }
            self.messages["chat_room"].append(msg)
            
            if self.chat_mode == "chat_room":
                self.display_message(msg)
        
        elif msg_type == 'file_receive':
            sender = message_data.get('sender', '未知')
            file_name = message_data.get('file_name', '未知文件')
            file_size = message_data.get('file_size', 0)
            file_content = message_data.get('file_content', '')
            private = message_data.get('private', False)
            
            # 如果是自己发送的文件，跳过显示（避免重复）
            if sender == self.username:
                print(f"[文件] 收到自己发送的文件，跳过显示: {file_name}")
                return
            
            # 处理文件（不预加载到磁盘，存储到内存字典）
            try:
                # 生成唯一文件ID
                import uuid
                file_id = str(uuid.uuid4())
                
                # 存储文件元数据到内存字典
                self.received_files[file_id] = {
                    'file_name': file_name,
                    'file_size': file_size,
                    'file_content': file_content,
                    'sender': sender,
                    'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat())
                }
                
                # 显示文件接收消息
                message = f"发送了文件: {file_name} ({self.format_file_size(file_size)})"
                if private:
                    target = message_data.get('target', '')
                    # 对于接收者，应该将消息存储在发送者对应的字典键下，而不是目标用户（自己）
                    # 这样在切换到与发送者的聊天界面时才能看到消息
                    if sender not in self.messages["private"]:
                        self.messages["private"][sender] = []
                    self.messages["private"][sender].append({
                        'sender': sender,
                        'message': message,
                        'type': 'private',
                        'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat()),
                        'file_id': file_id,
                        'file_name': file_name
                    })
                    
                    if self.chat_mode == "private" and self.current_chat_partner == sender:
                        self.display_message({
                            'sender': sender,
                            'message': message,
                            'type': 'private',
                            'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat()),
                            'file_id': file_id,
                            'file_name': file_name
                        })
                else:
                    self.messages["chat_room"].append({
                        'sender': sender,
                        'message': message,
                        'type': 'broadcast',
                        'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat()),
                        'file_id': file_id,
                        'file_name': file_name
                    })
                    
                    if self.chat_mode == "chat_room":
                        self.display_message({
                            'sender': sender,
                            'message': message,
                            'type': 'broadcast',
                            'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat()),
                            'file_id': file_id,
                            'file_name': file_name
                        })
            except Exception as e:
                print(f"[错误] 保存文件失败: {e}")
                QMessageBox.warning(self, "错误", f"保存文件失败: {str(e)}")
        
        elif msg_type == 'image_receive':
            sender = message_data.get('sender', '未知')
            image_name = message_data.get('image_name', '未知图片')
            image_content = message_data.get('image_content', '')
            private = message_data.get('private', False)
            
            # 如果是自己发送的图片，跳过显示（避免重复）
            if sender == self.username:
                print(f"[图片] 收到自己发送的图片，跳过显示: {image_name}")
                return
            
            # 保存图片
            try:
                # 创建保存目录
                save_dir = os.path.join(os.getcwd(), 'received_images')
                if not os.path.exists(save_dir):
                    os.makedirs(save_dir)
                
                # 保存图片
                image_path = os.path.join(save_dir, image_name)
                with open(image_path, 'wb') as f:
                    f.write(base64.b64decode(image_content))
                
                # 显示图片接收消息
                message = f"发送了图片: {image_name}"
                if private:
                    target = message_data.get('target', '')
                    # 对于接收者，应该将消息存储在发送者对应的字典键下，而不是目标用户（自己）
                    # 这样在切换到与发送者的聊天界面时才能看到消息
                    if sender not in self.messages["private"]:
                        self.messages["private"][sender] = []
                    self.messages["private"][sender].append({
                        'sender': sender,
                        'message': message,
                        'type': 'private',
                        'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat()),
                        'image_path': image_path,
                        'image_name': image_name
                    })
                    
                    if self.chat_mode == "private" and self.current_chat_partner == sender:
                        self.display_message({
                            'sender': sender,
                            'message': message,
                            'type': 'private',
                            'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat()),
                            'image_path': image_path,
                            'image_name': image_name
                        })
                    else:
                        self.display_message({
                            'sender': "系统",
                            'message': f"💬 您收到了来自 {sender} 的私聊图片，请点击用户列表查看",
                            'type': 'system',
                            'timestamp': datetime.datetime.now().isoformat()
                        })
                else:
                    self.messages["chat_room"].append({
                        'sender': sender,
                        'message': message,
                        'type': 'broadcast',
                        'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat()),
                        'image_path': image_path,
                        'image_name': image_name
                    })
                    
                    if self.chat_mode == "chat_room":
                        self.display_message({
                            'sender': sender,
                            'message': message,
                            'type': 'broadcast',
                            'timestamp': message_data.get('timestamp', datetime.datetime.now().isoformat()),
                            'image_path': image_path,
                            'image_name': image_name
                        })
            except Exception as e:
                print(f"[错误] 保存图片失败: {e}")
                QMessageBox.warning(self, "错误", f"保存图片失败: {str(e)}")
    
    def display_message(self, message_data):
        """显示消息到聊天区域"""
        sender = message_data.get('sender', '未知')
        message = message_data.get('message', '')
        msg_type = message_data.get('type', 'broadcast')
        timestamp = message_data.get('timestamp', datetime.datetime.now().isoformat())
        
        try:
            dt = datetime.datetime.fromisoformat(timestamp)
            time_str = dt.strftime("%H:%M:%S")
        except:
            time_str = datetime.datetime.now().strftime("%H:%M:%S")
        
        # 处理图片和文件
        image_path = message_data.get('image_path', '')
        file_path = message_data.get('file_path', '')
        file_name = message_data.get('file_name', '')
        
        # 导入URL编码模块
        import urllib.parse
        
        # 生成图片HTML
        if image_path and os.path.exists(image_path):
            # 修复Windows路径格式并进行URL编码
            fixed_image_path = image_path.replace('\\', '/')
            encoded_image_path = urllib.parse.quote(fixed_image_path)
            image_html = f"<div style='margin-top: 5px;'><img src='file:///{encoded_image_path}' style='max-width: 300px; max-height: 200px; border: 1px solid #ddd; padding: 2px; border-radius: 5px;'></div>"
            print(f"[调试] 显示图片: {image_path}, 编码后路径: file:///{encoded_image_path}")
        else:
            image_html = ""
            if image_path:
                print(f"[调试] 图片路径不存在: {image_path}")
        
        # 生成文件下载链接（使用download://协议）
        file_id = message_data.get('file_id', '')
        if file_id and file_name:
            # 使用file_id生成download://链接
            file_html = f"<div style='margin-top: 5px;'><a href='download://{file_id}' style='background-color: #3498db; color: white; text-decoration: none; padding: 5px 10px; border-radius: 3px; font-size: 0.9em; display: inline-block;'>下载文件: {file_name}</a></div>"
            print(f"[调试] 显示文件下载链接: download://{file_id}, 文件名: {file_name}")
        elif file_path and os.path.exists(file_path):
            # 兼容旧的file_path格式
            fixed_file_path = file_path.replace('\\', '/')
            encoded_file_path = urllib.parse.quote(fixed_file_path)
            file_html = f"<div style='margin-top: 5px;'><a href='file:///{encoded_file_path}' style='background-color: #3498db; color: white; text-decoration: none; padding: 5px 10px; border-radius: 3px; font-size: 0.9em; display: inline-block;'>下载文件: {file_name}</a></div>"
            print(f"[调试] 显示文件下载链接: {file_path}, 编码后路径: file:///{encoded_file_path}")
        else:
            file_html = ""
            if file_path:
                print(f"[调试] 文件路径不存在: {file_path}")
        
        self.message_count += 1
        self.message_counter.setText(f"消息: {self.message_count}")
        
        if self.is_dark_theme:
            if msg_type == 'system':
                html = f"""
                    <div style='background-color: #4a4031; border-left: 4px solid #ffc107;
                              padding: 8px; margin: 5px 0; border-radius: 0 5px 5px 0;'>
                        <span style='color: #ffd700; font-size: 0.9em;'>{time_str}</span><br>
                        <span style='color: #ffd700;'><b>📢 {sender}:</b> {message}</span>
                        {image_html}
                        {file_html}
                    </div>
                """
            elif msg_type == 'private':
                html = f"""
                    <div style='background-color: #2c3e50; border-left: 4px solid #3498db;
                              padding: 8px; margin: 5px 0; border-radius: 0 5px 5px 0;'>
                        <span style='color: #3498db; font-size: 0.9em;'>{time_str}</span><br>
                        <span style='color: #3498db;'><b>🔒 {sender}:</b> {message}</span>
                        {image_html}
                        {file_html}
                    </div>
                """
            else:
                if sender == self.username:
                    sender = "我"
                    bg_color = "#2c5f2d"
                    border_color = "#4CAF50"
                    text_color = "#4CAF50"
                    icon = "🗨️"
                else:
                    bg_color = "#3c3c3c"
                    border_color = "#777"
                    text_color = "#ddd"
                    icon = "👤"
                
                html = f"""
                    <div style='background-color: {bg_color}; border-left: 4px solid {border_color};
                              padding: 8px; margin: 5px 0; border-radius: 0 5px 5px 0;'>
                        <div style='color: {text_color}; font-size: 0.9em;'>
                            {time_str} | {icon} <b>{sender}</b>
                        </div>
                        <div style='color: {text_color}; margin-top: 3px;'>{message}</div>
                        {image_html}
                        {file_html}
                    </div>
                """
        else:
            if msg_type == 'system':
                html = f"""
                    <div style='background-color: #fff3cd; border-left: 4px solid #ffc107;
                              padding: 8px; margin: 5px 0; border-radius: 0 5px 5px 0;'>
                        <span style='color: #856404; font-size: 0.9em;'>{time_str}</span><br>
                        <span style='color: #856404;'><b>📢 {sender}:</b> {message}</span>
                        {image_html}
                        {file_html}
                    </div>
                """
            elif msg_type == 'private':
                html = f"""
                    <div style='background-color: #e7f3ff; border-left: 4px solid #2196F3;
                              padding: 8px; margin: 5px 0; border-radius: 0 5px 5px 0;'>
                        <span style='color: #0d47a1; font-size: 0.9em;'>{time_str}</span><br>
                        <span style='color: #0d47a1;'><b>🔒 {sender}:</b> {message}</span>
                        {image_html}
                        {file_html}
                    </div>
                """
            else:
                if sender == self.username:
                    sender = "我"
                    bg_color = "#d4edda"
                    border_color = "#28a745"
                    text_color = "#155724"
                    icon = "🗨️"
                else:
                    bg_color = "#f8f9fa"
                    border_color = "#6c757d"
                    text_color = "#212529"
                    icon = "👤"
                
                html = f"""
                    <div style='background-color: {bg_color}; border-left: 4px solid {border_color};
                      padding: 8px; margin: 5px 0; border-radius: 0 5px 5px 0;'>
                        <div style='color: {text_color}; font-size: 0.9em;'>
                            {time_str} | {icon} <b>{sender}</b>
                        </div>
                        <div style='color: {text_color}; margin-top: 3px;'>{message}</div>
                        {image_html}
                        {file_html}
                    </div>
                """
        
        self.message_area.append(html)
        self.message_area.moveCursor(QTextCursor.End)
    
    def send_message(self):
        """发送消息"""
        message = self.input_edit.text().strip()
        if not message:
            return
        
        if self.input_edit.hasFocus():
            modifiers = QApplication.keyboardModifiers()
            if modifiers == Qt.ControlModifier:
                cursor = self.input_edit.cursorPosition()
                text = self.input_edit.text()
                self.input_edit.setText(text[:cursor] + '\n' + text[cursor:])
                self.input_edit.setCursorPosition(cursor + 1)
                return
        
        timestamp = datetime.datetime.now().isoformat()
        
        if self.chat_mode == "private" and self.current_chat_partner:
            data = json.dumps({
                'type': 'private',
                'target': self.current_chat_partner,
                'content': message,
                'timestamp': timestamp
            })
            
            msg = {
                'sender': self.username,
                'message': message,
                'type': 'private',
                'timestamp': timestamp
            }
            
            if self.current_chat_partner not in self.messages["private"]:
                self.messages["private"][self.current_chat_partner] = []
            self.messages["private"][self.current_chat_partner].append(msg)
            
            self.display_message(msg)
        else:
            data = json.dumps({
                'type': 'message',
                'content': message,
                'timestamp': timestamp
            })
            
            msg = {
                'sender': self.username,
                'message': message,
                'type': 'broadcast',
                'timestamp': timestamp
            }
            
            self.messages["chat_room"].append(msg)
        
        try:
            self.socket.sendall(data.encode())
            self.input_edit.clear()
        except Exception as e:
            self.display_message({
                'sender': "系统",
                'message': f"发送失败: {e}",
                'type': 'system',
                'timestamp': datetime.datetime.now().isoformat()
            })
    
    def start_voice_call(self):
        """发起语音通话"""
        if not self.voice_client:
            QMessageBox.warning(self, "警告", "语音服务未连接")
            return
        
        if self.in_voice_call:
            QMessageBox.information(self, "提示", "您已经在通话中")
            return
        
        if self.is_calling:
            QMessageBox.information(self, "提示", "您正在呼叫其他用户")
            return
        
        # 选择通话对象
        users = []
        for i in range(self.user_list_widget.user_list.count()):
            item = self.user_list_widget.user_list.item(i)
            user = item.text()
            if user not in ["聊天室", "语音聊天室"] and user != f"{self.username} (我)":
                users.append(user)
        
        if not users:
            QMessageBox.information(self, "提示", "没有可通话的用户")
            return
        
        target, ok = QInputDialog.getItem(
            self, "选择通话对象", "请选择要通话的用户:", users, 0, False
        )
        
        if ok and target:
            self.start_voice_call_with(target)
    
    def start_voice_call_with(self, username):
        """与指定用户开始语音通话"""
        if not self.voice_client:
            QMessageBox.warning(self, "警告", "语音服务未连接")
            return
        
        if self.in_voice_call:
            QMessageBox.information(self, "提示", "您已经在通话中")
            return
        
        if self.is_calling:
            QMessageBox.information(self, "提示", "您正在呼叫其他用户")
            return
        
        # 设置呼叫状态
        self.is_calling = True
        print(f"[主程序] 开始呼叫 {username}")
        
        if self.voice_client.start_private_call(username):
            # 显示通话对话框
            print(f"[主程序] 创建通话对话框: 用户名={username}, 是来电=False")
            self.current_call_dialog = VoiceCallDialog(self, username, False)
            print(f"[主程序] 对话框创建成功: {self.current_call_dialog}")
            
            # 连接信号
            def on_dialog_ended():
                print("[主程序] 用户主动结束呼叫")
                self.end_current_call()
            
            self.current_call_dialog.ended.connect(on_dialog_ended)
            self.current_call_dialog.show()
            print(f"[主程序] 对话框已显示")
            
            # 发送语音状态通知
            try:
                voice_msg = json.dumps({
                    'type': 'voice_status',
                    'sender': self.username,
                    'target': username,
                    'status': '正在呼叫您',
                    'timestamp': datetime.datetime.now().isoformat()
                })
                self.socket.sendall(voice_msg.encode())
                print(f"[主程序] 已发送呼叫通知给 {username}")
            except Exception as e:
                print(f"[主程序] 发送呼叫通知失败: {e}")
        else:
            QMessageBox.warning(self, "错误", "发起通话失败")
            self.is_calling = False
    
    def join_voice_room(self):
        """加入语音房间"""
        if not self.voice_client:
            QMessageBox.warning(self, "警告", "语音服务未连接")
            return
        
        if self.in_voice_room:
            QMessageBox.information(self, "提示", "您已经在语音房间中")
            return
        
        if self.in_voice_call:
            QMessageBox.information(self, "提示", "您正在通话中")
            return
        
        room_id, ok = QInputDialog.getText(
            self, "加入语音房间", "请输入房间ID (默认: public):", QLineEdit.Normal, "public"
        )
        
        if ok:
            if not room_id.strip():
                room_id = "public"
            
            if self.voice_client.join_room(room_id):
                self.in_voice_room = True
                self.update_voice_status("在房间中", "#4CAF50")
                QMessageBox.information(self, "成功", f"已加入语音房间: {room_id}")
            else:
                QMessageBox.warning(self, "错误", "加入语音房间失败")
    
    def leave_voice_room(self):
        """离开语音房间"""
        if not self.in_voice_room:
            return
        
        if self.voice_client and self.voice_client.leave_room():
            self.in_voice_room = False
            self.update_voice_status("离线", "#666")
            QMessageBox.information(self, "提示", "已离开语音房间")
    
    def on_voice_action(self, action):
        """处理语音动作"""
        if action == "join_room":
            self.join_voice_room()
        elif action == "leave_room":
            self.leave_voice_room()
    
    def end_current_call(self):
        """结束当前通话"""
        print("[主程序] 结束当前通话")
        
        try:
            # 更新状态
            self.is_calling = False
            self.is_receiving_call = False
            
            # 结束通话
            if self.voice_client:
                self.voice_client.end_call()
                print("[主程序] 已发送结束通话命令")
            
            # 更新UI状态
            self.in_voice_call = False
            self.update_voice_status("离线", "#666")
            
            # 清理通话对话框
            if self.current_call_dialog:
                def cleanup_dialog():
                    try:
                        self.current_call_dialog.close()
                    except Exception as e:
                        print(f"[主程序] 关闭对话框失败: {e}")
                    finally:
                        self.current_call_dialog = None
                        print("[主程序] 通话对话框已清理")
                
                QTimer.singleShot(0, cleanup_dialog)
            
            print("[主程序] 通话结束完成")
            
        except Exception as e:
            print(f"[主程序] 结束通话失败: {e}")
            # 强制清理状态
            self.in_voice_call = False
            self.is_calling = False
            self.is_receiving_call = False
            self.current_call_dialog = None
            self.update_voice_status("离线", "#666")
    
    def test_microphone(self):
        """测试麦克风"""
        try:
            import pyaudio
            
            p = pyaudio.PyAudio()
            
            # 获取默认输入设备信息
            default_input = p.get_default_input_device_info()
            
            info_text = f"""
            麦克风测试:
            设备名称: {default_input['name']}
            采样率: {default_input['defaultSampleRate']} Hz
            最大输入通道数: {default_input['maxInputChannels']}
            
            正在测试...请对着麦克风说话。
            """
            
            # 测试录音
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=44100,
                input=True,
                frames_per_buffer=1024,
                input_device_index=default_input['index']
            )
            
            # 录制1秒的音频
            frames = []
            for i in range(0, int(44100 / 1024)):
                data = stream.read(1024)
                frames.append(data)
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            
            # 计算音量
            import struct
            import math
            
            audio_data = b''.join(frames)
            count = len(audio_data) / 2
            format = "%dh" % (count)
            shorts = struct.unpack(format, audio_data)
            
            sum_squares = 0.0
            for sample in shorts:
                n = sample * (1.0 / 32768)
                sum_squares += n * n
            
            rms = math.sqrt(sum_squares / count)
            volume = rms * 100
            
            info_text += f"\n测试完成！\n检测到的音量: {volume:.2f}%"
            
            if volume > 5:
                info_text += "\n✅ 麦克风工作正常！"
            else:
                info_text += "\n⚠️ 麦克风音量较低，请检查麦克风设置。"
            
            QMessageBox.information(self, "麦克风测试", info_text)
            
        except Exception as e:
            QMessageBox.critical(self, "测试失败", f"麦克风测试失败: {str(e)}")
    
    def test_audio_devices(self):
        """显示音频设备信息"""
        try:
            import pyaudio
            
            p = pyaudio.PyAudio()
            device_count = p.get_device_count()
            
            info_text = f"检测到 {device_count} 个音频设备:\n\n"
            
            # 获取默认设备信息
            try:
                default_input = p.get_default_input_device_info()
                info_text += f"默认输入设备: {default_input['name']} (索引: {default_input['index']})\n"
            except:
                info_text += "默认输入设备: 无\n"
                
            try:
                default_output = p.get_default_output_device_info()
                info_text += f"默认输出设备: {default_output['name']} (索引: {default_output['index']})\n"
            except:
                info_text += "默认输出设备: 无\n"
            
            info_text += "\n" + "="*40 + "\n"
            
            # 列出所有设备
            for i in range(device_count):
                device_info = p.get_device_info_by_index(i)
                device_name = device_info['name']
                
                # 设备类型
                device_type = ""
                if device_info['maxInputChannels'] > 0:
                    device_type += "输入"
                if device_info['maxOutputChannels'] > 0:
                    if device_type:
                        device_type += "/"
                    device_type += "输出"
                
                # 是否默认设备
                is_default = ""
                try:
                    if p.get_default_input_device_info()['index'] == i:
                        is_default += " (默认输入)"
                except:
                    pass
                try:
                    if p.get_default_output_device_info()['index'] == i:
                        is_default += " (默认输出)"
                except:
                    pass
                
                info_text += f"设备 {i}: {device_name}\n"
                info_text += f"  类型: {device_type}\n"
                info_text += f"  采样率: {device_info['defaultSampleRate']} Hz\n"
                info_text += f"  输入通道: {device_info['maxInputChannels']}\n"
                info_text += f"  输出通道: {device_info['maxOutputChannels']}\n"
                info_text += f"  默认设备: {is_default}\n\n"
            
            p.terminate()
            
            # 使用文本浏览器显示设备信息
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout
            
            dialog = QDialog(self)
            dialog.setWindowTitle("音频设备信息")
            dialog.resize(600, 500)
            
            layout = QVBoxLayout()
            
            text_browser = QTextBrowser()
            text_browser.setText(info_text)
            layout.addWidget(text_browser)
            
            # 关闭按钮
            button_layout = QHBoxLayout()
            button_layout.addStretch()
            close_button = QPushButton("关闭")
            close_button.clicked.connect(dialog.close)
            button_layout.addWidget(close_button)
            layout.addLayout(button_layout)
            
            dialog.setLayout(layout)
            dialog.exec_()
            
        except Exception as e:
            QMessageBox.critical(self, "获取设备信息失败", f"无法获取音频设备信息: {str(e)}")
    
    def configure_audio_devices(self):
        """配置音频设备"""
        try:
            import pyaudio
            
            p = pyaudio.PyAudio()
            device_count = p.get_device_count()
            
            if device_count == 0:
                QMessageBox.information(self, "无音频设备", "未检测到任何音频设备")
                p.terminate()
                return
            
            # 创建配置对话框
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFormLayout
            
            dialog = QDialog(self)
            dialog.setWindowTitle("配置音频设备")
            dialog.resize(400, 200)
            
            layout = QVBoxLayout()
            
            form_layout = QFormLayout()
            
            # 输入设备选择
            input_label = QLabel("麦克风设备:")
            self.input_device_combo = QComboBox()
            
            # 输出设备选择
            output_label = QLabel("扬声器设备:")
            self.output_device_combo = QComboBox()
            
            # 添加设备到下拉列表
            input_devices = []
            output_devices = []
            default_input_index = -1
            default_output_index = -1
            
            # 获取默认设备
            try:
                default_input = p.get_default_input_device_info()
                default_input_index = default_input['index']
            except:
                pass
            
            try:
                default_output = p.get_default_output_device_info()
                default_output_index = default_output['index']
            except:
                pass
            
            for i in range(device_count):
                device_info = p.get_device_info_by_index(i)
                device_name = device_info['name']
                
                if device_info['maxInputChannels'] > 0:
                    input_devices.append((i, device_name))
                    self.input_device_combo.addItem(f"{device_name} (索引: {i})")
                    if i == default_input_index:
                        self.input_device_combo.setCurrentIndex(len(input_devices) - 1)
                
                if device_info['maxOutputChannels'] > 0:
                    output_devices.append((i, device_name))
                    self.output_device_combo.addItem(f"{device_name} (索引: {i})")
                    if i == default_output_index:
                        self.output_device_combo.setCurrentIndex(len(output_devices) - 1)
            
            form_layout.addRow(input_label, self.input_device_combo)
            form_layout.addRow(output_label, self.output_device_combo)
            
            layout.addLayout(form_layout)
            
            # 按钮布局
            button_layout = QHBoxLayout()
            button_layout.addStretch()
            

            
            # 测试输出设备按钮
            test_output_button = QPushButton("测试扬声器")
            test_output_button.clicked.connect(self.test_selected_output_device)
            button_layout.addWidget(test_output_button)
            
            # 本地回环测试按钮
            loopback_button = QPushButton("本地回环测试")
            loopback_button.clicked.connect(self.test_audio_loopback)
            button_layout.addWidget(loopback_button)
            
            # 应用按钮
            apply_button = QPushButton("应用")
            apply_button.clicked.connect(dialog.accept)
            button_layout.addWidget(apply_button)
            
            # 取消按钮
            cancel_button = QPushButton("取消")
            cancel_button.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_button)
            
            layout.addLayout(button_layout)
            dialog.setLayout(layout)
            
            result = dialog.exec_()
            
            if result == QDialog.Accepted:
                # 保存用户选择的设备索引
                # 保存输入设备索引
                selected_input_text = self.input_device_combo.currentText()
                if "索引: " in selected_input_text:
                    index_part = selected_input_text.split("索引: ")[-1]
                    self.audio_input_device_index = int(''.join(filter(str.isdigit, index_part)))
                else:
                    self.audio_input_device_index = -1
                
                # 保存输出设备索引
                selected_output_text = self.output_device_combo.currentText()
                if "索引: " in selected_output_text:
                    index_part = selected_output_text.split("索引: ")[-1]
                    self.audio_output_device_index = int(''.join(filter(str.isdigit, index_part)))
                else:
                    self.audio_output_device_index = -1
                
                # 如果语音客户端已经存在，更新设备索引
                if self.voice_client:
                    self.voice_client.input_device_index = self.audio_input_device_index
                    self.voice_client.output_device_index = self.audio_output_device_index
                
                QMessageBox.information(self, "配置成功", "音频设备配置已应用")
            
            p.terminate()
            
        except Exception as e:
            QMessageBox.critical(self, "配置失败", f"无法配置音频设备: {str(e)}")
    
    def test_selected_input_device(self):
        """测试选择的输入设备"""
        try:
            import pyaudio
            
            p = pyaudio.PyAudio()
            
            # 获取选择的设备索引
            selected_text = self.input_device_combo.currentText()
            if "索引: " in selected_text:
                index = int(selected_text.split("索引: ")[-1])
            else:
                return
            
            # 获取设备信息
            device_info = p.get_device_info_by_index(index)
            
            info_text = f"\n正在测试设备: {device_info['name']}\n"
            info_text += f"采样率: {device_info['defaultSampleRate']} Hz\n"
            info_text += "请对着麦克风说话..."
            
            # 测试录音
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=44100,
                input=True,
                frames_per_buffer=1024,
                input_device_index=index
            )
            
            # 录制1秒的音频
            frames = []
            for i in range(0, int(44100 / 1024)):
                data = stream.read(1024)
                frames.append(data)
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            
            # 计算音量
            import struct
            import math
            
            audio_data = b''.join(frames)
            count = len(audio_data) / 2
            format = "%dh" % (count)
            shorts = struct.unpack(format, audio_data)
            
            sum_squares = 0.0
            for sample in shorts:
                n = sample * (1.0 / 32768)
                sum_squares += n * n
            
            rms = math.sqrt(sum_squares / count)
            volume = rms * 100
            
            info_text += f"\n测试完成！\n检测到的音量: {volume:.2f}%"
            
            if volume > 5:
                info_text += "\n✅ 麦克风工作正常！"
            else:
                info_text += "\n⚠️ 麦克风音量较低，请检查麦克风设置。"
            
            QMessageBox.information(self, "麦克风测试", info_text)
            
        except Exception as e:
            QMessageBox.critical(self, "测试失败", f"麦克风测试失败: {str(e)}")
    
    def test_selected_output_device(self):
        """测试选择的输出设备"""
        try:
            import pyaudio
            import numpy as np
            
            p = pyaudio.PyAudio()
            
            # 获取选择的设备索引
            selected_text = self.output_device_combo.currentText()
            if "索引: " in selected_text:
                # 提取索引部分并去掉括号
                index_part = selected_text.split("索引: ")[-1]
                # 只保留数字部分
                index_str = ''.join(filter(str.isdigit, index_part))
                if index_str:
                    index = int(index_str)
                else:
                    QMessageBox.warning(self, "警告", "无法解析设备索引")
                    return
            else:
                QMessageBox.warning(self, "警告", "未选择有效的输出设备")
                return
            
            # 获取设备信息
            device_info = p.get_device_info_by_index(index)
            
            info_text = f"正在测试设备: {device_info['name']}\n"
            
            # 生成测试音频 (440Hz正弦波，持续1秒)
            sample_rate = 44100
            duration = 1.0
            frequency = 440.0
            
            # 生成正弦波并转换为正确的格式
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
            sine_wave = 0.5 * np.sin(2 * np.pi * frequency * t)
            
            # 正确转换为16位PCM格式
            audio_data = (sine_wave * 32767).astype(np.int16)
            
            # 转换为字节
            audio_bytes = audio_data.tobytes()
            
            # 播放测试音频
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=sample_rate,
                output=True,
                frames_per_buffer=1024,
                output_device_index=index
            )
            
            stream.write(audio_bytes)
            
            # 确保音频完全播放
            import time
            time.sleep(duration)
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            
            info_text += "\n✅ 扬声器测试完成！您应该听到了一个440Hz的正弦波声音。"
            
            QMessageBox.information(self, "扬声器测试", info_text)
            
        except Exception as e:
            QMessageBox.critical(self, "测试失败", f"扬声器测试失败: {str(e)}")
            print(f"扬声器测试详细错误: {e}")
    
    def test_audio_loopback(self):
        """实现音频本地回环测试，将麦克风输入直接发送到扬声器输出"""
        try:
            import pyaudio
            import numpy as np
            import threading
            
            p = pyaudio.PyAudio()
            
            # 获取选择的输入和输出设备索引
            selected_input_text = self.input_device_combo.currentText()
            selected_output_text = self.output_device_combo.currentText()
            
            # 解析输入设备索引
            input_index = None
            if "索引: " in selected_input_text:
                index_part = selected_input_text.split("索引: ")[-1]
                index_str = ''.join(filter(str.isdigit, index_part))
                if index_str:
                    try:
                        input_index = int(index_str)
                    except ValueError:
                        input_index = None
            elif selected_input_text != "默认设备":
                # 如果不是默认设备但没有索引信息，尝试直接解析
                try:
                    index_str = ''.join(filter(str.isdigit, selected_input_text))
                    if index_str:
                        input_index = int(index_str)
                except ValueError:
                    input_index = None
            
            # 解析输出设备索引
            output_index = None
            if "索引: " in selected_output_text:
                index_part = selected_output_text.split("索引: ")[-1]
                index_str = ''.join(filter(str.isdigit, index_part))
                if index_str:
                    try:
                        output_index = int(index_str)
                    except ValueError:
                        output_index = None
            elif selected_output_text != "默认设备":
                # 如果不是默认设备但没有索引信息，尝试直接解析
                try:
                    index_str = ''.join(filter(str.isdigit, selected_output_text))
                    if index_str:
                        output_index = int(index_str)
                except ValueError:
                    output_index = None
            
            # 验证设备索引
            device_count = p.get_device_count()
            valid_input_index = -1  # -1表示使用默认设备
            valid_output_index = -1  # -1表示使用默认设备
            
            if input_index is not None:
                if 0 <= input_index < device_count:
                    valid_input_index = input_index
                    print(f"[回环测试] 使用输入设备索引: {valid_input_index}")
                else:
                    QMessageBox.warning(self, "警告", f"输入设备索引 {input_index} 无效，将使用默认设备")
                    valid_input_index = -1
            else:
                QMessageBox.warning(self, "警告", "无法解析输入设备索引，将使用默认设备")
                valid_input_index = -1
            
            if output_index is not None:
                if 0 <= output_index < device_count:
                    valid_output_index = output_index
                    print(f"[回环测试] 使用输出设备索引: {valid_output_index}")
                else:
                    QMessageBox.warning(self, "警告", f"输出设备索引 {output_index} 无效，将使用默认设备")
                    valid_output_index = -1
            else:
                QMessageBox.warning(self, "警告", "无法解析输出设备索引，将使用默认设备")
                valid_output_index = -1
            
            # 创建回环对话框
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
            
            loopback_dialog = QDialog(self)
            loopback_dialog.setWindowTitle("音频本地回环测试")
            loopback_dialog.resize(400, 150)
            
            layout = QVBoxLayout()
            
            status_label = QLabel("回环状态: 未启动")
            status_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(status_label)
            
            button_layout = QHBoxLayout()
            
            # 回环运行标志
            is_looping = False
            stop_event = threading.Event()
            
            def loopback_thread_func():
                try:
                    # 配置音频流参数
                    format = pyaudio.paInt16
                    channels = 1
                    rate = 44100
                    chunk = 1024
                    
                    # 打开输入流
                    input_stream = p.open(
                        format=format,
                        channels=channels,
                        rate=rate,
                        input=True,
                        frames_per_buffer=chunk,
                        input_device_index=valid_input_index if valid_input_index != -1 else None
                    )
                    # 打开输出流
                    output_stream = p.open(
                        format=format,
                        channels=channels,
                        rate=rate,
                        output=True,
                        frames_per_buffer=chunk,
                        output_device_index=valid_output_index if valid_output_index != -1 else None
                    )
                    
                    # 更新状态（在GUI线程中）
                    from PyQt5.QtCore import QTimer
                    QTimer.singleShot(0, lambda: status_label.setText("回环状态: 正在运行 - 请说话测试"))
                    
                    # 实时回环处理
                    while not stop_event.is_set():
                        try:
                            # 检查是否需要停止（在每次循环开始时）
                            if stop_event.is_set():
                                break
                                
                            # 读取麦克风输入（设置超时，避免阻塞）
                            if not input_stream.is_stopped():
                                try:
                                    data = input_stream.read(chunk, exception_on_overflow=False)
                                    if data and not output_stream.is_stopped():
                                        # 直接写入扬声器输出
                                        output_stream.write(data)
                                except IOError as e:
                                    # 忽略输入溢出错误
                                    if e.errno != -9981:  # input overflowed
                                        print(f"[回环测试] 音频读取错误: {e}")
                                        break
                        except Exception as e:
                            print(f"[回环测试] 音频处理错误: {e}")
                            break
                    
                    # 确保停止并关闭音频流
                    try:
                        if not input_stream.is_stopped():
                            input_stream.stop_stream()
                        input_stream.close()
                    except:
                        pass
                        
                    try:
                        if not output_stream.is_stopped():
                            output_stream.stop_stream()
                        output_stream.close()
                    except:
                        pass
                    
                    # 更新状态（在GUI线程中）
                    QTimer.singleShot(0, lambda: status_label.setText("回环状态: 已停止"))
                    QTimer.singleShot(0, lambda: start_button.setEnabled(True))
                    QTimer.singleShot(0, lambda: stop_button.setEnabled(False))
                    
                except Exception as e:
                    # 在GUI线程中显示错误
                    from PyQt5.QtCore import QTimer
                    QTimer.singleShot(0, lambda: QMessageBox.critical(loopback_dialog, "回环失败", f"回环测试失败: {str(e)}"))
                    QTimer.singleShot(0, lambda: status_label.setText("回环状态: 错误"))
                    QTimer.singleShot(0, lambda: start_button.setEnabled(True))
                    QTimer.singleShot(0, lambda: stop_button.setEnabled(False))
                    print(f"回环测试错误: {e}")
            
            def start_loopback():
                nonlocal is_looping
                is_looping = True
                stop_event.clear()
                
                status_label.setText("回环状态: 正在运行")
                start_button.setEnabled(False)
                stop_button.setEnabled(True)
                
                # 启动回环线程
                loopback_thread = threading.Thread(target=loopback_thread_func)
                loopback_thread.daemon = True
                loopback_thread.start()
            
            def stop_loopback():
                stop_event.set()
            
            # 启动按钮
            start_button = QPushButton("启动回环")
            start_button.clicked.connect(lambda: threading.Thread(target=start_loopback, daemon=True).start())
            button_layout.addWidget(start_button)
            
            # 停止按钮
            stop_button = QPushButton("停止回环")
            stop_button.setEnabled(False)
            stop_button.clicked.connect(stop_loopback)
            button_layout.addWidget(stop_button)
            
            # 关闭按钮
            close_button = QPushButton("关闭")
            close_button.clicked.connect(loopback_dialog.close)
            button_layout.addWidget(close_button)
            
            layout.addLayout(button_layout)
            loopback_dialog.setLayout(layout)
            
            # 对话框关闭时确保停止回环
            def on_dialog_close():
                stop_event.set()
                p.terminate()
            
            loopback_dialog.finished.connect(on_dialog_close)
            
            loopback_dialog.exec_()
            
        except Exception as e:
            QMessageBox.critical(self, "回环测试失败", f"无法启动音频回环测试: {str(e)}")
            print(f"回环测试初始化错误: {e}")
    
    def show_user_context_menu(self, position):
        """显示用户列表的右键菜单"""
        item = self.user_list_widget.user_list.itemAt(position)
        if not item:
            return
        
        username = item.text()
        if username in ["聊天室", "语音聊天室", f"{self.username} (我)"]:
            return
        
        menu = QMenu()
        
        # 私聊动作
        private_action = QAction("发送私聊消息", self)
        private_action.triggered.connect(lambda: self.start_private_chat_with(username))
        menu.addAction(private_action)
        
        # 语音通话动作
        voice_action = QAction("发起语音通话", self)
        voice_action.triggered.connect(lambda: self.start_voice_call_with(username))
        menu.addAction(voice_action)
        
        menu.exec_(self.user_list_widget.user_list.viewport().mapToGlobal(position))
    
    def start_private_chat_with(self, username):
        """与指定用户开始私聊"""
        self.chat_mode = "private"
        self.current_chat_partner = username
        self.title_label.setText(f"私聊 - {username}")
        
        self.message_area.clear()
        self.message_count = 0
        self.message_counter.setText("消息: 0")
        
        if username in self.messages["private"]:
            for msg in self.messages["private"][username]:
                self.display_message(msg)
        
        self.display_message({
            'sender': "系统",
            'message': f"已进入与 {username} 的私聊界面",
            'type': 'system',
            'timestamp': datetime.datetime.now().isoformat()
        })
    
    def show_online_users(self):
        """显示在线用户"""
        if not self.socket or not self.connection_status:
            return
            
        data = json.dumps({'type': 'command', 'command': 'users'})
        try:
            self.socket.sendall(data.encode())
        except Exception as e:
            self.display_message({
                'sender': "系统",
                'message': f"请求用户列表失败: {e}",
                'type': 'system',
                'timestamp': datetime.datetime.now().isoformat()
            })
    
    def start_private_chat(self):
        """开始私聊"""
        target, ok = QInputDialog.getText(
            self, "私聊", "请输入要私聊的用户名:", QLineEdit.Normal, ""
        )
        if ok and target:
            message, ok = QInputDialog.getText(
                self, "私聊消息", f"给 {target} 的消息:", QLineEdit.Normal, ""
            )
            if ok and message:
                data = json.dumps({
                    'type': 'private',
                    'target': target,
                    'content': message,
                    'timestamp': datetime.datetime.now().isoformat()
                })
                try:
                    self.socket.sendall(data.encode())
                except Exception as e:
                    self.display_message({
                        'sender': "系统",
                        'message': f"私聊发送失败: {e}",
                        'type': 'system',
                        'timestamp': datetime.datetime.now().isoformat()
                    })
    
    def clear_chat(self):
        """清空聊天记录"""
        reply = QMessageBox.question(self, '确认', '确定要清空聊天记录吗？',
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.message_area.clear()
            self.message_count = 0
            self.message_counter.setText("消息: 0")
    
    def show_emoji_picker(self):
        """显示表情选择器"""
        emojis = ["😊", "😂", "😍", "🥰", "😎", "🤔", "😴", "🤗", 
                 "👍", "👎", "🎉", "💕", "🔥", "⭐", "✨", "💯"]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("选择表情")
        dialog.setFixedSize(350, 250)
        
        layout = QVBoxLayout(dialog)
        
        emoji_grid = QWidget()
        grid_layout = QGridLayout(emoji_grid)
        grid_layout.setSpacing(15)
        grid_layout.setContentsMargins(25, 25, 25, 25)
        
        for i, emoji in enumerate(emojis):
            row = i // 4
            col = i % 4
            btn = QPushButton(emoji)
            btn.setFixedSize(50, 50)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 24px;
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    background-color: white;
                }
                QPushButton:hover {
                    background-color: #f0f0f0;
                }
            """)
            btn.clicked.connect(lambda checked, e=emoji: self.insert_emoji(e, dialog))
            grid_layout.addWidget(btn, row, col)
        
        layout.addWidget(emoji_grid)
        dialog.exec_()
    
    def insert_emoji(self, emoji, dialog):
        """插入表情到输入框"""
        self.input_edit.setText(self.input_edit.text() + emoji)
        dialog.close()
    
    def format_file_size(self, size):
        """格式化文件大小"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.2f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"
    
    def upload_file(self):
        """上传文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择文件", "", "All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            encoded_data = base64.b64encode(file_data).decode('utf-8')
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            # 发送文件
            if self.chat_mode == "private" and self.current_chat_partner:
                msg_type = 'private_file'
                target = self.current_chat_partner
            else:
                msg_type = 'file'
                target = None
            
            file_msg = {
                'type': msg_type,
                'file_name': file_name,
                'file_size': file_size,
                'file_content': encoded_data
            }
            
            if target:
                file_msg['target'] = target
            
            self.socket.sendall(json.dumps(file_msg).encode())
            
            # 显示发送的消息，保存文件到received_files以便自己也能下载
            import uuid
            file_id = str(uuid.uuid4())
            
            # 保存文件到内存字典
            self.received_files[file_id] = {
                'file_name': file_name,
                'file_size': file_size,
                'file_content': encoded_data,
                'sender': '我',
                'timestamp': datetime.datetime.now().isoformat()
            }
            
            display_msg = {
                'sender': '我',
                'type': 'file_receive',
                'message': f"发送文件: {file_name} ({self.format_file_size(file_size)})",
                'file_name': file_name,
                'file_size': file_size,
                'file_content': encoded_data,
                'file_id': file_id,
                'timestamp': datetime.datetime.now().isoformat()
            }
            
            # 保存到消息历史
            if self.chat_mode == "private" and self.current_chat_partner:
                if self.current_chat_partner not in self.messages["private"]:
                    self.messages["private"][self.current_chat_partner] = []
                self.messages["private"][self.current_chat_partner].append(display_msg)
            else:
                self.messages["chat_room"].append(display_msg)
            
            self.display_message(display_msg)
            
        except Exception as e:
            QMessageBox.warning(self, "上传失败", f"文件上传失败: {str(e)}")
    
    def handle_anchor_click(self, url):
        """处理链接点击事件"""
        url_str = url.toString()
        if url_str.startswith('download://'):
            file_id = url_str.replace('download://', '')
            self.download_file(file_id)
    
    def download_file(self, file_id):
        """下载文件"""
        if file_id not in self.received_files:
            QMessageBox.warning(self, "下载失败", "文件不存在")
            return
        
        try:
            file_data = self.received_files[file_id]
            file_name = file_data.get('file_name', 'unknown_file')
            file_content = file_data.get('file_content')
            
            save_path, _ = QFileDialog.getSaveFileName(
                self, "保存文件", file_name, "All Files (*)"
            )
            
            if not save_path:
                return
            
            with open(save_path, 'wb') as f:
                f.write(base64.b64decode(file_content))
            
            QMessageBox.information(self, "下载成功", f"文件已保存到: {save_path}")
            
        except Exception as e:
            QMessageBox.warning(self, "下载失败", f"文件下载失败: {str(e)}")
    
    def upload_image(self):
        """上传图片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "", "Image Files (*.png *.jpg *.jpeg *.gif *.bmp)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            encoded_data = base64.b64encode(file_data).decode('utf-8')
            file_name = os.path.basename(file_path)
            
            # 发送图片
            if self.chat_mode == "private" and self.current_chat_partner:
                msg_type = 'private_image'
                target = self.current_chat_partner
            else:
                msg_type = 'image'
                target = None
            
            image_msg = {
                'type': msg_type,
                'image_name': file_name,
                'image_content': encoded_data
            }
            
            if target:
                image_msg['target'] = target
            
            self.socket.sendall(json.dumps(image_msg).encode())
            
            # 保存图片到本地以便显示
            save_dir = os.path.join(os.getcwd(), 'sent_images')
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
            
            # 保存图片
            image_path = os.path.join(save_dir, file_name)
            with open(image_path, 'wb') as f:
                f.write(file_data)
            
            # 显示发送的消息
            display_msg = {
                'sender': '我',
                'type': 'image_receive',
                'message': f"发送图片: {file_name}",
                'image_path': image_path,
                'image_name': file_name,
                'timestamp': datetime.datetime.now().isoformat()
            }
            
            # 保存到消息历史
            if self.chat_mode == "private" and self.current_chat_partner:
                if self.current_chat_partner not in self.messages["private"]:
                    self.messages["private"][self.current_chat_partner] = []
                self.messages["private"][self.current_chat_partner].append(display_msg)
            else:
                self.messages["chat_room"].append(display_msg)
            
            self.display_message(display_msg)
            
        except Exception as e:
            QMessageBox.warning(self, "上传失败", f"图片上传失败: {str(e)}")
    
    def toggle_theme(self):
        """切换主题"""
        self.is_dark_theme = not self.is_dark_theme
        
        if self.is_dark_theme:
            self.setStyleSheet("""
                QMainWindow {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                              stop:0 #3d2e22,
                                              stop:0.25 #4a3520,
                                              stop:0.5 #3d2e22,
                                              stop:0.75 #4a3520,
                                              stop:1 #3d2e22);
                    background-repeat: repeat;
                }
                
                QWidget#centralWidget {
                    background-color: rgba(50, 40, 30, 0.95);
                    color: white;
                    border: 2px solid #8b4513;
                }
                
                QTextEdit {
                    background-color: #2b2b2b !important;
                    color: white !important;
                    border: 1px solid #555;
                }
                
                QLineEdit {
                    background-color: #2b2b2b !important;
                    color: white !important;
                    border: 2px solid #555;
                }
                
                QLineEdit:focus {
                    border-color: #4CAF50;
                }
                
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                              stop:0 #6d4c41, stop:1 #4e342e);
                    color: white;
                    border: 2px solid #8d6e63;
                    border-radius: 8px;
                }
                
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                              stop:0 #7d5c51, stop:1 #5e443e);
                    border-color: #a1887f;
                }
                
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                              stop:0 #4e342e, stop:1 #3e241e);
                }
                
                QComboBox {
                    background-color: #3c3c3c;
                    color: white;
                    border: 1px solid #555;
                }
                
                QComboBox QListView {
                    background-color: #3c3c3c;
                    color: white;
                    border: 1px solid #555;
                }
                
                QComboBox QListView::item:hover {
                    background-color: #444;
                }
                
                QListWidget {
                    background-color: #3c3c3c;
                    color: white;
                    border: none;
                }
                
                QListWidget::item:hover {
                    background-color: #444;
                }
                
                QListWidget::item:selected {
                    background-color: #007bff;
                    color: white;
                }
                
                QLabel {
                    color: white;
                }
                
                QGroupBox {
                    color: white;
                    border: 2px solid #555;
                    background-color: rgba(50, 40, 30, 0.85);
                }
                
                QGroupBox::title {
                    color: #ffd700;
                    background-color: #5d4037;
                    padding: 0 10px;
                    border-radius: 5px;
                }
                
                QMenuBar {
                    background-color: #3c3c3c;
                    color: white;
                }
                
                QMenu {
                    background-color: #3c3c3c;
                    color: white;
                }
                
                QMenu::item:selected {
                    background-color: #444;
                }
            """)
            self.message_area.setStyleSheet("""
                QTextEdit {
                    background-color: #2b2b2b !important;
                    color: white !important;
                    border: 1px solid #555;
                    border-radius: 8px;
                    padding: 10px;
                }
            """)
            self.input_edit.setStyleSheet("""
                QLineEdit {
                    background-color: #2b2b2b !important;
                    color: white !important;
                    border: 2px solid #555;
                    border-radius: 8px;
                    padding: 12px;
                }
                QLineEdit:focus {
                    border-color: #4CAF50;
                }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                              stop:0 #f4e3c9,
                                              stop:0.25 #e6c89e,
                                              stop:0.5 #f4e3c9,
                                              stop:0.75 #e6c89e,
                                              stop:1 #f4e3c9);
                    background-repeat: repeat;
                }
                QWidget#centralWidget {
                    background-color: rgba(250, 245, 230, 0.95);
                    border-radius: 15px;
                    margin: 10px;
                    border: 2px solid #8b4513;
                }
            """)
            self.reset_light_theme_styles()
    
    def reset_light_theme_styles(self):
        """重置浅色主题样式"""
        self.message_area.setStyleSheet("""
            QTextEdit {
                background-color: #fafafa;
                border: 1px solid #d4b88c;
                border-radius: 8px;
                font-size: 14px;
                padding: 10px;
                selection-background-color: #4CAF50;
            }
        """)
        
        self.input_edit.setStyleSheet("""
            QLineEdit {
                background-color: white;
                border: 2px solid #d4b88c;
                border-radius: 8px;
                font-size: 14px;
                padding: 12px;
                selection-background-color: #4CAF50;
            }
            QLineEdit:focus {
                border-color: #8b4513;
            }
        """)
        
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #8d6e63,
                                          stop:1 #5d4037);
                color: white;
                border: 2px solid #a1887f;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #a1887f,
                                          stop:1 #6d4c41);
                border-color: #bcaaa4;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #5d4037,
                                          stop:1 #3e2723);
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        
        button_style = """
            QToolButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #f5deb3,
                                          stop:1 #deb887);
                border: 2px solid #d4b88c;
                border-radius: 6px;
                padding: 8px;
                margin: 2px;
                color: #5d4037;
            }
            QToolButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #deb887,
                                          stop:1 #cd853f);
                border-color: #cd853f;
            }
            QToolButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #deb887,
                                          stop:1 #8b4513);
            }
        """
        
        self.users_btn.setStyleSheet(button_style)
        self.private_btn.setStyleSheet(button_style)
        self.clear_btn.setStyleSheet(button_style)
        self.emoji_btn.setStyleSheet(button_style)
        
        self.user_list_widget.user_list.setStyleSheet("""
            QListWidget {
                background-color: #fafafa;
                border: 1px solid #d4b88c;
                border-radius: 8px;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-bottom: 1px solid #f5deb3;
                color: #5d4037;
            }
            QListWidget::item:hover {
                background-color: #f5deb3;
            }
            QListWidget::item:selected {
                background-color: #d4b88c;
                color: #5d4037;
            }
        """)
        
        self.user_list_widget.title_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 14px;
                color: #5d4037;
                padding: 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                          stop:0 #f5deb3,
                                          stop:1 #deb887);
                border-bottom: 2px solid #d4b88c;
                border-radius: 8px 8px 0 0;
            }
        """)
        
        group_style = """
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #555;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
            }
        """
        
        for widget in self.centralWidget().findChildren(QGroupBox):
            widget.setStyleSheet(group_style)
    
    def change_font(self):
        """更改字体"""
        font, ok = QFontDialog.getFont()
        if ok:
            self.message_area.setFont(font)
            self.input_edit.setFont(font)
    
    def show_about(self):
        """显示关于对话框"""
        about_text = """
        <h2>精美网络聊天室 - 语音版</h2>
        <p>版本: 2.0.0</p>
        <p>作者: HNUER</p>
        <p>描述: 基于PyQt5和Socket的跨平台网络聊天室</p>
        <p>新增功能特性:</p>
        <ul>
            <li>多人语音聊天室</li>
            <li>私人语音通话</li>
            <li>实时音频传输</li>
            <li>麦克风测试功能</li>
            <li>实时语音状态显示</li>
        </ul>
        """
        QMessageBox.about(self, "关于", about_text)
    
    def reconnect(self):
        """重新连接服务器"""
        if self.connection_status:
            QMessageBox.information(self, "提示", "已经连接到服务器")
        else:
            self.connect_to_server()
    
    def disconnect(self):
        """断开连接"""
        try:
            # 断开语音连接
            if self.voice_client:
                self.voice_client.disconnect()
                self.voice_client = None
            
            # 断开主连接
            if self.connection_status and self.socket:
                try:
                    data = json.dumps({'type': 'disconnect'})
                    self.socket.sendall(data.encode())
                except:
                    pass
                finally:
                    self.update_connection_status(False)
                    if self.receive_thread:
                        self.receive_thread.stop()
                    if self.socket:
                        self.socket.close()
                    
                    self.display_message({
                        'sender': "系统",
                        'message': "已断开与服务器的连接",
                        'type': 'system',
                        'timestamp': datetime.datetime.now().isoformat()
                    })
                    
        except Exception as e:
            print(f"[主程序] 断开连接失败: {e}")
    
    def on_connection_closed(self):
        """连接关闭处理"""
        self.update_connection_status(False)
        
        if self.receive_thread:
            self.receive_thread.stop()
            self.receive_thread = None
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        # 断开语音连接
        if self.voice_client:
            self.voice_client.disconnect()
            self.voice_client = None
        
        self.display_message({
            'sender': "系统",
            'message': "服务器连接已断开",
            'type': 'system',
            'timestamp': datetime.datetime.now().isoformat()
        })
    
    def handle_error(self, error_message):
        """处理错误"""
        QMessageBox.critical(self, "连接错误", f"网络错误: {error_message}")
        self.update_connection_status(False)
    
    def on_user_clicked(self, username):
        """处理用户点击事件"""
        if username == self.username:
            return
        elif username == "聊天室":
            self.chat_mode = "chat_room"
            self.current_chat_partner = None
            self.title_label.setText("网络聊天室")
            self.message_area.clear()
            self.message_count = 0
            self.message_counter.setText("消息: 0")
            for msg in self.messages["chat_room"]:
                self.display_message(msg)
            self.display_message({
                'sender': "系统",
                'message': "已切换到聊天室",
                'type': 'system',
                'timestamp': datetime.datetime.now().isoformat()
            })
        elif username == "语音聊天室":
            self.join_voice_room()
        else:
            self.chat_mode = "private"
            self.current_chat_partner = username
            self.title_label.setText(f"私聊 - {username}")
            self.message_area.clear()
            self.message_count = 0
            self.message_counter.setText("消息: 0")
            if username in self.messages["private"]:
                for msg in self.messages["private"][username]:
                    self.display_message(msg)
            self.display_message({
                'sender': "系统",
                'message': f"已进入与 {username} 的私聊界面",
                'type': 'system',
                'timestamp': datetime.datetime.now().isoformat()
            })
    
    def createSystemTray(self):
        """创建系统托盘图标"""
        try:
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
            
            tray_menu = QMenu()
            
            show_action = QAction("显示窗口", self)
            show_action.triggered.connect(self.show)
            tray_menu.addAction(show_action)
            
            tray_menu.addSeparator()
            
            exit_action = QAction("退出", self)
            exit_action.triggered.connect(self.close)
            tray_menu.addAction(exit_action)
            
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.show()
        except:
            pass
    
    def closeEvent(self, event):
        """关闭窗口时清理资源"""
        print("[主程序] 关闭窗口")
        
        # 结束所有通话
        if self.in_voice_call or self.is_calling:
            self.end_current_call()
        
        # 断开连接
        self.disconnect()
        
        # 清理系统托盘
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.hide()
        
        # 停止定时器
        if hasattr(self, 'timer') and self.timer:
            self.timer.stop()
        
        event.accept()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='网络聊天室客户端')
    parser.add_argument('--title', type=str, help='客户端窗口标题')
    args = parser.parse_args()
    
    # 服务器配置
    SERVER_IP = "120.46.42.133"
    SERVER_PORT = 8888
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    client = ChatClient(SERVER_IP, SERVER_PORT)
    
    if args.title:
        client.setWindowTitle(args.title)
    
    client.show()
    sys.exit(app.exec_())