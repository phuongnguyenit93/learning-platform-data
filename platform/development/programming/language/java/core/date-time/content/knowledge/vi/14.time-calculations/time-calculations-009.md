# Không quy đổi tháng và năm thành số giây cố định trong Java

## 1. Vấn đề và mục tiêu

Tháng và năm là **đơn vị lịch**, không phải lượng thời gian có độ dài cố định. Một tháng có thể dài 28, 29, 30 hoặc 31 ngày; một năm thường có 365 ngày và năm nhuận có 366 ngày. Ở những múi giờ có DST, một ngày địa phương còn có thể dài 23 hoặc 25 giờ elapsed time.

Trong Java, hãy tách hai ngữ nghĩa:

- `java.time.Period` biểu diễn lượng lịch theo năm, tháng và ngày.
- `java.time.Duration` biểu diễn lượng thời gian theo giây và nano giây.
- `java.time.LocalDate` và `LocalDateTime` biểu diễn các trường lịch; chúng không tự chứa múi giờ.
- `java.time.Instant` là một mốc tuyệt đối; `ZoneId` và `ZonedDateTime` áp dụng quy tắc thời gian của vùng.

“Gia hạn một tháng” là yêu cầu theo lịch. “Chờ chính xác 720 giờ” là yêu cầu theo thời lượng. Không nên thay thế hai khái niệm này bằng cùng một hằng số giây.

## 2. Vì sao không có số giây cố định cho một tháng hoặc một năm?

| Đơn vị lịch | Số ngày | Số giây nếu mỗi ngày quy ước là 86.400 giây |
| --- | ---: | ---: |
| Tháng 2 năm thường | 28 | 2.419.200 |
| Tháng 2 năm nhuận | 29 | 2.505.600 |
| Tháng có 30 ngày | 30 | 2.592.000 |
| Tháng có 31 ngày | 31 | 2.678.400 |
| Năm thường | 365 | 31.536.000 |
| Năm nhuận | 366 | 31.622.400 |

Các con số trong bảng chỉ chuyển đổi **số ngày cụ thể** sang giây; chúng không chứng minh một tháng hay một năm có độ dài chung. Ví dụ 30 × 24 × 60 × 60 bằng 2.592.000 giây, nhưng đó là đúng 30 ngày, không nhất thiết là một tháng lịch.

Hơn nữa, 86.400 giây là một ngày 24 giờ theo thời lượng. Tại vùng có DST, ngày lịch ở địa phương có thể chỉ có 23 giờ hoặc có 25 giờ. Vì thế không dùng phép nhân hằng số để đại diện tháng/năm hoặc ngày lịch trong mọi ngữ cảnh.

## 3. Period và Duration khác nhau

| Tiêu chí | Period | Duration |
| --- | --- | --- |
| Thành phần | Năm, tháng, ngày | Giây, nano giây |
| Ngữ nghĩa | Khoảng lịch | Thời lượng đã trôi |
| Ví dụ | `Period.ofMonths(1)` | `Duration.ofDays(30)` |
| Phù hợp với | Hạn hợp đồng, ngày kỷ niệm, chu kỳ lịch | Timeout, thời gian chạy, hiệu giữa hai instant |

```java
Period month = Period.ofMonths(1);
Duration thirtyDays = Duration.ofDays(30);

System.out.println(month);       // P1M
System.out.println(thirtyDays);  // PT720H
```

Đây là mã minh họa trong một phương thức, cần import `java.time.Period` và `java.time.Duration`. `P1M` là một tháng lịch; `PT720H` là 720 giờ. Period không chứa ngày bắt đầu nên tự nó không có tổng số giây cố định.

## 4. Cộng một tháng theo lịch

Dùng `LocalDate.plusMonths(1)` hoặc `plus(Period.ofMonths(1))` khi muốn tiến một tháng trên lịch.

```java
LocalDate leapStart = LocalDate.of(2024, 1, 31);
LocalDate ordinaryStart = LocalDate.of(2023, 1, 31);

System.out.println(leapStart.plusMonths(1));     // 2024-02-29
System.out.println(ordinaryStart.plusMonths(1)); // 2023-02-28
```

Mã minh họa cần import `java.time.LocalDate`. Nếu ngày 31 không tồn tại trong tháng đích, Java điều chỉnh về ngày cuối cùng hợp lệ của tháng ấy. Tháng 2/2024 có 29 ngày vì 2024 là năm nhuận; tháng 2/2023 có 28 ngày.

Chương trình đầy đủ **CalendarMonthDemo.java**:

```java
import java.time.LocalDate;
import java.time.Period;

public class CalendarMonthDemo {
    public static void main(String[] args) {
        LocalDate leapStart = LocalDate.of(2024, 1, 31);
        LocalDate ordinaryStart = LocalDate.of(2023, 1, 31);

        System.out.println("leapYear = "
                + leapStart.plus(Period.ofMonths(1)));
        System.out.println("ordinaryYear = "
                + ordinaryStart.plus(Period.ofMonths(1)));
        System.out.println("daysInFeb2024 = "
                + LocalDate.of(2024, 2, 1).lengthOfMonth());
        System.out.println("daysInFeb2023 = "
                + LocalDate.of(2023, 2, 1).lengthOfMonth());
    }
}
```

Biên dịch và chạy Java 17+:

```bash
javac CalendarMonthDemo.java
java CalendarMonthDemo
```

Kết quả:

```text
leapYear = 2024-02-29
ordinaryYear = 2023-02-28
daysInFeb2024 = 29
daysInFeb2023 = 28
```

## 5. Cộng một năm lịch

```java
LocalDate leapDay = LocalDate.of(2024, 2, 29);
System.out.println(leapDay.plusYears(1)); // 2025-02-28
```

Đây là mã minh họa cần import `java.time.LocalDate`. Ngày 29/2 không tồn tại trong năm 2025 nên được điều chỉnh về ngày 28/2. Nếu nghiệp vụ kỷ niệm muốn xử lý 29/2 thành ngày 1/3 thay vì 28/2, phải viết quy tắc riêng.

Tương tự, `LocalDateTime.plusYears(1)` điều chỉnh phần ngày theo quy tắc lịch nhưng không bổ sung múi giờ. `LocalDateTime` không đủ để xác định một instant nếu không biết offset hoặc ZoneId nguồn.

## 6. Một tháng không giống 30 ngày

```java
LocalDate start = LocalDate.of(2024, 2, 1);

System.out.println(start.plus(Period.ofMonths(1))); // 2024-03-01
System.out.println(start.plusDays(30));             // 2024-03-02
```

Đây là mã minh họa cần `LocalDate` và `Period`. Vì tháng 2/2024 có 29 ngày, cộng một tháng đưa ngày 1/2 tới 1/3; cộng đúng 30 ngày đưa tới 2/3.

| Ngày bắt đầu | +1 tháng lịch | +30 ngày |
| --- | --- | --- |
| 2024-02-01 | 2024-03-01 | 2024-03-02 |
| 2024-04-01 | 2024-05-01 | 2024-05-01 |
| 2024-01-31 | 2024-02-29 | 2024-03-01 |

Hai phép tính có thể tình cờ cho cùng kết quả ở một mốc bắt đầu, nhưng không tương đương tổng quát. Đọc yêu cầu trước khi chọn phép toán: “một tháng sau” khác “sau 30 ngày”.

## 7. Period gồm năm, tháng và ngày

```java
Period contract = Period.of(1, 2, 3);
System.out.println(contract); // P1Y2M3D

LocalDate start = LocalDate.of(2024, 1, 31);
System.out.println(start.plus(contract));
```

Đoạn mã minh họa cần `Period` và `LocalDate`. Period có các thành phần lịch, không phải tổng số ngày. Ngày cuối tháng có thể được điều chỉnh khi áp dụng Period lên ngày bắt đầu.

`Period.getDays()` chỉ trả thành phần ngày, không phải tổng số ngày giữa hai mốc. Nếu cần khoảng cách ngày giữa hai `LocalDate`, dùng `ChronoUnit.DAYS.between(start, end)`.

## 8. Duration biểu diễn thời lượng cố định

Khi yêu cầu là đúng 30 ngày elapsed time, có thể dùng Duration:

```java
Duration thirtyDays = Duration.ofDays(30);
Instant start = Instant.parse("2024-02-01T00:00:00Z");
Instant end = start.plus(thirtyDays);

System.out.println(thirtyDays); // PT720H
System.out.println(end);        // 2024-03-02T00:00:00Z
```

Đây là mã minh họa cần `java.time.Duration` và `java.time.Instant`. Duration 30 ngày là 720 giờ cố định trong mô hình elapsed time.

Lựa chọn theo yêu cầu:

- Đúng 720 giờ: `Duration.ofHours(720)`.
- Năm lịch kế tiếp: `plusYears(1)`.
- Tháng lịch kế tiếp: `plusMonths(1)` hoặc `Period.ofMonths(1)`.
- Timeout 15 phút: `Duration.ofMinutes(15)`.
- Gia hạn hợp đồng một tháng: Period, cùng chính sách ngày cuối tháng được xác định rõ.

## 9. Ngày lịch và DST

`Duration.ofDays(1)` là 24 giờ. `ZonedDateTime.plusDays(1)` tiến sang ngày lịch tiếp theo tại vùng và có thể cách instant ban đầu 23 hoặc 25 giờ khi có DST.

Chương trình đầy đủ **DstCalendarDayDemo.java**:

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DstCalendarDayDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZonedDateTime start =
                LocalDate.of(2024, 3, 31).atStartOfDay(paris);
        ZonedDateTime nextDay = start.plusDays(1);
        ZonedDateTime after24Hours = start.plus(Duration.ofDays(1));

        System.out.println("start = " + start);
        System.out.println("calendarNextDay = " + nextDay);
        System.out.println("after24Hours = " + after24Hours);
        System.out.println("elapsedHours = "
                + Duration.between(start, nextDay).toHours());
    }
}
```

Biên dịch và chạy:

```bash
javac DstCalendarDayDemo.java
java DstCalendarDayDemo
```

Kết quả theo quy tắc Paris ngày 31/03/2024:

```text
start = 2024-03-31T00:00+01:00[Europe/Paris]
calendarNextDay = 2024-04-01T00:00+02:00[Europe/Paris]
after24Hours = 2024-04-01T01:00+02:00[Europe/Paris]
elapsedHours = 23
```

Từ đầu ngày 31/3 đến đầu ngày 1/4 ở Paris chỉ có 23 giờ elapsed. Cộng Duration 24 giờ tới 01:00. Nếu thao tác theo ngày địa phương, giữ `ZoneId` và dùng phép toán lịch; offset cố định không chứa đầy đủ quy tắc DST.

## 10. Chọn API theo bài toán

| Câu hỏi | API | Ý nghĩa |
| --- | --- | --- |
| Bao nhiêu ngày lịch giữa hai ngày? | `ChronoUnit.DAYS.between(a, b)` | Chênh lệch ngày lịch |
| Thêm một tháng? | `date.plusMonths(1)` | Di chuyển trên lịch |
| Thêm đúng 90 phút vào instant? | `instant.plus(Duration.ofMinutes(90))` | Dịch chuyển elapsed time |
| Bao nhiêu giờ đã trôi giữa hai instant? | `Duration.between(a, b)` | Thời lượng |
| Cùng giờ vào ngày lịch kế tiếp? | `zoned.plusDays(1)` | Áp dụng quy tắc vùng |
| Đầu ngày tại vùng? | `date.atStartOfDay(zone).toInstant()` | Ranh giới lịch thành instant |

Không dùng Duration cho tháng lịch vì Duration không mang thành phần tháng. Với hai `LocalDate`, tính chênh lệch ngày bằng `ChronoUnit.DAYS.between`; với hai instant, dùng Duration để đo thời gian đã trôi qua.

## 11. Tránh mã hết hạn sai ngữ nghĩa

Phép tính sau tạo mốc sau 30 ngày cố định:

```java
Instant expiry = created.plusSeconds(30L * 24 * 60 * 60);
```

Nó không có nghĩa “một tháng sau”. Nếu ngày tạo là 31/1/2024, cộng 30 ngày có thể đi đến 1/3 trong khi cộng một tháng lịch đưa ngày tới 29/2.

Nếu hạn được quy định theo ngày lịch và giờ địa phương, cần định nghĩa cả ngày, giờ và ZoneId:

```java
LocalDate dueDate = LocalDate.of(2024, 1, 31).plusMonths(1);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime deadline = dueDate.atTime(23, 59).atZone(zone);
Instant deadlineInstant = deadline.toInstant();
```

Đây là mã minh họa cần `LocalDate`, `ZoneId`, `ZonedDateTime` và `Instant`. Không tự gán UTC khi yêu cầu thực sự nói đến giờ địa phương.

## 12. Chu kỳ định kỳ và ngày cuối tháng

Cộng dồn từ ngày 31 có thể làm đổi ngày gốc sau tháng đầu:

```java
LocalDate date = LocalDate.of(2024, 1, 31);
date = date.plusMonths(1); // 2024-02-29
date = date.plusMonths(1); // 2024-03-29
```

Nếu nghiệp vụ là ngày cuối tháng, hãy biểu diễn đúng quy tắc:

```java
LocalDate januaryEnd = LocalDate.of(2024, 1, 1)
        .with(TemporalAdjusters.lastDayOfMonth());
LocalDate februaryEnd = LocalDate.of(2024, 2, 1)
        .with(TemporalAdjusters.lastDayOfMonth());

System.out.println(januaryEnd);  // 2024-01-31
System.out.println(februaryEnd); // 2024-02-29
```

Mã này cần `import java.time.temporal.TemporalAdjusters;`. Lịch thanh toán cần xác định rõ quy tắc cho ngày 29/30/31, ngày 29/2, cuối tuần và ngày nghỉ. Không mặc định cộng tháng đơn giản giải quyết mọi chính sách.

## 13. Chuyển Period thành elapsed time

Chỉ khi có điểm bắt đầu và bối cảnh lịch thích hợp mới có thể tính độ dài cụ thể của một Period.

```java
LocalDate start = LocalDate.of(2024, 2, 1);
LocalDate end = start.plus(Period.ofMonths(1));

System.out.println(end); // 2024-03-01
System.out.println(ChronoUnit.DAYS.between(start, end)); // 29
```

Đoạn minh họa cần `LocalDate`, `Period` và `ChronoUnit`. Trong ví dụ này một tháng cụ thể dài 29 ngày. Ngày bắt đầu khác có thể cho số ngày khác.

Nếu cần thời lượng giữa ngày-giờ trong vùng, hãy gắn ZoneId rồi tính hiệu giữa hai mốc:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
ZonedDateTime start = LocalDate.of(2024, 3, 1).atStartOfDay(paris);
ZonedDateTime end = start.plusMonths(1);
Duration elapsed = Duration.between(start, end);
System.out.println(elapsed.toHours());
```

Đây là mã minh họa với các import tương ứng. Tổng giờ phụ thuộc quy tắc offset trong khoảng đó. Không có phép chuyển Period thành giây độc lập ngày bắt đầu và múi giờ.

## 14. Lỗi thường gặp

| Sai lầm | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| Một tháng = 30 ngày | Sai với tháng 28/29/31 ngày | `Period.ofMonths(1)` hoặc `plusMonths(1)` |
| Một năm = 365 ngày | Bỏ qua năm nhuận | `Period.ofYears(1)` hoặc `plusYears(1)` |
| Dùng Duration cho tháng lịch | Sai ngữ nghĩa | Tách lịch với elapsed time |
| Duration.ofDays(1) là một ngày địa phương | DST có thể làm ngày dài 23/25 giờ | `ZonedDateTime.plusDays(1)` |
| Dùng Period.getDays() làm tổng số ngày | Chỉ lấy thành phần ngày | `ChronoUnit.DAYS.between(a, b)` |
| Cộng dồn ngày 31 mà không quy định | Ngày có thể co về 29/30 | Xác định quy tắc cuối tháng |
| Chỉ lưu LocalDateTime cho thời điểm tuyệt đối | Thiếu offset và ZoneId | Chọn Instant/OffsetDateTime/ZonedDateTime |

## 15. Bài tập tự kiểm tra

**Câu 1.** `LocalDate.of(2024, 2, 1).plusMonths(1)` là ngày nào?

**Đáp án:** `2024-03-01`.

**Câu 2.** Từ 1/2/2024, cộng 30 ngày là ngày nào?

**Đáp án:** `2024-03-02`.

**Câu 3.** Duration.ofDays(1) có luôn tương đương ZonedDateTime.plusDays(1) không?

**Đáp án:** Không. Duration là 24 giờ cố định; ngày lịch chịu ảnh hưởng quy tắc vùng và DST.

**Câu 4.** `LocalDate.of(2024, 2, 29).plusYears(1)` cho ngày nào?

**Đáp án:** `2025-02-28` theo quy tắc điều chỉnh lịch của Java.

**Câu 5.** Vì sao Period.ofMonths(1) không có số giây cố định?

**Đáp án:** Độ dài phụ thuộc ngày bắt đầu và tháng đích; trong bối cảnh vùng còn phụ thuộc quy tắc múi giờ.

**Câu 6.** Muốn đo elapsed time giữa hai Instant, dùng API nào?

**Đáp án:** `Duration.between(startInstant, endInstant)`.

**Câu 7.** Muốn tới ngày lịch kế tiếp tại Paris thì dùng gì?

**Đáp án:** `ZonedDateTime.plusDays(1)` với ZoneId `Europe/Paris`.

**Ghi nhớ:** Không quy đổi tháng/năm lịch thành số giây cố định. Dùng Period và phép toán lịch cho tháng/năm; dùng Duration cho thời lượng đã trôi. Khi có múi giờ, phân biệt “ngày lịch kế tiếp” với “sau đúng N giờ”, đặc biệt quanh DST.