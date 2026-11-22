# Đo thời gian publish và process event trong Spring Framework

## 1. Mục tiêu và bối cảnh observability

Trong Spring Framework Application Events, một service có thể gọi `ApplicationEventPublisher.publishEvent(...)` để thông báo một thay đổi nghiệp vụ. Nhiều ứng dụng chỉ đo thời gian gọi `publishEvent` và kết luận rằng **event đã được xử lý nhanh**. Kết luận này có thể đúng một phần khi toàn bộ listener chạy đồng bộ, nhưng sai rõ rệt khi sử dụng executor, `@Async`, transaction-bound listener hoặc một luồng xử lý tách rời.

Để quan sát đúng, phải định nghĩa các khoảng thời gian độc lập:

- **Publish latency:** thời gian phương thức `publishEvent(...)` mất để **bàn giao** event cho cơ chế phân phối và trả về/throw.
- **Processing latency:** thời gian **một handler cụ thể** thật sự thực hiện việc xử lý; đo ở bên trong handler.
- **Start delay:** khoảng từ lúc event được tạo/đánh dấu phát đến lúc handler bắt đầu; có thể chứa dispatch overhead và thời gian chờ executor queue.
- **End-to-end latency:** từ mốc nghiệp vụ được chọn đến khi **tất cả kết quả cần thiết** hoàn tất hoặc một kết quả cụ thể được xác nhận. Không mặc nhiên suy được từ publish timer.

Bài này giải thích các định nghĩa, đo bằng Micrometer `Timer`, phân biệt sync/async và transaction, thiết kế metric tags an toàn, viết ví dụ Java 17+ chạy được và kiểm thử để tránh đo sai.

**Quy tắc cốt lõi:** `publishEvent(...)` là **handoff** đến event multicaster; theo hợp đồng Spring, nó **không bảo đảm** đồng bộ, bất đồng bộ hoặc hoàn thành xử lý ngay tại thời điểm phương thức trả về.

## 2. Hợp đồng của ApplicationEventPublisher và nơi đo

Spring Framework có các thành phần:

- `ApplicationEventPublisher`: API phát một `ApplicationEvent` hoặc payload object thường.
- `ApplicationEventMulticaster`: quyết định phân phối event đến các `ApplicationListener` phù hợp.
- `SimpleApplicationEventMulticaster`: implementation mặc định khi context không khai báo bean multicaster riêng.
- `ApplicationListener<E>` và `@EventListener`: các cơ chế nhận event.
- `@TransactionalEventListener`: callback gắn với một phase của transaction, không nhất thiết xử lý lúc `publishEvent`.

Khi truyền một record/POJO:

~~~java
publisher.publishEvent(new OrderSubmitted("order-101", 100L));
~~~

Spring có thể bao nó thành `PayloadApplicationEvent` trước khi multicaster phân phối. Đoạn trên là **minh họa**, cần có `publisher` và record `OrderSubmitted` được định nghĩa.

Ở cấu hình **mặc định**, `SimpleApplicationEventMulticaster` thường gọi listener ngay trên thread publisher. Tuy nhiên, có thể cấu hình `setTaskExecutor(...)` hoặc dùng `@Async` để thay đổi đường thực thi. Do đó:

~~~text
Publisher                          Multicaster               Listener
    |                                  |                        |
    |------ publishEvent(event) ----->|                        |
    |                                  |---- listener() ------->|
    |                                  |<--- listener done -----|
    |<----- publishEvent returns ------|                        |

             SYNCHRONOUS: khoảng publish có thể bao gồm thời gian listener.
~~~

~~~text
Publisher                          Multicaster/Executor       Listener
    |                                  |                        |
    |------ publishEvent(event) ----->|                        |
    |                                  |-- submit task -------->|
    |<----- publishEvent returns ------|                        |
    |                                  |    queue / scheduling  |
    |                                  |---- handler starts --->|
    |                                  |<--- handler ends ------|

             ASYNCHRONOUS: khoảng publish thường chỉ đo handoff/submit.
~~~

Điểm cần quan sát: hình minh họa không phải lời hứa mọi loại listener đều sẽ chạy async khi multicaster có executor. Từ Spring 6.1, `ApplicationListener.supportsAsyncExecution()` cho phép listener từ chối async tại multicaster; ví dụ các transaction-synchronized listener cần đăng ký callback đúng thread có transaction.

## 3. Định nghĩa các mốc thời gian chính xác

Với một event và một handler, đặt:

~~~text
t0  business operation reaches chosen event-creation time
t1  just before publisher.publishEvent(event)
t2  publishEvent(event) returns or throws
t3  handler invocation begins
t4  handler finishes (success/failure)
t5  required downstream effect is durably confirmed, if applicable
~~~

Các duration thường dùng:

| Metric | Công thức | Ý nghĩa |
| --- | --- | --- |
| `publish_duration` | `t2 - t1` | Thời gian chạy lời gọi `publishEvent` |
| `start_delay` | `t3 - t0` | Từ mốc tạo event đến lúc handler bắt đầu |
| `process_duration` | `t4 - t3` | Thời gian handler chạy |
| `end_to_end_duration` | `t5 - t0` | Độ trễ kết quả nghiệp vụ được xác nhận theo hợp đồng |
| `queue_wait` | `handler_start - enqueue_time` | Chỉ đo đúng thời gian queue nếu thực sự có timestamp ở điểm enqueue |

**Không gọi `start_delay` là “queue wait chính xác”** nếu timestamp bắt đầu được lấy từ lúc tạo event. Nó còn bao gồm chuẩn bị event, dispatch overhead, scheduler handoff và các công việc khác trước khi handler bắt đầu.

Đồng thời không mặc định:

~~~text
end_to_end = publish_duration + start_delay + process_duration
~~~

Công thức này **đếm trùng** một số giai đoạn khi xử lý đồng bộ, và có thể bỏ sót tác vụ downstream bất đồng bộ. Với sync, `t3` và `t4` nằm bên trong khoảng `t1..t2`. Với async, publish và handler có thể chồng lấn một phần. Muốn `end_to_end`, cần chọn **mốc kết thúc riêng** có bằng chứng hoàn tất.

### 3.1. Đo ở đâu?

- **Publish timer:** quanh đúng lời gọi `publishEvent`, ở ranh giới publisher/gateway của ứng dụng.
- **Process timer:** quanh thân **mỗi listener hoặc bước xử lý có tên rõ**. Mỗi handler cần tag/metric nhận diện hợp lý.
- **Start delay:** đo tại đầu listener từ monotonic timestamp được tạo ở publisher, chỉ thích hợp cho event **trong cùng JVM**.
- **Result:** gắn `success`/`error` theo kết quả của handler, không lấy trạng thái `publishEvent returned` làm bằng chứng thành công async.

Nếu một event có 3 listener, một lần publish có thể tạo **1 publish measurement và 3 process measurements**. Vì thế count của hai loại timer không bắt buộc bằng nhau.

## 4. Spring event sync, async và transaction ảnh hưởng số đo thế nào?

| Cơ chế | Publish timer thực chất đo gì? | Process timer nên đặt ở đâu? | Cần lưu ý |
| --- | --- | --- | --- |
| `SimpleApplicationEventMulticaster` đồng bộ mặc định | Bàn giao + thời gian các listener được gọi trong cùng stack | Đầu/cuối từng handler | Publish timer có thể lớn do một listener chậm |
| Multicaster có `TaskExecutor` | Thường là lịch trình/submit task; có thể chứa fallback hoặc từ chối task | Trong handler thực thi trên worker | Không coi publish trả về là listener đã hoàn tất |
| `@Async` trên listener | Thường phản ánh bước gọi proxy/submit | Trong phần code async thực sự | Exception và context cần được theo dõi riêng |
| `@TransactionalEventListener(AFTER_COMMIT)` | Đăng ký callback nếu có transaction thích hợp | Trong callback chạy sau commit | Không đo được callback chỉ bằng `publishEvent` |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Đăng ký callback khi phát event | Trong callback trước commit | Callback có thể ảnh hưởng rollback; không mặc định async |
| Event reactive có `TransactionalEventPublisher` | Phát event theo subscription và Reactor Context | Trong listener đúng phase; nếu handler trả publisher cần đo đến terminal signal | Không dùng thời gian tạo Mono làm thời gian thực thi |

**Ví dụ quan trọng:** service thực hiện `publishEvent` trong transaction, listener là `AFTER_COMMIT` và gửi HTTP sau commit. Publish timer có thể chỉ vài micro/millisecond, trong khi handler tốn 500 ms sau commit. Số `publish_duration` không nói được SLA gửi HTTP.

## 5. Micrometer Timer là công cụ phù hợp

Micrometer cung cấp `Timer`, `Counter`, `DistributionSummary`, `Observation` và tích hợp với nhiều metrics registry. Đo thời lượng bằng **`Timer`** vì nó có ngữ nghĩa đơn vị thời gian và hỗ trợ count, total time, max, histogram/phân vị theo cấu hình.

Một mẫu ngắn:

~~~java
Timer publishTimer = Timer.builder("app.event.publish")
        .description("Time spent in publishEvent hand-off")
        .tag("event", "order_submitted")
        .register(registry);

publishTimer.record(() -> publisher.publishEvent(event));
~~~

Đây là **đoạn minh họa**, cần `registry`, `publisher` và `event` đã khai báo. `record(Runnable)` đo khối lệnh; khi có exception được ném ra, timer vẫn có thể ghi thời lượng nếu dùng đúng cơ chế `record`. Nếu muốn gắn tag kết quả **sau khi biết success/error**, dùng `Timer.Sample`.

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    doWork();
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    sample.stop(Timer.builder("app.event.process")
            .tag("handler", "notify_customer")
            .tag("outcome", outcome)
            .register(registry));
}
~~~

Đây cũng là **đoạn minh họa**, cần method `doWork` và `MeterRegistry`. Đặt `sample.stop(...)` trong `finally` để đo cả đường lỗi. Không catch rồi nuốt exception chỉ để có metric: điều đó sẽ thay đổi hợp đồng xử lý lỗi/rollback.

### 5.1. Count, total time và max

Một `Timer` có thể trả:

- `count()`: số measurement đã ghi trong cửa sổ/đối tượng registry tương ứng.
- `totalTime(TimeUnit.MILLISECONDS)`: tổng thời lượng đã ghi, tính theo đơn vị được yêu cầu.
- `max(TimeUnit.MILLISECONDS)`: maximum trong cửa sổ thống kê tương ứng; max có thể reset theo cấu hình time-window.

Mean đơn giản trong phạm vi thống kê là `totalTime / count` nếu `count > 0`, nhưng **mean không thay thế p95/p99**. Quan sát latency dưới tải cần histogram hoặc percentile phù hợp, và phải phân biệt metric snapshot trong local registry với số liệu đã aggregate qua hệ thống monitoring.

### 5.2. Clock cho đo duration

Với code trong cùng process, dùng `System.nanoTime()` hoặc clock đơn điệu của `Timer.Sample` để đo **độ dài khoảng thời gian**. Không dùng `Instant.now()` / `System.currentTimeMillis()` rồi khẳng định chính xác cao vì wall clock có thể bị điều chỉnh.

`System.nanoTime()` chỉ có ý nghĩa so sánh các mốc cùng một JVM runtime, **không phải timestamp để đưa qua Kafka, database hoặc máy khác**. Với event liên tiến trình, cần trace và timestamp có ngữ nghĩa khác, đồng thời tính clock skew.

## 6. Quy ước tên metric và tag để dùng lâu dài

Một bộ tên gợi ý:

| Meter name | Loại | Tag low-cardinality gợi ý | Mốc đo |
| --- | --- | --- | --- |
| `app.event.publish` | Timer | `event`, `result` | Quanh lời gọi publish |
| `app.event.process` | Timer | `event`, `handler`, `outcome` | Trong listener |
| `app.event.start.delay` | Timer | `event`, `handler` | Từ tạo event tới lúc handler bắt đầu |
| `app.event.inflight` | Gauge | `handler` | Số handler đang chạy |
| `app.event.failures` | Counter | `handler`, `error_kind` | Khi một handler thất bại |
| `app.event.executor.queue.depth` | Gauge | `executor` | Số công việc chờ trong queue thực |
| `app.event.executor.rejected` | Counter | `executor`, `reason` | Khi executor từ chối công việc |

Đây là **tên do ứng dụng đặt**, không phải metric tự động mà Spring Framework luôn xuất ra. Có thể dùng namespace được dự án thống nhất thay cho `app`; nên ổn định tên và tag qua các lần triển khai.

### Tag tuyệt đối không nên có

- `eventId`, `orderId`, `userId`, `requestId`, `traceId`.
- Raw exception message, full stacktrace, URL có query cá nhân, email, payload JSON.
- Tên class động theo dữ liệu người dùng hoặc mọi giá trị trạng thái không giới hạn.

Vì mỗi tổ hợp tag tạo một meter/time series riêng, tag có giá trị duy nhất theo từng event gây **high cardinality**, tốn memory và tăng chi phí hệ thống metrics. Dùng `event="order_submitted"`, `handler="billing"`, `outcome="success|error"` và bộ `error_kind` hữu hạn thay cho ID cụ thể.

**Phân biệt roles:** metric tags dùng để tổng hợp; trace/span attributes có thể chứa correlation ID theo chính sách bảo mật và sampling phù hợp. Không biến metrics thành nơi lưu log chi tiết từng event.

## 7. Ví dụ chạy được với Java 17+, Spring Framework và Micrometer

Ví dụ xây một Spring application context thuần và cấu hình `SimpleApplicationEventMulticaster` dùng **một worker thread**. Chương trình phát ba event, đo thời gian `publishEvent`, thời gian handler và khoảng từ tạo event đến khi handler bắt đầu. Nó dùng `CountDownLatch` thay cho `Thread.sleep` để chờ xử lý xong, rồi in **số lượng measurement** (ổn định), không in duration thực tế (phụ thuộc máy).

Mục tiêu: minh họa chính xác vì sao **publish returned** không đủ để kết luận **process done** khi listener chạy async.

### 7.1. Cấu trúc

~~~text
event-timing-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── EventTimingDemo.java
    └── test/
        └── java/
            └── demo/
                └── EventTimingDemoTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'event-timing-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
    implementation 'io.micrometer:micrometer-core:1.14.14'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.EventTimingDemo'
}

test {
    useJUnitPlatform()
}
~~~

Các phiên bản Spring 6.2.15 và Micrometer 1.14.14 đều là artifact đã phát hành; Spring Context 6.2.15 phụ thuộc `micrometer-observation` 1.14.14. Dùng cùng nhánh Micrometer giúp tránh lệch dependency. Nếu làm với Spring Boot, ưu tiên Boot BOM thay vì ghim rời các phiên bản này.

### 7.2. Mã nguồn hoàn chỉnh

Tạo `src/main/java/demo/EventTimingDemo.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

public class EventTimingDemo {

    // createdAtNanos chỉ dùng để đo duration trong cùng JVM.
    public record OrderSubmitted(
            String orderId,
            long amountCents,
            long createdAtNanos) {}

    // Đo chính xác thời lượng lời gọi publishEvent(...).
    public static final class MeasuredPublisher {
        private final ApplicationEventPublisher publisher;
        private final MeterRegistry registry;

        public MeasuredPublisher(
                ApplicationEventPublisher publisher,
                MeterRegistry registry) {
            this.publisher = publisher;
            this.registry = registry;
        }

        public void submit(String id, long amountCents) {
            OrderSubmitted event =
                    new OrderSubmitted(id, amountCents, System.nanoTime());

            Timer.Sample sample = Timer.start(registry);
            String result = "returned";

            try {
                publisher.publishEvent(event);
            } catch (RuntimeException ex) {
                result = "exception";
                throw ex;
            } finally {
                sample.stop(Timer.builder("demo.event.publish")
                        .tag("event", "order_submitted")
                        .tag("result", result)
                        .register(registry));
            }
        }
    }

    // Listener thực thi trên event executor.
    public static final class AccountingListener {
        private final MeterRegistry registry;
        private final CountDownLatch finished;
        private final AtomicLong totalCents = new AtomicLong();

        public AccountingListener(
                MeterRegistry registry,
                CountDownLatch finished) {
            this.registry = registry;
            this.finished = finished;
        }

        @EventListener
        public void onOrderSubmitted(OrderSubmitted event) {
            long elapsedNanos =
                    System.nanoTime() - event.createdAtNanos();

            Timer.builder("demo.event.start.delay")
                    .tag("event", "order_submitted")
                    .tag("handler", "accounting")
                    .register(registry)
                    .record(Math.max(0L, elapsedNanos),
                            TimeUnit.NANOSECONDS);

            Timer.Sample processing = Timer.start(registry);
            String outcome = "success";

            try {
                // Tượng trưng cho phần xử lý nghiệp vụ.
                totalCents.addAndGet(event.amountCents());
            } catch (RuntimeException ex) {
                outcome = "error";
                throw ex;
            } finally {
                processing.stop(Timer.builder("demo.event.process")
                        .tag("event", "order_submitted")
                        .tag("handler", "accounting")
                        .tag("outcome", outcome)
                        .register(registry));
                finished.countDown();
            }
        }

        public long totalCents() {
            return totalCents.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public MeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean(destroyMethod = "shutdown")
        public ExecutorService eventExecutor() {
            return Executors.newSingleThreadExecutor();
        }

        // Đây là tên bean mà Spring ApplicationContext tìm.
        @Bean(name = "applicationEventMulticaster")
        public ApplicationEventMulticaster applicationEventMulticaster(
                ExecutorService eventExecutor) {
            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();

            multicaster.setTaskExecutor(eventExecutor);
            return multicaster;
        }

        @Bean
        public CountDownLatch finished() {
            return new CountDownLatch(3);
        }

        @Bean
        public AccountingListener accountingListener(
                MeterRegistry registry,
                CountDownLatch finished) {
            return new AccountingListener(registry, finished);
        }

        @Bean
        public MeasuredPublisher measuredPublisher(
                ApplicationEventPublisher publisher,
                MeterRegistry registry) {
            return new MeasuredPublisher(publisher, registry);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            MeasuredPublisher measuredPublisher =
                    context.getBean(MeasuredPublisher.class);
            MeterRegistry registry = context.getBean(MeterRegistry.class);
            CountDownLatch finished = context.getBean(CountDownLatch.class);
            AccountingListener accounting =
                    context.getBean(AccountingListener.class);

            measuredPublisher.submit("A", 100L);
            measuredPublisher.submit("B", 200L);
            measuredPublisher.submit("C", 300L);

            if (!finished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for 3 event handlers");
            }

            System.out.println("publish.count=" +
                    registry.get("demo.event.publish")
                            .tag("result", "returned").timer().count());

            System.out.println("process.count=" +
                    registry.get("demo.event.process")
                            .tag("outcome", "success").timer().count());

            System.out.println("start.delay.count=" +
                    registry.get("demo.event.start.delay").timer().count());

            System.out.println("total.cents=" + accounting.totalCents());
        }
    }
}
~~~

**Vì sao code chạy theo thiết kế này:**

1. `MeasuredPublisher.submit(...)` tạo record trước, sau đó lấy `Timer.Sample` **ngay trước** `publisher.publishEvent(event)`. Nó ghi `result=returned` nếu lời gọi trả về mà không ném exception, **không đặt `result=processed`**.
2. `SimpleApplicationEventMulticaster` có bean name `applicationEventMulticaster` và sử dụng `ExecutorService`. Với listener `@EventListener` thông thường, công việc được đưa sang worker.
3. `AccountingListener` nhận event và dùng timestamp `createdAtNanos` để đo **start delay**, rồi dùng `Timer.Sample` riêng cho **process duration**. Hai khoảng có ngữ nghĩa khác nhau.
4. `finished.countDown()` trong `finally` bảo đảm tín hiệu hoàn tất của ba lời gọi handler được phát kể cả khi logic ném runtime exception. Việc đếm xuống không có nghĩa side effect đã thành công; đó là tín hiệu “handler đã kết thúc phần thân”.
5. `CountDownLatch.await(...)` đặt timeout thực sự, không đoán rằng 100 ms đủ để mọi callback chạy xong.
6. `AtomicLong` đảm bảo cộng dồn an toàn nếu sau này executor được mở rộng thành nhiều worker. `CountDownLatch` giúp thread main có quan hệ happens-before với việc handler đã thực hiện trước đó.
7. `SimpleMeterRegistry` lưu metric trong memory phục vụ demo; nó **không tự xuất metric ra Prometheus**. Muốn xuất metric từ ứng dụng thật phải cài registry/exporter phù hợp.

### 7.3. Chạy và dự đoán kết quả

Trong thư mục `event-timing-demo`, với JDK 17+ và Gradle:

~~~bash
gradle -q run
~~~

Hoặc dùng Gradle Wrapper nếu đã cấu hình: `./gradlew -q run` (Linux/macOS) hay `gradlew.bat -q run` (Windows).

Các dòng do chương trình chủ động in ra, khi cả ba handler hoàn tất thành công:

~~~text
publish.count=3
process.count=3
start.delay.count=3
total.cents=600
~~~

Đây là **kết quả logic dự kiến**, không phải log của một lần build đã thực thi trong môi trường này. Gradle hoặc logging thư viện có thể thêm thông tin khác.

**Không in duration cố định** vì thời gian nanosecond/millisecond phụ thuộc CPU, scheduler, JVM warmup và tải hệ thống. Kết quả đếm và tổng số cents mới là các giá trị xác định từ demo.

Tại đây, `publish.count=3` và `process.count=3` chỉ bằng nhau vì mỗi event của demo có **đúng một handler** và main chờ đủ ba lần callback. Điều đó không phải quy tắc tổng quát của Spring Application Events.

## 8. Kiểm thử instrumentation bằng JUnit 5

Ví dụ test dưới đây cùng sử dụng Spring context thực, phát đúng ba event, chờ handler hoàn tất và kiểm tra các timer. Nó **không kiểm tra một ngưỡng thời gian tuyệt đối**, vì unit/integration test latency dùng clock hệ thống rất dễ flaky.

Tạo `src/test/java/demo/EventTimingDemoTest.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EventTimingDemoTest {

    @Test
    @Timeout(15)
    void publishAndProcessAreMeasuredSeparately() throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             EventTimingDemo.Config.class)) {

            EventTimingDemo.MeasuredPublisher publisher =
                    context.getBean(EventTimingDemo.MeasuredPublisher.class);
            EventTimingDemo.AccountingListener listener =
                    context.getBean(EventTimingDemo.AccountingListener.class);
            MeterRegistry registry = context.getBean(MeterRegistry.class);
            CountDownLatch finished = context.getBean(CountDownLatch.class);

            publisher.submit("A", 100L);
            publisher.submit("B", 200L);
            publisher.submit("C", 300L);

            assertTrue(finished.await(10, TimeUnit.SECONDS));

            assertEquals(3L,
                    registry.get("demo.event.publish")
                            .tag("result", "returned").timer().count());
            assertEquals(3L,
                    registry.get("demo.event.process")
                            .tag("outcome", "success").timer().count());
            assertEquals(3L,
                    registry.get("demo.event.start.delay").timer().count());
            assertEquals(600L, listener.totalCents());
        }
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Đây là **integration-style unit test** có context và executor thật, không cần web server hay database. Nó xác minh rằng instrumentation được kích hoạt đúng vị trí và không đọc metric trước khi listener kết thúc.

Nếu dùng thêm test giả lập lỗi, kiểm tra timer `outcome=error` và exception path riêng. Khi async, exception handler có thể xảy ra ở worker thread thay vì quay về publisher; test phải có cơ chế quan sát lỗi trong listener/worker, không chỉ `assertThrows(() -> publishEvent(...))`.

## 9. Chuyển ví dụ sang synchronous mode để so sánh

Chỉ thay cấu hình multicaster: bỏ `setTaskExecutor(eventExecutor)` (hoặc không khai báo custom multicaster). Khi đó `SimpleApplicationEventMulticaster` mặc định gọi listener phù hợp đồng bộ:

~~~java
@Bean(name = "applicationEventMulticaster")
public ApplicationEventMulticaster applicationEventMulticaster() {
    return new SimpleApplicationEventMulticaster();
}
~~~

Đây là **biến thể của bean cấu hình**, không dùng đồng thời với bean `applicationEventMulticaster` ở ví dụ chính. Trong cùng một context chỉ nên có một bean với đúng tên ấy.

Nếu listener là đồng bộ:

~~~text
t1 start publish
   |
   +-- t3 handler starts
   |       |
   |       +-- processing
   |       |
   |   t4 handler ends
   |
t2 publish returns
~~~

Khi ấy `publish_duration` có thể lớn hơn `process_duration` vì nó bao gồm chi phí multicaster và có thể có nhiều handler. Không được suy ra “publisher chậm” nghĩa là chính phương thức `publishEvent` có logic nặng độc lập với listener: **một handler đồng bộ chậm sẽ làm chậm publisher**.

Nếu có **nhiều listener**, publisher có thể đo tổng duration của nhiều callback đồng bộ. Một timer `process` cho handler A không thể đại diện thời gian handler B.

## 10. Đo đa listener: metric cardinality và lựa chọn điểm bắt

Trong ứng dụng thật, một `OrderSubmitted` có thể kích hoạt:

~~~text
OrderSubmitted
  |
  +--> InventoryListener
  +--> BillingListener
  +--> NotificationListener
  +--> AnalyticsListener
~~~

Nếu cần biết listener nào chậm, phải đo **từng handler**:

~~~java
@EventListener
public void onOrderSubmitted(OrderSubmitted event) {
    Timer.Sample sample = Timer.start(registry);
    String outcome = "success";

    try {
        handleInventory(event);
    } catch (RuntimeException ex) {
        outcome = "error";
        throw ex;
    } finally {
        sample.stop(registry.timer(
                "app.event.process",
                "event", "order_submitted",
                "handler", "inventory",
                "outcome", outcome));
    }
}
~~~

Đây là **đoạn minh họa** cần `registry` và `handleInventory`; không thuộc class demo ở mục 7. Đặt tag `handler` cố định theo logical name, không sử dụng tên object proxy động hoặc ID của bean instance.

Có thể viết wrapper/decorator để giảm lặp logic, nhưng cần đảm bảo instrument **đúng thời gian phần xử lý**. Nếu decorator chỉ bao một method trả `CompletableFuture` hoặc `Mono`, timer có thể dừng ngay khi future/publisher được tạo, không đo tới khi công việc hoàn tất.

### Timer count khác số lượng event

Với 1 event và 4 listeners:

- `app.event.publish{event="order_submitted"}` có thể `count=1`.
- `app.event.process{handler="inventory"}` có `count=1`.
- `app.event.process{handler="billing"}` có `count=1`.
- Tổng count trên **tất cả handler** có thể bằng 4 nếu cả bốn xử lý, nhưng có thể nhỏ hơn khi listener bị lọc, skip, không được đăng ký hoặc chưa hoàn tất.

Khi làm dashboard, không lấy tổng `process.count` chia trực tiếp cho `publish.count` rồi mặc định đó là delivery success rate. Phải định nghĩa thành công theo handler và expected subscribers.

## 11. Đo lỗi: lỗi publish khác lỗi xử lý

Publisher có thể ném exception trong đồng bộ hoặc ngay khi multicaster/executor gặp lỗi, nhưng trường hợp async:

~~~text
publishEvent returned normally
               |
               v
task runs later -> handler throws exception
~~~

Khi đó `publish.result=returned` vẫn hợp lệ, dù `process.outcome=error`. Đây là hai metric đúng nhưng phản ánh hai ranh giới khác nhau.

Một mẫu xử lý trong listener:

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    processBusinessEvent(event);
} catch (ExpectedTemporaryException ex) {
    outcome = "error";
    registry.counter(
            "app.event.failures",
            "handler", "notification",
            "error_kind", "temporary").increment();
    throw ex;
} catch (RuntimeException ex) {
    outcome = "error";
    registry.counter(
            "app.event.failures",
            "handler", "notification",
            "error_kind", "runtime").increment();
    throw ex;
} finally {
    sample.stop(registry.timer(
            "app.event.process",
            "event", "order_submitted",
            "handler", "notification",
            "outcome", outcome));
}
~~~

**Đoạn này chỉ là minh họa**: `processBusinessEvent`, `ExpectedTemporaryException`, `event` và `registry` cần được định nghĩa trong ứng dụng. Không đổi nghiệp vụ bằng cách nuốt lỗi; ngoại lệ được ném lại như cũ.

Với mỗi handler, nên thống nhất một nơi đo lỗi; nếu đã dùng `Timer` có `outcome=error` thì có thể suy ra error count từ timer và không cần tạo Counter riêng chỉ để đếm trùng. Dùng counter riêng khi thật sự cần một phân loại lỗi bổ sung hoặc tần suất phát hiện khác với duration.

**Không đưa exception message vào tag**. Dùng một tập giá trị hữu hạn như `timeout`, `validation`, `dependency_unavailable`, `unknown`. Exception detail và event ID nên ở structured log/trace, có redaction và hạn chế quyền truy cập.

## 12. Transaction-bound event: đo đúng lúc callback chạy

Một listener:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderSubmitted event) {
    sendNotification(event);
}
~~~

Đây là method minh họa, chưa phải file hoàn chỉnh; cần bean Spring, import transaction annotation, event class và implementation gửi thông báo.

Nếu `publishEvent` được gọi bên trong `@Transactional`, listener có thể chỉ **đăng ký synchronization** khi publish; phần xử lý sẽ xảy ra **sau commit**. Vì vậy:

- Publish timer: đo lời gọi tại transaction service, không đo thời gian chờ commit.
- Process timer: đo trong `afterCommit(...)` khi callback thực sự chạy.
- Start delay: từ thời điểm event hình thành tới lúc callback chạy, **có thể bao gồm thời gian transaction chưa commit**, không đơn thuần là executor queue.
- End-to-end: phải định nghĩa sau commit + side effect có xác nhận hay không.

Nếu transaction rollback, một listener `AFTER_COMMIT` sẽ **không chạy**. Khi `fallbackExecution=false` mặc định và không có transaction, listener cũng bị bỏ qua. Vì thế `process.count < publish.count` **không tự động** là lỗi delivery trong trường hợp này.

Có thể đo thêm:

- `transaction.duration` nếu có instrumentation thích hợp ở service/transaction boundary.
- `event.pending.commit.duration` nếu lưu timestamp từ lúc event xảy ra đến lúc AFTER_COMMIT callback bắt đầu.
- `event.process.duration` cho handler thật.
- `event.outcome` với nhãn commit/rollback nếu business có yêu cầu quan sát outcome, không suy đoán từ publish count.

**Lưu ý:** Ghi DB trong `AFTER_COMMIT` không mặc nhiên tạo transaction mới có commit độc lập. Nếu cần ghi thêm dữ liệu, hãy xác định transaction mới; instrumentation không làm thay đổi semantics của transaction.

## 13. Phân biệt @Async, executor queue và context propagation

### 13.1. Đo queue wait đúng nghĩa

Nếu muốn có **queue wait** thuần túy, cần instrument ngay tại lớp executor khi task được enqueue và tại lúc task bắt đầu chạy:

~~~text
enqueue_time = clock.monotonicTime() ngay trước/sau queue offer theo hợp đồng
start_time   = clock.monotonicTime() ngay lúc worker bắt đầu task
queue_wait   = start_time - enqueue_time
~~~

Không đánh đồng thời gian từ tạo event đến handler với queue wait. Một executor chạy task bằng `CallerRunsPolicy` có thể thực thi ngay trên thread publisher; lúc đó publish timer **bao gồm handler**, mặc dù cấu hình được gọi là async. Bằng chứng phải đến từ cách executor thực sự chạy.

### 13.2. Quan sát backlog và thread pool

Đối với `ThreadPoolTaskExecutor` hoặc `ThreadPoolExecutor` phù hợp, thu thập:

- Active workers, pool size và maximum size.
- Queue depth, queue capacity, task submission/rejection.
- Completed task count và long-running task.
- Event handler p95/p99 duration so với producer rate.

Nếu producer gửi 1.000 event/s nhưng worker chỉ xử lý 600 event/s, độ trễ queue tăng theo thời gian dù `publish_duration` thấp. Đây là lý do phải quan sát **throughput + backlog + start delay**, không chỉ publish latency.

### 13.3. Tracing và MDC khi chuyển thread

Trong synchronous path, logging context/ThreadLocal của publisher thường tiếp tục có mặt khi listener chạy cùng thread. Khi multicaster chọn executor khác hoặc `@Async`, context không tự động chuyển sang worker thread. Nếu cần trace correlation, dùng cơ chế **Micrometer Context Propagation** và task decorator phù hợp, chẳng hạn `ContextPropagatingTaskDecorator` trên `TaskExecutor`.

Cấu hình minh họa với Spring Framework 6.2:

~~~java
@Bean(name = "applicationEventMulticaster")
public SimpleApplicationEventMulticaster eventMulticaster() {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();

    SimpleAsyncTaskExecutor executor = new SimpleAsyncTaskExecutor();
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());

    multicaster.setTaskExecutor(executor);
    return multicaster;
}
~~~

Đây là **cấu hình thay thế**, cần imports từ Spring, `io.micrometer:context-propagation` trên classpath và chính sách quản lý executor. Không sử dụng đồng thời với multicaster của demo. Decorator giúp truyền context hỗ trợ; nó **không biến Java ThreadLocal transaction thành transaction hợp lệ ở worker**. Dữ liệu cần thiết cho xử lý vẫn phải có contract rõ ràng.

## 14. Micrometer Observation và Spring Boot Actuator

Micrometer có API `ObservationRegistry` cho việc mô tả hoạt động quan sát được, kết hợp metrics và tracing khi có handler/registry phù hợp. Tuy nhiên, **Spring Framework không tự tạo Observation cho mọi lời gọi `@EventListener`**; tài liệu Spring nêu rõ vì ngữ nghĩa phân phối sync/async, framework không tự áp một model instrumentation duy nhất.

Nếu cần Observation cho một handler cụ thể, có thể bao công việc **thật**:

~~~java
Observation.createNotStarted("app.event.process", observationRegistry)
        .lowCardinalityKeyValue("event", "order_submitted")
        .lowCardinalityKeyValue("handler", "notification")
        .observe(() -> handle(event));
~~~

Đây là đoạn minh họa: cần `Observation`, `ObservationRegistry` và `handle` trong context; tùy setup, cần handlers để sinh metric/span. **Không cho rằng chỉ khai báo `@EventListener` hoặc `@Timed` là tự có dashboard** nếu chưa cấu hình instrumentation/AOP tương ứng.

Với Spring Boot Actuator, nếu dự án đã có `spring-boot-starter-actuator` và registry exporter như `micrometer-registry-prometheus`, có thể cấu hình công bố metric theo policy bảo mật. Ví dụ cấu hình tham khảo:

~~~properties
management.endpoints.web.exposure.include=health,info,prometheus
management.metrics.distribution.percentiles-histogram.app.event.process=true
management.metrics.distribution.percentiles-histogram.app.event.publish=true
~~~

Đây là **cấu hình tham khảo**, cần Actuator, Prometheus registry, đúng phiên bản Boot và thiết lập quyền truy cập endpoint. Không mặc định mở public endpoint metrics chứa thông tin hạ tầng. Cần xác minh tên metric thực tế qua exporter vì naming convention và phiên bản ảnh hưởng cách chuyển `app.event.process` thành series.

### 14.1. Prometheus và percentile

Nếu timer đã bật histogram, Prometheus có thể xuất các series `*_bucket`, `*_count` và `*_sum` theo naming convention phù hợp. Một truy vấn mẫu cho p95 theo handler:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, handler) (
    rate(app_event_process_seconds_bucket[5m])
  )
)
~~~

Giá trị phải được **xác minh với metric names và labels thật** trong hệ thống của bạn. Không dùng `histogram_quantile` nếu registry không xuất histogram bucket có label `le` phù hợp. Với hệ thống chỉ xuất count/sum, có thể tính mean rate nhưng không suy được percentile chính xác.

Đối với SLO, chọn threshold từ yêu cầu nghiệp vụ, ví dụ “p95 handler notification dưới 250 ms trong thời gian ổn định”. Con số đó là ví dụ cách đặt SLO, không phải chuẩn do Spring áp đặt.

## 15. Đo theo trace: kết nối publish và process span

Một flow có thể có:

~~~text
HTTP request span
    |
    +--> event.publish span
              |
              +--> handler.inventory span
              +--> handler.billing span
              +--> handler.notification span
~~~

Đây là **hình khái niệm**, không phải cấu trúc span Spring tự cung cấp cho `@EventListener`. Trong async, các span handler có thể là child/link hoặc một trace khác tùy cách propagate context và quy tắc instrumentation. Tracing cung cấp bằng chứng từng event khi được sample, nhưng không thay thế metric tổng hợp độ trễ cho tất cả event.

Khi event đi qua message broker hoặc transaction outbox:

- Dùng `eventId`/`correlationId` trong log/trace theo chính sách.
- Dùng trace context propagation theo chuẩn được hệ thống hỗ trợ.
- Tách `enqueue`, `broker lag`, `consumer start`, `consumer finish`.
- Không đưa `System.nanoTime()` của producer qua các máy để tính thời gian giao nhận.
- Nếu dùng wall-clock timestamp cho end-to-end giữa máy, đánh giá clock skew hoặc dùng tracing/server-side metrics có ngữ nghĩa rõ ràng.

## 16. Thiết kế dashboard và cảnh báo

Một dashboard event có thể chia thành bốn nhóm:

| Nhóm | Biểu đồ / câu hỏi |
| --- | --- |
| Producer | Publish rate, `publish_duration` p95/p99, exception count |
| Dispatch | Queue depth, rejected tasks, publish-to-start delay |
| Handler | `process_duration` p50/p95/p99 theo handler, success/error count, inflight |
| Business completion | Thời gian tới kết quả đã xác nhận, retry/dead-letter backlog, outcome |

Các biểu đồ phải có **định nghĩa tên và đơn vị thời gian**. Không gọi đồng thời cả `publish_duration` và `process_duration` là “event latency” mà không phân biệt stage. Với metric dạng timer, chọn aggregation phù hợp: rate/count cho throughput, histogram percentile cho tail latency, và tổng duration để theo dõi tiêu thụ thời gian.

Gợi ý cảnh báo:

1. **Handler p95 tăng kéo dài** dù publish latency không đổi → kiểm tra dependency chậm, worker hoặc database.
2. **Queue depth tăng liên tục** → producer nhanh hơn consumer, cần backpressure/concurrency/rate limit.
3. **Số handler errors tăng** → phân loại lỗi và kiểm tra những event chưa thành công.
4. **No process measurement trong thời gian có publish** → có thể listener bị bỏ qua, transaction rollback, cấu hình event type sai hoặc đo sai; kiểm tra trước khi kết luận mất event.
5. **Publish latency tăng đồng thời process latency tăng ở synchronous mode** → một listener có thể đang kéo dài lời gọi publish.
6. **Process duration ổn nhưng business E2E tăng** → tra cứu queue lag, retry, commit delay hoặc downstream side effect.

Không đặt alert dựa trên một điểm dữ liệu đơn lẻ khi lưu lượng thấp. Dùng window và min sample count hợp lý trước khi kết luận phân vị.

## 17. Những lỗi đo đạc phổ biến

| Lỗi / ngộ nhận | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `publishEvent` trả về nhanh thì event xử lý nhanh | Async chỉ trả sau handoff, không chờ handler | Đo timer trong listener và chờ completion thật |
| Bọc `publishEvent` rồi gọi đó là “handler latency” | Có thể bao gồm 0, 1 hoặc nhiều listeners tùy cấu hình | Gắn timer ở từng handler |
| Dùng `System.currentTimeMillis()` để đo microseconds | Wall clock có thể điều chỉnh, độ phân giải không phù hợp | Dùng `Timer.Sample`/`System.nanoTime` trong cùng JVM |
| Dùng `System.nanoTime` qua nhiều process | Mốc monotonic không đồng bộ giữa JVM | Dùng trace/timestamps và xử lý clock skew |
| Timer chỉ stop ở đường success | Lỗi không được đo → số liệu thiên lệch | Dùng `try/finally` và outcome tag |
| Dùng `eventId`/`userId` làm metric tag | High cardinality, memory/TSDB cost | Tag hữu hạn, đưa ID vào trace/log |
| Gọi `Timer` cho Mono vừa tạo, không subscribe | Đo thời gian tạo pipeline, không đo xử lý | Instrument quanh subscription/terminal signal |
| Bật executor nhưng mong transaction ThreadLocal theo thread | Async phá ranh giới thread-bound | Thiết kế transaction và context propagation đúng |
| Một event có nhiều listeners nhưng đòi process count = publish count | Một event sinh nhiều handler executions | Xem count theo handler/event/outcome |
| Đo start delay rồi gọi đó là queue wait chính xác | Start delay còn chứa thời gian dispatch/commit | Đo enqueue và dequeue nếu cần queue wait |
| Lấy trung bình che khuất tail latency | Mean không thể hiện p95/p99 | Dùng histogram/percentiles |
| Coi `@Timed` tự instrument mọi `@EventListener` | Spring Framework không có Observation mặc định cho event listener | Đặt timer/Observation rõ trong handler hoặc cấu hình AOP hợp lệ |
| Không chờ async callback trước assertion | Đọc count quá sớm → test flaky | Latch/future/StepVerifier với timeout phù hợp |
| `finally` countDown nghĩa là business đã thành công | Nó chỉ báo handler đã kết thúc | Kiểm tra outcome và trạng thái side effect |
| Đưa duration nano theo `Timer` nhưng mô tả milliseconds | Sai đơn vị và dashboard | Dùng `TimeUnit` tường minh, xem exporter base unit |
| Chỉ có metric nhưng không có trace/error log | Không biết event nào lỗi cụ thể | Tách metric tổng hợp và log/trace có correlation |
| Benchmark 3 event trong demo rồi đặt SLO production | Demo không đại diện tải, GC, network | Load test, theo dõi dài hạn, đặt SLO theo nhu cầu |

## 18. Checklist áp dụng vào dự án

- [ ] Đã ghi rõ metric nào đo **publication handoff** và metric nào đo **handler processing**.
- [ ] Timer `publish` bắt đầu ngay trước lời gọi, không vô tình tính cả bước tạo payload lớn.
- [ ] Timer `process` nằm trong handler thật; đo cả success và error trong `finally`.
- [ ] Với async, có mechanism biết xử lý **đã kết thúc**; không lấy return của publisher làm completion.
- [ ] Với transaction-bound listener, biết phase, commit/rollback và trường hợp không có transaction.
- [ ] Mốc `start_delay`, `queue_wait` và `end_to_end` được định nghĩa khác nhau.
- [ ] Dùng clock monotonic cho duration cùng process; không ghép `nanoTime` qua các JVM.
- [ ] Metric tags là low-cardinality; không có event ID, user ID, payload, exception message.
- [ ] Nếu có executor, theo dõi queue depth, active workers, rejection và saturation.
- [ ] Nếu tracing async, có context propagation phù hợp và kiểm tra span linkage.
- [ ] Không gán nhãn “event thành công” chỉ dựa vào `publish.count`; xem từng handler/outcome.
- [ ] Dashboard/alert có phân biệt rate, duration, count, percentile và error rate.
- [ ] Kiểm thử sync, async, handler exception, ignored listener, rollback và không có subscription nếu dùng reactive.
- [ ] Không dựa vào số duration tuyệt đối trong unit test có timing thật; kiểm tra count/tags và semantic trước.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Một listener chạy qua executor và thực hiện HTTP mất 400 ms. `publishEvent` trả về sau 2 ms. `publish_duration` là bao nhiêu và có chứng minh listener nhanh không?

**Đáp án:** `publish_duration` gần 2 ms, đo handoff. Nó không phản ánh 400 ms xử lý; cần `process_duration` trong listener.

**Câu 2.** 100 sự kiện cùng loại, mỗi sự kiện có 3 listener. Tổng timer process có bắt buộc bằng 100 không?

**Đáp án:** Không; có thể có đến 300 lượt handler thành công nếu cả ba listener chạy mỗi lần, nhưng còn tùy lọc kiểu event, phase, lỗi và trạng thái completion.

**Câu 3.** Vì sao `@TransactionalEventListener(AFTER_COMMIT)` có thể cho publish timer thấp nhưng process timer xuất hiện muộn?

**Đáp án:** Vì khi publish chỉ đăng ký callback. Listener xử lý sau commit thật; start delay còn bao gồm khoảng transaction chưa hoàn tất.

**Câu 4.** `eventId` có nên là tag của Micrometer `Timer` không?

**Đáp án:** Không. Nó tạo time series giá trị gần như duy nhất, gây high cardinality; dùng event type/handler/outcome hữu hạn và correlation ID trong trace/log.

**Câu 5.** Nếu đã dùng `@EventListener`, Spring Framework tự có Observation cho mọi listener không?

**Đáp án:** Không. Phải instrument bằng Timer/Observation cụ thể hoặc hạ tầng AOP được cấu hình đúng, theo hợp đồng đồng bộ/bất đồng bộ.

**Câu 6.** `CountDownLatch` trong ví dụ bảo đảm điều gì?

**Đáp án:** Nó giúp main đợi đủ ba lần handler thoát khỏi phần thân và đo xong; không tự bảo đảm một side effect ngoài process đã được commit hay giao nhận bền vững.

**Câu 7.** Muốn đo queue wait thuần, timestamp cần lấy ở đâu?

**Đáp án:** Quanh thời điểm task được enqueue và lúc worker bắt đầu chạy. Từ lúc tạo event đến lúc listener chạy chỉ là start delay tổng hợp.

**Câu 8.** Cần dùng đơn vị gì cho `Timer.record`?

**Đáp án:** Dùng `TimeUnit` rõ ràng cho số duration hoặc các API Timer ghi duration; không giả định số nguyên truyền vào là milliseconds hay nanoseconds mà không chỉ định.

## 20. Tài liệu tham khảo

- Spring Framework 6.2 — `ApplicationEventPublisher` và contract handoff: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — `SimpleApplicationEventMulticaster`, executor và xử lý exception: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Reference 6.2 — Observability Support; mục Application Events / `@EventListener`: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
- Spring Framework Reference 6.2 — Standard and Custom Events: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework Reference 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Micrometer Reference — Timers và `Timer.Sample`: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer Reference — Choosing Meter Types: https://docs.micrometer.io/micrometer/reference/concepts/meters.html
- Micrometer Reference — Histograms and Percentiles: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
- Spring Boot Reference — Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Micrometer Context Propagation: https://docs.micrometer.io/context-propagation/reference/
