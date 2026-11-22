# Tránh tạo executor không có cơ chế thu hồi trong Spring Boot

## 1. Bài toán: executor tạo được nhưng ai sẽ đóng?

Một ứng dụng Spring Boot thường có nhiều tác vụ không chạy trực tiếp trên luồng request: gửi thông báo, xử lý file, gọi API đối tác, thực thi `@Async`, job `@Scheduled`, consumer của message broker hoặc batch nền. Các công việc ấy cần một cơ chế thực thi như `Executor`, `ExecutorService`, `TaskExecutor` hoặc `TaskScheduler`.

Lỗi dễ mắc là **tạo một thread pool rồi không xác định ai chịu trách nhiệm dừng nó**:

```java
// PHẢN VÍ DỤ: method nghiệp vụ tạo pool mới nhưng không đóng.
public void handleRequest() {
    ExecutorService pool = Executors.newFixedThreadPool(4);
    pool.submit(() -> doWork());
}
```

Đây là snippet minh họa, `doWork()` chưa được định nghĩa. Nếu mỗi request gọi method này, mỗi lần lại tạo một pool riêng. Các thread mặc định của `Executors.newFixedThreadPool` không phải daemon thread; khi pool đã tạo worker, thread thường tồn tại để chờ công việc tiếp theo. **Không gọi `shutdown()` có thể giữ thread và tài nguyên vô thời hạn**, thậm chí khiến JVM không kết thúc như mong đợi.

Tình huống còn nguy hiểm hơn: một background task giữ kết nối database, HTTP client, file handle hoặc tài nguyên của bean khác. Khi `ApplicationContext` đang đóng, executor không được quản lý có thể tiếp tục chạy tác vụ sau khi tài nguyên đó đã bị destroy.

**Nguyên tắc trung tâm:** mọi executor phải có **owner**, vòng đời khởi tạo, chính sách nhận tác vụ, chính sách hủy/hoàn thành tác vụ đang chạy, timeout dừng và cách xử lý lỗi. Trong Spring Boot, ưu tiên **executor do Spring quản lý**; nếu phải tạo trực tiếp từ JDK, cần đóng có kỷ luật.

Bài này dùng **Java 17+, Spring Boot 3.3.x, Spring Framework 6.1.x**. Các ví dụ gồm một chương trình Java độc lập và một ứng dụng Spring Boot thực hành hoàn chỉnh.

## 2. “Thu hồi executor” gồm những gì?

Đóng một executor không chỉ là gọi một method tên `close`. Cần quản lý cả vòng đời:

1. **Tạo:** ai xây dựng pool, thread factory, số thread tối đa và queue?
2. **Sở hữu:** pool thuộc request, một bean Spring hay một process?
3. **Cấp việc:** service nào được phép submit và khi nào phải dừng submit?
4. **Áp lực tải:** queue có giới hạn, rejection policy rõ ràng không?
5. **Dừng nhận tác vụ:** khi shutdown, ngăn công việc mới vào pool.
6. **Hoàn tất/huỷ:** cho tác vụ đang chạy bao lâu, tác vụ chờ được xử lý ra sao?
7. **Giải phóng:** thread có kết thúc, tài nguyên trong task có được đóng?
8. **Quan sát:** có metrics active threads, queue depth, rejected tasks và shutdown timeout không?

Một pool có thể **không rò object heap** nhưng vẫn gây vấn đề lớn vì giữ thread, thread-local, classloader reference, connection hoặc I/O đang mở. Với ứng dụng web được triển khai lại trong cùng JVM hoặc test tạo nhiều `ApplicationContext`, pool không được đóng còn có thể giữ lại classloader cũ, làm khó GC và gây tác vụ ngoài vòng đời dự kiến.

### 2.1. Không nhầm pool reuse với pool leak

**Reuse pool** là mong muốn: một executor được tạo có chủ đích cho một phạm vi, nhiều công việc dùng chung và cuối cùng được đóng.

**Leak** xảy ra khi pool không còn hữu ích hoặc không còn owner quản lý nhưng vẫn tồn tại và giữ tài nguyên. Một pool singleton sống suốt vòng đời ứng dụng không phải leak; pool đó thành vấn đề nếu `ApplicationContext.close()` đã xảy ra mà nó vẫn tiếp tục sống.

## 3. Các API Java cần phân biệt

Java cung cấp `Executor` và `ExecutorService`:

- `Executor.execute(Runnable)`: gửi một công việc; bản thân interface `Executor` **không có contract shutdown**.
- `ExecutorService.submit(...)`: gửi tác vụ, nhận `Future` để theo dõi kết quả/exception/cancellation.
- `ExecutorService.shutdown()`: **ngừng nhận tác vụ mới**, cho tác vụ đã submit cơ hội hoàn thành, rồi pool chấm dứt. Lệnh này **không chờ** tác vụ xong.
- `ExecutorService.shutdownNow()`: cố ngừng tác vụ đang chạy (thường qua `interrupt`), không bắt đầu những tác vụ còn chờ, trả về danh sách tác vụ chưa bắt đầu. Đây là **best effort**, không bảo đảm mọi task dừng lập tức.
- `ExecutorService.awaitTermination(timeout, unit)`: **chờ có giới hạn** cho đến khi pool terminated sau shutdown, trả `true` nếu đã terminated hoặc `false` nếu hết hạn.
- `isShutdown()`: đã yêu cầu shutdown chưa? Không có nghĩa mọi task xong.
- `isTerminated()`: sau shutdown, mọi task đã kết thúc và pool không còn đang chạy công việc?
- `Future.cancel(true)`: yêu cầu hủy task tương ứng, có thể interrupt nếu đang chạy; không bảo đảm task hợp tác.

### 3.1. Bảng trạng thái

| Tình huống | `isShutdown()` | `isTerminated()` | Ý nghĩa |
| --- | --- | --- | --- |
| Pool đang nhận việc | `false` | `false` | Có thể submit. |
| Vừa gọi `shutdown()`, task còn đang chạy | `true` | `false` | Không nhận task mới, vẫn đang hoàn tất task cũ. |
| Gọi `shutdownNow()` nhưng task không chịu dừng | `true` | `false` | Không thể mặc định đã dừng tất cả. |
| Pool đã hoàn tất shutdown | `true` | `true` | Tác vụ cũ đã kết thúc và pool terminated. |

**Lưu ý Java 17:** `ExecutorService` **chưa** có `AutoCloseable.close()` theo contract Java 17 để có thể mặc định viết `try (ExecutorService pool = ...)`. Hãy dùng `try/finally` và tự `shutdown`/`awaitTermination`; đừng chép ví dụ của các phiên bản JDK mới hơn vào dự án khóa Java 17 mà không kiểm tra.

### 3.2. Interrupt là hợp đồng hợp tác

`shutdownNow()` có thể gọi `Thread.interrupt()` trên worker. Nếu task:

- Bị chặn bởi `Thread.sleep`, `BlockingQueue.take` hoặc nhiều API hỗ trợ interrupt, nó có thể ném `InterruptedException`.
- Đang xử lý một thư viện I/O không hỗ trợ interrupt đúng cách, nó có thể **tiếp tục chạy**.
- Có vòng lặp vô hạn bỏ qua cờ interrupt, pool có thể **không bao giờ terminated**.

Vì vậy “gọi shutdownNow rồi coi như đã dừng” là kết luận sai. Tác vụ phải được viết để phản hồi cancellation, quản lý timeout riêng và giải phóng tài nguyên trong `finally`/try-with-resources.

## 4. Anti-pattern thứ nhất: tạo pool trong mỗi request

Ví dụ không nên dùng:

```java
@RestController
class ExportController {

    @PostMapping("/exports")
    String startExport() {
        ExecutorService pool = Executors.newCachedThreadPool();
        pool.submit(() -> createExport());
        return "accepted";
    }
}
```

Đây là **minh họa phản diện**, chưa định nghĩa `createExport()` và imports. `newCachedThreadPool` có thể mở rộng số worker theo số task đến; thêm việc tạo **một pool cho mỗi request** khiến thread/resource tăng khó kiểm soát. Trả response không đồng nghĩa task đã hoàn tất hoặc task có nơi lưu trạng thái.

**Hướng sửa:** tạo **một executor được quản lý theo vòng đời ứng dụng**, inject vào service, dùng lại giữa các request; nếu công việc bắt buộc phải tồn tại sau process restart, dùng durable queue/job storage phù hợp thay vì chỉ một thread pool in-memory.

Không đặt `Executors.newFixedThreadPool(...)`, `newScheduledThreadPool(...)` hoặc `newSingleThreadExecutor()` trong controller/service method chỉ vì muốn “chạy nền nhanh”.

## 5. Anti-pattern thứ hai: field executor tự tạo trong bean mà không destroy

```java
@Service
class ReportService {

    private final ExecutorService pool =
            Executors.newFixedThreadPool(4);

    public void submitReport(Runnable task) {
        pool.submit(task);
    }
}
```

Đoạn class trên cũng là **ví dụ chưa an toàn** nếu không có callback destroy. Một bean `@Service` được Spring quản lý **không có nghĩa mọi ExecutorService tự tạo trong field cũng được Spring tự shutdown**. Spring quản lý bean ReportService, nhưng object pool do bạn tự tạo nằm bên trong; muốn cleanup phải viết contract tường minh.

Hai cách phù hợp:

1. Đưa executor ra thành **bean riêng**, để Spring quản lý lifecycle của chính executor.
2. Nếu phải giữ pool private, cho bean sở hữu pool một `@PreDestroy`/`DisposableBean`/destroy method thực hiện shutdown và chờ có giới hạn.

Không viết mọi thứ vào `finalize()` hoặc dựa vào GC: garbage collection không phải cơ chế bảo đảm shutdown thread pool. Thread đang sống còn có thể giữ reference ngăn đối tượng được GC.

## 6. Quy trình shutdown có giới hạn thời gian

Công thức JDK khuyến nghị về mặt ý tưởng:

```text
1. Dừng submit task mới.
2. executor.shutdown(): từ chối task mới, cho phép task đã submit chạy.
3. awaitTermination(timeout): đợi có giới hạn.
4. Nếu hết thời gian:
       executor.shutdownNow(): cố interrupt task đang chạy,
                              lấy danh sách task chưa bắt đầu.
5. Có thể awaitTermination lần nữa trong khoảng ngắn.
6. Nếu vẫn chưa dừng: ghi rõ sự cố, không tuyên bố đã cleanup hoàn toàn.
7. Nếu thread đang chờ bị interrupt:
       gọi shutdownNow, khôi phục interrupted flag.
```

Việc chọn timeout là chính sách nghiệp vụ, không phải hằng số JDK. Một task đọc bộ nhớ 20 ms khác một job ghi file 10 giây hoặc message consumer cần commit offset.

### 6.1. Shutdown theo hai pha không đảm bảo dữ liệu không mất

`shutdown()` đợi công việc đã submit nếu các task hợp tác và có thời gian. Nếu timeout dẫn tới `shutdownNow()`:

- Tác vụ chờ có thể **chưa bao giờ được chạy**.
- Tác vụ đang chạy có thể bị interrupt ở giữa thao tác.
- Một `Future` có thể bị hủy hoặc thất bại.
- Một task đã ghi một phần dữ liệu bên ngoài có thể để lại trạng thái trung gian.

Nếu yêu cầu không mất tác vụ, cần thiết kế **persistent queue, checkpoint, idempotency key, transaction hoặc retry có kiểm soát**. ExecutorService in-memory không phải hệ thống đảm bảo exactly-once delivery.

### 6.2. Đừng chờ vô hạn trong shutdown hook

Một `awaitTermination(Long.MAX_VALUE, ...)` có thể làm tiến trình không kết thúc vì một task bị kẹt hoặc một dependency không phản hồi. Trong Kubernetes/container, thời hạn `terminationGracePeriodSeconds` có thể cắt ngang trước khi ứng dụng hoàn tất dọn dẹp. Chọn timeout hữu hạn và quan sát khi quá hạn.

## 7. Ví dụ Java 17 hoàn chỉnh: pool có owner và cleanup

Ví dụ sau **không cần Spring**. Nó dùng `ThreadPoolExecutor` với queue hữu hạn, nhận một tác vụ, lấy kết quả bằng `Future` rồi shutdown có giới hạn thời gian trong `finally`.

**File:** `ExecutorShutdownDemo.java`

```java
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class ExecutorShutdownDemo {

    private static final AtomicInteger NEXT_ID = new AtomicInteger();

    public static void main(String[] args) throws Exception {
        ThreadFactory factory = task -> {
            Thread thread = new Thread(
                    task, "lesson-worker-" + NEXT_ID.incrementAndGet());
            thread.setDaemon(false);
            return thread;
        };

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1,
                2,
                10, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(4),
                factory,
                new ThreadPoolExecutor.AbortPolicy());

        try {
            Future<String> answer =
                    pool.submit(() -> "processed:42");

            System.out.println("RESULT "
                    + answer.get(5, TimeUnit.SECONDS));
        } finally {
            shutdownAndAwait(pool);
        }

        System.out.println("TERMINATED " + pool.isTerminated());
    }

    private static void shutdownAndAwait(ExecutorService pool) {
        pool.shutdown(); // Từ chối task mới, cho task cũ cơ hội hoàn thành.

        try {
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                List<Runnable> neverStarted = pool.shutdownNow();
                System.err.println(
                        "NOT_STARTED " + neverStarted.size());

                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.err.println("POOL_STILL_RUNNING");
                }
            }
        } catch (InterruptedException ex) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

### 7.1. Lệnh biên dịch và chạy

Với JDK 17+ trong cùng thư mục chứa file:

```bash
javac -encoding UTF-8 ExecutorShutdownDemo.java
java ExecutorShutdownDemo
```

Dòng stdout khi chạy thành công bình thường:

```text
RESULT processed:42
TERMINATED true
```

Tác vụ mẫu rất ngắn, hoàn thành trước shutdown. Vì vậy không có log `NOT_STARTED` trong trường hợp thông thường.

### 7.2. Tại sao ví dụ đáng tin?

- `ThreadPoolExecutor` được tạo **một lần** và giữ trong biến có owner rõ.
- `ArrayBlockingQueue<>(4)` giới hạn số task chờ trong queue.
- `AbortPolicy` từ chối tác vụ mới khi executor đã dừng hoặc không còn chỗ để tiếp nhận.
- `Future.get(5, TimeUnit.SECONDS)` chờ kết quả có timeout; không đợi vô hạn.
- `finally` đảm bảo cleanup khi xử lý kết quả ném exception trong phạm vi sau khi tạo pool.
- `shutdown()` không nhận tác vụ mới.
- `awaitTermination` giới hạn thời gian chờ.
- `shutdownNow()` chỉ là cơ chế escalated best-effort nếu hết hạn.
- `Thread.currentThread().interrupt()` khôi phục cờ interrupt trên thread bị gián đoạn khi đang chờ dừng.

**Không cam kết** rằng một task cố tình bỏ qua interrupt sẽ dừng. Nếu `POOL_STILL_RUNNING` xuất hiện, đó là tình huống lỗi cần chẩn đoán, không phải trạng thái “đã cleanup thành công”.

### 7.3. Vì sao cố tình setDaemon(false)?

Để thấy rõ thread không-daemon có thể giữ JVM sống nếu pool không được shutdown. Nhưng biến thread thành daemon **không phải cách sửa leak**: daemon thread có thể bị JVM kết thúc mà không bảo đảm flush/commit công việc. Cách đúng là quản lý vòng đời và phối hợp shutdown.

### 7.4. Java 17 và try-with-resources

Lưu ý ví dụ **không** viết `try (ExecutorService pool = ...)`. Code khóa Java 17 dùng `try/finally` vì `ExecutorService` ở JDK 17 chưa cung cấp `close()` như một `AutoCloseable`. Khi đọc tài liệu mới hơn của Java, phải đối chiếu API đúng phiên bản đang dùng.

## 8. Đưa executor thành bean có vòng đời Spring

Đối với ứng dụng Spring Boot, cách phổ biến nhất để giảm rủi ro là dùng `ThreadPoolTaskExecutor` làm **singleton bean** được Spring quản lý. Class này thuộc:

```java
org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor
```

Nó triển khai các Spring execution/lifecycle contracts và có shutdown logic qua hạ tầng `ExecutorConfigurationSupport`. Khi context đóng theo contract chuẩn, Spring gọi destroy/lifecycle phù hợp trên bean executor.

Một cấu hình khuyến nghị:

```java
@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {

    @Bean("businessExecutor")
    ThreadPoolTaskExecutor businessExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("business-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);

        return executor;
    }
}
```

Đoạn trên là **class minh họa trong package dự án**, cần import `@Configuration`, `@EnableAsync`, `@Bean`, `ThreadPoolTaskExecutor` và JDK `ThreadPoolExecutor`. Ví dụ hoàn chỉnh ở phần 10 cung cấp đầy đủ imports và các file để chạy.

**Quan trọng:** Khi `ThreadPoolTaskExecutor` được khai báo bằng `@Bean`, Spring container gọi callbacks khởi tạo/hủy liên quan. Không cần tự gọi `initialize()` trong method `@Bean` rồi lại để container initialize một lần nữa. Cũng không cần tự thêm `@PreDestroy` vào chính executor bean để gọi shutdown lần hai.

### 8.1. Ý nghĩa của hai cờ shutdown

Trong Spring Framework 6.1:

- `setWaitForTasksToCompleteOnShutdown(true)`: yêu cầu executor xử lý các task đã được đưa vào queue thay vì chủ động interrupt/loại bỏ chúng ngay khi shutdown. Nó có thể **bỏ qua pha coordinated lifecycle stop** để đợi theo shutdown riêng; không nên coi đây là lựa chọn miễn phí.
- `setAwaitTerminationSeconds(10)`: cho phép thao tác destroy/shutdown chờ tối đa 10 giây trước khi tiếp tục xử lý shutdown của container. Mục đích là giữ các bean/tài nguyên khác còn sống trong khoảng chờ cần thiết.
- Khi thời hạn chờ hết, việc shutdown tiếp tục; **không có bảo đảm mọi task đã hoàn thành**. Nếu task không phản hồi interrupt hoặc có backlog lớn, có thể còn task chạy sau deadline.
- Các setting này thuộc **instance executor** được cấu hình, không tự động điều chỉnh mọi `ExecutorService` do code khác tạo.

Nếu bạn bật `waitForTasksToCompleteOnShutdown(true)`, hãy chú ý chiều dài queue và thời gian chạy của các task: một queue lớn có thể cần tổng thời gian nhiều phút, lớn hơn timeout shutdown bạn đã cho.

### 8.2. Bounded queue quan trọng không kém cleanup

Một `ThreadPoolTaskExecutor` có queue unbounded có thể tích backlog vô hạn. Khi queue chưa đầy, số worker thường chỉ ở mức core pool, nên đặt `maxPoolSize` lớn **không tự bảo đảm pool mở rộng** với queue unbounded.

Đặt `queueCapacity` hữu hạn và `maxPoolSize` hợp lý giúp kiểm soát tài nguyên. Nhưng phải có **rejection policy**: chấp nhận phản hồi lỗi/throttle, retry sau, hoặc đẩy vào durable queue; không âm thầm làm mất task.

`CallerRunsPolicy` có thể chạy task trên thread đã submit khi pool bão hòa, gây **backpressure**, nhưng với HTTP request thread nó có thể kéo dài latency; khi executor đã shutdown, policy này còn có hành vi khác. Không dùng policy này mà không hiểu tải thực tế và yêu cầu phản hồi.

## 9. Spring Boot 3.3 tự cấu hình TaskExecutor và TaskScheduler

Trong ứng dụng Java 17 với cấu hình thông thường, Spring Boot 3.3 có khả năng auto-configure một `AsyncTaskExecutor`, mặc định là `ThreadPoolTaskExecutor` nếu không có `Executor` bean khiến auto-configuration phải nhường chỗ.

Trong một số tích hợp, executor auto-configured còn phục vụ:

- `@EnableAsync` và `@Async`.
- Spring MVC asynchronous request handling.
- Một số tích hợp GraphQL/WebFlux theo điều kiện loại executor và tên bean.

**Tên bean và loại bean quan trọng.** Với custom `Executor`, đường auto-configuration có thể back off; Spring MVC/WebFlux còn có các điều kiện riêng để chọn bean tên `applicationTaskExecutor` có kiểu phù hợp. Đừng tạo một executor tùy ý rồi mặc định mọi cơ chế async trong app đã dùng đúng pool đó.

Đối với `@Scheduled`, Spring Boot có thể auto-configure `TaskScheduler`, thường là `ThreadPoolTaskScheduler` trên Java 17 không bật virtual threads; scheduler mặc định thường có một thread, có thể điều chỉnh bằng thuộc tính `spring.task.scheduling`.

### 9.1. Cấu hình executor do Boot auto-configure

**Chỉ áp dụng khi sử dụng đường auto-configuration phù hợp; không mặc định tác động lên mọi custom bean.**

```properties
# Pool xử lý tác vụ, ví dụ khi Boot tạo ThreadPoolTaskExecutor.
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=100
spring.task.execution.thread-name-prefix=app-task-

# Cho phép đợi các task đã được nhận khi dừng.
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=15s

# Scheduler nếu được Boot auto-configure.
spring.task.scheduling.pool.size=2
spring.task.scheduling.thread-name-prefix=app-schedule-
spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=10s
```

Đây là snippet `application.properties`; các key trên được mô tả trong Spring Boot 3.3 common application properties. Cần kiểm tra executor nào thực sự được tạo trong runtime, đặc biệt khi ứng dụng hoặc starter đã khai báo custom bean.

### 9.2. Không nhầm cấu hình Boot với việc tự tạo Executors.newFixedThreadPool

Nếu một service tự gọi:

```java
ExecutorService unmanaged = Executors.newFixedThreadPool(4);
```

thì các thuộc tính `spring.task.execution.shutdown.*` **không tự chui vào object này**. Đó là object JDK nằm ngoài ownership của Spring nếu bạn không đăng ký nó làm bean hoặc không tạo wrapper có cleanup.

### 9.3. Java 21 virtual threads

Spring Boot 3.3 có thể dùng virtual threads khi Java 21+ và bật `spring.threads.virtual.enabled=true`. Khi đó auto-configured executor/scheduler có thể dùng những implementation khác với thread pool truyền thống; nhiều thuộc tính pool không còn hiệu lực.

Dù virtual threads nhẹ hơn, điều đó **không có nghĩa có thể bỏ qua ownership, cancellation, timeout và task lifecycle**. Không lấy ví dụ Java 21 làm code chạy được trên Java 17; bài này giữ toàn bộ ví dụ chính tương thích Java 17.

## 10. Ví dụ Spring Boot 3.3 chạy được: @Async dùng managed pool

Ví dụ hoàn chỉnh có ba file Java và một build script. Nó:

- Tạo `ThreadPoolTaskExecutor` thành Spring bean tên `businessExecutor`.
- Sử dụng `@Async("businessExecutor")` để gửi tác vụ vào pool cụ thể.
- Có runner nhận `CompletableFuture` và chờ kết quả trong giới hạn.
- Đóng `ApplicationContext` khi chương trình non-web kết thúc, để container chủ động cleanup executor.
- Không tạo `ExecutorService` trong mỗi request.

### 10.1. Cấu trúc

```text
managed-async-demo/
  settings.gradle
  build.gradle
  src/main/java/com/example/pool/
    ManagedAsyncApplication.java
    AsyncConfiguration.java
    ReportWorker.java
```

### 10.2. settings.gradle

```groovy
rootProject.name = 'managed-async-demo'
```

### 10.3. build.gradle (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Đây là build script cho Java 17+/Boot 3.3.x. Khi có Gradle Wrapper và JDK hợp lệ, có thể chạy bằng `bootRun`. Không cần `spring-boot-starter-web` vì mục tiêu là vòng đời pool, không phải HTTP.

### 10.4. ManagedAsyncApplication.java

```java
package com.example.pool;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ManagedAsyncApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ManagedAsyncApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("CONTEXT_READY");
        }

        System.out.println("CONTEXT_CLOSED");
    }

    @Bean
    ApplicationRunner runExample(ReportWorker worker) {
        return args -> {
            String value = worker.generate("42")
                    .get(5, TimeUnit.SECONDS);
            System.out.println("ASYNC_RESULT " + value);
        };
    }
}
```

### 10.5. AsyncConfiguration.java

```java
package com.example.pool;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {

    @Bean("businessExecutor")
    ThreadPoolTaskExecutor businessExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("business-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);

        return executor;
    }
}
```

### 10.6. ReportWorker.java

```java
package com.example.pool;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {

    @Async("businessExecutor")
    public CompletableFuture<String> generate(String id) {
        return CompletableFuture.completedFuture("report:" + id);
    }
}
```

**Giải thích:**

- `@EnableAsync` bật xử lý `@Async` theo proxy semantics thông thường.
- `@Async("businessExecutor")` chỉ định chính xác pool do Spring quản lý.
- `ReportWorker` là bean khác với nơi gọi `generate(...)`, nên lời gọi đi qua proxy của Spring. Gọi `this.generate(...)` trong chính class đó có thể **bỏ qua proxy**, khiến chạy đồng bộ; cần tránh self-invocation khi mong đợi async.
- `CompletableFuture<String>` giúp caller theo dõi kết quả và exception, thay vì chỉ fire-and-forget.
- Runner gọi `get(5, TimeUnit.SECONDS)` nên không chờ kết quả vô hạn.
- `ThreadPoolTaskExecutor` được Spring initialize/destroy theo lifecycle bean; không tự gọi `shutdown()` tại controller hoặc ở mỗi lần `generate(...)`.
- `try-with-resources` ở đây áp dụng cho **ConfigurableApplicationContext**, là `AutoCloseable`; không phải `ExecutorService` Java 17.

### 10.7. Chạy và stdout

Từ thư mục có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD: `gradlew.bat bootRun`; PowerShell: `.\gradlew.bat bootRun`.

Bỏ qua banner/log framework. Khi task thành công, ba dòng **do chương trình tự in** xuất hiện theo thứ tự:

```text
ASYNC_RESULT report:42
CONTEXT_READY
CONTEXT_CLOSED
```

Trong ví dụ non-web, sau khi `SpringApplication.run(...)` trả về, khối `try` thoát và đóng context. Nếu bean executor cần chờ các task chưa kết thúc, Spring áp dụng policy shutdown đã cấu hình. Vì task demo đã hoàn thành qua `Future.get(...)`, shutdown thông thường nhanh.

**Giới hạn:** Đây là ví dụ học thuật, không đo tốc độ thực tế hoặc bảo đảm mỗi thread bắt đầu/kết thúc đúng thời gian cố định. Một lỗi startup hoặc timeout sẽ làm đường thành công trên không còn đúng; đó là lý do phải quản lý failure policy.

## 11. Nếu dùng ExecutorService JDK như một Spring bean

Không bắt buộc mọi pool đều là `ThreadPoolTaskExecutor`. Một thư viện cũ có thể yêu cầu `ExecutorService`. Có thể đăng ký một bean có destroy callback:

```java
@Configuration(proxyBeanMethods = false)
class LegacyExecutorConfiguration {

    @Bean(destroyMethod = "shutdown")
    ExecutorService legacyExecutor() {
        return Executors.newFixedThreadPool(2);
    }
}
```

Đây là **snippet class minh họa**, cần import `ExecutorService`, `Executors`, `Configuration` và `Bean`.

**Ranh giới quan trọng:** `destroyMethod = "shutdown"` chỉ yêu cầu gọi `shutdown()` khi bean bị destroy. Trong Java 17, `shutdown()` **không đợi các task hoàn tất**. Nếu cần bounded waiting và cancellation policy, tạo một **owner bean** có phương thức `@PreDestroy`/`DisposableBean.destroy()` gọi đầy đủ `shutdownAndAwaitTermination`, thay vì cho rằng gắn một destroy method đã đủ.

### 11.1. Owner bean với @PreDestroy

```java
package com.example.pool;

import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class OwnedWorkerPool {

    private final ExecutorService delegate = new ThreadPoolExecutor(
            2, 4, 30, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(32),
            new ThreadPoolExecutor.AbortPolicy());

    public void submit(Runnable task) {
        delegate.execute(task);
    }

    @PreDestroy
    public void stop() {
        delegate.shutdown();

        try {
            if (!delegate.awaitTermination(10, TimeUnit.SECONDS)) {
                List<Runnable> notStarted = delegate.shutdownNow();
                System.err.println(
                        "Unstarted tasks: " + notStarted.size());

                if (!delegate.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.err.println(
                            "Worker pool did not terminate in time");
                }
            }
        } catch (InterruptedException ex) {
            delegate.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

Đây là **file Java đầy đủ** nếu nằm trong project Spring Boot 3.3 có `spring-boot-starter` và component scan bao phủ package. Nó minh họa bean **sở hữu** một pool private và được Spring gọi `@PreDestroy` khi bean bị hủy.

Không đăng ký đồng thời chính `delegate` làm bean độc lập với destroy method khác; nếu hai owner cùng shutdown một pool, bạn có thể gặp double-cleanup và thứ tự shutdown khó kiểm soát. Chỉ một owner chính nên quyết định policy hủy.

### 11.2. Bản thân @PreDestroy chưa bảo đảm task xong

Trong callback, cần làm rõ:

- Có chặn task mới vào không?
- Có đợi task cũ không, đợi tối đa bao lâu?
- Nếu quá hạn, hủy và ghi log thế nào?
- Task có phản hồi `interrupt` không?
- Những tác vụ chưa bắt đầu có cần được retry/persist không?
- Các bean tài nguyên mà task đang dùng có còn sống trong khoảng chờ không?

Nếu chỉ gọi `delegate.shutdown()` rồi return, container có thể tiếp tục destroy database client hoặc HTTP client khi task còn chạy. Vì vậy trong các hệ thống có dependency quan trọng, việc chờ có giới hạn và thứ tự đóng tài nguyên cần được thiết kế rõ.

## 12. @Scheduled và scheduler cũng có vòng đời

Một ứng dụng sử dụng `@EnableScheduling` và `@Scheduled` có thể cần `TaskScheduler` để chạy tác vụ định kỳ. Scheduler **cũng sở hữu thread và hàng đợi**, không khác về trách nhiệm dừng.

Bean có thể cấu hình:

```java
@Configuration(proxyBeanMethods = false)
@EnableScheduling
class SchedulingConfiguration {

    @Bean("taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();

        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("scheduled-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(10);
        return scheduler;
    }
}
```

Đây là snippet class minh họa, cần imports `Configuration`, `EnableScheduling`, `Bean`, `ThreadPoolTaskScheduler`. Khi được Spring quản lý, scheduler có lifecycle shutdown tương ứng. Nếu dùng scheduler do Boot auto-configure, có thể đặt `spring.task.scheduling.shutdown.await-termination` và `...period` thay vì tự tạo pool.

### 12.1. Scheduled tasks có thể kéo dài shutdown

Một task cố định 10 phút có thể đang chạy khi container nhận SIGTERM. Quyết định chính sách:

- Đợi task hoàn thành một khoảng thời gian tối đa?
- Interrupt task sau timeout?
- Chấp nhận một job bị dừng và retry ở lượt schedule sau?
- Dùng distributed lock/lease để tránh hai instance thực hiện một job khi rollout?
- Ghi checkpoint để xử lý lại nếu job dừng giữa chừng?

Executor shutdown **không tự cung cấp** exactly-once, distributed coordination hoặc transaction rollback. Với job tài chính/dữ liệu quan trọng, cần cơ chế job processing bền vững.

## 13. Thứ tự dừng: readiness, nguồn cấp việc, executor và tài nguyên

Một thiết kế shutdown thường phải làm nhiều việc hơn “đợi thread pool”.

```text
SIGTERM / yêu cầu dừng instance
       |
       v
Readiness REFUSING_TRAFFIC / drain traffic mới
       |
       v
Dừng producer / scheduler / consumer nhận việc mới
       |
       v
Executor từ chối submit mới
       |
       v
Chờ in-flight tasks trong deadline
       |
       +-- Hoàn tất: commit/checkpoint/cleanup
       |
       +-- Quá hạn: interrupt/cancel, ghi nhận task còn dang dở
       |
       v
Đóng DataSource, HTTP clients, broker resources
       |
       v
ApplicationContext kết thúc đóng
```

Đây là **thứ tự mục tiêu**; lifecycle callback thực tế phụ thuộc loại bean, phase, thứ tự dependency và config. Spring Boot và Spring Framework có cơ chế `SmartLifecycle`/`LifecycleProcessor` cho việc điều phối start/stop. Tự tạo pool bên ngoài container khiến bạn khó tham gia vào cơ chế này.

### 13.1. Khác biệt stop và destroy của Spring

- `SmartLifecycle.stop(Runnable callback)` có thể tham gia vào **pha dừng phối hợp**; callback phải được gọi khi việc dừng hoàn tất.
- `@PreDestroy` hoặc `DisposableBean.destroy()` được gọi trong **pha hủy bean**, không phải lệnh tạm dừng.
- `ThreadPoolTaskExecutor` kế thừa hạ tầng hỗ trợ lifecycle/destroy, có các lựa chọn phối hợp sớm hoặc đợi trong shutdown.
- `setWaitForTasksToCompleteOnShutdown(true)` tác động đến lựa chọn phối hợp lifecycle stop; hãy đọc đúng JavaDoc Spring 6.1 khi cấu hình các cờ cùng nhau.

Đối với một executor có nhiều tài nguyên phụ thuộc, không chỉ chọn phase theo số ngẫu nhiên: phải xác định ai **ngừng submit** trước, ai **đợi** task, ai **đóng nguồn tài nguyên** sau.

### 13.2. Thời hạn Kubernetes

Một container được gửi `SIGTERM` thường có khoảng grace period trước khi nền tảng buộc chấm dứt. Nếu `executor.awaitTermination` đặt 60 giây nhưng deployment chỉ cho 30 giây, bạn không thể tin rằng mọi task được chạy hết. Cần phối hợp:

- Thời gian drain load balancer/ingress.
- `server.shutdown=graceful` nếu dùng web server và thời gian phục vụ request đang chạy.
- `spring.lifecycle.timeout-per-shutdown-phase` cho các `SmartLifecycle` phases.
- Executor/scheduler await-termination period.
- `terminationGracePeriodSeconds` và deadline của hạ tầng.
- Thời gian commit checkpoint/offset nếu có durable queue.

Không cộng timeout bừa bãi để bảo đảm tổng thời gian; các pha có thể song song hoặc tuần tự tùy lifecycle, và hạ tầng vẫn có hard deadline.

## 14. Queue bounded, rejection, backpressure và task backlog

Một pool không được shutdown là một kiểu leak; một pool có **unbounded queue** cũng có thể làm cạn bộ nhớ trong khi thread count trông ổn định.

Với `ThreadPoolExecutor`:

1. Tạo thread tới `corePoolSize` khi cần.
2. Khi đã có core threads, cố xếp task vào queue.
3. Khi queue đầy, mở thêm thread tới `maximumPoolSize`.
4. Khi không còn chỗ, gọi `RejectedExecutionHandler`.

Đó là luồng thường gặp đối với một bounded blocking queue. Với queue unbounded, bước mở rộng tới max có thể gần như không được dùng; do đó `maxPoolSize=100` không giúp gì nếu core size 8 và queue liên tục nhận công việc vô hạn.

### 14.1. Các rejection policy của JDK

| Policy | Hành vi | Rủi ro cần xét |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` | Caller phải xử lý lỗi/HTTP status/retry rõ |
| `CallerRunsPolicy` | Trong điều kiện thích hợp, caller tự chạy task | Có thể chặn HTTP thread; khi shutdown có thể bỏ task |
| `DiscardPolicy` | Bỏ task mới | Mất công việc nếu không có cơ chế ghi nhận |
| `DiscardOldestPolicy` | Bỏ task cũ nhất đang chờ rồi thử lại | Có thể phá thứ tự và làm mất task |

Với công việc nghiệp vụ cần theo dõi, mặc định nên thiên về **rejection hiển thị rõ** và phản hồi có chủ đích hơn là discard im lặng. Nếu workload quá lớn cho in-memory pool, durable message queue và worker riêng có thể phù hợp hơn.

### 14.2. TaskRejectedException trong Spring

Khi dùng `ThreadPoolTaskExecutor`, tình huống bị từ chối có thể xuất hiện dưới dạng `TaskRejectedException` của Spring (liên quan `RejectedExecutionException` của JDK). Caller cần xác định cách xử lý:

- Trả HTTP 429/503 tùy contract.
- Thử lại có backoff nếu an toàn.
- Ghi task vào durable queue.
- Giới hạn input ở tầng API.
- Không nhận tác vụ mới khi instance đang dừng.

Không bắt mọi exception rồi trả `202 Accepted` nếu thực tế công việc **không hề được nhận**.

## 15. Xử lý interrupt và cancellation trong task

Task có thể chủ động kiểm tra interrupt:

```java
public void performLoop() {
    while (!Thread.currentThread().isInterrupted()) {
        try {
            doOneUnitOfWork();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            break;
        }
    }
}
```

Đây là snippet minh họa trong một class nghiệp vụ: `doOneUnitOfWork()` là một method **có thể ném InterruptedException** do ứng dụng/thư viện định nghĩa. Không có method đó trong Java chuẩn, nên snippet chưa phải file chạy riêng.

Lưu ý:

- Nếu API đang dùng **ném `InterruptedException`**, xử lý hợp đồng cancellation và thường khôi phục cờ interrupt khi không tiếp tục propagate.
- Nếu task đang làm một transaction, phải bảo đảm rollback/cleanup phù hợp.
- Không nuốt interrupt để lặp vô hạn.
- Có những I/O operations không dừng ngay khi interrupt, nên cần timeout/cancel riêng.
- Chỉ ngừng worker khi các invariant của dữ liệu/offset/checkpoint đã được xử lý an toàn.

### 15.1. Future.cancel(true) không thay thế quản lý executor

`Future.cancel(true)` chỉ yêu cầu hủy **một task cụ thể**. Executor vẫn có thể nhận task mới và giữ worker threads. Khi kết thúc vòng đời ứng dụng, bạn vẫn phải shutdown **chính executor** theo owner phù hợp.

### 15.2. ThreadLocal và MDC

Thread pool tái sử dụng worker. Nếu một task đặt dữ liệu trong `ThreadLocal`/MDC/security context mà không xóa, task tiếp theo có thể thấy context của task trước, gây sai log hoặc rò dữ liệu giữa request.

Dùng `try/finally` để clear dữ liệu đã đặt; với Spring có thể dùng `TaskDecorator` để truyền/dọn context đúng cách. Shutdown pool sẽ kết thúc thread, nhưng **không giải quyết** rò context giữa các task trong khi pool đang chạy.

## 16. @Async: những điều dễ hiểu sai

### 16.1. @Async cần được kích hoạt và gọi qua proxy

Trong cách dùng proxy mặc định, cần `@EnableAsync` và lời gọi tới method annotated qua Spring proxy. Lời gọi `this.methodAnnotatedAsync()` bên trong chính bean có thể bỏ qua proxy và chạy đồng bộ.

Việc method có annotation `@Async` **không bảo đảm** nó dùng executor mong muốn. Nếu nhiều `Executor` beans, thứ tự ưu tiên, qualifier và tên bean có thể ảnh hưởng chọn pool.

Dùng `@Async("businessExecutor")` hoặc `AsyncConfigurer` khi cần chỉ định rõ.

### 16.2. Không fire-and-forget không có lỗi

Một method `@Async void` có exception có thể không truyền trực tiếp về caller; Spring có `AsyncUncaughtExceptionHandler` để xử lý các exception không được bắt từ method trả `void`.

Với công việc cần xác nhận kết quả, ưu tiên `Future`/`CompletableFuture` hoặc hệ thống job có trạng thái. Đừng coi trả HTTP 202 từ controller là bằng chứng task đã hoàn tất.

### 16.3. @Async không tự có durable queue

Một executor in-memory mất nội dung queue khi process bị `SIGKILL` hoặc node bị mất. Nếu tác vụ không được phép mất, nhận và lưu công việc vào hệ thống bền vững trước khi trả acknowledgment. Executor chỉ chịu trách nhiệm **thực thi**, không phải transaction log.

## 17. Quan sát executor trong production

Cần theo dõi cả hiệu năng và khả năng dừng:

| Chỉ số | Dùng để hiểu điều gì? |
| --- | --- |
| Active thread count | Có bao nhiêu worker đang làm việc |
| Pool size/current threads | Pool đã mở rộng đến mức nào |
| Queue size/capacity | Backlog có tăng liên tục không |
| Completed task count | Tốc độ hoàn thành |
| Rejected task count | Có bị quá tải hoặc submit lúc shutdown không |
| Task duration p95/p99 | Task nào đang chậm |
| Task errors/timeouts | Có lỗi bị mất trong background không |
| Executor shutdown duration | Đóng pool mất bao lâu |
| Still-running task count | Có task bỏ qua interrupt hoặc chờ I/O vô hạn không |
| JVM thread count | Có thread leak qua nhiều lần tạo context không |

`ThreadPoolTaskExecutor` có API như `getPoolSize()`, `getActiveCount()` và `getQueueSize()` để quan sát pool hiện hành. Các metric cụ thể trên Actuator/Micrometer tùy cấu hình và meter binder; **không giả định** mọi custom executor tự xuất đủ chỉ số nếu chưa cấu hình giám sát.

### 17.1. Tìm thread leak

Một vài triệu chứng:

- JVM không thoát dù `ApplicationContext.close()` đã được gọi.
- Thread count tăng sau nhiều lượt chạy test/redeploy.
- Có nhiều thread tên `pool-123-thread-1`, tên không chỉ ra owner.
- Heap dump giữ reference tới classloader cũ qua thread/context.
- Logs báo callback shutdown hoàn tất nhưng executor vẫn `isTerminated() == false`.

Cách xử lý: lấy thread dump, ghi thread name prefix có ý nghĩa, tìm nơi tạo pool, xác định ownership và path shutdown thực tế. Không chỉ tăng memory limit hay đánh dấu mọi thread daemon.

## 18. Những tình huống thiết kế điển hình

### A. Một job đọc file 30 giây trong web service

Tạo `ExecutorService` mỗi request sẽ làm nhiều pools tích tụ. Dùng managed pool có queue hữu hạn; khi shutdown, dừng nhận job mới và cho job đang chạy một thời gian cụ thể để hoàn thành hoặc checkpoint. Nếu job cần sống qua restart, chuyển sang durable job queue.

### B. Hàng nghìn request cùng submit vào pool bốn threads

Không có queue limit, backlog có thể tăng quá khả năng bộ nhớ. Cấu hình bounded queue + explicit rejection policy; trả phản hồi tải phù hợp và quan sát p99/task wait.

### C. @Scheduled mỗi phút đồng bộ dữ liệu

Khi có shutdown, scheduler không nên phát thêm lượt mới trong lúc consumer/data source đang dừng. Dùng managed `TaskScheduler`, xác định cách xử lý lượt đang chạy và checkpoint nếu cần.

### D. Một bean tự tạo ScheduledExecutorService

Bean đó vẫn phải chủ động `shutdown` và `awaitTermination` khi destroy. Đừng kỳ vọng Spring tự quản lý executor private field. Nếu phù hợp, chuyển thành `ThreadPoolTaskScheduler` bean để tham gia lifecycle.

### E. Backend database mất kết nối khi shutdown

Một task cố chạy query trong lúc DataSource đã đóng sẽ thất bại. Thiết kế dừng producer trước, chờ task, rồi mới đóng DataSource; dùng `SmartLifecycle`/bean dependency phù hợp và await timeout có ý nghĩa.

### F. App trong Kubernetes bị kill trước khi job xong

Nếu app dành 60 giây để await nhưng platform chỉ cho 30 giây, `SIGKILL` có thể cắt ngang và bỏ qua cleanup. Sửa deadline tổng, rút ngắn task, checkpoint và dùng queue durable cho phần việc bắt buộc.

### G. Java 21 sử dụng virtual threads

Virtual thread không cần pool kích thước giống platform threads, nhưng task vẫn phải có cancellation, timeout và ownership. Nếu tạo executor thủ công, kiểm tra lifecycle theo JDK tương ứng; trên Java 17 không dùng API virtual-thread chỉ có ở phiên bản mới.

## 19. Những hiểu nhầm cần tránh

| Hiểu nhầm | Điều đúng |
| --- | --- |
| “ExecutorService là object, GC sẽ dọn thread.” | Thread pool sống có thể giữ thread/tài nguyên; shutdown phải có owner. |
| “shutdown() đợi mọi task chạy xong.” | Nó chỉ khởi tạo graceful shutdown; cần awaitTermination để chờ. |
| “shutdownNow() luôn kết thúc mọi task ngay.” | Chỉ best effort interruption/cancellation. |
| “Đánh dấu daemon=true là đã cleanup.” | Daemon có thể bị cắt đột ngột; không bảo đảm commit/flush. |
| “@Service chứa field executor thì Spring tự đóng field.” | Container không tự biết mọi pool con; phải có callback/bean owner. |
| “@Bean(destroyMethod=shutdown) bảo đảm task xong.” | shutdown không đợi; có thể cần owner await/cancel. |
| “Đặt maxPoolSize lớn là đủ chống quá tải.” | Unbounded queue có thể khiến maxPoolSize không được dùng. |
| “Một executor cho mỗi HTTP request là isolation tốt.” | Rủi ro thread/queue leak và resource explosion. |
| “@Async luôn chạy trên pool do mình vừa khai báo.” | Có proxy, qualifier và selection rules. |
| “@Async void exception được trả về HTTP caller.” | Lỗi có thể đi qua AsyncUncaughtExceptionHandler, không truyền trực tiếp. |
| “@Scheduled có job thì tự đảm bảo checkpoint.” | Scheduler không bảo đảm exactly-once hay persistence. |
| “Spring shutdown đợi vô hạn cho mọi thread.” | Có timeout, lifecycle policy và hard deadline của container. |
| “Tăng wait timeout đủ là an toàn dữ liệu.” | Cần idempotency, transaction/checkpoint và durable queue nếu task quan trọng. |
| “Virtual threads làm ownership không còn cần thiết.” | Resource/cancellation/lifecycle vẫn quan trọng. |
| “Executor đã isShutdown() nghĩa đã isTerminated().” | Có thể đang chạy và có queued work. |
| “CallerRunsPolicy luôn an toàn.” | Có thể chặn request thread và thay đổi behavior lúc shutdown. |

## 20. Checklist thực hành

1. Tìm các nơi gọi `Executors.newFixedThreadPool`, `newCachedThreadPool`, `newSingleThreadExecutor`, `newScheduledThreadPool` và `new Thread(...)`.
2. Với mỗi executor, ghi owner và chính xác callback sẽ đóng nó.
3. Ưu tiên `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler` do Spring quản lý cho `@Async`/`@Scheduled`.
4. Đảm bảo pool không được tạo trong mỗi request hoặc mỗi lần retry.
5. Nếu dùng `ExecutorService` JDK, viết `try/finally` hoặc owner bean `@PreDestroy`/destroy method.
6. Nhớ `shutdown()` ngừng nhận task mới **nhưng không đợi**.
7. Sau shutdown, `awaitTermination` hữu hạn; quá hạn cần policy rõ.
8. Với `shutdownNow()`, xử lý task chưa bắt đầu và task đang chạy có thể bỏ qua interrupt.
9. Khi dùng `@Async`, chỉ định pool đúng và kiểm tra proxy/self-invocation.
10. Đặt core/max/queue capacity phù hợp với workload; tránh backlog vô hạn.
11. Chọn rejection policy có phản hồi/quan sát, không âm thầm mất task.
12. Tách durable jobs khỏi thread pool in-memory nếu cần retry qua restart.
13. Trong shutdown, dừng producer/consumer nhận việc trước khi đóng dependencies.
14. Cấu hình await period cùng `spring.lifecycle.timeout-per-shutdown-phase` và grace period của hạ tầng.
15. Viết task tôn trọng interrupt, có timeout và cleanup resources.
16. Kiểm tra `ThreadLocal`/MDC sau mỗi task.
17. Theo dõi active threads, queue, rejected tasks, task duration và shutdown latency.
18. Test context close khi có task đang chạy, task bị kẹt và task bị từ chối.
19. Test deployment restart/`SIGTERM` ở staging; không dựa vào `SIGKILL` cleanup.
20. Với Java 17, đừng dùng `ExecutorService` try-with-resources mà không kiểm tra version contract.
21. Không mặc định các property của Boot tác động lên custom ExecutorService.
22. Đánh giá correctness/idempotency trước khi gọi một tác vụ nền là “đã accepted”.

## 21. Câu hỏi tự kiểm tra

**1. Vì sao pool tạo trong mỗi request thường nguy hiểm?**

Vì mỗi request có thể sinh pool riêng, thread không-daemon và queue sống lâu, không có owner đóng khi request kết thúc.

**2. shutdown() khác shutdownNow() ra sao?**

`shutdown()` từ chối công việc mới nhưng cho task cũ cơ hội hoàn thành; `shutdownNow()` cố ngừng task đang chạy và không bắt đầu task đang chờ, nhưng không bảo đảm mọi task dừng.

**3. awaitTermination() dùng khi nào?**

Sau khi đã yêu cầu shutdown, để chờ bounded cho đến khi executor thực sự terminated.

**4. isShutdown() == true có nghĩa mọi task xong không?**

Không. Cần kiểm tra `isTerminated()` hoặc kết quả `awaitTermination`.

**5. Spring tự đóng một ExecutorService private field trong @Service không?**

Không nên giả định. Cần explicit owner callback hoặc đăng ký executor thành Spring bean có lifecycle.

**6. @Bean(destroyMethod = "shutdown") đã đủ cho mọi nghiệp vụ không?**

Không. `shutdown()` không block; nhiệm vụ quan trọng thường cần await, cancel policy và checkpoint/transaction riêng.

**7. Vì sao đặt maxPoolSize=100 nhưng pool chỉ dùng 8 workers?**

Một queue unbounded có thể giữ vô hạn task trước khi cơ chế mở rộng tới max. Cần hiểu queue capacity.

**8. @Async có nghĩa task sẽ tồn tại sau pod restart không?**

Không. `@Async` chỉ thay đổi execution model trong process; cần durable queue/job store nếu muốn bền vững.

**9. Khi @Async method tự gọi method khác trong cùng bean có @Async, chắc chắn asynchronous không?**

Không. Self-invocation có thể bypass Spring proxy.

**10. Đánh dấu thread là daemon có thể thay shutdown() không?**

Không. Daemon thread có thể bị JVM kết thúc đột ngột, làm mất work/cleanup.

**11. Tại sao task cần xử lý InterruptedException?**

Vì shutdownNow/cancellation có thể yêu cầu interrupt; task phải hợp tác để dừng, giữ tính đúng đắn và giải phóng tài nguyên.

**12. Spring Boot 3.3 có property await termination cho task execution/scheduling không?**

Có; `spring.task.execution.shutdown.await-termination` và `spring.task.scheduling.shutdown.await-termination` cùng các property period, khi dùng auto-configuration phù hợp.

## 22. Kết luận

```text
Tạo Executor
     |
Xác định OWNER duy nhất
     |
Định nghĩa pool size + bounded queue + rejection
     |
Sử dụng lại giữa các tác vụ
     |
Ứng dụng bắt đầu dừng
     |
Ngừng nhận công việc mới
     |
shutdown()
     |
awaitTermination(timeout)
     |
   +-- terminated -> cleanup thành công
   |
   +-- timeout -> shutdownNow() (best effort)
                    |
                    +-- retry/checkpoint/log nếu cần
     |
ApplicationContext / process dừng
```

**Quy tắc quan trọng nhất:** Không tạo executor mà không có **chủ sở hữu và đường thu hồi xác định**. Với Spring Boot, dùng pool **được container quản lý** và policy shutdown phù hợp. Với Java `ExecutorService` tự tạo, dùng `shutdown + awaitTermination` trong owner lifecycle, không chờ GC hoặc trông cậy daemon threads. Khi công việc nền cần bảo đảm dữ liệu, kết hợp durable queue, checkpoint, idempotency và deadline của hạ tầng.

## Tài liệu chính thức

- [Java 17 — ExecutorService: shutdown, shutdownNow, awaitTermination](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java 17 — ThreadPoolExecutor và RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html)
- [Spring Boot 3.3 — Common Application Properties: spring.task.execution và spring.task.scheduling](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Framework 6.1 — ExecutorConfigurationSupport shutdown settings](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html)
- [Spring Framework 6.1 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.1 — ThreadPoolTaskScheduler API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
