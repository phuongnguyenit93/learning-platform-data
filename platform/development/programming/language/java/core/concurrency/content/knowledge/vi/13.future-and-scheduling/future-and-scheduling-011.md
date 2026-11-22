# Exception trong tác vụ lặp và tác động tới lần chạy sau (Java ScheduledExecutorService)

> **Phạm vi:** **Future & Scheduling** trong Java SE 17+, đặc biệt là cách `ScheduledExecutorService.scheduleAtFixedRate()` và `scheduleWithFixedDelay()` xử lý exception phát sinh từ một lần chạy và ảnh hưởng của nó đến toàn bộ chuỗi lần chạy sau. Bài học áp dụng cho **concurrency Java nói chung**; các API scheduler, job annotation hoặc lifecycle riêng của Spring được dành cho chương khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **task chạy một lần** với **task lặp định kỳ**, và phân biệt `scheduleAtFixedRate()` với `scheduleWithFixedDelay()`.
- Phân tích đúng quy tắc API: **một lần thực thi của task định kỳ ném exception không được xử lý → những lần thực thi tiếp theo của chính task đó bị ngăn lại (suppressed)**.
- Biết cách quan sát một periodic task dừng vì lỗi qua `ScheduledFuture.isDone()` và `get()`, không ngộ nhận rằng `get()` của một periodic task vẫn đang hoạt động sẽ trả kết quả thông thường.
- Phân biệt `ExecutionException`, `CancellationException`, `TimeoutException`, `InterruptedException` và `RejectedExecutionException`.
- Giải thích vì sao `ScheduledThreadPoolExecutor.afterExecute(Runnable, Throwable)` thường nhận `Throwable == null` **kể cả khi scheduled command lỗi**.
- Quyết định khi nào **bắt và xử lý exception trong mỗi lần chạy** để cho phép lần tiếp theo, khi nào **để lỗi thoát ra để dừng schedule**, và khi nào cần alert/restart thủ công.
- Xây một chương trình Java 17 chạy được, xác minh bằng `Future.get(timeout)` và `CountDownLatch` thay vì đoán thứ tự thread bằng `Thread.sleep()`.
- Phân tích retry, backoff, shutdown, idempotency, memory visibility, overlap, metrics và những lỗi khiến một tác vụ định kỳ ngừng âm thầm.

**Quy tắc quan trọng nhất:** `scheduleAtFixedRate` / `scheduleWithFixedDelay` không mặc định “thử lại ở chu kỳ sau” khi `Runnable.run()` ném exception. Trên một chuỗi periodic scheduled task, ngoại lệ **thoát khỏi lần chạy** là một sự kiện kết thúc bất thường; các lần tiếp theo của **cùng ScheduledFuture** bị suppressed.

## 2. Vì sao đây là một lỗi vận hành dễ bỏ sót?

Một tác vụ mỗi 10 giây cập nhật dữ liệu trong bộ nhớ hoặc đồng bộ cache có thể chạy tốt hàng giờ. Một lần nó nhận đầu vào không hợp lệ và ném `RuntimeException`:

```java
scheduler.scheduleAtFixedRate(() -> {
    refreshCache(); // Có thể throw RuntimeException.
}, 0, 10, TimeUnit.SECONDS);
```

Đây là **đoạn code minh họa** đặt trong method; cần `scheduler` là `ScheduledExecutorService`, `refreshCache()` đã được định nghĩa và import `java.util.concurrent.TimeUnit`.

Nếu `refreshCache()` ném exception ra khỏi `Runnable`, nhiều người chờ rằng “đến 10 giây sau nó tự chạy lại”. Với `ScheduledExecutorService` chuẩn, **điều ngược lại mới đúng**: task định kỳ đó **không còn được chạy ở các chu kỳ sau**. Tác vụ khác trong cùng scheduler vẫn có thể chạy bình thường, vì trạng thái lỗi thường thuộc về **cụ thể ScheduledFuture** này, không có nghĩa toàn bộ thread pool đã chết.

Hậu quả có thể nghiêm trọng:

- Dữ liệu cache trở nên cũ, nhưng ứng dụng vẫn đáp ứng HTTP request.
- Mỗi ngày một lần đối soát không còn chạy, trong khi health check của process vẫn xanh.
- Monitoring chỉ theo dõi JVM sống/chết mà không theo dõi “lần chạy thành công cuối cùng”, nên không phát hiện tác vụ đã dừng.
- Log lỗi một lần bị bỏ lỡ hoặc exception được giữ trong Future khiến không ai kiểm tra.

Do đó cần thiết kế **error policy + completion monitoring** cho từng periodic task, thay vì trông cậy scheduler tự restart.

## 3. Ôn lại ScheduledExecutorService

`ScheduledExecutorService` mở rộng `ExecutorService` và cung cấp các phương thức để chạy trễ một lần hoặc chạy lặp:

| API | Mục đích | Số lần chạy | Giá trị trả về |
|---|---|---|---|
| `schedule(Runnable, delay, unit)` | Thực thi một Runnable sau khoảng trễ | Một lần | `ScheduledFuture<?>` |
| `schedule(Callable<V>, delay, unit)` | Thực thi Callable có kết quả sau khoảng trễ | Một lần | `ScheduledFuture<V>` |
| `scheduleAtFixedRate(Runnable, initialDelay, period, unit)` | Lặp theo **mốc bắt đầu** theo chu kỳ | Nhiều lần, cho đến khi dừng | `ScheduledFuture<?>` |
| `scheduleWithFixedDelay(Runnable, initialDelay, delay, unit)` | Lặp theo **khoảng nghỉ sau khi lần trước kết thúc** | Nhiều lần, cho đến khi dừng | `ScheduledFuture<?>` |

`ScheduledFuture` mở rộng `Delayed` và `Future`; bạn có thể dùng `cancel()`, `isDone()`, `isCancelled()` và `get()` theo semantics của từng loại tác vụ.

### Ví dụ tạo scheduler

```java
ScheduledExecutorService scheduler =
        Executors.newScheduledThreadPool(2);
```

Đây là đoạn code trong một method, với imports `java.util.concurrent.Executors` và `ScheduledExecutorService`. Lời gọi tạo scheduled executor có số **core threads** là 2; nó không có nghĩa rằng một periodic task sẽ chạy **hai bản đồng thời**.

**Quan trọng về API:** với hai phương thức periodic, `period` và `delay` phải lớn hơn 0; `initialDelay` có thể bằng 0. Một scheduler không phải cron/calendar scheduler: nó tính delay tương đối, không hứa thời điểm wall-clock tuyệt đối hoặc lịch biểu theo timezone.

## 4. Fixed rate và fixed delay: khác nhau ở điểm nào?

### `scheduleAtFixedRate()`

Cú pháp:

```java
ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
        task, initialDelay, period, TimeUnit.MILLISECONDS);
```

Đây là mã minh họa; `scheduler`, `task`, `initialDelay` và `period` đã có trong method.

Các lần bắt đầu **theo lịch danh nghĩa** tại các mốc:

```text
t0 + initialDelay
t0 + initialDelay + period
t0 + initialDelay + 2*period
...
```

Nếu một lần chạy kéo dài **hơn period**, những lần sau có thể **bắt đầu muộn**. Executor không chạy song song hai lần thực thi của **cùng một periodic task** chỉ vì nó bị trễ. Sau khi một lần chậm kết thúc, lần kế tiếp có thể đủ điều kiện chạy gần như ngay mà không cần nghỉ đủ một period nữa.

Ví dụ period 100 ms, lần đầu chạy 260 ms:

```text
Mốc danh nghĩa: 0 ms, 100 ms, 200 ms, 300 ms ...
Thực tế:       chạy #1 [0----------------260]
               chạy #2                    [260--...]
               #3, #4 có thể tiếp tục trễ tùy tải và lịch
```

Sơ đồ minh họa, không phải cam kết start time tuyệt đối. “Fixed rate” không có nghĩa scheduler bỏ việc đang chạy và tạo một bản chạy song song ở mỗi mốc.

### `scheduleWithFixedDelay()`

Cú pháp:

```java
ScheduledFuture<?> future = scheduler.scheduleWithFixedDelay(
        task, initialDelay, delay, TimeUnit.MILLISECONDS);
```

Đây là mã minh họa với các biến tương ứng đã có.

Lần tiếp theo đủ điều kiện chạy **sau khi lần trước kết thúc + delay**. Nếu task mất 260 ms và delay 100 ms:

```text
run #1:      [0----------------260]
delay:                            [260----360]
run #2:                                        [360--...]
```

Điểm khác biệt là **khoảng nghỉ sau completion**, không phải đuổi theo các mốc fixed-rate.

### So sánh nhanh

| Thuộc tính | Fixed rate | Fixed delay |
|---|---|---|
| Bắt đầu dựa trên | Mốc chu kỳ lý thuyết | Thời gian lần trước hoàn tất |
| Khi task chậm hơn period/delay | Những lần sau có thể khởi động muộn, có thể nối tiếp sát nhau | Sau completion vẫn đợi khoảng delay yêu cầu |
| Hai lần của **cùng periodic task** chạy chồng lên nhau? | Không theo contract của `ScheduledThreadPoolExecutor` | Không theo contract |
| Một lần ném exception thoát khỏi `run()` | **Ngăn các lần tiếp theo** | **Ngăn các lần tiếp theo** |
| `ScheduledFuture.get()` khi đang chạy định kỳ bình thường | Không trả về bình thường | Không trả về bình thường |

Lựa chọn dựa trên semantics: “cứ mỗi khoảng mốc tính từ lịch” hay “nghỉ N đơn vị sau lần chạy trước”. **Quy tắc exception giống nhau cho cả hai**.

## 5. Quy tắc chính thức khi một lần chạy ném exception

Đặc tả `ScheduledExecutorService` nói rõ đối với `scheduleAtFixedRate` và `scheduleWithFixedDelay`:

- Chuỗi periodic executions kéo dài đến khi **Future bị cancel**, executor chấm dứt theo policy, hoặc **một lần thực thi của task ném exception**.
- Khi exception thoát ra, **những lần thực thi kế tiếp bị suppressed**.
- `ScheduledFuture.get()` ném `ExecutionException`, trong đó cause là exception của task.
- `isDone()` chuyển thành **true** sau khi kết thúc bất thường.
- Periodic `get()` **không trả về bình thường** khi task đang lặp. Nó chỉ thoát bằng exception do canceled/failed hoặc điều kiện kết thúc được API quy định.

### Đọc sơ đồ trạng thái

```text
             TASK PERIODIC ĐƯỢC LÊN LỊCH
                        |
                  run #1 / #2 / ...
                   /           \
           run() return        run() throws
           bình thường          throwable
               |                    |
       tính lần chạy sau      Future completed
       theo fixed rate/delay  exceptionally
               |                    |
           chạy tiếp          suppress lần chạy sau
               |
       cho tới cancel/shutdown
```

Điểm quyết định là **exception có thoát khỏi `Runnable.run()` hay không**. Nếu code tự bắt lỗi rồi `run()` trở về bình thường, scheduler có cơ sở tiếp tục lập lịch; việc một xử lý nghiệp vụ thực tế đã thành công hay chưa là điều bạn phải đánh giá riêng.

### Không phải mọi lỗi dừng cả scheduler

Một `ScheduledThreadPoolExecutor` có thể chứa nhiều task periodic độc lập. Một task thất bại thường chỉ khiến chuỗi của **task đó** bị ngừng; các task khác có thể vẫn tiếp tục. Đừng nghĩ “pool vẫn sống, vậy định kỳ A chắc vẫn chạy”.

**Không được dựa vào ứng dụng còn phản hồi request làm bằng chứng tất cả jobs đang chạy.** Theo dõi heartbeat của từng task quan trọng.

## 6. Runnable có thể ném loại exception nào?

`Runnable.run()` không khai báo `throws Exception`, nhưng có thể ném **unchecked exceptions**:

```java
Runnable task = () -> {
    throw new IllegalStateException("unexpected state");
};
```

Đây là đoạn code độc lập bên trong một method. `IllegalStateException` là `RuntimeException` nên không cần `throws`.

Nếu operation có checked exception như `IOException`, lambda Runnable phải **catch hoặc chuyển thành unchecked exception**:

```java
Runnable task = () -> {
    try {
        readFile();
    } catch (IOException e) {
        throw new UncheckedIOException(e);
    }
};
```

Đây là code minh họa; cần imports `java.io.IOException` và `UncheckedIOException`, còn `readFile()` cần được định nghĩa.

Khi bạn wrap bằng `UncheckedIOException` rồi để nó thoát khỏi run(), chuỗi periodic **cũng bị suppressed**. `Future.get()` nhận `ExecutionException` có cause là `UncheckedIOException`; muốn xem nguyên nhân I/O gốc cần đi sâu thêm qua `getCause()` của wrapper đó.

`Error` cũng là Throwable và có thể làm task periodic kết thúc bất thường. **Không nên catch toàn bộ `Throwable` để tiếp tục trong mọi hoàn cảnh**, nhất là những lỗi nghiêm trọng của runtime như `OutOfMemoryError`. Chính sách khôi phục phải dựa trên những lỗi dự kiến có thể xử lý an toàn.

## 7. Ví dụ Java 17 chạy độc lập: dừng, phát hiện và phục hồi

Chương trình sau kiểm tra ba tình huống:

1. `scheduleAtFixedRate`: lần đầu ném `IllegalStateException`, Future chứa lỗi và task chỉ chạy **một** lần.
2. `scheduleWithFixedDelay`: lần đầu ném `IllegalArgumentException`, lần sau cũng bị suppressed.
3. Một task fixed-rate khác **bắt lỗi dự kiến trong chính Runnable**, ghi nhận lỗi rồi trở về bình thường; các lần tiếp theo vẫn được thực thi. `CountDownLatch` xác nhận ít nhất ba lần chạy, sau đó main chủ động `cancel(false)`.

Tạo file **`PeriodicFailureDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicFailureDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(2);
        try {
            AtomicInteger fixedRateRuns = new AtomicInteger();
            ScheduledFuture<?> failedRate = scheduler.scheduleAtFixedRate(() -> {
                fixedRateRuns.incrementAndGet();
                throw new IllegalStateException("failed rate task");
            }, 0, 10, TimeUnit.MILLISECONDS);

            try {
                failedRate.get(3, TimeUnit.SECONDS);
            } catch (ExecutionException e) {
                System.out.println("rateCause=" + e.getCause().getClass().getSimpleName());
            }
            System.out.println("rateRuns=" + fixedRateRuns.get());
            System.out.println("rateFutureDone=" + failedRate.isDone());

            AtomicInteger fixedDelayRuns = new AtomicInteger();
            ScheduledFuture<?> failedDelay = scheduler.scheduleWithFixedDelay(() -> {
                fixedDelayRuns.incrementAndGet();
                throw new IllegalArgumentException("failed delay task");
            }, 0, 10, TimeUnit.MILLISECONDS);
            try {
                failedDelay.get(3, TimeUnit.SECONDS);
            } catch (ExecutionException e) {
                System.out.println("delayCause=" + e.getCause().getClass().getSimpleName());
            }
            System.out.println("delayRuns=" + fixedDelayRuns.get());

            AtomicInteger handledFailures = new AtomicInteger();
            AtomicInteger recoveredRuns = new AtomicInteger();
            CountDownLatch threeRuns = new CountDownLatch(3);
            ScheduledFuture<?> recovered = scheduler.scheduleAtFixedRate(() -> {
                int round = recoveredRuns.incrementAndGet();
                try {
                    if (round == 1) {
                        throw new IllegalStateException("transient");
                    }
                } catch (RuntimeException e) {
                    handledFailures.incrementAndGet();
                } finally {
                    threeRuns.countDown();
                }
            }, 0, 10, TimeUnit.MILLISECONDS);

            if (!threeRuns.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("recovery runs timed out");
            }
            recovered.cancel(false);
            System.out.println("recoveredAtLeastThree=" + (recoveredRuns.get() >= 3));
            System.out.println("handledFailures=" + handledFailures.get());
            System.out.println("recoveredCancelled=" + recovered.isCancelled());
        } finally {
            scheduler.shutdownNow();
            if (!scheduler.awaitTermination(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("scheduler did not terminate");
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 PeriodicFailureDemo.java
java PeriodicFailureDemo
```

**Stdout đã biên dịch và chạy kiểm chứng:**

```text
rateCause=IllegalStateException
rateRuns=1
rateFutureDone=true
delayCause=IllegalArgumentException
delayRuns=1
recoveredAtLeastThree=true
handledFailures=1
recoveredCancelled=true
```

### Phân tích phần fixed rate thất bại

- `fixedRateRuns.incrementAndGet()` được thực thi trước `throw`.
- Lần đầu chạy ném `IllegalStateException` ra khỏi `Runnable.run()`.
- `ScheduledFuture` của chuỗi này chuyển thành **completed exceptionally**; các execution tiếp theo bị suppressed, không có lần #2.
- `failedRate.get(3, SECONDS)` ném `ExecutionException` vì periodic task đã thất bại, và `getCause()` là `IllegalStateException`.
- Khi `get` trả exception, failure đã được ghi nhận; `fixedRateRuns.get() == 1` là một kết luận xác định, không cần dùng sleep để “đợi xem nó có chạy lại không”.
- `failedRate.isDone()` true: nó đã hoàn tất **bất thường**, không phải là “chạy thành công”.

### Phân tích phần fixed delay thất bại

- Lần đầu của `failedDelay` tăng counter rồi ném `IllegalArgumentException`.
- `scheduleWithFixedDelay` có **cùng quy tắc suppression** khi exception thoát khỏi Runnable. `delayRuns=1`.
- `failedDelay.get()` ném `ExecutionException` với cause tương ứng.

### Phân tích phần tiếp tục sau lỗi đã xử lý

- Lần đầu task `recovered` cố tình ném `IllegalStateException`, nhưng `catch (RuntimeException e)` xử lý lỗi trong Runnable.
- `run()` **trở về bình thường**, nên scheduler tiếp tục lên lịch các lần kế tiếp theo fixed rate.
- `threeRuns` được count down trong `finally` mỗi lần, kể cả lần xuất hiện lỗi nhưng đã bắt.
- Main dùng `threeRuns.await(3, SECONDS)` để biết task đã vào ít nhất ba vòng. Không cần mong scheduler vô tình chạy đúng ba vòng trước khi main tiếp tục; vì vậy output dùng `recoveredAtLeastThree=true`, không in một số lần chính xác dễ bị lệch do scheduling.
- `recovered.cancel(false)` hủy những lần chạy tiếp theo; nếu một lần đang chạy, `false` không yêu cầu interrupt lần đang thực thi đó. `isCancelled()` true sau khi cancel thành công trong đường chạy của demo.
- `finally` gọi `shutdownNow()` và `awaitTermination` để không để worker scheduler tồn tại sau khi main xong; trong ứng dụng dài hạn cần shutdown policy phù hợp thay vì luôn shutdownNow.

**Giới hạn mẫu:** đây là bài demo, không mô phỏng retry network/database thật và không khuyến khích bắt mọi `RuntimeException` rồi tiếp tục bất chấp invariant. Nếu một lỗi làm state không còn an toàn, hãy dừng và alert. Ba chuỗi periodic là những task độc lập trong cùng pool; lỗi của một chuỗi không tự động là lỗi của cả pool.

## 8. Vì sao không nên chỉ đợi một khoảng thời gian rồi kiểm tra counter?

Một bài test sai thường dùng:

```java
// Minh họa cách kiểm thử dễ flaky, KHÔNG phải bằng chứng đúng.
scheduler.scheduleAtFixedRate(task, 0, 100, TimeUnit.MILLISECONDS);
Thread.sleep(500);
System.out.println(runs.get());
```

Đây là snippet minh họa, với `scheduler`, `task` và `runs` có sẵn. `Thread.sleep(500)` không hứa scheduler sẽ được CPU đúng lúc, task không block hay hệ thống không pause vì GC. Counter sau một thời gian có thể phụ thuộc scheduler.

Thay vào đó:

- Với **failure terminal**, dùng `ScheduledFuture.get(timeout, unit)` và kiểm tra `ExecutionException.getCause()`.
- Với **progress**, dùng `CountDownLatch`/`Phaser`/counters atomic kèm event completion rõ.
- Với **kết thúc sau cancel**, dùng `Future.isCancelled()`/termination protocol thích hợp; việc cancel Future không luôn bảo đảm action đã dừng nếu đang chạy và cancel(false).
- Với **không xảy ra lần #2**, suy luận từ **hợp đồng suppression** của API và trạng thái Future đã completed exceptionally; nếu cần thêm bằng chứng runtime, kiểm tra count sau khi failure completion hoặc dùng instrumentation.

Các phép thử chịu deadline nên **fail một cách kiểm soát** khi môi trường bị kẹt; tránh treo test mãi ở `get()` không timeout.

## 9. Điều gì xảy ra với ScheduledFuture?

`ScheduledFuture<?>` trả về cho một periodic schedule là một handle của **cả chuỗi lặp**, không phải một Future tách riêng cho từng lần chạy.

### Khi task vẫn đang lặp bình thường

- `isDone()` thường là **false** khi chuỗi còn active.
- `get()` **không trả về giá trị bình thường chỉ vì một iteration đã hoàn thành**.
- `get(timeout, unit)` có thể ném `TimeoutException` nếu schedule vẫn active và chưa được cancel/fail trong thời hạn chờ.
- Không dùng `get()` ngay sau `scheduleAtFixedRate(...)` để “chờ iteration đầu tiên”: nó có thể chờ **mãi** nếu task cứ tiếp tục chạy.

### Khi một iteration ném exception thoát ra

- `isDone() == true` sau completion bất thường.
- `get()` ném `ExecutionException` với cause là throwable gốc của iteration gây lỗi.
- Chuỗi không có lần chạy sau; cần một hành động tạo schedule mới nếu muốn tiếp tục.

### Khi caller hủy lịch

- Nếu `cancel(...)` thành công, `isCancelled() == true` và `isDone() == true`.
- `get()` ném `CancellationException` (unchecked), **không phải `ExecutionException`** của business task.
- `cancel(true)` yêu cầu interrupt tác vụ đang chạy theo semantics của Future; nó **không đảm bảo task lập tức dừng** nếu code bỏ qua interrupt hoặc đang ở I/O không interruptible.
- `cancel(false)` không yêu cầu interrupt tác vụ đang chạy; trạng thái Future canceled không tự chứng minh mọi side effect đã ngừng ngay.

### Phân biệt các exception của get()

| Ngoại lệ | Khi nào thường gặp | Ý nghĩa |
|---|---|---|
| `ExecutionException` | Một iteration ném Throwable thoát ra | Chuỗi kết thúc bất thường; `getCause()` là lỗi gốc |
| `CancellationException` | Future đã được hủy | Chuỗi bị cancel; không mặc định là business failure |
| `TimeoutException` | `get(timeout)` không thấy kết thúc trong thời hạn | Schedule có thể vẫn đang chạy; **get timeout không tự hủy** |
| `InterruptedException` | Thread gọi `get` bị interrupt khi đợi | Caller bị yêu cầu ngắt; cần propagate/khôi phục cờ theo contract |

**Không được coi `isDone()` là dấu hiệu thành công.** Với periodic task, done thường là tín hiệu quan trọng cho **canceled hoặc failed**, không phải “iteration gần nhất thành công”.

## 10. Tại sao exception có thể không xuất hiện trong afterExecute(Throwable)?

Một điểm tinh tế của `ScheduledThreadPoolExecutor`: implementation sử dụng các `ScheduledFuture` để quản lý công việc. JavaDoc của class này nêu rõ: **`afterExecute` luôn nhận tham số `Throwable` thứ hai là null**, ngay cả khi scheduled command chấm dứt bất thường. Muốn biết throwable, đọc outcome qua `Future.get()`.

Ví dụ monitor chưa đủ:

```java
@Override
protected void afterExecute(Runnable task, Throwable error) {
    super.afterExecute(task, error);
    if (error != null) {
        report(error);
    }
}
```

Đây là method minh họa của subclass `ScheduledThreadPoolExecutor`; `report(Throwable)` do ứng dụng định nghĩa. Kiểm tra `error != null` như trên có thể **bỏ sót hoàn toàn lỗi của scheduled tasks**, vì wrapper lưu lỗi trong Future.

**Một cảnh báo khác:** `afterExecute` được gọi sau **từng iteration** của periodic task, nhưng khi task tiếp tục lặp, `ScheduledFuture.isDone()` vẫn **false**. Nếu hook gọi `future.get()` vô điều kiện cho periodic task active, worker có thể **block vô hạn ngay trong afterExecute** và không còn chạy được iterations tiếp theo!

Mẫu an toàn hơn:

```java
@Override
protected void afterExecute(Runnable task, Throwable error) {
    try {
        if (task instanceof Future<?> future && future.isDone()) {
            try {
                future.get();  // Chỉ đọc outcome khi Future đã done.
            } catch (ExecutionException e) {
                reportFailure(e.getCause());
            } catch (CancellationException e) {
                recordCancellation();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    } finally {
        super.afterExecute(task, error);
    }
}
```

Đây là **method minh họa** trong một subclass, với `reportFailure`, `recordCancellation` được cung cấp bên ngoài và imports `Future`, `ExecutionException`, `CancellationException`. Trong code thực, các methods telemetry này phải **nhanh, không block và exception-safe**, vì hook chạy trong worker thread. `future.isDone()` tránh `get()` blocking khi periodic Future còn active.

### Khác biệt với ThreadPoolExecutor thông thường

`ThreadPoolExecutor.afterExecute` khi nhận một direct `Runnable` qua `execute` có thể thấy Throwable thoát ra từ `run()`. Nhưng với `ScheduledThreadPoolExecutor`, **kể cả `execute()` cũng được wrapper thành scheduled future**. Vì vậy không nên chuyển nguyên mẫu “`t != null` là lỗi” từ thread pool thường sang scheduled pool mà không kiểm tra semantics của wrapper.

### Exception của hook không phải exception của business task

Nếu chính `beforeExecute` hoặc `afterExecute` ném exception, behavior của worker hook/lifecycle có thể khác với việc scheduled task `run()` ném exception. Không dùng hook để chứa business logic hoặc các thao tác có thể ném lỗi không được quản lý. Các lỗi đó có thể ảnh hưởng worker/monitoring và làm khó xác định nguyên nhân.

## 11. Phương án A: bắt và xử lý lỗi dự kiến để lịch tiếp tục

Nếu yêu cầu nghiệp vụ là “task phải tiếp tục ở chu kỳ sau dù lần này bị lỗi **có thể phục hồi**”, hãy xử lý lỗi **bên trong `Runnable`** trước khi nó thoát.

```java
Runnable refresh = () -> {
    try {
        refreshFromRemote();
        markSuccess();
    } catch (TransientNetworkException e) {
        recordFailure(e);
        // run() trả về bình thường; scheduler có thể chạy chu kỳ sau.
    }
};
```

Đây là **code minh họa**, không phải chương trình độc lập: `TransientNetworkException` và các method còn lại do ứng dụng định nghĩa. Chỉ bắt exception cụ thể, cho phép **retry ở chu kỳ kế tiếp** khi failure mode đó được xác định là an toàn.

**Không biến ngoại lệ thành “thành công”.** Dù `run()` về bình thường để scheduler tiếp tục, cần log/metric **iteration failed**, không tăng success counter. `ScheduledFuture` không thể cho bạn biết từng iteration từng thất bại đã được catch nếu chính code không báo outcome.

### Mẫu phân loại thất bại

Một policy ví dụ:

- **Transient/retryable:** timeout tạm thời, upstream trả trạng thái quá tải, kết nối ngắn hạn gặp vấn đề. Có thể ghi nhận, bỏ lần này và thử lại ở chu kỳ sau, nếu thao tác idempotent hoặc không gây trạng thái dở dang.
- **Permanent/data validation:** dữ liệu bất hợp lệ, precondition không còn đúng. Có thể cách ly dữ liệu xấu và tiếp tục với những dữ liệu tốt; hoặc dừng lịch nếu lỗi thể hiện invariant bị phá.
- **Programming/invariant failure:** `NullPointerException` không dự kiến, `IllegalStateException` báo state nghiêm trọng sai. Thường cần fail fast và alert hơn là catch rồi tiếp tục vô hạn.
- **JVM/runtime fatal:** `OutOfMemoryError` và các lỗi nghiêm trọng khác. Không cố bắt `Throwable` để “giữ schedule sống” một cách mù quáng.

Đặt **thao tác cleanup** trong `finally` phù hợp để release những tài nguyên thuộc iteration:

```java
Runnable task = () -> {
    Resource resource = openResource();
    try {
        performWork(resource);
    } finally {
        resource.close();
    }
};
```

Đây là **snippet minh họa**, `Resource`, `openResource`, `performWork` do ứng dụng định nghĩa. Với `AutoCloseable`, dùng try-with-resources khi hợp lý. Nếu cleanup cũng ném unchecked exception và thoát khỏi Runnable, **nó có thể làm cả periodic task ngừng**, dù phần main logic vừa chạy thành công.

## 12. Phương án B: để lỗi thoát ra khi cần dừng để tránh làm sai dữ liệu

Không phải lịch lặp nào cũng nên tiếp tục sau failure. Ví dụ job xử lý một batch rồi cập nhật cùng một state phụ thuộc:

- Một exception xảy ra sau khi cập nhật được 50% dữ liệu.
- Lần tiếp theo không biết đang ở batch nào, và chạy tiếp có thể ghi trùng hoặc mất item.
- Tiếp tục im lặng chỉ vì muốn “giữ scheduler sống” có thể gây lỗi lớn hơn.

Trong tình huống đó, để exception thoát khỏi `Runnable` để **suppression** là lựa chọn hợp lý, miễn có **alert và recovery workflow**:

```java
Runnable criticalJob = () -> {
    validateInvariant();   // Nếu không đúng, throw.
    commitOneBatch();      // Nếu lỗi, throw để dừng schedule.
};
```

Đây là snippet minh họa, methods do ứng dụng định nghĩa.

Điều quan trọng:

1. Lỗi bị báo rõ qua `ScheduledFuture.get()`/monitoring, không bị bỏ mặc.
2. Pipeline xác định trạng thái dữ liệu cuối đã được commit hay chưa.
3. Người vận hành hoặc controller có protocol reset/recover.
4. Khi khôi phục, không chỉ gọi `scheduleAtFixedRate` mới một cách vô điều kiện nếu instance cũ vẫn có thể đang chạy hoặc còn side effect.
5. Retry/restart phải **idempotent** hoặc có transactional semantics cần thiết.

**Suppression là behavior của scheduler, không phải một transaction/rollback của nghiệp vụ.** Các side effect đã xảy ra trước exception không được JVM tự hoàn tác.

## 13. Retry bên trong iteration hay thử lại ở chu kỳ sau?

Có hai cấp khác nhau:

### Retry nội bộ trong một iteration

Một execution có thể thử thao tác I/O vài lần, dùng backoff và timeout rồi quyết định return hoặc throw. Ví dụ:

```java
void runWithLimitedRetries() {
    for (int attempt = 1; attempt <= 3; attempt++) {
        try {
            callIdempotentRemoteApi();
            return;
        } catch (RetryableFailure e) {
            if (attempt == 3) {
                recordPermanentFailure(e);
                return; // hoặc throw để dừng schedule theo policy
            }
            backoff(attempt);
        }
    }
}
```

Đây là **method minh họa**, `RetryableFailure`, `callIdempotentRemoteApi`, `recordPermanentFailure` và `backoff` cần định nghĩa. Nếu `backoff` dùng sleep, phải xử lý `InterruptedException` đúng cách; deadline tổng thể không được vượt tùy tiện.

Khi retry trong iteration:

- Thời gian chạy iteration có thể dài hơn period/delay.
- `scheduleAtFixedRate` có thể bắt đầu lần sau muộn và chạy sát ngay sau completion để đuổi lịch.
- `scheduleWithFixedDelay` vẫn nghỉ đủ delay sau khi iteration kết thúc.
- Retry quá nhiều có thể giữ worker, tăng tải downstream và làm các task khác bị trễ.
- Một failure sau max attempts cần được ghi nhận, quyết định rõ **return để tiếp tục ở lần sau** hay **throw để suppress**.

### Để chu kỳ kế tiếp là lần retry

Nếu có thể bỏ qua kỳ hiện tại mà không phá invariant, catch lỗi tạm thời, log và return. Scheduler sẽ tự lên lịch lần sau; đây là retry **theo định kỳ**, không phải retry ngay lập tức. Cần bảo đảm input ở lần sau đủ để xử lý dữ liệu của lần thất bại, không tự động mất những work items cần ack.

### Retry không có nghĩa exactly-once

Nếu job gọi một API ngoài JVM và timeout **sau khi bên nhận đã commit**, retry có thể lặp side effect. Cần idempotency keys, transaction/outbox, checkpoint và business reconciliation theo yêu cầu. ScheduledExecutorService không bảo đảm exactly-once của external side effects.

## 14. Exception, interrupt và cancellation cần được phân loại rõ

### `InterruptedException`

Một `Runnable` không thể khai báo checked `InterruptedException`, nên khi gọi API interruptible phải tự xử lý:

```java
Runnable worker = () -> {
    try {
        waitForWork();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        // Dừng công việc hoặc báo hủy; không tiếp tục loop vô hạn.
    }
};
```

Đây là code minh họa, `waitForWork()` đã được định nghĩa. Khi interrupt biểu thị shutdown/cancel, **đừng nuốt** rồi coi đó là một failure retryable bình thường. Trong scheduled task, nếu code swallow interrupt và return bình thường nhưng Future không canceled, scheduler có thể còn lập lịch lại theo policy; shutdown path phải được xác định riêng.

Nếu một iteration được cancel `cancel(true)`:

- Cancellation đánh dấu Future canceled theo API.
- Interrupt thường là **yêu cầu** dừng; code phải hợp tác.
- Future canceled không phải bằng chứng external side effects đã được rollback hoặc iteration đã dừng hoàn toàn.

### `RejectedExecutionException`

Lỗi này có thể xảy ra khi bạn cố lên lịch một task mới sau shutdown, hoặc executor không thể nhận task theo policy. Nó xảy ra ở **submission/admission**, không phải exception phát sinh trong một iteration được scheduler thực thi. Theo dõi rejection riêng.

### `TimeoutException` từ Future.get

Một lời gọi:

```java
future.get(2, TimeUnit.SECONDS);
```

Đây là snippet minh họa, `future` là Future. Timeout của `get` nói rằng **caller không đợi thấy completion trong thời gian đó**. Với periodic task đang hoạt động, đây có thể là hành vi hoàn toàn bình thường. `get(timeout)` không tự cancel lịch.

### `Error`

Một `Error` không được bắt bằng `catch(Exception)`. Một Error ném khỏi iteration cũng khiến chuỗi periodic bị suppressed theo behavior của ScheduledExecutorService. Đừng catch Throwable vô điều kiện chỉ để bảo vệ lịch; các lỗi có thể cho thấy JVM hoặc resource đã ở trạng thái không còn đáng tin.

## 15. Task lặp không chạy chồng lên chính nó

Với `ScheduledThreadPoolExecutor`, các lần thực thi tiếp nối của **cùng periodic task** không chạy đồng thời, ngay cả khi một iteration lâu hơn period; các lần chạy sau có thể bắt đầu trễ.

Điều này rất quan trọng khi đọc logs:

```text
rate 100ms, iteration 1 mất 350ms

Task A: [run1------------------------------]
                                                [run2---]
Task B:    [runB]          [runB]
```

Sơ đồ mô tả hai schedules A và B độc lập; **B có thể chạy trong lúc A đang chạy** nếu pool có tài nguyên. Không overlap **giữa các iteration của A** không có nghĩa A không thể chạy song song với schedules khác.

JavaDoc của `ScheduledThreadPoolExecutor` còn cung cấp quan hệ **happens-before giữa effects của các lần thực thi liên tiếp của cùng periodic task**, ngay cả khi mỗi lần chạy trên worker thread khác. Tuy vậy:

- Không suy ra nhiều task định kỳ **khác nhau** được serialize.
- Không suy ra state mutable được dùng đồng thời bởi job A và B trở thành thread-safe.
- Không suy ra mỗi lần sẽ bắt đầu chính xác theo wall clock.
- Một lần lỗi dừng chuỗi vẫn cần monitoring.

Nếu cùng một code được schedule **hai lần riêng biệt**, đó là **hai periodic tasks khác nhau** và có thể chạy song song khi pool có nhiều workers. Đừng dựa vào no-overlap guarantee của một schedule để bảo vệ shared state của hai schedules.

## 16. Đồng hồ, period, drift và tác động của lỗi

`scheduleAtFixedRate` và `scheduleWithFixedDelay` nhận **relative delays**, thường phù hợp với cơ chế scheduling dùng thời gian đơn điệu cho khoảng trễ. Chúng không phải cron theo mốc giờ địa phương.

### Fixed rate nếu task chạy lâu

Nếu execution luôn mất nhiều thời gian hơn period, scheduler không thể chạy **chồng** các execution của cùng task để bù. Những lần sau có thể bắt đầu **muộn**, thời gian chờ thực tế rất nhỏ. Nếu một iteration lỗi trong chuỗi này, những lần sau bị suppressed dù trước đó nhiều deadline đã lỡ.

### Fixed delay nếu task chạy lâu

Khoảng delay giữa **lúc kết thúc** một iteration và lúc bắt đầu lần sau vẫn áp dụng; tổng khoảng cách giữa hai lần bắt đầu xấp xỉ **duration iteration + delay**, cộng overhead/scheduling jitter.

### Lỗi làm mất nhịp như thế nào?

Nếu task bất ngờ ném exception tại vòng thứ 5:

- Không có vòng thứ 6 của **cùng schedule**, không có chính sách “tự chờ thêm period rồi retry”.
- `ScheduledFuture` chuyển sang failed done state.
- Nếu muốn chạy lại, phải **tạo schedule mới** sau khi quyết định cách xử lý trạng thái của vòng thứ 5.
- Không có cơ chế mặc định “chạy bù tất cả các lần đã mất” sau khi bạn tạo schedule mới.
- Với business requiring catch-up, cần mô hình **work items/checkpoints** riêng, không suy từ fixed rate rằng dữ liệu nào bị bỏ lỡ sẽ tự được replay.

## 17. Monitoring: làm sao phát hiện job đã ngừng?

Một scheduler sống không chứng minh mỗi job định kỳ đang thực thi. Tối thiểu, mỗi job quan trọng nên có:

- **Định danh ổn định:** tên job, loại công việc, partition/tenant phù hợp, không log payload nhạy cảm.
- **Last start timestamp** và **last completion timestamp**.
- **Last success timestamp** và **last failure timestamp** tách riêng.
- **Consecutive failures** và tổng failure count, phân loại retryable/fatal.
- **Current ScheduledFuture**: canceled, done hoặc vẫn active.
- **Execution duration**, queue delay / schedule lag nếu cần SLA.
- **Số lần restart** và lý do, tránh restart storm.
- **Age của dữ liệu đầu ra**: job chạy nhưng không tạo tiến triển cũng phải được phát hiện.

Với những trường hợp logic bắt exception rồi return, Future **vẫn có thể active** dù business operation đã thất bại nhiều vòng. Chỉ kiểm tra `future.isDone()` là chưa đủ; phải theo dõi **business success metric** từ code thực thi.

### Probe Future không chặn thread

```java
void inspect(String jobName, ScheduledFuture<?> future) {
    if (!future.isDone()) {
        return; // Periodic task có thể đang hoạt động bình thường.
    }
    try {
        future.get(); // Đã done, không đợi vô hạn.
    } catch (CancellationException e) {
        recordCancelled(jobName);
    } catch (ExecutionException e) {
        recordFailed(jobName, e.getCause());
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
}
```

Đây là **method minh họa**, với các phương thức `recordCancelled`/`recordFailed` và imports của `java.util.concurrent` do ứng dụng định nghĩa. `Future.get` sau `isDone` phù hợp với `ScheduledFutureTask` chuẩn; nếu dùng custom Future, đánh giá contract riêng.

**Không gọi `future.get()` không timeout trên periodic Future active** trong health-check thread hoặc scheduler worker vì có thể chặn vô thời hạn. Đối với một controller định kỳ, nên lưu các handle Future và kiểm tra trạng thái không blocking.

### Khi job hoạt động nhưng đứng mãi

Nếu task **bị treo trong một iteration** mà không ném exception, Future có thể vẫn `isDone()==false` và không có lần chạy sau (vì iteration hiện tại chưa kết thúc). Cần **heartbeat, duration threshold, timeout của I/O, stack/thread diagnostics** để phân biệt “vẫn active” với “stuck”. `Future.isDone()==false` không đủ để khẳng định scheduler đang tiến triển đúng.

## 18. Điều gì xảy ra nếu tự động restart?

Một watchdog có thể phát hiện Future failed rồi tạo schedule mới, nhưng phải làm cẩn thận:

1. **Xác nhận trạng thái thật:** inspect Future đã done, lấy cause; phân biệt failed/canceled/shutdown.
2. **Kiểm tra chính sách restart:** lỗi là transient hay permanent/invariant corruption? Nếu permanent, cần dừng và alert.
3. **Giới hạn lần thử:** áp dụng backoff, jitter có kiểm soát, threshold/consecutive failure breaker; tránh tạo hàng trăm schedules mới trong một phút.
4. **Không tạo duplicates:** nếu scheduler hiện đã có một schedule khác cho cùng invariant, restart mới có thể tạo hai jobs cùng chạy. Cần ownership/registry và thao tác compare-and-swap trên handle hoặc lifecycle coordinator.
5. **Không tin rằng Future failed = side effect đã rollback:** kiểm tra transaction/checkpoint, idempotency và in-flight state.
6. **Không restart sau shutdown có chủ đích:** `isShutdown()`/policy vận hành phải được xét.
7. **Kiểm soát metrics và cảnh báo:** restart liên tục có thể che lỗi gốc; track số lần, cause và last healthy interval.
8. **Đánh giá race giữa watcher/restart:** nếu nhiều watchdog cùng phát hiện failure, chỉ một bên được tạo replacement hợp lệ.

Một skeleton ở mức ý tưởng:

```text
if periodicFuture completed exceptionally:
    cause = observe future failure
    if cause recoverable and restart budget available:
        reconcile state, then atomically register a new schedule
    else:
        alert and disable job until repaired
```

Đây là **pseudocode**, không phải Java runnable. Không tự động retry với mọi exception.

### Mất dữ liệu và idempotency

Một job đọc 100 records rồi ghi lần lượt 50 records trước khi lỗi. Tạo lại cùng schedule không có nghĩa các records đầu tiên được xử lý đúng một lần. Phải có transaction, checkpoint, idempotency hoặc deduplication để bảo vệ side effects. Scheduler chỉ điều khiển **khi nào chạy code**, không quản lý durability của data pipeline.

## 19. Shutdown policy của ScheduledThreadPoolExecutor

`ScheduledThreadPoolExecutor` có chính sách riêng cho task đã lên lịch khi executor shutdown:

- `setContinueExistingPeriodicTasksAfterShutdownPolicy(boolean)` quyết định các **periodic tasks đã tồn tại** có được tiếp tục sau `shutdown()` hay không (mặc định **false**).
- `setExecuteExistingDelayedTasksAfterShutdownPolicy(boolean)` quyết định các task **delayed one-shot** đã được xếp lịch có chạy sau `shutdown()` hay không (mặc định **true**).
- `setRemoveOnCancelPolicy(boolean)` quyết định có cố loại task đã bị cancel ra khỏi work queue ngay hay không (mặc định thường **false** trong Java 17; kiểm tra JDK version/implementation khi dùng).

Cần hiểu **shutdown** và **exception** là hai nguyên nhân khác nhau khiến periodic task không còn chạy. `shutdownNow()` còn cố ngắt các task đang chạy, trả những task đang chờ và không cam kết mọi side effect đã dừng.

### Vì sao shutdown policy liên quan debugging?

Nếu job không chạy lần tiếp theo sau khi một component gọi `scheduler.shutdown()`, đừng vội kết luận nó đã ném exception. Phải xem `isShutdown/isTerminated`, cancellation và outcome của Future.

Ví dụ:

```java
ScheduledThreadPoolExecutor scheduler = new ScheduledThreadPoolExecutor(2);
scheduler.setRemoveOnCancelPolicy(true);
// Sử dụng scheduler rồi chủ động shutdown theo ownership.
```

Đây là đoạn minh họa trong method, cần import `ScheduledThreadPoolExecutor`. `setRemoveOnCancelPolicy(true)` giúp tránh giữ những delayed tasks đã cancel trong queue lâu không cần thiết, nhưng không làm công việc đang chạy dừng ngay lập tức.

**Lifecycle ownership:** ai tạo scheduler thường phải chịu trách nhiệm shutdown nó. Không gọi shutdown pool dùng chung từ một iteration hay một business method không sở hữu lifecycle.

## 20. Một chuỗi periodic khác một tập task one-shot

Nhiều người cố mô phỏng periodic work bằng việc một task tự gọi `scheduler.schedule(this, delay, unit)` ở cuối:

```java
// Mô hình minh họa, bỏ qua các chi tiết lifecycle:
void runAndReschedule() {
    try {
        doWork();
    } finally {
        scheduler.schedule(this::runAndReschedule, 1, TimeUnit.SECONDS);
    }
}
```

Đây là **method minh họa** với `scheduler` và `doWork` ở ngữ cảnh khác, không phải chương trình production. Tự reschedule trong finally ngay cả sau lỗi có thể tạo chuỗi mới **bất chấp failure policy**. Nếu scheduler shutdown, `schedule` có thể reject; nếu có retry ở nơi khác, có thể tạo duplicates; nếu task lỗi nghiêm trọng, tự chạy lại có thể phá invariant.

Một chuỗi `ScheduledFuture` periodic do API quản lý có semantics cancellation/error suppression rõ; **chuỗi one-shot tự reschedule** lại cần tự quản lý toàn bộ:

- Lỗi và quyết định tiếp tục/dừng.
- Giới hạn số lần retry và backoff.
- Future/handle của lần sắp chạy tiếp.
- Race với shutdown/cancel.
- Không tạo nhiều schedules song song.
- Kết quả/metrics của từng iteration.

Đừng đổi từ periodic API sang self-rescheduling chỉ để “né” exception suppression nếu chưa thiết kế đầy đủ lifecycle.

## 21. Kiểm chứng exception mà không làm scheduler “im lặng”

### Log ở đúng tầng

Có ba vị trí hữu ích:

1. **Ngay trong iteration:** bắt lỗi có thể phục hồi, ghi metric/cause, quyết định return hay rethrow.
2. **Ở ScheduledFuture observer:** khi Future done, `get()` để biết terminal failure/cancellation.
3. **Ở worker/executor-level instrumentation:** đo thời gian, số lần chạy, queue, afterExecute, nhưng phải hiểu wrapper Future và điều kiện isDone.

Đừng chỉ dựa vào `Thread.UncaughtExceptionHandler`: với scheduled task được wrapper bằng `ScheduledFutureTask`, throwable có thể được lưu trong Future mà không thoát khỏi worker như một uncaught exception thông thường.

### Log không được nuốt lỗi gốc

Nếu phần logging ném exception mới trong khi bạn xử lý lỗi gốc, outcome của task có thể phản ánh lỗi logging thay vì lỗi nghiệp vụ ban đầu. Hãy khiến instrumentation **exception-safe**, giới hạn thời gian I/O và tránh log dữ liệu bí mật.

### Phân biệt một lần iteration thất bại với chuỗi dừng

Nếu iteration catch và return, metric `iterationFailures++` tăng nhưng `ScheduledFuture.isDone()` vẫn false. Nếu iteration throw ra, Future completed exceptionally và `lastTerminalCause` xuất hiện. Đây là hai loại alert khác nhau: **chuỗi vẫn chạy nhưng kết quả xấu**, so với **chuỗi đã chấm dứt**.

## 22. Trường hợp dễ nhầm liên quan thời gian

### Timeout của get không phải timeout của task

`future.get(100, TimeUnit.MILLISECONDS)` chỉ giới hạn **thời gian người gọi chờ completion**. Nó không áp thời hạn cứng cho nội dung `run()`. Nếu iteration đang block I/O 30 giây, một gọi get timeout 100 ms không làm I/O tự dừng.

Muốn giới hạn một iteration, phải thiết kế timeout ở các I/O operations, cancellation có interrupt support, deadline trong logic hoặc separate coordination. Không chạy periodic task mãi mà không có liveness metrics.

### Fixed rate không “chạy bù” đồng thời

Nếu pool bận, fixed-rate task có thể trễ. Những lần chạy tiếp theo không overlap với lần trước của cùng task. Không giả định 1.000 iteration diễn ra đúng một giây nếu period=1ms trong môi trường tải cao.

### Một lỗi được catch không tự điều chỉnh lịch

Nếu code xử lý một transient exception rồi return bình thường, fixed rate/delay vẫn tiếp tục theo quy tắc timing ban đầu. Nó **không tự tăng backoff** dựa trên số lần lỗi; nếu muốn exponential backoff, phải tự thiết kế một state machine/scheduling strategy phù hợp.

### Lỗi đầu vào lặp lại

Nếu cùng một item xấu xuất hiện ở mỗi iteration và bạn luôn catch rồi return, scheduler sẽ “sống” nhưng công việc có thể thất bại ở mọi lần. Cần quarantine/dead-letter, alert theo consecutive failures, kiểm tra dữ liệu xấu và không để retry storm.

## 23. Java Memory Model và quan hệ happens-before

Một vấn đề độc lập với exception là **memory visibility** giữa các threads.

`ScheduledThreadPoolExecutor` quy định các lần thực thi kế tiếp của **cùng periodic task** không overlap, và effects của lần thực thi trước *happen-before* effects của lần sau, dù chạy trên worker khác. Điều này giúp việc mang state giữa các iteration thuộc **cùng schedule** có cơ sở memory-ordering phù hợp.

Tuy nhiên:

- **Nhiều periodic tasks khác nhau** không tự có cùng thứ tự HB nếu cùng đọc/ghi state.
- Một object shared mutable có thể bị thread khác thay đổi trong lúc job chạy; vẫn cần lock/atomic/immutable state thích hợp.
- `Future.get()` là ranh giới outcome/completion của Future; với periodic task vẫn active, bạn không thể chờ nó bằng `get()` rồi nghĩ một iteration đơn lẻ đã hoàn tất.
- `CountDownLatch`/`AtomicInteger` trong demo cho phép main quan sát tiến triển qua các primitive có memory effects rõ.
- Không dùng `Thread.sleep` làm cơ chế publication/happens-before.

**Đừng nhầm** nguyên tắc no-overlap của cùng periodic task với transaction trên nhiều hệ thống bên ngoài: database/file/network vẫn cần consistency protocol riêng.

## 24. Common pitfalls — lỗi thường gặp và cách sửa

1. **“RuntimeException sẽ bị bỏ qua, scheduler vẫn chạy chu kỳ sau.”** Sai với `scheduleAtFixedRate`/`scheduleWithFixedDelay`: exception thoát ra suppress những lần sau.
2. **“Chỉ fixed rate mới bị dừng; fixed delay thì tự retry.”** Sai: cả hai có cùng suppression rule.
3. **“Future.get() sau scheduleAtFixedRate sẽ trả kết quả của lần chạy đầu.”** Sai: periodic Future active không trả về bình thường.
4. **“isDone() == true nghĩa là iteration cuối thành công.”** Sai: periodic done thường do cancel hoặc lỗi.
5. **“Chỉ cần sau 2 giây counter vẫn bằng 1 là chứng minh không chạy tiếp.”** Test timing có thể flaky; dùng Future failed outcome + contract.
6. **“Bắt Throwable rồi bỏ qua để giữ job chạy là giải pháp an toàn.”** Có thể che JVM fatal error và state corruption.
7. **“Catch exception rồi return là business task đã thành công.”** Sai: cần metrics về failure/success của từng iteration.
8. **“Exception của task định kỳ sẽ luôn hiển thị qua UncaughtExceptionHandler.”** Không; scheduled future wrapper thường lưu lỗi.
9. **“afterExecute Throwable sẽ khác null khi periodic task throw.”** Không với `ScheduledThreadPoolExecutor` chuẩn: sau scheduled wrappers, tham số Throwable luôn null theo JavaDoc.
10. **“Trong afterExecute cứ gọi future.get() là sẽ xem lỗi.”** Sai: nếu periodic task đang active, get có thể block vô hạn. Phải kiểm tra `isDone()`.
11. **“Một schedule có hai workers nên hai iteration cùng job sẽ overlap.”** Không theo contract của ScheduledThreadPoolExecutor.
12. **“Hai schedules khác nhau không overlap vì dùng cùng pool.”** Sai: pool có thể chạy chúng song song nếu đủ workers.
13. **“Future.get(timeout) làm iteration bị cancel khi hết timeout.”** Sai: chỉ caller ngừng chờ.
14. **“cancel(true) đảm bảo external side effect đã dừng/rollback.”** Sai: interrupt cần task hợp tác.
15. **“Scheduler vẫn chạy task khác nên job tôi quan tâm chắc khỏe.”** Sai: failure thuộc từng periodic Future.
16. **“Cứ tự động schedule lại task sau lỗi là an toàn.”** Có thể tạo duplicates/restart storm hoặc chạy lại operation không idempotent.
17. **“Một lần lỗi có nghĩa mọi dữ liệu lần đó được rollback.”** Sai: side effects trước exception có thể đã commit.
18. **“Fixed rate chạy bù tất cả missed ticks cùng lúc.”** Sai: không overlap các iteration của cùng task.
19. **“shutdown() không ảnh hưởng periodic jobs đã xếp lịch.”** Sai với policy mặc định của ScheduledThreadPoolExecutor.
20. **“Đặt Thread.sleep trong Runnable là cách điều phối period.”** Không cần và thường làm tăng drift/block worker; dùng scheduling API theo contract.
21. **“Cần một task mới riêng cho mỗi retry nhưng không cần lưu handle.”** Sai: không có handle sẽ khó cancel, monitor và tránh duplicates.
22. **“Nếu isDone=false thì không thể có lỗi.”** Sai: iteration có thể bắt lỗi rồi return bình thường, hoặc bị treo.
23. **“Lỗi do logging không thể thay đổi trạng thái schedule.”** Sai: logging ném unchecked exception ra ngoài Runnable cũng có thể suppress.
24. **“newScheduledThreadPool(4) có nghĩa một periodic task chạy bốn phiên bản song song.”** Sai: core pool size giới hạn concurrent tasks khác nhau, không nhân bản cùng một schedule.

## 25. Checklist thiết kế production

Khi triển khai một periodic job trong Java SE, cần trả lời:

- **Ý nghĩa công việc:** job có cần chạy đúng từng tick hay chỉ cần định kỳ làm mới trạng thái?
- **Timing:** fixed rate hay fixed delay; period, initialDelay, jitter và deadline thế nào?
- **Failure policy:** ngoại lệ nào được catch rồi tiếp tục, ngoại lệ nào phải dừng/alert?
- **Dữ liệu:** nếu iteration thất bại giữa chừng, state/output có còn nhất quán không?
- **Retry:** giới hạn số lần, backoff, idempotency, replay và checkpoint ra sao?
- **Observability:** có last success, last error, consecutive failures, task duration, lag, Future state?
- **Termination:** có chủ sở hữu scheduler, shutdown policy, deadline và cancellation rõ?
- **Overlap:** cùng logic có được schedule hai lần từ hai components khác nhau không?
- **Concurrency:** những schedules khác có chia sẻ mutable state không?
- **Timeout:** từng I/O operation có timeout, task không block vô hạn?
- **Monitoring:** observer có tránh gọi get blocking trên periodic Future active không?
- **Testing:** dùng latch/Future/timeout, có test exception đầu tiên, exception ở vòng thứ N, cancel, shutdown, restart và retry?
- **Compatibility:** JDK 17+ API có sẵn trên môi trường build/runtime không?

Tất cả các câu trả lời nên biến thành contract được test/giám sát, thay vì chỉ để một exception ném ra rồi hy vọng schedule tiếp tục.

## 26. Bài tập tự luyện

**Bài tập 1 — Fixed rate dừng sau vòng 2:** thay đổi demo để iteration #1 chạy bình thường và #2 ném `IllegalStateException`. Dùng `Future.get(timeout)` xác nhận cause và counter cuối cùng bằng 2. Không dùng `Thread.sleep` để kiểm thử.

**Bài tập 2 — Fixed delay tiếp tục sau một transient failure:** viết một `Runnable` chạy 4 vòng, vòng #2 bắt một `RetryableException` rồi return; dùng `CountDownLatch(4)` xác nhận 4 vòng hoàn thành. Đếm **business successes** riêng với **iteration attempts**.

**Bài tập 3 — Observer Future:** xây một method `inspect(ScheduledFuture<?>)` không blocking; nếu future not done, return; nếu done, phân loại `CancellationException`/`ExecutionException`. Gọi inspect trên một Future còn active và một Future failed.

**Bài tập 4 — Restart budget:** tạo một controller chỉ cho phép restart sau khi future failed và sau delay có backoff. Viết test sao cho hai observer không tạo hai replacement cùng lúc. Không dùng restart khi cause là invariant violation.

**Bài tập 5 — Side effect:** mô phỏng việc ghi 3 records, lỗi sau record #2 rồi retry. Chứng minh tại sao cần idempotency key hoặc commit boundary để tránh xử lý record #1/#2 hai lần.

**Bài tập 6 — Monitoring lỗi bị bắt:** nếu Runnable luôn catch exception rồi return, Future vẫn active. Thiết kế counter `consecutiveFailures` và `lastSuccessNanos` để health check phát hiện job không tạo tiến triển dù schedule vẫn sống.

## 27. Câu hỏi ôn tập và đáp án

**Câu 1.** `scheduleAtFixedRate()` có tự chạy iteration kế tiếp khi iteration trước ném RuntimeException ra ngoài không?  
**Đáp án:** Không. Các lần tiếp theo của cùng periodic schedule bị suppressed; Future completed exceptionally.

**Câu 2.** `scheduleWithFixedDelay()` có ngoại lệ khác fixed rate về failure suppression không?  
**Đáp án:** Không. Nó khác cách tính thời điểm chạy kế tiếp, nhưng có cùng quy tắc exception dừng các lần sau.

**Câu 3.** Làm sao lấy nguyên nhân gốc của periodic task đã thất bại?  
**Đáp án:** Gọi `ScheduledFuture.get()` trên Future đã done; nó ném `ExecutionException`, đọc `getCause()`.

**Câu 4.** Vì sao không gọi `future.get()` vô điều kiện trong `afterExecute`?  
**Đáp án:** Khi periodic task còn active, Future chưa done, get có thể block vô hạn trên worker; phải kiểm tra `future.isDone()`.

**Câu 5.** `afterExecute(r, t)` của `ScheduledThreadPoolExecutor` có luôn nhận Throwable khi scheduled Runnable ném lỗi không?  
**Đáp án:** Không. `ScheduledThreadPoolExecutor` bọc task trong `ScheduledFuture`, JavaDoc ghi `t` luôn null; lỗi đọc qua Future.

**Câu 6.** Khi một scheduled task ném lỗi, mọi scheduled tasks khác trên cùng pool có bị dừng không?  
**Đáp án:** Không mặc định. Chuỗi của task lỗi bị suppressed; các schedules khác có thể tiếp tục chạy nếu executor hoạt động.

**Câu 7.** Vì sao `isDone()` true chưa chứng minh task thành công?  
**Đáp án:** Với periodic task, done có thể do failure hoặc cancellation; phải phân tích outcome.

**Câu 8.** Nếu Runnable catch một transient exception rồi return, scheduler có tiếp tục không?  
**Đáp án:** Có thể tiếp tục theo chu kỳ định nghĩa, vì exception không thoát ra; cần ghi metrics riêng cho iteration failed.

**Câu 9.** Có nên catch toàn bộ Throwable để ngăn schedule dừng không?  
**Đáp án:** Không. Những lỗi nghiêm trọng như OutOfMemoryError/invariant corruption không nên bị che và tiếp tục mù quáng.

**Câu 10.** `Future.get(1, SECONDS)` ném TimeoutException trên periodic task còn active có nghĩa job đã lỗi không?  
**Đáp án:** Không. Nó chỉ nói caller không thấy Future kết thúc trong deadline; periodic Future hoạt động bình thường thường không complete.

**Câu 11.** Nếu fixed-rate task chạy 500ms với period 100ms, scheduler có chạy năm bản của cùng task đồng thời không?  
**Đáp án:** Không. Những lần của cùng periodic task không overlap; các lần sau có thể bắt đầu muộn.

**Câu 12.** `cancel(false)` có ngăn mọi lần future chưa bắt đầu không, và có ép iteration đang chạy dừng ngay không?  
**Đáp án:** Hủy ngăn những lần kế tiếp theo contract; `false` không yêu cầu interrupt iteration đang chạy, nên không hứa dừng ngay lập tức.

**Câu 13.** Sau khi một job failed, tạo schedule mới đã đảm bảo mọi dữ liệu hợp lệ chưa?  
**Đáp án:** Chưa. Cần reconcile/checkpoint/idempotency, kiểm soát duplicates, restart budget và phân tích nguyên nhân.

**Câu 14.** `shutdown()` với ScheduledThreadPoolExecutor có thể làm periodic task ngừng theo default policy không?  
**Đáp án:** Có. Default `continueExistingPeriodicTasksAfterShutdownPolicy` là false.

**Câu 15.** Một job luôn catch lỗi và return nên Future `isDone()==false`; có chắc job khỏe không?  
**Đáp án:** Không. Nó có thể thất bại mỗi iteration nhưng vẫn tiếp tục; cần monitor last success/failure, progress và output.

**Câu 16.** Một iteration không ném lỗi nhưng bị block vô hạn: Future có thể như thế nào?  
**Đáp án:** Có thể vẫn not done, các lần tiếp theo không chạy do iteration hiện tại chưa kết thúc; cần duration/timeout/heartbeat monitoring.

## 28. Tài liệu tham khảo chính thức

- [Java SE 17 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): hợp đồng của `scheduleAtFixedRate` và `scheduleWithFixedDelay`, exception suppression, periodic Future.get.
- [Java SE 17 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html): scheduling, no-overlap, happens-before giữa successive executions, `afterExecute`, shutdown và cancellation policies.
- [Java SE 17 — ScheduledFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html): Future + Delayed semantics.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, `cancel`, `isDone`, memory consistency.
- [Java SE 17 — Executors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): `newScheduledThreadPool` và các factory methods.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối kiểm thử/đồng bộ với happens-before.
- [Java SE 17 — ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html): wrapper của failure từ Future.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, interrupts và happens-before.

**Kết luận:** đối với các task định kỳ Java `scheduleAtFixedRate()` hoặc `scheduleWithFixedDelay()`, **exception thoát khỏi một lần chạy làm các lần chạy tiếp theo của chính task đó bị suppressed**. `ScheduledFuture` giúp quan sát terminal cause; còn muốn scheduler tiếp tục sau lỗi dự kiến, code phải **catch/record và return bình thường** theo một policy đúng về dữ liệu. Đừng gọi `Future.get()` vô điều kiện trên periodic Future còn active; giám sát business progress, duration và lifecycle tách biệt khỏi trạng thái “pool còn sống”.