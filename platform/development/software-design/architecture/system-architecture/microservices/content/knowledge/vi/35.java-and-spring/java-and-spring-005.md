# Tích hợp broker cho thông điệp nghiệp vụ

Trong hệ thống microservices, các service thường cần thông báo cho nhau khi một sự kiện nghiệp vụ xảy ra: đơn hàng được tạo, thanh toán được xác nhận, tồn kho được giữ chỗ, hồ sơ được cập nhật hoặc hóa đơn được phát hành. Nếu mọi service gọi HTTP đồng bộ qua lại, một request có thể phụ thuộc vào nhiều hệ thống cùng lúc; khi một dependency chậm hoặc tạm ngừng, lỗi dễ lan theo chuỗi và các nhóm phải phối hợp release chặt chẽ.

**Message broker** cung cấp cơ chế trung gian để producer gửi message và consumer nhận/xử lý theo mô hình bất đồng bộ. Broker giúp tách thời điểm gửi khỏi thời điểm xử lý, hấp thụ burst, phân phối message cho nhiều consumer và hỗ trợ retry theo chính sách. Tuy vậy, đưa broker vào hệ thống không tự làm giao dịch nhất quán, không tự bảo đảm consumer chỉ chạy một lần và không thay thế việc thiết kế domain contract.

Trong Java và Spring, tích hợp broker cho thông điệp nghiệp vụ cần phối hợp **domain event/command, message contract, producer, consumer, transaction/outbox, idempotency, ordering, retry/DLQ, schema evolution, security, observability và vận hành**. Bài học dùng Spring Boot cùng Kafka và RabbitMQ làm ví dụ; lựa chọn cụ thể phụ thuộc semantics cần có, nền tảng tổ chức đang vận hành và phiên bản thư viện.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt domain event, command, notification, integration event và message nội bộ.
2. Chọn giữa HTTP/RPC, queue, pub/sub, event log và streaming dựa trên nhu cầu nghiệp vụ.
3. Thiết kế message contract có event ID, type, version, occurred time, producer, aggregate reference và correlation/causation.
4. Tạo producer và consumer bằng Spring Kafka hoặc Spring AMQP.
5. Hiểu delivery semantics: at-most-once, at-least-once và giới hạn của exactly-once.
6. Dùng transactional outbox để tránh dual-write giữa database và broker.
7. Thiết kế consumer idempotent, xử lý duplicate và bảo toàn thứ tự khi cần.
8. Phân biệt retry tạm thời, lỗi dữ liệu vĩnh viễn, dead-letter và replay.
9. Version schema an toàn khi producer/consumer triển khai độc lập.
10. Bảo vệ message bằng authentication, authorization, TLS, validation và kiểm soát dữ liệu nhạy cảm.
11. Theo dõi publish/consume latency, consumer lag, retry, DLQ và business outcome.
12. Kiểm thử integration/failure paths và vận hành broker trong production.

## 2. Broker giải quyết bài toán gì?

Xét luồng đặt hàng:

~~~text
Client
  |
  v
Order Service -------> Order Database
  |
  | OrderPlaced
  v
Message Broker
  |
  +------> Billing Service
  |
  +------> Inventory Service
  |
  +------> Notification Worker
  |
  +------> Analytics Consumer
~~~

Order Service không cần đợi email được gửi hoặc báo cáo được cập nhật mới trả kết quả tạo đơn. Nó ghi nhận đơn hàng và phát thông điệp mô tả sự kiện đã xảy ra. Các consumer xử lý theo tốc độ riêng.

Lợi ích thường gặp:

- **Giảm coupling thời gian:** producer không cần consumer online tại đúng thời điểm gửi nếu broker giữ message theo durability/retention policy.
- **Hấp thụ burst:** broker buffer message khi consumer xử lý chậm, trong giới hạn dung lượng và retention.
- **Fan-out:** nhiều consumer độc lập nhận cùng một event theo semantics của broker.
- **Scale consumer:** tăng consumer instances để xử lý backlog nếu partition/queue topology cho phép.
- **Tách vòng đời triển khai:** producer và consumer có thể phát hành độc lập nếu contract tương thích.
- **Replay/audit:** một số broker giữ log message đủ lâu để đọc lại; cần policy và quyền phù hợp.
- **Resilience:** lỗi một consumer không nhất thiết làm producer thất bại ngay, nhưng backlog và side effects vẫn cần quản lý.

Broker cũng thêm những vấn đề mới:

- Message có thể được giao lại, trễ hoặc sai thứ tự theo topology.
- Consumer có thể crash sau khi thực hiện side effect nhưng trước khi ACK/commit offset.
- Broker có thể đầy, mất kết nối, failover hoặc hết retention.
- Poison message có thể làm một partition/queue bị kẹt.
- Contract không tương thích có thể làm nhiều consumer cùng lỗi.
- Message chứa PII/secret có thể tồn tại trong log, DLQ, backup và replay lâu hơn dự kiến.
- Debug bất đồng bộ khó hơn một call stack HTTP.

Vì vậy, broker phù hợp khi lợi ích bất đồng bộ và phân phối sự kiện lớn hơn chi phí quản lý delivery, state và vận hành.

## 3. Phân biệt event, command và notification

Tên message phải diễn tả đúng ý nghĩa:

- **Domain event:** sự kiện đã xảy ra trong domain, thường đặt ở dạng quá khứ: OrderPlaced, PaymentAuthorized, InventoryReserved.
- **Command:** yêu cầu một consumer thực hiện việc gì đó: ReserveInventory, SendInvoice. Command có người nhận/owner rõ và có thể bị từ chối.
- **Notification:** thông báo cho một nhóm quan tâm rằng trạng thái đã thay đổi, thường không yêu cầu một consumer cụ thể phải thực hiện một hành động.
- **Integration event:** event được công bố qua ranh giới service, có contract ổn định cho consumers bên ngoài domain.
- **Internal event:** event phục vụ logic trong cùng bounded context/process, không nhất thiết là public contract.

Ví dụ:

~~~text
Order Service:
  OrderPlaced            = event
  ReserveInventory       = command gửi Inventory
  OrderConfirmationReady = event

Inventory Service:
  InventoryReserved      = event
  InventoryReservationRejected = event

Billing Service:
  AuthorizePayment       = command
  PaymentAuthorized      = event
  PaymentDeclined        = event
~~~

Không đổi một event thành command chỉ vì tên topic có động từ. OrderPlaced nói điều gì đã xảy ra; PlaceOrder yêu cầu tạo một đơn hàng. Consumer nhận command phải có semantics về ownership, kết quả và lỗi; consumer nhận event thường phản ứng theo cách riêng.

### 3.1. Event không phải một bản sao entity

Không phát toàn bộ Order object cho mọi consumer nếu họ chỉ cần order reference, total, currency và trạng thái. Payload quá lớn làm tăng network, coupling với schema nội bộ và nguy cơ rò dữ liệu.

Một event tốt phản ánh một fact nghiệp vụ ổn định. Nó không nên phụ thuộc vào tên cột database, lazy-loaded ORM graph hoặc internal class của producer.

## 4. Khi nào dùng HTTP, khi nào dùng broker?

| Nhu cầu | Cơ chế thường phù hợp | Lý do |
|---|---|---|
| Cần trả kết quả ngay cho caller | HTTP/gRPC | Request-response trực tiếp |
| Cần validate đồng bộ trước khi nhận lệnh | HTTP/gRPC hoặc command API | Caller nhận lỗi/validation ngay |
| Thông báo một fact cho nhiều nhóm | Pub/sub hoặc event log | Fan-out và độc lập consumer |
| Xử lý công việc nền, có thể đợi | Queue | Buffer và worker pool |
| Cần lưu lịch sử để nhiều consumer đọc độc lập | Kafka/event log hoặc hệ thống tương đương | Retention và offset riêng |
| Stream dữ liệu liên tục với throughput cao | Kafka/stream platform | Partitioned log, consumer groups |
| Task có một nhóm worker cạnh tranh xử lý | RabbitMQ queue hoặc broker queue tương đương | Work distribution/ACK |
| Cần giao dịch nguyên tử xuyên nhiều service | Saga/workflow + local transactions | Broker đơn thuần không tạo distributed transaction nghiệp vụ |

Broker không thay thế mọi API. Nếu người dùng bấm “xác nhận thanh toán” và cần biết ngay có được chấp nhận hay không, command API có thể trả trạng thái tiếp nhận; phần thực thi provider có thể tiếp tục bất đồng bộ và cập nhật trạng thái sau. Contract phải phân biệt accepted, pending, succeeded, declined và unknown.

### 4.1. Một luồng có thể kết hợp sync và async

~~~text
Client
  |
  v
Order API --validate--> Order DB
  |                         |
  |<------ accepted --------|
  |
  +--> OrderPlaced event --> Broker
                               |
                               +--> Inventory
                               +--> Billing
                               +--> Notification
~~~

API có thể trả 202 Accepted hoặc một response domain phù hợp sau khi đơn hàng được commit. Không được trả “đã thanh toán” chỉ vì command đã được đưa vào broker.

## 5. Chọn broker theo semantics và khả năng vận hành

Kafka và RabbitMQ đều có thể truyền message nhưng mô hình lưu trữ, tiêu thụ và vận hành khác nhau.

| Tiêu chí | Kafka | RabbitMQ |
|---|---|---|
| Mô hình chính | Distributed append-only log theo topic/partition | Message broker với exchange, queue và binding |
| Consumer | Consumer group, offset theo partition | Consumer nhận message từ queue và ACK |
| Replay | Đọc lại theo offset trong retention | Thường cần giữ/requeue/DLQ hoặc thiết kế queue riêng |
| Ordering | Thứ tự trong một partition | Thứ tự phụ thuộc queue, consumers, requeue và topology |
| Fan-out | Nhiều consumer groups đọc cùng topic | Exchange định tuyến tới nhiều queues |
| Throughput | Phù hợp stream throughput lớn | Linh hoạt cho routing/queue workloads |
| Work distribution | Partition assignment trong group | Competing consumers trên queue |
| Routing | Topic/partition/key và stream processing | Direct/topic/fanout/headers exchanges |
| Message lifetime | Theo retention, không nhất thiết xóa khi consumer đọc | Queue/ACK và TTL/dead-letter policy |
| Phù hợp | Event streams, replay, analytics, nhiều consumer groups | Task queues, routing linh hoạt, work distribution |

Đây là so sánh khái niệm. Các phiên bản, managed offerings, plugin, durability mode và cấu hình cụ thể có thể thay đổi hành vi. Cần chọn dựa trên message rate, kích thước, retention, ordering, replay, routing, consumer concurrency, availability và năng lực vận hành hiện có.

Không chọn Kafka chỉ vì “microservices hiện đại” hoặc RabbitMQ chỉ vì “dễ dùng”. Broker là dependency quan trọng; team phải biết backup/restore, capacity, security, upgrade, partition/queue recovery và cách xử lý backlog.

## 6. Thiết kế topic, exchange và queue

Tên và topology nên phản ánh domain ownership, không chỉ team hoặc database table.

Ví dụ Kafka topics:

~~~text
orders.order-placed.v1
orders.order-cancelled.v1
payments.payment-authorized.v1
inventory.inventory-reserved.v1
~~~

Ví dụ RabbitMQ:

~~~text
Exchange: commerce.events (topic)
Routing keys:
  orders.placed
  orders.cancelled
  payments.authorized

Queues:
  billing.order-placed
  notification.order-placed
  analytics.order-placed
~~~

Nguyên tắc:

- Một domain event có producer owner rõ.
- Topic/exchange không trở thành nơi mọi service ghi tùy ý.
- Phân biệt event và command bằng naming/ownership.
- Có convention cho environment, version và domain.
- Quy định retention, TTL, max message size và DLQ.
- Quy định ai được publish/consume.
- Có quota và lifecycle khi event không còn consumer.
- Không dùng một queue duy nhất cho nhiều loại công việc có SLA/retry khác nhau nếu semantics không phù hợp.

### 6.1. Kafka partition key

Kafka chỉ đảm bảo ordering trong một partition. Nếu cần thứ tự theo đơn hàng, chọn key ổn định như orderId:

~~~text
key = orderId
value = OrderStatusChanged
~~~

Các event cùng key thường được đưa vào cùng partition theo partitioner và cấu hình topic. Điều này giúp giữ thứ tự theo aggregate trong partition, nhưng không tạo thứ tự toàn cục giữa các order. Thay đổi partition count có thể ảnh hưởng mapping key→partition; cần hiểu tác động với event ordering và stateful consumers.

### 6.2. RabbitMQ routing

RabbitMQ exchange quyết định route message đến queues theo loại exchange và binding:

- **Direct:** routing key khớp chính xác.
- **Topic:** pattern như orders.* hoặc orders.#.
- **Fanout:** broadcast đến mọi queue bind.
- **Headers:** route dựa trên header arguments.

Một consumer group nghiệp vụ nên có queue riêng khi cần retry, backlog và lifecycle độc lập. Nhiều consumer cùng đọc một queue thường chia nhau message; chúng không phải nhiều bản sao fan-out của cùng message.

## 7. Thiết kế message contract

Một integration event nên có envelope ổn định và payload domain có schema version.

Ví dụ:

~~~json
{
  "eventId": "2df5101d-fd53-4bba-b090-4da9788b8c68",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-12T03:15:24.112Z",
  "producer": "order-service",
  "aggregate": {
    "type": "Order",
    "id": "order-7812",
    "version": 18
  },
  "correlationId": "checkout-req-882",
  "causationId": "command-991",
  "payload": {
    "orderId": "order-7812",
    "customerRef": "customer-42",
    "totalMinorUnits": 129900,
    "currency": "VND"
  }
}
~~~

Các trường có ý nghĩa:

- eventId: định danh duy nhất của event logic; consumer dùng để deduplicate.
- eventType: tên fact nghiệp vụ đã xảy ra.
- schemaVersion: phiên bản contract, không nhất thiết là version của ứng dụng.
- occurredAt: thời điểm nghiệp vụ xảy ra; phân biệt với publish/consume time.
- producer: service sở hữu event; ở transport nên có identity được xác thực độc lập.
- aggregate.id và aggregate.version: liên hệ event với entity và thứ tự thay đổi của entity.
- correlationId: liên kết một workflow/request dài hơn.
- causationId: chỉ ra command/event trực tiếp dẫn đến event này.
- payload: dữ liệu tối thiểu consumer cần để thực hiện contract.

Không để consumer phụ thuộc vào internal Java class của producer. Một event JSON có thể được lưu trong schema registry hoặc tài liệu contract, có ví dụ và compatibility rules.

### 7.1. Event time và processing time

Một event có thể xảy ra lúc 10:00 nhưng đến consumer lúc 10:03. Hãy phân biệt:

- occurredAt: thời điểm fact xảy ra trong domain.
- publishedAt: thời điểm producer/broker ghi nhận publish, nếu có.
- consumedAt: thời điểm consumer nhận.
- processedAt: thời điểm xử lý hoàn tất.

Không dùng thời gian nhận message để quyết định thứ tự business nếu event time và aggregate version mới là nguồn đúng. Clock của các service có thể lệch; version/sequence do owner cấp đáng tin hơn cho một aggregate.

## 8. Schema evolution và backward compatibility

Producer và consumer triển khai độc lập nên contract phải sống lâu hơn một release.

### Thay đổi thường an toàn hơn

- Thêm field optional có default hợp lý.
- Thêm enum value nếu consumer được thiết kế chịu giá trị chưa biết.
- Thêm event type mới mà không thay semantics event cũ.
- Mở rộng metadata envelope không làm consumer cũ fail.

### Thay đổi dễ phá vỡ

- Xóa field đang được consumer dùng.
- Đổi tên hoặc kiểu field.
- Đổi unit (milliseconds thành seconds).
- Đổi nghĩa enum/status nhưng giữ tên cũ.
- Đổi semantics null/missing/default.
- Đổi timezone/rounding hoặc cách tính amount.
- Chuyển từ event “đã thanh toán” sang event “đã yêu cầu thanh toán”.

Khi cần breaking change:

1. Tạo schema/event version mới hoặc một contract migration rõ.
2. Triển khai consumer đọc được cả version cũ và mới.
3. Sau đó mới phát version mới.
4. Quan sát consumer lag/error/DLQ và xác minh tất cả đã nâng cấp.
5. Ngừng version cũ theo deprecation window và evidence.
6. Giữ khả năng replay/reader cũ nếu retention yêu cầu.

### 8.1. Không dùng version ứng dụng làm schema version

order-service 3.7.2 có thể phát OrderPlaced schema v1; release sau 3.8.0 vẫn có thể phát cùng schema v1. Schema version mô tả contract; application version mô tả artifact. Hai khái niệm này có lifecycle khác nhau.

### 8.2. Schema Registry và serialization

Tổ chức có thể dùng JSON Schema, Avro hoặc Protobuf cùng schema registry. Registry giúp kiểm tra compatibility và quản lý schema IDs, nhưng không thay thế review semantics. Một thay đổi schema “backward compatible” về cú pháp vẫn có thể sai nghiệp vụ nếu field amount đổi từ gross sang net.

## 9. Java và Spring: lựa chọn integration

Trong Spring Boot thường có hai abstraction phổ biến:

- **Spring for Apache Kafka:** KafkaTemplate, @KafkaListener, listener container, consumer factory và transaction configuration.
- **Spring AMQP:** RabbitTemplate, @RabbitListener, connection factory, exchange/queue/binding và acknowledgment.

Spring Cloud Stream cung cấp abstraction binder cho nhiều broker. Nó tiện khi muốn tách logic function khỏi broker-specific API, nhưng cần hiểu binder semantics, partitioning, retries, DLQ và transaction behavior của implementation đang dùng.

Ví dụ trong bài dùng code minh họa, cần đối chiếu Spring Boot/Spring Kafka/Spring AMQP version trong dự án. Không trộn dependency/config của các major versions khác nhau mà chưa kiểm tra compatibility.

### 9.1. Chọn abstraction theo nhu cầu

- Dùng Kafka API trực tiếp khi cần kiểm soát partition, offset, transactions hoặc Kafka-specific behavior.
- Dùng Spring AMQP khi cần Rabbit exchanges, bindings, routing và queue semantics.
- Dùng Spring Cloud Stream khi function-based processing và portability là lợi ích thực, đồng thời chấp nhận contract của binder.
- Đừng tạo một generic MessageBrokerClient quá trừu tượng nếu nó che mất ACK, offset, ordering hoặc DLQ semantics cần thiết.

## 10. Cấu hình Spring Kafka cơ bản

Dependencies khái niệm cho Maven:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
~~~

Trong Spring Boot, dependency management của BOM thường quản lý version tương thích; không tùy tiện pin một phiên bản khác với Spring Boot đang dùng.

Ví dụ application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: \${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: "com.example.contracts"
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        enable.idempotence: true
~~~

Đây là cấu hình minh họa cho môi trường local/test. Production phải cấu hình authentication, TLS/SASL theo broker, ACL, timeouts, retries, producer batching, consumer poll limits, partition strategy, schema handling và secret references. Không để credential trong YAML được commit.

auto-offset-reset chỉ có tác dụng khi group chưa có committed offset hoặc offset không còn hợp lệ; nó không phải chính sách replay mỗi lần restart. enable-auto-commit=false giúp listener container kiểm soát commit theo acknowledgment/error handling, nhưng phải hiểu chính xác AckMode và transaction configuration.

### 10.1. Producer với KafkaTemplate

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {
    private static final String TOPIC = "orders.order-placed.v1";

    private final KafkaTemplate<String, OrderPlacedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderPlacedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderPlacedEvent event) {
        kafkaTemplate.send(TOPIC, event.orderId(), event);
    }
}
~~~

Ví dụ trên minh họa cách gửi key/value. Trong production cần xử lý kết quả bất đồng bộ của send, log eventId và kết quả publish an toàn, đặt timeout/exception policy và tránh xem lời gọi method không ném exception ngay là broker đã lưu bền vững. Với Spring Kafka version hiện đại, send trả về CompletableFuture; API cũ có thể khác.

### 10.2. Consumer với @KafkaListener

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class BillingOrderConsumer {

    private final BillingApplicationService billing;

    public BillingOrderConsumer(BillingApplicationService billing) {
        this.billing = billing;
    }

    @KafkaListener(
        topics = "orders.order-placed.v1",
        groupId = "billing-service"
    )
    public void onOrderPlaced(OrderPlacedEvent event) {
        billing.startBilling(event);
    }
}
~~~

Consumer này chỉ là skeleton. Trong ứng dụng thật, cần xác định:

- Listener container commit offset khi nào.
- Exception nào retry, exception nào đi DLQ.
- Side effect database có idempotent không.
- Consumer có thể xử lý nhiều partitions đồng thời không.
- Message schema không hợp lệ sẽ được xử lý thế nào.
- Consumer shutdown/rebalance khi đang xử lý có thể gây redelivery ra sao.

## 11. Cấu hình Spring AMQP với RabbitMQ

Dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Ví dụ config:

~~~yaml
spring:
  rabbitmq:
    host: \${RABBITMQ_HOST:localhost}
    port: \${RABBITMQ_PORT:5672}
    username: \${RABBITMQ_USERNAME:app}
    password: \${RABBITMQ_PASSWORD:local-only}
    listener:
      simple:
        acknowledge-mode: manual
        prefetch: 20
        concurrency: 2
        max-concurrency: 8
~~~

Credential default chỉ phục vụ ví dụ local; production dùng secret manager, TLS, network restriction và user/vhost riêng. prefetch ảnh hưởng số message được broker giao trước cho consumer; giá trị cao có thể tăng throughput nhưng làm tăng in-flight messages và độ lệch tải khi consumer xử lý không đều.

### 11.1. Khai báo exchange, queue và binding

~~~java
import org.springframework.amqp.core.*;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CommerceRabbitConfig {

    @Bean
    TopicExchange commerceEventsExchange() {
        return ExchangeBuilder
                .topicExchange("commerce.events")
                .durable(true)
                .build();
    }

    @Bean
    Queue billingOrderPlacedQueue() {
        return QueueBuilder
                .durable("billing.order-placed")
                .build();
    }

    @Bean
    Binding billingOrderPlacedBinding(
            Queue billingOrderPlacedQueue,
            TopicExchange commerceEventsExchange) {
        return BindingBuilder
                .bind(billingOrderPlacedQueue)
                .to(commerceEventsExchange)
                .with("orders.placed");
    }
}
~~~

Production cần khai báo dead-letter exchange/queue, TTL, max length hoặc overflow behavior theo policy; có thể quản lý topology bằng IaC/operator thay vì để mọi service tự tạo tài nguyên có quyền rộng. Các queues và exchanges phải có ownership, retention/expiry và cleanup policy.

### 11.2. Publish bằng RabbitTemplate

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderRabbitPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderRabbitPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(OrderPlacedEvent event) {
        rabbitTemplate.convertAndSend(
                "commerce.events",
                "orders.placed",
                event,
                message -> {
                    message.getMessageProperties()
                           .setMessageId(event.eventId());
                    message.getMessageProperties()
                           .setContentType("application/json");
                    return message;
                }
        );
    }
}
~~~

Để biết message đã được broker nhận, cần publisher confirms và xử lý returned messages khi mandatory routing được bật; việc convertAndSend trả về không tự chứng minh message đã được route tới queue mong muốn. Cấu hình confirm/return callback tùy Spring AMQP version và connection factory.

### 11.3. Consumer với @RabbitListener

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BillingRabbitConsumer {

    private final BillingApplicationService billing;

    public BillingRabbitConsumer(BillingApplicationService billing) {
        this.billing = billing;
    }

    @RabbitListener(queues = "billing.order-placed")
    public void onOrderPlaced(OrderPlacedEvent event) {
        billing.startBilling(event);
    }
}
~~~

Với manual ACK, listener cần ACK sau khi business transaction hoàn tất và quyết định reject/requeue/DLQ rõ. Với container-managed acknowledgment, cấu hình transaction/error handler phải khớp semantics. Không ACK trước khi side effect được commit nếu muốn broker có cơ hội giao lại khi xử lý thất bại.

## 12. Delivery semantics: at-most-once, at-least-once, exactly-once

### 12.1. At-most-once

Message có thể mất nhưng không được giao lại sau khi consumer đã commit/ack theo semantics đó. Phù hợp một số telemetry hoặc signal có thể bỏ qua; không phù hợp sự kiện nghiệp vụ quan trọng nếu mất event không được chấp nhận.

### 12.2. At-least-once

Message được giao lại cho đến khi broker ghi nhận ACK/offset commit theo chính sách. Consumer có thể xử lý cùng event nhiều lần nếu crash/rebalance hoặc ACK/commit không hoàn tất.

Đây là lựa chọn phổ biến cho business messaging vì có thể ưu tiên không mất message, nhưng yêu cầu consumer **idempotent**.

### 12.3. Exactly-once

Cần phân biệt phạm vi:

- Broker có thể hỗ trợ exactly-once processing trong một số luồng Kafka transaction giữa Kafka input và Kafka output.
- Điều đó không tự tạo transaction nguyên tử với PostgreSQL, email provider, payment gateway hoặc API ngoài.
- Khi consumer commit DB rồi crash trước khi commit offset, message có thể được giao lại.
- Một external provider có thể đã xử lý request dù client timeout.

Vì vậy, mục tiêu thực tế thường là **at-least-once delivery + idempotent business effects + transaction boundaries rõ**. Nếu cần exactly-once business outcome, phải dùng idempotency key, unique constraints, transactional state và reconciliation theo domain.

## 13. Vấn đề dual write giữa database và broker

Một producer thường phải làm hai việc:

1. Ghi dữ liệu nghiệp vụ vào database.
2. Publish event lên broker.

Hai thao tác ở hai hệ thống khác nhau không tự nguyên tử:

~~~text
BEGIN DB
  UPDATE orders
COMMIT

PUBLISH OrderPlaced
~~~

Nếu process chết sau DB commit nhưng trước publish, đơn hàng tồn tại mà consumer không biết. Nếu publish trước rồi DB rollback, consumer xử lý một event không có business state tương ứng.

Đây là **dual-write problem**.

### 13.1. Transactional outbox

Ghi business row và outbox row trong cùng transaction database:

~~~text
Order Service
   |
   v
BEGIN TRANSACTION
   |
   +--> INSERT/UPDATE orders
   |
   +--> INSERT outbox(event_id, type, payload, created_at)
   |
COMMIT
   |
   v
Outbox Relay / CDC
   |
   v
Broker
   |
   v
Consumers
~~~

Nếu transaction rollback, cả business change và outbox event đều không tồn tại. Nếu commit, relay có thể publish lại sau outage.

Ví dụ PostgreSQL schema:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(200) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(200) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_unpublished
    ON outbox_event (occurred_at)
    WHERE published_at IS NULL;
~~~

Ghi cùng transaction:

~~~sql
BEGIN;

UPDATE orders
   SET status = 'PLACED',
       version = version + 1
 WHERE order_id = :order_id
   AND status = 'DRAFT';

-- Chỉ ghi event khi UPDATE thành công đúng một bản ghi.
INSERT INTO outbox_event (
    event_id, aggregate_type, aggregate_id,
    aggregate_version, event_type, schema_version,
    payload, occurred_at
) VALUES (
    :event_id, 'Order', :order_id,
    :new_version, 'OrderPlaced', 1,
    :payload, now()
);

COMMIT;
~~~

Đây là SQL khái niệm; placeholder do application/driver bind. Phải kiểm tra số row update và version thực tế trước khi insert event. Không tạo event OrderPlaced nếu transition không hợp lệ hoặc update không thành công.

### 13.2. Relay và CDC

Outbox relay có thể polling theo batch hoặc đọc CDC từ WAL/binlog:

- Polling dễ hiểu, nhưng cần locking/claiming rows, batch size và cleanup.
- CDC có độ trễ thấp và giảm polling, nhưng đòi hỏi connector, offsets, schema handling và vận hành CDC.
- Cả hai đều có thể publish lại event sau crash; consumer vẫn cần deduplication.
- Không xóa outbox row trước khi có bằng chứng publish thành công theo protocol.
- Theo dõi tuổi row cũ nhất chưa publish và backlog theo producer.

Transactional outbox giảm rủi ro dual write, nhưng không bảo đảm event đã tới mọi consumer hay đã được xử lý thành công.

## 14. Consumer idempotency

Giả sử Billing Service nhận OrderPlaced, tạo invoice trong DB, rồi crash trước khi commit Kafka offset. Khi restart, event được giao lại. Nếu consumer tạo invoice mới mỗi lần, có thể sinh hóa đơn trùng.

Dùng eventId và unique constraint:

~~~sql
CREATE TABLE processed_messages (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong một transaction:

~~~text
BEGIN

INSERT processed_messages(consumer_name, event_id)
  ON CONFLICT DO NOTHING

if insert did not occur:
    COMMIT and acknowledge duplicate
else:
    create invoice / update billing state
    COMMIT
    acknowledge message
~~~

Điểm quan trọng: insert dedup marker và business side effect phải nằm trong **cùng transaction** nếu cùng database. Nếu marker commit trước rồi business update fail, lần giao lại có thể bị coi là duplicate dù side effect chưa xảy ra.

### 14.1. Idempotency key theo nghiệp vụ

Ngoài eventId, một command có thể cần idempotency key như paymentAuthorizationId hoặc reservationRequestId. Hai event khác nhau đôi khi đại diện cho cùng một ý định nghiệp vụ; dedup chỉ theo eventId chưa đủ.

Ví dụ:

- AuthorizePayment phải dùng idempotency key ổn định cho lần thử logic đó.
- ReserveInventory phải kiểm soát reservation theo order/line item.
- SendEmail có thể cần delivery key theo notification purpose và recipient.
- CreateInvoice cần unique constraint theo order/payment reference.

Không dùng orderId làm key cho mọi hành động nếu một đơn hàng có thể có nhiều lần payment/refund hợp lệ.

## 15. Commit offset và ACK đúng thời điểm

### Kafka

Với listener container, cần hiểu AckMode và transaction behavior:

- Commit trước business side effect có thể làm mất message nếu xử lý thất bại sau commit.
- Commit sau side effect tạo khả năng duplicate nếu process chết giữa hai bước.
- Idempotent consumer xử lý trường hợp duplicate.
- Batch listener phải xác định lỗi một record ảnh hưởng commit các record khác thế nào.
- Rebalance có thể xảy ra trong lúc consumer đang xử lý; handler cần đủ nhanh và xử lý cancellation/shutdown đúng.

Không bật auto commit theo mặc định rồi giả định message được xử lý đúng. Cấu hình container phải phù hợp với transaction của application.

### RabbitMQ

- Manual ACK giúp consumer xác nhận sau khi xử lý xong.
- basic.reject/basic.nack với requeue có thể gây vòng lặp nếu message luôn lỗi.
- Requeue ngay liên tục tạo hot loop và làm queue không tiến triển.
- Prefetch giới hạn số message in-flight.
- Dead-letter routing cần queue/exchange và policy được cấu hình.
- Consumer channel/connection chết trước ACK có thể khiến message được giao lại.

Dù dùng broker nào, quy tắc vẫn là: **business side effect phải bền vững trước khi xác nhận xử lý**, và duplicate phải an toàn.

## 16. Retry: lỗi tạm thời và lỗi vĩnh viễn

Không phải mọi exception đều cần retry.

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Transient | Database connection reset, timeout ngắn, broker dependency tạm lỗi | Retry có giới hạn và backoff |
| Throttling | HTTP 429, provider rate limit | Tôn trọng Retry-After, giảm concurrency |
| Permanent/business | Order đã hủy, transition không hợp lệ | Không retry vô hạn; ghi outcome nghiệp vụ |
| Invalid message | JSON/schema sai, field bắt buộc thiếu | Quarantine/DLQ và điều tra producer |
| Authorization | Consumer không còn quyền truy cập | Dừng retry dày, alert và xử lý IAM |
| Dependency outage kéo dài | Database/third party unavailable | Backoff, circuit breaker, pause/hold khi phù hợp |

### 16.1. Exponential backoff và jitter

Ví dụ thời gian chờ tăng dần:

~~~text
attempt 1: 1 s
attempt 2: 2 s
attempt 3: 4 s
attempt 4: 8 s
attempt 5: 16 s
...
~~~

Có thể giới hạn max delay và thêm jitter để nhiều consumers không retry cùng lúc. Con số phải dựa trên SLA/deadline, không dùng một lịch cố định cho mọi loại message.

Retry cần có:

- Maximum attempts hoặc maximum elapsed time.
- Backoff có jitter.
- Timeout cho mỗi lần gọi dependency.
- Retry budget và concurrency limit.
- Phân loại exception.
- Idempotency cho side effect.
- Metric cho attempt count và retry age.
- Đường chuyển DLQ/quarantine.
- Quy trình replay có kiểm soát.

Không retry mọi lỗi 5xx vô hạn; có thể làm downstream càng quá tải.

## 17. Dead-letter queue và poison message

Một message không thể xử lý sau số lần retry cho phép có thể chuyển sang **dead-letter queue (DLQ)** hoặc quarantine store. DLQ là nơi điều tra, không phải thùng rác để bỏ quên.

Cần lưu:

- Original event/message ID.
- Original topic/queue/routing key.
- Consumer name và version.
- Failure category và exception class đã được redaction.
- First/last failure time, attempt count.
- Correlation/causation reference.
- Schema version và producer revision nếu có.
- Replay status và người/operation thực hiện replay.

Không lưu stack trace chứa secret hoặc payload nhạy cảm không cần thiết. Nếu payload chứa PII, DLQ cũng phải có access/retention tương ứng.

### 17.1. DLQ replay

Trước khi replay:

1. Xác định nguyên nhân đã được khắc phục.
2. Xác minh schema và consumer version tương thích.
3. Kiểm tra side effect có thể đã xảy ra trước khi message bị đưa DLQ không.
4. Xác minh idempotency/dedup store còn giữ marker cần thiết.
5. Chọn một message hoặc batch có giới hạn.
6. Ghi audit replay operation và actor.
7. Theo dõi outcome, duplicates và business invariants.
8. Có thể dừng batch nếu phát hiện lỗi mới.

Không replay toàn bộ DLQ vào giờ cao điểm chỉ bằng một lệnh thiếu giới hạn; backlog có thể làm quá tải database hoặc provider.

## 18. Ordering và partitioning

Một số nghiệp vụ cần thứ tự theo aggregate:

~~~text
Order 7812:
  v18 OrderPlaced
  v19 PaymentAuthorized
  v20 OrderConfirmed
  v21 ShipmentCreated
~~~

Nếu OrderConfirmed đến trước PaymentAuthorized, consumer có thể áp dụng sai state transition.

### Kafka

- Chọn message key theo aggregate ID để các event cùng aggregate đi cùng partition.
- Một partition chỉ được một consumer trong cùng consumer group xử lý tại một thời điểm.
- Nhiều partitions tăng parallelism nhưng ordering chỉ trong từng partition.
- Thay partition count có thể làm key chuyển partition; cần đánh giá thứ tự trong giai đoạn chuyển tiếp.
- Không đảm bảo thứ tự giữa các partitions.

### RabbitMQ

- Một queue giữ thứ tự enqueue ở mức broker, nhưng nhiều consumers, prefetch, requeue và redelivery có thể khiến thứ tự xử lý hoàn tất khác nhau.
- Nếu cần thứ tự nghiêm ngặt, có thể giới hạn concurrency theo queue/key hoặc dùng sharding queues theo aggregate.
- Một consumer chậm có thể làm giảm throughput nếu buộc xử lý tuần tự.

### 18.1. Version check tại consumer

Consumer có thể lưu lastProcessedVersion cho aggregate. Khi nhận event:

- version == last + 1: xử lý tiếp.
- version <= last: duplicate/old event; xử lý theo policy.
- version > last + 1: có gap; tạm giữ/retry hoặc yêu cầu reconcile/snapshot.

Đây là logic khái niệm. Nếu có event types không tăng version hoặc có nhiều aggregate, phải xác định sequence semantics phù hợp. Không tự bỏ event có version gap vì có thể làm mất một transition nghiệp vụ.

## 19. Saga và quy trình nhiều service

Một nghiệp vụ như đặt hàng có thể trải qua nhiều local transactions:

~~~text
Order Service
  |
  | OrderPlaced
  v
Inventory Service
  | reserve stock
  | InventoryReserved / InventoryRejected
  v
Payment Service
  | authorize payment
  | PaymentAuthorized / PaymentDeclined
  v
Order Service
  | confirm or cancel order
  v
Notification
~~~

Đây là dạng **Saga**: mỗi service commit transaction cục bộ rồi phát event/command tiếp theo. Nếu một bước thất bại, workflow có thể cần compensating action như release reservation hoặc void authorization.

Broker giúp truyền các thông điệp giữa bước, nhưng Saga cần:

- State machine/workflow owner.
- Correlation ID và command IDs.
- Timeout cho mỗi bước.
- Idempotency và deduplication.
- Compensation semantics.
- Xử lý trạng thái UNKNOWN khi external provider timeout.
- Reconciliation khi callback/event bị mất hoặc trễ.
- Audit và observability end-to-end.

Không coi compensation luôn là rollback thật. Ví dụ payment đã capture có thể phải refund; đây là một giao dịch mới với side effects, không xóa lịch sử capture.

## 20. Spring Kafka: retry và error handling

Spring Kafka cung cấp listener container và error handler để xử lý lỗi. Tên API/config có thể khác giữa các phiên bản; dưới đây là ví dụ định hướng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.ExponentialBackOffWithMaxRetries;

@Configuration
public class KafkaErrorConfig {

    @Bean
    DefaultErrorHandler kafkaErrorHandler() {
        var backOff =
            new ExponentialBackOffWithMaxRetries(4);

        backOff.setInitialInterval(1_000L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(10_000L);

        return new DefaultErrorHandler(backOff);
    }
}
~~~

Ví dụ minh họa cách định nghĩa retry backoff; production cần cấu hình recoverer/DLT, exception classification, deserialization failures, non-retryable exceptions, listener container factory và transactional behavior. Không retry lỗi validation vĩnh viễn như lỗi transient.

### 20.1. Dead-letter topic

Với Kafka, một dead-letter topic có thể có tên:

~~~text
orders.order-placed.v1
orders.order-placed.v1.DLT
~~~

Cần định nghĩa ai được publish/consume DLT, retention, alert và replay tool. DLT không tự được tạo hoặc vận hành an toàn chỉ vì error handler biết tên topic; topic ACL, partitions, replication và lifecycle phải được quản lý.

### 20.2. Deserialization errors

Nếu JSON không deserialize được thành Java class, listener method có thể chưa được gọi. Cần xử lý lỗi ở deserializer/error-handler layer và giữ raw message có kiểm soát để điều tra. Không để một message sai schema làm consumer group kẹt mãi mà không alert.

## 21. Spring AMQP: ACK, reject và dead-letter

Một consumer manual acknowledgment có thể được viết như sau:

~~~java
import com.rabbitmq.client.Channel;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderRabbitListener {

    private final BillingApplicationService billing;

    public OrderRabbitListener(BillingApplicationService billing) {
        this.billing = billing;
    }

    @RabbitListener(queues = "billing.order-placed")
    public void consume(
            OrderPlacedEvent event,
            Message message,
            Channel channel) throws Exception {

        long tag = message.getMessageProperties()
                           .getDeliveryTag();

        try {
            billing.startBillingIdempotently(event);
            channel.basicAck(tag, false);
        } catch (PermanentMessageException ex) {
            channel.basicReject(tag, false);
        } catch (Exception ex) {
            channel.basicNack(tag, false, false);
        }
    }
}
~~~

Ví dụ minh họa manual ACK. basicReject(..., false) hoặc basicNack(..., false, false) chỉ route sang DLX nếu queue có dead-letter configuration; nếu không, message có thể bị loại bỏ theo broker semantics. Với transient error, ví dụ này cần một retry strategy riêng thay vì đưa ngay mọi lỗi sang DLQ. Không dùng requeue=true vô hạn nếu không có delay/backoff.

### 21.1. Delayed retry

RabbitMQ có thể triển khai retry qua TTL + dead-letter routing hoặc plugin delayed-message tùy môi trường. Cần kiểm tra:

- Message quay về queue ban đầu bao nhiêu lần?
- Header retry count được quản lý thế nào?
- Queue retry có giới hạn và DLQ cuối không?
- Message ordering bị thay đổi ra sao?
- TTL expiration có tạo burst khi nhiều message cùng hết hạn không?
- Plugin/version có được tổ chức hỗ trợ không?

Không mặc định có thể dùng plugin ở mọi managed broker. Nếu không hỗ trợ, dùng retry queues được cấu hình rõ hoặc retry orchestration riêng.

## 22. Transaction trong consumer

Giả sử consumer ghi database và ACK message. Không có một transaction nguyên tử mặc định bao phủ cả DB và broker ACK.

Một luồng an toàn thường là:

~~~text
Receive message
    |
    v
BEGIN DB TRANSACTION
    |
    +--> insert processed event ID
    |
    +--> apply business state change
    |
COMMIT DB
    |
    v
ACK / commit offset
~~~

Nếu crash sau DB commit nhưng trước ACK, broker có thể giao lại; idempotency marker làm lần xử lý sau không tạo side effect lần nữa. Nếu ACK/offset commit trước DB commit, crash có thể làm message mất khỏi consumer dù business update chưa hoàn tất.

Một số nền tảng hỗ trợ transaction giữa broker input/output hoặc transaction manager tích hợp, nhưng **không mặc định bao trùm external database và mọi side effect**. Cần kiểm tra đúng transaction manager, isolation, offset commit và failure scenarios.

### 22.1. Không giữ transaction DB mở trong lúc gọi external provider lâu

Gọi Payment Provider trong DB transaction có thể giữ connection/lock quá lâu. Thường nên:

1. Ghi state PAYMENT_PENDING và idempotency key.
2. Commit local transaction.
3. Gọi provider qua workflow/worker với timeout.
4. Ghi kết quả vào transaction khác.
5. Xử lý callback/timeout/reconciliation.
6. Phát event outcome qua outbox.

Thiết kế phụ thuộc business semantics; không biến broker consumer thành một transaction phân tán kéo dài.

## 23. Correlation, tracing và logging

Thông điệp nên mang metadata để nối workflow:

- eventId: định danh message logic.
- correlationId: liên hệ quy trình nghiệp vụ.
- causationId: command/event trực tiếp tạo ra event.
- traceparent: W3C trace context khi instrumentation hỗ trợ.
- producer: domain owner/service.
- schemaVersion: contract version.
- aggregateId/aggregateVersion: entity và sequence.

Trong log có thể ghi:

~~~text
eventId=evt-01
eventType=OrderPlaced
consumer=billing-service
correlationId=checkout-882
outcome=SUCCEEDED
processingMs=34
~~~

Không log toàn bộ payload nếu có PII hoặc secret. Không dùng eventId, orderId, userId làm metric label cardinality cao; dùng trace/log có kiểm soát để truy vấn cụ thể. traceparent giúp nối trace nhưng không phải authentication proof.

### 23.1. Metrics cần có

| Metric | Ý nghĩa |
|---|---|
| messages_published_total | Số message producer gửi |
| publish_failures_total | Publish thất bại |
| consumer_messages_total{outcome} | Consume success/duplicate/fail |
| consumer_processing_duration | Thời gian xử lý |
| consumer_lag | Độ trễ offset/stream hoặc backlog |
| queue_depth | Message đang chờ trong queue |
| oldest_message_age | Tuổi message cũ nhất chưa xử lý |
| retry_attempts_total | Retry theo nguyên nhân |
| dead_letter_total | Message vào DLQ |
| outbox_pending_total | Outbox chưa publish |
| outbox_oldest_age | Tuổi event outbox cũ nhất |
| duplicate_events_total | Duplicate bị chặn |
| schema_rejections_total | Message không đạt contract |

Tên metric là ví dụ. Label phải hữu hạn, không chứa raw message key, user ID, email hay payload. Với Kafka, consumer lag thường được đo theo group/topic/partition; với RabbitMQ, queue depth và unacked messages là tín hiệu khác nhau.

## 24. Bảo mật broker và message

Broker có thể chứa dữ liệu nghiệp vụ trong thời gian dài, nên cần bảo vệ như một data platform.

- TLS giữa producer/consumer và broker.
- Authentication bằng workload identity, SASL, client certificates hoặc cơ chế được nền tảng hỗ trợ.
- ACL theo topic/queue/exchange và action publish/consume/configure.
- Tách credentials theo service/environment.
- Không cấp quyền quản trị broker cho runtime consumer.
- Không để secret trong message headers/payload.
- Phân loại PII và mã hóa payload khi policy yêu cầu.
- Giới hạn message size, rate và retention.
- Bảo vệ DLQ/replay tools với access audit.
- Quản lý schema registry permissions.
- Rotate credentials/certificates và kiểm tra consumer refresh.
- Không tin producer name hoặc tenant ID tự khai nếu không kiểm tra với authenticated identity.

### 24.1. Multi-tenant isolation

Nếu topic chứa dữ liệu nhiều tenant, phải xác định:

- Tenant nào được publish event?
- Consumer nào được đọc tenant nào?
- Partitioning/key có làm lộ pattern hoặc tạo hot tenant không?
- DLQ có giữ dữ liệu cross-tenant không?
- Replay API có kiểm tra tenant scope không?
- Schema/retention có đáp ứng data residency không?

Chỉ thêm tenantId vào payload không tạo isolation. Authorization phải được broker ACL hoặc application-level policy thực thi ở nơi thích hợp.

## 25. Thiết kế payload an toàn và gọn

Một message nên chứa dữ liệu đủ để consumer thực hiện contract. Có hai chiến lược:

### Event-carried state transfer

Event chứa một snapshot nhỏ các field consumer cần. Ưu điểm: consumer không phải gọi producer để lấy từng field; nhược điểm: payload lớn hơn và có thể stale.

### Reference-based event

Event chỉ chứa entity ID/version và consumer gọi API hoặc đọc read model. Ưu điểm: payload nhỏ và ít trùng dữ liệu; nhược điểm: consumer phụ thuộc availability/auth của producer, dữ liệu có thể đã thay đổi khi consumer đọc.

Có thể kết hợp: event mang reference/version cùng các giá trị fact quan trọng tại thời điểm event xảy ra. Ví dụ OrderPlaced nên giữ amount/currency đã chốt theo contract nếu consumer cần hiểu giao dịch tại thời điểm đó, thay vì gọi API lấy giá hiện tại.

Không phát token để consumer gọi API thay producer. Dùng workload identity của consumer và authorization riêng.

## 26. Consumer concurrency và backpressure

Tăng số consumer không phải lúc nào cũng tăng throughput:

- Kafka: parallelism tối đa của một consumer group bị giới hạn bởi số partitions; consumer dư có thể idle.
- RabbitMQ: nhiều consumers tăng concurrency nhưng có thể làm quá tải DB/downstream.
- Database connection pool và provider rate limit có thể là bottleneck.
- Message processing lâu có thể vượt max.poll.interval.ms hoặc gây ACK timeout tùy broker.
- Prefetch cao làm tăng in-flight messages và có thể giảm fairness.
- Rebalance/requeue có thể tạo duplicate.
- Một key nóng hoặc partition nóng giới hạn throughput.

Cần giới hạn concurrency theo khả năng downstream, không theo số Pod có thể tạo. Backpressure có thể gồm pause partitions, giảm consumer concurrency, rate limit hoặc để broker backlog tăng trong giới hạn retention/capacity.

### 26.1. Batch consume

Batch listener có thể giảm overhead nhưng làm tăng complexity:

- Nếu một record trong batch lỗi, commit/ACK các record khác thế nào?
- Có thể retry toàn batch gây side effects duplicate không?
- Cần idempotency theo từng event.
- Có giới hạn batch size và thời gian xử lý.
- Batch phải giữ thứ tự khi nghiệp vụ yêu cầu.

Không dùng batch chỉ vì throughput benchmark cao nếu failure recovery chưa được thiết kế.

## 27. Message size, retention và throughput

Message lớn làm tăng network, memory, disk, replication và serialization overhead. Tránh gửi binary/document lớn hoặc toàn bộ entity graph qua broker khi có thể lưu object ở object storage và gửi reference/version/checksum.

Cần thiết kế:

- Maximum payload size.
- Compression và CPU cost.
- Retention theo event type và consumer needs.
- Replication factor/quorum/durability.
- Queue TTL, max length, overflow policy.
- Disk capacity và alert thresholds.
- Partition/queue count.
- Network bandwidth và cross-zone cost.
- Backup/recovery và replay window.
- Schema registry retention.

Retention dài giúp replay nhưng tăng chi phí và phạm vi dữ liệu nhạy cảm tồn tại. Với event có PII, phải xem xét policy xóa/correction và khả năng replay lại dữ liệu đã bị yêu cầu xóa.

## 28. Kiểm thử producer và consumer

### 28.1. Unit tests

Producer/domain mapping:

- Chỉ phát event sau transition nghiệp vụ hợp lệ.
- Event type, schema version, amount/currency và aggregate version đúng.
- Không đưa field nhạy cảm không được phép vào payload.
- Event ID duy nhất cho lần phát logic.
- Correlation/causation được truyền đúng.

Consumer:

- Xử lý success và duplicate.
- Lỗi transient được retry theo policy.
- Lỗi permanent không retry vô hạn.
- Invalid schema đi quarantine/DLQ.
- Event version cũ/mới được xử lý theo contract.
- Ordering/version gap được phát hiện.
- Side effect có idempotency.

### 28.2. Integration tests

- Producer gửi tới broker thật/test container và consumer nhận được.
- Serialization/deserialization tương thích.
- Kafka key đi đúng partition hoặc Rabbit routing key tới đúng queue.
- ACK/offset commit theo thời điểm mong muốn.
- Retry/DLQ hoạt động.
- Outbox commit và relay publish.
- Duplicate delivery không tạo business side effect trùng.
- Consumer restart/rebalance không mất message.
- Broker unavailable và reconnect có hành vi đúng.
- Schema version mới chạy với consumer cũ theo compatibility matrix.

### 28.3. Contract tests

Producer và consumer có thể được kiểm tra độc lập với schema registry hoặc contract artifacts. Kiểm tra cả:

- Required/optional fields.
- Enum evolution.
- Default/null semantics.
- Field units và meaning.
- Event ordering/aggregate version.
- Consumer behavior với field chưa biết.
- Producer không xóa field trước khi consumers migrate.

Không chỉ test JSON parse thành công; test phải xác minh semantics nghiệp vụ.

## 29. Kiểm thử failure và recovery

Một hệ thống broker integration cần thử:

1. Producer crash sau DB commit nhưng trước relay.
2. Relay publish thành công nhưng crash trước khi đánh dấu outbox row.
3. Consumer crash sau DB commit nhưng trước ACK/offset commit.
4. Broker leader/node failover.
5. Consumer mất kết nối trong lúc đang xử lý.
6. Duplicate event và event đến sai thứ tự.
7. Poison message không deserialize được.
8. Downstream database/provider timeout.
9. DLQ đầy hoặc retention hết.
10. Consumer group tăng/giảm replicas và rebalance.
11. Schema registry không truy cập được.
12. Certificate/credential hết hạn.
13. Backlog tăng nhanh hơn khả năng xử lý.
14. Replay batch lớn trong lúc production traffic đang cao.

Đo business outcomes: không mất đơn, không duplicate charge, reservation không âm, email không gửi lặp ngoài semantics, và mọi trạng thái pending có cách reconcile.

## 30. Local development với Testcontainers

Testcontainers có thể chạy broker tạm trong integration tests thay vì mock toàn bộ behavior. Ví dụ Kafka:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class OrderEventIntegrationTest {

    @Container
    static KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse("confluentinc/cp-kafka:7.6.1")
        );

    @Autowired
    KafkaTemplate<String, OrderPlacedEvent> kafkaTemplate;

    @Test
    void publishesOrderPlacedEvent() {
        // Test configuration phải inject bootstrap server
        // từ kafka.getBootstrapServers() trước khi context khởi tạo.
        // Gửi event và assert consumer/sink nhận đúng contract.
    }
}
~~~

Đây là skeleton, chưa phải test hoàn chỉnh: bootstrap server cần được cung cấp bằng @DynamicPropertySource hoặc cơ chế cấu hình tương ứng **trước khi Spring context khởi tạo**; image version phải tương thích Testcontainers và môi trường. Không coi code minh họa là test đã chạy.

Với RabbitMQ, có thể dùng Testcontainers RabbitMQ module hoặc container image được tổ chức phê duyệt. Test integration nên xác minh exchange/queue/binding, ACK, DLQ và retry semantics.

### 30.1. Mock broker có giới hạn

Mock KafkaTemplate/RabbitTemplate hữu ích cho unit test mapping và error handling ở mức code, nhưng không kiểm chứng partition, offset, ACK, routing, serialization, rebalance hoặc broker failure. Giữ một tập integration tests với broker thật/test container cho những semantics quan trọng.

## 31. Triển khai và nâng cấp consumer an toàn

Consumer có thể cần rollout khác producer:

- Rolling deploy có thể chạy code cũ và mới cùng lúc.
- Event mới có thể tới consumer cũ trong thời gian rollout.
- Consumer group rebalance khi instances tăng/giảm.
- Schema registry compatibility cần phù hợp thứ tự deploy.
- Partition assignment có thể thay đổi.
- DLQ/retry policy có thể thay đổi semantics.

Quy trình thường an toàn hơn:

1. Triển khai consumer đọc được cả schema cũ và mới.
2. Xác minh consumer group ổn định, lag bình thường.
3. Triển khai producer bắt đầu phát schema mới.
4. Quan sát lỗi, lag, DLQ và business outcome.
5. Sau deprecation window, bỏ hỗ trợ schema cũ.
6. Dọn topic/queue cũ khi không còn consumer và retention/replay requirement đã hết.

Nếu thay đổi không tương thích, cần topic/version mới hoặc bridge adapter. Không deploy producer mới trước consumer khi consumer cũ không thể parse payload mới.

## 32. Vận hành Kafka trong production

Một số chủ đề cần có owner:

- Topic partitions và replication factor.
- min.insync.replicas, producer acks và idempotence.
- Retention theo time/size và cleanup policy.
- Consumer groups, offset reset/replay và lag alerts.
- Partition skew/hot key.
- Broker disk/network/CPU.
- Under-replicated partitions và ISR health.
- ACL/SASL/TLS, certificate rotation.
- Schema Registry availability/compatibility.
- Upgrade protocol/broker version.
- Backup/restore hoặc cross-cluster replication nếu yêu cầu.
- Capacity planning và quota.

Ví dụ producer acks=all kết hợp replication/quorum policy có thể tăng độ bền, nhưng không tự bảo đảm mọi trường hợp nếu topic replication và min.insync.replicas không phù hợp. Hiểu durability configuration toàn bộ, không chỉ một property.

## 33. Vận hành RabbitMQ trong production

Cần theo dõi:

- Queue depth và oldest message age.
- Unacked messages và consumer utilization.
- Publisher confirms/returns.
- Connection/channel count.
- Memory/disk alarms.
- Node/cluster health và quorum queue status.
- Queue TTL, DLX, max length và overflow.
- Redelivery/requeue rate.
- Consumer prefetch/concurrency.
- User/vhost/permissions và TLS.
- Federation/shovel nếu có.
- Upgrade, backup definitions và recovery plan.

Quorum queues có semantics durability/replication riêng; không giả định mọi classic queue và quorum queue có cùng failure behavior. Chọn queue type theo durability, performance, topology và phiên bản RabbitMQ đang vận hành.

## 34. Broker outage và degraded mode

Khi broker lỗi, producer/consumer cần hành vi rõ:

- Producer dùng outbox có thể tiếp tục commit business transaction nếu outbox capacity và policy cho phép; backlog phải có giới hạn/cảnh báo.
- Producer không có outbox có thể mất event hoặc phải fail request; cần quyết định theo business semantics.
- Consumer tạm dừng và broker giữ message theo retention/queue capacity.
- Downstream không nên bị retry storm khi broker hồi phục.
- Khi broker khôi phục, replay/backlog processing cần rate limit.
- Message hết retention hoặc queue bị overflow phải có quy trình reconciliation.
- Service health nên phân biệt degraded messaging với toàn bộ process unhealthy.

Không để lệnh “broker down” tự động biến mọi API thành 500 nếu business action có thể được ghi bền vững trong DB/outbox. Ngược lại, không trả thành công nếu business contract yêu cầu một event đã được broker xác nhận mà hệ thống chưa có durable handoff.

## 35. Security, schema và governance ở cấp tổ chức

Để message broker không trở thành data leak hoặc integration spaghetti:

- Mỗi event type có owner và tài liệu.
- Producer chỉ publish vào topics/queues được cấp.
- Consumer chỉ consume tài nguyên cần.
- Schema registry có quyền đăng ký/đọc subject theo ownership.
- Event có classification và retention policy.
- Có contract compatibility gate trong CI.
- Có deprecation window và inventory consumers.
- Có audit thay đổi ACL, topology, schema và replay.
- Có quota/limit để ngăn một producer lỗi tạo hàng tỷ messages.
- Có naming conventions theo domain/environment.
- Không cho nhiều service ghi chung một topic như một bảng database tùy tiện.

### 35.1. Event catalog

Một event catalog nên cho biết:

| Trường | Ví dụ |
|---|---|
| Event type | OrderPlaced |
| Owner | order-service |
| Topic | orders.order-placed.v1 |
| Schema | JSON Schema v1 |
| Meaning | Đơn hàng đã được commit ở trạng thái mới |
| Key | orderId |
| Consumers | billing, inventory, analytics |
| Retention | Theo policy của event class |
| PII classification | Internal, không chứa địa chỉ raw |
| Compatibility | Additive optional fields |
| Replay policy | Có kiểm soát, idempotent |
| Support | Team owner/on-call |

Catalog giúp developer tìm event hiện có và tránh tạo event trùng nghĩa. Nó cũng là nơi theo dõi consumer inventory trước khi deprecate version.

## 36. Quy trình thiết kế một integration event

**Bước 1 — Xác định fact nghiệp vụ.** Event diễn tả điều gì đã thực sự xảy ra, ở thời điểm nào và do domain nào sở hữu?

**Bước 2 — Xác định consumers và use cases.** Ai cần biết? Họ cần dữ liệu gì? Có cần fan-out hay một command queue?

**Bước 3 — Chọn semantics.** Kafka log hay Rabbit queue/routing? Cần replay, ordering, retention và consumer groups thế nào?

**Bước 4 — Định nghĩa contract.** Event ID, type, schema version, aggregate version, timestamps, correlation/causation và payload allowlist.

**Bước 5 — Chọn serialization/schema management.** JSON/Avro/Protobuf, schema registry, compatibility rules.

**Bước 6 — Bảo đảm publish.** Transactional outbox hoặc cơ chế atomic handoff đã được chứng minh; xử lý publish confirm và retry.

**Bước 7 — Thiết kế consumer.** Idempotency, transaction, ACK/offset, concurrency, ordering và side effects.

**Bước 8 — Thiết kế lỗi.** Retry/backoff, permanent error, DLQ, replay, poison messages và outage behavior.

**Bước 9 — Security.** Identity, ACL, TLS, tenant scope, payload classification và retention.

**Bước 10 — Observability.** Publish/consume latency, lag, backlog, outbox, retry, DLQ, correlation và business outcome.

**Bước 11 — Kiểm thử.** Contract, integration, duplicate, crash windows, replay, failover và load.

**Bước 12 — Vận hành.** Ownership, runbook, capacity, upgrade, recovery, deprecation và support.

## 37. Ví dụ end-to-end: OrderPlaced cho Billing Service

Giả sử Order Service ghi đơn hàng rồi Billing Service cần bắt đầu quy trình lập hóa đơn.

### Producer side

1. Client gửi command tạo đơn.
2. Order Service xác thực và kiểm tra domain rules.
3. Một transaction ghi order version mới và outbox event.
4. Transaction commit.
5. Outbox relay publish event có eventId, orderId key và aggregate version.
6. Broker xác nhận theo cấu hình durability.
7. Relay ghi nhận đã publish; có thể lặp khi crash nên consumer deduplicate.

### Consumer side

1. Billing nhận event.
2. Validate schema/version và tenant scope.
3. Bắt đầu DB transaction.
4. Insert (consumerName,eventId) vào processed table.
5. Nếu duplicate, kết thúc an toàn.
6. Nếu mới, tạo billing record với unique order reference.
7. Commit DB transaction.
8. ACK/commit offset.
9. Nếu transient failure, retry theo backoff; permanent invalid event vào DLQ.
10. Phát InvoiceCreated qua outbox của Billing nếu cần thông báo downstream.

### Những điều cần xác minh

- Order DB commit luôn có outbox row tương ứng.
- Billing không tạo invoice trùng khi nhận lại event.
- Event version được dùng đúng nếu nhiều trạng thái đến liên tiếp.
- Broker outage không làm mất order event.
- DLQ có owner và replay procedure.
- Metrics cho thấy outbox age, consumer lag và invoice completion.
- Không có raw customer PII hoặc secret trong message không cần thiết.

## 38. Những sai lầm phổ biến

1. **Gọi broker rồi mới commit database:** consumer có thể xử lý event cho transaction đã rollback.
2. **Commit database rồi publish trực tiếp:** process crash giữa hai bước làm mất event.
3. **Tin broker chỉ giao một lần:** redelivery/replay là hành vi bình thường ở nhiều cấu hình.
4. **Không có idempotency:** duplicate message tạo invoice/payment/reservation trùng.
5. **ACK trước side effect:** crash sau ACK có thể làm mất công việc.
6. **Retry mọi exception vô hạn:** poison message và dependency outage làm queue kẹt.
7. **Requeue ngay không delay:** tạo hot loop và tiêu thụ CPU/network.
8. **Không có DLQ owner:** message lỗi nằm đó vô thời hạn.
9. **Replay không kiểm tra side effects:** tạo giao dịch hoặc notification trùng.
10. **Dùng timestamp thay aggregate version:** event out-of-order có thể làm state sai.
11. **Một topic chứa mọi loại event:** ownership, retention và consumer semantics lẫn lộn.
12. **Payload là ORM entity:** contract bị coupling với schema nội bộ và rò dữ liệu.
13. **Thay schema phá vỡ consumer cũ:** producer deploy trước consumer khiến lỗi diện rộng.
14. **Không phân biệt event và command:** không rõ ai sở hữu hành động và kết quả.
15. **Dùng synchronous request trong consumer không giới hạn:** backlog tăng khi downstream chậm.
16. **Tăng consumer concurrency vô hạn:** database/provider bị quá tải.
17. **Không theo dõi lag/oldest message age:** user flow trễ nhưng API producer vẫn xanh.
18. **Không quản lý credential/ACL:** mọi service có thể đọc/publish mọi topic.
19. **Coi exactly-once broker là exactly-once business:** external side effects vẫn có thể trùng.
20. **Không có event owner/catalog:** event trùng nghĩa, không biết ai được phép deprecate.
21. **Không kiểm thử broker thật:** mock không thể kiểm tra routing/offset/ACK/rebalance.
22. **Không có retention/replay policy:** dữ liệu tồn tại quá lâu hoặc mất trước khi consumer phục hồi.
23. **Bỏ qua outbox backlog:** DB vẫn commit nhưng events chưa đến consumers.
24. **Không xử lý trạng thái UNKNOWN:** timeout provider bị hiểu sai thành thất bại hoặc thành công.

## 39. Checklist triển khai

- [ ] Event/command có semantics nghiệp vụ và owner rõ.
- [ ] Broker được chọn theo ordering, replay, routing, throughput và vận hành.
- [ ] Topic/queue/exchange có naming, ownership, retention và ACL.
- [ ] Contract có eventId, type, schemaVersion, timestamp và aggregate version khi cần.
- [ ] Payload tối thiểu, không có secret/PII ngoài policy.
- [ ] Schema compatibility được kiểm tra trong CI.
- [ ] Producer publish đáng tin; dual write được xử lý bằng outbox/CDC phù hợp.
- [ ] Consumer idempotent bằng event ID và business idempotency key.
- [ ] DB side effect commit trước ACK/offset commit.
- [ ] Ordering/key/partition strategy đáp ứng yêu cầu domain.
- [ ] Retry có phân loại, backoff, jitter, giới hạn và timeout.
- [ ] DLQ có alert, owner, retention và replay runbook.
- [ ] Consumer concurrency phù hợp capacity downstream.
- [ ] Broker auth/TLS/ACL và secret rotation được cấu hình.
- [ ] Có metrics publish/consume/lag/retry/DLQ/outbox.
- [ ] Có trace/correlation nhưng không đưa secret vào headers.
- [ ] Có integration tests với broker thật hoặc test container.
- [ ] Đã thử duplicate, crash window, out-of-order, failover và replay.
- [ ] Có runbook broker outage, backlog, schema failure và credential expiry.
- [ ] Có event catalog và deprecation policy.

## 40. Bài tập tình huống

Một hệ thống thương mại điện tử có luồng:

~~~text
Order API
   |
   v
Order Service ---> PostgreSQL
   |
   +--> Broker
          |
          +--> Inventory Service
          |
          +--> Billing Service
          |
          +--> Notification Worker
~~~

Yêu cầu:

- Đơn hàng phải được lưu trước khi thông báo cho các service khác.
- Billing không được tạo invoice trùng.
- Inventory cần giữ đúng thứ tự các thay đổi của cùng order.
- Notification có thể chậm vài phút nhưng không được gửi vô hạn.
- Broker có thể mất kết nối trong 10 phút.
- Consumer mới phải đọc được event cũ trong thời gian rollout.
- Một số message chứa thông tin khách hàng nhạy cảm.

### Câu hỏi

1. OrderPlaced nên là event hay command? Vì sao?
2. Thiết kế topic/queue và key/routing để các consumer có lifecycle độc lập.
3. Làm sao tránh mất event khi DB commit nhưng broker publish thất bại?
4. Nếu Billing crash sau khi tạo invoice nhưng trước ACK, điều gì xảy ra?
5. Cần dùng eventId hay orderId làm idempotency key trong từng use case?
6. Nếu OrderConfirmed tới trước PaymentAuthorized, consumer nên làm gì?
7. Retry lỗi provider nên dùng backoff/limit thế nào?
8. DLQ cần metadata và replay controls nào?
9. Khi broker outage, Order Service có tiếp tục nhận đơn được không? Điều kiện nào quyết định?
10. Làm sao rollout schema v2 mà consumer v1 vẫn đang chạy?
11. Dữ liệu nào được phép xuất hiện trong event payload?
12. Metrics nào báo sớm rằng business workflow đang chậm dù producer API vẫn trả 2xx?

### Gợi ý tự đối chiếu

- OrderPlaced là fact đã xảy ra; command như ReserveInventory yêu cầu hành động cụ thể.
- Mỗi consumer group/queue có lifecycle và backlog riêng; Kafka dùng key orderId khi cần ordering theo aggregate.
- Dùng transactional outbox trong cùng transaction với order.
- Consumer dùng processed event table/unique constraint cùng transaction với invoice creation.
- Event ID dedup delivery; business idempotency key ngăn cùng một ý định tạo side effect trùng.
- Dùng aggregate version, hold/retry/reconcile khi gap; không bỏ event chỉ vì tới sai thứ tự.
- Retry có phân loại, timeout, backoff và DLQ; không requeue vô hạn.
- DLQ giữ source, eventId, schema version, consumer version, attempt/failure category và audit replay.
- Nếu outbox còn dung lượng và policy cho phép, Order có thể commit cùng outbox trong lúc broker outage; phải alert backlog và có giới hạn capacity.
- Consumer hỗ trợ cả schema v1/v2 trước khi producer chuyển; deprecate sau khi inventory chứng minh không còn reader cũ.
- Chỉ đưa field cần thiết; token, password, raw address và payload PII phải được loại/mã hóa theo policy.
- Theo dõi oldest event age, consumer lag, workflow completion, DLQ và outbox backlog.

## 41. Bài tập thực hành: xây consumer idempotent

Hãy triển khai một consumer nhận PaymentAuthorized:

- Validate event schema và producer identity.
- Kiểm tra eventId đã được xử lý chưa.
- Kiểm tra payment/order state transition hợp lệ.
- Ghi payment authorization trong transaction.
- Ghi outbox OrderPaymentAuthorized trong cùng transaction nếu cần.
- Commit database rồi mới ACK/commit offset.
- Với duplicate, không tạo authorization mới.
- Với version gap, ghi nhận và reconcile theo policy.
- Với lỗi transient, retry có giới hạn.
- Với invalid payload, chuyển DLQ có reason code an toàn.

Kiểm thử tối thiểu:

1. Cùng event gửi hai lần chỉ tạo một authorization.
2. Consumer crash sau DB commit nhưng trước ACK không tạo side effect thứ hai.
3. DB rollback không ghi processed marker.
4. Message schema sai không làm consumer group kẹt vô hạn.
5. Event version đến sai thứ tự được phát hiện.
6. Broker outage không làm lộ hoặc mất credential.
7. DLQ replay sau khi fix không nhân đôi kết quả.

## 42. Kết luận

Message broker giúp microservices giao tiếp bất đồng bộ, giảm phụ thuộc thời gian giữa producer và consumer, hấp thụ burst và phân phối domain events cho nhiều nhóm. Nhưng broker không tự giải quyết tính đúng đắn nghiệp vụ: producer cần phát event gắn với transaction đáng tin, consumer phải idempotent, ordering phải được thiết kế theo aggregate, và retry/DLQ/replay cần có policy rõ.

Trong Java và Spring, KafkaTemplate/@KafkaListener hoặc RabbitTemplate/@RabbitListener giúp tích hợp thuận tiện, nhưng semantics thực tế vẫn phụ thuộc broker, listener container, ACK/offset, transaction manager và cấu hình triển khai. Hãy thiết kế contract và failure behavior trước khi viết listener; dùng outbox để tránh dual-write, kiểm thử duplicate/crash/replay, bảo vệ payload và theo dõi lag đến business outcome.

**Một integration broker tốt được đánh giá bằng việc sự kiện đúng được giao và xử lý an toàn qua cả lỗi, retry, deploy và phục hồi**, chứ không chỉ bằng việc producer gửi được message hoặc consumer có log “received”.
