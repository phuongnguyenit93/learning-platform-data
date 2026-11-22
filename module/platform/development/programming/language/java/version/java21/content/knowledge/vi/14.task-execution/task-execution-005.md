# Phân biệt lỗi trong Future với lỗi chuyển tới uncaught exception handler

Khi một tác vụ chạy trong thread hoặc executor phát sinh exception, cách Java báo lỗi phụ thuộc vào cách tác vụ được khởi chạy. Nếu exception thoát trực tiếp khỏi `Thread.run()` hoặc khỏi task chạy bằng `ThreadPoolExecutor.execute()`, thread có thể kết thúc bất thường và `UncaughtExceptionHandler` được gọi. Nếu tác vụ được gửi bằng `ExecutorService.submit()`, exception thường được lưu trong `Future`; nó không thoát khỏi worker thread và vì vậy không kích hoạt uncaught handler của worker.

Đây là khác biệt quan trọng khi thiết kế logging và giám sát. Một default uncaught handler không phải bộ nghe toàn cục cho mọi lỗi của task. Với `Future`, ứng dụng phải đọc kết quả hoặc quan sát completion stage để phát hiện lỗi.

## 1. Hai nơi khác nhau để quan sát lỗi

Java có hai cơ chế thường gặp:

- **Uncaught exception của thread:** exception thoát khỏi phương thức `run()` mà không được bắt. JVM gọi `Thread.UncaughtExceptionHandler` của thread, hoặc cơ chế handler mặc định của thread group/JVM.
- **Exception được lưu trong Future:** executor hoặc completion framework giữ lại exception như kết quả thất bại của tác vụ. Lỗi được trả về cho mã gọi khi đọc `Future` hoặc khi xử lý completion stage.

Hai cơ chế phục vụ hai ranh giới khác nhau. Uncaught handler quan sát việc một thread kết thúc do lỗi không được xử lý. `Future` đại diện cho kết quả của một tác vụ, cho phép mã gọi lấy giá trị, exception hoặc trạng thái hủy.

| Cách chạy tác vụ | Nơi lưu/chuyển exception | Cách quan sát chính |
|---|---|---|
| `Thread.start()` với `Runnable` | Thoát khỏi `run()` | Uncaught exception handler |
| `ThreadPoolExecutor.execute()` | Exception thoát khỏi task chạy trên worker | Handler của worker; `afterExecute` cũng nhận throwable |
| `ExecutorService.submit()` | Được lưu trong `Future` | `Future.get()` hoặc `Future` completion |
| `CompletableFuture` async stage | Được lưu trong trạng thái exceptional completion | `get()`, `join()`, `whenComplete()`, `handle()` |
| `ScheduledExecutorService.schedule()` | Được lưu trong `ScheduledFuture` | `get()` trên future |

Lưu ý: `Executor.execute()` là một interface method và hợp đồng `Executor` không bắt buộc mọi implementation phải tạo thread. Mô tả worker kết thúc và uncaught handler ở phần tiếp theo áp dụng cụ thể cho `ThreadPoolExecutor` với task được thực thi trên worker thread.

## 2. Exception thoát trực tiếp khỏi Thread

Khi một thread chạy `Runnable` và exception thoát khỏi `run()`, JVM gọi uncaught handler của thread. Handler nhận thread bị lỗi và đối tượng `Throwable`:

```java
Thread.UncaughtExceptionHandler handler = (thread, error) -> {
    System.err.printf("Thread %s failed: %s%n", thread.getName(), error);
    error.printStackTrace(System.err);
};

Thread worker = Thread.ofPlatform()
        .name("direct-worker")
        .uncaughtExceptionHandler(handler)
        .start(() -> {
            throw new IllegalStateException("Task failed");
        });

worker.join();
```

`IllegalStateException` không được bắt nên thoát khỏi `run()`. Handler được gọi trong quá trình worker kết thúc. `join()` chỉ đợi worker kết thúc; nó không ném lại exception mà worker gặp.

`Runnable.run()` không khai báo `throws` cho checked exception. Nếu công việc có thể ném checked exception, mã chạy trong `Runnable` phải bắt và xử lý nó hoặc chuyển thành một unchecked exception. Với `Callable<V>`, checked exception có thể được ném ra từ `call()` và khi submit sẽ được lưu trong `Future`.

Uncaught handler chỉ được gọi khi exception thật sự thoát khỏi thread. Nếu `run()` bắt exception rồi ghi log, trả về hoặc ném một exception khác đã được xử lý ở trong thread, handler không được gọi cho exception đã bắt.

## 3. ThreadPoolExecutor.execute(): exception có thể làm worker kết thúc

Với `ThreadPoolExecutor`, `execute(Runnable)` đưa task vào hàng đợi hoặc giao cho worker chạy trực tiếp. Task không được bọc trong một `Future` chỉ để giữ kết quả. Nếu `Runnable.run()` ném unchecked exception và exception thoát khỏi task, worker thread đang chạy task có thể kết thúc bất thường.

Có thể gắn handler cho worker bằng `ThreadFactory`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

Thread.UncaughtExceptionHandler handler = (thread, error) -> {
    System.err.printf("Worker %s terminated: %s%n", thread.getName(), error);
};

var factory = Thread.ofPlatform()
        .name("pool-worker-", 0)
        .uncaughtExceptionHandler(handler)
        .factory();

try (ExecutorService executor = Executors.newFixedThreadPool(2, factory)) {
    executor.execute(() -> {
        throw new IllegalStateException("Failure from execute");
    });
}
```

`Executors.newFixedThreadPool` dùng `ThreadPoolExecutor`. Với task gửi bằng `execute`, exception thoát khỏi `Runnable.run()` có thể làm worker kết thúc; uncaught handler được gắn vào worker sẽ nhận lỗi. Khi pool chưa shutdown và cần duy trì số worker, `ThreadPoolExecutor` có thể tạo worker thay thế.

Không nên suy ra rằng executor sẽ luôn có hành vi này. Một `Executor` khác có thể chạy task trên thread gọi, bắt exception hoặc áp dụng chính sách riêng. Cần đọc hợp đồng của implementation đang dùng.

## 4. ExecutorService.submit(): exception được lưu trong Future

`submit()` trả về `Future` để theo dõi kết quả tác vụ. Trong `ThreadPoolExecutor`, task được bọc bởi `FutureTask`. `FutureTask.run()` bắt exception phát sinh trong `Callable.call()` hoặc `Runnable.run()` và lưu exception vào trạng thái hoàn tất bất thường của future.

Ví dụ:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
    Future<String> future = executor.submit(() -> {
        throw new IllegalStateException("Failure from submit");
    });

    try {
        String result = future.get();
        System.out.println(result);
    } catch (ExecutionException ex) {
        Throwable taskFailure = ex.getCause();
        System.err.println("Task failed: " + taskFailure);
    }
}
```

Trong ví dụ, `IllegalStateException` được giữ trong `Future`. Worker thread không nhìn thấy exception thoát khỏi `run()`, vì `FutureTask` đã bắt nó. Do đó, uncaught handler của worker không được gọi cho lỗi của task này. `future.get()` ném `ExecutionException`, và `getCause()` trả về exception gốc.

`Future` lưu cả unchecked exception và `Error` phát sinh trong lúc thực thi task. Điều này không có nghĩa các lỗi đó được khắc phục; chúng chỉ được giữ lại để mã gọi quan sát.

### Các trạng thái khi gọi Future.get()

| Kết quả | Ý nghĩa |
|---|---|
| Trả về giá trị | Task hoàn tất bình thường |
| `ExecutionException` | Task kết thúc bằng exception; xem `getCause()` |
| `CancellationException` | Task đã bị hủy |
| `InterruptedException` | Thread đang chờ `get()` bị interrupt |
| `TimeoutException` | Hết thời gian chờ nếu dùng `get(timeout, unit)` |

`InterruptedException` không có nghĩa task đã thất bại. Nó báo rằng thread gọi `get()` bị interrupt trong khi chờ. Nếu không thể truyền exception lên trên, thông thường nên khôi phục interrupt status bằng `Thread.currentThread().interrupt()` sau khi xử lý.

## 5. Future không tự ghi log lỗi

Exception được lưu trong `Future` sẽ không tự động được in ra bởi uncaught handler. Nếu ứng dụng bỏ qua future và không kiểm tra trạng thái hoặc kết quả, lỗi có thể không được quan sát.

Ví dụ sau submit task nhưng bỏ future:

```java
executor.submit(() -> {
    throw new IllegalArgumentException("This failure is stored in Future");
});
```

Với `ThreadPoolExecutor`, lỗi được lưu trong `FutureTask`; worker thường tiếp tục xử lý task khác. Nếu không giữ future hoặc không có cơ chế quan sát khác, ứng dụng có thể không biết task đã thất bại.

Nên giữ future và xử lý kết quả:

```java
Future<?> future = executor.submit(this::performWork);

try {
    future.get();
} catch (ExecutionException ex) {
    logger.error("Background task failed", ex.getCause());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
}
```

Nếu không muốn thread gọi chờ đồng bộ, có thể dùng `CompletableFuture` và gắn callback xử lý lỗi. Điểm cốt lõi vẫn là phải quan sát completion; tạo một future mà không theo dõi nó không đảm bảo lỗi được ghi nhận.

## 6. CompletableFuture cũng lưu exception trong completion stage

`CompletableFuture` lưu kết quả bình thường hoặc exceptional completion. Nếu supplier hoặc callback ném exception, stage tương ứng hoàn tất bất thường; exception không được chuyển thành uncaught exception của thread thực thi callback.

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> {
    throw new IllegalStateException("Remote operation failed");
});

future.whenComplete((value, error) -> {
    if (error != null) {
        Throwable cause = error instanceof CompletionException
                ? error.getCause()
                : error;
        System.err.println("Async operation failed: " + cause);
    }
});
```

`supplyAsync` mặc định thường dùng `ForkJoinPool.commonPool()` nếu không truyền executor. Dù supplier chạy trên thread nào, exception của supplier được ghi vào `CompletableFuture`; uncaught handler của thread đó không nhận exception như lỗi thoát khỏi `run()`.

Có thể quan sát exceptional completion theo nhiều cách:

- `whenComplete(...)`: thực hiện hành động khi stage hoàn tất, nhận cả kết quả và exception.
- `handle(...)`: chuyển kết quả hoặc lỗi thành một kết quả mới.
- `exceptionally(...)`: cung cấp giá trị thay thế khi stage thất bại.
- `get()`: chờ và ném `ExecutionException` nếu stage thất bại.
- `join()`: chờ và ném `CompletionException` nếu stage thất bại.

Ví dụ xử lý lỗi bằng `exceptionally`:

```java
CompletableFuture<String> safeResult = CompletableFuture
        .supplyAsync(() -> loadRemoteValue())
        .exceptionally(error -> {
            logger.warn("Using fallback after async failure", error);
            return "fallback";
        });
```

Sau `exceptionally`, stage mới có thể hoàn tất bình thường với giá trị dự phòng. Đây là xử lý lỗi ở tầng completion stage, không phải uncaught handler.

## 7. Phân biệt ExecutionException và CompletionException

Hai exception này đều có thể bọc nguyên nhân gây lỗi, nhưng xuất hiện ở API chờ khác nhau:

| API | Exception khi task/stage thất bại | Lấy lỗi gốc |
|---|---|---|
| `Future.get()` | `ExecutionException` | `getCause()` |
| `CompletableFuture.get()` | `ExecutionException` | `getCause()` |
| `CompletableFuture.join()` | `CompletionException` | `getCause()` |

Ví dụ:

```java
try {
    future.join();
} catch (CompletionException ex) {
    Throwable taskFailure = ex.getCause();
    logger.error("Async stage failed", taskFailure);
}
```

Nếu không bắt `ExecutionException` hoặc `CompletionException`, exception wrapper có thể thoát khỏi thread đang gọi `get()` hoặc `join()`. Khi đó uncaught handler của **thread gọi** có thể được gọi với wrapper exception. Đây không phải là worker thread gửi trực tiếp exception gốc đến handler.

Ví dụ, nếu main thread gọi `future.get()` và không bắt `ExecutionException`, uncaught handler của main thread (nếu có) sẽ quan sát `ExecutionException` thoát khỏi main thread. Task worker vẫn không phát sinh uncaught exception từ `FutureTask`.

## 8. ScheduledExecutorService cũng lưu lỗi trong ScheduledFuture

Các phương thức `schedule(...)` trả về `ScheduledFuture`. Nếu task một lần ném exception, future hoàn tất bất thường; gọi `get()` sẽ ném `ExecutionException`.

Với task định kỳ (`scheduleAtFixedRate` hoặc `scheduleWithFixedDelay`), nếu một lần thực thi ném exception, các lần chạy tiếp theo của task đó sẽ bị ngăn. Future định kỳ hoàn tất bất thường và có thể quan sát lỗi qua `get()`.

```java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ExecutionException;

try (ScheduledExecutorService scheduler =
             Executors.newSingleThreadScheduledExecutor()) {
    ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
            () -> {
                throw new IllegalStateException("Periodic task failed");
            },
            0, 1, TimeUnit.SECONDS);

    try {
        future.get();
    } catch (ExecutionException ex) {
        logger.error("Scheduled task failed", ex.getCause());
    }
}
```

Với `ScheduledThreadPoolExecutor`, task định kỳ được quản lý qua future; exception không được chuyển thành uncaught exception của worker theo cách task ném trực tiếp qua `execute()`.

## 9. ThreadPoolExecutor.afterExecute(): quan sát cả execute và submit

`ThreadPoolExecutor` có hook `afterExecute(Runnable r, Throwable t)`. Khi task chạy qua `execute()` và exception thoát khỏi `run()`, tham số `t` thường chứa exception đó. Nhưng với task được gửi bằng `submit()`, `Runnable` thường là `FutureTask`; nó đã bắt exception và lưu vào future, nên `t` thường là `null`.

Nếu muốn dùng hook này để ghi nhận lỗi từ cả hai kiểu gửi task, cần kiểm tra `Future` khi `t == null`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

class ObservingExecutor extends ThreadPoolExecutor {
    ObservingExecutor() {
        super(2, 2, 0L, TimeUnit.MILLISECONDS, new LinkedBlockingQueue<>());
    }

    @Override
    protected void afterExecute(Runnable task, Throwable failure) {
        super.afterExecute(task, failure);

        Throwable taskFailure = failure;

        if (taskFailure == null && task instanceof Future<?> future
                && future.isDone()) {
            try {
                future.get();
            } catch (CancellationException ex) {
                // Task bị hủy, không phải task exception.
            } catch (ExecutionException ex) {
                taskFailure = ex.getCause();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }

        if (taskFailure != null) {
            taskFailure.printStackTrace(System.err);
        }
    }
}
```

Ví dụ dùng một queue không giới hạn và hai worker để làm rõ hook; ứng dụng thực tế cần chọn queue, giới hạn pool và `ThreadFactory` theo tải công việc. `future.isDone()` được kiểm tra trước `get()` để hook không chờ task chưa hoàn tất. `get()` vẫn có thể ném `CancellationException` hoặc `InterruptedException`, nên cần phân biệt chúng với exception gốc của task.

Không phải executor nào cũng có `afterExecute`; đây là hook riêng của `ThreadPoolExecutor`. Với executor khác, hãy dùng API quan sát kết quả mà implementation cung cấp.

## 10. RejectedExecutionException khác với lỗi khi task đang chạy

Một lỗi có thể xảy ra ngay khi gửi task, trước khi task bắt đầu chạy. Ví dụ executor đã shutdown hoặc hàng đợi bị giới hạn và chính sách từ chối được kích hoạt. Khi đó `execute()` hoặc `submit()` có thể ném `RejectedExecutionException` ngay trên thread gọi.

```java
executor.shutdown();

try {
    executor.submit(this::performWork);
} catch (java.util.concurrent.RejectedExecutionException ex) {
    logger.warn("Executor rejected the task", ex);
}
```

Đây không phải exception được lưu trong `Future` vì task có thể chưa được nhận. Nếu không bắt, `RejectedExecutionException` sẽ thoát khỏi thread gọi và uncaught handler của thread gọi có thể được kích hoạt.

Vì vậy, khi chẩn đoán lỗi cần phân biệt:

1. Lỗi xảy ra trong task đã chạy.
2. Lỗi được lưu trong `Future` hoặc completion stage.
3. Lỗi từ chối task xảy ra ngay tại thời điểm submit.
4. Lỗi trong chính mã quản lý worker hoặc executor.

## 11. UncaughtExceptionHandler vẫn cần thiết ở đâu?

Uncaught handler vẫn hữu ích để ghi nhận lỗi thoát khỏi thread không có future quản lý, ví dụ:

- Thread được tạo trực tiếp bằng `Thread.start()`.
- Worker của `ThreadPoolExecutor` kết thúc bất thường do task chạy qua `execute()` ném exception.
- Lỗi thoát khỏi vòng lặp điều phối hoặc mã nền không được bọc trong future.
- Lỗi phát sinh ngoài phạm vi một task future, trong chính mã chạy của thread.

Có thể thiết lập handler cho thread factory của pool:

```java
Thread.UncaughtExceptionHandler handler = (thread, error) ->
        logger.error("Uncaught failure in {}", thread.getName(), error);

var factory = Thread.ofPlatform()
        .name("background-", 0)
        .uncaughtExceptionHandler(handler)
        .factory();
```

Handler nên ngắn gọn và an toàn khi nhiều thread gọi đồng thời. Nó là lớp giám sát cuối cùng, không thay thế việc quan sát `Future`, retry ở tầng nghiệp vụ hoặc quản lý kết quả của `CompletableFuture`.

## 12. Bảng chọn cách quan sát lỗi

| Nhu cầu | Cơ chế nên dùng |
|---|---|
| Theo dõi lỗi của thread tạo trực tiếp | `Thread.UncaughtExceptionHandler` |
| Gửi task không cần lấy kết quả, dùng `ThreadPoolExecutor.execute` | `afterExecute` và/hoặc handler của worker |
| Gửi task cần kết quả hoặc lỗi | Giữ `Future`, gọi `get()` |
| Xử lý pipeline bất đồng bộ | `whenComplete`, `handle`, `exceptionally` |
| Đợi kết quả `CompletableFuture` đồng bộ | `get()` hoặc `join()` và xử lý wrapper exception |
| Theo dõi task định kỳ | Giữ `ScheduledFuture`, kiểm tra `get()` và trạng thái |
| Phát hiện task bị từ chối | Bắt `RejectedExecutionException` tại nơi submit |

## 13. Nguyên tắc thiết kế

1. Dùng `submit()` khi cần theo dõi kết quả; luôn giữ và quan sát `Future`.
2. Dùng `execute()` khi không cần future, nhưng thiết kế logging cho task failure theo implementation executor.
3. Phân biệt `ExecutionException`, `CompletionException`, `CancellationException`, `InterruptedException` và `RejectedExecutionException`.
4. Không kỳ vọng default uncaught handler ghi nhận exception đã được `FutureTask` hoặc `CompletableFuture` bắt lại.
5. Nếu dùng `ThreadPoolExecutor.afterExecute`, kiểm tra `Future` đã hoàn tất để lấy exception bị lưu.
6. Dùng uncaught handler cho lỗi thực sự thoát khỏi thread, không dùng nó làm cơ chế retry.
7. Với task định kỳ, quan sát `ScheduledFuture`; một lần chạy thất bại có thể ngăn các lần chạy tiếp theo.
8. Khi thread chờ `Future.get()` bị interrupt, xử lý interrupt riêng, không ghi nhầm thành lỗi của task.

## 14. Tổng kết

Exception thoát khỏi `Thread.run()` hoặc khỏi task chạy trực tiếp qua worker của `ThreadPoolExecutor.execute()` có thể kích hoạt uncaught exception handler và làm worker kết thúc. Ngược lại, `ExecutorService.submit()` thường bọc task bằng `FutureTask`, bắt exception và lưu vào `Future`; lỗi chỉ được nhìn thấy khi mã gọi quan sát future. `CompletableFuture` và `ScheduledFuture` cũng lưu exceptional completion theo hợp đồng của chúng.

Do đó, `UncaughtExceptionHandler` không phải bộ thu thập mọi lỗi bất đồng bộ. Hãy chọn cơ chế quan sát đúng với cách task được gửi: handler cho lỗi thoát khỏi thread, `Future.get()` cho task submit, completion callbacks cho `CompletableFuture`, và kiểm tra `ScheduledFuture` cho task định kỳ. Đồng thời, bắt `RejectedExecutionException` ngay tại nơi gửi task và xử lý interrupt của thread chờ như một sự kiện riêng.

## Tài liệu tham khảo

- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html) — hợp đồng `execute`, `submit`, `invokeAll` và `invokeAny`.
- [Java SE 21 API — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html) — kết quả, exception và cancellation của tác vụ bất đồng bộ.
- [Java SE 21 API — FutureTask](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/FutureTask.html) — task implementation lưu kết quả và exception.
- [Java SE 21 API — Thread.UncaughtExceptionHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html) — callback khi exception thoát khỏi thread.
- [Java SE 21 API — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — `execute`, worker lifecycle và hook `afterExecute`.
- [Java SE 21 API — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — exceptional completion, `get`, `join`, `handle`, `whenComplete` và `exceptionally`.
- [Java SE 21 API — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html) — kết quả của scheduled tasks.
