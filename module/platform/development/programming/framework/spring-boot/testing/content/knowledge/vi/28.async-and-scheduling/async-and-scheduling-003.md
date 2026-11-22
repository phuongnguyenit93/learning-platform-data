# Chờ điều kiện hoàn tất thay cho thời gian ngủ cố định

## 1. Vì sao Thread.sleep làm bài kiểm thử bất đồng bộ dễ thất bại?

Trong module **Spring Boot - testing**, nhóm **Bất đồng bộ và lịch chạy**, một lời gọi bất đồng bộ có thể hoàn thành sau vài mili-giây trên máy phát triển nhưng chậm hơn khi CI thiếu CPU, đang khởi động JVM hoặc chờ database, broker hay thread pool. Kiểm thử phải chờ **trạng thái nghiệp vụ đã hoàn tất**, không chỉ chờ một khoảng thời gian được đoán trước.

Phản ví dụ:

~~~java
// Mã minh họa anti-pattern, KHÔNG đưa vào test runnable.
jobService.submit("job-7", "hello");
Thread.sleep(1_000);
assertThat(jobStore.find("job-7").orElseThrow().status())
        .isEqualTo(JobStatus.SUCCEEDED);
~~~

Với đoạn code trên:

- Nếu job hoàn thành trong 5 ms, test vẫn **chờ đủ 1.000 ms**, làm suite chậm vô ích.
- Nếu job mất 1.300 ms do CI quá tải, assertion thực hiện quá sớm → **flaky failure**.
- Nếu worker ném exception và không cập nhật trạng thái, test chỉ biết trạng thái chưa đúng, khó tìm nguyên nhân.
- Nếu một task được submit nhưng chưa từng chạy vì executor bị shutdown/rejected, tăng sleep không sửa được.
- Nếu tác động nghiệp vụ xảy ra **sau** một callback hoặc database commit, việc Future đã được tạo không chứng minh tác động đã nhìn thấy được.

Cách đúng:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .pollInterval(Duration.ofMillis(50))
    .untilAsserted(() ->
        assertThat(jobStore.find("job-7").orElseThrow().status())
            .isEqualTo(JobStatus.SUCCEEDED)
    );
~~~

`untilAsserted` kiểm tra lại assertion nhiều lần cho tới khi đúng hoặc hết **deadline tối đa**. Khi điều kiện đúng, test tiếp tục ngay; nó **không phải** ngủ đủ 5 giây. `atMost` là giới hạn an toàn, không phải độ trễ mong đợi.

Bài học này trình bày đầy đủ Awaitility, `CompletableFuture.get(timeout)`, `CountDownLatch`/`Future`, kiểm thử `@Async` và `@Scheduled`, thread visibility, lỗi bất đồng bộ, transaction khác thread, cleanup và chạy song song. Ví dụ chạy được dựa trên **Java 17, Spring Boot 3.5.16, JUnit Jupiter, AssertJ và Awaitility 4.x**.

## 2. Phân biệt ba câu hỏi: đã gửi, đã chạy, đã hoàn tất

Một event/command đi qua nhiều trạng thái:

~~~text
Test thread
    |
    +-- submit(request)  ---> accepted / QUEUED
                                    |
                              executor thread
                                    |
                                RUNNING
                                    |
                       +------------+-----------+
                       |                        |
                    SUCCEEDED                 FAILED
                       |                        |
                 business state             error/cause
                 visible to test            visible to test
~~~

| Quan sát | Chứng minh | Chưa chứng minh |
| --- | --- | --- |
| Method `submit` đã return | Lời gọi phía gửi hoàn tất | Worker đã bắt đầu/chạy xong |
| Kafka `send().get()` đã return | Producer được xác nhận theo broker/acks config | Consumer đã xử lý business effect |
| `Future.isDone()` | Computation gắn với Future đã kết thúc, có thể thành công, lỗi hoặc bị hủy | DB/outbox/external effect đã commit, nếu chúng nằm ngoài Future |
| `CompletableFuture.get(timeout)` thành công | Future hoàn thành không ném exception | Eventual projection khác service đã cập nhật |
| Marker database `status=SUCCEEDED` | Quan sát được business state theo transaction/isolation của query | Tất cả side effects bên ngoài DB đã hoàn tất |
| `CountDownLatch` đếm về 0 | Các bên đã gọi `countDown()` theo protocol | Bất kỳ bước nào xảy ra **sau** tín hiệu đã hoàn tất |
| `@Scheduled` tick count tăng | Ít nhất một lần callback đã chạy | Task có đúng lịch millisecond tuyệt đối hoặc mọi job con đã hoàn tất |

Muốn test tin cậy, hãy chọn **tín hiệu tương ứng với hợp đồng của ca kiểm thử**. Ví dụ kiểm thử consumer xử lý thanh toán cần xác minh số dư/ledger hoặc idempotency marker đã commit; chỉ biết message được publish là chưa đủ.

Một dạng invariant thường gặp:

~~~text
submit command
    -> await until authoritative business predicate is true
    -> assert final values / cardinality / side effects
    -> release/cleanup resources
~~~

## 3. Khi nào dùng Awaitility, Future, latch và virtual time?

| Công cụ | Dùng tốt nhất cho | Đặc điểm |
| --- | --- | --- |
| Awaitility `await().untilAsserted(...)` | Poll một state eventually consistent: DB row, status API, in-memory concurrent store | Có timeout/poll interval và thông báo assertion |
| Awaitility `until(...)` | Boolean/predicate đơn giản, có thể đọc nhiều lần | Phải là condition **không gây tác dụng phụ** |
| `Future.get(timeout, unit)` | Chờ **một tác vụ có Future handle** trả kết quả/lỗi | Giữ nguyên exception và deadline, không cần polling state |
| `CompletableFuture.allOf(...)` | Chờ một tập futures do test biết trước | Kết thúc khi tất cả futures hoàn thành; cần inspect kết quả/lỗi riêng |
| `CountDownLatch.await(timeout, unit)` | Đồng bộ thứ tự giữa threads ở điểm chính xác | Signal-driven, không phụ thuộc tốc độ CI |
| `CyclicBarrier` / `Phaser` | Buộc nhiều worker tới điểm cạnh tranh hoặc nhiều phase | Phù hợp race/concurrency tests |
| Reactor `StepVerifier.withVirtualTime` | Publisher phụ thuộc Reactor scheduler | Điều khiển **virtual scheduler**, không phải đồng hồ OS/DB |
| Injected `Clock.fixed` / `Clock.offset` | Kiểm thử nghiệp vụ dựa trên thời gian: TTL, deadline | Không làm thread pool/scheduler tự chạy |
| `MockRestServiceServer` / embedded broker probe | Test client/network pipeline tương ứng | Cần quan sát **sau xử lý**, không chỉ request được gửi |

Không dùng một công cụ cho mọi vấn đề. Nếu có `CompletableFuture` trả về từ đúng boundary mà test quan tâm, `get(timeout)` là giải pháp rõ. Nếu completion ở database qua nhiều service, Awaitility quan sát DB hoặc API phù hợp hơn. Nếu cần điều khiển thứ tự hai threads để tái hiện race, latch/barrier chính xác hơn việc hy vọng scheduler có thời điểm mong muốn.

## 4. Awaitility: điều kiện và giới hạn rõ ràng

Awaitility là Java DSL cho tests bất đồng bộ. Spring Boot 3.5 `spring-boot-starter-test` đã mang Awaitility trong test dependencies; cũng có thể khai báo trực tiếp `testImplementation 'org.awaitility:awaitility'` do Boot BOM quản lý version.

Các pattern cốt lõi:

~~~java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

// Boolean predicate: trả true khi giá trị đạt 3.
await().atMost(Duration.ofSeconds(5))
       .until(() -> counter.get() >= 3);

// AssertJ được chạy lại cho tới khi pass.
await().atMost(Duration.ofSeconds(5))
       .pollInterval(Duration.ofMillis(50))
       .untilAsserted(() ->
           assertThat(repository.count()).isEqualTo(3)
       );
~~~

Đây là **đoạn code minh họa**; `counter`/`repository` phải do bài test tạo. Trong bộ ví dụ runnable bên dưới, `JobStore` và `TickCounter` là các dependency thực.

### Ý nghĩa từng tham số

- `atMost(Duration.ofSeconds(5))`: deadline tối đa cho điều kiện, không cam kết task luôn mất 5 giây.
- `pollInterval(Duration.ofMillis(50))`: khoảng giữa các lần quan sát; chọn theo khả năng đáp ứng và tải hệ thống, không đặt 1 ms một cách máy móc.
- `pollDelay(Duration.ZERO)`: có thể kiểm tra ngay lần đầu nếu muốn; mặc định Awaitility có độ trễ polling tùy cấu hình.
- `untilAsserted(...)`: chạy lại assertions; timeout sẽ báo điều kiện nào chưa đúng.
- `until(predicate)`: predicate nên **read-only và nhanh**, không tự tiêu thụ messages, xóa row hay kích hoạt business effect trong mỗi lần poll.

**Nếu assertion được đánh giá đúng sớm, test kết thúc sớm.** Không gọi `Thread.sleep(...)` thêm sau `await()` vì đã có tín hiệu completion.

### Lưu ý điều kiện nhiều trạng thái

Không chỉ await `status != QUEUED` vì `FAILED` cũng thỏa mãn. Nếu business yêu cầu thành công, hãy đợi **`SUCCEEDED`** và kiểm tra payload/amount/record count. Nếu trạng thái cuối là FAILED, có thể cấu hình fail-fast để chẩn đoán sớm thay vì chờ hết deadline.

### Không poll rồi tạo side effect

Sai:

~~~java
await().until(() -> queue.poll() != null);
~~~

`queue.poll()` **lấy và loại bỏ phần tử** mỗi lần gọi, khiến chính test tiêu thụ data. Đúng hơn là kiểm tra số lượng/marker bất biến khi thread-safe, hoặc nhận phần tử một lần bằng `poll(timeout, unit)` và assert sau đó. Với Kafka/RabbitMQ, không poll test helper làm mất record mà app consumer cần xử lý.

## 5. Timeout không phải một con số ma thuật

Mọi async test cần **giới hạn hữu hạn** để không treo CI, nhưng không cần ngủ bằng đúng thời lượng đó.

Một cấu hình tham khảo:

~~~java
await()
    .atMost(Duration.ofSeconds(8))
    .pollInterval(Duration.ofMillis(50))
    .untilAsserted(() ->
        assertThat(statusService.lookup(jobId)).isEqualTo("DONE")
    );
~~~

Đây là snippet minh họa. 8 giây là **ngưỡng tối đa theo SLA test environment**, không phải lời hứa job cần 8 giây. Test có thể hoàn tất sau vài milliseconds.

Chọn timeout dựa trên:

1. Thời gian khởi động/điều phối executor, broker, DB migration.
2. Độ trễ nội bộ của pipeline, retry/backoff và async batching.
3. Độ tải CI và khả năng contention hợp lệ.
4. Tổng ngân sách thời gian của suite.
5. Số lần polling đủ để chẩn đoán.
6. Giới hạn bên trong client (HTTP, DB) và timeout ở tầng ngoài (JUnit/Gradle/CI).

**Không chữa một deadlock bằng cách tăng timeout vô hạn.** Nếu một điều kiện luôn fail khi timeout, đọc root cause ở worker/log/call stack, xác định task có thật sự được submit, thread pool còn worker không và DB/broker có sẵn không.

Một bẫy: đặt `pollInterval` lớn hơn `atMost` thì có thể không kịp một lần quan sát hữu ích. Tránh polling dày trên database dùng chung; chọn interval vừa đủ.

## 6. Bộ ví dụ runnable: @Async + @Scheduled với tín hiệu rõ ràng

Ứng dụng ví dụ thực hiện hai luồng:

- **Bất đồng bộ:** `JobSubmissionService.submit` tạo `QUEUED` trong `JobStore`, rồi gọi `AsyncJobWorker.process` có `@Async("jobExecutor")` qua một **Spring bean khác**. Worker chuyển trạng thái thành `SUCCEEDED` hoặc `FAILED`, đồng thời trả `CompletableFuture` cho caller.
- **Lịch chạy:** `TickCounter.tick` được gọi bởi `@Scheduled(fixedDelayString=..., initialDelayString=...)`. Trong integration test riêng, giảm delay qua properties và await cho tới khi counter tăng; không sleep đợi một khoảng giờ cố định.

Cấu trúc tệp:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/conditionwait/
    ConditionWaitApplication.java
    JobAsyncConfig.java
    JobStatus.java
    JobSnapshot.java
    JobStore.java
    JobHandle.java
    AsyncJobWorker.java
    JobSubmissionService.java
    TickCounter.java
src/main/resources/
    application.properties
src/test/java/com/example/conditionwait/
    AsyncJobIntegrationTest.java
    ScheduledTickIntegrationTest.java
    GateWithoutSleepTest.java
~~~

Các file Java đều dùng package `com.example.conditionwait`. Ví dụ không cần web server, database hoặc Docker; không có HTTP side effect để làm mờ ý nghĩa của completion.

## 7. Gradle và Spring Boot 3.5

**`settings.gradle`:**

~~~groovy
rootProject.name = 'condition-wait-tests'
~~~

**`build.gradle` (Groovy DSL):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    // Có thể khai báo tường minh dù starter-test đã đưa vào.
    testImplementation 'org.awaitility:awaitility'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và Awaitility; khai báo trực tiếp `org.awaitility:awaitility` làm rõ dependency và dùng phiên bản tương thích do Spring Boot 3.5 BOM quản lý. Với bản Boot 3.5.16, BOM quản lý Awaitility 4.2.2. Tránh copy API chỉ có trong Awaitility 4.3.x vào demo nếu không cập nhật version.

Java 17 đáp ứng `record`, `CompletableFuture.failedFuture`, `Duration` và `java.util.concurrent`. Cần Gradle Wrapper được tạo trước (hoặc chạy bằng Gradle cài sẵn); script chỉ mô tả dependencies, không tự sinh `gradlew`.

**`src/main/resources/application.properties`:**

~~~properties
# Bình thường không chạy scheduler tick liên tục trong demo.
demo.tick.initial-delay-ms=600000
demo.tick.delay-ms=600000
~~~

Hai properties được phép override **trong test scheduler riêng** để không phụ thuộc thời gian chờ 10 phút của cấu hình mặc định. Không thay cấu hình production một cách global cho mọi tests.

## 8. Khởi động application và cấu hình thread pool

**`src/main/java/com/example/conditionwait/ConditionWaitApplication.java`:**

~~~java
package com.example.conditionwait;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class ConditionWaitApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConditionWaitApplication.class, args);
    }
}
~~~

`@EnableAsync` kích hoạt interception của `@Async`, còn `@EnableScheduling` đăng ký những method `@Scheduled` với Spring scheduler. Việc khai báo annotation không tự đảm bảo mọi Java method gọi qua `this` sẽ có proxy interception; xem phần self-invocation.

**`src/main/java/com/example/conditionwait/JobAsyncConfig.java`:**

~~~java
package com.example.conditionwait;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class JobAsyncConfig {

    @Bean(name = "jobExecutor")
    ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("job-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        executor.initialize();
        return executor;
    }
}
~~~

`@Async("jobExecutor")` chọn **đúng executor có tên jobExecutor**, không phụ thuộc executor mặc định của Boot. Prefix tên thread giúp integration test chứng minh code được thực thi trên worker thay vì thread của test; nó **không** phải cơ chế đồng bộ.

Với production, sizing và rejection policy phải tính theo workload/concurrency/latency. Queue đầy có thể ném `TaskRejectedException` **ngay lúc submit**, trước khi job được chạy. Một hệ thống thật cần ghi nhận rejected job/metric, không chỉ await đến timeout.

## 9. State model: enum và immutable snapshot

**`src/main/java/com/example/conditionwait/JobStatus.java`:**

~~~java
package com.example.conditionwait;

public enum JobStatus {
    QUEUED,
    SUCCEEDED,
    FAILED
}
~~~

**`src/main/java/com/example/conditionwait/JobSnapshot.java`:**

~~~java
package com.example.conditionwait;

public record JobSnapshot(
        String id,
        JobStatus status,
        String result,
        String workerThread,
        String error
) {
}
~~~

Dùng immutable `record` để mỗi lần đọc thấy **một snapshot nhất quán** gồm status/result/error. Nếu dùng nhiều trường `volatile` rời rạc, test có thể thấy `status=SUCCEEDED` nhưng `result` còn từ bản cũ do update không đồng bộ giữa nhiều fields; immutable object thay thế atomically trong map rõ ràng hơn.

`FAILED` là một trạng thái cuối riêng. Không coi “không còn QUEUED” là “thành công”.

## 10. Thread-safe JobStore cho integration test

**`src/main/java/com/example/conditionwait/JobStore.java`:**

~~~java
package com.example.conditionwait;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

@Component
public class JobStore {

    private final Map<String, JobSnapshot> jobs =
            new ConcurrentHashMap<>();

    public void queued(String id) {
        JobSnapshot initial = new JobSnapshot(
                id, JobStatus.QUEUED, null, null, null
        );

        if (jobs.putIfAbsent(id, initial) != null) {
            throw new IllegalArgumentException(
                    "Duplicate job id: " + id
            );
        }
    }

    public void succeeded(
            String id,
            String result,
            String workerThread
    ) {
        replace(
                id,
                new JobSnapshot(
                        id, JobStatus.SUCCEEDED,
                        result, workerThread, null
                )
        );
    }

    public void failed(
            String id,
            String error,
            String workerThread
    ) {
        replace(
                id,
                new JobSnapshot(
                        id, JobStatus.FAILED,
                        null, workerThread, error
                )
        );
    }

    private void replace(String id, JobSnapshot snapshot) {
        jobs.compute(id, (key, old) -> {
            if (old == null) {
                throw new IllegalStateException(
                        "Unknown job: " + id
                );
            }
            return snapshot;
        });
    }

    public Optional<JobSnapshot> find(String id) {
        return Optional.ofNullable(jobs.get(id));
    }

    public void remove(String id) {
        jobs.remove(id);
    }
}
~~~

`ConcurrentHashMap` hỗ trợ truy cập từ test thread và worker thread. `putIfAbsent` chống trùng ID trong phạm vi một JVM; `compute` thay thế snapshot atomically. Điều đó giúp polling có thể quan sát transition mà không dùng lock thô hoặc sleep.

**Giới hạn:** Đây là test/demo in-memory store, không có durability hoặc consistency giữa nhiều JVM/pods. Với production, dùng database/queue và kiểm tra commit/acks thực; không suy rằng một ConcurrentHashMap xử lý được distributed idempotency.

### Vì sao không dùng HashMap thường?

`HashMap` không thread-safe khi đồng thời read/write; chạy dưới CI có thể thấy stale state hoặc lỗi concurrency khó lặp lại. Tương tự, một boolean field đọc giữa threads cần `volatile`, `AtomicBoolean` hoặc synchronization đúng. Không “sửa” visibility bug bằng cách ngủ lâu hơn.

## 11. CompletableFuture handle cho một job

**`src/main/java/com/example/conditionwait/JobHandle.java`:**

~~~java
package com.example.conditionwait;

import java.util.concurrent.CompletableFuture;

public record JobHandle(
        String id,
        CompletableFuture<Void> completion
) {
}
~~~

Handle gom job ID và completion future. Đây là mô hình minh họa **chỉ trong JVM**; không serialize CompletableFuture vào JSON. Với REST API nhận asynchronous command, response thường có job ID/status URL; client poll state qua một API riêng, không mang Future qua network.

`Future` chỉ nói về completion của công việc gắn với nó. Nếu worker fire-and-forget thêm một task khác, Future của worker ban đầu có thể complete trước side effect của task con; cần nối futures/await đúng business state.

## 12. @Async worker thực và cách báo cả success lẫn error

**`src/main/java/com/example/conditionwait/AsyncJobWorker.java`:**

~~~java
package com.example.conditionwait;

import java.util.Locale;
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncJobWorker {

    private final JobStore store;

    public AsyncJobWorker(JobStore store) {
        this.store = store;
    }

    @Async("jobExecutor")
    public CompletableFuture<Void> process(
            String id,
            String input
    ) {
        String thread = Thread.currentThread().getName();

        try {
            // Cố ý cho phép một ca test thất bại có kiểm soát.
            if ("FAIL".equals(input)) {
                throw new IllegalStateException(
                        "simulated worker failure"
                );
            }

            store.succeeded(
                    id,
                    input.toUpperCase(Locale.ROOT),
                    thread
            );
            return CompletableFuture.completedFuture(null);
        } catch (RuntimeException failure) {
            store.failed(
                    id,
                    failure.getMessage(),
                    thread
            );
            return CompletableFuture.failedFuture(failure);
        }
    }
}
~~~

Trong Spring proxy-based async, lời gọi tới bean `AsyncJobWorker` qua Spring proxy được submit vào executor. Phần thân `process` chạy trên thread tên `job-worker-...` do ta cấu hình. Method trả `CompletableFuture.completedFuture(null)` trên worker để Spring hoàn thành future mà caller nhận; trên nhánh lỗi dùng `failedFuture` để lỗi **không biến mất**.

Điểm cần phân biệt:

- `store.succeeded(...)` đánh dấu business state hoàn tất (trong demo).
- `completion` báo worker method đã hoàn thành.
- Một callback khác chạy sau đó phải được awaited riêng nếu thuộc contract.
- Với `@Async void`, exception không xuất hiện trong Future của caller; cần `AsyncUncaughtExceptionHandler`/observability phù hợp. Vì vậy khi cần kiểm thử kết quả/lỗi, ưu tiên Future/CompletableFuture.

Trong production có DB, `store.succeeded` phải được thay bằng transaction commit/DB status có nghĩa nghiệp vụ. Không đánh dấu SUCCEEDED **trước** khi side effect quan trọng thực sự hoàn tất.

## 13. Submission service gọi sang bean khác

**`src/main/java/com/example/conditionwait/JobSubmissionService.java`:**

~~~java
package com.example.conditionwait;

import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class JobSubmissionService {

    private final JobStore store;
    private final AsyncJobWorker worker;

    public JobSubmissionService(
            JobStore store,
            AsyncJobWorker worker
    ) {
        this.store = store;
        this.worker = worker;
    }

    public JobHandle submit(String id, String input) {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(input, "input");

        store.queued(id);
        return new JobHandle(
                id,
                worker.process(id, input)
        );
    }
}
~~~

`JobSubmissionService` và `AsyncJobWorker` là **hai Spring beans**. Khi `submit` gọi `worker.process`, lời gọi đi qua proxy của `AsyncJobWorker`, nên `@Async` được kích hoạt.

Phản ví dụ self-invocation:

~~~java
@Service
class IncorrectWorker {
    public void submit() {
        doWorkAsync(); // this.doWorkAsync(): bỏ qua proxy!
    }

    @Async
    public void doWorkAsync() {
        // Có thể chạy đồng bộ trong thread gọi.
    }
}
~~~

Đây là **skeleton minh họa lỗi**. Trong Spring proxy mode mặc định, `@Async` trên lời gọi nội bộ cùng instance không được áp dụng. Test chỉ kiểm “kết quả cuối đúng” có thể vẫn PASS vì task chạy đồng bộ! Vì vậy test chính sẽ assert **worker thread name** và phân biệt nó với caller thread.

**Một giới hạn của code demo:** nếu executor reject ngay lúc `submit`, marker QUEUED vừa được tạo có thể còn lại. Khi xây production, bắt `TaskRejectedException` quanh lời gọi scheduling, cập nhật trạng thái FAILED/REJECTED hoặc dùng transactional enqueue, rồi trả lỗi thích hợp. Không để job im lặng QUEUED vô hạn.

## 14. @Scheduled task có counter có thể quan sát

**`src/main/java/com/example/conditionwait/TickCounter.java`:**

~~~java
package com.example.conditionwait;

import java.util.concurrent.atomic.AtomicLong;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class TickCounter {

    private final AtomicLong ticks = new AtomicLong();

    @Scheduled(
            fixedDelayString = "${demo.tick.delay-ms:600000}",
            initialDelayString = "${demo.tick.initial-delay-ms:600000}"
    )
    public void tick() {
        ticks.incrementAndGet();
    }

    public long count() {
        return ticks.get();
    }
}
~~~

Theo Spring Framework, `fixedDelay` đếm từ **khi lần chạy trước hoàn tất** tới lần chạy tiếp theo; `fixedRate` tính từ mốc bắt đầu các lần chạy theo nhịp, còn `cron` tính theo lịch với timezone. Cả hai thuộc loại thời gian **thực của scheduler**, không phải tiến nhanh bằng `Clock.offset`.

Trong cấu hình mặc định, tick đầu tiên chỉ được lên lịch sau 600.000 ms (10 phút). Test scheduler sẽ override riêng:

~~~properties
demo.tick.initial-delay-ms=0
demo.tick.delay-ms=120
~~~

Có thể tick đầu đã chạy **trước khi JUnit test method bắt đầu** vì Spring context khởi động trước. Test không assert `count()==1` sau 120 ms mà lấy **baseline counter hiện tại** và await `count() > baseline`. Không có bảo đảm chính xác từng tick theo mili-giây khi thread pool/CPU scheduling khác nhau.

**Bài này không dùng clock virtualization cho @Scheduled**, bởi Java `Clock` injection không tự thay clock của Spring TaskScheduler. Nếu muốn kiểm tra logic chạy tại một thời điểm cụ thể, hãy tách logic khỏi trigger và test bằng Clock giả; dùng scheduler integration test nhỏ để chứng minh binding thật.

## 15. Integration test @Async với Awaitility

**`src/test/java/com/example/conditionwait/AsyncJobIntegrationTest.java`:**

~~~java
package com.example.conditionwait;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class AsyncJobIntegrationTest {

    @Autowired
    JobSubmissionService submissions;

    @Autowired
    JobStore store;

    private final List<JobHandle> created = new ArrayList<>();

    private JobHandle newJob(String payload) {
        String id = "test-" + UUID.randomUUID();
        JobHandle handle = submissions.submit(id, payload);
        created.add(handle);
        return handle;
    }

    private JobSnapshot awaitStatus(
            String id,
            JobStatus expected
    ) {
        await()
                .atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(50))
                .untilAsserted(() -> {
                    JobSnapshot snapshot =
                            store.find(id).orElseThrow();
                    assertThat(snapshot.status()).isEqualTo(expected);
                });
        return store.find(id).orElseThrow();
    }

    @AfterEach
    void finishJobsThenCleanOwnIds() throws Exception {
        try {
            for (JobHandle handle : created) {
                try {
                    // Chờ worker kết thúc trước khi xóa store entry.
                    handle.completion().get(5, TimeUnit.SECONDS);
                } catch (ExecutionException completedWithFailure) {
                    // Một ca test chủ ý mô phỏng worker lỗi.
                    // Ca test đó phải assert lỗi riêng.
                }
            }
        } finally {
            created.forEach(h -> store.remove(h.id()));
        }
    }

    @Test
    void eventuallySucceedsWithoutSleeping() throws Exception {
        String callerThread = Thread.currentThread().getName();
        JobHandle handle = newJob("hello");

        JobSnapshot result = awaitStatus(
                handle.id(), JobStatus.SUCCEEDED
        );

        assertThat(result.result()).isEqualTo("HELLO");
        assertThat(result.workerThread())
                .startsWith("job-worker-")
                .isNotEqualTo(callerThread);

        handle.completion().get(5, TimeUnit.SECONDS);
    }

    @Test
    void eventuallyFailsAndFutureExposesCause() {
        JobHandle handle = newJob("FAIL");

        JobSnapshot result = awaitStatus(
                handle.id(), JobStatus.FAILED
        );

        assertThat(result.error())
                .isEqualTo("simulated worker failure");
        assertThat(result.result()).isNull();

        assertThatThrownBy(
                () -> handle.completion().get(
                        5, TimeUnit.SECONDS
                )
        ).isInstanceOf(ExecutionException.class)
         .hasCauseInstanceOf(IllegalStateException.class);
    }

    @Test
    void twoIndependentJobsBothReachBusinessCompletion()
            throws Exception {
        JobHandle first = newJob("alpha");
        JobHandle second = newJob("beta");

        await().atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(50))
                .untilAsserted(() -> {
                    assertThat(
                            store.find(first.id()).orElseThrow()
                                    .result()
                    ).isEqualTo("ALPHA");
                    assertThat(
                            store.find(second.id()).orElseThrow()
                                    .result()
                    ).isEqualTo("BETA");
                });

        CompletableFuture.allOf(
                first.completion(),
                second.completion()
        ).get(5, TimeUnit.SECONDS);

        assertThat(
                store.find(first.id()).orElseThrow().status()
        ).isEqualTo(JobStatus.SUCCEEDED);

        assertThat(
                store.find(second.id()).orElseThrow().status()
        ).isEqualTo(JobStatus.SUCCEEDED);
    }

    @Test
    void duplicateJobIdIsRejectedInsteadOfOverwritingState()
            throws Exception {
        JobHandle existing = newJob("first");

        assertThatThrownBy(
                () -> submissions.submit(existing.id(), "second")
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessageContaining("Duplicate job id");

        existing.completion().get(5, TimeUnit.SECONDS);
        assertThat(
                awaitStatus(existing.id(), JobStatus.SUCCEEDED)
                        .result()
        ).isEqualTo("FIRST");
    }
}
~~~

**Bốn integration tests** chứng minh:

1. Job thực sự chạy qua Spring async proxy, cập nhật business state, thread name bắt đầu `job-worker-`.
2. Nhánh lỗi không bị nuốt; vừa có `FAILED` snapshot vừa có exception qua `Future.get(timeout)`.
3. Hai jobs với ID riêng đều đạt điều kiện; `allOf` chứng minh cả hai futures kết thúc.
4. Submit ID trùng bị reject, không ghi đè state của job ban đầu.

Không có `Thread.sleep(...)`. Các tác vụ có thể hoàn thành trước cả lần poll đầu tiên — test vẫn PASS. Thời gian timeout là **giới hạn**, không phải thời gian được bắt buộc chờ.

`@AfterEach` đợi các futures của chính method, rồi dọn keys do method tạo, tránh worker cập nhật map **sau khi test đã xóa state**. Với worker error có chủ đích, `ExecutionException` được chấp nhận trong cleanup, nhưng chính test `eventuallyFailsAndFutureExposesCause` phải xác minh cause. Với production background task có thể không return Future, cần một cơ chế cancellation/join hoặc lifecycle ownership tương đương.

### Điều không được suy diễn từ demo

`ConcurrentHashMap` là source of truth trong một JVM, không phải database/distributed state. `@Async` qua executor thread không mặc định mang theo transaction, `SecurityContext` hoặc mọi `ThreadLocal` của caller; cần test/context propagation thích hợp cho production. Bài test chỉ chứng minh timing/lifecycle trong Spring context đã cấu hình.

## 16. Integration test @Scheduled: đợi tick mới thay vì ngủ

**`src/test/java/com/example/conditionwait/ScheduledTickIntegrationTest.java`:**

~~~java
package com.example.conditionwait;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
                "demo.tick.initial-delay-ms=0",
                "demo.tick.delay-ms=120"
        }
)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
class ScheduledTickIntegrationTest {

    @Autowired
    TickCounter ticks;

    @Test
    void schedulerEventuallyRunsAtLeastOnceAfterObservation() {
        long before = ticks.count();

        await()
                .atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(40))
                .untilAsserted(() ->
                        assertThat(ticks.count()).isGreaterThan(before)
                );
    }

    @Test
    void schedulerCanProduceTwoAdditionalTicks() {
        long before = ticks.count();

        await()
                .atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(40))
                .untilAsserted(() ->
                        assertThat(ticks.count())
                                .isGreaterThanOrEqualTo(before + 2)
                );
    }
}
~~~

**Hai test** ở trên không gọi trực tiếp `ticks.tick()` (nếu gọi trực tiếp sẽ không chứng minh Spring scheduler đã lên lịch). Chúng quan sát bộ đếm `AtomicLong` thật và chỉ đợi **tăng so với baseline**.

Dùng `@DirtiesContext(AFTER_CLASS)` để Spring đóng context có scheduler interval ngắn sau class, tránh một context test-specific tiếp tục phát tick khi các test khác dùng môi trường chung. Đây là một biện pháp lifecycle có chi phí context startup; trong suite thực nên xem lại cách tổ chức các nhóm scheduler tests, không lạm dụng trên mọi test.

### Vì sao không assert “sau 120 ms count phải bằng 1”?

- Callback đầu tiên có thể chạy trước khi test method bắt đầu.
- CPU scheduler và GC không đảm bảo chính xác thời điểm chạy.
- `fixedDelay` đo khoảng chờ sau **lần thực thi trước hoàn tất**.
- Nếu context đã khởi động lâu, counter có thể lớn hơn 1.
- Test suite parallel có thể làm test method bắt đầu ở thời điểm khác.

Đối với bài kiểm thử cron “đúng ngày/giờ”, tách calculation/trigger policy với `Clock.fixed` và `ZoneId`, rồi có một integration test nhỏ xác minh scheduler đăng ký callback. Awaitility không làm điều kiện thời gian calendar ảo đi nhanh hơn.

## 17. CountDownLatch: đồng bộ sự kiện chính xác không cần sleep

Khi test một race hoặc đường xử lý phải tạm dừng ở một điểm, `CountDownLatch` tốt hơn Awaitility polling. Chúng ta cho worker **chủ động báo đã bắt đầu**, sau đó chờ test thread mở gate.

**`src/test/java/com/example/conditionwait/GateWithoutSleepTest.java`:**

~~~java
package com.example.conditionwait;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class GateWithoutSleepTest {

    @Test
    void testControlsWorkerInterleavingWithoutSleep()
            throws Exception {
        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean completed = new AtomicBoolean(false);

        try {
            Future<?> task = executor.submit(() -> {
                started.countDown();

                try {
                    if (!release.await(3, TimeUnit.SECONDS)) {
                        throw new AssertionError(
                                "Worker gate not released"
                        );
                    }
                    completed.set(true);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
            });

            // Chờ tín hiệu worker đã tới gate.
            assertThat(
                    started.await(3, TimeUnit.SECONDS)
            ).isTrue();

            // Lúc này test CHƯA mở gate.
            assertThat(completed.get()).isFalse();

            release.countDown();
            task.get(3, TimeUnit.SECONDS);

            assertThat(completed.get()).isTrue();
        } finally {
            // Không để test fail làm worker mắc kẹt.
            release.countDown();
            executor.shutdownNow();
            assertThat(
                    executor.awaitTermination(3, TimeUnit.SECONDS)
            ).isTrue();
        }
    }

    @Test
    void futureCanCompleteFromAnExplicitTestSignal()
            throws Exception {
        CompletableFuture<String> input =
                new CompletableFuture<>();

        CompletableFuture<String> transformed =
                input.thenApply(String::toUpperCase);

        assertThat(transformed.isDone()).isFalse();

        // Đây là signal, không phải đợi một số millisecond.
        input.complete("ready");

        assertThat(
                transformed.get(2, TimeUnit.SECONDS)
        ).isEqualTo("READY");
    }
}
~~~

Có **hai unit tests** không khởi động Spring. Test thứ nhất làm rõ protocol:

~~~text
Worker: countDown(started) ---- await(release) ---- completed=true
Test:    await(started) ------- assert false --- countDown(release)
                                              \--- Future.get(timeout)
~~~

Không dùng `Thread.sleep` hay đoán thứ tự chạy của OS. Nếu worker không đến gate hoặc không hoàn thành đúng deadline, test FAIL có timeout rõ.

### Hai lưu ý quan trọng

- `CountDownLatch` là **one-shot**: count không tăng lại sau khi về 0. Nhiều phase hoặc barrier tái sử dụng thì cân nhắc `CyclicBarrier` hay `Phaser`.
- Đặt `countDown()` ở **đúng vị trí business completion**. Nếu đặt trước khi commit database, latch chỉ chứng minh worker đã qua dòng signal, không chứng minh commit. Một signal sai vị trí tạo false positive giống như sleep sai.

## 18. Tín hiệu completion khác Future completion thế nào?

Một `CompletableFuture` thường rất hữu ích:

~~~java
CompletableFuture<Void> first = sendAsyncCommandA();
CompletableFuture<Void> second = sendAsyncCommandB();

CompletableFuture.allOf(first, second)
        .get(5, TimeUnit.SECONDS);
~~~

Đây là snippet minh họa với hai hàm giả định, không phải file Java độc lập. Nó chứng minh **hai futures kết thúc**, không chứng minh downstream consumer ở một process khác đã xử lý hay database đã commit.

Với Spring service:

- Nếu `@Async CompletableFuture<T>` trực tiếp xử lý và commit business change trong method, Future hoàn thành là tín hiệu mạnh.
- Nếu `@Async` chỉ enqueue message rồi return, Future hoàn thành **trước** consumer.
- Nếu HTTP `202 Accepted` được trả sau khi job vào queue, phải await job status resource.
- Nếu code fire-and-forget một `void` task khác, Future của bước trước không bao gồm task đó.
- Nếu Kafka `KafkaTemplate.send` hoàn thành, hãy chờ **consumer-side observable effect** nếu test consumer, không dừng ở producer ack.

**Chọn boundary theo mục tiêu.** Một test “HTTP accepted” chỉ cần 202/Location; một test “đơn hàng đã thanh toán” phải kiểm ledger/payment state, không chỉ accepted.

### Future timeout và cancel

`future.get(5, TimeUnit.SECONDS)` ném `TimeoutException` nếu chờ quá lâu; Future không tự bị hủy chỉ vì timeout. Khi test quản lý executor riêng, có thể `cancel(true)` hoặc shutdown trong `finally`. Với executor Spring-managed, đừng shutdown bean dùng chung trong một test method; để Spring context quản lý lifecycle và test cleanup tasks của mình.

Nếu task phụ thuộc network, đặt timeout **ở HTTP client** cũng như test deadline; test timeout một mình không ngắt một socket call đang treo mãi.

## 19. @Async self-invocation: test có thể pass nhưng thực chất sync

Spring Framework xử lý `@Async` mặc định qua proxy. Nếu method đồng bộ trong cùng object gọi một method có `@Async`:

~~~java
@Service
class WrongService {
    public void submit() {
        doAsync(); // Gọi chính this, không qua proxy.
    }

    @Async
    public void doAsync() {
        // Thường không chạy trên async executor theo ý định.
    }
}
~~~

Đây là **phản ví dụ**, cần imports, không phải class thuộc sample runnable. Có thể test chỉ kiểm kết quả cuối và vẫn PASS do `doAsync()` thực thi ngay trong thread gọi. Tách service bean hoặc gọi qua proxy hợp lệ. Trong demo, `JobSubmissionService` inject `AsyncJobWorker` riêng, và test assert tên thread `job-worker-`.

**Không dùng Thread.sleep để “chứng minh async”.** Một chương trình đồng bộ cũng có thể ngủ. Test cần kiểm execution context, completion sequencing, latency contract hoặc trạng thái/signal theo yêu cầu thực.

### @EnableAsync và executor

Chỉ annotate `@Async` mà không bật async support hoặc không qua proxy có thể dẫn đến method không chạy như mong đợi. Trong Boot, executor mặc định tùy các beans/properties, phiên bản và cấu hình; dùng `@Async("jobExecutor")` trong ví dụ giúp có owner và naming rõ ràng. Nếu môi trường dùng Java 21 virtual threads, scheduler/executor behavior có thể thay đổi; bài mẫu chọn Java 17 và một ThreadPoolTaskExecutor tường minh.

## 20. Quan sát trạng thái giữa threads: volatile, Atomic* và transaction

Awaitility **không sửa** data races. Nó chỉ chạy assertion lại. Điều kiện cần đọc được trạng thái thực sự đã được xuất bản giữa các threads.

Phản ví dụ:

~~~java
// Phản ví dụ: không có memory visibility contract.
class UnsafeFlag {
    boolean done;
}
~~~

Một thread ghi `done=true`, thread khác đọc liên tục không có quan hệ happens-before hợp lệ: chương trình có **data race**. Không khắc phục bằng polling nhanh hoặc sleep lâu.

Các lựa chọn phù hợp:

- `AtomicBoolean`/`AtomicInteger`/`AtomicLong` cho trạng thái/đếm đơn giản.
- `volatile` cho cờ trạng thái với visibility; không thay thế atomic compound operations như `counter++`.
- `ConcurrentHashMap` và immutable value snapshots khi có nhiều trường liên quan.
- `CountDownLatch`/`Future.get` cho happens-before và completion signal.
- DB commit rồi query qua transaction/connection đúng khi state nằm trong database.
- `BlockingQueue`/`CompletionService` khi cần một consumer nhận result từ worker.

**Không gọi `Thread.sleep` để bù thiếu synchronization.** Nó không tạo ra giải pháp đúng cho data race.

### Một lúc nhiều fields

Nếu một worker làm:

~~~java
result = "READY";
done = true;
~~~

và cả hai là field thường, test có thể thấy cờ sai/stale, tùy memory ordering. Dùng immutable snapshot trong `AtomicReference`/ConcurrentHashMap, hoặc put fields vào một object và publish qua cơ chế thread-safe. Demo `JobStore` thay toàn bộ `JobSnapshot` atomically bằng `compute` để giữ trạng thái và payload cùng phiên bản.

## 21. Lỗi worker: FAILED, Future exception và fail-fast

Một async test không được chờ mãi `SUCCEEDED` khi job đã đi tới trạng thái cuối `FAILED`.

Cách đơn giản trong ví dụ runnable:

~~~java
await().atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertThat(store.find(jobId).orElseThrow().status())
            .isEqualTo(JobStatus.FAILED)
    );
~~~

Và sau đó:

~~~java
assertThatThrownBy(() -> handle.completion()
        .get(5, TimeUnit.SECONDS))
    .isInstanceOf(ExecutionException.class)
    .hasCauseInstanceOf(IllegalStateException.class);
~~~

Đây là snippets lấy từ integration test, phụ thuộc biến `store`/`handle` có sẵn. Với một test **mong SUCCEEDED**, nên báo lỗi sớm nếu phát hiện `FAILED`, chẳng hạn dùng Awaitility `failFast(...)` theo API 4.x, hoặc viết predicate quan sát terminal state rồi assert trạng thái cuối sau khi thức dậy:

~~~java
await().atMost(Duration.ofSeconds(5))
    .until(() -> {
        JobStatus state = store.find(jobId).orElseThrow()
                .status();
        return state == JobStatus.SUCCEEDED
                || state == JobStatus.FAILED;
    });

assertThat(store.find(jobId).orElseThrow().status())
        .isEqualTo(JobStatus.SUCCEEDED);
~~~

Điều này tránh đợi hết 5 giây khi lỗi đã dứt khoát. Không cấu hình `ignoreExceptions()` toàn cục một cách tùy tiện: nó có thể nuốt cả lỗi database/serialization đáng phải fail. Nếu condition có exception **tạm thời hợp lệ**, dùng `ignoreException(SomeTransientException.class)` với phạm vi rất hẹp và có deadline.

Một method `@Async void` có lỗi uncaught có thể chỉ log thông qua handler, test không thấy được. Khi cần assert lỗi, ưu tiên `CompletableFuture<T>` hoặc một error channel/record có thể quan sát. Test không được PASS chỉ vì không có exception trên **test thread**.

## 22. @Scheduled: fixedDelay, fixedRate, cron và môi trường

Trong Spring:

- `@Scheduled(fixedDelay=...)`: sau khi lần thực thi trước **kết thúc**, chờ delay rồi mới đến lần kế tiếp.
- `@Scheduled(fixedRate=...)`: lịch khởi phát theo nhịp bắt đầu; hành vi overlap thực tế phụ thuộc scheduler capacity và cấu hình.
- `@Scheduled(cron=..., zone=...)`: thời điểm theo lịch cron và zone; không tự có độ chính xác tuyệt đối dưới tải.
- `initialDelay`/`initialDelayString`: trì hoãn lần khởi chạy đầu; hữu ích khi test muốn thay đổi cấu hình.
- `@EnableScheduling`: cần kích hoạt scheduling infrastructure.
- `@Scheduled` method thông thường không nhận arguments, và kết quả return không được xem là một Future của test.

Nếu cần test “mỗi 5 phút quét đơn hàng”:

1. Tách **logic quét** thành một service có thể gọi trực tiếp và test bằng dữ liệu/Clock giả.
2. Dùng một scheduler adapter `@Scheduled` để kích hoạt service đó.
3. Integration test chỉ chứng minh adapter thực sự được Spring gọi khi cấu hình test có delay nhỏ.
4. Đừng assert tổng số lần chạy **đúng tuyệt đối** sau `Thread.sleep(5_000)`; assert một invariant như “đã tick thêm ít nhất một lần”.
5. Nếu cần mô phỏng calendar cron và DST, test hàm tính next-fire-time với explicit ZoneId và clock/time API phù hợp thay vì chờ ngoài đời thật.

Một scheduled method tự gọi một `@Async` worker có thể hoàn tất callback `@Scheduled` **ngay khi enqueue**, không phải khi job được xử lý. Vì vậy `fixedDelay` của scheduler adapter không mặc nhiên đợi async worker. Business test phải await **job completion** riêng.

## 23. Timeouts ở nhiều tầng và false-positive tests

Có nhiều loại timeout dễ bị trộn:

| Timeout | Mục đích | Tầng |
| --- | --- | --- |
| Awaitility `atMost` | Ngăn test chờ điều kiện vô hạn | Assertion/test |
| `Future.get(timeout)` | Ngăn chờ một Future vô hạn | Java concurrency |
| JUnit `@Timeout` | Giới hạn runtime của cả test method | Test runner |
| HTTP client connect/read timeout | Giới hạn network I/O | Client |
| DB query/transaction timeout | Giới hạn SQL/transaction | Database |
| Broker consumer poll/ack timeout | Giới hạn delivery/liveness | Messaging |
| CI job timeout | Giới hạn pipeline tổng | Hạ tầng |

Một test có `await().atMost(5s)` nhưng worker HTTP call timeout 60s vẫn có thể để lại background task đang chạy sau khi assertion timeout. Thiết kế cần **cancellation, bounded I/O** và cleanup, không chỉ tăng timeouts.

### Không dùng preemptive timeout tùy tiện với Spring @Transactional

Một số cơ chế JUnit timeout có thể chạy phần test body trên **thread khác** (ví dụ `assertTimeoutPreemptively`). Spring TestContext test-managed transaction gắn với thread nên thao tác DB ở thread mới có thể **không** nằm trong transaction rollback của test. Điều này đặc biệt quan trọng với async tests: consumer, `@Async`, HTTP server và scheduled tasks thường vốn đã ở thread/transaction khác. Không kỳ vọng `@Transactional` trên test rollback tất cả DB writes từ background thread.

### Test không cần luôn chờ 5 giây

Một `atMost(5s)` không khiến mỗi test tốn 5 giây. Nếu state đã SUCCEEDED trước lần poll đầu tiên, Awaitility có thể hoàn thành ở lần quan sát đầu. Đây chính là lý do condition-based waiting thường vừa **nhanh hơn**, vừa **ít flaky hơn** ngủ cố định.

## 24. Khi test database, HTTP và message broker: chờ business effect

Trong ứng dụng phân tán, tín hiệu cần chờ phải tương ứng với pipeline:

### Database worker

~~~java
await().atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertThat(repository.findByCorrelationId(correlationId))
            .hasValueSatisfying(row ->
                assertThat(row.getStatus()).isEqualTo("COMPLETED")
            )
    );
~~~

Đây là snippet minh họa, chưa có repository/entity definitions. Không poll một EntityManager cache cũ và kết luận DB chưa commit; dùng transaction/connection mới hoặc refresh nếu persistence context giữ state stale.

### HTTP 202 Accepted

~~~text
POST /jobs -> 202 Accepted + Location: /jobs/<id>
GET /jobs/<id> -> QUEUED
GET /jobs/<id> -> RUNNING
GET /jobs/<id> -> SUCCEEDED
~~~

Test nên poll `GET /jobs/{id}` bằng client phù hợp tới khi trạng thái terminal, giới hạn deadline và kiểm tra response body/side effects. Không chờ `Thread.sleep(1_000)` sau POST rồi assume job xong.

### Kafka / RabbitMQ

~~~text
Producer sends E -> broker ack
Consumer receives E -> DB transaction/ledger commit
Test awaits ledger/status/callback observer
~~~

`KafkaTemplate.send(...).get()` chỉ xác nhận delivery phía producer theo cấu hình, **không chứng minh consumer đã hoàn tất**. Với test có hai duplicate deliveries, phải đợi **đủ số lần consumer xử lý** hoặc kiểm tra marker/business state có ý nghĩa; một lần update đầu tiên không chứng minh lần thứ hai không tạo side effect.

### MockMvc async dispatch

Với controller Spring MVC trả `Callable`, `DeferredResult` hoặc một async return type được hỗ trợ, test có thể dùng:

~~~java
MvcResult pending = mockMvc.perform(get("/async/report"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(pending))
        .andExpect(status().isOk());
~~~

Đây là snippet minh họa **chỉ cho MVC async controller** có mapping và imports phù hợp; không thuộc ứng dụng console runnable của bài này. `asyncDispatch` là cách Spring MVC test mô phỏng dispatch hoàn tất, không yêu cầu `Thread.sleep` để đợi request. Không dùng `asyncStarted()` cho controller đồng bộ vì nó sẽ FAIL đúng.

## 25. Unit test với virtual time: khi không nên poll đồng hồ thật

Một số logic thực sự dựa vào **thời gian trôi qua**, ví dụ Reactor `Flux.interval`, debounce, retry/backoff hoặc timeout. Chờ thực 30 phút bằng Awaitility là sai công cụ. Nên **ảo hóa nguồn thời gian** khi framework hỗ trợ.

Reactor `StepVerifier.withVirtualTime` là một lựa chọn (cần dependency `io.projectreactor:reactor-test` trong test và Reactor trong app):

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofMinutes(30)).take(2)
)
.expectSubscription()
.thenAwait(Duration.ofMinutes(30))
.expectNext(0L)
.thenAwait(Duration.ofMinutes(30))
.expectNext(1L)
.verifyComplete();
~~~

Đây là snippet **tùy chọn, không thuộc sample Gradle runnable**; cần imports Reactor `Flux`, `StepVerifier` và test dependencies tương ứng. `withVirtualTime` phải nhận **supplier tạo publisher sau khi virtual scheduler được cài**, không tạo một Flux có scheduler thật trước đó rồi hy vọng time đã ảo hóa.

**Clock.fixed ≠ Reactor VirtualTimeScheduler ≠ Spring TaskScheduler.** Mỗi cơ chế điều khiển đồng hồ/scheduler của hệ mình. Nếu code gọi `System.currentTimeMillis` trực tiếp, virtual time của Reactor không tự điều khiển nó. Nếu code đọc thời điểm từ DB server, Clock injection của JVM cũng không điều khiển DB clock.

## 26. Chạy test song song: tài nguyên chia sẻ và dữ liệu kiểm thử

Async tests đặc biệt nhạy với context cache và singleton state:

- Một `@SpringBootTest` context có thể được **cache qua nhiều test classes**; bean `JobStore` singleton giữ state nếu không cleanup.
- Hai tests dùng cùng job ID sẽ tranh chấp map/DB row, dù mỗi test có Awaitility deadline riêng.
- Test A gọi `@AfterEach` cleanup rồi task của A mới hoàn tất có thể cập nhật/xuất hiện lại row và làm bẩn test B.
- Một test thay executor properties hoặc `@DirtiesContext` có thể ảnh hưởng context lifecycle; không đóng executor shared bean giữa methods.
- `@Scheduled` vẫn có thể chạy khi JUnit đã chuyển sang method tiếp theo; scheduler test phải có data isolation hoặc context/bean lifecycle đúng.
- Shared `CountDownLatch`/`AtomicBoolean` trong static fields giữa tests có thể làm tình huống phụ thuộc test order.
- Khi dùng CI shards/multiple JVMs, `@ResourceLock` trong JUnit chỉ điều phối trong JVM/engine tương ứng, không bảo vệ shared DB/broker xuyên process.
- Background task có thể chạy trên thread khác nên MDC, locale, security context, transaction không tự propagate theo cách người viết test mong đợi.

Giải pháp trong demo: **UUID riêng mỗi job**, immutable snapshots, thread-safe map, `Future.get(timeout)` trong cleanup, và scheduler-specific context được đóng sau class. Không dùng `@DirtiesContext` cho tất cả async tests vì có chi phí context startup; chỉ dùng nơi cần lifecycle cách ly.

### Tách nguồn chờ và nguồn gây thay đổi

Nếu điều kiện Awaitility tự gọi method tạo side effect mỗi lần poll:

~~~java
await().until(() -> paymentClient.charge(orderId).isSuccess());
~~~

đây là **nguy hiểm**: mỗi poll có thể **charge lần nữa**. Đúng là khởi động effect **một lần**, rồi poll một endpoint/ledger **read-only** hoặc await callback/future tương ứng. Trong messaging/reties, phải dùng idempotency key ổn định và giới hạn attempt theo nghiệp vụ.

## 27. Những lỗi thường gặp và cách sửa

| Sai lầm | Triệu chứng | Cách sửa |
| --- | --- | --- |
| `Thread.sleep(1000)` rồi assert | CI lúc PASS lúc FAIL; tốn thời gian | `await().untilAsserted` + deadline |
| Tăng sleep lên 10s “cho chắc” | Suite chậm nhưng vẫn flaky khi task kẹt | Chờ đúng state hoặc Future |
| Chỉ assert Future được tạo | Test PASS trước khi task chạy | Await Future completion/business effect |
| Await `status != QUEUED` | FAILED cũng làm điều kiện đúng | Await `SUCCEEDED`, xử lý FAILED riêng |
| Poll một queue bằng `poll()` trong predicate | Test tiêu thụ messages | Poll read-only hoặc nhận message một lần |
| Poll `HashMap`/boolean thường từ thread khác | Stale state / data race | ConcurrentHashMap, Atomic*, latch |
| `@Async` self-invocation | Task chạy đồng bộ dù annotation có mặt | Tách bean, gọi qua Spring proxy |
| Quên `@EnableAsync` | `@Async` không được áp dụng | Enable async configuration |
| Worker lỗi nhưng `@Async void` không được assert | Test chỉ timeout vô nghĩa | CompletableFuture/error channel |
| `Future.get()` không timeout | CI treo vô hạn | `get(timeout, unit)` |
| `@Scheduled` test assert tick đúng sau 120ms | Lệch CPU/GC/context startup | Baseline count + await tăng |
| Dùng `Clock.offset` để kích Spring scheduler | Scheduler không tự chạy theo clock giả | Scheduler test riêng hoặc virtual scheduler đúng |
| Test body `@Transactional`, async DB write | Row không rollback cùng test thread | DB cleanup/tx scope rõ |
| Awaitility ignore mọi exception | Nuốt lỗi schema/connection thật | Chỉ ignore exception tạm thời đã định danh |
| Gọi task mỗi lần Awaitility poll | Tạo duplicate business effects | Submit một lần, chỉ quan sát trong poll |
| Dùng `@DirtiesContext` mọi test | Context churn, test suite chậm | Isolation tài nguyên hợp lý |
| Test chỉ assert producer ack | Consumer chưa xử lý | Await consumer-side DB/status |
| Timeout quá ngắn trên shared CI | Flaky khi load tăng | Sizing deadline theo môi trường, poll hợp lý |
| Timeout quá lớn che deadlock | Chờ lâu không có thông tin | Fail-fast/lỗi worker/metrics, bounded I/O |
| `@AfterEach` xóa fixture khi worker chưa xong | Worker tạo lại data sau cleanup | Join/cancel tasks trước cleanup |
| Reactive `StepVerifier` dùng publisher tạo trước virtual scheduler | Time thật vẫn trôi | Tạo publisher trong supplier |
| `Mockito.verify(timeout(...))` làm bằng chứng DB commit | Chỉ verify invocation | Assert committed DB state |
| Test nhiều tasks đọc một shared mutable counter không atomic | Lost updates | AtomicLong/DB atomic update |
| Đợi callback chạy xong nhưng outbox relay chưa xong | Side effect khác chưa hoàn tất | Await đúng authoritative boundary |

## 28. Checklist QA trước khi chốt một async/scheduler test

- [ ] Đề bài đã xác định **business completion condition** thay vì delay phỏng đoán?
- [ ] Task được trigger **một lần**, predicate dùng để poll là read-only?
- [ ] Có timeout hữu hạn như `atMost` hoặc `get(timeout)`?
- [ ] Poll interval hợp lý với CI, không hammer database/service?
- [ ] State được publish thread-safe (`Atomic*`, `ConcurrentHashMap`, DB commit)?
- [ ] Assertion kiểm **SUCCEEDED + payload** thay vì chỉ status khác QUEUED?
- [ ] FAILED/exception worker được kiểm tra hoặc báo lỗi sớm?
- [ ] Có phân biệt producer ack / request accepted với consumer business effect?
- [ ] Với `@Async`, method được gọi qua Spring bean proxy và `@EnableAsync`?
- [ ] Executor được cấu hình/định danh đúng, không reject âm thầm?
- [ ] Có Future handle/observer khi cần debug uncaught errors?
- [ ] Với `@Scheduled`, test không assume callback chạy chính xác sau một số milliseconds?
- [ ] Clock/virtual time chỉ được dùng cho subsystem thực sự hỗ trợ?
- [ ] Nếu cần tái hiện concurrency race, dùng latch/barrier thay sleep?
- [ ] Test cleanup await/cancel background jobs trước khi xóa fixtures?
- [ ] Không có singleton test state dùng chung IDs hoặc mutable latches?
- [ ] Nếu DB writes ở worker thread, không dựa vào test transaction rollback?
- [ ] Nếu HTTP/messaging, await final persisted state chứ không chỉ call invocation?
- [ ] Không nuốt exception bằng ignore-all hoặc catch rồi return success?
- [ ] Không biến timeout thành phép kiểm performance tuyệt đối?
- [ ] Có mô tả expected và nói rõ việc code đã thực thi hay mới được review?

## 29. Lệnh chạy, expected và giới hạn của ví dụ

Từ thư mục có Gradle Wrapper và JDK 17+:

~~~bash
./gradlew test --tests "com.example.conditionwait.AsyncJobIntegrationTest"
./gradlew test --tests "com.example.conditionwait.ScheduledTickIntegrationTest"
./gradlew test --tests "com.example.conditionwait.GateWithoutSleepTest"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.conditionwait.AsyncJobIntegrationTest"
.\gradlew.bat test --tests "com.example.conditionwait.ScheduledTickIntegrationTest"
.\gradlew.bat test --tests "com.example.conditionwait.GateWithoutSleepTest"
~~~

Có **8 JUnit test methods**: 4 `AsyncJobIntegrationTest`, 2 `ScheduledTickIntegrationTest` và 2 `GateWithoutSleepTest`.

Kỳ vọng chính:

~~~text
Async input "hello" -> status=SUCCEEDED, result="HELLO"
Async input "FAIL"  -> status=FAILED, Future có IllegalStateException
Hai jobs alpha/beta -> results "ALPHA" và "BETA"
Trùng job ID        -> IllegalArgumentException, job gốc không đổi
Scheduler tick      -> counter tăng so với baseline trong deadline
CountDownLatch      -> hoàn tất sau release, không sleep
CompletableFuture   -> "ready" được transform thành "READY"
~~~

Đây là **kết quả kỳ vọng theo logic mã nguồn**, không phải output Gradle/JUnit đã quan sát. Mã không có `System.out.println`; test logs tùy runtime. **Chưa compile/run Gradle trong lúc biên soạn**, nên cần môi trường JDK 17, Gradle Wrapper và dependencies đầy đủ để xác nhận thực tế.

**Kết luận:** Đừng dùng `Thread.sleep` như phép đồng bộ. Hãy **kích hoạt tác vụ một lần**, chọn trạng thái/signal có nghĩa nghiệp vụ, **chờ điều kiện với timeout hữu hạn** rồi assert cả kết quả/lỗi và cleanup. Awaitility thích hợp cho eventual state; `Future.get(timeout)` cho task handle; `CountDownLatch` cho thứ tự threads; virtual time cho reactive timers. Làm đúng sẽ giúp test vừa chạy nhanh khi worker hoàn thành sớm, vừa không thất bại ngẫu nhiên vì tốc độ máy CI.

### Tài liệu chính thức và hướng dẫn API

- [Spring Framework — Task Execution and Scheduling, @Async và @Scheduled](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html)
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/)
- [Spring Boot — Test Scope Dependencies/Awaitility](https://docs.spring.io/spring-boot/3.5/reference/testing/test-scope-dependencies.html)
- [Awaitility — Usage Guide 4.x](https://github.com/awaitility/awaitility/wiki/Usage)
- [Awaitility — GitHub README](https://github.com/awaitility/awaitility)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [JUnit Jupiter — User Guide (parallel execution, timeouts)](https://docs.junit.org/current/user-guide/)
- [Reactor — Testing with StepVerifier and Virtual Time](https://projectreactor.io/docs/core/release/reference/testing.html)