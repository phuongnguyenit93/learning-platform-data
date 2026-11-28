# Hỗ trợ --help hoặc -h theo mô hình và phiên bản

Spring Shell cung cấp command `help` để khám phá lệnh và xem cách sử dụng. Ngoài command này, một số phiên bản và mô hình đăng ký còn hỗ trợ gọi trợ giúp ngay sau tên command bằng `--help` hoặc `-h`. Cách hoạt động không hoàn toàn giống nhau giữa Spring Shell 3.x, 4.0.3 và 4.0.4, cũng như giữa command được tạo bằng annotation và command được tạo bằng Java.

Bài học thuộc chương **Trợ giúp và lệnh có sẵn**. Nội dung giải thích ba cách truy cập trợ giúp, phân biệt cơ chế theo phiên bản, cấu hình tên help option, khai báo nội dung mô tả command và kiểm tra hành vi trong ứng dụng.

Sau bài học, bạn có thể:

- Phân biệt `help`, `help <command>`, `<command> --help` và `<command> -h`.
- Giải thích cơ chế help option mặc định của Spring Shell 3.x.
- Xác định điều kiện hỗ trợ `--help` và `-h` trong Spring Shell 4.0.3 và 4.0.4.
- Cấu hình help option toàn cục hoặc cho từng `CommandRegistration` ở 3.x.
- Chọn đúng cách khai báo command bằng annotation, `Command.builder()` hoặc `AbstractCommand` ở 4.x.
- Viết description, help text và metadata option để trợ giúp có ích cho người dùng.

## Ba cách truy cập trợ giúp

Spring Shell có ba cách chính để người dùng tìm hiểu command:

| Cách gọi | Mục đích | Ví dụ |
| --- | --- | --- |
| `help` | Liệt kê command đã đăng ký và mô tả ngắn. | `help` |
| `help <command>` | Hiển thị thông tin chi tiết của command, gồm synopsis, option, argument và metadata liên quan. | `help report export` |
| `<command> --help` hoặc `<command> -h` | Yêu cầu trợ giúp ngay tại command đang gọi, nếu phiên bản và mô hình command hỗ trợ help option. | `report export --help` |

Hai cách đầu dựa trên command tích hợp `help`. Cách thứ ba là shortcut gắn với command; đây là điểm có khác biệt theo phiên bản và cách đăng ký.

Ví dụ, khi gõ `help`, shell có thể liệt kê:

```text
AVAILABLE COMMANDS

Built-In Commands
    clear: Clear the terminal screen
    help: Show help about available commands
    quit, exit: Exit the shell
    version: Show version info

Report Commands
    report export: Xuất báo cáo
```

Khi gõ `help report export`, Spring Shell hiển thị thông tin chi tiết hơn:

```text
NAME
    report export - Xuất báo cáo

DESCRIPTION
    Xuất dữ liệu báo cáo theo định dạng được chọn.

SYNOPSIS
    report export --format String [--output String]

OPTIONS
    --format String
        Định dạng file xuất
        [Mandatory]

    --output String
        Đường dẫn file đầu ra
        [Optional]
```

Nội dung thực tế phụ thuộc phiên bản, command metadata và template trợ giúp được cấu hình.

## Spring Shell 3.x: help option được thêm mặc định

Trong Spring Shell 3.3.x, chức năng mặc định là bổ sung hai tên `--help` và `-h` cho mọi command. Khi một trong hai option xuất hiện, Spring Shell chuyển hướng sang command `help` để hiển thị trợ giúp và bỏ qua việc thực thi target command.

Điều này áp dụng cho command khai báo bằng annotation và command khai báo bằng `CommandRegistration`. Người dùng có thể gọi:

```text
report export --help
report export -h
```

### Cấu hình toàn cục

Các thuộc tính help option của Spring Shell 3.x nằm dưới `spring.shell.help`:

```yaml
spring:
  shell:
    help:
      enabled: true
      long-names: help
      short-names: h
      command: help
```

Ý nghĩa:

- `enabled`: bật hoặc tắt help option tự động cho command.
- `long-names`: tên dài được thêm vào command, mặc định là `help`.
- `short-names`: tên ngắn, mặc định là `h`.
- `command`: command đích nhận yêu cầu trợ giúp, thông thường là `help`.

Nếu muốn tắt shortcut cho toàn bộ command:

```yaml
spring:
  shell:
    help:
      enabled: false
```

Khi tắt help option tự động, command tích hợp `help` vẫn là một cơ chế riêng nếu nó chưa bị tắt bằng cấu hình của chính command đó. Người dùng vẫn có thể dùng `help report export`.

### Cấu hình theo từng CommandRegistration

Với mô hình programmatic của Spring Shell 3.x, có thể tùy chỉnh help option cho từng registration bằng `withHelpOptions()`:

```java
import org.springframework.shell.command.CommandRegistration;

CommandRegistration registration = CommandRegistration.builder()
    .command("report export")
    .withTarget()
        .function(context -> "Đã tạo báo cáo")
        .and()
    .withHelpOptions()
        .enabled(true)
        .longNames("help")
        .shortNames('h')
        .command("help")
        .and()
    .build();
```

Có thể tắt shortcut riêng cho một registration bằng `.enabled(false)`, hoặc thay tên option và command trợ giúp theo cấu hình ứng dụng. Đây là điểm khác biệt với mô hình annotation: trong 3.x, annotation model chỉ cho phép bật/tắt help option toàn cục qua cấu hình; programmatic model có thể thay đổi theo từng command.

### Built-in help command trong 3.x

Command `help` có thể liệt kê command và hiển thị chi tiết một command. Có thể tùy biến cách trình bày qua các thuộc tính dưới `spring.shell.command.help`, chẳng hạn:

```yaml
spring:
  shell:
    command:
      help:
        enabled: true
        grouping-mode: group
        commands-template: classpath:template/help-commands-default.stg
        command-template: classpath:template/help-command-default.stg
```

`grouping-mode` điều khiển việc gom command theo nhóm hay hiển thị dạng phẳng. Hai template cho phép thay đổi cách hiển thị danh sách command và chi tiết command. Đây là cấu hình giao diện của built-in help command, khác với `spring.shell.help.enabled` dùng để bật/tắt shortcut `--help` và `-h`.

## Spring Shell 4.0.3: phụ thuộc vào kiểu command

Spring Shell 4.x thiết kế lại command model. Built-in `help` vẫn có mặt:

- `help` liệt kê các command đã đăng ký.
- `help <command>` hiển thị chi tiết command.

Đối với shortcut trên command, tài liệu 4.0.3 mô tả `--help` và `-h` cho các command kế thừa `AbstractCommand`. Khi một trong hai option xuất hiện, `AbstractCommand` chuyển hướng sang command trợ giúp và không gọi nghiệp vụ của command.

### Command khai báo bằng annotation

Command method được đánh dấu `@Command` được chuyển thành `MethodInvokerCommandAdapter`. Adapter này là một lớp con của `AbstractCommand`, vì vậy command annotation trong Spring Shell 4.0.3 có cơ chế help option:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReportCommands {

    @Command(
        name = "report export",
        description = "Xuất báo cáo",
        help = "Xuất báo cáo ra file. Ví dụ: report export --format csv")
    public String export(
            @Option(longName = "format", shortName = 'f',
                    description = "Định dạng file xuất") String format) {
        return "Đã xuất báo cáo dạng " + format;
    }
}
```

Trong 4.0.3, có thể gọi:

```text
report export --help
report export -h
help report export
```

`description` là dòng mô tả ngắn dùng trong danh sách command. `help` cung cấp giải thích dài hơn, có thể gồm ví dụ sử dụng. Metadata của `@Option` giúp phần trợ giúp mô tả tên option và ý nghĩa của nó.

### Command programmatic bằng AbstractCommand

Nếu tạo command programmatic và muốn có shortcut `--help` cùng `-h` trong 4.0.3, có thể kế thừa `AbstractCommand`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;

@Configuration
class ReportCommandConfiguration {

    @Bean
    Command reportExportCommand() {
        return new AbstractCommand(
                "report export",
                "Xuất báo cáo",
                "Report Commands",
                "Xuất báo cáo ra file. Ví dụ: report export --format csv") {

            @Override
            public ExitStatus doExecute(CommandContext context) {
                println("Đã tạo báo cáo", context);
                return ExitStatus.OK;
            }
        };
    }
}
```

`AbstractCommand` cung cấp xử lý `--help` và `-h`. Các overload `Command.Builder.execute(...)` của Spring Shell 4.0.3 trả về `AbstractCommand`, vì vậy command tạo bằng builder và gắn execution target theo cách này cũng nhận help shortcut. Nếu tự triển khai trực tiếp interface `Command` hoặc cung cấp implementation không kế thừa `AbstractCommand`, không nên giả định nó có cùng cơ chế; dùng `help report export` hoặc tự cung cấp hành vi help phù hợp.

## Spring Shell 4.0.4: help thống nhất trên mọi command

Spring Shell 4.0.4 bổ sung `CommandHelpRenderer`, được giới thiệu từ phiên bản này. Renderer tạo nội dung trợ giúp chi tiết cho một command; cùng một nội dung được dùng bởi `help <command>` và implicit `--help` option của mọi command.

Điều này làm cho help của command annotation và command programmatic nhất quán hơn. Bản 4.0.4 cũng sửa các lỗi liên quan đến:

- Khác biệt nội dung giữa `mycommand --help` và `help mycommand`.
- Phát hiện help option khi command có option riêng.
- Xử lý implicit help option ở subcommand.
- Thiếu thông tin argument trong phần trợ giúp.

Ví dụ command annotation ở trên có thể gọi bằng:

```text
report export --help
report export -h
help report export
```

Khi dùng programmatic command với `Command.builder()`, 4.0.4 cũng cung cấp implicit `--help` theo command model mới. Để có cách gọi ngắn nhất quán giữa các implementation, nên dùng `--help`; `-h` là alias ngắn trong help model của các command có công bố tên này, bao gồm các command dựa trên `AbstractCommand`. `help <command>` vẫn là cú pháp rõ ràng và dễ dùng để kiểm tra chi tiết.

Ví dụ builder khai báo mô tả và help text:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
class ReportCommandConfiguration {

    @Bean
    Command reportExportCommand() {
        return Command.builder()
            .name("report export")
            .description("Xuất báo cáo")
            .help("Xuất báo cáo ra file. Ví dụ: report export --format csv")
            .execute(context -> {
                context.outputWriter().println("Đã tạo báo cáo");
            });
    }
}
```

`CommandHelpRenderer` tạo phần NAME, DESCRIPTION, SYNOPSIS và các phần dành cho option, argument, alias mà command khai báo. Vì vậy, hãy khai báo metadata đầy đủ để cả `help <command>` và `--help` hiển thị thông tin có ích.

## Ma trận hành vi theo phiên bản và mô hình

| Phiên bản | Mô hình command | `--help` | `-h` | Ghi chú |
| --- | --- | --- | --- | --- |
| 3.3.x | Annotation | Có, bật mặc định | Có, bật mặc định | Có thể tắt toàn cục bằng `spring.shell.help.enabled=false`. |
| 3.3.x | `CommandRegistration` | Có, bật mặc định | Có, bật mặc định | Có thể tùy chỉnh từng command bằng `withHelpOptions()`. |
| 4.0.3 | `@Command` method | Có | Có | Method adapter kế thừa `AbstractCommand`. |
| 4.0.3 | `AbstractCommand` | Có | Có | Hành vi được cung cấp bởi base class. |
| 4.0.3 | `Command.builder().execute(...)` | Có | Có | Builder trả về `AbstractCommand`; implementation `Command` tự viết không kế thừa base class cần được kiểm tra riêng. |
| 4.0.4 | Mọi command | Có, implicit | Có khi tên ngắn được expose bởi help model | `CommandHelpRenderer` thống nhất nội dung help; bản này sửa xử lý implicit help ở subcommand. |

Ma trận trên mô tả hành vi của các dòng phiên bản được nêu. Nếu ứng dụng dùng phiên bản nhỏ khác hoặc custom command adapter, hãy kiểm tra output `help <command>` để xác nhận tên shortcut thực tế.

## Viết nội dung trợ giúp có ích

Spring Shell có thể tạo synopsis và danh sách option từ metadata command, nhưng người viết vẫn cần cung cấp ngữ cảnh cho người dùng.

| Metadata | Mục đích | Ví dụ |
| --- | --- | --- |
| `name` | Tên command để gọi. | `report export` |
| `description` | Mô tả ngắn trong danh sách `help`. | `Xuất báo cáo` |
| `help` | Giải thích dài, có thể gồm ví dụ. | `Xuất báo cáo ra CSV. Ví dụ: report export --format csv` |
| Option description | Giải thích ý nghĩa option. | `Định dạng file xuất` |
| Argument description | Giải thích dữ liệu vị trí. | `Tháng cần xuất báo cáo` |

Một help text tốt nên trả lời được:

1. Command thực hiện việc gì?
2. Dữ liệu đầu vào nào là bắt buộc?
3. Option nào thường được dùng và giá trị nào được chấp nhận?
4. Có ví dụ lệnh hoàn chỉnh nào để người dùng sao chép không?
5. Kết quả được tạo ở đâu hoặc hiển thị theo cách nào?

Tránh lặp nguyên văn `description` trong `help`. Description nên ngắn để dễ quét; help text nên bổ sung cách dùng, ví dụ và lưu ý.

## Built-in help command và cấu hình riêng

Không nên nhầm hai cơ chế cấu hình:

- Help option gắn vào command, ví dụ `--help` hoặc `-h`.
- Built-in command tên `help`, dùng để liệt kê và tra cứu command.

Ở Spring Shell 3.x, `spring.shell.help.enabled` điều khiển việc thêm help option tự động. Cấu hình `spring.shell.command.help.enabled` điều khiển việc bật/tắt built-in command `help` và cách trình bày của nó được điều chỉnh bằng các thuộc tính template tương ứng.

Trong Spring Shell 4.x, built-in `help` vẫn là đường tra cứu độc lập. Có thể tắt built-in command bằng:

```yaml
spring:
  shell:
    command:
      help:
        enabled: false
```

Khi tắt built-in command, không nên kỳ vọng `help <command>` hoạt động. Với Spring Shell 4.0.4, implicit `--help` vẫn là cơ chế trợ giúp của từng command. Hãy kiểm tra cấu hình của đúng phiên bản trước khi tắt một cơ chế.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| `--help` bị báo là option không tồn tại trong 3.x | Help option tự động đã bị tắt toàn cục hoặc registration đặt `enabled(false)`. | Kiểm tra `spring.shell.help.enabled` và `withHelpOptions()`. |
| `-h` không hoạt động trong 4.0.3 | Command được triển khai trực tiếp từ `Command` mà không kế thừa `AbstractCommand`. | Dùng `Command.builder().execute(...)`, kế thừa `AbstractCommand` hoặc gọi `help <command>`. |
| `--help` không hoạt động trong 4.0.3 với command tự viết | Implementation không đi qua adapter hoặc base class có help handling. | Dùng `help <command>` hoặc tự bổ sung hành vi help cho implementation. |
| `help` không được nhận diện | Built-in help command bị tắt hoặc bị thay thế. | Kiểm tra `spring.shell.command.help.enabled` và bean cung cấp help command. |
| Help chỉ có một dòng ngắn | Chỉ khai báo `description`, chưa khai báo help text chi tiết. | Bổ sung `help` trên `@Command` hoặc command builder. |
| `--help` và `help <command>` hiển thị khác nhau trong 4.0.3 | Phiên bản này còn khác biệt trong cách dựng output; có lỗi đã được sửa ở 4.0.4. | Nâng cấp 4.0.4 hoặc dùng `help <command>` để xem synopsis và option đầy đủ. |
| Help của subcommand không đúng | Lỗi phát hiện implicit help trong phiên bản cũ. | Dùng bản 4.0.4 đã sửa xử lý help option cho subcommand. |
| Option nghiệp vụ xung đột với `help` hoặc `h` | Command tự khai báo option trùng tên dành cho trợ giúp. | Chọn tên khác cho option nghiệp vụ và giữ tên trợ giúp dành riêng. |

## Kiểm thử trợ giúp

Khi thêm hoặc thay đổi command, hãy kiểm tra cả ba đường truy cập trợ giúp:

1. Gõ `help` và xác nhận command xuất hiện với description phù hợp.
2. Gõ `help report export` và xác nhận synopsis, option, argument, alias cùng help text được hiển thị.
3. Gõ `report export --help`; với mô hình hỗ trợ short alias, kiểm tra thêm `report export -h`.
4. Xác nhận target nghiệp vụ không được gọi khi người dùng yêu cầu help.
5. Với Spring Shell 3.x, kiểm tra cấu hình bật/tắt toàn cục và tùy chỉnh per-command.
6. Với Spring Shell 4.0.3, kiểm tra riêng command annotation và command programmatic.
7. Với Spring Shell 4.0.4, kiểm tra cả command chính và subcommand để xác nhận nội dung help nhất quán.

Ví dụ kiểm thử thủ công:

```text
help
help report export
report export --help
report export -h
```

Nếu command có side effect như ghi file hoặc gọi API, dùng spy/mock trong integration test để xác nhận nhánh help không thực hiện hành vi nghiệp vụ.

## Checklist trước khi phát hành CLI

- [ ] Đã xác định phiên bản Spring Shell thực tế trong dependency tree.
- [ ] Đã xác định command dùng annotation, `CommandRegistration`, `AbstractCommand` hay `Command.builder()`.
- [ ] Đã kiểm tra `help` liệt kê đúng command và description.
- [ ] Đã kiểm tra `help <command>` hiển thị synopsis, option và argument.
- [ ] Đã kiểm tra `--help` và `-h` theo đúng phiên bản/mô hình.
- [ ] Help text có ví dụ lệnh có thể sao chép.
- [ ] Option và argument có description rõ ràng.
- [ ] Không có option nghiệp vụ trùng với tên help shortcut.
- [ ] Đã kiểm tra help cho subcommand và các command có alias.
- [ ] Đã xác nhận yêu cầu help không chạy nghiệp vụ hoặc tạo side effect.

## Ghi nhớ

Spring Shell luôn có thể dùng built-in `help` để liệt kê command và `help <command>` để xem chi tiết. Trong Spring Shell 3.x, `--help` và `-h` được thêm mặc định cho mọi command và có thể cấu hình toàn cục hoặc theo từng `CommandRegistration`. Trong Spring Shell 4.0.3, shortcut phụ thuộc command có kế thừa `AbstractCommand` hay không; command annotation được bọc bởi method adapter thuộc nhánh này. Từ 4.0.4, implicit `--help` được chuẩn hóa cho mọi command và `CommandHelpRenderer` giúp nội dung giữa hai cách gọi nhất quán hơn. Luôn kiểm tra đúng phiên bản và mô hình đăng ký trước khi dựa vào shortcut.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Help Options](https://docs.spring.io/spring-shell/reference/3.3/commands/helpoptions.html): mặc định `--help`/`-h`, cấu hình toàn cục và `withHelpOptions()`.
- [Spring Shell 3.3.4 — Built-in Help](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/help.html): liệt kê command, `help <command>` và tùy biến template.
- [Spring Shell 4.0.3 — Option Help](https://docs.spring.io/spring-shell/reference/commands/help.html): help shortcut trong `AbstractCommand`.
- [Spring Shell 4.0.3 — Built-in Help](https://docs.spring.io/spring-shell/reference/commands/builtin/help.html): cách dùng `help` và `help <command>`.
- [Spring Shell 4.0.3 API — `AbstractCommand`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/AbstractCommand.html): base class và các adapter kế thừa.
- [Spring Shell 4.0.3 API — `Command.Builder` dùng `AbstractCommand`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/class-use/AbstractCommand.html): các overload `Command.Builder.execute(...)` trả về `AbstractCommand`.
- [Spring Shell 4.0.4 API — `CommandHelpRenderer`](https://docs.spring.io/spring-shell/reference/4.0-SNAPSHOT/api/org/springframework/shell/core/command/CommandHelpRenderer.html): cùng nội dung cho `help <command>` và implicit `--help` của mọi command; API được giới thiệu từ 4.0.4.
- [Spring Shell 4.0.4 Release Notes](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.4): các sửa lỗi về help output, detection và subcommand.
- [Spring Shell 4.0.4 Available Now](https://spring.io/blog/2026/11/19/spring-shell-4-0-4-available-now/): thông báo phát hành 4.0.4.
