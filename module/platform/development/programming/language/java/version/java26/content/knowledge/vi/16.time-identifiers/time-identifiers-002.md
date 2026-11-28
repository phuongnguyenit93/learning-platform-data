# Hành vi bão hòa tại Instant.MIN, Instant.MAX

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích giới hạn biểu diễn của `Instant.MIN` và `Instant.MAX`.
- Phân biệt phép cộng thời gian thông thường với phép cộng bão hòa.
- Dùng `Instant.plusSaturating(Duration)` để tính deadline không vượt miền Instant.
- Hiểu vai trò và giới hạn của `Duration.MIN`, `Duration.MAX`.
- Kiểm thử giá trị nằm trong miền, đúng biên và vượt biên.
- Tránh nhầm giá trị biên với vô hạn hoặc dùng phép toán bão hòa cho mục đích không phù hợp.
- Phân biệt timestamp theo đồng hồ dân sự với phép đo thời gian trôi qua bằng đồng hồ monotonic.

## 1. Vì sao Instant có giới hạn?

`Instant` biểu diễn một thời điểm trên timeline theo epoch-second và nanosecond. Kiểu này không lưu mọi thời điểm toán học có thể tưởng tượng; nó có miền giá trị hữu hạn được Java Time API quy định.

Hai hằng số biên là:

- `Instant.MIN`: thời điểm sớm nhất được hỗ trợ, tương ứng năm -1.000.000.000 UTC.
- `Instant.MAX`: thời điểm muộn nhất được hỗ trợ, tương ứng cuối năm +1.000.000.000 UTC với độ chính xác nanosecond.

Chúng có thể được dùng làm mốc “rất xa trong quá khứ” hoặc “rất xa trong tương lai”. Tuy nhiên, đây vẫn là các giá trị `Instant` hữu hạn, hợp lệ và có thể so sánh; chúng không phải infinity theo nghĩa toán học.

`Instant` là immutable và thread-safe. Các phép toán như `plusSeconds`, `plusNanos`, `plus(Duration)` hoặc `minus(Duration)` trả về một instance mới. Nếu kết quả vượt miền hỗ trợ, phép toán thông thường có thể ném `DateTimeException` hoặc `ArithmeticException`.

## 2. Phép cộng thông thường có thể ném exception

Ví dụ, cộng thêm một nanosecond vào giá trị lớn nhất:

~~~java
Instant latest = Instant.MAX;

Instant next = latest.plusNanos(1);
// DateTimeException vì kết quả vượt Instant.MAX
~~~

Tương tự, trừ một nanosecond khỏi `Instant.MIN` cũng vượt miền biểu diễn:

~~~java
Instant earliest = Instant.MIN;

Instant previous = earliest.minusNanos(1);
// DateTimeException vì kết quả sớm hơn Instant.MIN
~~~

Đây là hành vi kiểm tra miền có chủ đích: Java không âm thầm wrap giá trị thời gian sang một thời điểm khác. Với nghiệp vụ cần phát hiện dữ liệu vượt giới hạn, exception là tín hiệu hữu ích và không nên bị bỏ qua.

Nhưng có những trường hợp ứng dụng muốn một phép tính luôn trả về thời điểm hợp lệ trong miền `Instant`. Ví dụ, tính hạn chót từ một timeout có thể rất lớn hoặc được cấu hình bằng giá trị sentinel. Trong trường hợp đó, phép cộng bão hòa phù hợp hơn.

## 3. Java 26 bổ sung Instant.plusSaturating(Duration)

Java 26 thêm method:

~~~java
public Instant plusSaturating(Duration duration)
~~~

Phương thức cộng `Duration` vào `Instant` với semantics bão hòa:

- Nếu kết quả sớm hơn `Instant.MIN`, trả về `Instant.MIN`.
- Nếu kết quả muộn hơn `Instant.MAX`, trả về `Instant.MAX`.
- Nếu kết quả nằm trong miền, trả về kết quả cộng thông thường.

~~~java
Instant start = Instant.MAX.minusSeconds(10);

Instant deadline = start.plusSaturating(Duration.ofSeconds(30));

System.out.println(deadline.equals(Instant.MAX)); // true
~~~

Ví dụ bắt đầu từ 10 giây trước biên trên và cộng 30 giây. Kết quả toán học vượt `Instant.MAX`, nên phương thức trả về đúng giá trị biên trên.

Phương thức này được thêm từ Java 26, thuộc API ổn định của `java.time.Instant`; không phải preview hoặc incubator. Không cần `--enable-preview` hay `--add-modules`.

## 4. Quy tắc bão hòa theo chiều dương và âm

`Duration` có thể dương, âm hoặc bằng zero. `plusSaturating` xử lý cả ba trường hợp:

| Instant ban đầu | Duration | Kết quả |
|---|---|---|
| Nằm trong miền | Dương, kết quả vẫn trong miền | Instant sau khi cộng |
| Gần `Instant.MAX` | Dương, vượt biên trên | `Instant.MAX` |
| Gần `Instant.MIN` | Âm, vượt biên dưới | `Instant.MIN` |
| `Instant.MAX` | `Duration.ZERO` | `Instant.MAX` |
| `Instant.MIN` | `Duration.ZERO` | `Instant.MIN` |
| `Instant.EPOCH` | `Duration.MAX` | `Instant.MAX` |
| `Instant.EPOCH` | `Duration.MIN` | `Instant.MIN` |

Ví dụ:

~~~java
Instant later = Instant.MAX.minusNanos(1)
    .plusSaturating(Duration.ofNanos(10));

Instant earlier = Instant.MIN.plusNanos(1)
    .plusSaturating(Duration.ofNanos(-10));

System.out.println(later.equals(Instant.MAX));     // true
System.out.println(earlier.equals(Instant.MIN));   // true
~~~

Phép cộng bão hòa không biến mọi duration thành số dương. Một duration âm vẫn dịch chuyển về quá khứ; nếu đi qua biên dưới, kết quả được chặn tại `Instant.MIN`.

## 5. So sánh plus() và plusSaturating()

Hai method có mục đích khác nhau:

| Tiêu chí | `plus(Duration)` | `plusSaturating(Duration)` |
|---|---|---|
| Kết quả nằm trong miền | Trả về thời điểm đã cộng | Trả về cùng thời điểm đã cộng |
| Kết quả vượt `Instant.MAX` | Ném exception | Trả `Instant.MAX` |
| Kết quả sớm hơn `Instant.MIN` | Ném exception | Trả `Instant.MIN` |
| Numeric overflow | Có thể ném `ArithmeticException` | Không ném vì overflow/range violation của phép cộng này |
| Mục tiêu | Phát hiện phép tính không hợp lệ | Giữ kết quả trong miền hợp lệ bằng cách chặn ở biên |

Ví dụ chọn cách xử lý:

~~~java
Instant expiry;

try {
    expiry = issuedAt.plus(validity);
} catch (DateTimeException | ArithmeticException error) {
    // Từ chối cấu hình hoặc báo dữ liệu vượt giới hạn.
}
~~~

Nếu nghiệp vụ yêu cầu từ chối thời hạn không thể biểu diễn, dùng phép cộng thông thường và xử lý lỗi.

Nếu nghiệp vụ định nghĩa rõ rằng giá trị vượt miền phải được chặn ở biên, dùng:

~~~java
Instant expiry = issuedAt.plusSaturating(validity);
~~~

Không thay tất cả lời gọi `plus()` bằng `plusSaturating()` một cách máy móc. Việc chặn ở biên có thể che giấu dữ liệu cấu hình bất thường nếu nghiệp vụ đáng lẽ phải từ chối giá trị đó.

## 6. Dùng để tính deadline từ timeout

Javadoc nêu một ứng dụng phù hợp là tính deadline từ một thời điểm bắt đầu và timeout:

~~~java
static Instant deadline(Instant start, Duration timeout) {
    if (timeout.isNegative()) {
        throw new IllegalArgumentException("timeout must not be negative");
    }

    return start.plusSaturating(timeout);
}
~~~

Hàm trên áp dụng quy tắc nghiệp vụ timeout không âm. Nếu timeout quá lớn, deadline được chặn tại `Instant.MAX` thay vì làm phép tính thất bại.

Có thể dùng với `Clock` để kiểm thử xác định:

~~~java
static Instant deadline(Clock clock, Duration timeout) {
    if (timeout.isNegative()) {
        throw new IllegalArgumentException("timeout must not be negative");
    }

    return clock.instant().plusSaturating(timeout);
}
~~~

Trong test, truyền `Clock.fixed(...)` để xác nhận deadline không phụ thuộc thời gian thực:

~~~java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-27T10:00:00Z"),
    ZoneOffset.UTC
);

Instant result = deadline(fixed, Duration.ofMinutes(15));

assertEquals(
    Instant.parse("2026-11-27T10:15:00Z"),
    result
);
~~~

`Clock` giúp tách nguồn thời gian khỏi logic và làm cho test tái lập được. Khi timeout là cấu hình do người dùng hoặc hệ thống bên ngoài cung cấp, cần xác thực dấu, đơn vị và giới hạn nghiệp vụ trước khi tính deadline.

## 7. Instant.MIN/MAX không phải biểu diễn vô hạn

Một số ứng dụng dùng `Instant.MAX` để biểu diễn “không hết hạn” hoặc `Instant.MIN` để biểu diễn “có hiệu lực từ trước mọi thời điểm”. Cách này có thể hữu ích nếu toàn bộ hệ thống hiểu cùng quy ước, nhưng cần cân nhắc:

- `Instant.MAX` là một thời điểm hữu hạn, không phải giá trị infinity.
- Database, JSON serializer, message broker hoặc hệ thống ngoài có thể không hỗ trợ năm ±1 tỷ.
- Một số thư viện date/time hoặc giao diện người dùng có miền năm nhỏ hơn Java Time API.
- Nếu `Instant.MAX` được dùng làm sentinel, phép tính và so sánh vẫn coi nó là thời điểm thực ở biên.
- Việc serialize hoặc chuyển đổi sang `java.sql.Timestamp` hay định dạng bên ngoài có thể có giới hạn riêng.

Nếu nghiệp vụ thật sự có khái niệm “không có deadline”, mô hình rõ ràng hơn thường là:

~~~java
record Expiration(Optional<Instant> deadline) {}
~~~

Hoặc dùng một kiểu miền riêng như `Deadline` với trạng thái `NEVER` và `AT(Instant)`. Chỉ dùng `Instant.MAX` làm sentinel khi hợp đồng dữ liệu của ứng dụng quy định rõ và mọi tầng đều xử lý được giá trị đó.

Tương tự, không dùng `Instant.MIN` như giá trị null thay thế nếu hệ thống cần phân biệt “chưa có thời gian”, “vô hiệu hóa” và “thời điểm rất xa trong quá khứ”.

## 8. Duration.MIN và Duration.MAX trong Java 26

Java 26 cũng bổ sung hai hằng biên vào `java.time.Duration`:

- `Duration.MIN`: duration nhỏ nhất, có `Long.MIN_VALUE` giây.
- `Duration.MAX`: duration lớn nhất, có `Long.MAX_VALUE` giây và 999.999.999 nanosecond.

Chúng được thêm từ Java 26. Javadoc mô tả chúng là giá trị hữu ích cho sentinel hoặc kiểm thử, đồng thời cảnh báo cần cẩn thận khi thực hiện số học vì có nguy cơ cao phát sinh `ArithmeticException` hoặc `DateTimeException`.

~~~java
Duration smallest = Duration.MIN;
Duration largest = Duration.MAX;

System.out.println(smallest.getSeconds()); // Long.MIN_VALUE
System.out.println(largest.getSeconds());  // Long.MAX_VALUE
System.out.println(largest.getNano());     // 999999999
~~~

Các hằng này biểu diễn biên của kiểu `Duration`, không phải thời gian vô hạn. `Duration.MAX` và `Duration.MIN` vẫn có thể được cộng vào `Instant` bằng `plusSaturating`; kết quả sẽ được chặn ở `Instant.MAX` hoặc `Instant.MIN` nếu vượt miền.

## 9. Cẩn thận khi đảo dấu Duration.MIN

Miền `Duration` không đối xứng hoàn toàn ở hai phía vì trường giây dùng kiểu `long`. Giá trị âm nhỏ nhất có độ lớn không thể biểu diễn bằng một duration dương tương ứng.

Do đó, các thao tác sau có thể ném `ArithmeticException`:

~~~java
Duration.MIN.negated();
Duration.MIN.abs();
~~~

Không viết helper trừ thời gian theo cách luôn gọi `duration.negated()` rồi truyền vào `plusSaturating` nếu đầu vào có thể là `Duration.MIN`:

~~~java
// Không an toàn với Duration.MIN
Instant result = start.plusSaturating(duration.negated());
~~~

`Instant.plusSaturating` chỉ cung cấp phép cộng bão hòa. Java 26 không thêm `minusSaturating(Duration)`. Nếu cần trừ một duration bất kỳ và muốn bão hòa, hãy định nghĩa rõ semantics của ứng dụng, xử lý riêng giá trị biên và kiểm thử cả trường hợp `Duration.MIN`; không giả định có thể đảo dấu mọi Duration.

Đối với các phép toán trên chính `Duration`, `plus`, `minus`, `multipliedBy`, `negated` và `abs` vẫn có thể ném exception khi kết quả vượt miền. Hai hằng `MIN` và `MAX` không làm các phép toán đó tự động bão hòa.

## 10. plusSaturating không thay đổi các phép toán Instant khác

Tên method có chủ ý cụ thể: `plusSaturating(Duration)`. Không suy rộng semantics của nó sang mọi phép toán thời gian.

| Phương thức | Bão hòa ở biên? |
|---|---|
| `plusSaturating(Duration)` | Có |
| `plus(Duration)` | Không |
| `plusSeconds(long)` | Không |
| `plusMillis(long)` | Không |
| `plusNanos(long)` | Không |
| `minus(Duration)` | Không |
| `minusSeconds(long)` | Không |
| `minusMillis(long)` | Không |
| `minusNanos(long)` | Không |

Ví dụ:

~~~java
Instant result = Instant.MAX.plusSaturating(Duration.ofSeconds(1));
// Trả về Instant.MAX

Instant invalid = Instant.MAX.plusSeconds(1);
// Ném DateTimeException
~~~

Các factory như `Instant.ofEpochSecond(...)`, `Instant.ofEpochMilli(...)` cũng vẫn kiểm tra miền đầu vào. `plusSaturating` không làm cho mọi cách tạo hoặc chuyển đổi Instant trở thành bão hòa.

## 11. Kiểm thử biên và trường hợp cực trị

Nên kiểm tra ít nhất các nhóm sau:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class InstantSaturationTest {
    @Test
    void keepsResultWhenItFits() {
        Instant start = Instant.parse("2026-11-27T10:00:00Z");

        assertEquals(
            Instant.parse("2026-11-27T10:30:00Z"),
            start.plusSaturating(Duration.ofMinutes(30))
        );
    }

    @Test
    void clampsAtMaximum() {
        assertEquals(
            Instant.MAX,
            Instant.MAX.plusSaturating(Duration.ofNanos(1))
        );

        assertEquals(
            Instant.MAX,
            Instant.EPOCH.plusSaturating(Duration.MAX)
        );
    }

    @Test
    void clampsAtMinimum() {
        assertEquals(
            Instant.MIN,
            Instant.MIN.plusSaturating(Duration.ofNanos(-1))
        );

        assertEquals(
            Instant.MIN,
            Instant.EPOCH.plusSaturating(Duration.MIN)
        );
    }

    @Test
    void zeroDoesNotMoveInstant() {
        Instant start = Instant.parse("2026-11-27T10:00:00Z");

        assertEquals(start, start.plusSaturating(Duration.ZERO));
    }

    @Test
    void nullDurationIsRejected() {
        assertThrows(
            NullPointerException.class,
            () -> Instant.EPOCH.plusSaturating(null)
        );
    }
}
~~~

Các test này xác nhận:

- Kết quả trong miền không bị thay đổi ngoài phép cộng thông thường.
- Kết quả vượt biên trên được chặn tại `Instant.MAX`.
- Kết quả vượt biên dưới được chặn tại `Instant.MIN`.
- Duration zero giữ nguyên thời điểm.
- Đầu vào null vẫn bị từ chối.

Có thể bổ sung test ngay sát biên nhưng vẫn hợp lệ:

~~~java
assertEquals(
    Instant.MAX,
    Instant.MAX.minusNanos(1)
        .plusSaturating(Duration.ofNanos(1))
);

assertEquals(
    Instant.MIN,
    Instant.MIN.plusNanos(1)
        .plusSaturating(Duration.ofNanos(-1))
);
~~~

Không chỉ test trường hợp overflow. Các trường hợp sát biên nhưng vừa đúng miền giúp phát hiện lỗi làm tròn hoặc kiểm tra điều kiện vượt biên sai.

## 12. Deadline và đồng hồ monotonic

`Instant` biểu diễn thời điểm trên timeline dân sự. Nó phù hợp để lưu timestamp, thời điểm phát hành, thời hạn có thể hiển thị, audit và trao đổi giữa hệ thống.

Tuy nhiên, đồng hồ hệ thống dùng cho `Instant.now()` không được đảm bảo tiến lên đơn điệu. Đồng hồ có thể được điều chỉnh bởi đồng bộ thời gian, thay đổi cấu hình hoặc hệ điều hành. Vì vậy, không nên dùng chênh lệch hai giá trị `Instant.now()` làm cơ sở duy nhất để đo chính xác thời gian thực thi hoặc timeout ngắn.

Nếu cần đo thời gian trôi qua trong cùng tiến trình, dùng `System.nanoTime()` hoặc một API dựa trên nguồn monotonic. `plusSaturating` giải quyết overflow/range của timestamp; nó không biến wall clock thành monotonic clock và không thay thế cơ chế timeout của scheduler hoặc network client.

Một cách phân chia thường dùng:

- Lưu thời điểm bắt đầu/kết thúc nghiệp vụ: `Instant`.
- Tính deadline cần trao đổi hoặc lưu trữ: `Instant.plusSaturating(timeout)`, sau khi xác thực timeout.
- Đo thời gian xử lý hoặc giới hạn thời gian chờ trong một tiến trình: `System.nanoTime()` hoặc API timeout chuyên dụng.
- Kiểm thử logic deadline: inject `Clock` và dùng `Clock.fixed(...)`.

## 13. Trạng thái API và tương thích phiên bản

Trong Java 26:

| API | Có từ | Trạng thái |
|---|---:|---|
| `Instant.MIN`, `Instant.MAX` | Java 8 | API ổn định |
| `Instant.plusSaturating(Duration)` | Java 26 | API ổn định |
| `Duration.MIN`, `Duration.MAX` | Java 26 | API ổn định |

Các API mới thuộc module `java.base`, package `java.time`. Không cần preview flag hoặc module incubator.

Nếu biên dịch với JDK 26 nhưng chạy trên JDK trước 26, method `Instant.plusSaturating` và các constant `Duration.MIN/MAX` không tồn tại ở runtime cũ. Binary tham chiếu trực tiếp các thành phần mới có thể thất bại khi liên kết hoặc tải class. Hãy đặt baseline runtime là Java 26 nếu dùng trực tiếp, hoặc xây adapter tương thích và kiểm thử trên từng runtime được hỗ trợ.

Không tự viết một phép cộng bão hòa bằng cách bắt tất cả exception rồi trả `Instant.MAX`. Cách đó có thể biến lỗi null, lỗi logic hoặc lỗi đầu vào thành một deadline có vẻ hợp lệ. Nếu phải hỗ trợ JDK cũ, helper tự triển khai cần kiểm tra dấu, biên và overflow rõ ràng, đồng thời có test cho Duration.MIN/MAX.

## 14. Checklist sử dụng an toàn

- [ ] Xác định nghiệp vụ muốn từ chối overflow hay chặn ở biên.
- [ ] Dùng `plusSaturating(Duration)` khi semantics bão hòa thực sự phù hợp.
- [ ] Kiểm tra timeout âm nếu nghiệp vụ yêu cầu timeout không âm.
- [ ] Không coi `Instant.MIN/MAX` là vô hạn hoặc null.
- [ ] Không giả định database, serializer hoặc hệ thống ngoài hỗ trợ năm ±1 tỷ.
- [ ] Hiểu `Duration.MIN/MAX` là giá trị hữu hạn dùng làm sentinel/test.
- [ ] Không gọi `Duration.MIN.negated()` hoặc `Duration.MIN.abs()` mà không xử lý overflow.
- [ ] Không suy ra `minusSaturating` tồn tại từ `plusSaturating`.
- [ ] Không thay toàn bộ phép cộng thông thường bằng phép cộng bão hòa.
- [ ] Dùng `Clock` để kiểm thử deadline và nguồn thời gian.
- [ ] Dùng monotonic clock để đo thời gian trôi qua.
- [ ] Kiểm thử giá trị trong miền, sát biên, vượt biên, zero và null.

## Kết luận

Java 26 bổ sung `Instant.plusSaturating(Duration)` để cộng thời lượng mà không vượt miền biểu diễn của Instant: kết quả quá muộn được chặn tại `Instant.MAX`, kết quả quá sớm được chặn tại `Instant.MIN`. Đây là API Java SE ổn định, không phải preview. Java 26 cũng bổ sung `Duration.MIN` và `Duration.MAX` làm giá trị biên hữu hạn, hữu ích cho sentinel và test nhưng cần thận trọng khi tính toán. Chỉ dùng bão hòa khi nghiệp vụ muốn chặn kết quả; nếu cần phát hiện dữ liệu vượt giới hạn, giữ phép cộng thông thường. Hãy nhớ rằng Instant.MIN/MAX không phải vô hạn, `plusSaturating` không có bản `minusSaturating`, và timestamp wall-clock không thay thế đồng hồ monotonic để đo timeout.

## Tài liệu tham khảo

- [Java SE 26 API – Instant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
- [Java SE 26 API – Duration](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html)
- [JDK 26 Release Notes – Adding a Duration to an Instant with Saturation](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JDK 26 Release Notes – java.time.Duration Minimum and Maximum Values](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [Java SE 26 API – Clock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html)
