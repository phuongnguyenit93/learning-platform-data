# Phân phối cùng tệp cấu hình, ví dụ và tài liệu trợ giúp

Một file JAR chạy được chưa phải là một bản phân phối CLI hoàn chỉnh. Người dùng còn cần biết cách khởi chạy, nơi đặt cấu hình, cách thay đổi môi trường, cú pháp command, ví dụ thao tác và cách tra cứu trợ giúp khi không có IDE hoặc Internet. Nếu chỉ gửi JAR, đội vận hành thường phải tự đoán working directory, tên property, profile và cách gọi command.

Với Spring Shell 3.x, có thể đóng gói ứng dụng thành executable JAR bằng Spring Boot Maven/Gradle plugin, sau đó phân phối cùng thư mục `config`, `examples`, `docs` và script khởi chạy. Tệp cấu hình mẫu nên chứa giá trị an toàn, không chứa secret; tài liệu offline nên giải thích cách dùng built-in `help`, `version`, `script` và completion.

## Xác định những gì người nhận cần có

Trước khi tạo gói, xác định người dùng nhận CLI theo cách nào và họ cần thực hiện công việc gì:

| Thành phần | Nội dung | Mục đích |
|---|---|---|
| Executable JAR | Ứng dụng và dependency runtime | Chạy bằng `java -jar` |
| Launcher script | Script cho Bash và Windows CMD (có thể gọi từ PowerShell) | Chuẩn hóa working directory, đường dẫn JAR và truyền nguyên các đối số |
| `config/` | Tệp cấu hình mẫu, cấu hình theo profile | Khởi chạy với thiết lập môi trường phù hợp |
| `examples/` | Script command, input mẫu và dữ liệu demo không nhạy cảm | Giúp người dùng thử các luồng thường gặp |
| `docs/` | README, danh sách command, hướng dẫn vận hành, troubleshooting | Hỗ trợ sử dụng offline |
| Completion | Script completion của Bash nếu cần | Gợi ý command/option ở shell hệ điều hành |
| Release metadata | Version, checksum, changelog, license và third-party notices | Xác định nguồn gốc và kiểm tra gói |

Không phải bản phân phối nào cũng cần mọi thành phần. Một CLI nội bộ nhỏ có thể chỉ cần JAR, README và config mẫu. Một CLI dùng trong production, CI hoặc được nhiều nhóm cài đặt cần thêm ví dụ, tài liệu vận hành, kiểm tra checksum và hướng dẫn nâng cấp.

## Tạo executable JAR

Spring Boot Maven Plugin đóng gói ứng dụng cùng dependency vào executable JAR để chạy bằng `java -jar`. Với dự án dùng `spring-boot-starter-parent`, execution `repackage` đã được cấu hình sẵn; chỉ cần khai báo plugin. Nếu không dùng parent, cần khai báo execution cho goal `repackage`.

Ví dụ Maven:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>build-info</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Nếu dùng `spring-boot-starter-parent`, execution `repackage` đã được cấu hình sẵn. Nếu không dùng parent, thêm execution sau vào cùng plugin:

```xml
<execution>
    <id>repackage</id>
    <goals>
        <goal>repackage</goal>
    </goals>
</execution>
```

Goal `build-info` tạo `META-INF/build-info.properties` với thông tin tọa độ project và thời điểm build. Spring Shell có built-in command `version`, vì vậy build metadata giúp người vận hành xác định phiên bản đang chạy.

Build bằng Maven Wrapper:

```bash
./mvnw clean package
```

Trên Windows:

```powershell
.\mvnw.cmd clean package
```

Với Gradle, plugin Spring Boot cung cấp task `bootJar`:

```bash
./gradlew clean bootJar
```

Artifact thường nằm ở `target/` với Maven hoặc `build/libs/` với Gradle. Kiểm tra tên file và xác nhận JAR chạy được:

```bash
java -version
java -jar target/customer-cli-1.4.0.jar
```

Khi phân phối, ghi rõ phiên bản Java tối thiểu tương thích với phiên bản Spring Boot đang dùng. Người nhận cần cài runtime phù hợp hoặc nhận một gói runtime riêng nếu sản phẩm chọn cách phân phối đó.

## Chọn loại artifact phù hợp

| Cách đóng gói | Khi nên dùng | Lưu ý |
|---|---|---|
| Executable JAR thông thường | Phân phối CLI đa nền tảng | Người dùng chạy `java -jar`; có thể đặt launcher script bên ngoài |
| Fully executable JAR | Triển khai trực tiếp như executable trên Linux hoặc tích hợp init system | JAR được thêm launch script ở đầu file; một số công cụ xử lý ZIP/JAR không đọc được định dạng này |
| Layered JAR | Đóng gói thành Docker image | Dependency và application được tách lớp để tận dụng cache image |
| Native executable | Khi đã có quy trình build/test native và cần giảm phụ thuộc JRE | Cần kiểm tra tương thích native, reflection, resource và startup behavior riêng |

Với gói ZIP/TAR dùng trên Windows, macOS và Linux, executable JAR thông thường cộng với launcher script thường dễ xử lý nhất. Fully executable JAR hữu ích cho một số cách cài đặt Linux, nhưng Spring Boot lưu ý các công cụ như `jar -xf` có thể không xử lý đúng định dạng này. Nếu cần trích xuất các layer bằng `jarmode=tools`, không bật launch script trên cùng artifact đó.

## Bố trí thư mục phát hành

Một gói CLI có thể có cấu trúc như sau:

```text
customer-cli-1.4.0/
├── bin/
│   ├── customer-cli
│   └── customer-cli.cmd
├── lib/
│   └── customer-cli-1.4.0.jar
├── config/
│   ├── application.yaml.example
│   └── application-production.yaml.example
├── examples/
│   ├── first-run.shell
│   └── daily-check.shell
├── completion/
│   └── customer-cli.bash
├── docs/
│   ├── README.md
│   ├── COMMANDS.md
│   ├── CONFIGURATION.md
│   ├── OPERATIONS.md
│   └── TROUBLESHOOTING.md
├── CHANGELOG.md
├── LICENSE
└── THIRD-PARTY-NOTICES.txt
```

Tên file chỉ là ví dụ. Dùng cùng một version trong tên thư mục, tên JAR, release tag và tài liệu. Giữ `lib/` riêng giúp launcher không phụ thuộc người dùng đang đứng ở thư mục nào; `config/`, `examples/` và `docs/` nằm cạnh nhau để dễ sao lưu hoặc triển khai.

Không đặt file cấu hình chứa mật khẩu, token, private key hoặc dữ liệu production vào gói phát hành. Các file `.example` chỉ chứa giá trị mẫu an toàn và hướng dẫn nơi cung cấp secret ở runtime.

## Phân phối cấu hình bên ngoài JAR

Spring Boot cho phép tách cấu hình khỏi code để cùng một JAR chạy ở nhiều môi trường. Theo mặc định, Boot tìm `application.properties`/`application.yaml` trong classpath và trong working directory, gồm thư mục hiện tại, `config/` và các thư mục con trực tiếp của `config/`.

Các file cấu hình bên ngoài JAR được xử lý sau cấu hình đóng gói, nên có thể ghi đè giá trị mặc định trong JAR. Environment variables, Java system properties và command-line arguments có độ ưu tiên cao hơn config data. Vì vậy:

- Đặt giá trị mặc định không nhạy cảm trong `application.yaml` đóng gói.
- Đặt cấu hình triển khai trong `config/application.yaml` bên ngoài JAR.
- Dùng `application-{profile}.yaml` cho thiết lập theo profile.
- Dùng environment variable hoặc secret manager/configuration tree cho secret.
- Không ghi đè cấu hình bằng cách sửa trực tiếp file bên trong JAR.

### Tạo file cấu hình mẫu

Gói phát hành có thể chứa `config/application.yaml.example`:

```yaml
spring:
  application:
    name: customer-cli
  main:
    banner-mode: "off"

app:
  api:
    base-url: "https://api.example.invalid"
    connect-timeout: 3s
    read-timeout: 10s
  output:
    format: table

logging:
  level:
    root: INFO
```

Tên miền `.invalid` là giá trị minh họa, không phải endpoint dịch vụ thật. Không đặt API key hoặc password trong file mẫu.

Người dùng copy file mẫu thành tên Spring Boot tự động nhận diện:

```bash
cp config/application.yaml.example config/application.yaml
```

PowerShell:

```powershell
Copy-Item config/application.yaml.example config/application.yaml
```

Sau đó chỉnh các giá trị môi trường trong `config/application.yaml`. Nếu muốn đặt tên file khác `application`, cần cấu hình `spring.config.name` hoặc import file tường minh.

### Cấu hình theo profile

Ví dụ `config/application-production.yaml.example` có thể chứa URL, timeout và mức log của môi trường production nhưng không chứa credential. Người triển khai copy thành `config/application-production.yaml` rồi kích hoạt profile:

```bash
SPRING_PROFILES_ACTIVE=production ./bin/customer-cli version
```

Trong PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "production"
.\bin\customer-cli.cmd version
```

Tên profile phải khớp phần hậu tố của file `application-{profile}.yaml`. Không đưa profile production vào làm mặc định nếu gói còn được dùng ở môi trường phát triển hoặc demo.

### Chọn additional-location hay location

Nếu cấu hình nằm ở thư mục chuẩn `config/` trong working directory, thường không cần property bổ sung. Nếu muốn đọc từ một vị trí riêng, dùng `spring.config.additional-location` để thêm vị trí mà vẫn giữ các vị trí mặc định:

```bash
SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:/etc/customer-cli/ \
  ./bin/customer-cli customer-list
```

Đường dẫn thư mục kết thúc bằng dấu `/`. Tiền tố `optional:` chỉ dùng khi file/thư mục có thể không tồn tại. Nếu cấu hình bắt buộc, bỏ `optional:` để ứng dụng dừng sớm khi không tìm thấy file.

`spring.config.location` thay thế các vị trí mặc định; `spring.config.additional-location` bổ sung vị trí mới và thường phù hợp hơn khi người đóng gói muốn người dùng vẫn giữ cấu hình mặc định trong JAR. Hai property này được xử lý rất sớm lúc khởi động nên phải truyền qua environment variable, system property hoặc command-line argument. Ví dụ dùng `SPRING_CONFIG_ADDITIONAL_LOCATION` để property cấu hình không bị nhầm với option của command Spring Shell.

## Launcher giữ working directory ổn định

Spring Boot tìm `config/` theo working directory. Nếu người dùng gọi JAR từ một thư mục khác, cấu hình bên cạnh JAR có thể không được tìm thấy. Launcher nên xác định thư mục gói, chuyển working directory tới đó và truyền nguyên các tham số còn lại.

### Launcher cho Bash

File `bin/customer-cli`:

```sh
#!/usr/bin/env sh
set -eu

APP_HOME=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
JAR="$APP_HOME/lib/customer-cli-1.4.0.jar"

if [ ! -r "$JAR" ]; then
    printf '%s\n' "Không tìm thấy ứng dụng: $JAR" >&2
    exit 1
fi

cd "$APP_HOME"
exec java -jar "$JAR" "$@"
```

Đặt quyền thực thi khi tạo archive hoặc sau khi giải nén:

```bash
chmod +x bin/customer-cli
```

`"$@"` giữ từng đối số riêng biệt, kể cả khi giá trị chứa dấu cách. Không ghép toàn bộ tham số thành một chuỗi rồi dùng `eval`; cách đó có thể làm sai quoting và tạo lỗ hổng command injection.

### Launcher cho Windows CMD và PowerShell

File `bin/customer-cli.cmd`:

```bat
@echo off
setlocal
set "APP_HOME=%~dp0.."
pushd "%APP_HOME%"

if not exist "lib\customer-cli-1.4.0.jar" (
    echo Khong tim thay ung dung: lib\customer-cli-1.4.0.jar 1>&2
    popd
    exit /b 1
)

java -jar "lib\customer-cli-1.4.0.jar" %*
set "APP_EXIT=%ERRORLEVEL%"
popd
exit /b %APP_EXIT%
```

Launcher dùng `%*` để chuyển tiếp các option của Spring Shell và trả lại exit code của JVM. Có thể gọi file `.cmd` từ Command Prompt hoặc PowerShell; người dùng cần cài Java runtime và có `java` trong `PATH`.

## Đưa ví dụ thao tác vào gói

Ví dụ nên dùng dữ liệu giả, không gọi hệ thống production và không yêu cầu credential thật. Mỗi file cần ghi rõ mục đích, command được chạy và điều kiện cần chuẩn bị.

Ví dụ `examples/first-run.shell`:

```text
help
version
customer-list --limit 10
customer-show --id C001
```

`customer-list` và `customer-show` là command minh họa; thay bằng command thực tế của ứng dụng. Mỗi dòng trong script là một command. Trong Spring Shell 3.x có built-in `script` command để đọc và thực thi file:

```text
script --file examples/first-run.shell
```

Nếu muốn chạy command script như một phần của quy trình khởi chạy, Spring Shell 3.3.x có `ScriptShellRunner`; runner này không bật mặc định từ 3.3.x. Cần bật property tương ứng `spring.shell.script.enabled=true` và kiểm thử cách runner xử lý lỗi/exit code trước khi đưa vào pipeline. Không nhầm `script` built-in command trong một phiên shell với runner xử lý đối số khởi động.

Trong ví dụ, không lưu password hoặc token vào file script. Nếu một bước cần xác thực, hướng dẫn người dùng lấy secret từ secret manager hoặc file secret được cấp quyền phù hợp tại runtime.

## Tài liệu trợ giúp trong ứng dụng và trong gói

Spring Shell có built-in `help` command. Khi chạy ứng dụng, người dùng có thể:

```text
help
help customer-list
customer-list --help
```

`help` liệt kê command và mô tả ngắn; `help <command>` hiển thị tên, cú pháp và option cùng thông tin bắt buộc/tùy chọn. Option `-h`/`--help` cũng được tích hợp cho command theo cấu hình help mặc định.

Để trợ giúp có ích, khai báo mô tả ngắn cho command và từng option. Với Spring Shell 3.x legacy annotation:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
class CustomerCommands {

    @ShellMethod(
            key = "customer-list",
            value = "Liệt kê khách hàng theo bộ lọc.")
    public String list(
            @ShellOption(
                    value = "status",
                    defaultValue = "ACTIVE",
                    help = "Trạng thái cần lọc.") String status,
            @ShellOption(
                    value = "limit",
                    defaultValue = "20",
                    help = "Số bản ghi tối đa cần hiển thị.") int limit) {
        return "status=" + status + ", limit=" + limit;
    }
}
```

`@ShellMethod.value` mô tả command; `@ShellOption.help` mô tả option. Mô tả nên ngắn, bắt đầu bằng chữ hoa và kết thúc bằng dấu chấm. Tài liệu offline trong `docs/COMMANDS.md` nên mở rộng phần help runtime bằng ví dụ thực tế, input/output mẫu, quyền cần có và exit code.

### Tổ chức tài liệu offline

Một README phân phối nên trả lời nhanh:

1. CLI này giải quyết công việc gì và hỗ trợ hệ điều hành nào?
2. Cần Java runtime phiên bản nào?
3. Cách giải nén và chạy command đầu tiên?
4. Cấu hình ở đâu, profile nào được hỗ trợ?
5. Cách cung cấp credential an toàn?
6. Các command quan trọng và cách xem help?
7. Cách chạy ví dụ/script?
8. Cách xem version, log, exit code và xử lý lỗi?
9. Cách nâng cấp, sao lưu cấu hình và quay về bản trước?

`CONFIGURATION.md` giải thích tên property, giá trị mặc định, nguồn override và profile. `OPERATIONS.md` giải thích backup, log, quyền file, secret, proxy, network và quy trình khôi phục. `TROUBLESHOOTING.md` ánh xạ lỗi thường gặp sang bước kiểm tra cụ thể.

## Phân phối command completion

Spring Shell có completion trong REPL khi dùng JLine. Người dùng nhấn Tab để nhận gợi ý command và option. Với command-line shell của hệ điều hành, tài liệu Spring Shell 3.4.1 nêu built-in `completion` command tạo script cho Bash; command-line completion không được mô tả là hỗ trợ mọi shell hệ điều hành.

Có thể tạo file completion trong gói phát hành bằng command non-interactive:

```bash
./bin/customer-cli completion bash > completion/customer-cli.bash
```

Người dùng Bash có thể nạp script trong phiên hiện tại:

```bash
source completion/customer-cli.bash
```

Nếu muốn tự động nạp ở các phiên sau, thêm một dòng `source` tới file đã cài vào cấu hình Bash của người dùng. Không ghi đè toàn bộ `.bashrc` hoặc file cấu hình shell hiện có. Kiểm tra script completion với tên executable thực tế và các command/option đã phát hành.

## Cung cấp thông tin version và build

Spring Shell có built-in `version` command. Spring Boot Maven Plugin có goal `build-info` tạo `META-INF/build-info.properties`, từ đó ứng dụng có thể hiển thị version, artifact và thời điểm build.

Release metadata bên ngoài gói cũng nên ghi:

- Version của CLI và release tag.
- Spring Boot/Spring Shell version được dùng để build.
- Java runtime tối thiểu.
- Commit hoặc revision nguồn.
- Ngày phát hành.
- SHA-256 checksum của archive.
- Thay đổi đáng chú ý và hướng dẫn nâng cấp.

Không đưa secret, endpoint nội bộ nhạy cảm hoặc thông tin hạ tầng không cần thiết vào build metadata.

## Tạo archive và checksum

Sau khi tạo cấu trúc phát hành, đóng gói thư mục thành ZIP cho Windows và TAR.GZ cho macOS/Linux:

```bash
zip -r customer-cli-1.4.0.zip customer-cli-1.4.0/
tar -czf customer-cli-1.4.0.tar.gz customer-cli-1.4.0/
```

Tạo SHA-256 checksum:

```bash
sha256sum customer-cli-1.4.0.zip customer-cli-1.4.0.tar.gz > SHA256SUMS
```

Đặt `SHA256SUMS` cạnh hai archive trong thư mục phát hành, không cần nhúng file checksum vào chính archive mà nó đang xác minh.

Người nhận xác minh archive:

```bash
sha256sum -c SHA256SUMS
```

Trên Windows PowerShell:

```powershell
Get-FileHash .\customer-cli-1.4.0.zip -Algorithm SHA256
```

So sánh hash với giá trị được công bố qua kênh phát hành đáng tin cậy. Checksum phát hiện file hỏng hoặc khác nội dung; nếu cần xác minh người phát hành, dùng chữ ký số và công bố public key/fingerprint qua kênh độc lập.

Gói phát hành cũng cần giữ license và third-party notices theo yêu cầu của dependency. Không đưa file build tạm, log test, `.env`, private key, database dump hoặc thư mục `.git` vào archive.

## Cài đặt và nâng cấp

Người dùng nên cài mỗi version vào một thư mục riêng:

```text
/opt/customer-cli/
├── releases/
│   ├── 1.3.0/
│   └── 1.4.0/
├── shared/
│   └── config/
└── current -> releases/1.4.0
```

Với cách này, file cấu hình và dữ liệu vận hành nằm ngoài release directory. Khi nâng cấp, giải nén release mới, kiểm tra config compatibility rồi đổi symlink `current`; khi cần rollback có thể trỏ lại release trước. Không ghi đè JAR đang chạy hoặc xóa cấu hình người dùng khi giải nén bản mới.

Nếu CLI chạy như service lâu dài trên Linux, có thể tích hợp `systemd` với `WorkingDirectory` trỏ tới thư mục cài đặt và `ExecStart` gọi JAR/launcher. Với command chạy một lần trong terminal hoặc CI, chỉ cần launcher và exit code phù hợp; không cần cài CLI thành service nền.

## Kiểm tra gói như người dùng mới

Không chỉ chạy ứng dụng từ IDE hoặc `target/`. Hãy tạo archive, giải nén vào một thư mục sạch và kiểm tra đúng nội dung được phát hành:

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Archive có đúng file | Có JAR, launcher, config mẫu, examples, docs, license và third-party notices; checksum được phát hành cạnh archive |
| Không có secret | Không có `.env`, password, token, private key hoặc config production |
| Java runtime | Thiếu Java hoặc sai version thì thông báo rõ |
| Launcher từ thư mục khác | Vẫn tìm thấy JAR và `config/` của gói |
| Cấu hình mẫu | Copy thành `application.yaml` và ứng dụng đọc được |
| Profile | File `application-{profile}.yaml` được nạp khi kích hoạt profile tương ứng |
| Override | Environment variable và CLI property ghi đè theo đúng precedence |
| Built-in help | `help`, `help <command>` và `--help` hiển thị đúng |
| Version | `version` hiển thị thông tin build mong đợi |
| Examples | Script chạy theo đúng thứ tự và có kết quả dự kiến |
| Completion | Bash script được tạo và gợi ý command đã phát hành |
| Exit code | Thành công, validation error và lỗi hệ thống trả mã theo hợp đồng CLI |
| Checksum | Người nhận xác minh được archive |
| Upgrade/rollback | Cấu hình người dùng được giữ lại và có thể quay lại release trước |

Nên thực hiện smoke test trên ít nhất một máy sạch không có source code hoặc IDE. Nếu hỗ trợ Windows, Linux và macOS, kiểm tra launcher, path separator, quyền thực thi, encoding và Java runtime trên từng nền tảng mục tiêu.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| JAR chạy ở máy phát triển nhưng không chạy trên máy nhận | Máy nhận thiếu Java hoặc sai version | Ghi rõ Java requirement và kiểm tra `java -version` |
| Không tìm thấy cấu hình | Working directory khác thư mục gói | Dùng launcher chuyển tới app home hoặc truyền `spring.config.additional-location` |
| File `.yaml.example` không được nạp | Spring Boot chỉ tự tìm basename `application` | Copy thành `application.yaml` hoặc import rõ ràng |
| Cấu hình ngoài không ghi đè cấu hình trong JAR | Đặt sai location hoặc dùng `spring.config.location` không đúng mục đích | Kiểm tra config search path; cân nhắc `spring.config.additional-location` |
| Gói ZIP không giải nén được bằng công cụ chuẩn | Dùng fully executable JAR có launch script | Dùng executable JAR thông thường cho archive đa nền tảng |
| Help thiếu mô tả option | Thiếu `@ShellMethod.value` hoặc `@ShellOption.help` | Bổ sung mô tả ngắn cho command và option |
| Bash Tab không hoạt động | Chưa tạo/nạp completion script hoặc executable name khác | Chạy `completion bash`, source file và kiểm tra tên CLI |
| Script chạy trong REPL nhưng không chạy lúc startup | `ScriptShellRunner` chưa được bật ở Spring Shell 3.3.x | Bật `spring.shell.script.enabled=true` nếu cần startup script |
| Release mới mất cấu hình | Giải nén đè toàn bộ thư mục cũ | Đặt config ngoài release directory và nâng cấp theo version directory |
| Checksum không khớp | Archive bị hỏng hoặc thay đổi sau khi phát hành | Tải lại từ nguồn tin cậy và kiểm tra chữ ký/checksum |
| README khác với command thực tế | Tài liệu không được cập nhật cùng release | Kiểm tra command/help/examples như một phần release checklist |

## Quy trình phát hành

1. Chốt version, Java baseline và nền tảng mục tiêu.
2. Build executable JAR và build metadata bằng Maven hoặc Gradle.
3. Tạo release directory gồm `bin`, `lib`, `config`, `examples`, `completion` và `docs`.
4. Đưa cấu hình mẫu an toàn vào gói; giữ secret ở secret manager hoặc môi trường runtime.
5. Viết README, command reference, configuration guide, operations guide và troubleshooting.
6. Tạo ví dụ script có thể chạy lại bằng dữ liệu giả.
7. Tạo Bash completion nếu sản phẩm cần command-line completion.
8. Đóng gói ZIP/TAR.GZ, license, third-party notices và changelog.
9. Tạo SHA-256 checksum và chữ ký nếu quy trình phát hành yêu cầu.
10. Giải nén archive vào môi trường sạch, kiểm tra launcher, config, help, examples, completion và exit code.
11. Phát hành cùng hướng dẫn cài đặt, nâng cấp, rollback và Java requirement.

Một bản phân phối tốt giúp người dùng cài đặt và thực hiện command đầu tiên mà không cần mở source code. JAR cung cấp chương trình, thư mục cấu hình giúp tách môi trường, examples cho phép thử các luồng thường gặp, còn help và tài liệu offline giúp người dùng tự tra cứu khi vận hành.

## Tài liệu tham khảo

- [Spring Boot 3.4 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.4/maven-plugin/packaging.html): goal `repackage`, executable JAR, manifest và layered archive.
- [Spring Boot 3.4 — Externalized Configuration](https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html): vị trí tìm cấu hình, profile-specific files, property precedence, `spring.config.location` và `spring.config.additional-location`.
- [Spring Boot 3.4 — Installing Applications](https://docs.spring.io/spring-boot/3.4/how-to/deployment/installing.html): chạy JAR trực tiếp, systemd và fully executable JAR cho init.d.
- [Spring Boot 3.4 — Dockerfiles and Layered JARs](https://docs.spring.io/spring-boot/3.4/reference/packaging/container-images/dockerfiles.html): trích xuất layer bằng `jarmode=tools` và tối ưu Docker image.
- [Spring Boot 3.4 — Build Info](https://docs.spring.io/spring-boot/3.4/maven-plugin/build-info.html): tạo `META-INF/build-info.properties` với `build-info` goal.
- [Spring Shell 3.3.4 — Help](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/help.html): built-in help command, command descriptions và help templates.
- [Spring Shell 3.4.1 — Completion](https://docs.spring.io/spring-shell/reference/completion.html): completion trong REPL và Bash completion cho command line.
- [Spring Shell 3.4.2 API — Script](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Script.html): built-in command đọc và thực thi command từ file.
- [Spring Shell 3.3.4 — Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html): interactive, non-interactive và script runners; cấu hình runner từ 3.3.x.
- [Spring Shell 3.3.4 — Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html): built-in commands và khai báo mô tả command bằng `@ShellMethod`.
- [Spring Shell 3.4 API — Version](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Version.html): built-in `version` command và cách nhận `BuildProperties`/`GitProperties`.
