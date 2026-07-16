param(
    [Parameter(Mandatory = $true)]
    [string]$RequestFile,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir
)

$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSVersion -lt [version]'5.1') {
    throw "PowerShell 5.1 or newer is required. Found $($PSVersionTable.PSVersion)."
}

foreach ($command in @('Get-Content', 'ConvertFrom-Json', 'Invoke-RestMethod', 'ConvertTo-Json')) {
    if (-not (Get-Command -Name $command -ErrorAction SilentlyContinue)) {
        throw "Required built-in PowerShell command is unavailable: $command"
    }
}

$config = Get-Content -LiteralPath $RequestFile -Raw | ConvertFrom-Json
$EndpointUrl = $config.EndpointUrl
$ImagePaths = @(
    $config.image_paths |
    Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }
)
$ImageSuffixes = @('.bmp', '.jpeg', '.jpg', '.png', '.tif', '.tiff', '.b64', '.base64')

function Test-ImageBytes {
    param([byte[]]$Bytes)

    return (
        ($Bytes.Length -ge 3 -and $Bytes[0] -eq 0xFF -and $Bytes[1] -eq 0xD8 -and $Bytes[2] -eq 0xFF) -or
        ($Bytes.Length -ge 8 -and $Bytes[0] -eq 0x89 -and $Bytes[1] -eq 0x50 -and $Bytes[2] -eq 0x4E -and $Bytes[3] -eq 0x47 -and $Bytes[4] -eq 0x0D -and $Bytes[5] -eq 0x0A -and $Bytes[6] -eq 0x1A -and $Bytes[7] -eq 0x0A) -or
        ($Bytes.Length -ge 2 -and $Bytes[0] -eq 0x42 -and $Bytes[1] -eq 0x4D) -or
        ($Bytes.Length -ge 4 -and (($Bytes[0] -eq 0x49 -and $Bytes[1] -eq 0x49 -and $Bytes[2] -eq 0x2A -and $Bytes[3] -eq 0x00) -or ($Bytes[0] -eq 0x4D -and $Bytes[1] -eq 0x4D -and $Bytes[2] -eq 0x00 -and $Bytes[3] -eq 0x2A)))
    )
}

foreach ($field in @('FirstName', 'LastName', 'Sex', 'camera', 'DOB', 'DiabetesStatus', 'SmokingStatus')) {
    if ([string]::IsNullOrWhiteSpace([string]$config.$field)) {
        throw "Missing required assessment field: $field"
    }
}

if ($config.DOB -notmatch '^\d{4}/\d{2}/\d{2}$') { throw "DOB must match YYYY/MM/DD. Got: $($config.DOB)" }
if ($EndpointUrl -notmatch '^https?://') { throw "EndpointUrl must start with http:// or https://. Got: $EndpointUrl" }
if ($config.Sex -notin @('M', 'F')) { throw 'Sex must be M or F.' }
if ($config.DiabetesStatus -notin @('Yes', 'No')) { throw 'DiabetesStatus must be Yes or No.' }
if ($config.SmokingStatus -notin @('Yes', 'No')) { throw 'SmokingStatus must be Yes or No.' }

if ($ImagePaths.Count -eq 0) {
    $requestDirectory = Split-Path -Parent (Resolve-Path -LiteralPath $RequestFile)
    $ImagePaths = @(
        Get-ChildItem -LiteralPath $requestDirectory -File -Recurse |
        Where-Object {
            $_.Extension.ToLowerInvariant() -in $ImageSuffixes -and
            $_.FullName -notmatch '[\\/](\.git|__pycache__|results|venv|\.venv)[\\/]'
        } |
        Sort-Object FullName |
        Select-Object -ExpandProperty FullName
    )
}

if ($ImagePaths.Count -lt 2) {
    throw 'At least two supported image or Base64 files are required. Place them beside assessment-request.json or supply image_paths explicitly.'
}

$batchImages = foreach ($path in $ImagePaths) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Image file not found: $path" }
    $bytes = [System.IO.File]::ReadAllBytes($path)
    if (-not (Test-ImageBytes $bytes)) {
        try { $bytes = [Convert]::FromBase64String([System.Text.Encoding]::ASCII.GetString($bytes).Trim()) } catch { throw "Unsupported image or Base64 file: $path" }
        if (-not (Test-ImageBytes $bytes)) { throw "Base64 file does not decode to a supported image: $path" }
    }
    [ordered]@{
        ImageName = [System.IO.Path]::GetFileName($path)
        Image64 = [Convert]::ToBase64String($bytes)
    }
}

$payload = [ordered]@{
    FirstName = $config.FirstName
    LastName = $config.LastName
    Sex = $config.Sex
    camera = $config.camera
    DOB = $config.DOB
    DiabetesStatus = $config.DiabetesStatus
    SmokingStatus = $config.SmokingStatus
    batchimages = @($batchImages)
}

$jsonBody = $payload | ConvertTo-Json -Depth 8 -Compress

try {
    $response = Invoke-RestMethod -Method Post -Uri $EndpointUrl -ContentType 'application/json' -Body $jsonBody
    $rawOutput = $response | ConvertTo-Json -Depth 20
} catch {
    $statusCode = $null
    $errorBody = $null
    if ($_.Exception.Response) {
        $statusCode = [int]$_.Exception.Response.StatusCode
        try {
            $errorBody = $_.Exception.Response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        } catch {
            $errorBody = $_.Exception.Message
        }
    }
    $response = [ordered]@{
        error = $_.Exception.Message
        statusCode = $statusCode
        body = $errorBody
    }
    $rawOutput = $response | ConvertTo-Json -Depth 20
}

if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$requestFile = Join-Path $OutputDir "assessment_request_${timestamp}.json"
$outFile = Join-Path $OutputDir "assessment_response_${timestamp}.json"
Set-Content -LiteralPath $requestFile -Value $jsonBody -Encoding UTF8
$rawOutput | Set-Content -LiteralPath $outFile -Encoding UTF8
[ordered]@{
    request_path = $requestFile
    response_path = $outFile
} | ConvertTo-Json -Compress | Write-Output