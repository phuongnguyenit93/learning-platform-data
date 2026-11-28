# AbstractCommand và đích thực thi trả về ExitStatus trong 4.x

Spring Shell 4.x cho phép đăng ký command bằng code thông qua các bean triển khai `Command`. Khi cần kiểm soát rõ cách command chạy, có thể kế thừa `AbstractCommand` và cài đặt phương thức `doExecute(CommandContext)`. Phương thức này là đích thực thi của command và phải trả về một `ExitStatus` để mô tả kết quả chạy.

Cách làm này phù hợp với command cần điều phối service, xử lý đầu vào ở mức thấp, ghi output theo ý muốn hoặc trả mã kết quả riêng cho tác vụ tự động. Nó cũng giúp command được tạo hoàn toàn bằng Java mà không cần khai báo method bằng annotation.

Các ví dụ trong bài sử dụng API Spring Shell 4.x, thuộc package `org.springframework.shell.core.command`. API 3.x có package và mô hình đăng ký khác; không sao chép import của 3.x vào dự án 4.x.

## Command, AbstractCommand và doExecute

`Command` là hợp đồng mà shell dùng để mô tả và thực thi một lệnh. Nó cung cấp tên, mô tả, nhóm trợ giúp, alias, tùy chọn, đối số, cơ chế availability/completion và phương thức `execute(CommandContext)`.

`AbstractCommand` là lớp cơ sở trừu tượng triển khai `Command`. Lớp này lưu metadata như tên, mô tả, nhóm và nội dung trợ giúp; đồng thời cung cấp các tiện ích để xử lý tùy chọn trợ giúp `-h`/`--help` và ghi thông báo ra output của shell. Khi kế thừa, lớp con tập trung cài đặt `doExecute(CommandContext)`.

| Thành phần | Vai trò |
|---|---|
| `Command` | Hợp đồng chung cho một command đã đăng ký |
| `AbstractCommand` | Lớp cơ sở triển khai `Command`, cung cấp metadata và helper |
| `CommandContext` | Ngữ cảnh của một lần gọi command: input đã phân tích, registry, reader và writer |
| `doExecute(...)` | Phần xử lý cụ thể do lớp con triển khai |
| `ExitStatus` | Kết quả thực thi gồm mã số và mô tả |

```mermaid
flowchart TD
    A[Bean triển khai Command] --> B[CommandRegistry]
    U[Người dùng hoặc tham số tiến trình] --> P[CommandParser]
    P --> C[CommandContext]
    B --> E[CommandExecutor]
    C --> E
    E --> F[Command.execute(context)]
    F --> G[AbstractCommand.execute(context)]
    G --> H[doExecute(context)]
    H --> I[Thực hiện nghiệp vụ và ghi output]
    I --> J[Trả ExitStatus]
    J --> K[Shell xử lý kết quả]
```

Luồng này thể hiện trách nhiệm ở mức khái niệm. Parser tạo đầu vào đã phân tích; `CommandExecutor` tìm command trong registry và thực thi nó với `CommandContext`. Khi command là một lớp con của `AbstractCommand`, phần xử lý tùy biến nằm trong `doExecute`.

## Tạo command bằng bean

Trong mô hình programmatic, một command có thể được khai báo thành bean kiểu `Command`. Spring Shell 4.x tự đưa các bean `Command` trong application context vào `CommandRegistry`. Do đó, trong ứng dụng Spring Boot thông thường, chỉ cần khai báo bean command là đủ để shell nhận diện nó.

Ví dụ dưới đây tạo command `health` để kiểm tra trạng thái một service:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;

@Configuration
class SystemCommandConfiguration {

    @Bean
    Command healthCommand(HealthService healthService) {
        return new AbstractCommand(
                "health",
                "Kiểm tra tình trạng dịch vụ",
                "Hệ thống"
        ) {
            @Override
            public ExitStatus doExecute(CommandContext context) {
                if (healthService.isHealthy()) {
                    println("Dịch vụ đang hoạt động.", context);
                    return ExitStatus.OK;
                }

                println("Dịch vụ chưa sẵn sàng.", context);
                return new ExitStatus(20, "SERVICE_UNHEALTHY");
            }
        };
    }
}
```

`HealthService` là service do ứng dụng định nghĩa. Constructor của `AbstractCommand` nhận tên command, mô tả và nhóm. `doExecute` gọi service, ghi thông tin cho người dùng bằng helper `println`, rồi trả về trạng thái tương ứng.

Khi bean được tạo, Spring Shell đăng ký command `health`. Người dùng có thể gọi lệnh trong phiên shell hoặc cung cấp lệnh khi khởi chạy ứng dụng ở chế độ không tương tác. Không cần tự gọi `CommandRegistry.registerCommand()` cho bean đã được auto-registration.

## Các constructor và metadata của AbstractCommand

Spring Shell 4.x cung cấp các constructor sau:

| Constructor | Metadata được truyền |
|---|---|
| `AbstractCommand(name, description)` | Tên và mô tả |
| `AbstractCommand(name, description, group)` | Thêm nhóm trợ giúp |
| `AbstractCommand(name, description, group, help)` | Thêm nội dung trợ giúp chi tiết |
| `AbstractCommand(name, description, group, help, hidden)` | Thêm cờ ẩn khỏi danh sách command thông thường |

Hãy chọn constructor phù hợp với mức thông tin mà command cần công bố. `description` nên ngắn để hiển thị trong danh sách trợ giúp; `help` có thể mô tả cú pháp và ví dụ sử dụng. `group` giúp gom các command theo miền chức năng. Cờ `hidden` chỉ điều khiển khả năng hiển thị trong các danh sách trợ giúp; nó không phải cơ chế bảo mật hay phân quyền.

Ngoài metadata constructor, `AbstractCommand` còn cung cấp các phương thức để lấy tên, mô tả, nhóm, alias, options, availability và completion provider. Có thể cấu hình alias, options, availability provider, completion provider và `ExitStatusExceptionMapper` thông qua các setter tương ứng.

## CommandContext cung cấp gì?

`CommandContext` trong 4.x là record chứa dữ liệu của lần gọi command. Các thành phần chính gồm:

- `parsedInput()`: đầu vào đã được parser phân tích.
- `commandRegistry()`: registry chứa các command mà shell biết đến.
- `outputWriter()`: `PrintWriter` dùng để ghi output.
- `inputReader()`: thành phần đọc dữ liệu bổ sung từ người dùng.

Context cũng có các phương thức tiện ích để lấy đối số theo vị trí và lấy tùy chọn theo tên dài, tên ngắn hoặc tên bất kỳ. Ví dụ:

```java
import org.springframework.shell.core.command.CommandOption;

CommandOption option = context.getOptionByName("verbose");
if (option != null && Boolean.parseBoolean(option.value())) {
    context.outputWriter().println("Đang chạy ở chế độ chi tiết.");
}
```

`getOptionByName()` có thể trả về `null` nếu tùy chọn không tồn tại trong context. Khi đọc một tùy chọn không bắt buộc, cần kiểm tra kết quả trước khi truy cập `value()`. Tương tự, `getArgumentByIndex()` có thể không có phần tử ở vị trí được yêu cầu.

Trong ví dụ `health`, command không cần đối số nên chỉ dùng `println`. Với command có nhiều tham số hoặc cần đọc tương tác thêm, hãy dùng `CommandContext` để lấy đúng dữ liệu đã được parser và shell chuẩn bị.

## Trả về ExitStatus

`ExitStatus` là record của Spring Shell 4.x gồm hai thành phần:

```java
ExitStatus status = new ExitStatus(20, "SERVICE_UNHEALTHY");
int code = status.code();
String description = status.description();
```

Trong ứng dụng, sử dụng lớp `org.springframework.shell.core.command.ExitStatus` của Spring Shell. Đây là record gồm hai thành phần `code` và `description`, có thể đọc bằng `code()` và `description()`.

Spring Shell cung cấp các trạng thái dựng sẵn:

| Hằng số | Tình huống sử dụng thường gặp |
|---|---|
| `ExitStatus.OK` | Command hoàn tất thành công |
| `ExitStatus.USAGE_ERROR` | Cách gọi hoặc dữ liệu đầu vào không phù hợp |
| `ExitStatus.AVAILABILITY_ERROR` | Command tồn tại nhưng hiện chưa khả dụng |
| `ExitStatus.EXECUTION_ERROR` | Có lỗi trong quá trình thực thi |

Khi các trạng thái dựng sẵn không diễn đạt đủ kết quả nghiệp vụ, có thể tạo trạng thái riêng:

```java
return new ExitStatus(20, "SERVICE_UNHEALTHY");
```

`code` là mã số mà ứng dụng dùng để phân loại kết quả; `description` là mô tả có thể dùng để giải thích kết quả. Hãy thống nhất mã số giữa các command và tài liệu vận hành để script, CI hoặc hệ thống gọi CLI có thể xử lý kết quả một cách ổn định.

Không dùng `null` làm kết quả thành công. Mỗi nhánh xử lý nên trả về một `ExitStatus` rõ ràng. Cũng không nên dùng một mã lỗi chung cho mọi tình huống nếu hệ thống gọi cần phân biệt lỗi đầu vào, lỗi nghiệp vụ và lỗi hạ tầng.

### ExitStatus khác output của command

Output và trạng thái thực thi giải quyết hai việc khác nhau:

- `println(...)` hoặc `context.outputWriter().println(...)` ghi thông tin mà người dùng nhìn thấy.
- `ExitStatus` cho biết command kết thúc với mã và mô tả nào.

Ví dụ, command có thể in `Không tìm thấy khách hàng C1024` và trả về một mã nghiệp vụ `CUSTOMER_NOT_FOUND`. Script có thể đọc output để hiển thị cho người vận hành, đồng thời dựa vào mã trả về để quyết định bước tiếp theo. Đừng chỉ in thông báo lỗi rồi luôn trả `ExitStatus.OK`.

### ExitStatus của command và mã thoát của tiến trình

`ExitStatus` là kết quả của một lần thực thi command. `Command.execute(CommandContext)` và `CommandExecutor.execute(CommandContext)` trả về đối tượng này. Mã thoát của tiến trình Java là kết quả ở cấp ứng dụng/runner, được môi trường khởi chạy quan sát sau khi chương trình kết thúc.

Hai khái niệm liên quan nhưng nằm ở hai ranh giới khác nhau. Trong phiên tương tác, một command có thể trả trạng thái lỗi và shell vẫn tiếp tục chờ lệnh tiếp theo. Khi dùng Spring Shell như công cụ chạy tự động, cần kiểm tra cả `ExitStatus` của command và mã thoát thực tế của tiến trình trong một kiểm thử end-to-end. Không gọi `System.exit()` bên trong `doExecute()` để ép tiến trình kết thúc; làm vậy có thể bỏ qua việc shell xử lý kết quả và đóng application context.

## Xử lý ngoại lệ bằng ExitStatusExceptionMapper

Nếu `doExecute()` phát sinh exception, lỗi được truyền lên shell. Spring Shell 4.x cung cấp `ExitStatusExceptionMapper` để ánh xạ exception thành `ExitStatus` và thông điệp phù hợp. Interface này là một hàm nhận `Exception` và trả về `ExitStatus`.

Ví dụ ánh xạ lỗi nghiệp vụ:

```java
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;
import org.springframework.context.annotation.Bean;

@Bean
ExitStatusExceptionMapper commandExceptionMapper() {
    return exception -> {
        if (exception instanceof CustomerNotFoundException) {
            return new ExitStatus(4, "CUSTOMER_NOT_FOUND");
        }
        return ExitStatus.EXECUTION_ERROR;
    };
}
```

`CustomerNotFoundException` là exception do ứng dụng định nghĩa. Với command kế thừa `AbstractCommand`, có thể gắn mapper qua `setExitStatusExceptionMapper(...)` trước khi trả bean cho Spring. Mô hình `Command.Builder` cũng có tùy chọn `exitStatusExceptionMapper(...)`.

Hãy phân biệt hai cách xử lý lỗi:

- Trường hợp nghiệp vụ dự kiến, chẳng hạn không tìm thấy dữ liệu, có thể được kiểm tra và trả `ExitStatus` ngay trong `doExecute()`.
- Trường hợp exception phát sinh ngoài dự kiến hoặc cần chính sách ánh xạ tập trung có thể được xử lý bằng `ExitStatusExceptionMapper`.

Mapper nên giữ thông tin lỗi đủ để người gọi phân biệt kết quả, nhưng không đưa stack trace, thông tin kết nối hoặc dữ liệu nhạy cảm vào mô tả hiển thị cho người dùng cuối.

## Đăng ký command động bằng CommandRegistry

Trong Spring Shell 4.x, `CommandRegistry` giữ tập hợp command mà ứng dụng shell biết đến. Các bean `Command` trong application context được đăng ký tự động. Khi cần thêm hoặc gỡ command trong thời gian chạy, có thể thao tác với registry theo API của phiên bản.

```java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandRegistry;
import org.springframework.stereotype.Component;

@Component
class DynamicCommandManager {

    private final CommandRegistry registry;

    DynamicCommandManager(CommandRegistry registry) {
        this.registry = registry;
    }

    void register(Command command) {
        registry.registerCommand(command);
    }

    void unregister(Command command) {
        registry.unregisterCommand(command);
    }
}
```

Đăng ký động phù hợp khi command phụ thuộc tính năng được bật, trạng thái phiên hoặc cấu hình tải trong lúc ứng dụng chạy. Với tập command cố định, khai báo bean thường đơn giản và dễ kiểm soát vòng đời hơn. Khi thêm/gỡ command động, cần bảo đảm tên và alias không xung đột với command đã có.

## CommandExecutor gọi đích thực thi như thế nào?

`CommandExecutor` là thành phần thực thi command dựa trên `CommandContext`. Nó sử dụng `CommandRegistry` để tìm command tương ứng với input đã phân tích. Khi tìm được command, executor gọi `execute(context)` và nhận `ExitStatus` trả về.

Nếu command không tồn tại, executor có thể ném `CommandNotFoundException`. Nếu có lỗi khi thực thi, lỗi có thể được biểu diễn bằng `CommandExecutionException`. Vì vậy, lỗi tra cứu và lỗi trong `doExecute()` thuộc hai giai đoạn khác nhau:

| Giai đoạn | Kết quả |
|---|---|
| Phân giải tên command | Tìm command trong registry; không tìm thấy thì báo lỗi command không tồn tại |
| Kiểm tra availability và đối số | Xác nhận command có thể chạy và dữ liệu đầu vào phù hợp |
| Thực thi | Gọi `Command.execute(context)`; với `AbstractCommand`, phương thức này đi vào phần xử lý `doExecute()` |
| Hoàn tất | Nhận `ExitStatus` để shell xử lý kết quả |

`CommandExecutor` là API hữu ích khi kiểm thử hoặc tích hợp luồng thực thi ở mức thấp. Trong ứng dụng Spring Shell thông thường, runner và parser đã điều phối những bước này; command không cần tự tạo `CommandExecutor` để gọi chính nó.

## Chạy command trong chế độ không tương tác

Spring Shell 4.x có `NonInteractiveShellRunner` để chạy một command hoặc một script mà không mở phiên nhập lệnh tương tác. Theo tài liệu 4.x, chế độ này được bật bằng cấu hình:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Khi tắt interactive mode, Spring Shell dùng `NonInteractiveShellRunner`. Runner có thể chạy command từ tham số tiến trình hoặc chạy một tệp script được chỉ định bằng tiền tố `@`, tùy cú pháp đầu vào của runner.

Ví dụ gọi ứng dụng:

```bash
java -jar customer-cli.jar health
```

Hoặc chạy script:

```bash
java -jar customer-cli.jar @daily-checks.txt
```

Trong môi trường tự động, hãy xác minh output, `ExitStatus` và mã thoát của tiến trình bằng một bài kiểm thử tích hợp. Điều này đặc biệt quan trọng khi một script chứa nhiều command hoặc khi runner được cấu hình khác với mặc định. Không nên suy ra mã thoát tiến trình chỉ từ một dòng output trên terminal.

## Khi nào nên dùng AbstractCommand?

| Nhu cầu | Cách triển khai phù hợp |
|---|---|
| Command đơn giản, thực thi bằng một lambda | Dùng `Command.builder()` |
| Cần lớp command riêng với logic nhiều bước | Kế thừa `AbstractCommand` |
| Cần dùng helper `println` và hành vi trợ giúp có sẵn | Kế thừa `AbstractCommand` |
| Cần tái sử dụng một kiểu command tùy chỉnh cho nhiều lệnh | Tạo lớp cơ sở riêng kế thừa `AbstractCommand` |
| Command chỉ cần một phương thức Java được đánh dấu annotation | Dùng annotation model `@Command` |

`AbstractCommand` phù hợp khi command có hành vi riêng và cần một điểm mở rộng rõ ràng. Nếu chỉ ghi một dòng output và trả thành công, `Command.builder()` thường ngắn gọn hơn. Nếu command cần dùng chung logic, có thể tạo lớp cơ sở ứng dụng để chuẩn hóa logging, kiểm tra đầu vào hoặc định dạng trạng thái, nhưng không nên nhồi nghiệp vụ của nhiều miền vào một lớp command lớn.

## Kiểm thử command và ExitStatus

Nên kiểm tra cả hành vi command lẫn kết quả trả về:

1. Xác nhận bean `Command` được đăng ký trong `CommandRegistry` với đúng tên.
2. Gọi command trong tình huống thành công và xác nhận `ExitStatus.OK`.
3. Tạo tình huống nghiệp vụ thất bại và xác nhận mã cùng mô tả trong `ExitStatus` đúng hợp đồng.
4. Kiểm tra output được ghi qua `println` hoặc `outputWriter` và không bị trộn với mô tả trạng thái.
5. Kiểm tra exception được ánh xạ đúng bởi `ExitStatusExceptionMapper`.
6. Kiểm tra command không tồn tại và lỗi thực thi được phân biệt.
7. Chạy thử non-interactive runner để xác nhận mã thoát thực tế mà shell script/CI nhận được.
8. Nếu command được đăng ký động, kiểm tra sau khi register có thể gọi được và sau khi unregister không còn được tìm thấy.

Có thể kiểm thử logic nghiệp vụ của service độc lập, kiểm thử command với dependency giả lập, rồi kiểm thử tích hợp qua parser/runner. Chỉ gọi trực tiếp service sẽ không xác minh quá trình đăng ký command, còn chỉ gọi trực tiếp `doExecute()` sẽ không xác minh parser và `CommandExecutor` đã chọn đúng command.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Bean đã tạo nhưng command không xuất hiện | Bean không có kiểu `Command` hoặc registry chưa nhận bean | Kiểm tra kiểu trả về của `@Bean` và cấu hình Spring Shell |
| Không biên dịch được `AbstractCommand` | Dùng import của Spring Shell 3.x | Dùng package `org.springframework.shell.core.command` trong 4.x |
| `doExecute()` chạy nhưng output không hiển thị | Ghi vào `System.out` thay vì writer của shell hoặc quên flush ở writer tùy biến | Dùng `println(message, context)` hoặc `context.outputWriter()` |
| Luôn trả mã thành công dù nghiệp vụ thất bại | Mọi nhánh đều trả `ExitStatus.OK` | Trả status riêng cho lỗi nghiệp vụ hoặc dùng exception mapper |
| Exception làm shell báo lỗi ngoài dự kiến | Chưa cấu hình mapper hoặc mapper không xử lý loại exception đó | Thêm `ExitStatusExceptionMapper` và kiểm thử các loại lỗi |
| Command không nhận được option | Chưa khai báo metadata option hoặc đọc sai tên option trong context | Kiểm tra cấu hình command và `getOptionByName()` |
| Script/CI nhận mã thoát sai | Chỉ kiểm tra output, chưa kiểm tra runner và process exit code | Chạy kiểm thử end-to-end ở non-interactive mode |

## Khác biệt API từ 3.x sang 4.x

Spring Shell 4.x thay đổi package và cách tổ chức module. Các API core được chuyển sang namespace `org.springframework.shell.core`; `AbstractCommand`, `Command`, `CommandContext` và `ExitStatus` nằm trong `org.springframework.shell.core.command`. `ExitStatusExceptionMapper` nằm trong package con `org.springframework.shell.core.command.exit`.

Mô hình đăng ký programmatic trong 4.x dùng bean kiểu `Command` và `CommandRegistry`. Spring Shell 3.x dùng các API cũ hơn như `CommandRegistration` và `CommandCatalog`. Các annotation legacy `@ShellComponent`, `@ShellMethod` và `@ShellOption` đã bị loại bỏ trong 4.x; khi nâng cấp, hãy chuyển sang annotation mới hoặc đăng ký command bằng code.

Ngoài ra, Spring Shell 4.x tách `spring-shell-core` khỏi JLine. Nếu ứng dụng cần terminal JLine, cần thêm dependency phù hợp; ví dụ trong bài chỉ dùng API core và không phụ thuộc vào JLine.

## Tài liệu tham khảo

- [Spring Shell 4.0.x — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html): đăng ký bằng annotation, programmatic bean và `AbstractCommand`.
- [Spring Shell 4.0.x API — AbstractCommand](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/AbstractCommand.html): constructor, `execute`, `doExecute` và helper methods.
- [Spring Shell 4.0.x API — Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html): hợp đồng command và `Command.Builder`.
- [Spring Shell 4.0.x API — CommandContext](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html): dữ liệu runtime của một lần gọi command.
- [Spring Shell 4.0.x API — CommandOption](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.html): metadata và giá trị runtime của option.
- [Spring Shell 4.0.x API — CommandRegistry](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandRegistry.html): tập command, tra cứu và đăng ký động.
- [Spring Shell 4.0.x API — ExitStatus](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ExitStatus.html): record gồm `code` và `description` cùng các trạng thái dựng sẵn.
- [Spring Shell 4.0.x — Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html): ánh xạ exception thành `ExitStatus`.
- [Spring Shell 4.0.x — Execution](https://docs.spring.io/spring-shell/reference/execution.html): interactive mode và `NonInteractiveShellRunner`.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): thay đổi package, module và mô hình đăng ký command.
