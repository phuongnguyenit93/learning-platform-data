# ThreadPoolTaskExecutor quản lý nhóm luồng tái sử dụng trong Spring Framework

Một dịch vụ Spring có thể cần tạo báo cáo, gửi thông báo, xử lý tài liệu hoặc gọi dịch vụ ngoài mà không giữ thread tiếp nhận request cho tới khi công việc kết thúc. Tạo `new Thread(...)` cho từng yêu cầu không phải chiến lược tốt khi số lượng task tăng: thread nền tảng cần stack, bộ nhớ và công lập lịch; số luồng mất kiểm soát sẽ gây tranh chấp tài nguyên. **`ThreadPoolTaskExecutor`** là implementation `TaskExecutor` của Spring bao quanh một **`java.util.concurrent.ThreadPoolExecutor`**, cung cấp nhóm worker có thể tái sử dụng, hàng đợi, giới hạn số luồng, chính sách từ chối và lifecycle do Spring quản lý.

Để **chọn bộ thực thi** đúng, cần hiểu hai việc: **công việc được đưa vào pool như thế nào** và **pool tiếp nhận bao nhiêu công việc trước khi phải xếp hàng hoặc từ chối**. Chỉ gắn `@Async` lên một method không bảo đảm hiệu năng, độ tin cậy hay thread safety.

## 1. Task, worker, executor và queue: bốn vai trò

- **Task:** một việc được biểu diễn bằng `Runnable` (không có giá trị trả về trực tiếp) hoặc `Callable<T>` (có kết quả).
- **Worker thread:** luồng thực thi task. Sau khi hoàn thành, worker thường lấy task khác thay vì bị hủy và tạo lại.
- **Executor:** nhận task và điều phối thực thi theo cấu hình, cho caller có thể tiếp tục trước khi task hoàn tất.
- **Queue:** giữ các task đã nhận nhưng chưa có worker xử lý.

```text
Controller / Service / @Async proxy
                  │
                  │ submit(task)
                  ▼
         ThreadPoolTaskExecutor
                  │
                  ▼
          ThreadPoolExecutor
           ├── worker-1: Task A → Task D → Task G
           ├── worker-2: Task B → Task E
           ├── worker-3: Task C → Task F
           └── Waiting queue: [Task H] [Task I] ...
```

Mũi tên trong cùng một worker minh họa **luồng tái sử dụng để chạy nhiều task theo lượt**, không phải một task được chạy lặp. Tái sử dụng giúp giảm chi phí tạo/hủy platform thread và cho phép kiểm soát mức độ đồng thời.

**Các abstraction liên quan:**

| Khái niệm | Thành phần | Trách nhiệm |
| --- | --- | --- |
| JDK executor cơ bản | `Executor` | `execute(Runnable)` |
| JDK executor có lifecycle/Future | `ExecutorService` | `submit`, `Future`, `shutdown` |
| JDK pool | `ThreadPoolExecutor` | Thuật toán core/queue/max/rejection |
| Spring executor | `TaskExecutor` / `AsyncTaskExecutor` | Cách giao task thống nhất cho các Spring component |
| Spring pool executor | `ThreadPoolTaskExecutor` | Bean cấu hình pool và lifecycle, dùng JDK ThreadPoolExecutor |
| Spring async invocation | `@EnableAsync`, `@Async` | Proxy chuyển lời gọi method qua executor được chọn |
| Spring scheduler | `TaskScheduler`, `@Scheduled` | Kích hoạt task theo lịch |

**`@Async` không đồng nghĩa `ThreadPoolTaskExecutor`.** Annotation chỉ chọn cách chuyển lời gọi; executor có thể là implementation khác. Ngược lại, ta có thể inject `ThreadPoolTaskExecutor` và gọi `execute(...)` hoặc `submit(...)` mà không dùng `@Async`.

## 2. Thuật toán core → queue → max → rejection

Cấu hình ví dụ:

```java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(4);
executor.setQueueCapacity(2);
```

Giả định pool vừa khởi tạo và **các task đã bắt đầu đều chưa kết thúc**. Khi task mới được gửi, `ThreadPoolExecutor` về cơ bản:

1. Nếu số worker hiện có ít hơn `corePoolSize`, tạo worker mới để xử lý task.
2. Khi đã đạt core, thử xếp task vào queue.
3. Nếu queue đầy, thử mở rộng worker nhưng không vượt `maxPoolSize`.
4. Nếu queue đầy **và** đã đạt max, chuyển cho chính sách từ chối.

| Task đến | Trạng thái | Kết quả khi task trước chưa hoàn tất |
| --- | --- | --- |
| #1 | Chưa đạt core=2 | Tạo worker #1 |
| #2 | Chưa đạt core=2 | Tạo worker #2 |
| #3 | Đã đạt core, queue còn chỗ | Chờ trong queue (1) |
| #4 | Đã đạt core, queue còn chỗ | Chờ trong queue (2) |
| #5 | Queue đầy, pool chưa đạt max=4 | Tạo worker #3 |
| #6 | Queue đầy, pool chưa đạt max=4 | Tạo worker #4 |
| #7 | Queue đầy, đã đạt max | Từ chối theo policy |

Bảng này không phải lời hứa thứ tự task sẽ chạy trong hệ thống thật. Nếu worker vừa rảnh, nó có thể lấy task đang chờ, khiến queue/pool thay đổi. Bài toán được cố định để thấy **quyết định tiếp nhận task**.

**Điểm khó nhớ nhất:** pool ưu tiên **xếp hàng sau khi đủ core**, rồi **mới tăng vượt core khi queue đầy**. Vì vậy, với `core=2, max=20, queueCapacity=10_000`, 100 task chậm thường chủ yếu nằm chờ sau hai worker; `max=20` không khiến 20 worker xuất hiện ngay.

### Tại sao pool dùng lại thread?

Một platform thread cần tài nguyên và quá trình tạo/lập lịch. Nếu mỗi task ngắn tự tạo thread, tải cao dễ tạo hàng nghìn thread. Pool giữ các worker để dùng lại, vừa giảm overhead vừa đặt giới hạn tài nguyên. Nhưng worker cũng có chi phí: quá nhiều thread làm tăng context switching và cạnh tranh CPU/heap/stack. Pool nhanh hay không còn phụ thuộc phần việc và hệ thống bên dưới, không chỉ số lượng thread.

## 3. Ý nghĩa các cấu hình

| Thuộc tính | Cơ chế | Lưu ý |
| --- | --- | --- |
| `corePoolSize` | Số worker nền tảng khi có tải | Không phải “số task chạy tối đa” |
| `maxPoolSize` | Trần số worker | Chỉ quan trọng khi queue đã đầy hoặc policy queue đặc biệt |
| `queueCapacity` | Số task chờ được giữ trong bộ nhớ | Nên đặt hữu hạn theo burst và độ trễ cho phép |
| `keepAliveSeconds` | Thời gian worker vượt core nhàn rỗi trước khi bị thu hồi | Mặc định 60 giây |
| `allowCoreThreadTimeOut` | Cho phép cả core worker rời pool khi nhàn rỗi | Mặc định `false` |
| `prestartAllCoreThreads` | Tạo sẵn core threads lúc init | Mặc định `false`, thường tạo khi có task |
| `threadNamePrefix` | Đặt tiền tố tên worker | Giúp log và thread dump dễ hiểu |
| `rejectedExecutionHandler` | Hành vi khi không nhận được task nữa | Không được bỏ qua mất task |
| `taskDecorator` | Bọc task trước khi worker chạy | Dùng truyền context/đo thời gian và cleanup |
| Shutdown flags | Cách đóng pool lúc context dừng | Có thể đợi hoặc gián đoạn task tùy cấu hình và phiên bản |

**Mặc định của bản thân `new ThreadPoolTaskExecutor()` trong Spring Framework 6.x**: `corePoolSize=1`, `maxPoolSize=Integer.MAX_VALUE`, `queueCapacity=Integer.MAX_VALUE`, `keepAliveSeconds=60` và `allowCoreThreadTimeOut=false`. Hàng đợi rất lớn có nghĩa pool thường chỉ chạy một worker ở tải thông thường; **max rất lớn không tự làm số worker tăng**.

**Phân biệt với Spring Boot auto-configuration:** Spring Boot có thể tạo `applicationTaskExecutor` theo mặc định riêng; ví dụ tài liệu Boot 3.5 mô tả một executor tự cấu hình có 8 core threads và các thuộc tính `spring.task.execution.*`. Không thể lấy default của class mới tạo bằng `new` để đoán default của bean Boot đang thực sự dùng. Khi cần ranh giới tải rõ ràng, cấu hình một bean có tên và chọn đích danh.

### 3.1. `queueCapacity > 0`: hàng chờ có sức chứa

`ThreadPoolTaskExecutor` dùng `LinkedBlockingQueue` khi queue capacity là số dương. Pool thử đưa task vào queue khi đủ core, chỉ mở rộng khi queue đầy. Hàng đợi có sức chứa quá lớn làm task tồn tại lâu trước khi chạy, vẫn chiếm bộ nhớ và có nguy cơ hết RAM.

Ví dụ `core=2, max=16, queue=1_000_000` không hợp lý chỉ vì “để không bao giờ reject”: nếu tốc độ nạp luôn lớn hơn tốc độ xử lý, backlog cứ tăng. Tính toán queue phải xét **độ trễ chờ**, kích thước từng task và tải burst.

### 3.2. `queueCapacity = 0`: bàn giao trực tiếp

`queueCapacity=0` dùng `SynchronousQueue`: không có chỗ lưu task chờ. Task được worker nhận trực tiếp hoặc executor mở thêm worker nếu chưa đạt max; nếu mọi worker bận và đã tới max, task bị từ chối. Mẫu này giúp tăng worker nhanh khi có tải, nhưng nếu max đặt cực cao có thể tạo rất nhiều platform threads.

**`queueCapacity=0` không có nghĩa executor không có queue ở nghĩa điều phối**, và không có nghĩa “không từ chối”; nó là một cơ chế handoff không lưu backlog.

### 3.3. Timeout và thread pool cố định

- Nếu `core=max=4`, pool tối đa bốn worker; task dư chờ queue, rồi bị từ chối nếu queue đầy.
- Worker **vượt core** có thể hết hạn khi rảnh `keepAliveSeconds`. Core worker thường được giữ lại.
- `setAllowCoreThreadTimeOut(true)` cho phép core worker cũng hết hạn khi rảnh (nếu cấu hình timeouts hợp lệ); hữu ích cho tải có lúc không hoạt động.
- `setPrestartAllCoreThreads(true)` có thể giảm delay khởi tạo worker của các task đầu tiên, nhưng giữ tài nguyên ngay cả trước khi có tải.

Các thông số là **chính sách capacity**, không phải giới hạn thời gian của mỗi task. Muốn task timeout cần cơ chế riêng phù hợp, ví dụ client timeout, deadline hoặc hủy task có kiểm soát.

## 4. Java 17+ runnable: thấy rõ worker reuse và queue capacity

`ThreadPoolTaskExecutor` bọc pool JDK nên có thể kiểm chứng hành vi lõi mà không cần Spring dependencies. Ví dụ sau cố ý dùng `CountDownLatch` thay vì đoán thứ tự task qua `Thread.sleep`.

Lưu toàn bộ vào **PoolBehaviorDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PoolBehaviorDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService single = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "reused-worker"));
        try {
            String a = single.submit(
                    () -> Thread.currentThread().getName()).get();
            String b = single.submit(
                    () -> Thread.currentThread().getName()).get();
            System.out.println("same worker: " + a.equals(b));
        } finally {
            single.shutdown();
        }

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 4, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(2));

        CountDownLatch started = new CountDownLatch(4);
        CountDownLatch release = new CountDownLatch(1);
        List<Future<?>> jobs = new ArrayList<>();

        try {
            Runnable heldTask = () -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
            };

            for (int i = 0; i < 6; i++) {
                jobs.add(pool.submit(heldTask));
            }

            started.await(); // 4 worker đang chạy và đợi release
            System.out.println("pool=" + pool.getPoolSize()
                    + ", active=" + pool.getActiveCount()
                    + ", queued=" + pool.getQueue().size());

            release.countDown();
            for (Future<?> job : jobs) {
                job.get();
            }
            System.out.println("completed=" + jobs.size());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac PoolBehaviorDemo.java
java PoolBehaviorDemo
```

**Stdout xác định khi chương trình chạy bình thường:**

```text
same worker: true
pool=4, active=4, queued=2
completed=6
```

**Giải thích tính xác định:**

1. `single` có một worker tên `reused-worker`. Task A hoàn tất qua `Future.get()` trước khi gửi task B; cả hai thực thi trên cùng thread, nên dòng đầu là `true`.
2. Pool thứ hai có core=2, max=4 và queue=2. Hai task đầu chạy, hai task kế chờ, hai task cuối kích hoạt worker #3/#4.
3. Tất cả task bắt đầu đều chờ trên `release`. `started.await()` chỉ xong sau khi bốn worker đã bắt đầu và chưa thể kết thúc, nên lúc đo có bốn worker active và hai task trong queue.
4. `release.countDown()` giải phóng các worker; hai task đang queue được nhận xử lý. `Future.get()` chờ đủ sáu kết quả rồi mới in `completed=6`.
5. `shutdownNow()` trong `finally` chỉ dùng để tránh để lại pool chạy nếu chương trình bị lỗi; luồng chạy bình thường đã hoàn tất công việc trước đó.

Đây là minh họa JDK cho **cơ chế underlying pool**, không phải ví dụ Spring container tự khởi tạo. Ví dụ Spring ở phần tiếp theo cho thấy cách khai báo bean và chọn executor bằng `@Async`.

## 5. Cấu hình ThreadPoolTaskExecutor làm Spring bean

Ví dụ dùng **Java 17+**, **Spring Boot 3.x / Spring Framework 6.x** và dependency `spring-boot-starter-web`. Đặt toàn bộ mã sau trong **src/main/java/com/example/demo/PoolApplication.java**. Đây là chương trình Spring Boot đầy đủ về cấu trúc lớp, cần build Spring dependencies; không chạy bằng `javac PoolApplication.java` trần.

```java
package com.example.demo;

import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class PoolApplication {
    public static void main(String[] args) {
        SpringApplication.run(PoolApplication.class, args);
    }

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("report-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}

@Service
class ReportService {
    @Async("reportExecutor")
    public CompletableFuture<String> generate(String id) {
        try {
            Thread.sleep(400); // Giả lập I/O blocking
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        }
        System.out.println("Working on " + id
                + " using " + Thread.currentThread().getName());
        return CompletableFuture.completedFuture("report:" + id);
    }
}

@RestController
class ReportController {
    private final ReportService reports;
    private final ThreadPoolTaskExecutor executor;

    ReportController(
            ReportService reports,
            @Qualifier("reportExecutor") ThreadPoolTaskExecutor executor) {
        this.reports = reports;
        this.executor = executor;
    }

    @GetMapping("/reports/{id}")
    public CompletableFuture<String> report(@PathVariable String id) {
        return reports.generate(id);
    }

    @GetMapping("/executor/stats")
    public Map<String, Integer> stats() {
        return Map.of(
                "poolSize", executor.getPoolSize(),
                "activeCount", executor.getActiveCount(),
                "queueSize", executor.getThreadPoolExecutor()
                        .getQueue().size(),
                "maxPoolSize", executor.getMaxPoolSize());
    }
}
```

Chạy bằng build Spring Boot của dự án:

```bash
./gradlew bootRun
curl -s http://localhost:8080/reports/R7
curl -s http://localhost:8080/executor/stats
```

Trên Windows, dùng `gradlew.bat bootRun`. Sau khi Future xử lý xong, body của request `/reports/R7` là:

```text
report:R7
```

Endpoint `/executor/stats` trả JSON chứa `poolSize`, `activeCount`, `queueSize`, `maxPoolSize`. Các con số thay đổi theo tải và thời điểm đo; **không có bộ giá trị JSON cố định**. Log worker bắt đầu bằng `report-` nhưng thứ tự và hậu tố tên thread không cố định.

### 5.1. Cơ chế kết nối với `@Async`

1. `@Bean("reportExecutor")` tạo **một** executor do Spring quản lý. Spring gọi lifecycle initialization cho bean; không cần tạo executor mới trên từng request.
2. `@EnableAsync` kích hoạt hạ tầng xử lý `@Async`. Controller gọi service bean được container quản lý.
3. `@Async("reportExecutor")` yêu cầu executor mang tên `reportExecutor`, nên đường thực thi không mơ hồ nếu context có thêm executor khác.
4. Khi proxy xử lý lời gọi, task `generate` được gửi tới pool. Worker chạy `Thread.sleep` mô phỏng I/O, tạo kết quả rồi hoàn thành `CompletableFuture`.
5. Spring MVC có thể xử lý kiểu trả về `CompletableFuture` bất đồng bộ ở phía server, nhưng **HTTP client vẫn chờ nội dung response hoàn thành**. Để client gửi việc rồi nhận mã job ngay, cần API riêng (ví dụ HTTP 202, job ID và endpoint tra kết quả).
6. Việc `Thread.sleep` vẫn chiếm worker dù controller xử lý request bất đồng bộ. `@Async` không biến một I/O blocking thành non-blocking I/O.

**Lỗi proxy quan trọng:** trong chế độ proxy mặc định, `this.generate(...)` gọi từ chính `ReportService` sẽ không đi qua interceptor `@Async`. Gọi từ bean khác như controller ở ví dụ trên, hoặc bố trí dịch vụ chuyên xử lý async để lời gọi thực sự qua Spring proxy.

### 5.2. Dùng executor trực tiếp

Khi đã có bean, ngoài `@Async` bạn có thể inject `ThreadPoolTaskExecutor` và gọi `execute(Runnable)`:

```java
@Component
class DispatchService {
    private final ThreadPoolTaskExecutor executor;

    DispatchService(
            @Qualifier("reportExecutor") ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    void dispatch(Runnable task) {
        executor.execute(task);
    }
}
```

Đây là **fragment** dành cho cùng project Spring ở trên; cần import `org.springframework.stereotype.Component` và `org.springframework.beans.factory.annotation.Qualifier` nếu tách thành file riêng. `execute` không trả giá trị nghiệp vụ. Nếu cần giá trị/kết quả lỗi, dùng `submit(Callable<T>)` và xử lý `Future<T>` theo phiên bản Spring, hoặc `CompletableFuture.supplyAsync(..., executor)`. Việc gọi `get()`/`join()` ngay sau submit khiến caller chủ động chờ, làm mất lợi ích overlap.

## 6. Khi quá tải: rejection và backpressure

Với `core=2, max=4, queue=16`, nếu bốn worker đang bận và queue đủ 16 task chờ, task mới có thể bị **reject**. Đối với API `TaskExecutor`, Spring có `TaskRejectedException`, phản ánh tình trạng không nhận được task. Khi đi qua annotation/proxy, cần kiểm tra đường truyền lỗi của API cụ thể.

| JDK RejectedExecutionHandler | Hành vi | Rủi ro |
| --- | --- | --- |
| `AbortPolicy` | Ném lỗi khi submit bị từ chối | Caller phải xử lý trạng thái quá tải; thường minh bạch |
| `CallerRunsPolicy` | Caller chạy task nếu executor chưa shutdown | Tạo backpressure nhưng có thể **chặn HTTP request thread**; `@Async` có thể trở thành việc đồng bộ lúc quá tải |
| `DiscardPolicy` | Bỏ task mới mà không báo lỗi | Dễ mất công việc âm thầm |
| `DiscardOldestPolicy` | Bỏ task cũ trong queue rồi thử lại | Phá thứ tự/độ tin cậy, có thể làm mất việc |

Chọn policy theo tính chất nghiệp vụ. Không dùng discard âm thầm khi công việc có hợp đồng **phải thực hiện** như ghi sự kiện thanh toán hoặc cập nhật bắt buộc. Nếu công việc quan trọng cần bền vững, queue trong RAM không thay thế message broker/job store.

**Phân biệt rõ:**

- **Rejected:** task chưa được pool nhận.
- **Failed:** task đã chạy nhưng code ném exception.
- **Timed out:** caller hoặc dependency vượt deadline.
- **Cancelled/interrupted:** có yêu cầu hủy, nhưng hiệu lực còn tùy task có hợp tác với interrupt hay không.
- **Shutdown:** pool không nhận task mới hoặc xử lý task tồn đọng theo lifecycle.

Đếm riêng các trường hợp để vận hành. Không báo “task thành công” chỉ vì lời gọi `execute` không ném lỗi; nghĩa là executor đã **chấp nhận** task, không phải đã hoàn tất.

## 7. Chọn pool size, queue và phân vùng theo loại tải

### 7.1. Tải CPU-bound

Công việc mã hóa, xử lý ảnh, nén hoặc tính toán nặng CPU thường bị giới hạn bởi số core thực tế và CPU quota của container. Tăng platform threads vượt xa số core có thể chỉ tăng context switching và cạnh tranh tài nguyên. Có thể bắt đầu từ mức worker gần số CPU được cấp, rồi đo throughput/latency với workload thật.

### 7.2. Tải blocking I/O-bound

Công việc thường đợi HTTP/database/disk có thể sử dụng nhiều worker hơn số CPU để che thời gian đợi. Nhưng nếu DB connection pool chỉ có 12 connections mà có 100 worker cùng thực hiện JDBC, nhiều worker sẽ đợi kết nối và làm tăng memory/latency. Cần xem cả connection pool, timeouts, quota và sức chịu tải downstream.

### 7.3. Queue quyết định độ trễ chờ

Giả sử producer sinh 200 task/giây, service ổn định chỉ hoàn thành 100 task/giây; nếu tiếp tục tiếp nhận không giới hạn, backlog tăng xấp xỉ 100 task mỗi giây trong điều kiện đơn giản hóa. Sau 10 giây có thể có khoảng 1.000 task chờ. Queue lớn chỉ trì hoãn việc bộc lộ overload.

Nếu hệ thống xử lý trung bình 100 task/giây và chỉ chấp nhận queue wait khoảng 0,5 giây, **50 task có thể là một mốc thử nghiệm**, không phải công thức bảo đảm latency. Burst traffic, phân phối thời gian chạy và downstream contention có thể khiến kết quả khác. Cần load test để chọn cấu hình thực.

### 7.4. Tách pool khi cần bảo vệ SLA

Một pool riêng cho email API chậm và pool riêng cho xử lý báo cáo CPU-bound giúp tải chậm không chiếm hết worker của nghiệp vụ quan trọng:

```text
Service A → @Async("emailExecutor")  → email worker pool → external mail API
Service B → @Async("reportExecutor") → report worker pool → CPU / storage
```

Đây là cách áp dụng **bulkhead** để cô lập sự cố. Nhưng nhiều pool cũng tăng tổng thread và chi phí cấu hình, nên phải chọn theo tải thật, không mặc định mỗi method một pool.

## 8. Lifecycle: từ khởi tạo tới đóng ứng dụng

Trong ứng dụng Spring, nên tạo pool dưới dạng **bean** để container quản lý vòng đời:

- Đặt các tham số `core/max/queue` trước khi bean initialize. Với `@Bean` thông thường, Spring tự khởi tạo lifecycle; không cần gọi `initialize()` thủ công.
- Nếu tự `new ThreadPoolTaskExecutor()` ngoài container, code sử dụng phải gọi `initialize()` và bảo đảm `shutdown()` khi không dùng nữa.
- Đừng tạo bean executor riêng mỗi request; pool sinh ra để dùng chung giữa nhiều task.
- Đừng gọi `shutdown()` sau mỗi lần submit; những task sau sẽ bị từ chối.
- Khi context đóng, lựa chọn chờ/hủy task tùy flags và version Spring. `setWaitForTasksToCompleteOnShutdown(true)` yêu cầu executor tiếp tục xử lý task đang chạy và task đã ở queue trong luồng shutdown có kiểm soát.
- `setAwaitTerminationSeconds(10)` giới hạn thời gian container đợi termination ở pha shutdown; không phải bảo đảm mọi task xong trước 10 giây.
- Trong container/Kubernetes, kết hợp readiness, dừng nhận request, termination grace period và hành vi dependency shutdown. Nếu bị kill/crash đột ngột, task chỉ tồn tại trong RAM queue có thể mất.

Một phần việc quan trọng cần **ít nhất một lần thực thi** hoặc khôi phục sau restart phải có state bền vững, idempotency key và cơ chế retry/ack phù hợp. `ThreadPoolTaskExecutor` tự thân không phải durable job queue và không phối hợp across multiple application replicas.

## 9. Thread-local context, log và an toàn concurrency

Worker được **tái sử dụng** nên mỗi task mới có thể chạy trên cùng thread mà task cũ vừa sử dụng. Đây là lý do phải cẩn thận với `ThreadLocal`, MDC logging và security context.

Mặc định, data trong request thread **không tự được copy** sang worker. Tự sao chép transaction hoặc request-scoped state tùy tiện cũng nguy hiểm: Spring transaction thông thường gắn với thread, nên `@Async` không tự thừa kế transaction của caller.

### 9.1. TaskDecorator truyền MDC có cleanup

Khi dự án dùng SLF4J, có thể cấu hình `TaskDecorator` trên bean executor. Đây là **fragment cấu hình** bổ sung vào method `reportExecutor()` trước khi trả bean:

```java
executor.setTaskDecorator(task -> {
    var submitted = org.slf4j.MDC.getCopyOfContextMap();
    return () -> {
        var previous = org.slf4j.MDC.getCopyOfContextMap();
        try {
            if (submitted == null) {
                org.slf4j.MDC.clear();
            } else {
                org.slf4j.MDC.setContextMap(submitted);
            }
            task.run();
        } finally {
            if (previous == null) {
                org.slf4j.MDC.clear();
            } else {
                org.slf4j.MDC.setContextMap(previous);
            }
        }
    };
});
```

Decorator chụp MDC **khi submit**, áp vào thread worker **khi chạy**, rồi dọn và khôi phục trạng thái ban đầu trong `finally`. Nếu không cleanup, worker tái sử dụng có thể đưa correlation ID hoặc dữ liệu nhạy cảm của task trước sang task sau.

**Lưu ý ngoại lệ:** TaskDecorator bọc runnable thực thi thực tế, có thể là `FutureTask` chứ không phải runnable của user. Với task gửi bằng `submit`, exception thường được chứa trong Future; không giả định decorator chỉ cần `catch` quanh `task.run()` là nhìn thấy mọi lỗi. Quan sát `Future.get()`, `CompletableFuture.exceptionally/whenComplete` và metric lỗi riêng. Với security context, cân nhắc wrapper từ Spring Security và chỉ truyền đúng context cần thiết.

### 9.2. Pool thread-safe không làm bean tự thread-safe

Pool đảm bảo cấu trúc nội bộ của nó khi nhận/phân phối task; **nó không bảo vệ biến dùng chung trong service**. Ví dụ hai task cùng làm `count++` trên field thường của singleton có thể làm mất cập nhật; cùng ghi vào `HashMap` không đồng bộ cũng sai. Sử dụng immutable DTO, biến local, atomic types, `ConcurrentHashMap`, hoặc synchronized/lock theo invariant cần bảo vệ.

## 10. Quan sát pool bằng metric

| Chỉ số | Dùng để trả lời |
| --- | --- |
| `getPoolSize()` | Hiện có bao nhiêu worker? |
| `getActiveCount()` | Khoảng bao nhiêu worker đang bận? |
| `getThreadPoolExecutor().getQueue().size()` | Bao nhiêu task đang chờ ở thời điểm đo? |
| Queue wait time | Task mất bao lâu từ submit đến bắt đầu thực thi? |
| Task run time | Task mất bao lâu khi đang chiếm worker? |
| Rejection count | Pool từ chối bao nhiêu task? |
| Completion/failure/cancellation count | Kết quả nghiệp vụ ra sao? |
| Downstream latency/connection usage | Bottleneck có nằm ngoài executor không? |

Các getter `poolSize`, `activeCount` và `queue.size()` phản ánh các **ảnh chụp có thể thay đổi tức thì**; đừng coi ba phép đọc rời rạc là snapshot nguyên tử. Đưa metric qua Micrometer/Actuator khi dự án có hệ thống quan sát tương ứng. Theo dõi p95/p99 latency, queue wait, task rejection và memory, không chỉ CPU.

Nếu CPU thấp nhưng `activeCount` gần max và queue tăng liên tục, có thể nhiều worker đang **chờ I/O hoặc lock**, không phải thiếu lõi CPU. Nếu CPU cao và các task CPU-bound chậm dần khi tăng thread, có thể đang oversubscribe CPU.

## 11. So sánh với các executor khác

| Executor | Đặc trưng | Phù hợp khi |
| --- | --- | --- |
| `SyncTaskExecutor` | Chạy trên caller thread | Kiểm thử hoặc cần đồng bộ |
| `SimpleAsyncTaskExecutor` | Không tái sử dụng platform threads; có tùy chọn virtual threads ở phiên bản hỗ trợ | Muốn strategy tạo thread theo task, không cần pool platform-thread truyền thống |
| **`ThreadPoolTaskExecutor`** | Tái sử dụng worker, core/max/queue/rejection rõ ràng | Workload nền có giới hạn tài nguyên và cần isolation |
| `ThreadPoolTaskScheduler` | Kích hoạt theo lịch | Job `@Scheduled` hoặc trigger thời gian |
| JDK `ThreadPoolExecutor` | Pool thuần Java | Không dùng Spring hoặc cần kiểm soát mức JDK |
| Virtual-thread-per-task executor (Java 21+) | Thread ảo mới mỗi task, không phải pool platform threads tái sử dụng theo kiểu trên | Nhiều blocking I/O phù hợp virtual thread, vẫn phải giới hạn downstream |

**Virtual thread không làm CPU và DB connection vô hạn**. Dù dùng virtual threads, vẫn có thể cần semaphore, admission control và timeout. Khi bài toán là một nhóm **platform worker** phải tái sử dụng có core/max/queue rõ ràng, `ThreadPoolTaskExecutor` là lựa chọn trực tiếp.

## 12. Lỗi phổ biến

**Lỗi 1 — Chỉ tăng `maxPoolSize` rồi thắc mắc vì sao không tăng threads.** Với queue lớn, task chờ trước khi pool vượt core. Kiểm tra đồng thời core, max, queue.

**Lỗi 2 — Đặt queue quá lớn để “khỏi reject”.** Backlog và thời gian chờ có thể tăng không giới hạn thực tế, đến lúc hết bộ nhớ.

**Lỗi 3 — Đặt `queueCapacity=0` với max quá cao.** Burst tạo nhiều platform threads, gây áp lực lên tài nguyên. Chọn max phù hợp.

**Lỗi 4 — Dùng một pool chung cho I/O chậm và CPU task nhanh.** Slow tasks chiếm hết worker, làm nghẽn việc quan trọng. Tách theo tài nguyên/SLA khi cần.

**Lỗi 5 — Cho rằng `@Async` luôn chạy trên pool mong muốn.** Có thể framework chọn executor khác; chỉ rõ `@Async("beanName")` và kiểm tra proxy.

**Lỗi 6 — Tự gọi `this.asyncMethod()`.** Self-invocation ở chế độ proxy mặc định bỏ qua interceptor `@Async`.

**Lỗi 7 — `join()` ngay sau submit.** Caller tự chờ, làm mất lợi ích tiếp tục xử lý song song với task.

**Lỗi 8 — Không xử lý rejection.** Task chưa được nhận cần phản hồi retry hoặc chính sách overload; không xem nó như đã xử lý thành công.

**Lỗi 9 — Không quan sát exception từ `Future`.** Task có thể đã thất bại trong worker nhưng caller vẫn không nhận ra; cần thu thập lỗi qua Future/callback hoặc handler.

**Lỗi 10 — Đánh đồng `@Async` với non-blocking I/O.** JDBC/HTTP client blocking vẫn giữ worker trong suốt thời gian chờ.

**Lỗi 11 — Rò rỉ `ThreadLocal` giữa task.** Worker tái sử dụng có thể chứa dữ liệu của task trước; dọn context trong `finally`.

**Lỗi 12 — Không tính shutdown/restart.** Task nằm trong RAM queue không tự tồn tại sau crash. Phải có job store/broker cho yêu cầu bền vững.

## 13. Cách kiểm thử trước khi đưa vào production

Một kiểm thử pool có ý nghĩa nên dựa trên điều kiện phối hợp **có thể kiểm soát**:

1. Gửi task được giữ bởi `CountDownLatch` để đạt trạng thái worker bận và queue đầy.
2. Với core=2, max=4, queue=2, xác minh sau sáu task có 4 worker bận và 2 task chờ; task thứ bảy bị từ chối nếu chưa nhả latch.
3. Nhả latch và đợi mọi `Future` hoàn tất. Chú ý task chạy xong khác với task đã được submit.
4. Chủ động cho một task ném lỗi và xác minh error path từ Future/callback, tách với rejection.
5. Thử `CallerRunsPolicy` khi quá tải, đo xem caller bị chặn bao lâu.
6. Thử MDC nhiều correlation ID trên cùng worker; xác minh không rò rỉ giữa task.
7. Đóng Spring context khi có task pending, đánh giá graceful shutdown, timeout và tài nguyên phụ thuộc.
8. Load test với traffic thật, đo CPU, memory, queue wait, p95/p99 latency, active threads, rejections và downstream capacity.

Đừng dùng `Thread.sleep(100)` làm bằng chứng xác định task nào sẽ chạy trước; OS/JVM scheduler không bảo đảm thứ tự. Dùng latch/barrier để tạo điều kiện kiểm thử rõ ràng.

## 14. Tự kiểm tra

**Câu 1.** `core=2, max=10, queue=100` và 20 task chậm cùng đến. Vì sao pool có thể chỉ có hai worker?

**Đáp án:** Sau khi đủ core, task được đưa vào queue. Queue còn chỗ nên pool chưa cần tăng vượt core; max=10 chỉ là giới hạn trên.

**Câu 2.** `queueCapacity=0` có nghĩa không chấp nhận task?

**Đáp án:** Không. Nó dùng `SynchronousQueue`, đòi hỏi chuyển giao trực tiếp cho worker có thể nhận hoặc tạo thêm worker nếu chưa đạt max. Chỉ khi không thể nhận nữa mới reject.

**Câu 3.** Một request HTTP gọi `@Async("reportExecutor")` và trả `CompletableFuture<String>`. Client có lập tức nhận body không?

**Đáp án:** Không. Server có thể trả thread xử lý request để làm việc khác, nhưng response có kết quả chỉ hoàn tất khi Future có kết quả; muốn trả job ID ngay cần thiết kế API riêng.

**Câu 4.** `CallerRunsPolicy` có thể thay đổi điều gì ở caller?

**Đáp án:** Khi overload, caller có thể trực tiếp chạy task và bị chặn cho đến lúc task xong, tạo backpressure nhưng tăng latency hoặc làm mất tính bất đồng bộ từ góc nhìn caller.

**Câu 5.** Pool có tự bảo vệ một `HashMap` chung trong bean không?

**Đáp án:** Không. Thread pool chỉ điều phối task. Dữ liệu chia sẻ vẫn phải thread-safe.

**Câu 6.** Tại sao queue trong pool không bảo đảm task còn tồn tại sau crash?

**Đáp án:** Queue này nằm trong RAM của tiến trình, không phải persistent job store.

**Câu 7.** Tại sao log MDC cần cleanup sau khi task hoàn tất?

**Đáp án:** Thread có thể được dùng lại cho task khác; context chưa xóa có thể rò rỉ giữa hai task.

**Câu 8.** Khi nào cân nhắc executor khác thay vì `ThreadPoolTaskExecutor`?

**Đáp án:** Khi muốn chạy đồng bộ (`SyncTaskExecutor`), cần trigger thời gian (`TaskScheduler`), hoặc chọn mô hình virtual-thread-per-task cho I/O phù hợp; lựa chọn phải bám theo ràng buộc tài nguyên.

## 15. Checklist khi chọn executor cho dự án

- Phân loại task theo CPU-bound hay blocking I/O-bound, thời gian chạy, mức burst và quota downstream.
- Dùng bean executor có tên cho nhóm công việc cần isolation; không tạo pool trong mỗi request.
- Chọn **corePoolSize, maxPoolSize, queueCapacity cùng nhau** theo thuật toán core → queue → max → reject.
- Đặt queue hữu hạn và xử lý overload; đo queue wait thay vì chỉ tăng max.
- Gắn `@Async("executorName")` khi cần proxy async, hoặc inject executor để submit trực tiếp.
- Quan sát Future/exception, xử lý timeout, retry, idempotency và interruption.
- Bảo vệ shared state của bean; truyền context cần thiết và dọn `ThreadLocal` khi worker tái sử dụng.
- Thiết kế lifecycle shutdown và độ bền task; phân biệt in-memory queue với persistent job system.
- Kiểm thử tải thực tế và thay đổi cấu hình dựa trên metric, không theo phỏng đoán.

**Ghi nhớ:** `ThreadPoolTaskExecutor` nhận task, **giữ worker để tái sử dụng**, đưa task vào queue khi đã đủ core, tăng worker khi queue đầy, và từ chối khi không còn capacity. Cách cấu hình quyết định mức công việc chạy đồng thời, độ trễ chờ và phản ứng khi hệ thống quá tải.

## Tài liệu tham khảo

- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework 6.1 Javadoc — ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.1 Javadoc — ExecutorConfigurationSupport: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html
- Spring Boot 3.5 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Java SE 17 — ThreadPoolExecutor API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
