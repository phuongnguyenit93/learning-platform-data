# Khác biệt thuộc tính command của 3.x với name của 4.x

Spring Shell 3.x và 4.x đều có mô hình khai báo command bằng annotation `@Command`, nhưng tên thuộc tính dùng để xác định đường dẫn command đã thay đổi. Trong Spring Shell 3.x, thuộc tính là `command`; từ Spring Shell 4.x, thuộc tính tương ứng là `name`.

Đây là thay đổi API cần xử lý khi nâng cấp mã nguồn. Ví dụ `@Command(command = "project list")` của 3.x phải được chuyển thành `@Command(name = "project list")` trong 4.x. Chỉ thay tên thuộc tính là chưa đủ cho mọi dự án: package annotation đã đổi, cách khai báo prefix ở cấp lớp cũng thay đổi, và một số annotation legacy của 3.x đã bị loại bỏ.

Bài học tập trung vào annotation `@Command` của mô hình declarative mới trong Spring Shell 3.x và 4.x. Không nhầm nó với annotation legacy `@ShellMethod`, vốn dùng `key` để khai báo tên lệnh.

## 1. Phân biệt hai API theo phiên bản

| Nội dung | Spring Shell 3.x | Spring Shell 4.x |
|---|---|---|
| Annotation khai báo command | `@Command` | `@Command` |
| Package | `org.springframework.shell.command.annotation` | `org.springframework.shell.core.command.annotation` |
| Thuộc tính tên command | `command` | `name` |
| Kiểu dữ liệu thuộc tính | `String[]` | `String[]` |
| Dùng trên phương thức | Có | Có |
| Dùng trên lớp để đặt prefix chung | Có | Không |
| Nhóm và prefix ở cấp lớp | `@Command(command = "...", group = "...")` | `@CommandGroup(prefix = "...", name = "...")` |
| Alias của command | `alias` | `alias` |

Trong 3.x, `command` có thể được khai báo ở cấp lớp và cấp phương thức. Giá trị ở cấp lớp được dùng làm prefix cho các command ở cấp phương thức. Trong 4.x, `@Command` chỉ đánh dấu phương thức; việc gom command cùng prefix và tên nhóm ở cấp lớp được chuyển sang `@CommandGroup`.

Các API này thuộc hai dòng phiên bản khác nhau. Không đặt cả hai tên thuộc tính trong một annotation với kỳ vọng chúng là alias cho nhau: compiler chỉ chấp nhận thuộc tính có trong API mà dependency hiện tại cung cấp.

## 2. Spring Shell 3.x: dùng thuộc tính command

Trong Spring Shell 3.x, annotation declarative nằm trong package:

```java
import org.springframework.shell.command.annotation.Command;
```

Ví dụ khai báo command đầy đủ:

```java
import org.springframework.shell.command.annotation.Command;

public class ProjectCommands {

    @Command(
        command = "project list",
        description = "Liệt kê các project"
    )
    public String listProjects() {
        return "Danh sách project";
    }
}
```

Ở đây:

- `command = "project list"` xác định đường dẫn command mà người dùng nhập.
- `description` mô tả chức năng trong phần trợ giúp.
- Phương thức Java `listProjects()` là đích thực thi khi command được gọi.

Thuộc tính `command` có kiểu `String[]`. Có thể truyền toàn bộ đường dẫn trong một chuỗi hoặc tách thành các phần:

```java
@Command(command = "project list")
public String listProjects() {
    return "Danh sách project";
}
```

Cách khai báo tương ứng:

```java
@Command(command = {"project", "list"})
public String listProjects() {
    return "Danh sách project";
}
```

Spring Shell ghép các phần thành command `project list`. Cách viết mảng hữu ích khi muốn thể hiện rõ các cấp của đường dẫn; cách viết chuỗi thuận tiện khi command đã có dạng hoàn chỉnh.

### 2.1. Đặt prefix ở cấp lớp trong 3.x

Một điểm quan trọng của API 3.x là `@Command` có thể đặt trên lớp để khai báo prefix chung:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
@Command(
    command = "project",
    group = "Project Commands"
)
public class ProjectCommands {

    @Command(
        command = "list",
        description = "Liệt kê các project"
    )
    public String listProjects() {
        return "Danh sách project";
    }

    @Command(
        command = "show",
        description = "Hiển thị thông tin project"
    )
    public String showProject() {
        return "Thông tin project";
    }
}
```

Prefix `project` ở cấp lớp được kết hợp với tên command ở cấp phương thức. Các command kết quả là:

```text
project list
project show
```

Nhóm `Project Commands` cũng được kế thừa bởi các command trong lớp. Đây là cách 3.x gom các command liên quan vào cùng một lớp và tái sử dụng metadata chung.

Trong mô hình đăng ký annotation của 3.x, command target còn cần được đăng ký. Với Spring Boot, có thể dùng `@CommandScan`; với cấu hình tường minh, dùng `@EnableCommand` để chỉ định các lớp command. Việc khai báo `@Command` tự nó không đồng nghĩa mọi lớp đều tự động được đăng ký.

## 3. Spring Shell 4.x: dùng thuộc tính name

Trong Spring Shell 4.x, annotation mới nằm trong package:

```java
import org.springframework.shell.core.command.annotation.Command;
```

Thuộc tính `command` được đổi tên thành `name`. Ví dụ 3.x:

```java
@Command(
    command = "project list",
    description = "Liệt kê các project"
)
public String listProjects() {
    return "Danh sách project";
}
```

được chuyển thành 4.x:

```java
@Command(
    name = "project list",
    description = "Liệt kê các project"
)
public String listProjects() {
    return "Danh sách project";
}
```

Ý nghĩa của giá trị không thay đổi: `name` xác định đường dẫn command. Kiểu dữ liệu vẫn là `String[]`, vì vậy có thể viết:

```java
@Command(name = "project list")
public String listProjects() {
    return "Danh sách project";
}
```

hoặc:

```java
@Command(name = {"project", "list"})
public String listProjects() {
    return "Danh sách project";
}
```

Trong 4.x, nếu không chỉ định `name`, tên phương thức có thể được dùng làm tên command. Khi command là một phần của giao diện công khai hoặc được script gọi, nên khai báo `name` rõ ràng để việc đổi tên phương thức không vô tình đổi tên CLI.

## 4. Chuyển prefix cấp lớp sang CommandGroup trong 4.x

Spring Shell 4.x không cho phép đặt `@Command` trên lớp nữa. Annotation này chỉ áp dụng cho phương thức. Vì vậy, ví dụ 3.x có:

```java
@Component
@Command(command = "project", group = "Project Commands")
public class ProjectCommands {

    @Command(command = "list", description = "Liệt kê các project")
    public String listProjects() {
        return "Danh sách project";
    }
}
```

cần chuyển sang `@CommandGroup`:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.stereotype.Component;

@Component
@CommandGroup(
    prefix = "project",
    name = "Project Commands"
)
public class ProjectCommands {

    @Command(
        name = "list",
        description = "Liệt kê các project"
    )
    public String listProjects() {
        return "Danh sách project";
    }

    @Command(
        name = "show",
        description = "Hiển thị thông tin project"
    )
    public String showProject() {
        return "Thông tin project";
    }
}
```

`@CommandGroup` được bổ sung từ Spring Shell 4.0.2. Nếu dự án đang ở 4.0.0 hoặc 4.0.1, hãy kiểm tra release cụ thể trước khi dùng annotation này và chọn bản 4.x có hỗ trợ.

Các command được tạo ra vẫn là:

```text
project list
project show
```

Hai thuộc tính của `@CommandGroup` có vai trò riêng:

- `prefix` là phần đầu của đường dẫn command được áp dụng cho các phương thức trong nhóm.
- `name` là tên nhóm hiển thị trong trợ giúp.
- `description` có thể mô tả nhóm command.

Do đó, `@CommandGroup(name = "Project Commands")` không đặt tên command. Tên command vẫn nằm ở `@Command(name = "...")` trên từng phương thức. Nếu chỉ muốn nhóm command mà không cần prefix, có thể bỏ `prefix` và chỉ đặt `name`.

Nếu một command cần thuộc nhóm khác, thuộc tính `group` khai báo trực tiếp trên `@Command` của phương thức có thể ghi đè group kế thừa từ `@CommandGroup`.

## 5. So sánh trước và sau khi nâng cấp

Giả sử ứng dụng có command `project list` và `project show`.

### 5.1. Mã nguồn 3.x

```java
package com.example.projectcli.command;

import org.springframework.shell.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
@Command(command = "project", group = "Project Commands")
public class ProjectCommands {

    @Command(
        command = "list",
        description = "Liệt kê các project"
    )
    public String listProjects() {
        return "Danh sách project";
    }

    @Command(
        command = "show",
        description = "Hiển thị thông tin project"
    )
    public String showProject() {
        return "Thông tin project";
    }
}
```

### 5.2. Mã nguồn 4.x

```java
package com.example.projectcli.command;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.stereotype.Component;

@Component
@CommandGroup(
    prefix = "project",
    name = "Project Commands"
)
public class ProjectCommands {

    @Command(
        name = "list",
        description = "Liệt kê các project"
    )
    public String listProjects() {
        return "Danh sách project";
    }

    @Command(
        name = "show",
        description = "Hiển thị thông tin project"
    )
    public String showProject() {
        return "Thông tin project";
    }
}
```

### 5.3. Bảng ánh xạ khi chuyển đổi

| Mã nguồn 3.x | Mã nguồn 4.x | Ý nghĩa |
|---|---|---|
| Import `org.springframework.shell.command.annotation.Command` | Import `org.springframework.shell.core.command.annotation.Command` | Package mới |
| `@Command(command = "project list")` | `@Command(name = "project list")` | Đổi tên thuộc tính |
| `@Command(command = "project")` trên lớp | `@CommandGroup(prefix = "project", ...)` | Chuyển prefix cấp lớp |
| `group = "Project Commands"` trên `@Command` cấp lớp | `name = "Project Commands"` trên `@CommandGroup` | Chuyển tên nhóm |
| `@Command(command = "list")` trên phương thức | `@Command(name = "list")` trên phương thức | Đổi thuộc tính tên command |
| `alias = "..."` | `alias = "..."` | Alias vẫn là thuộc tính riêng |

Việc chuyển đổi cần giữ nguyên hành vi mà người dùng nhìn thấy: command path, mô tả, nhóm và alias. Sau khi sửa mã nguồn, hãy kiểm tra lại trợ giúp và gọi từng command để xác nhận các tên cũ vẫn hoạt động như dự kiến.

## 6. Phân biệt name, alias, description và group trong 4.x

Khi chuyển sang 4.x, không gộp các metadata vào một thuộc tính. Mỗi thuộc tính có trách nhiệm riêng:

| Thuộc tính | Vai trò | Ví dụ |
|---|---|---|
| `name` | Đường dẫn command chính | `project list` |
| `alias` | Tên thay thế để gọi cùng command | `projects` |
| `description` | Mô tả ngắn hiển thị trong trợ giúp | `Liệt kê các project` |
| `help` | Hướng dẫn sử dụng chi tiết | Cú pháp, ví dụ và lưu ý |
| `group` | Nhóm trợ giúp của command | `Project Commands` |

Ví dụ:

```java
@Command(
    name = "project list",
    alias = {"projects", "pl"},
    description = "Liệt kê các project",
    help = "Hiển thị các project hiện có. Ví dụ: project list",
    group = "Project Commands"
)
public String listProjects() {
    return "Danh sách project";
}
```

Người dùng gọi command chính bằng `project list`, hoặc gọi qua alias `projects` và `pl`. Các tên thay thế được khai báo trong `alias`; không đưa alias vào `name` chỉ để tạo nhiều cách gọi, vì hai thuộc tính có ý nghĩa khác nhau trong API 4.x.

Đối với prefix chung, dùng `@CommandGroup`. Đối với alias riêng của một command, dùng `alias` trên phương thức. Điều này giúp cấu trúc tên lệnh và các tên thay thế được thể hiện rõ ràng.

Trong 3.x, `alias` cũng có thể được đặt ở cấp lớp và kết hợp với alias ở cấp phương thức. Trong 4.x, `@Command` chỉ đặt trên phương thức nên alias được khai báo ở từng command; `@CommandGroup` chỉ quản lý prefix và metadata nhóm, không thay thế alias cấp lớp.

## 7. Những thay đổi liên quan cần lưu ý khi nâng cấp

Thay `command` thành `name` là thay đổi dễ nhìn thấy, nhưng quá trình nâng cấp từ 3.x lên 4.x còn có các điểm liên quan đến khai báo và đăng ký command.

### 7.1. Package annotation thay đổi

Các annotation mới của 4.x thuộc package `org.springframework.shell.core.command.annotation`. Vì vậy, ngoài việc đổi thuộc tính, cần sửa import. IDE có thể gợi ý nhầm một annotation cùng tên từ dependency cũ nếu classpath vẫn chứa thư viện 3.x.

### 7.2. @Command không còn dùng trên lớp

Trong 3.x, `@Command` có thể đánh dấu lớp và phương thức. Trong 4.x, target của annotation chỉ còn là phương thức. Dùng `@Command` ở cấp lớp sẽ gây lỗi biên dịch. Hãy chuyển prefix và tên nhóm sang `@CommandGroup`.

### 7.3. Cơ chế đăng ký trong Spring Boot thay đổi

Trong 3.x, mô hình annotation yêu cầu `@EnableCommand` hoặc `@CommandScan` để đăng ký các command target; với Spring Boot, `@CommandScan` là cách quét các target. Trong 4.x, Spring Boot tự động bật command scanning, vì vậy không cần `@CommandScan`. Nếu không dùng Spring Boot, `@EnableCommand` vẫn được dùng để bật phát hiện command.

### 7.4. Annotation legacy đã bị loại bỏ

Spring Shell 4.x loại bỏ các annotation legacy như `@ShellComponent`, `@ShellMethod`, `@ShellOption` và các annotation liên quan đã bị deprecated trong 3.x. Dự án dùng mô hình legacy cần chuyển sang các annotation mới như `@Component`, `@Command`, `@Option` và `@Argument`.

Đặc biệt, không nhầm hai cặp thuộc tính sau:

| Annotation legacy | Annotation declarative mới |
|---|---|
| `@ShellMethod(key = "project list")` | 3.x `@Command(command = "project list")` |
|  | 4.x `@Command(name = "project list")` |

`key` thuộc `@ShellMethod`; `command` và `name` thuộc annotation `@Command` qua hai phiên bản. Chúng không phải các tên thuộc tính có thể thay thế lẫn nhau trong cùng một annotation.

### 7.5. Kiểm tra tương thích nền tảng

Spring Shell 4 dựa trên Spring Framework 7 và hỗ trợ Spring Boot từ 4 trở lên. Vì vậy, nâng cấp cần kiểm tra JDK, Spring Framework, Spring Boot, starter và các module Spring Shell cùng nhau. Chỉ sửa source code mà giữ nguyên bộ dependency 3.x có thể khiến project không resolve hoặc không khởi động được.

## 8. Quy trình chuyển đổi command từ 3.x sang 4.x

Có thể thực hiện theo thứ tự sau:

1. Xác nhận dự án đã nâng dependency nền tảng lên bộ phiên bản tương thích với Spring Shell 4.
2. Thay import `org.springframework.shell.command.annotation.Command` bằng import `org.springframework.shell.core.command.annotation.Command`.
3. Đổi thuộc tính `command` thành `name` trên từng phương thức.
4. Tìm mọi `@Command` đang đặt trên lớp và chuyển prefix, group sang `@CommandGroup`.
5. Kiểm tra `alias`, `description`, `help` và `group` ở từng command.
6. Chuyển các annotation legacy `@ShellComponent`, `@ShellMethod`, `@ShellOption` sang mô hình mới nếu dự án còn sử dụng.
7. Cập nhật cơ chế đăng ký command theo cách ứng dụng khởi động: Spring Boot 4 tự động scan; ứng dụng không dùng Boot cần cấu hình `@EnableCommand`.
8. Build lại và xử lý lỗi import, annotation target hoặc dependency.
9. Chạy `help`, xác minh nhóm command, rồi gọi command chính và từng alias bằng terminal hoặc script kiểm thử.

Một bảng kiểm chuyển đổi có thể dùng khi review:

- [ ] Không còn import `org.springframework.shell.command.annotation.Command` trong mã nguồn 4.x.
- [ ] Mọi command dùng `name` thay cho `command`.
- [ ] Không còn đặt `@Command` trên lớp.
- [ ] Prefix và tên nhóm chung đã chuyển sang `@CommandGroup`.
- [ ] Alias vẫn nằm trong `alias`.
- [ ] Mô tả và hướng dẫn vẫn nằm trong `description` và `help`.
- [ ] Annotation legacy đã được chuyển đổi.
- [ ] Command scanning được cấu hình phù hợp với Spring Boot hoặc Spring Framework thuần.
- [ ] Các command cũ vẫn có thể gọi bằng tên dự kiến sau khi nâng cấp.

## 9. Các lỗi thường gặp

**Chỉ đổi package mà quên đổi thuộc tính.** Import 4.x nhưng vẫn viết `@Command(command = "...")` sẽ không biên dịch vì annotation 4.x không có thuộc tính `command`. Hãy đổi thành `name`.

**Chỉ đổi thuộc tính mà quên package.** Import annotation 3.x trong project 4.x có thể làm IDE không tìm thấy class hoặc kéo nhầm dependency. Hãy kiểm tra import thuộc package `core.command.annotation`.

**Giữ @Command ở cấp lớp.** Annotation 4.x chỉ có target METHOD. Chuyển prefix và group chung sang `@CommandGroup`.

**Dùng name của CommandGroup để đặt tên command.** `@CommandGroup(name = "...")` đặt nhãn nhóm; `@Command(name = "...")` mới đặt đường dẫn command.

**Đưa alias vào name.** `name` là tên chính; `alias` là tên thay thế. Giữ hai khái niệm riêng để trợ giúp và định tuyến dễ hiểu.

**Giữ @CommandScan sau khi chuyển sang Spring Boot 4.** Spring Boot tự động bật command scanning trong mô hình 4.x. Kiểm tra và bỏ cấu hình cũ đã không còn được hỗ trợ, đồng thời giữ `@EnableCommand` nếu ứng dụng không dùng Boot.

**Cho rằng thay command thành name là toàn bộ quá trình nâng cấp.** Spring Shell 4 còn thay đổi package, command grouping, đăng ký command, module và các API khác. Theo dõi migration guide và xử lý toàn bộ thay đổi mà ứng dụng đang sử dụng.

## 10. Tài liệu tham khảo chính thức

- [Spring Shell 3.4 — Command annotation API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Command.html): thuộc tính `command`, `alias`, `group` và khả năng khai báo ở cấp lớp/phương thức.
- [Spring Shell 4 — Command annotation API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html): thuộc tính `name`, `alias`, `description`, `group` và phạm vi phương thức.
- [Spring Shell 4 — CommandGroup API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html): `prefix`, `name` và `description` của nhóm command.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): các thay đổi phá vỡ tương thích khi nâng cấp từ 3.x lên 4.x.

Điểm cần ghi nhớ khi đọc hoặc sửa mã nguồn: `command` của `@Command` trong Spring Shell 3.x đổi thành `name` của `@Command` trong 4.x. Khi nâng cấp, hãy đồng thời cập nhật package import và chuyển khai báo prefix cấp lớp sang `@CommandGroup`; sau đó xác minh lại command, alias và trợ giúp trên runtime 4.x.

