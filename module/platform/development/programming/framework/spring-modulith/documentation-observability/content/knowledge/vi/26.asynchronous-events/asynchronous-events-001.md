# Trace event publication và event listener

## 1. Mục tiêu và bối cảnh

Trong ứng dụng Spring Boot được chia thành **application module** bằng Spring Modulith, một module thường thông báo thay đổi trạng thái bằng **application event**. Module khác đăng ký listener để thực hiện phần việc riêng mà không cần gọi trực tiếp vào lớp nội bộ của bên phát. Khi listener chạy bất đồng bộ, luồng xử lý không còn nằm trên cùng một thread, và thời điểm hoàn tất cũng khác với thời điểm gọi publishEvent.

Bài học thuộc **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**: sử dụng Spring Modulith để biểu diễn ranh giới các application module, kết hợp **module graph**, Spring Boot **Actuator**, **event metrics**, **distributed tracing** và **context propagation** để kiểm chứng kiến trúc mô-đun lúc hệ thống vận hành. Trọng tâm của chương **Sự kiện bất đồng bộ** là lần theo đường đi từ lúc phát sự kiện (*event publication*) đến khi *event listener* nhận, xử lý và xác nhận hoàn tất.

Kết thúc bài, người học có thể:

1. Xác định sự khác nhau giữa lệnh publishEvent, thời điểm transaction commit, lần bắt đầu xử lý listener và kết quả xử lý.
2. Triển khai ví dụ hai application module giao tiếp bằng sự kiện và @ApplicationModuleListener.
3. Cấu hình Spring Modulith observability, Micrometer Observation/Tracing, Actuator và bộ xuất trace.
4. Đọc trace/span, log và metric để truy vết publisher → listener, kể cả khi chuyển thread.
5. Dùng event ID, correlation ID và event publication registry để chẩn đoán các ca retry, lỗi listener, duplicate và khởi động lại.
6. Kiểm thử đường phát sự kiện và hiệu ứng thực tế của listener theo hành vi bất đồng bộ.

**Phạm vi kỹ thuật:** Java 17+, Spring Boot 3.x, một phiên bản Spring Modulith tương thích với BOM của ứng dụng và Micrometer Tracing. Tên span/metric tự động và cấu hình exporter có thể khác theo phiên bản; cần xác nhận trong ứng dụng thực tế. Ví dụ dùng Spring application event trong cùng một tiến trình JVM, chưa giả định có Kafka hoặc RabbitMQ.

## 2. Hiểu bốn mốc trong vòng đời sự kiện

Xét hệ thống đặt hàng gồm hai module:

- **orders:** ghi nhận đơn hàng, phát OrderSubmitted.
- **shipping:** nghe OrderSubmitted rồi mở yêu cầu giao hàng.

Có bốn mốc cần đo và đối chiếu:

| Mốc | Hành động | Ý nghĩa quan sát |
| --- | --- | --- |
| T1 — Publication | orders gọi ApplicationEventPublisher.publishEvent(event) | Mã phát sự kiện đã được gọi; chưa chứng minh listener hoàn thành |
| T2 — Commit | Transaction ghi đơn hàng commit | Listener AFTER_COMMIT đủ điều kiện được kích hoạt |
| T3 — Dispatch / receive | Spring lên lịch listener và worker thread bắt đầu chạy | Có thể trễ vì hàng đợi executor, tải hệ thống hoặc retry |
| T4 — Completion | shipping hoàn tất xử lý và transaction riêng commit | Tác dụng phụ đã được lưu; publication có thể được đánh dấu hoàn tất |

**Không đồng nhất T1 với T4.** Khi log ghi “published” ngay sau publishEvent, listener vẫn có thể chưa bắt đầu, bị lỗi hoặc đang chờ trong executor. Tương tự, một span publisher thành công chỉ cho biết đoạn mã phát sự kiện chạy thành công, không mặc định chứng minh toàn bộ quy trình kinh doanh thành công.

~~~mermaid
sequenceDiagram
    autonumber
    participant HTTP as HTTP Controller
    participant O as orders / Transaction
    participant R as Event Publication Registry
    participant E as Spring Event Infrastructure
    participant X as Async Executor
    participant S as shipping / Listener

    HTTP->>O: submitOrder(...)
    O->>O: Lưu đơn hàng
    O->>E: publishEvent(OrderSubmitted)
    E->>R: Đăng ký publication nếu có registry
    Note over O,R: Sự kiện phát bên trong transaction
    O->>O: Commit transaction
    E->>X: Kích hoạt listener AFTER_COMMIT
    X-->>S: Bắt đầu listener trên thread khác
    S->>S: Xử lý nghiệp vụ và commit transaction mới
    S-->>R: Đánh dấu hoàn tất khi xử lý thành công
~~~

Sơ đồ biểu diễn trường hợp dùng listener bất đồng bộ theo pha AFTER_COMMIT với event publication registry đã cấu hình. Những chi tiết về lịch chạy và cơ chế ghi nhận hoàn tất phụ thuộc implementation/phiên bản.

### Đồng bộ, bất đồng bộ và listener theo transaction khác nhau thế nào?

| Kiểu listener | Thời điểm/luồng | Điểm cần nhớ |
| --- | --- | --- |
| @EventListener thông thường | Thường gọi ngay khi publishEvent và cùng thread nếu multicaster mặc định đồng bộ | Exception có thể quay về bên phát |
| @Async kết hợp @EventListener | Chạy trên executor | Không tự chờ commit transaction của bên phát |
| @TransactionalEventListener(phase = AFTER_COMMIT) | Kích hoạt sau khi transaction nguồn commit | Mặc định bỏ qua sự kiện khi không có transaction phù hợp, trừ khi bật fallbackExecution |
| @ApplicationModuleListener | Tiện ích Spring Modulith dành cho listener ứng dụng theo sự kiện, thường bao gồm xử lý bất đồng bộ, sau commit và transaction riêng | Kiểm tra semantics theo phiên bản và cấu hình async đang dùng |

**@ApplicationModuleListener** trong các dòng Spring Modulith hiện đại được cấu tạo theo ý tưởng @Async + @TransactionalEventListener + @Transactional với propagation REQUIRES_NEW: transaction của bên phát commit trước, listener xử lý trong transaction riêng. Đây là đặc tính hữu ích cho độ tách rời, nhưng cũng tạo ra một ranh giới quan sát mới.

Nếu yêu cầu nghiệp vụ bắt buộc listener cập nhật trong cùng transaction với publisher, không thể coi @ApplicationModuleListener là cơ chế thay thế tương đương lời gọi đồng bộ. Cần chọn thiết kế nhất quán với yêu cầu dữ liệu và thời gian phản hồi.

## 3. Thiết kế ranh giới module để trace có ý nghĩa

Bố cục minh họa:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderSubmitted.java            // API event công khai của module
│   ├── OrderApplicationService.java
│   └── internal
│       └── ...                        // Triển khai nội bộ
└── shipping
    ├── OrderSubmittedListener.java
    └── internal
        └── ...                        // Nghiệp vụ vận chuyển
~~~

Với cách phát hiện module mặc định theo package của Spring Modulith, orders và shipping là hai application module. Đặt kiểu OrderSubmitted trong **gói API được công bố của orders** giúp shipping sử dụng event mà không truy cập implementation nội bộ. Nếu đặt event trong gói con không được công bố, cần cấu hình named interface phù hợp để module khác phụ thuộc hợp lệ.

Có thể kiểm tra kiến trúc và sinh module graph từ mô hình ứng dụng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleArchitectureTests {

    @Test
    void verifyModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }

    @Test
    void writeModuleDocumentation() {
        var modules = ApplicationModules.of(ShopApplication.class);
        new Documenter(modules).writeDocumentation();
    }
}
~~~

Module graph mô tả **cấu trúc phụ thuộc và các quan hệ module** được Spring Modulith phát hiện. Nó hỗ trợ kiểm tra xem shipping có phụ thuộc đúng API của orders hay không. Module graph **không phải** một bản ghi trace cho biết sự kiện nào đã xử lý lúc 10:05; dữ liệu runtime cần lấy từ tracing, log, metrics và publication registry.

## 4. Viết publisher và listener cho ví dụ đơn hàng

### 4.1. Kiểu sự kiện ổn định

Tạo OrderSubmitted như một giá trị dữ liệu bất biến:

~~~java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderSubmitted(
        UUID eventId,
        UUID orderId,
        Instant occurredAt) {
}
~~~

Mỗi publication có eventId riêng, orderId chỉ ra thực thể kinh doanh, occurredAt ghi lại thời điểm tạo sự kiện. Nên dùng kiểu có thể tuần tự hóa phù hợp với cơ chế lưu publication đang lựa chọn; tránh nhúng JPA entity lazy-loading hoặc đối tượng chứa secret vào payload.

Sự kiện nên diễn tả một **sự thật đã xảy ra**: đơn hàng đã được chấp nhận trong transaction. Nó không nên mang toàn bộ thông tin trạng thái cơ sở dữ liệu hoặc cấu trúc nội bộ của orders.

### 4.2. Bên phát trong transaction

~~~java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public UUID submit(OrderDraft draft) {
        Order saved = orders.save(Order.from(draft));

        var event = new OrderSubmitted(
            UUID.randomUUID(), saved.id(), Instant.now());

        events.publishEvent(event);
        return saved.id();
    }
}
~~~

OrderRepository, OrderDraft và Order trong đoạn trên là các kiểu miền đặt hàng mà ứng dụng thực tế cần triển khai. Điểm cần quan sát là **save và publishEvent xảy ra khi transaction của submit còn hoạt động**.

Sự kiện được publish trước khi transaction kết thúc; Spring điều phối listener AFTER_COMMIT sau khi commit. Nếu transaction rollback, listener theo pha AFTER_COMMIT sẽ không được gọi theo đường đi thông thường.

### 4.3. Bên nghe ở module khác

~~~java
package com.example.shop.shipping;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderSubmitted;

@Component
public class OrderSubmittedListener {

    private final ShippingService shippingService;

    public OrderSubmittedListener(ShippingService shippingService) {
        this.shippingService = shippingService;
    }

    @ApplicationModuleListener
    public void on(OrderSubmitted event) {
        shippingService.requestShipment(
            event.orderId(), event.eventId());
    }
}
~~~

ShippingService là service nghiệp vụ của module shipping; thao tác của nó phải có **idempotency** theo eventId hoặc khóa nghiệp vụ tương ứng. Một event có thể được xử lý lại sau lỗi, nên kiểm tra “đã có yêu cầu giao hàng hay chưa” phải đi kèm ràng buộc duy nhất ở tầng lưu trữ khi có nhiều worker cạnh tranh.

Điều cần hiểu ở listener:

- Transaction xử lý phía shipping tách khỏi transaction ghi order.
- Listener có thể chạy trên worker thread thay vì HTTP request thread.
- Lỗi ném ra từ listener có thể khiến publication được xem là chưa hoàn tất và cần khôi phục; client HTTP đã nhận response trước đó không nhất thiết nhìn thấy lỗi này.
- Không dựa vào ThreadLocal, SecurityContext, MDC hoặc transaction context của publisher tự nhiên tồn tại ở listener.

## 5. Bổ sung thư viện observability và công cụ xem trace

Ví dụ nhóm dependency Gradle (phiên bản được quản lý bởi Spring Boot BOM và Spring Modulith BOM tương thích):

~~~groovy
dependencies {
    implementation("org.springframework.modulith:spring-modulith-starter-core")
    implementation("org.springframework.modulith:spring-modulith-starter-observability")

    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")

    // Nếu muốn lưu publication có độ bền bằng JDBC:
    implementation("org.springframework.modulith:spring-modulith-starter-jdbc")
}
~~~

Ứng dụng cần Spring Boot web/data/transaction và JDBC driver theo cách triển khai riêng. Spring Modulith JDBC publication registry còn cần **schema lưu event publication** và transaction manager; không nên thêm starter rồi mặc định dữ liệu đã được lưu mà không kiểm tra migration. Một số starter hoặc artifact có thể đổi theo phiên bản; dùng BOM nhất quán với Spring Boot.

Ví dụ application.yml cho môi trường thực hành có OTLP collector ở cổng 4318:

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

**Sampling 100% chỉ dành cho bài lab hoặc môi trường nhỏ.** Trong production, việc thu thập toàn bộ span có chi phí cao; nên chọn sampling phù hợp theo lưu lượng và nhu cầu xử lý sự cố.

Một hệ thống thu thập thường gồm:

~~~mermaid
flowchart LR
    P[Spring Boot + Spring Modulith] --> M[Micrometer Observation]
    M --> T[Micrometer Tracing + OTel bridge]
    T --> O[OTLP Collector]
    O --> B[Trace backend: Jaeger / Tempo]
    M --> A[Actuator metrics]
    P --> L[Structured logs]
    P --> R[Event Publication Registry]
~~~

Trace backend giúp tìm đoạn thực thi và quan hệ nhân quả, Actuator/metric cho phép xem tần suất và xu hướng, log ghi eventId và chi tiết nghiệp vụ, còn registry nắm tình trạng completion của các publication được theo dõi. Đây là các nguồn thông tin bổ trợ nhau.

### Spring Modulith quan sát những gì?

Starter observability của Spring Modulith giúp quan sát **tương tác qua ranh giới application module** trong hệ sinh thái Micrometer/Actuator. Khi truy vết một yêu cầu HTTP đi từ module này sang module khác, trace có thể cho thấy các span module entry được instrument theo cấu hình và phiên bản.

Tuy nhiên, không nên mặc định rằng mọi lời gọi publishEvent hay mọi listener đều tự sinh ra hai span có tên và quan hệ cố định. Cần mở trace trong backend, kiểm tra span thực tế rồi bổ sung **custom Observation** nếu luồng sự kiện chưa được thể hiện rõ. Tránh tạo hai Observation cho cùng một đoạn nếu instrumentation tự động đã bao phủ đoạn đó.

## 6. Tạo Observation rõ ràng cho publication và listener

Micrometer **Observation** là lớp trừu tượng có thể tạo span, metric và các tín hiệu quan sát tùy ObservationHandler đã được cấu hình. Ta bổ sung nhãn có cardinality thấp cho loại event và module, rồi lưu eventId trong log để truy tìm một sự kiện cụ thể.

### 6.1. Đo đoạn gọi publishEvent

~~~java
package com.example.shop.orders;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class ObservedOrderEventPublisher {

    private final ApplicationEventPublisher delegate;
    private final ObservationRegistry registry;

    public ObservedOrderEventPublisher(
            ApplicationEventPublisher delegate,
            ObservationRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    public void publish(OrderSubmitted event) {
        Observation.createNotStarted("shop.event.publish", registry)
            .lowCardinalityKeyValue("event.type", "OrderSubmitted")
            .lowCardinalityKeyValue("module", "orders")
            .observe(() -> delegate.publishEvent(event));
    }
}
~~~

Trong OrderApplicationService có thể thay việc gọi events.publishEvent(event) bằng observedPublisher.publish(event), đồng thời điều chỉnh constructor để inject wrapper này. **Observation kết thúc khi lời gọi delegate.publishEvent trả về.** Không gán tên “end-to-end processing duration” cho khoảng thời gian đó: với listener AFTER_COMMIT/async, thời gian xử lý thật còn ở phía sau.

Có thể ghi log theo ID cố định:

~~~java
private static final org.slf4j.Logger log =
    org.slf4j.LoggerFactory.getLogger(ObservedOrderEventPublisher.class);

// Trong phương thức publish:
log.info("event=OrderSubmitted stage=published eventId={} orderId={}",
    event.eventId(), event.orderId());
~~~

Cẩn thận với câu chữ: “published” nghĩa là **đã gọi publish**, không nhất thiết “listener đã xử lý”.

### 6.2. Đo thời gian xử lý listener

~~~java
package com.example.shop.shipping;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderSubmitted;

@Component
public class OrderSubmittedListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderSubmittedListener.class);

    private final ShippingService shippingService;
    private final ObservationRegistry observations;

    public OrderSubmittedListener(
            ShippingService shippingService,
            ObservationRegistry observations) {
        this.shippingService = shippingService;
        this.observations = observations;
    }

    @ApplicationModuleListener
    public void on(OrderSubmitted event) {
        log.info("event=OrderSubmitted stage=listener-start eventId={} orderId={}",
            event.eventId(), event.orderId());

        try {
            Observation.createNotStarted("shop.event.consume", observations)
                .lowCardinalityKeyValue("event.type", "OrderSubmitted")
                .lowCardinalityKeyValue("module", "shipping")
                .observe(() ->
                    shippingService.requestShipment(
                        event.orderId(), event.eventId()));

            log.info("event=OrderSubmitted stage=listener-finish eventId={}",
                event.eventId());
        } catch (RuntimeException ex) {
            log.error("event=OrderSubmitted stage=listener-failed eventId={}",
                event.eventId(), ex);
            throw ex;
        }
    }
}
~~~

Lưu ý mã ở đây minh họa **phiên bản listener có Observation**, thay thế phiên bản listener trước đó khi triển khai, không khai báo hai bean listener cùng nhận OrderSubmitted nếu bạn chỉ muốn một bên nhận.

**Vì sao phải rethrow?** Nếu bắt exception rồi chỉ log, event publication registry có thể coi listener đã hoàn tất, trong khi thao tác nghiệp vụ thất bại. Hãy để ngoại lệ lan ra, sau đó sử dụng cơ chế khôi phục/retry đã chọn.

**Lưu ý về transaction và log:** dòng listener-finish xuất hiện khi method đã chạy hết phần mã của nó; không phải bằng chứng tuyệt đối rằng mọi trạng thái bền vững, commit transaction ngoài method và hoàn tất trong registry đều đã thành công. Khi yêu cầu chứng cứ hoàn tất, cần kiểm tra giao dịch, dữ liệu hậu điều kiện và trạng thái publication.

### 6.3. Span và metric không thay cho correlation ID

Một hệ thống có thể cung cấp:

| Thông tin | Nên đặt ở đâu? | Lý do |
| --- | --- | --- |
| event.type = OrderSubmitted | Low-cardinality metric/span attribute | Số loại event hữu hạn, phù hợp nhóm dữ liệu |
| module = orders/shipping | Low-cardinality metric/span attribute | Cho phép so sánh module |
| outcome = success/failure | Low-cardinality metric tag | Phân tích tỷ lệ lỗi |
| eventId, orderId | Structured log; có thể là span attribute phù hợp chính sách | Giá trị thay đổi theo từng event, làm tăng cardinality nếu đưa vào metric label |
| traceId, spanId | Hệ thống tracing và MDC | Liên kết log với trace khi context tồn tại |
| Error exception type | Log/trace an toàn, kiểm soát nội dung | Chẩn đoán nguyên nhân mà không lộ dữ liệu nhạy cảm |

Có thể truy vết bằng eventId xuyên nhiều trace khác nhau, kể cả trường hợp retry sau restart. Đừng dùng một transaction ID hoặc thread name làm khóa tương quan lâu dài.

## 7. Context propagation qua @Async

### 7.1. Vì sao trace “đứt” khi chạy thread khác?

Micrometer Tracing thường giữ span đang hoạt động trong một dạng context gắn với thread. Request HTTP có thể mở span A, trong khi @ApplicationModuleListener được chạy trong thread của executor. Nếu không chuyển context phù hợp, bên listener không nhìn thấy span cha và có thể mở trace B riêng, hoặc không tạo span có ích.

Cần phân biệt:

- **Truyền tracing context:** mang thông tin trace/span phục vụ tương quan.
- **Truyền MDC/log context:** mang các trường phục vụ log, ví dụ traceId.
- **Truyền security context:** chỉ thực hiện theo chính sách bảo mật, không mặc định được phép.
- **Truyền transaction context:** không nên chuyển transaction hiện tại sang worker thread; listener dùng transaction riêng.
- **Truyền domain correlation:** eventId/correlationId là dữ liệu của event, vẫn tồn tại khi context thread đã mất.

### 7.2. Cấu hình executor có ContextPropagatingTaskDecorator

Với Spring Framework hỗ trợ ContextPropagatingTaskDecorator (từ dòng 6.1), có thể cấu hình executor dùng cho @Async:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncEventsConfiguration {

    @Bean(name = "taskExecutor")
    public ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("events-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Tên taskExecutor là tên thường được cơ chế @Async dùng khi chọn executor mặc định. Nếu ứng dụng có **nhiều executor** hoặc tùy chỉnh AsyncConfigurer, phải xác nhận @ApplicationModuleListener thực sự sử dụng bean được cấu hình; decorator đặt trên executor khác sẽ không mang lại hiệu quả.

Decorator **chụp context đang hoạt động vào lúc task được submit** và khôi phục khi task chạy. Trong luồng AFTER_COMMIT, task có thể được submit sau khi một Observation publisher đã kết thúc. Vì vậy decorator không thể tự tạo lại span đã kết thúc hoặc bảo đảm listener luôn có span publisher làm parent. Muốn liên kết chắc chắn giữa các lần xử lý, phải thiết kế thêm eventId/correlationId; nếu dùng broker bên ngoài, cần propagation qua message headers như traceparent.

Khi không có context để chuyển, việc listener bắt đầu trace mới vẫn là hành vi hợp lệ. Mục tiêu là có đủ dữ liệu để biết **sự kiện nào** gây ra lần xử lý, chứ không cố ép mọi lần retry phải mang cùng một trace ID.

### 7.3. Kiểm tra propagation thực tế

Ở môi trường lab:

1. Gửi một yêu cầu HTTP tạo đơn hàng và lấy traceId từ log phía orders.
2. Tìm log stage=published theo eventId.
3. Tìm log stage=listener-start với cùng eventId; xem traceId ở listener.
4. Mở trace backend, kiểm tra span shop.event.publish và shop.event.consume. Xem parent span và thời gian bắt đầu thực tế.
5. Thử tạm tắt decorator trong môi trường kiểm thử rồi lặp lại, quan sát mối quan hệ giữa hai span thay đổi thế nào.
6. Mô phỏng retry sau restart; xác nhận eventId giữ nguyên trong hệ thống tương quan, còn traceId có thể là trace mới.

Trong môi trường thật, log chưa có traceId thường do thiếu bridge, thiếu context propagation, sampling hoặc log correlation chưa bật. Điều này không chứng minh listener không chạy; cần kiểm tra side effect và event publication registry.

## 8. Event Publication Registry: trạng thái xử lý bền vững

**Trace span không phải bộ nhớ công việc.** Một span được xuất sang backend rồi vẫn không bảo đảm event đã được xử lý thành công hoặc tồn tại đủ lâu để khôi phục. Spring Modulith cung cấp cơ chế **event publication registry** để theo dõi các publication hướng đến transactional event listener.

Khi được cấu hình với kho lưu trữ phù hợp (ví dụ JDBC) và event được publish trong transaction, registry có thể ghi nhận publication cần chuyển tới listener; sau khi listener xử lý thành công, publication được đánh dấu đã hoàn tất. Publication chưa hoàn tất có thể được tìm và tái gửi bằng cơ chế khôi phục mà phiên bản đang dùng hỗ trợ.

Một vòng đời logic:

~~~mermaid
stateDiagram-v2
    [*] --> Registered: Event được phát và ghi nhận
    Registered --> Committed: Transaction nguồn commit
    Registered --> Discarded: Transaction nguồn rollback
    Committed --> Running: Listener bắt đầu
    Running --> Completed: Xử lý thành công
    Running --> Outstanding: Exception / bị gián đoạn
    Outstanding --> Running: Resubmit / retry
    Completed --> [*]
    Discarded --> [*]
~~~

Đây là **mô hình khái niệm**, không phải danh sách enum hay bảng trạng thái cụ thể trong nội bộ Spring Modulith. Tên cột, thao tác commit/mark complete và chính sách resubmission phải được xác nhận bằng implementation thực tế.

### 8.1. Các điều kiện để việc ghi nhận có ý nghĩa

- Đã thêm một implementation registry phù hợp và khởi tạo schema lưu publication.
- Có transaction manager và publication diễn ra trong transaction phù hợp.
- Đối tượng sự kiện có thể được serialize/deserialize qua cơ chế được chọn; kiểu và version phải tương thích với dữ liệu đang tồn.
- Listener cần được framework nhận diện đúng để theo dõi completion.
- Có chính sách xử lý publication outstanding khi lỗi hay restart; nếu bật tự động tái gửi, phải chấp nhận khả năng trùng xử lý.

**Không tuyên bố “exactly once” chỉ vì bật registry.** Trong tình huống listener đã commit tác dụng phụ nhưng tiến trình chết trước khi registry ghi trạng thái completed, lần khôi phục sau có thể gọi listener lần nữa. Vì vậy idempotency ở shipping vẫn bắt buộc nếu không được phép tạo hai yêu cầu vận chuyển.

### 8.2. EventId bảo vệ việc kiểm tra completion thế nào?

Nếu publication fail, ta cần nối được:

- Log bên phát: eventId=E, orderId=O.
- Publication record: sự kiện OrderSubmitted hướng đến listener shipping, chưa completed.
- Log listener: eventId=E, attempt nào, exception nào.
- Dữ liệu shipping: orderId=O đã/chưa có yêu cầu vận chuyển.
- Trace backend: một hoặc nhiều trace có span consume tương ứng eventId=E.

Nếu cần lưu eventId trên trace, có thể ghi như một **high-cardinality span attribute** theo quy định của hệ thống tracing và tránh thu thập dữ liệu nhạy cảm. Không dùng eventId làm metric tag.

## 9. Thiết kế metrics cho luồng sự kiện

Tracing trả lời: “Một sự kiện cụ thể đã đi qua những bước nào?”. Metrics trả lời: “Hệ thống đang xử lý bao nhiêu sự kiện, mất bao lâu và lỗi ở đâu?”.

Nên xem tối thiểu bốn nhóm chỉ số:

| Nhóm metric | Cách diễn giải | Lưu ý |
| --- | --- | --- |
| Publications | Số lần publishEvent theo event type | Có thể bao gồm event chưa được listener nhận |
| Listener attempts | Số lượt listener bắt đầu, thành công, thất bại | Retry làm số lượt lớn hơn số event duy nhất |
| Listener processing duration | Thời gian bên trong listener thực thi | Không bao gồm toàn bộ thời gian đợi trước khi worker bắt đầu |
| Outstanding publications | Số publication chưa hoàn tất trong registry | Cần đọc nguồn lưu và chính sách cleanup; không suy ra từ metric processing duration |

Nếu muốn có số liệu cụ thể khi listener thành công/thất bại, có thể sử dụng MeterRegistry:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class ListenerMetrics {

    private final Counter completed;
    private final Counter failed;

    public ListenerMetrics(MeterRegistry registry) {
        this.completed = Counter.builder("shop.event.listener.attempts")
            .tag("event.type", "OrderSubmitted")
            .tag("module", "shipping")
            .tag("outcome", "success")
            .register(registry);

        this.failed = Counter.builder("shop.event.listener.attempts")
            .tag("event.type", "OrderSubmitted")
            .tag("module", "shipping")
            .tag("outcome", "failure")
            .register(registry);
    }

    public void success() { completed.increment(); }
    public void failure() { failed.increment(); }
}
~~~

Ví dụ metric trên ghi nhận **số lần thử xử lý** theo nhánh được instrument, không thay cho dữ liệu completion sau commit. Khi gắn vào listener, gọi success() ở nhánh xử lý thành công, failure() trong catch rồi rethrow. Nếu hệ thống đã có metric tự động từ Observation, cần kiểm tra và tránh đếm trùng.

Có thể xem các metric đã đăng ký từ Actuator:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/shop.event.listener.attempts
~~~

Các đường dẫn trên chỉ hoạt động khi Actuator được bật, endpoint metrics được expose và ứng dụng đã thực sự đăng ký metric. Công khai Actuator phải có chính sách bảo mật và phạm vi mạng phù hợp; không để dữ liệu giám sát nhạy cảm truy cập tùy ý trên Internet.

## 10. Đọc một trace xuyên ranh giới module

Giả sử người dùng gọi POST /orders, hệ thống tạo OrderSubmitted rồi shipping xử lý sau commit.

Trong một lần chạy có context propagation và trace exporter hoạt động, có thể thấy hình dạng tương tự:

~~~text
traceId = A17...

HTTP POST /orders                  80 ms
  orders.submit                    35 ms
    shop.event.publish              2 ms
  [transaction commit]

shipping listener (sau commit, worker thread)
  shop.event.consume               45 ms
    shipping.requestShipment       39 ms
~~~

Đây là **mẫu giải thích**, không phải bảo đảm span tự động có đúng các tên, cấu trúc parent hoặc thời lượng trên. Span listener có thể thuộc cùng trace, một trace khác, hoặc là span có quan hệ link/correlation tùy instrumentation và thời điểm context được truyền.

Đặt các câu hỏi sau khi đọc trace:

1. Publication được quan sát tại thời điểm nào so với commit?
2. Có sự chậm trễ đáng kể giữa publication/commit và listener start không? Nếu có, kiểm tra executor queue hoặc tải hệ thống.
3. Listener chạy lâu ở bước nào: gọi database, tích hợp HTTP, lock hay xử lý CPU?
4. Một eventId có nhiều lần listener attempt không? Nếu có, kiểm tra retry và idempotency.
5. Trace xuất hiện thành công nhưng registry outstanding còn tăng? Nếu có, kiểm tra lỗi ở giai đoạn commit/completion của listener hoặc thiếu instrumentation.
6. Có call qua module boundary bị bỏ qua khỏi graph/tracing vì mã dùng API nội bộ hoặc vì instrumentation không áp dụng không?

Điểm quan trọng: **sơ đồ module kiểm chứng hình thức phụ thuộc**, còn **trace runtime** cho biết đường thực thi thật. Nếu shipping gọi trực tiếp vào repository nội bộ của orders, việc quan sát span có thể lộ bất thường, nhưng cần thêm kiểm thử module boundaries để ngăn quan hệ phụ thuộc vi phạm.

## 11. Chẩn đoán sự cố bằng bốn nguồn bằng chứng

| Triệu chứng | Khả năng thường gặp | Cách xác minh |
| --- | --- | --- |
| Có log publication, không có log listener | Chưa commit, thiếu registration listener, thiếu transaction, executor chưa chạy | Kiểm tra commit, cấu hình @ApplicationModuleListener, thread pool và registry |
| Listener chạy nhưng traceId khác | Không có active context tại lúc submit task hoặc thiếu propagation | Kiểm tra decorator, cấu hình tracing, thời điểm AFTER_COMMIT; dùng eventId để nối |
| Listener chạy nhiều lần cho cùng eventId | Retry, resubmission, duplicate delivery | Xem publication/outstanding và ràng buộc idempotency của shipping |
| Có span consume thành công, chưa thấy dữ liệu shipping | Transaction rollback sau khi code đã chạy, lỗi ở commit hoặc kiểm tra sai kho dữ liệu | Xem transaction log, exception và trạng thái dữ liệu đã commit |
| Event chưa hoàn tất tăng liên tục | Listener lỗi, lỗi deserialization, thiếu khôi phục hoặc data source lỗi | Truy xuất registry và log theo loại event/exception |
| Không thấy metric trong /actuator/metrics | Chưa tạo meter, endpoint chưa expose hoặc chưa có traffic | Kiểm tra MeterRegistry, endpoint và yêu cầu thử |
| Span bị mất khi xuất OTLP | Thiếu exporter/collector, sampling quá thấp hoặc network | Kiểm tra cấu hình OTLP, collector log và sampling |
| Xử lý trễ tăng khi có tải | Hàng đợi executor đầy, thread bị block, downstream chậm | Quan sát queue, active threads, latency và timeout |

### Một quy trình debug thực tế

Khi phát hiện “đơn hàng đã tạo nhưng chưa có yêu cầu vận chuyển”, hãy lần theo:

1. Tìm orderId trong log orders để lấy eventId.
2. Xác nhận transaction orders commit; không suy ra commit chỉ từ log published.
3. Kiểm tra publication của eventId và listener đích trong registry nếu đã cấu hình.
4. Tìm listener-start, listener-failed, listener-finish theo eventId trên mọi instance.
5. Mở trace của lần xử lý tương ứng; nếu bị đứt trace, tiếp tục theo eventId.
6. Kiểm tra side effect đã commit trong shipping và khóa idempotency.
7. Chỉ retry/resubmit theo chính sách sau khi xác định liệu tác dụng phụ đã xảy ra hay chưa.

Không nên kích hoạt retry thủ công lặp lại khi chưa xác minh idempotency: có thể tạo tác dụng phụ trùng lặp.

## 12. Kiểm thử publication, async listener và observability

### 12.1. Kiểm tra phát đúng sự kiện

Spring Modulith cung cấp công cụ kiểm thử theo module, trong đó có cách thu thập PublishedEvents. Ví dụ minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrderPublicationTests {

    @Autowired OrderApplicationService orders;

    @Test
    void publishesOrderSubmitted(PublishedEvents events) {
        // Thay draftFixture() bằng factory dữ liệu kiểm thử của ứng dụng.
        var orderId = orders.submit(draftFixture());

        assertThat(events.ofType(OrderSubmitted.class))
            .anyMatch(event -> event.orderId().equals(orderId));
    }

    private OrderDraft draftFixture() {
        // Tạo OrderDraft hợp lệ theo mô hình domain riêng.
        throw new UnsupportedOperationException("Supply test fixture");
    }
}
~~~

Đoạn mã kiểm thử trên trình bày **cách assert event**; hàm draftFixture là điểm cần điền theo domain, không phải test chạy nguyên trạng. Module test có thể có các chế độ bootstrap khác nhau; cần cấu hình các phụ thuộc/bean tối thiểu mà OrderApplicationService sử dụng.

Bài kiểm thử này chứng minh publisher đã phát OrderSubmitted với orderId đúng. **Nó không chứng minh shipping xử lý xong**, vì listener bất đồng bộ chạy theo lịch riêng.

### 12.2. Kiểm tra hậu điều kiện sau commit

Một kiểm thử tích hợp nên chạy với database và executor kiểm thử thực tế, **không đặt @Transactional ở chính test method** nếu điều đó khiến transaction nguồn không commit trong thời gian chờ.

Quy trình:

1. Gọi orders.submit(draft) và cho transaction phương thức commit.
2. Dùng Awaitility (hoặc cơ chế polling có giới hạn) chờ dữ liệu shipping xuất hiện.
3. Assert chỉ có **một** yêu cầu vận chuyển hợp lệ cho orderId.
4. Mô phỏng listener ném lỗi ở lượt đầu, rồi cho retry/resubmit theo cơ chế đã cấu hình.
5. Xác minh publication được hoàn tất sau retry và side effect không bị nhân đôi.

Ví dụ ý tưởng assert khi sử dụng Awaitility:

~~~java
var orderId = orders.submit(validDraft());

await().atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertThat(shippingRequests.countByOrderId(orderId))
            .isEqualTo(1));
~~~

Đoạn trên giả định đã import Awaitility/AssertJ/Duration và có fixture/repository của ứng dụng. Nó chỉ minh họa cách đồng bộ kiểm thử theo **hậu điều kiện**; không dùng Thread.sleep cố định để đoán lúc listener hoàn tất.

### 12.3. Kiểm tra instrumentation

Dùng ObservationRegistry kiểm thử hoặc một backend tracing test để xác nhận:

- Có Observation publication với tên và low-cardinality tags đã công bố.
- Có Observation consume khi shipping thực sự xử lý.
- Lỗi listener được ghi nhận và rethrow để registry không đánh dấu thành công sai.
- Với propagation bật, bối cảnh trace hiện diện khi executor thực sự nhận context thích hợp; với retry sau restart, correlation qua eventId vẫn dùng được.
- Thông tin nhạy cảm không được gán vào metric label, log hoặc span attribute.

Bài test instrumentation cần kiểm tra **hành vi quan sát được**, không phụ thuộc cứng vào span ID hay thời gian chính xác.

## 13. Điều chỉnh khi đưa lên môi trường vận hành

### Kiểm soát tải và độ bền

Executor cần cấu hình core/max pool, queue capacity, thread name và rejection policy phù hợp. Nếu queue đầy hoặc thread pool cạn, listener có thể bị trễ hoặc không được schedule như mong đợi. Theo dõi executor saturation và xử lý exception/rejection theo đặc thù transaction.

Nếu thời gian phục hồi sau lỗi là quan trọng, dùng **persistent event publication registry** phù hợp và quy trình resubmit/outstanding có kiểm soát. Kiểm tra cả serialization tương thích khi nâng version ứng dụng và xử lý event đã lưu bằng code mới.

### Correlation vượt qua tiến trình

Trong một JVM, task decorator giúp mang context đang hoạt động qua @Async. Với broker/message queue hoặc microservice khác, hãy dùng instrumentation cho messaging và truyền trace context bằng header tương ứng (ví dụ W3C traceparent). Nhưng trace context **không thay thế** eventId/correlationId trong payload hoặc metadata bền vững, đặc biệt khi replay sau nhiều giờ.

### Bảo mật và quyền riêng tư

Không gắn tên khách hàng, email, địa chỉ giao hàng, token, nội dung chứng từ hoặc payload đầy đủ vào span/metric mặc định. Kiểm soát quyền xem Actuator, log, registry và trace backend. Chỉ lưu định danh phù hợp chính sách dữ liệu, phân vùng theo môi trường và đặt retention hợp lý.

### Năng lực đối soát

Một dashboard hữu ích gồm số publication theo loại event, lượt listener success/failure, độ trễ xử lý, số outstanding publications, queue backlog, và tỷ lệ retry. Thiết lập ngưỡng cảnh báo dựa trên **outstanding tăng theo thời gian** hoặc độ trễ vượt SLO, không chỉ dựa trên một lỗi đơn lẻ.

## 14. Bài tập thực hành tổng hợp

**Bài tập 1 — trace luồng thành công.** Tạo hai module orders và shipping, triển khai OrderSubmitted, @ApplicationModuleListener và Observation ở cả publisher/listener. Chạy một POST tạo đơn, tìm eventId trong log, xem hai span trong backend. Ghi lại chính xác thời điểm publisher kết thúc, commit và listener bắt đầu.

**Bài tập 2 — thử propagation.** Chạy listener trước và sau khi cấu hình ContextPropagatingTaskDecorator trên đúng executor. So sánh traceId, parent relationship, thread name và tác dụng phụ. Giải thích trường hợp context publisher đã kết thúc trước lúc lịch chạy listener.

**Bài tập 3 — thử lỗi và retry.** Cho shipping thất bại một lần rồi xử lý thành công khi retry. Bật registry lưu bền, quan sát outstanding publication, log lần thử và kết quả sau resubmit. Bổ sung unique constraint để bảo đảm không tạo hai yêu cầu giao hàng.

**Bài tập 4 — kiểm chứng kiến trúc.** Sinh module graph và chạy ApplicationModules.verify(). Cố tình đưa một truy cập trực tiếp từ shipping đến lớp internal của orders rồi quan sát kiểm thử kiến trúc phản hồi. Sửa bằng cách sử dụng API/sự kiện được công bố chính thức.

### Tiêu chí hoàn thành

Một lời giải đạt yêu cầu khi:

1. Module orders phát event trong transaction và shipping xử lý sau commit bằng listener bất đồng bộ.
2. Kiểm thử kiến trúc xác nhận shipping chỉ phụ thuộc API được công bố của orders.
3. Tracing cho thấy đoạn publish và consume hoặc có đủ dữ liệu eventId để đối soát khi trace bị tách.
4. Log có eventId nhất quán; metric dùng tag có cardinality thấp và phản ánh rõ attempts/success/failure.
5. Tình huống lỗi listener được quan sát và không bị báo hoàn tất giả; khi retry không sinh side effect trùng.
6. Kiểm thử xác nhận cả event được phát lẫn hậu điều kiện đã commit của listener.
7. Actuator, trace backend và publication registry phục vụ các câu hỏi khác nhau và được đối chiếu khi debug.

**Kết quả cần đạt:** Có thể nói chính xác một sự kiện OrderSubmitted được phát từ module nào, đã commit hay chưa, listener bắt đầu lúc nào, hoàn tất ở đâu, có lỗi/retry hay không; từ đó chứng minh ranh giới mô-đun và hành vi vận hành của hệ thống Spring Modulith.
