# Duration, Period và phép tính khoảng thời gian

## 1. Hai khái niệm thời gian khác nhau

Trong Java 27, cụm từ **“một ngày”** không luôn có cùng ý nghĩa. Một tác vụ có thể cần chờ chính xác 24 giờ; một cuộc hẹn có thể cần lặp lại lúc 09:00 ngày hôm sau theo giờ địa phương; một hợp đồng có thể hết hạn sau một tháng lịch. Những yêu cầu đó phải được mô hình hóa khác nhau.

- **Duration** là lượng thời gian dựa trên **giây và nano giây**, dùng cho thời gian thực đã trôi qua, timeout, thời điểm hết hạn và chênh lệch giữa hai timestamp.
- **Period** là lượng thời gian dựa trên **năm, tháng và ngày lịch ISO**, dùng cho tuổi, hạn theo ngày, gia hạn hằng tháng và lịch lặp lại.
- **ChronoUnit** hỗ trợ tính số đơn vị hoàn chỉnh giữa hai giá trị thời gian, ví dụ số ngày lịch hoặc số giờ thực.

Hai lớp **java.time.Duration** và **java.time.Period** là những kiểu giá trị **immutable** và **thread-safe**, vẫn là các API chính thức, hiện hành của Java 27. Không cần sử dụng các cơ chế date/time cũ hoặc preview.

~~~mermaid
flowchart TD
    A["Yêu cầu tính khoảng thời gian"] --> B{"Ý nghĩa của khoảng cách?"}
    B -->|"Số giây/nano giây thực tế"| D["Duration"]
    B -->|"Năm, tháng, ngày theo lịch"| P["Period"]
    B -->|"Đếm số ngày trên lịch"| C["ChronoUnit.DAYS + LocalDate"]
    D --> I["Instant / ZonedDateTime"]
    P --> L["LocalDate / ZonedDateTime với ZoneId"]
~~~

**Nguyên tắc:** Chọn kiểu theo hợp đồng nghiệp vụ, không thay Duration và Period cho nhau vì cả hai đều có phương thức **ofDays(1)**.

## 2. Các kiểu điểm thời gian có liên quan

Trước khi tính khoảng cách, phải biết hai đầu mốc thuộc loại dữ liệu nào.

| Kiểu | Thông tin được biểu diễn | Ví dụ ứng dụng |
|---|---|---|
| **Instant** | Một thời điểm trên trục thời gian UTC | Timestamp sự kiện, thời điểm hết hạn |
| **LocalDate** | Ngày lịch, không có giờ và múi giờ | Ngày sinh, ngày giao hàng |
| **LocalTime** | Giờ trong ngày, không có ngày hay vùng | Giờ mở cửa |
| **LocalDateTime** | Ngày + giờ địa phương, không có offset/ZoneId | Lịch địa phương chưa xác định vùng |
| **OffsetDateTime** | Ngày giờ có UTC offset | Timestamp có offset từ API |
| **ZonedDateTime** | Ngày giờ có ZoneId và offset hợp lệ | Lịch hẹn theo múi giờ có DST |
| **Duration** | Lượng giây và nano giây | Timeout, elapsed time |
| **Period** | Số năm/tháng/ngày lịch | Tuổi, kỳ hạn theo tháng |

~~~java
import java.time.*;

Instant event = Instant.parse("2026-11-27T10:00:00Z");
LocalDate dueDate = LocalDate.of(2026, 12, 1);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime appointment = ZonedDateTime.of(
    2026, 12, 1, 9, 0, 0, 0, zone
);

Duration timeout = Duration.ofSeconds(3);
Period billingCycle = Period.ofMonths(1);
~~~

**Instant** biểu diễn một điểm xác định trên trục thời gian. **LocalDateTime** không tự xác định được một Instant: cần chọn offset hoặc ZoneId và xử lý các trường hợp đồng hồ địa phương thay đổi.

## 3. Tạo Duration từ các đơn vị chính xác

**Duration** sử dụng cặp giá trị giây (**long**) và phần nano giây (**int**, từ 0 đến 999.999.999). Thời lượng có thể dương, bằng 0 hoặc âm.

~~~java
import java.time.Duration;

Duration seconds = Duration.ofSeconds(45);
Duration millis = Duration.ofMillis(250);
Duration minutes = Duration.ofMinutes(30);
Duration hours = Duration.ofHours(2);
Duration days = Duration.ofDays(1);
Duration nanos = Duration.ofNanos(500);

System.out.println(seconds); // PT45S
System.out.println(minutes); // PT30M
System.out.println(hours);   // PT2H
System.out.println(days);    // PT24H
~~~

Một ngày trong **Duration.ofDays(1)** luôn bằng **86.400 giây**, tức 24 giờ chuẩn, **không** dựa trên độ dài thực của một ngày lịch ở từng múi giờ.

Có thể ghép thời lượng:

~~~java
Duration timeout = Duration.ofSeconds(2).plusMillis(500);

System.out.println(timeout);           // PT2.5S
System.out.println(timeout.toMillis()); // 2500
~~~

Các phương thức **plus**, **minus**, **multipliedBy**, **dividedBy** trả về Duration mới, không sửa đối tượng cũ.

## 4. Định dạng Duration và parse chuỗi

**Duration.parse** nhận chuỗi thời lượng theo biểu diễn hỗ trợ của ISO-8601:

~~~java
Duration value = Duration.parse("PT1H30M15S");

System.out.println(value);              // PT1H30M15S
System.out.println(value.getSeconds()); // 5415
System.out.println(value.toMinutes());  // 90
~~~

Trong **PT1H30M15S**, chữ **P** bắt đầu ký hiệu khoảng thời gian, **T** bắt đầu phần thời gian; các ký hiệu **H**, **M**, **S** chỉ giờ, phút, giây.

~~~java
Duration a = Duration.parse("PT0.25S");
Duration b = Duration.parse("P1DT3H");

System.out.println(a.toMillis()); // 250
System.out.println(b.toHours());  // 27
~~~

Chữ **M** trong phần thời gian sau T của Duration nghĩa là **minutes**; còn **M** ở Period nghĩa là **months**. Một tháng không có số giây cố định để tạo một Duration tương đương.

Đầu vào sai định dạng có thể ném **DateTimeParseException**. Với cấu hình từ bên ngoài, luôn kiểm tra giới hạn và chính sách chấp nhận giá trị âm, zero hoặc quá lớn.

## 5. Duration.between đo thời gian thực giữa hai Instant

Với timestamp, ưu tiên dùng **Instant** để tính chênh lệch chính xác:

~~~java
import java.time.Duration;
import java.time.Instant;

Instant started = Instant.parse("2026-11-27T08:00:00Z");
Instant finished = Instant.parse("2026-11-27T09:20:15Z");

Duration elapsed = Duration.between(started, finished);

System.out.println(elapsed);           // PT1H20M15S
System.out.println(elapsed.toSeconds()); // 4815
System.out.println(elapsed.toMinutes()); // 80
~~~

**Duration.between(start, end)** có hướng. Nếu đổi thứ tự:

~~~java
Duration reverse = Duration.between(finished, started);

System.out.println(reverse.isNegative()); // true
System.out.println(reverse.abs().toSeconds()); // 4815
~~~

**Đừng tự động lấy abs()** khi khoảng cách âm có thể báo sai thứ tự hai sự kiện. Nên kiểm tra bất biến như **end >= start** và phản hồi đúng khi dữ liệu không hợp lệ.

**Không dùng Duration.between trực tiếp trên hai LocalDate** vì LocalDate chỉ chứa ngày, không hỗ trợ đơn vị giây được Duration yêu cầu. Nếu cần chênh lệch ngày lịch, sử dụng **Period.between** hoặc **ChronoUnit.DAYS.between**.

## 6. Duration.toHours và toHoursPart khác nhau

Các phương thức **toDays**, **toHours**, **toMinutes**, **toSeconds**, **toMillis** cho giá trị ở **đơn vị tổng cộng**. Những phương thức kết thúc bằng **Part** cho thành phần của thời lượng theo biểu diễn ngày/giờ/phút/giây.

~~~java
Duration total = Duration.ofHours(26)
    .plusMinutes(7)
    .plusSeconds(9)
    .plusMillis(250);

System.out.println(total.toHours());      // 26
System.out.println(total.toMinutes());    // 1567
System.out.println(total.toDays());       // 1

System.out.println(total.toDaysPart());    // 1
System.out.println(total.toHoursPart());   // 2
System.out.println(total.toMinutesPart()); // 7
System.out.println(total.toSecondsPart()); // 9
System.out.println(total.toMillisPart());  // 250
~~~

Với Duration âm, mô hình giây và nano giây được chuẩn hóa theo quy tắc không hiển nhiên nếu tự tách số:

~~~java
Duration negativeHalfSecond = Duration.ofMillis(-500);

System.out.println(negativeHalfSecond.getSeconds()); // -1
System.out.println(negativeHalfSecond.getNano());    // 500000000
System.out.println(negativeHalfSecond.toMillis());   // -500
~~~

Không chỉ lấy **getSeconds()** rồi bỏ **getNano()** khi cần độ chính xác cao. Các phép chuyển tổng **toNanos()** hoặc **toMillis()** có thể ném **ArithmeticException** nếu kết quả vượt giới hạn long, dù bản thân Duration vẫn hợp lệ.

## 7. Duration là lựa chọn đúng cho timeout và giới hạn chờ

Một phương thức nhận **Duration timeout** diễn đạt đơn vị rõ hơn **long timeout**, vì tham số long không nói đó là giây hay mili giây.

~~~java
import java.time.Duration;
import java.util.Objects;

record RetryPolicy(Duration initialDelay, Duration maxDelay) {
    RetryPolicy {
        Objects.requireNonNull(initialDelay, "initialDelay");
        Objects.requireNonNull(maxDelay, "maxDelay");

        if (initialDelay.isNegative()
                || initialDelay.isZero()
                || maxDelay.compareTo(initialDelay) < 0) {
            throw new IllegalArgumentException("invalid retry policy");
        }
    }
}

RetryPolicy policy = new RetryPolicy(
    Duration.ofMillis(200),
    Duration.ofSeconds(5)
);
~~~

Hợp đồng vẫn cần xác định:

1. Duration.ZERO có hợp lệ hay không? Nếu hợp lệ, có nghĩa không chờ hay chờ vô hạn?
2. Có chấp nhận Duration âm không?
3. API đích có hỗ trợ nano giây hay chỉ đến mili giây?
4. Timeout có hủy tác vụ hay chỉ ngừng chờ kết quả?
5. Khi retry, thao tác đã thực hiện thành công nhưng mất phản hồi thì sao?

Một Duration dương nhưng nhỏ hơn một mili giây có thể thành 0 khi chuyển sang số nguyên mili giây. Không được tùy tiện truyền 0 tới API có hợp đồng “chờ mãi” nếu ý định ban đầu là “chờ rất ngắn”.

## 8. Period dùng năm, tháng và ngày lịch

**Period** mô tả lượng thời gian theo ba thành phần **years**, **months**, **days** của lịch ISO-8601:

~~~java
import java.time.Period;

Period threeDays = Period.ofDays(3);
Period twoWeeks = Period.ofWeeks(2);
Period oneMonth = Period.ofMonths(1);
Period oneYear = Period.ofYears(1);
Period combined = Period.of(1, 2, 10);

System.out.println(threeDays); // P3D
System.out.println(twoWeeks);  // P14D
System.out.println(oneMonth);  // P1M
System.out.println(oneYear);   // P1Y
System.out.println(combined);  // P1Y2M10D
~~~

**Period.ofWeeks(2)** lưu thành **14 ngày**, vì Period không có trường weeks riêng.

Không thể chuyển **Period.ofMonths(1)** thành một Duration cố định nếu chưa chọn mốc lịch. Tháng 2 có thể chứa 28 hoặc 29 ngày; tháng 3 có 31 ngày. Tương tự, năm lịch có thể dài 365 hoặc 366 ngày.

## 9. Parse Period và giá trị âm

**Period.parse** và **Period.toString** cung cấp biểu diễn năm/tháng/ngày:

~~~java
Period parsed = Period.parse("P1Y2M15D");

System.out.println(parsed.getYears());  // 1
System.out.println(parsed.getMonths()); // 2
System.out.println(parsed.getDays());   // 15
System.out.println(parsed);             // P1Y2M15D
~~~

| Chuỗi | Kiểu | Ý nghĩa |
|---|---|---|
| **PT30M** | Duration | 30 phút |
| **PT24H** | Duration | 24 giờ |
| **P1D** | Period | 1 ngày lịch |
| **P2M** | Period | 2 tháng lịch |
| **P1Y3M** | Period | 1 năm 3 tháng lịch |

Period có thể mang thành phần âm:

~~~java
Period backward = Period.ofMonths(-2);

System.out.println(backward);             // P-2M
System.out.println(backward.isNegative()); // true
~~~

Các thành phần còn có thể mang dấu khác nhau nếu tạo trực tiếp, ví dụ **Period.of(1, -2, 0)**. Vì vậy, một API nghiệp vụ chấp nhận Period nên quy định rõ tổ hợp dấu nào được phép, thay vì chỉ kiểm tra tổng số tháng.

## 10. Period.between: tuổi và khoảng cách lịch

**Period.between(LocalDate start, LocalDate end)** tính một khoảng thời gian theo năm/tháng/ngày, không dùng số giây đã trôi qua.

~~~java
import java.time.LocalDate;
import java.time.Period;

LocalDate born = LocalDate.of(2000, 4, 15);
LocalDate reference = LocalDate.of(2026, 11, 27);

Period age = Period.between(born, reference);

System.out.println(age.getYears());  // 26
System.out.println(age.getMonths()); // 7
System.out.println(age.getDays());   // 12
~~~

Phương thức loại bỏ những tháng hoàn chỉnh rồi tính phần ngày còn lại; không thể lấy số ngày rồi chia 30 để thu được kết quả tương đương.

Nếu end trước start, Period mang dấu âm theo hướng tính:

~~~java
Period negative = Period.between(
    LocalDate.of(2026, 12, 1),
    LocalDate.of(2026, 11, 1)
);

System.out.println(negative); // P-1M
~~~

Để so sánh hai ngày theo thứ tự, dùng **LocalDate.isBefore/isAfter**. Không so độ lớn hai Period tùy ý bằng riêng **getMonths** hoặc **getDays**.

## 11. Tổng số ngày lịch: ChronoUnit.DAYS.between

Khi chỉ cần **bao nhiêu ngày lịch giữa hai ngày**, dùng **ChronoUnit.DAYS.between**:

~~~java
import java.time.LocalDate;
import java.time.Period;
import java.time.temporal.ChronoUnit;

LocalDate from = LocalDate.of(2024, 2, 28);
LocalDate to = LocalDate.of(2024, 3, 1);

System.out.println(ChronoUnit.DAYS.between(from, to)); // 2
System.out.println(Period.between(from, to));          // P2D
~~~

Với nhiều tháng:

~~~java
LocalDate from = LocalDate.of(2024, 1, 15);
LocalDate to = LocalDate.of(2024, 3, 18);

System.out.println(Period.between(from, to));          // P2M3D
System.out.println(ChronoUnit.DAYS.between(from, to)); // 63
~~~

Hai phép tính có cách diễn đạt khác nhau: một bên trả **cấu trúc lịch năm/tháng/ngày**, bên còn lại trả **số ngày lịch tổng cộng**.

Nhiều nghiệp vụ lưu trú, phân trang lịch hoặc hợp đồng dùng khoảng nửa mở **[start, end)**: tính ngày đầu, không tính ngày kết thúc. Nếu nghiệp vụ cần tính cả hai ngày, phải định nghĩa và thực hiện quy tắc riêng; không tự ý cộng 1 trong mọi tình huống.

**DAYS.between(LocalDate, LocalDate) không nói được hai thời điểm cách nhau bao nhiêu giờ thực tế**. Việc đó cần ngày/giờ và ZoneId để xác định Instant.

## 12. Cộng trừ Period trên LocalDate

Một Period có thể cộng trừ trực tiếp với LocalDate:

~~~java
LocalDate issued = LocalDate.of(2026, 11, 27);

LocalDate expiry = issued.plus(Period.ofMonths(3));
LocalDate reminder = expiry.minus(Period.ofDays(7));

System.out.println(expiry);   // 2027-02-27
System.out.println(reminder); // 2027-02-20
~~~

Khi chỉ dùng một đơn vị, **plusMonths**, **plusYears** và **plusDays** thường dễ đọc hơn:

~~~java
LocalDate nextMonth = issued.plusMonths(1);
LocalDate nextYear = issued.plusYears(1);
LocalDate nextWeek = issued.plusWeeks(1);
~~~

Các ngày cuối tháng được xử lý theo lịch:

~~~java
LocalDate jan31 = LocalDate.of(2024, 1, 31);

System.out.println(jan31.plusMonths(1)); // 2024-02-29
System.out.println(jan31.plusYears(1));  // 2025-01-31
~~~

Nếu tháng đích không có ngày tương ứng, phép cộng tháng/năm điều chỉnh sang ngày hợp lệ cuối tháng theo quy tắc LocalDate. Đó là lý do “thêm một tháng” **khác** “thêm 30 ngày”.

## 13. Bẫy trôi ngày khi cộng tháng lặp lại

Một chu kỳ hằng tháng không nên tự động lấy ngày mới nhất làm mốc nếu yêu cầu nghiệp vụ là **giữ ngày neo ban đầu**.

~~~java
LocalDate anchor = LocalDate.of(2024, 1, 31);

LocalDate step1 = anchor.plusMonths(1); // 2024-02-29
LocalDate step2 = step1.plusMonths(1);  // 2024-03-29

LocalDate direct = anchor.plusMonths(2); // 2024-03-31

System.out.println(step2.equals(direct)); // false
~~~

Hai chính sách đều có thể hợp lệ:

- **Theo kết quả kỳ trước:** 31/01 → 29/02 → 29/03.
- **Giữ ngày neo 31:** 31/01 → 29/02 → 31/03.

Nếu cần chính sách thứ hai, tính từ ngày neo và chỉ số kỳ:

~~~java
import java.time.LocalDate;
import java.time.YearMonth;

static LocalDate monthlyAnniversary(LocalDate anchor, long months) {
    YearMonth target = YearMonth.from(anchor).plusMonths(months);

    int day = Math.min(
        anchor.getDayOfMonth(),
        target.lengthOfMonth()
    );

    return target.atDay(day);
}
~~~

~~~java
LocalDate anchor = LocalDate.of(2024, 1, 31);

System.out.println(monthlyAnniversary(anchor, 1)); // 2024-02-29
System.out.println(monthlyAnniversary(anchor, 2)); // 2024-03-31
~~~

Với kỳ hạn tài chính, bảo hiểm hoặc lịch thu phí, hãy viết rõ chính sách cuối tháng, ngày nghỉ và ngày nhuận trong tài liệu nghiệp vụ.

## 14. Period.normalized không đổi ngày thành tháng

**Period.normalized()** chỉ điều chỉnh phần năm/tháng sao cho tháng có trị tuyệt đối nhỏ hơn 12; **days** được giữ nguyên.

~~~java
Period raw = Period.of(1, 15, 45);
Period normalized = raw.normalized();

System.out.println(raw);        // P1Y15M45D
System.out.println(normalized); // P2Y3M45D
~~~

~~~java
Period months = Period.ofMonths(15);

System.out.println(months);                // P15M
System.out.println(months.normalized());   // P1Y3M
System.out.println(months.toTotalMonths()); // 15
~~~

**toTotalMonths()** cộng năm × 12 + tháng và **bỏ qua thành phần ngày**. Không có phép chuyển tổng quát “45 ngày = 1 tháng 15 ngày” độc lập với ngày bắt đầu.

Cũng cần lưu ý cách so bằng **equals** của Period dựa trên các thành phần: Period biểu diễn 12 tháng có thể không equals một Period biểu diễn 1 năm trước khi chuẩn hóa.

## 15. DST: một ngày lịch có thể dài 23 hoặc 25 giờ

Một lý do chính để phân biệt Duration và Period là **daylight saving time (DST)**.

Ví dụ tại **America/New_York**, ngày **08/03/2026** đồng hồ nhảy từ 02:00 lên 03:00. Ngày lịch đó có **23 giờ thực tế**.

~~~java
import java.time.*;

ZoneId zone = ZoneId.of("America/New_York");

ZonedDateTime start = ZonedDateTime.of(
    2026, 3, 7, 12, 0, 0, 0, zone
);

ZonedDateTime calendarNext =
    start.plus(Period.ofDays(1));

ZonedDateTime elapsedNext =
    start.plus(Duration.ofDays(1));

System.out.println(calendarNext.toLocalTime()); // 12:00
System.out.println(elapsedNext.toLocalTime());  // 13:00

System.out.println(Duration.between(start, calendarNext).toHours());
// 23

System.out.println(Duration.between(start, elapsedNext).toHours());
// 24
~~~

| Phép cộng | Ý nghĩa | Kết quả |
|---|---|---|
| **plus(Period.ofDays(1))** | Sang ngày lịch tiếp theo, cố giữ giờ địa phương | 12:00 ngày 08/03; thực tế **23 giờ** trôi qua |
| **plus(Duration.ofDays(1))** | Thêm đúng 86.400 giây | 13:00 ngày 08/03; **24 giờ** trôi qua |

Tại lần đồng hồ lùi về giờ tiêu chuẩn trong mùa thu, một ngày lịch có thể kéo dài **25 giờ**.

**Asia/Ho_Chi_Minh** hiện không có DST, nhưng ứng dụng đa vùng không được giả định mọi ZoneId đều có ngày 24 giờ.

## 16. ZonedDateTime.plusDays và plusHours cũng có ngữ nghĩa khác nhau

Trên **ZonedDateTime**, phép **plusDays** làm việc trên **local timeline**; phép **plusHours** làm việc trên **instant timeline**.

~~~java
ZonedDateTime byDate = start.plusDays(1);
ZonedDateTime byHours = start.plusHours(24);

System.out.println(byDate.toLocalTime());  // 12:00
System.out.println(byHours.toLocalTime()); // 13:00
~~~

Tóm tắt:

- **plusDays / plusMonths / plusYears**: tính theo lịch địa phương và giải quyết thay đổi offset.
- **plusHours / plusMinutes / plusSeconds**: cộng lượng thời gian thực.
- **plus(Duration)**: cộng giây/nano giây theo thời lượng.
- **plus(Period)**: cộng năm/tháng/ngày lịch.

Chính kiểu temporal đích và đơn vị được chọn quyết định ngữ nghĩa. Không suy ra rằng cùng tên “day” trong mọi phương thức nghĩa là 24 giờ.

## 17. Gap và overlap: giờ địa phương không phải lúc nào cũng duy nhất

Khi chuyển **LocalDateTime** thành **ZonedDateTime**, có ba trường hợp:

1. **Normal:** một offset hợp lệ.
2. **Gap:** không có offset hợp lệ vì đồng hồ nhảy tới phía trước.
3. **Overlap:** hai offset hợp lệ vì đồng hồ lùi lại.

Ví dụ **01:30 ngày 01/11/2026** ở New York xuất hiện hai lần khi hết DST:

~~~java
ZoneId newYork = ZoneId.of("America/New_York");

LocalDateTime ambiguous = LocalDateTime.of(
    2026, 11, 1, 1, 30
);

ZonedDateTime earlier = ambiguous.atZone(newYork);
ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

System.out.println(
    earlier.toLocalTime().equals(later.toLocalTime())
); // true

System.out.println(earlier.getOffset()); // -04:00
System.out.println(later.getOffset());   // -05:00

System.out.println(Duration.between(earlier, later).toHours());
// 1
~~~

Dù cùng ghi **01:30**, hai đối tượng biểu diễn **hai Instant khác nhau**, cách nhau một giờ.

Trong **gap**, **LocalDateTime.atZone** thông thường điều chỉnh thời gian về phía sau điểm nhảy, tức tiến tới giờ địa phương hợp lệ tiếp theo. Với lịch hẹn quan trọng, nên xác định rõ hành vi cần áp dụng thay vì mặc nhiên chấp nhận mọi điều chỉnh.

**Instant** và offset hợp lệ phù hợp để ghi nhận sự kiện đã xảy ra. **LocalDate + LocalTime + ZoneId + quy tắc DST** phù hợp mô tả cuộc hẹn lặp lại theo đồng hồ địa phương.

## 18. Vì sao Duration.between trên LocalDateTime có thể gây hiểu nhầm?

~~~java
LocalDateTime begin = LocalDateTime.of(2026, 3, 7, 12, 0);
LocalDateTime end = LocalDateTime.of(2026, 3, 8, 12, 0);

System.out.println(Duration.between(begin, end).toHours()); // 24
~~~

Kết quả là 24 giờ trên **trục ngày-giờ địa phương không có offset**. Nhưng nếu hai giờ đó thuộc New York, thời gian thực đã trôi qua chỉ 23 giờ.

~~~java
ZoneId zone = ZoneId.of("America/New_York");

ZonedDateTime actualStart = begin.atZone(zone);
ZonedDateTime actualEnd = end.atZone(zone);

Duration actual = Duration.between(
    actualStart.toInstant(),
    actualEnd.toInstant()
);

System.out.println(actual.toHours()); // 23
~~~

**Không tự gắn timezone mặc định của máy** cho LocalDateTime được nhận từ một hệ thống khác. Phải dựa vào metadata, API contract hoặc cấu hình vùng đã biết để chọn ZoneId.

## 19. ChronoUnit.between: số đơn vị nguyên hoàn chỉnh

Đôi khi cần một số nguyên như “bao nhiêu ngày lịch” hoặc “bao nhiêu giờ đã hoàn thành” thay vì một Duration/Period.

~~~java
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;

LocalDate from = LocalDate.of(2026, 1, 1);
LocalDate to = LocalDate.of(2026, 2, 15);

System.out.println(ChronoUnit.DAYS.between(from, to));   // 45
System.out.println(ChronoUnit.WEEKS.between(from, to));  // 6
System.out.println(ChronoUnit.MONTHS.between(from, to)); // 1
~~~

**ChronoUnit.between** trả số đơn vị **hoàn chỉnh**, theo quy tắc của loại temporal được dùng.

~~~java
Instant first = Instant.parse("2026-11-27T10:00:00Z");
Instant second = Instant.parse("2026-11-27T11:59:59Z");

System.out.println(ChronoUnit.HOURS.between(first, second)); // 1
System.out.println(Duration.between(first, second)); // PT1H59M59S
~~~

Kết quả **1** giờ hoàn chỉnh không có nghĩa Duration chỉ dài một giờ.

Khi yêu cầu “tháng hoàn chỉnh”, quy tắc của **ChronoUnit.MONTHS.between(LocalDate, LocalDate)** cần được xem xét so với quy tắc hợp đồng riêng của ứng dụng, đặc biệt khi bắt đầu từ ngày 29, 30 hoặc 31.

## 20. Giá trị âm, zero, so sánh và overflow

Duration có thứ tự tự nhiên và các phép toán định hướng rõ:

~~~java
Duration a = Duration.ofMinutes(1);
Duration b = Duration.ofSeconds(90);

System.out.println(a.compareTo(b) < 0); // true
System.out.println(Duration.ZERO.isZero()); // true
System.out.println(b.minus(a)); // PT30S
~~~

**Period không có phép compareTo tổng quát** để so độ dài chính xác của các lượng năm/tháng/ngày. Ví dụ:

~~~java
Period oneMonth = Period.ofMonths(1);
Period thirtyDays = Period.ofDays(30);

// Không thể tự khẳng định Period nào dài hơn
// nếu chưa biết ngày bắt đầu.
~~~

Cả Duration lẫn Period có thể gặp **ArithmeticException** khi phép nhân/cộng hoặc chuyển đơn vị vượt phạm vi số nguyên. Các phép toán trên ngày/giờ cũng có thể ném **DateTimeException** nếu vượt giới hạn lịch.

Với đầu vào của người dùng, cần kiểm tra giá trị âm/zero, giới hạn tối đa, độ chính xác cho phép và lỗi parse rồi chuyển chúng thành lỗi nghiệp vụ rõ nghĩa ở ranh giới thích hợp.

## 21. Clock giúp kiểm thử không phụ thuộc giờ chạy thật

Để tính hạn theo thời điểm hiện tại, truyền **Clock** vào service thay vì gọi trực tiếp **Instant.now()** ở khắp nơi.

~~~java
import java.time.*;

Clock fixed = Clock.fixed(
    Instant.parse("2026-11-27T10:00:00Z"),
    ZoneOffset.UTC
);

System.out.println(Instant.now(fixed));
// 2026-11-27T10:00:00Z
~~~

Ví dụ service:

~~~java
final class ExpiryService {
    private final Clock clock;

    ExpiryService(Clock clock) {
        this.clock = java.util.Objects.requireNonNull(clock);
    }

    boolean isExpired(Instant deadline) {
        return !Instant.now(clock).isBefore(deadline);
    }
}
~~~

Kiểm thử:

~~~java
ExpiryService service = new ExpiryService(
    Clock.fixed(
        Instant.parse("2026-11-27T10:00:00Z"),
        ZoneOffset.UTC
    )
);

System.out.println(service.isExpired(
    Instant.parse("2026-11-27T09:59:59Z")
)); // true
~~~

**Clock.fixed** phù hợp tính “hiện tại”. Nếu cần **đo thời gian thực thi một đoạn code**, nên dùng bộ đếm thời gian đơn điệu như **System.nanoTime()**, không dùng hiệu giữa hai giá trị thời gian tường vốn có thể bị điều chỉnh.

~~~java
long startedNanos = System.nanoTime();

// Chạy thao tác cần đo.

long elapsedNanos = System.nanoTime() - startedNanos;
Duration processingTime = Duration.ofNanos(elapsedNanos);
~~~

Chỉ dùng **hiệu** hai lần nanoTime để đo elapsed time. Giá trị nanoTime tuyệt đối không phải timestamp và không được dùng thay Instant.

## 22. Chọn kiểu đúng trong các tình huống thường gặp

| Yêu cầu | Kiểu phù hợp | Lý do |
|---|---|---|
| Token hết hạn đúng 15 phút sau khi tạo | **Instant + Duration.ofMinutes(15)** | Deadline tuyệt đối |
| Timeout HTTP 3 giây | **Duration.ofSeconds(3)** | Giới hạn elapsed time |
| Nhắc việc lúc 09:00 mỗi ngày theo giờ địa phương | **LocalTime + ZoneId + lịch/Period** | Giữ giờ địa phương qua DST |
| Hợp đồng gia hạn mỗi tháng | **LocalDate/YearMonth + Period** | Tháng theo lịch |
| Tuổi tại một ngày tham chiếu | **Period.between(LocalDate, LocalDate)** | Năm/tháng/ngày |
| Số đêm lưu trú giữa hai ngày | **ChronoUnit.DAYS.between(LocalDate, LocalDate)** | Chênh lệch ngày lịch |
| Thời gian xử lý trong JVM | **System.nanoTime() → Duration** | Đo thời lượng thực thi |
| Chênh lệch giữa hai sự kiện đã ghi timestamp | **Duration.between(Instant, Instant)** | Giây và nano giây thực tế |

Một lịch chạy định kỳ cần lưu đủ thông tin về **ngày/giờ địa phương, múi giờ, chính sách DST và quy tắc ngày cuối tháng**. Một Duration duy nhất không thể biểu diễn đầy đủ những quy tắc đó.

## 23. Serialization và hợp đồng dữ liệu

**Duration.toString()** và **Period.toString()** tạo biểu diễn dạng chuỗi:

~~~java
Duration delay = Duration.ofMinutes(90);
Period cycle = Period.of(1, 2, 3);

System.out.println(delay); // PT1H30M
System.out.println(cycle); // P1Y2M3D

System.out.println(Duration.parse("PT1H30M").equals(delay)); // true
System.out.println(Period.parse("P1Y2M3D").equals(cycle));    // true
~~~

Chỉ nói “chuỗi ISO” vẫn chưa đủ để tạo một hợp đồng API tốt. Nên mô tả:

- Trường **retryDelay** dùng Duration, đơn vị thực, giới hạn từ 1 ms đến 30 giây.
- Trường **billingCycle** dùng Period, chấp nhận tháng/năm, không cho giá trị âm.
- Trường **eventAt** là Instant, không phải Duration.
- Trường **dailyReminder** cần giờ địa phương + ZoneId và chính sách DST.

Không lưu Period thành một số lượng giây cố định nếu thiếu ngày gốc; không lưu Duration thành một số nguyên không kèm đơn vị rồi để mỗi client tự đoán. Nếu chọn mili giây, chú ý khả năng mất phần nano giây và overflow.

## 24. Ví dụ độc lập: Duration, Period, cuối tháng và DST

Lưu mã vào tệp **TimeAmountsDemo.java** và chạy với JDK 27.

~~~java
import java.time.*;

public class TimeAmountsDemo {
    static LocalDate anniversary(LocalDate anchor, long months) {
        YearMonth target = YearMonth.from(anchor).plusMonths(months);
        int day = Math.min(
            anchor.getDayOfMonth(), target.lengthOfMonth()
        );
        return target.atDay(day);
    }

    public static void main(String[] args) {
        // Timeout kỹ thuật.
        Duration timeout = Duration.ofSeconds(2).plusMillis(500);
        System.out.println("timeout=" + timeout);
        System.out.println("timeoutMillis=" + timeout.toMillis());

        // Tuổi theo lịch.
        LocalDate born = LocalDate.of(2000, 4, 15);
        LocalDate reference = LocalDate.of(2026, 11, 27);
        Period age = Period.between(born, reference);

        System.out.println("ageYears=" + age.getYears());
        System.out.println("ageMonths=" + age.getMonths());
        System.out.println("ageDays=" + age.getDays());

        // Kỳ gia hạn giữ ngày neo.
        LocalDate anchor = LocalDate.of(2024, 1, 31);
        System.out.println("renewal1=" + anniversary(anchor, 1));
        System.out.println("renewal2=" + anniversary(anchor, 2));

        // Hai cách thêm "một ngày" qua DST.
        ZoneId zone = ZoneId.of("America/New_York");
        ZonedDateTime before = ZonedDateTime.of(
            2026, 3, 7, 12, 0, 0, 0, zone
        );

        ZonedDateTime byCalendar =
            before.plus(Period.ofDays(1));
        ZonedDateTime byDuration =
            before.plus(Duration.ofDays(1));

        System.out.println("calendarTime="
            + byCalendar.toLocalTime());
        System.out.println("elapsedTime="
            + byDuration.toLocalTime());

        System.out.println("calendarElapsedHours="
            + Duration.between(before, byCalendar).toHours());
        System.out.println("elapsedHours="
            + Duration.between(before, byDuration).toHours());

        // Clock cố định cho kiểm thử.
        Clock fixed = Clock.fixed(
            Instant.parse("2026-11-27T10:00:00Z"),
            ZoneOffset.UTC
        );

        Duration sinceEvent = Duration.between(
            Instant.parse("2026-11-27T09:59:10Z"),
            Instant.now(fixed)
        );

        System.out.println("secondsSinceEvent="
            + sinceEvent.toSeconds());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 TimeAmountsDemo.java
java TimeAmountsDemo
~~~

Kết quả dự kiến, khi tzdb chứa quy tắc DST New York năm 2026:

~~~text
timeout=PT2.5S
timeoutMillis=2500
ageYears=26
ageMonths=7
ageDays=12
renewal1=2024-02-29
renewal2=2024-03-31
calendarTime=12:00
elapsedTime=13:00
calendarElapsedHours=23
elapsedHours=24
secondsSinceEvent=50
~~~

Chương trình sử dụng mốc thời gian cố định để kết quả có thể dự đoán. Trong hệ thống thực tế, các bản cập nhật **tzdb** có thể thay đổi quy tắc giờ của một quốc gia trong tương lai; cần có chính sách cho lịch hẹn dài hạn.

## 25. Lỗi thiết kế thường gặp

| Sai lầm | Nguyên nhân | Cách sửa |
|---|---|---|
| Dùng Duration để biểu diễn “một tháng” | Số ngày mỗi tháng khác nhau | Dùng Period.ofMonths và ngày neo |
| Nhắc việc bị lệch một giờ qua DST | Dùng đúng 24 giờ thay cho ngày lịch tiếp theo | Lên lịch theo LocalTime + ZoneId |
| Dùng LocalDateTime để đo elapsed time thật | Thiếu offset/múi giờ | Chuyển thành Instant bằng quy tắc zone |
| Ngày gia hạn 31 thành 29 vĩnh viễn | Cộng lặp tháng trên kết quả đã bị điều chỉnh | Giữ anchor date |
| Xem số ngày lịch là số giờ/24 | DST có ngày 23 hoặc 25 giờ | Dùng Instant để đo giờ thực |
| **Duration.between(LocalDate, LocalDate)** không hoạt động | LocalDate không chứa đơn vị giây | Dùng Period hoặc DAYS.between |
| Hiểu **getSeconds()** là toàn bộ thời lượng | Duration còn nano giây | Dùng API tổng/part đúng mục tiêu |
| **toNanos()** tràn số | Kết quả vượt long | Giới hạn dữ liệu và xử lý ArithmeticException |
| **Period.normalized()** không đổi days | Số ngày mỗi tháng không cố định | Chỉ chuẩn hóa năm/tháng |
| Giờ địa phương nằm trong DST gap | Không có offset hợp lệ | Có chính sách điều chỉnh/từ chối |
| Một giờ địa phương ánh xạ hai Instant | DST overlap | Lưu offset hoặc Instant đúng |
| Unit test phụ thuộc giờ chạy | Gọi Instant.now() trực tiếp | Inject Clock.fixed |
| Đo runtime bằng đồng hồ hệ thống | Wall-clock có thể bị chỉnh | Dùng System.nanoTime() |
| Nhầm **P1M** với **PT1M** | M là tháng với Period, phút với Duration | Định nghĩa chính xác loại giá trị |
| Duration âm bị lấy trị tuyệt đối | Che lỗi thứ tự dữ liệu | Kiểm tra bất biến của hai mốc |

## 26. Bài tập thực hành

**Bài tập 1 — Duration và các đơn vị.** Tạo 2 giờ, 15 phút, 400 mili giây. In **toHours**, **toMinutes**, **toMillis**, **toHoursPart**, **toMinutesPart** và **toMillisPart**. Giải thích vì sao tổng số phút và phần phút hiển thị khác nhau.

**Bài tập 2 — Tuổi theo lịch.** Với ngày sinh 29/02/2004, tính Period đến ngày 28/02/2026 và 01/03/2026. So sánh với phép tính tuổi theo quy định nghiệp vụ cụ thể; không mặc định cùng một quy tắc đúng cho mọi pháp luật.

**Bài tập 3 — Trôi ngày cuối tháng.** Từ ngày 31/01/2024, tạo 6 kỳ gia hạn theo hai chính sách: cộng từng tháng từ kỳ trước và cộng theo chỉ số kỳ từ ngày neo. Ghi lại kết quả và giải thích sự khác biệt.

**Bài tập 4 — Chuyển đổi DST.** Tại New York, chọn 12:00 ngày 07/03/2026. So sánh **plusDays(1)**, **plusHours(24)**, **plus(Period.ofDays(1))** và **plus(Duration.ofDays(1))** về giờ địa phương và elapsed time.

**Bài tập 5 — Expiry với Clock.** Viết service nhận Clock và Duration TTL. Kiểm thử trường hợp chưa hết hạn, đúng thời điểm hết hạn và đã quá hạn với Clock.fixed.

**Bài tập 6 — Overlap.** Với 01:30 ngày 01/11/2026 tại America/New_York, tạo hai ZonedDateTime với hai offset hợp lệ. Chứng minh LocalDateTime như nhau nhưng Instant khác nhau một giờ.

**Bài tập 7 — Thiết kế giao thức.** Chọn kiểu dữ liệu và cách serialize cho: timeout 250 ms, lịch nhắc việc 08:30 mỗi ngày, gia hạn hằng tháng, hạn chót UTC và thời gian xử lý của một batch.

## 27. Checklist dùng Duration và Period trong Java 27

- [ ] Phân biệt **elapsed time** với **calendar time** ngay từ yêu cầu.
- [ ] Dùng **Duration** cho timeout, giây/nano giây và chênh lệch Instant.
- [ ] Dùng **Period** cho năm/tháng/ngày lịch ISO.
- [ ] Dùng **ChronoUnit.DAYS.between(LocalDate, LocalDate)** khi cần tổng số ngày lịch.
- [ ] Không giả định tháng luôn 30 ngày hoặc năm luôn 365 ngày.
- [ ] Không coi LocalDateTime là timestamp tuyệt đối khi chưa có vùng/offset.
- [ ] Dùng **ZoneId** cho lịch địa phương, xử lý DST gap và overlap theo chính sách.
- [ ] Phân biệt **Period.ofDays(1)** và **Duration.ofDays(1)** khi cộng với ZonedDateTime.
- [ ] Xác định quy tắc cho ngày 29, 30, 31 và năm nhuận.
- [ ] Lưu ngày neo cho lịch định kỳ nếu không muốn trôi ngày.
- [ ] Không nhầm **Duration.toMinutes()** với **toMinutesPart()**.
- [ ] Xử lý parse errors, overflow và giới hạn giá trị.
- [ ] Xác định Duration âm/zero có hợp lệ theo hợp đồng hay không.
- [ ] Dùng **Clock** được inject để kiểm thử code phụ thuộc giờ hiện tại.
- [ ] Dùng **System.nanoTime()** cho elapsed processing time.
- [ ] Kiểm thử cuối tháng, năm nhuận, DST và ranh giới đầu/cuối khoảng.
- [ ] Serialize Duration, Period và Instant bằng kiểu/định dạng/đơn vị rõ ràng.

**Kết luận:** Duration và Period không phải hai cách viết khác nhau của một lượng thời gian. **Duration** đo giây/nano giây đã trôi qua; **Period** biểu đạt năm/tháng/ngày theo lịch. Kết hợp đúng chúng với **Instant**, **LocalDate**, **ZonedDateTime**, **ZoneId** và **Clock** giúp ứng dụng Java 27 xử lý timeout, lịch định kỳ, ngày đến hạn và chuyển giờ mùa hè một cách chính xác, rõ nghĩa và kiểm thử được.

## Tài liệu tham khảo

- [Java SE 27 — Duration](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Duration.html): Duration, between, parse, số giây và nano giây.
- [Java SE 27 — Period](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Period.html): Period, normalized, giữa hai LocalDate và khác biệt với Duration.
- [Java SE 27 — ZonedDateTime](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/ZonedDateTime.html): local timeline, instant timeline, gap và overlap.
- [Java SE 27 — LocalDate](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/LocalDate.html): phép toán theo lịch, cuối tháng và năm nhuận.
- [Java SE 27 — Instant](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Instant.html): timestamp và trục thời gian.
- [Java SE 27 — Clock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Clock.html): nguồn thời gian có thể thay thế cho test.
- [Java SE 27 — ChronoUnit](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/ChronoUnit.html): đếm số đơn vị hoàn chỉnh.
