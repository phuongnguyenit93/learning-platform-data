# Độ chính xác nanosecond và giới hạn đồng hồ hệ thống trong Java

## 1. Mục tiêu

Java hỗ trợ biểu diễn một mốc thời gian hoặc khoảng thời gian với phần lẻ đến **nanosecond** nhờ `java.time.Instant` và `java.time.Duration`. Tuy nhiên, kiểu dữ liệu có chín chữ số phần giây không đồng nghĩa đồng hồ hệ thống thực sự đo chính xác đến từng nanosecond.

Kết thúc bài học, bạn có thể:

- Phân biệt **độ chính xác biểu diễn** (precision), **độ phân giải** (resolution/granularity), **độ đúng so với thời gian chuẩn** (accuracy), và **độ ổn định của nguồn đo**.
- Hiểu `Instant.getEpochSecond()`, `getNano()` và `Duration` đến cấp nanosecond.
- Giải thích giới hạn của `Instant.now()` và `Clock.systemUTC()`.
- Chọn `System.currentTimeMillis()` cho epoch milliseconds và `System.nanoTime()` cho đo thời gian trôi qua; tránh đổi lẫn hai API.
- Chủ động giữ hoặc làm mất precision khi chuyển sang milliseconds/microseconds, format hoặc lưu database.
- Dùng `Clock.fixed`, `Clock.offset`, `Clock.tick` để kiểm thử ranh giới nano một cách xác định.
- Tránh giả định timestamp là duy nhất, luôn tăng hoặc có thể so sánh nguyên giá trị `nanoTime()` giữa các JVM.

`java.time`, `Clock` và các API thời gian trên vẫn được dùng trong JDK hiện hành. Nội dung chỉ sử dụng kiến thức còn áp dụng; những ví dụ yêu cầu `List.of`/`Stream.toList` sẽ ghi rõ Java 17+, còn khái niệm cốt lõi có từ Java 8.

## 2. Precision, resolution, accuracy là những khái niệm riêng

| Khái niệm | Câu hỏi mà nó trả lời | Ví dụ |
| --- | --- | --- |
| **Precision của biểu diễn** | Kiểu dữ liệu có thể phân biệt hai giá trị nhỏ đến mức nào? | `Instant` có thể giữ phần nanosecond trong giây |
| **Resolution/granularity** | Nguồn đồng hồ thực tế thay đổi từng bước nhỏ cỡ nào? | Có máy chỉ trả timestamp khác nhau sau nhiều microsecond hoặc millisecond |
| **Accuracy** | Đồng hồ đang lệch bao nhiêu so với chuẩn tham chiếu? | Có thể lệch mili giây dù timestamp chứa 9 chữ số phần lẻ |
| **Latency/jitter** | Lệnh được thực thi trễ hoặc dao động thế nào? | Scheduler có thể hoãn thread giữa hai lần đo |
| **Monotonic elapsed source** | Có phù hợp đo khoảng thực thi/timeout không? | `System.nanoTime()` được dành cho elapsed time, không phải UTC |

Đơn vị:

| Đơn vị | Bằng bao nhiêu giây? | Nanosecond |
| --- | --- | --- |
| 1 second | `1` | `1_000_000_000 ns` |
| 1 millisecond | `0.001` | `1_000_000 ns` |
| 1 microsecond | `0.000001` | `1_000 ns` |
| 1 nanosecond | `0.000000001` | `1 ns` |

Giả sử một thời điểm được in:

```text
2026-04-05T12:34:56.123456789Z
                    ^^^^^^^^^
              Phần lẻ có 9 chữ số
```

Điều này chứng minh *giá trị* đã biểu diễn phần lẻ tới cấp ns, **không chứng minh** cảm biến hay đồng hồ vật lý đã xác định thời điểm đó với sai số nhỏ hơn 1 ns. Những chữ số cuối có thể có được từ số học trên một giá trị cố định, phép ngoại suy, việc định dạng hoặc thuật toán hệ thống. Nếu đang cần độ chính xác đo lường thực, phải nghiên cứu nguồn đồng hồ/thiết bị, đồng bộ thời gian và đo kiểm độc lập.

## 3. `Instant` lưu giây epoch và nano trong giây

`Instant` đại diện một điểm trên timeline, không phải một giờ địa phương không có zone. Hai thành phần quan trọng:

- `getEpochSecond()`: số giây từ mốc `1970-01-01T00:00:00Z`, có thể là số âm.
- `getNano()`: phần nanosecond trong một giây, luôn từ **0 đến 999.999.999**.

`Instant` là immutable; `plusNanos`, `minusNanos`, `truncatedTo` trả về giá trị mới. Một `Instant` có thể biểu diễn hai thời điểm lệch 1 ns trong phạm vi hỗ trợ, nhưng lấy `Instant.now()` hai lần không bảo đảm nhận được hai giá trị cách nhau ít nhất 1 ns.

Lưu `InstantNanosecondDemo.java`:

```java
import java.time.Instant;
import java.time.temporal.ChronoField;

public class InstantNanosecondDemo {
    public static void main(String[] args) {
        Instant time =
                Instant.parse("2026-04-05T12:34:56.123456789Z");

        System.out.println("instant = " + time);
        System.out.println("nanos = " + time.getNano());
        System.out.println("micros = " +
                time.get(ChronoField.MICRO_OF_SECOND));
        System.out.println("millis = " +
                time.get(ChronoField.MILLI_OF_SECOND));

        Instant normalized =
                Instant.ofEpochSecond(1, 500_000_123);
        System.out.println("normalized = " + normalized);
    }
}
```

```bash
javac InstantNanosecondDemo.java
java InstantNanosecondDemo
```

```text
instant = 2026-04-05T12:34:56.123456789Z
nanos = 123456789
micros = 123456
millis = 123
normalized = 1970-01-01T00:00:01.500000123Z
```

`getNano()` trả phần lẻ nanosecond trong **giây hiện tại**, không phải tổng nanos từ epoch. Tương tự, `MICRO_OF_SECOND` và `MILLI_OF_SECOND` chỉ truy vấn những chữ số tương ứng từ giá trị đã lưu.

Khi biểu diễn `Instant` bằng cặp `(epochSeconds, nanoOfSecond)`, phần nano không âm ngay cả với mốc trước 1970. Đừng xây dựng timestamp nanosecond toàn cục bằng `getEpochSecond() * 1_000_000_000L + getNano()` mà không kiểm tra phạm vi: phép nhân/cộng có thể vượt `long` với những instant hoàn toàn hợp lệ.

## 4. `Duration` giữ thời lượng tới nanosecond

`Duration` mô hình hóa **khoảng thời gian**, khác với `Instant` là **một thời điểm**. API hữu ích gồm `ofNanos`, `between`, `getSeconds`, `getNano`, `toNanos` và `toMillis`.

Lưu `DurationNanosecondDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;

public class DurationNanosecondDemo {
    public static void main(String[] args) {
        Duration d = Duration.ofNanos(1_500_000_123L);

        System.out.println("duration = " + d);
        System.out.println("seconds = " + d.getSeconds());
        System.out.println("nanoPart = " + d.getNano());
        System.out.println("totalNanos = " + d.toNanos());
        System.out.println("totalMillis = " + d.toMillis());

        Instant a = Instant.parse("2026-01-01T00:00:00Z");
        Instant b = a.plusNanos(321);
        System.out.println("betweenNanos = " +
                Duration.between(a, b).toNanos());

        Duration negative = Duration.ofNanos(-1);
        System.out.println("negativeSeconds = " +
                negative.getSeconds());
        System.out.println("negativeNanoPart = " +
                negative.getNano());
    }
}
```

```bash
javac DurationNanosecondDemo.java
java DurationNanosecondDemo
```

```text
duration = PT1.500000123S
seconds = 1
nanoPart = 500000123
totalNanos = 1500000123
totalMillis = 1500
betweenNanos = 321
negativeSeconds = -1
negativeNanoPart = 999999999
```

Những điều cần nhớ:

1. `getNano()` chỉ là thành phần nano-of-second, **không phải tổng nanosecond**. Nếu tổng vừa trong một `long`, dùng `toNanos()`.
2. `toMillis()` bỏ phần nhỏ hơn 1 ms. `1.500000123 giây` thành `1500 ms`, mất phần `123 ns` nhỏ hơn millisecond còn lại.
3. Với duration âm, Java chuẩn hóa cặp giây/nano. `Duration.ofNanos(-1)` biểu diễn bằng `-1 giây + 999_999_999 ns`. Không dựa vào `getNano() >= 0` để kết luận duration không âm.
4. `Duration.toNanos()` có thể ném `ArithmeticException` với duration lớn vượt `long nanos`. Kiểu `Duration` không bị giới hạn chỉ trong ±292 năm vì nó lưu giây và nano tách biệt.

**Phân biệt:** `Duration.between(a,b)` với hai `Instant` đã xác định là phép toán trên timeline. Nhưng nếu tạo `a = Instant.now()`, `b = Instant.now()` rồi xem chênh lệch này là đồng hồ elapsed chuẩn cho timeout, bạn vẫn đang dựa vào **wall clock có thể bị chỉnh**. Với elapsed time nội bộ, ưu tiên `System.nanoTime()`.

## 5. `Instant.now()` không hứa đo chính xác từng nanosecond

`Instant.now()` lấy giá trị từ đồng hồ hệ thống. `Clock.systemUTC()` dùng nguồn thời gian tốt nhất hiện có mà JDK/hệ điều hành cung cấp. Tài liệu Oracle nói nguồn này **có thể dùng `System.currentTimeMillis()` hoặc đồng hồ có resolution cao hơn nếu có**.

Do đó:

- Hai lời gọi `Instant.now()` rất sát nhau **có thể bằng nhau**.
- Phần nano có thể là bội của 1 triệu ns trên một môi trường, hoặc thay đổi ở bước nhỏ hơn trên môi trường khác.
- Không có bảo đảm toàn cục rằng JDK luôn làm tròn về ms, hay luôn phân giải tới từng ns.
- Resolution có thể thay đổi theo hệ điều hành, máy ảo, phần cứng, chính sách đồng bộ giờ và cài đặt JDK.
- Đồng hồ lịch có thể được điều chỉnh để đồng bộ; việc đọc thời gian UTC không phải cơ chế cung cấp thứ tự tăng nghiêm ngặt giữa mọi sự kiện.

Mẫu lấy timestamp:

```java
Instant createdAt = Instant.now();
```

*Đoạn này cần `import java.time.Instant;`. Nó phụ thuộc thời gian thực nên không có stdout xác định.*

**Không dùng độ dài chuỗi trả về làm phép đo resolution.** Ví dụ một formatter có thể in thêm các số 0 cuối, nhưng các số 0 đó không chứa thông tin đo mới.

## 6. `Clock`: nguồn thời gian có thể thay thế và kiểm thử

`java.time.Clock` có các factory hiện hành:

| Factory | Công dụng |
| --- | --- |
| `Clock.systemUTC()` | Nguồn thời điểm thực theo đồng hồ hệ thống, UTC |
| `Clock.system(ZoneId)` | Nguồn hệ thống với zone được chọn |
| `Clock.fixed(Instant, ZoneId)` | Mốc cố định, giúp unit test không phụ thuộc thời gian thực |
| `Clock.offset(base, Duration)` | Mô phỏng sớm hoặc muộn hơn base clock |
| `Clock.tick(base, Duration)` | Cắt về các mốc tick |
| `Clock.tickMillis(zone)` | Trả các mốc millisecond theo nguồn hệ thống |
| `Clock.tickSeconds(zone)` / `tickMinutes(zone)` | Trả các mốc giây/phút |

**`Clock.tick` không tăng độ phân giải của phần cứng.** Nó giới hạn mức thay đổi/hiển thị của giá trị. Javadoc còn cho phép implementation dùng cache, nên thời điểm quan sát tick mới có thể chậm hơn thời điểm base clock vượt qua mốc.

Lưu `ClockResolutionDemo.java`:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public class ClockResolutionDemo {
    public static void main(String[] args) {
        Instant value =
                Instant.parse("2026-03-04T05:06:07.123456789Z");

        Clock base = Clock.fixed(value, ZoneOffset.UTC);
        Clock tenMillis = Clock.tick(base, Duration.ofMillis(10));
        Clock second = Clock.tick(base, Duration.ofSeconds(1));
        Clock offset = Clock.offset(base, Duration.ofMillis(250));

        System.out.println("base = " + Instant.now(base));
        System.out.println("tick10ms = " + Instant.now(tenMillis));
        System.out.println("tickSecond = " + Instant.now(second));
        System.out.println("offset = " + Instant.now(offset));
        System.out.println("zone = " + base.getZone());
    }
}
```

```bash
javac ClockResolutionDemo.java
java ClockResolutionDemo
```

```text
base = 2026-03-04T05:06:07.123456789Z
tick10ms = 2026-03-04T05:06:07.120Z
tickSecond = 2026-03-04T05:06:07Z
offset = 2026-03-04T05:06:07.373456789Z
zone = Z
```

`Clock.tick(base, Duration.ofMillis(10))` cắt phần lẻ về bội số của 10 ms. `Clock.offset` cộng 250 ms vào mô hình thời gian, **không đo thực tế**. `Clock.fixed` được xây dựng từ một `Instant` có chín chữ số, nên ví dụ cho đầu ra xác định kể cả khi máy thật chỉ có resolution millisecond.

**Lưu ý:** `tickDuration` phải đáp ứng điều kiện API. Với duration có phần nhỏ hơn 1 ms, toàn duration phải chia hết một giây; không được dùng các giá trị lẻ tùy ý rồi suy ra đồng hồ sẽ chấp nhận. Các tick thông dụng như 1 ms, 10 ms, 1 giây, 1 phút là phù hợp.

### 6.1. Khi nào nên tiêm `Clock`?

Nên truyền `Clock` cho service phụ thuộc thời gian, thay vì hardcode `Instant.now()` trong mọi method. Production có thể tiêm `Clock.systemUTC()`; test dùng `Clock.fixed`/`offset` để kiểm tra deadline, TTL, khoảng hiệu lực hoặc bước qua ranh giới ngày giờ. Không dùng fixed clock để benchmark vì nó không chạy theo thời gian thật.

## 7. `System.currentTimeMillis()`: đơn vị ms, resolution phụ thuộc OS

`System.currentTimeMillis()` trả một `long` biểu thị **millisecond kể từ epoch UTC 1970**. Điều này có ích cho API/giao thức yêu cầu epoch milliseconds, nhưng **đơn vị trả về** không đồng nghĩa đồng hồ cập nhật đúng mỗi 1 ms. Javadoc nói granularity phụ thuộc hệ điều hành và đôi khi lớn hơn một millisecond.

Đoạn minh họa:

```java
long epochMillis = System.currentTimeMillis();
```

Không có stdout cố định vì giá trị phụ thuộc lúc chạy. Các kết luận sai cần tránh:

- “`currentTimeMillis()` luôn tăng sau mỗi millisecond” — không có bảo đảm.
- “Hai sự kiện có cùng epochMilli chắc chắn đồng thời” — chúng có thể cách nhau một khoảng nhỏ hơn granularity của nguồn.
- “`currentTimeMillis()` đo benchmark có độ chi tiết nanosecond” — sai về đơn vị và mục đích.
- “Đồng hồ lịch không bao giờ bị điều chỉnh” — sai; cơ chế sync/sửa giờ hệ thống có thể tác động.

Dùng `Instant.now(clock)` khi cần timestamp ở dạng mạnh về ngữ nghĩa hơn, có thể truyền và kiểm thử.

## 8. `System.nanoTime()`: nguồn high-resolution để đo elapsed time

`System.nanoTime()` trả một `long` từ nguồn high-resolution của JVM, **theo đơn vị nanosecond**, nhưng mốc gốc **tùy ý** và không liên quan epoch UTC. Theo Javadoc:

- Mốc gốc có thể nằm “trong tương lai” với giá trị trả về, vì vậy số raw có thể âm.
- Mọi lần gọi trong **một JVM** dùng cùng origin; JVM khác có thể dùng origin khác.
- Chỉ **hiệu của hai lần đọc từ cùng JVM** mới có ý nghĩa đo duration.
- Độ chính xác biểu diễn là nanosecond, **nhưng resolution chưa chắc nanosecond**.
- Hiệu lớn hơn xấp xỉ 292 năm có thể overflow long; đa phần đo thời gian xử lý ứng dụng ngắn hơn rất nhiều.

Mẫu đo:

```java
long startNanos = System.nanoTime();
try {
    performWork();
} finally {
    long elapsedNanos = System.nanoTime() - startNanos;
    // Đưa duration vào metric có đơn vị ns.
}
```

*Đoạn snippet không độc lập: `performWork()` là nghiệp vụ được định nghĩa trong ứng dụng. Giá trị elapsed thực không có stdout cố định.*

**Tuyệt đối không lưu raw `System.nanoTime()` vào trường `createdAtUtc` hoặc chuyển nó thành `Instant.ofEpochSecond(...)`.** Vì raw value không phải thời gian UTC. Không so sánh raw nanoTime đến từ hai JVM, hai lần khởi động process hay hai máy khác nhau.

### 8.1. Cách kiểm tra timeout tránh cộng gây overflow

Javadoc `System.nanoTime()` khuyên so sánh **hiệu** thay vì tạo deadline bằng phép cộng raw nanoTime:

```java
long start = System.nanoTime();
long timeoutNanos = Duration.ofSeconds(2).toNanos();

// Ở một lần kiểm tra về sau:
if (System.nanoTime() - start >= timeoutNanos) {
    // Đã vượt budget thời gian trôi qua.
}
```

*Snippet dùng `import java.time.Duration;`. Timeout phải là giá trị hợp lệ biểu diễn trong long nanos.* Tránh mẫu `System.nanoTime() >= start + timeoutNanos` vì cả phép cộng và so sánh raw counter có thể lỗi tại biên overflow. `System.nanoTime()` cũng không phải bộ đo “thời điểm hẹn theo UTC”, nên deadline lịch (ngày thanh toán, giờ bắt đầu sự kiện) dùng logic trên `Instant`/`ZonedDateTime` phù hợp hơn.

### 8.2. Không đo benchmark bằng một lần chạy

`System.nanoTime()` là nguồn đo duration đúng ngữ nghĩa, nhưng phép đo đơn lẻ vẫn bao gồm nhiễu do JIT compilation, warm-up, GC, scheduler, cache, I/O và contention. Với benchmark nghiêm túc, dùng **JMH** và phương pháp thử đại diện. Đừng in giá trị đo thực rồi khẳng định đó là stdout “chính xác” có thể tái lập trên mọi máy.

## 9. Bảng chọn API đúng mục đích

| Nhu cầu | API phù hợp | Giới hạn cần nhớ |
| --- | --- | --- |
| Timestamp lúc tạo bản ghi | `Instant.now(clock)` | Accuracy/resolution của hệ thống không cố định |
| Nhận epoch milliseconds | `System.currentTimeMillis()` hoặc `Instant.toEpochMilli()` | Mất mọi phần nhỏ hơn 1 ms |
| Đo thời gian hàm chạy | Hiệu của `System.nanoTime()` trong cùng JVM | Không dùng raw value làm UTC |
| So sánh hai instant đã có | `Instant.compareTo` hoặc `Duration.between` | Timestamp nguồn có thể sai lệch nếu đồng hồ chưa đồng bộ |
| Test điều kiện hết hạn | `Clock.fixed`/`offset` | Mô phỏng giá trị chính xác, không đo resolution máy |
| Giảm timestamp về bội 1 ms | `truncatedTo(MILLIS)` hoặc `Clock.tick` | Chủ động loại bỏ thông tin |
| Sắp xếp event có timestamp trùng | Sequence/ID hoặc logic ordering riêng | Timestamp không bảo đảm duy nhất/tăng nghiêm ngặt |
| Đo elapsed time giữa dịch vụ | Distributed tracing có đồng bộ/hiệu chỉnh phù hợp | Raw nanoTime giữa JVM không so sánh được |

**Đặc biệt:** `Duration.between(Instant.now(), Instant.now())` vẫn dựa trên hai lần đọc wall clock. Với đo thời gian trôi qua cho timeout hoặc benchmark trong JVM, `nanoTime()` phù hợp hơn.

## 10. Chuyển về epoch milliseconds làm mất nanosecond

Giả sử `Instant` có phần giây `.123456789`. Khi gọi `toEpochMilli()`, các chữ số sau millisecond bị loại. Chuyển ngược bằng `Instant.ofEpochMilli(...)` không thể khôi phục micro/nano đã mất.

Các API thường gặp:

- `Instant.truncatedTo(ChronoUnit.MILLIS)`: giữ bước millisecond.
- `Instant.truncatedTo(ChronoUnit.MICROS)`: giữ bước microsecond.
- `Instant.toEpochMilli()`: trả số `long` millisecond từ epoch.
- `Instant.ofEpochMilli(long)`: tạo Instant có phần nano là bội của 1 triệu.

Lưu `EpochPrecisionLossDemo.java`:

```java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public class EpochPrecisionLossDemo {
    public static void main(String[] args) {
        Instant original =
                Instant.parse("2026-08-01T00:00:00.123456789Z");

        Instant micros = original.truncatedTo(
                ChronoUnit.MICROS);
        Instant millis = original.truncatedTo(
                ChronoUnit.MILLIS);
        Instant restored =
                Instant.ofEpochMilli(original.toEpochMilli());

        System.out.println("original = " + original);
        System.out.println("micros = " + micros);
        System.out.println("millis = " + millis);
        System.out.println("restored = " + restored);
        System.out.println("equal = " +
                original.equals(restored));
    }
}
```

```bash
javac EpochPrecisionLossDemo.java
java EpochPrecisionLossDemo
```

```text
original = 2026-08-01T00:00:00.123456789Z
micros = 2026-08-01T00:00:00.123456Z
millis = 2026-08-01T00:00:00.123Z
restored = 2026-08-01T00:00:00.123Z
equal = false
```

`truncatedTo` là **cắt** về ranh giới đơn vị, không phải làm tròn tới đơn vị gần nhất. Ví dụ `.123789000` cắt thành `.123` ở cấp millisecond; quy tắc round-to-nearest lại có thể cho `.124`. Nếu nghiệp vụ yêu cầu rounding, hãy định nghĩa và kiểm thử quy tắc riêng, kể cả các giá trị âm/trước epoch.

Dữ liệu được chuyển qua database, JSON, message queue, log exporter hoặc REST API có thể bị giới hạn precision ở một trong các tầng này. `Instant` hỗ trợ nano không bảo đảm phía nhận hay cột DB lưu trọn 9 chữ số. Cần đọc contract của **database/driver/serializer thực dùng** và kiểm tra round-trip.

### 10.1. Cẩn thận với mốc trước 1970

`Instant.getEpochSecond()` có thể âm, nhưng `getNano()` luôn không âm. Tự tính `epochSecond * 1000 + nanoPart / 1_000_000` mà không xét quy tắc chuyển có thể sai ở ranh giới epoch. Hãy dùng API chuẩn.

Lưu `BeforeEpochDemo.java`:

```java
import java.time.Instant;

public class BeforeEpochDemo {
    public static void main(String[] args) {
        Instant before =
                Instant.parse("1969-12-31T23:59:59.999999999Z");

        System.out.println("epochSecond = " +
                before.getEpochSecond());
        System.out.println("nanoPart = " + before.getNano());
        System.out.println("epochMilli = " +
                before.toEpochMilli());
        System.out.println("restored = " +
                Instant.ofEpochMilli(before.toEpochMilli()));
    }
}
```

```bash
javac BeforeEpochDemo.java
java BeforeEpochDemo
```

```text
epochSecond = -1
nanoPart = 999999999
epochMilli = -1
restored = 1969-12-31T23:59:59.999Z
```

Mốc chỉ trước epoch 1 ns được biểu diễn bằng `-1 giây + 999999999 ns`. `toEpochMilli()` cho `-1`, không phải `0`. Ngoài ra, với instant rất xa trong quá khứ hoặc tương lai, `toEpochMilli()` có thể ném `ArithmeticException` nếu không vừa long.

## 11. Nanosecond trong LocalDateTime không tự bổ sung múi giờ

`LocalTime`, `LocalDateTime`, `OffsetDateTime` và `ZonedDateTime` đều có thể mang phần nano, nhưng chúng biểu diễn những khái niệm khác nhau:

- `LocalDateTime` chỉ chứa ngày giờ **địa phương**, không có offset hoặc timezone; chưa chỉ ra duy nhất một instant UTC.
- `OffsetDateTime` có UTC offset.
- `ZonedDateTime` có zone cùng quy tắc lịch, có thể liên quan DST, overlap hoặc gap.
- `Instant` mô tả thời điểm trên timeline UTC.

Lưu `ZoneNanosecondDemo.java`:

```java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class ZoneNanosecondDemo {
    public static void main(String[] args) {
        Instant instant =
                Instant.parse("2026-07-01T12:00:00.000000321Z");

        ZonedDateTime plusSeven =
                instant.atZone(ZoneOffset.ofHours(7));

        System.out.println("utc = " + instant);
        System.out.println("localPlus7 = " +
                plusSeven.toLocalDateTime());
        System.out.println("nanoPart = " + plusSeven.getNano());
        System.out.println("sameInstant = " +
                instant.equals(plusSeven.toInstant()));
    }
}
```

```bash
javac ZoneNanosecondDemo.java
java ZoneNanosecondDemo
```

```text
utc = 2026-07-01T12:00:00.000000321Z
localPlus7 = 2026-07-01T19:00:00.000000321
nanoPart = 321
sameInstant = true
```

Ở đây đổi sang offset cố định `+07:00` để có kết quả ổn định; không làm thay đổi instant hay mất phần nano. Trong hệ thống thực có quy tắc giờ mùa hè, chọn `ZoneId` chính xác thay vì giả định một offset cố định quanh năm. Một `LocalDateTime` có chín chữ số nano vẫn **chưa phải UTC timestamp** nếu không có offset/zone.

## 12. Chuyển `ChronoUnit`/`TimeUnit` và overflow

`ChronoUnit.NANOS.between(start, end)` tính số nanos nguyên giữa hai mốc nếu vừa trong long; `Duration.between(start,end).toNanos()` cho cùng kết quả với khoảng nhỏ. `TimeUnit` hỗ trợ đổi nano/micro/milli/second khi giao tiếp với API `java.util.concurrent`.

Lưu `NanosecondUnitsDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.concurrent.TimeUnit;

public class NanosecondUnitsDemo {
    public static void main(String[] args) {
        Instant start =
                Instant.parse("2026-01-01T00:00:00Z");
        Instant end = start.plusNanos(1_234_567);

        Duration diff = Duration.between(start, end);

        System.out.println("chronoNanos = " +
                ChronoUnit.NANOS.between(start, end));
        System.out.println("durationNanos = " + diff.toNanos());
        System.out.println("durationMillis = " + diff.toMillis());
        System.out.println("timeUnitMillis = " +
                TimeUnit.NANOSECONDS.toMillis(1_234_567));
        System.out.println("fiveMillisNanos = " +
                TimeUnit.MILLISECONDS.toNanos(5));
    }
}
```

```bash
javac NanosecondUnitsDemo.java
java NanosecondUnitsDemo
```

```text
chronoNanos = 1234567
durationNanos = 1234567
durationMillis = 1
timeUnitMillis = 1
fiveMillisNanos = 5000000
```

Tổng `1.234.567 ns` chỉ gồm **1 millisecond nguyên**. Đừng giả định kết quả `toMillis()` vẫn giữ được các nanos dư. `Duration.toNanos()` có thể ném `ArithmeticException` do overflow; một số phép chuyển của `TimeUnit` lại có chính sách bão hòa tại biên `Long.MIN_VALUE/MAX_VALUE`. Hãy xem contract của API bạn đang dùng thay vì mặc định mọi cách chuyển đều giống nhau.

## 13. Kiểm thử logic nanosecond với `Clock.fixed` và `offset`

Kiểm thử deadline, TTL, chu kỳ hiệu lực hay token expiry bằng `Thread.sleep(...)` dễ gây flaky test. Thay bằng nguồn đồng hồ được tiêm vào code.

Lưu `FixedClockExpiryDemo.java`:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public class FixedClockExpiryDemo {
    private final Clock clock;

    public FixedClockExpiryDemo(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiry) {
        return !Instant.now(clock).isBefore(expiry);
    }

    public static void main(String[] args) {
        Instant created =
                Instant.parse("2026-09-01T00:00:00.000000123Z");
        Instant expiry = created.plusNanos(750_000_000);

        Clock original = Clock.fixed(created, ZoneOffset.UTC);
        Clock before = Clock.offset(
                original, Duration.ofNanos(749_999_999));
        Clock at = Clock.offset(
                original, Duration.ofNanos(750_000_000));
        Clock after = Clock.offset(
                original, Duration.ofNanos(750_000_001));

        System.out.println("before = " +
                new FixedClockExpiryDemo(before).isExpired(expiry));
        System.out.println("at = " +
                new FixedClockExpiryDemo(at).isExpired(expiry));
        System.out.println("after = " +
                new FixedClockExpiryDemo(after).isExpired(expiry));
    }
}
```

```bash
javac FixedClockExpiryDemo.java
java FixedClockExpiryDemo
```

```text
before = false
at = true
after = true
```

Bài test định nghĩa rõ quy tắc **hết hạn khi `now >= expiry`**. Ranh giới trước đúng 1 ns, đúng mốc và sau mốc 1 ns đều được kiểm chứng bằng **giá trị mô phỏng**, không phụ thuộc độ phân giải của đồng hồ thật. Không đánh đồng khả năng kiểm thử phép so sánh 1 ns với khả năng máy đo được hai sự kiện thực cách nhau chính xác 1 ns.

Nếu cần test thuật toán timeout dựa trên `System.nanoTime()`, hãy cân nhắc abstraction riêng cho elapsed-time source (ví dụ `LongSupplier`) và điều khiển giá trị tick trong test. `Clock.fixed` là **đồng hồ lịch cố định**, không thay thế thích hợp cho đo elapsed time thực trong benchmark.

## 14. Timestamp không bảo đảm ID duy nhất hoặc thứ tự tăng tuyệt đối

Hai lời gọi `Instant.now()` có thể trả cùng giá trị nếu độ phân giải của nguồn chưa đủ; việc cắt về milli càng tăng khả năng trùng. Wall clock cũng có thể bị chỉnh nên không phải nguồn thứ tự toàn phần giữa các server.

Ví dụ chủ động tạo hai timestamp giống nhau bằng fixed clock, lưu `TimestampCollisionDemo.java`:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public class TimestampCollisionDemo {
    public static void main(String[] args) {
        Instant original =
                Instant.parse("2026-03-04T05:06:07.123456789Z");
        Clock fixed = Clock.fixed(original, ZoneOffset.UTC);
        Clock millis = Clock.tick(fixed, Duration.ofMillis(1));

        Instant first = Instant.now(millis);
        Instant second = Instant.now(millis);

        System.out.println("first = " + first);
        System.out.println("second = " + second);
        System.out.println("same = " + first.equals(second));
    }
}
```

```bash
javac TimestampCollisionDemo.java
java TimestampCollisionDemo
```

```text
first = 2026-03-04T05:06:07.123Z
second = 2026-03-04T05:06:07.123Z
same = true
```

Không dùng timestamp làm khóa duy nhất khi nghiệp vụ cần uniqueness tuyệt đối. Có thể sử dụng sequence của database, UUID hoặc một ID khác được tạo theo contract rõ ràng. Khi cần **thứ tự tổng quát** giữa nhiều máy, cần thêm sequence/logical ordering/transaction order; chỉ thêm 9 chữ số thập phân vào timestamp không giải được phân tán.

## 15. Lưu trữ, JSON và database: kiểm tra precision end-to-end

Khi lưu timestamp có nanosecond, có thể mất dữ liệu ở nhiều chặng:

1. `Instant` trong Java giữ tối đa 9 chữ số phần giây.
2. Serializer có thể ghi ISO-8601 theo số chữ số cần thiết, hoặc ép thành `long epochMillis`.
3. Database timestamp column có thể giới hạn precision ở ms/µs/ns tùy engine, kiểu cột và khai báo schema.
4. JDBC/ORM mapping có thể chuyển kiểu, đổi offset/zone hoặc áp dụng làm tròn/cắt.
5. Bên tiêu thụ JSON có thể chỉ phân tích milliseconds rồi chuyển ngược thành Instant.

**Không đoán độ chính xác của cột chỉ qua tên `TIMESTAMP` hoặc `DATETIME`.** Kiểm tra DB/driver cụ thể và chạy test round-trip với `.123456789`. Nếu một tầng chỉ giữ microsecond, so sánh raw `Instant` của trước và sau sẽ khác trừ khi chuẩn hóa cùng chính sách precision.

Tài liệu API cần quy định rõ:

- Dùng UTC epoch hay ngày giờ địa phương? Có offset/zone không?
- Hỗ trợ tối đa bao nhiêu chữ số phần giây?
- Khi dư chữ số, cắt hay làm tròn? Có xử lý số âm/trước epoch đúng không?
- Cách parse/format có nhất quán không? Có bảo toàn thứ tự và thời điểm thực tế không?
- Timestamp có phải khóa định danh không, hay chỉ là dữ liệu quan sát?

`Instant.toString()` không bảo đảm luôn in đúng 9 chữ số: Java có thể dùng phần lẻ `.123Z`, `.123456Z` hoặc `.123456789Z` tùy giá trị. Nếu giao thức thực sự yêu cầu độ dài cố định, dùng `DateTimeFormatterBuilder.appendFraction(ChronoField.NANO_OF_SECOND, 9, 9, true)` cùng zone/offset hợp lệ. Việc định dạng với 9 chữ số vẫn **không tăng accuracy** của nguồn.

## 16. Những sai lầm thường gặp

| Hiểu lầm | Giải thích đúng |
| --- | --- |
| `Instant.getNano()` là tổng nanos kể từ epoch | Chỉ là thành phần nano trong giây, từ 0 đến 999.999.999 |
| Chuỗi timestamp có 9 chữ số ⇒ đồng hồ đo chính xác 1 ns | Chỉ chứng minh độ chi tiết biểu diễn |
| `Instant.now()` mỗi lần đều cho giá trị khác | Không có bảo đảm |
| `Clock.systemUTC()` luôn dùng nguồn có resolution 1 ns | Dùng nguồn tốt nhất hệ thống hỗ trợ, độ phân giải có thể thấp hơn |
| `Clock.tickMillis` làm đồng hồ máy chính xác hơn | Chỉ cắt về mốc milli, có thể giảm độ chi tiết |
| `System.currentTimeMillis()` luôn thay đổi mỗi 1 ms | Granularity phụ thuộc OS |
| `System.nanoTime()` là UTC timestamp | Mốc gốc tùy ý; chỉ lấy hiệu trong một JVM |
| So sánh raw nanoTime từ hai JVM | Không có origin chung được bảo đảm |
| Đo timeout bằng `nowNano >= startNano + timeout` | Có rủi ro overflow; so sánh hiệu |
| `Duration.getNano()` là tổng nanos | Chỉ là nano component; dùng `toNanos()` nếu phù hợp |
| `Duration.toNanos()` luôn không overflow | Có thể ném `ArithmeticException` |
| `Instant.toEpochMilli()` giữ nguyên nanosecond | Loại bỏ phần dưới millisecond |
| `truncatedTo(MILLIS)` là làm tròn | Đây là cắt phần lẻ về ranh giới đơn vị |
| `LocalDateTime` có 9 chữ số là UTC instant | Chưa có offset/zone để định nghĩa timeline |
| Timestamp luôn tăng và duy nhất | Wall clock có thể chỉnh và giá trị có thể trùng |
| Test sleep 1 ns đủ kiểm tra deadline 1 ns | Scheduler và timer resolution không hứa điều đó; dùng fixed/offset clock |
| Một lần đo `nanoTime()` đủ cho benchmark | Cần phương pháp đo nhiều lần, warm-up và phân tích môi trường |

## 17. Bài tập có lời giải

**Bài 1.** Có ba sự kiện trong cùng một giây, lần lượt cách mốc cố định `100 ns`, `500 ns`, `900 ns`. Sắp xếp tăng dần bằng `Instant` và tính độ lệch giữa hai sự kiện đầu.

**Bài 2.** Đưa cả ba thời điểm sang `epoch milliseconds`. Vì sao số lượng giá trị `epochMillis` phân biệt có thể bằng 1 dù ba `Instant` khác nhau?

**Bài 3.** Cần đo thời gian chạy một đoạn code. Giải thích vì sao `System.nanoTime()` khác `Instant.now()` về ngữ nghĩa và vì sao không nên lưu raw nanoTime làm thời điểm tạo bản ghi.

**Bài 4.** Cần test một token hết hạn đúng tại timestamp có phần lẻ ns. Viết logic dùng `Clock.fixed`/`offset` thay vì `Thread.sleep`.

**Bài 5.** Một API nhận `"2026-08-01T00:00:00.123456789Z"` nhưng trả `epochMillis`. Hãy mô tả thông tin không thể khôi phục và thiết kế hợp đồng lưu trữ rõ ràng nếu cần giữ nguyên nanos.

Lưu lời giải bài 1–2 trong `NanosecondPractice.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.List;

public class NanosecondPractice {
    public static void main(String[] args) {
        Instant base =
                Instant.parse("2026-09-01T00:00:00Z");

        List<Instant> input = List.of(
                base.plusNanos(900),
                base.plusNanos(100),
                base.plusNanos(500)
        );

        List<Instant> sorted = input.stream()
                .sorted()
                .toList();

        List<Long> offsets = sorted.stream()
                .map(i -> Duration.between(base, i).toNanos())
                .toList();

        long gap = Duration.between(
                sorted.get(0), sorted.get(1)).toNanos();

        long uniqueMillis = sorted.stream()
                .map(Instant::toEpochMilli)
                .distinct()
                .count();

        System.out.println("offsets = " + offsets);
        System.out.println("firstGap = " + gap);
        System.out.println("uniqueEpochMillis = " + uniqueMillis);
    }
}
```

```bash
javac NanosecondPractice.java
java NanosecondPractice
```

```text
offsets = [100, 500, 900]
firstGap = 400
uniqueEpochMillis = 1
```

Ba `Instant` được sắp xếp đúng với độ lệch nano; sau khi đổi sang millisecond chúng cùng nằm trong **một mốc ms**. Bài 3 dùng `nanoTime` cho duration, `Instant` cho UTC timestamp. Bài 4 xem `FixedClockExpiryDemo`. Bài 5 cần giữ cặp seconds+nanos hoặc ISO-8601 string với precision contract, tránh ép tất cả giá trị về epoch milliseconds.

## 18. Checklist áp dụng

- Tôi đang mô hình hóa một **instant**, một **local date-time** hay một **duration**?
- Có nhầm precision của `Instant` với resolution/accuracy của clock không?
- Tôi có kiểm chứng nguồn đồng hồ của môi trường thực và ghi rõ các giới hạn chưa?
- Đo elapsed time trong JVM đã dùng hiệu `System.nanoTime()` chưa?
- Đã tránh so sánh raw nanoTime giữa JVM hoặc dùng nó làm timestamp UTC?
- Timeout có dùng `now - start >= timeout` thay vì so sánh với `start + timeout` có thể tràn?
- Nếu convert xuống millis/micros, tôi đã ghi nhận việc mất phần lẻ nano và chính sách rounding/truncation?
- Timestamp lưu trong database/JSON/API có cùng precision contract hai chiều không?
- Có nhầm `Duration.getNano()` với `toNanos()` hoặc bỏ qua overflow không?
- Nếu cần zone, tôi đã chọn `Instant`/`OffsetDateTime`/`ZonedDateTime` đúng semantics?
- Nếu cần uniqueness/order, đã có ID/sequence/logical ordering độc lập chưa?
- Unit test ranh giới nanosecond đã tiêm `Clock.fixed`/`offset` và có stdout/assert xác định?
- Hiệu năng đã được đánh giá bằng phương pháp thích hợp thay vì một phép đo đơn lẻ?

## 19. Tài liệu Java hiện hành

- Oracle Java SE 26 — `Instant`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html
- Oracle Java SE 26 — `Duration`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html
- Oracle Java SE 26 — `Clock`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html
- Oracle Java SE 26 — `System.currentTimeMillis` và `System.nanoTime`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html
- Oracle Java SE 26 — `ChronoUnit`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ChronoUnit.html
- Oracle Java SE 26 — `TimeUnit`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/TimeUnit.html
- Oracle Java SE 26 — `DateTimeFormatterBuilder`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html

**Kết luận:** `Instant` và `Duration` có khả năng biểu diễn nanosecond nhưng **đồng hồ hệ thống không cam kết đo chính xác từng nanosecond**. `Instant.now(clock)` dành cho thời điểm UTC, `System.nanoTime()` dành cho đo khoảng thực thi trong một JVM. Khi chuyển sang milliseconds hoặc truyền qua storage/API, phải xác định độ chi tiết bị mất. Timestamp không thay thế một cơ chế ID hoặc thứ tự đáng tin cậy.