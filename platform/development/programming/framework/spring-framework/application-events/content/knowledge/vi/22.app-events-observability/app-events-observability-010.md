# Liên kết event với trace và correlation ID trong Spring Application Events

## 1. Mục tiêu: lần theo một sự kiện từ nơi phát đến nơi xử lý

Trong ứng dụng Spring, một request có thể làm thay đổi dữ liệu, gọi `ApplicationEventPublisher.publishEvent(...)`, kích hoạt nhiều `@EventListener` và tiếp tục tạo ra event khác. Khi những bước này trải qua nhiều thread, module hoặc service, log thông thường thường không đủ để trả lời:

- Request hoặc thao tác nghiệp vụ nào đã gây ra event?
- Event cụ thể nào đang được xử lý? Nó có phải bản giao lại (retry/replay) không?
- Listener nào tạo ra event tiếp theo và vì sao?
- Event có được xử lý trong cùng trace phân tán không, hay đã tách sang một trace khác?
- Nếu listener chạy trên executor, thông tin tracing và logging có còn đi theo không?
- Khi có lỗi, ta nên tìm log, span, metric và event record nào?

**Liên kết event với trace và correlation ID** là việc thiết kế các định danh và cách truyền ngữ cảnh để kết nối **nguyên nhân nghiệp vụ** với **đường thực thi kỹ thuật**. Hai thứ bổ sung cho nhau nhưng không đồng nghĩa.

Một luồng đơn giản:

~~~text
HTTP POST /orders
  |
  | traceId = 4bf92f3577b34da6a3ce929d0e0e4736
  | spanId  = 00f067aa0ba902b7
  | correlationId = order-flow-42
  v
OrderService
  |
  | publish OrderPlaced(
  |   eventId=evt-100,
  |   orderId=ORD-7,
  |   correlationId=order-flow-42,
  |   causationId=cmd-25)
  v
@EventListener OrderAuditListener
  |
  | observation/span: handle OrderPlaced
  | cùng correlationId, có thể là span con
  v
OrderAuditRecorded(
  eventId=evt-101,
  correlationId=order-flow-42,
  causationId=evt-100)
~~~

`correlationId` trong ví dụ dùng để gắn **các bước cùng hành trình nghiệp vụ**. `traceId` giúp liên kết các span kỹ thuật được hệ thống tracing thu thập. `eventId` phân biệt từng sự kiện cụ thể; `causationId` chỉ ra tác nhân trực tiếp dẫn tới một sự kiện mới.

**Spring Application Events không tự tạo sẵn toàn bộ các trường business correlation ở trên.** Đây là những giá trị mà hệ thống thiết kế trong payload/envelope hoặc metadata, sau đó chủ động đưa vào log và các span theo quy ước của ứng dụng.

## 2. Phân biệt trace ID, span ID, correlation ID, event ID

| Định danh | Trả lời câu hỏi | Đặc điểm |
| --- | --- | --- |
| **`traceId`** | Những bước kỹ thuật nào thuộc cùng một distributed trace? | Thường do tracing SDK cấp; nhiều span chia sẻ một trace ID. |
| **`spanId`** | Đây là thao tác cụ thể nào trong trace? | Mỗi span có ID riêng; span con thường giữ trace ID và có span ID khác. |
| **`correlationId`** | Các event/request nào thuộc cùng một hành trình hoặc giao dịch nghiệp vụ? | Do hệ thống định nghĩa; có thể tồn tại qua nhiều trace, retry hay thời gian dài. |
| **`eventId`** | Đây là lần phát sinh sự kiện nào? | Dùng cho audit, replay, idempotency/dedup khi event được lưu/giao lại. |
| **`causationId`** | Event/command nào trực tiếp sinh ra event này? | Hữu ích để dựng đồ thị nguyên nhân sự kiện. |
| **`aggregateId`** | Sự kiện thuộc đơn hàng/thực thể nghiệp vụ nào? | Ví dụ `orderId`; một aggregate có nhiều event. |
| **`requestId`** | Request vào hệ thống nào? | Có thể bằng correlation ID trong luồng ngắn, nhưng không bắt buộc. |

### Trace ID không phải correlation ID nghiệp vụ

Một trace thường mô tả một đường thực thi liên tục qua các span. Trong khi đó một nghiệp vụ đặt hàng kéo dài hàng giờ có thể đi qua request tạo đơn, tiến trình thanh toán, worker retry và callback vận chuyển. Các hoạt động ấy có thể được ghi thành **nhiều trace khác nhau**, nhưng vẫn chung một **business correlation ID**.

Vì vậy, đừng ép `traceId` trở thành định danh nghiệp vụ duy nhất. Nếu một event được xử lý lại sau khi trace ban đầu đã kết thúc, consumer có thể tạo một trace mới mà vẫn giữ `correlationId` gốc.

### Span ID không phải event ID

`spanId` đại diện cho một khoảng xử lý kỹ thuật: có thể là HTTP request, đoạn xử lý event hoặc một lần gọi database. `eventId` định danh một occurrence nghiệp vụ. Một event được retry có thể tạo nhiều span khác nhau, nhưng vẫn nên giữ **cùng event ID** khi đó thực sự là cùng occurrence được giao lại.

Không dùng riêng `spanId` để khử trùng xử lý nghiệp vụ. Nó có thể đổi qua mỗi lần thực thi.

### Correlation ID có thể trùng với request ID, nhưng chỉ nếu contract định nghĩa như vậy

Ở hệ thống nhỏ, có thể sinh correlation ID ngay ở API gateway/controller rồi dùng qua toàn bộ chuỗi event. Nhưng khi có batch, workflow dài, một request có thể tạo nhiều hành trình nghiệp vụ, hoặc một hành trình đi qua nhiều request. Khi đó nên dùng correlation ID độc lập với request ID và quy định rõ điểm phát sinh ID.

## 3. Thiết kế metadata để event có thể truy vết

Một payload nội bộ của Spring có thể mang những trường định danh:

~~~java
public record OrderPlaced(
        String eventId,
        String orderId,
        String correlationId,
        String causationId) {}
~~~

*Đoạn code là kiểu payload minh họa; `OrderPlaced` không cần kế thừa `ApplicationEvent`. Ví dụ Java 17+ chạy đầy đủ ở phần 6.*

Có thể thay các trường trên bằng một **metadata envelope** để không lặp lại ở từng event nghiệp vụ:

~~~java
public record EventMetadata(
        String eventId,
        String eventType,
        String correlationId,
        String causationId,
        Instant occurredAt) {}

public record DomainEvent<T>(
        EventMetadata metadata,
        T payload) {}
~~~

*Đoạn trên cần import `java.time.Instant`; đây là mô hình minh họa. Nếu muốn Spring tự dispatch theo kiểu generic `DomainEvent<T>` thì cần kiểm tra cách `ResolvableType` được Spring xác định; không mặc định rằng generic type vẫn được giữ nguyên sau Java type erasure.*

Tùy môi trường, metadata còn có thể chứa `traceId` ở dạng **tham chiếu phục vụ chẩn đoán**. Tuy nhiên:

1. Ghi riêng chuỗi `traceId` vào payload **không** tự tái lập tracing context hoặc tạo span con trong hệ thống nhận.
2. Nếu truyền qua broker/HTTP, nên dùng cơ chế inject/extract chuẩn của tracing SDK — chẳng hạn W3C Trace Context — thay vì tự sửa `traceId` rồi mong có distributed trace hoàn chỉnh.
3. Nếu event cần sống lâu hơn thời gian retention trace, `correlationId`, `eventId` và `causationId` quan trọng hơn vì vẫn có thể được lưu cùng business record.
4. Nếu payload/event được gửi cho đối tác, phải cân nhắc liệu các ID nội bộ có được phép tiết lộ hay không.

Một contract có thể quy định `correlationId` là bắt buộc, `causationId` là tùy chọn (với root event), và `eventId` là bắt buộc. Khi event mới do event trước sinh ra, giữ correlation ID và cấp event ID mới; đồng thời đặt causation ID thành event ID cha.

## 4. Cách Spring phát sự kiện và tác động đến tracing

### 4.1. Listener đồng bộ mặc định

`ApplicationEventPublisher.publishEvent(...)` bàn giao event cho cơ chế multicaster. Với `SimpleApplicationEventMulticaster` mặc định, listener thường chạy **ngay trên thread gọi publish**, vì thế `ThreadLocal` tracing/MDC của publisher có thể còn hiệu lực trong listener.

~~~text
Thread request-1
  current Observation / tracing scope
      |
      +-- publishEvent(OrderPlaced)
              |
              +-- @EventListener.onOrderPlaced(...)
                     (cùng thread, thấy thread-local scope)
      |
      +-- publishEvent trả về
~~~

Tuy nhiên **Spring Framework không tự đóng gói một `Observation` riêng cho mỗi lời gọi `@EventListener`**. Tài liệu observability của Spring nói rõ các lời gọi listener không được tự tạo Observation chỉ vì dùng annotation. Nếu cần đo latency/error của từng handler như một span riêng, ứng dụng phải **instrument** handler hoặc dùng hạ tầng tracing/observability phù hợp.

### 4.2. Async multicaster, @Async và executor

Khi cấu hình `SimpleApplicationEventMulticaster.setTaskExecutor(...)` hoặc listener dùng `@Async`, tác vụ có thể chuyển sang thread khác:

~~~text
publisher-thread                       executor-thread
trace context in ThreadLocal           ThreadLocal ban đầu trống
  |
  +-- submit(task) ----------------------> @EventListener(...)
          |
          +-- không tự chuyển mọi ThreadLocal
~~~

Nếu không được propagation, listener vẫn đọc được **correlation ID nằm trực tiếp trong event payload**, nhưng có thể mất MDC/tracing scope và log ra thiếu trace ID. Đây là lý do nên kết hợp **explicit business correlation** với **context propagation của tracing** thay vì chỉ chọn một trong hai.

Spring cung cấp `ContextPropagatingTaskDecorator` từ Framework 6.1 để giúp chuyển logging/observation context khi executor chạy ở thread khác. Cơ chế này dựa vào thư viện Micrometer Context Propagation cùng các accessor được đăng ký. Nó **không sao chép mọi ThreadLocal tùy ý** và không tự mang transaction JDBC/JPA sang worker.

### 4.3. @TransactionalEventListener và transaction phase

Một listener `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` chỉ phản ứng sau khi transaction tương ứng commit thành công. Điều này không tự bảo đảm một tracing scope còn sống, không bảo đảm retry, cũng không tự làm propagation sang executor khi downstream xử lý async.

Trong transaction imperative, state thường gắn với thread; chuyển xử lý sang worker không nên “mang theo” JDBC connection/`EntityManager` chỉ để giữ correlation. Nếu cần công việc sau commit và bền vững, cần thiết kế transaction/outbox riêng.

## 5. Quy tắc tạo và truyền correlation ID

Một thiết kế cơ bản nên quy định rõ:

**Bắt đầu hành trình**

- Nếu caller đã gửi correlation ID qua header được hệ thống chấp nhận, xác minh độ dài, định dạng và trust boundary trước khi dùng; không mặc định mọi header client đều đáng tin.
- Nếu không có ID hợp lệ, sinh ID mới (ví dụ UUID).
- Gắn ID đó vào business context và tất cả event dẫn xuất liên quan.

**Tạo event gốc**

- Cấp `eventId` mới cho business fact vừa xảy ra.
- Đặt `causationId` thành ID của command/request gốc nếu hệ thống theo dõi; có thể để `null` nếu đây là root event và contract cho phép.
- Lưu rõ ID của aggregate, ví dụ `orderId`.
- Ghi timestamp `occurredAt` theo thời điểm business fact xảy ra, tốt nhất dùng `Instant` UTC.

**Tạo event dẫn xuất**

- **Giữ nguyên correlation ID** của hành trình.
- **Sinh event ID mới** cho occurrence mới.
- Đặt `causationId` bằng ID của event trước đó, nếu thực sự là nguyên nhân trực tiếp.

**Retry/replay cùng event**

- Giữ `eventId` của occurrence gốc để consumer có thể khử trùng.
- `traceId`, `spanId` của lần xử lý mới có thể khác; không tạo event ID mới chỉ vì worker retry.
- Nếu phát một **sự kiện nghiệp vụ mới** trong lần retry, lúc đó mới cần occurrence/event ID mới; không gộp hai fact khác nhau thành một ID.

### Ví dụ chuỗi causation

~~~text
Command cmd-12          correlationId=flow-42
   |
   +--> OrderPlaced    eventId=evt-101, causationId=cmd-12
            |
            +--> StockReserved    eventId=evt-102, causationId=evt-101
            |
            +--> InvoiceIssued    eventId=evt-103, causationId=evt-101

Sau 30 phút:
PaymentWebhook         correlationId=flow-42 (từ trạng thái nghiệp vụ lưu bền)
   |
   +--> PaymentCaptured eventId=evt-150, causationId=webhook-77
~~~

Tập event phía trên có thể đi qua **nhiều trace** nhưng vẫn thuộc cùng một business correlation. Dùng correlation ID để truy vấn các bản ghi liên quan; dùng causation ID để hiểu quan hệ cha–con; dùng trace/span IDs để điều tra thời gian và các lời gọi kỹ thuật.

## 6. Ví dụ Java 17+ chạy được: correlation ID ổn định khi đổi thread

Ví dụ sử dụng **Spring Framework 6.2.9**, Java 17+ và Maven. Nó tạo hai `ApplicationContext` độc lập, mỗi context cấu hình một `SimpleApplicationEventMulticaster` gửi listener đến `ThreadPoolTaskExecutor`:

- **Không có `TaskDecorator`:** event vẫn mang `correlationId` nhưng một **trace marker giả lập** lưu trong `ThreadLocal` không tự đi sang worker.
- **Có `TaskDecorator`:** worker nhận trace marker đã capture; listener đồng thời đọc được correlation ID của event.

**Quan trọng:** Chuỗi `trace-demo-001` trong chương trình chỉ là **dữ liệu minh họa cho ThreadLocal**, không phải một OpenTelemetry/Micrometer trace ID hợp lệ và chương trình này **không phát span lên tracing backend**. Mục tiêu chạy được là chứng minh ranh giới thread và lợi ích của việc lưu correlation ID ngay trong payload. Cách tích hợp tracing thực tế trình bày ở phần 7.

### 6.1. Cấu trúc dự án

~~~text
event-trace-correlation-demo/
├── pom.xml
└── src/main/java/EventTraceCorrelationDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-trace-correlation-demo</artifactId>
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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/EventTraceCorrelationDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class EventTraceCorrelationDemo {

    // Đây chỉ là một trace marker minh họa, không phải tracing SDK.
    private static final ThreadLocal<String> TRACE_MARKER =
            new ThreadLocal<>();

    // Business correlation được đưa trực tiếp vào event contract.
    public record OrderPlaced(
            String eventId,
            String orderId,
            String correlationId) {
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderEventListener listener() {
            return new OrderEventListener();
        }
    }

    public static class OrderEventListener {
        private final CountDownLatch done = new CountDownLatch(1);
        private volatile String observation;

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            String marker = TRACE_MARKER.get();
            String visibleMarker =
                    marker == null ? "missing" : marker;

            observation = "eventId=" + event.eventId()
                    + " correlationId=" + event.correlationId()
                    + " traceMarker=" + visibleMarker;
            done.countDown();
        }

        public String awaitResult() throws InterruptedException {
            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not complete within timeout");
            }
            return observation;
        }
    }

    private static TaskDecorator captureTraceMarker() {
        return task -> {
            // Capture xảy ra tại lúc task được submit.
            String captured = TRACE_MARKER.get();

            return () -> {
                // Giữ giá trị của worker để cleanup đúng.
                String previous = TRACE_MARKER.get();
                try {
                    if (captured == null) {
                        TRACE_MARKER.remove();
                    } else {
                        TRACE_MARKER.set(captured);
                    }

                    task.run();
                } finally {
                    if (previous == null) {
                        TRACE_MARKER.remove();
                    } else {
                        TRACE_MARKER.set(previous);
                    }
                }
            };
        };
    }

    private static void runCase(boolean propagate)
            throws InterruptedException {

        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("event-worker-");

        if (propagate) {
            executor.setTaskDecorator(captureTraceMarker());
        }
        executor.initialize();

        try {
            try (var context =
                    new AnnotationConfigApplicationContext()) {

                context.register(Config.class);

                // Spring nhận bean có đúng tên này làm multicaster.
                context.registerBean(
                    "applicationEventMulticaster",
                    SimpleApplicationEventMulticaster.class,
                    () -> {
                        var multicaster =
                                new SimpleApplicationEventMulticaster();
                        multicaster.setTaskExecutor(executor);
                        return multicaster;
                    });

                context.refresh();

                TRACE_MARKER.set("trace-demo-001");
                try {
                    context.publishEvent(
                            new OrderPlaced(
                                    "evt-1",
                                    "ORD-7",
                                    "flow-42"));

                    String result = context.getBean(
                            OrderEventListener.class).awaitResult();

                    String mode = propagate
                            ? "WITH_PROPAGATION"
                            : "WITHOUT_PROPAGATION";

                    System.out.println(mode + " " + result);
                } finally {
                    TRACE_MARKER.remove();
                }
            }
        } finally {
            executor.shutdown();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        runCase(false);
        runCase(true);
    }
}
~~~

### 6.2. Chạy thử và đầu ra

Trong thư mục có `pom.xml`, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=EventTraceCorrelationDemo
~~~

Các dòng do chương trình in ra, không tính log riêng của Maven:

~~~text
WITHOUT_PROPAGATION eventId=evt-1 correlationId=flow-42 traceMarker=missing
WITH_PROPAGATION eventId=evt-1 correlationId=flow-42 traceMarker=trace-demo-001
~~~

Giải thích:

1. Cả hai lần, `OrderPlaced` được tạo với `correlationId=flow-42`, vì thế listener đều đọc được ID đó, **không phụ thuộc vào ThreadLocal**.
2. Trong trường hợp đầu tiên, `TRACE_MARKER` chỉ được đặt ở thread publisher; worker thread trong executor không có giá trị, nên in `missing`.
3. Trong trường hợp thứ hai, `TaskDecorator` capture `trace-demo-001` ở lúc submit và gán nó cho worker trong thời gian task chạy.
4. `finally` bảo đảm khôi phục/cleanup giá trị cũ của worker, tránh rò context qua các task kế tiếp trong thread pool.
5. `CountDownLatch` giúp main chờ listener kết thúc trước khi đọc kết quả, tránh `Thread.sleep(...)` hoặc phụ thuộc tốc độ máy.
6. Hai context được tạo mới để mỗi trường hợp có listener và executor riêng. Trong cấu hình này chỉ có một listener nhận `OrderPlaced` nên stdout giữ thứ tự hiển thị giữa hai lượt chạy.

**Bài học:** correlation ID trong hợp đồng event giúp lần theo nghiệp vụ kể cả khi tracing context bị mất; propagation của tracing context giúp log/span trong worker nối đúng vào đường thực thi. Cả hai phải được kiểm thử độc lập.

## 7. Tích hợp tracing thực tế với Spring Boot và Micrometer

Ở ứng dụng Spring Boot có Micrometer Tracing (ví dụ bridge OpenTelemetry hoặc Brave được cấu hình phù hợp), tracing SDK quản lý span và trace context thật. `Tracer` của Micrometer có thể được inject vào bean.

### 7.1. Truy cập trace hiện tại khi phát event

Đoạn mã tích hợp dưới đây minh họa cách ghi trace ID hiện tại **như metadata phục vụ điều tra**, không dùng làm cơ chế inject/extract trace across process:

~~~java
@Service
class OrderService {

    private final ApplicationEventPublisher publisher;
    private final Tracer tracer;

    OrderService(ApplicationEventPublisher publisher, Tracer tracer) {
        this.publisher = publisher;
        this.tracer = tracer;
    }

    public void place(String orderId, String correlationId) {
        Span currentSpan = tracer.currentSpan();
        String traceId = currentSpan == null
                ? null
                : currentSpan.context().traceId();

        publisher.publishEvent(
                new OrderPlacedForDiagnostics(
                        UUID.randomUUID().toString(),
                        orderId,
                        correlationId,
                        traceId));
    }
}

record OrderPlacedForDiagnostics(
        String eventId,
        String orderId,
        String correlationId,
        String originatingTraceId) {
}
~~~

*Đây là đoạn **tích hợp**, không phải chương trình độc lập. Cần bean Micrometer `io.micrometer.tracing.Tracer`, `io.micrometer.tracing.Span`, Spring `@Service` và `ApplicationEventPublisher`, import `java.util.UUID`. Việc chọn instrumentation, sampling, exporter và các dependency phù hợp phụ thuộc phiên bản Spring Boot ứng dụng.*

Ở ví dụ, `originatingTraceId` có thể vắng mặt nếu không có current span. Nếu lưu nó cùng event, đặt tên **originating** để không nhầm với trace hiện tại lúc event được xử lý lại sau nhiều phút hoặc nhiều ngày. Không xem trường này là một span context đầy đủ.

**Cách làm ưu tiên trong cùng JVM** là để tracing library giữ scope hiện hành trong lúc publish/listener xử lý. Khi chuyển sang executor, dùng context propagation đúng cách thay vì cố gán trace ID dạng chuỗi vào một ThreadLocal rồi coi như đã tạo span thật.

### 7.2. Propagation qua executor

Theo tài liệu Spring Framework, có thể cấu hình executor:

~~~java
@Configuration
class EventObservabilityConfiguration {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("observed-event-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());
        return executor;
    }

    @Bean(name = "applicationEventMulticaster")
    SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventExecutor") ThreadPoolTaskExecutor executor) {

        var multicaster = new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        return multicaster;
    }
}
~~~

*Đây là cấu hình tích hợp, không phải toàn bộ project. Cần `org.springframework.core.task.support.ContextPropagatingTaskDecorator`, `ThreadPoolTaskExecutor`, `SimpleApplicationEventMulticaster`, `@Configuration`, `@Bean`, `@Qualifier`, cùng dependency `io.micrometer:context-propagation`. Với Spring Boot nên dùng BOM/dependency management của Boot.*

`ContextPropagatingTaskDecorator` chụp và khôi phục những context mà hệ thống Micrometer nhận biết qua `ThreadLocalAccessor`/`ContextAccessor` tương ứng. Nó giúp chuyển logging/observation context trong các tình huống thread hop, nhưng **không tự đăng ký mọi ThreadLocal do ứng dụng tạo**. Nếu ứng dụng tự quản lý một correlation ID bằng ThreadLocal riêng, cần đăng ký accessor hoặc dùng decorator custom cho đúng biến.

Nếu listener dùng `@Async("mailExecutor")`, đặt decorator ở **executor thực sự chạy method async**, không chỉ ở executor của multicaster. Kết hợp cả hai lớp async có thể tạo hai thread hop và tăng độ phức tạp; nên thiết kế một chiến lược rõ ràng.

### 7.3. Tracing scope và span của listener

Propagation có thể giúp đưa **ngữ cảnh tracing hiện hành** đến worker, nhưng **không có nghĩa Spring tự tạo một span mới cho mọi `@EventListener`**. Nếu muốn đo riêng thời gian xử lý từng event, instrument chủ động bằng Micrometer Observation hoặc tracing API.

Ví dụ ý tưởng dùng `ObservationRegistry`:

~~~java
@EventListener
public void handle(OrderPlaced event) {
    Observation.createNotStarted("app.event.handle", observationRegistry)
        .lowCardinalityKeyValue("event.type", "order.placed")
        .observe(() -> processOrderPlaced(event));
}
~~~

*Đây là đoạn minh họa trong Spring bean đã inject `ObservationRegistry`; cần `io.micrometer.observation.Observation`. `processOrderPlaced` là phương thức xử lý nghiệp vụ của ứng dụng. Muốn Observation tạo thành span có quan hệ cha–con thực sự, cần tracing handler/bridge được cấu hình đúng trong `ObservationRegistry`.*

`lowCardinalityKeyValue("event.type", "order.placed")` hợp lý vì tập tên event thường hữu hạn. **Không dùng correlationId, eventId, orderId, traceId hoặc userId làm low-cardinality metric tags**, vì các giá trị này có thể gần như duy nhất, làm nổ số lượng time series. Có thể gắn ID cần truy vết vào log, span attribute hoặc `highCardinalityKeyValue` khi chính sách vận hành/bảo mật cho phép.

## 8. MDC và log correlation: khác business correlation ID

`MDC` (Mapped Diagnostic Context) thường mang các giá trị như `traceId` và `spanId` cho logging framework. Với Micrometer Tracing được cấu hình, Spring Boot có thể tự đưa **log correlation** theo mẫu từ `traceId` + `spanId` vào log.

Ví dụ log về mặt khái niệm:

~~~text
[traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7]
INFO OrderService - placed orderId=ORD-7 correlationId=flow-42 eventId=evt-100

[traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=5f2e730bb9b4368e]
INFO AuditListener - processed eventId=evt-100 correlationId=flow-42
~~~

*Đây là log minh họa, không phải stdout của ví dụ phần 6. Span ID trong dòng thứ hai giả định listener được instrument thành một span khác; một listener sync không được tạo span riêng tự động chỉ vì có `@EventListener`.*

Điểm dễ nhầm: trong tài liệu Spring Boot, “logging correlation ID” có thể chỉ **chuỗi hiển thị xây từ trace ID và span ID**, trong khi ứng dụng lại định nghĩa **business correlation ID** như `flow-42`. Hai định danh có mục đích khác nhau và nên đặt **tên trường rõ ràng**.

Nếu cần đưa business correlation ID vào log, có thể thêm MDC thủ công theo phạm vi:

~~~java
try (MDC.MDCCloseable scope =
        MDC.putCloseable("businessCorrelationId",
                         event.correlationId())) {

    logger.info("Handling OrderPlaced eventId={}", event.eventId());
}
~~~

*Đoạn tích hợp dùng `org.slf4j.MDC` và một logger `SLF4J` đã khai báo; không phải chương trình độc lập. `putCloseable` giúp khôi phục/dọn trạng thái theo API của MDC, nhưng không tạo tracing span hoặc bảo đảm MDC được tự động propagated qua executor.*

**Đừng chỉ chèn correlation ID vào MDC mà bỏ khỏi payload** nếu event cần đi qua broker, job chậm hoặc được replay. MDC thuộc ngữ cảnh thực thi, còn payload/envelope là hợp đồng dữ liệu đi theo event.

## 9. Liên kết event qua nhiều service hoặc message broker

Trong cùng JVM, Spring dispatch đối tượng event nội bộ. Qua Kafka/RabbitMQ/JMS/HTTP, trace context phải được **inject khi publish** và **extract khi consume** theo cơ chế instrumentation/propagator của công nghệ đó.

Khái niệm hai lớp metadata:

~~~text
Business envelope:
  eventId: evt-100
  eventType: sales.order.placed
  correlationId: flow-42
  causationId: cmd-25
  occurredAt: 2026-11-11T05:30:00Z

Tracing carrier (header hoặc metadata tương thích):
  traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

`traceparent` ở trên minh họa định dạng W3C gồm version, 32 ký tự hex trace ID, 16 ký tự hex parent span ID và cờ trace. Hệ thống tracing nên tạo/đọc header bằng **SDK propagator**, không tự nối chuỗi rồi coi là đã thiết lập đầy đủ ngữ cảnh phân tán.

Một quy trình liên dịch vụ:

1. Producer thay đổi nghiệp vụ và tạo event envelope với `eventId`, `correlationId`, `causationId`.
2. Messaging instrumentation inject tracing context hiện hành vào **headers/carrier**, hoặc cơ chế cấu hình tương đương.
3. Broker nhận message và có thể giao lại sau khi retry, tùy bảo đảm delivery.
4. Consumer extract tracing carrier khi bắt đầu xử lý, tạo span xử lý (hoặc span link nếu phù hợp với xử lý tách rời/batch).
5. Consumer log `correlationId`, `eventId` và thông tin span/tracing để truy vấn cả bản tin lẫn đường thực thi.
6. Nếu consumer tạo event mới, nó giữ business correlation ID, cấp event ID mới và đặt causation ID đúng quan hệ.

**Đừng hứa trace luôn là một cây span cha–con đơn giản.** Với hàng đợi bất đồng bộ, xử lý trễ, batch hoặc nhiều producer, span links hoặc trace mới có thể phù hợp hơn; chọn theo mô hình của tracing SDK và semantics của hệ thống.

Không phải mọi request bị lấy mẫu (sampling) đều được xuất đầy đủ thành trace. Vì thế correlation ID được lưu cùng event/log vẫn hữu ích khi không có trace hoàn chỉnh.

## 10. Liên hệ với Reactor Context

Trong ứng dụng reactive dùng Reactor, tracing/transaction context có thể đi theo **subscriber context**, thay vì chỉ theo Java `ThreadLocal`. Khi chuyển giữa code imperative, Reactor pipeline và executor ngoài Reactor:

- Context propagation phải được cấu hình đúng ở các ranh giới thread/scheduler.
- `contextWrite(...)` và `deferContextual(...)` có phạm vi theo subscription; tạo subscription mới có thể không tự thừa hưởng context trước đó.
- Micrometer Context Propagation có khả năng làm cầu nối giữa Reactor Context và ThreadLocal cho những accessor được đăng ký; không phải sao chép mọi biến toàn cục.
- Reactive transaction dùng `ReactiveTransactionManager` và transaction context theo subscriber. Không truyền JDBC transaction state qua executor chỉ để giữ trace/correlation.

Một event nên mang business correlation ID như dữ liệu bất biến, kể cả khi phần tracing context chuyển qua Reactor và các thread khác nhau. Hãy coi tracing propagation là phần hạ tầng, còn correlation/causation là phần contract nghiệp vụ.

## 11. Đảm bảo không mất event: trace không phải delivery guarantee

Có trace đẹp không có nghĩa event đã được giao bền vững. `ApplicationEventPublisher` nội bộ Spring mặc định không tự cung cấp persistence, retry, dead-letter queue hoặc replay. Nếu listener lỗi, JVM bị dừng hay publish xảy ra trước commit rồi transaction rollback, event có thể không đại diện cho một business fact đã commit.

Khi yêu cầu “giao sự kiện ngay cả nếu tiến trình chết sau DB commit”, có thể dùng **transactional outbox**:

~~~text
Transaction DB
  |
  +-- UPDATE orders
  +-- INSERT outbox(eventId, correlationId, causationId,
  |                 eventType, payload, createdAt, ...)
  |
  +-- COMMIT
         |
         v
Outbox relay -> broker -> consumer
                  |
                  +--> idempotent processing by eventId
                  +--> trace context may be new/linked
                  +--> correlationId remains flow-42
~~~

Nếu muốn liên hệ tới trace gốc khi relay chạy trễ, có thể cân nhắc lưu **tracing propagation metadata đã được chuẩn hóa và được phép lưu** trong outbox, sau đó SDK khôi phục/định nghĩa quan hệ phù hợp. **Chỉ lưu mỗi trace ID không đủ** để tự động khôi phục parent span, sampling state và các tracing fields khác.

Cũng cần bảo vệ metadata: outbox lưu lâu, tracing headers/baggage có thể chứa dữ liệu không nên lưu. Thiết kế retention, truy cập và dữ liệu nhạy cảm trước khi triển khai.

Nếu consumer có at-least-once delivery, dùng `eventId` để hỗ trợ dedup trong transaction/unique constraint; `correlationId` thường không thích hợp làm khóa dedup, vì nhiều event khác nhau trong cùng hành trình chia sẻ ID này.

## 12. Kiểm thử observability theo từng lớp

Không nên chỉ test rằng `@EventListener` “được gọi” rồi kết luận khả năng truy vết đã tốt.

### 12.1. Contract tests

- Event gốc có `eventId`, `correlationId` và `aggregateId` đúng.
- Event dẫn xuất giữ `correlationId` nhưng được cấp `eventId` mới.
- `causationId` trỏ tới event/command gây ra event mới.
- Event retry giữ lại `eventId` gốc và không tạo side effect trùng.
- Event không chứa token, mật khẩu hoặc payload không cần thiết.

### 12.2. Tests về thread context

- Listener đồng bộ có thể thấy logging/tracing scope hiện hành trong điều kiện mặc định.
- Listener chạy ở executor không được giả định tự nhận custom ThreadLocal.
- Executor được trang trí/có accessor phù hợp khôi phục context trong lúc chạy.
- Sau khi listener thất bại, worker không giữ context của tác vụ cũ.
- Tác vụ thứ hai dùng correlation ID khác không nhầm sang correlation ID trước.
- Nếu `@Async` dùng executor khác multicaster, cả ranh giới thực thi cần được quan sát.

### 12.3. Tracing integration tests

- Khi tracing được bật, span xử lý event có tên rõ ràng, metadata có cardinality phù hợp.
- Khi trace bị lấy mẫu hoặc exporter không hoạt động, business correlation ID trong log/event vẫn giúp điều tra.
- Khi message qua HTTP/broker, injection/extraction hoạt động với propagator thật.
- Khi replay, trace span của lần xử lý mới không bị nhầm là cùng span của lần phát sinh event gốc.
- Hệ thống có thể tìm event trong outbox/broker logs bằng `eventId` và tìm luồng nghiệp vụ bằng `correlationId`.

Đối với kiểm thử async, dùng `CountDownLatch`, `CompletableFuture` hoặc await với timeout; tránh `Thread.sleep(100)` để “chờ log”, vì gây test không ổn định.

## 13. Chiến lược logging và đo lường

Một chuẩn log/metric nhỏ cho mỗi listener nên phân biệt ba mục tiêu:

**Logs:** dùng để điều tra từng occurrence, nên có `eventType`, `eventId`, `correlationId`, `causationId` nếu có, handler name và outcome. Trace/span IDs giúp nối tới hệ thống tracing. Nếu logging được định dạng bằng JSON, đặt các trường có tên nhất quán và kiểm soát việc lộ dữ liệu nhạy cảm.

**Traces:** dùng để thấy thời gian/thứ tự kỹ thuật, network calls và đường đi qua nhiều service. Chỉ tạo observation/span hữu ích, không tự biến mọi dòng log thành span; dùng trace ID, span ID và span links đúng semantics.

**Metrics:** tổng hợp số lượng/độ trễ/lỗi theo event type, listener, outcome. Tag như `event.type=order.placed` hoặc `handler=OrderAuditListener` thường có tập giá trị hữu hạn. Tránh gắn `eventId`, `correlationId`, `traceId` làm **low-cardinality tags**.

Ví dụ đặt tên:

~~~text
Log fields:
  event.type=sales.order.placed
  event.id=evt-100
  business.correlation_id=flow-42
  event.causation_id=cmd-25
  trace_id=4bf92f3577b34da6a3ce929d0e0e4736
  span_id=00f067aa0ba902b7
  listener=OrderAuditListener
  outcome=success

Metric:
  app.event.handle{event.type="sales.order.placed",
                   listener="OrderAuditListener",outcome="success"}
~~~

*Đây là quy ước đề xuất; không phải tên metric hoặc field mặc định của Spring Boot. Cần map vào hệ thống logs/metrics đang dùng.*

Nếu cần tìm kiếm across services, đặt cùng field name trên mọi service. Tránh mỗi đội dùng một tên `requestId`, `corr`, `transactionRef` với semantics khác nhau mà không có chuẩn chuyển đổi.

## 14. Những lỗi thường gặp và cách sửa

1. **Dùng trace ID làm khóa nghiệp vụ duy nhất.** Trace có thể đổi qua retry và không phản ánh toàn bộ saga dài; cần business correlation ID độc lập.
2. **Dùng correlation ID để deduplicate mọi event.** Nhiều event cùng workflow chia sẻ correlation ID; dùng event ID occurrence để hỗ trợ idempotency.
3. **Cho rằng `publishEvent(...)` tự tạo span cho từng `@EventListener`.** Spring Framework không instrument những lời gọi này thành Observation mặc định; thêm instrumentation có chủ đích.
4. **Chỉ nhét correlation ID vào MDC.** Khi async, broker hoặc replay, context có thể mất; nên đưa business ID vào payload/envelope.
5. **Chỉ nhét trace ID vào payload rồi mong có distributed tracing.** Cần tracing SDK quản lý span và inject/extract context qua headers/carrier phù hợp.
6. **Quên cấu hình executor đúng chỗ.** Multicaster dùng một executor còn `@Async` dùng executor khác; propagation phải ở mỗi ranh giới cần thiết.
7. **Bỏ qua cleanup ThreadLocal/MDC.** Thread pool tái sử dụng worker; context cũ có thể rò sang request tiếp theo.
8. **Chia sẻ JDBC transaction hoặc EntityManager bằng decorator.** Context propagation của tracing không phải cơ chế chuyển transaction giữa các thread.
9. **Cho rằng cùng correlation ID luôn có cùng trace ID.** Một luồng nghiệp vụ có thể kéo dài, qua nhiều trace, replay và retry.
10. **Cho rằng khác trace ID thì event không liên quan.** Correlation ID và causation chain mới là mối liên hệ nghiệp vụ bền hơn.
11. **Đưa ID duy nhất vào metric low-cardinality tag.** Làm tăng số time series, chi phí và rủi ro vận hành; ID riêng nằm trong log/trace phù hợp.
12. **Cho rằng tracing bảo đảm delivery.** Nó phục vụ quan sát, không thay thế outbox, broker retry và consumer idempotency.
13. **Không kiểm tra inbound correlation header.** Định danh do người ngoài gửi có thể quá dài, chứa ký tự lạ hoặc gây lộ dữ liệu; xác thực và chuẩn hóa.
14. **Log secrets trong baggage hoặc MDC.** Metadata được propagated và có thể xuất ra log/traces; chỉ dùng thông tin tối thiểu, an toàn.
15. **Không định nghĩa causation chain.** Hai event cùng correlation không nói được event nào trực tiếp dẫn tới event nào; thêm causation ID khi nghiệp vụ cần điều tra nguyên nhân.

## 15. Tự kiểm tra

**Câu 1.** Một order workflow gồm tạo đơn, thanh toán sau 10 phút và gửi hàng vào ngày hôm sau. Có nên bắt buộc tất cả dùng cùng trace ID không?

**Đáp án:** Không. Có thể có nhiều trace riêng do ranh giới thời gian và hệ thống. Giữ `business correlationId` xuyên workflow; tracing context/links tùy cách instrumentation.

**Câu 2.** Một event được giao lại ba lần. Nên giữ `eventId` hay sinh event ID mới mỗi lần?

**Đáp án:** Giữ `eventId` của cùng occurrence gốc để consumer dedup. Các lần xử lý kỹ thuật có thể tạo span/trace context khác nhau.

**Câu 3.** Tại sao trong ví dụ Java, dòng `WITHOUT_PROPAGATION` vẫn có `correlationId=flow-42`?

**Đáp án:** Vì correlation ID là trường bất biến nằm trong event payload, không phụ thuộc vào ThreadLocal trên worker.

**Câu 4.** Đặt `ContextPropagatingTaskDecorator` vào executor có làm tất cả custom ThreadLocal tự truyền không?

**Đáp án:** Không. Micrometer Context Propagation cần các accessor/hạ tầng tương ứng; custom ThreadLocal không tự động được biết đến.

**Câu 5.** Nếu listener đã mang trace ID dưới dạng chuỗi trong event, điều đó có đủ để tracing SDK tiếp tục parent span không?

**Đáp án:** Không. Việc tiếp tục tracing cần propagator/SDK và tracing carrier chứa đủ context thích hợp, không chỉ một chuỗi trace ID.

**Câu 6.** Vì sao không dùng correlation ID như một metric label cho mọi request?

**Đáp án:** Nó có cardinality rất cao (gần như mỗi request một giá trị), làm tăng số lượng time series. Dùng nó trong log hoặc trace attributes phù hợp, còn metrics nên có tag với tập giá trị hữu hạn.

**Câu 7.** Nếu event chỉ được publish bằng Spring ApplicationEventPublisher, có tự lưu và retry sau khi JVM dừng không?

**Đáp án:** Không. Cần cơ chế lưu bền vững như outbox/broker và chiến lược retry/idempotency riêng khi nghiệp vụ yêu cầu.

**Câu 8.** Vì sao một event dẫn xuất nên giữ correlation ID nhưng có event ID mới?

**Đáp án:** Cả hai cùng workflow nhưng là **hai occurrence nghiệp vụ khác nhau**. Event ID mới định danh fact mới; causation ID có thể liên kết fact này với event cha.

## Tài liệu tham khảo

- [Spring Framework — Observability Support: Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/integration/observability.html): listener mặc định đồng bộ, không tự có Observation, và cách dùng `ContextPropagatingTaskDecorator` khi chạy async.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher`, `@EventListener` và cách phân phối sự kiện.
- [Spring Framework 6.2 Javadoc — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): cơ chế capture/restore task context và chi phí propagation.
- [Spring Boot 3.5 — Tracing and Logging Correlation IDs](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): Micrometer Tracing, `traceId`/`spanId` trong MDC và format correlation của log.
- [Micrometer Context Propagation — Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html): `ThreadLocalAccessor`, `ContextRegistry`, `ContextSnapshot` và chuyển context qua executor.
- [Micrometer Tracing — API](https://docs.micrometer.io/tracing/reference/api.html): `Tracer`, span scope và baggage.
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/): `traceparent`, `tracestate` và cấu trúc context truyền giữa các hệ thống.
