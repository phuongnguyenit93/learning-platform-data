# Năm nhuận, cuối tháng và phép cộng theo lịch (Java 8+)

> **Chủ đề:** Ngày giờ cục bộ. Bài này hướng dẫn xử lý ngày nhuận, tìm ngày cuối tháng và làm phép cộng **theo lịch** bằng `LocalDate`, `Year`, `YearMonth`, `Period` và `TemporalAdjusters` trong `java.time`. Đây là các API từ Java 8, vẫn phù hợp trên JDK hiện đại. Ví dụ chính tương thích Java 8 và có thể biên dịch với `javac --release 8` trên JDK 17+.

## 1. Mục tiêu

Bạn sẽ biết cách kiểm tra năm nhuận theo quy tắc 4–100–400; tạo và kiểm tra ngày hợp lệ; dùng `YearMonth.atEndOfMonth` và `TemporalAdjusters.lastDayOfMonth`; phân biệt `plusDays`, `plusMonths`, `plusYears` và `Period`; thiết kế lịch định kỳ không **trôi ngày** khi qua tháng 2; phân biệt một **ngày lịch** với chính xác **24 giờ** nếu có múi giờ và DST.

## 2. Kiểu dữ liệu nào hợp lý?

| Kiểu | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `LocalDate` | Năm–tháng–ngày theo lịch ISO, không có giờ/zone | Ngày sinh, chốt sổ, hạn theo ngày |
| `Year` | Chỉ một năm | Kiểm tra năm nhuận |
| `YearMonth` | Năm và tháng, chưa chọn ngày | Kỳ báo cáo, kỳ thanh toán |
| `Period` | Lượng năm/tháng/ngày **theo lịch** | Sau một tháng, một năm |
| `Duration` | Lượng giây/nanosecond | Sau đúng 24 giờ |
| `ZonedDateTime` | Ngày giờ theo region `ZoneId` | Lịch hẹn với giờ địa phương và DST |

`LocalDate` không đại diện cho một thời điểm UTC. Khi cần log timestamp trên timeline, dùng `Instant`; khi cần một lịch hẹn ở địa điểm cụ thể, gắn `ZoneId` và xử lý quy tắc giờ của vùng đó. Các kiểu java.time này là immutable: mọi `plus...`/`with...` trả **bản mới**, không làm thay đổi ngày gốc.

```java
LocalDate original = LocalDate.of(2024, 1, 31);
LocalDate next = original.plusMonths(1);
// original vẫn 2024-01-31; next là 2024-02-29.
```

## 3. Năm nhuận ISO/Gregorian

Quy tắc:

1. Chia hết cho **4** thì có thể nhuận.
2. Nhưng chia hết cho **100** thì không nhuận.
3. Ngoại lệ: chia hết cho **400** vẫn nhuận.

Có thể diễn đạt toán học:

```java
boolean leap = year % 4 == 0
        && (year % 100 != 0 || year % 400 == 0);
```

Đoạn trên chỉ minh họa quy tắc với biến `year` giả định. Trong chương trình thực, ưu tiên API:

```java
boolean leap2024 = Year.isLeap(2024); // true.
boolean leap2000 = Year.of(2000).isLeap(); // true.
boolean leapOfDate = LocalDate.of(2024, 2, 1).isLeapYear(); // true.
```

| Năm | Kết quả | Nguyên nhân |
| ---: | --- | --- |
| 1900 | Không nhuận | Chia hết 100 nhưng không chia hết 400 |
| 2000 | Nhuận | Chia hết 400 |
| 2024 | Nhuận | Chia hết 4, không chia hết 100 |
| 2025 | Không nhuận | Không chia hết 4 |
| 2100 | Không nhuận | Ngoại lệ thế kỷ |
| 2400 | Nhuận | Chia hết 400 |

`java.time` dùng **proleptic ISO/Gregorian calendar** (áp dụng quy tắc Gregorian xuyên suốt các năm hỗ trợ). Nếu nghiên cứu những lịch sử địa phương trước lúc áp dụng lịch Gregorian thì cần mô hình tương ứng; không được mặc định mọi lịch sử đều dùng cùng quy tắc.

### 3.1. Cách lấy độ dài tháng và năm

```java
int febLeap = YearMonth.of(2024, 2).lengthOfMonth(); // 29.
int febNormal = YearMonth.of(2025, 2).lengthOfMonth(); // 28.

int days2024 = LocalDate.of(2024, 1, 1).lengthOfYear(); // 366.
int days2025 = LocalDate.of(2025, 1, 1).lengthOfYear(); // 365.
```

Các tháng 1,3,5,7,8,10,12 có 31 ngày; tháng 4,6,9,11 có 30 ngày; tháng 2 thay đổi theo năm nhuận. `YearMonth.lengthOfMonth` giúp tránh mã hardcode một bảng tháng không có xử lý năm.

### 3.2. `LocalDate.of` kiểm tra ngày hợp lệ

```java
LocalDate valid = LocalDate.of(2024, 2, 29);

// LocalDate.of(2025, 2, 29) -> DateTimeException.
// LocalDate.of(2024, 4, 31) -> DateTimeException.
```

Khi **tạo** ngày sai bằng `of`, Java không tự điều chỉnh. Điều chỉnh về cuối tháng chỉ xuất hiện với **một số phép thay đổi/cộng ngày lịch** như `plusMonths` và `plusYears`. Đừng nhầm hai cơ chế.

## 4. Lấy ngày cuối tháng

### `YearMonth.atEndOfMonth()`

```java
LocalDate end2024 = YearMonth.of(2024, 2).atEndOfMonth();
// 2024-02-29.

LocalDate end2025 = YearMonth.of(2025, 2).atEndOfMonth();
// 2025-02-28.

LocalDate endApril = YearMonth.of(2024, 4).atEndOfMonth();
// 2024-04-30.
```

Đây là lựa chọn dễ hiểu nhất khi ứng dụng có **kỳ tháng** từ đầu.

### `TemporalAdjusters.lastDayOfMonth()`

```java
LocalDate day = LocalDate.of(2024, 4, 15);

LocalDate last = day.with(TemporalAdjusters.lastDayOfMonth());
// 2024-04-30.

LocalDate alsoLast = day.withDayOfMonth(day.lengthOfMonth());
// 2024-04-30.
```

`YearMonth.atEndOfMonth` và `TemporalAdjusters.lastDayOfMonth` đều quan tâm năm nhuận. Không đồng nhất ngày cuối tháng với ngày làm việc cuối: thứ Bảy, Chủ Nhật và ngày nghỉ lễ thuộc **chính sách nghiệp vụ khác**.

### Phân biệt ngày cụ thể với ngày cuối tháng

```java
YearMonth april = YearMonth.of(2024, 4);
LocalDate last = april.atEndOfMonth(); // 2024-04-30.

// april.atDay(31) sẽ ném DateTimeException.
```

`atDay(31)` là “ngày 31 chính xác hoặc báo lỗi”, không phải “cố lấy ngày cuối tháng”. Nếu yêu cầu là ngày cuối, dùng `atEndOfMonth`.

## 5. Cộng ngày, tuần, tháng, năm theo lịch

### 5.1. `plusDays` và `plusWeeks`

```java
LocalDate leapDay = LocalDate.of(2024, 2, 29);

LocalDate tomorrow = leapDay.plusDays(1);
// 2024-03-01.

LocalDate aWeekLater = leapDay.plusWeeks(1);
// 2024-03-07.

LocalDate yesterday = leapDay.minusDays(1);
// 2024-02-28.
```

Với `LocalDate`, `plusWeeks(1)` tương đương cộng 7 ngày lịch; ranh giới năm/tháng được tính tự động. Không suy ra ngay rằng một ngày lịch luôn bằng 86.400 giây, vì `LocalDate` không chứa timezone hay giờ. Khi gắn zone và DST, một ngày trên lịch có thể có 23 hoặc 25 giờ elapsed.

### 5.2. `plusMonths` điều chỉnh khi ngày đích không có

`LocalDate.plusMonths(n)` thực hiện:

1. Cộng `n` vào tháng.
2. Cố giữ cùng ngày trong tháng.
3. Nếu ngày đó không tồn tại trong tháng đích, chọn **ngày cuối cùng hợp lệ của tháng đích**.

```java
LocalDate jan31 = LocalDate.of(2024, 1, 31);

LocalDate feb = jan31.plusMonths(1); // 2024-02-29.
LocalDate mar = jan31.plusMonths(2); // 2024-03-31.
LocalDate apr = jan31.plusMonths(3); // 2024-04-30.
```

| Ngày gốc | Phép cộng | Kết quả |
| --- | --- | --- |
| 2023-01-31 | `plusMonths(1)` | 2023-02-28 |
| 2024-01-31 | `plusMonths(1)` | 2024-02-29 |
| 2024-01-31 | `plusMonths(2)` | 2024-03-31 |
| 2024-01-31 | `plusMonths(3)` | 2024-04-30 |
| 2024-03-31 | `plusMonths(1)` | 2024-04-30 |

**Bẫy quan trọng: cộng 2 tháng trực tiếp khác cộng 1 tháng hai lần.**

```java
LocalDate jan31 = LocalDate.of(2024, 1, 31);

LocalDate direct = jan31.plusMonths(2);
// 2024-03-31.

LocalDate repeated = jan31.plusMonths(1).plusMonths(1);
// 2024-03-29.
```

Khi đi qua tháng 2, ngày 31 bị **clamp xuống 29**. Kỳ tiếp theo chỉ thấy ngày gốc của nó là 29, không tự nhớ 31. Trong khi đó, cộng 2 tháng trực tiếp từ 31/1 sang tháng 3 vẫn có ngày 31.

Điều này cũng khiến phép cộng rồi trừ tháng **không nhất thiết đảo ngược**:

```java
LocalDate start = LocalDate.of(2024, 1, 31);

LocalDate after = start.plusMonths(1).minusMonths(1);
// 2024-01-29, không phải 2024-01-31.
```

Nếu cần chức năng hoàn tác, hãy lưu ngày ban đầu hoặc quy tắc anchor; không dùng `minusMonths` như một “inverse” bảo đảm.

### 5.3. `plusYears` và ngày 29 tháng 2

```java
LocalDate leap = LocalDate.of(2024, 2, 29);

LocalDate nextYear = leap.plusYears(1); // 2025-02-28.
LocalDate afterFour = leap.plusYears(4); // 2028-02-29.
LocalDate nextDay = leap.plusDays(1); // 2024-03-01.
```

`plusYears` cũng giữ tháng/ngày nếu hợp lệ; nếu không hợp lệ thì clamp về cuối tháng. Nhưng lịch kỷ niệm ngày 29/2 trong năm không nhuận có thể được quy định theo **28/2 hoặc 1/3** tùy nghiệp vụ/pháp lý. API không thể quyết định chính sách đó thay cho ứng dụng.

Cũng có thể bị mất ngày neo khi cộng năm từng bước:

```java
LocalDate start = LocalDate.of(2024, 2, 29);

LocalDate direct = start.plusYears(4); // 2028-02-29.
LocalDate chained = start.plusYears(1).plusYears(3);
// 2028-02-28.
```

Khi đã giảm từ 29 sang 28 trong năm thường, ngày 29 không được tự khôi phục khi sang năm nhuận. Với lịch kỷ niệm, luôn giữ **ngày neo ban đầu** hoặc policy riêng.

## 6. `Period` khác `Duration`

`Period` mô tả lượng **năm, tháng, ngày lịch**:

```java
Period oneMonth = Period.ofMonths(1);
Period oneYear = Period.ofYears(1);
Period quarter = Period.ofMonths(3);

LocalDate start = LocalDate.of(2024, 1, 31);
LocalDate a = start.plusMonths(1);
LocalDate b = start.plus(Period.ofMonths(1));
// Cả a và b đều 2024-02-29.
```

Một tháng `Period` không có số ngày cố định. `Duration.ofDays(30)` là 30×24 giờ thực, trong khi “một tháng lịch” có thể tương ứng tháng 28, 29, 30 hoặc 31 ngày theo mốc và quy tắc clamp.

`Period.between(a,b)` cho **các thành phần lịch** (năm/tháng/ngày), không trực tiếp cho số ngày tổng. Muốn đếm ngày giữa hai `LocalDate` dùng `ChronoUnit.DAYS.between(a,b)`:

```java
LocalDate a = LocalDate.of(2024, 2, 1);
LocalDate b = LocalDate.of(2024, 3, 1);

Period period = Period.between(a, b);
// P1M: một tháng.

long days = ChronoUnit.DAYS.between(a, b);
// 29 ngày.
```

Đừng đồng nhất cộng `Period.ofMonths(1)` với cộng 30 ngày. Nếu yêu cầu hợp đồng là “1 tháng theo lịch”, hãy nói rõ cách tính ngày đến hạn trong tháng thiếu ngày gốc.

## 7. Sinh lịch định kỳ KHÔNG trôi ngày

### Chính sách A — luôn là ngày cuối tháng

Với kỳ chốt sổ “ngày cuối cùng của mỗi tháng”, nên lấy mỗi kỳ `YearMonth` rồi gọi `atEndOfMonth`:

```java
YearMonth start = YearMonth.of(2024, 1);

List<LocalDate> schedule = IntStream.range(0, 4)
        .mapToObj(i -> start.plusMonths(i).atEndOfMonth())
        .collect(Collectors.toList());
// [2024-01-31, 2024-02-29, 2024-03-31, 2024-04-30].
```

Không dùng vòng lặp `current = current.plusMonths(1)` từ 31/1 rồi cho rằng mọi kỳ tự động là cuối tháng: sau tháng 2, ngày có thể bị trôi.

### Chính sách B — ngày 30, nếu thiếu thì cuối tháng

```java
static LocalDate dayOfMonthOrLast(YearMonth month, int requestedDay) {
    if (requestedDay < 1 || requestedDay > 31) {
        throw new IllegalArgumentException("day must be 1..31");
    }
    return month.atDay(Math.min(requestedDay, month.lengthOfMonth()));
}
```

Đây là snippet method trong một class, được dùng trong chương trình đầy đủ bên dưới.

```java
YearMonth jan = YearMonth.of(2024, 1);

List<LocalDate> dates = IntStream.range(0, 4)
        .mapToObj(i -> dayOfMonthOrLast(jan.plusMonths(i), 30))
        .collect(Collectors.toList());
// [2024-01-30, 2024-02-29, 2024-03-30, 2024-04-30].
```

Ngày 30 là **ngày neo lưu riêng**. Sau khi tháng 2 tạm dùng 29, tháng 3 trở lại 30 chứ không dùng 29 làm neo mới.

### Chính sách C — 29/2 hằng năm

Phải xác định chính sách khi năm đích không nhuận: dùng 28/2 hay 1/3. `plusYears(1)` mặc định cho 28/2; đừng coi đó là đáp án cho mọi quy định. Nên sinh từng kỳ theo năm mục tiêu và **ngày/điều khoản gốc**, thay vì lấy ngày đã điều chỉnh của kỳ trước.

### Chính sách D — ngày làm việc cuối tháng

`atEndOfMonth` không biết ngày nghỉ lễ hoặc lịch làm việc. Nếu chỉ muốn tránh cuối tuần, có thể điều chỉnh lùi từ cuối tháng:

```java
LocalDate d = YearMonth.of(2024, 8).atEndOfMonth();

while (d.getDayOfWeek() == DayOfWeek.SATURDAY
        || d.getDayOfWeek() == DayOfWeek.SUNDAY) {
    d = d.minusDays(1);
}
```

Đây chỉ giải quyết ngày cuối tuần, **chưa** giải quyết nghỉ lễ theo quốc gia/vùng. Sản phẩm cần chính sách rõ về ngày làm việc, dời tới hay dời lui và dữ liệu holiday calendar.

**Thiết kế lưu trữ nên có:** kỳ gốc, kiểu ngày neo (ví dụ `END_OF_MONTH` hoặc `DAY_N_OR_LAST`), số N nếu có, số kỳ và chính sách xử lý ngày nghỉ. Đừng lưu riêng một ngày đã bị clamp rồi dùng nó làm nguồn chân lý cho mọi kỳ kế tiếp.

## 8. Một ngày lịch có thể không phải 24 giờ thực

Với `LocalDate` không có timezone, `plusDays(1)` chỉ nghĩa “ngày tiếp theo”. Khi gắn giờ và region zone có DST, `ZonedDateTime.plusDays(1)` giữ logic **ngày và giờ địa phương**, trong khi `plus(Duration.ofHours(24))` tăng một thời lượng **24 giờ thực**.

Ví dụ tại Paris trước ngày đổi sang giờ mùa hè:

```java
ZoneId paris = ZoneId.of("Europe/Paris");

ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 30, 12, 0, 0, 0, paris);

ZonedDateTime calendarDay = start.plusDays(1);
// 2024-03-31T12:00+02:00[Europe/Paris].

ZonedDateTime elapsed24h = start.plus(Duration.ofHours(24));
// 2024-03-31T13:00+02:00[Europe/Paris].
```

Ngày này có **DST gap**: từ 12:00 hôm trước đến 12:00 hôm sau chỉ trôi qua **23 giờ thực**. Cộng chính xác 24 giờ cho kết quả 13:00 ở ngày kế tiếp. Nếu yêu cầu là “ngày mai cùng giờ”, chọn phép lịch; nếu yêu cầu “sau đúng 24 giờ”, chọn `Duration`/`Instant`.

Các quy tắc vùng thay đổi theo lịch sử và bản cập nhật timezone database. Với lịch hẹn ở vùng có giờ không tồn tại hoặc trùng lặp, ứng dụng cần chính sách xử lý rõ ràng, không thể chỉ dựa vào LocalDateTime để suy ra một Instant duy nhất.

## 9. Chương trình Java hoàn chỉnh

Tạo file **`CalendarArithmeticDemo.java`**. Chương trình kiểm tra năm nhuận, ngày cuối tháng, sự khác nhau giữa cộng trực tiếp và cộng lặp, lịch theo ngày neo, xử lý ngày không hợp lệ và DST. Không dùng `now()` nên các ví dụ có đầu ra xác định.

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.LocalDate;
import java.time.Period;
import java.time.Year;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalAdjusters;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class CalendarArithmeticDemo {
    static LocalDate dayOfMonthOrLast(YearMonth month, int requestedDay) {
        if (requestedDay < 1 || requestedDay > 31) {
            throw new IllegalArgumentException("day must be 1..31");
        }
        return month.atDay(Math.min(requestedDay, month.lengthOfMonth()));
    }

    public static void main(String[] args) {
        YearMonth feb24 = YearMonth.of(2024, 2);
        YearMonth feb25 = YearMonth.of(2025, 2);
        LocalDate jan31 = LocalDate.of(2024, 1, 31);
        LocalDate leapDay = LocalDate.of(2024, 2, 29);

        LocalDate byOneMonth = jan31.plusMonths(1);
        LocalDate directTwoMonths = jan31.plusMonths(2);
        LocalDate chainedTwoMonths = jan31.plusMonths(1).plusMonths(1);
        LocalDate byPeriod = jan31.plus(Period.ofMonths(1));
        LocalDate anniversary = leapDay.plusYears(1);
        LocalDate aprilEnd = LocalDate.of(2024, 4, 15)
                .with(TemporalAdjusters.lastDayOfMonth());

        List<LocalDate> monthEnds = IntStream.range(0, 4)
                .mapToObj(i -> YearMonth.from(jan31)
                        .plusMonths(i).atEndOfMonth())
                .collect(Collectors.toList());

        List<LocalDate> day30 = IntStream.range(0, 4)
                .mapToObj(i -> dayOfMonthOrLast(
                        YearMonth.of(2024, 1).plusMonths(i), 30))
                .collect(Collectors.toList());

        boolean rejected = false;
        try {
            LocalDate.of(2025, 2, 29);
        } catch (DateTimeException ex) {
            rejected = true;
        }

        ZonedDateTime paris = ZonedDateTime.of(
                2024, 3, 30, 12, 0, 0, 0,
                ZoneId.of("Europe/Paris"));
        ZonedDateTime calendarDay = paris.plusDays(1);
        ZonedDateTime fixed24Hours = paris.plus(Duration.ofHours(24));
        long actualHours = Duration.between(paris, calendarDay).toHours();

        System.out.println("Leap 1900/2000/2024/2025: "
                + Year.isLeap(1900) + "/" + Year.isLeap(2000)
                + "/" + Year.isLeap(2024) + "/" + Year.isLeap(2025));
        System.out.println("February 2024/2025: "
                + feb24.lengthOfMonth() + "/" + feb25.lengthOfMonth());
        System.out.println("Last days: "
                + feb24.atEndOfMonth() + " / " + feb25.atEndOfMonth());
        System.out.println("Jan31 +1 month: " + byOneMonth);
        System.out.println("Jan31 +2 direct: " + directTwoMonths);
        System.out.println("Jan31 +1 +1: " + chainedTwoMonths);
        System.out.println("Jan31 +Period 1M: " + byPeriod);
        System.out.println("Feb29 +1 year: " + anniversary);
        System.out.println("Feb29 +1 day: " + leapDay.plusDays(1));
        System.out.println("April end: " + aprilEnd);
        System.out.println("Month-end schedule: " + monthEnds);
        System.out.println("Day-30 schedule: " + day30);
        System.out.println("Invalid date rejected: " + rejected);
        System.out.println("Feb 2024 days: " + ChronoUnit.DAYS.between(
                LocalDate.of(2024, 2, 1), LocalDate.of(2024, 3, 1)));
        System.out.println("Paris calendar +1 day: " + calendarDay);
        System.out.println("Paris duration +24h: " + fixed24Hours);
        System.out.println("Elapsed hours for calendar day: " + actualHours);

        if (Year.isLeap(1900) || !Year.isLeap(2000)
                || !Year.isLeap(2024) || Year.isLeap(2025)
                || feb24.lengthOfMonth() != 29
                || feb25.lengthOfMonth() != 28
                || !byOneMonth.equals(leapDay)
                || !directTwoMonths.equals(LocalDate.of(2024, 3, 31))
                || !chainedTwoMonths.equals(LocalDate.of(2024, 3, 29))
                || !byPeriod.equals(leapDay)
                || !anniversary.equals(LocalDate.of(2025, 2, 28))
                || !aprilEnd.equals(LocalDate.of(2024, 4, 30))
                || !monthEnds.equals(Arrays.asList(
                       LocalDate.of(2024,1,31), LocalDate.of(2024,2,29),
                       LocalDate.of(2024,3,31), LocalDate.of(2024,4,30)))
                || !day30.equals(Arrays.asList(
                       LocalDate.of(2024,1,30), LocalDate.of(2024,2,29),
                       LocalDate.of(2024,3,30), LocalDate.of(2024,4,30)))
                || !rejected || actualHours != 23
                || !calendarDay.toString().equals(
                       "2024-03-31T12:00+02:00[Europe/Paris]")
                || !fixed24Hours.toString().equals(
                       "2024-03-31T13:00+02:00[Europe/Paris]")) {
            throw new AssertionError("Calendar arithmetic mismatch");
        }
        System.out.println("Checks passed.");
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac --release 8 CalendarArithmeticDemo.java
java CalendarArithmeticDemo
```

**Stdout đã kiểm chứng trên OpenJDK 24:**

```text
Leap 1900/2000/2024/2025: false/true/true/false
February 2024/2025: 29/28
Last days: 2024-02-29 / 2025-02-28
Jan31 +1 month: 2024-02-29
Jan31 +2 direct: 2024-03-31
Jan31 +1 +1: 2024-03-29
Jan31 +Period 1M: 2024-02-29
Feb29 +1 year: 2025-02-28
Feb29 +1 day: 2024-03-01
April end: 2024-04-30
Month-end schedule: [2024-01-31, 2024-02-29, 2024-03-31, 2024-04-30]
Day-30 schedule: [2024-01-30, 2024-02-29, 2024-03-30, 2024-04-30]
Invalid date rejected: true
Feb 2024 days: 29
Paris calendar +1 day: 2024-03-31T12:00+02:00[Europe/Paris]
Paris duration +24h: 2024-03-31T13:00+02:00[Europe/Paris]
Elapsed hours for calendar day: 23
Checks passed.
```

Phần tự kiểm tra trong chương trình không dùng Java `assert` (có thể bị tắt nếu thiếu `-ea`) mà ném `AssertionError` nếu kết quả không đúng. Điều này làm stdout tự kiểm thử đáng tin hơn trong ví dụ.

## 10. Lỗi phổ biến

| Lỗi | Vì sao sai? | Giải pháp |
| --- | --- | --- |
| Chia hết cho 4 là luôn nhuận | 1900/2100 là ngoại lệ thế kỷ | `Year.isLeap` |
| Tháng 2 lúc nào cũng 28 ngày | Năm nhuận có 29 | `YearMonth.lengthOfMonth` |
| `LocalDate.of(2025,2,29)` tự sửa | `of` ném exception cho ngày sai | Xác thực dữ liệu |
| Gọi `withDayOfMonth(31)` trên tháng 4 | Ngày 31 không có | `atEndOfMonth` nếu muốn cuối tháng |
| `plusMonths(1)` lặp luôn giữ cuối tháng | Clamp mất ngày neo | Tính từ từng `YearMonth` và policy gốc |
| Cộng trực tiếp 2 tháng luôn bằng cộng 1 tháng hai lần | Không đúng khi gặp clamp | Test mốc 31/1 |
| Cộng rồi trừ tháng trả về ngày cũ | Clamp có thể làm mất thông tin | Lưu ngày/anchor gốc |
| 29/2 cộng 1 năm tự đúng mọi quy định | API chọn 28/2, policy có thể chọn 1/3 | Định nghĩa policy |
| `Period.ofMonths(1)` là 30 ngày | Độ dài tháng khác nhau | Phân biệt calendar period |
| `Period.between` là tổng số ngày | Kết quả có năm/tháng/ngày | `ChronoUnit.DAYS.between` |
| Một ngày lịch bằng đúng 24 giờ thực | DST thay đổi số giờ elapsed | `plusDays` vs `Duration` |
| Ngày cuối tháng là ngày làm việc cuối | Còn cuối tuần/ngày nghỉ | Holiday calendar riêng |
| `LocalDate.now()` dùng để test ngày biên | Phụ thuộc thời gian chạy | `LocalDate.of` / `Clock.fixed` |

## 11. Kiểm thử và bài tập

Kiểm thử nên bao phủ: 1900, 2000, 2024, 2025, 2100; ngày 29/2 hợp lệ và không hợp lệ; 31/1 cộng tháng ở năm nhuận và năm thường; 31/3 sang tháng 4; 31/12 qua năm mới; phép trừ tháng; ngày cuối tháng khi trùng cuối tuần; quy tắc neo; và DST nếu có giờ địa phương. Nếu cần tính ngày từ một Instant, hãy chuyển nó về **múi giờ nghiệp vụ** trước khi lấy `toLocalDate()`.

**Bài 1.** Năm 2100 và 2400 có nhuận? — 2100 **không**, 2400 **có**.

**Bài 2.** Ngày cuối tháng 2/2028:

```java
LocalDate last = YearMonth.of(2028, 2).atEndOfMonth();
// 2028-02-29.
```

**Bài 3.** 31/1/2025 cộng một tháng là ngày nào?

```java
LocalDate result = LocalDate.of(2025, 1, 31).plusMonths(1);
// 2025-02-28.
```

**Bài 4.** 31/1/2024 cộng hai tháng trực tiếp so với cộng một tháng hai lần. — Lần lượt **31/3** và **29/3**. Bước trung gian qua tháng 2 đã điều chỉnh ngày.

**Bài 5.** Sinh các ngày cuối tháng 2, 3 và 4/2024:

```java
YearMonth feb = YearMonth.of(2024, 2);
List<LocalDate> dates = IntStream.range(0, 3)
        .mapToObj(i -> feb.plusMonths(i).atEndOfMonth())
        .collect(Collectors.toList());
// [2024-02-29, 2024-03-31, 2024-04-30].
```

**Bài 6.** Cần ngày 30 hàng tháng nhưng tháng 2 không có ngày 30. Tháng 3 sau tháng 2/2024 nên là ngày 29 hay 30? — **30/3**, vì ngày neo là 30, không phải ngày đã clamp tháng trước.

**Bài 7.** 29/2/2024 cộng một năm theo `LocalDate.plusYears` ra ngày nào? — **28/2/2025**; nếu hợp đồng cần 1/3, phải thiết kế policy riêng.

**Bài 8.** `Period.ofMonths(1)` có giống `Duration.ofDays(30)` không? — **Không**. Một lượng tháng lịch và 30×24 giờ thực là các khái niệm khác nhau.

**Bài 9.** Tại Paris ngày chuyển DST, “ngày mai cùng giờ địa phương” và “sau đúng 24 giờ” có chắc cùng kết quả? — **Không**. Dùng `plusDays` cho lịch địa phương, `Duration` cho thời lượng thực.

**Bài 10.** `YearMonth.atDay(31)` với tháng 4 có tự về ngày 30 không? — **Không**; ném `DateTimeException`. Dùng `atEndOfMonth` khi ý định là cuối tháng.

## 12. Nguồn tham khảo API hiện hành

- [Oracle Java SE 25 — LocalDate](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html): `isLeapYear`, `lengthOfMonth`, `plusDays`, `plusMonths`, `plusYears` và quy tắc clamp.
- [Oracle Java SE 25 — Year](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Year.html): `isLeap`, `length`.
- [Oracle Java SE 25 — YearMonth](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/YearMonth.html): `lengthOfMonth`, `atDay`, `atEndOfMonth`.
- [Oracle Java SE 25 — TemporalAdjusters](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/TemporalAdjusters.html): `lastDayOfMonth`.
- [Oracle Java SE 25 — Period](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Period.html) và [Duration](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html): calendar period đối chiếu elapsed duration.
- [Oracle Java SE 25 — ZonedDateTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html): local timeline, `plusDays` và DST.
- [Oracle Java SE 8 — java.time](https://docs.oracle.com/javase/8/docs/api/java/time/package-summary.html): API nền tảng đã xuất hiện từ Java 8.

**Tóm tắt:** `YearMonth.atEndOfMonth()` là giải pháp rõ ràng cho cuối tháng; `Year.isLeap` xử lý ngoại lệ năm chia hết 100/400; `plusMonths` và `plusYears` tự điều chỉnh ngày không còn hợp lệ nhưng **không ghi nhớ ngày neo cũ**. Lịch định kỳ đúng phải được tính lại từ tháng/năm mục tiêu và chính sách ngày neo, không cộng lặp trên kết quả đã clamp.
