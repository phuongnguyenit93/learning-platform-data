# Nhóm bằng `@CommandGroup` trong mô hình 4.x

Khi ứng dụng Spring Shell có nhiều command, danh sách trợ giúp dễ trở nên dài và khó tìm. Các lệnh cùng phục vụ một nghiệp vụ thường có quan hệ rõ ràng: `customer list`, `customer show`, `customer disable` đều thuộc quản lý khách hàng; `order list`, `order cancel` thuộc xử lý đơn hàng. Nếu tổ chức các lệnh theo nhóm, người dùng dễ nhận ra chức năng của ứng dụng và tìm được command cần chạy.

Trong Spring Shell 4.x, annotation `@Command` chỉ được đặt trên phương thức. Để gom các phương thức command trong cùng một lớp, Spring Shell cung cấp `@CommandGroup`. Annotation này cho phép đặt tên nhóm, mô tả nhóm và một prefix dùng chung cho tên command. Nhờ vậy, mỗi phương thức chỉ cần khai báo phần tên riêng của nó.

`@CommandGroup` có từ Spring Shell 4.0.2. Bài viết sử dụng mô hình annotation của Spring Shell 4.0.2 trở lên; nếu dự án đang ở 4.0.0 hoặc 4.0.1, cần dùng cách khai báo tên đầy đủ và group trực tiếp trên từng `@Command` như phần tương thích phiên bản bên dưới.

## Vai trò của `@CommandGroup`

`@CommandGroup` đánh dấu một lớp là nhóm command. Về mặt annotation, nó có các đặc điểm:

- `@Target(TYPE)`: được đặt trên lớp.
- `@Retention(RUNTIME)`: metadata còn tồn tại lúc chạy để Spring Shell phát hiện.
- `@Component`: bản thân annotation là một Spring stereotype, vì vậy lớp được đánh dấu có thể được component scan phát hiện như một bean.

Ba thuộc tính của annotation đều có giá trị mặc định là chuỗi rỗng:

| Thuộc tính | Vai trò | Ví dụ |
| --- | --- | --- |
| `name` | Tên nhóm dùng để phân loại các command trong trợ giúp | `name = "Quản lý khách hàng"` |
| `description` | Mô tả mục đích của nhóm command | `description = "Các thao tác với hồ sơ khách hàng"` |
| `prefix` | Phần tên chung được thêm vào trước tên của từng command trong nhóm | `prefix = "customer"` |

`name` và `prefix` giải quyết hai việc khác nhau. `name` giúp người dùng nhận biết nhóm trong phần trợ giúp; `prefix` tham gia vào tên command mà người dùng nhập. Ví dụ, nhóm có `name = "Quản lý khách hàng"` và `prefix = "customer"`, còn phương thức có `@Command(name = "list")`, thì command đầy đủ là `customer list`.

Nếu bỏ trống `prefix`, command dùng tên được khai báo trên phương thức. Nếu bỏ trống `name`, nhóm không có tên tường minh; nên đặt tên nhóm rõ ràng cho các tính năng có nhiều command để phần trợ giúp dễ đọc. `description` giúp giải thích phạm vi nhóm và có thể được dùng bởi phần hiển thị trợ giúp tùy bố cục của phiên bản.

## Ví dụ: nhóm các command khách hàng

Giả sử CLI quản lý khách hàng có ba thao tác: liệt kê, xem chi tiết và khóa tài khoản. Ta gom chúng vào một lớp `CustomerCommands`:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(
        name = "Quản lý khách hàng",
        description = "Các thao tác tra cứu và quản lý hồ sơ khách hàng",
        prefix = "customer")
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
    public String show(
            @Argument(index = 0, description = "Mã khách hàng") String code) {
        return customerService.describe(code);
    }

    @Command(name = "disable", description = "Khóa tài khoản khách hàng")
    public String disable(
            @Argument(index = 0, description = "Mã khách hàng") String code) {
        customerService.disable(code);
        return "Đã khóa tài khoản " + code;
    }
}
```

Lớp trên không cần thêm `@Component` vì `@CommandGroup` đã là một stereotype component. Spring tạo bean cho lớp, inject `CustomerService` qua constructor và Spring Shell phát hiện các phương thức được đánh dấu `@Command`.

Người dùng gọi các lệnh bằng tên đã ghép prefix:

```text
customer list
customer show CUS-123456
customer disable CUS-123456
```

Trong phần trợ giúp, các command này được xếp dưới nhóm `Quản lý khách hàng`. Phương thức chỉ khai báo phần tên riêng như `list`, `show` hoặc `disable`; prefix `customer` được áp dụng chung từ lớp. Cách tổ chức này giữ cho các tên command nhất quán khi thêm thao tác mới.

## Phân biệt tên nhóm, prefix và tên command

Ba thành phần này thường bị nhầm lẫn khi tổ chức command:

| Thành phần | Ví dụ | Người dùng nhìn thấy hoặc sử dụng |
| --- | --- | --- |
| Tên nhóm (`name`) | `Quản lý khách hàng` | Nhãn nhóm trong trợ giúp |
| Prefix (`prefix`) | `customer` | Phần đầu của tên command |
| Tên phương thức (`@Command(name = ...)`) | `show` | Phần tên riêng sau prefix |
| Tên command đầy đủ | `customer show` | Cú pháp người dùng nhập trong terminal |

Ví dụ khác với prefix gồm nhiều từ:

```java
@CommandGroup(
        name = "Xác thực GitHub",
        description = "Đăng nhập và đăng xuất GitHub",
        prefix = "github auth")
public class GitHubAuthenticationCommands {

    @Command(name = "login", description = "Đăng nhập GitHub")
    public String login() {
        return "Đã đăng nhập GitHub";
    }

    @Command(name = "logout", description = "Đăng xuất GitHub")
    public String logout() {
        return "Đã đăng xuất GitHub";
    }
}
```

Tên command hoàn chỉnh là `github auth login` và `github auth logout`. Prefix có thể gồm nhiều từ để biểu diễn namespace theo miền nghiệp vụ. Khi đã chọn prefix, tên trên phương thức nên là phần đuôi của command.

Một lỗi thường gặp là lặp prefix ở cả lớp và phương thức. Với `prefix = "customer"`, nếu phương thức khai báo `@Command(name = "customer list")`, kết quả sẽ có phần tên bị lặp thay vì chỉ là `customer list`. Hãy để `@Command(name = "list")` khi lớp đã cung cấp prefix.

## Tổ chức nhiều nhóm theo tính năng

Khi ứng dụng lớn dần, nên chia command theo năng lực nghiệp vụ hoặc khu vực chức năng. Mỗi nhóm có một lớp Spring bean riêng, một prefix dễ nhớ và một tên nhóm mô tả đúng phạm vi.

```text
com.example.cli
  SpringShellApplication.java
  customer
    CustomerCommands.java
  order
    OrderCommands.java
  inventory
    InventoryCommands.java
```

Ví dụ, `OrderCommands` có thể khai báo:

```java
@CommandGroup(
        name = "Quản lý đơn hàng",
        description = "Tra cứu và xử lý đơn hàng",
        prefix = "order")
public class OrderCommands {

    private final OrderService orderService;

    public OrderCommands(OrderService orderService) {
        this.orderService = orderService;
    }

    @Command(name = "list", description = "Liệt kê đơn hàng")
    public String list() {
        return orderService.listSummary();
    }

    @Command(name = "cancel", description = "Hủy đơn hàng")
    public String cancel(
            @Argument(index = 0, description = "Mã đơn hàng") String orderCode) {
        orderService.cancel(orderCode);
        return "Đã hủy đơn hàng " + orderCode;
    }
}
```

Các command tương ứng là `order list` và `order cancel`. Khi người dùng gọi `help`, danh sách có thể được chia thành những nhóm như `Quản lý khách hàng`, `Quản lý đơn hàng` và `Quản lý kho`, thay vì hiển thị mọi command như một danh sách dài.

Một nhóm nên có phạm vi đủ rõ để người đọc đoán được nơi đặt command mới. Không nên gom mọi lệnh vào một lớp `GeneralCommands` chỉ vì chúng đều là command; sau một thời gian, lớp đó sẽ khó tìm kiếm, khó kiểm thử và khó giao trách nhiệm.

## Ghi đè tên nhóm cho một command

Thông thường, mọi command trong lớp kế thừa tên nhóm từ `@CommandGroup`. Nếu một phương thức thuộc nhóm khác về mặt trợ giúp, có thể khai báo `group` ngay trên `@Command`:

```java
@CommandGroup(
        name = "Quản lý khách hàng",
        prefix = "customer")
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Command(name = "list", description = "Liệt kê khách hàng")
    public String list() {
        return customerService.listSummary();
    }

    @Command(
            name = "export",
            description = "Xuất dữ liệu khách hàng",
            group = "Báo cáo")
    public String export() {
        return customerService.exportSummary();
    }
}
```

Command `customer list` thuộc nhóm `Quản lý khách hàng`, còn `customer export` được hiển thị trong nhóm `Báo cáo`. Thuộc tính `group` trên phương thức có quyền ưu tiên cao hơn tên nhóm được đặt ở cấp lớp.

Việc ghi đè `group` chỉ thay đổi phân loại trong trợ giúp. Prefix của lớp vẫn được áp dụng cho tên command. Do đó, `customer export` vẫn giữ nguyên tên gọi dù nó xuất hiện dưới nhóm `Báo cáo`.

Chỉ nên ghi đè nhóm khi có lý do rõ ràng, chẳng hạn một lệnh báo cáo được đặt cạnh command khách hàng vì dùng chung dữ liệu nhưng thuộc một nhóm thao tác khác. Nếu nhiều phương thức liên tục phải ghi đè group, đó có thể là dấu hiệu lớp đang chứa nhiều trách nhiệm và nên được tách thành các nhóm riêng.

## Đưa nhóm command vào Spring ApplicationContext

`@CommandGroup` được đánh dấu là `@Component`, vì vậy lớp nhóm cần nằm trong phạm vi component scan của ứng dụng. Với Spring Boot 4 và Spring Shell 4, command scanning được bật tự động bởi auto-configuration. Cấu trúc package phổ biến là đặt lớp khởi động ở package gốc và các nhóm command trong package con:

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

Ví dụ nếu lớp này nằm trong `com.example.cli`, các lớp trong `com.example.cli.customer`, `com.example.cli.order` và `com.example.cli.inventory` nằm trong phạm vi component scan mặc định. Nếu dự án cấu hình `@ComponentScan` với package giới hạn, hãy đưa package chứa các nhóm vào danh sách quét.

Với ứng dụng không dùng Spring Boot, cần bật phát hiện command bằng `@EnableCommand` và chỉ định các lớp ứng viên:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.annotation.EnableCommand;

@Configuration
@EnableCommand({CustomerCommands.class, OrderCommands.class})
public class ShellCommandConfiguration {
}
```

`@EnableCommand` đăng ký các lớp chứa command vào cơ chế phát hiện command. Khi thêm một nhóm mới trong ứng dụng không dùng Boot, hãy bổ sung lớp đó vào danh sách ứng viên. Với Spring Boot, không cần thêm `@EnableCommand` một cách máy móc nếu auto-configuration đã đảm nhiệm việc quét.

Lưu ý về nền tảng: Spring Shell 4 dựa trên Spring Framework 7 và hỗ trợ Spring Boot từ dòng 4 trở lên. Nếu ứng dụng dùng Spring Boot, hãy bảo đảm dependency auto-configuration hoặc starter Spring Shell tương ứng đã có trên classpath; chỉ đặt annotation lên lớp không tự cung cấp các dependency còn thiếu.

## Chuyển từ cách nhóm command của Spring Shell 3 sang 4

Ở Spring Shell 3, có thể đặt `@Command` ở cấp lớp để cung cấp prefix và group chung cho các command bên trong. Mô hình đó không còn được hỗ trợ trong Spring Shell 4: `@Command` chỉ được dùng trên phương thức. Spring Shell 4.0.2 bổ sung `@CommandGroup` để đảm nhận vai trò tổ chức nhóm ở cấp lớp.

Ví dụ cách khai báo cũ:

```java
// Spring Shell 3.x
@Command(command = "github auth", group = "GitHub Authentication Commands")
public class GitHubCommands {

    @Command(command = "login", description = "Đăng nhập GitHub")
    public void login() {
        // Xử lý đăng nhập
    }

    @Command(command = "logout", description = "Đăng xuất GitHub")
    public void logout() {
        // Xử lý đăng xuất
    }
}
```

Khai báo tương ứng trong Spring Shell 4.0.2 trở lên:

```java
// Spring Shell 4.0.2+
@CommandGroup(
        prefix = "github auth",
        name = "GitHub Authentication Commands")
public class GitHubCommands {

    @Command(name = "login", description = "Đăng nhập GitHub")
    public void login() {
        // Xử lý đăng nhập
    }

    @Command(name = "logout", description = "Đăng xuất GitHub")
    public void logout() {
        // Xử lý đăng xuất
    }
}
```

Tên lệnh sau chuyển đổi vẫn là `github auth login` và `github auth logout`. Điểm thay đổi là prefix và tên nhóm được chuyển sang `@CommandGroup`, còn từng phương thức dùng `@Command(name = ...)` để khai báo phần tên riêng.

Nếu ứng dụng đang dùng Spring Shell 4.0.0 hoặc 4.0.1, `@CommandGroup` chưa có. Có thể khai báo tên đầy đủ trên từng phương thức và lặp `group` tương ứng:

```java
@Component
public class GitHubCommands {

    @Command(
            name = {"github", "auth", "login"},
            group = "GitHub Authentication Commands",
            description = "Đăng nhập GitHub")
    public void login() {
        // Xử lý đăng nhập
    }

    @Command(
            name = {"github", "auth", "logout"},
            group = "GitHub Authentication Commands",
            description = "Đăng xuất GitHub")
    public void logout() {
        // Xử lý đăng xuất
    }
}
```

Khi nâng cấp lên 4.0.2 trở lên, có thể chuyển phần prefix và group lặp lại sang `@CommandGroup` để giảm trùng lặp.

## Kiểm thử tổ chức nhóm command

Kiểm thử nhóm command cần xác nhận cả metadata và tên gọi cuối cùng. Việc lớp được tạo thành bean chưa chứng minh prefix được ghép đúng hoặc command đã xuất hiện trong trợ giúp.

| Nội dung kiểm tra | Cách xác minh |
| --- | --- |
| Phát hiện bean | Khởi tạo Spring ApplicationContext và xác nhận lớp nhóm được đăng ký |
| Prefix | Gọi tên đầy đủ, ví dụ `customer list`, `customer show` |
| Không lặp prefix | Xác nhận không xuất hiện tên sai như `customer customer list` |
| Tên nhóm | Dùng `help` và xác nhận các lệnh nằm dưới nhóm dự kiến |
| Description | Xác nhận mô tả command và thông tin nhóm đủ rõ |
| Ghi đè group | Kiểm tra command có `@Command(group = ...)` xuất hiện ở nhóm riêng |
| Trùng tên | Đảm bảo không có hai command cùng tên đầy đủ hoặc alias xung đột |
| Delegation | Xác nhận phương thức gọi đúng application service |

Nên có ít nhất một kiểm thử tích hợp cho mỗi nhóm, chạy ứng dụng với cấu hình thực tế và gọi command bằng tên đầy đủ. Nếu dự án dùng Spring Boot, kiểm tra component scan; nếu không dùng Boot, kiểm tra danh sách lớp trong `@EnableCommand`. Khi cấu hình package scan thay đổi, kiểm thử này giúp phát hiện nhóm command bị bỏ sót.

## Những lỗi thường gặp khi dùng `@CommandGroup`

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `@Command` trên class trong 4.x | Không tương thích vì `@Command` chỉ áp dụng cho method | Dùng `@CommandGroup` từ 4.0.2 |
| Dùng `@CommandGroup` trong 4.0.0 hoặc 4.0.1 | Không tìm thấy annotation khi biên dịch | Nâng lên 4.0.2+ hoặc khai báo tên và group trên từng method |
| Lặp prefix ở tên phương thức | Tên command bị lặp phần đầu | Chỉ khai báo phần tên riêng trên `@Command(name = ...)` |
| Nhầm `name` với `prefix` | Tên nhóm và tên command bị tổ chức sai | Dùng `name` cho nhóm trợ giúp, `prefix` cho tên command |
| Đặt lớp ngoài component scan | Nhóm không được phát hiện, command không xuất hiện | Điều chỉnh package scan hoặc `@EnableCommand` |
| Ghi đè `group` không có chủ đích | Một command bị tách khỏi nhóm chung trong trợ giúp | Chỉ dùng `@Command(group = ...)` khi cần phân loại riêng |
| Dồn command không liên quan vào một nhóm | Tên nhóm không còn phản ánh chức năng | Tách lớp theo năng lực nghiệp vụ |
| Xem prefix như cơ chế phân quyền | Người dùng vẫn có thể gọi command nếu có quyền thực thi | Kiểm tra authorization trong application service hoặc security layer |

`@CommandGroup` là công cụ tổ chức và mô tả giao diện CLI. Nó giúp nhóm command và tạo namespace dễ đọc; nó không kiểm soát quyền truy cập và không thay thế validation hay quy tắc nghiệp vụ.

## Quy trình tạo nhóm command mới

1. Xác định nhóm theo một năng lực nghiệp vụ hoặc một khu vực chức năng cụ thể.
2. Chọn `name` dễ hiểu cho phần trợ giúp và `prefix` ngắn, ổn định cho cú pháp command.
3. Đặt lớp nhóm trong package thuộc phạm vi component scan và dùng `@CommandGroup`.
4. Khai báo từng thao tác bằng `@Command(name = "...")`, chỉ ghi phần tên riêng sau prefix.
5. Inject application service qua constructor và giữ phương thức command ở vai trò adapter.
6. Chỉ ghi đè `group` ở cấp phương thức khi command thật sự thuộc nhóm trợ giúp khác.
7. Kiểm thử tên command đầy đủ, trợ giúp, component discovery và hành vi gọi nghiệp vụ.

Khi nhóm command theo `@CommandGroup`, cấu trúc mã nguồn phản ánh rõ các chức năng mà CLI cung cấp. Người dùng có thể tìm lệnh theo nhóm trong trợ giúp và gọi lệnh bằng prefix nhất quán; nhóm phát triển cũng có một vị trí rõ ràng để mở rộng command mà không làm danh sách trợ giúp trở nên khó quản lý.

## Tài liệu tham khảo

- [Organizing Commands – Spring Shell 4.0.2](https://docs.spring.io/spring-shell/reference/commands/organize.html)
- [API `@CommandGroup` – Spring Shell 4.x](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html)
- [API `@Command` – Spring Shell 4.x](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [API `@EnableCommand` – Spring Shell 4.x](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/EnableCommand.html)
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
