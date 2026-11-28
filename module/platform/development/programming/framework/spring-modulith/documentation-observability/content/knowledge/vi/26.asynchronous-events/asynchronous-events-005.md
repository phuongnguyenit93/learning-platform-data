# Event externalization và ranh giới trace

## Mục tiêu học tập

Trong **Spring Modulith**, application module có thể giao tiếp bằng domain event để giảm sự phụ thuộc trực tiếp. Tuy nhiên, khi event được xử lý **bất đồng bộ** hoặc **externalize** ra Kafka, AMQP hay hệ thống nhắn tin khác, đường xử lý đã vượt qua ranh giới của transaction, thread và có thể cả tiến trình. Việc theo dõi một yêu cầu từ module phát event đến hệ thống bên ngoài vì thế đòi hỏi hiểu rõ **event publication**, **trace context propagation** và mức độ bảo đảm của hệ thống gửi nhận.

Bài học thuộc chương **Sự kiện bất đồng bộ**, nằm trong phạm vi **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**: sinh và kiểm chứng tài liệu ranh giới module, quan sát tương tác bằng Spring Boot Actuator, event metrics, tracing và context propagation. Sau bài này, người học có thể:

1. Phân biệt domain event nội bộ, event externalization và distributed tracing.
2. Chỉ ra chính xác ranh giới giữa module, transaction, thread và message broker.
3. Cấu hình externalization một event có chọn lọc bằng **@Externalized** và hạ tầng gửi thông điệp.
4. Giữ hoặc liên kết trace context khi qua xử lý **@ApplicationModuleListener**, **@Async** và Kafka.
5. Dùng module graph, Actuator, metrics, log và trace để kiểm chứng các luồng giao tiếp.
6. Thiết kế phép thử khi publish lỗi, retry, phát lại event và nhận trùng thông điệp.

> **Giả định:** các ví dụ dùng Java, Spring Boot và Spring Modulith hiện đại, với Kafka làm broker minh họa. Tên package, phiên bản thư viện, các cấu hình tracing exporter và bean executor cần căn chỉnh theo BOM và phiên bản Spring Boot/Spring Modulith thật của dự án. Bài trình bày thiết kế và mã mẫu để thực hành; chưa thay thế kiểm thử tích hợp trong một ứng dụng cụ thể.

## 1. Ba khái niệm cần tách biệt

| Khái niệm | Mục đích | Ranh giới chính | Điều nó không bảo đảm |
|---|---|---|---|
| **Domain event nội bộ** | Thông báo một sự thật nghiệp vụ giữa các application module trong cùng ứng dụng | Module, có thể cùng transaction hoặc sau commit | Không tự gửi tới bên ngoài |
| **Event externalization** | Chọn một số domain event để phát lên hạ tầng messaging | Tiến trình ứng dụng → broker → consumer khác | Không tự bảo đảm exactly-once hoặc tracing xuyên tiến trình |
| **Distributed tracing** | Quan sát chuỗi công việc với span và ngữ cảnh trace | Thread, callback, broker và tiến trình | Không thay thế kho lưu event, retry hoặc mã định danh nghiệp vụ |

Ví dụ: hệ thống bán hàng gồm module **orders**, **billing** và **notification**. Khi đơn hàng hoàn tất, module orders phát **OrderCompleted**. Billing tạo hóa đơn trong cùng ứng dụng qua **@ApplicationModuleListener**; đồng thời một bản sự kiện được externalize tới Kafka để hệ thống CRM nhận.

Domain event **OrderCompleted** biểu diễn *điều gì đã xảy ra*. Event publication registry ghi nhận *việc listener đã xử lý thành công hay chưa*. Trace diễn tả *các bước xử lý xảy ra như thế nào, khi nào và trên những thành phần nào*. Cùng một event có thể được xử lý nhiều lần hoặc xuất hiện ở nhiều trace khác nhau khi retry.

## 2. Sơ đồ luồng và các ranh giới cần quan sát

~~~mermaid
flowchart LR
    HTTP["HTTP: POST /orders/{id}/complete"] --> ORD["Module orders<br/>Transaction T1"]
    ORD --> PUB["ApplicationEventPublisher<br/>OrderCompleted"]
    PUB --> BILL["Module billing<br/>@ApplicationModuleListener<br/>Async + transaction T2"]
    PUB --> EXT["Modulith externalizer<br/>sau commit T1"]
    EXT --> KAFKA[("Kafka topic<br/>orders.completed")]
    KAFKA --> CRM["CRM consumer<br/>tiến trình khác"]
    ORD --> REG[("Event Publication Registry<br/>ghi cùng T1")]
    REG -. "theo dõi và resubmit" .-> EXT
    classDef boundary fill:#f1f5f9,stroke:#64748b,color:#0f172a
    class KAFKA,REG boundary
~~~

*Sơ đồ thể hiện các nhánh xử lý logic; thứ tự thực thi giữa các listener bất đồng bộ có thể khác nhau và không nên dựa vào vị trí các mũi tên để suy ra thứ tự hoàn thành.*

Ta cần nhận diện bốn loại ranh giới:

**Ranh giới module.** Khi orders phát event cho billing, hợp đồng giữa module là kiểu event và dữ liệu được công bố. Module graph cho thấy dependency tĩnh và quan hệ event listener, trong khi trace cho thấy lời gọi thực tế phát sinh lúc ứng dụng chạy.

**Ranh giới transaction.** Lệnh thay đổi đơn hàng ở transaction **T1** được commit. Listener dùng **@ApplicationModuleListener** chạy sau commit, theo cách bất đồng bộ và trong transaction mới. Lỗi của billing không có nghĩa transaction orders đã commit bị rollback.

**Ranh giới thread.** Khi công việc đi sang executor khác, các giá trị trong ThreadLocal như current observation, current span hoặc MDC thường không tự đi theo. Nếu không cấu hình context propagation, một span mới có thể mất quan hệ với request gốc.

**Ranh giới tiến trình.** Từ externalizer qua Kafka đến CRM là một bước giao tiếp giữa các hệ thống. Trace context phải được inject vào message headers và extract ở consumer nếu muốn liên hệ các span. Không nên kỳ vọng event payload, publication registry hay annotation **@Externalized** tự lưu đầy đủ trace context.

## 3. Thực hành: chọn event cần externalize

### 3.1. Thiết kế sự kiện có danh tính ổn định

Mỗi domain event nên có **eventId** để xử lý trùng, **aggregateId** (ở đây là orderId) để tương quan nghiệp vụ và **occurredAt** để ghi nhận thời điểm sự kiện phát sinh. Các giá trị này phải giữ nguyên khi retry; không tạo eventId mới cho mỗi lần gửi lại cùng sự kiện.

Ví dụ event là một kiểu công khai của module orders:

~~~java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;
import org.springframework.modulith.events.Externalized;

@Externalized("orders.completed")
public record OrderCompleted(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

**@Externalized("orders.completed")** chỉ định event đủ điều kiện được gửi tới broker và tên đích logic. Với tích hợp Kafka, giá trị này được dùng làm tên topic; routing key có thể được cấu hình thêm nếu cần. Không phải mọi domain event đều cần ra ngoài: chỉ externalize event thuộc hợp đồng tích hợp được đối tác sử dụng, tránh lộ sự kiện nội bộ mang chi tiết triển khai.

Trong một hợp đồng tích hợp dài hạn, nên công bố định dạng JSON, tên trường, phiên bản schema và quy tắc xử lý lỗi rõ ràng. Khi có yêu cầu độc lập hóa dữ liệu nội bộ, dùng bước **mapping** của externalization để tạo payload tích hợp riêng, thay vì để consumer bên ngoài phụ thuộc vào toàn bộ cấu trúc Java của domain event.

### 3.2. Phát sự kiện trong transaction nghiệp vụ

~~~java
package com.example.shop.orders;

import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void complete(UUID orderId) {
        orders.markCompleted(orderId);
        events.publishEvent(
            new OrderCompleted(UUID.randomUUID(), orderId, clock.instant()));
    }
}
~~~

Ví dụ giả định ứng dụng cung cấp **OrderRepository** và bean **Clock**; phương thức markCompleted phải cập nhật trạng thái trong transaction. Trong ứng dụng thực, cần bảo vệ thao tác hoàn tất đơn khỏi việc thực hiện lặp lại nếu yêu cầu HTTP được gửi nhiều lần. Nếu mỗi lần gọi lại đều sinh eventId mới, cơ chế idempotency dựa trên eventId sẽ coi đó là hai sự kiện khác nhau.

**Điểm cần kiểm chứng:** sự kiện phải được phát *trong transaction nghiệp vụ đang hoạt động* để event publication registry có thể đăng ký việc giao đến transactional listeners cùng giao dịch. Nếu transaction T1 rollback thì không được phát thông điệp tích hợp tương ứng từ nhánh after-commit.

### 3.3. Một consumer nội bộ bất đồng bộ

~~~java
package com.example.shop.billing;

import com.example.shop.orders.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class BillingEventHandler {

    private final InvoiceService invoices;

    BillingEventHandler(InvoiceService invoices) {
        this.invoices = invoices;
    }

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        invoices.createIfAbsent(event.orderId(), event.eventId());
    }
}
~~~

**@ApplicationModuleListener** là shortcut của Spring Modulith cho transactional event listener được thực thi bất đồng bộ, dùng transaction riêng. Phương thức **createIfAbsent** biểu thị yêu cầu idempotency: nếu cùng một event được xử lý lại sau lỗi, không tạo hóa đơn trùng.

Đường xử lý billing và externalizer là hai mục tiêu khác nhau. Billing xử lý thành công không chứng minh message đã được Kafka nhận; ngược lại, Kafka nhận message không chứng minh billing đã tạo hóa đơn.

## 4. Cấu hình hạ tầng externalization và observability

Ví dụ Gradle dưới đây chỉ liệt kê các dependency có liên quan. Ứng dụng cần có Spring Boot, Spring Kafka, DataSource và transaction manager phù hợp; phiên bản do **Spring Boot/Spring Modulith BOM** quản lý:

~~~groovy
dependencies {
    implementation 'org.springframework.modulith:spring-modulith-events-kafka'
    implementation 'org.springframework.modulith:spring-modulith-starter-jdbc'

    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

**Vai trò các nhóm dependency:**

- **spring-modulith-events-kafka:** kết nối cơ chế externalization của Spring Modulith với Kafka.
- **spring-modulith-starter-jdbc:** cung cấp persistent event publication registry qua JDBC và cơ chế serialization sự kiện. Chọn starter JPA/MongoDB tương ứng nếu đó là công nghệ lưu trữ của ứng dụng.
- **spring-modulith-starter-insight:** đưa khả năng quan sát tương tác module và Actuator của Modulith vào ứng dụng.
- **Micrometer Tracing + OTLP:** tạo và xuất trace, nhưng còn cần exporter/collector thực sự hoạt động.

Ví dụ cấu hình trong **application.yml**:

~~~yaml
spring:
  application:
    name: shop-modulith
  kafka:
    bootstrap-servers: localhost:9092
    template:
      observation-enabled: true
    listener:
      observation-enabled: true
  modulith:
    events:
      externalization:
        enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,modulith
  tracing:
    sampling:
      probability: 1.0
~~~

Ở đây **sampling = 1.0** chỉ thích hợp cho thực hành hoặc môi trường thử nghiệm. Môi trường production thường chọn tỷ lệ phù hợp với chi phí lưu trữ và khối lượng yêu cầu. Cần cấu hình endpoint OTLP theo phiên bản Spring Boot đang dùng và bảo vệ Actuator; không nên mở các endpoint vận hành công khai nếu không có kiểm soát truy cập.

Với Kafka, cấu hình observation cho **KafkaTemplate** và **listener container** giúp hệ thống có thể tạo observation producer/consumer và truyền trace context trong message headers khi tracing stack được tích hợp đúng. Nếu một producer tùy biến tự tạo record và bỏ headers, hoặc một consumer khác công nghệ không extract context, mối liên hệ trace có thể mất. Phải xác minh bằng message thật, không chỉ nhìn cấu hình.

> **Lưu ý phiên bản:** Spring Modulith hỗ trợ cơ chế externalization mặc định qua transactional listener; từ nhánh 2.1 có thêm lựa chọn actual outbox thông qua các tích hợp như Namastack/JobRunr. Bảo đảm giao nhận và chế độ cấu hình của từng lựa chọn không giống nhau. Kiểm tra tài liệu đúng phiên bản trước khi thay đổi chiến lược durability.

## 5. Trace context qua ranh giới thread

### 5.1. Vì sao trace bị đứt sau @Async?

Giả sử HTTP request có traceId **T-100**. Span xử lý orders đang active trên thread phục vụ HTTP. Khi sự kiện được giao cho listener bất đồng bộ, việc chạy trên thread khác có thể không mang theo context hiện tại. Hậu quả:

- Log trong listener không có traceId hoặc có traceId khác.
- Span của billing hiện thành một trace riêng.
- Việc mở trace HTTP không hiển thị khoảng thời gian billing đã xử lý.
- Đội vận hành có thể kết luận nhầm billing không chạy, mặc dù event đã được xử lý.

Một span chỉ có thể gắn vào đúng trace nếu context của nó được truyền ở thời điểm tạo công việc và được khôi phục khi công việc chạy. Điều này không có nghĩa thread bất đồng bộ chia sẻ transaction với thread HTTP.

### 5.2. Cấu hình executor có context propagation

Khi tự tạo executor cho xử lý bất đồng bộ, có thể dùng **ContextPropagatingTaskDecorator** từ Spring Framework:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncTracingConfiguration {

    @Bean(name = "taskExecutor")
    ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("modulith-events-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Ví dụ này dành cho ứng dụng đang dùng cơ chế tìm executor mặc định của Spring Async. Nếu ứng dụng đã có **AsyncConfigurer** hoặc executor do Spring Boot tự cấu hình, cần tích hợp decorator vào đúng executor đang được listener sử dụng thay vì đăng ký bean thứ hai không được gọi.

Ở một số phiên bản Spring Boot, context propagation cho **AsyncTaskExecutor** do Boot tự cấu hình có thể bật bằng **spring.task.execution.propagate-context**. Hãy kiểm tra cấu hình được hỗ trợ trên phiên bản đang chạy và kiểm chứng bằng trace thực tế.

**ContextPropagatingTaskDecorator** chuyển context quan sát tại thời điểm submit task sang thread chạy task; nó không biến hai transaction thành một, không bảo đảm các ThreadLocal tùy chỉnh đều được chuyển và cũng không tự giải quyết propagation qua Kafka hoặc qua một lần replay sau khi tiến trình khởi động lại.

### 5.3. Theo dõi current span trong listener

Để chẩn đoán, có thể đọc traceId của span hiện hành trong một listener:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ObservedBillingHandler {

    private static final Logger log =
        LoggerFactory.getLogger(ObservedBillingHandler.class);

    private final Tracer tracer;

    ObservedBillingHandler(Tracer tracer) {
        this.tracer = tracer;
    }

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        Span span = tracer.currentSpan();
        String traceId = span == null
            ? "missing"
            : span.context().traceId();

        log.info("billing eventId={} orderId={} traceId={}",
            event.eventId(), event.orderId(), traceId);

        // Thực thi nghiệp vụ idempotent tại đây.
    }
}
~~~

Hai listener billing trong mục 3 và mục 5 là **hai ví dụ thay thế**, không nên đồng thời khai báo để xử lý cùng event nếu chỉ muốn một nghiệp vụ lập hóa đơn. Trong ứng dụng thực, thêm đoạn quan sát vào chính handler nghiệp vụ, đồng thời cấu hình logging/MDC an toàn theo quy ước của dự án.

Nếu traceId là **missing**, kiểm tra trước hết việc ứng dụng có observation/tracer active hay không, sau đó xác minh listener dùng đúng executor đã cấu hình propagation. Nếu traceId mới xuất hiện, so sánh span tree để xác định đây là trace mới hợp lệ hay propagation bị mất.

## 6. Trace context qua ranh giới broker và tiến trình

Qua Kafka, trace context thường được đưa vào **headers** theo định dạng propagation đã thống nhất (ví dụ W3C Trace Context). Producer tạo span gửi thông điệp; consumer nhận message, trích xuất context và tạo span xử lý. Cơ chế instrument có thể thể hiện quan hệ parent-child hoặc **span link** theo mô hình messaging và thư viện sử dụng; không nên mặc định rằng mọi hệ thống quan sát sẽ vẽ thành một cây trace liên tục.

| Dữ liệu | Đặt ở đâu? | Dùng làm gì? |
|---|---|---|
| **eventId** | Payload hợp đồng tích hợp | Deduplicate, retry, audit theo sự kiện |
| **orderId** | Payload | Truy vết nghiệp vụ theo aggregate |
| **occurredAt** | Payload | Thời điểm thực sự phát sinh sự kiện |
| **traceparent / tracestate** | Header do tracing instrumentation quản lý | Liên hệ span giữa producer và consumer |
| **correlationId** (nếu có) | Payload hoặc header theo hợp đồng | Gom các bước của một quy trình nghiệp vụ dài |
| **publication status** | Kho event publication của ứng dụng phát | Xác định listener/externalization đã hoàn thành hay còn cần retry |

**Không dùng traceId làm eventId.** Một request có thể tạo nhiều event, một event có thể được giao lại nhiều lần trong các trace mới. TraceId là dấu vết của một lần thực thi; eventId là danh tính của một sự thật nghiệp vụ.

Tương tự, đừng đưa dữ liệu nhạy cảm như access token, thông tin cá nhân hoặc toàn bộ baggage của request vào Kafka headers chỉ để thuận tiện theo dõi. Với trace context nhận từ bên ngoài, phải áp dụng chính sách trust boundary phù hợp; thông tin do đối tác gửi không tự động đáng tin.

### 6.1. Hai tình huống khác nhau

**Tình huống A — giao thông điệp thông thường.** Request HTTP hoàn tất đơn hàng, externalizer gửi Kafka và CRM nhận ngay. Nếu propagation từ executor và Kafka được cấu hình đúng, các span có thể liên kết theo trace context tương ứng. Kiểm tra producer span, Kafka headers và consumer span để chứng minh.

**Tình huống B — gửi lại sau sự cố.** Request ban đầu đã kết thúc từ nhiều giờ trước. Kho publication còn bản ghi cần resubmit; job phục hồi chạy sau khi restart và gửi lại event. Thread mới **không còn active context của HTTP request cũ**. Trace phát lại có thể bắt đầu mới; dùng **eventId**, **orderId** và thuộc tính log tương quan để liên kết lịch sử. Không được giả định publication registry tự lưu và khôi phục traceparent gốc.

Đối với xử lý kéo dài nhiều giờ hoặc nhiều ngày, có thể sử dụng **correlationId** độc lập với trace, và nếu hệ quan sát hỗ trợ, liên kết các trace bằng span links hoặc metadata an toàn đã thiết kế trước.

## 7. Event Publication Registry, lỗi gửi và retry

Spring Modulith có **Event Publication Registry** để ghi nhận việc giao event tới transactional listeners. Với cấu hình persistence thích hợp, thông tin publication được ghi trong transaction nghiệp vụ, còn listener được thực thi sau commit. Lần xử lý thành công sẽ đánh dấu publication hoàn thành; trường hợp lỗi có thể được phát lại theo API và chính sách vận hành.

Điều này giảm nguy cơ mất event do listener chạy lỗi, nhưng không tạo bảo đảm **exactly-once** cho broker hoặc consumer. Một tình huống điển hình:

1. Transaction T1 cập nhật đơn hàng và lưu publication; T1 commit.
2. Externalizer gửi message tới Kafka, broker nhận thành công.
3. Tiến trình chết trước khi đánh dấu publication đã hoàn thành.
4. Sau khi phục hồi, publication được gửi lại.
5. CRM nhận **cùng eventId** lần thứ hai.

Vì vậy consumer phải idempotent: ghi nhận **eventId** đã xử lý trong một cơ chế nhất quán với hiệu ứng nghiệp vụ, hoặc dùng khóa duy nhất theo eventId. Kiểm tra trùng trước mà không có bảo vệ giao dịch vẫn có thể gây race condition khi nhiều consumer đồng thời xử lý.

Ở các phiên bản Spring Modulith từ **2.0**, publication có lifecycle chi tiết hơn, gồm các trạng thái như **PUBLISHED**, **PROCESSING**, **COMPLETED**, **FAILED** và **RESUBMITTED**; cách truy vấn/resubmit tùy version. Không xây dashboard trên giả định rằng mọi hệ thống đều chỉ có hai trạng thái thành công/thất bại. Cần phân biệt *chưa được xử lý*, *đang xử lý*, *xử lý lỗi* và *đã xử lý* khi vận hành.

Nếu dùng chiến lược externalization mặc định qua listener, hãy hiểu rõ những giới hạn của nó so với một outbox đầy đủ (ví dụ cách định lịch, concurrency, retry/backoff và quan sát tồn đọng). Với yêu cầu khắt khe về giao nhận, đánh giá tích hợp outbox được hỗ trợ ở phiên bản tương ứng.

Một số vấn đề vận hành cần thiết kế rõ:

- **Retry/backoff:** không resubmit vô hạn và dồn dập khi broker đang gặp sự cố.
- **Thứ tự:** các publication bất đồng bộ có thể đến broker ngoài thứ tự; cấu hình serialize externalization chỉ có thể giảm đua tranh trong phạm vi cơ chế cụ thể, không bảo đảm thứ tự toàn hệ thống nhiều instance.
- **Retention:** dọn publication đã hoàn thành hoặc đưa vào kho archive theo chính sách.
- **Poison event:** tách event không thể serialize hoặc consumer không thể xử lý khỏi lỗi mạng tạm thời.
- **Schema evolution:** consumer ngoài hệ thống có thể triển khai khác thời điểm với producer, cần giữ tương thích dữ liệu.

## 8. Quan sát module graph, Actuator, metrics và traces cùng lúc

Trong Spring Modulith, **đồ thị module** và **trace runtime** trả lời hai câu hỏi khác nhau.

**Module graph** cho thấy ranh giới application module và các phụ thuộc được nhận diện từ code. Ví dụ orders công bố **OrderCompleted**, billing đăng ký listener. Spring Modulith hỗ trợ sinh tài liệu kiến trúc bằng **Documenter** và xem thông tin module qua Actuator endpoint **/actuator/modulith** khi đã bật hỗ trợ thích hợp. Graph giúp xác định các dependency ngoài ý muốn và kiểm chứng thiết kế module trước khi deploy.

**Runtime trace** cho thấy request hoặc event cụ thể thực sự đi qua các span nào. Spring Modulith observability có thể tạo module entry spans với các thuộc tính như **module.identifier**, **module.name**, **module.method** và **module.invocation-type**. Nếu event publication được instrument, có thể quan sát các metric liên quan tới các sự kiện được phát từ application module.

Các nguồn bằng chứng nên kết hợp:

| Nguồn | Câu hỏi có thể trả lời | Không thể suy ra riêng từ nguồn đó |
|---|---|---|
| Tài liệu module graph | Module nào có phụ thuộc tĩnh; listener nào liên quan đến event? | Event đã chạy trong production hay chưa |
| **/actuator/modulith** | Cấu trúc module được nhận diện trên instance đang chạy | Broker đã nhận được từng thông điệp |
| **module.events.published** | Có bao nhiêu lần application event được phát theo metric | Message đã publish thành công ra Kafka |
| Metric publication riêng của event | Loại event nào, module nào đang phát nhiều | Consumer đã xử lý thành công |
| Event Publication Registry | Publication nào đang tồn đọng/thất bại/hoàn thành | Trace context của request ban đầu chắc chắn còn |
| Kafka producer/consumer observations | Hoạt động gửi và nhận trên broker | Kết quả nghiệp vụ cuối cùng của consumer |
| Distributed trace và log theo eventId | Luồng xử lý, độ trễ, lỗi và sự tương quan | Bảo đảm không trùng event hoặc không mất dữ liệu |

Tên metric mặc định liên quan đến application event trong Spring Modulith gồm **module.events.published** và các metric theo module/loại sự kiện. Các metric này mô tả **publication trong ứng dụng**, không đồng nghĩa với số message được Kafka xác nhận. Để giám sát giao nhận, kết hợp producer errors, Kafka lag, publication backlog, retries và idempotency failures.

Khi sử dụng các nhãn cho metric, chỉ dùng tập giá trị có cardinality thấp như module, event type, outcome; **không gắn eventId, orderId, traceId làm metric labels** vì số chuỗi thời gian tăng rất nhanh. Các mã định danh chi tiết phù hợp hơn với structured logs và span attributes được kiểm soát.

## 9. Kịch bản kiểm thử xuyên ranh giới

Để chứng minh cơ chế hoạt động, sử dụng môi trường tích hợp với database giao dịch, broker Kafka và hệ thống thu trace (hoặc test exporter). Các bài kiểm thử cần quan sát **kết quả**, không chỉ đếm số lần gọi phương thức.

| Mã | Thao tác | Kết quả kỳ vọng |
|---|---|---|
| E1 | Gọi complete(orderId) trong transaction hợp lệ | Có đúng domain event được phát, lưu publication theo cấu hình; sau commit có message ở orders.completed |
| E2 | Bắt transaction rollback sau khi phát event | Không có message externalized cho giao dịch đã rollback |
| E3 | Giả lập broker lỗi khi gửi | Publication được ghi nhận để khôi phục; hệ thống nêu được trạng thái và nguyên nhân lỗi |
| E4 | Broker phục hồi và resubmit | Event được gửi lại với **eventId cũ**; consumer không tạo hiệu ứng nghiệp vụ trùng |
| E5 | Gửi cùng eventId hai lần tới consumer | Hiệu ứng nghiệp vụ được áp dụng một lần theo chính sách idempotency |
| E6 | Chạy listener bằng executor bất đồng bộ | Current trace context được propagated khi có cấu hình, hoặc được báo mất context rõ ràng khi cố ý tắt |
| E7 | Producer và consumer Kafka bật observation | Message có trace headers mong đợi; producer/consumer observations được liên hệ theo instrumentation |
| E8 | Khởi động lại rồi phát lại publication tồn đọng | Recovery chạy, trace mới vẫn liên hệ được bằng eventId/correlationId; không giả định traceId cũ được giữ |
| E9 | Xem module graph và Actuator | Có module orders/billing và dependency hợp lệ; không phát sinh truy cập xuyên ranh giới ngoài dự kiến |
| E10 | Quan sát metrics và logs khi một message gửi thất bại | Phân biệt được event đã publish nội bộ với externalization chưa thành công |

### 9.1. Kiểm thử event ở cấp module

Spring Modulith cung cấp **@ApplicationModuleTest** và **PublishedEvents** để kiểm tra các event được công bố. Một test tối giản có thể có dạng:

~~~java
@ApplicationModuleTest
class OrdersModuleTests {

    @Autowired
    OrderService orders;

    @Test
    void emitsCompletionEvent(PublishedEvents publishedEvents) {
        // Seed sẵn đơn hàng này trong database của test.
        UUID orderId = UUID.fromString(
            "00000000-0000-0000-0000-000000000001");

        orders.complete(orderId);

        assertThat(publishedEvents.ofType(OrderCompleted.class))
            .anySatisfy(event ->
                assertThat(event.orderId()).isEqualTo(orderId));
    }
}
~~~

Đây là đoạn mẫu cần bổ sung fixture, import và cấu hình persistence trước khi chạy. Test trên xác nhận **domain event đã được phát**; để kiểm chứng externalization cần thêm bài test tích hợp có broker thật hoặc Testcontainers, chờ delivery bất đồng bộ với timeout hợp lý rồi so khớp topic, payload và headers. Test này cũng chưa chứng minh trường hợp rollback hay retry đã đạt yêu cầu.

### 9.2. Phân tích một trace đạt yêu cầu

Với request hoàn tất đơn hàng và propagation đã bật, người thực hành nên thu được một chuỗi bằng chứng:

1. HTTP span ghi nhận request và module orders xử lý.
2. Event publication metric tăng, registry ghi nhận publication khi giao dịch commit.
3. Module billing chạy trong transaction riêng; log có cùng **eventId** và, nếu propagation phù hợp, được liên hệ với HTTP trace.
4. Producer Kafka có send observation và message headers chứa context mong đợi.
5. CRM consumer có receive/process observation liên hệ với message.
6. Consumer hoàn thành nghiệp vụ, registry bên phát đã ghi nhận publication thành công.

Nếu producer và consumer hiển thị hai trace khác nhau, chưa thể kết luận hệ thống sai. Hãy kiểm tra quy ước instrumentation, span links, sampling và trace propagation thực tế trước khi đánh giá; bằng chứng **eventId/correlationId** vẫn phải đầy đủ để truy vết nghiệp vụ.

## 10. Sự cố thường gặp và hướng điều tra

| Hiện tượng | Khả năng gây ra | Hướng kiểm tra |
|---|---|---|
| Event nội bộ phát nhưng Kafka không có message | Event không được chọn, thiếu broker integration, sai topic, transaction rollback | Kiểm tra @Externalized, dependency, config, registry và broker |
| Kafka có message nhưng không có trace headers | Producer chưa bật observation, instrument không đi qua KafkaTemplate, headers bị ghi đè | Kiểm tra cấu hình template và capture record thực tế |
| Listener bất đồng bộ có traceId khác HTTP request | Executor thiếu decorator hoặc context đã kết thúc trước lúc submit | Kiểm tra executor thực tế, current span và thời điểm submit |
| Consumer có trace mới dù header hiện diện | Tracer/provider, propagation format hoặc extraction không tương thích | Kiểm tra instrumentation của consumer và các header W3C |
| Registry còn publication chưa hoàn thành | Broker lỗi, serialization lỗi hoặc crash trước lúc đánh dấu thành công | Tra publication status và lỗi gửi; resubmit có kiểm soát |
| CRM tạo bản ghi trùng | At-least-once delivery, không có idempotency | Ràng buộc duy nhất theo eventId và kiểm tra transaction phía consumer |
| Event metric tăng nhưng externalization fail | Metric đo event nội bộ thay vì broker acknowledgement | So sánh metric với producer failures và registry backlog |
| Trace không xuất hiện dù request thành công | Sampling, thiếu bridge/exporter, collector không nhận | Kiểm tra sampler, exporter endpoint, network và trace backend |
| Graph không hiện dependency mong đợi | Module detection hoặc cách nhận diện API/listener chưa đúng | Kiểm tra cấu trúc package và cách Spring Modulith nhận diện module |
| Sau restart không nối được trace cũ | Trace context không được lưu/phục hồi cùng publication | Dùng eventId/correlationId; thiết kế trace link khi thật sự cần |

Lỗi khó nhất thường không nằm ở việc thiếu một annotation. Nó xuất hiện khi hệ thống sử dụng **một ID duy nhất cho nhiều mục đích** hoặc dùng một metric cho nhiều khâu trong pipeline. Hãy xem event identity, publication state, broker delivery state và trace relationship là bốn nguồn dữ liệu khác nhau.

## 11. Bài tập vận dụng

Xây dựng ứng dụng gồm ba module **orders**, **billing**, **shipping** và một Kafka consumer giả lập ngoài ứng dụng.

- Orders phát **OrderCompleted** với eventId ổn định, đồng thời lưu biến đổi trạng thái trong transaction.
- Billing dùng **@ApplicationModuleListener** tạo hóa đơn theo idempotency key.
- Shipping lắng nghe event để chuẩn bị giao hàng; externalizer gửi đúng một loại event ra topic **orders.completed**.
- Bật Actuator Modulith, event metrics, Kafka observation và Micrometer Tracing; xem module graph và thu trace qua các ranh giới.
- Cố tình tắt context propagation của executor rồi so sánh traces; bật lại và xác nhận sự thay đổi.
- Cố tình làm broker lỗi, quan sát publication tồn đọng, phục hồi rồi resubmit. Xác minh consumer không tạo dữ liệu trùng và vẫn truy vết được **eventId** khi trace mới xuất hiện.

**Điều kiện hoàn thành:** người học trình bày được bản đồ module, bảng publication status, một trace bình thường, một trace của lần retry và bằng chứng broker/payload. Các bằng chứng phải trả lời được *event được phát từ đâu, đã đi qua những ranh giới nào, còn đang chờ ở bước nào và có bị xử lý trùng hay không*.

## Tài liệu tham khảo chính thức

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): application module listener, event publication registry, externalization, retry và tích hợp broker.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Actuator, module spans, event metrics và insight starter.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): tracing, context propagation và exporter.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): context propagation cho luồng sự kiện bất đồng bộ.
- [Spring Kafka — Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html): KafkaTemplate, listener container và trace propagation qua messaging.
