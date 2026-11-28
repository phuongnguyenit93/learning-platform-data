# Pattern B của DateTimeFormatter được bổ sung từ Java 16

> **Chương:** Định dạng day period  
> **Phạm vi:** Tập trung vào cú pháp pattern `B` của `DateTimeFormatter`, các dạng văn bản ngắn/đầy đủ/hẹp, cách dựng formatter, cách parse và quy tắc resolve. Đây là API chính thức từ Java 16 và vẫn được hỗ trợ trong JDK hiện đại.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận biết `B` là pattern letter biểu diễn day period trong `DateTimeFormatter`.
2. Chọn đúng độ rộng `B`, `BBBB` hoặc `BBBBB`.
3. Tạo formatter bằng `DateTimeFormatter.ofPattern()` hoặc `DateTimeFormatterBuilder`.
4. Kết hợp day period với giờ 12 tiếng hoặc 24 tiếng.
5. Hiểu cách parser kết hợp giờ và day period, xử lý xung đột và midpoint.
6. Tránh nhầm pattern của `DateTimeFormatter` với `SimpleDateFormat` hoặc định dạng dữ liệu trao đổi.

## 1. Pattern B là gì?

Java 16 bổ sung pattern letter **`B`** cho `DateTimeFormatter`. Ký hiệu này đại diện cho *period-of-day*: tên khoảng trong ngày do dữ liệu locale xác định, chẳng hạn “in the morning”, “in the afternoon” hoặc một cách gọi tương ứng trong ngôn ngữ khác.

`B` là ký hiệu định dạng văn bản. Nó không phải một trường số giờ, không phải AM/PM và cũng không phải một quy tắc giờ cố định trong mã ứng dụng.

Ví dụ:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US);

System.out.println(formatter.format(LocalTime.of(9, 0)));
System.out.println(formatter.format(LocalTime.of(15, 30)));
```

Với dữ liệu locale tiếng Anh Mỹ, kết quả có thể có dạng:

```text
9:00 in the morning
3:30 in the afternoon
```

Văn bản cụ thể phụ thuộc locale và dữ liệu CLDR đi kèm JDK. Không coi các ví dụ đầu ra là chuỗi cố định cho mọi nhà cung cấp hoặc mọi bản cập nhật JDK.

## 2. Phân biệt B với a, h và H

Các ký hiệu thường xuất hiện cùng nhau nhưng mang ý nghĩa khác nhau:

| Pattern | Ý nghĩa | Vai trò |
| --- | --- | --- |
| `a` | AM/PM | Chia ngày thành hai nửa |
| `B` | Day period | Hiển thị khoảng trong ngày theo locale |
| `h` | Giờ đồng hồ 12 tiếng, 1–12 | Số giờ trong nửa ngày |
| `K` | Giờ trong AM/PM, 0–11 | Số giờ bắt đầu từ 0 |
| `H` | Giờ trong ngày, 0–23 | Số giờ theo đồng hồ 24 tiếng |
| `k` | Giờ đồng hồ trong ngày, 1–24 | Biểu diễn 24:00 ở cuối ngày |
| `m` | Phút trong giờ | Thành phần phút |

So sánh:

```java
LocalTime time = LocalTime.of(15, 30);

DateTimeFormatter amPm =
        DateTimeFormatter.ofPattern("h:mm a", Locale.US);
DateTimeFormatter dayPeriod =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US);

System.out.println(amPm.format(time));
System.out.println(dayPeriod.format(time));
```

`a` chỉ cho biết thời điểm thuộc PM. `B` có thể diễn đạt một khoảng cụ thể hơn theo quy tắc locale. Không thể thay thế `B` bằng `a` nếu yêu cầu giao diện cần phân biệt buổi chiều, buổi tối hoặc ban đêm.

## 3. Độ rộng văn bản của B

Tài liệu `DateTimeFormatterBuilder` định nghĩa các dạng chuẩn:

| Pattern | `TextStyle` tương đương | Ý nghĩa |
| --- | --- | --- |
| `B` | `TextStyle.SHORT` | Dạng ngắn |
| `BBBB` | `TextStyle.FULL` | Dạng đầy đủ |
| `BBBBB` | `TextStyle.NARROW` | Dạng hẹp |

Ví dụ:

```java
LocalTime time = LocalTime.of(15, 30);

DateTimeFormatter shortFormatter =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US);
DateTimeFormatter fullFormatter =
        DateTimeFormatter.ofPattern("h:mm BBBB", Locale.US);
DateTimeFormatter narrowFormatter =
        DateTimeFormatter.ofPattern("h:mm BBBBB", Locale.US);

System.out.println(shortFormatter.format(time));
System.out.println(fullFormatter.format(time));
System.out.println(narrowFormatter.format(time));
```

Các dạng này phục vụ bố cục giao diện:

- Dạng ngắn phù hợp vùng hiển thị hẹp.
- Dạng đầy đủ thường dễ hiểu hơn trong văn bản hoặc lịch.
- Dạng hẹp có thể phù hợp nhãn nhỏ, nhưng không phải locale nào cũng cung cấp dạng rút gọn dễ phân biệt.

Đừng giả định `B`, `BBBB` và `BBBBB` luôn tạo ra ba chuỗi khác nhau. Một locale có thể dùng cùng văn bản cho nhiều kiểu trình bày.

## 4. Tạo formatter bằng ofPattern

`DateTimeFormatter.ofPattern(pattern, locale)` là cách ngắn gọn khi pattern đã biết:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class DayPeriodPatternDemo {
    public static void main(String[] args) {
        Locale locale = Locale.US;
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("h:mm B", locale);

        LocalTime[] times = {
                LocalTime.of(7, 45),
                LocalTime.of(12, 15),
                LocalTime.of(16, 30),
                LocalTime.of(22, 10)
        };

        for (LocalTime time : times) {
            System.out.println(formatter.format(time));
        }
    }
}
```

Nên truyền `Locale` tường minh thay vì phụ thuộc locale mặc định của tiến trình. Nếu dùng `ofPattern(String)` không có tham số locale, formatter sử dụng default FORMAT locale tại thời điểm tạo formatter.

Với giao diện đa ngôn ngữ, có thể tạo formatter theo locale của người dùng:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("h:mm B", locale);
```

Đoạn mã cho thấy cách chọn locale, không cam kết một chuỗi tiếng Việt cụ thể. Kết quả cần được kiểm tra trên JDK/vendor mà sản phẩm triển khai.

### Kết hợp literal trong pattern

Ký tự chữ trong pattern có ý nghĩa định dạng. Nếu muốn in một từ cố định, đặt nó trong dấu nháy đơn:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("'At' h:mm B", Locale.US);
```

Để in chính ký tự `B`, dùng literal `'B'`. Nếu để `B` không có dấu nháy, formatter sẽ diễn giải nó như pattern day period.

Pattern của `DateTimeFormatter` tương tự một phần với `SimpleDateFormat`, nhưng không hoàn toàn giống nhau. Không sao chép pattern cũ giữa hai API mà không kiểm tra ý nghĩa từng ký hiệu.

## 5. Dựng formatter bằng DateTimeFormatterBuilder

Khi pattern có nhiều phần hoặc cần chọn `TextStyle` bằng mã, dùng `DateTimeFormatterBuilder.appendDayPeriodText(TextStyle)`.

Ví dụ:

```java
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.TextStyle;
import java.util.Locale;

DateTimeFormatter formatter = new DateTimeFormatterBuilder()
        .appendPattern("h:mm ")
        .appendDayPeriodText(TextStyle.FULL)
        .toFormatter(Locale.US);
```

Phương thức `appendDayPeriodText` có từ Java 16. Các kiểu thường dùng là `TextStyle.SHORT`, `TextStyle.FULL` và `TextStyle.NARROW`, tương ứng với `B`, `BBBB` và `BBBBB`.

Builder là đối tượng mutable và được thiết kế để sử dụng trong một thread khi đang dựng formatter. Sau khi gọi `toFormatter(locale)`, kết quả `DateTimeFormatter` là immutable và thread-safe, nên có thể chia sẻ formatter đã tạo giữa các luồng.

### Khi nào nên dùng cách nào?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Pattern đơn giản, cố định | `DateTimeFormatter.ofPattern()` |
| Chọn style bằng enum | `DateTimeFormatterBuilder.appendDayPeriodText()` |
| Kết hợp phần bắt buộc và tùy chọn | `DateTimeFormatterBuilder` |
| Tái sử dụng formatter giữa các luồng | Tạo một `DateTimeFormatter` hoàn chỉnh rồi chia sẻ |

## 6. B được ánh xạ từ giờ như thế nào?

Trong lúc định dạng, day period được lấy từ `HOUR_OF_DAY` và có thể sử dụng thêm `MINUTE_OF_HOUR` nếu trường này có sẵn. Sau đó, thời điểm được ánh xạ sang một day period type trong LDML, chẳng hạn `morning1`, rồi chuyển thành văn bản theo locale của formatter.

Điều này có hai hệ quả:

1. Cùng một giờ có thể cho văn bản khác nhau ở các locale khác nhau.
2. Phút có thể ảnh hưởng đến cách phân loại nếu dữ liệu locale đặt ranh giới ở giữa một giờ.

Với `LocalTime`, cả giờ và phút đều có sẵn. Với `Instant`, cần có múi giờ để chuyển thời điểm thành giờ địa phương trước khi định dạng. Một formatter có thể được gắn vùng bằng `withZone(ZoneId)`:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US)
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

String text = formatter.format(Instant.parse("2026-11-27T08:30:00Z"));
```

Day period là phần trình bày theo giờ địa phương. Không lấy trực tiếp một `Instant` rồi tự suy ra buổi sáng/chiều bằng giờ UTC.

## 7. Parse văn bản có B

`B` hỗ trợ cả định dạng lẫn phân tích. Khi parse, văn bản được chuyển thành day period type trước; ở giai đoạn resolve, day period được kết hợp với các trường thời gian khác để tạo `LocalTime`.

Ví dụ có giờ 12 tiếng:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US);

LocalTime parsed = LocalTime.parse("3:30 in the afternoon", formatter);
System.out.println(parsed);
```

Với `HOUR_OF_AMPM` có trong pattern `h`, parser kết hợp giờ đó với day period để xác định `HOUR_OF_DAY`, có xét đến phút nếu có.

Ví dụ có giờ 24 tiếng:

```java
DateTimeFormatter formatter24 =
        DateTimeFormatter.ofPattern("HH:mm B", Locale.US);

LocalTime parsed = LocalTime.parse("15:30 in the afternoon", formatter24);
```

Khi `HOUR_OF_DAY` có sẵn, parser kiểm tra giờ đó có phù hợp với day period đã parse hay không.

### Không có giờ và phút

Nếu chuỗi chỉ chứa day period, không có `HOUR_OF_DAY`, `MINUTE_OF_HOUR`, `SECOND_OF_MINUTE` và `NANO_OF_SECOND`, quy tắc resolve trong chế độ `SMART` và `LENIENT` đặt thời gian ở **điểm giữa của khoảng day period**.

Ví dụ theo tài liệu API: nếu locale định nghĩa `night1` từ 21:00 đến 06:00, điểm giữa là 01:30. Kết quả đó chỉ là giá trị đại diện được chọn để resolve, không phải thời điểm chính xác mà người dùng đã nói.

Vì vậy, không dùng chuỗi chỉ có “buổi chiều” hoặc “ban đêm” để khôi phục giờ gốc của một sự kiện.

## 8. ResolverStyle và xử lý xung đột

`DateTimeFormatter` mặc định dùng `ResolverStyle.SMART`. Khi parse day period, resolver kiểm tra sự phù hợp giữa giờ và khoảng thời gian đã đọc.

| ResolverStyle | Khi giờ không phù hợp với day period |
| --- | --- |
| `STRICT` | Ném `DateTimeException` |
| `SMART` | Ném `DateTimeException` |
| `LENIENT` | Không ném lỗi; day period đã parse bị bỏ qua |

Ví dụ dùng giờ 24 tiếng để thể hiện xung đột rõ ràng:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter strictFormatter =
        DateTimeFormatter.ofPattern("HH:mm B", Locale.US)
                .withResolverStyle(ResolverStyle.STRICT);

// 03:30 không thuộc khoảng "in the afternoon" trong locale này.
LocalTime.parse("03:30 in the afternoon", strictFormatter);
```

Lời gọi cuối sẽ thất bại khi giờ và day period mâu thuẫn theo dữ liệu locale. Trong ứng dụng cần xác thực đầu vào, `STRICT` thường là lựa chọn dễ hiểu vì yêu cầu dữ liệu phải nhất quán.

Không chọn `LENIENT` chỉ để tránh exception. Ở chế độ này, khi xung đột xảy ra, day period có thể bị bỏ qua và kết quả vẫn được resolve từ trường giờ. Điều đó có thể che giấu lỗi dữ liệu đầu vào.

### Trường hợp midnight

Day period type `midnight` cho phép cả `00:00` ở đầu ngày và `24:00` ở cuối ngày nếu phù hợp với trường giờ đã resolve. Đây là ngoại lệ có chủ đích trong quy tắc resolve; không tự áp dụng cách xử lý này cho mọi nhãn day period.

## 9. Parse không phân biệt hoa/thường khi cần

Mặc định parser của `DateTimeFormatterBuilder` phân biệt chữ hoa và chữ thường. Nếu dữ liệu đầu vào do người dùng nhập và sản phẩm cho phép nhiều kiểu viết, có thể cấu hình `parseCaseInsensitive()`:

```java
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.util.Locale;

DateTimeFormatter parser = new DateTimeFormatterBuilder()
        .parseCaseInsensitive()
        .appendPattern("h:mm B")
        .toFormatter(Locale.US);
```

Tùy chọn này ảnh hưởng cách parser so khớp văn bản sau vị trí được gọi trong builder. Chỉ bật khi yêu cầu sản phẩm cho phép; không tự động chuẩn hóa mọi văn bản nếu dữ liệu đầu vào cần giữ nguyên quy tắc chính tả của locale.

## 10. Các lỗi thường gặp với pattern B

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `IllegalArgumentException: Unknown pattern letter: B` | Chạy trên JDK trước Java 16 hoặc dùng API pattern không hỗ trợ `B` | Chạy trên JDK 16 trở lên; xác minh runtime thực tế |
| Không có nhãn day period như mong đợi | Locale hoặc dữ liệu locale không cung cấp dạng văn bản như kỳ vọng | Kiểm tra locale/JDK mục tiêu và dữ liệu CLDR |
| Parse thất bại dù chuỗi trông hợp lý | Giờ và day period không nhất quán, văn bản không khớp locale hoặc parser phân biệt hoa/thường | Kiểm tra resolver style, locale và nội dung đầu vào |
| Parse chỉ có `B` cho ra giờ không như mong đợi | Resolver chọn midpoint của khoảng trong `SMART`/`LENIENT` | Cung cấp cả giờ/phút nếu cần thời điểm chính xác |
| `UnsupportedTemporalTypeException` khi format | Đối tượng không cung cấp trường giờ cần thiết, ví dụ chỉ có `LocalDate` | Dùng kiểu có giờ như `LocalTime`/`LocalDateTime` hoặc cung cấp dữ liệu giờ |
| Chuỗi hiển thị thay đổi sau khi nâng JDK | Dữ liệu locale/CLDR hoặc nhà cung cấp JDK đã thay đổi | Kiểm thử lại locale và quản lý snapshot theo môi trường |
| Kết quả sai múi giờ | Format `Instant` mà không áp dụng `ZoneId` hiển thị phù hợp | Dùng `ZonedDateTime` hoặc `formatter.withZone(zone)` |

### Lưu ý khi dùng `--release`

`--release 16` kiểm tra sự tồn tại của API Java khi mã nguồn tham chiếu trực tiếp đến API đó. Nhưng pattern `B` thường nằm trong một chuỗi:

```java
DateTimeFormatter.ofPattern("h:mm B", locale);
```

Compiler không phân tích nội dung chuỗi pattern để xác nhận ký tự `B` có được runtime hỗ trợ hay không. Vì vậy, mã có thể biên dịch nhưng vẫn lỗi lúc chạy trên JDK trước Java 16. Hãy xác minh cả JDK compile lẫn runtime thực tế.

## 11. Pattern B không phải định dạng dữ liệu trao đổi

Day period là văn bản hiển thị cho con người. Nó phụ thuộc locale, có thể thay đổi theo dữ liệu CLDR và không biểu diễn một thời điểm duy nhất nếu chỉ có tên khoảng.

Không dùng chuỗi chứa `B` làm:

- Giá trị timestamp lưu trong database.
- Định dạng chuẩn cho REST API hoặc message queue.
- Khóa so sánh thời gian giữa các hệ thống.
- Cơ sở để quyết định ca làm, giờ mở cửa hoặc quy tắc nghiệp vụ.

Hãy lưu kiểu thời gian phù hợp:

- `Instant` cho thời điểm tuyệt đối.
- `ZonedDateTime` khi cần giữ cả thời điểm và vùng thời gian.
- `LocalDateTime` khi dữ liệu là giờ địa phương không gắn múi giờ.
- `LocalTime` khi chỉ cần giờ trong ngày.

Khi hiển thị, chuyển dữ liệu sang múi giờ người dùng và định dạng bằng locale phù hợp. `B` chỉ là một cách trình bày của thời điểm đã xác định.

## 12. Kiểm thử formatter có B

Test nên tập trung vào hợp đồng cần giữ: format có kết quả, parse với cùng formatter cho lại giờ khi pattern có đủ thông tin, và xung đột bị phát hiện theo resolver style.

Ví dụ JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.DateTimeException;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class DayPeriodPatternTest {
    @Test
    void formatsAndParsesUsingTheSameLocale() {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("h:mm B", Locale.US);
        LocalTime original = LocalTime.of(15, 30);

        String text = formatter.format(original);
        LocalTime parsed = LocalTime.parse(text, formatter);

        assertFalse(text.isBlank());
        assertEquals(original, parsed);
    }

    @Test
    void rejectsAnHourThatConflictsWithTheDayPeriod() {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("HH:mm B", Locale.US)
                        .withResolverStyle(ResolverStyle.STRICT);

        assertThrows(
                DateTimeException.class,
                () -> LocalTime.parse("03:30 in the afternoon", formatter));
    }
}
```

Không khóa cứng bản dịch nếu sản phẩm không cam kết chuỗi cụ thể. Nếu cần kiểm tra snapshot giao diện, cố định JDK vendor/version, locale provider và locale; khi nâng JDK, xem lại snapshot cùng dữ liệu locale.

### Kiểm tra nhiều locale

Có thể lặp qua các locale mà sản phẩm hỗ trợ:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;

List<Locale> locales = List.of(
        Locale.US,
        Locale.UK,
        Locale.forLanguageTag("vi-VN"),
        Locale.forLanguageTag("fr-FR")
);

for (Locale locale : locales) {
    DateTimeFormatter formatter =
            DateTimeFormatter.ofPattern("h:mm B", locale);
    String text = formatter.format(LocalTime.of(15, 30));
    if (text.isBlank()) {
        throw new AssertionError("Empty day-period text for " + locale);
    }
}
```

Mục tiêu của test này là xác nhận các locale được sản phẩm hỗ trợ đều tạo ra nội dung. Nếu bản dịch là yêu cầu bắt buộc, thêm kiểm tra chuỗi riêng cho từng locale với phiên bản dữ liệu được quản lý.

## 13. Checklist áp dụng pattern B

| Hạng mục | Câu hỏi xác nhận |
| --- | --- |
| Phiên bản | Runtime thực tế có phải Java 16 trở lên không? |
| Pattern | Đã dùng `B`, `BBBB` hoặc `BBBBB` theo mục tiêu trình bày chưa? |
| Locale | Formatter có nhận locale tường minh không? |
| Dữ liệu giờ | Đối tượng có cung cấp trường giờ cần thiết không? |
| Múi giờ | Nếu dữ liệu là `Instant`, đã áp dụng `ZoneId` hiển thị chưa? |
| Parse | Chuỗi có giờ/phút nếu cần khôi phục thời điểm cụ thể không? |
| Resolve | Có cần `STRICT` để phát hiện xung đột không? |
| Kiểm thử | Có test round-trip và trường hợp xung đột không? |
| Tương thích | Đã kiểm tra runtime, không chỉ compile với `--release 16`, chưa? |
| Lưu trữ | Dữ liệu hệ thống có giữ kiểu thời gian thay vì chuỗi day period không? |

## 14. Bài tập thực hành

### Bài 1 — Chọn độ rộng

Tạo formatter với `B`, `BBBB` và `BBBBB` cho cùng một giờ và locale. So sánh kết quả, ghi nhận trường hợp các dạng trùng nhau và chọn kiểu phù hợp với giao diện.

### Bài 2 — Kết hợp giờ 12 và 24 tiếng

Tạo hai formatter `h:mm B` và `HH:mm B`. Định dạng cùng một `LocalTime`, sau đó parse lại từng chuỗi. Giải thích vai trò của `HOUR_OF_AMPM` và `HOUR_OF_DAY`.

### Bài 3 — Kiểm tra xung đột

Dùng `HH:mm B` để parse một chuỗi mà giờ không thuộc day period. Thử `STRICT`, `SMART` và `LENIENT`, ghi lại hành vi và giải thích vì sao `LENIENT` có thể bỏ qua day period.

### Bài 4 — Parse chỉ có day period

Dùng formatter chỉ chứa `B` để parse văn bản do formatter tạo ra từ một giờ cụ thể. Quan sát thời gian kết quả và giải thích quy tắc midpoint.

### Bài 5 — Kiểm tra runtime

Biên dịch mã với JDK mới và `--release 16`. Chạy thử trên runtime Java 16 trở lên, sau đó giải thích vì sao compiler không phát hiện ký tự `B` trong chuỗi pattern khi runtime quá cũ.

## Tài liệu chính thức

- [Java SE 16 — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/DateTimeFormatter.html) — bảng pattern letter, trong đó `B` là period-of-day.
- [Java SE 16 — `DateTimeFormatterBuilder.appendDayPeriodText`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html) — ánh xạ giờ sang day period, parse và quy tắc resolve; phương thức có từ Java 16.
- [Java SE 25 — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html) — xác nhận pattern `B` tiếp tục được hỗ trợ.
- [Java SE 25 — `DateTimeFormatterBuilder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html) — builder và `appendDayPeriodText`.
- [Unicode CLDR — Dates, Day Periods](https://www.unicode.org/reports/tr35/tr35-dates.html) — định nghĩa day period và dữ liệu locale.

**Nguyên tắc áp dụng:** Dùng pattern `B` để trình bày day period theo locale; chọn `B`/`BBBB`/`BBBBB` theo không gian giao diện, truyền locale và múi giờ rõ ràng, hiểu quy tắc resolve khi parse, và giữ dữ liệu thời gian ở kiểu dữ liệu chuẩn thay vì chuỗi day period.
