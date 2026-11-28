# Ánh xạ exit code và `@ExceptionResolver` trong nhánh 3.x

Một ứng dụng dòng lệnh thường cần cho biết command đã thành công hay thất bại bằng một mã số. Người dùng có thể đọc thông báo trên terminal, còn script, scheduler hoặc CI có thể kiểm tra exit code để quyết định bước tiếp theo. Ví dụ, pipeline chỉ chạy bước phát hành khi lệnh kiểm tra dữ liệu trả về mã `0`.

Trong Spring Shell 3.x, kết quả xử lý exception có thể chứa thông báo và exit code thông qua `CommandHandlingResult`. Với command đăng ký bằng annotation legacy, `@ExceptionResolver` cho phép đặt phương thức xử lý exception ngay trong `@ShellComponent`. Với command đăng ký bằng `CommandRegistration`, có thể dùng `CommandExceptionResolver` và `withExitCode()` để cấu hình riêng. Bài viết sử dụng API Spring Shell 3.4.3.

## Exit code cho biết điều gì?

Exit code là một số nguyên biểu thị kết quả thực thi của command trong chế độ non-interactive. Theo quy ước thông dụng:

- `0`: command thành công.
- Khác `0`: command thất bại hoặc không thể hoàn thành theo yêu cầu.

Spring Shell 3.4.x có ánh xạ mặc định:

| Trường hợp | Exit code mặc định |
| --- | ---: |
| Lỗi phân tích option của command | `2` |
| Lỗi tổng quát khi thực thi | `1` |
| Các trường hợp còn lại, bao gồm thành công | `0` |

Các mã tùy chỉnh như `3`, `4` hoặc `5` do ứng dụng quy ước. Hãy ghi lại ý nghĩa của từng mã để script bên ngoài có thể xử lý nhất quán. Không nên dùng mã `0` cho một thao tác thất bại chỉ vì exception đã được bắt và hiển thị thông báo.

### Exit code chỉ có ý nghĩa trong non-interactive mode

Trong REPL tương tác, shell vẫn tiếp tục chạy sau một command. Exit code của `CommandHandlingResult` không phải là tín hiệu kết thúc tiến trình cho mỗi lệnh. Giá trị này có ý nghĩa khi shell thực thi command trong chế độ non-interactive, chẳng hạn được gọi từ script hoặc CI.

Spring Shell 3.3.x trở đi chỉ bật `NonInteractiveShellRunner` theo mặc định. Các runner khác có thể được bật/tắt bằng thuộc tính:

```yaml
spring:
  shell:
    noninteractive:
      enabled: true
    interactive:
      enabled: false
```

Khi cần xác minh mã tiến trình mà hệ điều hành hoặc CI nhận được, hãy chạy ứng dụng đã đóng gói trong chế độ non-interactive và kiểm tra exit code của chính tiến trình. Kiểm thử command trong REPL chỉ xác minh thông báo và luồng xử lý bên trong shell.

## `CommandHandlingResult` chứa thông báo và mã thoát

`CommandHandlingResult` thuộc package `org.springframework.shell.command`. Đây là kiểu kết quả mà exception resolver có thể trả về. Nó có thể chứa:

- `message()`: thông báo sẽ được ghi ra shell.
- `exitCode()`: mã kết quả, có ý nghĩa khi shell chạy non-interactive.
- `isPresent()` và `isEmpty()`: cho biết kết quả có nội dung hay không.

Tạo kết quả bằng các factory method:

```java
CommandHandlingResult.of("Không tìm thấy khách hàng.\n", 4);
CommandHandlingResult.of("Có lỗi xảy ra.\n");
CommandHandlingResult.empty();
```

Nếu chỉ truyền message, mã thoát sẽ do quy tắc xử lý tương ứng quyết định. Khi muốn kiểm soát cả thông báo lẫn mã, hãy truyền hai tham số để tránh phụ thuộc vào mặc định.

## Xử lý exception bằng `@ExceptionResolver`

Với mô hình annotation legacy của Spring Shell 3.x, lớp `@ShellComponent` có thể khai báo một hoặc nhiều phương thức `@ExceptionResolver`. Các phương thức này xử lý exception phát sinh từ những phương thức command trong component.

Ví dụ command tìm khách hàng:

```java
import org.springframework.shell.command.CommandHandlingResult;
import org.springframework.shell.command.annotation.ExceptionResolver;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @ShellMethod(key = "customer show", value = "Hiển thị khách hàng theo mã")
    public String show(@ShellOption(value = "--code") String code) {
        return customerService.findByCode(code)
                .orElseThrow(() -> new CustomerNotFoundException(code))
                .toString();
    }

    @ExceptionResolver
    public CommandHandlingResult handleCustomerNotFound(
            CustomerNotFoundException exception) {
        return CommandHandlingResult.of(
                "Không tìm thấy khách hàng được yêu cầu.\n", 4);
    }
}
```

Khi `customerService.findByCode(...)` không tìm thấy dữ liệu, command ném `CustomerNotFoundException`. Spring Shell tìm phương thức resolver phù hợp trong `CustomerCommands`, gọi nó và ghi thông báo trong `CommandHandlingResult`. Trong chế độ non-interactive, kết quả này mang exit code `4`.

`@ExceptionResolver` có thể đặt trên phương thức xử lý exception trong `@ShellComponent`. Nếu thuộc tính `value` để trống, loại exception được suy ra từ tham số exception của phương thức. Có thể chỉ định rõ các loại cần bắt:

```java
@ExceptionResolver({IllegalArgumentException.class, DateTimeException.class})
public CommandHandlingResult handleInvalidInput(Exception exception) {
    return CommandHandlingResult.of(
            "Dữ liệu ngày hoặc tham số không hợp lệ.\n", 2);
}
```

Nên khai báo kiểu exception cụ thể trên tham số khi có thể. Khi nhiều resolver cùng khớp, Spring Shell dùng `ExceptionDepthComparator` để ưu tiên kiểu phù hợp nhất; exception ở root thường được ưu tiên hơn exception chỉ xuất hiện trong cause lồng bên trong. Cơ chế này cho phép xử lý exception được bọc trong một exception khác ở nhiều cấp cause.

### Các kiểu trả về của `@ExceptionResolver`

Phương thức resolver hỗ trợ ba kiểu trả về chính:

| Kiểu trả về | Hành vi | Exit code mặc định |
| --- | --- | ---: |
| `String` | Nội dung chuỗi được ghi ra shell | `1` |
| `CommandHandlingResult` | Có thể đặt cả message và exit code | Theo kết quả trả về |
| `void` | Được xem là đã xử lý exception hoàn toàn | `0` |

Với `String` hoặc `void`, có thể dùng `@ExitCode` để chỉ định mã khác. Với `CommandHandlingResult`, đặt mã trực tiếp trong `CommandHandlingResult.of(message, code)`.

Ví dụ resolver trả `String` và đặt mã `5`:

```java
import org.springframework.shell.command.annotation.ExitCode;

@ExceptionResolver
@ExitCode(code = 5)
public String handleRemoteServiceUnavailable(RemoteServiceUnavailableException exception) {
    return "Dịch vụ từ xa hiện không khả dụng. Vui lòng thử lại sau.";
}
```

Nếu trả `String` mà không có `@ExitCode`, mã mặc định là `1`. Annotation `@ExitCode` ghi đè mã mặc định của phương thức resolver.

Resolver `void` có thể nhận thêm `Terminal` để tự ghi nội dung:

```java
import java.io.PrintWriter;

import org.jline.terminal.Terminal;
import org.springframework.shell.command.annotation.ExitCode;

@ExceptionResolver
@ExitCode(code = 5)
public void handleRemoteServiceUnavailable(
        RemoteServiceUnavailableException exception,
        Terminal terminal) {

    PrintWriter writer = terminal.writer();
    writer.println("Dịch vụ từ xa hiện không khả dụng.");
    writer.flush();
}
```

Nếu resolver `void` không đặt `@ExitCode`, exception được xem là đã xử lý và exit code là `0`. Vì vậy, nếu phương thức xử lý một lỗi thực sự khiến command thất bại, hãy đặt mã khác `0`.

## Phân biệt `@ExceptionResolver` và `CommandExceptionResolver`

Hai API có mục đích gần nhau nhưng cách đăng ký khác nhau:

| API | Cách hoạt động | Phạm vi |
| --- | --- | --- |
| `@ExceptionResolver` | Spring Shell tìm phương thức xử lý exception trong `@ShellComponent` | Phù hợp với command theo mô hình annotation legacy |
| `CommandExceptionResolver` | Implement interface `resolve(Exception)` và trả `CommandHandlingResult` | Đăng ký toàn cục hoặc gắn vào `CommandRegistration` |

`CommandExceptionResolver` thuộc package `org.springframework.shell.command`. Ví dụ triển khai:

```java
import org.springframework.shell.command.CommandExceptionResolver;
import org.springframework.shell.command.CommandHandlingResult;

public class CustomerCommandExceptionResolver implements CommandExceptionResolver {

    @Override
    public CommandHandlingResult resolve(Exception exception) {
        if (exception instanceof CustomerNotFoundException) {
            return CommandHandlingResult.of(
                    "Không tìm thấy khách hàng.\n", 4);
        }

        // Không xử lý loại exception này; nhường resolver tiếp theo.
        return null;
    }
}
```

Có thể đăng ký resolver như một Spring bean để dùng toàn cục:

```java
@Bean
CustomerCommandExceptionResolver customerCommandExceptionResolver() {
    return new CustomerCommandExceptionResolver();
}
```

Hoặc gắn riêng vào một `CommandRegistration`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.CommandRegistration;

@Configuration
public class CustomerCommandConfiguration {

    @Bean
    CommandRegistration customerShowCommand(CustomerService customerService) {
        return CommandRegistration.builder()
                .command("customer show")
                .withOption()
                    .longNames("code")
                    .type(String.class)
                    .required()
                    .and()
                .withErrorHandling()
                    .resolver(new CustomerCommandExceptionResolver())
                    .and()
                .withTarget()
                    .function(context -> customerService.findByCode(
                                    context.getOptionValue("code"))
                            .orElseThrow(() -> new CustomerNotFoundException(
                                    context.getOptionValue("code")))
                            .toString())
                    .and()
                .build();
    }
}
```

Resolver gắn riêng cho command được gọi trước resolver toàn cục. Resolver toàn cục được sắp xếp theo precedence; có thể dùng `@Order` hoặc `Ordered` để kiểm soát thứ tự so với resolver mặc định của Spring Shell. Nếu resolver không nhận diện exception, trả `null` để resolver tiếp theo có cơ hội xử lý.

Chọn `@ExceptionResolver` khi muốn xử lý exception gần với nhóm command annotation. Chọn `CommandExceptionResolver` khi cần tái sử dụng logic trên nhiều command hoặc cần kiểm soát resolver bằng cấu hình Java.

## Ánh xạ exit code bằng `CommandRegistration.withExitCode()`

Command được đăng ký bằng `CommandRegistration` có thể định nghĩa ánh xạ giữa exception và mã thoát qua `withExitCode()`:

```java
CommandRegistration.builder()
        .command("customer delete")
        .withExitCode()
            .map(CustomerNotFoundException.class, 4)
            .map(exception -> {
                if (exception instanceof DuplicateCustomerException) {
                    return 3;
                }
                return 1;
            })
            .and()
        .build();
```

Có thể ánh xạ một lớp exception sang mã cố định hoặc cung cấp hàm nhận `Throwable` để tính mã động. Cấu hình này thuộc từng `CommandRegistration` và áp dụng cho command được đăng ký theo cách programmatic.

Tài liệu Spring Shell 3.4.x lưu ý rằng mapping của `withExitCode()` không được cấu hình bằng annotation-based command registration. Điều này không có nghĩa `@ExitCode` vô hiệu: `@ExitCode` là annotation dành cho phương thức `@ExceptionResolver`, còn `withExitCode()` là API mapping exception trên `CommandRegistration`. Hai cơ chế có phạm vi khác nhau.

## Dùng `ExitCodeGenerator` của Spring Boot

Một exception tùy chỉnh có thể implement `org.springframework.boot.ExitCodeGenerator` để cung cấp mã thoát:

```java
import org.springframework.boot.ExitCodeGenerator;

public class CustomerNotFoundException
        extends RuntimeException implements ExitCodeGenerator {

    public CustomerNotFoundException(String code) {
        super("Customer not found: " + code);
    }

    @Override
    public int getExitCode() {
        return 4;
    }
}
```

Spring Shell 3.x tích hợp với cơ chế exit code của Spring Boot, vì vậy exception có thể mang mã thoát riêng qua `getExitCode()`. Cách này hữu ích khi mã lỗi gắn với chính loại exception và có thể được sử dụng ở nhiều nơi. Nếu cần một thông điệp thân thiện riêng cho người dùng terminal, vẫn nên dùng resolver để chuyển exception thành `CommandHandlingResult`.

Không nên đặt mã thoát tùy tiện ở nhiều tầng cùng lúc. Nếu exception đã implement `ExitCodeGenerator`, resolver cũng trả mã khác và registration cũng có mapping riêng, hãy xác định rõ cơ chế nào có quyền quyết định trong luồng xử lý cụ thể rồi kiểm thử để tránh kết quả khó đoán.

## Quy ước mã thoát cho ứng dụng

Hãy định nghĩa một bảng mã dùng chung thay vì để mỗi command tự chọn số riêng:

| Mã | Ý nghĩa ví dụ |
| ---: | --- |
| `0` | Thành công |
| `1` | Lỗi thực thi không phân loại |
| `2` | Sai cú pháp hoặc lỗi phân tích option |
| `3` | Dữ liệu bị trùng hoặc xung đột |
| `4` | Không tìm thấy tài nguyên |
| `5` | Dịch vụ phụ thuộc không khả dụng |

Đây chỉ là một quy ước mẫu. Ứng dụng cần ghi lại mã và ý nghĩa trong tài liệu vận hành, đặc biệt khi script hoặc CI phân nhánh theo mã. Không dùng cùng một mã cho hai tình huống mà pipeline cần xử lý khác nhau.

## Kiểm thử exception resolver và exit code

Nên kiểm thử cả thông báo lẫn mã thoát. Một resolver có thể hiển thị đúng message nhưng trả sai code; khi đó người dùng tương tác thấy lỗi hợp lý nhưng pipeline lại xem command là thành công.

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Command thành công | Không phát sinh exception và kết quả thành công có mã `0` trong non-interactive mode |
| Lỗi parser | Exit code mặc định là `2` |
| Exception không có resolver tùy chỉnh | Áp dụng xử lý mặc định và mã lỗi tổng quát `1` |
| `@ExceptionResolver` trả `String` | Message xuất hiện và mã mặc định là `1` |
| Resolver trả `String` có `@ExitCode` | Message xuất hiện và mã được đặt đúng |
| Resolver trả `CommandHandlingResult` | Cả message và mã tùy chỉnh đều đúng |
| Resolver `void` | Output được ghi qua `Terminal`; mặc định mã là `0` |
| Exception lồng cause | Resolver khớp đúng loại exception và ưu tiên phù hợp |
| Nhiều resolver | Resolver cụ thể được chọn; resolver trả `null` nhường xử lý tiếp |
| Resolver theo command và toàn cục | Resolver gắn với command chạy trước resolver toàn cục |
| Non-interactive process | Mã tiến trình thực tế khớp với hợp đồng đã định nghĩa |

Kiểm thử resolver riêng giúp xác minh cách phân loại exception. Kiểm thử command qua Spring Shell giúp xác minh exception thực sự được chuyển tới resolver. Cuối cùng, kiểm thử tiến trình đã đóng gói giúp xác minh mã mà shell runner và môi trường bên ngoài nhận được.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `@ExceptionResolver` trên lớp không phải `@ShellComponent` trong mô hình legacy | Spring Shell không phát hiện phương thức resolver theo cơ chế này | Đặt resolver trong `@ShellComponent` phù hợp |
| Trả `String` và nghĩ exit code là `0` | Resolver String mặc định trả mã `1` | Dùng `CommandHandlingResult` hoặc `@ExitCode(code = 0)` nếu thực sự là thành công |
| Resolver `void` xử lý lỗi nhưng không đặt mã | Exception được xem là đã xử lý, mã mặc định `0` | Đặt `@ExitCode` khác `0` khi thao tác thất bại |
| Chỉ trả thông báo mà quên exit code | Script có thể không phân biệt được các loại lỗi | Trả `CommandHandlingResult.of(message, code)` |
| Trả `null` từ resolver và nghĩ lỗi đã được xử lý | Resolver tiếp theo sẽ được gọi | Chỉ trả `null` khi muốn nhường xử lý |
| Cấu hình `withExitCode()` nhưng mong annotation tự áp dụng | Mapping thuộc registration programmatic | Dùng resolver annotation hoặc cấu hình registration đúng cơ chế |
| Kiểm tra exit code trong REPL | Exit code không có ý nghĩa như mã kết thúc tiến trình trong interactive mode | Chạy và kiểm thử non-interactive runner |
| Dùng `0` cho exception nghiệp vụ | CI có thể xem thao tác thất bại là thành công | Dùng mã khác `0` và ghi rõ ý nghĩa |
| Không kiểm thử mã tiến trình | Mã trong kết quả command có thể khác kỳ vọng của script | Kiểm thử ứng dụng đã đóng gói từ shell/CI |

## Quy trình thiết kế exit code

1. Phân loại các lỗi mà command có thể phát sinh.
2. Xây dựng bảng mã thoát ổn định, giữ `0` cho thành công.
3. Với command annotation legacy, đặt `@ExceptionResolver` trong `@ShellComponent` và trả `CommandHandlingResult` khi cần kiểm soát cả message lẫn code.
4. Dùng `@ExitCode` cho resolver trả `String` hoặc `void` khi cần ghi đè mã mặc định.
5. Với command programmatic, chọn `CommandExceptionResolver` hoặc `withExitCode()` theo phạm vi xử lý.
6. Trả `null` từ `CommandExceptionResolver` khi không nhận diện exception để nhường resolver kế tiếp.
7. Kiểm thử trong non-interactive mode và xác nhận process exit code mà script/CI nhận được.

Trong Spring Shell 3.x, `@ExceptionResolver` giúp đặt cách xử lý lỗi cạnh các command annotation, còn `CommandHandlingResult` mang thông báo và mã thoát về cơ chế xử lý kết quả. Khi kết hợp với mapping theo `CommandRegistration` hoặc `ExitCodeGenerator`, ứng dụng có thể cung cấp phản hồi dễ hiểu cho người dùng và mã ổn định cho hệ thống tự động hóa.

## Tài liệu tham khảo

- [Exception Resolving – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/commands/exceptionhandling/resolving.html)
- [@ExceptionResolver – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/commands/exceptionhandling/annotation.html)
- [Exit Code Mappings – Spring Shell 3.4.2](https://docs.spring.io/spring-shell/reference/3.4/commands/exceptionhandling/mappings.html)
- [CommandExceptionResolver API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandExceptionResolver.html)
- [CommandHandlingResult API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandHandlingResult.html)
- [ShellComponent API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/ShellComponent.html)
- [Execution – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/execution.html)
- [Spring Boot Exit Codes – Spring Boot 3.4](https://docs.spring.io/spring-boot/3.4/reference/features/spring-application.html)
