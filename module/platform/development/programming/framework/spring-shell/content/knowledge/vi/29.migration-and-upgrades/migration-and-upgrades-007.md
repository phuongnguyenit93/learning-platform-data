# Chuyển CommandRegistration và CommandCatalog sang Command và CommandRegistry

Trong Spring Shell 3.x, mô hình đăng ký command bằng code xoay quanh hai đối tượng: **CommandRegistration** mô tả tên lệnh, option, target và các thuộc tính liên quan; **CommandCatalog** lưu các registration để shell tìm và thực thi. Mô hình này tách định nghĩa command khỏi đối tượng thực thi, nhưng nhiều lớp trung gian như target spec, resolver, customizer và exception resolver khiến việc theo dõi một command khá phức tạp.

Spring Shell 4 thay mô hình đó bằng **Command** và **CommandRegistry**. Một Command chứa metadata cùng hành vi thực thi; registry giữ các Command mà shell biết đến và cho phép đăng ký hoặc gỡ bỏ command trong lúc ứng dụng chạy.

Việc nâng cấp vì vậy không chỉ là đổi tên hai class. Cần chuyển phần định nghĩa, option, argument và logic target sang Command; chuyển thao tác thêm/gỡ command sang CommandRegistry; đồng thời thiết kế lại những CommandResolver hoặc CommandCatalogCustomizer cũ nếu ứng dụng đang dùng chúng.

## 1. Hai mô hình và trách nhiệm của từng đối tượng

Ở Spring Shell 3.x, một command thường được tạo thành **CommandRegistration** rồi đưa vào **CommandCatalog**. Registration lưu thông tin mô tả command và cách gọi target. Catalog quản lý các registration, hỗ trợ đăng ký/gỡ đăng ký, có thể kết hợp resolver để tìm command động và customizer để thay đổi catalog lúc khởi tạo.

Ở Spring Shell 4, **Command** là hợp đồng thực thi command. Nó cung cấp metadata như tên, mô tả, nhóm, help, alias, option, argument, completion và availability; đồng thời có phương thức **execute(CommandContext)** trả về **ExitStatus**. **CommandRegistry** lưu các Command đã đăng ký.

| Spring Shell 3.x | Spring Shell 4 | Vai trò sau migration |
|---|---|---|
| **CommandRegistration** | **Command** | Định nghĩa command, metadata và hành vi thực thi |
| **CommandRegistration.Builder** | **Command.Builder** | Xây dựng command bằng builder |
| **CommandRegistration.TargetSpec** | **Command.Builder.execute(...)** hoặc **AbstractCommand** | Khai báo hành vi chạy command |
| **CommandRegistration.OptionSpec** | **CommandOption** | Khai báo option |
| Target method/consumer/function | Lambda hoặc lớp implement Command | Xử lý input và nghiệp vụ |
| **CommandCatalog** | **CommandRegistry** | Lưu và quản lý các command đã biết |
| **CommandCatalog.register(...)** | **CommandRegistry.registerCommand(...)** | Đăng ký command |
| **CommandCatalog.unregister(...)** | **CommandRegistry.unregisterCommand(...)** | Gỡ command |
| **CommandCatalog.getRegistrations()** | **CommandRegistry.getCommands()** | Đọc danh sách command |
| **CommandResolver** | Không có thay thế 1:1 | Đăng ký/gỡ command theo sự kiện hoặc dùng availability provider |
| **CommandCatalogCustomizer** | Command bean hoặc logic khởi tạo dùng registry | Đăng ký command lúc khởi động hoặc tùy biến sau khi context sẵn sàng |

Điểm khác biệt quan trọng: **CommandRegistry là class trong Spring Shell 4**, không phải interface tương ứng trực tiếp với CommandCatalog. Nó quản lý đối tượng Command đã hoàn chỉnh, thay vì quản lý các registration descriptor.

## 2. Chuẩn bị trước khi nâng cấp

Spring Shell 4 dựa trên Spring Framework 7 và yêu cầu Spring Boot 4 khi tích hợp với Boot. Trước khi thay API command, nâng ứng dụng lên phiên bản Spring Shell 3.4.x mới nhất để xử lý các thay đổi nhỏ trong nhánh 3.x trước.

Kiểm tra dependency và import cũ:

~~~java
import org.springframework.shell.command.CommandRegistration;
import org.springframework.shell.command.CommandCatalog;
~~~

Trong Spring Shell 4, API command mới nằm dưới package:

~~~java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandRegistry;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.CommandArgument;
import org.springframework.shell.core.command.ExitStatus;
~~~

Đừng giữ đồng thời dependency Spring Shell 3 và 4 trong cùng runtime để trì hoãn migration. Hai thế hệ có mô hình command và package khác nhau; hãy nâng dependency đồng bộ rồi sửa code theo compiler error và test.

## 3. Từ CommandRegistration sang Command

Ví dụ Spring Shell 3.x đăng ký một command bằng target function:

~~~java
CommandRegistration registration = CommandRegistration.builder()
        .command("report show")
        .description("Hiển thị báo cáo.")
        .group("reports")
        .withTarget()
            .function(context -> reportService.render("table"))
            .and()
        .build();

commandCatalog.register(registration);
~~~

Registration mô tả tên, description, group và target. Function nhận **CommandContext** rồi trả nội dung sẽ hiển thị trong shell.

Trong Spring Shell 4, hành vi được đưa vào Command:

~~~java
import org.springframework.shell.core.command.Command;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BasicReportCommandConfiguration {

    @Bean
    Command reportShowCommand(ReportService reportService) {
        return Command.builder()
                .name("report show")
                .description("Hiển thị báo cáo.")
                .group("reports")
                .execute(context -> reportService.render("table"));
    }
}
~~~

Ví dụ này dùng **Command.Builder.execute(Function<CommandContext, String>)**. Chuỗi trả về được Spring Shell in ra output. Phương thức **execute(...)** trả về một **AbstractCommand**, là một implementation của Command; builder không có bước **build()** ở cuối.

Nếu command cần ghi nhiều dòng, có thể dùng Consumer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
public class ReportListCommandConfiguration {

    @Bean
    Command reportListCommand(ReportService reportService) {
        return Command.builder()
                .name("report list")
                .description("Liệt kê báo cáo.")
                .execute(context -> {
                    context.outputWriter().println("Các báo cáo hiện có:");
                    reportService.findAll().forEach(
                            report -> context.outputWriter().println(report.name())
                    );
                    context.outputWriter().flush();
                });
    }
}
~~~

Consumer không trả về nội dung. Command tự ghi qua **CommandContext.outputWriter()**.

## 4. Đưa option và argument vào Command

Trong 3.x, option được khai báo qua **CommandRegistration.OptionSpec**. Trong 4.x, mỗi option là một **CommandOption**; argument vị trí là **CommandArgument**.

Ví dụ tạo option bằng builder:

~~~java
CommandOption formatOption = CommandOption.with()
        .shortName('f')
        .longName("format")
        .description("Định dạng đầu ra.")
        .defaultValue("table")
        .required(false)
        .type(String.class)
        .build();
~~~

Tạo argument vị trí:

~~~java
CommandArgument reportIdArgument = CommandArgument.with()
        .index(0)
        .description("Mã báo cáo.")
        .type(String.class)
        .build();
~~~

Sau đó gắn chúng vào Command.Builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandArgument;
import org.springframework.shell.core.command.CommandOption;

@Configuration
public class DetailedReportCommandConfiguration {

    @Bean
    Command reportShowCommand(ReportService reportService) {
        CommandOption formatOption = CommandOption.with()
                .shortName('f')
                .longName("format")
                .description("Định dạng đầu ra.")
                .defaultValue("table")
                .required(false)
                .type(String.class)
                .build();

        CommandArgument reportIdArgument = CommandArgument.with()
                .index(0)
                .description("Mã báo cáo.")
                .type(String.class)
                .build();

        return Command.builder()
                .name("report show")
                .description("Hiển thị một báo cáo.")
                .group("reports")
                .aliases("rshow")
                .options(formatOption)
                .arguments(reportIdArgument)
                .execute(context -> {
                    CommandOption selectedFormat =
                            context.getOptionByLongName("format");
                    String format = selectedFormat == null
                            || selectedFormat.value() == null
                            ? "table"
                            : selectedFormat.value();

                    CommandArgument selectedId = context.getArgumentByIndex(0);
                    String reportId = selectedId == null
                            ? null
                            : selectedId.value();

                    if (reportId == null || reportId.isBlank()) {
                        return "Cần cung cấp mã báo cáo.";
                    }

                    return reportService.render(reportId, format);
                });
    }
}
~~~

**CommandContext** cung cấp các phương thức:

| API | Công dụng |
|---|---|
| **getOptionByLongName(name)** | Lấy option theo tên dài |
| **getOptionByShortName(char)** | Lấy option theo tên ngắn |
| **getOptionByName(name)** | Lấy option theo tên dài hoặc ngắn |
| **getArgumentByIndex(index)** | Lấy argument theo vị trí |
| **outputWriter()** | Ghi nội dung ra shell |
| **parsedInput()** | Đọc cấu trúc input đã được parser xử lý |
| **commandRegistry()** | Truy cập registry hiện tại |

**CommandOption** và **CommandArgument** lưu cả định nghĩa lẫn giá trị của lần gọi hiện tại. Dùng **value()** để đọc giá trị đã parse, không tự tách chuỗi command line trong command.

**CommandArgument.Builder** không có thuộc tính **required** như option. Hãy xác định index, type, defaultValue hoặc variadic phù hợp, rồi kiểm tra trường hợp thiếu dữ liệu trước khi gọi nghiệp vụ có side effect.

## 5. Lưu ý về option name và arity

Spring Shell 4 giới hạn mỗi option ở một tên ngắn và một tên dài. Trong 3.x, builder có thể nhận nhiều tên qua các phương thức dạng **longNames(...)** và **shortNames(...)**. Khi nâng cấp, chọn một tên ngắn và một tên dài làm tên chuẩn.

| Cấu hình 3.x | Cấu hình 4.x |
|---|---|
| **longNames("format", "output-format")** | **longName("format")** |
| **shortNames('f', 'o')** | **shortName('f')** |
| Nhiều tên cho cùng một option | Một cặp short/long name |

Nếu script cũ dùng nhiều tên option, cần quyết định cách tương thích: cập nhật script, thêm một option riêng và chuẩn hóa về cùng một giá trị nghiệp vụ, hoặc cung cấp wrapper chuyển cú pháp cũ sang cú pháp mới. Không giả định CommandOption 4.x hỗ trợ danh sách tên như OptionSpec cũ.

Spring Shell 4 cũng bổ sung **CommandArgument** và **@Arguments** để mô tả argument nhiều giá trị. Với command programmatic, cấu hình argument bằng index, type và cờ variadic nếu cần. Kiểm tra lại các command cũ đang dùng option arity để biểu diễn danh sách; có thể chuyển sang positional arguments nếu cú pháp người dùng phù hợp.

## 6. Chuyển target method, function và consumer

Trong 3.x, **CommandRegistration.TargetSpec** có ba cách định nghĩa target:

- **method(bean, methodName):** gọi một method trên object.
- **function(...):** nhận CommandContext và trả về kết quả.
- **consumer(...):** nhận CommandContext nhưng không trả kết quả.

Trong 4.x, builder cung cấp **execute(Function<CommandContext, String>)** và **execute(Consumer<CommandContext>)**. Với xử lý cần trả về một **ExitStatus** cụ thể, dùng **AbstractCommand** hoặc tự implement Command.

Ví dụ dùng AbstractCommand:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;

@Configuration
public class ReportExportCommandConfiguration {

    @Bean
    Command reportExportCommand(ReportService reportService) {
        return new AbstractCommand(
                "report export",
                "Xuất báo cáo.",
                "reports"
        ) {
            @Override
            public ExitStatus doExecute(CommandContext context) {
                try {
                    reportService.exportAll();
                    println("Đã xuất báo cáo.", context);
                    return ExitStatus.OK;
                }
                catch (ReportExportException ex) {
                    println("Không thể xuất báo cáo.", context);
                    return new ExitStatus(5, "Report export failed");
                }
            }
        };
    }
}
~~~

**AbstractCommand** hỗ trợ in nội dung qua **println(...)**, xử lý help option và cho phép trả ExitStatus từ **doExecute(...)**. Nếu cần metadata phức tạp như options, arguments, aliases hoặc completion provider, cấu hình thêm qua Command.Builder hoặc implement Command phù hợp.

## 7. Chuyển metadata và hành vi sang builder mới

Các thuộc tính phổ biến của CommandRegistration có thể chuyển như sau:

| CommandRegistration 3.x | Command.Builder 4.x | Ghi chú |
|---|---|---|
| **command("report show")** | **name("report show")** | Tên command đầy đủ |
| **description("...")** | **description("...")** | Mô tả ngắn |
| **group("reports")** | **group("reports")** | Nhóm hiển thị |
| **hidden()** | **hidden(true)** | Ẩn command khỏi danh sách thông thường |
| **withAlias().command("rshow")** | **aliases("rshow")** | Alias của command |
| **withOption()...** | **options(CommandOption...)** | Khai báo option riêng |
| TargetSpec.function(...) | **execute(Function...)** | Trả chuỗi kết quả |
| TargetSpec.consumer(...) | **execute(Consumer...)** | Ghi output qua context |
| Availability supplier | **availabilityProvider(...)** | Cung cấp trạng thái khả dụng |
| Exception resolver | **exitStatusExceptionMapper(...)** | Ánh xạ exception thành ExitStatus |
| Completion provider | **completionProvider(...)** | Hoàn thành tập trung ở command |

Không phải mọi thuộc tính cũ đều có phép chuyển 1:1. Đặc biệt, **interactionMode** của command đã bị loại bỏ trong Spring Shell 4: chế độ interactive/non-interactive được chọn ở cấp shell, không phải từng command.

## 8. Chuyển CommandExitCode và CommandExceptionResolver

Trong 3.x, mã thoát và xử lý exception được chia qua **CommandExitCode**, **CommandHandlingResult** và **CommandExceptionResolver**. Trong 4.x, **ExitStatus** là record chứa code và description; **ExitStatusExceptionMapper** ánh xạ exception thành ExitStatus.

Ví dụ mapper mới:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
public class CommandErrorConfiguration {

    @Bean
    ExitStatusExceptionMapper reportExceptionMapper() {
        return exception -> {
            if (exception instanceof ReportNotFoundException) {
                return new ExitStatus(4, "Report not found");
            }
            return ExitStatus.EXECUTION_ERROR;
        };
    }
}
~~~

Gắn mapper vào command bằng builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
public class MappedReportCommandConfiguration {

    @Bean
    Command reportShowCommand(
            ReportService reportService,
            ExitStatusExceptionMapper reportExceptionMapper) {
        return Command.builder()
                .name("report show")
                .exitStatusExceptionMapper(reportExceptionMapper)
                .execute(context -> reportService.render("table"));
    }
}
~~~

Hoặc gắn mapper bằng thuộc tính **exitStatusExceptionMapper** trên annotation **@Command** nếu dùng mô hình annotation. Không giữ **CommandExceptionResolver** hoặc **CommandHandlingResult** trong code 4.x.

## 9. Chuyển CommandCatalog sang CommandRegistry

Trong 3.x, **CommandCatalog** lưu các **CommandRegistration**. Các thao tác phổ biến:

~~~java
commandCatalog.register(registration);
commandCatalog.unregister("report show");
Map<String, CommandRegistration> registrations =
        commandCatalog.getRegistrations();
~~~

Trong 4.x, **CommandRegistry** quản lý đối tượng **Command**:

~~~java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandRegistry;
import org.springframework.stereotype.Component;

@Component
public class ReportCommandManager {

    private final CommandRegistry commandRegistry;

    public ReportCommandManager(CommandRegistry commandRegistry) {
        this.commandRegistry = commandRegistry;
    }

    public void register(Command command) {
        commandRegistry.registerCommand(command);
    }

    public void unregister(Command command) {
        commandRegistry.unregisterCommand(command);
    }
}
~~~

Các phương thức quan trọng:

| CommandRegistry API | Công dụng |
|---|---|
| **registerCommand(command)** | Đăng ký một Command |
| **unregisterCommand(command)** | Gỡ Command |
| **getCommands()** | Lấy tập Command hiện có |
| **getCommandByName(name)** | Tìm theo tên command |
| **getCommandByAlias(name)** | Tìm theo alias |
| **getCommandsByPrefix(prefix)** | Tìm các command theo tiền tố |
| **clearCommands()** | Xóa toàn bộ command trong registry |

Command được định danh duy nhất bằng tên. Trước khi đăng ký command động, kiểm tra tên có đang được dùng hay không để tránh xung đột. Chỉ gọi **clearCommands()** nếu thật sự muốn xóa toàn bộ command, bao gồm command được đăng ký từ application context.

Không sửa tập trả về từ **getCommands()** để thêm hoặc xóa command. Dùng **registerCommand()** và **unregisterCommand()** để registry cập nhật đúng.

## 10. Đăng ký Command bean khi ứng dụng khởi động

Spring Shell 4 tự động đưa các bean kiểu **Command** trong application context vào registry. Vì vậy, command cố định có thể được khai báo thành bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
public class ReportCommands {

    @Bean
    Command reportListCommand(ReportService reportService) {
        return Command.builder()
                .name("report list")
                .description("Liệt kê các báo cáo.")
                .execute(context -> reportService.listAsText());
    }
}
~~~

Trong trường hợp này, không cần tự gọi **commandRegistry.registerCommand(...)** lần nữa. Nếu vừa khai báo Command bean vừa tự đăng ký cùng object, ứng dụng có thể gặp đăng ký trùng hoặc logic khởi tạo khó theo dõi.

Mô hình annotation cũng được hỗ trợ: method **@Command** nằm trong bean Spring. Khi dùng Spring Boot, command scanning được tự động cấu hình. Với ứng dụng không dùng Boot, dùng **@EnableCommand** để chỉ định các class chứa command annotation.

## 11. Đăng ký và gỡ command động trong lúc chạy

Nếu command chỉ xuất hiện khi một plugin được bật, người dùng đăng nhập hoặc một tính năng được cấp quyền, tạo Command rồi đăng ký vào registry khi trạng thái thay đổi.

~~~java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandRegistry;
import org.springframework.stereotype.Component;

@Component
public class PluginCommandManager {

    private final CommandRegistry registry;
    private Command pluginCommand;

    public PluginCommandManager(CommandRegistry registry) {
        this.registry = registry;
    }

    public void enablePlugin() {
        if (registry.getCommandByName("plugin inspect") != null) {
            return;
        }

        pluginCommand = Command.builder()
                .name("plugin inspect")
                .description("Kiểm tra trạng thái plugin.")
                .execute(context -> "Plugin đang hoạt động.");

        registry.registerCommand(pluginCommand);
    }

    public void disablePlugin() {
        if (pluginCommand != null) {
            registry.unregisterCommand(pluginCommand);
            pluginCommand = null;
        }
    }
}
~~~

Đây là trường hợp thay thế phù hợp cho nhiều cách dùng **CommandCatalog.register/unregister**. Giữ tham chiếu tới đúng Command đã đăng ký để gỡ bỏ chính xác khi plugin bị tắt.

Nếu command luôn tồn tại nhưng chỉ có thể chạy khi người dùng đăng nhập, không nhất thiết phải thêm/gỡ command. Có thể dùng **AvailabilityProvider** để trả về trạng thái khả dụng. Cách này giữ command trong help và completion nhưng cho biết vì sao command chưa thể chạy.

## 12. Chuyển CommandResolver và CommandCatalogCustomizer

**CommandResolver** của 3.x cung cấp danh sách CommandRegistration mỗi khi shell cần resolve command. Tài liệu 3.x cảnh báo resolver được gọi ở mỗi lần resolve; nếu xử lý lâu, shell sẽ phản hồi chậm.

Trong 4.x không có một interface resolver thay thế trực tiếp. Chọn chiến lược theo nhu cầu:

| Nhu cầu cũ | Chiến lược trong 4.x |
|---|---|
| Command cố định được biết lúc startup | Khai báo **Command** bean |
| Command phụ thuộc plugin đã bật | Đăng ký/gỡ command qua **CommandRegistry** khi trạng thái plugin thay đổi |
| Command luôn tồn tại nhưng tạm thời không khả dụng | Dùng **AvailabilityProvider** |
| Thay đổi danh sách command lúc khởi tạo | Tạo các Command bean theo cấu hình hoặc đăng ký trong lifecycle bean |
| Tùy biến catalog ở startup | Đưa logic vào bean cấu hình tạo Command hoặc thành phần khởi tạo dùng registry |

**CommandCatalogCustomizer** cũng không có phép chuyển 1:1. Nếu customizer cũ chỉ thêm vài registration cố định, thay nó bằng các bean **Command**. Nếu cần đăng ký sau khi ứng dụng đã khởi tạo, inject **CommandRegistry** và gọi phương thức đăng ký tại thời điểm thích hợp.

Nếu ứng dụng dùng **CommandRegistration.BuilderSupplier** hoặc **CommandRegistrationCustomizer** để áp dụng metadata chung, chuyển phần mặc định đó thành một factory/helper do ứng dụng sở hữu. Factory có thể tạo một **Command.Builder** mới, đặt group, description hoặc mapper chung, rồi trả builder để từng bean hoàn tất bằng **execute(...)**. Tạo builder mới cho mỗi command để tránh chia sẻ trạng thái giữa các lần cấu hình.

Không thực hiện truy vấn database hoặc gọi dịch vụ mạng mỗi lần shell resolve danh sách command. Hãy nạp trạng thái một lần hoặc phản ứng theo sự kiện, rồi cập nhật registry khi trạng thái thay đổi.

## 13. Không nhầm CommandRegistry với CommandCatalog

Hai đối tượng cùng giữ tập command nhưng có khác biệt về cấu trúc:

| Khía cạnh | CommandCatalog 3.x | CommandRegistry 4.x |
|---|---|---|
| Đối tượng lưu | CommandRegistration | Command |
| Định nghĩa target | Tách trong TargetSpec | Nằm trong Command.execute |
| Đăng ký động | register/unregister registration | registerCommand/unregisterCommand |
| Đọc danh sách | getRegistrations() | getCommands() |
| Định danh | Tên trong registration | Tên Command duy nhất |
| Resolver | CommandResolver | Không có resolver tương đương trực tiếp |
| Customizer | CommandCatalogCustomizer | Command bean hoặc code dùng registry |
| Tìm kiếm | Catalog/resolver | getCommandByName, getCommandByAlias, getCommandsByPrefix |

Trong 3.x, **getRegistrations()** trả về một bản sao của map; thay đổi map đó không đăng ký command vào catalog. Trong 4.x, cũng dùng API registry để thay đổi trạng thái thay vì cố chỉnh collection trả về.

## 14. Lộ trình migration theo từng bước

1. **Liệt kê nơi dùng API cũ:** tìm CommandRegistration, CommandCatalog, CommandResolver, CommandCatalogCustomizer và BuilderSupplier.
2. **Phân loại command:** command cố định, command theo plugin, command theo trạng thái người dùng hoặc command được tạo theo cấu hình.
3. **Tách target khỏi registration:** xác định logic đang nằm trong method, function hoặc consumer.
4. **Tạo Command:** chuyển tên, description, group, help, hidden, alias và hành vi thực thi.
5. **Chuyển input:** chuyển OptionSpec sang CommandOption; bổ sung CommandArgument cho positional argument.
6. **Chuyển lỗi:** thay CommandExceptionResolver bằng ExitStatusExceptionMapper và ExitStatus.
7. **Chuyển registry:** thay thao tác catalog bằng CommandRegistry.
8. **Thay resolver/customizer:** dùng Command bean cho startup và registry event cho command động.
9. **Kiểm tra xung đột tên:** xác nhận không có hai Command cùng tên và alias không bị trùng.
10. **Chạy kiểm thử:** xác nhận help, option, argument, availability, completion, exit status và register/unregister.
11. **Xóa import/dependency cũ:** chỉ sau khi không còn code nào dùng API 3.x.

Có thể dùng tìm kiếm trong IDE hoặc lệnh ripgrep:

~~~bash
rg "CommandRegistration|CommandCatalog|CommandResolver|CommandCatalogCustomizer|CommandExceptionResolver" src
~~~

Sau migration, không còn kết quả sử dụng API cũ trong source code của module đã nâng cấp.

## 15. Kiểm thử sau migration

Kiểm thử nên bao phủ cả định nghĩa command và vòng đời registry:

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Command bean được tạo | Command xuất hiện trong registry |
| Command.Builder có tên và mô tả | Help hiển thị đúng metadata |
| Alias được khai báo | Có thể gọi command bằng alias |
| Option có default value | Giá trị mặc định được áp dụng |
| Argument theo index | Đúng giá trị được đọc từ CommandContext |
| Thiếu argument | Parser từ chối hoặc command xử lý lỗi rõ ràng |
| AvailabilityProvider trả unavailable | Command không thực thi và lý do được hiển thị |
| Exception mapper | Exception được chuyển thành ExitStatus đúng |
| registerCommand | Command xuất hiện trong registry |
| unregisterCommand | Command không còn được tìm thấy |
| Đăng ký tên trùng | Ứng dụng xử lý xung đột theo chính sách đã chọn |
| CommandCatalogCustomizer cũ | Logic tương đương đã chuyển sang Command bean hoặc registry |
| CommandResolver cũ | Không còn resolver thực hiện công việc tốn thời gian mỗi lần resolve |

Ví dụ kiểm tra registry:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandRegistry;

class CommandRegistryMigrationTests {

    @Test
    void registersAndUnregistersCommand() {
        CommandRegistry registry = new CommandRegistry();
        Command command = Command.builder()
                .name("report ping")
                .description("Kiểm tra command.")
                .execute(context -> "pong");

        registry.registerCommand(command);
        assertThat(registry.getCommandByName("report ping"))
                .isSameAs(command);

        registry.unregisterCommand(command);
        assertThat(registry.getCommandByName("report ping")).isNull();
    }
}
~~~

Test trên kiểm tra hành vi registry thuần. Cần thêm integration test với Spring context để xác nhận các Command bean được tự động nạp và command annotation được đăng ký đúng trong ứng dụng thực tế.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không biên dịch sau khi nâng cấp | Import vẫn trỏ tới org.springframework.shell.command | Chuyển sang org.springframework.shell.core.command |
| Command bean không xuất hiện | Bean không nằm trong application context hoặc bị exclude component scan | Kiểm tra @Bean/@Component và component scanning |
| Gọi build() bị lỗi | Nhầm Command.Builder với builder của CommandRegistration | Gọi execute(...) để nhận AbstractCommand |
| Command chạy nhưng không in output | Dùng Consumer nhưng không ghi vào outputWriter | Ghi qua CommandContext.outputWriter() hoặc dùng Function trả String |
| Không lấy được option | Dùng API getOptionValue cũ | Dùng getOptionByLongName/getOptionByName rồi đọc value() |
| Không lấy được argument | Chưa khai báo CommandArgument hoặc dùng sai index | Khai báo arguments(...) và dùng getArgumentByIndex |
| Alias không hoạt động | Chưa chuyển alias từ AliasSpec | Dùng aliases(...) trên builder |
| Option cũ không còn tên phụ | 4.x chỉ hỗ trợ một shortName và một longName | Chọn tên chuẩn hoặc xử lý tương thích riêng |
| Exception trả sai mã | Vẫn dùng CommandExceptionResolver | Dùng ExitStatusExceptionMapper |
| Command đăng ký hai lần | Command vừa là bean vừa tự register thủ công | Chọn một cơ chế cho command cố định |
| Command động không gỡ được | Không giữ tham chiếu Command đã đăng ký | Lưu instance và truyền lại cho unregisterCommand |
| Resolver làm shell chậm | Thực hiện I/O trong mỗi lần resolve | Chuyển sang đăng ký theo sự kiện hoặc availability provider |
| Command không còn phân biệt interactive | Cố giữ InteractionMode cũ | Chọn interactive/non-interactive ở cấp shell |
| Gọi clearCommands làm mất help/version | Xóa toàn bộ registry | Chỉ unregister command do tính năng sở hữu |

## 17. Checklist hoàn tất migration

- [ ] Đã nâng dependency lên Spring Shell 4 tương thích Spring Boot 4/Spring Framework 7.
- [ ] Đã thay CommandRegistration bằng Command.
- [ ] Đã thay CommandRegistration.Builder bằng Command.Builder.
- [ ] Đã chuyển target function/consumer sang execute(...).
- [ ] Đã chuyển OptionSpec sang CommandOption.
- [ ] Đã chuyển positional input sang CommandArgument khi cần.
- [ ] Đã kiểm tra giới hạn một short name và một long name cho mỗi option.
- [ ] Đã thay CommandCatalog bằng CommandRegistry.
- [ ] Command cố định được đăng ký như bean Command.
- [ ] Command động dùng registerCommand/unregisterCommand.
- [ ] Đã thay CommandResolver và CommandCatalogCustomizer theo đúng nhu cầu.
- [ ] Đã thay CommandExceptionResolver bằng ExitStatusExceptionMapper.
- [ ] Đã bỏ InteractionMode ở cấp command.
- [ ] Không còn import hoặc dependency API cũ.
- [ ] Đã test metadata, option, argument, alias, availability và completion.
- [ ] Đã test register/unregister và command name conflict.
- [ ] Đã chạy integration test trên Spring context thực tế.

Migration từ CommandRegistration/CommandCatalog sang Command/CommandRegistry làm cho định nghĩa và thực thi command nằm trong cùng một mô hình. Command bean phù hợp với lệnh cố định; CommandRegistry phù hợp với lệnh cần thêm hoặc gỡ trong lúc chạy. Khi chuyển đúng hai trường hợp này, code ít lớp trung gian hơn và hành vi đăng ký dễ kiểm tra hơn.

## Tài liệu tham khảo

- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — thay đổi command model, Command, CommandRegistry, exception mapping và các breaking changes từ 3.x lên 4.x.
- [Spring Shell 4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) — annotation-based và programmatic command registration, Command bean và CommandRegistry.
- [Spring Shell 4 API — Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html) — hợp đồng execute và metadata của Command.
- [Spring Shell 4 API — Command.Builder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.Builder.html) — xây dựng command, cấu hình options, arguments, aliases và execute.
- [Spring Shell 4 API — CommandRegistry](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandRegistry.html) — registerCommand, unregisterCommand, tìm kiếm và liệt kê command.
- [Spring Shell 4 API — CommandContext](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html) — truy cập option, argument, parsed input và output writer.
- [Spring Shell 4 API — CommandOption](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.html) — cấu trúc option và giá trị được parse.
- [Spring Shell 4 API — CommandArgument](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandArgument.html) — argument vị trí, kiểu và variadic.
- [Spring Shell 4 API — AbstractCommand](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/AbstractCommand.html) — lớp cơ sở để trả ExitStatus và xử lý help/output.
- [Spring Shell 3.4 — Command Catalog](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/appendices/techintro/commandcatalog.html) — vai trò của CommandCatalog, CommandResolver và CommandCatalogCustomizer trong 3.x.
- [Spring Shell 3.4 — Command Registration](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/registration.html) — registration, target, function và consumer trong 3.x.
- [Spring Shell 3.4 API — CommandRegistration.Builder](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.Builder.html) — builder và các spec của registration cũ.
