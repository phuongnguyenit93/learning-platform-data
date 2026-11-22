# TimeUnit: chuyển đơn vị, độ chính xác và ngân sách thời gian qua nhiều bước

## 1. TimeUnit giải quyết vấn đề gì trong Java Concurrency?

Các API concurrency thường cần biểu diễn **thời gian chờ**, **timeout**, **độ trễ lên lịch** và **thời hạn kết thúc**. Những con số như `1000` không đủ rõ nghĩa: đó là mili giây, micro giây hay nano giây?

Java cung cấp enum `java.util.concurrent.TimeUnit` để truyền một giá trị `long` **cùng đơn vị thời gian**. Ví dụ:

```java
future.get(2, TimeUnit.SECONDS);
latch.await(500, TimeUnit.MILLISECONDS);
lock.tryLock(250, TimeUnit.MICROSECONDS);
executor.awaitTermination(5, TimeUnit.SECONDS);
scheduler.schedule(task, 100, TimeUnit.MILLISECONDS);
```

Các đoạn trên là **minh họa API**; `future`, `latch`, `lock`, `executor`, `scheduler` và `task` được khai báo phù hợp trong ứng dụng. Đọc `2, SECONDS` rõ hơn một số `2000` không được đặt tên đơn vị.

Nhưng chỉ dùng TimeUnit chưa đủ để viết code timeout đúng. Ba nhóm vấn đề phải phân biệt:

1. **Chuyển đơn vị:** `TimeUnit.convert`, `toNanos`, `toMillis` có thể **làm tròn về 0 khi chuyển sang đơn vị thô hơn**, hoặc **bão hòa** nếu kết quả vượt `long`.
2. **Độ chính xác thực tế:** khai báo timeout ở mức nano giây **không bảo đảm thread được đánh thức đúng nano giây đó**; JVM, hệ điều hành, scheduler và tải CPU ảnh hưởng thời điểm thực thi.
3. **Ngân sách thời gian qua nhiều bước:** nếu một workflow có tổng tối đa 1 giây, mỗi bước không được tự dùng lại **đầy đủ 1 giây**. Cần đo thời gian **đã trôi qua** bằng một đồng hồ phù hợp, rồi truyền **phần còn lại** cho bước sau.

Đây là kiến thức của **Future & Scheduling** trong **Java concurrency nói chung**, không phụ thuộc framework.

## 2. Các đơn vị được TimeUnit hỗ trợ

`TimeUnit` là một `enum` với các hằng:

| Hằng số | Viết tắt thường dùng | Quan hệ |
| --- | --- | --- |
| `NANOSECONDS` | ns | 1 nano giây |
| `MICROSECONDS` | µs | 1 µs = 1.000 ns |
| `MILLISECONDS` | ms | 1 ms = 1.000 µs |
| `SECONDS` | s | 1 s = 1.000 ms |
| `MINUTES` | min | 1 phút = 60 s |
| `HOURS` | h | 1 giờ = 60 phút |
| `DAYS` | d | 1 ngày = 24 giờ |

Các đơn vị `DAYS`, `HOURS`, `MINUTES` trong `TimeUnit` là **khoảng thời gian có độ dài cố định**, không tính lịch, múi giờ hay daylight saving time. Ví dụ `DAYS.toHours(1)` luôn là `24`, không phải “số giờ thực tế của một ngày địa phương có thể đổi giờ”.

Để biểu diễn **thời điểm lịch**, dùng `Instant`, `ZonedDateTime` hoặc kiểu `java.time` phù hợp. Để biểu diễn **khoảng chờ/timeout** trong concurrency, `TimeUnit` kết hợp đồng hồ đo thời gian trôi qua là lựa chọn quen thuộc.

## 3. Chuyển đơn vị với `convert` và `toX`

Có hai cách diễn đạt tương đương về mục tiêu:

```java
long millis = TimeUnit.MILLISECONDS.convert(3, TimeUnit.SECONDS);
long same = TimeUnit.SECONDS.toMillis(3);
```

Cả hai cho `3000`.

**Thứ tự tham số của `convert`:**

```java
targetUnit.convert(value, sourceUnit);
```

Điều này có nghĩa **đơn vị nhận lời gọi** là đơn vị đích. Ví dụ:

```java
long seconds = TimeUnit.SECONDS.convert(
        1500, TimeUnit.MILLISECONDS);
```

`seconds == 1`, chứ không phải `1.5`, vì kết quả là `long` nguyên.

Một số hàm tiện ích:

- `TimeUnit.SECONDS.toMillis(5)` → `5000`.
- `TimeUnit.MILLISECONDS.toNanos(2)` → `2_000_000`.
- `TimeUnit.MINUTES.toSeconds(3)` → `180`.
- `TimeUnit.NANOSECONDS.toMillis(999_999)` → `0`.
- `TimeUnit.SECONDS.convert(1_999, TimeUnit.MILLISECONDS)` → `1`.

**Không có đơn vị thập phân trong kết quả `long`.** Nếu cần giữ độ chính xác nano giây, nên giữ giá trị ở đơn vị đủ mịn cho tới lúc gọi API nhận timeout.

### Ví dụ 1: chuyển đơn vị, cắt phần dư và bão hòa

Tạo tệp `TimeUnitConversionDemo.java`:

```java
import java.util.concurrent.TimeUnit;

public class TimeUnitConversionDemo {
    public static void main(String[] args) {
        System.out.println("3s to ms="
                + TimeUnit.SECONDS.toMillis(3));
        System.out.println("1500ms to s="
                + TimeUnit.SECONDS.convert(
                        1500, TimeUnit.MILLISECONDS));
        System.out.println("999999ns to ms="
                + TimeUnit.NANOSECONDS.toMillis(999_999));
        System.out.println("-1500ms to s="
                + TimeUnit.SECONDS.convert(
                        -1500, TimeUnit.MILLISECONDS));
        System.out.println("23h to days="
                + TimeUnit.DAYS.convert(
                        23, TimeUnit.HOURS));
        System.out.println("huge days to nanos="
                + TimeUnit.DAYS.toNanos(Long.MAX_VALUE));
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac TimeUnitConversionDemo.java
java TimeUnitConversionDemo
```

Kết quả:

```text
3s to ms=3000
1500ms to s=1
999999ns to ms=0
-1500ms to s=-1
23h to days=0
huge days to nanos=9223372036854775807
```

Giải thích:

1. `3s` chuyển sang ms chính xác là `3000`.
2. `1500ms` chuyển sang giây nguyên thành `1`, **mất phần 500ms**.
3. `999_999ns` nhỏ hơn 1ms, chuyển sang mili giây thành `0`.
4. `-1500ms` chuyển sang giây nguyên thành `-1`: Java chia số nguyên theo hướng **về 0**, không phải luôn làm tròn xuống âm vô cực.
5. `23h` chưa đủ một ngày cố định 24 giờ, nên `toDays` là `0`.
6. `Long.MAX_VALUE` ngày chuyển sang nano giây vượt phạm vi `long`. `TimeUnit` trả giá trị **bão hòa (saturation)** ở `Long.MAX_VALUE`, không wrap thành số âm.

Không nên lấy kết quả `toMillis(...) == 0` và kết luận “không còn thời gian” nếu ban đầu vẫn còn hàng trăm nghìn nano giây. **Đơn vị quá thô** đã xóa mất phần dư trong phép đổi số nguyên.

## 4. Conversion truncation: trường hợp gây bug timeout

Giả sử một deadline chỉ còn `800_000 ns` = `0.8 ms`.

```java
long remainingNanos = 800_000;
long remainingMillis =
        TimeUnit.NANOSECONDS.toMillis(remainingNanos);
// remainingMillis == 0, dù thời gian còn lại dương.
```

Nếu code kiểm tra `if (remainingMillis <= 0)`, nó có thể từ chối một bước còn khả năng hoàn thành trong `0.8ms`. Nếu gọi API:

```java
future.get(remainingMillis, TimeUnit.MILLISECONDS);
```

thì `get(0, MILLISECONDS)` hoạt động như một phép kiểm tra kết quả ngay, thay vì đợi `0.8ms`.

**Cách giữ độ phân giải:** truyền đúng phần còn lại ở nanoseconds:

```java
long nanos = budget.remainingNanos();
if (nanos <= 0) {
    throw new TimeoutException("budget exhausted");
}
return future.get(nanos, TimeUnit.NANOSECONDS);
```

Đây là **đoạn minh họa** trong method có `budget`, `future`, `TimeoutException` và khai báo checked exceptions phù hợp. Dù truyền nano giây, độ chính xác **thức dậy thực tế** vẫn phụ thuộc scheduler; ưu điểm là không mất độ phân giải **do chính phép chuyển đơn vị**.

### Cẩn thận với negative timeout

Giá trị thời gian âm thường không có ý nghĩa “đợi âm một giây”. Nhiều API timeout hiểu khoảng chờ không dương là không chờ, nhưng hợp đồng mỗi API có thể khác. Không nên dựa vào các giá trị âm truyền vào `Future.get`, `Condition.await` hoặc `Lock.tryLock` như một cơ chế timeout chuẩn chung.

Hãy chuẩn hóa tại biên:

```java
long remaining = Math.max(0L, deadlineNanos - nowNanos);
```

Đây là mã minh họa; phép trừ thô còn phải xét overflow và điểm gốc của `System.nanoTime()`. Phần sau xây dựng cách tính dựa trên **elapsed time** an toàn cho các deadline thực tế.

## 5. Bão hòa số nguyên và giới hạn long

`TimeUnit` dùng `long` và trong những phép chuyển sang đơn vị nhỏ hơn, nó **bão hòa** về `Long.MAX_VALUE` hoặc `Long.MIN_VALUE` khi số học cần vượt giới hạn. Đây là hành vi hữu ích vì không chuyển một timeout khổng lồ thành giá trị âm vô nghĩa.

Ví dụ:

```java
long nanos = TimeUnit.DAYS.toNanos(Long.MAX_VALUE);
// nanos == Long.MAX_VALUE
```

Nhưng cần phân biệt với các phép số học khác:

```java
long nanos = hugeSeconds * 1_000_000_000L;
```

Dòng thứ hai **không tự bão hòa**; phép nhân `long` có thể overflow và wrap. Ưu tiên `TimeUnit.SECONDS.toNanos(hugeSeconds)` nếu mục đích chỉ là chuyển đơn vị.

### So sánh với java.time.Duration

`Duration` mô tả khoảng thời gian theo giây và nano giây với độ phân giải chi tiết. Nó thích hợp ở tầng API cấu hình, deadline, logging hoặc xử lý thời gian chung.

```java
Duration duration = Duration.ofMillis(1500);
long nanos = duration.toNanos();
long millis = duration.toMillis();
```

Đây là đoạn minh họa, cần import `java.time.Duration`. `nanos` là `1_500_000_000` và `millis` là `1500`.

Khác `TimeUnit` có quy tắc saturation ở các phép đổi liên quan, một số phép chuyển `Duration` như `toNanos()` có thể ném `ArithmeticException` nếu giá trị không biểu diễn được trong `long`. **Không giả định hai API có cùng hợp đồng overflow**.

Khi dùng `Duration` để nhập thời hạn người dùng, hãy xác nhận giá trị **không âm**, có nằm trong ngưỡng hệ thống cho phép không và phép đổi cần thiết có overflow hay không.

## 6. TimeUnit không phải đồng hồ

Một câu lệnh:

```java
TimeUnit.MILLISECONDS.sleep(10);
```

yêu cầu thread ngủ **ít nhất theo cơ chế chờ mà JVM/OS hỗ trợ**, không bảo đảm code tiếp tục chính xác ngay ở mốc `10ms`. Sau khi thời gian trôi qua, thread còn phụ thuộc thời điểm scheduler cho chạy lại.

Phân biệt hai khái niệm:

- **Độ phân giải biểu diễn (resolution):** số lượng nhỏ nhất mà kiểu/đơn vị mô tả được; `NANOSECONDS` biểu diễn tới 1ns.
- **Độ chính xác thời gian chạy (accuracy):** sự kiện thực tế xảy ra gần deadline tới đâu; phụ thuộc hệ điều hành, JVM, độ phân giải timer, tải máy, GC pause, contention, CPU scheduling và đặc điểm API.

Chọn `TimeUnit.NANOSECONDS` không có nghĩa thread sẽ thức dậy hay lịch sẽ chạy ở chính xác từng nano giây.

Đặc biệt, `Thread.sleep`, `TimeUnit.sleep` và một số wait có thể bị **interrupt**; các API có thể ném `InterruptedException`. Khi bị interrupt, phải xử lý tín hiệu hủy đúng cách thay vì catch rỗng rồi lặp vô hạn.

### Ba API tiện ích của TimeUnit

`TimeUnit` còn có:

```java
TimeUnit.MILLISECONDS.sleep(20);
TimeUnit.SECONDS.timedJoin(thread, 2);
TimeUnit.MILLISECONDS.timedWait(monitor, 200);
```

Đây là **các đoạn minh họa độc lập**. `thread` phải là `Thread` hợp lệ; với `timedWait`, caller phải đang giữ **monitor của chính `monitor`** giống khi gọi `monitor.wait(...)`, nếu không có thể nhận `IllegalMonitorStateException`. Không dùng `timedWait` thay cho một giao thức condition chuẩn. Điều kiện chờ phải được kiểm tra trong vòng `while` vì spurious wakeups và khả năng điều kiện thay đổi khi thread được đánh thức.

## 7. Đồng hồ đo elapsed time: `System.nanoTime()`

Khi cần tính **ngân sách còn lại**, không nên lấy hai lần `System.currentTimeMillis()` rồi trừ tùy tiện. Đồng hồ wall-clock có thể bị điều chỉnh do NTP, người dùng đổi giờ hoặc thay đổi hệ thống.

`System.nanoTime()` dành cho **đo khoảng thời gian trôi qua**. Giá trị của nó có một điểm gốc tùy ý; **không phải Unix timestamp**, không mang ngày giờ và có thể âm.

Mẫu:

```java
long startedAt = System.nanoTime();
// Thực hiện một bước.
long elapsed = System.nanoTime() - startedAt;
```

`elapsed` là số nano giây đo được từ điểm bắt đầu đến hiện tại. Với các khoảng đo hợp lý nhỏ hơn khoảng `2^63 ns` (xấp xỉ 292 năm), phép trừ này là mẫu Java thường dùng ngay cả khi biểu diễn `long` tràn theo vòng. Không nên dùng một số `nanoTime()` như thời điểm tuyệt đối để lưu database hoặc so sánh giữa các JVM.

### Khác biệt với Instant

- `Instant.now()`: thời điểm trên đồng hồ thực, phù hợp lưu timestamp/log khi sự kiện xảy ra.
- `System.nanoTime()`: đo duration/timeout trong cùng JVM, phù hợp tính elapsed budget.
- `TimeUnit`: **đơn vị** của một khoảng thời gian; không cung cấp một đồng hồ riêng.

Có thể log `Instant.now()` cho con người nhưng dùng `nanoTime()` để quyết định deadline của một retry loop. Không cộng số nanoTime vào epoch millis rồi cho rằng hai đồng hồ cùng hệ quy chiếu.

## 8. Ngân sách chung: không restart timeout cho từng bước

Giả sử một request có **tổng ngân sách 500ms**, gồm ba bước:

1. Chờ lock.
2. Chờ dữ liệu sẵn sàng.
3. Chờ kết quả `Future`.

**Sai:** mỗi bước gọi API với đủ `500ms`:

```java
lock.tryLock(500, TimeUnit.MILLISECONDS);
ready.await(500, TimeUnit.MILLISECONDS);
future.get(500, TimeUnit.MILLISECONDS);
```

Đây là **phản ví dụ về ngân sách**, chưa xét unlock, exceptions và trạng thái return của từng API. Mỗi bước có thể đợi gần `500ms`, khiến tổng latency gần **1500ms** cộng overhead. Càng nhiều bước, deadline end-to-end càng bị kéo dài.

**Đúng ý tưởng:** chỉ có **một start time và một budget**, sau mỗi bước tính lại **remaining time**:

```text
Budget tổng: 500ms
Start                   500ms còn
Bước 1 sử dụng 300ms    200ms còn
Bước 2 sử dụng 150ms     50ms còn
Bước 3 chỉ được dùng tối đa 50ms
Hết 500ms => không khởi tạo một lần chờ 500ms mới.
```

Không chia cố định mỗi bước 166ms nếu không có nhu cầu riêng: một bước hoàn thành nhanh thì bước sau có thể sử dụng phần chưa tiêu. Đây là **end-to-end deadline** chứ không phải timeout tĩnh cho từng phần.

## 9. Một TimeBudget dùng elapsed time và LongSupplier

Để test chính xác logic chia ngân sách mà không dựa vào scheduler, thiết kế một helper nhận **đồng hồ nano giây** qua `LongSupplier`. Trong production sử dụng `System::nanoTime`; trong test dùng đồng hồ giả có thể tiến lên theo ý muốn.

Tạo tệp `TimeBudgetDemo.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public class TimeBudgetDemo {
    static final class Budget {
        private final LongSupplier clock;
        private final long started;
        private final long allowedNanos;

        Budget(long timeout, TimeUnit unit, LongSupplier clock) {
            if (timeout < 0) {
                throw new IllegalArgumentException("negative timeout");
            }
            this.clock = clock;
            this.started = clock.getAsLong();
            this.allowedNanos = unit.toNanos(timeout);
        }

        long remainingNanos() {
            long elapsed = clock.getAsLong() - started;
            if (elapsed <= 0) {
                return allowedNanos;
            }
            return Math.max(0L, allowedNanos - elapsed);
        }

        long remainingMillis() {
            return TimeUnit.NANOSECONDS.toMillis(remainingNanos());
        }
    }

    public static void main(String[] args) {
        AtomicLong fakeNanos = new AtomicLong(0);
        Budget budget = new Budget(
                500, TimeUnit.MILLISECONDS, fakeNanos::get);

        System.out.println("at 0ms=" + budget.remainingMillis());

        fakeNanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(300));
        System.out.println("at 300ms=" + budget.remainingMillis());

        fakeNanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(150));
        System.out.println("at 450ms=" + budget.remainingMillis());

        fakeNanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(60));
        System.out.println("at 510ms=" + budget.remainingMillis());
    }
}
```

```bash
javac TimeBudgetDemo.java
java TimeBudgetDemo
```

Kết quả hoàn toàn xác định:

```text
at 0ms=500
at 300ms=200
at 450ms=50
at 510ms=0
```

Ví dụ **không ngủ** và không dựa vào hiệu năng máy. `AtomicLong` được dùng làm đồng hồ mô phỏng để minh họa chính xác phép tính.

**Đưa vào production:** tạo `new Budget(timeout, unit, System::nanoTime)` và gọi `remainingNanos()` ngay trước mỗi bước chờ. Cần lưu ý `LongSupplier` test phải tiến lên theo đúng đơn vị nano giây, và phép trừ `nanoTime` dựa trên giả định khoảng đo thực tế nhỏ hơn khoảng tràn `long` khổng lồ (khoảng 292 năm).

**Không dùng `remainingMillis()==0` làm điều kiện hết hạn:** nó có thể là `0` dù `remainingNanos() > 0` do truncation. Dùng nanos cho logic hết hạn, chỉ chuyển sang ms khi **hiển thị**.

## 10. Helper TimeBudget có xử lý overflow như thế nào?

Ở ví dụ, `unit.toNanos(timeout)` áp dụng saturation của `TimeUnit` khi số lượng quá lớn. `allowedNanos` có thể là `Long.MAX_VALUE` nếu yêu cầu timeout vượt khả năng biểu diễn nano giây. Với ngân sách hữu hạn thông thường, điều đó không ảnh hưởng.

Để dùng cho hệ thống thật, nên đặt **ngưỡng timeout hợp lý** (chẳng hạn vài giây/phút/giờ tùy nghiệp vụ), thay vì chấp nhận `Long.MAX_VALUE` nano giây và vô tình tạo một phép đợi gần như không giới hạn.

Phép tính:

```java
long elapsed = System.nanoTime() - started;
long remaining = Math.max(0L, allowedNanos - elapsed);
```

được ưa dùng hơn so sánh trực tiếp hai giá trị `deadline` tuyệt đối thiếu kiểm soát. Tuy vậy, nó vẫn có những giả định thời gian thông thường:

- Clock đo elapsed phải ổn định và không tự nhảy theo wall-clock.
- Không dùng helper để xử lý khoảng thời gian hàng thế kỷ vượt phạm vi diễn giải chênh lệch `long`.
- Không trộn giá trị `System.currentTimeMillis()` vào phép trừ `System.nanoTime()`.
- Khi còn đúng `0`, có thể chọn policy fail fast; kết quả của các bước đã hoàn tất không tự biến mất.
- Nếu cần delay dài bất thường, quản lý theo mốc lịch và cơ chế scheduler/renewal phù hợp thay vì giữ một phép chờ một lần cực lớn.

## 11. Truyền remaining budget vào Future.get()

Mẫu quan trọng cho nhiều bước:

```java
long remaining = budget.remainingNanos();
if (remaining <= 0) {
    throw new TimeoutException("request budget exhausted");
}
T result = future.get(remaining, TimeUnit.NANOSECONDS);
```

Đây là **đoạn minh họa** trong method generic có khai báo checked exceptions; `budget` là helper tính thời gian còn lại và `future` là `Future<T>`.

`Future.get(timeout, unit)` có những kết quả cần tách biệt:

- **Thành công:** trả `T`.
- **Task fail:** ném `ExecutionException`; kiểm tra `getCause()`.
- **Future bị hủy:** ném `CancellationException`.
- **Thread caller bị ngắt khi chờ:** ném `InterruptedException`.
- **Không hoàn thành trước timeout chờ:** ném `TimeoutException`.

**Rất quan trọng:** một `TimeoutException` từ `Future.get(timeout)` **không tự hủy task**. Task có thể còn chạy và tiếp tục chiếm CPU/I/O. Nếu policy request muốn dừng task sau deadline, cân nhắc `future.cancel(true)` và hiểu đó chỉ là yêu cầu interrupt hợp tác.

### Ví dụ 3: timeout không tự cancel task

Tạo tệp `FutureWaitTimeoutDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureWaitTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();
                release.await();
                return "DONE";
            });

            started.await();
            try {
                future.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("caller timeout");
            }

            System.out.println("cancelled=" + future.isCancelled());
            release.countDown();
            System.out.println("later=" + future.get());
        } finally {
            release.countDown();
            executor.shutdownNow();
            executor.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac FutureWaitTimeoutDemo.java
java FutureWaitTimeoutDemo
```

Kết quả khi không có interrupt ngoài ý muốn:

```text
caller timeout
cancelled=false
later=DONE
```

Task đã phát `started` nhưng đang chờ `release` chưa mở; `get(30ms)` phải timeout vì task chưa thể hoàn tất. `isCancelled()` vẫn `false` vì timeout **không gọi cancel**. Sau khi mở latch, task trả kết quả và lần `get()` tiếp theo thành công.

Trong ứng dụng thật, đừng lạm dụng `future.get()` **không timeout** sau một lần timeout tổng nếu SLA yêu cầu không chờ thêm. Ví dụ cố ý làm vậy để chứng minh timeout **không hủy**. Với end-to-end deadline, hãy dừng đợi hoặc dùng `cancel(true)` theo policy.

## 12. Dùng một budget cho Future, CountDownLatch và Lock

Các primitive đồng bộ có chữ ký tương tự nhưng kết quả khác nhau:

```java
future.get(remaining, TimeUnit.NANOSECONDS);           // T hoặc exception
latch.await(remaining, TimeUnit.NANOSECONDS);          // boolean
lock.tryLock(remaining, TimeUnit.NANOSECONDS);         // boolean
condition.await(remaining, TimeUnit.NANOSECONDS);      // boolean
executor.awaitTermination(remaining, TimeUnit.NANOSECONDS); // boolean
```

Đây là các đoạn minh họa, `remaining` phải được **tính mới ngay trước từng lời gọi**, và các biến thuộc đúng loại. **Không** tính remaining một lần rồi truyền lặp cho mọi bước.

Ví dụ flow thực tế:

```text
Clock bắt đầu ở t0; budget = 800ms.

Bước A: latch.await(remainingNanos, NANOSECONDS)
          nếu false: request timeout
          nếu true:  tính remaining mới

Bước B: future.get(remainingNanos, NANOSECONDS)
          nếu TimeoutException: request timeout
          nếu ExecutionException: task thất bại
          nếu success: tính remaining mới

Bước C: lock.tryLock(remainingNanos, NANOSECONDS)
          nếu false: request timeout
          nếu true: xử lý critical section ngắn, unlock finally
```

**Cảnh báo về deadlock:** tránh giữ lock trong lúc chờ một Future/latch nếu task đang chờ **cần chính lock đó** để tiến triển. Có thể chờ điều kiện/dữ liệu trước, chỉ khóa ở cuối để commit ngắn; phải bảo vệ invariant của kết quả.

Khi một bước chặn trả về do **interrupt**, thông điệp đó khác timeout. Với `InterruptedException`, truyền tiếp exception hoặc khôi phục cờ nếu không thể propagate và dừng ở điểm an toàn. Không “reset budget” do interrupt rồi cố chờ thêm toàn bộ timeout.

## 13. Ví dụ 4: end-to-end deadline với hai bước chờ

Chương trình dưới có một budget chung cho **hai latch**. Cả hai được mở sẵn để minh họa nhánh thành công và không dựa vào timing của worker. Phần tính deadline vẫn sử dụng `System.nanoTime()` thực.

Tạo tệp `SharedDeadlineDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class SharedDeadlineDemo {
    static long remainingNanos(long startedAt, long budgetNanos) {
        long elapsed = System.nanoTime() - startedAt;
        return Math.max(0L, budgetNanos - elapsed);
    }

    static boolean awaitWithinBudget(
            CountDownLatch first,
            CountDownLatch second,
            long timeout,
            TimeUnit unit) throws InterruptedException {

        long startedAt = System.nanoTime();
        long budgetNanos = unit.toNanos(timeout);

        long remaining = remainingNanos(startedAt, budgetNanos);
        if (remaining <= 0
                || !first.await(remaining, TimeUnit.NANOSECONDS)) {
            return false;
        }

        remaining = remainingNanos(startedAt, budgetNanos);
        if (remaining <= 0
                || !second.await(remaining, TimeUnit.NANOSECONDS)) {
            return false;
        }

        return true;
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch first = new CountDownLatch(0);
        CountDownLatch second = new CountDownLatch(0);

        boolean finished = awaitWithinBudget(
                first, second, 5, TimeUnit.SECONDS);
        System.out.println("finished=" + finished);
    }
}
```

```bash
javac SharedDeadlineDemo.java
java SharedDeadlineDemo
```

Kết quả trên một môi trường chạy bình thường khi hai bước rất ngắn hoàn thành trong năm giây:

```text
finished=true
```

Vì hai latch đã ở `count=0` nên `await` trả về ngay. Nhưng nếu JVM bị dừng/lên lịch chậm đến mức **vượt deadline giữa hai lần kiểm tra**, kết quả có thể là `false` theo đúng policy. Không bịa bảo đảm rằng một chương trình luôn hoàn tất trước một deadline vật lý chỉ vì tác vụ thông thường rất nhanh.

**Ý chính của code:** `startedAt` và `budgetNanos` được tạo **một lần**. Mỗi `await` nhận phần còn lại được tính mới từ cùng `startedAt`, không được thêm trọn vẹn `5 seconds` lần thứ hai.

## 14. Chờ Lock bằng time budget: quyền sở hữu và finally

`ReentrantLock.tryLock(timeout, unit)` chờ trong một khoảng có giới hạn, trả `true` khi **đã sở hữu lock**; trả `false` nếu hết thời hạn chờ mà không chiếm được khóa; có thể ném `InterruptedException` khi bị ngắt.

Mẫu:

```java
long remaining = budget.remainingNanos();
if (remaining <= 0) {
    throw new TimeoutException("no budget for lock");
}

if (!lock.tryLock(remaining, TimeUnit.NANOSECONDS)) {
    throw new TimeoutException("lock unavailable");
}
try {
    updateState();
} finally {
    lock.unlock();
}
```

Đây là đoạn minh họa trong phương thức khai báo throws phù hợp. `unlock()` chỉ được gọi **sau khi tryLock trả true**. Nếu trả false hoặc ném `InterruptedException`, caller chưa lấy được lock qua lời gọi đó, nên không được unlock vô điều kiện.

### Độ trễ critical section cũng tiêu tốn ngân sách

Ngay cả khi chiếm lock thành công ở giây thứ 4.9 trong ngân sách 5 giây, phần xử lý tiếp theo vẫn có thể mất thêm thời gian. `tryLock(timeout)` chỉ giới hạn **thời gian chờ lấy lock**, không đặt timer cưỡng chế chấm dứt code bên trong critical section.

Nếu cần SLA end-to-end nghiêm ngặt, kiểm tra `budget.remainingNanos()` trước phần có thể bắt đầu và chọn điểm hủy an toàn. Nhưng không bỏ dở một cập nhật nhiều trường trong trạng thái hỏng chỉ để đáp ứng deadline; phải thiết kế đơn vị commit/rollback.

## 15. `awaitTermination` cũng phải chia sẻ shutdown budget

Một ứng dụng có thể đóng executor hai giai đoạn:

1. `shutdown()`, đợi graceful.
2. Nếu chưa xong, `shutdownNow()`, đợi thêm.
3. Nếu vẫn chưa xong, báo chưa terminated.

Nếu caller có deadline **tổng là 8 giây**, không nên cứ dùng `awaitTermination(8, SECONDS)` ở cả hai pha; tổng có thể lên tới khoảng 16 giây.

Một mẫu dùng thời gian còn lại:

```java
long started = System.nanoTime();
long totalNanos = TimeUnit.SECONDS.toNanos(8);

executor.shutdown();
long remaining = Math.max(
        0L, totalNanos - (System.nanoTime() - started));

if (!executor.awaitTermination(remaining, TimeUnit.NANOSECONDS)) {
    executor.shutdownNow();

    remaining = Math.max(
            0L, totalNanos - (System.nanoTime() - started));

    boolean terminated = executor.awaitTermination(
            remaining, TimeUnit.NANOSECONDS);
    if (!terminated) {
        reportIncompleteShutdown();
    }
}
```

Đây là **đoạn minh họa** trong method đã xử lý `InterruptedException`, với `executor` và `reportIncompleteShutdown()` do ứng dụng định nghĩa.

**Lưu ý:** `shutdownNow()` là yêu cầu hủy best-effort, thường gửi interrupt worker. Nó không ép tất cả task ngừng ngay lập tức. Khi deadline hết, cần báo trạng thái shutdown chưa hoàn tất, không giả định “awaitTermination đã gọi xong nên worker chắc chắn dừng”.

Nếu thread điều phối shutdown bị interrupt trong lúc await, quy trình có thể gửi `shutdownNow()` và khôi phục cờ interrupt trước khi thoát; đây là quyết định lifecycle riêng, không nên nuốt tín hiệu.

## 16. Độ chính xác: conversion, clock và scheduler là ba tầng khác nhau

Hãy tách ba nguồn sai lệch:

| Tầng | Vấn đề | Ví dụ |
| --- | --- | --- |
| **Số học chuyển đơn vị** | Cắt phần thập phân khi chuyển sang đơn vị thô | 999.999ns → 0ms |
| **Đồng hồ đo elapsed** | Độ phân giải/chi phí lấy mẫu của `nanoTime`, gốc tùy ý | Hai lần gọi rất sát có thể không phân biệt được |
| **Scheduler và runtime** | Thread được lên lịch chậm, GC pause, CPU contention, timer granularity | Timeout 10ms không bảo đảm callback chạy đúng mốc 10ms |

Vì vậy `TimeUnit.NANOSECONDS` là **đơn vị biểu diễn độ trễ/timeout**, không phải lời hứa về độ chính xác nanosecond.

Nếu một task cần đo latency thực tế, dùng `System.nanoTime()` trước/sau và quan sát một phân phối nhiều lần. Không dùng một lần `sleep(10)` rồi khẳng định độ chính xác timer của JVM.

## 17. Sai lầm: dùng sleep để “đợi hoàn thành”

`TimeUnit.MILLISECONDS.sleep(100)` có thể cho task khác cơ hội chạy, nhưng không bảo đảm một tác vụ đã hoàn thành sau 100ms. Nếu cần biết một event đã xảy ra, dùng primitive diễn đạt điều kiện:

- `CountDownLatch.await(timeout, unit)` khi chờ một số sự kiện hoàn thành.
- `Future.get(timeout, unit)` khi đợi outcome của task.
- `Condition.await(timeout, unit)` khi chờ condition trong giao thức lock.
- `ExecutorService.awaitTermination(timeout, unit)` khi chờ toàn executor kết thúc.
- `Thread.join(timeout)` hoặc `TimeUnit.timedJoin` khi chờ một thread kết thúc.

Tương tự, trong test concurrency, không nên `sleep(50)` rồi giả định worker đã tới một dòng cụ thể. Dùng latch hoặc barrier thiết lập precondition; chỉ dùng timeout để **giới hạn test không treo vô hạn**, không thay thế tín hiệu hoàn thành.

## 18. Tính deadline bằng tổng chờ + xử lý + overhead

Một request có thể gồm:

```text
Budget = 1000ms
  chờ lock                    70ms
  query/cache lookup         400ms
  chờ Future khác            450ms
  serialization/logging       90ms
Tổng                        1010ms -> quá hạn
```

Nếu mỗi bước chỉ giới hạn thời gian chờ riêng mà không tính **CPU work, serialization, network processing và overhead**, end-to-end latency vẫn vượt SLA.

Cần tính remaining từ **clock chung** ngay trước mỗi bước và kiểm tra sau những phần xử lý đáng kể. Nhưng ngay cả code tính remaining chính xác cũng không thể cưỡng chế một lời gọi **blocking không hỗ trợ timeout** dừng ở đúng deadline. Với I/O, dùng API có connect/read/request deadline; với task CPU-bound, kiểm tra token hủy hoặc interrupt ở điểm an toàn; với những thao tác cần transaction, đảm bảo commit/rollback nhất quán.

**Deadline là policy điều phối**, không phải cơ chế khiến mọi code Java tự động bị preempt khi hết thời gian.

## 19. Phân biệt timeout, cancellation và interruption

Các khái niệm có liên hệ nhưng khác nhau:

- **Timeout:** một thao tác chờ không hoàn tất trong thời hạn được cho phép; API có thể trả `false`, `null`, hoặc ném `TimeoutException` tùy contract.
- **Cancellation:** yêu cầu công việc không cần tiếp tục; có thể qua `Future.cancel(true)` hoặc token ứng dụng.
- **Interruption:** tín hiệu đến một thread. Nhiều API chặn có thể phản ứng bằng `InterruptedException`; code phải hợp tác.
- **Deadline:** mốc kết thúc ngân sách cho **toàn workflow** hoặc một đơn vị công việc.

Ví dụ:

```java
try {
    String result = future.get(remaining, TimeUnit.NANOSECONDS);
    return result;
} catch (TimeoutException e) {
    future.cancel(true); // Chỉ nếu policy muốn yêu cầu hủy.
    throw e;
}
```

Đây là đoạn minh họa, không có import/context đầy đủ. `cancel(true)` cố yêu cầu interrupt task; **không bảo đảm cleanup xong ngay** hoặc side effect được rollback.

Một `InterruptedException` ở thread caller đang `get()` không mặc định có nghĩa **worker đã lỗi**. Cần xử lý hủy của caller và task theo giao thức riêng; nếu không thể propagate interrupt, nên khôi phục bằng `Thread.currentThread().interrupt()` trước khi rời scope.

## 20. Chuyển ngân sách sang nhiều dịch vụ hoặc process

`System.nanoTime()` có điểm gốc tùy ý trong một JVM. **Không gửi nguyên giá trị nanoTime như một deadline tuyệt đối sang máy khác** rồi yêu cầu máy nhận so sánh với đồng hồ của nó. Chúng không có cùng hệ quy chiếu.

Khi vượt ranh giới process:

1. Có thể gửi **remaining duration** đã được giảm theo elapsed time tại phía gửi.
2. Hoặc gửi **deadline trên wall-clock** với hiểu biết về lệch đồng hồ và contract timeout.
3. Tại phía nhận, dùng ngân sách nhận được để bắt đầu **đồng hồ monotonic cục bộ**.
4. Trừ chi phí truyền và bảo vệ trước độ trễ/clock skew theo yêu cầu hệ thống.
5. Chỉ truyền deadline vào API có hỗ trợ, không giả định một HTTP/database client tự kế thừa TimeUnit của caller.

Đây là nguyên tắc chung của thời hạn phân tán; không cần bất kỳ framework nào để hiểu. Với bài thực thi trong một JVM, dùng một `nanoTime()` tại điểm bắt đầu là cách đơn giản và đáng tin cho elapsed deadline.

## 21. ScheduledExecutorService: delay không phải thời điểm chính xác

`ScheduledExecutorService.schedule(task, delay, unit)` diễn đạt **độ trễ** trước khi một task trở nên đủ điều kiện để thực thi:

```java
scheduler.schedule(
        () -> sendReminder(),
        200,
        TimeUnit.MILLISECONDS);
```

Đây là đoạn minh họa, `scheduler` là `ScheduledExecutorService` và `sendReminder()` được định nghĩa. Nó **không cam kết callback bắt đầu sau chính xác 200.000000ms**; worker có thể bận, CPU bị tranh chấp hoặc JVM bị pause.

`scheduleAtFixedRate` cố duy trì các mốc tương đối theo period, còn `scheduleWithFixedDelay` tính delay sau khi một lần chạy hoàn thành. Cả hai đều chịu thực tế scheduler, độ dài task và exception của periodic task. Không tự suy diễn rằng TimeUnit có thể giúp “lịch chạy tuyệt đối chính xác”.

Nếu cần lên lịch theo giờ lịch (“8h sáng mai tại Hà Nội”), phải tính mốc calendar/wall clock bằng `java.time` trước, rồi chuyển thành delay ở thời điểm lập lịch, có xử lý múi giờ và thay đổi đồng hồ phù hợp. `TimeUnit.DAYS` vẫn chỉ là 24 giờ cố định.

## 22. Time budget có nên cộng trực tiếp vào `System.nanoTime()`?

Một mẫu hay gặp:

```java
long deadline = System.nanoTime() + timeoutNanos;
long remaining = deadline - System.nanoTime();
```

Mẫu này có thể đúng **nếu hiểu rõ overflow và giới hạn khoảng timeout**, nhưng dễ bị dùng sai khi:

- `timeoutNanos` đã được convert bão hòa tới `Long.MAX_VALUE`.
- Code so sánh `System.nanoTime() >= deadline` bằng toán tử số nguyên trực tiếp mà không xử lý wrap.
- Dùng deadline tạo trong JVM này ở JVM khác.
- Deadline được lưu như timestamp wall-clock.
- Hai lần gọi `System.nanoTime()` rất xa nhau hoặc toán học duration vượt khoảng biểu diễn an toàn.

Với bài học chung, **lưu `startedAt` + `allowedNanos`, tính `elapsed = now - startedAt` và `remaining = max(0, allowed - elapsed)`** dễ giải thích hơn và thích hợp cho timeout hợp lý.

Không sử dụng `System.currentTimeMillis()` để giải quyết bài toán “monotonic deadline” chỉ vì con số dễ đọc. Đồng hồ hệ thống có thể nhảy.

## 23. Kiểm tra tính đúng bằng fake clock và latch

### Test phép tính deadline

Dùng fake clock như `TimeBudgetDemo`:

- Tại `0ms`, budget `500ms`.
- Sau `300ms`, còn `200ms`.
- Sau `150ms` nữa, còn `50ms`.
- Sau `60ms` nữa, còn `0ms`.

Không cần sleep. Kết quả không phụ thuộc máy nhanh hay chậm.

### Test timeout của một API chờ

Giữ một `CountDownLatch` đóng, xác nhận `await(30, MILLISECONDS)` trả `false` vì latch không thể mở trước khi timeout. Sau đó mở latch và kiểm tra thành công. Phải xử lý trường hợp thread test bị interrupt.

### Test phân biệt timeout và cancel

Dùng `FutureWaitTimeoutDemo` để xác nhận `get(timeout)` ném `TimeoutException` nhưng `isCancelled()` vẫn `false`; task hoàn tất sau khi được mở latch.

### Tránh flaky test

Không đo “phải đúng chính xác 30ms” bằng `System.currentTimeMillis()` hoặc yêu cầu scheduler bảo đảm cực ngắn. Có thể đặt timeout hợp lý và kiểm tra **trạng thái logic**: đã timeout khi precondition không thể hoàn tất, đã hoàn tất sau latch, không mất interrupt và cleanup executor.

## 24. Những lỗi thường gặp

### 24.1. Đảo thứ tự nguồn/đích của `convert`

`TimeUnit.SECONDS.convert(5000, MILLISECONDS)` là `5` giây, còn `TimeUnit.MILLISECONDS.convert(5, SECONDS)` là `5000` mili giây. Hãy đọc theo công thức **target.convert(value, source)**.

### 24.2. Lấy kết quả cắt phần dư làm deadline

`NANOSECONDS.toMillis(500_000) == 0` không có nghĩa 500.000ns đã hết. Kiểm tra phần còn lại bằng nanos.

### 24.3. Chuyển Duration lớn bằng phép nhân thủ công

`seconds * 1_000_000_000L` có thể overflow. Dùng `TimeUnit.SECONDS.toNanos(seconds)` nếu cần quy tắc saturation; vẫn phải validate timeout hợp lệ cho domain.

### 24.4. Reset timeout ở mỗi bước

`get(1s)` rồi `tryLock(1s)` rồi `await(1s)` có thể ngốn tới 3s. Dùng **một budget** và tính remaining trước từng bước.

### 24.5. Dùng wall-clock cho elapsed timeout

`System.currentTimeMillis()` có thể thay đổi khi hệ thống chỉnh giờ. `System.nanoTime()` phù hợp đo duration trong JVM.

### 24.6. Nhầm độ phân giải nanos với độ chính xác scheduler

Truyền `NANOSECONDS` không đảm bảo thread được đánh thức đúng 1ns. Timeout là ràng buộc trên logic chờ theo API, không phải SLA thực thi tuyệt đối.

### 24.7. Timeout rồi giả định Future đã bị hủy

`Future.get(timeout)` ném `TimeoutException` nhưng task có thể tiếp tục. Cần policy `cancel(true)` riêng nếu muốn yêu cầu ngừng.

### 24.8. Ngủ để chờ điều kiện

`sleep(100)` không chứng minh task/condition đã xong. Dùng `CountDownLatch`, `Future`, `Condition` hoặc primitive tương ứng.

### 24.9. Dùng TimeUnit.DAYS như “ngày lịch”

Một ngày cố định 24 giờ không phải mọi ngày địa phương trong lịch đổi giờ. Dùng `java.time` cho calendar semantics.

### 24.10. Cắt nhỏ thời gian tới millis quá sớm

Nếu một API cho phép `NANOSECONDS`, hãy giữ remaining trong nanos. Khi chuyển sang độ thô hơn, hãy hiểu truncation và không biến một thời lượng dương nhỏ thành “đã hết”.

### 24.11. Không nhả lock khi timeout/exception

Nếu `tryLock` thành công, luôn dùng `finally` để `unlock()`. Nếu thất bại hoặc bị interrupt trước khi lấy lock, không gọi unlock vô điều kiện.

### 24.12. Tin một helper deadline có thể dừng mọi I/O

Một elapsed budget chỉ cung cấp **giá trị remaining**. Nếu API downstream không hỗ trợ timeout/cancellation, deadline không thể tự preempt lời gọi đó.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** `TimeUnit.SECONDS.convert(1_999, TimeUnit.MILLISECONDS)` trả gì?

**Đáp án:** `1`; phần 999ms bị cắt do chuyển sang giây nguyên.

**Câu 2.** `TimeUnit.NANOSECONDS.toMillis(999_999)` bằng 0. Có phải đã hết thời gian?

**Đáp án:** Không nhất thiết; vẫn còn 999.999 nano giây. Cần kiểm tra ở đơn vị đủ mịn.

**Câu 3.** `TimeUnit.DAYS.toNanos(Long.MAX_VALUE)` có wrap số âm không?

**Đáp án:** Không. Phép đổi của `TimeUnit` bão hòa tới `Long.MAX_VALUE` khi vượt giới hạn.

**Câu 4.** Một workflow có budget 500ms, bước A dùng 300ms. Bước B được dùng tối đa bao lâu?

**Đáp án:** Khoảng 200ms còn lại (trừ thêm overhead thực tế) chứ không được reset lại 500ms.

**Câu 5.** Vì sao không dùng `Instant.now()` hoặc `System.currentTimeMillis()` để đo thời gian chờ monotonic?

**Đáp án:** Wall-clock có thể bị chỉnh; `System.nanoTime()` phù hợp đo elapsed duration trong cùng JVM.

**Câu 6.** `future.get(100, MILLISECONDS)` ném TimeoutException. Worker có bị hủy không?

**Đáp án:** Không tự động. Task có thể còn chạy; cancellation là yêu cầu riêng.

**Câu 7.** `TimeUnit.NANOSECONDS.sleep(1)` có bảo đảm code thức dậy chính xác sau 1ns không?

**Đáp án:** Không. Độ phân giải biểu diễn không đồng nghĩa độ chính xác thức dậy thực tế.

**Câu 8.** Nếu `lock.tryLock` trả false, có được gọi `lock.unlock()` không?

**Đáp án:** Không nếu thread chưa sở hữu khóa qua lời gọi ấy. Chỉ unlock sau khi đã acquire thành công.

**Câu 9.** `awaitTermination(timeout)` trả false có nghĩa executor đã dừng chưa?

**Đáp án:** Chưa đạt trạng thái terminated trong thời gian chờ; worker vẫn có thể đang chạy.

**Câu 10.** Có nên gửi giá trị tuyệt đối của `System.nanoTime()` qua mạng để server khác dùng như timestamp deadline không?

**Đáp án:** Không. NanoTime có gốc tùy ý và không phải một mốc có thể so sánh giữa các JVM. Truyền duration remaining hoặc deadline wall-clock có hợp đồng rõ.

**Câu 11.** Khi áp dụng một budget cho cả `CountDownLatch.await` và `Future.get`, vì sao phải tính remaining lại?

**Đáp án:** Vì thời gian chờ latch đã tiêu một phần ngân sách. Nếu dùng lại timeout ban đầu, tổng latency có thể vượt budget.

**Câu 12.** Muốn test đúng logic ngân sách 500ms có cần `Thread.sleep(300)` thật không?

**Đáp án:** Không. Fake clock được inject có thể mô phỏng elapsed time chính xác, tránh flaky test do scheduler.

## 26. Tổng kết

**`TimeUnit` biểu diễn đơn vị thời gian của các phép chuyển và API timeout, nhưng không phải đồng hồ và không tự đảm bảo độ chính xác lập lịch.** Khi chuyển sang đơn vị thô hơn, giá trị `long` được cắt phần dư; khi đổi sang đơn vị nhỏ hơn quá lớn, có thể bão hòa. Đừng đánh đồng `0ms` sau chuyển đổi với `0ns` còn lại.

Để quản lý **ngân sách thời gian qua nhiều bước**, hãy bắt đầu một đồng hồ elapsed bằng `System.nanoTime()`, giữ một budget chung, **tính lại `remainingNanos()` ngay trước từng API chờ**, xử lý riêng timeout/interrupt/cancel, và không reset thời hạn tại mỗi bước. `Future.get`, `CountDownLatch.await`, `Lock.tryLock` và `ExecutorService.awaitTermination` chỉ giới hạn phần chờ của chính lời gọi; các phần CPU/I/O khác vẫn tiêu thời gian chung.

Với Java concurrency, deadline đúng là một **giao thức end-to-end**, không phải một danh sách các lời gọi mỗi lời gọi được cấp một timeout riêng. Kiểm tra bằng fake clock và latch, giữ tính nhất quán khi hủy, và dùng các kiểu `java.time` cho thời điểm lịch thay vì nhầm với thời gian đo elapsed.
