# start_multiple_clients.py
# 用于在同一台电脑上启动多个客户端实例的脚本
import subprocess
import sys
import time
import os

# 要启动的客户端数量
CLIENT_COUNT = 2

# 客户端程序路径
CLIENT_PATH = "client_tcp.py"

def start_client(index):
    """启动一个客户端实例"""
    print(f"启动客户端 #{index+1}...")
    
    # 设置QT平台插件路径（根据用户提供的方法）
    env = os.environ.copy()
    env["QT_QPA_PLATFORM_PLUGIN_PATH"] = "venv\\Lib\\site-packages\\PyQt5\\Qt5\\plugins"
    
    # 使用不同的窗口标题来区分客户端
    window_title = f"网络聊天室 - 客户端 #{index+1}"
    cmd = [sys.executable, CLIENT_PATH, "--title", window_title]
    process = subprocess.Popen(cmd, env=env)
    return process

def main():
    print(f"将启动 {CLIENT_COUNT} 个客户端实例...")
    processes = []
    
    try:
        # 逐个启动客户端实例
        for i in range(CLIENT_COUNT):
            process = start_client(i)
            processes.append(process)
            # 等待一秒，避免同时弹出太多对话框
            time.sleep(1)
        
        print(f"已启动 {CLIENT_COUNT} 个客户端实例")
        print("请为每个客户端输入不同的用户名")
        
        # 等待所有客户端进程结束
        for i, process in enumerate(processes):
            process.wait()
            print(f"客户端 #{i+1} 已关闭")
            
    except KeyboardInterrupt:
        print("\n正在关闭所有客户端实例...")
        for process in processes:
            process.terminate()
        print("所有客户端已关闭")

if __name__ == "__main__":
    main()
