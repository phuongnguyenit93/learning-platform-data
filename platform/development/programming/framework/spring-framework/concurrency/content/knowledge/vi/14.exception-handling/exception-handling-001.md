# Ngoại lệ xảy ra khi gửi tác vụ khác với ngoại lệ trong lúc chạy

Trong Spring Framework, một lời gọi `@Async` hoặc `TaskExecutor.execute(...)` có thể thất bại ở **hai thời điểm có ý nghĩa rất khác nhau**:

1. **Khi gửi tác vụ (submission/admission):** executor không thể hoặc không muốn nhận công việc, chẳng hạn pool đã shutdown hoặc cả worker và queue đều bão hòa. Lỗi xảy ra trên đường gọi gửi tác vụ và thường có thể được phía caller phát hiện ngay.
2. **Trong lúc chạy (execution):** executor đã chấp nhận công việc, một worker bắt đầu thực hiện, nhưng logic nghiệp vụ ném exception. Cách lỗi được chuyển về phụ thuộc API: `Future`, `CompletableFuture`, `@Async void` hay `execute(Runnable)` trực tiếp.

Phân biệt đúng hai nhóm lỗi quyết định cách đặt `try/catch`, trả HTTP status, ghi metrics, cấu hình exception handler và lựa chọn retry. **Không phải cứ “đã có executor” là exception sẽ được gửi lại thread caller**, cũng không phải mọi lỗi xuất hiện gần `execute(...)` đều là lỗi nghiệp vụ.

Bài học thuộc nhóm **Xử lý ngoại lệ** trong module **Spring Framework - concurrency**. Các đoạn mã tích hợp sử dụng Spring Framework 6.x, Java 17+; các chương trình Java độc lập phía dưới có thể biên dịch và chạy ngay bằng JDK 17.

## 1. Hai giai đoạn khác nhau: nhận việc và thực thi

Một chu trình thông thường:

~~~text
HTTP / service caller                TaskExecutor / queue                 Worker
          |                                   |                               |
          |---- execute / submit(task) ------>|                               |
          |                                   |--- thử nhận task ------------>|
          |                                   |                               |
          |       +---------------------------+                               |
          |       | REJECT: hết capacity, shutdown, policy                     |
          |<------X  exception khi gửi, task chưa được nhận                    |
          |                                                                       |
          |<------ accepted / Future ---------|                                  |
          |                                   |-- chờ worker ----------------->|
          |                                   |                           task.run()
          |                                   |                              |
          |                                   |                     +--------+--------+
          |                                   |                     |                 |
          |                                   |                   success           throw
          |                                   |                     |                 |
          |                                   |                 completed       execution failure
          |                                   |                                       |
          |                                   |                         Future / handler / log
~~~

Sơ đồ mô tả tình huống có thread pool bất đồng bộ và policy từ chối bằng exception; các implementation đồng bộ và chính sách `CallerRunsPolicy` có thể có thứ tự khác, được phân tích ở phần sau.

| Đặc điểm | Ngoại lệ lúc gửi tác vụ | Ngoại lệ trong lúc chạy |
| --- | --- | --- |
| Thời điểm | Trước khi executor chấp nhận task hoặc trong chính lời gọi submit | Sau khi task đã được chấp nhận và logic thực thi bắt đầu |
| Vấn đề tiêu biểu | Pool quá tải, queue đầy, executor shutdown, không còn khả năng nhận | Dữ liệu sai, lỗi DB/HTTP, parse lỗi, business rule, NPE, timeout I/O |
| Java thường gặp | `RejectedExecutionException` từ `execute`/`submit` | Exception phát sinh trong `Runnable.run()` hoặc `Callable.call()` |
| Spring thường gặp | `TaskRejectedException` từ `TaskExecutor` | Exception trong target method `@Async` |
| Caller thấy thế nào? | Thường ném đồng bộ từ lời gọi submit khi dùng policy từ chối bằng exception | Tùy hợp đồng: `Future.get()`/`join()`, `AsyncUncaughtExceptionHandler`, hoặc worker uncaught handler |
| Công việc có chắc đã chạy? | **Không** nếu bị từ chối trước khi nhận | **Có bắt đầu thực thi** (nhưng không nhất thiết hoàn tất thành công) |
| Cách ứng phó | Điều tiết tải, 503/429 phù hợp, backpressure, pool/queue sizing, kiểm tra shutdown | Logging, phân loại lỗi nghiệp vụ, retry có giới hạn, lưu trạng thái thất bại và quan sát downstream |

Cần lưu ý “ngoại lệ tại lời gọi gửi” và “ngoại lệ của bản thân task” là **hai khái niệm nhân quả**. Thời điểm caller nhận thấy lỗi có thể xảy ra muộn hơn lỗi gốc: ví dụ exception đã ném ở worker từ lâu, nhưng chỉ đến khi caller gọi `Future.get()` mới nhìn thấy `ExecutionException`.

## 2. Submission failure: task không được nhận

### 2.1. Vì sao executor từ chối?

Với `ThreadPoolExecutor`, và thông qua đó là `ThreadPoolTaskExecutor` của Spring, trình tự nhận việc cơ bản là:

1. Nếu số worker dưới `corePoolSize`, thử tạo worker mới.
2. Khi đã đạt core, thử đưa task vào queue.
3. Nếu queue không nhận được, thử tăng số worker tới `maxPoolSize`.
4. Khi không còn khả năng nhận, áp dụng `RejectedExecutionHandler`.

Ngoài trường hợp bão hòa, **executor đã shutdown cũng có thể từ chối task mới**, dù CPU rảnh hoặc queue chưa đầy. Không nhìn thấy queue đầy không đủ để loại trừ nguyên nhân rejection.

Ví dụ với `corePoolSize=1`, `maxPoolSize=1`, queueCapacity=1:

~~~text
Task A: worker #1 đang chạy và bị chặn
Task B: được nhận và nằm trong queue duy nhất
Task C: không có worker trống, queue đã đầy
        -> AbortPolicy -> rejected khi submit
~~~

Khi dùng Java `ThreadPoolExecutor.AbortPolicy`, lời gọi `execute(C)` ném `RejectedExecutionException`. Trong Spring `ThreadPoolTaskExecutor`, hợp đồng `TaskExecutor` thường bộc lộ trường hợp tương ứng dưới dạng `TaskRejectedException`, một subtype của `RejectedExecutionException`.

### 2.2. Bắt lỗi ở điểm gửi tác vụ

Đoạn Java minh họa:

~~~java
try {
    executor.execute(task);
    System.out.println("Submission accepted");
} catch (RejectedExecutionException ex) {
    System.err.println("Executor did not accept the task");
}
~~~

Đây là **mã rút gọn**, giả định `executor` và `task` đã được khai báo. Với Spring có bean kiểu `ThreadPoolTaskExecutor`, thường bắt `TaskRejectedException` ở ranh giới gửi để quyết định trả lỗi, giảm tải hoặc ghi lại công việc ở một hàng đợi bền vững nếu nghiệp vụ cần.

Quan trọng: một lời gọi `execute(...)` trả bình thường chỉ cho biết task đã được xử lý theo **policy** của executor, không bảo đảm task sẽ chạy thành công. Một policy có thể chạy task trên caller hoặc âm thầm bỏ task. Do đó “không có exception khi gửi” **không phải** xác nhận task đã được lưu bền vững hay đã hoàn tất.

### 2.3. Không phải policy nào cũng ném exception

| Chính sách `ThreadPoolExecutor` | Khi không thể nhận thêm | Hệ quả với caller |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` | Caller thường phát hiện ngay; dễ phân biệt overload |
| `CallerRunsPolicy` | Nếu executor chưa shutdown, caller **tự chạy** `Runnable` | Lời gửi có thể bị chặn và exception task có thể xảy ra trên caller |
| `DiscardPolicy` | Bỏ task, thường không ném từ policy | Không có exception không có nghĩa đã xử lý |
| `DiscardOldestPolicy` | Bỏ task đứng đầu queue rồi thử tiếp nhận task mới | Có thể làm mất task khác và phá kỳ vọng về thứ tự/delivery |

Các policy này đều có rủi ro nghiệp vụ; cần chọn theo yêu cầu chịu tải, khả năng mất việc và cách ghi nhận kết quả. Ví dụ một yêu cầu thanh toán không nên dùng `DiscardPolicy` rồi chỉ dựa vào việc method gửi đã trả về.

### 2.4. Ngoại lệ đến từ caller không nhất thiết là rejection

Nếu caller tự parse tham số trước khi submit và ném `IllegalArgumentException`, lỗi đó thuộc **validation tại biên caller**, không phải executor từ chối. Nếu thiếu bean executor hoặc cấu hình proxy sai, lời gọi có thể thất bại trước bước tiếp nhận; không được gộp mọi exception đồng bộ thành `TaskRejectedException`.

Muốn phân loại chính xác, đo và log **nguyên nhân, loại exception, bean executor và giai đoạn lỗi**, thay vì chỉ ghi thông báo “async failed”.

## 3. Execution failure: task đã chạy rồi ném lỗi

Sau khi executor nhận task, worker thực thi logic. Ví dụ:

~~~java
Runnable task = () -> {
    throw new IllegalStateException("Business processing failed");
};
~~~

Đây là một `Runnable` minh họa. Lỗi ở đây là **lỗi thực thi bên trong task**. Khi dùng thread pool, nó thường không được ném ngược qua stack của method `execute(task)` đã trả về trước đó.

Điều người gọi quan sát được phụ thuộc API:

- **`Executor.execute(Runnable)` trực tiếp:** một exception chưa bắt trong `run()` thường đi qua cơ chế uncaught exception của worker thread; nó không tạo một Future kết quả cho caller. Với `ThreadPoolExecutor`, worker gặp lỗi runtime có thể kết thúc đột ngột và pool quản lý việc tạo worker thay thế theo nhu cầu.
- **`ExecutorService.submit(Runnable/Callable)`:** task thường được bọc trong `FutureTask`; exception trong worker được giữ thành trạng thái thất bại của Future. Caller gọi `get()` sẽ nhận `ExecutionException`, có thể kiểm tra `getCause()` để thấy nguyên nhân gốc.
- **`CompletableFuture`:** khi task hoàn tất thất bại, có thể dùng `whenComplete`/`handle`/`exceptionally` để xử lý. `join()` thường bộc lộ lỗi qua `CompletionException`; `get()` thường qua `ExecutionException`.
- **Spring `@Async` trả `void`:** không có Future trả về, nên Spring dùng `AsyncUncaughtExceptionHandler` cho exception chưa được bắt từ target method.
- **Spring `@Async` trả `Future`/`CompletableFuture<T>`:** exception thực thi được truyền theo Future để caller theo dõi; `AsyncUncaughtExceptionHandler` không phải kênh chính cho những trường hợp này.

**Không đồng nhất “exception trong worker” với “exception đã được caller xử lý”**. Nếu không ai gọi `Future.get()`, gắn completion callback hoặc instrument task, lỗi của một task `submit` có thể không được quan sát kịp thời.

## 4. Java 17 — chứng minh rejection trước khi chạy và lỗi bên trong worker

Chương trình dưới đây tạo tình huống có thể kiểm chứng **mà không dựa vào `Thread.sleep`**. Pool chỉ có một worker và queue sức chứa một task:

- Task A được chạy và giữ worker bằng latch.
- Task B được submit thành công vào queue nhưng khi chạy sẽ ném lỗi nghiệp vụ.
- Task C bị từ chối **ngay tại lời gọi gửi** vì worker và queue đang bận.
- Sau khi mở latch, B mới được chạy và Future của B hoàn tất thất bại.

Tạo tệp `SubmitVsRunErrorDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class SubmitVsRunErrorDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 10, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First worker did not start");
            }

            Future<?> second = pool.submit(() -> {
                throw new IllegalStateException("business failure");
            });
            System.out.println("1. Second task accepted");

            try {
                pool.execute(() -> System.out.println("never run"));
                System.out.println("unexpected acceptance");
            } catch (RejectedExecutionException ex) {
                System.out.println("2. Third task rejected during submission");
            }

            release.countDown();
            try {
                second.get(5, TimeUnit.SECONDS);
                System.out.println("unexpected success");
            } catch (ExecutionException ex) {
                System.out.println("3. Second task failed while running: "
                        + ex.getCause().getClass().getSimpleName());
            }
            System.out.println("4. Second task done=" + second.isDone());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy với Java 17 trở lên:

~~~bash
javac --release 17 SubmitVsRunErrorDemo.java
java SubmitVsRunErrorDemo
~~~

Stdout đã được xác minh bằng JDK khi biên dịch với `--release 17`:

~~~text
1. Second task accepted
2. Third task rejected during submission
3. Second task failed while running: IllegalStateException
4. Second task done=true
~~~

**Giải thích vì sao kết quả xác định:**

1. `started.await(...)` chờ tới khi A thực sự bắt đầu. A sẽ không rời worker trước khi `release.countDown()`.
2. Khi B được `submit`, queue còn đúng một chỗ và được điền bởi B; Future đã được trả về trước khi B có thể chạy.
3. C xuất hiện khi A còn giữ worker và B còn chiếm queue; `AbortPolicy` ném ngay `RejectedExecutionException`. C **không chạy**, không có Future và không có exception nghiệp vụ từ C.
4. `release.countDown()` cho A thoát; worker lấy B. B ném `IllegalStateException` trong worker, được giữ trong Future.
5. `second.get(...)` ném `ExecutionException` trên caller **lúc đọc kết quả**; `getCause()` là `IllegalStateException` gốc. `isDone()==true` không có nghĩa B thành công; trạng thái thất bại cũng được coi là hoàn tất.

Ví dụ không giả vờ đo thời gian cụ thể. Đối với code production, cần quan tâm thêm timeout, admission control, logging và shutdown có kiểm soát.

## 5. Java 17 — vì sao execute trực tiếp khác submit khi task ném lỗi?

Một điểm tinh tế: **`execute(...)` không nhất thiết tạo `FutureTask`**, còn `submit(...)` thường bọc task để lưu kết quả và exception.

Với `ThreadPoolExecutor.execute(rawRunnable)`, exception chưa bắt có thể đi tới `Thread.UncaughtExceptionHandler` của worker. Với `ExecutorService.submit(rawRunnable)`, FutureTask ghi nhận lỗi và `Future.get()` cung cấp đường đọc lỗi cho caller; uncaught handler của worker thường **không được gọi vì FutureTask đã bắt exception**.

Chương trình sau minh họa phía `execute` trực tiếp, không cần Spring. Tạo tệp `ExecuteUncaughtDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

public class ExecuteUncaughtDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch handled = new CountDownLatch(1);
        ThreadFactory factory = task -> {
            Thread worker = new Thread(task, "worker-example");
            worker.setUncaughtExceptionHandler((thread, error) -> {
                System.out.println("1. Uncaught on " + thread.getName()
                        + ": " + error.getClass().getSimpleName());
                handled.countDown();
            });
            return worker;
        };
        ExecutorService pool = Executors.newSingleThreadExecutor(factory);
        try {
            pool.execute(() -> {
                throw new IllegalStateException("worker crash");
            });
            if (!handled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Handler was not called");
            }
            System.out.println("2. Main observed uncaught handler");
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ExecuteUncaughtDemo.java
java ExecuteUncaughtDemo
~~~

Stdout đã xác minh:

~~~text
1. Uncaught on worker-example: IllegalStateException
2. Main observed uncaught handler
~~~

Hạn chế cần hiểu: đây là hành vi của **Java ExecutorService với `execute(rawRunnable)`**. Spring `@Async` có interceptor và cơ chế xử lý exception riêng, vì vậy không được suy ra rằng mọi lỗi `@Async void` chắc chắn đến `Thread.UncaughtExceptionHandler` của worker.

Việc đếm lỗi chỉ bằng uncaught handler cũng không đủ nếu hệ thống dùng `submit`, `CompletableFuture` hoặc các wrapper bắt exception. Quan sát kết quả phải phù hợp với API thật sự được dùng.

## 6. Spring Framework: một executor, hai kênh lỗi rõ ràng

Phần này là mã **tích hợp trong Spring Framework 6.x / Java 17+**; cần Spring Context, Spring AOP, component scanning và `@EnableAsync`. Mỗi `public class` nằm trong tệp trùng tên ở package `example.concurrency`. Những đoạn sau **không chạy với `javac` đơn lẻ nếu không có dependency Spring**.

### 6.1. Cấu hình ThreadPoolTaskExecutor và handler cho @Async void

Tệp `AsyncErrorConfiguration.java`:

~~~java
package example.concurrency;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncErrorConfiguration implements AsyncConfigurer {

    @Bean("jobExecutor")
    public ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("job-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, args) ->
                System.err.println("Async void execution failed: "
                        + method.getName() + " / "
                        + exception.getClass().getSimpleName());
    }
}
~~~

Ý nghĩa:

- `jobExecutor` là bean executor duy nhất được ví dụ chọn qua `@Async("jobExecutor")`. `@EnableAsync` kích hoạt cách Spring intercept lời gọi qua proxy.
- `core=2`, `max=4`, `queueCapacity=16` chỉ là giá trị demo, không phải cấu hình production khuyến nghị chung.
- `AbortPolicy` giúp pool bão hòa dẫn tới tín hiệu từ chối rõ ràng ở lời submit; với Spring `ThreadPoolTaskExecutor`, thường thấy `TaskRejectedException`.
- `AsyncConfigurer.getAsyncUncaughtExceptionHandler()` được Spring dùng cho exception chưa được xử lý từ **target method `@Async void`**. Ví dụ chỉ in tên method/loại lỗi; trong sản phẩm nên dùng structured logging, metrics, correlation id và không ghi lộ các tham số nhạy cảm.

Spring tự quản lý lifecycle/initialization của bean executor. Không cần gọi `initialize()` trong factory method nếu bean được tạo qua ApplicationContext theo cơ chế chuẩn.

### 6.2. Worker có hai loại phương thức async

Tệp `JobWorker.java`:

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class JobWorker {

    @Async("jobExecutor")
    public CompletableFuture<String> generate(String jobId) {
        if (jobId.isBlank()) {
            throw new IllegalArgumentException("jobId is blank");
        }
        if (jobId.equals("fail")) {
            throw new IllegalStateException("generate failed");
        }
        return CompletableFuture.completedFuture("generated:" + jobId);
    }

    @Async("jobExecutor")
    public void notifyBestEffort(String id) {
        if (id.equals("fail")) {
            throw new IllegalStateException("notification failed");
        }
        System.out.println("Notified: " + id);
    }
}
~~~

Với `@Async("jobExecutor")` hoạt động đúng:

- Gọi `generate("ok")`: caller nhận `CompletableFuture<String>`; task có thể chờ queue trước khi chạy. Nếu thành công, Future hoàn tất với `"generated:ok"`.
- Gọi `generate("fail")`: nếu submit thành công, `IllegalStateException` xảy ra **ở worker**. Future của caller hoàn tất thất bại; caller xem được thông qua `whenComplete(...)`, `join()` hoặc `get()`.
- Gọi `notifyBestEffort("fail")`: nếu submit thành công, lỗi xuất hiện trong target method `@Async void`, không có Future trả về nên Spring gửi lỗi chưa được bắt tới `AsyncUncaughtExceptionHandler`.
- Với **bất kỳ** method nào, nếu executor reject ngay trong bước submit, caller có thể nhận `TaskRejectedException` **trước khi có kết quả async**; handler dành cho lỗi thực thi của `void` không thay thế xử lý rejection.

Ví dụ dùng `String.isBlank()` (Java 11+) nên tương thích Java 17. Đây là logic minh họa; nếu cần validate tham số **trước khi submit**, nên kiểm tra ở biên controller/service caller để trả lỗi 4xx đồng bộ thay vì đẩy lỗi dữ liệu lên worker.

### 6.3. Caller bắt lỗi gửi, Future nhận lỗi chạy

Đoạn trong một bean khác đã inject `JobWorker worker`:

~~~java
try {
    CompletableFuture<String> future = worker.generate("fail");

    future.whenComplete((value, error) -> {
        if (error != null) {
            System.err.println("Execution failed: " + error);
        } else {
            System.out.println("Success: " + value);
        }
    });
} catch (org.springframework.core.task.TaskRejectedException ex) {
    System.err.println("Submission rejected: executor is not accepting work");
}
~~~

Đây là **mã caller minh họa**, không có stdout cố định vì việc chạy phụ thuộc executor và tải. Hai nhánh quan sát **không giống nhau**:

- `catch (TaskRejectedException)` bắt tình huống **không gửi được công việc** theo policy từ chối bằng exception.
- `whenComplete((value, error) -> ...)` quan sát **kết quả thực thi** của task đã được nhận, có thể đã bắt đầu hoặc còn chờ khi caller đăng ký callback.

Với `CompletableFuture`, `join()` thường ném `CompletionException` khi task lỗi, còn `get()` ném `ExecutionException` (hoặc các exception liên quan cancellation/interruption). Cả hai có thể bọc cause là exception nghiệp vụ thật; đừng dựa vào chuỗi thông báo bên ngoài để phân loại lỗi. Nếu caller dùng `join()` ngay sau khi submit, nó sẽ chờ task và không còn hoàn toàn không chặn.

### 6.4. Caller của @Async void xử lý hai nguồn lỗi thế nào?

Đoạn trong bean khác:

~~~java
try {
    worker.notifyBestEffort("fail");
    // Trả về bình thường chỉ có nghĩa lời gọi qua proxy đã đi qua
    // đường submit theo chính sách executor hiện hành.
} catch (org.springframework.core.task.TaskRejectedException ex) {
    System.err.println("Submission rejected");
}
~~~

Nếu task được nhận rồi ném `IllegalStateException` trong worker, `catch` trên không bắt lỗi đó; handler trong `AsyncErrorConfiguration` mới là kênh xử lý lỗi thực thi `@Async void`. Nếu task bị reject, handler đó không có một target exception nào để xử lý vì method chưa chạy.

Với `void`, caller không có handle để biết tác vụ đã hoàn thành hay chưa. Nếu cần acknowledgement về thành công/thất bại, hãy dùng `CompletableFuture<Void>` hoặc cơ chế job id/trạng thái thay vì chỉ thêm `@Async` cho method `void`.

## 7. Bảng phân biệt đường đi của exception theo API

| API / hợp đồng | Lỗi không nhận task | Lỗi target method đã chạy | Ai thường nhìn thấy? |
| --- | --- | --- | --- |
| Java `ThreadPoolExecutor.execute(Runnable)` + AbortPolicy | `RejectedExecutionException` ở `execute` | Uncaught trên worker nếu `Runnable` không bắt | Caller cho rejection; worker uncaught handler/log cho lỗi chạy |
| Java `ExecutorService.submit(Callable)` | `RejectedExecutionException` ở `submit` | Future hoàn tất thất bại; `get()` ném `ExecutionException` | Caller lúc gọi `get()`; metrics/callback nếu instrument |
| Java `CompletableFuture.runAsync(..., executor)` | Có thể ném `RejectedExecutionException` khi yêu cầu không được nhận | CompletableFuture hoàn tất thất bại | Caller khi submit; callback/`join()` cho lỗi chạy |
| Spring `TaskExecutor.execute(Runnable)` + AbortPolicy | `TaskRejectedException` | Phụ thuộc loại executor/wrapper và uncaught handler | Caller đối với rejection; worker/instrumentation cho lỗi chạy |
| Spring `@Async void` | `TaskRejectedException` tại proxy submit | `AsyncUncaughtExceptionHandler` | Caller cho lỗi gửi; handler cho lỗi chạy |
| Spring `@Async CompletableFuture<T>` | `TaskRejectedException` tại proxy submit | Future hoàn tất thất bại | Caller cho lỗi gửi; Future callback/`get()`/`join()` cho lỗi chạy |

Bảng lấy trường hợp **executor bất đồng bộ với chính sách AbortPolicy hoặc tương đương** làm mặc định để so sánh. Cần điều chỉnh cách diễn giải khi dùng `CallerRunsPolicy`, `DiscardPolicy`, `SyncTaskExecutor` hoặc wrapper tùy biến. Không biến bảng thành một kết luận rằng exception của task **không bao giờ** ném trên caller trong mọi implementation.

## 8. Trường hợp ngoại lệ vượt ranh giới giai đoạn

### 8.1. CallerRunsPolicy có thể chạy target ngay trên caller

Khi pool quá tải và policy là `CallerRunsPolicy`, lời `execute(rawRunnable)` có thể trực tiếp gọi `run()` trên caller. Nếu `run()` ném exception chưa bắt, exception đó có thể xuất hiện ngay **trong lời `execute(...)`**, dù nguyên nhân thuộc **logic thực thi**, không phải executor reject bằng AbortPolicy.

Ngược lại, nếu tác vụ gửi bằng `submit(...)` được bọc trong `FutureTask`, lỗi vẫn có thể được lưu trong Future, ngay cả khi `CallerRunsPolicy` khiến nó thực thi đồng bộ ở caller. **Kiểu wrapper và policy quan trọng hơn cách suy luận “nó ném sớm nên chắc là rejection”.**

### 8.2. SyncTaskExecutor không chuyển sang worker khác

Spring `SyncTaskExecutor` chạy `Runnable` trên thread gọi. Nếu method ném exception, caller có thể nhìn thấy ngay. Đây không phải ngoại lệ “bị trả về từ background thread”. Khi test dùng executor đồng bộ còn production dùng thread pool, kết quả của test về timing và exception propagation có thể khác. Nên có integration test xác nhận executor thật.

### 8.3. Self-invocation bỏ qua proxy @Async

Trong proxy mode mặc định, một method của bean gọi `this.otherAsyncMethod()` bên trong chính bean thường không đi qua interceptor `@Async`. Method có thể chạy **đồng bộ** trên caller và ném exception ngay, khiến người học nhầm rằng lỗi worker tự truyền về caller.

Kiểm tra `@EnableAsync`, bean do Spring quản lý và việc lời gọi đi qua proxy trước khi kết luận về hành vi lỗi. Thực tế thường tách method async sang bean khác để giữ đường gọi rõ ràng.

### 8.4. Exception bị bắt bên trong worker

Nếu method đã tự bắt exception rồi trả về bình thường, Future có thể hoàn tất thành công hoặc handler không được gọi, dù một bước nghiệp vụ bên trong đã thất bại. Đây không phải “Spring làm mất exception”; nó là hệ quả của việc code đã **nuốt lỗi**.

Chỉ catch khi có chiến lược xử lý thật: trả kết quả biểu diễn lỗi, cập nhật trạng thái, retry có giới hạn, hoặc ném lại để hoàn tất Future thất bại/đưa qua handler. Không dùng `catch (Exception ignored)` cho công việc bắt buộc.

## 9. Từ exception kỹ thuật đến HTTP response và SLA

Giả sử một endpoint gửi yêu cầu tạo báo cáo nền:

| Tình huống | Phản hồi hợp lý ở biên API | Nghĩa của phản hồi |
| --- | --- | --- |
| Dữ liệu đầu vào sai trước khi submit | `400 Bad Request` khi phù hợp | Request không hợp lệ; không gửi task |
| Executor bão hòa, từ chối nhận task | `503 Service Unavailable` hoặc `429 Too Many Requests` tùy hợp đồng | Hệ thống không nhận công việc; caller nên biết để điều tiết/retry |
| Task đã được nhận vào executor in-memory | Có thể `202 Accepted` theo hợp đồng API | Đã được submit; **chưa** phải bảo đảm thành công hoặc bền vững |
| Task chạy rồi lỗi sau khi HTTP response đã trả | Không thể đổi status của response trước đó | Cần kênh job status, completion event, metrics/log/alert |
| Công việc bắt buộc lưu bền vững | Xác nhận theo việc lưu thành công vào job store/queue | Không đồng nhất `ThreadPoolTaskExecutor.execute` với durable acceptance |

`503` và `429` không phải mapping bắt buộc của Spring cho mọi `TaskRejectedException`; đó là **quyết định thiết kế API** tùy nguyên nhân và chính sách điều tiết. Việc retry từ client cần backoff/jitter và idempotency để không tạo bão yêu cầu mới.

Với `@Async CompletableFuture<T>`, caller có thể gắn callback hoặc lưu job id. Nếu endpoint đã trả `202`, lỗi sau đó nên cập nhật trạng thái/ghi cảnh báo hoặc gửi thông báo qua kênh khác; không giả định completion lỗi sẽ tự chuyển response thành 500.

## 10. Retry khác nhau theo giai đoạn

**Khi submission bị từ chối:**

- Kiểm tra nguyên nhân saturation hay shutdown. Nếu node đang shutdown, retry cùng node ngay có thể vô ích.
- Chọn backpressure, bounded queue, rate limiting, giới hạn concurrency và cân đối năng lực.
- Nếu nghiệp vụ cho phép retry, đặt ngân sách retry, timeout/deadline, backoff và jitter; tránh vòng lặp `while(true) submit()` ngay trên request thread.
- Với công việc không được mất, cần ghi task vào hàng đợi bền vững trước hoặc trong giao thức tiếp nhận có ACK; một queue in-memory không đủ.

**Khi task đã chạy rồi lỗi:**

- Phân loại lỗi tạm thời (kết nối, quá tải downstream) và lỗi cố định (input không hợp lệ, điều kiện nghiệp vụ không thỏa).
- Retry phải dựa vào **idempotency**: một lần chạy có thể đã ghi dữ liệu một phần trước khi ném exception. Không mặc định chạy lại là không tạo side effect trùng.
- Không retry lỗi validation vĩnh viễn vô hạn.
- Nếu Future hoàn tất thất bại, quyết định trạng thái job, số lần thử và cách báo lỗi tới caller. Với `@Async void`, handler có thể phát cảnh báo nhưng tự nó không có logic retry.
- Có timeout độc lập cho HTTP/JDBC và deadline end-to-end, không chỉ cho `Future.get(timeout)`.

Ngoài ra, cancellation/interruption là nhánh riêng. `Future.cancel(true)` có thể yêu cầu ngắt, nhưng không bảo đảm task đang chạy ngừng ngay hoặc rollback thao tác đã làm. Bị hủy trước khi thực thi cũng không tương đương task chạy rồi lỗi nghiệp vụ.

## 11. Logging và metrics phải phân biệt lỗi submit/lỗi run

Khi theo dõi hệ thống, ghi nhận các loại sự kiện riêng thay vì một counter “async failed” mơ hồ:

| Sự kiện | Mốc ghi | Gợi ý thông tin |
| --- | --- | --- |
| `submitted_total` | Lúc caller bắt đầu gửi | Tên workload/loại task, correlation id |
| `accepted_total` | Sau khi executor nhận thành công theo policy có xác nhận | Executor, kích thước/giới hạn queue, trạng thái thời điểm nhận |
| `rejected_total` | Khi submit thất bại | Executor name, pool size, active count, queue depth, shutdown flag |
| `started_total` | Đầu worker callback | Job id, wait duration từ lúc submit |
| `completed_total` | Khi task hoàn tất thành công | Runtime, workload |
| `execution_failed_total` | Khi task đã bắt đầu và lỗi | Nhóm exception, downstream, retry count |
| `cancelled_total` | Khi được hủy | Task đang queue hay đang chạy, kết quả yêu cầu hủy |

Đây là **tên metric gợi ý**, không phải những metric mà Spring tự sinh với đúng tên đó. Instrumentation phải đúng vị trí: exception của `FutureTask` có thể được lưu trong Future, nên chỉ dựa vào `Thread.UncaughtExceptionHandler` hoặc `TaskDecorator` catch quanh `callback.run()` có thể **bỏ sót lỗi thực thi**.

Với một `FutureTask`, wrapper có thể hoàn tất bình thường ở mức `run()` bên ngoài trong khi Future đã ở trạng thái thất bại. Tùy loại executor, có thể quan sát `afterExecute(...)`, completion callback hoặc instrumentation ở chính ranh giới nghiệp vụ. Tránh tự `get()` chặn worker trong mọi callback nếu có thể gây deadlock/starvation.

Không log toàn bộ payload hoặc exception arguments có chứa token/dữ liệu nhạy cảm. Dùng job id và trace id để nối các giai đoạn.

## 12. Kiểm thử hai lỗi mà không dựa vào timing may rủi

Một bài integration test tốt có ít nhất hai ca **khác nhau**:

### 12.1. Case A: rejection ngay tại lời gửi

- Dùng executor core=max=1, queueCapacity=1, `AbortPolicy`.
- Dùng `CountDownLatch` giữ worker A.
- Gửi B vào queue, sau đó gửi C.
- Xác nhận C bị `TaskRejectedException` (trong Spring) hoặc `RejectedExecutionException` (Java) khi gọi submit.
- Xác nhận logic task C **không hề được gọi**.
- Mở latch và shutdown pool trong `finally` để test không treo.

Không chỉ thử gửi hàng nghìn task với `Thread.sleep` rồi đoán có rejection: test như vậy dễ chập chờn theo máy CI.

### 12.2. Case B: lỗi sau khi task đã được chấp nhận

- Submit một công việc được thiết kế sẽ ném `IllegalStateException` ở worker.
- Với Future, xác nhận `get()` ném `ExecutionException` với cause đúng; với `CompletableFuture`, xác nhận callback nhận lỗi hoặc Future hoàn tất thất bại.
- Với `@Async void`, inject một `AsyncUncaughtExceptionHandler` testable và xác nhận handler được gọi với method/exception đúng.
- Xác nhận không nhầm lỗi worker với `TaskRejectedException`.
- Gọi phương thức qua Spring proxy, không `new Service()` và không self-invocation, để test thật sự đi qua `@Async`.

### 12.3. Case C: chính sách đặc biệt và lifecycle

Thử thêm `CallerRunsPolicy`, `SyncTaskExecutor` và shutdown khi có yêu cầu tương ứng. Chúng có thể cho behavior khác về thread và thời điểm exception xuất hiện. Xác minh test không dựa vào giả định “mọi task đều ở background”.

## 13. Những nhầm lẫn thường gặp

**“`try/catch` quanh `submit(...)` sẽ bắt hết exception bên trong task.”** Không. Nó thường bắt rejection/lỗi lúc gửi; exception execution của task được lưu vào Future và được nhìn thấy qua `get()`/completion callback.

**“`Future.isDone() == true` tức là thành công.”** Không. Future có thể đã hoàn thành bằng lỗi hoặc cancellation.

**“`@Async void` chạy lỗi sẽ quay về controller.”** Không theo đường thông thường khi đã được submit bất đồng bộ. Spring dùng `AsyncUncaughtExceptionHandler`; caller có thể đã trả response.

**“Mọi exception xuất hiện trong `execute(...)` đều là rejection.”** Không. `CallerRunsPolicy` hoặc executor đồng bộ có thể chạy logic task ngay trên caller, và logic đó có thể ném exception.

**“`@Async CompletableFuture` có nghĩa submission không thể fail.”** Không. Executor có thể từ chối trước khi Future được trả cho caller.

**“Không thấy uncaught exception log nghĩa là task submit không lỗi.”** Không. `submit` thường bọc exception vào `FutureTask`; handler của worker có thể không được gọi.

**“Pool còn CPU rảnh thì không bao giờ reject.”** Không. Pool có thể shutdown, workers bị chặn, queue đầy hoặc giới hạn max bị chạm.

**“Đã trả 202 thì task chắc chắn hoàn tất.”** Không. Queue in-memory có thể mất khi crash, task có thể lỗi và response đã trả không đổi.

**“Chỉ thêm retry cho mọi loại exception là an toàn.”** Không. Retry lỗi cố định hoặc side effect không idempotent có thể gây lặp hành động và làm hệ thống quá tải thêm.

## 14. Bài tập tự kiểm tra

**Câu 1.** `ThreadPoolTaskExecutor` đã bão hòa và cấu hình `AbortPolicy`; controller gọi `@Async` method. Exception phát sinh ở đâu và làm gì?

**Đáp án:** có thể nhận `TaskRejectedException` ngay ở lời gọi gửi (trong proxy). Controller cần phản hồi quá tải/giảm tải/điều phối retry, không đợi worker xử lý task chưa được nhận.

**Câu 2.** `ExecutorService.submit(...)` trả `Future`, task được chấp nhận rồi ném `IllegalArgumentException`. `try/catch` quanh lời submit có chắc bắt được lỗi đó không?

**Đáp án:** không. Khi gọi `Future.get()`, caller thường nhận `ExecutionException` có cause là `IllegalArgumentException`.

**Câu 3.** Khi gọi `CompletableFuture.join()` cho Future hoàn tất thất bại, thường gặp wrapper gì?

**Đáp án:** `CompletionException`, với cause thể hiện nguyên nhân thực thi; `get()` thường dùng `ExecutionException`.

**Câu 4.** Một method `@Async void` đã được nhận nhưng lỗi ở worker. Caller có nhận lỗi qua return value không?

**Đáp án:** không. Cần `AsyncUncaughtExceptionHandler`, logging/metrics hoặc kênh trạng thái riêng.

**Câu 5.** Vì sao `CallerRunsPolicy` làm cách phân loại “sớm/muộn” trở nên nguy hiểm?

**Đáp án:** raw `Runnable` có thể được chạy trên caller trong lời `execute(...)`; exception nghiệp vụ sẽ xuất hiện ngay tại phương thức gửi dù bản chất là lỗi thực thi.

**Câu 6.** Vì sao `submit` có thể không kích hoạt uncaught exception handler của worker khi task lỗi?

**Đáp án:** task được bọc bởi `FutureTask`, wrapper giữ exception để caller đọc qua Future.

**Câu 7.** Đã submit thành công task tạo biên lai nhưng JVM crash trước khi worker xử lý. Đây có phải “execution exception” mà Future chắc chắn bắt được không?

**Đáp án:** không. Lỗi crash/loss-of-process nằm ngoài đường báo lỗi thông thường; cần cơ chế tiếp nhận/lưu công việc bền vững.

**Câu 8.** Khi theo dõi chất lượng, nên có một counter `async_failed_total` hay tách loại lỗi?

**Đáp án:** nên tách ít nhất `rejected_total` (không nhận được) và `execution_failed_total` (đã chạy nhưng thất bại); thêm hoàn tất, queue wait và cancel theo yêu cầu.

## 15. Tài liệu tham khảo chính thức

- Spring Framework Reference 6.2 — Task Execution and Scheduling, `@Async`, Exception Management: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework API 6.2 — `ThreadPoolTaskExecutor` và `TaskRejectedException`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework API 6.2 — `@Async`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/Async.html
- Spring Framework API 6.2 — `@EnableAsync` / `AsyncConfigurer`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html
- Oracle Java SE 17 — `ThreadPoolExecutor`, rejection policies: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java SE 17 — `ExecutorService` / `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Oracle Java SE 17 — `ExecutionException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html
