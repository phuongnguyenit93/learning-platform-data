# Đo khoảng cách giữa hai giá trị bằng between()

Trong Java, `Duration.between(start, end)` tạo một đối tượng `Duration` biểu diễn khoảng thời gian từ giá trị bắt đầu đến kết thúc. Phương thức thường dùng để tính thời gian giữa hai timestamp, thời gian xử lý request, khoảng chờ hoặc độ dài một ca làm đã xác định đủ ngày giờ.

~~~java
Instant start = Instant.parse("2025-04-09T09:00:00Z");
Instant end = Instant.parse("2025-04-09T10:30:15.250Z");
Duration elapsed = Duration.between(start, end);
// PT1H30M15.25S
~~~

Quy tắc cốt lõi là **kết quả = end − start**. Đổi thứ tự hai đối số có thể tạo Duration âm. Duration biểu diễn thời gian theo giây và phần nanosecond, không mô tả trực tiếp một tháng lịch hoặc ý nghĩa “cùng giờ ngày mai”.

## 1. Cú pháp và kiểu đầu vào

~~~java
Duration duration = Duration.between(start, end);
~~~

Hai đối số thường là các kiểu hỗ trợ đơn vị thời gian mà Duration cần, như `Instant`, `OffsetDateTime`, `ZonedDateTime`, `LocalDateTime`, `LocalTime` hoặc `OffsetTime`. Không phải mọi kiểu `Temporal` đều phù hợp; kiểu chỉ có ngày, không có phần thời gian cần thiết, có thể gây `UnsupportedTemporalTypeException`.

| Kiểu đầu vào | Ý nghĩa và giới hạn |
| --- | --- |
| `Instant` | Thời lượng giữa hai thời điểm tuyệt đối |
| `OffsetDateTime` | Hai mốc có ngày, giờ và offset xác định |
| `ZonedDateTime` | Thời lượng đã trôi qua theo quy tắc vùng, bao gồm chuyển giờ |
| `LocalDateTime` | Khoảng cách giữa giờ địa phương, không tự xác định thời lượng tuyệt đối |
| `LocalTime` | Chỉ so sánh giờ đồng hồ; không biết ngày nên có thể âm qua nửa đêm |
| `OffsetTime` | Có giờ và offset nhưng không có ngày, vì vậy cần cẩn thận ở ranh giới ngày |

Duration không sửa đối tượng đầu vào. Các kiểu `java.time` bất biến, phương thức trả về một đối tượng mới.

## 2. Đọc kết quả và chuyển đơn vị

~~~java
Instant start = Instant.parse("2025-04-09T09:00:00Z");
Instant end = Instant.parse("2025-04-09T10:30:15.250Z");
Duration duration = Duration.between(start, end);

System.out.println(duration);                 // PT1H30M15.25S
System.out.println(duration.getSeconds());    // 5415
System.out.println(duration.getNano());       // 250000000
System.out.println(duration.toMillis());      // 5415250
System.out.println(duration.toSeconds());     // 5415
System.out.println(duration.toMinutesPart()); // 30
System.out.println(duration.toSecondsPart()); // 15
~~~

`Duration.toString()` dùng biểu diễn ISO-8601; `PT1H30M15.25S` nghĩa là 1 giờ, 30 phút, 15,25 giây.

- `getSeconds()` trả thành phần giây nguyên đã chuẩn hóa, không phải giây trong một phút; nó có thể lớn hơn 59 hoặc âm.
- `getNano()` trả phần nanosecond còn lại trong giây theo biểu diễn chuẩn hóa.
- `toSeconds()`, `toMillis()` trả tổng số đơn vị nguyên và bỏ phần nhỏ hơn đơn vị đích.
- `toMinutesPart()` và `toSecondsPart()` trả phần dư sau khi chia thành đơn vị lớn hơn. Ví dụ tổng là 90 phút nhưng `toMinutesPart()` là 30 vì còn một giờ nguyên.

Độ phân giải nanosecond của kiểu không bảo đảm đồng hồ nguồn có độ chính xác tương đương.

## 3. Thứ tự start/end và Duration âm

~~~java
Instant earlier = Instant.parse("2025-04-09T09:00:00Z");
Instant later = Instant.parse("2025-04-09T10:30:15.250Z");

System.out.println(Duration.between(earlier, later));
// PT1H30M15.25S
System.out.println(Duration.between(later, earlier));
// PT-1H-30M-15.25S
~~~

Kết quả âm là hợp lệ khi end xảy ra trước start. Điều đó có thể báo hai đối số bị đảo hoặc thể hiện độ lệch từ một mốc sau về mốc trước. Không tự động dùng `abs()` để che dấu âm: cần quyết định theo nghiệp vụ xem đó là lỗi hay kết quả có hướng. `abs()` chỉ lấy độ lớn, làm mất thông tin trước/sau.

## 4. Chọn kiểu đúng để tính khoảng thời gian

### Instant: thời gian thực giữa hai sự kiện

~~~java
Instant requestStart = Instant.parse("2025-04-09T09:00:00Z");
Instant requestEnd = Instant.parse("2025-04-09T09:00:02.345Z");
Duration latency = Duration.between(requestStart, requestEnd);
// PT2.345S
~~~

Khi hai mốc đã là timestamp tuyệt đối, `Instant` là lựa chọn rõ ràng cho thời lượng giữa sự kiện. Để đo thời gian thực thi trong cùng JVM, `System.nanoTime()` thường phù hợp hơn vì đồng hồ đơn điệu dùng để đo khoảng, trong khi `Instant.now()` là đồng hồ dân sự có thể bị hiệu chỉnh.

### LocalDateTime: khoảng cách trên đồng hồ địa phương

~~~java
LocalDateTime start = LocalDateTime.of(2025, 4, 9, 9, 0);
LocalDateTime end = LocalDateTime.of(2025, 4, 9, 10, 0);
System.out.println(Duration.between(start, end)); // PT1H
~~~

Đây là khoảng cách giữa hai giá trị ngày giờ cục bộ. Vì `LocalDateTime` không có offset hay `ZoneId`, không thể khẳng định nó luôn là thời gian thực giữa hai sự kiện toàn cầu, đặc biệt gần thời điểm đổi DST.

### ZonedDateTime: ngày lịch có thể không dài 24 giờ

~~~java
ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime start =
        ZonedDateTime.of(2025, 3, 9, 0, 0, 0, 0, newYork);
ZonedDateTime end =
        ZonedDateTime.of(2025, 3, 10, 0, 0, 0, 0, newYork);
System.out.println(Duration.between(start, end)); // PT23H
~~~

Theo quy tắc DST hiện hành, ngày 09/03/2025 ở New York bỏ qua một giờ khi đồng hồ nhảy tiến. Hai nửa đêm cách nhau 23 giờ thực tế. Trái lại, `Duration.ofDays(1)` luôn bằng 24 giờ. Nếu mục tiêu là “cùng giờ ngày lịch tiếp theo”, hãy cộng ngày với `LocalDate` và xử lý cùng `ZoneId` thay vì cộng một Duration 24 giờ.

## 5. Duration, Period và ChronoUnit

`Duration` đo giây/nanosecond. `Period` diễn tả các thành phần lịch năm/tháng/ngày; `ChronoUnit` đếm số đơn vị giữa các giá trị mà kiểu đầu vào hỗ trợ.

| API | Câu hỏi phù hợp |
| --- | --- |
| `Duration.between(a,b)` | Bao nhiêu thời gian đã trôi qua? |
| `Period.between(dateA,dateB)` | Khoảng cách theo năm, tháng và ngày lịch là gì? |
| `ChronoUnit.DAYS.between(a,b)` | Có bao nhiêu ngày giữa hai ngày? |
| `Duration.ofDays(1)` | Khoảng thời gian cố định 24 giờ |

~~~java
LocalDate jan31 = LocalDate.of(2025, 1, 31);
LocalDate feb28 = LocalDate.of(2025, 2, 28);
System.out.println(Period.between(jan31, feb28)); // P28D
System.out.println(ChronoUnit.DAYS.between(jan31, feb28)); // 28
System.out.println(Duration.ofDays(1).toHours()); // 24
~~~

Không dùng Duration cho “một tháng” hoặc “một năm” vì số ngày của khoảng lịch thay đổi. Để đo khoảng cách giữa hai `LocalDate`, dùng `Period` hoặc `ChronoUnit.DAYS`; `LocalDate` không cung cấp các trường thời gian cần thiết cho Duration.

## 6. LocalTime qua nửa đêm

~~~java
LocalTime start = LocalTime.of(23, 30);
LocalTime end = LocalTime.of(1, 0);
System.out.println(Duration.between(start, end));
// PT-22H-30M
~~~

Java không tự biết end thuộc ngày kế tiếp. Nếu đây là ca làm 23:30 đến 01:00 ngày kế tiếp, hãy bổ sung ngày:

~~~java
LocalDateTime shiftStart = LocalDateTime.of(2025, 4, 9, 23, 30);
LocalDateTime shiftEnd = LocalDateTime.of(2025, 4, 10, 1, 0);
System.out.println(Duration.between(shiftStart, shiftEnd)); // PT1H30M
~~~

Nếu ca làm theo giờ địa phương của vùng có DST, hãy bổ sung `ZoneId` để tính thời lượng thực; hai giờ đồng hồ đơn lẻ không cho biết ngày hay quy tắc vùng.

## 7. Cắt bớt, phép toán và độ chính xác

~~~java
Duration duration = Duration.ofSeconds(125, 123_000_000);
System.out.println(duration.toMinutes()); // 2
System.out.println(duration.toSeconds()); // 125
System.out.println(duration.toMillis()); // 125123
System.out.println(duration.truncatedTo(ChronoUnit.MINUTES)); // PT2M
~~~

`truncatedTo(ChronoUnit.MINUTES)` bỏ phần nhỏ hơn phút, không làm tròn lên. Nếu cần làm tròn, phải quy định rõ làm tròn gần nhất, luôn lên hay luôn xuống, và xử lý số âm nhất quán. `toMillis()` mất độ chính xác dưới mili giây; chuyển đổi các thời lượng rất lớn có thể ném `ArithmeticException` khi vượt phạm vi kiểu số kết quả.

Duration bất biến; các phép toán trả đối tượng mới:

~~~java
Duration wait = Duration.ofSeconds(10);
System.out.println(wait.multipliedBy(2)); // PT20S
System.out.println(wait.dividedBy(2));    // PT5S
System.out.println(Duration.ofHours(2).plusMinutes(15)); // PT2H15M
~~~

## 8. Ví dụ Java 17+ hoàn chỉnh

Lưu mã thành `DurationBetweenDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;

public class DurationBetweenDemo {
    public static void main(String[] args) {
        Instant start = Instant.parse("2025-04-09T09:00:00Z");
        Instant end = Instant.parse("2025-04-09T10:30:15.250Z");
        Duration duration = Duration.between(start, end);

        System.out.println("duration=" + duration);
        System.out.println("seconds=" + duration.getSeconds());
        System.out.println("nanos=" + duration.getNano());
        System.out.println("totalMillis=" + duration.toMillis());
        System.out.println("totalSeconds=" + duration.toSeconds());
        System.out.println("minutesPart=" + duration.toMinutesPart());
        System.out.println("secondsPart=" + duration.toSecondsPart());
        System.out.println("negative=" + Duration.between(end, start));
        System.out.println("plusDayHours=" + Duration.ofDays(1).toHours());

        LocalDate jan31 = LocalDate.of(2025, 1, 31);
        LocalDate feb28 = LocalDate.of(2025, 2, 28);
        System.out.println("period=" + Period.between(jan31, feb28));
        System.out.println("days=" + ChronoUnit.DAYS.between(jan31, feb28));

        ZoneId ny = ZoneId.of("America/New_York");
        ZonedDateTime springStart =
                ZonedDateTime.of(2025, 3, 9, 0, 0, 0, 0, ny);
        ZonedDateTime springEnd =
                ZonedDateTime.of(2025, 3, 10, 0, 0, 0, 0, ny);
        System.out.println("dstElapsed="
                + Duration.between(springStart, springEnd));

        System.out.println("div=" + Duration.ofSeconds(125).dividedBy(2));
        System.out.println("trunc="
                + Duration.ofSeconds(125, 123_000_000)
                        .truncatedTo(ChronoUnit.MINUTES));

        LocalDateTime localStart = LocalDateTime.of(2025, 4, 9, 9, 0);
        LocalDateTime localEnd = LocalDateTime.of(2025, 4, 9, 10, 0);
        System.out.println("betweenLocalDateTime="
                + Duration.between(localStart, localEnd));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac DurationBetweenDemo.java
java DurationBetweenDemo
~~~

Đầu ra với dữ liệu cố định:

~~~text
duration=PT1H30M15.25S
seconds=5415
nanos=250000000
totalMillis=5415250
totalSeconds=5415
minutesPart=30
secondsPart=15
negative=PT-1H-30M-15.25S
plusDayHours=24
period=P28D
days=28
dstElapsed=PT23H
div=PT1M2.5S
trunc=PT2M
betweenLocalDateTime=PT1H
~~~

## 9. Lỗi thường gặp

| Sai lầm | Cách xử lý |
| --- | --- |
| Đảo `start` và `end` khiến Duration âm | Kiểm tra thứ tự; chỉ lấy trị tuyệt đối nếu nghiệp vụ yêu cầu |
| Dùng `getSeconds()` như giây trong phút | Dùng `toSecondsPart()` để lấy thành phần giây |
| Dùng `toMillis()` nhưng cần độ chính xác nano giây | Giữ Duration hoặc dùng đơn vị đủ chính xác |
| Coi `Duration.ofDays(1)` là ngày lịch tiếp theo trong zone DST | Tính ngày bằng `LocalDate` và vùng bằng `ZoneId` |
| Dùng `LocalTime` tính ca làm qua nửa đêm | Dùng `LocalDateTime` có ngày bắt đầu và kết thúc |
| Dùng Duration cho tháng/năm lịch | Chọn `Period` hoặc `ChronoUnit` |
| Tính thời lượng thực từ `LocalDateTime` chưa có zone | Xác định offset/zone theo nguồn dữ liệu trước |
| Coi khả năng biểu diễn nanosecond là độ chính xác đồng hồ | Phân biệt độ phân giải kiểu và chất lượng nguồn thời gian |

## 10. Tự kiểm tra

**Câu 1.** `Duration.between(09:00Z, 10:30:15.250Z)` bằng bao nhiêu?

**Đáp án:** `PT1H30M15.25S`, tức 5.415,25 giây.

**Câu 2.** Vì sao đảo thứ tự đối số có thể làm Duration âm?

**Đáp án:** Phép tính là `end − start`, nên đảo thứ tự thì đổi dấu.

**Câu 3.** `Duration.ofDays(1).toHours()` trả bao nhiêu?

**Đáp án:** 24 giờ cố định, không phải độ dài của bất kỳ ngày lịch nào trong một vùng DST.

**Câu 4.** Khoảng từ 31/01/2025 đến 28/02/2025 nên dùng gì cho ngày lịch?

**Đáp án:** `Period` hoặc `ChronoUnit.DAYS.between`, vì hai đầu là ngày không có thời gian trong ngày.

**Câu 5.** Hai nửa đêm New York giữa ngày bắt đầu DST tháng 03/2025 cách nhau bao nhiêu thời gian thực?

**Đáp án:** `PT23H` theo quy tắc múi giờ trong ví dụ.

**Câu 6.** Hai giá trị `LocalTime` 23:30 và 01:00 có tự cho biết ca làm dài 90 phút không?

**Đáp án:** Không; thiếu ngày. Hãy bổ sung ngày và tính bằng `LocalDateTime`.

**Ghi nhớ:** `Duration.between(start, end)` đo thời lượng **end trừ start** theo giây và nanosecond. Chọn đúng kiểu đầu vào, kiểm tra dấu và độ chính xác, đồng thời phân biệt thời lượng cố định với khoảng cách theo lịch.