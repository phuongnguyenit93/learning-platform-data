# CancellationException và giới hạn mayInterruptIfRunning của CompletableFuture trong Java

> **Chủ đề:** Java Core → Exception → CompletableFuture. Nội dung giải thích ý nghĩa của `CancellationException`, hành vi của `CompletableFuture.cancel(boolean)`, vì sao đối số `mayInterruptIfRunning` không có hiệu lực ngắt tác vụ đối với `CompletableFuture`, cách phân biệt **hủy trạng thái kết quả** với **dừng công việc đang chạy**, và cách xử lý đúng khi phối hợp `Future`, `ExecutorService`, timeout, dependent stages và interruption.

## 1. Cần phân biệt ba sự kiện

Trong lập trình bất đồng bộ, ba sự kiện dưới đây dễ bị gộp làm một dù chúng có bản chất khác nhau.

1. **Hủy kết quả (cancel completion):** một future chuyển sang trạng thái bị hủy, nên người chờ kết quả nhận `CancellationException` thay vì giá trị thành công.
2. **Ngắt một thread (interrupt):** gửi yêu cầu hợp tác qua `Thread.interrupt()`; thread có thể phản ứng tại những điểm chặn hoặc khi chủ động kiểm tra cờ interrupt.
3. **Dừng/hoàn tác công việc:** computation thật sự ngừng thực thi, cleanup tài nguyên và nếu cần thì rollback tác dụng phụ. Việc này đòi hỏi thiết kế riêng; không thể suy ra chỉ từ trạng thái future.

Một `CompletableFuture` có thể được đánh dấu hủy **khi mã đang chạy trong executor vẫn tiếp tục**. Sau khi lời gọi `cancel` thành công, người gọi có thể không nhận kết quả cuối cùng của computation dù computation vẫn thực hiện I/O, ghi dữ liệu hoặc chiếm CPU.

**Thông điệp chính:** `CompletableFuture.cancel(true)` không tương đương “buộc worker dừng”; `CancellationException` là một cách biểu diễn trạng thái hủy, không phải chứng chỉ rằng mọi side effect đã dừng hoặc được rollback.

## 2. CancellationException là gì?

`java.util.concurrent.CancellationException` là một unchecked exception (kế thừa `IllegalStateException`, rồi `RuntimeException`). Trong các API tương lai/bất đồng bộ, nó biểu thị việc chờ hoặc lấy kết quả gặp một tác vụ đã bị hủy.

Ví dụ:

~~~java
// Trích đoạn có thể đặt trong một phương thức Java.
java.util.concurrent.CompletableFuture<String> future =
        new java.util.concurrent.CompletableFuture<>();

future.cancel(false);

try {
    future.join();
} catch (java.util.concurrent.CancellationException ex) {
    System.out.println("result was cancelled");
}
~~~

Với `CompletableFuture` được hủy, các kiểm tra sau thường cùng đúng:

~~~java
// future ở ví dụ trên đã bị hủy.
future.isDone();                    // true
future.isCancelled();               // true
future.isCompletedExceptionally();  // true
~~~

Vì **cancellation là một dạng exceptional completion**, `isCompletedExceptionally()` không đủ để xác định task đã thất bại bởi lỗi nghiệp vụ hay bị hủy. Kiểm tra `isCancelled()` và lựa chọn kênh xử lý phù hợp.

**Chi tiết cần nhớ:** `isCancelled()` đối với `CompletableFuture` dựa trên việc future đã hoàn tất với `CancellationException`. Vì vậy một lệnh `completeExceptionally(new CancellationException(...))` cũng có thể dẫn đến trạng thái được coi là canceled. Khi cần phân loại, xét ngữ nghĩa của trạng thái kết quả thay vì giả định chỉ riêng phương thức `cancel()` mới có thể tạo ra trạng thái đó.

## 3. Hợp đồng CompletableFuture.cancel(boolean)

Chữ ký:

~~~java
public boolean cancel(boolean mayInterruptIfRunning)
~~~

Theo tài liệu Java SE 17 về `CompletableFuture`, phương thức `cancel` cố gắng hoàn tất bất thường future bằng `CancellationException` nếu nó chưa hoàn tất. Lệnh có ngữ nghĩa tương đương việc thực hiện exceptional completion bằng một `CancellationException` mới trên future đang pending.

Giá trị trả về:

- `true` nếu future được hủy thành công bởi lần gọi này **hoặc đã ở trạng thái canceled**.
- `false` nếu future đã hoàn tất theo một trạng thái không phải cancellation, ví dụ đã thành công với giá trị hoặc đã thất bại với exception khác.
- Không được diễn giải `true` như lời cam kết computation gốc đã dừng.

Đặc biệt, **đối số `mayInterruptIfRunning` không có hiệu lực trong implementation `CompletableFuture`**, vì các phương thức của lớp này không sử dụng interrupt để điều khiển trực tiếp quá trình computation. Trong Java SE 17, gọi `cancel(true)` trên `CompletableFuture` không tự gửi interrupt tới worker thực thi supplier.

Điều này đúng kể cả khi future có liên quan đến `CompletableFuture.supplyAsync(...)` hoặc `runAsync(...)`. Nếu supplier đang chạy, nó có thể tiếp tục cho tới khi tự hoàn tất hoặc gặp một cơ chế hủy khác. Nếu cancellation thắng trước khi tác vụ bắt đầu, cơ chế chạy cụ thể có thể bỏ qua phần body đã bị đánh dấu hoàn tất; điều đó không tạo thành bảo đảm rằng `cancel(true)` có thể ngắt một tác vụ **đang chạy**.

~~~java
// Minh họa: future nhận trạng thái canceled, không bảo đảm stopWorker().
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(() -> runSlowOperation());

boolean accepted = result.cancel(true);
// accepted phản ánh kết quả completion.
// Không suy ra runSlowOperation() đã bị interrupt hay rollback.
~~~

`runSlowOperation()` là hàm minh họa cần có trong ứng dụng. Muốn yêu cầu dừng tác vụ thật, phải thiết kế một cơ chế phối hợp khác, chẳng hạn cancellation token được task kiểm tra, giữ một `Future` do executor trả về, hoặc một API hủy của thao tác I/O.

## 4. So sánh với Future.cancel(boolean)

Cùng tên phương thức nhưng `mayInterruptIfRunning` mang ý nghĩa khác khi thao tác trên `FutureTask`/`Future` được trả về từ `ExecutorService.submit()`.

| Tiêu chí | `CompletableFuture.cancel(true)` | `Future.cancel(true)` từ `ExecutorService.submit` |
|---|---|---|
| Đối tượng trực tiếp bị tác động | Trạng thái completion của `CompletableFuture` | Trạng thái cancellation của tác vụ `Future` |
| `mayInterruptIfRunning` | **Không có tác dụng ngắt computation** theo hợp đồng lớp | Nếu tác vụ đang chạy, implementation có thể **yêu cầu interrupt thread đang thực thi** |
| Bảo đảm tác vụ thực sự dừng? | **Không** | **Không**: interrupt là hợp tác; tác vụ có thể không đáp ứng |
| `get()` sau khi đã canceled | `CancellationException` | `CancellationException` |
| Khả năng rollback side effect | Không tự thực hiện | Không tự thực hiện |
| Cách xử lý đúng | Cần kênh hủy riêng nếu muốn dừng worker | Thiết kế task đáp ứng interrupt, cleanup và quản lý lifecycle |

Trong hợp đồng `Future.cancel(boolean)`, `mayInterruptIfRunning = true` cho phép yêu cầu interrupt khi tác vụ đang chạy; `false` không yêu cầu interrupt một công việc đã chạy. Ngay cả khi `Future.cancel(true)` trả `true`, vẫn **không chứng minh** mã đã dừng hoàn toàn hoặc resource đã được giải phóng. Task có thể bỏ qua interrupt, chặn ở API không đáp ứng interrupt, hoặc đang làm side effect đã commit.

`CompletableFuture` triển khai `Future` nhưng định nghĩa cụ thể rằng cờ này không dùng để điều khiển computation; vì vậy không nên áp nguyên xi giả định từ `FutureTask` sang `CompletableFuture`.

## 5. Sơ đồ hai luồng độc lập

~~~text
Thread gọi API                               Executor worker
---------------                              -----------------------
CompletableFuture.supplyAsync(supplier)  --> bắt đầu supplier
         |                                      |
         |                                   đang đợi latch/I/O
         |
result.cancel(true)
         |
 CompletableFuture chuyển canceled
         |
result.join() -> CancellationException       worker có thể vẫn đang chạy
         |                                      |
         |                                   hoàn thành side effect
         |                                      |
         |                                  trả một giá trị
         |                                      |
         |                                  kết quả đến quá muộn
         v
caller không nhận giá trị đó từ future canceled
~~~

Sơ đồ mô tả trường hợp supplier **đã bắt đầu chạy** và không có cơ chế hủy độc lập. Không nói rằng mọi supplier luôn tiếp tục đến hết trong mọi tình huống: tác vụ có thể tự phản ứng với token hủy, bị interrupt bởi một nguồn khác, thất bại bởi I/O hoặc không được bắt đầu nếu future đã bị canceled trước đó.

## 6. Chương trình Java 17 hoàn chỉnh: hủy CompletableFuture không interrupt worker

Chương trình sau dùng `CountDownLatch` để bảo đảm tác vụ đã bắt đầu trước khi caller hủy. Nó còn dùng `ExecutorService` một luồng và một tác vụ đánh dấu sau đó để bảo đảm quan sát đã diễn ra **sau khi supplier cũ kết thúc**, tránh kết quả phụ thuộc vào `sleep` hoặc timing của hệ điều hành.

Lưu toàn bộ mã vào **`CompletableFutureCancellationDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

public class CompletableFutureCancellationDemo {
    public static void main(String[] args) throws Exception {
        demonstrateCompletableFuture();
        demonstrateSubmittedFuture();
    }

    static void demonstrateCompletableFuture() throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);
        AtomicBoolean completedWork = new AtomicBoolean(false);

        try {
            CompletableFuture<String> result =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException ex) {
                            sawInterrupt.set(true);
                            Thread.currentThread().interrupt();
                            return "interrupted";
                        }

                        completedWork.set(true);
                        return "finished";
                    }, pool);

            CompletableFuture<Integer> dependent =
                    result.thenApply(String::length);

            started.await(); // Supplier đã bắt đầu.
            System.out.println("CF cancel: " + result.cancel(true));
            System.out.println("CF isCancelled: " + result.isCancelled());
            System.out.println("CF isExceptional: "
                    + result.isCompletedExceptionally());

            try {
                result.join();
            } catch (CancellationException ex) {
                System.out.println("CF join: CancellationException");
            }

            try {
                dependent.join();
            } catch (CompletionException ex) {
                System.out.println("Dependent cause: "
                        + ex.getCause().getClass().getSimpleName());
            }

            release.countDown();
            // Một executor đơn luồng: marker chạy sau supplier.
            pool.submit(() -> {}).get();

            System.out.println("CF worker interrupted: " + sawInterrupt.get());
            System.out.println("CF worker finished work: " + completedWork.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }

    static void demonstrateSubmittedFuture() throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);

        try {
            Future<?> submitted = pool.submit(() -> {
                started.countDown();
                try {
                    new CountDownLatch(1).await(); // Chờ tới khi bị interrupt.
                } catch (InterruptedException ex) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            started.await();
            System.out.println("Future cancel: " + submitted.cancel(true));
            finished.await();
            System.out.println("Future worker interrupted: "
                    + sawInterrupt.get());

            try {
                submitted.get();
            } catch (CancellationException ex) {
                System.out.println("Future get: CancellationException");
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CompletableFutureCancellationDemo.java
java CompletableFutureCancellationDemo
~~~

**Stdout chính xác:**

~~~text
CF cancel: true
CF isCancelled: true
CF isExceptional: true
CF join: CancellationException
Dependent cause: CancellationException
CF worker interrupted: false
CF worker finished work: true
Future cancel: true
Future worker interrupted: true
Future get: CancellationException
~~~

**Giải thích theo từng giai đoạn:**

1. Latch `started` xác nhận supplier của `supplyAsync` đã chạy. `result.cancel(true)` thành công, đưa `result` vào trạng thái canceled, làm `isCancelled` và `isCompletedExceptionally` trả `true`.
2. `result.join()` ném trực tiếp `CancellationException`. Stage phụ thuộc `thenApply(String::length)` không thực hiện phép đổi độ dài và hoàn tất bất thường; `dependent.join()` báo một `CompletionException` có `cause` là `CancellationException`.
3. Vì `CompletableFuture.cancel(true)` không interrupt supplier, supplier vẫn chờ `release`. Sau khi main nhả latch, supplier thực hiện phần công việc còn lại và cập nhật `completedWork`, mặc dù kết quả tương lai đã bị hủy. Tác vụ đánh dấu `pool.submit(() -> {}).get()` bảo đảm supplier trước đó đã chạy xong trong executor một luồng; output `false` và `true` ở hai dòng kiểm tra không dựa vào may rủi scheduler.
4. Phần thứ hai dùng `Future<?>` do `ExecutorService.submit` tạo. Sau khi Runnable đã bắt đầu, `submitted.cancel(true)` có khả năng yêu cầu interrupt tới thread đang ở `await()`. Runnable bắt `InterruptedException`, ghi nhận `sawInterrupt=true` và kết thúc. `submitted.get()` vẫn báo `CancellationException` vì future đã bị hủy.
5. Hai cơ chế có cùng kết quả **future canceled** nhưng khác nhau rõ ràng ở việc có cố gửi interrupt cho công việc thật hay không. Ngay cả `Future.cancel(true)` cũng chỉ dựa vào sự hợp tác của task, không thể coi như transaction rollback.

Mã mẫu quản lý executor bằng `shutdownNow()` trong `finally` để tránh rò rỉ thread nếu một bước lỗi. Trong ứng dụng production nên có timeout và kế hoạch xử lý khi công việc cố tình không phản hồi interrupt; ví dụ này cố ý chọn các thao tác có thể ngắt để đầu ra xác định trong điều kiện chạy bình thường.

## 7. Vì sao join/get có thể báo CancellationException khác nhau?

Nếu **chính future** đã bị canceled, `CompletableFuture.join()` và `get()` có thể ném **trực tiếp** `CancellationException`. Đây là unchecked exception, không phải `ExecutionException` hay `CompletionException` chứa một lỗi nghiệp vụ.

Ngược lại, một dependent stage truyền lỗi từ nguồn canceled thường hoàn tất bất thường thông qua một wrapper `CompletionException` có `cause` là `CancellationException`. Vì vậy cần phân biệt kết quả của *source* và *dependent stage*.

~~~java
// Đoạn minh họa Java, có thể đặt trong một phương thức.
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<Integer> derived = source.thenApply(String::length);
source.cancel(false);

try {
    source.join();
} catch (CancellationException ex) {
    // Hủy trực tiếp trên source.
}

try {
    derived.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause(); // Có thể là CancellationException.
}
~~~

Trong tình huống này, `derived.isCompletedExceptionally()` là `true`. Nhưng `derived.isCancelled()` thường là `false` do nó hoàn tất bất thường bằng wrapper được truyền từ source, **không phải** chính stage đó được đặt canceled. Không viết logic “nếu `isCancelled()` là false thì chắc chắn không liên quan cancellation”; kiểm tra `cause` của stage khi cần phân loại nguyên nhân gốc.

Với `get()` ở dependent stage, wrapper báo lỗi thường là `ExecutionException`, có thể chứa nguyên nhân `CancellationException`. Đừng giả định một khuôn exception đơn giản áp dụng cho mọi tổ hợp stage.

## 8. Cancellation ảnh hưởng dependent stages như thế nào?

Các stage nối từ future đã bị hủy tuân thủ semantics hoàn tất của `CompletionStage`:

| Stage | Khi nguồn canceled | Ý nghĩa |
|---|---|---|
| `thenApply(fn)` | Không gọi `fn` theo nhánh thành công; stage phụ thuộc hoàn tất bất thường | Không làm computation thành công |
| `thenCompose(fn)` | Không gọi `fn` của nhánh thành công; stage phụ thuộc lỗi | Hủy ở nguồn lan theo kênh lỗi |
| `thenAccept`, `thenRun` | Action chỉ thuộc nhánh thành công nên không chạy | Side effect của action không xảy ra từ completion thất bại |
| `exceptionally(fn)` | Callback nhận lỗi và có thể trả giá trị dự phòng cho **stage mới** | Hữu ích nếu cancellation được coi là fallback hợp lệ |
| `handle((value, error) -> ...)` | Được gọi với thông tin thất bại để tạo kết quả mới | Có thể phân loại cancellation riêng |
| `whenComplete((value, error) -> ...)` | Quan sát lỗi, thường giữ nguyên completion bất thường | Thích hợp log/metrics, không mặc nhiên recover |

Một stage `exceptionally` có thể phục hồi cả lỗi nghiệp vụ và cancellation. Điều này **có thể không đúng với ý định người dùng**: hủy một yêu cầu đôi khi phải dừng toàn bộ pipeline, trong khi fallback lại khiến downstream tiếp tục như thành công. Vì thế cần xem `CancellationException` có nên được propagate hay chuyển thành giá trị “cancelled” theo API.

Ví dụ:

~~~java
// Trích đoạn: fallback cho lỗi thường, nhưng vẫn giữ cancellation.
CompletableFuture<String> recovered =
        source.exceptionally(error -> {
            Throwable root = error;
            if (root instanceof CompletionException && root.getCause() != null) {
                root = root.getCause();
            }
            if (root instanceof CancellationException) {
                throw new CompletionException(root);
            }
            return "fallback";
        });
~~~

Đây là ví dụ chính sách tại tầng ứng dụng. Vì callback phục hồi ném `CompletionException` trên nhánh cancellation, stage `recovered` tiếp tục hoàn tất bất thường thay vì trả `"fallback"`. Khi unwrap nguyên nhân, không bóc mọi lớp exception vô hạn hay bỏ mất thông tin lỗi; xử lý đúng cấu trúc theo API cụ thể.

### Hủy stage phụ thuộc có hủy nguồn không?

Không mặc nhiên. `derived.cancel(true)` chủ yếu hủy kết quả của **derived**, không tự bảo đảm task gốc được ngắt hay `source` đã bị canceled. Tương tự, hủy `source` có thể khiến các stage phụ thuộc hoàn tất bất thường, nhưng không đồng nghĩa mọi tác vụ side effect đã chạy hoặc đang chạy trong các stage khác được dừng.

Hệ thống cần **cancellation propagation** thực sự phải định nghĩa quan hệ giữa parent/child jobs, cancellation token hoặc các thao tác hủy của nguồn tài nguyên.

## 9. Khác biệt giữa cancel, completeExceptionally và obtrudeException

Một số cách hoàn tất bất thường thường xuất hiện trong mã:

~~~java
CompletableFuture<String> a = new CompletableFuture<>();
a.cancel(false);

CompletableFuture<String> b = new CompletableFuture<>();
b.completeExceptionally(new CancellationException("cancelled by user"));

CompletableFuture<String> c = new CompletableFuture<>();
c.completeExceptionally(new IllegalStateException("failed"));
~~~

- `a` biểu diễn một yêu cầu cancellation; với `CompletableFuture`, trạng thái cuối là exceptional completion bằng `CancellationException`.
- `b` cũng có thể được coi là canceled vì nguyên nhân exception thực tế là `CancellationException`.
- `c` hoàn tất bất thường bởi lỗi nghiệp vụ, nhưng không phải canceled.
- `obtrudeException(ex)` có khả năng thay đổi kết quả mà future đang giữ theo ngữ nghĩa đặc biệt của nó, kể cả khi đã hoàn tất. Không dùng nó thay `cancel`/`completeExceptionally` trong flow bình thường vì các dependent stages đã kích hoạt có thể giữ trạng thái trước đó, gây quan sát không nhất quán.

Lưu ý khi log và phân loại: không chỉ nhìn `isCompletedExceptionally()` rồi đánh dấu mọi task là failed. Phân loại cancellation, timeout, thất bại kỹ thuật và lỗi nghiệp vụ theo hợp đồng riêng.

## 10. Timeout không đồng nghĩa cancellation hay interrupt

`CompletableFuture` hỗ trợ:

- `orTimeout(timeout, unit)`: nếu future chưa hoàn tất vào hạn, nó sẽ được hoàn tất bất thường với `TimeoutException`.
- `completeOnTimeout(value, timeout, unit)`: nếu chưa hoàn tất vào hạn, nó được hoàn tất bình thường bằng giá trị `value`.
- `cancel(...)`: đưa future vào trạng thái cancellation bằng `CancellationException` khi phù hợp.

Các phương thức timeout nói trên **tác động trên chính future được gọi**, không phải luôn tạo một future độc lập mới. Completion thành công, timeout và cancellation có thể cạnh tranh nhau; kết quả nào thắng tùy thời điểm xảy ra.

~~~java
// Trích đoạn minh họa.
CompletableFuture<String> result = new CompletableFuture<>();
result.orTimeout(2, java.util.concurrent.TimeUnit.SECONDS);

// Khi quá hạn và chưa complete, join() báo CompletionException
// với nguyên nhân TimeoutException, không phải CancellationException.
~~~

**Một kết quả TimeoutException không chứng minh computation đã ngừng.** Nếu task chạy trên executor hoặc yêu cầu mạng, nó có thể đang thực hiện. Nếu muốn hủy công việc thật sau timeout, phải gọi cơ chế hủy của chính công việc đó hoặc chuyển token hủy và làm cho task hợp tác.

`completeOnTimeout("fallback", ...)` còn có thể khiến người tiêu thụ thấy thành công, dù computation nguồn bên ngoài vẫn chạy. Nếu nguồn có tác dụng phụ, phải nêu rõ trong hợp đồng để caller không giả định operation đã kết thúc thật.

## 11. Đảm bảo hủy tác vụ thật khi cần

Có nhiều chiến lược, tùy abstraction và phạm vi công việc.

### 11.1. Giữ Future thực thi thực tế

Khi kiểm soát `ExecutorService` và cần ngắt task đang chạy, một `Future<?>` từ `submit` là kênh cancellation phù hợp hơn một `CompletableFuture` trần.

~~~java
// Trích đoạn trong một ứng dụng có ExecutorService pool.
Future<?> task = pool.submit(() -> performBlockingWork());
boolean requested = task.cancel(true);
~~~

`performBlockingWork()` phải phản ứng với interrupt hoặc kiểm tra trạng thái hợp tác. Cờ `mayInterruptIfRunning` lúc này có ngữ nghĩa cho implementation `Future` mà executor trả về, nhưng `requested` vẫn không phải bảo đảm “mọi công việc đã dừng và rollback”.

### 11.2. Token hủy cho tác vụ không chặn

Với vòng tính toán không gọi API có thể bị interrupt, có thể dùng một token chẳng hạn `AtomicBoolean`:

~~~java
// Trích đoạn, task đọc token trong vòng lặp.
AtomicBoolean cancelled = new AtomicBoolean(false);

// Bên gọi yêu cầu hủy:
cancelled.set(true);

// Bên trong task:
while (!cancelled.get()) {
    doSmallUnitOfWork();
}
~~~

Bất kỳ tác vụ có thể chạy mã dài giữa hai lần đọc token đều không dừng ngay; cần chọn ranh giới kiểm tra hợp lý, giữ invariant và cleanup. Token phải được chia sẻ đúng giữa bên ra yêu cầu và tác vụ, khác với việc đơn thuần gọi `CompletableFuture.cancel(true)`.

### 11.3. Cần dừng I/O hoặc tài nguyên cụ thể

Một số thao tác không đáp ứng thread interrupt theo cách bạn mong muốn. Trong các trường hợp đó, sử dụng timeout ở client, API hủy request, đóng resource thích hợp hoặc cơ chế shutdown do thư viện cung cấp, theo Javadoc của dịch vụ ấy. Không tự ý đóng shared connection từ một callback hủy nếu nó còn đang phục vụ task khác.

### 11.4. Cancellation protocol cho API trả CompletableFuture

Một thư viện có thể trả cả result future và một đối tượng điều khiển việc hủy, hoặc cung cấp phương thức `cancelRequest(id)`. Người gọi có thể đồng thời yêu cầu hủy task thật và hoàn tất future ở trạng thái canceled theo một chính sách thống nhất. Phải giải quyết race: task có thể đã hoàn tất/commit trước khi tín hiệu hủy đến.

## 12. Interrupt, InterruptedException và restore flag

Một task hợp tác có thể chờ trên `BlockingQueue.take()`, `Thread.sleep()`, `Object.wait()`, `CountDownLatch.await()` hoặc API ngắt được. Khi nó bị interrupt, nhiều phương thức có thể ném `InterruptedException` và xóa interrupt status.

Nếu phương thức có thể khai báo `throws InterruptedException`, thường nên truyền ngoại lệ lên theo hợp đồng. Nếu không truyền được, như trong `Runnable.run()`, thường cần:

~~~java
@Override
public void run() {
    try {
        doInterruptibleWork();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return; // Thoát thay vì làm tiếp như chưa bị hủy.
    }
}
~~~

`doInterruptibleWork()` là phương thức minh họa khai báo `throws InterruptedException`. `Thread.currentThread().interrupt()` phục hồi tín hiệu, còn `return` kết thúc đường làm việc hiện tại. Việc khôi phục cờ không tự rollback thay đổi trong task trước thời điểm lỗi.

**Đừng nghĩ `CompletableFuture.cancel(true)` sẽ tự đưa task vào khối catch trên.** Với `CompletableFuture`, đối số này không được dùng để interrupt computation. Catch `InterruptedException` chỉ chạy nếu thread thực sự bị ngắt bởi một kênh thích hợp hoặc thao tác chặn ném nó vì nguyên nhân theo API.

## 13. Race giữa completion và cancellation

Giả sử một producer sắp `complete("done")`, còn một request handler gọi `cancel(true)` gần cùng thời điểm:

~~~java
// Minh họa logic cạnh tranh, các dòng không tự tạo thread.
CompletableFuture<String> result = new CompletableFuture<>();

// Producer:
boolean completed = result.complete("done");

// Request cancel:
boolean cancelled = result.cancel(true);
~~~

Kết quả phụ thuộc thứ tự thắng cuộc:

- Nếu `complete("done")` thắng khi future pending, result thành công; `cancel` gọi sau trả `false`.
- Nếu `cancel(true)` thắng trước, result canceled; `complete("done")` gọi sau trả `false`.
- Nếu result đã canceled từ trước, một lần gọi `cancel` tiếp theo vẫn có thể trả `true` theo hợp đồng lớp, dù nó không làm thêm một lần hủy tác vụ thật.

Không viết:

~~~java
// Sai nếu coi hai thao tác là nguyên tử.
if (!result.isDone()) {
    result.cancel(true);
    // Không thể khẳng định cancel đã thắng nếu bỏ qua kết quả boolean.
}
~~~

Kiểm tra `isDone()` rồi thay đổi là kiểu *check-then-act*: thread khác có thể hoàn tất xen giữa. Hãy dùng kết quả completion và xác định chính sách khi cancellation quá muộn.

**Trong sản phẩm thật, cancellation có thể đến sau commit:** API phải định nghĩa rằng “hủy yêu cầu” không nhất thiết “hủy tác dụng phụ đã hoàn tất”. Ví dụ thanh toán đã được xử lý tại hệ thống bên ngoài rồi client timeout; gọi `cancel` trên future không hoàn tiền.

## 14. Thiết kế hủy theo yêu cầu nghiệp vụ

Trước khi thiết kế API cancellation, hỏi “hủy” nghĩa là gì trong miền nghiệp vụ:

| Loại công việc | Kỳ vọng hợp lý | Cơ chế cần bổ sung |
|---|---|---|
| Tính toán thuần, không side effect | Có thể ngừng giữa các bước | Token/cờ ngắt được kiểm tra định kỳ |
| Đọc mạng | Ngừng chờ và giải phóng tài nguyên nếu client hỗ trợ | Timeout, cancel request hoặc đóng resource đúng scope |
| Ghi file | Không để lại file không hoàn chỉnh theo hợp đồng | File tạm, flush/close, atomic move khi phù hợp |
| Cập nhật DB | Giữ transaction nhất quán | Transaction, rollback trước commit; xử lý race với completion |
| Gửi email/sự kiện | Có thể không thu hồi sau khi đã gửi | Idempotency, outbox, kiểm tra trạng thái gửi |
| Thanh toán | Không được giả định có thể đảo ngược | Idempotency key, inquiry và quy trình refund/compensation rõ ràng |

Future chỉ phản ánh một phần của hệ thống. Một người dùng nhấn “Hủy” có thể yêu cầu dừng một thao tác chưa commit; nếu thao tác đã commit, hệ thống phải báo trạng thái thực và đưa ra quy trình đảo ngược được phép, không đơn giản đánh dấu UI canceled.

## 15. Lỗi thường gặp

1. **“`cancel(true)` trên CompletableFuture interrupt supplier.”** Không. `mayInterruptIfRunning` không được dùng để điều khiển computation của lớp này.
2. **“`cancel(false)` trên CompletableFuture khác căn bản `cancel(true)`.”** Không theo cơ chế interrupt của `CompletableFuture`; cả hai có cùng giới hạn không điều khiển worker.
3. **“Future canceled đồng nghĩa I/O đã dừng.”** Không. Resource ngoài có thể còn hoạt động.
4. **“Future.cancel(true) luôn dừng task ngay.”** Không. Với executor Future, có thể gửi interrupt; task vẫn cần hợp tác.
5. **“`CancellationException` là một lỗi nghiệp vụ như mọi RuntimeException.”** Nó thường biểu diễn yêu cầu hủy và nên có chính sách riêng.
6. **“`isCompletedExceptionally()` phân biệt được hủy và thất bại.”** Không. Cancellation cũng là exceptional completion.
7. **“Dependent stage isCancelled() phải là true khi nguồn canceled.”** Không. Stage phụ thuộc có thể mang `CompletionException` chứa `CancellationException`.
8. **“`join()` luôn bọc `CancellationException` trong CompletionException.”** Không với future nguồn bị hủy: nó có thể ném `CancellationException` trực tiếp.
9. **“Bắt CancellationException rồi trả thành công luôn đúng.”** Không. Điều đó có thể vô tình tiếp tục pipeline mà người dùng đã yêu cầu dừng.
10. **“`orTimeout` tự interrupt work.”** Không. Nó xử lý trạng thái completion khi quá hạn.
11. **“Chỉ cần gọi cancel, không cần dọn tài nguyên.”** Sai: còn cleanup, kết thúc executor và điều phối trạng thái nhiệm vụ.
12. **“Kiểm tra isDone trước cancel sẽ tránh được race.”** Sai: trạng thái có thể đổi giữa hai lời gọi.
13. **“Tác vụ bị cancel thì transaction tự rollback.”** Sai: completion state không cung cấp giao dịch.
14. **“Cứ bắt Throwable khi task bị hủy.”** Không nên dùng bắt quá rộng để che lỗi nghiêm trọng; phân loại cancellation/interrupt/lỗi nghiệp vụ theo hợp đồng.

## 16. Kiểm thử đáng tin cậy

Test concurrency nên kiểm tra riêng **trạng thái future** và **hành vi của worker**, không chỉ `assertThrows(CancellationException.class, future::join)`.

| Tình huống | Kiểm tra |
|---|---|
| Cancel một CompletableFuture pending | `isCancelled()`, `isDone()` và `isCompletedExceptionally()` đều đúng |
| Lấy kết quả của future canceled | `join()`/`get()` ném `CancellationException` trực tiếp theo trường hợp source |
| Stage phụ thuộc vào canceled future | CompletionException/cause hợp lý; callback nhánh thành công không chạy |
| `supplyAsync` đã chạy rồi gọi `cancel(true)` | Future canceled nhưng không được suy ra supplier bị interrupt; đo với latch |
| `ExecutorService.submit` chạy tác vụ interruptible rồi `cancel(true)` | Tác vụ quan sát interrupt và đi vào đường cleanup |
| Cancel sau khi `complete(value)` thắng | `cancel` trả `false`; giá trị cũ giữ nguyên |
| Repeated cancel trên future đã canceled | Hiểu đúng boolean và không suy diễn lần nào cũng hủy công việc mới |
| Timeout trước khi computation kết thúc | Future hoàn tất timeout, nguồn I/O vẫn có thể đang hoạt động |
| Hủy task có side effect | Dữ liệu sau hủy/commit vẫn đúng hợp đồng nghiệp vụ |
| Shutdown executor | Không rò rỉ thread, xử lý task chưa hoàn thành đúng chính sách |

Dùng `CountDownLatch`, `CyclicBarrier` hoặc điều phối thích hợp để dựng lịch thực thi có thể kiểm tra. Tránh dùng `Thread.sleep(100)` rồi đoán rằng worker đã bắt đầu. Một test pass không thay thế lập luận về race, nhưng test có đúng ranh giới giúp phát hiện giả định sai về interrupt.

## 17. Checklist triển khai an toàn

1. **Future thuộc loại nào?** `CompletableFuture`, `FutureTask` hay abstraction riêng? Đọc ngữ nghĩa `cancel` của loại thật.
2. **Cần hủy kết quả hay ngắt công việc?** Nếu cần dừng thực thi, phải có control path riêng hỗ trợ điều đó.
3. **Task có interruptible không?** Nếu không, dùng cooperative cancellation token hoặc API đóng/hủy của thư viện.
4. **Có dependent stages không?** Phân biệt cancellation trực tiếp và exception được bọc ở stage phụ thuộc.
5. **Có timeout không?** Timeout không chứng minh tài nguyên bên ngoài ngừng chạy.
6. **Completion có thể tranh chấp không?** Xử lý race giữa `complete`, `cancel`, timeout và exception.
7. **Có tài nguyên và side effect không?** Cleanup, transaction, idempotency, xác định trạng thái commit.
8. **Kênh quan sát lỗi có rõ không?** Phân loại `CancellationException`, `CompletionException`/cause, `ExecutionException`, `InterruptedException`.
9. **Test có đo trạng thái worker thật không?** Dùng synchronization primitive thay cho sleep đoán thời gian.
10. **Hợp đồng API có nói rõ “hủy” nghĩa là gì?** Caller phải hiểu quyền hủy, mức độ dừng và các việc đã thực hiện không thể đảo ngược.

## 18. Tổng kết

`CancellationException` thường báo rằng kết quả của một future đã bị hủy. Với `CompletableFuture`, `cancel(boolean)` đánh dấu hoàn tất bất thường bằng `CancellationException`; tham số **`mayInterruptIfRunning` không được dùng để ngắt computation**, kể cả khi truyền `true`. Điều này khác với những `Future` thực thi qua `ExecutorService.submit` có thể cố gắng interrupt task khi `cancel(true)`.

Một tương lai đã canceled không thể bảo đảm công việc thật đã dừng, resource đã đóng hay tác dụng phụ đã rollback. Cần tách rõ **trạng thái completion**, **tín hiệu interrupt**, **giao thức dừng tác vụ** và **bảo toàn trạng thái**. Khi tất cả được thiết kế nhất quán, ứng dụng mới có thể báo và xử lý cancellation chính xác.

### Tài liệu tham khảo

- [Java SE 17 — CompletableFuture.cancel(boolean)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html#cancel(boolean))
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CancellationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CancellationException.html)
- [Java SE 17 — Future.cancel(boolean)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html#cancel(boolean))
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 17 — Thread.interrupt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#interrupt())
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
