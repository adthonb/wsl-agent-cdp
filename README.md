# WSL CDP bridge

Connect an MCP server running in WSL2 NAT mode to Chrome, Edge, or Brave running
on Windows:

```text
MCP -> WSL 127.0.0.1:9223 -> Windows gateway:9224 -> browser 127.0.0.1:9222
```

The local relay is byte-blind, so DevTools HTTP responses, WebSocket upgrades,
and large frames are passed unchanged. It also keeps the port echoed by
`webSocketDebuggerUrl` reachable from WSL.

## Quick start

From WSL:

```bash
chmod +x cdp-bridge
./cdp-bridge up brave
./cdp-bridge doctor
./cdp-bridge config
```

The Python project entry points are aliases for the same CLI, so
`uv run wsl-agent-cdp up brave` and `uv run cdp-bridge up brave` also work.

Accept the Windows UAC prompt on `up`. The first browser launch uses a new,
dedicated profile at `%LOCALAPPDATA%\wsl-cdp-bridge\brave`; sign in there if the
session needs authentication. Chromium 136 and newer intentionally refuse the
remote-debugging flag against the normal default profile.

Use Chrome or Edge instead with `./cdp-bridge up chrome` or
`./cdp-bridge up edge`. Check all three hops with:

```bash
./cdp-bridge status
curl http://127.0.0.1:9223/json/version
```

Run `./cdp-bridge up` after a WSL or Windows restart. It re-discovers the
changing WSL gateway, refreshes the Windows rule, and replaces a stale relay.
Stop and remove the narrowly scoped firewall/portproxy rules with:

```bash
./cdp-bridge down
```

Ports can be overridden consistently for every command:

```bash
CDP_BROWSER_PORT=9322 CDP_LOCAL_PORT=9323 CDP_BRIDGE_PORT=9324 \
  ./cdp-bridge up brave
```

## Security

Remote debugging grants complete control of the dedicated browser profile,
including its cookies, and CDP itself has no authentication. WSL2 distributions
on the same machine share the loopback namespace; reachable containers may also
be able to connect. `./cdp-bridge doctor` lists other installed distributions,
and every browser launch repeats the warning. Do not sign the agent profile into
sensitive accounts while untrusted code is running in another distribution or
container.

The Windows listener binds only to the current WSL
gateway address, the firewall rule permits only the current WSL guest address,
and the Linux endpoint binds only to loopback. Do not reuse your everyday
browser profile.

## Requirements

- Windows 10 with WSL2's default NAT networking
- Windows PowerShell 5.1 (included with Windows 10)
- Python 3 and curl inside WSL
- Brave, Chrome, or Edge installed on Windows

No `socat` installation is needed.

## Troubleshooting

- If UAC does not appear, run `./cdp-bridge up` from an interactive WSL shell.
- If the Windows hop is reachable but CDP is not, start the dedicated browser
  with `./cdp-bridge browser brave` and run `./cdp-bridge status` again.
- If a custom firewall policy blocks the generated rule, inspect it in an
  elevated PowerShell window with
  `Get-NetFirewallRule -DisplayName 'WSL CDP Bridge 9224'`.
- Browser flags only affect a newly created browser process for that profile.
  Close that dedicated profile and rerun the browser command if needed.

References: [WSL networking](https://learn.microsoft.com/windows/wsl/networking),
[netsh portproxy](https://learn.microsoft.com/windows-server/administration/windows-commands/netsh-interface),
[Chrome remote-debugging changes](https://developer.chrome.com/blog/remote-debugging-port),
and [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp).
