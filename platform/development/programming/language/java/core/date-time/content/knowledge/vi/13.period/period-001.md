# `Period` biểu diễn lượng thời gian theo năm, tháng và ngày lịch

`java.time.Period` biểu diễn **một lượng thời gian theo lịch** bằng ba thành phần: năm, tháng và ngày. Nó hữu ích khi nghiệp vụ nói “thêm một tháng”, “trừ hai năm” hoặc “sau 3 tháng 5 ngày”, bởi những đơn vị này phụ thuộc lịch và không tương đương với một số giây cố định.

Khác với `Duration`, được biểu diễn theo giây và nano giây, `Period` không lưu tổng số ngày hay số giây chung. `Period.ofMonths(1)` là một tháng lịch, chứ không phải luôn 30 ngày; `Period.ofDays(1)` là một ngày lịch, chứ không phải luôn 24 giờ khi áp dụng với vùng có DST.

## 1. Cấu trúc và cách tạo `Period`

Một `Period` có ba thành phần số nguyên:

- **Years** — số năm.
- **Months** — số tháng.
- **Days** — số ngày.

Có thể tạo qua các factory:

```java
import java.time.Period;

Period years = Period.ofYears(2);
Period months = Period.ofMonths(3);
Period days = Period.ofDays(10);
Period combined = Period.of(1, 2, 10);

System.out.println(years);    // P2Y
System.out.println(months);   // P3M
System.out.println(days);     // P10D
System.out.println(combined); // P1Y2M10D
```

`Period.of(years, months, days)` nhận ba thành phần độc lập. `P1Y2M10D` là biểu diễn theo ISO-8601: chữ `P` bắt đầu phần thời lượng, `Y` là năm, `M` ở vị trí này là tháng, `D` là ngày.

Các factory chính:

| Phương thức | Ý nghĩa |
| --- | --- |
| `Period.ofYears(n)` | Tạo lượng (n) năm |
| `Period.ofMonths(n)` | Tạo lượng (n) tháng |
| `Period.ofWeeks(n)` | Tạo lượng (7n) ngày |
| `Period.ofDays(n)` | Tạo lượng (n) ngày |
| `Period.of(y, m, d)` | Tạo ba thành phần năm, tháng, ngày |
| `Period.ZERO` | Lượng thời gian bằng không |

Các factory chấp nhận số âm. Ví dụ `Period.ofMonths(-2)` biểu diễn trừ hai tháng khi áp dụng vào ngày. Giá trị `Period` bất biến; các phép toán trả về một `Period` khác và không sửa instance hiện có.

## 2. Vì sao một tháng không bằng số ngày cố định?

Độ dài tháng phụ thuộc năm và tháng cụ thể:

| Tháng | Số ngày |
| --- | ---: |
| Tháng 1 | 31 |
| Tháng 2 năm thường | 28 |
| Tháng 2 năm nhuận | 29 |
| Tháng 4, 6, 9, 11 | 30 |
| Tháng 3, 5, 7, 8, 10, 12 | 31 |

Vì vậy, `Period.ofMonths(1)` không thể chuyển thành “30 ngày” một cách chính xác cho mọi ngày bắt đầu. Ví dụ:

```java
import java.time.LocalDate;
import java.time.Period;

LocalDate start = LocalDate.of(2024, 1, 31);

System.out.println(start.plus(Period.ofMonths(1)));
// 2024-02-29

System.out.println(start.plusDays(30));
// 2024-03-01
```

Trong năm nhuận 2024, cộng một tháng vào ngày 31/1 đưa tới ngày cuối tháng 2, còn cộng 30 ngày đưa tới 1/3. Đây là hai yêu cầu nghiệp vụ khác nhau.

### Cộng một tháng khi ngày đích không tồn tại

Khi cộng tháng hoặc năm vào một ngày mà ngày-tháng đích không hợp lệ, các kiểu ngày giờ của `java.time` điều chỉnh về ngày hợp lệ gần nhất trong tháng đích. Ví dụ:

```java
LocalDate jan31 = LocalDate.of(2025, 1, 31);
LocalDate feb = jan31.plus(Period.ofMonths(1));
System.out.println(feb); // 2025-02-28

LocalDate leapDay = LocalDate.of(2024, 2, 29);
System.out.println(leapDay.plus(Period.ofYears(1)));
// 2025-02-28
```

Không có ngày 29/2 trong năm 2025, nên phép cộng năm cho kết quả 28/2/2025. Đây là quy tắc điều chỉnh lịch của `LocalDate`; nếu nghiệp vụ cần quy tắc khác (ví dụ ngày cuối tháng, ngày làm việc tiếp theo, hoặc giữ ngày 29 nếu có), cần mã hóa quy tắc riêng và kiểm thử rõ.

## 3. Đọc các thành phần của `Period`

`Period` cung cấp getter cho từng thành phần:

```java
Period p = Period.of(2, 14, 40);

System.out.println(p.getYears());  // 2
System.out.println(p.getMonths()); // 14
System.out.println(p.getDays());   // 40
System.out.println(p);             // P2Y14M40D
```

Các getter trả lại **thành phần được lưu**, không tự chuẩn hóa tháng thành năm hoặc ngày thành tháng. Do đó, `getMonths()` có thể trả 14; `getDays()` có thể trả 40. Điều này hợp lệ bởi một `Period` duy trì các thành phần riêng biệt.

### `normalized()` chuẩn hóa năm và tháng

`normalized()` chuyển tổng phần tháng thành năm và tháng trong khoảng chuẩn, nhưng **không quy đổi ngày thành tháng**, vì số ngày trong tháng phụ thuộc lịch:

```java
Period p = Period.of(2, 14, 40);

System.out.println(p.normalized()); // P3Y2M40D
```

Phép toán này không thay đổi `p`; nó trả `Period` chuẩn hóa mới. Phần `40D` vẫn giữ nguyên. Không mong `normalized()` trả một lượng có số ngày tổng duy nhất hoặc đổi thành `Duration`.

**Quan trọng:** `Period.ofMonths(12)` và `Period.ofYears(1)` áp dụng vào ngày lịch thường cho kết quả tương đương trong nhiều trường hợp, nhưng các giá trị `Period` không nhất thiết bằng nhau theo `equals()`:

```java
System.out.println(Period.ofMonths(12).equals(Period.ofYears(1)));
// false

System.out.println(Period.ofMonths(12).normalized());
// P1Y
System.out.println(Period.ofMonths(12).normalized()
        .equals(Period.ofYears(1))); // true
```

Nếu cần so sánh biểu diễn đã chuẩn hóa của phần năm/tháng, dùng `normalized()`. Nếu cần so sánh ý nghĩa sau khi áp dụng lên một ngày cụ thể, hãy áp dụng lên ngày và so sánh kết quả; ngày bắt đầu có thể ảnh hưởng cách lượng thời gian được diễn giải.

## 4. Áp dụng `Period` lên ngày và giờ

Với `LocalDate`, `plus(Period)` và `minus(Period)` là cách phổ biến:

```java
LocalDate today = LocalDate.of(2026, 10, 24);
Period trial = Period.ofMonths(1).plusDays(14);

LocalDate endDate = today.plus(trial);
System.out.println(endDate); // 2026-12-08

LocalDate back = endDate.minus(trial);
System.out.println(back); // 2026-10-24
```

Ví dụ có thể đảo ngược ở mốc cụ thể này. Tuy nhiên, không phải mọi chuỗi phép cộng rồi trừ các thành phần riêng rẽ đều khôi phục ngày ban đầu do điều chỉnh ngày cuối tháng. Chẳng hạn:

```java
LocalDate jan31 = LocalDate.of(2025, 1, 31);
LocalDate feb28 = jan31.plusMonths(1);
LocalDate back = feb28.minusMonths(1);

System.out.println(feb28); // 2025-02-28
System.out.println(back);  // 2025-01-28
```

Sau khi chuyển 31/1 sang 28/2, thông tin “ngày ban đầu là 31” không nằm trong giá trị 28/2; trừ một tháng trở lại cho ngày 28/1. Nếu cần quy tắc “ngày cuối tháng” xuyên suốt, hãy lưu rõ đó là quy tắc nghiệp vụ, không mong `Period` tự ghi nhớ ngày bắt đầu.

### Áp dụng lên `LocalDateTime` hoặc `ZonedDateTime`

`Period` có thể được cộng vào nhiều kiểu thuộc hệ thống `java.time` hỗ trợ phép toán lịch, gồm `LocalDate`, `LocalDateTime`, và `ZonedDateTime`. Kết quả phụ thuộc kiểu nhận:

- Với `LocalDate`, chỉ các trường lịch ngày thay đổi.
- Với `LocalDateTime`, trường ngày giờ địa phương được tính lại nhưng kiểu này không có zone để xác định instant.
- Với `ZonedDateTime`, phép cộng ngày/tháng/năm hoạt động theo trục ngày giờ địa phương; sau đó vùng thời gian phân giải offset và DST tại ngày đích.

```java
ZonedDateTime meeting = ZonedDateTime.of(
        2024, 3, 9, 9, 0, 0, 0,
        ZoneId.of("America/New_York"));

System.out.println(meeting.plus(Period.ofDays(1)));
// 2024-03-10T09:00-04:00[America/New_York]
```

Ở ví dụ này, giờ họp tiếp tục là 09:00 giờ địa phương. Khoảng thời gian thực giữa hai instant là 23 giờ do DST mùa xuân. Nếu yêu cầu là “sau đúng 24 giờ”, hãy dùng `Duration.ofHours(24)`, không dùng `Period.ofDays(1)`.

## 5. Phân biệt `Period` và `Duration`

Hai lớp đều có thể diễn đạt “một lượng thời gian”, nhưng đơn vị nền tảng khác nhau:

| Đặc điểm | `Period` | `Duration` |
| --- | --- | --- |
| Thành phần | Năm, tháng, ngày | Giây và nano giây |
| Cách hiểu | Lượng theo lịch | Lượng thời gian dựa trên giây |
| `ofDays(1)` nghĩa là | Một ngày lịch | Chính xác 86.400 giây |
| Có tháng/năm | Có | Không |
| Số ngày cố định sang giây | Không thể quy đổi chung cho mọi ngày | Có: 1 ngày = 86.400 giây |
| Phù hợp với | Hạn thanh toán theo tháng, tuổi, kỳ lịch, ngày kỷ niệm | Timeout, TTL 24 giờ, đo khoảng đã trôi |

Ví dụ qua DST mùa xuân ở New York:

```java
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0,
        ZoneId.of("America/New_York"));

ZonedDateTime byPeriod = start.plus(Period.ofDays(1));
ZonedDateTime byDuration = start.plus(Duration.ofDays(1));

System.out.println(byPeriod);
// 2024-03-10T12:00-04:00[America/New_York]

System.out.println(byDuration);
// 2024-03-10T13:00-04:00[America/New_York]
```

Mốc `Period` là trưa ngày lịch kế tiếp; mốc `Duration` là đúng 86.400 giây sau, tương ứng 13:00. Cả hai đều hợp lệ, nhưng cần chọn theo ý định.

Đừng dùng `Period.getDays()` để tính tổng số ngày trong toàn bộ period. Ví dụ `Period.of(1, 2, 3).getDays()` trả 3, không phải tổng số ngày trong 1 năm 2 tháng 3 ngày. Không thể quy đổi phần năm và tháng sang tổng ngày duy nhất nếu chưa chọn ngày bắt đầu và lịch áp dụng.

## 6. Tạo `Period` từ hai ngày

`Period.between(startDate, endDate)` tính khoảng cách năm/tháng/ngày giữa hai `LocalDate`. Thành phần được phân rã theo lịch, không phải tổng số ngày:

```java
LocalDate start = LocalDate.of(2024, 1, 31);
LocalDate end = LocalDate.of(2024, 3, 2);

Period p = Period.between(start, end);

System.out.println(p);             // P1M2D
System.out.println(p.getYears());  // 0
System.out.println(p.getMonths()); // 1
System.out.println(p.getDays());   // 2
System.out.println(start.plus(p).equals(end)); // true
```

Với ngày theo thứ tự ngược, `Period.between` tạo kết quả âm theo quy tắc API:

```java
Period reverse = Period.between(
        LocalDate.of(2024, 3, 2),
        LocalDate.of(2024, 1, 31));

System.out.println(reverse); // P-1M-2D
```

Không đọc giá trị âm này như một phép toán số học đơn giản trên tổng ngày; nó là thành phần lịch theo điểm bắt đầu và kết thúc. Nếu cần tổng số ngày trôi qua giữa hai ngày, dùng `ChronoUnit.DAYS.between(start, end)` thay vì cộng ba getter.

```java
long elapsedDays = ChronoUnit.DAYS.between(start, end);
```

(Cần `import java.time.temporal.ChronoUnit;`.) `ChronoUnit.DAYS.between` trả số ngày theo lịch giữa hai ngày, phù hợp khi chỉ cần tổng ngày chênh lệch thay vì năm/tháng/ngày.

## 7. Parse và format `Period`

`Period.parse(String)` đọc chuỗi ISO-8601, chẳng hạn:

```java
Period p1 = Period.parse("P2Y3M4D");
Period p2 = Period.parse("P6M");
Period p3 = Period.parse("P10D");
Period negative = Period.parse("P-1Y-2M-3D");

System.out.println(p1);       // P2Y3M4D
System.out.println(p2);       // P6M
System.out.println(p3);       // P10D
System.out.println(negative); // P-1Y-2M-3D
```

`Period.toString()` tạo biểu diễn ISO của ba thành phần. `P1Y2M10D` không chứa ngày bắt đầu, timezone hoặc instant; chỉ biểu thị lượng lịch. Không nhầm chuỗi period với timestamp `2026-10-24T09:00:00Z`.

Parser cũng hỗ trợ lượng tuần như `P2W`; factory `Period.ofWeeks(2)` chuyển thành 14 ngày. `Period.parse` có thể ném `DateTimeParseException` khi cú pháp không hợp lệ. Khi nhận input từ API, cần validate và xử lý lỗi, thay vì mặc định mọi chuỗi đều là period hợp lệ.

## 8. Phép toán với `Period`

Các phương thức thường dùng:

| Phương thức | Kết quả |
| --- | --- |
| `plus(other)` | Cộng từng thành phần tương ứng |
| `minus(other)` | Trừ từng thành phần |
| `multipliedBy(n)` | Nhân từng thành phần |
| `negated()` | Đổi dấu từng thành phần |
| `normalized()` | Chuẩn hóa tổng năm/tháng, giữ phần ngày |
| `isZero()` | Kiểm tra tất cả thành phần bằng 0 |
| `isNegative()` | Kiểm tra giá trị có được xem là âm theo hợp đồng API |

Ví dụ:

```java
Period base = Period.of(1, 2, 3);

System.out.println(base.plus(Period.ofMonths(2)));
// P1Y4M3D

System.out.println(base.minus(Period.ofDays(5)));
// P1Y2M-2D

System.out.println(base.multipliedBy(2));
// P2Y4M6D

System.out.println(base.negated());
// P-1Y-2M-3D

System.out.println(Period.ZERO.isZero()); // true
```

Các phép toán tác động lên thành phần năm/tháng/ngày, không tự cộng trừ trên một ngày cụ thể. Khi áp dụng period có thành phần dấu khác nhau (ví dụ năm dương nhưng ngày âm), kết quả có thể khó diễn giải bằng mắt; ưu tiên xây dựng period theo quy tắc rõ ràng và thử trên ngày bắt đầu thực tế.

### Dùng `withDays`, `withMonths`, `withYears`

Nếu cần thay một thành phần:

```java
Period p = Period.of(1, 2, 3);

System.out.println(p.withDays(10));   // P1Y2M10D
System.out.println(p.withMonths(6));  // P1Y6M3D
System.out.println(p.withYears(4));   // P4Y2M3D
System.out.println(p);               // P1Y2M3D
```

Các phương thức này trả giá trị mới, không thay đổi `p`. Hãy phân biệt “thay thành phần tháng thành 6” với “cộng thêm 6 tháng”: `withMonths(6)` đặt thành phần, còn `plusMonths(6)` cộng lượng sáu tháng.

## 9. Lưu ý về dấu âm, chuẩn hóa và so sánh

`Period` không bắt buộc mọi thành phần cùng dấu. Ví dụ `Period.of(1, -2, 3)` vẫn có thể được tạo. `isNegative()` và `isZero()` không phải phép so sánh tổng số ngày thông thường, vì period không có một tổng số ngày độc lập với ngày bắt đầu. Nếu yêu cầu so sánh hai period để quyết định “khoảng nào dài hơn”, không có cách chính xác chung khi một period chứa tháng/năm mà chưa biết mốc áp dụng.

Ví dụ không thể nói `P1M` lúc nào cũng dài hơn `P28D`: từ 1/2/2025, cộng 1 tháng tới 1/3/2025 là 28 ngày; từ 1/1/2025, cộng 1 tháng tới 1/2/2025 là 31 ngày. Muốn so sánh khoảng theo kết quả thực, chọn ngày bắt đầu rõ ràng rồi áp dụng từng period và so sánh kết quả hoặc tính `Duration` khi có đầy đủ instant.

### Bất biến không có nghĩa là phép toán luôn đảo ngược

Các factory và phép toán trả ra `Period` bất biến, nhưng khi áp dụng lên ngày cuối tháng, một phép cộng tháng rồi trừ tháng có thể không phục hồi ngày ban đầu. Tính bất biến nói rằng đối tượng không bị sửa; nó không cam kết mọi phép toán lịch là phép nghịch đảo hoàn hảo.

Với các lượng lớn, phép nhân/cộng thành phần có thể vượt phạm vi `int` và ném `ArithmeticException`. Không ép kết quả thành số nhỏ hơn để tránh ngoại lệ mà không có quy tắc nghiệp vụ.

## 10. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`PeriodCalendarDemo.java`**:

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;

public class PeriodCalendarDemo {
    public static void main(String[] args) {
        Period p = Period.of(1, 14, 40);
        System.out.println("period = " + p);
        System.out.println("years = " + p.getYears());
        System.out.println("months = " + p.getMonths());
        System.out.println("days = " + p.getDays());
        System.out.println("normalized = " + p.normalized());

        LocalDate jan31Leap = LocalDate.of(2024, 1, 31);
        LocalDate jan31Normal = LocalDate.of(2025, 1, 31);
        System.out.println("2024 plus month = "
                + jan31Leap.plus(Period.ofMonths(1)));
        System.out.println("2025 plus month = "
                + jan31Normal.plus(Period.ofMonths(1)));
        System.out.println("2024 plus 30 days = "
                + jan31Leap.plusDays(30));

        LocalDate start = LocalDate.of(2024, 1, 31);
        LocalDate end = LocalDate.of(2024, 3, 2);
        Period between = Period.between(start, end);
        System.out.println("between = " + between);
        System.out.println("between days = "
                + ChronoUnit.DAYS.between(start, end));

        ZonedDateTime zoned = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0,
                ZoneId.of("America/New_York"));
        System.out.println("period one day = "
                + zoned.plus(Period.ofDays(1)));
        System.out.println("duration one day = "
                + zoned.plus(Duration.ofDays(1)));

        System.out.println("negative period = "
                + Period.parse("P-1Y-2M-3D"));
    }
}
```

Biên dịch và chạy:

```bash
javac PeriodCalendarDemo.java
java PeriodCalendarDemo
```

Kết quả dự kiến trên JDK 17+ với dữ liệu timezone chuẩn:

```text
period = P1Y14M40D
years = 1
months = 14
days = 40
normalized = P2Y2M40D
2024 plus month = 2024-02-29
2025 plus month = 2025-02-28
2024 plus 30 days = 2024-03-01
between = P1M2D
between days = 31
period one day = 2024-03-10T12:00-04:00[America/New_York]
duration one day = 2024-03-10T13:00-04:00[America/New_York]
negative period = P-1Y-2M-3D
```

Đầu ra minh họa `Period` giữ thành phần, `normalized()` chỉ chuyển tháng thành năm, phép cộng tháng điều chỉnh ngày cuối tháng, và khác biệt giữa ngày lịch với 86.400 giây. Mã dùng các mốc cố định nên không phụ thuộc thời gian hiện tại hay timezone mặc định.

## 11. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Xem `Period.ofMonths(1)` là 30 ngày | Tháng có độ dài khác nhau | Áp dụng vào ngày thực tế hoặc giữ quy tắc lịch |
| Nghĩ `Period.ofDays(1)` luôn bằng 24 giờ | Qua DST, ngày địa phương có thể 23/25 giờ | Dùng `Duration` cho thời lượng cố định |
| Gọi `getDays()` để lấy tổng ngày của period | Chỉ trả thành phần ngày, không quy đổi tháng/năm | Dùng `ChronoUnit.DAYS.between(start,end)` nếu cần số ngày giữa hai ngày |
| Nghĩ `normalized()` đổi cả ngày thành tháng | Tháng không có số ngày cố định | Chỉ năm/tháng được chuẩn hóa |
| Cộng tháng vào 31 rồi trừ tháng mong về 31 | Ngày ban đầu có thể đã được điều chỉnh về cuối tháng | Đặt quy tắc cuối tháng rõ ràng |
| Dùng `equals()` để khẳng định hai period cho cùng kết quả trên mọi ngày | Biểu diễn có thể khác dù áp dụng vào một ngày cho cùng kết quả | So sánh giá trị đã chuẩn hóa hoặc kết quả khi áp dụng lên mốc cụ thể |
| So sánh trực tiếp `P1M` và `P30D` để quyết định period nào lớn hơn | Không có một độ dài cố định cho tháng | Cần ngày bắt đầu và lịch cụ thể |
| Cho rằng `Period` chứa timezone | Nó chỉ giữ năm/tháng/ngày | Dùng `ZonedDateTime` hoặc thêm `ZoneId` ở tầng nghiệp vụ |
| Parse chuỗi tùy ý như period ISO | Cú pháp không hợp lệ có thể ném ngoại lệ | Validate và xử lý `DateTimeParseException` |
| Coi tính bất biến đồng nghĩa phép cộng trừ luôn đảo ngược | Quy tắc ngày cuối tháng làm mất thông tin ban đầu | Kiểm thử các ranh giới lịch, xác định quy tắc nghiệp vụ |

## 12. Chọn `Period` cho đúng yêu cầu

- **Kỳ thanh toán theo tháng:** lưu định nghĩa kỳ, ngày bắt đầu và quy tắc nếu ngày thanh toán không tồn tại (ví dụ ngày 31 khi tháng chỉ có 30 ngày).
- **Tuổi hoặc mốc kỷ niệm:** dùng năm/tháng/ngày theo lịch, không đổi tuổi thành tổng giây.
- **Gia hạn một tháng:** `date.plus(Period.ofMonths(1))`, với quy tắc rõ về ngày cuối tháng.
- **Hạn trong 30 × 24 giờ:** dùng `Instant.plus(Duration.ofHours(720))` hoặc một thời lượng xác định, không mặc định “1 tháng”.
- **Ngày làm việc:** `Period` không biết cuối tuần, ngày lễ hoặc lịch nghỉ công ty; cần business calendar ngoài.
- **So sánh hai khoảng theo số ngày:** dùng ngày bắt đầu/kết thúc cụ thể rồi `ChronoUnit.DAYS.between`, không suy từ getter của period.

### Câu hỏi tự kiểm tra

1. `Period.of(1, 14, 40).normalized()` trả gì?  
   → `P2Y2M40D`; tháng chuyển sang năm, ngày vẫn giữ nguyên.
2. `Period.ofMonths(1)` có luôn tương đương 30 ngày?  
   → Không. Phải xét ngày/tháng/năm bắt đầu.
3. `Period.ofDays(1)` khác `Duration.ofDays(1)` ở đâu?  
   → Một ngày lịch so với 86.400 giây cố định.
4. `Period.between(start, end).getDays()` có phải tổng ngày giữa hai mốc?  
   → Không; đó chỉ là thành phần ngày sau khi phân rã thành năm/tháng/ngày.
5. Tại sao 31/1 + 1 tháng rồi − 1 tháng có thể thành 28/1?  
   → Phép cộng đã điều chỉnh ngày 31 về ngày cuối tháng 2; thông tin “31” không được lưu trong ngày kết quả.
6. Vì sao không thể so sánh tổng độ dài của `P1M` và `P30D` trong mọi trường hợp?  
   → Tháng có số ngày khác nhau; cần một ngày bắt đầu cụ thể.
7. Khi yêu cầu là hết hạn đúng 24 giờ sau, nên dùng gì?  
   → `Duration` trên `Instant`/mốc thời điểm, không dùng `Period`.

### Tài liệu API chính thức

- [Java SE 17 — `Period`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html): factory, thành phần, chuẩn hóa, phép toán, parse và `between`.
- [Java SE 17 — `LocalDate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): hành vi cộng tháng/năm và điều chỉnh ngày cuối tháng.
- [Java SE 17 — `Duration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): lượng thời gian dựa trên giây.
- [Java SE 17 — `ChronoUnit`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/ChronoUnit.html): đo chênh lệch theo đơn vị thời gian.

**Ghi nhớ:** `Period` lưu lượng thời gian theo **năm, tháng và ngày lịch**, không lưu một tổng số giây/ngày cố định. Hãy chọn `Period` cho yêu cầu theo lịch và `Duration` cho thời lượng xác định; ngày bắt đầu, năm nhuận, ngày cuối tháng và quy tắc vùng quyết định kết quả thực tế.
