# Mô hình `@Command` và `@Option` trong Spring Shell 3.x

Spring Shell 3.x cung cấp mô hình annotation mới để biến các phương thức Java thành command của ứng dụng dòng lệnh. `@Command` xác định command và cách tổ chức tên lệnh; `@Option` mô tả những tham số có tên mà người dùng truyền vào khi gọi command. Khi kết hợp với Spring component model, hai annotation này giúp mã CLI gọn, dễ đọc và có thể tự tạo trợ giúp từ metadata khai báo.

Trong module `SPRING_SHELL`, mô hình này là nền tảng để khai báo command, xử lý đối số, kiểm tra dữ liệu đầu vào, cung cấp trợ giúp và tự hoàn thành. Bài học tập trung vào API `org.springframework.shell.command.annotation` của Spring Shell 3.x. Đây là API khác với bộ annotation legacy `@ShellComponent`, `@ShellMethod`, `@ShellOption` và cũng khác tên package, thuộc tính của API Spring Shell 4.x.

## 1. Vai trò của `@Command` và `@Option`

Một command thường có ba phần: tên thao tác, mô tả cho người dùng và các giá trị đầu vào. Trong mô hình annotation của Spring Shell 3.x, các phần này được khai báo như sau:

| Annotation | Vị trí sử dụng | Vai trò |
| --- | --- | --- |
| `@Command` | Trên lớp hoặc phương thức | Đánh dấu command target, đặt tên command, mô tả, nhóm và các metadata liên quan |
| `@Option` | Trên tham số phương thức | Định nghĩa tên option dài/ngắn, giá trị mặc định, tính bắt buộc và mô tả |
| `@Argument` | Trên tham số phương thức | Định nghĩa tham số theo vị trí trong dòng lệnh |

Ví dụ một lệnh tạo người dùng:

```text
user create --username linh --role editor
```

Trong đó `user create` là đường dẫn command; `--username` và `--role` là option. Spring Shell phân giải tên command trước, sau đó liên kết giá trị của option với các tham số phương thức tương ứng.

## 2. Đăng ký command target trong ứng dụng

Một lớp có annotation `@Command` cần được Spring quản lý như một bean. Đồng thời, ứng dụng phải bật cơ chế đăng ký command target. Trong Spring Boot, cách thường dùng là đặt `@CommandScan` trên lớp ứng dụng để quét các command trong package của lớp đó và những package con.

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.shell.command.annotation.CommandScan;

@SpringBootApplication
@CommandScan
public class CliApplication {

    public static void main(String[] args) {
        SpringApplication.run(CliApplication.class, args);
    }
}
```

Nếu muốn chỉ định rõ lớp command thay vì quét package, có thể dùng `@EnableCommand` trên một lớp cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.annotation.EnableCommand;

@Configuration
@EnableCommand(UserCommands.class)
public class ShellCommandConfiguration {
}
```

`@Command` đánh dấu lớp hoặc phương thức là ứng viên command; riêng annotation này không tự đăng ký mọi lớp command vào ứng dụng. `@CommandScan` hoặc `@EnableCommand` xác định những command target được đưa vào registry. Nếu quên bước đăng ký, ứng dụng vẫn có thể khởi động nhưng command không xuất hiện trong trợ giúp và không được gọi từ shell.

## 3. Khai báo command bằng `@Command`

`@Command` có thể được đặt trên phương thức để định nghĩa một command độc lập. Thuộc tính `command` nhận tên command; `description` cung cấp mô tả ngắn; `group` gom các command liên quan trong trợ giúp.

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class SystemCommands {

    @Command(
        command = "status",
        description = "Hiển thị trạng thái của ứng dụng.",
        group = "System"
    )
    public String status() {
        return "Ứng dụng đang hoạt động";
    }
}
```

Sau khi được đăng ký, người dùng gọi command:

```text
shell:> status
Ứng dụng đang hoạt động
```

Nếu phương thức trả về một giá trị, Spring Shell chuyển giá trị đó tới output của shell. Ví dụ trên trả về `String` để shell hiển thị. Với command cần in nhiều dòng hoặc định dạng phức tạp, có thể dùng các kiểu trả về và cơ chế output phù hợp với thiết kế ứng dụng.

### Đặt tiền tố chung ở cấp lớp

Annotation `@Command` cũng có thể đặt trên lớp để khai báo tiền tố chung và metadata mặc định cho những phương thức command bên trong. Khi lớp có `@Command(command = "user")` và phương thức có `@Command(command = "create")`, đường dẫn hoàn chỉnh là `user create`.

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
@Command(command = "user", group = "User Management")
public class UserCommands {

    @Command(command = "create", description = "Tạo người dùng mới.")
    public String create() {
        return "Đã tạo người dùng";
    }

    @Command(command = "list", description = "Liệt kê người dùng.")
    public String list() {
        return "Danh sách người dùng";
    }
}
```

Người dùng gọi hai command:

```text
shell:> user create
Đã tạo người dùng

shell:> user list
Danh sách người dùng
```

Khai báo ở cấp lớp còn có thể cung cấp `group`, `description`, `hidden`, `alias` và `interactionMode` làm metadata dùng chung. Giá trị đặt ở cấp phương thức có thể ghi đè metadata tương ứng khi API hỗ trợ kế thừa thuộc tính đó. Nhờ vậy, một lớp có thể gom command theo nghiệp vụ mà không phải lặp lại cùng cấu hình trên mọi phương thức.

## 4. Khai báo option bằng `@Option`

`@Option` được đặt trực tiếp trên tham số phương thức. Các thuộc tính thường dùng gồm:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `longNames` | `String[]` | Tên option dài, thường được gọi bằng tiền tố `--`; phần tử đầu là tên chính, các phần tử sau là bí danh |
| `shortNames` | `char[]` | Tên option ngắn, thường được gọi bằng một dấu gạch ngang; phần tử đầu là tên chính |
| `required` | `boolean` | Đánh dấu option bắt buộc; mặc định là `false` |
| `defaultValue` | `String` | Giá trị mặc định khi người dùng không truyền option |
| `description` | `String` | Mô tả option trong trợ giúp |
| `label` | `String` | Nhãn gợi ý cho giá trị option trong phần trợ giúp |
| `arity`, `arityMin`, `arityMax` | Enum hoặc `int` | Điều khiển số lượng giá trị mà một option có thể nhận |

Ví dụ:

```java
@Command(command = "create", description = "Tạo người dùng mới.")
public String create(
        @Option(
            longNames = {"username", "user"},
            shortNames = 'u',
            required = true,
            description = "Tên đăng nhập"
        ) String username,
        @Option(
            longNames = "role",
            shortNames = 'r',
            defaultValue = "viewer",
            description = "Vai trò của người dùng"
        ) String role) {
    return "Đã tạo " + username + " với vai trò " + role;
}
```

Với command trên, những cách gọi sau tương đương về mặt ý nghĩa:

```text
create --username linh --role editor
create --user linh --role editor
create -u linh -r editor
create --username linh
```

Lệnh cuối bỏ qua `--role`, nên phương thức nhận giá trị mặc định `viewer`. Option `username` là bắt buộc; nếu không truyền, shell báo lỗi phân tích đầu vào và không gọi command với một tên người dùng hợp lệ giả định.

Tên option dài không cần chứa dấu gạch ngang trong giá trị annotation. Ví dụ `longNames = "username"` tạo cú pháp `--username`; `shortNames = 'u'` tạo cú pháp `-u`. Nếu khai báo nhiều tên, phần tử đầu tiên là tên chính và những phần tử còn lại là bí danh.

## 5. Ghép `@Command` và `@Option` trong một ví dụ hoàn chỉnh

Ví dụ dưới đây tổ chức command theo nhóm `user`, sử dụng option bắt buộc, option có giá trị mặc định và một option boolean. Lớp được đánh dấu `@Validated` để các ràng buộc Bean Validation trên tham số có thể được áp dụng khi method validation đã được cấu hình trong ứng dụng.

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;
import org.springframework.validation.annotation.Validated;

@Component
@Validated
@Command(command = "user", group = "User Management")
public class UserCommands {

    @Command(command = "create", description = "Tạo người dùng mới.")
    public String create(
            @Option(
                longNames = "username",
                shortNames = 'u',
                required = true,
                description = "Tên đăng nhập"
            ) @NotBlank String username,
            @Option(
                longNames = "role",
                shortNames = 'r',
                defaultValue = "viewer",
                description = "Vai trò người dùng"
            ) String role,
            @Option(
                longNames = "enabled",
                defaultValue = "false",
                description = "Đánh dấu tài khoản được kích hoạt"
            ) boolean enabled) {

        return "username=" + username
                + ", role=" + role
                + ", enabled=" + enabled;
    }

    @Command(command = "find", description = "Tìm người dùng theo mã.")
    public String find(
            @Option(
                longNames = "id",
                shortNames = 'i',
                required = true,
                description = "Mã người dùng"
            ) @Positive long id) {

        return "Đang tìm người dùng có mã " + id;
    }
}
```

Ví dụ lời gọi:

```text
shell:> user create --username linh --role editor --enabled
username=linh, role=editor, enabled=true

shell:> user create -u minh
username=minh, role=viewer, enabled=false

shell:> user find --id 42
Đang tìm người dùng có mã 42
```

`@Command(command = "user")` ở cấp lớp tạo tiền tố cho hai phương thức. `@Command(command = "create")` và `@Command(command = "find")` xác định phần cuối của đường dẫn. `@Option` ánh xạ từng option vào tham số tương ứng; `@NotBlank` và `@Positive` diễn tả các điều kiện hợp lệ ở mức dữ liệu.

Để dùng các constraint Jakarta Validation trong ứng dụng Spring Boot, cần có implementation Bean Validation trên classpath, thường được thêm bằng dependency `spring-boot-starter-validation`. `@Validated` bật method validation cho bean theo cơ chế Spring. Các constraint giúp phát hiện đầu vào sai trước khi logic nghiệp vụ tiếp tục; thông báo lỗi nên đủ rõ để người dùng biết phải sửa option nào.

Option boolean có thể được dùng như một cờ. Khi người dùng chỉ truyền `--enabled`, giá trị boolean được bật; nếu bỏ qua option, `defaultValue = "false"` được sử dụng. Với các kiểu tham số khác, option thường cần giá trị đi kèm, ví dụ `--username linh` hoặc `--id 42`.

## 6. `@Option` và tham số theo vị trí

Option có tên và argument theo vị trí phục vụ hai kiểu cú pháp khác nhau:

- Option có tên được nhận diện qua `longNames` hoặc `shortNames`, ví dụ `--id 42` hay `-i 42`.
- Argument được nhận diện theo vị trí trong dòng lệnh, ví dụ `user show 42`.

Trong mô hình annotation 3.x, tham số theo vị trí có thể được khai báo bằng `@Argument`. Khi một command có nhiều tham số, option có tên thường dễ đọc và ít phụ thuộc thứ tự hơn. Argument phù hợp với giá trị ngắn, tự nhiên và có thứ tự ổn định, như tên tệp hoặc mã đối tượng.

```java
import org.springframework.shell.command.annotation.Argument;
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;

@Command(command = "show")
public String show(
        @Argument(index = 0, description = "Mã người dùng") long id,
        @Option(longNames = "details", defaultValue = "false") boolean details) {
    return details ? "Chi tiết người dùng " + id : "Người dùng " + id;
}
```

Lời gọi `show 42 --details` truyền `42` vào argument vị trí đầu tiên và bật option `details`. Không nên dùng `@Option` để mô tả một giá trị theo vị trí, hoặc dùng `@Argument` khi cú pháp cần tên option rõ ràng.

## 7. Giá trị mặc định, tính bắt buộc và kiểu dữ liệu

`required` và `defaultValue` giải quyết hai nhu cầu khác nhau. `required = true` yêu cầu người dùng truyền option; `defaultValue` cung cấp giá trị thay thế khi option bị bỏ qua. Khi một option không bắt buộc và không có giá trị mặc định, kiểu dữ liệu tham số ảnh hưởng tới cách biểu diễn trạng thái thiếu.

| Khai báo | Hành vi khi bỏ qua option |
| --- | --- |
| `@Option(required = true) String name` | Shell yêu cầu người dùng cung cấp giá trị |
| `@Option(defaultValue = "viewer") String role` | Tham số nhận chuỗi `viewer` |
| `@Option String note` | Tham số có thể không có giá trị; dùng kiểu tham chiếu nếu cần biểu diễn `null` |
| `@Option(defaultValue = "false") boolean enabled` | Tham số nhận `false` |

Giá trị của `defaultValue` được khai báo dưới dạng chuỗi và được chuyển đổi sang kiểu tham số. Vì vậy, `defaultValue = "42"` có thể dùng cho một tham số số; giá trị mặc định phải chuyển đổi được sang kiểu đã khai báo.

Spring Shell hỗ trợ các kiểu cơ bản như `String`, boolean, số, enum và mảng. Khi dùng enum, giá trị nhập phải tương ứng với một hằng số enum được khai báo. Với danh sách hoặc nhiều giá trị, hãy xác định rõ arity để người dùng biết một option nhận một hay nhiều giá trị. Nếu trạng thái “không truyền” khác với `false`, hãy cân nhắc dùng `Boolean` thay cho `boolean` để có thể phân biệt giá trị thiếu với giá trị false.

## 8. Metadata của command và trợ giúp

`@Command` không chỉ đăng ký tên lệnh. Các metadata của nó còn giúp shell tổ chức danh sách command và mô tả cách sử dụng:

- `description`: mô tả ngắn xuất hiện trong danh sách command.
- `group`: gom command theo chức năng trong trợ giúp.
- `alias`: khai báo tên thay thế cho command.
- `hidden`: ẩn command khỏi danh sách trợ giúp thông thường khi cần giữ một thao tác nội bộ.
- `interactionMode`: gợi ý chế độ tương tác mà command phù hợp, chẳng hạn chỉ dùng trong phiên tương tác hoặc chế độ không tương tác.

`@Option(description = "...")` bổ sung mô tả cho từng giá trị đầu vào. Hãy viết mô tả theo hướng giải thích mục đích của option, đơn vị hoặc định dạng giá trị cần truyền. Tên option tốt kết hợp với mô tả rõ ràng giúp người dùng hiểu command qua `help` mà không cần mở mã nguồn.

Ví dụ một command có bí danh và mô tả đầy đủ:

```java
@Command(
    command = "list",
    alias = "ls",
    description = "Liệt kê người dùng.",
    group = "User Management"
)
public String list(
        @Option(longNames = "active-only", description = "Chỉ hiển thị tài khoản đang hoạt động")
        boolean activeOnly) {
    return activeOnly ? "Danh sách tài khoản đang hoạt động" : "Tất cả người dùng";
}
```

Nếu phương thức này nằm trong lớp có tiền tố `@Command(command = "user")`, người dùng gọi command chính bằng `user list` và bí danh bằng `user ls`. Nên thử `help` sau khi đăng ký để xác nhận tên, bí danh, nhóm và mô tả hiển thị như dự kiến.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Command không xuất hiện trong `help` | Lớp chưa là Spring bean hoặc chưa được `@CommandScan`/`@EnableCommand` đăng ký | Kiểm tra component scan và cấu hình đăng ký command target |
| Command có tên sai | Ghép tiền tố cấp lớp với tên phương thức không đúng | Kiểm tra `command` ở cả cấp lớp và cấp phương thức |
| Không nhận ra `--username` | `longNames` không khớp tên option người dùng nhập | Dùng đúng tên đã khai báo; nhớ rằng `longNames` không chứa tiền tố `--` |
| `-u` không hoạt động | Chưa khai báo `shortNames = 'u'` hoặc nhập sai ký tự | Kiểm tra short name và gọi bằng `-u` |
| Thiếu option nhưng command vẫn chạy | Option chưa được đánh dấu `required = true` | Đánh dấu bắt buộc hoặc đặt default phù hợp với nghiệp vụ |
| Giá trị mặc định không chuyển đổi được | `defaultValue` không phù hợp kiểu tham số | Sửa giá trị mặc định hoặc kiểu dữ liệu |
| Constraint không được áp dụng | Thiếu validation provider hoặc bean chưa bật method validation | Thêm implementation Bean Validation và cấu hình `@Validated` đúng cách |
| Command không được nhóm đúng trong trợ giúp | `group` chưa khai báo hoặc bị ghi đè ở cấp phương thức | Kiểm tra metadata ở cả lớp và phương thức |

Khi kiểm tra một command, hãy thử tối thiểu các trường hợp: gọi đủ option hợp lệ; bỏ option bắt buộc; bỏ option có giá trị mặc định; truyền giá trị sai kiểu; truyền giá trị vi phạm constraint; và gọi bằng bí danh hoặc short name. Những trường hợp này xác nhận cả bước phân giải command lẫn bước liên kết và kiểm tra tham số.

## 10. Lưu ý tương thích giữa các thế hệ Spring Shell

Spring Shell 3.x có hai mô hình annotation có thể gặp trong dự án:

| Mô hình | Annotation tiêu biểu | Đặc điểm |
| --- | --- | --- |
| Annotation mới | `@Command`, `@Option`, `@Argument` trong `org.springframework.shell.command.annotation` | Có thể đặt `@Command` ở cấp lớp để tạo tiền tố; dùng `longNames` và `shortNames` cho option |
| Annotation legacy | `@ShellComponent`, `@ShellMethod`, `@ShellOption` trong `org.springframework.shell.standard` | Mô hình cũ với `key`, `value` và cách khai báo option riêng |

Không trộn annotation legacy với annotation mới trong cùng một command class nếu chưa có chủ đích chuyển đổi rõ ràng. Khi đọc ví dụ trên Internet, hãy kiểm tra phiên bản tài liệu vì Spring Shell 4.x tiếp tục thay đổi package và tên thuộc tính; ví dụ 4.x có thể dùng `name`, `longName`, `shortName` thay cho API `command`, `longNames`, `shortNames` của 3.x.

## 11. Checklist khi khai báo command

- Lớp command là Spring bean và được đăng ký bằng `@CommandScan` hoặc `@EnableCommand`.
- `@Command` ở cấp lớp và cấp phương thức ghép thành đường dẫn đúng.
- Mỗi command có mô tả ngắn và group phù hợp để trợ giúp dễ đọc.
- `@Option` dùng đúng `longNames` và `shortNames`; bí danh không gây trùng lặp.
- Option bắt buộc, tùy chọn và giá trị mặc định phản ánh đúng yêu cầu nghiệp vụ.
- Kiểu tham số và `defaultValue` tương thích; constraint được kích hoạt khi cần.
- Command được thử với dữ liệu hợp lệ, thiếu option, sai kiểu và sai ràng buộc.
- Ví dụ và hướng dẫn sử dụng khớp với đúng phiên bản Spring Shell 3.x của dự án.

## Tài liệu tham khảo

- [Spring Shell 3.2 — Annotation-Based Command Registration](https://docs.spring.io/spring-shell/reference/3.2/commands/registration/annotation.html)
- [Spring Shell 3.4 — `@Command` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Command.html)
- [Spring Shell 3.4 — `@Option` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Option.html)
- [Spring Shell 3.4 — Short Option Format](https://docs.spring.io/spring-shell/reference/3.4/options/short.html)
- [Spring Shell 3.4 — Default Option Value](https://docs.spring.io/spring-shell/reference/3.4/options/default.html)
- [Spring Shell 3.4 — Optional Option Value](https://docs.spring.io/spring-shell/reference/3.4/options/optional.html)
