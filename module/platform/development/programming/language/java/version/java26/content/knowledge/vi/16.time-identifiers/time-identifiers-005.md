# Tính, so sánh và kiểm thử khoảng thời gian âm

Khoảng thời gian âm là kết quả hợp lệ khi thời điểm kết thúc đứng trước thời điểm bắt đầu. Ví dụ: deadline đã qua, dữ liệu đến muộn so với mốc tham chiếu, hoặc phép so sánh hai timestamp theo chiều ngược lại. Trong Java, không nên tự đổi dấu số mili giây hoặc tự cộng/trừ các thành phần thời gian; API `java.time` đã biểu diễn được khoảng thời gian có hướng, so sánh chính xác và xử lý các trường hợp biên.

Điều quan trọng là chọn đúng loại dữ liệu. `Duration` mô tả lượng thời gian chính xác theo giây và nano giây; `Period` mô tả lượng thời gian theo lịch gồm năm, tháng và ngày. Cả hai đều có thể mang giá trị âm, nhưng quy tắc so sánh và ý nghĩa của chúng khác nhau.

## 1. Khi nào khoảng thời gian âm xuất hiện?

Một khoảng thời gian được tính từ `start` đến `end` có hướng:

- `end` sau `start`: khoảng thời gian dương.
- `end` bằng `start`: khoảng thời gian bằng không.
- `end` trước `start`: khoảng thời gian âm.

Ví dụ trong hệ thống đặt lịch, nếu thời điểm hiện tại là 10:05 nhưng deadline là 10:00, thời gian còn lại là âm 5 phút. Giá trị âm có ích vì nó cho biết deadline đã trễ bao lâu. Nếu chỉ cần biết deadline đã hết hạn hay chưa, có thể kiểm tra trực tiếp thứ tự hai `Instant`.

```java
Instant deadline = Instant.parse("2026-11-27T10:00:00Z");
Instant now = Instant.parse("2026-11-27T10:05:00Z");

Duration remaining = Duration.between(now, deadline);
System.out.println(remaining);       // PT-5M
System.out.println(remaining.isNegative()); // true
```

`Duration.between(startInclusive, endExclusive)` trả về khoảng thời gian có hướng từ đối số đầu tới đối số thứ hai. Nếu đối số thứ hai ở trước đối số đầu, kết quả là `Duration` âm; API không tự đổi thành trị tuyệt đối.

## 2. Duration biểu diễn khoảng thời gian âm

`java.time.Duration` biểu diễn lượng thời gian theo giây và nano giây. Nó có độ phân giải nano giây và có thể dương, bằng không hoặc âm. `Duration` là immutable và thread-safe.

Các phương thức thường dùng để kiểm tra dấu:

| Phương thức | Ý nghĩa |
|---|---|
| `isNegative()` | Độ dài tổng thể nhỏ hơn 0 |
| `isZero()` | Độ dài bằng 0 |
| `isPositive()` | Độ dài lớn hơn 0; có từ Java 18 |
| `abs()` | Trả về bản sao có độ dài không âm |
| `negated()` | Đổi dấu độ dài |
| `compareTo(other)` | So sánh hai Duration theo độ dài chính xác |

Ví dụ kiểm tra cả ba trạng thái:

```java
Duration late = Duration.ofMinutes(-5);
Duration noDelay = Duration.ZERO;
Duration early = Duration.ofSeconds(30);

System.out.println(late.isNegative());   // true
System.out.println(noDelay.isZero());    // true
System.out.println(early.isPositive());  // true
```

Không nên dùng `duration.getSeconds() < 0` như cách duy nhất để hiểu cấu trúc hoặc độ lớn của Duration. Giá trị được lưu bằng hai phần: seconds và nano-of-second đã chuẩn hóa. Với duration âm nhỏ hơn một giây, seconds có thể là `-1` trong khi nano-of-second vẫn là số dương.

### 2.1. Vì sao -1 nano giây có seconds = -1?

`Duration` luôn chuẩn hóa nano-of-second về khoảng từ `0` đến `999_999_999`. Vì thế, một nano giây âm được biểu diễn như sau:

```java
Duration minusOneNano = Duration.ofNanos(-1);

System.out.println(minusOneNano);            // PT-0.000000001S
System.out.println(minusOneNano.getSeconds()); // -1
System.out.println(minusOneNano.getNano());    // 999999999
System.out.println(minusOneNano.isNegative()); // true
```

Hai thành phần `getSeconds()` và `getNano()` phải được hiểu cùng nhau. Tổng độ dài là `-1` nano giây, không phải `-1` giây cộng thêm gần một giây theo nghĩa số học thông thường. Quy tắc chuẩn hóa giúp biểu diễn duy nhất một giá trị duration; dùng `isNegative()` để kiểm tra dấu và `compareTo()` để so sánh.

### 2.2. Tạo Duration âm

Có thể tạo Duration âm từ factory, phép tính hoặc `between()`:

```java
Duration a = Duration.ofSeconds(-12);
Duration b = Duration.ofMillis(-250);
Duration c = Duration.ofSeconds(0, -1); // -1 nano giây

Instant start = Instant.parse("2026-11-27T10:00:00Z");
Instant end = Instant.parse("2026-11-27T09:59:59.750Z");
Duration d = Duration.between(start, end); // -250 ms
```

Các factory như `ofSeconds`, `ofMillis`, `ofNanos` nhận số âm. Với `ofSeconds(seconds, nanoAdjustment)`, phần điều chỉnh nano cũng có thể âm; factory tự chuẩn hóa hai thành phần về dạng nội bộ hợp lệ.

## 3. So sánh Duration mà không mất độ chính xác

`Duration` triển khai `Comparable<Duration>`. Dùng `compareTo()` khi cần thứ tự tổng quát:

```java
Duration a = Duration.ofMillis(-500);
Duration b = Duration.ofMillis(-250);
Duration zero = Duration.ZERO;

System.out.println(a.compareTo(b) < 0);    // true: -500 ms nhỏ hơn -250 ms
System.out.println(b.compareTo(zero) < 0); // true
System.out.println(a.compareTo(b) == 0);   // false
```

`compareTo()` so sánh tổng độ dài của hai Duration và nhất quán với `equals()`. Không chuyển cả hai sang `toNanos()` để so sánh vì một Duration lớn có thể vượt phạm vi `long` nano giây và ném `ArithmeticException`. So sánh trực tiếp bằng `compareTo()` tránh bước chuyển đổi có nguy cơ tràn số.

Không viết logic so sánh bằng cách trừ hai giá trị mili giây:

```java
// Tránh: phép trừ long có thể overflow.
long difference = end.toEpochMilli() - start.toEpochMilli();
```

Thay vào đó, so sánh hai `Instant` trực tiếp hoặc tạo `Duration`:

```java
boolean endBeforeStart = end.isBefore(start);
Duration difference = Duration.between(start, end);
boolean negative = difference.isNegative();
```

Nếu chỉ cần xác định thứ tự, `Instant.isBefore()`/`isAfter()` đơn giản hơn. Nếu cần đo khoảng cách, `Duration` giữ độ chính xác nano giây.

## 4. Dùng abs() và negated() đúng mục đích

`abs()` trả về bản sao có độ dài không âm. `negated()` đảo dấu của khoảng thời gian. Hai phương thức không thay đổi instance gốc vì `Duration` immutable:

```java
Duration delay = Duration.ofSeconds(-7);

Duration magnitude = delay.abs();
Duration reversed = delay.negated();

System.out.println(magnitude); // PT7S
System.out.println(reversed); // PT7S
System.out.println(delay);    // PT-7S, giá trị ban đầu không đổi
```

Chỉ dùng `abs()` khi nghiệp vụ thực sự cần độ lớn không quan tâm chiều, ví dụ hiển thị “trễ 7 giây”. Không dùng nó khi dấu âm thể hiện trạng thái cần xử lý, như deadline đã quá hạn hoặc dữ liệu timestamp sai thứ tự.

### 4.1. Tràn số ở biên Duration

JDK 26 bổ sung các hằng `Duration.MIN` và `Duration.MAX`. `MIN` là giá trị nhỏ nhất có thể biểu diễn: `Long.MIN_VALUE` giây; `MAX` là `Long.MAX_VALUE` giây cộng `999_999_999` nano giây. Các giá trị này hữu ích cho sentinel và kiểm thử biên.

Do phạm vi số nguyên có dấu không đối xứng, trị tuyệt đối của giá trị nhỏ nhất không thể biểu diễn bằng kiểu tương ứng. Vì vậy `Duration.MIN.abs()` và `Duration.MIN.negated()` có thể ném `ArithmeticException`. Các phép cộng, trừ, nhân, chuyển sang mili giây/nano giây cũng có thể overflow:

```java
try {
    Duration largestPositive = Duration.MIN.abs();
} catch (ArithmeticException ex) {
    // Không thể biểu diễn trị tuyệt đối của Duration.MIN.
}

try {
    long nanos = Duration.ofDays(200_000).toNanos();
} catch (ArithmeticException ex) {
    // Duration quá lớn để chứa tổng nano giây trong một long.
}
```

Không giả định `abs()`, `negated()`, `toMillis()` hoặc `toNanos()` luôn thành công. Nếu nhận timestamp hoặc khoảng thời gian từ dữ liệu ngoài, hãy xác định miền giá trị nghiệp vụ và xử lý `ArithmeticException` ở ranh giới chuyển đổi.

## 5. Tính khoảng thời gian từ hai mốc thời gian

Chọn loại temporal phù hợp với dữ liệu:

| Dữ liệu | API tính khoảng | Đặc điểm |
|---|---|---|
| Hai mốc thời gian tuyệt đối | `Duration.between(Instant, Instant)` | So sánh trên timeline, độc lập múi giờ |
| Hai thời điểm có offset | `Duration.between(OffsetDateTime, OffsetDateTime)` | Tính theo thời gian thực tương ứng với offset |
| Hai thời điểm có múi giờ | `Duration.between(ZonedDateTime, ZonedDateTime)` | Tính số giây thực tế giữa hai mốc, có xét chuyển đổi offset/DST |
| Hai ngày lịch | `Period.between(LocalDate, LocalDate)` | Trả về năm, tháng, ngày theo lịch |
| Số ngày nguyên giữa hai ngày | `ChronoUnit.DAYS.between(start, end)` | Trả về số ngày có dấu dưới dạng `long` |

`Duration.between()` yêu cầu các temporal hỗ trợ đơn vị `SECONDS`; để có độ chính xác đầy đủ, cần hỗ trợ `NANOS` hoặc `NANO_OF_SECOND`. `LocalDate` không có giờ/giây nên không phù hợp để tính `Duration`; dùng `Period` hoặc `ChronoUnit.DAYS`.

```java
LocalDate today = LocalDate.of(2026, 11, 27);
LocalDate earlier = LocalDate.of(2026, 11, 20);

Period calendarGap = Period.between(today, earlier);
long dayGap = ChronoUnit.DAYS.between(today, earlier);

System.out.println(calendarGap.isNegative()); // true
System.out.println(dayGap);                   // -7
```

Với `LocalTime`, không có ngày đi kèm nên `Duration.between(23:00, 01:00)` biểu diễn khoảng âm 22 giờ theo thứ tự cùng một ngày, không tự hiểu là 2 giờ qua nửa đêm. Nếu nghiệp vụ có thể qua ngày, hãy dùng `LocalDateTime` hoặc `ZonedDateTime` đầy đủ ngày.

## 6. Phân biệt Duration âm và Period âm

`Duration` đo thời lượng chính xác. `Period` mô tả thay đổi theo lịch với ba thành phần năm, tháng và ngày. Không thể luôn đổi một `Period` thành số giây cố định vì tháng có độ dài khác nhau, năm có thể có ngày nhuận và ngày lịch có thể dài 23 hoặc 25 giờ khi đổi DST.

`Period.between(startDate, endDate)` trả về Period âm nếu ngày kết thúc trước ngày bắt đầu. Với phép tính ngược chiều này, dấu của các thành phần năm, tháng và ngày được điều chỉnh cùng chiều:

```java
LocalDate start = LocalDate.of(2026, 6, 10);
LocalDate end = LocalDate.of(2026, 6, 1);

Period backwards = Period.between(start, end);
System.out.println(backwards.isNegative()); // true
System.out.println(backwards.isZero());     // false
```

`Period.isNegative()` có ý nghĩa riêng: trả về `true` nếu **bất kỳ** thành phần năm, tháng hoặc ngày nào nhỏ hơn 0. `Period` có thể chứa các thành phần trái dấu vì các phép toán được thực hiện riêng trên từng đơn vị và không tự chuẩn hóa:

```java
Period mixed = Period.of(1, -2, 3);

System.out.println(mixed.isNegative()); // true vì months = -2

LocalDate base = LocalDate.of(2026, 1, 1);
System.out.println(base.plus(mixed));  // 2026-11-04, vẫn sau base
```

Ví dụ cho thấy `Period.isNegative()` không phải phép tính tổng quát để xác định kết quả khi áp dụng Period vào một ngày cụ thể. Nó chỉ kiểm tra có thành phần nào âm hay không. Nếu cần biết ngày sau khi áp dụng Period nằm trước hay sau mốc gốc, hãy áp dụng Period vào cùng một ngày nền rồi so sánh hai `LocalDate`.

### 6.1. Period không có compareTo()

`Period` không triển khai `Comparable` và không có `compareTo()`. Không thể xếp thứ tự mọi Period chỉ dựa vào các con số năm/tháng/ngày vì ý nghĩa của tháng và năm phụ thuộc ngày bắt đầu. Ví dụ cộng một tháng vào ngày 31 có thể đưa tới ngày cuối tháng kế tiếp, trong khi cộng một tháng vào ngày 15 giữ ngày 15.

Nếu cần so sánh hai thay đổi lịch trong một nghiệp vụ cụ thể, hãy xác định ngày nền:

```java
LocalDate baseDate = LocalDate.of(2026, 1, 31);
Period p1 = Period.ofMonths(1);
Period p2 = Period.ofDays(30);

LocalDate result1 = baseDate.plus(p1);
LocalDate result2 = baseDate.plus(p2);

int comparison = result1.compareTo(result2);
```

Kết quả so sánh chỉ có ý nghĩa đối với `baseDate` đã chọn. Không chuyển `Period` sang `Duration` bằng cách giả định một tháng bằng 30 ngày hoặc một năm bằng 365 ngày.

### 6.2. normalized() không biến Period thành một con số thời gian

`Period.normalized()` chỉ chuẩn hóa phần năm và tháng, đưa tháng về khoảng nhỏ hơn 12 và điều chỉnh năm tương ứng. Phần ngày không thay đổi; phép chuẩn hóa không tính số ngày thực tế và không loại bỏ khả năng có thành phần âm:

```java
Period original = Period.of(1, -25, 3);
Period normalized = original.normalized();

System.out.println(original);   // P1Y-25M3D
System.out.println(normalized); // P-1Y-1M3D
```

Vì ngày vẫn là `+3D`, Period chuẩn hóa vẫn có thành phần trái dấu. `normalized()` không phải phép chuyển đổi để so sánh Period như một số nguyên ngày.

## 7. Duration và Period khác nhau khi qua DST

Một ngày lịch không phải lúc nào cũng dài chính xác 24 giờ ở múi giờ có daylight saving time. `Period.ofDays(1)` cộng một ngày lịch và cố giữ giờ địa phương; `Duration.ofDays(1)` luôn cộng chính xác 86.400 giây.

```java
ZoneId paris = ZoneId.of("Europe/Paris");
ZonedDateTime beforeDst = ZonedDateTime.of(
        2026, 3, 28, 12, 0, 0, 0, paris);

ZonedDateTime nextCalendarDay = beforeDst.plus(Period.ofDays(1));
ZonedDateTime after24Hours = beforeDst.plus(Duration.ofDays(1));

System.out.println(Duration.between(beforeDst, nextCalendarDay)); // PT23H
System.out.println(Duration.between(beforeDst, after24Hours));    // PT24H
```

Trong ví dụ, Paris chuyển sang giờ mùa hè vào ngày 29-03-2026. Cộng một ngày lịch giữ 12:00 giờ địa phương nhưng chỉ đi qua 23 giờ thực tế; cộng `Duration.ofDays(1)` đi qua đúng 24 giờ và cho kết quả 13:00 giờ địa phương.

Khi kiểm tra khoảng thời gian âm liên quan lịch hẹn, hạn chót hoặc sự kiện có múi giờ, hãy dùng `Instant`/`ZonedDateTime` để biểu diễn đúng mốc thời gian và `Duration` để đo thời lượng thực. Khi tính tuổi, kỳ hạn theo tháng hoặc số ngày lịch, dùng `LocalDate`/`Period` theo quy tắc nghiệp vụ.

## 8. Kiểm tra deadline và khoảng thời gian âm

Một mẫu phổ biến là tính thời gian còn lại đến deadline:

```java
static Duration remainingUntil(Instant deadline, Clock clock) {
    return Duration.between(clock.instant(), deadline);
}

static boolean isExpired(Instant deadline, Clock clock) {
    return !clock.instant().isBefore(deadline);
}
```

Nếu `remainingUntil()` trả về Duration âm, deadline đã qua; nếu bằng zero, thời điểm hiện tại đúng bằng deadline; nếu dương, deadline còn ở tương lai. `isExpired()` dùng so sánh mốc trực tiếp và xem thời điểm bằng deadline là hết hạn. Hãy xác định rõ quy tắc biên này trong nghiệp vụ.

Inject `Clock` giúp code kiểm thử được mà không phải chờ thời gian thực. Không dùng `Thread.sleep()` để kiểm thử deadline vì test sẽ chậm và phụ thuộc scheduler của máy chạy:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class DeadlineTest {
    private static final Instant NOW =
            Instant.parse("2026-11-27T10:00:00Z");
    private static final Clock CLOCK =
            Clock.fixed(NOW, ZoneOffset.UTC);

    private static Duration remainingUntil(Instant deadline, Clock clock) {
        return Duration.between(clock.instant(), deadline);
    }

    private static boolean isExpired(Instant deadline, Clock clock) {
        return !clock.instant().isBefore(deadline);
    }

    @Test
    void deadlineInPastProducesNegativeDuration() {
        Instant deadline = NOW.minusSeconds(5);

        Duration remaining = remainingUntil(deadline, CLOCK);

        assertEquals(Duration.ofSeconds(-5), remaining);
        assertTrue(remaining.isNegative());
        assertTrue(isExpired(deadline, CLOCK));
    }

    @Test
    void deadlineAtNowIsExpiredButDurationIsZero() {
        Duration remaining = remainingUntil(NOW, CLOCK);

        assertTrue(remaining.isZero());
        assertFalse(remaining.isNegative());
        assertTrue(isExpired(NOW, CLOCK));
    }

    @Test
    void deadlineInFutureProducesPositiveDuration() {
        Instant deadline = NOW.plusNanos(1);

        Duration remaining = remainingUntil(deadline, CLOCK);

        assertEquals(Duration.ofNanos(1), remaining);
        assertFalse(remaining.isNegative());
        assertFalse(isExpired(deadline, CLOCK));
    }
}
```

Các phương thức `remainingUntil()` và `isExpired()` là code ứng dụng minh họa. Trong dự án, đặt chúng trong class cần kiểm thử và inject `Clock` qua constructor hoặc tham số thay vì đọc trực tiếp `Instant.now()` bên trong logic.

## 9. Kiểm thử riêng các trường hợp âm và biên

Ngoài kiểm thử deadline, nên kiểm tra các đặc điểm dễ bị nhầm của `Duration` và `Period`:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.time.LocalDate;
import java.time.Period;
import org.junit.jupiter.api.Test;

class NegativeAmountTest {
    @Test
    void negativeSubsecondDurationIsStillNegative() {
        Duration value = Duration.ofNanos(-1);

        assertTrue(value.isNegative());
        assertFalse(value.isZero());
        assertEquals(-1, value.getSeconds());
        assertEquals(999_999_999, value.getNano());
    }

    @Test
    void compareNegativeDurationsByTheirTotalLength() {
        Duration longerDelay = Duration.ofSeconds(-5);
        Duration shorterDelay = Duration.ofSeconds(-2);

        assertTrue(longerDelay.compareTo(shorterDelay) < 0);
        assertEquals(Duration.ofSeconds(5), longerDelay.abs());
        assertEquals(Duration.ofSeconds(5), longerDelay.negated());
    }

    @Test
    void reversedDateRangeProducesNegativePeriod() {
        LocalDate later = LocalDate.of(2026, 6, 10);
        LocalDate earlier = LocalDate.of(2026, 6, 1);

        Period value = Period.between(later, earlier);

        assertTrue(value.isNegative());
        assertFalse(value.isZero());
    }

    @Test
    void mixedSignPeriodIsNegativeWhenAnyComponentIsNegative() {
        Period value = Period.of(1, -2, 3);
        LocalDate base = LocalDate.of(2026, 1, 1);

        assertTrue(value.isNegative());
        assertTrue(base.plus(value).isAfter(base));
    }
}
```

Test không nên giả định `Period.isNegative()` có nghĩa tổng thay đổi lịch luôn đi lùi. Hãy kiểm tra riêng quy tắc API và kết quả sau khi áp dụng Period vào một ngày nền nếu đó là điều nghiệp vụ cần xác nhận.

### 9.1. Kiểm thử overflow

Với những phép tính có thể chạm giới hạn kiểu dữ liệu, kiểm tra exception một cách tường minh:

```java
@Test
void absoluteValueOfMinimumDurationOverflows() {
    assertThrows(ArithmeticException.class, () -> Duration.MIN.abs());
}

@Test
void convertingHugeDurationToNanosOverflows() {
    assertThrows(ArithmeticException.class,
            () -> Duration.ofDays(200_000).toNanos());
}
```

Đây là kiểm thử biên theo API JDK 26. `Duration.MIN` và `Duration.MAX` được bổ sung từ JDK 26; nếu source phải chạy trên JDK cũ hơn, hãy tạo giá trị biên bằng `Duration.ofSeconds(Long.MIN_VALUE)` thay cho hằng `MIN`.

## 10. Các lỗi thường gặp khi xử lý khoảng thời gian âm

| Cách làm dễ sai | Vấn đề | Cách làm phù hợp |
|---|---|---|
| Luôn gọi `abs()` ngay sau `between()` | Che mất việc end trước start | Kiểm tra `isNegative()` trước; chỉ lấy trị tuyệt đối nếu nghiệp vụ cần |
| So sánh bằng `toNanos()` | Có thể overflow với Duration lớn | Dùng `compareTo()` |
| Chỉ nhìn `getNano()` để xác định dấu | Nano-of-second luôn nằm từ 0 đến 999.999.999 | Dùng `isNegative()` |
| Dùng `Duration` cho hai `LocalDate` | `LocalDate` không có đơn vị giây | Dùng `Period` hoặc `ChronoUnit.DAYS` |
| Coi một ngày luôn bằng 24 giờ | Sai khi cộng ngày lịch qua DST | Phân biệt `Period` và `Duration` |
| Coi `Period.isNegative()` là tổng dấu | Chỉ cần một thành phần âm là true | Xem từng thành phần hoặc áp dụng vào ngày nền |
| Tự chuyển Period thành số ngày bằng 30 ngày/tháng | Tháng và năm có độ dài khác nhau | Giữ Period hoặc tính trên ngày nền cụ thể |
| Dùng `Instant.now()` trong logic cần test | Test phụ thuộc đồng hồ thật | Inject `Clock` và dùng `Clock.fixed()` |
| Dùng `Thread.sleep()` để kiểm tra deadline | Test chậm, dễ flaky | Dịch chuyển Clock cố định để kiểm tra quá khứ/hiện tại/tương lai |
| Không xử lý `ArithmeticException` | Phép tính hoặc chuyển đổi có thể overflow | Xác định miền giá trị và kiểm thử biên |

## 11. Chọn API theo mục đích

- Dùng `Duration` khi đo thời gian thực giữa hai `Instant`, timeout, thời gian xử lý, độ trễ hoặc khoảng cách tới deadline.
- Dùng `Period` khi tính thay đổi theo lịch như tuổi, số tháng hợp đồng, ngày gia hạn hoặc khoảng ngày trên lịch.
- Dùng `ChronoUnit` khi chỉ cần số nguyên của một đơn vị cụ thể, ví dụ số ngày giữa hai `LocalDate`.
- Dùng `Clock` khi logic phụ thuộc thời điểm hiện tại và cần kiểm thử xác định.
- Dùng `Instant.isBefore()`/`isAfter()` nếu chỉ cần thứ tự mốc thời gian, không cần tạo Duration.

Các API `java.time.Duration`, `Period`, `Instant`, `LocalDate`, `ZonedDateTime` và `Clock` là API chuẩn từ Java 8, vẫn áp dụng trên JDK 26 và không cần bật preview. JDK 26 bổ sung `Duration.MIN` và `Duration.MAX`; những phần còn lại trong bài là cách sử dụng API ổn định hiện hành, không phụ thuộc incubator hoặc tính năng preview.

## Tài liệu tham khảo

- [Java SE 26 API: Duration](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html)
- [Java SE 26 API: Period](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Period.html)
- [Java SE 26 API: Instant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
- [Java SE 26 API: Clock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html)
- [Java SE 26 API: ChronoUnit](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ChronoUnit.html)
- [Java SE 26 Date-Time User Guide](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/package-summary.html)
