# Viết script PowerShell để tự động hóa Java tooling

PowerShell là shell và ngôn ngữ scripting phù hợp để tự động hóa các tác vụ Java như tìm JDK, biên dịch source, chạy ứng dụng, đóng gói JAR, kiểm tra checksum và thu thập diagnostic. PowerShell có pipeline dựa trên object, biến, function, exception handling và khả năng gọi trực tiếp các chương trình native như java, javac, jar và jcmd.

Khi làm việc trên nhiều hệ điều hành, nên dùng **PowerShell 7 (pwsh)** vì nó chạy trên Windows, Linux và macOS. Windows PowerShell 5.1 (powershell.exe) chỉ dành cho Windows nhưng vẫn phổ biến trong các script cũ và môi trường doanh nghiệp. Script trong bài được viết theo cú pháp tương thích PowerShell 5.1 trở lên; phần kiểm thử thực tế được chạy trên Windows PowerShell 5.1.26100.9711 với JDK 24.0.2.

## 1. PowerShell 5.1 và PowerShell 7

Có hai dòng PowerShell cần phân biệt:

| Phiên bản | Executable | Nền tảng | Runtime |
|---|---|---|---|
| Windows PowerShell 5.1 | powershell.exe | Windows | .NET Framework |
| PowerShell 7+ | pwsh | Windows, Linux, macOS | .NET |
| PowerShell 7.3+ | pwsh | Windows, Linux, macOS | Có cải tiến cách truyền argument cho native command |

Kiểm tra phiên bản hiện tại:

~~~powershell
$PSVersionTable | Format-List PSVersion, PSEdition, Platform, OS
~~~

Một output trên Windows PowerShell 5.1:

~~~text
PSVersion : 5.1.26100.9711
PSEdition : Desktop
~~~

PowerShell 7 thường hiển thị PSEdition là Core. Không nên suy ra hệ điều hành chỉ từ PSEdition vì PowerShell 7 chạy trên nhiều nền tảng.

Chạy script từ command prompt hoặc CI:

Windows PowerShell:

~~~powershell
powershell.exe -NoProfile -File .\scripts\build-java.ps1
~~~

PowerShell 7:

~~~powershell
pwsh -NoProfile -File ./scripts/build-java.ps1
~~~

Nếu đang ở trong một phiên PowerShell, có thể dùng call operator:

~~~powershell
& ./scripts/build-java.ps1 -MainClass com.example.HelloJava -Release 17
~~~

PowerShell 7 là lựa chọn phù hợp khi một script cần chạy cùng logic trên Windows, Linux và macOS. Nếu phải duy trì Windows PowerShell 5.1, tránh cú pháp hoặc API chỉ có trong PowerShell 6/7.

## 2. Cấu trúc cơ bản của một script

Một file script có phần tham số, thiết lập lỗi, function và phần thực thi. Đặt param ở đầu script, trước các lệnh thực thi:

~~~powershell
param(
    [string]$Name = "Java",
    [int]$Release = 17
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Output "Hello $Name"
Write-Output "Target release: $Release"
~~~

Các khái niệm thường dùng:

- Variable bắt đầu bằng ký tự $.
- String có thể dùng nháy đơn hoặc nháy kép.
- Array chứa nhiều giá trị.
- Hashtable lưu cặp key/value.
- Function gom logic để tái sử dụng.
- Pipeline chuyển object từ command này sang command khác.
- try/catch/finally xử lý lỗi và cleanup.
- Parameter giúp script nhận cấu hình từ command line hoặc CI.

PowerShell không chỉ chuyển text giữa các command. Ví dụ Get-ChildItem trả về object FileInfo/DirectoryInfo, có thể lọc bằng Where-Object, sắp xếp bằng Sort-Object và lấy thuộc tính bằng Select-Object.

### Function và parameter validation

~~~powershell
function Get-JavaReleaseLabel {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateRange(8, 99)]
        [int]$Release
    )

    return "Java SE $Release"
}

Get-JavaReleaseLabel -Release 17
~~~

Output:

~~~text
Java SE 17
~~~

ValidateRange chặn input ngoài phạm vi đã khai báo. Nó không chứng minh JDK đang cài hỗ trợ release đó; javac vẫn phải xác nhận bằng cách thực thi.

## 3. Dùng đường dẫn an toàn trên nhiều hệ điều hành

Windows thường dùng dấu gạch chéo ngược trong path, còn Linux/macOS dùng dấu gạch chéo xuôi. Tránh tự ghép path bằng cách nối chuỗi:

~~~powershell
# Fragile: separator and quoting are hard-coded
$source = "C:\project\src\Main.java"
~~~

Dùng Join-Path để tạo path theo hệ điều hành:

~~~powershell
$projectRoot = $PSScriptRoot
$sourceDirectory = Join-Path $projectRoot "src"
$outputDirectory = Join-Path $projectRoot "build/classes"
~~~

Các biến hữu ích:

| Biến | Ý nghĩa |
|---|---|
| PSScriptRoot | Thư mục chứa script hiện tại |
| PSCommandPath | Đường dẫn đầy đủ của script hiện tại |
| PWD | Thư mục làm việc hiện tại |
| JAVA_HOME | Thư mục gốc của JDK |
| PATH | Các thư mục shell tìm executable |

Dùng PSScriptRoot để script tìm source hoặc config tương đối với chính file script. Cách này ổn định hơn phụ thuộc vào thư mục mà CI chọn làm working directory.

Dùng LiteralPath khi làm việc với tên file có ký tự như ngoặc vuông:

~~~powershell
Get-Item -LiteralPath $sourceDirectory
Test-Path -LiteralPath $sourceDirectory -PathType Container
~~~

LiteralPath coi chuỗi là đường dẫn chính xác, không diễn giải wildcard như dấu ngoặc vuông hoặc dấu sao.

### Đường dẫn và filesystem case-sensitive

Windows thường dùng filesystem không phân biệt chữ hoa/chữ thường; Linux thường phân biệt. File HelloJava.java và hellojava.java có thể được coi là hai tên khác nhau trên Linux. Giữ đúng cách viết hoa/thường trong tên file, package, class và đường dẫn.

Không hard-code dấu phân cách path hoặc giả định mọi máy có ổ C:. Join-Path, Split-Path và PSScriptRoot giúp script dùng được trên các nền tảng khác nhau.

## 4. Tìm JDK và kiểm tra JAVA_HOME

JAVA_HOME nên trỏ tới thư mục gốc của JDK, ví dụ thư mục chứa bin, lib và conf. Không đặt JAVA_HOME trỏ trực tiếp vào bin hoặc vào một JRE rút gọn.

Kiểm tra:

~~~powershell
$env:JAVA_HOME
Get-Command java -CommandType Application
Get-Command javac -CommandType Application
java -version
javac -version
~~~

Một máy có thể cài nhiều JDK. Nếu PATH trỏ tới JDK khác với JAVA_HOME, lệnh java và javac có thể đến từ một phiên bản không mong muốn.

Function sau ưu tiên tool trong JAVA_HOME, sau đó mới tìm trên PATH. Nó thêm đuôi .exe trên Windows và dùng tên executable không có phần mở rộng trên Linux/macOS.

~~~powershell
function Get-JdkToolPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $fileName = if ($env:OS -eq "Windows_NT") {
        "$Name.exe"
    } else {
        $Name
    }

    if (-not [string]::IsNullOrWhiteSpace($env:JAVA_HOME)) {
        $candidate = Join-Path (Join-Path $env:JAVA_HOME "bin") $fileName

        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    $command = Get-Command $fileName -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($null -eq $command) {
        throw "Cannot find $fileName. Install a JDK and set JAVA_HOME or PATH."
    }

    return $command.Source
}

$java = Get-JdkToolPath -Name "java"
$javac = Get-JdkToolPath -Name "javac"

Write-Output "java: $java"
Write-Output "javac: $javac"
~~~

Trên Windows, biến môi trường OS thường có giá trị Windows_NT. Trên Linux và macOS, biến này thường không được đặt, nên function dùng tên tool không có .exe.

PowerShell 6+ có các biến tự động như IsWindows, IsLinux và IsMacOS. Các biến này không tồn tại trong Windows PowerShell 5.1. Nếu script cần tương thích 5.1, không dùng chúng nếu chưa có fallback.

## 5. Gọi java, javac và jar từ PowerShell

PowerShell dùng call operator & để chạy executable:

~~~powershell
$javac = Get-JdkToolPath -Name "javac"

& $javac --version
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    throw "javac --version failed with exit code $exitCode"
}
~~~

Các lệnh java, javac, jar và jcmd là native executable, không phải cmdlet PowerShell. Vì vậy có một số khác biệt quan trọng:

- $LASTEXITCODE chứa exit code gần nhất của native command.
- $? chỉ cho biết lệnh gần nhất thành công theo góc nhìn PowerShell; nó không thay thế exit code số.
- $ErrorActionPreference = "Stop" xử lý terminating error của PowerShell, nhưng trong Windows PowerShell 5.1 nó không tự biến mọi native exit code khác 0 thành exception.
- Hãy lưu $LASTEXITCODE ngay sau từng lệnh native, trước khi chạy command khác.

Ví dụ:

~~~powershell
& $java -version
$javaVersionExit = $LASTEXITCODE

if ($javaVersionExit -ne 0) {
    throw "java -version failed with exit code $javaVersionExit"
}

& $javac -version
$javacVersionExit = $LASTEXITCODE

if ($javacVersionExit -ne 0) {
    throw "javac -version failed with exit code $javacVersionExit"
}
~~~

Không đợi đến cuối script mới đọc $LASTEXITCODE. Một native command khác có thể ghi đè giá trị đó.

### Truyền argument bằng array và splatting

Không xây dựng một chuỗi command rồi chạy bằng Invoke-Expression. Cách đó dễ gặp lỗi quoting và tạo nguy cơ command injection nếu chuỗi có dữ liệu bên ngoài.

Dùng array argument:

~~~powershell
$arguments = @(
    "--release", "17",
    "-encoding", "UTF-8",
    "-d", $outputDirectory,
    $sourceFile
)

& $javac @arguments
$compileExitCode = $LASTEXITCODE
~~~

Dấu @ trước tên array là splatting: mỗi phần tử được truyền như một argument riêng. Cách này giúp đường dẫn có dấu cách được truyền đúng trong các trường hợp thông thường.

PowerShell 7.3 cải thiện cách serialize argument cho native command và cung cấp biến PSNativeCommandArgumentPassing. Windows PowerShell 5.1 sử dụng cơ chế legacy. Nếu truyền argument chứa dấu nháy kép lồng nhau, dấu gạch chéo cuối hoặc cú pháp đặc biệt của chương trình native, hãy kiểm thử trên từng shell/version được hỗ trợ.

## 6. Phân biệt lỗi PowerShell và lỗi chương trình Java

PowerShell có hai nhóm lỗi thường gặp:

**Lỗi của cmdlet hoặc script:** ví dụ đường dẫn không tồn tại, parameter sai hoặc file không đọc được. Có thể dùng try/catch và ErrorActionPreference để xử lý.

**Lỗi của native process:** ví dụ javac compile thất bại hoặc Java application trả exit code 7. Cần kiểm tra LASTEXITCODE.

Ví dụ:

~~~powershell
try {
    & $java -cp $outputDirectory "com.example.HelloJava"
    $runExitCode = $LASTEXITCODE

    if ($runExitCode -ne 0) {
        throw "Java application failed with exit code $runExitCode"
    }
}
catch {
    Write-Error "Build step failed: $($_.Exception.Message)"
    exit 1
}
~~~

Nếu cần trả chính xác exit code của Java process cho CI, có thể dùng:

~~~powershell
& $java -jar $jarPath
$runExitCode = $LASTEXITCODE

if ($runExitCode -ne 0) {
    exit $runExitCode
}
~~~

Khi dùng exit, script kết thúc ngay. Nếu có file tạm hoặc resource cần cleanup, đặt cleanup trong finally và thiết kế luồng điều khiển sao cho finally được chạy trước khi thoát.

PowerShell 7.3+ có thể cấu hình PSNativeCommandUseErrorActionPreference để biến native exit code khác 0 thành error theo preference. Tuy nhiên script dùng chung nhiều phiên bản nên vẫn nên kiểm tra LASTEXITCODE rõ ràng.

## 7. Ví dụ Java 17+: build và chạy project bằng PowerShell

Cấu trúc project:

~~~text
java-demo/
├── scripts/
│   └── build-java.ps1
├── src/
│   └── com/
│       └── example/
│           ├── HelloJava.java
│           └── ExitCodeDemo.java
└── build/
    └── classes/
~~~

### HelloJava.java

~~~java
package com.example;

public final class HelloJava {
    public static void main(String[] args) {
        System.out.println("Hello from Java on PowerShell");
    }
}
~~~

### ExitCodeDemo.java

~~~java
package com.example;

public final class ExitCodeDemo {
    public static void main(String[] args) {
        System.err.println("intentional failure");
        System.exit(7);
    }
}
~~~

### scripts/build-java.ps1

Đặt đoạn script sau vào file build-java.ps1:

~~~powershell
param(
    [string]$MainClass = "com.example.HelloJava",
    [int]$Release = 17
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-JdkToolPath {
    param([Parameter(Mandatory = $true)][string]$Name)

    $fileName = if ($env:OS -eq "Windows_NT") {
        "$Name.exe"
    } else {
        $Name
    }

    if (-not [string]::IsNullOrWhiteSpace($env:JAVA_HOME)) {
        $candidate = Join-Path (Join-Path $env:JAVA_HOME "bin") $fileName

        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    $command = Get-Command $fileName -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($null -eq $command) {
        throw "Cannot find $fileName. Install a JDK and set JAVA_HOME or PATH."
    }

    return $command.Source
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceDirectory = Join-Path $projectRoot "src"
$outputDirectory = Join-Path $projectRoot "build/classes"

if (-not (Test-Path -LiteralPath $sourceDirectory -PathType Container)) {
    throw "Source directory not found: $sourceDirectory"
}

$sourceFiles = @(
    Get-ChildItem -LiteralPath $sourceDirectory -Filter "*.java" -File -Recurse |
        Sort-Object -Property FullName |
        ForEach-Object { $_.FullName }
)

if ($sourceFiles.Count -eq 0) {
    throw "No Java source files found in $sourceDirectory"
}

$null = New-Item -ItemType Directory -Force -Path $outputDirectory

$javac = Get-JdkToolPath -Name "javac"
$java = Get-JdkToolPath -Name "java"

$compileArgs = @(
    "--release", $Release.ToString(),
    "-encoding", "UTF-8",
    "-d", $outputDirectory
) + $sourceFiles

Write-Output "Compiling $($sourceFiles.Count) Java source file(s) with JDK release $Release"

& $javac @compileArgs
$compileExitCode = $LASTEXITCODE

if ($compileExitCode -ne 0) {
    throw "javac failed with exit code $compileExitCode"
}

Write-Output "Running $MainClass"

& $java "-cp" $outputDirectory $MainClass
$runExitCode = $LASTEXITCODE

if ($runExitCode -ne 0) {
    throw "java exited with code $runExitCode"
}

Write-Output "Build and run succeeded"
~~~

### Chạy trên Windows PowerShell

Từ thư mục project:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-java.ps1
~~~

Hoặc từ một phiên PowerShell đã mở:

~~~powershell
& .\scripts\build-java.ps1 -MainClass "com.example.HelloJava" -Release 17
~~~

### Chạy trên PowerShell 7

~~~powershell
pwsh -NoProfile -File ./scripts/build-java.ps1 -MainClass com.example.HelloJava -Release 17
~~~

Trên Linux/macOS, cài PowerShell 7 và JDK, đặt JAVA_HOME nếu cần rồi gọi pwsh. Script dùng Join-Path, PSScriptRoot và tên executable theo OS nên không cần hard-code path Windows.

### Output khi chạy thành công

Trên Windows PowerShell 5.1.26100.9711 và JDK 24.0.2, project thử nghiệm nằm trong đường dẫn có dấu cách đã cho output:

~~~text
Compiling 2 Java source file(s) with JDK release 17
Running com.example.HelloJava
Hello from Java on PowerShell
Build and run succeeded
~~~

Script compile cả hai source file với javac --release 17, sau đó chạy class chính.

### Kiểm tra lỗi exit code

Chạy class chủ động trả exit code 7:

~~~powershell
powershell.exe -NoProfile -File .\scripts\build-java.ps1 -MainClass "com.example.ExitCodeDemo"
~~~

Output liên quan:

~~~text
Compiling 2 Java source file(s) with JDK release 17
Running com.example.ExitCodeDemo
intentional failure
java exited with code 7
~~~

PowerShell script kết thúc với exit code khác 0 (trong lần thử này là 1 do exception chưa xử lý). Điều này giúp CI đánh dấu job thất bại thay vì tiếp tục như thể Java chạy thành công.

## 8. Đóng gói và chạy JAR

Sau khi compile, có thể gọi jar để đóng gói class:

~~~powershell
$jar = Get-JdkToolPath -Name "jar"
$jarPath = Join-Path $projectRoot "build/java-demo.jar"

$jarArgs = @(
    "--create",
    "--file", $jarPath,
    "-C", $outputDirectory,
    "."
)

& $jar @jarArgs
$jarExitCode = $LASTEXITCODE

if ($jarExitCode -ne 0) {
    throw "jar failed with exit code $jarExitCode"
}
~~~

Lệnh này tạo JAR chứa class file. Để chạy bằng java -jar, archive cần manifest có Main-Class. Có thể tạo manifest file rồi truyền vào jar:

~~~text
Main-Class: com.example.HelloJava

~~~

Ví dụ tạo manifest và đóng gói:

~~~powershell
$manifestPath = Join-Path $projectRoot "build/MANIFEST.MF"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$manifestContent = "Main-Class: com.example.HelloJava" + [Environment]::NewLine + [Environment]::NewLine

[System.IO.File]::WriteAllText($manifestPath, $manifestContent, $utf8NoBom)

& $jar "--create" "--file" $jarPath "--manifest" $manifestPath "-C" $outputDirectory "."
$jarExitCode = $LASTEXITCODE

if ($jarExitCode -ne 0) {
    throw "jar packaging failed with exit code $jarExitCode"
}

& $java "-jar" $jarPath
$runExitCode = $LASTEXITCODE

if ($runExitCode -ne 0) {
    throw "java -jar failed with exit code $runExitCode"
}
~~~

Đường dẫn được truyền thành argument riêng nên có thể chứa dấu cách. Dùng UTF-8 không BOM cho file manifest do script tạo và kết thúc manifest bằng dòng trống theo định dạng manifest JAR.

## 9. Encoding và newline giữa Windows và Unix

Encoding là một nguồn lỗi thường gặp khi script tạo file Java, properties, manifest hoặc checksum list.

Windows PowerShell 5.1 và PowerShell 7 có khác biệt:

| Lệnh | Windows PowerShell 5.1 | PowerShell 7 |
|---|---|---|
| Set-Content -Encoding UTF8 | UTF-8 có BOM | UTF-8 không BOM |
| Out-File mặc định | UTF-16LE | UTF-8 |
| Set-Content mặc định | Encoding phụ thuộc hệ thống | UTF-8 không BOM |

Để tạo file UTF-8 không BOM nhất quán, dùng .NET:

~~~powershell
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

[System.IO.File]::WriteAllText(
    $filePath,
    $content,
    $utf8NoBom
)
~~~

Khi ghi file nhiều dòng, hãy quyết định newline có cần cố định hay không. Windows thường dùng CRLF, Unix-like thường dùng LF. Với source Java, javac chấp nhận cả hai, nhưng nếu file được đưa vào reproducible build hoặc checksum comparison, newline khác nhau làm byte content khác nhau.

Trong repository, có thể chuẩn hóa line ending bằng .gitattributes và giữ encoding thống nhất.

## 10. Xử lý output và log

PowerShell có nhiều output stream: Success, Error, Warning, Verbose, Debug và Information. Dùng đúng stream giúp CI phân loại log.

~~~powershell
Write-Output "Normal build information"
Write-Warning "Optional configuration is missing"
Write-Verbose "Resolved javac path: $javac"
Write-Error "Build failed"
~~~

Bật verbose khi cần:

~~~powershell
$VerbosePreference = "Continue"
~~~

Ghi log:

~~~powershell
Start-Transcript -Path "./build/powershell-build.log" -Append

try {
    & ./scripts/build-java.ps1
    $scriptExit = $LASTEXITCODE
}
finally {
    Stop-Transcript
}
~~~

Transcript ghi lại lệnh và output của phiên PowerShell. Với CI, cũng có thể redirect stdout/stderr của job hoặc upload log làm artifact.

Không gộp stderr vào stdout nếu pipeline cần phân biệt hai luồng. PowerShell 7 và Windows PowerShell 5.1 có một số khác biệt trong cách xử lý native stderr; kiểm thử script trên phiên bản shell mục tiêu.

## 11. Tích hợp PowerShell vào CI

PowerShell có thể dùng làm shell thống nhất cho job Windows, Linux và macOS nếu runner đã cài PowerShell 7.

### GitHub Actions

Ví dụ workflow chạy trên Ubuntu:

~~~yaml
name: Java PowerShell build

on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - name: Build with PowerShell
        shell: pwsh
        run: ./scripts/build-java.ps1
~~~

Để kiểm tra trên Windows hoặc macOS, có thể tạo thêm job tương ứng với runner windows-latest hoặc macos-latest. Các runner đó cần dùng shell pwsh nếu muốn giữ cùng phiên bản PowerShell.

### GitLab CI

~~~yaml
stages:
  - build

java-build:
  stage: build
  script:
    - pwsh -NoProfile -File ./scripts/build-java.ps1
~~~

Runner cần có pwsh và JDK. Nếu runner chỉ có Windows PowerShell 5.1, dùng powershell.exe và kiểm tra compatibility của script.

### Jenkins

Trên agent có PowerShell 7:

~~~groovy
pipeline {
    agent any

    stages {
        stage('Java build') {
            steps {
                pwsh './scripts/build-java.ps1'
            }
        }
    }
}
~~~

Trên Windows agent dùng Windows PowerShell:

~~~groovy
pipeline {
    agent { label 'windows' }

    stages {
        stage('Java build') {
            steps {
                powershell '.\\scripts\\build-java.ps1'
            }
        }
    }
}
~~~

Trong CI, để script trả exit code khác 0 khi compile hoặc run thất bại. Không bắt exception rồi chỉ Write-Warning và tiếp tục job.

## 12. Tham số, environment và cấu hình

Không hard-code mọi giá trị vào script. Dùng parameter để người chạy hoặc CI chọn release, main class và output directory.

~~~powershell
param(
    [ValidateRange(8, 99)]
    [int]$Release = 17,

    [string]$MainClass = "com.example.HelloJava",

    [string]$OutputDirectory = "./build/classes"
)
~~~

Có thể truyền parameter:

~~~powershell
pwsh -File ./scripts/build-java.ps1 -Release 21 -MainClass com.example.HelloJava
~~~

Environment variable phù hợp cho cấu hình do CI cung cấp:

~~~powershell
$env:JAVA_HOME
$env:CI
$env:BUILD_NUMBER
~~~

Không lưu password, access token hoặc private key trực tiếp trong script hoặc log. Dùng secret store của CI và chỉ đọc secret tại thời điểm cần thiết.

## 13. Bảo mật khi viết PowerShell script

Một số nguyên tắc quan trọng:

- Không dùng Invoke-Expression để chạy chuỗi có dữ liệu bên ngoài.
- Không ghép command từ tên file, branch hoặc input chưa kiểm tra.
- Dùng argument array và call operator.
- Dùng LiteralPath khi path có thể chứa wildcard.
- Kiểm tra input trước khi truyền vào java, jar hoặc jcmd.
- Không in token hoặc credential ra log.
- Không chạy script tải từ nguồn không tin cậy.
- Không tắt Execution Policy trên toàn máy chỉ để chạy một script CI.
- Pin JDK và build tool version trong môi trường release.
- Dùng chữ ký hoặc provenance để xác thực artifact khi yêu cầu bảo mật cao.

Execution Policy kiểm soát cách PowerShell nạp script trên Windows. Nó không phải ranh giới bảo mật hoàn chỉnh. Trên Linux/macOS, cơ chế này không có cùng ý nghĩa như Windows. Với CI, dùng policy của runner và quản lý script source trong repository.

## 14. Lỗi thường gặp

### Không tìm thấy java hoặc javac

Kiểm tra JAVA_HOME có trỏ tới JDK root không, executable có nằm trong bin không và PATH có chứa đúng JDK không. Dùng Get-Command để biết shell đang chọn file nào.

### Chạy nhầm phiên bản Java

Có thể java và javac đến từ các JDK khác nhau. Resolve cả hai bằng cùng JAVA_HOME và in version trong CI log.

### Path có dấu cách làm lệnh thất bại

Đừng xây command thành một chuỗi dài. Dùng array argument và splatting. Kiểm tra cả đường dẫn project, JDK và output.

### Script báo thành công dù Java trả exit code khác 0

Lưu LASTEXITCODE ngay sau lệnh java hoặc javac và kiểm tra giá trị số. ErrorActionPreference không thay thế bước này trong Windows PowerShell 5.1.

### Script chạy ở máy cá nhân nhưng fail trong CI

CI có thể dùng working directory, PATH, JAVA_HOME, user permission và shell version khác. Dùng PSScriptRoot để định vị file, log phiên bản và kiểm tra tool path.

### Script không chạy do Execution Policy

Kiểm tra Get-ExecutionPolicy -List. Dùng policy phù hợp với tổ chức và runner. Trên CI Windows có thể đặt scope Process khi được phép; không tự thay đổi policy toàn máy.

### Script chạy trên Windows nhưng fail trên Linux

Kiểm tra path separator, chữ hoa/thường, file permission, tên executable có phần mở rộng và dependency ngoài JDK. Dùng pwsh thay vì powershell.exe trên Linux/macOS.

### Java source có ký tự lạ sau khi script tạo file

Kiểm tra encoding và BOM. Windows PowerShell 5.1 ghi UTF-8 có BOM khi dùng Set-Content -Encoding UTF8; nếu cần UTF-8 không BOM, dùng UTF8Encoding(false).

### Native stderr bị coi là lỗi PowerShell

Khác biệt stream giữa Windows PowerShell và PowerShell 7 có thể làm pipeline xử lý stderr khác nhau. Nếu cần thu thập stderr, redirect có chủ đích và vẫn kiểm tra LASTEXITCODE riêng.

## 15. Quy trình viết và kiểm thử script

1. Xác định shell tối thiểu cần hỗ trợ: Windows PowerShell 5.1 hay PowerShell 7.
2. Chọn cách gọi native tool và kiểm tra phiên bản JDK.
3. Dùng PSScriptRoot và Join-Path để tạo đường dẫn.
4. Dùng parameter thay cho hard-code cấu hình.
5. Dùng StrictMode và ErrorActionPreference cho lỗi PowerShell.
6. Gọi javac/java bằng call operator và argument array.
7. Kiểm tra LASTEXITCODE ngay sau mỗi native command.
8. Kiểm thử với project path có dấu cách.
9. Kiểm thử cả success path và failure path.
10. Chạy trên từng OS/shell được hỗ trợ.
11. Kiểm tra encoding, newline và output log.
12. Đưa script vào CI và bảo đảm exit code được job truyền đúng.

Khi thay đổi script dùng chung, hãy kiểm thử trên đúng các phiên bản PowerShell mà repository cam kết hỗ trợ. Một script chạy được trên PowerShell 7 không tự động chứng minh nó tương thích Windows PowerShell 5.1.

## 16. Lệnh PowerShell cần nhớ

~~~powershell
# PowerShell version
$PSVersionTable

# Locate Java tools
Get-Command java -CommandType Application
Get-Command javac -CommandType Application
Get-Command jar -CommandType Application

# Inspect JDK environment
$env:JAVA_HOME
$env:PATH

# Build paths portably
$source = Join-Path $PSScriptRoot "src"
$output = Join-Path $PSScriptRoot "build/classes"

# Find Java source files
Get-ChildItem -LiteralPath $source -Filter "*.java" -File -Recurse

# Run javac and check its exit code
& $javac "--release" "17" "-d" $output $sourceFile
$compileExitCode = $LASTEXITCODE

# Run an application
& $java "-cp" $output "com.example.HelloJava"
$runExitCode = $LASTEXITCODE

# Run a JAR
& $java "-jar" $jarPath
$jarExitCode = $LASTEXITCODE

# Check a file or directory
Test-Path -LiteralPath $output -PathType Container

# Create UTF-8 without BOM
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($filePath, $content, $utf8NoBom)

# Run scripts with the intended shell
powershell.exe -NoProfile -File .\scripts\build-java.ps1
pwsh -NoProfile -File ./scripts/build-java.ps1
~~~

PowerShell giúp tự động hóa Java tooling bằng cách kết hợp object pipeline, function, path API và khả năng gọi native executable. Để script chạy ổn định trên nhiều môi trường, hãy chọn rõ PowerShell version, tìm JDK từ JAVA_HOME/PATH, tạo path bằng Join-Path, truyền argument bằng array và kiểm tra LASTEXITCODE sau từng lệnh Java. Sau đó kiểm thử cả trường hợp thành công lẫn thất bại trên từng runner mà dự án hỗ trợ.

## Tài liệu tham khảo

- [PowerShell Documentation](https://learn.microsoft.com/powershell/)
- [PowerShell 7 overview](https://learn.microsoft.com/powershell/scripting/overview)
- [about Automatic Variables](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_automatic_variables)
- [about Preference Variables](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_preference_variables)
- [about Quoting Rules](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_quoting_rules)
- [about Operators](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_operators)
- [Java Compiler javac — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [Java Launcher — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
