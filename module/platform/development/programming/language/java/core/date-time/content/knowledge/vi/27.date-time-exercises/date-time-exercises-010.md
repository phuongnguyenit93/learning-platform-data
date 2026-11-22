# Tổng hợp lỗi thường gặp và tiêu chí chọn đúng API

## 1. Chọn API bắt đầu từ câu hỏi, không từ tên phương thức

Nhiều lỗi ngày giờ không phải do viết sai cú pháp. Mã vẫn biên dịch và trả về một ngày hợp lệ, nhưng đang trả lời một câu hỏi khác với yêu cầu.

Ví dụ:

- “Sau một ngày lịch” có thể khác “sau đúng 24 giờ”.
- “Cùng thời điểm” có thể khác “cùng ngày giờ và offset”.
- “Ngày 31 mỗi tháng, thiếu thì lùi” khác “lấy ngày đã lùi của kỳ trước rồi cộng tiếp”.
- “Ngày giờ 09:00” chưa nói 09:00 ở đâu.
- “Có hiệu lực đến 10:00” cần nói rõ đúng 10:00 còn hiệu lực hay không.

Trước khi chọn API, hãy phát biểu bốn điều: **dữ liệu biểu diễn gì, phép toán muốn làm gì, chính sách ranh giới là gì và phải giữ thông tin nào khi chuyển đổi**.

Bài này tổng hợp các tiêu chí chọn API và những phản ví dụ có thể chạy được. Các ngày trong ví dụ là dữ liệu cố định để kiểm thử, không phải ngày hiện tại.

## 2. Tiêu chí thứ nhất: kiểu dữ liệu có đúng ngữ nghĩa không?

| Câu hỏi hoặc dữ liệu | Kiểu nên xem xét | Lỗi cần tránh |
| --- | --- | --- |
| Ngày lịch, chẳng hạn ngày sinh | `LocalDate` | Tự gắn giờ/múi giờ chưa có |
| Giờ trong ngày, không có ngày | `LocalTime` | Mong phép cộng giữ thông tin ngày hôm sau |
| Bộ ngày giờ địa phương | `LocalDateTime` | Gọi nó là một thời điểm duy nhất khi thiếu vùng/offset |
| Thời điểm sự kiện đã xác định | `Instant` | Lưu bằng chuỗi địa phương mất ngữ cảnh |
| Ngày giờ cần giữ offset | `OffsetDateTime` | Chỉ giữ thời điểm rồi cho rằng offset gốc còn tồn tại |
| Ngày giờ gắn quy tắc vùng | `ZonedDateTime` hoặc mô hình có `ZoneId` rõ | Thay vùng bằng một độ lệch cố định cho mọi ngày |
| Một kỳ tháng | `YearMonth` | Dùng tháng riêng lẻ và bỏ mất năm |
| Một năm | `Year` | Tạo ngày giả 1/1 nếu nghiệp vụ không có ngày đó |
| Mẫu tháng-ngày lặp lại | `MonthDay` | Dùng nó thay ngày sinh đầy đủ khi cần tính tuổi |

Một kiểu có nhiều trường hơn chưa chắc tốt hơn. Dùng `LocalDateTime` cho mọi dữ liệu có thể vừa thêm thông tin không có nguồn, vừa vẫn thiếu thông tin thời điểm.

`Instant` xác định điểm trên trục thời gian, nhưng không lưu tên vùng nơi sự kiện được ghi nhận. `LocalDate` giữ ngày, nhưng không giữ múi giờ đã được dùng để suy ra ngày đó. Chọn và giữ đúng thông tin theo mục đích; xem [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) và [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).

## 3. Tiêu chí thứ hai: đặt thành phần hay cộng một lượng?

| Ý định | API điển hình |
| --- | --- |
| Đọc một thành phần | `getYear()`, `get(DAY_OF_MONTH)`, `getLong(field)` |
| Đặt trường thành giá trị | `withDayOfMonth(1)`, `with(field, value)` |
| Áp quy tắc điều chỉnh | `with(lastDayOfMonth())` |
| Cộng lượng theo một đơn vị | `plusDays(1)`, `plus(1, DAYS)` |
| Cộng lượng đóng gói | `plus(Period)`, `plus(Duration)` |
| Đo lượng giữa hai giá trị | `ChronoUnit.X.between(start, end)` |

`with(DAY_OF_MONTH, 1)` đưa về ngày 1 trong tháng. `plus(1, DAYS)` tiến một ngày. Không chọn chỉ vì cả hai đều nhận số 1.

`ChronoField` mô tả trường; `ChronoUnit` mô tả đơn vị. `DAY_OF_MONTH` không thay cho `DAYS`. Khi một API nhận giao diện tổng quát `Temporal`, nó vẫn không làm đối tượng có thêm thành phần: `LocalDate` không cộng được `HOURS`.

Chỉ dùng `get` khi hợp đồng cho phép giá trị `int`. Một số trường có miền lớn như `NANO_OF_DAY` phải đọc qua `getLong`. Đổi từ `get` sang `getLong` không làm trường không được hỗ trợ trở thành được hỗ trợ.

Với các kiểu chuẩn bất biến, luôn giữ kết quả trả về khi cần sử dụng thay đổi:

```java
// Minh họa bên trong một phương thức.
LocalDate date = LocalDate.of(2024, 1, 31);
date.plusDays(1);          // Bỏ kết quả; date vẫn là 31/1.
date = date.plusDays(1);   // date nay là 1/2.
```

Gán lại biến không phải sửa đối tượng gốc. Khi so các giá trị, dùng `equals` hoặc phép so theo ý nghĩa, không dùng `==`.

## 4. Tiêu chí thứ ba: quy tắc lịch hay thời lượng đã trôi qua?

`Period` mô tả lượng năm-tháng-ngày theo lịch. `Duration` mô tả lượng giây và nano giây. Trên một kiểu có múi giờ, sự khác biệt này có thể hiện rõ khi offset thay đổi.

Ví dụ tại Paris, từ 12:00 ngày 30/3/2024:

| Phép cộng | Giờ địa phương kết quả |
| --- | --- |
| `plus(Period.ofDays(1))` | 12:00 ngày 31/3 |
| `plus(Duration.ofHours(24))` | 13:00 ngày 31/3 |

Ngày lịch kế tiếp giữ mốc giờ địa phương trong ví dụ, nhưng thời gian thực đã trôi qua chỉ là 23 giờ. Đừng đổi yêu cầu “mỗi ngày lúc 12:00” thành “cứ 24 giờ một lần” mà không đánh giá hệ quả.

Tương tự:

- Một tháng không có số ngày cố định.
- Một năm không luôn có 365 ngày.
- Kết quả `ChronoUnit.MONTHS.between` là số tháng hoàn chỉnh theo quy tắc kiểu dữ liệu, không chắc là nghịch đảo của một lần cộng tháng có điều chỉnh.
- Khoảng ngày và khoảng thời điểm phải được đo bằng câu hỏi phù hợp.

Khi chuyển ngày giờ địa phương thành thời điểm, một giờ ở vùng chuyển offset có thể không tồn tại hoặc tồn tại hai lần. `ZonedDateTime` có quy tắc xử lý mặc định, nhưng nghiệp vụ có thể cần từ chối hoặc yêu cầu chọn offset. Không coi “gắn vùng thành công” là bằng chứng đầu vào ban đầu luôn có đúng một cách hiểu. Xem các trường hợp thiếu/lặp giờ ở [ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html).

## 5. Tiêu chí thứ tư: chính sách tại cuối tháng và ngày nhuận

### 5.1. Cộng tháng có thể làm mất số ngày ban đầu

Từ 31/1/2024:

```text
Cộng 1 tháng, rồi cộng 1 tháng:  29/3/2024
Cộng thẳng 2 tháng:              31/3/2024
```

Bước qua tháng 2 đã lùi ngày 31 về 29. Khi tiếp tục từ giá trị đã lùi, số ngày gốc không còn trong đối tượng.

Nếu yêu cầu là “hạn cuối mỗi tháng”, dùng kỳ `YearMonth` của từng tháng rồi `atEndOfMonth()`. Nếu yêu cầu là “ngày 30, thiếu thì lùi”, giữ số ngày yêu cầu 30 riêng rồi áp vào từng tháng. Hai chính sách không tự đồng nghĩa.

Cũng không dùng cộng rồi trừ tháng như một phép hoàn tác bảo đảm khôi phục ngày gốc. Thông tin đã bị lùi có thể không tự quay lại.

### 5.2. Ngày nhuận không chỉ là chia hết cho 4

Các ca quan trọng:

- 1900 không nhuận.
- 2000 nhuận.
- 2100 không nhuận.
- 2024 nhuận.

Dùng API lịch để xác định nhuận và tạo ngày hợp lệ, đồng thời kiểm tra các ca thế kỷ để hiểu đúng quy tắc.

### 5.3. Tạo ngày hợp lệ khác với từ chối đầu vào sai

`MonthDay.of(2, 29).atYear(2023)` cho 28/2/2023. Đó là hành vi điều chỉnh của API.

Nếu yêu cầu là xác thực “29/2/2023 có tồn tại không?”, không dùng kết quả đó để kết luận đầu vào hợp lệ. Hãy kiểm tra `Year.isValidMonthDay` hoặc tạo ngày qua đường nghiêm ngặt tương ứng.

Tuổi tròn và ngày kỷ niệm 29/2 còn cần chính sách: năm thường chọn 28/2, 1/3 hay không có lần xuất hiện? API không tự biết quy tắc của ứng dụng. Chỉ lấy `Period.getYears()` rồi gọi đó là tuổi chưa chắc đáp ứng mọi chính sách đã chọn.

## 6. Tiêu chí thứ năm: “bằng nhau” cần giữ điều gì?

Xét hai giá trị:

```text
2024-01-15T09:00+07:00
2024-01-15T02:00Z
```

Chúng là cùng thời điểm, nhưng khác bộ ngày giờ và offset.

| Yêu cầu | Phép so phù hợp |
| --- | --- |
| Cùng ngày lịch | `LocalDate.equals` |
| Cùng bộ ngày giờ địa phương | `LocalDateTime.equals` |
| Cùng thời điểm | So `Instant`, hoặc `OffsetDateTime.isEqual` |
| Cùng bộ ngày giờ và offset | `OffsetDateTime.equals` |
| Cần giữ tên vùng | Kiểm tra giá trị và `ZoneId` theo hợp đồng |

Không so chuỗi đã định dạng để thay tất cả các phép so. Mẫu hiển thị có thể bỏ giây, phần lẻ, offset hoặc vùng. Hai giá trị khác nhau có thể có cùng nhãn màn hình.

Khi sắp xếp, chọn cùng tiêu chí với yêu cầu: nếu cần thứ tự sự kiện toàn cục, so thời điểm; nếu cần sắp các ngày lịch, so `LocalDate`. Đừng để thứ tự từ điển của chuỗi tự quyết định.

## 7. Tiêu chí thứ sáu: nguồn “bây giờ” và ngày nghiệp vụ

`LocalDate.now()` dùng múi giờ mặc định JVM. Máy chủ UTC và người dùng ở Việt Nam có thể ở hai ngày lịch khác nhau tại cùng thời điểm.

Nếu yêu cầu là hôm nay theo vùng nghiệp vụ:

1. Xác định nguồn thời điểm bằng `Clock`.
2. Chọn `ZoneId` theo quy tắc nghiệp vụ.
3. Suy ra ngày bằng `LocalDate.ofInstant(reference, zone)` hoặc một clock đã được gắn đúng vùng.

Tại `2024-01-01T17:00Z`, ngày UTC vẫn là 1/1, nhưng ngày tại Việt Nam là 2/1 trong ví dụ.

Dùng một thời điểm tham chiếu cho một lần xử lý để tránh nhiều lời gọi đi qua nửa đêm. Trong kiểm thử, dùng `Clock.fixed`; không chờ bằng sleep và không lấy ngày máy chạy thử làm kết quả mong đợi.

Đổi vùng của clock không dịch chuyển thời điểm gốc. Cộng 7 giờ vào thời điểm không phải cách biểu diễn đúng việc nhìn cùng thời điểm trong một vùng khác. Xem cách thay nguồn thời gian ở [Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html).

## 8. Tiêu chí thứ bảy: định dạng, xác thực và trao đổi

Một luồng dữ liệu nên có ranh giới rõ:

```text
Dữ liệu ngoài
   ↓ parse theo hợp đồng
Kiểu ngày giờ trong Java
   ↓ xác thực và tính toán
Kết quả có kiểu
   ↓ format theo người dùng/giao thức
Chuỗi đầu ra
```

Các lỗi thường gặp ở ranh giới:

| Lỗi | Cách chọn đúng |
| --- | --- |
| Phân tích ngày mà để mặc định tự điều chỉnh | Chọn `ResolverStyle.STRICT` nếu yêu cầu từ chối ngày sai |
| Nhầm `MM` với `mm` | `MM` là tháng; `mm` là phút |
| Nhầm `uuuu`, `yyyy`, `YYYY` | Phân biệt năm trên trục, năm trong kỷ nguyên và năm theo tuần |
| Parse giờ địa phương thành `Instant` nhưng thiếu offset | Yêu cầu offset hoặc quy tắc vùng rõ |
| Dùng locale/múi giờ mặc định không được công bố | Truyền rõ theo hợp đồng |
| Định dạng rồi tách chuỗi để tính | Giữ kiểu và dùng API trường/phép tính |
| Bắt lỗi rồi thay bằng ngày hiện tại | Báo lỗi hoặc xử lý thiếu theo chính sách |

`DateTimeFormatter` là bất biến và an toàn luồng theo hợp đồng; có thể cấu hình rõ locale, vùng và chế độ phân tích. Chuyển sang API hiện đại không có nghĩa chỉ đổi tên lớp mà vẫn giữ cách dùng chuỗi mơ hồ. Xem [DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html).

## 9. Tiêu chí thứ tám: đơn vị, độ chính xác và kho lưu trữ

Một số epoch chỉ có nghĩa khi biết đơn vị: giây và mili giây không thể dùng lẫn. `Instant` tách giây epoch và nano giây; đi vòng qua `toEpochMilli` sẽ mất phần nhỏ hơn mili giây.

Ví dụ:

```text
Ban đầu:  2024-01-15T02:00:00.123456789Z
Qua milli:2024-01-15T02:00:00.123Z
```

Với JDBC hoặc hệ thống ngoài, phải xác định:

- Cột/dữ liệu mang thời điểm hay bộ ngày giờ địa phương.
- Múi giờ được dùng ở bước nào.
- Mức chính xác và cách làm tròn/cắt.
- Giá trị thiếu được biểu diễn thế nào.
- Driver/bộ ánh xạ hỗ trợ kiểu nào.

`Timestamp.toInstant` và `Timestamp.toLocalDateTime` có mục tiêu khác nhau; chọn theo ngữ nghĩa dữ liệu và kiểm tra hợp đồng JDBC. Một phương thức chuyển đổi không thể tự sửa thông tin múi giờ đã bị diễn giải sai ở bước đọc.

Kiểm tra đi-về phải so theo điều cần giữ. Nếu kho chỉ giữ micro giây và chính sách đã cho phép cắt, so với giá trị được chuẩn hóa đúng quy tắc. Không dùng ngưỡng sai số rộng để che lỗi.

## 10. Tiêu chí thứ chín: cận thời gian được bao gồm hay loại trừ?

Với khoảng hiệu lực nửa mở:

```text
[fromInclusive, untilExclusive)
```

Điều kiện là:

```text
from <= reference AND reference < until
```

Đúng cận đầu có hiệu lực; đúng cận cuối không còn hiệu lực. Hai khoảng nối tiếp có thể dùng chung ranh giới mà không đếm trùng.

Nếu giao diện chọn “đến hết ngày 31/5”, cận thời điểm loại trừ nên là đầu ngày 1/6 theo vùng nghiệp vụ. Không đoán thời điểm cuối ngày bằng 23:59:59 hoặc trừ một đơn vị nhỏ tùy ý.

Quy tắc cận phải thống nhất giữa Java, truy vấn kho và giao diện. Tên biến `untilExclusive` có ích hơn một biến `end` không nói rõ ý nghĩa.

## 11. Chương trình Java 17+ kiểm chứng những lựa chọn dễ sai

Lưu mã sau thành `ChooseDateTimeApi.java`. Chương trình độc lập, không cần thư viện ngoài và không đọc đồng hồ thực.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.MonthDay;
import java.time.OffsetDateTime;
import java.time.Period;
import java.time.Year;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.UnsupportedTemporalTypeException;
import java.util.Locale;
import java.util.Objects;

public class ChooseDateTimeApi {
    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Class<? extends RuntimeException> type,
                                Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw new AssertionError("Unexpected exception", ex);
            }
            checks++;
            return;
        }
        throw new AssertionError("Expected " + type.getSimpleName());
    }

    private static boolean active(Instant value, Instant from, Instant until) {
        if (!from.isBefore(until)) {
            throw new IllegalArgumentException("Invalid interval");
        }
        return !value.isBefore(from) && value.isBefore(until);
    }

    public static void main(String[] args) {
        DateTimeFormatter strict = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        eq(LocalDate.parse("2024-02-29", strict), LocalDate.of(2024, 2, 29));
        rejects(DateTimeParseException.class,
                () -> LocalDate.parse("2023-02-29", strict));
        rejects(DateTimeParseException.class,
                () -> Instant.parse("2024-01-15T09:00:00"));

        LocalDate date = LocalDate.of(2024, 1, 31);
        date.plusDays(1); // Discarding the returned value changes nothing.
        eq(date, LocalDate.of(2024, 1, 31));
        eq(date.with(ChronoField.DAY_OF_MONTH, 1), LocalDate.of(2024, 1, 1));
        eq(date.plus(1, ChronoUnit.DAYS), LocalDate.of(2024, 2, 1));
        eq(date.plusMonths(1), LocalDate.of(2024, 2, 29));
        eq(date.plusMonths(1).plusMonths(1), LocalDate.of(2024, 3, 29));
        eq(date.plusMonths(2), LocalDate.of(2024, 3, 31));
        eq(YearMonth.from(date).plusMonths(2).atEndOfMonth(),
                LocalDate.of(2024, 3, 31));
        eq(Year.isLeap(1900), false);
        eq(Year.isLeap(2000), true);
        MonthDay leapDay = MonthDay.of(2, 29);
        eq(leapDay.atYear(2023), LocalDate.of(2023, 2, 28));
        eq(Year.of(2023).isValidMonthDay(leapDay), false);

        ZoneId paris = ZoneId.of("Europe/Paris");
        ZonedDateTime noon = ZonedDateTime.of(2024, 3, 30, 12, 0, 0, 0, paris);
        ZonedDateTime calendarDay = noon.plus(Period.ofDays(1));
        ZonedDateTime elapsedDay = noon.plus(Duration.ofHours(24));
        eq(calendarDay.getHour(), 12);
        eq(elapsedDay.getHour(), 13);
        eq(Duration.between(noon.toInstant(), calendarDay.toInstant()).toHours(), 23L);

        Clock fixed = Clock.fixed(Instant.parse("2024-01-01T17:00:00Z"),
                ZoneOffset.UTC);
        eq(LocalDate.now(fixed), LocalDate.of(2024, 1, 1));
        eq(LocalDate.ofInstant(fixed.instant(), ZoneId.of("Asia/Ho_Chi_Minh")),
                LocalDate.of(2024, 1, 2));

        OffsetDateTime localOffset = OffsetDateTime.parse("2024-01-15T09:00+07:00");
        OffsetDateTime utcOffset = OffsetDateTime.parse("2024-01-15T02:00Z");
        eq(localOffset.isEqual(utcOffset), true);
        eq(localOffset.equals(utcOffset), false);
        LocalDateTime ambiguous = LocalDateTime.parse("2024-10-27T02:30");
        eq(paris.getRules().getValidOffsets(ambiguous).size(), 2);

        Instant precise = Instant.parse("2024-01-15T02:00:00.123456789Z");
        eq(Instant.parse(precise.toString()), precise);
        eq(Instant.ofEpochMilli(precise.toEpochMilli()).equals(precise), false);
        Instant from = precise;
        Instant until = from.plusSeconds(60);
        eq(active(from, from, until), true);
        eq(active(until, from, until), false);
        rejects(UnsupportedTemporalTypeException.class,
                () -> date.plus(1, ChronoUnit.HOURS));

        System.out.println("calendarDayHour=" + calendarDay.getHour());
        System.out.println("elapsed24HoursHour=" + elapsedDay.getHour());
        System.out.println("calendarDayElapsedHours="
                + Duration.between(noon.toInstant(), calendarDay.toInstant()).toHours());
        System.out.println("sameInstant=" + localOffset.isEqual(utcOffset));
        System.out.println("sameOffsetDateTime=" + localOffset.equals(utcOffset));
        System.out.println("businessDate=" + LocalDate.ofInstant(
                fixed.instant(), ZoneId.of("Asia/Ho_Chi_Minh")));
        System.out.println("activeAtEnd=" + active(until, from, until));
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ChooseDateTimeApi.java
java ChooseDateTimeApi
```

Stdout:

```text
calendarDayHour=12
elapsed24HoursHour=13
calendarDayElapsedHours=23
sameInstant=true
sameOffsetDateTime=false
businessDate=2024-01-02
activeAtEnd=false
PASS checks=27
```

Hàm `eq` chủ động ném `AssertionError` khi sai nên không cần cờ `-ea`. Hàm `rejects` xác nhận đúng loại ngoại lệ, không coi mọi lỗi bất kỳ là đạt.

Các dòng đầu làm rõ một ngày lịch khác đúng 24 giờ. Hai dòng so offset cho thấy tiêu chí bằng nhau cần được chọn. Ngày nghiệp vụ lấy từ một thời điểm cố định. Dòng `activeAtEnd=false` xác nhận cận cuối loại trừ.

Các ca không in riêng còn kiểm tra parse nghiêm ngặt, bỏ mất kết quả của đối tượng bất biến, đặt trường khác cộng lượng, trôi ngày khi cộng tháng, năm thế kỷ, giờ địa phương lặp, giảm độ chính xác và đơn vị không hỗ trợ.

Có thể chạy hai cấu hình để phát hiện phụ thuộc ngầm:

```shell
java "-Duser.timezone=UTC" ChooseDateTimeApi
java "-Duser.timezone=America/New_York" ChooseDateTimeApi
```

Cả hai phải cho cùng stdout trên. Ví dụ dùng những ngày cố định theo quy tắc vùng trong JDK; không chứng minh cho một driver/cơ sở dữ liệu chưa được chạy thử.

## 12. Quy trình chọn API cho một yêu cầu mới

Thực hiện theo thứ tự sau:

1. **Viết lại yêu cầu bằng dữ liệu cụ thể.** Ví dụ “hết hạn vào đầu ngày sau ngày 31/5 ở vùng cơ sở”, thay vì chỉ viết “hết hạn cuối tháng”.
2. **Chọn kiểu giữ đúng thông tin.** Tách ngày lịch, thời điểm, giờ địa phương và mẫu lặp.
3. **Chọn phép toán.** Đặt trường, điều chỉnh theo quy tắc, cộng lịch, cộng thời lượng hay đo khoảng.
4. **Công bố chính sách biên.** Ngày nhuận, tháng ngắn, giờ thiếu/lặp, cận bao gồm/loại trừ.
5. **Xác định môi trường.** Clock, vùng và locale phải có nguồn rõ khi chúng ảnh hưởng kết quả.
6. **Định nghĩa thông tin cần giữ khi chuyển đổi.** Thời điểm, offset, vùng và độ chính xác là các tiêu chí khác nhau.
7. **Viết ca phân biệt lựa chọn đúng với lựa chọn có vẻ hợp lý nhưng sai.** Chọn cuối tháng, năm thế kỷ, nửa đêm hoặc chuyển offset.
8. **Chỉ khẳng định trong phạm vi đã kiểm chứng.** Kiểm thử trong bộ nhớ không thay kiểm tra đọc/ghi kho thực tế.

Không bắt buộc một hàm đơn giản phải tự xử lý mọi hệ lịch và mọi vùng. Một hợp đồng hẹp nhưng rõ có thể tốt hơn một hàm tổng quát nhận mọi kiểu rồi đoán ý nghĩa.

## 13. Bài tập tự kiểm tra

1. **“Nhắc hằng ngày lúc 09:00 ở Paris” hay “nhắc sau mỗi 24 giờ”?** Hãy chọn hai mô hình riêng và dự đoán khác biệt ở ngày chuyển offset.

2. **“Hạn cuối mỗi tháng từ tháng 1/2024”.** Kết quả ba kỳ đầu phải là 31/1, 29/2, 31/3. Giải thích vì sao cộng tháng nối tiếp từ ngày đã lùi có thể không đáp ứng.

3. **“Hai chuỗi giờ có offset khác nhau nhưng cùng thời điểm”.** Nêu khi nào dùng `isEqual`, khi nào cần `equals`; không chọn chỉ vì một phép so trả `true`.

4. **“Người dùng nhập 29/2/2023 và hệ thống phải từ chối”.** Chọn đường parse/tạo nghiêm ngặt. Không lấy kết quả tự lùi 28/2 làm bằng chứng dữ liệu đúng.

5. **“Kho chỉ lưu mili giây nhưng đầu vào có nano giây”.** Xác định có chấp nhận giảm độ chính xác không, quy tắc là gì và kiểm tra đi-về so với giá trị nào.

6. **“Sự kiện đúng 10:00 ở ranh giới hai khoảng”.** Với `[09:00,10:00)` và `[10:00,11:00)`, sự kiện thuộc khoảng thứ hai.

Một lựa chọn API đúng phải khớp ý nghĩa dữ liệu và chính sách đã nêu. Các ca biên giúp chứng minh sự phù hợp ấy, thay vì chỉ chứng minh phương thức có thể chạy.
