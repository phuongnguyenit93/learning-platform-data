# Future.get(timeout) và tránh chờ vô hạn trong Java Concurrency

Trong Java Executor Framework, `Future<T>` là một giao diện biểu diễn kết quả của một tác vụ bất đồng bộ. Khi gửi một `Callable<T>` qua `ExecutorService.submit()`, caller nhận một `Future<T>` ngay cả khi task vẫn đang xếp hàng hoặc chạy. Để lấy kết quả, có hai cách quan trọng:

```java
T result = future.get();                         // Có thể chờ vô hạn.
T resultWithLimit = future.get(2, TimeUnit.SECONDS); // Chờ có giới hạn.
```

Đây là trích đoạn minh họa cần một `Future<T> future` và import `TimeUnit`, với exception phải được xử lý. `get()` chờ tới khi Future hoàn tất, bị hủy hoặc thread đợi bị interrupt. Nếu task không bao giờ hoàn tất, thread gọi `get()` có thể bị chặn **vô thời hạn**. `get(timeout, unit)` giới hạn **một lần chờ** và ném `TimeoutException` khi hết ngân sách.

**Điểm cần nhớ ngay:** `Future.get(timeout)` **không tự hủy task** khi timeout. Nó chỉ đưa thread gọi trở về bằng exception; worker có thể tiếp tục chạy, xếp hàng, thực hiện I/O hoặc tạo tác dụng phụ. Để ứng dụng không chờ mãi và không để lại tác vụ vô chủ, cần kết hợp **wait timeout, overall deadline, cancellation, cleanup và quản lý vòng đời executor**.

Bài tập trung vào Java 17+ và các API concurrency của JDK, không phụ thuộc framework.

## 1. Phân biệt trạng thái của Future

Một Future có thể chưa hoàn tất, hoàn tất thành công, thất bại do exception, hoặc bị hủy:

```text
submit(callable)
       |
       v
 Future chưa xong
       |------------------------|
       v                        v
Task trong queue             Task đang chạy
       |                        |
       +-----------+------------+
                   |
          +--------+--------+
          |        |        |
        Success  Failure  Cancelled
          |        |        |
        get T    get ->    get ->
                 Execution  Cancellation
                 Exception  Exception
```

`isDone()` trả `true` cho Future đã **hoàn tất ở bất kỳ trạng thái kết thúc** phù hợp, bao gồm thất bại hoặc hủy. Nó không đồng nghĩa có kết quả thành công. `isCancelled()` phản ánh Future được đánh dấu hủy, chứ không xác nhận worker đã cleanup xong.

`get(timeout, unit)` có thể có các kết quả:

| Kết quả | Ý nghĩa | Hành động phù hợp |
|---|---|---|
| Trả về `T` | Tác vụ thành công trước khi hết thời gian đợi. | Dùng kết quả; giá trị có thể là `null` tùy `Callable`. |
| `TimeoutException` | Thời hạn của **lần chờ** đã hết. | Quyết định có hủy, fallback, tiếp tục theo dõi hay đợi lại không. |
| `ExecutionException` | Task hoàn tất nhưng ném lỗi. | Lấy `getCause()`; báo lỗi nghiệp vụ phù hợp. |
| `InterruptedException` | **Thread đang gọi get** bị interrupt. | Ném tiếp, hoặc khôi phục interrupt và thoát theo contract. |
| `CancellationException` | Future đã bị hủy. | Phân biệt hủy với lỗi task hoặc timeout chờ. |

Ba exception đầu được nêu trong chữ ký phương thức là checked exception; `CancellationException` là unchecked. Một `ExecutionException` bao bọc lỗi do task gây ra, còn `TimeoutException` không khẳng định task đang thất bại: task có thể hoàn tất thành công ngay sau timeout.

## 2. Ví dụ đầu tiên: timeout mà Future vẫn hoàn thành về sau

Để quan sát hành vi chắc chắn, ta giữ worker tại `CountDownLatch.await()`. Main gọi `get(20, MILLISECONDS)` trong lúc latch vẫn đóng, sau đó chủ động mở latch và lấy kết quả từ **cùng Future**.

Tạo file **`FutureTimeoutThenComplete.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutThenComplete {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Future<String> future = executor.submit(() -> {
            started.countDown();
            release.await();
            return "completed";
        });

        try {
            started.await();
            try {
                future.get(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("First get timed out");
            }

            System.out.println("Cancelled: " + future.isCancelled());
            release.countDown();

            String result = future.get(5, TimeUnit.SECONDS);
            System.out.println("Result: " + result);
        } finally {
            release.countDown();
            executor.shutdown();
        }

        boolean stopped = executor.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Executor terminated: " + stopped);
    }
}
```

Lệnh:

```bash
javac FutureTimeoutThenComplete.java
java FutureTimeoutThenComplete
```

Đầu ra khi không có external interrupt:

```text
First get timed out
Cancelled: false
Result: completed
Executor terminated: true
```

**Vì sao kết quả xác định?** `started.await()` xác nhận worker đã vào callable. Nhưng worker phải chờ `release`, trong khi main chưa mở latch lúc gọi `get(20, ...)`. Vì vậy get đầu tiên phải timeout; nó không hủy task và `isCancelled() == false`. Main mở latch, worker trả `completed`, lần get sau thành công. Cuối cùng shutdown và `awaitTermination()` xác nhận executor thực sự dừng.

`get(timeout)` chỉ giới hạn **lần chờ hiện tại**. Gọi lại get với một timeout mới có nghĩa caller **đặt thêm ngân sách**, điều này có thể đúng nếu có lý do, nhưng không tự tạo thời hạn tổng cho request.

## 3. Timeout chờ không phải timeout chạy task

Giả sử executor đang quá tải:

```text
0 ms      Caller submit task; task ở queue.
200 ms    Caller bắt đầu get(1000, MILLISECONDS).
1200 ms   get() ném TimeoutException, caller không chờ nữa.
1600 ms   Worker mới lấy task khỏi queue và bắt đầu chạy.
2200 ms   Task hoàn thành và có thể đã tạo side effect.
```

Đây là timeline **giả định**, minh họa sự khác biệt giữa thời gian nộp task và thời gian bắt đầu chờ.

| Loại thời hạn | Muốn giới hạn gì? | Công cụ |
|---|---|---|
| Wait timeout | Caller được block trong một lời get bao lâu? | `Future.get(timeout, unit)`. |
| Queue deadline | Task còn hữu ích nếu đợi trong queue bao lâu? | Deadline trong task, queue capacity và cơ chế loại bỏ/hủy. |
| Execution budget | Task được phép chạy tới khi nào? | Cooperative cancellation, kiểm tra deadline, timeout từng thao tác. |
| I/O timeout | Lời gọi socket/database/network chờ tối đa bao lâu? | Timeout của chính I/O API hoặc giao thức dịch vụ. |
| Overall deadline | Toàn bộ công việc end-to-end phải xong trước khi nào? | Một ngân sách chung truyền qua nhiều bước. |

Một `TimeoutException` ở caller **không rollback side effect** mà worker đã tạo, không bảo đảm worker đã trả kết nối về pool và cũng không làm Future chuyển sang canceled.

## 4. Xử lý TimeoutException: tiếp tục, fallback hay cancel?

Khi một lần get quá hạn, có ba chính sách thường gặp:

- **Còn cần kết quả:** giữ Future, tiếp tục làm việc khác, rồi chỉ đợi lại trong ngân sách còn lại hoặc nhận kết quả bất đồng bộ.
- **Không còn cần task:** gọi `future.cancel(true)` nếu caller có quyền hủy và task có đường phản ứng interruption; sau đó quản lý việc kết thúc và cleanup.
- **Cần fallback hoặc trả lỗi timeout:** trả cho caller một kết quả thay thế, nhưng vẫn phải có owner của task đang chạy; không mặc định nó tự biến mất.

`cancel(true)` yêu cầu hủy Future và có thể cố interrupt thread chạy task; nó **không phải lời hứa task sẽ chấm dứt ngay lập tức**. Một task chạy CPU mà không kiểm tra cờ interrupt, hoặc một lời I/O không hỗ trợ interruption, có thể tiếp tục sau khi Future bị đánh dấu canceled.

`cancel(false)` yêu cầu hủy nhưng không yêu cầu interrupt task đang chạy. Cần phân biệt trạng thái Future với tiến triển thực tế của worker: `isDone()` hay `isCancelled()` có thể true khi cleanup phía worker chưa hoàn tất.

Không retry ngay một task có side effect chỉ vì get timeout: task cũ có thể vẫn đang chạy. Hãy thiết kế **idempotency**, unique request ID, transaction hoặc cơ chế phát hiện công việc đã thực hiện nếu một lần chạy trùng gây hại.

## 5. Ví dụ 2: timeout, cancel(true) và chờ cleanup

Ví dụ này cho thấy một `Future` bị hủy không đủ làm bằng chứng cleanup đã xong. Worker sử dụng một blocking call có hỗ trợ interruption và dọn trong `finally`. Main **đợi executor terminated** rồi mới đọc cờ cleanup.

Tạo file **`FutureCancelAndCleanup.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancelAndCleanup {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        AtomicBoolean cleaned = new AtomicBoolean();

        Future<Integer> future = executor.submit(() -> {
            started.countDown();
            try {
                neverReleased.await();
                return 42;
            } finally {
                cleaned.set(true);
            }
        });

        try {
            started.await();
            try {
                future.get(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("Wait timed out");
            }

            boolean accepted = future.cancel(true);
            System.out.println("Cancel accepted: " + accepted);
        } finally {
            executor.shutdown();
        }

        boolean terminated = executor.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Executor terminated: " + terminated);
        System.out.println("Cleanup completed: " + cleaned.get());
        System.out.println("Future cancelled: " + future.isCancelled());
    }
}
```

```bash
javac FutureCancelAndCleanup.java
java FutureCancelAndCleanup
```

Đầu ra trong điều kiện bình thường:

```text
Wait timed out
Cancel accepted: true
Executor terminated: true
Cleanup completed: true
Future cancelled: true
```

Worker đã bắt đầu và phải chờ một latch không bao giờ mở. Lần get đầu vì vậy hết hạn, còn `cancel(true)` có thể interrupt worker đang đợi. `await()` ném `InterruptedException`, nhánh `finally` đặt `cleaned=true`. Chỉ **sau `awaitTermination()` thành công** thì main mới kết luận executor không còn worker đang chạy.

Trong code production, nếu `awaitTermination()` trả `false`, không được báo “đã cleanup xong”. Phải đưa việc còn chạy quá hạn vào một chính sách giám sát và xử lý phù hợp.

## 6. Task failure và hủy khác timeout

Nếu callable ném exception, `future.get()` thường ném `ExecutionException` và `getCause()` chứa nguyên nhân. Với Future canceled, `get()` ném `CancellationException`.

Tạo file **`FutureResultPaths.java`**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class FutureResultPaths {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> failed = executor.submit(() -> {
                throw new IllegalArgumentException("bad input");
            });

            try {
                failed.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException e) {
                System.out.println("Failure: "
                        + e.getCause().getMessage());
            }

            CompletableFuture<String> cancelled =
                    new CompletableFuture<>();
            cancelled.cancel(false);
            try {
                cancelled.get(0, TimeUnit.MILLISECONDS);
            } catch (CancellationException e) {
                System.out.println("Cancelled: true");
            }
        } finally {
            executor.shutdown();
        }

        boolean terminated = executor.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Executor terminated: " + terminated);
    }
}
```

```bash
javac FutureResultPaths.java
java FutureResultPaths
```

Đầu ra:

```text
Failure: bad input
Cancelled: true
Executor terminated: true
```

Đường lỗi của callable đã được tạo rõ ràng và get bọc nó trong `ExecutionException`. `CompletableFuture` thứ hai được cancel trước bất cứ lần chạy nào, nên `get(0, ...)` ném `CancellationException` ngay. Trong một Future chưa hoàn tất, timeout không dương không cung cấp khoảng thời gian chờ có ích; hãy dùng ngân sách dương rõ ràng nếu muốn đợi.

Đừng bắt `Exception` chung rồi trả fallback cho mọi trường hợp: lỗi do task, hủy do caller và timeout chờ là những tình huống có hậu quả nghiệp vụ khác nhau.

## 7. InterruptedException: caller bị ngắt không đồng nghĩa worker bị hủy

Một thread đang chờ `future.get(timeout)` có thể nhận interrupt và bị ném `InterruptedException`. Đây là **interrupt của thread chờ**, không phải bằng chứng worker thực thi Future đã kết thúc.

Mẫu xử lý khi không muốn ném tiếp checked exception:

```java
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Nếu thực sự sở hữu task và contract yêu cầu:
    future.cancel(true);
    throw new IllegalStateException("Wait interrupted", e);
}
```

Đây là trích đoạn trong một method có kiểu trả về phù hợp và cần import các lớp concurrency. Khi bắt `InterruptedException`, cờ interrupt thường đã bị xóa; `Thread.currentThread().interrupt()` khôi phục nó cho tầng gọi. Nếu method **ném tiếp `InterruptedException`**, thông thường không cần tự restore tại tầng này.

Việc hủy Future khi caller bị interrupt là **một lựa chọn có chủ đích**: nếu Future là tác vụ dùng chung và caller không sở hữu nó, hủy có thể ảnh hưởng người khác. Không tự động áp dụng `cancel(true)` cho mọi Future chỉ vì một người đợi không còn quan tâm.

## 8. Overall deadline khi có nhiều Future

Ba lời đợi sau có thể tiêu tốn gần sáu giây:

```java
Result a = first.get(2, TimeUnit.SECONDS);
Result b = second.get(2, TimeUnit.SECONDS);
Result c = third.get(2, TimeUnit.SECONDS);
```

Đây là trích đoạn minh họa; các Future và `Result` được giả định đã khai báo. **Hai giây cho mỗi get** khác với **hai giây cho toàn bộ chuỗi**.

Một helper để chia sẻ deadline:

```java
static <T> T getBeforeDeadline(
        Future<T> future, long deadlineNanos)
        throws InterruptedException, ExecutionException,
               TimeoutException {
    long remaining = deadlineNanos - System.nanoTime();
    if (remaining <= 0L) {
        throw new TimeoutException("Overall deadline expired");
    }
    return future.get(remaining, TimeUnit.NANOSECONDS);
}
```

Đây là method minh họa không độc lập, cần import `Future`, `TimeUnit` và ba exception. Caller tính **một deadline**:

```java
long deadline = System.nanoTime()
        + TimeUnit.SECONDS.toNanos(2);

Result a = getBeforeDeadline(first, deadline);
Result b = getBeforeDeadline(second, deadline);
Result c = getBeforeDeadline(third, deadline);
```

Không reset hai giây ở mỗi lượt. `System.nanoTime()` phù hợp để đo khoảng thời gian và không phụ thuộc điều chỉnh đồng hồ lịch như `currentTimeMillis()`. Với ngân sách quá lớn, cần giới hạn/kiểm tra tràn số; mẫu này giả định duration dương, hữu hạn, đủ nhỏ để phép cộng và so sánh nanoTime không vướng overflow ngoài phạm vi đo.

**Lưu ý:** Một thời hạn end-to-end thường nên bắt đầu từ lúc tiếp nhận yêu cầu, **không** phải sau khi task đã nằm trong queue lâu. Nếu thời gian chờ queue cũng thuộc SLA, tính nó vào ngân sách tổng. Task tự kiểm tra deadline khi bắt đầu cũng hữu ích nếu kết quả quá hạn không còn giá trị.

## 9. Memory consistency và happens-before của Future.get()

`Future` có hợp đồng memory consistency: **các hành động do tính toán bất đồng bộ thực hiện happens-before các hành động trong thread khác xảy ra sau khi lời `Future.get()` tương ứng hoàn tất**. Khi worker xây dựng kết quả rồi hoàn thành Future, thread đợi get thành công có thể quan sát dữ liệu được công bố theo Java Memory Model (JMM) mà không cần tự thêm `volatile` chỉ cho việc chuyển giao kết quả đúng cách.

Ví dụ:

```java
// Trích đoạn: dữ liệu được worker tính xong trước khi Future thành công.
Future<Integer> future = executor.submit(() -> {
    data.result = 42;
    return data.result;
});
int value = future.get();
System.out.println(value);
```

Đoạn này giả định `executor` và `data` đã khai báo, xử lý checked exceptions. `get()` thành công là một **mốc nhận kết quả**, nhưng không biến mọi mutation đồng thời lên `data` từ thread khác thành an toàn.

**Khi `get(timeout)` timeout**, caller **chưa nhận mốc hoàn tất của tác vụ** qua lần get đó. Không được tự suy “mọi ghi của worker đã hoàn tất và hiển thị” chỉ vì vừa hết hạn. Nếu vẫn cần đọc state cuối, hãy đợi một cơ chế hoàn tất được xác nhận, hoặc dùng primitive đồng bộ có hợp đồng riêng như volatile/atomic/lock.

## 10. Với ScheduledFuture, timeout có thêm thời gian trì hoãn trước khi chạy

`ScheduledExecutorService.schedule(task, delay, unit)` trả `ScheduledFuture<T>`. Khi task có delay ban đầu, `get(timeout)` đợi **kết quả cuối cùng** chứ không chỉ đợi thời điểm hẹn:

```java
ScheduledFuture<String> scheduled =
        scheduler.schedule(() -> "done", 3, TimeUnit.SECONDS);
String result = scheduled.get(1, TimeUnit.SECONDS);
```

Đây là trích đoạn, với `scheduler` là `ScheduledExecutorService` đã khai báo. Vì delay ba giây, lần get có ngân sách một giây **thường** sẽ timeout nếu scheduled task chưa chạy; timeout không hủy lịch đã lên. `getDelay(unit)` phản ánh thời gian còn lại tới mốc scheduling theo contract, **không** phải thời gian task sẽ chạy xong.

Với `scheduleAtFixedRate()` hoặc `scheduleWithFixedDelay()`, `ScheduledFuture<?> ` đại diện cho một **chuỗi thực thi định kỳ**. Future của task định kỳ bình thường **không hoàn tất sau tick đầu**, nên gọi `get(timeout)` không phải cách chờ “đã có một lần chạy”. Chuỗi Future thường chỉ đi tới trạng thái kết thúc khi bị hủy hoặc khi việc thực thi chấm dứt bất thường. Nếu cần đợi riêng một tick, dùng `CountDownLatch` hoặc Future chuyên biệt cho sự kiện đó.

## 11. CompletableFuture: orTimeout khác get(timeout)

`CompletableFuture` còn có:

```java
future.orTimeout(1, TimeUnit.SECONDS);
future.completeOnTimeout("fallback", 1, TimeUnit.SECONDS);
```

Hai dòng là **hai chiến lược thay thế**, không nên gọi cả hai lên cùng Future chỉ vì thấy tiện. `orTimeout` có thể làm **chính CompletableFuture đó** hoàn tất ngoại lệ với `TimeoutException`. `completeOnTimeout` có thể hoàn tất Future bằng giá trị dự phòng. Đây là thay đổi **trạng thái Future**, khác với `future.get(timeout)` chỉ làm kết thúc **lần chờ caller**.

Khi một CompletableFuture hoàn tất ngoại lệ vì `orTimeout`, `get()` thường ném `ExecutionException` với cause là `TimeoutException`; `join()` thường ném `CompletionException`. **Các phương thức này không bảo đảm phép tính underlying đã dừng**. Một tác vụ chạy qua `supplyAsync()` có thể tiếp tục làm side effect sau khi CompletableFuture đã timeout. Cleanup và cancellation cần được thiết kế riêng.

## 12. Không để get(timeout) trở thành một điểm nghẽn mới

`get(timeout)` vẫn **block thread gọi** trong khoảng chờ được cho phép. Nếu gọi nó trên event loop, UI thread hoặc nhiều request threads với timeout lớn, hệ thống có thể nghẽn dù từng lời chờ đều hữu hạn.

Nếu xử lý kết quả theo kiểu bất đồng bộ phù hợp, có thể dùng `thenApply()`, `thenCompose()`, `whenComplete()` của `CompletableFuture` thay cho việc block. Nếu phải chờ đồng bộ, hãy:

- Chọn ngân sách phù hợp với SLA và số bước còn lại.
- Cân nhắc bounded executor queue để không tạo backlog vô hạn.
- Dùng timeout riêng cho I/O bên trong task.
- Đảm bảo có đường xử lý quá hạn và cancellation/cleanup.
- Không dùng `while (!future.isDone()) Thread.sleep(...)` như polling mặc định: việc tự ngủ không thay thế exception handling và có thể tăng độ trễ.

Không có timeout nào là “an toàn tuyệt đối” cho mọi workload. Mục tiêu là một giới hạn **có nghĩa trong nghiệp vụ**, không phải luôn đặt một con số rất lớn.

## 13. Shutdown executor và tránh chờ vô thời hạn ở vòng đời

Sau khi hoàn tất sử dụng pool, owner nên ngừng nhận task mới, rồi chờ termination với giới hạn:

```java
executor.shutdown();
if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
    executor.shutdownNow();
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        System.err.println("Executor still running");
    }
}
```

Đây là trích đoạn cần khai báo `executor` và xử lý `InterruptedException`. `shutdown()` cho những task đã được nhận tiếp tục chạy, trong khi `shutdownNow()` **cố** ngắt worker và lấy các task chưa bắt đầu ra khỏi queue. Cả hai không đảm bảo một task không hợp tác sẽ chấm dứt ngay.

`awaitTermination(timeout)` trả `false` khi hết thời gian mà executor vẫn chưa kết thúc. Nếu thread đang shutdown bị interrupt, ứng dụng nên có chính sách riêng để yêu cầu dừng và **khôi phục trạng thái interrupt** thay vì nuốt exception rồi chờ không giới hạn.

`get(timeout)` trên từng Future **không thay thế** việc đóng executor: một tác vụ bị bỏ qua sau timeout vẫn có thể giữ worker sống, làm chương trình không kết thúc hoặc làm tài nguyên không được giải phóng.

## 14. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Giải pháp |
|---|---|---|
| Dùng `get()` vô hạn trên task có thể treo. | Caller bị block mãi. | Đặt deadline hữu hạn và đường xử lý timeout. |
| Cho rằng `get(timeout)` tự hủy. | Worker có thể còn chạy và làm side effect. | Cancel/cleanup theo ownership nếu cần. |
| Reset toàn bộ timeout cho mỗi get trong chuỗi. | Tổng thời gian chờ vượt SLA. | Dùng một overall deadline. |
| Gộp lỗi task, cancel và timeout thành một ngoại lệ chung. | Retry/báo lỗi sai nguyên nhân. | Phân biệt `ExecutionException`, `CancellationException`, `TimeoutException`. |
| Nuốt `InterruptedException`. | Mất tín hiệu hủy của caller. | Ném tiếp hoặc restore interrupt rồi thoát. |
| Chỉ xem `isDone()` là thành công. | Failed/canceled cũng là done. | Kiểm tra trạng thái, lấy kết quả/exception hợp lệ. |
| Cancel Future rồi coi resource đã đóng. | Cleanup của worker có thể còn chạy. | Xác nhận termination/cleanup riêng. |
| Chỉ dùng get timeout để kiểm soát socket/database. | I/O worker có thể tiếp tục sau khi caller bỏ cuộc. | Đặt I/O timeout và cancellation phù hợp. |
| Retry tác vụ có side effect sau timeout. | Task cũ vẫn chạy, gây thực hiện trùng. | Dùng idempotency/transaction và theo dõi kết quả cũ. |
| Gọi get của periodic ScheduledFuture để chờ một tick. | Future chưa hoàn tất dù tick đã chạy. | Latch hoặc Future riêng cho tick. |
| Dùng `orTimeout` rồi nghĩ computation đã dừng. | Underlying task có thể tiếp tục. | Tách Future completion và cancellation. |
| Không shutdown executor sau khi dùng. | Rò worker và có thể giữ JVM sống. | Owner quản lý lifecycle và awaitTermination có giới hạn. |

## 15. Checklist và câu hỏi tự kiểm tra

Trước khi dùng Future timeout trong thực tế, kiểm tra hợp đồng: **thời điểm bắt đầu budget**, ý nghĩa timeout với caller, task có còn hữu ích sau deadline không, khả năng interruption, owner của worker, cơ chế cleanup và cách truyền nguyên nhân lỗi. Đối với nhiều Future, tính thời gian còn lại từ một mốc chung; đối với task trong queue, đưa thời gian chờ queue vào deadline khi cần. Không retry tác dụng phụ ngoài JVM nếu chưa có chính sách tránh trùng. Theo dõi timeout rate, queue latency, task duration, cancellation và termination failures.

Các câu hỏi quan trọng:

1. **Vì sao `get()` có thể làm thread chờ vô hạn?** Nếu Future không hoàn tất thì lời get không có hạn có thể không trả về.
2. **`get(1, SECONDS)` timeout có tự ngắt worker không?** Không.
3. **`TimeoutException` có nghĩa task ném exception không?** Không; chỉ là caller đợi quá hạn.
4. **`ExecutionException` cho biết gì?** Task đã kết thúc bằng lỗi; `getCause()` cung cấp nguyên nhân.
5. **`CancellationException` khác timeout thế nào?** Future đã bị hủy, không chỉ một lượt chờ quá hạn.
6. **`InterruptedException` trong get là interrupt của ai?** Thread **đang đợi get**, không nhất thiết là worker.
7. **Có thể gọi get lần nữa sau TimeoutException không?** Có; nếu Future chưa bị hủy, nhưng phải quản lý tổng thời gian.
8. **Vì sao `isDone()` không có nghĩa thành công?** Vì lỗi và hủy cũng là kết thúc theo trạng thái Future.
9. **`cancel(true)` có bảo đảm cleanup xong?** Không; cần xác nhận worker termination/cleanup.
10. **Vì sao ba lần `get(2, SECONDS)` có thể đợi gần sáu giây?** Mỗi lời get được cấp hai giây riêng.
11. **Tại sao dùng `System.nanoTime()` cho deadline?** Nó phù hợp đo khoảng, không bị điều chỉnh theo đồng hồ lịch.
12. **`ScheduledFuture.get()` của task định kỳ có trả về sau một tick không?** Không, Future đại diện chuỗi định kỳ.
13. **`orTimeout()` có cùng nghĩa với `get(timeout)` không?** Không; một bên có thể complete Future ngoại lệ, bên kia chỉ kết thúc lời chờ.
14. **Khi get thành công, JMM đảm bảo gì?** Các hành động tính toán bất đồng bộ happens-before các hành động sau get tương ứng; không có nghĩa mọi object mutable ngoài giao thức đều an toàn.

**Ghi nhớ:** `Future.get(timeout)` giúp **giới hạn thời gian chờ một lần của caller**, không tự hủy task. Một hệ thống tránh chờ vô hạn thực sự cần **overall deadline, xử lý đủ các trạng thái kết thúc, cancellation hợp tác, I/O timeout và shutdown/cleanup có giới hạn**.
