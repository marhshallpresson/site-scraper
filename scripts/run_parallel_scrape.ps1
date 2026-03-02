param(
    [string]$Targets = "config/targets.json",
    [int]$MaxParallel = 2,
    [string]$OutputRoot = "scraped_site",
    [int]$MaxPages = 200,
    [int]$MaxDepth = 3,
    [int]$ClickLimit = 50,
    [int]$ClickDepth = 2,
    [int]$ScanInterval = 120,
    [switch]$Continuous
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$targetsPath = $Targets
if (-not (Test-Path $targetsPath)) {
    $targetsPath = Join-Path $repoRoot $Targets
}
if (-not (Test-Path $targetsPath)) {
    throw "Targets file not found: $Targets"
}

$targetsConfig = Get-Content $targetsPath -Raw | ConvertFrom-Json
$batchNames = @($targetsConfig.PSObject.Properties.Name)
if ($batchNames.Count -eq 0) {
    throw "No batches found in targets file: $targetsPath"
}

foreach ($batchName in $batchNames) {
    $urls = @($targetsConfig.$batchName)
    if ($urls.Count -eq 0) {
        continue
    }

    Write-Host ""
    Write-Host "Starting $batchName with $($urls.Count) target(s)..."
    $jobs = @()

    foreach ($url in $urls) {
        while ((@($jobs | Where-Object { $_.State -eq "Running" }).Count) -ge $MaxParallel) {
            Start-Sleep -Seconds 2
        }

        $domain = ([uri]$url).Host -replace "[^\w\-]", "_"
        $logPath = Join-Path $repoRoot ("logs/{0}.log" -f $domain)
        $logDir = Split-Path -Parent $logPath
        if (-not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Path $logDir | Out-Null
        }

        $args = @(
            "site_scraper.py",
            $url,
            "--output", $OutputRoot,
            "--max-pages", "$MaxPages",
            "--max-depth", "$MaxDepth",
            "--click-limit", "$ClickLimit",
            "--click-depth", "$ClickDepth",
            "--scroll",
            "--resource-same-domain-only",
            "--manifest-file", "manifest.json",
            "--log-file", $logPath
        )

        if ($Continuous) {
            $args += @("--continuous", "--scan-interval", "$ScanInterval")
        }

        $jobName = "$batchName-$domain"
        $jobs += Start-Job -Name $jobName -ScriptBlock {
            param($workdir, $argList)
            Set-Location $workdir
            & python @argList
            if ($LASTEXITCODE -ne 0) {
                throw "Scraper failed for $($argList[1]) with exit code $LASTEXITCODE"
            }
        } -ArgumentList $repoRoot, $args

        Write-Host ("Started {0} -> {1}" -f $url, $logPath)
    }

    if ($jobs.Count -eq 0) {
        continue
    }

    Wait-Job -Job $jobs | Out-Null
    foreach ($job in $jobs) {
        $jobErrors = $null
        $jobOutput = Receive-Job -Job $job -Keep -ErrorAction SilentlyContinue -ErrorVariable jobErrors
        if ($jobOutput) {
            $jobOutput | Out-String | Write-Host
        }
        if ($jobErrors) {
            Write-Warning ("Job {0} emitted error stream output." -f $job.Name)
        }
        if ($job.State -ne "Completed") {
            $reason = $job.ChildJobs[0].JobStateInfo.Reason
            $reasonText = if ($reason) { $reason.ToString() } else { "Unknown failure" }
            throw ("Job {0} did not complete successfully: {1}" -f $job.Name, $reasonText)
        }
    }
    Remove-Job -Job $jobs | Out-Null
    Write-Host "Completed $batchName."
}

Write-Host ""
Write-Host "All scrape batches completed."
