# Wrapper script cho Windows, Linux và macOS

Một ứng dụng Spring Shell thường được đóng gói thành executable JAR của Spring Boot. Người dùng có thể chạy trực tiếp bằng **java -jar**, nhưng phải tự nhớ đường dẫn JAR, vị trí Java, các tùy chọn JVM và cấu hình môi trường. Wrapper script gom những chi tiết đó vào một lệnh ổn định như **spring-shell**, đồng thời chuyển nguyên các argument của người dùng tới ứng dụng.

Để phân phối cho Windows, Linux và macOS, có thể phát hành cùng một JAR với hai wrapper:

- Một shell script POSIX dùng chung cho Linux và macOS.
- Một batch script **.cmd** dùng trong Windows Command Prompt và có thể gọi từ PowerShell.

Wrapper chỉ khởi chạy tiến trình Java. Spring Shell vẫn quyết định command nào chạy, cách phân tích argument, chế độ interactive hay non-interactive và mã thoát cuối cùng. Vì vậy, wrapper cần giữ nguyên thứ tự argument, xử lý đường dẫn có khoảng trắng và trả lại exit code của Java.

## 1. Cấu trúc gói phân phối

Một gói cài đặt đơn giản có thể tổ chức như sau:

```text
spring-shell-cli/
├── bin/
│   ├── spring-shell
│   └── spring-shell.cmd
├── lib/
│   └── spring-shell-cli.jar
├── conf/
│   └── application.yml
├── README.md
└── LICENSES/
```

| Thành phần | Vai trò |
| --- | --- |
| **bin/spring-shell** | Wrapper cho Linux và macOS |
| **bin/spring-shell.cmd** | Wrapper cho Windows |
| **lib/spring-shell-cli.jar** | Executable JAR chứa ứng dụng và dependency |
| **conf/application.yml** | Cấu hình có thể thay đổi khi cài đặt |
| **README.md** | Hướng dẫn cài Java, cấu hình và sử dụng command |
| **LICENSES/** | Giấy phép của ứng dụng và dependency cần phân phối |

Hai wrapper dùng cùng một tên JAR để không phải thay đổi script theo từng bản phát hành. Khi build, hãy copy executable JAR vào đúng vị trí và đổi tên thành **spring-shell-cli.jar**, hoặc điều chỉnh hằng số JAR trong cả hai wrapper.

Không đặt đường dẫn JAR cố định theo thư mục build như **target/** hoặc **build/libs/** trong wrapper phát hành. Các thư mục đó thuộc workspace phát triển và có thể không tồn tại trên máy người dùng.

## 2. Đóng gói executable JAR

Wrapper cần một JAR có manifest và Spring Boot loader phù hợp để chạy bằng **java -jar**. Spring Boot Maven Plugin có thể đóng gói ứng dụng cùng dependency thành executable archive. Với Gradle, task **bootJar** tạo executable JAR.

### Maven

Nếu dự án dùng **spring-boot-starter-parent**, execution **repackage** thường đã được cấu hình sẵn. Chỉ cần khai báo plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Nếu không dùng Spring Boot parent hoặc plugin management tương đương, khai báo goal **repackage**:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Build:

```bash
mvn clean package
```

Sau khi build, kiểm tra executable JAR trong **target/**. Tên file thực tế phụ thuộc **artifactId**, **version** và cấu hình build.

### Gradle

Spring Boot Gradle Plugin cung cấp task **bootJar**:

```groovy
tasks.named('bootJar') {
    archiveFileName = 'spring-shell-cli.jar'
}
```

Build:

```bash
./gradlew clean bootJar
```

**build** hoặc **assemble** cũng kéo theo **bootJar** theo cấu hình mặc định của plugin. Sau khi build, lấy JAR trong **build/libs/**.

### Tạo thư mục phân phối

Ví dụ với Maven trên Linux/macOS:

```bash
mkdir -p dist/spring-shell-cli/bin
mkdir -p dist/spring-shell-cli/lib
mkdir -p dist/spring-shell-cli/conf
cp target/my-app-1.0.0.jar dist/spring-shell-cli/lib/spring-shell-cli.jar
cp packaging/spring-shell dist/spring-shell-cli/bin/
cp packaging/spring-shell.cmd dist/spring-shell-cli/bin/
```

Đường dẫn **packaging/** và tên JAR là ví dụ; thay chúng theo cấu trúc dự án. Trước khi nén, kiểm tra gói có đủ JAR, hai wrapper, cấu hình mẫu, README và giấy phép cần thiết.

## 3. Wrapper cho Linux và macOS

Linux và macOS đều có shell tương thích POSIX. Một file script dùng **#!/usr/bin/env sh** có thể chạy trên cả hai hệ điều hành nếu chỉ dùng lệnh và cú pháp portable.

Nội dung **bin/spring-shell**:

```sh
#!/usr/bin/env sh
set -e

# Thư mục bin chứa script; APP_HOME là thư mục gốc của gói phân phối.
SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
APP_HOME=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)
JAR="$APP_HOME/lib/spring-shell-cli.jar"

if [ ! -f "$JAR" ]; then
    echo "Không tìm thấy ứng dụng: $JAR" >&2
    exit 2
fi

# Ưu tiên JAVA_HOME; nếu không có thì tìm java trong PATH.
if [ -n "$JAVA_HOME" ]; then
    JAVA="$JAVA_HOME/bin/java"
else
    JAVA=$(command -v java 2>/dev/null || true)
fi

if [ -z "$JAVA" ] || [ ! -x "$JAVA" ]; then
    echo "Không tìm thấy Java. Hãy cài JDK/JRE tương thích hoặc đặt JAVA_HOME." >&2
    exit 127
fi

# exec thay thế tiến trình shell bằng JVM và giữ nguyên argument.
exec "$JAVA" -jar "$JAR" "$@"
```

**"$@"** chuyển từng argument thành một argument riêng, giữ nguyên khoảng trắng bên trong giá trị đã được người dùng đặt trong dấu nháy. Không thay bằng **$*** hoặc **$@** không có dấu nháy, vì shell có thể tách lại argument và làm mất dữ liệu.

**exec** thay thế tiến trình wrapper bằng tiến trình Java. Nhờ vậy, Ctrl+C và tín hiệu kết thúc được gửi tới JVM trực tiếp hơn, đồng thời exit code của Java trở thành exit code của wrapper.

### Cấp quyền thực thi

Sau khi giải nén gói trên Linux hoặc macOS, cấp quyền chạy:

```bash
chmod +x bin/spring-shell
```

Chạy ứng dụng:

```bash
./bin/spring-shell help
./bin/spring-shell project list --status FAILED
```

Nếu thư mục cài đặt có khoảng trắng, hãy đặt toàn bộ đường dẫn script trong dấu nháy:

```bash
"/opt/Development Tools/spring-shell-cli/bin/spring-shell" help
```

Wrapper xác định JAR dựa trên vị trí của chính script, không dựa vào thư mục hiện tại của người dùng. Script không tự **cd** sang thư mục cài đặt; vì vậy, các đường dẫn tương đối trong argument của command vẫn được tính từ thư mục mà người dùng đang đứng khi gọi wrapper. Đây thường là hành vi phù hợp với một CLI thao tác trên file.

## 4. Wrapper cho Windows bằng CMD

Windows có thể chạy ứng dụng bằng **java.exe** từ Command Prompt hoặc PowerShell. File **.cmd** là lựa chọn đơn giản vì không yêu cầu người dùng thay đổi execution policy của PowerShell.

Nội dung **bin/spring-shell.cmd**:

```bat
@echo off
setlocal

for %%I in ("%~dp0..") do set "APP_HOME=%%~fI"
set "JAR=%APP_HOME%\lib\spring-shell-cli.jar"

if not exist "%JAR%" (
    echo Khong tim thay ung dung: "%JAR%" 1>&2
    endlocal
    exit /b 2
)

if defined JAVA_HOME goto use_java_home

where java.exe >nul 2>&1
if errorlevel 1 goto no_java
set "JAVA_EXE=java.exe"
goto launch

:use_java_home
set "JAVA_EXE=%JAVA_HOME%\bin\java.exe"
if not exist "%JAVA_EXE%" goto no_java

:launch
"%JAVA_EXE%" -jar "%JAR%" %*
set "APP_EXIT=%ERRORLEVEL%"
endlocal & exit /b %APP_EXIT%

:no_java
echo Khong tim thay Java. Hay cai JDK/JRE tuong thich hoac kiem tra JAVA_HOME. 1>&2
endlocal & exit /b 9009
```

Các điểm cần chú ý:

- **%~dp0** là thư mục chứa file **.cmd**; **for %%I** chuẩn hóa đường dẫn thư mục gốc của gói.
- Đường dẫn JAR và Java được đặt trong dấu nháy để hỗ trợ thư mục như **C:\Program Files\...**.
- **%*** chuyển tiếp toàn bộ argument người dùng truyền cho wrapper.
- **%ERRORLEVEL%** lưu mã thoát của Java trước khi **endlocal** kết thúc phạm vi biến cục bộ.
- **exit /b** trả mã thoát về cửa sổ gọi script.

Nếu **JAVA_HOME** đã được đặt nhưng trỏ tới thư mục không có **bin\java.exe**, wrapper báo lỗi thay vì âm thầm chạy một Java khác từ **PATH**. Điều này giúp tránh khởi chạy nhầm runtime.

### Chạy từ Command Prompt

```bat
bin\spring-shell.cmd help
bin\spring-shell.cmd project list --status FAILED
```

### Chạy từ PowerShell

PowerShell có thể gọi trực tiếp file **.cmd** bằng call operator:

```powershell
& ".\bin\spring-shell.cmd" project list --status FAILED
$LASTEXITCODE
```

**$LASTEXITCODE** là mã thoát của chương trình native vừa chạy. Với argument chứa khoảng trắng, đặt giá trị trong dấu nháy kép:

```powershell
& ".\bin\spring-shell.cmd" user create --display-name "Ada Lovelace"
```

Khi chuyển argument qua CMD, hãy đặt trong dấu nháy các giá trị có khoảng trắng hoặc ký tự đặc biệt của shell như **&**, **|**, **(** và **)**.

## 5. Phân biệt JVM options và argument của Spring Shell

Java launcher có thứ tự cú pháp:

```text
java [JVM options] -jar application.jar [application arguments]
```

Vị trí của argument quyết định chương trình nhận nó như thế nào:

| Vị trí | Ví dụ | Mục đích |
| --- | --- | --- |
| Trước **-jar** | **-Xms256m -Xmx1g** | Tùy chọn JVM |
| Sau **-jar** và tên JAR | **project list --status FAILED** | Argument ứng dụng, được Spring Boot chuyển cho Spring Shell runner |
| Biến môi trường Java | **JDK_JAVA_OPTIONS** | Bổ sung JVM options mà không sửa wrapper |
| Biến môi trường Spring Boot | **SPRING_PROFILES_ACTIVE** | Chọn profile cấu hình ứng dụng |

Wrapper mẫu không phân tích hoặc sắp xếp lại argument. Nó chỉ đặt JVM options ở vị trí của Java launcher và chuyển toàn bộ argument còn lại sau JAR cho ứng dụng.

### Cấu hình JVM qua JDK_JAVA_OPTIONS

Java launcher hỗ trợ biến môi trường **JDK_JAVA_OPTIONS** để thêm JVM options vào lệnh chạy. Biến này hiểu các argument phân tách bằng khoảng trắng và cho phép dùng dấu nháy để giữ giá trị có khoảng trắng.

Linux/macOS:

```bash
JDK_JAVA_OPTIONS='-Xms256m -Xmx1g -Duser.timezone=UTC' \
    ./bin/spring-shell project list
```

Windows CMD:

```bat
set "JDK_JAVA_OPTIONS=-Xms256m -Xmx1g -Duser.timezone=UTC"
bin\spring-shell.cmd project list
```

PowerShell:

```powershell
$env:JDK_JAVA_OPTIONS = '-Xms256m -Xmx1g -Duser.timezone=UTC'
& ".\bin\spring-shell.cmd" project list
```

**JDK_JAVA_OPTIONS** được Java launcher đọc tự động; không đặt **-jar** hoặc tên JAR trong biến này. Hãy chỉ dùng biến này cho JVM options, còn command và option của Spring Shell phải được truyền sau tên JAR.

## 6. Cấu hình Spring Boot bên ngoài gói

Không nên đóng cứng thông tin môi trường như profile, endpoint hoặc đường dẫn dữ liệu vào wrapper. Dùng biến môi trường của Spring Boot hoặc file cấu hình đặt trong thư mục **conf/**.

Ví dụ trên Linux/macOS:

```bash
export SPRING_PROFILES_ACTIVE=production
export SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:/etc/spring-shell/
./bin/spring-shell project list
```

Ví dụ trên Windows CMD:

```bat
set "SPRING_PROFILES_ACTIVE=production"
set "SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:///C:/ProgramData/SpringShell/"
bin\spring-shell.cmd project list
```

**SPRING_CONFIG_ADDITIONAL_LOCATION** tương ứng với thuộc tính **spring.config.additional-location**; đường dẫn trong ví dụ là đường dẫn tuyệt đối của từng hệ điều hành. Thư mục cấu hình phải tồn tại nếu không dùng tiền tố **optional:**.

Trong layout mẫu, **conf/application.yml** nằm cạnh thư mục **bin/** và **lib/**. Spring Boot không tự động nạp thư mục **conf/** đó chỉ vì nó nằm cạnh JAR. Nếu muốn dùng file cấu hình đi cùng gói, hãy đặt **SPRING_CONFIG_ADDITIONAL_LOCATION** thành đường dẫn tuyệt đối tới thư mục này, ví dụ **optional:file:/opt/spring-shell-cli/conf/** trên Linux/macOS hoặc **optional:file:///C:/ProgramData/SpringShell/conf/** trên Windows. Wrapper cố ý giữ nguyên working directory của người gọi để các đường dẫn tương đối trong command không bị thay đổi.

Nếu cần cấu hình khác nhau cho từng người dùng hoặc máy chủ, giữ **application.yml** mặc định trong JAR và đặt cấu hình bổ sung bên ngoài gói. Không đưa mật khẩu, token hoặc khóa bí mật vào script; dùng cơ chế secret/configuration phù hợp với môi trường triển khai.

## 7. Chọn interactive, non-interactive và script runner

Wrapper chỉ chuyển argument. Runner nào nhận các argument đó là quyết định của Spring Shell và phụ thuộc phiên bản cùng cấu hình ứng dụng.

Với Spring Shell 3.3.x trở lên:

- **NonInteractiveShellRunner** được bật mặc định.
- **InteractiveShellRunner** cần bật bằng **spring.shell.interactive.enabled=true**.
- **ScriptShellRunner** cần bật bằng **spring.shell.script.enabled=true**.

Các phiên bản đến 3.2.x bật cả ba runner theo mặc định. Vì vậy, hãy kiểm tra đúng phiên bản Spring Shell của ứng dụng trước khi tạo gói phân phối.

Ví dụ cấu hình cho ứng dụng cần hỗ trợ cả ba chế độ trên Spring Shell 3.3.x/3.4.x:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: true
```

Khi đó, người dùng có thể sử dụng wrapper theo các cách:

```bash
# Mở phiên shell tương tác khi không truyền command.
./bin/spring-shell

# Chạy một command rồi kết thúc.
./bin/spring-shell project list --status FAILED

# Chạy danh sách command trong file script.
./bin/spring-shell @/opt/ops/project-maintenance.txt
```

**ScriptShellRunner** nhận argument bắt đầu bằng ký tự **@** và coi phần còn lại là đường dẫn script. Với đường dẫn có khoảng trắng, đặt toàn bộ argument trong dấu nháy:

```bash
./bin/spring-shell "@/opt/Operations Scripts/project-maintenance.txt"
```

Trên Windows:

```bat
bin\spring-shell.cmd "@C:\Operations Scripts\project-maintenance.txt"
```

File script chứa một command trên mỗi dòng, được chạy theo thứ tự. Ví dụ:

```text
project list
project show --id P101
project archive --id P101
```

Phân biệt **ScriptShellRunner** với command tích hợp **script --file ...**. Runner nhận argument **@file** ngay lúc khởi động; command **script** là một command shell có thể được gọi trong phiên tương tác hoặc qua non-interactive runner nếu command đó được bật.

## 8. Linux service và fully executable JAR

Spring Boot có thể thêm launch script vào đầu JAR để tạo fully executable archive. Trên Linux, kiểu JAR này có thể được gọi trực tiếp như một chương trình hoặc tích hợp với **init.d**. Gradle hỗ trợ **bootJar { launchScript() }**; Maven hỗ trợ cấu hình **<executable>true</executable>**.

Tuy nhiên, fully executable JAR được thiết kế để chạy trực tiếp bằng script nhúng. Spring Boot khuyến nghị chỉ dùng kiểu này khi muốn thực thi JAR trực tiếp; một số công cụ đóng gói hoặc giải nén không xử lý định dạng đó đúng cách. Với gói đa nền tảng ở bài này, wrapper gọi **java -jar**, vì vậy hãy dùng executable JAR thông thường và không thêm launch script vào cùng artifact.

Nếu muốn chạy CLI như một Linux service, có thể dùng systemd với JAR thông thường:

```ini
[Unit]
Description=Spring Shell CLI worker
After=network.target

[Service]
Type=exec
User=shellapp
Group=shellapp
WorkingDirectory=/opt/spring-shell-cli
ExecStart=/usr/lib/jvm/java-17/bin/java -jar /opt/spring-shell-cli/lib/spring-shell-cli.jar
SuccessExitStatus=143

[Install]
WantedBy=multi-user.target
```

Thay Java path, user, group và thư mục cài đặt theo máy chủ. Với service, systemd quản lý process và log theo cấu hình unit; wrapper dành cho người dùng terminal không thay thế cấu hình service.

Launch script mặc định của Spring Boot nhắm tới các Linux distribution phổ biến. Tài liệu Spring Boot ghi rõ macOS cần custom script nếu muốn dùng fully executable JAR theo cách đó. Gói wrapper POSIX riêng ở trên tránh phụ thuộc vào launch script nhúng và có thể dùng chung cho Linux/macOS.

## 9. Bảo toàn argument và đường dẫn

Lỗi thường gặp nhất của wrapper là làm biến dạng argument trước khi đưa cho Java:

| Cách viết | Vấn đề |
| --- | --- |
| POSIX: **java -jar app.jar $@** | Không quote; argument có khoảng trắng có thể bị tách |
| POSIX: **java -jar app.jar "$@"** | Giữ từng argument, cách dùng đúng |
| POSIX: **java -jar app.jar "$*"** | Gộp các argument thành một chuỗi |
| CMD: **java -jar app.jar %*** | Chuyển tiếp argument; người gọi cần quote giá trị có khoảng trắng |
| CMD: **java -jar app.jar "%*"** | Gộp toàn bộ argument thành một argument duy nhất |

Luôn kiểm thử các trường hợp:

- Tên file hoặc thư mục có khoảng trắng.
- Giá trị option có dấu tiếng Việt hoặc Unicode.
- Giá trị chứa dấu gạch ngang, dấu bằng hoặc ký tự đặc biệt.
- Người dùng gọi wrapper từ thư mục hiện tại khác thư mục cài đặt.
- Đường dẫn JAR hoặc Java nằm trong thư mục có khoảng trắng.

Không dùng **eval** để dựng lệnh Java từ chuỗi do người dùng nhập. Hãy chuyển argument bằng cơ chế quote/splatting của từng shell.

## 10. Giữ mã thoát của ứng dụng

Mã thoát giúp script hoặc CI xác định command thành công hay thất bại. Wrapper nên trả lại đúng exit code của Java:

- POSIX dùng **exec** để thay wrapper bằng JVM.
- CMD lưu **%ERRORLEVEL%** ngay sau khi Java kết thúc và trả lại bằng **exit /b**.
- PowerShell đọc **$LASTEXITCODE** sau khi gọi **.cmd**.

Không ghi đè exit code của Java bằng một lệnh phụ chạy sau đó. Ví dụ, nếu chạy **java**, rồi chạy **echo**, rồi mới đọc **%ERRORLEVEL%**, giá trị có thể không còn là mã thoát của Java. Hãy lưu ngay như trong wrapper mẫu.

Spring Shell command cần có quy ước kết quả rõ ràng. Nếu ứng dụng chỉ in thông báo lỗi nhưng vẫn trả exit status thành công, wrapper không thể tự suy ra lỗi từ văn bản. Hãy cấu hình hoặc triển khai cơ chế ánh xạ lỗi nghiệp vụ sang trạng thái kết thúc phù hợp, rồi kiểm thử bằng cách gọi wrapper trong script.

## 11. Kiểm thử wrapper trước khi phát hành

Kiểm thử ở cả ba hệ điều hành mục tiêu, không chỉ chạy script trên máy build:

| Kiểm tra | Linux | macOS | Windows |
| --- | --- | --- | --- |
| Java có trong **JAVA_HOME** | **JAVA_HOME/bin/java** | **JAVA_HOME/bin/java** | **JAVA_HOME\bin\java.exe** |
| Java được tìm từ **PATH** | **command -v java** | **command -v java** | **where java.exe** |
| Wrapper có quyền thực thi | **chmod +x** | **chmod +x** | Không áp dụng |
| JAR nằm đúng vị trí | Kiểm tra **lib/** | Kiểm tra **lib/** | Kiểm tra **lib\** |
| Argument có khoảng trắng | Quote trong shell | Quote trong shell | Quote trong CMD/PowerShell |
| Exit code | Kiểm tra **$?** | Kiểm tra **$?** | Kiểm tra **%ERRORLEVEL%** hoặc **$LASTEXITCODE** |

Các lệnh smoke test có thể gồm:

```bash
./bin/spring-shell version
./bin/spring-shell help
./bin/spring-shell project list
```

Kiểm tra thêm:

1. Gói chạy được khi được giải nén sang thư mục có khoảng trắng.
2. Wrapper báo lỗi rõ khi thiếu JAR.
3. Wrapper báo lỗi rõ khi không tìm thấy Java.
4. **JAVA_HOME** được ưu tiên hơn Java trong **PATH**.
5. Profile và external config được nạp đúng.
6. Chế độ interactive mở prompt khi được bật.
7. Command non-interactive thực thi xong và kết thúc process.
8. Script **@file** chạy các command theo thứ tự.
9. Mã thoát được truyền về terminal gọi wrapper.
10. Ctrl+C kết thúc ứng dụng theo cơ chế shutdown của JVM.

Với Windows, lưu file **.cmd** bằng encoding tương thích với CMD và dùng line ending CRLF. Với shell script, dùng LF và giữ shebang ở dòng đầu tiên. Không kiểm thử wrapper chỉ bằng cách gọi thẳng **java -jar**, vì như vậy bỏ qua toàn bộ phần tìm Java, tìm JAR và chuyển tiếp argument.

## 12. Tạo archive và kiểm tra nội dung phát hành

Sau khi chuẩn bị thư mục phân phối, có thể tạo ZIP dùng chung cho Windows và macOS, Linux:

```bash
cd dist
zip -r spring-shell-cli-1.0.0.zip spring-shell-cli
```

Hoặc tạo tar.gz cho Linux/macOS:

```bash
tar -czf spring-shell-cli-1.0.0.tar.gz spring-shell-cli
```

Trước khi công bố:

- Ghi rõ phiên bản Spring Shell, Spring Boot và Java runtime tối thiểu được hỗ trợ.
- Ghi rõ cách đặt **JAVA_HOME** và cấu hình **PATH**.
- Nêu các chế độ interactive, non-interactive và script runner được bật.
- Ghi ví dụ command và cách truyền option có khoảng trắng.
- Đưa license/notice của dependency vào gói nếu giấy phép yêu cầu.
- Tạo checksum SHA-256 để người nhận xác minh file tải xuống.
- Thử giải nén và chạy từ một thư mục cài đặt sạch, không có Maven/Gradle.

Nếu muốn người dùng không cần cài Java riêng, cần đóng gói runtime hoặc tạo installer/native image bằng công cụ phù hợp. Wrapper mẫu ở đây giả định máy người dùng đã có Java runtime tương thích.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| **Unable to access jarfile** | JAR không ở vị trí wrapper dự kiến hoặc tên file không khớp | Kiểm tra **lib/spring-shell-cli.jar** và APP_HOME |
| **java** không được nhận diện | Chưa cài Java hoặc PATH chưa có **bin** | Đặt **JAVA_HOME** hoặc cập nhật PATH |
| Java chạy sai phiên bản | JAVA_HOME trỏ tới runtime cũ hơn yêu cầu | Kiểm tra **java -version** và đặt lại JAVA_HOME |
| Argument bị tách | Wrapper không quote argument | Dùng **"$@"** trên POSIX và quote giá trị khi gọi CMD |
| Chạy command nhưng lại vào prompt | Runner interactive/non-interactive không đúng cấu hình | Kiểm tra các thuộc tính **spring.shell.*.enabled** |
| Không chạy được file script **@...** | Script runner chưa bật hoặc đường dẫn file sai | Bật **spring.shell.script.enabled** và dùng đường dẫn hợp lệ |
| Không mở được wrapper trên Linux/macOS | Thiếu quyền execute hoặc sai line ending/shebang | Chạy **chmod +x**, dùng LF và kiểm tra dòng đầu |
| PowerShell không đọc được exit code | Đọc sai biến sau khi gọi script | Dùng **$LASTEXITCODE** ngay sau wrapper |
| Cấu hình production không được nạp | External location sai hoặc biến môi trường chưa được đặt | Kiểm tra **SPRING_CONFIG_ADDITIONAL_LOCATION** |
| JAR không chạy qua wrapper | Đã thêm launch script nhúng vào artifact nhưng vẫn gọi **java -jar** | Dùng JAR thường cho wrapper đa nền tảng |

## 14. Checklist tạo wrapper đa nền tảng

- Đóng gói ứng dụng thành executable JAR bằng Spring Boot Maven Plugin hoặc Gradle Plugin.
- Dùng một tên JAR ổn định trong thư mục **lib/**.
- Đặt wrapper POSIX trong **bin/** và cấp quyền execute.
- Đặt wrapper **.cmd** cho Windows và chuyển tiếp **%***.
- Tìm Java qua **JAVA_HOME** trước, sau đó mới tìm trong **PATH**.
- Quote mọi đường dẫn có thể chứa khoảng trắng.
- Dùng **"$@"** để giữ nguyên từng argument trên Linux/macOS.
- Không đổi thư mục làm việc của người dùng nếu command cần xử lý đường dẫn tương đối.
- Dùng **JDK_JAVA_OPTIONS** cho JVM options.
- Dùng biến môi trường Spring Boot cho profile và external config.
- Kiểm tra runner interactive, non-interactive và script theo đúng minor version Spring Shell.
- Giữ nguyên exit code của Java.
- Không nhầm fully executable JAR có launch script với JAR thường dùng qua **java -jar**.
- Kiểm thử trên Windows, Linux và macOS thật hoặc môi trường CI tương ứng.
- Phát hành README, license, checksum và yêu cầu Java runtime cùng archive.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Execution và Shell Runners](https://docs.spring.io/spring-shell/reference/3.3/execution.html)
- [Spring Shell 3.4 — ScriptShellRunner API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/ScriptShellRunner.html)
- [Spring Shell 3.4 — Script command API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Script.html)
- [Spring Boot 3.4 — Installing Spring Boot Applications](https://docs.spring.io/spring-boot/3.4/how-to/deployment/installing.html)
- [Spring Boot — Packaging Executable Archives with Maven](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Spring Boot — Packaging Executable Archives with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
- [Java Launcher — Command Syntax and JDK_JAVA_OPTIONS](https://docs.oracle.com/en/java/javase/18/docs/specs/man/java.html)
