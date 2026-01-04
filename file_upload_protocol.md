# 文件上传协议设计

## 协议概述
基于现有的JSON消息机制，设计文件上传协议，支持大文件分块传输和进度跟踪。

## 消息类型

### 1. 文件上传请求 (file_upload_request)
客户端发送文件上传请求，包含文件元数据

```json
{
  "type": "file_upload_request",
  "file_id": "唯一文件ID",
  "file_name": "文件名",
  "file_size": "文件大小(字节)",
  "file_type": "文件类型/扩展名",
  "timestamp": "上传时间戳"
}
```

### 2. 文件块传输 (file_upload_chunk)
客户端发送文件块数据，使用Base64编码

```json
{
  "type": "file_upload_chunk",
  "file_id": "唯一文件ID",
  "chunk_index": "块索引",
  "total_chunks": "总块数",
  "chunk_data": "Base64编码的文件块数据",
  "chunk_size": "块大小(字节)"
}
```

### 3. 文件上传完成 (file_upload_complete)
客户端通知服务器文件上传完成

```json
{
  "type": "file_upload_complete",
  "file_id": "唯一文件ID",
  "file_name": "文件名",
  "file_size": "文件大小(字节)"
}
```

### 4. 文件接收通知 (file_receive)
服务器转发给其他客户端的文件接收通知

```json
{
  "type": "file_receive",
  "sender": "发送者用户名",
  "file_id": "唯一文件ID",
  "file_name": "文件名",
  "file_size": "文件大小(字节)",
  "file_url": "文件下载路径或数据",
  "timestamp": "接收时间戳"
}
```

## 实现细节

1. **文件分块**：
   - 每个文件块大小为1024字节（可调整）
   - 使用Base64编码转换二进制数据为可传输的字符串
   - 计算总块数：`total_chunks = ceil(file_size / chunk_size)`

2. **文件ID生成**：
   - 使用UUID或时间戳+随机数生成唯一文件ID
   - 确保在传输过程中标识同一文件的不同块

3. **进度跟踪**：
   - 客户端可通过已发送块数计算上传进度
   - 服务器可通过已接收块数计算接收进度

4. **错误处理**：
   - 传输失败时客户端可重试发送特定块
   - 服务器验证文件完整性（可选）

## 与现有系统的兼容性

- 所有文件上传相关消息均采用JSON格式
- 复用现有的`receive_complete_message`方法处理消息
- 新消息类型扩展现有消息处理机制
