# Phân biệt nhóm trong trợ giúp với cây lệnh thực thi

Khi một CLI có nhiều chức năng, người dùng cần vừa tìm được lệnh trong phần trợ giúp, vừa biết chính xác cú pháp để gọi lệnh. Spring Shell hỗ trợ hai khái niệm có liên quan nhưng độc lập: **nhóm hiển thị trong trợ giúp** và **đường dẫn command được parser thực thi**.

Nhóm hiển thị giúp gom những command cùng mục đích dưới một nhãn như `User Management` hoặc `Reporting`. Đường dẫn command xác định chuỗi token mà người dùng nhập, chẳng hạn `user list` hoặc `report export`. Đổi tên nhóm không tự đổi đường dẫn command; thêm tiền tố vào đường dẫn cũng không tự quyết định nhãn nhóm trong trợ giúp.

Bài này sử dụng mô hình API Spring Shell 4.x. Đây là điểm cần chú ý khi nâng cấp từ 3.x, vì Spring Shell 4 chuyển việc gom command ở cấp lớp sang annotation `@CommandGroup` và chỉ dùng `@Command` trên phương thức.

## 1. Hai cấu trúc phục vụ hai mục đích

Hãy xem một ứng dụng quản trị có các thao tác về người dùng:

```text
user list
user show 42
user disable 42
```

Ba lệnh có chung một miền nghiệp vụ. Trong trợ giúp, chúng có thể được trình bày dưới nhóm `User Management`. Nhưng `User Management` không phải là một phần của cú pháp người dùng nhập. Người dùng gọi `user list`, chứ không nhập `User Management list`.

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Group (nhóm trợ giúp) | Command này được xếp cùng nhóm chức năng nào khi hiển thị? | `User Management` |
| Command name/path (đường dẫn command) | Người dùng phải nhập những token nào để gọi command? | `user list` |
| Alias | Có tên gọi thay thế nào cũng gọi được command này? | `users` có thể là alias của một command nếu được khai báo |

Trong Spring Shell, group là metadata phục vụ việc tổ chức danh sách command. Command path là tên command được đăng ký và phân tích khi người dùng nhập lệnh. Alias là một cách gọi thay thế nếu command khai báo alias. Ba thông tin này không thay thế cho nhau.

## 2. Group chỉ tổ chức cách hiển thị

Trong mô hình annotation, thuộc tính `group` của `@Command` xác định nhóm hiển thị của command:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class UserCommands {

    @Command(
        name = "user list",
        group = "User Management",
        description = "Liệt kê người dùng"
    )
    public String list() {
        return "Danh sách người dùng";
    }

    @Command(
        name = "user show",
        group = "User Management",
        description = "Xem thông tin người dùng"
    )
    public String show() {
        return "Thông tin người dùng";
    }
}
```

Hai command được gom dưới group `User Management` khi hiển thị trong trợ giúp. Đường dẫn thực thi vẫn là `user list` và `user show`, được xác định bởi thuộc tính `name`.

Có thể thay group bằng một nhãn khác mà không đổi cách gọi:

```java
@Command(
    name = "user list",
    group = "Account Operations",
    description = "Liệt kê người dùng"
)
public String list() {
    return "Danh sách người dùng";
}
```

Sau thay đổi, người dùng vẫn nhập `user list`. Chỉ cách command được phân nhóm trong trợ giúp thay đổi.

Group cũng có thể được khai báo theo mô hình lập trình bằng `Command.Builder.group(String)`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.ExitStatus;

@Configuration
class UserCommandConfiguration {

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

Ở cả hai mô hình, `group` mô tả nơi command xuất hiện trong danh sách trợ giúp. `name` mới là tên command được đăng ký.

## 3. Command path tạo thành chuỗi token có thứ tự

Spring Shell phân tích cú pháp command theo dạng tổng quát:

```text
CommandSyntax ::= CommandName [SubCommandName]* [Option | Argument]*
```

Ví dụ:

```text
user account show --id 42
```

Trong đó `user account show` là phần tên command và các token phân cấp của đường dẫn; `--id 42` là option cùng giá trị. Parser xử lý tên command path để tìm command đã đăng ký.

Với Spring Shell 4, `@Command.name` có thể khai báo bằng một chuỗi hoặc một mảng token:

```java
@Command(name = "user account show")
public String showAccount() {
    return "Thông tin tài khoản";
}
```

Hoặc:

```java
@Command(name = {"user", "account", "show"})
public String showAccount() {
    return "Thông tin tài khoản";
}
```

Hai cách trên mô tả cùng một command path. Các token tên command có thể được biểu diễn theo dạng nhiều từ; parser hiểu chúng như một đường dẫn lệnh.

Điều này không có nghĩa mỗi token cha phải được khai báo thành một command riêng. Ví dụ, nếu chỉ đăng ký `user account show`, thì `user` hoặc `user account` không tự động trở thành command có thể thực thi. Chúng là các phần của đường dẫn đến command đã đăng ký. Muốn gọi `user` như một command độc lập, ứng dụng phải đăng ký thêm command có tên `user`.

## 4. `@CommandGroup` có cả nhãn trợ giúp và prefix đường dẫn

Trong Spring Shell 4, `@CommandGroup` cho phép khai báo metadata chung ở cấp lớp:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(
    name = "User Management",
    description = "Các thao tác quản lý người dùng",
    prefix = "user"
)
public class UserCommands {

    @Command(name = "list", description = "Liệt kê người dùng")
    public String list() {
        return "Danh sách người dùng";
    }

    @Command(name = "show", description = "Xem thông tin người dùng")
    public String show(@Argument(index = 0) String id) {
        return "Người dùng " + id;
    }
}
```

Ở đây có hai tác dụng riêng:

- `name = "User Management"` đặt tên group để gom các command trong trợ giúp.
- `prefix = "user"` thêm token `user` vào đầu đường dẫn command của các phương thức trong lớp.

Các lệnh được gọi là:

```bash
user list
user show 42
```

Nếu đổi `name` thành `Accounts`, nhãn trợ giúp đổi theo nhưng các lệnh vẫn là `user list` và `user show 42`. Nếu đổi `prefix` thành `account`, đường dẫn sẽ thành `account list` và `account show 42`, còn group name vẫn là `User Management`.

Prefix có thể gồm nhiều token, ví dụ `github auth`. Khi kết hợp với `@Command(name = "login")`, đường dẫn hoàn chỉnh là `github auth login`. Prefix là thành phần ảnh hưởng đến cú pháp thực thi; group name là nhãn trình bày.

`@CommandGroup` có từ Spring Shell `4.0.2`. Nếu dự án dùng `4.0.0` hoặc `4.0.1`, cần kiểm tra phiên bản trước khi dùng annotation này.

## 5. Override group ở cấp phương thức

Nếu một lớp chứa phần lớn command thuộc cùng một nhóm nhưng có một command cần xuất hiện trong nhóm trợ giúp khác, có thể ghi đè group trên `@Command`:

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
        group = "Diagnostics",
        description = "Kiểm tra dịch vụ người dùng"
    )
    public String health() {
        return "User service is healthy";
    }
}
```

`health` được xếp dưới group `Diagnostics` trong trợ giúp. Prefix của lớp vẫn áp dụng, vì vậy đường dẫn command vẫn là `user health`. Thuộc tính `group` ở method override nhãn nhóm, không xóa prefix và không đổi tên command.

Khi thiết kế, hãy dùng group cấp lớp làm giá trị chung và chỉ override ở method khi có lý do rõ ràng. Nếu override quá nhiều, cấu trúc lớp và nhóm trợ giúp có thể không còn phản ánh cùng một miền nghiệp vụ.

## 6. Nhìn kết quả trợ giúp và đường dẫn thực thi riêng biệt

Giả sử ứng dụng đăng ký các command sau:

| Command path | Group |
|---|---|
| `user list` | `User Management` |
| `user show` | `User Management` |
| `user health` | `Diagnostics` |
| `report list` | `Reporting` |
| `report export` | `Reporting` |

Khi người dùng gọi `help`, các command được trình bày theo nhóm tương tự ví dụ minh họa dưới đây:

```text
AVAILABLE COMMANDS

Diagnostics
  user health       Kiểm tra dịch vụ người dùng

Reporting
  report export     Xuất báo cáo
  report list       Liệt kê báo cáo

User Management
  user list         Liệt kê người dùng
  user show         Xem thông tin người dùng
```

Đây là cách minh họa quan hệ giữa group và command path; định dạng, căn cột và thứ tự cụ thể phụ thuộc phiên bản và cấu hình help renderer.

Từ danh sách này, người dùng lấy command path ở cột lệnh để thực thi. Tên group giúp tìm lệnh theo chức năng. Không lấy tên group rồi ghép vào trước command path.

## 7. Group không tạo command cha hoặc ràng buộc quyền thực thi

Một nhầm lẫn phổ biến là nghĩ group `User Management` sẽ tự tạo một command cha `User Management`, hoặc mọi command trong group sẽ được gọi thông qua tên group. Spring Shell không dùng group theo cách đó.

Ví dụ:

```java
@Command(name = "user list", group = "User Management")
public String list() {
    return "Users";
}
```

Command path là `user list`. `User Management` chỉ là nhãn nhóm. Lệnh `User Management` không được tạo ra từ thuộc tính `group`.

Tương tự, group không tự tạo quan hệ cha-con trong registry, không tạo alias, không quyết định command có khả dụng hay không và không thay thế cơ chế phân quyền. Nếu cần:

- Một đường dẫn có nhiều token, hãy khai báo command name hoặc class-level prefix.
- Một cách gọi thay thế, hãy khai báo `alias` trên `@Command`.
- Ẩn command khỏi danh sách trợ giúp, hãy dùng thuộc tính `hidden`.
- Điều khiển command có khả dụng trong một trạng thái hay không, hãy dùng `availabilityProvider`.
- Phân quyền nghiệp vụ, hãy kiểm tra quyền trong lớp service hoặc cơ chế bảo mật của ứng dụng.

Không nên dùng tên group như một cơ chế bảo mật hoặc kiểm soát truy cập. Nó chỉ phục vụ tổ chức và khám phá command.

## 8. Phân biệt group, prefix, command name và alias

Bảng sau tổng hợp vai trò của các thuộc tính thường gặp:

| Thuộc tính | Nơi khai báo | Ảnh hưởng đến trợ giúp | Ảnh hưởng đến cách gọi |
|---|---|---|---|
| `group` | `@Command` hoặc `Command.Builder.group(...)` | Có: gom command dưới nhãn nhóm | Không |
| `@CommandGroup.name` | `@CommandGroup` trên lớp | Có: tên nhóm chung | Không |
| `@CommandGroup.description` | `@CommandGroup` trên lớp | Có: mô tả nhóm nếu renderer sử dụng | Không |
| `@CommandGroup.prefix` | `@CommandGroup` trên lớp | Không phải nhãn nhóm | Có: thêm token vào command path |
| `@Command.name` | `@Command` trên phương thức | Hiển thị tên command | Có: xác định command path |
| `@Command.alias` | `@Command` trên phương thức | Có thể hiển thị theo cách renderer hỗ trợ | Có: tạo tên gọi thay thế |

Khi đọc code, hãy kiểm tra đúng thuộc tính trước khi kết luận cấu trúc lệnh. Nếu muốn command được gọi bằng `user list`, hãy kiểm tra `name` hoặc `prefix` kết hợp `name`. Nếu chỉ muốn nó xuất hiện trong nhóm `User Management`, hãy kiểm tra `group` hoặc `@CommandGroup.name`.

## 9. Chuyển đổi từ Spring Shell 3 sang 4

Spring Shell 3 cho phép đặt `@Command` ở cấp lớp để khai báo command prefix và group chung cho các phương thức. Cách dùng đó đã bị loại bỏ trong Spring Shell 4: `@Command` chỉ được áp dụng trên phương thức. Spring Shell 4 đưa `@CommandGroup` vào để gom các phương thức trong cùng một lớp.

Ví dụ ý tưởng ở v3:

```java
// Spring Shell 3.x
@Command(command = "github auth", group = "GitHub Authentication Commands")
public class GitHubCommands {

    @Command(command = "login")
    public void login() {
        // ...
    }
}
```

Tương đương trong v4:

```java
// Spring Shell 4.x
@CommandGroup(
    prefix = "github auth",
    name = "GitHub Authentication Commands"
)
public class GitHubCommands {

    @Command(name = "login")
    public void login() {
        // ...
    }
}
```

Trong cả hai trường hợp, group label dùng để trình bày trợ giúp và prefix tạo phần đầu của đường dẫn command. Khi nâng cấp, hãy chuyển đúng ý nghĩa của từng thuộc tính; không chuyển group thành prefix hoặc ngược lại.

## 10. Kiểm tra group và command path trong ứng dụng

Sau khi khai báo, hãy xác minh cả hai khía cạnh riêng biệt.

**Kiểm tra phần trợ giúp:**

1. Chạy ứng dụng và nhập `help`.
2. Kiểm tra các command liên quan có xuất hiện dưới group mong muốn không.
3. Kiểm tra method-level `group` có override group cấp lớp đúng không.
4. Kiểm tra mô tả command có đủ rõ để người dùng chọn đúng lệnh không.

**Kiểm tra đường dẫn thực thi:**

1. Đọc `@Command.name` trên từng phương thức.
2. Nếu có `@CommandGroup.prefix`, ghép prefix với tên command để suy ra đường dẫn đầy đủ.
3. Gọi trực tiếp từng đường dẫn trong terminal.
4. Thử các token cha riêng lẻ để xác nhận chúng có phải command được đăng ký độc lập hay chỉ là thành phần của path.
5. Kiểm tra alias nếu ứng dụng có khai báo.

`CommandRegistry` chứa tập command mà shell biết đến và cho phép đăng ký hoặc gỡ đăng ký command động. Khi debug, hãy kiểm tra tên command thực tế trong registry để xác nhận command đã được đăng ký. Group chỉ giúp tổ chức danh sách đó khi hiển thị.

## 11. Bài tập thực hành

Bạn đang xây dựng CLI cho hệ thống quản trị gồm người dùng, vai trò và báo cáo. Hãy thiết kế cả trợ giúp lẫn command path sao cho người dùng dễ khám phá và dễ gọi.

1. Tạo nhóm `User Management` với các command `user list`, `user show` và `user disable`.
2. Tạo nhóm `Role Management` với các command `role list`, `role grant` và `role revoke`.
3. Tạo nhóm `Reporting` với các command `report list` và `report export`.
4. Thử khai báo group bằng `@Command(group = ...)` trên từng method.
5. Chuyển các command của người dùng sang `@CommandGroup(name = ..., prefix = "user")`, rồi so sánh kết quả help và đường dẫn gọi.
6. Đổi group name từ `User Management` thành `Accounts` mà không đổi prefix. Ghi lại phần nào thay đổi và phần nào giữ nguyên.
7. Đổi prefix từ `user` thành `account` mà không đổi group name. Ghi lại đường dẫn mới.
8. Thử thêm method-level `group = "Diagnostics"` cho `user health` và xác minh prefix vẫn được áp dụng.
9. Chỉ đăng ký `user account show`; thử gọi `user` và `user account` để xác nhận token cha không tự trở thành command độc lập.
10. Viết một bảng đối chiếu group label, prefix, command name, command path và alias cho toàn bộ ứng dụng.

**Kết quả cần nộp:** mã nguồn các nhóm command, output `help`, danh sách đường dẫn command đã thử và bảng giải thích sự khác nhau giữa metadata trợ giúp và cú pháp thực thi.

## 12. Checklist thiết kế

- [ ] Mỗi command có `name` xác định rõ đường dẫn thực thi.
- [ ] Group được dùng để gom command theo chức năng trong trợ giúp.
- [ ] Không dùng tên group như một token của command path nếu chưa khai báo nó trong `name` hoặc `prefix`.
- [ ] Đã phân biệt `@CommandGroup.name` và `@CommandGroup.prefix`.
- [ ] Đã xác định method-level `group` có override group cấp lớp hay không.
- [ ] Prefix và tên command được kết hợp thành đường dẫn có nghĩa, không bị lặp token.
- [ ] Các token cha chỉ được xem là command độc lập khi có command tương ứng được đăng ký.
- [ ] Alias được khai báo riêng nếu cần tên gọi thay thế.
- [ ] Không dùng group để kiểm soát quyền hoặc availability.
- [ ] Đã kiểm tra `help` và gọi trực tiếp command path trong terminal.

## Tài liệu tham khảo

- [Spring Shell Reference Documentation — Organizing Commands](https://docs.spring.io/spring-shell/reference/commands/organize.html)
- [Spring Shell Reference Documentation — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell Reference Documentation — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell API — `@Command`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell API — `@CommandGroup`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html)
- [Spring Shell v4 Migration Guide — Command Grouping](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
