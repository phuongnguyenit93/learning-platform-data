# Đổi package và thuộc tính `@Command` từ Spring Shell 3.x sang 4.x

Spring Shell 4 thay đổi command annotation model và cách framework phát hiện command. Khi nâng cấp từ 3.x, việc sửa tên import thường chưa đủ: `@Command.command` đổi thành `name`, annotation `@Command` không còn đặt trên class, nhóm command chuyển sang `@CommandGroup`, và các thuộc tính của `@Option` được đơn giản hóa.

Một dự án 3.x có thể đang dùng một trong hai mô hình: annotation cũ `@ShellComponent`/`@ShellMethod`/`@ShellOption`, hoặc annotation model mới `@Command`/`@Option` được giới thiệu trong dòng 3.x. Hai đường nâng cấp có điểm xuất phát khác nhau. Bài viết tách riêng hai trường hợp để tránh thay import máy móc rồi gặp lỗi compile hoặc command không còn được đăng ký.

## 1. Chọn đúng phiên bản nguồn trước khi nâng cấp

Spring Shell 3.x có cả API legacy và API annotation model mới:

| Phiên bản/mô hình | Annotation thường gặp | Package chính |
|---|---|---|
| 3.3 legacy | `@ShellComponent`, `@ShellMethod`, `@ShellOption` | `org.springframework.shell.standard` |
| 3.3/3.4 annotation model mới | `@Command`, `@Option`, `@Argument`, `@EnableCommand` | `org.springframework.shell.command.annotation` |
| 4.x | `@Command`, `@Option`, `@Argument`, `@Arguments`, `@CommandGroup`, `@EnableCommand` | `org.springframework.shell.core.command.annotation` |

Hướng dẫn migration chính thức khuyến nghị nâng dự án lên phiên bản Spring Shell 3.4.x mới nhất trước khi chuyển sang 4.x. Bước trung gian này giúp tách lỗi nâng dependency khỏi lỗi đổi API và cho phép chuyển khỏi annotation legacy trước khi thay đổi package lần cuối.

Spring Shell 4.0 yêu cầu Spring Framework 7 và Spring Boot 4 trở lên. Hãy kiểm tra phiên bản Spring Boot, Java và dependency management của dự án trước khi thay imports.

## 2. Bảng đổi package quan trọng

### Annotation và command API

| Spring Shell 3.x | Spring Shell 4.x | Ghi chú |
|---|---|---|
| `org.springframework.shell.standard.ShellComponent` | `org.springframework.stereotype.Component` | `@ShellComponent` legacy đã bị loại bỏ; command class vẫn phải là Spring bean |
| `org.springframework.shell.standard.ShellMethod` | `org.springframework.shell.core.command.annotation.Command` | Đổi annotation và đổi thuộc tính `key` thành `name` |
| `org.springframework.shell.standard.ShellOption` | `org.springframework.shell.core.command.annotation.Option` | Đổi `value` thành `longName`/`shortName`, `help` thành `description` |
| `org.springframework.shell.standard.ShellCommandGroup` | `org.springframework.shell.core.command.annotation.CommandGroup` | Chuyển group cấp class sang `name`; thêm `prefix` nếu cần tiền tố command |
| `org.springframework.shell.command.annotation.Command` (3.4) | `org.springframework.shell.core.command.annotation.Command` | Chuyển package và đổi `command` thành `name` |
| `org.springframework.shell.command.annotation.Option` (3.4) | `org.springframework.shell.core.command.annotation.Option` | Chuyển package; thuộc tính tên option chuyển từ số nhiều sang số ít |
| `org.springframework.shell.command.annotation.Argument` (3.4) | `org.springframework.shell.core.command.annotation.Argument` | Chuyển package |
| `org.springframework.shell.command.annotation.EnableCommand` (3.4) | `org.springframework.shell.core.command.annotation.EnableCommand` | Chuyển package; vẫn dùng ngoài Spring Boot |
| `@Command` đặt trên class trong 3.4 | `@CommandGroup` | Tách prefix và tên nhóm khỏi annotation command method |

### Một số package khác

| Package 3.x | Hướng chuyển trong 4.x |
|---|---|
| `org.springframework.shell.standard` | Các API chuẩn được hợp nhất vào module `spring-shell-core`; annotation legacy như `ShellMethod` không còn tương đương cùng tên |
| `org.springframework.shell.command` | Các command API cốt lõi chuyển sang `org.springframework.shell.core.command` |
| `org.springframework.shell.command.annotation` | `org.springframework.shell.core.command.annotation` |
| `org.springframework.shell.table` | `org.springframework.shell.jline.tui.table` |

Không thay mọi import `org.springframework.shell.standard.*` bằng `org.springframework.shell.core.*` một cách tự động. Một số annotation legacy đã bị xóa và cần chuyển sang annotation mới hoặc thay đổi cách thiết kế command.

Với các API chuẩn khác còn được giữ lại, migration guide chuyển các package dưới `org.springframework.shell.standard` sang `org.springframework.shell.core`; hãy tra đúng class cụ thể thay vì suy luận rằng mọi type cũ vẫn tồn tại với cùng tên.

## 3. Chuyển từ mô hình legacy 3.3

Ví dụ command trong Spring Shell 3.3:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class ProjectCommands {

    @ShellMethod(value = "List projects.", key = "project list")
    public String list(
            @ShellOption(
                    value = { "--status" },
                    defaultValue = "all",
                    help = "Filter projects by status") String status) {
        return "Projects with status: " + status;
    }
}
```

Trong Spring Shell 4:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ProjectCommands {

    @Command(name = { "project", "list" }, description = "List projects.")
    public String list(
            @Option(
                    longName = "status",
                    defaultValue = "all",
                    description = "Filter projects by status") String status) {
        return "Projects with status: " + status;
    }
}
```

Những thay đổi:

1. `@ShellComponent` được thay bằng `@Component` hoặc một stereotype Spring phù hợp.
2. `@ShellMethod` được thay bằng `@Command`.
3. `key` được thay bằng `name`; `value` mô tả command được thay bằng `description`.
4. `@ShellOption` được thay bằng `@Option`.
5. `value = "--status"` trở thành `longName = "status"`; không đặt tiền tố `--` trong giá trị `longName`.
6. `help` của option trở thành `description`.

Giữ nguyên logic nghiệp vụ trong method hoặc service. Tập trung thay metadata command và xác nhận cú pháp command thực tế sau khi nâng cấp.

## 4. Chuyển từ annotation model mới của 3.4

Nếu dự án đã dùng `@Command` trong Spring Shell 3.4, thay đổi thường ít hơn vì mô hình annotation đã gần với 4.x.

Spring Shell 3.4:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class GreetingCommands {

    @Command(command = "hello", description = "Greet a user")
    public String hello(
            @Option(longNames = { "name", "user" },
                    shortNames = { 'n', 'u' },
                    defaultValue = "World") String name) {
        return "Hello " + name;
    }
}
```

Spring Shell 4:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class GreetingCommands {

    @Command(name = "hello", description = "Greet a user")
    public String hello(
            @Option(longName = "name", shortName = 'n',
                    defaultValue = "World") String name) {
        return "Hello " + name;
    }
}
```

Các điểm khác biệt:

- Package `org.springframework.shell.command.annotation` chuyển thành `org.springframework.shell.core.command.annotation`.
- `command` được đổi thành `name`.
- `longNames` được đổi thành `longName`.
- `shortNames` được đổi thành `shortName`.
- Chỉ còn một tên dài và một tên ngắn cho mỗi option.

Nếu đang dùng annotation model 3.4, không đổi `@Command` thành `@ShellMethod`. `@ShellMethod` là API legacy đã bị loại bỏ trong 4.x.

## 5. Đổi thuộc tính `command` thành `name`

Trong annotation model 3.4, thuộc tính `command` xác định tên command và có thể được dùng ở cả cấp class lẫn method. Trong 4.x, `@Command` chỉ được đặt trên method và tên command dùng thuộc tính `name`.

| 3.4 | 4.x |
|---|---|
| `@Command(command = "project list")` | `@Command(name = "project list")` |
| `@Command(command = { "project", "list" })` | `@Command(name = { "project", "list" })` |
| `@ShellMethod(key = "project list")` | `@Command(name = { "project", "list" })` |

Tên command có thể truyền dưới dạng chuỗi đầy đủ hoặc mảng các phần. Spring Shell tách và chuẩn hóa các phần tên. Với command nhiều cấp, dùng mảng giúp cấu trúc rõ ràng:

```java
@Command(name = { "project", "environment", "list" })
public String listEnvironments() {
    return "...";
}
```

Trong 4.x, không đặt `@Command` trên class. Nếu muốn gom các command có chung prefix, dùng `@CommandGroup` như phần tiếp theo.

## 6. Chuyển nhóm command cấp class sang `@CommandGroup`

Spring Shell 3.4 cho phép đặt `@Command` ở cấp class để khai báo prefix và group dùng chung:

```java
// Spring Shell 3.4
@Component
@Command(command = "github auth", group = "GitHub Authentication")
public class GitHubCommands {

    @Command(command = "login", description = "Log in to GitHub")
    public void login() {
        // ...
    }

    @Command(command = "logout", description = "Log out from GitHub")
    public void logout() {
        // ...
    }
}
```

Trong 3.4, class command còn phải được đưa vào command scanning bằng `@EnableCommand` hoặc `@CommandScan` theo cách khởi tạo ứng dụng. Ví dụ trên chỉ minh họa mapping group/prefix.

Trong Spring Shell 4.0.2 trở lên:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(prefix = "github auth", name = "GitHub Authentication")
public class GitHubCommands {

    @Command(name = "login", description = "Log in to GitHub")
    public void login() {
        // ...
    }

    @Command(name = "logout", description = "Log out from GitHub")
    public void logout() {
        // ...
    }
}
```

`@CommandGroup` có từ Spring Shell 4.0.2 và là component stereotype. Các thuộc tính chính:

- `prefix`: tiền tố chung khi gọi command, ví dụ `github auth`.
- `name`: tên nhóm hiển thị trong help.
- `description`: mô tả nhóm.

Nếu một command có thuộc tính `group` riêng, group ở cấp command có thể ghi đè group mặc định của class. Nếu chỉ cần phân nhóm hiển thị mà không cần prefix, dùng `@CommandGroup(name = "...")`.

Với Spring Shell 4.0.0 hoặc 4.0.1, `@CommandGroup` chưa có. Có thể đặt tên đầy đủ trong từng `@Command(name = ...)` và khai báo `group` trên từng method, hoặc nâng lên ít nhất 4.0.2 trước khi chuyển nhóm cấp class.

## 7. Chuyển `key`, alias và mô tả command

Trong mô hình legacy:

- `@ShellMethod(key = ...)` xác định tên command.
- `@ShellMethod(value = ...)` xác định mô tả.
- `key` có thể chứa nhiều tên để đăng ký nhiều cách gọi.

Trong 4.x:

- `@Command(name = ...)` xác định tên chính.
- `@Command(alias = ...)` khai báo alias.
- `@Command(description = ...)` mô tả command.
- `@Command(value = ...)` là alias của `description` trong API 4.x hiện hành; nên dùng `description` để code dễ đọc.

Ví dụ:

```java
@Command(
        name = "project list",
        alias = { "projects", "prj-list" },
        description = "List all projects")
public String list() {
    return "...";
}
```

Không đưa nhiều tên command vào `name` với ý định tạo alias. Dùng `alias` cho các tên thay thế; `name` giữ vai trò tên chính.

## 8. Chuyển thuộc tính của `@Option`

API `@Option` trong 4.x được đơn giản hóa so với annotation model 3.4:

| 3.4 `@Option` | 4.x `@Option` | Ý nghĩa |
|---|---|---|
| `longNames = { "output", "out" }` | `longName = "output"` | Tên option dài chính; chỉ còn một tên |
| `shortNames = { 'o', 'O' }` | `shortName = 'o'` | Tên option ngắn chính; chỉ còn một ký tự |
| `label = "OUTPUT"` | Bỏ | Label đã bị loại bỏ |
| `description = "Output file"` | `description = "Output file"` | Mô tả option được giữ |
| `defaultValue = "result.txt"` | `defaultValue = "result.txt"` | Giá trị mặc định được giữ |
| `required = true` | `required = true` | Bắt buộc nhập option được giữ |

Ví dụ:

```java
// Spring Shell 3.4
@Option(
        longNames = { "output", "out" },
        shortNames = { 'o', 'O' },
        label = "FILE",
        description = "Output file",
        defaultValue = "result.txt") String output
```

```java
// Spring Shell 4
@Option(
        longName = "output",
        shortName = 'o',
        description = "Output file",
        defaultValue = "result.txt") String output
```

Khi một option 3.x có nhiều tên dài/ngắn, hãy chọn một tên dài và một tên ngắn làm chuẩn. API annotation 4.x không còn danh sách alias cho option. Alias của command không thay thế alias của option vì chúng nằm ở hai cấp khác nhau.

### Chuyển từ `@ShellOption`

Với legacy `@ShellOption`, thuộc tính `value` có thể chứa các khóa option. Chuyển thành `longName` và/hoặc `shortName`:

```java
// Spring Shell 3.3
@ShellOption(value = { "--output", "-o" },
        defaultValue = "result.txt",
        help = "Output file") String output
```

```java
// Spring Shell 4
@Option(longName = "output", shortName = 'o',
        defaultValue = "result.txt",
        description = "Output file") String output
```

Tên trong `longName` là `output`, không phải `--output`; tên trong `shortName` là ký tự `o`, không phải chuỗi `-o`.

## 9. Chuyển positional parameter sang `@Argument`

Trong 4.x, `@Option` biểu diễn tham số có tên, còn `@Argument` biểu diễn tham số theo vị trí. Hãy quyết định rõ cú pháp CLI mà người dùng cần:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(name = "project show", description = "Show a project")
public String show(
        @Argument(index = 0, description = "Project identifier") long id,
        @Option(longName = "details", description = "Include full details") boolean details) {
    return "Project " + id + ", details=" + details;
}
```

Người dùng có thể gọi command với ID theo vị trí và option có tên, ví dụ `project show 42 --details true`.

`@Arguments` thu thập các positional token còn lại vào kiểu mảng hoặc collection. Ví dụ dùng `List<String>`:

```java
import java.util.List;

@Command(name = "project tag", description = "Add tags to a project")
public String addTags(
        @Argument(index = 0, description = "Project identifier") long projectId,
        @Arguments(description = "Tags to add") List<String> tags) {
    return "...";
}
```

Không nhầm `@Arguments` với option nhiều giá trị: annotation này thu thập các argument còn lại theo vị trí, không tái tạo mọi cách sử dụng `@ShellOption(arity = ...)` cũ.

## 10. Xử lý `arity` và option nhiều giá trị

Legacy `@ShellOption` có thuộc tính `arity` dạng số nguyên; annotation model 3.4 có `OptionArity`, `arityMin` và `arityMax`. API `@Option` của Spring Shell 4.0.x dùng mô hình tên option đơn giản hơn và không có cùng bộ thuộc tính arity như annotation 3.4.

Nếu command cũ nhận nhiều token sau một option, không đổi `arity` thành một thuộc tính giả trong 4.x. Hãy chọn cách biểu diễn mới dựa trên cú pháp cần giữ:

- Nếu dữ liệu có thể là một giá trị duy nhất, dùng một `@Option` và quy định định dạng như chuỗi phân tách bằng dấu phẩy.
- Nếu các giá trị là positional arguments còn lại, dùng `@Arguments` với array hoặc collection.
- Nếu cần giữ nguyên ngữ nghĩa option nhiều giá trị hoặc quy tắc parsing đặc biệt, kiểm tra khả năng của parser phiên bản đích và cân nhắc programmatic command registration.

Viết test cho trường hợp không có giá trị, một giá trị, nhiều giá trị và vượt số lượng cho phép. Đừng giả định rằng code compile đồng nghĩa cú pháp cũ vẫn hoạt động giống hệt.

## 11. Chuyển availability và completion vào `@Command`

Trong annotation model 3.4, khả năng sử dụng command có thể được khai báo bằng annotation riêng:

```java
// Spring Shell 3.4
@Command(command = "download")
@CommandAvailability("loginAvailabilityProvider")
public void download() {
    // ...
}
```

Trong 4.x, cấu hình provider ngay trên `@Command`:

```java
@Command(
        name = "download",
        availabilityProvider = "loginAvailabilityProvider")
public void download() {
    // ...
}
```

Completion cũng được gom về command level:

```java
@Command(
        name = "project deploy",
        completionProvider = "projectDeployCompletionProvider")
public void deploy(
        @Option(longName = "environment") String environment,
        @Option(longName = "region") String region) {
    // ...
}
```

Trong 4.x, `@OptionValues` và cơ chế value provider gắn trực tiếp vào `@ShellOption` không còn được dùng. Thay vào đó, tạo một bean `CompletionProvider` và tham chiếu bằng `completionProvider`. Completion provider nhận completion context của command, nhờ đó có thể đưa ra gợi ý dựa trên nhiều option cùng lúc.

Tương tự, các annotation availability riêng trong 3.x như `@CommandAvailability` hoặc `@ShellMethodAvailability` được chuyển thành thuộc tính `availabilityProvider` của `@Command`.

`@Command` cũng có thuộc tính `exitStatusExceptionMapper` để chỉ định bean ánh xạ exception thành exit status. Khi chuyển exception handling từ 3.x, rà soát resolver/mapper cũ và chuyển sang cơ chế mới thay vì giữ annotation đã bị loại bỏ.

## 12. Xử lý `interactionMode` đã bị loại bỏ

Annotation model 3.x có thể gắn `interactionMode` để chỉ định command dành cho interactive hoặc non-interactive shell. Trong 4.x, `InteractionMode` không còn được dùng và command không còn được đánh dấu riêng theo mode.

Ứng dụng chọn chế độ shell ngay lúc khởi động. Tất cả command được đăng ký cho shell và chạy theo mode mà shell đang sử dụng. Nếu command thực sự cần terminal, hãy kiểm tra khả năng tương tác tại runtime và đưa ra thông báo phù hợp; không cố gắng khôi phục `interactionMode` bằng một thuộc tính tùy chỉnh trên `@Command`.

## 13. Chuyển cơ chế đăng ký command

### Spring Boot application

Trong Spring Shell 3.4, ứng dụng thường khai báo `@EnableCommand` hoặc `@CommandScan`, kể cả khi dùng Spring Boot. Trong 4.x, Spring Boot auto-configuration tự động quét command; bỏ `@CommandScan` và không cần thêm `@EnableCommand` chỉ để kích hoạt command scanning.

Command class vẫn phải được Spring phát hiện. Dùng `@Component`, `@Service` hoặc `@CommandGroup` và bảo đảm package nằm trong component scan.

### Ứng dụng không dùng Spring Boot

Với Spring Framework thuần, tiếp tục dùng `@EnableCommand` trên cấu hình và import mới:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.annotation.EnableCommand;

@Configuration(proxyBeanMethods = false)
@EnableCommand(ProjectCommands.class)
public class ShellConfiguration {
}
```

`@CommandScan` đã bị loại bỏ. Chuyển sang `@EnableCommand` với danh sách class command rõ ràng hoặc cách đăng ký programmatic phù hợp.

## 14. Thay đổi module và dependency đi kèm package

Một số lỗi import sau nâng cấp xuất phát từ việc module đã được hợp nhất hoặc đổi tên:

| Module 3.x | Thay đổi trong 4.x |
|---|---|
| `spring-shell-standard` | Hợp nhất vào `spring-shell-core` |
| `spring-shell-standard-commands` | Hợp nhất vào `spring-shell-core` |
| `spring-shell-autoconfigure` | Đổi tên thành `spring-shell-core-autoconfigure` |
| `spring-shell-table` | Hợp nhất vào `spring-shell-jline` |

Ngoài ra:

- `spring-shell-core` không còn phụ thuộc Spring Boot. Ứng dụng Spring Boot cần thêm `spring-shell-core-autoconfigure` hoặc dùng một Spring Shell starter.
- `spring-shell-core` không còn kéo JLine theo. Nếu cần JLine-based console, thêm `spring-shell-jline` hoặc starter tương ứng.
- Các command built-in trước đây thuộc `spring-shell-standard-commands` đã được đưa vào core.

Đừng chỉ xóa module cũ khỏi build file mà không kiểm tra tính năng mà ứng dụng đang dùng. Nếu dự án dùng table API, JLine console hoặc Spring Boot auto-configuration, hãy thêm module đích tương ứng.

## 15. Quy trình nâng cấp đề xuất

Thực hiện theo thứ tự để giới hạn phạm vi lỗi:

1. **Nâng lên Spring Shell 3.4.x mới nhất.** Giữ Spring Boot 3.x tương thích và xử lý các cảnh báo deprecated trước.
2. **Xác định command model.** Tìm `@ShellComponent`/`@ShellMethod`/`@ShellOption` và `@Command`/`@Option` của annotation model mới.
3. **Chuyển legacy annotation nếu còn dùng.** Đổi sang `@Component`, `@Command`, `@Option`, `@Argument`.
4. **Nâng Spring Boot và Framework.** Spring Shell 4 yêu cầu Spring Boot 4+ và Spring Framework 7+.
5. **Cập nhật dependency modules.** Đổi autoconfigure, bỏ module đã hợp nhất và thêm JLine nếu ứng dụng cần.
6. **Đổi imports.** Chuyển annotation package sang `org.springframework.shell.core.command.annotation` và các API liên quan sang package mới.
7. **Đổi thuộc tính annotation.** `command` thành `name`, `longNames` thành `longName`, `shortNames` thành `shortName`; bỏ `label` và các thuộc tính đã bị loại bỏ.
8. **Chuyển grouping.** Dùng `@CommandGroup` cho prefix/group cấp class nếu target là 4.0.2+.
9. **Chuyển customization.** Gộp availability, completion và exception mapping vào `@Command`.
10. **Cập nhật registration.** Bỏ `@CommandScan` trong Spring Boot; giữ `@EnableCommand` cho ứng dụng không dùng Boot.
11. **Biên dịch và chạy test.** Kiểm tra help, command names, options, arguments, completion và availability.
12. **Kiểm tra hành vi runtime.** Thử interactive/non-interactive, script và exit status vì Spring Shell 4 có các thay đổi execution riêng.

## 16. Tìm kiếm các API cũ trong mã nguồn

Trước khi compile, tìm các annotation và thuộc tính cũ trong source:

```bash
rg -n "ShellComponent|ShellMethod|ShellOption|CommandAvailability|ShellMethodAvailability|CommandScan|OptionValues|interactionMode|longNames|shortNames|label|command\s*=" src
```

Đây là danh sách điểm bắt đầu, không phải lệnh thay thế tự động. Một chuỗi như `command =` có thể xuất hiện trong cấu hình khác không liên quan tới Spring Shell; xem từng kết quả trước khi sửa.

Kiểm tra imports:

```bash
rg -n "org\.springframework\.shell\.(standard|command\.annotation|table)" src
```

Sau khi cập nhật, biên dịch lại và xác nhận không còn import tới annotation legacy đã bị xóa.

## 17. Kiểm thử sau migration

Một command compile được vẫn có thể thay đổi cú pháp hoặc không còn được đăng ký. Tạo test bao phủ các hành vi người dùng nhìn thấy:

| Hạng mục | Điều cần xác nhận |
|---|---|
| Registration | Command xuất hiện trong help và registry |
| Command name | Tên chính và alias vẫn đúng |
| Group/prefix | Command group và prefix không đổi ngoài chủ đích |
| Description/help | Mô tả và hướng dẫn option vẫn rõ ràng |
| Long/short option | `--name` và `-n` hoạt động đúng |
| Option default | Giá trị mặc định và required behavior giữ đúng |
| Positional argument | `@Argument(index=...)` nhận đúng vị trí |
| Multi-argument | `@Arguments` thu thập đúng các token còn lại |
| Availability | Command bị ẩn/không khả dụng đúng trạng thái |
| Completion | CompletionProvider trả đúng gợi ý |
| Exception/exit status | Exception được ánh xạ đúng mã thoát |
| Spring profile | Chỉ command thuộc profile được kích hoạt mới đăng ký |
| Interactive mode | Command không phụ thuộc sai vào `InteractionMode` cũ |

Chạy test với Spring Shell version đích, không chỉ chạy compile. Nếu thay đổi cú pháp option, hãy kiểm tra cả help output và các script hiện có để phát hiện breaking change đối với người dùng.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ShellMethod` hoặc `ShellOption` không tìm thấy | Legacy annotation đã bị loại bỏ trong 4.x | Chuyển sang `@Command` và `@Option` |
| `org.springframework.shell.command.annotation` không tồn tại | Package 3.4 chưa được chuyển | Dùng `org.springframework.shell.core.command.annotation` |
| `command` không còn là thuộc tính hợp lệ | `@Command.command` đã đổi thành `name` | Sửa `command =` thành `name =` |
| `@Command` không áp dụng được cho class | 4.x chỉ cho phép `@Command` trên method | Dùng `@CommandGroup` cho class |
| Không thấy group/prefix cũ | Chưa chuyển class-level mapping | Đặt `prefix` và `name` trong `@CommandGroup` |
| `longNames`/`shortNames` không compile | 4.x dùng một tên dài/ngắn | Chọn một `longName` và một `shortName` |
| `label` không còn | Option label đã bị loại bỏ | Đưa mô tả hữu ích vào `description` |
| `@OptionValues` không tìm thấy | Completion chuyển lên command level | Tạo `CompletionProvider` và đặt `completionProvider` |
| `@CommandScan` không tìm thấy | Annotation này đã bị loại bỏ | Bỏ nó trong Boot hoặc dùng `@EnableCommand` ngoài Boot |
| Command không xuất hiện | Class không phải bean hoặc package không được scan | Kiểm tra `@Component`/`@CommandGroup` và component scan |
| Thiếu class table hoặc JLine | Module đã được hợp nhất/đổi tên | Dùng `spring-shell-jline` và package table mới |
| Spring Boot auto-config không hoạt động | `spring-shell-core` không còn kéo Boot | Thêm starter hoặc `spring-shell-core-autoconfigure` |
| Command chỉ lỗi khi nhập nhiều giá trị | Ngữ nghĩa arity cũ chưa được thiết kế lại | Dùng `@Arguments` nếu phù hợp hoặc programmatic registration |

## 19. Checklist hoàn tất migration

- [ ] Đã nâng dự án lên Spring Shell 3.4.x mới nhất trước khi chuyển sang 4.x.
- [ ] Đã nâng Spring Boot lên 4+ và Spring Framework lên 7+.
- [ ] Đã loại bỏ `@ShellComponent`, `@ShellMethod`, `@ShellOption`.
- [ ] Đã chuyển package annotation sang `org.springframework.shell.core.command.annotation`.
- [ ] Đã đổi `@Command(command = ...)` thành `@Command(name = ...)`.
- [ ] `@Command` chỉ còn đặt trên method.
- [ ] Đã chuyển grouping cấp class sang `@CommandGroup` nếu dùng 4.0.2+.
- [ ] Đã đổi `longNames`/`shortNames` thành `longName`/`shortName` và xử lý alias dư.
- [ ] Đã loại bỏ `label`, `@OptionValues` và `interactionMode` cũ.
- [ ] Đã chuyển availability/completion/exception mapping vào thuộc tính `@Command`.
- [ ] Đã dùng `@Argument`/`@Arguments` cho positional input.
- [ ] Đã bỏ `@CommandScan` trong ứng dụng Spring Boot.
- [ ] Đã giữ `@EnableCommand` cho ứng dụng không dùng Spring Boot.
- [ ] Đã cập nhật module `spring-shell-core-autoconfigure` và `spring-shell-jline` khi cần.
- [ ] Đã kiểm thử help, registration, option, argument, completion và exit status.
- [ ] Đã chạy thử các script và cú pháp command hiện có với phiên bản 4.x.

## Tài liệu tham khảo

1. [Spring Shell – v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) – thay đổi breaking từ 3.x lên 4.x, annotation, command grouping, registration và dependency modules.
2. [Spring Shell 3.3 – Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html) – mô hình legacy `@ShellComponent`, `@ShellMethod` và `@ShellOption`.
3. [Spring Shell 3.4 – `@Command` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Command.html) – package và thuộc tính `command` trong annotation model 3.4.
4. [Spring Shell 4 – `@Command` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html) – thuộc tính `name`, `alias`, `availabilityProvider`, `completionProvider` và `exitStatusExceptionMapper`.
5. [Spring Shell 4 – `@Option` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html) – `longName`, `shortName`, `description`, `required` và `defaultValue`.
6. [Spring Shell 4 – `@Argument` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Argument.html) – positional arguments theo index.
7. [Spring Shell 4 – `@CommandGroup` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html) – prefix và nhóm command, có từ 4.0.2.
8. [Spring Shell 4 – Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) – đăng ký annotation và programmatic trong Spring Boot/Framework.
9. [Spring Shell Releases](https://github.com/spring-projects/spring-shell/releases) – xác nhận tính năng và thay đổi theo từng bản 4.0.x.

Khi nâng từ Spring Shell 3.x lên 4.x, hãy xác định trước dự án đang dùng annotation legacy 3.3 hay annotation model mới 3.4. Sau đó chuyển package, đổi `command` thành `name`, đưa nhóm command lên `@CommandGroup`, cập nhật option và registration theo API mới. Cuối cùng kiểm tra help, cú pháp command và các script thực tế để bảo đảm migration không chỉ hết lỗi biên dịch mà còn giữ đúng trải nghiệm của người dùng.
