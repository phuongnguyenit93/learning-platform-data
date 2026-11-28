# Khai báo tên ngắn, tên dài và mô tả cho option

Một command dễ sử dụng cần có tên option nhất quán và phần mô tả đủ rõ để người dùng biết mỗi option làm gì. Trong Spring Shell, một option có thể có tên dài như `--output` và tên ngắn như `-o`; cả hai tên có thể cùng ánh xạ đến một tham số Java. Phần mô tả của command và mô tả của từng option được dùng để tạo trợ giúp, giúp người dùng khám phá cú pháp ngay trong shell.

Bài học tập trung vào cách khai báo tên ngắn, tên dài, bí danh và mô tả bằng annotation trong Spring Shell 3.x. Các ví dụ dùng `@Command` và `@Option`; cuối bài có phần đối chiếu cách khai báo programmatic và lưu ý API ở các dòng phiên bản khác.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt tên dài, tên ngắn và bí danh của một option.
- Khai báo `longNames`, `shortNames` và `description` bằng `@Option`.
- Hiểu cách nhiều tên cùng ánh xạ đến một tham số command.
- Viết mô tả cho command và cho từng option để trợ giúp dễ hiểu.
- Phân biệt `description` với `label`, `required` và `defaultValue`.
- Tránh xung đột tên, tên khó nhớ và mô tả gây hiểu nhầm.
- Kiểm tra cách các tên option xuất hiện trong trợ giúp và hoạt động khi gọi command.

## 1. Option có tên dài và tên ngắn

Option là dữ liệu có tên mà người dùng truyền cho command. Spring Shell 3.x hỗ trợ hai dạng tên phổ biến:

- **Tên dài** (*long name*) bắt đầu bằng hai dấu gạch ngang, ví dụ `--output`, `--format`, `--customer-id`.
- **Tên ngắn** (*short name*) bắt đầu bằng một dấu gạch ngang, thường là một ký tự, ví dụ `-o`, `-f`, `-i`.

Hai tên có thể là hai cách gọi của cùng một option:

```text
report export --output report.csv
report export -o report.csv
```

Trong cả hai dòng, người dùng truyền cùng giá trị cho option `output`. Tên ngắn giúp gõ nhanh trong phiên tương tác; tên dài giúp command dễ đọc và tự mô tả trong script.

Một option không bắt buộc phải có cả hai dạng. Có thể chỉ khai báo tên dài nếu muốn cú pháp rõ ràng, hoặc chỉ khai báo tên ngắn trong trường hợp đặc biệt. Với CLI dùng lâu dài, tên dài thường nên là tên chính; tên ngắn là cách viết tắt thuận tiện.

## 2. Khai báo bằng `@Option`

Trong mô hình annotation của Spring Shell 3.x, `@Option` được đặt trên tham số phương thức command. Hai thuộc tính chính để khai báo tên là:

- `longNames`: mảng chuỗi chứa tên dài, không bao gồm tiền tố `--`.
- `shortNames`: mảng ký tự chứa tên ngắn, không bao gồm tiền tố `-`.

Ví dụ:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ReportCommands {

    @Command(command = "report export", description = "Xuất báo cáo ra tệp")
    public String export(
            @Option(
                    longNames = "output",
                    shortNames = 'o',
                    description = "Đường dẫn tệp đầu ra") String output) {
        return "Đã xuất báo cáo tới " + output;
    }
}
```

Ở đây:

- `longNames = "output"` tạo tên dài `--output`.
- `shortNames = 'o'` tạo tên ngắn `-o`.
- `description` giải thích ý nghĩa của option trong trợ giúp.
- Tham số Java `output` nhận giá trị dù người dùng gọi bằng tên dài hay tên ngắn.

Các cách gọi tương đương:

```text
shell:> report export --output report.csv
Đã xuất báo cáo tới report.csv

shell:> report export -o report.csv
Đã xuất báo cáo tới report.csv
```

Khi khai báo annotation, chỉ ghi phần tên như `output` hoặc ký tự `o`. Spring Shell tự xử lý tiền tố hiển thị và cú pháp gọi. Không viết `longNames = "--output"` hoặc `shortNames = '-'`.

## 3. Một option có thể có nhiều tên

`longNames` và `shortNames` đều là mảng. Spring Shell cho phép khai báo nhiều tên cho cùng một option; tên đầu tiên là tên chính, các tên tiếp theo là bí danh (*alias*).

Ví dụ:

```java
@Command(command = "customer find", description = "Tìm khách hàng theo tên")
public String find(
        @Option(
                longNames = {"name", "customer-name"},
                shortNames = {'n', 'c'},
                description = "Tên hoặc bí danh khách hàng") String name) {
    return "Đang tìm khách hàng: " + name;
}
```

Các cách gọi sau cùng ánh xạ đến tham số `name`:

```text
customer find --name Lan
customer find --customer-name Lan
customer find -n Lan
customer find -c Lan
```

Trong ví dụ, `name` là tên dài chính, `customer-name` là bí danh dài; `n` là tên ngắn chính, `c` là bí danh ngắn. Người dùng có thể dùng tên phù hợp với ngữ cảnh, còn command method chỉ cần nhận một tham số.

Không nên tạo quá nhiều bí danh cho một option. Mỗi bí danh là một cú pháp mà nhóm phát triển cần duy trì và tài liệu hóa. Bí danh có ích khi phải tương thích với script cũ hoặc khi người dùng quen một thuật ngữ khác, nhưng số lượng lớn sẽ làm help khó đọc và tăng nguy cơ xung đột.

## 4. Phân biệt tên option với tên tham số Java

Tên tham số Java và tên option có liên quan nhưng không nhất thiết giống nhau. `@Option` cho phép khai báo tên CLI độc lập với tên biến trong phương thức.

```java
@Command(command = "customer find", description = "Tìm khách hàng")
public String find(
        @Option(longNames = "customer-id", shortNames = 'i',
                description = "Mã định danh khách hàng") Long id) {
    return "Customer ID: " + id;
}
```

Người dùng nhập `--customer-id` hoặc `-i`, còn code Java làm việc với biến `id`. Cách tách biệt này hữu ích khi tên option cần theo quy ước CLI nhưng tên biến cần ngắn gọn hoặc theo quy ước Java.

Đối với option được khai báo rõ ràng, nên đặt tên dài phản ánh ý nghĩa mà người dùng hiểu được. Tránh phụ thuộc vào tên tham số Java như một hợp đồng CLI lâu dài: đổi tên biến trong refactor có thể vô tình làm thay đổi cách gọi nếu tên option được suy ra theo quy ước mặc định của mô hình đang dùng.

## 5. Mô tả command và mô tả option

Một CLI có hai cấp mô tả cần được phân biệt.

**Mô tả command** giải thích hành động tổng thể. Trong Spring Shell 3.x, có thể khai báo bằng thuộc tính `description` của `@Command`:

```java
@Command(
        command = "report export",
        description = "Xuất báo cáo theo định dạng và đường dẫn đã chọn")
```

**Mô tả option** giải thích ý nghĩa của một giá trị đầu vào cụ thể. Mô tả này được khai báo bằng thuộc tính `description` của `@Option`:

```java
@Option(
        longNames = "format",
        shortNames = 'f',
        description = "Định dạng báo cáo: csv hoặc json") String format
```

Một command hoàn chỉnh có thể khai báo cả hai cấp:

```java
@Component
public class ReportCommands {

    @Command(
            command = "report export",
            description = "Xuất báo cáo ra tệp theo định dạng được chọn")
    public String export(
            @Option(
                    longNames = "format",
                    shortNames = 'f',
                    description = "Định dạng báo cáo: csv hoặc json") String format,
            @Option(
                    longNames = "output",
                    shortNames = 'o',
                    description = "Đường dẫn tệp đầu ra") String output) {
        return "Đã xuất báo cáo " + format + " tới " + output;
    }
}
```

Mô tả command trả lời câu hỏi “lệnh này làm gì?”. Mô tả option trả lời “giá trị này điều khiển phần nào?”. Không nên lặp lại cùng một câu ở cả hai nơi.

## 6. Mô tả xuất hiện trong trợ giúp như thế nào?

Trợ giúp là một phần của giao diện CLI. Khi người dùng xem trợ giúp command, họ cần biết tên command, công dụng, các option có thể truyền và ý nghĩa của từng option.

Với khai báo ở phần trước, thông tin có thể được trình bày theo dạng minh họa:

```text
NAME
    report export - Xuất báo cáo ra tệp theo định dạng được chọn

OPTIONS
    --format, -f
        Định dạng báo cáo: csv hoặc json

    --output, -o
        Đường dẫn tệp đầu ra
```

Đây là ví dụ giản lược để minh họa nội dung, không phải bản sao cố định của output help. Cách căn lề, thứ tự và nhãn có thể khác theo phiên bản, cấu hình hoặc help renderer của ứng dụng.

Một mô tả tốt nên:

- Dùng động từ cụ thể như “Đường dẫn tệp đầu ra”, “Số bản ghi tối đa” hoặc “Định dạng báo cáo”.
- Nêu đơn vị hoặc tập giá trị hợp lệ khi điều đó giúp người dùng chọn đúng.
- Ngắn gọn nhưng đủ phân biệt option với các option khác.
- Tránh lặp lại tên option mà không giải thích thêm.
- Không ghi thông tin chỉ đúng trong môi trường phát triển nếu command được phát hành cho người dùng khác.

## 7. Phân biệt `description` với `label`

`description` và `label` đều có thể xuất hiện trong trợ giúp nhưng phục vụ hai mục đích khác nhau.

| Thuộc tính | Mục đích | Ví dụ |
|---|---|---|
| `description` | Giải thích option dùng để làm gì | `Đường dẫn tệp đầu ra` |
| `label` | Đặt tên gợi ý cho giá trị option trong synopsis/help | `FILE` |
| `required` | Cho biết option có bắt buộc hay không | `true` |
| `defaultValue` | Giá trị dùng khi người dùng không truyền option, theo quy tắc binding | `report.csv` |

Ví dụ:

```java
@Option(
        longNames = "output",
        shortNames = 'o',
        description = "Đường dẫn tệp đầu ra",
        label = "FILE",
        required = true) String output
```

Trong help, `label` có thể làm synopsis dễ đọc hơn, ví dụ `--output FILE`. `label` không thay thế description và không tự thay đổi hành vi command. Nó là nhãn trình bày cho kiểu hoặc nội dung value.

Tương tự, `required` và `defaultValue` ảnh hưởng đến quy tắc nhận input; chúng không phải phần mô tả. Khi người dùng xem help, cần giữ thông tin bắt buộc và mặc định nhất quán với cách command thực thi.

## 8. Chọn tên dài tốt

Tên dài thường là cách viết dễ đọc nhất trong script và tài liệu. Hãy chọn tên dựa trên ý nghĩa của dữ liệu, không dựa vào chi tiết triển khai bên trong.

Một số nguyên tắc:

- Dùng từ mô tả rõ, ví dụ `--output`, `--format`, `--customer-id`.
- Dùng kebab-case cho tên gồm nhiều từ, thống nhất trong toàn bộ CLI.
- Tránh tên quá chung như `--value`, `--data` hoặc `--type` nếu có thể chọn tên cụ thể hơn.
- Không dùng cùng một tên dài cho hai option khác nhau trong cùng command.
- Giữ tên ổn định vì script và tài liệu bên ngoài có thể phụ thuộc vào chúng.

So sánh:

| Tên khó hiểu | Tên dễ hiểu hơn | Lý do |
|---|---|---|
| `--p` | `--page-size` | Nêu rõ giá trị điều khiển |
| `--out` | `--output` | Dễ đoán và nhất quán |
| `--id` | `--customer-id` | Tránh mơ hồ khi command có nhiều loại ID |
| `--fmt` | `--format` | Rõ nghĩa với người dùng mới |

Không cần kéo dài tên option bằng cách lặp lại toàn bộ tên command. Chọn mức chi tiết vừa đủ để tránh nhầm lẫn trong phạm vi command đó.

## 9. Chọn tên ngắn tốt

Tên ngắn chủ yếu phục vụ thao tác nhanh. Vì chỉ có một ký tự, chúng dễ xung đột hơn tên dài.

Ví dụ:

```text
report export -f csv -o report.csv
```

Một số quy tắc hữu ích:

- Chọn ký tự dễ liên tưởng đến tên dài, chẳng hạn `-f` cho `--format`, `-o` cho `--output`.
- Giữ ý nghĩa của một ký tự nhất quán giữa các command liên quan nếu có thể.
- Tránh gán cùng một short name cho hai option trong cùng command.
- Chỉ thêm short name khi nó thực sự giúp thao tác nhanh.
- Không cố tạo short name cho mọi option nếu ký tự dễ nhớ đã được dùng.

Tên ngắn thường được khai báo dưới dạng một ký tự, ví dụ `shortNames = 'o'`. Trong khi đó tên dài là chuỗi, ví dụ `longNames = "output"`.

### 9.1. Tổ hợp short option

Spring Shell hỗ trợ cách kết hợp một số short option theo quy tắc POSIX, đặc biệt hữu ích với các cờ boolean. Ví dụ, các cờ `-a`, `-b`, `-c` có thể được kết hợp thành `-abc` khi chúng được định nghĩa là boolean flag.

Không nên giả định mọi short option nhận giá trị đều có thể kết hợp an toàn. Với option nhận chuỗi hoặc số, cách phân tích token kết hợp có thể khác và dễ gây mơ hồ. Hãy dùng cú pháp tách rõ ràng như `-o report.csv` và kiểm thử parser của phiên bản đang dùng.

## 10. Bí danh và tương thích ngược

Bí danh có ích khi tên option đã được sử dụng trong script hoặc tài liệu cũ. Ví dụ, một phiên bản CLI trước đây dùng `--out`, còn phiên bản mới muốn chuẩn hóa thành `--output`.

Có thể giữ cả hai tên trong một khoảng thời gian:

```java
@Option(
        longNames = {"output", "out"},
        shortNames = 'o',
        description = "Đường dẫn tệp đầu ra") String output
```

Khi đó `--output`, `--out` và `-o` cùng ánh xạ đến một tham số. Tên đầu tiên trong `longNames` là tên chính, các tên sau là alias. Tương tự, phần tử đầu tiên trong `shortNames` là tên ngắn chính.

Nếu cần loại bỏ alias cũ:

1. Ghi nhận alias nào đang được sử dụng.
2. Thông báo tên mới trong help và tài liệu phát hành.
3. Duy trì alias trong giai đoạn chuyển tiếp nếu cần tương thích.
4. Xóa alias sau khi đã có kế hoạch nâng cấp cho script và người dùng.

Không đổi tên option một cách âm thầm. CLI thường được gọi từ script tự động, nên một thay đổi tên có thể làm pipeline hoặc lịch chạy bị lỗi dù ứng dụng vẫn khởi động bình thường.

## 11. Khai báo option bằng `CommandRegistration`

Ngoài annotation, Spring Shell 3.x cho phép xây dựng metadata option theo cách programmatic bằng `CommandRegistration`. Cách này hữu ích khi command được tạo từ cấu hình hoặc cần đăng ký động.

```java
import org.springframework.shell.command.CommandRegistration;

CommandRegistration registration = CommandRegistration.builder()
        .command("report export")
        .description("Xuất báo cáo ra tệp")
        .withTarget()
            .function(context -> {
                String format = context.getOptionValue("format");
                String output = context.getOptionValue("output");
                return "Đã xuất " + format + " tới " + output;
            })
            .and()
        .withOption()
            .longNames("format")
            .shortNames('f')
            .description("Định dạng báo cáo: csv hoặc json")
            .required()
            .and()
        .withOption()
            .longNames("output", "out")
            .shortNames('o')
            .description("Đường dẫn tệp đầu ra")
            .required()
            .and()
        .build();
```

Trong cách khai báo này, `longNames(...)`, `shortNames(...)` và `description(...)` thiết lập metadata cho từng option. Command-level `.description(...)` mô tả thao tác tổng thể. Các quy tắc về tên chính và alias vẫn cần được tổ chức nhất quán.

## 12. Lưu ý với mô hình annotation legacy

Một số ứng dụng Spring Shell 3.x vẫn sử dụng mô hình annotation cũ `@ShellMethod` và `@ShellOption`. Trong mô hình này, tên option được khai báo qua thuộc tính `value`:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class LegacyReportCommands {

    @ShellMethod(key = "report-export", value = "Xuất báo cáo ra tệp")
    public String export(
            @ShellOption(value = {"--output", "-o"}) String output) {
        return "Đã xuất báo cáo tới " + output;
    }
}
```

Ở mô hình legacy, mảng `value` chứa các cách gọi option, bao gồm tiền tố `--` và `-`. Cách khai báo này khác với `@Option` của annotation model mới, nơi `longNames` và `shortNames` chỉ nhận phần tên không có tiền tố.

Không trộn import của hai mô hình trong cùng ví dụ. Khi dự án dùng `@ShellMethod`, hãy theo tài liệu API của legacy annotation; khi dùng `@Command` và `@Option`, dùng đúng package `org.springframework.shell.command.annotation`.

### 12.1. Khác biệt thuộc tính trong Spring Shell 4.x

Ở Spring Shell 4.x, annotation `@Option` mới dùng thuộc tính số ít `longName` và `shortName` thay cho hai mảng `longNames` và `shortNames` của 3.x. Package annotation cũng chuyển sang `org.springframework.shell.core.command.annotation`.

Ví dụ theo API 4.x:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ReportCommands {

    @Command(name = "report export", description = "Xuất báo cáo ra tệp")
    public String export(
            @Option(
                    longName = "output",
                    shortName = 'o',
                    description = "Đường dẫn tệp đầu ra") String output) {
        return "Đã xuất báo cáo tới " + output;
    }
}
```

Đây là API khác với ví dụ 3.x ở trên. Khi nâng cấp, cần cập nhật import và tên thuộc tính theo phiên bản thực tế; không sao chép nguyên `longNames` hoặc `shortNames` từ 3.x sang 4.x.

## 13. Những lỗi thường gặp

### Ghi cả tiền tố vào `longNames` hoặc `shortNames`

Với annotation model mới, dùng `longNames = "output"` và `shortNames = 'o'`. Không đưa `--` hoặc `-` vào giá trị annotation vì framework đảm nhiệm tiền tố.

### Dùng kiểu dữ liệu sai cho tên ngắn

`shortNames` là mảng ký tự, vì vậy khai báo một ký tự như `'o'`, không phải chuỗi `"o"`. `longNames` là mảng chuỗi.

### Hai option có cùng tên

Nếu cùng một command có hai tham số đăng ký `--format`, parser không thể xác định rõ tham số đích. Hãy kiểm tra tên dài, tên ngắn và alias của tất cả option trong command.

### Mô tả command quá chung chung

Mô tả như “Chạy lệnh” hoặc “Xử lý dữ liệu” không giúp người dùng hiểu hành động. Hãy nêu đối tượng và kết quả chính, ví dụ “Xuất báo cáo doanh thu ra tệp”.

### Mô tả option lặp lại tên option

Mô tả `--output: output` không giải thích giá trị. Nên viết “Đường dẫn tệp đầu ra” hoặc “Thư mục lưu báo cáo”.

### Dùng `label` thay cho `description`

`label` chỉ đặt nhãn value trong help/synopsis. Nó không giải thích mục đích option. Hãy khai báo cả hai khi cần.

### Thay tên chính nhưng quên alias cũ

Script cũ có thể ngừng hoạt động. Nếu đổi tên option, hãy cân nhắc duy trì alias trong thời gian chuyển tiếp và cập nhật tài liệu.

## 14. Kiểm thử tên và mô tả option

Kiểm thử nên xác nhận cả hành vi binding lẫn thông tin trợ giúp.

| Trường hợp | Điều cần xác nhận |
|---|---|
| Gọi bằng tên dài | Giá trị được truyền đúng vào tham số |
| Gọi bằng tên ngắn | Cùng tham số nhận được giá trị tương đương |
| Gọi bằng alias dài | Alias được chấp nhận như tên chính |
| Gọi bằng alias ngắn | Alias ngắn được nhận diện đúng |
| Hai option khác nhau | Không có xung đột tên hoặc alias |
| Xem help command | Mô tả command và option dễ hiểu |
| Option có label | Label xuất hiện đúng ở phần synopsis nếu renderer hỗ trợ |
| Tên option thay đổi | Script và tài liệu cũ được kiểm tra tương thích |

Ví dụ kiểm thử đơn vị cho phương thức command:

```java
@Test
void returnsOutputPath() {
    String result = commands.export("report.csv");

    assertEquals("Đã xuất báo cáo tới report.csv", result);
}
```

Kiểm thử trên chỉ xác nhận logic phương thức. Để xác nhận `--output`, `-o` và alias được parser nhận diện, cần chạy command qua Spring Shell runtime hoặc lớp kiểm thử command phù hợp với phiên bản dự án. Cũng nên kiểm tra help thực tế để bảo đảm metadata đã được đưa vào giao diện.

## 15. Checklist thiết kế tên option

- [ ] Mỗi option có tên dài rõ nghĩa nếu người dùng cần gọi trong script.
- [ ] Tên ngắn dễ nhớ và không xung đột với option khác.
- [ ] `longNames` không chứa tiền tố `--`.
- [ ] `shortNames` là ký tự và không chứa tiền tố `-`.
- [ ] Bí danh được dùng có chủ đích; tên đầu tiên là tên chính.
- [ ] Mô tả command giải thích hành động tổng thể.
- [ ] Mô tả option giải thích ý nghĩa của value.
- [ ] `label`, `required` và `defaultValue` được dùng đúng mục đích.
- [ ] Help hiển thị nội dung dễ hiểu và phù hợp với cú pháp thực tế.
- [ ] Script hiện có được kiểm tra khi thay đổi tên option.

## 16. Tự kiểm tra

**Câu 1.** `longNames = "output"` và `shortNames = 'o'` tạo ra những cách gọi nào?

**Gợi ý trả lời:** `--output` và `-o`; cả hai cùng ánh xạ đến tham số được đánh dấu `@Option`.

**Câu 2.** Nếu `longNames = {"output", "out"}`, tên nào là tên chính?

**Gợi ý trả lời:** `output` là tên chính vì đứng đầu mảng; `out` là bí danh.

**Câu 3.** `description` của `@Command` khác `description` của `@Option` như thế nào?

**Gợi ý trả lời:** Mô tả command giải thích hành động tổng thể; mô tả option giải thích ý nghĩa của một giá trị đầu vào.

**Câu 4.** `label = "FILE"` có thay thế được `description = "Đường dẫn tệp đầu ra"` không?

**Gợi ý trả lời:** Không. Label là nhãn hiển thị cho value trong help/synopsis; description giải thích mục đích của option.

**Câu 5.** Khi đổi tên `--out` thành `--output`, vì sao nên cân nhắc giữ alias cũ?

**Gợi ý trả lời:** Script và người dùng hiện tại có thể đang phụ thuộc vào tên cũ. Alias giúp duy trì tương thích trong giai đoạn chuyển đổi.

## Kết luận

Trong Spring Shell 3.x, `@Option` cho phép khai báo tên dài bằng `longNames`, tên ngắn bằng `shortNames` và mô tả option bằng `description`. Nhiều tên có thể cùng ánh xạ đến một tham số; phần tử đầu tiên trong mỗi mảng là tên chính, các phần tử sau là bí danh. Mô tả của `@Command` giải thích hành động tổng thể, còn mô tả của `@Option` giải thích từng giá trị đầu vào.

Hãy chọn tên dài rõ nghĩa, tên ngắn dễ nhớ, giới hạn alias ở mức cần thiết và viết mô tả hướng đến người sử dụng CLI. Kiểm tra help cùng cách gọi thực tế để bảo đảm metadata đã khai báo trở thành một giao diện command nhất quán.

## Tài liệu tham khảo

- [Spring Shell 3.4 — `@Option` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Option.html)
- [Spring Shell 3.4 — Short Format](https://docs.spring.io/spring-shell/reference/3.4/options/short.html)
- [Spring Shell 3.4 — Annotation option](https://docs.spring.io/spring-shell/reference/3.4/options/basics/annotation.html)
- [Spring Shell 3.4 — Label](https://docs.spring.io/spring-shell/reference/3.4/options/label.html)
- [Spring Shell 3.4 — Command Registration](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/registration.html)
- [Spring Shell 4.x — `@Option` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html)
