# `DateTimeFormatterBuilder` và khi nào cần dùng

## 1. Từ một mẫu định dạng đến một quy tắc có cấu trúc

Một định dạng như `dd/MM/uuuu` thường chỉ cần `DateTimeFormatter.ofPattern()`. Nhưng giả sử nguồn nhập có tháng bằng chữ tiếng Anh, chấp nhận cả `jun` lẫn `JUN`, vẫn bắt buộc chữ `T` viết hoa, có thể thiếu giây, cho phép phần lẻ của giây và luôn cần độ lệch UTC. Lúc này, các quyết định nằm ở từng phần của định dạng chứ không chỉ ở một chuỗi mẫu.

`DateTimeFormatterBuilder` cho phép xây quy tắc từ các thành phần nhỏ: trường số, chữ cố định, văn bản theo ngôn ngữ, phần tùy chọn, phần lẻ, độ lệch và các thiết lập phân tích. Kết quả cuối cùng vẫn là một `DateTimeFormatter` dùng với `parse()` hoặc `format()`.

Theo [Java SE 21 — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html), builder là đối tượng có thể thay đổi, dành cho quá trình xây dựng trong một luồng. Còn [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) là bất biến và an toàn khi dùng chung giữa các luồng.

Có thể hình dung vòng đời như sau:

```text
DateTimeFormatterBuilder
    thêm lần lượt quy tắc đọc/ghi
                ↓ toFormatter(locale)
DateTimeFormatter
    parse chuỗi → đối tượng thời gian
    format đối tượng → chuỗi
```

Builder không tạo giá trị ngày giờ ngay khi gọi `appendValue()`. Các lời gọi ấy chỉ thêm quy tắc cho bộ định dạng sẽ được tạo ra.

## 2. Khi nào nên chọn builder?

| Nhu cầu | Cách phù hợp để bắt đầu |
| --- | --- |
| Đọc/ghi dạng ISO chuẩn có sẵn | Dùng hằng như `ISO_LOCAL_DATE`, `ISO_OFFSET_DATE_TIME` |
| Một mẫu cố định, dễ đọc như `dd/MM/uuuu HH:mm` | Dùng `ofPattern()` với `Locale` rõ ràng |
| Hiển thị ngày theo ngôn ngữ/phong cách địa phương | Xem `ofLocalizedDate()` hoặc `ofLocalizedDateTime()` |
| Cần đổi quy tắc chữ hoa/thường tại một đoạn | Builder với `parseCaseInsensitive()` rồi đặt lại chế độ |
| Cần số chữ số phần lẻ biến thiên hoặc độ rộng trường được chỉ rõ | Builder với `appendFraction()`/`appendValue()` |
| Cần cung cấp trường mặc định khi thật sự bị thiếu | Builder với `parseDefaulting()` |
| Cần ghép các bộ định dạng con hoặc văn bản tra cứu riêng | Builder với `append()` hoặc `appendText()` |

Một số phần tùy chọn đã diễn đạt được bằng `[]` trong mẫu. Vì vậy, có phần tùy chọn không tự động đồng nghĩa phải dùng builder. Chọn builder khi cấu trúc và các điều kiện riêng cần được nhìn thấy rõ qua những lời gọi có tên, hoặc khi mẫu không mô tả được yêu cầu.

Không có cam kết rằng viết lại một mẫu đơn giản bằng nhiều lời gọi builder sẽ làm chương trình nhanh hơn. Lợi ích chính ở đây là kiểm soát và khả năng diễn đạt quy tắc.

## 3. Những nhóm thao tác cần nhận biết

| Thao tác | Vai trò |
| --- | --- |
| `appendValue(field, width)` | Thêm trường số có độ rộng cố định trong cách đọc thông thường |
| `appendLiteral(...)` | Thêm ký tự hoặc đoạn chữ cố định như `-`, `:`, `T` |
| `appendText(field, textStyle)` | Thêm văn bản của trường, chẳng hạn tên tháng rút gọn |
| `appendPattern(pattern)` | Ghép một đoạn mẫu quen thuộc vào builder |
| `append(formatter)` | Ghép quy tắc từ một bộ định dạng có sẵn |
| `optionalStart()` / `optionalEnd()` | Đánh dấu cả một nhóm có thể vắng mặt |
| `appendFraction(field, min, max, decimalPoint)` | Điều khiển phần lẻ, số chữ số và dấu thập phân |
| `appendOffsetId()` | Thêm độ lệch UTC như `+07:00` hoặc `Z` |
| `appendZoneRegionId()` | Thêm mã vùng thời gian theo vùng khi hợp đồng cần nó |
| `parseDefaulting(field, value)` | Bổ sung giá trị cho trường chưa có ở thời điểm đó |

Đây là các nhóm để định hướng đọc mã, không cần ghi nhớ toàn bộ API. Thứ tự lời gọi chính là thứ tự các thành phần của chuỗi. Thiết lập phân tích cũng tác động đến các phần tiếp theo, nên đặt nó ở đúng vị trí là một phần của thiết kế.

## 4. Xây bộ định dạng cho một nguồn nhập cụ thể

Trong thí nghiệm này, đầu vào được quy định như sau:

- Năm có bốn chữ số, tháng bằng tên tiếng Anh rút gọn, ngày có hai chữ số.
- Tên tháng không phân biệt chữ hoa/thường.
- Giữa ngày và giờ phải là chữ `T` viết hoa.
- Giờ và phút bắt buộc; nhóm giây có thể vắng mặt.
- Khi có giây, phần lẻ có thể có tối đa 9 chữ số.
- Độ lệch UTC bắt buộc vì kiểu đích là `OffsetDateTime`.

Hai ví dụ hợp lệ:

```text
2025-jun-10T09:15+07:00
2025-JUN-10T09:15:30.12+07:00
```

Lưu chương trình vào `FormatterBuilderDemo.java`. Mã dùng Java 17 trở lên, không cần thư viện ngoài:

```java
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.format.TextStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class FormatterBuilderDemo {
    private static final DateTimeFormatter INPUT = new DateTimeFormatterBuilder()
            .appendValue(ChronoField.YEAR, 4)
            .appendLiteral('-')
            .parseCaseInsensitive()
            .appendText(ChronoField.MONTH_OF_YEAR, TextStyle.SHORT)
            .parseCaseSensitive()
            .appendLiteral('-')
            .appendValue(ChronoField.DAY_OF_MONTH, 2)
            .appendLiteral('T')
            .appendPattern("HH:mm")
            .optionalStart()
                .appendLiteral(':')
                .appendValue(ChronoField.SECOND_OF_MINUTE, 2)
                .appendFraction(ChronoField.NANO_OF_SECOND, 0, 9, true)
            .optionalEnd()
            .appendOffsetId()
            .toFormatter(Locale.ENGLISH)
            .withResolverStyle(ResolverStyle.STRICT);

    private static void check(String text) {
        try {
            OffsetDateTime value = OffsetDateTime.parse(text, INPUT);
            System.out.println(text + " -> " + value);
            System.out.println("formatted -> " + INPUT.format(value));
        } catch (DateTimeParseException ex) {
            System.out.println(text + " -> DateTimeParseException");
        }
    }

    public static void main(String[] args) {
        check("2025-jun-10T09:15+07:00");
        check("2025-JUN-10T09:15:30.12+07:00");
        check("2025-Jun-10t09:15+07:00");
        check("2025-Jun-31T09:15+07:00");
        check("2025-Jun-10T09:15");

        DateTimeFormatter normalizedOutput = DateTimeFormatter
                .ofPattern("uuuu-MM-dd'T'HH:mm:ssXXX", Locale.ROOT);
        OffsetDateTime parsed = OffsetDateTime.parse(
                "2025-jun-10T09:15+07:00", INPUT);
        System.out.println("separate output -> "
                + parsed.format(normalizedOutput));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 FormatterBuilderDemo.java
java FormatterBuilderDemo
```

Kết quả:

```text
2025-jun-10T09:15+07:00 -> 2025-06-10T09:15+07:00
formatted -> 2025-Jun-10T09:15:00+07:00
2025-JUN-10T09:15:30.12+07:00 -> 2025-06-10T09:15:30.120+07:00
formatted -> 2025-Jun-10T09:15:30.12+07:00
2025-Jun-10t09:15+07:00 -> DateTimeParseException
2025-Jun-31T09:15+07:00 -> DateTimeParseException
2025-Jun-10T09:15 -> DateTimeParseException
separate output -> 2025-06-10T09:15:00+07:00
```

## 5. Đọc builder từ trái sang phải

### Trường số và ký tự cố định

`appendValue(YEAR, 4)` đặt hợp đồng năm bốn chữ số; `appendValue(DAY_OF_MONTH, 2)` đặt ngày hai chữ số. Cách chọn này có chủ đích giới hạn cách viết của dữ liệu nguồn; không phải toàn bộ miền năm mà `java.time` hỗ trợ. Nếu hệ thống cần năm có dấu hoặc nhiều chữ số hơn, phải thiết kế lại quy tắc độ rộng và dấu tương ứng.

`appendLiteral('-')` và `appendLiteral('T')` thể hiện những ký tự phải có. `appendPattern("HH:mm")` cho thấy builder và mẫu có thể phối hợp: không cần viết thủ công từng trường khi một đoạn mẫu đã dễ hiểu. `HH` là giờ 24 giờ, còn `mm` là phút; viết `MM` ở vị trí phút sẽ mang ý nghĩa khác.

### Chữ hoa/thường và ngôn ngữ

`parseCaseInsensitive()` được đặt trước tên tháng, sau đó `parseCaseSensitive()` được gọi để đặt lại quy tắc cho phần phía sau. Do vậy `jun` và `JUN` đều được đọc, nhưng chữ `t` viết thường không thay cho `T` được. Những thiết lập này không phải khối lệnh tự hết hiệu lực sau một lời gọi: phải chủ động đặt lại khi cần.

`toFormatter(Locale.ENGLISH)` xác định ngôn ngữ tên tháng. Chấp nhận nhiều kiểu viết hoa không có nghĩa chấp nhận tên tháng thuộc mọi ngôn ngữ. Khi ghi ra chuỗi, tên tháng có dạng chuẩn theo `Locale` và `TextStyle`, nên các đầu vào khác nhau về chữ hoa đều có thể được ghi lại thành `Jun`.

### Nhóm giây tùy chọn và phần lẻ

`optionalStart()` mở nhóm chứa dấu `:`, hai chữ số giây và phần lẻ của giây. `optionalEnd()` đóng nhóm trước khi thêm độ lệch. Nhờ đó, thiếu giây không làm độ lệch trở thành tùy chọn theo.

`appendFraction(NANO_OF_SECOND, 0, 9, true)` biểu diễn phần lẻ của một giây. Tham số `0` cho phép không có chữ số phần lẻ, `9` là số chữ số tối đa, còn `true` yêu cầu phần tử này quản lý dấu thập phân. Với cấu hình của ví dụ, dấu đó là `.`. Không thêm một dấu `.` cố định nữa phía trước nếu muốn phần tử này tự quản lý dấu.

Chuỗi `.12` mang nghĩa 0,12 giây, tương ứng 120.000.000 nano giây; không phải 12 nano giây. Vì vậy dòng in đối tượng có thể là `.120`, trong khi bộ định dạng của bài xuất `.12`. Hai cách viết có cùng giá trị phần giây.

Phần lẻ nằm sau trường giây bên trong nhóm tùy chọn, nên không cho phép gắn phần lẻ trực tiếp vào phút trong định dạng này. Cấu trúc nhóm quyết định những biến thể nào được nhận.

### Độ lệch và ngày hợp lệ

`appendOffsetId()` nằm ngoài nhóm tùy chọn nên độ lệch luôn được yêu cầu. Ví dụ thiếu `+07:00` thất bại. Nếu tùy chọn hóa độ lệch nhưng vẫn muốn tạo `OffsetDateTime`, còn phải xác định nguồn cung cấp độ lệch khi nó vắng mặt; riêng dấu tùy chọn không tạo ra thông tin đó.

`.withResolverStyle(ResolverStyle.STRICT)` được gọi trên bộ định dạng kết quả để từ chối `2025-Jun-31`. Dữ liệu này đúng hình thức của các trường nhưng tháng 6 không có ngày 31. Các phương thức builder như `parseStrict()`/`parseLenient()` điều khiển việc đọc cú pháp; chúng không thay thế cho chế độ phân giải ngày hợp lệ. Tương tự, không phân biệt chữ hoa/thường không có nghĩa nới lỏng kiểm tra ngày.

## 6. Phần tùy chọn khi đọc không bảo toàn nguyên văn khi ghi

Dòng đầu vào không có giây vẫn được ghi lại với `:00`. Lý do là `OffsetDateTime` sau phân tích đã có trường giây bằng 0; khi định dạng đối tượng đó, nhóm tùy chọn có đủ thông tin để được xuất ra. Nó không ghi nhớ rằng nhóm đã bị bỏ trong chuỗi ban đầu.

Vì vậy, cùng một formatter có thể dùng cho cả đọc và ghi nhưng không bảo đảm tái tạo nguyên văn đầu vào. Những khác biệt như chữ hoa tên tháng, giây bằng 0 và số chữ số phần lẻ có thể được chuẩn hóa. Nếu cần giữ nguyên văn, phải lưu chuỗi gốc riêng.

Chương trình còn dùng `normalizedOutput` riêng cho đầu ra. Đây là cách rõ ràng khi đầu vào có nhiều biến thể nhưng đầu ra phải có dạng ổn định. Tên biến chỉ nói đến cách xuất thống nhất; không có lời gọi chuẩn hóa đối tượng thời gian đặc biệt nào ở đây.

## 7. Sử dụng trong ứng dụng và lỗi thường gặp

**Xây một lần, dùng bộ định dạng kết quả nhiều lần.** Ví dụ đặt `INPUT` là `static final DateTimeFormatter`. Giữ builder trong phạm vi khởi tạo; không dùng chung một builder đang bị thêm quy tắc giữa nhiều luồng. Không cần tạo lại toàn bộ builder cho từng bản ghi.

**Đóng nhóm ở đúng chỗ.** Nếu đặt `optionalEnd()` sau `appendOffsetId()`, độ lệch cũng thuộc nhóm tùy chọn. Nếu gọi `optionalEnd()` khi chưa mở nhóm, đó là lỗi cấu hình. Nên viết đóng/mở cân đối để người đọc kiểm tra cấu trúc dễ dàng.

**Không nhầm tùy chọn cú pháp với dữ liệu đủ cho kiểu đích.** Một phần có thể vắng mặt theo formatter nhưng vẫn cần cho việc tạo `LocalDateTime`, `OffsetDateTime` hoặc `ZonedDateTime`. Cần chọn kiểu phù hợp hoặc có quy tắc bổ sung. `parseDefaulting()` chỉ cung cấp giá trị nếu trường chưa có tại vị trí gọi; thường đặt sau phần đọc có thể cung cấp trường đó, và không dùng nó để che dữ liệu đã có nhưng sai.

**Giữ hợp đồng đầu vào đủ hẹp.** Nếu hai định dạng không liên quan dùng ý nghĩa hoặc thứ tự trường khác nhau, không nên coi việc ghép nhiều phần tùy chọn là cơ chế lựa chọn mọi định dạng. Có thể duy trì các formatter riêng và phân loại đầu vào theo hợp đồng rõ ràng; kiểm tra bằng các ví dụ được phép và bị cấm.

**Kiểm tra đúng loại thất bại.** Chuỗi không phù hợp khi phân tích thường gây `DateTimeParseException`; cấu hình builder không hợp lệ là lỗi khi xây dựng. Khi xuất một đối tượng không có trường bắt buộc, thao tác định dạng cũng có thể thất bại. Phải kiểm tra cả chiều đọc và chiều ghi mà ứng dụng thật sự dùng.

Bài tập: sửa bộ định dạng để bắt buộc có giây bằng cách bỏ cặp `optionalStart()`/`optionalEnd()` bao quanh nhóm giây. Đầu vào `2025-jun-10T09:15+07:00` khi đó phải bị từ chối, còn đầu vào có `:30.12` vẫn hợp lệ. Tiếp theo, chuyển `parseCaseSensitive()` xuống sau chữ `T` và dự đoán rằng `t` viết thường cũng được đọc tại vị trí ấy. Hai thay đổi giúp kiểm tra bạn đã hiểu phạm vi nhóm và phạm vi thiết lập trong builder.
