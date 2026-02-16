# Clash Verge Proxy Switcher

一个基于 [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) 的 Clash Verge 代理管理工具，让 AI 助手（如 Claude）能够直接查看和切换你的代理节点。

## 功能

| 工具 | 说明 |
|------|------|
| `clash_status` | 查看 Clash 运行状态（内核版本、模式、端口、TUN、策略组选择） |
| `clash_list_proxies` | 列出所有代理节点（自动过滤策略组和信息节点） |
| `clash_test_proxies` | 对所有节点进行延迟测速，按延迟排序 |
| `clash_switch_proxy` | 在指定策略组中切换到指定节点 |
| `clash_select_best` | 自动测速并切换到最快的节点 |

## 前置要求

- [Node.js](https://nodejs.org/) >= 18
- [Clash Verge Rev](https://github.com/clash-verge-rev/clash-verge-rev) 已安装并运行

## Clash Verge 配置

在使用本工具前，需要确保 Clash Verge 的外部控制（RESTful API）已开启。

### 1. 查看 API 端口和密钥

打开 Clash Verge -> **设置** -> **Clash 内核**，找到以下信息：

- **外部控制端口** — 默认为 `9097`（mihomo 内核）
- **API Secret** — 用于鉴权的密钥

你也可以在 Clash 运行时配置文件中查看，通常位于：

```
~/.config/clash-verge-rev/profiles/
```

配置文件中的相关字段：

```yaml
external-controller: 127.0.0.1:9097
secret: "your-api-secret-here"
```

### 2. 确认 API 可访问

在终端中测试 API 是否正常工作：

```bash
curl -H "Authorization: Bearer YOUR_SECRET" http://127.0.0.1:9097/version
```

如果返回类似 `{"meta":true,"version":"..."}` 的 JSON，说明 API 已就绪。

## 安装

```bash
git clone https://github.com/your-username/clash-verge-proxy-switcher.git
cd clash-verge-proxy-switcher
npm install
npm run build
```

## 配置

### 环境变量

复制 `.env.example` 为 `.env`，填入你的 Clash API 密钥：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
CLASH_API_URL=http://127.0.0.1:9097
CLASH_API_SECRET=your-clash-api-secret-here
```

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CLASH_API_URL` | Clash RESTful API 地址 | `http://127.0.0.1:9097` |
| `CLASH_API_SECRET` | API 密钥 | 无（必须配置） |

> `.env` 已加入 `.gitignore`，不会被提交到仓库。

### 在 Claude Code 中使用

项目已包含 `.mcp.json` 配置。在项目目录下使用 Claude Code 即可自动加载（会自动读取 `.env`）。

如需手动配置，编辑 `~/.claude/claude_desktop_config.json` 或项目下的 `.mcp.json`：

```json
{
  "mcpServers": {
    "clash-verge": {
      "command": "node",
      "args": ["/path/to/clash-verge-proxy-switcher/build/index.js"]
    }
  }
}
```

### 在 Claude Desktop 中使用

编辑 Claude Desktop 配置文件：

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

添加相同的 `mcpServers` 配置即可。

## 使用示例

在 Claude 对话中，你可以直接用自然语言操作代理：

```
"帮我看看当前代理状态"
→ 调用 clash_status

"列出所有可用节点"
→ 调用 clash_list_proxies

"测试所有节点的速度"
→ 调用 clash_test_proxies

"帮我切到日本节点"
→ 调用 clash_switch_proxy

"自动选择最快的节点"
→ 调用 clash_select_best
```

## 技术栈

- **Runtime**: Node.js (ES2022)
- **Language**: TypeScript
- **Protocol**: MCP over stdio
- **Backend API**: mihomo RESTful API
- **SDK**: `@modelcontextprotocol/sdk`

## License

MIT
