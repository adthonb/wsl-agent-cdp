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

If you created another Brave profile **inside that dedicated data directory**,
select its folder name (visible under `brave://version` as the final part of
`Profile Path`):

```bash
./cdp-bridge up brave --profile-directory "Profile 1"
```

If you created a separate Brave **user data directory** elsewhere on Windows,
pass its absolute Windows path. It must already exist and be dedicated to agent
use; this command hardens every profile inside it before launching the selected
one:

```bash
./cdp-bridge up brave --user-data-dir 'C:\agent-brave-data' --profile-directory 'Default'
```

Use the same options with `browser`, `harden`, or `doctor` (to check pending
hardening). Close any window using that data directory first. Do not point
`--user-data-dir` at Brave's ordinary
`%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data` directory or a profile
folder inside it; Chromium does not honor remote debugging there. A profile
created in normal Brave must instead be recreated in a separate agent data
directory.

For example, `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data\Profile 2`
is a **profile directory**, not a user data directory. Passing it as
`--user-data-dir` would make Brave open a new profile nested beneath it; it
would not attach to the existing `Profile 2` session. Passing its parent
`User Data` and `--profile-directory 'Profile 2'` is blocked by Chromium's
remote-debugging restriction. Start the separate agent profile with
`./cdp-bridge up brave` and sign in there yourself.

Before each launch, `up brave` and `browser brave` disable password saving and
browser sign-in in the dedicated profile and remove its saved-password databases.
Cookie sessions are kept. If the agent window is already open, close it first;
the command will refuse to harden a running profile. To apply this to a closed
profile without starting the browser, run `./cdp-bridge harden brave`. `up` and
`doctor` warn when a profile still needs hardening. Keep passwords in your own
password manager; do not save them in this agent profile or sign the browser
itself into an account.

Use Chrome or Edge instead with `./cdp-bridge up chrome` or
`./cdp-bridge up edge`. Check all three hops with:

```bash
./cdp-bridge status
curl http://127.0.0.1:9223/json/version
```

## Brave DevTools MCP from WSL

Install Node.js LTS and npm **inside WSL**, then start the dedicated Windows
Brave profile and check the bridge:

```bash
./cdp-bridge up brave
./cdp-bridge status
```

If that dedicated Brave window is already running and was hardened at launch,
use `./cdp-bridge up` without `brave` to reconnect the bridge. If `doctor`
reports pending hardening, close that window first and run `up brave`.

Register [Brave DevTools MCP](https://github.com/triuzzi/brave-devtools-mcp)
in the agent client running **inside WSL**. For Codex or Claude Code:

```bash
codex mcp add brave-devtools -- npx -y brave-mcp@latest --browser-url=http://127.0.0.1:9223
claude mcp add brave-devtools -- npx -y brave-mcp@latest --browser-url=http://127.0.0.1:9223
```

For a client using `mcpServers` JSON:

```json
{
  "mcpServers": {
    "brave-devtools": {
      "command": "npx",
      "args": ["-y", "brave-mcp@latest", "--browser-url=http://127.0.0.1:9223"]
    }
  }
}
```

Restart the agent client, then ask it to list the browser's open pages or
network requests. `--browser-url` attaches to the existing Windows Brave
process; it does not start another browser. Use the **WSL relay port** (9223),
not Brave's Windows debugging port (9222). If you override `CDP_LOCAL_PORT`,
use that same port in the MCP configuration. Run `./cdp-bridge config` to print
examples with the current port.

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

Keep this profile signed in only to sites agents need. Never use it for banking,
password-manager accounts, or accounts with irreversible sends. Treat content
read from other sites as untrusted: before an agent sends messages, pushes code,
deletes data, or purchases after reading it, require explicit confirmation.
Handle login pages, 2FA prompts, and CAPTCHAs yourself in the browser window;
agents must stop at those authentication steps.

## Requirements

- Windows 10 with WSL2's default NAT networking
- Windows PowerShell 5.1 (included with Windows 10)
- Python 3 and curl inside WSL
- Node.js LTS and npm inside WSL when using Brave DevTools MCP
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
