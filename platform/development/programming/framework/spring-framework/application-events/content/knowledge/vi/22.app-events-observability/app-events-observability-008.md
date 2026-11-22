# Metric lỗi và thời gian xử lý trong Spring Framework Application Events

## 1. Vì sao cần đo lường Spring Application Events?

Trong nhóm **Observability**, việc có log “đã publish event” chưa đủ để kết luận listener đã xử lý thành công. Một ứng dụng có thể phát `OrderPlaced`, `PaymentReceived` hoặc `InventoryReserved` và cho nhiều listener phản ứng. Các vấn đề thường gặp:

- Một listener xử lý chậm khiến request bị tăng độ trễ khi dispatch đồng bộ.
- Listener thất bại nhưng lỗi bị `ErrorHandler` ghi log và suppress, làm publisher tưởng mọi việc đã hoàn tất.
- Listener chạy trên thread pool, trong khi `publishEvent()` trả về trước khi tác vụ kết thúc.
- Số lỗi tăng sau deployment, nhưng log rời rạc khiến khó xác định loại event/handler nào đang lỗi.
- Một phần nghiệp vụ chạy sau database commit; kết quả commit và kết quả side effect không phải cùng một trạng thái.

**Metric lỗi và thời gian xử lý** giúp trả lời một cách có thể tổng hợp và cảnh báo:

1. Mỗi listener được gọi bao nhiêu lần?
2. Bao nhiêu lần xử lý thành công và bao nhiêu lần gặp exception?
3. Độ trễ thực tế của từng listener và xu hướng p95/p99 ra sao?
4. Có xảy ra tắc nghẽn ở hàng đợi executor không?
5. Việc publish, xử lý listener và hoàn tất công việc bên ngoài khác nhau ở điểm nào?
6. Khi xảy ra lỗi, có thể lần theo correlation ID/event ID trong log hoặc trace để điều tra không?

Các metric cần có tên, đơn vị, tập tag ổn định, phạm vi đo rõ và chính sách quan sát lỗi. **Một số đo không có ranh giới rõ ràng dễ dẫn tới quyết định vận hành sai.**

## 2. Ba ranh giới thời gian cần phân biệt

### 2.1. Thời gian gọi `publishEvent()`

Với `ApplicationEventPublisher.publishEvent(event)`, bạn có thể đo thời gian của chính lời gọi publish:

```java
long start = System.nanoTime();
try {
    applicationEventPublisher.publishEvent(event);
} finally {
    long elapsedNanos = System.nanoTime() - start;
    publisherTimer.record(elapsedNanos, TimeUnit.NANOSECONDS);
}
```

Đây là **đoạn tích hợp**, giả định publisher, event và Micrometer `Timer` đã được khai báo.

`System.nanoTime()` thích hợp để đo **elapsed time** vì là đồng hồ monotonic, không phải timestamp lịch. Dùng `Instant.now()` hoặc `System.currentTimeMillis()` để ghi mốc thời gian trong log/tracing, không nên trừ hai giá trị wall clock rồi coi đó là latency chắc chắn.

Ý nghĩa thời gian publish thay đổi theo cấu hình:

- **Multicaster đồng bộ mặc định:** lời gọi `publishEvent()` bao gồm dispatch và quá trình chạy các listener đồng bộ được gọi trên thread publisher. Nếu listener chậm, publish lâu.
- **Multicaster có executor:** lời gọi có thể chỉ bao gồm việc xác định listener, submit task và các listener vẫn cần chạy trong thread publisher. Nó **không** đo thời gian xử lý của các task async sau khi được enqueue.
- **Listener gắn transaction:** việc đăng ký synchronization có thể xảy ra lúc publish, nhưng xử lý theo phase như `AFTER_COMMIT` diễn ra lúc transaction hoàn tất, không nhất thiết trong lời gọi publish.

Do đó, biểu đồ `publishEvent latency` **không thay thế** biểu đồ thời gian xử lý handler.

### 2.2. Thời gian một listener thực thi

Đây thường là metric quan trọng nhất cho yêu cầu của bài học: đặt phép đo ngay **quanh logic của mỗi handler**:

```text
Listener bắt đầu
       |
       +--> lấy start time / Timer.Sample
       |
       +--> validate, tính toán, gọi service, I/O nếu có
       |
       +--> thành công hoặc exception
       |
       +--> ghi Timer với outcome tương ứng
       +--> tăng Counter lỗi nếu exception thuộc phạm vi đo
       |
Listener kết thúc
```

Đo tại handler sẽ phản ánh thời gian thực sự thực thi mã của listener, **không** tự bao gồm thời gian chờ queue trước khi handler bắt đầu. Nếu một handler chỉ enqueue job ra ngoài rồi trả về, thời gian handler nhỏ **không có nghĩa job đã hoàn tất**.

### 2.3. Độ trễ end-to-end của event

Độ trễ từ lúc xảy ra fact nghiệp vụ tới lúc mọi side effect cần thiết hoàn thành có thể bao gồm:

```text
Domain fact -> publish -> queue -> listener -> retry/backoff
                -> remote service / message broker -> consumer -> kết quả
```

Để đo **end-to-end**, phải định nghĩa mốc bắt đầu/kết thúc, lưu `eventId` và thời điểm thích hợp, quan sát cả queue/remote work, và có signal hoàn tất thực sự. Một `Timer` trong Spring listener không đo tự động các bước đó.

Trong một process, có thể dùng monotonic elapsed time nếu cùng clock phù hợp và cùng vòng đời đo. Với hệ thống phân tán, timestamps từ nhiều máy có thể lệch; cần tracing, clock discipline và quy tắc diễn giải đo lường. Không truyền `System.nanoTime()` qua broker rồi trừ ở process khác: giá trị nanoTime không có mốc gốc chung giữa JVM/máy.

## 3. Chọn metric nào: Timer, Counter, Gauge, Observation?

| Metric | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `Timer` | Số lượt được ghi, tổng thời gian, max và histogram/percentiles nếu bật | Đo duration của mỗi lần listener được gọi |
| `Counter` | Số sự kiện cộng dồn, chỉ tăng | Đếm exception, retry, reject, timeout hay tác vụ lỗi |
| `Gauge` | Giá trị tức thời | Độ sâu hàng đợi, số task active, backlog |
| `DistributionSummary` | Phân phối đại lượng không phải thời gian | Kích thước payload hoặc batch |
| `Observation` | API theo dõi một operation và có thể sinh metrics/traces tùy handler | Khi muốn kết hợp đo duration với tracing/low-cardinality context |

**Micrometer `Timer` đã có count và total time**, nên không nhất thiết tạo thêm `Counter` cho **mọi** thành công. Có thể dùng hai timer series mang tag `outcome=success/error` để tính tỷ lệ thành công/lỗi theo cùng mẫu số. Counter lỗi riêng vẫn hữu ích để:
- Phân nhóm failure cause có kiểm soát.
- Đặt alert trực tiếp trên error throughput.
- Đo các lỗi **không gắn với** handler như executor rejection hoặc lỗi convert/publish.

Cần định nghĩa rõ một đơn vị tính: **một listener invocation**, **một lần publish**, hay **một logical event đã được xử lý cuối cùng**. Với retry, ba thứ này không đồng nhất.

### Naming và unit

Ví dụ một bộ tên metric ở dạng Micrometer:

| Tên | Loại | Ý nghĩa |
| --- | --- | --- |
| `application.events.listener.duration` | Timer | Thời gian một lần thực thi listener |
| `application.events.listener.errors` | Counter | Số exception ứng dụng do listener ghi nhận |
| `application.events.publish.duration` | Timer | Độ dài lời gọi publishEvent |
| `application.events.executor.queued` | Gauge | Số task đang chờ trong pool |
| `application.events.executor.rejected` | Counter | Lượt executor từ chối submit |
| `application.events.delivery.retries` | Counter | Số lần retry khi gửi/consume theo cơ chế riêng |

Micrometer quy đổi tên và đơn vị theo monitoring backend. Với Prometheus, timer thường xuất ra series có hậu tố `_seconds_count`, `_seconds_sum` (và `_seconds_bucket` khi histogram thích hợp đã bật); counter thường có hậu tố `_total`. Không tự cộng đổi từ nanoseconds sang milliseconds ở nhiều nơi nếu đã dùng `Timer.record(duration, unit)` hoặc `Timer.Sample` đúng API.

## 4. Thiết kế tag: phân nhóm có ích, tránh cardinality bùng nổ

Một chiến lược tag thực tế:

- `event=OrderPlaced`: **loại** event, tập giá trị hữu hạn.
- `listener=OrderPlacedListener`: tên handler/consumer ổn định.
- `outcome=success|error`: trạng thái của **một attempt**.
- `exception=IllegalArgumentException` hoặc nhóm lỗi hữu hạn khi cần counter lỗi.
- `phase=immediate|after_commit|after_rollback` nếu thật sự cần phân biệt và số giá trị có giới hạn.
- `delivery=sync|async` nếu có khác biệt có ý nghĩa và dự án chuẩn hóa rõ.

**Không đặt vào metric tags**:
- `orderId`, `userId`, `eventId`, `correlationId`, `traceId` hoặc request URI động chứa ID.
- Toàn bộ `exception.getMessage()`, SQL query gốc hoặc message payload.
- Tên người dùng, email, access token, PII hoặc dữ liệu nhạy cảm.

Ví dụ: 10 loại event × 8 listener × 2 outcome × 4 exception category tạo tối đa 640 nhóm metric trước khi xét thêm dimension. Nếu dùng một triệu `eventId` khác nhau làm tag, số time series có thể tăng theo số event, gây chi phí, chậm dashboard và mất dữ liệu do giới hạn backend.

Đưa high-cardinality identifiers vào **structured logs hoặc tracing spans**, không vào metric labels. Cùng metric name nên có **tập tên tag nhất quán** trên các series, nhất là với Prometheus registry; nếu tag `exception` chỉ có ở error timer, tốt hơn giữ `exception` ngoài timer và dành nó cho counter lỗi riêng.

## 5. Ví dụ Java 17+ chạy được: Micrometer Timer và Counter cho @EventListener

Ví dụ dưới đây dùng Spring Framework 6.1.21 và Micrometer Core. Nó tạo **hai event**: một xử lý thành công, một chủ động ném `IllegalArgumentException`. Listener:
- Dùng `Timer.Sample` để đo mỗi invocation.
- Ghi duration vào một `Timer` có tag `outcome=success` hoặc `outcome=error`.
- Khi handler ném `RuntimeException`, tăng `Counter` lỗi một lần rồi **rethrow** để giữ nguyên ngữ nghĩa lỗi.
- Không ghi ID payload vào metric tag.
- Sau khi publish hai event, chương trình đọc kết quả từ `SimpleMeterRegistry` và in số liệu ổn định.

Không cần Spring Boot, web server, database hay monitoring backend ngoài. `SimpleMeterRegistry` dùng để minh họa và kiểm thử trong process; production nên cấu hình registry thực qua Micrometer/Actuator/Prometheus hoặc backend phù hợp.

Cấu trúc dự án:

```text
event-metrics-demo/
├── build.gradle
└── src/main/java/demo/EventMetricsDemo.java
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
    implementation 'io.micrometer:micrometer-core:1.13.6'
}

application {
    mainClass = 'demo.EventMetricsDemo'
}
```

File `src/main/java/demo/EventMetricsDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class EventMetricsDemo {

    public record OrderPlaced(String orderId, boolean fail) {}

    public static final class OrderPlacedListener {
        private final MeterRegistry meters;

        public OrderPlacedListener(MeterRegistry meters) {
            this.meters = meters;
        }

        @EventListener
        public void on(OrderPlaced event) {
            Timer.Sample sample = Timer.start(meters);
            String outcome = "error"; // Mặc định fail-closed cho duration.

            try {
                process(event);
                outcome = "success";
            } catch (RuntimeException ex) {
                Counter.builder("application.events.listener.errors")
                    .description("Number of listener runtime failures")
                    .tags(
                        "event", "OrderPlaced",
                        "listener", "OrderPlacedListener",
                        "exception", "IllegalArgumentException"
                    )
                    .register(meters)
                    .increment();
                throw ex; // Không nuốt lỗi.
            } finally {
                Timer timer = Timer.builder(
                        "application.events.listener.duration")
                    .description("Elapsed time of one listener attempt")
                    .tags(
                        "event", "OrderPlaced",
                        "listener", "OrderPlacedListener",
                        "outcome", outcome
                    )
                    .register(meters);
                sample.stop(timer);
            }
        }

        private void process(OrderPlaced event) {
            if (event.fail()) {
                throw new IllegalArgumentException(
                    "simulated listener failure"
                );
            }
            // Một nghiệp vụ thành công trong ví dụ.
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public MeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        public OrderPlacedListener orderPlacedListener(
                MeterRegistry registry) {
            return new OrderPlacedListener(registry);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            MeterRegistry metrics = context.getBean(MeterRegistry.class);

            context.publishEvent(new OrderPlaced("ORD-1", false));

            try {
                context.publishEvent(new OrderPlaced("ORD-2", true));
            } catch (IllegalArgumentException expected) {
                System.out.println(
                    "publisher caught=" + expected.getMessage()
                );
            }

            long successes = metrics.get(
                    "application.events.listener.duration")
                .tags(
                    "event", "OrderPlaced",
                    "listener", "OrderPlacedListener",
                    "outcome", "success"
                )
                .timer()
                .count();

            long failures = metrics.get(
                    "application.events.listener.duration")
                .tags(
                    "event", "OrderPlaced",
                    "listener", "OrderPlacedListener",
                    "outcome", "error"
                )
                .timer()
                .count();

            double errors = metrics.get(
                    "application.events.listener.errors")
                .tags(
                    "event", "OrderPlaced",
                    "listener", "OrderPlacedListener",
                    "exception", "IllegalArgumentException"
                )
                .counter()
                .count();

            System.out.println("success_count=" + successes);
            System.out.println("error_count=" + failures);
            System.out.printf(
                java.util.Locale.ROOT,
                "error_counter=%.0f%n", errors
            );
        }
    }
}
```

Chạy bằng JDK 17+ và Gradle:

```bash
gradle run --quiet
```

**Các dòng stdout nghiệp vụ kỳ vọng** (không tính thông báo bổ sung của Gradle/backend logging):

```text
publisher caught=simulated listener failure
success_count=1
error_count=1
error_counter=1
```

Giải thích:
1. `AnnotationConfigApplicationContext` đăng ký `SimpleMeterRegistry` và một `OrderPlacedListener` có `@EventListener`.
2. Không cấu hình executor, nên multicaster mặc định dispatch listener đồng bộ. `publishEvent(ORD-1)` chạy thành công và tạo một Timer sample mang `outcome=success`.
3. `publishEvent(ORD-2)` gọi handler, `process` ném `IllegalArgumentException`, counter lỗi tăng, block `finally` vẫn ghi duration mang `outcome=error`.
4. `catch` bên ngoài nhận exception do Spring multicaster đồng bộ **không có ErrorHandler custom**. Nó không chứng minh DB rollback, vì demo không dùng transaction.
5. `Timer.count()` là số samples được ghi, **không phải tổng thời gian**. Tổng duration có thể đọc qua `timer.totalTime(TimeUnit.MILLISECONDS)` hoặc `timer.mean(TimeUnit.MILLISECONDS)`, nhưng giá trị thực thay đổi theo máy nên ví dụ không in số mili-giây cố định.
6. Mã bắt `RuntimeException` làm phạm vi counter lỗi ứng dụng. Trong trường hợp phát sinh `Error` nghiêm trọng, `finally` vẫn chạy khi runtime cho phép và sample được gắn outcome error, nhưng counter ví dụ không được tăng vì không có `catch(Error)`. Không nên coi `OutOfMemoryError` là lỗi nghiệp vụ cần xử lý tương tự.
7. Tag `exception` trong demo được cố định là `IllegalArgumentException` vì chính method demo chủ động ném đúng loại đó. Ứng dụng thực cần ánh xạ exception sang **một tập class/category giới hạn**; không nên gắn message hoặc ID động.

**Quan trọng về thứ tự và ngữ nghĩa:** thử nghiệm không dùng `@Async` hoặc `setTaskExecutor(...)`, nên có thể đọc tất cả metrics ngay sau `publishEvent` trả về (hoặc ném exception). Nếu chuyển listener sang executor, không được kỳ vọng các phép đếm đã hoàn thành ngay tại thời điểm publish trả về; test phải đợi handler chạy bằng latch/future hoặc tín hiệu kiểm thử tương ứng.

## 6. Vì sao Timer.Sample và finally phù hợp?

`Timer.Sample.start(registry)` lưu thời điểm bắt đầu theo monotonic clock do Micrometer quản lý. `sample.stop(timer)` ghi elapsed duration vào timer đã chọn. Ta chỉ biết outcome sau khi nghiệp vụ chạy nên có thể chọn timer tag `outcome=success/error` **ở cuối**.

Mẫu chung:

```java
Timer.Sample sample = Timer.start(registry);
String outcome = "error";

try {
    businessAction();
    outcome = "success";
} catch (RuntimeException ex) {
    failureCounter.increment();
    throw ex;
} finally {
    Timer.builder("application.events.listener.duration")
        .tags("event", "OrderPlaced", "outcome", outcome)
        .register(registry);
    // Ví dụ hoàn chỉnh cần giữ reference Timer rồi gọi sample.stop(timer).
}
```

Đoạn trên là **pseudo-integration snippet** nhằm làm rõ luồng điều khiển, không phải chương trình hoàn chỉnh như mục 5. Code production nên cache/đăng ký meter đúng chiến lược để giảm chi phí lookup hot path. `Timer.Sample` có thể dùng khi outcome cần được xác định ở cuối mà vẫn muốn timestamp bắt đầu chính xác.

**Không bỏ `finally`**: nếu handler ném exception trước khi ghi timer, những lần xử lý chậm nhất và thất bại có thể không xuất hiện trong biểu đồ latency, dẫn tới dữ liệu thiên lệch. Đồng thời, **không được nuốt exception** chỉ để dashboard nhìn đẹp; việc chọn `ErrorHandler`, retry và chuyển lỗi tới caller phải có hợp đồng riêng.

Cần cân nhắc lỗi xảy ra trong chính code instrumentation: một bug đo lường trong `finally` có thể che exception gốc. Thực tế nên giữ logic ghi metrics đơn giản, đặt các meter ổn định sớm và test nhánh instrumentation failure nếu hệ thống có yêu cầu cao.

## 7. Tách metric publish, listener và queue wait

Một kiến trúc quan sát tốt thường có ba nguồn dữ liệu:

| Stage | Mốc bắt đầu/kết thúc | Metric | Cần lưu ý |
| --- | --- | --- | --- |
| Publish call | Trước/sau `publishEvent()` | `application.events.publish.duration` | Với async chỉ phản ánh handoff/dispatch, không phải handler completion |
| Queue wait | Lúc submit task đến lúc worker bắt đầu | `application.events.executor.queue.wait` | Phải đo trên cùng executor; không tự có trong listener Timer |
| Handler execution | Bắt đầu method đến khi method kết thúc | `application.events.listener.duration` | Phản ánh một lần xử lý trong handler; không gồm job được tách sau đó |
| End-to-end | Khi domain fact hợp lệ đến khi outcome thật hoàn tất | `application.events.delivery.duration` hoặc tracing | Cần outcome/event lifecycle và cơ chế bền vững riêng |

### Cấu hình async làm thay đổi kết luận từ metric publish

`SimpleApplicationEventMulticaster` mặc định gọi listener trong calling thread. Khi cấu hình `setTaskExecutor(executor)`, listener hỗ trợ async có thể được submit sang pool; listener nào **không hỗ trợ async execution** vẫn có thể được gọi trong publisher thread, ví dụ transactional listener đăng ký synchronization. Vì vậy, thời gian publish không đơn giản là “đo queue enqueue” cho mọi listener.

Nếu muốn biết pool nghẽn, đo:
- `executor.active`: số task đang hoạt động.
- `executor.queued`: số task chờ.
- `executor.rejected`: số task bị từ chối.
- `executor.completed` hoặc task throughput (tùy executor/registry cung cấp).

`ThreadPoolTaskExecutor` có thể expose những số liệu liên quan (`getActiveCount()`, `getPoolSize()`, queue size thông qua underlying executor); việc bind/đặt gauge cần tuân theo tên và vòng đời bean. Không tự giả định Spring Framework core đã xuất tất cả metric này ra Prometheus mà không có binder/Actuator/custom registration.

**Queue wait và timeout khác nhau:** queue wait đo lúc task chưa bắt đầu; timeout đo một hạn mức nghiệp vụ hoặc I/O. Nếu tác vụ bị rejected ở lúc submit, không có listener invocation để ghi `listener.duration`; cần counter rejection riêng nếu muốn biết đầy đủ tình trạng không xử lý được event.

## 8. Lỗi listener với SimpleApplicationEventMulticaster

### 8.1. Đồng bộ không có ErrorHandler

Ở cấu hình mặc định, một exception của listener có thể **dừng multicast hiện tại** và propagate tới publisher. Nếu có nhiều listener, không nên giả định tất cả listener phía sau đều đã được gọi khi một listener trước ném lỗi.

Ví dụ:

```text
publish(OrderPlaced)
   |
   +--> listener A thành công
   |
   +--> listener B ném IllegalStateException
           |
           +--> exception propagate về publisher
           +--> listener C có thể không được gọi
```

Chỉ ghi một `publish error` từ caller sẽ bỏ sót thông tin **listener nào lỗi**, còn đếm cả publisher và handler error mà không phân biệt mục đích có thể làm hai biểu đồ cùng phản ánh một sự cố theo hai đơn vị khác nhau. Gắn nhãn metric để phân biệt error ở biên publish với error của handler.

### 8.2. Dùng `setErrorHandler(...)`

`SimpleApplicationEventMulticaster.setErrorHandler(...)` có thể nhận strategy để xử lý lỗi listener. Một strategy suppress lỗi có thể giúp các listener còn lại tiếp tục, nhưng **`publishEvent()` thành công không đồng nghĩa tất cả listeners đã thành công**. Nếu chiến lược propagate lỗi, publisher vẫn có thể nhận exception.

Khi dùng error handler, tăng metric ở **một vị trí có contract rõ**:
- Trực tiếp bên trong handler/wrapper của handler cho lỗi thực tế của mỗi attempt.
- Hoặc trong một shared error handler để đếm các exception mà multicaster bắt được, khi không có lớp instrumentation khác trùng đếm.

Tránh tăng cùng một counter ở cả listener lẫn ErrorHandler nếu hai nơi cùng ghi cho một lần thất bại, trừ khi metric được định nghĩa khác nhau và đặt tên/tags rõ.

### 8.3. Async và @Async

Với executor, listener có thể lỗi **sau khi** publisher đã trả về. Lỗi thường đến cơ chế executor/async error handling, không tự propagate về request publisher. `@Async @EventListener` dùng đường async proxy và error handling khác với multicaster executor tùy cấu hình.

Vì vậy, **đo trực tiếp trong listener hoặc tại wrapper thực thi** đáng tin hơn suy ra lỗi listener từ số exception của `publishEvent()`. Các công việc async quan trọng phải có retry, dead-letter, và alert theo delivery outcome; một metric cho exception là cảnh báo nhưng không tự khôi phục tác vụ.

## 9. Transactional event listener và thời gian sau commit

`@TransactionalEventListener` có các phase `BEFORE_COMMIT`, `AFTER_COMMIT` (mặc định), `AFTER_ROLLBACK` và `AFTER_COMPLETION`. Việc phát event trong một transaction thường **đăng ký synchronization**; phase xử lý có thể xảy ra khi transaction kết thúc.

Các câu hỏi phải tách biệt:
- Transaction DB có commit thành công không?
- Listener `AFTER_COMMIT` có được gọi không?
- Listener thực thi có ném exception không?
- Job/broker/API do listener kích hoạt đã hoàn tất chưa?

Nếu DB đã commit nhưng handler `AFTER_COMMIT` thất bại, không thể rollback lại transaction gốc. Listener timing đo **handler thực thi ở phase đó**, không phải tự động đo toàn bộ thời gian transaction hoặc độ trễ từ lúc phát event.

Đo transaction duration bằng instrumentation của transaction/database phù hợp; đo event handler duration bằng Timer riêng; đo external delivery hoặc outbox lag bằng một metric khác. Đừng cộng các series có đơn vị hoặc start/end khác nhau để tạo một “total” tùy ý.

**Không tự động đo được delivery guarantee:** Spring Application Events là in-process; `@TransactionalEventListener(AFTER_COMMIT)` vẫn có khoảng trống crash sau commit. Nếu event quan trọng không được phép mất, lưu **transactional outbox** trong cùng DB transaction, rồi đo backlog, age, retry và successful deliveries từ worker.

### Reactive transaction

Trong WebFlux/Reactor, transactional event có thể mang `TransactionContext` theo cơ chế Spring 6.1 (thường qua `TransactionalEventPublisher`). Với handler reactive, một method trả về `Mono` **không đồng nghĩa phép đo method invocation bao trùm thời gian subscription và completion**. Cần instrument tại reactive Publisher lifecycle, chẳng hạn bằng `doOnEach`, `doFinally`, `tap` hoặc Micrometer Observation tích hợp đúng cách. Đặc biệt, `doFinally` chạy theo signal terminal/cancel, nhưng xác định success/error/cancel cần xử lý riêng; không đơn giản coi mọi `finally` là thành công.

## 10. Độ trễ và phân phối: mean, p95, p99, histogram

Một `Timer` cung cấp count, total time và max/percentiles/histogram tùy cấu hình. Không nên chỉ nhìn **mean**:

- Mean 10 ms vẫn có thể che một nhóm request chạy 5 giây.
- p95/p99 thể hiện **tail latency**, thường ảnh hưởng user experience khi listener đồng bộ.
- Max trong Micrometer thường là max theo time window, có thể reset/đổi khi cửa sổ trôi; không nên coi max từ SimpleMeterRegistry trong một phút là max vĩnh viễn.
- Histogram cần chọn bucket/service level objective phù hợp, có chi phí time series.

Có thể khai báo timer cho production như sau (đoạn tích hợp):

```java
Timer timer = Timer.builder("application.events.listener.duration")
    .description("Duration of an event listener invocation")
    .tags(
        "event", "OrderPlaced",
        "listener", "OrderPlacedListener",
        "outcome", "success"
    )
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(10),
        Duration.ofMillis(50),
        Duration.ofMillis(200),
        Duration.ofSeconds(1)
    )
    .register(registry);
```

Cần import `java.time.Duration`, `io.micrometer.core.instrument.Timer` và `MeterRegistry`, và backend hỗ trợ histogram. Đây **không phải code bắt buộc cho chương trình demo**; chỉ bật histogram khi thật sự cần tính percentiles trên monitoring backend, thường không bật tràn lan cho tất cả event/handler.

**Đọc p95/p99 đúng cách:** nếu backend hỗ trợ histogram, có thể tổng hợp percentile theo tag bằng cách hợp lệ (ví dụ Prometheus `histogram_quantile` trên các bucket); không lấy trung bình đơn giản của các p95 từ nhiều pod rồi coi đó là p95 của toàn hệ thống.

## 11. Ví dụ truy vấn Prometheus và ý nghĩa

Nếu dùng Prometheus registry và timer/counter được export với tên chuẩn hóa, query có thể có dạng:

```promql
sum by (event, listener, outcome) (
  rate(application_events_listener_duration_seconds_count[5m])
)
```

Query này ước lượng **attempts mỗi giây** theo outcome. Nó không phải độ trễ.

Một query tính **mean seconds** theo handler:

```promql
sum by (event, listener) (
  rate(application_events_listener_duration_seconds_sum[5m])
)
/
clamp_min(
  sum by (event, listener) (
    rate(application_events_listener_duration_seconds_count[5m])
  ),
  1e-9
)
```

Một query p95 **chỉ khi có histogram buckets**:

```promql
histogram_quantile(
  0.95,
  sum by (le, event, listener) (
    rate(application_events_listener_duration_seconds_bucket[5m])
  )
)
```

Một query error ratio dựa trên **cùng Timer attempts**, giảm nguy cơ khác mẫu số giữa counter và timer:

```promql
sum by (event, listener) (
  rate(application_events_listener_duration_seconds_count{outcome="error"}[5m])
)
/
clamp_min(
  sum by (event, listener) (
    rate(application_events_listener_duration_seconds_count[5m])
  ),
  1e-9
)
```

Tên thực tế phụ thuộc naming convention, Micrometer registry version và exporter của hệ thống. Query trên là **mẫu hướng dẫn** cần xác minh với series mà Prometheus thực sự scrape được, không phải cam kết rằng một ứng dụng Spring Context thuần tự có Prometheus endpoint.

**Rate trên counter** phù hợp hơn nhìn giá trị tích lũy khi muốn so sánh lưu lượng theo thời gian. Với các event hiếm, 5 phút có thể thiếu mẫu; có thể cần cửa sổ dài hơn hoặc alert dựa số lỗi tuyệt đối. Chú ý nhánh “zero denominator” và một số event không hề được gọi không tạo series thành công để chia; dashboard cần thể hiện “no data” có chủ đích.

## 12. Alert và SLO

Một số chỉ báo có ý nghĩa vận hành:

| Signal | Khi nào cảnh báo? | Kiểm tra trước khi kết luận |
| --- | --- | --- |
| Error rate của listener quan trọng | Tăng vượt ngưỡng đủ lâu với đủ số attempts | Có retry? có thay đổi số lượng event? |
| Error count tuyệt đối | Có failure hiếm nhưng nghiêm trọng | Exception category và business criticality |
| p95/p99 duration | Vượt latency objective theo nhiều cửa sổ | Handler blocking, downstream API hay GC |
| Executor backlog/queue wait | Tăng liên tục trong khi worker bận | Pool size, task type, reject policy |
| Rejected tasks | Bất kỳ giá trị nào với event bắt buộc xử lý | Có fallback sync? có outbox? |
| Outbox age/backlog | Event commit lâu nhưng chưa giao | Worker sống không, broker có lỗi không |
| Event volume biến mất | Count đột ngột về 0 khi vẫn có traffic | Event không được publish hay metric pipeline hỏng? |

Ví dụ giả định: listener gửi email phải xử lý p95 trong 200 ms và error ratio dưới 0,5% trong ít nhất 15 phút. Đây là **mục tiêu minh họa**, không phải mặc định cho mọi dự án. Nếu listener chỉ enqueue email vào queue, 200 ms là SLO của **enqueue**, không phải SLO của việc email đến khách hàng. Cần đặt SLO ở đúng ranh giới user-facing/business outcome.

Alert cần ngưỡng tối thiểu lưu lượng và khoảng chờ thích hợp, tránh báo động quá mức khi mới có 1 error trên 2 attempts hoặc khi deployment làm thay đổi số series.

## 13. Kết hợp metrics với log và tracing

Metrics trả lời **“bao nhiêu lần, chậm đến mức nào?”**. Log và tracing trả lời **“lần nào, ở đâu, vì sao?”**.

Một event nên có:
- `eventId`: định danh một lần xảy ra domain event; hữu ích cho retry/idempotency.
- `correlationId`: liên kết nhiều thao tác trong cùng workflow.
- `traceId`/`spanId`: liên kết tới distributed trace nếu tracing được cấu hình.
- `eventType` và `listener`: tag hữu hạn cho metric.

Ví dụ structured log khi handler lỗi:

```text
level=ERROR eventType=OrderPlaced listener=OrderPlacedListener
eventId=EVT-17 correlationId=REQ-42 exception=IllegalArgumentException
message="simulated listener failure"
```

Log này là **minh họa**; không phải output của chương trình demo. Metric chỉ gắn `event=OrderPlaced`, `listener=OrderPlacedListener` và `outcome=error`. Các ID riêng biệt ở log/trace, tránh cardinality bùng nổ.

Khi listener chạy qua `@Async` hoặc executor multicaster, MDC (Mapped Diagnostic Context) gắn thread không mặc nhiên truyền sang worker. Dùng `TaskDecorator`/Micrometer context propagation phù hợp, hoặc dựng lại logging scope từ immutable event payload. Việc propagate MDC không tự propagate transaction, security hay bảo đảm delivery.

## 14. Kiểm thử độ đúng của instrumentation

### 14.1. Unit test Timer và Counter

`SimpleMeterRegistry` phù hợp cho test:
1. Gọi listener với event thành công; assert Timer `outcome=success` có count 1, fail timer chưa có hoặc count 0.
2. Gọi listener với event gây lỗi; assert exception vẫn được ném và Error Counter tăng chính xác một lần.
3. Assert Timer `outcome=error` có count 1 **dù handler ném exception**.
4. Có thể kiểm tra `totalTime(...) >= 0`, không assert exact duration của máy vì scheduling/CPU khác nhau.
5. Đảm bảo metric không có tag `eventId`, `orderId` hoặc `correlationId`.

Trong một framework test, để tránh phụ thuộc clock, có thể cung cấp `MockClock` cho một registry thích hợp hoặc đo bằng Timer.Sample theo clock đã kiểm soát. Không dùng `Thread.sleep` làm cách chủ đạo để xác minh đơn vị thời gian.

### 14.2. Integration test với Spring context

Chạy với `AnnotationConfigApplicationContext` tương tự demo, đảm bảo `@EventListener` thực sự được đăng ký. Gọi `publishEvent` và đọc registry. Trong sync mode, metric có ngay sau lời gọi listener kết thúc; khi có nhiều listeners, cần xác minh từng listener độc lập, không suy ra tất cả đã chạy nếu một listener lỗi.

### 14.3. Async test

Khi multicaster dùng `ThreadPoolTaskExecutor`:
- Dùng `CountDownLatch`/future hoặc test signal để chờ listener hoàn tất.
- Verify Timer count của **listener** sau completion, không đo publish rồi coi là handler time.
- Kiểm tra task bị rejected hoặc queue full được quan sát ở metric riêng.
- Cho listener lỗi, verify lỗi xuất hiện ở error metric/log dù publisher không nhận exception.

### 14.4. Transaction integration test

Trong transaction có `@TransactionalEventListener(AFTER_COMMIT)`:
- Commit thật rồi xác minh listener được gọi/đo.
- Rollback và xác minh listener `AFTER_COMMIT` không được gọi.
- Nếu listener lỗi sau commit, DB state vẫn commit; error metric phản ánh **post-commit failure**.
- Test Spring `@Transactional` có thể tự rollback cuối test nên phải chủ động commit khi cần test AFTER_COMMIT.

### 14.5. Retry và idempotency

Nếu event được thử lại 3 lần và lần cuối thành công:
- `attempt_count=3`, `attempt_error_count=2` là số liệu ở **lớp attempt**.
- `logical_events_succeeded=1` chỉ đúng nếu có cơ chế theo dõi kết quả cuối theo `eventId` (chẳng hạn outbox consumer).
- Không cộng ba attempts và gọi đó là ba domain events riêng.
- Nếu retry tạo ra cùng một exception rồi error handler còn đếm lỗi lần nữa, cần kiểm tra không double-count.

## 15. Sai lầm thường gặp

1. **Dùng duration của `publishEvent` làm duration của async listener:** hai ranh giới khác nhau.
2. **Không ghi Timer khi exception:** đồ thị latency đẹp giả vì thiếu các lần xử lý thất bại.
3. **Chỉ đo lỗi ở publisher:** bỏ sót lỗi listener chạy async hoặc lỗi bị ErrorHandler suppress.
4. **Đếm lỗi hai lần tại listener và ErrorHandler:** báo cáo error rate bị thổi phồng.
5. **Dùng `eventId`, `orderId` hay `correlationId` làm metric tags:** gây nổ cardinality.
6. **Chỉ dùng average latency:** che p95/p99 và tình trạng tail latency.
7. **Giả định Micrometer core tự export endpoint:** cần registry, exporter/binder/Actuator phù hợp.
8. **Bật histogram mọi nơi:** tăng số time series/bộ nhớ/chí phí mà chưa có SLO.
9. **Không tách queue wait với listener execution:** bỏ sót nghẽn pool.
10. **Coi callback AFTER_COMMIT lỗi là transaction DB rollback:** commit gốc đã hoàn tất.
11. **Cho rằng một retry là một event nghiệp vụ mới:** metric attempts và logical outcome bị nhầm.
12. **Không phân loại cancellation/timeouts:** reactive chain/async task có outcome khác thành công/lỗi RuntimeException.
13. **Bỏ log và tracing vì đã có metrics:** không có ID chi tiết để điều tra một event cụ thể.
14. **Cho rằng metrics tự đem lại reliability:** không thay thế outbox, retry, DLQ hoặc idempotency.

## 16. Checklist triển khai

- [ ] Đã định nghĩa rõ `publishEvent latency`, `listener duration` và `end-to-end duration` là ba metric khác nhau.
- [ ] Mỗi listener quan trọng có Timer, gồm cả nhánh exception, và metric error có hợp đồng đếm nhất quán.
- [ ] Outcome success/error/cancel/rejected được phân loại đúng với execution model.
- [ ] Không dùng identifiers động, exception messages hoặc dữ liệu PII làm metric tag.
- [ ] Listener async được đo tại điểm thực thi, không suy ra outcome từ publisher.
- [ ] Queue wait, executor backlog và rejection được quan sát nếu sử dụng thread pool.
- [ ] Transactional listener đo đúng phase; failure sau commit không bị nhầm với rollback DB.
- [ ] Có histogram/p95/p99 ở những handler cần SLO, không bật mọi nơi theo thói quen.
- [ ] Các alert có cửa sổ đo, traffic floor và ngưỡng có ý nghĩa với nghiệp vụ.
- [ ] Correlation/event ID nằm ở log/trace để điều tra, không ở metric tags.
- [ ] Unit/integration tests xác minh timer count, error count, exact grouping, rollback và retry.
- [ ] Với event bắt buộc giao bền vững, có outbox/queue và theo dõi delivery outcome thực.

**Ghi nhớ:** đo **một lần listener invocation** bằng Micrometer `Timer` ở ranh giới thực thi và ghi lỗi bằng `Counter` hoặc outcome tag có kiểm soát. `publishEvent()` chỉ đo dispatch/handoff theo cấu hình, không bảo đảm async listener đã hoàn thành. Kết hợp metrics với log/tracing, tránh high-cardinality tags và tách commit DB khỏi kết quả side effect để quan sát hệ thống đáng tin cậy.

## Tài liệu tham khảo

- [Spring Framework 6.1.21 — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.1.21 — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Micrometer Concepts — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Concepts — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer Concepts — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer Concepts — Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
