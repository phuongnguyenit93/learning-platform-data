# CommandRegistry và đăng ký lệnh động trong 4.x

Spring Shell 4 cho phép xây dựng command bằng mã Java rồi đưa command vào shell thông qua **CommandRegistry**. Cách này phù hợp khi tập lệnh thay đổi theo module được bật, tính năng được cấp phép, kết nối hiện tại hoặc cấu hình triển khai. Ứng dụng có thể thêm command khi một tính năng sẵn sàng và gỡ command khi tính năng không còn được cung cấp.

Trong Spring Shell 4.0.4, **CommandRegistry** là một lớp giữ tập command mà shell biết đến. Registry được tự động điền từ các bean kiểu **Command** trong Spring ApplicationContext và cũng hỗ trợ đăng ký hoặc hủy đăng ký command trong lúc ứng dụng đang chạy. Tên command là định danh duy nhất trong registry.

Bài này tập trung vào mô hình đăng ký bằng mã của Spring Shell 4.x. Các ví dụ dùng package **org.springframework.shell.core.command**. Không dùng lại **CommandRegistration** hoặc **CommandCatalog** của dòng 3.x trong mã 4.x.

| Spring Shell 3.x | Spring Shell 4.x |
|---|---|
| **CommandRegistration** mô tả một command | **Command** là hợp đồng thực thi |
| **CommandCatalog** lưu các registration | **CommandRegistry** lưu các command |
| **CommandCatalog.register()** và **unregister()** | **CommandRegistry.registerCommand()** và **unregisterCommand()** |
| API registration và target resolver | **Command.Builder** hoặc **AbstractCommand** |

## 1. Khi nào cần đăng ký command bằng mã?

Spring Shell có hai cách định nghĩa command:

| Cách định nghĩa | Cách hoạt động | Khi nên dùng |
|---|---|---|
| Annotation model | Đặt **@Command** trên method của một Spring bean | Tập lệnh ổn định, được biết trước khi ứng dụng khởi động |
| Programmatic model | Tạo đối tượng **Command** bằng builder hoặc lớp **AbstractCommand** | Command được tạo theo cấu hình, module hoặc trạng thái runtime |

Ví dụ, một CLI quản lý hệ thống có các command cơ bản như **help**, **version** và **status**. Khi người dùng kích hoạt module báo cáo, ứng dụng mới đăng ký thêm **report-preview**. Khi module bị tắt, command đó được gỡ khỏi shell. Nếu danh sách command cố định, annotation hoặc bean **Command** là đủ. Nếu danh sách cần thay đổi trong lúc chạy, quản lý registry trực tiếp sẽ phù hợp hơn.

Một điểm cần phân biệt:

- **Đăng ký command** quyết định shell có biết và nhận diện lệnh đó hay không.
- **Availability** quyết định command đã đăng ký có thể được thực thi trong trạng thái hiện tại hay không.

Nếu command nên xuất hiện trong help nhưng chỉ chạy được sau khi người dùng kết nối, giữ command trong registry và dùng **AvailabilityProvider**. Nếu command chỉ tồn tại khi một module được kích hoạt, có thể đăng ký và hủy đăng ký command theo vòng đời module.

Với annotation model, method **@Command** phải nằm trong Spring bean được quản lý. Spring Boot 4 tự bật command scanning; nếu chạy Spring Framework mà không dùng Boot, cần bật discovery bằng **@EnableCommand**. Với programmatic model, bean kiểu **Command** được registry tự động thu thập từ ApplicationContext.

## 2. Command và CommandRegistry trong kiến trúc 4.x

**Command** là hợp đồng của một lệnh. Nó cung cấp tên, mô tả, help, nhóm, alias, option, argument, provider và phương thức thực thi. **Command.Builder** tạo một đối tượng command mà không cần tự cài đặt toàn bộ hợp đồng.

**CommandRegistry** giữ các command đã đăng ký và cung cấp các thao tác tra cứu, thêm hoặc gỡ:

| Phương thức | Mục đích |
|---|---|
| **getCommands()** | Lấy tập command hiện có |
| **getCommandByName(name)** | Tìm command theo tên |
| **getCommandByAlias(name)** | Tìm command qua alias |
| **getCommandsByPrefix(prefix)** | Lấy các command có prefix tương ứng |
| **registerCommand(command)** | Đăng ký một command |
| **unregisterCommand(command)** | Hủy đăng ký một command |
| **clearCommands()** | Xóa toàn bộ command trong registry |

Tên command là duy nhất. Vì vậy, ứng dụng nên chọn tên ổn định, tránh trùng tên giữa command của ứng dụng, module mở rộng và command tích hợp sẵn. Trước khi đăng ký command động, có thể dùng **getCommandByName()** để kiểm tra tên đã được sử dụng hay chưa.

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["Command bean"]
    B --> C["CommandRegistry"]
    D["Module hoặc tính năng được bật"] --> E["Command.Builder"]
    E --> F["Command object"]
    F --> G["registerCommand(command)"]
    G --> C
    C --> H["CommandParser và CommandExecutor"]
    H --> I["Shell thực thi command"]
    J["Module hoặc tính năng bị tắt"] --> K["unregisterCommand(command)"]
    K --> C
~~~

Registry là nguồn dữ liệu chung để shell tra cứu command. Các thành phần như parser, executor, help và completion sử dụng danh sách command này để phục vụ người dùng.

## 3. Tạo command bằng Command.Builder

Với command đơn giản, **Command.builder()** là cách ngắn gọn nhất. Có thể khai báo tên, mô tả, nhóm, help, alias, option, argument, availability provider, completion provider, exception mapper và logic thực thi.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
class CliCommandConfiguration {

    @Bean
    Command pingCommand() {
        return Command.builder()
                .name("ping")
                .description("Kiểm tra CLI đang hoạt động.")
                .group("System")
                .aliases("health-check")
                .execute(context -> {
                    context.outputWriter().println("pong");
                });
    }
}
~~~

Bean có kiểu **Command** được Spring Shell tự động đưa vào **CommandRegistry**. Vì vậy, khi định nghĩa command dưới dạng bean, không cần gọi **registerCommand()** lần nữa. Đăng ký cùng một command theo cả hai cách có thể gây xung đột tên hoặc đăng ký trùng.

Phương thức **execute()** của builder hỗ trợ hai dạng callback:

- **Consumer<CommandContext>** khi command tự ghi kết quả bằng **context.outputWriter()**.
- **Function<CommandContext, String>** khi command trả về chuỗi để hiển thị.

Ví dụ trả về chuỗi:

~~~java
@Bean
Command greetingCommand() {
    return Command.builder()
            .name("greeting")
            .description("Hiển thị lời chào.")
            .execute(context -> "Xin chào từ Spring Shell");
}
~~~

Nếu cần kiểm soát mã thoát hoặc xử lý trợ giúp ở mức thấp hơn, có thể kế thừa **AbstractCommand**. Lớp này cung cấp tiện ích cho help option **-h** và **--help**, ghi output và yêu cầu cài đặt **doExecute(CommandContext)** để trả về **ExitStatus**.

~~~java
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;

Command command = new AbstractCommand("sync", "Đồng bộ dữ liệu") {

    @Override
    public ExitStatus doExecute(CommandContext context) {
        println("Đã hoàn tất đồng bộ", context);
        return ExitStatus.OK;
    }
};
~~~

Builder phù hợp với phần lớn command thông thường. Dùng **AbstractCommand** khi cần tùy chỉnh sâu hơn cách thực thi và mã thoát.

## 4. Khai báo option và argument trong programmatic model

Trong annotation model, tham số Java và các annotation **@Option**, **@Argument** mô tả đầu vào. Với programmatic model, ứng dụng tạo metadata bằng **CommandOption** và **CommandArgument** rồi truyền chúng vào builder.

### 4.1. CommandOption

**CommandOption.with()** tạo builder cho một option. Có thể khai báo tên ngắn, tên dài, mô tả, kiểu dữ liệu, tính bắt buộc và giá trị mặc định.

~~~java
import org.springframework.shell.core.command.CommandOption;

CommandOption formatOption = CommandOption.with()
        .shortName('f')
        .longName("format")
        .description("Định dạng báo cáo")
        .type(String.class)
        .required(false)
        .defaultValue("json")
        .build();
~~~

Sau đó gắn option vào command:

~~~java
Command command = Command.builder()
        .name("report-preview")
        .description("Xem trước báo cáo.")
        .options(formatOption)
        .execute(context -> {
            CommandOption option = context.getOptionByLongName("format");
            String format = option == null || option.value() == null
                    ? "json"
                    : option.value();

            context.outputWriter().println("Định dạng: " + format);
        });
~~~

Người dùng có thể gọi:

~~~text
report-preview
report-preview --format=csv
report-preview -f csv
~~~

**CommandContext.getOptionByLongName()** lấy option đã phân tích trong lần gọi hiện tại. Giá trị runtime được đọc từ **CommandOption.value()**. Giá trị mặc định được khai báo trong metadata giúp shell xử lý trường hợp người dùng bỏ qua option.

### 4.2. CommandArgument

Argument là dữ liệu vị trí trong command. **CommandArgument.Builder** cho phép khai báo index, mô tả, kiểu dữ liệu, giá trị mặc định và việc argument có nhận nhiều giá trị hay không.

~~~java
import org.springframework.shell.core.command.CommandArgument;

CommandArgument fileArgument = new CommandArgument.Builder()
        .index(0)
        .description("Đường dẫn file đầu vào")
        .type(String.class)
        .build();
~~~

Gắn argument vào command và đọc giá trị trong context:

~~~java
Command command = Command.builder()
        .name("inspect-file")
        .description("Đọc thông tin file.")
        .arguments(fileArgument)
        .execute(context -> {
            CommandArgument argument = context.getArgumentByIndex(0);
            String file = argument == null ? "" : argument.value();
            context.outputWriter().println("File cần kiểm tra: " + file);
        });
~~~

Lệnh tương ứng có dạng **inspect-file README.md**. Dùng option khi người gọi cần truyền giá trị có tên rõ ràng; dùng argument khi vị trí của giá trị là một phần tự nhiên của cú pháp lệnh.

## 5. Đăng ký command động trong lúc ứng dụng chạy

Khi command phụ thuộc vào trạng thái module hoặc tính năng, có thể inject **CommandRegistry** vào một Spring bean quản lý vòng đời command. Bean này tạo command, đăng ký khi tính năng được bật và gỡ command khi tính năng bị tắt.

Ví dụ sau đăng ký command xem trước báo cáo khi module báo cáo được kích hoạt:

~~~java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.CommandRegistry;
import org.springframework.stereotype.Component;

@Component
public class ReportCommandManager {

    private static final String COMMAND_NAME = "report-preview";

    private final CommandRegistry commandRegistry;
    private final ReportService reportService;

    private Command registeredCommand;

    public ReportCommandManager(
            CommandRegistry commandRegistry,
            ReportService reportService) {
        this.commandRegistry = commandRegistry;
        this.reportService = reportService;
    }

    public synchronized void enableReportModule() {
        if (registeredCommand != null) {
            return;
        }

        if (commandRegistry.getCommandByName(COMMAND_NAME) != null
                || commandRegistry.getCommandByName("preview-report") != null
                || commandRegistry.getCommandByAlias("preview-report") != null) {
            throw new IllegalStateException(
                    "Command name or alias is already in use"
            );
        }

        CommandOption formatOption = CommandOption.with()
                .shortName('f')
                .longName("format")
                .description("Định dạng báo cáo")
                .type(String.class)
                .required(false)
                .defaultValue("json")
                .build();

        Command command = Command.builder()
                .name(COMMAND_NAME)
                .description("Xem trước báo cáo.")
                .group("Reports")
                .aliases("preview-report")
                .options(formatOption)
                .execute(context -> {
                    CommandOption option =
                            context.getOptionByLongName("format");
                    String format = option == null || option.value() == null
                            ? "json"
                            : option.value();

                    String report = reportService.preview(format);
                    context.outputWriter().println(report);
                });

        commandRegistry.registerCommand(command);
        registeredCommand = command;
    }

    public synchronized void disableReportModule() {
        if (registeredCommand == null) {
            return;
        }

        commandRegistry.unregisterCommand(registeredCommand);
        registeredCommand = null;
    }
}
~~~

Trong ví dụ:

1. **ReportCommandManager** nhận registry và service nghiệp vụ qua constructor injection.
2. **enableReportModule()** kiểm tra command đã được đăng ký trong manager chưa và kiểm tra tên đã tồn tại trong registry chưa.
3. Manager tạo **CommandOption**, sau đó dùng **Command.builder()** để tạo command.
4. **registerCommand(command)** đưa command vào registry.
5. Manager giữ lại đúng đối tượng command vừa đăng ký.
6. **disableReportModule()** dùng đối tượng đó để gọi **unregisterCommand()**, rồi xóa tham chiếu đang quản lý.

Giữ tham chiếu đến command đã đăng ký rất quan trọng vì API **unregisterCommand()** nhận một đối tượng **Command**, không nhận tên command. Cách này cũng giúp manager biết chính xác command nào thuộc vòng đời của module mình quản lý.

Các phương thức được đánh dấu **synchronized** để tuần tự hóa những lần bật/tắt thông qua cùng manager. Nếu ứng dụng có nhiều thành phần cùng đăng ký command, hãy tập trung thao tác qua một cơ chế quản lý chung để tránh hai nơi cùng kiểm tra một tên rồi đồng thời đăng ký.

Trong ứng dụng thực tế, có thể gọi **enableReportModule()** sau khi module được tải, người dùng kích hoạt tính năng hoặc cấu hình cho phép báo cáo. Khi module dừng hoặc bị vô hiệu hóa, gọi **disableReportModule()** để gỡ command khỏi shell.

## 6. Tùy chỉnh registry khi khởi tạo ứng dụng

Không phải mọi command bổ sung đều cần đăng ký động sau khi ứng dụng đã chạy. Nếu muốn thêm command theo cấu hình ngay khi shell khởi tạo, dùng **CommandRegistryCustomizer**.

Đây là functional interface có phương thức **customize(CommandRegistry)**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.autoconfigure.CommandRegistryCustomizer;
import org.springframework.shell.core.command.Command;

@Configuration
class RegistryConfiguration {

    @Bean
    CommandRegistryCustomizer addDiagnosticsCommand() {
        return registry -> {
            if (registry.getCommandByName("diagnostics") == null) {
                Command command = Command.builder()
                        .name("diagnostics")
                        .description("Hiển thị thông tin chẩn đoán.")
                        .group("System")
                        .execute(context -> {
                            context.outputWriter()
                                    .println("CLI đang hoạt động");
                        });

                registry.registerCommand(command);
            }
        };
    }
}
~~~

Có thể phân biệt hai trường hợp:

| Nhu cầu | Cách triển khai |
|---|---|
| Command cố định, tạo từ cấu hình Spring | Khai báo bean kiểu **Command** |
| Bổ sung command khi registry được tùy chỉnh lúc khởi tạo | **CommandRegistryCustomizer** |
| Bật/tắt command sau khi ứng dụng đã khởi động | Inject **CommandRegistry**, gọi **registerCommand()**/**unregisterCommand()** |

Registry mặc định tự nạp các command được định nghĩa trong ApplicationContext. Vì vậy, không tạo một bean **Command** rồi lại đăng ký chính command đó bằng customizer nếu không có lý do cụ thể. Chọn một cơ chế sở hữu vòng đời command để tránh trùng tên và khó theo dõi.

## 7. Phân biệt đăng ký động và AvailabilityProvider

Không phải lúc nào trạng thái tính năng thay đổi cũng cần thêm hoặc gỡ command. Hãy quyết định theo trải nghiệm mà CLI cần cung cấp:

| Tình huống | Cách xử lý |
|---|---|
| Module báo cáo không được cài hoặc không được cấp quyền sử dụng | Không đăng ký hoặc gỡ command của module |
| Command tải dữ liệu luôn tồn tại, nhưng chỉ dùng được sau khi kết nối | Giữ command và gắn **AvailabilityProvider** |
| Command cần gợi ý các định dạng có thể chọn | Gắn **CompletionProvider** |
| Một command được bật theo cấu hình ngay khi khởi động | Dùng bean **Command** hoặc **CommandRegistryCustomizer** |
| Một plugin được nạp hoặc tháo khi ứng dụng đang chạy | Đăng ký hoặc hủy đăng ký trực tiếp qua registry |

Ví dụ command vẫn xuất hiện trong help nhưng chỉ chạy khi kết nối:

~~~java
import org.springframework.shell.core.command.availability.Availability;

Command downloadCommand = Command.builder()
        .name("download")
        .description("Tải dữ liệu từ máy chủ.")
        .availabilityProvider(() -> connectionService.isConnected()
                ? Availability.available()
                : Availability.unavailable("you are not connected"))
        .execute(context -> {
            downloadService.downloadLatest();
            context.outputWriter().println("Đã tải dữ liệu");
        });
~~~

Availability mô tả trạng thái hiện tại của command. Registry mô tả tập command shell đang quản lý. Dùng đúng cơ chế sẽ giúp help và trải nghiệm tương tác phản ánh đúng khả năng của ứng dụng.

## 8. Quản lý alias, nhóm lệnh và command ẩn

**Command.Builder** hỗ trợ các metadata giúp tổ chức command:

- **name()** đặt tên command.
- **description()** đặt mô tả ngắn xuất hiện trong danh sách help.
- **help()** cung cấp hướng dẫn chi tiết.
- **group()** gom command vào một nhóm.
- **aliases()** khai báo tên gọi thay thế.
- **hidden(true)** ẩn command khỏi danh sách lệnh thông thường.
- **options()** và **arguments()** khai báo tham số.
- **availabilityProvider()**, **completionProvider()** và **exitStatusExceptionMapper()** gắn các hành vi mở rộng.

Ví dụ:

~~~java
Command maintenanceCommand = Command.builder()
        .name("maintenance-check")
        .description("Kiểm tra chế độ bảo trì.")
        .help("Dùng lệnh này để xem trạng thái bảo trì của hệ thống.")
        .group("Administration")
        .aliases("maintenance-status", "maint-check")
        .hidden(false)
        .execute(context -> {
            context.outputWriter().println("Hệ thống đang hoạt động");
        });
~~~

Alias giúp giữ tương thích với cách gọi cũ hoặc tạo tên ngắn thuận tiện. Group giúp help được tổ chức theo chủ đề. Hidden phù hợp với command nội bộ hoặc command hỗ trợ, nhưng ẩn command không phải cơ chế phân quyền. Nếu một lệnh có thể thay đổi dữ liệu nhạy cảm, service vẫn phải xác minh quyền của người gọi.

Không đăng ký hai command có cùng tên; cũng nên kiểm tra alias để tránh làm người dùng gọi nhầm một lệnh. Khi hủy đăng ký, hãy kiểm tra cả tên command lẫn alias qua registry để xác nhận các đường gọi của command đã được gỡ khỏi tập lệnh đang hoạt động.

## 9. CommandRegistry và vòng đời plugin

Một ứng dụng CLI có thể chia command theo module:

~~~mermaid
flowchart TD
    A["Ứng dụng khởi động"] --> B["Core commands"]
    B --> C["CommandRegistry"]
    D["Plugin được nạp"] --> E["PluginCommandManager"]
    E --> F["Tạo Command"]
    F --> G["registerCommand"]
    G --> C
    H["Người dùng gọi command plugin"] --> I["Command thực thi"]
    I --> J["Plugin service"]
    K["Plugin được tháo"] --> L["unregisterCommand"]
    L --> C
~~~

Vòng đời điển hình:

1. Core command được tạo từ Spring bean khi ứng dụng khởi tạo.
2. Module/plugin được nạp và khởi tạo service cần thiết.
3. Manager tạo command dựa trên khả năng mà plugin cung cấp.
4. Manager đăng ký command vào registry.
5. Người dùng gọi command; command chuyển yêu cầu đến service của plugin.
6. Khi plugin dừng, manager gỡ command trước khi giải phóng tài nguyên mà command sử dụng.

Thứ tự tháo gỡ rất quan trọng. Nếu service hoặc tài nguyên plugin đã bị đóng trong khi command vẫn còn đăng ký, người dùng có thể gọi command và gặp lỗi do dependency không còn hoạt động. Vì vậy, hãy gỡ command trước khi đóng service hoặc connection mà command cần.

CommandRegistry quản lý khả năng nhận diện command. Nó không tự quản lý vòng đời plugin, không tự tải JAR, không tạo classloader và không tự đóng tài nguyên của module. Các trách nhiệm đó thuộc hệ thống plugin hoặc module manager của ứng dụng.

## 10. Các lỗi thường gặp khi đăng ký bằng mã

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Command không xuất hiện trong help | Chưa đăng ký command hoặc bean chưa được đưa vào ApplicationContext | Kiểm tra bean kiểu **Command** hoặc lời gọi **registerCommand()** |
| Command trùng tên | Nhiều module cùng sử dụng một tên | Quy hoạch namespace và kiểm tra **getCommandByName()** trước khi đăng ký |
| Không gỡ được command | Gọi **unregisterCommand()** với một đối tượng khác thay vì đối tượng đã đăng ký | Lưu lại command object trong manager |
| Command vẫn tồn tại sau khi plugin dừng | Quên gọi **unregisterCommand()** | Gắn đăng ký/hủy đăng ký với lifecycle của plugin |
| Bean command bị đăng ký hai lần | Vừa khai báo bean kiểu **Command**, vừa gọi **registerCommand()** cho command đó | Chọn một cách quản lý vòng đời |
| Alias gọi nhầm command | Alias bị trùng hoặc không được kiểm soát | Kiểm tra alias khi đăng ký và dùng tên có quy ước |
| Command gọi vào service đã đóng | Gỡ tài nguyên plugin trước khi gỡ command | Hủy đăng ký command trước khi đóng dependency |
| Help không phản ánh tính năng hiện tại | Command ẩn/hiện không đúng hoặc registry không được cập nhật | Kiểm tra vòng đời đăng ký và metadata hidden |

Không nên gọi **clearCommands()** chỉ để gỡ một plugin. Phương thức này xóa toàn bộ command trong registry, có thể bao gồm help, version, script và các command của module khác. Hãy dùng **unregisterCommand(command)** với từng command do module sở hữu.

## 11. Kiểm thử đăng ký và hủy đăng ký

Kiểm thử command động nên tập trung vào vòng đời và kết quả quan sát được:

1. Khi manager kích hoạt module, **getCommandByName()** tìm thấy command mới.
2. Người dùng có thể gọi command qua shell test client hoặc parser/executor tương ứng và nhận output mong đợi.
3. Alias trỏ đến đúng command.
4. Option và argument được parse đúng kiểu, có giá trị mặc định đúng khi bỏ qua.
5. Khi manager tắt module, **getCommandByName()** không còn trả về command đó.
6. Gọi lệnh đã bị gỡ sẽ không còn thực thi command cũ.
7. Bật module nhiều lần không tạo command trùng.
8. Tắt module nhiều lần không làm phát sinh lỗi do hủy đăng ký lặp.
9. Command core và command của plugin khác vẫn hoạt động sau khi một plugin bị gỡ.

Ví dụ kiểm thử đơn giản với registry:

~~~java
@Test
void shouldRegisterAndUnregisterReportCommand() {
    manager.enableReportModule();

    assertThat(commandRegistry.getCommandByName("report-preview"))
            .isNotNull();

    manager.disableReportModule();

    assertThat(commandRegistry.getCommandByName("report-preview"))
            .isNull();
}
~~~

Đây là kiểm thử vòng đời registry. Ngoài ra, nên kiểm thử logic nghiệp vụ của **ReportService** độc lập để xác nhận command chỉ đóng vai trò adapter. Khi cần kiểm tra output và cách parse toàn bộ dòng lệnh, dùng **ShellTestClient** của Spring Shell để chạy command qua luồng thực thi thực tế.

Nếu ứng dụng cho phép nhiều thread bật/tắt module, kiểm thử cả các yêu cầu đồng thời. Manager nên tuần tự hóa thay đổi registry và tránh để hai module cùng đăng ký một tên command.

## 12. Chọn cách đăng ký phù hợp

Có thể dùng các quy tắc sau khi thiết kế CLI:

- Tập command cố định và đơn giản: khai báo bằng **@Command**.
- Command được định nghĩa bằng mã nhưng luôn có từ lúc khởi động: khai báo bean kiểu **Command**.
- Command bổ sung ở thời điểm khởi tạo: dùng **CommandRegistryCustomizer**.
- Command phụ thuộc module hoặc trạng thái runtime: inject **CommandRegistry** và quản lý **registerCommand()**/**unregisterCommand()**.
- Command vẫn cần hiển thị nhưng chỉ chạy khi điều kiện thỏa mãn: dùng **AvailabilityProvider**.
- Command cần option/argument được định nghĩa động: tạo **CommandOption** và **CommandArgument** rồi truyền vào **Command.Builder**.

Mỗi command nên có một nơi sở hữu vòng đời rõ ràng. Khi biết module nào tạo, đăng ký và hủy đăng ký command, ứng dụng sẽ tránh được command mồ côi, xung đột tên và dependency đã bị đóng.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) — annotation model, programmatic model và khả năng đăng ký/hủy đăng ký động.
- [Spring Shell 4.0.4 API — CommandRegistry](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandRegistry.html) — các phương thức tra cứu, đăng ký và hủy đăng ký command.
- [Spring Shell 4.0.4 API — Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html) — hợp đồng thực thi và metadata của command.
- [Spring Shell 4.0.4 API — Command.Builder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.Builder.html) — các thuộc tính builder, option, argument và callback thực thi.
- [Spring Shell 4.0.4 API — CommandOption.Builder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.Builder.html) — khai báo option bằng mã.
- [Spring Shell 4.0.4 API — CommandArgument.Builder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandArgument.Builder.html) — khai báo argument bằng mã.
- [Spring Shell 4.0.4 API — CommandRegistryCustomizer](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/CommandRegistryCustomizer.html) — tùy chỉnh registry.
- [Spring Shell 4.0.4 API — AbstractCommand](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/AbstractCommand.html) — lớp cơ sở cho command tùy chỉnh.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — thay đổi từ CommandRegistration/CommandCatalog sang Command/CommandRegistry.
