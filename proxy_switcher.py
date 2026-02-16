#!/usr/bin/env python3
"""
Clash Verge Proxy Switcher
- List all proxy nodes across all profiles
- Test latency for all nodes
- Switch profile and proxy node via mihomo API
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def load_dotenv():
    """Load .env file from the same directory as this script."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value


load_dotenv()

# --- Config ---
CLASH_API = os.getenv("CLASH_API_URL", "http://127.0.0.1:9097")
CLASH_SECRET = os.getenv("CLASH_API_SECRET", "")
VERGE_DIR = Path.home() / "Library/Application Support/io.github.clash-verge-rev.clash-verge-rev"
PROFILES_DIR = VERGE_DIR / "profiles"
PROFILES_YAML = VERGE_DIR / "profiles.yaml"

# Nodes with these keywords in name are info-only, not real proxies
INFO_KEYWORDS = ["剩余流量", "距离下次", "套餐到期", "过期时间", "到期时间", "官网"]

HEADERS = {
    "Authorization": f"Bearer {CLASH_SECRET}",
    "Content-Type": "application/json",
}


def api_request(path, method="GET", data=None):
    url = f"{CLASH_API}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 204:
                return None
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"error": e.code, "message": body}
    except Exception as e:
        return {"error": str(e)}


def load_profiles_yaml():
    with open(PROFILES_YAML) as f:
        return yaml.safe_load(f)


def get_remote_profiles():
    data = load_profiles_yaml()
    current_uid = data.get("current", "")
    profiles = []
    for item in data.get("items", []):
        if item.get("type") == "remote":
            profiles.append({
                "uid": item["uid"],
                "name": item.get("name", item["uid"]),
                "file": item.get("file", ""),
                "active": item["uid"] == current_uid,
                "url": item.get("url", ""),
                "extra": item.get("extra"),
            })
    return profiles


def parse_profile_nodes(profile):
    filepath = PROFILES_DIR / profile["file"]
    if not filepath.exists():
        return []
    with open(filepath) as f:
        data = yaml.safe_load(f)
    nodes = []
    for p in data.get("proxies", []):
        name = p.get("name", "")
        if any(kw in name for kw in INFO_KEYWORDS):
            continue
        nodes.append({
            "name": name,
            "type": p.get("type", "unknown"),
            "server": p.get("server", ""),
            "port": p.get("port", ""),
            "profile": profile["name"],
            "profile_uid": profile["uid"],
        })
    return nodes


def test_single_node_delay(node_name, timeout=3000, test_url="https://www.gstatic.com/generate_204"):
    encoded = urllib.parse.quote(node_name, safe="")
    path = f"/proxies/{encoded}/delay?timeout={timeout}&url={urllib.parse.quote(test_url, safe='')}"
    result = api_request(path)
    if result and "delay" in result:
        return result["delay"]
    return -1


def cmd_list():
    profiles = get_remote_profiles()
    all_nodes = []
    for p in profiles:
        nodes = parse_profile_nodes(p)
        all_nodes.extend(nodes)

    print(f"\n{'='*80}")
    print(f" Clash Verge Proxy Nodes — {len(all_nodes)} total across {len(profiles)} profiles")
    print(f"{'='*80}\n")

    for p in profiles:
        marker = " ★ ACTIVE" if p["active"] else ""
        nodes = [n for n in all_nodes if n["profile_uid"] == p["uid"]]
        extra = ""
        if p.get("extra"):
            e = p["extra"]
            used = (e.get("upload", 0) + e.get("download", 0)) / 1024**3
            total = e.get("total", 0) / 1024**3
            extra = f"  [{used:.1f}/{total:.0f} GB]"
        print(f"  [{p['uid'][:8]}] {p['name']}{marker}{extra}")
        print(f"  {'—'*60}")
        for i, n in enumerate(nodes, 1):
            print(f"    {i:>2}. {n['name']:<45} {n['type']:<12} {n['server']}")
        print()


def cmd_test(profile_filter=None):
    profiles = get_remote_profiles()
    active = next((p for p in profiles if p["active"]), None)
    if not active:
        print("Error: no active profile found")
        return

    # Get currently loaded proxies from mihomo
    result = api_request("/proxies")
    if not result or "proxies" in result and not result["proxies"]:
        print("Error: cannot fetch proxies from mihomo API")
        return

    proxies = result["proxies"]
    # Filter to actual proxy nodes (not groups/special)
    real_nodes = {
        name: info for name, info in proxies.items()
        if info.get("type") not in ("Selector", "Direct", "Reject", "RejectDrop", "Pass", "Compatible")
        and not any(kw in name for kw in INFO_KEYWORDS)
    }

    print(f"\n Testing {len(real_nodes)} nodes from active profile [{active['name']}]...\n")

    results = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(test_single_node_delay, name): name for name in real_nodes}
        for future in as_completed(futures):
            name = futures[future]
            delay = future.result()
            results.append((name, real_nodes[name]["type"], delay))

    # Sort: available first (by delay), then unavailable
    results.sort(key=lambda x: (x[2] < 0, x[2]))

    print(f"  {'#':>3}  {'Node':<50} {'Type':<12} {'Delay':>8}")
    print(f"  {'—'*78}")
    for i, (name, ntype, delay) in enumerate(results, 1):
        if delay >= 0:
            delay_str = f"{delay}ms"
            color = "\033[32m" if delay < 300 else "\033[33m" if delay < 800 else "\033[31m"
            print(f"  {i:>3}  {name:<50} {ntype:<12} {color}{delay_str:>8}\033[0m")
        else:
            print(f"  {i:>3}  {name:<50} {ntype:<12} \033[90m timeout\033[0m")

    available = [r for r in results if r[2] >= 0]
    print(f"\n  {len(available)}/{len(results)} nodes available", end="")
    if available:
        best = available[0]
        print(f" | Best: {best[0]} ({best[2]}ms)")
    else:
        print()


def cmd_switch_profile(target):
    profiles = get_remote_profiles()
    # Match by name (partial) or uid
    match = None
    for p in profiles:
        if target.lower() in p["name"].lower() or target.lower() in p["uid"].lower():
            match = p
            break

    if not match:
        print(f"Error: profile '{target}' not found. Available:")
        for p in profiles:
            print(f"  - {p['name']} ({p['uid']})")
        return

    if match["active"]:
        print(f"Profile [{match['name']}] is already active.")
        return

    print(f"Switching to profile [{match['name']}] (uid: {match['uid']})...")

    # Step 1: Update profiles.yaml
    data = load_profiles_yaml()
    data["current"] = match["uid"]
    with open(PROFILES_YAML, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    # Step 2: Load the profile yaml directly into mihomo
    profile_path = str(PROFILES_DIR / match["file"])
    result = api_request("/configs?force=true", method="PUT", data={"path": profile_path})

    if result is None:  # 204 = success
        print(f"  mihomo config reloaded from {match['file']}")
        # Verify
        time.sleep(1)
        ver = api_request("/version")
        if ver:
            print(f"  mihomo {ver.get('version', '?')} running OK")
        # Show loaded proxies
        proxies = api_request("/proxies")
        if proxies:
            real = [
                name for name, info in proxies["proxies"].items()
                if info.get("type") not in ("Selector", "Direct", "Reject", "RejectDrop", "Pass", "Compatible")
                and not any(kw in name for kw in INFO_KEYWORDS)
            ]
            print(f"  {len(real)} proxy nodes loaded")
        print(f"\n  NOTE: Clash Verge GUI may still show the old profile.")
        print(f"  Open Clash Verge and click the profile to sync the GUI state.")
    else:
        print(f"  Error: {result}")


def cmd_switch_node(node_name, group="Proxies"):
    encoded_group = urllib.parse.quote(group, safe="")
    result = api_request(f"/proxies/{encoded_group}", method="PUT", data={"name": node_name})

    if result is None:  # 204 = success
        print(f"Switched [{group}] -> {node_name}")
        # Test delay
        delay = test_single_node_delay(node_name)
        if delay >= 0:
            print(f"  Delay: {delay}ms")
        else:
            print(f"  Warning: node may not be reachable")
    else:
        print(f"Error: {result}")
        # Show available nodes
        info = api_request(f"/proxies/{encoded_group}")
        if info and "all" in info:
            print(f"\nAvailable nodes in [{group}]:")
            for n in info["all"]:
                print(f"  - {n}")


def cmd_best(group="Proxies"):
    """Auto-select the best (lowest latency) node in a group."""
    encoded = urllib.parse.quote(group, safe="")
    info = api_request(f"/proxies/{encoded}")
    if not info or "all" not in info:
        print(f"Error: cannot read group [{group}]")
        return

    candidates = [
        n for n in info["all"]
        if not any(kw in n for kw in INFO_KEYWORDS)
        and n not in ("DIRECT", "REJECT", "PASS")
        # Exclude sub-groups (they are also selectors)
    ]

    # Check which are actual nodes vs sub-groups
    proxies = api_request("/proxies")
    actual_nodes = []
    for name in candidates:
        pinfo = proxies["proxies"].get(name, {})
        if pinfo.get("type") not in ("Selector", "Direct", "Reject", "RejectDrop", "Pass", "Compatible"):
            actual_nodes.append(name)

    print(f"\n Testing {len(actual_nodes)} nodes in [{group}]...\n")

    results = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(test_single_node_delay, name): name for name in actual_nodes}
        for future in as_completed(futures):
            name = futures[future]
            delay = future.result()
            results.append((name, delay))

    results.sort(key=lambda x: (x[1] < 0, x[1]))
    available = [(n, d) for n, d in results if d >= 0]

    for i, (name, delay) in enumerate(results[:10], 1):
        if delay >= 0:
            color = "\033[32m" if delay < 300 else "\033[33m" if delay < 800 else "\033[31m"
            print(f"  {i:>2}. {name:<50} {color}{delay}ms\033[0m")
        else:
            print(f"  {i:>2}. {name:<50} \033[90mtimeout\033[0m")

    if available:
        best_name, best_delay = available[0]
        print(f"\n  Best: {best_name} ({best_delay}ms)")
        result = api_request(f"/proxies/{encoded}", method="PUT", data={"name": best_name})
        if result is None:
            print(f"  Switched [{group}] -> {best_name}")
        else:
            print(f"  Error switching: {result}")
    else:
        print("\n  No available nodes!")


def cmd_status():
    profiles = get_remote_profiles()
    active = next((p for p in profiles if p["active"]), None)
    config = api_request("/configs")
    proxies = api_request("/proxies")

    print(f"\n{'='*60}")
    print(f" Clash Verge Status")
    print(f"{'='*60}\n")

    ver = api_request("/version")
    print(f"  Core:    mihomo {ver.get('version', '?')}")
    print(f"  Mode:    {config.get('mode', '?')}")
    print(f"  Port:    {config.get('mixed-port', '?')}")
    tun = config.get("tun", {})
    print(f"  TUN:     {'ON' if tun.get('enable') else 'OFF'} ({tun.get('device', '')})")
    print()

    print(f"  Profiles:")
    for p in profiles:
        marker = " ★" if p["active"] else "  "
        nodes = parse_profile_nodes(p)
        print(f"  {marker} {p['name']:<15} {len(nodes)} nodes  [{p['uid'][:8]}]")
    print()

    if proxies:
        # Show current selections for key groups
        key_groups = ["Proxies", "GLOBAL", "Telegram", "Netflix"]
        print(f"  Current Selections:")
        for g in key_groups:
            if g in proxies["proxies"]:
                now = proxies["proxies"][g].get("now", "—")
                print(f"    {g:<15} -> {now}")
    print()


def print_usage():
    print("""
Clash Verge Proxy Switcher

Usage:
  python3 proxy_switcher.py <command> [args]

Commands:
  status                  Show current status
  list                    List all nodes across all profiles
  test                    Test latency of current profile's nodes
  best [group]            Auto-select lowest latency node (default group: Proxies)
  switch-profile <name>   Switch to a different profile (partial name match)
  switch-node <name>      Switch proxy node in Proxies group
  switch-node <name> -g <group>   Switch node in a specific group
""")


def main():
    if len(sys.argv) < 2:
        print_usage()
        return

    cmd = sys.argv[1]

    if cmd == "status":
        cmd_status()
    elif cmd == "list":
        cmd_list()
    elif cmd == "test":
        cmd_test()
    elif cmd == "best":
        group = sys.argv[2] if len(sys.argv) > 2 else "Proxies"
        cmd_best(group)
    elif cmd == "switch-profile":
        if len(sys.argv) < 3:
            print("Usage: switch-profile <name>")
            return
        cmd_switch_profile(sys.argv[2])
    elif cmd == "switch-node":
        if len(sys.argv) < 3:
            print("Usage: switch-node <name> [-g group]")
            return
        node = sys.argv[2]
        group = "Proxies"
        if "-g" in sys.argv:
            gi = sys.argv.index("-g")
            if gi + 1 < len(sys.argv):
                group = sys.argv[gi + 1]
        cmd_switch_node(node, group)
    else:
        print(f"Unknown command: {cmd}")
        print_usage()


if __name__ == "__main__":
    main()
