# Quy tắc xử lý tên trùng hoặc tiền tố gây nhập nhằng

Khi ứng dụng Spring Shell có nhiều command, việc đặt tên cần được quản lý như một phần của thiết kế giao diện dòng lệnh. Hai command dùng cùng một tên, một alias trùng với tên command khác, hoặc một command cha đồng thời là đường dẫn của command con có thể khiến người dùng khó biết lệnh nào sẽ được gọi. Các tên gần giống nhau cũng làm giảm khả năng khám phá command qua trợ giúp và tự hoàn thành.

Spring Shell biểu diễn command bằng một đường dẫn gồm một hoặc nhiều từ. Ví dụ, `user create` là một command có hai thành phần tên; `user delete` là một command khác cùng nhóm từ đầu. Việc hai command chia sẻ một từ đầu không tự động có nghĩa là chúng trùng nhau. Điều cần kiểm soát là toàn bộ đường dẫn command, alias, quan hệ cha-con và cách người dùng phân biệt các lựa chọn.

Bài học này trình bày các dạng xung đột tên thường gặp, cách Spring Shell tổ chức command path, những giới hạn cần lưu ý giữa các phiên bản, cách thiết kế tên và alias, cũng như quy trình kiểm tra trước khi phát hành command.

## 1. Phân biệt tên command, alias, nhóm và tiền tố

Trước khi xử lý xung đột, cần phân biệt các thành phần có thể cùng xuất hiện trong cấu hình.

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Tên command | Đường dẫn chính để gọi command | `user create` |
| Alias | Tên thay thế cho cùng một command | `user new` |
| Từ đầu của command path | Thành phần đầu trong đường dẫn nhiều từ | `user` trong `user create` |
| Subcommand | Thành phần tiếp theo trong command path | `create` trong `user create` |
| Group | Nhóm hiển thị trong trợ giúp | `User Management` |
| Option | Tham số có tên sau command | `--email`, `-e` |

Ví dụ, hai command sau có chung từ đầu nhưng có đường dẫn khác nhau:

~~~text
user create
user delete
~~~

Chúng là hai command riêng biệt. Từ `user` giúp người dùng nhận ra nhóm chức năng, còn từ tiếp theo xác định hành động cụ thể.

Ngược lại, hai khai báo cùng tạo ra đường dẫn `user create` là xung đột tên chính. Tình huống tương tự xảy ra nếu command thứ nhất có alias `user new`, trong khi command thứ hai dùng `user new` làm tên chính.

Một group chỉ dùng để phân loại command trong trợ giúp không nhất thiết là một phần của tên command. Cần xem API đang sử dụng để biết một thuộc tính có thay đổi command path hay chỉ thay đổi cách hiển thị.

## 2. Cách Spring Shell hiểu command path

Spring Shell xem tên command là một chuỗi từ được phân tách bởi khoảng trắng. Trong mô hình đăng ký programmatic của Spring Shell 3.x, có thể truyền các thành phần tên riêng biệt vào builder:

~~~java
CommandRegistration registration = CommandRegistration.builder()
        .command("user", "create")
        .build();
~~~

Cách viết trên mô tả command path `user create`. Trong mô hình annotation mới của Spring Shell 3.1.x, `@Command` có thể đặt ở cấp lớp để khai báo tiền tố dùng chung, sau đó method khai báo phần còn lại:

~~~java
import org.springframework.shell.command.annotation.Command;

@Command(command = "user")
class UserCommands {

    @Command(command = "create")
    String create() {
        return "User created";
    }

    @Command(command = "delete")
    String delete() {
        return "User deleted";
    }
}
~~~

Hai method tạo ra các command `user create` và `user delete`.

Trong ứng dụng Spring Boot, cần bật đăng ký command target bằng `@CommandScan` trên lớp cấu hình/khởi động hoặc dùng `@EnableCommand` để chỉ định lớp command. Ví dụ:

~~~java
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
~~~

Với mô hình annotation cũ, `@ShellMethod(key = ...)` xác định tên command trực tiếp. Thuộc tính `key` có thể nhận nhiều giá trị để đăng ký các alias cho cùng một method:

~~~java
@ShellComponent
public class UserCommands {

    @ShellMethod(
        value = "Create a user.",
        key = {"user create", "user new"}
    )
    public String createUser() {
        return "User created";
    }
}
~~~

Trong ví dụ này, `user create` là tên chính theo quy ước của ứng dụng và `user new` là alias. Cả hai đều gọi cùng một method.

### 2.1. Parser xử lý đường dẫn và phần tham số

Về mặt cú pháp, command line có cấu trúc khái quát:

~~~text
CommandName [SubCommandName]* [Option | Argument]*
~~~

Ví dụ:

~~~text
user create --email linh@example.com --active true
~~~

Phần `user create` xác định command path. Các token còn lại được phân tích thành option hoặc argument theo metadata của command.

Không nên dựa vào việc người dùng nhập một phần tên như `user cr` rồi mong shell tự suy ra `user create`. Thiết kế command nên dùng đường dẫn đầy đủ; completion có thể giúp người dùng khám phá và chọn phần còn lại. Cơ chế gợi ý không nên bị hiểu nhầm là quy tắc phân giải tên thay thế.

### 2.2. Tiền tố giống nhau không đồng nghĩa với tên trùng

Các ví dụ sau có chung một từ đầu nhưng là các đường dẫn khác nhau:

~~~text
project list
project lock
project log
~~~

Người dùng vẫn có thể phân biệt bằng từ thứ hai. Tuy nhiên, nếu có nhiều command với tên gần giống, cần mô tả rõ và giữ cách đặt tên nhất quán.

Các trường hợp sau dễ gây nhầm hơn:

~~~text
project user
project users
project user-group
~~~

Dù các chuỗi khác nhau, người dùng có thể gõ nhầm hoặc khó nhớ. Nên chọn một quy ước số ít/số nhiều, dấu gạch nối và cách đặt tên hành động thống nhất trong toàn ứng dụng.

## 3. Các dạng xung đột cần phát hiện

### 3.1. Trùng toàn bộ tên command

Hai thành phần cùng đăng ký `user create` là xung đột trực tiếp:

~~~java
@ShellMethod(key = "user create")
public String createUser() {
    return "Created by UserCommands";
}
~~~

~~~java
@ShellMethod(key = "user create")
public String createUserFromAdmin() {
    return "Created by AdminCommands";
}
~~~

Người dùng không có cách rõ ràng để chọn implementation mong muốn vì cả hai cùng công bố một đường dẫn. Điều này có thể phát sinh khi command được khai báo ở nhiều lớp, nhiều module hoặc được đăng ký qua cả annotation lẫn code.

Không nên dựa vào giả định rằng registration sau sẽ luôn ghi đè registration trước, hoặc một nguồn đăng ký sẽ luôn được ưu tiên. Nếu tài liệu của phiên bản không cam kết thứ tự giải quyết xung đột, đó không phải hợp đồng ổn định để ứng dụng dựa vào.

**Quy tắc:** mỗi command path chỉ có một chủ sở hữu trong một cấu hình shell đang chạy.

### 3.2. Alias trùng tên command khác

Một alias cũng là một tên có thể gọi được. Vì vậy, alias phải tham gia vào kiểm tra trùng tên giống như tên chính.

Ví dụ:

| Command | Tên chính | Alias |
|---|---|---|
| Tạo người dùng | `user create` | `user new` |
| Tạo nhóm | `group create` | `user new` |

Ở đây, `user new` vừa là alias của command thứ nhất vừa là tên thay thế được khai báo cho command thứ hai. Người dùng không thể biết ý nghĩa nào sẽ được thực thi.

Khi thiết kế alias, cần kiểm tra va chạm với:

- Tên chính của mọi command.
- Alias của các command khác.
- Command tích hợp của Spring Shell.
- Command được thêm động trong lúc ứng dụng chạy.

Alias nên ngắn, dễ nhớ và có cùng ý nghĩa với tên chính. Tránh tạo alias chỉ vì muốn tận dụng một từ phổ biến đã được dùng ở nơi khác.

### 3.3. Xung đột giữa command cha và command con

Một đường dẫn có thể được mở rộng thành command nhiều cấp. Tuy nhiên, không phải mọi tổ hợp cha-con đều có thể cùng đăng ký.

Ví dụ về cấu trúc dễ gây xung đột:

~~~text
project user
project user detail
~~~

Nếu `project user` vừa là một command thực thi hoàn chỉnh vừa được dùng làm tiền tố của `project user detail`, shell phải phân biệt liệu người dùng muốn gọi command cha hay tiếp tục nhập command con.

Tài liệu đăng ký command của Spring Shell 3.4 ghi rõ một giới hạn: không thể đồng thời đăng ký `command1 sub1` và `command1 sub1 subsub1` như hai command trong cấu trúc được mô tả. Cần kiểm tra lại tài liệu của đúng phiên bản Spring Shell mà dự án sử dụng trước khi thiết kế đường dẫn cha-con.

Cách tổ chức an toàn là để command ở các nhánh cuối cùng thực hiện hành động:

~~~text
project user list
project user show
project user create
project user delete
~~~

Nếu cần một hành động riêng ở cấp cha, hãy chọn tên hành động cụ thể:

~~~text
project user overview
project user list
project user show
~~~

Không đăng ký một command thực thi ở một nút đồng thời được dùng làm nút cha cho các command sâu hơn nếu phiên bản đang dùng không hỗ trợ cấu trúc đó.

### 3.4. Xung đột do tiền tố được thêm ở cấp lớp

Một tiền tố khai báo ở cấp lớp có thể được áp dụng cho nhiều method. Khi nhiều lớp cùng khai báo một tiền tố, cần kiểm tra toàn bộ tên sau khi ghép.

Ví dụ:

~~~java
@Command(command = "user")
class UserCommands {

    @Command(command = "create")
    String create() {
        return "User created";
    }
}
~~~

~~~java
@Command(command = "user")
class AdminUserCommands {

    @Command(command = "create")
    String createAsAdmin() {
        return "Admin user created";
    }
}
~~~

Cả hai method đều tạo đường dẫn `user create`. Việc tách lớp Java không làm cho tên command trở nên khác nhau.

Nên chia prefix theo miền chức năng hoặc đổi tên nhánh:

~~~text
user create
admin user create
~~~

Một lớp có thể chứa nhiều command liên quan, nhưng prefix của nó phải được xem như một phần của hợp đồng tên command.

### 3.5. Xung đột do tên option

Tên command có thể không trùng nhưng các option vẫn có thể khiến cách gọi khó hiểu. Ví dụ, hai option có cùng short name `-f` nhưng mang ý nghĩa khác nhau trong các command thường được sử dụng liền kề.

Trong một command, mỗi option cần có tên rõ ràng và alias ngắn không xung đột với option khác. Giữa các command, nên duy trì ý nghĩa nhất quán cho các option dùng chung:

| Ý nghĩa | Tên dài đề xuất | Tên ngắn đề xuất |
|---|---|---|
| Đường dẫn file | `--file` | `-f` |
| Định dạng output | `--format` | `-o` |
| Môi trường triển khai | `--environment` | `-e` |
| Hiển thị chi tiết | `--verbose` | `-v` |

Đây là quy ước của ứng dụng, không phải một bộ tên bắt buộc toàn cục của Spring Shell. Điều quan trọng là một short option không được mang các ý nghĩa trái ngược trong cùng một command và cần được mô tả nhất quán giữa các command có liên quan.

## 4. Phân biệt command prefix với group và option prefix

Từ “prefix” có thể chỉ nhiều khái niệm khác nhau. Nhầm lẫn giữa chúng khiến người phát triển tưởng rằng đã đổi nhóm hiển thị nhưng thực tế tên command không đổi, hoặc ngược lại.

### 4.1. Prefix của command

Prefix command là một phần của đường dẫn gọi lệnh. Ví dụ `user` trong `user create`.

Trong annotation mới của Spring Shell 3.1.x, có thể dùng `@Command(command = "user")` ở cấp lớp để các method con kế thừa phần đầu của tên command.

Trong Spring Shell 4.x, `@CommandGroup` có thuộc tính `prefix` để cung cấp tiền tố dùng chung cho các command trong group. Cách cấu hình cụ thể khác nhau theo thế hệ API.

### 4.2. Group chỉ tổ chức trợ giúp

Group giúp gom các command liên quan khi hiển thị danh sách trợ giúp. Ví dụ, group `User Management` có thể chứa `user create`, `user list` và `user delete`.

Tên group không tự động trở thành command path. Trong Spring Shell 3.1 legacy annotation, `@ShellCommandGroup` là cách phân loại command trong trợ giúp, còn `@ShellMethod(key = ...)` xác định tên gọi.

### 4.3. Prefix của option

Trong mô hình legacy, thuộc tính `prefix` của `@ShellMethod` liên quan đến cách đặt tiền tố cho tham số được ánh xạ theo tên. Nó không phải tiền tố nhóm command.

Ví dụ, option thường dùng dạng `--email` hoặc `-e`. Thay đổi cách đặt tiền tố option không làm thay đổi command path `user create`.

| Cấu hình | Ảnh hưởng |
|---|---|
| Command path / prefix ở cấp lớp | Thay đổi tên gọi command |
| Alias / key bổ sung | Tạo thêm tên gọi cho cùng command |
| Group | Thay đổi cách phân nhóm trong trợ giúp |
| Option prefix | Thay đổi cách nhận diện option |
| Short/long option name | Thay đổi tên tham số của command |

## 5. Quy tắc đặt tên để tránh nhập nhằng

Một bộ quy tắc đơn giản có thể ngăn phần lớn xung đột trước khi command được đăng ký.

### 5.1. Dùng cấu trúc động từ và đối tượng nhất quán

Ưu tiên tên mô tả hành động:

~~~text
user create
user list
user show
user update
user delete
~~~

Không trộn nhiều kiểu đặt tên cho cùng một miền:

~~~text
user-create
list-users
user show
deleteUser
~~~

Các tên này có thể đều hợp lệ về mặt cú pháp, nhưng khiến người dùng phải học nhiều quy ước khác nhau. Chọn một kiểu như `resource action` hoặc `action resource` và áp dụng xuyên suốt.

### 5.2. Dùng từ cụ thể ở vị trí phân biệt

Các từ quá chung như `run`, `do`, `process`, `manage` làm command khó hiểu khi đứng riêng. Hãy thêm ngữ cảnh:

| Tên quá chung | Tên rõ nghĩa hơn |
|---|---|
| `data run` | `data import` |
| `user process` | `user deactivate` |
| `project manage` | `project archive` |
| `report do` | `report export` |

### 5.3. Tránh tên gần giống nhưng khác rất ít

Các cặp như `user show` và `user shows`, `config set` và `config setup`, hoặc `service start` và `service status` có thể khiến người dùng gõ nhầm.

Nếu hai hành động khác nhau về nghiệp vụ, hãy chọn các động từ dễ phân biệt và mô tả rõ trong trợ giúp.

### 5.4. Thống nhất số ít, số nhiều và dấu phân cách

Chọn một quy tắc cho tên resource:

- `user list`, `user show`, `user create` dùng resource ở dạng số ít.
- Hoặc `users list`, `users show`, `users create` nếu ứng dụng đã chọn dạng số nhiều.

Không trộn `user list` với `users create` nếu không có lý do.

Với tên nhiều từ, chọn cách viết nhất quán như `access-token rotate` hoặc `access token rotate`. Hãy cân nhắc khả năng gõ, completion, script và tài liệu hướng dẫn.

### 5.5. Không dùng alias quá ngắn hoặc quá phổ biến

Alias như `ls`, `rm`, `go`, `new` có thể dễ nhớ nhưng cũng dễ đụng với command tích hợp hoặc command của module khác. Alias chỉ nên được thêm khi nó thực sự giúp người dùng thao tác nhanh hơn.

Nếu alias được giữ để tương thích với phiên bản cũ, cần ghi rõ alias nào đang được duy trì và thời điểm dự kiến loại bỏ.

## 6. Ví dụ tổ chức command không xung đột

Giả sử CLI quản lý người dùng, nhóm và quyền truy cập. Có thể thiết kế command path như sau:

~~~text
user list
user show
user create
user update
user delete

group list
group show
group create
group add-member
group remove-member

access grant
access revoke
access list
~~~

Các command chia sẻ một từ đầu nhưng có nhánh phân biệt rõ ràng. Tên command không trùng và không dùng một command executable làm prefix cho một command sâu hơn.

### 6.1. Ví dụ legacy annotation

~~~java
@ShellComponent
public class UserCommands {

    @ShellMethod(
        value = "Create a user.",
        key = {"user create", "user new"}
    )
    public String createUser(
            @ShellOption(value = "--name") String name) {
        return "Created user " + name;
    }

    @ShellMethod(
        value = "List users.",
        key = "user list"
    )
    public String listUsers() {
        return "User list";
    }

    @ShellMethod(
        value = "Delete a user.",
        key = "user delete"
    )
    public String deleteUser(
            @ShellOption(value = "--id") long id) {
        return "Deleted user " + id;
    }
}
~~~

Ở đây, `user new` là alias của `user create`. Không được khai báo `user new` như một command khác trong lớp hoặc module khác.

### 6.2. Ví dụ annotation mới trong Spring Shell 3.1.x

~~~java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;

@Command(command = "user")
class UserCommands {

    @Command(command = "create")
    String create(
            @Option(longNames = "name") String name) {
        return "Created user " + name;
    }

    @Command(command = "list")
    String list() {
        return "User list";
    }

    @Command(command = "delete")
    String delete(
            @Option(longNames = "id") long id) {
        return "Deleted user " + id;
    }
}
~~~

Prefix `user` được áp dụng cho các command method trong lớp, tạo thành các đường dẫn `user create`, `user list` và `user delete`.

Nếu một lớp khác cũng khai báo prefix `user`, cần kiểm tra các method của lớp đó để bảo đảm không tạo lại những đường dẫn đã tồn tại.

### 6.3. Ví dụ programmatic registration

~~~java
CommandRegistration createUser = CommandRegistration.builder()
        .command("user", "create")
        .description("Create a user")
        .withTarget()
            .function(context -> "User created")
            .and()
        .build();

CommandRegistration listUsers = CommandRegistration.builder()
        .command("user", "list")
        .description("List users")
        .withTarget()
            .function(context -> "User list")
            .and()
        .build();
~~~

Khi đăng ký command bằng code, cần kiểm tra tên của registration trước khi đưa vào catalog. Nếu command được tạo từ nhiều module, nên tập trung việc đặt tên và đăng ký ở một lớp cấu hình hoặc một thành phần quản lý catalog.

## 7. Cách xử lý khi phát hiện xung đột

Khi hai command có tên hoặc alias xung đột, hãy xử lý theo trình tự sau:

1. Xác định nguồn tạo ra từng registration: annotation, bean programmatic, customizer, resolver hay đăng ký động.
2. Xác định tên chính, alias và prefix sau khi đã ghép đầy đủ.
3. Xác định command nào là chủ sở hữu của hành động nghiệp vụ.
4. Chọn một tên chính duy nhất.
5. Đổi tên command còn lại hoặc chuyển nó sang một nhánh chức năng khác.
6. Nếu cần tương thích, chỉ giữ alias khi alias đó chưa được sử dụng ở nơi khác.
7. Cập nhật trợ giúp, completion, script và tài liệu sử dụng.
8. Kiểm thử cả tên chính và alias sau khi thay đổi.

Không nên giải quyết xung đột bằng cách chỉ đổi tên class Java. Tên class không quyết định command path khi annotation hoặc builder đã khai báo một tên cụ thể.

### 7.1. Ví dụ đổi tên command trùng

Trước khi sửa:

~~~text
user create
user create
~~~

Sau khi phân chia trách nhiệm:

~~~text
user create
admin user create
~~~

Command thứ nhất phục vụ người dùng thông thường. Command thứ hai phục vụ thao tác quản trị. Service vẫn phải kiểm tra quyền quản trị khi thực thi.

### 7.2. Ví dụ xử lý alias trùng

Trước khi sửa:

~~~text
user create  alias: user new
group create alias: user new
~~~

Sau khi sửa:

~~~text
user create   alias: user new
group create  alias: group new
~~~

Alias mới phải phản ánh cùng miền nghiệp vụ với command chính.

### 7.3. Khi cần giữ tên cũ

Nếu một command được đổi tên nhưng người dùng đã có script sử dụng tên cũ, có thể giữ tên cũ như alias trong một giai đoạn chuyển tiếp:

~~~text
Tên chính: user create
Alias tương thích: user add
~~~

Cần thông báo alias cũ sẽ được duy trì trong bao lâu. Khi loại bỏ alias, hãy kiểm tra script, tài liệu và các automation nội bộ đang sử dụng tên đó.

## 8. Giảm nhập nhằng giữa command và tham số

Không phải mọi trường hợp khó phân tích đều xuất phát từ command path. Một số xung đột xuất hiện do option và positional argument.

Ví dụ:

~~~text
report export json
~~~

Token `json` có thể được hiểu là positional argument. Nếu command có nhiều tham số vị trí, người dùng khó biết token đó đang đại diện cho định dạng, tên file hay một giá trị khác.

Nên ưu tiên option có tên:

~~~text
report export --format json --file report.json
~~~

Spring Shell hỗ trợ option dạng dài như `--format=json` hoặc `--format json`, cùng option dạng ngắn theo cấu hình. Dùng tên option giúp lời gọi rõ nghĩa và giảm việc phải suy luận dựa trên vị trí token.

Với command nhiều cấp, càng nên tránh sử dụng nhiều positional argument không có mô tả rõ. Cần khai báo arity, kiểu dữ liệu và giá trị mặc định phù hợp.

### 8.1. Quote giá trị chứa khoảng trắng

Token command được phân tách theo khoảng trắng. Nếu giá trị option hoặc argument chứa khoảng trắng, hãy đặt trong dấu nháy theo quy tắc parser của phiên bản đang sử dụng:

~~~text
user create --display-name "Nguyen Van An"
~~~

Không dùng tên command có khoảng trắng tùy tiện ở giữa một token. Khoảng trắng trong command path có ý nghĩa phân tách các thành phần tên.

## 9. Kiểm tra xung đột bằng trợ giúp và completion

Sau khi đăng ký command, cần kiểm tra từ góc nhìn người dùng.

### 9.1. Dùng help để xem toàn bộ tên command

~~~text
shell:> help
~~~

Kiểm tra:

- Có hai dòng command trùng tên không?
- Alias có hiển thị ở đúng command không?
- Các command liên quan có được nhóm hợp lý không?
- Mô tả có đủ khác biệt để người dùng chọn đúng không?
- Có command cũ hoặc command thử nghiệm không nên công bố không?

Có thể dùng `help user create` để xem thông tin chi tiết của command:

~~~text
shell:> help user create
~~~

Đối với command nhiều từ, hãy sử dụng đầy đủ command path khi yêu cầu trợ giúp.

### 9.2. Dùng tab completion để khám phá nhánh

Completion giúp người dùng thấy các lựa chọn có thể nhập tại vị trí hiện tại. Hãy thử hoàn thành sau mỗi cấp:

~~~text
shell:> user <TAB>
shell:> user cr<TAB>
~~~

Kết quả gợi ý có thể thay đổi theo cấu hình và phiên bản. Nếu nhiều command có tên gần giống, hãy xem completion có cung cấp đủ ngữ cảnh để người dùng phân biệt không.

Completion chỉ là hỗ trợ nhập liệu. Không nên dựa vào completion để che giấu một thiết kế tên command trùng hoặc khó hiểu.

### 9.3. Kiểm tra command tích hợp

Spring Shell có các command tích hợp như `help`, `history`, `clear`, `quit`, `exit`, `version` và `script` tùy cấu hình. Trước khi đặt tên command ứng dụng, cần xem danh sách command hiện có để tránh ghi đè hoặc làm thay đổi trải nghiệm của command tích hợp.

Nếu ứng dụng có chủ đích thay thế command tích hợp, cần xác định rõ hành vi mong muốn và kiểm thử riêng. Không dùng tên phổ biến như `help` hoặc `exit` cho nghiệp vụ thông thường.

## 10. Kiểm thử quy tắc tên command

Kiểm thử nên bao gồm kiểm tra cấu hình và kiểm thử lời gọi thật. Một danh sách tên được kiểm tra bằng mắt thường không đủ khi command đến từ nhiều module.

### 10.1. Kiểm tra danh mục sau khi khởi động

Với mô hình programmatic, có thể lấy các registration từ `CommandCatalog` để kiểm tra tên chính đã đăng ký. Nếu có alias, cần đưa cả alias vào cùng một tập tên dùng để phát hiện trùng.

Có thể tổ chức một kiểm tra theo nguyên tắc:

~~~java
import java.util.HashSet;
import java.util.Set;
import org.springframework.shell.command.CommandAlias;
import org.springframework.shell.command.CommandRegistration;

Set<String> registeredNames = new HashSet<>();

for (CommandRegistration registration : commandCatalog.getRegistrations().values()) {
    String commandName = registration.getCommand();

    if (!registeredNames.add(commandName)) {
        throw new IllegalStateException(
                "Duplicate command name: " + commandName);
    }

    for (CommandAlias alias : registration.getAliases()) {
        String aliasName = alias.getCommand();
        if (!registeredNames.add(aliasName)) {
            throw new IllegalStateException(
                    "Duplicate command name or alias: " + aliasName);
        }
    }
}
~~~

Đoạn mã kiểm tra tên chính và alias trong snapshot catalog hiện tại. Vì snapshot chỉ phản ánh các registration đang có, nên để phát hiện cả hai registration trùng tên trước khi một registration khác có thể thay thế hoặc che khuất nó, hãy kiểm tra danh sách registration đầu vào ở một đầu mối quản lý trước khi gọi `register(...)`. Có thể áp dụng thêm quy tắc chuẩn hóa tên của dự án, nhưng không nên tự giả định Spring Shell sẽ xử lý tên hoa/thường hoặc khoảng trắng theo quy tắc riêng của ứng dụng.

### 10.2. Kiểm thử command path và alias

Với mỗi command, nên có các trường hợp:

- Tên chính gọi đúng target.
- Alias gọi đúng cùng target.
- Tên gần giống nhưng không được đăng ký phải không gọi nhầm command khác.
- Command có prefix chung vẫn phân biệt được ở token tiếp theo.
- Command cha và command con không tạo cấu trúc mà phiên bản Spring Shell không hỗ trợ.
- Command tích hợp vẫn hoạt động đúng.
- Trợ giúp hiển thị đúng tên và mô tả.

### 10.3. Kiểm thử khi có nhiều nguồn đăng ký

Nếu ứng dụng sử dụng annotation, bean `CommandRegistration`, `CommandCatalogCustomizer`, `CommandResolver` hoặc đăng ký động, hãy kiểm tra danh sách sau khi tất cả nguồn đã được áp dụng.

Đặc biệt kiểm tra khi:

- Một module mới được bật.
- Plugin được nạp hoặc gỡ.
- Một alias cũ được thêm để tương thích.
- Một command được chuyển từ annotation sang programmatic registration.
- Cấu hình môi trường làm thay đổi tập command.

Không nên chỉ kiểm tra từng lớp command riêng lẻ vì xung đột có thể chỉ xuất hiện khi các module cùng được khởi tạo.

## 11. Checklist thiết kế tên command

- [ ] Mỗi command có một đường dẫn chính duy nhất.
- [ ] Alias không trùng với tên chính hoặc alias của command khác.
- [ ] Các tiền tố cấp lớp đã được ghép thành command path đầy đủ để kiểm tra.
- [ ] Không đăng ký command cha và command con theo cấu trúc mà phiên bản hiện tại không hỗ trợ.
- [ ] Các command có chung từ đầu vẫn có từ tiếp theo đủ rõ nghĩa.
- [ ] Tên command tuân theo một quy tắc về động từ, resource, số ít/số nhiều và dấu phân cách.
- [ ] Group trợ giúp được phân biệt với command prefix.
- [ ] Option có tên rõ ràng; hạn chế positional argument gây khó phân biệt.
- [ ] Alias cũ có mục đích tương thích và kế hoạch loại bỏ.
- [ ] Không vô tình chiếm tên command tích hợp.
- [ ] Help và completion giúp người dùng tìm đúng command.
- [ ] Kiểm thử toàn bộ registration sau khi các module đã được nạp.

## 12. Kết luận

Xung đột command trong Spring Shell cần được xem xét trên toàn bộ đường dẫn gọi lệnh, bao gồm tên chính, alias và tiền tố được thêm từ cấp lớp hoặc cấu hình. Hai command có chung một từ đầu chưa chắc trùng nhau, nhưng cùng một đường dẫn đầy đủ hoặc alias va chạm sẽ khiến giao diện dòng lệnh khó dự đoán.

Thiết kế ổn định cần một chủ sở hữu cho mỗi command path, alias có ý nghĩa và duy nhất, cấu trúc cha-con phù hợp với giới hạn của phiên bản, cùng quy ước nhất quán cho option và argument. Hãy dùng `help`, completion và kiểm thử danh mục sau khi khởi động để xác minh trải nghiệm thực tế.

## Tài liệu tham khảo

- [Spring Shell 3.1 Reference: Commands and Registration](https://docs.spring.io/spring-shell/docs/3.1.0/docs/index.html)
- [Spring Shell 3.1 Reference: Organizing Commands](https://docs.spring.io/spring-shell/docs/3.1.0/docs/index.html)
- [Spring Shell 3.1 API: `@Command`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/annotation/Command.html)
- [Spring Shell 3.1 API: `CommandCatalog`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandCatalog.html)
- [Spring Shell 3.1 API: `CommandAlias`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandAlias.html)
- [Spring Shell 3.4 Reference: Command Registration](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/registration.html)
- [Spring Shell 4.0.3 Reference: Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell 4.0.2 Reference: Organizing Commands](https://docs.spring.io/spring-shell/reference/commands/organize.html)

