# Quản lý hàng đợi, giới hạn đồng thời và lỗi trong tác vụ nền của Spring Boot

**Phạm vi:** Spring Boot Application Runtime → Luồng và tác vụ. Bài học tập trung vào ba yêu cầu phải được giải quyết **cùng nhau** khi ứng dụng nhận công việc không thực hiện trực tiếp trên HTTP request thread: **hàng đợi có giới hạn**, **số công việc được thực thi đồng thời**, và **cách tiếp nhận/ghi nhận/phục hồi lỗi**. Nội dung trình bày cơ chế `ThreadPoolTaskExecutor`, chiến lược từ chối, `@Async` và `CompletableFuture`, backpressure, tính bền vững khi restart và shutdown. Ví dụ hoàn chỉnh dùng **Java 17+**, **Spring Boot 3.5.x** và **Spring MVC**.

Mọi lệnh và response ở phần thực hành đều theo một ứng dụng local; kết quả thời gian, ID UUID, số thread trong một snapshot có thể thay đổi theo máy. Tách riêng **mã hoàn chỉnh có thể build bằng Maven** và **snippet thiết kế nâng cao** để tránh hiểu một mảnh code là một ứng dụng độc lập.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt `request thread`, worker thread, thread pool, task queue, scheduler và một job đang lưu trong database.
2. Giải thích `corePoolSize`, `maxPoolSize`, `queueCapacity`, `keepAliveSeconds`, `activeCount` và `poolSize`.
3. Dự đoán điều kiện pool tạo thêm thread, đưa việc vào hàng đợi và từ chối request khi bão hòa.
4. Thiết kế giới hạn chấp nhận việc, không dùng queue không giới hạn để che giấu quá tải.
5. Xử lý **lỗi nộp việc (rejection)** khác với **exception trong worker**, cancellation và timeout.
6. Dùng `ThreadPoolTaskExecutor.execute(...)` và `TaskRejectedException` để xây HTTP API trả `202 Accepted` hoặc phản hồi quá tải phù hợp.
7. Dùng `@Async("...")` với `CompletableFuture` khi cần tương tác bất đồng bộ qua Spring proxy; nêu giới hạn của `void @Async`.
8. Đo pool/queue/accepted/rejected/succeeded/failed thay vì chỉ dựa vào log “started”.
9. Hiểu vì sao kết quả trả về 202 chưa có nghĩa job đã thành công và tại sao queue RAM không phải durable queue.
10. Đề xuất shutdown, retry, idempotency, độ công bằng và backpressure cho ứng dụng có nhiều replica.

**Thông điệp chính:** Một hệ thống tác vụ nền đáng tin phải có **sức chứa hữu hạn**, **quy tắc từ chối rõ ràng**, **trạng thái công việc có thể quan sát**, **cơ chế phục hồi khi lỗi**, và **lifecycle lúc tắt ứng dụng**. Chỉ dùng `@Async` hoặc `new Thread(...)` không tự cung cấp các đặc tính này.

## 2. Tách bạch ba tài nguyên: worker, queue, nguồn công việc

Với một HTTP API nhận tác vụ:

~~~text
HTTP client
    |
    | POST /lab/jobs
    v
Controller (Tomcat request thread)
    |
    | validate + submit
    v
ThreadPoolTaskExecutor
    |
    +--- worker đang chạy task      <= maxPoolSize
    |
    +--- BlockingQueue chờ lượt    <= queueCapacity
    |
    +--- rejection khi không còn chỗ
    |
    v
Result/state: DONE, FAILED, INTERRUPTED ...
~~~

**Worker threads** là nơi code task thật sự chạy. **Queue** là nơi task chờ chưa có worker rảnh. **Nguồn công việc** có thể là HTTP, event, scheduler, Kafka/RabbitMQ consumer hoặc database jobs. Nếu nguồn đưa việc nhanh hơn mức hoàn thành trong thời gian dài, backlog buộc phải tăng ở đâu đó; đổi từ queue JVM sang message broker chỉ chuyển vị trí backlog, không tự giải quyết năng lực xử lý.

Ví dụ pool có tối đa **4** thread, queue **2** task. Khi mọi worker đều bận và hai ô queue đã đầy, một submission mới cần bị từ chối, trì hoãn ở upstream, hoặc kích hoạt cơ chế backpressure hợp lệ. Không để process nhận vô hạn request rồi giữ mọi `Runnable` trong RAM: khi đó latency tăng, heap phình, có thể dẫn đến GC pressure hoặc `OutOfMemoryError`.

### 2.1. Định nghĩa “đồng thời” đúng phạm vi

- `maxPoolSize=4` chỉ giới hạn tối đa 4 **worker threads của executor cụ thể** khi pool đã tăng đến mức đó.
- Nó **không** giới hạn tổng request đồng thời của Tomcat, tổng task trong mọi executor, số request lên database hoặc mọi instance trong cluster.
- Một job có thể tự spawn thêm threads hoặc thực hiện nhiều I/O bất đồng bộ; khi đó 4 worker không nhất thiết đồng nghĩa tối đa 4 kết nối ra external service.
- Với 3 replicas, mỗi replica có pool tối đa 4 thread thì toàn cụm có thể có đến khoảng 12 worker hoạt động cùng lúc, nếu load được phân phối tới cả ba.
- Muốn giới hạn **concurrency của một resource** (ví dụ chỉ 2 request vào API có quota), có thể cần `Semaphore`/bulkhead riêng quanh resource đó, không chỉ cấu hình executor tổng.

## 3. Cơ chế ThreadPoolTaskExecutor và bốn tham số thiết yếu

Spring Framework cung cấp `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`, lớp cấu hình gần với Java `ThreadPoolExecutor`, có giao diện `TaskExecutor`, quản lý lifecycle cùng Spring và cung cấp metric mức pool.

### 3.1. Quy tắc tiếp nhận task

Với một pool dùng **bounded queue**:

1. Nếu số worker hiện tại chưa đạt `corePoolSize`, executor thường tạo worker để chạy task mới.
2. Khi đã có các core workers bận, task mới **được đưa vào queue** nếu còn sức chứa.
3. Khi queue đã đầy, executor có thể tạo thêm worker từ core đến `maxPoolSize`.
4. Khi worker đã đạt max **và** queue đầy, task mới bị **rejected** theo handler được cấu hình.
5. Worker ngoài core có thể co lại khi idle quá `keepAliveSeconds`, tùy cấu hình core timeout.

**Sai lầm phổ biến:** nghĩ `maxPoolSize=32` đồng nghĩa pool tự mở rộng tới 32 ngay khi 8 core bận. Với **hàng đợi đủ rộng**, pool tiếp tục xếp task vào queue và chỉ tăng số worker khi queue đầy. Điều này là hành vi nền của `ThreadPoolExecutor` với queue thông thường.

### 3.2. Các tham số

| Tham số | Chức năng | Trade-off |
|---|---|---|
| `corePoolSize` | Kích thước lõi của pool | Core cao tăng khả năng xử lý đồng thời nhưng tốn thread/resource |
| `maxPoolSize` | Trần worker trong executor | Không nên vượt quá khả năng CPU, DB pool hoặc upstream |
| `queueCapacity` | Số task có thể chờ trong queue | Queue quá dài gây latency và giữ object trong heap |
| `keepAliveSeconds` | Thời gian worker ngoài core idle trước khi thu nhỏ | Ảnh hưởng chi phí tạo thread khi tải dao động |
| `threadNamePrefix` | Tiền tố tên worker | Giúp đọc thread dump/log và attribution |
| `RejectedExecutionHandler` | Hành vi khi full hoặc shutdown | Chính sách backpressure bắt buộc được quyết định rõ |
| `waitForTasksToCompleteOnShutdown` | Hành vi giữ/không giữ tác vụ đang queue khi shutdown | Liên quan shutdown budget và độ bền nhiệm vụ |
| `awaitTerminationSeconds` | Thời gian chờ executor kết thúc khi shutdown | Phải phối hợp termination grace period toàn tiến trình |

Với `ThreadPoolTaskExecutor`, `queueCapacity > 0` tạo hàng đợi `LinkedBlockingQueue` có sức chứa tương ứng; `queueCapacity <= 0` tạo `SynchronousQueue` không lưu task chờ. Dùng `queueCapacity=0` có thể khiến threads tăng sớm đến max; cần có trần hợp lý. Mặc định của `ThreadPoolTaskExecutor` độc lập là core 1, max rất lớn và queue rất lớn; đừng đánh đồng cấu hình class này với các defaults mà Spring Boot auto-configure cho executor ứng dụng. Đặc biệt, queue không giới hạn có thể làm `maxPoolSize` hầu như không phát huy tác dụng.

### 3.3. Bảng quyết định minh họa

Với `corePoolSize=2`, `maxPoolSize=4`, `queueCapacity=2` và **sáu task đầu đều bị chặn có chủ đích**:

| Submission | Cách xử lý điển hình | Tổng task được chấp nhận |
|---|---|---:|
| Task 1 | Chạy trên core worker thứ nhất | 1 |
| Task 2 | Chạy trên core worker thứ hai | 2 |
| Task 3 | Vào queue | 3 |
| Task 4 | Vào queue | 4 |
| Task 5 | Queue đầy, tăng worker thứ ba | 5 |
| Task 6 | Tăng worker thứ tư | 6 |
| Task 7 | Worker max + queue đầy → rejection | 6 |

Đây là ví dụ được thiết kế để task **không hoàn thành trước khi nộp đủ bảy tác vụ**. Trong sản xuất, vì job liên tục hoàn thành và worker liên tục lấy task khỏi queue, số lượng queue/active là snapshot biến động. Không hardcode bảng này như một quy luật cho mọi kiểu công việc và mọi thời điểm.

## 4. Rejection là cơ chế kiểm soát tải, không chỉ là exception

`java.util.concurrent.ThreadPoolExecutor` có các chiến lược xử lý rejection nổi bật:

| Policy | Khi không còn chỗ | Nguy cơ |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException`; Spring `ThreadPoolTaskExecutor` thể hiện bằng `TaskRejectedException` theo contract TaskExecutor | Caller phải xử lý để không thành 500 mơ hồ |
| `CallerRunsPolicy` | Chạy task ngay trên thread gọi submit, nếu executor còn hoạt động | HTTP request thread có thể bị giữ lâu, gây nghẽn request pool |
| `DiscardPolicy` | Bỏ task mà không thực thi | Mất việc âm thầm; rất nguy hiểm với nghiệp vụ |
| `DiscardOldestPolicy` | Loại task cũ nhất đang chờ rồi thử lại | Mất task cũ, phá thứ tự, khó audit |

Đối với API nhận việc không được phép mất, mẫu lab chọn **AbortPolicy** rồi chuyển rejection thành HTTP **429 Too Many Requests** có thông điệp và chính sách client retry. Trong hệ thống thật, nếu executor đang shutdown, HTTP **503 Service Unavailable** và readiness state có thể thích hợp hơn 429. Hai lý do từ chối khác nhau không nên bị lẫn nếu gateway/client quyết định retry theo status.

**Không mặc định dùng CallerRunsPolicy để “không bao giờ reject”.** Khi task làm I/O dài, nó có thể chạy ngay trên Tomcat thread, khiến HTTP submit biến thành xử lý đồng bộ, làm cạn request threads; đúng là một loại backpressure, nhưng phải chủ động chọn, đo lường và kiểm soát timeout mới an toàn.

## 5. Ứng dụng mẫu có hàng đợi hữu hạn, theo dõi trạng thái và saturation test

### 5.1. Tạo project

Tạo project bằng Spring Initializr:

- Build: **Maven**, Language: **Java**, Java: **17+**.
- Spring Boot: **3.5.x**, packaging **Jar**.
- Group: `com.example`, Artifact: `bounded-worker-lab`.
- Package: `com.example.boundedworker`.
- Dependency: **Spring Web** (không bắt buộc Actuator cho lab cơ bản).

Giữ `pom.xml` và Maven Wrapper mà Initializr sinh ra. Các file:

~~~text
bounded-worker-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/boundedworker/
    BoundedWorkerApplication.java
    WorkerExecutorConfiguration.java
    JobService.java
    JobController.java
  src/main/resources/application.properties
~~~

Các public class đặt trong file trùng tên, đúng package. Cần Maven classpath để biên dịch vì `ThreadPoolTaskExecutor` và Spring MVC là dependency ngoài JDK. Lệnh `javac` một file riêng không đủ; dùng `./mvnw spring-boot:run` hoặc build JAR.

### 5.2. Main class

File `BoundedWorkerApplication.java`:

~~~java
package com.example.boundedworker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundedWorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundedWorkerApplication.class, args);
    }
}
~~~

Không cần `@EnableAsync` vì ở lab chính ta **submit trực tiếp** vào executor qua `execute(...)`. `@EnableAsync` chỉ cần khi lựa chọn cơ chế `@Async` ở phần mở rộng.

### 5.3. Khai báo ThreadPoolTaskExecutor có trần cụ thể

File `WorkerExecutorConfiguration.java`:

~~~java
package com.example.boundedworker;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class WorkerExecutorConfiguration {

    @Bean("boundedWorkerExecutor")
    public ThreadPoolTaskExecutor boundedWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(2);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("lab-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        // Khi Spring quan ly @Bean, no se goi init lifecycle.
        // Khong can tu goi executor.initialize() o day.
        executor.setWaitForTasksToCompleteOnShutdown(false);
        executor.setAwaitTerminationSeconds(10);

        return executor;
    }
}
~~~

**Giải thích:**

- Bốn worker là trần đồng thời **của riêng bean** `boundedWorkerExecutor`.
- Queue chứa tối đa hai `Runnable` đang chờ.
- `AbortPolicy` làm API nhận biết tình trạng executor không thể nhận task.
- `setWaitForTasksToCompleteOnShutdown(false)` không hứa giữ mọi tác vụ trong queue khi shutdown; những task chưa hoàn thành có thể bị gián đoạn/hủy. `setAwaitTerminationSeconds(10)` là thời gian chờ trong shutdown xử lý executor, **không** tạo độ bền dữ liệu.
- `ThreadPoolTaskExecutor` là Spring bean có initialization/shutdown lifecycle; **không gọi `initialize()` thủ công trong `@Bean` rồi để Spring tự init lần nữa** vì có thể tạo/trỏ tới executor không như mong muốn.
- Spring Boot có thể thay đổi auto-configuration task executor khi ứng dụng tự định nghĩa bean `Executor`. Bài này luôn inject chính xác bean `boundedWorkerExecutor` bằng `@Qualifier`, không giả định nó thay thế hoặc không thay thế `applicationTaskExecutor` dùng bởi Spring MVC.
- Không dùng pool này cho mọi việc của ứng dụng một cách vô điều kiện; nên đặt tên và phân tách work classes có nhu cầu tài nguyên khác nhau.

### 5.4. JobService: phân biệt QUEUED, RUNNING, DONE, FAILED và REJECTED

File `JobService.java`:

~~~java
package com.example.boundedworker;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class JobService {

    private final ThreadPoolTaskExecutor executor;
    private final ConcurrentMap<String, JobView> jobs =
            new ConcurrentHashMap<>();
    private final CountDownLatch releaseGate =
            new CountDownLatch(1);

    private final AtomicInteger accepted = new AtomicInteger();
    private final AtomicInteger rejected = new AtomicInteger();
    private final AtomicInteger succeeded = new AtomicInteger();
    private final AtomicInteger failed = new AtomicInteger();
    private final AtomicInteger interrupted = new AtomicInteger();

    public JobService(
            @Qualifier("boundedWorkerExecutor")
            ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public Submission submit(String kind) {
        String id = UUID.randomUUID().toString();
        jobs.put(id, new JobView(id, kind, "QUEUED", "waiting"));

        try {
            executor.execute(() -> runJob(id, kind));
            accepted.incrementAndGet();
            System.out.println("LAB_SUBMITTED id=" + id
                    + " kind=" + kind);
            return new Submission(id, "ACCEPTED");
        } catch (TaskRejectedException ex) {
            rejected.incrementAndGet();
            jobs.put(id, new JobView(
                    id, kind, "REJECTED",
                    "executor saturated or shutting down"));
            System.out.println("LAB_REJECTED id=" + id);
            return new Submission(id, "REJECTED");
        }
    }

    private void runJob(String id, String kind) {
        String thread = Thread.currentThread().getName();
        jobs.put(id, new JobView(id, kind, "RUNNING", thread));
        System.out.println("LAB_RUNNING id=" + id
                + " thread=" + thread);

        try {
            switch (kind) {
                case "block" -> {
                    if (!releaseGate.await(120, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "LAB_BLOCK_WAIT_TIMEOUT");
                    }
                }
                case "fail" -> throw new IllegalStateException(
                        "LAB_INTENTIONAL_WORKER_FAILURE");
                default -> Thread.sleep(300);
            }

            succeeded.incrementAndGet();
            jobs.put(id, new JobView(id, kind, "DONE", thread));
            System.out.println("LAB_DONE id=" + id);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            interrupted.incrementAndGet();
            jobs.put(id, new JobView(
                    id, kind, "INTERRUPTED", thread));
            System.out.println("LAB_INTERRUPTED id=" + id);
        } catch (Exception ex) {
            failed.incrementAndGet();
            jobs.put(id, new JobView(
                    id, kind, "FAILED", ex.getMessage()));
            System.out.println("LAB_FAILED id=" + id
                    + " cause=" + ex.getMessage());
        }
    }

    public void releaseBlockedJobs() {
        releaseGate.countDown();
    }

    public JobView find(String id) {
        return jobs.get(id);
    }

    public Stats stats() {
        ThreadPoolExecutor pool = executor.getThreadPoolExecutor();
        return new Stats(
                executor.getPoolSize(),
                executor.getActiveCount(),
                pool.getQueue().size(),
                pool.getQueue().remainingCapacity(),
                accepted.get(),
                rejected.get(),
                succeeded.get(),
                failed.get(),
                interrupted.get());
    }

    public record Submission(String id, String state) {
    }

    public record JobView(
            String id, String kind, String state, String detail) {
    }

    public record Stats(
            int poolSize,
            int active,
            int queued,
            int queueRemaining,
            int accepted,
            int rejected,
            int succeeded,
            int failed,
            int interrupted) {
    }
}
~~~

**Các quyết định trong lab:**

1. `executor.execute(...)` nộp task nhưng **không đợi** task chạy xong. Nếu nhận thành công, API trả `ACCEPTED`; nếu queue và workers hết chỗ, `TaskRejectedException` được bắt ngay ở **thread đang nộp việc**.
2. `JobView` được lưu trong `ConcurrentHashMap` với các state `QUEUED` → `RUNNING` → `DONE`/`FAILED`/`INTERRUPTED`. Rejection tạo `REJECTED` và task không chạy.
3. `"block"` dùng `CountDownLatch.await(120, TimeUnit.SECONDS)` để giữ các worker trong lab; endpoint release cho chúng hoàn thành. Đây là công cụ **thử tải có kiểm soát**, không phải mô hình queue nghiệp vụ.
4. `"fail"` ném `IllegalStateException` bên trong worker. Method `runJob` bắt nó và ghi state `FAILED`, nên HTTP response lúc submit vẫn có thể là `202 Accepted`. **Không** đồng nhất accepted với succeeded.
5. `InterruptedException` có xử lý riêng, khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` rồi ghi `INTERRUPTED`; không dùng catch-all để nuốt lệnh shutdown.
6. `getPoolSize()`, `getActiveCount()`, `getThreadPoolExecutor().getQueue().size()` là metric snapshot; chúng có thể thay đổi giữa các phép đọc, nên không phải một transaction atomic.
7. Đếm accepted/rejected/succeeded/failed/interrupted chỉ nhằm quan sát. Khi worker chạy rất nhanh, `succeeded` có thể tăng trước lúc thread nộp kịp tăng `accepted`, tạo snapshot chênh lệch ngắn; không dùng chênh lệch như bất biến tức thời.
8. `ConcurrentHashMap` lưu toàn bộ job đã nộp **không có giới hạn hoặc TTL trong lab**. Production phải chọn retention, cleanup, persistent job store, giới hạn kích thước/cấp phát bộ nhớ và xử lý restart. Pool bounded **không** tự làm registry job bounded.

### 5.5. Controller nhận việc và báo backpressure qua HTTP

File `JobController.java`:

~~~java
package com.example.boundedworker;

import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class JobController {

    private static final Set<String> VALID_KINDS =
            Set.of("quick", "block", "fail");

    private final JobService service;

    public JobController(JobService service) {
        this.service = service;
    }

    @PostMapping("/lab/jobs")
    public ResponseEntity<?> submit(
            @RequestParam(defaultValue = "quick") String kind) {

        if (!VALID_KINDS.contains(kind)) {
            return ResponseEntity.badRequest().body(
                    Map.of("error",
                            "kind must be quick, block, or fail"));
        }

        JobService.Submission submission = service.submit(kind);

        if (submission.state().equals("REJECTED")) {
            return ResponseEntity.status(
                    HttpStatus.TOO_MANY_REQUESTS).body(submission);
        }
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(submission);
    }

    @GetMapping("/lab/jobs/{id}")
    public ResponseEntity<?> find(@PathVariable String id) {
        JobService.JobView job = service.find(id);

        if (job == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(Map.of("error", "unknown job id"));
        }
        return ResponseEntity.ok(job);
    }

    @GetMapping("/lab/stats")
    public JobService.Stats stats() {
        return service.stats();
    }

    @PostMapping("/lab/release")
    public Map<String, Boolean> release() {
        service.releaseBlockedJobs();
        return Map.of("released", true);
    }
}
~~~

Với ứng dụng đang chạy và controller không bị security chặn:

- `POST /lab/jobs?kind=quick` → HTTP 202 nếu executor nhận task.
- `POST /lab/jobs?kind=block` → HTTP 202 nếu có chỗ; task chờ trên latch.
- `POST /lab/jobs?kind=fail` → HTTP 202 khi accepted, nhưng sau đó state `FAILED`.
- Khi pool đầy: HTTP **429** với JSON `state=REJECTED`. Trong production có thể bổ sung `Retry-After` theo khả năng phục hồi có cơ sở, không tùy tiện đoán.
- `GET /lab/jobs/{id}` → trạng thái cụ thể của job.
- `GET /lab/stats` → metric executor và counters.
- `POST /lab/release` → mở latch **một lần** cho các job block; sau đó latch không thể reset. Restart app để tái lập saturation test.

**Bảo mật:** Đây là API thử nghiệm không có auth/rate limit. `POST /lab/release` và các loại job cố ý gây lỗi/block phải **không có** trên production public API. Cần giới hạn body/size/tenant/token cho API thực.

### 5.6. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=bounded-worker-lab
server.address=127.0.0.1
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

`server.address=127.0.0.1` giữ lab trên loopback. Trong Pod/container cần network binding phù hợp; không copy nguyên cấu hình localhost lên Kubernetes khi kubelet hoặc ingress phải kết nối từ interface mạng khác.

## 6. Chạy ứng dụng và kiểm tra job hoàn tất

### 6.1. Maven Wrapper

Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

Maven biên dịch các class và khởi chạy Tomcat. Nếu port 8080 bị chiếm, dừng service cũ hoặc đổi port và URL curl tương ứng. Sau khi Spring Boot hoàn thành startup, thử trong terminal thứ hai:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=quick"
curl -i "http://127.0.0.1:8080/lab/stats"
~~~

Response submit điển hình:

~~~json
{"id":"<UUID-thuc-te>","state":"ACCEPTED"}
~~~

`<UUID-thuc-te>` là **chỗ ký hiệu giá trị thay đổi trong mô tả**, không phải chuỗi ID literal do API trả; response thật có UUID v4 cụ thể. Bạn phải sao chép ID được trả về, ví dụ `b2e2c77c-6ef3-4554-9221-69831a9c1141` nếu log của bạn cho ra ID đó. Đây chỉ là **ví dụ định dạng**, không phải kết quả chạy đo được.

Tiếp tục:

~~~bash
curl -i "http://127.0.0.1:8080/lab/jobs/<UUID-thuc-te>"
~~~

Thay phần trong dấu `<...>` bằng ID thực tế **trước khi chạy lệnh**; không gửi nguyên ký hiệu placeholder qua shell. Job có thể đang `QUEUED` hoặc `RUNNING` nếu gọi quá sớm; vài trăm mili-giây sau, nó sẽ có `state=DONE` trong điều kiện máy bình thường. `HTTP 202` chỉ là xác nhận **đã được đưa vào executor**, không bảo đảm job hoàn thành.

### 6.2. Dấu hiệu trong log

Log ngắn gọn cho một job sẽ có các marker kiểu:

~~~text
LAB_SUBMITTED id=<id> kind=quick
LAB_RUNNING id=<id> thread=lab-worker-1
LAB_DONE id=<id>
~~~

**Không ràng buộc tuyệt đối** thứ tự các dòng `LAB_SUBMITTED` và `LAB_RUNNING`: worker có thể bắt đầu chạy trước khi request thread hoàn tất ghi log “submitted” vì đó là hai threads độc lập. Điều phải đúng là job không có state `DONE`/`FAILED` nếu chưa từng được executor chấp nhận và thực thi.

Tên worker `lab-worker-1` cũng chỉ minh họa; thực tế có thể `lab-worker-2`, `lab-worker-3`... theo lịch cấp thread.

## 7. Saturation test: 6 accepted, request thứ 7 bị từ chối

Trong **một JVM mới chạy**, trước khi gọi `/lab/release`, nộp liên tiếp bảy công việc `block`. Chúng chờ trên latch tối đa 120 giây; cần thao tác trong khoảng đó để giữ điều kiện thử nghiệm.

Trên Linux/macOS:

~~~bash
for i in 1 2 3 4 5 6 7; do
  curl -s -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=block"
done
curl -s "http://127.0.0.1:8080/lab/stats"
~~~

Trên Windows PowerShell:

~~~powershell
1..7 | ForEach-Object {
    curl.exe -s -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=block"
}
curl.exe -s "http://127.0.0.1:8080/lab/stats"
~~~

Trong điều kiện các job chưa hết timeout và chưa release, dự kiến:

- Sáu response HTTP **202 Accepted** với những UUID khác nhau.
- Response thứ bảy HTTP **429 Too Many Requests**, body có `state=REJECTED`.
- `poolSize` có thể là **4**, `active` **4**, `queued` **2**, `queueRemaining` **0**.
- `accepted` khoảng **6**, `rejected` **1**, `succeeded` **0** cho những job block.
- Có bốn `LAB_RUNNING` đến từ worker threads, hai job vẫn ở `QUEUED`.
- `LAB_REJECTED` in ID của job bị từ chối; job đó không được execute.

Đây là thí nghiệm cố ý khóa tasks. Trong điều kiện tác vụ hoàn tất, timeout hoặc môi trường bị chậm quá lâu giữa các lệnh, các số snapshot có thể khác. Hãy restart JVM để làm mới latch và counters nếu cần tái lập đúng bảng.

### 7.1. Mở latch và quan sát queue drain

Ở terminal thứ hai:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/lab/release"
curl -i "http://127.0.0.1:8080/lab/stats"
~~~

Ngay sau release, bốn workers đang block sẽ tiến tới `DONE`; hai task trong queue sẽ lần lượt được lấy ra và hoàn thành. Hãy gọi lại `/lab/stats` sau khi log có sáu marker `LAB_DONE` để thấy `queued=0`, `active=0` và `succeeded=6` cho bảy submission của thí nghiệm. Pool có thể vẫn có `poolSize=4` trong một thời gian do keep-alive; không nhầm “thread còn tồn tại trong pool” với “thread đang chạy task”.

`JobView` của job rejected vẫn ở `REJECTED`. Khi pool rảnh, nó **không tự chạy bù** nếu không có logic retry/re-enqueue được thiết kế. Trong production, client cần được thông báo từ chối và có chiến lược retry với backoff hoặc đưa công việc vào hệ thống bền vững.

### 7.2. Tính chất đáng lưu ý

Lưu lượng tối đa đang được ghi nhớ trong executor ở ví dụ có thể gồm **4 task chạy + 2 task chờ**, nhưng `ConcurrentHashMap jobs` và dữ liệu trong request vẫn tiêu tốn thêm bộ nhớ. Vì vậy giới hạn đồng thời không đồng nghĩa toàn bộ memory footprint đã được chặn; phải giới hạn kích thước payload, số job records lưu lại, request rate và số người dùng/tenant.

Khi một job block có I/O hoặc giữ connection, nó vẫn chiếm worker dù không sử dụng CPU. Đó là lý do capacity planning cho I/O-bound và CPU-bound task khác nhau.

## 8. Hai loại lỗi phải được xử lý ở hai ranh giới

### 8.1. Lỗi thứ nhất: không thể submit

Trong `JobService.submit(...)`:

~~~java
try {
    executor.execute(() -> runJob(id, kind));
    return new Submission(id, "ACCEPTED");
} catch (TaskRejectedException ex) {
    return new Submission(id, "REJECTED");
}
~~~

Snippet này là phiên bản rút gọn; class runnable ở mục 5 chứa đầy đủ counters và state transitions. Nếu pool full/shutting down và dùng AbortPolicy, executor báo rejection **đồng bộ cho thread submit**. Tại HTTP boundary, có thể trả 429 hoặc 503 theo chính sách, rồi để client xử lý kết quả.

Không retry vô hạn ngay bên trong controller bằng vòng `while(true)`: với pool đang full, retry tức thì làm tăng CPU và latency mà không tạo thêm capacity. Cần backoff/jitter và deadline. Nếu không thể từ chối việc quan trọng, phải có một durable queue/DB transaction được thiết kế có sức chứa và vận hành rõ ràng, thay vì im lặng drop.

### 8.2. Lỗi thứ hai: task đã chạy nhưng thất bại

Submit một job cố ý fail khi pool rảnh:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=fail"
~~~

Response thường vẫn là **202 Accepted** kèm ID. Sau đó:

~~~bash
curl -i "http://127.0.0.1:8080/lab/jobs/<ID-that>"
~~~

Thay ID thật ở lệnh curl. Khi worker đã chạy, body có `state="FAILED"` và `detail="LAB_INTENTIONAL_WORKER_FAILURE"`. Console có:

~~~text
LAB_FAILED id=<id> cause=LAB_INTENTIONAL_WORKER_FAILURE
~~~

Lỗi nằm **sau khi** executor chấp nhận task, nên handler HTTP của bước submit không thể chờ bắt nó bằng một `catch` quanh `execute(...)` như thể đang xử lý đồng bộ. `JobService.runJob(...)` phải tự bắt và ghi state; một cách khác là `submit(Callable)` trả `Future` để luồng quan sát đọc `ExecutionException` từ `Future.get()`.

**Phân biệt:** `202 Accepted` không phải `200 completed`. API tốt trả `jobId` và cung cấp cách truy vấn status, polling có giới hạn hoặc callback/webhook đáng tin cậy; không trả kết quả thành công giả trong khi job còn chưa chạy.

### 8.3. Lỗi thứ ba: cancellation / interrupt / timeout

Khi worker chờ `CountDownLatch.await(...)` và context shutdown hoặc task bị cancel có interrupt, `InterruptedException` báo yêu cầu ngắt. Code mẫu:

- Gọi `Thread.currentThread().interrupt()` để khôi phục cờ interrupt.
- Ghi trạng thái `INTERRUPTED` tách với lỗi nghiệp vụ.
- Không tiếp tục làm việc như không có chuyện gì.
- Không giữ lock hoặc bỏ qua cleanup nếu cần dừng resource.

Hết timeout chờ latch sau 120 giây làm job `FAILED` với marker `LAB_BLOCK_WAIT_TIMEOUT`. Đây là **timeout do task kiểm soát**, khác với request timeout của Tomcat và khác `awaitTerminationSeconds` khi shutdown. Một task chạy quá lâu không tự bị executor giết chỉ vì hàng đợi có capacity nhỏ.

Trong production cần **deadline xuyên suốt** cho job, timeout khi gọi DB/HTTP/broker, circuit breaker/bulkhead, cancel policy và cleanup trong `finally`.

## 9. @Async và CompletableFuture: cơ chế khác, cùng bài toán giới hạn

Spring hỗ trợ gọi method có `@Async` qua AOP proxy để đưa việc sang `TaskExecutor`. Đây là cách viết gọn, nhưng **không loại bỏ** yêu cầu bounded pool, rejection, exception handling và context propagation.

### 9.1. Ví dụ mở rộng có thể thêm vào project

Thêm `@EnableAsync` trên main class:

~~~java
@SpringBootApplication
@EnableAsync
public class BoundedWorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundedWorkerApplication.class, args);
    }
}
~~~

Đây là **snippet thay thế main class** cùng package như mục 5; thêm import `org.springframework.scheduling.annotation.EnableAsync`. Không giữ hai class `BoundedWorkerApplication` trùng tên trong project.

Tạo một bean mới:

~~~java
package com.example.boundedworker;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncReportService {

    @Async("boundedWorkerExecutor")
    public CompletableFuture<String> generate(String id) {
        if ("fail".equals(id)) {
            throw new IllegalStateException("LAB_ASYNC_FAILURE");
        }
        return CompletableFuture.completedFuture("report-" + id);
    }
}
~~~

Đoạn trên là **file Java hoàn chỉnh khi đã bật `@EnableAsync`** và đặt đúng package/classpath. `@Async("boundedWorkerExecutor")` chỉ rõ executor được chọn; không cần phụ thuộc vào tên bean mặc định hoặc việc Spring Boot auto-configure `applicationTaskExecutor`.

Một bean **khác** gọi `asyncReportService.generate("x")` sẽ nhận `CompletableFuture`. Nếu method ném lỗi trong worker, future sẽ hoàn thành exceptionally; code gọi có thể dùng `whenComplete(...)`, `exceptionally(...)`, `handle(...)` hoặc `join()` để quan sát và xử lý. Khi `join()` gặp lỗi, nó thường ném `CompletionException` chứa nguyên nhân.

**Cảnh báo quan trọng:**

- Gọi `this.generate("x")` từ **cùng bean** thường bypass Spring proxy, nên `@Async` không được áp dụng theo proxy mode mặc định.
- `private` method hoặc tự tạo object bằng `new` không phải phương án bảo đảm được AOP intercept.
- `@Async` trên method `void` không trả future cho caller; exception không thể được truyền qua future và có thể được log bởi `AsyncUncaughtExceptionHandler`. Nếu cần audit/retry, **ưu tiên future hoặc service tự ghi job state**.
- `@Async` submission cũng có thể bị executor reject ngay lúc proxy dispatch; caller cần xử lý đường từ chối riêng, không chỉ `future.exceptionally(...)`.
- Nếu future được trả về ngay trong HTTP controller mà chưa xây API async đúng nghĩa, không tự coi JSON response là kết quả job. Chọn contract trả 202 + ID hoặc Spring MVC async response phù hợp.
- Không dùng một executor quá nhỏ chung cho cả HTTP async handling và background jobs quan trọng nếu chúng có thể starve lẫn nhau.

### 9.2. Tại sao void @Async dễ làm mất lỗi?

Ví dụ snippet:

~~~java
@Async("boundedWorkerExecutor")
public void sendNotification() {
    throw new IllegalStateException("notification failed");
}
~~~

Nếu không có `Future`, caller không thể `join/get` để lấy exception này; Spring có handler cho uncaught exceptions của `void @Async`, mặc định thường ghi log. Muốn chính sách rõ hơn, có thể cấu hình `AsyncConfigurer.getAsyncUncaughtExceptionHandler()` và metrics/alert. Nhưng một log error **không** đồng nghĩa job đã được retry, chuyển DLQ hoặc đánh dấu failed trong kho bền vững.

### 9.3. Spring Boot auto-configure executor và property

Spring Boot 3.5 có task execution auto-configuration. Nếu không có custom `Executor` bean, Boot có thể tự cung cấp `AsyncTaskExecutor`; với platform threads, thường là `ThreadPoolTaskExecutor`. Khi Java 21+ bật virtual threads, lựa chọn executor và tác động của các pool properties khác đi. Vì lab đặt tên executor riêng và inject rõ `@Qualifier`, nó không dựa vào lựa chọn mặc định đó.

Các properties sau **dành cho executor do Boot auto-configure**, không tự thay đổi bean `boundedWorkerExecutor` được code tự tạo ở mục 5:

~~~properties
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=100
spring.task.execution.pool.keep-alive=30s
~~~

Không thêm chúng vào `application.properties` của lab rồi nghĩ chúng override code `setCorePoolSize(2)`. Muốn cấu hình bean custom theo properties, sử dụng `@ConfigurationProperties` hoặc `@Value`/builder và gắn đúng instance, cùng validation constraints.

Trong Spring Boot 3.5, đăng ký custom `Executor` có thể làm auto-configuration back off; Spring MVC/WebFlux/GraphQL async integrations có yêu cầu riêng với bean tên `applicationTaskExecutor`. Nếu cần vừa pool nghiệp vụ tách biệt vừa executor framework mặc định, nghiên cứu `@Bean(defaultCandidate=false)` (Boot 3.5/Spring Framework 6.2 tương ứng), `spring.task.execution.mode=force` hoặc khai báo executor phù hợp. Không đổi cơ chế toàn application chỉ để giải quyết một queue nghiệp vụ.

## 10. Tác vụ nền là một hệ thống điều tiết tải, không phải chỉ một Executor

### 10.1. Ước lượng capacity

Một nguyên tắc ước lượng sơ bộ theo **Little's Law**:

\[
L = \lambda \times W
\]

Trong đó `L` là số việc trung bình trong hệ thống, `\lambda` là số việc đến mỗi giây, và `W` là thời gian chờ + xử lý trung bình. Với 10 jobs/s và thời gian lưu trong hệ thống 0,8 s, trung bình có khoảng 8 jobs outstanding trong điều kiện ổn định. Đây là **ước lượng**, không phải công thức chọn trực tiếp queue capacity hoặc trần threads. Phải đo tail latency, burstiness, memory per job, retry và downstream pool limits.

Với CPU-bound work, số worker quá lớn gây context switching; với blocking I/O, số worker có thể lớn hơn số cores nhưng vẫn phải tôn trọng database connection pool, API rate limit và thời gian chờ. Dùng load tests phản ánh workload thật để chọn `core/max/queue` và SLO.

### 10.2. Semaphore để giới hạn tài nguyên hẹp hơn pool

Giả sử executor có 4 threads nhưng đối tác chỉ cho tối đa 2 request đồng thời. Có thể dùng `Semaphore(2)` quanh lời gọi đối tác:

~~~java
private final Semaphore gatewayPermits = new Semaphore(2);

public void callGateway() throws InterruptedException {
    if (!gatewayPermits.tryAcquire(2, TimeUnit.SECONDS)) {
        throw new IllegalStateException("gateway overloaded");
    }
    try {
        invokeExternalGatewayWithTimeout();
    } finally {
        gatewayPermits.release();
    }
}
~~~

**Đây là snippet thiết kế**, cần import `Semaphore`/`TimeUnit`, định nghĩa `invokeExternalGatewayWithTimeout()` và bean/scope thích hợp. Semaphore giới hạn **số threads có thể vào critical section của một instance**; không bảo đảm quota toàn cụm. Dùng `tryAcquire` có deadline thay vì để mọi worker block vô hạn; nếu không, bản thân semaphore lại trở thành hàng đợi ẩn làm cạn pool.

### 10.3. Rate limit khác concurrency limit

- **Rate limit** giới hạn số request/job **theo thời gian**, ví dụ 100/s.
- **Concurrency limit** giới hạn số việc **cùng lúc**, ví dụ 4.
- **Queue capacity** giới hạn việc **đã nhận nhưng còn chờ**.
- **Timeout** giới hạn thời gian một lần chờ hoặc thực hiện.
- **Backpressure** báo nguồn giảm tốc, thử lại có kiểm soát hoặc từ chối.

Một hệ thống với 10.000 tasks cực nhanh mỗi giây có thể không vi phạm concurrency=4 nhưng vẫn quá tải DB network. Ngược lại, 4 requests bị treo 10 phút có thể chiếm toàn pool dù throughput thấp. Phải thiết kế kết hợp các giới hạn, không dùng một tham số cho mọi vấn đề.

## 11. Retry, DLQ và tính idempotent

Khi job lỗi, không thể đơn giản `catch (Exception e) { executor.execute(task); }` rồi chạy lại vô hạn:

1. Lỗi vĩnh viễn (dữ liệu sai, business rule vi phạm) sẽ tiếp tục thất bại.
2. Retry ngay tạo “retry storm”, chiếm hết queue, chặn job mới.
3. Nếu side effect thành công một phần nhưng process fail trước khi ghi trạng thái, retry có thể gửi trùng email, trừ tiền hoặc ghi trùng.
4. Khi JVM restart, queue RAM và registry trong ví dụ mất; `ThreadPoolTaskExecutor` không phải broker bền vững.
5. Exception do shutdown/interruption cần chính sách khác lỗi kết nối tạm thời.

Một thiết kế production nên xác định:

- **Idempotency key** ổn định cho cùng business job, ví dụ `(tenantId, orderId, operationType)` hoặc event ID ổn định.
- **Retry taxonomy:** transient, permanent, cancelled, timeout; giới hạn số lần thử.
- **Delay:** exponential backoff có jitter, không `Thread.sleep` dài ngay trên worker khan hiếm nếu có thể dùng delayed queue/scheduler phù hợp.
- **Visibility timeout/ack:** nếu dùng broker, xác định khi nào ack, khi nào redelivery và ai sở hữu trạng thái.
- **DLQ/quarantine:** job vượt ngưỡng retry được giữ để điều tra thay vì bị drop.
- **Outbox/inbox:** xử lý nguyên tử với database khi cần ghi nhận trạng thái và publish event liên hệ.
- **Compensation:** nếu external side effect không thể transaction chung, định nghĩa recovery/compensation và dùng idempotency contract của provider.

Với API nộp job quan trọng, **đừng trả 202 trước khi có bằng chứng lưu bền** nếu yêu cầu nghiệp vụ là “đã nhận và không được mất khi crash”. Trong lab `202` chỉ nghĩa executor đã accepted vào RAM. Nếu contract production yêu cầu durability, hãy ghi job vào database/queue có xác nhận bền vững **trước** khi trả 202, sau đó worker tiêu thụ.

## 12. Shutdown và vòng đời tác vụ nền

Khi Spring Boot nhận shutdown bình thường, context đóng và managed executors được xử lý theo lifecycle. Hai lựa chọn thường gặp:

| Chính sách | Ý nghĩa | Dùng khi |
|---|---|---|
| Chờ queue và tasks hoàn thành (`waitForTasksToCompleteOnShutdown=true`) | Cho task đã nhận cơ hội hoàn tất, nhưng có thể kéo dài shutdown | Task hữu hạn, timeout rõ, termination budget đủ |
| Không chờ mọi queued tasks (`false`) | Cho phép ngắt/hủy tùy cơ chế shutdown | Job đã nằm trong durable source và có thể redeliver |
| `awaitTerminationSeconds` | Thời gian framework chờ executor chấm dứt | Cần tính cùng shutdown phase và platform grace period |
| Graceful HTTP shutdown | Ngừng nhận request mới, xử lý in-flight requests theo server | Đảm bảo nguồn submit ngừng trước lúc worker bị dispose |

**Quan trọng:** `server.shutdown=graceful` dành cho web server; không biến queue RAM thành durable. `spring.lifecycle.timeout-per-shutdown-phase` giới hạn một shutdown phase, khác `awaitTerminationSeconds` của executor và khác Kubernetes `terminationGracePeriodSeconds`. Nếu task blocking I/O không có timeout hoặc không tôn trọng interrupt, shutdown vẫn có thể quá hạn.

Trong lab, `CountDownLatch.await(...)` có timeout và phản ứng với interrupt; khi shutdown mà còn job block, state có thể là `INTERRUPTED` trước khi JVM kết thúc. Nhưng do registry ở RAM, không nên tuyên bố các trạng thái đó còn được truy vấn sau khi process chết.

**Quy trình vận hành gợi ý:**

1. Ngăn nguồn submit mới bằng readiness/gateway hoặc admission control theo contract.
2. Ngừng nhận message mới ở broker consumer; giữ cơ chế ack/redelivery hợp lệ.
3. Cho queued/running jobs hoàn tất hoặc cancel theo deadline; ghi trạng thái bền vững/ack.
4. Đóng connections/executors trong phase đúng, xử lý lỗi cleanup.
5. Quan sát số việc bị hủy, retry pending và lost work trước khi khởi tạo instance thay thế.

Tránh `kill -9` để “thử graceful”: SIGKILL không đảm bảo chạy shutdown hooks hoặc callbacks.

## 13. Logging, metrics và cảnh báo

Chỉ nhìn `poolSize=4` chưa đủ để đánh giá hệ thống. Cần quan sát theo thời gian:

| Metric/tín hiệu | Ý nghĩa | Cần cảnh báo khi |
|---|---|---|
| `activeCount` | Số threads đang xử lý task | Bám sát max kéo dài |
| `poolSize` | Số worker threads hiện tại | Dao động bất thường hoặc quá thấp so với kỳ vọng |
| `queue.size` | Số task đang chờ | Tăng liên tục hoặc thường xuyên đầy |
| `queue.remainingCapacity` | Chỗ trống queue | Gần 0 trong nhiều khoảng đo |
| Rejection count/rate | Việc không được nhận | Vượt budget hoặc tăng đột biến |
| Queue waiting time | Submit → start mất bao lâu | p95/p99 vượt SLA |
| Execution duration | Thời gian worker chạy | p95/p99 tăng, task bị treo |
| Success/fail/interrupt/cancel | Kết quả thực của job | Tỷ lệ fail lớn hoặc không có recovery |
| Retry attempts / DLQ size | Khối lượng công việc bị lỗi lặp | Backlog tăng ngoài kiểm soát |
| Memory/GC, DB pool, external latency | Tài nguyên bị giới hạn gián tiếp | Queue/pool vẫn nhỏ nhưng dependency nghẽn |

`ThreadPoolTaskExecutor` cung cấp `getActiveCount()` và `getPoolSize()`, đủ cho bài lab. Trong production có thể dùng Spring Boot Actuator/Micrometer để instrument executor/job metrics; việc một metric cụ thể được ghi nhận **phụ thuộc cấu hình instrumentation**, không suy rằng mọi custom executor tự xuất hiện trong dashboard mà không cần kiểm tra.

Một event log nên có job ID, loại việc, submit time, start time, finish time, trạng thái, duration, attempt number, thread name, idempotency key và correlation ID. Tránh log toàn bộ payload chứa secrets/PII. Đừng giữ reference tới `HttpServletRequest` hay request-scoped bean trong `Runnable` sau khi request đã kết thúc.

### 13.1. Context propagation và thread-local

Các thread trong pool có thể được **tái sử dụng** cho jobs khác nhau. Vì vậy:

- MDC/trace context, locale, tenant, transaction, Spring Security context không tự động luôn đi theo khi đổi thread.
- Không mặc định `@Transactional` của HTTP caller “bao” được công việc ở worker thread. Cần transaction độc lập trong method chạy worker nếu cần.
- Khi copy context, dùng `TaskDecorator` hoặc cơ chế context propagation được framework hỗ trợ, theo scope thực tế; **dọn ThreadLocal trong finally** để không rò dữ liệu giữa request.
- Không copy password/token hoặc SecurityContext rộng hơn mức cần thiết; ưu tiên chuyển dữ liệu nghiệp vụ đã xác thực và kiểm tra quyền cần thiết ở boundary.
- Khi job cần retry sau restart, trace/tenant/user identity cần được lưu với ngữ nghĩa phù hợp trong durable job metadata, không dựa ThreadLocal sống tạm.

## 14. Tác vụ Scheduled và các loại executor khác

`@Scheduled` có thể được cấu hình bởi `TaskScheduler`; các properties `spring.task.scheduling.*` không đồng nhất với `spring.task.execution.*`. Nếu một scheduled job chỉ tạo ra background tasks liên tục, phải giới hạn tốc độ submit; scheduler chạy một thread không có nghĩa queue ở executor bên dưới sẽ không bị bão hòa.

Java `Executors.newFixedThreadPool(n)` có queue backing không giới hạn theo implementation mặc định; chỉ vì thread count cố định không có nghĩa memory backlog đã bị chặn. Tự tạo `newCachedThreadPool()` có thể sinh rất nhiều threads khi request đồng loạt blocking, nên vẫn cần giới hạn.

Với **Java 21+ virtual threads**, số virtual threads không phải quota cho database, network hoặc CPU. Virtual threads giảm chi phí thread-per-task trong nhiều tình huống blocking, nhưng **không thay thế** giới hạn concurrency tới external resource, backpressure, request budgets và durable job handling.

Nếu lựa chọn một broker thay vì thread pool RAM, vẫn cần cấu hình consumer concurrency, prefetch/inflight, ack policy, retries, DLQ và quota. Broker không tự xử lý một tác vụ không idempotent bị giao lại.

## 15. Chẩn đoán nhanh các lỗi phổ biến

| Triệu chứng | Giả thuyết | Cách kiểm tra |
|---|---|---|
| Đặt max=32 nhưng active luôn quanh core=2 | Queue chưa đầy hoặc quá lớn | Kiểm `queueCapacity`, `queue.size` và thời điểm saturation |
| App OOM dù chỉ có 2 worker | Queue hoặc job registry giữ object quá nhiều | Heap histogram, queue size, payload size, retention |
| Submit trả 500 khi pool bão hòa | Rejection không được map thành HTTP response | Bắt `TaskRejectedException` ở submission boundary |
| HTTP 202 nhưng job chưa chạy | Task đang nằm trong queue | Truy vấn state `QUEUED`, queue metrics |
| HTTP 202 rồi job thất bại | Exception trong worker | Ghi FAILED state, error category, retry policy |
| `@Async` method vẫn chạy đồng bộ | Tự gọi trong cùng bean, không qua proxy, thiếu `@EnableAsync` | Kiểm proxy invocation, bean Spring-managed |
| `void @Async` lỗi nhưng caller không biết | Không có Future/observability | Async exception handler hoặc trả CompletableFuture |
| `CallerRunsPolicy` khiến HTTP chậm đột biến | Runnable bị chạy trên request thread | Đo thread name, pool rejection policy |
| Job bị xử lý đôi sau retry | Thiếu idempotency key/dedupe | Kiểm business ID, durable inbox, provider idempotency |
| Shutdown làm mất queued work | Queue RAM và policy không đợi/hủy | Dùng durable store hoặc chấp nhận at-most-once rõ ràng |
| Job không bao giờ dừng | Blocking I/O không timeout/không tôn trọng interrupt | Thread dump, deadlines, graceful shutdown budget |
| Metrics queue thấp nhưng request vẫn chậm | Worker/DB pool/upstream đã bottleneck | Đo end-to-end latency, DB pool, external quotas |
| Nhiều replicas gây vượt quota upstream | Giới hạn chỉ per JVM | Tổng concurrency và distributed bulkhead |
| Job RUNNING mãi sau process crash | Trạng thái chỉ in-memory hoặc lease thiếu expiry | Durable job lease/heartbeat, redelivery protocol |
| Queue rỗng mà executor từ chối | Executor đang shutdown hoặc pool lifecycle lỗi | Log lifecycle, shutdown state, exception type |
| Dùng `Future.get()` trong HTTP request rồi timeout | Biến async thành blocking chờ kết quả | Thiết kế 202 + status, hoặc async MVC response với timeout hợp lệ |

## 16. Bài tập thực hành và tiêu chí nghiệm thu

### Bài tập A — Job bình thường

Chạy lab, POST `kind=quick`, ghi ID thật, gọi GET status cho tới `DONE`. Xác minh `accepted` tăng khi nộp và `succeeded` tăng khi task hoàn tất. Phân biệt 202 Accepted với trạng thái DONE.

### Bài tập B — Bão hòa executor

Restart app để latch chưa release. Gửi 7 POST `kind=block` nhanh trong 120 giây. Xác nhận 6 accepted, 1 rejected theo cấu hình `core=2, max=4, queue=2` và snapshot active/queued. Gọi `/lab/release` và chờ queue drain. Không suy đoán nếu job đã timeout trước khi submit xong.

### Bài tập C — Worker exception

Khi pool rảnh, POST `kind=fail`. Quan sát HTTP 202 trước và trạng thái `FAILED` sau, cùng marker `LAB_INTENTIONAL_WORKER_FAILURE`. Giải thích tại sao `catch` quanh `execute(...)` không bắt được exception bên trong worker nếu task tự xử lý hoặc future nhận exception.

### Bài tập D — Rejection policy

Trong bản copy lab, so sánh `AbortPolicy` với `CallerRunsPolicy` trên cùng workload block. Quan sát response latency và thread name thực thi task nếu submission bị quá tải. **Không** dùng policy bỏ task âm thầm cho job thật. Khôi phục AbortPolicy sau thí nghiệm.

### Bài tập E — Kiểm soát resource

Giả sử một upstream chỉ cho 2 kết nối đồng thời trong khi pool max 4. Đề xuất `Semaphore(2)`, deadline khi acquire, metric reject/timeout và retry policy. Tính giới hạn tổng khi có 3 replicas; mô tả cách bảo vệ upstream nếu quota là toàn cụm.

### Bài tập F — Độ bền khi crash

Đánh giá thử: sau khi HTTP API trả 202 nhưng job còn trong queue RAM, JVM bị kill cưỡng bức. Job có được khôi phục không? Với lab là **không có bảo đảm**. Thiết kế bảng DB hoặc broker có ack + retry + idempotency key, chỉ trả 202 sau khi lưu thành công theo contract nghiệp vụ.

### Bảng xác nhận

| Thử nghiệm | Bằng chứng cần giữ | Kết luận |
|---|---|---|
| Quick task | 202, UUID, cuối cùng DONE | Submit khác completion |
| Saturation | 6 accepted, 1 rejected, queue đầy | Bounded capacity và rejection |
| Release | Queue giảm, succeeded tăng | Worker tiếp tục lấy task từ queue |
| Intentional fail | 202 rồi FAILED | Lỗi trong worker khác lỗi submit |
| Shutdown | Logs interrupt/stop tùy thời điểm | Queue RAM không bền qua process |
| Async proxy | Caller nhận Future và thấy exception | Exception path của `@Async` |
| Retry/durability design | Idempotency key, ack/inbox/outbox | Chuẩn bị cho at-least-once delivery |

### Checklist cuối

- [ ] Đọc đúng `corePoolSize`, `maxPoolSize` và `queueCapacity`.
- [ ] Giải thích tại sao queue lớn ngăn pool tăng lên max sớm.
- [ ] Biết chỗ bắt `TaskRejectedException`.
- [ ] Biết phân biệt QUEUED/RUNNING/DONE/FAILED/REJECTED/INTERRUPTED.
- [ ] Chạy được Maven project Java 17/Spring Boot 3.5.x.
- [ ] Kiểm chứng HTTP 202 không đồng nghĩa job thành công.
- [ ] Tái lập được saturation với 7 POST kind=block.
- [ ] Kiểm tra queue/active/pool và biết snapshot là số liệu biến đổi.
- [ ] Chứng minh worker exception không bị catch bởi submission handler.
- [ ] Hiểu `@Async` proxy và cách bắt exception qua CompletableFuture.
- [ ] Chỉ ra khác biệt queue RAM so với durable job store.
- [ ] Đặt được concurrency limit, timeout, retry với idempotency.
- [ ] Mô tả chuẩn shutdown và lý do cần interruption/cleanup.
- [ ] Có metric và alert cho rejections, backlog, failure và latency.

## 17. Tài liệu chính thức

1. Spring Framework 6.2 — Task Execution and Scheduling, `@Async` và exception management: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
2. Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc, queue capacity và metrics: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
3. Spring Framework — `TaskRejectedException`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskRejectedException.html
4. Spring Boot 3.5 — Task Execution and Scheduling auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
5. Java SE 17 — `ThreadPoolExecutor` và rejection handlers: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
6. Java SE 17 — `CountDownLatch` và `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html

**Kết luận:** Với task nền, “có executor” chỉ là điểm bắt đầu. Hãy **giới hạn số worker và queue**, chấp nhận rejection có chủ đích, theo dõi job state và lỗi, áp dụng retry/idempotency theo contract, và bảo vệ shutdown/restart. Một HTTP 202 chỉ nên mang đúng nghĩa ứng dụng đã **nhận việc theo mức bảo đảm đã công bố**, không được tự biến thành lời hứa rằng công việc chắc chắn hoàn tất.