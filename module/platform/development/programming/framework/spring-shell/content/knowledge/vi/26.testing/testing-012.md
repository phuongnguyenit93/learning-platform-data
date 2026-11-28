# Kiểm chứng exit code ở cấp tiến trình

Một command Spring Shell có thể báo lỗi cho người vận hành, nhưng hệ điều hành hoặc công cụ gọi ứng dụng vẫn cần biết lần chạy đó thành công hay thất bại. Ví dụ, Bash script, PowerShell, CI pipeline, cron hoặc scheduler thường chỉ kiểm tra **exit code của tiến trình** để quyết định có tiếp tục bước sau, thử lại hay đánh dấu job thất bại.

Trong Spring Shell 4, cần phân biệt hai tầng trạng thái:

- **ExitStatus của command:** kết quả của một lần thực thi command, gồm mã số và mô tả.
- **Process exit code:** mã số mà JVM trả về cho hệ điều hành khi ứng dụng kết thúc.

Hai giá trị này có liên quan nhưng không tự động là một. **ExitStatusExceptionMapper** của Spring Shell chuyển exception thành trạng thái command. **ExitCodeExceptionMapper** của Spring Boot chuyển exception chưa được xử lý thành mã thoát của ứng dụng. Khi chạy non-interactive, Spring Shell nối hai tầng này bằng **CommandExecutionException**.

Bài này tập trung vào Spring Shell 4 và Spring Boot 4, cách cấu hình mã thoát ổn định, cách kiểm thử bằng tiến trình thật và các giới hạn cần biết khi chạy script.

## 1. Vì sao cần kiểm tra ở cấp tiến trình?

Giả sử một lệnh import dữ liệu trả về thông báo:

~~~text
Không thể đọc file đầu vào.
~~~

Người dùng có thể nhìn thấy thông báo và hiểu thao tác thất bại. Nhưng nếu command kết thúc với process exit code bằng **0**, CI hoặc script sẽ coi đó là thành công.

Ví dụ Bash:

~~~bash
java -jar task-cli.jar import --file=missing.csv
echo $?
~~~

Ví dụ PowerShell:

~~~powershell
java -jar task-cli.jar import --file=missing.csv
$LASTEXITCODE
~~~

Ví dụ Windows Command Prompt:

~~~bat
java -jar task-cli.jar import --file=missing.csv
echo %ERRORLEVEL%
~~~

Nếu tiến trình trả mã **0**, shell script thường tiếp tục như thể import thành công. Vì vậy, kiểm thử output trên màn hình chưa đủ; cần xác nhận mã mà tiến trình trả về.

## 2. Phân biệt ExitStatus và process exit code

**ExitStatus** của Spring Shell 4 là một record gồm hai thành phần:

~~~java
public record ExitStatus(int code, String description) {
}
~~~

API có các trạng thái dựng sẵn như **OK**, **USAGE_ERROR**, **EXECUTION_ERROR** và **AVAILABILITY_ERROR**. Ứng dụng cũng có thể tạo một trạng thái riêng bằng constructor với mã và mô tả.

| Tầng | Đối tượng | Phạm vi | Ai đọc kết quả? |
|---|---|---|---|
| Command | ExitStatus | Một lần gọi command | Spring Shell và command caller |
| Exception mapping của shell | ExitStatusExceptionMapper | Một command | Spring Shell |
| Exception mapping của Boot | ExitCodeExceptionMapper | Lần chạy ứng dụng | Spring Boot |
| Tiến trình | Exit code của JVM | Toàn bộ tiến trình | Hệ điều hành, shell script, CI |

Ở chế độ interactive, nhiều command có thể chạy trong cùng một JVM. Một command thất bại không nhất thiết kết thúc shell; người dùng vẫn có thể chạy command tiếp theo. Vì thế, process exit code cuối cùng không phải là mã kết quả của từng command đã chạy trong REPL.

Khi chạy một command từ script hoặc automation, hãy chọn chế độ non-interactive để một lần khởi chạy ứng dụng tương ứng với một tác vụ có thể kiểm tra kết quả ở cấp tiến trình.

## 3. Chạy Spring Shell ở chế độ non-interactive

Spring Shell 4 mặc định khởi chạy chế độ interactive. Để chạy command từ đối số tiến trình, đặt thuộc tính:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
~~~

Khi thuộc tính này tắt interactive mode, Spring Shell dùng **NonInteractiveShellRunner**. Runner này thực thi command được truyền qua đối số tiến trình rồi kết thúc. Nó cũng hỗ trợ chạy script được chỉ định bằng tiền tố **@**:

~~~bash
java -jar task-cli.jar task list
java -jar task-cli.jar @nightly-tasks.txt
~~~

Chế độ non-interactive phù hợp với:

- CI/CD pipeline.
- Bash hoặc PowerShell script.
- Cron và scheduler.
- Job chạy theo lịch hoặc tác vụ tự động.
- Container chạy một tác vụ rồi kết thúc.

Không dùng process exit code để quyết định trạng thái của một command trong REPL đang hoạt động. Trong REPL, hãy hiển thị lỗi rõ ràng, giữ shell hoạt động và để người dùng tự quyết định bước tiếp theo.

## 4. Định nghĩa một quy ước mã thoát

Nên thống nhất mã thoát trong toàn bộ CLI để script có thể xử lý nhất quán. Ví dụ sau là quy ước riêng của ứng dụng:

| Mã | Ý nghĩa | Trường hợp sử dụng |
|---:|---|---|
| 0 | Thành công | Command hoàn tất đúng |
| 2 | Sai cú pháp hoặc cách dùng | Thiếu argument, giá trị option sai định dạng |
| 3 | Dữ liệu không hợp lệ | File có nội dung không đạt quy tắc |
| 4 | Không tìm thấy tài nguyên | File hoặc bản ghi được yêu cầu không tồn tại |
| 5 | Lỗi I/O hoặc phụ thuộc bên ngoài | Không đọc được file, database hoặc API |
| 10 | Lỗi thực thi không dự kiến | Lỗi nội bộ chưa phân loại |

Các con số này là hợp đồng của ứng dụng, không phải tất cả đều là mã mặc định bắt buộc của Spring Shell. Chọn một bộ mã ổn định, ghi tài liệu và không thay đổi ý nghĩa của mã đã được script bên ngoài sử dụng.

Giữ mã **0** dành riêng cho thành công. Không trả **0** khi gặp exception chỉ vì muốn tránh stack trace hoặc muốn command kết thúc bình thường. Nếu cần hiển thị lỗi thân thiện, hãy xử lý thông báo và ánh xạ exception sang một mã khác 0.

## 5. Hai lớp exception mapper

Spring Shell 4 và Spring Boot 4 có hai interface riêng:

| Mapper | Package | Đầu vào | Kết quả |
|---|---|---|---|
| **ExitStatusExceptionMapper** | org.springframework.shell.core.command.exit | Exception từ command | ExitStatus |
| **ExitCodeExceptionMapper** | org.springframework.boot | Throwable làm ứng dụng kết thúc | Số nguyên process exit code |

**ExitStatusExceptionMapper** được cấu hình cho command. Với annotation-based command, thuộc tính **exitStatusExceptionMapper** tham chiếu tên Spring bean. Với command đăng ký bằng builder, có thể cấu hình mapper trên **Command.Builder**.

**ExitCodeExceptionMapper** là cơ chế của Spring Boot. Nó nhận exception khiến ứng dụng kết thúc và ánh xạ sang mã mà ứng dụng nên trả về cho môi trường chạy.

Không dùng một mapper thay cho mapper còn lại. Việc map exception thành ExitStatus của Spring Shell không tự nó bảo đảm JVM trả đúng process exit code.

## 6. Ánh xạ lỗi nghiệp vụ thành ExitStatus

Ví dụ ứng dụng có hai loại lỗi: file không tồn tại và dữ liệu import không hợp lệ:

~~~java
public class InputFileNotFoundException extends RuntimeException {

    public InputFileNotFoundException(String message) {
        super(message);
    }
}

public class InvalidImportDataException extends RuntimeException {

    public InvalidImportDataException(String message) {
        super(message);
    }
}
~~~

Đăng ký mapper của Spring Shell:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
public class CommandExitStatusConfiguration {

    @Bean
    ExitStatusExceptionMapper commandExitStatusMapper() {
        return exception -> {
            if (exception instanceof InputFileNotFoundException) {
                return new ExitStatus(4, "Không tìm thấy file đầu vào.");
            }
            if (exception instanceof InvalidImportDataException) {
                return new ExitStatus(3, "Dữ liệu import không hợp lệ.");
            }
            return new ExitStatus(10, "Command không thể hoàn tất.");
        };
    }
}
~~~

Gắn mapper vào command:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ImportCommands {

    private final ImportService importService;

    public ImportCommands(ImportService importService) {
        this.importService = importService;
    }

    @Command(
            name = "import",
            description = "Import dữ liệu từ file.",
            exitStatusExceptionMapper = "commandExitStatusMapper"
    )
    public String importFile(
            @Option(longName = "file", required = true) Path file) {

        if (!Files.exists(file)) {
            throw new InputFileNotFoundException(
                    "Không tìm thấy file: " + file
            );
        }

        importService.importFile(file);
        return "Import thành công.";
    }
}
~~~

Mapper trả **ExitStatus** với mã 4 hoặc 3 tùy loại exception. Nếu có lỗi không được phân loại, ví dụ trả mã 10 thay vì mặc định thành công.

Đối với command được đăng ký bằng builder, API **Command.Builder.exitStatusExceptionMapper(...)** cho phép truyền trực tiếp mapper thay vì tham chiếu tên bean trong annotation.

## 7. Chuyển mã của command thành process exit code

Trong non-interactive mode, khi command trả một ExitStatus có mã khác 0, **NonInteractiveShellRunner** chuyển kết quả đó thành **CommandExecutionException**. Exception này mang mã của command qua phương thức **getExitCode()**.

Spring Boot có thể nhận exception đó và ánh xạ sang process exit code bằng **ExitCodeExceptionMapper**:

~~~java
import org.springframework.boot.ExitCodeExceptionMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.CommandExecutionException;

@Configuration
public class ProcessExitCodeConfiguration {

    @Bean
    ExitCodeExceptionMapper processExitCodeMapper() {
        return exception -> {
            for (Throwable current = exception;
                    current != null;
                    current = current.getCause()) {
                if (current instanceof CommandExecutionException commandException) {
                    return commandException.getExitCode();
                }
            }
            return 1;
        };
    }
}
~~~

Mapper duyệt cả chuỗi cause để tìm **CommandExecutionException** và lấy đúng mã mà Spring Shell đã tạo. Nếu exception không có mã command, mapper trả 1 để báo thất bại chung. Không trả 0 cho exception không nhận diện được vì như vậy có thể che giấu lỗi.

Luồng xử lý trong non-interactive mode:

~~~mermaid
flowchart TD
    A["Process nhận lệnh"] --> B["NonInteractiveShellRunner"]
    B --> C["Command được thực thi"]
    C --> D{"Có lỗi?"}
    D -->|Không| E["ExitStatus.OK"]
    D -->|Có| F["ExitStatusExceptionMapper"]
    F --> G["ExitStatus với code khác 0"]
    G --> H["CommandExecutionException"]
    H --> I["Spring Boot ExitCodeExceptionMapper"]
    I --> J["Process exit code"]
    E --> K["Process kết thúc với code 0"]
    J --> L["Shell script / CI kiểm tra"]
    K --> L
~~~

**ExitStatusExceptionMapper** xử lý ý nghĩa lỗi ở cấp command. **ExitCodeExceptionMapper** chuyển mã đó sang trạng thái của ứng dụng. Hai lớp phối hợp để giữ nguyên mã nghiệp vụ khi command chạy trong process riêng.

## 8. Ứng dụng Spring Boot không cần gọi System.exit trong command

Ứng dụng Spring Shell 4 có thể dùng main method thông thường:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TaskCliApplication {

    public static void main(String[] args) {
        SpringApplication.run(TaskCliApplication.class, args);
    }
}
~~~

Để non-interactive runner thực thi một command, cấu hình thuộc tính trong **application.yml** rồi truyền tên command và argument khi chạy JAR.

Không gọi **System.exit()** từ command method hoặc service. Việc đó dừng JVM ngay tại vị trí gọi, có thể bỏ qua các bước cleanup của Spring, transaction, logging và resource bean.

Spring Boot cũng có **ExitCodeGenerator** và phương thức **SpringApplication.exit()** để ứng dụng trả mã khi chủ động kết thúc bình thường. Cơ chế này hữu ích cho những ứng dụng runner tự quản lý vòng đời; với command thất bại trong non-interactive Spring Shell, hãy để exception đi qua cơ chế xử lý của Spring Boot và dùng ExitCodeExceptionMapper.

## 9. Chạy command và đọc process exit code

Với cấu hình non-interactive, có thể chạy:

~~~bash
java -jar task-cli.jar import --file=tasks.csv
echo $?
~~~

Nếu import thành công, process trả 0. Nếu file không tồn tại và mapper đã được cấu hình, process trả 4.

Trong Bash, có thể dùng trực tiếp điều kiện:

~~~bash
if java -jar task-cli.jar import --file=tasks.csv; then
    echo "Import thành công"
else
    code=$?
    echo "Import thất bại, exit code: $code"
    exit "$code"
fi
~~~

Trong PowerShell:

~~~powershell
java -jar task-cli.jar import --file=tasks.csv
if ($LASTEXITCODE -ne 0) {
    Write-Error "Import thất bại, exit code: $LASTEXITCODE"
    exit $LASTEXITCODE
}
~~~

Nếu chạy nhiều bước, chỉ tiếp tục khi mã thoát bằng 0 hoặc thuộc một nhóm mã được quy định rõ. Không chỉ dò chuỗi "thành công" trong output vì nội dung có thể thay đổi theo ngôn ngữ, format hoặc phiên bản.

## 10. Exit code của REPL không đại diện cho command cuối cùng

Trong interactive mode, Spring Shell giữ tiến trình sống để người dùng nhập nhiều command. Một command lỗi có thể được hiển thị như một kết quả lỗi nhưng không kết thúc REPL. Người dùng vẫn có thể sửa input và chạy lại.

Ví dụ:

~~~text
$ task-cli.jar
shell> import --file=missing.csv
Không tìm thấy file đầu vào.
shell> task list
...
shell> quit
~~~

Không nên kỳ vọng process exit code cuối cùng là 4 chỉ vì một command trước đó thất bại. Process exit code biểu diễn kết quả kết thúc của toàn bộ ứng dụng. Nếu scheduler cần mã cho từng tác vụ, hãy chạy command ở chế độ non-interactive, mỗi tác vụ một process.

## 11. Kiểm thử mapper ở cấp unit

Kiểm thử mapper riêng giúp xác nhận các exception được phân loại đúng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.shell.core.command.ExitStatus;

class CommandExitStatusMapperTests {

    private final CommandExitStatusConfiguration configuration =
            new CommandExitStatusConfiguration();

    @Test
    void mapsMissingFileToCodeFour() {
        ExitStatus status = configuration.commandExitStatusMapper()
                .apply(new InputFileNotFoundException("missing.csv"));

        assertThat(status.code()).isEqualTo(4);
    }

    @Test
    void mapsInvalidDataToCodeThree() {
        ExitStatus status = configuration.commandExitStatusMapper()
                .apply(new InvalidImportDataException("invalid row"));

        assertThat(status.code()).isEqualTo(3);
    }
}
~~~

Kiểm thử mapper của Spring Boot:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.shell.core.command.CommandExecutionException;

class ProcessExitCodeMapperTests {

    private final ProcessExitCodeConfiguration configuration =
            new ProcessExitCodeConfiguration();

    @Test
    void preservesCommandExitCode() {
        int code = configuration.processExitCodeMapper()
                .getExitCode(new CommandExecutionException("Not found", 4));

        assertThat(code).isEqualTo(4);
    }

    @Test
    void mapsUnknownFailureToNonZero() {
        int code = configuration.processExitCodeMapper()
                .getExitCode(new IllegalStateException("Unexpected"));

        assertThat(code).isEqualTo(1);
    }
}
~~~

Unit test xác nhận quy tắc mapping, nhưng không chứng minh JVM thực sự kết thúc với mã đó. Cần kiểm thử thêm qua process riêng.

## 12. Kiểm thử command bằng ShellTestClient

**@ShellTest** và **ShellTestClient** giúp gửi command như người dùng nhập và kiểm tra nội dung hiển thị:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.shell.core.command.annotation.Command;

@SpringBootApplication
public class TestCliApplication {

    @Command(name = "ping")
    public String ping() {
        return "ready";
    }
}
~~~

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTest;
import org.springframework.shell.test.ShellTestClient;

@ShellTest
@ContextConfiguration(classes = TestCliApplication.class)
class ShellCommandTests {

    @Autowired
    ShellTestClient client;

    @Test
    void displaysCommandOutput() throws Exception {
        var screen = client.sendCommand("ping");

        ShellAssertions.assertThat(screen).containsText("ready");
    }
}
~~~

Với command thất bại, kiểm thử riêng mapper để xác nhận mã được tạo ra. **ShellTestClient** kiểm tra command execution và output; nó không thay thế kiểm thử exit code của một JVM process độc lập.

## 13. Kiểm thử process bằng ProcessBuilder

Để xác nhận mã mà hệ điều hành nhìn thấy, khởi chạy JAR trong một process con rồi kiểm tra **Process.exitValue()**. Ví dụ sau giả định build đã tạo JAR và đường dẫn JAR được truyền qua system property **app.jar**:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.fail;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ProcessExitCodeIntegrationTests {

    @TempDir
    Path tempDir;

    @Test
    void missingInputFileReturnsExitCodeFour() throws Exception {
        Path java = Path.of(
                System.getProperty("java.home"),
                "bin",
                System.getProperty("os.name").startsWith("Windows")
                        ? "java.exe"
                        : "java"
        );
        Path jar = Path.of(System.getProperty("app.jar")).toAbsolutePath();
        Path missingFile = tempDir.resolve("missing.csv");
        Path output = tempDir.resolve("process.log");

        Process process = new ProcessBuilder(
                java.toString(),
                "-jar",
                jar.toString(),
                "import",
                "--file=" + missingFile
        )
                .redirectErrorStream(true)
                .redirectOutput(output.toFile())
                .start();

        boolean finished = process.waitFor(30, TimeUnit.SECONDS);
        if (!finished) {
            process.destroyForcibly();
            fail("CLI không kết thúc trong thời gian cho phép.");
        }

        assertThat(process.exitValue()).isEqualTo(4);
        assertThat(Files.readString(output))
                .contains("Không tìm thấy file đầu vào.");
    }
}
~~~

Test này khởi chạy tiến trình Java thật. Việc chuyển stdout và stderr vào file giúp tránh pipe buffer đầy khi test chờ process. Timeout bảo vệ test khỏi một ứng dụng bị treo.

Ứng dụng được đóng gói để chạy test phải đặt **spring.shell.interactive.enabled=false** trong cấu hình. Nếu runner vào REPL và chờ input, test process sẽ không tự kết thúc và bị timeout.

Có thể mở rộng thành các ca:

- Command thành công trả 0.
- Dữ liệu không hợp lệ trả 3.
- File không tồn tại trả 4.
- Lỗi nội bộ trả 10.
- Option hoặc argument không hợp lệ.
- Script có nhiều command và một command thất bại.
- Script không tồn tại hoặc không đọc được.

Khi kiểm thử lỗi parse hoặc script, cần lưu ý giới hạn phiên bản ở phần tiếp theo.

## 14. Lỗi exit code cần biết trong Spring Shell 4.0.4

Spring Shell 4.0.2 đã sửa một lỗi khiến **NonInteractiveShellRunner** trả process code 0 khi command trả một ExitStatus khác 0. Với command execution failure, runner tạo **CommandExecutionException** mang mã tương ứng; Spring Boot có thể dùng **ExitCodeExceptionMapper** để chuyển mã này sang process exit code.

Tuy nhiên, tại ngày 26-11-2026, Spring Shell 4.0.4 vẫn có một lỗi đã được báo cáo trong issue **#1391**: khi parser không thể phân tích command, file script **@file** không tồn tại/không mở được hoặc dòng script không đọc được, runner có thể chỉ ghi log rồi kết thúc bình thường với process code 0.

Pull request **#1393** đề xuất chuyển các lỗi này thành **CommandExecutionException**, nhưng tại thời điểm biên soạn PR vẫn đang mở và chưa được triển khai. Vì vậy:

- Không giả định lỗi parse trong non-interactive mode luôn tạo process code khác 0 trên 4.0.4.
- Kiểm thử riêng command execution failure và command parsing failure.
- Kiểm tra riêng file script không tồn tại, không có quyền đọc và lỗi khi đọc dòng.
- Theo dõi release Spring Shell có chứa bản sửa #1393 trước khi dựa vào hành vi mới.
- Nếu cần bảo đảm nghiêm ngặt ngay trên phiên bản đang dùng, validate cú pháp và sự tồn tại của script ở lớp launcher/wrapper trước khi gọi Spring Shell, đồng thời giữ test process-level để phát hiện thay đổi.

Đây là khác biệt quan trọng giữa một command được parse thành công nhưng thất bại khi chạy và một command không thể parse ngay từ đầu. Không gộp hai ca thành một test "command lỗi".

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Output báo lỗi nhưng process code bằng 0 | Chỉ kiểm tra thông báo hoặc trả trạng thái thành công | Kiểm tra cả ExitStatus và process exit code |
| Mapper của Spring Shell chạy nhưng process code không đổi | Nhầm ExitStatusExceptionMapper với mapper của JVM | Cấu hình ExitCodeExceptionMapper của Spring Boot |
| Command trả mã khác 0 nhưng script không nhận được | Chạy interactive REPL hoặc runner không phù hợp | Dùng spring.shell.interactive.enabled=false |
| Mọi exception đều thành code 0 | Boot mapper trả 0 cho exception không nhận diện | Dùng fallback khác 0 |
| Mã lỗi bị mất | Không giữ CommandExecutionException.getExitCode() | Ánh xạ lại mã từ exception |
| Một command lỗi nhưng REPL vẫn chạy | Interactive mode tiếp tục vòng lặp | Không dùng process code làm trạng thái của từng command |
| Test output pass nhưng CI vẫn xanh sai | Test chỉ kiểm tra ShellScreen hoặc log | Thêm kiểm thử JVM process riêng |
| Process test bị treo | Không đặt timeout hoặc process chờ input | Chạy non-interactive và dùng waitFor(timeout) |
| Test bị treo khi đọc output | Chờ process trong khi pipe stdout/stderr đầy | Redirect output vào file hoặc drain stream đồng thời |
| Lỗi parse vẫn trả 0 ở 4.0.4 | Lỗi #1391 trong NonInteractiveShellRunner | Kiểm thử riêng và theo dõi bản sửa #1393 |
| Gọi System.exit trong command | Dừng JVM trực tiếp, bỏ qua cleanup | Để Spring Boot xử lý vòng đời và exit code |

## 16. Checklist trước khi phát hành CLI

- [ ] Đã phân biệt ExitStatus của command và process exit code.
- [ ] Đã xác định quy ước mã thoát của ứng dụng.
- [ ] Đã cấu hình **ExitStatusExceptionMapper** cho exception nghiệp vụ.
- [ ] Đã cấu hình **ExitCodeExceptionMapper** của Spring Boot.
- [ ] Mapper của Boot giữ mã từ **CommandExecutionException.getExitCode()**.
- [ ] Exception không nhận diện được luôn tạo process code khác 0.
- [ ] Đã bật non-interactive mode cho automation.
- [ ] Đã kiểm thử command thành công và thất bại.
- [ ] Đã kiểm thử bằng một JVM process riêng.
- [ ] Đã đặt timeout cho process test.
- [ ] Đã kiểm thử script và lỗi parser riêng biệt.
- [ ] Đã kiểm tra giới hạn của phiên bản Spring Shell đang triển khai.
- [ ] Không gọi **System.exit()** từ command hoặc service.
- [ ] CI kiểm tra mã thoát thay vì chỉ dò nội dung log.

Kiểm chứng ở cấp tiến trình là bước cuối để xác nhận CLI có thể phối hợp đúng với shell script, CI và scheduler. Hãy giữ mã lỗi nhất quán từ command đến JVM, kiểm thử bằng process riêng và xác minh cả các trường hợp lỗi parser, script. Khi đó, thông báo thân thiện cho người dùng và tín hiệu máy đọc được sẽ cùng phản ánh đúng kết quả thực thi.

## Tài liệu tham khảo

- [Spring Shell 4 — Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html) — ExitStatusExceptionMapper và cấu hình mapper theo command.
- [Spring Shell 4 — Execution](https://docs.spring.io/spring-shell/reference/execution.html) — interactive mode, non-interactive mode và ShellRunner.
- [Spring Shell 4 API — ExitStatus](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ExitStatus.html) — trạng thái command, code và description.
- [Spring Shell 4 API — CommandExecutionException](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandExecutionException.html) — exception mang mã exit code của command.
- [Spring Shell 4 API — NonInteractiveShellRunner](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html) — runner chạy command hoặc script mà không vào REPL.
- [Spring Boot 4 API — ExitCodeExceptionMapper](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/ExitCodeExceptionMapper.html) — ánh xạ exception sang mã thoát của ứng dụng.
- [Spring Boot 4 — SpringApplication / Application Exit](https://docs.spring.io/spring-boot/4.0/reference/features/spring-application.html) — vòng đời application context, ExitCodeGenerator và SpringApplication.exit.
- [Spring Shell 4 — Testing](https://docs.spring.io/spring-shell/reference/testing.html) — ShellTest, ShellTestClient và end-to-end testing.
- [Spring Shell issue #1339](https://github.com/spring-projects/spring-shell/issues/1339) — sửa lỗi command trả ExitStatus khác 0 nhưng process luôn trả 0; fix thuộc Spring Shell 4.0.2.
- [Spring Shell issue #1391](https://github.com/spring-projects/spring-shell/issues/1391) — lỗi process exit code 0 khi command parsing hoặc script file gặp lỗi.
- [Spring Shell pull request #1393](https://github.com/spring-projects/spring-shell/pull/1393) — đề xuất ném CommandExecutionException cho lỗi parse và lỗi đọc script.
- [Spring Shell releases](https://github.com/spring-projects/spring-shell/releases) — lịch sử phiên bản và các thay đổi của Spring Shell 4.x.
