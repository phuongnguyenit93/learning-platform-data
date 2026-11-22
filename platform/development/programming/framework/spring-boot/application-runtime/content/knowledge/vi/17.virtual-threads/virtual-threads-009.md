# Kiểm tra khả năng dừng, giải phóng tài nguyên và giới hạn hệ thống bên ngoài khi dùng luồng ảo

**Chủ đề:** Spring Boot Application Runtime → **Luồng ảo**. Bài học này giải thích cách kiểm chứng một ứng dụng dùng **virtual threads** thực sự có thể dừng, ngắt công việc, giải phóng tài nguyên đang giữ và không vượt giới hạn của database/API/broker ở bên ngoài. Trọng tâm không phải “tạo được bao nhiêu luồng”, mà là **lifecycle, bounded admission, concurrency limit, timeout, interrupt, cleanup, kết quả job và khả năng khôi phục**.

**Phiên bản lab:** **Java 21+** (virtual threads là tính năng chính thức từ Java 21), **Spring Boot 3.5.x**, Spring Web, Maven. Spring Boot 3.5 khuyến nghị Java 24+ để có trải nghiệm virtual threads tốt hơn; ví dụ dưới đây vẫn biên dịch trên **JDK 21**. Không dùng Java 17 cho mã có `Executors.newVirtualThreadPerTaskExecutor()` hoặc `Thread.isVirtual()`. Với ứng dụng trên JDK 24+, chi tiết về pinning do `synchronized` khác JDK 21; luôn gắn nhận định hiệu năng với bản JDK đang chạy.

## 1. Mục tiêu học tập

Kết thúc bài, bạn cần làm được:

1. Giải thích virtual thread là **một thread Java nhẹ cho một tác vụ**, không phải thread pool có kích thước tự động an toàn cho mọi resource.
2. Phân biệt **số luồng ảo đang tồn tại**, **số job được chấp nhận**, **số request đang dùng resource ngoài** và **số connection thực tế của client pool**.
3. Bật virtual threads trong Spring Boot 3.5 bằng `spring.threads.virtual.enabled=true` và giải thích lý do cân nhắc `spring.main.keep-alive=true`.
4. Tạo `ExecutorService` dùng virtual thread per task và quản lý vòng đời của nó cùng Spring context.
5. Dùng **hai `Semaphore` có mục đích khác nhau**: trần job đang được nhận và trần concurrent external I/O.
6. Tái lập tình huống **5 job accepted, job thứ 6 bị từ chối**, trong khi concurrent external operations không vượt **2**.
7. Chứng minh `InterruptedException` được xử lý đúng: khôi phục interrupt flag, ghi trạng thái, và `release()` trong `finally`.
8. Phân biệt shutdown mềm `shutdown()`, shutdown cưỡng bức hợp tác `shutdownNow()`, timeout của `awaitTermination(...)` và SIGKILL.
9. Chỉ ra những tài nguyên phải đóng riêng (JDBC/HTTP clients, responses, streams, broker consumers), không nhầm kết thúc virtual thread với đóng mọi connection.
10. Thiết kế deadline, retry, idempotency và durable job queue nếu nghiệp vụ không được phép mất việc khi restart.
11. Thu thập bằng chứng runtime qua job status, số permits, log shutdown và thread dump/JFR.
12. Phân biệt việc application **đã nhận** job với **job đã hoàn thành**, và readiness với khả năng chấp nhận việc mới.

**Nguyên tắc cốt lõi:** Virtual threads giúp mở rộng số tác vụ blocking mà không giữ mỗi tác vụ một platform thread. Chúng **không** tự tăng sức chứa của database connection pool, API quota, memory hoặc CPU. Vì vậy phải giới hạn **công việc/tài nguyên**, và phải kiểm chứng **cleanup ở mọi đường thoát**.

## 2. Vì sao virtual threads vẫn cần giới hạn?

### 2.1. Một luồng ảo cho mỗi tác vụ

Java 21 cung cấp:

~~~java
ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor();
~~~

Mỗi task được submit tạo một virtual thread mới. Executor này **không giới hạn** số virtual threads theo cách fixed thread pool. Đây là API JDK, có thể dùng trong Spring Boot, nhưng **Spring không tự sở hữu lifecycle của một field ExecutorService do bạn tạo**; code quản lý nó phải dừng/đóng khi context shutdown.

Java docs khuyến nghị **không pool virtual threads** như một tài nguyên khan hiếm. Dùng `Semaphore` để giới hạn đồng thời truy cập một resource, hoặc dùng admission control để giới hạn tổng số công việc còn chờ. `Semaphore` không biến virtual threads thành platform thread pool: virtual threads chờ permit có thể bị suspend/unmount khỏi carrier thread khi blocking.

### 2.2. Những giới hạn độc lập nhau

Giả sử một ứng dụng có thể tạo hàng chục nghìn virtual threads nhưng API đối tác chỉ cho **2 calls concurrent**:

| Tài nguyên | Ví dụ trần | Hậu quả nếu bỏ qua |
|---|---:|---|
| Virtual threads | Có thể rất nhiều, tùy heap/runtime | Nhiều object/thread-local/job state và overhead |
| Job đã nhận trong process | 5 | Backlog RAM tăng vô hạn nếu không giới hạn |
| External API inflight | 2 | Bị rate limit/throttle, overload upstream |
| JDBC connections | Ví dụ 10 mỗi instance | Chờ connection lâu, timeout và contention |
| CPU cores | Tùy máy | Virtual threads không làm CPU work chạy nhanh hơn |
| Memory mỗi job | Tùy payload | OOM dù các thread “nhẹ” |
| Deadline/job | Ví dụ 30 giây để lấy permit | Task treo lâu, khó graceful shutdown |
| Replica count | Ví dụ 4 | Trần per-instance nhân lên trên cụm |

**Hai phép đo không được đánh đồng:** `Thread.currentThread().isVirtual() == true` chỉ xác nhận job đang chạy trên virtual thread; nó không chứng minh external I/O có bounded concurrency. Ngược lại, một `Semaphore(2)` hạn chế concurrent calls trong **một JVM/process**; nếu có 4 replica, tổng khả năng có thể lên đến 8 calls nếu tất cả đều tải, không phải quota toàn hệ thống.

### 2.3. Trần người dùng, trần downstream và trần backlog

Một thiết kế có thể phân lớp:

~~~text
HTTP client
    |
    | POST /lab/jobs
    v
Admission gate (Semaphore: 5)
    |    -> Hết chỗ: HTTP 429, không tạo virtual thread mới
    v
Executor: newVirtualThreadPerTaskExecutor()
    |
    +-- Virtual Thread A --    +-- Virtual Thread B ---+--> External slots (Semaphore: 2)
    +-- Virtual Thread C --/         |
    +-- Virtual Thread D ---- wait   +--> Mock external operation
    +-- Virtual Thread E ---- wait
                                   |
                             finally: release permit
                 |
                 +--> Job state: DONE / FAILED / INTERRUPTED
    |
    +--> finally: release admission permit
~~~

Giới hạn **5** là số job chưa hoàn tất đang giữ admission permit; giới hạn **2** là số job cùng ở trong phần giả lập external operation. Ba job còn lại có thể chờ permit ngoài. Bài lab dùng semaphore không chờ tại HTTP boundary (`tryAcquire()`) và semaphore chờ có timeout ở worker (`tryAcquire(timeout)`).

Đây là hai chính sách khác nhau: **không để request HTTP chờ vô hạn chỉ để nộp job**, và **không cho phép hơn hai job cùng sử dụng dịch vụ ngoài**.

## 3. Spring Boot 3.5 hỗ trợ virtual threads như thế nào?

### 3.1. Bật bằng cấu hình

Trong application properties:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

`spring.threads.virtual.enabled=true` yêu cầu Java **21+**. Khi Boot auto-configures `AsyncTaskExecutor` mà không có custom `Executor` chi phối, nó có thể dùng `SimpleAsyncTaskExecutor` chạy virtual threads. Khi Boot tự cấu hình scheduler, virtual threads có thể được dùng qua `SimpleAsyncTaskScheduler`.

**Không hiểu sai:** các property pool như `spring.task.execution.pool.max-size`, `queue-capacity`, hoặc `spring.task.scheduling.pool.size` **không tự đặt trần virtual threads trong chế độ virtual-thread tương ứng**. Spring Boot documentation nói các thuộc tính pool không còn tác dụng với executor/scheduler dùng virtual threads. Trần external requests phải được đặt tại lớp admission/semaphore/connection pool có ý nghĩa.

`spring.main.keep-alive=true` hữu ích vì **virtual threads là daemon threads**. Nếu ứng dụng chỉ còn các daemon threads (chẳng hạn workload chủ yếu `@Scheduled`) thì JVM có thể thoát ngay cả khi còn công việc; keep-alive giúp tránh tình huống process tự kết thúc ngoài ý muốn. Đây không phải một chiến lược shutdown hoặc lưu job bền vững: khi dừng context hợp lệ hoặc bị SIGKILL, vẫn cần xử lý resource và dữ liệu.

### 3.2. Executor do code tạo và executor do Boot auto-configure

Hai cách phổ biến:

| Cách | Ví dụ | Ai sở hữu lifecycle? | Giới hạn cần thêm |
|---|---|---|---|
| Boot-managed task executor | `@Async` dùng executor do Boot auto-configure | Spring/Boot tùy loại executor | Admission/timeout/connection quota |
| Custom Java executor ở một `@Service` | `Executors.newVirtualThreadPerTaskExecutor()` | Chính bean sở hữu field phải đóng | Admission và external permits |
| Custom Spring `SimpleAsyncTaskExecutor` | `setVirtualThreads(true)` | Tùy cách đăng ký/đóng; không phải pool tái sử dụng | `setConcurrencyLimit` hoặc gate khác theo semantics |
| JDBC connection pool | HikariCP hoặc tương đương | DataSource/pool bean | `maximumPoolSize`, connection timeout |
| Broker listener container | Spring integration tương ứng | Listener container/lifecycle | Consumer concurrency, inflight, ack, retries |

`SimpleAsyncTaskExecutor` **không tái sử dụng threads**. Một số phiên bản Spring Framework 6.2 hỗ trợ `setConcurrencyLimit(...)` và tùy chọn reject ở trần; việc giới hạn có thể **block submitter** theo default. Hãy kiểm tra đúng Javadoc phiên bản đang dùng; không coi `setConcurrencyLimit` tương đương bounded job queue có durable storage.

Trong lab, ta **cố tình sở hữu một `ExecutorService` field** để thấy rõ shutdown. Nó độc lập với executor `@Async` do Spring Boot có thể tạo.

## 4. Interrupt, cancellation và đóng tài nguyên: ba việc khác nhau

### 4.1. Thread bị interrupt chưa chắc operation đã dừng

`shutdownNow()` thực hiện một **nỗ lực best-effort** để dừng đang chạy, thường bằng `Thread.interrupt()`. Một task bị block ở `Thread.sleep(...)`, `CountDownLatch.await(...)` hoặc `Semaphore.tryAcquire(timeout)` có thể phản ứng bằng `InterruptedException`. Nhưng nếu external client không tôn trọng interrupt, thao tác native I/O hoặc một API bị kẹt có thể chưa dừng ngay.

Thao tác đúng:

~~~java
try {
    performInterruptibleWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    recordCancelledOrInterrupted();
} finally {
    releaseOwnedResources();
}
~~~

Đây là **snippet minh họa**, không phải file Java độc lập. Luôn phân biệt:

- **interrupt request**: tín hiệu yêu cầu hợp tác dừng;
- **job actually stopped**: task đã thoát khỏi critical section và trả permit;
- **executor terminated**: không còn task còn chạy;
- **external operation rolled back**: cần contract riêng của DB/API, không tự suy ra từ interrupt.

### 4.2. Không giải phóng nhầm permit

Cơ chế acquire/release an toàn:

~~~java
boolean acquired = false;
try {
    acquired = semaphore.tryAcquire(20, TimeUnit.SECONDS);
    if (!acquired) {
        throw new TimeoutException("external permit timeout");
    }
    performExternalCallWithTimeout();
} finally {
    if (acquired) {
        semaphore.release();
    }
}
~~~

Nếu `tryAcquire(...)` không thành công nhưng code vẫn `release()`, số permits sẽ tăng sai so với giới hạn ban đầu. Nếu không `release` khi exception, permit bị rò và các job về sau có thể chờ mãi. Trong lab hoàn chỉnh ta đặt ngoại lệ và xử lý interrupt rõ hơn; đoạn trên chỉ minh họa ownership.

### 4.3. Đóng connection khác đóng virtual thread

- JDBC: lấy `Connection` từ pool và dùng `try-with-resources` để **trả connection về pool**; physical connection có thể được giữ tái sử dụng.
- HTTP client: đặt connect/request/read timeout tương ứng; đóng `InputStream`/`Response` nếu API yêu cầu; pooled HTTP client được đóng ở lifecycle của bean.
- File/Socket: đóng `Closeable` trong `try-with-resources`, không giữ file descriptor qua các luồng công việc không kiểm soát.
- Message broker: ngừng nhận message mới, hoàn tất ack/nack theo policy, đóng session/consumer.
- Semaphore: trả permit trong `finally`, không dùng GC để khôi phục permit bị rò.
- Virtual thread: kết thúc `run()` không tự roll back một external side effect đã được gửi đi.

Đừng “sửa” resource leak bằng cách tạo thêm virtual threads. Nhiều task hơn chỉ làm lỗi resource pool/FD trở nên khó thấy trong thời gian ngắn hơn.

## 5. Project thực hành hoàn chỉnh: giới hạn ngoài và shutdown hợp tác

### 5.1. Khởi tạo Maven project

Tạo project bằng Spring Initializr:

- **Java 21** (có thể dùng 24+ nếu môi trường hỗ trợ), **Spring Boot 3.5.x**.
- Build: **Maven**, Packaging: **Jar**.
- Group `com.example`; Artifact `virtual-shutdown-lab`.
- Package `com.example.virtualshutdown`.
- Dependency: **Spring Web**.
- Giữ `pom.xml` và Maven Wrapper được sinh ra, không tự pha trộn dependency versions.

Cấu trúc:

~~~text
virtual-shutdown-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/virtualshutdown/
    VirtualShutdownLabApplication.java
    VirtualJobService.java
    VirtualJobController.java
  src/main/resources/application.properties
~~~

Ba file Java bên dưới **là mã hoàn chỉnh trong project Maven nêu trên**. Chúng cần Spring Web và Jakarta annotation đã có trong runtime dependencies; không chạy bằng `javac` với classpath chỉ chứa JDK.

### 5.2. Main class

File `src/main/java/com/example/virtualshutdown/VirtualShutdownLabApplication.java`:

~~~java
package com.example.virtualshutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VirtualShutdownLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(VirtualShutdownLabApplication.class, args);
    }
}
~~~

Main không tự mở `new Thread()` hoặc giữ ExecutorService như một local variable không được đóng. Worker lifecycle thuộc Spring-managed `VirtualJobService` ở bước tiếp theo.

### 5.3. VirtualJobService: hai giới hạn + xử lý lỗi + shutdown

File `src/main/java/com/example/virtualshutdown/VirtualJobService.java`:

~~~java
package com.example.virtualshutdown;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

@Service
public class VirtualJobService {

    // Moi task co mot virtual thread; executor KHONG co gioi han size.
    private final ExecutorService executor =
            Executors.newVirtualThreadPerTaskExecutor();

    // Toi da 5 jobs dang accepted/chua ket thuc trong JVM.
    private final Semaphore admitted = new Semaphore(5, true);

    // Chi 2 jobs duoc vao phan gia lap external I/O.
    private final Semaphore externalSlots = new Semaphore(2, true);

    private final CountDownLatch demoRelease = new CountDownLatch(1);
    private final ConcurrentMap<String, JobView> jobs =
            new ConcurrentHashMap<>();

    private final AtomicBoolean stopping = new AtomicBoolean();
    private final AtomicInteger accepted = new AtomicInteger();
    private final AtomicInteger rejected = new AtomicInteger();
    private final AtomicInteger done = new AtomicInteger();
    private final AtomicInteger failed = new AtomicInteger();
    private final AtomicInteger interrupted = new AtomicInteger();
    private final AtomicInteger externalActive = new AtomicInteger();
    private final AtomicInteger externalPeak = new AtomicInteger();

    public Submission submit(String kind) {
        if (stopping.get()) {
            return new Submission(null, "SHUTTING_DOWN");
        }

        // Fast-fail o HTTP boundary: KHONG tao thread vo han.
        if (!admitted.tryAcquire()) {
            rejected.incrementAndGet();
            return new Submission(null, "REJECTED");
        }

        // Kiem tra lai de giam race voi shutdown.
        if (stopping.get()) {
            admitted.release();
            return new Submission(null, "SHUTTING_DOWN");
        }

        String id = UUID.randomUUID().toString();
        jobs.put(id, new JobView(id, kind, "ACCEPTED",
                null, "accepted in memory"));

        try {
            executor.execute(() -> runJob(id, kind));
            accepted.incrementAndGet();
            System.out.println("LAB_SUBMITTED id=" + id);
            return new Submission(id, "ACCEPTED");
        } catch (RejectedExecutionException ex) {
            admitted.release();
            jobs.put(id, new JobView(id, kind, "REJECTED",
                    null, "executor is shutting down"));
            return new Submission(id, "SHUTTING_DOWN");
        }
    }

    private void runJob(String id, String kind) {
        boolean slotHeld = false;
        String thread = Thread.currentThread().toString();

        try {
            jobs.put(id, new JobView(id, kind, "WAITING_SLOT",
                    Thread.currentThread().isVirtual(),
                    "waiting for external permit"));

            // Cho permit co deadline; viec cho virtual thread la hop le.
            if (!externalSlots.tryAcquire(30, TimeUnit.SECONDS)) {
                throw new TimeoutException(
                        "LAB_EXTERNAL_PERMIT_TIMEOUT");
            }

            slotHeld = true;
            int activeNow = externalActive.incrementAndGet();
            externalPeak.accumulateAndGet(activeNow, Math::max);

            jobs.put(id, new JobView(id, kind, "RUNNING",
                    Thread.currentThread().isVirtual(), thread));
            System.out.println("LAB_EXTERNAL_BEGIN id=" + id
                    + " active=" + activeNow
                    + " virtual=" + Thread.currentThread().isVirtual());

            switch (kind) {
                case "block" -> {
                    if (!demoRelease.await(90, TimeUnit.SECONDS)) {
                        throw new TimeoutException(
                                "LAB_EXTERNAL_TIMEOUT");
                    }
                }
                case "fail" -> throw new IllegalStateException(
                        "LAB_INTENTIONAL_FAILURE");
                default -> Thread.sleep(250);
            }

            done.incrementAndGet();
            jobs.put(id, new JobView(id, kind, "DONE",
                    true, "completed"));
            System.out.println("LAB_DONE id=" + id);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            interrupted.incrementAndGet();
            jobs.put(id, new JobView(id, kind, "INTERRUPTED",
                    Thread.currentThread().isVirtual(),
                    "interrupted during shutdown or cancellation"));
            System.out.println("LAB_INTERRUPTED id=" + id);
        } catch (Exception ex) {
            failed.incrementAndGet();
            jobs.put(id, new JobView(id, kind, "FAILED",
                    Thread.currentThread().isVirtual(),
                    ex.getMessage()));
            System.out.println("LAB_FAILED id=" + id
                    + " cause=" + ex.getMessage());
        } finally {
            if (slotHeld) {
                int now = externalActive.decrementAndGet();
                externalSlots.release();
                System.out.println("LAB_EXTERNAL_RELEASE id=" + id
                        + " active=" + now);
            }
            admitted.release();
            System.out.println("LAB_ADMISSION_RELEASE id=" + id);
        }
    }

    public void releaseBlockedTasks() {
        demoRelease.countDown();
    }

    public JobView job(String id) {
        return jobs.get(id);
    }

    public Stats stats() {
        return new Stats(
                accepted.get(),
                rejected.get(),
                done.get(),
                failed.get(),
                interrupted.get(),
                5 - admitted.availablePermits(),
                admitted.availablePermits(),
                externalActive.get(),
                externalPeak.get(),
                externalSlots.availablePermits(),
                stopping.get());
    }

    @PreDestroy
    public void shutdown() {
        stopping.set(true);
        System.out.println("LAB_SHUTDOWN_BEGIN inFlight="
                + (5 - admitted.availablePermits()));

        // Buoc 1: dung nhan tasks moi, cho tasks dang chay.
        executor.shutdown();

        try {
            if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
                // Buoc 2: neu chua ket thuc, yeu cau interrupt.
                System.out.println("LAB_SHUTDOWN_INTERRUPT");
                executor.shutdownNow();

                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.out.println(
                            "LAB_SHUTDOWN_TIMEOUT cleanup incomplete");
                }
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
            System.out.println("LAB_SHUTDOWN_WAIT_INTERRUPTED");
        }

        System.out.println("LAB_SHUTDOWN_END terminated="
                + executor.isTerminated()
                + " externalActive=" + externalActive.get()
                + " admittedInFlight="
                + (5 - admitted.availablePermits()));
    }

    public record Submission(String id, String state) {
    }

    public record JobView(
            String id, String kind, String state,
            Boolean virtualThread, String detail) {
    }

    public record Stats(
            int accepted, int rejected, int done, int failed,
            int interrupted, int admittedInFlight,
            int admissionAvailable, int externalActive,
            int externalPeak, int externalAvailable,
            boolean stopping) {
    }
}
~~~

**Phân tích tính đúng đắn của code:**

1. `newVirtualThreadPerTaskExecutor()` tạo **một virtual thread trên mỗi task**. Trần **5** được thực thi bởi `admitted.tryAcquire()` trước khi gọi `execute`, không phải do executor giới hạn threads.
2. `Semaphore(5, true)` là **admission guard**: mỗi job chưa hoàn tất giữ một permit; job thứ sáu bị từ chối khi cả năm permits đang giữ. Nó chặn việc tạo quá nhiều virtual threads chỉ để chờ external resource.
3. `Semaphore(2, true)` là **downstream concurrency guard**: chỉ hai job cùng vào phần critical section. Các job khác chờ bằng `tryAcquire(30, TimeUnit.SECONDS)` trong virtual thread.
4. `Boolean virtualThread` trong `JobView` là `null` trước khi job chạy và trở thành `true` khi code đo `Thread.currentThread().isVirtual()`. Đây là phép đo trực tiếp, không suy từ property hay tên thread.
5. `RUNNING` chỉ được ghi **sau khi lấy được permit external**; `WAITING_SLOT` cho biết task đã có virtual thread nhưng chưa dùng resource. `DONE`, `FAILED` và `INTERRUPTED` là trạng thái cuối trong ví dụ.
6. `slotHeld` bảo đảm chỉ release external permit khi đã acquire thành công. `finally` giải phóng **cả external và admission permits** khi job kết thúc, dù thành công, lỗi, interrupt hay timeout.
7. `Thread.currentThread().interrupt()` bảo toàn interrupt status khi bắt `InterruptedException`. Code không cố chạy tiếp external call sau khi nhận interrupt.
8. `@PreDestroy` được Spring gọi khi bean bị hủy trong quá trình context close bình thường. Nó ngừng nhận việc, gọi `shutdown()`, đợi tối đa 3 giây, rồi `shutdownNow()` và đợi thêm tối đa 5 giây. Đây là **deadline lab**, không phải bộ đảm bảo mọi external operation dừng trong 8 giây.
9. `executor.isTerminated()` được log sau quá trình chờ. **Chỉ khi isTerminated=true, externalActive=0, admittedInFlight=0** thì các task được quản lý đã rời critical section trong demo. Nếu vẫn khác, phải ghi nhận cleanup chưa đầy đủ.
10. `ConcurrentHashMap jobs` không có TTL/retention để đơn giản hóa bài. Với production, phải giới hạn bộ nhớ và dùng durable job store nếu job không được phép mất khi JVM chết.
11. `accepted` tăng sau `execute(...)`. Task rất nhanh có thể hoàn thành trước khi caller tăng counter, vì vậy metric snapshot giữa nhiều `AtomicInteger` **không phải một transaction**; so kết quả cuối khi hệ thống yên.
12. `demoRelease` là latch một lần. Sau khi mở, nó không tự reset; restart ứng dụng để chạy lại saturation test trong trạng thái mới.

**Giới hạn cố ý của demo:** không có network I/O thật và không có transaction. Vì vậy ta xác minh **semantics concurrency/cleanup**, nhưng không thể từ đó khẳng định JDBC connection, HTTP response stream hoặc broker consumer thật đã được đóng. Điều đó cần các phép thử chuyên biệt ở phần sau.

### 5.4. REST controller để nộp việc và đọc kết quả

File `src/main/java/com/example/virtualshutdown/VirtualJobController.java`:

~~~java
package com.example.virtualshutdown;

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
public class VirtualJobController {

    private static final Set<String> KINDS =
            Set.of("quick", "block", "fail");

    private final VirtualJobService jobs;

    public VirtualJobController(VirtualJobService jobs) {
        this.jobs = jobs;
    }

    @PostMapping("/lab/jobs")
    public ResponseEntity<?> submit(
            @RequestParam(defaultValue = "quick") String kind) {

        if (!KINDS.contains(kind)) {
            return ResponseEntity.badRequest().body(
                    Map.of("error", "kind must be quick, block or fail"));
        }

        VirtualJobService.Submission result = jobs.submit(kind);

        return switch (result.state()) {
            case "ACCEPTED" ->
                    ResponseEntity.status(HttpStatus.ACCEPTED)
                            .body(result);
            case "REJECTED" ->
                    ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                            .body(result);
            default ->
                    ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                            .body(result);
        };
    }

    @GetMapping("/lab/jobs/{id}")
    public ResponseEntity<?> status(@PathVariable String id) {
        VirtualJobService.JobView job = jobs.job(id);

        if (job == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(Map.of("error", "job id not found"));
        }
        return ResponseEntity.ok(job);
    }

    @GetMapping("/lab/stats")
    public VirtualJobService.Stats stats() {
        return jobs.stats();
    }

    @PostMapping("/lab/release")
    public Map<String, Boolean> release() {
        jobs.releaseBlockedTasks();
        return Map.of("released", true);
    }
}
~~~

**Giao kèo HTTP:**

- `POST /lab/jobs?kind=quick`: 202 nếu nhận vào RAM, kết quả job thành `DONE` sau một khoảng ngắn.
- `POST /lab/jobs?kind=block`: 202 nếu nhận, giữ external permit trong khi chờ latch; dùng kiểm tra limit.
- `POST /lab/jobs?kind=fail`: có thể **202 khi submit** nhưng sau đó `FAILED` khi virtual thread chạy; không nhầm 202 với business success.
- Nếu admission full: **429** với `state="REJECTED"`.
- Nếu đang shutdown: **503** với `state="SHUTTING_DOWN"` nếu HTTP connector còn nhận được request.
- `GET /lab/jobs/{id}` đọc trạng thái; response `404` khi ID không tồn tại.
- `GET /lab/stats` bộc lộ counters, active external, peak và permits.
- `POST /lab/release` giải phóng latch lab, không phải API business.

**An toàn:** Controller chỉ dùng localhost, không có authentication. **Không đưa các endpoint tạo việc block/fail hoặc release vào production**. Production cần auth, quota theo tenant, request validation, rate limit và body size limit. Bản lab lưu trạng thái trong RAM, không có guarantee khôi phục sau restart.

### 5.5. Cấu hình Spring Boot

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=virtual-shutdown-lab
server.address=127.0.0.1
server.port=8080

# Enable Spring Boot virtual-thread integrations on Java 21+
spring.threads.virtual.enabled=true
spring.main.keep-alive=true

# Make context stop behavior explicit for the lab
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Trong lab, **custom executor ở `VirtualJobService` đã tạo virtual threads bằng JDK API dù `spring.threads.virtual.enabled` không được bật**. Property này cũng cho phép quan sát cách Spring Boot cấu hình virtual threads ở các integration points được hỗ trợ; đừng nhầm nó là trần executor riêng của service.

`server.address=127.0.0.1` chỉ phù hợp test local. Khi chạy container/Kubernetes cần bind interface có thể được kubelet/ingress truy cập; không copy địa chỉ loopback vào Pod mà quên kiểm tra networking.

## 6. Chạy lab và xác nhận có virtual threads thật

### 6.1. Maven Wrapper và JDK

Trên Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

`java -version` cần thể hiện **JDK 21+**. Nếu terminal có `JAVA_HOME` hoặc PATH trỏ tới Java 17, ứng dụng sẽ không chạy đúng API này. Không biên dịch target Java 17 rồi hy vọng `newVirtualThreadPerTaskExecutor()` tồn tại ở runtime thấp hơn.

Giữ terminal Maven chạy app. Terminal khác:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=quick"
curl -i "http://127.0.0.1:8080/lab/stats"
~~~

Submit trả HTTP **202** và JSON chứa UUID cùng `state="ACCEPTED"`. ID do chương trình tạo là ngẫu nhiên, không có giá trị stdout cố định để hardcode.

Sau khi lấy ID từ response, với shell Linux/macOS:

~~~bash
read -r JOB_ID
# Dan ID vua nhan, nhan Enter
curl -i "http://127.0.0.1:8080/lab/jobs/$JOB_ID"
~~~

Trên PowerShell:

~~~powershell
$jobId = Read-Host "Paste job ID from 202 response"
curl.exe -i "http://127.0.0.1:8080/lab/jobs/$jobId"
~~~

Sau khi worker hoàn thành, job có `state="DONE"` và `virtualThread=true`, hoặc khi việc còn chạy có `WAITING_SLOT`/`RUNNING` cũng với `virtualThread=true`. Log tương tự:

~~~text
LAB_SUBMITTED id=<dynamic-id>
LAB_EXTERNAL_BEGIN id=<dynamic-id> active=1 virtual=true
LAB_DONE id=<dynamic-id>
LAB_EXTERNAL_RELEASE id=<dynamic-id> active=0
LAB_ADMISSION_RELEASE id=<dynamic-id>
~~~

Các ID chỉ là **biến số trong sơ đồ log**, không phải chuỗi chương trình luôn in. `LAB_EXTERNAL_BEGIN` có thể xuất hiện trước `LAB_SUBMITTED` vì request thread và virtual thread chạy song song. `virtual=true` là dấu mốc đáng kiểm hơn là thứ tự tuyệt đối các log.

**Không ghi “job success” chỉ từ HTTP 202.** `202 Accepted` chỉ cho biết admission và `execute()` đã chấp nhận task vào JVM; job có thể fail hoặc bị ngắt sau đó.

## 7. Thí nghiệm 1 — Chứng minh giới hạn external, không phải giới hạn virtual threads

Khởi động **một JVM mới** để latch chưa được release. Trong thời gian dưới **30 giây** (deadline chờ permit) và trước **90 giây** (deadline giữ external gate), gửi sáu request `block` thật nhanh.

Trên Linux/macOS:

~~~bash
for i in 1 2 3 4 5 6; do
  curl -s -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=block"
done
curl -s "http://127.0.0.1:8080/lab/stats"
~~~

Trên Windows PowerShell:

~~~powershell
1..6 | ForEach-Object {
    curl.exe -s -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=block"
}
curl.exe -s "http://127.0.0.1:8080/lab/stats"
~~~

**Kỳ vọng khi các job chưa timeout và chưa release:**

- **5 request đầu** → HTTP **202**, mỗi request có UUID riêng và `state=ACCEPTED`.
- **Request thứ sáu** → HTTP **429**, `state=REJECTED`; service không tạo virtual thread cho task này.
- `admittedInFlight=5`, `admissionAvailable=0`.
- `externalActive=2`, `externalAvailable=0`.
- `externalPeak=2`; không bao giờ vượt 2 trong lab chuẩn.
- Có **2 jobs** ở `RUNNING` đang giữ external permits.
- Có **3 jobs** ở `WAITING_SLOT` với virtual threads đang chờ permit.
- `accepted=5` và `rejected=1` (nếu đây là sáu submissions duy nhất).
- Chưa có job `DONE` cho batch block.

Bảng đối chứng:

| Chỉ số | Giá trị tối đa/kỳ vọng | Được giới hạn bởi |
|---|---:|---|
| Job accepted nhưng chưa kết thúc | 5 | `Semaphore admitted(5)` |
| Job đang sử dụng mock external resource | 2 | `Semaphore externalSlots(2)` |
| Virtual threads chờ external permit | 3 trong batch này | Admission còn lại, không phải virtual thread pool |
| Job thứ 6 được accept? | Không | Fast-fail tại admission |
| HTTP response khi bão hòa | 429 | Controller mapping của `REJECTED` |

Điều này chứng minh việc giới hạn **external concurrency** vẫn đúng dù virtual threads có thể được tạo nhiều. Semaphore của lab không nên được xem là quota toàn cluster; nếu chạy N replicas thì trần tổng có thể lên tới `2 × N` nếu không có coordination/rate limit phía downstream.

### 7.1. Giải phóng và xác nhận không rò permit

Khi mọi request block đang giữ/wait permit:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/lab/release"
curl -i "http://127.0.0.1:8080/lab/stats"
~~~

Poll stats vài lần cho đến khi toàn bộ năm accepted jobs hoàn tất. Trong điều kiện không có timeout/interrupt và không có submissions khác:

~~~json
{
  "accepted": 5,
  "rejected": 1,
  "done": 5,
  "failed": 0,
  "interrupted": 0,
  "admittedInFlight": 0,
  "admissionAvailable": 5,
  "externalActive": 0,
  "externalPeak": 2,
  "externalAvailable": 2,
  "stopping": false
}
~~~

Đây là **JSON kỳ vọng sau khi hệ thống yên**, không nhất thiết là kết quả của lần GET ngay sau POST release vì workers chạy bất đồng bộ. Thứ tự property trong JSON có thể khác. Các giá trị permit quay về **5** và **2** chứng minh trong mô hình này không rò semaphore; chúng **chưa chứng minh** một JDBC connection thật hoặc HTTP response stream thật được đóng.

Đừng thử lại saturation trong **cùng JVM sau release** rồi kỳ vọng các job block vẫn chờ, vì `CountDownLatch` không reset. Restart app để test lại với latch mới.

## 8. Thí nghiệm 2 — Lỗi task và cleanup trong finally

Khi không còn job block hoặc sau khi restart, gọi:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=fail"
curl -i "http://127.0.0.1:8080/lab/stats"
~~~

HTTP submit có thể trả **202** trước khi virtual thread ném lỗi. Trong log:

~~~text
LAB_EXTERNAL_BEGIN id=<dynamic-id> active=1 virtual=true
LAB_FAILED id=<dynamic-id> cause=LAB_INTENTIONAL_FAILURE
LAB_EXTERNAL_RELEASE id=<dynamic-id> active=0
LAB_ADMISSION_RELEASE id=<dynamic-id>
~~~

Khi job thành `FAILED`, `failed` tăng một, nhưng `admittedInFlight=0` và `externalAvailable=2` trở lại sau `finally`. Đây là bằng chứng rằng **exception nghiệp vụ** không làm leak permit.

Nếu `externalSlots.tryAcquire(...)` **hết 30 giây** trước khi lấy slot, task trở thành `FAILED` với `LAB_EXTERNAL_PERMIT_TIMEOUT`, và chỉ **admission** permit được release. Vì `slotHeld=false`, code **không** release external permit nó chưa có. Phân biệt timeout này với một API network timeout xảy ra **sau khi đã lấy permit**.

Nếu worker bị interrupt khi đang chờ external permit, nhánh `InterruptedException` sẽ thực hiện và admission permit được release; external permit không bị tăng sai.

## 9. Thí nghiệm 3 — Shutdown khi còn virtual threads đang chờ

### 9.1. Quy trình kiểm thử không làm hỏng dữ liệu

1. Restart ứng dụng cho latch chưa release.
2. Nộp **5 request** `kind=block`.
3. Xác nhận `admittedInFlight=5`, `externalActive=2`, `externalPeak=2`.
4. **Không gọi `/lab/release`**.
5. Dừng tiến trình bằng Ctrl+C từ terminal Maven hoặc SIGTERM hợp lệ khi chạy JAR (đừng dùng SIGKILL).
6. Quan sát log của `VirtualJobService.shutdown()`, worker interrupts và giải phóng permits.

Ví dụ log **tương đối**:

~~~text
LAB_SHUTDOWN_BEGIN inFlight=5
LAB_SHUTDOWN_INTERRUPT
LAB_INTERRUPTED id=<dynamic-id>
LAB_EXTERNAL_RELEASE id=<dynamic-id> active=...
LAB_ADMISSION_RELEASE id=<dynamic-id>
LAB_SHUTDOWN_END terminated=true externalActive=0 admittedInFlight=0
~~~

Vì có năm tasks, marker interrupt/release xuất hiện nhiều lần và thứ tự giữa các virtual threads **không cố định**. Các marker của web server graceful shutdown có thể xen vào trước `LAB_SHUTDOWN_BEGIN`. Đường đi mặc định của lab là: `shutdown()` yêu cầu dừng nhận tasks mới; vì 5 jobs đang block không tự hoàn tất trong 3 giây, code gọi `shutdownNow()` để yêu cầu interrupt; vì `CountDownLatch.await` và `Semaphore.tryAcquire` đáp ứng interrupt, các worker thoát và `finally` trả permits.

**Điều kiện PASS cho phép thử này:**

- Thấy `LAB_SHUTDOWN_BEGIN` và sau đó `LAB_SHUTDOWN_END`.
- `terminated=true` trong điều kiện worker hợp tác và không có external I/O kẹt.
- `externalActive=0`; `admittedInFlight=0` ở cuối trong lab chuẩn.
- Có các marker `LAB_INTERRUPTED` với IDs tương ứng.
- Mỗi job đã giữ external slot phải có marker `LAB_EXTERNAL_RELEASE`; mỗi job đã accepted phải có `LAB_ADMISSION_RELEASE` nếu task thực sự bắt đầu.
- Không có thông báo `LAB_SHUTDOWN_TIMEOUT cleanup incomplete` trong đường hợp tác chuẩn.

**Không được kết luận tuyệt đối:** Thứ tự từng marker hoặc đúng thời gian 3+5 giây không phải hợp đồng; scheduler, OS, framework và công việc cleanup có thể gây thay đổi. Nếu một task đang nằm trong danh sách returned bởi `shutdownNow()` mà chưa hề bắt đầu, nó có thể không chạy `finally`; JDK API không cam kết mọi task pending sẽ được bắt đầu chỉ để cleanup. Vì vậy production cần durable job state và xử lý dropped/unstarted tasks.

### 9.2. Shutdown của HTTP server và background jobs là hai pha

Spring Boot 3.5 hỗ trợ graceful shutdown cho embedded web servers. `server.shutdown=graceful` điều khiển web server không nhận request mới theo policy, cho in-flight requests hoàn tất trong thời gian cho phép. `spring.lifecycle.timeout-per-shutdown-phase` là budget theo lifecycle phase. `@PreDestroy` của service demo là một hook thuộc bean destruction, không phải cơ chế thay thế hoàn toàn cho `SmartLifecycle` và phase orchestration nếu có broker consumer.

Khi Ctrl+C/SIGTERM đến, **HTTP server có thể đóng hoặc không còn truy cập được trước khi job service hoàn tất cleanup**. Đừng dựa vào việc GET `/lab/stats` trong lúc shutdown; dùng log, metrics trước shutdown và external state. Trong sản phẩm thật, cần policy ngừng nhận job sớm (readiness/admission gate), sau đó drain/cancel và ghi trạng thái bền vững.

### 9.3. Khác biệt giữa shutdown, shutdownNow, close và SIGKILL

| Cơ chế | Tác dụng | Có bảo đảm tasks thoát ngay không? |
|---|---|---|
| `executor.shutdown()` | Không nhận task mới; cho task đã nộp tiếp tục | Không |
| `executor.awaitTermination(timeout)` | Chờ cho đến khi executor dừng hoặc quá hạn | Không tự cancel |
| `executor.shutdownNow()` | Yêu cầu dừng và trả danh sách task chưa bắt đầu; thường interrupt task đang chạy | Không, best effort |
| `ExecutorService.close()` trên Java 21 | Yêu cầu orderly shutdown và **đợi tới khi tất cả task kết thúc**; khi interrupted có hành vi riêng theo API | Có thể chờ lâu nếu task không dừng |
| `@PreDestroy` | Hook Spring bean destruction khi context close hợp lệ | Không chạy chắc chắn nếu process bị giết |
| JVM SIGTERM/Ctrl+C | Có thể kích hoạt shutdown hooks và context close | Phụ thuộc deadline, ứng dụng và OS |
| SIGKILL / `kill -9` | Kết thúc cưỡng bức process | Không có callback/cleanup Java đáng tin |

Do đó, nếu task có thể block vô thời hạn, gọi `executor.close()` trong `@PreDestroy` mà không có timeout có thể khiến shutdown treo. Lab dùng hai pha với `awaitTermination` và `shutdownNow`, nhưng không thể **cưỡng ép** một I/O native không hợp tác dừng trong khoảng thời gian hữu hạn.

## 10. Giải phóng tài nguyên bên ngoài: kiểm tra điều gì?

### 10.1. JDBC/DataSource

Trong Spring Boot, JDBC connection thường đến từ connection pool như HikariCP. Virtual threads không làm pool có nhiều connections hơn. Khi 1.000 virtual threads cùng xin connection từ pool 10, phần lớn phải chờ connection hoặc timeout; latency tăng và có thể làm toàn bộ hệ thống chậm.

Mẫu code đúng cho một thao tác JDBC thủ công:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT 1")) {
    try (ResultSet rows = statement.executeQuery()) {
        if (rows.next()) {
            return rows.getInt(1);
        }
    }
}
~~~

Đây là **method-body snippet**, cần `DataSource`/imports và một method có kiểu trả thích hợp; **không** đặt trực tiếp vào project Web-only chưa có JDBC dependency. Với Spring `JdbcTemplate` hoặc `@Transactional`, framework có thể quản lý acquisition/release theo contract; không tự đóng connection đang thuộc transaction do framework quản lý bên ngoài phạm vi của bạn.

Cần kiểm: Hikari active/idle/pending, connection acquisition timeout, transaction duration, leak detection có chọn lọc, và việc connection quay về pool khi exception/cancellation. Nếu JDBC pool đã là trần concurrent operations bạn mong muốn, thêm một semaphore đúng **cùng một trần** có thể dư thừa; Oracle cũng lưu ý connection pool tự đóng vai trò giới hạn. Dùng thêm permit khi cần **trần nghiệp vụ khác** (ví dụ đối tác chỉ chấp nhận 2 QPS/concurrent calls) hoặc muốn từ chối sớm trước khi hết connection.

### 10.2. HTTP client gọi upstream

Một call HTTP production cần:

- Kết nối và request/response deadline phù hợp.
- Giới hạn concurrent calls/tổng inflight và rate limit theo chính sách upstream.
- Đóng response body stream khi API yêu cầu.
- Đóng/stop reusable HTTP client ở lifecycle thích hợp, không tạo một client mới cho mỗi job nếu nó quản lý connection pool.
- Phân biệt timeout, cancellation, response 429/503, DNS/network failure và permanent error.
- Dùng idempotency key nếu operation có external side effect và có retry.

Snippet JDK 21 dùng `HttpClient` (client có thể được tái sử dụng):

~~~java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.invalid/resource"))
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

Đây chỉ là **đoạn mã minh họa**, `example.invalid` là host dành cho tài liệu, **không được gọi như service thực**, và cần định nghĩa `HttpClient client`, imports, error handling, URI hợp lệ, timeout. Dùng `client.send` từ virtual thread phù hợp cho blocking I/O; `send` có thể throw `InterruptedException`, cần xử lý cancellation. Không suy rằng response 200 hay interrupt chứng minh mọi tài nguyên downstream đã rollback.

### 10.3. Broker consumer

Với Kafka, RabbitMQ hoặc JMS, việc “dừng virtual thread” không tự ack/nack messages. Cần quản lý:

1. Tạm ngừng nhận message mới.
2. Đợi/ghi nhận in-flight processing trong deadline.
3. Ack hoặc thực hiện protocol redelivery hợp lệ.
4. Đóng consumer/session/connection theo hợp đồng thư viện.
5. Ghi trạng thái bền vững/idempotency khi task có external side effect.

Nếu listener container của framework đã có `SmartLifecycle` và shutdown phase, ưu tiên cấu hình lifecycle của nó, không tự viết hai nơi cùng sở hữu start/stop.

### 10.4. File descriptors, streams và ThreadLocal

Mỗi virtual thread là một Java Thread object nên code vẫn có thể dùng `ThreadLocal`. Nhưng virtual thread per-task **không được pool/reuse để amortize cache** như ít platform threads. Giữ payload lớn, credentials hoặc per-request objects trong ThreadLocal của hàng chục nghìn jobs có thể phình memory. Khi dùng MDC/SecurityContext/transaction context, phải xác định propagation và cleanup; việc đổi thread không bảo đảm context cũ được chuyển tự động.

Một thread kết thúc không đồng nghĩa mọi file descriptor hoặc pooled connection đã được giải phóng nếu references còn được giữ. Đối với các `AutoCloseable` thật sự do task sở hữu, dùng `try-with-resources`/`finally`. Với shared clients, đặt hook đóng ở owner bean, không để một job đóng client dùng chung của job khác.

## 11. CPU, memory và pinning của virtual threads

### 11.1. I/O-bound không giống CPU-bound

Virtual threads có lợi khi nhiều tác vụ thường xuyên chờ I/O. Chúng **không làm một phép tính CPU chạy nhanh hơn** hoặc tăng số CPU cores. Nếu công việc CPU-bound, tăng số virtual threads có thể chỉ tạo contention; dùng work limiter theo CPU cores/measurement hoặc kiến trúc phù hợp.

### 11.2. Pinned virtual threads: cần phân biệt phiên bản JDK

Với **JDK 21**, một virtual thread có thể **bị pin vào carrier** khi blocking trong `synchronized` hoặc native/foreign calls. Pinned virtual thread giữ platform carrier thread và làm giảm khả năng mở rộng nếu pinning kéo dài/lặp nhiều. JDK **24+** thay đổi đáng kể vấn đề synchronized pinning (theo JEP 491); không áp nguyên mô tả JDK 21 cho tất cả bản Java mới.

Không sửa tất cả `synchronized` vô điều kiện. Tìm những critical sections **giữ monitor trong lúc blocking I/O lâu**; cân nhắc đưa blocking I/O ra ngoài synchronized hoặc dùng `ReentrantLock` tại nơi cần. Với native/third-party drivers, kiểm chứng stack và library compatibility.

Công cụ chẩn đoán trên JDK 21:

~~~bash
jcmd PID Thread.dump_to_file -format=json virtual-threads.json
~~~

Thay `PID` bằng PID JVM đang chạy. Có thể bật Java Flight Recorder và tìm sự kiện `jdk.VirtualThreadPinned` khi thực tế có pinning. Đừng suy “không thấy event” đồng nghĩa luôn không pinning: sự kiện, threshold và cấu hình JFR ảnh hưởng quan sát. Java 24+ có thay đổi nên hướng dẫn pinning và events phải đối chiếu JDK hiện tại.

### 11.3. Memory pressure mới là giới hạn còn lại

Một virtual thread nhẹ hơn platform thread, nhưng không **miễn phí**. Mỗi task có stack/data structures, futures, payload, HTTP context, job result, TLS/trace context và có thể giữ reference đến resource ngoài. Nếu admission không bounded, 100.000 virtual threads cùng chờ một semaphore là một backlog lớn, có thể làm heap thiếu bộ nhớ hoặc response latency vô hạn.

Đó là lý do lab dùng **Semaphore(5)** trước khi tạo thread, thay vì chỉ dùng `Semaphore(2)` ở downstream. Trong production, chọn admission capacity theo SLO, estimated memory per task, queue delay, retry policy và khả năng phục hồi.

## 12. Graceful shutdown, readiness và thời hạn của container

Spring Boot 3.5 cung cấp graceful shutdown với embedded web servers được hỗ trợ; web server cố ngừng nhận request mới và xử lý in-flight requests theo budget. Nhưng có **hai trục riêng**:

- **HTTP request lifecycle:** ingress/readiness, client connections, request handlers, web connector.
- **Background jobs lifecycle:** admission, pending jobs, resource semaphores, external I/O, executor, job persistence.

Nếu chỉ bật `server.shutdown=graceful` mà service tự tạo `ExecutorService` không đóng, không có bảo đảm jobs nền được drain/cancel. Nếu chỉ gọi `executor.shutdownNow()` nhưng web server vẫn nhận job mới, có thể tạo các rejection/loss khó kiểm soát.

**Trình tự thiết kế đề nghị:**

1. Publish readiness `REFUSING_TRAFFIC` hoặc tắt admission cho **new jobs** trước/đồng thời với giai đoạn drain theo policy.
2. Dừng intake từ HTTP/broker/scheduler; tránh tạo task mới.
3. Cho in-flight jobs hoàn thành theo deadline; ghi lại trạng thái/durable outcome.
4. Cancel/interrupt các task còn lại nếu cần; yêu cầu chúng giải phóng permits/streams/connections trong `finally`.
5. Đóng reusable clients và consumer/container sau khi user jobs ngừng sử dụng.
6. Kiểm executor terminated, active external=0, permits trả về và các metrics lỗi/cancellation.
7. Đảm bảo tổng deadline của các phase phù hợp với `terminationGracePeriodSeconds`, autoscaling/restart và timeout cấp platform.

**Cẩn thận:** readiness chỉ là tín hiệu routing của hạ tầng; publish `REFUSING_TRAFFIC` **không tự chặn tất cả direct HTTP requests** nếu app không cài gate hoặc web server chưa bước vào shutdown. Cần một cơ chế admission ngay tại API để không nhận job mới khi đang dừng.

### 12.1. Không thể chứng minh graceful shutdown bằng SIGKILL

SIGKILL hoặc crash OS không bảo đảm `@PreDestroy`, `SmartLifecycle.stop(...)` hay `finally` của các task chạy. Vì thế nếu yêu cầu “HTTP trả 202 thì job chắc chắn không mất”, phải lưu job bền vững trước response, dùng queue/broker/DB với ack/recovery và idempotency. Bài lab 202 chỉ nghĩa “được nhận vào RAM của JVM”, **không** phải lời hứa durability.

### 12.2. Đừng nhầm timeout khác nhau

| Timeout | Phạm vi | Nếu hết hạn |
|---|---|---|
| Admission `tryAcquire()` không đợi | HTTP submit | Từ chối ngay |
| External permit `tryAcquire(30s)` | Chờ quyền sử dụng resource | Job `FAILED` nếu không lấy được |
| Demo external latch `await(90s)` | Giả lập I/O | Job `FAILED` nếu chưa release |
| HTTP client request timeout | Request đến upstream | Tùy thư viện, thường ném exception |
| `awaitTermination(3s+5s)` | Chờ executor dừng | Escalate/ghi timeout |
| Spring shutdown phase timeout | `LifecycleProcessor` của context | Sang xử lý tiếp theo/timeout theo framework |
| Kubernetes termination grace period | Toàn process/Pod | Có thể kết thúc cưỡng bức |
| Business operation deadline | Toàn tác vụ | Thường cần cancel và idempotency |

Một job có ba lời gọi HTTP mỗi lời 30 giây không tự bảo đảm tổng deadline 30 giây. Cần tính budget xuyên suốt, có cancellation propagation và timeout cho mỗi bước. Nếu số retries cũng không giới hạn, deadline có thể bị vượt dù mỗi call có timeout riêng.

## 13. Observability và bằng chứng đủ để khẳng định PASS

### 13.1. Các số cần theo dõi

| Metric | Ý nghĩa | Dấu hiệu nguy hiểm |
|---|---|---|
| `admittedInFlight` | Job accepted mà chưa hoàn tất/cleanup | Bám trần 5 liên tục |
| `admissionAvailable` | Chỗ trống để nhận job | 0 trong thời gian dài |
| `externalActive` | Job đang giữ external permit | Vượt 2 là lỗi invariant |
| `externalPeak` | Giá trị active cao nhất đã quan sát | **Không được vượt 2** |
| `externalAvailable` | Số permits external còn lại | Sau khi yên phải là 2 |
| `accepted/rejected` | Thành công/thất bại tại submission | Spike rejection cần throttle/upstream signal |
| `done/failed/interrupted` | Outcome của worker | Job fail nhưng HTTP submit 202 vẫn có thể đúng |
| Executor terminated | Không còn task đang chạy sau shutdown | false sau deadline cần điều tra |
| Resource pool metrics | JDBC/HTTP/broker active/pending | Leak, backlog, pool exhaustion |
| Process memory, GC | Bộ nhớ của jobs/threads/payload | Tăng dù CPU thấp |

Một snapshot `externalActive=0` không chứng minh job đã hoàn tất business side effect hoặc đã commit transaction. Một snapshot `externalAvailable=2` chỉ chứng minh **semaphore internal** đã được trả. Cần đo **physical resources** và business state nếu muốn khẳng định end-to-end.

### 13.2. Invariant tối thiểu

Trong một JVM lab ổn định, khi chưa shutdown:

~~~text
0 <= admittedInFlight <= 5
0 <= externalActive <= 2
0 <= externalPeak <= 2
admissionAvailable + admittedInFlight == 5
externalAvailable + externalActive == 2   (snapshot gan nhat, co race giua reads)
~~~

Do `Semaphore.availablePermits()` và `AtomicInteger.get()` được đọc ở những thời điểm khác nhau, một lần `GET /lab/stats` rất sát lúc release/acquire có thể thấy số lượng không cộng đúng ngay tức thời. Chỉ khẳng định invariant từ trạng thái quiescent hoặc dùng instrumentation có đồng bộ/atomic snapshot thật sự.

### 13.3. Các dấu hiệu trong log

- `LAB_EXTERNAL_BEGIN`: task đã lấy permit và đang dùng simulated external resource.
- `virtual=true`: code chạy trên virtual thread.
- `LAB_EXTERNAL_RELEASE`: task đi qua cleanup external critical section.
- `LAB_ADMISSION_RELEASE`: job trả permit admission.
- `LAB_FAILED`: exception trong task, không chỉ lỗi submit.
- `LAB_INTERRUPTED`: task phản ứng với interrupt.
- `LAB_SHUTDOWN_BEGIN` / `LAB_SHUTDOWN_END`: vòng đời của service owner.
- `terminated=true` và `externalActive=0`: bằng chứng kết thúc đúng của demo khi kết hợp với trạng thái job/counters.

Với production, thêm request ID, job ID, trace ID, deadline, attempt count và error category; tránh log secrets, full request payload hoặc business identifiers nhạy cảm.

## 14. Tình huống lỗi và cách phân tích

| Hiện tượng | Nguyên nhân khả dĩ | Bước kiểm tra đúng |
|---|---|---|
| Bật `spring.threads.virtual.enabled` nhưng job không chạy virtual | Code tự submit vào executor platform hoặc đường call khác | In `Thread.isVirtual()` tại task thật |
| Virtual threads tăng mà DB timeouts tăng | Connection pool/upstream vẫn có trần | Hikari active/pending, query duration, số calls |
| `externalPeak` vượt trần | Release sai, nhiều semaphore instances, code bỏ qua guard | Kiểm bean scope và acquire/release đúng cặp |
| Sau job fail, `externalAvailable` vẫn thiếu permit | Thiếu `finally` hoặc release path sai | Inject lỗi và đối chiếu release log |
| Permit tăng hơn trần | Release khi acquire thất bại | Dùng `slotHeld` boolean, chỉ release khi owner thật sự có slot |
| Shutdown treo | I/O không timeout/interrupt, close chờ vô hạn | Thread dump, deadlines, shutdownNow/awaitTermination |
| JVM thoát khi chỉ còn scheduler virtual threads | Daemon semantics | Xem `spring.main.keep-alive=true` |
| Bật pool max-size mà concurrency vẫn lớn | Virtual threads không dùng pool settings đó | Thêm admission/downstream gate |
| Job status RUNNING mãi sau crash | Registry chỉ RAM, không durable | Persistent job store/leases/heartbeat |
| Gọi `ExecutorService.close()` làm app shutdown chậm | close đợi tasks kết thúc | Bounded shutdown strategy, timeouts |
| Task interrupt nhưng external request vẫn đang chạy | Client không hỗ trợ cancellation nhanh | Request timeout, explicit close/cancel, library docs |
| Một bean tự tạo executor rồi không đóng | Thiếu owner lifecycle | `@PreDestroy` hoặc `SmartLifecycle` thích hợp |
| Nhiều replica vượt API quota toàn cụm | Semaphore chỉ local | Distributed rate limit/coordination |
| Bật thêm Semaphore cạnh JDBC pool làm latency tăng | Giới hạn thừa hoặc chọn sai tầng | Đo DB pool, quyết định đặt gate nơi cần |
| CPU đạt 100%, throughput không tăng | Work CPU-bound | Core count, CPU profile; virtual threads không tăng compute |
| Virtual thread pinned kéo dài trên JDK 21 | Blocking trong synchronized/native | JFR pinned events, thread dumps, JDK upgrade |
| HTTP 202 nhưng job mất khi restart | Admission chỉ ở RAM | Durable queue và ack/idempotency |
| Request mới vẫn vào khi publish refusing | Readiness là tín hiệu, chưa có app gate | Kiểm routing và trạng thái `stopping` tại submit |
| `executor.isTerminated=false` sau deadline | Task không cooperatively dừng hoặc unstarted pending | Log failure, thread dump, external resource cleanup |

## 15. Bài tập mở rộng theo mức độ

### Bài tập A — Bằng chứng 2 external calls và 5 admitted jobs

Chạy sáu `kind=block` từ một JVM mới. Xác nhận 5 HTTP 202, 1 HTTP 429, `externalActive=2`, `admittedInFlight=5`, `externalPeak<=2`. Nêu rõ tại sao **không** có một virtual-thread pool size bằng 2.

### Bài tập B — Kiểm chứng release ở happy path

Gọi `POST /lab/release`, chờ các accepted jobs kết thúc, đối chiếu `done=5`, `admissionAvailable=5`, `externalAvailable=2`. Giải thích vì sao phải đợi trạng thái yên trước khi so snapshot.

### Bài tập C — Kiểm chứng cleanup khi exception

Chạy `kind=fail`. Quan sát `FAILED` sau response HTTP 202, `LAB_EXTERNAL_RELEASE` và `LAB_ADMISSION_RELEASE`. Chỉ ra khối `finally` bảo đảm release dù có exception.

### Bài tập D — Kiểm chứng stop khi đang block

Chạy 5 jobs block nhưng không release, dùng Ctrl+C/SIGTERM. Ghi `LAB_SHUTDOWN_INTERRUPT`, các marker interrupted/release và `LAB_SHUTDOWN_END`; giải thích vì sao `shutdownNow()` chỉ là best-effort nếu task không cooperative.

### Bài tập E — Thử thiếu cleanup trong bản copy

Trong một bản sao lab, cố ý bỏ `externalSlots.release()` ở `finally`. Gửi một job `fail`, rồi thêm jobs mới; đối chiếu số permits và hiện tượng chờ timeout. Khôi phục code ngay. **Chỉ làm với simulated resource**, không tạo leak trên môi trường production hoặc dịch vụ ngoài.

### Bài tập F — Thay mock external bằng HTTP thật có kiểm soát

Dùng một local mock server hoặc test container, không dùng dịch vụ production. Giới hạn 2 concurrent requests, timeout hữu hạn, log request start/end; kiểm rằng không vượt trần dưới tải, và callback cleanup/đóng response được gọi khi timeout/interrupt.

### Bài tập G — Thay mock external bằng JDBC pool

Dùng database thử nghiệm và Hikari metrics. Tạo 10+ virtual threads nhưng pool 2 connections; đo active/pending/acquire time và xác nhận connection được trả sau exception. Đánh giá có cần semaphore bổ sung hay pool đã giới hạn hợp lý.

### Bài tập H — Kiểm crash thật và durability

So sánh graceful SIGTERM với SIGKILL sau HTTP 202 trong lab. Xác nhận sau SIGKILL không thể dựa vào `@PreDestroy` hoặc RAM job registry để recovery. Đề xuất durable table/queue + retry/idempotency và test redelivery sau restart.

## 16. Checklist nghiệm thu

- [ ] Chạy đúng Java 21+ và biên dịch được project Spring Boot 3.5.x.
- [ ] Biết `spring.threads.virtual.enabled=true` và `spring.main.keep-alive=true` có vai trò khác nhau.
- [ ] Quan sát `Thread.currentThread().isVirtual()==true` trong worker.
- [ ] Giải thích virtual threads không làm database/API có sức chứa vô hạn.
- [ ] Tái lập 5 accepted + 1 rejected với admission 5.
- [ ] Thấy externalActive/Peak tối đa 2 với semaphore external 2.
- [ ] Thấy các job còn lại ở `WAITING_SLOT` thay vì lén vào external critical section.
- [ ] Chứng minh success và fail đều chạy qua `finally` để giải phóng permits.
- [ ] Bắt và xử lý `InterruptedException`, khôi phục interrupt flag.
- [ ] Xác nhận shutdown mềm và escalation interrupt có bounded wait.
- [ ] Đọc `executor.isTerminated()` và số permits sau stop để kết luận trên phạm vi lab.
- [ ] Nêu giới hạn của SIGKILL và uninterruptible external I/O.
- [ ] Biết đóng JDBC connections, HTTP bodies và broker consumers theo owner thích hợp.
- [ ] Biết pool properties của Boot không thay thế external concurrency limit.
- [ ] Phân biệt readiness routing, admission và executor shutdown.
- [ ] Đề xuất durable job queue/idempotency nếu 202 phải bảo đảm không mất việc.
- [ ] Phân biệt pinning JDK 21 với cải tiến JDK 24+.
- [ ] Ghi được logs/metrics cho accepted, rejected, externalPeak, failed và interrupted.

## 17. Tài liệu chính thức

1. **Oracle JDK 21 — Virtual Threads**: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html — lifecycle, carrier, semaphore, interrupt, pinning và quan sát.
2. **Java SE 21 — Executors**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html — `newVirtualThreadPerTaskExecutor()`.
3. **Java SE 21 — ExecutorService**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html — `shutdown`, `shutdownNow`, `awaitTermination` và `close`.
4. **Spring Boot 3.5 — SpringApplication, Virtual Threads**: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html — enablement, daemon và keep-alive.
5. **Spring Boot 3.5 — Task Execution and Scheduling**: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html — Boot auto-configured executor/scheduler khi dùng virtual threads.
6. **Spring Boot 3.5 — Graceful Shutdown**: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html — HTTP connector và lifecycle phase timeout.
7. **Spring Framework 6.2 — SimpleAsyncTaskExecutor**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/SimpleAsyncTaskExecutor.html — virtual threads option và concurrency limiting.
8. **Java SE 21 — Semaphore**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html — acquire/release, fairness và interruptibility.

**Kết luận:** Virtual threads làm cho việc dùng **một Java thread trên mỗi công việc blocking** khả thi hơn; chúng không thay thế resource limits. Một hệ thống đúng phải **từ chối hoặc xếp việc có giới hạn trước khi tạo vô số threads**, **giới hạn các thao tác chiếm tài nguyên ngoài**, **đặt deadline**, **giải phóng trong `finally`** và **ngừng intake + drain/cancel khi shutdown**. Trong lab, các mốc đáng tin là `externalPeak<=2`, permits trả về ban đầu và `terminated=true` khi dừng hợp tác. Trong production, phải bổ sung kiểm chứng thực tế với JDBC/HTTP/broker và lưu job bền vững trước khi cam kết không mất việc.