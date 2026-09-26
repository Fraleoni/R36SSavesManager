#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ConsoleIp,
    [string]$SshUser,
    [switch]$PublishConfig,
    [switch]$StartService,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Invoke-Native {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Executable"
    }
}

function Confirm-Choice {
    param([string]$Prompt)
    return (Read-Host "$Prompt [y/N]") -match '^(y|yes)$'
}

$localStage = $null
$remoteStage = $null
$remoteCompleted = $false
try {
    if (-not $ConsoleIp) { $ConsoleIp = Read-Host 'Console IPv4 address (e.g. 192.168.1.43)' }
    if (-not $SshUser) {
        $SshUser = Read-Host 'SSH user [ark]'
        if (-not $SshUser) { $SshUser = 'ark' }
    }
    $address = $null
    if (-not [System.Net.IPAddress]::TryParse($ConsoleIp, [ref]$address) -or
        $address.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
        throw 'Specify a valid IPv4 address.'
    }
    $ConsoleIp = $address.ToString()
    if ($SshUser -notmatch '^[a-zA-Z_][a-zA-Z0-9_-]*$') {
        throw 'Invalid SSH username.'
    }
    if (-not $DryRun) {
        if (-not $PSBoundParameters.ContainsKey('PublishConfig')) {
            $PublishConfig = Confirm-Choice 'Publish config.json too? The remote version will be backed up'
        }
        if (-not $PSBoundParameters.ContainsKey('StartService')) {
            $StartService = Confirm-Choice 'Start the service after deployment?'
        }
    }

    $source = Split-Path -Parent $PSScriptRoot
    $files = @('R36SavesManager.py', 'config.json', 'index.html', 'app.js', 'console.png',
        'locales/en.json', 'locales/it.json',
        'packaging/install.sh', 'packaging/r36s-saves-manager.service', 'packaging/Saves Manager.sh')
    foreach ($file in $files) {
        if (-not (Test-Path -LiteralPath (Join-Path $source $file) -PathType Leaf)) {
            throw "Missing package file: $file"
        }
    }
    $null = Get-Content -LiteralPath (Join-Path $source 'config.json') -Raw | ConvertFrom-Json
    foreach ($language in @('en', 'it')) {
        $null = Get-Content -LiteralPath (Join-Path $source "locales/$language.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    $ssh = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
    $tar = Join-Path $env:WINDIR 'System32\tar.exe'
    foreach ($tool in @($ssh, $tar)) {
        if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
            throw "Missing Windows tool: $tool. Install the Windows OpenSSH client and tar."
        }
    }

    Write-Host "Destination: ${SshUser}@${ConsoleIp}; application layout: /home/ark"
    Write-Host "Publish configuration: $PublishConfig; start when complete: $StartService"
    Write-Host 'Deployment stops the web service and invalidates sessions. No reboot or autostart.'
    Write-Host 'The web password, ROMs and saves are not transferred or deleted.'
    if (-not $DryRun -and -not (Confirm-Choice 'Proceed? No import should be in progress')) {
        Write-Host 'Deployment cancelled.'
        return
    }

    $releaseId = [guid]::NewGuid().ToString('N')
    $localStage = Join-Path ([System.IO.Path]::GetTempPath()) "r36s-deploy-$releaseId"
    $null = New-Item -ItemType Directory -Path $localStage
    $archive = Join-Path $localStage 'package.tar.gz'
    Invoke-Native $tar (@('-czf', $archive, '-C', $source) + $files)
    $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    $remoteStage = "/tmp/r36s-deploy-$releaseId"
    $destination = "${SshUser}@${ConsoleIp}"
    $sshOptions = @('-T', '-o', 'ConnectTimeout=10', '-o', 'NumberOfPasswordPrompts=1')
    $archivePayload = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($archive))
    $publishFlag = if ($PublishConfig) { '1' } else { '0' }
    $startFlag = if ($StartService) { '1' } else { '0' }
    $remoteScript = @'
set -euo pipefail
stage='__STAGE__'
id ark > /dev/null
test -x /usr/bin/python3
test -d /opt/system/Advanced
sudo -n true < /dev/null
cd "$stage"
tr -d '\r\n' | base64 -d > package.tar.gz
printf '%s  package.tar.gz\n' '__HASH__' | sha256sum --check
tar -xzf package.tar.gz
bash -n packaging/install.sh
bash -n 'packaging/Saves Manager.sh'
config=/home/ark/.config/r36s-saves-manager/config.json
if [ '__PUBLISH__' = 1 ] && sudo -n test -f "$config"; then
    sudo -n test ! -L "$config"
    sudo -n cp -p -- "$config" "$config.before-__ID__.bak"
    printf 'Configuration backup: %s\n' "$config.before-__ID__.bak"
fi
sudo -n bash packaging/install.sh
if [ '__PUBLISH__' = 1 ]; then
    sudo -n install -o ark -g ark -m 0600 config.json "$config"
fi
if [ '__START__' = 1 ]; then
    bash '/opt/system/Advanced/Saves Manager.sh' --start
fi
systemctl show r36s-saves-manager.service --property=ActiveState --property=SubState --property=UnitFileState
'@
    $remoteScript = $remoteScript.Replace('__STAGE__', $remoteStage).Replace('__HASH__', $hash)
    $remoteScript = $remoteScript.Replace('__PUBLISH__', $publishFlag).Replace('__START__', $startFlag)
    $remoteScript = $remoteScript.Replace('__ID__', $releaseId).Replace("`r", '')
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript))
    $remoteCommand = "set -eu; umask 077; mkdir '$remoteStage'; trap 'rm -rf -- $remoteStage' EXIT; printf '%s' '$encoded' | base64 -d > '$remoteStage/deploy.sh'; bash '$remoteStage/deploy.sh'"

    if ($DryRun) {
        Write-Host "DRY RUN: archive created, SHA256 $hash"
        Write-Host ('Included files: ' + ($files -join ', '))
        Write-Host 'Transport: one SSH connection; Base64 archive on standard input; one password attempt.'
        Write-Host "Remote script (not executed):`n$remoteScript"
        Write-Host 'No connection or changes to the console.'
        return
    }

    Write-Host 'Enter the SSH password once in the OpenSSH prompt. If incorrect, rerun this script.'
    Write-Host 'On the first connection, verify the SSH fingerprint before accepting it.'
    $archivePayload | & $ssh @sshOptions $destination $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw "SSH deployment failed ($LASTEXITCODE)."
    }
    $remoteCompleted = $true
    Write-Host 'Deployment completed. No automatic startup at boot enabled.'
    if ($StartService) {
        Write-Host "Open http://${ConsoleIp}:8765 and sign in again."
    } else {
        Write-Host 'Service stopped. Start it from Advanced > Saves Manager > Start.'
    }
} catch {
    if ($remoteStage -and -not $DryRun -and -not $remoteCompleted) {
        Write-Warning "Deployment incomplete. Possible remote staging directory: $remoteStage. The service may be stopped."
    }
    throw
} finally {
    if ($localStage -and (Test-Path -LiteralPath $localStage)) {
        Remove-Item -LiteralPath $localStage -Recurse -Force
    }
}