# Giới hạn số tên ngắn hoặc tên dài theo phiên bản

Spring Shell cho phép một option có tên dài như `--format` và tên ngắn như `-f`. Số tên thay thế mà một option có thể nhận phụ thuộc vào API của phiên bản Spring Shell đang sử dụng. Ở dòng 3.x, annotation `@Option` hỗ trợ nhiều tên dài và nhiều tên ngắn; ở Spring Shell 4.x, mỗi option chỉ khai báo được tối đa một tên dài và một tên ngắn trong annotation.

Bài học thuộc chương **Tùy chọn và đối số** của Spring Shell. Nội dung tập trung vào giới hạn tên option theo phiên bản, cách dùng alias trong Spring Shell 3.x, thay đổi API ở 4.x và cách duy trì tương thích khi nâng cấp ứng dụng.

Sau bài học, bạn có thể:

- Phân biệt tên dài, tên ngắn, alias của option và alias của command.
- Xác định số tên ngắn và tên dài một option có thể khai báo trong Spring Shell 3.x và 4.x.
- Viết đúng annotation và programmatic registration theo API của từng phiên bản.
- Chuyển đổi cấu hình nhiều alias từ 3.x sang 4.x.
- Chọn cách xử lý tương thích khi CLI cần tiếp tục nhận các tên option cũ.

## Tên dài, tên ngắn và alias

Option là đầu vào có tên của command. Tên dài thường có nhiều ký tự và được viết với tiền tố `--`; tên ngắn là một ký tự và được viết với tiền tố `-`.

Ví dụ:

```text
report export --format csv
report export -f csv
```

Hai cách gọi trên có thể cùng truyền giá trị `csv` cho option định dạng. Trong cách khai báo có alias, một tên được chọn làm tên chính và những tên còn lại là cách viết thay thế của cùng option.

Cần phân biệt hai loại alias:

| Loại | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Alias của option | `--format`, `--output-format`, `-f` | Nhiều cách viết để cung cấp cùng một giá trị cho một option. |
| Alias của command | `report export`, `export-report` | Nhiều tên gọi để chạy cùng một command. |

Alias của command không làm tăng số tên dài hoặc tên ngắn mà một option được phép khai báo. Đây là hai phần metadata độc lập.

## Giới hạn trong Spring Shell 3.x

Trong API annotation hiện đại của Spring Shell 3.x, `@Option` khai báo:

- `longNames` có kiểu `String[]`.
- `shortNames` có kiểu `char[]`.

Mỗi mảng có thể chứa nhiều tên. Phần tử đầu tiên là tên chính; các phần tử sau là alias của cùng option. API không đặt ra một con số tối đa cụ thể trong khai báo; số lượng thực tế bị giới hạn bởi kích thước mảng và tính hữu ích của giao diện CLI.

Ví dụ dùng Spring Shell 3.4.x:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReportCommands {

    @Command(command = "report export")
    public String export(
            @Option(
                    longNames = {"format", "output-format"},
                    shortNames = {'f', 'o'},
                    description = "Định dạng file xuất") String format) {
        return "Định dạng xuất: " + format;
    }
}
```

Với khai báo này, tên chính là `--format` và `-f`. Hai alias là `--output-format` và `-o`. Người dùng có thể gọi:

```text
report export --format csv
report export --output-format csv
report export -f csv
report export -o csv
```

Tất cả các cách gọi trên đều cung cấp giá trị cho tham số `format` của method. Mỗi tên ngắn vẫn là một ký tự; `shortNames` là mảng các ký tự, không phải danh sách chuỗi tùy ý.

### Khai báo nhiều tên bằng CommandRegistration

Spring Shell 3.x cũng hỗ trợ nhiều tên trong programmatic registration. Builder cung cấp `longNames(String...)` và `shortNames(Character...)`:

```java
import org.springframework.shell.command.CommandRegistration;

CommandRegistration registration = CommandRegistration.builder()
    .command("report export")
    .withOption()
        .longNames("format", "output-format")
        .shortNames('f', 'o')
        .type(String.class)
        .required()
        .and()
    .withTarget()
        .function(ctx -> "Định dạng xuất: " + ctx.getOptionValue("format"))
        .and()
    .build();
```

Ở đây, các tên dài và tên ngắn vẫn thuộc về một option. Việc dùng builder hay annotation không làm thay đổi quy tắc alias của dòng 3.x.

### Annotation legacy trong dòng 3.x

Spring Shell 3.x còn có mô hình annotation legacy `@ShellMethod` và `@ShellOption`. Thuộc tính `value` của `@ShellOption` nhận một mảng tên option, có thể chứa cả cách viết dài và ngắn:

```java
@ShellMethod(key = "report export")
String export(
        @ShellOption(value = {
                "--format", "--output-format", "-f", "-o"
        }) String format) {
    return "Định dạng xuất: " + format;
}
```

Đây là mô hình legacy. Khi bắt đầu code mới trong Spring Shell 3.x, nên ưu tiên `@Command` và `@Option`; khi duy trì ứng dụng cũ, cần nhận diện rõ annotation đang dùng để không nhầm `value` của `@ShellOption` với `longNames` và `shortNames` của `@Option`.

## Giới hạn trong Spring Shell 4.x

Spring Shell 4.x thay đổi cấu trúc annotation `@Option`. API ổn định 4.0.3/4.0.4 khai báo:

- `longName` có kiểu `String`.
- `shortName` có kiểu `char`.

Vì vậy, một option có thể không khai báo tên ngắn hoặc khai báo một tên ngắn; tương tự, nó có thể không khai báo tên dài hoặc khai báo một tên dài. Không thể truyền mảng nhiều tên vào cùng một `@Option` như dòng 3.x.

Ví dụ hợp lệ trong Spring Shell 4.x:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReportCommands {

    @Command(name = "report export")
    public String export(
            @Option(
                    longName = "format",
                    shortName = 'f',
                    description = "Định dạng file xuất") String format) {
        return "Định dạng xuất: " + format;
    }
}
```

Người dùng gọi command bằng `--format csv` hoặc `-f csv`. Những khai báo như `longNames = {"format", "output-format"}` hay `shortNames = {'f', 'o'}` không thuộc chữ ký annotation 4.x và sẽ không biên dịch.

### Programmatic model trong 4.x

Trong Spring Shell 4.x, `CommandOption` là record chứa một `shortName` kiểu `char` và một `longName` kiểu `String`. Builder tương ứng cũng cung cấp `shortName(char)` và `longName(String)`, mỗi lời gọi nhận một giá trị:

```java
import org.springframework.shell.core.command.CommandOption;

CommandOption option = CommandOption.with()
    .longName("format")
    .shortName('f')
    .type(String.class)
    .required(true)
    .build();
```

`Command` có thể chứa nhiều `CommandOption`, do đó command vẫn có thể có nhiều option độc lập. Giới hạn ở đây áp dụng cho số tên của từng option, không áp dụng cho tổng số option của command.

## Ma trận so sánh theo phiên bản

| API | Tên dài cho một option | Tên ngắn cho một option | Alias của option |
| --- | --- | --- | --- |
| Spring Shell 3.x `@Option` | Nhiều (`String[] longNames`) | Nhiều (`char[] shortNames`) | Các phần tử sau phần tử đầu tiên là alias. |
| Spring Shell 3.x `CommandRegistration` | Nhiều (`longNames(String...)`) | Nhiều (`shortNames(Character...)`) | Hỗ trợ nhiều tên trên cùng option. |
| Spring Shell 3.x legacy `@ShellOption` | Nhiều tên trong `value` | Nhiều tên trong `value` | Mảng `value` có thể chứa cả tên dài và ngắn. |
| Spring Shell 4.x `@Option` | Tối đa một (`String longName`) | Tối đa một (`char shortName`) | Không có mảng alias cho option. |
| Spring Shell 4.x `CommandOption` | Tối đa một (`String longName`) | Tối đa một (`char shortName`) | Mô hình dữ liệu lưu một cặp tên. |

Lưu ý: một tên ngắn luôn là một ký tự ở cả hai dòng phiên bản. Khả năng khai báo nhiều tên ngắn trong 3.x có nghĩa là nhiều alias một ký tự, không có nghĩa một alias có thể gồm nhiều ký tự như `-out`.

## Nhiều option trong cùng một command

Giới hạn một cặp tên trong Spring Shell 4.x không giới hạn số option độc lập mà command có thể nhận. Mỗi tham số method có thể khai báo một `@Option` riêng:

```java
@Command(name = "report export")
public String export(
        @Option(longName = "format", shortName = 'f') String format,
        @Option(longName = "output", shortName = 'o') String output,
        @Option(longName = "overwrite") boolean overwrite) {
    return "format=" + format
            + ", output=" + output
            + ", overwrite=" + overwrite;
}
```

Command này có ba option độc lập:

| Option | Tên dài | Tên ngắn |
| --- | --- | --- |
| Định dạng | `--format` | `-f` |
| Đường dẫn đầu ra | `--output` | `-o` |
| Ghi đè | `--overwrite` | Không khai báo |

Mỗi option có tối đa một tên dài và một tên ngắn, nhưng command có thể khai báo nhiều tham số option tùy theo nhu cầu nghiệp vụ và chữ ký method.

## Alias của command không phải alias của option

Trong Spring Shell 4.x, annotation `@Command` vẫn có thuộc tính `alias` dạng mảng để khai báo nhiều tên thay thế cho command. Ví dụ:

```java
@Command(
    name = "report export",
    alias = {"export-report", "report save"})
public String export(
        @Option(longName = "format", shortName = 'f') String format) {
    return "Định dạng xuất: " + format;
}
```

Ở đây, người dùng có thể gọi command bằng `report export`, `export-report` hoặc `report save`. Dù command có nhiều alias, option `format` vẫn chỉ có `--format` và `-f`. Không thể dùng `@Command(alias = ...)` để thêm alias như `--output-format` cho option.

## Chuyển ứng dụng từ 3.x lên 4.x

Khi nâng cấp, các khai báo nhiều tên trong `@Option` 3.x cần được rà soát. Ví dụ:

```java
// Spring Shell 3.x
@Option(
    longNames = {"format", "output-format"},
    shortNames = {'f', 'o'}) String format
```

Không thể chuyển nguyên văn sang annotation 4.x. Có một số hướng xử lý tùy mục tiêu tương thích.

### Chọn một tên chuẩn

Nếu không cần duy trì cú pháp cũ, giữ lại một tên dài và một tên ngắn:

```java
@Option(longName = "format", shortName = 'f') String format
```

Đồng thời cập nhật script, tài liệu, ví dụ và hướng dẫn sử dụng để gọi `--format` hoặc `-f`.

### Giữ tên cũ dưới dạng option riêng

Nếu cần một giai đoạn chuyển tiếp, có thể khai báo tên cũ như một option riêng rồi hợp nhất giá trị trong method. Cần xử lý rõ trường hợp người dùng truyền cả hai:

```java
@Command(name = "report export")
public String export(
        @Option(longName = "format", shortName = 'f') String format,
        @Option(longName = "output-format") String legacyFormat) {

    if (format != null && legacyFormat != null) {
        throw new IllegalArgumentException(
            "Chỉ truyền một trong --format hoặc --output-format");
    }

    String selectedFormat = format != null ? format : legacyFormat;
    return "Định dạng xuất: " + selectedFormat;
}
```

Đây là hai option độc lập được xử lý chung trong method, không phải alias thật sự của một option. Phần trợ giúp sẽ hiển thị hai option riêng và ứng dụng phải xác định cách xử lý khi cả hai cùng xuất hiện.

### Chuẩn hóa tên cũ bằng parser tùy chỉnh

Nếu muốn giữ nhiều cách viết nhưng chỉ có một option chuẩn trong command metadata, có thể triển khai `CommandParser` tùy chỉnh để chuyển tên cũ thành tên chuẩn trước khi gọi parser mặc định. Ví dụ, chuẩn hóa `--output-format` thành `--format` và `-o` thành `-f`.

Cách này giữ handler chỉ biết một option, nhưng parser phải xử lý token chính xác, không thay chuỗi bên trong giá trị có dấu nháy hoặc đối số thông thường. Cần kiểm thử các trường hợp có khoảng trắng, dấu `=`, quoting và escaping trước khi dùng trong môi trường thật.

## Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `longNames` không biên dịch trong 4.x | API 4.x dùng `longName` dạng `String`. | Chọn một tên dài cho option. |
| `shortNames` không biên dịch trong 4.x | API 4.x dùng `shortName` dạng `char`. | Chọn một ký tự ngắn cho option. |
| Chỉ một trong các tên 3.x hoạt động sau nâng cấp | Các alias còn lại chưa được chuyển đổi. | Cập nhật script hoặc tạo option tương thích riêng/parser chuẩn hóa. |
| Nhầm alias command thành alias option | Hai loại alias nằm ở hai annotation khác nhau. | Dùng `@Command(alias = ...)` cho tên command; dùng `@Option` cho tên option. |
| Dùng chuỗi nhiều ký tự làm tên ngắn | Short name chỉ là một ký tự. | Dùng tên dài như `--output-format` cho chuỗi nhiều ký tự. |
| Người dùng truyền cả tên chuẩn và tên tương thích | Hai option riêng cùng được cung cấp. | Từ chối trường hợp đồng thời hoặc quy định rõ ưu tiên. |

## Checklist chọn tên option

1. Xác định phiên bản Spring Shell và package annotation đang sử dụng.
2. Chọn một tên dài dễ hiểu làm tên chuẩn.
3. Chọn một ký tự ngắn dễ nhớ nếu command thường được nhập thủ công.
4. Với Spring Shell 3.x, chỉ thêm alias khi có nhu cầu tương thích hoặc tiện dụng rõ ràng.
5. Với Spring Shell 4.x, không truyền mảng tên vào `@Option`; nếu cần giữ cú pháp cũ, chọn giải pháp tương thích có kiểm thử.
6. Kiểm tra alias của command riêng biệt với tên option.
7. Cập nhật tài liệu, trợ giúp, script và kiểm thử sau khi thay đổi tên.

## Ghi nhớ

Spring Shell 3.x cho phép một option có nhiều tên dài và nhiều tên ngắn thông qua mảng `longNames` và `shortNames`; tên đầu tiên là tên chính, các tên còn lại là alias. Spring Shell 4.x dùng `longName` và `shortName` dạng đơn, nên mỗi option có tối đa một tên dài và một tên ngắn. Số lượng option độc lập trong một command không bị giới hạn bởi thay đổi này. Khi nâng cấp, cần quyết định tên chuẩn và cách duy trì các cách viết cũ thay vì chuyển nguyên văn annotation 3.x sang 4.x.

## Tài liệu tham khảo

- [Spring Shell 3.4.3 API — `@Option`](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Option.html): `longNames` và `shortNames` dạng mảng; phần tử đầu tiên là tên chính, các phần tử sau là alias.
- [Spring Shell 3.4 — Short Format](https://docs.spring.io/spring-shell/reference/3.4/options/short.html): tên ngắn và cách khai báo qua programmatic, annotation hiện đại và annotation legacy.
- [Spring Shell 3.4.3 API — CommandRegistration.OptionSpec](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.OptionSpec.html): các phương thức `longNames(String...)` và `shortNames(Character...)`.
- [Spring Shell 4.0.4 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html): cách dùng option và argument trong Spring Shell 4.x.
- [Spring Shell 4.0.3 API — `@Option`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html): `longName` kiểu `String` và `shortName` kiểu `char`.
- [Spring Shell 4.0.3 API — `CommandOption`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.html): record lưu một tên ngắn và một tên dài cho mỗi option.
