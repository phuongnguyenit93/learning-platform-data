# Spring for Apache Pulsar và lớp tích hợp riêng

## 1. Bài toán tích hợp Pulsar trong ứng dụng Spring

Apache Pulsar cung cấp hệ thống messaging phân tán với topic, subscription, producer, consumer, schema, acknowledgement, redelivery và transaction. Ứng dụng Spring có thể dùng trực tiếp Pulsar Java Client, nhưng khi làm như vậy code nghiệp vụ phải tự quản lý nhiều chi tiết kết nối và vòng đời.

**Spring for Apache Pulsar** đưa các abstraction quen thuộc của Spring vào Pulsar:

- `PulsarTemplate` để gửi message.
- `@PulsarListener` và listener container để tiêu thụ message.
- `@PulsarReader` khi cần đọc topic với vị trí bắt đầu/cursor do ứng dụng chỉ định.
- Spring Boot auto-configuration cho client, producer factory, consumer factory, listener infrastructure và property cấu hình.
- Hỗ trợ schema, acknowledgement, retry, Dead Letter Topic, transaction và Micrometer observation.

Một ứng dụng vẫn có thể cần **lớp tích hợp riêng** để chuyển đổi domain event sang message contract, chuẩn hóa metadata, áp dụng policy của tổ chức hoặc che chi tiết broker khỏi application service. Lớp này nên bổ sung quy tắc của ứng dụng trên các abstraction Spring đã có.

Không nên nhầm ba lớp:

1. **Apache Pulsar Java Client:** API nền tảng, trực tiếp điều khiển producer, consumer, reader, admin và transaction.
2. **Spring for Apache Pulsar:** tích hợp client vào Spring bằng template, listener, container, schema, transaction và auto-configuration.
3. **Lớp tích hợp riêng của ứng dụng:** adapter và policy thuộc hệ thống, ví dụ contract event, topic mapping, correlation, idempotency, outbox hoặc quy tắc xử lý lỗi.

Mỗi lớp có trách nhiệm riêng. Khi phân chia rõ, ứng dụng tận dụng khả năng đã có của Spring/Pulsar và vẫn giữ được hợp đồng nghiệp vụ độc lập với broker.

## 2. Chọn đúng dự án và phiên bản

Bài này tập trung vào dự án **Spring for Apache Pulsar** do Spring duy trì, với package Java `org.springframework.pulsar` và starter Spring Boot `spring-boot-starter-pulsar`.

Với Spring Boot, dependency starter thường là điểm bắt đầu:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-pulsar</artifactId>
</dependency>
~~~

Hoặc Gradle:

~~~groovy
implementation("org.springframework.boot:spring-boot-starter-pulsar")
~~~

Nên để Spring Boot dependency management/BOM quản lý phiên bản starter và các dependency liên quan. Chỉ override Pulsar Client khi compatibility matrix và yêu cầu triển khai cho phép.

Compatibility matrix của Spring for Apache Pulsar 2.0.x ghi nhận các tổ hợp Pulsar Client 4.1.x, 4.0.x hoặc 3.3.x, Spring Boot 4.0.x và Java 17+. Dòng 1.2.x hỗ trợ Spring Boot 3.4.x/3.5.x với Pulsar Client 3.3.x hoặc cấu hình tương thích được tài liệu nêu. Matrix thay đổi theo release; cần kiểm tra đúng phiên bản Spring Boot, Spring for Apache Pulsar và Pulsar Client của dự án trước khi nâng cấp.

Tên dự án tích hợp Pulsar cho Spring có thể gây nhầm lẫn. Tài liệu Apache Pulsar hiện có một project riêng với artifact group `org.apache.pulsar` và module `pulsar-spring`. Đây là project line khác với Spring-maintained `org.springframework.pulsar:spring-pulsar`. Không trộn dependency, package hoặc ví dụ API giữa hai project.

## 3. Kiến trúc từ ứng dụng tới broker

Luồng publish thường có dạng:

~~~text
Domain / Application Service
          |
          | domain event hoặc command
          v
Application-owned messaging port
          |
          | map sang message contract
          v
Spring Pulsar adapter
          |
          | PulsarTemplate
          v
Pulsar Producer / Client
          |
          v
Topic / Partition / Broker
~~~

Luồng consume đi theo chiều ngược lại:

~~~text
Pulsar Topic
     |
     v
Pulsar Consumer
     |
     v
Spring Listener Container
     |
     v
@PulsarListener adapter
     |
     | validate + map contract
     v
Application Service / Use Case
     |
     v
Domain state / Database
~~~

Spring listener container tạo và quản lý Pulsar consumer, nhận message rồi chuyển cho listener method. Annotation `@PulsarListener` là cách khai báo thuận tiện; khi cần kiểm soát nhiều hơn, có thể dùng listener container factory hoặc Pulsar Java Client ở adapter chuyên biệt.

Lớp tích hợp riêng nên nằm ở ranh giới giữa application và transport. Domain model không cần biết tên topic, subscription type, `PulsarTemplate` hay Pulsar `MessageId`.

## 4. Cấu hình kết nối và auto-configuration

Spring Boot tự cấu hình `PulsarClient` khi starter có trên classpath. Mặc định client kết nối tới `pulsar://localhost:6650`; có thể đổi bằng property:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar://localhost:6650
~~~

Đây là Pulsar protocol URL, không phải HTTP Admin URL. Spring Boot cũng có thể auto-configure Pulsar administration client; Admin API mặc định thường dùng `http://localhost:8080` và được cấu hình riêng qua `spring.pulsar.admin.service-url`.

Các nhóm property thường gặp:

| Prefix | Vai trò |
|---|---|
| `spring.pulsar.client.*` | PulsarClient, service URL, timeout, authentication, TLS và thread |
| `spring.pulsar.admin.*` | PulsarAdministration và Admin API |
| `spring.pulsar.producer.*` | Producer mặc định, batching, compression, routing và cache |
| `spring.pulsar.consumer.*` | Consumer mặc định, subscription, receiver queue và acknowledgement |
| `spring.pulsar.listener.*` | Listener container và concurrency |
| `spring.pulsar.reader.*` | Reader factory và reader properties |
| `spring.pulsar.transaction.*` | Bật và cấu hình transaction support |

Ví dụ cấu hình authentication OAuth2:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example.net:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.oauth2.AuthenticationOAuth2
        param:
          issuerUrl: https://auth.example.net/
          privateKey: file:/run/secrets/pulsar-private-key.json
          audience: urn:example:pulsar:production
~~~

Tên tham số trong map authentication phải khớp chính xác với tên mà authentication plugin yêu cầu; các key này không được relaxed binding như property Spring thông thường. Nếu dùng TLS, kiểm tra trust certificate, hostname verification và cấu hình provider theo tài liệu triển khai.

Spring Boot hỗ trợ customizer khi property chuẩn chưa đủ:

- `PulsarClientBuilderCustomizer` để tùy chỉnh client.
- `PulsarAdminBuilderCustomizer` để tùy chỉnh admin client.
- `ProducerBuilderCustomizer` và `ConsumerBuilderCustomizer` cho producer/consumer.
- `PulsarContainerFactoryCustomizer` cho listener container factory.
- `PulsarTemplateCustomizer` cho template.

Nên dùng property trước, sau đó mới thêm customizer cho tùy chọn chuyên biệt. Không tạo một `PulsarClient` mới cho mỗi lần gửi message; dùng client và factory do Spring quản lý để tái sử dụng connection và resource.

## 5. Gửi message với PulsarTemplate

### 5.1. Simple API

Spring Boot auto-configure `PulsarTemplate<T>`. Một component có thể inject template và gửi message:

~~~java
import org.springframework.pulsar.core.PulsarTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {

    private final PulsarTemplate<String> pulsarTemplate;

    public OrderEventPublisher(PulsarTemplate<String> pulsarTemplate) {
        this.pulsarTemplate = pulsarTemplate;
    }

    public void publish(String payload) {
        pulsarTemplate.send("persistent://acme/orders/order-events", payload);
    }
}
~~~

`send` là thao tác đồng bộ: method chờ kết quả publish và trả về `MessageId` khi message đã được broker persist theo semantics của producer. Nếu caller không cần chờ, có thể dùng `sendAsync`, nhận `CompletableFuture` để xử lý kết quả bất đồng bộ.

Không nên hiểu việc method gửi trả về là business workflow đã hoàn tất ở consumer. Nó xác nhận kết quả publish của producer theo cấu hình broker; consumer có thể xử lý sau đó.

### 5.2. Fluent API và message key

Khi cần thiết lập key, property hoặc metadata, dùng fluent API:

~~~java
pulsarTemplate.newMessage(event)
    .withMessageCustomizer(builder -> builder.key(orderId))
    .send();
~~~

Message key hữu ích khi cần định tuyến theo key và duy trì thứ tự theo một entity trong subscription hỗ trợ ordering tương ứng. Ví dụ, dùng `orderId` làm key để các event của cùng đơn hàng đi theo cùng một nhóm xử lý/partition phù hợp.

Có thể dùng `TypedMessageBuilderCustomizer` để tùy chỉnh message và `ProducerBuilderCustomizer` để tùy chỉnh producer. Customizer áp dụng riêng cho một lần gửi hoặc toàn factory tùy nơi đăng ký. Những API này cho phép mở rộng cấu hình mà không cần tự viết lại producer lifecycle.

### 5.3. Topic resolution

Topic có thể truyền trực tiếp vào API:

~~~java
pulsarTemplate.send("persistent://acme/orders/order-events", event);
~~~

Nếu không truyền topic, Spring for Apache Pulsar có thể giải quyết destination theo thứ tự: topic do người dùng chỉ định, topic mặc định gắn với message type, rồi global default. Nếu không tìm thấy topic, thao tác sẽ thất bại.

Topic đầy đủ thường có dạng:

~~~text
persistent://tenant/namespace/topic-name
~~~

Nên quản lý tên topic trong cấu hình ứng dụng hoặc một topic catalog có kiểm soát, không rải literal string ở nhiều service. Đối với topic partitioned hoặc topic có policy đặc biệt, quản lý việc tạo và cấu hình topic bằng quy trình hạ tầng rõ ràng.

## 6. Nhận message với @PulsarListener

### 6.1. Listener cơ bản

`@PulsarListener` tạo listener endpoint và để container quản lý Pulsar consumer:

~~~java
import org.springframework.pulsar.annotation.PulsarListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @PulsarListener(
        topics = "persistent://acme/orders/order-events",
        subscriptionName = "inventory-service-v1"
    )
    public void handle(String payload) {
        // Delegate to an application use case.
    }
}
~~~

Khi dùng Spring Boot starter, annotation processing và listener infrastructure được auto-configure. Nếu không dùng Spring Boot, cần bật `@EnablePulsar` và tự cung cấp các factory/container phù hợp.

Luôn đặt `subscriptionName` tường minh trong môi trường production. Nếu bỏ trống, framework có thể tạo subscription name tự động; điều đó thường không phù hợp khi cần nhiều replica cùng chia sẻ một subscription ổn định.

### 6.2. Subscription type và concurrency

Pulsar có nhiều subscription type với semantics khác nhau:

| Type | Hành vi chính | Trường hợp sử dụng |
|---|---|---|
| `Exclusive` | Một consumer hoạt động trên subscription | Đơn giản, một consumer xử lý |
| `Failover` | Một consumer active, consumer khác dự phòng | Cần failover và ordering theo semantics của Pulsar |
| `Shared` | Message được phân phối giữa nhiều consumer | Tăng throughput, không bảo đảm thứ tự tổng thể |
| `Key_Shared` | Phân phối theo key, giữ thứ tự cho cùng key theo cấu hình phù hợp | Scale consumer nhưng vẫn cần ordering theo entity/key |

`@PulsarListener` mặc định dùng `Exclusive` nếu không cấu hình khác. Với nhiều replica cùng xử lý một subscription, cần chọn subscription type phù hợp. `Shared` phù hợp cho workload có thể xử lý song song; nếu cần ordering theo key, xem xét `Key_Shared` và gửi message có key ổn định.

Ví dụ listener chia sẻ subscription:

~~~java
@PulsarListener(
    topics = "persistent://acme/orders/order-events",
    subscriptionName = "inventory-service-v1",
    subscriptionType = SubscriptionType.Shared,
    concurrency = "3"
)
void handle(OrderPlacedV1 event) {
    inventoryService.reserve(event);
}
~~~

Concurrency lớn hơn 1 chỉ có ý nghĩa với subscription type hỗ trợ nhiều consumer như Failover, Shared hoặc Key_Shared. Với topic partitioned, số partition và số consumer quyết định mức song song thực tế. Tăng concurrency trên topic không partitioned không tự tạo thêm partition để tăng throughput.

### 6.3. PulsarReader khác PulsarListener

`@PulsarListener` sử dụng consumer subscription, acknowledgement và redelivery. `@PulsarReader` dùng Pulsar Reader API để đọc topic từ một message ID/cursor được chỉ định, ví dụ `earliest` hoặc `latest`.

Dùng Reader khi cần tự quản lý vị trí bắt đầu đọc hoặc đọc lại dữ liệu theo cursor. Không thay listener bằng reader cho consumer nghiệp vụ thông thường nếu cần subscription, load balancing, acknowledgement và retry. Reader có lifecycle và semantics khác consumer.

## 7. Schema và serialization

### 7.1. Chọn schema tường minh

Spring for Apache Pulsar sử dụng Pulsar Schema để serialize/deserialize payload. Với kiểu primitive, framework có thể suy luận schema. Với kiểu phức tạp, schema mặc định thường là JSON nếu không cấu hình khác.

Các schema thường dùng:

- `JSON`: dễ đọc, phù hợp DTO và tích hợp nhiều ngôn ngữ.
- `AVRO`: schema rõ ràng, có quy tắc writer/reader schema và evolution.
- `PROTOBUF`: schema nhị phân với field number và code generation.
- `KEY_VALUE`: payload gồm key và value theo schema.
- `AUTO_CONSUME` hoặc `AUTO_PRODUCE_BYTES`: khi cần xử lý record generic hoặc bytes theo schema của topic.

Ví dụ khai báo schema JSON rõ ràng trên listener:

~~~java
@PulsarListener(
    topics = "persistent://acme/orders/order-placed-v1",
    subscriptionName = "billing-service-v1",
    schemaType = SchemaType.JSON
)
void handle(OrderPlacedV1 event) {
    billingService.createInvoice(event);
}
~~~

Với message type phức tạp, nên khai báo schema hoặc mapping rõ ràng thay vì phụ thuộc vào suy luận mặc định. Producer và consumer phải thống nhất contract, field, null/default, enum, timestamp, đơn vị tiền tệ và quy tắc versioning.

### 7.2. Ví dụ contract

~~~java
public record OrderPlacedV1(
    String eventId,
    String orderId,
    String customerId,
    long occurredAtEpochMillis,
    String currency,
    long totalMinorUnits
) {}
~~~

Contract là DTO tích hợp, không phải entity ORM hay domain aggregate. Nó chỉ chứa dữ liệu cần công bố. Nếu domain model thay đổi, mapper ở producer giữ cho message contract ổn định.

Pulsar Schema Registry kiểm tra schema của topic theo compatibility policy. Khi thay đổi contract, phải xem xét consumer cũ có thể đọc schema mới hay không. Thêm field optional thường dễ tương thích hơn đổi kiểu hoặc xóa field; không tái sử dụng field number của Protobuf đã bỏ và không đổi ý nghĩa field mà vẫn giữ tên cũ.

### 7.3. Schema mapping và @PulsarMessage

Có thể cấu hình type-to-schema mapping qua `spring.pulsar.defaults.type-mappings` hoặc `SchemaResolverCustomizer`. Tài liệu cũng hỗ trợ annotation `@PulsarMessage(schemaType = SchemaType.JSON)` để đặt schema mặc định cho message type.

Mapping theo Java class giúp cấu hình trong ứng dụng, nhưng class name trong cấu hình nội bộ không nên trở thành một phần contract bắt buộc giữa các service. Contract trên wire cần được quản lý qua Pulsar schema và quy tắc compatibility.

Nếu consumer chưa biết schema cụ thể, `AUTO_CONSUME` cho phép đọc generic record và truy cập field theo metadata schema. Cách này hữu ích cho tooling, router hoặc xử lý nhiều loại record; với business handler thông thường, DTO có kiểu rõ ràng thường dễ kiểm tra hơn.

## 8. Headers, properties và message key

Pulsar không có một abstraction header hoàn toàn giống Spring Messaging. Pulsar message cung cấp metadata và map user properties. Spring for Apache Pulsar ánh xạ chúng sang `MessageHeaders` thông qua `PulsarHeaderMapper`.

Consumer có thể đọc metadata bằng `@Header`:

~~~java
@PulsarListener(topics = "persistent://acme/orders/order-events")
void handle(
        OrderPlacedV1 event,
        @Header(PulsarHeaders.MESSAGE_ID) MessageId messageId,
        @Header("correlationId") String correlationId) {
    // Process the event and include IDs in logs/traces.
}
~~~

Header thường dùng cho message ID, key, event time, correlation ID và metadata kỹ thuật. Payload vẫn là nơi chứa dữ liệu nghiệp vụ chính.

Một số lưu ý:

- Không đưa toàn bộ domain object vào user properties.
- Chỉ truyền các header thực sự cần thiết qua broker.
- Không tin tenant ID hoặc user ID chỉ vì nó xuất hiện trong header; xác thực ở tầng bảo mật.
- Nếu dùng JSON header mapper, cấu hình trusted package và danh sách header được phép.
- Tránh high-cardinality metric tag như order ID hoặc customer ID.

Message key ảnh hưởng routing và ordering; header metadata không tự tạo ordering. Nếu cần thứ tự theo aggregate, hãy chọn key và subscription type phù hợp, sau đó kiểm thử với partitioned topic.

## 9. Acknowledgement, redelivery và xử lý lỗi

### 9.1. Automatic acknowledgement

Listener container điều phối việc nhận và acknowledge message. Với record listener, chế độ mặc định `BATCH` xử lý message nhận được theo batch nội bộ rồi acknowledge batch khi các record thành công; record lỗi được negative acknowledge theo cơ chế container.

Có thể chọn `AckMode.RECORD` để acknowledge hoặc nack từng record sau khi listener xử lý. Với batch listener, `RECORD` không được hỗ trợ; nếu cần quyết định từng message trong batch, dùng manual acknowledgement.

### 9.2. Manual acknowledgement

Chỉ dùng manual ack khi ứng dụng cần kiểm soát thời điểm xác nhận message:

~~~java
@PulsarListener(
    topics = "persistent://acme/orders/order-events",
    subscriptionName = "billing-service-v1",
    ackMode = AckMode.MANUAL
)
void handle(Message<OrderPlacedV1> message, Acknowledgment acknowledgment) {
    billingService.createInvoice(message.getValue());
    acknowledgment.acknowledge();
}
~~~

Chỉ acknowledge sau khi xử lý đã đạt trạng thái bền vững theo cam kết ứng dụng. Nếu acknowledge trước khi database commit, process có thể chết sau ack và message không được gửi lại dù dữ liệu chưa được lưu.

Manual ack chuyển trách nhiệm acknowledgement sang ứng dụng. Cần xác định rõ trường hợp success, retryable failure, permanent failure và thời điểm nack.

### 9.3. Redelivery và backoff

Pulsar có redelivery khi ack timeout hoặc negative acknowledgement. Có thể cấu hình `ackTimeoutMillis`, `negativeAckRedeliveryDelay` hoặc `RedeliveryBackoff` với khoảng chờ tăng dần.

Không retry mọi exception vô hạn. Phân loại:

- Lỗi tạm thời: dependency timeout, broker/network tạm thời lỗi; retry có giới hạn và backoff.
- Lỗi dữ liệu: schema không hợp lệ, payload thiếu field bắt buộc; thường cần chuyển sang DLT/DLQ hoặc quarantine để điều tra.
- Lỗi nghiệp vụ: trạng thái không cho phép; tùy contract có thể ghi nhận kết quả từ chối thay vì redeliver.
- Lỗi code: bug trong handler; giới hạn retry để tránh poison message chiếm consumer.

### 9.4. Dead Letter Topic

Pulsar native Dead Letter Policy hỗ trợ Shared subscription; không hỗ trợ native DLQ cho Exclusive và Failover vì redelivery có thể phá ordering semantics. Với Shared subscription, cấu hình `DeadLetterPolicy` và cung cấp DLT topic rõ ràng:

~~~java
@Bean
DeadLetterPolicy orderDeadLetterPolicy() {
    return DeadLetterPolicy.builder()
        .maxRedeliverCount(10)
        .deadLetterTopic("persistent://acme/orders/order-events-dlt")
        .build();
}
~~~

Sau đó tham chiếu bean trong annotation `@PulsarListener(deadLetterPolicy = "orderDeadLetterPolicy")`. Khi dùng partitioned topic, nên chỉ định DLT topic tường minh thay vì phụ thuộc tên mặc định có thể chứa hậu tố partition.

Spring for Apache Pulsar còn có `PulsarConsumerErrorHandler` và `PulsarDeadLetterPublishingRecoverer` để triển khai recovery/DLT cho nhiều subscription type. Đây là cơ chế khác với native DLQ của Pulsar; nếu dùng cho Exclusive/Failover, cần hiểu rằng retry/recovery có thể làm thay đổi ordering. Không cấu hình đồng thời các cơ chế acknowledgement/retry xung đột.

## 10. Transaction support

Spring for Apache Pulsar cung cấp:

- `PulsarTransactionManager`.
- Transactional `PulsarTemplate`.
- Transactional `@PulsarListener`.
- Đồng bộ với Spring transaction manager khác theo khả năng được tài liệu hỗ trợ.

Transaction support tắt mặc định. Có thể bật qua:

~~~yaml
spring:
  pulsar:
    transaction:
      enabled: true
~~~

Một consume-process-produce flow có thể chạy trong Pulsar transaction: listener nhận message, xử lý, publish message mới qua transactional template và container enlist acknowledgement vào cùng Pulsar transaction. Nếu xử lý hoặc publish thất bại, transaction rollback và message đầu vào có thể được redeliver.

Pulsar transaction không tự biến database transaction và broker transaction thành một transaction nguyên tử toàn hệ thống. Khi kết hợp JDBC transaction với Pulsar transaction, cần hiểu thứ tự commit và tình huống một bên commit trong khi bên kia thất bại. Thiết kế idempotency cho DB write và cân nhắc transactional outbox/inbox khi cần bảo đảm giữa database và broker.

Không bật transaction chỉ vì annotation `@Transactional` có sẵn. Chọn transaction boundary theo nghiệp vụ, kiểm tra timeout và khả năng broker, rồi kiểm thử commit/rollback với broker thật.

## 11. Spring Cloud Stream Pulsar Binder

Nếu ứng dụng muốn tập trung vào function-based event processing và hạn chế phụ thuộc vào middleware, có thể dùng Spring Cloud Stream Pulsar Binder.

Mô hình function thường dùng:

- `Supplier<T>` phát dữ liệu.
- `Function<T, R>` nhận và biến đổi dữ liệu.
- `Consumer<T>` tiêu thụ dữ liệu.

Spring Cloud Stream ánh xạ input/output binding sang Pulsar topic qua cấu hình destination. Binder quản lý binding và kết nối với Pulsar. Khi dùng binder, application code có thể ít phụ thuộc trực tiếp vào `PulsarTemplate` hoặc `@PulsarListener` hơn.

Ví dụ cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: orderProcessor
    stream:
      bindings:
        orderProcessor-in-0:
          destination: orders.raw
        orderProcessor-out-0:
          destination: orders.validated
~~~

Trong binder, message conversion mặc định thường dùng `application/json` ở Spring Messaging rồi truyền bytes qua Pulsar `Schema.BYTES`. Nếu muốn Pulsar native schema encoding/decoding, cần bật `use-native-encoding` ở producer và `use-native-decoding` ở consumer, đồng thời cấu hình schema type/message type cho binding.

Chọn binder khi cần mô hình function/binding, cấu hình destination và tính middleware-neutral. Chọn Spring for Apache Pulsar trực tiếp khi cần kiểm soát sâu Pulsar-specific features như schema, key, subscription, acknowledgement, reader, producer customizer hoặc Pulsar transaction. Không thêm cả binder và lớp abstraction riêng nếu không có nhu cầu cụ thể; mỗi tầng bổ sung đều làm tăng độ phức tạp cấu hình và debugging.

## 12. Thiết kế lớp tích hợp riêng của ứng dụng

### 12.1. Nên đặt trách nhiệm ở đâu?

Một lớp tích hợp riêng hữu ích khi nó chứa quy tắc chung của hệ thống:

- Ánh xạ domain event/command sang message contract versioned.
- Chọn topic theo loại event, tenant hoặc bounded context.
- Gắn message key, event ID, correlation ID và causation ID.
- Chuẩn hóa log, tracing và metric tag.
- Áp dụng chính sách idempotency, outbox/inbox và deduplication.
- Chuẩn hóa retry, DLT routing và phân loại lỗi nghiệp vụ.
- Cung cấp port để application service không phụ thuộc vào Pulsar khi thực sự cần thay transport hoặc test độc lập.

Không nên đặt logic nghiệp vụ vào một generic messaging framework. Domain quyết định khi nào một event xảy ra; integration adapter quyết định cách công bố event đó lên broker.

### 12.2. Ví dụ port và adapter

Application layer định nghĩa port theo ngôn ngữ nghiệp vụ:

~~~java
public interface OrderEventPublisher {
    void publish(OrderPlaced event);
}
~~~

Adapter sử dụng Spring for Apache Pulsar:

~~~java
import org.springframework.pulsar.core.PulsarTemplate;
import org.springframework.stereotype.Component;

@Component
public class PulsarOrderEventPublisher implements OrderEventPublisher {

    private final PulsarTemplate<OrderPlacedV1> template;

    public PulsarOrderEventPublisher(PulsarTemplate<OrderPlacedV1> template) {
        this.template = template;
    }

    @Override
    public void publish(OrderPlaced event) {
        OrderPlacedV1 contract = new OrderPlacedV1(
            event.eventId(),
            event.orderId().toString(),
            event.customerId().toString(),
            event.occurredAt().toEpochMilli(),
            event.currency(),
            event.totalMinorUnits()
        );

        template.newMessage(contract)
            .withMessageCustomizer(builder -> builder.key(contract.orderId()))
            .send();
    }
}
~~~

Đoạn code là ví dụ adapter; kiểu domain `OrderPlaced` và topic configuration thuộc ứng dụng. Trong production, topic nên được lấy từ configuration properties hoặc topic catalog thay vì hard-code.

Consumer adapter nhận DTO rồi gọi application service:

~~~java
import org.springframework.pulsar.annotation.PulsarListener;
import org.springframework.stereotype.Component;

@Component
public class InventoryPulsarAdapter {

    private final ReserveInventoryUseCase useCase;

    public InventoryPulsarAdapter(ReserveInventoryUseCase useCase) {
        this.useCase = useCase;
    }

    @PulsarListener(
        topics = "persistent://acme/orders/order-placed-v1",
        subscriptionName = "inventory-service-v1",
        schemaType = SchemaType.JSON,
        subscriptionType = SubscriptionType.Shared
    )
    public void onOrderPlaced(OrderPlacedV1 message) {
        useCase.reserve(
            message.orderId(),
            message.eventId()
        );
    }
}
~~~

Application service chỉ thấy use case và domain data. Nó không cần import `PulsarTemplate`, `PulsarClient`, `Consumer` hay `MessageId`.

### 12.3. Khi nào không cần custom wrapper?

Nếu ứng dụng chỉ có một producer, một listener và không có quy tắc tích hợp chung, inject `PulsarTemplate` và dùng `@PulsarListener` trực tiếp có thể là lựa chọn đơn giản nhất.

Không tạo wrapper một-một cho mọi method của Pulsar Client. Một interface như `MessagingService.send(Object)`, `receive()` hoặc `publish(String, Object)`, không thể hiện semantics về topic, schema, key, acknowledgement và retry sẽ chỉ che API mà không tạo abstraction có ích.

Nếu abstraction che mất tính năng Pulsar quan trọng, hãy để adapter cụ thể dùng Spring/Pulsar API ở bên trong và chỉ giữ contract nghiệp vụ ổn định ở bên ngoài.

### 12.4. Không tự viết lại các phần Spring đã cung cấp

Tránh tự triển khai lại:

- PulsarClient lifecycle và connection management.
- Producer/consumer cache và factory.
- Listener container, thread management và consumer lifecycle.
- Schema serialization/deserialization đã có trong framework.
- Acknowledgement, redelivery và listener recovery.
- Pulsar transaction manager.
- Micrometer observation cho template/listener.

Khi cần khác biệt, ưu tiên property, factory customizer, template customizer, schema resolver customizer hoặc listener-specific customizer. Chỉ dùng Pulsar Java Client trực tiếp trong adapter chuyên biệt khi tính năng cần thiết chưa được Spring abstraction cung cấp.

## 13. Quan sát và vận hành

Spring for Apache Pulsar tích hợp Micrometer Observation cho `PulsarTemplate` và `@PulsarListener`. Khi có `ObservationRegistry`, send/receive operations được trace và đo thời gian. Spring Boot Actuator có thể tự cấu hình registry trong ứng dụng Boot.

Các observation/metric phổ biến gồm:

- `spring.pulsar.template`: thời gian gửi message.
- `spring.pulsar.template.active`: số operation publish đang hoạt động.
- `spring.pulsar.listener`: thời gian xử lý/nhận message ở listener.
- `spring.pulsar.listener.active`: operation listener đang hoạt động.

Tag mặc định có thể bao gồm template bean name và listener ID. Có thể thêm tag qua `PulsarTemplateObservationConvention` hoặc `PulsarListenerObservationConvention`. Chỉ dùng tag có cardinality thấp; không đưa order ID hoặc user ID vào metric label.

Bên cạnh metric framework, cần theo dõi:

- Publish success/failure và latency.
- Consumer backlog, message age và processing latency.
- Redelivery count, nack, ack timeout và DLT volume.
- Subscription/consumer count và partition distribution.
- Outbox backlog nếu có.
- Schema incompatibility và serialization failure.
- Transaction rollback/timeout.

Log nên chứa topic, subscription, message ID, key và correlation ID ở mức phù hợp. Không log toàn bộ payload nhạy cảm hoặc credential.

## 14. Kiểm thử

Một bộ test tốt cần kiểm tra contract và semantics với broker, không chỉ mock `PulsarTemplate`.

**Unit test application layer:** kiểm tra domain event, use case, validation và idempotency mà không cần Pulsar.

**Adapter test:** kiểm tra mapper domain-to-contract, topic routing, key và metadata.

**Integration test:** khởi động Pulsar test broker/container, gửi message và xác nhận listener xử lý đúng. Spring for Apache Pulsar có module `spring-pulsar-test` với `PulsarConsumerTestUtil` và `PulsarTestContainerSupport` để hỗ trợ test.

**Failure test:** kiểm tra schema mismatch, listener exception, retry, redelivery, DLT, broker unavailable và restart.

**Transaction test:** xác nhận message output và acknowledgement commit/rollback đúng; nếu có database, kiểm thử cả trường hợp DB commit nhưng Pulsar transaction thất bại.

**Compatibility test:** producer mới và consumer cũ/mới đọc được schema theo policy; kiểm tra field optional, enum mở rộng và version mới.

Một bài test cần kiểm tra subscription type và ordering thực tế. Mock không thể chứng minh Shared subscription giữ thứ tự, hoặc native DLQ hoạt động đúng trên broker.

## 15. Lỗi thiết kế thường gặp

1. **Tự tạo PulsarClient cho mỗi request.** Điều này lãng phí connection và resource. Dùng auto-configured client/factory và template.
2. **Để topic name rải khắp code.** Khó thay đổi naming, tenant hoặc version. Dùng configuration/topic catalog.
3. **Không khai báo subscription name ổn định.** Mỗi instance có thể tạo subscription riêng, làm thay đổi semantics load balancing.
4. **Dùng Shared nhưng giả định ordering toàn cục.** Shared không bảo đảm thứ tự tổng thể; dùng key và Key_Shared khi cần ordering theo entity.
5. **Tăng concurrency trên Exclusive subscription.** Không tạo thêm consumer hoạt động; chọn subscription type phù hợp và xét partition count.
6. **Không khai báo schema cho DTO phức tạp.** Producer/consumer có thể suy luận khác nhau. Đặt schema rõ ràng và kiểm thử compatibility.
7. **Retry vô hạn poison message.** Tạo backlog và tốn tài nguyên. Giới hạn retry, backoff và DLT.
8. **Bật native DLQ trên subscription không hỗ trợ.** Native DLQ chỉ hỗ trợ Shared; với subscription khác cần cơ chế error handler và hiểu tác động ordering.
9. **Acknowledge trước khi commit dữ liệu.** Có thể mất message khi ứng dụng chết. Ack sau khi đạt điều kiện bền vững hoặc dùng Pulsar transaction.
10. **Cho rằng Pulsar transaction bao gồm database transaction.** Không có atomicity tự động xuyên hai resource; dùng idempotency, outbox/inbox và kiểm thử failure.
11. **Tự viết lại listener container và producer cache.** Tăng code vận hành, khó xử lý lifecycle. Dùng abstraction Spring và customizer.
12. **Tạo generic wrapper không mang semantics.** Chỉ che API mà không giảm coupling. Thiết kế port theo use case và contract cụ thể.
13. **Bỏ qua compatibility matrix.** Spring Boot, Spring Pulsar và Pulsar Client có release cycle riêng. Kiểm tra version matrix trước nâng cấp.

## 16. Quy trình chọn kiến trúc

Có thể quyết định theo trình tự:

1. Ứng dụng chỉ cần gửi/nhận topic theo API Spring? Bắt đầu bằng Spring for Apache Pulsar.
2. Có nhiều listener và producer? Dùng auto-configuration, listener container và factory customizer.
3. Cần function-based pipeline và middleware-neutral binding? Đánh giá Spring Cloud Stream Pulsar Binder.
4. Cần giữ domain độc lập với broker? Thêm port/adapter riêng cho contract và mapping nghiệp vụ.
5. Cần tính năng Pulsar-specific chưa có trong Spring abstraction? Dùng Pulsar Java Client bên trong adapter chuyên biệt.
6. Có yêu cầu retry, ordering, DLT, schema evolution hoặc transaction? Thiết kế theo semantics Pulsar trước, rồi cấu hình Spring abstraction.
7. Có nhiều service độc lập? Quản lý schema/contract version, subscription name và topic governance ở cấp nền tảng.

## 17. Checklist trước khi phát hành

- [ ] Chọn đúng Spring for Apache Pulsar artifact và compatibility matrix.
- [ ] PulsarClient được quản lý bởi Spring, không tạo mới cho mỗi thao tác.
- [ ] Service URL, TLS và authentication được cấu hình đúng môi trường.
- [ ] Topic và subscription name ổn định, có owner rõ ràng.
- [ ] Subscription type phù hợp với throughput và ordering.
- [ ] Schema được khai báo/version hóa và kiểm thử compatibility.
- [ ] Producer xác định key, metadata và send sync/async phù hợp.
- [ ] Consumer xác định ack mode, timeout, retry và DLT.
- [ ] DLT policy phù hợp với subscription type; topic partitioned có DLT name tường minh.
- [ ] Transaction boundary được xác định; DB/Pulsar không bị giả định là một transaction nguyên tử.
- [ ] Lớp tích hợp riêng chỉ chứa policy và contract của ứng dụng.
- [ ] Không reimplement producer factory, listener container hoặc schema/ack lifecycle đã có.
- [ ] Micrometer observation, backlog, retry và DLT được theo dõi.
- [ ] Integration test chạy với Pulsar broker/container và có failure scenarios.

## 18. Tài liệu tham khảo

- [Spring for Apache Pulsar — Project Overview](https://spring.io/projects/spring-pulsar/): mục tiêu, tính năng và compatibility của dự án Spring.
- [Spring Boot Reference — Apache Pulsar Support](https://docs.spring.io/spring-boot/reference/messaging/pulsar.html): starter, auto-configuration, PulsarClient, PulsarTemplate, listener và transaction.
- [Spring for Apache Pulsar — Quick Tour](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/quick-tour.html): ứng dụng Spring Boot publish và consume đầu tiên.
- [Spring for Apache Pulsar — Message Production](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-production.html): PulsarTemplate, send/sendAsync, fluent API, producer customization và schema.
- [Spring for Apache Pulsar — Message Consumption](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html): PulsarListener, subscription, schema, container, ack, retry và DLT.
- [Spring for Apache Pulsar — Transactions](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/transactions.html): PulsarTransactionManager, transactional template/listener và consume-process-produce.
- [Spring for Apache Pulsar — Observability](https://docs.spring.io/spring-pulsar/reference/reference/observability.html): Micrometer observation, metric và trace cho producer/listener.
- [Spring for Apache Pulsar — Testing Applications](https://docs.spring.io/spring-pulsar/reference/reference/testing-applications.html): PulsarConsumerTestUtil và PulsarTestContainerSupport.
- [Spring for Apache Pulsar — Version Compatibility](https://docs.spring.io/spring-pulsar/reference/appendix/version-compatibility.html): ma trận Spring Pulsar, Pulsar Client, Spring Boot và Java.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/spring-cloud-stream-binder-pulsar.html): mô hình function/binding và tích hợp Pulsar qua binder.
- [Apache Pulsar — Spring Integration Project](https://pulsar.apache.org/pulsar-spring/reference/): tài liệu cho project `org.apache.pulsar:pulsar-spring`, phân biệt với Spring-maintained `org.springframework.pulsar` project.
