# server_tcp.py
# -*- coding: utf-8 -*-
import socket
import threading
import json
import sys
import base64
import os
import time
import struct
import pickle

class VoiceServer:
    """语音服务器类，处理语音通话"""
    def __init__(self, host='0.0.0.0', voice_port=8889):
        self.host = host
        self.voice_port = voice_port
        self.voice_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.voice_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # 存储语音客户端
        self.voice_clients = {}  # username -> voice_socket
        self.voice_rooms = {}    # room_id -> {usernames}
        self.private_calls = {}  # caller -> callee
        
        # 音频参数
        self.CHUNK = 1024
        self.FORMAT = 'int16'
        self.CHANNELS = 1
        self.RATE = 44100
        
        self.lock = threading.Lock()
    
    def send_with_length_prefix(self, sock, data):
        """发送带有长度前缀的数据"""
        # 1. 序列化数据
        serialized_data = pickle.dumps(data)
        
        # 2. 计算数据长度并转换为4字节的大端序
        import struct
        length_prefix = struct.pack('>I', len(serialized_data))
        
        # 3. 发送长度前缀 + 数据
        try:
            sock.sendall(length_prefix + serialized_data)
            return True
        except Exception as e:
            print(f"[错误] 发送数据失败: {e}")
            return False
    
    def start(self):
        """启动语音服务器"""
        self.voice_server.bind((self.host, self.voice_port))
        self.voice_server.listen(5)
        print(f"语音服务器启动在 {self.host}:{self.voice_port}")
        
        while True:
            voice_socket, addr = self.voice_server.accept()
            print(f"新语音连接: {addr}")
            
            # 为新语音客户端创建线程
            thread = threading.Thread(
                target=self.handle_voice_client,
                args=(voice_socket,)
            )
            thread.daemon = True
            thread.start()
    
    def handle_voice_client(self, voice_socket):
        """处理语音客户端连接"""
        try:
            # 接收用户名（使用长度前缀）
            # 1. 接收4字节的长度前缀
            length_prefix = voice_socket.recv(4)
            if not length_prefix:
                return
            
            # 2. 解析长度
            import struct
            data_length = struct.unpack('>I', length_prefix)[0]
            
            # 3. 接收完整的用户名数据
            username_data = b''
            while len(username_data) < data_length:
                remaining = data_length - len(username_data)
                chunk = voice_socket.recv(min(4096, remaining))
                if not chunk:
                    break
                username_data += chunk
            
            if len(username_data) != data_length:
                print(f"[错误] 用户名数据接收不完整")
                return
            
            username = username_data.decode().strip()
            
            with self.lock:
                self.voice_clients[username] = voice_socket
            
            print(f"{username} 加入语音系统")
            
            # 持续处理语音命令
            while True:
                try:
                    # 1. 接收4字节的长度前缀
                    length_prefix = voice_socket.recv(4)
                    if not length_prefix:
                        break
                    
                    # 2. 解析长度
                    data_length = struct.unpack('>I', length_prefix)[0]
                    
                    # 3. 接收完整的数据
                    cmd_data = b''
                    while len(cmd_data) < data_length:
                        remaining = data_length - len(cmd_data)
                        chunk = voice_socket.recv(min(4096, remaining))
                        if not chunk:
                            break
                        cmd_data += chunk
                    
                    if len(cmd_data) != data_length:
                        print(f"[错误] 数据接收不完整: 预期 {data_length} 字节，实际收到 {len(cmd_data)} 字节")
                        continue
                    
                    command = pickle.loads(cmd_data)
                    cmd_type = command.get('type')
                    
                    if cmd_type == 'join_room':
                        # 加入语音聊天室
                        room_id = command.get('room_id', 'public')
                        with self.lock:
                            if room_id not in self.voice_rooms:
                                self.voice_rooms[room_id] = set()
                            self.voice_rooms[room_id].add(username)
                        
                        print(f"{username} 加入语音房间 {room_id}")
                        
                    elif cmd_type == 'leave_room':
                        # 离开语音聊天室
                        room_id = command.get('room_id', 'public')
                        with self.lock:
                            if room_id in self.voice_rooms and username in self.voice_rooms[room_id]:
                                self.voice_rooms[room_id].remove(username)
                                if not self.voice_rooms[room_id]:
                                    del self.voice_rooms[room_id]
                        
                        print(f"{username} 离开语音房间 {room_id}")
                        
                    elif cmd_type == 'start_private_call':
                        # 发起私人通话
                        callee = command.get('callee')
                        with self.lock:
                            if callee in self.voice_clients:
                                self.private_calls[username] = callee
                                # 通知对方
                                notify_cmd = {
                                    'type': 'incoming_call',
                                    'caller': username
                                }
                                self.send_with_length_prefix(self.voice_clients[callee], notify_cmd)
                                print(f"{username} 呼叫 {callee}")
                        
                    elif cmd_type == 'accept_call':
                        # 接受通话
                        caller = command.get('caller')
                        with self.lock:
                            if caller in self.private_calls and self.private_calls[caller] == username:
                                # 创建双向通话关系
                                self.private_calls[username] = caller
                                # 通知对方已接受
                                accept_cmd = {
                                    'type': 'call_accepted',
                                    'callee': username
                                }
                                if caller in self.voice_clients:
                                    try:
                                        if self.send_with_length_prefix(self.voice_clients[caller], accept_cmd):
                                            print(f"[语音] 已通知 {caller} 通话被接受")
                                        else:
                                            print(f"[语音] 通知 {caller} 通话被接受失败")
                                    except Exception as e:
                                        print(f"[错误] 发送通话接受通知失败: {e}")
                                print(f"{username} 接受了 {caller} 的通话")
                        
                    elif cmd_type == 'reject_call':
                        # 拒绝通话
                        caller = command.get('caller')
                        with self.lock:
                            if caller in self.private_calls and self.private_calls[caller] == username:
                                del self.private_calls[caller]
                                # 通知对方已拒绝
                                reject_cmd = {
                                    'type': 'call_rejected',
                                    'callee': username
                                }
                                self.send_with_length_prefix(self.voice_clients[caller], reject_cmd)
                                print(f"{username} 拒绝了 {caller} 的通话")
                        
                    elif cmd_type == 'end_call':
                        # 结束通话
                        with self.lock:
                            if username in self.private_calls:
                                other = self.private_calls[username]
                                # 清理双向通话关系
                                if other in self.private_calls:
                                    del self.private_calls[other]
                                del self.private_calls[username]
                                # 通知双方通话结束
                                end_cmd = {
                                    'type': 'call_ended',
                                    'user': username
                                }
                                # 通知对方
                                if other in self.voice_clients:
                                    try:
                                        self.send_with_length_prefix(self.voice_clients[other], end_cmd)
                                    except Exception as e:
                                        print(f"[错误] 发送结束通话通知给 {other} 失败: {e}")
                                # 通知发起结束的一方
                                try:
                                    self.send_with_length_prefix(self.voice_clients[username], end_cmd)
                                except Exception as e:
                                    print(f"[错误] 发送结束通话通知给 {username} 失败: {e}")
                                print(f"{username} 结束通话")
                        
                    elif cmd_type == 'audio_data':
                        # 转发音频数据
                        room_id = command.get('room_id')
                        audio_data = command.get('audio_data')
                        
                        print(f"[语音] 收到音频数据 from {username}, 大小: {len(audio_data)} bytes")
                        if room_id:
                            print(f"[语音] 来自房间: {room_id}")
                        else:
                            print(f"[语音] 私人通话数据")
                        
                        # 确定转发目标
                        targets = []
                        with self.lock:
                            if room_id:  # 房间语音
                                if room_id in self.voice_rooms:
                                    targets = list(self.voice_rooms[room_id])
                                    print(f"[语音] 房间 {room_id} 中的用户: {targets}")
                            elif username in self.private_calls:  # 私人通话
                                other = self.private_calls[username]
                                targets = [other]
                                print(f"[语音] 私人通话目标: {other}")
                        
                        # 转发给所有目标（除了发送者自己）
                        for target in targets:
                            if target != username and target in self.voice_clients:
                                try:
                                    forward_cmd = {
                                    'type': 'audio_data',
                                    'sender': username,
                                    'audio_data': audio_data,
                                    'room_id': room_id
                                }
                                    print(f"[语音] 转发音频数据 to {target}, 大小: {len(audio_data)} bytes")
                                    if self.send_with_length_prefix(self.voice_clients[target], forward_cmd):
                                        print(f"[语音] 转发成功 to {target}")
                                    else:
                                        print(f"[语音] 转发失败 to {target}")
                                except Exception as e:
                                    print(f"[语音] 转发到 {target} 时出错: {e}")
                        
                except (EOFError, ConnectionError):
                    break
                    
        except Exception as e:
            print(f"语音客户端处理错误: {e}")
        finally:
            # 清理
            with self.lock:
                if username in self.voice_clients:
                    del self.voice_clients[username]
                # 从所有房间移除
                for room_id in list(self.voice_rooms.keys()):
                    if username in self.voice_rooms[room_id]:
                        self.voice_rooms[room_id].remove(username)
                        if not self.voice_rooms[room_id]:
                            del self.voice_rooms[room_id]
                # 结束私人通话
                if username in self.private_calls:
                    other = self.private_calls[username]
                    if other in self.voice_clients:
                        end_cmd = {'type': 'call_ended', 'user': username}
                        try:
                            self.send_with_length_prefix(self.voice_clients[other], end_cmd)
                        except:
                            pass
                    del self.private_calls[username]
                # 如果有人呼叫当前用户，也要清理
                for caller, callee in list(self.private_calls.items()):
                    if callee == username:
                        del self.private_calls[caller]
            
            try:
                voice_socket.close()
            except:
                pass
            
            print(f"{username} 离开语音系统")

class ChatServer:
    def __init__(self, host='0.0.0.0', port=8888, voice_port=8889):
        self.host = host
        self.port = port
        self.voice_port = voice_port
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients = {}
        self.lock = threading.Lock()
        
        # 启动语音服务器
        self.voice_server = VoiceServer(host, voice_port)
        voice_thread = threading.Thread(target=self.voice_server.start)
        voice_thread.daemon = True
        voice_thread.start()
        
        print(f"语音服务器已启动，端口: {voice_port}")
    
    def receive_complete_message(self, sock):
        """接收完整的 JSON 消息（处理粘包）"""
        buffer = b""
        while True:
            data = sock.recv(1024)
            if not data:
                return None
            
            buffer += data
            try:
                # 尝试解析 JSON，如果成功说明收到完整消息
                message = json.loads(buffer.decode())
                return message
            except json.JSONDecodeError:
                # 消息不完整，继续接收
                continue
    
    def start(self):
        self.server.bind((self.host, self.port))
        self.server.listen(5)
        print(f"聊天服务器启动在 {self.host}:{self.port}")
        
        while True:
            client_socket, addr = self.server.accept()
            print(f"新连接: {addr}")
            
            # 为新客户端创建线程
            thread = threading.Thread(
                target=self.handle_client,
                args=(client_socket, addr)
            )
            thread.daemon = True
            thread.start()
    
    def handle_client(self, client_socket, addr):
        """处理单个客户端连接"""
        username = None
        added_to_clients = False
        
        try:
            # 接收并验证用户名
            username_data = self.receive_complete_message(client_socket)
            if not username_data:
                return
                
            username = username_data.get('username')
            if not username:
                response = json.dumps({'status': 'error', 'message': '用户名不能为空'})
                client_socket.sendall(response.encode())
                return
            
            # 检查用户名是否已存在
            with self.lock:
                if username in self.clients:
                    response = json.dumps({'status': 'error', 'message': '用户名已存在'})
                    client_socket.sendall(response.encode())
                    return
                
                # 发送连接成功响应
                response = json.dumps({
                    'status': 'success',
                    'message': f'欢迎 {username} 加入聊天室',
                    'sender': '系统',
                    'type': 'connect',
                    'voice_port': self.voice_port  # 发送语音服务器端口
                })
                client_socket.sendall(response.encode())
                
                # 保存客户端信息
                self.clients[username] = {
                    'socket': client_socket,
                    'address': addr
                }
                added_to_clients = True
            
            print(f"{username} 加入聊天室")
            self.broadcast(f"{username} 加入了聊天室", sender="系统", exclude=username, msg_type='broadcast')
            
            # 发送欢迎消息给新用户
            welcome_msg = json.dumps({
                'sender': '系统',
                'message': f'欢迎加入聊天室！当前在线用户数: {len(self.clients)}',
                'voice_port': self.voice_port,  # 包含语音端口
                'type': 'system'
            })
            client_socket.sendall(welcome_msg.encode())
            
            # 持续接收消息
            while True:
                message_data = self.receive_complete_message(client_socket)
                if not message_data:
                    break
                    
                msg_type = message_data.get('type')
                
                if msg_type == 'message':
                    content = message_data.get('content', '')
                    if content.strip():
                        print(f"{username}: {content}")
                        self.broadcast(
                            content,
                            sender=username,
                            msg_type='message'
                        )
                        
                elif msg_type == 'private':
                    target = message_data.get('target')
                    content = message_data.get('content', '')
                    if target and content.strip():
                        self.send_private(
                            target,
                            f"{username} (私聊): {content}",
                            sender=username
                        )
                        
                elif msg_type == 'command':
                    if message_data.get('command') == 'users':
                        users_list = self.get_online_users()
                        response = json.dumps({
                            'sender': '系统',
                            'message': f'在线用户: {", ".join(users_list)}',
                            'type': 'users',
                            'users': users_list
                        })
                        client_socket.sendall(response.encode())
                
                elif msg_type == 'heartbeat':
                    response = json.dumps({'type': 'heartbeat_ack'})
                    client_socket.sendall(response.encode())
                
                elif msg_type == 'file':
                    file_name = message_data.get('file_name')
                    file_size = message_data.get('file_size')
                    file_content = message_data.get('file_content')
                    
                    if file_name and file_size and file_content:
                        print(f"{username} 上传了文件: {file_name} ({file_size} 字节)")
                        file_msg = json.dumps({
                            'type': 'file_receive',
                            'sender': username,
                            'file_name': file_name,
                            'file_size': file_size,
                            'file_content': file_content
                        })
                        self.broadcast_raw(file_msg)
                
                elif msg_type == 'image':
                    image_name = message_data.get('image_name')
                    image_content = message_data.get('image_content')
                    
                    if image_name and image_content:
                        print(f"{username} 发送了图片: {image_name}")
                        image_msg = json.dumps({
                            'type': 'image_receive',
                            'sender': username,
                            'image_name': image_name,
                            'image_content': image_content
                        })
                        self.broadcast_raw(image_msg)
                        
                elif msg_type == 'private_image':
                    target = message_data.get('target')
                    image_name = message_data.get('image_name')
                    image_content = message_data.get('image_content')
                    
                    if target and image_name and image_content:
                        print(f"{username} 私发图片给 {target}: {image_name}")
                        image_msg = json.dumps({
                            'type': 'image_receive',
                            'sender': username,
                            'image_name': image_name,
                            'image_content': image_content,
                            'private': True,
                            'target': target
                        })
                        
                        confirm_msg = json.dumps({
                            'type': 'private_sent',
                            'sender': '系统',
                            'message': f'[私聊给 {target}] 发送图片: {image_name}'
                        })
                        
                        with self.lock:
                            if target in self.clients:
                                try:
                                    self.clients[target]['socket'].sendall(image_msg.encode())
                                except:
                                    pass
                            
                            if username in self.clients:
                                try:
                                    self.clients[username]['socket'].sendall(confirm_msg.encode())
                                except:
                                    pass
                                     
                elif msg_type == 'private_file':
                    target = message_data.get('target')
                    file_name = message_data.get('file_name')
                    file_size = message_data.get('file_size')
                    file_content = message_data.get('file_content')
                    
                    if target and file_name and file_size and file_content:
                        print(f"{username} 私发文件给 {target}: {file_name} ({file_size} 字节)")
                        file_msg = json.dumps({
                            'type': 'file_receive',
                            'sender': username,
                            'file_name': file_name,
                            'file_size': file_size,
                            'file_content': file_content,
                            'private': True,
                            'target': target
                        })
                        
                        confirm_msg = json.dumps({
                            'type': 'private_sent',
                            'sender': '系统',
                            'message': f'[私聊给 {target}] 发送文件: {file_name}'
                        })
                        
                        with self.lock:
                            if target in self.clients:
                                try:
                                    self.clients[target]['socket'].sendall(file_msg.encode())
                                except:
                                    pass
                            
                            if username in self.clients:
                                try:
                                    self.clients[username]['socket'].sendall(confirm_msg.encode())
                                except:
                                    pass
                                    
                elif msg_type == 'voice_status':
                    # 语音状态通知
                    target = message_data.get('target')
                    status = message_data.get('status')
                    
                    if target and status:
                        voice_msg = json.dumps({
                            'type': 'voice_status',
                            'sender': username,
                            'status': status,
                            'target': target
                        })
                        
                        with self.lock:
                            if target in self.clients:
                                try:
                                    self.clients[target]['socket'].sendall(voice_msg.encode())
                                except:
                                    pass
    
        except json.JSONDecodeError as e:
            print(f"JSON 解析错误 ({addr}): {e}")
        except Exception as e:
            print(f"客户端 {addr} 错误: {e}")
        finally:
            if username and added_to_clients:
                with self.lock:
                    if username in self.clients:
                        del self.clients[username]
                self.broadcast(f"{username} 离开了聊天室", sender="系统", exclude=username, msg_type='broadcast')
            client_socket.close()
    
    def broadcast(self, message, sender="系统", exclude=None, msg_type='broadcast'):
        """广播消息给所有客户端"""
        data = json.dumps({
            'sender': sender,
            'message': message,
            'type': msg_type
        })
        
        with self.lock:
            for user, info in list(self.clients.items()):
                if user != exclude:
                    try:
                        info['socket'].sendall(data.encode())
                    except:
                        try:
                            info['socket'].close()
                        except:
                            pass
                        del self.clients[user]
    
    def broadcast_raw(self, data):
        """广播原始数据给所有客户端"""
        with self.lock:
            for user, info in list(self.clients.items()):
                try:
                    info['socket'].sendall(data.encode())
                except:
                    try:
                        info['socket'].close()
                    except:
                        pass
                    del self.clients[user]
    
    def send_private(self, target, message, sender):
        """发送私聊消息"""
        receiver_data = json.dumps({
            'sender': sender,
            'message': message,
            'type': 'private'
        })
        
        sender_data = json.dumps({
            'sender': '系统',
            'message': f'[私聊给 {target}] {message.split(": ")[1] if ": " in message else message}',
            'type': 'private_sent'
        })
        
        with self.lock:
            if target in self.clients:
                try:
                    self.clients[target]['socket'].sendall(receiver_data.encode())
                except:
                    pass
            
            if sender in self.clients:
                try:
                    self.clients[sender]['socket'].sendall(sender_data.encode())
                except:
                    pass
    
    def get_online_users(self):
        """获取在线用户列表"""
        with self.lock:
            return list(self.clients.keys())

if __name__ == "__main__":
    # 从命令行获取IP和端口
    host = sys.argv[1] if len(sys.argv) > 1 else '0.0.0.0'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8888
    voice_port = int(sys.argv[3]) if len(sys.argv) > 3 else 8889
    
    server = ChatServer(host, port, voice_port)
    try:
        server.start()
    except KeyboardInterrupt:
        print("服务器关闭")