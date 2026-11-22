# Giây, mili giây, micro giây và nano giây trong Java

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa giây (s), mili giây (ms), micro giây (µs) và nano giây (ns), cũng như đổi đơn vị mà không nhầm hệ số.
- Phân biệt **thời điểm** (một mốc trên trục thời gian), **khoảng thời gian** (độ dài giữa hai mốc) và **thời gian đã trôi qua khi đo hiệu năng**.
- Chọn đúng API Java: `Instant`, `Duration`, `ChronoUnit`, `TimeUnit`, `System.currentTimeMillis()` và `System.nanoTime()`.
- Nhận ra giới hạn về độ phân giải đồng hồ, độ chính xác, mất phần lẻ và tràn số khi chuyển đổi.

## 2. Bốn đơn vị và hệ số chuyển đổi

Đây là các **đơn vị SI theo cơ số 10**, không phải đơn vị lưu trữ theo cơ số 2.

| Đơn vị | Ký hiệu | Theo giây | Quan hệ với đơn vị nhỏ hơn |
| --- | --- | ---: | --- |
| Giây | s | 1 s | 1 s = 1.000 ms |
| Mili giây | ms | 10⁻³ s | 1 ms = 1.000 µs |
| Micro giây | µs (đôi khi viết us) | 10⁻⁶ s | 1 µs = 1.000 ns |
| Nano giây | ns | 10⁻⁹ s | 1 ns = 0,001 µs |

Suy ra:

- **1 giây = 1.000 mili giây = 1.000.000 micro giây = 1.000.000.000 nano giây.**
- **1 mili giây = 1.000.000 nano giây.**
- Đổi từ đơn vị lớn sang nhỏ: **nhân** với 1.000 ở mỗi bậc. Đổi từ nhỏ sang lớn: **chia** với 1.000 ở mỗi bậc.
- 1,234567890 giây = 1.234,567890 ms = 1.234.567,890 µs = 1.234.567.890 ns (dấu phẩy là dấu thập phân theo cách viết tiếng Việt).

Ví dụ: độ trễ 2,5 ms tương đương 2.500 µs hoặc 2.500.000 ns. Một phép đo ghi 1.234.567 ns tương đương 1,234567 ms. Số chữ số sau dấu thập phân phải đi kèm **đơn vị** mới có ý nghĩa.

## 3. Thời điểm, khoảng thời gian và bộ đếm

Ba khái niệm này thường bị trộn lẫn:

| Cần biểu diễn | Ý nghĩa | API phù hợp |
| --- | --- | --- |
| Một thời điểm trên timeline UTC | Ví dụ lúc bắt đầu giao dịch | `java.time.Instant` |
| Khoảng thời gian có độ dài xác định | Ví dụ timeout 750 ms | `java.time.Duration` |
| Đơn vị dùng trong phép tính giữa các thời điểm | Ví dụ chênh lệch theo µs | `java.time.temporal.ChronoUnit` |
| Đổi đơn vị số nguyên và thao tác chờ của concurrency | Ví dụ ms → ns | `java.util.concurrent.TimeUnit` |
| Đồng hồ thời gian thực theo Unix epoch, đơn vị ms | Ghi nhận thời điểm hiện tại | `System.currentTimeMillis()` |
| Bộ đếm độ phân giải cao để tính elapsed time | Đo thời lượng thao tác | `System.nanoTime()` |

**Thời điểm (instant)** trả lời “xảy ra lúc nào?”, còn **duration** trả lời “kéo dài bao lâu?”. Một giá trị số `1_000_000` không tự nói đó là 1 giây dưới dạng micro giây, 1 mili giây dưới dạng nano giây, hay một timestamp tính bằng mili giây. Vì vậy tên biến/API/hợp đồng dữ liệu phải nêu rõ đơn vị.

**Unix epoch** là `1970-01-01T00:00:00Z`. Unix timestamp đếm thời gian tương ứng từ mốc này; thời điểm trước epoch có giá trị âm. Đơn vị của timestamp phải được quy định rõ: Unix seconds và epoch milliseconds là hai cách mã hóa khác nhau của cùng một thời điểm.

## 4. `Instant`: giây và phần nano của một thời điểm

`Instant` biểu diễn thời điểm trên trục UTC, không mang múi giờ hiển thị. Về mặt biểu diễn, nó có hai thành phần chính:

- `getEpochSecond()`: số giây tính từ Unix epoch, kiểu `long`.
- `getNano()`: phần nano **trong giây hiện tại**, luôn từ `0` đến `999_999_999`.

Ví dụ `Instant.ofEpochSecond(1, 234_567_890)` nghĩa là 1 giây cộng 234.567.890 ns sau epoch, được định dạng `1970-01-01T00:00:01.234567890Z`. **`getNano()` không phải tổng số nano giây kể từ epoch.**

Java chuẩn hóa số nano ngoài khoảng [0, 999.999.999] khi xây dựng `Instant`. Ví dụ `Instant.ofEpochSecond(0, -1)` là thời điểm 1 ns trước epoch; khi đó `getEpochSecond() == -1` và `getNano() == 999_999_999`. Đây là biểu diễn chuẩn cho cả giá trị âm.

Các phép tạo/đọc thường dùng:

```java
Instant epoch = Instant.EPOCH;
Instant fromMillis = Instant.ofEpochMilli(1_234);
Instant precise = Instant.ofEpochSecond(1, 234_567_890);
Instant parsed = Instant.parse("2026-01-02T03:04:05.123456789Z");

long millisecondsSinceEpoch = fromMillis.toEpochMilli();
int nanoFraction = precise.getNano();
```

Đây là **đoạn mã minh họa**, cần `import java.time.Instant;` và được đặt trong thân một phương thức. `toEpochMilli()` trả mili giây nguyên, vì vậy phần nhỏ hơn 1 ms không được bảo toàn. Với giá trị ngoài phạm vi biểu diễn được bằng `long` mili giây, `toEpochMilli()` có thể ném `ArithmeticException`.

`Instant.now()` có thể hiển thị đến 9 chữ số phần giây, nhưng **độ phân giải và độ chính xác thực tế của đồng hồ phụ thuộc hệ điều hành, phần cứng và nguồn clock**. Có trường nano không đồng nghĩa hệ thống đo đúng đến 1 ns.

## 5. `Duration`: độ dài thời gian với độ phân giải nano

`Duration` biểu diễn một lượng thời gian dựa trên giây và nano giây, thích hợp cho timeout, elapsed time, thời lượng media và phép cộng/trừ thời gian.

```java
Duration oneAndHalfSeconds = Duration.ofMillis(1_500);
Duration oneMicrosecond = Duration.ofNanos(1_000);
Duration twoSeconds = Duration.ofSeconds(2);
Duration combined = twoSeconds.plusMillis(250).plusNanos(75);

long wholeMillis = combined.toMillis();
long totalNanos = combined.toNanos();
```

Đây là **đoạn mã minh họa**, cần `import java.time.Duration;` và thân một phương thức. Trong ví dụ, `combined` là 2 giây + 250 ms + 75 ns: `wholeMillis` = 2.250, `totalNanos` = 2.250.000.075.

Lưu ý cách `Duration` chuẩn hóa **giá trị âm**. `Duration.ofNanos(-1)` có `getSeconds() == -1` và `getNano() == 999_999_999`, nhưng toàn bộ độ dài vẫn là **âm 1 ns**. Không được coi hai thành phần này là hai đại lượng độc lập mang cùng dấu.

Các API `toMillis()`, `toNanos()` và phép đếm đơn vị nguyên không giữ lại phần nhỏ hơn đơn vị đích. Ví dụ 1.234.567 ns → `toMillis() == 1`. Khi tổng số nano giây không nằm trong giới hạn `long`, `Duration.toNanos()` ném `ArithmeticException`. Đừng chuyển một duration cực lớn sang ns chỉ để so sánh: có thể dùng `compareTo()`, `isNegative()`, `isZero()` hoặc phương thức cộng/trừ ở mức `Duration`.

## 6. Chương trình Java 17+ đầy đủ: đổi đơn vị và kiểm tra thời điểm

Lưu thành **`TimeUnitDemo.java`**:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.concurrent.TimeUnit;

public class TimeUnitDemo {
    public static void main(String[] args) {
        long milliseconds = 1_234L;
        long microseconds = TimeUnit.MILLISECONDS.toMicros(milliseconds);
        long nanoseconds = TimeUnit.MILLISECONDS.toNanos(milliseconds);

        System.out.println("ms = " + milliseconds);
        System.out.println("us = " + microseconds);
        System.out.println("ns = " + nanoseconds);

        Instant instant = Instant.ofEpochSecond(1, 234_567_890);
        System.out.println("instant = " + instant);
        System.out.println("nanoPart = " + instant.getNano());

        Duration duration = Duration.ofSeconds(1)
                .plusMillis(234)
                .plusNanos(567_890);
        System.out.println("durationNanos = " + duration.toNanos());
        System.out.println("durationMicros = " + duration.toNanos() / 1_000);
        System.out.println("betweenMicros = "
                + ChronoUnit.MICROS.between(Instant.EPOCH, instant));
    }
}
```

Biên dịch và chạy:

```bash
javac TimeUnitDemo.java
java TimeUnitDemo
```

Kết quả xác định:

```text
ms = 1234
us = 1234000
ns = 1234000000
instant = 1970-01-01T00:00:01.234567890Z
nanoPart = 234567890
durationNanos = 1234567890
durationMicros = 1234567
betweenMicros = 1234567
```

Giải thích:

1. `TimeUnit.MILLISECONDS.toMicros(1_234)` nhân 1.000; sang ns nhân 1.000.000.
2. `getNano()` trả riêng phần nano của giây trên `Instant`.
3. `Duration` đã xây dựng có 1.234.567.890 ns; chia nguyên cho 1.000 được 1.234.567 µs, bỏ 890 ns cuối.
4. `ChronoUnit.MICROS.between(a, b)` trả số micro giây **nguyên** giữa hai `Instant`, cũng bỏ phần nano dư khi quy đổi.

Chọn `Duration.between(start, end)` khi cần giữ đầy đủ độ chính xác mà API hỗ trợ; chọn `ChronoUnit.MILLIS/MICROS/NANOS.between` khi bên nhận cần một số nguyên với đơn vị cụ thể. Phép `between` ở đơn vị quá nhỏ trên khoảng thời gian quá dài có thể tràn `long`.

## 7. `TimeUnit`, `ChronoUnit` và phép đổi số nguyên

`TimeUnit` có các hằng `NANOSECONDS`, `MICROSECONDS`, `MILLISECONDS`, `SECONDS`, `MINUTES`, `HOURS`, `DAYS`. Ví dụ:

```java
long nanos = TimeUnit.MICROSECONDS.toNanos(750);        // 750_000
long millis = TimeUnit.MICROSECONDS.toMillis(1_999);    // 1
long seconds = TimeUnit.MILLISECONDS.toSeconds(2_999); // 2
```

Đây là đoạn minh họa với `import java.util.concurrent.TimeUnit;`. `TimeUnit` đổi **giá trị số nguyên**; khi chia, phần lẻ của đơn vị đích bị cắt về 0. Khi phép nhân vượt `long`, các phương thức chuyển đổi của `TimeUnit` thường **bão hòa về `Long.MAX_VALUE` hoặc `Long.MIN_VALUE`**, khác với `Duration.toNanos()` có thể ném ngoại lệ.

`ChronoUnit` là tập đơn vị cho API ngày giờ (ví dụ `SECONDS`, `MILLIS`, `MICROS`, `NANOS`) và phép `between` trên hai temporal. Không phải tất cả đối tượng ngày giờ đều hỗ trợ mọi đơn vị; ví dụ `LocalDate` không biểu diễn nano giây trong ngày. Đơn vị chỉ mô tả độ lớn; nó **không tự quyết định múi giờ**.

Để đổi số thực mà không mất phần lẻ do nhị phân, có thể dùng `BigDecimal` kèm quy tắc làm tròn minh bạch:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalUnitDemo {
    public static void main(String[] args) {
        BigDecimal milliseconds = new BigDecimal("0.123456");
        BigDecimal nanoseconds = milliseconds.movePointRight(6);
        System.out.println(nanoseconds.toPlainString()); // 123456
        System.out.println(nanoseconds.setScale(0, RoundingMode.UNNECESSARY));
    }
}
```

Lưu thành `DecimalUnitDemo.java`, chạy với `javac DecimalUnitDemo.java` và `java DecimalUnitDemo`. Hai dòng đầu ra đều là `123456`. Hệ số từ **mili giây sang nano giây là 10⁶**. `RoundingMode.UNNECESSARY` chỉ chấp nhận kết quả nguyên chính xác; nếu có phần nano lẻ, bạn phải chọn rõ chính sách làm tròn phù hợp nghiệp vụ.

## 8. Đo thời gian chạy: `nanoTime()` khác `currentTimeMillis()`

`System.currentTimeMillis()` biểu diễn wall-clock time theo Unix epoch ở đơn vị ms. Đồng hồ hệ thống có thể được điều chỉnh (NTP, thao tác quản trị); hai lần gọi cách nhau không nhất thiết cho chênh lệch phản ánh elapsed time chính xác.

`System.nanoTime()` trả một giá trị `long` từ một gốc tùy ý của JVM/hệ thống. Giá trị có thể âm; **không chuyển nó thành Unix timestamp, không lưu như thời điểm lịch**, và không so sánh số đọc của các JVM khác nhau. Hãy lấy hiệu giữa hai lần đo trong cùng môi trường:

```java
public class StopwatchDemo {
    public static void main(String[] args) {
        long start = System.nanoTime();

        long sum = 0;
        for (int i = 0; i < 100_000; i++) {
            sum += i;
        }

        long elapsedNanos = System.nanoTime() - start;
        double elapsedMillis = elapsedNanos / 1_000_000.0;

        System.out.println("sum = " + sum);
        System.out.printf("elapsed = %.3f ms%n", elapsedMillis);
    }
}
```

Lưu `StopwatchDemo.java`; chạy `javac StopwatchDemo.java`, rồi `java StopwatchDemo`. Dòng đầu là `sum = 4999950000`; số mili giây đo được ở dòng sau **thay đổi theo mỗi lần chạy**. Với benchmark đáng tin, cần làm nóng JVM, tránh kết luận từ một lần đo, kiểm soát JIT/GC/scheduling và cân nhắc **JMH**. Một vòng lặp đơn giản chỉ minh họa cách đọc đồng hồ, không phải phép đo vi mô chính xác.

Khi đo timeout, hãy so `System.nanoTime() - start` với ngưỡng thời lượng, ví dụ `TimeUnit.SECONDS.toNanos(2)`. Việc lấy hiệu `long` hoạt động theo số học hai bù ngay cả khi bộ đếm vòng qua, với điều kiện khoảng đo không vượt phạm vi hiệu có dấu (xấp xỉ 292 năm ở đơn vị ns). Với thời điểm nghiệp vụ cần lưu trữ và trao đổi, dùng `Instant` và đồng hồ có thể tiêm qua `Clock` để kiểm thử.

## 9. Độ phân giải, độ chính xác và quy tắc làm tròn

Ba khái niệm khác nhau:

- **Độ phân giải (resolution/granularity):** bước nhỏ nhất đồng hồ/API có thể phân biệt trên thực tế. Giá trị được trả bằng ns chưa chắc đồng hồ cập nhật mỗi ns.
- **Độ chính xác (accuracy):** thời điểm đo gần thời gian thực bao nhiêu; ảnh hưởng bởi đồng bộ clock, hệ điều hành và phần cứng.
- **Độ chính xác số học (numeric precision):** số chữ số hoặc phần nhỏ có thể **biểu diễn** và giữ qua chuyển đổi.

Khi đổi ns → µs/ms bằng phép chia số nguyên, phần dư nhỏ hơn đơn vị đích sẽ mất. Quy tắc làm tròn cần ghi rõ: cắt về 0 (trong nhiều phép chia số nguyên Java), làm tròn gần nhất, xuống, lên, hoặc báo lỗi nếu không biểu diễn chính xác.

Ví dụ: 1.999.999 ns là **1 ms** nếu lấy phần nguyên theo ms, nhưng **gần 2 ms** nếu làm tròn đến ms gần nhất. Đừng gắn thêm ba chữ số `000` vào timestamp và tuyên bố dữ liệu chính xác tới micro/nano giây nếu nguồn gốc chỉ có mili giây.

Khi truyền dữ liệu qua JSON, cơ sở dữ liệu, Kafka hoặc API, luôn công bố rõ trường là `epochMillis`, `epochMicros`, ISO-8601 `Instant` hay `durationNanos`. Trường timestamp trong cơ sở dữ liệu có thể chỉ lưu tới µs hoặc ms dù Java có thể biểu diễn ns; kiểm tra độ chính xác thực tế của driver, cột và định dạng trao đổi.

## 10. Giới hạn số nguyên, số âm và ngoại lệ

- `long` là số nguyên có dấu 64 bit. Một lượng ns lớn hơn `Long.MAX_VALUE` không thể nằm trong một `long` duy nhất. `Long.MAX_VALUE` ns chỉ khoảng **292 năm**; cùng kiểu `long` nếu dùng ms thì phạm vi thời gian lớn hơn rất nhiều.
- Tránh phép nhân trần `milliseconds * 1_000_000` khi chưa kiểm tra tràn; có thể dùng `Math.multiplyExact(milliseconds, 1_000_000L)` để nhận `ArithmeticException`, hoặc dùng `TimeUnit` khi hợp đồng chấp nhận bão hòa.
- `Duration.toNanos()` có thể tràn; `Duration` bản thân có phạm vi lớn hơn việc dồn tất cả về một `long` ns.
- Phép chia số nguyên của Java **cắt về 0**, cần đặc biệt thận trọng với độ dài âm, timestamp trước epoch và cách dùng `Math.floorDiv`.
- Một `Instant` trước epoch có thể có `getEpochSecond() < 0` nhưng `getNano() >= 0` do chuẩn hóa. Đừng cộng hai thành phần một cách ngây thơ rồi đổi đơn vị thiếu kiểm tra.

Chương trình minh họa giá trị âm và overflow, lưu thành **`NegativeDurationDemo.java`**:

```java
import java.time.Duration;

public class NegativeDurationDemo {
    public static void main(String[] args) {
        Duration minusOneNano = Duration.ofNanos(-1);
        System.out.println("seconds = " + minusOneNano.getSeconds());
        System.out.println("nanoPart = " + minusOneNano.getNano());
        System.out.println("wholeMillis = " + minusOneNano.toMillis());

        try {
            Duration.ofSeconds(Long.MAX_VALUE).toNanos();
        } catch (ArithmeticException ex) {
            System.out.println("nanos overflow");
        }
    }
}
```

Chạy `javac NegativeDurationDemo.java` và `java NegativeDurationDemo`:

```text
seconds = -1
nanoPart = 999999999
wholeMillis = 0
nanos overflow
```

Kết quả `wholeMillis = 0` thể hiện cách làm tròn theo phần nguyên khi đổi **độ dài** -1 ns sang ms, không có nghĩa duration ban đầu bằng 0.

## 11. Quy tắc lựa chọn trong ứng dụng

| Tình huống | Chọn | Lý do |
| --- | --- | --- |
| Lưu lúc tạo đơn hàng, log hoặc thời điểm sự kiện | `Instant` / chuỗi ISO-8601 UTC | Xác định thời điểm, tránh nhập nhằng đơn vị và múi giờ |
| Truyền Unix timestamp cho API chỉ nhận số nguyên | `Instant.toEpochMilli()` nếu hợp đồng là ms | Cần ghi tên trường, kiểm tra phạm vi và phần nano mất đi |
| Timeout HTTP 500 ms | `Duration.ofMillis(500)` | Tự mô tả đơn vị, dễ truyền tới API nhận `Duration` |
| Đổi số µs ↔ ns trong thư viện concurrency | `TimeUnit` | Chuyển đổi đơn vị nguyên với ngữ nghĩa bão hòa |
| Đếm số micro giây giữa hai thời điểm | `ChronoUnit.MICROS.between(...)` | Trả số nguyên đơn vị đã chọn |
| Đo thời gian đã trôi qua của một đoạn chương trình | `System.nanoTime()` lấy hiệu | Tách khỏi chỉnh sửa đồng hồ lịch |
| Hiển thị giờ địa phương của người dùng | `Instant` kết hợp `ZoneId` / `ZonedDateTime` | Đơn vị giây/ns không giải quyết múi giờ, DST |

## 12. Sai lầm thường gặp và cách tự kiểm tra

1. **Nhầm hệ số 1.024 với 1.000.** Các đơn vị s, ms, µs, ns là cơ số 10; 1 ms = 1.000.000 ns.
2. **Coi `getNano()` là epoch nanoseconds.** Nó chỉ là phần nano của một giây trên `Instant`.
3. **Dùng `currentTimeMillis()` để benchmark hoặc lấy `nanoTime()` làm timestamp.** Chọn đồng hồ theo mục đích.
4. **Coi độ phân giải biểu diễn bằng ns là khả năng đo chính xác 1 ns.** Phải xét nguồn đồng hồ và thực nghiệm.
5. **Tự nhân lên mà không kiểm tra tràn `long`.** Dùng API chuyển đổi và quy tắc overflow phù hợp.
6. **Âm 1 ns thành 0 ms rồi kết luận thời lượng bằng 0.** Hãy giữ đơn vị mịn hơn hoặc dùng `Duration` cho tới lúc cuối.
7. **Lưu số nguyên thời gian mà không ghi đơn vị.** Đặt tên rõ `elapsedNanos`, `timeoutMillis`, `createdAtEpochMillis`; khai báo hợp đồng của từng hệ thống.

Tự kiểm tra:

- 0,75 ms bằng bao nhiêu ns? **750.000 ns**.
- 2.500.001 ns lấy phần nguyên mili giây được bao nhiêu? **2 ms**, dư 500.001 ns.
- `Instant.ofEpochSecond(0, -1)` có `getNano()` bằng bao nhiêu? **999.999.999**, đồng thời `getEpochSecond() == -1`.
- Muốn đo elapsed time của một lời gọi hàm có thể bị ảnh hưởng bởi việc chỉnh đồng hồ hệ thống, chọn gì? **Hiệu hai lần gọi `System.nanoTime()`**.
- Khi cần lưu một thời điểm chính xác về mặt ngữ nghĩa, chọn `Instant`; khi cần lưu “chờ 300 ms”, chọn **`Duration.ofMillis(300)`**.

**Ghi nhớ:** s, ms, µs, ns chỉ là đơn vị. Hãy xác định trước đại lượng đang đo là **thời điểm** hay **khoảng thời gian**, sau đó chọn API và quy định rõ đơn vị, cách làm tròn, giới hạn tràn và độ chính xác thực tế.