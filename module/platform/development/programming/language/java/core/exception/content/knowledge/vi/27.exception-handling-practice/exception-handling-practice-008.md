# Xử lý lỗi và ngắt trong tác vụ ExecutorService (Java Core)

## 1. Mục tiêu thực hành

`ExecutorService` giúp thực thi tác vụ qua pool thread, nhưng mỗi lời gọi như `execute()`, `submit()`, `Future.get()`, `cancel(true)` và `shutdownNow()` có **hợp đồng xử lý exception và interruption khác nhau**. Nếu nhầm những hợp đồng đó, chương trình có thể mất dấu lỗi, không dừng được worker hoặc báo thành công giả sau khi tác vụ đã thất bại.

Sau bài này, bạn cần tự thực hiện được các việc:

- Chọn `execute()` hay `submit()` dựa trên cách caller cần quan sát lỗi và kết quả.
- Phân biệt **lỗi của task** với **lỗi của thread đang chờ kết quả**.
- Quan sát chính xác `ExecutionException`, `CancellationException`, `InterruptedException` và `RejectedExecutionException`.
- Thiết kế tác vụ biết hợp tác hủy qua `interrupt()`, tránh nuốt `InterruptedException` rồi tiếp tục.
- Hủy Future đúng hợp đồng và không nhầm trạng thái “future đã cancelled” với “mọi side effect đã dừng”.
- Đóng pool bằng `shutdown()`, `awaitTermination()` và `shutdownNow()` theo thứ tự có giới hạn.
- Viết test có latch/timeout để xác minh đường thất bại và đường hủy mà không dựa hoàn toàn vào `Thread.sleep`.

**Nguyên tắc chung:** ExecutorService quản lý việc xếp lịch và thực thi, **không tự biến exception thành kết quả nghiệp vụ hợp lệ, không tự rollback và không cưỡng chế mọi tác vụ dừng ngay sau interrupt**. Tác vụ, caller và owner của pool phải có trách nhiệm rõ ràng.

## 2. Bức tranh vòng đời tác vụ

Một luồng xử lý phổ biến:

```text
Caller thread
   |
   +-- executor.execute(runnable) --------> worker thread
   |                                          |
   |                                          +-- normal return
   |                                          |
   |                                          +-- throws unchecked exception
   |                                               (worker exits abnormally;
   |                                                uncaught handler may observe)
   |
   +-- Future<T> f = executor.submit(task) -> worker thread
                                              |
                                              +-- normal return
                                              |     -> Future result
                                              |
                                              +-- throws exception
                                              |     -> Future exceptional outcome
                                              |
                                              +-- interrupted/cancelled
                                                    -> cancellation contract
   |
   +-- f.get() -> value / ExecutionException /
                  InterruptedException / CancellationException
```

Hai điều dễ nhầm:

1. **Task chạy trong call stack của worker**. `try/catch` quanh câu `submit()` ở caller không tự bắt lỗi xảy ra về sau trong worker.
2. Một `Future` là **kênh quan sát hoàn tất**, không nhất thiết là bộ điều khiển dừng thực thi cưỡng chế. Caller phải quan sát `get()`, `isCancelled()`, policy hoặc trạng thái riêng; không suy từ một Boolean rằng mọi công việc đã hoàn tác.

Một pool có thể tái sử dụng luồng sau task thành công. Nếu một task được chạy bằng `execute` ném unchecked exception và thoát không được bắt, worker có thể kết thúc bất thường và executor sẽ xử lý vòng đời worker theo implementation; không nên thiết kế logic dựa vào tên hoặc danh tính thread còn giữ nguyên.

## 3. `execute()` và `submit()` báo lỗi khác nhau

### `execute(Runnable)`

`execute()` có chữ ký trả về `void`. Nếu `Runnable.run()` ném unchecked exception không được task tự xử lý, lỗi có thể đi tới **uncaught exception handler** của thread thực thi (với ThreadPoolExecutor thông thường), hoặc cơ chế báo lỗi khác do executor implementation quyết định.

```java
executor.execute(() -> {
    throw new IllegalStateException("work failed");
});
```

Đây là mảnh code có biến `executor` kiểu `ExecutorService` đã khai báo. Một handler ở caller như sau **không bắt** lỗi phát sinh bất đồng bộ trong task:

```java
try {
    executor.execute(() -> doWork());
} catch (RuntimeException ex) {
    // Có thể bắt lỗi nộp tác vụ ngay lúc gọi,
    // không phải tự động bắt mọi lỗi về sau trong doWork().
}
```

Đây là mảnh code có `doWork()` do ứng dụng định nghĩa. Nếu pool đã shutdown hoặc từ chối task, `execute()` có thể ném `RejectedExecutionException` ở luồng **nộp**. Điều đó khác với exception ném khi worker đã bắt đầu chạy.

### `submit(Runnable/Callable)`

`submit()` trả về `Future`. Với những executor phổ biến được tạo từ `Executors` hoặc `ThreadPoolExecutor`, exception phát sinh bên trong task được ghi nhận trong **Future**. Nó không nhất thiết đi qua uncaught exception handler của thread theo cách giống `execute()`.

```java
Future<Integer> future = executor.submit(() -> {
    throw new IllegalArgumentException("bad computation");
});
```

Đây là mảnh code cần import `java.util.concurrent.Future`. Khi caller gọi `future.get()`, ngoại lệ của task được thể hiện bằng `ExecutionException` với `getCause()` chứa lỗi gốc:

```java
try {
    Integer result = future.get();
    use(result);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} catch (ExecutionException ex) {
    handleTaskFailure(ex.getCause());
}
```

Đây là mảnh code trong một phương thức `void` có `future`, `use`, `handleTaskFailure` được định nghĩa, import `java.util.concurrent.ExecutionException`. **Không bỏ qua Future được trả về** khi nghiệp vụ phải biết tác vụ đã thành công hay thất bại; nếu không ai đọc/quan sát kết quả, lỗi có thể trở nên rất khó phát hiện.

`submit(Runnable)` trả `Future<?>` có `get()` nhận `null` nếu task kết thúc bình thường. `submit(Runnable, result)` dùng giá trị `result` do caller truyền khi Runnable hoàn tất bình thường. `submit(Callable<T>)` cho phép trả giá trị hoặc ném checked exception theo `Callable.call()`.

## 4. Bảng phân biệt các tín hiệu lỗi quan trọng

| Loại | Xuất hiện ở đâu | Ý nghĩa |
| --- | --- | --- |
| `IllegalStateException`/`IOException` bên trong task | Call stack worker | Lỗi nghiệp vụ, trạng thái hoặc dependency của task |
| `ExecutionException` | Luồng đang gọi `Future.get()` | Task đã hoàn tất bất thường; xem `getCause()` |
| `InterruptedException` từ `Future.get()` | **Thread đang chờ**, không phải tự động từ task | Caller bị yêu cầu ngắt trong lúc chờ |
| `CancellationException` từ `Future.get()` | Luồng đọc Future | Future đã bị hủy; không bảo đảm side effect đã rollback |
| `RejectedExecutionException` ở `execute/submit` | Thread nộp tác vụ | Executor không chấp nhận task theo chính sách |
| `TimeoutException` từ `get(timeout, unit)` | Thread đang chờ | Chờ quá hạn; task có thể vẫn đang chạy |
| `InterruptedException` từ `sleep/take/await` trong worker | Worker task | Worker nhận yêu cầu ngắt và cần quyết định dừng |
| `CompletionException` từ `CompletableFuture.join()` | Thread quan sát CompletableFuture | Wrapper cho exceptional completion của pipeline CompletableFuture |

Cần lưu ý `Future.get()` và `CompletableFuture.join()` khác nhau về wrapper và interruption. Không nên cho mọi thứ đi qua một `catch (Exception)` rồi log và tiếp tục như thành công.

## 5. Ví dụ Java 17+ hoàn chỉnh, chạy được

Ví dụ sau cố ý tách thành bốn kịch bản. Mọi pool đều được đóng trong `finally`, các điểm chờ đều có giới hạn trong phần điều phối, và `CountDownLatch` giúp xác định thứ tự mà không phải đoán thời điểm thread được scheduler chạy.

- **executeFailure:** task `execute` ném unchecked exception, `ThreadFactory` cấu hình uncaught handler để quan sát.
- **submitFailure:** task `submit` ném exception, caller đọc nguyên nhân từ `ExecutionException`.
- **cancelCooperatively:** caller gọi `Future.cancel(true)`; worker đang `sleep` bắt `InterruptedException`, khôi phục cờ và kết thúc.
- **interruptWaiter:** một thread khác chờ `Future.get()` rồi bị interrupt; task trong pool vẫn chờ riêng và tiếp tục được sau khi điều kiện chờ được giải phóng.

Lưu file **`ExecutorErrorInterruptDemo.java`**:

```java
import java.util.concurrent.*;

public class ExecutorErrorInterruptDemo {
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static void stop(ExecutorService pool) throws InterruptedException {
        pool.shutdown();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            check(pool.awaitTermination(5, TimeUnit.SECONDS), "shutdown timeout");
        }
    }

    static void executeFailure() throws InterruptedException {
        CountDownLatch observed = new CountDownLatch(1);
        ThreadFactory factory = runnable -> {
            Thread thread = new Thread(runnable, "execute-worker");
            thread.setUncaughtExceptionHandler((t, error) -> {
                System.out.println("EXECUTE_HANDLER: "
                        + error.getClass().getSimpleName());
                observed.countDown();
            });
            return thread;
        };
        ExecutorService pool = Executors.newSingleThreadExecutor(factory);
        try {
            pool.execute(() -> {
                throw new IllegalStateException("execute failed");
            });
            check(observed.await(5, TimeUnit.SECONDS), "handler did not run");
            System.out.println("EXECUTE_OBSERVED: true");
        } finally {
            stop(pool);
        }
    }

    static void submitFailure() throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> future = pool.submit(() -> {
                throw new IllegalArgumentException("submit failed");
            });
            try {
                future.get();
                throw new AssertionError("expected failure");
            } catch (ExecutionException ex) {
                System.out.println("SUBMIT_CAUSE: "
                        + ex.getCause().getClass().getSimpleName());
            }
        } finally {
            stop(pool);
        }
    }

    static void cancelCooperatively() throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        try {
            Future<?> future = pool.submit(() -> {
                started.countDown();
                try {
                    Thread.sleep(60_000);
                } catch (InterruptedException ex) {
                    boolean cleared = !Thread.currentThread().isInterrupted();
                    Thread.currentThread().interrupt();
                    System.out.println("CANCEL_WORKER: cleared=" + cleared
                            + " restored="
                            + Thread.currentThread().isInterrupted());
                } finally {
                    finished.countDown();
                }
            });
            check(started.await(5, TimeUnit.SECONDS), "worker not started");
            boolean cancelled = future.cancel(true);
            check(finished.await(5, TimeUnit.SECONDS), "worker did not finish");
            System.out.println("CANCEL_REQUESTED: " + cancelled);
            try {
                future.get();
                throw new AssertionError("expected cancellation");
            } catch (CancellationException expected) {
                System.out.println("CANCEL_GET: CancellationException");
            } catch (ExecutionException unexpected) {
                throw new AssertionError(unexpected);
            }
        } finally {
            stop(pool);
        }
    }

    static void interruptWaiter() throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch waiterStarted = new CountDownLatch(1);
        try {
            Future<String> future = pool.submit(() -> {
                workerStarted.countDown();
                release.await();
                return "result";
            });
            check(workerStarted.await(5, TimeUnit.SECONDS),
                    "worker not started");
            Thread waiter = new Thread(() -> {
                waiterStarted.countDown();
                try {
                    future.get();
                    throw new AssertionError("expected waiter interruption");
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    System.out.println("WAITER: restored="
                            + Thread.currentThread().isInterrupted()
                            + " taskDone=" + future.isDone());
                } catch (ExecutionException ex) {
                    throw new AssertionError(ex);
                }
            }, "waiter");
            waiter.start();
            check(waiterStarted.await(5, TimeUnit.SECONDS), "waiter not ready");
            waiter.interrupt();
            waiter.join(5_000);
            check(!waiter.isAlive(), "waiter did not stop");
            System.out.println("TASK_NOT_CANCELLED: " + !future.isCancelled());
            release.countDown();
            try {
                System.out.println("TASK_RESULT: " + future.get());
            } catch (ExecutionException ex) {
                throw new AssertionError(ex);
            }
        } finally {
            release.countDown();
            stop(pool);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        executeFailure();
        submitFailure();
        cancelCooperatively();
        interruptWaiter();
        System.out.println("DEMO: PASS");
    }
}
```

Chạy bằng JDK 17 trở lên từ thư mục chứa file:

```bash
javac -encoding UTF-8 ExecutorErrorInterruptDemo.java
java ExecutorErrorInterruptDemo
```

**Standard output đã kiểm chứng:**

```text
EXECUTE_HANDLER: IllegalStateException
EXECUTE_OBSERVED: true
SUBMIT_CAUSE: IllegalArgumentException
CANCEL_WORKER: cleared=true restored=true
CANCEL_REQUESTED: true
CANCEL_GET: CancellationException
WAITER: restored=true taskDone=false
TASK_NOT_CANCELLED: true
TASK_RESULT: result
DEMO: PASS
```

### Cách đọc từng trường hợp

1. `EXECUTE_HANDLER` chứng minh unchecked exception thoát khỏi `Runnable` dùng `execute()` và được custom handler quan sát. Không cần in stack trace mặc định nên output ổn định.
2. `SUBMIT_CAUSE` cho thấy `Future.get()` không ném trực tiếp `IllegalArgumentException`, mà dùng `ExecutionException` với cause.
3. `CANCEL_WORKER` xác nhận worker đang ngủ phản ứng với interrupt. `Thread.sleep` ném `InterruptedException` và xóa cờ; code kiểm tra `cleared=true` rồi `interrupt()` để đặt cờ lại.
4. `CANCEL_REQUESTED: true` cho biết yêu cầu hủy được chấp nhận cho Future đang chạy trong tình huống demo. **Đó không phải cam kết rằng mọi `cancel(true)` đều trả true hoặc mọi task sẽ dừng.**
5. `CANCEL_GET` nhận `CancellationException` trực tiếp sau khi Future đã hủy; không có kết quả thành công để đọc.
6. `WAITER` cho biết thread đang chờ `get()` đã bị interrupt và khôi phục flag; tại lúc đó, Future của worker vẫn chưa hoàn tất.
7. `TASK_NOT_CANCELLED: true` và `TASK_RESULT: result` chứng minh **ngắt một thread đang chờ Future không tự cancel task nguồn**.
8. `DEMO: PASS` xuất hiện sau khi cả bốn phần đã đi hết đường thành công của phép kiểm chứng và các pool được yêu cầu đóng.

Ví dụ dùng timeout 5 giây để phát hiện các tình huống không hoạt động như dự kiến. Trên máy quá tải hoặc môi trường bị can thiệp khác thường, test thời gian thực vẫn có thể cần timeout rộng hơn; không nên coi chính con số 5 giây là một bảo đảm của Java. Chương trình không truy cập mạng/database và không dùng dữ liệu nghiệp vụ thật.

## 6. `ThreadFactory` và `UncaughtExceptionHandler`

Với `execute()` và worker không bắt exception, một `Thread.UncaughtExceptionHandler` do `ThreadFactory` cấu hình có thể giúp ghi nhận thất bại:

```java
ThreadFactory factory = runnable -> {
    Thread thread = new Thread(runnable, "worker");
    thread.setUncaughtExceptionHandler((t, error) -> {
        reportUnexpectedFailure(error);
    });
    return thread;
};
```

Đây là mảnh code cần import `ThreadFactory` và định nghĩa `reportUnexpectedFailure`. Nó phù hợp khi tác vụ chạy theo kênh `execute` và executor implementation cho phép unchecked exception thoát khỏi worker.

**Không thể suy luận rằng uncaught handler sẽ ghi nhận mọi lỗi từ mọi task `submit()`.** Các implementation thường đóng gói task nộp qua `submit` vào `FutureTask` và giữ Throwable làm kết quả exceptional. Nếu chỉ dựa vào handler, bạn có thể bỏ sót lỗi trong Future.

Một số framework executor có quy trình báo lỗi riêng. Đừng ép một mô hình ThreadFactory lên mọi `ExecutorService` do thư viện cung cấp mà không đọc contract của chính implementation ấy.

Đừng để handler log nguyên exception từ dependency chứa password/token/PII hoặc tự ném exception làm mất thêm thông tin vận hành. Chọn event code, operation, correlation ID an toàn và nơi ghi có phân quyền.

## 7. Quan sát kết quả `Future.get()` đúng cách

Mẫu xử lý ở caller:

```java
try {
    Result value = future.get();
    use(value);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} catch (CancellationException ex) {
    recordCancelled();
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    handleTaskFailure(cause);
}
```

Đây là **mảnh code trong một phương thức trả `void`**, cần `Result` và các hàm ứng dụng cùng import từ `java.util.concurrent`.

- `InterruptedException`: **luồng chờ** đã nhận yêu cầu interrupt. Bắt rồi bỏ qua và gọi `get()` lần nữa có thể phá deadline/shutdown.
- `CancellationException`: Future đã bị hủy. Caller phải báo tình trạng CANCELLED thay vì tự coi nó là thành công hoặc lỗi tính toán thông thường.
- `ExecutionException`: task kết thúc bất thường do cause. Tùy loại cause, chính sách có thể là validation, dependency failure, bug hoặc retryable failure.
- Kết quả `get()` bình thường: Future đã hoàn tất thành công theo contract của task, nhưng điều đó **không** tự chứng minh mọi side effect bên ngoài đã được commit an toàn nếu task viết thiếu kiểm tra.

Với `future.get(timeout, TimeUnit.SECONDS)`, còn phải xử lý `TimeoutException`. Timeout của việc **chờ** không tự hủy Future; nếu muốn yêu cầu hủy task, caller phải quyết định gọi `cancel(true)` hoặc cơ chế hủy khác phù hợp, cùng chiến lược đối chiếu side effect.

### Không quan sát Future là một dạng mất dấu lỗi

```java
executor.submit(() -> sendReport());
```

Đây là mảnh code có `sendReport` được định nghĩa. Nếu không ai giữ hoặc đọc Future, việc task lỗi có thể khó nhìn thấy, nhất là khi không có logging riêng trong task. Cân nhắc `Future.get()`, `ExecutorCompletionService`, callback giám sát hoặc cơ chế job result khi hệ thống cần xác nhận trạng thái.

Nếu ứng dụng cố tình làm *fire-and-forget*, nó vẫn phải có chính sách quan sát thất bại và không được nhầm “đã nộp task” với “đã hoàn thành task”.

## 8. Xử lý `InterruptedException` ở trong worker

Interruption là cơ chế **yêu cầu hợp tác**. Khi caller gọi `thread.interrupt()` hoặc `future.cancel(true)`, worker có thể nhận tín hiệu qua cờ interrupt hoặc qua exception từ API blocking.

Một số blocking API như `Thread.sleep`, `BlockingQueue.take`, `CountDownLatch.await` hoặc `Semaphore.acquire` có thể ném `InterruptedException`. Nhiều API loại này **xóa cờ interrupt khi ném**. Vì vậy handler dưới đây nguy hiểm:

```java
while (true) {
    try {
        Job job = queue.take();
        process(job);
    } catch (InterruptedException ignored) {
        // Sai: coi như chưa hề có yêu cầu dừng.
    }
}
```

Đây là mảnh code minh họa lỗi, với `Job`, `queue` và `process` do ứng dụng định nghĩa. Sau khi cờ bị xóa, vòng loop có thể quay lại `take()` và block tiếp, khiến pool không thể dừng theo mong muốn.

Nếu phương thức có thể khai báo checked exception:

```java
Job receive(BlockingQueue<Job> queue) throws InterruptedException {
    return queue.take();
}
```

Đây là mảnh code yêu cầu import `BlockingQueue` và định nghĩa `Job`. **Truyền tiếp** giữ tín hiệu cho tầng quản lý.

Trong `Runnable.run()` không được khai báo checked exception:

```java
@Override
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            process(queue.take());
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    } finally {
        releaseResources();
    }
}
```

Đây là mảnh class có `queue`, `process`, `releaseResources`. Nó **khôi phục flag và rời task**, còn cleanup luôn được thử.

**Khôi phục cờ mà tiếp tục vòng `while(true)` không có điều kiện thoát** cũng sai: lệnh blocking tiếp theo có thể lập tức ném và xóa cờ, handler lại đặt cờ, tạo *busy loop*. Luôn kết hợp chính sách interrupt với điều khiển vòng đời.

Không bắt buộc mọi nơi phải restore cờ nếu `InterruptedException` được **truyền tiếp đúng contract** hoặc tầng đó thực sự sở hữu và xử lý xong yêu cầu hủy. Vấn đề là nuốt tín hiệu một cách vô thức.

## 9. `Thread.interrupted()` và `isInterrupted()` khác nhau

Khi viết worker loop:

- `Thread.currentThread().isInterrupted()` đọc trạng thái luồng hiện tại **không xóa cờ**.
- `Thread.interrupted()` là phương thức static đọc trạng thái **luồng hiện tại và xóa cờ**.

Đoạn này có thể vô tình xóa mất tín hiệu:

```java
if (Thread.interrupted()) {
    logSomething();
}
// Một đoạn mã sau đó có thể không còn thấy cờ interrupted.
```

Đây là mảnh code có `logSomething` do ứng dụng định nghĩa. Nếu mục tiêu là kiểm tra mà vẫn giữ yêu cầu hủy, dùng `isInterrupted()`.

Tuy nhiên, cờ interrupt **không phải lệnh kill**. Nếu task chỉ tính CPU không gọi API interruptible, nó cần kiểm tra cờ định kỳ ở những điểm phù hợp. Ví dụ:

```java
while (hasMoreWork()) {
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
    processNextChunk();
}
```

Đây là mảnh code trong phương thức có `hasMoreWork` và `processNextChunk`. Kiểm tra đủ thường xuyên để đáp ứng cancellation nhưng không cần làm ở từng phép toán nhỏ.

Nếu một tác vụ có I/O không phản ứng nhanh với interrupt, phải dùng timeout, close/cancel API của tài nguyên hoặc contract phụ thuộc thích hợp. Không chỉ dựa vào `interrupt()` để hứa một deadline cứng.

## 10. `Future.cancel(true)` là yêu cầu, không phải phép dừng cưỡng chế

`Future.cancel(boolean mayInterruptIfRunning)` yêu cầu hủy tác vụ nếu chưa hoàn tất. Giá trị `true` cho phép implementation cố ngắt thread đang chạy; `false` không yêu cầu interrupt task đang chạy. Kết quả thực tế phụ thuộc thời điểm và implementation.

Những điểm cần hiểu:

1. Nếu Future đã hoàn tất, `cancel(...)` thường không thay đổi trạng thái.
2. Với task còn đang chạy, `cancel(true)` có thể đặt trạng thái Future là cancelled và gửi interrupt cho worker.
3. **`Future.isCancelled() == true` không chứng minh worker đã dừng mọi lệnh tại thời điểm đó.**
4. Task nuốt `InterruptedException` có thể tiếp tục chạy sau khi Future đã bị cancel.
5. Một side effect đã được ghi vào DB hoặc gửi qua mạng **không tự rollback** khi cancel.
6. `future.get()` sau cancellation ném `CancellationException` trực tiếp; nó không phải luôn được bọc trong `ExecutionException`.

Mẫu:

```java
boolean accepted = future.cancel(true);
if (accepted) {
    recordCancellationRequested();
}
```

Đây là mảnh code với `future`, `recordCancellationRequested`. Tên hàm cố tình dùng **Requested**: caller nên tách yêu cầu hủy khỏi xác nhận rằng tác vụ đã đạt trạng thái cuối an toàn.

Với tác vụ thanh toán, upload, gửi email, ghi file hoặc commit database, cần chính sách idempotency/transaction/compensation riêng. Đừng tự động retry toàn bộ task sau khi Future bị cancel mà không biết thao tác có thực hiện một phần hay không.

## 11. Ngắt caller đang đợi không tự hủy worker

Một trường hợp thường bị nhầm:

```java
Future<String> future = executor.submit(this::load);
String result = future.get();
```

Đây là mảnh code trong một class có `load()` phù hợp. Nếu **luồng caller** bị interrupt trong khi `get()` đang block, `get()` có thể ném `InterruptedException`. Nhưng điều đó **không tự gọi `future.cancel(true)`** và không tự khiến worker biết caller không còn muốn kết quả.

Đường đi thực tế:

```text
worker: đang chờ dependency ............... -> hoàn tất về sau
caller: gọi future.get()
another thread: interrupt(caller)
caller: InterruptedException -> dừng chờ
worker: không tự bị interrupt bởi sự kiện đó
```

Trong demo, caller-waiter kết thúc với `taskDone=false` nhưng Future nguồn vẫn có thể trả `result` sau khi main giải phóng latch.

Nếu hủy tác vụ nguồn là chính sách mong muốn, caller có thể **cân nhắc**:

```java
try {
    return future.get();
} catch (InterruptedException ex) {
    future.cancel(true);
    Thread.currentThread().interrupt();
    throw ex;
}
```

Đây là **mảnh phương thức** khai báo `throws InterruptedException` và phù hợp kiểu return. Việc gọi `cancel(true)` có ý nghĩa khi task thực sự thuộc phạm vi hủy của caller và implementation cho phép interrupt. Trong một hệ thống có công việc dùng chung giữa nhiều request, tự cancel future nguồn khi một caller dừng chờ **có thể ảnh hưởng người dùng khác**; cần quyết định quyền sở hữu.

## 12. `shutdown()`, `shutdownNow()` và `awaitTermination()`

Ba API phục vụ lifecycle của executor:

| API | Hành vi cơ bản |
| --- | --- |
| `shutdown()` | Không nhận tác vụ mới, cho những tác vụ đã nộp được tiếp tục theo contract |
| `shutdownNow()` | Cố dừng các tác vụ đang chạy, thường bằng interrupt, và trả danh sách tác vụ chưa bắt đầu |
| `awaitTermination(timeout, unit)` | **Thread đang gọi** chờ executor chấm dứt hoặc hết hạn, có thể ném `InterruptedException` |

`shutdown()` không chờ cho mọi task hoàn thành. `shutdownNow()` là **best effort**; task bỏ qua interrupt có thể vẫn chạy. Danh sách trả về từ `shutdownNow()` không phải “mọi task đã thất bại”; nó chủ yếu mô tả những tác vụ chưa bắt đầu trong hàng chờ theo contract.

Mẫu lifecycle phổ biến (mảnh code trong phương thức sở hữu executor):

```java
executor.shutdown();
try {
    if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
            reportPoolDidNotTerminate();
        }
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Đây là đoạn có `executor`, `reportPoolDidNotTerminate` và import `TimeUnit`. Hai số 30 giây chỉ minh họa chính sách; chọn thời hạn theo SLA và đặc tính task.

Quan trọng:

- `shutdownNow()` không bảo đảm tất cả worker đã kết thúc.
- `awaitTermination()` bị interrupt là tín hiệu dành cho **caller đang quản lý shutdown**; cần restore cờ nếu handler không truyền checked exception tiếp.
- Với một pool không được dừng, phải báo rõ trạng thái thay vì in “shutdown complete”.
- Chỉ shutdown pool khi thành phần hiện tại **sở hữu** pool; đừng đóng shared executor của framework tại mỗi request.

## 13. Cấu trúc quản lý pool bằng try/finally

Một scope ngắn có thể:

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
try {
    Future<Result> first = executor.submit(this::firstJob);
    Future<Result> second = executor.submit(this::secondJob);
    return combine(first.get(), second.get());
} finally {
    executor.shutdown();
}
```

Đây là **mảnh code** trong phương thức có hợp đồng checked exception thích hợp và các hàm/kiểu ứng dụng. Nó đảm bảo **gửi yêu cầu shutdown** dù có exception. Tuy nhiên, `shutdown()` **không đợi** các worker hoàn tất. Nếu bắt buộc đợi termination hoặc cancel task còn chạy, cần mẫu `awaitTermination`/`shutdownNow` bổ sung.

Một số thiết kế có thể dùng executor làm trường lâu dài, khởi tạo ở startup và shutdown trong lifecycle của ứng dụng; không tạo pool mới cho mỗi đơn hàng rồi bỏ quên không đóng. Với shared executor, ownership và ranh giới đóng càng quan trọng.

Với JDK mới hơn có thể có tiện ích lifecycle bổ sung, nhưng ví dụ ở đây chỉ dùng API bảo đảm có trong **Java 17**. Không dựa vào `ExecutorService.close()` như phương thức phổ quát trên Java 17.

## 14. `RejectedExecutionException` không phải lỗi do body task

Nếu pool đã shutdown hoặc hàng chờ/chính sách từ chối không cho nhận thêm task:

```java
try {
    Future<?> future = executor.submit(task);
    track(future);
} catch (RejectedExecutionException ex) {
    recordNotScheduled();
}
```

Đây là mảnh code có `task`, `track`, `recordNotScheduled` và import tương ứng.

`RejectedExecutionException` xảy ra ở **lúc nộp tác vụ**, không chứng minh logic trong task đã chạy hay thất bại. Caller nên phân biệt:

- **Not accepted:** chưa được executor tiếp nhận; có thể chuyển qua hàng đợi khác theo policy.
- **Accepted but failed:** task đã được nộp và hoàn tất bất thường; xem Future.
- **Accepted then cancelled:** Future bị hủy; task có thể đã bắt đầu và có side effect.
- **Still running:** chưa biết kết quả cuối cùng.

Nếu cấu hình `RejectedExecutionHandler` đặc biệt như `CallerRunsPolicy`, một task có thể được thực thi trong **thread của caller** khi bị từ chối đưa vào pool (trong các điều kiện của policy). Khi ấy giả định “mọi task đều chạy ở worker thread riêng” cũng sai. Luôn hiểu policy và cấu hình executor đang dùng.

Không retry `submit()` vô hạn khi executor từ chối: có thể gây vòng lặp nóng, tăng tải hoặc tạo backpressure ngược. Giải pháp cần ngân sách retry và ranh giới chịu trách nhiệm rõ.

## 15. `invokeAll` và `invokeAny`: quan sát nhiều tác vụ

Ngoài `submit()`, `ExecutorService` còn có các API thực thi theo nhóm.

### `invokeAll(...)`

`invokeAll(tasks)` nộp nhiều task và chờ tất cả hoàn tất theo hợp đồng của overload. Nó trả danh sách `Future`. **Một Future có thể hoàn tất exceptional trong khi `invokeAll` vẫn trả danh sách.** Caller muốn phát hiện lỗi task phải đọc `get()` trên từng Future:

```java
List<Future<String>> futures = executor.invokeAll(tasks);
for (Future<String> f : futures) {
    try {
        consume(f.get());
    } catch (ExecutionException ex) {
        recordTaskFailure(ex.getCause());
    }
}
```

Đây là mảnh code có `tasks` là collection `Callable<String>`, các hàm ứng dụng và imports từ `java.util.concurrent` cùng `java.util.List`; phương thức bao quanh khai báo/giải quyết `InterruptedException`. Với overload có timeout, những task chưa hoàn tất khi hết thời gian có thể bị cancel theo contract; đừng đọc từng Future như thể tất cả đều thành công.

### `invokeAny(...)`

`invokeAny(tasks)` tìm **một tác vụ hoàn tất thành công** và có thể hủy những task còn lại theo contract. Nếu không có tác vụ nào thành công, caller có thể nhận `ExecutionException`; `InterruptedException` từ caller cũng cần được xử lý. Overload có timeout có thể ném `TimeoutException`.

Không suy ra task bị yêu cầu hủy đã rollback. Nếu những Callable tạo side effect, việc chạy nhiều bản song song rồi lấy kết quả thành công đầu tiên cần thiết kế idempotency, không chỉ dùng `invokeAny`.

## 16. `ExecutorCompletionService` để thu kết quả theo thứ tự hoàn tất

Khi có nhiều task hoàn tất ở các thời điểm khác nhau, có thể dùng `ExecutorCompletionService<T>`:

```java
ExecutorCompletionService<String> completion =
        new ExecutorCompletionService<>(executor);
completion.submit(this::jobA);
completion.submit(this::jobB);

for (int i = 0; i < 2; i++) {
    Future<String> done = completion.take();
    try {
        use(done.get());
    } catch (ExecutionException ex) {
        handleTaskFailure(ex.getCause());
    }
}
```

Đây là mảnh code với `jobA`, `jobB`, `use`, `handleTaskFailure` do ứng dụng định nghĩa. Method phải xử lý hoặc khai báo `InterruptedException`. `take()` chờ một Future đã hoàn tất; `get()` của Future đó mới tiết lộ kết quả hoặc lỗi. Đừng quên đếm/giữ các task đã nộp để tránh chờ nhiều lượt hơn số task có thật.

Nếu `take()` bị interrupt, đó là tình huống của thread đang lấy kết quả; policy hủy những task nguồn cần quyết định riêng. Việc Future trở thành done không có nghĩa chắc chắn thành công, vì trạng thái done gồm kết quả, lỗi và hủy.

## 17. Bắt exception trong task: khi nào nên làm?

Không phải lúc nào cũng để task ném exception. Có thể xử lý tại chính task nếu nó **có chính sách phục hồi hợp lệ**, chẳng hạn retry một thao tác mạng có giới hạn và không gây side effect trùng, chuyển một lỗi đọc cache thành giá trị cache hợp lệ hoặc cleanup tài nguyên:

```java
Callable<Result> task = () -> {
    try {
        return remoteCall();
    } catch (KnownTemporaryFailure ex) {
        return validFallback();
    }
};
```

Đây là mảnh code có `Result`, `KnownTemporaryFailure`, `remoteCall`, `validFallback` tự định nghĩa. Nếu fallback thật sự hợp lệ theo contract, Future thành công với giá trị fallback là có chủ đích. Nếu fallback chỉ để giấu lỗi, đây là **success giả**.

Không nên:

```java
Callable<Boolean> task = () -> {
    try {
        chargeAccount();
        return true;
    } catch (Exception ignored) {
        return false;
    }
};
```

Đây là mảnh code có `chargeAccount` tự định nghĩa, cố tình minh họa sai lầm. Nếu thanh toán đã commit rồi mất phản hồi, trả `false` không chứng minh chưa trừ tiền. Caller retry có thể tạo giao dịch trùng.

Nếu task có thể ném checked exception, `Callable.call()` đã cho phép điều đó. Không cần bọc mọi exception thành `RuntimeException` chỉ để vừa chữ ký như `Runnable.run()`.

## 18. Truyền lỗi qua Future không hoàn tác side effect

Một task có thể thực hiện:

```java
Callable<String> task = () -> {
    database.commit();
    notification.send();
    return "DONE";
};
```

Đây là mảnh minh họa cần định nghĩa `database`, `notification` và contract của chúng. Nếu `commit()` thành công nhưng `notification.send()` ném exception, `Future.get()` báo thất bại, nhưng database **có thể đã commit**.

Khi gặp lỗi sau một thao tác có side effect:

1. Biết bước nào hoàn tất chắc chắn, bước nào chưa xác định.
2. Dùng transaction khi cùng một tài nguyên hỗ trợ; không coi Future cancellation là rollback.
3. Với hai hệ thống, cân nhắc outbox/compensation hoặc trạng thái trung gian có thể đối chiếu.
4. Retry có hạn và có idempotency key khi phù hợp.
5. Ghi nhận error code và correlation ID không nhạy cảm để điều tra.
6. Không coi `ExecutionException` là bằng chứng “task chưa làm gì”.

Đây là lý do xử lý exception/cancel phải gắn với hợp đồng nghiệp vụ, không chỉ với type của Throwable.

## 19. `ThreadPoolExecutor.afterExecute`: điểm quan sát chuyên biệt

Trong trường hợp cần theo dõi nhiều task ở mức executor, `ThreadPoolExecutor` có hook `afterExecute(Runnable r, Throwable t)`. Tuy nhiên, **không được mặc định `t` luôn khác null khi một task `submit()` thất bại**: với `FutureTask`, exception có thể đã được giữ trong Future.

Mẫu khái niệm:

```java
@Override
protected void afterExecute(Runnable runnable, Throwable error) {
    super.afterExecute(runnable, error);
    if (error == null && runnable instanceof Future<?> future
            && future.isDone()) {
        try {
            future.get();
        } catch (CancellationException cancelled) {
            recordCancelled();
        } catch (ExecutionException failed) {
            recordTaskFailure(failed.getCause());
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        }
    } else if (error != null) {
        recordTaskFailure(error);
    }
}
```

Đây là **mảnh bên trong subclass `ThreadPoolExecutor`**, không phải chương trình độc lập; cần imports và các hàm ghi nhận lỗi. Hook phải ngắn, không chặn vô hạn, không thêm side effect không kiểm soát. Đặt `future.isDone()` giúp tránh gọi `get()` trên Future chưa hoàn tất theo những triển khai không chuẩn; trong trường hợp bình thường task vừa hoàn tất.

Đây là kỹ thuật nâng cao. Đối với ứng dụng nhỏ, **giữ và quan sát Future** thường đơn giản hơn việc kế thừa executor. Cũng phải kiểm soát logging lỗi ở hook để không ghi trùng với caller hoặc làm lộ message nhạy cảm của dependency.

## 20. Test đường lỗi và ngắt một cách xác định

Để kiểm thử executor, dùng `CountDownLatch`, `Future`, thread-safe counters, `AtomicBoolean` và timeout hơn là `Thread.sleep(100)` rồi đoán thread đã làm gì. Một test có thể đặt hai latch:

- `started`: worker đã đạt vị trí chờ/có thể bị interrupt.
- `finished`: worker đã đi qua cleanup và sắp kết thúc.

Ví dụ tối giản:

```java
CountDownLatch started = new CountDownLatch(1);
CountDownLatch finished = new CountDownLatch(1);

Future<?> task = executor.submit(() -> {
    started.countDown();
    try {
        Thread.sleep(60_000);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    } finally {
        finished.countDown();
    }
});

if (!started.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("task did not start");
}
task.cancel(true);
if (!finished.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("task did not finish");
}
```

Đây là **mảnh code** trong method có `executor` và imports tương ứng, khai báo/giải quyết `InterruptedException`. Không cần thực tế ngủ một phút: `cancel(true)` làm worker phản ứng với interrupt trong demo. Tuy nhiên, nếu một executor implementation/task khác không hợp tác, thời gian chờ sẽ hết và test báo lỗi.

**Thử nghiệm không nên dựa vào `Future.isDone()` duy nhất để khẳng định worker đã thoát:** sau cancellation, Future có thể báo done sớm hơn việc worker dừng. Dùng latch hoặc signal từ worker khi thật sự cần chứng minh cleanup đã chạy.

## 21. Ma trận kiểm thử thực hành

| Trường hợp | Điều cần xác minh |
| --- | --- |
| `execute` với Runnable ném unchecked exception | Uncaught handler/giám sát của executor nhận lỗi theo contract |
| `submit` với Callable ném exception | `get()` ném `ExecutionException`, cause là lỗi task |
| `submit` thành công | `get()` trả đúng giá trị |
| `submit(Runnable)` thành công | `get()` thường trả `null` |
| Task bị `cancel(true)` khi đang `sleep` | Task được yêu cầu interrupt; worker hợp tác và có cleanup |
| Worker nuốt `InterruptedException` | Test phát hiện worker vẫn chạy trái ý định |
| Caller `get()` bị interrupt | Caller xử lý interruption, Future nguồn không tự bị cancel |
| Future bị cancel | `get()` ném `CancellationException` |
| Caller `get(timeout)` hết hạn | Ném `TimeoutException`, task không tự bị hủy |
| Executor đã shutdown rồi `submit` | Caller nhận rejection theo policy |
| `shutdownNow()` với worker không hợp tác | Không giả định pool dừng ngay; kiểm tra termination timeout |
| `invokeAll` có một task lỗi | Duyệt các Future và xem cause, không chỉ xem list được trả |
| Task đã commit rồi bị lỗi sau đó | Không retry mù; trạng thái side effect đúng contract |
| Cleanup tự ném exception | Cause/suppressed và trạng thái được ghi nhận đúng |
| `afterExecute` khi submit thất bại | Không phụ thuộc `Throwable t` khác null |
| Shared executor bị shutdown nhầm | Test ownership/lifecycle, không đóng pool của thành phần khác |

Những test này phải có **giới hạn thời gian** và cleanup. Một worker bị lập trình sai có thể từ chối dừng; không được để toàn bộ bộ kiểm thử treo vô hạn. Với thread không hợp tác, cân nhắc cách ly test và cơ chế giới hạn ở cấp process.

## 22. Những lỗi phổ biến trong code thực tế

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `submit()` rồi bỏ Future | Task lỗi nhưng không ai quan sát | Giữ Future hoặc hệ thống báo kết quả |
| `catch (Exception ignored)` trong task | Che validation, bug và interrupt | Phân loại, chỉ xử lý lỗi có policy rõ |
| `catch (InterruptedException ex) {}` | Mất tín hiệu cancel | Truyền tiếp hoặc restore và thoát |
| Restore flag rồi quay lại `while(true)` | Loop nóng, task không dừng | `return`/`break` hoặc kiểm tra flag |
| `cancel(true)` rồi khẳng định “đã rollback” | Side effect có thể đã xảy ra | Transaction/idempotency/đối chiếu |
| Bị interrupt lúc `get()` rồi giả định task cũng bị hủy | Worker có thể vẫn chạy | Quyết định cancel nguồn theo ownership |
| Chỉ gọi `shutdown()` và in “all tasks done” | `shutdown()` không chờ termination | `awaitTermination` có timeout |
| `shutdownNow()` rồi kỳ vọng luôn chấm dứt | Best effort; task có thể không hợp tác | Kiểm tra termination và báo thất bại |
| Retry mọi `ExecutionException` | Bug và lỗi vĩnh viễn cũng bị retry | Phân loại `getCause()` |
| Dùng `get(timeout)` rồi không quản lý task | Timeout caller nhưng task tiếp tục | Cancel/deadline policy phù hợp |
| Chỉ dựa uncaught handler để giám sát `submit` | `FutureTask` giữ lỗi, handler không thấy | Quan sát Future |
| Mỗi tầng log Throwable đầy đủ | Trùng log, nguy cơ lộ secret | Một boundary quan sát và log an toàn |
| Tắt shared executor ở một request | Request khác bị rejection | Xác định owner lifecycle |

## 23. Checklist triển khai

1. Xác định executor thuộc thành phần nào và **ai có quyền shutdown**.
2. Chọn `execute` hay `submit` theo kênh giám sát lỗi/kết quả mong muốn.
3. Với `submit`, luôn có cơ chế **quan sát Future** nếu kết quả task quan trọng.
4. Phân biệt rejection ngay khi nộp với failure xảy ra trong worker.
5. Ở `Future.get()`, xử lý riêng `InterruptedException`, `ExecutionException`, `CancellationException` và timeout nếu có.
6. Task hỗ trợ cancellation phải có điểm check interrupt, hoặc sử dụng API interruptible.
7. Khi bắt `InterruptedException` trong `Runnable`, nếu dừng task, restore flag và **rời task**; không nuốt rồi chạy tiếp.
8. Không xem `cancel(true)`, `isDone()` hay `shutdownNow()` là bằng chứng cleanup/side effect hoàn tất.
9. Dùng `try-with-resources`/`finally` cho tài nguyên của từng task, transaction/idempotency cho trạng thái nghiệp vụ.
10. Shutdown có thời hạn và báo rõ khi pool không chấm dứt.
11. Trong test, dùng latch/signal xác định thay cho timing đoán mò.
12. Logging exception an toàn, tránh raw token, request body, PII và những bản ghi lặp.
13. Retry phải có điều kiện, giới hạn và policy không gây tác dụng phụ trùng.
14. Xác nhận cả đường success, failure, rejection, timeout, interrupt, cancel và cleanup.

**Kết luận:** khi thực hành với `ExecutorService`, đừng chỉ chứng minh “task được chạy”. Cần chứng minh **lỗi được quan sát đúng kênh**, **ngắt được xử lý đúng luồng**, **cancellation có tác dụng hợp tác**, và **executor kết thúc theo chính sách**. `execute()`, `submit()`, `Future.get()` và `cancel(true)` cung cấp những cơ chế khác nhau; hiểu rõ chúng là chìa khóa tránh nuốt lỗi, treo worker hoặc báo thành công giả.
