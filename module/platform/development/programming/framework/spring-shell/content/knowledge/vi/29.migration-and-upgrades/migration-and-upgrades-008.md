# Đối chiếu tùy chọn, đối số, arity và quy tắc Boolean sau khi đổi parser

Khi nâng cấp Spring Shell 3.x lên 4.x, cách khai báo tham số command và cách parser phân loại token thay đổi đáng kể. Trong mô hình cũ, tham số của `@ShellMethod` thường được ánh xạ thành option có tên theo tham số; option có thể có nhiều alias và có thể nhận nhiều token thông qua `arity`. Trong mô hình 4.x, option là giá trị có tên, argument là giá trị theo vị trí, và dữ liệu nhiều giá trị được khai báo bằng `@Arguments`.

Nếu chỉ đổi `@ShellOption` thành `@Option` mà giữ nguyên cách gọi cũ, script và người dùng có thể gặp lỗi: option alias không còn được nhận diện, danh sách file không được bind như trước hoặc Boolean flag làm thay đổi cách parser phân loại token tiếp theo. Vì vậy, cần đối chiếu cả annotation, cú pháp dòng lệnh và kết quả binding.

Bài học thuộc chương **Di chuyển và nâng cấp**. Nội dung tập trung vào chuyển đổi option/argument, arity của option và collection, Boolean flag, cú pháp parser mới và các mốc sửa lỗi trong Spring Shell 4.0.x.

Sau bài học, bạn có thể:

- Phân biệt option có tên với argument theo vị trí.
- Chuyển tham số `@ShellMethod` sang `@Option`, `@Argument` hoặc `@Arguments`.
- Đối chiếu `OptionArity` của 3.x với cách nhận nhiều argument trong 4.x.
- Nhận biết giới hạn alias của `@Option` mới.
- Dự đoán giá trị Boolean khi option vắng mặt, xuất hiện dạng flag hoặc có giá trị tường minh.
- Hiểu cách parser quyết định token `true`/`false` có thuộc Boolean option hay argument.
- Kiểm thử các cú pháp quan trọng trước khi thay parser trong script và CI.

## Thay đổi mô hình: option và argument là hai loại dữ liệu khác nhau

Option là dữ liệu có tên, thường dùng cho cấu hình hoặc cờ điều khiển. Argument là dữ liệu theo vị trí, thường dùng cho đối tượng mà command thao tác, chẳng hạn tên file, mã dự án hoặc tên người dùng.

| Thành phần | Spring Shell 3.3.x, legacy annotation | Spring Shell 4.x |
| --- | --- | --- |
| Command class | `@ShellComponent` | Bean Spring, thường là `@Component`. |
| Method command | `@ShellMethod` | `@Command`. |
| Tham số có tên | `@ShellOption`; tham số thường được suy ra thành option theo tên tham số | `@Option`. |
| Argument vị trí | Legacy model không có cách khai báo positional argument rõ như mô hình mới | `@Argument(index = ...)`. |
| Nhiều argument còn lại | Thường dùng option kiểu mảng với arity | `@Arguments` trên array hoặc collection. |
| Alias option | Có thể khai báo nhiều tên trong mảng `value` | Một `shortName` và một `longName` cho mỗi option. |
| Arity option | Có thể điều khiển số token option nhận | `@Option` không còn thuộc tính arity. |

Spring Shell 4.x đã loại bỏ các legacy annotation `@ShellComponent`, `@ShellMethod`, `@ShellOption` và các annotation liên quan. Mô hình mới dùng `@Command`, `@Option`, `@Argument` và `@Arguments` trong package `org.springframework.shell.core.command.annotation`.

Một điểm cần phân biệt: Spring Shell 3.x có `position(int)` trong programmatic `CommandRegistration` để ánh xạ token positional chưa được nhận diện vào một option. Đây là quy tắc binding của option theo vị trí, không phải annotation `@Argument` trên tham số method. Trong 4.x, `@Argument(index = ...)` biểu diễn positional argument trực tiếp và dễ đọc hơn.

### Ví dụ khác biệt giữa tham số có tên và tham số theo vị trí

Trong legacy model 3.3.x, tham số phương thức thường được dùng như một option có tên theo tên tham số:

```java
@ShellComponent
class GreetingCommands {

    @ShellMethod(key = "greet")
    String greet(String name) {
        return "Hello " + name;
    }
}
```

Lệnh được gọi với tên tham số:

```text
greet --name Alice
```

Trong Spring Shell 4.x, khai báo rõ dữ liệu nào là argument và dữ liệu nào là option:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class GreetingCommands {

    @Command(name = "greet")
    String greet(
            @Argument(index = 0, defaultValue = "World") String name,
            @Option(shortName = 'u', longName = "uppercase") boolean uppercase) {
        String greeting = "Hello " + name;
        return uppercase ? greeting.toUpperCase() : greeting;
    }
}
```

Các cách gọi tương ứng:

```text
greet Alice
greet --uppercase Alice
greet Alice --uppercase
```

Trong 4.x, `@Argument(index = 0)` xác định argument vị trí đầu tiên; `@Option` xác định option có tên. Không nên chuyển một tham số legacy sang `@Argument` chỉ vì tên Java của nó giống một danh từ. Trước tiên cần xem người dùng đang truyền dữ liệu theo dạng `--name value` hay `command value`.

## Cú pháp option và argument trong parser 4.x

Parser mặc định của Spring Shell 4.x hỗ trợ:

| Dạng | Ví dụ |
| --- | --- |
| Option dài dùng dấu cách | `--format csv` |
| Option dài dùng dấu bằng | `--format=csv` |
| Option ngắn dùng dấu cách | `-f csv` |
| Option ngắn dùng dấu bằng | `-f=csv` |
| Argument vị trí | `report.csv` |

Option và argument có thể xuất hiện theo nhiều thứ tự. Argument được đánh chỉ số từ `0` trong nhóm argument. Ví dụ:

```text
deploy release staging --version 2.4.0 --dry-run
deploy release --dry-run staging --version=2.4.0
deploy release --version=2.4.0 staging --dry-run
```

Các dạng trên có thể được phân tích theo cùng một tập dữ liệu: argument môi trường `staging`, option `version` và Boolean option `dry-run`.

Một số quy tắc cần nhớ:

- Short option chỉ gồm một ký tự.
- Không hỗ trợ gộp nhiều short option như `-abc`.
- Option thông thường cần một giá trị.
- Boolean option có thể dùng dạng flag không có giá trị hoặc nhận `true`/`false` tường minh.
- Ưu tiên option có tên khi có nhiều argument hoặc subcommand để tránh mơ hồ.

### Quoting và escaping

Token có khoảng trắng phải được đặt trong dấu nháy đơn hoặc nháy kép:

```text
report create --name "Monthly sales report"
report create --name='Monthly sales report'
```

Parser bỏ dấu nháy bao ngoài, nên giá trị nhận được là `Monthly sales report`. Có thể dùng loại dấu nháy còn lại bên trong giá trị:

```text
message send --text "I'm ready"
message send --text 'He said "Ready"'
```

Nếu cần dùng chính dấu nháy bao ngoài bên trong giá trị, escape bằng backslash. Backslash literal bên trong quoted value cũng cần escape:

```text
message send --text "He said \"Ready\""
path show --value "C:\\work\\reports"
```

Quote không cân bằng bị parser từ chối. Khi nâng cấp, nên kiểm tra script có chứa đường dẫn Windows, dấu nháy lồng nhau hoặc nội dung có khoảng trắng.

## Arity của option trong Spring Shell 3.3.x

Arity mô tả số token mà một option nhận. Trong 3.3.x, `CommandRegistration` và annotation model mới hỗ trợ các mức sau:

| `OptionArity` | Số token tối thiểu | Số token tối đa |
| --- | ---: | ---: |
| `ZERO` | 0 | 0 |
| `ZERO_OR_ONE` | 0 | 1 |
| `EXACTLY_ONE` | 1 | 1 |
| `ZERO_OR_MORE` | 0 | Không giới hạn thực tế |
| `ONE_OR_MORE` | 1 | Không giới hạn thực tế |

Ví dụ trong annotation model 3.3.x:

```java
import org.springframework.shell.command.CommandRegistration.OptionArity;
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;

@Command(command = "report export")
String export(
        @Option(arity = OptionArity.EXACTLY_ONE) String format,
        @Option(arityMin = 1, arityMax = 3) String[] columns) {
    return format + ": " + Arrays.toString(columns);
}
```

Với programmatic registration, có thể đặt min/max trực tiếp:

```java
import org.springframework.shell.command.CommandRegistration;

CommandRegistration.builder()
    .command("report export")
    .withOption()
        .longNames("columns")
        .type(String[].class)
        .arity(1, 3)
        .and()
    .build();
```

Legacy annotation `@ShellOption` chỉ cho phép khai báo arity tối đa qua `arity`; nó không hỗ trợ đặt min riêng. Annotation model mới của 3.3.x có `arityMin` và `arityMax`, còn programmatic API có thể dùng `arity(min, max)` hoặc `OptionArity`.

Khi arity không khớp, parser có thể báo thiếu hoặc thừa giá trị. Ví dụ option yêu cầu tối thiểu một và tối đa hai giá trị:

```text
files --items
```

Không đủ giá trị. Hai dạng sau hợp lệ:

```text
files --items one
files --items one two
```

Ba giá trị vượt giới hạn:

```text
files --items one two three
```

## Arity sau khi chuyển sang Spring Shell 4.x

Trong mô hình 4.x, `@Option` không còn thuộc tính `arity`, `arityMin` hoặc `arityMax`. Option có tên được dùng cho một giá trị; dữ liệu nhiều giá trị nên chuyển thành positional arguments.

Spring Shell 4.x cung cấp hai annotation:

| Annotation | Dùng cho | Kiểu tham số |
| --- | --- | --- |
| `@Argument(index = n)` | Một argument ở vị trí xác định | Một kiểu dữ liệu đơn. |
| `@Arguments` | Một tập hợp argument còn lại | Array hoặc collection như `List`/`Set`. |

`@Arguments` mặc định thu thập tất cả argument còn lại. Từ Spring Shell 4.0.2, thuộc tính `arity` cho phép đặt số lượng tối đa được thu thập. Thuộc tính này không biểu diễn min/max như `OptionArity`; nếu cần ít nhất hoặc chính xác một số phần tử, ứng dụng phải tự kiểm tra kích thước collection.

Ví dụ:

```java
@Command(name = "files inspect")
String inspect(@Arguments(arity = 3) List<String> paths) {
    if (paths.isEmpty()) {
        throw new IllegalArgumentException("Cần ít nhất một đường dẫn");
    }
    return String.join(", ", paths);
}
```

Ở đây `arity = 3` đặt giới hạn tối đa ba argument; nó không tự yêu cầu đúng ba phần tử. Kiểm tra tối thiểu hoặc chính xác phải nằm trong validation của command/service.

## Chuyển option nhiều giá trị thành @Arguments

Một trường hợp thường gặp là command xóa nhiều file. Trong 3.3.x, danh sách file có thể được khai báo như option nhận nhiều token:

```java
import java.util.Arrays;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
class FileCommands {

    @ShellMethod(key = "rm")
    String remove(
            @ShellOption(value = {"-f", "--force"}) boolean force,
            @ShellOption(value = "--files", arity = 2) String[] files) {
        if (files.length != 2) {
            throw new IllegalArgumentException("Cần truyền đúng hai file");
        }
        return "force=" + force + ", files=" + Arrays.toString(files);
    }
}
```

Cách gọi 3.3.x:

```text
rm --files report.csv archive.zip --force
```

Trong 4.x, chuyển danh sách file thành positional arguments:

```java
import java.util.List;

import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class FileCommands {

    @Command(name = "rm")
    String remove(
            @Option(shortName = 'f', longName = "force") boolean force,
            @Arguments(arity = 2) List<String> files) {
        if (files.size() != 2) {
            throw new IllegalArgumentException("Cần truyền đúng hai file");
        }
        return "force=" + force + ", files=" + files;
    }
}
```

Cách gọi 4.x:

```text
rm --force report.csv archive.zip
rm report.csv archive.zip --force
```

Lệnh mới thể hiện hai loại dữ liệu rõ hơn: `--force` là option điều khiển, còn các file là đối tượng được thao tác nên là argument. Nếu cần giới hạn tối đa hai file, `@Arguments(arity = 2)` thực hiện giới hạn đó; phần kiểm tra đúng hai file vẫn do command hoặc service đảm nhiệm.

Nếu nghiệp vụ bắt buộc danh sách phải gắn với một option có tên vì tương thích giao diện bên ngoài, hãy cân nhắc thiết kế command khác hoặc custom parser. Không cố chuyển `arity` của option cũ sang một thuộc tính không còn tồn tại trên `@Option`.

## Alias option thay đổi trong 4.x

Trong 3.3.x, option có thể khai báo nhiều tên. Ví dụ legacy annotation:

```java
@ShellOption(value = {"-f", "--force", "--yes"}) boolean force
```

Hoặc annotation model mới 3.3.x có thể khai báo nhiều short/long names trong các mảng tương ứng.

Trong 4.x, `@Option` chỉ có một `shortName` và một `longName`:

```java
@Option(shortName = 'f', longName = "force") boolean force
```

Do đó, `-f` và `--force` vẫn cùng trỏ đến một option, nhưng alias thứ ba như `--yes` không còn khai báo trực tiếp trong annotation. Migration cần:

1. Chọn một tên ngắn và một tên dài làm tên chuẩn.
2. Cập nhật script, tài liệu và automation dùng alias cũ.
3. Nếu phải giữ nhiều alias tương thích, cân nhắc cung cấp `CommandParser` tùy chỉnh để chuẩn hóa alias cũ sang tên chuẩn trước khi binding.

Thuộc tính `label` của option cũng đã bị loại bỏ. Trong 3.x, label chỉ được dùng cho chuỗi help; khi chuyển sang 4.x, chuyển nội dung cần hiển thị sang `description`.

## Quy tắc Boolean trong 3.3.x

Boolean thường được dùng làm flag. Spring Shell 3.3.x phân biệt primitive `boolean` và wrapper `Boolean`:

| Khai báo | Khi không truyền option và không có default | Khi có flag | Khi truyền giá trị |
| --- | --- | --- | --- |
| `boolean` | `false` | `true` | Có thể truyền `true`/`false` theo cấu hình arity phù hợp. |
| `Boolean` | `null` | `true` | `true` hoặc `false`. |
| Có `defaultValue` | Giá trị default khi vắng mặt | Phụ thuộc cách khai báo arity/flag | Dùng test để xác nhận cú pháp flag và giá trị tường minh của command. |

Tài liệu Types của 3.3.x minh họa `Boolean` không có default nhận `null` khi vắng mặt, `--arg4` nhận `true`, còn `--arg4 false` nhận `false`. Với primitive `boolean`, giá trị mặc định của Java là `false`.

Trong legacy `@ShellOption`, `arity` mặc định dùng heuristic: tham số Boolean có arity `0`, kiểu khác thường là `1`. Tài liệu Types 3.3.x cũng minh họa `Boolean` có thể nhận cả flag `--arg4` lẫn giá trị tường minh `--arg4 false`. Nếu command phụ thuộc vào cách kết hợp default, flag và giá trị tường minh, hãy giữ các trường hợp đó trong test khi nâng cấp; có thể đặt `arity = 1` khi muốn buộc option nhận một token theo cấu hình legacy.

## Quy tắc Boolean trong parser 4.x

Trong Spring Shell 4.x, option kiểu `boolean` hoặc `Boolean` có thể dùng không kèm giá trị:

```text
deploy release staging --dry-run
```

`--dry-run` được hiểu là `true`. Giá trị tường minh cũng được hỗ trợ:

```text
deploy release staging --dry-run=false
deploy release --dry-run false staging
```

Trong dạng có dấu cách, parser chỉ tiêu thụ token kế tiếp làm giá trị Boolean nếu token đó là `true` hoặc `false`, không phân biệt hoa thường. Nếu token kế tiếp không phải hai giá trị này, nó vẫn là argument:

```text
deploy release --dry-run staging
```

Ở đây `--dry-run` là `true`; `staging` vẫn là argument môi trường. Quy tắc này giúp phân biệt Boolean flag với argument theo vị trí.

Ví dụ command:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class DeploymentCommands {

@Command(name = "deploy release")
String release(
        @Argument(index = 0) String environment,
        @Option(longName = "dry-run", defaultValue = "false") boolean dryRun) {
    return "environment=" + environment + ", dryRun=" + dryRun;
}
}
```

Với khai báo trên:

| Lệnh | `environment` | `dryRun` |
| --- | --- | --- |
| `deploy release staging` | `staging` | `false` |
| `deploy release staging --dry-run` | `staging` | `true` |
| `deploy release --dry-run staging` | `staging` | `true` |
| `deploy release --dry-run=false staging` | `staging` | `false` |
| `deploy release --dry-run false staging` | `staging` | `false` |

Nếu cần trạng thái ba giá trị (không truyền, true, false), dùng `Boolean` thay vì primitive và không đặt default nếu `null` có ý nghĩa nghiệp vụ. Nếu chỉ cần flag bật/tắt, primitive `boolean` với default rõ ràng thường dễ hiểu hơn.

### Chú ý phiên bản vá 4.0.x

Quy tắc Boolean đã có một số lỗi trong các bản đầu của 4.0.x:

| Phiên bản | Ghi nhận | Khuyến nghị |
| --- | --- | --- |
| 4.0.0 | Một số primitive option không nhận được khi thiếu giá trị tường minh. | Không dùng hành vi của bản đầu làm chuẩn cho parser hiện tại. |
| 4.0.1 | Cải thiện parser để chấp nhận Boolean option không có giá trị; vẫn có lỗi trong trường hợp Boolean đi cùng argument hoặc subcommand. | Kiểm tra kỹ lệnh có cả flag và positional argument. |
| 4.0.2 | Sửa Boolean flag không có value trong subcommand và Boolean option không value khi có argument. | Đây là mốc sửa các lỗi parser Boolean quan trọng. |
| 4.0.4 | Sửa xử lý escaped quote trong `DefaultCommandParser`. | Vẫn nên kiểm thử script có quote lồng nhau sau khi nâng cấp. |

Khi ứng dụng cần bare Boolean flag cùng subcommand hoặc argument, nên dùng patch release đã có các bản sửa này và chạy test trên đúng phiên bản dependency thực tế. Không kết luận parser hoạt động chỉ từ một test đơn giản không có argument.

## Khác biệt về parser và khả năng tùy chỉnh

Spring Shell 4.x cung cấp API `CommandParser` mới. Parser mặc định hỗ trợ cú pháp option/argument được mô tả ở trên. Nếu hệ thống cần giữ một cú pháp riêng hoặc cần chuẩn hóa alias cũ, có thể triển khai `CommandParser` và đăng ký implementation thành bean trong application context.

Chỉ nên thay parser khi có yêu cầu tương thích cụ thể. Parser tùy chỉnh phải giữ nhất quán các quy tắc:

- Nhận diện tên command và subcommand.
- Phân biệt option có tên với argument vị trí.
- Xử lý token giá trị option, bao gồm Boolean.
- Xử lý quoting và escaping.
- Báo lỗi khi thiếu giá trị, thừa giá trị hoặc cú pháp không hợp lệ.
- Không làm thay đổi ý nghĩa của script đã phát hành mà không có kế hoạch migration.

Nếu chỉ cần thêm một alias hoặc chuyển option nhiều giá trị sang argument, hãy cân nhắc cập nhật command và script trước khi tự viết parser mới. Parser tùy chỉnh làm tăng trách nhiệm kiểm thử và bảo trì cú pháp.

## Quy trình migration đề xuất

1. **Liệt kê command hiện có:** ghi lại tên command, option, alias, kiểu dữ liệu, default và script đang sử dụng.
2. **Phân loại từng tham số:** đánh dấu dữ liệu là option có tên, một argument vị trí hay danh sách argument.
3. **Ghi lại arity:** xác định option cũ nhận 0, 1 hoặc nhiều token; kiểm tra min/max có được dùng không.
4. **Chuyển annotation:** thay legacy annotation bằng `@Command`, `@Option`, `@Argument` hoặc `@Arguments`.
5. **Chuẩn hóa alias:** giữ một short name và một long name; cập nhật alias bổ sung trong script hoặc custom parser nếu cần.
6. **Xử lý Boolean:** quyết định primitive/wrapper, default và cú pháp flag/giá trị tường minh.
7. **Cập nhật script:** chuyển multi-value option thành positional arguments và cập nhật các lệnh dùng alias cũ.
8. **Chạy test ma trận:** kiểm tra parser, binding, Boolean, arity, quoting và command output.
9. **Nâng cấp theo baseline:** migration guide khuyến nghị nâng ứng dụng lên Spring Shell 3.4.x mới nhất trước khi chuyển sang 4.x; Spring Shell 4.x yêu cầu nền Spring Framework 7 và Spring Boot 4 khi dùng Boot.

## Ma trận kiểm thử sau migration

Ít nhất nên kiểm thử các trường hợp sau trên đúng phiên bản Spring Shell 4.x mà ứng dụng sẽ phát hành:

| Nhóm | Input cần kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Named option | `--format csv` | Giá trị option là `csv`. |
| Option bằng dấu `=` | `--format=csv` | Kết quả giống dạng dấu cách. |
| Short option | `-f csv` | Binding đúng short name. |
| Positional argument | `deploy release staging` | Argument index 0 là `staging`. |
| Option sau argument | `deploy release staging --dry-run` | Argument và Boolean đều đúng. |
| Boolean bare flag | `--dry-run` | Boolean là `true`. |
| Boolean false tường minh | `--dry-run=false` | Boolean là `false`. |
| Boolean dạng dấu cách | `--dry-run false staging` | `false` được tiêu thụ làm Boolean; `staging` vẫn là argument. |
| Boolean theo sau bởi token khác | `--dry-run staging` | `staging` không bị tiêu thụ làm Boolean. |
| Nhiều argument | `rm file1 file2 --force` | Collection chứa hai file. |
| Vượt arity tối đa | Truyền quá số phần tử `@Arguments(arity = n)` | Parser không thu thập vượt giới hạn đã đặt; phần token dư phải được xử lý hoặc báo lỗi theo khai báo command. |
| Quoting | `--name "Monthly sales report"` | Giá trị giữ nguyên khoảng trắng. |
| Escaped quote | `--message "He said \"Hi\""` | Giá trị nhận được chứa dấu nháy literal. |
| Alias cũ | Dùng alias bổ sung từng tồn tại trong 3.x | Được cập nhật hoặc chuẩn hóa theo chính sách tương thích. |

Test nên chạy qua `ShellTestClient` hoặc test API tương ứng của phiên bản 4.x để xác nhận parser, command registry và argument binding cùng hoạt động. Gọi trực tiếp method Java không kiểm tra được cách parser tách token.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@ShellOption` không biên dịch trong 4.x | Legacy annotations đã bị loại bỏ. | Chuyển sang `@Option`, `@Argument` hoặc `@Arguments`. |
| Tham số không còn nhận bằng `--name value` | Tham số đã chuyển thành positional `@Argument`. | Nếu cần giữ cú pháp có tên, dùng `@Option`; nếu muốn positional, cập nhật script. |
| Option cũ có nhiều alias nhưng chỉ một alias còn hoạt động | `@Option` 4.x chỉ có một short name và một long name. | Chọn tên chuẩn, cập nhật script hoặc dùng custom parser cho alias cần giữ. |
| `arity` không còn tồn tại trên `@Option` | Option arity đã bị loại bỏ trong 4.x. | Chuyển danh sách nhiều giá trị sang `@Arguments`. |
| `@Arguments(arity = 2)` vẫn chấp nhận ít hơn hai phần tử | `arity` của `@Arguments` là giới hạn tối đa, không phải min/max. | Kiểm tra kích thước collection trong validation. |
| Boolean flag không hoạt động cùng subcommand/argument ở 4.0.0/4.0.1 | Lỗi parser ở các bản đầu 4.x. | Dùng patch có bản sửa và kiểm thử trên phiên bản thực tế. |
| Token `staging` bị hiểu thành Boolean | Dùng cú pháp hoặc custom parser khác với quy tắc mặc định. | Kiểm tra Boolean token; chỉ `true`/`false` mới được tiêu thụ làm giá trị Boolean. |
| `--verbose` không bật cờ | Giá trị mặc định hoặc kiểu tham số không phải Boolean. | Dùng `boolean`/`Boolean`, đặt default rõ ràng và kiểm tra annotation. |
| Không phân biệt được vắng mặt với false | Dùng primitive `boolean` khi cần trạng thái ba giá trị. | Dùng `Boolean` và xử lý `null` như trạng thái không truyền. |
| `-abc` không được nhận | Parser không hỗ trợ gộp short option. | Viết `-a -b -c` hoặc dùng long option. |
| Script có quote không đóng bị lỗi | Parser mới kiểm tra quote/escape nghiêm ngặt. | Sửa quoting và thêm test cho script có dấu nháy lồng nhau. |

## Checklist trước khi phát hành

- [ ] Đã phân loại mọi tham số thành option, argument đơn hoặc collection argument.
- [ ] Đã chuyển `@ShellComponent`, `@ShellMethod`, `@ShellOption` sang annotation 4.x.
- [ ] Đã thay tham số legacy mặc định theo tên thành `@Option` hoặc `@Argument` phù hợp.
- [ ] Đã thay multi-value option bằng `@Arguments` khi phù hợp.
- [ ] Đã kiểm tra lại arity: giới hạn tối đa và số lượng tối thiểu.
- [ ] Đã kiểm tra tất cả alias short/long và script cũ.
- [ ] Mỗi `@Option` có tối đa một short name và một long name.
- [ ] Đã kiểm tra Boolean primitive, wrapper, default và explicit false.
- [ ] Đã kiểm tra Boolean flag cùng argument và subcommand trên patch 4.x mục tiêu.
- [ ] Đã kiểm tra option có dấu `=` và dấu cách.
- [ ] Đã kiểm tra quoting, escaping và token có khoảng trắng.
- [ ] Đã chạy command test qua shell parser, không chỉ gọi method trực tiếp.
- [ ] Đã cập nhật help, tài liệu và script theo cú pháp mới.

## Ghi nhớ

Trong Spring Shell 3.3.x, option có thể có nhiều alias và arity điều khiển số token mà option nhận. Legacy `@ShellOption` chỉ đặt được arity tối đa; annotation model mới có min/max. Trong 4.x, `@Option` chỉ khai báo một short name và một long name, không còn option arity. Dữ liệu nhiều giá trị nên chuyển thành `@Arguments` trên array/collection; `@Arguments.arity` từ 4.0.2 là giới hạn tối đa, nên min/exact count cần validation riêng. Dùng `@Argument(index = ...)` cho dữ liệu theo vị trí. Boolean flag có thể không kèm giá trị; nếu token tiếp theo là `true` hoặc `false`, parser tiêu thụ nó làm giá trị, còn token khác vẫn là argument. Kiểm thử cả hai dạng Boolean cùng subcommand/argument và kiểm tra patch version vì các lỗi parser quan trọng được sửa trong 4.0.2.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Arity](https://docs.spring.io/spring-shell/reference/3.3/options/arity.html): OptionArity, min/max và giới hạn của legacy annotation.
- [Spring Shell 3.3.4 — Types](https://docs.spring.io/spring-shell/reference/3.3/options/types.html): primitive/wrapper Boolean, default value và ví dụ flag.
- [Spring Shell 3.3.0 API — `ShellOption`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/ShellOption.html): alias, default value và heuristic arity của Boolean.
- [Spring Shell 3.3.0 API — `Option`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/annotation/Option.html): nhiều short/long aliases, arity và min/max trong annotation model mới.
- [Spring Shell 3.3.4 — Legacy Option Annotation](https://docs.spring.io/spring-shell/reference/3.3/options/basics/legacyannotation.html): tham số legacy và tên option.
- [Spring Shell 3.3.4 — Legacy Command Annotation](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/legacyannotation.html): `@ShellComponent`, `@ShellMethod` và cách đăng ký command.
- [Spring Shell 4.0.4 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html): `@Option`, `@Argument`, `@Arguments`, parsing, Boolean, quoting và escaping.
- [Spring Shell 4.0.4 API — `Option`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html): thuộc tính shortName, longName, required và defaultValue.
- [Spring Shell 4.0.4 API — `Argument`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Argument.html): argument index và default value.
- [Spring Shell 4.0.4 API — `Arguments`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Arguments.html): collection argument và giới hạn arity tối đa từ 4.0.2.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): loại bỏ legacy annotations, giới hạn alias option và baseline nâng cấp.
- [Spring Shell Releases](https://github.com/spring-projects/spring-shell/releases): các bản sửa Boolean parser, `@Arguments.arity` và quoting trong 4.0.1, 4.0.2 và 4.0.4.
- [Spring Shell Issue #1263](https://github.com/spring-projects/spring-shell/issues/1263): lý do chuyển multi-valued option sang arguments và bổ sung arity cho `@Arguments`.
