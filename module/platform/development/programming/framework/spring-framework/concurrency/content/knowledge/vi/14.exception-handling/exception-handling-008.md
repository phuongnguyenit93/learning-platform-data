# Giới hạn bắt lỗi bằng TaskDecorator khi tác vụ được bọc trong Future

## 1. Vấn đề: vì sao try/catch ở TaskDecorator không bắt được lỗi?

Trong Spring Framework, `ThreadPoolTaskExecutor#setTaskDecorator(...)` cho phép bọc mã chạy một `Runnable` bằng logic bổ sung: thiết lập ngữ cảnh log, đo thời gian thực thi, ghi metric, làm sạch `ThreadLocal` hoặc quan sát lỗi **thoát ra từ lời gọi `run()`**.

Một mẫu thường gặp:

```java
executor.setTaskDecorator(task -> () -> {
    try {
        task.run();
    } catch (RuntimeException ex) {
        logger.error("Task failed", ex);
        throw ex;
    }
});
```

Đây chỉ là **snippet minh họa** với `executor` và `logger` đã tồn tại. Nhìn vào `catch`, ta dễ nghĩ “mọi task ném exception đều được log ở đây”. Thực tế **không đúng** khi tác vụ đã được bọc trong một `FutureTask` hoặc callback tương tự:

- Với một `Runnable` gốc được chạy trực tiếp qua đường `execute(Runnable)`, exception không bị một wrapper khác giữ lại có thể **thoát ra từ `task.run()`**, nên decorator bắt được.
- Với `submit(Runnable)` hoặc `submit(Callable)`, framework/executor thường tạo **`FutureTask`**: `FutureTask.run()` bắt lỗi nghiệp vụ và **lưu lỗi vào trạng thái của Future**. Nó trả về bình thường ở bề mặt `Runnable.run()`, vì vậy `catch` bên ngoài **không được gọi**.
- Với `@Async` trả `Future`/`CompletableFuture` hoặc các task đã được bọc nhiều tầng, callback thực sự được decorate **có thể không còn là Runnable/Callable người dùng truyền vào**. Không được suy luận kiểu hoặc quy tắc bắt lỗi chỉ từ chữ ký `TaskDecorator.decorate(Runnable)`.

Đây chính là giới hạn được nêu trong **Javadoc của Spring `ThreadPoolTaskExecutor.setTaskDecorator`**: decorator phù hợp để bổ sung context/monitoring cho callback thực thi, nhưng việc bắt lỗi có thể chỉ thấy exception của `Runnable` trực tiếp. Với đường `submit`, `FutureTask` không truyền exception ra khỏi `run()`; nếu cần quan sát lỗi, có thể phải truy cập `Future.get()`.

**Mục tiêu của bài:** hiểu ranh giới xảy ra lỗi, tái hiện bằng Java 17, nhận diện hành vi Spring và chọn vị trí xử lý exception đáng tin cậy thay vì kỳ vọng mọi lỗi đều tới `TaskDecorator.catch`.

## 2. TaskDecorator có tác dụng gì, và không có quyền gì?

Interface trong Spring:

```java
@FunctionalInterface
public interface TaskDecorator {
    Runnable decorate(Runnable runnable);
}
```

Đây là chữ ký rút gọn để học khái niệm, không phải mã source đầy đủ của Spring. Nó nhận một `Runnable` mà executor sẽ chạy và trả về một `Runnable` khác, thường cũng gọi lại `runnable.run()`.

```text
Caller / @Async proxy / ExecutorService
       |
       v
  Task submitted
       |
       v
  (có thể được bọc trong FutureTask / callback nội bộ)
       |
       v
  TaskDecorator.decorate(actualRunnable)
       |
       v
  decoratedRunnable chạy trên worker
       |
       +--> setup context / start timer
       |
       +--> actualRunnable.run()
       |       |
       |       +--> lỗi có thể THOÁT RA
       |       +--> hoặc bị FutureTask giữ lại
       |
       +--> finally: cleanup context / record duration
```

TaskDecorator rất hữu ích khi cần:

1. Chép/khôi phục ngữ cảnh log từ thread submit sang worker (ví dụ correlation ID/MDC).
2. Đặt `ThreadLocal` theo một scope rõ ràng, rồi khôi phục hoặc xóa ở `finally` để tránh dữ liệu của request trước rò sang task sau.
3. Đo thời gian callback thực thi và ghi metric với tag giới hạn cardinality.
4. Bổ sung context tracing/observation, nếu ứng dụng có đúng thư viện và cơ chế context propagation.
5. Đánh dấu vòng đời task ở cấp executor, không gắn logic đo đạc vào mọi method nghiệp vụ.

**TaskDecorator không phải:**

- Một error handler toàn cục hiểu mọi `Future`, `CompletableFuture` hoặc exception của `@Async`.
- Một `try/catch` có thể nhìn xuyên qua exception đã bị `FutureTask` ghi lại trong state.
- Một cơ chế tự hủy task, retry, rollback transaction hoặc cam kết lỗi sẽ được log đúng một lần.
- Một cơ chế tự động bao phủ công việc không được nộp qua executor bean có decorator đó.
- Một cơ chế bắt mọi lỗi từ các việc bất đồng bộ *được khởi tạo bởi* task gốc nhưng tiếp tục chạy sau khi `Runnable.run()` đã trả về.

Điều Spring decorate là **callback thực tế**, không nhất thiết là chính đối tượng `Runnable` hay `Callable` mà caller ban đầu cung cấp. Vì thế việc ép mọi callback thành kiểu ứng dụng tự định nghĩa thường không an toàn.

## 3. Phân biệt execute, submit và FutureTask

### 3.1. execute(Runnable): lỗi có thể thoát khỏi run()

Với JDK `Executor.execute(Runnable)` hoặc Spring `TaskExecutor.execute(Runnable)`, khi underlying executor thực sự chạy một `Runnable` trực tiếp và không có lớp bọc giữ lỗi:

```java
executor.execute(() -> {
    throw new IllegalStateException("direct failure");
});
```

Exception có thể thoát khỏi `Runnable.run()`, đi qua wrapper của decorator, rồi được xử lý bởi cơ chế exception/uncaught exception của thread hoặc executor. Nếu decorator bắt rồi ném lại, worker có thể chết và pool thay thread theo chính sách triển khai.

**Giới hạn của câu này:** “gọi `execute`” **không đủ** để bảo đảm callback decorate chính là lambda gốc. Spring `@Async`, `CompletableFuture`, các adapter khác hoặc middleware có thể đã bọc tác vụ trước đó. Hãy kiểm tra đường thực thi thật trước khi tin rằng decorator sẽ thấy mọi exception.

### 3.2. submit(...): lỗi được lưu trong FutureTask

JDK `ExecutorService.submit(Callable)` trả về `Future<T>`:

```java
Future<String> future = executor.submit(() -> {
    throw new IllegalArgumentException("task failed");
});

// Ở code sở hữu kết quả (không phải mặc định trong TaskDecorator):
try {
    String value = future.get();
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause(); // IllegalArgumentException
    // Ghi nhận và quyết định xử lý theo nghiệp vụ.
}
```

Đây là snippet cần biến `executor` và các import JDK. Khi dùng `FutureTask`, lời gọi `run()` bên ngoài không cần ném `IllegalArgumentException` lên decorator; nó lưu lỗi để `Future.get()` báo `ExecutionException` với `cause` là lỗi gốc.

`FutureTask` triển khai **cả `Runnable` và `Future`** (qua `RunnableFuture`). Điều này giải thích vì sao nó có thể được worker chạy như `Runnable`, nhưng vẫn giữ trạng thái kết quả/ngoại lệ cho phía gọi.

### 3.3. Bảng đối chiếu

| Tình huống | Callback `run()` có thể ném ra lỗi nghiệp vụ? | Vị trí quan sát lỗi đáng tin cậy |
| --- | --- | --- |
| `execute(plainRunnable)`, không wrapper giữ lỗi | Có | `catch` quanh `run()`; uncaught handler/logger của executor |
| `submit(Runnable)` qua `FutureTask` | Thường không: lỗi nằm trong Future | `Future.get()` → `ExecutionException.getCause()` |
| `submit(Callable)` qua `FutureTask` | Thường không | `Future.get()` → `ExecutionException.getCause()` |
| `CompletableFuture.supplyAsync(...)` | Không nên giả định | `whenComplete`, `handle`, `exceptionally` hoặc `join/get` |
| Spring `@Async` trả `Future/CompletableFuture` | Không nên giả định TaskDecorator nhìn thấy | Future trả về caller; kiểm tra hoàn tất/lỗi |
| Spring `@Async void` | Không trả Future cho caller | `AsyncUncaughtExceptionHandler` |
| Submission bị pool/queue từ chối | Tác vụ chưa chạy | `TaskRejectedException` hoặc `RejectedExecutionException` **tại submitter** |

**Lưu ý:** `CompletableFuture.join()` ném `CompletionException` đối với thất bại thông thường; `Future.get()` ném `ExecutionException`. Với trường hợp cancellation, cần xử lý `CancellationException` riêng.

## 4. Cơ chế FutureTask.run(): vì sao catch không được kích hoạt?

Trình tự khi một `Callable` bị bọc bởi `FutureTask`:

```text
Caller: submit(callable)
            |
            v
        FutureTask(callable)   <-- implements RunnableFuture
            |
            v
TaskDecorator sees a Runnable that may be this FutureTask
            |
            v
decoratedRunnable.run()
            |
            +--> try {
            |        futureTask.run()
            |            |
            |            +--> callable.call() throws IllegalArgumentException
            |            |
            |            +--> FutureTask records exceptional state
            |            +--> returns normally from run()
            |    } catch (RuntimeException ex) {
            |        // KHÔNG chạy cho lỗi đã bị FutureTask giữ
            |    }
            |
            v
Caller calls Future.get()
            |
            +--> ExecutionException(cause=IllegalArgumentException)
```

**Cơ chế quan trọng nhất:** một `FutureTask` có thể hoàn thành ở trạng thái **exceptional** mà phương thức `run()` của nó vẫn **trả về bình thường**. Không có mâu thuẫn: Future là nơi lưu lỗi, còn `Runnable.run()` là giao diện thực thi callback.

Điều đó không có nghĩa “lỗi đã được xử lý xong về nghiệp vụ”. Một caller không bao giờ gọi `get()` và không có cơ chế quan sát trạng thái exceptional có thể **bỏ lỡ lỗi** dù pool vẫn tiếp tục phục vụ task khác.

Nó cũng không có nghĩa tất cả exception đều bị FutureTask nuốt: exception từ **decorator itself**, quá trình tạo context, cleanup, hoặc những lớp bọc khác có thể vẫn thoát ra. Ranh giới nào bắt lỗi phải được xác định từ chính đối tượng/callback đang chạy.

## 5. Ví dụ Java 17 độc lập: cùng một decorator, hai kết quả khác nhau

Ví dụ dưới mô phỏng logic wrapper mà một `TaskDecorator` tạo ra, nhưng dùng **100% JDK 17**, không cần Spring. Chạy đồng bộ trên thread chính để kết quả xác định và dễ thấy cách `Runnable.run()` khác với `FutureTask.run()`. **Đây là minh họa semantics**, không phải mô phỏng đầy đủ vòng đời bean/executor của Spring.

Tạo tệp **`FutureTaskDecoratorDemo.java`**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;

public final class FutureTaskDecoratorDemo {
    static Runnable decorate(Runnable task) {
        return () -> {
            try {
                task.run();
            } catch (RuntimeException ex) {
                System.out.println(
                        "caughtAtRun=" + ex.getClass().getSimpleName());
                throw ex; // Giữ nguyên semantics báo lỗi của Runnable.
            } finally {
                // Chỉ xem Future sau run(), chỉ khi Future báo đã hoàn tất.
                if (task instanceof Future<?> future && future.isDone()) {
                    try {
                        future.get();
                    } catch (ExecutionException ex) {
                        System.out.println(
                                "causeFromGet="
                                        + ex.getCause().getClass().getSimpleName());
                    } catch (CancellationException ex) {
                        System.out.println("cancelled=true");
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                }
            }
        };
    }

    public static void main(String[] args) {
        Runnable direct = () -> {
            throw new IllegalStateException("direct");
        };
        try {
            decorate(direct).run();
        } catch (IllegalStateException ex) {
            System.out.println("directPropagated=true");
        }

        FutureTask<String> future = new FutureTask<>(
                () -> {
                    throw new IllegalArgumentException("stored");
                });

        decorate(future).run();

        System.out.println("futureDone=" + future.isDone());
        System.out.println("futureCancelled=" + future.isCancelled());
    }
}
```

Biên dịch/chạy với JDK 17 hoặc mới hơn:

```bash
javac --release 17 FutureTaskDecoratorDemo.java
java FutureTaskDecoratorDemo
```

**Standard output đã được kiểm chứng khi chạy chương trình:**

```text
caughtAtRun=IllegalStateException
directPropagated=true
causeFromGet=IllegalArgumentException
futureDone=true
futureCancelled=false
```

### Giải thích đầu ra

1. Với `direct`, `run()` ném `IllegalStateException`. Wrapper bắt được nên in `caughtAtRun=IllegalStateException`, rồi ném lại. Main bắt tiếp và in `directPropagated=true`.
2. Với `future`, `FutureTask.run()` gọi `Callable.call()`, nhận `IllegalArgumentException`, **ghi exception vào trạng thái Future** và hoàn tất. Nó **không ném** ngoại lệ đó ra wrapper, nên không có dòng `caughtAtRun=IllegalArgumentException`.
3. Trong `finally`, wrapper nhận ra `task instanceof Future<?>` và `future.isDone()`. Gọi `get()` báo `ExecutionException`; `getCause()` là `IllegalArgumentException` nên in `causeFromGet=IllegalArgumentException`.
4. Future đã hoàn tất nhưng **không bị hủy**: `futureDone=true`, `futureCancelled=false`. Lỗi nghiệp vụ và cancellation là hai trạng thái khác nhau.

Ví dụ sử dụng `get()` **sau** khi `FutureTask.run()` đã hoàn tất; không có chờ vô hạn. Trong executor thật, tuyệt đối không gọi `Future.get()` bừa bãi từ một wrapper khi future còn chạy hoặc phụ thuộc chính worker đang bị chặn: có thể làm cạn pool và deadlock.

**Tính đúng đắn đã xác minh:** chương trình ở trên được biên dịch với `javac --release 17` và thực thi trên JDK hỗ trợ Java 17; stdout khớp đúng năm dòng đã ghi. Điều này xác nhận semantics của mẫu JDK, **không thay thế integration test với phiên bản Spring ứng dụng đang dùng**.

## 6. Cấu hình Spring TaskDecorator: mục đích phù hợp là context và metric

Trong Spring Framework 6.2, một bean `ThreadPoolTaskExecutor` có thể được cấu hình:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class ObservedExecutorConfig {
    private static final Logger LOG =
            Logger.getLogger(ObservedExecutorConfig.class.getName());

    @Bean("observedExecutor")
    public ThreadPoolTaskExecutor observedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("observed-");

        executor.setTaskDecorator(task -> () -> {
            long start = System.nanoTime();
            try {
                task.run();
            } catch (RuntimeException | Error ex) {
                // Chỉ các lỗi THOÁT RA khỏi callback.run() mới đến đây.
                LOG.log(Level.SEVERE, "Runnable callback failed", ex);
                throw ex;
            } finally {
                long elapsedNanos = System.nanoTime() - start;
                LOG.fine("Callback duration (ns): " + elapsedNanos);
            }
        });
        return executor;
    }
}
```

Đây là **class cấu hình tích hợp Spring**, cần dependency `spring-context`/`spring-aop` liên quan và application context phù hợp; không biên dịch trực tiếp bằng JDK thuần. Không có output cố định vì nó cấu hình worker và thời gian chạy. Spring quản lý việc khởi tạo/shutdown executor bean theo lifecycle.

**Phân tích đúng:**

- `setTaskDecorator` bọc callback thực tế mà Spring giao cho pool. Nó hữu ích cho scope thời gian chạy callback, context logging và cleanup.
- `catch` chỉ nhận exception thực sự thoát khỏi `task.run()`. Nó **có thể không nhận** lỗi đã được một `FutureTask`/callback giữ ở trạng thái kết quả.
- Giữ `throw ex` để không âm thầm thay đổi semantics của exception đối với `execute(Runnable)` trực tiếp.
- `finally` vẫn chạy khi callback hoàn thành bình thường hoặc ném lỗi. Đây là nơi hợp lý để hoàn trả context/metric.
- `System.nanoTime()` thích hợp đo thời gian tương đối, không dùng như timestamp UTC. Nếu callback chỉ **lên lịch thêm việc khác rồi trả về**, khoảng thời gian đo ở đây chỉ là **thời gian chạy callback**, không tự bao trùm toàn bộ các future con.
- `LOG.fine` có thể không xuất hiện nếu logger không bật mức FINE; đó không phải dấu hiệu decorator không chạy.

**Đừng dùng `TaskDecorator` làm nơi nuốt mọi exception** bằng một `catch (Exception ex) { log; }` không ném lại. Với `execute(Runnable)`, cách đó có thể làm tác vụ lỗi trông như hoàn thành bình thường; với `FutureTask`, ngay cả cách đó vẫn bỏ sót lỗi đã được lưu trong Future.

## 7. Có thể nhìn Future.get() trong TaskDecorator, nhưng có giới hạn

Javadoc Spring gợi ý: khi callback được expose dưới dạng `FutureTask`, có thể cast sang `Future` và dùng `get()` để đánh giá lỗi. Cách này **không phải một lời hứa** rằng mọi callback đều triển khai `Future`.

Một biến thể chẩn đoán:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import org.springframework.core.task.TaskDecorator;

// Dùng trong cấu hình executor hoặc nơi tạo decorator.
TaskDecorator diagnosticDecorator = runnable -> () -> {
    try {
        runnable.run();
    } finally {
        if (runnable instanceof Future<?> future && future.isDone()) {
            try {
                future.get();
            } catch (ExecutionException ex) {
                // Ghi nhận lỗi được FutureTask lưu (ex.getCause()).
                recordFailure(ex.getCause());
            } catch (CancellationException ex) {
                // Cancellation khác với lỗi tính toán.
                recordCancellation();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }
};
```

Đây là **snippet minh họa** với `recordFailure(...)` và `recordCancellation()` do ứng dụng cung cấp; cần import/config phù hợp và **không phải chương trình độc lập**.

### Những điều kiện quan trọng

- **Phải kiểm tra `instanceof Future<?>`.** Decorator có thể thấy một `Runnable` là wrapper nội bộ **không** triển khai `Future`, dù logic cao hơn đang tạo ra kết quả kiểu `CompletableFuture`.
- **Chỉ cân nhắc `get()` sau `run()` và khi `isDone()`**. Cố gọi `get()` trước `run()` hoặc trên một Future chưa xong ngay trong worker có thể chặn vô hạn hoặc tạo deadlock.
- **`get()` có thể ném ba nhóm lỗi khác nhau**: `ExecutionException` (lỗi computation), `CancellationException` (task bị hủy) và `InterruptedException` (worker đang đợi bị interrupt). Cần phân loại riêng; khi bắt `InterruptedException` thường phải khôi phục cờ interrupt.
- Nếu Future là một implementation khác, `get()` không nhất thiết phản ánh toàn bộ công việc phụ thuộc hoặc callback phía sau. Không biến decorator thành một generic future orchestrator.
- Với `@Async` trả `CompletableFuture`, wrapper mà executor thực sự chạy có thể là **callback nội bộ**, không phải `FutureTask` trực tiếp; phép thử `instanceof Future` có thể luôn `false`. Phải kiểm chứng trên Spring version/executor implementation thực tế.
- `recordFailure` trong decorator có thể trùng với handler ở caller. Chọn một nơi sở hữu log/metric và định danh task để tránh đếm hai lần.
- Các hook như `ThreadPoolExecutor.afterExecute(Runnable, Throwable)` có cùng vấn đề: `Throwable` có thể là `null` khi `FutureTask` đã lưu exception. JDK đưa ví dụ kiểm tra `r instanceof Future<?>` rồi `get()`, nhưng nếu decorator bọc FutureTask trong một Runnable khác, `afterExecute` có thể chỉ thấy wrapper đó. Cần test cấu trúc callback thực tế.

**Khuyến nghị:** dùng kiểm tra Future trong decorator cho nhu cầu diagnostic được kiểm chứng, không dùng làm **nền tảng duy nhất** của xử lý lỗi nghiệp vụ. Phần sau trình bày các điểm bắt lỗi vững hơn.

## 8. Xử lý lỗi ở Future: vị trí sở hữu kết quả đáng tin cậy hơn

### 8.1. Future.get(): rõ nguyên nhân nhưng có thể chặn caller

Khi chủ động gọi `submit` và giữ kết quả:

```java
Future<String> result = executor.submit(() -> {
    throw new IllegalArgumentException("bad input");
});

try {
    String value = result.get();
    useValue(value);
} catch (ExecutionException ex) {
    Throwable original = ex.getCause();
    handleFailure(original);
} catch (CancellationException ex) {
    handleCancellation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    handleInterruptedWait(ex);
}
```

Đây là snippet có `executor` và các hàm nghiệp vụ được cung cấp bởi chương trình tích hợp. `Future.get()` có thể **chặn caller**; nếu caller là HTTP event-loop hoặc đang giữ lock/connection quý hiếm, cân nhắc API bất đồng bộ hoặc timeout.

Với deadline, dùng `get(timeout, unit)` và xử lý thêm `TimeoutException`. Timeout khi đợi **không tự xác nhận** task đã dừng; cần quyết định cancel/cleanup phù hợp với executor và dependency.

### 8.2. CompletableFuture.whenComplete(): quan sát mà không gọi blocking get

Với `CompletableFuture`, callback là lựa chọn phù hợp để xử lý kết quả hoàn thành bất đồng bộ:

```java
CompletableFuture<String> job =
        CompletableFuture.supplyAsync(() -> calculateReport(), executor);

job.whenComplete((value, error) -> {
    if (error != null) {
        // error có thể là CompletionException bọc nguyên nhân.
        logFailure(error);
    } else {
        logSuccess(value);
    }
});
```

Đây là **snippet tích hợp**. `whenComplete` nhận được exceptional completion của future, kể cả khi `Runnable.run()` phía executor trả về bình thường. Cần lưu ý callback không nhất thiết chạy trên một worker mới: tùy trạng thái completion và loại overload, hàm `whenComplete` có thể chạy trên thread hoàn tất stage hoặc thread đăng ký callback; không đặt trong đó một xử lý blocking dài.

Nếu muốn luôn dispatch callback sang một executor kiểm soát được, xem `whenCompleteAsync(action, executor)` nhưng phải tính tới saturation/rejection của executor đó.

### 8.3. exceptionally(), handle(), whenComplete(): không giống nhau

| API | Chức năng | Cẩn thận |
| --- | --- | --- |
| `whenComplete((v,e) -> ...)` | Quan sát cả thành công và lỗi | Thường giữ trạng thái kết quả/lỗi của stage nguồn; callback cũng có thể ném lỗi |
| `exceptionally(e -> fallback)` | Phục hồi bằng giá trị khác sau lỗi | Có thể biến lỗi thành thành công; đừng dùng chỉ để log rồi vô tình nuốt lỗi |
| `handle((v,e) -> newValue)` | Biến đổi kết quả của cả hai nhánh | Trạng thái mới do hàm handler quyết định |
| `join()` | Lấy kết quả, ném `CompletionException` khi lỗi | Có thể chặn; dùng khi phù hợp |
| `get()` | Lấy kết quả, ném `ExecutionException` khi lỗi | Checked exceptions, có thể chặn |

Nếu hệ thống phải báo lỗi cho caller, không dùng `exceptionally(ex -> null)` chỉ để “ghi log rồi xong” khi `null` bị hiểu là kết quả hợp lệ. Hãy định nghĩa contract phục hồi/fail-fast rõ ràng.

### 8.4. Đặt catch ngay trong task nghiệp vụ khi cần context

Một task biết `orderId`, transaction boundary và remote endpoint thường có đủ thông tin để phân loại lỗi:

```java
public Invoice calculateInvoice(String orderId) {
    try {
        return invoiceClient.calculate(orderId);
    } catch (RemoteTimeoutException ex) {
        failureMetric.increment();
        throw ex;
    }
}
```

Đây là **snippet minh họa**, phụ thuộc các kiểu nghiệp vụ và client của ứng dụng. Ưu điểm: log/counter có ngữ cảnh chính xác. Nhược điểm: lặp code nếu mọi task đều thêm đoạn giống nhau; khi đó tạo component wrapper nghiệp vụ hay aspect có contract rõ thay vì ép generic TaskDecorator biết toàn bộ lỗi.

## 9. Spring @Async: Future, CompletableFuture và void không cùng đường lỗi

Đối với Spring `@Async`, return type ảnh hưởng cách exception tới người gọi:

| Dạng phương thức | Khi thân phương thức ném lỗi | Điểm xử lý nên dùng |
| --- | --- | --- |
| `@Async CompletableFuture<T>` | Lỗi có thể được biểu diễn thành exceptional completion của future trả cho caller | `whenComplete`/`handle` hoặc `join/get` |
| `@Async Future<T>` | Caller có thể nhận exception qua `Future.get()` | `get()` và `ExecutionException.getCause()` |
| `@Async void` | Caller không nhận Future để lấy exception | `AsyncUncaughtExceptionHandler`, logging/metrics tại boundary |
| Tác vụ bị reject khi submit | Execution chưa được chấp nhận | Xử lý `TaskRejectedException` ở nơi nộp |

**Ví dụ Spring service:**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("observedExecutor")
    public CompletableFuture<String> build(String id) {
        if (id.isBlank()) {
            throw new IllegalArgumentException("id is blank");
        }
        return CompletableFuture.completedFuture("report:" + id);
    }

    @Async("observedExecutor")
    public void publish(String id) {
        if (id.isBlank()) {
            throw new IllegalArgumentException("id is blank");
        }
    }
}
```

Đây là **class tích hợp Spring**, dùng bean executor ở mục 6 và cơ chế `@EnableAsync`; không phải chương trình JDK standalone. Spring quản lý dispatch qua proxy nếu method được gọi từ một Spring bean khác; tự gọi `this.build(...)` trong cùng target thường bypass `@Async` ở chế độ proxy.

**Caller xử lý future:**

```java
CompletableFuture<String> result = reportService.build("");
result.whenComplete((value, error) -> {
    if (error != null) {
        // Đây là lỗi của async computation, không nhất thiết
        // là RuntimeException thoát ra TaskDecorator.run().
        recordBuildError(error);
    }
});
```

Snippet cần `reportService` và `recordBuildError` được định nghĩa. Khi dùng `@Async void`, Spring cung cấp `AsyncUncaughtExceptionHandler` để xử lý exception không có Future trả về.

### Cấu hình AsyncUncaughtExceptionHandler cho void

```java
import java.util.concurrent.Executor;
import java.util.logging.Level;
import java.util.logging.Logger;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;

@Configuration
public class AsyncErrorsConfig implements AsyncConfigurer {
    private static final Logger LOG =
            Logger.getLogger(AsyncErrorsConfig.class.getName());

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, args) ->
                LOG.log(Level.SEVERE,
                        "Async void failed: " + method.getName(), error);
    }
}
```

Đây là class cấu hình Spring, có thể dùng trong ứng dụng đã bật `@EnableAsync` và có đúng bean executor; ***không*** phải một phương tiện nhận lỗi từ `Future<T>`. Nếu nhiều `AsyncConfigurer` hoặc cấu hình async cùng tồn tại, phải kiểm chứng executor/error handler thực sự được chọn.

**Không kỳ vọng `TaskDecorator` thay thế `AsyncUncaughtExceptionHandler`.** Với `@Async void`, exception có thể bị async interceptor bắt và chuyển tới handler trước khi callback chạy về đến decorator. Cơ chế nào được gọi phải được integration-test trên bản Spring thực tế.

## 10. Phân biệt bốn trạng thái: lỗi thực thi, hủy, timeout, từ chối

### Lỗi thực thi

Task được nhận vào executor, bắt đầu chạy và ném lỗi. Lỗi có thể được đưa vào `Future`/`CompletableFuture` hoặc thoát ra worker. Xử lý tại kết quả hoặc boundary thực thi có đủ context.

### Cancellation

Một `Future` bị hủy: `isCancelled()` có thể đúng; `get()` ném `CancellationException`. Đây **không phải** `ExecutionException` của lỗi nghiệp vụ. Hủy `CompletableFuture` có thể đổi trạng thái future mà không dừng supplier phía sau, tùy implementation.

### Timeout

`Future.get(timeout, unit)` có thể ném `TimeoutException` do caller chờ quá lâu, trong khi task vẫn tiếp tục chạy. Timeout của JDBC/HTTP client là cơ chế khác; đo riêng waiting duration, execution duration và resource release.

### Rejection

Khi executor đã shutdown hoặc hết khả năng nhận task (ví dụ full pool + full queue theo policy), lời gọi submit/execute có thể bị từ chối **trước khi task được chạy**. Trong Spring, lỗi này thường là `org.springframework.core.task.TaskRejectedException`. Decorator của tác vụ chưa chạy **không có cơ hội** bắt exception này. Hãy xử lý tại caller/admission layer, không lẫn với lỗi completion.

```text
                  submission
                      |
              +-------+-------+
              |               |
           rejected         accepted
              |               |
    TaskRejectedException    v
       (caller thread)     execution
                              |
                      +-------+-------+
                      |               |
                    plain          FutureTask/
                  Runnable         async wrapper
                      |               |
                may throw out     stores task error
                  of run()         in Future state
                      |               |
              decorator catch      Future.get() /
               may see error      whenComplete()
```

## 11. Vì sao không nên cố chữa bằng afterExecute hoặc Thread.UncaughtExceptionHandler?

JDK `ThreadPoolExecutor.afterExecute(Runnable r, Throwable t)` chạy sau khi worker thực thi task. `t` có thể là `null` ngay cả khi một `FutureTask` đã thất bại, vì `run()` của FutureTask không ném exception ra worker.

JDK Javadoc có ví dụ: nếu `t == null` và `r instanceof Future<?>`, hãy gọi `get()` để lấy `ExecutionException`/`CancellationException`; cần lưu ý cả `InterruptedException`.

**Nhưng trong Spring có TaskDecorator:**

1. `FutureTask` được wrap bởi decorator thành một `Runnable` mới.
2. `afterExecute` của underlying pool có thể nhận **wrapper** đó chứ không phải FutureTask gốc.
3. Nếu wrapper không triển khai Future, `r instanceof Future<?>` là `false` dù lỗi nằm ở FutureTask bên trong.
4. Vì vậy sao chép logic JDK `afterExecute` không tự bảo đảm quan sát được tất cả lỗi khi có thêm decorator, async interceptor, adapter hoặc callback nội bộ.

Tương tự, `Thread.UncaughtExceptionHandler` chỉ xử lý exception thật sự không được bắt trên thread. Một lỗi đã được `FutureTask` ghi vào state không trở thành uncaught exception.

**Chọn vị trí xử lý theo quyền sở hữu kết quả:** subscriber của `CompletableFuture`, caller có `Future`, handler của `@Async void`, hoặc boundary nghiệp vụ. Dùng TaskDecorator/afterExecute bổ sung metric/context thay vì kỳ vọng chúng nhìn xuyên mọi wrapper.

## 12. Context propagation và cleanup vẫn là use case mạnh của TaskDecorator

Với ứng dụng Spring có log correlation ID, MDC hoặc observation context, decorator thích hợp vì **nó chạy ở biên thực thi callback**, độc lập với thành công hay lỗi nghiệp vụ.

Cách làm đúng với `ThreadLocal`/MDC:

1. **Chụp context khi submit** ở thread nguồn, nếu implementation thực sự gọi decorate lúc submit. Đừng chỉ đọc `ThreadLocal` của worker rồi tưởng đó là context của request.
2. **Thiết lập context ở worker** trước `task.run()`.
3. **Trong `finally`, khôi phục context cũ hoặc xóa** để worker được tái sử dụng không làm rò trace/request ID từ task này sang task tiếp theo.
4. **Không quên cancellation và exception path**; cleanup vẫn phải chạy.
5. Tránh đính kèm cả security principal hay dữ liệu nhạy cảm vào log/metric tag không kiểm soát.
6. Đo overhead khi mỗi task rất ngắn: snapshot/restore context cũng có chi phí.

Spring Framework 6.1+ có `ContextPropagatingTaskDecorator` hỗ trợ truyền một số context như logging/observation khi có tích hợp Micrometer Context Propagation thích hợp. Tính năng này **không biến TaskDecorator thành exception handler toàn năng**. Nếu dùng `CompositeTaskDecorator` để phối hợp nhiều decorator, cần kiểm tra thứ tự wrap/cleanup và tác động đến đối tượng `Runnable` mà mỗi tầng nhìn thấy.

Đừng giả định worker-thread-local là nơi an toàn để lưu exception “cho ai đó lấy sau”: thread có thể được pool tái sử dụng; lỗi nên được liên kết với **task ID/future/trace context** thích hợp và được dọn đúng vòng đời.

## 13. Kiểm thử thực tế cho ThreadPoolTaskExecutor

Một integration test tốt nên tạo các trường hợp khác nhau, thay vì chỉ một lời gọi ném lỗi:

| Ca kiểm thử | Thiết lập | Kỳ vọng cần kiểm chứng |
| --- | --- | --- |
| A: `execute(Runnable)` trực tiếp | Runnable ném `IllegalStateException`, không wrapper giữ lỗi | Decorator catch có thể thấy exception thoát khỏi `run()` |
| B: `submit(Callable)` | Callable ném `IllegalArgumentException` | `Future.get()` ném `ExecutionException`; decorator catch không nên được coi là đủ |
| C: `submit(Runnable)` | Runnable ném lỗi | Future giữ lỗi tương tự ca B |
| D: `@Async CompletableFuture<T>` | Method body ném lỗi | Future của caller kết thúc exceptional, callback nhận lỗi |
| E: `@Async void` | Method body ném lỗi | `AsyncUncaughtExceptionHandler` được kích hoạt |
| F: cancellation | Hủy Future trước/đang thực thi | Xử lý `CancellationException` riêng; không coi là business failure |
| G: rejection | Saturate pool/queue hoặc shutdown | Caller nhận `TaskRejectedException`; task không chạy |
| H: cleanup | Task thành công/lỗi/cancel | Context/ThreadLocal được trả về trạng thái trước khi chạy |

**Cách tạo test ổn định:**

- Dùng `CountDownLatch`/barrier để xác nhận task bắt đầu, giữ worker tại điểm chặn rồi chủ động mở; đừng dùng duy nhất `Thread.sleep(100)` để chứng minh thứ tự race.
- Chạy trên đúng bean `ThreadPoolTaskExecutor` có decorator được cấu hình, không vô tình dùng common pool hoặc executor khác.
- Với `@Async`, lời gọi phải đi **qua Spring proxy** (bean khác gọi vào); `this.asyncMethod()` trong cùng target thường bypass interception.
- Với future, đặt thời hạn khi `get(timeout, unit)` hoặc `await` để test không treo vô hạn.
- Ghi nhận cả lỗi xuất hiện tại **submitter** và lỗi trong **worker/future**. Đây là hai điểm khác nhau.
- Khi đo metric, tránh double count nếu vừa có `Future.whenComplete`, vừa có logic `Future.get` ở decorator, vừa có logging trong method nghiệp vụ.
- Kiểm tra dọn dẹp worker, queue và context ngay cả khi assertion thất bại; đóng executor hoặc để Spring lifecycle đóng theo thiết kế.

### Assertion trọng tâm

Với ca B trên executor thực tế, cần chứng minh **hai điều đồng thời**:

```text
(1) Future.get() -> ExecutionException(cause=IllegalArgumentException)
(2) catch(RuntimeException) quanh callback.run()
    KHÔNG bắt được IllegalArgumentException đã bị FutureTask giữ.

Kết luận:
  TaskDecorator có thể đã CHẠY bình thường,
  nhưng nó vẫn KHÔNG thấy lỗi dưới dạng exception thoát từ run().
```

Đây là phép phân biệt quan trọng hơn việc chỉ kiểm tra “có log lỗi hay không”; log có thể đến từ nhiều nguồn khác nhau.

## 14. Checklist xử lý lỗi cho production

Khi thiết kế Spring service có executor và Future:

1. **Phân loại kiểu submission**: `execute`, `submit`, `CompletableFuture`, `@Async void` hay scheduler/adapter khác?
2. **Xác định Runnable thực tế đi vào decorator**: là task người dùng hay wrapper/FutureTask? Đừng ép kiểu dựa trên giả định.
3. **Chọn nơi sở hữu lỗi nghiệp vụ**: Future của caller, callback `CompletableFuture`, method boundary hoặc `AsyncUncaughtExceptionHandler`.
4. **Phân loại exception**: task failure, cancellation, timeout khi chờ, rejection ở submitter.
5. **Không block worker bằng get() tùy tiện**: chỉ chẩn đoán Future sau khi task hoàn tất, có `isDone()` và hiểu implementation; ưu tiên callback bất đồng bộ cho luồng kết quả.
6. **Giữ semantics**: decorator bắt RuntimeException/Error phải ném lại trừ khi cố ý chuyển sang một chính sách recovery được định nghĩa.
7. **Tách logging và recovery**: log không đồng nghĩa retry, không đồng nghĩa task được đánh dấu thành công.
8. **Xử lý rejection** ở cổng nộp việc, có backpressure/response/retry hoặc job store; không đặt toàn bộ trách nhiệm lên decorator.
9. **Giữ context sạch**: snapshot đúng lúc, restore ở `finally`, tránh rò ThreadLocal giữa worker pool.
10. **Không nhân đôi báo lỗi**: xác định owner của error metric/log với task ID và causal exception.
11. **Kiểm thử code thật** trên JDK/Spring/Boot version đang dùng: behavior của `submitCompletable`, `@Async`, callbacks và wrappers có thể không giống nhau.
12. **Bảo vệ tài nguyên**: bounded executor, queue, timeout JDBC/HTTP, metric về active/queued/rejected/failure và propagation ngữ cảnh.

### Bảng chọn vị trí quan sát lỗi

| Nhu cầu | Công cụ nên ưu tiên |
| --- | --- |
| Đo thời gian callback, MDC, trace context | `TaskDecorator` với `finally` |
| Bắt lỗi từ Runnable thuần được execute trực tiếp | `catch` quanh `run()` hoặc executor error hook |
| Biết vì sao một `FutureTask` thất bại | `Future.get()` → `ExecutionException.getCause()` |
| Quan sát lỗi của `CompletableFuture` không cần chặn | `whenComplete`/`handle` |
| Xử lý lỗi `@Async void` | `AsyncUncaughtExceptionHandler` |
| Xử lý lỗi nộp task khi hết chỗ | Catch `TaskRejectedException` tại submitter |
| Phân tích lỗi theo mã nghiệp vụ và retry | Handler/boundary ở tầng service/client |
| Test nguyên nhân lỗi và cleanup | Integration test có latch, timeout, assertions |

## 15. Tổng kết và tài liệu chính thức

**Ba câu cần nhớ:**

1. **`TaskDecorator` bọc `Runnable` thực tế**; nó không nhất thiết nhìn thấy task nguyên gốc.
2. **`FutureTask.run()` lưu exception thay vì ném ra ngoài**, nên `catch` quanh `run()` không đủ để quan sát lỗi của `submit`/future-backed tasks.
3. **Xử lý lỗi theo loại kết quả và đúng ranh giới**: `Future.get()`, `CompletableFuture.whenComplete(...)`, `AsyncUncaughtExceptionHandler` hoặc catch `TaskRejectedException` ở nơi submit; giữ TaskDecorator cho context/metrics và chỉ bổ sung future inspection khi biết rõ wrapper thật.

**Tài liệu đối chiếu:**

- [Spring Framework 6.2 – ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html) — `setTaskDecorator` và cảnh báo khi callback là `FutureTask`.
- [Spring Framework 6.2 – TaskDecorator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/task/TaskDecorator.html) — hợp đồng decorate callback và giới hạn bắt lỗi.
- [Java SE 17 – FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html) — `run`, `get` và `setException`.
- [Java SE 17 – ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — `afterExecute` và cách xem lỗi của Future.
- [Java SE 17 – CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — `whenComplete`, `handle`, `join`.
- [Spring Framework 6.2 – Async exception management](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html#scheduling-annotation-support-exception) — xử lý lỗi `@Async Future` và `@Async void`.
- [Spring Framework 6.2 – ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html) — truyền context logging/observation.

**Kết luận:** Khi `TaskDecorator.catch` không log được một lỗi từ tác vụ `submit`, nguyên nhân có thể hoàn toàn hợp lệ: lỗi đã nằm trong `FutureTask`, không thoát khỏi `Runnable.run()`. Đừng “chữa” bằng cách bọc thêm nhiều `try/catch` vào decorator; hãy đọc/đăng ký xử lý ở **kết quả Future**, giữ decorator làm đúng nhiệm vụ context/metrics, và kiểm chứng bằng thử nghiệm trên executor thực tế.
