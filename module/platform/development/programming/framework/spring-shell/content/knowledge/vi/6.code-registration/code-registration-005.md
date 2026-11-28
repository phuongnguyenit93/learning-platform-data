# CommandCatalog và vòng đời thêm hoặc gỡ lệnh ở 3.x

Spring Shell 3.x cho phép xây dựng command bằng mã Java thông qua `CommandRegistration`, sau đó quản lý các command đã đăng ký trong một `CommandCatalog`. Nhờ đó, ứng dụng có thể thêm hoặc gỡ command ngay khi đang chạy, chẳng hạn bật nhóm lệnh quản trị sau khi người dùng đăng nhập, chỉ cung cấp command của module đang được kích hoạt, hoặc gỡ một command khi phiên làm việc kết thúc.

Cơ chế này phù hợp khi danh sách command phụ thuộc vào trạng thái của ứng dụng. Nó cũng hữu ích khi muốn tạo command từ cấu hình hoặc từ một dịch vụ nghiệp vụ. Để sử dụng đúng, cần phân biệt việc định nghĩa command, việc đưa command vào catalog, và việc thực thi command sau khi người dùng gọi.

Bài học tập trung vào API của Spring Shell 3.x: cách tạo `CommandRegistration`, cách inject và sử dụng `CommandCatalog`, cách đăng ký/gỡ command, vai trò của `CommandCatalogCustomizer` và `CommandResolver`, cũng như cách kiểm thử vòng đời này. API của Spring Shell 4.x đã thay đổi ở một số phần, vì vậy ví dụ cần được đối chiếu với phiên bản dependency của dự án.

## 1. Ba thành phần trong đăng ký command bằng mã

Mô hình programmatic của Spring Shell 3.x xoay quanh ba thành phần:

- **`CommandRegistration`** mô tả một command: tên, mô tả, tham số, alias, availability, chế độ tương tác và target thực thi.
- **`CommandCatalog`** quản lý các `CommandRegistration` mà shell có thể phân giải và gọi.
- **Command target** là phần mã được gọi khi command được thực thi. Target có thể là method trên một POJO, một `Function` hoặc một `Consumer`.

Có thể hình dung mối quan hệ như sau:

~~~mermaid
flowchart TD
    A["Ứng dụng tạo CommandRegistration"] --> B["CommandCatalog"]
    B --> C["Danh sách command đã đăng ký"]
    C --> D["Parser nhận dòng lệnh"]
    D --> E["Tìm registration phù hợp"]
    E --> F["Gọi command target"]
    F --> G["Trả kết quả / output"]
    H["Ứng dụng thay đổi trạng thái"] --> I["register(...) hoặc unregister(...)"]
    I --> B
~~~

`CommandRegistration` là bản mô tả cách một lệnh hoạt động. `CommandCatalog` là nơi quản lý các bản mô tả đó trong phiên chạy shell. Việc tạo một object `CommandRegistration` chưa đồng nghĩa command đã có thể được gọi; object cần được đăng ký vào catalog hoặc được cung cấp qua cơ chế đăng ký mà Spring Shell tự cấu hình.

Các kiểu chính trong Spring Shell 3.x thuộc package `org.springframework.shell.command`, ví dụ:

~~~java
import org.springframework.shell.command.CommandCatalog;
import org.springframework.shell.command.CommandRegistration;
import org.springframework.shell.command.CommandContext;
~~~

## 2. Tạo CommandRegistration

Có thể tạo command bằng `CommandRegistration.builder()`. Builder cho phép khai báo tên lệnh, mô tả, target và các option.

Ví dụ tối giản:

~~~java
CommandRegistration registration = CommandRegistration.builder()
        .command("report export")
        .description("Export the current report")
        .withTarget()
            .function(context -> "Report exported")
            .and()
        .build();
~~~

Lệnh được đặt tên là `report export`. Khi được đăng ký, người dùng có thể gọi lệnh đó từ shell. Function trả về chuỗi; Spring Shell sử dụng giá trị trả về làm output của command.

### 2.1. Đặt tên command và subcommand

Thuộc tính `command(...)` nhận một hoặc nhiều chuỗi. Spring Shell tách các từ để tạo đường dẫn command đầy đủ. Vì vậy, hai cách sau có thể mô tả cùng một command:

~~~java
.command("report export")
~~~

~~~java
.command("report", "export")
~~~

Với lệnh có nhiều cấp, nên dùng tên nhất quán để người dùng dễ khám phá qua trợ giúp. Ví dụ:

- `project list`
- `project select`
- `report export`
- `admin user disable`

Tên command đầy đủ cũng là căn cứ để gỡ command bằng `unregister(String... commandName)`. Cần truyền đúng tên đã đăng ký.

### 2.2. Khai báo option và target

Command có thể đọc giá trị option từ `CommandContext`. Ví dụ dưới đây khai báo option `--format`, có giá trị mặc định là `csv`:

~~~java
CommandRegistration registration = CommandRegistration.builder()
        .command("report export")
        .description("Export the current report")
        .withTarget()
            .function(context -> {
                String format = context.getOptionValue("format");
                return "Export format: " + format;
            })
            .and()
        .withOption()
            .longNames("format")
            .type(String.class)
            .defaultValue("csv")
            .and()
        .build();
~~~

Người dùng có thể gọi:

~~~text
shell:> report export
Export format: csv

shell:> report export --format json
Export format: json
~~~

Target `Function` nhận `CommandContext`. Context cung cấp các giá trị option đã được parser xử lý. Nếu target trả về một giá trị, giá trị đó được in ra shell. Nếu cần ghi output chủ động, có thể sử dụng một `Consumer` và lấy writer từ context theo API của phiên bản đang dùng.

### 2.3. Target có thể là method, Function hoặc Consumer

Spring Shell 3.x hỗ trợ nhiều cách liên kết command với phần thực thi.

**Method trên POJO:**

~~~java
public class ReportCommandTarget {

    public String export(String format) {
        return "Export format: " + format;
    }
}

ReportCommandTarget target = new ReportCommandTarget();

CommandRegistration registration = CommandRegistration.builder()
        .command("report export")
        .withTarget()
            .method(target, "export")
            .and()
        .withOption()
            .longNames("format")
            .type(String.class)
            .and()
        .build();
~~~

**Function:**

~~~java
CommandRegistration registration = CommandRegistration.builder()
        .command("report export")
        .withTarget()
            .function(context -> {
                String format = context.getOptionValue("format");
                return "Export format: " + format;
            })
            .and()
        .withOption()
            .longNames("format")
            .type(String.class)
            .and()
        .build();
~~~

**Consumer:**

~~~java
CommandRegistration registration = CommandRegistration.builder()
        .command("report print")
        .withTarget()
            .consumer(context -> {
                context.getTerminal().writer().println("Report is ready");
            })
            .and()
        .build();
~~~

Method target phù hợp khi đã có lớp xử lý riêng. Function tiện lợi khi cần truy cập trực tiếp context và trả kết quả. Consumer phù hợp khi command chủ động ghi output và không cần trả một giá trị.

Trong ứng dụng Spring, nên giữ logic nghiệp vụ trong service và để target gọi service đó. Tránh đặt toàn bộ xử lý dữ liệu, truy cập cơ sở dữ liệu và quy tắc nghiệp vụ trong lambda đăng ký command.

## 3. CommandCatalog quản lý command đã đăng ký

`CommandCatalog` định nghĩa hợp đồng để quản lý các `CommandRegistration` đang có. Trong Spring Shell 3.x, các thao tác quan trọng là:

| Phương thức | Tác dụng |
|---|---|
| `register(CommandRegistration... registration)` | Thêm một hoặc nhiều command registration |
| `unregister(String... commandName)` | Gỡ command theo tên |
| `unregister(CommandRegistration... registration)` | Gỡ command theo registration object |
| `getRegistrations()` | Lấy map các registration hiện có |
| `of()` | Tạo một instance catalog mặc định |

Ví dụ thao tác trực tiếp:

~~~java
CommandRegistration registration = CommandRegistration.builder()
        .command("maintenance status")
        .description("Show maintenance status")
        .withTarget()
            .function(context -> "Maintenance mode is active")
            .and()
        .build();

commandCatalog.register(registration);

// Khi không còn cần command:
commandCatalog.unregister("maintenance status");
~~~

Có thể gỡ theo chính object đã đăng ký:

~~~java
commandCatalog.register(registration);

// Gỡ registration cụ thể này:
commandCatalog.unregister(registration);
~~~

Dùng tên command thuận tiện khi chỉ cần gỡ theo định danh. Dùng object registration thuận tiện khi thành phần quản lý đang giữ chính object đã tạo và muốn gỡ đúng registration đó.

### 3.1. Inject catalog do Spring Shell quản lý

Trong ứng dụng Spring Boot có Spring Shell starter và auto-configuration tương ứng, có thể inject `CommandCatalog` vào bean quản lý vòng đời command:

~~~java
@Component
public class DynamicCommandManager {

    private final CommandCatalog commandCatalog;

    public DynamicCommandManager(CommandCatalog commandCatalog) {
        this.commandCatalog = commandCatalog;
    }
}
~~~

Không nên tự tạo một `CommandCatalog.of()` mới bên trong mỗi command manager nếu mục tiêu là thay đổi danh sách lệnh của shell đang chạy. Một catalog mới là một instance độc lập; đăng ký vào đó không tự thay đổi catalog mà shell đang sử dụng.

Nếu tự dựng ứng dụng không dùng auto-configuration, cần bảo đảm catalog được tạo và chia sẻ đúng với thành phần phân giải command. Trong ứng dụng Spring Boot thông thường, ưu tiên sử dụng bean do Spring Shell cấu hình.

### 3.2. Đọc danh sách command hiện có

`getRegistrations()` trả về map các `CommandRegistration` được quản lý theo tên. Map trả về là một bản sao, không phải nơi để chỉnh sửa danh sách command.

~~~java
Map<String, CommandRegistration> registrations =
        commandCatalog.getRegistrations();

registrations.forEach((name, registration) ->
        System.out.println(name + " - " + registration.getDescription()));
~~~

Có thể dùng bản sao này để kiểm tra hoặc hiển thị trạng thái. Không nên gọi `registrations.remove(...)` rồi mong command bị gỡ khỏi shell. Muốn thay đổi catalog, hãy dùng `register(...)` hoặc `unregister(...)`.

## 4. Đăng ký command ngay khi ứng dụng khởi động

Nếu command luôn có mặt trong một phiên chạy, có thể khai báo `CommandRegistration` thành Spring bean. Spring Shell 3.x auto-configuration sẽ đưa các bean loại này vào catalog.

~~~java
@Configuration
public class ReportCommandConfiguration {

    @Bean
    CommandRegistration reportExportCommand(ReportService reportService) {
        return CommandRegistration.builder()
                .command("report export")
                .description("Export the current report")
                .withTarget()
                    .function(context -> {
                        String format = context.getOptionValue("format");
                        return reportService.export(format);
                    })
                    .and()
                .withOption()
                    .longNames("format")
                    .type(String.class)
                    .defaultValue("csv")
                    .and()
                .build();
    }
}
~~~

Cách này thích hợp với command có vòng đời gắn với ứng dụng: command được tạo và đăng ký khi context khởi động, sau đó tồn tại trong suốt thời gian shell chạy.

Có thể dùng `CommandRegistration.BuilderSupplier` nếu nhiều command cần chung quy tắc cấu hình builder. Spring Shell cung cấp builder supplier mặc định để mỗi lần lấy builder sẽ có một builder mới. Cơ chế này giúp giảm lặp khi cấu hình option, help hoặc các thiết lập chung.

## 5. Tùy biến catalog ở thời điểm khởi động

`CommandCatalogCustomizer` là functional interface nhận một `CommandCatalog` và cho phép thay đổi catalog trong quá trình auto-configuration.

Ví dụ:

~~~java
@Configuration
public class InitialCatalogConfiguration {

    @Bean
    CommandCatalogCustomizer maintenanceCommandCustomizer() {
        return catalog -> {
            CommandRegistration registration = CommandRegistration.builder()
                    .command("maintenance status")
                    .description("Show maintenance status")
                    .withTarget()
                        .function(context -> "Maintenance mode is inactive")
                        .and()
                    .build();

            catalog.register(registration);
        };
    }
}
~~~

Spring Shell gọi customizer trong quá trình cấu hình catalog. Đây là nơi phù hợp để thêm các command bổ sung ngay lúc khởi động dựa trên cấu hình ứng dụng.

Cần phân biệt hai cách:

- **CommandRegistration bean:** khai báo một registration như bean để Spring Shell tự đăng ký.
- **CommandCatalogCustomizer:** nhận catalog và thực hiện các thao tác tùy biến trên catalog.

Không nên đăng ký cùng một command bằng nhiều cơ chế nếu không có chủ đích rõ ràng. Ví dụ, cùng một registration vừa là bean được auto-register vừa được customizer đăng ký lại có thể gây xung đột hoặc hành vi không mong muốn.

## 6. Thêm và gỡ command khi ứng dụng đang chạy

Điểm mạnh của `CommandCatalog` là có thể thay đổi danh sách command trong lúc shell đang hoạt động. Ví dụ, command quản trị chỉ xuất hiện sau khi người dùng kích hoạt chế độ bảo trì.

### 6.1. Xây dựng một command manager

Ví dụ sau minh họa một bean quản lý command `maintenance status`. Khi bật chế độ bảo trì, manager đăng ký command. Khi tắt chế độ, manager gỡ command.

~~~java
package com.example.cli.command;

import java.util.Map;

import org.springframework.shell.command.CommandCatalog;
import org.springframework.shell.command.CommandRegistration;
import org.springframework.stereotype.Component;

@Component
public class MaintenanceCommandManager {

    private static final String COMMAND_NAME = "maintenance status";

    private final CommandCatalog commandCatalog;
    private final MaintenanceService maintenanceService;

    public MaintenanceCommandManager(
            CommandCatalog commandCatalog,
            MaintenanceService maintenanceService) {
        this.commandCatalog = commandCatalog;
        this.maintenanceService = maintenanceService;
    }

    public synchronized void enableMaintenanceCommands() {
        Map<String, CommandRegistration> current =
                commandCatalog.getRegistrations();

        if (current.containsKey(COMMAND_NAME)) {
            return;
        }

        CommandRegistration registration = CommandRegistration.builder()
                .command("maintenance", "status")
                .description("Show current maintenance state")
                .withTarget()
                    .function(context -> maintenanceService.describeState())
                    .and()
                .build();

        commandCatalog.register(registration);
    }

    public synchronized void disableMaintenanceCommands() {
        commandCatalog.unregister(COMMAND_NAME);
    }
}
~~~

Các điểm đáng chú ý:

- Manager nhận đúng catalog mà shell đang sử dụng qua constructor injection.
- Tên command được khai báo ở một hằng số để tránh sai khác giữa lúc kiểm tra và lúc gỡ.
- Trước khi đăng ký, manager kiểm tra snapshot hiện có để tránh thêm lặp trong luồng gọi thông thường.
- Hai phương thức được đồng bộ hóa để các lời gọi qua cùng manager không đồng thời thực hiện chuỗi kiểm tra và cập nhật.

Đồng bộ hóa trên manager chỉ điều phối các lời gọi đi qua instance manager đó. Nếu có nhiều thành phần khác cùng thay đổi catalog, ứng dụng cần quy định một đầu mối quản lý hoặc một cơ chế phối hợp chung. Không nên mặc định mọi implementation catalog hay mọi thao tác từ nhiều luồng đều có bảo đảm thread-safety giống nhau nếu tài liệu của phiên bản đang dùng không cam kết điều đó.

### 6.2. Gọi manager từ luồng nghiệp vụ

Một luồng nghiệp vụ có thể bật hoặc tắt nhóm command:

~~~java
@Service
public class MaintenanceWorkflow {

    private final MaintenanceCommandManager commandManager;
    private final MaintenanceService maintenanceService;

    public MaintenanceWorkflow(
            MaintenanceCommandManager commandManager,
            MaintenanceService maintenanceService) {
        this.commandManager = commandManager;
        this.maintenanceService = maintenanceService;
    }

    public void startMaintenance() {
        maintenanceService.start();
        commandManager.enableMaintenanceCommands();
    }

    public void finishMaintenance() {
        maintenanceService.finish();
        commandManager.disableMaintenanceCommands();
    }
}
~~~

Trong ứng dụng thật, thứ tự cập nhật trạng thái và catalog cần phản ánh kết quả nghiệp vụ. Nếu bắt đầu bảo trì thất bại, không nên đăng ký command với nội dung mô tả rằng chế độ bảo trì đã bật. Nếu kết thúc bảo trì thất bại, cần quyết định command có tiếp tục tồn tại để người dùng xử lý hay không.

### 6.3. Luồng vòng đời command

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Workflow as MaintenanceWorkflow
    participant Manager as MaintenanceCommandManager
    participant Catalog as CommandCatalog
    User->>Workflow: Bật chế độ bảo trì
    Workflow->>Manager: enableMaintenanceCommands()
    Manager->>Catalog: getRegistrations()
    Catalog-->>Manager: Snapshot hiện tại
    Manager->>Catalog: register(registration)
    Catalog-->>Manager: Đã thêm command
    User->>Catalog: Gọi maintenance status
    Catalog-->>User: Phân giải command và thực thi target
    User->>Workflow: Tắt chế độ bảo trì
    Workflow->>Manager: disableMaintenanceCommands()
    Manager->>Catalog: unregister("maintenance status")
    Catalog-->>Manager: Đã gỡ command
~~~

Sau khi gỡ, các lần phân giải command tiếp theo không còn tìm thấy registration đó trong catalog. Việc gỡ command không tự động hủy một tác vụ đã bắt đầu chạy, đóng tài nguyên mà target đã mở hoặc hoàn tác nghiệp vụ. Các hoạt động đó cần được quản lý riêng ở service hoặc workflow.

## 7. Khi nào nên đăng ký, khi nào nên gỡ, khi nào nên dùng Availability?

Không phải mọi thay đổi trạng thái đều cần thêm hoặc gỡ command. Hãy chọn cơ chế phù hợp với ý nghĩa mà người dùng cần thấy.

| Nhu cầu | Cơ chế phù hợp | Ví dụ |
|---|---|---|
| Command luôn thuộc ứng dụng | Bean `CommandRegistration` | `help`, `version`, `project list` |
| Bổ sung command lúc khởi động | `CommandCatalogCustomizer` | Đăng ký command từ cấu hình module |
| Thêm hoặc gỡ command trong phiên chạy | `CommandCatalog.register/unregister` | Bật nhóm command theo plugin |
| Command tồn tại nhưng tạm thời không thể chạy | Availability | `download` chỉ chạy khi đã kết nối |
| Danh sách command được tính từ nguồn dữ liệu mỗi lần phân giải | `CommandResolver` | Tập command được cung cấp bởi một nguồn động, nhẹ |

Ví dụ, nếu người dùng chưa đăng nhập nhưng command `profile` vẫn có ý nghĩa để giải thích trạng thái, có thể giữ command và dùng Availability để báo chưa đăng nhập. Nếu một plugin chưa được cài đặt và toàn bộ command của plugin không nên xuất hiện, có thể không đăng ký hoặc gỡ các command đó.

Không nên dùng việc gỡ command làm cơ chế bảo mật duy nhất. Nếu một thao tác yêu cầu quyền quản trị, service vẫn phải xác thực quyền trước khi thực hiện. Việc command có xuất hiện trong trợ giúp hay không chỉ là hành vi giao diện của shell.

## 8. CommandResolver và CommandCatalogCustomizer khác nhau thế nào?

Spring Shell 3.x có hai cơ chế bổ trợ thường được nhắc cùng `CommandCatalog`.

### 8.1. CommandCatalogCustomizer

Customizer nhận catalog hiện có và thay đổi nó. Spring Shell sử dụng customizer trong quá trình auto-configuration. Đây là cách phù hợp để bổ sung hoặc tùy chỉnh registration ở thời điểm khởi động.

### 8.2. CommandResolver

`CommandResolver` là một nguồn có thể phân giải danh sách `CommandRegistration` từ trạng thái hoặc dữ liệu riêng. Ví dụ, resolver có thể cung cấp command tùy theo một danh sách tính năng:

~~~java
import java.util.List;
import org.springframework.shell.command.CommandRegistration;
import org.springframework.shell.command.CommandResolver;
import org.springframework.stereotype.Component;

@Component
public class FeatureCommandResolver implements CommandResolver {

    private final FeatureService featureService;

    public FeatureCommandResolver(FeatureService featureService) {
        this.featureService = featureService;
    }

    @Override
    public List<CommandRegistration> resolve() {
        if (!featureService.isReportingEnabled()) {
            return List.of();
        }

        return List.of(createReportCommand());
    }

    private CommandRegistration createReportCommand() {
        return CommandRegistration.builder()
                .command("report status")
                .description("Show reporting feature status")
                .withTarget()
                    .function(context -> "Reporting is enabled")
                    .and()
                .build();
    }
}
~~~

Resolver được gọi mỗi khi command được phân giải. Vì vậy, không nên thực hiện truy vấn mạng chậm, đọc dữ liệu lớn hoặc tính toán nặng trong `resolve()`. Nếu việc phân giải mất nhiều thời gian, shell có thể phản hồi chậm mỗi khi cần tìm command.

Có thể cân nhắc cache hoặc duy trì một snapshot nhỏ được cập nhật khi cấu hình tính năng thay đổi. Nếu cần chủ động thêm/gỡ một command tại một thời điểm cụ thể, `CommandCatalog.register/unregister` thường diễn đạt ý định rõ hơn.

### 8.3. Bảng so sánh

| Cơ chế | Ai quyết định danh sách? | Thời điểm | Phù hợp khi |
|---|---|---|---|
| `CommandRegistration` bean | Cấu hình Spring | Khởi động | Command cố định |
| `CommandCatalogCustomizer` | Customizer | Khởi động | Bổ sung hoặc điều chỉnh catalog ban đầu |
| `CommandCatalog.register/unregister` | Workflow hoặc service | Khi trạng thái thay đổi | Vòng đời command có sự kiện rõ ràng |
| `CommandResolver` | Resolver | Mỗi lần phân giải | Danh sách command được suy ra từ nguồn động và việc tính toán nhanh |

## 9. Những lưu ý về tên, trùng lặp và trạng thái

### 9.1. Dùng một định danh ổn định

Tên command được sử dụng khi đăng ký, tra cứu và gỡ. Nếu lệnh là `maintenance status`, hãy dùng chính xác tên đó ở tất cả các nơi. Có thể định nghĩa tên bằng hằng số để tránh lỗi chính tả.

### 9.2. Tránh đăng ký lặp

Một sự kiện có thể được phát nhiều lần, hoặc một workflow có thể được gọi lại. Trước khi đăng ký, nên xác định command đã tồn tại chưa. Nếu command cần được thay thế, hãy thực hiện quy trình gỡ registration cũ và đăng ký registration mới một cách có kiểm soát.

Không nên dựa vào giả định rằng đăng ký trùng sẽ luôn thay thế registration cũ theo cách mong muốn. Hành vi cụ thể cần được xác minh với implementation và phiên bản đang sử dụng.

### 9.3. Không chỉnh sửa map trả về

`getRegistrations()` trả về một bản sao. Sửa map này chỉ thay đổi bản sao trong bộ nhớ của caller, không thay đổi catalog. Mọi thay đổi phải đi qua API chính thức.

### 9.4. Phối hợp thay đổi catalog

Nếu nhiều luồng hoặc nhiều bean có thể cùng thêm/gỡ command, hãy thiết kế một đầu mối quản lý hoặc cơ chế phối hợp chung. Cần tránh tình huống một luồng kiểm tra command chưa tồn tại trong khi luồng khác vừa đăng ký command đó.

Ví dụ manager ở trên dùng `synchronized` để minh họa điều phối các lời gọi đi qua cùng một bean. Với ứng dụng phức tạp hơn, có thể cần khóa theo nhóm command hoặc một workflow tuần tự hóa thay đổi.

### 9.5. Catalog là trạng thái trong tiến trình

Command được đăng ký động nằm trong catalog của ứng dụng đang chạy. Thay đổi đó không tự ghi vào cấu hình hoặc lưu bền qua lần khởi động tiếp theo. Khi ứng dụng khởi động lại, danh sách command được xây dựng lại từ các bean, customizer, resolver và logic khởi tạo của phiên chạy mới.

Nếu trạng thái tính năng cần tồn tại sau restart, hãy lưu trạng thái đó trong cấu hình hoặc kho dữ liệu phù hợp rồi khôi phục command tương ứng trong quá trình khởi động.

## 10. Kiểm thử vòng đời đăng ký và gỡ command

Kiểm thử nên xác minh cả trạng thái catalog lẫn khả năng người dùng gọi command.

### 10.1. Kiểm thử CommandRegistration

Có thể kiểm tra registration được tạo với đúng tên, mô tả và option:

~~~java
@Test
void shouldCreateReportExportRegistration() {
    CommandRegistration registration = createReportExportCommand();

    assertThat(registration.getCommand()).isEqualTo("report export");
    assertThat(registration.getDescription())
            .isEqualTo("Export the current report");
}
~~~

### 10.2. Kiểm thử register và unregister

~~~java
@Test
void shouldRegisterAndRemoveMaintenanceCommand() {
    CommandRegistration registration = createMaintenanceCommand();

    commandCatalog.register(registration);

    assertThat(commandCatalog.getRegistrations())
            .containsKey("maintenance status");

    commandCatalog.unregister("maintenance status");

    assertThat(commandCatalog.getRegistrations())
            .doesNotContainKey("maintenance status");
}
~~~

Test này xác minh catalog nhận và gỡ registration theo tên. Nếu sử dụng Spring Shell auto-configuration, cần có integration test xác nhận command thực sự được phân giải và gọi được trong shell context.

### 10.3. Các trường hợp nên kiểm thử

- Command xuất hiện sau khi được đăng ký.
- Command không còn được phân giải sau khi được gỡ.
- Đăng ký lặp không tạo ra trạng thái không mong muốn.
- Gỡ command chưa tồn tại được xử lý theo hành vi của phiên bản.
- Option và target vẫn hoạt động sau khi đăng ký động.
- Command chỉ được thêm khi điều kiện nghiệp vụ phù hợp.
- Command được gỡ khi module hoặc phiên làm việc kết thúc.
- Lỗi trong lúc tạo registration không làm workflow đánh dấu tính năng đã bật.
- Các lời gọi đồng thời không làm catalog rơi vào trạng thái không nhất quán.

Trong kiểm thử tích hợp, có thể gọi command qua cơ chế kiểm thử shell của Spring Shell tương ứng với phiên bản dự án. Chỉ kiểm tra `getRegistrations()` chưa chứng minh parser, target và output đều hoạt động đúng.

## 11. Các lỗi thường gặp

| Lỗi | Biểu hiện | Cách xử lý |
|---|---|---|
| Tạo catalog mới thay vì inject catalog của shell | Đăng ký thành công nhưng shell không thấy command | Dùng bean `CommandCatalog` đang được Spring Shell quản lý |
| Chỉ tạo `CommandRegistration` nhưng không đăng ký | Command không xuất hiện | Đăng ký qua bean, customizer hoặc `catalog.register(...)` |
| Gỡ bằng tên không khớp | Command vẫn còn trong catalog | Dùng đúng tên đầy đủ đã đăng ký |
| Sửa map từ `getRegistrations()` | Shell không thay đổi | Gọi `register` hoặc `unregister` |
| Đăng ký command trùng nhiều lần | Có thể gặp xung đột hoặc hành vi thay thế không mong muốn | Kiểm tra trạng thái và quản lý vòng đời tập trung |
| Resolver làm việc nặng | Shell phản hồi chậm khi phân giải command | Giữ `resolve()` nhanh, dùng cache hoặc catalog mutation |
| Gỡ command nhưng quên dừng workflow | Tác vụ nền vẫn tiếp tục chạy | Quản lý việc dừng tác vụ và giải phóng tài nguyên riêng |
| Dùng gỡ command thay cho phân quyền | Service có thể vẫn bị gọi từ đường khác | Kiểm tra authorization trong service |
| Dùng API 3.x trong dự án 4.x | Không biên dịch hoặc không khớp mô hình đăng ký | Đối chiếu migration guide và API của phiên bản đang dùng |

## 12. Bài thực hành: bật và tắt nhóm command báo cáo

Xây dựng một ứng dụng Spring Shell có service `ReportService` và một nhóm command báo cáo chỉ được đăng ký khi tính năng reporting được bật.

Yêu cầu:

1. Tạo command registration `report status` và `report export`.
2. Dùng `CommandCatalog` để đăng ký hai command khi tính năng reporting được bật.
3. Dùng `getRegistrations()` để kiểm tra command đã tồn tại.
4. Khi tắt tính năng, gỡ hai command theo tên.
5. Đảm bảo gọi lại thao tác bật không tạo đăng ký lặp.
6. Kiểm thử command xuất hiện trong trợ giúp sau khi bật.
7. Kiểm thử command không còn được phân giải sau khi tắt.
8. Kiểm tra service vẫn xác thực quyền truy cập khi thực hiện thao tác xuất báo cáo.

Kịch bản mong đợi:

~~~text
shell:> help
# Chưa có nhóm command report

shell:> feature enable reporting

shell:> help
# Xuất hiện report status và report export

shell:> report status
Reporting is enabled

shell:> report export --format json
Report exported as json

shell:> feature disable reporting

shell:> help
# Nhóm command report không còn xuất hiện
~~~

Sau khi hoàn thành, bổ sung trường hợp người dùng đang chạy export thì tính năng bị tắt. Xác định rõ việc gỡ command ảnh hưởng tới lần gọi tiếp theo như thế nào và ứng dụng quản lý tác vụ đang chạy ra sao.

## 13. Checklist khi quản lý command bằng mã

- [ ] Chọn đúng phiên bản Spring Shell 3.x và import API từ package tương ứng.
- [ ] Tạo `CommandRegistration` với tên, mô tả, option và target rõ ràng.
- [ ] Chọn target phù hợp: method, Function hoặc Consumer.
- [ ] Dùng catalog bean đang được shell sử dụng.
- [ ] Đăng ký command bằng bean, customizer hoặc `register(...)` theo đúng vòng đời.
- [ ] Gỡ command bằng đúng tên hoặc registration object.
- [ ] Không chỉnh sửa map trả về từ `getRegistrations()` để thay đổi catalog.
- [ ] Tránh đăng ký lặp và xác định rõ chính sách khi command đã tồn tại.
- [ ] Phối hợp các thay đổi catalog nếu có nhiều luồng hoặc nhiều bean cùng quản lý.
- [ ] Giữ `CommandResolver.resolve()` nhanh nếu sử dụng resolver.
- [ ] Không dùng việc ẩn/gỡ command thay cho authorization ở lớp nghiệp vụ.
- [ ] Quản lý tác vụ đang chạy và tài nguyên độc lập với việc gỡ command.
- [ ] Kiểm thử cả catalog, parser, target và output.
- [ ] Đối chiếu API khi chuyển từ Spring Shell 3.x sang 4.x.

## 14. Kết luận

Trong Spring Shell 3.x, `CommandRegistration` mô tả command và `CommandCatalog` quản lý các registration mà shell có thể phân giải. Ứng dụng có thể đăng ký command như bean ở thời điểm khởi động, tùy biến catalog bằng `CommandCatalogCustomizer`, hoặc thêm/gỡ command động qua `register(...)` và `unregister(...)`.

`CommandResolver` phù hợp khi danh sách command được tính từ một nguồn động mỗi lần phân giải, nhưng cần giữ quá trình đó nhanh. `getRegistrations()` hữu ích để quan sát trạng thái catalog; map trả về là bản sao nên mọi thay đổi phải đi qua API của catalog.

Khi thiết kế vòng đời command, hãy chọn một đầu mối quản lý, dùng tên command ổn định, xử lý đăng ký lặp, phối hợp cập nhật đồng thời và giữ kiểm tra quyền trong service. Việc thêm hoặc gỡ command thay đổi những gì shell có thể gọi trong phiên chạy hiện tại; nó không thay thế quản lý trạng thái nghiệp vụ, dừng tác vụ đang chạy hoặc lưu cấu hình qua lần khởi động sau.

## Tài liệu tham khảo

- [Spring Shell 3.1 Reference: Command Registration](https://docs.spring.io/spring-shell/docs/3.1.0/docs/index.html)
- [Spring Shell 3.1 Reference: Command Catalog](https://docs.spring.io/spring-shell/docs/3.1.0/docs/index.html)
- [Spring Shell 3.1 API: CommandCatalog](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandCatalog.html)
- [Spring Shell 3.1 API: CommandRegistration](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandRegistration.html)
- [Spring Shell 3.1 API: CommandCatalogCustomizer](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandCatalogCustomizer.html)
- [Spring Shell 3.1 API: CommandResolver](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandResolver.html)
- [Spring Shell 3.1 API: CommandContext](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandContext.html)

