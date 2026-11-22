# CompletableFuture.cancel() không bảo đảm ngắt luồng xử lý

Khi xây dựng tác vụ bất đồng bộ trong Java và Spring Framework, một hiểu nhầm phổ biến là gọi `future.cancel(true)` thì luồng đang thực thi công việc sẽ lập tức bị ngắt. **Điều này không đúng với `java.util.concurrent.CompletableFuture`.** Theo hợp đồng Java SE 17, tham số `mayInterruptIfRunning` của `CompletableFuture.cancel(boolean)` **không có hiệu lực**: implementation này không dùng interruption để kiểm soát quá trình xử lý.

`cancel(true)` chủ yếu chuyển đối tượng `CompletableFuture` sang **trạng thái đã hủy**, khiến bên gọi không còn nhận được kết quả bình thường. Một worker đã bắt đầu có thể vẫn tiếp tục chờ I/O, ghi database hoặc thực hiện side effect **sau khi `future.isCancelled()` đã bằng `true`**. Việc hủy kết quả không đồng nghĩa chấm dứt công việc.

Bài học thuộc nhóm **Hết hạn và hủy** trong **Spring Framework - concurrency**. Nội dung giải thích ngữ nghĩa chuẩn Java 17, so sánh với `FutureTask`, các kiểu timeout, cách áp dụng cho `@Async`, thiết kế hủy hợp tác và ví dụ biên dịch/chạy được.

## 1. Tách trạng thái kết quả khỏi tiến trình xử lý

Có ba thực thể liên quan nhưng khác nhau:

- **Bên gọi (caller):** có thể quyết định không muốn nhận hoặc chờ kết quả nữa.
- **Đối tượng kết quả `CompletableFuture<T>`:** giữ trạng thái pending, thành công, lỗi hoặc hủy; hỗ trợ composition với `CompletionStage`.
- **Công việc thực tế (worker/task):** thao tác trên thread, DB, network hoặc phần mềm khác. Nó chỉ thực sự dừng nếu logic hoặc tài nguyên điều khiển việc đó.

Một CompletableFuture có thể được tạo bằng `new CompletableFuture<>()` và được code khác hoàn tất bằng `complete(value)`, **không liên kết với worker cụ thể**. Vì vậy cancel của đối tượng kết quả không thể biết chắc thread nào cần ngắt.

~~~text
Caller                   CompletableFuture                 Worker
  |                             |                             |
  |--- runAsync(task, pool) ---->|--- dispatch --------------->|
  |                             |                         task bắt đầu
  |                             |                         đang chạy/chờ
  |--- future.cancel(true) ----->|                             |
  |<-- trạng thái đã hủy --------|                             |
  |                             |                             |
  |   isCancelled() = true      |                        worker vẫn có thể
  |   join() ném cancellation   |                        thực hiện tiếp
  |                             |                             |
  |                             |                        kết thúc theo logic
~~~

Điều quan trọng là **`cancel(true) == true` không xác nhận worker đã dừng**. Bên gọi nhận `CancellationException` từ Future có thể đang nhìn một kết quả đã hủy, trong khi công việc vẫn chạy hoặc một request remote đã được xử lý.

### 1.1. Hai câu hỏi khác nhau

1. **Future còn cung cấp kết quả bình thường không?** Khi hủy thành công, không. `complete(value)` thông thường không ghi đè trạng thái đã được hủy.
2. **Worker có dừng và cleanup chưa?** Không suy ra được từ `isCancelled()`, `isDone()` hay `cancel()`. Phải có trạng thái công việc, tín hiệu worker exit hoặc xác nhận từ hệ thống điều phối.

“Cancel” ở API có thể chỉ là **cancel quyền chờ/nhận kết quả**; “stop job” là một giao thức nghiệp vụ mạnh hơn.

## 2. Hợp đồng của CompletableFuture.cancel(boolean)

Chữ ký API trong Java SE 17:

~~~java
public boolean cancel(boolean mayInterruptIfRunning)
~~~

Đây là **chữ ký rút gọn để tham khảo**, không phải method cần tự định nghĩa. Hành vi chính:

- Nếu Future chưa hoàn tất, `cancel(...)` hoàn thành nó bằng `CancellationException`.
- Tham số `mayInterruptIfRunning` không tác động đến cách implementation này điều khiển worker. `cancel(true)` và `cancel(false)` đều là thao tác đánh dấu hủy trạng thái.
- Nếu Future đã có kết quả bình thường hoặc lỗi trước đó, cancel không thay thế kết quả đã xác lập.
- Dependent CompletableFuture chưa hoàn tất sẽ hoàn tất đặc biệt do cancellation nguồn; lỗi ở stage dẫn xuất có thể là `CompletionException` với cause `CancellationException`.
- Giá trị trả về từ `cancel` là thông tin về trạng thái **đối tượng Future**. Nó không phải kết quả của một lời gọi `Thread.interrupt()` tới worker.

| API | Quan sát khi hủy thành công |
| --- | --- |
| `future.cancel(true)` | Future chuyển sang trạng thái hủy; không buộc ngắt worker |
| `future.isCancelled()` | `true`: Future bị hủy |
| `future.isDone()` | `true`: đã có trạng thái hoàn tất; không có nghĩa worker đã thoát |
| `future.isCompletedExceptionally()` | `true`: hủy là một dạng hoàn tất đặc biệt |
| `future.join()` | Ném `CancellationException` đối với Future gốc bị hủy trực tiếp |
| `future.get()` | Ném `CancellationException` đối với Future gốc bị hủy |
| `future.complete(value)` sau hủy | Không đổi trạng thái hủy sang giá trị bình thường |

`isDone()==true` cũng xuất hiện khi một Future **thành công** hoặc **lỗi**, nên không dùng nó làm tín hiệu nghiệp vụ “task đã thành công”. Tương tự, `isCancelled()==true` là trạng thái logic chứ không chứng minh đã rollback side effect.

### 2.1. Vì sao đặt mayInterruptIfRunning=true vẫn không giúp?

`CompletableFuture` không cần gắn một thread với Future: nó có thể được hoàn tất từ callback, completion stage, executor, event loop hoặc người gọi trực tiếp. API hủy của nó định nghĩa thay đổi trạng thái kết quả. JDK 17 ghi rõ tham số này không có tác dụng trong implementation vì interrupts không được dùng để điều khiển processing.

Không suy luận dựa vào **tên tham số** mà phải dựa vào **hợp đồng class cụ thể**. Đây là khác biệt quan trọng với `FutureTask.cancel(true)`.

## 3. Java 17 chạy độc lập: Future đã hủy nhưng worker còn chờ

Ví dụ sử dụng `CountDownLatch` để điều khiển chính xác: worker đã bắt đầu nhưng không thể kết thúc trước khi main mở latch. Main hủy CompletableFuture trước khi thả worker.

Tạo tệp **`CompletableFutureCancelDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CompletableFutureCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch workerEnded = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);
        try {
            CompletableFuture<Void> future = CompletableFuture.runAsync(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    interrupted.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    workerEnded.countDown();
                }
            }, pool);
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }
            System.out.println("1. cancel(true): " + future.cancel(true));
            System.out.println("2. isCancelled: " + future.isCancelled());
            try {
                future.join();
            } catch (CancellationException expected) {
                System.out.println("3. join(): CancellationException");
            }
            System.out.println("4. Worker ended before release: "
                    + (workerEnded.getCount() == 0));
            release.countDown();
            if (!workerEnded.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not finish");
            }
            System.out.println("5. Worker interrupted by cancel: "
                    + interrupted.get());
            System.out.println("6. isDone after worker exit: "
                    + future.isDone());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Lệnh biên dịch/chạy bằng JDK 17+:

~~~bash
javac --release 17 CompletableFutureCancelDemo.java
java CompletableFutureCancelDemo
~~~

Stdout đã kiểm chứng khi chạy chương trình:

~~~text
1. cancel(true): true
2. isCancelled: true
3. join(): CancellationException
4. Worker ended before release: false
5. Worker interrupted by cancel: false
6. isDone after worker exit: true
~~~

**Giải thích bằng các ràng buộc đồng bộ:**

1. `started.await(...)` bảo đảm worker thật sự đã chạy, không phải chỉ đang nằm trong queue.
2. Worker đang chặn tại `release.await()`. Nó không thể thoát khi main chưa mở latch, trừ khi bị interrupt.
3. `future.cancel(true)` đánh dấu kết quả hủy; `join()` đã nhìn thấy `CancellationException`.
4. Dòng thứ tư in `false` vì worker còn chờ, chứng minh trạng thái Future hủy **trước khi worker rời tác vụ**.
5. Main mở latch, worker thoát bình thường. `interrupted` là `false`, nên chính lệnh `cancel(true)` đã không ngắt worker trong kịch bản có kiểm soát này.
6. `isDone()` ở dòng cuối chỉ lặp lại trạng thái Future đã có từ trước, không phải một acknowledgement mới rằng worker kết thúc.

`shutdownNow()` chỉ được gọi ở `finally` **sau** khi kết quả đã được quan sát. Nếu đảo thứ tự, tín hiệu ngắt từ shutdown sẽ làm sai ý nghĩa thí nghiệm.

### 3.1. Vì sao không dùng Thread.sleep(100) để đoán?

Một test chạy task rồi ngủ 100 ms trước khi cancel có thể bị thay đổi bởi tải CI, CPU scheduling và thời gian khởi động worker. Latch giúp xác định **đã start** và **chưa thể finish**, nhờ đó tránh kết luận từ timing ngẫu nhiên.

## 4. So sánh: FutureTask.cancel(true) có thể yêu cầu ngắt

Interface `Future` có nhiều implementation. `FutureTask` thường được sử dụng khi `ExecutorService.submit(...)` trả một `Future<?>`. Với implementation đó, `cancel(true)` có thể yêu cầu `Thread.interrupt()` trên thread đang thực thi. Tuy nhiên **interruption vẫn là tín hiệu hợp tác**, không phải cơ chế giết thread cưỡng bức.

Tạo tệp độc lập **`InterruptibleFutureDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptibleFutureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch observed = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);
        try {
            Future<?> handle = pool.submit(() -> {
                started.countDown();
                try {
                    Thread.sleep(60_000);
                } catch (InterruptedException ex) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    observed.countDown();
                }
            });
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }
            System.out.println("1. Future.cancel(true): " + handle.cancel(true));
            if (!observed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not observe interruption");
            }
            System.out.println("2. Worker observed interruption: " + sawInterrupt.get());
            System.out.println("3. Future isCancelled: " + handle.isCancelled());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 InterruptibleFutureDemo.java
java InterruptibleFutureDemo
~~~

Stdout đã kiểm chứng:

~~~text
1. Future.cancel(true): true
2. Worker observed interruption: true
3. Future isCancelled: true
~~~

Worker đang ở thao tác `Thread.sleep(...)` có khả năng phản ứng với interrupt bằng `InterruptedException`. `FutureTask.cancel(true)` gửi yêu cầu ngắt và chương trình quan sát được.

Dù vậy, nếu worker phớt lờ cờ interrupt, chặn trong một I/O không hỗ trợ interruption hoặc đã commit một giao dịch, `Future.cancel(true)` **không thể bảo đảm worker dừng ngay** và cũng không rollback side effect.

| Cơ chế | Ý nghĩa trực tiếp | Có bảo đảm dừng ngay? |
| --- | --- | --- |
| `CompletableFuture.cancel(true)` | Đánh dấu kết quả hủy bằng `CancellationException`; bỏ qua mayInterruptIfRunning | Không |
| `FutureTask.cancel(true)` | Yêu cầu hủy, có thể gửi interrupt tới thread đang chạy | Không; task phải hợp tác |
| `Thread.interrupt()` | Gửi tín hiệu ngắt; một số blocking API quan sát và ném `InterruptedException` | Không |
| `ExecutorService.shutdownNow()` | Cố gắng ngắt task đang chạy và dừng nhận việc | Không; cơ chế best-effort |
| Token `AtomicBoolean` | Gửi cờ dừng do ứng dụng định nghĩa | Không; worker phải kiểm tra cờ |

Không dùng `Thread.stop()` để ép task chấm dứt: đó là API không an toàn và đã bị deprecated. Không gọi interrupt tùy tiện vào thread của pool dùng chung khi không có quyền sở hữu công việc.

## 5. Cancellation đối với chuỗi CompletionStage

Với `thenApply`, `thenCompose`, `whenComplete` và các stage khác, cần phân biệt **Future gốc** và **stage phụ thuộc**.

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<Integer> dependent =
        source.thenApply(String::length);
source.cancel(true);
~~~

Đây là mã Java minh họa (cần import `CompletableFuture`). Nếu nguồn chưa hoàn tất và bị hủy:

- `source.isCancelled()` là `true`; `source.join()` ném `CancellationException`.
- `dependent` chưa hoàn tất sẽ hoàn thành đặc biệt, thông thường bằng `CompletionException` mang cause `CancellationException`.
- Function `String::length` không nhận kết quả bình thường để xử lý.
- `dependent.isCancelled()` **không nhất thiết là `true`**, vì stage dẫn xuất có thể chỉ mang trạng thái exception, không phải object được gọi `cancel(...)` trực tiếp.

**Hủy một dependent stage không mặc nhiên hủy upstream**, và hủy một source Future không tự biết cách hủy HTTP request, JDBC query hoặc công việc đã được chuyển cho một hệ thống khác. Nếu cần lan tín hiệu hủy qua pipeline, phải xây dựng một cancellation protocol riêng.

Ví dụ callback phân loại trên Future gốc:

~~~java
source.whenComplete((value, error) -> {
    if (error instanceof java.util.concurrent.CancellationException) {
        System.out.println("Result cancelled");
    } else if (error != null) {
        System.out.println("Result failed: " + error);
    } else {
        System.out.println("Result completed: " + value);
    }
});
~~~

Đây là snippet minh họa, không có stdout cố định nếu không biết trạng thái `source` lúc đăng ký. Trên dependent stage, exception có thể được bọc trong `CompletionException`; kiểm tra cause thay vì chỉ so sánh kiểu ngoài cùng.

Callback hoàn tất có thể chạy trên thread hoàn thành/hủy; các biến thể `*Async` dùng cơ chế scheduling khác. Tránh block dài trong callback mà không biết thread nào sẽ chạy nó.

## 6. Timeout không tự dừng worker

Các API timeout của Java thể hiện **quyền chờ kết quả**, **trạng thái kết quả** hoặc **timeout I/O**, là ba trách nhiệm khác nhau.

| API | Hành vi khi hết thời gian | Có tự ngắt worker? |
| --- | --- | --- |
| `future.get(2, SECONDS)` | Caller ngừng chờ, nhận `TimeoutException` | Không |
| `future.orTimeout(2, SECONDS)` | Chính CompletableFuture hoàn thành đặc biệt bằng `TimeoutException` nếu còn pending | Không |
| `future.completeOnTimeout(fallback, 2, SECONDS)` | Chính CompletableFuture hoàn thành bằng giá trị fallback nếu còn pending | Không |
| `future.cancel(true)` | CompletableFuture chuyển sang hủy nếu còn có thể | Không, tham số true bị bỏ qua |
| HTTP/JDBC client timeout | Giới hạn thao tác I/O theo API cụ thể | Tùy thư viện, không được đồng nhất với cancel Future |

`orTimeout(...)` và `completeOnTimeout(...)` trả **chính CompletableFuture được gọi**, không phải một bản sao độc lập của kết quả. Nếu underlying task vẫn đang chạy, nó có thể tiếp tục ghi dữ liệu dù Future đã trả lỗi timeout hoặc fallback.

Ví dụ tích hợp với một công việc chậm:

~~~java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(() -> slowOperation(), executor);
result.orTimeout(2, TimeUnit.SECONDS);
~~~

Snippet trên cần có `slowOperation()`, `executor` và imports. Nó **không bảo đảm ngắt** `slowOperation()` khi hết 2 giây. Muốn deadline thật cho network/DB phải cấu hình timeout trong thư viện tương ứng, và có kiểm soát khi side effect đã xảy ra.

### 6.1. Timeout từ góc nhìn toàn hệ thống

Một task có thể mất 5 giây trong executor queue rồi 10 giây thực thi. Nếu SLA cho phép tổng 8 giây, một I/O timeout 10 giây trên worker là chưa đủ. Nên theo dõi `t_submit`, `t_start`, `t_finish`, áp dụng deadline end-to-end, và kiểm tra thời hạn ở điểm bắt đầu để tránh thực thi một nhiệm vụ đã hết giá trị.

**Timeout ở caller, trạng thái hủy của Future và ngừng thực hiện side effect là ba sự kiện cần xác nhận riêng.**

## 7. Với Spring @Async, cần phân biệt Future và worker

Trong Spring Framework, phương thức `@Async` có thể trả `CompletableFuture<T>` để caller nhận kết quả, ghép callback hoặc theo dõi lỗi. Tuy nhiên, **không có hợp đồng chung rằng gọi `cancel(true)` trên Future được trả về sẽ ngắt target method đang chạy trong ThreadPoolTaskExecutor**.

Những yếu tố cần kiểm tra:

1. `@EnableAsync` được bật, bean thực sự do Spring quản lý.
2. Caller đi qua Spring proxy. Self-invocation như `this.doWork()` thường bypass interceptor trong proxy mode mặc định.
3. `@Async("jobExecutor")` chọn đúng executor. Method có thể đang queue hoặc đã bắt đầu lúc caller nhận Future.
4. Nếu executor không chấp nhận việc, `TaskRejectedException` có thể xuất hiện **ngay lúc gửi**, không phải một trạng thái cancellation của task đã chạy.
5. `@Async void` không có Future trả về để caller gọi `cancel`; cần kênh request-cancel khác nếu nghiệp vụ hỗ trợ.
6. Với `CompletableFuture<T>`, kể cả `cancel(true)` thành công ở handle, vẫn phải xác minh worker đã thực sự dừng theo logic/metric của ứng dụng.

Không triển khai nút Hủy ở API chỉ bằng `storedFuture.cancel(true)` rồi trả kết quả “job đã dừng chắc chắn”. Future có thể đã bị hủy còn worker đang gọi remote service.

## 8. Hủy hợp tác bằng cancellation token trong Spring

Nếu yêu cầu là **dừng công việc**, hãy thiết kế cơ chế hợp tác thay vì trông chờ trạng thái Future:

1. Service điều phối tạo một token cho mỗi job.
2. Worker kiểm tra token tại các điểm an toàn giữa những bước xử lý.
3. Endpoint hủy đặt token thành yêu cầu dừng.
4. Worker dừng, cleanup và báo lại trạng thái cuối.
5. Hệ thống phân biệt `CANCEL_REQUESTED` với `CANCELLED`: đã nhận yêu cầu khác với xác nhận đã dừng.

Một token trong cùng JVM có thể là `AtomicBoolean`. Nó thread-safe nhưng **không tự đánh thức blocking I/O**, nên công việc dài vẫn cần timeout và cơ chế interruption riêng nếu muốn phản hồi nhanh.

### 8.1. Cấu hình ThreadPoolTaskExecutor

Tệp `AsyncPoolConfiguration.java` (Spring Framework 6.x và Java 17+):

~~~java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncPoolConfiguration {
    @Bean("jobExecutor")
    public ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("job-");
        return executor;
    }
}
~~~

Đây là **mã tích hợp Spring** cần dependency Spring Context và được đăng ký qua ApplicationContext; không biên dịch bằng `javac` riêng một tệp không có classpath. Các số pool chỉ là minh họa, không phải tuning chung cho mọi workload.

### 8.2. Worker kiểm tra tín hiệu dừng

Tệp `ReportWorker.java`:

~~~java
package example.concurrency;

import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    @Async("jobExecutor")
    public CompletableFuture<String> build(
            String reportId, AtomicBoolean cancelRequested) {
        try {
            for (int part = 1; part <= 10; part++) {
                if (cancelRequested.get()
                        || Thread.currentThread().isInterrupted()) {
                    throw new CancellationException(
                            "Report cancellation requested: " + reportId);
                }
                // Mô phỏng I/O; trong ứng dụng thật đặt timeout cho HTTP/DB.
                TimeUnit.MILLISECONDS.sleep(100);
            }
            return CompletableFuture.completedFuture("ready:" + reportId);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(ex);
        }
    }
}
~~~

Mã này minh họa **điểm kiểm tra token** trong worker. Khi một bước chạy xong, vòng lặp mới quan sát cờ. Nếu worker đang ở thao tác `sleep(...)`, chỉ đổi `AtomicBoolean` không tự đánh thức nó. Không dùng `Thread.sleep` làm I/O giả lập trong production mà bỏ qua timeout thực tế.

Caller ở **bean khác** có thể dùng:

~~~java
AtomicBoolean stopRequested = new AtomicBoolean(false);
CompletableFuture<String> result =
        reportWorker.build("R-17", stopRequested);

// Một lúc khác người dùng yêu cầu ngừng:
stopRequested.set(true);

// Theo dõi worker hoàn tất theo giao thức hợp tác:
result.whenComplete((value, error) -> {
    if (error != null) {
        System.out.println("Worker did not complete normally: " + error);
    } else {
        System.out.println("Worker completed: " + value);
    }
});
~~~

Đây là **đoạn caller minh họa**, giả định `reportWorker` được Spring inject, có imports `AtomicBoolean` và `CompletableFuture`. Không có stdout cố định: công việc có thể hoàn tất trước hoặc sau khi cờ được đặt.

**Tại sao không lập tức gọi `result.cancel(true)` trong ví dụ này?** Vì khi đó `result` có thể báo hủy ngay trong khi worker chưa kiểm tra token, làm mất một kênh theo dõi thời điểm worker thực sự thoát. Với hợp đồng cần biết đã dừng, nên giữ job status hoặc completion signal tách biệt.

### 8.3. Hủy công việc liên process hoặc nhiều replica

`AtomicBoolean` chỉ truyền tín hiệu trong một JVM. Nếu job chạy trên pod A mà request cancel đến pod B, cờ trong bộ nhớ B không thể tác động tới worker A. Thiết kế cần job id, nơi lưu trạng thái tập trung và kênh báo tín hiệu hoặc polling tới đúng worker. Với job có yêu cầu bền vững, thêm job store, retry/idempotency và cơ chế khôi phục sau restart.

Token lưu trong map cần có lifecycle cleanup để không rò bộ nhớ, nhưng cũng không nên xóa trước khi worker thực sự hoàn tất.

## 9. Interruption là tín hiệu hợp tác, không phải lệnh giết thread

Một số API Java như `Thread.sleep`, `Object.wait` hoặc `BlockingQueue.take` hỗ trợ ngắt bằng `InterruptedException`. Khi code bắt exception này nhưng không thể ném lên tầng trên, mẫu phổ biến là khôi phục cờ interrupt rồi thoát:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Đây là **pseudocode trong một method void**, giả định `blockingOperation()` có thể ném `InterruptedException`. Trong method có thể khai báo `throws InterruptedException`, việc ném tiếp cũng là cách xử lý hợp lệ.

Tránh `catch (InterruptedException ignored) {}` rồi chạy tiếp vô thời hạn. Nhưng cũng không nên tưởng mọi JDBC/HTTP/remote API đều chấm dứt lập tức khi thấy interrupt: một số I/O cần timeout/hủy riêng, và hệ thống từ xa có thể đã nhận công việc.

### 9.1. Side effect không bị hoàn tác bởi cancel

Một worker có thể đã ghi cơ sở dữ liệu, gửi email hoặc thực hiện HTTP POST trước khi caller yêu cầu cancel. Khi `future.cancel(true)` thành công, những tác động đã xảy ra **không được rollback**. Trong Spring, transaction context thường gắn với thread; transaction của caller không tự lan đầy đủ sang worker `@Async`. Hủy Future của caller không tự rollback transaction worker.

Với nghiệp vụ không thể mất hoặc không được phép xử lý trùng, cần idempotency key, trạng thái job, giao thức rollback/compensation và một nguồn công việc bền vững nếu phù hợp. Không hứa “hủy thành công” chỉ vì handle chuyển sang canceled.

## 10. Hủy task trước khi bắt đầu chạy

Nếu task còn chờ queue, hủy một Future trước khi nó start có thể khiến wrapper của executor **bỏ qua logic task** khi được worker lấy ra. Nhưng điều này phụ thuộc implementation, loại Future, cách tạo callback và cơ chế hủy. Không suy luận rằng mọi `CompletableFuture.cancel()` sẽ tự gỡ chính xác task khỏi queue của mọi `TaskExecutor`.

Đối với `FutureTask` từ `ExecutorService.submit(...)`, việc hủy thành công trước khi task chạy thông thường ngăn phần `Callable/Runnable` chạy. Với một CompletableFuture dùng `runAsync`, cần kiểm tra đường dispatch/wrapper thực tế nếu yêu cầu ngăn task tuyệt đối.

Tương tự, hủy một dependent stage không đồng nghĩa dừng stage nguồn. Một stage có thể đã khởi chạy HTTP call trước khi downstream bị hủy. Cần thiết kế cách truyền cancellation riêng nếu upstream cũng phải dừng.

## 11. Quy trình xác minh cancellation trong production

Để tránh dashboard báo “100% jobs canceled” trong khi worker vẫn chạy, nên ghi nhận riêng:

| Sự kiện/metric | Ý nghĩa |
| --- | --- |
| `submitted_total` | Số task được yêu cầu |
| `started_total` | Số worker thực sự bắt đầu |
| `cancel_requested_total` | Số lời yêu cầu dừng |
| `future_cancelled_total` | Số handle Future chuyển sang trạng thái hủy |
| `worker_stopped_total` | Số worker có tín hiệu đã thoát/cleanup |
| `completed_total` | Số tác vụ hoàn tất bình thường |
| `failed_total` | Số tác vụ thất bại |
| `cancel_latency` | Khoảng từ yêu cầu hủy tới worker xác nhận dừng |
| `active_threads` / `queue_depth` | Pool còn bận và backlog bao nhiêu |

Các tên trên là **gợi ý metrics**, không phải những tên Spring mặc định bắt buộc phải có. Dùng job id/correlation id để nối logs giữa caller, worker và downstream. Nếu Future bị cancel, `whenComplete` có thể chạy ngay và báo lỗi cancellation **trước khi worker thực tế dừng**; không lấy callback đó làm metric xác nhận stopped.

### 11.1. Ngôn ngữ trạng thái rõ ràng

- **`CANCEL_REQUESTED`:** hệ thống đã nhận lệnh yêu cầu hủy.
- **`CANCELLING`:** worker đang phối hợp thoát và cleanup, nếu cần phân biệt.
- **`CANCELLED`:** đã có xác nhận rằng job không còn thực hiện công việc theo giao thức của ứng dụng.
- **`SUCCEEDED`:** worker hoàn tất trước khi lệnh hủy có hiệu lực.
- **`FAILED`:** lỗi khác phát sinh; cần xem có retry/compensation không.

Không dùng `future.isCancelled()` để quyết định mọi trạng thái nghiệp vụ trên khi chưa có kênh xác nhận từ worker.

## 12. Cách kiểm thử đáng tin cậy

Một bài test liên quan hủy nên bảo đảm **worker đã bắt đầu** trước khi gọi cancel. Dùng latch/barrier hoặc fake client có thể dừng tại điểm xác định:

1. **Cancel CompletableFuture đang chạy:** dùng `CompletableFutureCancelDemo`; kiểm tra Future canceled trong khi worker vẫn chờ; sau đó thả latch để cleanup.
2. **FutureTask nhận interrupt:** dùng `InterruptibleFutureDemo`; worker chặn ở API có thể ngắt, cancel và xác minh worker quan sát `InterruptedException`.
3. **Timeout không dừng worker:** tạo task có latch, gọi `get(timeout)`/`orTimeout`, xác nhận callback chưa rời latch trước khi main mở nó.
4. **Spring @Async proxy:** gọi qua bean Spring thật, không gọi `this.method()`; inject đúng executor và token.
5. **Hủy tại ranh giới side effect:** dùng fake DB/API để kiểm tra worker không tạo side effect mới sau điểm kiểm tra token được thiết kế; đồng thời xác minh xử lý trường hợp side effect đã xảy ra.
6. **Đóng executor:** cleanup trong `finally`, dùng timeout hữu hạn để tránh test treo và không để worker vô hạn sau khi test.

Test dùng `Thread.sleep(100)` ở main để đoán task đã bắt đầu thường chập chờn trên CI. Latch khiến thứ tự trong ví dụ có bằng chứng.

## 13. Các nhầm lẫn thường gặp

**“`CompletableFuture.cancel(true)` chắc chắn gửi interrupt đến worker.”** Sai. Theo Java SE 17, tham số `mayInterruptIfRunning` không có tác dụng với implementation CompletableFuture.

**“`cancel(true)` trả true nghĩa là worker đã dừng.”** Sai. Đó là trạng thái Future, không phải acknowledgement của worker.

**“`future.isDone()==true` có nghĩa công việc đã xong.”** Sai. Hủy và lỗi đều là trạng thái hoàn tất của Future; worker có thể còn chạy.

**“`join()` ném CancellationException nghĩa là database chưa commit.”** Sai. Side effect có thể đã diễn ra hoặc tiếp tục.

**“`get(timeout)` ném TimeoutException nên task tự bị hủy.”** Sai. Caller chỉ thôi đợi kết quả.

**“`orTimeout` sẽ ngắt thread sau N giây.”** Sai. Nó cập nhật trạng thái CompletableFuture, không điều khiển I/O thực tế.

**“AtomicBoolean tự làm worker thức dậy.”** Sai. Cờ phải được kiểm tra; blocking I/O cần timeout/interrupt phù hợp.

**“Spring @Async trả Future thì Spring chắc chắn ngắt được thread của method khi cancel.”** Không có bảo đảm chung như vậy. Cần xác nhận implementation và thiết kế giao thức stop riêng.

**“Nếu future canceled thì mọi dependent và upstream cũng ngừng chạy.”** Sai. Dependent có thể hoàn tất đặc biệt, upstream không mặc nhiên nhận lệnh dừng.

**“Hủy một job đồng nghĩa có thể rollback mọi giao dịch đã commit.”** Sai. Cancellation là quyết định điều khiển, không phải transaction rollback toàn hệ thống.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `CompletableFuture.cancel(true)` trả true, worker đang chờ `CountDownLatch.await()`. Worker có chắc nhận `InterruptedException` không?

**Đáp án:** không. CompletableFuture bỏ qua tham số true, nên worker có thể tiếp tục đợi cho tới khi latch được mở hoặc có nguồn interrupt khác.

**Câu 2.** `isCancelled()==true` và `isDone()==true` có chứng minh worker đã thoát không?

**Đáp án:** không. Hai hàm chỉ phản ánh trạng thái kết quả; phải có tín hiệu dừng từ worker.

**Câu 3.** `FutureTask.cancel(true)` khác gì `CompletableFuture.cancel(true)`?

**Đáp án:** FutureTask có thể yêu cầu interrupt thread đang chạy; CompletableFuture tiêu chuẩn không dùng interrupt để điều khiển processing. Cả hai đều không bảo đảm rollback hoặc kết thúc tức thì.

**Câu 4.** Nếu `get(2, SECONDS)` ném `TimeoutException`, task có bị hủy không?

**Đáp án:** không mặc nhiên. Chỉ lượt chờ của caller hết thời gian.

**Câu 5.** Trong ví dụ đầu tiên, vì sao in “Worker ended before release: false”?

**Đáp án:** worker đã bắt đầu nhưng vẫn chờ latch; main chưa mở latch và cancel không interrupt worker.

**Câu 6.** Thiết kế chức năng Cancel cho job Spring @Async chạy lâu thế nào?

**Đáp án:** cần job id, token/status riêng, worker kiểm tra ở điểm an toàn, timeout I/O, phân biệt CANCEL_REQUESTED với CANCELLED; khi có nhiều pod cần tín hiệu/điều phối phân tán.

**Câu 7.** Nếu caller cancel Future ngay sau HTTP POST tạo đơn hàng, có chắc đơn hàng chưa được tạo không?

**Đáp án:** không. Request có thể đã đến remote service; dùng idempotency key, tra cứu trạng thái và/hoặc cơ chế bù trừ phù hợp.

**Câu 8.** Để chứng minh cancel không interrupt worker, nên dùng sleep ngẫu nhiên ở test hay latch?

**Đáp án:** dùng latch để bảo đảm worker đã chạy và chưa thể kết thúc trước khi cancel, rồi quan sát interrupt và cleanup theo thứ tự kiểm soát.

## 15. Tài liệu tham khảo chính thức

- Java SE 17 — `CompletableFuture`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Java SE 17 — `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17 — `FutureTask`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html
- Java SE 17 — `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — `Thread.interrupt()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Spring Framework — Task Execution and Scheduling / `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
