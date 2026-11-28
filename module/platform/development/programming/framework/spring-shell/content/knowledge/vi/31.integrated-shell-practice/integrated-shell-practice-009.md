# Chạy không tương tác với mã thoát nhất quán

Một CLI thường được gọi từ terminal, script triển khai hoặc pipeline CI. Những môi trường này cần biết command đã thành công hay thất bại để quyết định bước tiếp theo. Dòng thông báo trên màn hình không đủ để tự động hóa; tiến trình phải trả mã thoát (exit code) ổn định và có ý nghĩa.

Trong bài thực hành này, chúng ta xây dựng một CLI nhập dữ liệu catalog bằng Spring Shell 3.4.3. Command chạy không tương tác, kiểm tra đầu vào, gọi service nghiệp vụ, hiển thị kết quả và trả mã thoát theo một quy ước thống nhất. Cuối bài, kiểm tra mã thoát thực tế từ Bash, PowerShell và Docker.

## 1. Kết quả cần đạt

Sau bài thực hành, bạn có thể:

- Chạy một command Spring Shell từ application arguments mà không mở prompt.
- Phân biệt kết quả hiển thị với mã thoát của tiến trình.
- Ánh xạ lỗi cú pháp, lỗi dữ liệu và lỗi phụ thuộc bên ngoài sang mã ổn định.
- Trả mã thoát qua Spring Shell và Spring Boot về operating system.
- Viết script kiểm tra mã thoát và dừng khi một bước thất bại.
- Xác minh hành vi bằng cách chạy JAR như một tiến trình độc lập.

## 2. Hiểu luồng thực thi không tương tác

Trong chế độ non-interactive, người gọi truyền tên command và các option ngay khi khởi chạy:

```bash
java -jar catalog-cli.jar catalog import --file fixtures/catalog.csv
```

Spring Shell khởi động application context, chọn `NonInteractiveShellRunner`, phân tích command line, thực thi command rồi kết thúc. Mã thoát của command có ý nghĩa trong chế độ này. Khi chạy interactive, shell vẫn tiếp tục chờ command tiếp theo nên mã thoát của một command không phải mã kết thúc tiến trình tại thời điểm đó.

Từ Spring Shell 3.3.x, chỉ `NonInteractiveShellRunner` được bật mặc định. Có thể bật hoặc tắt runner bằng `spring.shell.interactive.enabled`, `spring.shell.noninteractive.enabled` và `spring.shell.script.enabled`. <Link url="https://docs.spring.io/spring-shell/reference/3.3/execution.html" title="Execution and Shell Runners — Spring Shell 3.3"/>.

## 3. Thiết kế hợp đồng mã thoát

Mã thoát là một phần giao diện công khai của CLI. Hãy định nghĩa một bảng nhỏ, giữ nguyên ý nghĩa qua các phiên bản và ghi rõ trong hướng dẫn vận hành.

| Mã | Ý nghĩa | Ví dụ |
| ---: | --- | --- |
| `0` | Thành công | Catalog được nhập đầy đủ |
| `1` | Lỗi thực thi không dự kiến | Lỗi nội bộ chưa phân loại |
| `2` | Sai cú pháp hoặc option | Thiếu option bắt buộc, option không hợp lệ |
| `3` | Dữ liệu đầu vào không hợp lệ | CSV sai định dạng hoặc thiếu cột |
| `4` | Không tìm thấy tài nguyên | File đầu vào không tồn tại |
| `5` | Phụ thuộc bên ngoài không sẵn sàng | API catalog hoặc database không truy cập được |

Spring Shell có mã mặc định: lỗi phân tích option trả `2`, lỗi chung trả `1`, và command thành công trả `0`. Các mã `3`, `4`, `5` trong bài là quy ước của ứng dụng. <Link url="https://docs.spring.io/spring-shell/reference/3.4/commands/exceptionhandling/mappings.html" title="Exit Code Mappings — Spring Shell 3.4"/>.

Giữ mã trong phạm vi `0–255` để dễ dùng với shell và công cụ Unix. Không dùng mã âm, không tái sử dụng một mã cho nhiều lỗi không liên quan và không trả `0` khi command chỉ in ra một thông báo thất bại.

## 4. Cấu hình runner không tương tác

Trong `application.yml`, khai báo rõ chế độ chạy của CLI:

```yaml
spring:
  main:
    banner-mode: off
  shell:
    interactive:
      enabled: false
    noninteractive:
      enabled: true
    script:
      enabled: false

logging:
  level:
    root: WARN
```

Tắt banner và giảm log khởi động giúp output của command gọn hơn, đặc biệt khi một script cần đọc kết quả. Trong môi trường phát triển, có thể dùng profile khác để bật log chi tiết.

Nếu cần chạy một file chứa nhiều command, có thể bật `spring.shell.script.enabled` và dùng `@file.commands`. Tuy nhiên, với pipeline cần biết chính xác command nào thất bại, nên chạy từng command thành một tiến trình riêng hoặc để script bên ngoài kiểm tra mã thoát sau mỗi bước. Không giả định một file script nội bộ sẽ tự tổng hợp mã thoát theo chính sách riêng của pipeline.

## 5. Khai báo enum mã thoát của ứng dụng

Tạo enum để các tầng nghiệp vụ dùng cùng một bộ mã:

```java
public enum CliExitCode {

    SUCCESS(0),
    GENERAL_ERROR(1),
    USAGE_ERROR(2),
    VALIDATION_ERROR(3),
    NOT_FOUND(4),
    DEPENDENCY_UNAVAILABLE(5);

    private final int value;

    CliExitCode(int value) {
        this.value = value;
    }

    public int value() {
        return value;
    }
}
```

Command thành công không cần ném exception hoặc tự trả enum `SUCCESS`; Spring Shell mặc định trả mã `0` khi không có lỗi. Enum chủ yếu định nghĩa các mã lỗi của ứng dụng.

## 6. Tạo exception mang mã lỗi nghiệp vụ

Không rải các số `3`, `4`, `5` khắp command và service. Tạo một exception riêng mang `CliExitCode`:

```java
public final class CliFailure extends RuntimeException {

    private final CliExitCode exitCode;

    public CliFailure(CliExitCode exitCode, String message) {
        super(message);
        this.exitCode = exitCode;
    }

    public CliExitCode exitCode() {
        return exitCode;
    }

    public static CliFailure invalidData(String message) {
        return new CliFailure(CliExitCode.VALIDATION_ERROR, message);
    }

    public static CliFailure notFound(String message) {
        return new CliFailure(CliExitCode.NOT_FOUND, message);
    }

    public static CliFailure dependencyUnavailable(String message) {
        return new CliFailure(
                CliExitCode.DEPENDENCY_UNAVAILABLE, message);
    }
}
```

Service nghiệp vụ chỉ cần ném exception có ý nghĩa:

```java
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.stereotype.Service;

@Service
public class CatalogImportService {

    private final CatalogRepository catalogRepository;

    public CatalogImportService(CatalogRepository catalogRepository) {
        this.catalogRepository = catalogRepository;
    }

    public ImportSummary importCsv(Path file) {
        if (!Files.exists(file)) {
            throw CliFailure.notFound(
                    "Không tìm thấy file: " + file.getFileName());
        }

        if (!Files.isRegularFile(file)) {
            throw CliFailure.invalidData(
                    "Đường dẫn đầu vào không phải file thường");
        }

        try {
            return catalogRepository.importCsv(file);
        }
        catch (IllegalArgumentException ex) {
            throw CliFailure.invalidData(
                    "Nội dung CSV không hợp lệ: " + ex.getMessage());
        }
        catch (CatalogApiUnavailableException ex) {
            throw CliFailure.dependencyUnavailable(
                    "Dịch vụ catalog hiện không sẵn sàng");
        }
    }
}
```

CatalogRepository, ImportSummary và CatalogApiUnavailableException là kiểu của ứng dụng. Adapter đọc CSV có thể trả ImportSummary và ném CatalogApiUnavailableException khi API đích không truy cập được. Ví dụ hợp đồng của adapter:

```java
public interface CatalogRepository {
    ImportSummary importCsv(Path file)
            throws CatalogApiUnavailableException;
}

public final class CatalogApiUnavailableException extends Exception {
    public CatalogApiUnavailableException(String message) {
        super(message);
    }
}
```

Không bắt mọi Exception rồi chuyển thành lỗi dữ liệu; lỗi lập trình hoặc lỗi chưa biết phải giữ là lỗi chung để Spring Shell xử lý với mã 1.

Ví dụ kiểu kết quả:

```java
public record ImportSummary(int importedCount) {
}
```

## 7. Ánh xạ exception thành thông báo và mã thoát

Trong Spring Shell 3.4, phương thức `@ExceptionResolver` trong một lớp `@ShellComponent` có thể trả `CommandHandlingResult`. Kết quả này chứa thông báo hiển thị và mã thoát:

```java
import java.nio.file.Path;

import org.springframework.shell.command.CommandHandlingResult;
import org.springframework.shell.command.annotation.ExceptionResolver;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class CatalogCommands {

    private final CatalogImportService importService;

    public CatalogCommands(CatalogImportService importService) {
        this.importService = importService;
    }

    @ShellMethod(
            key = "catalog import",
            value = "Nhập catalog từ file CSV")
    public String importCatalog(
            @ShellOption(value = "--file") String file) {

        ImportSummary summary =
                importService.importCsv(Path.of(file));
        return "Đã nhập " + summary.importedCount() + " bản ghi.";
    }

    @ExceptionResolver
    public CommandHandlingResult handleCliFailure(CliFailure failure) {
        return CommandHandlingResult.of(
                "Lỗi: " + failure.getMessage(),
                failure.exitCode().value());
    }
}
```

`ImportSummary.importedCount()` là accessor của record hoặc DTO do ứng dụng định nghĩa.

Một số điểm cần nhớ:

- Giá trị `String` do command trả về là output hiển thị, không phải mã thoát.
- `CommandHandlingResult.of(message, code)` cung cấp cả thông báo và mã thoát.
- Một `@ExceptionResolver` trả `String` đơn thuần dùng mã mặc định `1`; muốn trả mã khác, dùng `CommandHandlingResult` hoặc `@ExitCode`.
- Resolver ở lớp command xử lý exception của các method trong component đó. Exception không được xử lý sẽ đi tiếp qua resolver mặc định.

Tham khảo [Exception Resolving](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/resolving.html) và [@ExceptionResolver](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/annotation.html).

## 8. Đưa mã thoát ra khỏi JVM

Spring Shell tích hợp cơ chế mã thoát với Spring Boot. Khi khởi động ứng dụng như một CLI đóng gói, lấy mã từ `SpringApplication.exit(context)` rồi trả về operating system bằng `System.exit(...)`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class CatalogCliApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(CatalogCliApplication.class, args);

        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
```

Spring Boot thu thập mã từ `ExitCodeGenerator` và các exception được ánh xạ. `SpringApplication.exit(context)` thực hiện quy trình kết thúc context và trả mã; `System.exit(exitCode)` chuyển mã đó thành trạng thái tiến trình mà shell hoặc CI quan sát được. <Link url="https://docs.spring.io/spring-boot/3.4/reference/features/spring-application.html" title="Application Exit — Spring Boot 3.4"/>.

Không gọi `System.exit()` từ command hoặc service. Nếu command gọi trực tiếp, nó có thể kết thúc JVM trước khi Spring đóng context, giải phóng tài nguyên hoặc flush log. Giữ việc thoát tiến trình tại entry point `main`.

## 9. Chạy một command trực tiếp

Sau khi đóng gói JAR, chạy command với các application arguments đặt sau tên JAR:

```bash
java -jar catalog-cli.jar catalog import --file fixtures/catalog.csv
```

Ví dụ PowerShell:

```powershell
java -jar .\catalog-cli.jar catalog import --file .\fixtures\catalog.csv
$exitCode = $LASTEXITCODE
Write-Host "CLI exit code: $exitCode"
```

Để chọn profile hoặc cấu hình Spring Boot, ưu tiên dùng biến môi trường hoặc file cấu hình. Giữ application arguments sau JAR rõ ràng để Spring Shell nhận diện command và option.

## 10. Kiểm tra mã thoát trong Bash

Trong Bash, biến `$?` chứa mã thoát của lệnh vừa chạy. Phải đọc ngay sau command cần kiểm tra vì một lệnh tiếp theo sẽ thay đổi giá trị đó.

Ví dụ:

```bash
java -jar catalog-cli.jar catalog import --file fixtures/catalog.csv
exit_code=$?

if [ "$exit_code" -eq 0 ]; then
  echo "Import completed"
else
  echo "Import failed with exit code $exit_code" >&2
  exit "$exit_code"
fi
```

Có thể viết helper để kiểm tra nhiều trường hợp:

```bash
#!/usr/bin/env bash
set -u

expect_code() {
  expected="$1"
  shift

  if java -jar catalog-cli.jar "$@"; then
    actual=0
  else
    actual=$?
  fi

  if [ "$actual" -ne "$expected" ]; then
    echo "Expected $expected, received $actual: $*" >&2
    exit 99
  fi
}

expect_code 0 catalog import --file fixtures/valid.csv
expect_code 3 catalog import --file fixtures/invalid.csv
expect_code 4 catalog import --file fixtures/missing.csv
expect_code 2 catalog import --unknown-option
```

Script trả `99` nếu kết quả thực tế không khớp kỳ vọng. Đây là mã của script kiểm thử, không phải mã lỗi nghiệp vụ của CLI.

## 11. Kiểm tra mã thoát trong PowerShell

PowerShell lưu mã thoát của tiến trình native gần nhất trong `$LASTEXITCODE`. Hãy chép giá trị này ngay sau khi chạy Java:

```powershell
java -jar .\catalog-cli.jar catalog import --file .\fixtures\catalog.csv
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Error "Catalog import failed with code $exitCode"
    exit $exitCode
}

Write-Host "Catalog import completed"
```

Khi chạy nhiều bước, kiểm tra `$LASTEXITCODE` sau từng tiến trình. Đừng kiểm tra sau một lệnh PowerShell khác đã chạy, vì khi đó giá trị có thể không còn thuộc command Spring Shell cần đánh giá.

## 12. Chạy trong Docker và pipeline CI

Với Docker image dùng Java làm entry point:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/catalog-cli.jar /app/catalog-cli.jar
ENTRYPOINT ["java", "-jar", "/app/catalog-cli.jar"]
```

Chạy command:

```bash
docker run --rm \
  -v "$PWD/fixtures:/data:ro" \
  catalog-cli:latest \
  catalog import --file /data/catalog.csv
```

`docker run` trả mã thoát của tiến trình chính trong container. Vì vậy, nếu Java trả mã `4`, script gọi Docker cũng có thể nhận mã `4`.

Trong pipeline CI, dùng chế độ non-interactive và kiểm tra mã sau mỗi bước:

```bash
set -euo pipefail

java -jar catalog-cli.jar catalog validate --file fixtures/catalog.csv
java -jar catalog-cli.jar catalog import --file fixtures/catalog.csv
java -jar catalog-cli.jar catalog report
```

Với `set -e`, script dừng khi một command trả mã khác `0`. Điều này giúp pipeline không chạy bước tiếp theo khi dữ liệu chưa được xác thực hoặc nhập thất bại.

Không bật interactive runner trong job không có TTY và không yêu cầu người dùng xác nhận qua prompt. Nếu cần nhiều bước, hãy để script CI điều phối từng tiến trình và nhận mã thoát của từng bước.

## 13. Giữ output rõ ràng cho người và máy

Output của command và mã thoát phục vụ hai mục đích khác nhau. Người vận hành cần thông báo dễ hiểu; script cần mã máy đọc được.

| Tình huống | Output gợi ý | Exit code |
| --- | --- | ---: |
| Nhập thành công | `Đã nhập 12 bản ghi.` | `0` |
| CSV sai cấu trúc | `Lỗi: Thiếu cột product_id.` | `3` |
| Không tìm thấy file | `Lỗi: Không tìm thấy file catalog.csv.` | `4` |
| API catalog không sẵn sàng | `Lỗi: Dịch vụ catalog hiện không sẵn sàng.` | `5` |
| Lỗi nội bộ | Thông báo tổng quát và correlation ID | `1` |

Không đưa stack trace, credential hoặc URL có token vào output công khai. Ghi chi tiết kỹ thuật vào log với correlation ID để người vận hành tra cứu. Nếu command hỗ trợ `--output=json`, giữ stdout là JSON hợp lệ và đưa thông báo chẩn đoán sang stderr theo thiết kế của result handler.

## 14. Kiểm thử mã thoát bằng tiến trình thật

Unit test cho service không đủ để chứng minh operating system nhận đúng mã. Cần chạy JAR trong process riêng và đọc `Process.exitValue()`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

class CatalogCliProcessTests {

    private int runCli(String... arguments)
            throws IOException, InterruptedException {

        var command = new java.util.ArrayList<String>();
        command.add("java");
        command.add("-jar");
        command.add("target/catalog-cli.jar");
        command.addAll(java.util.List.of(arguments));

        Process process = new ProcessBuilder(command)
                .redirectOutput(ProcessBuilder.Redirect.INHERIT)
                .redirectError(ProcessBuilder.Redirect.INHERIT)
                .start();

        boolean finished = process.waitFor(30, TimeUnit.SECONDS);
        if (!finished) {
            process.destroyForcibly();
            throw new AssertionError("CLI did not finish within 30 seconds");
        }
        return process.exitValue();
    }

    @Test
    void successfulImportReturnsZero() throws Exception {
        assertEquals(0, runCli(
                "catalog", "import",
                "--file", "fixtures/valid.csv"));
    }

    @Test
    void missingFileReturnsFour() throws Exception {
        assertEquals(4, runCli(
                "catalog", "import",
                "--file", "fixtures/missing.csv"));
    }
}
```

Đoạn test giả định JAR đã được build và file fixture tồn tại trong working directory của test. Trong CI, thêm bước đóng gói trước khi chạy process test. Bổ sung test cho mã `2`, `3`, `5` và lỗi chung `1`.

Không chỉ kiểm tra exit value. Hãy xác nhận thông báo lỗi có thể hiểu được, command không bị treo chờ prompt và process kết thúc trong giới hạn thời gian.

## 15. Kiểm tra tương thích và runner

Với Spring Shell 3.4.3, dùng annotation model `@ShellComponent`, `@ShellMethod`, `@ShellOption`, `@ExceptionResolver` và `CommandHandlingResult`. Spring Shell 4 đã thay đổi command programming model và cơ chế exception/exit status; không sao chép trực tiếp `ExitStatusExceptionMapper` của v4 vào ứng dụng 3.x. <Link url="https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide" title="Spring Shell 4 Migration Guide"/>.

Nếu command chạy trong interactive shell, exception resolver vẫn hiển thị lỗi nhưng mã thoát của command không kết thúc tiến trình ngay. Kiểm thử mã thoát phải chạy với non-interactive runner. <Link url="https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/index.html" title="Exception Handling — Spring Shell 3.3"/>.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Command in thông báo lỗi nhưng process trả `0` | Exception bị xử lý như kết quả thành công hoặc mã không được chuyển vào `CommandHandlingResult` | Trả `CommandHandlingResult.of(message, code)` từ resolver |
| Mọi lỗi đều trả `1` | Resolver trả `String` hoặc lỗi chưa được ánh xạ | Trả `CommandHandlingResult` với mã ứng dụng |
| Sai option trả mã khác `2` | Parser error bị bọc hoặc bị resolver tùy chỉnh xử lý | Giữ parser resolver mặc định và test option sai |
| `System.exit` không nhận mã command | Chưa lấy exit code qua Spring Boot hoặc entry point không gọi `System.exit` | Dùng `SpringApplication.exit(context)` rồi trả mã cho JVM |
| Script chạy tiếp sau command thất bại | Script không kiểm tra exit code | Dùng `set -e` hoặc kiểm tra `$LASTEXITCODE` |
| CI treo chờ prompt | Interactive runner được bật hoặc command yêu cầu input | Chạy non-interactive và truyền đầy đủ option |
| Docker luôn trả `0` | Entry point che mất mã của tiến trình Java | Để Java là tiến trình chính, không nuốt exit status trong wrapper |
| Mã lỗi thay đổi giữa các phiên bản | Không có hợp đồng exit code được tài liệu hóa | Dùng enum, bảng mã và process test |

## 17. Bài thực hành tổng hợp

Hoàn thiện một CLI nhập catalog có command `catalog validate`, `catalog import` và `catalog report`:

1. Cấu hình `spring.shell.interactive.enabled=false` và `spring.shell.noninteractive.enabled=true`.
2. Tạo enum `CliExitCode` với các mã từ `0` đến `5`.
3. Tạo `CliFailure` để service ném lỗi dữ liệu, không tìm thấy file hoặc phụ thuộc không sẵn sàng.
4. Viết `CatalogImportService` kiểm tra file và thực hiện nhập dữ liệu.
5. Tạo command bằng `@ShellMethod` và option `--file`.
6. Thêm `@ExceptionResolver` trả `CommandHandlingResult.of(message, code)`.
7. Cấu hình `main` dùng `SpringApplication.exit(context)` và `System.exit(exitCode)`.
8. Đóng gói JAR rồi chạy command thành công và các trường hợp lỗi.
9. Viết Bash và PowerShell script kiểm tra từng mã thoát.
10. Chạy Docker container và một pipeline CI không có TTY.
11. Viết process test cho ít nhất bốn mã: `0`, `2`, `3` và `4`.
12. Ghi hợp đồng mã thoát vào hướng dẫn vận hành của sản phẩm sau khi bài thực hành hoàn tất.

## 18. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Non-interactive runner | Chạy command trực tiếp từ application arguments và không mở prompt |
| Exit code contract | Có bảng mã ổn định, dễ hiểu và được tài liệu hóa |
| Exception mapping | Phân biệt parser error, lỗi nghiệp vụ và lỗi chung |
| Spring Shell | Dùng `CommandHandlingResult` để trả message và code |
| Spring Boot | Đưa mã thoát từ context về operating system |
| Bash/PowerShell | Script đọc đúng mã của tiến trình Java |
| Docker/CI | Container và pipeline nhận đúng mã thất bại |
| Process testing | Có kiểm thử JAR thật trong process riêng |
| Output | Thông báo rõ ràng, không lộ stack trace hoặc secret |
| Reliability | Command không phụ thuộc prompt và không nuốt lỗi |

## Tài liệu tham khảo

- [Spring Shell 3.3 — Execution and Shell Runners](https://docs.spring.io/spring-shell/reference/3.3/execution.html)
- [Spring Shell 3.4 — Exit Code Mappings](https://docs.spring.io/spring-shell/reference/3.4/commands/exceptionhandling/mappings.html)
- [Spring Shell 3.3 — Exception Resolving](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/resolving.html)
- [Spring Shell 3.3 — @ExceptionResolver](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/annotation.html)
- [Spring Boot 3.4 — Application Exit](https://docs.spring.io/spring-boot/3.4/reference/features/spring-application.html)
- [Spring Boot 3.4 — ExitCodeGenerator API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/ExitCodeGenerator.html)
- [Spring Shell — v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
