# Chọn cách thực thi theo tải, môi trường và yêu cầu vòng đời

## 1. Mục tiêu và nguyên tắc chọn bộ thực thi

Một lời gọi nghiệp vụ trong Spring có thể chạy trực tiếp trên thread hiện tại, được nộp vào pool, chạy trên virtual thread, được điều phối bởi scheduler, tiếp tục trong reactive pipeline hoặc chuyển thành công việc bền vững qua hàng đợi bên ngoài. Mỗi cách có đặc tính tài nguyên, phản hồi lỗi và vòng đời khác nhau.

**Bài toán chính:** chọn **cách thực thi** phù hợp với **tải công việc**, **môi trường triển khai** và **yêu cầu vòng đời**, sau đó cấu hình giới hạn, timeout, quan sát và cơ chế dừng. Không chọn executor chỉ dựa trên tên API hay mong muốn “càng nhiều thread càng nhanh”.

Sau bài học, người học cần có khả năng:

- Mô tả tải CPU-bound, blocking I/O, non-blocking I/O, burst, tác vụ ngắn/dài và yêu cầu độ trễ.
- Phân biệt chạy đồng bộ, `TaskExecutor`/`@Async`, `TaskScheduler`/`@Scheduled`, virtual threads, Reactor và durable job.
- Tính toán sơ bộ nhu cầu concurrency từ arrival rate và thời gian xử lý, đồng thời nhận biết giới hạn CPU/connection/downstream.
- Thiết kế thread pool và queue hữu hạn, chính sách khi quá tải, timeout và cancellation; tránh tạo hàng đợi vô hạn.
- Chọn cấu hình phù hợp giữa Spring MVC, WebFlux, tác vụ batch, Jakarta EE và nhiều instance của ứng dụng.
- Phân rõ ai sở hữu executor, ai được phép shutdown, cách xử lý task đang chạy khi ứng dụng dừng và việc cần thực thi bền vững sau restart.
- Kiểm chứng lựa chọn bằng metric, load test và tình huống lỗi.

Trong bài, “executor” là thành phần quyết định *chạy task bằng cách nào*; “scheduler” quyết định *khi nào nộp/chạy task*. Một scheduler có thể cũng sử dụng thread để thực thi callback, nhưng hai trách nhiệm này cần được phân biệt.

## 2. Ba trục quyết định trước khi chọn API

### 2.1. Trục tải: công việc thực sự dùng CPU hay chờ gì?

| Dạng công việc | Đặc điểm | Cách tiếp cận ban đầu |
| --- | --- | --- |
| Tính toán CPU-bound | Ít thời gian chờ; tốn CPU thật: mã hóa, phân tích, chuyển đổi dữ liệu lớn | Pool giới hạn gần năng lực CPU đo được; tránh tăng thread vô hạn |
| Blocking I/O | Thread thường chờ JDBC, HTTP client đồng bộ, file hoặc dịch vụ bên ngoài | Pool có giới hạn rõ, hoặc virtual threads (JDK 21+) kèm giới hạn downstream |
| Non-blocking I/O | Driver/client trả tín hiệu hoàn tất mà không chiếm thread chờ toàn thời gian | Duy trì reactive/event-driven pipeline, tránh block event loop |
| Tác vụ rất ngắn | Xử lý rẻ hơn chi phí nộp queue, context switch và đồng bộ | Có thể chạy ngay trên caller thread |
| Công việc dài, có thể mất phút/giờ | Không thích hợp giữ request chờ; cần theo dõi trạng thái, retry, khôi phục | Job bất đồng bộ có định danh; dùng storage/queue bền vững nếu không được mất |
| Burst, lưu lượng thay đổi nhanh | Số task đến tức thời lớn hơn khả năng xử lý | Bounded queue, backpressure, admission control và rejection policy |
| Tác vụ định kỳ | Chạy theo giờ/khoảng thời gian | `TaskScheduler` hoặc hệ thống lịch bên ngoài; cân nhắc nhiều replica |

Một tác vụ có thể có nhiều giai đoạn. Chẳng hạn đọc từ DB là blocking I/O, biến đổi dữ liệu là CPU-bound, gọi API bên ngoài lại blocking I/O. Không cần bắt mọi giai đoạn chạy cùng một executor nếu chúng có giới hạn tài nguyên và mức ưu tiên khác nhau.

### 2.2. Trục môi trường: runtime đang quản lý thread ra sao?

- **Spring MVC / Servlet:** request thường được xử lý qua thread do web container quản lý. Nộp tác vụ sang executor có thể giải phóng request thread trong một số kiểu xử lý async, nhưng một HTTP request **chờ** `Future.get()` ngay sau khi submit vẫn có thể chặn thời gian tương tự; việc chuyển thread chỉ làm tăng công việc điều phối.
- **Spring WebFlux / Reactor:** event-loop phải được giữ không bị chặn. Blocking client trên event-loop là lỗi thiết kế dễ gây suy giảm toàn hệ thống; ưu tiên non-blocking API. Khi phải bao một blocking API, chuyển nó sang bounded scheduler thích hợp, ví dụ `Schedulers.boundedElastic()`, và đo giới hạn của nó.
- **Spring Boot độc lập (embedded server):** Spring quản lý bean executor/scheduler; cấu hình auto-configuration phụ thuộc phiên bản Boot, bean nào đã khai báo và khả năng bật virtual threads.
- **Jakarta EE / application server quản lý thread:** kiểm tra hợp đồng container; dùng `ManagedExecutorService` hoặc adapter/managed executor của Spring thay vì tự tạo thread ngoài cơ chế quản lý.
- **Batch, CLI, job ngắn hạn:** kết quả và exit code là một phần hợp đồng; phải đợi task được yêu cầu hoàn tất và shutdown executor trước khi process kết thúc.
- **Container / Kubernetes / serverless:** instance có thể bị thay thế, scale về 0 hoặc hết thời gian chạy. Không dựa vào bộ nhớ/queue trong process nếu task bắt buộc tồn tại qua restart.
- **Nhiều replica:** một `@Scheduled` gắn trong mỗi instance có thể chạy trên từng replica; lịch đơn nhất toàn cụm cần cơ chế điều phối/lock hoặc scheduler bên ngoài.

### 2.3. Trục vòng đời: task được phép tồn tại bao lâu?

Trước khi chọn executor, ghi rõ:

1. **Nguồn kích hoạt:** request, message, timer, startup, batch command hay sự kiện nghiệp vụ.
2. **Deadline:** caller cần phản hồi trong bao lâu? Task có timeout riêng không?
3. **Ownership:** ai tạo, dùng và đóng executor? Spring context, application server hay code tạo bằng `new`?
4. **Durability:** task có được mất khi JVM tắt không? Có cần lưu job vào DB/queue trước khi báo accepted?
5. **Cancellation:** caller timeout/disconnect có cần hủy task không? Task có hỗ trợ interrupt và I/O timeout không?
6. **Error/result:** lỗi trả về caller, được lưu trạng thái job, hay gửi tới dead-letter queue?
7. **Context:** transaction, security identity, locale, trace ID và request context có thể bị đổi khi chuyển thread.
8. **Quá tải:** nếu hàng chờ đầy, caller chờ, nhận lỗi, retry có giới hạn hay giảm chất lượng dịch vụ?
9. **Shutdown:** ngừng nhận task, xử lý in-flight và thời gian grace; task chưa hoàn thành được khôi phục bằng cách nào?

Nếu không thể trả lời các câu hỏi trên, cấu hình số thread sẽ chỉ là một phỏng đoán.

## 3. Sơ đồ quyết định nhanh

```text
Có bắt buộc hoàn thành trong cùng lời gọi / transaction hiện tại?
  ├─ Có, công việc ngắn và không gây chặn kéo dài
  │    └─ Chạy đồng bộ trên caller thread
  └─ Không
       ├─ Cần tồn tại sau restart, retry bền vững hoặc xử lý nhiều phút?
       │    └─ Durable job/queue/workflow + worker có giới hạn
       └─ Có thể quản lý trong vòng đời JVM
            ├─ Kích hoạt theo lịch?
            │    └─ TaskScheduler/@Scheduled; tách worker pool nếu callback dài
            └─ Kích hoạt theo request/event/task
                 ├─ Reactor non-blocking pipeline?
                 │    ├─ Có non-blocking API → giữ pipeline non-blocking
                 │    └─ Chỉ có blocking API → offload có giới hạn
                 ├─ CPU-bound → pool hữu hạn theo CPU và ưu tiên
                 └─ Blocking I/O → pool bounded hoặc virtual threads
                                     + timeout + giới hạn tài nguyên downstream
```

Đây là điểm bắt đầu, không phải thuật toán có thể bỏ qua load test. Một request có deadline ngắn vẫn có thể cần workflow durable nếu công việc nghiệp vụ bắt buộc được thực thi nhưng caller chỉ nhận job ID.

## 4. Chạy đồng bộ: lựa chọn có chủ đích

Dùng trực tiếp lời gọi phương thức khi kết quả cần ngay, công việc nhanh, các bước phải nằm cùng transaction hoặc không cần tách vòng đời. Việc tạo bất đồng bộ không đem lại lợi ích nếu caller vẫn chờ kết quả ngay lập tức.

Trong Spring có `SyncTaskExecutor`, thực thi task **ngay trong thread gọi**. Đây là lựa chọn hữu ích cho test xác định hoặc khi muốn cố ý không chuyển thread; tên “executor” không có nghĩa luôn có pool.

Tệp `SyncAndAsyncChoiceDemo.java`, chạy trên Java 17+:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SyncAndAsyncChoiceDemo {
    static int calculate(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("sync=" + calculate(20, 22));

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> future = executor.submit(
                    () -> calculate(20, 22));
            System.out.println("async result=" + future.get());
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac SyncAndAsyncChoiceDemo.java
java SyncAndAsyncChoiceDemo
```

Kết quả:

```text
sync=42
async result=42
```

Ở bước thứ hai, công việc được submit vào thread khác, nhưng `future.get()` chặn thread chính để nhận kết quả. Nếu công việc đơn giản như phép cộng, việc tạo executor/queue còn gây overhead; nếu phép tính nặng, tách khỏi request có thể hữu ích **khi caller không cần chờ trực tiếp** hoặc đã có cơ chế trả kết quả bất đồng bộ thực sự.

Chạy đồng bộ không có nghĩa là mặc nhiên thread-safe: nếu phương thức sửa bean singleton hoặc cache chung, vẫn cần bảo vệ trạng thái và kiểm tra invariant.

## 5. ThreadPoolTaskExecutor: lựa chọn quen thuộc cho tải hữu hạn

`ThreadPoolTaskExecutor` bọc `java.util.concurrent.ThreadPoolExecutor` và có lifecycle tích hợp với Spring. Các tham số cốt lõi:

- `corePoolSize`: số worker lõi mà pool có thể giữ sẵn/duy trì theo chính sách.
- `maxPoolSize`: trần số worker khi executor cần mở rộng.
- `queueCapacity`: khả năng chứa task chưa được thực thi.
- `keepAliveSeconds`: thời gian worker dư thừa được giữ khi rảnh; còn tùy chính sách core timeout.
- `RejectedExecutionHandler`: hành vi khi không nhận được thêm task do quá tải hoặc executor đã dừng.
- `threadNamePrefix`: giúp truy vết trong log, thread dump.
- Các thiết lập shutdown/await: quy định ứng dụng xử lý task đang chạy và queue ra sao lúc context đóng.

**Đừng bỏ qua mặc định.** Với `ThreadPoolTaskExecutor` của Spring Framework, mặc định cổ điển là `corePoolSize = 1`, `maxPoolSize` rất lớn và `queueCapacity` không giới hạn thực tế. Do pool thường **đưa task vào queue sau khi đạt core trước khi mở rộng đến max**, chỉ tăng `maxPoolSize` mà vẫn để queue vô hạn có thể không tạo hiệu quả tăng worker như kỳ vọng.

### 5.1. Quy tắc nhận task của ThreadPoolExecutor

Một cách gần đúng theo thứ tự thông thường:

1. Nếu đang có ít hơn `corePoolSize` worker, tạo worker cho task.
2. Nếu đã có core worker, thử xếp task vào queue.
3. Nếu queue đầy và số worker còn dưới `maxPoolSize`, thử tạo worker tiếp.
4. Nếu không thể nhận, áp dụng rejection policy.

Ví dụ `core = 4`, `max = 8`, `queue = 64`: sau khi bốn worker lõi bận, task mới thường được xếp vào queue; khi queue đầy mới cần mở thêm worker thứ 5–8. Cấu hình này không có nghĩa tám thread đều lập tức chạy ngay khi xuất hiện tám task. Scheduling/race có thể ảnh hưởng trạng thái tức thời, nên xem đây là quy tắc hoạt động của executor chứ không phải biểu đồ thời gian cố định.

`queueCapacity = 0` khiến pool dùng cơ chế handoff trực tiếp; khi không có worker sẵn sàng, nó có xu hướng mở rộng nhanh hơn tới giới hạn max rồi từ chối. Một queue lớn giúp hấp thụ burst nhưng làm tăng thời gian chờ và memory; queue nhỏ có thể làm task bị từ chối sớm hơn. Cần xác định chính sách nào đáp ứng SLA.

### 5.2. Cấu hình Spring cho nhóm I/O blocking

Ví dụ cấu hình sau cần Spring Framework và dependency phù hợp; đặt trong tệp `AsyncExecutionConfig.java` (đây là snippet ứng dụng Spring, không chạy đơn lẻ chỉ bằng `javac`):

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncExecutionConfig {
    @Bean("outboundIoExecutor")
    ThreadPoolTaskExecutor outboundIoExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("outbound-io-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
```

Ý nghĩa: tại thời điểm bình thường, executor dùng tối đa bốn core worker; có thể tăng tới tám khi queue hữu hạn đã đầy; nếu không còn năng lực nhận thì từ chối thay vì giữ vô hạn request. Các giá trị 4/8/64/20 **chỉ là mẫu để hiểu cơ chế**, không phải cấu hình sản xuất mặc định.

Khi dùng `AbortPolicy`, task bị từ chối sẽ dẫn đến lỗi nộp tác vụ (Spring có thể chuyển thành `TaskRejectedException`); tầng gọi phải quyết định trả 429/503, lưu công việc bền vững, chuyển hướng, hoặc retry có giới hạn. Đừng đợi tới khi đã quá tải mới quyết định chính sách xử lý.

Cấu hình `setWaitForTasksToCompleteOnShutdown(true)` ưu tiên hoàn tất công việc đã nhận, kể cả hàng đợi, khi shutdown. `setAwaitTerminationSeconds(20)` quy định khoảng chờ trong pha shutdown theo API; **không** bảo đảm mọi task đã hoàn thành trong 20 giây và không làm task bền vững qua process crash. Hành vi shutdown chính xác còn phụ thuộc phiên bản Spring, cách đóng context và hạ tầng cấp tín hiệu; cần kiểm thử với runtime mục tiêu.

### 5.3. Chọn pool cho CPU-bound

Với tính toán CPU thuần, đặt giới hạn số công việc thực sự chạy gần mức CPU hiệu dụng, rồi đo throughput/latency trong môi trường thật (container có thể bị CPU quota). Thread nhiều hơn số lõi không tự tăng năng lực tính toán; nó có thể chỉ tăng context switching và cạnh tranh cache.

Nếu một API vừa có tính toán nặng vừa có I/O blocking, cân nhắc pool riêng cho từng loại hoặc tách pipeline. Không dùng cùng một pool nhỏ cho task CPU kéo dài và task phản hồi nhanh nếu việc đó gây starvation.

### 5.4. Khi quá tải, tác vụ nên chờ ở đâu?

Một pool có queue không giới hạn biến “không đủ năng lực” thành **độ trễ và bộ nhớ tích tụ**. Cách tiếp cận an toàn hơn:

- Giới hạn số task đang chạy, queue và số connection tới downstream.
- Đặt timeout/đường retry ở tầng API, DB và client; tránh chờ vô hạn.
- Ưu tiên phản hồi fail-fast khi deadline caller đã không thể đáp ứng.
- Dùng hàng đợi bền vững khi công việc phải được xử lý sau, kèm idempotency key và retry policy.
- Quan sát rejection, queue length, queue wait, active count, completed count, latency và lỗi.
- Nếu áp dụng `CallerRunsPolicy`, hiểu rằng task sẽ chạy trên thread caller khi pool/queue đầy. Điều này tạo backpressure nhưng có thể kéo dài thời gian xử lý HTTP hoặc chặn event-loop; không chọn cho mọi môi trường.

### 5.5. Java 17+: mô phỏng pool hữu hạn và rejection

Ví dụ runnable sau chủ động giữ task đầu tiên cho tới khi main mở latch, để kết quả không phụ thuộc vào việc “đoán” lịch thread.

Tệp `BoundedPoolChoiceDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedPoolChoiceDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch release = new CountDownLatch(1);
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            Future<?> running = pool.submit(() -> {
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            Future<?> queued =
                    pool.submit(() -> System.out.println("queued task ran"));

            try {
                pool.execute(() -> {});
                System.out.println("unexpected acceptance");
            } catch (RejectedExecutionException e) {
                System.out.println("third task rejected");
            }

            release.countDown();
            running.get();
            queued.get();
        } finally {
            release.countDown();
            pool.shutdown();
        }
    }
}
```

```bash
javac BoundedPoolChoiceDemo.java
java BoundedPoolChoiceDemo
```

Kết quả:

```text
third task rejected
queued task ran
```

Một worker đang chờ; một slot queue đã chứa task thứ hai; task thứ ba bị từ chối. Latch bảo đảm task đầu chưa giải phóng worker trước khi main kiểm tra rejection. Đây là minh họa nguyên lý tải hữu hạn của `ThreadPoolExecutor`; trong Spring, `ThreadPoolTaskExecutor` cung cấp cấu hình tương tự và chuyển đổi một số lỗi theo hợp đồng riêng.

## 6. Virtual threads: tăng concurrency cho blocking I/O, vẫn phải kiểm soát tải

Java 21 cung cấp virtual threads ổn định. Chúng cho phép rất nhiều tác vụ dùng lối lập trình blocking dễ đọc trong lúc JVM điều phối chúng trên số platform threads nhỏ hơn. Virtual threads thường có ích khi **phần lớn thời gian task chờ I/O**, không giải quyết giới hạn CPU, DB connection pool hay quota của upstream.

Trong Spring Framework hỗ trợ tương ứng (ví dụ Spring 6.1+):

- `VirtualThreadTaskExecutor` tạo virtual thread mới cho từng task.
- `SimpleAsyncTaskExecutor` có thể dùng virtual threads khi bật tùy chọn hỗ trợ và chạy trên JDK 21+; executor này không có pool tái sử dụng thread theo nghĩa truyền thống.
- Spring Boot các phiên bản hỗ trợ có thể kích hoạt virtual threads bằng `spring.threads.virtual.enabled=true`; tác động tới auto-configured executor/scheduler tùy phiên bản và các bean đã tự khai báo. Không giả định mọi executor tùy chỉnh tự chuyển thành virtual threads.

**Virtual thread không phải cơ chế giới hạn concurrency.** Với 50.000 yêu cầu cùng gọi dịch vụ chỉ cho phép 40 connection, tạo 50.000 virtual threads không biến 40 connection thành 50.000. Cần semaphore, HTTP connection pool, rate limiter, bounded queue hoặc admission control ở boundary phù hợp.

### 6.1. Ví dụ Java 21+ với virtual-thread-per-task executor

Tệp `VirtualThreadChoiceDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadChoiceDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Integer> first = executor.submit(() -> 40);
            Future<Integer> second = executor.submit(() -> 2);
            System.out.println(first.get() + second.get());
        }
    }
}
```

```bash
javac VirtualThreadChoiceDemo.java
java VirtualThreadChoiceDemo
```

Kết quả:

```text
42
```

`try` với executor (JDK 21+) đóng tài nguyên và chờ theo hợp đồng `ExecutorService.close()`. Không suy ra hai phép tính nhỏ chạy nhanh hơn chỉ vì dùng virtual threads; ví dụ minh họa lifecycle và API. Khi worker truy cập remote I/O thật, áp dụng timeout, giới hạn connection và kiểm soát số request đồng thời.

### 6.2. Giới hạn downstream bằng Semaphore

Tệp `SemaphoreLimitDemo.java`, chạy với Java 17+:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreLimitDemo {
    public static void main(String[] args) throws Exception {
        Semaphore permits = new Semaphore(2);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        ExecutorService executor = Executors.newFixedThreadPool(4);

        try {
            List<Future<?>> jobs = new ArrayList<>();
            for (int i = 0; i < 10; i++) {
                jobs.add(executor.submit(() -> {
                    try {
                        permits.acquire();
                        try {
                            int now = active.incrementAndGet();
                            peak.accumulateAndGet(now, Math::max);
                            // Đại diện cho thao tác tới một tài nguyên giới hạn.
                        } finally {
                            active.decrementAndGet();
                            permits.release();
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }));
            }
            for (Future<?> job : jobs) {
                job.get();
            }
            System.out.println("underLimit=" + (peak.get() <= 2));
            System.out.println("allFinished=" + (active.get() == 0));
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac SemaphoreLimitDemo.java
java SemaphoreLimitDemo
```

Kết quả trong lần chạy bình thường, không có tác động interrupt ngoài chương trình:

```text
underLimit=true
allFinished=true
```

Dù executor có tối đa bốn worker, semaphore chỉ cho tối đa hai task đi vào vùng dùng tài nguyên đồng thời. Trong hệ thống thực, phép acquire có thể cần timeout, task có thể cần bị từ chối và metric phải đo số task đang đợi permit. Ví dụ này không khẳng định `peak` luôn bằng hai.

### 6.3. Các vấn đề thực tế cần kiểm tra

- Blocking I/O: thư viện/driver có hỗ trợ interrupt và timeout theo mong đợi không?
- Thread-local: mỗi virtual thread có giá trị ThreadLocal riêng; dùng ThreadLocal bừa bãi ở concurrency rất cao cũng có chi phí memory/context.
- CPU-bound: virtual threads không thay thế giới hạn theo lõi.
- Số lượng task: tạo không giới hạn vẫn có thể làm cạn heap, connection, file descriptor và nguồn lực hệ thống.
- Spring Boot với virtual threads: một số pool-size property không còn điều khiển virtual-thread executor như trước; cần kiểm tra chính xác auto-config ở phiên bản đang chạy.
- Vòng đời JVM: virtual threads là daemon; ở ứng dụng chỉ còn scheduled/background virtual threads, cần cơ chế keep-alive thích hợp khi môi trường yêu cầu process tiếp tục sống. Đối với Spring Boot hỗ trợ, xem `spring.main.keep-alive`.

## 7. Async method: chọn executor cho từng loại nghiệp vụ

`@EnableAsync` bật hỗ trợ `@Async` theo cấu hình phù hợp; `@Async("beanName")` yêu cầu Spring định tuyến method tới executor được chỉ định. Điều này hữu ích khi những task có đặc tính khác nhau không nên tranh cùng pool.

Ví dụ ứng dụng Spring (tách mỗi `public class` vào đúng file, có Spring dependencies):

Tệp `LookupWorker.java`:

```java
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class LookupWorker {
    @Async("outboundIoExecutor")
    public CompletableFuture<String> normalize(String input) {
        return CompletableFuture.completedFuture(
                input.trim().toUpperCase(Locale.ROOT));
    }
}
```

Tệp `LookupCaller.java`:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class LookupCaller {
    private final LookupWorker worker;

    public LookupCaller(LookupWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> run(String text) {
        return worker.normalize(text);
    }
}
```

Đây là ví dụ định tuyến, công việc mẫu rất nhẹ và **thực tế nên chạy đồng bộ**. Nó cho thấy Spring sẽ chọn bean executor có tên `outboundIoExecutor` ở cấu hình trước khi lời gọi tới `LookupWorker.normalize(...)` đi qua proxy Spring. Không giả định luôn là thread mới nếu chưa xác nhận interceptor, scope/proxy và executor được cấu hình đúng.

Ba lưu ý quan trọng:

1. **Self-invocation:** gọi `this.normalize(...)` trong chính bean thường không đi qua proxy của `@Async` ở chế độ mặc định, vì thế method không được offload như mong đợi.
2. **Kết quả và lỗi:** dùng `CompletableFuture`/`Future` khi caller cần quan sát thành công hoặc thất bại. Method async trả `void` không có kênh trả exception về caller; cấu hình `AsyncUncaughtExceptionHandler` và logging nếu phải dùng.
3. **Thread boundary:** context transaction, security, MDC, locale và request-scoped data không mặc nhiên được truyền. Transaction ở thread caller không tự bao trùm việc xảy ra về sau trong thread worker.

Nếu caller gọi `worker.normalize(...).join()` tức thời trên request thread, người gọi vẫn chờ. Lợi ích của concurrency phải xuất phát từ cấu trúc ứng dụng, ví dụ caller trả job ID, kết hợp nhiều future đúng cách, hoặc dùng xử lý async phù hợp với HTTP framework.

### 7.1. Một executor chung hay nhiều executor?

Một pool dùng chung dễ cấu hình nhưng có thể gây **head-of-line blocking**: batch đồng bộ hóa dữ liệu chạy dài chiếm hết worker và queue, trong khi task gửi thông báo quan trọng phải xếp sau. Tách pool có thể tạo ranh giới tài nguyên:

- `cpuExecutor`: số worker tương ứng CPU, queue ngắn, phép tính có deadline.
- `outboundIoExecutor`: cho blocking calls, giới hạn thread và connection.
- `mailExecutor`: công việc ngoài đường trả lời request, nhưng vẫn có rejection/timeout/monitor.
- `maintenanceScheduler`: kích hoạt theo lịch; việc nặng nộp tới worker pool phù hợp.

Đổi lại, quá nhiều pool khiến tổng số thread, queue và memory khó quản lý. Mỗi pool phải có **ngân sách tài nguyên** và chủ sở hữu rõ ràng; chỉ tách khi có lý do về workload, ưu tiên hoặc fault isolation.

## 8. Scheduling: khi nào chạy và chạy bao nhiêu lần?

Dùng `TaskScheduler`/`@Scheduled` khi trigger theo thời gian: quét dữ liệu định kỳ, refresh cache, gửi báo cáo nhỏ. Chọn một trong các cách phổ biến:

- `fixedDelay`: đo thời gian chờ sau khi lượt trước kết thúc rồi mới kích hoạt lần kế tiếp; không cố giữ điểm đầu các lượt cách đều nhau.
- `fixedRate`: lịch kích hoạt theo nhịp đều đặn; nếu task chậm hoặc không đủ worker, thời điểm thực tế có thể trễ. Không khẳng định một tác vụ đơn có thể tự động overlap với chính nó trong mọi implementation.
- `cron`: kích hoạt theo lịch biểu. Cần quan tâm timezone, giờ mùa hè (nếu áp dụng), restart và việc bỏ lỡ lịch.
- `TaskScheduler.schedule(...)`: nộp callback theo `Instant`, `Trigger` hoặc chu kỳ qua API, thay vì annotation cố định.

`ThreadPoolTaskScheduler` thuộc nhóm Spring-managed scheduler. Số scheduler worker quá nhỏ có thể làm một callback chậm trì hoãn callback khác. Không mặc định cho rằng tăng kích thước scheduler là đủ khi callback giữ connection lâu; có thể cần **scheduler nhẹ chỉ điều phối**, còn công việc được xử lý bởi worker pool giới hạn.

Một fragment cấu hình Spring (không phải chương trình Java chạy độc lập):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
@EnableScheduling
class SchedulingConfig {
    @Bean
    ThreadPoolTaskScheduler maintenanceScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("maintenance-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(15);
        return scheduler;
    }
}
```

Cấu hình trên có ý nghĩa trong Spring context và cần test overlap/shutdown. Nó không bảo đảm các job chạy đúng một lần trong toàn cụm. Mỗi replica của ứng dụng có bean `@Scheduled` riêng, nên khi deploy ba instance có thể có ba lần thực thi cùng lịch. Nếu yêu cầu đúng một lần trên toàn hệ thống, hãy dùng scheduler tập trung, leader election, lease/lock phân tán hoặc hàng đợi có consumer coordination phù hợp; thiết kế job idempotent vì hệ phân tán vẫn có thể retry hoặc gặp failure giữa chừng.

**Không nhầm scheduler với job queue bền vững.** Lịch trong memory bị ảnh hưởng bởi JVM restart và node outage. Công việc tài chính hoặc nghiệp vụ không được phép mất cần có kế hoạch ghi nhận trạng thái, retry, kiểm soát duplicate và theo dõi tồn đọng.

## 9. Reactive / WebFlux: đừng chặn event-loop

Trong WebFlux, reactor pipelines hỗ trợ mô hình non-blocking khi toàn bộ thao tác I/O tương ứng không chặn. Nếu một endpoint reactive trực tiếp gọi một JDBC/HTTP client blocking trên event-loop, thread dùng chung có thể bị giữ chờ, ảnh hưởng nhiều request.

Nếu có driver/client reactive tương thích, ưu tiên sử dụng theo pipeline. Nếu chưa thể thay blocking dependency, bọc công việc bằng `Mono.fromCallable(...)` và `subscribeOn(Schedulers.boundedElastic())` tại boundary phù hợp:

```java
// Fragment: giả định đang ở service dùng Reactor và blockingClient đã tồn tại.
Mono<Result> result = Mono.fromCallable(
        () -> blockingClient.fetch(id))
    .subscribeOn(Schedulers.boundedElastic());
```

Đoạn trên cần import Reactor, kiểu `Result` và client trong project, nên **không** phải chương trình Java độc lập. `boundedElastic` là scheduler hữu hạn cho công việc blocking; nó không làm blocking API trở thành non-blocking thực sự và vẫn có giới hạn queue/tài nguyên. Với throughput lớn, phải kiểm tra backpressure, connection pool, timeout và mức concurrency downstream.

Không mặc nhiên chuyển mọi Reactor operator qua `@Async` hoặc `parallel()`. `parallel()` là lựa chọn cho công việc CPU thích hợp, còn `boundedElastic()` thường dành cho adapter tới code blocking; việc sử dụng sai làm tăng context switching mà không nâng throughput.

## 10. Môi trường Spring Boot, Java và container: kiểm tra cấu hình đang thực sự có hiệu lực

Spring Boot có cơ chế auto-configuration cho task execution/scheduling, nhưng hành vi phụ thuộc phiên bản, bean executor đang có và các thành phần tích hợp với nó. Với ứng dụng có cấu hình tùy chỉnh:

- Xác định executor nào thật sự được `@Async` chọn, có `@Async("name")` hoặc `AsyncConfigurer` nào không.
- Xác định bean executor nào Spring MVC/WebFlux, WebSocket, GraphQL hoặc thành phần khác dùng; **không** suy ra chúng đều dùng cùng một bean tùy chỉ vì có một bean `Executor` trong context.
- Xem application profile, environment variables và cấu hình ghi đè khi chạy local/test/staging/production.
- Xem CPU quota/memory limit thật của container, không lấy duy nhất số lõi máy chủ vật lý.
- Xem JDK (17/21+), phiên bản Spring/Boot và trạng thái bật virtual threads. Các thuộc tính chỉnh pool có thể không còn cùng ý nghĩa nếu executor được thay bằng virtual-thread strategy.

Ví dụ properties của Spring Boot có thể cấu hình pool auto-configured khi phù hợp, **không** bảo đảm áp dụng cho `@Bean` `ThreadPoolTaskExecutor` do chính bạn tạo:

```yaml
spring:
  task:
    execution:
      pool:
        core-size: 4
        max-size: 8
        queue-capacity: 64
      thread-name-prefix: app-task-
    scheduling:
      pool:
        size: 2
```

Kiểm chứng bean được tạo trong context và metric thực tế; việc một property có mặt trong YAML không chứng minh nó đang chi phối executor mà method đã sử dụng. Nếu ứng dụng có nhiều executor, ưu tiên tên bean/qualifier rõ ràng hơn suy luận dựa trên mặc định.

**Java 21 và virtual threads:** với các phiên bản Boot hỗ trợ, `spring.threads.virtual.enabled=true` cho phép chọn execution strategy dựa trên virtual threads; các pool configuration của platform threads có thể không còn tác dụng như trước. Quyết định kích hoạt cần bao gồm khả năng library tương thích, hành vi blocking, lượng ThreadLocal, tải database và cơ chế giữ JVM sống cho background tasks.

### 10.1. Trong Jakarta EE application server

Nếu hạ tầng quản lý thread qua container, việc tự tạo `new Thread` hoặc một `Executors.newFixedThreadPool` không được quản lý có thể vi phạm quy ước về classloader, context và shutdown. Spring có adapter cho managed executor/scheduler (ví dụ `DefaultManagedTaskExecutor` và `DefaultManagedTaskScheduler` khi môi trường tương ứng hỗ trợ); đây là bài toán ownership, không phải chỉ đổi API.

### 10.2. Trong test

Một executor chạy đồng bộ như `SyncTaskExecutor` giúp kiểm tra logic có tính xác định khi thread boundary không phải đối tượng test. Tuy nhiên test lỗi concurrency phải chạy bằng executor bất đồng bộ thật, latch/barrier và timeout rõ ràng. Không dùng test đồng bộ để tuyên bố race condition đã được giải quyết.

### 10.3. Trong môi trường container nhiều replica

Giới hạn tổng khả năng của upstream cần tính trên **toàn hệ thống**: nếu một service có 10 replica và mỗi instance cho phép 50 concurrent DB calls, tổng tối đa lý thuyết có thể là 500 concurrent calls, lớn hơn connection capacity của DB. Per-process semaphore chỉ hạn chế từng instance; muốn giới hạn toàn cụm cần kiến trúc admission/rate limiting tương ứng hoặc điều chỉnh tổng ngân sách theo replica.

## 11. Ước lượng năng lực: throughput, latency, concurrency, queue

Đừng cấu hình “max = 200 thread” mà không có dữ liệu. Ba đại lượng nền tảng:

- **Arrival rate** (λ): task/giây đến hệ thống.
- **Residence/response time** (W): thời gian trung bình mỗi task ở trong hệ thống (có thể gồm queue và service).
- **Số task đang hiện diện trung bình** (L): với hệ ổn định và cùng phạm vi đo, Little's Law cho `L = λ × W`.

Ví dụ: 100 yêu cầu/giây, thời gian một yêu cầu trong vùng đang xem là 0,4 giây, thì **trung bình khoảng 40 yêu cầu** tồn tại đồng thời trong vùng đó. Điều này **không** tự suy ra cần 40 CPU threads: nếu chúng phần lớn chờ I/O, số thread/virtual threads/connection cần quản lý khác nhau; nếu toàn bộ là CPU-bound, năng lực CPU sẽ là rào cản.

### 11.1. Một quy trình capacity planning tối thiểu

1. Đo p50/p95/p99 service time và queue wait trong từng nhóm tác vụ, tách CPU và blocking wait.
2. Đo arrival rate trung bình và peak, burst duration, deadline và khả năng chịu lỗi.
3. Đo CPU hiệu dụng, memory, database connection pool, outbound HTTP connection limit và quota API.
4. Đặt trần concurrency cho **điểm nghẽn thực**, rồi chọn pool/virtual-thread strategy tương ứng.
5. Chọn queue capacity theo burst có thể hấp thụ trong budget chờ; không để queue lớn hơn mức làm deadline hết hạn.
6. Đặt rejection policy, fallback và retry/backoff; kiểm tra dữ liệu có idempotent hay không.
7. Load test bình thường, burst và thời gian dài; đo throughput, p95/p99 latency, queue occupancy, active count, reject, timeout, error, CPU và memory.
8. Kiểm tra shutdown, deploy rolling, mạng chậm và downstream failure; điều chỉnh theo kết quả.

Một hàng đợi chứa 1.000 task với khả năng xử lý 20 task/giây sẽ cần khoảng 50 giây chỉ để giải phóng số task đó nếu không có task mới và tốc độ không đổi. Nếu caller chỉ chờ được 2 giây, queue lớn như vậy không giải quyết vấn đề. Dùng mô hình đơn giản này để phát hiện cấu hình vô lý, rồi xác thực bằng load test thực.

### 11.2. Công thức gần đúng cho CPU và blocking I/O

Đối với CPU-bound, điểm bắt đầu thường là mức concurrency tương đương số core hiệu dụng (có hiệu chỉnh cho tác vụ khác và JVM), sau đó đo. Với blocking I/O, số thread cần có thể lớn hơn vì mỗi thread chỉ sử dụng CPU trong một phần thời gian; tuy nhiên giới hạn kết nối và latency của hệ thống đích thường quyết định trần hợp lý.

Các công thức kinh nghiệm dựa trên wait/service ratio chỉ là **ước lượng ban đầu**. Không áp dụng cứng nhắc khi task trộn nhiều pha, thread virtual, downstream có rate limit, hoặc queue wait thay đổi lớn dưới tải.

## 12. Chọn theo ưu tiên, độ tin cậy và khả năng cách ly lỗi

Không chỉ phân loại CPU/I/O; ứng dụng còn có nhiều **mức độ quan trọng**.

| Nhóm công việc | Mục tiêu | Mẫu giải pháp |
| --- | --- | --- |
| Xác thực và trả API tương tác | p95 latency thấp, trả lỗi sớm khi quá tải | Đồng bộ ngắn hoặc offload giới hạn; queue nhỏ, timeout rõ |
| Gọi đối tác HTTP blocking | Kiểm soát fan-out và quota | Bounded I/O pool hoặc virtual threads + semaphore/connection pool |
| Tính toán báo cáo nặng | Giữ CPU ổn định, không gây đói request | CPU pool riêng, job ID nếu xử lý lâu |
| Email/thông báo không cần trong response | Chấp nhận trả kết quả trước khi gửi | Job queue bền vững nếu không được mất; worker có retry |
| Refresh cache định kỳ | Chấp nhận trễ một ít | Scheduler, deadline, tránh các lượt refresh chồng không cần thiết |
| Kiểm toán/thanh toán/bước nghiệp vụ quan trọng | At-least-once với xử lý duplicate an toàn và audit | Persistence + transactional outbox/queue/workflow khi phù hợp |

**Isolation:** nếu job đòi hỏi khả năng phục hồi và mức ưu tiên khác nhau, chia tài nguyên theo nhóm, hoặc dùng consumer process riêng. Không để việc tải ảnh ồ ạt chiếm hết connection pool, rồi gây timeout cho các giao dịch quan trọng.

**Task priority:** `ThreadPoolExecutor` mặc định không biến một FIFO queue thành bộ lập lịch nghiệp vụ có thứ tự ưu tiên tuyệt đối; nếu có priority queue cũng cần ngăn starvation, bảo đảm thread safety và phù hợp cancellation/metrics. Thường đơn giản hơn khi tách queue/pool theo criticality đã được xác định.

## 13. Vòng đời executor và shutdown có kiểm soát

Quyền sở hữu executor quyết định ai được gọi shutdown:

| Chủ sở hữu | Cách dùng | Đóng khi nào |
| --- | --- | --- |
| Spring-managed `@Bean ThreadPoolTaskExecutor` | Inject/`@Async` theo tên và để Spring điều phối | Khi application context đóng theo lifecycle tích hợp |
| Spring-managed `ThreadPoolTaskScheduler` | Trigger lịch bằng cấu hình Spring | Khi context đóng, với chính sách hoàn tất/hủy đã xác định |
| Executor do một phương thức tạo riêng | Chỉ dùng trong công việc cục bộ có phạm vi rõ | Chính phương thức phải `shutdown`/await trong `finally` |
| Container-managed executor của Jakarta EE | Dùng thông qua abstraction được cấp | Lifecycle thuộc container; ứng dụng không tự đóng shared resource |
| Queue/worker ngoài process | Publish job và nhận kết quả/trạng thái qua giao thức | Lifecycle do broker/worker manager/cluster kiểm soát |

Quy trình shutdown lý tưởng với in-memory executor:

1. **Ngừng nhận việc mới** hoặc chuyển sang trạng thái not-ready; xử lý rejection một cách có chủ đích.
2. **Đặt giới hạn chờ** cho tác vụ đã nhận; chờ những công việc cần hoàn thành trong grace period.
3. **Yêu cầu hủy hợp tác** cho task có thể bỏ qua: interrupt, cancellation, timeout của client/DB và đóng tài nguyên.
4. **Ghi nhận công việc dở dang** nếu nghiệp vụ cần retry; nếu chỉ ở RAM thì không thể bảo đảm phục hồi sau crash.
5. **Đợi theo deadline**, ghi metric/log tình trạng cuối rồi thoát; hạ tầng có thể kết thúc process sau grace period.
6. **Kiểm tra restart**: không chạy trùng job đã hoàn tất, không bỏ sót job chưa hoàn tất; có cơ chế idempotency/deduplication.

Spring-managed executor không nên bị mỗi service gọi `shutdown()` giữa chừng. Nếu nhiều consumer dùng cùng bean executor, một consumer tự đóng nó sẽ gây lỗi nộp task cho các consumer khác.

### 13.1. Java 17+: ví dụ shutdown và hủy hợp tác

Tệp `CooperativeShutdownDemo.java` minh họa gửi tín hiệu interrupt qua `Future.cancel(true)` và đợi executor kết thúc:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeShutdownDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        AtomicBoolean observedInterrupt = new AtomicBoolean(false);

        try {
            Future<?> job = executor.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                } catch (InterruptedException e) {
                    observedInterrupt.set(true);
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            job.cancel(true);
        } finally {
            executor.shutdown();
        }

        boolean terminated =
                executor.awaitTermination(5, TimeUnit.SECONDS);
        System.out.println("terminated=" + terminated);
        System.out.println("interruptSeen=" + observedInterrupt.get());
    }
}
```

```bash
javac CooperativeShutdownDemo.java
java CooperativeShutdownDemo
```

Kết quả trong môi trường chạy bình thường, khi worker phản hồi interrupt trong thời hạn năm giây:

```text
terminated=true
interruptSeen=true
```

`cancel(true)` chỉ yêu cầu interruption; mã task quyết định phản hồi. Nếu task bị kẹt ở I/O không hỗ trợ interruption, hoặc không kiểm tra trạng thái, có thể không dừng trong thời gian kỳ vọng. `awaitTermination` trả boolean để caller phân biệt đã kết thúc và còn task; không nên bỏ qua trường hợp `false` trong production.

### 13.2. Khi nào cần job bền vững thay vì executor trong process?

Chọn durable job khi có ít nhất một điều kiện:

- Job bắt buộc hoàn thành dù JVM/process restart.
- Phải retry sau khi DB/API bên ngoài tạm thời lỗi.
- Cần xem trạng thái `PENDING/RUNNING/SUCCEEDED/FAILED`, kiểm toán hoặc làm lại một cách chủ đích.
- Có thể mất nhiều phút/giờ hoặc lớn hơn deadline HTTP.
- Scale worker độc lập với web app hoặc điều tiết tốc độ tiêu thụ.

Kịch bản thích hợp: request ghi nhận công việc (hoặc transactional outbox), phản hồi `202 Accepted` với job ID, worker nhận job từ hệ thống bền vững, cập nhật trạng thái và dùng idempotency key để chống tác động lặp. “Nhận được 202” chỉ có nghĩa server **đã nhận yêu cầu theo hợp đồng đã định**; nếu chưa ghi bền vững thì không được hứa job chắc chắn sống qua restart.

## 14. Timeout, retry, backpressure và cancellation gắn với lựa chọn executor

Nhiều sự cố bắt nguồn từ việc offload mà không có **deadline**:

- `Future.get(timeout, unit)` chỉ giới hạn thời gian **thread gọi chờ**; hết hạn không tự động hủy worker. Quyết định `cancel(true)` cần có chính sách rõ.
- `CompletableFuture.orTimeout(...)` đặt trạng thái completion của future; không tự bảo đảm dừng thao tác I/O vật lý đã bắt đầu. Vẫn phải cấu hình timeout trong client/driver và cancellation nếu API hỗ trợ.
- HTTP client/DB timeout thường cần ít nhất connect/read/total deadline phù hợp; queue wait cũng phải nằm trong ngân sách độ trễ tổng.
- Retry không giới hạn trong task đang giữ thread có thể nhân tải lên đúng lúc downstream đang hỏng. Dùng bounded retry với backoff/jitter và idempotency khi side effect có thể xảy ra.
- `Semaphore`/rate limiter áp dụng ở boundary downstream hữu ích ngay cả khi executor có hàng nghìn virtual threads.
- Rejection policy là thành phần của API contract: task có thể không được nhận; cần quyết định trả lỗi, retry hay persist, không âm thầm làm mất việc.

Nếu thời gian còn lại của deadline đã nhỏ hơn ước lượng queue wait, nhận task rồi để nó chết vì timeout trong queue là cách lãng phí tài nguyên. Backpressure và fail-fast có thể bảo vệ p95 latency tốt hơn việc cho mọi task vào queue.

### 14.1. Không chuyển transaction hoặc request state một cách vô tình

`@Async` thường đổi thread; Spring transaction context và request-scoped state gắn thread caller không tự động có mặt ở worker. Tránh chuyển nguyên `HttpServletRequest`, persistence entity đang được quản lý hoặc DTO mutable sang background task lâu dài. Thay vào đó truyền ID/immutable snapshot cần thiết; task mở transaction riêng tại boundary của nó khi cần.

MDC/trace context và security identity cần propagation có chủ đích, kiểm thử đường cleanup khi worker thread được tái sử dụng. Spring có `TaskDecorator` và các tích hợp context propagation thích hợp, nhưng decorator không thay thế ownership và không bảo đảm tự động chuyển mọi thread-local/transaction.

## 15. Kiểm thử đúng ba trục: tải, môi trường, vòng đời

Một cấu hình chỉ được xem là phù hợp sau khi kiểm tra hành vi dưới điều kiện của chính hệ thống.

### 15.1. Kiểm thử tải

- **Steady-state:** arrival rate thấp hơn khả năng xử lý; queue có ổn định, p95 có đạt SLO?
- **Burst:** tăng lưu lượng đột ngột; queue đạt đỉnh bao nhiêu, rejection xảy ra khi nào?
- **Overload dài:** arrival rate cao hơn capacity; hệ thống có fail-fast hoặc giữ memory ổn định không?
- **Downstream chậm/mất kết nối:** timeout có ngăn task giữ worker vô hạn không?
- **CPU quota giảm:** ứng dụng có đang tạo quá nhiều worker so với CPU thực không?
- **Multi-replica:** tổng connection, rate-limit và scheduler duplicate được kiểm soát chưa?

### 15.2. Kiểm thử môi trường

Xác minh executor **thực sự được dùng** bằng bean name, thread-name prefix, metrics và quan sát thread dump. Với Spring Boot, chạy dưới đúng profile và phiên bản runtime. Với WebFlux, dùng công cụ phát hiện blocking trên event-loop khi thích hợp. Với virtual threads, đo cả tốc độ I/O, memory, ThreadLocal và giới hạn downstream.

### 15.3. Kiểm thử vòng đời

- Đóng Spring context khi còn queue và task chạy; task nào hoàn tất/hủy, có shutdown đúng thời hạn?
- Thử nộp task sau khi executor đã bắt đầu shutdown; caller nhận rejection ra sao?
- Gửi SIGTERM / rolling update trong môi trường tương tự production; kiểm tra grace period và readiness.
- Restart trong khi durable job đang chạy; job có được khôi phục/retry và có tác động lặp không?
- Test cancellation với `CountDownLatch`/barrier có timeout; không dựa vào `Thread.sleep` để đoán thứ tự.
- Với `@Async`, xác minh lời gọi thực sự đi qua proxy và exception được quan sát.

Metric nên gắn **tên nhóm công việc/executor** và trace ID khi phù hợp: active worker, pool size, queue depth, queue wait, tasks completed, rejected count, task duration, error/timeout/cancelled, CPU, heap, GC và độ trễ p95/p99. Không để log/metric rò thông tin cá nhân trong payload.

## 16. Các lựa chọn đối chiếu theo tình huống

| Tình huống | Cách thực thi đáng thử trước | Điều kiện bắt buộc |
| --- | --- | --- |
| Validate DTO và tính phí đơn giản trong request | Đồng bộ | Độ trễ nhỏ, invariant/transaction rõ |
| Gọi ba REST API blocking độc lập trong request MVC | I/O executor có giới hạn hoặc virtual threads với API tổng hợp kết quả | Timeout từng API, hạn mức kết nối, deadline request |
| Mã hóa hàng nghìn file lớn | CPU pool riêng, công việc có thể phân lô | Giới hạn CPU/memory và queue, cancellation |
| Ứng dụng WebFlux dùng reactive HTTP client | Reactor non-blocking pipeline | Không block event-loop, backpressure |
| WebFlux phải dùng SDK blocking tạm thời | Adapter `boundedElastic` | Giới hạn blocking, bảo vệ downstream và kế hoạch thay SDK |
| Gửi email sau khi API trả 202, không được mất | Durable queue/job worker | Persist trước khi xác nhận, retry, idempotency |
| Đồng bộ cache vào lúc 2 giờ sáng trên ba replica | Scheduler có điều phối toàn cụm | Không chạy ba bản sao ngoài ý muốn, job idempotent |
| Ứng dụng command-line xử lý một danh sách rồi thoát | Executor local hữu hạn + await | Đợi kết quả, đóng executor, exit code phản ánh lỗi |
| Jakarta EE server cung cấp managed executor | Managed executor/scheduler | Tuân thủ lifecycle/container context |
| Test unit muốn hành vi xác định | Executor đồng bộ | Vẫn có test concurrency độc lập |

## 17. Các sai lầm thường gặp

| Sai lầm | Vì sao có hại | Quy tắc thay thế |
| --- | --- | --- |
| “Tất cả xử lý lâu đều dùng `@Async`.” | Không có job ID, timeout, kết quả hoặc durability; lỗi có thể bị bỏ qua | Xác định hợp đồng với caller và thời gian sống trước |
| “`maxPoolSize` đủ lớn thì tự mở nhiều thread.” | Queue dài có thể giữ pool ở `corePoolSize` | Hiểu cơ chế core → queue → max → rejection |
| “Queue không giới hạn giúp tránh lỗi.” | Dời lỗi thành latency/memory và task hết deadline | Bounded queue, admission/rejection rõ |
| “Virtual threads không cần giới hạn concurrency.” | DB/API quota, heap và file descriptor vẫn hữu hạn | Semaphore/connection pool/rate limit tại nguồn tài nguyên |
| “Đã chuyển sang async là request không block.” | Caller vẫn có thể `get()/join()` ngay | Thiết kế async end-to-end hoặc trả job ID |
| “`@Async` luôn chạy khác thread.” | Self-invocation có thể bỏ qua proxy | Kiểm tra call path và bean executor |
| “Tăng scheduler pool đảm bảo mỗi cron chạy đúng một lần toàn cụm.” | Mỗi replica có scheduler riêng | Điều phối phân tán hoặc scheduler ngoài JVM |
| “`@Scheduled` là queue bền vững.” | Restart/stop có thể làm mất lần thực thi | Persist job nếu nghiệp vụ đòi hỏi |
| “`shutdownNow()` chắc chắn dừng mọi task.” | Interrupt mang tính hợp tác | Timeout, cancellation và cleanup ở task |
| “Cấu hình YAML chắc chắn áp dụng cho pool hiện tại.” | Có thể bị bean tùy chỉnh/phiên bản/virtual threads thay đổi | Kiểm chứng bean runtime và metric |
| “`Future.get(timeout)` đã dừng I/O.” | Hết thời gian chờ không phải hủy thao tác | Timeout trong client, cancellation, deadline tổng |
| “Một pool chung là đơn giản và đủ.” | Heavy tasks gây starvation cho nghiệp vụ quan trọng | Cách ly pool/queue theo priority và ngân sách |

## 18. Bài thực hành: thiết kế executor cho một hệ thống ba loại việc

Giả sử ứng dụng Spring có: (A) endpoint cần gọi API sản phẩm mất trung bình 200 ms, (B) báo cáo CPU nặng mất vài giây, (C) job đồng bộ trạng thái đối tác chạy định kỳ và phải tiếp tục sau restart.

### Yêu cầu thực hiện

1. Ghi bảng cho từng task: CPU hay I/O, concurrency peak, deadline, quota downstream, kết quả, lỗi và owner.
2. Đề xuất đường thực thi cho A: request blocking, MVC async hay end-to-end reactive; chọn bounded I/O pool/virtual threads phù hợp và giới hạn connection; giải thích caller chờ hay nhận future.
3. Đề xuất B: CPU pool riêng, queue hữu hạn, trả job ID nếu vượt HTTP deadline, test CPU quota và cancellation.
4. Đề xuất C: scheduler chỉ kích hoạt, durable job record và worker có cơ chế retry; tránh duplicate khi nhiều replica.
5. Đặt cấu hình khởi đầu mang tính giả thuyết: core/max/queue hoặc virtual-thread strategy, timeout, queue rejection, maximum downstream concurrency và shutdown grace.
6. Tạo kịch bản load steady-state, burst, một downstream treo, rolling restart và hai request cạnh tranh cùng pool.
7. Thu metric: queue wait, active worker, reject, error, p95/p99, CPU, số connection; điều chỉnh cấu hình dựa trên bottleneck thực.
8. Mô tả hợp đồng khi task bị từ chối: API trả mã gì, job có được lưu trước không, client có thể retry an toàn không.
9. Xác minh shutdown: không nhận việc mới khi not-ready; task đã nhận được xử lý/hủy theo SLA; không mất durable job.

### Tiêu chí đạt

- [ ] Tôi giải thích được vì sao “càng nhiều thread càng tốt” là sai với CPU-bound và downstream có quota.
- [ ] Tôi chọn được giữa synchronous, bounded pool, virtual threads, scheduler, Reactor và durable worker dựa trên đặc tính task.
- [ ] Tôi hiểu `corePoolSize`/`maxPoolSize`/`queueCapacity` và thời điểm reject.
- [ ] Tôi không dùng queue vô hạn để che quá tải hoặc để job vượt deadline.
- [ ] Tôi định nghĩa được timeout, cancellation, kết quả/lỗi và chính sách retry trước khi triển khai.
- [ ] Tôi biết sự khác nhau giữa môi trường MVC, WebFlux, application server và nhiều replica.
- [ ] Tôi xác định đúng ai sở hữu executor và quy trình graceful shutdown/restart.
- [ ] Tôi kiểm chứng cấu hình runtime thay vì suy từ YAML hoặc tên bean.
- [ ] Tôi có load test và failure test cho quyết định chọn executor.

**Điểm then chốt:** executor là một phần của **hợp đồng tài nguyên và vòng đời**. Cách thực thi phù hợp phải vừa bảo vệ CPU, connection và deadline dưới tải, vừa khớp mô hình thread của môi trường, vừa có đường xử lý hoàn tất, lỗi, quá tải, hủy và restart được kiểm chứng.

## 19. Tài liệu chính thức để đối chiếu theo phiên bản đang dùng

- Spring Framework Reference — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `TaskScheduler`, `@Async`, `@Scheduled` và các lựa chọn implementation.
- Spring Framework API — [ThreadPoolTaskExecutor 6.1](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): default queue/pool, tham số core/max/capacity và lifecycle.
- Spring Boot Reference — [Task Execution and Scheduling (3.4)](https://docs.spring.io/spring-boot/3.4/reference/features/task-execution-and-scheduling.html): nguyên tắc auto-configuration và phân biệt executor dùng bởi các thành phần.
- Spring Boot Reference — [Virtual Threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html): yêu cầu Java 21+, cấu hình và các vấn đề lifecycle/keep-alive.

Tài liệu Spring/Boot và JDK có thể thay đổi theo phiên bản. Khi triển khai, kiểm tra chính xác release đang dùng thay vì lấy mặc định từ tài liệu của một release khác.
