[CmdletBinding()]
param(
    [ValidateSet('Setup', 'Teardown', 'Browser')]
    [string]$Action = 'Setup',
    [ValidateSet('brave', 'chrome', 'edge')]
    [string]$Browser = 'brave',
    [ValidateRange(1, 65535)]
    [int]$BrowserPort = 9222,
    [ValidateRange(1, 65535)]
    [int]$ClientPort = 9223,
    [ValidateRange(1, 65535)]
    [int]$BridgePort = 9224,
    [string]$ListenAddress,
    [string]$WslAddress
)

$ErrorActionPreference = 'Stop'
$RuleName = "WSL CDP Bridge $BridgePort"
$StateRoot = Join-Path $env:LOCALAPPDATA 'wsl-cdp-bridge'
$StateFile = Join-Path $StateRoot "bridge-$BridgePort.txt"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-ElevatedSelf {
    $arguments = @(
        '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $PSCommandPath),
        '-Action', $Action,
        '-BridgePort', $BridgePort
    )
    if ($ListenAddress) { $arguments += @('-ListenAddress', $ListenAddress) }
    if ($WslAddress) { $arguments += @('-WslAddress', $WslAddress) }
    if ($Action -eq 'Setup') { $arguments += @('-BrowserPort', $BrowserPort) }

    $process = Start-Process -FilePath 'powershell.exe' -Verb RunAs `
        -ArgumentList $arguments -Wait -PassThru
    exit $process.ExitCode
}

function Invoke-Netsh {
    param([string[]]$Arguments, [switch]$IgnoreFailure)
    & "$env:SystemRoot\System32\netsh.exe" @Arguments | Out-Null
    if (-not $IgnoreFailure -and $LASTEXITCODE -ne 0) {
        throw "netsh failed (exit $LASTEXITCODE): $($Arguments -join ' ')"
    }
}

function Remove-OwnedRules {
    if (Test-Path -LiteralPath $StateFile) {
        $previousAddress = (Get-Content -LiteralPath $StateFile -Raw).Trim()
        if ($previousAddress -match '^\d{1,3}(\.\d{1,3}){3}$') {
            Invoke-Netsh @('interface', 'portproxy', 'delete', 'v4tov4',
                "listenaddress=$previousAddress", "listenport=$BridgePort", 'protocol=tcp') -IgnoreFailure
        }
    }
    if ($ListenAddress) {
        Invoke-Netsh @('interface', 'portproxy', 'delete', 'v4tov4',
            "listenaddress=$ListenAddress", "listenport=$BridgePort", 'protocol=tcp') -IgnoreFailure
    }
    # Older versions of this bridge listened on every interface.
    Invoke-Netsh @('interface', 'portproxy', 'delete', 'v4tov4',
        'listenaddress=0.0.0.0', "listenport=$BridgePort", 'protocol=tcp') -IgnoreFailure
    Remove-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
}

function Find-BrowserPath {
    $relativePaths = switch ($Browser) {
        'brave'  { 'BraveSoftware\Brave-Browser\Application\brave.exe' }
        'chrome' { 'Google\Chrome\Application\chrome.exe' }
        'edge'   { 'Microsoft\Edge\Application\msedge.exe' }
    }
    $roots = @($env:LOCALAPPDATA, $env:ProgramFiles, ${env:ProgramFiles(x86)}) |
        Where-Object { $_ }
    foreach ($root in $roots) {
        $candidate = Join-Path $root $relativePaths
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw "$Browser was not found in LocalAppData or Program Files."
}

if ($Action -in @('Setup', 'Teardown') -and -not (Test-Administrator)) {
    Invoke-ElevatedSelf
}

switch ($Action) {
    'Setup' {
        if ($ListenAddress -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
            throw 'A valid Windows/WSL gateway ListenAddress is required.'
        }
        if ($WslAddress -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
            throw 'A valid WSL IPv4 address is required.'
        }

        Remove-OwnedRules

        # A stale loopback listener on the actual browser port captures Chromium
        # before it can bind and can create a portproxy self-loop.
        Invoke-Netsh @('interface', 'portproxy', 'delete', 'v4tov4',
            'listenaddress=127.0.0.1', "listenport=$BrowserPort", 'protocol=tcp') -IgnoreFailure

        Set-Service -Name iphlpsvc -StartupType Automatic
        Start-Service -Name iphlpsvc
        Invoke-Netsh @('interface', 'portproxy', 'add', 'v4tov4',
            "listenaddress=$ListenAddress", "listenport=$BridgePort",
            'connectaddress=127.0.0.1', "connectport=$BrowserPort", 'protocol=tcp')

        New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow `
            -Protocol TCP -LocalAddress $ListenAddress -LocalPort $BridgePort `
            -RemoteAddress $WslAddress | Out-Null
        New-Item -ItemType Directory -Force -Path $StateRoot | Out-Null
        Set-Content -LiteralPath $StateFile -Value $ListenAddress -NoNewline
        Write-Host "Windows bridge ready: ${ListenAddress}:$BridgePort -> 127.0.0.1:$BrowserPort"
    }
    'Teardown' {
        Remove-OwnedRules
        Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
        Write-Host 'Windows bridge rules removed.'
    }
    'Browser' {
        $executable = Find-BrowserPath
        $profileRoot = Join-Path $env:LOCALAPPDATA 'wsl-cdp-bridge'
        $profile = Join-Path $profileRoot $Browser
        New-Item -ItemType Directory -Force -Path $profile | Out-Null
        $origins = "http://127.0.0.1:$ClientPort,http://localhost:$ClientPort"
        $arguments = @(
            "--remote-debugging-port=$BrowserPort",
            "--remote-allow-origins=$origins",
            "--user-data-dir=$profile",
            '--no-first-run',
            '--no-default-browser-check'
        )
        Start-Process -FilePath $executable -ArgumentList $arguments
        Write-Host "$Browser started with isolated profile: $profile"
    }
}
