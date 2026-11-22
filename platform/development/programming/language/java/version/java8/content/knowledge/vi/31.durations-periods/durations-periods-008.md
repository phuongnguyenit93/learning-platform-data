# Đo thời gian thực thi bằng đồng hồ đơn điệu trong Java

## 1. Vấn đề: “Mất bao lâu?” khác “Xảy ra lúc mấy giờ?”

Trong nhóm kiến thức **Khoảng thời gian**, câu hỏi **đo thời gian thực thi bằng đồng hồ đơn điệu** (*monotonic elapsed-time clock*) quan trọng vì phần mềm phải đo độ trễ request, thời gian chạy thuật toán, thời gian chờ timeout, tiến độ tác vụ và mức trễ của lời gọi I/O. Không phải mọi đồng hồ trong Java đều phù hợp cho nhiệm vụ này.

Hai câu hỏi có bản chất khác nhau:

1. **Một sự kiện diễn ra tại thời điểm nào?** Cần timestamp theo trục UTC để ghi log, truyền API hoặc lưu database. Dùng `Instant.now()`, `Clock`, hoặc `System.currentTimeMillis()` khi API thực sự cần epoch milliseconds.
2. **Một tác vụ đã tiêu tốn bao nhiêu thời gian trôi qua?** Cần đo hiệu hai lần đọc của nguồn thời gian ổn định cho elapsed time. Trong Java, sử dụng **`System.nanoTime()`**.

`System.nanoTime()` là API đã có từ trước Java 8, **không phải tính năng lỗi thời**. Nó tiếp tục là cách trực tiếp và được tài liệu JDK hiện hành hướng dẫn để đo elapsed time trong một JVM. Trên phần lớn hệ thống, JVM sử dụng nguồn thời gian có tính chất đơn điệu phù hợp cho đo khoảng thời gian, thay vì đồng hồ ngày giờ dân sự có thể bị điều chỉnh.

Quy tắc trọng tâm:

```java
long started = System.nanoTime();
try {
    doWork();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    recordElapsed(elapsedNanos);
}
```

Đây là **đoạn minh họa bên trong một phương thức**: `doWork()` và `recordElapsed(...)` đại diện cho tác vụ và nơi ghi nhận metric của ứng dụng. Các chương trình Java hoàn chỉnh, có thể biên dịch/chạy và được kiểm thử, xuất hiện ở những mục sau.

**Không dùng giá trị thô của `nanoTime()` làm timestamp, không lấy một lần `nanoTime()` trừ một lần `currentTimeMillis()` và không lấy nanoTime của hai JVM khác nhau để tính chênh lệch.**

## 2. Đồng hồ tường (wall clock) và đồng hồ đo khoảng thời gian

**Wall clock** trả lời “bây giờ là lúc nào” trong hệ thống thời gian dân sự hoặc epoch UTC. Nó cần thiết cho lịch, timestamp sự kiện, giao tiếp giữa máy và hiển thị múi giờ, nhưng có thể bị điều chỉnh khi đồng hồ máy được đồng bộ, người quản trị sửa giờ hoặc có các thay đổi về nguồn thời gian.

**Nguồn thời gian đơn điệu** phục vụ đo **khoảng thời gian trôi qua**. Thay vì gắn kết với 1970-01-01 UTC, nó dùng một mốc nội bộ và bạn quan tâm tới hiệu `end - start`. Tên gọi “đơn điệu” nhấn mạnh mục đích tránh các cú nhảy đồng hồ dân sự làm phép đo elapsed time âm hoặc sai.

| Câu hỏi | API phù hợp | Không nên dùng thay thế |
| --- | --- | --- |
| Request nhận lúc nào theo UTC? | `Instant.now()` | `System.nanoTime()` làm timestamp |
| In ngày giờ cho người dùng | `ZonedDateTime` / `DateTimeFormatter` | Nano tick |
| Một lời gọi API mất bao nhiêu ms? | `System.nanoTime()` lấy **hiệu** | Chênh `LocalDateTime.now()` |
| Đã quá timeout 250 ms chưa? | Hiệu nano tick so với `TimeUnit.MILLISECONDS.toNanos(250)` | So mốc epoch có thể bị điều chỉnh |
| Công việc dùng bao nhiêu CPU time? | CPU timer như `ThreadMXBean` nếu được hỗ trợ | Nano elapsed time nếu muốn CPU-only |
| Chu kỳ tháng/năm trên lịch | `Period` hoặc ngày/tháng theo lịch | Duration hoặc nano ticks |
| Lưu một elapsed duration ra báo cáo | `Duration` hoặc số kèm đơn vị rõ | Raw `nanoTime()` |

**Daylight saving time (DST) không tự làm epoch milliseconds nhảy**: đổi offset khi hiển thị giờ địa phương không thay đổi bản chất UTC epoch. Rủi ro của wall clock với elapsed time là khả năng **đồng hồ hệ thống được chỉnh** và các đặc tính không bảo đảm đơn điệu, không phải cứ đến ngày DST thì `currentTimeMillis()` tất yếu nhảy lùi.

## 3. Hợp đồng chính xác của `System.nanoTime()`

JavaDoc `System.nanoTime()` mô tả nó là “giá trị hiện tại của nguồn thời gian độ phân giải cao trong JVM”, đơn vị **nanosecond**. Những điểm quan trọng:

- **Chỉ dùng để đo elapsed time**, không liên quan trực tiếp đến ngày/giờ tường hoặc UTC.
- Giá trị biểu diễn nanoseconds tính từ **một mốc cố định nhưng tùy ý**; mốc đó có thể ở tương lai, nên **giá trị âm là hợp lệ**.
- Các lời gọi trong **cùng một JVM instance** chia sẻ mốc gốc; các JVM khác có thể có mốc khác.
- Giá trị có **đơn vị nanosecond**, nhưng không bảo đảm clock có khả năng phân biệt mọi khoảng cách 1 ns. **Precision của biểu diễn không bằng resolution của nguồn**.
- Các chênh lệch quá khoảng **2^63 nanoseconds (~292 năm)** không thể được tính đúng bằng một phép trừ `long` đơn giản do tràn.
- **Chỉ hiệu giữa hai lần đọc mới có nghĩa**. Đừng coi giá trị thô là timestamp hoặc so sánh với epoch.

Vì vậy:

```java
long t0 = System.nanoTime();
// Tác vụ cần đo.
long t1 = System.nanoTime();
long elapsedNanos = t1 - t0;
```

Không viết:

```java
long timestamp = System.nanoTime(); // Sai ý nghĩa: không phải UTC timestamp.
```

Cũng không gọi `Instant.ofEpochSecond(System.nanoTime())`: nano tick không phải epoch seconds; phép chuyển đó tự bịa một mốc thời gian dân sự.

### “Đơn điệu” không có nghĩa mỗi lần gọi đều phải lớn hơn trước

Nguồn đo có thể có **độ phân giải hữu hạn**; hai lần đọc rất sát nhau có thể cho cùng giá trị, `elapsedNanos == 0`, đặc biệt khi khối đo rất ngắn. Tên “nanoTime” không cam kết rằng mỗi thao tác mất tối thiểu một nano giây hay rằng mọi thời điểm đo đều khác nhau.

Ngoài ra, đặc tính của nguồn thời gian qua suspend/resume, máy ảo hóa, cấu hình hệ điều hành và phần cứng có thể khác nhau. Đừng suy từ `nanoTime()` ra một đồng hồ vật lý tuyệt đối lý tưởng trong mọi hoàn cảnh. API này vẫn là lựa chọn đúng **theo hợp đồng Java** cho khoảng thời gian chạy của tác vụ trong cùng JVM.

## 4. Mẫu đo tối thiểu và ranh giới đo

Quy trình thường gặp:

1. Đặt `start = System.nanoTime()` **ngay trước phần cần đo**.
2. Thực thi đúng phần công việc đã xác định.
3. Lấy `elapsed = System.nanoTime() - start` **ngay sau phần cần đo**.
4. Chuyển đơn vị nếu cần, ghi metric hoặc kiểm tra timeout.
5. Nếu phần công việc có thể ném exception, cân nhắc `try/finally` để vẫn ghi elapsed.

```java
long started = System.nanoTime();

int total = calculateTotal();

long elapsed = System.nanoTime() - started;
double elapsedMillis = elapsed / 1_000_000.0;
```

Đây là đoạn minh họa trong phương thức có `calculateTotal()`. `elapsedMillis` có thể là số lẻ, ví dụ `1.234567` ms. Chia cho `1_000_000.0` (có dấu chấm) để dùng phép chia số thực; chia cho `1_000_000L` sẽ cho **số nguyên bị cắt phần lẻ**.

### Đo phần nào?

Đo toàn bộ hàm có thể bao gồm:
- CPU thực thi mã Java.
- Chờ lock, scheduling và context switch.
- Thời gian thực thi bên thứ ba.
- Garbage collection hoặc các pause của runtime.
- Chờ I/O, mạng, database hoặc filesystem.
- Công việc đồng bộ bên trong phần được bao bởi hai timestamp.

Đây là **latency theo thời gian trôi qua**, không phải “CPU time thuần”. Nếu bạn chỉ muốn đo một đoạn tính toán nhưng đặt `println`, khởi tạo framework, đọc file hoặc setup dữ liệu trong khoảng đo, kết quả sẽ bao gồm cả overhead đó. Hãy xác định start/end theo đúng câu hỏi cần trả lời.

## 5. Đơn vị: nanosecond, microsecond, millisecond, second

Các hằng số cơ bản:

```text
1 second      = 1,000 milliseconds
1 millisecond = 1,000 microseconds
1 microsecond = 1,000 nanoseconds
1 millisecond = 1,000,000 nanoseconds
1 second      = 1,000,000,000 nanoseconds
```

Để đổi từ `elapsedNanos`:

```java
long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
double elapsedMillisPrecise = elapsedNanos / 1_000_000.0;
Duration duration = Duration.ofNanos(elapsedNanos);
```

Đoạn minh họa trong phương thức có import `java.util.concurrent.TimeUnit`, `java.time.Duration`.

| Cách biểu diễn | Ý nghĩa | Cảnh báo |
| --- | --- | --- |
| `elapsedNanos` | Raw duration trong `long` nanoseconds | Không phải timestamp |
| `TimeUnit.NANOSECONDS.toMillis(nanos)` | Số milli giây dạng `long` | Phần lẻ nhỏ hơn 1 ms bị bỏ |
| `nanos / 1_000_000.0` | Số ms dạng `double` để hiển thị | Có thể mất chính xác biểu diễn số thực |
| `Duration.ofNanos(nanos)` | Giá trị duration bất biến, có thể format/compare | `Duration` không tự tạo đồng hồ |
| `TimeUnit.MILLISECONDS.toNanos(250)` | 250 ms → 250 triệu ns | Tránh tự nhân làm tràn khi timeout lớn |

`TimeUnit` có khả năng **chuyển đơn vị** và dùng trong nhiều API đồng bộ của Java như `Future.get(timeout, unit)`. Lưu ý conversion về đơn vị thô hơn có thể **truncation**; phép chuyển về đơn vị nhỏ hơn có thể **saturate** khi vượt miền `long` tùy hợp đồng của TimeUnit. Không tự tính `milliseconds * 1_000_000` trên `long` không kiểm soát overflow.

`Duration.ofNanos` thích hợp khi cần biểu diễn elapsed time dưới dạng một object có nghĩa, nhưng nó chỉ bọc kết quả đo được. `Duration.between(Instant.now(), Instant.now())` dùng hai lần đọc wall clock và **không thay thế** cơ chế đo monotonic.

## 6. Chương trình Java đầy đủ: đo một phép tính thật

Tạo tệp `RealElapsedDemo.java`:

```java
import java.util.concurrent.TimeUnit;

public class RealElapsedDemo {
    static long sumUpTo(int end) {
        long total = 0;
        for (int i = 1; i <= end; i++) {
            total += i;
        }
        return total;
    }

    public static void main(String[] args) {
        long start = System.nanoTime();
        long result = sumUpTo(10_000);
        long elapsed = System.nanoTime() - start;

        System.out.println("result = " + result);
        System.out.println("elapsed nonnegative = " +
                (elapsed >= 0));
        System.out.println("elapsed nanos captured = " +
                (elapsed >= 0));
        System.out.println("elapsed millis >= 0 = " +
                (TimeUnit.NANOSECONDS.toMillis(elapsed) >= 0));
    }
}
```

```bash
javac -encoding UTF-8 RealElapsedDemo.java
java RealElapsedDemo
```

Trên nguồn `nanoTime` hoạt động bình thường theo mục đích đo elapsed time, chương trình in:

```text
result = 50005000
elapsed nonnegative = true
elapsed nanos captured = true
elapsed millis >= 0 = true
```

Mục đích của ví dụ là minh họa **cách đặt hai lần đo** và tránh ràng buộc bài học vào một con số thời gian cụ thể. Kết quả phép cộng `1 + ... + 10000 = 50005000` là cố định; còn **`elapsed` thực tế thay đổi theo CPU, JIT, GC, tải hệ thống và thời điểm chạy**.

Nếu muốn nhìn số thực:

```java
System.out.printf(
        java.util.Locale.ROOT,
        "elapsed = %.6f ms%n",
        elapsed / 1_000_000.0);
```

Dòng này là **đoạn minh họa thêm trong `main`**, kết quả số là biến động nên không có stdout cố định để chép nguyên văn. Với khối đo ngắn, kết quả còn chứa overhead đọc clock; **đừng lấy một phép đo duy nhất để kết luận thuật toán nhanh hay chậm**.

## 7. Stopwatch là một abstraction cho khoảng thời gian

Khi ứng dụng nhiều nơi cần đo khoảng thời gian, có thể đóng gói việc lấy start, đọc elapsed, dừng và chuyển đơn vị vào một **Stopwatch** nhỏ.

Hợp đồng thiết kế:
- Ghi `started` đúng một lần khi bắt đầu.
- Đọc ticker hiện tại rồi lấy **hiệu** so với `started`.
- Sau khi `stop()`, giữ một giá trị dừng không đổi.
- Không cung cấp raw tick như timestamp có ý nghĩa với người dùng.
- Không giả định một Stopwatch dùng đồng thời nhiều thread nếu class chưa thiết kế đồng bộ.
- Hỗ trợ **ticker injection** để test mà không phải ngủ thật.

Java có interface `LongSupplier` (Java 8) — chức năng nhận `long` không cần argument. Dùng `System::nanoTime` cho production và một biến giả lập `AtomicLong::get` cho test.

## 8. Ví dụ đầy đủ: Stopwatch với ticker có thể thay thế trong test

Tạo `MonotonicStopwatchDemo.java`:

```java
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public class MonotonicStopwatchDemo {
    static final class Stopwatch {
        private final LongSupplier ticker;
        private final long started;
        private long stoppedAt;
        private boolean stopped;

        private Stopwatch(LongSupplier ticker) {
            this.ticker = Objects.requireNonNull(ticker);
            this.started = ticker.getAsLong();
        }

        static Stopwatch start(LongSupplier ticker) {
            return new Stopwatch(ticker);
        }

        long elapsedNanos() {
            return (stopped ? stoppedAt : ticker.getAsLong())
                    - started;
        }

        long stop() {
            if (!stopped) {
                stoppedAt = ticker.getAsLong();
                stopped = true;
            }
            return stoppedAt - started;
        }
    }

    public static void main(String[] args) {
        AtomicLong fake = new AtomicLong(1_000_000_000L);
        Stopwatch sw = Stopwatch.start(fake::get);

        fake.addAndGet(123_456_789L);

        System.out.println("running nanos = " +
                sw.elapsedNanos());
        System.out.println("stop nanos = " + sw.stop());

        fake.addAndGet(200_000_000L);

        System.out.println("after stop nanos = " +
                sw.elapsedNanos());
        System.out.println("millis truncated = " +
                TimeUnit.NANOSECONDS.toMillis(sw.stop()));

        System.out.printf(Locale.ROOT,
                "millis decimal = %.6f%n",
                sw.stop() / 1_000_000.0);
    }
}
```

```bash
javac -encoding UTF-8 MonotonicStopwatchDemo.java
java MonotonicStopwatchDemo
```

```text
running nanos = 123456789
stop nanos = 123456789
after stop nanos = 123456789
millis truncated = 123
millis decimal = 123.456789
```

`AtomicLong fake` ở đây là **nguồn thời gian giả lập**, không phải đồng hồ thật. Sau khi `stop()`, dù `fake` tăng thêm 200 triệu nano, `elapsedNanos()` vẫn trả kết quả đã chốt.

Trong production có thể gọi:

```java
Stopwatch stopwatch = Stopwatch.start(System::nanoTime);
try {
    // Đo phần việc thực sự cần thiết.
} finally {
    long nanos = stopwatch.stop();
    // Ghi metric theo đơn vị nanos.
}
```

Đoạn này minh họa **bên trong phạm vi nhìn thấy class Stopwatch** và không phải chương trình chạy độc lập. Nếu Stopwatch được dùng bởi nhiều thread, cần quyết định rõ ownership/đồng bộ; class đơn giản bên trên là **single-owner**, không hứa thread-safe chỉ vì ticker là AtomicLong.

## 9. Kiểm thử đồng hồ đơn điệu không cần Thread.sleep

Test “ngủ 50 ms rồi assert elapsed == 50 ms” dễ thất bại vì scheduler, độ phân giải clock, pause GC và tải hệ thống. Với logic chuyển đơn vị, deadline, pause/resume hoặc trạng thái stopwatch, **inject ticker giả** sẽ đáng tin hơn:

```java
AtomicLong ticker = new AtomicLong(1_000L);
long started = ticker.get();

ticker.addAndGet(250_000_000L);

long elapsed = ticker.get() - started;
// Chính xác 250_000_000 nanos = 250 milliseconds.
```

Đây là đoạn minh họa với `import java.util.concurrent.atomic.AtomicLong`. Không cần đợi 250 ms thật để test.

Hãy tách hai loại test:
- **Unit test logic**: dùng nguồn giả lập để kiểm tra tính toán, ranh giới, timeout, trạng thái stop.
- **Integration/production observation**: sử dụng `System.nanoTime` thật để đo tính năng trên runtime và phần cứng mục tiêu.

Nếu test sự kiện theo **ngày/giờ dân sự** như lịch hẹn “ngày mai”, nên inject `java.time.Clock`. Nếu test **elapsed ticks**, inject `LongSupplier` hoặc abstraction `Ticker` riêng. `Clock.fixed(...)` cung cấp **fixed Instant**, nhưng **không biến `System.nanoTime()` thành đồng hồ test có thể điều khiển**.

## 10. Timeout: so **hiệu thời gian**, không so timestamp cộng timeout

Khi ứng dụng cần kiểm tra “đã quá 250 ms chưa?”, mẫu đơn giản:

```java
long started = System.nanoTime();
long timeoutNanos = TimeUnit.MILLISECONDS.toNanos(250L);

// ... trong vòng lặp hoặc điểm kiểm tra ...
boolean expired =
        System.nanoTime() - started >= timeoutNanos;
```

Đây là đoạn minh họa sau khi import `java.util.concurrent.TimeUnit`. Nhớ dùng **cùng đơn vị** hai vế. Trong trường hợp timeout dưới `Long.MAX_VALUE` nanoseconds và khoảng elapsed thực tế trong miền hiệu biểu diễn được, cách này tránh lỗi so sánh mốc tuyệt đối khi bộ đếm `long` wrap.

**Không khuyến nghị:**

```java
long deadline = started + timeoutNanos;
boolean expired = System.nanoTime() >= deadline;
```

Vì `nanoTime` có gốc tùy ý và `long` có thể wrap qua `Long.MAX_VALUE` sang vùng âm, việc so sánh **giá trị raw** với `>=` có thể kết luận sai. Phép trừ **`now - started`** mới là cách JavaDoc minh họa.

Không lấy `started` từ một JVM rồi dùng `now` của JVM khác; mốc origin không được chia sẻ qua tiến trình. Đối với timeouts phân tán, cần protocol và thiết kế deadline có thông tin thời gian, đồng bộ/trễ mạng rõ ràng, không truyền raw nano tick.

### Mốc overflow cần hiểu

Phạm vi biểu diễn signed `long` là từ `Long.MIN_VALUE` tới `Long.MAX_VALUE`. Một `System.nanoTime()` có thể có giá trị âm, và số tick có thể wrap. Với khoảng đo thực dưới khoảng **292 năm**, phép **hiệu có thứ tự** vẫn có thể khôi phục elapsed đúng trong miền `long` dù raw counter đi qua biên.

Nhưng **không có lời hứa** rằng đo khoảng 300 năm có thể diễn đạt bằng một `long` nanoseconds. Đừng dùng logic này như bộ lưu trữ duration vô hạn; với timeout thực tế tính bằng mili giây/giây/phút/giờ, miền `long` rất rộng.

## 11. Ví dụ đầy đủ: sai lầm ở biên Long.MAX_VALUE

Tạo `TimeoutArithmeticDemo.java`:

```java
import java.util.concurrent.TimeUnit;

public class TimeoutArithmeticDemo {
    static boolean expired(
            long started, long now, long timeoutNanos) {
        if (timeoutNanos < 0) {
            throw new IllegalArgumentException(
                    "negative timeout");
        }
        return now - started >= timeoutNanos;
    }

    public static void main(String[] args) {
        long started = Long.MAX_VALUE - 5;
        long timeout = 20;

        long before = started + 5;
        long after = started + 25;
        long deadline = started + timeout;

        System.out.println("before elapsed = " +
                (before - started));
        System.out.println("before expired = " +
                expired(started, before, timeout));
        System.out.println("after elapsed = " +
                (after - started));
        System.out.println("after expired = " +
                expired(started, after, timeout));

        System.out.println("naive before >= deadline = " +
                (before >= deadline));
        System.out.println("timeout millis->nanos = " +
                TimeUnit.MILLISECONDS.toNanos(250));
        System.out.println("negative origin permitted = " +
                (Long.MIN_VALUE < 0));
    }
}
```

```bash
javac -encoding UTF-8 TimeoutArithmeticDemo.java
java TimeoutArithmeticDemo
```

```text
before elapsed = 5
before expired = false
after elapsed = 25
after expired = true
naive before >= deadline = true
timeout millis->nanos = 250000000
negative origin permitted = true
```

Chúng ta tạo **giá trị giả lập gần `Long.MAX_VALUE`** để quan sát wrap, không có nghĩa `System.nanoTime()` của một JVM mới luôn bắt đầu gần số này. Khi mới trôi **5 ns** (ít hơn timeout 20 ns), phép so sánh raw `before >= deadline` lại **true** vì phép cộng deadline đã tràn sang miền âm — kết luận timeout sai. Trong khi đó `before - started` = 5, phép so sánh theo **hiệu** đúng là false.

Khi trôi 25 ns, `after - started` = 25 dù raw tick đã wrap. Đó là lý do chọn công thức **`now - started >= timeoutNanos`** cho kiểm tra elapsed/timeout.

Lưu ý khi timeout = 0, điều kiện thường có nghĩa đã hết hạn ngay; với timeout âm, ví dụ chủ động báo lỗi thay vì cố giải thích một yêu cầu không hợp lệ. Các API thư viện khác có thể định nghĩa riêng về timeout bằng 0/âm — đọc hợp đồng của từng API.

## 12. Tránh vòng lặp busy-wait khi chờ timeout

Một ví dụ không nên dùng trong hệ thống thực:

```java
long started = System.nanoTime();
long timeoutNanos = TimeUnit.MILLISECONDS.toNanos(500);

while (System.nanoTime() - started < timeoutNanos) {
    // Busy spin: chiếm CPU mà không làm việc.
}
```

Công thức đo **không sai**, nhưng thiết kế chờ **có thể sai**:
- Vòng lặp gọi nanoTime liên tục, tiêu tốn CPU.
- Không bảo đảm thức dậy hay dừng chính xác từng nanosecond.
- Có thể tranh tài nguyên với thread khác.
- Nếu timeout được dùng để chờ I/O/lock/future, thư viện thường có primitive chờ tốt hơn.

Ưu tiên API timeout sẵn có, ví dụ:

```java
Future<String> future = executor.submit(task);
try {
    String result = future.get(250, TimeUnit.MILLISECONDS);
    // Dùng result.
} catch (TimeoutException ex) {
    future.cancel(true); // Chỉ gửi yêu cầu hủy/interruption.
}
```

Đây là đoạn minh họa **trong phương thức**, giả định `executor`, `task` đã tồn tại và đã import `java.util.concurrent.*`; còn phải xử lý `InterruptedException` và `ExecutionException` theo hợp đồng của ứng dụng. `cancel(true)` không bảo đảm task lập tức dừng, vì task cần hợp tác với interruption.

Cũng có `Thread.sleep`, `LockSupport.parkNanos`, `Condition.awaitNanos` và các lời gọi blocking có timeout tùy use case. **Đặt timeout không có nghĩa scheduler bảo đảm thức dậy đúng thời điểm tuyệt đối**; độ trễ phát hiện timeout chịu ảnh hưởng tải hệ thống và cách thư viện triển khai.

## 13. Vì sao không dùng chênh `System.currentTimeMillis()`?

`System.currentTimeMillis()` trả **epoch milliseconds** liên quan đến wall-clock UTC. Hai lần đọc có thể thuận tiện để in timestamp, nhưng khi đồng hồ hệ thống được điều chỉnh tiến/lùi, chênh lệch wall clock không nhất thiết phản ánh chính xác elapsed time thực.

Ví dụ giả định:
- Trước tác vụ, clock tường là mốc `T`.
- Trong lúc tác vụ chạy 80 ms, hệ thống bị chỉnh lùi 120.000 ms.
- Hiệu hai wall timestamps có thể bằng **-120.000 ms** xấp xỉ, dù tác vụ không chạy ngược thời gian.
- Nguồn elapsed tick độc lập với thay đổi wall-clock vẫn có thể cho kết quả gần **80 ms**.

**Mô phỏng này cố tình đơn giản hóa** thành hai nguồn thời gian giả, không nói mọi JDK/hệ điều hành đều chỉnh giờ theo cách giống hệt. Nó minh họa vì sao không chọn wall clock cho elapsed time.

`Instant.now()` và `Clock.systemUTC()` cũng phục vụ lịch/timestamp; chúng không bảo đảm wall-clock sẽ đơn điệu như một ticker elapsed. Ngược lại, `nanoTime()` không cho biết giờ UTC của một sự kiện. Với logging có thể ghi **cả timestamp UTC để định vị sự kiện và duration monotonic để đo độ trễ**, không dùng một giá trị thay thế giá trị kia.

## 14. Chương trình đầy đủ: mô phỏng wall-clock bị chỉnh lùi

Tạo `WallClockJumpDemo.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public class WallClockJumpDemo {
    public static void main(String[] args) {
        AtomicLong wallMillis =
                new AtomicLong(1_700_000_000_000L);
        AtomicLong tickNanos =
                new AtomicLong(500_000_000_000L);

        long startWall = wallMillis.get();
        long startTick = tickNanos.get();

        // Mô phỏng thay đổi 2 phút của đồng hồ tường.
        wallMillis.addAndGet(-120_000L);

        // Ticker elapsed vẫn tiến 80 milliseconds.
        tickNanos.addAndGet(80_000_000L);

        System.out.println("simulated wall delta ms = " +
                (wallMillis.get() - startWall));
        System.out.println("simulated elapsed ms = " +
                TimeUnit.NANOSECONDS.toMillis(
                        tickNanos.get() - startTick));
        System.out.println("same origin needed = true");
    }
}
```

```bash
javac -encoding UTF-8 WallClockJumpDemo.java
java WallClockJumpDemo
```

```text
simulated wall delta ms = -120000
simulated elapsed ms = 80
same origin needed = true
```

Cả hai nguồn thời gian đều là **AtomicLong giả lập**, không truy cập clock thực. Mục đích là test chính sách đo, không phải mô tả việc một hệ điều hành thật xử lý NTP thế nào.

Điểm đáng lưu ý: hiệu hai raw tick có nghĩa khi chúng được đọc từ **cùng một ticker có chung origin**. Không so tick của JVM này với tick của JVM khác dù chúng chạy trên cùng máy. Với phân tích request xuyên nhiều service, cần trace/span timing của từng service và giao thức đồng bộ hóa thích hợp.

## 15. Ghi nhận duration ngay cả khi tác vụ thất bại

Nếu đo một tác vụ có thể ném exception, đoạn ghi elapsed **sau** lời gọi sẽ không được chạy khi exception xảy ra:

```java
long started = System.nanoTime();
sendRequest();
long elapsed = System.nanoTime() - started;
// Không chạy nếu sendRequest() ném exception.
```

Mẫu thường dùng:

```java
long started = System.nanoTime();
try {
    sendRequest();
} finally {
    long elapsed = System.nanoTime() - started;
    metrics.record(elapsed);
}
```

Đây là đoạn minh họa trong phương thức với `sendRequest()` và `metrics` do ứng dụng cung cấp. `finally` được thực thi khi khối try rời đi bình thường hoặc do exception (trừ tình huống JVM/process dừng đột ngột); giúp thu được latency của các request thất bại, vốn cũng có giá trị theo dõi.

**Cần chú ý:** nếu `metrics.record(...)` tự ném exception, nó có thể **che exception gốc** của `sendRequest()`. Trong thực tế cần làm metrics observer đủ tin cậy, hoặc bắt/xử lý lỗi ghi metrics theo chính sách, không để instrumentation làm thay đổi kết quả chính. Một `finally` cũng không bảo đảm thống kê được tác vụ nếu tiến trình bị kill hoặc có lỗi máy.

### Đo một operation hay toàn bộ pipeline?

- Đo transaction cấp cao: bao từ nhận request tới hoàn tất response (end-to-end).
- Đo từng bước: gọi database, serialize, HTTP request, xử lý business.
- Đo tác vụ thất bại: dùng finally để ghi duration và status riêng.
- Đo asynchronous: bắt đầu trước việc cần tính, kết thúc ở **completion thật**, không ở thời điểm chỉ gửi/lên lịch task.

Các tầng có thể chồng lên nhau; **đừng cộng thời lượng các span chồng lấn rồi tự kết luận đó là latency end-to-end**.

## 16. Chương trình đầy đủ: try/finally và exception vẫn được giữ

Tạo `FinallyTimingDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.LongConsumer;
import java.util.function.Supplier;

public class FinallyTimingDemo {
    static <T> T measured(
            Supplier<T> work, LongConsumer report) {

        long started = System.nanoTime();
        try {
            return work.get();
        } finally {
            long elapsed = System.nanoTime() - started;
            report.accept(elapsed);
        }
    }

    public static void main(String[] args) {
        AtomicInteger reports = new AtomicInteger();

        System.out.println("success = " +
                measured(
                        () -> "done",
                        nanos -> reports.incrementAndGet()));

        try {
            measured(
                    () -> {
                        throw new IllegalStateException("boom");
                    },
                    nanos -> reports.incrementAndGet());
        } catch (IllegalStateException ex) {
            System.out.println("failure = " +
                    ex.getClass().getSimpleName());
        }

        System.out.println("reported intervals = " +
                reports.get());
    }
}
```

```bash
javac -encoding UTF-8 FinallyTimingDemo.java
java FinallyTimingDemo
```

```text
success = done
failure = IllegalStateException
reported intervals = 2
```

`report.accept(elapsed)` được gọi **cả khi thành công và khi work ném exception**, nên bộ đếm là 2. Duration thực tế không in ra vì nó là biến ngẫu nhiên theo runtime. Nếu thực sự gửi nó tới một metrics backend, hãy bảo đảm callback báo cáo không phá luồng xử lý hoặc che lỗi gốc.

Lớp minh họa dùng generic `Supplier<T>` và `LongConsumer` của Java 8; có thể mở rộng bằng `Runnable`, checked exception hoặc các cơ chế đo tích hợp tùy nhu cầu, nhưng cần giữ semantics try/finally và phạm vi đo rõ ràng.

## 17. Đo CPU time khác elapsed time

Giả sử một thread:
- Tính toán 20 ms trên CPU.
- Chờ kết nối database 150 ms.
- Bị scheduler tạm dừng 30 ms.

Theo mô hình đơn giản, **elapsed latency có thể gần 200 ms**, còn **CPU time của thread** có thể gần 20 ms. `System.nanoTime()` đo **thời gian trôi qua**, không biết mã đang chạy CPU hay chờ.

Nếu mục tiêu là CPU sử dụng riêng cho thread, có thể nghiên cứu API `java.lang.management.ThreadMXBean` (ví dụ `getCurrentThreadCpuTime()`), **kiểm tra `isCurrentThreadCpuTimeSupported()`, trạng thái enable và hành vi implementation trước khi dùng**. Nó có hợp đồng và độ phủ khác `System.nanoTime()`; không nên coi là một cách “đo elapsed nhanh hơn”.

| Metric | Bản chất | Điều nên đo |
| --- | --- | --- |
| Wall/elapsed latency | Thời gian từ bắt đầu đến kết thúc, bao gồm chờ | `System.nanoTime()` |
| Thread CPU time | CPU time được quy cho một thread khi được hỗ trợ | `ThreadMXBean` |
| Throughput | Số thao tác hoàn tất trên một đơn vị thời gian | Đếm completions + khoảng đo rõ |
| Deadline miss | Có quá hạn không | Elapsed tick so với timeout |
| Timestamp | Sự kiện xảy ra lúc nào UTC | `Instant.now(clock)` |
| Allocation/GC/lock wait | Chi phí tài nguyên cụ thể | Profiler/JFR/metrics tương ứng |

**Không kết luận thuật toán tiêu tốn CPU chỉ vì p99 latency tăng**. Latency có thể tăng do I/O, queue, lock contention, GC, giới hạn kết nối, vận hành bên ngoài hoặc tải nền.

## 18. Tổng hợp nhiều mẫu đo: min/median/mean không phải cả bức tranh

Một lần chạy chỉ là một quan sát. Để mô tả hành vi ứng dụng, thu nhiều mẫu dưới điều kiện test rõ ràng:
- **min**: độ trễ thấp nhất quan sát được.
- **median / p50**: một nửa số mẫu không cao hơn nó, một nửa không thấp hơn nó theo cách xác định percentile.
- **mean**: trung bình cộng, có thể bị outlier kéo lệch.
- **p95, p99**: nhìn phần đuôi phân phối latency, thường hữu ích cho trải nghiệm người dùng.
- **max**: cao nhất trong tập đo, có thể bị một pause hoặc sự kiện nền chi phối.

Đừng so hai thay đổi code chỉ bằng **min của vài lần chạy** rồi tuyên bố cải thiện có ý nghĩa. JIT warmup, GC, OS scheduler, nền tải và phân phối input có thể thay đổi kết quả; nên có số lượng mẫu đủ, baseline, độ biến thiên, môi trường và chế độ chạy rõ ràng.

Khi đo rất nhiều request, tránh giữ vô hạn tất cả mẫu trong RAM. Có thể dùng histograms/metrics library để tính percentiles với chiến lược bộ nhớ phù hợp. Ví dụ dưới dùng một mảng nhỏ cố định để minh họa toán học của các thống kê, **không phải benchmark thực tế**.

## 19. Chương trình đầy đủ: số liệu mẫu mô phỏng và thống kê

Tạo `TimingStatisticsDemo.java`:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class TimingStatisticsDemo {
    public static void main(String[] args) {
        // Các duration giả lập, không phải thời gian đo máy.
        long[] durationsNs = {
                5_000_000L,
                3_000_000L,
                11_000_000L,
                4_000_000L,
                7_000_000L
        };

        Arrays.sort(durationsNs);

        long sum = 0;
        for (long value : durationsNs) {
            sum += value;
        }

        System.out.println("samples millis = " +
                Arrays.toString(
                        Arrays.stream(durationsNs)
                                .map(value ->
                                        TimeUnit.NANOSECONDS
                                                .toMillis(value))
                                .toArray()));

        System.out.println("min ms = " +
                TimeUnit.NANOSECONDS
                        .toMillis(durationsNs[0]));
        System.out.println("median ms = " +
                TimeUnit.NANOSECONDS
                        .toMillis(
                                durationsNs[durationsNs.length / 2]));
        System.out.println("max ms = " +
                TimeUnit.NANOSECONDS
                        .toMillis(
                                durationsNs[durationsNs.length - 1]));

        System.out.printf(Locale.ROOT,
                "mean ms = %.1f%n",
                (sum / (double) durationsNs.length)
                        / 1_000_000.0);
    }
}
```

```bash
javac -encoding UTF-8 TimingStatisticsDemo.java
java TimingStatisticsDemo
```

```text
samples millis = [3, 4, 5, 7, 11]
min ms = 3
median ms = 5
max ms = 11
mean ms = 6.0
```

Các số là **dữ liệu giả lập**, vì vậy kết quả cố định. Đoạn code minh họa cách đổi đơn vị bằng `TimeUnit` và tính mean bằng `double` để không mất phần lẻ. Với mảng có số phần tử chẵn, cách tính median cần lấy trung bình hai giá trị giữa theo định nghĩa bạn chọn; với nhiều mẫu nên xử lý tổng có thể overflow và chọn thư viện metrics phù hợp.

**Một thống kê mô phỏng không chứng minh hiệu năng thật.** Trong production cần đo với workload và phân phối input đại diện, đồng thời theo dõi p95/p99, error rate, throughput và mức sử dụng tài nguyên khi cần.

## 20. Microbenchmark trên JVM: khi nào phải dùng JMH?

`System.nanoTime()` đủ cho đo latency thực tế, log và đơn vị test đơn giản. Tuy nhiên, đối với việc so sánh **hai thuật toán/method rất ngắn trên JVM**, đo thủ công một lần trong `main` có thể cho kết quả sai do:
- **JIT compilation / warm-up:** lần đầu chạy bao gồm interpreter, nạp lớp hoặc biên dịch tối ưu.
- **Dead-code elimination:** JIT có thể loại bỏ phần tính nếu kết quả không được sử dụng.
- **Constant folding:** các phép toán với dữ liệu hằng có thể được tính trước.
- **Inlining và escape analysis:** runtime biến đổi cấu trúc và chi phí code.
- **Clock read overhead:** một đoạn tính vài nanosecond có thể bị chi phí đo che lấp.
- **GC, CPU scheduling và tần số CPU:** tạo nhiễu không phản ánh khác biệt thật.
- **Workload không đại diện:** chạy vài giá trị nhỏ khác xa dữ liệu production.
- **Compiler optimization of loops:** đo nhiều vòng không đồng nghĩa thời gian/iteration đúng nếu mã bị optimize theo cách không mong đợi.

**JMH (Java Microbenchmark Harness)** là công cụ hiện hành của dự án OpenJDK dành cho microbenchmark JVM. Nó hỗ trợ warmup, measurement iterations, forked JVM, cách tiêu thụ kết quả, tham số benchmark và nhiều mode đo như throughput, average time, sample time. Dùng JMH khi muốn đưa ra kết luận đáng tin về **hiệu năng code ngắn**, thay vì tự viết vòng lặp `for` với một đồng hồ và chia cho N.

### Mẫu JMH minh họa (cần dependency, không phải Java thuần độc lập)

```java
import org.openjdk.jmh.annotations.*;
import java.util.concurrent.TimeUnit;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
public class SampleBenchmark {
    private int input = 12_345;

    @Benchmark
    public long calculate() {
        long sum = 0;
        for (int i = 1; i <= input; i++) {
            sum += i;
        }
        return sum; // JMH xử lý kết quả để hạn chế DCE.
    }
}
```

Mã này **chỉ là snippet JMH**, không phải tệp chạy với mỗi `javac` vì annotation nằm trong thư viện JMH. Để xây benchmark thực, dùng cấu hình project theo tài liệu OpenJDK JMH và dependency phù hợp; không chỉ thêm `jmh-core` rồi chạy class thường. Khi muốn so sánh, cần thử nhiều fork, warmup và các tham số đại diện.

Không nên ghi một con số “JMH cho thấy X ns” nếu chưa thực sự benchmark trên môi trường cụ thể. Mục tiêu ở đây là hiểu **khi nào `System.nanoTime()` là đủ cho đo elapsed và khi nào JMH cần thiết cho so sánh microbenchmark**.

## 21. Đo tác vụ bất đồng bộ: start và end phải bao đúng completion

Xem trường hợp:

```java
long started = System.nanoTime();
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(this::fetchValue);
long elapsed = System.nanoTime() - started;
```

Đây là **đoạn minh họa trong phương thức** có method `fetchValue()` của ứng dụng và import `CompletableFuture`. `elapsed` trên chỉ đo thời gian **khởi tạo/lên lịch công việc bất đồng bộ**, không đo thời gian `fetchValue` thực sự hoàn tất.

Nếu yêu cầu là **latency end-to-end từ lúc submit tới lúc result sẵn sàng**, phải đo tới điểm completion:

```java
long started = System.nanoTime();
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(this::fetchValue);

String result = future.join();
long elapsed = System.nanoTime() - started;
```

Đây là minh họa khi **có chủ đích chờ bằng `join()`** (nó có thể ném `CompletionException`) và không phải cách bắt buộc cho hệ thống muốn non-blocking. Trong pipeline không blocking, có thể capture start và ghi metric trong `whenComplete(...)`:

```java
long started = System.nanoTime();
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(this::fetchValue);

future.whenComplete((value, error) -> {
    long elapsed = System.nanoTime() - started;
    // Ghi elapsed và trạng thái error riêng.
});
```

Đoạn này minh họa cách lấy elapsed tại callback completion, nhưng callback có thể được thực thi ở thread khác và trễ so với thời điểm hoàn thành thực; nếu cần độ chính xác cao hoặc tách queue time, phải thiết kế instrumentation tại các điểm phù hợp. `System.nanoTime()` dùng chung origin trong một JVM, nhưng đồng bộ hóa, scheduling và thread hops ảnh hưởng phạm vi được đo.

Đối với request phân tán qua nhiều JVM, **đừng dùng hai raw nano ticks từ hai process để trừ**. Nên đo mỗi span bằng ticker của chính process đó rồi tổng hợp trace/metrics theo protocol quan sát hệ thống.

## 22. Cách đo ảnh hưởng đến hành vi chương trình

Instrumentation **cũng tiêu tốn tài nguyên**. Những lỗi phổ biến:
- Gọi `System.out.println` trong vòng lặp rất nóng để ghi mỗi iteration, khiến I/O console chiếm phần lớn thời gian.
- Chèn nhiều lần `System.nanoTime()` vào mỗi phép toán cực ngắn, rồi báo “đo được vài ns” không tính overhead của phép đo.
- Tạo đối tượng/chuỗi/JSON trong đoạn muốn benchmark, khiến so sánh hai thuật toán bị chi phối bởi allocation.
- Để formatter hoặc remote metrics exporter chạy đồng bộ trong hot path, tạo latency mới.
- Bắt exception của tác vụ rồi đổi kết quả chỉ để phục vụ thống kê.
- Không tách **thời gian setup** và **thời gian xử lý business**.
- Tự tối ưu theo một giá trị latency không đại diện tải thật.

Một giải pháp thực tế là ghi raw elapsed nanos vào cấu trúc metrics nhẹ, rồi xử lý aggregation/format ở tầng quan sát riêng. Chọn sampling khi tần suất rất cao, và đo overhead instrumentation nếu cần.

Đừng đặt hiệu năng báo cáo cao hơn tính đúng đắn: phép đo sai ranh giới, loại bỏ exception hoặc thay đổi trạng thái chương trình có thể dẫn đến metric vô dụng dù công cụ rất “nhanh”.

## 23. Phân biệt Duration, Clock, Instant và nano tick

Các API này đều liên quan đến thời gian nhưng không thể hoán đổi:

| API | Đại diện | Dùng tốt cho |
| --- | --- | --- |
| `System.nanoTime()` | Một lần đọc ticker elapsed, origin tùy ý | `end - start` trong cùng JVM |
| `Duration.ofNanos(elapsed)` | **Lượng thời gian**, không có nguồn đồng hồ | Lưu/format/so sánh duration |
| `Instant.now()` | Moment UTC hiện tại từ wall-clock source | Timestamp event/log |
| `Clock.fixed(Instant, ZoneId)` | Nguồn thời gian tường giả lập | Test ngày giờ, không phải fake nanoTime |
| `LocalDateTime.now()` | Ngày giờ địa phương chưa có zone/offset trong giá trị | Hiển thị theo policy cục bộ, không làm elapsed ticker |
| `System.currentTimeMillis()` | Epoch milliseconds của wall-clock | Giao tiếp timestamp kiểu `long` nếu API cần |
| `ThreadMXBean` | Thông tin CPU/management theo thread | Phân tích CPU usage khi được hỗ trợ |

Dùng `Duration` để biểu diễn kết quả đo là hợp lý:

```java
long start = System.nanoTime();
// ... công việc ...
long elapsedNanos = System.nanoTime() - start;
Duration took = Duration.ofNanos(elapsedNanos);
```

Nhưng không suy ra nguồn đo `Duration` là đơn điệu: **Duration chỉ là một giá trị khoảng thời gian**. `Duration.between(a, b)` mang semantics của hai temporal được truyền, không tự quyết định loại clock nào sinh `a`, `b`.

Cần quan tâm precision vs accuracy: `Duration` có thể biểu diễn nanosecond, nhưng số nanosecond đó không tự có ý nghĩa là đo chính xác đến từng nanosecond trong thế giới thật.

## 24. Các lỗi thường gặp và sửa như thế nào?

| Sai lầm | Vấn đề | Cách đúng |
| --- | --- | --- |
| Lưu `System.nanoTime()` làm timestamp UTC | Origin tùy ý, có thể âm | `Instant.now()` cho timestamp |
| Trừ nanoTime của hai JVM | Hai origin không được bảo đảm trùng | Đo span trong từng JVM |
| `System.nanoTime() >= start + timeout` | Tràn `long` và raw comparison không đúng | `System.nanoTime() - start >= timeoutNanos` |
| Lấy nano tick rồi chia cho `1_000_000` để ra epoch ms | Không có quan hệ với epoch | Dùng `System.currentTimeMillis()` nếu cần epoch |
| `System.currentTimeMillis()` để benchmark độ trễ | Đồng hồ có thể được chỉnh và resolution thấp | Dùng `nanoTime` lấy hiệu |
| Cho rằng `nanoTime` chính xác vật lý 1 ns | Unit nanosecond ≠ clock resolution | Đánh giá nguồn đo và distribution |
| Chuyển `nanos / 1_000_000L` rồi nghĩ giữ phần lẻ | Chia nguyên truncation | `nanos / 1_000_000.0` cho hiển thị |
| Gọi `TimeUnit.MILLISECONDS.toNanos` sau khi tự nhân trước | Có thể tràn trước khi convert | Chuyển trực tiếp bằng TimeUnit |
| Dùng `Duration.between(Instant.now(), Instant.now())` làm monotonic timer | Hai Instant từ wall clock | `nanoTime` lấy hiệu, rồi `Duration.ofNanos` |
| Đặt start trước setup lớn nhưng muốn đo riêng operation | Metric gồm setup | Đặt boundary theo mục tiêu |
| Đặt end ngay sau `supplyAsync` | Chỉ đo scheduling | Đo tại completion |
| Đo `Thread.sleep(10)` rồi đòi đúng 10 ms | Scheduler không bảo đảm chính xác tuyệt đối | Kiểm thử có tolerance/giả lập |
| Busy-spin gọi nanoTime liên tục để chờ | Tốn CPU, không bảo đảm thức đúng hạn | Future/lock/condition timeout |
| Dùng nanoTime để đo “CPU time” | Chứa thời gian chờ, preemption, I/O | CPU timer/profiler nếu phù hợp |
| Chỉ chạy một vòng để so microbenchmark | JIT/GC/scheduler chi phối | JMH với warmup/fork |
| Không sử dụng kết quả tính benchmark | JIT có thể loại bỏ phép tính | JMH xử lý tiêu thụ kết quả |
| Ghi latency sau try nhưng không có finally | Exception khiến bỏ mất metric | Ghi trong finally/callback |
| Metrics callback ném lỗi | Có thể che lỗi nghiệp vụ | Tách/kiểm soát lỗi instrumentation |
| Tổng hợp các span chồng lấn bằng phép cộng | Đếm trùng elapsed | Dùng trace và phạm vi đo rõ |
| Xem duration là timestamp | Lẫn lượng thời gian với mốc UTC | Phân biệt Duration / Instant |

Một hệ thống đo tốt thường theo dõi **cả duration, thời điểm, status và kích thước workload**, vì chỉ nhìn một con số không đủ để kết luận điều gì làm hệ thống chậm.

## 25. Quy trình đo thời gian thực thi thực tế

Khi thêm instrumentation cho một service Java:

1. **Chọn câu hỏi**: độ trễ end-to-end, thời gian riêng DB, thời gian chờ queue, hay CPU time?
2. **Chọn điểm bắt đầu/kết thúc** bao đúng phần việc. Với async, đo tới completion thật.
3. **Dùng `System.nanoTime()` lấy hiệu**, không chuyển raw tick thành UTC.
4. **Dùng đơn vị nhất quán**: nội bộ giữ nanos, ở metric ghi unit hoặc đổi bằng `TimeUnit`/`Duration`.
5. **Xử lý cả thành công và thất bại**; không để việc ghi metric thay đổi exception của tác vụ.
6. **Chọn API timeout có sẵn** thay vì tự busy-spin.
7. **Thu nhiều mẫu** với thông tin workload và trạng thái thành công/thất bại, xem median/p95/p99 khi đủ dữ liệu.
8. **Phân biệt latency với CPU time**, không suy một giá trị ra tất cả.
9. **Khi so microbenchmark**, dùng JMH và môi trường kiểm thử kiểm soát được.
10. **Test các tính toán thời gian bằng ticker giả** để tránh flakiness của `Thread.sleep` và clock thật.
11. **Không so raw nano ticks của các process khác nhau**, kể cả chạy cùng máy.
12. **Ghi rõ giới hạn**: nguồn time độ phân giải hữu hạn, VM/OS scheduling, GC, clock configuration, accuracy và phiên bản runtime.

Nếu mục tiêu là giám sát request production, không nhất thiết phải tự triển khai một thư viện Stopwatch lớn; có thể dùng hệ thống metrics/tracing đã được dự án lựa chọn, miễn nó sử dụng ngữ nghĩa elapsed time đúng. **Điều quan trọng là lựa chọn clock, đơn vị, ranh giới đo và thống kê phù hợp**.

## 26. Bài tập tự kiểm tra

**Câu 1.** Vì sao `System.nanoTime()` không nên được lưu vào cột `created_at`?  
**Đáp án:** Origin của nó tùy ý và có thể âm; không liên quan UTC. Dùng `Instant`/epoch timestamp theo contract dữ liệu.

**Câu 2.** Công thức cơ bản để đo duration?  
**Đáp án:** Lấy `start = System.nanoTime()` rồi `elapsed = System.nanoTime() - start` trong cùng JVM.

**Câu 3.** Dùng `TimeUnit.NANOSECONDS.toMillis(123456789L)` trả bao nhiêu?  
**Đáp án:** `123`, vì conversion integer cắt phần nhỏ hơn 1 ms. Muốn hiển thị thập phân, chia `123456789 / 1_000_000.0 = 123.456789` ms.

**Câu 4.** `nanoTime()` có thể trả giá trị âm không?  
**Đáp án:** Có. Origin tùy ý, raw tick âm không có nghĩa JVM chạy ngược thời gian.

**Câu 5.** Vì sao không kiểm tra `now >= start + timeout`?  
**Đáp án:** Cộng/so raw `long` có thể sai qua overflow. Kiểm tra `now - start >= timeoutNanos` trong giới hạn duration đại diện được.

**Câu 6.** Khi người dùng hỏi “request này đến lúc 10:30 UTC chưa?”, dùng nanoTime hay Instant?  
**Đáp án:** `Instant.now()` hoặc wall clock API tương đương vì cần moment dân sự, không phải elapsed duration.

**Câu 7.** Có thể lấy nanoTime trước trên JVM A và sau trên JVM B rồi tính chênh lệch không?  
**Đáp án:** Không. Origin không được bảo đảm chung giữa các JVM.

**Câu 8.** `Clock.fixed` có làm `System.nanoTime()` dừng theo không?  
**Đáp án:** Không. `Clock.fixed` dùng cho `java.time` wall clock. Muốn test elapsed ticker cần inject `LongSupplier`/Ticker riêng.

**Câu 9.** Vì sao tác vụ ngủ chờ I/O lâu có thể có elapsed time lớn nhưng CPU time nhỏ?  
**Đáp án:** Elapsed bao gồm thời gian chờ/scheduling; CPU time chỉ tính CPU đã sử dụng theo cơ chế đo tương ứng.

**Câu 10.** `System.nanoTime()` có bảo đảm mỗi lần gọi khác nhau đúng 1 ns không?  
**Đáp án:** Không. API có nanosecond unit nhưng nguồn có thể có resolution thô hơn.

**Câu 11.** Đặt end ngay sau `CompletableFuture.supplyAsync` đo điều gì?  
**Đáp án:** Chủ yếu đo chi phí scheduling/submit, không đo toàn bộ việc async. Đo tới completion hoặc callback.

**Câu 12.** Một exception giữa đoạn đo nên làm gì với metric?  
**Đáp án:** Có thể ghi trong `finally`/completion callback để vẫn có latency của lần thất bại, không để observer che lỗi gốc.

**Câu 13.** Có nên tự so hai thuật toán siêu ngắn bằng một vòng lặp `for` và một lần nanoTime?  
**Đáp án:** Không nên coi là benchmark đáng tin; JIT, DCE, GC và nhiều yếu tố ảnh hưởng. Sử dụng JMH cho microbenchmark JVM.

**Câu 14.** “Đã chạy 24 giờ” và “hiện tại là ngày hôm sau” có cùng nghĩa không?  
**Đáp án:** Không. Elapsed time tính duration; ngày lịch phụ thuộc `ZoneId` và có thể bị ảnh hưởng DST. Chọn API theo đúng câu hỏi.

**Câu 15.** Một service ở hai máy khác nhau có thể dùng `nanoTime` để tính latency tổng không?  
**Đáp án:** Không lấy hiệu trực tiếp raw ticks liên tiến trình. Đo từng span tại mỗi process rồi dùng tracing/metrics để phân tích end-to-end.

## 27. Ghi nhớ

- **`System.nanoTime()`** là nguồn thời gian độ phân giải cao dùng để đo **elapsed time** trong JVM; giá trị thô có origin tùy ý và không phải timestamp.
- **Đo bằng hiệu:** `long elapsed = System.nanoTime() - start;`. Không suy ra ý nghĩa của raw tick hoặc so raw tick với epoch time.
- **Timeout nên so hiệu**: `System.nanoTime() - start >= timeoutNanos`, tránh raw deadline comparison và kiểm soát đơn vị.
- **Nanosecond precision không bảo đảm 1 ns resolution/accuracy.** Kết quả chịu ảnh hưởng scheduling, JIT, GC, clock source và workload.
- `Duration` **biểu diễn một lượng thời gian**, `Instant`/`Clock` dùng cho thời điểm dân sự, `ThreadMXBean` dùng phân tích CPU khi phù hợp.
- Dùng `try/finally` hoặc callback completion để không bỏ metric khi tác vụ lỗi; đo tới **completion thực** khi async.
- Test công thức bằng **ticker có thể điều khiển**, không dùng sleep chính xác tuyệt đối; với **microbenchmark** dùng JMH.
- Ưu tiên các API hiện hành và làm rõ **đơn vị, ranh giới đo, độ tin cậy và ý nghĩa thống kê**.

### Tài liệu chính thức và dự án được duy trì

- [Java SE 26 — `System.nanoTime()` và `System.currentTimeMillis()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html)
- [Java SE 26 — `TimeUnit` và các phép chuyển đơn vị, timeout](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/TimeUnit.html)
- [Java SE 26 — `Duration`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html)
- [Java SE 26 — `Instant`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
- [Java SE 26 — `Clock`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html)
- [Java SE 26 — `ThreadMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [OpenJDK JMH — hướng dẫn và mã nguồn](https://github.com/openjdk/jmh) — benchmark JVM có warmup, forks và các sample về dead-code elimination.
