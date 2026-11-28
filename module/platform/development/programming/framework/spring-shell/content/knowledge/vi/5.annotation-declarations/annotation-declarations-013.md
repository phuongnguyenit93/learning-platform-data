# Phạm vi sử dụng của annotation cũ khi nâng lên Spring Shell 4.x

Khi nâng một ứng dụng Spring Shell từ 3.x lên 4.x, các annotation legacy như `@ShellComponent`, `@ShellMethod` và `@ShellOption` không còn được hỗ trợ. Chúng đã bị deprecated trong dòng 3.x và bị loại bỏ trong 4.x. Vì vậy, mã nguồn còn import các annotation này phải được chuyển đổi trước khi biên dịch với Spring Shell 4.

Điểm cần phân biệt là Spring Shell 3.x có hai thế hệ API annotation. Bộ annotation legacy nằm trong `org.springframework.shell.standard`; mô hình mới `@Command`, `@Option`, `@Argument` nằm trong `org.springframework.shell.command.annotation`. Khi sang 4.x, mô hình mới tiếp tục được dùng nhưng package và một số thuộc tính thay đổi. Bài học này xác định phạm vi còn dùng được của annotation cũ, chỉ ra phần nào bị loại bỏ và hướng dẫn chuyển đổi theo từng lớp API.

## 1. Annotation legacy còn dùng được trong phiên bản nào?

Bộ annotation legacy được dùng rộng rãi trong các ứng dụng Spring Shell trước khi mô hình command mới xuất hiện. Trong Spring Shell 3.x, bộ này vẫn tồn tại để hỗ trợ chuyển tiếp nhưng đã bị deprecated. Từ Spring Shell 4.x, các annotation legacy và những API liên quan đã bị xóa khỏi framework.

| Thế hệ Spring Shell | Trạng thái của annotation legacy | Cách hiểu khi bảo trì ứng dụng |
| --- | --- | --- |
| 2.x | Là mô hình annotation quen thuộc để khai báo command | Dự án có thể vẫn dùng `@ShellComponent`, `@ShellMethod`, `@ShellOption` |
| 3.x | Vẫn tồn tại nhưng đã deprecated; framework giới thiệu mô hình `@Command`, `@Option`, `@Argument` mới | Có thể giữ mã legacy trong giai đoạn chuyển tiếp, nhưng nên lên kế hoạch thay thế trước khi nâng major version |
| 4.x | Annotation legacy và API liên quan đã bị loại bỏ | Mã còn import annotation legacy sẽ không biên dịch với API 4.x; phải chuyển sang mô hình mới |

Những annotation legacy thường gặp gồm:

- `@ShellComponent`: đánh dấu lớp chứa các phương thức command. Trong 3.x, annotation này đồng thời là một Spring stereotype dựa trên `@Component`.
- `@ShellMethod`: đánh dấu phương thức có thể được gọi từ shell; `value` mô tả command và `key` xác định tên gọi hoặc bí danh.
- `@ShellOption`: định nghĩa tên option, giá trị mặc định và cách liên kết tham số của phương thức.
- Các annotation và API phụ trợ đi cùng mô hình legacy, chẳng hạn những cơ chế tùy biến trợ giúp, khả năng command hoặc xử lý tham số.

Trong 4.x, không có chế độ tương thích để bật lại bộ annotation legacy bằng một thuộc tính cấu hình. Nếu cần duy trì một nhánh ứng dụng chạy trên 3.x, hãy giữ nhánh đó dùng đúng dependency 3.x; mã được biên dịch cho 4.x phải sử dụng API mới.

## 2. Phân biệt hai mô hình annotation trong Spring Shell 3.x

Việc phân biệt hai mô hình trong 3.x rất quan trọng vì không phải mọi thay đổi đều là đổi tên annotation.

| Mô hình | Package trong Spring Shell 3.x | Annotation chính | Trạng thái trong 4.x |
| --- | --- | --- | --- |
| Legacy | `org.springframework.shell.standard` | `@ShellComponent`, `@ShellMethod`, `@ShellOption` | Bị loại bỏ |
| Annotation mới | `org.springframework.shell.command.annotation` | `@Command`, `@Option`, `@Argument` | Được tiếp tục sử dụng sau khi chuyển package và điều chỉnh API |

Ví dụ, một dự án 3.x có thể chứa đồng thời lớp dùng `@ShellComponent`/`@ShellMethod` và lớp dùng `@Command`/`@Option`. Khi nâng lên 4.x, chỉ các lớp dùng mô hình mới là nền tảng thuận lợi để chuyển tiếp; các lớp legacy vẫn phải được viết lại.

Mô hình mới trong 3.x cũng có một số cách khai báo không còn hợp lệ ở 4.x. Ví dụ, `@Command` từng có thể được đặt trên lớp để khai báo tiền tố và nhóm; trong 4.x, `@Command` chỉ đánh dấu phương thức. Vì vậy, chỉ thay package import mà giữ nguyên cách dùng annotation cấp lớp sẽ không đủ để hoàn thành việc nâng cấp.

## 3. Thay thế các annotation legacy

Bảng sau tóm tắt cách chuyển từ bộ legacy sang API 4.x. Đây là bản đồ chuyển đổi theo ý nghĩa; không phải mọi thuộc tính cũ đều có thuộc tính mới tương ứng một-một.

| API legacy | Vai trò cũ | Cách biểu diễn trong Spring Shell 4.x |
| --- | --- | --- |
| `@ShellComponent` | Đánh dấu bean chứa command | Dùng `@Component`, `@Service` hoặc Spring stereotype phù hợp trên lớp chứa phương thức command |
| `@ShellMethod(value = ..., key = ...)` | Đăng ký phương thức, mô tả và tên command | Dùng `@Command(name = ..., description = ...)` trên phương thức |
| `@ShellOption(value = "--name")` | Khai báo option dài | Dùng `@Option(longName = "name")` trên tham số |
| `@ShellOption(value = "-n")` | Khai báo option ngắn | Dùng `@Option(shortName = 'n')` |
| `@ShellOption(defaultValue = ...)` | Giá trị mặc định | Dùng `@Option(defaultValue = ...)`, đồng thời kiểm tra lại hành vi khi không truyền giá trị |
| `@ShellMethod(group = ...)` | Gom command trong trợ giúp | Dùng `group` trên `@Command`; nếu cần tiền tố và nhóm chung cho cả lớp, dùng `@CommandGroup` |
| Tham số được suy ra theo tên trong legacy | Liên kết đối số theo quy ước cũ | Khai báo rõ bằng `@Argument` hoặc `@Option` tùy cú pháp command |

### Ví dụ trước khi nâng cấp

Đoạn mã dưới đây minh họa mô hình legacy trong một ứng dụng Spring Shell 3.x:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class UserCommands {

    @ShellMethod(
        value = "Tạo người dùng mới.",
        key = "user create"
    )
    public String create(
            @ShellOption(value = "--username") String username,
            @ShellOption(value = "--role", defaultValue = "viewer") String role) {
        return "Đã tạo " + username + " với vai trò " + role;
    }
}
```

Trong ví dụ này, `@ShellComponent` làm lớp trở thành bean được Spring quản lý; `@ShellMethod` đăng ký command `user create`; `@ShellOption` liên kết hai option với tham số `username` và `role`.

### Ví dụ sau khi nâng lên Spring Shell 4.x

Trong 4.x, command được khai báo trên phương thức của một Spring bean. `@Command` dùng `name` để mô tả đường dẫn command, còn `@Option` dùng `longName` hoặc `shortName` để định nghĩa option.

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class UserCommands {

    @Command(
        name = {"user", "create"},
        description = "Tạo người dùng mới."
    )
    public String create(
            @Option(longName = "username", required = true) String username,
            @Option(longName = "role", defaultValue = "viewer") String role) {
        return "Đã tạo " + username + " với vai trò " + role;
    }
}
```

Người dùng vẫn gọi command theo đường dẫn quen thuộc:

```text
shell:> user create --username linh --role editor
Đã tạo linh với vai trò editor
```

Trong API 4.x, `name` là mảng các thành phần của đường dẫn command. Ví dụ `{"user", "create"}` biểu diễn hai thành phần `user` và `create`. Thuộc tính `alias` của `@Command` dùng để khai báo tên thay thế cho command. Không nên chuyển một mảng `key` legacy vốn dùng làm nhiều bí danh thành `name` một cách máy móc, vì `name` biểu diễn đường dẫn còn `alias` biểu diễn bí danh.

## 4. Thay đổi package và cấu trúc của `@Command`

Khi chuyển mô hình annotation mới từ 3.x sang 4.x, cần cập nhật import và cách tổ chức lớp:

| Thành phần | Spring Shell 3.x | Spring Shell 4.x |
| --- | --- | --- |
| Package annotation mới | `org.springframework.shell.command.annotation` | `org.springframework.shell.core.command.annotation` |
| Tên command | `@Command(command = ...)` | `@Command(name = ...)` |
| Vị trí `@Command` | Có thể dùng trên lớp và phương thức | Chỉ dùng trên phương thức |
| Nhóm và tiền tố chung | Có thể khai báo bằng `@Command` cấp lớp | Dùng `@CommandGroup(prefix = ..., name = ...)` |
| Đăng ký trong Spring Boot | Thường dùng `@CommandScan` hoặc `@EnableCommand` | Command scanning được tự động bật bởi Spring Boot; `@CommandScan` đã bị loại bỏ |

Ví dụ cách khai báo nhóm command trong Spring Shell 4.x:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(
    prefix = "user",
    name = "User Management"
)
public class UserCommands {

    @Command(name = "create", description = "Tạo người dùng mới.")
    public String create() {
        return "Đã tạo người dùng";
    }

    @Command(name = "list", description = "Liệt kê người dùng.")
    public String list() {
        return "Danh sách người dùng";
    }
}
```

`@CommandGroup` cung cấp tiền tố `user` cho các command trong lớp và tên nhóm dùng trong trợ giúp. Annotation này được giới thiệu từ Spring Shell 4.0.2; nếu dự án đang ở 4.0.0 hoặc 4.0.1, hãy dùng tên command đầy đủ ngay trên từng phương thức, ví dụ `@Command(name = {"user", "create"})`, hoặc nâng lên phiên bản có `@CommandGroup`.

Với ứng dụng Spring Boot 4, command scanning được tự động cấu hình; không thêm lại `@CommandScan` từ mã 3.x. Với ứng dụng Spring thuần không dùng Boot, vẫn cần bật đăng ký command bằng `@EnableCommand` và chỉ định cấu hình hoặc command target theo API 4.x.

## 5. Thay đổi cách khai báo option

Trong mô hình annotation mới của 3.x, `@Option` cho phép khai báo nhiều tên dài và nhiều tên ngắn qua `longNames` và `shortNames`. Trong 4.x, `@Option` chỉ có một `longName` và một `shortName`; thuộc tính `label` cũng đã bị loại bỏ.

| Spring Shell 3.x | Spring Shell 4.x | Lưu ý |
| --- | --- | --- |
| `longNames = {"username", "user"}` | `longName = "username"` | Chọn một tên dài chính; tên thay thế cần được xem xét như thay đổi cú pháp CLI |
| `shortNames = {'u', 'U'}` | `shortName = 'u'` | Chỉ còn một tên ngắn |
| `required = true` | `required = true` | Ý nghĩa vẫn là option bắt buộc |
| `defaultValue = "viewer"` | `defaultValue = "viewer"` | Kiểm tra giá trị mặc định có chuyển đổi được sang kiểu tham số |
| `label = "User name"` | Không còn thuộc tính `label` | Đưa thông tin cần thiết vào `description` hoặc `help` của command |

Ví dụ option 4.x:

```java
@Command(name = "user-create", description = "Tạo người dùng.")
public String create(
        @Option(
            longName = "username",
            shortName = 'u',
            required = true,
            description = "Tên đăng nhập"
        ) String username) {
    return "Đã tạo " + username;
}
```

Đối với các command đã phát hành, việc bỏ bí danh option có thể ảnh hưởng script và tài liệu của người dùng. Hãy thống kê những cú pháp cũ đang được sử dụng, chọn một tên chính trong 4.x và cập nhật đồng bộ script, hướng dẫn, ví dụ cũng như kiểm thử. Nếu cần giữ nhiều cách gọi, có thể cân nhắc bí danh ở cấp command khi phù hợp; bí danh command không thay thế được bí danh của từng option.

Spring Shell 4 cũng yêu cầu option luôn có một giá trị, kể cả option boolean. Vì vậy, cách viết cờ đơn như `--enabled` không còn mang ý nghĩa tự động bật boolean như một số CLI khác. Hãy truyền giá trị rõ ràng theo cú pháp 4.x, ví dụ `--enabled=true`. Các short option cũng không thể gộp thành một cụm như `-abc`; hãy truyền từng option theo cú pháp được hỗ trợ.

## 6. Những annotation và hook phụ trợ cũng cần chuyển đổi

Nâng cấp không chỉ là đổi `@ShellMethod` thành `@Command`. Một số khả năng trước đây được cấu hình qua nhiều annotation hoặc extension point đã được tổ chức lại trong 4.x.

| API hoặc cách làm ở 3.x | Thay đổi trong 4.x | Hướng chuyển đổi |
| --- | --- | --- |
| `@CommandAvailability` hoặc cơ chế availability riêng | Metadata availability được đưa vào `@Command` | Dùng `@Command(availabilityProvider = "...")` và bean `AvailabilityProvider` |
| `@OptionValues` và completer riêng cho từng option | `@OptionValues` bị loại bỏ; completion được tổ chức ở cấp command | Dùng `@Command(completionProvider = "...")` với bean `CompletionProvider` |
| Nhiều annotation tùy biến command | Các cấu hình command được gom vào `@Command` | Rà soát availability, completion, help và exception mapping rồi chuyển vào thuộc tính phù hợp |
| `CommandExceptionResolver` / `CommandHandlingResult` | Mô hình exception và exit code được đơn giản hóa | Dùng `ExitStatusExceptionMapper` và `@Command(exitStatusExceptionMapper = "...")` khi cần ánh xạ exception |
| `InteractionMode` | Enum đã bị loại bỏ; command không còn đánh dấu riêng interactive/non-interactive | Chọn chế độ shell khi khởi động; command được thực thi trong chế độ đã chọn |

Ví dụ chuyển availability:

```java
@Command(
    name = "download",
    availabilityProvider = "downloadAvailability"
)
public void download() {
    // Tải dữ liệu sau khi đã kết nối.
}

@Bean
AvailabilityProvider downloadAvailability() {
    return () -> connected
            ? Availability.available()
            : Availability.unavailable("you are not connected");
}
```

Ví dụ chuyển completion:

```java
@Command(
    name = "hello",
    completionProvider = "helloCompletionProvider"
)
public void hello(@Option(longName = "name") String name) {
    System.out.println("Hello " + name);
}

@Bean
CompletionProvider helloCompletionProvider() {
    return context -> List.of();
}
```

Phần thân provider trong ví dụ là điểm mở rộng để bổ sung đề xuất phù hợp với trạng thái và nội dung đang nhập. Khi chuyển completer cũ, hãy xem lại logic ở cấp command vì provider mới có thể xem xét ngữ cảnh của nhiều option cùng lúc.

## 7. Các thay đổi nền tảng có ảnh hưởng tới bước nâng cấp

Spring Shell 4 dựa trên Spring Framework 7; hỗ trợ Spring Boot yêu cầu Spring Boot 4 trở lên. Vì vậy, một ứng dụng chỉ nâng version Spring Shell nhưng vẫn giữ nguyên nền tảng Boot 3 sẽ không đáp ứng yêu cầu tương thích của dòng 4.x.

Một số thay đổi dependency đáng chú ý:

- `spring-shell-core` không còn phụ thuộc Spring Boot. Ứng dụng Boot cần thêm `spring-shell-core-autoconfigure` hoặc một Spring Shell starter phù hợp.
- `spring-shell-core` không còn phụ thuộc JLine. Nếu cần shell dựa trên JLine, hãy thêm `spring-shell-jline` hoặc dùng starter cấu hình sẵn runner tương ứng.
- Các module `spring-shell-standard` và `spring-shell-standard-commands` đã được hợp nhất vào `spring-shell-core`.
- Module `spring-shell-autoconfigure` được đổi tên thành `spring-shell-core-autoconfigure`.
- Module `spring-shell-table` được hợp nhất vào `spring-shell-jline`.

Các thay đổi này không phải annotation, nhưng có thể khiến build thất bại ngay cả khi đã chuyển xong mã command. Hãy cập nhật dependency và kiểm tra import của những API liên quan trước khi đánh giá lỗi biên dịch.

## 8. Lộ trình chuyển đổi an toàn

Nên chia quá trình nâng cấp thành những bước nhỏ để xác định rõ lỗi do annotation hay do nền tảng:

1. **Ổn định ứng dụng trên 3.x:** nâng lên bản Spring Shell 3.4.x mới nhất trước khi chuyển major version, như hướng dẫn migration chính thức khuyến nghị.
2. **Kiểm kê annotation:** tìm toàn bộ import `org.springframework.shell.standard` và ghi lại nơi dùng `@ShellComponent`, `@ShellMethod`, `@ShellOption` cùng annotation phụ trợ.
3. **Phân loại command:** xác định command key, bí danh, group, option, argument, default, availability, completion và cách xử lý exception đang dùng.
4. **Chuyển command class:** thay `@ShellComponent` bằng Spring stereotype phù hợp; thay `@ShellMethod` bằng `@Command`; thay `@ShellOption` bằng `@Option` hoặc `@Argument` theo cú pháp thực tế.
5. **Chuyển nhóm và tiền tố:** thay cách dùng `@Command` cấp lớp trong 3.x bằng `@CommandGroup` ở phiên bản 4.x có hỗ trợ, hoặc khai báo tên command đầy đủ trên từng phương thức.
6. **Cập nhật cấu hình và dependency:** nâng Spring Boot lên 4+, cập nhật module Spring Shell, xóa `@CommandScan` khỏi cấu hình Boot và giữ `@EnableCommand` nếu ứng dụng không dùng Boot.
7. **Kiểm tra hành vi CLI:** chạy các command bằng tên chính và alias, thử option bắt buộc, giá trị mặc định, boolean, argument, quoting, help, completion, availability và exit code.
8. **Cập nhật script và tài liệu:** sửa mọi cú pháp cũ bị thay đổi, đặc biệt tên option, short option gộp và command alias.

Nếu một tổ chức phải duy trì đồng thời bản phát hành 3.x và 4.x, hãy cân nhắc tách lớp command adapter theo từng phiên bản vào module hoặc source set riêng. Phần nghiệp vụ như service, repository và mô hình dữ liệu có thể được dùng chung; mỗi adapter chịu trách nhiệm ánh xạ cú pháp CLI sang cùng service. Cách này tránh để mã nguồn chung phụ thuộc vào annotation chỉ tồn tại ở một major version.

## 9. Lỗi thường gặp khi nâng cấp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy `ShellComponent` hoặc `ShellMethod` khi biên dịch | Legacy annotation đã bị xóa trong 4.x | Chuyển lớp sang `@Component` và phương thức sang `@Command` |
| Không tìm thấy `org.springframework.shell.command.annotation` | Package của API annotation mới đã thay đổi | Dùng `org.springframework.shell.core.command.annotation` |
| Không biên dịch `@Command(command = ...)` | Thuộc tính `command` đã đổi thành `name` | Đổi sang `name`, biểu diễn đường dẫn bằng các phần tử mảng |
| `@Command` trên lớp bị báo lỗi | 4.x chỉ cho phép `@Command` trên phương thức | Dùng `@CommandGroup` hoặc khai báo đường dẫn đầy đủ ở method |
| Không tìm thấy `@CommandScan` trong Boot | Boot 4 tự động bật command scanning; annotation này đã bị loại bỏ | Xóa `@CommandScan`; với ứng dụng non-Boot, dùng `@EnableCommand` |
| Không biên dịch `longNames` hoặc `shortNames` | 4.x đổi thành tên đơn `longName` và `shortName` | Chọn một tên dài và một tên ngắn cho mỗi option |
| Không còn `label` hoặc `@OptionValues` | Metadata label và option-level completion đã bị loại bỏ | Đưa mô tả vào `description`/`help`, dùng `CompletionProvider` cấp command |
| Script boolean không còn chạy | Parser 4.x yêu cầu option có giá trị | Truyền tường minh `--enabled=true` hoặc `--enabled=false` |
| Lỗi dependency Spring Boot hoặc JLine | Nền tảng và cách chia module đã thay đổi | Nâng Boot lên 4+, thêm starter/autoconfigure và JLine khi cần |

## 10. Checklist xác nhận phạm vi annotation sau nâng cấp

- Không còn import `org.springframework.shell.standard` trong các lớp command 4.x.
- Mọi command được khai báo bằng `@Command` trên phương thức của Spring bean.
- Mọi option dùng `longName` hoặc `shortName` đơn; không còn `longNames`, `shortNames` hay `label`.
- Tham số theo vị trí được khai báo rõ bằng `@Argument` hoặc `@Arguments`.
- Nhóm và tiền tố ở cấp lớp dùng `@CommandGroup` khi phiên bản hỗ trợ.
- Availability, completion và exception mapping dùng provider mới.
- Cấu hình đăng ký command phù hợp: Boot tự scan; ứng dụng non-Boot bật `@EnableCommand`.
- Các script và tài liệu gọi CLI đã được cập nhật theo parser 4.x.
- Build và kiểm thử xác nhận command hoạt động với đúng Spring Boot/Spring Framework tương thích.

## Tài liệu tham khảo

- [Spring Shell — v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell 3.3 — Legacy Annotation](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/legacyannotation.html)
- [Spring Shell 4.0.3 — Command API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell 4.0.3 — Option API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html)
- [Spring Shell 4.0.3 — CommandGroup API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html)
- [Spring Shell 4.0.3 — Organizing Commands](https://docs.spring.io/spring-shell/reference/commands/organize.html)
- [Spring Shell 4.0.3 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
