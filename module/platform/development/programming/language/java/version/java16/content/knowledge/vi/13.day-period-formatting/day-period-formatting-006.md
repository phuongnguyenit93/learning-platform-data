# DateTimeFormatterBuilder.appendDayPeriodText và TextStyle

> **Chương:** Định dạng day period  
> **Phạm vi:** Dùng `DateTimeFormatterBuilder.appendDayPeriodText(TextStyle)` để thêm nhãn day period vào formatter theo locale. Bài học tập trung vào vai trò của builder, lựa chọn `TextStyle`, cách kết hợp với trường giờ/phút, parse và resolve. API này được bổ sung ở Java 16 và tiếp tục có trong JDK hiện đại.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chức năng và thời điểm xuất hiện của `appendDayPeriodText`.
2. Chọn `TextStyle.SHORT`, `FULL` hoặc `NARROW` cho day period.
3. Tạo formatter bằng cách kết hợp builder với các trường giờ, phút và literal.
4. Phân biệt `appendDayPeriodText` với `appendText` cho AM/PM hoặc các trường văn bản khác.
5. Hiểu cách day period được ánh xạ khi format và kết hợp với giờ khi parse.
6. Sử dụng builder an toàn, tái sử dụng formatter đã hoàn tất và kiểm thử theo locale.

## 1. Vai trò của appendDayPeriodText

`DateTimeFormatterBuilder` là API dựng formatter theo từng thành phần. Thay vì mô tả toàn bộ định dạng trong một pattern string, ta có thể lần lượt thêm trường số, văn bản, literal, múi giờ hoặc phần tùy chọn.

Java 16 bổ sung phương thức:

```java
DateTimeFormatterBuilder appendDayPeriodText(TextStyle style)
```

Phương thức này thêm chỉ thị để định dạng hoặc phân tích tên day period. Day period được định nghĩa trong LDML (Locale Data Markup Language) và được ánh xạ theo locale của formatter.

Một số day period thường gặp là:

- `morning1`: một khoảng buổi sáng.
- `afternoon1`: một khoảng buổi chiều.
- `evening1`: một khoảng buổi tối.
- `night1`: một khoảng ban đêm.

Đây là tên loại trong dữ liệu locale, không phải chuỗi hiển thị mà ứng dụng nên tự in ra. Formatter tra văn bản tương ứng theo locale.

### Vì sao cần phương thức riêng?

AM/PM là trường thời gian có thể biểu diễn bằng `ChronoField.AMPM_OF_DAY`, nên formatter có thể thêm văn bản trường đó bằng `appendText`.

Day period linh hoạt phức tạp hơn: loại khoảng được suy ra từ giờ địa phương, có thể cần cả phút và phụ thuộc quy tắc locale. `appendDayPeriodText` đóng gói logic ánh xạ và parse đó.

| Nhu cầu | API phù hợp |
| --- | --- |
| Thêm nhãn AM/PM | `appendText(ChronoField.AMPM_OF_DAY, TextStyle.SHORT)` |
| Thêm tên day period linh hoạt | `appendDayPeriodText(TextStyle)` |
| Thêm tên thứ/tháng từ một `TemporalField` | `appendText(field, TextStyle)` |
| Thêm chuỗi cố định do ứng dụng định nghĩa | `appendLiteral(String)` |

Không dùng `appendText(AMPM_OF_DAY, ...)` để thay cho day period. Hai API biểu diễn hai khái niệm khác nhau.

## 2. TextStyle điều khiển cách hiển thị

`appendDayPeriodText` nhận một `TextStyle`. Ba style thông dụng cho day period là:

| TextStyle | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| `TextStyle.SHORT` | Văn bản ngắn | Nhãn gọn trong danh sách hoặc lịch |
| `TextStyle.FULL` | Văn bản đầy đủ | Màn hình chi tiết hoặc câu hiển thị dễ đọc |
| `TextStyle.NARROW` | Văn bản hẹp | Thành phần giao diện có chiều rộng hạn chế |

Các style tương ứng với pattern letter:

| Pattern | Builder tương đương |
| --- | --- |
| `B`, `BB`, `BBB` | `appendDayPeriodText(TextStyle.SHORT)` |
| `BBBB` | `appendDayPeriodText(TextStyle.FULL)` |
| `BBBBB` | `appendDayPeriodText(TextStyle.NARROW)` |

`TextStyle` còn có các biến thể `*_STANDALONE` dành cho văn bản đứng độc lập trong một số ngữ cảnh ngôn ngữ. Pattern day period `B` được định nghĩa bằng các style `SHORT`, `FULL` và `NARROW`; khi dựng formatter cho day period, hãy dùng đúng ba style này theo mục tiêu trình bày.

### Không đồng nhất style với độ dài chuỗi

`SHORT`, `FULL` và `NARROW` là lựa chọn kiểu văn bản trong dữ liệu locale, không phải giới hạn số ký tự. Một locale có thể dùng cùng chuỗi cho nhiều style; một dạng `NARROW` cũng không nhất thiết luôn ngắn hơn `SHORT` ở mọi ngôn ngữ.

Vì vậy, không cắt văn bản theo số ký tự và không viết test yêu cầu `FULL` luôn dài hơn `SHORT`. Hãy kiểm tra kết quả trên các locale mà sản phẩm hỗ trợ.

## 3. Tạo formatter cơ bản

Ví dụ tạo formatter gồm giờ 12 tiếng, phút và day period đầy đủ:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.TextStyle;
import java.util.Locale;

DateTimeFormatter formatter = new DateTimeFormatterBuilder()
        .appendPattern("h:mm ")
        .appendDayPeriodText(TextStyle.FULL)
        .toFormatter(Locale.US);

LocalTime time = LocalTime.of(15, 30);
System.out.println(formatter.format(time));
```

`appendPattern("h:mm ")` thêm giờ và phút. `appendDayPeriodText(TextStyle.FULL)` thêm nhãn khoảng trong ngày. `toFormatter(Locale.US)` hoàn tất builder và tạo formatter gắn với locale tiếng Anh Mỹ.

Kết quả có thể được diễn đạt theo dạng `3:30 in the afternoon`, tùy dữ liệu locale của JDK đang chạy.

### Tạo ba formatter theo style

```java
DateTimeFormatter shortPeriod = new DateTimeFormatterBuilder()
        .appendPattern("h:mm ")
        .appendDayPeriodText(TextStyle.SHORT)
        .toFormatter(Locale.US);

DateTimeFormatter fullPeriod = new DateTimeFormatterBuilder()
        .appendPattern("h:mm ")
        .appendDayPeriodText(TextStyle.FULL)
        .toFormatter(Locale.US);

DateTimeFormatter narrowPeriod = new DateTimeFormatterBuilder()
        .appendPattern("h:mm ")
        .appendDayPeriodText(TextStyle.NARROW)
        .toFormatter(Locale.US);
```

Ba formatter dùng cùng cấu trúc giờ/phút và cùng locale. Chỉ style của day period thay đổi.

## 4. Kết hợp các thành phần trong builder

Builder cho phép đặt day period cạnh các thành phần khác:

- `appendValue(...)` hoặc `appendPattern(...)` để thêm giờ/phút.
- `appendLiteral(...)` để thêm dấu cách hoặc dấu phân cách cố định.
- `appendDayPeriodText(...)` để thêm nhãn day period.
- `optionalStart()` và `optionalEnd()` để thêm phần tùy chọn.
- `toFormatter(locale)` để tạo formatter hoàn chỉnh.

Ví dụ không dùng pattern cho phần giờ:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.TextStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

DateTimeFormatter formatter = new DateTimeFormatterBuilder()
        .appendValue(ChronoField.CLOCK_HOUR_OF_AMPM)
        .appendLiteral(':')
        .appendValue(ChronoField.MINUTE_OF_HOUR, 2)
        .appendLiteral(' ')
        .appendDayPeriodText(TextStyle.FULL)
        .toFormatter(Locale.US);

System.out.println(formatter.format(LocalTime.of(15, 30)));
```

Ví dụ này cho thấy builder có thể ghép các trường một cách tường minh. Với pattern quen thuộc, `appendPattern("h:mm ")` ngắn gọn hơn và thường dễ bảo trì hơn.

### Thêm giây tùy chọn

```java
DateTimeFormatter formatter = new DateTimeFormatterBuilder()
        .appendPattern("h:mm")
        .optionalStart()
        .appendPattern(":ss")
        .optionalEnd()
        .appendLiteral(' ')
        .appendDayPeriodText(TextStyle.FULL)
        .toFormatter(Locale.US);
```

Phần `:ss` có thể xuất hiện khi dữ liệu có giây. Khi parse, phần tùy chọn cũng có thể vắng mặt. Hãy kiểm tra round-trip theo độ chính xác mà ứng dụng yêu cầu.

## 5. Locale quyết định ánh xạ và bản dịch

`appendDayPeriodText` không nhận locale trực tiếp. Locale được gắn khi builder hoàn tất bằng `toFormatter(Locale)`.

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale englishUS = Locale.US;

DateTimeFormatter viFormatter = new DateTimeFormatterBuilder()
        .appendPattern("h:mm ")
        .appendDayPeriodText(TextStyle.FULL)
        .toFormatter(vietnamese);

DateTimeFormatter enFormatter = new DateTimeFormatterBuilder()
        .appendPattern("h:mm ")
        .appendDayPeriodText(TextStyle.FULL)
        .toFormatter(englishUS);
```

Cùng một `LocalTime` có thể tạo day period và bản dịch khác nhau giữa hai formatter. Không suy ra locale từ `ZoneId`; ngôn ngữ hiển thị và múi giờ là hai lựa chọn độc lập.

### Vai trò của dữ liệu CLDR

CLDR định nghĩa các loại day period, ranh giới thời gian và tên văn bản theo locale. Trong lúc định dạng, Java lấy giờ trong ngày, có thể dùng thêm phút, ánh xạ thời gian sang loại day period rồi tra bản dịch.

Điều này có nghĩa:

- Không tự hard-code ranh giới như 12:00 hoặc 18:00 để giả lập CLDR.
- Không giả định mọi locale đều có đủ các nhãn morning, afternoon, evening và night.
- Kết quả có thể thay đổi khi dữ liệu locale được cập nhật cùng JDK.
- Test nên kiểm tra hợp đồng cần thiết, không khóa cứng bản dịch ngoài cam kết sản phẩm.

## 6. Builder là mutable, formatter hoàn chỉnh là immutable

`DateTimeFormatterBuilder` là đối tượng mutable và được thiết kế để sử dụng từ một thread trong lúc dựng formatter. Không chia sẻ cùng một builder cho nhiều luồng cùng sửa đổi.

Sau khi gọi `toFormatter(locale)`, đối tượng `DateTimeFormatter` được tạo ra là immutable và thread-safe. Có thể lưu formatter đã hoàn tất trong cấu hình hoặc cache theo locale/style và tái sử dụng giữa các request.

Ví dụ:

```java
private static final DateTimeFormatter US_DAY_PERIOD =
        new DateTimeFormatterBuilder()
                .appendPattern("h:mm ")
                .appendDayPeriodText(TextStyle.FULL)
                .toFormatter(Locale.US);
```

Nếu ứng dụng hỗ trợ nhiều locale, hãy tạo formatter tương ứng với locale đã chọn. Không gọi `Locale.setDefault()` để thay đổi ngôn ngữ định dạng cho riêng một request.

### toFormatter() và toFormatter(Locale)

| Phương thức | Locale sử dụng |
| --- | --- |
| `toFormatter()` | Default FORMAT locale của tiến trình |
| `toFormatter(locale)` | Locale được truyền rõ ràng |

Với ứng dụng server hoặc ứng dụng đa ngôn ngữ, ưu tiên `toFormatter(locale)` để kết quả không phụ thuộc cấu hình máy chạy.

## 7. Parse day period bằng builder

`appendDayPeriodText` hỗ trợ cả format và parse. Khi parse, văn bản được chuyển thành loại day period trước; ở giai đoạn resolve, loại này kết hợp với trường giờ/phút để tạo `LocalTime`.

Ví dụ:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.ResolverStyle;
import java.time.format.TextStyle;
import java.util.Locale;

DateTimeFormatter parser = new DateTimeFormatterBuilder()
        .appendPattern("h:mm ")
        .appendDayPeriodText(TextStyle.FULL)
        .toFormatter(Locale.US)
        .withResolverStyle(ResolverStyle.STRICT);

LocalTime parsed =
        LocalTime.parse("3:30 in the afternoon", parser);

System.out.println(parsed);
```

Nếu pattern có giờ 12 tiếng, parser kết hợp `HOUR_OF_AMPM` với day period để xác định `HOUR_OF_DAY`, có xét đến phút. Nếu pattern có `HOUR_OF_DAY`, parser kiểm tra giờ đó có thuộc day period đã parse không.

### Chỉ parse tên day period

Nếu văn bản chỉ có day period và không có giờ, phút, giây hoặc nano giây, chế độ `SMART` và `LENIENT` resolve về điểm giữa của khoảng day period.

Ví dụ, nếu locale định nghĩa khoảng `night1` từ 21:00 đến 06:00, midpoint là 01:30. Đây là giá trị đại diện để hoàn tất parse, không phải thời điểm chính xác do người dùng cung cấp.

### Xung đột giữa giờ và day period

Nếu thời gian đã resolve không phù hợp với day period:

| ResolverStyle | Hành vi |
| --- | --- |
| `STRICT` | Ném `DateTimeException` |
| `SMART` | Ném `DateTimeException` |
| `LENIENT` | Bỏ qua day period đã parse và không ném lỗi do xung đột này |

`midnight` là loại đặc biệt cho phép cả 00:00 ở đầu ngày và 24:00 ở cuối ngày nếu phù hợp với trường giờ đã resolve.

Khi xác thực dữ liệu nhập, chọn resolver style rõ ràng. Không dùng `LENIENT` chỉ để làm parser chấp nhận chuỗi mâu thuẫn.

## 8. Kiểm thử format và parse

Test nên dùng cùng locale, formatter và thời gian đầu vào cố định:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.TextStyle;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class DayPeriodBuilderTest {
    @Test
    void formatsAndParsesWithTheSameLocale() {
        DateTimeFormatter formatter = new DateTimeFormatterBuilder()
                .appendPattern("h:mm ")
                .appendDayPeriodText(TextStyle.FULL)
                .toFormatter(Locale.US);

        LocalTime original = LocalTime.of(15, 30);
        String text = formatter.format(original);
        LocalTime parsed = LocalTime.parse(text, formatter);

        assertFalse(text.isBlank());
        assertEquals(original, parsed);
    }
}
```

Test này xác nhận formatter có thể round-trip giờ khi pattern cung cấp đủ giờ và phút. Nó không yêu cầu một bản dịch cố định cho mọi JDK.

### Kiểm thử ba TextStyle

Có thể chạy cùng một test với `SHORT`, `FULL` và `NARROW`. Mục tiêu là xác nhận cả ba formatter tạo được văn bản và parse lại được theo locale thử nghiệm. Không assertion rằng:

- Ba kết quả luôn khác nhau.
- `FULL` luôn dài hơn `SHORT`.
- `NARROW` luôn chỉ có một ký tự.

### Kiểm thử locale sản phẩm hỗ trợ

Lặp qua locale được sản phẩm cam kết, ví dụ `Locale.US`, `Locale.UK`, `vi-VN` và `fr-FR`. Nếu bản dịch cụ thể là yêu cầu sản phẩm, cố định JDK/vendor và locale provider trong môi trường test, rồi quản lý snapshot theo quy trình cập nhật dữ liệu locale.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy `appendDayPeriodText` khi compile | Compiler hoặc API baseline trước Java 16 | Dùng JDK 16 trở lên và xác minh toolchain |
| Chuỗi day period khác giữa máy | Formatter dùng default locale hoặc dữ liệu CLDR khác nhau | Gọi `toFormatter(locale)` và test trên JDK mục tiêu |
| Gọi builder từ nhiều thread | Builder mutable, không an toàn khi cùng sửa đổi | Dựng formatter riêng rồi chia sẻ formatter hoàn chỉnh |
| Parse chỉ có tên khoảng trả về giờ lạ | Resolver dùng midpoint của day period | Cung cấp cả giờ/phút nếu cần thời điểm cụ thể |
| Parse báo `DateTimeException` | Giờ không thuộc day period đã đọc | Kiểm tra locale, pattern và resolver style |
| Parse chấp nhận dữ liệu mâu thuẫn | Đang dùng `LENIENT` | Chuyển sang `STRICT` hoặc `SMART` nếu cần xác thực |
| Dùng `appendText(AMPM_OF_DAY)` nhưng muốn buổi chiều/tối | AM/PM chỉ chia ngày thành hai nửa | Dùng `appendDayPeriodText` |
| Pattern hoạt động khi compile nhưng lỗi trên runtime cũ | API/pattern day period chưa có trong runtime trước Java 16 | Kiểm tra JDK chạy ứng dụng, không chỉ JDK biên dịch |

## 10. Checklist áp dụng

| Hạng mục | Câu hỏi xác nhận |
| --- | --- |
| API | Runtime có hỗ trợ `appendDayPeriodText` từ Java 16 không? |
| Style | Đã chọn `SHORT`, `FULL` hoặc `NARROW` theo giao diện chưa? |
| Locale | Có truyền locale rõ ràng vào `toFormatter(locale)` không? |
| Thành phần giờ | Formatter có giờ/phút cần thiết để format và parse không? |
| Builder | Builder có được giới hạn trong một thread khi dựng không? |
| Formatter | Chỉ chia sẻ formatter sau khi đã hoàn tất bằng `toFormatter()` chưa? |
| Parse | Có chọn resolver style theo yêu cầu xác thực không? |
| Midpoint | Có tránh dùng parse chỉ day period để khôi phục thời điểm gốc không? |
| Kiểm thử | Có test round-trip và locale sản phẩm hỗ trợ không? |
| Nghiệp vụ | Day period có chỉ phục vụ hiển thị, không quyết định quy tắc nghiệp vụ không? |

## 11. Bài tập thực hành

### Bài 1 — Tạo formatter bằng builder

Tạo formatter gồm giờ, phút và day period đầy đủ bằng `appendPattern()` kết hợp `appendDayPeriodText(TextStyle.FULL)`. Định dạng một `LocalTime` buổi chiều.

### Bài 2 — So sánh TextStyle

Tạo ba formatter với `SHORT`, `FULL` và `NARROW`. Dùng cùng thời gian và locale, ghi lại kết quả và giải thích vì sao không nên giả định độ dài chuỗi.

### Bài 3 — So sánh appendText và appendDayPeriodText

Tạo một formatter dùng `appendText(ChronoField.AMPM_OF_DAY, TextStyle.SHORT)` và một formatter dùng `appendDayPeriodText(TextStyle.FULL)`. Định dạng cùng một giờ buổi chiều và giải thích khác biệt thông tin.

### Bài 4 — Parse và resolve

Parse chuỗi có giờ/phút/day period bằng `STRICT`. Thử chuỗi mâu thuẫn và quan sát exception. Sau đó thử parse chỉ có day period trong `SMART`, ghi lại midpoint.

### Bài 5 — Nhiều locale

Tạo formatter bằng `toFormatter(locale)` cho `Locale.US`, `Locale.UK` và `vi-VN`. Định dạng cùng `LocalTime` và giải thích vì sao văn bản có thể khác.

### Bài 6 — Tái sử dụng formatter

Tạo formatter một lần rồi dùng trong nhiều lời gọi format. Giải thích vì sao có thể chia sẻ `DateTimeFormatter`, nhưng không nên dùng chung một `DateTimeFormatterBuilder` mutable giữa nhiều thread.

## Tài liệu chính thức

- [Java SE 16 — `DateTimeFormatterBuilder.appendDayPeriodText`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html) — hợp đồng API, mapping theo locale, parse/resolve và `Since: 16`.
- [Java SE 16 — `TextStyle`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/TextStyle.html) — các style `SHORT`, `FULL`, `NARROW` và biến thể standalone.
- [Java SE 16 — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/DateTimeFormatter.html) — formatter immutable, thread-safe và resolver style.
- [Java SE 25 — `DateTimeFormatterBuilder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html) — xác nhận `appendDayPeriodText` vẫn được hỗ trợ trong JDK hiện đại.
- [Unicode CLDR — Dates, Day Periods](https://www.unicode.org/reports/tr35/tr35-dates.html) — định nghĩa LDML cho day period và dữ liệu locale.

**Nguyên tắc áp dụng:** Dùng `appendDayPeriodText(TextStyle)` khi cần thêm day period linh hoạt vào formatter tự dựng. Chọn `SHORT`, `FULL` hoặc `NARROW` theo giao diện, truyền locale tường minh, hiểu quy tắc parse/resolve và chỉ chia sẻ formatter sau khi builder đã hoàn tất.
