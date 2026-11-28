# Command, CommandRegistry và AbstractCommand trong kiến trúc 4.x

## 1. Bức tranh tổng thể

Trong Spring Shell 4.x, command được mô hình hóa thành một đối tượng có tên, mô tả, tham số, khả năng thực thi và trạng thái kết thúc. Các đối tượng này được tập hợp trong **CommandRegistry** để shell có thể tìm command theo tên hoặc alias, cung cấp trợ giúp, gợi ý và thực thi lệnh người dùng nhập.

Có hai cách tạo command thường gặp:

- **Khai báo bằng annotation:** đánh dấu phương thức trong một Spring bean bằng annotation **@Command**. Spring Shell tạo phần tích hợp để phương thức đó hoạt động như một command.
- **Khai báo bằng API:** tạo một đối tượng triển khai **Command**, thường thông qua **Command.builder()** hoặc kế thừa **AbstractCommand**.

Ba thành phần trong tiêu đề có quan hệ rõ ràng:

| Thành phần | Trách nhiệm |
|---|---|
| **Command** | Hợp đồng mô tả một command và cách thực thi nó trong một CommandContext. |
| **CommandRegistry** | Lưu trữ và tra cứu các command mà ứng dụng shell đang biết; hỗ trợ đăng ký và hủy đăng ký khi chạy. |
| **AbstractCommand** | Lớp cơ sở triển khai Command, cung cấp metadata và các tiện ích chung để lớp con tập trung vào phần xử lý. |

Luồng xử lý khái quát:

~~~mermaid
flowchart LR
    A[Phương thức @Command] --> D[Đối tượng Command]
    B[Command.builder] --> D
    C[Subclass AbstractCommand] --> D
    D --> R[CommandRegistry]
    U[Input của người dùng] --> P[CommandParser]
    R --> P
    P --> E[CommandExecutor]
    E --> X[Command.execute CommandContext]
    X --> S[ExitStatus]
    S --> O[ShellRunner / tiến trình]
~~~

Sơ đồ mô tả trách nhiệm ở mức khái niệm. Cách tạo command có thể khác nhau, nhưng sau khi được đăng ký, shell làm việc với cùng hợp đồng Command.

## 2. Command: hợp đồng thực thi command

Trong Spring Shell 4.x, **org.springframework.shell.core.command.Command** là một functional interface. Phương thức thực thi cốt lõi là:

~~~java
ExitStatus execute(CommandContext commandContext) throws Exception;
~~~

Điều này có nghĩa một command nhận **CommandContext** làm ngữ cảnh thực thi và trả về **ExitStatus**. Context cung cấp thông tin của lần gọi hiện tại, gồm đầu vào đã phân tích, registry, bộ đọc input và writer để ghi output.

Ngoài phương thức execute, Command còn cung cấp các thuộc tính mặc định để mô tả command:

- **name:** tên command dùng khi người dùng nhập lệnh.
- **description:** mô tả ngắn, thường được hiển thị trong danh sách trợ giúp.
- **help:** nội dung hướng dẫn chi tiết hơn.
- **group:** nhóm command để tổ chức danh sách lệnh.
- **aliases:** các tên thay thế có thể dùng để gọi cùng command.
- **options và arguments:** khai báo option có tên và argument theo vị trí.
- **availabilityProvider:** xác định command hiện có thể thực thi hay chưa.
- **completionProvider:** cung cấp gợi ý hoàn thành đầu vào.
- **hidden:** cho biết command có được hiển thị trong danh sách trợ giúp thông thường hay không.

Command là hợp đồng ở tầng thực thi. Nó không bắt buộc phải được viết dưới dạng một lớp cụ thể: có thể dùng builder, lớp kế thừa hoặc adapter do framework tạo ra từ phương thức khai báo bằng annotation.

### CommandContext và ExitStatus

**CommandContext** là ngữ cảnh của một lần gọi command. Trong command được tạo bằng API, có thể sử dụng context để đọc dữ liệu đã phân tích và ghi kết quả:

~~~java
commandContext.outputWriter().println("Đã xử lý xong");
~~~

Không nên tạo một writer toàn cục hoặc ghi trực tiếp ra console ở mọi nơi. Dùng writer được cung cấp trong context giúp command làm việc với cơ chế output của shell và thuận tiện hơn khi kiểm thử.

**ExitStatus** biểu diễn kết quả thực thi của command. Giá trị phổ biến là **ExitStatus.OK** khi thao tác thành công. Trạng thái này là dữ liệu kết quả để shell hoặc runner xử lý tiếp; nội dung in ra màn hình và trạng thái kết thúc là hai khái niệm khác nhau. Một command có thể in thông báo lỗi rồi vẫn trả trạng thái thành công nếu lập trình viên chọn sai quy ước, vì vậy cần thiết kế rõ các nhánh thành công và thất bại.

## 3. Tạo command bằng Command.Builder

Với command ngắn, **Command.builder()** là cách khai báo trực tiếp và gọn. Builder cho phép thiết lập tên, mô tả, nhóm, trợ giúp, alias, option, argument, availability provider, completion provider và xử lý ngoại lệ. Sau khi cấu hình, gọi một trong các overload **execute(...)** để tạo đối tượng command.

Ví dụ khai báo command liệt kê sản phẩm:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
class InventoryCommandConfiguration {

    @Bean
    Command inventoryListCommand() {
        return Command.builder()
                .name("inventory list")
                .description("Liệt kê sản phẩm trong kho")
                .group("Inventory")
                .help("Hiển thị danh sách sản phẩm hiện có trong kho.")
                .execute(context -> {
                    context.outputWriter().println("SKU-001  Bàn phím");
                    context.outputWriter().println("SKU-002  Chuột");
                });
    }
}
~~~

Ở ví dụ này, overload nhận **Consumer<CommandContext>** được dùng vì command chỉ cần ghi output. Builder trả về một đối tượng **AbstractCommand**, vốn triển khai **Command**, nên có thể khai báo kiểu trả về của bean là Command. API này không yêu cầu gọi thêm phương thức build().

Khi cần trả về nội dung dạng chuỗi, có thể dùng overload nhận **Function<CommandContext, String>**:

~~~java
@Bean
Command inventoryStatusCommand() {
    return Command.builder()
            .name("inventory status")
            .description("Xem trạng thái kho")
            .execute(context -> "Kho đang hoạt động bình thường");
}
~~~

Builder phù hợp với command có xử lý đơn giản và metadata được khai báo ngay tại nơi tạo command. Khi logic lớn hơn, nên đưa nghiệp vụ vào service riêng rồi gọi service từ command để giữ phần giao tiếp dòng lệnh mỏng và dễ kiểm thử.

## 4. CommandRegistry: danh mục command của shell

**org.springframework.shell.core.command.CommandRegistry** là lớp quản lý tập command mà shell có thể sử dụng. Trong API Spring Shell 4.0.4, đây là một lớp cụ thể, không phải interface. Nếu được khai báo như một Spring bean, registry được Spring tự động nạp các command có trong application context sau khi các singleton đã được khởi tạo. Registry cũng hỗ trợ thêm và gỡ command trong thời gian chạy.

Các phương thức thường dùng:

| Phương thức | Công dụng |
|---|---|
| **getCommands()** | Lấy tập command hiện có. |
| **getCommandByName(name)** | Tìm command theo tên; có thể không tìm thấy và trả về null. |
| **getCommandByAlias(name)** | Tìm command thông qua alias. |
| **getCommandsByPrefix(prefix)** | Lấy các command có tên bắt đầu bằng tiền tố. |
| **registerCommand(command)** | Đăng ký command trong lúc ứng dụng đang chạy. |
| **unregisterCommand(command)** | Hủy đăng ký command. |
| **clearCommands()** | Xóa toàn bộ command khỏi registry. |

Tên là định danh của command trong registry. Vì vậy, cần chọn tên rõ ràng và tránh đăng ký hai command có cùng tên. Alias chỉ là tên thay thế để gọi command, không phải một command nghiệp vụ độc lập.

### Đăng ký tự động từ Spring context

Với command được khai báo thành Spring bean, Spring Shell tự đưa chúng vào registry. Ví dụ ở phần trước trả về một bean kiểu Command, nên ứng dụng không cần tự gọi registerCommand cho chính bean đó.

Với mô hình annotation, Spring Shell 4.x nhận diện phương thức được đánh dấu bằng **@Command** trong một Spring-managed bean:

~~~java
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class InventoryCommands {

    @Command(
            name = "inventory count",
            description = "Đếm số sản phẩm trong kho",
            group = "Inventory")
    public void count(CommandContext context) {
        context.outputWriter().println("Tổng số sản phẩm: 2");
    }
}
~~~

Trong ứng dụng Spring Boot, cơ chế auto-configuration tự bật việc quét command. Ứng dụng Spring không dùng Boot cần bật cơ chế khám phá bằng **@EnableCommand** trên lớp cấu hình. Dù được khai báo bằng annotation hay API, command sau khi được tạo vẫn được đưa vào registry để shell tra cứu và thực thi.

### Đăng ký và hủy đăng ký động

Đăng ký động hữu ích khi tập command phụ thuộc vào trạng thái ứng dụng, quyền người dùng hoặc một tính năng được bật sau khi khởi động. Ví dụ, chỉ thêm command chẩn đoán khi người vận hành bật chế độ hỗ trợ:

~~~java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandRegistry;
import org.springframework.stereotype.Component;

@Component
class DiagnosticsCommandManager {

    private final CommandRegistry registry;
    private Command diagnosticsCommand;

    DiagnosticsCommandManager(CommandRegistry registry) {
        this.registry = registry;
    }

    public void enableDiagnostics() {
        if (diagnosticsCommand != null) {
            return;
        }

        diagnosticsCommand = Command.builder()
                .name("system diagnostics")
                .description("Hiển thị thông tin chẩn đoán")
                .execute(context -> {
                    context.outputWriter().println("Diagnostic mode is enabled");
                });

        registry.registerCommand(diagnosticsCommand);
    }

    public void disableDiagnostics() {
        if (diagnosticsCommand == null) {
            return;
        }

        registry.unregisterCommand(diagnosticsCommand);
        diagnosticsCommand = null;
    }
}
~~~

Đoạn mã giữ lại đúng đối tượng command đã đăng ký để có thể truyền chính đối tượng đó khi hủy đăng ký. Việc kiểm tra null giúp tránh đăng ký lặp khi tính năng đã được bật hoặc hủy đăng ký khi command chưa tồn tại. Trong ứng dụng thực tế, hai phương thức này cần được gọi từ luồng điều khiển phù hợp, chẳng hạn sau khi xác thực quyền hoặc khi bật/tắt một tính năng.

Không nên gọi registerCommand cho một command bean vốn đã được registry tự nạp, vì như vậy có thể tạo đăng ký lặp hoặc xung đột tên. Hãy chọn cơ chế tự động qua bean cho command tồn tại xuyên suốt vòng đời ứng dụng; dùng đăng ký động khi command thực sự xuất hiện hoặc biến mất theo trạng thái runtime.

## 5. AbstractCommand: lớp cơ sở cho command tùy chỉnh

**AbstractCommand** là lớp trừu tượng triển khai **Command**. Lớp này giữ các metadata như tên, mô tả, nhóm, nội dung trợ giúp và trạng thái ẩn; đồng thời cung cấp các tiện ích dùng chung để tạo command.

Các constructor nhận những mức metadata khác nhau:

- **AbstractCommand(name, description)**: khai báo tên và mô tả ngắn.
- **AbstractCommand(name, description, group)**: bổ sung nhóm command.
- **AbstractCommand(name, description, group, help)**: bổ sung hướng dẫn chi tiết.
- **AbstractCommand(name, description, group, help, hidden)**: bổ sung cờ ẩn command.

Lớp con cần triển khai phương thức **doExecute(CommandContext)** và trả về **ExitStatus**. Khi shell gọi **execute(CommandContext)**, phần triển khai của lớp cơ sở cung cấp đường thực thi chung; logic riêng của command nằm trong doExecute. AbstractCommand còn có helper **println(message, commandContext)** để ghi thông báo và **isHelp(option)** để nhận diện option trợ giúp. Các helper này giảm phần mã lặp khi tự viết command.

Ví dụ tạo command đếm sản phẩm bằng AbstractCommand:

~~~java
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;

class InventoryCountCommand extends AbstractCommand {

    InventoryCountCommand() {
        super(
                "inventory count",
                "Đếm số sản phẩm trong kho",
                "Inventory",
                "Đếm các sản phẩm hiện có trong kho và in tổng số.",
                false);
    }

    @Override
    public ExitStatus doExecute(CommandContext commandContext) {
        println("Tổng số sản phẩm: 2", commandContext);
        return ExitStatus.OK;
    }
}
~~~

Để Spring quản lý và tự đăng ký đối tượng này, có thể tạo bean trả về kiểu Command:

~~~java
@Bean
Command inventoryCountCommand() {
    return new InventoryCountCommand();
}
~~~

Trong ứng dụng thực tế, lớp command có thể nhận service qua constructor và gọi service trong doExecute. Ví dụ trên chỉ minh họa cấu trúc kế thừa; dữ liệu đếm đang được cố định để tập trung vào hợp đồng thực thi.

### Khi nào dùng AbstractCommand?

Nên cân nhắc AbstractCommand khi command cần:

- Tùy chỉnh cách thực thi ở mức thấp, trực tiếp làm việc với CommandContext.
- Kiểm soát ExitStatus được trả về sau khi xử lý.
- Tái sử dụng một lớp cơ sở chung cho nhiều command tự xây.
- Sử dụng helper in output và xử lý option trợ giúp do lớp cơ sở cung cấp.

Với command chỉ in một chuỗi hoặc thực hiện một hành động ngắn, Command.Builder thường ít mã hơn. Không cần kế thừa AbstractCommand chỉ để tận dụng Spring dependency injection; cả bean Command được tạo bằng builder lẫn lớp con AbstractCommand đều có thể được khai báo trong Spring context.

## 6. So sánh ba cách tiếp cận

| Tiêu chí | Command.Builder | AbstractCommand | Annotation @Command |
|---|---|---|---|
| Cách định nghĩa | Cấu hình đối tượng bằng builder | Tạo lớp con và override doExecute | Đánh dấu phương thức trong Spring bean |
| Phần xử lý | Lambda Consumer hoặc Function | Phương thức doExecute | Thân phương thức Java |
| Mức kiểm soát | Vừa đủ cho command đơn giản đến trung bình | Cao, phù hợp command cần tùy chỉnh sâu | Tập trung vào chữ ký phương thức và metadata annotation |
| Đăng ký | Khai báo bean Command hoặc register động | Khai báo bean Command hoặc register động | Spring Shell khám phá phương thức trong bean |
| Phù hợp khi | Command gọn, logic có thể tách ra service | Cần logic thực thi tùy chỉnh hoặc lớp cơ sở tái sử dụng | Muốn khai báo command theo phong cách Spring declarative |

Ba cách tiếp cận cùng hướng đến hợp đồng Command và registry. Có thể dùng kết hợp trong một ứng dụng, nhưng nên chọn cách thống nhất cho các command có cùng phong cách để đội phát triển dễ đọc và bảo trì.

## 7. Những thay đổi cần nhớ khi chuyển từ Spring Shell 3.x sang 4.x

Spring Shell 4.x thay đổi đáng kể mô hình command. Khi đọc ví dụ cũ, cần kiểm tra phiên bản trước khi sao chép mã.

| Spring Shell 3.x | Spring Shell 4.x |
|---|---|
| Annotation cũ như **@ShellComponent**, **@ShellMethod**, **@ShellOption** | Dùng **@Command**, **@Option**, **@Argument** và các annotation mới trong package command.annotation. |
| Command từng là marker interface trong mô hình cũ | Command là functional interface có phương thức execute và trả ExitStatus. |
| CommandCatalog và CommandRegistration là các khái niệm trong API đăng ký cũ | CommandRegistry quản lý các đối tượng Command. |
| Khai báo command bằng API đăng ký cũ | Dùng Command.builder(), bean Command hoặc AbstractCommand. |

Các annotation **@ShellComponent**, **@ShellMethod**, **@ShellOption** đã bị loại bỏ trong Spring Shell 4.x. Một ứng dụng nâng cấp cần chuyển sang annotation mới thay vì giữ lại các import cũ. Trong mô hình annotation mới, **@Command** được đặt trên phương thức; lớp chứa phương thức phải là Spring bean. Việc dùng **@Command** trên cấp lớp để gom nhóm command không còn được hỗ trợ; dùng **@CommandGroup** khi cần khai báo prefix và nhóm cho nhiều command trong cùng lớp.

Mô hình programmatic cũng thay đổi: thay vì xây CommandRegistration và đăng ký vào CommandCatalog như trước, hãy tạo Command và để Spring tự đăng ký bean hoặc dùng CommandRegistry để thêm/gỡ command khi chạy. Đọc migration guide của đúng phiên bản trước khi chuyển các command có completion, availability hoặc exception mapping tùy chỉnh.

## 8. Lỗi thiết kế thường gặp

**Đăng ký trùng command:** một command đã được khai báo thành bean sẽ được registry tự nạp. Gọi registerCommand thêm lần nữa mà không có lý do rõ ràng có thể gây xung đột tên hoặc trạng thái khó hiểu.

**Dùng alias như một tên nghiệp vụ mới:** alias chỉ là lối gọi thay thế cho cùng một command. Nếu hai thao tác có quy tắc hoặc kết quả khác nhau, hãy khai báo hai command riêng với tên rõ ràng.

**Đặt toàn bộ nghiệp vụ vào lambda hoặc doExecute:** command là ranh giới giao tiếp với terminal. Hãy để service thực hiện quy tắc nghiệp vụ, còn command chịu trách nhiệm nhận đầu vào, gọi service và trình bày kết quả.

**Bỏ qua ExitStatus:** thông báo thành công hoặc lỗi trên terminal không tự quyết định kết quả tiến trình. Với command dùng trong script, cần trả trạng thái phù hợp và kiểm tra cách runner chuyển trạng thái đó thành mã thoát.

**Gỡ command không đúng đối tượng:** khi đăng ký động, lưu tham chiếu tới đối tượng Command đã đăng ký để truyền lại khi unregisterCommand. Tìm command bằng tên rồi tự tạo một đối tượng mới không đảm bảo đó là đối tượng đã được đăng ký.

**Dùng ví dụ 3.x trong dự án 4.x:** package, annotation và cơ chế đăng ký đã thay đổi. Hãy xác nhận import và API theo Javadoc của Spring Shell 4.x mà dự án đang dùng.

## 9. Quy trình lựa chọn và triển khai

Khi thêm một command mới, có thể thực hiện theo thứ tự sau:

1. Xác định tên command, mô tả, nhóm, option và argument mà người dùng cần.
2. Chọn cách định nghĩa: annotation cho phương thức Spring bean, builder cho command gọn hoặc AbstractCommand cho xử lý cần tùy chỉnh sâu.
3. Đưa nghiệp vụ vào service và giữ command tập trung vào input/output.
4. Đăng ký command bằng Spring bean nếu nó luôn tồn tại; dùng CommandRegistry khi command cần được thêm hoặc gỡ theo trạng thái runtime.
5. Kiểm tra tên và alias để tránh trùng lặp, đồng thời cung cấp mô tả và trợ giúp có ý nghĩa.
6. Kiểm thử việc tìm command, phân tích input, output, trạng thái kết thúc và hành vi khi command không khả dụng.

## Kết luận

Trong Spring Shell 4.x, Command là hợp đồng thực thi, CommandRegistry là nơi quản lý danh mục command, còn AbstractCommand là lớp cơ sở giúp triển khai hợp đồng đó với các tiện ích có sẵn. Command.Builder phù hợp với command ngắn, AbstractCommand phù hợp khi cần tùy chỉnh sâu, và annotation @Command phù hợp với cách khai báo theo Spring bean. Hiểu ranh giới giữa ba thành phần giúp thiết kế command nhất quán, đăng ký đúng vòng đời và kiểm soát rõ kết quả thực thi.

## Tài liệu tham khảo

- [Spring Shell 4.x – Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4.x API – Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html)
- [Spring Shell 4.x API – CommandRegistry](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandRegistry.html)
- [Spring Shell 4.x API – AbstractCommand](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/AbstractCommand.html)
- [Spring Shell – v4 migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
