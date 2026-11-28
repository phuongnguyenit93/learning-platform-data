# Trợ giúp một lệnh với cú pháp, tham số và ví dụ

Một CLI dễ sử dụng cần tự giải thích cách gọi từng command. Người dùng phải biết tên lệnh, argument nào cần truyền, option nào bắt buộc, giá trị mặc định là gì và một ví dụ chạy thành công. Spring Shell cung cấp command `help` để liệt kê lệnh và xem hướng dẫn chi tiết; mỗi command cũng có thể khai báo mô tả và phần trợ giúp riêng.

Trong Spring Shell 4.x, có ba cách khám phá thông tin:

- Gõ `help` để xem danh sách command và mô tả ngắn.
- Gõ `help <command>` để xem cú pháp, tham số và metadata của command.
- Gõ `<command> --help` hoặc `<command> -h` để xem phần trợ giúp ngắn được khai báo cho command.

Bài học này hướng dẫn viết trợ giúp rõ ràng, khai báo metadata cho argument và option, thêm ví dụ sử dụng và kiểm tra kết quả ngay trong shell.

## 1. Ba mức trợ giúp trong Spring Shell

Mỗi mức trợ giúp trả lời một câu hỏi khác nhau:

| Cách gọi | Nội dung | Khi nên dùng |
|---|---|---|
| `help` | Danh sách command, nhóm lệnh và mô tả ngắn | Khi người dùng chưa biết ứng dụng hỗ trợ những gì |
| `help user create` | Tên command, synopsis, argument, option, kiểu dữ liệu, trạng thái bắt buộc và mô tả tham số | Khi người dùng biết lệnh nhưng chưa rõ cách truyền dữ liệu |
| `user create --help` hoặc `user create -h` | Chuỗi trợ giúp ngắn của command | Khi người dùng muốn xem nhanh hướng dẫn ngay tại lệnh đang định chạy |

Ví dụ kết quả danh sách:

~~~text
shell:> help

AVAILABLE COMMANDS

User Management
    user create: Create a user account
    user disable: Disable a user account

Built-In Commands
    help: Show help about available commands
    version: Show version information
~~~

Ví dụ xem chi tiết một lệnh:

~~~text
shell:> help user create

NAME
    user create - Create a user account

SYNOPSIS
    user create <username> --email String [--role String]

OPTIONS
    --email String
        Email address of the new user.
        [Mandatory]

    --role or -r String
        Role assigned to the user.
        [Optional, default = reader]
~~~

Nội dung thực tế phụ thuộc metadata command và phiên bản Spring Shell. Hãy xem ví dụ trên là hình dạng minh họa để hiểu cấu trúc, không phải output cố định của mọi ứng dụng.

## 2. Khai báo mô tả ngắn và trợ giúp riêng bằng @Command

Với command khai báo bằng annotation, hai thuộc tính quan trọng là:

- `description`: mô tả ngắn dùng trong danh sách command.
- `help`: nội dung hướng dẫn ngắn riêng của command, hiển thị khi gọi `<command> --help` hoặc `<command> -h`.

Ví dụ:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class UserCommands {

    @Command(
            name = "user list",
            description = "List user accounts",
            help = "List user accounts. Example: user list --status=active"
    )
    public String list() {
        return "Danh sách tài khoản";
    }
}
~~~

Khi gõ `help`, người dùng nhìn thấy mô tả `List user accounts`. Khi gõ `user list --help`, Spring Shell hiển thị chuỗi trợ giúp đã khai báo.

Hãy viết `description` như một câu ngắn nêu hành động và đối tượng. Phần `help` nên nói rõ cách dùng, các lưu ý quan trọng và một hoặc hai ví dụ có thể sao chép. Không lặp lại một đoạn dài ở cả hai thuộc tính.

## 3. Khai báo mô tả cho từng argument và option

`help <command>` có thể trình bày cú pháp và metadata tham số vì Spring Shell đọc thông tin từ annotation của method.

Với argument, dùng `@Argument`:

- `index` xác định vị trí, bắt đầu từ 0.
- `description` giải thích ý nghĩa của giá trị.
- `defaultValue` mô tả giá trị mặc định nếu người dùng bỏ qua argument.

Với option, dùng `@Option`:

- `longName` là tên dài, không gồm tiền tố `--`.
- `shortName` là ký tự tên ngắn, không gồm tiền tố `-`.
- `description` giải thích mục đích option.
- `required` đánh dấu option bắt buộc.
- `defaultValue` khai báo giá trị dùng khi người dùng không truyền option.

Ví dụ:

~~~java
@Command(name = "user create", description = "Create a user account")
public String create(
        @Argument(
                index = 0,
                description = "Login name of the new user"
        )
        String username,
        @Option(
                longName = "email",
                description = "Email address of the new user",
                required = true
        )
        String email,
        @Option(
                shortName = 'r',
                longName = "role",
                description = "Role assigned to the user",
                defaultValue = "reader"
        )
        String role) {
    return "Created " + username + " with role " + role;
}
~~~

Khi người dùng gọi `help user create`, Spring Shell có thể lấy các mô tả này để hiển thị argument và option. Nếu tham số không có description, trợ giúp sẽ ít hữu ích hơn; hãy mô tả bằng ngôn ngữ của người dùng CLI thay vì tên biến Java.

## 4. Ví dụ hoàn chỉnh: command tạo người dùng

Một command thực tế nên cung cấp đủ metadata để người dùng biết:

- Tên command và mục đích.
- Argument nào xác định tài khoản cần tạo.
- Option nào bắt buộc và option nào có mặc định.
- Cú pháp truyền giá trị.
- Một ví dụ đơn giản và một ví dụ có dùng option tùy chọn.

~~~java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class UserCommands {

    @Command(
            name = "user create",
            group = "User Management",
            description = "Create a user account",
            help = "Create a user account.\n"
                    + "Usage: user create <username> --email=<email> "
                    + "[--role=<role>]\n"
                    + "Example: user create linh --email=linh@example.com\n"
                    + "Example: user create minh --email=minh@example.com "
                    + "--role=admin"
    )
    public String create(
            @Argument(
                    index = 0,
                    description = "Login name of the new user"
            )
            String username,
            @Option(
                    longName = "email",
                    description = "Email address of the new user",
                    required = true
            )
            String email,
            @Option(
                    shortName = 'r',
                    longName = "role",
                    description = "Role assigned to the user",
                    defaultValue = "reader"
            )
            String role) {

        return "Created user " + username
                + " with email " + email
                + " and role " + role;
    }
}
~~~

Các cách gọi hợp lệ:

~~~text
user create linh --email=linh@example.com
user create minh --email=minh@example.com --role=admin
user create minh --email=minh@example.com -r=admin
~~~

Nếu bỏ `--role`, command dùng `reader`. Nếu bỏ `--email`, Spring Shell từ chối lời gọi vì option được đánh dấu bắt buộc. Phần trợ giúp nên phản ánh chính xác các quy tắc này.

## 5. Viết cú pháp Usage dễ đọc

Một dòng Usage thường kết hợp tên command, argument theo vị trí và option có tên. Có thể dùng quy ước ký hiệu sau trong phần trợ giúp:

| Ký hiệu | Ý nghĩa |
|---|---|
| `<username>` | Giá trị bắt buộc theo vị trí |
| `[--role=<role>]` | Option tùy chọn |
| `--email=<email>` | Option bắt buộc |
| `<source> <destination>` | Hai argument theo thứ tự |
| `--format=<csv\|json>` | Option nhận một trong các giá trị được liệt kê |

Ví dụ:

~~~text
Usage: report export <period> --output=<file> [--format=<csv|json>]
~~~

Đọc cú pháp như sau:

- Người dùng phải gọi command `report export`.
- Phải truyền argument `period`.
- Phải truyền option `--output`.
- Có thể bỏ qua `--format`; nếu không truyền, ứng dụng sẽ dùng mặc định đã khai báo.

Khi viết Usage thủ công trong thuộc tính `help`, hãy giữ nó đồng nhất với metadata `@Argument` và `@Option`. Nếu tên option hoặc trạng thái required thay đổi trong code, hãy cập nhật phần hướng dẫn và ví dụ cùng lúc.

## 6. Phân biệt description, help và metadata tham số

Ba nguồn thông tin bổ sung cho nhau:

| Nơi khai báo | Mục tiêu | Nội dung nên đặt |
|---|---|---|
| `@Command(description = ...)` | Giúp nhận diện command trong danh sách | Một câu ngắn mô tả hành động |
| `@Command(help = ...)` | Hướng dẫn ngắn khi gọi `-h` hoặc `--help` | Usage, lưu ý và ví dụ |
| `@Argument` / `@Option` | Mô tả cú pháp và từng tham số trong chi tiết command help | Ý nghĩa, kiểu, bắt buộc, mặc định |

Không dùng `description` để chứa toàn bộ tài liệu dài. Ngược lại, không nên để `help` chỉ lặp lại đúng một câu description mà không có cú pháp hay ví dụ.

## 7. Nhóm command để danh sách trợ giúp dễ tìm

Khi ứng dụng có nhiều command, đặt chúng vào nhóm chức năng giúp danh sách `help` dễ quét hơn. Với annotation, dùng thuộc tính `group`:

~~~java
@Command(
        name = "user disable",
        group = "User Management",
        description = "Disable a user account"
)
public String disable(
        @Argument(index = 0, description = "Login name") String username) {
    return "Disabled " + username;
}
~~~

Với command lập trình bằng code, có thể đặt nhóm qua `Command.Builder.group(String)`:

~~~java
@Bean
Command healthCommand() {
    return Command.builder()
            .name("system health")
            .group("System Operations")
            .description("Show system health")
            .execute(context ->
                    context.outputWriter().println("System is healthy."))
            .build();
}
~~~

Những command liên quan nên có tên nhóm nhất quán, ví dụ `User Management`, `System Operations` hoặc `Report Management`. Tránh tạo quá nhiều nhóm chỉ có một command nếu chúng không giúp người dùng định hướng.

## 8. Alias và command ẩn

`alias` cho phép cung cấp tên gọi thay thế. Alias nên ngắn, dễ nhớ và không làm thay đổi ý nghĩa của command:

~~~java
@Command(
        name = "user list",
        alias = "users",
        description = "List user accounts"
)
public String list() {
    return "Danh sách tài khoản";
}
~~~

Khi dùng alias, hãy ghi chúng trong tài liệu hướng dẫn nếu người dùng cần biết. Tên command chính vẫn nên xuất hiện rõ trong Usage.

Thuộc tính `hidden = true` loại command khỏi danh sách trợ giúp thông thường. Dùng nó cho lệnh nội bộ hoặc lệnh hỗ trợ vận hành mà người dùng phổ thông không cần khám phá. Command ẩn không phải cơ chế bảo mật; nếu người dùng biết tên và có quyền gọi, ứng dụng vẫn phải kiểm tra authorization trong service.

## 9. Trợ giúp cho command lập trình bằng Command.Builder

Nếu command được đăng ký bằng bean `Command`, có thể cung cấp mô tả, nhóm và help string bằng builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
class SystemCommands {

    @Bean
    Command statusCommand() {
        return Command.builder()
                .name("system status")
                .group("System Operations")
                .description("Show current system status")
                .help("Show current system status.\n"
                        + "Usage: system status\n"
                        + "Example: system status")
                .execute(context -> {
                    context.outputWriter().println("System is healthy.");
                })
                .build();
    }
}
~~~

Ở mô hình lập trình, `.description(...)` và `.help(...)` đóng vai trò tương ứng với thuộc tính cùng tên của `@Command`. Nếu command có tham số, hãy khai báo cả metadata argument và option trong builder để chi tiết help có thể mô tả cú pháp.

## 10. Quy trình kiểm tra trợ giúp trước khi phát hành

Với mỗi command, kiểm tra lần lượt:

1. Gõ `help` và xác nhận command xuất hiện trong nhóm phù hợp.
2. Kiểm tra description ngắn có giải thích đúng hành động không.
3. Gõ `help <command>` và xác nhận synopsis phản ánh argument, option và thứ tự.
4. Kiểm tra từng tham số có mô tả, kiểu, trạng thái required và default value chính xác.
5. Gõ `<command> --help` và `<command> -h` để xem nội dung help ngắn.
6. Sao chép từng ví dụ trong help và chạy thử với dữ liệu hợp lệ.
7. Thử bỏ option bắt buộc và bỏ option có mặc định để kiểm tra hướng dẫn khớp hành vi.
8. Kiểm tra alias và trạng thái hidden nếu command sử dụng các thuộc tính này.

Ví dụ với command tạo người dùng:

~~~text
help user create
user create --help
user create -h
user create linh --email=linh@example.com
~~~

Khi kiểm thử tự động, dùng `ShellTestClient` để gửi các command trợ giúp và xác nhận những phần quan trọng của output. Có thể kiểm tra tên command, option bắt buộc, mô tả và ví dụ. Nên kiểm tra nội dung có ý nghĩa thay vì so sánh toàn bộ output nếu template hoặc căn lề có thể thay đổi.

Ví dụ kiểm thử hai mức trợ giúp của command `user create`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellScreen;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@ContextConfiguration(classes = UserCommands.class)
class UserCommandsHelpTests {

    @Autowired
    ShellTestClient client;

    @Test
    void showsCommandSyntaxAndParameterDescriptions() throws Exception {
        ShellScreen screen = client.sendCommand("help user create");

        ShellAssertions.assertThat(screen)
                .containsText("user create")
                .containsText("--email")
                .containsText("Email address of the new user")
                .containsText("--role");
    }

    @Test
    void showsUsageAndExamplesFromCommandHelp() throws Exception {
        ShellScreen screen = client.sendCommand("user create --help");

        ShellAssertions.assertThat(screen)
                .containsText("Usage: user create")
                .containsText("Example: user create linh");
    }
}
~~~

Hai test xác nhận cả metadata tham số do Spring Shell dựng và nội dung ví dụ do ứng dụng cung cấp. Nếu ứng dụng dùng template trợ giúp riêng, hãy kiểm tra các phần thông tin quan trọng thay vì phụ thuộc vào khoảng trắng hoặc căn lề.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Command có trong ứng dụng nhưng không thấy trong `help` | Command bị đánh dấu hidden hoặc chưa được đăng ký | Kiểm tra `hidden` và cấu hình đăng ký command |
| Danh sách chỉ có tên command, thiếu mô tả | Chưa khai báo `description` | Thêm mô tả ngắn vào `@Command` hoặc builder |
| `help <command>` thiếu thông tin tham số | Thiếu metadata hoặc description trên argument/option | Khai báo `@Argument`, `@Option` và mô tả rõ ràng |
| Usage không khớp cách gọi thực tế | Chuỗi help được viết thủ công và chưa cập nhật sau khi đổi tham số | Đối chiếu Usage với metadata command |
| Ví dụ trong help chạy lỗi | Ví dụ dùng option sai tên, thiếu giá trị hoặc thiếu argument | Chạy thử từng ví dụ trước khi phát hành |
| `--help` không hiển thị nội dung mong muốn | Thuộc tính `help` rỗng hoặc command tùy biến xử lý help riêng | Khai báo help string và kiểm tra mô hình đăng ký |
| Danh sách command quá dài | Chưa nhóm command theo chức năng | Dùng thuộc tính `group` và đặt tên nhóm nhất quán |
| Người dùng hiểu command ẩn là command được bảo vệ | Nhầm hidden với authorization | Kiểm tra quyền thực thi trong tầng service |

## 12. Bài tập thực hành

Tạo command `report export` với yêu cầu:

- Argument index 0: kỳ báo cáo, ví dụ `monthly` hoặc `quarterly`.
- Option `--output`, bắt buộc: đường dẫn file đầu ra.
- Option `--format`, tên ngắn `-f`, mặc định `csv`; chỉ nhận `csv` hoặc `json`.
- Nhóm command: `Report Management`.
- Description: một câu ngắn mô tả chức năng xuất báo cáo.
- Help string: có Usage, giải thích format và ít nhất hai ví dụ.

Thử các lệnh:

~~~text
help
help report export
report export --help
report export quarterly --output=reports/q2.csv
report export monthly --output=reports/month.json --format=json
~~~

Sau khi hoàn thành, tự kiểm tra:

1. Command xuất hiện trong nhóm đúng chưa?
2. Synopsis có hiển thị kỳ báo cáo và option output không?
3. Help có cho biết format mặc định là csv không?
4. Các ví dụ có thể sao chép và chạy được không?
5. Khi thiếu output, thông báo lỗi có nhất quán với nội dung trợ giúp không?

## Tài liệu tham khảo

- [Spring Shell – Built-in Help](https://docs.spring.io/spring-shell/reference/commands/builtin/help.html)
- [Spring Shell – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell – Organizing Commands](https://docs.spring.io/spring-shell/reference/commands/organize.html)
- [Spring Shell API – @Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell API – Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html)
