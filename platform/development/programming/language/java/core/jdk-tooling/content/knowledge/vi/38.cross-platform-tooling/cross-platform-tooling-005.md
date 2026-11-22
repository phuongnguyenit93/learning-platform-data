# Script shell đa nền tảng cho dự án Java

Shell script tự động hóa các công việc quanh ứng dụng Java: kiểm tra JDK, biên dịch source, chạy Maven, tạo artifact, chạy test và đóng gói release. Một script chạy tốt trên máy developer chưa chắc chạy được trên Windows, Linux và macOS vì mỗi môi trường có shell, cách viết đường dẫn, quy tắc quoting và cách truyền argument khác nhau.

Để xây dựng tooling đa nền tảng, trước tiên phải xác định interpreter mục tiêu. Bash/POSIX shell phù hợp với Linux, macOS, Git Bash hoặc WSL; PowerShell 7 có thể chạy trên Windows, Linux và macOS; Windows PowerShell 5.1 chỉ có trên Windows. Một script Bash không tự chạy được bằng PowerShell, và ngược lại. Dự án thường cung cấp cặp script theo từng shell hoặc dùng Maven Wrapper để giảm số lệnh phụ thuộc hệ điều hành.

Bài này trình bày cách tổ chức script, xử lý path/argument/environment, kiểm tra exit code, chạy Java/Maven an toàn, đồng bộ line ending và kiểm thử trên CI. Ví dụ cuối dùng một chương trình Java 17+ cùng hai launcher Bash và PowerShell có hành vi giống nhau.

## 1. Shell script dùng để làm gì trong Java tooling?

Shell script là chương trình văn bản được một command interpreter đọc và thực thi. Trong dự án Java, script thường đảm nhiệm:

- Kiểm tra Java/JDK/Maven trước khi build.
- Chọn JDK qua JAVA_HOME hoặc PATH.
- Gọi javac, java, javadoc hoặc jcmd.
- Chạy Maven Wrapper với tham số chuẩn.
- Chuẩn bị thư mục output và cấu hình environment.
- Chạy test, tạo package hoặc tạo image.
- Trả đúng exit code để CI nhận biết build thành công/thất bại.
- Thu thập log và dọn tài nguyên tạm.

Script nên điều phối các công cụ hiện có. Logic nghiệp vụ phức tạp, xử lý dữ liệu hoặc quy tắc build quan trọng thường nên đặt trong Java, Maven plugin hoặc một công cụ chuyên dụng để dễ kiểm thử và ít phụ thuộc shell.

## 2. Chọn shell và xác định phạm vi hỗ trợ

Các shell phổ biến có cú pháp và runtime khác nhau:

| Shell | Nền tảng thường gặp | Ghi chú |
|---|---|---|
| POSIX sh | Linux, Unix, macOS | Cú pháp cơ bản, phù hợp script cần tương thích rộng |
| Bash | Linux, macOS, Git Bash, WSL | Có arrays, [[ ]], pipefail và nhiều tiện ích riêng |
| PowerShell 7 (pwsh) | Windows, Linux, macOS | Shell đa nền tảng, có object pipeline và .NET APIs |
| Windows PowerShell 5.1 | Windows | Bản cũ đi kèm Windows; không có trên Linux/macOS |
| cmd.exe / batch | Windows | Cú pháp riêng, thường dùng cho file .bat/.cmd |

Đừng viết một file rồi kỳ vọng mọi shell hiểu cùng cú pháp. Hãy chọn một trong các chiến lược:

1. Cung cấp script riêng: run.sh và run.ps1, cùng gọi một Java/Maven task.
2. Dùng PowerShell 7 nếu tổ chức đã chuẩn hóa pwsh trên mọi runner.
3. Dùng Maven Wrapper để chuẩn hóa build command, còn script chỉ làm phần kiểm tra môi trường.
4. Đưa logic đa nền tảng quan trọng vào Java hoặc Maven plugin thay vì shell.

Ghi rõ phiên bản shell tối thiểu trong README và CI. Nếu dùng Bash array, pipefail hoặc BASH_SOURCE, script phải yêu cầu Bash chứ không thể khai báo là POSIX sh.

## 3. Shebang và cách khởi chạy script

Shebang là dòng đầu file trên hệ Unix-like, chỉ định interpreter:

~~~bash
#!/usr/bin/env bash
~~~

Dòng này tìm bash qua PATH. Cách gọi thường dùng:

~~~bash
chmod +x scripts/run.sh
./scripts/run.sh
~~~

Hoặc gọi interpreter trực tiếp:

~~~bash
bash scripts/run.sh
~~~

Nếu script dùng cú pháp POSIX sh, có thể khai báo:

~~~sh
#!/bin/sh
~~~

Với PowerShell, cách gọi rõ ràng là:

~~~powershell
pwsh -File ./scripts/run.ps1
~~~

Trên Windows PowerShell 5.1:

~~~powershell
powershell.exe -NoProfile -File .\scripts\run.ps1
~~~

PowerShell 7 có thể chạy trên nhiều OS; Windows PowerShell 5.1 chỉ chạy trên Windows. Shebang PowerShell trên Unix-like chỉ có ý nghĩa khi máy có pwsh và file có quyền thực thi. Trên Windows, dùng pwsh -File hoặc powershell.exe -File.

Git Bash và WSL cung cấp môi trường Unix-like trên Windows. Chúng không phải PowerShell và cũng không phải Windows CMD. Cần kiểm tra đường dẫn JAVA_HOME theo định dạng mà môi trường Bash đang hiểu.

## 4. POSIX sh và Bash không hoàn toàn giống nhau

Nếu script cần chạy trên nhiều Unix shell, hãy giữ cú pháp POSIX:

- Dùng [ ... ] thay cho [[ ... ]].
- Tránh Bash arrays và process substitution.
- Không dùng pipefail nếu cần tương thích với mọi /bin/sh.
- Không dùng BASH_SOURCE; POSIX shell chỉ có $0.
- Tránh phụ thuộc GNU-only flags nếu script còn chạy trên macOS/BSD.
- Dùng command -v để tìm executable.
- Luôn quote biến chứa path và argument.

Nếu đã chọn Bash, khai báo rõ shebang và có thể bật:

~~~bash
set -Eeuo pipefail
~~~

Trong đó -e dừng khi một số command thất bại, -u báo lỗi khi đọc biến chưa đặt và pipefail làm pipeline thất bại nếu một command ở giữa thất bại. Bash có các ngoại lệ cho set -e trong điều kiện, vòng lặp và pipeline; với bước quan trọng, vẫn nên kiểm tra exit code một cách tường minh.

Không đặt shebang /bin/sh rồi dùng cú pháp Bash. Trên một số hệ thống /bin/sh là dash hoặc shell POSIX khác và sẽ báo syntax error.

## 5. Quoting và truyền argument có dấu cách

Lỗi phổ biến nhất của shell script là làm vỡ một path hoặc argument thành nhiều phần vì thiếu quote.

Bash:

~~~bash
java -cp "$CLASSPATH" demo.App "$@"
~~~

"$@" truyền từng argument ban đầu thành một argument riêng, kể cả khi có dấu cách. Không dùng $@ không quote hoặc "$*" nếu muốn bảo toàn ranh giới argument.

PowerShell:

~~~powershell
& $javaExe -cp $classPath demo.App @AppArgs
~~~

@AppArgs splat mảng argument thành các đối số riêng. Dùng quote cho path có dấu cách và kiểm tra cách PowerShell truyền argument tới native executable.

Ví dụ lệnh gọi:

~~~powershell
./scripts/run.ps1 "hello world" "two words"
~~~

Ứng dụng phải nhận đúng hai argument:

~~~text
arg[0]=<hello world>
arg[1]=<two words>
~~~

Quy tắc quote của Bash và PowerShell khác nhau. Bash dùng single quote để giữ literal và double quote vẫn cho phép variable/command expansion. PowerShell dùng single quote cho chuỗi literal và double quote cho expandable string. Backslash không phải escape character chung của PowerShell; PowerShell dùng backtick cho escaping trong string.

PowerShell 7.3 thay đổi cách truyền argument tới native command so với Windows PowerShell 5.1. Nếu script phụ thuộc argument có quote lồng nhau hoặc chuỗi rỗng, hãy test trên đúng phiên bản PowerShell hỗ trợ. Tránh tự ghép một command string rồi gọi eval hoặc Invoke-Expression.

## 6. Đường dẫn: working directory khác script directory

Working directory là thư mục hiện tại khi người dùng chạy lệnh. Script directory là nơi file script nằm. Hai thư mục này có thể khác nhau.

Không giả định người dùng luôn chạy script từ thư mục gốc repository. Hãy xác định root dựa trên vị trí script.

Bash:

~~~bash
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
~~~

PowerShell:

~~~powershell
$scriptDir = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptDir
~~~

Dùng Join-Path, Split-Path và Resolve-Path trong PowerShell; dùng dirname, cd và pwd -P trong Bash. Tránh tự nối path bằng cách ghép dấu gạch chéo nếu có thể dùng API path của shell.

Các lưu ý:

- Quote mọi path có thể chứa khoảng trắng.
- Không hardcode username hoặc home directory.
- Không giả định path Windows có thể dùng trực tiếp trong Bash.
- Không dựa vào path tương đối với terminal hiện tại.
- Kiểm tra file/directory tồn tại trước khi chạy.
- Dùng đường dẫn tuyệt đối cho file đầu vào quan trọng sau khi xác định project root.

Git Bash thường biểu diễn ổ Windows theo dạng /c/Users/...; một JAVA_HOME dạng C:\Program Files\... có thể cần chuyển đổi bằng cygpath -u trước khi dùng trong Bash. PowerShell dùng trực tiếp path Windows.

## 7. Environment variable và cấu hình JDK

Các công cụ Java thường dùng environment variable:

| Biến | Mục đích |
|---|---|
| JAVA_HOME | Root của JDK/JRE được chọn theo quy ước môi trường |
| PATH | Danh sách thư mục shell tìm executable |
| MAVEN_HOME | Có thể chỉ Maven installation nếu môi trường sử dụng |
| MAVEN_OPTS | JVM options cho Maven process |
| JDK_JAVA_OPTIONS | JVM options được launcher Java thêm vào |
| JAVA_TOOL_OPTIONS | JVM options được VM nhận khi khởi tạo |

JAVA_HOME nên trỏ tới thư mục gốc của JDK, không phải bin hoặc java.exe. Nếu cần biên dịch, phải có javac trong thư mục bin.

Bash đặt environment variable cho child process bằng export:

~~~bash
export JAVA_HOME="/opt/jdk-17"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

PowerShell:

~~~powershell
$env:JAVA_HOME = 'C:\Java\jdk-17'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
~~~

Thay đổi environment trong script thường chỉ ảnh hưởng process hiện tại và child process, không thay đổi vĩnh viễn cấu hình user/system. Không ghi đè PATH toàn bộ; hãy thêm thư mục cần thiết vào đầu hoặc cuối theo chính sách dự án.

Không tin rằng JAVA_HOME đã đúng chỉ vì biến tồn tại. Hãy kiểm tra java và javac thực sự nằm trong đó, rồi in version khi cần chẩn đoán.

## 8. Chọn java/javac và kiểm tra JDK

Bash trên Linux/macOS có thể chọn JDK từ JAVA_HOME hoặc PATH:

~~~bash
if [[ -n "${JAVA_HOME:-}" ]]; then
  JAVA="$JAVA_HOME/bin/java"
  JAVAC="$JAVA_HOME/bin/javac"
else
  JAVA="$(command -v java || true)"
  JAVAC="$(command -v javac || true)"
fi

if [[ -z "$JAVA" || ! -x "$JAVA" ]]; then
  printf '%s\n' "Cannot find executable java" >&2
  exit 2
fi

if [[ -z "$JAVAC" || ! -x "$JAVAC" ]]; then
  printf '%s\n' "Cannot find executable javac; install a JDK" >&2
  exit 2
fi
~~~

PowerShell có thể tìm executable trong PATH bằng Get-Command:

~~~powershell
$javaCommand = Get-Command java -CommandType Application -ErrorAction Stop
$javaExe = $javaCommand.Source
~~~

Nếu JAVA_HOME được đặt, ghép path tới bin/java hoặc bin/java.exe theo OS và kiểm tra bằng Test-Path -LiteralPath.

Trong Git Bash trên Windows, executable thường có đuôi .exe và JAVA_HOME có thể ở dạng Windows path. Script Bash cần chọn java.exe/javac.exe và chuyển JAVA_HOME sang POSIX path bằng cygpath -u. Ví dụ đầy đủ ở phần 15 minh họa cả hai điểm này.

Không chỉ dựa vào output java -version nếu script cần javac. Một runtime-only installation có thể chạy Java nhưng không biên dịch được. Lệnh javac -version xác nhận compiler tồn tại.

## 9. Gọi Maven và Maven Wrapper

Maven Wrapper cung cấp hai launcher trong repository:

- mvnw cho Unix-like shell.
- mvnw.cmd cho Windows CMD/PowerShell.

Trong Bash:

~~~bash
"$PROJECT_ROOT/mvnw" -f "$PROJECT_ROOT/pom.xml" clean verify
~~~

Trong PowerShell:

~~~powershell
& (Join-Path $projectRoot 'mvnw.cmd') -f (Join-Path $projectRoot 'pom.xml') clean verify
$buildExit = $LASTEXITCODE
if ($buildExit -ne 0) {
    exit $buildExit
}
~~~

Wrapper giúp pin Maven distribution qua .mvn/wrapper/maven-wrapper.properties. Nó không tự cài JDK và không thay thế việc kiểm soát JAVA_HOME hoặc Maven Toolchains.

Trên Unix-like, cần giữ executable bit của mvnw. Khi clone trên Windows, Git có thể không giữ đầy đủ quyền executable trong mọi cấu hình; gọi bash ./mvnw nếu cần hoặc kiểm tra mode trong Git.

## 10. Exit code và xử lý lỗi

Quy ước phổ biến của command-line tool:

- Exit code 0: thành công.
- Exit code khác 0: thất bại hoặc trạng thái đặc biệt.
- Bash lưu exit status của lệnh gần nhất trong $?.
- PowerShell dùng $LASTEXITCODE cho native executable và $? cho trạng thái success của command gần nhất.

Luôn đọc exit code ngay sau lệnh native. Nếu chạy thêm một command trước khi lưu, $LASTEXITCODE có thể đã đổi.

Bash:

~~~bash
javac --release 17 -d "$BUILD_DIR" "$SOURCE_FILE"
compile_status=$?
if (( compile_status != 0 )); then
  exit "$compile_status"
fi
~~~

PowerShell:

~~~powershell
& $javacExe --release 17 -d $buildDir $sourceFile
$compileExit = $LASTEXITCODE
if ($compileExit -ne 0) {
    exit $compileExit
}
~~~

Trong PowerShell, $ErrorActionPreference = 'Stop' giúp biến nhiều non-terminating cmdlet errors thành terminating errors. Nó không thay thế việc kiểm tra $LASTEXITCODE sau khi gọi java.exe, javac.exe hoặc mvnw.cmd.

Đừng dùng echo/Write-Host để báo lỗi rồi vẫn trả exit code 0. CI dựa vào exit code, không dựa vào câu chữ trong log.

## 11. Pipeline, trap và cleanup

Một pipeline có thể che mất lỗi của command đứng trước nếu chỉ lấy status cuối.

Bash có thể bật pipefail:

~~~bash
set -o pipefail
some_command | tee build.log
~~~

PowerShell pipeline truyền object giữa cmdlet; khi gọi native executable qua pipeline, cần kiểm tra exit code và xử lý stderr/stdout theo cách phù hợp.

Dọn file tạm và process cần có cơ chế cleanup:

Bash:

~~~bash
TEMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf -- "$TEMP_DIR"
}
trap cleanup EXIT
~~~

PowerShell:

~~~powershell
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempDir | Out-Null
try {
    # Run the build steps.
}
finally {
    if (Test-Path -LiteralPath $tempDir) {
        Remove-Item -LiteralPath $tempDir -Recurse -Force
    }
}
~~~

Chỉ xóa thư mục tạm do chính script tạo và lưu path vào biến đã kiểm soát. Không chạy rm -rf hoặc Remove-Item trên path rỗng, root path hay biến chưa xác thực.

## 12. Encoding, line ending và executable bit

Script đa nền tảng thường hỏng do line ending hoặc encoding không đúng.

- Bash script nên dùng UTF-8 và LF.
- PowerShell 7 đọc UTF-8 tốt; Windows PowerShell 5.1 có khác biệt về default encoding, đặc biệt với file không phải ASCII.
- Tránh smart quote hoặc ký tự Unicode lạ trong script.
- Nếu cần tương thích Windows PowerShell 5.1, kiểm tra encoding file và ưu tiên UTF-8 có BOM khi có ký tự ngoài ASCII.
- Git có thể chuẩn hóa line ending theo .gitattributes.
- Bash script cần executable bit nếu chạy trực tiếp bằng ./script.sh.

Ví dụ .gitattributes:

~~~text
*.sh text eol=lf
*.ps1 text eol=crlf
*.bat text eol=crlf
~~~

Có thể dùng LF cho PowerShell 7 trên mọi nền tảng; nếu cần Windows PowerShell 5.1, thống nhất encoding và line ending với team rồi kiểm thử trên đúng host.

Nếu Bash báo /usr/bin/env: bash\r: No such file or directory, file có thể đang dùng CRLF và ký tự carriage return bị đưa vào shebang. Chuyển file .sh về LF.

## 13. Bảo mật khi truyền input vào shell

Shell thực hiện expansion, quote removal và cách diễn giải metacharacter trước khi chạy command. Nếu nối input không tin cậy vào command string, dữ liệu có thể bị hiểu thành command hoặc option.

Nguyên tắc:

- Truyền arguments riêng, không ghép thành một command string.
- Quote biến trong Bash và dùng argument array/splat trong PowerShell.
- Không dùng eval hoặc Invoke-Expression với dữ liệu từ người dùng.
- Kiểm tra giá trị path trước khi xóa hoặc ghi file.
- Không in token/password hoặc environment variable nhạy cảm ra log.
- Không đưa secret vào command-line nếu process list có thể đọc được.
- Dùng allowlist cho tên profile, task hoặc environment.
- Không tải và chạy script từ URL không được xác minh.

Ví dụ Bash an toàn hơn:

~~~bash
java -cp "$CLASSPATH" demo.App "$USER_INPUT"
~~~

Ví dụ PowerShell:

~~~powershell
& $javaExe -cp $classPath demo.App $UserInput
~~~

Nếu input phải được truyền thành nhiều argument, dùng mảng và giữ ranh giới argument. Không escape bằng cách thay dấu cách hoặc dấu nháy một cách thủ công rồi ghép thành chuỗi lệnh.

## 14. Ví dụ Java dùng chung cho hai shell

Tạo file src/main/java/demo/ArgsDemo.java:

~~~java
package demo;

public final class ArgsDemo {
    private ArgsDemo() {
    }

    public static void main(String[] args) {
        System.out.println("Arguments: " + args.length);
        for (int i = 0; i < args.length; i++) {
            System.out.println("arg[" + i + "]=<" + args[i] + ">");
        }
    }
}
~~~

Chương trình in số argument và từng giá trị trong dấu ngoặc nhọn để dễ kiểm tra việc shell có giữ nguyên chuỗi chứa dấu cách hay không.

Chương trình không phụ thuộc shell. Cùng một class có thể được gọi từ Bash, PowerShell, CMD, Maven hoặc CI.

## 15. Ví dụ Bash launcher: scripts/run.sh

Tạo file scripts/run.sh trong repository:

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
SOURCE_FILE="$PROJECT_ROOT/src/main/java/demo/ArgsDemo.java"
BUILD_DIR="$PROJECT_ROOT/build/classes"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    JAVA_NAME=java.exe
    JAVAC_NAME=javac.exe
    if [[ -n "${JAVA_HOME:-}" ]] && command -v cygpath >/dev/null 2>&1; then
      JAVA_HOME="$(cygpath -u "$JAVA_HOME")"
    fi
    ;;
  *)
    JAVA_NAME=java
    JAVAC_NAME=javac
    ;;
esac

if [[ -n "${JAVA_HOME:-}" ]]; then
  JAVA="$JAVA_HOME/bin/$JAVA_NAME"
  JAVAC="$JAVA_HOME/bin/$JAVAC_NAME"
else
  JAVA="$(command -v java || true)"
  JAVAC="$(command -v javac || true)"
fi

if [[ -z "$JAVA" || ! -x "$JAVA" ]]; then
  printf '%s\n' "Cannot find java. Set JAVA_HOME or update PATH." >&2
  exit 2
fi

if [[ -z "$JAVAC" || ! -x "$JAVAC" ]]; then
  printf '%s\n' "Cannot find javac. Install a JDK and set JAVA_HOME." >&2
  exit 2
fi

if [[ ! -f "$SOURCE_FILE" ]]; then
  printf 'Source file not found: %s\n' "$SOURCE_FILE" >&2
  exit 2
fi

mkdir -p "$BUILD_DIR"
"$JAVAC" --release 17 -encoding UTF-8 -d "$BUILD_DIR" "$SOURCE_FILE"

exec "$JAVA" -cp "$BUILD_DIR" demo.ArgsDemo "$@"
~~~

Giải thích:

- BASH_SOURCE[0] lấy đường dẫn file script hiện tại.
- PROJECT_ROOT được tính từ thư mục scripts.
- Trên Git Bash, script chọn java.exe/javac.exe và chuyển JAVA_HOME dạng Windows path bằng cygpath -u.
- Trên Linux/macOS/WSL, script dùng java/javac không có đuôi .exe.
- JAVA_HOME được ưu tiên; nếu không có thì tìm java/javac trong PATH.
- Tất cả path đều được quote.
- javac dùng release 17 và UTF-8.
- exec thay shell process bằng Java process; exit code của Java trở thành exit code của script.
- "$@" giữ nguyên từng argument mà người gọi truyền vào.

Cấp quyền thực thi trên Linux/macOS/Git Bash:

~~~bash
chmod +x scripts/run.sh
~~~

Chạy:

~~~bash
./scripts/run.sh "hello world" "two words"
~~~

## 16. Ví dụ PowerShell launcher: scripts/run.ps1

Tạo file scripts/run.ps1:

~~~powershell
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $AppArgs
)

$ErrorActionPreference = 'Stop'

$scriptDir = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptDir
$sourceFile = Join-Path $projectRoot 'src/main/java/demo/ArgsDemo.java'
$buildDir = Join-Path $projectRoot 'build/classes'

if ($env:OS -eq 'Windows_NT') {
    $javaRelative = 'bin/java.exe'
    $javacRelative = 'bin/javac.exe'
}
else {
    $javaRelative = 'bin/java'
    $javacRelative = 'bin/javac'
}

if (-not [string]::IsNullOrWhiteSpace($env:JAVA_HOME)) {
    $javaExe = Join-Path $env:JAVA_HOME $javaRelative
    $javacExe = Join-Path $env:JAVA_HOME $javacRelative
}
else {
    $javaCommand = Get-Command java -CommandType Application -ErrorAction Stop
    $javacCommand = Get-Command javac -CommandType Application -ErrorAction Stop
    $javaExe = $javaCommand.Source
    $javacExe = $javacCommand.Source
}

if (-not (Test-Path -LiteralPath $javaExe -PathType Leaf)) {
    throw "Cannot find java executable: $javaExe"
}
if (-not (Test-Path -LiteralPath $javacExe -PathType Leaf)) {
    throw "Cannot find javac executable: $javacExe"
}
if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
    throw "Source file not found: $sourceFile"
}

New-Item -ItemType Directory -Path $buildDir -Force | Out-Null

& $javacExe --release 17 -encoding UTF-8 -d $buildDir $sourceFile
$compileExit = $LASTEXITCODE
if ($compileExit -ne 0) {
    exit $compileExit
}

& $javaExe -cp $buildDir demo.ArgsDemo @AppArgs
$runExit = $LASTEXITCODE
exit $runExit
~~~

Giải thích:

- PSScriptRoot xác định vị trí script, không phụ thuộc working directory.
- Join-Path xử lý path separator theo hệ điều hành.
- JAVA_HOME được dùng nếu có; nếu không, Get-Command tìm executable.
- Dấu & gọi executable từ một path đã resolve.
- @AppArgs truyền mảng argument riêng lẻ.
- $LASTEXITCODE được lưu ngay sau mỗi native executable.
- exit trả exit code của javac hoặc Java cho caller/CI.

Chạy trên Windows:

~~~powershell
powershell.exe -NoProfile -File .\scripts\run.ps1 "hello world" "two words"
~~~

Chạy trên PowerShell 7:

~~~powershell
pwsh -NoProfile -File ./scripts/run.ps1 "hello world" "two words"
~~~

Trên Linux/macOS, cài JDK và PowerShell 7 rồi dùng pwsh. Windows PowerShell 5.1 không phải interpreter cho Linux/macOS.

## 17. Output mong đợi và kiểm tra argument

Chạy Bash hoặc PowerShell launcher với hai argument hello world và two words.

Stdout của Java:

~~~text
Arguments: 2
arg[0]=<hello world>
arg[1]=<two words>
~~~

Nếu output hiển thị bốn argument thay vì hai, script đã làm vỡ argument khi expansion. Nếu Java nhận dấu quote như một phần giá trị, shell hoặc cách gọi native executable đang truyền quote sai.

Có thể kiểm tra exit code sau khi chạy:

Bash:

~~~bash
./scripts/run.sh "hello world"
printf 'exit=%s\n' "$?"
~~~

PowerShell:

~~~powershell
& ./scripts/run.ps1 "hello world"
$scriptExit = $LASTEXITCODE
Write-Output "exit=$scriptExit"
~~~

Khi launcher dùng exit, nên chạy nó như một process riêng để kiểm tra exit code từ shell gọi. Trong PowerShell, nếu script được gọi trực tiếp bằng &, cần phân biệt lỗi PowerShell exception với exit code của native process.

## 18. CI matrix và kiểm thử trên nhiều hệ điều hành

Một script đa nền tảng cần được chạy trên từng môi trường mục tiêu. Không thể chứng minh tính portable chỉ bằng việc đọc code trên Windows.

CI nên có matrix tối thiểu cho các OS thực sự được hỗ trợ:

| Runner | Shell kiểm tra |
|---|---|
| Ubuntu | Bash và PowerShell 7 nếu hỗ trợ |
| macOS | Bash mặc định của runner và PowerShell 7 nếu hỗ trợ |
| Windows | PowerShell 7/5.1 theo policy và Git Bash nếu dự án hỗ trợ |

Mỗi job nên:

1. Checkout source sạch.
2. Cài JDK version đã pin.
3. In java -version và javac -version.
4. Chạy shell syntax/lint check.
5. Chạy launcher từ một working directory khác project root.
6. Truyền argument có dấu cách và ký tự đặc biệt.
7. Kiểm tra stdout và exit code.
8. Chạy build/test thật của dự án.
9. Thu log khi thất bại.

Dùng ShellCheck để kiểm tra Bash và PSScriptAnalyzer để kiểm tra PowerShell. CI matrix giúp phát hiện khác biệt giữa shell version, path, encoding và native argument passing.

## 19. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| bad interpreter hoặc bash\r not found | Script Bash dùng CRLF | Chuyển .sh về LF |
| Permission denied khi chạy ./run.sh | Thiếu executable bit | chmod +x và commit file mode |
| java chạy được nhưng javac không tìm thấy | Chỉ cài runtime hoặc JAVA_HOME trỏ sai | Cài JDK đầy đủ và kiểm tra bin/javac |
| Path có dấu cách bị tách | Thiếu quote hoặc truyền argument sai | Quote path và dùng "$@" / @array |
| Script chỉ chạy từ project root | Dùng relative path theo terminal cwd | Tính project root từ script location |
| Maven dùng sai Java | JAVA_HOME/PATH hoặc toolchain không như mong đợi | In mvn -version và kiểm tra toolchain log |
| PowerShell báo command not found | Dùng sai executable path hoặc command type | Get-Command và kiểm tra Source/Path |
| CI luôn báo success dù javac lỗi | Không truyền exit code | Kiểm tra $LASTEXITCODE hoặc $? ngay sau lệnh |
| Script Bash lỗi trên macOS | Dùng GNU-only command/option | Dùng POSIX-compatible command hoặc cài dependency có pin version |
| Git Bash không đọc JAVA_HOME | JAVA_HOME dùng Windows path syntax | Dùng path POSIX hoặc chuyển bằng cygpath |
| PowerShell 5.1 và 7 truyền args khác nhau | Khác biệt native argument passing | Kiểm thử đúng version và giữ argument array |
| Script chạy được local nhưng fail CI | Shell/JDK/working directory/environment khác | Pin version, log environment và chạy CI matrix |

## 20. Best practices cho shell tooling

- Nêu rõ interpreter và version tối thiểu.
- Giữ Bash và PowerShell script ngắn, tập trung điều phối.
- Tính project root từ vị trí script.
- Quote path và truyền argument bằng array.
- Dùng JAVA_HOME có kiểm tra, không chỉ tin giá trị environment.
- Kiểm tra javac riêng nếu cần compile.
- Lưu exit code của native command ngay sau khi chạy.
- Không trộn cú pháp POSIX, Bash, PowerShell và CMD.
- Không hardcode path tuyệt đối hoặc username.
- Chuẩn hóa encoding và line ending.
- Pin Maven/JDK/plugin qua Wrapper, Toolchains và build config.
- Không dùng eval/Invoke-Expression với input không tin cậy.
- Dọn file tạm bằng trap hoặc try/finally.
- Chạy ShellCheck/PSScriptAnalyzer và CI matrix.
- Ghi output rõ ràng, gửi lỗi ra stderr và trả exit code khác 0 khi thất bại.

## 21. Checklist shell script đa nền tảng

- [ ] Đã xác định OS và shell cần hỗ trợ.
- [ ] Bash script có shebang đúng; PowerShell script có cách gọi rõ ràng.
- [ ] Không dùng cú pháp Bash trong script khai báo POSIX sh.
- [ ] Working directory không ảnh hưởng cách tìm project root.
- [ ] Path có dấu cách được quote đúng.
- [ ] Argument có dấu cách được bảo toàn bằng "$@" hoặc mảng.
- [ ] JAVA_HOME trỏ tới đúng JDK root.
- [ ] java và javac được kiểm tra độc lập.
- [ ] Maven Wrapper được gọi đúng theo OS.
- [ ] Exit code của native command được truyền về caller.
- [ ] Pipeline và cleanup được xử lý rõ ràng.
- [ ] Script không ghép input thành command string để eval.
- [ ] File .sh dùng LF và có executable bit khi cần.
- [ ] Encoding của .ps1 phù hợp với PowerShell version.
- [ ] Script được lint bằng ShellCheck/PSScriptAnalyzer.
- [ ] CI matrix chạy trên tất cả OS/shell đã công bố.
- [ ] Test có path chứa dấu cách và argument có ký tự đặc biệt.
- [ ] Build log ghi rõ JDK, Maven và shell version.

Shell script đa nền tảng cần tôn trọng khác biệt giữa interpreter, path, quoting, environment và exit code. Dùng script riêng cho Bash và PowerShell khi cần, giữ logic ứng dụng trong Java/Maven, và xác minh trên đúng OS/shell được hỗ trợ. Một launcher tốt luôn tìm đúng project root, giữ nguyên argument, kiểm tra JDK và trả chính xác kết quả của lệnh build.

## Tài liệu tham khảo

- GNU Bash Reference Manual — Quoting: https://www.gnu.org/software/bash/manual/html_node/Quoting.html
- GNU Bash Reference Manual — Shell Expansions: https://www.gnu.org/software/bash/manual/html_node/Shell-Expansions.html
- GNU Bash Reference Manual: https://www.gnu.org/software/bash/manual/bash.html
- Microsoft Learn — PowerShell about_Quoting_Rules: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules
- Microsoft Learn — PowerShell about_Parsing: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing
- Microsoft Learn — PowerShell about_Automatic_Variables: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_automatic_variables
- Microsoft Learn — PowerShell about_Environment_Variables: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_environment_variables
- Apache Maven — Maven Wrapper: https://maven.apache.org/tools/mavenwrapper.html
- Oracle Java SE 17 — The java Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
