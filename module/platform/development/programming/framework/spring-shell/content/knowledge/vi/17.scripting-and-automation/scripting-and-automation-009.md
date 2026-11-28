# Dùng mã thoát để phối hợp với shell hệ điều hành hoặc CI

Khi một command chạy trong script hoặc pipeline CI, hệ thống gọi cần biết thao tác thành công hay thất bại mà không phải đọc và phân tích toàn bộ thông báo trên màn hình. Mã thoát (exit code) cung cấp tín hiệu ngắn gọn cho shell hệ điều hành, script và công cụ tự động hóa.

Spring Shell 4.x biểu diễn kết quả của một lần thực thi bằng `ExitStatus`. Trong chế độ không tương tác, `NonInteractiveShellRunner` chạy command hoặc script rồi kết thúc. Để phối hợp đúng với hệ điều hành, cần hiểu hai lớp kết quả: trạng thái của command trong Spring Shell và mã thoát của tiến trình JVM. Hai lớp này liên quan với nhau nhưng không phải cùng một giá trị.

## 1. Mã thoát là tín hiệu cho tiến trình gọi

Một tiến trình trả về một số nguyên khi kết thúc. Theo quy ước phổ biến của Unix và nhiều công cụ CI:

- `0` biểu thị thao tác thành công.
- Giá trị khác `0` biểu thị có lỗi hoặc kết quả cần xử lý đặc biệt.

Ví dụ, một pipeline có thể chạy bước kiểm tra trước khi triển khai:

~~~text
validate-config
deploy
notify
~~~

Nếu `validate-config` trả mã `0`, script có thể tiếp tục. Nếu command trả mã khác `0`, script hoặc CI có thể dừng pipeline, đánh dấu job thất bại hoặc chạy nhánh xử lý lỗi.

Mã thoát không thay thế thông báo lỗi. Thông báo giải thích điều gì đã xảy ra; mã thoát cho tiến trình gọi biết nên tiếp tục hay dừng.

## 2. Thiết kế quy ước mã thoát cho CLI

Nên thống nhất một bảng mã nhỏ, ổn định và được dùng giống nhau giữa các command:

| Mã | Ý nghĩa gợi ý | Hành động của script/CI |
|---:|---|---|
| `0` | Thành công | Tiếp tục bước tiếp theo |
| `1` | Lỗi thực thi chưa phân loại | Dừng và báo lỗi |
| `2` | Đầu vào hoặc cú pháp không hợp lệ | Sửa tham số hoặc cấu hình |
| `3` | Không đủ quyền | Kiểm tra tài khoản hoặc quyền truy cập |
| `4` | Không kết nối được dịch vụ phụ thuộc | Kiểm tra dịch vụ và thử lại theo chính sách |
| `5` | Không tìm thấy tài nguyên | Kiểm tra tên hoặc đường dẫn |

Đây là quy ước của ứng dụng, không phải bảng mã bắt buộc của Spring Shell. Chọn các mã nhỏ, dễ nhớ và ghi lại trong tài liệu CLI. Tránh thay đổi ý nghĩa của một mã giữa các phiên bản nếu script bên ngoài đang phụ thuộc vào nó.

Trong môi trường Unix, một số giá trị có ý nghĩa đặc biệt với shell hoặc được dùng để biểu diễn tín hiệu. Để giữ tính tương thích, nên chọn các mã lỗi nhỏ trong khoảng `1` đến `125`, đồng thời dành riêng `0` cho thành công.

## 3. ExitStatus trong Spring Shell 4.x

Spring Shell 4.x dùng record `ExitStatus` trong package `org.springframework.shell.core.command`:

~~~java
import org.springframework.shell.core.command.ExitStatus;
~~~

Record này chứa hai thành phần:

| Thành phần | Kiểu | Ý nghĩa |
|---|---|---|
| `code` | `int` | Mã trạng thái của lần thực thi command |
| `description` | `String` | Mô tả trạng thái hoặc lý do lỗi |

Spring Shell cung cấp các trạng thái chuẩn:

| Hằng số | Mục đích |
|---|---|
| `ExitStatus.OK` | Command thực thi thành công |
| `ExitStatus.USAGE_ERROR` | Lỗi cách gọi hoặc dữ liệu đầu vào |
| `ExitStatus.AVAILABILITY_ERROR` | Command chưa khả dụng trong trạng thái hiện tại |
| `ExitStatus.EXECUTION_ERROR` | Lỗi khi thực thi command |

Khi cần mã riêng cho ứng dụng, có thể tạo trạng thái bằng constructor:

~~~java
new ExitStatus(2, "invalid input file")
new ExitStatus(4, "remote service is unavailable")
~~~

Các mã tùy chỉnh phải tuân theo quy ước mà CLI công bố. Không nên để mỗi command tự chọn số mà không có tài liệu chung.

## 4. Trả ExitStatus trực tiếp từ command lập trình

Với command được xây dựng bằng API lập trình, lớp `AbstractCommand` cho phép trả trực tiếp `ExitStatus` từ `doExecute`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;

@Configuration
class HealthCommandConfiguration {

    @Bean
    Command checkRemoteService(RemoteHealthService healthService) {
        return new AbstractCommand(
                "check-remote",
                "Check the availability of the remote service") {

            @Override
            public ExitStatus doExecute(CommandContext context) {
                if (healthService.isHealthy()) {
                    println("Remote service is healthy.", context);
                    return ExitStatus.OK;
                }

                println("Remote service is unavailable.", context);
                return new ExitStatus(4, "remote service is unavailable");
            }
        };
    }
}
~~~

`doExecute` quyết định trạng thái cuối cùng. Khi service hoạt động, command trả `ExitStatus.OK`. Khi service không sẵn sàng, command trả mã `4` cùng mô tả. `NonInteractiveShellRunner` nhận trạng thái này để quyết định tiến trình có tiếp tục bình thường hay phát sinh lỗi thực thi.

Command được khai báo bằng `@Command` thường trả về dữ liệu để Spring Shell hiển thị hoặc ném exception khi có lỗi. Với kiểu command này, có thể dùng `ExitStatusExceptionMapper` để ánh xạ exception thành trạng thái.

## 5. Ánh xạ exception thành ExitStatus

`ExitStatusExceptionMapper` của Spring Shell là functional interface nhận một `Exception` và trả về `ExitStatus`. Có thể khai báo mapper như một Spring bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
class CommandExitStatusConfiguration {

    @Bean
    ExitStatusExceptionMapper importExitStatusMapper() {
        return exception -> {
            if (exception instanceof InvalidInputException) {
                return new ExitStatus(2, "invalid input");
            }
            if (exception instanceof AccessDeniedException) {
                return new ExitStatus(3, "access denied");
            }
            if (exception instanceof RemoteServiceException) {
                return new ExitStatus(4, "remote service is unavailable");
            }
            return ExitStatus.EXECUTION_ERROR;
        };
    }
}
~~~

Command annotation tham chiếu mapper bằng tên bean:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ImportCommands {

    private final ImportService importService;

    ImportCommands(ImportService importService) {
        this.importService = importService;
    }

    @Command(
            name = "import-users",
            description = "Import users from a file",
            exitStatusExceptionMapper = "importExitStatusMapper"
    )
    public String importUsers(
            @Option(
                    longName = "file",
                    required = true,
                    description = "Path to the input file"
            )
            String file) {

        importService.importUsers(file);
        return "Users imported successfully.";
    }
}
~~~

Khi `ImportService` ném `InvalidInputException`, mapper trả `ExitStatus` có mã `2`. Khi service ném `AccessDeniedException`, mapper trả mã `3`. Các exception không được xử lý riêng sẽ nhận `ExitStatus.EXECUTION_ERROR`.

Có thể gắn mapper trực tiếp trong mô hình lập trình bằng `Command.Builder.exitStatusExceptionMapper(...)`. Cách đăng ký theo bean name trong `@Command` phù hợp với command annotation; builder phù hợp với command được tạo bằng code.

## 6. Phân biệt hai loại mapper

Đây là phần quan trọng khi tích hợp Spring Shell với hệ điều hành:

| Mapper | Package | Đầu vào | Đầu ra | Phạm vi |
|---|---|---|---|---|
| `ExitStatusExceptionMapper` | `org.springframework.shell.core.command.exit` | `Exception` trong command | `ExitStatus` | Trạng thái command |
| `ExitCodeExceptionMapper` | `org.springframework.boot` | `Throwable` làm ứng dụng kết thúc do lỗi | `int` | Mã thoát của tiến trình Spring Boot |

Hai interface có tên gần giống nhau nhưng giải quyết hai tầng khác nhau.

`ExitStatusExceptionMapper` giúp Spring Shell phân loại lỗi của command và tạo mô tả dễ hiểu. Trong chế độ không tương tác, khi command trả trạng thái khác `OK`, runner tạo `CommandExecutionException` mang mã lỗi đó.

`ExitCodeExceptionMapper` của Spring Boot nhận exception làm ứng dụng kết thúc và ánh xạ sang mã thoát tiến trình. Đây là nơi có thể lấy mã từ `CommandExecutionException` để hệ điều hành hoặc CI nhận được đúng kết quả.

Tài liệu Spring Shell 4.0.4 nhấn mạnh rằng trạng thái command khác với mã thoát JVM. Chỉ cấu hình mapper của Spring Shell không có nghĩa là đã cấu hình mã thoát của tiến trình.

## 7. Chuyển mã command sang mã tiến trình trong Spring Boot

Khi ứng dụng chạy bằng `NonInteractiveShellRunner`, lỗi command được chuyển thành `CommandExecutionException`. Exception này cung cấp `getExitCode()`. Có thể khai báo mapper của Spring Boot để giữ nguyên mã đó:

~~~java
import org.springframework.boot.ExitCodeExceptionMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.CommandExecutionException;

@Configuration
class ProcessExitCodeConfiguration {

    @Bean
    ExitCodeExceptionMapper shellProcessExitCodeMapper() {
        return exception -> {
            Throwable current = exception;

            while (current != null) {
                if (current instanceof CommandExecutionException commandException) {
                    return commandException.getExitCode();
                }
                current = current.getCause();
            }

            return 1;
        };
    }
}
~~~

Mapper đi qua chuỗi cause vì Spring Boot có thể bọc exception trong một exception khác khi runner thất bại. Nếu tìm thấy `CommandExecutionException`, mapper trả đúng mã mà Spring Shell đã gắn cho command. Nếu lỗi không đến từ command, ví dụ lỗi khởi động hoặc lỗi hạ tầng khác, mapper trả `1` theo quy ước chung của ứng dụng.

Spring Boot sử dụng `ExitCodeExceptionMapper` khi `SpringApplication` xử lý lỗi làm ứng dụng dừng. Trong luồng khởi động không tương tác, `NonInteractiveShellRunner` chạy như một `ApplicationRunner`; lỗi command được ném ra ngoài runner và có thể được Spring Boot ánh xạ thành mã tiến trình.

Đừng nhầm mapper Spring Boot ở ví dụ này với mapper của Spring Shell ở phần trước. Một mapper tạo `ExitStatus`; mapper còn lại tạo số nguyên cho tiến trình.

## 8. Chọn chế độ không tương tác khi chạy command một lần

Trong Spring Shell 4.x, interactive mode được bật mặc định. Khi ứng dụng cần chạy một command từ tham số tiến trình rồi thoát, đặt:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
~~~

Có thể đặt thuộc tính này trong cấu hình dành cho môi trường batch/CI hoặc thông qua biến môi trường:

~~~text
SPRING_SHELL_INTERACTIVE_ENABLED=false
~~~

Trong interactive mode, command có thể trả trạng thái lỗi nhưng phiên shell vẫn tiếp tục để người dùng nhập lệnh khác. Mã thoát của tiến trình chỉ có ý nghĩa khi ứng dụng kết thúc. Vì vậy, script và CI nên chạy ứng dụng ở chế độ không tương tác thay vì mở một REPL rồi chờ người dùng thoát.

Khi chạy ở chế độ không tương tác, runner xử lý một command hoặc script rồi kết thúc. Ví dụ:

~~~text
java -jar user-admin.jar import-users --file=users.csv
~~~

Lệnh trên giả định ứng dụng đã được cấu hình `spring.shell.interactive.enabled=false`. Nếu command thành công, tiến trình trả mã `0`. Nếu command trả trạng thái lỗi, runner chuyển trạng thái đó thành lỗi thực thi và Spring Boot có thể dùng mapper tiến trình để trả mã khác `0`.

## 9. Đọc mã thoát trong shell hệ điều hành

Sau khi tiến trình kết thúc, shell hệ điều hành cung cấp mã thoát để script quyết định bước tiếp theo.

### Bash hoặc shell tương thích POSIX

`$?` chứa mã của lệnh vừa chạy. Hãy đọc ngay sau command:

~~~bash
java -jar user-admin.jar import-users --file=users.csv
status=$?

if [ "$status" -eq 0 ]; then
    echo "Import completed"
else
    echo "Import failed with exit code $status"
    exit "$status"
fi
~~~

Nếu command nằm trong pipeline, Bash mặc định thường lấy mã của lệnh cuối cùng trong pipeline. Dùng `set -o pipefail` khi cần pipeline thất bại nếu bất kỳ lệnh thành phần nào thất bại:

~~~bash
set -o pipefail
java -jar user-admin.jar export --format=csv | gzip > users.csv.gz
~~~

### Windows PowerShell

Với tiến trình native như `java.exe`, `$LASTEXITCODE` giữ mã thoát của tiến trình:

~~~powershell
java -jar user-admin.jar import-users --file=users.csv
$status = $LASTEXITCODE

if ($status -eq 0) {
    Write-Host "Import completed"
}
else {
    Write-Error "Import failed with exit code $status"
    exit $status
}
~~~

`$?` trong PowerShell là trạng thái thành công/thất bại của câu lệnh gần nhất, còn `$LASTEXITCODE` là số nguyên mà chương trình native trả về. Khi cần chuyển nguyên mã của Java sang bước tiếp theo, hãy lưu `$LASTEXITCODE` ngay sau khi chạy tiến trình.

### Windows Command Prompt

Trong `cmd.exe`, `%ERRORLEVEL%` chứa mã thoát của chương trình vừa chạy:

~~~bat
java -jar user-admin.jar import-users --file=users.csv
if errorlevel 1 exit /b %ERRORLEVEL%
~~~

## 10. Dùng mã thoát trong CI

Hầu hết CI runner xem mã `0` là thành công và mã khác `0` là thất bại. Vì vậy, command có thể được đặt trực tiếp trong một step:

~~~yaml
steps:
  - name: Import users
    run: java -jar user-admin.jar import-users --file=users.csv
~~~

Nếu ứng dụng chạy đúng chế độ không tương tác và truyền mã thoát đúng, CI tự đánh dấu step thất bại khi command trả mã lỗi.

Không nên bắt lỗi rồi chỉ in thông báo mà vẫn trả mã `0`. Ví dụ script sau làm mất tín hiệu lỗi:

~~~bash
java -jar user-admin.jar import-users --file=missing.csv || echo "Import failed"
~~~

Vì `echo` thành công, trạng thái cuối cùng của dòng có thể là `0`. Nếu cần ghi log rồi giữ nguyên lỗi, lưu mã trước khi ghi log và trả lại mã đó:

~~~bash
java -jar user-admin.jar import-users --file=missing.csv
status=$?

if [ "$status" -ne 0 ]; then
    echo "Import failed; stopping pipeline"
    exit "$status"
fi
~~~

Trong workflow nhiều bước, nên để command trả mã lỗi ngay khi có lỗi. Các bước tiếp theo chỉ chạy khi step trước thành công, trừ khi pipeline được cấu hình rõ ràng để tiếp tục sau lỗi.

## 11. Script chứa nhiều command

`NonInteractiveShellRunner` có thể nhận một script bằng cách đặt ký tự `@` trước đường dẫn file:

~~~text
java -jar user-admin.jar @nightly-import.shell
~~~

Ví dụ nội dung script:

~~~text
check-connection
import-users --file=users.csv
rebuild-index
~~~

Runner thực thi từng dòng theo thứ tự. Khi một command trả trạng thái khác `OK`, runner báo lỗi và dừng các command tiếp theo trong script. Thiết kế script theo thứ tự phụ thuộc: kiểm tra môi trường trước, nhập dữ liệu sau, rồi mới chạy tác vụ tổng hợp.

Lỗi cú pháp của dòng script, file script không tồn tại và lỗi đọc file cũng cần được kiểm tra ở cấp tiến trình. Các trường hợp này xảy ra trước hoặc ngoài phần thực thi command nên không nhất thiết đi qua `ExitStatusExceptionMapper` của command.

## 12. Lưu ý phiên bản và lỗi phân tích cú pháp

Spring Shell 4.0.2 sửa lỗi trong đó `NonInteractiveShellRunner` luôn trả mã `0` khi command thực thi thất bại. Vì vậy, khi cần dựa vào mã lỗi của command, hãy dùng bản 4.0.2 trở lên và kiểm tra phiên bản thực tế được đóng gói.

Có một trường hợp khác cần chú ý: trong Spring Shell 4.0.4, issue #1391 ghi nhận rằng lỗi phân tích cú pháp command, file script không mở được hoặc lỗi đọc script có thể chỉ được ghi log rồi runner kết thúc bình thường với mã `0`. PR #1393 đề xuất chuyển các trường hợp này thành `CommandExecutionException`, nhưng tại thời điểm kiểm tra PR vẫn chưa được triển khai trong bản phát hành. Vì vậy, không suy ra rằng mọi lỗi cú pháp đều chắc chắn trả mã khác `0` chỉ từ việc mapper command đã được cấu hình.

Đối với CLI dùng trong CI, hãy kiểm thử riêng:

- Command chạy thành công.
- Command thực thi nhưng nghiệp vụ thất bại.
- Option/argument sai kiểu hoặc thiếu tham số.
- Dòng command không phân tích được.
- File script không tồn tại.
- Một dòng trong script không hợp lệ.

Nếu phiên bản đang dùng trả `0` cho lỗi parsing, có thể kiểm tra cú pháp trước trong script, nâng lên bản đã có bản sửa tương ứng khi phát hành, hoặc bổ sung lớp launcher/validation ở cấp ứng dụng. Đừng để pipeline coi một lệnh sai cú pháp là thành công.

## 13. Kiểm thử mã thoát ở hai cấp

`ShellTestClient` hữu ích để kiểm thử hành vi command bên trong ứng dụng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellScreen;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@ShellTest
@ContextConfiguration(classes = ImportCommands.class)
class ImportCommandsTests {

    @Autowired
    ShellTestClient client;

    @MockitoBean
    ImportService importService;

    @Test
    void printsSuccessMessage() throws Exception {
        ShellScreen screen = client.sendCommand(
                "import-users --file=users.csv");

        ShellAssertions.assertThat(screen)
                .containsText("Users imported successfully");
    }
}
~~~

Test này kiểm tra nội dung command và thông báo hiển thị. Nó không thay thế kiểm thử mã thoát của tiến trình JVM.

Để xác nhận mã mà hệ điều hành nhận được, chạy ứng dụng đã đóng gói bằng một tiến trình con:

~~~java
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class ImportProcessExitCodeTests {

    @Test
    void returnsZeroWhenImportSucceeds() throws Exception {
        ProcessBuilder builder = new ProcessBuilder(
                "java",
                "-jar",
                "user-admin.jar",
                "import-users",
                "--file=users.csv"
        );
        builder.environment().put(
                "SPRING_SHELL_INTERACTIVE_ENABLED", "false");
        Process process = builder.redirectErrorStream(true).start();

        String output = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8
        );
        int exitCode = process.waitFor();

        assertThat(exitCode).isEqualTo(0);
        assertThat(output).contains("Users imported successfully");
    }
}
~~~

Test này giả định artifact đã được build và nằm tại đường dẫn được truyền cho `ProcessBuilder`. Có thể thêm test tương tự cho mã lỗi nghiệp vụ và lỗi parsing.

Với trường hợp lỗi, cấu hình test để service ném exception đã được mapper phân loại, rồi xác nhận tiến trình trả đúng mã đã quy ước. Nên có thêm test cho lỗi parsing và script vì chúng đi qua nhánh xử lý khác với lỗi trong command.

## 14. Quy ước mã thoát nên được duy trì như hợp đồng CLI

Khi một script bên ngoài phụ thuộc vào mã lỗi, mã đó trở thành một phần giao diện công khai của ứng dụng:

- Công bố bảng mã trong tài liệu CLI.
- Giữ ổn định ý nghĩa của mã qua các lần phát hành.
- Dùng cùng một mã cho cùng loại lỗi giữa các command.
- Ghi thông tin chi tiết vào output hoặc log, không cố nhồi toàn bộ nội dung vào mã số.
- Kiểm thử cả mã thành công lẫn mã thất bại ở cấp tiến trình.
- Không trả mã thành công sau khi đã bắt lỗi và chỉ in cảnh báo.

Một quy ước nhỏ, rõ ràng giúp shell script và CI xử lý lỗi nhất quán mà không cần phân tích văn bản thông báo.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| CI luôn thành công dù command báo lỗi | Chỉ kiểm tra output hoặc script đã nuốt mã lỗi | Kiểm tra mã tiến trình và trả lại mã khác 0 |
| Command có `ExitStatus` lỗi nhưng tiến trình không có mã tương ứng | Chỉ cấu hình `ExitStatusExceptionMapper` | Bổ sung mapping ở cấp Spring Boot và kiểm thử tiến trình |
| Mọi lỗi đều thành mã 1 | Dùng một mã chung cho tất cả exception | Ánh xạ loại lỗi sang mã đã công bố |
| Không lấy được mã trong PowerShell | Đọc `$?` thay vì `$LASTEXITCODE` | Lưu `$LASTEXITCODE` ngay sau tiến trình native |
| Pipeline Bash che mất lỗi | Không bật `pipefail` hoặc lấy mã của lệnh cuối | Dùng `set -o pipefail` và kiểm tra mã |
| Lỗi command trong script không chạy các dòng sau | Runner dừng script khi command trả trạng thái lỗi | Sắp xếp command theo phụ thuộc và xử lý lỗi ở script gọi |
| Lỗi parsing vẫn trả mã 0 | Nhánh parser chỉ ghi log và kết thúc bình thường ở phiên bản đang dùng | Kiểm thử lỗi parsing riêng, kiểm tra bản sửa theo phiên bản |
| Mã thoát thay đổi giữa các bản | Không có quy ước chung | Công bố và duy trì bảng mã như hợp đồng CLI |

## 16. Bài tập thực hành

Tạo command `backup` có hai trường hợp:

- Thành công: sao lưu hoàn tất, trả `ExitStatus.OK`.
- Thất bại do đường dẫn nguồn không tồn tại: trả mã `2` với mô tả `source path does not exist`.
- Thất bại do dịch vụ lưu trữ không truy cập được: trả mã `4` với mô tả `storage service is unavailable`.

Yêu cầu:

1. Tạo `ExitStatusExceptionMapper` của Spring Shell để ánh xạ hai exception nghiệp vụ.
2. Tạo `ExitCodeExceptionMapper` của Spring Boot để lấy mã từ `CommandExecutionException`.
3. Chạy ứng dụng trong chế độ không tương tác.
4. Viết Bash hoặc PowerShell script đọc mã thoát và dừng khi backup thất bại.
5. Viết test cho output thành công, mã lỗi nghiệp vụ và mã lỗi tiến trình.
6. Thử một command sai cú pháp và một file script không tồn tại để kiểm tra hành vi của phiên bản Spring Shell đang dùng.

Các lệnh thử:

~~~text
backup --source=documents --destination=archive
backup --source=missing --destination=archive
backup --source=documents --destination=remote-store
java -jar backup-cli.jar backup --source=documents
~~~

Sau khi hoàn thành, hãy giải thích được sự khác nhau giữa `ExitStatus.code()`, `CommandExecutionException.getExitCode()` và mã tiến trình mà shell hệ điều hành đọc được.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 – Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell 4.0.4 – Execution](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell API – ExitStatus](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ExitStatus.html)
- [Spring Shell API – ExitStatusExceptionMapper](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/exit/ExitStatusExceptionMapper.html)
- [Spring Shell API – CommandExecutionException](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandExecutionException.html)
- [Spring Shell 4.0.2 Release Notes – non-interactive exit-code fix](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.2)
- [Spring Shell issue #1391 – parse errors and process exit code](https://github.com/spring-projects/spring-shell/issues/1391)
- [Spring Shell PR #1393 – proposed parse-error exit-code fix](https://github.com/spring-projects/spring-shell/pull/1393)
- [Spring Boot 4 – Application Exit](https://docs.spring.io/spring-boot/4.0/reference/features/spring-application.html)
- [Spring Boot API – ExitCodeExceptionMapper](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/ExitCodeExceptionMapper.html)
