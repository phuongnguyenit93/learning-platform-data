# execute() so với submit() và xử lý lỗi trong Java Executor Framework

## 1. Hai cách giao việc cho executor, hai cách quan sát lỗi

Khi sử dụng **Executor Framework** trong Java, ta thường đưa một công việc vào executor bằng một trong hai phương thức:

- `execute(Runnable)`, được định nghĩa bởi interface `Executor`, **không trả đối tượng kết quả** (kiểu trả về `void`).
- `submit(...)`, được định nghĩa bởi `ExecutorService`, **trả về `Future`** để quan sát hoàn tất, lấy kết quả, nhận lỗi và gửi yêu cầu hủy.

Cả hai đều giao tác vụ cho executor theo chính sách thực thi của implementation. Với một `ThreadPoolExecutor` thông thường, task được chạy trên worker thread; nhưng không được tổng quát hóa rằng **mọi executor đều luôn chạy bất đồng bộ**: có executor chạy trong caller, và một số `RejectedExecutionHandler` cũng có thể chạy công việc trong thread gọi.

Khác biệt quan trọng nhất đối với lỗi:

- `execute(() -> { throw ...; })` với một `Runnable` trực tiếp trong `ThreadPoolExecutor`: lỗi không được callback gọi `execute` trả về như exception bất đồng bộ. Nó thường thoát khỏi `run()` của worker, được `ThreadPoolExecutor.afterExecute(Runnable, Throwable)` nhận dưới dạng tham số `Throwable` và tới cơ chế uncaught exception của thread; worker bị kết thúc bất thường và pool có thể tạo worker thay thế theo trạng thái.
- `submit(() -> { throw ...; })`: implementation thông thường bọc task trong một `FutureTask` hoặc đối tượng `RunnableFuture`. Lỗi được **ghi lại như trạng thái thất bại của Future**; `Future.get()` ném `ExecutionException` chứa nguyên nhân. Lỗi đó thường **không thoát khỏi `FutureTask.run()`** để đến `UncaughtExceptionHandler`. Khi `afterExecute` được gọi cho FutureTask, tham số `Throwable` thường là `null` dù task bên trong đã thất bại.

**Đừng nhầm:** một lời gọi `execute(...)` hoặc `submit(...)` **có thể ném `RejectedExecutionException` ngay trong thread gọi** khi executor từ chối nhận task. Đây là lỗi **giao việc**, khác với exception ném **khi task chạy**.

Bài này dùng Java 17+ và API JDK tiêu chuẩn; nội dung áp dụng cho Java concurrency nói chung.

## 2. Bảng so sánh nhanh

| Tiêu chí | `execute(Runnable)` | `submit(...)` |
| --- | --- | --- |
| Interface | `Executor` | `ExecutorService` |
| Kiểu task | `Runnable` | `Runnable` hoặc `Callable<T>` |
| Giá trị trả từ lời gọi | `void` | `Future<?>` / `Future<T>` |
| Lấy kết quả tính toán | Không có `Future` được trả | `Future.get()` lấy kết quả |
| Quan sát task hoàn tất | Cần cơ chế khác: latch, callback, queue, trạng thái riêng | `Future.isDone()`, `get()` |
| Lỗi trong task với `ThreadPoolExecutor` thông thường | Có thể thoát khỏi worker và tới uncaught handler | Thường được giữ bên trong Future; `get()` ném `ExecutionException` |
| Lỗi khi executor từ chối | Có thể ném `RejectedExecutionException` ngay | Cũng có thể ném `RejectedExecutionException` ngay |
| Hủy công việc qua kết quả trả về | Không có Future để gọi `cancel` | `Future.cancel(...)` |
| Bảo đảm thứ tự task | Không tự bảo đảm | Không tự bảo đảm |
| Có bắt buộc task chạy ở thread khác? | Không, tùy implementation/policy | Không, tùy implementation/policy |

Việc một interface có `Future` **không đồng nghĩa** bạn đã thiết kế xong xử lý lỗi. Nếu chỉ gọi `submit(task)` rồi **bỏ đối tượng Future**, lỗi trong task có thể không được ứng dụng quan sát hoặc ghi nhận như mong đợi.

## 3. Hiểu `Runnable`, `Callable` và ba overload `submit`

`Runnable.run()` không có giá trị trả về và không khai báo checked exception trong chữ ký:

```java
@FunctionalInterface
public interface Runnable {
    void run();
}
```

Đây là trích đoạn chữ ký API để giải thích, không phải định nghĩa lại interface trong dự án.

`Callable<V>.call()` trả về giá trị kiểu `V` và được khai báo `throws Exception`:

```java
@FunctionalInterface
public interface Callable<V> {
    V call() throws Exception;
}
```

`ExecutorService` có ba overload thường dùng:

1. `Future<?> submit(Runnable task)`: nếu hoàn thành bình thường, `future.get()` trả `null`.
2. `<T> Future<T> submit(Runnable task, T result)`: nếu hoàn thành bình thường, `get()` trả đúng **đối tượng `result` được cung cấp**, không phải kết quả return của `Runnable.run()`.
3. `<T> Future<T> submit(Callable<T> task)`: nếu hoàn thành bình thường, `get()` trả kết quả do `call()` sinh ra.

`Future.get()` **chờ cho đến khi task hoàn tất** hoặc gặp một sự kiện hủy/interrupt/lỗi được phản ánh qua API. `isDone()` có thể là true khi task đã hoàn tất **thành công, thất bại hoặc bị hủy**, chứ không đồng nghĩa thành công.

### Ví dụ Java 17+: ba kiểu submit và giá trị get

Tạo file `SubmitResultsDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SubmitResultsDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<?> runnable = executor.submit(() -> {
                int local = 1 + 1;
                if (local != 2) {
                    throw new AssertionError("Math error");
                }
            });

            Future<String> runnableWithResult =
                    executor.submit(() -> {}, "finished");

            Future<Integer> callable = executor.submit(() -> 40 + 2);

            System.out.println("Runnable result: " + runnable.get());
            System.out.println("Provided result: "
                    + runnableWithResult.get());
            System.out.println("Callable result: " + callable.get());
        } finally {
            executor.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SubmitResultsDemo.java
java SubmitResultsDemo
```

Đầu ra:

```text
Runnable result: null
Provided result: finished
Callable result: 42
```

`Future.get()` giúp main chờ task và có quan hệ memory consistency thích hợp: các hành động trong task xảy ra-before các hành động sau `get()` thành công trên Future tương ứng theo hợp đồng `java.util.concurrent`. Ví dụ không dựa vào thứ tự bất định của các worker vì main in kết quả sau khi gọi `get()` lần lượt.

## 4. Exception từ `execute` không truyền ngược qua lời gọi đã trả về

Xét snippet sau:

```java
try {
    executor.execute(() -> {
        throw new IllegalStateException("worker failed");
    });
} catch (IllegalStateException e) {
    System.out.println("Caught in caller?");
}
```

Đây là **snippet**, `executor` là biến có sẵn. Với `ThreadPoolExecutor` thông thường đang nhận task để chạy trên worker, `execute` có thể trả về trước khi task chạy, nên `catch` ở **caller** không bắt được exception phát sinh trên worker. Lỗi được xử lý trên chính đường thực thi của worker.

**Ngoại lệ quan trọng:** nếu sử dụng một executor **chạy task ngay trên thread gọi**, hoặc rejection policy kiểu `CallerRunsPolicy` khiến task chạy trong caller, exception của task **có thể** xuất hiện đồng bộ trên caller. Vì vậy không thể đưa ra quy tắc tuyệt đối rằng “mọi exception từ execute đều không thể bắt ở caller”; phải phân biệt **chính sách executor**.

### Java 17+: quan sát lỗi qua `UncaughtExceptionHandler` và `Future.get`

Tạo file `ExecuteVsSubmitFailure.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ExecuteVsSubmitFailure {
    public static void main(String[] args) throws Exception {
        AtomicReference<Throwable> uncaught = new AtomicReference<>();
        CountDownLatch handlerCalled = new CountDownLatch(1);

        ExecutorService pool = Executors.newSingleThreadExecutor(task -> {
            Thread t = new Thread(task, "example-worker");
            t.setUncaughtExceptionHandler((thread, error) -> {
                uncaught.set(error);
                handlerCalled.countDown();
            });
            return t;
        });

        try {
            pool.execute(() -> {
                throw new IllegalStateException("execute failure");
            });

            if (!handlerCalled.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Uncaught handler not called");
            }
            System.out.println("execute handler: "
                    + uncaught.get().getClass().getSimpleName());

            Future<?> submitted = pool.submit(() -> {
                throw new IllegalArgumentException("submit failure");
            });

            try {
                submitted.get();
            } catch (ExecutionException e) {
                System.out.println("submit get cause: "
                        + e.getCause().getClass().getSimpleName());
            }
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Chạy:

```bash
javac ExecuteVsSubmitFailure.java
java ExecuteVsSubmitFailure
```

Khi pool hoạt động bình thường, không có interrupt ngoài và không vượt thời hạn phòng vệ 5 giây:

```text
execute handler: IllegalStateException
submit get cause: IllegalArgumentException
```

**Phân tích:**

1. Thread factory đặt `UncaughtExceptionHandler` tùy chỉnh cho worker, tránh phụ thuộc vào stack trace mặc định in ra stderr.
2. `execute` nhận một `Runnable` ném `IllegalStateException`. Với pool này, lỗi không được FutureTask bắt; worker gặp uncaught exception và handler ghi lại lỗi.
3. `handlerCalled.await(...)` buộc main đợi đến khi handler đã nhận lỗi trước khi in. Latch giúp đầu ra không phụ thuộc scheduling; không chèn `sleep` để “canh” thread.
4. Pool kiểu single-thread executor duy trì khả năng chạy công việc tiếp theo, tạo worker thay thế khi cần sau khi worker trước chết bất thường.
5. `submit` bọc `Runnable` trong Future. `IllegalArgumentException` được lưu trong Future; `submitted.get()` ném `ExecutionException`, và `getCause()` trả ngoại lệ gốc.
6. Uncaught handler **không phải kênh thông thường** để thu lỗi của task do `submit` tạo, vì wrapper bắt lỗi.

Đoạn demo sử dụng một `Runnable` trực tiếp với `execute`. Nếu chính đối tượng truyền vào `execute` là `FutureTask` hoặc một wrapper tự bắt `Throwable`, cơ chế báo lỗi có thể khác: phải hiểu **đối tượng Runnable được chạy thực sự là gì**, không chỉ tên hàm giao việc.

## 5. Tại sao exception trong `submit` có thể bị “ẩn”?

Với một executor dựa trên `AbstractExecutorService`, `submit` thường chuyển task thành `RunnableFuture` bằng `newTaskFor`, sau đó gọi `execute` với wrapper ấy. `FutureTask.run()` bắt lỗi từ `Runnable`/`Callable` và lưu kết quả thất bại. Thread worker có thể **tiếp tục chạy các task sau** thay vì chết vì exception của task.

Luồng xử lý khái niệm:

```text
execute(runnable):
    caller -> executor queue -> worker.run()
                             -> lỗi thoát ra từ Runnable
                             -> afterExecute(..., throwable)
                             -> uncaught exception handling

submit(callable/runnable):
    caller -> tạo RunnableFuture/FutureTask
           -> executor queue -> worker.run(FutureTask)
                             -> FutureTask lưu kết quả/lỗi
                             -> afterExecute(..., null) thường gặp
    caller -> future.get() -> giá trị hoặc ExecutionException
```

Đây là **sơ đồ** cho việc thực thi điển hình bằng `ThreadPoolExecutor`, không phải đặc tả rằng mọi implementation `ExecutorService` phải có cùng nội bộ.

**Sai lầm phổ biến:**

```java
// Lỗi thiết kế: không giữ Future và không quan sát ngoại lệ của task.
executor.submit(() -> processOrder());
```

Nếu `processOrder()` ném exception, caller có thể không biết. Trong ứng dụng cần audit, retry, alert hoặc ghi nhận lỗi, hãy **giữ Future để quan sát** hoặc dùng lớp quản lý task có cơ chế báo cáo lỗi tập trung.

## 6. Xử lý `Future.get` đúng cách

`Future.get()` có thể có những kết quả quan trọng:

| Kết quả | API phản ánh | Cách hiểu |
| --- | --- | --- |
| Hoàn tất bình thường | Trả kết quả; với Runnable không có result là `null` | Task đã hoàn tất thành công theo hợp đồng |
| Task ném lỗi | `ExecutionException` | `getCause()` là lỗi gốc trong task |
| Future bị hủy | `CancellationException` (unchecked) | Future đang ở trạng thái canceled |
| Thread **đang chờ** bị interrupt | `InterruptedException` | Việc chờ bị ngắt; không nhất thiết task đã hủy |
| `get(timeout, unit)` hết thời gian | `TimeoutException` | Việc **chờ** hết hạn; task có thể vẫn chạy |

Khi xử lý `ExecutionException`, không được bỏ qua nguyên nhân:

```java
try {
    Result value = future.get();
    use(value);
} catch (ExecutionException e) {
    Throwable original = e.getCause();
    recordFailure(original);
}
```

Đây là snippet, `Result`, `future`, `use` và `recordFailure` thuộc ứng dụng giả định; cần xử lý thêm `InterruptedException` và `CancellationException` tại tầng thích hợp.

**Không nên làm mất interrupt:** nếu thread gọi `get` bị interrupt và tầng hiện tại không thể `throws InterruptedException`, thường gọi `Thread.currentThread().interrupt()` rồi thoát/đưa ra kết quả hủy hợp lệ. Không bắt `InterruptedException` rồi tiếp tục chờ vô hạn mà không có chính sách.

**Không nhầm thời gian chờ với cancellation:** `future.get(100, MILLISECONDS)` ném `TimeoutException` không làm task tự dừng. Nếu muốn yêu cầu hủy, caller có thể `future.cancel(true)`, nhưng đó là **yêu cầu hợp tác**, không bảo đảm worker lập tức ngừng hoặc đã rollback các side effect.

### Có cần gọi `get` trong chính worker chạy task đó không?

Nếu một task trong pool **một worker** gửi task khác vào cùng pool rồi gọi `future.get()` đợi task mới, worker có thể tự kẹt: task mới đang nằm trong queue và không có worker khác để chạy. Đây là **thread-starvation deadlock**, không phải lỗi riêng của `submit`. Không thiết kế workflow chờ lồng nhau trên pool thiếu tài nguyên.

## 7. `ThreadPoolExecutor.afterExecute` và vì sao `Throwable` có thể bằng null

`ThreadPoolExecutor` có hook:

```java
protected void afterExecute(Runnable r, Throwable t)
```

Hook chạy khi task kết thúc trên worker của pool. Với `execute` truyền một `Runnable` ném exception trực tiếp, `t` thường chứa exception đó. Nhưng với task `submit` được bọc `FutureTask`, lỗi đã bị wrapper lưu lại, nên `t` thường là `null`.

Nếu muốn ghi nhận lỗi của **cả hai cách giao việc** ở một `ThreadPoolExecutor` tùy chỉnh, cần kiểm tra trường hợp `r instanceof Future<?>` rồi lấy lỗi từ Future **nếu task đã done**. Việc gọi `get()` khi task chưa done có thể làm block worker của hook; cần guard đúng.

### Ví dụ Java 17+: thu lỗi tập trung trong afterExecute

Tạo file `AfterExecuteFailures.java`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class AfterExecuteFailures {
    static final class ObservedPool extends ThreadPoolExecutor {
        final ConcurrentLinkedQueue<String> failures =
                new ConcurrentLinkedQueue<>();

        ObservedPool() {
            super(1, 1, 0L, TimeUnit.MILLISECONDS,
                    new LinkedBlockingQueue<>(), task -> {
                        Thread t = new Thread(task, "observed-worker");
                        t.setUncaughtExceptionHandler((thread, error) -> {
                            // Hook này chỉ tránh in stack trace mặc định
                            // trong ví dụ; không thay thế logging thực tế.
                        });
                        return t;
                    });
        }

        @Override
        protected void afterExecute(Runnable task, Throwable error) {
            super.afterExecute(task, error);
            Throwable failure = error;

            if (failure == null
                    && task instanceof Future<?> future
                    && future.isDone()) {
                try {
                    future.get();
                } catch (ExecutionException e) {
                    failure = e.getCause();
                } catch (CancellationException e) {
                    failure = e;
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }

            if (failure != null) {
                failures.add(failure.getClass().getSimpleName());
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ObservedPool pool = new ObservedPool();

        try {
            pool.submit(() -> {
                throw new IllegalArgumentException("submitted");
            });
            pool.execute(() -> {
                throw new IllegalStateException("executed");
            });

            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Pool did not terminate");
            }
            System.out.println("Observed: " + pool.failures);
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac AfterExecuteFailures.java
java AfterExecuteFailures
```

Khi pool hoàn tất bình thường trong thời hạn 5 giây:

```text
Observed: [IllegalArgumentException, IllegalStateException]
```

**Giải thích:**

- Pool có đúng **một worker** và hàng đợi FIFO `LinkedBlockingQueue`, nên task submit được xử lý trước task execute.
- `submit` tạo FutureTask lưu `IllegalArgumentException`; trong hook, `error` là `null` nhưng `future.get()` ném `ExecutionException`, từ đó lấy cause.
- `execute` truyền Runnable ném `IllegalStateException`; hook nhận `error` khác null và ghi vào hàng đợi lỗi.
- Với lỗi của `execute`, worker có thể chết; ThreadPoolExecutor xử lý trạng thái worker phù hợp. Chờ `awaitTermination` giúp main chỉ in danh sách lỗi sau khi hai task đều đã được xử lý.
- `future.isDone()` là guard trước `get()` để tránh blocking không cần thiết. Tuy nhiên nếu subclass hoặc custom RunnableFuture có hợp đồng lạ, hoặc hook được thiết kế để chạy trong môi trường phức tạp, vẫn cần thận trọng.

**Giới hạn của hook:** `afterExecute` được gọi cho các task **đã thực sự chạy trên worker**. Task bị từ chối trước khi chạy sẽ không tự đi qua hook; task nằm trong queue nhưng bị `shutdownNow()` lấy ra cũng không nhất thiết được chạy. Ngoài ra, `afterExecute` không phải nơi thích hợp cho tác vụ logging nặng hoặc blocking lâu, vì nó đang chạy trên worker và có thể làm giảm throughput.

Không nên coi ví dụ như một thư viện observability đầy đủ: trong production, logging cần tránh ném exception trong hook, ghi cả context/correlation ID và tách riêng cancellation khỏi lỗi nghiệp vụ nếu cần.

## 8. Lỗi bị từ chối khi giao việc: `RejectedExecutionException`

Cả `execute` và `submit` có thể bị từ chối **ngay khi gọi**, ví dụ executor đã shutdown hoặc thread pool và hàng đợi bounded đều đầy. Với `ThreadPoolExecutor.AbortPolicy`, phương thức ném `RejectedExecutionException` trong thread gọi.

Ngược lại, `CallerRunsPolicy` có thể chạy task trong caller khi pool còn đang chạy nhưng không nhận thêm task; điều này có thể tạo backpressure nhưng cũng thay đổi luồng chạy và cách exception xuất hiện. `DiscardPolicy` hoặc `DiscardOldestPolicy` có rủi ro đánh rơi task theo chính sách; với `submit`, nếu future của task bị bỏ mà không thực thi/hoàn tất, caller đang đợi kết quả có thể bị kẹt. Chỉ sử dụng rejection policy khi hiểu rõ tác động đến business logic và hợp đồng Future.

### Java 17+: tái hiện rejection với bounded queue

Tạo file `RejectionDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class RejectionDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    releaseWorker.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            workerStarted.await();     // Worker đang chờ trong task đầu.
            pool.execute(() -> {});   // Chiếm slot duy nhất trong queue.

            boolean rejected = false;
            try {
                pool.submit(() -> 42);
            } catch (RejectedExecutionException e) {
                rejected = true;
            }

            System.out.println("Submission rejected: " + rejected);
        } finally {
            releaseWorker.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac RejectionDemo.java
java RejectionDemo
```

Đầu ra khi pool hoàn tất bình thường:

```text
Submission rejected: true
```

Một worker đang bị giữ trong task đầu bởi `releaseWorker`; hàng đợi capacity 1 đã chứa task thứ hai. Lần gọi `submit` thứ ba không còn worker hay slot nhận nên `AbortPolicy` ném `RejectedExecutionException` **ở caller**. Không có `Future` được trả thành công từ lần gọi bị từ chối ấy.

**Giao việc thất bại khác task thất bại:** `RejectedExecutionException` cần được xử lý quanh câu lệnh `submit`/`execute`, còn lỗi của task `submit` cần quan sát qua `Future.get` hoặc cơ chế riêng.

`Executors.newFixedThreadPool(n)` thường dùng hàng đợi không giới hạn về mặt cấu hình, nên không phù hợp nếu bạn cần bounded backpressure rõ ràng. Số lượng task chờ vẫn có thể tiêu thụ nhiều bộ nhớ; cân nhắc `ThreadPoolExecutor` với queue capacity và rejection policy được chọn cẩn thận.

## 9. Shutdown, interruption và cancellation

`ExecutorService` có hai phương thức vòng đời quan trọng:

- `shutdown()`: không nhận task mới; những task đã được nhận trước đó tiếp tục được xử lý theo hợp đồng của executor. **Không phải dừng ngay mọi worker.**
- `shutdownNow()`: cố gắng dừng các task đang chạy—thông thường bằng interrupt—và trả lại danh sách task đang chờ nhưng chưa được chạy. **Không bảo đảm mọi task đang chạy sẽ dừng**, đặc biệt nếu code không hợp tác với interrupt hoặc đang ở blocking point không interruptible.

`Future.cancel(false)` có thể đánh dấu Future bị hủy khi phù hợp mà không yêu cầu interrupt thread đang chạy. `Future.cancel(true)` cố gửi interrupt cho task đang chạy nếu có thread được gắn với nó, nhưng không phải cơ chế cưỡng ép rollback. `Future.get()` trên Future đã cancelled ném `CancellationException`.

Nếu task có side effect, cần xác định:

1. Hủy trước khi task chạy thì có cần trả lại quyền sở hữu công việc không?
2. Hủy khi đang ghi dở thì cleanup/compensation thế nào?
3. Interrupt đến khi đang chờ queue, lock hoặc I/O thì phản ứng ra sao?
4. Chờ kết quả quá hạn có đồng nghĩa phải yêu cầu hủy task không?
5. Có cần log trạng thái **đã nhận**, **đang chạy**, **thành công**, **lỗi**, **bị hủy** riêng biệt không?

Một cách shutdown có trách nhiệm cho ứng dụng sử dụng executor riêng là:

```java
// Snippet: executor là ExecutorService do ứng dụng sở hữu.
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            // Báo cáo worker chưa dừng, không tuyên bố shutdown thành công.
        }
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Đây là snippet về shutdown policy, không phải file độc lập. Không nên tùy tiện shutdown một executor **thuộc sở hữu của thành phần khác**, vì như vậy có thể cắt ngang task của họ.

### Task code cần hợp tác với interrupt

`submit` và `cancel(true)` sẽ không tự sửa một task chạy CPU vô hạn:

```java
// Snippet về vòng tính toán có điều kiện dừng hợp tác.
while (!Thread.currentThread().isInterrupted()) {
    processNextChunk();
}
```

Ở đây `processNextChunk()` do ứng dụng định nghĩa. Đối với thao tác blocking như `BlockingQueue.take()`, `CountDownLatch.await()`, thread có thể ném `InterruptedException`; code thường cần cleanup và restore/propagate interrupt phù hợp. Không bắt rồi nuốt exception, khiến công việc tiếp tục dù caller đã yêu cầu hủy.

## 10. Khi nào chọn `execute`, khi nào chọn `submit`?

### Nên cân nhắc `execute` khi

- Task thực sự **không có kết quả** cho caller và được quản lý bằng một hệ thống giám sát/lifecycle riêng.
- Bạn muốn dùng `Executor` interface đơn giản, không cần hợp đồng `Future`.
- Hệ thống có kênh rõ ràng để ghi nhận lỗi của Runnable (ví dụ bắt/ghi lỗi **bên trong** task, custom executor hook hoặc uncaught handler phù hợp với implementation).
- Công việc “fire-and-forget” là **đúng nghiệp vụ**, đã có đường xử lý lỗi và không chỉ bị quên sau khi giao.

Ví dụ wrapper để ghi lỗi:

```java
// Snippet: executor là Executor, task là Runnable,
// recordFailure được định nghĩa bởi ứng dụng.
executor.execute(() -> {
    try {
        task.run();
    } catch (RuntimeException e) {
        recordFailure(e);
        throw e; // Tùy chính sách: giữ cho worker biết lỗi.
    }
});
```

Đây là snippet, không phải chương trình độc lập. Việc **rethrow** có thể kích hoạt uncaught handler hoặc khiến worker kết thúc trong ThreadPoolExecutor; với một `Executor` khác phản ứng có thể khác. Không ghi lỗi hai lần nếu đã có hệ thống observability bắt từ nơi khác.

### Nên cân nhắc `submit` khi

- Cần nhận kết quả của `Callable` hoặc quan sát khi `Runnable` hoàn tất.
- Caller cần chờ task qua `get`, xử lý `ExecutionException`, dùng timeout hoặc hủy qua `Future.cancel`.
- Cần quản lý một tập task và thu thập trạng thái **thành công / thất bại / hủy** rõ ràng.
- Có một service chịu trách nhiệm **theo dõi Future** thay vì vứt Future rồi mặc định các lỗi sẽ được log.

Ví dụ quản lý nhiều task:

```java
// Snippet: executor là ExecutorService, tasks là danh sách Callable<Result>.
List<Future<Result>> futures = new ArrayList<>();
for (Callable<Result> task : tasks) {
    futures.add(executor.submit(task));
}
for (Future<Result> future : futures) {
    try {
        Result result = future.get();
        saveResult(result);
    } catch (ExecutionException e) {
        recordFailure(e.getCause());
    }
}
```

Đây là snippet, chưa có imports và khai báo `Result`/`tasks`/`saveResult`/`recordFailure`; đồng thời cần xử lý `InterruptedException`, `CancellationException`, deadline và chính sách có tiếp tục chờ sau một task thất bại hay không. Nếu cần gom kết quả theo thứ tự **hoàn thành**, `ExecutorCompletionService` có thể giúp tránh việc đợi Future đầu tiên lâu dù các task sau đã xong.

### Một quy tắc thiết kế đơn giản

**Nếu task thất bại, ai chịu trách nhiệm biết và phản ứng?**

- Nếu answer là **caller**, `submit` + `Future.get`/quản lý Future thường là thiết kế rõ nhất.
- Nếu answer là **hạ tầng hoặc task tự ghi nhận**, `execute` có thể đủ.
- Nếu **không ai** chịu trách nhiệm, cả hai cách đều thiếu chính sách xử lý lỗi.

Không có lựa chọn luôn tốt hơn. Khác biệt cốt lõi là **hợp đồng giao việc, quan sát kết quả, lỗi và lifecycle**, chứ không chỉ “hàm nào chạy nhanh hơn”.

## 11. Các sai lầm cần tránh

1. **“`execute` chạy đồng bộ, `submit` chạy bất đồng bộ.”** Sai; implementation và rejection policy quyết định thread chạy thực tế.
2. **“`submit` không bao giờ ném exception ở caller.”** Sai: `RejectedExecutionException` có thể ném **ngay lúc giao việc**; còn exception **trong task** được Future ghi lại theo implementation thông thường.
3. **“`try/catch` quanh `execute` luôn bắt lỗi task.”** Sai nếu task chạy trên worker khác; có ngoại lệ với direct/caller-runs execution.
4. **“`submit` tự log exception ra stderr.”** Sai; wrapper Future thường bắt lỗi; nếu không quan sát Future, lỗi có thể bị bỏ qua.
5. **“`Future.isDone()` true nghĩa là thành công.”** Sai: cancelled và failed đều có thể done.
6. **“`Future.get()` trả exception gốc trực tiếp.”** Thường sai: task exception được bọc trong `ExecutionException`; dùng `getCause()`.
7. **“`afterExecute` nhận Throwable khác null cho mọi task lỗi.”** Sai đối với `FutureTask` của `submit`; có thể cần kiểm tra Future.
8. **“`afterExecute` bắt cả task bị từ chối.”** Sai: task bị reject trước khi chạy không đi qua hook worker.
9. **“`Future.get(timeout)` hết hạn đồng nghĩa task đã cancel.”** Sai: timeout là trạng thái **ngừng chờ** của caller.
10. **“`cancel(true)` bảo đảm tác vụ ngừng tức thì.”** Sai: interrupt là hợp tác; task/I/O có thể không đáp ứng ngay.
11. **“`shutdownNow` dừng mọi tác vụ ngay.”** Sai: chỉ cố dừng và trả các task chưa chạy; cần kiểm tra thực tế.
12. **“Có một worker thì task gửi nested submit và get luôn chạy được.”** Sai: có thể deadlock do thiếu worker.
13. **“Dùng `DiscardPolicy` với submit là vô hại.”** Sai: Future của một task bị bỏ có thể không bao giờ hoàn thành và caller chờ mãi.
14. **“Chỉ cần bắt `Exception` trong task là xử lý được mọi lỗi.”** Không hoàn toàn: `Error` là `Throwable` nhưng không phải `Exception`; chính sách logging/lifecycle cần phân loại lỗi phù hợp, không cố nuốt lỗi hệ thống nghiêm trọng.
15. **“UncaughtExceptionHandler là cơ chế tổng quát cho mọi kiểu submit.”** Sai: task wrapper có thể lưu lỗi mà không để exception thoát ra worker.
16. **“Dùng Future đồng nghĩa đã có observability.”** Sai nếu không giữ, đọc hoặc xử lý Future ở đâu cả.
17. **“ExecutorService cần shutdown ở mọi nơi gọi submit.”** Không đúng nếu executor thuộc quyền quản lý của service khác; phải tuân thủ ownership.

## 12. Checklist triển khai ExecutorService có xử lý lỗi

1. **Task có cần kết quả không?** Chọn `Runnable` hay `Callable<T>` phù hợp.
2. **Ai sở hữu executor?** Ai chịu trách nhiệm `shutdown` và giám sát vòng đời?
3. **Chọn `execute` hay `submit` theo nghĩa vụ quan sát:** Future có được lưu và chờ/kiểm tra không?
4. **Phân biệt exception khi nhận việc và khi chạy:** catch `RejectedExecutionException` đúng ở caller; xử lý task failure qua Future/hook/logging.
5. **Đối với submit, quan sát `ExecutionException` và cause;** phân biệt cancellation, interrupt và timeout.
6. **Đối với execute, xác định cơ chế báo lỗi:** task tự xử lý, uncaught handler hay `afterExecute` tùy implementation.
7. **Nếu override `afterExecute`, xử lý `Future` an toàn:** chỉ `get` khi done; tránh làm hook blocking và không để hook tự ném lỗi.
8. **Xem rejection policy và queue capacity:** pool bounded không có slot phải có đường backpressure/retry/từ chối rõ ràng.
9. **Không chờ nested Future trên pool không đủ thread:** kiểm tra phụ thuộc task, worker count và các lock đang giữ.
10. **Thiết kế timeout, cancel, shutdown:** có chính sách khi caller ngừng chờ nhưng task còn chạy.
11. **Bảo đảm xử lý lỗi không tạo side effect trùng:** retry cần idempotency hoặc giao thức phù hợp.
12. **Kiểm thử đường thành công, thất bại, hủy, từ chối:** dùng `CountDownLatch`/bounded queue để tạo lịch có kiểm soát, không đoán timing bằng `sleep`.
13. **Đo và giám sát:** số task được nhận/chạy/xong, lỗi task, cancellation, rejection, queue backlog và thời gian chờ; ghi context để tìm được task liên quan.

**Ghi nhớ:** `execute(Runnable)` giao việc **không trả Future**; với task trực tiếp trên `ThreadPoolExecutor`, exception có thể đi qua hook/uncaught handler của worker. `submit(...)` trả **Future**, nơi chứa kết quả và lỗi để caller quan sát qua `get()`; lỗi của task thường không xuất hiện ở uncaught handler. Cả hai có thể bị từ chối **ngay khi giao việc**. Thiết kế đúng phải có người chịu trách nhiệm nhận lỗi, xử lý timeout/interrupt/cancellation và quản lý executor theo vòng đời rõ ràng.