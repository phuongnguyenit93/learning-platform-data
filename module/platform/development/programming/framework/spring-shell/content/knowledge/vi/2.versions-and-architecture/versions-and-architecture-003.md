# Các thế hệ annotation legacy, mô hình 3.x và mô hình 4.x

Spring Shell cung cấp nền tảng để xây dựng ứng dụng CLI theo mô hình Spring. Thay vì tự viết bộ phân tích chuỗi lệnh, cơ chế chuyển đổi kiểu dữ liệu, trợ giúp, tự hoàn thành và vòng lặp tương tác, ứng dụng khai báo command rồi để framework xử lý phần hạ tầng. Phần nghiệp vụ vẫn nằm trong các method hoặc command object do ứng dụng quản lý.

API khai báo command đã thay đổi qua nhiều thế hệ. Khi đọc mã nguồn cũ hoặc nâng cấp ứng dụng, cần phân biệt ba lớp thường bị gọi chung là “legacy”: annotation CLI của Spring Shell 1.x, annotation kiểu Shell của 2.x và 3.x, cùng mô hình annotation mới được giới thiệu trong 3.1.x. Spring Shell 4.x tiếp tục mô hình mới này nhưng thay đổi package, cách đặt tên và một số hợp đồng runtime.

| Thế hệ | Cách khai báo tiêu biểu | Cách đăng ký và thực thi |
|---|---|---|
| Spring Shell 1.x | **CommandMarker**, **@CliCommand**, **@CliOption**, **@CliAvailabilityIndicator** | Phát hiện command marker trong Spring context và ánh xạ method được đánh dấu |
| Spring Shell 2.x đến 3.0 | **@ShellComponent**, **@ShellMethod**, **@ShellOption** | Annotation legacy được chuyển thành metadata đăng ký command; từ 2.1 có thêm API **CommandRegistration** |
| Spring Shell 3.1 đến 3.4 | **@Command**, **@Option** và API **CommandRegistration** | Có mô hình annotation mới, mô hình annotation legacy vẫn được giữ để tương thích; command được quản lý qua command catalog |
| Spring Shell 4.x | **@Command**, **@Option**, **@Argument**, **@CommandGroup** | Annotation mới được chuẩn hóa; API lập trình dùng **Command** và **CommandRegistry**; annotation legacy đã bị loại bỏ |

## 1. Spring Shell 1.x: CLI annotations đời đầu

Ở thế hệ 1.x, một lớp cung cấp command thường được khai báo là Spring bean bằng **@Component** và triển khai marker interface **CommandMarker**. Marker này giúp Spring Shell nhận diện lớp chứa command. Method được gắn **@CliCommand**, còn tham số được mô tả bằng **@CliOption**.

~~~java
import org.springframework.shell.core.CommandMarker;
import org.springframework.shell.core.annotation.CliAvailabilityIndicator;
import org.springframework.shell.core.annotation.CliCommand;
import org.springframework.shell.core.annotation.CliOption;
import org.springframework.stereotype.Component;

@Component
public class GreetingCommands implements CommandMarker {

    @CliCommand(value = "greet", help = "Gửi lời chào đến một người.")
    public String greet(
            @CliOption(
                    key = { "name" },
                    mandatory = true,
                    help = "Tên người nhận lời chào"
            ) String name) {
        return "Xin chào " + name;
    }

    @CliAvailabilityIndicator({ "greet" })
    public boolean isGreetAvailable() {
        return true;
    }
}
~~~

Trong ví dụ này:

- **CommandMarker** đánh dấu lớp có thể cung cấp command.
- **@CliCommand** định nghĩa tên lệnh và nội dung trợ giúp. Tên lệnh được khai báo trực tiếp trong annotation, không phụ thuộc tên method Java.
- **@CliOption** khai báo tên tham số, tính bắt buộc và phần trợ giúp của tham số.
- **@CliAvailabilityIndicator** cho phép quyết định command có sẵn tại thời điểm hiện tại hay không. Ứng dụng có thể dùng trạng thái nội bộ để khóa một command cho đến khi người dùng hoàn tất bước chuẩn bị.

Khi chạy trong shell, người dùng có thể gọi command **greet** và truyền option **name**. Method trả về chuỗi để framework hiển thị kết quả. Mô hình này tận dụng Spring Dependency Injection, nhưng yêu cầu marker interface và bộ annotation CLI riêng.

Khi gặp code dùng **CommandMarker** hoặc **@CliCommand**, hãy nhận diện đó là API thế hệ 1.x. Không đổi tên máy móc **@CliCommand** thành **@ShellMethod**: cách tổ chức command, tên thuộc tính và cơ chế phát hiện lớp đã thay đổi giữa hai thế hệ.

## 2. Spring Shell 2.x và legacy annotation model

Ở thế hệ tiếp theo, Spring Shell chuyển sang bộ annotation quen thuộc hơn với ứng dụng Spring:

- **@ShellComponent** đánh dấu một bean có thể chứa command. Annotation này cũng là một stereotype dựa trên **@Component**.
- **@ShellMethod** đánh dấu method có thể được gọi từ shell. Thuộc tính **value** mô tả command; **key** xác định tên lệnh và các alias.
- **@ShellOption** gắn với tham số method để khai báo tên option, giá trị mặc định và cách xử lý giá trị đầu vào.

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class GreetingCommands {

    @ShellMethod(
            value = "Gửi lời chào đến một người.",
            key = "greet"
    )
    public String greet(
            @ShellOption(
                    value = "--name",
                    defaultValue = "World"
            ) String name) {
        return "Hello " + name;
    }
}
~~~

Nếu không khai báo **key**, tên method được chuyển từ camelCase sang dạng command có dấu gạch nối. Ví dụ, method **sayHello()** có thể được gọi bằng **say-hello**. Khi muốn tên lệnh ổn định với API công khai của CLI, nên khai báo **key** rõ ràng thay vì phụ thuộc tên method.

**@ShellOption** cho phép đổi tên option so với tên tham số Java, đặt giá trị mặc định và điều chỉnh cách parse. Spring Shell còn cung cấp các cơ chế liên quan đến availability, validation, completion và help. Các annotation này giúp viết command nhanh, dễ đọc, phù hợp với ứng dụng nhỏ hoặc ứng dụng đã dùng Spring Shell từ thế hệ 2.x.

### Bước chuyển kiến trúc trong 2.1

Spring Shell 2.1 giới thiệu **CommandRegistration** như một API lập trình để mô tả command. Trước thay đổi này, phần lớn thông tin command được giữ trong metadata của **@ShellMethod** rồi framework dùng reflection để gọi method. Thiết kế mới đưa định nghĩa command về một cấu trúc đăng ký tường minh hơn.

**CommandRegistration** cho phép khai báo tên command, target thực thi, option, kiểu dữ liệu, vị trí tham số và các quy tắc parse. Một registration có thể được cung cấp dưới dạng Spring bean hoặc được đăng ký động qua **CommandCatalog**. Nhờ đó, ứng dụng có thể thêm hoặc gỡ command theo trạng thái runtime, thay vì chỉ dựa vào tập method cố định lúc khởi động.

~~~java
@Bean
CommandRegistration statusCommand() {
    return CommandRegistration.builder()
            .command("status")
            .withTarget()
                .function(context -> "Ứng dụng đang hoạt động")
                .and()
            .build();
}
~~~

Điểm quan trọng là annotation **@ShellMethod** và **@ShellOption** vẫn được giữ tương thích. Framework chuyển mô hình annotation thành registration ở phía sau. Vì vậy, từ 2.1 trở đi có thể hiểu hai cách khai báo:

1. Annotation model: mô tả command trên Spring bean và method.
2. Programmatic model: tạo **CommandRegistration** trực tiếp để kiểm soát đăng ký command.

2.1 cũng mở rộng khả năng trình bày terminal, theming và các thành phần giao diện tương tác. Hỗ trợ GraalVM native image chính thức được đưa vào dòng 3.x; các thử nghiệm trước đó trong 2.1 chưa nên được hiểu là cam kết hỗ trợ chính thức của toàn bộ dòng 2.x.

## 3. Spring Shell 3.x: hai annotation model cùng tồn tại

Spring Shell 3.x đi cùng thế hệ Spring Boot 3 và Spring Framework 6. Ví dụ tài liệu 3.1.3 sử dụng JDK 17, Spring Boot 3.1.2 và Spring Framework 6.0.11. Khi chọn phiên bản, cần đối chiếu đúng dòng Spring Boot và JDK của ứng dụng thay vì chỉ nâng version của riêng Spring Shell.

Trong 3.x có hai mô hình annotation:

- **Legacy annotation model**: **@ShellComponent**, **@ShellMethod**, **@ShellOption** và các annotation liên quan. Chúng tiếp tục được duy trì để ứng dụng cũ có thời gian chuyển đổi, nhưng đã được đánh dấu deprecated trong dòng 3.x.
- **New annotation model**: bắt đầu được hỗ trợ tốt hơn từ 3.1.x, dùng **@Command** và **@Option**. Mô hình này được thiết kế để bao phủ các khả năng của API **CommandRegistration** và là hướng chuyển tiếp sang 4.x.

### 3.1. Annotation model mới

Trong 3.x, **@Command** có thể đặt trên method để đánh dấu một command. Annotation cũng có thể đặt trên class để khai báo prefix hoặc thiết lập chung được kế thừa bởi các method command trong class. **@Option** mô tả named option của method.

~~~java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
@Command(command = "report", group = "Report commands")
public class ReportCommands {

    @Command(command = "show", description = "Hiển thị báo cáo.")
    public String show(
            @Option(
                    longNames = "month",
                    shortNames = 'm',
                    required = true
            ) String month) {
        return "Đang hiển thị báo cáo tháng " + month;
    }
}
~~~

Với prefix **report** ở cấp class và command **show** ở cấp method, người dùng gọi **report show --month 2026-11**. Các thuộc tính **longNames** và **shortNames** ở 3.x là mảng, do đó có thể khai báo nhiều tên dài hoặc tên ngắn cho cùng một option.

Một khác biệt quan trọng so với legacy model là **@Command** không tự động làm cho mọi class được phát hiện. Ứng dụng cần bật command discovery bằng **@EnableCommand** hoặc **@CommandScan**. Với Spring Boot, có thể đặt **@CommandScan** trên lớp ứng dụng để quét các command target trong phạm vi package tương ứng. Nếu không dùng Spring Boot, có thể chỉ định các class đích bằng **@EnableCommand**.

### 3.2. Programmatic model trong 3.x

**CommandRegistration** vẫn là API mức thấp để mô tả command. Một registration chứa tên command, target thực thi và các option. **CommandCatalog** quản lý tập registration mà shell biết đến; ứng dụng có thể đăng ký hoặc gỡ một registration khi trạng thái hệ thống thay đổi.

~~~java
CommandRegistration exportCommand() {
    return CommandRegistration.builder()
            .command("export")
            .withOption()
                .longNames("format")
                .shortNames('f')
                .required()
                .and()
            .withTarget()
                .function(context -> {
                    String format = context.getOptionValue("format");
                    return "Xuất dữ liệu theo định dạng " + format;
                })
                .and()
            .build();
}
~~~

Ở góc nhìn kiến trúc, annotation model là cách khai báo thuận tiện cho người viết ứng dụng; registration model biểu diễn command theo cấu trúc mà runtime sử dụng. Cả hai cùng đi vào quá trình parse và thực thi command. Vì vậy, không nên hiểu **@Command** là một runtime độc lập với **CommandRegistration** trong 3.x.

~~~mermaid
flowchart TD
    A["Annotation model<br/>legacy hoặc mới"] --> C["Command registration"]
    B["Programmatic model<br/>CommandRegistration"] --> C
    C --> D["CommandCatalog"]
    E["Dòng lệnh người dùng"] --> F["Command parser"]
    D --> G["Tìm command và target"]
    F --> G
    G --> H["Thực thi method hoặc function"]
    H --> I["Kết quả hiển thị trong shell"]
~~~

Mô hình mới giải quyết một vấn đề thực tế của legacy annotation: những khả năng mới thường phải được thêm vào API registration trước, sau đó mới tìm cách biểu diễn bằng annotation cũ. 3.1.x tạo một bộ annotation mới để có thể đồng bộ tính năng với registration mà không phá vỡ ứng dụng đang dùng **@ShellMethod**.

### 3.3. Nên dùng mô hình nào trong dự án 3.x?

Với code mới trên 3.1–3.4, ưu tiên **@Command** và **@Option** nếu command có cấu trúc ổn định, được khai báo trong Spring bean. Chọn **CommandRegistration** khi cần tạo command động, điều khiển option ở mức chi tiết hoặc xây dựng một lớp tích hợp riêng với runtime.

Với ứng dụng hiện có dùng **@ShellComponent**, **@ShellMethod** và **@ShellOption**, có thể tiếp tục duy trì trên phiên bản 3.x trong thời gian chuyển đổi. Tuy nhiên, nên tránh tạo thêm command mới theo legacy model, vì các annotation này đã deprecated trong 3.x và bị xóa ở 4.x.

## 4. Spring Shell 4.x: mô hình command được chuẩn hóa lại

Spring Shell 4 là một major version có thay đổi tương thích. Dòng 4 dựa trên Spring Framework 7 và yêu cầu Spring Boot 4 trở lên khi tích hợp với Spring Boot. Hướng dẫn migration chính thức khuyến nghị nâng ứng dụng lên phiên bản 3.4.x mới nhất trước khi chuyển sang 4.x để giảm số thay đổi phải xử lý cùng lúc.

### 4.1. Legacy annotations đã bị loại bỏ

Các annotation **@ShellComponent**, **@ShellMethod**, **@ShellOption** và annotation liên quan đã bị xóa trong 4.x. Mã nguồn còn import các kiểu này sẽ không biên dịch sau khi nâng dependency. Hãy chuyển sang **@Command**, **@Option**, **@Argument** và các annotation thuộc package **org.springframework.shell.core.command.annotation**.

Mô hình mới có các quy tắc rõ ràng hơn:

- **@Command** chỉ đặt trên method command. Class khai báo method phải là Spring bean, chẳng hạn dùng **@Component** hoặc **@Service**.
- Thuộc tính **command** của **@Command** trong 3.x được đổi thành **name** trong 4.x.
- Không còn dùng **@Command** trên class để khai báo prefix. Dùng **@CommandGroup(prefix = ..., name = ...)** để gom các command trong cùng class.
- **@Option** dùng **shortName** và **longName** dạng đơn trị, thay cho **shortNames** và **longNames** dạng mảng ở 3.x.
- **@Argument(index = ...)** mô tả tham số vị trí. **@Arguments** có thể gom nhiều đối số còn lại vào một array hoặc collection.

~~~java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.shell.core.command.annotation.Option;

@CommandGroup(prefix = "report", name = "Report commands")
public class ReportCommands {

    @Command(name = "show", description = "Hiển thị báo cáo.")
    public String show(
            @Argument(index = 0, description = "Kỳ báo cáo") String period,
            @Option(
                    shortName = 'v',
                    longName = "verbose",
                    description = "Hiển thị thông tin chi tiết"
            ) boolean verbose) {
        if (verbose) {
            return "Đang hiển thị báo cáo chi tiết cho " + period;
        }
        return "Đang hiển thị báo cáo cho " + period;
    }
}
~~~

**@CommandGroup** cũng là một stereotype Spring component. Prefix **report** được áp dụng cho các method command trong class, vì vậy lệnh có dạng **report show 2026-11 --verbose**. Nếu một command cần nhóm khác, có thể khai báo group riêng ở cấp method.

### 4.2. Khám phá command và đăng ký command

Với Spring Boot 4, việc quét command được bật tự động theo cơ chế auto-configuration. Không cần khai báo **@CommandScan** như trong 3.x. Khi chạy Spring Framework mà không dùng Spring Boot, vẫn cần bật discovery bằng **@EnableCommand**.

API lập trình cũng được thiết kế lại. Thay cho **CommandRegistration** và **CommandCatalog** của 3.x, 4.x dùng:

- **Command**: hợp đồng của một command. Method **execute(CommandContext)** thực thi command và trả về **ExitStatus**.
- **Command.Builder**: tạo command bằng builder, khai báo tên, mô tả, option và logic thực thi.
- **CommandRegistry**: lưu tập command mà shell có thể gọi; có thể đăng ký hoặc gỡ command động.
- **CommandParser** và **CommandExecutor**: phân tích đầu vào và điều phối việc thực thi command đã tìm thấy.

Ví dụ tạo một command bằng builder:

~~~java
@Bean
Command statusCommand() {
    return Command.builder()
            .name("status")
            .execute(context -> {
                context.outputWriter().println("CLI sẵn sàng");
            });
}
~~~

Ở 4.x, bean có kiểu **Command** được tự động đưa vào **CommandRegistry**. Hợp đồng **execute** trả về **ExitStatus**, giúp biểu diễn mã thoát và mô tả kết quả rõ ràng hơn. Cơ chế ánh xạ exception sang exit code dùng **ExitStatusExceptionMapper**; đây là hướng thay thế cho **CommandExceptionResolver** của 3.x.

~~~mermaid
flowchart TD
    A["Người dùng nhập lệnh"] --> B["ShellRunner"]
    B --> C["CommandParser"]
    C --> D["CommandRegistry"]
    D --> E["CommandExecutor"]
    E --> F["Command.execute(CommandContext)"]
    F --> G["ExitStatus và output"]
~~~

### 4.3. Core và terminal adapter được tách rõ hơn

Trong 4.x, **spring-shell-core** không còn phụ thuộc trực tiếp vào Spring Boot hoặc JLine:

- Nếu dùng Spring Boot, thêm starter Spring Shell hoặc cấu hình **spring-shell-core-autoconfigure**.
- Nếu cần trải nghiệm terminal nâng cao của JLine, thêm dependency **spring-shell-jline**.
- Nếu chỉ cần console cơ bản, **SystemShellRunner** dùng **java.io.Console** của JDK và không cần JLine.
- **NonInteractiveShellRunner** phục vụ chạy command từ tham số dòng lệnh, script và quy trình tự động hóa.

Các runner là những cách vận hành shell khác nhau. Một application context chỉ chọn một **ShellRunner** để chạy tại một thời điểm. Mặc định 4.x chạy ở chế độ interactive; đặt **spring.shell.interactive.enabled=false** để chạy non-interactive. Khi đã chọn chế độ non-interactive, ứng dụng nhận command từ tham số khởi động, thực thi rồi kết thúc. Command không còn được đánh dấu riêng là chỉ interactive hoặc chỉ non-interactive bằng **InteractionMode** như 3.x.

Sự tách biệt này giúp phần xử lý command không bị buộc vào một thư viện terminal cụ thể. Đổi lại, khi nâng từ 3.x, cần kiểm tra dependency JLine và cấu hình runner thay vì cho rằng mọi khả năng terminal cũ đều còn nằm trong core.

## 5. Đối chiếu nhanh khi đọc hoặc chuyển đổi code

| Trong code 1.x hoặc 2.x–3.x | Hướng xử lý trong 4.x |
|---|---|
| **CommandMarker** và **@CliCommand** | Tạo Spring bean, đánh dấu method bằng **@Command** |
| **@CliOption** | Dùng **@Option** cho option có tên hoặc **@Argument** cho tham số vị trí |
| **@ShellComponent** và **@ShellMethod** | Dùng bean chứa method **@Command** |
| **@ShellOption** | Dùng **@Option** hoặc **@Argument** tùy cú pháp đầu vào |
| **@Command(command = "show")** của 3.x | **@Command(name = "show")** |
| **@Command(command = "report")** trên class của 3.x | **@CommandGroup(prefix = "report", name = "...")** |
| **@Option(longNames = "verbose", shortNames = 'v')** của 3.x | **@Option(longName = "verbose", shortName = 'v')** |
| **@CommandScan** trong ứng dụng Spring Boot 3.x | Bỏ annotation này; Spring Boot 4 tự bật command scanning |
| **@EnableCommand** trong ứng dụng không dùng Boot | Tiếp tục dùng **@EnableCommand** để bật command discovery |
| **@OptionValues** | Dùng **CompletionProvider** ở cấp command |
| **@CommandAvailability** | Khai báo **availabilityProvider** trên **@Command** |
| **CommandRegistration** và **CommandCatalog** | Dùng **Command**, **Command.Builder** và **CommandRegistry** |
| **CommandExceptionResolver** và **CommandHandlingResult** | Dùng **ExitStatusExceptionMapper** và **ExitStatus** |
| **InteractionMode** trên command | Chọn chế độ interactive hoặc non-interactive khi khởi động shell |

Các bước migration nên được thực hiện theo thứ tự sau:

1. **Chốt nền tảng tương thích.** Spring Shell 4 yêu cầu Spring Framework 7 và Spring Boot 4 trở lên khi dùng Boot. Trước khi nâng, cập nhật dự án 3.x lên nhánh 3.4.x mới nhất theo khuyến nghị của migration guide.
2. **Cập nhật dependency.** Kiểm tra starter đang dùng, tên module auto-configuration và dependency JLine. **spring-shell-autoconfigure** được đổi tên thành **spring-shell-core-autoconfigure**; các module standard được gộp vào core và phần table được chuyển vào JLine.
3. **Thay annotation legacy.** Chuyển từng command từ **@ShellMethod** sang method **@Command**; phân loại tham số thành **@Option** hoặc **@Argument**. Cập nhật import sang **org.springframework.shell.core.command.annotation**.
4. **Sửa cách đặt tên.** Đổi **command** thành **name**, **longNames** thành **longName**, **shortNames** thành **shortName**. Nếu class cũ dùng **@Command** để đặt prefix hoặc nhóm, chuyển sang **@CommandGroup**.
5. **Sửa command discovery.** Bỏ **@CommandScan** trong ứng dụng Spring Boot 4. Với ứng dụng không dùng Boot, giữ **@EnableCommand**.
6. **Rà soát extension points.** Chuyển completion, availability và exception mapping sang các provider/API mới. Kiểm tra các API đã bị loại bỏ trong migration guide, đặc biệt **@OptionValues**, **CommandExceptionResolver** và **InteractionMode**.
7. **Chọn runner và kiểm tra hành vi thực tế.** Xác định ứng dụng cần console cơ bản, JLine hay non-interactive; chạy thử cả lệnh tương tác, gọi trực tiếp từ tham số khởi động và script nếu dự án hỗ trợ các luồng đó.

Không nên thực hiện nâng cấp chỉ bằng thao tác thay import. Một số thay đổi ảnh hưởng đến cú pháp command, cách gom command, discovery, completion, mã thoát và lựa chọn runner. Sau khi chuyển, cần kiểm tra lại help output và các lệnh đang được script hoặc hệ thống bên ngoài gọi.

### Lưu ý về GraalVM native image

Hướng dẫn migration hiện ghi nhận rằng, tính đến Spring Shell 4.0.0, đăng ký command bằng annotation chưa được hỗ trợ cho GraalVM native compilation; cách khai báo command bằng API lập trình là hướng được hỗ trợ trong giới hạn được nêu. Nếu ứng dụng cần native image, hãy kiểm tra issue và release notes của đúng phiên bản đang triển khai trước khi quyết định kiến trúc command. Không suy ra khả năng native image chỉ từ việc ứng dụng chạy được trên JVM.

## 6. Chọn mô hình theo phiên bản và nhu cầu

- **Duy trì ứng dụng 1.x:** giữ nguyên API cũ cho đến khi có kế hoạch nâng cấp rõ ràng. Khi chuyển, cần tái cấu trúc marker interface, tên command và option thay vì đổi annotation theo từng cặp.
- **Duy trì ứng dụng 2.x hoặc 3.0:** các annotation Shell legacy có thể giúp giữ tương thích. Với dự án cần mở rộng lâu dài, lên dòng 3.x phù hợp trước rồi chuyển command sang annotation model mới hoặc programmatic registration.
- **Phát triển trên 3.1–3.4:** ưu tiên **@Command** và **@Option** cho command khai báo tĩnh; dùng **CommandRegistration** khi cần đăng ký động hoặc kiểm soát cấu hình mức thấp. Tránh thêm code mới phụ thuộc annotation đã deprecated.
- **Phát triển hoặc nâng cấp trên 4.x:** dùng annotation package mới và các API **Command**/**CommandRegistry**. Chọn **@CommandGroup** cho nhóm command; chọn programmatic model khi cần đăng ký động hoặc khi yêu cầu native image đòi hỏi.

Tại thời điểm biên soạn ngày 26/11/2026, Spring Shell 4.0.4 đã được phát hành. Nhóm phát triển thông báo dòng 4.x chuyển sang chế độ maintenance, dự kiến tiếp tục nhận bug fix, security update và dependency upgrade đến tháng 12/2027. Với dự án mới, hãy kiểm tra phiên bản Spring Boot, Spring Framework, JDK và chính sách hỗ trợ đang áp dụng trước khi chốt dependency.

Điểm mấu chốt khi đọc code qua nhiều đời Spring Shell là nhận diện đúng lớp API: nhóm annotation Cli thuộc 1.x; nhóm annotation Shell là legacy model được giữ trong 2.x và 3.x; **@Command** mới xuất hiện trong 3.1.x và tiếp tục ở 4.x với package cùng hợp đồng mới. Sự khác biệt này quyết định cách khai báo, phát hiện, đăng ký và thực thi command.

## Tài liệu tham khảo

- [Spring Shell 1.1.0 Reference Documentation](https://docs.spring.io/spring-shell/docs/1.1.x/reference/pdf/spring-shell-reference.pdf) — **CommandMarker**, **@CliCommand**, **@CliOption** và availability indicator.
- [Spring Shell 2.1.0 is now available](https://spring.io/blog/2022/07/25/spring-shell-2-1-0-is-now-available/) — giới thiệu **CommandRegistration**, khả năng đăng ký động, theming và UI components.
- [Spring Shell 3.1.3 Reference Documentation](https://docs.spring.io/spring-shell/docs/3.1.3/docs/index.html) — phân biệt legacy annotation model, new annotation model và programmatic model.
- [Spring Shell 3.3 Legacy Annotation](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/legacyannotation.html) — cách **@ShellComponent** và **@ShellMethod** tạo command.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — breaking changes, package mới, command grouping, registration, runner và native image.
- [Spring Shell 4 Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) — annotation-based registration, programmatic registration và **CommandRegistry**.
- [Spring Shell 4 Execution](https://docs.spring.io/spring-shell/reference/execution.html) — **ShellRunner** và chế độ interactive/non-interactive.
- [Spring Shell 4.0.4 available now](https://spring.io/blog/2026/11/19/spring-shell-4-0-4-available-now/) — phiên bản phát hành và thời hạn maintenance của dòng 4.x.
