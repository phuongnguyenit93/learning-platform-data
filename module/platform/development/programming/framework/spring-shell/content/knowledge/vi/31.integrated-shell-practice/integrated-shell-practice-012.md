# Đóng gói và chạy trên terminal thật cùng môi trường CI

Một ứng dụng Spring Shell chỉ thực sự sẵn sàng phân phối khi người dùng có thể build artifact, chạy nó bằng terminal của hệ điều hành, gọi command từ script và đưa cùng artifact vào pipeline CI. Chạy được trong IDE chưa chứng minh các tình huống này hoạt động: IDE có thể cung cấp working directory, environment, classpath và console khác với máy của người dùng.

Bài thực hành này đóng gói một ứng dụng Spring Shell thành executable JAR, tổ chức thư mục phân phối có launcher cho Windows và Linux/macOS, kiểm tra tương tác trên terminal thật và chạy command theo chế độ non-interactive trong CI. Phần cuối mở rộng sang OCI image bằng Spring Boot Buildpacks.

Một điểm cần nhớ với Spring Shell 4.x: interactive mode được bật mặc định, kể cả khi process nhận command arguments. Khi chạy command từ script hoặc CI, phải chọn non-interactive mode một cách rõ ràng bằng thuộc tính spring.shell.interactive.enabled=false. Nếu bỏ qua bước này, process có thể mở prompt và chờ vô thời hạn trong pipeline.

## Mục tiêu thực hành

Sau bài học, bạn có thể:

- Cấu hình Spring Boot Maven Plugin hoặc Gradle Plugin để tạo executable JAR.
- Phân biệt executable JAR với JAR Java thông thường.
- Chạy cùng một artifact bằng java -jar trên máy phát triển và máy triển khai.
- Tổ chức thư mục phân phối gồm launcher, JAR, cấu hình và tài liệu.
- Viết launcher Bash, CMD và PowerShell có chuyển tiếp arguments và exit code.
- Kiểm tra command trong terminal thật có TTY và JLine.
- Phân biệt interactive mode với non-interactive mode trong Spring Shell 4.x.
- Chạy một command hoặc script nhiều command trong CI.
- Kiểm tra encoding, Unicode, đường dẫn, output, exit code và working directory.
- Tạo OCI image bằng Spring Boot Buildpacks khi cần phân phối bằng container.
- Xây dựng smoke test sau khi đóng gói để phát hiện lỗi thiếu dependency hoặc sai launcher.
- Lập checklist phát hành cho nhiều hệ điều hành.

## 1. Kết quả cuối cùng

Giả sử ứng dụng có các command:

~~~text
help
backend status
report export --format csv --output <file>
customer show --id <id>
~~~

Sau bài thực hành, người dùng có thể:

**Chạy shell tương tác:**

~~~bash
./bin/support
~~~

**Chạy một command trong CI:**

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false ./bin/support backend status
~~~

**Chạy một file script gồm nhiều command:**

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
java -jar lib/support-cli.jar @scripts/smoke.shell
~~~

**Chạy trong container:**

~~~bash
docker run --rm -it example/support-cli:1.0
~~~

Thư mục phân phối mẫu:

~~~text
support-cli/
  bin/
    support
    support.cmd
    support.ps1
  lib/
    support-cli.jar
  conf/
    application.yml
  scripts/
    smoke.shell
  README.txt
~~~

JAR là artifact chính. Launcher chỉ chuẩn hóa cách tìm JAR, thiết lập một số biến môi trường và chuyển tiếp arguments. Cấu hình theo môi trường được đặt bên ngoài JAR để có thể triển khai cùng artifact tới nhiều môi trường.

## 2. Chuẩn bị phiên bản và môi trường build

Trước khi đóng gói, xác định:

- Phiên bản Java dùng để compile và chạy.
- Phiên bản Spring Boot.
- Phiên bản Spring Shell.
- Build tool và phiên bản wrapper.
- Hệ điều hành, kiến trúc CPU và runtime được hỗ trợ.

Các module Spring Shell phải dùng cùng một dòng phiên bản. Không trộn spring-shell-core, spring-shell-jline và spring-shell-test từ những phiên bản khác nhau.

Kiểm tra Java:

~~~bash
java -version
~~~

Kiểm tra Maven Wrapper:

~~~bash
./mvnw -version
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd -version
~~~

Nếu dùng Gradle Wrapper:

~~~bash
./gradlew --version
~~~

Wrapper giúp máy phát triển và CI sử dụng cùng phiên bản build tool. Java runtime của máy triển khai vẫn phải tương thích với bytecode và các dependency đã đóng gói.

Không giả định JDK trên máy build cũng chính là JRE/JDK trên máy chạy. Ghi rõ phiên bản Java tối thiểu trong tài liệu phân phối và kiểm tra phiên bản đó trong pipeline.

## 3. Tạo executable JAR bằng Maven

Spring Boot Maven Plugin tạo executable archive chứa application classes, resources và dependencies cần thiết để chạy bằng java -jar.

Nếu dự án sử dụng spring-boot-starter-parent, thêm plugin vào pom.xml:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Parent POM của Spring Boot đã cấu hình execution repackage trong lifecycle. Khi chạy package, plugin đóng gói lại JAR thông thường thành executable JAR.

Nếu dự án không sử dụng spring-boot-starter-parent, cần khai báo execution repackage:

~~~xml
<build>
    <plugins>
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
    </plugins>
</build>
~~~

Giữ version plugin đồng bộ với phiên bản Spring Boot được quản lý trong dự án. Nếu dùng Spring Boot dependency management, tránh khai báo một version plugin độc lập khác dòng.

Build:

~~~bash
./mvnw clean package
~~~

Artifact thường nằm trong:

~~~text
target/support-cli-1.0.0.jar
~~~

Tên thật phụ thuộc artifactId và version trong pom.xml.

Chạy artifact:

~~~bash
java -jar target/support-cli-1.0.0.jar
~~~

Spring Boot Plugin quản lý các entry Main-Class và Start-Class trong manifest. Không cần tự ghép tất cả dependency vào classpath khi chạy JAR đã được repackaged.

### 3.1. Vì sao JAR thông thường có thể không chạy được?

JAR được tạo bởi Maven Jar Plugin có thể chỉ chứa class và resource của dự án. Nếu dependency không được đóng gói cùng, lệnh:

~~~bash
java -jar target/support-cli-1.0.0.jar
~~~

có thể thất bại với lỗi thiếu class hoặc không tìm thấy main class phù hợp.

Executable JAR của Spring Boot có cấu trúc riêng, thường chứa:

~~~text
BOOT-INF/
  classes/
  lib/
META-INF/
  MANIFEST.MF
org/springframework/boot/loader/
~~~

BOOT-INF/classes chứa class và resource của ứng dụng; BOOT-INF/lib chứa dependency. Spring Boot Loader đọc cấu trúc này khi khởi chạy.

Có thể kiểm tra nội dung:

~~~bash
jar tf target/support-cli-1.0.0.jar
~~~

Không dùng JAR executable của ứng dụng như một dependency thông thường trong dự án khác. Nếu cần thư viện dùng chung, tạo module library riêng hoặc giữ plain JAR làm artifact thư viện.

## 4. Tạo executable JAR bằng Gradle

Với Gradle, Spring Boot Plugin cung cấp task bootJar:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.7'
}
~~~

Version trong ví dụ phải được thay bằng phiên bản Spring Boot do dự án quản lý. Nếu dùng plugin dependency management hoặc version catalog, giữ quy tắc quản lý phiên bản hiện tại của dự án.

Build:

~~~bash
./gradlew clean bootJar
~~~

Hoặc chạy build nếu task assemble/build đã phụ thuộc bootJar:

~~~bash
./gradlew clean build
~~~

Artifact nằm trong:

~~~text
build/libs/
~~~

Chạy:

~~~bash
java -jar build/libs/support-cli-1.0.0.jar
~~~

Gradle có thể tạo cả plain JAR và executable JAR. Kiểm tra classifier và tên file trước khi copy artifact vào thư mục phân phối; đừng vô tình phát hành plain JAR thay cho bootJar.

## 5. Smoke test artifact ngay sau khi build

Không dừng ở việc build thành công. Hãy chạy artifact đã đóng gói để kiểm tra manifest, dependency runtime và Spring context.

Ví dụ dùng biến môi trường để chọn non-interactive mode:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
java -jar target/support-cli-1.0.0.jar help
~~~

Với PowerShell:

~~~powershell
$env:SPRING_SHELL_INTERACTIVE_ENABLED = 'false'
java -jar .\target\support-cli-1.0.0.jar help
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
~~~

Smoke test tối thiểu nên xác nhận:

- Process kết thúc trong thời gian hữu hạn.
- Command help chạy được.
- Exit code thành công là 0.
- Không có lỗi thiếu class hoặc dependency.
- Output có command dự kiến.
- Không yêu cầu nhập dữ liệu từ terminal.

Không dùng lệnh chỉ khởi tạo Spring context làm bằng chứng cho toàn bộ command hoạt động. Một smoke test nên gọi ít nhất một command thực tế hoặc command help.

## 6. Interactive mode và non-interactive mode trong Spring Shell 4.x

Spring Shell 4.x yêu cầu ứng dụng chọn chế độ chạy ngay từ lúc khởi động.

| Chế độ | Runner | Cách sử dụng |
|---|---|---|
| Interactive | JLineShellRunner hoặc SystemShellRunner | Người dùng mở shell và nhập nhiều command |
| Non-interactive | NonInteractiveShellRunner | Process nhận command hoặc script rồi kết thúc |

Interactive mode được bật mặc định. Việc truyền command arguments không tự động chuyển ứng dụng sang non-interactive mode.

Để chạy command từ arguments:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
java -jar support-cli.jar backend status
~~~

Tên biến môi trường được ánh xạ từ property spring.shell.interactive.enabled theo relaxed binding:

~~~text
SPRING_SHELL_INTERACTIVE_ENABLED=false
~~~

Có thể đặt trong application.yml:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
~~~

Tuy nhiên, không nên mặc định tắt interactive mode trong một artifact dành cho người dùng mở terminal. Hãy chọn cấu hình theo mục đích triển khai hoặc cung cấp launcher riêng cho batch.

### 6.1. JLineShellRunner và SystemShellRunner

Khi sử dụng Spring Shell starter, interactive mode dùng JLineShellRunner. Nếu JLine không có trên classpath, Spring Shell dùng SystemShellRunner dựa trên Java Console.

JLine cung cấp trải nghiệm terminal phong phú hơn, ví dụ:

- Lịch sử command.
- Điều hướng dòng bằng phím mũi tên.
- Tab completion.
- Xử lý terminal và prompt.
- Hỗ trợ tương tác mật khẩu qua input reader tương ứng.

SystemShellRunner dùng java.io.Console của JDK và phù hợp với shell tương tác cơ bản.

Không tự tạo reader mới từ System.in trong command nếu shell đã quản lý input. Hai thành phần cùng đọc một stream có thể làm mất dòng hoặc khiến prompt hoạt động sai.

### 6.2. Chọn chế độ cho từng cách triển khai

| Tình huống | Cách chạy |
|---|---|
| Người dùng mở shell trên máy cá nhân | Interactive mặc định |
| Người dùng chạy một command từ script | Non-interactive |
| CI build và smoke test | Non-interactive |
| Scheduler chạy báo cáo | Non-interactive |
| Container mở terminal cho người vận hành | Interactive và cấp TTY |
| Container chạy một command rồi thoát | Non-interactive |

Nếu một command gọi readInput() hoặc readPassword(), command đó cần phiên tương tác có input phù hợp. Không thiết kế batch job để chờ prompt trên runner CI.

## 7. Chạy nhiều command từ script file

NonInteractiveShellRunner hỗ trợ một command hoặc một script file. Đường dẫn script được truyền với tiền tố @.

Ví dụ file scripts/smoke.shell:

~~~text
help
backend status
customer show --id 1001
~~~

Chạy:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
java -jar support-cli.jar @/absolute/path/scripts/smoke.shell
~~~

Dùng đường dẫn tuyệt đối trong CI để tránh phụ thuộc working directory. Script nên chứa command có thể chạy mà không cần prompt.

Spring Shell cũng có built-in command script để đọc file trong interactive shell:

~~~text
script --file /absolute/path/scripts/setup.shell
~~~

File script dùng một command trên mỗi dòng; có thể thêm comment bắt đầu bằng //.

Phân biệt hai cách:

| Cách | Mục đích |
|---|---|
| @file khi chạy NonInteractiveShellRunner | Chạy file command rồi kết thúc process |
| script --file trong interactive shell | Yêu cầu shell hiện tại thực thi một file command |

Không nhầm script file của Spring Shell với script Bash, PowerShell hoặc CMD. Một file .shell chứa command Spring Shell, còn file .sh/.ps1/.cmd là script của hệ điều hành dùng để khởi chạy ứng dụng.

## 8. Tổ chức thư mục phân phối

Không phát hành riêng JAR nếu người dùng cần launcher, file cấu hình mẫu hoặc script vận hành. Một gói ZIP có cấu trúc rõ ràng giúp người dùng cài đặt và cập nhật dễ hơn.

Ví dụ:

~~~text
support-cli-1.0.0/
  bin/
    support
    support.cmd
    support.ps1
  lib/
    support-cli.jar
  conf/
    application.yml
  scripts/
    smoke.shell
  README.txt
  LICENSE.txt
~~~

Vai trò:

- bin: launcher theo hệ điều hành.
- lib: executable JAR.
- conf: cấu hình ngoài có thể thay đổi theo môi trường.
- scripts: các script Spring Shell mẫu hoặc tác vụ vận hành.
- README: yêu cầu Java, cách chạy, cấu hình và ví dụ.
- LICENSE: giấy phép phân phối nếu dự án cần.

Launcher nên xác định vị trí JAR dựa trên thư mục của chính launcher. Không giả định người dùng luôn chạy lệnh từ thư mục cài đặt.

Không đặt password, token hoặc private key trong file cấu hình được đóng gói. Cung cấp secret qua secret manager hoặc cơ chế bảo vệ của môi trường triển khai.

## 9. Viết launcher Bash cho Linux và macOS

Tạo bin/support:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
APP_HOME=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)

exec java -jar "$APP_HOME/lib/support-cli.jar" "$@"
~~~

Ý nghĩa:

- Xác định thư mục chứa script.
- Tìm thư mục gốc của gói phân phối.
- Xây dựng đường dẫn tuyệt đối đến JAR.
- Truyền toàn bộ arguments bằng "$@" để giữ nguyên ranh giới từng argument.
- Dùng exec để process Java thay thế process shell, nhờ đó exit code và signal được chuyển tiếp tự nhiên hơn.

Cấp quyền thực thi:

~~~bash
chmod +x bin/support
~~~

Nếu launcher được lưu trong Git, kiểm tra executable bit:

~~~bash
git ls-files --stage bin/support
~~~

Mode mong đợi là 100755. Nếu file được checkout thành 100644, người dùng có thể không chạy trực tiếp được dù nội dung shebang đúng.

Chạy tương tác:

~~~bash
./bin/support
~~~

Chạy command trong CI:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
./bin/support backend status
~~~

Xuất báo cáo:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
./bin/support report export --format csv --output "$PWD/out/report.csv"
~~~

Launcher không đổi working directory. Vì vậy, đường dẫn tương đối mà command nhận được vẫn được phân giải theo thư mục mà người dùng gọi script. Đây thường là hành vi mong đợi cho CLI. Nếu sản phẩm muốn đường dẫn tương đối luôn tính từ APP_HOME, hãy quy định rõ và kiểm thử hành vi đó trước khi thay đổi working directory.

## 10. Viết launcher CMD cho Windows

Tạo bin/support.cmd:

~~~bat
@echo off
setlocal

set "APP_HOME=%~dp0.."
set "SPRING_SHELL_INTERACTIVE_ENABLED=false"

java -jar "%APP_HOME%\lib\support-cli.jar" %*
exit /b %ERRORLEVEL%
~~~

%~dp0 là thư mục chứa file batch. Dấu nháy quanh đường dẫn JAR bảo vệ đường dẫn có khoảng trắng.

%* chuyển tiếp các đối số mà người dùng đã truyền vào launcher. Exit /b trả lại exit code của Java process cho caller.

Ví dụ:

~~~bat
bin\support.cmd backend status
~~~

Vì launcher này đặt SPRING_SHELL_INTERACTIVE_ENABLED=false, nó dành cho command và script batch. Nếu cần mở shell tương tác, dùng một launcher interactive riêng không đặt biến này hoặc chạy JAR trực tiếp.

Trong script CMD gọi launcher, kiểm tra ERRORLEVEL ngay sau khi process kết thúc:

~~~bat
call bin\support.cmd backend status
if errorlevel 1 exit /b %ERRORLEVEL%
~~~

Không chạy thêm lệnh có thể ghi đè ERRORLEVEL trước khi kiểm tra.

## 11. Viết launcher PowerShell

Tạo bin/support.ps1:

~~~powershell
$appHome = Split-Path -Parent $PSScriptRoot
$jarPath = Join-Path $appHome 'lib\support-cli.jar'

$env:SPRING_SHELL_INTERACTIVE_ENABLED = 'false'

& java -jar $jarPath @args
$exitCode = $LASTEXITCODE
exit $exitCode
~~~

PowerShell splatting với @args chuyển từng argument vào Java process. Không ghép arguments thành một chuỗi command line vì việc quoting có thể sai khi giá trị chứa dấu cách hoặc Unicode.

Chạy:

~~~powershell
.\bin\support.ps1 backend status
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
~~~

Nếu tổ chức yêu cầu ký script hoặc áp dụng Execution Policy cụ thể, tuân thủ chính sách đó. Không yêu cầu người dùng tắt bảo vệ script chỉ để launcher hoạt động.

## 12. Kiểm tra trên terminal thật có TTY

Một terminal thật có thể cung cấp TTY, console hoặc pseudo-terminal. Khi chạy trong IDE, CI hoặc qua pipe, ứng dụng có thể nhận input/output theo cách khác.

Mở terminal của hệ điều hành và chạy:

~~~bash
java -jar support-cli.jar
~~~

Hoặc chạy launcher:

~~~bash
./bin/support
~~~

Kiểm tra:

1. Shell hiển thị prompt đúng.
2. Có thể nhập command và nhận kết quả.
3. Phím mũi tên hoạt động nếu dùng JLine.
4. History hoạt động theo cấu hình.
5. Tab completion gợi ý command hoặc giá trị.
6. Dấu tiếng Việt và Unicode hiển thị đúng.
7. Dòng dài và terminal hẹp không làm output khó đọc.
8. Ctrl+C dừng thao tác theo hành vi đã định.
9. EOF hoặc Ctrl+D thoát theo hành vi phù hợp.
10. Terminal trở lại trạng thái bình thường sau khi shell kết thúc.

Nếu dùng password prompt, xác nhận password không bị echo ra màn hình trong terminal hỗ trợ cơ chế này. Không kết luận hành vi password từ test chạy bằng pipe trong CI.

### 12.1. JLine và System Console

Với Spring Shell starter, JLine runner được sử dụng khi JLine có trên classpath. Nếu không có JLine, SystemShellRunner sử dụng Java Console.

Khi chạy trong terminal:

- JLine cung cấp line editing, history và completion.
- Java Console cung cấp khả năng đọc dòng và password theo API của JDK.
- Tính năng cụ thể còn phụ thuộc terminal emulator và hệ điều hành.

Nếu command hoạt động trong JLine nhưng thất bại khi chạy qua IDE hoặc service, kiểm tra ứng dụng có nhận được TTY/Console hay không. Không tự động coi stdin pipe là terminal.

### 12.2. Kiểm tra Unicode và terminal width

Thử tên và dữ liệu có dấu:

~~~text
customer show --name "Nguyễn Thị Ánh"
~~~

Kiểm tra:

- UTF-8 được dùng cho file cấu hình và file output.
- Dấu tiếng Việt không bị thay bằng ký tự lỗi.
- Bảng không vỡ cột khi terminal hẹp.
- Ký tự CJK hoặc emoji không làm lệch bố cục ngoài dự kiến.
- Màu ANSI không gây nhiễu khi output được redirect vào file.

Đối với file output, quy định encoding độc lập với encoding của terminal. Không giả định console encoding và file encoding luôn giống nhau.

## 13. Chạy non-interactive trong CI

CI thường không có terminal tương tác. Spring Shell 4.x vẫn bật interactive mode mặc định, kể cả khi command được truyền qua process arguments. Vì vậy, pipeline phải thiết lập:

~~~text
SPRING_SHELL_INTERACTIVE_ENABLED=false
~~~

Ví dụ trên Linux:

~~~bash
export SPRING_SHELL_INTERACTIVE_ENABLED=false
java -jar target/support-cli.jar help
~~~

Hoặc đặt biến ngay trên một lệnh:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
java -jar target/support-cli.jar backend status
~~~

Trên PowerShell:

~~~powershell
$env:SPRING_SHELL_INTERACTIVE_ENABLED = 'false'
java -jar .\target\support-cli.jar backend status
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
~~~

Không dùng lệnh cần readInput() hoặc readPassword() trong CI nếu không có cơ chế cấp input được thiết kế cho automation. Tác vụ CI nên nhận đủ option/argument và secret từ nguồn được bảo vệ.

### 13.1. Pipeline build và smoke test

Một pipeline cơ bản:

~~~yaml
steps:
  - name: Checkout
    run: checkout source

  - name: Set up Java
    run: install supported JDK

  - name: Build and test
    run: ./mvnw -B clean verify

  - name: Smoke test packaged CLI
    run: SPRING_SHELL_INTERACTIVE_ENABLED=false java -jar target/support-cli.jar help

  - name: Upload distribution
    run: publish target/support-cli-1.0.0.zip
~~~

Đây là cấu trúc minh họa, không phải cú pháp của một CI vendor cụ thể. Thay các bước checkout, setup Java và upload bằng action/task tương ứng của hệ thống CI đang dùng.

Build và smoke test cần chạy trên artifact đã đóng gói. Test chỉ chạy từ classpath của Maven hoặc Gradle có thể bỏ sót lỗi xảy ra khi JAR được tạo và chạy độc lập.

### 13.2. Kiểm tra script nhiều command

File scripts/ci-smoke.shell:

~~~text
help
backend status
~~~

Chạy:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
java -jar target/support-cli.jar @scripts/ci-smoke.shell
~~~

Dùng file script để kiểm tra trình tự nhiều command. Nếu một command thất bại, hãy xác minh cách phiên bản Spring Shell đang dùng truyền kết quả lỗi và kết thúc script; không suy đoán chỉ từ việc process cuối cùng có exit code 0.

Với các bước CI quan trọng, có thể gọi từng command thành process riêng để pipeline kiểm soát rõ bước nào thất bại và lưu diagnostic tương ứng.

## 14. Kiểm thử launcher như người dùng cuối

Không chỉ gọi JAR trực tiếp. Hãy gọi đúng launcher được đưa vào ZIP:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
./dist/support-cli/bin/support backend status
~~~

Trên Windows:

~~~powershell
.\dist\support-cli\bin\support.cmd backend status
~~~

Kiểm tra các hợp đồng:

| Hạng mục | Cách xác minh |
|---|---|
| Tìm JAR | Chạy launcher từ thư mục khác |
| Arguments | Truyền option và giá trị có dấu cách |
| Working directory | Dùng đường dẫn output tương đối |
| Environment | Đặt profile và biến cấu hình |
| Exit code | Gọi command thành công và command thất bại |
| Encoding | Truyền đường dẫn Unicode và đọc file output |
| Permission | Chạy launcher POSIX sau khi giải nén |
| Cấu hình ngoài | Đặt file cấu hình ở vị trí đã công bố |

Một test quan trọng là giải nén ZIP vào đường dẫn có dấu cách, sau đó chạy launcher từ một thư mục làm việc khác. Test này phát hiện lỗi đường dẫn tương đối và quoting mà test trong source tree có thể bỏ qua.

## 15. Tạo OCI image bằng Spring Boot Buildpacks

Nếu hệ thống triển khai dùng container, có thể tạo OCI image từ ứng dụng bằng Spring Boot Buildpacks. Cách này không yêu cầu tự viết Dockerfile cho trường hợp đóng gói Java thông thường.

Với Maven:

~~~bash
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.imageName=example/support-cli:1.0.0
~~~

Build image cần Docker daemon hoặc môi trường container tương thích để buildpack thực hiện công việc.

Chạy command non-interactive:

~~~bash
docker run --rm \
  -e SPRING_SHELL_INTERACTIVE_ENABLED=false \
  example/support-cli:1.0.0 \
  help
~~~

Mở shell tương tác:

~~~bash
docker run --rm -it example/support-cli:1.0.0
~~~

Hai cờ container có ý nghĩa khác nhau:

- -i giữ stdin mở.
- -t cấp pseudo-terminal.

Khi người dùng cần nhập lệnh, cấp cả hai bằng -it. Trong CI, thường không cấp TTY và đặt non-interactive mode.

Buildpacks tạo image theo cấu hình builder và run image. Spring Boot Buildpacks mặc định cấu hình process chạy dưới user không phải root vì lý do bảo mật. Nếu CLI ghi file, bảo đảm volume mount và thư mục đích có quyền ghi cho user của container.

### 15.1. Đưa cấu hình vào container

Không bake secret vào image. Truyền cấu hình bằng environment variable hoặc mount file cấu hình/secret khi chạy container.

Ví dụ:

~~~bash
docker run --rm \
  -e SPRING_SHELL_INTERACTIVE_ENABLED=false \
  -e SPRING_PROFILES_ACTIVE=production \
  -e SUPPORT_BACKEND_BASEURL=https://api.example.internal \
  example/support-cli:1.0.0 \
  backend status
~~~

Nếu ứng dụng cần xuất file, mount một thư mục writable và dùng đường dẫn bên trong container. Kiểm tra quyền sở hữu thư mục trước khi chạy.

### 15.2. Khi nào nên dùng executable JAR hoặc OCI image?

| Tiêu chí | Executable JAR | OCI image |
|---|---|---|
| Yêu cầu | Java runtime | Container runtime |
| Phân phối | ZIP hoặc package manager | Registry |
| Cấu hình | Environment/file ngoài | Environment/volume/secret mount |
| Cập nhật | Thay JAR hoặc ZIP | Build và push image mới |
| Cô lập runtime | Phụ thuộc máy chạy | Runtime được đóng gói trong image |
| Tương tác terminal | Chạy trực tiếp trong terminal | Cần cấp TTY cho container |

Với công cụ CLI nội bộ nhỏ, executable JAR cùng launcher có thể đơn giản hơn. Với nền tảng đã chuẩn hóa container, OCI image giúp thống nhất runtime và cách triển khai.

## 16. Quản lý cấu hình và secret khi phân phối

File application.yml trong JAR nên chứa cấu hình mặc định không nhạy cảm. Cấu hình triển khai được cung cấp từ bên ngoài.

Đặt file application-prod.yml trong thư mục cấu hình bên ngoài, ví dụ /etc/support-cli/. Thuộc tính spring.config.additional-location được xử lý trước khi Spring Boot nạp Config Data, vì vậy hãy truyền nó qua environment variable hoặc JVM system property, không đặt nó trong application.yml:

~~~bash
SPRING_CONFIG_ADDITIONALLOCATION=optional:file:/etc/support-cli/ \
SPRING_PROFILES_ACTIVE=prod \
SPRING_SHELL_INTERACTIVE_ENABLED=false \
./bin/support backend status
~~~

Nếu file đó là bắt buộc trong production, bỏ tiền tố optional: để ứng dụng thất bại sớm khi file không tồn tại. Có thể cấu hình đường dẫn tuyệt đối tương ứng trong launcher hoặc deployment manifest; đừng giả định đường dẫn tương đối luôn tính từ thư mục chứa JAR.

Với secret:

- Dùng secret manager hoặc secret store của nền tảng.
- Nếu dùng environment variable, bảo đảm CI không in giá trị ra log.
- Nếu dùng file secret, giới hạn quyền đọc và không đưa file vào ZIP công khai.
- Không đưa token vào command line vì process list hoặc log có thể lưu lại.
- Không ghi secret vào output diagnostics.

Không nên dùng optional cho file cấu hình bắt buộc trong production. Nếu file chứa endpoint hoặc thông tin cần thiết để command hoạt động đúng, hãy để ứng dụng thất bại sớm khi thiếu cấu hình thay vì chạy với giá trị mặc định không phù hợp.

## 17. Kiểm tra artifact và tính toàn vẹn

Sau khi build ZIP hoặc image:

- Kiểm tra đúng JAR đã được copy.
- Kiểm tra file launcher có mặt.
- Kiểm tra permission của launcher POSIX.
- Kiểm tra cấu hình mẫu không chứa secret.
- Kiểm tra README ghi đúng lệnh chạy.
- Kiểm tra artifact có thể chạy sau khi giải nén sang thư mục mới.
- Tạo checksum để người nhận xác minh file tải xuống.

Linux/macOS:

~~~bash
sha256sum support-cli-1.0.0.zip
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\support-cli-1.0.0.zip -Algorithm SHA256
~~~

Ghi checksum vào release notes hoặc metadata phát hành. Người nhận có thể tính lại hash sau khi tải xuống để xác nhận file không bị thay đổi trong quá trình truyền.

## 18. Ma trận xác minh terminal và CI

Một sản phẩm hỗ trợ nhiều hệ điều hành cần test launcher và runtime trên từng nền tảng đã công bố:

| Hạng mục | Windows | Linux | macOS |
|---|---|---|---|
| Launcher | CMD/PowerShell | Bash/POSIX shell | Bash/zsh |
| Executable JAR | java -jar | java -jar | java -jar |
| Interactive terminal | Windows Terminal/PowerShell | Terminal emulator | Terminal/iTerm |
| Batch mode | Non-interactive | Non-interactive | Non-interactive |
| Exit code | ERRORLEVEL/LASTEXITCODE | $? | $? |
| Unicode path | Có dấu và khoảng trắng | Có dấu và khoảng trắng | Có dấu và khoảng trắng |
| Line ending | CRLF cho batch | LF | LF |
| Permission | Execution policy/file association | Git mode/chmod | Git mode/chmod |
| CI | Windows runner | Linux runner | macOS runner |

Nên có hai nhóm kiểm tra:

1. **Terminal smoke test:** chạy thủ công hoặc trong môi trường có TTY để kiểm tra prompt, history, completion, Unicode, Ctrl+C và password input.
2. **CI contract test:** chạy non-interactive để kiểm tra command, exit code, stdout/stderr, file output và cấu hình.

Không giả lập terminal bằng pipe rồi kết luận JLine hoạt động giống terminal thật. Không dùng một runner Linux để thay thế kiểm thử launcher Windows hoặc macOS.

## 19. Lỗi thường gặp khi đóng gói và chạy

### JAR chạy trong IDE nhưng java -jar báo thiếu class

Kiểm tra artifact có được Spring Boot repackage hoặc Gradle bootJar tạo ra hay không. Có thể bạn đang chạy plain JAR thay vì executable JAR.

### CI bị treo ở prompt

Spring Shell 4.x mặc định interactive, kể cả khi truyền command arguments. Đặt SPRING_SHELL_INTERACTIVE_ENABLED=false trong environment của process CI.

### Command arguments không được thực thi

Kiểm tra runner đang dùng và property interactive. Với NonInteractiveShellRunner, command arguments được thực thi rồi process kết thúc.

### File script không được chạy

Kiểm tra đường dẫn file, quyền đọc và cú pháp gọi. NonInteractiveShellRunner nhận file script qua tiền tố @; built-in command script dùng option --file trong shell tương tác.

### Launcher không tìm thấy JAR

Không ghép đường dẫn từ working directory hiện tại. Tính đường dẫn từ thư mục của launcher và quote toàn bộ đường dẫn.

### Launcher POSIX báo permission denied

Kiểm tra executable bit trong Git và sau khi giải nén. File cần được lưu với mode 100755 nếu được gọi trực tiếp.

### Windows không chuyển đúng arguments

Kiểm tra cách launcher dùng %* hoặc PowerShell @args. Không ghép toàn bộ arguments thành một chuỗi và tự thêm dấu nháy tùy tiện.

### Exit code luôn là 0

Kiểm tra launcher có trả lại exit code của Java hay không. Bash nên dùng exec; CMD dùng exit /b với ERRORLEVEL; PowerShell cần lưu LASTEXITCODE trước khi chạy lệnh khác.

### Unicode bị lỗi khi hiển thị

Kiểm tra terminal encoding, encoding của file output và locale. File UTF-8 không tự bảo đảm console đang dùng UTF-8.

### JLine không hoạt động trong CI

CI thường không có TTY. Dùng non-interactive mode cho CI; kiểm tra tính năng JLine trong terminal thật.

### Container không ghi được file

Buildpack image thường chạy dưới user không phải root. Kiểm tra quyền ghi của volume mount và thư mục đích.

### File cấu hình ngoài không được nạp

Kiểm tra working directory, additional-location, profile và đường dẫn file. Không giả định working directory là thư mục chứa JAR.

## 20. Quy trình phát hành mẫu

Một quy trình phát hành có thể thực hiện theo thứ tự:

~~~mermaid
flowchart TD
    A[Checkout source] --> B[Build bằng wrapper]
    B --> C[Unit và Spring Shell tests]
    C --> D[Đóng gói executable JAR]
    D --> E[Smoke test bằng java -jar]
    E --> F[Tạo ZIP có launcher và config mẫu]
    F --> G[Test launcher sau khi giải nén]
    G --> H[Kiểm tra terminal thật]
    H --> I[Chạy CI non-interactive trên OS hỗ trợ]
    I --> J[Tạo checksum và release notes]
    J --> K[Phát hành artifact]
~~~

Nếu có OCI image, thêm bước build image, chạy smoke test container và publish image vào registry. Không bỏ qua bước test artifact sau khi đóng gói chỉ vì unit test đã thành công.

## 21. Checklist hoàn thành

- [ ] Java runtime tối thiểu được ghi rõ.
- [ ] Spring Boot và Spring Shell dùng phiên bản tương thích.
- [ ] Maven repackage hoặc Gradle bootJar tạo executable JAR.
- [ ] Artifact chạy được bằng java -jar.
- [ ] Smoke test command help thành công.
- [ ] Interactive mode chạy trên terminal thật.
- [ ] JLine hoạt động nếu ứng dụng sử dụng JLine runner.
- [ ] Non-interactive mode được bật rõ trong CI.
- [ ] Command batch không phụ thuộc prompt.
- [ ] Script nhiều command chạy được bằng cơ chế đã chọn.
- [ ] Launcher POSIX chuyển tiếp arguments và exit code.
- [ ] Launcher CMD/PowerShell chuyển tiếp arguments và exit code.
- [ ] Launcher tìm JAR theo vị trí của chính nó.
- [ ] Đường dẫn có dấu cách và Unicode được kiểm tra.
- [ ] Working directory và file output có hành vi được định nghĩa.
- [ ] Cấu hình theo môi trường nằm ngoài JAR.
- [ ] Secret không nằm trong artifact hoặc log.
- [ ] ZIP chạy được sau khi giải nén sang thư mục mới.
- [ ] Permission executable được giữ sau khi đóng gói.
- [ ] CI chạy trên các OS được công bố hỗ trợ.
- [ ] Có checksum và hướng dẫn cài đặt/phát hành.

## 22. Tự kiểm tra

**Câu 1.** Maven dùng plugin nào để tạo executable JAR cho ứng dụng Spring Boot?

**Gợi ý trả lời:** spring-boot-maven-plugin với goal repackage. Khi dùng Spring Boot Starter Parent, execution này được cấu hình sẵn trong lifecycle package.

**Câu 2.** Gradle dùng task nào để tạo executable JAR?

**Gợi ý trả lời:** bootJar.

**Câu 3.** Vì sao java -jar cần executable JAR?

**Gợi ý trả lời:** Executable JAR chứa cấu trúc loader, main class và dependency runtime cần thiết để tự khởi chạy.

**Câu 4.** Spring Shell 4.x có tự chuyển sang non-interactive khi nhận command arguments không?

**Gợi ý trả lời:** Không. Interactive mode bật mặc định. Đặt spring.shell.interactive.enabled=false để dùng NonInteractiveShellRunner.

**Câu 5.** Biến môi trường nào tắt interactive mode?

**Gợi ý trả lời:** SPRING_SHELL_INTERACTIVE_ENABLED=false.

**Câu 6.** NonInteractiveShellRunner nhận script file bằng cách nào?

**Gợi ý trả lời:** Truyền đường dẫn file với tiền tố @, ví dụ @/absolute/path/commands.shell.

**Câu 7.** Vì sao cần test trên terminal thật?

**Gợi ý trả lời:** TTY, JLine, history, completion, password prompt, Unicode và terminal width có thể khác khi chạy trong IDE hoặc pipe.

**Câu 8.** Vì sao launcher cần trả lại exit code của Java?

**Gợi ý trả lời:** Scheduler và CI dựa vào exit code để xác định command thành công hay thất bại. Wrapper che exit code sẽ làm pipeline đánh giá sai.

**Câu 9.** Khi nào nên dùng OCI image thay cho ZIP chứa executable JAR?

**Gợi ý trả lời:** Khi nền tảng triển khai đã chuẩn hóa container và cần runtime nhất quán, quản lý image qua registry, cấu hình qua environment/volume.

## Kết luận

Đóng gói CLI không chỉ là tạo một file JAR. Một bản phân phối hoàn chỉnh cần executable archive, launcher phù hợp với hệ điều hành, cấu hình bên ngoài, hướng dẫn chạy và kiểm tra sau khi giải nén. Spring Boot Maven Plugin hoặc Gradle bootJar tạo executable JAR; launcher giúp người dùng chạy cùng artifact từ nhiều working directory và chuyển tiếp arguments cùng exit code.

Với Spring Shell 4.x, hãy phân biệt rõ interactive và non-interactive mode. Terminal thật cần TTY để kiểm tra prompt, JLine, history, completion và Unicode. CI cần đặt spring.shell.interactive.enabled=false để chạy command hoặc script rồi kết thúc process. Cuối cùng, kiểm thử artifact và launcher trên các hệ điều hành được hỗ trợ, xác minh file output, quyền thực thi, cấu hình và checksum trước khi phát hành.

## Tài liệu tham khảo

- [Spring Shell 4.0.3 — Execution and Interaction Modes](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell 4.0.3 — NonInteractiveShellRunner API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html)
- [Spring Shell 4.0.3 — Script Command](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html)
- [Spring Boot 4.0 — Packaging Executable Archives with Maven](https://docs.spring.io/spring-boot/4.0/maven-plugin/packaging.html)
- [Spring Boot 4.0 — Packaging Executable Archives with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
- [Spring Boot — Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html)
- [Spring Boot — Efficient Container Images](https://docs.spring.io/spring-boot/reference/packaging/container-images/efficient-images.html)
- [Java SE — Process and Runtime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html)
