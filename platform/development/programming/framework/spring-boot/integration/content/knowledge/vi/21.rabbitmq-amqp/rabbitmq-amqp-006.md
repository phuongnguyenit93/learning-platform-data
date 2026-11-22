# @RabbitListener và listener container factory

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot kết nối nhiều hệ thống qua HTTP client, cơ sở dữ liệu, cache, message broker và các adapter của Spring Integration. Với RabbitMQ/AMQP, một producer thường dùng `RabbitTemplate` để phát sự kiện/command; ở phía nhận, consumer dùng **`@RabbitListener`** để xử lý message. Nhưng annotation không tự tạo một worker thread theo ý nghĩa đơn giản: Spring AMQP cần một **listener container** quản lý connection, AMQP channel, consumers, concurrency, acknowledgement, chuyển đổi payload, retry, lỗi và lifecycle.

Giả sử Order Service phát `OrderConfirmed` vào exchange `orders.events`, Inventory Service tiêu thụ từ queue `inventory.order-confirmed` để giữ hàng trong database. Một consumer có thể nhận message, nhưng SQL transaction chưa commit; một process có thể crash sau COMMIT trước ACK; hoặc một event sai schema có thể bị redeliver mãi. Việc cấu hình `@RabbitListener` và container factory quyết định **khi nào broker được ACK, bao nhiêu messages được xử lý đồng thời và lỗi đi đâu**.

Bài thuộc chương **RabbitMQ và AMQP**, đề mục **`@RabbitListener và listener container factory`**. Trọng tâm là kiến trúc Spring AMQP trong Spring Boot, cách xây listener theo production contract, đúng semantics RabbitMQ, không để pool/thread/retry làm mất dữ liệu hoặc nhân đôi side effect.

Sau bài học, bạn có thể:

1. Mô tả đường đi broker queue → consumer channel → listener container → `@RabbitListener` method.
2. Phân biệt annotation, endpoint registry, container, container factory, `RabbitTemplate` và `ConnectionFactory`.
3. Cấu hình factory mặc định và named factory; hiểu `SimpleRabbitListenerContainerFactory` so với `DirectRabbitListenerContainerFactory`.
4. Sử dụng `queues`, `bindings`, `id`, `containerFactory`, arguments, payload converter và method parameters.
5. Chọn concurrency, prefetch, consumer acknowledgement mode, transaction boundaries và retry/DLQ policy.
6. Thiết kế consumer idempotent, handle duplicate/redelivery, poison message và unknown downstream outcome.
7. Tách rõ broker publisher confirm với consumer ACK.
8. Kiểm thử bằng RabbitMQ Testcontainers, quan sát listener lifecycle, queue depth, unacked và lỗi.
9. Vận hành credential/TLS, schema evolution, backpressure, graceful shutdown và deployment rolling.

> **Điểm cốt lõi:** `@RabbitListener` chỉ mô tả endpoint tiêu thụ. **Container factory** cấu hình cách chạy listener, còn **listener container** thực thi vòng đời nhận/ACK/retry. Consumer ACK không tự chứng minh transaction bên ngoài RabbitMQ đã commit nếu thứ tự thực hiện bị sai.

## 1. Kiến trúc tổng thể

~~~mermaid
flowchart LR
    P["Order Service / RabbitTemplate"] --> X["Exchange: orders.events"]
    X -->|"order.confirmed"| Q["Queue: inventory.order-confirmed"]
    Q --> B["RabbitMQ consumer deliveries"]
    B --> C["Listener Container"]
    C --> M["Message Converter / Argument Resolver"]
    M --> L["@RabbitListener method"]
    L --> S["Inventory application service"]
    S --> D["PostgreSQL + Inbox"]
    C -. "ACK / NACK / reject" .-> Q
    C -. "Retry / error handler" .-> E["DLQ or retry topology"]
~~~

Các thành phần khác vai trò:

| Thành phần | Đối tượng Spring | Trách nhiệm |
| --- | --- | --- |
| Publisher | `RabbitTemplate` | Gửi message tới exchange/routing key |
| Connection resource | AMQP `ConnectionFactory`, thường `CachingConnectionFactory` | Tạo/cache connections và channels |
| Listener declaration | `@RabbitListener` | Chỉ định queue/binding, method, listener ID, container factory |
| Factory | `RabbitListenerContainerFactory` | Tạo container với thiết lập chung |
| Container runtime | `SimpleMessageListenerContainer` hoặc `DirectMessageListenerContainer` | Quản lý consumer threads/channels/ACK/lifecycle |
| Argument conversion | `MessageConverter` và message handler adapters | Chuyển AMQP message sang DTO/method arguments |
| Business logic | `OrderProjectionService` | Validate, transaction, side effects, idempotency |
| Registry | `RabbitListenerEndpointRegistry` | Tìm, start/stop listener containers do annotation đăng ký |
| Error/retry | Error handler, advice, retry policy, DLX/DLQ | Phân loại lỗi và giữ khả năng khôi phục |

**Một factory không phải một connection pool.** `SimpleRabbitListenerContainerFactory` tạo và cấu hình containers; `CachingConnectionFactory` là lớp hạ tầng quản lý AMQP connections/channels. Một container có thể tạo nhiều AMQP consumers và channels theo concurrency.

### 1.1. Phân biệt publish và consume

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as RabbitMQ
    participant C as Listener Container
    participant D as Database
    P->>B: Publish event E-100
    B-->>P: Publisher confirm ACK (nếu bật)
    B->>C: Deliver event E-100
    C->>D: Business transaction + inbox
    D-->>C: COMMIT
    C-->>B: Consumer ACK
    Note over P,C: Publisher confirm != Consumer ACK
~~~

Một `RabbitTemplate.convertAndSend(...)` return thành công hoặc publisher confirm ACK **không cho biết** `@RabbitListener` đã chạy. Ngược lại, consumer được giao message **không cho biết** DB đã commit. Trên dashboard phải tách producer confirmed, consumer delivered, business applied và consumer acknowledged.

## 2. Phụ thuộc và cấu hình khởi đầu

### 2.1. Spring AMQP starter

Với Spring Boot 3.x/Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'

    // Nếu consumer ghi PostgreSQL:
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    // Nếu dùng Actuator:
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:rabbitmq'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
}
~~~

Một số cấu hình retry yêu cầu `spring-retry` trong dependency graph; kiểm tra starter/version thực tế. Spring Boot 4/Spring AMQP phiên bản mới có thể thay đổi package/starter/test support hoặc converter API: dùng BOM của project thay vì trộn thư viện theo bài viết cũ.

### 2.2. Connection properties

~~~yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST:localhost}
    port: ${RABBITMQ_PORT:5672}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    virtual-host: ${RABBITMQ_VHOST:/}
    connection-timeout: 5s

app:
  messaging:
    orders:
      queue: inventory.order-confirmed
~~~

Ví dụ dùng biến môi trường cho credentials. Với production có TLS, cấu hình SSL/trust/client certificate theo Spring Boot/AMQP version, xác minh hostname và CA; không coi port 5672 mặc định có TLS. Không log credentials hoặc connection URI chứa password.

### 2.3. Boot auto-configuration và @EnableRabbit

Với Spring Boot và starter AMQP, hạ tầng `@RabbitListener`, `ConnectionFactory` và listener container factory mặc định thường được cấu hình theo điều kiện. Trong **Spring Framework thuần**, thường cần `@EnableRabbit` để đăng ký xử lý annotation.

Khi tự cấu hình, điều cần xác minh là:

- `RabbitListenerAnnotationBeanPostProcessor` đã xử lý annotation.
- Có bean `RabbitListenerContainerFactory` phù hợp.
- Queue/binding tồn tại hoặc có người chịu trách nhiệm khai báo.
- Converter và error handling đúng contract.
- Container đã start và broker ACL cho phép consume.

Đừng thêm nhiều bean factories/`@EnableRabbit` theo cảm tính rồi bỏ qua cấu hình Boot đã áp dụng. Nếu tự tạo factory thủ công, các properties ở `spring.rabbitmq.listener.*` **không tự động được áp lên factory đó** nếu không dùng configurer hoặc tự map.

## 3. Listener tối thiểu: @RabbitListener(queues=...)

Một DTO JSON cho command/event:

~~~java
// OrderConfirmedEvent.java
import java.time.Instant;

public record OrderConfirmedEvent(
        String eventId,
        String orderId,
        long aggregateVersion,
        Instant occurredAt) {
}
~~~

Listener:

~~~java
// OrderConfirmedListener.java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConfirmedListener {

    private final InventoryReservationService service;

    public OrderConfirmedListener(
            InventoryReservationService service) {
        this.service = service;
    }

    @RabbitListener(
            id = "inventory-order-consumer",
            queues = "${app.messaging.orders.queue}")
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        service.reserveIdempotently(event);
    }
}
~~~

`InventoryReservationService` là application service cần định nghĩa, ví dụ lưu reservation + inbox trong một SQL transaction. Để JSON được chuyển thành record, phải có `MessageConverter` tương thích hoặc được cấu hình từ auto-configuration.

**`queues` chỉ subscription tới queue có tên**. Không có nghĩa Spring chắc chắn tự khai báo queue: nếu topology được provision bởi IaC/RabbitAdmin thì listener sẽ consume queue tương ứng; nếu queue chưa tồn tại, container có thể retry declaration/khởi động lỗi tùy cấu hình.

### 3.1. Listener endpoint ID

`id = "inventory-order-consumer"` dùng để theo dõi/điều khiển container qua `RabbitListenerEndpointRegistry`. Nó không phải RabbitMQ consumer tag bắt buộc và không phải khóa idempotency. Dùng ID ổn định, rõ chức năng để logs/metrics và vận hành dễ nhận diện.

### 3.2. Chọn queue theo cấu hình

Sử dụng placeholder:

~~~java
@RabbitListener(
        queues = "${app.messaging.orders.queue}",
        id = "inventory-order-consumer")
public void handle(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

Giá trị queue qua environment cho phép đổi theo môi trường. Tuy nhiên **đừng để user nhập tùy ý tên queue** qua request: queue là topology và permission boundary do ứng dụng/ops quản lý.

### 3.3. Queue đã tồn tại khác queue được khai báo

Có hai chiến lược:

1. **Infrastructure-managed topology:** Terraform/Helm/operator/management API tạo exchange/queue/bindings trước deploy, listener chỉ consume.
2. **Application-managed topology:** cấu hình `Queue`, `Exchange`, `Binding` beans để `RabbitAdmin` khai báo khi thích hợp.

Chọn rõ ownership. Không để hai ứng dụng khai báo cùng queue tên nhưng khác arguments (durable, queue type, DLX, TTL), vì RabbitMQ có thể trả `PRECONDITION_FAILED` nếu thuộc tính không tương thích.

## 4. Khai báo topology bằng beans

~~~java
// OrdersRabbitTopology.java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrdersRabbitTopology {

    @Bean
    TopicExchange ordersExchange() {
        return new TopicExchange(
                "orders.events", true, false);
    }

    @Bean
    Queue inventoryOrdersQueue() {
        return QueueBuilder
                .durable("inventory.order-confirmed")
                .deadLetterExchange("orders.dlx")
                .deadLetterRoutingKey("inventory.order.failed")
                .build();
    }

    @Bean
    Binding inventoryOrdersBinding(
            Queue inventoryOrdersQueue,
            TopicExchange ordersExchange) {
        return BindingBuilder.bind(inventoryOrdersQueue)
                .to(ordersExchange)
                .with("order.confirmed");
    }
}
~~~

Code chỉ khai báo queue chính có DLX arguments; **muốn thực sự giữ rejected messages** thì phải có `orders.dlx`, dead-letter queue và binding phù hợp. Nếu exchange DLX thiếu hoặc không route, message có thể bị mất khi reject theo broker policy. Production cần kiểm tra DLX/queue type/persistence.

Với spring AMQP, `RabbitAdmin` có thể tự khai báo các beans `Queue`/`Exchange`/`Binding` khi connection được tạo, nếu nó tồn tại và auto-declaration bật. Việc cấu hình beans không có nghĩa declarations sẽ luôn thành công: quyền `configure`, broker availability, existing topology và policy có thể khiến khai báo thất bại.

### 4.1. Có thể khai báo bằng annotation bindings

Ví dụ khác thay vì `@Bean` topology:

~~~java
import org.springframework.amqp.rabbit.annotation.Queue;
import org.springframework.amqp.rabbit.annotation.Exchange;
import org.springframework.amqp.rabbit.annotation.QueueBinding;
import org.springframework.amqp.rabbit.annotation.RabbitListener;

@RabbitListener(
        id = "inventory-order-consumer",
        bindings = @QueueBinding(
                value = @Queue(
                        value = "inventory.order-confirmed",
                        durable = "true"),
                exchange = @Exchange(
                        value = "orders.events",
                        type = "topic",
                        durable = "true"),
                key = "order.confirmed"))
public void consume(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

Đây là **cách thay thế** topological beans, không copy cùng lúc rồi để hai nguồn cùng quản lý queue nếu chúng khai báo khác arguments. Annotation trong Spring AMQP cho phép khai báo binding topology; giới hạn/attributes thay đổi theo version.

### 4.2. Exchange, queue, routing key và consumer group

RabbitMQ không dùng Kafka consumer group/offset theo cùng nghĩa:

- Producer gửi vào **exchange**.
- Exchange route tới queue theo binding key/type.
- Nhiều consumers trên **cùng queue** thường cạnh tranh lấy deliveries.
- Nếu hai ứng dụng cần mỗi bên nhận cùng một event, mỗi bên nên có queue riêng cùng bind đến exchange.
- Consumer acknowledgement xử lý delivery trong queue; không phải commit offset của một Kafka consumer group.

Ví dụ `inventory.order-confirmed` và `billing.order-confirmed` là hai queues riêng, cùng bind routing key `order.confirmed` để mỗi service nhận một bản logical event.

## 5. Listener container factory là gì?

`RabbitListenerContainerFactory` chịu trách nhiệm tạo container cho một endpoint `@RabbitListener`. Một application có thể có nhiều factories với những chính sách khác nhau:

- Inventory events cần throughput cao: nhiều concurrent consumers, prefetch có giới hạn, auto ack sau xử lý.
- Payment commands cần tuần tự/độ tin cậy cao: concurrency thấp, manual ack, strict idempotency.
- Batch telemetry cần batching, converter/handler riêng.
- Dead-letter repair queue cần consumer độc lập, retry và traffic limits khác.

Container factory là **configuration blueprint**, không trực tiếp là một AMQP consumer.

### 5.1. Tách ba tầng

~~~text
@RabbitListener method (endpoint definition)
            |
            v
RabbitListenerContainerFactory (configuration)
            |
            v
MessageListenerContainer (runtime consumer(s))
            |
            v
AMQP ConnectionFactory → Connection / Channel(s)
            |
            v
RabbitMQ Queue
~~~

Đừng gán `AcknowledgeMode.MANUAL` lên `RabbitTemplate` rồi kỳ vọng listener đổi mode; publisher template và consumer container có trách nhiệm riêng.

### 5.2. Factory mặc định

Spring Boot thường cung cấp một factory tên `rabbitListenerContainerFactory` khi cấu hình phù hợp. `@RabbitListener` **không chỉ rõ** `containerFactory` sẽ sử dụng factory mặc định theo hạ tầng đăng ký endpoint.

Ví dụ:

~~~java
@RabbitListener(queues = "inventory.order-confirmed")
public void consume(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

Tên queue vẫn phải tồn tại/được declare. Nếu đã tự định nghĩa factory cùng tên nhưng bỏ qua `SimpleRabbitListenerContainerFactoryConfigurer`, một số properties từ Boot có thể không áp dụng.

## 6. SimpleRabbitListenerContainerFactory: lựa chọn phổ biến

`SimpleRabbitListenerContainerFactory` tạo `SimpleMessageListenerContainer` (SMLC), một implementation lâu đời, ổn định và linh hoạt. SMLC dùng cơ chế xử lý deliveries thông qua consumer/worker threads/container executors. Nó hỗ trợ điều chỉnh số consumers, prefetch, acknowledgements và các thiết lập liên quan.

### 6.1. Cấu hình qua application.yml

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: auto
        concurrency: 3
        max-concurrency: 8
        prefetch: 20
        default-requeue-rejected: false

app:
  messaging:
    orders:
      queue: inventory.order-confirmed
~~~

Ý nghĩa:

| Property | Vai trò | Lưu ý |
| --- | --- | --- |
| `acknowledge-mode: auto` | Container tự ACK sau handler hoàn tất | Không phải RabbitMQ auto-ack-on-delivery |
| `concurrency: 3` | Số concurrent consumers tối thiểu/ban đầu | Tăng tải DB/CPU tương ứng |
| `max-concurrency: 8` | Upper bound khi SMLC mở rộng động | Không bảo đảm luôn có 8 threads |
| `prefetch: 20` | Số deliveries chưa ACK có thể được giao theo consumer/channel semantics | Tổng in-flight tăng với concurrency |
| `default-requeue-rejected: false` | Mặc định từ chối không requeue khi listener lỗi | Cần DLX/DLQ nếu muốn giữ message |
| Retry settings | Policy retry ở application/container | Không bật retry vô hạn theo mặc định |

**Điểm rất dễ nhầm:** Spring container `AUTO` nghĩa là **client library/container tự gửi consumer ACK sau khi method xử lý thành công**. RabbitMQ broker auto-ack-on-delivery tương ứng với `AcknowledgeMode.NONE` trong Spring AMQP. Chọn sai có thể làm mất message khi handler crash.

### 6.2. Factory tùy chỉnh nhưng giữ Boot defaults

~~~java
// OrdersListenerConfig.java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrdersListenerConfig {

    @Bean("ordersListenerContainerFactory")
    SimpleRabbitListenerContainerFactory ordersFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory =
                new SimpleRabbitListenerContainerFactory();

        // Áp các thiết lập từ spring.rabbitmq.listener.simple.*
        configurer.configure(factory, connectionFactory);

        // Chính sách riêng của endpoint này:
        factory.setConcurrentConsumers(3);
        factory.setMaxConcurrentConsumers(8);
        factory.setPrefetchCount(20);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false);

        return factory;
    }
}
~~~

`SimpleRabbitListenerContainerFactoryConfigurer` là helper của Spring Boot; package có thể đổi ở Boot 4, vì vậy kiểm tra Javadoc/BOM phiên bản đang dùng. Với Boot 3.x, cấu trúc import minh họa là phổ biến.

**Chủ đích:** sử dụng `configurer.configure(...)` **trước** khi override options cục bộ, để không đánh mất connection, converter/retry/observation settings được Boot hỗ trợ. Một factory tự tạo bằng `new SimpleRabbitListenerContainerFactory()` rồi chỉ gọi `setConnectionFactory` có thể bỏ sót cấu hình quan trọng.

### 6.3. Gán factory theo listener

~~~java
@RabbitListener(
        id = "inventory-order-consumer",
        queues = "${app.messaging.orders.queue}",
        containerFactory = "ordersListenerContainerFactory")
public void onMessage(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

Tên `containerFactory` phải trùng **bean name** của factory, không phải tên class. Nếu bean không tồn tại, ứng dụng có thể lỗi khi đăng ký endpoint/khởi động.

### 6.4. Annotation concurrency override

Một số phiên bản cho phép:

~~~java
@RabbitListener(
        id = "order-consumer",
        queues = "inventory.order-confirmed",
        concurrency = "2-6")
public void receive(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

Với SMLC, biểu thức kiểu `2-6` biểu diễn min/max concurrency theo các phiên bản hỗ trợ. Với DMLC, semantics là consumers-per-queue và có thể yêu cầu số nguyên; kiểm tra implementation/version. Không cấu hình hai nguồn concurrency mâu thuẫn mà không hiểu precedence.

## 7. DirectRabbitListenerContainerFactory: khi nào chọn?

`DirectRabbitListenerContainerFactory` tạo `DirectMessageListenerContainer` (DMLC). Nó xử lý deliveries khác SMLC, thường dùng RabbitMQ client consumer threads trực tiếp hơn và có semantics về `consumersPerQueue` thay vì min/max adaptive concurrent consumers.

| Chủ đề | Simple (SMLC) | Direct (DMLC) |
| --- | --- | --- |
| Factory | `SimpleRabbitListenerContainerFactory` | `DirectRabbitListenerContainerFactory` |
| Container | `SimpleMessageListenerContainer` | `DirectMessageListenerContainer` |
| Concurrency | `concurrentConsumers`, `maxConcurrentConsumers` | `consumersPerQueue` |
| Dynamic scaling | Cơ chế tăng/giảm consumer theo chính sách SMLC | Số consumers per queue do container quản lý |
| Thread model | Container/worker execution model | Gắn chặt hơn với client consumer execution |
| Queue additions/removals | Hỗ trợ theo lifecycle container | DMLC có cơ chế quản lý riêng |
| Tuning | Prefetch, ack, executor, batch, backoff | Prefetch, ack, consumer count, monitor settings |
| Chọn lựa | Mặc định quen thuộc, nhiều khả năng cấu hình | Khi workload/latency/consumer dynamics phù hợp và đã benchmark |

Không kết luận DMLC luôn nhanh hơn hoặc ít threads hơn mà không đo. Sự khác biệt phụ thuộc broker, consumer runtime, payload, DB bottleneck và release Spring AMQP.

### 7.1. Định nghĩa named Direct factory

~~~java
import org.springframework.amqp.rabbit.config.DirectRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.DirectRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;

@Bean("directInventoryListenerFactory")
DirectRabbitListenerContainerFactory directInventoryFactory(
        DirectRabbitListenerContainerFactoryConfigurer configurer,
        ConnectionFactory connectionFactory) {

    var factory =
            new DirectRabbitListenerContainerFactory();
    configurer.configure(factory, connectionFactory);
    factory.setConsumersPerQueue(2);
    factory.setPrefetchCount(25);

    return factory;
}
~~~

Snippet `@Bean` phải đặt trong class `@Configuration`. Sử dụng `DirectRabbitListenerContainerFactoryConfigurer` với Spring Boot version có API tương ứng. Khác với SMLC `setMaxConcurrentConsumers`, DMLC thường chỉnh số consumers per queue bằng `setConsumersPerQueue`.

### 7.2. Listener dùng DMLC

~~~java
@RabbitListener(
        id = "inventory-direct-consumer",
        queues = "inventory.order-confirmed",
        containerFactory = "directInventoryListenerFactory")
public void consume(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

Không **đăng ký đồng thời hai listeners trên cùng queue** chỉ để “test xem factory nào tốt hơn” trong production: chúng trở thành competing consumers, làm thay đổi phân phối messages và khả năng xử lý/ordering. Muốn so sánh, dùng môi trường test hoặc một consumer group/queue tách biệt.

## 8. ConnectionFactory, channel và listener container

RabbitMQ AMQP 0-9-1 sử dụng TCP connection có thể multiplex nhiều channels. Một listener container thường mở consumers trên các channels do `ConnectionFactory` cấp. Spring AMQP phổ biến dùng `CachingConnectionFactory` để cache/reuse connections/channels.

~~~mermaid
flowchart TD
    F["SimpleRabbitListenerContainerFactory"] --> C["SimpleMessageListenerContainer"]
    C --> CF["CachingConnectionFactory"]
    CF --> CON["AMQP TCP/TLS Connection"]
    CON --> CH1["Channel consumer 1"]
    CON --> CH2["Channel consumer 2"]
    CH1 --> Q["Queue"]
    CH2 --> Q
~~~

### 8.1. Không tạo Channel singleton cho cả listener

AMQP `Channel` có lifecycle, delivery tags, confirms, transactions và thread-safety constraints. Trong manual ACK, delivery tag gắn với **channel nhận delivery**; ACK trên channel khác hoặc sau khi channel đóng có thể báo lỗi protocol.

**Không lưu một `Channel` vào static field rồi dùng từ worker threads khác**. Listener container quản lý channels, concurrency và recovery; method chỉ sử dụng `Channel` được cung cấp cho delivery hiện tại nếu manual ACK.

### 8.2. Connection/channel cache khác concurrency

`spring.rabbitmq.cache.channel.size` là giá trị **cache channel**, không tương đương tối đa tuyệt đối số consumers. Nếu đặt listener concurrency 12, RabbitMQ có thể cần ít nhất số channels tương ứng; channel cache nhỏ có thể ảnh hưởng churn khi consumers/tasks thay đổi nhưng không tự giới hạn concurrency theo cách bạn muốn.

Với toàn cluster, số connections/channels có thể tăng theo replicas × listeners × concurrency. Cần tính budget tổng, broker memory/FD limits và maximum consumers.

### 8.3. Reconnect và auto recovery

Spring AMQP connection factory/container có cơ chế recovery/redeclare phù hợp. Không tự bật đồng thời tất cả automatic recovery của RabbitMQ Java Client và Spring recovery theo cách dẫn đến xung đột nếu framework đã quản lý. Khi broker disconnect:

- In-flight/unacked messages có thể bị redeliver.
- Listener container có thể khởi tạo lại consumers.
- Queue/binding declaration có thể được thực hiện lại theo RabbitAdmin policy.
- Consumer cần idempotent vì replay là hành vi bình thường.

Recovery không có nghĩa không mất message khi queue không durable, publisher không confirm hoặc message đã ACK trước commit nghiệp vụ.

## 9. Message converter và method arguments

Một `@RabbitListener` method không chỉ nhận raw bytes. Spring AMQP có **AMQP MessageConverter** và method argument resolvers để chuyển body/headers thành DTO, `Message`, `Channel` hoặc `@Header`.

### 9.1. Converter JSON

Ví dụ cho Spring AMQP 3.x:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;

@Bean
MessageConverter rabbitJsonConverter(ObjectMapper objectMapper) {
    return new Jackson2JsonMessageConverter(objectMapper);
}
~~~

Snippet đặt trong class cấu hình. Với Spring AMQP 4.x/Spring Boot 4, họ Jackson converter có thể được đổi/tái tổ chức; kiểm tra class thay thế phù hợp (ví dụ converter dựa trên Jackson 3) và runtime Jackson version.

Khi listener dùng một factory tự tạo, có thể cần gọi `factory.setMessageConverter(rabbitJsonConverter)` hoặc để Boot configurer áp dụng converter bean theo version và cấu hình. **Producer và consumer phải thống nhất Content-Type, schema và JSON field names**, không chỉ cùng dùng thư viện Jackson.

### 9.2. Header và raw AMQP Message

~~~java
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;

@RabbitListener(queues = "inventory.order-confirmed")
public void handle(
        OrderConfirmedEvent payload,
        @Header(AmqpHeaders.RECEIVED_ROUTING_KEY)
        String routingKey,
        Message raw) {

    validateRoutingKey(routingKey);
    service.reserveIdempotently(payload);
}
~~~

`validateRoutingKey(...)` minh họa domain-specific validation. Trong một method listener, signatures hợp lệ phụ thuộc converter/argument resolver version; nếu không cần raw body, ưu tiên typed payload để dễ test. **Không log raw body** nếu chứa PII/credential.

### 9.3. @Payload, @Header và MessageHeaders

Có thể annotate:

~~~java
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.Header;

@RabbitListener(queues = "inventory.order-confirmed")
public void handle(
        @Payload OrderConfirmedEvent event,
        @Header(name = "schema-version", required = false)
        Integer schemaVersion) {

    checkCompatibleSchema(schemaVersion);
    service.reserveIdempotently(event);
}
~~~

Header tên `schema-version` là contract ứng dụng, producer phải set tương ứng. Nếu header thiếu, logic xử lý backward compatibility cần được thiết kế; không default sang version mới nhất một cách mù quáng.

### 9.4. JSON TypeId headers và security

Khi chuyển JSON, Spring AMQP converter có thể dùng type headers (ví dụ `__TypeId__`), inferred method type và class mapper. Không tin một class name tùy ý từ untrusted producer để instantiate arbitrary Java types. Cấu hình trusted packages/class mappings hoặc để target DTO type tường minh, validate schema và giới hạn payload size.

Tránh Java native serialization cho messages nhận từ hệ thống không đáng tin. Đảm bảo không có secret/token trong JSON payload hoặc DLQ logs.

### 9.5. Method overload và @RabbitHandler

Một class có thể dùng `@RabbitListener` ở cấp class và nhiều methods `@RabbitHandler` để dispatch theo payload type, nếu converters/type mapping đúng:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitHandler;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
@RabbitListener(queues = "inventory.events")
public class InventoryEventHandlers {

    @RabbitHandler
    public void onConfirmed(OrderConfirmedEvent event) {
        // Xử lý OrderConfirmedEvent.
    }

    @RabbitHandler
    public void onCancelled(OrderCancelledEvent event) {
        // Xử lý OrderCancelledEvent.
    }
}
~~~

`OrderCancelledEvent` là DTO minh họa. Routing theo Java runtime payload type đòi converter biết type chính xác. Với public event contracts có nhiều versions, một single envelope record + `eventType` và explicit version dispatch thường dễ quản trị hơn relying solely on Java class headers.

## 10. AcknowledgeMode.AUTO, MANUAL và NONE

Consumer acknowledgement là một trong những quyết định quan trọng nhất của container.

| Spring mode | Broker semantics | Khi nào ACK? | Rủi ro |
| --- | --- | --- | --- |
| `AUTO` | Consumer **manual ACK** được container điều khiển | Sau handler return thành công (theo lifecycle/error policy) | Nếu method trả trước khi async work hoàn tất, có thể ACK sớm |
| `MANUAL` | Ứng dụng gọi `basicAck`/`basicNack`/`basicReject` | Khi business logic quyết định | Quên ACK khiến unacked tích tụ; ACK nhầm channel/tag |
| `NONE` | RabbitMQ auto-ack-on-delivery | Khi broker giao message | Crash trong handler có thể mất message |

**AUTO không đồng nghĩa RabbitMQ auto ack.** Tên mode AUTO ở Spring có nghĩa container làm việc thay bạn; broker vẫn cần consumer ACK sau khi listener xử lý thành công.

### 10.1. AUTO phù hợp khi handler đồng bộ

~~~java
@RabbitListener(
        id = "order-consumer",
        queues = "inventory.order-confirmed",
        containerFactory = "ordersListenerContainerFactory")
public void consume(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

Nếu `service.reserveIdempotently` là synchronous method có `@Transactional` được gọi qua Spring proxy, transaction commit trước khi method return. Khi listener return thành công, container có thể ACK. Nếu DB commit thành công nhưng ACK bị mất, broker có thể redeliver; đó là lý do service phải idempotent.

### 10.2. MANUAL với ACK sau DB commit

Tạo factory riêng:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;

@Bean("manualOrderListenerFactory")
SimpleRabbitListenerContainerFactory manualFactory(
        ConnectionFactory connectionFactory,
        SimpleRabbitListenerContainerFactoryConfigurer configurer) {

    var factory = new SimpleRabbitListenerContainerFactory();
    configurer.configure(factory, connectionFactory);
    factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
    factory.setPrefetchCount(10);
    factory.setDefaultRequeueRejected(false);
    return factory;
}
~~~

Listener method:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;

@RabbitListener(
        id = "order-manual-consumer",
        queues = "inventory.order-confirmed",
        containerFactory = "manualOrderListenerFactory")
public void consume(
        OrderConfirmedEvent event,
        Channel channel,
        @Header(AmqpHeaders.DELIVERY_TAG) long deliveryTag)
        throws IOException {

    // Đồng bộ, @Transactional tại service: COMMIT trước khi return.
    service.reserveIdempotently(event);

    // ACK đúng delivery trên đúng channel, sau thành công.
    channel.basicAck(deliveryTag, false);
}
~~~

**Snippet minh họa happy path.** Với `MANUAL`, ứng dụng phải thiết kế **error path** rõ cho exceptions trước khi có thể ACK, message conversion failure trước khi method chạy, shutdown và nack/reject. Không giả định exception trong manual handler tự được ACK/NACK đúng ý trong mọi version/error handler.

### 10.3. Manual NACK/Reject và DLX

~~~java
try {
    service.reserveIdempotently(event);
    channel.basicAck(deliveryTag, false);
} catch (PermanentBusinessValidationException ex) {
    // Không requeue; DLX nếu queue đã cấu hình.
    channel.basicReject(deliveryTag, false);
} catch (TransientDatabaseException ex) {
    // Không requeue ngay để tránh vòng lặp nóng;
    // chuyển retry theo topology/durable backoff đã thiết kế.
    channel.basicNack(deliveryTag, false, false);
}
~~~

`PermanentBusinessValidationException` và `TransientDatabaseException` là application exceptions minh họa. Đoạn trên chỉ hợp lệ khi retry/DLX topology đã có và failure được persist/parked theo chính sách. Với broker không có DLX hoặc DLX không route, reject/nack `requeue=false` có thể làm message bị loại bỏ.

Với lỗi xảy ra ở `channel.basicAck` sau DB COMMIT, có thể không biết broker đã nhận ACK chưa. Không gọi ACK trên channel khác; dùng idempotency và chấp nhận redelivery khi cần.

### 10.4. NONE chỉ cho dữ liệu có thể mất

`AcknowledgeMode.NONE` để broker tự xác nhận delivery. Nó có thể phù hợp với telemetry fire-and-forget có thể mất, nhưng không phù hợp để đảm bảo đặt hàng, thanh toán, cập nhật tồn kho hoặc outbox processing.

## 11. Transaction boundary với SQL và AMQP

Hai transactions thường bị hiểu lẫn:

- **Local SQL transaction** do `@Transactional` và JDBC/JPA transaction manager quản lý.
- **AMQP channel transaction** khi cấu hình `channelTransacted=true`, có commit/rollback riêng ở broker.

Một `@Transactional` gắn trên service dùng DataSource **không tự tạo distributed ACID transaction** giữa PostgreSQL và RabbitMQ. Spring AMQP có cơ chế đồng bộ với transaction manager trong một số cấu hình, nhưng vẫn có failure window; không coi là XA/global exactly-once nếu không triển khai giao thức/resource support tương ứng.

### 11.1. Service @Transactional + AUTO ack

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryReservationService {

    private final InventoryRepository inventory;
    private final ProcessedEventRepository inbox;

    public InventoryReservationService(
            InventoryRepository inventory,
            ProcessedEventRepository inbox) {
        this.inventory = inventory;
        this.inbox = inbox;
    }

    @Transactional
    public void reserveIdempotently(OrderConfirmedEvent event) {
        if (!inbox.tryInsert("inventory", event.eventId())) {
            return;
        }

        inventory.reserve(
                event.orderId(),
                event.aggregateVersion());
    }
}
~~~

`InventoryRepository` và `ProcessedEventRepository` là application-specific; `tryInsert` phải dùng unique constraint/atomic insert trong **cùng SQL transaction** với `inventory.reserve`. Không thực hiện `SELECT exists` rồi insert mà thiếu unique key, vì concurrency gây race.

Với AUTO ACK: listener gọi service đồng bộ; method service return sau khi transaction commit thành công theo Spring proxy; container sau đó ACK. Nếu COMMIT fail thì handler báo lỗi, message không nên bị ACK thành công.

### 11.2. Crash sau SQL commit trước consumer ACK

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant C as Listener
    participant D as PostgreSQL
    B->>C: Deliver eventId=E-123
    C->>D: INSERT inbox + business update
    D-->>C: COMMIT OK
    C--xB: ACK lost / process crash
    B->>C: Redelivery E-123
    C->>D: Inbox sees E-123 already processed
    C-->>B: ACK duplicate safely
~~~

Đây là **at-least-once**. Không phải lỗi broker, mà là một failure window bình thường; unique event ID/inbox giúp giữ business side effect không lặp.

### 11.3. ACK trước COMMIT gây mất nghiệp vụ

~~~text
Delivery received
    ↓
ACK gửi tới broker
    ↓
SQL INSERT/UPDATE
    ↓
Process crash hoặc transaction rollback
    ↓
Broker không còn message để tự redeliver
~~~

Tránh ACK sớm. Nếu handler chỉ đẩy việc vào executor RAM rồi return, AUTO có thể ACK mặc dù công việc chưa hoàn tất. Muốn tách worker async, **ghi durable work item/outbox** rồi ACK source.

### 11.4. HTTP partner side effects

Nếu consumer vừa cập nhật SQL vừa gọi Payment API, remote HTTP không thuộc SQL transaction. Nếu Payment đã xử lý nhưng response timeout, retry có thể tính phí hai lần. Tách thành local SQL inbox + outbox intent, sau commit worker gọi Payment với idempotency key/status lookup.

## 12. Prefetch, concurrency và capacity planning

Prefetch điều khiển số deliveries **chưa ACK** RabbitMQ có thể đẩy tới consumer/channel theo QoS semantics. Concurrency điều khiển số consumers đang hoạt động.

Ví dụ:

~~~text
concurrency = 4
prefetch = 20
=> có thể có tới khoảng 80 deliveries in-flight
   (theo topology/channel/QoS và runtime thực tế)
~~~

Đây không có nghĩa 80 Java handlers chắc chắn chạy song song. Một số deliveries có thể nằm trong client/container buffers chờ xử lý.

### 12.1. Sizing theo downstream DB

Giả sử Inventory Service có:

| Resource | Giới hạn minh họa |
| --- | ---: |
| Hikari JDBC pool per pod | 12 connections |
| Rabbit listener concurrent consumers | 6 |
| Rabbit prefetch per consumer | 20 |
| Pod replicas | 4 |
| DB max usable connections toàn service | 60 |

Bốn pods × 6 consumers = 24 handlers đồng thời có thể chạm DB, chưa kể HTTP requests/jobs. Pool 12 per pod không tự là bottleneck nếu transactions ngắn, nhưng có thể bị cạn nếu calls giữ locks lâu. Bốn pods × 6 × 20 ≈ 480 deliveries in flight theo lý thuyết; sau crash có thể được redeliver.

### 12.2. Prefetch quá lớn

Rủi ro:

- Một consumer giữ nhiều deliveries làm message phân phối không đều.
- Crash khiến nhiều messages cần redelivery.
- Tăng memory pressure.
- Poison message chặn processing nếu ordering và retry sai.
- Khó đo backlog vì queue "ready" giảm nhưng "unacked" tăng.

Với xử lý chậm/đắt, bắt đầu với prefetch vừa phải và đo; với workload xử lý nhanh, có thể tăng khi broker/client overhead thực sự là bottleneck.

### 12.3. Concurrency không phải global ordering

Nhiều competing consumers trong cùng queue làm **completion order** không chắc trùng publish order. Dù broker giữ FIFO order ở queue trong những điều kiện nhất định, concurrency, priorities, requeue, redelivery và retries có thể thay đổi thứ tự hoàn tất.

Nếu cùng `orderId` phải xử lý version 1 → 2 → 3, ứng dụng cần aggregate version guard, consistent routing/sharding hoặc chiến lược tuần tự thích hợp. Đặt concurrency=1 có thể giảm cạnh tranh trong một queue nhưng không tự giải quyết replay/duplicate/out-of-order giữa nhiều queues hoặc instances.

### 12.4. Exclusive consumer

RabbitMQ có exclusive consumer option cho một queue; không kết hợp bừa với concurrency >1. Exclusive consumer giúp một connection có quyền nhận delivery theo điều kiện broker nhưng không phải distributed business lock hay exactly-once mechanism.

## 13. Container retry vs broker redelivery

Một lỗi listener có thể được retry **trong cùng process trước khi NACK**, hoặc được broker redeliver **sau khi message bị requeue**. Hai vòng khác nhau.

~~~mermaid
flowchart TD
    D["RabbitMQ delivery"] --> L["Listener invocation"]
    L --> O{"Kết quả"}
    O -->|"Success"| A["ACK"]
    O -->|"Transient failure"| R["Bounded local retry / delayed queue"]
    O -->|"Permanent failure"| P["Reject and park/DLQ"]
    R --> L
    R -->|"Budget exhausted"| P
~~~

Không dùng retry ở mọi lớp mà không có ngân sách: Spring Retry advice × RabbitMQ requeue × scheduler replay × downstream HTTP retry có thể tạo nhiều attempts, gây bão tải và duplicate.

### 13.1. Retry trong listener container

Spring Boot cung cấp properties để bật retry cho simple/direct listener (cấu hình phụ thuộc phiên bản):

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        retry:
          enabled: true
          max-attempts: 3
          initial-interval: 500ms
          multiplier: 2
          max-interval: 5s
        default-requeue-rejected: false
~~~

Điều này minh họa **bounded retry** trước khi lỗi được chuyển sang chính sách final rejection. Cần bảo đảm có DLX/DLQ/parking phù hợp, vì requeue=false không giữ message nếu queue không có tuyến dead-letter hoạt động.

Spring Retry thường thực hiện **local retry** trên consumer thread: khi attempt đang sleep/backoff, thread/slot vẫn bị chiếm. Với retries dài hàng phút hoặc nhiều poison messages, dùng **delayed retry topology** để không giữ threads.

### 13.2. Config retry advice code

Ví dụ với Spring AMQP/Spring Retry version hỗ trợ:

~~~java
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.aopalliance.aop.Advice;

Advice retryAdvice =
        RetryInterceptorBuilder.stateless()
                .maxAttempts(3)
                .backOffOptions(500, 2.0, 5000)
                .recoverer(new RejectAndDontRequeueRecoverer())
                .build();

// Trong named SimpleRabbitListenerContainerFactory bean:
factory.setAdviceChain(retryAdvice);
~~~

Snippet giả định `factory` đã được tạo và gắn connection factory; đây là một **lựa chọn thay cho** Boot retry property, không nên vô tình bật cả hai cơ chế cùng chính sách rồi nhân số attempts.

**Stateless retry** phù hợp nhiều handlers đơn giản; với transactional semantics, stateful retry và transaction rollback behavior phức tạp hơn. Chọn theo contract, thử nghiệm với DB rollback/requeue thực và không giữ long-running transaction xuyên nhiều retries.

### 13.3. Phân loại lỗi

| Lỗi | Retry? | Gợi ý |
| --- | --- | --- |
| JSON không parse/schema sai | Không nên retry nóng | DLQ/parking và contract remediation |
| Invalid business state | Thường không | Reject nghiệp vụ/audit |
| Missing authorization/tenant mismatch | Không | Security incident |
| SQL deadlock | Có thể | Bounded retry toàn transaction, idempotent |
| DB temporarily unavailable | Có thể | Backoff; đo pool/availability |
| HTTP 429/503 downstream | Có thể | Backoff/bulkhead/circuit breaker |
| HTTP timeout sau side effect | Chỉ nếu idempotent | Unknown outcome, status lookup |
| Broker channel closed | Container recovery | Không tự ACK delivery đã mất channel |
| Duplicate eventId đã xử lý | Không apply lại | ACK thành công sau dedupe |

### 13.4. Default requeue và poison messages

Nếu handler fail và container requeue liên tục, broker có thể redeliver ngay:

~~~text
Receive invalid JSON
  -> listener/converter throws
  -> requeue
  -> receive same invalid JSON
  -> requeue forever
~~~

Để tránh vòng lặp, cần fail-fast permanent errors, retry attempts hữu hạn, DLX/DLQ hoặc delayed retry queues. Spring AMQP có `ConditionalRejectingErrorHandler` và các exceptions như `AmqpRejectAndDontRequeueException`; hành vi chính xác có thể khác giữa conversion failure, listener failure và configured error/recoverer.

## 14. Dead-letter exchange, DLQ và delayed retry

### 14.1. DLX/DLQ minh họa

~~~mermaid
flowchart LR
    X["orders.events exchange"] --> Q["inventory.order-confirmed queue"]
    Q -->|"NACK/reject requeue=false"| DLX["orders.dlx"]
    DLX --> DLQ["inventory.order-failed"]
    DLQ --> OPS["Review / replay worker"]
~~~

Ví dụ khai báo DLX và binding (khi ứng dụng sở hữu topology):

~~~java
import org.springframework.amqp.core.*;

@Bean
DirectExchange ordersDlx() {
    return new DirectExchange("orders.dlx", true, false);
}

@Bean
Queue inventoryDeadQueue() {
    return QueueBuilder.durable("inventory.order-failed").build();
}

@Bean
Binding inventoryDeadBinding(
        Queue inventoryDeadQueue,
        DirectExchange ordersDlx) {
    return BindingBuilder.bind(inventoryDeadQueue)
            .to(ordersDlx)
            .with("inventory.order.failed");
}
~~~

Đặt trong class `@Configuration`. Queue chính đã khai báo `deadLetterExchange("orders.dlx")` và `deadLetterRoutingKey("inventory.order.failed")` ở mục 4; nếu dùng hai đoạn cùng nhau, các tên này phải nhất quán.

**DLQ không tự là business success.** Một message vào DLQ nghĩa là chưa xử lý theo yêu cầu, phải có alert, retention, access control, replay/reconciliation.

### 14.2. Bảo đảm dead-letter durability

Publisher confirm áp dụng publisher → broker; consumer NACK/Reject và broker dead-lettering có semantics riêng phụ thuộc queue type/broker version. Không assume mọi DLX handoff đều exactly-once/durable tuyệt đối.

RabbitMQ quorum queues có các tính năng dead-lettering và delivery-limit khác classic queues, cần xem RabbitMQ version và policy triển khai. Nếu broker/queue không cấu hình DLX phù hợp, `requeue=false` có thể làm mất message.

### 14.3. Delayed retry topology

Có thể dùng retry queues với TTL + DLX về queue chính, hoặc plugin delayed-message exchange nếu broker hỗ trợ. Ví dụ:

~~~text
inventory.order-confirmed
   |
   +-- temporary failure → inventory.retry.30s
           (TTL 30s, DLX quay về exchange chính)
   |
   +-- max attempts → inventory.order-failed DLQ
~~~

Cần **attempt count bền vững**, giới hạn số vòng, idempotency và chống starvation; không chỉ dùng `x-death` không kiểm chứng. Một custom retry publisher phải chờ broker xác nhận việc publish tới retry queue trước khi ACK message nguồn, nếu không có thể mất event giữa hai thao tác.

### 14.4. DLQ replay

Khi replay một message đã sửa lỗi mapping:

1. Kiểm tra nguyên nhân và schema version.
2. Xác nhận side effect trước đó đã commit hay chưa.
3. Giữ **eventId** ổn định.
4. Publish lại vào topology được phê duyệt, ghi audit/replay attempt.
5. Quan sát inbox dedupe và kết quả nghiệp vụ.
6. Không purge queue hoặc sửa routing hàng loạt trước khi đối soát.

## 15. Error handling trước và sau method invocation

Không phải mọi lỗi đều đi vào `try/catch` trong `@RabbitListener`:

- **Broker delivery/connection errors:** xảy ra ở container/channel.
- **Message conversion errors:** xảy ra trước khi method được gọi.
- **Argument resolution/validation errors:** xảy ra khi Spring tạo method arguments.
- **Business exceptions:** ném từ method/service.
- **ACK/NACK failures:** xảy ra sau hoặc quanh method completion.
- **Downstream side-effect uncertainty:** HTTP timeout hoặc transaction commit outcome unknown.

Do đó một `try/catch(Exception)` trong listener **không giải quyết toàn bộ** failure classification. Phải thiết kế container `ErrorHandler`, retry advice, AMQP recoverer và DLX policy.

### 15.1. Không nuốt exception rồi return thành công

~~~java
@RabbitListener(queues = "inventory.order-confirmed")
public void antiPattern(OrderConfirmedEvent event) {
    try {
        service.reserveIdempotently(event);
    } catch (Exception ex) {
        log.warn("Reservation failed", ex);
        // Sai: return bình thường trong AUTO mode có thể ACK message.
    }
}
~~~

Đây là **anti-pattern**. Với AUTO mode, một method return bình thường thường khiến container ACK. Nếu business failed, phải ném lỗi để error handling quyết định retry/NACK/parking, hoặc đã chuyển message một cách **bền vững** sang workflow xử lý khác trước khi ACK.

### 15.2. ErrorHandler và conversion errors

Spring AMQP có `ConditionalRejectingErrorHandler` để phân biệt những lỗi fatal (chẳng hạn lỗi conversion) trong nhiều setup. Có thể customize fatality classification, nhưng cần test kỹ để không vô tình reject một event transient hoặc requeue một poison message mãi.

Nếu JSON không parse được, listener method có thể **không bao giờ được gọi**; một unit test trực tiếp gọi method không chứng minh production behavior. Kiểm thử với AMQP message body Content-Type sai, TypeId header không được tin cậy và payload schema thiếu fields.

### 15.3. Lỗi protocol khác lỗi domain

Nếu queue không tồn tại, connection bị từ chối hoặc consumer không có quyền `read`, cần sửa topology/ACL/credential. Không retry nghiệp vụ từng message để giải quyết một AMQP connection failure.

Nếu domain validation thất bại, cần record rejection/parking theo hợp đồng; không chỉnh queue permissions để “fix” dữ liệu sai.

## 16. Idempotency và transaction inbox

At-least-once delivery nghĩa là **duplicate là chuyện bình thường**:

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant C as Listener
    participant D as PostgreSQL
    B->>C: Deliver E-100
    C->>D: INSERT processed_event + business mutation
    D-->>C: COMMIT
    C--xB: ACK lost
    B->>C: Redeliver E-100
    C->>D: INSERT eventId conflict → already processed
    C-->>B: ACK duplicate
~~~

### 16.1. Database inbox table

~~~sql
CREATE TABLE processed_integration_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Mỗi logical consumer có thể xử lý cùng một event; dùng `consumer_name + event_id` làm unique key để Inventory và Billing độc lập xử lý cùng event.

### 16.2. Cùng SQL transaction với business update

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryReservationService {

    private final JdbcTemplate jdbc;

    public InventoryReservationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserveIdempotently(OrderConfirmedEvent event) {
        int inserted = jdbc.update(
                """
                INSERT INTO processed_integration_events(
                    consumer_name, event_id, processed_at)
                VALUES ('inventory', ?, CURRENT_TIMESTAMP)
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """,
                UUID.fromString(event.eventId()));

        if (inserted == 0) {
            return; // Duplicate: business update đã commit trước đó.
        }

        jdbc.update(
                """
                INSERT INTO inventory_reservations(
                    order_id, source_version, state)
                VALUES (?, ?, 'RESERVED')
                ON CONFLICT (order_id)
                DO UPDATE
                   SET source_version = EXCLUDED.source_version,
                       state = EXCLUDED.state
                 WHERE inventory_reservations.source_version
                       < EXCLUDED.source_version
                """,
                event.orderId(),
                event.aggregateVersion());
    }
}
~~~

Đây là ví dụ PostgreSQL; `inventory_reservations` phải được tạo bằng migration với `order_id` unique, `source_version` thích hợp. Production cần quy tắc domain đầy đủ cho quantity/stock, không chỉ trạng thái RESERVE.

**Quan trọng:** `INSERT inbox` và cập nhật reservation phải nằm trong **cùng transaction**. Nếu SQL update fail, rollback cả inbox insert; nếu không, lần redelivery sẽ bị coi nhầm đã xử lý dù tác động nghiệp vụ chưa được áp dụng.

### 16.3. Out-of-order khác duplicate

Hai events khác nhau có `eventId=E-1` và `eventId=E-2` nhưng cùng `orderId` và version khác nhau. Inbox chặn E-1 được áp dụng lần hai, **không tự chặn** E-1 đến sau E-2. Dùng aggregateVersion/conditional update và domain ordering policy.

### 16.4. EventId không phải delivery tag

`AmqpHeaders.DELIVERY_TAG` là delivery identity thuộc channel, thay đổi qua redelivery; **không** dùng làm business dedupe key. Tương tự, `traceId` có thể thay đổi mỗi attempt; phải có upstream eventId/operationId ổn định từ hợp đồng dữ liệu.

## 17. Message schema, versioning và security

Một event contract nên có:

~~~java
public record OrderConfirmedEvent(
        String eventId,
        String orderId,
        long aggregateVersion,
        java.time.Instant occurredAt) {
}
~~~

Tốt hơn có explicit `eventType` và `schemaVersion` trong envelope/header nếu một queue chứa nhiều event types. Các consumers có thể được deploy lệch versions; cần tương thích dữ liệu:

- Fields optional mới: consumer cũ nên có policy ignore/forward compatibility phù hợp.
- Breaking change: tạo schema version mới, không đổi âm thầm ý nghĩa field cũ.
- Enum unknown: reject/park có lý do hoặc fallback có kiểm soát.
- Decimal/Instant/timezone: định nghĩa format rõ.
- Idempotency key: luôn ổn định qua replay.
- JSON size/depth và field validation: giới hạn trước khi business logic.

### 17.1. Không tin untrusted producer

Broker ACL giới hạn ai có thể publish, nhưng event headers/payload vẫn phải được xác thực theo trust boundary. Không chấp nhận `tenantId`/`role`/`permissions` từ raw JSON như credential để thay authorization. Hạn chế converter type mapping được tin cậy, kiểm soát MIME/content type và không bật unsafe deserialization.

### 17.2. TLS, SASL/credentials và vhost permissions

RabbitMQ có virtual hosts, permissions và TLS. Consumer thường cần:

- Quyền `read` trên queue, và các quyền liên quan tới declarations/bindings nếu app tự quản lý topology.
- Connection URI/vhost chính xác.
- TLS trust, hostname verification và client certificate nếu mTLS.
- Secret manager cho username/password/private key.
- Network egress policy, không mở management port ra internet tùy tiện.

Không log full `amqp://user:password@host/vhost`; không disable TLS verification để xử lý certificate errors.

## 18. Listener lifecycle và RabbitListenerEndpointRegistry

Listener containers thường start khi application context refresh nếu auto-startup bật. Có thể điều khiển lifecycle bằng `RabbitListenerEndpointRegistry`:

~~~java
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;
import org.springframework.amqp.rabbit.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class RabbitListenerOperations {

    private final RabbitListenerEndpointRegistry registry;

    public RabbitListenerOperations(
            RabbitListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isRunning(String id) {
        MessageListenerContainer container =
                registry.getListenerContainer(id);
        return container != null && container.isRunning();
    }

    public void stop(String id) {
        MessageListenerContainer container =
                registry.getListenerContainer(id);
        if (container != null) {
            container.stop();
        }
    }

    public void start(String id) {
        MessageListenerContainer container =
                registry.getListenerContainer(id);
        if (container != null) {
            container.start();
        }
    }
}
~~~

`getListenerContainer(id)` dùng ID của `@RabbitListener`, không phải queue name. Registry chủ yếu quản lý listener containers được tạo qua endpoint infrastructure; custom containers đăng ký thành beans thủ công có thể có lifecycle quản lý khác.

### 18.1. Pause/stop và graceful shutdown

Khi rolling deployment:

1. Ngừng nhận deliveries mới hoặc stop listener containers theo lifecycle.
2. Cho handlers đang xử lý kết thúc trong shutdown grace period.
3. ACK những messages đã business commit; đừng ACK pending work trong RAM.
4. Nếu process dừng trước ACK, broker có thể redeliver; idempotency bảo vệ.
5. Quan sát consumer count và unacked sau rollout.
6. Không dùng queue purge như một bước rollout mặc định.

Chính sách container shutdown timeout và cancellation behavior khác nhau theo implementation/version. Với API xử lý vài phút, cần đánh giá Kubernetes terminationGracePeriodSeconds, JVM shutdown timeout và Rabbit consumer cancellation tương ứng.

### 18.2. Dynamic scaling

SMLC có khả năng điều chỉnh concurrent consumers tùy cấu hình, DMLC có số consumers per queue. Không đổi concurrency không giới hạn ở production để “giải backlog”: broker, JDBC pool, CPU và downstream HTTP đều có capacity limit.

## 19. Batch listeners và xử lý đồng bộ/bất đồng bộ

Spring AMQP hỗ trợ batch-oriented consumption theo factory settings và method signatures phù hợp. Tuy nhiên, batch semantics **khác per-message**:

- Nếu một record trong batch lỗi, policy phải rõ ACK/NACK phạm vi.
- Phải có idempotency từng event, không chỉ batch ID.
- Nếu batch chứa nhiều tenants, giữ authorization/context tách biệt.
- Transaction có thể commit toàn batch hoặc theo item, tùy domain.
- Prefetch và batch size cần được cân đối.

### 19.1. Bẫy async listener

~~~java
@RabbitListener(queues = "inventory.order-confirmed")
public void unsafeAsync(OrderConfirmedEvent event) {
    executor.submit(() -> service.reserveIdempotently(event));
    // Method return ngay -> AUTO có thể ACK trước khi task chạy.
}
~~~

Đây là **anti-pattern** nếu `executor` là RAM queue và yêu cầu at-least-once business processing. Nếu muốn non-blocking, dùng async return types/ack handling được Spring AMQP version hỗ trợ **và** xác minh ACK được thực hiện sau async completion; hoặc ghi durable work item trước khi ACK.

### 19.2. Async return và manual ack là version-sensitive

Một số Spring AMQP versions có hỗ trợ async listener method trả `CompletableFuture`/Reactor types và tự điều chỉnh ack mode; semantics phụ thuộc version và container config. Không copy ví dụ `@RabbitListener public Mono<Void> ...` rồi giả định như MVC controller: cần kiểm thử ACK timing, exception propagation, requeue và shutdown.

## 20. Request/reply với @RabbitListener

`@RabbitListener` có thể trả một giá trị và dùng `@SendTo` hoặc `replyTo` để gửi response qua AMQP. Tuy nhiên request/reply trên broker vẫn có timeouts, correlation IDs và duplicate risks, không tự thay HTTP synchronous API.

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.SendTo;

@RabbitListener(queues = "pricing.calculate")
@SendTo("pricing.responses")
public PriceResult calculate(PriceRequest request) {
    return pricingService.calculate(request);
}
~~~

`PriceResult`, `PriceRequest` và `pricingService` là application-specific. Trong thực tế reply routing/correlation semantics còn phụ thuộc `replyTo` header và RabbitTemplate RPC; sử dụng `@SendTo` với địa chỉ exchange/routing phải đúng contract. Đừng xem một reply như distributed transaction ACK hoặc exactly-once proof.

### 20.1. RPC trên broker có nhược điểm

- Consumer có thể chậm hoặc chưa sẵn sàng.
- Caller có thể timeout sau khi handler đã commit.
- Reply message có thể mất hoặc không route nếu topology sai.
- Bị ghép chặt vào latency của downstream.
- Retries có thể duplicate side effects.

Nếu không thật sự cần synchronous semantics, event-driven communication + completion event/status API thường dễ phục hồi hơn.

## 21. Kiểm thử ở nhiều lớp

### 21.1. Unit test business service

Unit test `InventoryReservationService` kiểm tra:

- Event mới tạo reservation.
- EventId trùng không tạo reservation lần hai.
- Version thấp không ghi đè version cao.
- Invalid domain state bị reject.
- DB exception làm rollback inbox cùng business update.

Unit test có thể mock dependencies, nhưng **không chứng minh RabbitMQ ACK/timing**, converter hay SQL unique constraint thực.

### 21.2. Mock listener method không đủ

Gọi trực tiếp:

~~~java
listener.onOrderConfirmed(
        new OrderConfirmedEvent(
                "E-1", "ORD-1", 1, Instant.now()));
~~~

chỉ chạy Java method. Nó bỏ qua exchange/routing, container, message conversion, prefetch, ACK/NACK, retry and DLX. Dùng để test orchestration đơn giản, không thay integration test RabbitMQ.

### 21.3. RabbitMQ Testcontainers

Ví dụ Boot 3.1+ Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

@SpringBootTest
@Testcontainers
class OrderRabbitIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:3-management");

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Test
    void publishesToOrdersExchange() {
        rabbitTemplate.convertAndSend(
                "orders.events",
                "order.confirmed",
                new OrderConfirmedEvent(
                        "TEST-E-1", "TEST-O-1", 1,
                        java.time.Instant.now()));

        // Assert business side effect qua polling DB/inbox
        // (không dùng Thread.sleep cố định làm chứng minh).
    }
}
~~~

Đây là **integration-test skeleton**: phải có converter, topology, SQL test database và assertions thực để test PASS. Không coi một test chỉ publish mà không assert consumer business state là test hoàn chỉnh.

### 21.4. Test matrix

| Test case | Điều phải xác minh |
| --- | --- |
| Queue/binding đúng | Routing key đưa message đến listener mong muốn |
| Queue không tồn tại | Container startup/retry/error có thể quan sát |
| JSON body hợp lệ | Typed DTO được convert đúng |
| JSON sai schema | Bị reject/park theo policy, không requeue vô hạn |
| AUTO ack + DB commit | Message được ACK sau handler thành công |
| DB rollback | Không ACK như thành công; retry/DLQ đúng |
| DB commit + mất ACK | Redelivery và inbox dedupe |
| MANUAL ack | `basicAck` đúng channel/tag sau commit |
| MANUAL nack | DLX routing và không mất message ngoài ý muốn |
| Prefetch/concurrency | Active handlers và unacked nằm trong budget |
| Duplicate eventId | Side effect chỉ được apply một lần |
| Out-of-order aggregateVersion | Projection không bị quay về version cũ |
| Rabbit broker disconnect | Container recovery, redelivery an toàn |
| DLQ replay | EventId giữ ổn định, audit/reconciliation đúng |
| Graceful shutdown | In-flight messages xử lý/được redeliver an toàn |
| TLS/credentials/ACL | Negative tests cho CA, vhost, read permissions |

### 21.5. Đừng chạy toàn bộ lỗi production lên queue thật

Load/chaos tests có thể tạo backlog, tốn tài nguyên hoặc làm dữ liệu nhạy cảm bị chuyển DLQ. Dùng môi trường test độc lập, permissions riêng, synthetic events và cleanup policy.

### 21.6. RabbitListenerTestHarness

Spring AMQP có test harness/libraries cho listener annotation trong những version phù hợp. Nó hữu ích để quan sát invocations và spy behavior, nhưng vẫn không thay broker/transport/DB integration test cho transaction, ACK timing hoặc DLX.

## 22. Observability và metrics listener

Trong production, cần quan sát **message đã vào queue, được giao, được xử lý, được ACK hay đang mắc kẹt** theo các tầng.

| Tín hiệu | Tầng | Ý nghĩa |
| --- | --- | --- |
| Queue messages ready | RabbitMQ | Deliveries sẵn sàng giao |
| Queue messages unacked | RabbitMQ | Deliveries đã giao nhưng chưa được ACK |
| Consumer count | RabbitMQ | Có bao nhiêu consumers subscribe |
| Channel/connection count | RabbitMQ | Tài nguyên AMQP |
| Listener invocation latency p95/p99 | Spring AMQP/app | Thời gian handler |
| Listener errors by type | Application | Schema, business, SQL, downstream failures |
| Retry attempt count | Container/retry | Mức độ phục hồi |
| DLQ depth/age | RabbitMQ | Events cần điều tra |
| Inbox duplicate count | SQL/application | Redelivery được dedupe |
| End-to-end confirmation lag | Business | Từ publish intent đến business applied |

Một queue có `messages_ready=0` nhưng `messages_unacked=1000` không có nghĩa hệ thống đã xử lý xong; consumers có thể đang giữ quá nhiều messages, bị DB pool exhausted hoặc treo.

### 22.1. Micrometer và observations

Spring AMQP versions mới có khả năng publish listener timers/observations qua Micrometer/Observation. Cấu hình `observationEnabled`/Micrometer và Actuator phụ thuộc Spring AMQP/Boot version và factory implementation; khi tạo factory tùy chỉnh, kiểm tra configurer đã áp các options.

Không assume mọi metric tự xuất hiện chỉ vì có `spring-boot-starter-actuator`. Muốn đo business applied, cần instrument service ngay sau SQL commit hoặc có event audit bền vững.

### 22.2. Cardinality và dữ liệu nhạy cảm

Tags nên có tập giá trị nhỏ: `listener=inventory-order-consumer`, `queue=inventory.order-confirmed`, `outcome=applied/duplicate/retry/dlq`. Không đưa eventId/orderId/email/token/raw XML/JSON vào Prometheus labels. Logs có thể chứa correlation ID an toàn với access control/retention phù hợp, không dump raw body tùy tiện.

### 22.3. Broker ACK khác business success

Một message được consumer ACK có thể là duplicate đã processed, permanent invalid đã được parking thành công hoặc business applied. Vì thế metrics cần tách:

~~~text
consumer.delivered
consumer.business_applied
consumer.duplicate
consumer.rejected
consumer.dlq_parked
consumer.ack_failed
~~~

Chỉ metric `consumer.business_applied` hoặc completion event đáng tin mới đáp ứng dashboard nghiệp vụ “đã đồng bộ tồn kho”.

## 23. Runbook chẩn đoán @RabbitListener không nhận message

| Dấu hiệu | Nguyên nhân thường gặp | Kiểm tra |
| --- | --- | --- |
| Không có listener logs | Annotation infrastructure chưa active, wrong queue/bean | `@RabbitListener`, registry ID, Boot config |
| Listener không start | Broker down, vhost/ACL sai, queue thiếu | Container startup logs/recovery |
| `PRECONDITION_FAILED` | Queue declaration khác existing topology | Durable/queue type/DLX/TTL arguments |
| Queue ready tăng | Consumer absent/slow, listener stopped | Consumer count, container state |
| Queue unacked tăng | Handler chậm, ACK thiếu, prefetch quá cao | DB pool, thread dumps, ACK mode |
| Message không tới queue | Exchange/routing key/binding sai | Publisher returns, exchange bindings |
| Payload conversion failure | Content-Type, TypeId, JSON schema sai | Converter/class mapper, DLQ |
| Requeue loop | default-requeue-rejected hoặc nack requeue=true | Retry/DLX config |
| 1 message xử lý nhiều lần | Crash sau DB COMMIT trước ACK | Inbox eventId dedupe |
| Events sai thứ tự | Multiple competing consumers/requeue | Aggregate version guard |
| Rabbit channel lỗi | ACK wrong tag/channel, shutdown/race | Manual ACK code, channel lifecycle |
| Consumer không scale | Concurrency/prefetch/broker capacity | SMLC vs DMLC settings |
| DLQ trống dù reject | DLX không tồn tại/binding sai | Topology và broker policy |
| Cache/DB không cập nhật | Listener ACK trước async task chạy | Durable handoff, business completion |
| HTTP downstream timeout | Side effect outcome unknown | Idempotency/status lookup |
| TLS handshake fail | CA/SAN/client certificate sai | TLS config, trust, hostname |
| Consumer 403/access refused | Broker vhost permissions/ACL sai | Service credentials, read/configure |

### 23.1. Thứ tự điều tra

1. Xác nhận publisher thực gửi đúng exchange/routing key và có confirm/return policy.
2. Xem RabbitMQ queue ready/unacked, consumer count và bindings.
3. Kiểm tra application config/`@RabbitListener` id/queue/factory bean names.
4. Kiểm tra factory type, concurrency/prefetch/ack mode.
5. Kiểm tra converter/content-type/schema version.
6. Xác minh SQL transaction, inbox, idempotency và business state.
7. Xem retry/DLX/DLQ và poison message handling.
8. Xem network/TLS/ACL/channel errors.
9. Sử dụng eventId/traceId đã redact để đối soát một intent.
10. Replay có kiểm soát sau khi xác định failure window.

**Không xử lý backlog bằng purge/force-ack** khi chưa đối soát business effects; việc đó có thể xóa khả năng khôi phục.

## 24. Các anti-pattern thường gặp

| Anti-pattern | Vì sao sai? | Cách đúng hơn |
| --- | --- | --- |
| Coi `@RabbitListener` là chỉ một method callback | Bỏ qua container/ACK/lifecycle | Quản lý qua factory và registry |
| Tạo custom factory nhưng không dùng Boot configurer | Mất cấu hình converter/retry/metrics | Configure từ Boot rồi override |
| Dùng SMLC `maxConcurrency` cho DMLC | Sai model concurrency | DMLC `consumersPerQueue` |
| AUTO bị hiểu là broker auto-ack | Dễ mất dữ liệu/sai error handling | Hiểu AUTO vs NONE |
| ACK trong method trước SQL COMMIT | Crash gây mất business update | ACK sau commit/durable handoff |
| Return bình thường sau catch exception | AUTO ACK như thành công | Throw/park bền vững |
| Push task vào executor RAM rồi return | ACK trước task execution | Durable queue/outbox |
| Requeue poison message vô hạn | Retry storm, CPU cao | DLQ/backoff/limit |
| NACK requeue=false nhưng không có DLX | Có thể mất message | Kiểm chứng DLX routing |
| Một queue cho hai services cần cả hai nhận event | Competing consumers làm một service không nhận | Queue riêng cho mỗi service |
| Dùng deliveryTag làm idempotency key | Tag đổi qua redelivery | Stable eventId |
| Quên version guard | Event cũ ghi đè state mới | AggregateVersion/conditional update |
| Tăng prefetch/concurrency vô hạn | Bão tải DB/broker | Capacity budget/bulkhead |
| Lưu Channel global giữa threads | Sai channel lifecycle/ACK tag | Container quản lý channels |
| Chỉ test gọi trực tiếp listener method | Không test converter/ACK/DLX | RabbitMQ Testcontainers |
| Coi publisher confirm là consumer processed | Sai delivery semantics | Business completion metrics |
| Dùng credential broker trong logs/metrics | Security leak | Secret manager/redaction |

## 25. Checklist trước khi vận hành

- [ ] `@RabbitListener` có queue/binding đúng và listener ID ổn định.
- [ ] Queue/exchange/binding ownership rõ (IaC hoặc app), không khai báo xung đột.
- [ ] Factory mặc định/named factory đúng bean name và đúng loại Simple/Direct.
- [ ] Custom factories dùng Boot configurer hoặc map đủ settings.
- [ ] ConnectionFactory/TLS/vhost/credentials và permissions phù hợp.
- [ ] Converter có schema/type mapping an toàn, không tin arbitrary TypeId.
- [ ] AUTO/MANUAL/NONE được hiểu đúng theo broker ACK semantics.
- [ ] Listener synchronous hoàn tất business transaction trước ACK.
- [ ] Manual ACK có đường success/error rõ, không quên ACK/nack/consumer shutdown.
- [ ] Prefetch × concurrency × replicas nằm trong DB/broker capacity budget.
- [ ] Có inbox/unique eventId và version guard chống replay/out-of-order.
- [ ] Permanent errors không requeue vô hạn, transient errors có retry budget.
- [ ] DLX/DLQ/retry topology tồn tại và được kiểm thử bằng broker thật.
- [ ] DLQ parked không được tính là business success.
- [ ] Không ACK trước durable async handoff.
- [ ] Không gửi HTTP side effect khó rollback trong DB transaction nếu có thể tránh.
- [ ] Có Testcontainers tests cho routing, converter, ACK/NACK, recovery, redelivery, DLQ.
- [ ] Có graceful shutdown và kiểm tra unacked sau rolling deployment.
- [ ] Có metrics queue ready/unacked, consumers, business applied, retry, DLQ, duplicates.
- [ ] Logs và metrics không chứa credentials, PII hoặc raw sensitive payload.

**Ghi nhớ:** `@RabbitListener` định nghĩa **đầu nhận message**; `RabbitListenerContainerFactory` xác định **cách tạo và cấu hình runtime**; `MessageListenerContainer` quản lý **consumers, channels, lifecycle và ACK/NACK**. `SimpleRabbitListenerContainerFactory` phù hợp các cấu hình min/max concurrency phổ biến, còn `DirectRabbitListenerContainerFactory` có cơ chế consumers-per-queue và thread model riêng. Dù chọn loại nào, độ tin cậy của luồng tích hợp Spring Boot vẫn dựa trên **transaction đúng ranh giới, inbox/idempotency, retry/DLQ có giới hạn, kiểm thử failure windows và observability từ broker tới business state**.

## Tài liệu tham khảo

- [Spring AMQP — @RabbitListener Annotation](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html): method signatures, endpoint registration, @RabbitHandler.
- [Spring AMQP — Listener Containers](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): Simple/Direct containers, concurrency, ack modes.
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): SMLC concurrency và DMLC consumers per queue.
- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): JSON conversion, type inference và trusted types.
- [Spring AMQP — Resilience and Recoverer](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): retry, errors, recoverer, container recovery.
- [Spring AMQP — Acknowledgement and Transactions](https://docs.spring.io/spring-amqp/reference/amqp/transactions.html): channel transaction và Spring transaction integration.
- [Spring AMQP — Connections](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): CachingConnectionFactory và RabbitAdmin.
- [Spring Boot — RabbitMQ](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): starter, listener factory auto-configuration và properties.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): publisher vs consumer ACK/NACK.
- [RabbitMQ — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): QoS, unacked windows và throughput.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): reject, TTL, DLX routing và broker policy.
- [RabbitMQ — Queues](https://www.rabbitmq.com/docs/queues): durable/queue type/topology declarations.
- [Testcontainers — RabbitMQ](https://java.testcontainers.org/modules/rabbitmq/): integration tests với RabbitMQ.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): local transactions, rollback semantics.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): event deduplication và at-least-once processing.
