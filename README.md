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

## 快速开始

### 前置要求

- [Node.js](https://nodejs.org/) >= 18
- [Clash Verge Rev](https://github.com/clash-verge-rev/clash-verge-rev) 已安装并运行
- 获取你的 Clash API Secret（见下方 [Clash Verge 配置](#clash-verge-配置)）

### Claude Code 一键安装

如果你使用 [Claude Code](https://docs.anthropic.com/en/docs/claude-code)，只需在终端中运行以下命令：

```bash
# 1. 克隆并构建
git clone https://github.com/anthropics/clash-verge-proxy-switcher.git
cd clash-verge-proxy-switcher
npm install && npm run build

# 2. 一键添加到 Claude Code（替换 your-secret 为你的 Clash API Secret）
claude mcp add clash-verge -e CLASH_API_SECRET=your-secret -- node $(pwd)/build/index.js
```

完成！现在在 Claude Code 中直接说 **"帮我切到日本节点"** 就能用了。

> 如果你的 Clash API 端口不是默认的 `9097`，额外添加 `-e CLASH_API_URL=http://127.0.0.1:你的端口`。

### OpenClaw 一键安装

如果你使用 [OpenClaw](https://github.com/nicepkg/openclaw)，在终端中运行：

```bash
# 1. 克隆并构建
git clone https://github.com/anthropics/clash-verge-proxy-switcher.git
cd clash-verge-proxy-switcher
npm install && npm run build

# 2. 手动添加 MCP 配置
```

编辑 OpenClaw 的 MCP 配置文件（通常位于 `~/.openclaw/mcp.json` 或对应的设置页面），添加：

```json
{
  "mcpServers": {
    "clash-verge": {
      "command": "node",
      "args": ["/你的完整路径/clash-verge-proxy-switcher/build/index.js"],
      "env": {
        "CLASH_API_SECRET": "your-secret",
        "CLASH_API_URL": "http://127.0.0.1:9097"
      }
    }
  }
}
```

### 其他 MCP 客户端

本工具兼容所有支持 MCP 协议的客户端（Claude Desktop、Cursor、Windsurf 等）。只需在对应客户端的 MCP 配置中添加上述 `mcpServers` 配置即可。

**Claude Desktop** 配置文件位置：
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

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

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CLASH_API_URL` | Clash RESTful API 地址 | `http://127.0.0.1:9097` |
| `CLASH_API_SECRET` | API 密钥 | 无（必须配置） |

除了通过 `claude mcp add -e` 传入环境变量外，你也可以在项目目录下创建 `.env` 文件：

```bash
cp .env.example .env
# 编辑 .env，填入你的 CLASH_API_SECRET
```

> `.env` 已加入 `.gitignore`，不会被提交到仓库。

## 使用示例

安装完成后，在 AI 对话中直接用自然语言操作代理：

```
"帮我看看当前代理状态"        → clash_status
"列出所有可用节点"            → clash_list_proxies
"测试所有节点的速度"          → clash_test_proxies
"帮我切到日本节点"            → clash_switch_proxy
"自动选择最快的节点"          → clash_select_best
"网速太慢了，换个快的"        → clash_select_best
"切换到美国的节点"            → clash_switch_proxy
"当前用的是哪个节点？"        → clash_status
```

## 技术栈

- **Runtime**: Node.js (ES2022)
- **Language**: TypeScript
- **Protocol**: MCP over stdio
- **Backend API**: mihomo RESTful API
- **SDK**: `@modelcontextprotocol/sdk`

## License

MIT
