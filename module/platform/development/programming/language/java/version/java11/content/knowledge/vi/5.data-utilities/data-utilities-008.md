# TimeUnit.convert(Duration) và chuyển đổi đơn vị thời gian (Java 11)

Khi một chương trình Java cần chuyển khoảng thời gian từ giây sang mili giây, micro giây hoặc nano giây, nên dùng API để tránh nhầm hệ số và lỗi tràn số. **Từ Java 11**, `java.util.concurrent.TimeUnit` có thêm phương thức **`convert(Duration)`**, nhận trực tiếp đối tượng `java.time.Duration` rồi trả về lượng thời gian ở đơn vị đích dưới dạng `long`.

Ví dụ:

```java
Duration timeout = Duration.ofMillis(1500);
long seconds = TimeUnit.SECONDS.convert(timeout);       // 1
long micros = TimeUnit.MICROSECONDS.convert(timeout);  // 1500000
```

Đây là **đoạn mã minh họa bên trong một phương thức**, có `import java.time.Duration;` và `import java.util.concurrent.TimeUnit;`; phần 4 cung cấp chương trình hoàn chỉnh. Điểm cần nhớ là **phép đổi sang đơn vị thô hơn có thể mất phần lẻ**, còn **phép đổi sang đơn vị mịn hơn có thể tràn phạm vi `long`**.

Bài học thuộc nhóm **Tiện ích dữ liệu** của Java 11, chỉ sử dụng API còn có giá trị hiện nay. Bạn có thể thực hành trên **JDK LTS còn được nhà cung cấp cập nhật** (chẳng hạn 21 hoặc 25) và dùng `javac --release 11` để kiểm tra tương thích Java 11, miễn là compiler vẫn hỗ trợ mức nguồn đó.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt `Duration`, `TimeUnit` và đơn vị thời gian của một tham số `long`.
2. Biết cách gọi `TimeUnit.MILLISECONDS.convert(Duration)` và so sánh với `convert(long, TimeUnit)`.
3. Đổi giữa nano giây, micro giây, mili giây, giây, phút, giờ và ngày với hệ số đúng.
4. Giải thích **cắt bỏ phần lẻ về phía 0** khi chuyển sang đơn vị lớn hơn, kể cả với thời lượng âm.
5. Nhận diện **saturation**: phép chuyển đổi tràn `long` trả về `Long.MAX_VALUE` hoặc `Long.MIN_VALUE` thay vì ném lỗi tràn số.
6. Chọn chiến lược chuyển đổi phù hợp cho timeout, kiểm tra dữ liệu đầu vào và tránh nhầm thời lượng cố định với thời gian lịch.

## 2. Hai kiểu biểu diễn thời lượng

### `Duration` — giá trị khoảng thời gian

`java.time.Duration` là lớp **bất biến** mô tả một thời lượng dựa trên giây và nano giây. Có thể khởi tạo bằng `Duration.ofSeconds(2)`, `Duration.ofMillis(1500)`, `Duration.ofNanos(250)`, `Duration.ofMinutes(3)` hoặc đọc chuỗi ISO-8601 như `Duration.parse("PT2.5S")`. Một đối tượng `Duration` chứa ý nghĩa “dài bao lâu” mà không buộc người gọi nhớ một số nguyên đang mang đơn vị nào.

Ví dụ `Duration.ofMillis(1500)` biểu diễn 1,5 giây. `Duration` không đại diện một mốc giờ cụ thể như “08:30 ngày mai”; những mốc thời gian thuộc các kiểu như `Instant`, `LocalDateTime` hoặc `ZonedDateTime` theo yêu cầu nghiệp vụ.

### `TimeUnit` — đơn vị và công cụ chuyển đổi

`java.util.concurrent.TimeUnit` là một `enum` định nghĩa bảy đơn vị, từ mịn đến thô:

| Hằng `TimeUnit` | Ý nghĩa | Quy đổi |
| --- | --- | --- |
| `NANOSECONDS` | Nano giây | 1 giây = 1.000.000.000 ns |
| `MICROSECONDS` | Micro giây | 1 giây = 1.000.000 µs |
| `MILLISECONDS` | Mili giây | 1 giây = 1.000 ms |
| `SECONDS` | Giây | 1 phút = 60 giây |
| `MINUTES` | Phút | 1 giờ = 60 phút |
| `HOURS` | Giờ | 1 ngày cố định = 24 giờ |
| `DAYS` | Ngày cố định | 1 ngày = 86.400 giây |

`TimeUnit` thường xuất hiện trong API concurrency và timeout, ví dụ `BlockingQueue.poll(long timeout, TimeUnit unit)`, `Lock.tryLock(long time, TimeUnit unit)` hoặc `CompletableFuture.orTimeout(long timeout, TimeUnit unit)`. Ý nghĩa của cặp đối số `(long, TimeUnit)` là “giá trị `long` này đo bằng đơn vị nào”, giúp tránh lỗi đưa số mili giây vào nơi yêu cầu giây.

**Quan trọng:** `TimeUnit.DAYS` luôn là **24 giờ cố định**. Một **ngày theo lịch** trong múi giờ có giờ mùa hè (DST) có thể không tương ứng 24 giờ; tháng và năm còn có độ dài biến đổi. Không dùng `TimeUnit` như công cụ tính ngày tháng lịch. Khi cần thời lượng trôi qua trên trục thời gian, dùng `Duration`; khi cần cộng ngày, tháng, năm theo lịch, sử dụng kiểu thời gian lịch phù hợp, chẳng hạn `LocalDate`/`ZonedDateTime` cùng `Period` hoặc phép toán lịch.

## 3. API chính: `TimeUnit.convert(Duration)`

Chữ ký:

```java
public long convert(Duration duration)
```

Phương thức này nằm trên **đơn vị đích**. Cách đọc:

```java
long milliseconds = TimeUnit.MILLISECONDS.convert(duration);
```

nghĩa là “chuyển `duration` sang **mili giây**”. `duration` là `Duration` nguồn; `TimeUnit.MILLISECONDS` xác định đơn vị của kết quả; kiểu trả về là `long`.

**Hợp đồng quan trọng của Java 11:**

- Phương thức **có từ Java 11** và vẫn tồn tại trong các JDK hiện đại.
- `TimeUnit.SECONDS.convert(Duration.ofMillis(1500))` cho kết quả `1`, không phải `1.5`, vì kiểu trả về là `long` và phần nhỏ hơn một giây bị bỏ.
- Nếu kết quả không biểu diễn được bằng `long`, giá trị sẽ **bão hòa về biên**: dương tràn thành `Long.MAX_VALUE`, âm tràn thành `Long.MIN_VALUE`.
- Nếu tham số `duration` là `null`, phương thức ném `NullPointerException`.
- Đối số âm được cho phép về mặt chuyển đổi. **Ứng dụng gọi timeout** phải tự quyết định có chấp nhận thời lượng âm hoặc bằng 0 hay không.

Với một đơn vị `unit`, hợp đồng API cũng cho biết:

```java
unit.convert(Duration.ofNanos(n))
```

tương đương (về kết quả) với:

```java
unit.convert(n, TimeUnit.NANOSECONDS)
```

và:

```java
unit.convert(Duration.of(n, unit.toChronoUnit()))
```

tương đương `n` khi không xảy ra tràn số. Cả hai quy tắc cho phép kiểm tra logic chuyển đổi mà không tự nhân các hệ số.

### Overload nhận số nguyên và đơn vị nguồn

`TimeUnit` cũng có phương thức:

```java
public long convert(long sourceDuration, TimeUnit sourceUnit)
```

Ví dụ:

```java
long millis = TimeUnit.MILLISECONDS.convert(2L, TimeUnit.SECONDS);
// millis = 2000
```

Cả hai overload vẫn hữu ích hiện nay:

| Dữ liệu đang có | Cách viết | Vì sao |
| --- | --- | --- |
| `Duration.ofSeconds(2)` | `TimeUnit.MILLISECONDS.convert(duration)` | Đã có đối tượng thời lượng, không cần tách giây/nano giây |
| Số `2L` với đơn vị `SECONDS` | `TimeUnit.MILLISECONDS.convert(2L, TimeUnit.SECONDS)` | API hoặc cấu hình đã có cặp giá trị và đơn vị |
| `1500L` mili giây | `TimeUnit.SECONDS.convert(1500L, TimeUnit.MILLISECONDS)` | Chuyển đơn vị có nguồn xác định |
| Một `Duration` cần giữ phần lẻ | Giữ nguyên `Duration` hoặc chọn đơn vị mịn hơn | Kết quả kiểu `long` không giữ được phần lẻ của đơn vị đích |

Không nên dùng phép nhân thủ công kiểu `seconds * 1000` khi bài toán có thể vượt miền `long`; API chuẩn làm rõ đơn vị và có quy tắc xử lý tràn số xác định.

## 4. Ví dụ hoàn chỉnh: một `Duration` đổi sang nhiều đơn vị

Tạo tệp **`TimeUnitDemo.java`**:

```java
import java.time.Duration;
import java.time.temporal.ChronoUnit;
import java.util.concurrent.TimeUnit;

public class TimeUnitDemo {
    public static void main(String[] args) {
        Duration duration = Duration.ofSeconds(2).plusMillis(750);

        System.out.println("Duration: " + duration);
        System.out.println("Seconds: " +
                TimeUnit.SECONDS.convert(duration));
        System.out.println("Milliseconds: " +
                TimeUnit.MILLISECONDS.convert(duration));
        System.out.println("Microseconds: " +
                TimeUnit.MICROSECONDS.convert(duration));
        System.out.println("Nanoseconds: " +
                TimeUnit.NANOSECONDS.convert(duration));
        System.out.println("Minutes: " +
                TimeUnit.MINUTES.convert(duration));

        System.out.println("From 2 seconds to millis: " +
                TimeUnit.MILLISECONDS.convert(2, TimeUnit.SECONDS));
        System.out.println("ChronoUnit seconds maps to: " +
                TimeUnit.of(ChronoUnit.SECONDS));
    }
}
```

Trong terminal tại thư mục chứa tệp, dùng JDK còn được cập nhật và có compiler hỗ trợ release 11:

```sh
javac --release 11 -encoding UTF-8 TimeUnitDemo.java
java TimeUnitDemo
```

**Stdout chính xác:**

```text
Duration: PT2.75S
Seconds: 2
Milliseconds: 2750
Microseconds: 2750000
Nanoseconds: 2750000000
Minutes: 0
From 2 seconds to millis: 2000
ChronoUnit seconds maps to: SECONDS
```

**Đọc kết quả theo hệ số:**

1. `Duration.ofSeconds(2).plusMillis(750)` biểu diễn chính xác **2,75 giây**, định dạng `Duration.toString()` là `PT2.75S`.
2. Đổi sang giây: `2` vì phần `0,75` giây không còn sau khi cắt phần lẻ.
3. Đổi sang mili giây: `2 × 1000 + 750 = 2750`.
4. Đổi sang micro giây: `2.750.000`; sang nano giây: `2.750.000.000`. Cả hai giá trị còn nằm trong miền `long`.
5. Đổi sang phút: `0` vì thời lượng nhỏ hơn một phút.
6. `TimeUnit.of(ChronoUnit.SECONDS)` ánh xạ đơn vị trong `java.time.temporal.ChronoUnit` sang đơn vị tương đương trong `TimeUnit`, ở đây là `SECONDS`. Nếu `ChronoUnit` không có đơn vị tương đương trong bảy hằng của `TimeUnit`, phương thức sẽ báo `IllegalArgumentException`; không dùng nó cho `MONTHS` hoặc `YEARS`.

Bảng này cũng cho thấy **cùng một thời lượng có nhiều biểu diễn số nguyên**, nên nhãn đơn vị của kết quả rất quan trọng. Nếu giao diện hay API cần giữ chính xác `2.75` giây, nên trả `Duration` hoặc đơn vị đủ mịn, không ép kết quả `TimeUnit.SECONDS.convert` thành số thực rồi nghĩ rằng phần lẻ được phục hồi.

## 5. Cắt bỏ phần lẻ: quy tắc với số dương lẫn số âm

Đổi từ đơn vị mịn sang đơn vị thô hơn (ví dụ nano giây → micro giây, mili giây → giây) làm mất phần nhỏ hơn một đơn vị đích. `TimeUnit.convert(Duration)` **cắt về phía 0**; nó không tự làm tròn tới số nguyên gần nhất, không tự làm tròn lên và không luôn làm tròn xuống về âm vô cực.

Tạo tệp **`TruncationDemo.java`**:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public class TruncationDemo {
    public static void main(String[] args) {
        System.out.println("1500 ms -> s: " +
                TimeUnit.SECONDS.convert(Duration.ofMillis(1500)));
        System.out.println("999 ms -> s: " +
                TimeUnit.SECONDS.convert(Duration.ofMillis(999)));
        System.out.println("-1500 ms -> s: " +
                TimeUnit.SECONDS.convert(Duration.ofMillis(-1500)));
        System.out.println("-999 ms -> s: " +
                TimeUnit.SECONDS.convert(Duration.ofMillis(-999)));
        System.out.println("1234 ns -> us: " +
                TimeUnit.MICROSECONDS.convert(Duration.ofNanos(1234)));

        Duration negativeHalf = Duration.ofMillis(-500);
        System.out.println("-500 ms getSeconds: " +
                negativeHalf.getSeconds());
        System.out.println("-500 ms convert to seconds: " +
                TimeUnit.SECONDS.convert(negativeHalf));
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 TruncationDemo.java
java TruncationDemo
```

**Stdout chính xác:**

```text
1500 ms -> s: 1
999 ms -> s: 0
-1500 ms -> s: -1
-999 ms -> s: 0
1234 ns -> us: 1
-500 ms getSeconds: -1
-500 ms convert to seconds: 0
```

**Vì sao `-999 ms` đổi sang giây bằng `0`?** Giá trị toán học là `-0,999` giây; khi lấy phần nguyên theo hướng **về 0**, kết quả là `0`. Nếu cố dùng phép chia nguyên với biểu diễn chuẩn hóa của `Duration` mà không hiểu quy tắc, bạn dễ tính sai thời lượng âm.

**Vì sao `getSeconds()` là `-1` nhưng `convert` là `0` với `-500 ms`?** `Duration` lưu thời lượng bằng cặp (`seconds`, `nanos`), trong đó trường nano giây là phần bù không âm. `-500 ms` được lưu tương đương **`-1` giây cộng `500.000.000` nano giây**. `getSeconds()` trả trường lưu trữ `-1`; còn `TimeUnit.SECONDS.convert(duration)` chuyển **toàn bộ thời lượng -0,5 giây** sang giây nguyên và cắt về `0`. Không dùng riêng `getSeconds()` để suy ra kết quả chuyển đổi đơn vị cho mọi thời lượng âm có phần nano giây.

**Mất độ chính xác là thật:** khi `999 ms` đã đổi thành `0` giây, đổi ngược `0` giây thành mili giây vẫn là `0`. Phần `999 ms` không thể tự khôi phục. Giữ `Duration` nguyên gốc khi cần phép tính chính xác.

## 6. Tràn số: `convert(Duration)` bão hòa thay vì ném `ArithmeticException`

`long` chỉ chứa các số nguyên trong khoảng `Long.MIN_VALUE` đến `Long.MAX_VALUE`. Khi một thời lượng rất dài đổi sang nano giây, số đơn vị đích có thể vượt giới hạn. `TimeUnit.convert(Duration)` trả về **giá trị biên** theo dấu:

- Dương vượt miền `long` → `Long.MAX_VALUE`.
- Âm vượt miền `long` → `Long.MIN_VALUE`.

Đây là **saturation**, khác với `Duration.toNanos()` (có thể ném `ArithmeticException` khi tràn số). Không nên coi saturation là một kết quả chính xác; đây là quy tắc xử lý giá trị không thể biểu diễn.

Tạo tệp **`SaturationDemo.java`**:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public class SaturationDemo {
    public static void main(String[] args) {
        Duration huge = Duration.ofDays(1_000_000_000_000L);

        System.out.println("Nanos positive saturated: " +
                (TimeUnit.NANOSECONDS.convert(huge) == Long.MAX_VALUE));
        System.out.println("Millis positive saturated: " +
                (TimeUnit.MILLISECONDS.convert(huge) == Long.MAX_VALUE));
        System.out.println("Nanos negative saturated: " +
                (TimeUnit.NANOSECONDS.convert(huge.negated())
                        == Long.MIN_VALUE));

        try {
            huge.toNanos();
            System.out.println("Unexpected conversion success");
        } catch (ArithmeticException expected) {
            System.out.println("Duration.toNanos() overflow");
        }
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 SaturationDemo.java
java SaturationDemo
```

**Stdout chính xác:**

```text
Nanos positive saturated: true
Millis positive saturated: true
Nanos negative saturated: true
Duration.toNanos() overflow
```

Điều cần hiểu: **`Duration` vẫn biểu diễn được khoảng thời gian lớn trong ví dụ**, nhưng **số nano giây hoặc mili giây** không còn vừa một `long`. API chuyển đổi giữ lời hứa không ném `ArithmeticException` cho phép đổi quá lớn, nhưng đổi lại có thể mất giá trị chính xác. `Long.MAX_VALUE` có thể là giá trị hợp lệ thực sự **hoặc** dấu hiệu đã bão hòa, vì vậy ứng dụng yêu cầu độ chính xác tuyệt đối phải kiểm soát phạm vi đầu vào **trước khi đổi** thay vì chỉ dựa trên việc kết quả bằng giá trị biên.

Cần phân biệt thêm **tràn số khi tạo `Duration`** với **tràn số khi chuyển `Duration`**: bản thân các phép tạo/cộng/trừ thời lượng có thể ném ngoại lệ nếu vượt phạm vi mà `Duration` biểu diễn được. Bảo đảm của `TimeUnit.convert(Duration)` chỉ áp dụng cho bước chuyển đổi một `Duration` đã tạo hợp lệ.

### Phân biệt với `convert(long, TimeUnit)`

Overload `convert(long, TimeUnit)` cũng sử dụng quy tắc **cắt phần lẻ** và **bão hòa**. Hai API phục vụ hai kiểu dữ liệu đầu vào khác nhau; chúng không đồng nghĩa với việc dùng phép nhân số nguyên trong code ứng dụng hoặc việc gọi `Duration.toNanos()` trong mọi trường hợp.

## 7. Áp dụng vào timeout: cần quyết định cách làm tròn

Các API chờ trong Java thường nhận cặp `(long timeout, TimeUnit unit)`. Ví dụ:

```java
String value = queue.poll(timeoutMillis, TimeUnit.MILLISECONDS);
```

Đây là **mã minh họa bên trong phương thức** nơi `queue` đã là `BlockingQueue<String>` và mã gọi xử lý `InterruptedException`; không phải chương trình độc lập. Nhiều API chờ không chờ nếu timeout **nhỏ hơn hoặc bằng 0**. Vì thế, **`TimeUnit.MILLISECONDS.convert(Duration.ofNanos(1))` cho kết quả `0`** và có thể làm thay đổi ý định “chờ một khoảng dương rất nhỏ”.

Nếu cần bảo đảm **timeout dương không bị rút xuống 0** hoặc không bị làm tròn xuống, ứng dụng phải xác định chính sách: **làm tròn lên** tới đơn vị đích, giới hạn tối đa, rồi kiểm thử với giá trị biên. Không phải mọi bài toán đều muốn làm tròn lên: đo thời gian đã trôi qua đôi khi cần số nguyên đã cắt phần lẻ để báo cáo.

Tạo tệp **`TimeoutConfigDemo.java`** minh họa chuyển timeout dương tối đa 30 giây sang mili giây và **làm tròn lên** khi có phần lẻ:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public class TimeoutConfigDemo {
    private static long ceilMillis(Duration timeout) {
        Duration max = Duration.ofSeconds(30);
        if (timeout == null || timeout.isZero() || timeout.isNegative()
                || timeout.compareTo(max) > 0) {
            throw new IllegalArgumentException(
                    "timeout must be within (0, 30s]");
        }

        long millis = TimeUnit.MILLISECONDS.convert(timeout);
        if (Duration.ofMillis(millis).compareTo(timeout) < 0) {
            millis++;
        }
        return millis;
    }

    public static void main(String[] args) {
        System.out.println("1 ns -> " +
                ceilMillis(Duration.ofNanos(1)) + " ms");
        System.out.println("1,500,001 ns -> " +
                ceilMillis(Duration.ofNanos(1_500_001)) + " ms");
        System.out.println("1250 ms -> " +
                ceilMillis(Duration.ofMillis(1250)) + " ms");
        System.out.println("PT0.25S -> " +
                ceilMillis(Duration.parse("PT0.25S")) + " ms");

        try {
            ceilMillis(Duration.ZERO);
        } catch (IllegalArgumentException expected) {
            System.out.println("Zero rejected");
        }
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 TimeoutConfigDemo.java
java TimeoutConfigDemo
```

**Stdout chính xác:**

```text
1 ns -> 1 ms
1,500,001 ns -> 2 ms
1250 ms -> 1250 ms
PT0.25S -> 250 ms
Zero rejected
```

**Giải thích:**

1. Kiểm tra `null`, `zero`, số âm và giới hạn 30 giây là **hợp đồng ứng dụng**, không phải yêu cầu của `TimeUnit.convert`.
2. Trong miền tối đa 30 giây, `long millis` an toàn, không thể tràn `long`.
3. `TimeUnit.MILLISECONDS.convert(timeout)` tính số mili giây **nguyên** theo quy tắc cắt phần lẻ.
4. `Duration.ofMillis(millis).compareTo(timeout) < 0` nghĩa là số mili giây nguyên vừa tính **ngắn hơn thời lượng yêu cầu**; tăng `millis` thêm 1 để làm tròn lên.
5. `Duration.parse("PT0.25S")` tạo thời lượng 0,25 giây, tương đương 250 mili giây.

Hàm này phù hợp khi hệ thống đã chọn **mili giây** là đơn vị timeout và yêu cầu “chờ **ít nhất** thời lượng đã cấu hình theo độ phân giải đơn vị”. Một kết quả quy đổi vẫn **không cam kết** thời gian chờ thực tế chính xác tới mili giây vì OS scheduler, sự tranh chấp tài nguyên, độ phân giải đồng hồ và từng API chờ có hành vi khác nhau.

Với timeout quá lớn hoặc không giới hạn, không ngầm dùng `Long.MAX_VALUE` như giá trị “vô hạn” nếu API chưa quy định. Hãy thiết kế chính sách riêng, ví dụ cho phép từ chối cấu hình quá lớn, giới hạn ở một mức nghiệp vụ hoặc dùng API hỗ trợ `Duration` trực tiếp khi có sẵn trên phiên bản Java mục tiêu.

## 8. Cách chọn API theo ngữ cảnh

| Trường hợp | Cách làm có chủ đích | Giới hạn cần nhớ |
| --- | --- | --- |
| Đổi `Duration` sang đơn vị nguyên | `TimeUnit.MILLISECONDS.convert(duration)` | Cắt phần lẻ và bão hòa khi tràn |
| Đổi một số `long` có đơn vị nguồn rõ ràng | `TimeUnit.SECONDS.convert(value, TimeUnit.MILLISECONDS)` | Phải truyền **đúng đơn vị nguồn** |
| Giữ độ chính xác phần nano giây khi tính toán | Giữ `Duration` qua các bước tính | Đừng chuyển sớm sang `long` giây |
| Cần số nano giây dưới dạng `long` nhưng muốn báo lỗi tràn | `duration.toNanos()` với xử lý `ArithmeticException` | Khác saturation của `TimeUnit.convert` |
| Cần đơn vị `ChronoUnit` tương đương | `unit.toChronoUnit()` / `TimeUnit.of(chronoUnit)` | Chỉ hỗ trợ những đơn vị có ánh xạ tương đương |
| Timeout hệ thống nhận `long` và `TimeUnit` | Xác thực thời lượng và chọn đơn vị đủ mịn | Cẩn thận số dương bị cắt về 0 |
| Cộng 1 ngày theo lịch địa phương | `LocalDate`, `ZonedDateTime` hay phép cộng theo lịch | `TimeUnit.DAYS` = 24 giờ, không phải mọi ngày lịch |
| Cần trình bày “2,75 giây” cho người dùng | Giữ `Duration` hoặc tính phần thập phân có kiểm soát | `SECONDS.convert` trả `2`, không trả số thực |

### `TimeUnit` và `ChronoUnit` có giống nhau không?

Không hoàn toàn. `TimeUnit` tập trung vào các đơn vị từ nano giây đến ngày 24 giờ, đặc biệt hữu ích cho concurrency và timeouts. `ChronoUnit` là `enum` của API thời gian rộng hơn, có các đơn vị lịch như `MONTHS` và `YEARS`. Khi cần ánh xạ, `TimeUnit.of(ChronoUnit.SECONDS)` hợp lệ, nhưng `TimeUnit.of(ChronoUnit.MONTHS)` không có tương đương và ném `IllegalArgumentException`.

`Duration` là một đối tượng thời lượng; `TimeUnit` và `ChronoUnit` là **đơn vị**. Không thay thế ba loại một cách máy móc, vì chúng thể hiện vai trò khác nhau.

## 9. Lỗi thường gặp

**Lỗi 1 — Đảo đơn vị nguồn và đơn vị đích.** `TimeUnit.SECONDS.convert(2, TimeUnit.MILLISECONDS)` cho `0`, không phải `2000`. Muốn **2 giây thành 2000 mili giây**, dùng `TimeUnit.MILLISECONDS.convert(2, TimeUnit.SECONDS)`.

**Lỗi 2 — Giả định chuyển đổi làm tròn số học.** `SECONDS.convert(Duration.ofMillis(1500))` trả `1`, không trả `2`. Quy tắc là **bỏ phần lẻ về 0**.

**Lỗi 3 — Quên thời lượng âm.** `SECONDS.convert(Duration.ofMillis(-999))` trả `0`, không phải `-1`. Đừng tự áp phép `Math.floor` cho mọi giá trị.

**Lỗi 4 — Lấy riêng `Duration.getSeconds()` làm toàn bộ thời lượng.** Với `Duration.ofMillis(-500)`, `getSeconds()` là `-1` do cách chuẩn hóa nội bộ, nhưng thời lượng thật là `-0,5` giây và `SECONDS.convert` trả `0`.

**Lỗi 5 — Tin rằng `convert(Duration)` luôn trả giá trị chính xác.** Nó có thể bão hòa về `Long.MAX_VALUE`/`Long.MIN_VALUE` khi số đơn vị quá lớn. Với dữ liệu cần tính toán tài chính, lịch, phân tích thời gian hoặc đo lường chính xác, phải xác thực giới hạn và chọn biểu diễn phù hợp.

**Lỗi 6 — Tưởng phép chuyển đổi sẽ ném `ArithmeticException` giống `Duration.toNanos()`.** Hai API có hợp đồng khác nhau: `TimeUnit.convert(Duration)` sử dụng **saturation** khi tràn.

**Lỗi 7 — Dùng `TimeUnit.DAYS` để biểu diễn lịch.** Một “ngày” của `TimeUnit` là **86.400 giây cố định**. Độ dài ngày thực tế theo lịch địa phương có thể khác do DST; tháng và năm càng không có số giây cố định.

**Lỗi 8 — Dùng số mili giây bằng 0 cho timeout dương rất nhỏ.** Ví dụ `1` nano giây đổi sang mili giây bằng `0`. Nếu không muốn hết hạn lập tức, cân nhắc đơn vị mịn hơn hoặc chính sách làm tròn lên theo yêu cầu.

**Lỗi 9 — Trộn API ở các mức Java không tương thích.** `TimeUnit.convert(Duration)` tồn tại từ Java 11. Nếu code phải tương thích Java 11, sử dụng `javac --release 11` trên JDK còn bảo trì và kiểm thử runtime đích, thay vì dựa vào default language level của JDK mới.

## 10. Bài tập luyện tập

### Bài 1 — Đối chiếu các overload

Cho:

```java
Duration d = Duration.ofSeconds(3).plusMillis(250);
```

Đây là một dòng minh họa đặt **trong một phương thức** và có import `Duration`. Hãy dự đoán:

- `TimeUnit.MILLISECONDS.convert(d)` → **3250**.
- `TimeUnit.MICROSECONDS.convert(d)` → **3250000**.
- `TimeUnit.SECONDS.convert(d)` → **3**.
- `TimeUnit.SECONDS.convert(3250, TimeUnit.MILLISECONDS)` → **3**.

Sau đó giải thích vì sao đổi ngược từ `3` giây không thể khôi phục `250` mili giây đã mất.

### Bài 2 — Làm chủ thời lượng âm

Tự chạy `TruncationDemo.java` rồi trả lời: vì sao `-999` mili giây đổi sang giây bằng `0`? Vì sao `Duration.ofMillis(-500).getSeconds()` khác kết quả `SECONDS.convert`? Trình bày quy tắc **truncation toward zero** và cấu trúc giây/nano giây của `Duration`.

### Bài 3 — Xử lý giá trị cực lớn

Chạy `SaturationDemo.java`, xác nhận ba kết quả `true` và thông báo `Duration.toNanos() overflow`. Thử đổi cùng `Duration` sang `DAYS` để xem vì sao kết quả nhỏ hơn vẫn có thể biểu diễn được. Phân biệt **giá trị chính xác** với **giá trị bão hòa**.

### Bài 4 — Timeout có chính sách rõ ràng

Tự kiểm tra `TimeoutConfigDemo.java` với `1` ns, `1_500_001` ns, `1250` ms, `Duration.ZERO`, `Duration.ofSeconds(31)`. Giải thích vì sao code chọn **làm tròn lên tới mili giây**, và vì sao ứng dụng vẫn cần giới hạn đầu vào.

### Bài 5 — Chọn đơn vị cho một API

Một công cụ nhận `Duration timeout` nhưng thư viện chỉ cung cấp `poll(long, TimeUnit)`. Mô tả những bước cần quyết định: miền thời lượng hợp lệ, đơn vị đích, mất độ chính xác, xử lý trường hợp dương nhỏ hơn một đơn vị, tràn số và cách kiểm thử. Không cần viết một cơ chế đếm ngược từ đầu nếu thư viện đã hỗ trợ timeout đúng yêu cầu.

### Checklist hoàn thành

- [ ] Phân biệt được `Duration` là **giá trị thời lượng**, còn `TimeUnit` là **đơn vị và công cụ chuyển đổi**.
- [ ] Biết `TimeUnit.convert(Duration)` ra đời ở Java 11 và còn được sử dụng.
- [ ] Đổi đúng `2.75` giây thành `2750` ms, `2750000` µs, `2750000000` ns; giải thích vì sao đổi thành phút là `0`.
- [ ] Nêu được quy tắc cắt phần lẻ về `0` cho thời lượng dương và âm.
- [ ] Nêu được quy tắc saturation của `TimeUnit.convert(Duration)` và phân biệt với `Duration.toNanos()`.
- [ ] Có chiến lược an toàn khi chuyển `Duration` thành timeout của API nhận `long`.
- [ ] Không nhầm ngày cố định 24 giờ với ngày theo lịch; code ví dụ được kiểm tra ở mức `--release 11`.

## 11. Tài liệu tham khảo chính thức

1. [Java SE 11 — TimeUnit](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/TimeUnit.html) — `convert(Duration)` (Since 11), `convert(long, TimeUnit)`, truncation, saturation và `toChronoUnit`/`of`.
2. [Java SE 25 — TimeUnit](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/TimeUnit.html) — xác nhận API vẫn tiếp tục được hỗ trợ trên JDK LTS hiện đại.
3. [Java SE 11 — Duration](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/time/Duration.html) — `ofSeconds`, `ofMillis`, `parse`, `getSeconds`, `toNanos` và điều kiện tràn số.
4. [Java SE 11 — ChronoUnit](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/time/temporal/ChronoUnit.html) — đơn vị thời gian thuộc API `java.time`.
5. [Java SE 11 — BlockingQueue](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/BlockingQueue.html) — ví dụ hợp đồng API chờ có `long timeout` và `TimeUnit`.

**Nguyên tắc áp dụng:** Khi đã có `Duration`, dùng `TimeUnit.<UNIT>.convert(duration)` để nhận số nguyên theo đơn vị cần thiết. Luôn cân nhắc **phần lẻ bị cắt**, **tràn số được bão hòa**, và **chính sách timeout** của nơi nhận kết quả. Với dữ liệu cần giữ chính xác thời lượng, đừng chuyển quá sớm sang `long` ở đơn vị thô.