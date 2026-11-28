# Vị trí đối số trong mô hình option của 3.x

Trong Spring Shell 3.x, khi khai báo command bằng `CommandRegistration`, dữ liệu đầu vào được mô tả chủ yếu dưới dạng option. Người dùng có thể truyền option bằng tên như `--source report.csv`, hoặc nhập giá trị trực tiếp sau tên command như `file copy report.csv backup/`. Để Spring Shell hiểu các token không có tên thuộc option nào, ta có thể đặt vị trí cho option bằng `position(...)`.

Điểm quan trọng là `position` không tạo ra một tham số Java độc lập. Nó là gợi ý cho parser để ánh xạ những argument chưa gắn với option có tên vào một `OptionSpec` cụ thể. Khi hiểu cơ chế này, ta có thể thiết kế cú pháp gọn như `file copy source.txt backup/` mà vẫn đọc được dữ liệu trong `CommandContext` theo tên option.

Bài viết sử dụng API programmatic `CommandRegistration` của Spring Shell 3.4.1. Các bản 3.x có thể có khác biệt nhỏ về API hoặc parser; hãy kiểm tra tài liệu của minor version thực tế trước khi áp dụng.

## Phân biệt option, giá trị option và positional argument

Khi parser đọc một dòng lệnh, cần phân biệt ba loại token:

- **Option:** tên được đánh dấu bằng `--` hoặc `-`, ví dụ `--source` hoặc `-s`.
- **Giá trị option:** dữ liệu đi cùng một option có tên, ví dụ `report.csv` trong `--source report.csv`.
- **Positional argument:** token không được gắn trực tiếp với option nào, ví dụ `report.csv` trong `file copy report.csv backup/`.

Với option có tên, parser biết chính xác giá trị thuộc về option nào. Với positional argument, parser cần thêm thông tin để quyết định token đó sẽ được ánh xạ vào đâu. `position(...)` cung cấp gợi ý thứ tự cho việc ánh xạ thứ cấp này.

```text
file copy --source report.csv --destination backup/
          ^^^^^^^^ ^^^^^^^^^^  ^^^^^^^^^^^^^ ^^^^^^^
          option   giá trị     option        giá trị

file copy report.csv backup/
          ^^^^^^^^^^ ^^^^^^^
          positional positional
```

Hai cách gọi có thể cung cấp cùng dữ liệu cho command, miễn là các option được cấu hình đúng và các positional token được ánh xạ theo vị trí.

## `position(...)` hoạt động như thế nào?

`position(Integer position)` là phương thức của `CommandRegistration.OptionSpec`. Nó đánh dấu vị trí mà parser có thể dùng để ánh xạ một positional argument vào option đó.

Ví dụ khai báo một option bắt buộc tên `arg1`:

```java
CommandRegistration.builder()
        .command("greet")
        .withOption()
            .longNames("arg1")
            .type(String.class)
            .required()
            .position(0)
            .and()
        .withTarget()
            .function(context -> {
                String name = context.getOptionValue("arg1");
                return "Xin chào " + name;
            })
            .and()
        .build();
```

Người dùng có thể gọi:

```text
greet Linh
greet --arg1 Linh
```

Token `Linh` không có tên option, nhưng được ánh xạ vào option `arg1` nhờ `.position(0)`. Target vẫn đọc giá trị bằng tên option:

```java
String name = context.getOptionValue("arg1");
```

Khai báo `position` hỗ trợ thêm cách gọi theo vị trí, không loại bỏ tên option.

### Điều gì xảy ra khi không khai báo vị trí?

Nếu option bắt buộc không có `position`, parser không có gợi ý để gán một token trần vào option đó. Tài liệu Spring Shell 3.4.1 minh họa trường hợp sau:

```java
CommandRegistration.builder()
        .command("greet")
        .withOption()
            .longNames("name")
            .type(String.class)
            .required()
            .and()
        .withTarget()
            .function(context -> "Xin chào " + context.getOptionValue("name"))
            .and()
        .build();
```

Khi gọi `greet Linh`, parser có thể báo:

```text
Missing mandatory option --name.
```

Giá trị `Linh` đã xuất hiện trên dòng lệnh nhưng chưa được gắn với option bắt buộc `name`. Thêm `.position(0)` vào option cho parser biết có thể dùng positional token đầu tiên để điền option đó.

Điều này giải thích vì sao `required()` và `position(...)` có hai vai trò khác nhau:

- `required()` yêu cầu option phải có giá trị khi command được thực thi.
- `position(...)` chỉ cho parser biết có thể lấy giá trị chưa gắn tên từ vị trí nào.

Khai báo một option là bắt buộc không tự động khiến nó nhận positional argument. Muốn người dùng được phép bỏ tên option, cần cấu hình vị trí tương ứng.

## Ánh xạ nhiều positional argument

Khi command có nhiều dữ liệu vị trí, khai báo các option có vị trí khác nhau. Ví dụ, lệnh sao chép file cần nguồn và đích:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.CommandRegistration;

@Configuration
public class FileCommandConfiguration {

    @Bean
    CommandRegistration copyFileCommand(FileService fileService) {
        return CommandRegistration.builder()
                .command("file copy")
                .description("Sao chép file")
                .withOption()
                    .longNames("source")
                    .type(String.class)
                    .required()
                    .position(0)
                    .description("Đường dẫn file nguồn")
                    .and()
                .withOption()
                    .longNames("destination")
                    .type(String.class)
                    .required()
                    .position(1)
                    .description("Đường dẫn đích")
                    .and()
                .withTarget()
                    .function(context -> {
                        String source = context.getOptionValue("source");
                        String destination = context.getOptionValue("destination");
                        return fileService.copy(source, destination);
                    })
                    .and()
                .build();
    }
}
```

Trong ví dụ, `source` nhận positional argument ở vị trí `0`, còn `destination` nhận positional argument ở vị trí `1`. Vì vậy, cú pháp rút gọn là:

```text
file copy report.csv backup/report.csv
```

Hai giá trị vẫn được đọc theo tên `source` và `destination` trong target. Điều này giữ cho phần xử lý không phụ thuộc vào việc người dùng đã nhập option bằng tên hay theo vị trí.

Người dùng cũng có thể truyền tường minh:

```text
file copy --source report.csv --destination backup/report.csv
```

Khi dùng tên option, parser ánh xạ trực tiếp theo tên. Khi dùng token không có tên, parser mới cần đến gợi ý `position`.

### Chọn số vị trí có quy tắc

Nên đánh số theo thứ tự dữ liệu mà người dùng nhìn thấy trong cú pháp:

| Vị trí | Option | Ý nghĩa |
| --- | --- | --- |
| `0` | `source` | Giá trị vị trí đầu tiên |
| `1` | `destination` | Giá trị vị trí thứ hai |
| `2` | `format` | Giá trị vị trí thứ ba, nếu command thật sự cần |

Các vị trí nên duy nhất và dễ đoán. Tránh gán nhiều option vào cùng một vị trí hoặc tạo khoảng trống không cần thiết trong dãy vị trí. Khi có nhiều dữ liệu tùy chọn, hãy cân nhắc yêu cầu người dùng ghi rõ tên option thay vì cố ánh xạ mọi giá trị theo vị trí.

## Kết hợp `position(...)` với `arity(...)`

`position(...)` quyết định nơi parser có thể bắt đầu ánh xạ positional token vào option. `arity(min, max)` quyết định số lượng giá trị option có thể nhận. Hai thuộc tính bổ sung cho nhau, đặc biệt khi option nhận một mảng hoặc collection.

Ví dụ, command nhận từ một đến hai tên người dùng:

```java
CommandRegistration.builder()
        .command("greet")
        .withOption()
            .longNames("names")
            .type(String[].class)
            .required()
            .arity(1, 2)
            .position(0)
            .description("Một hoặc hai tên")
            .and()
        .withTarget()
            .function(context -> {
                String[] names = context.getOptionValue("names");
                return "Xin chào " + String.join(" và ", names);
            })
            .and()
        .build();
```

Các cách gọi:

```text
greet Linh
greet Linh An
greet --names Linh
greet --names Linh An
```

Với `position(0)`, các token vị trí bắt đầu được ánh xạ vào option `names`. Với `arity(1, 2)`, option nhận tối thiểu một và tối đa hai giá trị. Nếu dùng `String[].class`, target nhận một mảng; nếu dùng kiểu đơn như `String.class`, command chỉ nhận một giá trị cho option đó.

Tài liệu Spring Shell 3.4.1 cũng minh họa `arity(0, 2)` kết hợp `position(0)`: một hoặc hai positional token đầu được gom vào mảng. Khi số token vượt quá arity tối đa, phần vượt quá không được đưa vào giá trị option đó. Vì hành vi của các token còn lại có thể ảnh hưởng tới việc parse command, hãy kiểm thử rõ trường hợp thừa đối số thay vì dựa vào giả định.

### Khi nào nên dùng arity cố định?

Nếu command có nhiều option positional, arity cố định giúp parser biết mỗi option tiêu thụ bao nhiêu token trước khi chuyển sang vị trí kế tiếp. Ví dụ, lệnh cần hai tọa độ có thể dùng một option kiểu mảng với `arity(2, 2)`.

```java
.withOption()
    .longNames("coordinates")
    .type(Integer[].class)
    .required()
    .arity(2, 2)
    .position(0)
    .and()
```

Khi đó, option `coordinates` được thiết kế để nhận đúng hai giá trị vị trí. Nếu một command có nhiều option cùng nhận số lượng không giới hạn, parser khó xác định ranh giới giữa chúng. Hãy chuyển các phần sau sang option có tên hoặc giới hạn arity rõ ràng.

## Kết hợp positional argument với option có tên

Không phải mọi đầu vào đều nên là positional. Một command thường có một vài giá trị chính dễ dự đoán và nhiều tùy chọn bổ sung. Có thể đặt vị trí cho các giá trị chính, đồng thời khai báo option bổ sung chỉ dùng theo tên.

Ví dụ về ý tưởng giao diện:

```text
file copy report.csv backup/report.csv --overwrite true
```

Trong đó:

- `report.csv` là positional argument cho option `source`.
- `backup/report.csv` là positional argument cho option `destination`.
- `--overwrite true` là option có tên, không cần vị trí.

Với những lệnh kết hợp nhiều cách truyền dữ liệu, cần thử cả cách gọi vị trí lẫn cách gọi tường minh để chắc chắn parser không gán nhầm token. Khi cú pháp trở nên khó đọc, hãy yêu cầu người dùng dùng `--source` và `--destination` để tránh sự mơ hồ.

## Khi nào không nên dùng positional mapping?

Positional mapping tiện cho command ngắn, có thứ tự đầu vào tự nhiên và ít giá trị. Tuy nhiên, nó có thể gây nhầm lẫn khi command có nhiều tham số hoặc có các option nhận nhiều giá trị.

| Tình huống | Khuyến nghị |
| --- | --- |
| Command chỉ cần một mã định danh | Có thể dùng `position(0)` để cú pháp gọn |
| Command cần nguồn và đích theo thứ tự quen thuộc | Dùng `position(0)` và `position(1)` |
| Command có nhiều option tùy chọn | Dùng tên option để người dùng không phải nhớ thứ tự |
| Nhiều option cùng nhận mảng hoặc số lượng biến đổi | Khai báo arity rõ hoặc chuyển một số option sang dạng có tên |
| Command được gọi chủ yếu từ script dài | Ưu tiên option có tên để câu lệnh tự mô tả |
| Giá trị dễ bị nhầm với token khác | Dùng option có tên để parser không phải suy luận |

Tài liệu Spring Shell cảnh báo rằng positional parameters có thể nhanh chóng trở nên khó hiểu vì người dùng và parser phải xác định token trần đang được ánh xạ vào option nào. Hãy giữ positional mapping ở mức tối thiểu và dùng tên option cho dữ liệu ít hiển nhiên.

## Kiểm thử positional mapping

Một command có thể hoạt động với option có tên nhưng thất bại khi truyền positional, hoặc ngược lại. Vì vậy, cần kiểm thử hai cách gọi như hai hợp đồng đầu vào của cùng command.

| Trường hợp | Ví dụ | Điều cần xác minh |
| --- | --- | --- |
| Positional đơn | `greet Linh` | Token đầu được gán vào option có `position(0)` |
| Positional nhiều vị trí | `file copy a.txt backup/` | Token 0 và 1 được gán đúng option |
| Option có tên | `file copy --source a.txt --destination backup/` | Tên option ánh xạ đúng giá trị |
| Thiếu positional bắt buộc | `greet` | Parser báo thiếu option bắt buộc |
| Sai kiểu dữ liệu | Option số nhận `abc` | Lỗi chuyển đổi được báo trước khi target chạy |
| Arity tối thiểu | Mảng cần ít nhất một phần tử nhưng không có | Parser báo thiếu giá trị |
| Arity tối đa | Truyền nhiều token hơn giới hạn | Kiểm tra chính xác cách parser xử lý token dư |
| Positional và named option | `file copy a.txt backup/ --overwrite true` | Hai đường dẫn và option bổ sung được gán đúng |

Trong unit test, có thể kiểm tra logic của target bằng `CommandContext` hoặc gọi service với dữ liệu đã chuẩn hóa. Trong kiểm thử tích hợp, khởi tạo command catalog và thực thi cú pháp thật để xác nhận parser đã ánh xạ positional token đúng như cấu hình.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Nghĩ rằng option `required()` tự nhận token trần | Parser vẫn báo thiếu option | Thêm `.position(...)` nếu muốn nhận positional argument |
| Nhầm `position` với thứ tự khai báo option | Token được ánh xạ sai | Đặt vị trí theo thứ tự đầu vào người dùng sẽ nhập |
| Không đặt `type(...)` rõ ràng | Giá trị có thể không được chuyển đổi theo mong đợi | Khai báo kiểu Java phù hợp |
| Dùng mảng nhưng không giới hạn arity | Một option có thể tiêu thụ nhiều token hơn dự kiến | Đặt `arity(min, max)` |
| Nhiều option positional có arity không giới hạn | Parser khó xác định ranh giới dữ liệu | Giới hạn arity hoặc dùng option có tên |
| Gán nhiều option vào cùng vị trí | Token trần trở nên mơ hồ | Dùng vị trí duy nhất, tuần tự |
| Chỉ kiểm thử cách gọi có tên | Không phát hiện lỗi ánh xạ positional | Kiểm thử cả cú pháp vị trí và cú pháp có tên |

## Quy trình khai báo option có vị trí

1. Xác định những giá trị nào thật sự phù hợp để nhập theo vị trí.
2. Tạo một `OptionSpec` cho mỗi giá trị và đặt tên option có ý nghĩa.
3. Khai báo kiểu dữ liệu, tính bắt buộc và mô tả cho từng option.
4. Dùng `position(0)`, `position(1)` theo thứ tự positional token cần nhận.
5. Dùng `arity(...)` khi một option nhận mảng hoặc nhiều giá trị.
6. Trong target, đọc giá trị qua `CommandContext.getOptionValue("...")`.
7. Kiểm thử cách gọi vị trí, cách gọi theo tên, thiếu giá trị, sai kiểu và token thừa.

Trong Spring Shell 3.x, positional argument không phải một loại tham số tách rời khỏi option trong mô hình `CommandRegistration`. Ta định nghĩa option trước, rồi dùng `position(...)` để cho parser biết token không có tên có thể được gán vào option nào. Cách làm này giữ được một hợp đồng dữ liệu thống nhất trong target, đồng thời cho phép CLI cung cấp cú pháp ngắn gọn khi thứ tự đầu vào đủ rõ ràng.

## Tài liệu tham khảo

- [Positional – Spring Shell 3.4.1](https://docs.spring.io/spring-shell/reference/options/positional.html)
- [Programmatic Option Registration – Spring Shell 3.4.1](https://docs.spring.io/spring-shell/reference/options/basics/programmatic.html)
- [CommandRegistration.OptionSpec API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.OptionSpec.html)
