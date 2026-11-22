# Ghi nhận metric cho listener trong Spring Framework Application Events

Khi sử dụng **Spring Framework Application Events**, một lời gọi `ApplicationEventPublisher.publishEvent(...)` có thể kích hoạt một hoặc nhiều `@EventListener`. Nếu một listener chậm, lỗi liên tục hoặc tạo tồn đọng công việc, chỉ nhìn log publisher rất khó biết vấn đề nằm ở đâu. **Ghi nhận metric cho listener** giúp đo được **số lần xử lý, tỷ lệ thành công/thất bại, thời gian thực thi, công việc đang chạy, hàng đợi và retry** theo cách có thể tổng hợp, cảnh báo và kiểm thử.

Một điểm cần nhớ trước khi triển khai:

> **Spring Framework không tự tạo Micrometer Observation cho mọi lời gọi `@EventListener`.** Muốn có metric riêng cho từng listener, ứng dụng phải thêm instrumentation (chẳng hạn `MeterRegistry`/`Timer`/`Counter` hoặc `ObservationRegistry`) ở đúng vị trí. Bật Actuator không tự biến tất cả Spring Application Events thành bộ số liệu listener.

Bài thực hành này dùng **Spring Framework 6.2**, **Micrometer**, Java 17+ và một chương trình chạy được để ghi metric cho listener đồng bộ. Sau đó mở rộng sang Spring Boot Actuator/Prometheus, `@Async`, `@TransactionalEventListener`, các phương pháp kiểm thử và tiêu chí thiết kế dashboard.

## 1. Xác định điều cần đo trước khi viết code

Một luồng event trong request có các mốc riêng:

```text
HTTP request / use case
      |
      +-- publishEvent(OrderPlaced) -----> publish duration
               |
               +-- Listener A bắt đầu --> listener processing duration
               |                              success / failure
               |
               +-- Listener B bắt đầu --> listener processing duration
               |                              success / failure
               |
               +-- listener async được submit --> queue waiting time
                                                    |
                                                    +-- worker start
                                                    +-- worker complete
      |
      +-- transaction commit / rollback
```

**Các trạng thái không đồng nghĩa nhau:**

| Mốc / tín hiệu | Đã chứng minh điều gì? | Chưa chứng minh điều gì? |
| --- | --- | --- |
| `publishEvent` được gọi | Publisher đã yêu cầu Spring phát event | Listener xử lý thành công |
| `publishEvent` trả về | Đường gọi publisher hoàn tất theo cấu hình hiện tại | Mọi listener async đã chạy xong |
| Listener `started` | Một lần thực thi listener bắt đầu | Event đã được xử lý xong |
| Listener `completed` thành công | Một attempt hoàn tất không ném lỗi | Transaction nghiệp vụ đã commit hoặc side effect bên ngoài đã giao |
| Transaction `AFTER_COMMIT` được kích hoạt | Transaction nguồn đã commit | Callback sau commit đã gửi thông báo thành công |
| Message đã được gửi đến broker | Broker/producer xác nhận theo hợp đồng | Consumer phía ngoài đã hoàn tất nghiệp vụ |

Trong multicaster **đồng bộ mặc định**, thời gian gọi `publishEvent(...)` bao gồm thời gian các listener đồng bộ, chứ không chỉ overhead dispatch của Spring. Nếu listener có `@Async` hoặc một custom multicaster dùng executor, thời gian publish thường chỉ phản ánh bước submit/dispatch, không phải tổng thời gian xử lý trên worker.

Do đó, một dashboard tốt cần đo **vị trí thực thi công việc**, không chỉ đo API phát event.

## 2. Những metric phù hợp cho listener

### 2.1. Counter: đếm số lần xử lý và lỗi

`Counter` là một số đếm **chỉ tăng** trong registry khi chương trình hoạt động. Ví dụ thiết kế:

```text
app.event.listener.completed{event.type="OrderPlaced",
                             listener="InvoiceProjection",
                             outcome="success"} = 120

app.event.listener.completed{event.type="OrderPlaced",
                             listener="InvoiceProjection",
                             outcome="error"} = 5
```

Các số liệu này chỉ **minh họa**. Nếu ứng dụng restart, counter cục bộ có thể được tạo lại; backend time series thường tính **rate/increase** theo thời gian và xử lý reset theo cơ chế riêng.

Counter nên tăng **khi một attempt hoàn thành**, không tăng vô điều kiện ở đầu method rồi gọi là “processed successfully”. Nếu muốn đo event đã bắt đầu, dùng một metric `started` riêng, hoặc đo in-flight và completion thích hợp.

Đừng gọi `counter.increment()` cả trong `catch` và `finally` cho cùng một failure: như vậy sẽ đếm đôi.

### 2.2. Timer: thời gian một lần xử lý

`Timer` đo **duration** của các thao tác hoàn tất, đồng thời có sẵn những thống kê như `count` và `totalTime`. Trong Micrometer, `Timer.Sample.start(registry)` ghi thời điểm bắt đầu bằng clock của registry, và `sample.stop(timer)` ghi duration vào timer đã chọn.

```java
Timer.Sample sample = Timer.start(meterRegistry);
try {
    doWork();
} finally {
    sample.stop(timer);
}
```

Đây là **mã minh họa**, cần bean `meterRegistry`, meter `timer` và method `doWork`. `finally` đảm bảo metric vẫn được ghi khi work ném exception. Nếu muốn tách duration thành công và lỗi, chọn timer theo kết quả **tại thời điểm stop**, ví dụ `outcome="success"` hoặc `outcome="error"`.

**Không dùng `Counter` để đo thời gian** và không dùng `DistributionSummary` khi ý nghĩa của số đo là duration: `Timer` có biểu diễn đơn vị thời gian phù hợp. Không tự gắn timestamp tuyệt đối như một duration metric.

### 2.3. Gauge: công việc đang chạy hoặc backlog

`Gauge` biểu diễn **giá trị hiện tại**: số listener đang thực thi, kích thước queue, số outbox pending, lượng job chưa xử lý. Thường nó được lấy từ đối tượng/nguồn có trạng thái:

```java
// Ví dụ khung: AtomicInteger inFlight được giữ lâu dài bởi một Spring bean.
Gauge.builder("app.event.listener.inflight", inFlight, AtomicInteger::get)
        .tag("listener", "InvoiceProjection")
        .register(meterRegistry);
```

Đây là **mã minh họa**, cần `Gauge`, `AtomicInteger` và `meterRegistry`. Micrometer gauge thường giữ **weak reference** tới state object, nên đối tượng `inFlight` phải được bean giữ strong reference; nếu đối tượng bị GC, metric có thể biến mất/ra NaN.

Một `Gauge` không thay thế `Counter` vì nó không lưu toàn bộ số lần event đã chạy. Với backlog từ broker/outbox, **đọc state thật từ hàng đợi** thay vì tăng/giảm một biến cục bộ và giả định biến đó luôn đúng sau crash.

### 2.4. LongTaskTimer: việc dài đang xử lý

`LongTaskTimer` hữu ích khi muốn biết **có bao nhiêu tác vụ dài đang chạy và tổng thời gian của chúng**, ví dụ consumer xử lý file lớn, batch projection hay workflow dài. `Timer` thường ghi nhận khi tác vụ **kết thúc**; vì vậy một task bị treo có thể chưa xuất hiện trong duration histogram.

Không cần đặt `LongTaskTimer` cho tất cả listener vài mili-giây. Instrument đúng nơi có tác vụ chạy lâu và chi phí quan sát chấp nhận được.

### 2.5. Metric nào nên dùng?

| Câu hỏi vận hành | Metric thích hợp | Ghi chú |
| --- | --- | --- |
| Listener hoàn thành bao nhiêu lần? | `Counter` theo outcome | Không nhầm attempt với logical event |
| Tỷ lệ lỗi trong 5 phút? | Rate/increase của error counter chia tổng | Xác định mẫu số và thời gian |
| Listener xử lý mất bao lâu? | `Timer` duration histogram/p95/p99 | Cần histogram/percentile config nếu muốn percentile |
| Có bao nhiêu listener đang chạy? | `Gauge`/`LongTaskTimer` | Không dùng sum counter để suy đoán |
| Executor có đầy không? | Queue depth, active threads, task rejections | Không tự được cung cấp chỉ từ `@EventListener` |
| Event bị kẹt sau commit? | Outbox pending age, retry backlog, delivery latency | Đo ở worker/broker, không chỉ producer |
| Một logical event bị thử lại mấy lần? | Counter attempts và terminal success riêng | Stable event ID để correlation ở logs/traces |

## 3. Thiết kế tags: low cardinality trước tiên

Metric có ích khi có thể lọc theo loại event, listener và outcome, nhưng mỗi tổ hợp tags có thể tạo một time series riêng. Cần giới hạn chặt **cardinality**.

**Tags low-cardinality nên dùng:**

- `event.type`: tên **tập hữu hạn** như `OrderPlaced`, `InvoiceIssued`.
- `listener`: tên logic ổn định như `InvoiceProjection` hoặc `EmailNotification`.
- `outcome`: `success`, `error`, có thể thêm `cancelled` khi thật sự cần.
- `error.category`: `validation`, `timeout`, `database`, `external`; lấy từ classifier có số giá trị hữu hạn.
- `phase`: `sync`, `after_commit` hoặc `async_worker` khi đó là thông tin quan trọng.

**Không nên dùng làm metric tag:**

- `eventId`, `orderId`, `customerId` hoặc traceId.
- Email, username, IP nếu số lượng không được giới hạn, token/credential.
- URL nguyên vẹn chứa ID, exception message tự do hoặc payload serialised.
- Tên listener tạo động dựa trên instance/user/tenant không được giới hạn.

Ví dụ: 6 event types × 8 listeners × 3 outcomes = **144 tổ hợp tag** trước khi tính thêm error category, environment hoặc histogram buckets. Nếu thêm `orderId` có hàng triệu giá trị, metrics backend có thể bị **nổ số lượng time series**, tăng RAM và chi phí lưu trữ.

**Event ID vẫn quan trọng cho truy vết**, nhưng nên đưa vào **structured logs/traces (high-cardinality metadata)**, không phải low-cardinality metric tags. Với Spring Observations, `highCardinalityKeyValue(...)` có ý nghĩa khác `lowCardinalityKeyValue(...)`; không chuyển tùy tiện dữ liệu high-cardinality thành nhãn meter.

## 4. Ví dụ Java 17+ hoàn chỉnh: Timer và Counter trong @EventListener

Ví dụ dùng Spring Framework **6.2.9** và Micrometer Core **1.14.9**. Không cần Spring Boot, HTTP server hay Prometheus; `SimpleMeterRegistry` lưu số đo trong bộ nhớ cho mục đích học tập/test.

Ta phát hai `InvoiceIssued`:

- `id=101`: listener xử lý thành công.
- `id=102`: listener ném `IllegalStateException` để mô phỏng projection lỗi; nó vẫn ghi metric **failure** và **timer** ở `finally`, rồi truyền nguyên nhân về publisher.

Vì multicaster mặc định đồng bộ, output có thứ tự rõ ràng. Chương trình chỉ in **counts**, không in duration nanosecond không ổn định.

### 4.1. Cấu trúc thư mục

```text
event-listener-metrics-demo/
├── pom.xml
└── src/main/java/example/EventListenerMetricsDemo.java
```

### 4.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>event-listener-metrics-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.14.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.EventListenerMetricsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.3. src/main/java/example/EventListenerMetricsDemo.java

```java
package example;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventListenerMetricsDemo {

    public record InvoiceIssued(long id) {}

    public static final class InvoiceProjectionListener {
        private final MeterRegistry registry;

        // Đăng ký các meter với bộ tags hữu hạn ngay khi tạo bean.
        private final Counter successCounter;
        private final Counter errorCounter;
        private final Timer successTimer;
        private final Timer errorTimer;

        public InvoiceProjectionListener(MeterRegistry registry) {
            this.registry = registry;
            this.successCounter = newCounter(registry, "success");
            this.errorCounter = newCounter(registry, "error");
            this.successTimer = newTimer(registry, "success");
            this.errorTimer = newTimer(registry, "error");
        }

        private static Counter newCounter(
                MeterRegistry registry, String outcome) {
            return Counter.builder("demo.event.listener.calls")
                    .description("Completed listener attempts")
                    .tags(
                            "event.type", "InvoiceIssued",
                            "listener", "InvoiceProjection",
                            "outcome", outcome)
                    .register(registry);
        }

        private static Timer newTimer(
                MeterRegistry registry, String outcome) {
            return Timer.builder("demo.event.listener.duration")
                    .description("Execution duration of listener attempts")
                    .tags(
                            "event.type", "InvoiceIssued",
                            "listener", "InvoiceProjection",
                            "outcome", outcome)
                    .register(registry);
        }

        @EventListener
        public void onInvoiceIssued(InvoiceIssued event) {
            Timer.Sample sample = Timer.start(registry);
            boolean success = false;

            try {
                if (event.id() == 102L) {
                    System.out.println(
                            "listener: failed invoice=" + event.id());
                    throw new IllegalStateException(
                            "projection unavailable");
                }

                System.out.println(
                        "listener: processed invoice=" + event.id());
                success = true;
            } finally {
                // finally chạy cả khi listener ném exception.
                sample.stop(success ? successTimer : errorTimer);
                if (success) {
                    successCounter.increment();
                } else {
                    errorCounter.increment();
                }
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfig {
        @Bean
        SimpleMeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        InvoiceProjectionListener listener(SimpleMeterRegistry meterRegistry) {
            return new InvoiceProjectionListener(meterRegistry);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DemoConfig.class)) {

            context.publishEvent(new InvoiceIssued(101L));

            try {
                context.publishEvent(new InvoiceIssued(102L));
            } catch (IllegalStateException ex) {
                System.out.println(
                        "publisher: caught " + ex.getMessage());
            }

            MeterRegistry registry =
                    context.getBean(SimpleMeterRegistry.class);

            long successCalls = Math.round(registry
                    .get("demo.event.listener.calls")
                    .tag("outcome", "success")
                    .counter().count());

            long errorCalls = Math.round(registry
                    .get("demo.event.listener.calls")
                    .tag("outcome", "error")
                    .counter().count());

            long successDurations = registry
                    .get("demo.event.listener.duration")
                    .tag("outcome", "success")
                    .timer().count();

            long errorDurations = registry
                    .get("demo.event.listener.duration")
                    .tag("outcome", "error")
                    .timer().count();

            System.out.println(
                    "metrics: success=" + successCalls
                    + " error=" + errorCalls
                    + " timer.success=" + successDurations
                    + " timer.error=" + errorDurations);
        }
    }
}
```

Chạy trong thư mục dự án bằng **JDK 17+** và Maven:

```bash
mvn -q compile exec:java
```

Các dòng **do chương trình** in ra, theo thứ tự (không kể log của Spring/Maven):

```text
listener: processed invoice=101
listener: failed invoice=102
publisher: caught projection unavailable
metrics: success=1 error=1 timer.success=1 timer.error=1
```

### 4.4. Giải thích cơ chế và kết quả

1. `DemoConfig` khai báo một `SimpleMeterRegistry` và một `InvoiceProjectionListener` Spring bean. Spring phát hiện `@EventListener` khi `ApplicationContext` được khởi tạo.
2. `context.publishEvent(new InvoiceIssued(101L))` dùng multicaster đồng bộ mặc định; listener in dòng thành công, biến `success` là `true` và khối `finally` ghi đúng **một sample timer** cùng **một lần tăng counter** có `outcome=success`.
3. Với `id=102`, listener in dòng thất bại và ném `IllegalStateException`. Khối `finally` vẫn chạy, ghi `errorTimer` và `errorCounter`; exception **không bị nuốt**.
4. Publisher bắt được lỗi `projection unavailable` vì listener đang chạy đồng bộ và không có `ErrorHandler` suppress exception.
5. `SimpleMeterRegistry` trả lại hai counters/timers có tags `outcome=success/error`. Count cho từng nhánh đều bằng 1; timer `count` là số **completed samples**, không phải số mili-giây.
6. Duration thực tế có thể khác giữa các lần chạy. Chúng ta **không in nó** để stdout không phụ thuộc vào tốc độ máy.
7. Meter được **đăng ký một lần trong constructor**, tránh tạo builder và tìm meter mỗi khi event đến. Đó là một tối ưu tốt cho listener xử lý tần suất cao khi tags là hữu hạn.

### 4.5. Vì sao ví dụ không cần exporter?

`SimpleMeterRegistry` là registry **in-memory** dùng cho demo/test. Các số liệu ở đây **không tự gửi tới Prometheus**. Khi triển khai Spring Boot, nên inject `MeterRegistry` được Boot quản lý thay vì tự tạo `SimpleMeterRegistry` cho production; exporter backend và Actuator sẽ được cấu hình riêng.

Ví dụ cũng **không mở database transaction**, không dùng `@Async` và không triển khai retry. Vì thế nó chứng minh cách đo **execution outcome** trên listener đồng bộ, chứ không chứng minh commit/rollback hoặc event delivery tới hệ thống ngoài.

### 4.6. Thực hành mở rộng

Hãy sửa điều kiện lỗi:

```java
if (event.id() == 102L) {
    throw new IllegalStateException("projection unavailable");
}
```

Rồi thay event `102` bằng `103`. Bạn sẽ thấy tăng thêm một sample success thay vì failure, với giả định publisher gọi thêm một lần. Không chỉnh outcome metric bằng tay trước khi logic chạy; metric phải phản ánh **đường thực thi thật**.

Thử xóa phần `finally` để thấy metric có thể mất trên đường exception. Sau đó khôi phục `finally` và xác nhận cả timer/counter lỗi đều được ghi. Đây là bài tập làm rõ vì sao phải instrument đủ success và failure path.

## 5. Từ meter trực tiếp đến Micrometer Observation

Micrometer cung cấp hai hướng phù hợp:

**Hướng A — Instrument metrics trực tiếp:** dùng `MeterRegistry`, `Timer`, `Counter` như ví dụ. Ưu điểm là ít lớp trung gian và tên meter/tags rõ ràng; phù hợp khi chỉ cần metrics.

**Hướng B — Instrument một `Observation`:** dùng `ObservationRegistry`/`Observation` để có một khái niệm operation thống nhất. Tùy handlers được cấu hình, observation có thể tạo **metrics và traces** mà không phải viết một đoạn code cho mỗi backend.

Ví dụ một listener trong ứng dụng **Spring Boot có ObservationRegistry**:

```java
@Component
public class CustomerProjectionListener {
    private final ObservationRegistry observationRegistry;
    private final CustomerProjectionService projection;

    public CustomerProjectionListener(
            ObservationRegistry observationRegistry,
            CustomerProjectionService projection) {
        this.observationRegistry = observationRegistry;
        this.projection = projection;
    }

    @EventListener
    public void onCustomerChanged(CustomerChanged event) {
        Observation.createNotStarted(
                        "application.event.listener",
                        observationRegistry)
                .lowCardinalityKeyValue("event.type", "CustomerChanged")
                .lowCardinalityKeyValue("listener", "CustomerProjection")
                .highCardinalityKeyValue("event.id", event.eventId())
                .observe(() -> projection.update(event));
    }
}
```

Đây là **mã tích hợp minh họa**, không phải file chạy cùng ví dụ `EventListenerMetricsDemo`; các kiểu `CustomerChanged`, `CustomerProjectionService`, imports `@Component`, `Observation` và `ObservationRegistry` phải do ứng dụng cung cấp.

`observe(...)` mở vòng đời observation quanh code xử lý, ghi nhận lỗi và đóng scope phù hợp. Nhưng để có meter, `ObservationRegistry` phải có **ObservationHandler** tạo metrics, ví dụ `DefaultMeterObservationHandler`. Spring Boot Actuator có thể auto-configure những handler cần thiết theo dependencies; ứng dụng Spring Framework thuần phải tự thiết lập khi dùng Observation thay cho MeterRegistry trực tiếp.

**Không dùng cả A và B để đo cùng một operation với cùng tên/tags mà không có thiết kế rõ ràng.** Nếu Observation đã sinh Timer, thêm Timer thủ công trùng có thể làm dashboard đếm quá số lần và báo latency sai.

### 5.1. Tự cấu hình metrics cho Observation trong Spring thuần

Mã **minh họa riêng** (cần dependencies `micrometer-observation` và `micrometer-core`, imports đúng):

```java
SimpleMeterRegistry meters = new SimpleMeterRegistry();
ObservationRegistry observations = ObservationRegistry.create();

observations.observationConfig().observationHandler(
        new DefaultMeterObservationHandler(meters));

Observation.createNotStarted("application.event.listener", observations)
        .lowCardinalityKeyValue("event.type", "OrderPlaced")
        .lowCardinalityKeyValue("listener", "OrderListener")
        .observe(() -> handleOrder());
```

Khi có handler này, một observation được kết thúc có thể đóng góp **timer** vào MeterRegistry. Đoạn này không phải app đầy đủ; `handleOrder()` chỉ là placeholder cho công việc ứng dụng và phải được hiện thực ở project thực tế.

### 5.2. @Observed và AOP

Micrometer có `@Observed`. Tùy cấu hình Spring Boot/AOP phiên bản sử dụng, bạn có thể instrument phương thức thông qua `ObservedAspect` hoặc tính năng annotation observation được bật. Không được giả định chỉ viết `@Observed` trên `@EventListener` là chắc chắn nhận metric.

Ví dụ **minh họa tích hợp**:

```java
@Observed(
        name = "application.event.listener",
        lowCardinalityKeyValues = {
            "event.type", "OrderPlaced",
            "listener", "Projection"
        })
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    projectionService.apply(event);
}
```

Để có hiệu lực, phải xác minh:

- Spring AOP/AspectJ và `ObservedAspect` có được đăng ký theo cấu hình không?
- Spring thực sự gọi method qua **proxy** nào; có self-invocation bỏ qua advice không?
- Nếu dùng custom observation thủ công, có **double instrumentation** không?
- Tags từ annotation có **cardinality bounded** không?
- Tests có thấy meter và số samples chính xác không?

Với Spring Boot, property `management.observations.annotations.enabled=true` được hỗ trợ trong các phiên bản tương ứng nhưng còn phụ thuộc dependency/proxy infrastructure; hãy theo đúng docs của phiên bản ứng dụng.

## 6. Tích hợp với Spring Boot Actuator và Prometheus

Trong ứng dụng Spring Boot, thường thêm:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
```

Đây là **dependency fragment** cho một project Spring Boot đã có dependency management; không phải `pom.xml` độc lập. Boot sẽ quản lý phiên bản Micrometer theo BOM phù hợp.

Cấu hình gợi ý trong `application.properties`:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.distribution.percentiles-histogram.application.event.listener=true
management.metrics.distribution.slo.application.event.listener=100ms,500ms,1s
```

Các tên `application.event.listener` ở đây giả định ứng dụng dùng **Observation/TIMER với đúng tên đó**; ví dụ `EventListenerMetricsDemo` phía trên dùng meter riêng `demo.event.listener.duration`, do đó **không được sao chép cấu hình SLO này rồi chờ nó tác động vào tên khác**. Khi dùng Timer trực tiếp, thay suffix properties bằng **tên meter thực sự**.

Bạn có thể kiểm tra:

- `/actuator/metrics`: danh sách meter đã được ghi. Endpoint cần được expose đúng và không mặc định công khai.
- `/actuator/metrics/application.event.listener` hoặc `/actuator/metrics/demo.event.listener.duration` tùy metric trong ứng dụng.
- `/actuator/prometheus`: dữ liệu ở định dạng Prometheus nếu có `micrometer-registry-prometheus` và endpoint được expose.
- Dashboard Grafana/Prometheus: request rate, error ratio và histogram quantiles theo listener.

**Bảo mật endpoints:** Actuator có thể tiết lộ tên hệ thống, tags, runtime details. Không công khai endpoint nhạy cảm ra Internet để debug. Đặt authentication/authorization, giới hạn network và cấu hình scraping phù hợp.

### 6.1. Đặt tên metric nhất quán

Ví dụ convention cho **metric do ứng dụng tự đặt**, không phải số liệu Spring tự sinh:

| Meter name | Loại | Ý nghĩa |
| --- | --- | --- |
| `app.event.listener.duration` | Timer | Duration của mỗi attempt listener |
| `app.event.listener.completed` | Counter | Số attempts hoàn tất theo outcome |
| `app.event.listener.inflight` | Gauge | Số listener đang xử lý |
| `app.event.listener.queue.depth` | Gauge | Backlog trong executor được quan sát |
| `app.event.listener.rejected` | Counter | Số task bị executor từ chối |
| `app.event.delivery.end_to_end` | Timer | Thời gian từ event phát/commit đến xử lý cuối cùng |
| `app.event.retry.attempts` | Counter | Số lần thử trên worker/broker |
| `app.event.outbox.pending` | Gauge | Số outbox events đang chờ |

Nếu dùng Micrometer Observation với name `application.event.listener`, tên meter có thể dựa trên name đó; một số registry/exporter **biến đổi tên** (ví dụ dấu chấm thành gạch dưới, suffix units). Hãy truy vấn tên trong `/actuator/metrics` theo **tên Micrometer**, và xác minh tên thực tế khi xuất Prometheus thay vì đoán.

### 6.2. Percentiles, histograms và SLO

Để xem p95/p99 duration, cần hiểu:

- `Timer.count`/`totalTime` không tự biến thành p95/p99 trong mọi registry.
- Client-side percentiles có thể hữu ích cho instance đơn, nhưng thường **không tổng hợp chính xác** giữa instances.
- Histogram buckets cho phép backend như Prometheus tính **ước lượng quantile tổng hợp** bằng cơ chế `histogram_quantile`, tùy phân bố buckets và retention.
- SLO buckets tại 100 ms/500 ms/1 s giúp biết tỷ lệ attempts vượt ngưỡng cụ thể.
- Histogram làm tăng số time series; chỉ bật cho những listener/metrics quan trọng.
- Với số samples quá ít, p99 có thể không ổn định. Không kết luận “listener khỏe” chỉ vì không có mẫu lỗi trong vài phút.

Đừng so sánh trực tiếp p95 của **thời gian xử lý listener** với p95 của **end-to-end event latency** khi có async/queue. Chúng đo hai đại lượng khác nhau.

### 6.3. PromQL minh họa

Giả định exporter tạo tên metrics `app_event_listener_completed_total` với các nhãn đã cấu hình:

```promql
sum by (listener) (
  rate(app_event_listener_completed_total{outcome="error"}[5m])
)
/
clamp_min(
  sum by (listener) (
    rate(app_event_listener_completed_total[5m])
  ),
  1e-9
)
```

Đây là **PromQL minh họa**, tên metric tùy naming convention/exporter. Nếu denominator bằng 0, biểu thức phụ thuộc cách tính `clamp_min` và có thể cho 0 khi không có traffic; dashboard nên hiển thị thêm throughput và xử lý khoảng “không có data”. Không dùng ratio này một mình để suy ra availability khi sample volume thấp.

Nếu có histogram buckets cho duration, có thể tính p95:

```promql
histogram_quantile(
  0.95,
  sum by (le, listener) (
    rate(app_event_listener_duration_seconds_bucket[5m])
  )
)
```

Điều kiện: metrics histogram thực sự được export dưới tên đó và labels `le`/`listener` tồn tại. Đây không phải query chạy được với `SimpleMeterRegistry` của demo (nó không có Prometheus exporter).

## 7. Event listener đồng bộ: metric đo ở đâu và ảnh hưởng gì đến transaction?

Với `SimpleApplicationEventMulticaster` mặc định, listener được gọi **đồng bộ trên thread publisher**. Ví dụ:

```text
HTTP Request Span
  |
  +-- @Transactional OrderService
        |
        +-- publishEvent(OrderPlaced)
              |
              +-- AuditListener  [Timer A]
              +-- EmailListener  [Timer B]
              +-- Projection    [Timer C]
        |
        +-- COMMIT / ROLLBACK
```

Trong cấu hình này:

- Duration từng listener thường **nằm trong tổng thời gian request phải chờ**.
- Nếu listener làm I/O chậm bên trong transaction, nó có thể kéo dài thời gian giữ DB connection/lock và tăng p95/p99 của các request khác.
- Nếu listener ném `RuntimeException` và không bị suppress, lỗi có thể truyền về publisher và làm transaction rollback theo policy.
- `Timer` có `outcome="success"` ở cuối listener **không chứng minh transaction đã commit**; transaction có thể rollback sau khi listener đã trả về.
- Nếu một listener ném exception khiến multicast dừng sớm, các listener sau có thể **không có sample** vì chúng chưa được gọi. Không interpret sample missing thành “0ms success”.

Một số tình huống có ý nghĩa nghiệp vụ quan trọng nên dùng một service call tường minh thay vì giấu dependency đồng bộ trong event listener. Metrics giúp thấy chi phí, nhưng không tự giải quyết transaction coupling.

## 8. Async và executor: metric phải được đo trên worker

Một listener:

```java
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationService.send(event);
}
```

là **mã minh họa tích hợp**, cần `@EnableAsync`, executor và các kiểu ứng dụng. Khi `@Async` hoạt động, code xử lý chạy trên thread khác. Nếu đặt `Timer` **chỉ quanh `publishEvent(...)`**, số đo có thể chỉ bao gồm **scheduling/submit**, không bao gồm thời gian `notificationService.send`.

Hãy instrument **bên trong listener body** trên worker:

```text
event published (T0)
      |
      +-- submit task (T1)
              |
              +-- task waits in executor queue
                         |
                         +-- worker start (T2)
                                 |
                                 +-- listener handling
                                 |
                                 +-- worker finish (T3)

publish duration      = T1 - T0 (xấp xỉ)
queue waiting time    = T2 - T1
listener duration     = T3 - T2
event completion lag  = T3 - T0
```

Đây là mô hình thời gian khái niệm. Trong một JVM có thể dùng `System.nanoTime()` cho **durations** trong cùng time source; timestamp `Instant`/UTC thích hợp cho sự kiện phải được truyền qua process nhưng có sai số do đồng hồ hệ thống. Với broker hoặc nhiều hosts, event completion lag cần hiểu clock skew và xác định start timestamp có hợp đồng rõ.

### 8.1. Metric ở ThreadPoolTaskExecutor

Trong ứng dụng có `ThreadPoolTaskExecutor`, theo dõi:

- Số threads đang active, pool size, queue depth.
- Số task bị reject.
- Thời gian chờ trong queue khi cần độ trễ end-to-end.
- Consumer/worker thành công, thất bại, timeout.
- Shutdown backlog khi ứng dụng dừng.

Các số đo của executor không tự động tương đương `listener completed`: một task có thể bị reject trước khi method bắt đầu. Nếu yêu cầu **không mất event**, in-memory executor không đủ; cân nhắc durable queue hoặc Transactional Outbox.

### 8.2. ThreadLocal, MDC và tracing context

Thread khác có thể không có context/trace ID của publisher. Với Spring, có thể dùng `ContextPropagatingTaskDecorator` và thư viện Micrometer Context Propagation:

```java
@Bean("eventExecutor")
ThreadPoolTaskExecutor eventExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator());
    executor.initialize();
    return executor;
}
```

Đây là **cấu hình tích hợp minh họa**, không thuộc demo Maven mục 4. Cần imports và dependency phù hợp; context accessors/tracing handlers phải được cấu hình. TaskDecorator giúp truyền context thích hợp nhưng **không tự mang database transaction của publisher sang worker** và không cung cấp durable delivery.

**Metric của listener không nhất thiết cần trace context**, vì meter tags được đăng ký rõ ràng tại listener. Nhưng để đi từ một spike error rate đến **event ID gây lỗi**, structured logging/tracing với correlation ID là hữu ích.

### 8.3. Chọn metric error cho async

Với `@Async` trả về `void`, exception có thể được xử lý qua `AsyncUncaughtExceptionHandler` và không lan về publisher. Vì vậy:

- Đặt `try/finally`/Observation quanh work **bên trong async listener**.
- Ghi `outcome=error` trước khi truyền lỗi cho async exception handling.
- Không tăng “success” ngay khi task được submit.
- Nếu caller quản lý `CompletableFuture`/`Future`, theo dõi terminal completion một cách phù hợp với API, không coi scheduler accepted là business success.
- Nếu queue bị reject, ghi metric **rejected** ở đường submit/exception handler, không đánh đồng với listener processing failure.

## 9. Transaction-bound events: trước commit và sau commit khác nhau

`@TransactionalEventListener` có các pha:

| Pha | Khi callback chạy | Diễn giải metric đúng |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước commit | Listener thành công chưa bảo đảm commit cuối cùng |
| `AFTER_COMMIT` | Sau commit thành công | Có thể đo side effect sau commit; failure không rollback transaction đã commit |
| `AFTER_ROLLBACK` | Sau rollback | Dùng để ghi nhận kết quả rollback, không phải business success |
| `AFTER_COMPLETION` | Sau commit hoặc rollback | Cần thêm outcome transaction nếu muốn phân biệt |

Ví dụ:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    Observation.createNotStarted(
                    "application.event.after_commit",
                    observationRegistry)
            .lowCardinalityKeyValue("event.type", "OrderPlaced")
            .lowCardinalityKeyValue("listener", "Notification")
            .observe(() -> notificationService.send(event));
}
```

Đây là **mã tích hợp minh họa**, yêu cầu các bean/import phù hợp. Nếu notification thất bại ở `AFTER_COMMIT`, transaction đơn hàng **vẫn đã commit**. Metric `outcome=error` phản ánh **notification attempt** chứ không phải transaction rollback.

Mặc định `@TransactionalEventListener(fallbackExecution = false)` **không chạy khi không có transaction phù hợp**. Vì thế có thể không có metric ở listener dù publisher đã gọi `publishEvent(...)`. Không tự sửa bằng cách bật `fallbackExecution=true` nếu nó làm thay đổi semantics nghiệp vụ.

Khi triển khai **reactive transactions**, transaction context nằm trong Reactor Context; không thể giả định ThreadLocal imperative giống transaction reactive. Cần đúng `TransactionalEventPublisher`/transaction-context contract khi dùng reactive transaction-bound events.

### Ghi metric cho commit outcome ở đâu?

Nếu bài toán hỏi “bao nhiêu đơn được commit?”, không thể chỉ đếm `@EventListener` xử lý thành công. Phải đo outcome tại **transaction boundary** hoặc từ nguồn nghiệp vụ đã commit (DB/outbox/CDC) có bảo đảm tương ứng.

Một lời gọi `publishEvent(...)` trong transaction có thể đã hoàn tất nhưng transaction bị rollback sau đó. Ngược lại, một listener `AFTER_COMMIT` có thể fail mà DB đã commit. Dashboard nên có hai nhóm metric riêng: **business commit** và **side effect processing**.

## 10. Retry: đếm attempts và logical event riêng

Giả sử một event `evt-42` được worker xử lý ba lần:

```text
evt-42 attempt 1 -> timeout
evt-42 attempt 2 -> timeout
evt-42 attempt 3 -> success
```

Nếu mỗi attempt tăng listener success/error counters, ta thấy:

```text
listener_attempts{outcome="error"}   += 2
listener_attempts{outcome="success"} += 1
logical_events_completed            += 1
```

Đây là **ý nghĩa dữ liệu minh họa**, không phải names do Spring tự tạo.

Đừng báo “đã xử lý ba events” chỉ vì có ba attempts. **Một logical event** có thể retry nhiều lần và cuối cùng thành công hoặc dead-letter. Với Kafka/RabbitMQ/outbox:

- Đo attempts tại **consumer worker**, không chỉ producer.
- Dùng `eventId` ổn định cho correlation logs/traces và idempotency; **không đưa eventId vào metric labels**.
- Theo dõi retry backlog, oldest pending age, dead-letter count, final success/exhaustion.
- Consumer phải idempotent vì có thể xử lý xong rồi crash trước ack/offset commit.
- Nếu retry thất bại dài, số attempts tăng nhưng số logical successes có thể đứng yên.

**Double counting:** Nếu instrumentation ở cả `@EventListener` và service retry wrapper, xác định metric nào đang đếm *attempt* và metric nào đếm *logical completion*. Đừng ghép chúng chung một tên rồi dùng làm tỷ lệ thành công của nghiệp vụ.

## 11. Thiết kế alert và SLO khả thi

Một dashboard nên trả lời:

1. **Throughput:** listeners hoàn tất bao nhiêu attempts/giây? Có đột ngột về 0 dù publisher còn hoạt động?
2. **Error rate:** tỷ lệ `error` tăng so với tổng attempts? Có đủ lưu lượng để đánh giá không?
3. **Latency:** p95/p99 thời gian xử lý listener, có vượt ngưỡng?
4. **Backlog:** với async/outbox/broker, tuổi event pending có vượt budget?
5. **Rejection/failure:** executor reject, publish-to-broker lỗi, retry exhaustion/DLT tăng?
6. **Business impact:** event completion end-to-end và transaction commit outcome có đúng SLA không?

Ví dụ SLO **giả định**, không phải chuẩn do Spring quy định:

```text
ProjectionListener:
  - 99% attempts thành công trong 5 phút, nếu có >=100 samples
  - p95 processing duration < 250 ms
  - queue oldest pending age < 5 s
  - zero silently dropped mandatory events
```

Một cảnh báo chỉ nhìn error rate có thể bỏ sót listener ngừng chạy (vì không có calls nào để tạo errors). Cần thêm **missing traffic** hoặc backlog/age alerts khi có một nguồn event độc lập để so sánh. Với listener chỉ chạy hiếm khi có nghiệp vụ, không đặt alert “không có event trong 1 phút” thiếu bối cảnh.

**Label và histogram budgets:** bật histogram cho mọi event type, mọi listener và mọi deployment có thể làm số time series tăng mạnh. Bắt đầu với các listener có SLO quan trọng, chọn buckets thích hợp với phân bố latency thật.

## 12. Kiểm thử metric: kiểm tra logic, không assert nanosecond tuyệt đối

Một lỗi instrumentation có thể không làm service fail, nhưng dashboard sai. Vì vậy cần test **trạng thái meter** và **hành vi nghiệp vụ**.

### 12.1. Unit test với SimpleMeterRegistry

Mục đích:

- Event thành công tạo đúng một counter success/timer success.
- Event lỗi tạo đúng một counter error/timer error; exception vẫn propagate theo hợp đồng.
- Không tạo metric tag theo event ID.
- Các metric được đăng ký với name/type/tags ổn định.
- Không đếm đôi nếu handler bị gọi lồng hoặc có retry.

Ví dụ **JUnit 5 snippet** tích hợp với class ở mục 4:

```java
@Test
void recordsFailureMetricsAndPropagates() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    EventListenerMetricsDemo.InvoiceProjectionListener listener =
            new EventListenerMetricsDemo.InvoiceProjectionListener(registry);

    assertThrows(IllegalStateException.class,
            () -> listener.onInvoiceIssued(
                    new EventListenerMetricsDemo.InvoiceIssued(102L)));

    assertEquals(1.0, registry
            .get("demo.event.listener.calls")
            .tag("outcome", "error").counter().count());

    assertEquals(1L, registry
            .get("demo.event.listener.duration")
            .tag("outcome", "error").timer().count());
}
```

Đây là **test snippet**, không nằm trong file `EventListenerMetricsDemo.java`. Cần dependency JUnit 5, `@Test` và static imports `assertThrows`/`assertEquals`. Test cho thấy **metric được ghi ngay cả khi code ném lỗi**, nhưng chưa chứng minh Spring đã đăng ký `@EventListener`.

### 12.2. Spring integration test

Dùng `@SpringJUnitConfig` hoặc `@SpringBootTest` để xác minh:

1. Bean listener thực sự có trong `ApplicationContext`.
2. Publish event đúng type làm method được gọi.
3. Counter/timer tăng đúng một sample, không bị duplicate do đăng ký nhiều bean.
4. Exception propagation đồng bộ/async đúng như thiết kế.
5. Với `@TransactionalEventListener`, kiểm tra phase ở transaction commit/rollback thật.
6. Với `@Async`, sử dụng `CountDownLatch`/test executor/completion để chờ; không dùng `Thread.sleep` để đoán event đã chạy.
7. Với Spring Boot metrics exporter, endpoint có metric tên đúng và tags đúng sau khi listener xử lý.

`@RecordApplicationEvents` của `spring-test` có thể kiểm tra **event publication**, nhưng không thay thế assertion rằng listener đã hoàn thành và meter được ghi. Nếu listener nằm ngoài component scan, event vẫn được publish trong context nhưng không có sample listener.

### 12.3. Test cardinality và dữ liệu nhạy cảm

Tạo một số event có `orderId` khác nhau, rồi assert danh sách meters/tags **không tăng theo số order IDs**. Đó là cách tìm bug cardinality sớm.

Cần kiểm tra:

- Không có password, access token, email khách hàng hoặc payload nhạy cảm trong tags.
- Các exception message động không biến thành tag value.
- `event.type` và `listener` đến từ tập được kiểm soát; không dùng input tự do.
- Mỗi event attempt đúng một completion signal; đường failure trong `finally` không che lỗi gốc.

## 13. Sai lầm phổ biến khi đo metric listener

**1. Chỉ đo `publishEvent(...)` rồi gọi đó là listener latency.**  
Đồng bộ thì nó gộp nhiều listeners; async thì nó có thể chỉ đo submit. Hãy đo trong từng listener/worker.

**2. Tin Spring tự có metrics cho mọi `@EventListener`.**  
Không theo mặc định. Cần manual MeterRegistry/Observation instrumentation hoặc một cơ chế được cấu hình rõ.

**3. Chỉ tăng success counter ngay khi listener bắt đầu.**  
Một lỗi xảy ra sau đó sẽ được báo là thành công. Chọn outcome khi việc xử lý đã hoàn tất.

**4. Quên `finally` khi đo thời gian.**  
Trên đường exception, timer không được stop, làm thống kê duration thiếu samples lỗi.

**5. Nuốt exception để metric `error` không xuất hiện.**  
Điều đó thay đổi transaction semantics và tạo báo cáo giả. Ghi metric rồi propagate khi nghiệp vụ yêu cầu.

**6. Gắn event ID hoặc customer ID vào metric labels.**  
Gây cardinality cao và có thể làm lộ dữ liệu. Dùng trace/log thay cho tags.

**7. Tạo tên metric động theo mỗi class instance hoặc mỗi request.**  
MeterRegistry tích lũy nhiều meter IDs; rất khó quản lý capacity. Dùng tên ổn định và finite tags.

**8. Đăng ký cùng meter quá nhiều lần trong hot path.**  
Registry có thể cache meter theo ID, nhưng tạo builder/lookup nhiều lần vẫn có overhead. Cache references khi tag set cố định.

**9. Dùng một Timer cho cả handler và broker delivery rồi diễn giải cùng latency.**  
Processing duration khác queue latency và end-to-end completion lag; đặt tên và đo riêng.

**10. Dùng `Gauge` để đếm số event trong lịch sử.**  
Gauge là snapshot trạng thái, không phải bộ đếm tích lũy. Dùng Counter.

**11. In duration chính xác rồi assert stdout bằng mili-giây cố định.**  
Thời gian phụ thuộc scheduler/JVM/GC. Chỉ assert counts, thứ tự hợp đồng đồng bộ, hoặc duration thuộc ngưỡng hợp lý.

**12. Thêm `@Observed` trong project chưa có AOP handler rồi cho rằng đã có metric.**  
Annotation có thể không được intercept. Kiểm tra real meter trong integration test.

**13. Đo trùng bằng @Observed và Timer thủ công.**  
Khi cả hai instrument cùng operation, có thể tạo duplicate samples/measurements. Một nơi nên sở hữu metric.

**14. Thấy timer success rồi khẳng định order commit.**  
Listener có thể chạy trước khi transaction rollback. Phải đo commit outcome ở boundary phù hợp.

**15. Không quan sát rejected tasks với listener async.**  
Task có thể chưa từng chạy nên không có timer/error listener. Cần metric ở đường submit/executor.

**16. Bật histogram cho mọi metric mọi tags.**  
Có thể tạo quá nhiều buckets/time series và tăng chi phí. Chọn listener có SLO rõ ràng.

**17. Chỉ xem averages.**  
Một số requests rất chậm có thể bị che bởi trung bình tốt. Kết hợp throughput, error rate và p95/p99.

**18. Bỏ qua missing-data alerts.**  
Listener ngừng được đăng ký/scan cũng có thể tạo **không còn metric**, không phải counter error tăng. Đối chiếu expected event volume và backlog nguồn.

## 14. Quy trình thực hành cho ứng dụng thật

Nếu một dự án dùng Spring Boot, có thể triển khai theo thứ tự:

1. **Chọn listener cần đo:** nghiệp vụ quan trọng, thường chậm, có retry hoặc side effect bên ngoài.
2. **Xác định metric contract:** tên ổn định, unit, type, allowed tags, ý nghĩa outcome và attempt.
3. **Đặt instrumentation đúng boundary:** bên trong listener thực thi, không chỉ quanh `publishEvent`; nếu async, đo trên worker.
4. **Cấu hình registry/exporter:** Spring Boot Actuator + backend phù hợp; không tự tạo SimpleMeterRegistry làm registry production ngầm nếu Boot đã quản lý.
5. **Không thay error semantics:** `finally`/Observation ghi cả failure; không swallow exception, không biến listener bắt buộc thành best-effort.
6. **Giới hạn cardinality:** kiểm tra meter IDs thực tế trước khi deploy; tránh tags lấy từ input động.
7. **Test bằng SimpleMeterRegistry/TestObservationRegistry:** thành công, lỗi, rollback/after-commit và async.
8. **Quan sát staging:** kiểm tra tên meter ở `/actuator/metrics`, số samples, tags và exporter transform.
9. **Tạo dashboard/alert:** error ratio, latency p95, no-traffic khi phù hợp, queue lag, rejection, retries.
10. **Load test:** xem instrumentation overhead, time series count, histogram size và tác động tới throughput.
11. **Kiểm tra reliability:** nếu event không được mất khi process chết, kết hợp outbox/broker và đo terminal delivery; metrics không thay thế durability.
12. **Định kỳ review:** dọn metric thừa, cập nhật SLO và bảo đảm không có tag chứa PII.

## 15. Câu hỏi tự kiểm tra

**1. Spring `@EventListener` có tự sinh metrics không?**  
Không. Spring Framework không tạo Observation cho từng lời gọi `@EventListener` theo mặc định. Ứng dụng cần instrumentation phù hợp.

**2. Đo thời gian thực thi một listener bằng loại meter nào?**  
`Timer`; có thể dùng `Timer.Sample.start(...)`, chọn timer ở cuối theo outcome và `stop(...)` trong `finally`.

**3. Vì sao `Timer.count()` không phải số mili-giây?**  
Vì đó là số samples đã được ghi. Duration được lấy qua `totalTime(...)`, `max(...)` hoặc histogram/percentiles khi cấu hình.

**4. Nên đưa `eventId` vào tag `event.type` hay `listener` không?**  
Không. Event ID có cardinality gần như không giới hạn; phù hợp hơn với structured logs/traces, không phải metric tag.

**5. Tại sao success metric của listener không chứng minh transaction đã commit?**  
Vì listener đồng bộ có thể chạy trong transaction chưa commit; transaction có thể rollback sau đó.

**6. Nếu `@Async` listener lỗi nhưng publisher trả về bình thường, nên đo lỗi ở đâu?**  
Trong body listener chạy trên worker và/hoặc completion/error handler, không dựa riêng vào publisher response.

**7. Có thể dùng `SimpleMeterRegistry` làm demo/test không cần Prometheus không?**  
Có. Nó giữ meters trong bộ nhớ để assert counts/timers, nhưng không tự xuất metric tới hệ thống monitoring.

**8. Observation khác Timer trực tiếp ở điểm nào?**  
`Observation` là abstraction cho operation có thể gắn metric/tracing handlers; `Timer` trực tiếp chỉ ghi duration trong `MeterRegistry`.

**9. Vì sao không thể chỉ alert khi error counter tăng?**  
Vì listener bị mất bean/scan sai hoặc executor không chạy có thể khiến **không có samples**, trong khi hệ thống đang lỗi. Cần thêm expected volume/backlog/missing-data logic.

**10. Khi có retry, success rate tính thế nào?**  
Cần xác định đang tính theo **attempts** hay **logical events**. Không gộp hai định nghĩa trong một metric.

## 16. Tài liệu chính thức

- [Spring Framework — Observability Support, Application Events và @EventListener](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework 6.2 — Application Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Micrometer — Timers và Timer.Sample](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Instrumentation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)

