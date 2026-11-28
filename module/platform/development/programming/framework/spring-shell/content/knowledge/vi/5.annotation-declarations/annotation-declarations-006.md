# Annotation `@Command` trên phương thức của Spring bean trong 4.x

Trong Spring Shell 4.x, một command có thể được khai báo trực tiếp trên phương thức Java bằng annotation `@Command`. Phương thức đó phải thuộc về một đối tượng do Spring quản lý, chẳng hạn bean mang `@Component` hoặc `@Service`. Spring Shell đọc metadata trên phương thức và các tham số để đăng ký lệnh, chuyển đầu vào thành kiểu Java, sau đó gọi phương thức khi người dùng thực thi command.

Cách khai báo này giúp đặt tên lệnh, mô tả, trợ giúp và hợp đồng đầu vào gần nơi xử lý. Nhóm phát triển có thể gom những command liên quan vào cùng một Spring bean, inject application service qua constructor và giữ cho command method tập trung vào việc tiếp nhận đầu vào, gọi nghiệp vụ rồi trả kết quả phù hợp với terminal.

## `@Command` đánh dấu phương thức

Trong Spring Shell 4.x, `@Command` có phạm vi áp dụng là phương thức (`METHOD`). Lớp khai báo phương thức phải là Spring bean. Một ví dụ tối giản:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class GreetingCommands {

    @Command(name = "greet", description = "Gửi lời chào")
    public String greet() {
        return "Xin chào từ Spring Shell!";
    }
}
```

Khi command được đăng ký, người dùng có thể gọi:

```text
greet
```

Vì phương thức trả về `String`, Spring Shell đưa giá trị trả về ra shell output. Nếu không khai báo `name`, tên phương thức được dùng làm tên command. Dù vậy, với command được sử dụng lâu dài, khai báo `name` tường minh giúp tránh thay đổi tên lệnh ngoài ý muốn khi refactor tên phương thức Java.

`@Command` không phải annotation đánh dấu một lớp chứa lệnh. Không đặt `@Command` trên class để tạo prefix hoặc nhóm lệnh như một số ví dụ cũ. Trong 4.x, annotation này chỉ đánh dấu phương thức; việc gom nhóm và prefix có cách khai báo riêng.

## Đưa command vào Spring ApplicationContext

Annotation chỉ có thể được phát hiện khi lớp chứa phương thức là bean và được cơ chế đăng ký command của ứng dụng xử lý. Với ứng dụng Spring Boot sử dụng Spring Shell 4.x, auto-configuration bật việc quét command. Một lớp `@Component` nằm trong phạm vi component scan thông thường có thể được phát hiện mà không cần thêm `@EnableCommand`.

Ví dụ cấu trúc package:

```text
com.example.cli
  SpringShellApplication.java
  customer
    CustomerCommands.java
  greeting
    GreetingCommands.java
```

Lớp khởi động:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SpringShellApplication {

    public static void main(String[] args) {
        SpringApplication.run(SpringShellApplication.class, args);
    }
}
```

`@SpringBootApplication` thực hiện component scan từ package chứa lớp khởi động xuống các package con. Vì vậy, `CustomerCommands` và `GreetingCommands` cần nằm trong phạm vi quét hoặc được khai báo rõ bằng cấu hình component scan phù hợp. Nếu package command bị loại bởi `excludeFilters` hoặc nằm ngoài vùng quét, bean không được tạo và command sẽ không được đăng ký.

Nếu dùng Spring Framework mà không dùng Spring Boot, cần bật việc phát hiện command bằng `@EnableCommand` trên lớp cấu hình và chỉ định các lớp chứa phương thức `@Command`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.annotation.EnableCommand;

@Configuration
@EnableCommand({CustomerCommands.class, GreetingCommands.class})
public class ShellConfiguration {
}
```

`@EnableCommand` nhận danh sách lớp ứng viên có command. Cách khởi tạo `ApplicationContext` và `ShellRunner` trong ứng dụng không dùng Boot cũng cần được cấu hình theo mô hình chạy của ứng dụng. Không thêm `@EnableCommand` một cách máy móc vào ứng dụng Spring Boot 4.x đã dùng auto-configuration.

Khi nâng cấp lên Spring Shell 4, cần đồng bộ nền tảng: Spring Shell 4 dựa trên Spring Framework 7 và hỗ trợ Spring Boot từ dòng 4 trở lên. Module `spring-shell-core` không còn kéo Spring Boot vào như dependency mặc định; ứng dụng Boot cần thêm `spring-shell-core-autoconfigure` hoặc dùng starter Spring Shell phù hợp. Việc có annotation đúng trong source chưa đủ nếu dependency đăng ký command hoặc auto-configuration không có trên classpath.

## Khai báo tên, mô tả và trợ giúp

`@Command` cung cấp các thuộc tính để mô tả command và điều chỉnh cách command xuất hiện trong shell:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `name` | Tên command; có thể là chuỗi nhiều từ hoặc mảng thành phần | `name = "customer show"` |
| `description` | Mô tả ngắn hiển thị trong danh sách trợ giúp | `description = "Xem thông tin khách hàng"` |
| `value` | Bí danh của `description` | `@Command("Xem khách hàng")` |
| `alias` | Các tên gọi thay thế cho command | `alias = {"customer get", "cust show"}` |
| `group` | Tên nhóm dùng để phân loại command trong trợ giúp | `group = "Customer Management"` |
| `help` | Nội dung trợ giúp chi tiết và ví dụ cách sử dụng | `help = "Dùng: customer show CUS-123456"` |
| `hidden` | Ẩn command khỏi danh sách trợ giúp thông thường | `hidden = true` |
| `availabilityProvider` | Tên bean cung cấp trạng thái khả dụng | `availabilityProvider = "customerAvailability"` |
| `completionProvider` | Tên bean cung cấp gợi ý tự hoàn thành | `completionProvider = "customerCompletion"` |
| `exitStatusExceptionMapper` | Tên bean ánh xạ exception sang mã thoát | `exitStatusExceptionMapper = "commandErrorMapper"` |

Ví dụ:

```java
@Command(
        name = "customer list",
        description = "Liệt kê khách hàng",
        alias = {"customers", "cust list"},
        group = "Customer Management",
        help = "Liệt kê khách hàng. Ví dụ: customer list")
public String list() {
    return customerService.listSummary();
}
```

Tên command có thể viết thành một chuỗi nhiều từ, chẳng hạn `customer list`, hoặc thành mảng như `name = {"customer", "list"}`. Các phần tử được tách và chuẩn hóa thành các từ của tên command. `description` phù hợp cho câu mô tả ngắn trong danh sách trợ giúp; `help` dành cho nội dung chi tiết hơn, có thể nêu cách gọi và ví dụ.

Chỉ dùng alias khi thật sự cần hỗ trợ tên gọi ngắn hoặc tương thích với người dùng cũ. Mỗi alias cần dễ hiểu và không gây xung đột với command khác. Command ẩn vẫn có thể được gọi nếu người dùng biết tên; `hidden` chủ yếu điều chỉnh việc hiển thị trong trợ giúp.

## Nhận option và argument trên tham số phương thức

Trong Spring Shell 4.x, tham số phương thức được mô tả bằng annotation chuyên biệt:

- `@Option` dùng cho giá trị có tên, thường được viết sau `--` hoặc `-`.
- `@Argument` dùng cho giá trị vị trí, được nhận theo thứ tự trong dòng lệnh.
- `@Arguments` dùng để thu thập nhiều argument vào mảng hoặc collection.

`@Option` có thể khai báo `shortName`, `longName`, `description`, `required` và `defaultValue`. Giá trị mặc định của `required` là `false`; nếu option phải được cung cấp, hãy đánh dấu `required = true`. `@Argument` yêu cầu `index` để xác định vị trí và có thể có `description` hoặc `defaultValue`.

Ví dụ một command xem khách hàng:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Command(
            name = "customer show",
            description = "Hiển thị thông tin khách hàng",
            group = "Customer Management",
            help = "Dùng: customer show CUS-123456 [--details true]")
    public String show(
            @Argument(index = 0, description = "Mã khách hàng") String code,
            @Option(shortName = 'd', longName = "details",
                    description = "Hiển thị thông tin chi tiết",
                    defaultValue = "false") boolean details) {

        return customerService.describe(code, details);
    }
}
```

Các cách gọi tương ứng:

```text
customer show CUS-123456
customer show CUS-123456 --details true
customer show CUS-123456 -d true
```

`@Argument(index = 0)` chỉ vị trí argument đầu tiên; chỉ số argument bắt đầu từ `0`. `@Option` đặt tên rõ ràng cho một option, đồng thời có thể khai báo tên ngắn, mô tả và giá trị mặc định. Trong Spring Shell 4.x, mỗi option có tối đa một tên ngắn và một tên dài.

Lưu ý cách phân tích option: khi một option được truyền, Spring Shell 4.x luôn mong đợi giá trị của option, kể cả option kiểu boolean. Vì vậy, hãy truyền `--details true` hoặc `--details false`; dạng chỉ có `--details` không phải cách viết boolean flag mặc định của parser 4.x. Nếu bỏ qua option, ví dụ trên sử dụng giá trị mặc định `false`.

Spring Shell 4.x cũng tích hợp Bean Validation cho tham số command. Khi ứng dụng có provider validation phù hợp, các constraint như `@NotBlank`, `@Size`, `@Min` hoặc `@Max` đặt trên tham số được kiểm tra trước khi phương thức command thực thi. Hãy xác nhận dependency validation có trong ứng dụng; annotation constraint không thay thế cho việc cấu hình provider.

### Khi nào dùng argument và khi nào dùng option?

Argument phù hợp với dữ liệu vị trí ngắn gọn, thường là định danh chính của thao tác, chẳng hạn mã khách hàng trong `customer show CUS-123456`. Option phù hợp với dữ liệu có tên, có thể xuất hiện theo nhiều thứ tự hoặc có giá trị mặc định, chẳng hạn `--details true`, `--sort createdAt` hay `--limit 20`.

Với command có nhiều tham số, ưu tiên option có tên để tránh người dùng phải nhớ thứ tự của quá nhiều giá trị. Dùng argument cho những vị trí thật sự tự nhiên và dễ hiểu.

### Thu thập nhiều argument với `@Arguments`

Khi command cần nhận một số lượng argument thay đổi, `@Arguments` có thể gom các token còn lại vào mảng hoặc collection:

```java
@Command(name = "label add", description = "Thêm nhãn cho một đối tượng")
public String addLabels(
        @Argument(index = 0, description = "Mã đối tượng") String code,
        @Arguments List<String> labels) {

    return labelService.add(code, labels);
}
```

Người dùng có thể gọi `label add ITEM-42 urgent review`. Tất cả argument còn lại được thu thập vào `labels`. Kiểu tham số phải là mảng hoặc collection. Từ Spring Shell 4.0.2, `@Arguments` có thuộc tính `arity` để giới hạn số argument được thu thập; nếu cần dùng thuộc tính này, hãy xác nhận phiên bản tối thiểu của dự án.

## Nhóm command bằng `@CommandGroup`

Trong Spring Shell 4.x, `@Command` không còn dùng trên class để tạo nhóm và prefix. Từ phiên bản 4.0.2, có thể dùng `@CommandGroup` trên lớp để cung cấp prefix và thông tin chung cho nhóm command:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(
        prefix = "customer",
        name = "Customer Management",
        description = "Các thao tác quản lý khách hàng")
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Command(name = "list", description = "Liệt kê khách hàng")
    public String list() {
        return customerService.listSummary();
    }

    @Command(name = "show", description = "Xem thông tin khách hàng")
    public String show(@Argument(index = 0) String code) {
        return customerService.describe(code, false);
    }
}
```

Với prefix `customer`, các command trong nhóm có tên `customer list` và `customer show`. `@CommandGroup` cũng là một stereotype Spring component, nên lớp được phát hiện như bean khi component scan bao phủ package đó. Nếu dự án dùng phiên bản 4.0.0 hoặc 4.0.1 chưa có `@CommandGroup`, có thể khai báo tên đầy đủ trong `@Command(name = "customer list")` và dùng thuộc tính `group` để phân loại trong trợ giúp.

Không nhầm `group` trong `@Command` với `prefix` của `@CommandGroup`: `group` phân loại command trong trợ giúp, còn `prefix` thêm phần đầu vào tên command.

## Giá trị trả về và `CommandContext`

Với command đơn giản, phương thức có thể trả về `String` hoặc một giá trị mà shell có thể hiển thị. Khi phương thức trả về một giá trị, Spring Shell in giá trị đó ra shell output. Cách này gọn và dễ kiểm thử:

```java
@Command(name = "system status", description = "Hiển thị trạng thái hệ thống")
public String status() {
    return statusService.summary();
}
```

Khi cần ghi nhiều dòng hoặc truy cập reader/writer của phiên hiện tại, phương thức có thể nhận `CommandContext`:

```java
import java.io.PrintWriter;
import org.springframework.shell.core.command.CommandContext;

@Command(name = "system diagnostics", description = "Hiển thị chẩn đoán hệ thống")
public void diagnostics(CommandContext context) {
    PrintWriter writer = context.outputWriter();
    writer.println("Đang kiểm tra dịch vụ...");
    writer.println(statusService.detailedReport());
    writer.flush();
}
```

`CommandContext` cung cấp thông tin về lần gọi command hiện tại, bao gồm output writer, input reader và dữ liệu đã phân tích. Chỉ dùng nó khi command cần tương tác trực tiếp với luồng I/O hoặc thông tin ngữ cảnh; command thông thường nên nhận các tham số nghiệp vụ rõ ràng và trả kết quả.

## Tách command method khỏi nghiệp vụ

Lớp chứa `@Command` là adapter giao tiếp với terminal. Nó nên chịu trách nhiệm nhận option và argument, gọi service, sau đó định dạng kết quả. Các quy tắc như tính giá, xác định quyền, cập nhật trạng thái, kiểm tra tồn kho và truy cập repository nên nằm trong application service hoặc domain model.

Ví dụ constructor injection trong `CustomerCommands` giúp command gọi `CustomerService` mà không tự tạo service bằng `new`. Điều đó cho phép Spring quản lý dependency, cấu hình giao dịch và thay thế implementation trong kiểm thử.

Nếu nhiều command cần cùng một quy tắc, đặt quy tắc đó trong service dùng chung. Không sao chép logic vào từng phương thức `@Command`; nếu sau này có REST API hoặc tác vụ nền, các adapter đó cũng cần dùng cùng quy tắc.

## Kiểm thử command được khai báo bằng annotation

Nên kiểm tra cả việc command được phát hiện và hành vi khi gọi. Một unit test cho service không chứng minh rằng annotation được quét hoặc option được bind đúng.

Các điểm nên xác minh:

| Nội dung | Điều cần kiểm tra |
| --- | --- |
| Bean discovery | Lớp chứa `@Command` có nằm trong Spring ApplicationContext không? |
| Command registration | Tên command và alias có được đăng ký đúng một lần không? |
| Metadata | Description, help, group và hidden có đúng như khai báo không? |
| Argument | Giá trị vị trí được bind theo đúng index không? |
| Option | Tên ngắn, tên dài, mặc định và kiểu dữ liệu có hoạt động đúng không? |
| Delegation | Command gọi đúng application service với tham số mong đợi không? |
| Output | Giá trị trả về hoặc nội dung writer có đúng không? |
| Failure | Đầu vào sai, command không khả dụng hoặc exception được xử lý phù hợp không? |

Với Spring Boot, có thể dùng kiểm thử tích hợp để khởi tạo application context và xác minh command registry. Với ứng dụng không dùng Boot, kiểm tra cả cấu hình `@EnableCommand`. Khi kiểm thử option boolean, truyền tường minh `true` hoặc `false` như cú pháp của Spring Shell 4.x.

## Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đặt `@Command` trên class | Trong 4.x, `@Command` chỉ áp dụng cho method | Đặt trên từng phương thức; dùng `@CommandGroup` cho prefix nhóm từ 4.0.2 |
| Lớp command không được phát hiện | Không phải Spring bean hoặc nằm ngoài component scan | Thêm stereotype phù hợp và kiểm tra phạm vi quét |
| Dùng `@ShellComponent` hoặc `@ShellMethod` trong 4.x | Annotation legacy đã bị loại bỏ | Dùng `@Component`, `@Command`, `@Option`, `@Argument` |
| Dùng thuộc tính `command` thay cho `name` | API 4.x đổi tên thuộc tính | Dùng `@Command(name = "...")` |
| Thêm `@CommandScan` theo ví dụ cũ | Cơ chế này đã bị loại bỏ trong 4.x | Dùng auto-configuration của Boot hoặc `@EnableCommand` khi không dùng Boot |
| Gọi option boolean mà không truyền giá trị | Parser 4.x yêu cầu mỗi option có giá trị | Truyền `--flag true` hoặc `--flag false` |
| Dùng quá nhiều argument vị trí | Người dùng khó nhớ thứ tự | Chuyển tham số tùy chọn sang `@Option` |
| Viết nghiệp vụ trực tiếp trong command method | Khó tái sử dụng và kiểm thử | Inject application service và giao việc cho use case |

## Quy trình thêm một command mới

1. Xác định Spring bean hoặc nhóm command sẽ sở hữu phương thức mới.
2. Đặt `@Command` trên phương thức và khai báo `name`, `description`, `group` hoặc `help` khi cần.
3. Dùng `@Argument`, `@Option` hoặc `@Arguments` để mô tả đầu vào và chọn kiểu Java phù hợp.
4. Inject application service qua constructor; giữ phương thức command ở vai trò adapter.
5. Xác nhận bean được phát hiện: dùng auto-configuration trong Spring Boot hoặc `@EnableCommand` ngoài Boot.
6. Kiểm thử tên command, metadata, binding tham số, kết quả và lỗi đầu vào.

Khai báo `@Command` trên phương thức Spring bean tạo ra ranh giới rõ ràng giữa giao diện terminal và phần thực thi của ứng dụng. Khi tên lệnh, metadata và tham số được mô tả tường minh, Spring Shell có thể đăng ký command nhất quán, còn nhóm phát triển có thể mở rộng trợ giúp, tự hoàn thành, kiểm thử và xử lý nghiệp vụ theo từng phần riêng.

## Tài liệu tham khảo

- [Command Registration – Spring Shell 4.x](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Command Syntax – Spring Shell 4.x](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [API `@Command` – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [API `@CommandGroup` – Spring Shell 4.x](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html)
- [Hướng dẫn chuyển đổi lên Spring Shell 4](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
