# Nhãn giá trị trong trợ giúp và các thay đổi ở 4.x

Khi người dùng chạy `help <command>`, Spring Shell trình bày cú pháp và các tham số mà command chấp nhận. Với một option, phần trợ giúp thường cần chỉ ra người dùng phải cung cấp loại giá trị nào. Ví dụ, `--output` cần một đường dẫn file, `--date` cần một ngày và `--limit` cần một số nguyên.

Trong Spring Shell 3.x, thuộc tính `label` cho phép thay tên kiểu Java chung chung bằng một nhãn dễ hiểu trong phần trợ giúp. Spring Shell 4.x đã loại bỏ thuộc tính này. Khi nâng cấp, cần hiểu đúng vai trò của label và dùng metadata trợ giúp còn được hỗ trợ để diễn đạt cú pháp rõ ràng.

## Label là gì?

`label` là văn bản đại diện cho giá trị của một option trong nội dung trợ giúp. Nó giúp người đọc hiểu giá trị mong đợi mà không cần suy luận từ kiểu Java. Ví dụ, thay vì hiển thị `--output String`, trợ giúp có thể hiển thị `--output FILE_PATH`.

Label chỉ phục vụ việc trình bày trợ giúp. Nó không đổi tên option, không chuyển đổi giá trị, không đặt giá trị mặc định, không làm option bắt buộc và không thay đổi cách parser nhận dòng lệnh.

| Metadata | Mục đích | Ví dụ |
|---|---|---|
| `label` (3.x) | Tên gợi nhớ cho giá trị trong help | `FILE_PATH`, `ISO_DATE`, `PAGE_SIZE` |
| `description` | Giải thích ý nghĩa của option | `Đường dẫn file báo cáo cần tạo` |
| `defaultValue` | Giá trị thực tế được dùng khi người dùng bỏ qua option | `./reports/today.csv` |
| `required` | Xác định người dùng có bắt buộc truyền option hay không | `true` |
| Kiểu Java | Kiểu dữ liệu mà Spring Shell chuyển đổi giá trị đầu vào thành | `String`, `LocalDate`, `Integer` |

Ví dụ, `label = "FILE_PATH"` không có nghĩa là ứng dụng tự tạo một file hoặc tự gán chuỗi `FILE_PATH` vào tham số. Người dùng vẫn truyền một đường dẫn thật, chẳng hạn `--output ./reports/today.csv`.

## Label trong Spring Shell 3.x

Spring Shell 3.x có hai cách khai báo command phổ biến: annotation model mới và đăng ký programmatic bằng `CommandRegistration`. Cả hai mô hình này đều có thể gán label cho option. Annotation legacy `@ShellOption` không hỗ trợ thuộc tính label.

### Dùng annotation @Option

Trong annotation model mới của Spring Shell 3.x, `@Option` có thuộc tính `label`:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReportCommands {

    @Command(command = "report-export", description = "Xuất báo cáo")
    public String export(
            @Option(
                    longNames = "output",
                    label = "FILE_PATH",
                    description = "Đường dẫn file báo cáo cần tạo",
                    required = true
            ) String output) {
        return "Đã tạo báo cáo tại " + output;
    }
}
```

Khi người dùng xem `help report-export`, label được dùng trong phần mô tả cú pháp và danh sách option. Theo ví dụ trong tài liệu Spring Shell 3.4.1, phần trợ giúp có dạng:

```text
NAME
       report-export -

SYNOPSIS
       report-export --output FILE_PATH

OPTIONS
       --output FILE_PATH
       [Mandatory]
```

Tên `FILE_PATH` chỉ là gợi ý trực quan cho người đọc. Lệnh thực tế vẫn truyền một giá trị:

```text
shell:>report-export --output ./reports/today.csv
Đã tạo báo cáo tại ./reports/today.csv
```

### Dùng CommandRegistration

Với mô hình programmatic, gọi `label(...)` trên option spec của `CommandRegistration.Builder`:

```java
import org.springframework.shell.command.CommandRegistration;

CommandRegistration exportCommand = CommandRegistration.builder()
        .command("report-export")
        .description("Xuất báo cáo")
        .withOption()
            .longNames("output")
            .type(String.class)
            .label("FILE_PATH")
            .description("Đường dẫn file báo cáo cần tạo")
            .required()
            .and()
        .withTarget()
            .function(context -> {
                String output = context.getOptionValue("output");
                return "Đã tạo báo cáo tại " + output;
            })
            .and()
        .build();
```

`label("FILE_PATH")` điều chỉnh cách option xuất hiện trong trợ giúp. `longNames("output")` mới là tên mà người dùng nhập sau dấu `--`; `type(String.class)` xác định kiểu dữ liệu; `required()` quy định option bắt buộc. Các thiết lập này có vai trò riêng.

### Label không được hỗ trợ với annotation legacy

Mô hình legacy dùng `@ShellMethod` và `@ShellOption`. Tài liệu Spring Shell 3.x ghi rõ label không được hỗ trợ với legacy annotation. Không thêm `label` vào `@ShellOption` và kỳ vọng nó thay đổi help output.

Nếu ứng dụng còn dùng annotation legacy nhưng cần nhãn tùy chỉnh, có thể chuyển command đó sang annotation model mới (`@Command` và `@Option`) hoặc đăng ký bằng `CommandRegistration`. Hãy chuyển theo đúng phiên bản 3.x đang sử dụng và kiểm thử lại output `help`.

## Label không phải tên option hay mô tả option

Ba loại thông tin sau thường bị nhầm lẫn:

```text
report-export --output FILE_PATH
             |        |
             |        +-- label: giá trị mong đợi, chỉ dùng trong help (3.x)
             +----------- tên option: khóa parser nhận diện
```

- Tên option là `output`, được nhập thành `--output`.
- Label là `FILE_PATH`, giúp người dùng hiểu giá trị cần truyền.
- Description giải thích option dùng để làm gì, ví dụ `Đường dẫn file báo cáo cần tạo`.

Không dùng label để thay thế description. Một nhãn như `DATE` có thể ngắn gọn trong synopsis nhưng chưa giải thích định dạng ngày nào được chấp nhận. Description nên nói rõ điều đó, ví dụ `Ngày báo cáo theo định dạng yyyy-MM-dd`.

## Điều gì thay đổi trong Spring Shell 4.x?

Spring Shell 4 loại bỏ option label. Hướng dẫn migration giải thích rằng label không được dùng để sắp xếp, lọc hoặc nhóm option; nó chỉ được dùng trong chuỗi trợ giúp. Vì vậy, API 4.x không còn thuộc tính label trong `@Option`, `CommandOption` hoặc builder tương ứng.

| Thành phần | Spring Shell 3.x | Spring Shell 4.x |
|---|---|---|
| Annotation option | `org.springframework.shell.command.annotation.Option` | `org.springframework.shell.core.command.annotation.Option` |
| Tên option dài | `longNames` (mảng, có thể có alias) | `longName` (một tên) |
| Tên option ngắn | `shortNames` (mảng, có thể có alias) | `shortName` (một tên) |
| Nhãn giá trị | Có `label` | Đã loại bỏ |
| Mô tả option | `description` | `description` vẫn được hỗ trợ |
| Giá trị mặc định | `defaultValue` | `defaultValue` vẫn được hỗ trợ |
| Mô hình legacy | `@ShellOption` còn tồn tại | Annotation legacy đã bị loại bỏ |

API `@Option` trong Spring Shell 4.x chỉ còn các thuộc tính như `longName`, `shortName`, `description`, `required` và `defaultValue`. `CommandOption` cũng lưu tên ngắn, tên dài, mô tả, tính bắt buộc, giá trị mặc định, giá trị hiện tại và kiểu dữ liệu; không có thành phần label.

Vì vậy, code sau hợp lệ trong annotation model 3.x nhưng không biên dịch trong 4.x:

```java
// Spring Shell 3.x
@Option(longNames = "output", label = "FILE_PATH") String output
```

Trong Spring Shell 4.x, không có thuộc tính thay thế trực tiếp cho `label`:

```java
// Spring Shell 4.x
@Option(
        longName = "output",
        description = "Đường dẫn file báo cáo cần tạo",
        required = true
) String output
```

Không đổi `label` thành `description` một cách máy móc. Hai thuộc tính có mục đích khác nhau: description là câu giải thích option, không phải placeholder hiển thị thay kiểu dữ liệu trong synopsis.

## Viết trợ giúp dễ hiểu trong Spring Shell 4.x

Khi không còn label, hãy dùng `description` của option để giải thích giá trị và `help` của command để ghi cú pháp hoặc ví dụ cụ thể. `@Command(help = "...")` bổ sung phần hướng dẫn riêng cho command; mô hình programmatic có `Command.Builder.help(String)` tương ứng.

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReportCommands {

    @Command(
            name = "report-export",
            description = "Xuất báo cáo ra file",
            help = """
                    Xuất báo cáo ra đường dẫn được chỉ định.

                    Cú pháp:
                      report-export --output=<file-path>

                    Ví dụ:
                      report-export --output=./reports/today.csv
                    """
    )
    public String export(
            @Option(
                    longName = "output",
                    description = "Đường dẫn file báo cáo cần tạo",
                    required = true
            ) String output) {
        return "Đã tạo báo cáo tại " + output;
    }
}
```

Trong ví dụ này:

- `description` ngắn gọn giải thích ý nghĩa của option `--output`.
- `help` cung cấp cách dùng có placeholder `<file-path>` và một lệnh mẫu có thể sao chép.
- `required = true` vẫn kiểm soát việc người dùng có phải truyền option hay không.

Ở Spring Shell 4.0.4, bộ dựng trợ giúp chi tiết tạo các phần NAME, DESCRIPTION, SYNOPSIS và các phần dành cho option, argument, alias. Nội dung `help` của command được đặt trong phần DESCRIPTION. Vì vậy, placeholder do bạn viết trong `help` là hướng dẫn bằng văn bản; nó không thay đổi metadata hoặc placeholder tự sinh trong SYNOPSIS.

### Cách viết help hiệu quả

Khi thay label bằng nội dung trợ giúp, hãy ưu tiên các thông tin sau:

1. Viết description ngắn, tập trung vào ý nghĩa nghiệp vụ của option.
2. Ghi định dạng giá trị nếu có quy ước cụ thể, ví dụ `Ngày theo ISO-8601 (yyyy-MM-dd)`.
3. Đưa một cú pháp hoàn chỉnh vào `help`, dùng placeholder dễ hiểu như `<file-path>`, `<iso-date>` hoặc `<page-size>`.
4. Thêm ít nhất một ví dụ lệnh với giá trị thật có thể chạy.
5. Nếu option có default value, ghi rõ giá trị mặc định trong mô tả khi người dùng cần biết.

Ví dụ nội dung trợ giúp:

```text
report-export --output=<file-path> --date=<yyyy-MM-dd>

Ví dụ:
report-export --output=./reports/sales.csv --date=2026-11-26
```

Người dùng đọc được định dạng cần truyền ngay cả khi synopsis tự sinh không còn placeholder tùy chỉnh.

## Đăng ký command bằng code trong 4.x

Mô hình programmatic 4.x cũng không có label trên `CommandOption.Builder`. Có thể đặt `description` cho từng option và `help` cho toàn command:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.CommandContext;

@Bean
Command reportExportCommand() {
    CommandOption outputOption = CommandOption.with()
            .longName("output")
            .description("Đường dẫn file báo cáo cần tạo")
            .required(true)
            .type(String.class)
            .build();

    return Command.builder()
            .name("report-export")
            .description("Xuất báo cáo ra file")
            .help("Cú pháp: report-export --output=<file-path>. "
                    + "Ví dụ: report-export --output=./reports/today.csv")
            .options(outputOption)
            .execute((CommandContext context) -> {
                context.outputWriter().println("Đã nhận yêu cầu xuất báo cáo.");
            });
}
```

`CommandOption.with()` cung cấp builder cho metadata option. Các phương thức hiện có gồm `longName`, `shortName`, `description`, `required`, `defaultValue`, `value` và `type`; không có `label`. `Command.Builder.help(...)` giữ phần hướng dẫn của command ở mức command, phù hợp để mô tả cú pháp và ví dụ.

## Các thay đổi liên quan khi nâng từ 3.x lên 4.x

Ngoài việc loại bỏ label, migration guide còn nêu một số thay đổi có thể xuất hiện cùng lúc trong phần khai báo option:

| Nội dung | Trước 4.x | Trong 4.x |
|---|---|---|
| Package annotation mới | `org.springframework.shell.command.annotation` | `org.springframework.shell.core.command.annotation` |
| Thuộc tính tên command | `command` | `name` |
| Nhiều tên dài/ngắn cho một option | Có thể khai báo mảng `longNames`/`shortNames` | Một `longName` và một `shortName` |
| Label | Có thể dùng trong help | Bị loại bỏ |
| Legacy `@ShellOption` | Có trong 3.x | Đã bị loại bỏ |
| Mô tả và hướng dẫn command | `description`, `help` | Tiếp tục dùng `description`, `help` |

Ví dụ chuyển một method từ 3.x sang 4.x:

```java
// Spring Shell 3.x
@Command(command = "report-export")
public String export(
        @Option(longNames = "output", label = "FILE_PATH") String output) {
    return output;
}
```

```java
// Spring Shell 4.x
@Command(
        name = "report-export",
        help = "Cú pháp: report-export --output=<file-path>"
)
public String export(
        @Option(
                longName = "output",
                description = "Đường dẫn file báo cáo cần tạo"
        ) String output) {
    return output;
}
```

Khi chuyển đổi, cần kiểm tra mọi chỗ dùng `label`, `longNames`, `shortNames`, `@ShellOption` và thuộc tính `command` của `@Command`. Không chỉ đổi import rồi giữ nguyên các thuộc tính cũ.

## Kiểm thử phần trợ giúp

Nên kiểm tra trợ giúp ở cả hai phiên bản để bảo đảm người dùng hiểu được giá trị cần truyền:

1. Trong 3.x, gọi `help <command>` và xác nhận label xuất hiện trong SYNOPSIS và OPTIONS.
2. Xác nhận thay đổi label không làm thay đổi tên option hoặc giá trị parser nhận.
3. Với legacy `@ShellOption`, xác nhận không dựa vào label vì mô hình này không hỗ trợ thuộc tính đó.
4. Trong 4.x, gọi `help <command>` và kiểm tra description của option được hiển thị.
5. Xác nhận nội dung `@Command(help = ...)` hoặc `Command.Builder.help(...)` xuất hiện trong phần hướng dẫn command.
6. Chạy ví dụ được ghi trong help để chắc chắn cú pháp mô tả khớp với parser.
7. Kiểm tra option bắt buộc, giá trị mặc định và chuyển đổi kiểu vẫn hoạt động độc lập với nội dung help.
8. Sau khi nâng phiên bản, tìm và loại bỏ các thuộc tính `label` còn sót lại để tránh lỗi biên dịch.

Nếu sản phẩm cần thay đổi hoàn toàn bố cục help, hãy kiểm tra extension point của phiên bản Spring Shell đang dùng và viết kiểm thử cho output đó. Không nên chỉnh sửa chuỗi help để giả vờ rằng label vẫn là metadata của option.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `label` không được nhận diện trong `@Option` | Đang dùng Spring Shell 4.x | Bỏ `label`; dùng `description` và `@Command(help = ...)` |
| `.label(...)` không biên dịch | `CommandOption.Builder` 4.x không có phương thức này | Chuyển nội dung cần giải thích vào `description` hoặc `help` |
| Help vẫn hiển thị kiểu Java thay vì `FILE_PATH` | Đang kỳ vọng label 3.x trong 4.x | Viết cú pháp có placeholder trong phần help của command |
| Người dùng nhầm label là giá trị mặc định | Chưa phân biệt label với `defaultValue` | Chỉ dùng `defaultValue` để đặt giá trị runtime |
| Description quá dài và khó quét | Dùng description thay cho toàn bộ hướng dẫn | Giữ description ngắn; chuyển ví dụ và cú pháp sang `help` |
| Annotation legacy không hiển thị label | `@ShellOption` không hỗ trợ label từ trước | Chuyển sang annotation model mới hoặc programmatic registration trong 3.x |
| Code 3.x không biên dịch sau nâng cấp | Còn `longNames`, `shortNames`, `command` hoặc `@ShellOption` | Chuyển sang `longName`, `shortName`, `name` và annotation package 4.x |

## Tài liệu tham khảo

- [Spring Shell 3.4.1 — Label](https://docs.spring.io/spring-shell/reference/options/label.html): mục đích của label, cách khai báo programmatic/annotation và ví dụ help output.
- [Spring Shell 3.4.3 API — Option](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Option.html): thuộc tính `label` trong annotation model 3.x.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): lý do loại bỏ option labels và các thay đổi về tên option trong 4.x.
- [Spring Shell 4.0.4 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html): khai báo option, description và help của command.
- [Spring Shell 4.0.3 API — Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html): các thuộc tính còn được hỗ trợ trong `@Option` 4.x.
- [Spring Shell 4.0.4 API — CommandOption](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.html): cấu trúc metadata option không còn thành phần label.
- [Spring Shell 4.0.4 API — CommandOption.Builder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.Builder.html): các phương thức builder programmatic của option.
- [Spring Shell 4.0.3 API — Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html): `Command.Builder` và thuộc tính help của command.
