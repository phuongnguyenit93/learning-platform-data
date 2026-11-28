# Mô tả ngắn, trợ giúp chi tiết và nhãn tham số

Một command tốt cần tự giải thích được cách sử dụng. Khi người dùng gõ `help`, họ cần nhận ra lệnh phù hợp qua một mô tả ngắn. Khi gõ `help <command>`, họ cần biết cú pháp, tham số, kiểu dữ liệu và giá trị mặc định. Trong phần synopsis, một nhãn như `FILE`, `USERNAME` hoặc `YYYY-MM-DD` giúp người dùng hiểu giá trị cần truyền mà không phải đoán từ tên kiểu Java.

Spring Shell cung cấp các thuộc tính `description` và `help` cho command, cùng mô tả cho từng argument và option. Một số phiên bản còn hỗ trợ nhãn riêng cho option. Cần phân biệt tính năng theo phiên bản: Spring Shell 3.4 có `label` trong API option mới, trong khi API annotation và model `CommandOption` của Spring Shell 4.0.3 không còn thuộc tính này. Bài học sẽ chỉ rõ cách dùng và giới hạn của từng dòng phiên bản.

## 1. Ba lớp thông tin trong trợ giúp

Trợ giúp của một command thường có ba lớp:

| Lớp thông tin | Mục đích | Nơi khai báo |
|---|---|---|
| Mô tả ngắn | Giúp người dùng nhận ra command trong danh sách | `@Command(description = ...)` hoặc `Command.Builder.description(...)` |
| Trợ giúp chi tiết | Giải thích cú pháp, lưu ý và ví dụ gọi lệnh | `@Command(help = ...)` hoặc `Command.Builder.help(...)` |
| Thông tin tham số | Giải thích argument/option và gợi ý giá trị cần nhập | `@Argument(description = ...)`, `@Option(description = ...)`; nhãn option `label` ở Spring Shell 3.4 |

Ba lớp này bổ sung cho nhau. Description nên ngắn để danh sách command dễ quét. Help nên hướng dẫn người dùng thực hiện một tác vụ cụ thể. Mô tả và nhãn tham số nên giải thích từng giá trị ngay cạnh cú pháp.

## 2. Khám phá trợ giúp bằng lệnh help

Spring Shell cung cấp built-in command `help` với ba cách dùng chính:

| Cách gọi | Kết quả |
|---|---|
| `help` | Liệt kê command đã đăng ký cùng mô tả ngắn |
| `help report export` | Hiển thị tên command, synopsis, argument, option, kiểu, trạng thái bắt buộc và mặc định |
| `report export --help` hoặc `report export -h` | Hiển thị chuỗi trợ giúp ngắn do command khai báo |

Ví dụ danh sách command:

~~~text
AVAILABLE COMMANDS

Report Management
    report export: Export a report to a file
    report preview: Preview a report

User Management
    user create: Create a user account
~~~

Ví dụ trợ giúp chi tiết:

~~~text
NAME
    report export - Export a report to a file

SYNOPSIS
    report export <period> --output FILE [--format FORMAT]

OPTIONS
    --output FILE
        Destination file for the exported report.
        [Mandatory]

    --format FORMAT
        Output format.
        [Optional, default = csv]
~~~

Đây là output minh họa. Nội dung và cách căn lề thực tế phụ thuộc metadata command, template help và phiên bản Spring Shell.

## 3. Viết mô tả ngắn bằng description

Với command khai báo bằng annotation, `@Command` có thuộc tính `description`. Mô tả này xuất hiện trong danh sách `help`.

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class ReportCommands {

    @Command(
            name = "report export",
            description = "Export a report to a file"
    )
    public String export() {
        return "Đã xuất báo cáo.";
    }
}
~~~

Một description hữu ích thường trả lời hai câu hỏi: command làm gì và tác động lên đối tượng nào?

| Mô tả chưa rõ | Mô tả rõ hơn |
|---|---|
| `Process data` | `Import customer records from a CSV file` |
| `Run report` | `Export a sales report to a file` |
| `User operation` | `Disable a user account` |
| `Check` | `Show the current connection status` |

Nên dùng động từ cụ thể như `Create`, `Export`, `List`, `Validate`, `Connect` hoặc `Delete`. Tránh đưa toàn bộ hướng dẫn vào description vì danh sách command sẽ dài và khó quét.

`value` là alias của `description`, vì vậy hai cách khai báo sau có cùng ý nghĩa:

~~~java
@Command(name = "report export", description = "Export a report")
~~~

~~~java
@Command(name = "report export", value = "Export a report")
~~~

Nên dùng `description` trong code để thể hiện rõ mục đích của thuộc tính.

## 4. Viết trợ giúp chi tiết bằng help

Thuộc tính `help` của `@Command` là chuỗi được hiển thị khi người dùng gọi `--help` hoặc `-h` trên command. Nội dung nên tập trung vào cách sử dụng:

- Mục đích và kết quả của command.
- Dòng Usage có thể sao chép.
- Ý nghĩa của các lựa chọn quan trọng.
- Ví dụ cho cách gọi thường gặp.
- Lưu ý về điều kiện hoặc tác động của thao tác.

Ví dụ:

~~~java
@Command(
        name = "report export",
        description = "Export a report to a file",
        help = "Export a report for the selected period.\n"
                + "Usage: report export <period> --output=<file> "
                + "[--format=<csv|json>]\n"
                + "Example: report export monthly "
                + "--output=reports/monthly.csv\n"
                + "Example: report export quarterly "
                + "--output=reports/q1.json --format=json"
)
public String export(/* parameters */) {
    // ...
}
~~~

Người dùng có thể xem phần này bằng:

~~~text
report export --help
report export -h
~~~

Help string là văn bản do ứng dụng viết. Spring Shell không tự đồng bộ nội dung Usage trong chuỗi này với chữ ký phương thức. Khi thay đổi tên option, trạng thái bắt buộc hoặc giá trị mặc định, hãy cập nhật ví dụ và kiểm tra lại chúng.

## 5. Mô tả argument và option

Chi tiết của `help <command>` được xây dựng từ metadata tham số.

Với argument, `@Argument` cung cấp:

- `index`: vị trí argument, bắt đầu từ 0.
- `description`: giải thích ý nghĩa của giá trị.
- `defaultValue`: giá trị dùng khi argument được bỏ qua.

Với option trong Spring Shell 4.x, `@Option` cung cấp:

- `longName` và `shortName`: tên dài và tên ngắn.
- `description`: mô tả ngắn của option.
- `required`: đánh dấu option bắt buộc.
- `defaultValue`: giá trị mặc định.

Ví dụ:

~~~java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(
        name = "report export",
        description = "Export a report to a file"
)
public String export(
        @Argument(
                index = 0,
                description = "Reporting period, for example monthly or quarterly"
        )
        String period,
        @Option(
                longName = "output",
                description = "Destination path for the exported file",
                required = true
        )
        String output,
        @Option(
                shortName = 'f',
                longName = "format",
                description = "Output format: csv or json",
                defaultValue = "csv"
        )
        String format) {

    return "Exported " + period + " report to " + output
            + " as " + format;
}
~~~

Các mô tả nên giải thích ý nghĩa cho người dùng, không chỉ lặp lại tên biến. Ví dụ, `Destination path for the exported file` hữu ích hơn `The output`.

## 6. Nhãn option trong Spring Shell 3.4

Nhãn tham số là từ hoặc cụm từ thay cho tên kiểu dữ liệu trong synopsis. Ví dụ, thay vì chỉ hiển thị:

~~~text
report export --output String
~~~

trợ giúp có thể hiển thị:

~~~text
report export --output FILE
~~~

`FILE` cho người dùng biết giá trị cần nhập là đường dẫn file. Tương tự, có thể dùng `USERNAME`, `EMAIL`, `YYYY-MM-DD`, `PORT` hoặc `FORMAT`.

Spring Shell 3.4 hỗ trợ nhãn option qua API option mới:

~~~java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReportCommands {

    @Command(command = "report export", description = "Export a report")
    public String export(
            @Option(
                    longNames = "output",
                    label = "FILE",
                    description = "Destination file"
            )
            String output) {
        return "Exporting to " + output;
    }
}
~~~

Nhãn cũng có thể được đặt bằng API programmatic `CommandRegistration`:

~~~java
import org.springframework.shell.command.CommandRegistration;

CommandRegistration.Builder builder = CommandRegistration.builder()
        .command("report export");

builder.withOption()
        .longNames("output")
        .label("FILE")
        .description("Destination file")
        .and();

// Bổ sung target và metadata cần thiết trước khi gọi builder.build().
~~~

Khi người dùng gọi `help report export`, nhãn được dùng trong synopsis và phần option thay cho tên kiểu mặc định. Ví dụ:

~~~text
SYNOPSIS
    report export --output FILE

OPTIONS
    --output FILE
        Destination file
        [Mandatory]
~~~

Nhãn chỉ ảnh hưởng cách trợ giúp mô tả giá trị. Nó không đổi tên option, không thay đổi cách parser đọc dữ liệu và không tự thực hiện validation. Người dùng vẫn nhập:

~~~text
report export --output=reports/monthly.csv
~~~

Nhãn nên ngắn, viết hoa và thể hiện loại giá trị mong đợi. Tránh dùng câu dài hoặc lặp lại toàn bộ description.

## 7. Lưu ý quan trọng khi dùng Spring Shell 4.x

Không nên sao chép thuộc tính `label` từ ví dụ Spring Shell 3.4 vào annotation 4.x mà không kiểm tra API.

Trong Spring Shell 4.0.3:

- `org.springframework.shell.core.command.annotation.Option` có `shortName`, `longName`, `description`, `required` và `defaultValue`.
- Annotation này không có thuộc tính `label`.
- `CommandOption` là record chứa tên, description, required, default value, value và type; record này cũng không có trường label.
- `@Argument` có `index`, `description` và `defaultValue`, không có label.

`@Command` của Spring Shell 3.4 cũng khác API 4.x: bản 3.4 dùng thuộc tính `command` để đặt tên và không có thuộc tính `help`. Trong 3.4, trang `help <command>` được dựng từ metadata đăng ký; nhãn option giúp synopsis dễ hiểu hơn. Thuộc tính `name` và `help` trong các ví dụ 4.x thuộc API mới của dòng 4.

Vì vậy, code dùng `@Option(label = "FILE")` của Spring Shell 3.4 sẽ không biên dịch khi chuyển nguyên trạng sang annotation API 4.x. Trong 4.x, hãy diễn đạt gợi ý giá trị qua `description` và cung cấp cú pháp rõ trong `@Command(help = ...)`:

~~~java
@Command(
        name = "report export",
        description = "Export a report to a file",
        help = "Usage: report export <period> --output=<FILE>\n"
                + "Example: report export monthly "
                + "--output=reports/monthly.csv"
)
public String export(
        @Argument(
                index = 0,
                description = "Reporting period, e.g. monthly"
        )
        String period,
        @Option(
                longName = "output",
                description = "Destination file (FILE)",
                required = true
        )
        String output) {
    return "Exported " + period + " report to " + output;
}
~~~

Trong ví dụ 4.x, `FILE` là gợi ý được viết trong help và description, không phải metadata label riêng của parser. Điều này giúp tài liệu vẫn dễ hiểu mà không sử dụng API không tồn tại trong phiên bản đang chạy.

| Phiên bản | Cách mô tả command và nhãn option |
|---|---|
| Spring Shell 3.4 API annotation mới | `@Command(command = ...)`; `@Option(label = "FILE")` |
| Spring Shell 3.4 API programmatic | `CommandRegistration.OptionSpec.label("FILE")` |
| Spring Shell 3.4 legacy annotation | Không hỗ trợ label theo tài liệu 3.4 |
| Spring Shell 4.0.3 | `@Command(name = ..., help = ...)`; không có `label` trong `@Option`/`CommandOption`, dùng description và help string |

Khi nâng cấp, rà soát import package. Annotation 3.4 dùng `org.springframework.shell.command.annotation`, còn annotation 4.x dùng `org.springframework.shell.core.command.annotation`. Chỉ đổi package import mà giữ nguyên thuộc tính `label` vẫn không giải quyết được vì API 4.x đã thay đổi.

## 8. Mô tả command bằng Command.Builder

Với command đăng ký bằng bean `Command`, có thể đặt mô tả và trợ giúp qua builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
class ReportCommandConfiguration {

    @Bean
    Command reportStatusCommand() {
        return Command.builder()
                .name("report status")
                .group("Report Management")
                .description("Show the report generation status")
                .help("Show the current report generation status.\n"
                        + "Usage: report status\n"
                        + "Example: report status")
                .execute(context -> {
                    context.outputWriter().println("No report is running.");
                })
                .build();
    }
}
~~~

Trong Spring Shell 4.x, builder có các thuộc tính `description(...)`, `help(...)`, `group(...)`, `aliases(...)`, `arguments(...)` và `options(...)`. Model option của builder không cung cấp label riêng; hãy dùng description và help string để giải thích giá trị.

## 9. Quy tắc viết description, help và label

Một quy ước thống nhất giúp trợ giúp dễ đọc:

| Thành phần | Nên viết | Nên tránh |
|---|---|---|
| Description | Một câu ngắn, bắt đầu bằng động từ | Đoạn văn dài hoặc câu chung chung |
| Help | Usage, lưu ý quan trọng, ví dụ chạy được | Lặp lại description mà không thêm hướng dẫn |
| Argument description | Ý nghĩa và thứ tự của giá trị | Tên biến Java không giải thích |
| Option description | Mục đích, định dạng hoặc tập giá trị | Chỉ lặp lại tên option |
| Label (3.4) | `FILE`, `EMAIL`, `PORT`, `YYYY-MM-DD` | Câu dài hoặc giá trị ví dụ cụ thể |

Đối với label, chọn tên loại dữ liệu hoặc vai trò của giá trị. `FILE` phù hợp để chỉ một đường dẫn; `OUTPUT_PATH` phù hợp khi cần phân biệt đường dẫn đầu ra với file đầu vào. Không dùng `reports/monthly.csv` làm label vì đó là giá trị mẫu, không phải tên loại tham số.

## 10. Kiểm tra trợ giúp bằng ShellTestClient

Khi viết test, xác nhận cả mô tả ngắn lẫn nội dung trợ giúp. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellScreen;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@ContextConfiguration(classes = ReportCommands.class)
class ReportCommandsHelpTests {

    @Autowired
    ShellTestClient client;

    @Test
    void listsTheShortCommandDescription() throws Exception {
        ShellScreen screen = client.sendCommand("help");

        ShellAssertions.assertThat(screen)
                .containsText("report export")
                .containsText("Export a report to a file");
    }

    @Test
    void showsDetailedParameterInformation() throws Exception {
        ShellScreen screen = client.sendCommand("help report export");

        ShellAssertions.assertThat(screen)
                .containsText("--output")
                .containsText("Destination path for the exported file");
    }

    @Test
    void showsTheCommandHelpString() throws Exception {
        ShellScreen screen = client.sendCommand("report export --help");

        ShellAssertions.assertThat(screen)
                .containsText("Usage: report export")
                .containsText("reports/monthly.csv");
    }
}
~~~

Với Spring Shell 3.4, có thể thêm assertion cho nhãn `FILE` trong synopsis. Với 4.x, kiểm tra phần description và help string có chứa gợi ý giá trị mong đợi. Nên xác nhận các cụm từ quan trọng thay vì so sánh toàn bộ output, vì template có thể thay đổi cách căn lề.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Danh sách `help` thiếu mô tả | Chưa khai báo `description` | Thêm mô tả ngắn vào `@Command` hoặc builder |
| `help <command>` thiếu thông tin tham số | Thiếu description trên argument/option | Bổ sung `@Argument(description = ...)` và `@Option(description = ...)` |
| `--help` chỉ hiển thị nội dung sơ sài | Help string quá ngắn hoặc chưa có Usage | Bổ sung cú pháp, lưu ý và ví dụ |
| Synopsis hiển thị kiểu `String` khó hiểu | Chưa đặt label ở phiên bản có hỗ trợ | Với 3.4 dùng `label`; với 4.x dùng description và help string |
| `@Option(label = "FILE")` không biên dịch | Đang dùng annotation API của Spring Shell 4.x | Bỏ thuộc tính label, chuyển gợi ý sang description/help |
| Nhãn xuất hiện nhưng parser không thay đổi | Label chỉ ảnh hưởng output trợ giúp | Tiếp tục dùng tên option thật khi gọi command |
| Ví dụ trong help không chạy | Tên option hoặc tham số đã đổi nhưng help chưa cập nhật | Chạy thử từng ví dụ và đồng bộ với metadata |
| Help quá dài | Description chứa nội dung hướng dẫn chi tiết | Chuyển nội dung dài sang help string hoặc tài liệu riêng |

## 12. Bài tập thực hành

Tạo command `user import` với yêu cầu:

- Description: `Import user records from a CSV file`.
- Help: có Usage và hai ví dụ, một ví dụ cơ bản và một ví dụ chỉ định chế độ kiểm tra trước.
- Argument đầu tiên là tên nhóm người dùng, có description rõ ràng.
- Option `--file` bắt buộc, mô tả là đường dẫn file CSV đầu vào.
- Option `--mode` có mặc định `validate`, chỉ nhận `validate` hoặc `import`.
- Với Spring Shell 3.4, đặt label option `--file` thành `FILE`.
- Với Spring Shell 4.x, diễn đạt gợi ý `FILE` trong description và help string.

Thử các lệnh:

~~~text
help
help user import
user import --help
user import customers --file=data/customers.csv
user import customers --file=data/customers.csv --mode=import
~~~

Sau đó tự kiểm tra:

1. Description có ngắn và nói đúng hành động không?
2. Help string có Usage và ví dụ chạy được không?
3. `help user import` có mô tả đúng argument và option không?
4. Label `FILE` có xuất hiện đúng trong Spring Shell 3.4 không?
5. Khi dùng Spring Shell 4.x, code có tránh thuộc tính `label` không tồn tại không?

## Tài liệu tham khảo

- [Spring Shell 4.0.3 – Built-in Help](https://docs.spring.io/spring-shell/reference/commands/builtin/help.html)
- [Spring Shell 4.0.3 – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell 4.0.3 API – @Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell 4.0.3 API – @Argument](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Argument.html)
- [Spring Shell 4.0.3 API – @Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html)
- [Spring Shell 4.0.3 API – CommandOption](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.html)
- [Spring Shell 3.4.3 – Option label](https://docs.spring.io/spring-shell/reference/options/label.html)
- [Spring Shell 3.4.3 API – @Option](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Option.html)
