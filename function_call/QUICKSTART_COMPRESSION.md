# 🚀 上下文压缩 - 快速开始

## 📦 安装依赖

### 1. 安装tiktoken（必需）

```bash
# 进入项目目录
cd function_call

# 安装依赖
pip install tiktoken

# 或安装所有依赖
pip install -r requirements_compression.txt
```

### 2. 验证安装

```bash
python -c "import tiktoken; print('✅ tiktoken安装成功')"
```

---

## ⚙️ 配置

### 方式1：环境变量（推荐）

在项目根目录的 `.env` 文件中添加：

```bash
# 启用压缩
ENABLE_COMPRESSION=true

# 压缩策略（推荐hybrid）
COMPRESSION_STRATEGY=hybrid

# 限制配置
MAX_MESSAGES=20
MAX_TOKENS=6000
COMPRESSION_THRESHOLD=10
```

### 方式2：使用配置模板

```bash
# 复制配置示例
cp compression_config.example .env

# 编辑配置文件
# Windows: notepad .env
# Linux/Mac: nano .env
```

---

## 🧪 测试压缩功能

### 运行测试脚本

```bash
cd function_call
python test_compression.py
```

### 预期输出

```
🔬 上下文压缩策略对比测试
=============================================================
📝 生成测试数据:
  对话轮数: 15
  总消息数: 61

📊 测试策略: HYBRID
=============================================================
📈 压缩统计:
  原始消息数: 61
  压缩后消息数: 18
  减少消息数: 43
  压缩率: 70.5%
  原始Token数: 8500
  压缩后Token数: 2700
  节省Token数: 5800
  Token压缩率: 68.2%

✅ 所有测试完成！
```

---

## 🚀 启动服务

### 1. 启动服务器

```bash
cd function_call
python tool_chains_streaming2.py
```

### 2. 观察启动日志

```
==================================================
🚀 服务启动中...
🔑 API密钥: 已设置
🤖 模型名称: qwen3-max
🛠️ 注册工具: get_city_code, get_weather, get_weather_forecast

🗜️ 上下文压缩:
   - 状态: 启用
   - 策略: hybrid
   - 最大消息数: 20
   - 最大Token数: 6000
   - 压缩阈值: 10
==================================================
```

---

## 📊 测试API

### 1. 发送对话请求

```bash
# 发送第一条消息
curl -X POST http://localhost:8000/query/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "北京天气怎么样？"}'
```

### 2. 继续对话（触发压缩）

```python
import requests
import json

conversation_id = None

# 发送多轮对话
for i in range(15):
    response = requests.post(
        "http://localhost:8000/query/stream",
        json={
            "query": f"第{i+1}个问题",
            "conversation_id": conversation_id
        },
        stream=True
    )
    
    for line in response.iter_lines():
        if line:
            data = json.loads(line)
            if data.get("event") == "conversation_start":
                conversation_id = data["conversation_id"]
                print(f"会话ID: {conversation_id}")
```

### 3. 查看压缩统计

服务端日志会显示：

```
🗜️ 触发上下文压缩 (消息数: 15 > 10)
📊 压缩统计:
   - 消息数: 15 → 12 (减少 20.0%)
   - Token数: 3200 → 2400 (节省 25.0%)
```

### 4. 查询会话统计

```bash
curl http://localhost:8000/conversation/{conversation_id}/stats
```

**响应示例：**
```json
{
  "conversation_id": "1728000000_abc123",
  "message_count": 12,
  "total_tokens": 2400,
  "role_distribution": {
    "system": 1,
    "user": 5,
    "assistant": 5,
    "tool": 1
  },
  "compression_enabled": true,
  "compression_strategy": "hybrid"
}
```

---

## 🎯 不同场景配置

### 场景1：简单问答（快速压缩）

```bash
COMPRESSION_STRATEGY=sliding_window
MAX_MESSAGES=15
COMPRESSION_THRESHOLD=8
```

### 场景2：客服对话（推荐）

```bash
COMPRESSION_STRATEGY=hybrid
MAX_MESSAGES=20
COMPRESSION_THRESHOLD=10
```

### 场景3：成本优先（激进压缩）

```bash
COMPRESSION_STRATEGY=token_limit
MAX_MESSAGES=12
MAX_TOKENS=3000
COMPRESSION_THRESHOLD=6
```

### 场景4：开发调试（禁用压缩）

```bash
ENABLE_COMPRESSION=false
```

---

## 📈 监控和优化

### 查看压缩配置

```bash
curl http://localhost:8000/compression/config
```

### 监控指标

在生产环境中，关注以下指标：

1. **压缩率** - 目标30%-50%
   ```python
   # 从日志中提取
   # 消息数: 15 → 12 (减少 20.0%)
   ```

2. **Token节省** - 目标40%-60%
   ```python
   # Token数: 3200 → 2400 (节省 25.0%)
   ```

3. **响应时间** - 应有提升
   ```python
   # 对比启用前后的平均响应时间
   ```

### 调优步骤

```python
# 1. 如果压缩率太高（>60%），可能影响对话质量
#    → 增大 COMPRESSION_THRESHOLD 和 MAX_MESSAGES

# 2. 如果Token数仍然超限
#    → 降低 MAX_TOKENS 或切换到 token_limit 策略

# 3. 如果工具调用失败
#    → 使用 smart_truncate 或 hybrid 策略

# 4. 如果对话不连贯
#    → 增大 keep_recent_messages（需修改代码）
```

---

## 🔍 故障排查

### 问题1：导入错误

```
ModuleNotFoundError: No module named 'tiktoken'
```

**解决：**
```bash
pip install tiktoken
```

### 问题2：导入错误（相对导入）

```
ModuleNotFoundError: No module named 'context_compression'
```

**解决：**
确保从 `function_call` 目录运行：
```bash
cd function_call
python tool_chains_streaming2.py
```

或者将 `function_call` 添加到 Python 路径：
```python
import sys
sys.path.insert(0, 'function_call')
```

### 问题3：压缩不生效

**检查：**
1. 确认 `ENABLE_COMPRESSION=true`
2. 确认消息数超过 `COMPRESSION_THRESHOLD`
3. 查看服务器日志

### 问题4：对话质量下降

**调整：**
```bash
# 增大阈值，减少压缩频率
COMPRESSION_THRESHOLD=15

# 增大保留消息数
MAX_MESSAGES=25

# 切换到保守策略
COMPRESSION_STRATEGY=smart_truncate
```

---

## 📚 完整文档

更详细的信息请参考：

- **详细指南**: `CONTEXT_COMPRESSION_GUIDE.md`
- **功能总结**: `README_COMPRESSION.md`
- **配置示例**: `compression_config.example`
- **核心代码**: `context_compression.py`
- **测试脚本**: `test_compression.py`

---

## ✅ 检查清单

在部署前确认：

- [ ] 已安装 tiktoken
- [ ] 已配置 .env 文件
- [ ] 已运行测试脚本验证
- [ ] 已设置合适的压缩策略
- [ ] 已配置监控告警

---

## 🎓 下一步

1. **性能测试** - 在测试环境压测
2. **A/B测试** - 对比不同配置
3. **监控部署** - 添加指标采集
4. **逐步上线** - 先小流量验证

---

## 💬 需要帮助？

- 查看日志中的压缩统计信息
- 使用 `/compression/config` API查看当前配置
- 使用 `/conversation/{id}/stats` 查看会话详情
- 参考完整文档获取更多信息

---

**快速开始完成！** 🎉

现在你可以享受更快、更省的对话体验了！

