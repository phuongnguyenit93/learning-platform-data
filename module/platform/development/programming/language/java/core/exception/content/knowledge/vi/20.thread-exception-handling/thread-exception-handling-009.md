# Lỗi trong tác vụ định kỳ và ảnh hưởng tới các lần chạy tiếp theo (Java)

## 1. Tình huống: một lần chạy lỗi, lịch chạy còn tiếp tục không?

Một tác vụ định kỳ (*periodic task*) được cấu hình chạy lặp lại sau một khoảng thời gian, chẳng hạn làm mới cache, dọn dữ liệu tạm, đồng bộ trạng thái hoặc gửi báo cáo. Nếu ở một lần thực thi tác vụ ném exception, điều gì xảy ra với các lần tiếp theo?

Trong Java, câu trả lời **phụ thuộc API lập lịch và việc exception có thoát khỏi thân tác vụ hay không**. Đặc biệt, với `ScheduledExecutorService.scheduleAtFixedRate(...)` và `scheduleWithFixedDelay(...)`, hợp đồng Java quy định:

> Nếu **bất kỳ lần thực thi** tác vụ định kỳ nào gặp exception **không được xử lý và thoát khỏi tác vụ**, các lần thực thi tiếp theo **bị ngăn lại** (*subsequent executions are suppressed*).

Đây là lý do một job đang chạy đều đặn có thể **im lặng ngừng hoạt động sau một lỗi duy nhất**, dù `ScheduledExecutorService` còn sống và các công việc khác vẫn tiếp tục. Caller không tự bắt được lỗi chỉ bằng một `try/catch` bọc lời gọi lập lịch; lỗi phát sinh về sau trên thread của executor.

Bài này làm rõ cơ chế, điểm khác nhau giữa hai kiểu lập lịch, cách quan sát và xử lý exception, khi nào tiếp tục/hủy tác vụ, cũng như các giới hạn về trạng thái, retry và concurrency.

## 2. Phân biệt ba sự kiện riêng biệt

Khi xét một tác vụ định kỳ, cần tách biệt:

1. **Lập lịch thành công:** lệnh `scheduleAtFixedRate` hoặc `scheduleWithFixedDelay` trả về một `ScheduledFuture<?>`. Điều này chỉ xác nhận yêu cầu đã được nhận, **không** bảo đảm mọi lượt tương lai sẽ thành công.
2. **Một lượt chạy thành công hoặc lỗi:** executor thực thi `Runnable.run()` trên một worker thread. Nếu `run()` trả về bình thường, lịch có thể tiếp tục. Nếu một `Throwable` thoát ra khỏi lượt chạy, future của lịch sẽ chuyển sang trạng thái hoàn tất do lỗi theo hợp đồng các phương thức định kỳ và những lần kế tiếp bị ngăn.
3. **Người gọi quan sát kết quả:** `ScheduledFuture.isDone()`, `isCancelled()`, `get()`, log/metric hoặc một kênh báo lỗi riêng mới giúp bộ phận giám sát biết tác vụ đang sống hay đã dừng.

Không nên suy ra lịch còn hoạt động chỉ vì gọi `scheduleAtFixedRate(...)` không ném lỗi ngay lúc tạo lịch. Cũng không nên suy ra toàn bộ scheduler đã chết chỉ vì **một lịch** dừng do exception.

## 3. Hai kiểu lập lịch định kỳ quan trọng

### `scheduleAtFixedRate`: chu kỳ tính theo thời điểm dự kiến

Chữ ký:

```java
ScheduledFuture<?> scheduleAtFixedRate(
    Runnable command,
    long initialDelay,
    long period,
    TimeUnit unit);
```

Đây là **chữ ký API để đọc hiểu**, không phải đoạn mã độc lập. Ví dụ `initialDelay = 0`, `period = 1 SECOND`: lịch dự kiến tại các mốc khoảng `t0, t0+1s, t0+2s, ...`, không phải luôn đợi đúng một giây sau khi lượt trước kết thúc.

Nếu một lượt chạy lâu hơn chu kỳ, lần kế tiếp có thể bắt đầu trễ và có thể chạy gần như ngay sau lượt trước để bắt kịp mốc dự kiến. **Các lần thực thi của cùng một tác vụ định kỳ không chạy chồng lấn nhau**, dù executor có nhiều worker; các tác vụ định kỳ **khác nhau** vẫn có thể chạy song song. Theo hợp đồng của `ScheduledThreadPoolExecutor`, các hiệu ứng của lượt chạy trước *happens-before* lượt chạy tiếp theo của cùng tác vụ định kỳ.

**Khi exception thoát khỏi lượt chạy:** những lần thực thi tiếp theo của **chính lịch đó** sẽ bị ngăn lại, bất kể các mốc định kỳ khác đã tới.

### `scheduleWithFixedDelay`: độ trễ tính sau khi lượt trước kết thúc

Chữ ký:

```java
ScheduledFuture<?> scheduleWithFixedDelay(
    Runnable command,
    long initialDelay,
    long delay,
    TimeUnit unit);
```

Ví dụ công việc chạy trong `300 ms` và `delay = 1 SECOND` thì lần sau được phép bắt đầu sau khoảng một giây kể từ khi lần trước **kết thúc**, tức khoảng `1,3 giây` từ lúc lần trước bắt đầu (bỏ qua trễ lên lịch). Nếu công việc tốn `3 giây`, độ dài giữa hai lần bắt đầu có thể khoảng `4 giây`.

**Khi exception thoát khỏi lượt chạy:** những lần thực thi tiếp theo cũng bị ngăn. Đây là điểm **giống nhau** cốt lõi của cả fixed-rate và fixed-delay.

| Thuộc tính | `scheduleAtFixedRate` | `scheduleWithFixedDelay` |
| --- | --- | --- |
| Thời điểm lần sau | Theo các mốc dự kiến cách nhau `period` | Sau khi lượt trước kết thúc, đợi thêm `delay` |
| Lượt xử lý lâu hơn chu kỳ | Lượt kế tiếp có thể chạy muộn, rồi bắt đầu gần như ngay | Luôn có khoảng chờ `delay` giữa lúc kết thúc và lần bắt đầu kế tiếp |
| Cùng một tác vụ chạy chồng lấn? | Không | Không |
| Exception thoát ra từ một lượt | Ngăn những lần tiếp theo | Ngăn những lần tiếp theo |
| Hợp với | Nhịp lấy mẫu/làm việc theo tần suất tương đối cố định | Polling, dọn dẹp hoặc tác vụ muốn nghỉ sau mỗi lần hoàn tất |

Hai cơ chế trên dùng **thời gian tương đối** và không tự có quy tắc cron, múi giờ hay xử lý giờ mùa hè. Nếu yêu cầu “8 giờ sáng mỗi ngày theo lịch địa phương”, cần thiết kế lịch theo clock/calendar với API thích hợp.

Các tham số `period` và `delay` dành cho tác vụ định kỳ phải **lớn hơn 0**; đầu vào không hợp lệ có thể gây `IllegalArgumentException` ngay trong **luồng gọi lập lịch**, khác với lỗi trong một lần `run()` chạy về sau.

## 4. Vì sao exception lại dừng lịch?

Với `ScheduledThreadPoolExecutor` (triển khai thông dụng của `ScheduledExecutorService`), mỗi lịch định kỳ được quản lý bằng một đối tượng future gắn với trạng thái thực thi. Khi `Runnable` ném exception không được bắt ở bên trong:

- Lượt hiện tại kết thúc bất thường.
- Future của lịch được đánh dấu **hoàn tất do exception** (*exceptional completion*).
- Executor **không đưa cùng lịch đó vào hàng đợi cho lượt tiếp theo**.
- Người gọi có thể lấy nguyên nhân thông qua `ScheduledFuture.get()`; vì lỗi đã làm future hoàn tất, `get()` ném `ExecutionException` có `getCause()` là nguyên nhân của lượt chạy thất bại.

Với lịch định kỳ không kết thúc và đang hoạt động bình thường, `future.get()` **không trả về giá trị thành công sau mỗi lượt**. Nó có thể chờ mãi cho đến khi lịch bị hủy hoặc gặp lỗi (hoặc thao tác chờ bị interrupt). Do đó, tuyệt đối không dùng `get()` không có timeout ở thread quan trọng chỉ để “xem lần vừa chạy có tốt không”.

`Future.isDone() == true` có thể do **lỗi** hoặc **đã hủy**, nên cần kiểm tra `isCancelled()` và nguyên nhân khi thích hợp. `isDone() == false` không đủ để bảo đảm tác vụ đang hoạt động lành mạnh: lịch có thể chưa tới lượt, đang chạy lâu, nghẽn worker, hoặc phụ thuộc bị treo.

## 5. Ví dụ Java 17+ chạy được: một lịch dừng, lịch kia tiếp tục

Chương trình dưới đây tạo scheduler có hai worker và hai tác vụ định kỳ:

- **Tác vụ A:** lần đầu thành công, lần thứ hai ném `IllegalStateException` ra khỏi `Runnable`. Lịch A dừng; `get()` báo `ExecutionException`.
- **Tác vụ B:** lần đầu giả lập lỗi nhưng **bắt và ghi nhận lỗi bên trong**; nó hoàn tất bình thường và tiếp tục ít nhất ba lượt, sau đó main hủy để kết thúc ví dụ.
- **Tác vụ độc lập:** được lập lịch sau lỗi của A để chứng minh scheduler vẫn thực thi việc khác.

Tạo file `PeriodicTaskFailureDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicTaskFailureDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newScheduledThreadPool(2);
        AtomicInteger failedRuns = new AtomicInteger();
        AtomicInteger resilientRuns = new AtomicInteger();
        AtomicInteger handledErrors = new AtomicInteger();
        CountDownLatch thirdRun = new CountDownLatch(1);
        ScheduledFuture<?> resilient = null;

        try {
            ScheduledFuture<?> failed = scheduler.scheduleAtFixedRate(() -> {
                int n = failedRuns.incrementAndGet();
                if (n == 2) {
                    throw new IllegalStateException("second execution failed");
                }
            }, 0, 20, TimeUnit.MILLISECONDS);

            try {
                failed.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                System.out.println("FAILED: "
                        + ex.getCause().getClass().getSimpleName());
            }
            System.out.println("FAILED RUNS: " + failedRuns.get());
            System.out.println("FAILED FUTURE DONE: " + failed.isDone());

            resilient = scheduler.scheduleWithFixedDelay(() -> {
                int n = resilientRuns.incrementAndGet();
                try {
                    if (n == 1) {
                        throw new IllegalArgumentException("recoverable example");
                    }
                } catch (IllegalArgumentException ex) {
                    handledErrors.incrementAndGet();
                } finally {
                    if (n >= 3) {
                        thirdRun.countDown();
                    }
                }
            }, 0, 20, TimeUnit.MILLISECONDS);

            if (!thirdRun.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("resilient task did not run");
            }
            resilient.cancel(false);

            System.out.println("HANDLED ERRORS: " + handledErrors.get());
            System.out.println("RECOVERED AND KEPT RUNNING: "
                    + (resilientRuns.get() >= 3));

            ScheduledFuture<String> independent = scheduler.schedule(
                    () -> "still active", 0, TimeUnit.MILLISECONDS);
            System.out.println("OTHER TASK: "
                    + independent.get(5, TimeUnit.SECONDS));
        } finally {
            if (resilient != null) {
                resilient.cancel(false);
            }
            scheduler.shutdownNow();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Scheduler did not terminate in time");
            }
        }
    }
}
```

Lệnh chạy trong thư mục chứa file, với JDK 17 trở lên:

```bash
javac -encoding UTF-8 PeriodicTaskFailureDemo.java
java PeriodicTaskFailureDemo
```

Standard output:

```text
FAILED: IllegalStateException
FAILED RUNS: 2
FAILED FUTURE DONE: true
HANDLED ERRORS: 1
RECOVERED AND KEPT RUNNING: true
OTHER TASK: still active
```

Diễn giải kết quả:

1. `failedRuns` bằng **2** vì exception thoát ra ở lượt thứ hai; executor không lên lịch lượt ba.
2. `failed.get(...)` ném `ExecutionException`. Chương trình lấy `getCause()` để thấy `IllegalStateException` thực tế.
3. `failed.isDone()` trả `true` vì lịch **đã hoàn tất do lỗi**; điều này không có nghĩa tác vụ “thành công”.
4. Lịch `resilient` tự bắt `IllegalArgumentException` rồi kết thúc lượt đầu bình thường. Các lượt tiếp theo vẫn được chạy; `CountDownLatch` giúp ví dụ xác nhận đạt ba lượt mà không phụ thuộc vào `Thread.sleep()`.
5. `resilient.cancel(false)` ngăn lên lịch những lượt sau. Có thể một lượt đã bắt đầu vẫn tiếp tục do `false` không yêu cầu interrupt, nhưng chương trình chỉ kiểm tra điều kiện “đã chạy ít nhất ba lượt”, nên output không phụ thuộc số lần chính xác tại lúc hủy.
6. Tác vụ `independent` vẫn nhận kết quả `still active`, cho thấy lỗi của lịch A **không tự làm scheduler ngừng vận hành**.

`AtomicInteger` giữ bộ đếm an toàn khi đọc từ main và cập nhật trên worker. `CountDownLatch` đồng bộ điều kiện hoàn thành; `get(timeout)` và `await(timeout)` tránh chờ vô hạn trong demo. `shutdownNow()` là yêu cầu dừng và interrupt các worker còn hoạt động; nó không bảo đảm một tác vụ không hợp tác sẽ dừng ngay. Phần `finally` dọn scheduler để chương trình thoát.

Ví dụ chủ động dùng **20 ms** để minh họa nhanh, không coi scheduler là bộ đếm thời gian chính xác đến mili giây. Trên máy quá tải, timeout có thể hết trước khi các tác vụ được chạy; đó là tình huống chờ quá hạn cần xử lý trong ứng dụng thực tế, không làm thay đổi hợp đồng suppression khi task ném lỗi.

## 6. Lỗi thoát ra và lỗi đã được xử lý trong tác vụ khác nhau thế nào?

Điểm quyết định lịch có tiếp tục do lỗi nghiệp vụ hay không là **giá trị trả về của `Runnable.run()`**:

### Exception thoát ra ngoài

```java
Runnable job = () -> {
    loadData();
    saveData(); // Nếu ném RuntimeException không được catch...
};
scheduler.scheduleAtFixedRate(job, 0, 1, TimeUnit.MINUTES);
```

Đây là mảnh minh họa giả định có `ScheduledExecutorService scheduler` và các hàm `loadData()`, `saveData()`. Nếu một exception thoát khỏi `job.run()`, hợp đồng tác vụ định kỳ yêu cầu **ngăn những lần chạy tiếp theo của lịch này**.

### Bắt lỗi dự kiến rồi hoàn tất lượt chạy bình thường

```java
Runnable job = () -> {
    try {
        refreshCache();
    } catch (RecoverableBackendException ex) {
        recordFailure(ex);
        // Lượt này đã thất bại nhưng policy cho phép thử lại ở kỳ sau.
    }
};
scheduler.scheduleWithFixedDelay(job, 0, 30, TimeUnit.SECONDS);
```

Đây cũng là **mảnh minh họa**, với `RecoverableBackendException`, `refreshCache()` và `recordFailure()` là thành phần ứng dụng phải tự định nghĩa. Nếu nhánh `catch` thực thi xong và `run()` trả về bình thường, lịch **có thể tiếp tục** ở kỳ sau. Hành vi đó là quyết định ứng dụng: lỗi tạm thời có thể được ghi nhận và bỏ qua cho lần này, còn lỗi không thể phục hồi nên được báo ra và có thể chủ đích dừng lịch.

Cần đặc biệt chú ý: chính `recordFailure(ex)` cũng có thể ném exception. Nếu logging, metric hoặc callback báo lỗi thất bại và exception mới thoát ra ngoài `run()`, lịch vẫn bị ngăn. Hãy chọn đường giám sát bền vững và xử lý lỗi của đường giám sát theo mức độ quan trọng.

**Không nên bọc toàn bộ tác vụ bằng `catch (Throwable)` rồi bỏ qua mọi lỗi.** `Throwable` gồm `Error` như `OutOfMemoryError`, là tình trạng thường không có cơ sở để tiếp tục sử dụng tài nguyên bình thường. Chỉ bắt loại lỗi mà ứng dụng có chính sách xử lý và khả năng giữ bất biến. Với `InterruptedException`, cần tuân thủ chính sách hủy và trạng thái interrupt riêng.

## 7. Lịch đã lỗi có tự khởi động lại không?

Không. Với `scheduleAtFixedRate` và `scheduleWithFixedDelay`, khi một lượt ném exception thoát ra, **chính đối tượng `ScheduledFuture` của lịch đó chuyển sang trạng thái kết thúc do lỗi**. Executor không tự retry lượt bị lỗi và cũng không tự dựng lịch mới.

Nếu yêu cầu khởi động lại sau một lỗi, ứng dụng phải có chiến lược rõ ràng:

- Cho phép một số lỗi tạm thời **được bắt trong task**, ghi log/metric và để lần chạy theo chu kỳ tiếp theo xử lý lại.
- Nếu cần thay đổi lịch theo số lần thất bại, sử dụng cơ chế **lập lịch lại có điều kiện** (một lần chạy `schedule(...)` rồi chủ động lên lịch lần tiếp) với backoff/jitter thay cho chu kỳ cứng.
- Nếu task đã dừng do lỗi nghiêm trọng, chuyển trạng thái sang `FAILED` và cần hành động vận hành hoặc thay đổi cấu hình; không tự động gọi lịch mới vô hạn.
- Có giám sát tìm những future đã `isDone()` bất thường, tránh tình trạng tác vụ thiết yếu ngừng hoạt động mà không ai biết.

Khi tự lập lịch lại, cần chống trùng: chỉ một scheduler/controller sở hữu lịch, hủy/lưu tham chiếu lịch cũ và tránh việc nhiều callback cùng tạo lịch mới sau một sự cố. Nếu nhiều instance ứng dụng cùng chạy, cần nghĩ đến cơ chế leader election, distributed lock hoặc idempotency phù hợp; `ScheduledExecutorService` tự nó không điều phối các JVM khác nhau.

## 8. Kiểm tra trạng thái và đọc nguyên nhân qua `ScheduledFuture`

Đối tượng `ScheduledFuture<?>` là handle để quản lý và quan sát vòng đời lịch. Một số thuộc tính:

| Lời gọi | Ý nghĩa |
| --- | --- |
| `future.isDone()` | Lịch đã hoàn tất do hủy, lỗi hoặc hình thức kết thúc khác; không đồng nghĩa thành công |
| `future.isCancelled()` | Lịch đã bị hủy |
| `future.cancel(false)` | Yêu cầu hủy những lần chưa chạy; không yêu cầu interrupt lần đang thực thi |
| `future.cancel(true)` | Yêu cầu hủy và **có thể interrupt** lần đang chạy; task phải hợp tác |
| `future.get()` | Với lịch định kỳ khỏe mạnh, thường **không bao giờ trả về bình thường**; khi lỗi ném `ExecutionException`, khi hủy ném `CancellationException` |
| `future.get(timeout, unit)` | Có giới hạn thời gian chờ; `TimeoutException` có thể chỉ phản ánh lịch vẫn đang hoạt động |

Mẫu quan sát *sau khi đã biết future kết thúc*:

```java
if (future.isDone()) {
    if (future.isCancelled()) {
        reportCancelled();
    } else {
        try {
            future.get();
        } catch (ExecutionException ex) {
            reportFailure(ex.getCause());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }
}
```

Đây là mảnh code trong một phương thức có `ScheduledFuture<?> future`, đã import các lớp `java.util.concurrent.*` phù hợp và có các hàm `reportCancelled()`, `reportFailure(Throwable)` do ứng dụng định nghĩa. Cần bảo vệ race do trạng thái hủy và thay đổi kết quả nếu chính hệ thống có nhiều luồng quản lý handle. Nếu `get()` bị hủy sau kiểm tra, nó có thể ném `CancellationException`; ví dụ đã bỏ nhánh đó cho ngắn, còn mã production nên xử lý đầy đủ.

Không nên gọi `future.get()` bên trong **chính một lượt tác vụ định kỳ trên cùng lịch**, vì future chưa kết thúc và có thể tự chờ mình vô thời hạn. Nếu cần xử lý lỗi của từng lượt, hãy ghi nhận nó ngay trong wrapper và dùng hệ thống giám sát riêng.

### `UncaughtExceptionHandler` có nhìn thấy lỗi này không?

Với các task chạy qua `ScheduledThreadPoolExecutor`, executor thường **giữ lỗi vào future**. Vì vậy `Thread.UncaughtExceptionHandler` không phải kênh tin cậy để quan sát mọi thất bại của tác vụ đã lập lịch; lỗi có thể không xuất hiện như một uncaught exception trên worker thread. Đường ổn định là quản lý `ScheduledFuture`, wrapper ghi nhận kết quả từng lượt hoặc kênh giám sát do ứng dụng định nghĩa.

Nếu xây subclass `ScheduledThreadPoolExecutor` và override `afterExecute(Runnable, Throwable)`, lưu ý tham số `Throwable` thứ hai có thể là `null` ngay cả khi task thất bại, do lỗi nằm trong `Future`. Không nên gọi `get()` không điều kiện trên các periodic future chưa `isDone()`; hành động đó có thể block worker của executor.

## 9. Vì sao lỗi một task không đồng nghĩa cả scheduler bị hỏng?

`ScheduledExecutorService` là bộ quản lý **nhiều công việc độc lập**. Một lịch định kỳ lỗi và bị suppression là trạng thái của **handle lịch đó**, không phải mệnh lệnh chung `shutdown()`. Ví dụ có hai job:

- Job A làm mới tỷ giá và gặp một `IllegalStateException` không được bắt;
- Job B dọn dẹp cache bình thường.

Nếu scheduler còn hoạt động và tài nguyên đáp ứng, Job B vẫn được phép thực thi theo lịch của nó. Không được suy luận ngược rằng scheduler hoàn toàn khỏe chỉ vì Job B vẫn chạy: các worker có thể nghẽn, queue tăng hoặc job A đã chết.

Dịch vụ giám sát cần theo dõi **từng lịch** và **pool** riêng. Một số tín hiệu hữu ích:

- Thời điểm gần nhất một lượt bắt đầu/kết thúc;
- Thời điểm thành công cuối cùng;
- Số lỗi liên tiếp, loại lỗi gần nhất và correlation ID;
- `ScheduledFuture.isDone()`, `isCancelled()` cho lịch được kỳ vọng chạy lâu dài;
- Thời lượng một lượt, độ trễ so với lịch dự kiến, worker saturation;
- Số task đang đợi, trạng thái `isShutdown()`/`isTerminated()` của executor.

Không nên đặt tên trạng thái “HEALTHY” chỉ dựa trên việc tiến trình JVM còn sống; một scheduler có thể tồn tại lâu trong khi tất cả periodic job quan trọng đã dừng sau exception.

## 10. So sánh với `java.util.Timer` và `TimerTask`

Java cũ có `java.util.Timer`, hoạt động theo mô hình một thread chạy các `TimerTask` tuần tự trong một Timer. Khi một `TimerTask.run()` ném **unchecked exception** không được xử lý, thread thực thi của `Timer` có thể bị kết thúc; timer không thể tiếp tục lịch như trước và những task khác của **cùng Timer** cũng bị ảnh hưởng.

Điểm này khác đáng kể với `ScheduledThreadPoolExecutor`:

| Trường hợp | `java.util.Timer` | `ScheduledExecutorService` với lịch định kỳ |
| --- | --- | --- |
| Thread thực thi | Một thread cho các task của Timer | Pool gồm một hoặc nhiều worker |
| Lỗi unchecked thoát khỏi một tác vụ | Có thể kết thúc thread Timer, ảnh hưởng toàn bộ các tác vụ cùng Timer | Suppress các lượt sau của **lịch bị lỗi**, không tự dừng các lịch khác |
| Kênh lấy lỗi tác vụ | Không trả handle kiểu `Future` cho từng lượt | `ScheduledFuture` có thể hoàn tất exceptionally |
| Tác vụ lâu | Chặn các task khác trong cùng Timer | Pool có thể cho task khác chạy trên worker khác, tùy kích thước |
| Đề xuất cho mã mới | Thường không phải lựa chọn ưu tiên | Thường phù hợp hơn vì quản lý pool, hủy và future |

Ví dụ `Timer` (mảnh mã trong phương thức; có import `java.util.Timer` và `TimerTask`):

```java
Timer timer = new Timer("legacy-timer", true);
timer.scheduleAtFixedRate(new TimerTask() {
    @Override
    public void run() {
        throw new IllegalStateException("legacy timer task failed");
    }
}, 0L, 1000L);
```

Đây là ví dụ **để phân tích hậu quả**, không nên dùng làm mẫu xử lý lỗi production. Với `Timer`, một exception runtime không được bắt trong task có thể giết thread Timer và khiến những task đã lập lịch sau đó không còn chạy. Nếu sử dụng Timer trong mã cũ, cần xử lý lỗi, quản lý vòng đời và cân nhắc chuyển sang `ScheduledExecutorService` khi phù hợp.

Trong cả hai mô hình, **bắt lỗi có chọn lọc** trong thân tác vụ có thể giúp duy trì việc lập lịch ở lượt sau, nhưng không bảo đảm công việc thật đã hoàn thành đúng.

## 11. Checked exception, unchecked exception và `Error`

`ScheduledExecutorService` nhận `Runnable` cho tác vụ định kỳ. `Runnable.run()` **không khai báo `throws` cho checked exception**. Do đó, phương thức dùng I/O ném `IOException` checked phải xử lý nó trong `run()`:

```java
Runnable job = () -> {
    try {
        refreshFromRemote(); // Có thể ném IOException
    } catch (IOException ex) {
        logTransientFailure(ex);
    }
};
```

Đây là mảnh minh họa cần `java.io.IOException` và các phương thức ứng dụng `refreshFromRemote()`, `logTransientFailure(...)`. Nếu giữ `IOException` trong nhánh `catch` và kết thúc `run()` bình thường, lịch có thể tiếp tục. Nếu cố tình bọc lại bằng `UncheckedIOException` hay `IllegalStateException` **rồi ném ra ngoài**, lịch sẽ bị suppression như các runtime exception khác.

`Error` cũng thuộc `Throwable`. Hợp đồng Java về tác vụ định kỳ dùng ngôn ngữ “execution encounters an exception”; triển khai `ScheduledThreadPoolExecutor` lưu cả thất bại nghiêm trọng từ việc thực thi. Không nên dựa vào việc cố catch mọi `Throwable` để “giữ job còn sống” khi JVM có thể đã thiếu tài nguyên hoặc trạng thái không còn đáng tin.

Tách chính sách:

- **Lỗi có thể phục hồi:** ví dụ một request mạng tạm mất, dữ liệu của lượt này có thể bỏ qua, giữ cache cũ hợp lệ. Ghi nhận rồi kết thúc bình thường nếu đã bảo toàn trạng thái.
- **Lỗi nghiệp vụ/validation:** lỗi cấu hình, không thể giải mã payload, invariant bị vi phạm. Thường phải dừng hoặc cách ly job và cảnh báo, thay vì chạy liên tục làm hỏng dữ liệu.
- **Lỗi hủy/interruption:** có thể cần dừng tác vụ, giải phóng tài nguyên và khôi phục trạng thái interrupt. Không phải mọi `InterruptedException` đều là lỗi tạm thời nên được bỏ qua.
- **Lỗi nghiêm trọng cấp runtime:** báo về cơ chế giám sát hoặc để executor/runtime xử lý theo chính sách vận hành, tránh che bằng vòng lặp retry vô hạn.

## 12. `InterruptedException` và việc hủy lịch

Một tác vụ định kỳ có thể block trên I/O, khóa hoặc các lệnh `sleep`/`wait`. Khi luồng worker bị interrupt, các lời gọi blocking có thể ném `InterruptedException`. Vì `Runnable.run()` không được khai báo checked exception, task cần quyết định xử lý.

Một mảnh xử lý trong `Runnable`:

```java
try {
    waitForWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
```

Đây là mảnh code trong phương thức trả về `void`, với `waitForWork()` do ứng dụng định nghĩa. Nó bảo toàn tín hiệu interrupt để code bên ngoài quan sát nếu thích hợp.

**Bẫy quan trọng:** nếu task chỉ bắt `InterruptedException` rồi **return bình thường** trong khi `ScheduledFuture` của lịch **chưa bị hủy**, lịch định kỳ có thể vẫn được lên lịch cho lượt sau. `return` chỉ kết thúc **lượt hiện tại**, không phải lệnh hủy hợp đồng định kỳ. Muốn hủy toàn bộ lịch, cần gọi `future.cancel(...)` hoặc shutdown/cơ chế kiểm soát lifecycle phù hợp.

`cancel(true)` chỉ yêu cầu interrupt nếu đang chạy và là *best effort*. Task làm I/O không phản hồi interrupt có thể vẫn tiếp tục side effect. `cancel(false)` không yêu cầu interrupt công việc đang thực hiện. Cả hai không tự hoàn tác ghi file, update DB hoặc HTTP request đã xảy ra.

Nếu một task được đánh dấu `isCancelled()`, `get()` ném `CancellationException` thay vì trả báo cáo kết quả thành công; cancellation có ngữ nghĩa khác với exceptional completion do lỗi trong `run()`.

## 13. Tác vụ định kỳ có async bên trong: một ranh giới lỗi nữa

Ví dụ một `Runnable` chỉ **khởi tạo** thao tác bất đồng bộ rồi return:

```java
scheduler.scheduleAtFixedRate(() -> {
    CompletableFuture<Void> action = service.refreshAsync();
    action.whenComplete((value, error) -> {
        if (error != null) {
            reportFailure(error);
        }
    });
}, 0, 1, TimeUnit.MINUTES);
```

Đây là mảnh code có `ScheduledExecutorService scheduler`, đối tượng ứng dụng `service` trả `CompletableFuture<Void>` và hàm `reportFailure(Throwable)`.

Nếu `refreshAsync()` trả về stage bình thường rồi lỗi phát sinh **về sau** khi stage đang chạy, lỗi đó **không thoát trực tiếp khỏi lượt `Runnable.run()`** đã return. Vì vậy lịch ngoài có thể **tiếp tục chạy các lượt sau**, trong khi stage trước đó thất bại. Nếu callback `whenComplete` tự ném exception, stage mà nó trả về có thể hoàn tất exceptionally; nó cũng không tự làm exception nhảy ngược vào stack của `Runnable` đã kết thúc.

Một rủi ro khác là **overlap bất đồng bộ**: executor bảo đảm không chạy chồng lấn **các lượt `Runnable.run()`** của cùng lịch, nhưng khi mỗi lượt chỉ phát một future rồi return, các **công việc async do những lượt đó khởi tạo** vẫn có thể chạy chồng lấn trong hệ thống khác.

Để xử lý, chọn hợp đồng rõ ràng:

1. Đặt giới hạn concurrency/in-flight, ví dụ semaphore hoặc state flag và chắc chắn giải phóng ở mọi đường completion.
2. Dùng scheduling của lượt tiếp theo **sau khi stage trước đã hoàn tất** nếu thật sự muốn không overlap.
3. Theo dõi từng future, ghi lỗi, trạng thái và yêu cầu hủy.
4. Nếu buộc phải chờ `join()`/`get()` trong `Runnable`, biết rằng việc chờ có thể block worker, phát sinh exception wrapper, và cần timeout/cancel phù hợp.

Tương tự, exception xảy ra trong callback trên thread khác không tự lan đến `catch` quanh câu `scheduleAtFixedRate` của caller. Phải truyền kết quả qua future hoặc kênh quan sát đã thiết kế.

## 14. Task chạy một lần khác task định kỳ

`scheduler.schedule(Runnable, delay, unit)` hoặc `schedule(Callable, delay, unit)` tạo tác vụ **một lần**. Nếu tác vụ lỗi, future tương ứng hoàn tất exceptionally nhưng không tồn tại “lần chạy tiếp theo của cùng lịch” để bị suppression. Caller có thể `get()` để lấy kết quả hoặc exception.

Ngược lại, `scheduleAtFixedRate` và `scheduleWithFixedDelay` định nghĩa một chuỗi lặp lại; khi có exception thoát ra thì **chuỗi đó kết thúc**. Đừng nhầm việc tự gọi `schedule(...)` liên tục từ callback với hợp đồng của hai API periodic: hệ thống tự lập lịch lại phải quản lý lỗi, hủy và các lịch trùng theo logic riêng.

Tương tự, `executor.execute(Runnable)` không trả future còn `executor.submit(...)` trả `Future`. Đường ghi nhận ngoại lệ của executor có thể khác nhau giữa hai API. Khi phân tích một hệ thống hiện có, trước hết xác định đúng **phương thức đã dùng**, thay vì áp dụng một câu trả lời chung cho “mọi lỗi ở background thread”.

## 15. Sau exception, dữ liệu đã cập nhật có bị rollback không?

Không. Suppression chỉ dừng **lịch chạy tương lai**. Nó không tự hoàn tác những thay đổi đã làm trong lượt bị lỗi.

Ví dụ mảnh mã:

```java
Runnable job = () -> {
    updateDatabase();       // Có thể đã commit
    sendNotification();     // Có thể lỗi sau khi update
};
```

Đây là minh họa có các hàm ứng dụng `updateDatabase()` và `sendNotification()`. Nếu thao tác DB đã commit rồi `sendNotification()` ném exception, lịch định kỳ có thể bị suppression, **nhưng dữ liệu DB đã commit vẫn còn**. Khi vận hành thử lại, một bản ghi có thể đã được xử lý hoặc thông báo có thể đã được gửi dù không nhận ACK.

Đối với job có side effect:

- Dùng transaction đúng phạm vi cho những thay đổi cùng tài nguyên.
- Phân biệt lỗi trước commit, sau commit và kết quả chưa xác định khi timeout.
- Dùng idempotency key/correlation ID để tránh xử lý trùng khi retry hoặc reschedule.
- Với DB và message, cân nhắc outbox nếu nghiệp vụ cần lưu ý định phát sự kiện cùng transaction.
- Dùng trạng thái tiến độ, checkpoint hoặc đối chiếu nghiệp vụ nếu một job xử lý nhiều bản ghi.

Việc “bắt lỗi cho lịch tiếp tục” là lựa chọn về **lịch chạy**, không phải bảo đảm trạng thái nghiệp vụ đã an toàn. Nếu invariant đã bị phá, tiếp tục ở kỳ sau có thể làm lỗi nghiêm trọng hơn.

## 16. Thiết kế wrapper xử lý lỗi có chính sách

Một wrapper hợp lý nên tách đường lỗi có thể tiếp tục với đường lỗi cần dừng:

```java
Runnable guarded = () -> {
    long started = System.nanoTime();
    try {
        performOneSafeIteration();
        recordSuccess(System.nanoTime() - started);
    } catch (TransientDependencyException ex) {
        recordRecoverableFailure(ex);
        // Return bình thường: lịch được phép chạy lượt sau.
    } catch (IllegalStateException ex) {
        recordFatalFailure(ex);
        throw ex; // Cố tình dừng các lượt kế tiếp của lịch này.
    }
};
```

Đây là **mảnh thiết kế**; `TransientDependencyException`, `performOneSafeIteration()` và các phương thức `record...` phải được ứng dụng định nghĩa. Mức phân loại ngoại lệ và lựa chọn dừng/tiếp tục phải dựa trên hợp đồng của job cụ thể.

Đường ghi nhận metric/log cũng cần đủ ổn định. Nếu recordFailure ném exception, nó có thể làm thay đổi quyết định tiếp tục. Trong ứng dụng cần bảo đảm giám sát cao, có thể dùng kênh báo lỗi độc lập, gom lỗi của logging dưới dạng suppressed, hoặc lưu trạng thái thất bại bền vững. Tuy nhiên, không nên viết một `catch` vô hạn, cố bỏ qua mọi lỗi không xác định để duy trì tỷ lệ chạy giả tạo.

### Retry ngay trong một lượt hay chờ kỳ sau?

Có hai cách hợp lý, không tương đương:

- **Đợi kỳ tiếp theo:** khi lỗi có khả năng tạm thời và không cần phản hồi tức thì, ghi nhận lượt thất bại rồi return bình thường. Lượt sau sẽ thử lại theo chính lịch `fixedRate` hoặc `fixedDelay`.
- **Retry trong lượt hiện tại:** thử thêm có giới hạn theo timeout/backoff, rồi quyết định thành công hoặc thất bại. Nếu một lượt chạy dài, lịch fixed-rate có thể bị trễ; lịch fixed-delay cũng bị dời theo thời gian kết thúc lượt.

Đừng phối hợp nhiều vòng retry ở client, service và scheduler mà không có giới hạn tổng. Một dependency tạm mất có thể gây *retry storm* nếu mọi instance cùng đánh thức vào thời điểm giống nhau; jitter và circuit breaker có thể phù hợp với hệ thống quy mô lớn.

## 17. Quan sát và cảnh báo khi job âm thầm ngừng chạy

Sự cố thường gặp là job dừng sau exception nhưng ứng dụng vẫn trả HTTP 200 và JVM vẫn sống. Có thể xây watchdog riêng dựa trên các chỉ số được cập nhật ngay trong từng lượt:

- `lastStartedAt`: lần gần nhất bắt đầu;
- `lastCompletedAt` và `lastSuccessAt`: lần gần nhất hoàn thành/thành công;
- `consecutiveFailures`: số lần lỗi liên tiếp;
- `lastErrorType`, `lastErrorSummary`: loại lỗi và ngữ cảnh không chứa bí mật;
- Trạng thái `ScheduledFuture`: **active**, **cancelled**, **completed exceptionally**;
- Deadline kỳ vọng của lần chạy tiếp theo, cộng với sai số phù hợp và tình trạng scheduler.

Nếu `future.isDone()` cho một lịch **được kỳ vọng còn chạy**, cần phát cảnh báo và xác định nguyên nhân thay vì chỉ tạo lịch mới một cách mù quáng. Nếu `future.get(timeout)` ném `TimeoutException`, cần nhớ rằng một future định kỳ khỏe mạnh cũng chưa hoàn tất, nên timeout của `get()` không đủ kết luận job bị treo.

Tránh giám sát chỉ bằng log stack trace vì task có thể thất bại nhưng ngoại lệ đã được future giữ lại; công việc tự catch lỗi có thể cũng không in gì. Đường giám sát nên là phần rõ ràng của hợp đồng job.

## 18. Vòng đời scheduler: shutdown, cancel và tác động lên lịch

Một scheduler có thể ngừng các kỳ tiếp theo vì các nguyên nhân **khác lỗi trong task**:

- `future.cancel(...)` hủy một lịch cụ thể.
- `scheduler.shutdown()` ngừng nhận task mới, và mặc định với `ScheduledThreadPoolExecutor` các periodic task hiện hữu không tiếp tục sau shutdown (chính sách có thể được thay đổi qua `setContinueExistingPeriodicTasksAfterShutdownPolicy` trên lớp triển khai).
- `shutdownNow()` yêu cầu ngừng càng sớm càng tốt, trả về các task chưa bắt đầu và có thể interrupt worker đang chạy; nó không bảo đảm mọi side effect dừng tức thời.
- Task bị chậm vì pool nghẽn hoặc dependency treo, dù future chưa `isDone()`.
- JVM hoặc process dừng; lịch trong bộ nhớ không tự được lưu bền vững và khôi phục sau restart.

Để chẩn đoán “vì sao job không chạy”, cần phân biệt **exception suppression**, **cancellation**, **executor shutdown**, **quá tải/trễ lịch**, **kẹt công việc**, và **process restart**. Chỉ nhìn một giá trị Boolean không đủ.

Trong mã production dùng `ScheduledThreadPoolExecutor`, có thể cân nhắc `setRemoveOnCancelPolicy(true)` để các task đã hủy được gỡ khỏi hàng đợi nhanh hơn; API này là tùy chọn của lớp triển khai, không phải phương thức trên interface `ScheduledExecutorService`. Không được coi thay đổi đó là xử lý cho task đã **hoàn tất do exception**, vốn khác cancellation.

## 19. Kiểm thử chính xác việc dừng và tiếp tục

Khi viết test, ngoài kiểm tra loại exception, phải xác nhận số lần thực thi **trước và sau lỗi**. Những trường hợp quan trọng:

| Kịch bản | Kiểm tra |
| --- | --- |
| `scheduleAtFixedRate` lỗi lượt hai | `ScheduledFuture.get(timeout)` ném `ExecutionException` đúng `cause`; bộ đếm không tăng sau đó |
| `scheduleWithFixedDelay` lỗi lượt đầu | Lịch dừng; các kỳ tiếp theo không chạy |
| Task catch lỗi tạm thời | Sau một lượt lỗi, các lượt tiếp tục chạy; metric ghi nhận lỗi |
| Exception thoát từ hàm logging/callback | Lịch cũng có thể dừng; người quan sát nhận được lỗi thích hợp |
| Một lịch lỗi, lịch độc lập khỏe | Lịch độc lập vẫn chạy khi scheduler hoạt động |
| `Future` bị hủy | `isCancelled()` đúng; không nhầm với lỗi thực thi |
| Executor bị shutdown | Không lẫn shutdown policy với suppression do exception |
| Một lượt chạy lâu hơn `period` | Không có hai lượt của **cùng lịch** thực thi đồng thời |
| Async stage lỗi sau khi `Runnable` return | Lịch ngoài có thể tiếp tục; lỗi stage phải được thu thập riêng |
| Retry tác vụ có side effect | Không tạo ghi DB, message hoặc yêu cầu thanh toán trùng |

Dùng `CountDownLatch`, `AtomicInteger` và timeout đủ rộng để test những sự kiện cần thiết. Không dùng `Thread.sleep()` như bằng chứng duy nhất “chắc chắn đã xảy ra ba lượt”; thời gian scheduler phụ thuộc tải hệ thống. Khi xác nhận suppression, `future.get(timeout)` trả về bằng exception giúp biết lịch đã kết thúc; sau đó có thể kiểm tra bộ đếm. Tránh để các tác vụ test chạy mãi hoặc gây rò executor sau assertion thất bại: luôn dọn trong `finally`.

Nếu dùng hệ thống lịch khác ngoài Java SE như Quartz, Spring `@Scheduled` hoặc scheduler của ứng dụng, phải đọc hợp đồng của framework và cấu hình error handler tương ứng. Không suy rộng quy tắc suppression của `ScheduledExecutorService` sang mọi framework: có framework bắt lỗi, ghi log và tiếp tục các lần sau theo chính sách riêng.

## 20. Checklist trước khi triển khai tác vụ định kỳ

1. **Chọn đúng kiểu lịch:** fixed-rate nếu cần nhịp theo mốc dự kiến, fixed-delay nếu muốn chờ sau mỗi lần hoàn thành; hiểu rằng cùng một periodic task không overlap ở cấp `Runnable`.
2. **Phân loại lỗi:** lỗi tạm thời nào được catch để tiếp tục, lỗi nghiêm trọng nào phải thoát ra để dừng lịch?
3. **Quan sát kết quả:** giữ `ScheduledFuture` và ghi lại trạng thái/lỗi; không dựa duy nhất vào `UncaughtExceptionHandler` hoặc log mặc định.
4. **Không block vô hạn ở `get()`:** future định kỳ đang hoạt động thường không có kết quả kết thúc; dùng timeout và cơ chế giám sát phù hợp.
5. **Quản lý vòng đời:** cancel, shutdown, interrupt và cleanup theo chính sách; lưu ý cancel không undo tác dụng phụ đã có.
6. **Bảo toàn dữ liệu:** transaction, idempotency, checkpoint và kiểm tra kết quả chưa rõ trước retry.
7. **Kiểm tra job bất đồng bộ:** nếu `Runnable` chỉ khởi tạo future thì xử lý lỗi và overlap của future riêng.
8. **Giám sát từng job:** thời điểm thành công cuối, lỗi liên tiếp, trạng thái future và sức khỏe scheduler.
9. **Test cả hai hành vi:** exception thoát ra **dừng** các kỳ sau; exception được xử lý hợp lệ **cho phép tiếp tục**.
10. **Kiểm tra đúng thư viện:** `Timer`, `ScheduledThreadPoolExecutor`, Spring/Quartz hoặc các scheduler khác có hợp đồng và chính sách lỗi khác nhau.

**Quy tắc cần nhớ:** với `scheduleAtFixedRate` và `scheduleWithFixedDelay`, **một exception thoát khỏi lượt chạy có thể chấm dứt toàn bộ các lần chạy tương lai của lịch đó**. Bắt lỗi bên trong cho phép chạy tiếp khi thật sự an toàn; quan sát `ScheduledFuture` và trạng thái nghiệp vụ giúp tránh thất bại âm thầm. Lịch chạy, trạng thái dữ liệu và khả năng phục hồi cần được thiết kế cùng nhau.
