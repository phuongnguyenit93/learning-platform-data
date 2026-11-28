# Xử lý ô trống, nội dung nhiều dòng và chuỗi quá dài

Khi hiển thị dữ liệu trong bảng CLI, các ô không phải lúc nào cũng chứa một chuỗi ngắn, gọn. Một ô có thể là `null`, chuỗi rỗng, nội dung có nhiều dòng, đường dẫn rất dài hoặc mô tả vượt quá chiều rộng terminal. Nếu không chuẩn hóa, bảng có thể khó đọc, lệch cột hoặc chiếm quá nhiều màn hình.

Spring Shell 4.x cung cấp table API để tách việc định dạng giá trị, tính chiều rộng cột, wrap nội dung và căn chỉnh. Bài viết hướng dẫn cách xử lý các trường hợp dữ liệu này bằng `Formatter`, `TextWrapper`, `SizeConstraints` và `CellMatcher`, đồng thời lưu ý về Unicode và dữ liệu không đáng tin cậy.

## 1. Một ô bảng có thể chứa nhiều dạng dữ liệu

Trước khi chọn cách hiển thị, hãy phân biệt các trường hợp sau:

| Giá trị nguồn | Ý nghĩa có thể có | Cách hiển thị gợi ý |
|---|---|---|
| `null` | Không có giá trị hoặc chưa được cung cấp | `—` hoặc `(not set)` |
| `""` | Giá trị có mặt nhưng rỗng | `(empty)` |
| `"   "` | Chỉ chứa khoảng trắng | `(blank)` hoặc chuẩn hóa thành rỗng |
| `"Line 1\nLine 2"` | Nội dung có xuống dòng có chủ đích | Giữ dòng hoặc wrap theo chiều rộng cột |
| URL/path/hash dài | Chuỗi không có điểm ngắt tự nhiên | Rút gọn có dấu `...` hoặc cho phép cuộn/xem chi tiết |
| Mô tả dài có dấu cách | Văn bản tự nhiên | Wrap tại ranh giới từ |
| Tiếng Việt, CJK hoặc emoji | Ký tự có độ rộng hiển thị khác nhau | Đo theo terminal columns, không theo `String.length()` |

Không nên gộp mọi trường hợp thành một chuỗi trống. `null`, empty và blank có thể mang ý nghĩa nghiệp vụ khác nhau. Chọn placeholder phù hợp với dữ liệu mà command đang hiển thị.

## 2. Pipeline render của table trong Spring Shell 4

Spring Shell 4 có table API trong package `org.springframework.shell.jline.tui.table`. `Table` nhận một `TableModel` chứa dữ liệu thô. Khi render, các bước chính diễn ra theo thứ tự:

1. **Formatter:** chuyển giá trị của cell thành một hoặc nhiều dòng văn bản.
2. **Size constraints:** xác định chiều rộng tối thiểu và tối đa của từng cột.
3. **Text wrapper:** wrap hoặc crop các dòng theo chiều rộng cột đã tính.
4. **Aligner:** căn trái, giữa hoặc phải và đệm khoảng trắng để các cell thẳng hàng.

`TableBuilder` mặc định dùng `toString()` để định dạng, tách chuỗi theo newline, tự tính kích thước cột, wrap tại dấu cách và căn trái. Có thể thay đổi từng chiến lược cho tất cả cell, một cột, một hàng, một vị trí hoặc các cell có kiểu dữ liệu cụ thể thông qua `CellMatcher`.

Các API quan trọng:

| API | Vai trò |
|---|---|
| `TableModel` / `TableModelBuilder` | Cung cấp dữ liệu theo hàng và cột |
| `Formatter` | Chuyển một giá trị thành `String[]` dòng hiển thị |
| `SizeConstraints` | Quyết định chiều rộng cell/cột |
| `TextWrapper` | Wrap hoặc crop nội dung theo chiều rộng |
| `Aligner` | Căn chỉnh nội dung trong cell |
| `CellMatchers` | Chọn cell cần áp dụng formatter, sizer, wrapper hoặc aligner |
| `Table.render(int)` | Render bảng theo chiều rộng terminal được truyền vào |

## 3. Xử lý `null`, empty và blank trước khi render

`TableModel.getValue(row, column)` cho phép trả về `null`. Vì vậy, ứng dụng nên xác định cách hiển thị giá trị thiếu thay vì để người dùng phải đoán ý nghĩa của chuỗi `null` hoặc một ô trắng.

Ví dụ quy ước:

```text
ID    NAME       EMAIL
101   An         an@example.com
102   Bình       —
103   Chi        (empty)
104   Dũng       (blank)
```

Trong bảng trên:

- `—` biểu thị giá trị nguồn là `null`.
- `(empty)` biểu thị chuỗi có tồn tại nhưng không có ký tự.
- `(blank)` biểu thị chuỗi chỉ có khoảng trắng.

Nếu ứng dụng không cần phân biệt empty và blank, có thể chuẩn hóa cả hai thành cùng một placeholder. Hãy dùng một quy tắc nhất quán trong mọi command để người dùng không phải học nhiều cách hiểu.

Nếu terminal/font không hiển thị tốt dấu gạch ngang dài `—`, dùng placeholder ASCII như `(none)` hoặc `-` để bảo đảm tương thích.

### Tạo formatter xử lý giá trị rỗng và xuống dòng

`DefaultFormatter` dùng `Object.toString()` và tách nội dung theo newline. Khi cần placeholder riêng cho `null`, empty và blank, hãy tạo `Formatter` tùy chỉnh.

```java
import org.jline.utils.AttributedString;
import org.springframework.shell.jline.tui.table.Formatter;

public class SafeCellFormatter implements Formatter {

    @Override
    public String[] format(Object value) {
        if (value == null) {
            return new String[] { "—" };
        }

        String text = AttributedString.stripAnsi(value.toString())
                .replace("\r\n", "\n")
                .replace('\r', '\n')
                .replace('\t', ' ');

        StringBuilder sanitized = new StringBuilder();
        text.codePoints()
                .filter(codePoint -> codePoint == '\n' || !Character.isISOControl(codePoint))
                .forEach(sanitized::appendCodePoint);
        text = sanitized.toString();

        if (text.isEmpty()) {
            return new String[] { "(empty)" };
        }
        if (text.isBlank()) {
            return new String[] { "(blank)" };
        }

        return text.split("\n", -1);
    }
}
```

`AttributedString.stripAnsi(...)` loại bỏ ANSI escape sequence khỏi dữ liệu cell; bước lọc tiếp theo loại bỏ control characters còn lại nhưng vẫn giữ newline. `split("\\n", -1)` giữ lại dòng rỗng ở cuối chuỗi. Điều này hữu ích nếu nội dung nhiều dòng có xuống dòng cuối mang ý nghĩa. Nếu không cần bảo toàn dòng rỗng cuối, có thể dùng chính sách chuẩn hóa khác, nhưng nên quyết định rõ để tránh kết quả không nhất quán.

Với dữ liệu đến từ bên ngoài, cần cân nhắc loại bỏ các ký tự điều khiển không mong muốn trước khi render. Giữ newline có chủ đích, chuẩn hóa tab thành dấu cách và loại bỏ ESC/control characters không cần thiết để nội dung không làm hỏng bố cục terminal.

## 4. Nội dung nhiều dòng trong một cell

Một cell có thể chứa ghi chú, mô tả, địa chỉ hoặc lỗi gồm nhiều dòng. Spring Shell table formatter có thể chuyển nội dung đó thành mảng `String[]`; mỗi phần tử là một dòng trong cùng cell.

Ví dụ dữ liệu:

```java
String note = "Import started\n3 rows skipped\nCompleted with warnings";
```

Khi đưa vào table, nội dung có thể được hiển thị thành nhiều dòng trong cùng một hàng:

```text
+------+----------+-----------------------------+
| ID   | STATUS   | NOTE                        |
+------+----------+-----------------------------+
| 101  | DONE     | Import started              |
|      |          | 3 rows skipped              |
|      |          | Completed with warnings     |
+------+----------+-----------------------------+
```

Các cell khác trên cùng một hàng được căn theo chiều cao của cell nhiều dòng nhất. Vì vậy, bảng có thể cao hơn số bản ghi. Đây là hành vi phù hợp khi cần giữ nội dung, nhưng không nên để các cột mô tả dài khiến bảng chiếm nhiều trang terminal.

### Chuẩn hóa newline

Nguồn dữ liệu có thể dùng nhiều kiểu line ending:

- `\n`: Unix/Linux/macOS.
- `\r\n`: Windows.
- `\r`: một số dữ liệu cũ hoặc hệ thống đặc thù.

Nên chuẩn hóa về `\n` trước khi split. Nếu không, một chuỗi có `\r\n` có thể tạo ra ký tự `\r` còn sót ở cuối dòng.

### Giữ hay gộp dòng trống?

Hai nội dung sau không nhất thiết có cùng ý nghĩa:

```text
First line
Second line
```

và:

```text
First line

Second line
```

Trường hợp thứ hai có một dòng trống có chủ đích. Nếu dữ liệu là ghi chú do người dùng nhập, giữ dòng trống giúp bảo toàn cách trình bày. Nếu dữ liệu là log hoặc nội dung máy sinh, có thể chuẩn hóa nhiều dòng trống liên tiếp thành một dòng để giảm chiều cao bảng.

## 5. Áp dụng formatter cho một cột bằng `CellMatchers`

Không phải cột nào cũng cần cùng một quy tắc. Ví dụ ID cần hiển thị nguyên vẹn, cột status ngắn, còn cột note cần placeholder và multiline formatting.

Ví dụ tạo bảng:

```java
import org.springframework.shell.jline.tui.table.CellMatchers;
import org.springframework.shell.jline.tui.table.DelimiterTextWrapper;
import org.springframework.shell.jline.tui.table.Formatter;
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableBuilder;
import org.springframework.shell.jline.tui.table.TableModelBuilder;

TableModelBuilder<Object> model = new TableModelBuilder<>();
model.addRow()
        .addValue("ID")
        .addValue("STATUS")
        .addValue("NOTE");
model.addRow()
        .addValue("101")
        .addValue("DONE")
        .addValue("Import started\n3 rows skipped\nCompleted");
model.addRow()
        .addValue("102")
        .addValue("WAITING")
        .addValue(null);

TableBuilder builder = new TableBuilder(model.build());
builder.on(CellMatchers.column(2))
        .addFormatter(new SafeCellFormatter())
        .addWrapper(new DelimiterTextWrapper())
        .and();

Table table = builder.build();
String rendered = table.render(100);
```

`CellMatchers.column(2)` chọn cột `NOTE` vì chỉ số cột bắt đầu từ `0`. `SafeCellFormatter` chuyển `null` thành placeholder và tách multiline. `DelimiterTextWrapper` wrap các dòng tại ranh giới từ khi cần.

Các matcher thông dụng:

| Matcher | Phạm vi |
|---|---|
| `CellMatchers.table()` | Tất cả cell |
| `CellMatchers.column(2)` | Mọi cell trong cột thứ ba |
| `CellMatchers.row(1)` | Mọi cell trong hàng thứ hai |
| `CellMatchers.at(1, 2)` | Một cell tại hàng 1, cột 2 |
| `CellMatchers.ofType(String.class)` | Các cell có giá trị thuộc kiểu `String` |

Chọn matcher hẹp nhất đáp ứng mục tiêu để formatter không vô tình thay đổi các cột có quy tắc dữ liệu khác.

## 6. Wrap văn bản dài theo ranh giới từ

Với mô tả tự nhiên có dấu cách, wrap thường dễ đọc hơn cắt chuỗi. Spring Shell cung cấp `DelimiterTextWrapper`, mặc định wrap tại dấu cách.

Ví dụ một nội dung dài:

```text
The import process validates every customer record before writing the result to the database.
```

Nếu chiều rộng cột là 30 ký tự, nội dung có thể được chia thành các dòng ngắn hơn tại ranh giới từ thay vì bị cắt giữa một từ.

`TextWrapper.wrap(String[] original, int columnWidth)` nhận các dòng đã format và chiều rộng cột. Mỗi dòng kết quả phải có độ dài đúng bằng `columnWidth` theo hợp đồng API; wrapper có thể trả về nhiều dòng hơn đầu vào khi wrap.

```java
builder.on(CellMatchers.column(2))
        .addWrapper(new DelimiterTextWrapper())
        .and();
```

Đối với văn bản có delimiter khác dấu cách, có thể khởi tạo `DelimiterTextWrapper` với delimiter phù hợp. Tuy nhiên, không nên chọn delimiter tùy tiện nếu nó có thể xuất hiện bên trong dữ liệu và làm thay đổi ý nghĩa.

## 7. Xử lý chuỗi dài không có điểm ngắt tự nhiên

`DelimiterTextWrapper` phù hợp với văn bản có khoảng trắng. Nhưng một chuỗi như URL, hash, UUID, mã giao dịch hoặc đường dẫn dài có thể không có dấu cách. Nếu không có điểm ngắt, cột có thể rộng bất thường hoặc nội dung khó đọc.

Ví dụ:

```text
https://storage.example.com/archive/2026/11/customer-export-very-long-file-name.csv
```

Có ba chiến lược chính:

| Chiến lược | Cách dùng | Phù hợp khi |
|---|---|---|
| Wrap theo delimiter | Chia văn bản tại dấu cách hoặc delimiter đã chọn | Mô tả, ghi chú, địa chỉ |
| Break token | Chia một token dài thành các đoạn | Hash, path, chuỗi kỹ thuật có thể đọc từng đoạn |
| Truncate có dấu hiệu | Giữ phần đầu và thêm `...` | Bảng tổng quan cần gọn; giá trị đầy đủ có thể xem riêng |

Không nên âm thầm cắt mất phần cuối của ID hoặc URL nếu người dùng cần sao chép chính xác. Nếu truncate, hãy cung cấp command xem chi tiết hoặc cách lấy giá trị đầy đủ.

### Giới hạn chiều rộng cột

`AbsoluteWidthSizeConstraints` áp dụng chiều rộng cố định cho cell. Có thể kết hợp nó với một wrapper để bảo đảm nội dung không làm cột phình quá mức.

```java
import org.springframework.shell.jline.tui.table.AbsoluteWidthSizeConstraints;

builder.on(CellMatchers.column(2))
        .addSizer(new AbsoluteWidthSizeConstraints(24))
        .addWrapper(new DelimiterTextWrapper())
        .and();
```

Chiều rộng `24` là ví dụ. Cần tính tổng chiều rộng các cột, border và khoảng cách để không vượt quá terminal. Nếu tổng kích thước tối thiểu của các cột lớn hơn chiều rộng terminal, bảng vẫn có thể bị tràn ngang.

### Wrapper truncate đơn giản cho dữ liệu ASCII

Với mã kỹ thuật chỉ gồm ASCII, có thể tạo wrapper cắt chuỗi và thêm `...`. Ví dụ này chỉ dành cho ASCII vì nó dùng `String.length()` làm độ rộng; không dùng trực tiếp cho tiếng Việt, CJK hoặc emoji.

```java
import java.util.Arrays;

import org.springframework.shell.jline.tui.table.TextWrapper;

public class AsciiEllipsisWrapper implements TextWrapper {

    @Override
    public String[] wrap(String[] original, int columnWidth) {
        return Arrays.stream(original)
                .map(line -> fitAscii(line, columnWidth))
                .toArray(String[]::new);
    }

    private String fitAscii(String value, int width) {
        if (width <= 0) {
            return "";
        }

        String result = value;
        if (result.length() > width) {
            result = width <= 3
                    ? ".".repeat(width)
                    : result.substring(0, width - 3) + "...";
        }

        return result + " ".repeat(width - result.length());
    }
}
```

Áp dụng wrapper:

```java
builder.on(CellMatchers.column(0))
        .addSizer(new AbsoluteWidthSizeConstraints(12))
        .addWrapper(new AsciiEllipsisWrapper())
        .and();
```

Đây là lựa chọn cho cột mã ASCII cần hiển thị gọn. Nếu giá trị là nội dung đa ngôn ngữ, cần wrapper đo theo terminal columns và không cắt giữa grapheme cluster.

## 8. Phân biệt wrap và truncate

Wrap và truncate giải quyết hai mục tiêu khác nhau:

- **Wrap:** giữ toàn bộ nội dung, tăng số dòng trong cell.
- **Truncate:** giảm số ký tự hiển thị, giữ bảng gọn hơn nhưng không còn toàn bộ nội dung trong cell.

| Loại dữ liệu | Lựa chọn gợi ý | Lý do |
|---|---|---|
| Mô tả sản phẩm | Wrap | Người dùng cần đọc đầy đủ nội dung |
| Ghi chú lỗi | Wrap, có giới hạn số dòng | Giữ thông tin chẩn đoán nhưng tránh bảng quá cao |
| UUID | Truncate hoặc break token | Giá trị dài, ít điểm ngắt |
| URL | Truncate trong bảng, xem đầy đủ ở lệnh detail | Giữ bố cục nhưng không mất khả năng truy xuất |
| Hash | Hiển thị prefix và suffix | Dễ phân biệt các giá trị, vẫn nhận biết được phần đầu/cuối |
| JSON/XML lớn | Hiển thị summary hoặc số dòng | Bảng không phù hợp để chứa payload lớn |

Nếu cần giới hạn chiều cao cell, hãy xác định rõ phần bị lược bỏ và hiển thị dấu `…` hoặc thông tin như `(more)` để người dùng biết còn nội dung. Không nên âm thầm bỏ dòng cuối.

## 9. Căn chỉnh và chiều cao của cell nhiều dòng

Sau khi formatter và wrapper tạo ra các dòng, aligner quyết định cách căn chỉnh. Spring Shell hỗ trợ căn ngang trái, giữa, phải và căn dọc trên, giữa, dưới.

Các nguyên tắc thường dùng:

- Văn bản và mô tả: căn trái.
- Số lượng và giá trị tiền: căn phải để dễ so sánh.
- Trạng thái ngắn: căn giữa nếu bảng có nhiều cột trạng thái.
- Nội dung nhiều dòng: thường căn dọc trên để dòng đầu bắt đầu cùng vị trí.

Không nên căn giữa các đoạn mô tả dài. Khi cell có nhiều dòng, căn dọc trên giúp người đọc so sánh dòng đầu giữa các hàng dễ hơn.

Nếu sử dụng `SimpleVerticalAligner` hoặc `SimpleHorizontalAligner`, hãy áp dụng bằng `CellMatcher` cho đúng cột và kiểm tra kết quả sau khi wrapper đã tạo các dòng. Formatter, sizer, wrapper và aligner có quan hệ với nhau; thay đổi thứ tự hoặc chiến lược có thể làm kết quả khác mong đợi.

## 10. Đo chiều rộng hiển thị của Unicode

Không dùng `String.length()` để quyết định chiều rộng cột cho văn bản đa ngôn ngữ. Java đếm UTF-16 code units, còn terminal hiển thị theo số cột.

Ví dụ:

| Chuỗi | Đặc điểm |
|---|---|
| `ABC` | 3 ký tự ASCII, thường chiếm 3 cột |
| `Tiếng Việt` | Có ký tự có dấu và tổ hợp Unicode; số code unit không luôn bằng cột hiển thị |
| `你好` | Mỗi ký tự CJK thường chiếm 2 cột terminal |
| `😀` | Emoji thường chiếm 2 cột, tùy terminal/font |
| `é` | Chữ `e` kết hợp dấu có thể gồm nhiều code point nhưng hiển thị như một grapheme |

JLine cung cấp `WCWidth` để tính độ rộng hiển thị của Unicode code point. JLine cũng có các API đo chiều rộng `AttributedString` theo terminal columns. Với các chuỗi phức tạp như emoji ZWJ, cờ hoặc ký tự kết hợp, cần tính theo grapheme cluster thay vì cắt tùy ý theo `char` hoặc code point.

Ví dụ đo độ rộng của chuỗi bằng JLine:

```java
import org.jline.utils.AttributedString;

String text = "Xin chào 你好 😀";
int terminalColumns = new AttributedString(text).columnLength();
System.out.println("Display width: " + terminalColumns);
```

Nếu tự triển khai wrapper Unicode:

- Dùng API đo display width của JLine thay vì `String.length()`.
- Không cắt giữa surrogate pair.
- Không cắt giữa grapheme cluster hoặc chuỗi emoji kết hợp.
- Xem xét tab, control characters và ANSI style sequence trước khi đo.
- Kiểm thử trên terminal/font thực tế vì độ rộng emoji và ký tự East Asian Ambiguous có thể khác theo môi trường.

## 11. Làm sạch nội dung trước khi đưa vào bảng

Dữ liệu trong cell có thể đến từ file import, API bên ngoài, log hoặc người dùng. Không nên giả định nội dung đó luôn là văn bản thuần an toàn.

Trước khi render, cân nhắc:

- Chuẩn hóa line ending.
- Chuyển tab thành khoảng trắng để tránh phụ thuộc tab stop của terminal.
- Loại bỏ ESC và control characters không được phép.
- Giới hạn số dòng hoặc tổng độ dài nếu dữ liệu không đáng tin cậy.
- Không render trực tiếp ANSI sequence do người dùng cung cấp nếu không có chủ đích.
- Che dữ liệu nhạy cảm như token, mật khẩu, email hoặc thông tin cá nhân theo chính sách của ứng dụng.

Một cell chứa ký tự điều khiển terminal có thể làm thay đổi màu, di chuyển con trỏ hoặc xóa nội dung ngoài dự kiến. Bảng không nên trở thành kênh thực thi terminal escape sequence từ dữ liệu bên ngoài.

## 12. Chọn `AutoSizeConstraints`, `NoWrapSizeConstraints` hay chiều rộng cố định

Spring Shell có nhiều chiến lược tính chiều rộng:

| Sizer | Đặc điểm | Trường hợp dùng |
|---|---|---|
| `AutoSizeConstraints` | Tính khoảng chiều rộng dựa trên nội dung và ranh giới dấu cách | Bảng thông thường, nội dung có thể wrap |
| `NoWrapSizeConstraints` | Dùng chiều dài dòng lớn nhất làm yêu cầu chiều rộng | Bảng cần giữ nguyên dòng và terminal đủ rộng |
| `AbsoluteWidthSizeConstraints` | Ép chiều rộng cố định | Cột có giới hạn rõ ràng, kết hợp wrapper |
| `KeyValueSizeConstraints` | Tối ưu cho dạng key-value | Bảng cấu hình hoặc thuộc tính |

`NoWrapSizeConstraints` có thể khiến cột rất rộng nếu dữ liệu chứa một chuỗi dài. Tránh dùng nó cho dữ liệu tự do hoặc dữ liệu bên ngoài chưa được giới hạn.

Khi dùng chiều rộng cố định, cần chọn wrapper tương ứng. Sizer quyết định kích thước; wrapper quyết định nội dung vừa vào kích thước đó bằng cách wrap hoặc crop.

## 13. Kiểm thử các trường hợp dữ liệu biên

Một bảng chỉ nên được đưa vào sử dụng sau khi kiểm tra các loại dữ liệu có thể phá vỡ bố cục.

| Trường hợp | Dữ liệu thử | Kết quả cần xác nhận |
|---|---|---|
| Null | `null` | Hiển thị placeholder đã quy định |
| Empty | `""` | Phân biệt với null nếu nghiệp vụ cần |
| Blank | `"   "` | Không tạo ô trắng khó hiểu |
| Một dòng | `"Ready"` | Căn chỉnh đúng |
| Nhiều dòng | `"First\nSecond"` | Dòng nằm trong cùng cell |
| Dòng rỗng ở giữa | `"First\n\nThird"` | Chính sách giữ/gộp dòng rõ ràng |
| CRLF | `"First\r\nSecond"` | Không còn `\r` ở cuối dòng |
| Tab | `"A\tB"` | Khoảng cách hiển thị ổn định |
| Văn bản dài có dấu cách | Một đoạn mô tả dài | Wrap không cắt giữa từ |
| Token dài không có dấu cách | UUID/hash/URL | Không làm bảng tràn bất ngờ |
| Unicode | Tiếng Việt, CJK, emoji | Cột không lệch theo display width |
| ANSI/control | Chuỗi có ESC | Không làm thay đổi terminal ngoài dự kiến |
| Dòng quá dài | Hàng nghìn ký tự | Có giới hạn hoặc truncate rõ ràng |

Ngoài unit test formatter và wrapper, nên render bảng ở nhiều chiều rộng khác nhau, ví dụ 60, 80 và 120 cột. Kiểm tra cả trường hợp chỉ có một hàng, không có dữ liệu và có nhiều hàng với độ cao cell khác nhau.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Ô null hiện thành chữ `null` hoặc gây lỗi format | Chưa có quy tắc biểu diễn null | Dùng formatter trả placeholder rõ ràng |
| Không phân biệt null và empty | Mọi giá trị đều bị chuyển thành chuỗi rỗng | Xác định placeholder cho từng trạng thái |
| Dòng cuối bị mất | Split newline bỏ phần tử rỗng cuối | Dùng `split("\\n", -1)` nếu cần bảo toàn |
| Nội dung multiline làm hàng quá cao | Không giới hạn số dòng hoặc độ dài | Giới hạn dòng và cung cấp lệnh xem chi tiết |
| Cột rộng bất thường | Dữ liệu có token dài không chứa delimiter hoặc dùng `NoWrapSizeConstraints` | Đặt width cố định và chọn wrapper phù hợp |
| URL bị cắt giữa ký tự khó đọc | Truncate không có dấu hiệu | Thêm `...` và giữ command detail để xem giá trị đầy đủ |
| Cột tiếng Việt hoặc CJK lệch | Dùng `String.length()` để tính độ rộng | Dùng display width của JLine và kiểm thử terminal |
| Emoji bị tách đôi | Cắt chuỗi theo UTF-16 index | Cắt theo grapheme cluster |
| Tab làm lệch bảng | Giữ tab trong nội dung | Chuẩn hóa tab thành khoảng trắng |
| ESC làm đổi style hoặc di chuyển con trỏ | Render trực tiếp control sequence từ dữ liệu | Loại bỏ control characters không được phép |
| Bảng tràn terminal dù đã giới hạn một cột | Tổng chiều rộng tất cả cột và border vượt terminal | Tính ngân sách chiều rộng cho toàn bảng |

## 15. Checklist xử lý cell trước khi render

- [ ] Đã quy định riêng cách hiển thị `null`, empty và blank.
- [ ] Đã chuẩn hóa `\r\n`, `\r`, `\n` và tab.
- [ ] Đã quyết định có giữ dòng trống hay không.
- [ ] Dùng `Formatter` khi cần chuyển giá trị thành nhiều dòng hoặc placeholder.
- [ ] Chọn `CellMatcher` đúng phạm vi cột/hàng/cell.
- [ ] Dùng wrap cho mô tả và truncate có dấu hiệu cho giá trị cần bảng gọn.
- [ ] Đã xử lý token dài không có dấu cách.
- [ ] Đã chọn `SizeConstraints` phù hợp với chiều rộng terminal.
- [ ] Không dùng `String.length()` làm display width cho Unicode.
- [ ] Không cắt giữa surrogate pair hoặc grapheme cluster.
- [ ] Đã loại bỏ ANSI/control characters không mong muốn từ dữ liệu ngoài.
- [ ] Có cách xem giá trị đầy đủ khi cell bị truncate.
- [ ] Đã kiểm thử ở nhiều terminal width và với dữ liệu biên.

## Tài liệu tham khảo

1. [Spring Shell 4 – `Table` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Table.html) – pipeline format, size constraints, wrapping và alignment.
2. [Spring Shell 4 – `TableBuilder` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableBuilder.html) – cấu hình formatter, sizer, wrapper và aligner theo cell matcher.
3. [Spring Shell 4 – `DefaultFormatter` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/DefaultFormatter.html) – `toString()` và tách nội dung theo newline.
4. [Spring Shell 4 – `TextWrapper` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TextWrapper.html) – hợp đồng wrap theo chiều rộng cột.
5. [Spring Shell 4 – `TableModel` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableModel.html) – mô hình dữ liệu và giá trị cell có thể là `null`.
6. [JLine 3 – Unicode and display width](https://jline.org/versions/3.x/docs/advanced/attributed-strings/) – attributed text, độ rộng hiển thị và màu terminal.
7. [JLine – Unicode Support](https://jline.org/docs/advanced/unicode-support/) – Unicode width, East Asian characters, emoji và fallback.

Một bảng dễ đọc cần xử lý dữ liệu trước khi tính kích thước: quy định placeholder cho ô thiếu, giữ hoặc chuẩn hóa newline, wrap văn bản tự nhiên và giới hạn chuỗi dài có chủ đích. Với dữ liệu Unicode, hãy tính theo số cột terminal thay vì số code unit của Java. Luôn giữ đường truy cập tới giá trị đầy đủ khi bảng chỉ hiển thị bản rút gọn.
