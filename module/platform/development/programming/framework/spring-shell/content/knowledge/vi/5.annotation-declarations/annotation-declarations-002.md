# Tên lệnh, mô tả, nhóm và tên thay thế trong mô hình legacy

Trong mô hình annotation legacy của Spring Shell, một phương thức Java được đánh dấu bằng `@ShellMethod` sẽ trở thành một command. Annotation này cho phép khai báo ba phần metadata quan trọng: mô tả command qua `value`, tên dùng để gọi command qua `key`, và nhóm hiển thị qua `group`.

Lớp chứa command thường được đánh dấu bằng `@ShellComponent` để Spring phát hiện bean và Spring Shell đăng ký các phương thức được chú thích. Tên phương thức Java có thể được dùng để suy ra tên command khi không khai báo `key`. Khi cần tên rõ ràng hoặc nhiều tên gọi tương đương, hãy khai báo `key` tường minh.

Bài học này tập trung vào API legacy `@ShellMethod` và `@ShellComponent`. Các ví dụ dùng phong cách của Spring Shell 2.x; hãy kiểm tra tài liệu đúng release trước khi áp dụng vào dự án đang dùng dòng phiên bản khác.

## 1. Cấu trúc khai báo command legacy

Ví dụ tối thiểu:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class GreetingCommands {

    @ShellMethod("Hiển thị lời chào")
    public String hello() {
        return "Xin chào!";
    }
}
```

Có hai annotation với hai vai trò khác nhau:

- `@ShellComponent` đánh dấu lớp là nơi Spring Shell có thể tìm các command.
- `@ShellMethod` đánh dấu phương thức là command và cung cấp metadata cho command đó.

Trong ví dụ trên, command được suy ra từ tên phương thức `hello`. Người dùng có thể nhập `hello` trong shell. Mô tả “Hiển thị lời chào” được dùng trong phần trợ giúp.

Một phương thức được đánh dấu `@ShellMethod` vẫn là phương thức Java thông thường. Nó có thể gọi service, nhận tham số và trả kết quả. Annotation bổ sung cách Spring Shell công bố phương thức đó như một giao diện dòng lệnh.

## 2. Tên command: suy ra từ tên phương thức hoặc khai báo bằng key

Tên command là chuỗi người dùng nhập trong shell. Với mô hình legacy, có hai cách xác định tên này.

### 2.1. Để Spring Shell suy ra tên từ phương thức

Khi không khai báo `key`, Spring Shell suy ra command key từ tên phương thức. Tên camelCase thường được chuyển thành dạng kebab-case:

| Tên phương thức Java | Tên command suy ra |
|---|---|
| `hello` | `hello` |
| `listProjects` | `list-projects` |
| `showProjectDetails` | `show-project-details` |
| `createUserAccount` | `create-user-account` |

Ví dụ:

```java
@ShellComponent
public class ProjectCommands {

    @ShellMethod("Liệt kê các project")
    public String listProjects() {
        return "Danh sách project";
    }
}
```

Người dùng gọi command bằng:

```text
list-projects
```

Cách suy ra tên phù hợp với command đơn giản và tên phương thức Java đã mô tả đúng hành động. Tuy nhiên, tên phương thức là một phần của mã nguồn; đổi tên phương thức có thể làm thay đổi tên command mà người dùng đang sử dụng. Với command đã được công bố cho người dùng hoặc script, nên cân nhắc khai báo key tường minh để giữ hợp đồng CLI ổn định.

### 2.2. Khai báo tên command bằng key

Thuộc tính `key` cho phép chỉ định tên command. Ví dụ:

```java
@ShellComponent
public class ProjectCommands {

    @ShellMethod(
        value = "Liệt kê các project",
        key = "project list"
    )
    public String listProjects() {
        return "Danh sách project";
    }
}
```

Người dùng gọi:

```text
project list
```

Tên command lúc này được xác định bởi `key`, thay vì dựa vào tên phương thức `listProjects`. Điều này giúp tên CLI thể hiện ngôn ngữ nghiệp vụ trong khi tên phương thức Java vẫn tuân theo quy ước đặt tên của Java.

Trong một lớp có nhiều command, hãy chọn tên nhất quán theo hành động và đối tượng, chẳng hạn `project list`, `project show`, `project create` và `project delete`. Nhóm từ đầu giúp người dùng dễ khám phá các thao tác cùng miền.

## 3. Mô tả command bằng value

Thuộc tính `value` của `@ShellMethod` là mô tả command. Mô tả được dùng trong trợ giúp để người dùng hiểu command thực hiện việc gì.

Có thể viết dạng rút gọn:

```java
@ShellMethod("Hiển thị thông tin project")
public String showProject() {
    return "Thông tin project";
}
```

Hoặc ghi rõ tên thuộc tính:

```java
@ShellMethod(
    value = "Hiển thị thông tin của một project",
    key = "project show"
)
public String showProject() {
    return "Thông tin project";
}
```

Hai cách trên tương đương về ý nghĩa: chuỗi được truyền vào `value` là mô tả, không phải tên command. Tên command trong ví dụ thứ hai đến từ `key`.

Một mô tả tốt nên trả lời ngắn gọn câu hỏi “command này làm gì?”. Ví dụ:

| Mô tả chưa rõ | Mô tả hữu ích hơn |
|---|---|
| `Project` | `Liệt kê các project hiện có` |
| `Run` | `Chạy tác vụ đồng bộ dữ liệu` |
| `Delete data` | `Xóa project theo mã định danh` |
| `Update` | `Cập nhật trạng thái của một project` |

Mô tả nên dùng động từ cụ thể, tránh lặp lại tên command mà không giải thích hành động. Với thao tác có tác động lớn, mô tả nên giúp người dùng nhận ra tác động chính; các điều kiện và tham số chi tiết có thể được giải thích thêm trong tài liệu trợ giúp của ứng dụng.

## 4. Tổ chức command bằng group

Thuộc tính `group` gán command vào một nhóm. Nhóm giúp phần trợ giúp phân loại các command theo chức năng hoặc miền nghiệp vụ, đặc biệt khi ứng dụng có nhiều command.

Ví dụ:

```java
@ShellComponent
public class ProjectCommands {

    @ShellMethod(
        value = "Liệt kê các project",
        key = "project list",
        group = "Project"
    )
    public String listProjects() {
        return "Danh sách project";
    }

    @ShellMethod(
        value = "Tạo project mới",
        key = "project create",
        group = "Project"
    )
    public String createProject() {
        return "Đã tạo project";
    }
}
```

Cả hai command được gán vào nhóm `Project`. Khi người dùng xem trợ giúp tổng quát, nhóm giúp họ nhận ra những command cùng chủ đề.

Có thể tổ chức nhóm theo miền nghiệp vụ:

| Nhóm | Command ví dụ |
|---|---|
| `Project` | `project list`, `project show`, `project create` |
| `User` | `user list`, `user disable` |
| `System` | `system status`, `system version` |
| `Maintenance` | `cache clear`, `data export` |

Nên dùng tên nhóm ngắn, nhất quán và đủ rộng để chứa các command liên quan. Tránh tạo một nhóm riêng cho từng command vì khi đó nhóm không còn giúp người dùng khám phá chức năng.

`group` chỉ là metadata phục vụ tổ chức và trợ giúp. Nó không tạo namespace cho command, không giới hạn quyền truy cập và không thay thế cơ chế phân quyền. Nếu hai command có cùng tên, việc đặt chúng ở hai group khác nhau không nên được xem là cách giải quyết xung đột tên. Hãy thiết kế command key duy nhất và kiểm soát quyền ở lớp nghiệp vụ hoặc bảo mật phù hợp.

## 5. Tên thay thế và nhiều command key

Trong mô hình legacy, thuộc tính `key` nhận một mảng chuỗi. Vì vậy, một phương thức có thể được gọi bằng nhiều command key. Đây là cách cung cấp tên thay thế (alias) cho cùng một thao tác.

Ví dụ:

```java
@ShellComponent
public class ProjectCommands {

    @ShellMethod(
        value = "Liệt kê các project",
        key = {"project list", "projects", "pl"},
        group = "Project"
    )
    public String listProjects() {
        return "Danh sách project";
    }
}
```

Các cách gọi sau cùng thực thi một phương thức:

```text
project list
projects
pl
```

Tất cả key trong mảng đều là tên được chấp nhận cho command. Chúng không tạo ra các phương thức hay luồng nghiệp vụ riêng. Khi người dùng gọi bất kỳ key nào, Spring Shell định tuyến đến cùng phương thức `listProjects`.

### 5.1. Khi nào nên dùng alias?

Alias hữu ích trong một số tình huống:

- **Tên ngắn:** cung cấp dạng rút gọn cho command thường dùng, ví dụ `pl` cho `project list`.
- **Tên quen thuộc:** hỗ trợ người dùng đã quen với tên command cũ.
- **Tương thích script:** giữ tên cũ trong giai đoạn chuyển đổi để script hiện hữu tiếp tục gọi được.
- **Từ đồng nghĩa có chủ đích:** cho phép một tên khác dễ nhớ hơn mà không nhân đôi logic.

Ví dụ giữ tương thích tên cũ:

```java
@ShellMethod(
    value = "Xuất dữ liệu project",
    key = {"project export", "export-projects"},
    group = "Project"
)
public String exportProjects() {
    return "Đã xuất dữ liệu project";
}
```

Trong giai đoạn chuyển đổi, tài liệu có thể hướng người dùng mới sang `project export`, trong khi script cũ vẫn gọi `export-projects`. Khi muốn loại bỏ alias cũ, cần xem xét các script và người dùng còn phụ thuộc vào nó.

### 5.2. Quy tắc thiết kế alias

Không nên tạo quá nhiều alias cho một command. Một danh sách dài gồm nhiều cách viết gần giống nhau làm trợ giúp khó đọc và tăng chi phí duy trì hợp đồng CLI.

Hãy áp dụng các nguyên tắc sau:

1. Giữ một tên dễ hiểu làm cách gọi chính trong tài liệu.
2. Chỉ thêm alias khi có nhu cầu sử dụng rõ ràng.
3. Dùng alias ngắn cho command phổ biến, nhưng tránh các chữ viết tắt khó đoán.
4. Không dùng cùng một key cho nhiều command.
5. Khi giữ alias cũ, ghi nhận lý do và kế hoạch duy trì hoặc loại bỏ.
6. Kiểm tra cả tên có nhiều từ và tên viết tắt trong shell thực tế.

Một điểm cần nhớ: khi khai báo `key`, hãy liệt kê đầy đủ những tên muốn hỗ trợ. Đừng mặc định tên suy ra từ phương thức vẫn tự động tồn tại như một alias bổ sung. Nếu muốn giữ cả tên suy ra lẫn tên mới, hãy đưa cả hai vào danh sách key và xác minh hành vi trên đúng phiên bản Spring Shell đang dùng.

## 6. Kết hợp tên, mô tả, group và alias

Một khai báo đầy đủ có thể đặt cả ba thuộc tính trong `@ShellMethod`:

```java
package com.example.projectcli.command;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class ProjectCommands {

    @ShellMethod(
        value = "Hiển thị thông tin của project",
        key = {"project show", "pshow"},
        group = "Project"
    )
    public String showProject() {
        return "Thông tin project";
    }

    @ShellMethod(
        value = "Liệt kê các project",
        key = {"project list", "projects", "pl"},
        group = "Project"
    )
    public String listProjects() {
        return "Danh sách project";
    }

    @ShellMethod(
        value = "Tạo project mới",
        key = "project create",
        group = "Project"
    )
    public String createProject() {
        return "Đã tạo project";
    }
}
```

Có thể đọc metadata của từng command như sau:

| Phương thức Java | key được khai báo | value (mô tả) | group |
|---|---|---|---|
| `showProject` | `project show`, `pshow` | Hiển thị thông tin của project | `Project` |
| `listProjects` | `project list`, `projects`, `pl` | Liệt kê các project | `Project` |
| `createProject` | `project create` | Tạo project mới | `Project` |

Nhìn vào metadata, người phát triển có thể phân biệt rõ:

- Tên phương thức là định danh trong mã Java.
- `key` là tên người dùng nhập để gọi command.
- `value` là mô tả hiển thị trong trợ giúp.
- `group` là nhãn phân loại command trong trợ giúp.
- Nhiều phần tử trong `key` cho phép nhiều cách gọi cùng một command.

Việc tách các vai trò này giúp đổi tên nội bộ phương thức mà vẫn giữ nguyên tên CLI khi key đã được khai báo tường minh.

## 7. Cách Spring Shell sử dụng metadata

Khi ứng dụng khởi động, Spring phát hiện lớp `@ShellComponent`. Spring Shell đọc các phương thức được đánh dấu `@ShellMethod`, lấy metadata và đăng ký command tương ứng.

Có thể mô tả luồng xử lý như sau:

```text
ApplicationContext khởi động
          |
          v
Phát hiện lớp @ShellComponent
          |
          v
Đọc các phương thức @ShellMethod
          |
          v
Thu thập key, value và group
          |
          v
Đăng ký command và các key được chấp nhận
          |
          v
Hiển thị metadata trong trợ giúp
          |
          v
Người dùng gọi một key
          |
          v
Spring Shell thực thi phương thức Java tương ứng
```

Metadata có hai tác động chính:

- **Khám phá command:** tên, mô tả và nhóm giúp người dùng biết command nào có sẵn và chúng phục vụ mục đích gì.
- **Định tuyến command:** key giúp Spring Shell xác định phương thức cần gọi khi người dùng nhập lệnh.

Mô tả và group không quyết định logic thực thi. Alias cũng không thay đổi kết quả nghiệp vụ; chúng chỉ cung cấp thêm cách định tuyến đến cùng command.

## 8. Các lỗi khai báo thường gặp

**Nhầm value là tên command.** Trong `@ShellMethod`, `value` dùng cho mô tả. Nếu cần đặt tên CLI tường minh, hãy dùng `key`.

**Cho rằng tên command luôn bằng tên phương thức.** Khi có `key`, các key được khai báo quyết định cách gọi command. Khi không có key, Spring Shell mới suy ra tên từ phương thức theo quy tắc của phiên bản.

**Đổi tên phương thức làm thay đổi CLI ngoài dự kiến.** Nếu tên command được suy ra, đổi tên phương thức có thể làm thay đổi giao diện người dùng. Với command cần ổn định, khai báo key tường minh và kiểm thử các cách gọi.

**Dùng alias trùng nhau.** Một key nên định tuyến đến một command duy nhất. Tránh để nhiều phương thức cùng khai báo một key hoặc dùng alias quá chung như `list`, `show` khi ứng dụng có nhiều miền nghiệp vụ.

**Đặt group như thể đó là namespace.** Group chỉ hỗ trợ phân loại và hiển thị trợ giúp. Tên command vẫn cần được thiết kế rõ ràng và không xung đột.

**Mô tả quá chung chung.** Chuỗi như `Run command` hoặc `Project` không cho người dùng biết tác động. Dùng động từ cụ thể và mô tả đối tượng thao tác.

**Khai báo quá nhiều alias.** Alias dư thừa khiến giao diện khó học và khó duy trì. Chỉ giữ tên thay thế có người dùng hoặc hệ thống thực sự cần.

**Trộn API legacy với API của dòng mới.** `@ShellMethod` thuộc mô hình annotation legacy; các dòng Spring Shell mới có thể dùng mô hình `@Command` với thuộc tính khác. Không chuyển nguyên `value`, `key`, `group` sang annotation mới theo suy đoán. Hãy đối chiếu tài liệu và package của dependency đang dùng.

## 9. Checklist khi khai báo metadata command

- [ ] Lớp chứa command được đánh dấu `@ShellComponent`.
- [ ] Mỗi phương thức command được đánh dấu `@ShellMethod`.
- [ ] Tên command được suy ra có chủ đích hoặc được khai báo rõ bằng `key`.
- [ ] `value` mô tả đúng hành động và tác động chính.
- [ ] `group` được dùng nhất quán để người dùng dễ khám phá.
- [ ] Các alias đều có mục đích sử dụng rõ ràng.
- [ ] Không có key trùng giữa các command.
- [ ] Các tên được tài liệu hoặc script sử dụng đều đã được kiểm tra trong shell.
- [ ] API và package annotation khớp với phiên bản Spring Shell của dự án.

Trong mô hình legacy, `@ShellMethod` là nơi công bố hợp đồng cơ bản của một command: người dùng gọi bằng tên nào, trợ giúp mô tả điều gì và command nằm trong nhóm nào. Hãy xem các key như giao diện công khai của CLI. Khi đặt tên ổn định, viết mô tả rõ và dùng group cùng alias có chủ đích, ứng dụng sẽ dễ học, dễ tự động hóa và dễ duy trì khi mã nguồn tiếp tục thay đổi.

