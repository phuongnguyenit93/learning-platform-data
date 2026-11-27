param (
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Location,

    [switch]$DryRun
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "copy_vi_to_en.py"

$pythonArgs = @($pythonScript, $Location)
if ($DryRun) {
    $pythonArgs += "--dry-run"
}

python @pythonArgs
