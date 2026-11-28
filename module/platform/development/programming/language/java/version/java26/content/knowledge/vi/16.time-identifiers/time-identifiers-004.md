# `Duration.MIN`, `Duration.MAX` và giá trị biên

Java 26 bổ sung hai hằng `Duration.MIN` và `Duration.MAX` để biểu diễn chính xác hai đầu của miền giá trị mà `java.time.Duration` hỗ trợ. Chúng hữu ích khi viết thuật toán cần giá trị khởi tạo cực tiểu/cực đại, kiểm thử overflow và xử lý các khoảng thời gian rất lớn. Tuy nhiên, `Duration` vẫn là một giá trị thời gian hữu hạn; `MIN` và `MAX` không có nghĩa là âm vô cực, dương vô cực hoặc “không giới hạn thời gian”.

`Duration.MIN` và `Duration.MAX` là API chính thức từ JDK 26 (`Since: 26`), không phải preview hay incubator. JDK 25 trở xuống chỉ có `Duration.ZERO`; nếu cần tương thích source với JDK cũ, có thể tạo hai giá trị biên bằng các factory `ofSeconds` đã tồn tại từ Java 8.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả cấu trúc giây và nano giây của `Duration` và cách chuẩn hóa giá trị âm.
- Xác định chính xác giá trị của `Duration.MIN` và `Duration.MAX`.
- Giải thích vì sao miền `Duration` bất đối xứng và tại sao `abs()` của `MIN` có thể overflow.
- Dự đoán các phép cộng, trừ, nhân, đổi đơn vị và chuyển đổi có thể ném `ArithmeticException`.
- Viết test cho các giá trị sát biên và xác nhận trường hợp overflow.
- Phân biệt giới hạn của `Duration` với giới hạn của `Instant`.
- Dùng `Instant.plusSaturating(Duration)` khi nghiệp vụ muốn giới hạn kết quả ở `Instant.MIN` hoặc `Instant.MAX`.
- Chọn cách biểu diễn sentinel và timeout mà không nhầm một giá trị hữu hạn với vô cực.

## 1. `Duration` lưu trữ thời gian như thế nào?

`Duration` biểu diễn một khoảng thời gian theo giây và nano giây. Đây là giá trị có hướng: có thể dương, bằng không hoặc âm. Lớp này immutable và thread-safe; hai đối tượng có cùng giá trị được xem là tương đương. Vì là value-based class, không dùng instance `Duration` làm monitor cho `synchronized`.

Về mặt biểu diễn, một `Duration` gồm hai phần:

- `seconds`: kiểu `long`.
- `nanos`: kiểu `int`, luôn nằm trong khoảng từ `0` đến `999_999_999`.

Tổng thời lượng bằng số giây cộng phần nano giây điều chỉnh. Phần nano luôn không âm, kể cả khi tổng thời lượng là số âm. Ví dụ:

```java
Duration negativeOneNano = Duration.ofNanos(-1);

System.out.println(negativeOneNano.getSeconds()); // -1
System.out.println(negativeOneNano.getNano());    // 999999999
```

Giá trị trên tương đương `-1 giây + 999_999_999 nano giây`, tức `-1 nano giây`. Không được đọc `getNano()` rồi kết luận rằng duration này dương. Dấu của tổng giá trị phải được xác định từ toàn bộ cặp giây/nano; dùng `isNegative()`, `isZero()` và `isPositive()` khi cần phân loại.

`Duration` cũng không phải `Period`. `Duration.ofDays(1)` luôn tương đương đúng 24 giờ (86.400 giây), không phải “một ngày theo lịch” có thể dài 23 hoặc 25 giờ do chuyển đổi daylight saving time. Với tháng, năm và đơn vị lịch, dùng các kiểu date-based phù hợp như `Period` hoặc thao tác trên `ZonedDateTime`.

## 2. Hai đầu của miền giá trị trong Java 26

Java 26 bổ sung:

```java
import java.time.Duration;

Duration min = Duration.MIN;
Duration max = Duration.MAX;
Duration zero = Duration.ZERO;
```

Giá trị chính xác:

| Hằng | `getSeconds()` | `getNano()` | Ý nghĩa |
|---|---:|---:|---|
| `Duration.MIN` | `Long.MIN_VALUE` | `0` | Duration nhỏ nhất, âm nhất |
| `Duration.ZERO` | `0` | `0` | Không có thời lượng |
| `Duration.MAX` | `Long.MAX_VALUE` | `999_999_999` | Duration lớn nhất, dương nhất |

Có thể xác nhận bằng code:

```java
System.out.println(Duration.MIN.getSeconds() == Long.MIN_VALUE); // true
System.out.println(Duration.MIN.getNano() == 0);                  // true

System.out.println(Duration.MAX.getSeconds() == Long.MAX_VALUE); // true
System.out.println(Duration.MAX.getNano() == 999_999_999);       // true
```

Miền giá trị không đối xứng quanh zero. Phần giây nhỏ nhất là `-2^63`, trong khi phần giây lớn nhất là `2^63 - 1` và còn có thể cộng thêm `999_999_999` nano giây. Vì vậy không tồn tại một giá trị dương có độ lớn bằng `Duration.MIN`.

Hai hằng này được thiết kế để dùng làm giá trị biên hoặc sentinel trong thuật toán và test. API ghi rõ cần thận trọng khi thực hiện số học với chúng vì nguy cơ `ArithmeticException` hoặc `DateTimeException` cao.

## 3. Tạo lại giá trị biên bằng factory

`Duration.ofSeconds(long)` và `Duration.ofSeconds(long, long)` đã có từ Java 8. Do đó, trên JDK 25 trở xuống, có thể biểu diễn hai đầu miền như sau:

```java
static final Duration MIN_SUPPORTED_DURATION =
        Duration.ofSeconds(Long.MIN_VALUE);

static final Duration MAX_SUPPORTED_DURATION =
        Duration.ofSeconds(Long.MAX_VALUE, 999_999_999);
```

Trên JDK 26 trở lên, nên dùng trực tiếp `Duration.MIN` và `Duration.MAX` để diễn đạt ý định rõ ràng. Nếu một thư viện cần biên dịch bằng `--release 25`, không tham chiếu hai field mới vì chúng chưa có trong API Java 25.

Factory hai tham số chuẩn hóa `nanoAdjustment` vào khoảng `0..999_999_999`, đồng thời điều chỉnh phần giây. Ví dụ:

```java
Duration a = Duration.ofSeconds(3, 1);
Duration b = Duration.ofSeconds(4, -999_999_999);
Duration c = Duration.ofSeconds(2, 1_000_000_001);

System.out.println(a.equals(b)); // true
System.out.println(a.equals(c)); // true
```

Việc chuẩn hóa có thể làm phần giây vượt khỏi `long`. Nếu điều chỉnh khiến giá trị vượt miền `Duration`, factory ném `ArithmeticException`. Ví dụ tạo một nano giây nhỏ hơn `MIN` hoặc lớn hơn `MAX` sẽ thất bại thay vì wrap-around.

## 4. Vì sao `abs(Duration.MIN)` bị overflow?

Với số nguyên có dấu 64-bit:

- `Long.MIN_VALUE = -9_223_372_036_854_775_808`.
- `Long.MAX_VALUE =  9_223_372_036_854_775_807`.

Không có số `long` dương tương ứng với trị tuyệt đối của `Long.MIN_VALUE`. `Duration` có thêm nano giây nhưng phần đó không thể bù cho một giây vượt khỏi miền lưu trữ. Vì thế:

```java
Duration.MIN.negated(); // ArithmeticException
Duration.MIN.abs();     // ArithmeticException
```

Trong khi đó, nhiều phép toán ở sát biên vẫn hợp lệ:

```java
Duration justAboveMin = Duration.MIN.plusNanos(1);
Duration justBelowMax = Duration.MAX.minusNanos(1);

System.out.println(justAboveMin.getSeconds() == Long.MIN_VALUE); // true
System.out.println(justAboveMin.getNano() == 1);                  // true

System.out.println(justBelowMax.getSeconds() == Long.MAX_VALUE); // true
System.out.println(justBelowMax.getNano() == 999_999_998);       // true
```

Một quan hệ biên hữu ích khác:

```java
Duration result = Duration.MIN.plus(Duration.MAX);
System.out.println(result.equals(Duration.ofNanos(-1))); // true
```

Tổng của hai đầu miền là `-1 nano giây`, vì phần giây `Long.MIN_VALUE + Long.MAX_VALUE` bằng `-1`, cộng phần nano `999_999_999` cho kết quả `-0.000000001` giây. Phép cộng này hợp lệ và cho thấy cách biểu diễn hai phần hoạt động ở vùng biên.

## 5. Phép toán có thể vượt miền `Duration`

`Duration` là immutable; các phép toán trả về instance mới. Nếu kết quả không biểu diễn được bằng `long seconds` và `0..999_999_999 nanos`, các phép toán số học ném `ArithmeticException`, không wrap-around như phép cộng `long` thông thường.

| Biểu thức | Kết quả |
|---|---|
| `Duration.MIN.plusNanos(1)` | Thành công; lớn hơn MIN một nano giây |
| `Duration.MIN.minusNanos(1)` | `ArithmeticException` |
| `Duration.MAX.minusNanos(1)` | Thành công; nhỏ hơn MAX một nano giây |
| `Duration.MAX.plusNanos(1)` | `ArithmeticException` |
| `Duration.MIN.negated()` | `ArithmeticException` |
| `Duration.MIN.abs()` | `ArithmeticException` |
| `Duration.MAX.plus(Duration.ofSeconds(1))` | `ArithmeticException` |
| `Duration.MIN.minus(Duration.ofSeconds(1))` | `ArithmeticException` |
| `Duration.MAX.multipliedBy(2)` | `ArithmeticException` |

Ví dụ xử lý overflow có chủ đích:

```java
static Duration addOrReject(Duration current, Duration increment) {
    try {
        return current.plus(increment);
    } catch (ArithmeticException overflow) {
        throw new IllegalArgumentException(
                "Tổng thời lượng vượt miền Duration", overflow);
    }
}
```

Chỉ bắt `ArithmeticException` khi có chính sách nghiệp vụ cụ thể. Không tự thay overflow bằng `Duration.MAX` hoặc `Duration.MIN` nếu nghiệp vụ không định nghĩa cách bão hòa như vậy; việc âm thầm clamp có thể làm deadline, thời hạn lưu trữ hoặc thời gian tính phí sai.

Các factory cũng có thể overflow trước khi tạo được duration. Ví dụ `Duration.ofDays(long)` nhân số ngày với 86.400 giây; một đầu vào quá lớn sẽ ném `ArithmeticException`. Đừng giả định tham số kiểu `long` luôn có thể chuyển đổi sang mọi đơn vị thời gian.

## 6. Chuyển đổi sang millisecond và nanosecond

`Duration` có thể lưu một khoảng thời gian lớn hơn rất nhiều so với miền biểu diễn của một `long` nano giây. Vì thế, một `Duration` hợp lệ không nhất thiết chuyển đổi được thành tổng nanosecond hoặc millisecond kiểu `long`.

```java
Duration small = Duration.ofSeconds(2);

long millis = small.toMillis(); // 2000
long nanos = small.toNanos();   // 2_000_000_000
```

Nhưng với các giá trị biên:

```java
Duration.MAX.toNanos(); // ArithmeticException
Duration.MIN.toNanos(); // ArithmeticException
Duration.MAX.toMillis(); // ArithmeticException
Duration.MIN.toMillis(); // ArithmeticException
```

Lý do là tổng nanosecond hoặc millisecond vượt `Long.MAX_VALUE` hoặc thấp hơn `Long.MIN_VALUE`. `toMillis()` còn bỏ phần độ chính xác nhỏ hơn millisecond nếu giá trị vẫn nằm trong miền biểu diễn; nó không làm tròn lên. `toNanos()` và `toMillis()` ném `ArithmeticException` nếu tổng không vừa `long`.

Nếu cần hiển thị hoặc tính toán với giá trị cực lớn, giữ dạng `Duration`, hoặc dùng cặp `getSeconds()`/`getNano()` hay `BigInteger` cho phép tính tổng hợp. Đừng ép về `long nanos` rồi kỳ vọng kết quả không mất dữ liệu.

Các phép đổi sang đơn vị lớn hơn như `toDays()`, `toHours()`, `toMinutes()` và `toSeconds()` chia phần giây theo đơn vị tương ứng nên phù hợp hơn khi cần đọc phần nguyên ở giá trị biên. Chúng trả về số đơn vị nguyên, bỏ phần nhỏ hơn đơn vị đó.

## 7. `Duration` hợp lệ không có nghĩa có thể cộng vào mọi `Instant`

Miền của `Instant` khác miền của `Duration`. Một `Duration` cực lớn có thể hoàn toàn hợp lệ, nhưng cộng nó vào một mốc thời gian có thể vượt `Instant.MIN` hoặc `Instant.MAX`.

Thông thường:

```java
Instant deadline = Instant.now().plus(timeout);
```

`Instant.plus(Duration)` ném `DateTimeException` nếu kết quả vượt miền `Instant`; phép tính cũng có thể ném `ArithmeticException` khi có overflow số học.

Java 26 bổ sung `Instant.plusSaturating(Duration)`. Phương thức này dùng saturated arithmetic:

- Nếu kết quả sớm hơn `Instant.MIN`, trả về `Instant.MIN`.
- Nếu kết quả muộn hơn `Instant.MAX`, trả về `Instant.MAX`.
- Nếu kết quả nằm trong miền, trả về kết quả cộng bình thường.

```java
import java.time.Duration;
import java.time.Instant;

Instant fromEpochWithHugePositive =
        Instant.EPOCH.plusSaturating(Duration.MAX);

Instant fromEpochWithHugeNegative =
        Instant.EPOCH.plusSaturating(Duration.MIN);

System.out.println(fromEpochWithHugePositive.equals(Instant.MAX)); // true
System.out.println(fromEpochWithHugeNegative.equals(Instant.MIN)); // true
```

`plusSaturating` hữu ích khi tính deadline hoặc giới hạn thời gian mà chính sách yêu cầu kẹp kết quả vào miền Instant. Nó không thay đổi `Duration`, không làm `Duration.MAX` thành vô hạn và không thay thế `Duration.plus()` khi overflow của chính duration cần được phát hiện. Nếu việc vượt miền là lỗi dữ liệu nghiệp vụ, tiếp tục dùng phép cộng thông thường và xử lý exception.

Khi tính timeout, hãy kiểm tra giá trị âm nếu nghiệp vụ chỉ cho phép timeout không âm:

```java
static Instant deadlineFrom(Instant start, Duration timeout) {
    if (timeout.isNegative()) {
        throw new IllegalArgumentException("Timeout không được âm");
    }
    return start.plusSaturating(timeout);
}
```

Không dùng phép cộng bão hòa để che giấu một timeout âm hoặc dữ liệu đầu vào sai. Saturation chỉ giải quyết trường hợp kết quả vượt miền `Instant`.

## 8. Dùng MIN/MAX làm sentinel và giới hạn timeout

Một thuật toán tìm giá trị nhỏ nhất có thể khởi tạo kết quả tạm bằng `Duration.MAX`; thuật toán tìm giá trị lớn nhất có thể khởi tạo bằng `Duration.MIN`:

```java
static Duration shortest(List<Duration> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("Danh sách phải có phần tử");
    }

    Duration best = Duration.MAX;
    for (Duration value : values) {
        if (value.compareTo(best) < 0) {
            best = value;
        }
    }
    return best;
}
```

Phải xử lý collection rỗng. Nếu không có phần tử, sentinel vẫn còn nguyên và có thể bị nhầm thành kết quả thật. Với bài toán mà mọi giá trị đều có ý nghĩa, cân nhắc trả `Optional<Duration>` hoặc dùng một cờ `found` thay vì dựa vào sentinel.

Không tự động dùng `Duration.MAX` làm “không timeout” khi truyền vào API khác. Một API có thể:

- Chuyển duration thành nanosecond hoặc millisecond kiểu `long` và gặp overflow.
- Chỉ chấp nhận duration không âm.
- Diễn giải `Duration.ZERO` là không chờ hoặc không timeout.
- Có giới hạn timeout riêng của hệ điều hành, giao thức hoặc thư viện.

Hãy đọc hợp đồng của API nhận timeout. `Duration.MAX` là giá trị lớn nhất mà lớp `Duration` biểu diễn được, không phải quy ước toàn cục cho vô thời hạn. Tương tự, `Duration.MIN` không phải giá trị “chưa đặt” an toàn nếu dữ liệu âm cũng hợp lệ trong miền nghiệp vụ.

## 9. Kiểm thử các giá trị biên bằng JUnit

Kiểm thử biên nên xác nhận cả giá trị lớn nhất/nhỏ nhất hợp lệ và phép toán ngay bên ngoài miền. Ví dụ dưới đây dùng JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.Instant;

import org.junit.jupiter.api.Test;

class DurationBoundaryTest {
    @Test
    void exposesExactMinimumAndMaximum() {
        assertEquals(Long.MIN_VALUE, Duration.MIN.getSeconds());
        assertEquals(0, Duration.MIN.getNano());

        assertEquals(Long.MAX_VALUE, Duration.MAX.getSeconds());
        assertEquals(999_999_999, Duration.MAX.getNano());
    }

    @Test
    void permitsValuesOneNanosecondInsideTheBounds() {
        assertEquals(
                Duration.ofSeconds(Long.MIN_VALUE, 1),
                Duration.MIN.plusNanos(1));

        assertEquals(
                Duration.ofSeconds(Long.MAX_VALUE, 999_999_998),
                Duration.MAX.minusNanos(1));
    }

    @Test
    void detectsArithmeticOverflow() {
        assertThrows(ArithmeticException.class, () -> Duration.MIN.negated());
        assertThrows(ArithmeticException.class, () -> Duration.MIN.abs());
        assertThrows(ArithmeticException.class, () -> Duration.MIN.minusNanos(1));
        assertThrows(ArithmeticException.class, () -> Duration.MAX.plusNanos(1));
        assertThrows(ArithmeticException.class, () -> Duration.MAX.toNanos());
    }

    @Test
    void addingTheTwoBoundsProducesNegativeOneNanosecond() {
        assertEquals(Duration.ofNanos(-1), Duration.MIN.plus(Duration.MAX));
    }

    @Test
    void instantSaturatesAtItsOwnBounds() {
        assertEquals(Instant.MAX,
                Instant.EPOCH.plusSaturating(Duration.MAX));
        assertEquals(Instant.MIN,
                Instant.EPOCH.plusSaturating(Duration.MIN));
    }

    @Test
    void minimumIsNegativeAndMaximumIsPositive() {
        assertTrue(Duration.MIN.isNegative());
        assertTrue(Duration.MAX.isPositive());
    }
}
```

Test nên được biên dịch và chạy bằng JDK 26 trở lên vì `Duration.MIN`, `Duration.MAX` và `Instant.plusSaturating` được bổ sung trong release này. Không cần `--enable-preview` vì đây là API final.

## 10. Những lỗi thường gặp khi làm việc với giá trị biên

| Lỗi | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Gọi `Duration.MIN.abs()` để lấy độ lớn dương | Không có giá trị dương tương ứng trong miền Duration | Xử lý trường hợp MIN riêng hoặc dùng kiểu số rộng hơn như `BigInteger` nếu cần trị tuyệt đối chính xác |
| Gọi `toNanos()` trên duration cực lớn | Tổng nano giây vượt miền `long` | Giữ `Duration`, dùng seconds/nanos hoặc `BigInteger` |
| Dùng `Duration.MAX` làm timeout vô hạn | API nhận timeout có thể đổi sang đơn vị hẹp hơn hoặc có giới hạn riêng | Kiểm tra hợp đồng timeout; biểu diễn “không timeout” bằng trạng thái riêng nếu API cần |
| Cho rằng `Duration.MAX` cộng vào `Instant` luôn thành công | Miền Instant hẹp hơn miền Duration | Dùng `plusSaturating` nếu cần clamp, hoặc xử lý exception của `plus` |
| Cho rằng nano component của duration âm cũng âm | `nanos` luôn nằm trong `0..999_999_999` | Xem cả cặp seconds/nanos hoặc dùng `isNegative()` |
| Dùng `Duration.ofDays(1)` như một ngày theo lịch | Duration quy định ngày đúng 24 giờ | Dùng `Period` hoặc `ZonedDateTime` khi cần phép toán theo lịch |
| Dùng `Duration.MIN/MAX` với `--release 25` | Hai field chưa tồn tại trong API Java 25 | Dựng giá trị tương ứng bằng `Duration.ofSeconds(...)` hoặc nâng target lên JDK 26 |

## 11. Trạng thái API và tương thích JDK

| JDK | `Duration.MIN` / `Duration.MAX` | `Instant.plusSaturating(Duration)` | Preview flag |
|---|---|---|---|
| JDK 25 trở xuống | Chưa có field; có thể dựng bằng `ofSeconds` | Chưa có | Không liên quan |
| JDK 26 | API final, `Since: 26` | API final, `Since: 26` | Không cần |
| JDK 27 | Tiếp tục là API chính thức | Tiếp tục là API chính thức | Không cần |

Khi thư viện cần hỗ trợ nhiều release, có thể tạo một lớp tiện ích nội bộ để cung cấp hai bound bằng factory trên JDK 25 và dùng field mới trên source set JDK 26+. Nếu chỉ hỗ trợ JDK 26 trở lên, dùng trực tiếp hằng API để mã nguồn dễ đọc.

Không cần module bổ sung vì `java.time` thuộc module `java.base`. Đây là API Java SE chính thức, không phải preview, incubator hoặc API nội bộ của HotSpot.

## 12. Bài tập thực hành

Viết một module nhỏ tính thời gian thực thi và deadline cho các job. Module phải xử lý dữ liệu timeout từ cấu hình, kiểm tra giá trị âm, cộng deadline và ghi nhận overflow.

**Yêu cầu:**

1. In `getSeconds()` và `getNano()` của `Duration.MIN`, `Duration.ZERO` và `Duration.MAX`.
2. Giải thích vì sao `Duration.MIN` không có trị tuyệt đối dương biểu diễn được.
3. Viết test cho `MIN.plusNanos(1)`, `MAX.minusNanos(1)`, `MIN.minusNanos(1)` và `MAX.plusNanos(1)`.
4. Chứng minh `Duration.MIN.plus(Duration.MAX)` bằng `Duration.ofNanos(-1)`.
5. Kiểm tra `toNanos()` và `toMillis()` trên hai bound; phân loại exception.
6. Tạo deadline từ `Instant.now()` với `Duration.MAX` bằng cả `plus()` và `plusSaturating()`; giải thích sự khác biệt.
7. Viết hàm timeout từ chối duration âm và dùng `plusSaturating` nếu chính sách muốn kẹp deadline vào miền Instant.
8. Viết hàm tìm thời lượng nhỏ nhất bằng `Duration.MAX` làm sentinel; xử lý rõ danh sách rỗng.
9. Giải thích cách tạo bound tương đương nếu source phải biên dịch với JDK 25.

**Kết quả mong đợi:**

- Người học xác định chính xác cặp seconds/nanos của hai bound.
- Không nhầm `Duration` với một số `long` nano giây.
- Nhận diện được các phép toán overflow và không dựa vào wrap-around.
- Biết phân biệt saturation của `Instant` với overflow của `Duration`.
- Không dùng `Duration.MAX` như một quy ước vô hạn nếu API đích không định nghĩa như vậy.
- Phân biệt API final từ Java 26 với các preview/incubator khác trong module.

## Tài liệu tham khảo

- [Duration — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html): miền giá trị, `MIN`, `MAX`, biểu diễn seconds/nanos, arithmetic và overflow.
- [Instant — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html): `plusSaturating(Duration)` và giới hạn `Instant.MIN`/`Instant.MAX`.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): bổ sung `Duration.MIN`, `Duration.MAX` và `Instant.plusSaturating`.
- [Duration — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html): API trước Java 26, chưa có hai hằng MIN/MAX.
- [java.time — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/package-summary.html): phân biệt kiểu thời gian dựa trên duration và kiểu thời gian dựa trên lịch.
