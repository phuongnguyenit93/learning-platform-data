# Cancellation, interrupt và giới hạn của CompletableFuture

`CompletableFuture<T>` giúp xây dựng các pipeline xử lý bất đồng bộ bằng `supplyAsync()`, `thenApply()`, `thenCompose()`, `thenCombine()`, `exceptionally()` và nhiều phép kết hợp khác. Nhưng **hoàn tất một Future**, **hủy một Future**, **ngắt một thread** và **dừng công việc thực sự** là bốn chuyện khác nhau.

Điểm quan trọng nhất của bài:

> **`CompletableFuture.cancel(true)` không phải lệnh cưỡng bức ngắt thread đang tính toán.** Trong implementation `CompletableFuture` của JDK, tham số `mayInterruptIfRunning` không được dùng để điều khiển quá trình xử lý. Lệnh hủy khiến CompletableFuture chuyển sang trạng thái hoàn tất ngoại lệ do cancellation, nhưng phép tính nền có thể tiếp tục chạy, giữ tài nguyên và tạo side effect.

Đây là kiến thức **Java concurrency nói chung** (JDK 17+), không dựa trên Spring hoặc framework khác. Ta sẽ phân biệt hợp đồng từng API, dùng các chương trình Java độc lập có lệnh `javac`/`java` và stdout có thể đối chiếu.

## 1. Bốn khái niệm phải tách riêng

| Khái niệm | Ai/điều gì bị ảnh hưởng? | Có bảo đảm task dừng không? |
|---|---|---|
| `CompletableFuture.cancel(...)` | **Trạng thái hoàn tất** của CompletableFuture và các dependent stage liên quan. | **Không.** Không bảo đảm interrupt underlying computation. |
| `Thread.interrupt()` | Cờ interrupt của một **thread**; một số thao tác blocking phản hồi bằng `InterruptedException`. | **Không tuyệt đối.** Code phải hợp tác hoặc dùng API hỗ trợ interrupt. |
| `Future.get(timeout)` | Giới hạn **thời gian caller chờ kết quả** trong một lần gọi. | **Không.** Hết hạn không tự hủy task. |
| `CompletableFuture.orTimeout(...)` | Có thể **complete chính CompletableFuture bằng lỗi timeout** nếu nó vẫn chưa xong. | **Không.** Computation phía sau có thể tiếp tục. |
| `completeOnTimeout(value,...)` | Có thể complete chính CompletableFuture với **fallback value**. | **Không.** Không cắt ngang task nền. |
| Cờ dừng hợp tác / timeout I/O | Logic **thực thi công việc** tự kiểm tra điều kiện dừng. | Có thể làm task thoát theo giao thức, nhưng vẫn cần điểm kiểm tra, cleanup và quan sát termination. |

Một pipeline có thể trông như sau:

```text
Thread caller                 CompletableFuture              Worker
--------------                -----------------              -------------
supplyAsync(task) ----------> [chưa hoàn tất] -------------> task bắt đầu
      |
      +--- cancel(true) -----> [CANCELLED]                     vẫn có thể chạy
      |                                                            |
      +--- join() -----------> CancellationException                |
                                                                   v
                                                            side effect / cleanup
                                                            (chưa chắc đã xong)
```

**Không đồng nhất `isDone() == true` với `worker đã dừng` hoặc `mọi resource đã được giải phóng`.** `isDone` phản ánh terminal state của Future, không phải phép đợi toàn bộ thread/side effect.

## 2. CompletableFuture là Future nhưng cancellation có semantics riêng

`CompletableFuture<T>` implements `Future<T>` và `CompletionStage<T>`. Nó có `get()`, `get(timeout)`, `cancel()`, `isDone()` của Future, đồng thời có các method composition và các phương thức hoàn tất thủ công.

Những trạng thái phổ biến:

```text
                          [chưa hoàn tất]
                            /    |     \
                           /     |      \
                   complete(T)  completeExceptionally(e)  cancel(...)
                         |          |            |
                         v          v            v
                      success   exceptional   canceled
                         \          |            /
                          \         |           /
                               isDone = true
```

Với `CompletableFuture` chuẩn:

- `complete(value)` cố hoàn tất thành công và trả `true` nếu **lần đó thắng**.
- `completeExceptionally(error)` cố hoàn tất ngoại lệ; cũng trả boolean theo việc lần hoàn tất đó thắng.
- `cancel(mayInterruptIfRunning)` cố hoàn tất ngoại lệ bằng `CancellationException`; tham số `mayInterruptIfRunning` **không có tác dụng điều khiển interruption** đối với CompletableFuture.
- `isCancelled()` true nếu Future đã hoàn tất theo kiểu cancellation.
- `isCompletedExceptionally()` true với exceptional completion, bao gồm cancellation.
- `isDone()` true nếu completed thành công, thất bại hoặc hủy.

**Trạng thái terminal không phải nút “kill worker”.** Có thể Future đã canceled nhưng lambda đang chạy trong `supplyAsync` chưa ra khỏi method. Nếu lambda sau đó tính ra một giá trị và cố hoàn tất cùng CompletableFuture, kết quả mới thường không thay được trạng thái đã canceled.

### cancel(true) và cancel(false) trên CompletableFuture

Trong interface `Future`, `mayInterruptIfRunning` biểu thị mong muốn interrupt khi hủy một tác vụ đang chạy. Nhưng mỗi implementation có contract cụ thể. Với `CompletableFuture`, Java API nói rõ tham số này **không có tác dụng** vì interrupts không được dùng để điều khiển processing của nó.

Vì vậy:

```java
CompletableFuture<String> cf = new CompletableFuture<>();
cf.cancel(true);   // Không mang nghĩa chắc chắn ngắt worker.
```

Đây là trích đoạn; không có worker thực sự ở đây, vì `new CompletableFuture<>()` đơn giản tạo một **promise chưa hoàn tất**. Lệnh cancel chuyển trạng thái promise nếu chưa completed. Phải phân biệt promise này với một computation được tạo bằng `supplyAsync`.

## 3. Ví dụ 1 — cancel(true) không tự interrupt supplier của CompletableFuture

Ta giữ một supplier đang đợi trên `CountDownLatch` và dùng thêm các cờ ghi nhận nó có thật sự đi qua phần xử lý/cleanup không. Main hủy CompletableFuture trong khi supplier vẫn chờ latch; nếu cancellation tự ngắt worker thì `await()` sẽ nhận interrupt. Tuy nhiên, CompletableFuture không dùng tham số `true` để interrupt underlying worker.

Tạo file **`CompletableCancellationDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CompletableCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();
        AtomicBoolean workFinished = new AtomicBoolean();

        CompletableFuture<String> future =
                CompletableFuture.supplyAsync(() -> {
                    started.countDown();
                    try {
                        release.await();
                        workFinished.set(true);
                        return "actual-result";
                    } catch (InterruptedException e) {
                        interrupted.set(true);
                        Thread.currentThread().interrupt();
                        return "interrupted-result";
                    }
                }, executor);

        try {
            started.await();

            boolean cancellationAccepted = future.cancel(true);
            System.out.println("Cancel accepted: "
                    + cancellationAccepted);
            System.out.println("Future cancelled: "
                    + future.isCancelled());
            System.out.println("Work finished before release: "
                    + workFinished.get());
        } finally {
            release.countDown();
            executor.shutdown();
        }

        boolean terminated =
                executor.awaitTermination(5, TimeUnit.SECONDS);
        System.out.println("Executor terminated: " + terminated);
        System.out.println("Worker interrupted: " + interrupted.get());
        System.out.println("Underlying work finished: "
                + workFinished.get());
    }
}
```

```bash
javac CompletableCancellationDemo.java
java CompletableCancellationDemo
```

Đầu ra khi không có interruption bên ngoài và worker được lập lịch bình thường:

```text
Cancel accepted: true
Future cancelled: true
Work finished before release: false
Executor terminated: true
Worker interrupted: false
Underlying work finished: true
```

**Giải thích:**

1. `started.await()` xác nhận supplier đã bắt đầu, nhưng supplier **chưa thể thoát `release.await()`** khi latch còn đóng.
2. `future.cancel(true)` thắng completion, khiến Future báo canceled. Nó không gửi interrupt cho worker chỉ vì đối số là true.
3. Cờ `workFinished` vẫn false trước khi mở latch. Đây là bằng chứng task nền **chưa hoàn tất**, dù Future đã canceled.
4. Khi main mở latch, worker thực hiện phần còn lại, đặt `workFinished=true`. Vì không bị interrupt do cancel, cờ `interrupted` là false.
5. `awaitTermination()` được dùng để kiểm tra executor riêng đã dừng; **không** kết luận cleanup chỉ từ `future.isCancelled()`.

Ví dụ này dùng `CountDownLatch` để kiểm soát mốc thời gian, **không dùng `sleep()` đoán lịch chạy**. Nó minh họa contract của `CompletableFuture` trên JDK 17, không cho phép ta kết luận mọi Future implementation khác đều có cancellation giống vậy.

## 4. So sánh FutureTask / ExecutorService.submit(): cancel(true) có thể interrupt

Một `Future` do `ExecutorService.submit(Callable)` trên `ThreadPoolExecutor` thông thường có thể dựa trên `FutureTask`. Với `FutureTask`, `cancel(true)` có thể cố **interrupt thread thực thi** nếu task đã bắt đầu. Điều này vẫn là **yêu cầu hợp tác**: một task bỏ qua cờ interrupt hoặc blocking không phản hồi có thể tiếp tục.

### Ví dụ 2 — FutureTask trả về từ submit() nhận interrupt

Tạo file **`FutureTaskInterruptDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureTaskInterruptDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();
        AtomicBoolean cleaned = new AtomicBoolean();

        Future<String> future = executor.submit(() -> {
            started.countDown();
            try {
                neverReleased.await();
                return "not-reached";
            } catch (InterruptedException e) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
                return "interrupted";
            } finally {
                cleaned.set(true);
            }
        });

        try {
            started.await();
            System.out.println("Cancel accepted: "
                    + future.cancel(true));
            System.out.println("Future cancelled: "
                    + future.isCancelled());
        } finally {
            executor.shutdown();
        }

        boolean terminated =
                executor.awaitTermination(5, TimeUnit.SECONDS);
        System.out.println("Executor terminated: " + terminated);
        System.out.println("Worker saw interrupt: "
                + interrupted.get());
        System.out.println("Cleanup finished: " + cleaned.get());
    }
}
```

```bash
javac FutureTaskInterruptDemo.java
java FutureTaskInterruptDemo
```

Đầu ra với executor chuẩn và không bị tác động ngoài:

```text
Cancel accepted: true
Future cancelled: true
Executor terminated: true
Worker saw interrupt: true
Cleanup finished: true
```

`started.await()` đảm bảo callable đã chạy và đang đợi một latch không được mở. `cancel(true)` trên FutureTask do `submit` tạo ra cố interrupt worker; `CountDownLatch.await()` phản hồi bằng `InterruptedException`, rồi worker đi qua `finally`. Chỉ khi `awaitTermination()` trả true mới có thể dùng nó làm mốc xác nhận worker đã dừng.

So sánh hai ví dụ:

| Cùng lời gọi `cancel(true)` | `CompletableFuture.supplyAsync(...)` | `Future` từ `ExecutorService.submit(...)` |
|---|---|---|
| Chuyển trạng thái Future sang canceled | Có thể. | Có thể. |
| Đối số `true` khiến implementation thử interrupt worker | **Không**, trong CompletableFuture JDK. | **Có thể**, nếu implementation dùng FutureTask và task đang chạy. |
| Bảo đảm code đang chạy đã dừng trước khi cancel trả về | **Không.** | **Không.** |
| Bảo đảm `finally` đã xong khi `isCancelled=true` | Không. | Không. |
| Cần timeout/cleanup/resource ownership riêng | Có. | Có. |

Đừng so sánh bằng cách chỉ gọi `isDone()` ngay sau cancel; cả hai Future đều có thể báo terminal trong khi worker chưa kết thúc `finally`.

## 5. Future bị canceled thì get()/join() trả gì?

Với **chính CompletableFuture đã bị cancel**:

- `future.get()` và `future.join()` có thể ném **`CancellationException`**.
- `isCancelled()` là true.
- `isCompletedExceptionally()` cũng true.
- `complete(value)` thông thường không thể ghi đè trạng thái terminal đã canceled.

Đối với **dependent stage**, outcome khác một chút: nếu source bị cancel, dependent stage phụ thuộc vào thành công của source có thể hoàn tất ngoại lệ với một **`CompletionException` bọc `CancellationException`**. Khi đó dependent thường `isCompletedExceptionally() == true`, nhưng **không nhất thiết `isCancelled() == true`** vì nó được completed bằng ngoại lệ bọc chứ không được cancel trực tiếp.

### Ví dụ 3 — Cancellation lan tới dependent, không phải dừng upstream/downstream

Tạo file **`CancellationPropagationDemo.java`**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class CancellationPropagationDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source = new CompletableFuture<>();
        CompletableFuture<Integer> dependent =
                source.thenApply(value -> value + 1);
        CompletableFuture<Integer> fallback =
                dependent.exceptionally(error -> -1);

        source.cancel(true);

        System.out.println("Source cancelled: "
                + source.isCancelled());
        System.out.println("Dependent exceptional: "
                + dependent.isCompletedExceptionally());

        try {
            dependent.join();
        } catch (CompletionException e) {
            System.out.println("Dependent cause is cancellation: "
                    + (e.getCause() instanceof CancellationException));
        }
        System.out.println("Recovered result: " + fallback.join());

        CompletableFuture<Integer> upstream = new CompletableFuture<>();
        CompletableFuture<Integer> child =
                upstream.thenApply(value -> value * 2);

        child.cancel(true);
        upstream.complete(7);

        System.out.println("Upstream result: " + upstream.join());
        System.out.println("Child cancelled: " + child.isCancelled());
    }
}
```

```bash
javac CancellationPropagationDemo.java
java CancellationPropagationDemo
```

Đầu ra:

```text
Source cancelled: true
Dependent exceptional: true
Dependent cause is cancellation: true
Recovered result: -1
Upstream result: 7
Child cancelled: true
```

**Phân tích:**

- Trong nhánh đầu, `source.cancel(true)` complete source dưới dạng cancellation. `thenApply` không có giá trị thành công để chạy, nên `dependent` hoàn tất ngoại lệ. `exceptionally` của dependent có thể phục hồi thành giá trị -1.
- Khi gọi `dependent.join()`, exception của dependent được quan sát qua `CompletionException` có cause `CancellationException`. Đây là **lan truyền outcome**, không phải một lời yêu cầu dừng CPU của callback đã chạy.
- Trong nhánh hai, `child.cancel(true)` **không hủy ngược** `upstream`. Ta vẫn `upstream.complete(7)` và lấy được 7. Child đã canceled không cần hoàn thành phép nhân cho kết quả của mình.

**Không có quy tắc tự động “cancel một stage sẽ cancel toàn bộ pipeline”**. Người thiết kế phải xác định stage nào thuộc cùng một operation, stage nào dùng chung giữa nhiều consumer, và ai có quyền yêu cầu dừng công việc thật.

## 6. get(timeout) không hủy Future; orTimeout/completeOnTimeout là completion của Future

Ba API thường bị gọi chung là “timeout” nhưng có hợp đồng khác nhau:

| API | Caller có block không? | Trạng thái CompletableFuture có đổi không? | Underlying task có tự dừng không? |
|---|---|---|---|
| `future.get(50, MILLISECONDS)` | Có thể, tối đa khoảng 50 ms. | **Không**, chỉ vì lần chờ hết hạn. | Không. |
| `future.orTimeout(50, MILLISECONDS)` | Không chờ tại lời đăng ký timeout. | Nếu còn incomplete khi tới hạn, **complete exceptional với TimeoutException**. | Không bảo đảm. |
| `future.completeOnTimeout("fallback", 50, MILLISECONDS)` | Không chờ tại lời đăng ký timeout. | Nếu còn incomplete khi tới hạn, **complete bình thường với fallback**. | Không bảo đảm. |

`orTimeout` và `completeOnTimeout` trên CompletableFuture chuẩn **trả về chính đối tượng Future đó**, không phải một bản sao độc lập. Nếu Future được nhiều caller chia sẻ, thêm timeout từ một caller có thể ảnh hưởng outcome của những caller còn lại.

**`TimeoutException` từ `get(timeout)`** là lỗi của **lần chờ**. **`TimeoutException` do `orTimeout` dùng để complete Future** là trạng thái lỗi của **chính Future**; với `join()` caller thường thấy `CompletionException` có cause tương ứng.

### Ví dụ 4 — Ba loại timeout và trạng thái khác nhau

Tạo file **`CompletableTimeoutDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CompletableTimeoutDemo {
    public static void main(String[] args) throws Exception {
        CompletableFuture<String> waiting = new CompletableFuture<>();

        try {
            waiting.get(20, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            System.out.println("get timed out");
        }

        System.out.println("Still incomplete: " + !waiting.isDone());
        waiting.complete("late-success");
        System.out.println("Later result: " + waiting.join());

        CompletableFuture<String> timedOut = new CompletableFuture<>();
        timedOut.orTimeout(20, TimeUnit.MILLISECONDS);

        try {
            timedOut.join();
        } catch (CompletionException e) {
            System.out.println("orTimeout cause: "
                    + e.getCause().getClass().getSimpleName());
        }

        CompletableFuture<String> fallback = new CompletableFuture<>();
        fallback.completeOnTimeout(
                "fallback", 20, TimeUnit.MILLISECONDS);
        System.out.println("Fallback result: " + fallback.join());
    }
}
```

```bash
javac CompletableTimeoutDemo.java
java CompletableTimeoutDemo
```

Kết quả:

```text
get timed out
Still incomplete: true
Later result: late-success
orTimeout cause: TimeoutException
Fallback result: fallback
```

Không có worker tính toán trong ví dụ này; các Future được tạo thủ công ở trạng thái incomplete. Vì vậy việc `get(20, ...)` đầu tiên và cơ chế hoàn tất timeout sau đó không bị cuộc đua với kết quả từ tác vụ khác.

Trong chương trình có `supplyAsync` thật, **timeout ở CompletableFuture không chặn task đang chạy**. Task đó có thể hoàn thành sau khi Future đã được đánh dấu timeout; completion sau không ghi đè được terminal state bằng cách hoàn tất thông thường.

## 7. Ví dụ 5 — orTimeout trả về nhưng supplier vẫn chưa ngừng

Để chứng minh câu trên, ta chạy một supplier chờ latch. Main đăng ký `orTimeout`, đợi stage kết thúc ngoại lệ, kiểm tra task chưa hoàn tất, rồi mới mở latch cho worker đi tiếp.

Tạo file **`TimeoutDoesNotStopWorker.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class TimeoutDoesNotStopWorker {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean workerFinished = new AtomicBoolean();

        CompletableFuture<String> result =
                CompletableFuture.supplyAsync(() -> {
                    started.countDown();
                    try {
                        release.await();
                        workerFinished.set(true);
                        return "real-result";
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return "interrupted";
                    }
                }, executor);

        try {
            started.await();
            result.orTimeout(20, TimeUnit.MILLISECONDS);
            try {
                result.join();
            } catch (CompletionException e) {
                System.out.println("Timed out: "
                        + (e.getCause() instanceof TimeoutException));
            }
            System.out.println("Worker finished before release: "
                    + workerFinished.get());
        } finally {
            release.countDown();
            executor.shutdown();
        }

        boolean terminated = executor.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Executor terminated: " + terminated);
        System.out.println("Worker finished after release: "
                + workerFinished.get());
    }
}
```

```bash
javac TimeoutDoesNotStopWorker.java
java TimeoutDoesNotStopWorker
```

Đầu ra khi worker không bị external interrupt:

```text
Timed out: true
Worker finished before release: false
Executor terminated: true
Worker finished after release: true
```

`started.await()` đảm bảo supplier đã vào `release.await()`. Khi latch còn đóng, supplier không thể trả `real-result`. Vì thế `orTimeout(20,...)` làm Future exceptional, `join()` báo `CompletionException` bọc TimeoutException, nhưng **worker chưa đi qua phần xử lý**. Main mở latch rồi chờ termination; worker sau đó mới thực sự ra khỏi lambda.

Trong hệ thống thực tế, task có thể đang xử lý database/network và không thể “mở latch” để dừng. Cần timeout của chính I/O, cancellation protocol và cleanup trong task.

## 8. InterruptedException: caller đang get bị ngắt không có nghĩa Future bị cancel

`CompletableFuture.get()` và `get(timeout)` là các lời chờ có thể bị interrupt. Nếu **thread đang đợi** bị interrupt, method có thể ném `InterruptedException`. Nó **không tự complete Future là canceled** và không gửi interrupt cho thread đang thực hiện supplier.

Đối với `join()`, hợp đồng không khai báo `InterruptedException`; đây là lời chờ **không phản hồi interrupt bằng checked exception giống get**. Nếu caller cần bảo toàn khả năng hủy/chấm dứt chờ, phải chọn API đúng và quản lý interrupt có chủ đích.

### Ví dụ 6 — Ngắt thread chờ, Future vẫn còn dùng được

Tạo file **`InterruptedWaiterDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptedWaiterDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> future = new CompletableFuture<>();
        CountDownLatch waiterReady = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean();

        Thread waiter = new Thread(() -> {
            waiterReady.countDown();
            try {
                future.get();
            } catch (InterruptedException e) {
                sawInterrupt.set(true);
                Thread.currentThread().interrupt();
            } catch (Exception e) {
                throw new IllegalStateException(e);
            }
        }, "waiter");

        waiter.start();
        waiterReady.await();

        waiter.interrupt();
        waiter.join();

        System.out.println("Waiter interrupted: "
                + sawInterrupt.get());
        System.out.println("Future cancelled: "
                + future.isCancelled());

        future.complete("still-usable");
        System.out.println("Future value: " + future.join());
    }
}
```

```bash
javac InterruptedWaiterDemo.java
java InterruptedWaiterDemo
```

Đầu ra:

```text
Waiter interrupted: true
Future cancelled: false
Future value: still-usable
```

Main chỉ gọi `future.complete("still-usable")` **sau khi đã `waiter.join()`**, vì vậy lời `future.get()` của waiter không thể thành công do completion. Waiter bị interrupt và thoát qua nhánh `InterruptedException`; Future vẫn incomplete và không bị cancel. Sau đó main có thể complete nó bình thường.

Một `InterruptedException` thường xóa cờ interrupt tại thời điểm ném; nếu tầng gọi **bắt và không ném tiếp**, nên cân nhắc `Thread.currentThread().interrupt()` để giữ thông tin. Nếu method được phép ném `InterruptedException` lên trên, thường tốt hơn là ném tiếp thay vì nuốt tín hiệu.

**Không xử lý bằng vòng lặp `while(true) { try { get(); } catch(InterruptedException ignored) {} }`**: cách đó bỏ qua yêu cầu dừng và có thể dẫn đến chờ vô hạn.

## 9. Cancellation có thể lan truyền outcome, nhưng không có structured cancellation tự động

Với một pipeline:

```java
CompletableFuture<User> source = loadUserAsync();

CompletableFuture<String> label = source
        .thenApply(user -> user.name())
        .thenApply(String::toUpperCase);
```

Đây là trích đoạn giả định `User`, `loadUserAsync` được định nghĩa.

Nếu `source` bị complete exceptional, các stage cần kết quả thành công thường **không gọi callback thành công** mà hoàn tất exceptional theo dependency. Nhưng:

- Hủy **stage nguồn** không tự hủy một request HTTP/database đang chạy nếu chính task đó không có cancel hook.
- Hủy **stage cuối** không tự hủy mọi stage upstream, đặc biệt nếu upstream còn được consumer khác dùng.
- Một dependent callback đã bắt đầu chạy có thể tiếp tục side effect dù stage phụ thuộc của nó sau đó bị cancel theo một con đường khác.
- Hủy một nhánh không đồng nghĩa `allOf`/ `anyOf` sẽ dừng mọi sibling.
- Trạng thái `CancellationException` trong Future không có nghĩa một transaction ngoài JVM đã rollback.

Nếu cần “cancel request thì toàn bộ công việc con dừng và cleanup”, phải xây giao thức **ownership + cancellation token + timeout I/O + resource cleanup + completion acknowledgement**. Một `CompletableFuture` thông thường không tự thiết lập *structured concurrency scope* cho mọi stage mà nó liên quan.

### Tác vụ dùng chung: hủy ai?

Ví dụ hai caller dùng một stage `sharedLoad`, rồi tạo hai dependent riêng. Nếu caller A hủy `sharedLoad`, caller B cũng có thể chịu exceptional outcome. Nếu chỉ A hủy dependent stage của mình, việc dùng chung nguồn của B thường không cần bị dừng.

Do đó phân biệt:

1. **Source owned by one request:** có thể có quyền dừng toàn bộ work của request.
2. **Shared source cached/deduplicated:** không nên một consumer tự ý cancel source mà consumer khác còn cần.
3. **Dependent view:** mỗi consumer có thể tạo stage kết quả riêng để xử lý lỗi/timeout mà không mutate shared source theo hợp đồng đã chọn.

Không chỉ đổi static type từ `CompletableFuture` sang `CompletionStage` rồi cho rằng caller không bao giờ có cách truy cập concrete object. Nếu cần tách quyền hoàn tất/hủy, cân nhắc `minimalCompletionStage()`, `copy()`, hoặc wrapper/API bảo vệ nguồn phù hợp, với hiểu biết rõ về `toCompletableFuture()` và quyền sở hữu.

## 10. Cooperative cancellation: dừng thật bằng tín hiệu mà worker tự đọc

Để **dừng công việc**, code phải có điểm kiểm tra. Một pattern đơn giản:

- Một `AtomicBoolean stopRequested` thuộc operation owner.
- Worker kiểm tra `stopRequested.get()` trước các bước tốn thời gian và định kỳ trong vòng lặp.
- Nếu task có blocking wait, owner phải có cách **đánh thức** task hoặc dùng timeout/chức năng cancel cụ thể.
- Worker kết thúc theo một nhánh đã xác định và cleanup trong `finally`.
- Owner đợi một mốc xác nhận **worker đã kết thúc** nếu cần đóng resource an toàn.

**Không chỉ đặt flag rồi cho rằng worker sẽ nhìn thấy ngay nếu nó đang chờ I/O vô hạn.** Cần timeout API, interrupt của một FutureTask được sở hữu đúng, đóng socket theo contract, hoặc một wake-up signal.

### Ví dụ 7 — Dừng hợp tác, Future vẫn trả kết quả có ý nghĩa

Tạo file **`CooperativeStopDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeStopDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        AtomicBoolean stopRequested = new AtomicBoolean();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch proceed = new CountDownLatch(1);
        AtomicBoolean cleaned = new AtomicBoolean();

        CompletableFuture<String> result =
                CompletableFuture.supplyAsync(() -> {
                    try {
                        started.countDown();
                        proceed.await();
                        if (stopRequested.get()) {
                            return "stopped-cooperatively";
                        }
                        return "finished-work";
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return "interrupted";
                    } finally {
                        cleaned.set(true);
                    }
                }, executor);

        try {
            started.await();
            stopRequested.set(true);
            proceed.countDown();

            System.out.println("Worker result: "
                    + result.get(5, TimeUnit.SECONDS));
        } finally {
            proceed.countDown();
            executor.shutdown();
        }

        boolean terminated = executor.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Executor terminated: " + terminated);
        System.out.println("Cleanup finished: " + cleaned.get());
    }
}
```

```bash
javac CooperativeStopDemo.java
java CooperativeStopDemo
```

Đầu ra trong điều kiện chạy bình thường:

```text
Worker result: stopped-cooperatively
Executor terminated: true
Cleanup finished: true
```

Main đặt cờ dừng **trước khi** mở latch. Worker chỉ tiến tới kiểm tra cờ sau khi latch mở, nên nó nhìn thấy yêu cầu dừng và trả trạng thái `stopped-cooperatively`. `CompletableFuture` hoàn tất **bình thường** với một outcome có ý nghĩa; không cần hủy chính promise để ra khỏi lambda.

Đây là một thiết kế hợp lệ khi nghiệp vụ cần phân biệt **đã dừng có kiểm soát** và **Future bị canceled**. Trong thực tế, có thể dùng `enum ResultStatus` hoặc sealed result type thay cho chuỗi. Phần quan trọng là có **tín hiệu thật để worker hợp tác**, không phải trông chờ vào `cancel(true)` của CompletableFuture.

## 11. Làm thế nào nếu vừa cần cancel Future vừa cần dừng worker?

Nếu phải expose khả năng hủy cho caller mà vẫn cần dừng worker, có thể tách hai handle:

- **Handle kết quả**: `CompletableFuture<Result>` cho composition và observation.
- **Handle điều khiển**: `Future<?> submittedTask` từ executor hoặc một `CancellationToken` có thể gửi tín hiệu dừng.
- **Resource owner**: đóng/kết thúc socket, stream, request hoặc task con theo protocol thực.

Ví dụ kiến trúc (trích đoạn):

```java
AtomicBoolean stop = new AtomicBoolean();
CompletableFuture<String> result = new CompletableFuture<>();

Future<?> running = executor.submit(() -> {
    try {
        while (!stop.get()) {
            doOneSmallStep();
        }
        result.complete("stopped");
    } catch (Throwable failure) {
        result.completeExceptionally(failure);
    } finally {
        cleanupResources();
    }
});

// Khi owner yêu cầu dừng:
stop.set(true);
running.cancel(true); // Có thể interrupt theo FutureTask contract.
result.cancel(false); // Chỉ nếu muốn công bố trạng thái canceled.
```

Đây là **phác thảo**, cần định nghĩa `doOneSmallStep`, `cleanupResources` và imports; không phải chương trình độc lập. Một điểm cần lưu ý: nếu hủy `result` ngay, caller **không còn dùng result để chờ cleanup**. Cần thêm tín hiệu `done/terminated` hoặc đợi shutdown executor/resource owner để xác minh kết thúc.

Với `FutureTask.cancel(true)`, ngay cả khi interrupt được gửi, task có thể bỏ qua interrupt. Nên kết hợp tín hiệu stop hợp tác và timeout của API bên trong, không gọi `Thread.stop()`.

**Lỗi thiết kế khác:** nếu owner hủy `running` **trước khi task bắt đầu**, runnable có thể chưa bao giờ chạy; đoạn `finally` **bên trong runnable** cũng chưa chạy. Nếu resource được cấp phát bên ngoài runnable, owner phải cleanup theo đường riêng. Đừng chỉ dựa vào `finally` của một task có thể chưa start.

## 12. Resource cleanup, try-with-resources và side effects

Cancellation đặc biệt khó khi task sở hữu dữ liệu ngoài JVM:

```text
Caller timeout/cancel
         |
         v
CompletableFuture completed exceptionally
         |
         +-- worker có thể còn sử dụng HTTP/DB connection
         +-- callback có thể còn ghi file
         +-- transaction bên ngoài có thể đã commit
         +-- dependent task khác có thể còn chạy
```

Những nguyên tắc:

1. Đặt **`try/finally` hoặc `try-with-resources` trong worker** quanh resource nó mở và sở hữu.
2. Dùng **timeout tại tầng I/O** (connect/read/request) chứ không chỉ timeout của lời `get()`.
3. Nếu muốn ngừng I/O, dùng API hủy/đóng tài nguyên theo hợp đồng của library cụ thể.
4. Đừng đóng resource từ caller ngay khi `future.isDone()` nếu worker vẫn có thể đang sử dụng nó; cần ownership và completion acknowledgement.
5. Nếu retry sau timeout, cần **idempotency key** hoặc giao thức tránh side effect trùng; Future không rollback giao dịch.
6. Nếu cleanup có thể thất bại, có đường quan sát exception/metrics riêng; cancellation của Future có thể làm lỗi cleanup không xuất hiện ở lời `get()` của nó.
7. Quản lý executor và dependent callbacks để không shutdown sớm khi các bước async cần thiết chưa chạy.

Không có một flag hoặc một lời `cancel()` đơn lẻ có thể bảo đảm “mọi tài nguyên, trên mọi thread và hệ thống ngoài, đã trở lại trạng thái ban đầu”.

## 13. Executor lifecycle và khác biệt shutdown()/shutdownNow()

Với executor riêng do ứng dụng tạo:

```java
ExecutorService executor = Executors.newFixedThreadPool(4);

try {
    // Nộp công việc; giữ handle, timeout và cancellation contract.
} finally {
    executor.shutdown();
}
```

Đây là trích đoạn. `shutdown()` ngừng nhận tác vụ mới, nhưng **cho tác vụ đã nhận được phép hoàn tất**. Nó không tự cancel một `CompletableFuture` đang chờ phụ thuộc.

`shutdownNow()` cố gửi interrupt tới các worker và trả danh sách task chưa bắt đầu theo hợp đồng của executor, nhưng **không bảo đảm các task đang chạy lập tức dừng**. Với các callback hoặc các stage `thenApplyAsync(..., executor)` chưa được submit, việc shutdown executor quá sớm có thể làm chúng bị **rejected** và dependent stage hoàn tất exceptional thay vì chạy bình thường.

`awaitTermination(timeout, unit)` cho owner một mốc chờ có giới hạn. Trả `false` nghĩa pool chưa terminated trong thời gian đó; không được in “cleanup hoàn tất” chỉ vì đã gọi phương thức. Trong shutdown code, nếu caller bị interrupt, thường nên bảo toàn interrupt signal và có chính sách dừng phù hợp.

**Common pool:** `CompletableFuture.supplyAsync(...)` không chỉ định executor thường dùng `ForkJoinPool.commonPool()` theo chính sách JDK, nên đừng cố shutdown common pool như tài nguyên thuộc một request. Nếu cần cancellation/resource isolation/metrics rõ, truyền một executor do thành phần của bạn sở hữu.

## 14. Concurrent completion races: success, error, timeout, cancel

Một CompletableFuture có thể có nhiều đường cạnh tranh để hoàn tất:

```text
                       CompletableFuture chưa hoàn tất
                                   |
                 +-----------------+------------------+
                 |                 |                  |
          worker complete(T)  orTimeout(...)      caller cancel(...)
                 |                 |                  |
                 +-----------------+------------------+
                                   |
                        Một terminal completion thắng
```

Trong các trường hợp thông thường, chỉ một trong `complete`, `completeExceptionally`, `cancel` thắng lúc Future chưa complete. Các lời hoàn tất sau trả false hoặc không thay outcome. Scheduler có thể quyết định **đường nào thắng** nếu result đến sát deadline.

Vì vậy không viết test kiểu:

```java
Thread.sleep(50);
assert future.isCancelled();
```

rồi cho là nó xác định; lịch chạy hệ điều hành và JVM có thể làm sai. Hãy dùng `CountDownLatch` hoặc Future chưa hoàn tất thủ công để điều phối chính xác các điều kiện khi test.

Nếu timeout và completion thực xảy ra gần đồng thời, application phải **chấp nhận ranh giới race**: có lần Future hoàn tất bằng giá trị, có lần timeout thắng, tùy điều kiện và thứ tự linearization thực tế. Không suy `orTimeout(100ms)` là đồng hồ tuyệt đối chính xác tới từng nanosecond.

### CancellationException và CompletionException trong dependent stage

Đường exception nên phân loại rõ:

- Direct `CompletableFuture.cancel()` rồi `get()/join()` trên **chính Future**: `CancellationException`.
- Lỗi của callback/supplier hoặc `completeExceptionally`: `join()` thường đưa ra `CompletionException` chứa cause; `get()` đưa ra `ExecutionException` chứa cause.
- Source bị cancel và dependent stage chỉ phụ thuộc success: dependent có thể exceptional với `CompletionException` bọc `CancellationException`.
- `get(timeout)` trên Future **chưa hoàn tất** khi hết hạn: `TimeoutException` trực tiếp từ lần đợi.
- `orTimeout` đã hoàn tất Future với lỗi timeout: `join()` thường ném `CompletionException` chứa TimeoutException, còn `get()` ném `ExecutionException` chứa TimeoutException.
- Caller bị interrupt trong `get()`: `InterruptedException`, **không** có nghĩa source bị cancel.

Gộp tất cả thành một thông báo “task failed” làm hỏng logic retry, alerting và khả năng theo dõi vận hành.

## 15. Hạn chế của CompletableFuture ngoài cancellation

`CompletableFuture` rất hữu ích cho composition nhưng không tự đảm nhiệm toàn bộ orchestration:

| Giới hạn | Hậu quả | Hướng thiết kế |
|---|---|---|
| `cancel(true)` không điều khiển interrupt task nền. | Worker có thể vẫn chạy/giữ resource. | Cancellation token, FutureTask handle, API hủy của I/O. |
| `orTimeout` chỉ complete Future. | Task thật có thể vẫn tạo side effect sau deadline. | Deadline được truyền vào task và I/O timeout. |
| Không tự cancel toàn bộ upstream/sibling/dependent đang chạy. | Công việc vô ích tiếp tục khi caller đã bỏ cuộc. | Ownership và cancellation graph riêng. |
| `allOf/anyOf` không mặc nhiên hủy các Future còn lại. | Sibling task còn chạy dù aggregator completed. | Dọn từng task cần thiết theo policy. |
| Callback non-Async có thể chạy trên completing thread. | Callback nặng làm chậm thread không mong muốn. | `*Async(..., executor)` có chủ đích. |
| Callback Async phụ thuộc executor đang hoạt động. | Shutdown/rejection có thể làm stage exceptional. | Quản lý lifecycle để dependent được chạy. |
| `join()` có thể block vô thời hạn. | Thread caller bị giữ nếu stage không hoàn tất. | Timed `get`, timeout/deadline tổng, composition. |
| Completion không bảo đảm I/O hoặc transaction đã rollback. | Retry có thể nhân đôi side effect. | Idempotency, transaction, deduplication. |
| Kết quả Future không phải stream nhiều event. | `complete` nhiều lần không phát chuỗi kết quả. | Dùng queue/publisher phù hợp cho event stream. |
| API cho phép caller `complete` vào Future nội bộ. | Caller có thể thay đổi kết quả trái ownership. | Trả `CompletionStage` view phù hợp, bảo vệ quyền hoàn tất. |

**Không có “structured cancellation” tự động chỉ vì tạo chuỗi `thenCompose` hay `thenCombine`.** Bạn đang tạo các dependent stages về kết quả, không nhất thiết tạo cây sở hữu tài nguyên và vòng đời.

## 16. Java Memory Model: completion và publication khác worker termination

Với một `Future`, hành động của asynchronous computation có quan hệ **happens-before** với các hành động xảy ra trong thread khác **sau khi lấy kết quả qua `Future.get()`** tương ứng. Đồng bộ hóa của `CompletableFuture` cho phép dependent stage nhận kết quả đã công bố theo completion mechanism.

Tuy nhiên:

- `future.get()` thành công bảo đảm bạn đã quan sát completion/result của Future; **không** cho phép giả định mọi worker/sibling bên ngoài Future đã hoàn tất.
- Khi Future bị **cancel sớm**, worker có thể tiếp tục mutation **sau** khi future đã terminal; những mutation chưa diễn ra lúc đó không thể tự được coi là đã hoàn tất hay hiển thị.
- `AtomicBoolean` cancellation token có ngữ nghĩa volatile read/write: worker đọc cờ có thể thấy yêu cầu dừng đúng theo JMM, nhưng cần thật sự **đọc cờ**.
- `CountDownLatch.countDown()/await()`, `Thread.join()` và các primitive đồng bộ khác có hợp đồng happens-before tương ứng, phù hợp để kiểm thử mốc “worker đã tới đây” hoặc “worker đã xong”.
- `CompletableFuture` không biến một `ArrayList` bị nhiều callback mutate đồng thời thành thread-safe.

Lựa chọn an toàn thường là kết quả immutable, ownership rõ ràng, một cancellation flag riêng cho operation, và một tín hiệu **task termination** độc lập nếu cần đóng tài nguyên sau khi cancel result future.

## 17. Thiết kế API có quyền hủy: một mô hình hợp lý

Nếu cung cấp `CompletionStage<Result>` cho caller, hãy quyết định quyền của caller:

- Caller được **ngừng chờ**, nhưng computation phải tiếp tục vì người khác cần?
- Caller được **hủy operation** và yêu cầu worker thoát?
- Caller được **nhận fallback** khi timeout, trong khi operation nền vẫn chạy?
- Caller cần đợi đến **khi cleanup thực sự xong**?

Có thể tách ba tín hiệu:

```text
Operation handle
   |
   +-- CompletionStage<Result> outcome   -> kết quả/exception theo contract
   +-- requestCancel()                     -> yêu cầu dừng công việc thực
   +-- CompletionStage<Void> terminated    -> worker/resource cleanup xong
```

Đây là **mô hình thiết kế**, không phải một interface API JDK có sẵn. Nó làm rõ rằng **hủy việc nhận kết quả** và **đóng công việc thật** là hai nhu cầu khác nhau. Nếu caller không sở hữu source computation, requestCancel có thể chỉ hủy phần việc riêng thay vì dừng shared source.

Trường hợp đơn giản không cần ba handle riêng: nếu task luôn kết thúc nhanh, không có side effect và owner chỉ cần giá trị, một CompletableFuture thường đủ. Chỉ thêm cancellation machinery khi bài toán có nhu cầu thực sự.

## 18. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Hướng đúng |
|---|---|---|
| Tin `CompletableFuture.cancel(true)` sẽ interrupt worker. | Worker vẫn chạy sau Future canceled. | Dùng tín hiệu dừng riêng/handle FutureTask nếu cần interrupt. |
| Xem `isCancelled()` là worker cleanup đã xong. | Đóng resource quá sớm, state bị sửa sau đó. | Đợi termination/acknowledgement khác. |
| Gọi `get(timeout)` rồi coi như hủy task. | Timeout chỉ kết thúc lượt chờ. | Quyết định tiếp tục/cancel/timeout tại task. |
| Dùng `orTimeout` làm timeout cho database/socket. | I/O vẫn có thể chạy sau Future timeout. | Đặt timeout ở I/O client và cancellation protocol. |
| Nghĩ `completeOnTimeout` không thay đổi Future nguồn. | Shared caller có thể cùng thấy fallback terminal. | Xác định rõ owner và stage được đặt timeout. |
| Hủy dependent và kỳ vọng source shared dừng. | Source còn chạy, các consumer khác vẫn dùng. | Thiết kế upstream cancellation theo ownership. |
| Hủy source rồi nghĩ mọi dependent đã chạy cũng dừng. | Callback đã start có thể tiếp tục side effect. | Cooperative stop cho tác vụ thật. |
| Gộp `CancellationException`, `InterruptedException`, `TimeoutException` thành một tình huống. | Sai retry/metrics và xử lý lifecycle. | Phân biệt future-state, caller-wait, operation-timeout. |
| Bắt `InterruptedException` và bỏ qua. | Caller có thể chờ mãi và mất tín hiệu hủy. | Ném tiếp hoặc restore flag rồi thoát. |
| Gọi `join()` vô hạn trên stage không có đường complete. | Thread bị block vô hạn. | Thiết kế deadline/completion đảm bảo và chờ có giới hạn. |
| Retry task có side effect sau timeout ngay lập tức. | Có thể thực hiện trùng vì task cũ vẫn chạy. | Idempotency/dedup, theo dõi trạng thái cũ. |
| Đóng executor trước khi các `thenApplyAsync` phụ thuộc được submit. | RejectedExecutionException, pipeline exceptional. | Quản lý vòng đời toàn bộ pipeline. |
| Để non-Async callback làm blocking I/O dài. | Completing thread bị kẹt. | Chỉ định executor phù hợp. |
| Tạo CompletableFuture nhưng không bao giờ complete. | Dependent và caller có thể chờ mãi. | Timeout/owner bảo đảm mỗi nhánh terminal. |
| Dùng CancellationToken chỉ là boolean thường không đồng bộ. | Worker có thể không thấy cập nhật theo JMM. | Dùng `AtomicBoolean`/volatile và điểm kiểm tra rõ. |
| Tự đóng resource được worker dùng ngay sau future.cancel. | Worker còn đang sở hữu resource. | Xác định ownership và tín hiệu terminated riêng. |

## 19. Checklist thực hành

1. **Phân biệt yêu cầu:** chỉ ngừng chờ kết quả, hay cần ngừng computation thực?
2. **Biết implementation:** `CompletableFuture.cancel(true)` không giống kỳ vọng `FutureTask.cancel(true)`.
3. **Thiết kế cancellation token:** dùng atomic/volatile hoặc API chuyên dụng, kiểm tra ở các điểm hợp lý.
4. **Đánh thức tác vụ block:** timeout I/O, interrupt qua handle đúng, đóng resource theo contract hoặc cơ chế wake-up.
5. **Không gọi Thread.stop():** nó không cung cấp cơ chế cleanup/invariant an toàn.
6. **Tách result và termination:** Future canceled không đồng nghĩa `finally` của worker xong.
7. **Có đường exceptional outcome:** phân biệt CancellationException, CompletionException, ExecutionException, TimeoutException và InterruptedException.
8. **Không giả định cancel tự lan ngược:** dependent bị hủy không mặc nhiên dừng source.
9. **Không giả định cancel sibling:** allOf/anyOf không đảm nhiệm toàn bộ lifecycle của các task thành phần.
10. **Xác định deadline:** get timeout khác orTimeout và khác timeout API I/O; cân nhắc SLA tổng.
11. **Quản lý executor:** dedicated pool có owner, shutdown có kiểm soát và awaitTermination có giới hạn.
12. **Bảo vệ mutable state:** completion không thay lock/atomic/immutable payload.
13. **Idempotency khi retry:** task cũ có thể còn tạo side effect sau timeout.
14. **Không để cancel che lỗi cleanup:** có log/metrics và tín hiệu termination nếu cần.
15. **Kiểm thử race deterministically:** dùng latch để tách task started, future cancelled, worker released và executor terminated.
16. **Kiểm thử task không hợp tác:** nếu task bỏ qua token/interrupt, hệ thống có chính sách giới hạn tài nguyên và cách giám sát.
17. **Xét shared computations:** caller không nên tự hủy source mà người khác còn cần.
18. **Quan sát production:** cancellation rate, timeout rate, tác vụ tồn sau cancel, queue depth, thread pool saturation, I/O latency và failures trong cleanup.

## 20. Câu hỏi tự kiểm tra

1. **`CompletableFuture.cancel(true)` có luôn interrupt worker không?** Không; với implementation JDK, mayInterruptIfRunning không có tác dụng.
2. **`FutureTask.cancel(true)` có khác không?** Có thể cố interrupt worker nếu task đang chạy; vẫn không cưỡng bức dừng mọi code.
3. **`isDone() == true` có nghĩa worker đã dừng không?** Không; Future terminal có thể xảy ra trước worker termination.
4. **`isCancelled() == true` có bảo đảm cleanup xong không?** Không.
5. **Sau `cancel()`, `join()` trên chính CompletableFuture thường ném gì?** `CancellationException`.
6. **Source canceled có thể làm dependent exceptional theo cách nào?** Dependent có thể ném `CompletionException` bọc `CancellationException`.
7. **Hủy dependent có tự hủy upstream không?** Không mặc nhiên.
8. **`get(timeout)` có mutate Future khi hết hạn không?** Không.
9. **`orTimeout()` có mutate Future không?** Có thể complete chính Future đó bằng TimeoutException.
10. **`completeOnTimeout()` có tự dừng supplier không?** Không.
11. **Nếu `get()` ném InterruptedException thì ai bị interrupt?** Thread đang đợi get; không nhất thiết worker.
12. **`join()` có khai báo InterruptedException như get không?** Không.
13. **Làm thế nào để worker hợp tác dừng?** Dùng token atomic/volatile, điểm kiểm tra, cơ chế đánh thức blocking phù hợp và cleanup.
14. **Tại sao cần termination acknowledgement riêng?** Vì result future có thể terminal trước khi worker cleanup xong.
15. **Vì sao retry ngay sau timeout có thể nguy hiểm?** Task cũ còn chạy/side effect, gây trùng công việc.
16. **`allOf` có tự cancel tất cả sibling khi một Future bị hủy không?** Không.
17. **Có nên shutdown common pool trong một request không?** Không; đó là pool dùng chung.
18. **JMM giúp gì với cancellation token?** Atomic/volatile bảo đảm visibility phù hợp, nhưng worker phải đọc cờ.
19. **Điều gì xảy ra nếu hai đường complete và cancel cạnh tranh?** Một terminal completion thắng; kết quả phụ thuộc thứ tự thực tế.
20. **Hướng thiết kế đáng tin nhất cho tác vụ I/O dài?** Đặt timeout I/O, quyền sở hữu rõ, cancellation thực ở API nguồn, cleanup và kết quả/termination riêng.

**Ghi nhớ:** **`CompletableFuture.cancel()` hủy trạng thái kết quả, không phải lệnh dừng thread.** `get(timeout)` giới hạn một lần chờ, `orTimeout()` hoặc `completeOnTimeout()` thay đổi trạng thái Future, còn dừng computation cần **cancellation hợp tác, kiểm soát I/O, quản lý tài nguyên và xác nhận termination**. Đừng suy tình trạng worker từ mỗi `isDone()` hoặc `isCancelled()`.
