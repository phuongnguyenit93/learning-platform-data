# `scheduleAtFixedRate()` và `scheduleWithFixedDelay()` trong Java

Khi ứng dụng Java cần kiểm tra sức khỏe, làm mới cache, lấy mẫu metric hoặc chạy một công việc định kỳ, `ScheduledExecutorService` cho phép lên lịch thực thi lặp lại mà không phải tự viết vòng `while` cộng `Thread.sleep()`. Hai API phổ biến có bề ngoài gần giống nhau nhưng khác **điểm tính lịch lần chạy tiếp theo**:

- **`scheduleAtFixedRate()`:** mục tiêu chạy ở các mốc thời gian cách đều nhau theo **lịch cố định**, tính từ thời điểm dự kiến của lần chạy đầu. Nếu một lần chạy chậm, lần sau có thể bắt đầu muộn và có thể chạy liên tiếp để bắt kịp lịch; **không có hai lần chạy của cùng periodic task chồng lên nhau**.
- **`scheduleWithFixedDelay()`:** lần sau chỉ được lên lịch sau khi **lần trước kết thúc**, rồi đợi đủ một khoảng delay. Tần suất thực tế phụ thuộc cả thời gian chạy công việc.

Cả hai đều chạy bằng thread pool có lịch của Java SE. **Không có cam kết hard real-time**: thời gian chính xác có thể trễ do scheduler, CPU, queue, garbage collection hoặc task khác. Thêm nữa, một tác vụ định kỳ ném exception không được xử lý sẽ khiến **những lần chạy sau bị ngừng** theo hợp đồng hai API.

Bài thuộc **Future & Scheduling** của **Java concurrency nói chung**, dùng JDK 17+, không dùng annotation, scheduler hoặc runtime riêng của Spring Framework.

## 1. API ở đâu, dùng loại executor nào?

Interface `ScheduledExecutorService` nằm trong `java.util.concurrent` và mở rộng `ExecutorService`. Triển khai thường dùng nhất là `ScheduledThreadPoolExecutor`.

Ví dụ tạo scheduler:

```java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;

ScheduledExecutorService scheduler =
        Executors.newScheduledThreadPool(2);
```

Đây là snippet minh họa, không phải chương trình độc lập. Factory thường tạo một `ScheduledThreadPoolExecutor` với số core thread tương ứng. Hai lựa chọn khác:

```java
ScheduledExecutorService one =
        Executors.newSingleThreadScheduledExecutor();

ScheduledExecutorService several =
        Executors.newScheduledThreadPool(4);
```

`newSingleThreadScheduledExecutor()` cung cấp một scheduler dùng một thread xử lý lần lượt task (và có thể thay worker khi cần); `newScheduledThreadPool(4)` có thể thực thi **các task khác nhau** đồng thời trên tối đa số core worker phù hợp.

Một scheduled executor **không phải một clock timer chính xác tuyệt đối**, và con số core pool không tạo bảo đảm về thời điểm task bắt đầu. Cần thiết kế logic chịu được trễ và quá tải.

## 2. Chữ ký hai phương thức và các tham số

```java
ScheduledFuture<?> scheduleAtFixedRate(
        Runnable command,
        long initialDelay,
        long period,
        TimeUnit unit);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable command,
        long initialDelay,
        long delay,
        TimeUnit unit);
```

Đây là khai báo API minh họa, không phải code thêm vào class.

| Tham số | `scheduleAtFixedRate` | `scheduleWithFixedDelay` |
| --- | --- | --- |
| `command` | `Runnable` sẽ chạy nhiều lần | `Runnable` sẽ chạy nhiều lần |
| `initialDelay` | Đợi bao lâu trước mốc lần chạy đầu | Đợi bao lâu trước lần chạy đầu |
| `period` / `delay` | Khoảng cách giữa **các mốc bắt đầu dự kiến** | Khoảng cách giữa **kết thúc lần trước** và **bắt đầu lần sau** |
| `unit` | Đơn vị thời gian của initialDelay và period | Đơn vị thời gian của initialDelay và delay |
| Kết quả | `ScheduledFuture<?>` điều khiển/quan sát lịch | `ScheduledFuture<?>` điều khiển/quan sát lịch |

Đối với cả hai:

- `period` hoặc `delay` phải **dương**; giá trị bằng 0 hoặc âm gây `IllegalArgumentException`.
- `initialDelay` bằng 0 (hoặc âm theo contract của delayed execution) có nghĩa lần đầu được xem là có thể chạy ngay, nhưng vẫn chịu scheduling.
- Nếu command là `null`, contract ném `NullPointerException`.
- Nếu executor không chấp nhận task (ví dụ đã shutdown), có thể gặp `RejectedExecutionException`.
- `Runnable` không trả giá trị nghiệp vụ; `ScheduledFuture<?>` chủ yếu đại diện lifecycle/cancel và exception của task định kỳ, không phải stream kết quả mỗi lần chạy.

## 3. Fixed rate: mốc theo lịch, không theo lúc task kết thúc

Giả sử `initialDelay = 0`, `period = 1 giây`. Các **mốc lý tưởng** lần lượt là:

```text
time (s):  0       1       2       3       4       5
           |-------|-------|-------|-------|-------|
target:    R1      R2      R3      R4      R5      R6
```

Nếu từng lần chạy khoảng 200 ms, scheduler thường có thời gian rảnh giữa các lần. Khi một lần chạy kéo dài 1,6 giây, mốc lần tiếp theo đã đến trước khi lần hiện tại kết thúc:

```text
Mốc lịch:  0       1       2       3       4       5
           |-------|-------|-------|-------|-------|
run R1:    [==============]   (mất khoảng 1,6 s)
run R2:                   [==] (có thể bắt đầu muộn)
run R3:                     [==]
```

Sơ đồ là **minh họa quan hệ thời gian**, không phải output bắt buộc. Java không hứa mốc thực tế cách nhau chính xác 1 giây.

Điều quan trọng:

1. Mục tiêu khoảng cách dựa trên lịch bắt đầu dự kiến, không cộng period sau lúc task hoàn thành.
2. Nếu task bị trễ/overrun, lần sau **được phép bắt đầu muộn**.
3. Các lần chạy có thể gần nhau hoặc liên tiếp khi scheduler đang trễ lịch.
4. **Không chồng lấn các lần thực thi của cùng một periodic task**, ngay cả trong pool có nhiều worker.
5. Các lần liên tiếp có thể chạy trên **những worker thread khác nhau**, và `ScheduledThreadPoolExecutor` bảo đảm hiệu ứng lần trước happens-before lần sau đối với cùng periodic task.

Không nên hiểu "fixed rate" là "bắt buộc cứ 1 giây tạo thêm một bản sao độc lập". `scheduleAtFixedRate` không phải cơ chế tự động nhân bản task khi task cũ chạy chậm.

## 4. Fixed delay: khoảng nghỉ sau khi làm xong

Giả sử `initialDelay = 0`, `delay = 1 giây`; lần thứ nhất chạy 600 ms:

```text
time:      0        0.6        1.6        2.2        3.2
           |--------|----------|----------|----------|
run 1:     [======]
delay:              [----------]
run 2:                         [======]
delay:                                  [----------]
run 3:                                             ...
```

Với `scheduleWithFixedDelay`, lần kế tiếp được lên lịch sau khi **lần hiện tại kết thúc** cộng `delay`. Nếu lần hiện tại mất 2 giây và delay 1 giây, khoảng từ lúc bắt đầu lần này đến lần sau thường xấp xỉ 3 giây cộng trễ scheduling.

Vì vậy:

- Hữu ích cho polling nên nghỉ sau mỗi lần hoàn thành.
- Không cố bắt kịp mốc lịch bị lỡ; hệ thống có khoảng nghỉ được định nghĩa giữa các lần hoàn tất thành công.
- Một lần chạy chậm kéo theo việc lần sau bắt đầu muộn hơn tương ứng.
- Giống fixed rate, **không có hai lần chạy của cùng một periodic task chạy chồng nhau**.

Nếu yêu cầu là "ít nhất 1 giây giữa hai lần gửi network request", fixed delay thường dễ phù hợp hơn fixed rate; nhưng phải còn xét retry, những request khác và deadline của công việc bên trong.

## 5. So sánh ngắn gọn theo trục thời gian

Giả sử task kéo dài 800 ms và khoảng cấu hình 500 ms, không tính scheduler jitter:

| Yếu tố | Fixed rate (period 500 ms) | Fixed delay (delay 500 ms) |
| --- | --- | --- |
| Mốc tính tiếp theo | Mốc bắt đầu theo lịch từ lần đầu | Lúc kết thúc lần trước |
| Khi task chạy 800 ms | Lịch trễ, lần sau có thể bắt đầu gần ngay sau kết thúc | Chờ thêm khoảng 500 ms sau khi kết thúc |
| Khoảng giữa các lần bắt đầu | Có thể gần 800 ms khi task luôn overrun | Xấp xỉ 800 + 500 = 1.300 ms |
| Có catch-up không? | Có thể bắt đầu các lần muộn liên tiếp để đuổi lịch | Không |
| Một periodic task có overlap không? | Không | Không |
| Tần suất gắn với | Mục tiêu cadence của lịch | Chu kỳ làm việc + thời gian nghỉ |

Các số là **ước lượng để học**, không phải thời gian được đảm bảo bởi JVM. Khi hệ thống có scheduler delay lớn, các khoảng quan sát được có thể dài hơn đáng kể.

## 6. Ví dụ Java 17+: cả hai lịch hoàn thành ít nhất ba lần

Ví dụ sau kiểm tra **lifecycle** bằng `CountDownLatch` thay vì đoán khoảng thời gian bằng `Thread.sleep`.

Lưu thành `PeriodicThreeRunsDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class PeriodicThreeRunsDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newScheduledThreadPool(2);
        CountDownLatch rates = new CountDownLatch(3);
        CountDownLatch delays = new CountDownLatch(3);

        try {
            ScheduledFuture<?> fixedRate =
                    scheduler.scheduleAtFixedRate(
                            rates::countDown,
                            0, 10, TimeUnit.MILLISECONDS);

            ScheduledFuture<?> fixedDelay =
                    scheduler.scheduleWithFixedDelay(
                            delays::countDown,
                            0, 10, TimeUnit.MILLISECONDS);

            boolean rateReached = rates.await(
                    5, TimeUnit.SECONDS);
            boolean delayReached = delays.await(
                    5, TimeUnit.SECONDS);

            fixedRate.cancel(false);
            fixedDelay.cancel(false);

            System.out.println("Rate reached three: " + rateReached);
            System.out.println("Delay reached three: " + delayReached);
            System.out.println("Both canceled: "
                    + (fixedRate.isCancelled()
                            && fixedDelay.isCancelled()));
        } finally {
            scheduler.shutdownNow();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac PeriodicThreeRunsDemo.java
java PeriodicThreeRunsDemo
```

**Stdout trên lần chạy bình thường, scheduler nhận được CPU trong 5 giây:**

```text
Rate reached three: true
Delay reached three: true
Both canceled: true
```

Cả hai periodic tasks có thể thực thi hơn ba lần trước khi main cancel vì scheduling của main không tức thời. **Bài cố ý không in số lần thực tế** hay hứa đúng ba lần. `CountDownLatch` chỉ xác minh ít nhất ba invocation đã chạy. `cancel(false)` yêu cầu dừng những lần chạy **tương lai**; không tự interrupt invocation đang chạy.

Dùng `await(timeout)` trong test hạn chế nguy cơ treo vô hạn nếu executor không tiến triển. Trong ứng dụng thật, nếu `await` trả `false` thì phải xử lý sự kiện hết deadline thay vì mặc định thành công.

## 7. Lần chạy của cùng một periodic task không overlap

Có thể nhìn `ScheduledThreadPoolExecutor(4)` và nghĩ bốn thread sẽ chạy song song nhiều lần của **cùng** một công việc cố định nếu period nhỏ. Đó là hiểu nhầm.

Theo hợp đồng `ScheduledThreadPoolExecutor`, successive executions của **một periodic task** không chạy đồng thời. Khi task còn chạy, lần tiếp theo không được phép chồng lên invocation đó, dù pool có worker khác đang rảnh.

Hơn nữa, **hiệu ứng của lần thực thi trước happens-before lần kế tiếp** đối với cùng periodic task. Vì vậy một object task có mutable state riêng mà chỉ được truy cập từ các lần chạy định kỳ **của đúng task đó** có thể dựa vào sequencing này; nhưng nếu state còn được đọc/ghi từ thread khác, vẫn cần đồng bộ/safe publication phù hợp.

Ví dụ Java 17+ xác minh số invocation đồng thời của cùng periodic task:

Lưu thành `NoOverlapDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class NoOverlapDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(4);
        CountDownLatch completed = new CountDownLatch(3);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximumConcurrent = new AtomicInteger();

        try {
            ScheduledFuture<?> task =
                    scheduler.scheduleAtFixedRate(() -> {
                        int now = active.incrementAndGet();
                        maximumConcurrent.accumulateAndGet(
                                now, Math::max);
                        try {
                            Thread.sleep(60);
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        } finally {
                            active.decrementAndGet();
                            completed.countDown();
                        }
                    }, 0, 10, TimeUnit.MILLISECONDS);

            boolean reached = completed.await(
                    5, TimeUnit.SECONDS);
            task.cancel(false);

            System.out.println("Three runs observed: " + reached);
            System.out.println("Max concurrent runs: "
                    + maximumConcurrent.get());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
```

```bash
javac NoOverlapDemo.java
java NoOverlapDemo
```

Stdout trên đường chạy bình thường:

```text
Three runs observed: true
Max concurrent runs: 1
```

Task chạy lâu hơn period, nhưng cùng một task không overlap. `active` chỉ được tăng/giảm trong invocation, và `completed.countDown()` sau khi đã giảm. Code dùng Atomic cho phép quan sát metric an toàn nếu thay đổi logic về sau. Nếu main bị scheduler trì hoãn, task có thể thực thi lần thứ tư trước cancel; giá trị **max concurrent** vẫn là 1.

Chú ý hai tác vụ định kỳ **khác nhau** vẫn có thể chạy song song khi pool có đủ worker. Quy tắc không overlap ở đây áp dụng cho những lần chạy của **cùng một ScheduledFuture periodic task**, không phải mọi task trong executor.

## 8. Fixed rate có "bù" các mốc lịch bị lỡ không?

Khi task chạy lâu hơn `period`, các mốc lý tưởng của schedule vẫn tiến. Sau khi một invocation kết thúc, nếu mốc tiếp theo đã ở trong quá khứ, executor có thể cho invocation kế tiếp bắt đầu ngay khi có worker và tài nguyên. Khi tiếp tục trễ, các invocation có thể diễn ra gần nhau.

Nhưng:

- Không có cơ chế chạy **đồng thời nhiều bản sao** của cùng periodic task để bù backlog.
- Không có lời hứa chính xác "mỗi mốc lỡ tương ứng một lần xử lý ở millisecond nào".
- Nếu hệ thống liên tục quá tải, lịch có thể cứ trễ và task gần như chạy liên tục.
- Nếu task throw exception, lịch các lần sau bị ngừng (không tiếp tục bắt kịp).
- Nếu executor shutdown/cancel, quy tắc lifecycle chặn các lần chạy tương lai theo policy tương ứng.

**Một periodic task không phải event log.** Nếu nghiệp vụ phải xử lý tất cả sự kiện xảy ra từng giây kể cả sau khi app bị dừng hoặc restart, một lịch in-memory không cung cấp durability hay exactly-once semantics. Cần dữ liệu mốc/offset/queue hoặc cơ chế persistence riêng.

## 9. Fixed delay giúp có "cool-down" nhưng không bảo đảm tần suất tối thiểu

Với fixed delay 2 giây, sau một invocation hoàn thành bình thường, lần kế tiếp sẽ không được lên lịch bắt đầu **trước khoảng nghỉ đó** theo quy tắc scheduling. Điều này hữu ích khi muốn tránh polling dồn dập.

Tuy nhiên, không có cam kết invocation tiếp theo chắc chắn bắt đầu đúng sau 2 giây; nó có thể bị trễ do scheduler, pool bận hoặc tài nguyên hệ thống. Nếu chính task mất 10 giây, chu kỳ từ lúc bắt đầu lần này tới lần sau sẽ lớn hơn 12 giây.

Do đó, hãy đặt câu hỏi:

- Muốn **cadence cố định** cho việc lấy mẫu? Cân nhắc fixed rate.
- Muốn **nghỉ một khoảng sau khi hoàn tất công việc**? Cân nhắc fixed delay.
- Muốn **một thời điểm cụ thể trên đồng hồ** (ví dụ 02:00 địa phương hằng ngày)? Hai API trên nhận relative delay/period; muốn lịch theo wall clock và timezone thì cần lớp tính lịch khác.
- Muốn **rate limiting toàn bộ request của nhiều task**? Một lịch của từng task riêng không tự là global rate limiter.

## 10. Bảng timeline khi một lần chạy quá chậm

Giả sử mốc bắt đầu đầu là t=0, thời gian chạy mỗi invocation 1,4 giây và cấu hình là 1 giây, bỏ qua scheduler overhead:

```text
Fixed rate, period = 1 s
Lịch mục tiêu: 0, 1, 2, 3, 4, ...
Bắt đầu xấp xỉ: 0, 1.4, 2.8, 4.2, ...
Kết thúc xấp xỉ: 1.4, 2.8, 4.2, ...
=> gần như không có thời gian nghỉ khi liên tục overrun.

Fixed delay, delay = 1 s
Bắt đầu xấp xỉ: 0, 2.4, 4.8, 7.2, ...
Kết thúc xấp xỉ: 1.4, 3.8, 6.2, ...
=> luôn có khoảng nghỉ khoảng 1 s giữa các lần hoàn tất
   và lần bắt đầu tiếp theo.
```

Các số mang tính **lý tưởng hóa để giải thích**, không phải stdout hay deadline runtime đảm bảo.

Với fixed rate, bắt đầu lần thứ hai khoảng t=1,4 s không phải vì period đã đổi thành 1,4 s; đó là do invocation đầu chưa hoàn thành ở mốc t=1. Với fixed delay, mốc lần thứ hai tính **sau** kết thúc invocation đầu nên khoảng t=2,4 s.

## 11. Vì sao không in những khoảng thời gian như output cố định?

Hai lời gọi `System.nanoTime()` đặt trước mỗi invocation có thể giúp **quan sát** khoảng cách bắt đầu nhưng không có kết quả cố định. Nếu in `startDeltaMs` hoặc `currentTimeMillis`, mỗi máy và mỗi lần chạy có thể khác.

Một chương trình đo thực tế nên:

1. Ghi `System.nanoTime()` ngay khi invocation bắt đầu và kết thúc.
2. Tránh in log quá nhiều ngay trong critical path vì logging có thể tạo overhead.
3. Đợi đủ một số invocation bằng latch/atomic counter để lấy mẫu.
4. Tính median/p95 và so với độ dài task/queue contention.
5. Chỉ phát biểu **xu hướng**, không gán output tính theo mili-giây là bất biến.
6. Giữ riêng logic test correctness và benchmark performance; không dùng một con số jitter để kết luận scheduler sai.

`System.nanoTime()` dùng đo **thời lượng trôi qua**, không đại diện ngày giờ thực hoặc timezone. Trong các API scheduling này, các relative delays cũng không đảm bảo đồng bộ với mỗi mốc wall-clock tuyệt đối.

## 12. Exception trong periodic task: lần sau bị ngừng

Hợp đồng của hai phương thức định kỳ đều nói rằng nếu **một invocation ném exception**, các invocation tiếp theo bị **suppressed**. Điều này khác với nhiều ý tưởng cron "lỗi lần này, lần sau vẫn tiếp tục".

Ví dụ:

```java
scheduler.scheduleAtFixedRate(() -> {
    refreshCache(); // Ném RuntimeException nếu refresh thất bại.
}, 0, 1, TimeUnit.MINUTES);
```

Đây là snippet minh họa. Nếu `refreshCache()` ném unchecked exception ra khỏi `Runnable.run()`, lịch đó không tiếp tục ở các phút sau như bình thường.

Điều cần thiết kế:

- Task nào phải **dừng hẳn** khi lỗi để tránh làm hỏng state? Để exception propagate có thể là policy đúng.
- Task nào phải **tiếp tục** sau một lỗi tạm thời? Catch **có chọn lọc**, ghi nhận lỗi, đặt health status và quyết định liệu invocation sau có được phép chạy.
- Nếu exception được catch rồi bỏ qua hoàn toàn, hệ thống có thể tiếp tục lịch trong khi trạng thái dữ liệu vẫn sai. **Đừng dùng catch-all chỉ để "giữ lịch sống"** mà không có policy.
- Nếu task block vĩnh viễn, không có exception và cũng không hoàn tất invocation; scheduler không thể bắt đầu invocation kế của cùng task cho đến khi lần hiện tại kết thúc.

## 13. Ví dụ Java 17+: exception làm periodic future kết thúc

Lưu thành `PeriodicExceptionDemo.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicExceptionDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        AtomicInteger attempts = new AtomicInteger();

        try {
            ScheduledFuture<?> future =
                    scheduler.scheduleAtFixedRate(() -> {
                        int n = attempts.incrementAndGet();
                        if (n == 2) {
                            throw new IllegalStateException("boom");
                        }
                    }, 0, 10, TimeUnit.MILLISECONDS);

            boolean failed = false;
            String type = "";
            try {
                future.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException e) {
                failed = true;
                type = e.getCause().getClass().getSimpleName();
            }

            System.out.println("Failed: " + failed);
            System.out.println("Invocations: " + attempts.get());
            System.out.println("Cause: " + type);
            System.out.println("Future done: " + future.isDone());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
```

```bash
javac PeriodicExceptionDemo.java
java PeriodicExceptionDemo
```

Stdout trên đường chạy bình thường:

```text
Failed: true
Invocations: 2
Cause: IllegalStateException
Future done: true
```

`future.get(5, SECONDS)` đợi future kết thúc exceptional khi invocation thứ hai ném lỗi. Vì exception ngừng schedule, **không có lần thứ ba**. `ExecutionException.getCause()` giúp lấy nguyên nhân. Một invocation thất bại không tự khiến toàn bộ executor shutdown; các task khác của pool có thể tiếp tục theo hợp đồng.

Nếu thay `scheduleAtFixedRate` bằng `scheduleWithFixedDelay` với delay dương, quy tắc suppressed executions khi exception vẫn áp dụng.

## 14. `ScheduledFuture.get()` của periodic task có gì đặc biệt?

Cả hai method trả `ScheduledFuture<?>`. Vì lịch định kỳ chạy lặp lại cho đến khi cancel, exception hoặc shutdown policy kết thúc nó, nên **`future.get()` không trả một result bình thường cho mỗi lần chạy**.

Theo hợp đồng scheduling:

- Nếu periodic task còn được lên lịch liên tục và không kết thúc, `get()` sẽ **chờ** thay vì trả một `List` các kết quả.
- Nếu bị cancel, `get()` ném `CancellationException`.
- Nếu một invocation ném exception không được xử lý, `get()` có thể ném `ExecutionException` với cause tương ứng.
- Một `get(timeout, unit)` có thể ném `TimeoutException` nếu future vẫn chưa done.
- `isDone()` không phải counter của những lần chạy đã hoàn thành; periodic future có thể đã chạy 100 lần mà `isDone() == false`.

Nếu cần **kết quả của từng invocation**, hãy tự báo bằng queue, metric, listener hoặc một cấu trúc result/notification có đồng bộ phù hợp. Đừng gọi `get()` của periodic future sau mỗi lần chạy rồi chờ một kết quả bình thường.

## 15. Ví dụ Java 17+: `get(timeout)` không đếm từng lần lặp

Lưu thành `PeriodicFutureGetDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.CancellationException;

public class PeriodicFutureGetDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        CountDownLatch oneRun = new CountDownLatch(1);

        try {
            ScheduledFuture<?> future =
                    scheduler.scheduleWithFixedDelay(
                            oneRun::countDown,
                            0, 1, TimeUnit.HOURS);

            oneRun.await();

            boolean timedOut = false;
            try {
                future.get(10, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                timedOut = true;
            }

            future.cancel(false);

            boolean canceledGet = false;
            try {
                future.get();
            } catch (CancellationException e) {
                canceledGet = true;
            }

            System.out.println("One run completed: "
                    + (oneRun.getCount() == 0));
            System.out.println("Get timed out: " + timedOut);
            System.out.println("Get after cancel: " + canceledGet);
        } finally {
            scheduler.shutdownNow();
        }
    }
}
```

```bash
javac PeriodicFutureGetDemo.java
java PeriodicFutureGetDemo
```

Stdout trên đường chạy bình thường:

```text
One run completed: true
Get timed out: true
Get after cancel: true
```

`oneRun.await()` đợi invocation đầu đến tín hiệu. Periodic future vẫn còn một lượt tiếp theo dự kiến sau **1 giờ**, nên `get(10ms)` timeout, không trả giá trị của lần đầu. Sau `cancel(false)`, `get()` ném `CancellationException`.

Trong trường hợp scheduler bị shutdown hoặc task bị cancel từ nguồn khác trước đó, đường đi có thể khác; ví dụ chỉ có một thread main điều khiển vòng đời pool. `await()` trong demo cố ý không timeout, nhưng invocation đầu không block và pool đang chạy; test harness sản xuất vẫn nên có timeout để tránh treo khi môi trường hỏng.

## 16. Chủ động bắt lỗi: khi nào vẫn nên cho lần sau chạy?

Với một tác vụ polling không quan trọng từng kết quả đơn lẻ, có thể chọn chính sách **log/metric rồi tiếp tục**:

```java
scheduler.scheduleWithFixedDelay(() -> {
    try {
        pollRemoteService();
    } catch (TransientPollingException e) {
        recordFailure(e);
        // Lần kế tiếp vẫn được lên lịch sau delay.
    }
}, 0, 1, TimeUnit.MINUTES);
```

Đây là snippet minh họa với các class/method giả định.

Tuy nhiên:

- Chỉ catch những lỗi **thật sự có thể phục hồi**. Lỗi phá invariant có thể phải dừng schedule.
- Nếu task thực hiện I/O, cần timeout cho **chính I/O**, bởi delay chỉ bắt đầu khi task kết thúc.
- Khi catch `InterruptedException` trong một `Runnable`, thường nên `Thread.currentThread().interrupt()` rồi **thoát theo giao thức hủy**; đừng nuốt interrupt và tiếp tục task như thường.
- Ghi nhận failure rate, consecutive failures và last-success time; đừng chỉ in exception vào console rồi quên.
- Nếu cần retry/backoff, cố định delay 1 phút chưa chắc thích hợp. Có thể quản lý retry bên trong task với deadline hoặc lập lịch **one-shot** theo delay động.

## 17. Cancellation: dừng lịch tương lai khác việc ngắt invocation đang chạy

`ScheduledFuture.cancel(boolean mayInterruptIfRunning)` dùng để yêu cầu hủy periodic task.

- `cancel(false)`: yêu cầu chấm dứt lịch tương lai mà **không yêu cầu interrupt** invocation đang chạy qua tham số này.
- `cancel(true)`: cho phép thử interrupt invocation đang chạy, nếu implementation thực thi phù hợp; không bảo đảm dừng tức thì.
- Khi cancel thành công, `isCancelled()` và `isDone()` phản ánh trạng thái future, **không phải bằng chứng mọi side effect của invocation đã cleanup xong**.
- Task có thể hoàn tất gần thời điểm cancel; xử lý race và idempotency nếu tác vụ đang làm việc bên ngoài.

Mẫu vòng đời cơ bản:

```java
ScheduledFuture<?> handle =
        scheduler.scheduleWithFixedDelay(
                work, 0, 5, TimeUnit.SECONDS);

// Ở nơi quản lý vòng đời phù hợp:
handle.cancel(false);
```

Đây là snippet minh họa, với `scheduler` và `work` đã được khai báo ở nơi khác.

Không dựa vào `future.cancel(false)` để cưỡng bức dừng một HTTP request đã được gửi. Ngay cả `cancel(true)` cũng chỉ là một yêu cầu hợp tác; I/O có thể cần timeout/close riêng.

## 18. Ví dụ Java 17+: `cancel(false)` không hủy công việc đang chạy

Ví dụ dùng latch để tách **đã yêu cầu hủy lịch** khỏi **invocation đã kết thúc**.

Lưu thành `CancelPeriodicDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CancelPeriodicDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(1);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicInteger started = new AtomicInteger();

        try {
            ScheduledFuture<?> future =
                    scheduler.scheduleAtFixedRate(() -> {
                        started.incrementAndGet();
                        entered.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        } finally {
                            finished.countDown();
                        }
                    }, 0, 10, TimeUnit.MILLISECONDS);

            entered.await();
            boolean accepted = future.cancel(false);
            boolean beforeRelease = finished.getCount() == 0;

            release.countDown();
            finished.await();

            System.out.println("Cancel accepted: " + accepted);
            System.out.println("Finished before release: "
                    + beforeRelease);
            System.out.println("Invocations started: "
                    + started.get());
            System.out.println("Future canceled: "
                    + future.isCancelled());
        } finally {
            release.countDown();
            scheduler.shutdownNow();
        }
    }
}
```

```bash
javac CancelPeriodicDemo.java
java CancelPeriodicDemo
```

Stdout trên đường chạy bình thường:

```text
Cancel accepted: true
Finished before release: false
Invocations started: 1
Future canceled: true
```

**Phân tích:**

1. `entered.await()` chắc chắn invocation đầu đã bắt đầu và đang chờ `release`.
2. `cancel(false)` đặt future vào trạng thái canceled; nó **không yêu cầu interrupt** thread đang chờ latch.
3. Ngay trước khi main mở `release`, `finished` chưa về 0, nên invocation chưa hoàn tất; dòng `Finished before release: false` minh họa việc cancel không đồng nghĩa cleanup done.
4. Main mở latch, đợi `finished`, rồi in kết quả. Chỉ một invocation từng được bắt đầu vì những lần tiếp theo đã bị cancel trong khi lần đầu chưa kết thúc.
5. `finally` đảm bảo mở latch nếu gặp lỗi, tránh bỏ mặc worker đợi vô hạn.

Không áp dụng trực tiếp biến `finished` kiểu latch này cho nhiều invocation mà không làm rõ **generation**; một latch count=1 chỉ theo dõi một completion event.

## 19. Tự dừng sau N lần chạy: tránh lưu handle chưa an toàn

Một số ví dụ trên internet viết periodic task tự gọi `future.cancel(false)` thông qua biến `future` gán sau `scheduleAtFixedRate(..., 0, ...)`. Vì lần đầu **có thể chạy trước khi biến được gán**, code đó có race hoặc có nguy cơ `NullPointerException`.

Mẫu an toàn hơn trong chương trình đơn giản là:

1. Tạo task và một `CountDownLatch` đánh dấu N lần đã xảy ra.
2. Main hoặc owner của schedule đợi latch rồi hủy thông qua `ScheduledFuture` đã nhận.
3. Chấp nhận có thể có thêm invocation giữa lúc đạt N và lúc cancel, **trừ khi** task có state machine tự từ chối work vượt N.

Nếu yêu cầu **chính xác N lần side effect**, có thể đặt bộ đếm/claim atomic ngay trong task và không làm side effect ở những invocation vượt N, sau đó owner cancel lịch. Không nhầm "chỉ N side effects" với "scheduler gọi đúng N lần".

Ví dụ logic:

```java
int ordinal = count.incrementAndGet();
if (ordinal > 3) {
    return;
}
performSideEffectFor(ordinal);
```

Đây là snippet minh họa, `count` là `AtomicInteger` và `performSideEffectFor` là method giả định. Nếu external side effect có thể thất bại, cần thêm chính sách hoàn tất/at-least-once/exactly-once riêng; bộ đếm alone không tạo transaction.

## 20. Các task định kỳ khác nhau có thể tranh worker

Quy tắc không-overlap **chỉ áp dụng successive executions của cùng một periodic task**. Trong pool có hai worker:

```java
ScheduledThreadPoolExecutor pool =
        new ScheduledThreadPoolExecutor(2);

pool.scheduleAtFixedRate(this::sampleMetrics,
        0, 1, TimeUnit.SECONDS);

pool.scheduleWithFixedDelay(this::pollResource,
        0, 1, TimeUnit.SECONDS);
```

Đây là snippet minh họa trong class có `sampleMetrics` và `pollResource`.

Hai task trên có thể chạy **đồng thời** và cạnh tranh shared state. Nếu cả hai sửa một `ArrayList` hoặc cùng gửi dữ liệu qua một resource không thread-safe, phải bảo vệ nó hoặc thiết kế ownership riêng. Không có "global lock" chỉ vì cả hai thuộc cùng executor.

Với **một worker**, các task khác nhau được thực thi tuần tự, nhưng một periodic task rất chậm có thể gây **starvation/latency** cho task còn lại. Với nhiều worker, một task bị block lâu sẽ chiếm một worker nhưng task khác có thể chạy nếu còn capacity.

Vì vậy, chọn pool size dựa trên **độ dài task, blocking behavior và số loại periodic work**, không chỉ "mỗi phút có bao nhiêu schedule".

## 21. Ví dụ Java 17+: một worker khiến task khác đợi

Lưu thành `SharedSchedulerContentionDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class SharedSchedulerContentionDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(1);
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch secondFinished = new CountDownLatch(1);
        AtomicBoolean releasedBeforeSecond = new AtomicBoolean();

        try {
            pool.schedule(() -> {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, 0, TimeUnit.MILLISECONDS);

            firstStarted.await();

            pool.schedule(() -> {
                releasedBeforeSecond.set(
                        releaseFirst.getCount() == 0);
                secondFinished.countDown();
            }, 0, TimeUnit.MILLISECONDS);

            boolean secondBeforeRelease =
                    secondFinished.getCount() == 0;

            releaseFirst.countDown();
            secondFinished.await();

            System.out.println("Second ran before release: "
                    + secondBeforeRelease);
            System.out.println("Second saw release: "
                    + releasedBeforeSecond.get());
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
        }
    }
}
```

```bash
javac SharedSchedulerContentionDemo.java
java SharedSchedulerContentionDemo
```

Stdout trên đường chạy bình thường:

```text
Second ran before release: false
Second saw release: true
```

Vì pool chỉ có **một worker**, task đầu giữ worker trong khi chờ latch; task thứ hai không thể chạy trước khi task đầu rời chỗ chờ. Khi main mở latch, worker xử lý xong task đầu rồi mới có thể thực hiện task thứ hai.

Ví dụ dùng one-shot `schedule` để minh họa **worker contention** rõ ràng, không phụ thuộc period hoặc delay. Nguyên tắc tương tự áp dụng khi một invocation periodic chiếm worker quá lâu. Nếu pool có hai worker, hai task khác nhau có thể chạy cùng lúc và kết quả kiểm tra phải đổi.

## 22. `shutdown()` và tác vụ định kỳ có tiếp tục không?

Với `ScheduledThreadPoolExecutor`, shutdown policy quan trọng:

- **`setContinueExistingPeriodicTasksAfterShutdownPolicy(boolean)`:** quyết định liệu những periodic tasks đã được lập lịch có tiếp tục chạy **sau `shutdown()`** hay không. Mặc định là **`false`**.
- **`setExecuteExistingDelayedTasksAfterShutdownPolicy(boolean)`:** quyết định liệu những one-shot delayed tasks đã được nhận có chạy sau `shutdown()` hay không. Mặc định là **`true`**.
- `shutdownNow()` yêu cầu dừng công việc đang chạy, cố ngăn các task đợi và trả danh sách những task chưa bắt đầu theo hợp đồng; không bảo đảm task đang chạy ngừng ngay.

Đừng gộp **delayed one-shot** với **periodic** khi nói về shutdown. Một scheduler đã shutdown không tiếp nhận task mới, nhưng số task đã được nhận còn có thể chịu policy riêng.

Nếu bật continue-existing-periodic-after-shutdown, periodic tasks có thể tiếp tục được thực hiện, khiến `awaitTermination()` không hoàn tất cho đến khi chúng được cancel hoặc chấm dứt theo điều kiện khác. Phải lưu các `ScheduledFuture` handle và thiết kế lifecycle rõ ràng.

Ví dụ cấu hình minh họa:

```java
ScheduledThreadPoolExecutor pool =
        new ScheduledThreadPoolExecutor(2);

pool.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
pool.setExecuteExistingDelayedTasksAfterShutdownPolicy(true);
```

Đây là các giá trị default nhưng viết tường minh giúp người đọc biết chính sách. Nếu đang quản lý một pool được **chia sẻ**, đừng tự ý đổi policy hoặc shutdown từ một component không sở hữu executor.

## 23. `removeOnCancelPolicy` và queue giữ task đã cancel

`ScheduledThreadPoolExecutor` sử dụng delayed work queue. Một task được schedule rất xa trong tương lai rồi cancel có thể **vẫn còn trong queue** cho đến khi thời điểm delay tới, nếu áp dụng policy mặc định giữ entry.

Với nhiều task bị hủy trước khi tới deadline, điều này có thể khiến queue giữ thêm reference và tăng memory retention dù task sẽ không chạy.

Có thể bật:

```java
ScheduledThreadPoolExecutor pool =
        new ScheduledThreadPoolExecutor(2);
pool.setRemoveOnCancelPolicy(true);
```

Đây là snippet minh họa. `setRemoveOnCancelPolicy(true)` yêu cầu loại bỏ ngay những task bị cancel khỏi work queue khi được cancel, giúp giảm thời gian giữ reference khi có nhiều task delayed/periodic bị hủy. `getRemoveOnCancelPolicy()` cho biết policy hiện hành.

Không suy rằng việc task rời queue chứng minh task đang chạy đã kết thúc. **Queue retention** và **worker execution/cancellation** là hai vấn đề khác nhau.

Tránh trực tiếp `getQueue().remove(...)` hoặc chỉnh queue thay cho việc lưu `ScheduledFuture` handle và dùng `cancel`; thao tác tay có thể phá lifecycle tracking của executor.

## 24. Nếu task chạy lâu: tách scheduling khỏi công việc blocking

Một phương thức định kỳ có thể gọi HTTP, đọc file hoặc chờ downstream service. Nếu thao tác blocking không có timeout:

- Invocation hiện tại có thể kéo dài không giới hạn.
- Không có invocation tiếp theo của **cùng periodic schedule** trước khi lần này kết thúc.
- `scheduleWithFixedDelay` không thể bắt đầu delay sau một invocation chưa hoàn tất.
- `scheduleAtFixedRate` cũng không thể tự spawn invocation khác để vượt qua lần đang block.
- Các task khác có thể bị chậm nếu chung worker pool nhỏ.

Giải pháp phụ thuộc yêu cầu:

1. **Đặt timeout cho I/O** bằng API đúng của client/channel.
2. **Định nghĩa deadline** cho cả nghiệp vụ, thay vì chỉ quy định period/delay của scheduler.
3. Nếu cần một lượt không chồng lấn và có thể chờ, dùng scheduling tuần tự cùng chính sách timeout.
4. Nếu cần concurrency thực sự, tách timer khỏi worker pool và dùng **bounded concurrency / queue / semaphore**, nhưng phải quản lý overlap, backpressure, memory và cancellation.
5. **Không tự submit vô hạn** một task mới mỗi giây khi downstream đang kẹt; backlog có thể tăng không giới hạn.
6. Dùng metric `lastSuccess`, duration, failure count và queue depth để quan sát độ trễ thực tế.

Bản chất: `period` và `delay` quyết định **lịch gọi**, không áp một hard timeout cho thân task.

## 25. Ví dụ một-shot tự lập lịch lại: khi khoảng delay cần thay đổi

`scheduleWithFixedDelay` có **delay cố định**. Nếu cần exponential backoff hoặc lịch theo kết quả lần trước, một phương án là **schedule one-shot task rồi tự lập lịch lượt sau**.

Phác thảo:

```java
void pollOnce() {
    long nextDelayMillis;
    try {
        doPoll();
        nextDelayMillis = 1_000L;
    } catch (TransientException e) {
        nextDelayMillis = 5_000L;
    }

    if (!stopping.get()) {
        scheduler.schedule(this::pollOnce,
                nextDelayMillis, TimeUnit.MILLISECONDS);
    }
}
```

Đây là snippet minh họa, không phải chương trình standalone. `scheduler` là `ScheduledExecutorService`, `stopping` là trạng thái được công bố an toàn, `doPoll`/`TransientException` thuộc ứng dụng.

Những điều phải thiết kế thêm:

- Race giữa `stopping` và `schedule`: shutdown có thể xảy ra ngay sau kiểm tra, gây `RejectedExecutionException`; xử lý có chủ đích.
- Nếu muốn bảo đảm không còn task sau stop, quản lý scheduled handle và cancellation.
- Nếu exception khác thoát ra trước bước reschedule, chuỗi có thể dừng.
- Retry cần giới hạn và jitter phù hợp để tránh nhiều client đồng loạt retry.
- Một-shot scheduling không mang tự động semantics "same periodic task successive executions HB" theo cách periodic API; các task mới vẫn cần publication và đồng bộ đúng với state chia sẻ.

## 26. Fixed rate không phải cron hoặc lịch thời gian thực

Khi dùng:

```java
scheduler.scheduleAtFixedRate(
        this::refresh, 0, 24, TimeUnit.HOURS);
```

đây là snippet minh họa. Nó đặt một chu kỳ **relative 24 giờ**, không tự tương đương "mỗi ngày đúng 08:00 theo timezone địa phương". Giờ thực có daylight saving time, hệ thống có thể restart, và target relative cũng có scheduler delay.

Một lịch calendar cần xử lý:

- Timezone và daylight saving time.
- Lần chạy bị lỡ khi process tắt.
- Duplicate execution khi có nhiều instance JVM.
- Idempotency/transaction semantics.
- Chính sách catch-up hoặc skip missed occurrences.
- Persistence của lịch và state qua restart.

`ScheduledExecutorService` là công cụ chạy task định kỳ **trong một JVM đang sống**, không phải distributed scheduler hay durable job coordinator.

## 27. Đặt tên thread và tách pool theo tác vụ

Nếu scheduler có nhiều loại task, đặt tên worker giúp chẩn đoán:

```java
AtomicInteger sequence = new AtomicInteger();

ThreadFactory factory = runnable -> {
    Thread t = new Thread(runnable);
    t.setName("metrics-scheduler-" + sequence.incrementAndGet());
    return t;
};

ScheduledThreadPoolExecutor pool =
        new ScheduledThreadPoolExecutor(2, factory);
```

Đây là snippet minh họa, cần import `AtomicInteger`, `ThreadFactory` và `ScheduledThreadPoolExecutor`.

Nên cân nhắc pool riêng khi một nhóm task có blocking I/O dài hoặc có yêu cầu latency khác hẳn nhóm còn lại. Tuy nhiên, tạo quá nhiều pool cũng tiêu thụ thread và tài nguyên; cần quan sát workload thực tế.

Nếu pool được dùng chung bởi nhiều component, phải xác định **ai sở hữu shutdown và policy**. Không để một listener tùy ý gọi `shutdownNow()` rồi vô tình ngừng lịch của component khác.

## 28. Thực hành quản lý lifecycle đúng

Một public class sở hữu scheduler nên có chính sách start/stop rõ. Khung:

```java
final class PeriodicService implements AutoCloseable {
    private final ScheduledThreadPoolExecutor scheduler =
            new ScheduledThreadPoolExecutor(1);
    private ScheduledFuture<?> handle;

    synchronized void start() {
        if (handle != null) {
            throw new IllegalStateException("Already started");
        }
        handle = scheduler.scheduleWithFixedDelay(
                this::tick, 0, 1, TimeUnit.SECONDS);
    }

    private void tick() {
        // Thực hiện một bước có timeout/cancellation phù hợp.
    }

    @Override
    public synchronized void close() {
        if (handle != null) {
            handle.cancel(false);
        }
        scheduler.shutdown();
    }
}
```

Đây là class minh họa chưa có `main`; cần import `ScheduledThreadPoolExecutor`, `ScheduledFuture` và `TimeUnit`.

Điểm cần bổ sung trong production:

- Quy định `close()` có idempotent hay không và có chờ task đang chạy hoàn thành không.
- Tránh giữ monitor `this` khi **chờ worker** đang có khả năng gọi synchronized method của cùng object.
- Kiểm tra `scheduler.isShutdown()` hoặc state machine nếu `start` có thể được gọi sau close.
- `cancel(false)` không interrupt một tick đang chạy; nếu cần thời hạn shutdown, phải định nghĩa `awaitTermination(timeout)` và escalation.
- Nếu `tick` throw exception, future sẽ exceptional; cần báo health status thay vì im lặng.
- Nếu `tick` gọi external system, cần policy idempotency/timeout.

`AutoCloseable.close()` chỉ giúp caller biết có nơi đóng, không tự tạo transaction hay đợi cleanup nếu implementation không thực hiện điều đó.

## 29. Cách chọn API theo yêu cầu

| Yêu cầu | Gợi ý |
| --- | --- |
| Lấy mẫu metric định kỳ theo cadence danh nghĩa | `scheduleAtFixedRate` |
| Poll remote endpoint, nghỉ N giây sau mỗi poll | `scheduleWithFixedDelay` |
| Task phải có retry/backoff động | One-shot `schedule` tự lên lịch lại theo kết quả |
| Chỉ chạy một lần sau delay | `schedule` |
| Mỗi 08:00 địa phương và đúng DST | Tính lịch theo calendar/timezone, không chỉ fixed rate 24h |
| Không được overlap một periodic task | Cả hai periodic API đều có bảo đảm không overlap |
| Nhiều task khác nhau cần chạy đồng thời | Pool có đủ worker, và tự bảo vệ shared state |
| Chạy quá lâu phải bị hủy | Tách timeout/cancellation của task ra khỏi period/delay |
| Lỗi tạm thời không được làm lịch mất luôn | Catch/record theo failure policy bên trong task |
| Shutdown phải ngừng periodic jobs | Lưu handles, cancel, shutdown và chọn policies phù hợp |

**Mục tiêu sản phẩm quan trọng hơn tên API.** Fixed rate phù hợp với sampling cadence, nhưng nếu downstream không chịu nổi các lần chạy sát nhau sau overrun, fixed delay hoặc backoff động có thể bền vững hơn.

## 30. Những lỗi phổ biến

**1. "Fixed rate tạo thêm nhiều bản sao chạy chồng nhau khi task chậm."** Sai. Các lần chạy của một periodic task không overlap.

**2. "Fixed delay tính từ thời điểm bắt đầu lần trước."** Sai. Delay tính từ lúc lần trước **kết thúc**.

**3. "Fixed rate chính xác từng mili-giây."** Sai. Scheduler/JVM không cung cấp hard real-time guarantee.

**4. "Fixed rate không bao giờ chạy hai lần liên tiếp sát nhau."** Sai. Sau một overrun, các lần chạy có thể gần nhau khi catch-up lịch.

**5. "Task ném RuntimeException thì lần sau vẫn luôn chạy."** Sai. Các periodic invocations tiếp theo bị suppressed khi exception thoát ra khỏi task.

**6. "`ScheduledFuture.get()` trả kết quả của một lần chạy định kỳ."** Sai. Nó chờ state cuối của periodic future; không phải stream kết quả mỗi invocation.

**7. "`cancel(false)` dừng ngay invocation đang chạy."** Sai. Nó không yêu cầu interrupt invocation đó.

**8. "`cancel(true)` buộc side effect bên ngoài rollback."** Sai. Interruption chỉ là yêu cầu hợp tác.

**9. "Một pool bốn worker cho cùng task chạy song song bốn lần."** Sai. Nhiều worker giúp các task **khác nhau** chạy concurrent, không phá non-overlap của cùng periodic task.

**10. "Cấu hình `period=0` nghĩa chạy nhanh nhất có thể."** Sai. Period/delay phải dương; giá trị không hợp lệ bị từ chối.

**11. "`initialDelay=0` có nghĩa method schedule sẽ đợi command chạy xong."** Sai. Schedule trả handle; command chạy bất đồng bộ khi executor có worker.

**12. "Shutdown mặc định vẫn cho mọi periodic task chạy mãi."** Sai. Default continue-existing-periodic policy của `ScheduledThreadPoolExecutor` là false.

**13. "Đã cancel thì task được loại khỏi queue ngay trong mọi cấu hình."** Không mặc định; xem `setRemoveOnCancelPolicy(true)`.

**14. "Thêm `Thread.sleep(period)` bên trong command sẽ tương đương fixed delay."** Sai. Sleep làm dài thân invocation, không thay contract thời điểm scheduling; có thể phá throughput và làm catch-up của fixed rate.

**15. "Một periodic task in số lần rất nhiều chứng minh không có race."** Không. Shared state và các task khác vẫn cần synchronization theo Java Memory Model.

**16. "`scheduleAtFixedRate` là hệ thống đảm bảo exactly-once qua restart."** Không. Nó chỉ lên lịch in-memory trong executor đang chạy.

## 31. Câu hỏi tự kiểm tra

**Câu 1:** `scheduleAtFixedRate(task, 0, 1, SECONDS)`, mỗi invocation chạy 2 giây. Executor có chạy đồng thời hai invocation của cùng task không?

**Không.** Lần sau có thể bắt đầu muộn và gần sát khi lần trước kết thúc; không overlap cùng periodic task.

**Câu 2:** Với `scheduleWithFixedDelay(task, 0, 1, SECONDS)`, task mất 2 giây. Khoảng bắt đầu các lần liên tiếp khoảng bao lâu khi không có trễ scheduling?

Xấp xỉ **3 giây**: 2 giây làm việc cộng 1 giây nghỉ sau khi hoàn tất.

**Câu 3:** Vì sao `period=0` không thể dùng để chạy "liên tục"?

Vì API yêu cầu `period > 0`, nếu không ném `IllegalArgumentException`. Nếu muốn một worker liên tục xử lý queue, thường nên dùng consumer loop có hủy/lifecycle rõ hơn.

**Câu 4:** `ScheduledFuture.isDone()` false nhưng task đã chạy 1.000 lần, có mâu thuẫn không?

Không. Periodic future còn active; `isDone` không phải số lần hoàn tất.

**Câu 5:** Một invocation ném `IllegalStateException` ra ngoài `Runnable`, chuyện gì xảy ra?

Các invocation định kỳ kế tiếp bị ngừng. Có thể quan sát failure qua `ScheduledFuture.get()` ném `ExecutionException` với cause tương ứng.

**Câu 6:** Khi task làm I/O chậm, nên fixed rate hay fixed delay?

Tùy contract. Fixed delay thường hợp khi muốn nghỉ sau khi request kết thúc; fixed rate hợp khi muốn cadence danh nghĩa nhưng có nguy cơ chạy sát nhau sau overrun. Cả hai vẫn cần timeout cho I/O.

**Câu 7:** Khi một periodic task bị cancel với `false` trong lúc đang chờ latch, nó có tự thức không?

Không. `cancel(false)` không yêu cầu interrupt invocation đang chạy. Cần tín hiệu/lifecycle riêng để kết thúc.

**Câu 8:** Khi `shutdown()`, periodic tasks có tiếp tục mặc định không với `ScheduledThreadPoolExecutor`?

Mặc định **không**; policy `getContinueExistingPeriodicTasksAfterShutdownPolicy()` mặc định false. Delayed one-shot tasks có chính sách khác.

**Câu 9:** `scheduleAtFixedRate` có thay thế cron hằng ngày theo timezone không?

Không. Nó sử dụng chu kỳ tương đối, không tự giải quyết timezone, DST, restart hoặc distributed ownership.

**Câu 10:** Tại sao cần `setRemoveOnCancelPolicy(true)` nếu ứng dụng có nhiều task delayed bị cancel?

Để các entry canceled được loại sớm khỏi delayed queue, giảm thời gian giữ reference và tránh retention không cần thiết.

**Câu 11:** Hai periodic tasks khác nhau trong pool hai worker có được sửa một `HashMap` ordinary chung không?

Chỉ khi có giao thức đồng bộ bảo vệ phù hợp; scheduler không tự làm `HashMap` thread-safe.

**Câu 12:** Muốn điều chỉnh delay sau mỗi lỗi, nên làm gì?

Dùng one-shot scheduling với delay được tính từ trạng thái/lần thất bại, có giới hạn retry và lifecycle rõ; fixed-delay periodic API chỉ nhận một delay cố định.

## 32. Checklist triển khai và vận hành

Trước khi đưa lịch vào production:

1. **Mục tiêu thời gian là gì?** Mốc bắt đầu danh nghĩa hay khoảng nghỉ sau hoàn thành?
2. **Task tối đa chạy bao lâu?** Nếu có I/O, cấu hình timeout/deadline cho chính tác vụ.
3. **Có chấp nhận catch-up sát nhau không?** Nếu không, fixed delay/backoff có thể phù hợp.
4. **Có shared mutable state không?** Chỉ cùng periodic task được non-overlap; task khác vẫn concurrent.
5. **Ai sở hữu ScheduledFuture?** Giữ handle để cancel đúng lịch.
6. **Exception có làm mất schedule không?** Xác định policy recoverable vs fatal, báo health/metric.
7. **Có cần kết quả mỗi invocation không?** Không dựa vào `ScheduledFuture.get()` để lấy stream kết quả.
8. **Khi close, có interrupt invocation đang chạy không?** Chọn `cancel(false/true)` theo hợp đồng.
9. **Có timeout chờ shutdown không?** Dùng `awaitTermination` và escalation phù hợp; không block vô hạn trong monitor.
10. **Task canceled có giữ queue reference lâu không?** Cân nhắc `setRemoveOnCancelPolicy(true)`.
11. **Có cần calendar/DST hoặc durability không?** Đừng dùng fixed rate như một distributed persistent scheduler.
12. **Dữ liệu task bị lỗi hoặc chạy lại có idempotent không?** Cân nhắc kết quả tới muộn, retry và partial side effect.
13. **Pool có đủ worker cho các task khác nhau không?** Một task blocking dài có thể gây trễ task khác.
14. **Có backpressure và resource limit không?** Không submit vô hạn một task mới mỗi tick.
15. **Đo đạc gì?** Scheduled-vs-actual start delay, invocation duration, success/failure count, longest gap, queue depth.
16. **Test có dựa vào sleeping time chính xác không?** Dùng latches và kiểm tra invariant; log timestamp chỉ để quan sát.

## 33. Tổng kết

- **`scheduleAtFixedRate()`** nhắm tới các **mốc bắt đầu cách đều** theo thời gian tương đối; nếu task chậm, lần sau có thể bắt đầu muộn và những lần chạy có thể nối sát nhau.
- **`scheduleWithFixedDelay()`** bắt đầu đợi `delay` **sau khi lần trước kết thúc**; chu kỳ bắt đầu-bắt đầu gồm thời gian task + delay + trễ scheduling.
- **Cả hai không cho những lần chạy của cùng một periodic task overlap**, nhưng các task khác trong pool có thể thực thi đồng thời và cần bảo vệ shared state.
- **Exception thoát khỏi periodic Runnable ngừng các lần chạy sau.** Hãy thiết kế failure policy và theo dõi trạng thái của `ScheduledFuture`.
- **`ScheduledFuture.get()` không trả kết quả của từng tick**; cancel, shutdown và exceptional completion định nghĩa điểm kết thúc lifecycle.
- **Scheduling interval không phải task timeout.** Công việc blocking vẫn cần deadline, cancellation và cleanup riêng.
- **`ScheduledThreadPoolExecutor` có policy shutdown và remove-on-cancel riêng.** Chúng ảnh hưởng lifecycle và memory retention.
- **Hai API này không phải cron calendar, hard-real-time timer hoặc durable distributed job scheduler.** Yêu cầu đúng giờ theo timezone, bù lịch bị lỡ hay exactly-once qua restart cần giải pháp khác.

Lựa chọn đúng nhất xuất phát từ **ý nghĩa nghiệp vụ của khoảng thời gian**: bạn muốn công việc cố gắng xuất hiện theo nhịp đồng hồ, hay muốn một khoảng nghỉ chắc chắn giữa những lượt đã hoàn tất? Khi hiểu rõ ranh giới đó, cộng với exception/cancellation/shutdown contract của Java, việc lập lịch sẽ dễ dự đoán hơn nhiều so với tự kết hợp `while` và `Thread.sleep()`.