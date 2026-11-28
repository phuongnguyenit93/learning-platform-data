# Gắn bộ ánh xạ lỗi bằng annotation hoặc builder đúng phiên bản

Khi command phát sinh exception, Spring Shell cần quyết định thông điệp nào được hiển thị và mã trạng thái nào đại diện cho kết quả đó. Nếu mọi lỗi đều trở thành một thông báo chung, script và hệ thống CI khó phân biệt lỗi đầu vào, tài nguyên không tồn tại hay lỗi thực thi.

API ánh xạ lỗi thay đổi đáng kể giữa Spring Shell 3.x và 4.x:

- **Spring Shell 3.3:** mô hình annotation legacy dùng `@ExceptionResolver` và có thể kết hợp `@ExitCode`. Mô hình `CommandRegistration` dùng `.withErrorHandling().resolver(...)` và `.withExitCode().map(...)`.
- **Spring Shell 4.x:** API mới thống nhất thành `ExitStatusExceptionMapper`. Command annotation tham chiếu bean qua `exitStatusExceptionMapper`; command builder nhận mapper qua `.exitStatusExceptionMapper(...)`.

Không trộn `CommandExceptionResolver`, `CommandHandlingResult` của 3.x với `ExitStatusExceptionMapper`, `ExitStatus` của 4.x. Bài học dùng Spring Shell 3.3.4 và 4.0.4 làm mốc.

## 1. Vì sao cần ánh xạ exception?

Command có thể thất bại vì nhiều nguyên nhân:

| Tình huống | Ví dụ exception | Phản hồi CLI nên có |
|---|---|---|
| Dữ liệu không hợp lệ | `IllegalArgumentException` | Hướng dẫn sửa đầu vào |
| Không tìm thấy tài nguyên | `ProjectNotFoundException` | Nêu mã project không tồn tại |
| Không đủ quyền | `AccessDeniedException` | Thông báo thao tác bị từ chối |
| Dịch vụ phụ thuộc không sẵn sàng | `ServiceUnavailableException` | Thông báo có thể thử lại |
| Lỗi không dự kiến | `RuntimeException` | Thông báo lỗi thực thi chung |

Một command có thể ném exception từ application service hoặc domain layer. Bộ ánh xạ chuyển exception đó thành kết quả phù hợp với người dùng CLI và môi trường gọi command.

Ví dụ, ứng dụng có thể quy ước mã lỗi: `0` là thành công, `2` là đầu vào không hợp lệ, `4` là không tìm thấy tài nguyên, `5` là thao tác bị từ chối và `1` là lỗi thực thi không phân loại. Đây là quy ước của ứng dụng, không phải mã bắt buộc do Spring Shell áp đặt. Hãy công bố bảng mã và giữ ổn định khi script bên ngoài phụ thuộc vào chúng.

## 2. Phân biệt xử lý lỗi và mã thoát

Hai việc thường xảy ra cùng lúc nhưng có vai trò khác nhau:

- **Xử lý exception:** quyết định lỗi nào được nhận diện, thông điệp nào được hiển thị và exception có được xử lý hay chuyển tiếp.
- **Ánh xạ mã thoát:** xác định mã số đại diện cho kết quả command khi chạy không tương tác.

Trong Spring Shell 3.3, `CommandHandlingResult` có thể mang cả thông điệp và exit code. Trong Spring Shell 4.x, `ExitStatus` là record gồm `code` và `description`.

Mã trạng thái của command cũng cần được phân biệt với mã thoát của tiến trình JVM. Đặc biệt trong Spring Shell 4.x, `ExitStatusExceptionMapper` tạo trạng thái cho command; chỉ cấu hình mapper không tự động cấu hình process exit code. Nếu CI cần nhận mã thoát của tiến trình, hãy xác minh cách runner hoặc lớp tích hợp Spring Boot chuyển kết quả command thành mã tiến trình trong ứng dụng đang triển khai.

Mã thoát có ý nghĩa rõ nhất khi command chạy ở chế độ non-interactive. Trong một phiên REPL, người dùng thường tiếp tục nhập command sau khi một command thất bại.

## 3. Spring Shell 3.3: xử lý lỗi bằng @ExceptionResolver

Trong mô hình annotation legacy của Spring Shell 3.x, lớp command được đánh dấu `@ShellComponent`. Có thể khai báo phương thức `@ExceptionResolver` trong lớp đó để xử lý exception phát sinh từ các command method.

Ví dụ command ném exception khi project không tồn tại:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class ProjectCommands {

    @ShellMethod("Triển khai một project")
    public String deploy(String projectId) {
        throw new ProjectNotFoundException(projectId);
    }
}
```

Khai báo resolver trong cùng lớp:

```java
import org.springframework.shell.command.CommandHandlingResult;
import org.springframework.shell.command.annotation.ExceptionResolver;

@ExceptionResolver
public CommandHandlingResult handleProjectNotFound(
        ProjectNotFoundException exception) {

    return CommandHandlingResult.of(
        "Không tìm thấy project: " + exception.getMessage(),
        4
    );
}
```

Trong ví dụ, `@ExceptionResolver` đánh dấu phương thức xử lý exception; kiểu tham số `ProjectNotFoundException` xác định loại lỗi mà phương thức nhận; `CommandHandlingResult.of(message, exitCode)` trả về thông điệp và mã trạng thái.

Nếu phương thức resolver nhận tham số kiểu `Exception`, có thể chỉ định các loại exception bằng giá trị của annotation:

```java
@ExceptionResolver({
    ProjectNotFoundException.class,
    IllegalArgumentException.class
})
public CommandHandlingResult handleKnownErrors(Exception exception) {
    return CommandHandlingResult.of(
        "Không thể thực hiện command: " + exception.getMessage(),
        2
    );
}
```

Ưu tiên khai báo kiểu exception cụ thể làm tham số khi có thể. Khi nhiều phương thức resolver cùng khớp, Spring Shell dùng độ sâu kiểu exception để lựa chọn; match với exception gốc thường được ưu tiên hơn match với cause lồng bên trong.

### 3.1. Dùng @ExitCode khi resolver trả về String hoặc void

`@ExitCode` cho phép đặt mã thoát cho phương thức `@ExceptionResolver`.

Nếu resolver trả về `String`, chuỗi được ghi ra console. Không có `@ExitCode`, trường hợp này dùng mã mặc định `1`:

```java
import org.springframework.shell.command.annotation.ExceptionResolver;
import org.springframework.shell.command.annotation.ExitCode;

@ExceptionResolver
@ExitCode(code = 4)
public String handleProjectNotFound(ProjectNotFoundException exception) {
    return "Không tìm thấy project: " + exception.getMessage();
}
```

Nếu resolver trả về `void`, Spring Shell xem exception đã được xử lý và mặc định dùng mã `0`. Với lỗi cần thể hiện thất bại, hãy đặt `@ExitCode` rõ ràng:

```java
import org.springframework.shell.command.annotation.ExceptionResolver;
import org.springframework.shell.command.annotation.ExitCode;
import org.springframework.shell.jline.Terminal;

@ExceptionResolver
@ExitCode(code = 4)
public void handleProjectNotFound(
        ProjectNotFoundException exception,
        Terminal terminal) {

    terminal.writer().println(
        "Không tìm thấy project: " + exception.getMessage()
    );
    terminal.writer().flush();
}
```

`CommandHandlingResult` thường dễ đọc hơn khi cần trả cả thông điệp và mã thoát trong một giá trị. `@ExitCode` hữu ích khi muốn giữ kiểu trả về `String` hoặc `void`.

## 4. Spring Shell 3.3: gắn resolver bằng CommandRegistration.Builder

Với mô hình đăng ký command bằng `CommandRegistration`, có thể gắn `CommandExceptionResolver` trực tiếp vào registration qua `withErrorHandling()`.

Một resolver là implementation của `CommandExceptionResolver`. Phương thức `resolve(Exception)` trả về `CommandHandlingResult` nếu xử lý được lỗi; trả về `null` để chuyển exception cho resolver tiếp theo.

Ví dụ:

```java
import org.springframework.shell.command.CommandExceptionResolver;
import org.springframework.shell.command.CommandHandlingResult;

public class ProjectCommandExceptionResolver
        implements CommandExceptionResolver {

    @Override
    public CommandHandlingResult resolve(Exception exception) {
        if (exception instanceof ProjectNotFoundException) {
            return CommandHandlingResult.of(
                "Không tìm thấy project: " + exception.getMessage(),
                4
            );
        }

        if (exception instanceof IllegalArgumentException) {
            return CommandHandlingResult.of(
                "Dữ liệu command không hợp lệ: " + exception.getMessage(),
                2
            );
        }

        // Không xử lý loại lỗi này; để resolver tiếp theo quyết định.
        return null;
    }
}
```

Gắn resolver vào một `CommandRegistration`:

```java
CommandRegistration.builder()
    .command("project deploy")
    .withErrorHandling()
        .resolver(new ProjectCommandExceptionResolver())
        .and()
    // Khai báo target và các thuộc tính command tại đây.
    .build();
```

Resolver gắn trực tiếp với command được xử lý trước resolver toàn cục. Cách này phù hợp khi một command có quy tắc lỗi riêng. Nếu nhiều command dùng chung quy tắc, có thể đăng ký implementation `CommandExceptionResolver` thành Spring bean để xử lý toàn cục. Dùng `@Order` hoặc `Ordered` để điều chỉnh thứ tự resolver toàn cục so với các resolver mặc định.

## 5. Spring Shell 3.3: ánh xạ exception sang mã bằng withExitCode

`withErrorHandling()` cho phép xử lý exception và trả thông điệp cùng mã trong `CommandHandlingResult`. Nếu chỉ cần ánh xạ exception sang số nguyên, `CommandRegistration.Builder` có thêm `withExitCode()`.

Ví dụ ánh xạ theo loại exception:

```java
CommandRegistration.builder()
    .command("project deploy")
    .withExitCode()
        .map(ProjectNotFoundException.class, 4)
        .map(IllegalArgumentException.class, 2)
        .and()
    // Khai báo target và các thuộc tính command tại đây.
    .build();
```

Có thể dùng hàm ánh xạ tổng quát nếu mã lỗi được lưu trong exception:

```java
.withExitCode()
    .map(ProjectNotFoundException.class, 4)
    .map(throwable -> {
        if (throwable instanceof CodedProjectException coded) {
            return coded.getExitCode();
        }
        return 1;
    })
    .and()
```

`map(Class<? extends Throwable>, int)` khai báo mã cho một loại exception. `map(Function<Throwable, Integer>)` cho phép tự tính mã dựa trên exception nhận được.

| Builder API | Vai trò |
|---|---|
| `withErrorHandling().resolver(...)` | Xử lý exception và có thể trả thông điệp cùng mã |
| `withExitCode().map(...)` | Ánh xạ exception sang mã số |
| Kết hợp hai API | Tách thông điệp lỗi và quy tắc mã thoát khi cần |

Tài liệu Spring Shell 3.3 nêu rõ mã thoát không thể tùy chỉnh bằng cấu hình annotation của mô hình `CommandRegistration` mới. Khi cần ánh xạ mã ở mô hình này, hãy dùng builder. `@ExceptionResolver` và `@ExitCode` thuộc cơ chế resolver method của mô hình `@ShellComponent` legacy.

### 5.1. Resolver toàn cục và resolver riêng command

Spring Shell 3.3 cho phép đăng ký `CommandExceptionResolver` theo hai phạm vi:

- **Toàn cục:** khai báo resolver thành bean trong ApplicationContext.
- **Theo command:** gắn resolver vào `CommandRegistration.Builder`.

Resolver riêng command được xét trước resolver toàn cục. Với các resolver toàn cục, thứ tự có thể được điều khiển bằng `@Order` hoặc `Ordered`.

Một resolver không xử lý exception nên trả về `null`. Nếu resolver trả về một `CommandHandlingResult`, exception được xem là đã được xử lý và chuỗi resolver không cần xử lý tiếp exception đó.

Không nên viết resolver toàn cục bắt mọi exception rồi trả một kết quả thành công. Điều này làm mất thông tin thất bại và khiến script tiếp tục như thể command đã chạy đúng.

## 6. Spring Shell 4.x: ExitStatusExceptionMapper

Spring Shell 4.x thay mô hình exception handling của 3.x bằng `ExitStatusExceptionMapper`. Interface này thuộc package:

```java
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;
```

`ExitStatusExceptionMapper` là functional interface nhận một `Exception` và trả về `ExitStatus`. `ExitStatus` biểu diễn trạng thái command bằng `code` và `description`.

Một số trạng thái có sẵn:

| Hằng | Ý nghĩa |
|---|---|
| `ExitStatus.OK` | Command thành công |
| `ExitStatus.EXECUTION_ERROR` | Lỗi khi thực thi |
| `ExitStatus.USAGE_ERROR` | Cú pháp hoặc cách sử dụng không hợp lệ |
| `ExitStatus.AVAILABILITY_ERROR` | Command chưa khả dụng |

Có thể tạo mapper thành Spring bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
public class CommandErrorConfiguration {

    @Bean
    public ExitStatusExceptionMapper projectErrorMapper() {
        return exception -> {
            if (exception instanceof ProjectNotFoundException) {
                return new ExitStatus(
                    4,
                    "Không tìm thấy project: " + exception.getMessage()
                );
            }

            if (exception instanceof IllegalArgumentException) {
                return new ExitStatus(
                    2,
                    "Dữ liệu command không hợp lệ: " + exception.getMessage()
                );
            }

            return ExitStatus.EXECUTION_ERROR;
        };
    }
}
```

Mapper có thể trả `ExitStatus` riêng cho từng loại exception. Với exception không được nhận diện, nên trả trạng thái lỗi chung phù hợp thay vì trả `ExitStatus.OK`.

## 7. Gắn mapper bằng thuộc tính của @Command trong 4.x

Trong mô hình annotation mới của Spring Shell 4.x, `@Command` có thuộc tính `exitStatusExceptionMapper`. Giá trị là tên bean mapper trong Spring context.

Ví dụ:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ProjectCommands {

    @Command(
        name = "project deploy",
        description = "Triển khai project",
        exitStatusExceptionMapper = "projectErrorMapper"
    )
    public String deploy(
            @Option(longName = "id", required = true) String projectId) {

        deployProject(projectId);
        return "Đã triển khai project " + projectId;
    }

    private void deployProject(String projectId) {
        throw new ProjectNotFoundException(projectId);
    }
}
```

Tên `projectErrorMapper` phải khớp với tên bean đã khai báo. Nếu phương thức `@Bean` có tên `projectErrorMapper`, Spring dùng tên đó làm bean name mặc định. Có thể đặt tên rõ ràng trong `@Bean("...")` nếu cần.

Đây là thuộc tính của annotation `@Command` trong API mới 4.x. Không áp dụng thuộc tính này cho `@ShellMethod` hoặc giả định rằng `@Command` của mọi phiên bản 3.x đều có cùng thuộc tính.

## 8. Gắn mapper bằng Command.Builder trong 4.x

Khi tạo command theo hướng programmatic, có thể truyền trực tiếp mapper vào `Command.Builder.exitStatusExceptionMapper(...)`.

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
public class ProjectCommandConfiguration {

    @Bean
    public Command deployProjectCommand(
            ExitStatusExceptionMapper projectErrorMapper) {

        return Command.builder()
            .name("project deploy")
            .description("Triển khai project")
            .exitStatusExceptionMapper(projectErrorMapper)
            .execute(context -> {
                throw new ProjectNotFoundException("payments");
            });
    }
}
```

Builder nhận instance `ExitStatusExceptionMapper`. Trong ví dụ, Spring inject bean `projectErrorMapper` vào phương thức `@Bean`, sau đó builder gắn mapper vào command.

| Cách khai báo | Cách liên kết mapper |
|---|---|
| Annotation `@Command` | Tên bean qua `exitStatusExceptionMapper = "projectErrorMapper"` |
| Programmatic `Command.Builder` | Instance qua `.exitStatusExceptionMapper(projectErrorMapper)` |

Chọn annotation khi command được khai báo trên phương thức Spring bean. Chọn builder khi command được tạo trực tiếp bằng code và cần truyền mapper như một dependency.

## 9. Bảng chuyển đổi API giữa 3.x và 4.x

Khi nâng cấp, cần chuyển cả interface, kiểu kết quả và cách gắn mapper:

| Nhu cầu | Spring Shell 3.3 | Spring Shell 4.x |
|---|---|---|
| Kiểu resolver | `CommandExceptionResolver` | `ExitStatusExceptionMapper` |
| Kiểu kết quả | `CommandHandlingResult` | `ExitStatus` |
| Annotation method legacy | `@ExceptionResolver`, có thể dùng `@ExitCode` | Không dùng cơ chế legacy này |
| Annotation command mới | `@ExceptionResolver` trong `@ShellComponent` legacy; mã của `CommandRegistration` không cấu hình bằng annotation | `@Command(exitStatusExceptionMapper = "beanName")` |
| Builder xử lý exception | `.withErrorHandling().resolver(...)` | `.exitStatusExceptionMapper(mapper)` |
| Builder ánh xạ mã | `.withExitCode().map(...)` | Mapper trả về `ExitStatus` gồm mã và mô tả |
| Mô hình command chính | `CommandRegistration` hoặc annotation | `Command` và `Command.Builder` |

Spring Shell 4.x thay `CommandExceptionResolver` của 3.x bằng `ExitStatusExceptionMapper`. Đây không chỉ là đổi tên class: API kết quả đã thay từ `CommandHandlingResult` sang `ExitStatus`, và builder mới gắn mapper trực tiếp vào `Command`.

### 9.1. Ví dụ chuyển đổi một quy tắc lỗi

Quy tắc nghiệp vụ: khi project không tồn tại, hiển thị thông báo và trả mã `4`.

Trong Spring Shell 3.3:

```java
@ExceptionResolver
public CommandHandlingResult handleProjectNotFound(
        ProjectNotFoundException exception) {

    return CommandHandlingResult.of(
        "Không tìm thấy project: " + exception.getMessage(),
        4
    );
}
```

Trong Spring Shell 4.x:

```java
@Bean
ExitStatusExceptionMapper projectErrorMapper() {
    return exception -> {
        if (exception instanceof ProjectNotFoundException) {
            return new ExitStatus(
                4,
                "Không tìm thấy project: " + exception.getMessage()
            );
        }
        return ExitStatus.EXECUTION_ERROR;
    };
}
```

Khi chuyển đổi, hãy giữ nguyên hợp đồng mã lỗi và nội dung thông báo mà script hoặc người dùng đang phụ thuộc. Sau đó cập nhật nơi gắn mapper theo mô hình command của phiên bản mới.

## 10. Kiểm thử bộ ánh xạ lỗi

Mapper nên được kiểm thử độc lập với shell. Mỗi loại exception cần có kỳ vọng cụ thể về mã và thông điệp.

Ví dụ kiểm thử mapper của Spring Shell 4.x:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

class ProjectErrorMapperTests {

    private final ExitStatusExceptionMapper mapper = exception -> {
        if (exception instanceof ProjectNotFoundException) {
            return new ExitStatus(4, "Project not found");
        }
        if (exception instanceof IllegalArgumentException) {
            return new ExitStatus(2, "Invalid input");
        }
        return ExitStatus.EXECUTION_ERROR;
    };

    @Test
    void mapsMissingProject() {
        ExitStatus status = mapper.apply(
            new ProjectNotFoundException("payments")
        );

        assertEquals(4, status.code());
        assertEquals("Project not found", status.description());
    }

    @Test
    void mapsInvalidInput() {
        ExitStatus status = mapper.apply(
            new IllegalArgumentException("bad identifier")
        );

        assertEquals(2, status.code());
        assertEquals("Invalid input", status.description());
    }

    @Test
    void mapsUnexpectedFailure() {
        ExitStatus status = mapper.apply(
            new IllegalStateException("unexpected")
        );

        assertEquals(
            ExitStatus.EXECUTION_ERROR.code(),
            status.code()
        );
    }
}
```

Với Spring Shell 3.3, kiểm thử `CommandExceptionResolver.resolve(...)` bằng các exception tương ứng và xác minh `CommandHandlingResult.message()` cùng `exitCode()`.

Ngoài unit test, nên có kiểm thử tích hợp non-interactive để xác nhận:

- Exception trong command được chuyển thành thông điệp dự kiến.
- Mã trạng thái của command có giá trị như quy ước.
- Resolver không nhận diện exception thì lỗi được xử lý theo cơ chế mặc định.
- Mã thoát của tiến trình được kiểm tra riêng nếu pipeline phụ thuộc vào nó.

## 11. Nguyên tắc thiết kế resolver và mapper

**Ánh xạ theo loại exception có ý nghĩa.** Không nên ánh xạ mọi exception thành cùng một mã nếu caller cần phân biệt lỗi đầu vào, tài nguyên không tồn tại và lỗi hệ thống.

**Giữ mã lỗi ổn định.** Script có thể dùng exit code để quyết định retry, rollback hoặc dừng pipeline. Thay đổi mã đã công bố cần được xem như thay đổi hợp đồng CLI.

**Thông điệp hướng tới người dùng.** Hãy giải thích điều kiện cần sửa hoặc bước tiếp theo. Tránh trả stack trace hoặc thông tin nội bộ trong thông điệp mặc định.

**Không che giấu lỗi không dự kiến.** Với resolver 3.x, trả `null` khi chưa xử lý để resolver khác tiếp tục. Với mapper 4.x, trả trạng thái lỗi chung cho exception chưa phân loại.

**Không trả mã thành công cho exception thất bại.** Resolver `void` trong mô hình legacy có thể được xem là đã xử lý với mã `0`; chỉ dùng khi thao tác thực sự được xử lý thành công hoặc đặt `@ExitCode` phù hợp.

**Không nhầm trạng thái command với process exit code.** Kiểm tra cách runner và ứng dụng chuyển kết quả ra mã tiến trình, đặc biệt trong Spring Shell 4.x.

**Giữ resolver ít phụ thuộc.** Việc ánh xạ nên dựa trên loại lỗi và dữ liệu lỗi. Tránh gọi thêm dịch vụ từ xa hoặc thực hiện nghiệp vụ mới trong resolver.

## 12. Các lỗi thường gặp

**Dùng `@ExceptionResolver` của 3.x trong Spring Shell 4.x.** Mô hình legacy đã bị loại bỏ trong 4.x. Chuyển sang `ExitStatusExceptionMapper`.

**Dùng `CommandExceptionResolver` với `Command.Builder` 4.x.** Builder 4.x nhận `ExitStatusExceptionMapper` qua `.exitStatusExceptionMapper(...)`.

**Trả `CommandHandlingResult` trong mapper 4.x.** Kiểu kết quả của API 4.x là `ExitStatus`.

**Gắn sai tên bean trong `@Command`.** `exitStatusExceptionMapper` nhận bean name. Nếu tên không khớp, Spring Shell không thể lấy mapper mong muốn.

**Nhầm `withErrorHandling()` với `withExitCode()` trong 3.3.** Một API xử lý exception và thông điệp; API còn lại ánh xạ exception sang mã số.

**Kỳ vọng `@Command` của 3.3 có thuộc tính exit mapper như 4.x.** Trong 3.3, tài liệu exit code nêu rõ không thể tùy chỉnh mã bằng cấu hình annotation của mô hình `CommandRegistration`; hãy dùng builder. `@ExceptionResolver` là cơ chế method của mô hình `@ShellComponent` legacy.

**Resolver trả `null` nhưng không có resolver nào khác xử lý.** Khi không nhận diện exception, lỗi sẽ đi tiếp theo chuỗi xử lý mặc định. Hãy xác định rõ hành vi fallback.

**Mapper luôn trả `ExitStatus.OK`.** Điều này làm command thất bại có vẻ như thành công. Chỉ trả mã thành công khi thao tác thực sự hoàn tất đúng.

**Cho rằng mapper 4.x đã đặt mã thoát JVM.** `ExitStatus` là trạng thái command. Cần kiểm tra riêng process exit code trong môi trường non-interactive.

## 13. Checklist triển khai

- [ ] Xác nhận phiên bản Spring Shell đang dùng.
- [ ] Chọn đúng API của phiên bản: 3.3 resolver hoặc 4.x exception mapper.
- [ ] Với 3.3 legacy, dùng `@ExceptionResolver` trong lớp `@ShellComponent`.
- [ ] Với 3.3 legacy, dùng `@ExitCode` nếu cần đặt mã cho resolver trả `String` hoặc `void`.
- [ ] Với `CommandRegistration` 3.3, dùng `.withErrorHandling().resolver(...)` khi cần xử lý exception.
- [ ] Dùng `.withExitCode().map(...)` để ánh xạ exception sang số trong 3.3.
- [ ] Với 4.x, triển khai hoặc khai báo bean `ExitStatusExceptionMapper`.
- [ ] Gắn bean qua `@Command(exitStatusExceptionMapper = "...")` hoặc instance qua `Command.Builder`.
- [ ] Phân biệt `CommandHandlingResult` với `ExitStatus`.
- [ ] Định nghĩa mã cho lỗi nghiệp vụ và lỗi không dự kiến.
- [ ] Giữ thông điệp rõ ràng và không tiết lộ dữ liệu nhạy cảm.
- [ ] Kiểm thử cả exception đã ánh xạ và exception không nhận diện.
- [ ] Kiểm tra exit code của command và process exit code riêng biệt.
- [ ] Kiểm tra script hoặc CI dùng đúng hợp đồng mã lỗi đã công bố.

## 14. Tài liệu tham khảo chính thức

- [Spring Shell 3.3.4 — Exception Handling](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/index.html): tổng quan xử lý exception và mã thoát.
- [Spring Shell 3.3.4 — Exception Resolving](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/resolving.html): CommandExceptionResolver, resolver toàn cục và resolver gắn theo command.
- [Spring Shell 3.3.4 — Exit Code Mappings](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/mappings.html): withExitCode().map(...) và giới hạn cấu hình annotation.
- [Spring Shell 3.3.4 — @ExceptionResolver](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/annotation.html): resolver method, @ExitCode và kiểu trả về.
- [Spring Shell 3.3 API — CommandRegistration.ErrorHandlingSpec](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/CommandRegistration.ErrorHandlingSpec.html): phương thức resolver(...).
- [Spring Shell 3.3 API — CommandRegistration.ExitCodeSpec](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/CommandRegistration.ExitCodeSpec.html): các overload map(...).
- [Spring Shell 4.0.4 — Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html): triển khai và gắn ExitStatusExceptionMapper bằng annotation hoặc builder.
- [Spring Shell 4.0.4 — Command API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html): thuộc tính exitStatusExceptionMapper.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): chuyển từ CommandExceptionResolver sang ExitStatusExceptionMapper.

Khi cấu hình xử lý lỗi, hãy bắt đầu từ phiên bản và mô hình đăng ký command. Spring Shell 3.3 có resolver method legacy và builder của CommandRegistration; Spring Shell 4.x dùng ExitStatusExceptionMapper với annotation @Command hoặc Command.Builder. Giữ riêng thông điệp, trạng thái command và mã thoát tiến trình để người dùng terminal cũng như hệ thống automation nhận được kết quả nhất quán.

