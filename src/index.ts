#!/usr/bin/env node

import "dotenv/config";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

// --- Config ---
const CLASH_API = process.env.CLASH_API_URL || "http://127.0.0.1:9097";
const CLASH_SECRET = process.env.CLASH_API_SECRET || "";

const INFO_KEYWORDS = [
  "剩余流量",
  "距离下次",
  "套餐到期",
  "过期时间",
  "到期时间",
  "官网",
];

const GROUP_TYPES = new Set([
  "Selector",
  "Direct",
  "Reject",
  "RejectDrop",
  "Pass",
  "Compatible",
  "URLTest",
  "Fallback",
  "LoadBalance",
  "Relay",
]);

function isInfoNode(name: string): boolean {
  return INFO_KEYWORDS.some((kw) => name.includes(kw));
}

function isRealProxy(type: string): boolean {
  return !GROUP_TYPES.has(type);
}

// --- API helpers ---

async function apiRequest(
  path: string,
  method = "GET",
  data?: unknown
): Promise<unknown> {
  const url = `${CLASH_API}${path}`;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${CLASH_SECRET}`,
    "Content-Type": "application/json",
  };
  const opts: RequestInit = { method, headers };
  if (data) opts.body = JSON.stringify(data);

  const resp = await fetch(url, opts);
  if (resp.status === 204) return null;
  return resp.json();
}

interface ProxyInfo {
  name: string;
  type: string;
  now?: string;
  all?: string[];
  history?: { delay: number }[];
  [key: string]: unknown;
}

interface ProxiesResponse {
  proxies: Record<string, ProxyInfo>;
}

async function getProxies(): Promise<ProxiesResponse> {
  return (await apiRequest("/proxies")) as ProxiesResponse;
}

async function testNodeDelay(
  nodeName: string,
  timeout = 5000,
  url = "http://www.gstatic.com/generate_204"
): Promise<number> {
  const encoded = encodeURIComponent(nodeName);
  const testUrl = encodeURIComponent(url);
  try {
    const result = (await apiRequest(
      `/proxies/${encoded}/delay?timeout=${timeout}&url=${testUrl}`
    )) as { delay?: number; message?: string };
    return result?.delay ?? -1;
  } catch {
    return -1;
  }
}

// --- MCP Server ---

const server = new McpServer({
  name: "clash-verge-proxy-switcher",
  version: "1.0.0",
});

// Tool 1: clash_status
server.tool("clash_status", "获取 Clash Verge 当前状态（版本、模式、端口、TUN、各策略组当前选择）", async () => {
  try {
    const [version, config, proxiesData] = await Promise.all([
      apiRequest("/version") as Promise<{ version?: string }>,
      apiRequest("/configs") as Promise<Record<string, unknown>>,
      getProxies(),
    ]);

    const tun = (config.tun as { enable?: boolean; device?: string }) || {};
    const lines: string[] = [];

    lines.push("=== Clash Verge Status ===");
    lines.push(`Core:    mihomo ${version?.version ?? "unknown"}`);
    lines.push(`Mode:    ${config.mode ?? "unknown"}`);
    lines.push(`Port:    ${config["mixed-port"] ?? "unknown"}`);
    lines.push(`TUN:     ${tun.enable ? "ON" : "OFF"}${tun.device ? ` (${tun.device})` : ""}`);
    lines.push("");

    // Show selector groups and their current selection
    const selectorGroups = Object.entries(proxiesData.proxies)
      .filter(([, info]) => info.type === "Selector")
      .sort((a, b) => a[0].localeCompare(b[0]));

    if (selectorGroups.length > 0) {
      lines.push("Strategy Groups:");
      for (const [name, info] of selectorGroups) {
        const nodeCount = (info.all ?? []).filter(
          (n) => !isInfoNode(n) && n !== "DIRECT" && n !== "REJECT"
        ).length;
        lines.push(`  ${name} -> ${info.now ?? "—"} (${nodeCount} nodes)`);
      }
    }

    return { content: [{ type: "text" as const, text: lines.join("\n") }] };
  } catch (e) {
    return {
      content: [{ type: "text" as const, text: `Error: ${e instanceof Error ? e.message : String(e)}` }],
      isError: true,
    };
  }
});

// Tool 2: clash_list_proxies
server.tool(
  "clash_list_proxies",
  "列出当前已加载的所有代理节点（过滤掉策略组和特殊节点）",
  async () => {
    try {
      const proxiesData = await getProxies();
      const proxies = proxiesData.proxies;

      // Find which groups each node belongs to
      const nodeGroups: Record<string, string[]> = {};
      for (const [groupName, info] of Object.entries(proxies)) {
        if (info.type === "Selector" && info.all) {
          for (const nodeName of info.all) {
            if (!nodeGroups[nodeName]) nodeGroups[nodeName] = [];
            nodeGroups[nodeName].push(groupName);
          }
        }
      }

      // Filter real proxy nodes
      const realNodes = Object.entries(proxies)
        .filter(([name, info]) => isRealProxy(info.type) && !isInfoNode(name))
        .sort((a, b) => a[0].localeCompare(b[0]));

      const lines: string[] = [];
      lines.push(`=== Proxy Nodes (${realNodes.length} total) ===`);
      lines.push("");

      for (const [name, info] of realNodes) {
        const groups = nodeGroups[name]?.join(", ") ?? "";
        lines.push(`  ${name}`);
        lines.push(`    Type: ${info.type}  Groups: ${groups}`);
      }

      return { content: [{ type: "text" as const, text: lines.join("\n") }] };
    } catch (e) {
      return {
        content: [{ type: "text" as const, text: `Error: ${e instanceof Error ? e.message : String(e)}` }],
        isError: true,
      };
    }
  }
);

// Tool 3: clash_test_proxies
server.tool(
  "clash_test_proxies",
  "对所有代理节点进行延迟测速，返回按延迟排序的结果",
  {
    timeout: z
      .number()
      .optional()
      .default(5000)
      .describe("测速超时时间（毫秒），默认 5000"),
    url: z
      .string()
      .optional()
      .default("http://www.gstatic.com/generate_204")
      .describe("测速 URL，默认 http://www.gstatic.com/generate_204"),
  },
  async ({ timeout, url }) => {
    try {
      const proxiesData = await getProxies();
      const realNodes = Object.entries(proxiesData.proxies).filter(
        ([name, info]) => isRealProxy(info.type) && !isInfoNode(name)
      );

      // Test all nodes concurrently
      const results = await Promise.allSettled(
        realNodes.map(async ([name, info]) => {
          const delay = await testNodeDelay(name, timeout, url);
          return { name, type: info.type, delay };
        })
      );

      const testResults = results
        .filter(
          (r): r is PromiseFulfilledResult<{ name: string; type: string; delay: number }> =>
            r.status === "fulfilled"
        )
        .map((r) => r.value)
        .sort((a, b) => {
          if (a.delay < 0 && b.delay < 0) return 0;
          if (a.delay < 0) return 1;
          if (b.delay < 0) return -1;
          return a.delay - b.delay;
        });

      const available = testResults.filter((r) => r.delay >= 0);
      const lines: string[] = [];
      lines.push(
        `=== Speed Test Results (${available.length}/${testResults.length} available) ===`
      );
      lines.push("");
      lines.push(`${"#".padStart(4)}  ${"Node".padEnd(50)} ${"Type".padEnd(12)} ${"Delay".padStart(8)}`);
      lines.push(`${"—".repeat(78)}`);

      for (let i = 0; i < testResults.length; i++) {
        const { name, type, delay } = testResults[i];
        const num = String(i + 1).padStart(4);
        const delayStr = delay >= 0 ? `${delay}ms` : "timeout";
        lines.push(
          `${num}  ${name.padEnd(50)} ${type.padEnd(12)} ${delayStr.padStart(8)}`
        );
      }

      if (available.length > 0) {
        lines.push("");
        lines.push(
          `Best: ${available[0].name} (${available[0].delay}ms)`
        );
      }

      return { content: [{ type: "text" as const, text: lines.join("\n") }] };
    } catch (e) {
      return {
        content: [{ type: "text" as const, text: `Error: ${e instanceof Error ? e.message : String(e)}` }],
        isError: true,
      };
    }
  }
);

// Tool 4: clash_switch_proxy
server.tool(
  "clash_switch_proxy",
  "在指定策略组中切换到指定代理节点",
  {
    node: z.string().describe("目标节点名称"),
    group: z
      .string()
      .optional()
      .default("Proxies")
      .describe("策略组名称，默认 Proxies"),
  },
  async ({ node, group }) => {
    try {
      const encodedGroup = encodeURIComponent(group);
      const resp = await fetch(`${CLASH_API}/proxies/${encodedGroup}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${CLASH_SECRET}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ name: node }),
      });

      if (resp.status === 204 || resp.ok) {
        // Test delay of the new node
        const delay = await testNodeDelay(node);
        const delayStr =
          delay >= 0 ? `${delay}ms` : "unreachable";
        return {
          content: [
            {
              type: "text" as const,
              text: `Switched [${group}] -> ${node}\nDelay: ${delayStr}`,
            },
          ],
        };
      } else {
        const body = await resp.text();
        // Show available nodes on error
        const groupInfo = (await apiRequest(
          `/proxies/${encodedGroup}`
        )) as ProxyInfo | null;
        let hint = "";
        if (groupInfo?.all) {
          hint = `\n\nAvailable nodes in [${group}]:\n${groupInfo.all
            .filter((n) => !isInfoNode(n))
            .map((n) => `  - ${n}`)
            .join("\n")}`;
        }
        return {
          content: [
            {
              type: "text" as const,
              text: `Error switching: ${resp.status} ${body}${hint}`,
            },
          ],
          isError: true,
        };
      }
    } catch (e) {
      return {
        content: [{ type: "text" as const, text: `Error: ${e instanceof Error ? e.message : String(e)}` }],
        isError: true,
      };
    }
  }
);

// Tool 5: clash_select_best
server.tool(
  "clash_select_best",
  "自动测速并切换到最快的代理节点",
  {
    group: z
      .string()
      .optional()
      .default("Proxies")
      .describe("策略组名称，默认 Proxies"),
  },
  async ({ group }) => {
    try {
      const encodedGroup = encodeURIComponent(group);
      const groupInfo = (await apiRequest(
        `/proxies/${encodedGroup}`
      )) as ProxyInfo | null;
      if (!groupInfo?.all) {
        return {
          content: [{ type: "text" as const, text: `Error: cannot read group [${group}]` }],
          isError: true,
        };
      }

      // Get all proxies to check types
      const proxiesData = await getProxies();
      const candidates = groupInfo.all.filter((name) => {
        if (isInfoNode(name)) return false;
        if (["DIRECT", "REJECT", "PASS"].includes(name)) return false;
        const pInfo = proxiesData.proxies[name];
        return pInfo && isRealProxy(pInfo.type);
      });

      // Test all candidates
      const results = await Promise.allSettled(
        candidates.map(async (name) => {
          const delay = await testNodeDelay(name);
          return { name, delay };
        })
      );

      const testResults = results
        .filter(
          (r): r is PromiseFulfilledResult<{ name: string; delay: number }> =>
            r.status === "fulfilled"
        )
        .map((r) => r.value)
        .sort((a, b) => {
          if (a.delay < 0 && b.delay < 0) return 0;
          if (a.delay < 0) return 1;
          if (b.delay < 0) return -1;
          return a.delay - b.delay;
        });

      const available = testResults.filter((r) => r.delay >= 0);
      const lines: string[] = [];
      lines.push(
        `=== Test ${candidates.length} nodes in [${group}] ===`
      );
      lines.push("");

      // Show top 10
      const top = testResults.slice(0, 10);
      for (let i = 0; i < top.length; i++) {
        const { name, delay } = top[i];
        const num = String(i + 1).padStart(3);
        const delayStr = delay >= 0 ? `${delay}ms` : "timeout";
        lines.push(`${num}. ${name.padEnd(50)} ${delayStr}`);
      }
      if (testResults.length > 10) {
        lines.push(`  ... and ${testResults.length - 10} more`);
      }

      lines.push("");
      lines.push(`${available.length}/${testResults.length} nodes available`);

      if (available.length > 0) {
        const best = available[0];
        // Switch to best
        const resp = await fetch(`${CLASH_API}/proxies/${encodedGroup}`, {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${CLASH_SECRET}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ name: best.name }),
        });

        if (resp.status === 204 || resp.ok) {
          lines.push("");
          lines.push(`Switched [${group}] -> ${best.name} (${best.delay}ms)`);
        } else {
          lines.push("");
          lines.push(`Best: ${best.name} (${best.delay}ms) but failed to switch`);
        }
      } else {
        lines.push("No available nodes!");
      }

      return { content: [{ type: "text" as const, text: lines.join("\n") }] };
    } catch (e) {
      return {
        content: [{ type: "text" as const, text: `Error: ${e instanceof Error ? e.message : String(e)}` }],
        isError: true,
      };
    }
  }
);

// --- Start server ---

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((e) => {
  console.error("Fatal error:", e);
  process.exit(1);
});
