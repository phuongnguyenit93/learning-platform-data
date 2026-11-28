# ExitStatus và ExitStatusExceptionMapper trong mô hình 4.x

Một command có thể hoàn thành thành công, bị từ chối vì dữ liệu đầu vào, chưa khả dụng hoặc thất bại khi gọi dịch vụ bên ngoài. Trong Spring Shell 4, kết quả thực thi command được biểu diễn bằng `ExitStatus`; các exception phát sinh trong lúc command chạy có thể được chuyển thành trạng thái này bằng `ExitStatusExceptionMapper`.

Hai API này tạo ra một hợp đồng rõ ràng cho command và thông báo lỗi. Chúng đặc biệt hữu ích khi CLI được gọi từ script, pipeline hoặc CI, nơi mã lỗi ổn định giúp bước tiếp theo quyết định tiếp tục hay dừng. Cần phân biệt trạng thái của một command với mã thoát của toàn bộ tiến trình JVM: chúng liên quan nhưng không phải cùng một lớp kết quả.

## 1. Mô hình kết quả trong Spring Shell 4

Trong Spring Shell 4, `Command` có phương thức thực thi trả về `ExitStatus`:

```java
ExitStatus execute(CommandContext commandContext) throws Exception;
```

`ExitStatus` là một record gồm hai thành phần:

```java
public record ExitStatus(int code, String description) { }
```

`code` là mã trạng thái dạng số để chương trình khác có thể xử lý. `description` là mô tả ngắn giúp người vận hành hiểu kết quả. Command có thể trả về một trạng thái có sẵn hoặc tạo trạng thái riêng:

```java
return ExitStatus.OK;

return new ExitStatus(20, "không tìm thấy dự án được yêu cầu");
```

API `Command.execute(CommandContext)` trả `ExitStatus`; `CommandExecutor.execute(...)` cũng trả trạng thái thực thi command. Đây là hợp đồng của mô hình command 4.x. <Link url="https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html" title="Command API — Spring Shell 4.0.3"/> · <Link url="https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandExecutor.html" title="CommandExecutor API — Spring Shell 4.0.3"/>.

## 2. Các trạng thái dựng sẵn

Spring Shell 4 cung cấp các hằng `ExitStatus` phổ biến:

| Hằng | Ý nghĩa sử dụng |
| --- | --- |
| `ExitStatus.OK` | Command hoàn tất thành công |
| `ExitStatus.USAGE_ERROR` | Cách gọi command hoặc dữ liệu đầu vào không phù hợp |
| `ExitStatus.AVAILABILITY_ERROR` | Command chưa thể thực hiện ở trạng thái hiện tại |
| `ExitStatus.EXECUTION_ERROR` | Lỗi phát sinh trong quá trình thực thi |

Các hằng này giúp code dễ đọc và thống nhất ý nghĩa giữa các command. Khi cần phân loại chi tiết hơn cho script, ứng dụng có thể tạo `new ExitStatus(code, description)` với mã riêng. API cung cấp `code()` và `description()` để đọc hai thành phần. <Link url="https://javadoc.io/static/org.springframework.shell/spring-shell-core/4.0.3/org/springframework/shell/core/command/ExitStatus.html" title="ExitStatus API — Spring Shell 4.0.3"/>.

Không gán mã `0` cho một tình huống thất bại chỉ vì command đã xử lý được exception. Theo quy ước CLI phổ biến, `0` biểu thị thành công và mã khác `0` biểu thị một loại lỗi hoặc kết quả cần được script chú ý. Mã cụ thể nên được quy ước trong tài liệu ứng dụng.

## 3. Khi nào command cần trả trạng thái riêng?

Nếu command chỉ thực hiện thao tác và in kết quả, builder hoặc annotation registration là đủ. Nếu ứng dụng cần phân biệt các kết quả nghiệp vụ mà không xem chúng là exception, command cần trả `ExitStatus` tương ứng.

Ví dụ command đồng bộ dữ liệu có thể có ba kết quả:

| Kết quả nghiệp vụ | Trạng thái đề xuất |
| --- | --- |
| Có bản ghi mới và đã đồng bộ | `ExitStatus.OK` |
| Không có dữ liệu mới, không cần thay đổi | Mã riêng như `10`, mô tả `không có dữ liệu mới` |
| Không thể đồng bộ do dịch vụ từ xa lỗi | `ExitStatus.EXECUTION_ERROR` hoặc mã riêng |

“Không có dữ liệu mới” có thể là kết quả bình thường trong một ứng dụng và là điều kiện cần cảnh báo trong ứng dụng khác. Hãy chọn mã theo hợp đồng của command thay vì mặc định mọi tình huống không tạo thay đổi đều là lỗi.

## 4. Trả `ExitStatus` trực tiếp bằng `AbstractCommand`

`Command.Builder.execute(...)` cung cấp adapter cho các command dùng `Consumer<CommandContext>` hoặc `Function<CommandContext, String>`. Các dạng này phù hợp khi command chỉ cần xử lý và ghi output theo cách thông thường. Khi cần tự quyết định `ExitStatus` cho từng nhánh kết quả, có thể kế thừa `AbstractCommand` và cài đặt `doExecute`.

Ví dụ:

```java
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.stereotype.Component;

@Component
public class SyncCommand extends AbstractCommand {

    private final SyncService syncService;

    public SyncCommand(SyncService syncService) {
        super("sync", "Đồng bộ dữ liệu từ nguồn đã cấu hình");
        this.syncService = syncService;
    }

    @Override
    public ExitStatus doExecute(CommandContext context) {
        SyncResult result = syncService.sync();

        if (result.importedCount() == 0) {
            println("Không có dữ liệu mới.", context);
            return new ExitStatus(10, "không có dữ liệu mới");
        }

        println("Đã đồng bộ " + result.importedCount() + " bản ghi.", context);
        return ExitStatus.OK;
    }
}
```

`AbstractCommand` cung cấp phần cấu trúc chung của command; `doExecute` quyết định trạng thái kết quả. Nếu chỉ cần trả thành công hoặc để exception được xử lý bằng mapper, có thể dùng `Command.Builder` hoặc `@Command` cho gọn hơn. <Link url="https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/AbstractCommand.html" title="AbstractCommand API — Spring Shell 4.0.3"/>.

## 5. `ExitStatusExceptionMapper` làm nhiệm vụ gì?

Khi command ném exception trong lúc thực thi, Spring Shell có thể chuyển exception đó thành `ExitStatus` thông qua `ExitStatusExceptionMapper`. Đây là functional interface nhận `Exception` và trả về `ExitStatus`:

```java
ExitStatus apply(Exception exception);
```

Mapper giúp tập trung quy tắc ánh xạ lỗi. Thay vì mỗi command tự bắt nhiều loại exception, ứng dụng có thể chuyển các lỗi nghiệp vụ đã biết thành mã ổn định và thông báo thân thiện.

Ví dụ ứng dụng triển khai dự án có các lỗi:

- `ProjectNotFoundException`: dự án không tồn tại.
- `DeploymentPermissionException`: người dùng không có quyền triển khai.
- `InvalidDeploymentRequestException`: yêu cầu triển khai không hợp lệ.
- Các exception khác: lỗi thực thi chưa phân loại.

## 6. Viết mapper cho các exception nghiệp vụ

Tạo mapper như một Spring bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
public class ExitStatusConfiguration {

    @Bean
    ExitStatusExceptionMapper deploymentExceptionMapper() {
        return exception -> {
            if (exception instanceof ProjectNotFoundException) {
                return new ExitStatus(3, "không tìm thấy dự án");
            }
            if (exception instanceof DeploymentPermissionException) {
                return new ExitStatus(4, "không có quyền triển khai dự án này");
            }
            if (exception instanceof InvalidDeploymentRequestException) {
                return ExitStatus.USAGE_ERROR;
            }
            return ExitStatus.EXECUTION_ERROR;
        };
    }
}
```

Các mã `3` và `4` trong ví dụ là mã do ứng dụng tự quy ước, không phải mã mặc định bắt buộc của Spring Shell. Mô tả nên ngắn, có thể hiển thị cho người vận hành và không chứa stack trace, token hoặc thông tin nhạy cảm.

Chỉ ánh xạ các exception mà ứng dụng hiểu rõ. Không chuyển mọi exception thành `ExitStatus.OK`, cũng không trả cùng một mã thành công cho lỗi không xác định. Nếu exception chưa được phân loại, dùng trạng thái lỗi thực thi chung để script nhận biết thao tác thất bại.

## 7. Gắn mapper bằng annotation `@Command`

Với annotation-based registration, thuộc tính `exitStatusExceptionMapper` nhận tên bean mapper:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class DeploymentCommands {

    private final DeploymentService deploymentService;

    public DeploymentCommands(DeploymentService deploymentService) {
        this.deploymentService = deploymentService;
    }

    @Command(
            name = "deploy",
            description = "Triển khai một dự án",
            exitStatusExceptionMapper = "deploymentExceptionMapper")
    public void deploy(
            @Argument(index = 0, description = "Tên dự án") String projectName) {
        deploymentService.deploy(projectName);
    }
}
```

Spring Shell lấy bean `deploymentExceptionMapper` khi xử lý exception của command. Cách này phù hợp khi một nhóm command dùng chung một quy ước lỗi. Nếu mỗi command có chính sách mã lỗi khác nhau, tạo mapper riêng hoặc dùng cấu hình programmatic cho từng command.

## 8. Gắn mapper bằng `Command.Builder`

Khi tạo command bằng code, truyền mapper vào `.exitStatusExceptionMapper(...)`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandArgument;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Bean
Command deployCommand(
        DeploymentService deploymentService,
        ExitStatusExceptionMapper deploymentExceptionMapper) {

    CommandArgument projectNameArgument = new CommandArgument.Builder()
            .index(0)
            .description("Tên dự án")
            .type(String.class)
            .build();

    return Command.builder()
            .name("deploy")
            .description("Triển khai một dự án")
            .arguments(projectNameArgument)
            .exitStatusExceptionMapper(deploymentExceptionMapper)
            .execute(context -> {
                String projectName = context.getArgumentByIndex(0).value();
                deploymentService.deploy(projectName);
                context.outputWriter().println("Đã triển khai " + projectName);
            });
}
```

Trong ví dụ, `execute` dùng `Consumer<CommandContext>` để thực hiện thao tác và ghi output. Nếu xử lý thành công, adapter command trả trạng thái thành công mặc định. Nếu service ném exception, mapper đã gắn vào command sẽ ánh xạ exception theo quy tắc của ứng dụng.

Nếu cần trả một mã riêng cho kết quả nghiệp vụ bình thường, chẳng hạn “không có thay đổi”, hãy dùng `AbstractCommand` như mục 4. Mapper chỉ giải quyết nhánh exception; nó không thay thế trạng thái được command chủ động trả về.

## 9. Phân loại lỗi theo đúng tầng

Không phải mọi lỗi xuất hiện khi gọi command đều được tạo ra trong thân phương thức command. Cần phân biệt lỗi phân tích cú pháp, chuyển đổi, validation và lỗi thực thi:

| Tầng | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Parsing | Thiếu option bắt buộc, sai cú pháp command | Parser báo lỗi sử dụng (usage) |
| Type conversion | Chuỗi `abc` không chuyển được thành số nguyên | Conversion/binding báo lỗi đầu vào |
| Validation | Tên dự án không đạt constraint | Validation báo lỗi tham số |
| Availability | Command chưa thể chạy vì chưa kết nối | `AVAILABILITY_ERROR` và lý do unavailable |
| Command execution | Service từ xa timeout hoặc dự án không tồn tại | Exception mapper hoặc trạng thái do command trả về |

`ExitStatusExceptionMapper` được mô tả để ánh xạ exception phát sinh trong quá trình thực thi command. Không giả định mapper của một command sẽ xử lý mọi lỗi parser xảy ra trước khi command được gọi. Hãy kiểm tra riêng các lỗi parsing và validation bằng test tích hợp.

## 10. Thiết kế bảng mã lỗi ổn định cho script và CI

Mã thoát là giao diện giữa CLI và chương trình gọi nó. Nếu script dựa vào mã `3` để biết dự án không tồn tại, không nên đổi mã đó tùy tiện trong một bản phát hành nhỏ.

Ví dụ bảng mã riêng của ứng dụng:

| Mã ví dụ | Ý nghĩa | Hành động của script |
| ---: | --- | --- |
| `0` | Thành công | Tiếp tục bước kế tiếp |
| `3` | Không tìm thấy dự án | Báo cấu hình sai hoặc dừng pipeline |
| `4` | Không có quyền | Dừng và yêu cầu cấp quyền |
| `10` | Không có dữ liệu mới | Bỏ qua bước xuất bản nếu đây là kết quả hợp lệ |
| `20` | Lỗi dịch vụ từ xa | Có thể thử lại theo chính sách retry |
| Mã khác | Lỗi chưa phân loại | Dừng và lưu log để điều tra |

Đây là ví dụ thiết kế, không phải bảng mã cố định của Spring Shell. Nên công bố bảng mã trong README hoặc tài liệu vận hành, giữ mã ổn định giữa các phiên bản và chỉ dùng mô tả để bổ sung ngữ cảnh cho người vận hành.

Không đưa thông tin thay đổi liên tục như timestamp, ID request hoặc stack trace vào `code`. Những thông tin đó thuộc `description`, log hoặc hệ thống quan sát.

## 11. `ExitStatus` khác mã thoát của tiến trình JVM

`ExitStatus` mô tả kết quả của một lần thực thi command. Trong interactive shell, một command có thể thất bại nhưng phiên shell vẫn tiếp tục để người dùng chạy command khác. Vì vậy, mã của command không tự động có nghĩa tiến trình JVM đã kết thúc với mã đó.

Spring Shell 4 có `NonInteractiveShellRunner` cho trường hợp chạy command hoặc script rồi kết thúc. Có thể chọn non-interactive mode bằng cấu hình:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Khi triển khai automation, hãy kiểm tra cả hai lớp:

1. Command trả `ExitStatus` đúng và mô tả đúng.
2. Tiến trình được khởi chạy thực tế trả mã thoát mà script/CI nhận được.

Sau khi chạy ứng dụng ở non-interactive mode, có thể kiểm tra mã tiến trình trong terminal:

```bash
java -jar app.jar deploy demo
echo $?
```

Trong PowerShell:

```powershell
java -jar app.jar deploy demo
$LASTEXITCODE
```

Tài liệu exception handling Spring Shell 4.0.4 nhấn mạnh command status và JVM process exit code là hai khái niệm riêng; chỉ cấu hình mapper không đồng nghĩa đã cấu hình mọi hành vi thoát của tiến trình. Spring Shell 4.0.2 cũng sửa lỗi non-interactive runner luôn trả `0`, vì vậy nên dùng ít nhất bản 4.0.2 khi dựa vào mã thoát của runner và kiểm thử đúng artifact được triển khai. <Link url="https://docs.spring.io/spring-shell/reference/execution.html" title="Execution — Spring Shell 4.0.3"/> · <Link url="https://github.com/spring-projects/spring-shell/releases" title="Spring Shell Releases"/>.

## 12. Tích hợp mã thoát cấp tiến trình với Spring Boot

Spring Boot cung cấp `ExitCodeGenerator` và `SpringApplication.exit(...)` để quyết định mã thoát của ứng dụng. Nếu ứng dụng cần truyền kết quả command ra hệ điều hành theo một chính sách riêng, hãy lưu kết quả cuối cùng vào thành phần quản lý trạng thái tiến trình, rồi cung cấp mã đó cho `ExitCodeGenerator`.

Ví dụ tối giản về launcher Spring Boot:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class CliApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(CliApplication.class, args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
```

Đoạn launcher gọi `SpringApplication.exit` để lấy mã từ các bean `ExitCodeGenerator` hoặc exception có triển khai hợp đồng đó, rồi truyền mã cho `System.exit`. Trong ứng dụng thực tế, bean `ExitCodeGenerator` phải đọc kết quả command hoặc exception cuối cùng theo chính sách của ứng dụng. Đừng thêm `System.exit` vào thân command vì điều đó có thể kết thúc JVM ngay giữa interactive session và bỏ qua vòng đời đóng context.

Nếu ứng dụng chỉ chạy interactive shell, thường không cần kết thúc tiến trình sau mỗi command. Chỉ thiết kế bridge cấp tiến trình khi chạy non-interactive hoặc khi có yêu cầu vận hành rõ ràng.

Tài liệu Spring Boot mô tả `ExitCodeGenerator`, `SpringApplication.exit` và việc truyền mã trả về cho `System.exit`. <Link url="https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-exit" title="Spring Boot — Application Exit"/>.

## 13. `CommandExecutionException` trong API 4.x

Spring Shell 4.0.2 bổ sung constructor `CommandExecutionException(String message, int exitCode)` và phương thức `getExitCode()`. API này biểu diễn lỗi thực thi kèm mã lỗi ở tầng command executor/runner.

```java
import org.springframework.shell.core.command.CommandExecutionException;

throw new CommandExecutionException(
        "Không thể hoàn tất thao tác đồng bộ", 20);
```

Đây là API cấp thấp khi cần tạo exception thực thi có mã cụ thể. Với lỗi nghiệp vụ phát sinh trong command, `ExitStatusExceptionMapper` thường dễ quản lý hơn vì nó tập trung quy tắc ánh xạ theo loại exception. Không bọc một exception bằng `CommandExecutionException` rồi lại ánh xạ nó sang mã thành công.

Nếu dùng constructor có `exitCode`, kiểm tra đúng phiên bản Spring Shell vì constructor này có từ 4.0.2. <Link url="https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandExecutionException.html" title="CommandExecutionException API — Spring Shell 4.x"/>.

## 14. Kiểm thử `ExitStatus` và mapper

Nên kiểm thử mapper độc lập trước, sau đó kiểm thử command và cuối cùng kiểm thử tiến trình non-interactive.

Unit test cho mapper:

```java
import org.junit.jupiter.api.Test;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DeploymentExceptionMapperTest {

    private final ExitStatusExceptionMapper mapper = exception -> {
        if (exception instanceof ProjectNotFoundException) {
            return new ExitStatus(3, "không tìm thấy dự án");
        }
        if (exception instanceof DeploymentPermissionException) {
            return new ExitStatus(4, "không có quyền triển khai dự án này");
        }
        return ExitStatus.EXECUTION_ERROR;
    };

    @Test
    void mapsMissingProject() {
        ExitStatus status = mapper.apply(new ProjectNotFoundException("demo"));
        assertEquals(3, status.code());
    }

    @Test
    void mapsUnknownFailureToExecutionError() {
        ExitStatus status = mapper.apply(new IllegalStateException("unexpected"));
        assertEquals(ExitStatus.EXECUTION_ERROR, status);
    }
}
```

Ma trận kiểm thử tích hợp:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Command thành công | Trả `ExitStatus.OK` |
| Command chủ động trả mã riêng | `code()` và `description()` đúng |
| Exception nghiệp vụ đã biết | Mapper trả mã đã quy ước |
| Exception chưa biết | Trả trạng thái lỗi chung, không thành công giả |
| Sai cú pháp hoặc thiếu option | Parser báo usage error; không giả định command mapper xử lý |
| Command unavailable | Trạng thái availability được báo đúng |
| Annotation registration | Bean mapper được tham chiếu đúng tên |
| Programmatic registration | Mapper được gắn qua builder hoặc setter phù hợp |
| Interactive shell | Command lỗi nhưng shell vẫn tiếp tục hoạt động |
| Non-interactive runner | Tiến trình trả mã thoát như automation mong đợi |
| Script nhiều command | Hành vi khi một command lỗi được kiểm tra trên đúng phiên bản |

Unit test hoặc `ShellTestClient` có thể xác nhận command output và trạng thái ở cấp framework. Để xác nhận mã thoát của JVM, hãy chạy JAR trong một tiến trình riêng và đọc exit code của tiến trình; test trong cùng JVM không đủ để chứng minh mã mà CI nhận được.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Command luôn trả thành công | Builder adapter chỉ xử lý output, còn logic lỗi bị nuốt hoặc không ném exception | Trả trạng thái riêng bằng `AbstractCommand` hoặc để exception đi qua mapper |
| Mapper không được gọi | Exception xảy ra trước khi command bắt đầu hoặc mapper chưa gắn đúng command | Phân biệt parser/validation với execution; kiểm tra bean name và builder |
| Mọi lỗi đều thành `EXECUTION_ERROR` | Mapper không phân loại exception nghiệp vụ hoặc exception đã bị bọc | Kiểm tra loại exception và cause theo chính sách rõ ràng |
| Mã riêng thay đổi giữa các bản | Không có bảng mã lỗi ổn định | Công bố mã và giữ tương thích cho script |
| Interactive shell thoát khi command lỗi | Gọi `System.exit` trực tiếp trong command | Trả `ExitStatus` và để shell quản lý vòng lặp |
| CI luôn nhận mã `0` | Chỉ kiểm tra output hoặc dùng Spring Shell 4.0.0/4.0.1 có lỗi runner | Dùng 4.0.2 trở lên và test tiến trình thực |
| Mã command khác mã process | Nhầm `ExitStatus` với JVM process exit code | Thiết kế rõ runner và bridge Spring Boot khi cần |
| Thông báo lỗi lộ thông tin nội bộ | Đưa exception message/stack trace nguyên bản vào description | Trả thông báo an toàn; lưu chi tiết trong log có kiểm soát |

## 16. Bài thực hành tổng hợp

Xây dựng command `deploy` có mã kết quả ổn định cho automation:

1. Tạo các exception nghiệp vụ `ProjectNotFoundException`, `DeploymentPermissionException` và `InvalidDeploymentRequestException`.
2. Tạo `ExitStatusExceptionMapper` ánh xạ ba exception trên thành mã riêng hoặc hằng `ExitStatus` phù hợp.
3. Gắn mapper bằng `@Command(exitStatusExceptionMapper = "deploymentExceptionMapper")`.
4. Tạo command programmatic tương đương và gắn mapper bằng `.exitStatusExceptionMapper(...)`.
5. Tạo một command kế thừa `AbstractCommand` để trả mã riêng khi không có dữ liệu mới.
6. Viết bảng mã lỗi trong README để script và CI sử dụng.
7. Chạy command trong interactive mode và xác nhận shell vẫn hoạt động sau lỗi.
8. Chạy ứng dụng bằng non-interactive runner với từng trường hợp thành công và thất bại; kiểm tra mã thoát ở cấp tiến trình.
9. Thử với Spring Shell 4.0.3 hoặc mới hơn và xác nhận lỗi runner luôn trả `0` đã được khắc phục từ 4.0.2.
10. Viết unit test mapper, integration test command và end-to-end test cho JAR.

Sau bài thực hành, bạn cần giải thích được vì sao command trả `ExitStatus`, exception mapper chuyển lỗi thành status như thế nào, vì sao mã command và mã JVM có thể khác nhau, và cách kiểm chứng mã mà CI thực sự nhận.

## 17. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| ExitStatus | Đọc và tạo được `ExitStatus(code, description)` |
| Hằng dựng sẵn | Chọn đúng `OK`, `USAGE_ERROR`, `AVAILABILITY_ERROR`, `EXECUTION_ERROR` |
| Command | Trả status tùy chỉnh bằng `AbstractCommand` khi cần |
| Exception mapping | Viết mapper phân loại exception nghiệp vụ và có fallback |
| Registration | Gắn mapper bằng `@Command` hoặc `Command.Builder` |
| Phân tầng lỗi | Phân biệt parsing, conversion, validation, availability và execution |
| Automation | Thiết kế mã ổn định để script/CI xử lý |
| Process exit | Phân biệt status command với exit code JVM và kiểm thử non-interactive runner |
| Version | Biết lỗi non-interactive exit code luôn 0 được sửa từ Spring Shell 4.0.2 |

## Tài liệu tham khảo

- [Spring Shell 4.0.3 — Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell 4.0.3 — `ExitStatus` API](https://javadoc.io/static/org.springframework.shell/spring-shell-core/4.0.3/org/springframework/shell/core/command/ExitStatus.html)
- [Spring Shell 4.0.3 — `ExitStatusExceptionMapper` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/exit/ExitStatusExceptionMapper.html)
- [Spring Shell 4.0.3 — `AbstractCommand` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/AbstractCommand.html)
- [Spring Shell 4.0.3 — Execution](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell 4.0.3 — `NonInteractiveShellRunner` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html)
- [Spring Shell 4.0.3 — `CommandExecutionException` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandExecutionException.html)
- [Spring Shell — Release Notes](https://github.com/spring-projects/spring-shell/releases)
- [Spring Boot — Application Exit](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-exit)
