#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$BashPath = (Join-Path $env:LOCALAPPDATA 'Programs\Git\bin\bash.exe')
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

Assert-True (Test-Path -LiteralPath $BashPath -PathType Leaf) 'Git Bash is required for these offline tests.'
. (Join-Path $PSScriptRoot 'deploy.ps1') -ConsoleIp 192.0.2.1 -SshUser ark -DryRun
Assert-True (-not (Test-Path -LiteralPath $localStage)) 'Local staging was not removed.'
Assert-True ($sshOptions -contains 'NumberOfPasswordPrompts=1') 'Expected one password attempt.'
Assert-True ($sshOptions -contains '-T') 'The transfer must not allocate a remote terminal.'
$remoteScript | & $BashPath -n
Assert-True ($LASTEXITCODE -eq 0) 'Generated Bash has a syntax error.'

$fixture = $remoteScript.Substring(0, $remoteScript.IndexOf('config=/home/ark/'))
$fixture = $fixture.Replace('id ark > /dev/null', 'true')
$fixture = $fixture.Replace('test -x /usr/bin/python3', 'true')
$fixture = $fixture.Replace('test -d /opt/system/Advanced', 'true')
$fixture = $fixture.Replace('sudo -n true < /dev/null', 'true')
$fixture += "printf 'EXTRACT_OK\n'`n"
$corruptPayload = 'A' + $archivePayload.Substring(1)
Assert-True ($corruptPayload -ne $archivePayload) 'The corruption fixture must change the payload.'

$cases = @(
    @{ Name = 'CRLF transfer'; Payload = ($archivePayload -replace '(.{76})', "`$1`r`n"); Script = $fixture; Exit = 0; Extracted = $true },
    @{ Name = 'Corrupt archive'; Payload = $corruptPayload; Script = $fixture; Exit = 1; Extracted = $false },
    @{ Name = 'Truncated archive'; Payload = $archivePayload.Substring(0, 100); Script = $fixture; Exit = 1; Extracted = $false },
    @{ Name = 'Preflight failure'; Payload = $archivePayload; Script = "exit 42`n"; Exit = 42; Extracted = $false },
    @{ Name = 'Installation failure'; Payload = $archivePayload; Script = ($fixture + "exit 43`n"); Exit = 43; Extracted = $true }
)

foreach ($case in $cases) {
    $fixtureEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($case.Script))
    $testCommand = $remoteCommand.Replace($encoded, $fixtureEncoded)
    $output = $case.Payload | & $BashPath -c $testCommand
    $exitCode = $LASTEXITCODE
    Assert-True ($exitCode -eq $case.Exit) "$($case.Name): unexpected exit code $exitCode."
    Assert-True (($output -contains 'EXTRACT_OK') -eq $case.Extracted) "$($case.Name): unexpected extraction state."
    & $BashPath -c "test ! -e '$remoteStage'"
    Assert-True ($LASTEXITCODE -eq 0) "$($case.Name): remote staging was not removed."
    Write-Host "PASS: $($case.Name)"
}

Write-Host "All offline deployment tests passed on PowerShell $($PSVersionTable.PSVersion). No SSH connection was made."