# Command.builder và bean Command trong Spring Shell 4.x

Spring Shell 4.x hỗ trợ hai cách khai báo command: dùng annotation trên phương thức của Spring bean hoặc tạo command bằng API lập trình. Với cách thứ hai, ứng dụng gọi `Command.builder()` để mô tả command, cung cấp hành vi thực thi qua `execute(...)`, rồi công bố kết quả như một Spring bean có kiểu `Command`.

Cách làm này hữu ích khi command được tạo từ cấu hình, plugin, module tích hợp hoặc logic khởi tạo ứng dụng. Nó cũng cho phép định nghĩa metadata và hành vi command ngay trong Java mà không cần tạo một phương thức riêng cho từng command.

Bài học tập trung vào API programmatic của Spring Shell 4.x. Các ví dụ sử dụng package `org.springframework.shell.core.command` và API theo tài liệu Spring Shell 4.0.4. Không nhầm `Command.builder()` của 4.x với `CommandRegistration.builder()` của dòng 3.x.

## 1. Hai mô hình đăng ký command trong Spring Shell 4.x

Spring Shell 4.x cung cấp hai cách chính:

| Mô hình | Cách khai báo | Khi phù hợp |
|---|---|---|
| Annotation | Đánh dấu phương thức trong một Spring bean bằng `@Command` | Command có cấu trúc cố định, mỗi command tương ứng với một phương thức Java |
| Programmatic | Tạo đối tượng `Command` bằng `Command.builder()` rồi đăng ký thành bean | Command cần được mô tả động bằng code, cấu hình hoặc tích hợp module |

Ví dụ annotation:

```java
@Component
class GreetingCommands {

    @Command(name = "hello")
    public String hello() {
        return "Xin chào!";
    }
}
```

Ví dụ programmatic:

```java
@Bean
Command helloCommand() {
    return Command.builder()
        .name("hello")
        .execute(context -> {
            context.outputWriter().println("Xin chào!");
        });
}
```

Cả hai cách đều tạo command có thể được shell gọi. Điểm khác biệt là mô hình annotation dùng metadata gắn với phương thức; mô hình programmatic tạo trực tiếp đối tượng command.

## 2. Command là gì trong API 4.x?

Trong Spring Shell 4.x, `org.springframework.shell.core.command.Command` là một interface biểu diễn một command đã được định nghĩa. Interface này cung cấp thông tin như:

- Tên command.
- Mô tả ngắn và hướng dẫn chi tiết.
- Nhóm command.
- Các alias.
- Các option và argument.
- Provider kiểm tra khả năng thực thi và gợi ý giá trị.
- Hành vi thực thi và kết quả dạng `ExitStatus`.

`Command` là functional interface với phương thức thực thi nhận một `CommandContext`. Đối tượng context cung cấp dữ liệu của lần gọi hiện tại, registry và các phương tiện nhập/xuất.

Lớp `Command.Builder` là builder lồng bên trong interface `Command`. Điểm bắt đầu là:

```java
Command.builder()
```

Builder cho phép thiết lập tên, mô tả, nhóm, trợ giúp, alias, option, argument và các provider. Khi gọi `execute(...)`, builder tạo ra một command cụ thể. API này trả về `AbstractCommand`, một implementation của `Command`, nên có thể trả trực tiếp từ phương thức `@Bean` khai báo kiểu `Command`.

> Với `Command.Builder`, không gọi thêm `.build()` sau `.execute(...)`. Đây là điểm khác với các builder khác trong Spring: phương thức `execute(...)` là bước hoàn tất định nghĩa command và trả về đối tượng command.

## 3. Tạo command đơn giản bằng Command.builder()

Ví dụ đầu tiên tạo command `hello` và ghi kết quả ra output của shell:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
class ShellCommandConfiguration {

    @Bean
    Command helloCommand() {
        return Command.builder()
            .name("hello")
            .description("Hiển thị lời chào")
            .group("Greeting")
            .execute(context -> {
                context.outputWriter().println("Xin chào từ Spring Shell 4!");
            });
    }
}
```

Giải thích:

- `@Configuration` khai báo lớp cấu hình Spring.
- `@Bean` đưa đối tượng trả về từ phương thức vào ApplicationContext.
- Kiểu trả về `Command` cho biết bean này là một command của Spring Shell.
- `name("hello")` đặt tên mà người dùng nhập.
- `description(...)` cung cấp mô tả trong trợ giúp.
- `group("Greeting")` phân loại command.
- `execute(...)` định nghĩa công việc thực hiện khi command được gọi.

Sau khi ứng dụng khởi động, người dùng có thể gọi:

```text
hello
```

Kết quả:

```text
Xin chào từ Spring Shell 4!
```

Command bean được Spring Shell nhận diện qua ApplicationContext. Trong ứng dụng Spring Boot, không cần tự tạo một lệnh đăng ký riêng cho từng bean `Command`.

## 4. Đăng ký Command bean và vai trò của CommandRegistry

Khi khởi động, Spring Shell lấy các command đã được định nghĩa trong ApplicationContext và đưa chúng vào `CommandRegistry`. Registry giữ tập command mà shell có thể định tuyến và thực thi.

Luồng đăng ký thông thường:

```text
Spring ApplicationContext khởi động
              |
              v
Tạo các bean có kiểu Command
              |
              v
Spring Shell lấy các Command bean
              |
              v
CommandRegistry lưu các command
              |
              v
Parser nhận tên command người dùng nhập
              |
              v
Registry tìm command phù hợp
              |
              v
Shell thực thi command
```

Có thể khai báo nhiều command bean trong cùng lớp cấu hình:

```java
@Configuration
class ShellCommandConfiguration {

    @Bean
    Command helloCommand() {
        return Command.builder()
            .name("hello")
            .description("Hiển thị lời chào")
            .execute(context -> {
                context.outputWriter().println("Xin chào!");
            });
    }

    @Bean
    Command versionCommand(AppVersion appVersion) {
        return Command.builder()
            .name("app version")
            .description("Hiển thị phiên bản ứng dụng")
            .execute(context -> {
                context.outputWriter().println(appVersion.value());
            });
    }
}
```

Spring quản lý vòng đời các bean này. Dependency của ứng dụng có thể được truyền trực tiếp vào phương thức `@Bean`, ví dụ `AppVersion` ở command thứ hai.

Trong Spring Boot, cấu hình auto-configuration của Spring Shell sẽ thiết lập registry và đưa các command bean vào đó. Nếu ứng dụng không dùng Spring Boot, cần cấu hình phần command discovery theo hướng dẫn của Spring Shell 4.x; việc có bean `Command` trong context vẫn cần một runtime và registry được khởi tạo đúng cách.

## 5. Khai báo metadata bằng Builder

Builder cung cấp các phương thức để mô tả giao diện command:

| Phương thức | Ý nghĩa |
|---|---|
| `name(String)` | Tên command chính |
| `description(String)` | Mô tả ngắn |
| `help(String)` | Hướng dẫn sử dụng chi tiết |
| `group(String)` | Nhóm trợ giúp |
| `aliases(String...)` | Các tên thay thế |
| `hidden(boolean)` | Ẩn command khỏi danh sách trợ giúp thông thường |
| `options(CommandOption...)` | Khai báo option |
| `arguments(CommandArgument...)` | Khai báo argument vị trí |
| `availabilityProvider(...)` | Kiểm tra command có thể chạy ở trạng thái hiện tại hay không |
| `completionProvider(...)` | Cung cấp gợi ý hoàn thành |
| `exitStatusExceptionMapper(...)` | Ánh xạ exception sang trạng thái thoát |

Ví dụ khai báo metadata đầy đủ hơn:

```java
@Bean
Command projectListCommand() {
    return Command.builder()
        .name("project list")
        .description("Liệt kê các project")
        .help("Hiển thị các project hiện có trong hệ thống.")
        .group("Project")
        .aliases("projects", "pl")
        .execute(context -> {
            context.outputWriter().println("Danh sách project");
        });
}
```

Người dùng có thể gọi command bằng tên chính hoặc alias:

```text
project list
projects
pl
```

Các alias trỏ đến cùng một command và cùng hành vi thực thi. Nên giữ một tên chính rõ nghĩa và chỉ thêm alias khi có nhu cầu thực tế.

## 6. Khai báo option bằng CommandOption

Command programmatic không nhận tham số Java trực tiếp như command annotation. Thay vào đó, khai báo option bằng `CommandOption`, gắn option vào builder và đọc giá trị từ `CommandContext` khi thực thi.

Ví dụ command `hello --name Linh`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandOption;

@Configuration
class GreetingCommandConfiguration {

    @Bean
    Command greetingCommand() {
        CommandOption nameOption = CommandOption.with()
            .longName("name")
            .description("Tên người cần chào")
            .required(false)
            .defaultValue("world")
            .type(String.class)
            .build();

        return Command.builder()
            .name("hello")
            .description("Chào một người")
            .options(nameOption)
            .execute(context -> {
                CommandOption option = context.getOptionByLongName("name");
                String name = option == null || option.value() == null
                    ? "world"
                    : option.value();

                context.outputWriter().println("Xin chào, " + name + "!");
            });
    }
}
```

Người dùng có thể chạy:

```text
hello
hello --name Linh
```

Kết quả tương ứng:

```text
Xin chào, world!
Xin chào, Linh!
```

Các phần chính:

1. `CommandOption.with()` tạo builder cho một option.
2. `longName("name")` định nghĩa tên dài `--name`.
3. `required(false)` cho phép bỏ qua option.
4. `defaultValue("world")` đặt giá trị mặc định.
5. `type(String.class)` xác định kiểu dữ liệu.
6. `build()` hoàn tất đối tượng `CommandOption`.
7. `options(nameOption)` gắn option vào command.
8. `getOptionByLongName("name")` lấy option trong lần thực thi hiện tại.

Lưu ý sự khác nhau giữa hai builder: `CommandOption.Builder` có phương thức `build()`, còn `Command.Builder` hoàn tất command thông qua `execute(...)`.

## 7. Đọc dữ liệu từ CommandContext

`CommandContext` đại diện cho ngữ cảnh của một lần gọi command. Các thành phần thường dùng gồm:

| Thành phần | Công dụng |
|---|---|
| `outputWriter()` | Ghi kết quả ra output của shell |
| `inputReader()` | Đọc dữ liệu nhập từ giao diện tương tác |
| `getOptionByLongName(name)` | Lấy option theo tên dài |
| `getOptionByShortName(char)` | Lấy option theo tên ngắn |
| `getOptionByName(name)` | Lấy option theo tên dài hoặc ngắn |
| `getArgumentByIndex(index)` | Lấy argument theo vị trí |
| `commandRegistry()` | Truy cập registry hiện tại |
| `parsedInput()` | Truy cập dữ liệu đã được parser phân tích |

Ví dụ ghi output:

```java
.execute(context -> {
    context.outputWriter().println("Đang xử lý...");
    context.outputWriter().flush();
})
```

Nên dùng `outputWriter()` do Spring Shell cung cấp để output đi theo luồng terminal của shell. Không nên mặc định dùng `System.out` trong command nếu muốn hỗ trợ kiểm thử hoặc thay thế phương tiện hiển thị.

Đối với option, `CommandContext` cung cấp đối tượng `CommandOption` đã gắn với lần gọi hiện tại. Giá trị nhận được có thể cần xử lý null hoặc giá trị mặc định theo cấu hình option. Với argument vị trí, dùng `getArgumentByIndex(0)`, `getArgumentByIndex(1)` và kiểm tra kết quả trước khi truy cập.

## 8. Hai cách viết hành vi execute

`Command.Builder` hỗ trợ hai dạng thực thi phổ biến:

**Consumer nhận CommandContext:** phù hợp khi muốn chủ động ghi một hoặc nhiều dòng output.

```java
return Command.builder()
    .name("status")
    .execute(context -> {
        context.outputWriter().println("Application is running");
    });
```

**Function nhận CommandContext và trả String:** phù hợp với command đơn giản có một kết quả văn bản.

```java
return Command.builder()
    .name("status")
    .execute(context -> "Application is running");
```

Ở dạng Consumer, code tự ghi output qua writer. Ở dạng Function, giá trị chuỗi trả về được command adapter xử lý để hiển thị. Chọn một cách phù hợp với hợp đồng output của command; tránh vừa ghi writer vừa trả về một chuỗi chứa cùng kết quả, vì người dùng có thể thấy nội dung lặp.

Nếu cần kiểm soát rõ `ExitStatus`, xử lý lỗi hoặc thêm logic thực thi phức tạp, có thể dùng `AbstractCommand` làm lớp cơ sở và override `doExecute(CommandContext)`.

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;

@Bean
Command healthCommand() {
    return new AbstractCommand("health", "Kiểm tra tình trạng ứng dụng") {
        @Override
        public ExitStatus doExecute(CommandContext context) {
            println("Application is healthy", context);
            return ExitStatus.OK;
        }
    };
}
```

`AbstractCommand` cung cấp tiện ích để in thông báo và xử lý help option. Đây là lựa chọn khác khi command cần kiểm soát luồng thực thi rõ hơn; với command đơn giản, builder thường ngắn gọn hơn.

## 9. Đăng ký và gỡ command động bằng CommandRegistry

Command bean thường được tạo khi ApplicationContext khởi động. Trong một số ứng dụng, danh sách command còn thay đổi theo module, plugin hoặc trạng thái runtime. Khi đó, có thể dùng `CommandRegistry` để đăng ký hoặc gỡ một command trong lúc ứng dụng đang chạy.

Ví dụ minh họa:

```java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandRegistry;
import org.springframework.stereotype.Component;

@Component
class PluginCommandManager {

    private final CommandRegistry registry;
    private Command pluginStatusCommand;

    PluginCommandManager(CommandRegistry registry) {
        this.registry = registry;
    }

    public void registerPluginCommand() {
        if (pluginStatusCommand != null) {
            return;
        }

        pluginStatusCommand = Command.builder()
            .name("plugin status")
            .description("Hiển thị trạng thái plugin")
            .execute(context -> {
                context.outputWriter().println("Plugin is active");
            });

        registry.registerCommand(pluginStatusCommand);
    }

    public void unregisterPluginCommand() {
        if (pluginStatusCommand == null) {
            return;
        }

        registry.unregisterCommand(pluginStatusCommand);
        pluginStatusCommand = null;
    }
}
```

Trong ví dụ này:

- `CommandRegistry` được inject từ Spring context.
- Command được tạo bằng cùng `Command.builder()` như khi khai báo bean.
- `registerCommand(...)` đưa command vào tập command đang hoạt động.
- `unregisterCommand(...)` loại command đó khỏi registry.
- Manager giữ tham chiếu command đã đăng ký để có thể gỡ đúng đối tượng.

Tên command là định danh duy nhất trong registry. Trước khi đăng ký command động, ứng dụng nên kiểm tra xung đột tên và quản lý vòng đời plugin rõ ràng. Không đăng ký lặp cùng command mỗi lần người dùng gọi một thao tác.

Đăng ký động chỉ nên dùng khi danh sách command thực sự cần thay đổi trong runtime. Với command cố định, khai báo `@Bean Command` giúp Spring quản lý vòng đời và dependency đơn giản hơn.

## 10. Chọn Command bean hay CommandRegistry?

Hai cơ chế phục vụ hai giai đoạn khác nhau:

| Nhu cầu | Cách dùng |
|---|---|
| Command luôn tồn tại khi ứng dụng khởi động | Khai báo `@Bean Command` |
| Command cần dependency từ Spring | Inject dependency vào phương thức `@Bean` hoặc bean quản lý command |
| Nhiều command cố định | Khai báo nhiều bean `Command` |
| Command xuất hiện khi plugin được bật | Tạo command và gọi `registerCommand` |
| Command phải biến mất khi plugin dừng | Gọi `unregisterCommand` với đúng command đã đăng ký |
| Cần xem danh sách command hiện tại | Dùng `getCommands()` hoặc truy vấn theo tên/prefix |

Trong Spring Shell 4.x, `CommandRegistry` được Spring Shell sử dụng để giữ các command đã biết. Registry tự được nạp từ command bean trong ApplicationContext. Ứng dụng chỉ cần thao tác trực tiếp với registry khi có yêu cầu thay đổi danh sách command ở runtime.

## 11. Các lỗi thường gặp

**Nhầm Command.builder() với CommandRegistration.builder().** `CommandRegistration` thuộc API programmatic của các dòng Spring Shell 3.x. Trong 4.x, mô hình command được xây bằng `Command.builder()` và `CommandOption`, `CommandArgument`.

**Gọi build() trên Command.Builder.** Builder của `Command` không kết thúc bằng `build()`. Gọi `execute(...)` sẽ tạo đối tượng `AbstractCommand` triển khai `Command`. Riêng `CommandOption.Builder` và `CommandArgument.Builder` có `build()`.

**Khai báo bean sai kiểu.** Một phương thức `@Bean` nên trả về `Command` hoặc implementation của nó. Trả về một builder chưa hoàn tất sẽ không tạo bean command mà registry có thể thực thi.

**Quên tên command.** Hãy đặt `name` tường minh để command dễ nhận biết và tránh phụ thuộc vào tên biến hoặc tên phương thức cấu hình.

**Đọc option mà không kiểm tra null.** Option có thể không được truyền nếu không bắt buộc. Xử lý giá trị mặc định và null trước khi dùng.

**Dùng System.out thay cho outputWriter.** Dùng writer trong `CommandContext` giúp command làm việc với output của shell và thuận tiện hơn khi kiểm thử.

**Đăng ký command trùng tên.** Registry định danh command bằng tên. Cần đảm bảo tên duy nhất và gỡ command cũ trước khi thay thế.

**Tạo command động nhưng không quản lý vòng đời.** Nếu plugin dừng mà command vẫn còn trong registry, người dùng có thể gọi một command không còn hoạt động. Hãy gỡ command khi module hoặc plugin kết thúc.

**Đưa nghiệp vụ vào lambda quá dài.** Builder chỉ định nghĩa giao diện và adapter CLI. Nên gọi application service từ lambda để logic nghiệp vụ có thể tái sử dụng và kiểm thử độc lập.

## 12. Checklist khi tạo Command bean

- [ ] Dùng API `org.springframework.shell.core.command.Command` của Spring Shell 4.x.
- [ ] Tạo command bằng `Command.builder()`.
- [ ] Đặt `name` rõ ràng và duy nhất.
- [ ] Cung cấp `description`, `help`, `group` và alias khi cần.
- [ ] Khai báo option và argument với kiểu dữ liệu, tính bắt buộc và giá trị mặc định phù hợp.
- [ ] Đọc dữ liệu runtime qua `CommandContext`.
- [ ] Ghi kết quả qua `outputWriter()` hoặc trả về chuỗi theo đúng một cách.
- [ ] Trả trạng thái phù hợp nếu dùng `AbstractCommand`.
- [ ] Đưa command cố định vào ApplicationContext dưới dạng bean `Command`.
- [ ] Chỉ dùng `CommandRegistry` trực tiếp khi cần đăng ký hoặc gỡ command lúc runtime.
- [ ] Kiểm tra tên command và alias không xung đột.
- [ ] Tách nghiệp vụ khỏi lambda thực thi để có thể tái sử dụng.

## 13. Tài liệu tham khảo chính thức

- [Spring Shell 4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html): hai mô hình annotation và programmatic, cách khai báo `Command` bean và vai trò của registry.
- [Spring Shell 4 — Command API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html): interface `Command`, `Command.builder()` và phương thức thực thi.
- [Spring Shell 4 — Command.Builder API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.Builder.html): các thuộc tính metadata và hai overload `execute(...)`.
- [Spring Shell 4 — AbstractCommand API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/AbstractCommand.html): lớp cơ sở và phương thức `doExecute(...)`.
- [Spring Shell 4 — CommandOption API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.html): khai báo option bằng builder.
- [Spring Shell 4 — CommandContext API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html): dữ liệu của lần gọi command.
- [Spring Shell 4 — CommandRegistry API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandRegistry.html): tra cứu, đăng ký và gỡ command.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): thay đổi API programmatic từ 3.x sang 4.x.

Với Spring Shell 4.x, `Command.builder()` tạo command theo hướng lập trình; khai báo đối tượng đó thành bean kiểu `Command` để Spring Shell tự đưa vào registry. Chỉ cần thao tác trực tiếp với `CommandRegistry` khi ứng dụng cần thay đổi command trong lúc chạy. Cách tổ chức này giữ rõ ranh giới giữa định nghĩa giao diện CLI, vòng đời bean và logic nghiệp vụ của ứng dụng.

