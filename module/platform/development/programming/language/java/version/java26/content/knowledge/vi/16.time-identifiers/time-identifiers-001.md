# Instant.plusSaturating và bài toán vượt giới hạn thời gian

Khi cộng một `Duration` vào `Instant`, phép tính có thể vượt miền thời gian mà `Instant` biểu diễn được. Các method thông thường như `plus`, `plusSeconds` hoặc `plusNanos` sẽ ném exception nếu xảy ra tràn số hoặc kết quả vượt giới hạn. Từ **JDK 26**, `Instant.plusSaturating(Duration)` cung cấp cách tính bão hòa: nếu kết quả vượt giới hạn thì trả về `Instant.MIN` hoặc `Instant.MAX`; nếu vẫn nằm trong miền hợp lệ thì trả kết quả cộng bình thường.

Đây là API Java SE ổn định, không phải preview hay incubator. JDK 27 tiếp tục cung cấp method này. Nó đặc biệt hữu ích khi tính deadline từ thời điểm hiện tại và timeout, hoặc khi ứng dụng cần biểu diễn một thời điểm rất xa trong quá khứ/tương lai mà không để phép cộng làm gián đoạn luồng xử lý.

## 1. Instant biểu diễn thời điểm trên timeline

`Instant` đại diện một điểm thời gian trên timeline UTC của Java. Nó lưu hai thành phần:

- Số giây tính từ epoch `1970-01-01T00:00:00Z` bằng `long`.
- Phần nano giây trong giây hiện tại bằng `int`, luôn từ `0` đến `999_999_999`.

Miền thời gian của `Instant` rất rộng nhưng vẫn có giới hạn:

| Hằng số | Giá trị |
| --- | --- |
| `Instant.MIN` | `-1000000000-01-01T00:00:00Z` |
| `Instant.EPOCH` | `1970-01-01T00:00:00Z` |
| `Instant.MAX` | `+1000000000-12-31T23:59:59.999999999Z` |

`Instant.MIN` và `Instant.MAX` có thể được dùng như các mốc “rất xa trong quá khứ” và “rất xa trong tương lai”. Chúng không phải giá trị vô hạn theo nghĩa toán học; chúng là hai biên hợp lệ của kiểu `Instant`.

`Instant` immutable và thread-safe. Các phép toán như `plus` và `plusSaturating` trả về instance mới, không sửa instance ban đầu.

## 2. Vì sao phép cộng thời gian có thể thất bại?

`Instant.plus(Duration)` thực hiện phép cộng thông thường. Nếu kết quả vượt `Instant.MIN` hoặc `Instant.MAX`, method ném `DateTimeException`. Nếu phép tính số học vượt miền kiểu số, nó có thể ném `ArithmeticException`.

```java
import java.time.Duration;
import java.time.Instant;

Instant almostMax = Instant.MAX.minusSeconds(2);

// Kết quả nằm trong miền hợp lệ.
Instant valid = almostMax.plus(Duration.ofSeconds(1));

// Kết quả vượt Instant.MAX nên phép cộng thông thường thất bại.
Instant invalid = almostMax.plus(Duration.ofSeconds(10));
```

Ví dụ thứ hai ném `DateTimeException`. Trong ứng dụng, exception này có thể xuất hiện khi timeout hoặc thời gian lưu giữ dữ liệu được cấu hình quá lớn, khi cộng một duration lấy từ input bên ngoài, hoặc khi tính toán trên các mốc sentinel như `Instant.MAX`.

Nếu nghiệp vụ muốn từ chối dữ liệu vượt giới hạn, phép cộng thông thường vẫn phù hợp: exception cho biết giá trị không thể biểu diễn. Nếu nghiệp vụ chấp nhận chặn kết quả tại biên gần nhất, `plusSaturating` phù hợp hơn.

## 3. plusSaturating hoạt động như thế nào?

Chữ *saturating* có nghĩa là kết quả được giữ ở biên cho phép thay vì tiếp tục vượt biên hoặc ném lỗi do tràn. Quy tắc của `Instant.plusSaturating(Duration)`:

- Nếu `this + duration` sớm hơn `Instant.MIN`, trả về `Instant.MIN`.
- Nếu `this + duration` muộn hơn `Instant.MAX`, trả về `Instant.MAX`.
- Nếu kết quả nằm trong miền, trả về kết quả tương đương `plus(duration)`.

Ví dụ:

```java
import java.time.Duration;
import java.time.Instant;

Instant start = Instant.parse("2026-11-27T08:00:00Z");

Instant normalDeadline = start.plusSaturating(Duration.ofMinutes(30));
Instant farFuture = Instant.MAX.plusSaturating(Duration.ofSeconds(1));
Instant farPast = Instant.MIN.plusSaturating(Duration.ofSeconds(-1));

System.out.println(normalDeadline);
System.out.println(farFuture.equals(Instant.MAX)); // true
System.out.println(farPast.equals(Instant.MIN));   // true
```

`Duration` có thể dương, âm hoặc bằng zero. Duration âm làm thời điểm lùi về quá khứ; nếu lùi quá `Instant.MIN`, kết quả được chặn tại `Instant.MIN`.

Điểm khác biệt quan trọng: `plusSaturating` không chỉ bắt `DateTimeException` rồi trả về `MAX`. Nó xử lý cả hai hướng vượt biên và cả trường hợp tràn số trong phép cộng. API bảo đảm không ném `ArithmeticException` hoặc `DateTimeException` do numeric overflow hay do kết quả vượt miền `Instant`.

## 4. So sánh plus và plusSaturating

| Trường hợp | `plus(Duration)` | `plusSaturating(Duration)` |
| --- | --- | --- |
| Kết quả nằm trong miền | Trả kết quả | Trả cùng kết quả |
| Vượt `Instant.MAX` | Ném `DateTimeException` hoặc lỗi tràn số tương ứng | Trả `Instant.MAX` |
| Sớm hơn `Instant.MIN` | Ném `DateTimeException` hoặc lỗi tràn số tương ứng | Trả `Instant.MIN` |
| Duration là `null` | Ném `NullPointerException` | Ném `NullPointerException` |
| Mục tiêu | Phát hiện phép tính không biểu diễn được | Luôn tạo ra một `Instant` trong miền hợp lệ |

Ví dụ dùng `plus` khi muốn báo lỗi rõ ràng:

```java
import java.time.Duration;
import java.time.Instant;

Instant start = Instant.now();
Duration timeout = Duration.ofMinutes(30);

try {
    Instant deadline = start.plus(timeout);
    schedule(deadline);
} catch (ArithmeticException | java.time.DateTimeException e) {
    throw new IllegalArgumentException("Timeout is outside the supported range", e);
}
```

Ví dụ dùng `plusSaturating` khi chấp nhận biên thời gian:

```java
Instant deadline = start.plusSaturating(timeout);
schedule(deadline);
```

Không nên thay tất cả `plus` bằng `plusSaturating`. Hai method diễn tả hai chính sách nghiệp vụ khác nhau: một bên từ chối kết quả không thể biểu diễn; bên kia chấp nhận giới hạn hóa kết quả.

## 5. Bài toán deadline và timeout

API note của Java 26 nêu rõ một ứng dụng có thể dùng `plusSaturating` để tính deadline từ một `Instant` và timeout. Đây là tình huống thực tế thường gặp trong HTTP client, job scheduler, cache hoặc quy trình xử lý có hạn chót.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

final class DeadlineService {
    private DeadlineService() {}

    static Instant deadlineFrom(Clock clock, Duration timeout) {
        Objects.requireNonNull(clock, "clock");
        Objects.requireNonNull(timeout, "timeout");

        if (timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must not be negative");
        }

        Instant startedAt = Instant.now(clock);
        return startedAt.plusSaturating(timeout);
    }
}
```

Ở đây:

1. `Clock` cung cấp nguồn thời gian hiện tại.
2. `Instant.now(clock)` lấy mốc bắt đầu.
3. `plusSaturating(timeout)` tính deadline mà không để overflow làm hỏng luồng xử lý.
4. Nếu timeout quá lớn nhưng vẫn là một `Duration` hợp lệ, deadline được chặn ở `Instant.MAX`.

Kiểm tra deadline:

```java
static boolean isExpired(Clock clock, Instant deadline) {
    return !Instant.now(clock).isBefore(deadline);
}
```

Với timeout âm, ví dụ đã hết hạn, việc từ chối hay coi như deadline trong quá khứ là chính sách của ứng dụng. Đoạn helper trên chọn từ chối timeout âm để tránh cấu hình sai bị diễn giải âm thầm.

## 6. Kiểm thử thời gian có thể tái lập bằng Clock

Không nên buộc unit test phụ thuộc đồng hồ thật. `Instant.now(Clock)` cho phép thay nguồn thời gian bằng `Clock.fixed`, nhờ đó kiểm thử deadline một cách xác định.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

class DeadlineTest {
    @org.junit.jupiter.api.Test
    void addsTimeoutToFixedInstant() {
        Instant start = Instant.parse("2026-11-27T08:00:00Z");
        Clock clock = Clock.fixed(start, ZoneOffset.UTC);

        Instant deadline = DeadlineService.deadlineFrom(clock, Duration.ofMinutes(15));

        assertEquals(
                Instant.parse("2026-11-27T08:15:00Z"),
                deadline
        );
    }

    @org.junit.jupiter.api.Test
    void saturatesAtMaximumInstant() {
        Clock clock = Clock.fixed(Instant.MAX, ZoneOffset.UTC);

        Instant deadline = DeadlineService.deadlineFrom(clock, Duration.ofSeconds(1));

        assertEquals(Instant.MAX, deadline);
    }

    @org.junit.jupiter.api.Test
    void saturatesAtMinimumInstant() {
        Instant result = Instant.MIN.plusSaturating(Duration.ofSeconds(-1));

        assertEquals(Instant.MIN, result);
    }
}
```

`Clock.fixed` luôn trả cùng một thời điểm, nên test không bị ảnh hưởng bởi thời gian chạy của máy hoặc thời điểm bắt đầu test. Có thể dùng `Clock.offset` để tạo clock dịch chuyển so với một clock khác nếu cần kiểm tra nhiều tình huống.

## 7. Duration cũng có giới hạn riêng

`plusSaturating` bảo vệ phép cộng trên `Instant`; nó không làm cho mọi thao tác tạo hoặc biến đổi `Duration` trở nên vô hạn.

Từ JDK 26, `Duration` có hai hằng biên:

| Hằng số | Giá trị |
| --- | --- |
| `Duration.MIN` | `Long.MIN_VALUE` giây |
| `Duration.ZERO` | 0 |
| `Duration.MAX` | `Long.MAX_VALUE` giây và `999_999_999` nano giây |

Ví dụ:

```java
Instant start = Instant.EPOCH;

Instant latest = start.plusSaturating(Duration.MAX);
Instant earliest = start.plusSaturating(Duration.MIN);

System.out.println(latest.equals(Instant.MAX));   // true
System.out.println(earliest.equals(Instant.MIN)); // true
```

`Duration.MAX` và `Duration.MIN` là các giá trị hợp lệ. Tuy nhiên, việc tạo một duration bằng đơn vị lớn có thể tràn trước khi có `Duration` để truyền vào:

```java
Duration tooManyDays = Duration.ofDays(Long.MAX_VALUE);
// ArithmeticException: số ngày không thể chuyển thành số giây trong Duration.
```

Phép nhân thủ công cũng có thể tràn trước khi `Duration` được tạo:

```java
long seconds = days * 86_400; // Phép nhân long có thể wrap khi overflow.
Duration timeout = Duration.ofSeconds(seconds);
```

Nếu phải chuyển đổi thủ công, dùng phép toán có kiểm tra:

```java
long seconds = Math.multiplyExact(days, 86_400);
Duration timeout = Duration.ofSeconds(seconds);
```

Hoặc gọi trực tiếp `Duration.ofDays(days)` để factory kiểm tra giới hạn của `Duration`. `plusSaturating` chỉ bảo vệ phép cộng sau khi một `Duration` hợp lệ đã được tạo; nó không thể khôi phục giá trị dự định sau khi một phép nhân `long` đã wrap.

Tương tự, `Duration.toNanos()` và `Duration.toMillis()` có thể ném `ArithmeticException` nếu tổng thời lượng không vừa kiểu `long` của đơn vị đích. Đừng chuyển một duration rất lớn sang nano giây chỉ để gọi `plusSaturating`; truyền trực tiếp `Duration`.

Ví dụ sau dùng một duration lớn nhưng vẫn hợp lệ:

```java
Duration hugeButValid = Duration.ofSeconds(Long.MAX_VALUE);
Instant deadline = Instant.now().plusSaturating(hugeButValid);
```

`plusSaturating` xử lý được phép cộng này và trả `Instant.MAX`. Nó không thể xử lý lỗi đã xảy ra trong biểu thức tạo `Duration` trước khi method được gọi.

## 8. Duration là thời lượng cố định, không phải khoảng lịch

`Duration` đo lượng thời gian theo giây và nano giây. Một ngày trong `Duration` luôn bằng đúng 24 giờ; nó không tự điều chỉnh theo giờ mùa hè (DST) hoặc quy tắc lịch của múi giờ.

```java
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant in24Hours = Instant.now().plusSaturating(Duration.ofDays(1));
```

Nếu yêu cầu nghiệp vụ là “cùng giờ địa phương vào ngày mai”, hãy dùng `ZonedDateTime` và phép toán theo lịch:

```java
ZonedDateTime sameLocalTimeTomorrow =
        ZonedDateTime.now(ZoneId.of("Europe/Paris")).plusDays(1);
```

`plusSaturating` nhận `Duration`, không nhận `Period`. Không thay một phép tính theo lịch tháng/ngày bằng một số giây cố định nếu nghiệp vụ phụ thuộc múi giờ hoặc DST.

## 9. Instant deadline và monotonic timeout là hai khái niệm khác nhau

`Instant` biểu diễn thời điểm trên wall clock. Nó phù hợp để lưu deadline, gửi deadline qua API, ghi log hoặc so sánh với một mốc thời gian UTC. Tuy nhiên, đồng hồ hệ thống có thể được điều chỉnh bởi đồng bộ thời gian, quản trị hệ thống hoặc môi trường ảo hóa; Java Time API không yêu cầu clock phải tiến đều hoặc đơn điệu.

Nếu mục tiêu là đo thời lượng đã trôi qua trong một JVM, hãy dùng `System.nanoTime()` thay vì lấy hai `Instant.now()` rồi trừ nhau:

```java
long startedAt = System.nanoTime();
long timeoutNanos = Duration.ofSeconds(5).toNanos();

// ... thực hiện công việc ...

boolean timedOut = System.nanoTime() - startedAt >= timeoutNanos;
```

Phép trừ hai giá trị `nanoTime()` là cách so sánh elapsed time an toàn trước overflow của phép cộng mốc tuyệt đối. Không so sánh trực tiếp `System.nanoTime()` với `Instant`, không lưu giá trị `nanoTime()` vào database và không gửi nó sang process/JVM khác: origin của nó chỉ có ý nghĩa trong cùng một JVM instance.

Phân biệt mục tiêu:

| Bài toán | Công cụ phù hợp |
| --- | --- |
| Lưu thời điểm sự kiện hoặc deadline UTC | `Instant` |
| Tính deadline từ một mốc UTC và timeout, có thể vượt biên Instant | `Instant.plusSaturating(Duration)` |
| Đo thời gian thực thi trong một JVM | `System.nanoTime()` |
| Tính “ngày mai cùng giờ địa phương” | `ZonedDateTime.plusDays(1)` |
| Tính số ngày/tháng theo lịch | `Period` hoặc API lịch phù hợp |

`plusSaturating` tạo ra một mốc deadline an toàn trong miền `Instant`; nó không tự lên lịch task, không chờ timeout và không cung cấp đồng hồ đơn điệu.

## 10. Saturation có thể che giấu cấu hình bất thường

Saturation ngăn exception do phép cộng vượt miền, nhưng có thể khiến một timeout sai hoặc cực lớn biến thành `Instant.MAX`. Trong một số hệ thống, điều đó là đúng ý nghĩa “không hết hạn trong miền biểu diễn”; trong hệ thống khác, nó có thể che lỗi cấu hình.

Trước khi dùng, hãy quyết định rõ chính sách:

- Nếu giá trị vượt giới hạn có nghĩa là “không bao giờ hết hạn”, `Instant.MAX` có thể dùng như sentinel nội bộ.
- Nếu timeout phải nằm trong giới hạn nghiệp vụ, hãy validate trước khi tính deadline.
- Nếu dữ liệu được ghi vào database, message broker hoặc hệ thống khác, xác nhận các hệ thống đó có thể lưu/diễn giải `Instant.MAX` hay không. Nhiều kiểu timestamp bên ngoài có miền nhỏ hơn Java `Instant` rất nhiều.
- Nếu cần phân biệt “không có deadline” với “deadline cực xa”, dùng kiểu dữ liệu rõ ràng như `Optional<Instant>` hoặc một domain type thay vì ngầm quy ước `Instant.MAX`.

Ví dụ validate giới hạn nghiệp vụ:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

static Instant createDeadline(Clock clock, Duration timeout) {
    Objects.requireNonNull(clock);
    Objects.requireNonNull(timeout);

    Duration maximumAllowed = Duration.ofDays(30);
    if (timeout.isNegative() || timeout.compareTo(maximumAllowed) > 0) {
        throw new IllegalArgumentException("timeout must be between 0 and 30 days");
    }

    return Instant.now(clock).plusSaturating(timeout);
}
```

Trong ví dụ, `plusSaturating` vẫn bảo vệ phép cộng, còn validation đảm bảo giá trị đầu vào phù hợp với nghiệp vụ. Hai việc này giải quyết hai vấn đề khác nhau.

## 11. Trạng thái API và điều kiện sử dụng

| JDK | Trạng thái `Instant.plusSaturating(Duration)` | Cách sử dụng |
| --- | --- | --- |
| JDK 25 trở xuống | Chưa có method này | Dùng `plus(Duration)` và xử lý exception hoặc tự áp dụng chính sách biên phù hợp |
| JDK 26 | API Java SE final, `Since: 26` | Gọi trực tiếp, không cần preview flag |
| JDK 27 | Tiếp tục là API Java SE final | Gọi trực tiếp, không cần preview flag |

`Instant.plusSaturating` thuộc module `java.base`, package `java.time`. Không cần `--enable-preview` hoặc `--add-modules`. Khi dự án vẫn phải hỗ trợ JDK 25 trở xuống, không thể biên dịch source gọi method này trực tiếp với `--release 25`; cần giữ một implementation tương thích riêng hoặc đặt baseline JDK tối thiểu là 26.

## Ghi nhớ

- `Instant.plus(Duration)` có thể ném `DateTimeException` khi vượt `Instant.MIN/MAX` hoặc `ArithmeticException` khi phép tính số học tràn.
- `Instant.plusSaturating(Duration)` có từ JDK 26; vượt biên thì trả `Instant.MIN` hoặc `Instant.MAX`, còn trong biên thì cho kết quả như `plus`.
- `plusSaturating` chấp nhận duration âm; duration âm quá lớn sẽ bị chặn ở `Instant.MIN`.
- API không ném `ArithmeticException` hoặc `DateTimeException` do overflow/range của phép cộng, nhưng vẫn yêu cầu `Duration` khác `null`.
- `Duration.MIN` và `Duration.MAX` có từ JDK 26; tạo hoặc chuyển đổi duration vẫn có thể overflow trước khi gọi `plusSaturating`.
- `Duration.ofDays(1)` là đúng 24 giờ; không thay thế phép cộng theo lịch/múi giờ.
- Dùng `Instant` cho mốc deadline có thể lưu/truyền; dùng `System.nanoTime()` cho đo elapsed timeout trong cùng JVM.
- Saturation là chính sách giới hạn hóa kết quả, không thay thế validation đầu vào hoặc kiểm tra khả năng lưu timestamp của hệ thống ngoài.
- API final trong JDK 26/27, không cần preview flag.

## Tài liệu tham khảo

- [Instant, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html) — `plusSaturating`, `Instant.MIN/MAX`, hành vi overflow của `plus`.
- [Instant, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Instant.html) — xác nhận API tiếp tục có trong JDK 27.
- [Duration, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html) — giới hạn `Duration.MIN/MAX`, tạo duration và overflow khi chuyển đổi đơn vị.
- [System.nanoTime(), Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html#nanoTime()) — đo elapsed time và cách so sánh timeout tránh overflow.
- [Clock, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html) — clock có thể không đơn điệu; `Clock.fixed` và nguồn thời gian có thể thay thế khi kiểm thử.
