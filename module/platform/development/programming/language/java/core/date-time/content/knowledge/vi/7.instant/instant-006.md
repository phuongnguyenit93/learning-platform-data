# Cộng trừ khoảng thời gian và đơn vị được hỗ trợ trong Java `Instant`

Một đơn hàng được tạo lúc `2025-01-15T10:00:00Z` và sẽ hết hạn **sau 90 phút**. Hệ thống cần tính đúng **một mốc thời gian mới** trên dòng thời gian thực, không cần chọn múi giờ địa phương:

```java
Instant createdAt = Instant.parse("2025-01-15T10:00:00Z");
Instant expiresAt = createdAt.plus(Duration.ofMinutes(90));
// expiresAt = 2025-01-15T11:30:00Z
```

Đoạn này thuộc một phương thức Java, cần `import java.time.*;`. Trong Java 8+, `Instant` biểu diễn thời điểm tuyệt đối dưới dạng số giây tính từ epoch và phần nano giây. `Duration` biểu diễn một khoảng trôi thực. Các phép `plus(...)` và `minus(...)` dịch `Instant` theo khoảng trôi, trả **đối tượng mới** vì `Instant` bất biến.

Có ba câu hỏi khác nhau cần xác định trước khi chọn phép tính:

- **Sau đúng 90 phút hoặc 24 giờ?** Cộng `Duration` hoặc số lượng theo đơn vị được `Instant` hỗ trợ.
- **Cùng giờ địa phương vào ngày mai hoặc tháng sau?** Áp dụng quy tắc lịch trên `ZonedDateTime` ở `ZoneId` xác định, không mặc nhiên cộng một số giây cố định.
- **Khoảng thời gian giữa hai mốc là bao lâu?** Dùng `Duration.between(start, end)` hoặc `ChronoUnit.between(...)` để đo chênh lệch.

## 1. Mô hình `Instant` và ý nghĩa của cộng/trừ

Giá trị `Instant.parse("2025-01-15T10:00:00Z")` chỉ đến một thời điểm duy nhất. Ký hiệu `Z` cho biết chuỗi được biểu diễn theo UTC. Mọi nơi trên thế giới đều có thể diễn giải cùng mốc này, dù giờ địa phương khi hiển thị khác nhau.

```text
Mốc ban đầu:  2025-01-15T10:00:00Z
                   │
              +90 phút
                   ↓
Mốc mới:      2025-01-15T11:30:00Z
```

`Instant` có độ chính xác biểu diễn tới **nano giây**. Phép cộng/trừ trên `Instant` không tự xét DST, cuối tháng hoặc ngày làm việc. Nếu cộng “1 ngày” bằng `ChronoUnit.DAYS`, Java cộng **86.400 giây**, tức đúng 24 giờ; đây là một **ngày theo thời lượng**, không nhất thiết là một ngày lịch ở vùng có giờ mùa hè.

Mỗi phương thức `plus`/`minus` trả lại `Instant` mới:

```java
Instant start = Instant.parse("2025-01-15T10:00:00Z");
Instant later = start.plusSeconds(30);
// start vẫn là 2025-01-15T10:00:00Z
// later là 2025-01-15T10:00:30Z
```

Lệnh `start.plusSeconds(30);` không gán kết quả sẽ không làm thay đổi `start`.

## 2. Các phương thức cộng thời lượng

### Cộng trực tiếp giây, mili giây hoặc nano giây

`Instant` cung cấp các phương thức tiện lợi:

| Phương thức | Đơn vị | Ví dụ |
| --- | --- | --- |
| `plusSeconds(long seconds)` | Giây | `instant.plusSeconds(90)` thêm 1 phút 30 giây. |
| `plusMillis(long millis)` | Mili giây | `instant.plusMillis(1_500)` thêm 1,5 giây. |
| `plusNanos(long nanos)` | Nano giây | `instant.plusNanos(1_000_000)` thêm 1 mili giây. |

Quan hệ giữa đơn vị: 1 giây = 1.000 mili giây = 1.000.000 micro giây = 1.000.000.000 nano giây. Đừng truyền giá trị mili giây vào `plusNanos` mà không chuyển đổi.

Ví dụ:

```java
Instant base = Instant.parse("2025-01-15T10:00:00Z");

Instant a = base.plusSeconds(3_600); // 11:00:00Z
Instant b = base.plusMillis(1_500);  // 10:00:01.500Z
Instant c = base.plusNanos(1);       // 10:00:00.000000001Z
```

Đây là đoạn minh họa trong một phương thức, cần `import java.time.Instant;`. Giá trị tham số có thể âm, ví dụ `plusSeconds(-30)` tương đương trừ 30 giây, nhưng nên chọn `minusSeconds(30)` khi ý nghĩa là trừ để code dễ hiểu.

### Cộng một `Duration`

`Duration` là kiểu thích hợp khi khoảng trôi được tính toán, cấu hình hoặc truyền giữa các lớp:

```java
Duration retention = Duration.ofHours(2).plusMinutes(30);
Instant deadline = base.plus(retention);
// deadline = 2025-01-15T12:30:00Z
```

`plus(Duration)` áp dụng độ dài đã chứa trong `Duration`, vốn được lưu theo giây và nano giây. Một `Duration` có thể âm; cộng duration âm làm `Instant` lùi trên dòng thời gian. Khi nghiệp vụ cần khoảng cố định, truyền một `Duration` thường rõ ràng hơn các con số đơn vị không ghi chú.

### Cộng lượng và `TemporalUnit`

Overload tổng quát:

```java
Instant afterNinetyMinutes = base.plus(90, ChronoUnit.MINUTES);
Instant afterOneDay = base.plus(1, ChronoUnit.DAYS);
Instant afterMicrosecond = base.plus(1, ChronoUnit.MICROS);
```

Cần `import java.time.temporal.ChronoUnit;` cùng `import java.time.Instant;`. `TemporalUnit` là giao diện đơn vị; `ChronoUnit` là bộ enum đơn vị chuẩn của Java. **Không phải mọi đơn vị `ChronoUnit` đều được `Instant` hỗ trợ**. Cần kiểm tra nếu đơn vị đến từ người dùng hoặc cấu hình.

## 3. Các phép trừ tương ứng

`Instant` có những phương thức đối xứng:

| Cộng | Trừ | Ví dụ |
| --- | --- | --- |
| `plusSeconds(n)` | `minusSeconds(n)` | Trước mốc 10:00 đúng 30 giây: `minusSeconds(30)`. |
| `plusMillis(n)` | `minusMillis(n)` | Trước mốc 10:00 đúng 250 ms: `minusMillis(250)`. |
| `plusNanos(n)` | `minusNanos(n)` | Trừ một nano giây bằng `minusNanos(1)`. |
| `plus(duration)` | `minus(duration)` | Trừ `Duration.ofMinutes(10)`. |
| `plus(amount, unit)` | `minus(amount, unit)` | Trừ 2 giờ bằng `minus(2, ChronoUnit.HOURS)`. |

Ví dụ với `base = 2025-01-15T10:00:00Z`:

```java
Instant oneHourBefore = base.minusSeconds(3_600);
Instant twoHoursBefore = base.minus(2, ChronoUnit.HOURS);
Instant aQuarterSecondBefore = base.minusMillis(250);
Instant oneNanosecondBefore = base.minusNanos(1);
```

Kết quả lần lượt là `2025-01-15T09:00:00Z`, `2025-01-15T08:00:00Z`, `2025-01-15T09:59:59.750Z` và `2025-01-15T09:59:59.999999999Z`. Chú ý phép trừ 1 nano giây chuyển sang **giây trước** và có phần nano `999999999`; Java xử lý bước chuyển đó.

`minusSeconds(-30)` tương đương `plusSeconds(30)`. Đầu vào âm hợp lệ về mặt phép toán nhưng nên hạn chế nhầm dấu trong nghiệp vụ.

## 4. Các đơn vị `ChronoUnit` mà `Instant` hỗ trợ

Với các **đơn vị chuẩn `ChronoUnit`**, `Instant` hỗ trợ nhóm từ `NANOS` đến `DAYS` như sau:

| Đơn vị | Độ dài cố định | `Instant.plus(amount, unit)` |
| --- | --- | --- |
| `NANOS` | 1 nano giây | Được hỗ trợ |
| `MICROS` | 1 micro giây = 1.000 ns | Được hỗ trợ |
| `MILLIS` | 1 mili giây = 1.000.000 ns | Được hỗ trợ |
| `SECONDS` | 1 giây | Được hỗ trợ |
| `MINUTES` | 60 giây | Được hỗ trợ |
| `HOURS` | 3.600 giây | Được hỗ trợ |
| `HALF_DAYS` | 12 giờ | Được hỗ trợ |
| `DAYS` | 24 giờ = 86.400 giây | Được hỗ trợ |
| `WEEKS` | Tuần theo lịch | **Không được hỗ trợ trực tiếp** |
| `MONTHS` | Tháng theo lịch | **Không được hỗ trợ trực tiếp** |
| `YEARS` | Năm theo lịch | **Không được hỗ trợ trực tiếp** |
| `DECADES`, `CENTURIES`, `MILLENNIA` | Nhiều năm | Không được hỗ trợ trực tiếp |
| `ERAS`, `FOREVER` | Kỷ nguyên/vô hạn | Không được hỗ trợ trực tiếp |

Với enum tiêu chuẩn này, có thể kiểm tra:

```java
boolean supportsDays = base.isSupported(ChronoUnit.DAYS);       // true
boolean supportsMonths = base.isSupported(ChronoUnit.MONTHS);   // false
```

Gọi `base.plus(1, ChronoUnit.MONTHS)` hoặc `base.minus(1, ChronoUnit.WEEKS)` gây `UnsupportedTemporalTypeException`. `Instant` không có ngày tháng địa phương để diễn giải “tháng sau” theo lịch, nên không thể suy ra một thời điểm mới chỉ từ `MONTHS`.

**Tại sao `DAYS` được hỗ trợ?** `Instant` quy định đơn vị `DAYS` như **24 giờ cố định**, chứ không thực hiện phép cộng một ngày theo lịch vùng. Đối với **một tuần đúng 7 × 24 giờ**, dùng `Duration.ofDays(7)` hoặc `plus(7, ChronoUnit.DAYS)`; muốn “cùng giờ địa phương tuần tới” thì làm phép cộng lịch trên `ZonedDateTime` có vùng.

Lưu ý bảng nói về các enum `ChronoUnit` chuẩn; một kiểu `TemporalUnit` tự định nghĩa có thể có quy tắc tùy logic triển khai, nên không nên khẳng định mọi đơn vị bên ngoài `ChronoUnit` đều bị từ chối.

## 5. `Duration` và `Period`: khác nhau thế nào khi cộng lên `Instant`?

- `Duration` diễn đạt **thời lượng thực** theo giây và nano giây. `Duration.ofDays(1)` luôn là **86.400 giây**.
- `Period` diễn đạt **số năm, tháng, ngày lịch**, phù hợp với `LocalDate` hay `ZonedDateTime` trong những tình huống tính lịch. Một tháng có thể dài 28–31 ngày.

Một chi tiết dễ bỏ sót: `Instant.plus(Period.ofDays(1))` **có thể chạy được**, vì `Period` này chỉ áp dụng đơn vị `DAYS` mà `Instant` hỗ trợ. Nhưng `Instant.plus(Period.ofMonths(1))` **không chạy được**, vì `MONTHS` không được hỗ trợ. Điều đó không có nghĩa có thể dùng mọi `Period` như `Duration` trên `Instant`.

Để tránh mơ hồ, nếu ý nghĩa là **sau đúng N giây, phút, giờ hoặc 24 giờ**, chọn `Duration`. Nếu ý nghĩa là **cùng ngày tháng sau hoặc cùng giờ ngày hôm sau tại một vùng**, chọn phép cộng lịch sau khi đã có `ZoneId`. Không mặc định một tháng = 30 ngày.

## 6. Ví dụ Java 17+ hoàn chỉnh: cộng trừ và đơn vị hợp lệ

Tạo tệp **`InstantArithmeticDemo.java`**:

```java
import java.time.*;
import java.time.temporal.ChronoUnit;

public class InstantArithmeticDemo {
    public static void main(String[] args) {
        Instant start = Instant.parse("2025-01-15T10:00:00Z");
        Duration ninetyMinutes = Duration.ofMinutes(90);

        System.out.println("Start              : " + start);
        System.out.println("Plus 90 minutes    : " + start.plus(ninetyMinutes));
        System.out.println("Minus 2 hours      : "
                + start.minus(2, ChronoUnit.HOURS));
        System.out.println("Plus 1500 millis   : " + start.plusMillis(1500));
        System.out.println("Minus 1 nanosecond : " + start.minusNanos(1));
        System.out.println("Plus 1 day         : "
                + start.plus(1, ChronoUnit.DAYS));
        System.out.println("Plus 24 hours      : "
                + start.plus(Duration.ofHours(24)));
        System.out.println("Supported (days)   : "
                + start.isSupported(ChronoUnit.DAYS));
        System.out.println("Supported (months) : "
                + start.isSupported(ChronoUnit.MONTHS));
        System.out.println("Period of 1 day    : "
                + start.plus(Period.ofDays(1)));

        try {
            start.plus(1, ChronoUnit.MONTHS);
        } catch (java.time.temporal.UnsupportedTemporalTypeException e) {
            System.out.println(
                    "Plus month error   : UnsupportedTemporalTypeException"
            );
        }
        try {
            start.plus(Period.ofMonths(1));
        } catch (java.time.temporal.UnsupportedTemporalTypeException e) {
            System.out.println(
                    "Period month error : UnsupportedTemporalTypeException"
            );
        }
        System.out.println("Original           : " + start);
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac InstantArithmeticDemo.java
java InstantArithmeticDemo
```

Kết quả đã kiểm chứng bằng Java:

```text
Start              : 2025-01-15T10:00:00Z
Plus 90 minutes    : 2025-01-15T11:30:00Z
Minus 2 hours      : 2025-01-15T08:00:00Z
Plus 1500 millis   : 2025-01-15T10:00:01.500Z
Minus 1 nanosecond : 2025-01-15T09:59:59.999999999Z
Plus 1 day         : 2025-01-16T10:00:00Z
Plus 24 hours      : 2025-01-16T10:00:00Z
Supported (days)   : true
Supported (months) : false
Period of 1 day    : 2025-01-16T10:00:00Z
Plus month error   : UnsupportedTemporalTypeException
Period month error : UnsupportedTemporalTypeException
Original           : 2025-01-15T10:00:00Z
```

**Đọc kết quả:** Thêm 90 phút vào mốc 10:00 tạo 11:30. Trừ 2 giờ tạo 08:00. `plusMillis(1500)` tạo phần mili giây `.500` sau khi đi qua 1 giây. `minusNanos(1)` lùi một nano giây sang giây liền trước. `DAYS` tạo cùng kết quả với `Duration.ofHours(24)`. `MONTHS` bị từ chối, trong khi `Period.ofDays(1)` áp dụng được do chứa thành phần ngày. Cuối cùng `start` không đổi, chứng minh tính bất biến.

## 7. Tại sao cộng 1 `DAYS` trên `Instant` khác cộng 1 ngày theo lịch?

Giả sử người dùng đặt lịch vào **12:00 ngày 09/03/2024 ở New York**. Hôm sau, vùng này chuyển sang DST: độ lệch UTC chuyển từ `-05:00` sang `-04:00`. Khi đó:

- `Instant.plus(1, ChronoUnit.DAYS)` đi tới **24 giờ thực sau đó**, hiển thị **13:00 ngày 10/03** tại New York.
- `ZonedDateTime.plusDays(1)` đi tới **12:00 ngày 10/03 theo giờ địa phương**, chỉ cách mốc đầu **23 giờ thực**.

Muốn nhìn thấy sự khác biệt, tạo tệp **`InstantAcrossDstDemo.java`**:

```java
import java.time.*;
import java.time.temporal.ChronoUnit;

public class InstantAcrossDstDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZonedDateTime localStart =
                ZonedDateTime.of(2024, 3, 9, 12, 0, 0, 0, zone);
        Instant start = localStart.toInstant();

        Instant afterInstantDay =
                start.plus(1, ChronoUnit.DAYS);
        ZonedDateTime afterCalendarDay =
                localStart.plusDays(1);

        System.out.println("Local start         : " + localStart);
        System.out.println("Instant start       : " + start);
        System.out.println("Instant + 1 DAY     : " + afterInstantDay);
        System.out.println("Viewed in New York  : "
                + afterInstantDay.atZone(zone));
        System.out.println("Local + 1 calendar day: " + afterCalendarDay);
        System.out.println("Calendar day instant: "
                + afterCalendarDay.toInstant());
        System.out.println("Hours to local +1d : "
                + Duration.between(start,
                        afterCalendarDay.toInstant()).toHours());
        System.out.println("Hours instant +1d  : "
                + Duration.between(start, afterInstantDay).toHours());
    }
}
```

```bash
javac InstantAcrossDstDemo.java
java InstantAcrossDstDemo
```

Kết quả đã kiểm chứng:

```text
Local start         : 2024-03-09T12:00-05:00[America/New_York]
Instant start       : 2024-03-09T17:00:00Z
Instant + 1 DAY     : 2024-03-10T17:00:00Z
Viewed in New York  : 2024-03-10T13:00-04:00[America/New_York]
Local + 1 calendar day: 2024-03-10T12:00-04:00[America/New_York]
Calendar day instant: 2024-03-10T16:00:00Z
Hours to local +1d : 23
Hours instant +1d  : 24
```

Cả hai kết quả đều đúng. Một phép toán giữ **đúng thời lượng 24 giờ đã trôi**, phép còn lại giữ **12:00 theo giờ địa phương ngày hôm sau**. DST làm cho hai yêu cầu có kết quả khác nhau.

Với nghiệp vụ “cùng ngày giờ vào tháng sau tại Paris”, cần một `ZoneId`:

```java
Instant event = Instant.parse("2025-01-15T10:00:00Z");
ZoneId zone = ZoneId.of("Europe/Paris");

ZonedDateTime local = event.atZone(zone);
ZonedDateTime nextMonthLocal = local.plusMonths(1);
Instant nextMonthInstant = nextMonthLocal.toInstant();
```

Đây là **đoạn minh họa trong một phương thức**, cần `import java.time.*;`. Phép cộng `plusMonths(1)` diễn ra trên ngày giờ theo lịch vùng Paris, sau đó mới trở lại `Instant`. Khi có DST hoặc ngày cuối tháng, hãy quyết định rõ cách xử lý dựa vào nghiệp vụ.

## 8. So sánh kiểu thao tác theo nhu cầu thực tế

| Nhu cầu | Cách viết phù hợp | Giải thích |
| --- | --- | --- |
| Hạn dùng sau 15 phút | `issuedAt.plus(Duration.ofMinutes(15))` | Cộng chính xác 900 giây. |
| Cộng 500 mili giây | `start.plusMillis(500)` | Mili giây cố định. |
| Lùi 2 giờ | `end.minus(2, ChronoUnit.HOURS)` | Đơn vị giờ cố định. |
| Sau đúng 24 giờ | `start.plus(1, ChronoUnit.DAYS)` | `DAYS` trên `Instant` = 86.400 giây. |
| Sau đúng 7 × 24 giờ | `start.plus(Duration.ofDays(7))` | Thời lượng cố định 604.800 giây. |
| Cùng giờ địa phương ngày mai | `start.atZone(zone).plusDays(1).toInstant()` | Theo ngày lịch trong vùng. |
| Cùng giờ địa phương tháng sau | `start.atZone(zone).plusMonths(1).toInstant()` | Theo tháng lịch trong vùng. |
| Độ dài giữa hai `Instant` | `Duration.between(start, end)` | Chênh lệch thực giữa các mốc. |

Đối với dữ liệu của ứng dụng, nên lưu `Instant` như thời điểm phát sinh hoặc hết hạn (ví dụ `createdAt`, `expiresAt`), đồng thời dùng `Duration` cho khoảng cấu hình (ví dụ `tokenTtl`). Phân biệt dữ liệu lịch và thời lượng giúp cấu trúc API rõ ràng và dễ kiểm thử.

**Đo timeout khi một thao tác đang chạy** cần chú ý thêm: `Instant.now()` đọc thời gian đồng hồ thực, có thể bị ảnh hưởng bởi việc điều chỉnh giờ hệ thống. Khi đo khoảng chạy thực trong một JVM, nguồn như `System.nanoTime()` thường phù hợp hơn. Mốc hết hạn phải còn ý nghĩa sau khi restart hoặc trao đổi giữa hệ thống lại thích hợp với `Instant`.

## 9. Các giới hạn và ngoại lệ phải kiểm soát

### Đơn vị không được hỗ trợ

Nếu gọi `instant.plus(1, ChronoUnit.MONTHS)` hoặc `instant.minus(1, ChronoUnit.YEARS)`, Java ném `UnsupportedTemporalTypeException`. Kiểm tra bằng `instant.isSupported(unit)` trước khi cộng/trừ khi đầu vào chứa đơn vị động. Với yêu cầu theo lịch, chuyển sang `ZonedDateTime` hoặc `LocalDate` rồi dùng đơn vị tương ứng.

### Miền thời gian hữu hạn và tràn số

`Instant` có giới hạn giá trị `Instant.MIN` và `Instant.MAX`. Phép cộng vượt miền này không tự quay vòng mà có thể báo `DateTimeException` hoặc `ArithmeticException` tùy nguyên nhân. Các phép chuyển đổi/multiplication dùng `long`, ví dụ `Duration.toNanos()` trên duration quá lớn, cũng có thể tràn số. Hãy xác thực số lượng lớn bất thường từ API và xử lý lỗi có chủ đích.

### Phần nano giây

`Instant` biểu diễn thời điểm tới nano giây; `plusNanos(1)` tăng một nano giây **trong mô hình giá trị**. Điều này không có nghĩa đồng hồ máy hay cơ sở dữ liệu luôn đo/lưu được chính xác từng nano giây. Khi lưu DB hoặc JSON, cần kiểm tra độ chính xác và hợp đồng định dạng của hệ thống tiếp nhận.

### Dấu âm và số lượng không hợp lệ theo nghiệp vụ

Tham số âm là hợp lệ với phép cộng/trừ, nhưng ứng dụng có thể phải từ chối TTL, timeout hoặc khoảng giữ dữ liệu âm. Đừng để phép cộng âm vô ý tạo hạn hết hiệu lực trước thời điểm tạo. Các đầu vào ngoài quy tắc nghiệp vụ nên được validate ở tầng nhận dữ liệu.

### Phép cộng trả giá trị mới

`Instant` bất biến, nên:

```java
Instant deadline = Instant.parse("2025-01-15T10:00:00Z");
deadline.plusSeconds(60); // bỏ qua kết quả: deadline vẫn 10:00
deadline = deadline.plusSeconds(60); // deadline trở thành 10:01
```

Đoạn này chỉ minh họa trong phạm vi có `import java.time.Instant;`. Muốn giữ mốc gốc, dùng biến riêng `Instant extendedDeadline = deadline.plusSeconds(60);`.

## 10. Tính thời lượng giữa hai mốc

Đây là phép toán liên quan nhưng khác cộng/trừ: **đo chênh lệch giữa hai `Instant`**. Dùng `Duration.between(...)`:

```java
Instant first = Instant.parse("2025-01-15T10:00:00Z");
Instant second = Instant.parse("2025-01-15T11:30:00Z");

Duration elapsed = Duration.between(first, second); // PT1H30M
long minutes = ChronoUnit.MINUTES.between(first, second); // 90
```

Đây là đoạn minh họa trong phương thức có `import java.time.*;` và `import java.time.temporal.ChronoUnit;`. `Duration` giữ cả phần giây/nano giây, còn `ChronoUnit.MINUTES.between` trả số phút nguyên. Khi cần biểu diễn chênh lệch dưới một phút, đừng chỉ lấy số phút nguyên vì sẽ mất phần dư.

Hai mốc `Instant` không mang vùng nên không cần đổi sang giờ địa phương để tính độ dài thực. Chỉ chuyển sang `ZonedDateTime` khi muốn áp dụng quy tắc lịch hoặc hiển thị cho người dùng.

## 11. Lỗi thường gặp

1. **Cộng tháng/năm trực tiếp vào `Instant`:** `MONTHS`, `YEARS` không được hỗ trợ; chọn kiểu theo lịch và `ZoneId` khi cần.
2. **Hiểu `DAYS` như ngày địa phương:** `Instant.plus(1, DAYS)` luôn là 24 giờ, nhưng một ngày theo DST có thể là 23 hoặc 25 giờ.
3. **Coi `ChronoUnit.WEEKS` được hỗ trợ vì một tuần bằng 7 ngày:** muốn 7 × 24 giờ thì dùng `Duration.ofDays(7)`; muốn cùng ngày/giờ tuần sau thì cộng trên kiểu lịch có vùng.
4. **Nhầm đơn vị:** `plusMillis(1000)` là cộng 1 giây, còn `plusNanos(1000)` là cộng một micro giây.
5. **Nhầm `Period` và `Duration`:** `Period.ofDays(1)` có thể áp dụng trên `Instant`, nhưng `Period.ofMonths(1)` thì không; dùng `Duration` để truyền thời lượng trôi.
6. **Làm tròn tháng thành 30 ngày:** không đúng với các tháng có 28, 29 hoặc 31 ngày.
7. **Bỏ qua giá trị trả về:** `Instant` bất biến, không sửa biến gốc.
8. **Không kiểm soát giá trị đầu vào lớn:** phép cộng có thể vượt `Instant.MAX` hoặc phép đổi duration có thể gây tràn `long`.
9. **Tự gắn múi giờ hệ thống khi muốn cộng time span:** `Instant` không cần múi giờ cho 90 phút hay 24 giờ; dùng múi giờ khi nghiệp vụ thực sự theo lịch địa phương.
10. **Đo độ trễ bằng hai lần đọc wall clock rồi mặc nhiên tin kết quả:** điều chỉnh đồng hồ có thể làm phép trừ timestamp không phản ánh thời gian chạy thực; cân nhắc nguồn đo thời gian trôi.

## 12. Bài tập tự kiểm tra

**1.** `Instant.parse("2025-01-15T10:00:00Z").plusSeconds(45)` cho kết quả gì?

**Đáp án:** `2025-01-15T10:00:45Z`.

**2.** Từ mốc `2025-01-15T10:00:00Z`, trừ 250 mili giây được gì?

**Đáp án:** `2025-01-15T09:59:59.750Z`.

**3.** `plus(1, ChronoUnit.DAYS)` có tương đương `plus(Duration.ofHours(24))` không?

**Đáp án:** Có, trên `Instant` cả hai cùng cộng 86.400 giây.

**4.** `Instant` có hỗ trợ `ChronoUnit.MICROS`, `HALF_DAYS` và `WEEKS` không?

**Đáp án:** `MICROS` và `HALF_DAYS` được hỗ trợ; `WEEKS` không được hỗ trợ trực tiếp.

**5.** Làm sao tính “cùng giờ ngày mai” ở New York qua ngày bắt đầu DST?

**Đáp án:** Chuyển `Instant` sang `ZonedDateTime` bằng `atZone(ZoneId.of("America/New_York"))`, dùng `plusDays(1)` rồi `toInstant()`. Kết quả có thể cách mốc đầu 23 giờ, không phải 24 giờ.

**6.** `Instant.plus(Period.ofMonths(1))` có chạy không?

**Đáp án:** Không, vì phải áp dụng đơn vị `MONTHS` không được `Instant` hỗ trợ. Cần kiểu ngày giờ theo lịch để cộng tháng.

**7.** Vì sao gọi `instant.plusSeconds(30);` mà biến `instant` vẫn không đổi?

**Đáp án:** Vì `Instant` bất biến. Hãy lưu giá trị trả về.

**8.** Hai mốc UTC cách nhau 90 phút, cần lưu đầy đủ khoảng trôi. Chọn kiểu nào?

**Đáp án:** `Duration.between(start, end)`, cho kết quả biểu diễn `PT1H30M`.

## Ghi nhớ

`Instant` thích hợp để dịch một mốc theo **thời lượng đã trôi**: `plus/minus(Duration)`, `plusSeconds/plusMillis/plusNanos`, `minusSeconds/minusMillis/minusNanos`, hoặc overload với `ChronoUnit` được hỗ trợ. Các đơn vị chuẩn dùng trực tiếp từ `NANOS` đến `DAYS`; `DAYS` trên `Instant` chính là **24 giờ**. Đơn vị lịch như `WEEKS`, `MONTHS` và `YEARS` không cộng trực tiếp. Khi nghiệp vụ cần **cùng giờ địa phương vào ngày/tháng tới**, hãy chuyển qua kiểu có lịch và `ZoneId`, xử lý quy tắc vùng rồi chuyển lại `Instant` nếu cần.
