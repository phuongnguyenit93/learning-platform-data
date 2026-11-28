# Tự động hóa trong CI và môi trường không có TTY

Một ứng dụng Spring Shell có thể chạy trong terminal của người vận hành, trong pipeline CI/CD, trong container hoặc dưới một scheduler. Các môi trường tự động thường không có terminal tương tác (TTY), không thể trả lời prompt và cần biết chính xác command thành công hay thất bại để quyết định bước tiếp theo.

Để chạy ổn định trong các môi trường này, hãy chọn non-interactive mode ngay khi khởi động, truyền đầy đủ input qua argument hoặc cấu hình, chuẩn hóa output và kiểm tra exit code ở cấp process. Không nên dựa vào việc Spring Shell tự đoán môi trường có TTY hay không.

Bài này dùng Spring Shell 4.0.4 làm ví dụ chính, đồng thời nêu khác biệt quan trọng khi vận hành Spring Shell 3.3.x.

## 1. TTY và non-interactive có ý nghĩa gì?

TTY (teletypewriter) là giao diện terminal mà chương trình có thể dùng để đọc phím, điều khiển con trỏ, hiển thị prompt hoặc cập nhật màn hình. CI runner, pipe, cron job và container chạy nền thường không cấp một terminal tương tác cho tiến trình.

Một số dấu hiệu của môi trường không có TTY:

- `System.console()` có thể trả về `null`.
- `stdin` có thể là pipe hoặc đã kết thúc (EOF), không có người dùng chờ nhập.
- `stdout` có thể được chuyển vào file, artifact collector hoặc một command khác.
- Các chuỗi ANSI, spinner và cursor movement có thể làm log khó đọc.
- Prompt xác nhận hoặc nhập password có thể treo job vô thời hạn.

Không có TTY không đồng nghĩa tiến trình không thể đọc dữ liệu. Một command vẫn có thể đọc file, biến môi trường hoặc stdin nếu ứng dụng thiết kế rõ ràng cho việc đó. Điều cần tránh là yêu cầu một người dùng tương tác khi pipeline không có người dùng.

## 2. Chọn non-interactive mode trong Spring Shell 4

Spring Shell 4 bật interactive mode theo mặc định, kể cả khi process được khởi chạy cùng command-line arguments. Vì vậy, lệnh sau có thể vẫn mở prompt thay vì chạy command rồi thoát:

```bash
java -jar app.jar customer validate --file customers.csv
```

Để chọn `NonInteractiveShellRunner`, đặt property:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Trong CI, có thể đặt bằng biến môi trường:

```bash
export SPRING_SHELL_INTERACTIVE_ENABLED=false
java -jar app.jar customer validate --file customers.csv
```

Trên PowerShell:

```powershell
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "false"
java -jar app.jar customer validate --file .\customers.csv
```

`NonInteractiveShellRunner` thực thi command được truyền qua process arguments rồi kết thúc. Đây là runner phù hợp cho script và automation. Property phải được áp dụng trước khi Spring Shell chọn runner lúc khởi động.

Không dùng riêng `TERM=dumb`, `CI=true` hoặc kiểm tra `System.console()` như một cách thay thế cho property này. Các biến đó không tự chuyển Spring Shell 4 sang `NonInteractiveShellRunner`.

## 3. Cấu hình profile riêng cho CI

Để không phải thêm property ở mọi lệnh gọi, tạo profile `ci`:

`application-ci.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Khởi chạy:

```bash
SPRING_PROFILES_ACTIVE=ci java -jar app.jar customer validate --file customers.csv
```

Hoặc kết hợp profile và property trong pipeline:

```bash
export SPRING_PROFILES_ACTIVE=ci
export SPRING_SHELL_INTERACTIVE_ENABLED=false
java -jar app.jar customer validate --file customers.csv
```

Profile có thể chứa các cấu hình khác dành cho môi trường CI như endpoint test, logging, database tạm hoặc giới hạn timeout. Không đưa credential thật vào file profile được commit vào repository.

## 4. Khác biệt giữa Spring Shell 3.3 và 4.0

Hai thế hệ có quy tắc chọn runner khác nhau:

| Nội dung | Spring Shell 3.3.x | Spring Shell 4.0.4 |
|---|---|---|
| Runner mặc định | `NonInteractiveShellRunner` được bật mặc định | Interactive mode được bật mặc định |
| Chọn non-interactive | `spring.shell.interactive.enabled=false` và bật `spring.shell.noninteractive.enabled` theo cấu hình runner | `spring.shell.interactive.enabled=false` |
| Script runner | Có `ScriptShellRunner`, bật bằng `spring.shell.script.enabled=true` | `NonInteractiveShellRunner` hỗ trợ script qua `@file`; built-in `script` command cũng có thể chạy file |
| Mô hình command | API 3.x như `@ShellComponent`, `@ShellMethod` | API 4.x như `@Command`, `@Option` |
| Exception/exit status | `CommandExceptionResolver` và `CommandHandlingResult` | `ExitStatusExceptionMapper` và `ExitStatus` |

Từ Spring Shell 3.3, chỉ `NonInteractiveShellRunner` được bật mặc định; interactive và script runner có property riêng. Trong Spring Shell 4, ứng dụng chọn một mode ngay từ đầu. Không bê nguyên cấu hình runner 3.3 sang 4.0 mà không kiểm tra property và dependency.

Ví dụ cấu hình 3.3 khi muốn chạy script runner:

```yaml
spring:
  shell:
    interactive:
      enabled: false
    noninteractive:
      enabled: true
    script:
      enabled: true
```

Trong Spring Shell 4, cấu hình non-interactive tối thiểu là:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

## 5. Thiết kế command để có thể chạy tự động

Một command phù hợp với CI cần nhận đủ input qua argument hoặc cấu hình. Không yêu cầu người dùng xác nhận bằng phím `y`, nhập password ở prompt hoặc chọn mục trong menu.

Ví dụ command kiểm tra file CSV trong Spring Shell 4:

```java
import java.nio.file.Path;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class CustomerCommands {

    private final CustomerValidator validator;

    CustomerCommands(CustomerValidator validator) {
        this.validator = validator;
    }

    @Command(
            name = "customer validate",
            description = "Kiểm tra file khách hàng")
    public String validate(
            @Option(longName = "file", required = true) Path file) {

        ValidationSummary summary = validator.validate(file);
        return "Đã kiểm tra " + summary.totalRows()
                + " dòng; lỗi: " + summary.errorCount();
    }
}
```

Lời gọi:

```bash
java -jar app.jar customer validate --file /workspace/input/customers.csv
```

Command handler nhận file path tường minh, gọi service và trả kết quả. Service không cần biết nó được gọi từ CI, cron hay terminal.

Nếu một thao tác có tính phá hủy, cung cấp option xác nhận rõ ràng như `--confirm` hoặc `--dry-run`. Ví dụ pipeline có thể chạy kiểm tra trước:

```bash
java -jar app.jar customer delete --inactive-days 365 --dry-run
java -jar app.jar customer delete --inactive-days 365 --confirm
```

Không tự động coi EOF hoặc input rỗng là đồng ý thực hiện thao tác phá hủy.

## 6. Không để command chờ prompt trong CI

Các component tương tác như `StringInput`, `ConfirmationInput`, selector hoặc wizard cần có input provider và vòng tương tác phù hợp. Một pipeline không có người dùng sẽ không thể trả lời các prompt đó.

Hãy thiết kế hai cách gọi cho cùng use case nếu cần:

- Interactive: command hỏi thêm dữ liệu, cho phép người vận hành xem lại và xác nhận.
- Non-interactive: tất cả dữ liệu cần thiết được truyền qua options, file cấu hình hoặc biến môi trường.

Nếu thiếu input bắt buộc, command nên kết thúc với thông báo lỗi và trạng thái khác `0`. Không chờ stdin vô thời hạn.

Ví dụ kiểm tra biến môi trường trước khi chạy:

```java
String apiToken = environment.getProperty("CUSTOMER_API_TOKEN");
if (apiToken == null || apiToken.isBlank()) {
    throw new IllegalStateException(
            "Thiếu cấu hình CUSTOMER_API_TOKEN cho môi trường hiện tại");
}
```

Không in token vào thông báo lỗi hoặc log. Nếu ứng dụng cần nhập password, dùng secret manager hoặc input provider có cơ chế bảo vệ; tránh prompt tương tác trong CI.

## 7. Chạy một command trong process riêng

Với CI, cách dễ kiểm soát nhất là chạy mỗi bước quan trọng thành một process riêng. Ví dụ:

```bash
export SPRING_SHELL_INTERACTIVE_ENABLED=false

java -jar app.jar customer validate --file customers.csv
java -jar app.jar customer import --file customers.csv
java -jar app.jar customer report --format json
```

Mỗi process có một command, một log và một exit code riêng. Pipeline có thể dừng ngay khi một bước thất bại. Nếu dùng shell script, bật chế độ dừng khi lệnh lỗi:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

export SPRING_SHELL_INTERACTIVE_ENABLED=false

java -jar app.jar customer validate --file "$INPUT_FILE"
java -jar app.jar customer import --file "$INPUT_FILE"
java -jar app.jar customer report --format json
```

`set -e` làm script dừng khi một command đơn giản trả mã khác `0`; `-u` báo lỗi khi dùng biến chưa được khai báo; `pipefail` làm pipeline phản ánh lỗi của command trong pipe. Khi đặt lệnh trong `if`, `||` hoặc các cấu trúc điều khiển khác, hãy hiểu quy tắc của Bash vì `set -e` có một số ngoại lệ.

## 8. Chạy nhiều command từ file script

Spring Shell 4 cung cấp hai cách phổ biến để chạy chuỗi command.

**Cách 1: `@file` với NonInteractiveShellRunner**

```bash
export SPRING_SHELL_INTERACTIVE_ENABLED=false
java -jar app.jar @/workspace/scripts/customer-release.txt
```

`NonInteractiveShellRunner` nhận ký tự `@` trước tên file để hiểu đó là script. Script chứa các command được thực thi theo thứ tự.

**Cách 2: built-in `script` command**

```bash
java -jar app.jar script --file /workspace/scripts/customer-release.txt
```

Từ Spring Shell 4.0.4, option `--file` nhận đường dẫn tuyệt đối hoặc Spring resource reference như `file:` và `classpath:`:

```bash
java -jar app.jar script --file file:/workspace/scripts/customer-release.txt
java -jar app.jar script --file classpath:scripts/customer-release.txt
```

Một file script có một command trên mỗi dòng; command được chạy theo thứ tự xuất hiện. Dòng comment bắt đầu bằng `//`:

```text
// Chuẩn bị và kiểm tra dữ liệu
customer validate --file /workspace/input/customers.csv
customer import --file /workspace/input/customers.csv
customer report --format json
```

Tài liệu mô tả thứ tự thực thi, nhưng không nên giả định script tự dừng ở mọi loại lỗi theo đúng semantics của Bash `set -e`. Nếu mỗi bước phải là một cổng kiểm soát độc lập, gọi từng command từ CI runner hoặc kiểm thử rõ hành vi dừng/lỗi của script trên đúng phiên bản Spring Shell đang triển khai.

## 9. Exit status của command và exit code của process

CI thường quyết định thành công dựa trên mã thoát của process. Cần phân biệt:

- **Command exit status:** kết quả thực thi command bên trong Spring Shell.
- **JVM process exit code:** mã mà tiến trình Java trả về cho hệ điều hành hoặc CI runner.

Trong Spring Shell 4, `ExitStatusExceptionMapper` chuyển exception thành `ExitStatus` gồm mã và mô tả. Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
class ShellErrorConfiguration {

    @Bean
    ExitStatusExceptionMapper validationExitStatusMapper() {
        return exception -> {
            if (exception instanceof CustomerValidationException) {
                return new ExitStatus(2, "Dữ liệu khách hàng không hợp lệ");
            }
            return new ExitStatus(1, "Command không thể hoàn tất");
        };
    }
}
```

Gắn mapper vào command bằng tên bean:

```java
@Command(
        name = "customer import",
        description = "Nhập dữ liệu khách hàng",
        exitStatusExceptionMapper = "validationExitStatusMapper")
public String importCustomers(
        @Option(longName = "file", required = true) Path file) {
    importer.importFile(file);
    return "Nhập dữ liệu thành công";
}
```

`ExitStatusExceptionMapper` giúp Spring Shell xử lý exception ở cấp command. Tài liệu Spring Shell 4 lưu ý rằng command status khác với JVM process exit code; chỉ cấu hình mapper này không đồng nghĩa đã cấu hình mã thoát của process.

Nếu cần process exit code theo quy tắc của ứng dụng, hãy nối kết quả nghiệp vụ với cơ chế exit code của Spring Boot như `ExitCodeGenerator` hoặc `ExitCodeExceptionMapper` tại application boundary. Đảm bảo command failure không bị xử lý thành thông báo bình thường rồi mất thông tin trước khi tới lớp điều phối process. Kiểm tra kết quả bằng cách chạy JAR thật và đọc `Process.exitValue()`.

Spring Boot cung cấp `ExitCodeGenerator` để sinh mã thoát khi gọi `SpringApplication.exit(...)`; exception cũng có thể triển khai interface này. Cơ chế đó cần được nối đúng với cách ứng dụng khởi động và đóng context. Đừng chỉ kiểm tra chuỗi lỗi in ra console rồi kết luận pipeline sẽ nhận mã lỗi phù hợp.

## 10. Quy ước mã thoát cho pipeline

Mã thoát là contract giữa ứng dụng và hệ thống gọi nó. Chọn một bảng mã nhỏ, có tài liệu và giữ ổn định:

| Mã ví dụ | Ý nghĩa | Hành động pipeline gợi ý |
|---:|---|---|
| `0` | Thành công | Chạy bước tiếp theo |
| `2` | Sai cú pháp hoặc thiếu input | Dừng, sửa command/options |
| `3` | Dữ liệu nghiệp vụ không hợp lệ | Dừng, sửa dữ liệu nguồn |
| `4` | Dependency tạm thời không khả dụng | Retry có giới hạn nếu thao tác an toàn |
| `10` | Lỗi nội bộ không mong đợi | Dừng và điều tra log |

Đây là quy ước ví dụ của ứng dụng, không phải bảng mã bắt buộc của Spring Shell hoặc hệ điều hành. Tránh dùng mã `0` cho mọi trường hợp chỉ để pipeline tiếp tục.

Với Spring Shell 4, `ExitStatus` có các trạng thái chuẩn như `OK`, `USAGE_ERROR`, `AVAILABILITY_ERROR` và `EXECUTION_ERROR`. Có thể dùng các giá trị này làm cơ sở cho quy ước command-level; process-level mapping vẫn cần được xác minh riêng.

## 11. Giữ stdout sạch cho dữ liệu máy đọc

Một command có thể trả dữ liệu cho người dùng hoặc cho một command khác. Nếu output được pipe vào `jq`, lưu thành JSON artifact hoặc được đọc bởi một chương trình khác, không để banner, prompt, spinner hoặc log chen vào payload.

Quy ước nên áp dụng:

- stdout chứa kết quả command theo contract đã công bố.
- stderr hoặc log file chứa diagnostics, warning và thông tin debug.
- Output máy đọc không có ANSI color hoặc cursor movement.
- JSON/CSV có schema ổn định, tên field rõ ràng và encoding UTF-8.
- Không thay đổi thứ tự record giữa các lần chạy nếu thứ tự không có ý nghĩa.
- Ngày giờ, locale, timezone và số thập phân được cấu hình tường minh.

Nếu dùng logger console mặc định, hãy kiểm tra logger đang ghi vào stream nào trong bản JAR được đóng gói. Khi stdout là payload JSON, cấu hình logging sang stderr hoặc file để tránh làm hỏng JSON.

Ví dụ pipeline xử lý JSON:

```bash
java -jar app.jar customer report --format json > report.json
jq '.customers | length' report.json
```

Nếu command in log hoặc banner vào `report.json`, bước `jq` có thể thất bại dù nghiệp vụ đã chạy thành công. Hãy kiểm thử stdout và stderr riêng.

## 12. Tránh ANSI và hiệu ứng terminal trong CI

Các tính năng sau hữu ích khi có người quan sát trực tiếp nhưng không cần thiết trong log tự động:

- Màu ANSI và chuỗi điều khiển terminal.
- Spinner, progress animation và cập nhật cùng một dòng bằng carriage return.
- Xóa màn hình hoặc di chuyển con trỏ.
- Prompt nhập liệu, menu chọn và confirmation dialog.

Trong CI, ưu tiên thông báo một dòng cho mỗi giai đoạn, ví dụ `Đã xử lý 100/100 file`. Nếu cần tiến độ, ghi snapshot theo batch hoặc theo mốc phần trăm thay vì redraw terminal liên tục.

Đừng dùng `TERM=dumb` như bảo đảm duy nhất rằng output sẽ sạch. Kiểm thử output của command ở chế độ non-interactive và cấu hình renderer/logging phù hợp với contract.

## 13. Truyền cấu hình và secret an toàn

Không ghi API token, mật khẩu hoặc private key trực tiếp vào command line hoặc script file được lưu trong repository. Argument có thể xuất hiện trong process listing, shell history hoặc log pipeline.

Ưu tiên:

- CI secret store hoặc secret manager của nền tảng triển khai.
- Biến môi trường được inject vào process.
- File secret được mount với quyền đọc tối thiểu và vòng đời ngắn.
- Spring configuration binding để chuyển secret vào service cần dùng.

Ví dụ GitHub Actions:

```yaml
env:
  SPRING_SHELL_INTERACTIVE_ENABLED: "false"
  CUSTOMER_API_TOKEN: ${{ secrets.CUSTOMER_API_TOKEN }}
```

Trong command, chỉ truyền tham chiếu file hoặc tên môi trường nếu cần. Không log giá trị secret; tránh bật shell tracing (`set -x`) trong đoạn xử lý credential.

Không đưa secret vào artifact, image layer, Docker build argument hoặc file script được lưu lâu dài. Xóa file tạm sau khi chạy nếu pipeline buộc phải tạo chúng.

## 14. Retry, timeout và idempotency

CI có thể chạy lại job khi worker mất kết nối hoặc pipeline bị khởi động lại. Một command có side effect phải xác định cách xử lý khi được gọi nhiều lần.

- Đặt timeout cho HTTP client, database operation và toàn bộ job.
- Chỉ retry lỗi có khả năng tạm thời, ví dụ timeout hoặc HTTP 503.
- Không retry lỗi input hoặc validation.
- Dùng idempotency key, unique constraint hoặc checkpoint để tránh tạo dữ liệu trùng.
- Ghi request ID hoặc task ID để tra cứu lần chạy.
- Phân biệt trạng thái đã hoàn tất với trạng thái không rõ vì process bị kill giữa chừng.

Ví dụ một pipeline có thể chạy lại `customer import` sau timeout. Nếu command đã ghi dữ liệu nhưng chưa kịp trả kết quả, lần chạy tiếp theo cần nhận biết record đã được import hoặc dùng khóa idempotency. Không giả định exit code khác `0` luôn có nghĩa không có side effect.

## 15. Build executable JAR trong CI

Với Maven, dùng wrapper và chế độ batch để build trong môi trường không tương tác:

```bash
./mvnw -B clean verify
```

Với Gradle:

```bash
./gradlew --no-daemon clean check bootJar
```

Sau khi build, chạy smoke test bằng chính artifact được tạo:

```bash
export SPRING_SHELL_INTERACTIVE_ENABLED=false
java -jar target/customer-cli.jar customer validate --file src/test/resources/customers.csv
```

Không chỉ chạy test class trong IDE rồi coi đó là bằng chứng JAR hoạt động. Smoke test sau packaging giúp phát hiện thiếu dependency, sai profile, cấu hình runner hoặc khác biệt classpath.

Để build tái lập hơn, pin Java distribution/version, dùng Maven/Gradle wrapper, quản lý dependency bằng BOM hoặc lockfile phù hợp, lưu checksum của artifact và giữ lại log build cùng test report.

## 16. Ví dụ pipeline CI hoàn chỉnh

Ví dụ GitHub Actions dùng Java 21 và Maven wrapper:

```yaml
name: customer-cli-ci

on:
  push:
  pull_request:

jobs:
  verify-cli:
    runs-on: ubuntu-latest
    env:
      SPRING_PROFILES_ACTIVE: ci
      SPRING_SHELL_INTERACTIVE_ENABLED: "false"

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: maven

      - name: Build and test
        run: ./mvnw -B clean verify

      - name: Validate fixture
        run: >-
          java -jar target/customer-cli.jar
          customer validate
          --file src/test/resources/customers.csv

      - name: Export report
        run: >-
          java -jar target/customer-cli.jar
          customer report
          --format json > customer-report.json

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: customer-report
          path: customer-report.json
```

Pipeline này chọn non-interactive mode qua environment variable, build/test trước rồi mới chạy command trên JAR. `run` của GitHub Actions sẽ đánh dấu step thất bại khi process trả mã khác `0`; do đó command cần có process exit code đáng tin cậy.

Nếu report là dữ liệu máy đọc, kiểm tra JSON trước khi upload. Có thể thêm bước `jq` hoặc JSON schema validation để bảo đảm artifact không chứa log/banner.

## 17. Chạy trong Docker hoặc container job

Container chạy nền thường không cần cấp pseudo-TTY. Đặt non-interactive mode trong image:

```dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY target/customer-cli.jar /app/customer-cli.jar

ENV SPRING_SHELL_INTERACTIVE_ENABLED=false

ENTRYPOINT ["java", "-jar", "/app/customer-cli.jar"]
CMD ["customer", "validate", "--file", "/data/customers.csv"]
```

Chạy container:

```bash
docker run --rm \
  -v "$PWD/data:/data:ro" \
  customer-cli:latest
```

Không cần `-it` khi container chạy command tự động. Nếu cần override command mặc định:

```bash
docker run --rm \
  -v "$PWD/data:/data:ro" \
  customer-cli:latest \
  customer report --format json
```

Khi chạy trên Kubernetes Job hoặc scheduler tương tự, cấu hình command/args, environment và resource limit tường minh. Chỉ bật TTY khi thực sự có người vận hành kết nối vào container.

## 18. Ví dụ PowerShell cho Windows runner

Trong Windows CI, `$ErrorActionPreference = "Stop"` không thay thế việc kiểm tra exit code của chương trình native. Dùng `$LASTEXITCODE`:

```powershell
$ErrorActionPreference = "Stop"
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "false"
$env:SPRING_PROFILES_ACTIVE = "ci"

java -jar target\customer-cli.jar customer validate --file data\customers.csv
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

java -jar target\customer-cli.jar customer import --file data\customers.csv
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
```

Nếu cần lưu exit code để xử lý riêng, gán `$LASTEXITCODE` ngay sau lệnh Java; command native tiếp theo có thể thay đổi giá trị này.

## 19. Kiểm thử process thật, không chỉ kiểm thử method

Unit test cho command handler không xác nhận được runner đã chọn đúng mode hoặc JAR có trả mã thoát đúng. Tạo integration test chạy artifact trong process con.

Ví dụ JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

class CustomerCliProcessTests {

    @Test
    void validatesFileWithoutInteractiveTerminal() throws Exception {
        Path jar = Path.of("target/customer-cli.jar").toAbsolutePath();
        Path stdout = Path.of("target/cli-stdout.log");
        Path stderr = Path.of("target/cli-stderr.log");

        ProcessBuilder processBuilder = new ProcessBuilder(
                "java", "-jar", jar.toString(),
                "customer", "validate",
                "--file", "src/test/resources/customers.csv")
                .redirectOutput(stdout.toFile())
                .redirectError(stderr.toFile());
        processBuilder.environment().put("SPRING_SHELL_INTERACTIVE_ENABLED", "false");
        Process process = processBuilder.start();

        if (!process.waitFor(30, TimeUnit.SECONDS)) {
            process.destroyForcibly();
            process.waitFor();
            throw new AssertionError("CLI không kết thúc trong thời gian cho phép");
        }
        assertEquals(0, process.exitValue());
        assertTrue(Files.readString(stdout).contains("Đã kiểm tra"));
    }
}
```

Ví dụ dùng file để tách stdout và stderr, tránh trộn payload với diagnostics. Trong test suite thực tế, dùng thư mục tạm và xóa file sau test. Nếu process không kết thúc trong timeout, hủy process trong cleanup để không để lại tiến trình treo.

Các ca process-level nên có:

| Ca kiểm thử | Điều cần xác nhận |
|---|---|
| Command hợp lệ | Output đúng và process trả `0` |
| Thiếu option bắt buộc | Có thông báo usage và mã lỗi theo contract |
| File không tồn tại | Báo lỗi rõ, không treo chờ input |
| Validation thất bại | Mã lỗi khác `0`, không tiếp tục bước import |
| Command không tồn tại | Parse/lookup error có mã thoát được kiểm tra |
| Script có nhiều dòng | Thứ tự thực thi và cách xử lý lỗi đúng với phiên bản đã pin |
| Chạy khi không có TTY | Process tự kết thúc, không chờ prompt |
| Output JSON | stdout parse được, stderr không lẫn vào payload |
| Secret bị thiếu | Job thất bại sớm, không in giá trị secret |

Kiểm tra riêng command parse error và option validation error. Release Spring Shell 4.0.2 đã sửa lỗi non-interactive runner luôn trả `0` trong một trường hợp; issue #1391 sau đó ghi nhận sai exit value khi command không parse được. Với phiên bản đang triển khai, hãy giữ test regression ở cấp process thay vì suy ra từ unit test.

## 20. Logging và chẩn đoán lỗi trong pipeline

Một pipeline cần đủ thông tin để chẩn đoán nhưng không nên làm lộ dữ liệu nhạy cảm.

- Ghi task ID, command name, thời gian chạy và mã lỗi.
- Ghi stack trace vào log khi có exception không mong đợi; thông báo stdout/stderr dành cho người vận hành nên ngắn gọn.
- Không ghi token, password, dữ liệu cá nhân hoặc toàn bộ payload nếu không cần thiết.
- Lưu log và report thành artifact theo retention policy.
- Khi retry, ghi nhận attempt number để phân biệt lần chạy đầu và lần chạy lại.
- Dùng correlation ID để nối log của CLI với API hoặc service bên ngoài.

Spring Shell có `spring.shell.debug.enabled`; tài liệu 4.0.4 mô tả phần stack trace bổ sung của chế độ này cho interactive mode. Trong CI non-interactive, hãy cấu hình logging và error handling của ứng dụng để lưu diagnostics, thay vì phụ thuộc vào debug mode của shell. Tránh ghi payload nhạy cảm hoặc stack trace không cần thiết vào output công khai của job.

## 21. Bài tập thực hành

Xây dựng pipeline cho ứng dụng `customer-cli` với ba command:

1. `customer validate --file ...` kiểm tra cấu trúc và nội dung file.
2. `customer import --file ...` ghi dữ liệu hợp lệ vào hệ thống.
3. `customer report --format json` tạo báo cáo sau khi import.

Yêu cầu:

- Chọn non-interactive mode bằng profile hoặc environment variable.
- Không có prompt hoặc xác nhận thủ công trong pipeline.
- Định nghĩa exit-code contract cho thành công, input lỗi, validation lỗi và lỗi dependency.
- Tách stdout payload khỏi stderr/logging.
- Viết Bash và PowerShell script dừng khi một command thất bại.
- Đóng gói executable JAR và chạy smoke test sau packaging.
- Tạo Docker image không cần `-it` để chạy job.
- Kiểm thử process exit code cho success, invalid options, unknown command và lỗi file.
- Dùng secret store để truyền API token, không ghi token vào script.
- Lưu report và test log thành CI artifacts.

**Kết quả cần nộp:** cấu hình profile CI, command code, pipeline YAML, Bash/PowerShell script, Dockerfile, process integration tests và bảng mã thoát.

## 22. Checklist trước khi đưa CLI vào CI/CD

- [ ] Đã pin phiên bản Spring Shell và Spring Boot.
- [ ] Spring Shell 4 đã đặt `spring.shell.interactive.enabled=false` trong CI.
- [ ] Cấu hình 3.3 đã bật đúng runner cần dùng theo property của thế hệ đó.
- [ ] Mọi input bắt buộc được truyền qua options, file hoặc environment.
- [ ] Không có prompt hoặc confirmation chờ người dùng.
- [ ] Script command có cú pháp và đường dẫn đã được kiểm thử.
- [ ] Đã xác định behavior khi một dòng script thất bại.
- [ ] Command status và JVM process exit code được phân biệt.
- [ ] Process-level tests xác nhận `exitValue()` cho cả success và failure.
- [ ] Parse error và option validation error có test riêng.
- [ ] stdout có contract ổn định; stderr/logging không làm hỏng payload.
- [ ] Output không phụ thuộc màu ANSI, terminal width hoặc cursor state.
- [ ] Secret lấy từ secret store và không xuất hiện trong log/argument/script.
- [ ] Retry có giới hạn và thao tác có side effect được thiết kế idempotent.
- [ ] Build dùng wrapper, version cố định và tạo artifact có thể lưu trữ.
- [ ] JAR hoặc container được smoke test trong môi trường không có TTY.
- [ ] Timeout và cleanup process được cấu hình.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 — Execution](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell 4.0.4 — Script Command](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html)
- [Spring Shell 4.0.4 — Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell 4.0.4 API — `NonInteractiveShellRunner`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html)
- [Spring Shell 4.0.4 API — `ExitStatus`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ExitStatus.html)
- [Spring Shell 3.3 — Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html)
- [Spring Shell 3.3 — Exception Handling](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/index.html)
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell Releases](https://github.com/spring-projects/spring-shell/releases)
- [Spring Shell issue #1391 — NonInteractiveShellRunner exit value on parse errors](https://github.com/spring-projects/spring-shell/issues/1391)
- [Spring Boot 4.0 — Application Exit Codes](https://docs.spring.io/spring-boot/4.0/reference/features/spring-application.html)
