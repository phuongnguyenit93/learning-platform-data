# Parse giờ có day period và ảnh hưởng của ResolverStyle

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Định dạng day period. Java 16 bổ sung khả năng định dạng và phân tích day period linh hoạt qua ký hiệu mẫu `B` trong `DateTimeFormatter` và phương thức `appendDayPeriodText` của `DateTimeFormatterBuilder`. Day period có thể biểu diễn các khoảng như buổi sáng, buổi chiều, buổi tối, ban đêm, trưa hoặc nửa đêm tùy locale. Khi parse, thông tin này được kết hợp với giờ và phút để tạo `LocalTime` hoặc được dùng để kiểm tra giờ đã có. Bài học tập trung vào cách parse đúng và vai trò của `ResolverStyle` trong giai đoạn resolve.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt day period linh hoạt với AM/PM truyền thống.
- Dùng ký hiệu `B` để format và parse giờ theo locale.
- Kết hợp day period với giờ 12 tiếng hoặc kiểm tra giờ 24 tiếng.
- Giải thích hai giai đoạn parse và resolve của `DateTimeFormatter`.
- Phân biệt hành vi của `STRICT`, `SMART` và `LENIENT` khi day period mâu thuẫn với giờ.
- Hiểu cách parse khi đầu vào chỉ có day period mà không có giờ.
- Viết test cho dữ liệu hợp lệ, xung đột, thiếu trường và locale khác nhau.

## 1. Day period là gì?

Day period là cách chia ngày thành những khoảng thời gian có tên theo ngôn ngữ và quy ước địa phương. Ví dụ tiếng Anh có thể hiển thị:

- `in the morning` — buổi sáng.
- `in the afternoon` — buổi chiều.
- `in the evening` — buổi tối.
- `at night` — ban đêm.
- `noon` — buổi trưa.
- `midnight` — nửa đêm.

Các khoảng này không nhất thiết chia ngày thành hai nửa cố định như AM và PM. Ranh giới và cách hiển thị phụ thuộc locale và dữ liệu locale của JDK. Một locale có thể phân biệt buổi sáng, buổi chiều, buổi tối và ban đêm; locale khác có thể có cách chia hoặc tên gọi khác.

### 1.1. Phân biệt `a` và `B`

Trong mẫu của `DateTimeFormatter`:

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| `a` | AM/PM của ngày | `AM`, `PM` |
| `B` | Day period linh hoạt theo locale | `in the morning`, `at night` |
| `h` | Giờ đồng hồ trong nửa ngày, từ 1 đến 12 | `1` đến `12` |
| `K` | Giờ trong nửa ngày, từ 0 đến 11 | `0` đến `11` |
| `H` | Giờ trong ngày, từ 0 đến 23 | `0` đến `23` |
| `k` | Giờ đồng hồ trong ngày, từ 1 đến 24 | `1` đến `24` |
| `m` | Phút trong giờ | `00` đến `59` |

`a` chỉ cho biết giờ thuộc AM hay PM. `B` có thể cung cấp thêm ngữ nghĩa như morning, afternoon, evening hoặc night. Do đó, `B` không phải cách viết khác của `a`.

Ví dụ, với locale tiếng Anh Mỹ, `2:30 in the afternoon` có thể được hiểu là 14:30. Day period giúp phân giải giờ 12 tiếng thành giờ trong ngày.

### 1.2. Ký hiệu B có từ Java 16

Java 16 bổ sung pattern letter `B` cho day period trong `DateTimeFormatter`. Khả năng tương ứng cũng có trong `DateTimeFormatterBuilder.appendDayPeriodText(TextStyle)`.

Đây là API của `java.time` và vẫn dùng được trong Java hiện đại. Khi biên dịch hoặc chạy trên Java 15 trở xuống, không thể giả định ký hiệu `B` được hỗ trợ.

## 2. Format giờ bằng day period

Ví dụ dùng `Locale.US` để định dạng `LocalTime`:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class DayPeriodFormatDemo {
    public static void main(String[] args) {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("h:mm B", Locale.US);

        LocalTime time = LocalTime.of(14, 30);
        String text = time.format(formatter);

        System.out.println(text);
    }
}
```

Với dữ liệu locale tiếng Anh Mỹ thường gặp, kết quả có dạng:

```text
2:30 in the afternoon
```

Kết quả thực tế phụ thuộc locale data của JDK. Không nên xem câu chữ ví dụ là chuỗi cố định cho mọi locale hoặc mọi môi trường.

### 2.1. Chọn locale tường minh

Không nên phụ thuộc locale mặc định của máy chạy ứng dụng khi định dạng hoặc parse dữ liệu người dùng. Hãy truyền locale phù hợp với ngôn ngữ của giao diện:

```java
DateTimeFormatter english = DateTimeFormatter.ofPattern("h:mm B", Locale.US);
DateTimeFormatter vietnamese = DateTimeFormatter.ofPattern(
        "h:mm B",
        Locale.forLanguageTag("vi-VN")
);
```

Hai formatter có thể hiển thị day period khác nhau. Không giả định tiếng Việt luôn có cùng số khoảng hoặc cách diễn đạt với tiếng Anh.

`DateTimeFormatter` là immutable và thread-safe, nên có thể tái sử dụng formatter đã cấu hình trong nhiều lời gọi. Nếu ứng dụng hỗ trợ nhiều locale, có thể giữ formatter riêng cho từng locale thay vì thay đổi locale mặc định toàn tiến trình.

### 2.2. Dùng DateTimeFormatterBuilder

Nếu muốn tạo formatter theo từng thành phần, dùng `appendDayPeriodText`:

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

`TextStyle.FULL` yêu cầu dạng văn bản đầy đủ. `TextStyle.SHORT` hoặc `NARROW` có thể tạo cách hiển thị ngắn hơn nếu locale cung cấp. Dùng pattern `B` thường ngắn gọn hơn; builder hữu ích khi cần ghép formatter phức tạp hoặc tạo các phần optional.

## 3. Parse giờ 12 tiếng kết hợp với day period

Khi parse, pattern `h:mm B` cung cấp:

- `h` — giờ trong nửa ngày.
- `m` — phút.
- `B` — day period theo locale.

Resolver kết hợp giờ 12 tiếng với day period để suy ra `HOUR_OF_DAY`. Ví dụ:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class DayPeriodParseDemo {
    public static void main(String[] args) {
        DateTimeFormatter formatter = DateTimeFormatter
                .ofPattern("h:mm B", Locale.US)
                .withResolverStyle(ResolverStyle.STRICT);

        LocalTime parsed = LocalTime.parse(
                "2:30 in the afternoon",
                formatter
        );

        System.out.println(parsed); // 14:30
    }
}
```

Với locale và day period tương ứng, `h` được kết hợp với `B` để xác định giờ trong ngày. Ví dụ `2:30 in the afternoon` cho kết quả 14:30.

Một ví dụ khác:

```java
LocalTime morning = LocalTime.parse(
        "10:15 in the morning",
        DateTimeFormatter.ofPattern("h:mm B", Locale.US)
);

LocalTime night = LocalTime.parse(
        "10:15 at night",
        DateTimeFormatter.ofPattern("h:mm B", Locale.US)
);
```

Các giá trị thường tương ứng với 10:15 và 22:15 trong locale tiếng Anh Mỹ. Ranh giới day period cụ thể do locale data quyết định; không tự suy luận rằng mọi giờ tối đều thuộc cùng một khoảng ở mọi ngôn ngữ.

### 3.1. Vì sao h và B có thể tạo ra một giờ duy nhất?

Trường `h` chỉ có thể biểu diễn một giờ trong chu kỳ 12 tiếng. Khi có `B`, resolver dùng day period để xác định giờ trong ngày phù hợp. Theo hợp đồng của API, nếu `HOUR_OF_AMPM` hiện diện, nó được kết hợp với day period để tạo `HOUR_OF_DAY`, có xét tới `MINUTE_OF_HOUR` nếu có.

Nếu đầu vào chỉ có `h` mà không có `a` hoặc `B`, thông tin AM/PM có thể chưa đủ để xác định một `LocalTime` duy nhất. Khi cần parse giờ 12 tiếng, hãy đưa chỉ báo AM/PM hoặc day period vào mẫu.

## 4. Parse giờ 24 tiếng và dùng day period để kiểm tra

Khác với `h`, `H` đã biểu diễn giờ trong ngày từ 0 đến 23. Khi parse mẫu có cả `H` và `B`, resolver không dùng day period để đổi giờ sang nửa ngày khác. Nó kiểm tra giờ đã parse có thuộc day period đó hay không, có xét phút nếu có.

Ví dụ formatter:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("HH:mm B", Locale.US)
        .withResolverStyle(ResolverStyle.STRICT);
```

Chuỗi `14:30 in the afternoon` nhất quán: giờ 14:30 thuộc day period buổi chiều trong locale tương ứng. Chuỗi `10:30 in the afternoon` mâu thuẫn: giờ 10:30 không thuộc day period được ghi.

```java
LocalTime valid = LocalTime.parse(
        "14:30 in the afternoon",
        formatter
);

// Lỗi resolve: 10:30 không khớp "in the afternoon".
LocalTime invalid = LocalTime.parse(
        "10:30 in the afternoon",
        formatter
);
```

Ở chế độ `STRICT`, trường hợp mâu thuẫn bị từ chối trong giai đoạn resolve. Chế độ `SMART` cũng từ chối xung đột day period với `HOUR_OF_DAY`. `LENIENT` có hành vi riêng: nó bỏ qua day period khi đã có giờ trong ngày mâu thuẫn, như trình bày ở phần tiếp theo.

Không dùng `H` và `B` nếu mục tiêu là để day period chọn nửa ngày cho giờ 12 tiếng. Trong trường hợp đó, dùng `h` kết hợp `B`.

## 5. DateTimeFormatter parse theo hai giai đoạn

Để hiểu ảnh hưởng của `ResolverStyle`, cần phân biệt parse và resolve.

```text
Văn bản đầu vào
      |
      v
Phase 1: Parse
- Đọc chữ số, dấu phân cách và day period text
- Ghi các field đã nhận diện
      |
      v
Map<Field, Value>
      |
      v
Phase 2: Resolve
- Kết hợp giờ 12 tiếng với day period
- Kiểm tra giờ 24 tiếng có khớp day period
- Xử lý giá trị theo ResolverStyle
      |
      v
LocalTime hoặc lỗi
```

**Phase 1 — Parse:** formatter đọc chuỗi theo pattern, locale và quy tắc văn bản. Ví dụ, nó nhận diện phần giờ, phút và tên day period.

**Phase 2 — Resolve:** các field đã parse được kết hợp và xác thực để tạo kiểu thời gian như `LocalTime`. `ResolverStyle` điều khiển giai đoạn này.

Do đó, `ResolverStyle.LENIENT` không có nghĩa mọi chuỗi tùy ý đều được chấp nhận. Chuỗi vẫn phải khớp pattern và văn bản day period phải được nhận diện theo locale. LENIENT điều chỉnh giai đoạn resolve, không bỏ qua lỗi cú pháp của phase 1.

### 5.1. STRICT

`STRICT` yêu cầu dữ liệu resolve nhất quán và nằm trong miền hợp lệ.

Với day period:

- `h:mm B` có thể kết hợp giờ 12 tiếng với day period để tạo giờ trong ngày.
- `H:mm B` được kiểm tra xem giờ đã có có thuộc day period không.
- Nếu `HOUR_OF_DAY` xung đột với day period, parse bị từ chối.
- Nếu chỉ có day period mà không có giờ/phút/giây/nano, resolver không tự chọn midpoint để tạo giờ.

STRICT phù hợp khi dữ liệu đầu vào phải phản ánh chính xác giờ mà người gửi định cung cấp.

### 5.2. SMART

`SMART` là resolver style mặc định của `DateTimeFormatter` nếu không cấu hình khác. Nó áp dụng quy tắc thông minh theo từng field.

Với day period, một điểm cần nhớ là `SMART` vẫn từ chối xung đột giữa `HOUR_OF_DAY` và day period. SMART không tự sửa giờ 10:30 thành 14:30 chỉ vì chuỗi ghi `in the afternoon`.

Nếu chỉ có day period mà không có giờ, phút, giây hoặc nano, SMART có thể chọn midpoint của khoảng day period để tạo giờ. Đây là quy tắc được định nghĩa cho trường hợp chỉ parse day period.

### 5.3. LENIENT

`LENIENT` cho phép resolver nới lỏng một số quy tắc. Với day period:

- Nếu đã có `HOUR_OF_DAY` và giờ đó mâu thuẫn với day period, day period bị bỏ qua và không phát sinh lỗi xung đột.
- Nếu chỉ có day period, resolver chọn midpoint của khoảng day period.
- Văn bản đầu vào vẫn phải được parse theo pattern và locale.

LENIENT hữu ích khi day period chỉ là gợi ý phụ trong dữ liệu đầu vào và ứng dụng quyết định ưu tiên giờ 24 tiếng. Với dữ liệu cần chính xác, không nên chọn LENIENT chỉ để làm cho chuỗi lỗi được chấp nhận.

### 5.4. Bảng so sánh hành vi

| Trường hợp parse | STRICT | SMART | LENIENT |
|---|---|---|---|
| `h:mm B` có giờ 12 tiếng và day period hợp lệ | Kết hợp thành giờ trong ngày | Kết hợp thành giờ trong ngày | Kết hợp thành giờ trong ngày |
| `H:mm B` có giờ khớp day period | Chấp nhận | Chấp nhận | Chấp nhận |
| `H:mm B` có giờ mâu thuẫn day period | Ném lỗi resolve | Ném lỗi resolve | Bỏ qua day period |
| Chỉ có `B`, không có trường giờ/phút/giây/nano | Không tự tạo midpoint | Chọn midpoint | Chọn midpoint |
| Văn bản day period không nhận diện được theo locale | Lỗi parse | Lỗi parse | Lỗi parse |

Điểm khác biệt quan trọng nhất khi có `HOUR_OF_DAY` là STRICT và SMART đều từ chối xung đột, trong khi LENIENT bỏ qua day period. Đừng suy luận hành vi của day period chỉ từ ví dụ SMART xử lý ngày tháng; từng field có quy tắc resolve riêng.

## 6. Chỉ parse day period mà không có giờ

Một trường hợp đặc biệt là đầu vào chỉ có tên day period, ví dụ `at night`. API có thể chọn midpoint của khoảng day period trong `SMART` và `LENIENT`.

Theo tài liệu API, ví dụ một day period kiểu `night1` có khoảng từ 21:00 đến 06:00 thì midpoint là 01:30. Khoảng thực tế và văn bản tương ứng phụ thuộc locale.

Ví dụ với locale tiếng Anh Mỹ:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter periodOnly = DateTimeFormatter
        .ofPattern("B", Locale.US)
        .withResolverStyle(ResolverStyle.SMART);

LocalTime representativeTime = LocalTime.parse("at night", periodOnly);
```

Với day period tương ứng kiểu `night1`, giờ đại diện có thể là 01:30. Đây là midpoint được chọn để đại diện cho khoảng thời gian, không phải thời điểm chính xác mà người dùng đã cung cấp.

Ở `STRICT`, chỉ có day period không đủ thông tin để tạo `LocalTime` vì không có `HOUR_OF_DAY` được resolve. Nếu nghiệp vụ cần một thời điểm chính xác, yêu cầu người dùng nhập giờ và phút thay vì tự dùng midpoint.

### 6.1. Vì sao midpoint không phải giờ thực tế?

Day period là một khoảng, không phải một instant. Ví dụ “buổi chiều” có thể kéo dài nhiều giờ. Chọn midpoint chỉ là quy tắc resolve để có thể tạo một `LocalTime` khi input chỉ có khoảng thời gian.

Không dùng kết quả midpoint để:

- Ghi nhận thời điểm giao dịch.
- Tính thời lượng hoặc deadline chính xác.
- Lên lịch gửi thông báo chính xác đến phút.
- Thay thế giờ do người dùng thực sự nhập.

Nếu chỉ biết day period, giữ nguyên thông tin đó như một trạng thái/khoảng thời gian ở mô hình nghiệp vụ thay vì giả vờ đã biết giờ cụ thể.

## 7. Trường hợp noon và midnight

Day period có thể bao gồm những loại đặc biệt như `noon` và `midnight`. API quy định loại `midnight` cho phép cả `00:00` ở đầu ngày và `24:00` ở cuối ngày nếu giờ resolve phù hợp.

`24:00` có ý nghĩa “kết thúc ngày”, không giống một giờ thông thường trong `LocalTime` vì `LocalTime` chỉ biểu diễn từ 00:00 đến trước 24:00. Khi parse theo SMART với ngữ cảnh ngày giờ, formatter có thể xử lý 24:00 như nửa đêm đầu ngày tiếp theo và cung cấp thông tin excess day. Với riêng `LocalTime`, kết quả cuối cùng là 00:00 vì kiểu này không giữ ngày.

Không tự viết logic kiểm tra chuỗi `midnight` bằng cách so sánh text. Hãy để formatter và locale resolver thực hiện quy tắc theo API.

## 8. Viết test cho ResolverStyle

Nên kiểm thử từng hợp đồng resolve riêng biệt. Ví dụ dùng JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class DayPeriodResolverTest {
    private static DateTimeFormatter formatter(
            String pattern,
            ResolverStyle style
    ) {
        return DateTimeFormatter.ofPattern(pattern, Locale.US)
                .withResolverStyle(style);
    }

    @Test
    void combinesTwelveHourClockWithAfternoonPeriod() {
        LocalTime parsed = LocalTime.parse(
                "2:30 in the afternoon",
                formatter("h:mm B", ResolverStyle.STRICT)
        );

        assertEquals(LocalTime.of(14, 30), parsed);
    }

    @Test
    void strictRejectsConflictWithTwentyFourHourClock() {
        DateTimeFormatter strict =
                formatter("HH:mm B", ResolverStyle.STRICT);

        assertThrows(
                DateTimeParseException.class,
                () -> LocalTime.parse("10:30 in the afternoon", strict)
        );
    }

    @Test
    void smartAlsoRejectsConflictWithTwentyFourHourClock() {
        DateTimeFormatter smart =
                formatter("HH:mm B", ResolverStyle.SMART);

        assertThrows(
                DateTimeParseException.class,
                () -> LocalTime.parse("10:30 in the afternoon", smart)
        );
    }

    @Test
    void lenientIgnoresConflictingDayPeriodWhenHourOfDayExists() {
        DateTimeFormatter lenient =
                formatter("HH:mm B", ResolverStyle.LENIENT);

        LocalTime parsed = LocalTime.parse(
                "10:30 in the afternoon",
                lenient
        );

        assertEquals(LocalTime.of(10, 30), parsed);
    }
}
```

Các test dùng locale tường minh để kết quả không phụ thuộc locale mặc định của máy. Câu chữ day period vẫn dựa trên locale data của JDK đang chạy; nếu ứng dụng hỗ trợ nhiều JDK hoặc nhiều locale provider, hãy kiểm thử với môi trường triển khai thực tế.

### 8.1. Kiểm thử midpoint khi chỉ có day period

Có thể bổ sung test riêng cho trường hợp chỉ parse day period:

Đặt method này bên trong class `DayPeriodResolverTest` ở phần trên:

```java
@Test
void smartUsesMidpointWhenOnlyDayPeriodIsParsed() {
    DateTimeFormatter formatter =
            DateTimeFormatter.ofPattern("B", Locale.US)
                    .withResolverStyle(ResolverStyle.SMART);

    LocalTime parsed = LocalTime.parse("at night", formatter);

    assertEquals(LocalTime.of(1, 30), parsed);
}
```

Assertion `01:30` phù hợp với dữ liệu locale trong đó `night1` là khoảng 21:00–06:00. Nếu locale data khác, midpoint cũng có thể khác. Với test đa môi trường, có thể kiểm tra chính sách resolve bằng locale data được cố định trong môi trường test hoặc kiểm tra kết quả theo dữ liệu locale đang dùng.

Không viết test yêu cầu mọi locale đều trả cùng một midpoint cho `B`.

### 8.2. Kiểm thử strict không tự suy ra midpoint

Nếu formatter chỉ chứa `B` và dùng STRICT, không có giờ để tạo `LocalTime`:

Đây là method test bổ sung trong cùng class `DayPeriodResolverTest`:

```java
@Test
void strictCannotCreateLocalTimeFromDayPeriodAlone() {
    DateTimeFormatter formatter =
            DateTimeFormatter.ofPattern("B", Locale.US)
                    .withResolverStyle(ResolverStyle.STRICT);

    assertThrows(
            DateTimeParseException.class,
            () -> LocalTime.parse("at night", formatter)
    );
}
```

Test này kiểm tra rằng ứng dụng không vô tình dùng midpoint khi chính sách yêu cầu giờ cụ thể. Nếu API chỉ cần giữ field đã parse mà chưa resolve, có thể dùng phương thức parse cấp thấp phù hợp, nhưng không nên nhầm kết quả chưa resolve với một `LocalTime` hoàn chỉnh.

## 9. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Xem `B` giống `a` | `B` biểu diễn day period linh hoạt, `a` chỉ AM/PM | Chọn pattern theo ý nghĩa dữ liệu |
| Parse `h:mm` mà không có AM/PM hoặc day period | Có thể không xác định được giờ trong ngày | Bổ sung `a` hoặc `B` |
| Dùng `HH:mm B` để day period tự sửa giờ | `H` đã là giờ trong ngày; `B` dùng để kiểm tra | Dùng `h:mm B` nếu cần suy ra nửa ngày |
| Nghĩ SMART luôn tự sửa xung đột | Với `HOUR_OF_DAY` và day period, SMART cũng ném lỗi khi mâu thuẫn | Chọn resolver theo hợp đồng |
| Nghĩ LENIENT bỏ qua mọi lỗi chuỗi | LENIENT chỉ nới lỏng phase resolve; phase parse vẫn phải khớp | Kiểm tra pattern và locale riêng |
| Dùng midpoint làm giờ thực tế | Midpoint chỉ đại diện cho khoảng day period | Yêu cầu giờ cụ thể nếu cần độ chính xác |
| Dùng locale mặc định của server | Kết quả có thể khác theo máy chạy | Truyền `Locale` tường minh |
| Hard-code câu chữ `in the afternoon` cho mọi locale | Tên day period phụ thuộc locale data | Dùng formatter và locale tương ứng |
| So sánh chuỗi đã format trên mọi JDK | Locale data có thể khác theo môi trường | Test parse/format theo locale và JDK mục tiêu |

## 10. Khi nào nên dùng day period?

Day period phù hợp khi hiển thị hoặc nhận giờ theo cách diễn đạt tự nhiên của người dùng:

- Biểu mẫu đặt lịch cho phép nhập “2:30 in the afternoon”.
- Giao diện hiển thị giờ phù hợp với ngôn ngữ của người dùng.
- Ứng dụng cần diễn giải “at night” thành một khoảng thời gian mang tính mô tả.
- Dữ liệu nhập có giờ 12 tiếng và cần day period để xác định AM/PM chi tiết hơn.

Không nên dùng day period làm định dạng trao đổi máy-máy nếu cần biểu diễn giờ chính xác, ổn định. Với dữ liệu hệ thống, `LocalTime` có thể được serialize theo định dạng ISO-8601 như `14:30`; nếu cần ngày và múi giờ, chọn kiểu phù hợp như `LocalDateTime`, `OffsetDateTime` hoặc `ZonedDateTime` theo semantics nghiệp vụ.

Day period không chứa ngày hoặc múi giờ. `14:30` trong một ngày cụ thể và múi giờ cụ thể có ý nghĩa khác với “in the afternoon” không có ngày, offset hoặc zone.

## 11. Checklist parse day period

Trước khi đưa formatter vào ứng dụng, hãy kiểm tra:

1. Runtime mục tiêu là Java 16 trở lên để hỗ trợ pattern `B`?
2. Đã chọn locale tường minh chưa?
3. Đầu vào dùng giờ 12 tiếng (`h`) hay giờ 24 tiếng (`H`)?
4. Day period có vai trò suy ra giờ hay chỉ xác thực giờ đã có?
5. ResolverStyle có phù hợp với độ nghiêm ngặt của dữ liệu không?
6. Đã test trường hợp `HOUR_OF_DAY` mâu thuẫn day period chưa?
7. Đã quyết định có chấp nhận midpoint khi chỉ có day period không?
8. Có phân biệt lỗi parse văn bản với lỗi resolve field không?
9. Test có chạy trên locale/JDK data gần với production không?
10. Dữ liệu trao đổi hệ thống có cần dùng định dạng giờ ổn định như ISO-8601 không?

## 12. Bài tập vận dụng

**Bài 1 — Format theo locale:** Dùng `DateTimeFormatter.ofPattern("h:mm B", locale)` để format một số giờ buổi sáng, buổi chiều và ban đêm. So sánh `Locale.US` với `vi-VN` và ghi nhận sự khác biệt.

**Bài 2 — Parse giờ 12 tiếng:** Parse `2:30 in the afternoon` bằng pattern `h:mm B`. Kiểm tra kết quả `LocalTime.of(14, 30)`.

**Bài 3 — Kiểm tra giờ 24 tiếng:** Dùng `HH:mm B` để parse một giờ phù hợp và một giờ mâu thuẫn day period. Thử cả STRICT, SMART và LENIENT.

**Bài 4 — Midpoint:** Parse chuỗi chỉ có day period bằng SMART và LENIENT. Tìm midpoint theo locale data. Thử STRICT và giải thích vì sao không tạo được giờ hoàn chỉnh.

**Bài 5 — API nhập lịch:** Thiết kế parser cho biểu mẫu đặt lịch. Quy định rõ trường hợp người dùng nhập giờ 12 tiếng, giờ 24 tiếng, chỉ day period, missing và null. Viết test cho từng nhánh.

---

## Tài liệu tham khảo

- [DateTimeFormatter — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/DateTimeFormatter.html): pattern letter B, parse hai giai đoạn và resolver style.
- [DateTimeFormatterBuilder — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html): `appendDayPeriodText(TextStyle)` và cách resolve day period.
- [ResolverStyle — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/ResolverStyle.html): định nghĩa STRICT, SMART và LENIENT.
- [DateTimeFormatterBuilder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html): xác nhận API day period tiếp tục có trong Java hiện đại.
- [DateTimeFormatter — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html): hành vi parse/resolve và cấu hình resolver style hiện hành.

---

**Ghi nhớ:** `B` biểu diễn day period theo locale. Với `h`, day period giúp suy ra giờ trong ngày; với `H`, day period xác thực giờ đã có. Khi hai thông tin mâu thuẫn, STRICT và SMART từ chối, còn LENIENT bỏ qua day period. Nếu chỉ có day period, SMART và LENIENT chọn midpoint; đó là giờ đại diện cho một khoảng, không phải thời điểm chính xác do người dùng cung cấp.
