# Thay đổi bất biến bằng with...(), plus...() và minus...() trong java.time

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao các đối tượng ngày giờ hiện đại của Java là **bất biến (immutable)** và các lời gọi `with...()`, `plus...()`, `minus...()` không sửa đối tượng ban đầu.
- Phân biệt **đặt/thay một thành phần ngày giờ** với **dịch chuyển một khoảng thời gian**, từ đó chọn phương thức đúng với yêu cầu nghiệp vụ.
- Sử dụng các overload như `with(TemporalField, long)`, `with(TemporalAdjuster)`, `plus(long, TemporalUnit)` và `minus(long, TemporalUnit)`.
- Hiểu chính xác chuyện ngày cuối tháng, năm nhuận, giới hạn trường, chuỗi thao tác, múi giờ và daylight saving time (DST).
- Tránh mất kết quả do quên nhận giá trị trả về, dùng sai lớp/đơn vị, hoặc tưởng rằng cộng một ngày lịch luôn bằng 24 giờ thực tế.

Bối cảnh là nhóm API `java.time` trong Java 17 trở lên. Bài dùng các ví dụ có ngày xác định để kết quả chạy có thể kiểm chứng.

## 2. Bất biến có nghĩa gì?

Các lớp giá trị phổ biến như `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `ZonedDateTime`, `OffsetDateTime`, `Duration` và `Period` được thiết kế bất biến: một giá trị ngày giờ đã tạo không bị sửa tại chỗ. Phương thức “thay đổi” **trả về giá trị kết quả** để bạn dùng tiếp.

```java
LocalDate original = LocalDate.of(2024, 1, 31);
original.plusDays(1);                    // kết quả bị bỏ đi
System.out.println(original);            // 2024-01-31

LocalDate nextDay = original.plusDays(1);
System.out.println(nextDay);             // 2024-02-01
System.out.println(original);            // 2024-01-31
```

Đây là **đoạn mã minh họa** trong một phương thức, cần `import java.time.LocalDate;`. Lời gọi `original.plusDays(1)` không phải lệnh gán; nếu bỏ kết quả trả về thì biến `original` vẫn tham chiếu tới giá trị cũ.

Có ba kiểu sử dụng:

```java
LocalDate revised = original.plusDays(7); // giữ cả giá trị cũ và mới
original = original.plusDays(7);           // gán biến sang giá trị mới
LocalDate result = original.withDayOfMonth(1).plusMonths(1).minusDays(2);
```

- **Bất biến của đối tượng** khác với **khả năng gán lại của biến**: câu `original = ...` đổi giá trị được tham chiếu bởi biến, không biến đổi đối tượng đã tạo.
- Phương thức có thể trả về **cùng instance** nếu kết quả không thay đổi; hợp đồng cần dựa trên **giá trị**, không dựa vào giả định “mỗi lần luôn tạo object mới”.
- Hãy so sánh nội dung bằng `equals()` hoặc cách so sánh thời gian thích hợp, tránh dùng `==` để xét hai ngày có cùng giá trị.
- Immutable value an toàn khi chia sẻ giữa luồng với mục đích đọc; nhiều luồng cùng gán/cập nhật một biến tham chiếu vẫn cần cơ chế phối hợp nếu muốn phép cập nhật nguyên tử.

## 3. Phân biệt ba họ phương thức

| Họ API | Ý nghĩa cơ bản | Ví dụ | Kết quả từ `2024-01-31` |
| --- | --- | --- | --- |
| `with...()` | **Đặt/thay** một trường hoặc áp dụng quy tắc điều chỉnh | `withDayOfMonth(1)` | `2024-01-01` |
| `plus...()` | **Cộng** một lượng hoặc một đơn vị | `plusDays(1)` | `2024-02-01` |
| `minus...()` | **Trừ** một lượng hoặc một đơn vị | `minusDays(1)` | `2024-01-30` |

Ví dụ `withMonth(6)` nghĩa là chọn **tháng 6**, còn `plusMonths(6)` nghĩa là **tiến thêm 6 tháng**. Tương tự, `withHour(9)` đặt giờ thành 09; `plusHours(9)` cộng 9 giờ. Các phương thức này không luôn có mặt trên mọi lớp vì một `LocalDate` không có trường giờ và một `LocalTime` không có trường năm.

Nên diễn đạt yêu cầu trước khi chọn API:

- “Đổi hạn thanh toán về **ngày 1** của tháng hiện tại” → đặt trường với `withDayOfMonth(1)`.
- “Gia hạn thêm **một tháng lịch**” → cộng với `plusMonths(1)`.
- “Lùi ngày hẹn **ba ngày**” → trừ bằng `minusDays(3)`.
- “Chọn **thứ Hai kế tiếp**” → dùng quy tắc `TemporalAdjusters.next(DayOfWeek.MONDAY)`.

## 4. Họ with...(): thay trường hay áp dụng quy tắc

### 4.1. Các phương thức có tên trường

```java
LocalDate date = LocalDate.of(2024, 8, 23);
LocalDate firstDay = date.withDayOfMonth(1); // 2024-08-01
LocalDate otherYear = date.withYear(2025);   // 2025-08-23

LocalDateTime time = LocalDateTime.of(2024, 8, 23, 9, 45);
LocalDateTime revised = time.withHour(14).withMinute(0);
// 2024-08-23T14:00
```

Đoạn mã cần `import java.time.LocalDate;` và `import java.time.LocalDateTime;` và được đặt trong phương thức. `withYear(2025)` là chọn năm 2025; `withDayOfMonth(1)` là chọn ngày số 1. Không cộng thêm vào giá trị hiện tại.

Các thao tác thường gặp:

- `LocalDate.withYear(...)`, `withMonth(...)`, `withDayOfMonth(...)`, `withDayOfYear(...)`.
- `LocalTime.withHour(...)`, `withMinute(...)`, `withSecond(...)`, `withNano(...)`.
- `LocalDateTime` kết hợp cả trường ngày và giờ.
- `ZonedDateTime`, `OffsetDateTime` có thêm các thao tác liên quan đến zone/offset, nhưng cần nắm rõ quy tắc xử lý giá trị ngày giờ và instant.

**Chú ý:** Không phải mọi giá trị đầu vào đều hợp lệ. Ví dụ `LocalDate.of(2024, 2, 29).withDayOfMonth(30)` ném `DateTimeException`. Tuy nhiên một số cách thay trường khác được định nghĩa để **điều chỉnh về ngày hợp lệ cuối cùng của tháng**: `LocalDate.of(2024, 1, 31).withMonth(2)` cho `2024-02-29`. Không suy diễn rằng mọi `with...()` đều có cùng chính sách khi ngày đích không hợp lệ; xem quy tắc của phương thức cụ thể.

### 4.2. Dạng tổng quát with(field, value)

Các lớp triển khai `Temporal` còn có thể hỗ trợ `with(TemporalField field, long newValue)`. Ví dụ dùng `ChronoField`:

```java
import java.time.LocalDate;
import java.time.temporal.ChronoField;

public class WithFieldDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 8, 23);
        LocalDate edited = date.with(ChronoField.DAY_OF_MONTH, 5);
        System.out.println(edited); // 2024-08-05
    }
}
```

Lưu thành `WithFieldDemo.java`, biên dịch bằng `javac WithFieldDemo.java` rồi chạy `java WithFieldDemo`. Kết quả hiển thị `2024-08-05`. Dạng này hữu ích khi field được chọn động, nhưng thiếu tính dễ đọc so với `withDayOfMonth(5)` trong mã nghiệp vụ đơn giản.

**Không phải mọi field đều được hỗ trợ bởi mọi đối tượng.** Ví dụ `LocalDate` không hỗ trợ `ChronoField.HOUR_OF_DAY`. Có thể kiểm tra trước bằng `date.isSupported(ChronoField.HOUR_OF_DAY)` (trả `false`); nếu vẫn gọi thay trường không được hỗ trợ sẽ gặp `UnsupportedTemporalTypeException`.

### 4.3. with(adjuster): điều chỉnh theo quy tắc

Thay vì đặt số ngày cụ thể, đôi khi cần áp dụng quy tắc như ngày đầu tháng, ngày cuối tháng, thứ Hai tiếp theo:

```java
LocalDate day = LocalDate.of(2026, 10, 24); // Thứ Bảy
LocalDate first = day.with(TemporalAdjusters.firstDayOfMonth());
LocalDate last = day.with(TemporalAdjusters.lastDayOfMonth());
LocalDate nextMonday = day.with(TemporalAdjusters.next(DayOfWeek.MONDAY));
```

Đây là đoạn minh họa trong phương thức, cần `import java.time.LocalDate;`, `import java.time.DayOfWeek;` và `import java.time.temporal.TemporalAdjusters;`. Kết quả lần lượt là `2026-10-01`, `2026-10-31` và `2026-10-26`.

So sánh hai quy tắc rất dễ nhầm:

- `TemporalAdjusters.next(MONDAY)` chọn **thứ Hai sau ngày đầu vào**, ngay cả khi đầu vào đã là thứ Hai.
- `TemporalAdjusters.nextOrSame(MONDAY)` chọn thứ Hai **trùng ngày hoặc về sau**; nếu ngày đầu vào đã là thứ Hai thì giữ ngày đó.

`TemporalAdjuster` còn cho phép đóng gói quy tắc ngày giờ riêng theo nghiệp vụ. Một adjuster tự viết phải xử lý những `Temporal` mà nó nhận một cách phù hợp; khi có quy tắc phức tạp như “ngày làm việc tiếp theo”, cần xét cả lịch nghỉ lễ chứ không chỉ thứ Bảy và Chủ nhật.

## 5. Họ plus...(): cộng một lượng theo đơn vị

Các phương thức cụ thể diễn đạt rõ mục đích:

```java
LocalDate date = LocalDate.of(2024, 1, 31);
LocalDate tomorrow = date.plusDays(1);       // 2024-02-01
LocalDate nextWeek = date.plusWeeks(1);      // 2024-02-07
LocalDate nextMonth = date.plusMonths(1);    // 2024-02-29
LocalDate nextYear = date.plusYears(1);      // 2025-01-31

LocalDateTime start = LocalDateTime.of(2024, 6, 10, 9, 30);
LocalDateTime later = start.plusHours(2).plusMinutes(15);
// 2024-06-10T11:45
```

Đoạn minh họa trên cần `import java.time.LocalDate;` và `import java.time.LocalDateTime;`. Phép cộng xử lý qua ranh giới ngày, tháng, năm theo quy tắc của lớp đối tượng. Ví dụ `2024-01-31 + 1 month` trở thành `2024-02-29` (năm nhuận), chứ không ném lỗi.

Dạng tổng quát `plus(long amountToAdd, TemporalUnit unit)` nhận các đơn vị như `ChronoUnit.DAYS`, `MONTHS`, `HOURS`, `MINUTES`, `SECONDS`, `NANOS` **nếu đối tượng hỗ trợ**.

```java
LocalDate result = LocalDate.of(2024, 1, 31)
        .plus(2, ChronoUnit.MONTHS); // 2024-03-31
```

Đây là đoạn minh họa có `import java.time.LocalDate;` và `import java.time.temporal.ChronoUnit;`. Một `LocalDate` không thể `plusHours(2)` vì không có giờ; với dạng tổng quát `plus(2, ChronoUnit.HOURS)` sẽ ném ngoại lệ do đơn vị không được hỗ trợ.

Họ `plus` cũng có dạng `plus(TemporalAmount amount)`. Ví dụ:

```java
LocalDate deadline = LocalDate.of(2024, 1, 31);
LocalDate afterPeriod = deadline.plus(Period.ofMonths(1)); // 2024-02-29

Instant instant = Instant.parse("2024-01-01T00:00:00Z");
Instant laterInstant = instant.plus(Duration.ofMinutes(90));
// 2024-01-01T01:30:00Z
```

Đây là đoạn minh họa có `import java.time.LocalDate;`, `import java.time.Period;`, `import java.time.Instant;` và `import java.time.Duration;`. `Period` phù hợp đại lượng lịch (năm, tháng, ngày), còn `Duration` phù hợp lượng thời gian dựa trên giây/nano giây. Không dùng `Instant.plus(1, ChronoUnit.MONTHS)`: một instant thuần túy không có ngữ cảnh lịch/múi giờ để biết “một tháng sau” là bao nhiêu giây.

## 6. Họ minus...(): trừ một lượng theo đơn vị

`minus...()` đối xứng với `plus...()` trong phần lớn trường hợp sử dụng:

```java
LocalDate date = LocalDate.of(2024, 3, 1);
LocalDate previousDay = date.minusDays(1);     // 2024-02-29
LocalDate previousMonth = date.minusMonths(1); // 2024-02-01
LocalDate previousYear = date.minusYears(1);   // 2023-03-01

LocalTime clock = LocalTime.of(0, 15);
LocalTime earlier = clock.minusMinutes(30);    // 23:45
```

Đây là đoạn minh họa cần `import java.time.LocalDate;` và `import java.time.LocalTime;`. `LocalTime` chỉ biểu diễn thời gian trong ngày; khi trừ qua nửa đêm, kết quả quay vòng trong 24 giờ **không giữ thông tin ngày trước đó**. Muốn giữ ngày, sử dụng `LocalDateTime` hoặc kiểu phù hợp với múi giờ.

Dạng tổng quát:

```java
LocalDate date = LocalDate.of(2024, 3, 1);
LocalDate previous = date.minus(2, ChronoUnit.WEEKS);
LocalDate withPeriod = date.minus(Period.ofMonths(1));
```

Đoạn minh họa cần `import java.time.LocalDate;`, `import java.time.Period;` và `import java.time.temporal.ChronoUnit;`.

Cộng một lượng âm thường giống trừ lượng dương và ngược lại, ví dụ `date.plusDays(-3)` tương đương về kết quả với `date.minusDays(3)` trong phạm vi hợp lệ. Tuy nhiên cẩn trọng với `Long.MIN_VALUE` và ranh giới ngày có thể biểu diễn: không tự triển khai `minusDays(n)` bằng `plusDays(-n)` với mọi `long` vì `-Long.MIN_VALUE` tràn số. Hãy gọi API `minus...()` trực tiếp theo ý nghĩa cần diễn đạt.

## 7. Tính bất biến khi chain: thứ tự rất quan trọng

Một chuỗi như:

```java
LocalDate result = start
        .withDayOfMonth(1)
        .plusMonths(1)
        .minusDays(2);
```

được xử lý **từ trái sang phải**: giá trị được trả về bởi mỗi bước là đầu vào cho bước tiếp theo. Bản thân `start` vẫn giữ nguyên. Có thể tách thành nhiều biến để debug và đặt tên ngữ nghĩa:

```java
LocalDate firstDayThisMonth = start.withDayOfMonth(1);
LocalDate firstDayNextMonth = firstDayThisMonth.plusMonths(1);
LocalDate dueDate = firstDayNextMonth.minusDays(2);
```

Đây là hai đoạn minh họa trong một phương thức nơi `start` là `LocalDate` hợp lệ, cần `import java.time.LocalDate;`. Cách đặt tên từng bước rõ hơn khi yêu cầu nghiệp vụ phức tạp.

**Các phép tính theo tháng không luôn có tính kết hợp theo cách trực giác**, do cơ chế điều chỉnh ngày cuối tháng. Ví dụ từ `2024-01-31`:

```java
LocalDate start = LocalDate.of(2024, 1, 31);

System.out.println(start.plusMonths(1));               // 2024-02-29
System.out.println(start.plusMonths(1).plusMonths(1)); // 2024-03-29
System.out.println(start.plusMonths(2));               // 2024-03-31
```

Đây là đoạn minh họa trong phương thức có `import java.time.LocalDate;`. Bước `+1 month` đầu tiên điều chỉnh 31 thành 29 khi đi qua tháng 2; bước tiếp theo lấy **ngày 29** làm gốc, trong khi `+2 months` trực tiếp từ 31/1 giữ ngày 31 ở tháng 3.

Do đó với lịch định kỳ thu tiền hằng tháng, nên tính các kỳ từ **ngày gốc cộng n tháng**, hoặc định nghĩa rõ quy tắc “ngày cuối tháng”, thay vì luôn nối tiếp từ kết quả kỳ trước và mặc định chúng tương đương.

## 8. Ví dụ Java 17+ đầy đủ: immutable, with, plus, minus

Lưu file **`ImmutableDateTimeDemo.java`**:

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.temporal.TemporalAdjusters;

public class ImmutableDateTimeDemo {
    public static void main(String[] args) {
        LocalDate original = LocalDate.of(2024, 1, 31);

        LocalDate firstDay = original.withDayOfMonth(1);
        LocalDate oneMonthLater = original.plusMonths(1);
        LocalDate threeDaysEarlier = firstDay.minusDays(3);

        System.out.println("original = " + original);
        System.out.println("firstDay = " + firstDay);
        System.out.println("oneMonthLater = " + oneMonthLater);
        System.out.println("threeDaysEarlier = " + threeDaysEarlier);
        System.out.println("original again = " + original);

        LocalDateTime meeting = LocalDateTime.of(2024, 6, 10, 9, 30);
        LocalDateTime rescheduled = meeting
                .withHour(14)
                .plusDays(2)
                .minusMinutes(15);

        System.out.println("meeting = " + meeting);
        System.out.println("rescheduled = " + rescheduled);

        LocalDate saturday = LocalDate.of(2026, 10, 24);
        LocalDate nextMonday = saturday.with(
                TemporalAdjusters.next(DayOfWeek.MONDAY));
        System.out.println("nextMonday = " + nextMonday);
    }
}
```

Chạy bằng Java 17+:

```bash
javac ImmutableDateTimeDemo.java
java ImmutableDateTimeDemo
```

Kết quả xác định:

```text
original = 2024-01-31
firstDay = 2024-01-01
oneMonthLater = 2024-02-29
threeDaysEarlier = 2023-12-29
original again = 2024-01-31
meeting = 2024-06-10T09:30
rescheduled = 2024-06-12T14:15
nextMonday = 2026-10-26
```

Giải thích:

1. Các giá trị `firstDay`, `oneMonthLater` và `threeDaysEarlier` là kết quả mới, còn `original` không đổi.
2. `plusMonths(1)` từ 31/1/2024 đi đến 29/2/2024 vì tháng 2 năm nhuận không có ngày 31.
3. Khi điều chỉnh cuộc họp, `withHour(14)` đặt giờ 14, `plusDays(2)` chuyển tới 12/6 và `minusMinutes(15)` đưa phút 30 về 15.
4. `next(MONDAY)` tìm thứ Hai kế tiếp kể từ thứ Bảy 24/10/2026.

## 9. Đi qua DST: plusDays(1) có thể khác plusHours(24)

Đây là khác biệt quan trọng của `ZonedDateTime` khi một múi giờ có thay đổi offset theo quy tắc daylight saving time. `plusDays(1)` thao tác theo **ngày trên lịch địa phương**; `plusHours(24)` thao tác theo **24 giờ elapsed** trên timeline. Hai kết quả có thể khác nhau khi chuyển giờ mùa hè.

Lưu file **`DstAdjustmentDemo.java`**:

```java
import java.time.Duration;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DstAdjustmentDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");

        ZonedDateTime before = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, zone);

        ZonedDateTime nextCalendarDay = before.plusDays(1);
        ZonedDateTime after24Hours = before.plusHours(24);

        System.out.println("before = " + before);
        System.out.println("plusDays(1) = " + nextCalendarDay);
        System.out.println("plusHours(24) = " + after24Hours);
        System.out.println("elapsedHours = "
                + Duration.between(before, nextCalendarDay).toHours());
    }
}
```

Biên dịch và chạy:

```bash
javac DstAdjustmentDemo.java
java DstAdjustmentDemo
```

Kết quả theo quy tắc múi giờ New York áp dụng cho tháng 3/2024:

```text
before = 2024-03-09T12:00-05:00[America/New_York]
plusDays(1) = 2024-03-10T12:00-04:00[America/New_York]
plusHours(24) = 2024-03-10T13:00-04:00[America/New_York]
elapsedHours = 23
```

Đêm 10/3/2024 tại New York, đồng hồ nhảy từ 02:00 sang 03:00. Đi từ **12:00 hôm trước tới 12:00 hôm sau trên lịch địa phương** chỉ có 23 giờ elapsed, còn cộng chính xác 24 giờ thì đến 13:00. Vì vậy:

- Quy tắc “ngày mai vào cùng giờ địa phương” → thường dùng `zoned.plusDays(1)`.
- Quy tắc “sau đúng 24 giờ thực tế” → dùng `zoned.plusHours(24)` hoặc `zoned.plus(Duration.ofHours(24))`.
- `Period.ofDays(1)` gắn với ngày lịch; `Duration.ofDays(1)` luôn biểu diễn 24 giờ theo giây. Với `ZonedDateTime`, chúng có thể tạo ra hai mốc thời gian khác nhau.

Khi dùng `withHour(...)` hoặc thay ngày trên `ZonedDateTime` trúng một giờ địa phương **không tồn tại** trong DST gap, Java phải điều chỉnh kết quả để được thời điểm hợp lệ; trong overlap có thể có hai offset hợp lệ. Đừng giả định mọi tổ hợp “ngày + giờ địa phương + ZoneId” luôn ánh xạ duy nhất tới một instant. Với lịch đặt hẹn, phải định nghĩa hành vi ở vùng gap/overlap.

Không nên áp dụng lập luận DST cho `LocalDateTime` khi chưa gắn `ZoneId`: `LocalDateTime` chỉ giữ các thành phần lịch/giờ, chưa xác định offset hay instant trên timeline.

## 10. Các lớp java.time khác nhau hỗ trợ thao tác khác nhau

| Kiểu | Thay trường với with | Cộng/trừ điển hình | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| `LocalDate` | `withYear`, `withMonth`, `withDayOfMonth`, adjuster lịch | `plusDays`, `plusMonths`, `minusYears` | Không có giờ, offset hoặc zone |
| `LocalTime` | `withHour`, `withMinute`, `withNano` | `plusHours`, `minusSeconds` | Quay vòng 24 giờ, không giữ ngày |
| `LocalDateTime` | Các trường ngày và giờ | `plusDays`, `plusHours`, `minusMinutes` | Không tự biết DST nếu chưa gắn zone |
| `ZonedDateTime` | Các trường ngày/giờ, điều chỉnh zone/offset | Cộng ngày lịch hoặc lượng thời gian | Phải xét DST gap/overlap |
| `OffsetDateTime` | Các trường ngày/giờ và offset | Cộng/trừ ngày giờ | Có offset cố định trong giá trị, không có toàn bộ quy tắc `ZoneId` |
| `Instant` | Các trường thời điểm được hỗ trợ | `plusSeconds`, `plusMillis`, `minusNanos` | Không cộng “tháng lịch” khi thiếu zone |
| `Duration` | `withSeconds`, `withNanos` | `plusSeconds`, `minusMillis`, cộng/trừ Duration | Đại lượng thời lượng, không là ngày/giờ lịch |
| `Period` | `withYears`, `withMonths`, `withDays` | `plusYears`, `minusMonths`, cộng/trừ Period | Lượng năm-tháng-ngày, không là số giây cố định |

Đặc biệt `Period.withDays(5)` nghĩa là **thay thành phần days thành 5**, không chuyển period thành “5 ngày tổng cộng”. Ví dụ `Period.of(1, 2, 3).withDays(5)` là `P1Y2M5D`, còn `Period.of(1, 2, 3).plusDays(5)` là `P1Y2M8D`. Lưu ý các thành phần `Period` có thể mang dấu riêng; `Period` không tự chuẩn hóa mọi tổ hợp thành một số ngày vì độ dài tháng không cố định.

Tương tự `Duration.withNanos(500_000_000)` thay phần nano trong giây, **không cộng** thêm 500 triệu nano. Chọn đúng loại đại lượng là bước đầu tiên trước khi dùng họ phương thức.

## 11. Validation, ngoại lệ và overflow

Các thao tác bất biến vẫn có thể thất bại:

- **Giá trị trường không hợp lệ:** `withDayOfMonth(32)` hoặc `withHour(24)` bị từ chối bằng `DateTimeException`.
- **Trường hoặc đơn vị không được hỗ trợ:** ví dụ `LocalDate.now().plus(1, ChronoUnit.HOURS)` ném `UnsupportedTemporalTypeException` (là một `DateTimeException`).
- **Vượt phạm vi có thể biểu diễn:** ví dụ `LocalDate.MAX.plusDays(1)` không thể tạo giá trị hợp lệ; có thể gặp `DateTimeException` hoặc `ArithmeticException` theo API và thao tác.
- **Tràn số lượng:** một số phép chuyển đổi/nhân số lượng lớn có thể ném `ArithmeticException`, nhất là khi dữ liệu đầu vào đến từ bên ngoài.

Lưu file **`InvalidAdjustmentDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;

public class InvalidAdjustmentDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);

        try {
            date.withDayOfMonth(30);
        } catch (DateTimeException ex) {
            System.out.println("Invalid February day");
        }

        try {
            date.plus(1, ChronoUnit.HOURS);
        } catch (DateTimeException ex) {
            System.out.println("Unsupported hour unit");
        }

        System.out.println("date remains = " + date);
    }
}
```

Biên dịch với `javac InvalidAdjustmentDemo.java` rồi chạy `java InvalidAdjustmentDemo`:

```text
Invalid February day
Unsupported hour unit
date remains = 2024-02-29
```

Chính vì đối tượng bất biến, lời gọi thất bại không làm hỏng `date`. Tuy nhiên hãy **xác thực đầu vào từ người dùng** trước khi lập lịch, và chỉ bắt ngoại lệ ở mức phù hợp để đưa thông báo hữu ích; không tự động đổi mọi giá trị sai thành một ngày bất kỳ.

## 12. Quy tắc áp dụng trong mã thực tế

1. **Luôn dùng giá trị trả về.** Một lời gọi `orderDate.plusDays(7);` đơn độc rất dễ là bug. Gán kết quả hoặc trả ra từ hàm.
2. **Dùng `with...()` khi yêu cầu nói “đặt thành”.** “Đặt hạn vào ngày 1” → `withDayOfMonth(1)`; “gia hạn 1 tháng” → `plusMonths(1)`.
3. **Xác định đơn vị lịch hay thời lượng.** Deadline theo tháng/ngày của lịch không tự tương đương số giờ cố định; qua DST lại càng quan trọng.
4. **Để ý thứ tự chain.** Với mốc cuối tháng, `plusMonths(1).plusMonths(1)` có thể khác `plusMonths(2)`.
5. **Giữ ngữ cảnh thời gian.** `LocalDate` cho ngày đơn thuần; `ZonedDateTime` cho lịch theo múi giờ; `Instant` cho một mốc tuyệt đối. Không suy ra zone từ `LocalDateTime`.
6. **Dùng adjuster diễn đạt quy tắc.** `firstDayOfMonth()`, `lastDayOfMonth()`, `nextOrSame(...)` rõ ràng hơn tự cộng trừ các số “ma thuật”.
7. **Tránh so sánh bằng identity.** `before.equals(after)` kiểm tra giá trị; `before == after` chỉ so tham chiếu.
8. **Tạo giá trị đầu vào cố định khi kiểm thử.** Các ví dụ dùng `of(...)` thay vì `now()` để không thay đổi theo thời điểm chạy; các quy tắc nghiệp vụ có thể cần `Clock` được tiêm vào để kiểm thử có kiểm soát.
9. **Thử ranh giới.** Đưa vào 28/2, 29/2 năm nhuận, 30/4, 31/1, chuyển năm, DST, giờ 23:59 và trường ngoài phạm vi.
10. **Đừng nhầm tính bất biến với “luôn không lỗi”.** Bất biến giữ nguyên đối tượng cũ, nhưng quy tắc tháng, vùng DST và phạm vi giá trị vẫn phải được thiết kế.

## 13. Bài tập tự kiểm tra

**Câu 1.** Với `LocalDate d = LocalDate.of(2024, 1, 31);`, lệnh `d.plusMonths(1);` được gọi mà không gán kết quả. Sau lệnh, `d` là ngày nào?

**Đáp án:** `2024-01-31`; kết quả trả về bị bỏ đi.

**Câu 2.** Từ 31/1/2024, `withDayOfMonth(1)`, `plusDays(1)`, `plusMonths(1)` lần lượt ra gì?

**Đáp án:** `2024-01-01`, `2024-02-01`, `2024-02-29`.

**Câu 3.** Từ ngày 31/1/2024, `plusMonths(2)` và `plusMonths(1).plusMonths(1)` có bằng nhau không?

**Đáp án:** Không. Trường hợp đầu là `2024-03-31`; trường hợp sau là `2024-03-29` vì bước đi qua tháng 2 đã điều chỉnh ngày 31 xuống 29.

**Câu 4.** Vì sao `ZonedDateTime.plusDays(1)` khác `ZonedDateTime.plusHours(24)` khi qua DST?

**Đáp án:** Một phép cộng theo **ngày lịch địa phương**, phép kia theo **24 giờ đã trôi qua**. Ngày có chuyển giờ có thể dài 23 hoặc 25 giờ.

**Câu 5.** Muốn tìm thứ Hai **hôm nay hoặc tiếp theo** thì dùng gì?

**Đáp án:** `date.with(TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY))`. Nếu dùng `next(...)` vào đúng thứ Hai, kết quả là thứ Hai tuần sau.

**Kết luận:** Với `java.time`, `with...()` **thay giá trị thành phần hoặc áp dụng quy tắc**, `plus...()` **cộng** và `minus...()` **trừ**. Cả ba trả về một giá trị ngày giờ bất biến; chọn đúng loại ngày giờ, đơn vị và quy tắc biên là điều quyết định kết quả có đúng nghiệp vụ hay không.