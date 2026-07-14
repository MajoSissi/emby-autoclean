# emby-autoclean

可以自动删除已观看的剧集文件。

## 功能特性

- 可以定时触发, 使用cron格式
- 删除已观看超过指定天数的剧集文件
- 保留每个剧集最近N集不删除
- 支持只清理特定媒体库
- 支持只清理特定标签的文件
- 白名单保护（收藏和指定标签的文件不会被删除）
- 当剧集的所有集都被删除后，自动删除该剧集条目

## 快速开始

### 环境变量配置

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `EMBY_URL` | 是 | - | Emby服务器地址，如 `http://localhost:8096` |
| `EMBY_API_KEY` | 是 | - | Emby API密钥 |
| `CRON_SCHEDULE` | 否 | `0 2 * * *` | Cron表达式，默认每天凌晨2点执行 |
| `DAYS_TO_KEEP` | 否 | `30` | 保留已观看剧集的天数 |
| `KEEP_EPISODES` | 否 | `2` | 每部剧保留最近N集不删除 |
| `LIBRARY_FILTER` | 否 | - | 逗号分隔的媒体库名称，为空则清理所有TV库 |
| `TAG_FILTER` | 否 | - | 逗号分隔的标签，只清理包含这些标签的文件 |
| `WHITELIST_TAGS` | 否 | - | 逗号分隔的白名单标签，包含这些标签的文件不会被删除 |
| `DRY_RUN` | 否 | `false` | 设为 `true` 可预览删除操作而不实际删除 |
| `DELETE_EMPTY_SERIES` | 否 | `true` | 设为 `true` 当剧集所有集被删除后自动删除该剧集条目 |

### Docker运行

```bash
docker run -d \
  --name emby-autoclean \
  --restart unless-stopped \
  -e EMBY_URL=http://your-emby-server:8096 \
  -e EMBY_API_KEY=your-api-key \
  -e CRON_SCHEDULE="0 2 * * *" \
  -e DAYS_TO_KEEP=30 \
  -e KEEP_EPISODES=2 \
  your-username/emby-autoclean
```

### Docker Compose

创建 `.env` 文件：

```env
EMBY_URL=http://your-emby-server:8096
EMBY_API_KEY=your-api-key
CRON_SCHEDULE=0 2 * * *
DAYS_TO_KEEP=30
KEEP_EPISODES=2
DELETE_EMPTY_SERIES=true
DRY_RUN=false
```

运行：

```bash
docker-compose up -d
```

### 本地运行

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 文件配置
python -m app.main
```

## 获取Emby API密钥

1. 登录Emby管理面板
2. 进入设置 → 高级 → API密钥
3. 创建新的API密钥并复制

## 使用场景

### 场景1：保留最近5集，删除30天前的已观看剧集

```bash
docker run -d \
  -e EMBY_URL=http://emby:8096 \
  -e EMBY_API_KEY=xxx \
  -e KEEP_EPISODES=5 \
  -e DAYS_TO_KEEP=30 \
  your-username/emby-autoclean
```

### 场景2：只清理特定媒体库

```bash
docker run -d \
  -e EMBY_URL=http://emby:8096 \
  -e EMBY_API_KEY=xxx \
  -e LIBRARY_FILTER="美剧,日剧" \
  your-username/emby-autoclean
```

### 场景3：保护特定标签的文件

```bash
docker run -d \
  -e EMBY_URL=http://emby:8096 \
  -e EMBY_API_KEY=xxx \
  -e WHITELIST_TAGS="收藏,经典" \
  your-username/emby-autoclean
```

### 场景4：预览模式（不实际删除）

```bash
docker run -d \
  -e EMBY_URL=http://emby:8096 \
  -e EMBY_API_KEY=xxx \
  -e DRY_RUN=true \
  your-username/emby-autoclean
```

### 场景5：删除空剧集

```bash
docker run -d \
  -e EMBY_URL=http://emby:8096 \
  -e EMBY_API_KEY=xxx \
  -e DELETE_EMPTY_SERIES=true \
  your-username/emby-autoclean
```

## 注意事项

1. 首次运行建议使用 `DRY_RUN=true` 预览
2. 删除操作不可撤销，请确认配置正确
3. 建议定期检查日志确保正常运行
4. API密钥请妥善保管，不要泄露
