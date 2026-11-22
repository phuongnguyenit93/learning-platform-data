# Khác biệt đường truyền ngoại lệ giữa execute() và submit()

> **Chủ đề:** Spring Framework – Concurrency / Gửi và nhận tác vụ.  
> **Ý chính:** Với executor chạy trên worker thread, `execute(Runnable)` có thể để ngoại lệ không được bắt thoát ra khỏi `Runnable.run()` và đi qua cơ chế xử lý exception của worker. Trong khi đó, `submit(...)` của `ExecutorService` thông dụng bọc công việc thành một `FutureTask`, giữ ngoại lệ trong `Future` và cho bên gọi lấy lại qua `Future.get()` dưới dạng `ExecutionException`. Tuy nhiên, cả hai đều có thể ném **lỗi nộp việc** ngay tại caller; và một executor chạy đồng bộ hay dùng `CallerRunsPolicy` có thể thay đổi đường truyền lỗi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt ngoại lệ **trong tác vụ** với ngoại lệ **khi nộp tác vụ**.
2. Nêu hợp đồng của `Executor.execute(Runnable)`, `ExecutorService.submit(Runnable)`, `submit(Callable<T>)` và vai trò của `Future`.
3. Giải thích cơ chế `FutureTask`, `ExecutionException.getCause()`, `UncaughtExceptionHandler` và `ThreadPoolExecutor.afterExecute`.
4. Dự đoán khi nào `try/catch` ở caller bắt được exception và khi nào không.
5. Phân tích các góc cạnh trong Spring `ThreadPoolTaskExecutor`, `TaskDecorator`, `@Async void` và `@Async Future/CompletableFuture`.
6. Viết ví dụ Java 17 chạy được, đọc stdout đáng tin và thiết kế error handling, timeout/cancellation/rejection nhất quán.

## 2. Đầu tiên: có hai thời điểm lỗi rất khác nhau

Một lời gọi executor thường liên quan hai giai đoạn:

~~~text
Caller
   |
   +-- execute(task) / submit(task)
   |      |
   |      +-- Giai đoạn 1: nhận hoặc từ chối task
   |                |
   |                +-- rejection -> exception ngay trong caller
   |
   +-- Giai đoạn 2: chạy task (worker, hoặc đôi khi caller)
          |
          +-- code của Runnable/Callable thành công
          |
          +-- code của Runnable/Callable ném exception
                 |
                 +-- Runnable thô: có thể thành uncaught của worker
                 |
                 +-- FutureTask: lưu exception, đọc từ Future.get()
~~~

**Lỗi nộp (submission failure):** executor không thể nhận thêm công việc do shutdown, bão hòa, sai đối số hoặc lỗi được phát hiện ngay khi dispatch. `RejectedExecutionException` của JDK, hoặc `TaskRejectedException` qua abstraction Spring, có thể được ném ngay tại lời gọi. Một catch bao quanh `execute/submit` có cơ hội bắt loại lỗi này.

**Lỗi thực thi (task failure):** công việc đã được nhận, sau đó code trong `run()/call()` ném lỗi (ví dụ `IllegalStateException`, lỗi mạng, lỗi dữ liệu). Với tác vụ chạy trên worker, đây là **call stack khác**. Nó không tự nhảy ngược về catch đã rời khỏi caller.

Cần giữ riêng hai loại lỗi trong mọi thiết kế logging, API response, retry và quan sát trạng thái. `submit` trả `Future` chỉ khi phương thức nộp công việc trả về thành công; không phải mọi lỗi rejection đều được “biến thành Future bị lỗi”.

## 3. execute(Runnable): không có kênh kết quả mặc định

Giao diện `java.util.concurrent.Executor` rất nhỏ:

~~~java
public interface Executor {
    void execute(Runnable command);
}
~~~

Phương thức trả kiểu `void`, nên chính lời gọi này **không có `Future`** để chờ, hủy hay đọc kết quả. Với `ThreadPoolExecutor` chuẩn khi task là `Runnable` thô:

- Caller có thể trả về sau khi pool nhận task.
- Worker gọi `Runnable.run()`.
- Nếu `run()` ném một `RuntimeException`/`Error` không được bắt, task kết thúc bất thường. Hook `afterExecute(...)` có thể nhận exception; cơ chế `Thread.UncaughtExceptionHandler` của worker cũng có thể xử lý.
- Vì lỗi xuất hiện ở worker, catch trong caller thông thường **không bắt được**; một số môi trường in stack trace trên stderr, nhưng đó không phải bảo đảm báo lỗi nghiệp vụ cho caller.
- Thread worker có thể kết thúc và được pool thay thế; không được đánh đồng “một task chết vì lỗi” với “toàn bộ pool bị hỏng”.

Một ví dụ code dễ hiểu sai:

~~~java
try {
    pool.execute(() -> {
        throw new IllegalStateException("inside worker");
    });
} catch (IllegalStateException ex) {
    // Không mặc nhiên bắt được lỗi của worker ở đây.
}
~~~

Đây là **snippet**: `pool` phải là biến đã khai báo và khởi tạo.

**Ngoại lệ:** Một `Executor` có thể chạy thẳng `command.run()` trong cùng caller (ví dụ direct executor/`SyncTaskExecutor` của Spring). Ngoài ra, khi pool bão hòa, `CallerRunsPolicy` có thể chạy task ngay trong caller. Với các trường hợp đó, lỗi của `Runnable` thô có thể ném trực tiếp qua `execute`. Không thể phát biểu tuyệt đối “execute không bao giờ ném lỗi task cho caller”.

## 4. submit(...): FutureTask thay đổi đường đi của exception

`ExecutorService` thêm API `submit`:

~~~java
Future<?> submit(Runnable task);
<T> Future<T> submit(Callable<T> task);
<T> Future<T> submit(Runnable task, T result);
~~~

Với triển khai phổ biến dựa trên `AbstractExecutorService`:

1. `submit` tạo wrapper tương tự `FutureTask` để theo dõi trạng thái.
2. Executor được yêu cầu chạy wrapper (thường bằng cơ chế `execute(...)` ở tầng dưới).
3. Khi task ném exception, `FutureTask.run()` **bắt và lưu** exception vào trạng thái thất bại của Future; exception không thoát khỏi `run()` của wrapper như một `Runnable` thô.
4. `Future.get()` bên caller chờ tới khi có kết quả. Nếu task thất bại, `get()` ném `ExecutionException`, và `getCause()` chứa exception gốc.
5. Nếu `Runnable` thành công và bạn gọi `submit(Runnable)` không chỉ định result, `get()` trả `null`; nếu dùng `Callable<T>`, `get()` trả `T` do task tính.

~~~text
Caller                                 Worker
  |                                      |
  +-- submit(task)                       |
  |     +-- FutureTask(task) ------------+-- FutureTask.run()
  |     +-- return Future                 |    +-- gọi task
  |                                      |    +-- task throw
  |                                      |    +-- FutureTask giữ cause
  |                                      |
  +-- future.get() ----------------------+-- Future hoàn thành
          |
          +-- ExecutionException
                |
                +-- getCause() -> lỗi thực từ task
~~~

“Submit nuốt mất exception” là cách nói không chính xác. **Lỗi còn trong Future**, nhưng khi ứng dụng bỏ quên `Future` và không có observer khác thì lỗi có thể trở thành **vô hình về mặt vận hành**.

## 5. Bảng so sánh cách nhận lỗi

| Tiêu chí | `execute(Runnable)` | `submit(Runnable/Callable)` |
| --- | --- | --- |
| Interface gốc | `Executor` | `ExecutorService`; trong Spring có các executor hỗ trợ `submit` |
| Giá trị trả về | `void` | `Future<?>` hoặc `Future<T>` |
| Kết quả task | Không có handle do method trả về | `Future.get()`: `T`, kết quả định trước hoặc `null` |
| Exception task trên worker pool thông dụng | Thường thoát khỏi `Runnable.run()` → hook/uncaught handler | Thường được wrapper `FutureTask` ghi nhận |
| Cách bên gọi biết task đã thất bại | Chủ động thiết kế callback/error channel | Gọi `Future.get()`/dùng completion observer |
| Exception ở caller khi nộp task | Có thể ném rejection | Cũng có thể ném rejection trước khi có Future |
| Caller tự bắt exception logic task? | Có thể nếu task thực thi trên caller; thường không nếu ở worker | Thường phải lấy lỗi từ Future, ngay cả khi `CallerRunsPolicy` chạy wrapper trên caller |
| Hủy công việc | Method không trả handle hủy | `Future.cancel(...)` có khả năng hủy ở mức best-effort |
| Bảo đảm task chạy thread khác? | Không | Cũng không |

Hai cột mô tả triển khai phổ biến, không bao trùm mọi executor tự viết. Chú ý **kiểu đối tượng thực sự được executor chạy**: một `FutureTask` được đưa vào qua `execute` cũng giữ exception của logic gốc!

## 6. Java 17 độc lập: thấy đúng cả hai đường exception

Ví dụ chạy thực tế này dùng một worker và `ThreadFactory` đặt custom `UncaughtExceptionHandler`, để không phải phụ thuộc stack trace mặc định trên stderr. `CountDownLatch` giữ thứ tự output, `Future.get(timeout)` bảo đảm không đọc kết quả sớm.

Tạo **`ExecuteSubmitExceptionDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ExecuteSubmitExceptionDemo {

    public static void main(String[] args) throws Exception {
        CountDownLatch handlerDone = new CountDownLatch(1);
        AtomicInteger uncaughtEvents = new AtomicInteger();

        ThreadFactory factory = work -> {
            Thread thread = new Thread(work, "demo-worker");
            thread.setUncaughtExceptionHandler((t, ex) -> {
                uncaughtEvents.incrementAndGet();
                System.out.println("uncaught = "
                        + ex.getClass().getSimpleName()
                        + ": " + ex.getMessage());
                handlerDone.countDown();
            });
            return thread;
        };

        ExecutorService pool =
                Executors.newSingleThreadExecutor(factory);
        try {
            pool.execute(() -> {
                throw new IllegalStateException("execute-fail");
            });

            if (!handlerDone.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("handler timed out");
            }
            System.out.println("execute has Future = false");

            Future<?> failed = pool.submit(() -> {
                throw new IllegalArgumentException("submit-fail");
            });

            try {
                failed.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println("submit cause = "
                        + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
            }

            Future<String> success = pool.submit(() -> "OK");
            System.out.println("callable result = "
                    + success.get(5, TimeUnit.SECONDS));

            Future<?> done = pool.submit(() -> { });
            System.out.println("runnable result = "
                    + done.get(5, TimeUnit.SECONDS));

            // Dùng execute nhưng đưa vào một FutureTask.
            FutureTask<Integer> wrapped = new FutureTask<>(() -> {
                throw new IllegalArgumentException("wrapped-fail");
            });
            pool.execute(wrapped);
            try {
                wrapped.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                System.out.println("wrapped cause = "
                        + ex.getCause().getMessage());
            }
            System.out.println("uncaught events = "
                    + uncaughtEvents.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac ExecuteSubmitExceptionDemo.java
java ExecuteSubmitExceptionDemo
~~~

**Stdout dự kiến chính xác khi chạy thành công:**

~~~text
uncaught = IllegalStateException: execute-fail
execute has Future = false
submit cause = IllegalArgumentException: submit-fail
callable result = OK
runnable result = null
wrapped cause = wrapped-fail
uncaught events = 1
~~~

Giải thích:

- Lỗi đầu tiên thoát khỏi `Runnable.run()` thô do `execute` dispatch; custom worker handler in `uncaught` và tăng bộ đếm.
- `handlerDone.await()` không cho main in dòng tiếp theo trước khi handler thực hiện.
- Lỗi từ `submit` được đưa qua `Future.get()` rồi mới in, không tăng số uncaught event.
- `submit(Callable<String>)` thành công trả `OK`. `submit(Runnable)` thành công trả `null`.
- `FutureTask` được đưa qua chính **`execute`** vẫn giữ exception: chứng minh wrapper quan trọng hơn tên method.
- `newSingleThreadExecutor` có thể thay worker bị lỗi, và các task tiếp theo vẫn xử lý bình thường. `shutdown/awaitTermination` dọn tài nguyên.

Đây là **chương trình chạy độc lập**, không cần Maven/Spring. Không dùng `Thread.sleep` để tạo một lịch thực thi may rủi.

## 7. Một bẫy quan trọng: execute(FutureTask) không giống execute(Runnable) thô

Mã sau:

~~~java
FutureTask<Integer> wrapped = new FutureTask<>(() -> {
    throw new IllegalStateException("boom");
});
pool.execute(wrapped);
wrapped.get();
~~~

là một **snippet minh họa**, cần `pool`, import `FutureTask` và xử lý checked exceptions.

Nếu `wrapped` là FutureTask, lỗi gốc bị bắt trong `FutureTask.run()`, **không** làm worker kết thúc bất thường theo cách của `Runnable` thô. `wrapped.get()` ném `ExecutionException` chứa `IllegalStateException`.

Điều này làm rõ một điểm sâu hơn: `submit` điển hình cũng sẽ gọi tầng thực thi với một wrapper chứa trạng thái kết quả. **Cùng một executor và cùng một lỗi có thể đi theo hai kênh quan sát chỉ vì một bên bọc công việc vào FutureTask**. Vì vậy, khi debug không chỉ đọc `execute/submit` ở dòng gọi; cần biết object thực sự nằm trong queue.

## 8. Vì sao try/catch đặt ở caller thường không hoạt động?

~~~java
try {
    executor.execute(() -> {
        throw new IllegalStateException("worker failed");
    });
} catch (IllegalStateException ex) {
    // Không mặc nhiên vào đây nếu task chạy trên worker khác.
}
~~~

Đây không phải class chạy độc lập vì `executor` chưa được khởi tạo.

`try/catch` chạy trong call stack của caller. Task trên worker có call stack của worker, nên exception không thể “nhảy thread” đến catch của caller nếu không có cơ chế truyền tín hiệu/result rõ ràng.

Tuy nhiên, catch trên caller **có thể** bắt lỗi khi:

1. Executor đồng bộ gọi `Runnable.run()` trực tiếp trong caller, ví dụ `SyncTaskExecutor`.
2. Pool bão hòa với `CallerRunsPolicy` và handler tự gọi `run()` của `Runnable` thô ngay trên caller.
3. Phần code nộp task/đánh giá decorator ném exception đồng bộ trước khi task được dispatch.
4. Executor từ chối tác vụ với exception khi nó đã shutdown hoặc full.

Vì thế, câu “`execute` luôn cho lỗi lên caller” và câu “`execute` không bao giờ cho lỗi lên caller” **đều sai** nếu không nói rõ implementation và nơi chạy task.

## 9. Lỗi nộp việc: cả execute và submit đều có thể ném ngay

Với `ExecutorService` đã shutdown:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
executor.shutdown();

try {
    executor.submit(() -> System.out.println("never runs"));
} catch (java.util.concurrent.RejectedExecutionException ex) {
    System.out.println("submission rejected on caller");
}
~~~

Đoạn này có thể đặt trong một method có import `ExecutorService`/`Executors`. Trong implementation JDK thông dụng dùng `AbortPolicy`, exception xảy ra **ở lời gọi `submit`**, không phải một lỗi task được giữ trong Future. Khi `submit` ném exception như vậy, nó không trả về Future thành công để caller lấy kết quả.

### 9.1. Rejection policy có thể đổi đường truyền lỗi

| Policy của `ThreadPoolExecutor` | `execute(Runnable)` thô khi full | `submit(...)` (wrapper FutureTask) khi full |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` tại caller | Ném rejection tại caller, không trả Future |
| `CallerRunsPolicy`, chưa shutdown | Caller thực thi `Runnable.run()`; lỗi có thể ném trực tiếp | Caller chạy FutureTask; task exception thường được lưu cho `get()` |
| `DiscardPolicy` | Task có thể bị bỏ mà caller không biết | Có thể nhận Future **không bao giờ hoàn thành**, nếu wrapper bị bỏ |
| `DiscardOldestPolicy` | Bỏ task ở đầu queue để thử enqueue task mới | Future của task bị loại khỏi queue có thể không hoàn thành nếu không có cancel bổ sung |

Không nên chọn các policy silent discard cho nghiệp vụ yêu cầu xác nhận thành công/thất bại nếu chưa có cơ chế hủy, bù hoặc quan sát riêng. Với `CallerRunsPolicy`, một request HTTP có thể bất ngờ phải chạy task trên request thread, gây tăng latency. Với `submit`, chính FutureTask vẫn giữ lỗi ngay cả nếu việc chạy xảy ra trong caller.

### 9.2. TaskRejectedException trong Spring

Spring `ThreadPoolTaskExecutor` dùng abstraction `TaskExecutor` và thường chuyển rejection của executor nền thành `org.springframework.core.task.TaskRejectedException`:

~~~java
import org.springframework.core.task.TaskRejectedException;

try {
    reportExecutor.execute(job);
} catch (TaskRejectedException ex) {
    // Thực thi chính sách quá tải: fail fast, retry có giới hạn,
    // trả lỗi thích hợp hoặc giao cho job store bền vững.
}
~~~

Đây là **snippet**, cần `reportExecutor`/`job` đã được khai báo. `TaskRejectedException` là **lỗi tại submission**, không phải `ExecutionException` bên trong `Future.get()`. Khi sử dụng `submit`, code cần xử lý **cả rejection ngay lúc gọi** và **failure đọc từ Future sau đó**.

## 10. Future.get: đọc lỗi, kết quả, timeout, cancel đúng cách

### 10.1. ExecutionException và nguyên nhân gốc

`Future.get()` có thể chờ cho đến khi task hoàn thành. Nếu task thất bại, `get()` ném một `ExecutionException` và `getCause()` trả exception logic gốc. Ví dụ:

~~~text
Future.get()
   |
   +-- ExecutionException
           |
           +-- getCause()
                   |
                   +-- IllegalArgumentException("bad input")
~~~

Một snippet sử dụng timeout:

~~~java
try {
    String answer = future.get(3, TimeUnit.SECONDS);
    return answer;
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    throw new IllegalStateException("task failed", cause);
} catch (TimeoutException ex) {
    future.cancel(true);
    throw new IllegalStateException("task timed out", ex);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    future.cancel(true);
    throw new IllegalStateException("wait interrupted", ex);
} catch (CancellationException ex) {
    throw new IllegalStateException("task cancelled", ex);
}
~~~

Đây là **method-body snippet**, cần `Future<String> future` và imports các exception tương ứng. Nó là một chính sách minh họa, không phải bắt buộc luôn phải cancel khi timeout.

Quan trọng:

- `get(timeout)` ném `TimeoutException` nghĩa là **caller không đợi thêm**; task có thể vẫn chạy.
- `cancel(true)` chỉ **cố gắng** hủy, thường qua interrupt; nếu task đang làm blocking I/O không hỗ trợ interrupt, nó vẫn có thể còn chạy.
- Khi đón `InterruptedException`, thường phải khôi phục interrupt flag hoặc truyền tiếp exception phù hợp.
- `CancellationException` khác với business exception và khác lỗi rejection.
- `Future.isDone() == true` có thể là thành công, thất bại hoặc đã cancel. Không thể chỉ nhìn isDone để kết luận tác vụ thành công.

### 10.2. Runnable thành công có get() == null

~~~java
Future<?> f = executor.submit(() -> doSideEffect());
Object value = f.get(); // null khi Runnable hoàn thành bình thường.
~~~

Đây là snippet với `executor` và `doSideEffect()` được khai báo ở ứng dụng. `null` là completion value đúng của overload `submit(Runnable)`, không phải dấu hiệu lỗi.

### 10.3. Đừng bỏ quên Future

~~~java
executor.submit(() -> {
    sendMessage();
    throw new IllegalStateException("message failed");
});

// Không lưu Future, không get, không callback, không job-status.
~~~

Đoạn trên có thể khiến lỗi bị lưu trong FutureTask và không ai đọc. Nếu nghiệp vụ không cần chặn caller, hãy dùng callback/completion observer hoặc trạng thái job. Nếu công việc cần tiếp tục sau restart/crash, cần message queue/job store bền vững, không chỉ thread pool in-memory.

## 11. afterExecute() và UncaughtExceptionHandler: tại sao hai lỗi nhìn khác nhau?

`ThreadPoolExecutor` có hook:

~~~java
protected void afterExecute(Runnable task, Throwable error);
~~~

Với một `Runnable` thô ném exception không được bắt, `error` có thể là exception đó. Nhưng với `submit(...)`, `FutureTask.run()` bắt và ghi exception vào trạng thái Future, nên `afterExecute(..., error)` **thường nhận `error == null`** dù logic task thất bại.

Javadoc Java SE gợi ý kiểm tra Future wrapper khi đã hoàn thành:

~~~java
@Override
protected void afterExecute(Runnable task, Throwable error) {
    super.afterExecute(task, error);

    if (error == null
            && task instanceof Future<?> future
            && future.isDone()) {
        try {
            future.get();
        } catch (CancellationException ex) {
            error = ex;
        } catch (ExecutionException ex) {
            error = ex.getCause();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    if (error != null) {
        reportFailure(error);
    }
}
~~~

Đây là **method trong một subclass của `ThreadPoolExecutor`**, không độc lập; cần import Future và các exception, cùng phương thức `reportFailure(...)` do ứng dụng tự định nghĩa.

Vì `future.isDone()` true, việc gọi `get()` trong mẫu này không chờ task chưa hoàn thành. Cần phân biệt cancellation hợp lệ với failure nghiệp vụ; các wrapper/decorator tùy biến có thể khiến `task` không còn trực tiếp là `Future`, nên không được coi snippet là một giải pháp universal.

**Thread.UncaughtExceptionHandler** có thể quan sát exception làm worker kết thúc bất thường nhưng thông thường không được gọi cho task failure đã bị `FutureTask` giữ lại. Và ngay cả khi handler log được lỗi, caller vẫn **không tự có kết quả nghiệp vụ**. Phải xây đường phản hồi riêng nếu cần.

## 12. Spring ThreadPoolTaskExecutor: dùng đúng kênh lỗi

Spring Framework cung cấp `ThreadPoolTaskExecutor`, hỗ trợ `execute` và `submit`. Cấu hình bean có thể là:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class ExecutorConfig {
    @Bean("businessExecutor")
    ThreadPoolTaskExecutor businessExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("business-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return pool; // Container khởi tạo và hủy pool.
    }
}
~~~

Đây là **snippet cấu hình Spring**, chưa phải chương trình độc lập; cần ứng dụng có `spring-context` hoặc starter Spring Boot tương ứng.

- `execute` dùng để gửi một `Runnable`; nếu task thô chạy trên worker và ném lỗi, nó có thể đi theo uncaught/error-observer của worker, không tự trở lại caller.
- `submit` trả `Future` cho phép caller lấy cause bằng `get()`.
- Khi queue/full, chính sách rejection quyết định liệu lỗi xuất hiện ngay lúc submission, chuyển việc sang caller hay bỏ task.
- Một TaskDecorator có thể bọc object thực thi; với `submit` object ấy thường đã là `FutureTask`.

### 12.1. Service sử dụng submit và giữ Future

~~~java
import java.util.concurrent.Future;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ThreadPoolTaskExecutor executor;

    public ReportService(
            @Qualifier("businessExecutor")
            ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public Future<String> start(String jobId) {
        return executor.submit(() -> runJob(jobId));
    }

    private String runJob(String jobId) {
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException("missing jobId");
        }
        return "done:" + jobId;
    }
}
~~~

Đây là **service snippet** cho ứng dụng Spring; không có `main`. Điểm quan trọng không phải chỉ “gọi submit”, mà là caller phải **sở hữu Future**, kiểm tra completion/failure và biến kết quả đó thành trạng thái nghiệp vụ phù hợp.

### 12.2. Ví dụ Spring Context độc lập chạy bằng Maven + Java 17

Dự án nhỏ chứng minh `ThreadPoolTaskExecutor.submit(Callable)` giữ exception, Spring container quản lý lifecycle; không cần Spring Boot hay Web server.

Cấu trúc:

~~~text
spring-exception-demo/
├── pom.xml
└── src/main/java/demo/SpringFutureDemo.java
~~~

Tệp **`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-exception-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp **`src/main/java/demo/SpringFutureDemo.java`**:

~~~java
package demo;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SpringFutureDemo {

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean("workExecutor")
        ThreadPoolTaskExecutor workExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(8);
            pool.setThreadNamePrefix("work-");
            pool.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.AbortPolicy());
            return pool;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            ThreadPoolTaskExecutor executor =
                    context.getBean("workExecutor",
                            ThreadPoolTaskExecutor.class);

            Future<String> failed = executor.submit(() -> {
                throw new IllegalStateException("spring-failed");
            });

            try {
                failed.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println("spring cause = "
                        + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
            }

            Future<Integer> good = executor.submit(() -> 40 + 2);
            System.out.println("spring result = "
                    + good.get(5, TimeUnit.SECONDS));
        }
    }
}
~~~

Chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SpringFutureDemo
~~~

**Stdout của class demo** khi chạy thành công (không tính thông báo riêng từ Maven nếu có):

~~~text
spring cause = IllegalStateException: spring-failed
spring result = 42
~~~

`get(5, TimeUnit.SECONDS)` chờ Future hoàn thành; exception gốc được lấy từ `ExecutionException`. Context tự quản lý bean và đóng executor khi đóng context. Đây là đường lỗi Spring tương ứng với `submit`; ví dụ Java 17 ở phần 6 đã minh họa rõ đường lỗi `execute`.

## 13. TaskDecorator của Spring có bẫy với submit

`ThreadPoolTaskExecutor#setTaskDecorator(...)` cho phép bọc callback thực thi để đặt MDC/tracing, đo thời gian hoặc log:

~~~java
executor.setTaskDecorator(original -> () -> {
    try {
        original.run();
    } catch (RuntimeException ex) {
        logger.error("task failed", ex);
        throw ex;
    }
});
~~~

Đây là **snippet**, giả định `executor` và `logger` có sẵn. Với `execute(Runnable)` thô, decorator có thể thấy exception thoát khỏi `run()`. Nhưng trong đường `submit`, `original` thường là `FutureTask` hoặc callback bao quanh nó. `FutureTask.run()` giữ lỗi bên trong, do đó catch trong decorator **có thể không chạy** dù task gốc đã thất bại.

Javadoc Spring có lưu ý chính thức về trường hợp này. Nếu cần quan sát tất cả failure, đừng dựa duy nhất vào `TaskDecorator.catch`. Hãy có chủ sở hữu `Future`/completion observer; hoặc xây một error-monitoring layer hiểu đúng wrapper và tránh block worker.

## 14. @Async void và @Async Future/CompletableFuture

`@Async` là abstraction interception của Spring; exception của một phương thức được `@Async` xử lý có đường đi phụ thuộc **kiểu trả về**. Cần có `@EnableAsync`/cấu hình tương đương và invocation đi **qua proxy**; self-invocation bằng `this.method()` trong proxy mode mặc định không kích hoạt async interception.

### 14.1. @Async void: không có Future cho caller

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
class MailService {
    @Async("businessExecutor")
    public void send(String recipient) {
        throw new IllegalStateException("mail failed");
    }
}
~~~

Đây là service snippet. Caller không có `Future` để nhận lỗi. Với `@Async void` có interception hợp lệ, Spring dùng `AsyncUncaughtExceptionHandler` để xử lý exception do phương thức ném. Handler mặc định thường log lỗi; ứng dụng có thể đăng ký handler tùy chỉnh.

Đây **không phải** `Thread.UncaughtExceptionHandler` của Java. Không được suy rằng mọi lỗi `@Async void` sẽ làm chết worker hoặc tự xuất hiện trong try/catch controller.

### 14.2. Tùy chỉnh AsyncUncaughtExceptionHandler

~~~java
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncErrorConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, args) -> {
            System.err.println("async method failure = "
                    + method.getName() + ": " + error.getMessage());
            // Ứng dụng thật: log có correlation ID, alert, job-status.
        };
    }
}
~~~

Đây là **class cấu hình Spring**, không có `main`. Với `@Async("businessExecutor")`, Spring chọn executor được chỉ định theo bean name/qualifier. Cấu hình này xử lý **ngoại lệ của void @Async method**; không thay thế việc caller phải đọc `Future` khi method trả Future.

### 14.3. @Async trả CompletableFuture

~~~java
@Async("businessExecutor")
public CompletableFuture<String> load(String key) {
    if (key.isBlank()) {
        throw new IllegalArgumentException("empty key");
    }
    return CompletableFuture.completedFuture("value:" + key);
}
~~~

Đây là method snippet, cần import `CompletableFuture` và `@Async`. Nếu phương thức được gọi qua Spring proxy:

- Caller nhận `CompletableFuture` để theo dõi việc hoàn thành.
- `future.get()` thất bại với `ExecutionException` có cause.
- `future.join()` thông thường ném `CompletionException` (unchecked) có cause khi thất bại.
- `whenComplete`, `handle` hoặc `exceptionally` cho phép xử lý không chặn.
- Lời gọi từ chính instance không qua proxy sẽ đi theo Java call stack bình thường và không có nghĩa vụ chạy async.

Một observer:

~~~java
service.load(key).whenComplete((value, error) -> {
    if (error != null) {
        logger.error("load failed for key={}", key, error);
    }
});
~~~

Đây là code tích hợp, cần `service`, `key` và `logger`. Callback có thể chạy trên thread hoàn tất future, vì vậy không gán cho nó giả định về `ThreadLocal`/transaction của caller. Một exception trong callback có thể làm completion stage của callback thất bại; phải theo dõi cả đường lỗi đó khi quan trọng.

## 15. CompletableFuture cũng chứng minh wrapper quan trọng

~~~java
CompletableFuture<Integer> f = CompletableFuture.supplyAsync(
        () -> {
            throw new IllegalStateException("calculation failed");
        },
        executor);

f.whenComplete((value, ex) -> {
    if (ex != null) {
        report(ex);
    }
});
~~~

Đây là snippet, giả định `executor` thực thi `Executor` và có hàm `report`.

Ngay cả khi implementation sử dụng `Executor.execute(...)` để dispatch callback nội bộ, `CompletableFuture` có cơ chế ghi trạng thái completion/exception của chính nó. Vì thế, quy tắc “execute luôn ra uncaught handler” là sai khi object thực thi có wrapper bắt lỗi.

Khác biệt cần nhớ:

| API đọc kết quả | Khi thất bại thông thường |
| --- | --- |
| `Future.get()` | `ExecutionException` (checked), `getCause()` chứa nguyên nhân |
| `CompletableFuture.get()` | `ExecutionException` (checked) |
| `CompletableFuture.join()` | `CompletionException` (unchecked), lấy cause để phân loại |
| `whenComplete(...)` | Nhận cả value/error trên completion, không tự block caller |
| `exceptionally(...)` | Có thể thay failure bằng giá trị fallback |
| `handle(...)` | Biến đổi cả success/failure, có thể thay kết quả cuối |

Future/completion không tự bảo đảm chạy khác thread; nếu executor là direct executor, việc chạy có thể diễn ra ngay ở caller.

## 16. Thiết kế xử lý lỗi theo trách nhiệm

| Tình huống | Kênh quan sát phù hợp | Cần chú ý |
| --- | --- | --- |
| `execute` với Runnable thô trên worker | Worker error handler / structured task logging | Caller không tự có kết quả; report failure có job ID |
| `submit` với Callable thất bại | `Future.get()`, completion observer | Đừng bỏ Future; unwrap `ExecutionException` |
| `@Async void` thất bại | `AsyncUncaughtExceptionHandler` | Không có Future trả caller |
| `@Async CompletableFuture` thất bại | Future exceptional / callback | Đừng chặn HTTP request vô hạn |
| Pool từ chối lúc nộp | `RejectedExecutionException` / Spring `TaskRejectedException` | Quyết định fail fast, backpressure, retry hoặc queue bền vững |
| Task bị hủy | `CancellationException` | Hủy chủ động không nhất thiết là business failure |
| Chờ Future quá deadline | `TimeoutException` | Task có thể vẫn chạy sau timeout |
| Thread chờ bị interrupt | `InterruptedException` | Khôi phục interrupt hoặc truyền lên policy |
| FutureTask trong `afterExecute` | Quan sát `Future.get()` nếu đã done | `Throwable == null` không chứng minh task thành công |

Một nguyên tắc thực hành là **một nơi sở hữu trạng thái kết quả**. Nếu worker, decorator, callback, controller và service cùng log một exception, sẽ có log trùng và khó suy nguyên nhân. Chọn nơi cập nhật job status, nơi log và nơi trả lỗi cho khách hàng rõ ràng.

### 16.1. Wrapper log lỗi mà vẫn giữ fail state

~~~java
public static Runnable withErrorReport(
        String jobId,
        Runnable work,
        java.util.function.BiConsumer<String, Throwable> reporter) {
    return () -> {
        try {
            work.run();
        } catch (RuntimeException | Error ex) {
            reporter.accept(jobId, ex);
            throw ex;
        }
    };
}
~~~

Đây là **phương thức có thể đặt trong utility class**. Nó giúp báo lỗi tại nơi task chạy, kể cả khi sau này task được gửi bằng `submit` và bọc thành FutureTask. Cần tránh để `reporter` tự ném lỗi che mất cause gốc; trong production nên thiết kế observer robust, cân nhắc log một lần và cập nhật status.

### 16.2. Lỗi task, giao dịch và context

`@Transactional` thường gắn transaction association vào thread. Nếu task chạy trên worker, transaction của caller không tự đi theo, bất kể dùng `execute` hay `submit`. Tương tự, MDC/tracing, security context hay request context thường cần giải pháp propagation cụ thể. **Lỗi không được gửi về caller** cũng không có nghĩa transaction của caller sẽ tự rollback khi worker ném lỗi.

Nếu nghiệp vụ cần lỗi quyết định transaction/câu trả lời HTTP, phải thiết kế điểm đồng bộ/orchestration và transaction boundary tương ứng, không chỉ thêm một try/catch bên ngoài lệnh submit.

## 17. Kiểm thử đúng đường ngoại lệ

### 17.1. Test submit bằng Future.get

Ví dụ JUnit 5, **snippet** yêu cầu pool fixture, imports và assertions:

~~~java
Future<?> failed = pool.submit(() -> {
    throw new IllegalArgumentException("invalid");
});

ExecutionException ex = assertThrows(
        ExecutionException.class,
        () -> failed.get(3, TimeUnit.SECONDS));

assertEquals(IllegalArgumentException.class,
        ex.getCause().getClass());
assertEquals("invalid", ex.getCause().getMessage());
~~~

Không dùng `Thread.sleep(100)` rồi thử xem log có stack trace không. Với `submit`, lỗi vốn có thể được giữ trong Future và không in ra stderr.

### 17.2. Test execute với handler có đồng bộ

Cấp `ThreadFactory` tùy biến ghi `Throwable` vào `BlockingQueue<Throwable>` hoặc đếm `CountDownLatch` sau khi thấy exception. Test đợi bounded timeout rồi assert loại exception. Ví dụ Java 17 ở phần 6 đã làm chính điều này, nên không phụ thuộc vào thời gian scheduler.

### 17.3. Những đường biên phải kiểm tra

- Lỗi runtime trong `execute(Runnable)` trên worker.
- Lỗi runtime trong `submit(Runnable/Callable)`, kể cả đúng cause sau `Future.get()`.
- `execute(FutureTask)` để xác nhận wrapper giữ lỗi.
- Lỗi rejection khi executor shutdown/full.
- `CallerRunsPolicy` với Runnable thô và FutureTask wrapper.
- `Future.get(timeout)`, cancel, interrupt; task có thể vẫn chạy nếu không phản ứng interrupt.
- Spring `TaskDecorator` với `submit`, `@Async void` có handler, `@Async CompletableFuture`.
- Error logging không trùng, có job ID/correlation ID, không lộ dữ liệu nhạy cảm.
- Dọn executor và Spring context đúng cách sau test.

## 18. Những ngộ nhận thường gặp

**1. “execute luôn ném exception task cho caller.”** Sai: worker có call stack khác. Caller chỉ có thể thấy lỗi synchronous hoặc lỗi nộp việc nếu không có cơ chế result riêng.

**2. “execute không bao giờ ném lỗi.”** Sai: executor đồng bộ, `CallerRunsPolicy` và rejection vẫn có thể ném cho caller.

**3. “submit nuốt mất lỗi mãi mãi.”** Sai: Future giữ cause; cần `get()` hoặc observer. Lỗi thực sự bị bỏ sót khi app không quan sát kết quả.

**4. “submit có Future nghĩa là task đã chạy xong.”** Sai: Future có thể đang pending, trong queue, đã lỗi hoặc bị hủy.

**5. “try/catch quanh submit bắt được IllegalStateException từ worker.”** Không, nếu failure nằm trong task đã được nhận; cần đọc `ExecutionException.getCause()`.

**6. “afterExecute(..., null) nghĩa là thành công.”** Sai với `FutureTask` vì nó có thể giữ lỗi mà không ném ra ngoài `run()`.

**7. “TaskDecorator catch(Exception) bắt được mọi lỗi submit.”** Sai khi wrapper FutureTask đã lưu exception trước đó.

**8. “Future.isDone() là thành công.”** Sai: isDone true với cả normal, exceptional và cancelled completion.

**9. “get(timeout) timeout thì task bị hủy.”** Sai: timeout chỉ chấm dứt việc chờ nếu không chủ động cancel hoặc có cơ chế deadline.

**10. “@Async void sẽ ném lỗi về controller.”** Sai trong proxy async path; Spring gọi `AsyncUncaughtExceptionHandler`.

**11. “Future.get và CompletableFuture.join giống nhau.”** Sai về exception class checked/unchecked.

**12. “Đổi execute thành submit là đủ để giám sát toàn bộ lỗi.”** Sai nếu không giữ/đọc Future và không xử lý lỗi rejection.

**13. “CallerRunsPolicy chỉ giúp hiệu năng, không ảnh hưởng exception.”** Sai: với Runnable thô, task có thể ném ngay trên caller; với FutureTask vẫn lưu lỗi.

**14. “Mọi exception đều nên retry.”** Sai: phân loại lỗi không hợp lệ, lỗi tạm thời, rejection, cancel; retry phải có backoff/idempotency, tránh khuếch đại quá tải.

## 19. Câu hỏi tự kiểm tra

**Câu 1:** `pool.submit(() -> { throw new IllegalStateException("x"); })` trả Future. Khi nào caller biết lỗi?

**Đáp án:** khi gọi `future.get()` (hoặc observer tương đương); với JDK implementation thông dụng, `get` ném `ExecutionException`, cause là `IllegalStateException`.

**Câu 2:** `pool.execute(new FutureTask<>(callable))` có chắc đi qua `UncaughtExceptionHandler` nếu callable lỗi?

**Đáp án:** không. FutureTask lưu exception và có thể kết thúc `run()` bình thường; vẫn cần đọc `FutureTask.get()`.

**Câu 3:** Pool shutdown trước `submit`, caller bắt `RejectedExecutionException`. Đây là lỗi logic bên trong task không?

**Đáp án:** không, đây là lỗi nộp việc. Task không được nhận nên không có Future trả về thành công.

**Câu 4:** Pool đầy với `CallerRunsPolicy`. Vì sao `execute` của một Runnable thô có thể ném ngay, còn `submit` của logic tương đương trả Future lỗi?

**Đáp án:** CallerRunsPolicy chạy `Runnable.run()` ngay trên caller; nhưng trong đường submit, Runnable chạy là FutureTask wrapper có cơ chế ghi exception.

**Câu 5:** Phương thức `@Async public void send()` lỗi. Caller có thể gọi `get()` không?

**Đáp án:** không, vì method trả `void`. Cần `AsyncUncaughtExceptionHandler` hoặc đổi thiết kế API sang `Future/CompletableFuture` nếu caller cần biết kết quả.

**Câu 6:** Vì sao `Future.isDone() == true` không có nghĩa task thành công?

**Đáp án:** trạng thái done gồm cả thành công, thất bại và hủy; cần `get()`/completion mechanism để phân loại.

## 20. Checklist trước khi áp dụng

- [ ] Biết implementation executor, nơi task chạy, có thể caller-runs/synchronous không.
- [ ] Phân biệt exception do task thực thi và exception xảy ra ngay khi nộp việc.
- [ ] Với `execute`, có cơ chế quan sát failure và quản lý task ID nếu nghiệp vụ cần.
- [ ] Với `submit`, có owner rõ ràng của `Future` và nơi đọc/quan sát `get()`.
- [ ] Không dựa duy nhất vào `afterExecute` `Throwable` hoặc `TaskDecorator.catch` để kết luận submit không có lỗi.
- [ ] Bắt `ExecutionException` rồi giữ cause gốc; phân biệt timeout, cancel và interrupt.
- [ ] Không để `get()` chờ vô hạn nếu caller có deadline.
- [ ] Có phản ứng khi pool reject, không retry vô hạn trên request thread.
- [ ] Với `@Async void`, đã cấu hình exception handler; với Future/CompletableFuture có consumer/observer.
- [ ] Có chính sách logging/tracing an toàn, không tạo log trùng.
- [ ] Có cơ chế lưu job bền vững nếu không được mất task qua crash/restart.
- [ ] Đã kiểm thử cả lỗi thực thi, lỗi nộp, cancellation, shutdown và load-saturation.

## 21. Tóm tắt

**`execute(Runnable)`** trả `void`. Với task thô chạy trên worker của `ThreadPoolExecutor`, exception không được bắt có thể tới worker error/uncaught handling, chứ không tự trở lại caller. Tuy nhiên, executor đồng bộ, `CallerRunsPolicy` hoặc rejection tại submission có thể tạo exception ngay ở caller.

**`submit(...)`** trả `Future`. Với triển khai thông dụng, task được bọc bởi `FutureTask`; lỗi task được lưu và đưa tới người gọi khi `get()` ném `ExecutionException` chứa cause gốc. **Bỏ Future mà không có observer** là một lỗi thiết kế giám sát.

Trong Spring, `ThreadPoolTaskExecutor` có cùng bài toán, cộng thêm bẫy `TaskDecorator` và hai đường lỗi khác nhau của `@Async void` so với `@Async CompletableFuture`. Hãy thiết kế kênh kết quả, chủ sở hữu xử lý lỗi, deadline/cancel/rejection rõ ràng thay vì suy luận dựa vào tên phương thức.

## Tài liệu tham khảo chính thức

- Java SE 17 — `Executor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html
- Java SE 17 — `ExecutorService` (submit, lifecycle): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — `Future` (get, cancel, isDone): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17 — `FutureTask`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html
- Java SE 17 — `ThreadPoolExecutor` (afterExecute, rejection): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Spring Reference — Task Execution and Scheduling, `@Async` Exception Management: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Javadoc — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Javadoc — `AsyncUncaughtExceptionHandler`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html
