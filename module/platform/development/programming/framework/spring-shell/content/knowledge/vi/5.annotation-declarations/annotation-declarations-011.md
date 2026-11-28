# `@CommandGroup` và tiền tố nhóm trong Spring Shell 4.x

Khi một ứng dụng Spring Shell có nhiều command, người dùng cần một cấu trúc dễ nhớ để tìm và gọi chúng. Spring Shell 4 cung cấp annotation `@CommandGroup` để gom các command liên quan trong cùng một lớp, đặt tên nhóm và khai báo một tiền tố chung cho đường dẫn lệnh.

Hai giá trị `name` và `prefix` giải quyết hai việc khác nhau: `name` mô tả nhóm để các command được trình bày cùng nhau trong phần trợ giúp; `prefix` là phần đầu của tên lệnh mà người dùng phải nhập. Hiểu rõ sự khác nhau này giúp thiết kế CLI có namespace nhất quán, ví dụ `user list`, `user show` và `user disable`.

Bài này tập trung vào API annotation của Spring Shell 4.x. `@CommandGroup` được giới thiệu từ phiên bản 4.0.2; nếu dự án đang dùng 4.0.0 hoặc 4.0.1, hãy nâng lên bản có annotation này hoặc dùng cách khai báo phù hợp với phiên bản hiện tại.

## 1. Vì sao cần nhóm command?

Một CLI nhỏ có thể chỉ có vài lệnh ở cấp cao nhất. Khi sản phẩm phát triển, số command tăng lên theo các miền nghiệp vụ như người dùng, phân quyền, báo cáo, cấu hình và vận hành. Nếu tất cả command nằm trong một danh sách phẳng, tên lệnh dễ trùng, phần trợ giúp dài và người dùng khó đoán được lệnh nào thuộc cùng một chức năng.

Nhóm command giúp giải quyết hai vấn đề:

- **Tổ chức khi khám phá:** các command liên quan được trình bày cùng nhóm trong output của lệnh `help` và các nơi hiển thị danh sách command.
- **Tổ chức tên lệnh:** tiền tố chung tạo namespace cho command, giảm nguy cơ xung đột tên và giúp người dùng dự đoán đường dẫn lệnh.

Ví dụ, một công cụ quản trị có thể tổ chức các lệnh như sau:

| Nhóm nghiệp vụ | Prefix | Command đầy đủ |
|---|---|---|
| Quản lý người dùng | `user` | `user list` |
| Quản lý người dùng | `user` | `user show` |
| Quản lý người dùng | `user` | `user disable` |
| Quản lý báo cáo | `report` | `report list` |
| Quản lý báo cáo | `report` | `report export` |

Prefix tạo đường dẫn mà người dùng gọi. Tên nhóm là nhãn để nhóm command trong trợ giúp. Hai giá trị có thể giống nhau về ý nghĩa nghiệp vụ, nhưng không bắt buộc giống nhau về câu chữ.

## 2. `@CommandGroup` là gì?

`@CommandGroup` nằm trong package:

```java
org.springframework.shell.core.command.annotation.CommandGroup
```

Annotation đánh dấu một lớp là nhóm command. Trong API 4.x, annotation có các đặc điểm chính:

- Được áp dụng ở cấp lớp (`@Target(TYPE)`).
- Được giữ ở runtime (`@Retention(RUNTIME)`) để Spring Shell có thể đọc metadata khi đăng ký command.
- Được meta-annotate bằng `@Component`, vì vậy lớp mang `@CommandGroup` là một Spring component candidate và có thể được phát hiện bởi component scanning.
- Được giới thiệu từ Spring Shell `4.0.2`.

Ba thuộc tính của annotation:

| Thuộc tính | Ý nghĩa | Giá trị mặc định |
|---|---|---|
| `name` | Tên hiển thị/định danh nhóm command | Chuỗi rỗng |
| `description` | Mô tả nhóm command | Chuỗi rỗng |
| `prefix` | Tiền tố chung được ghép vào tên các command trong nhóm | Chuỗi rỗng |

Ví dụ tối thiểu:

```java
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(
    name = "User Management",
    description = "Các thao tác quản lý người dùng",
    prefix = "user"
)
public class UserCommands {
    // Các phương thức @Command được khai báo bên trong lớp.
}
```

`@CommandGroup` khai báo metadata chung cho lớp. Mỗi thao tác có thể gọi vẫn cần được đánh dấu bằng `@Command` trên phương thức tương ứng.

## 3. `prefix` và `name` khác nhau như thế nào?

Đây là điểm quan trọng nhất khi dùng `@CommandGroup`.

**`name` là tên nhóm.** Giá trị này cho biết các command thuộc cùng một nhóm chức năng. Nó phục vụ việc tổ chức danh sách command và trợ giúp. Người dùng không cần nhập tên nhóm chỉ vì tên nhóm được khai báo trong annotation.

**`prefix` là tiền tố của đường dẫn lệnh.** Spring Shell ghép prefix chung với tên command ở phương thức. Nếu prefix là `user` và phương thức có `@Command(name = "list")`, command được gọi bằng `user list`.

Ví dụ:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(
    name = "User Management Commands",
    prefix = "user"
)
public class UserCommands {

    @Command(name = "list", description = "Liệt kê người dùng")
    public String list() {
        return "Danh sách người dùng";
    }

    @Command(name = "show", description = "Xem thông tin một người dùng")
    public String show(@Argument(index = 0, description = "Mã người dùng") String id) {
        return "Thông tin người dùng " + id;
    }
}
```

Các command có thể gọi:

```text
user list
user show 42
```

Trong khi đó, `User Management Commands` là nhãn nhóm được dùng khi trình bày danh sách trợ giúp. Không gọi `User Management Commands list` trừ khi đó thực sự là tên lệnh được khai báo.

### Prefix có thể gồm nhiều từ

Prefix không nhất thiết chỉ có một token. Ví dụ:

```java
@CommandGroup(
    name = "GitHub Authentication Commands",
    prefix = "github auth"
)
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

Tên lệnh đầy đủ là `github auth login` và `github auth logout`. Prefix cung cấp các token đầu tiên; tên khai báo ở `@Command` cung cấp phần còn lại của đường dẫn.

### Prefix rỗng

Nếu bỏ thuộc tính `prefix`, giá trị mặc định là chuỗi rỗng. Khi đó, tên command được khai báo ở phương thức là đường dẫn lệnh. Nhóm vẫn có thể có `name` để gom các command trong phần trợ giúp mà không thêm namespace vào cách gọi.

```java
@CommandGroup(name = "Diagnostics")
public class DiagnosticsCommands {

    @Command(name = "health", description = "Kiểm tra trạng thái dịch vụ")
    public String health() {
        return "UP";
    }
}
```

Trong ví dụ này, command được gọi bằng `health`; `Diagnostics` là tên nhóm.

## 4. Khai báo nhiều command trong một nhóm

Thông thường, các command cùng miền nghiệp vụ được đặt trong một lớp. Cách tổ chức này giúp chúng dùng chung service, repository hoặc trạng thái phiên khi có nhu cầu.

Ví dụ lớp quản lý tài khoản:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(
    name = "Account Management",
    description = "Các thao tác quản trị tài khoản",
    prefix = "account"
)
public class AccountCommands {

    @Command(name = "list", description = "Liệt kê tài khoản")
    public String listAccounts() {
        return "Đang hiển thị danh sách tài khoản";
    }

    @Command(name = "show", description = "Xem một tài khoản")
    public String showAccount(
            @Argument(index = 0, description = "Mã tài khoản") String accountId) {
        return "Tài khoản: " + accountId;
    }

    @Command(name = "lock", description = "Khóa một tài khoản")
    public String lockAccount(
            @Argument(index = 0, description = "Mã tài khoản") String accountId) {
        return "Đã gửi yêu cầu khóa tài khoản " + accountId;
    }
}
```

`@CommandGroup` đã là component stereotype, do đó không cần thêm `@Component` chỉ để biến lớp này thành component. Nếu dự án có convention riêng, có thể dùng stereotype cụ thể của ứng dụng; điều quan trọng là lớp phải được đưa vào Spring application context.

Với các command trong ví dụ, đường dẫn gọi là:

```bash
account list
account show 42
account lock 42
```

Khi chạy `help`, các command này được trình bày cùng nhóm `Account Management`. Mỗi command vẫn có mô tả riêng để người dùng hiểu tác dụng của lệnh.

## 5. Tên nhóm và nhóm riêng cho từng command

`@CommandGroup.name` đặt tên nhóm ở cấp lớp. Nếu một command cần xuất hiện trong nhóm khác, thuộc tính `group` trên `@Command` có thể ghi đè tên nhóm được khai báo ở cấp lớp.

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(name = "User Management", prefix = "user")
public class UserCommands {

    @Command(name = "list", description = "Liệt kê người dùng")
    public String list() {
        return "Users";
    }

    @Command(
        name = "health",
        description = "Kiểm tra kết nối dịch vụ người dùng",
        group = "Diagnostics"
    )
    public String health() {
        return "User service is healthy";
    }
}
```

Trong trường hợp này, thuộc tính `group` của command `health` có độ ưu tiên cao hơn tên nhóm cấp lớp khi tổ chức command trong phần trợ giúp. Thuộc tính này điều khiển phân nhóm hiển thị, không phải là cách đổi tên command. Hãy kiểm tra kết quả `help` sau khi áp dụng override để xác nhận cách tổ chức phù hợp với CLI.

Nên dùng override có chọn lọc. Nếu phần lớn command trong một lớp thuộc một miền nghiệp vụ, hãy để `@CommandGroup.name` làm giá trị chung. Chỉ dùng `@Command(group = ...)` khi một thao tác thực sự thuộc nhóm trình bày khác.

## 6. `@CommandGroup.prefix` không phải tiền tố của option

Từ `prefix` dễ gây nhầm lẫn vì các phiên bản Spring Shell cũ từng có thuộc tính `prefix` trên annotation khai báo command để xác định tiền tố option. Trong Spring Shell 4, `@CommandGroup.prefix` có ý nghĩa khác: nó tạo phần đầu của tên command.

Đối với option, hãy dùng `@Option` và khai báo tên ngắn hoặc tên dài:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.shell.core.command.annotation.Option;

@CommandGroup(name = "User Management", prefix = "user")
public class UserCommands {

    @Command(name = "search", description = "Tìm người dùng")
    public String search(
            @Option(shortName = 's', longName = "status", description = "Trạng thái") String status) {
        return "Tìm người dùng có trạng thái " + status;
    }
}
```

Gọi command:

```bash
user search --status ACTIVE
user search -s ACTIVE
```

Ở đây:

- `user` là prefix do `@CommandGroup` thêm vào đường dẫn command.
- `search` là tên command do `@Command` khai báo.
- `--status` và `-s` là tên option do `@Option` khai báo.

Prefix nhóm không thay đổi quy tắc đặt tên option và không tự động tạo option cho command.

## 7. Đăng ký nhóm command trong ứng dụng Spring

Annotation chỉ có tác dụng khi lớp chứa command được đưa vào Spring application context và command discovery được bật.

### Với Spring Boot

Trong ứng dụng Spring Boot, command scanning được auto-configuration bật tự động. Đặt lớp `@CommandGroup` trong package nằm trong phạm vi component scan của ứng dụng. Không cần thêm `@EnableCommand` hoặc `@CommandScan` chỉ để phát hiện các command trong một ứng dụng Boot chuẩn.

Ví dụ cấu trúc package:

```text
com.example.admin
├── AdminApplication.java
└── commands
    ├── AccountCommands.java
    └── ReportCommands.java
```

Nếu `AdminApplication` dùng `@SpringBootApplication` tại package `com.example.admin`, các lớp command bên dưới package đó được component scanning phát hiện. Do `@CommandGroup` có meta-annotation `@Component`, các lớp nhóm đủ điều kiện trở thành Spring bean.

### Không dùng Spring Boot

Nếu tự tạo Spring context, cần bật command discovery bằng `@EnableCommand` và chỉ định các lớp chứa command theo cách được tài liệu của phiên bản 4.x hướng dẫn.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.annotation.EnableCommand;

@Configuration
@EnableCommand({AccountCommands.class, ReportCommands.class})
class ShellConfiguration {
}
```

Sau khi đăng ký, kiểm tra application context và danh sách command đã được tạo. Nếu lớp nằm ngoài phạm vi scan hoặc chưa được đăng ký, annotation có thể đúng nhưng command sẽ không xuất hiện trong shell.

## 8. Tách nhóm theo miền nghiệp vụ

Một nhóm nên gom các command có cùng mục đích và cách sử dụng. Không nên tạo một lớp duy nhất chứa tất cả command của ứng dụng chỉ vì việc khai báo nhanh hơn.

Ví dụ cách chia nhóm:

| Lớp command | Group name | Prefix | Một số command |
|---|---|---|---|
| `AccountCommands` | `Account Management` | `account` | `list`, `show`, `lock`, `unlock` |
| `RoleCommands` | `Role Management` | `role` | `list`, `grant`, `revoke` |
| `ReportCommands` | `Reporting` | `report` | `list`, `export`, `status` |
| `SystemCommands` | `System Operations` | `system` | `health`, `info`, `shutdown` |

Thiết kế prefix theo danh từ hoặc miền nghiệp vụ thường giúp người dùng dự đoán được command. Các động từ mô tả hành động nên đặt ở phần command con, ví dụ `account lock`, `account unlock`, `report export`.

Trước khi chốt prefix, kiểm tra các đường dẫn command đầy đủ để tránh trùng lặp. Ví dụ, hai nhóm cùng dùng prefix `user` và đều có command con `list` sẽ tạo ra cùng một đường dẫn `user list`. Hãy đổi prefix hoặc tên command để mỗi đường dẫn có ý nghĩa rõ ràng.

## 9. Khi dùng mô hình khai báo và mô hình lập trình

`@CommandGroup` dành cho mô hình khai báo bằng annotation. Trong mô hình lập trình, có thể đặt group cho từng command bằng `Command.Builder.group(String)` và khai báo tên command đầy đủ bằng `name(String)`.

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.ExitStatus;

@Configuration
class ProgrammaticCommandConfiguration {

    @Bean
    Command listUsers() {
        return Command.builder()
                .name("user list")
                .group("User Management")
                .description("Liệt kê người dùng")
                .execute(context -> {
                    context.outputWriter().println("Danh sách người dùng");
                    return ExitStatus.OK;
                })
                .build();
    }
}
```

Trong cách này, tên command đầy đủ và group label được khai báo trực tiếp trên command. `Command.Builder.group(...)` không tương đương với việc đặt `@CommandGroup` lên một lớp; nếu dùng mô hình lập trình, hãy quản lý prefix trong tên command theo quy ước của ứng dụng.

Có thể kết hợp hai mô hình trong cùng ứng dụng. Tuy nhiên, nên thống nhất quy tắc đặt tên và nhóm để người dùng không phải học hai cách gọi khác nhau cho những command có chức năng tương tự.

## 10. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy `@CommandGroup` | Dự án dùng Spring Shell trước 4.0.2 | Kiểm tra phiên bản dependency và nâng lên phiên bản hỗ trợ |
| Command không xuất hiện trong `help` | Lớp nhóm không được component scan hoặc command discovery chưa bật | Kiểm tra package, Spring bean và cấu hình `@EnableCommand` nếu không dùng Boot |
| Gọi `list` không chạy nhưng `user list` chạy | Command có prefix `user` | Dùng đường dẫn đầy đủ đã tạo bởi prefix và tên command |
| Người dùng nhập tên group thay vì prefix | Nhầm `name` với `prefix` | Dùng prefix để gọi lệnh; dùng name để tổ chức trợ giúp |
| Tất cả command hiện dưới một nhóm không mong muốn | `group` ở cấp method override tên nhóm cấp lớp | Kiểm tra thuộc tính `group` trên từng `@Command` |
| Command bị trùng đường dẫn | Nhiều nhóm tạo cùng prefix và cùng tên command con | Đổi prefix hoặc tên command để đường dẫn duy nhất |
| Option bị nhầm với prefix nhóm | Dùng `@CommandGroup.prefix` để cố thay đổi tên option | Khai báo option bằng `@Option(shortName, longName)` |
| Code cũ không biên dịch sau nâng cấp | Dùng `@Command` trên lớp hoặc thuộc tính `command` của v3 | Chuyển metadata nhóm sang `@CommandGroup`; đổi tên command sang `name` trên method |

## 11. Bài tập thực hành

Bạn đang xây dựng CLI cho một hệ thống quản trị có hai miền chức năng: quản lý tài khoản và xuất báo cáo. Hãy tổ chức các command bằng Spring Shell 4.x.

1. Tạo lớp `AccountCommands` với `@CommandGroup(name = "Account Management", prefix = "account")`.
2. Khai báo các command `list`, `show` và `disable` bằng `@Command` trên phương thức.
3. Tạo lớp `ReportCommands` với group name `Reporting` và prefix `report`; khai báo `list` và `export`.
4. Dùng `@Argument` hoặc `@Option` cho dữ liệu đầu vào của ít nhất hai command.
5. Chạy ứng dụng và xác nhận `help` trình bày các command theo hai nhóm.
6. Gọi `account show 42` và `report export --format csv`; xác nhận prefix và tên command được kết hợp đúng.
7. Thử đặt `group = "Diagnostics"` cho một command trong `AccountCommands`, sau đó quan sát cách command đó được phân nhóm trong trợ giúp.
8. Tạo một đường dẫn command trùng có chủ ý, quan sát kết quả đăng ký và sửa lại prefix hoặc tên command để loại bỏ xung đột.
9. Viết một command bằng `Command.Builder` với tên đầy đủ và group riêng; so sánh với cách dùng `@CommandGroup`.

**Kết quả cần nộp:** hai lớp command, cấu hình đăng ký, ảnh hoặc nội dung output `help`, các lệnh đã chạy và bảng ánh xạ group name, prefix, command con thành đường dẫn đầy đủ.

## 12. Checklist trước khi đưa nhóm command vào sử dụng

- [ ] Phiên bản Spring Shell từ `4.0.2` trở lên.
- [ ] `@CommandGroup` được đặt trên lớp chứa các phương thức command.
- [ ] Lớp nhóm được Spring quản lý và nằm trong phạm vi component scan hoặc command discovery.
- [ ] `name` được dùng để mô tả nhóm trong trợ giúp.
- [ ] `prefix` được dùng để tạo phần đầu của đường dẫn command.
- [ ] Các phương thức được đánh dấu bằng `@Command` và dùng thuộc tính `name`.
- [ ] Mỗi command có mô tả dễ hiểu và argument/option được khai báo rõ.
- [ ] Các thuộc tính `group` ở cấp method chỉ override khi có chủ đích.
- [ ] Không có đường dẫn command trùng giữa các nhóm.
- [ ] Đã chạy `help` và gọi trực tiếp các command bằng đường dẫn đầy đủ.
- [ ] Không nhầm prefix nhóm với tên option hoặc group label.

## Tài liệu tham khảo

- [Spring Shell Reference Documentation — Organizing Commands](https://docs.spring.io/spring-shell/reference/commands/organize.html)
- [Spring Shell API — `@CommandGroup`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html)
- [Spring Shell API — `@Command`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell Reference Documentation — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell v4 Migration Guide — Command Grouping](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
