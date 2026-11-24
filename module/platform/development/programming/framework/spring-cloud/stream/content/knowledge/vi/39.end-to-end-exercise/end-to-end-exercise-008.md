# Bắc cầu Kafka và RabbitMQ với hợp đồng dữ liệu thống nhất

Một hệ thống có thể dùng Kafka làm nơi tiếp nhận sự kiện từ các dịch vụ nghiệp vụ, nhưng dùng RabbitMQ để phân phối công việc tới các nhóm xử lý. Khi xây dựng cầu nối giữa hai broker bằng Spring Cloud Stream, thách thức lớn nhất không phải là đọc một record rồi publish một message. Thách thức là bảo đảm hai phía hiểu **cùng một hợp đồng dữ liệu**, giữ được danh tính và ngữ cảnh của sự kiện, kiểm soát duplicate khi lỗi xảy ra, và vận hành được khi một broker ngừng hoạt động.

Bài thực hành này xây dựng luồng:

~~~text
Order Service
    |
    | Kafka topic: orders.created
    v
Kafka Binder
    |
    | Spring Cloud Stream Function
    v
Bridge: validate + map + preserve event identity
    |
    | RabbitMQ topic exchange: orders.fulfillment
    v
Queue: orders.fulfillment.fulfillment-service
    |
    v
Fulfillment Service
~~~

Ứng dụng bridge nhận sự kiện OrderCreated từ Kafka, kiểm tra hợp đồng, chuyển thành FulfillmentRequested và phát sang RabbitMQ. Cả hai broker dùng một envelope sự kiện thống nhất với event ID, event type, schema version, thời điểm, nguồn, correlation ID và payload có kiểu rõ ràng.

Ví dụ dùng Spring Cloud Stream functional model và hai binder chính thức. Các tên broker, queue, topic, routing key và mã Java là ví dụ có thể điều chỉnh theo hệ thống. Bài học cũng phân tích giới hạn giao nhận: Kafka và RabbitMQ không tham gia cùng một transaction mặc định, vì vậy không được tuyên bố bridge đạt exactly-once chỉ vì function đã trả về thành công.

## 1. Mục tiêu và tiêu chí hoàn thành

Sau bài thực hành, bạn cần có thể:

1. Định nghĩa một event envelope dùng chung cho nhiều broker.
2. Phân biệt event contract với Kafka record key, Kafka headers, Rabbit routing key và AMQP headers.
3. Cấu hình một ứng dụng Spring Cloud Stream có Kafka input binder và Rabbit output binder.
4. Viết Function nhận OrderCreated và tạo FulfillmentRequested.
5. Giữ event ID, causation ID, correlation ID và trace context qua bridge.
6. Ánh xạ destination, consumer group, exchange, queue và routing key rõ ràng.
7. Kiểm tra schema evolution và validation trước khi publish.
8. Giải thích cửa sổ duplicate giữa output publish và Kafka offset commit.
9. Thiết kế inbox/outbox và idempotent consumer khi cần độ tin cậy cao.
10. Kiểm thử end-to-end bằng Kafka và RabbitMQ thật qua Testcontainers.
11. Quan sát lag, retry, publish failure, DLQ và backlog.
12. Xử lý broker outage, restart, replay và rolling deployment theo runbook.

Tiêu chí hoàn thành tối thiểu:

- Một OrderCreated hợp lệ được đọc từ đúng Kafka topic.
- Bridge phát đúng một nội dung FulfillmentRequested theo hợp đồng đã thống nhất trong tình huống bình thường.
- Event identity và correlation context được giữ hoặc ánh xạ theo quy tắc đã công bố.
- RabbitMQ route message tới đúng queue của fulfillment group.
- Payload không hợp lệ đi vào error path có thể quan sát và xử lý.
- Test chứng minh duplicate có thể xảy ra ở ranh giới hai broker và downstream xử lý idempotent.

## 2. Thiết kế hợp đồng sự kiện thống nhất

Không nên để mỗi broker quyết định cấu trúc nghiệp vụ riêng. Kafka và RabbitMQ chỉ là transport; event contract mô tả ý nghĩa dữ liệu mà producer và consumer cùng hiểu.

Một envelope đề xuất:

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| eventId | string | Danh tính duy nhất, ổn định của sự kiện |
| eventType | string | Tên loại sự kiện, ví dụ OrderCreated |
| schemaVersion | integer | Phiên bản schema của payload |
| occurredAt | timestamp UTC | Thời điểm nghiệp vụ xảy ra |
| producer | string | Dịch vụ phát sự kiện |
| correlationId | string | Liên kết các bước trong cùng một nghiệp vụ |
| causationId | string/null | Event đã gây ra event hiện tại |
| traceparent | string/null | W3C trace context nếu có |
| payload | object | Dữ liệu nghiệp vụ có schema riêng |

Ví dụ JSON:

~~~json
{
  "eventId": "9d7a1a3e-6c88-4f8e-ae6c-7b80d8c8d100",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T08:15:30Z",
  "producer": "order-service",
  "correlationId": "checkout-7f13",
  "causationId": null,
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "payload": {
    "orderId": "ORD-1042",
    "customerId": "CUS-882",
    "currency": "VND",
    "totalMinor": 259900,
    "items": [
      {
        "sku": "SKU-CHAIR-01",
        "quantity": 1,
        "unitPriceMinor": 259900
      }
    ]
  }
}
~~~

Dùng số nguyên đơn vị nhỏ nhất cho tiền (ví dụ đồng hoặc cent) giúp tránh sai số số thực. Với hệ thống đa tiền tệ, luôn mang currency. Timestamp nên có timezone và chuẩn hóa UTC. ID nghiệp vụ không nên chứa thông tin nhạy cảm.

### Vì sao envelope cần ổn định?

Nếu producer Kafka gửi một record với header chứa correlation ID nhưng bridge chuyển payload sang RabbitMQ mà quên header, downstream mất ngữ cảnh truy vết. Nếu event ID chỉ tồn tại trong Kafka offset, nó không thể được dùng để deduplicate ở RabbitMQ consumer.

Đưa những trường mang ý nghĩa xuyên hệ thống vào envelope giúp hợp đồng không phụ thuộc broker. Có thể sao chép một số trường sang transport headers để routing/observability nhanh hơn, nhưng payload vẫn phải chứa dữ liệu cần thiết để replay hoặc lưu trữ độc lập.

## 3. Định nghĩa schema đầu vào và đầu ra

OrderCreated mô tả sự kiện đơn hàng được tạo. FulfillmentRequested là yêu cầu gửi tới hệ thống thực hiện đơn hàng.

~~~json
{
  "eventId": "source-event-id",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T08:15:30Z",
  "producer": "order-service",
  "correlationId": "checkout-7f13",
  "causationId": null,
  "traceparent": null,
  "payload": {
    "orderId": "ORD-1042",
    "customerId": "CUS-882",
    "currency": "VND",
    "totalMinor": 259900,
    "items": [
      {
        "sku": "SKU-CHAIR-01",
        "quantity": 1,
        "unitPriceMinor": 259900
      }
    ]
  }
}
~~~

Bridge tạo envelope đầu ra:

~~~json
{
  "eventId": "deterministic-fulfillment-event-id",
  "eventType": "FulfillmentRequested",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T08:15:31Z",
  "producer": "order-fulfillment-bridge",
  "correlationId": "checkout-7f13",
  "causationId": "source-event-id",
  "traceparent": null,
  "payload": {
    "fulfillmentId": "deterministic-id-derived-from-source-event",
    "orderId": "ORD-1042",
    "customerId": "CUS-882",
    "currency": "VND",
    "totalMinor": 259900,
    "items": [
      {
        "sku": "SKU-CHAIR-01",
        "quantity": 1
      }
    ]
  }
}
~~~

Sự kiện đầu ra có eventType và schemaVersion riêng. CausationId trỏ về event đầu vào. EventId đầu ra phải ổn định qua lần xử lý lại cùng một event đầu vào, nếu downstream dùng nó để chống duplicate.

Một quy tắc đơn giản là tạo ID xác định từ source event ID và tên loại sự kiện đầu ra. Không tạo UUID ngẫu nhiên mới ở mỗi lần retry, vì hai lần xử lý cùng một input khi đó sẽ thành hai event khác nhau về mặt identity.

## 4. Quy tắc tương thích schema

Hợp đồng dữ liệu cần được quản lý như API công khai giữa các service.

Các quy tắc thực tế:

- Thêm field mới theo hướng optional hoặc có default an toàn.
- Không đổi ý nghĩa field cũ trong cùng schema version.
- Không đổi tên field bắt buộc mà không có giai đoạn chuyển tiếp.
- Không đổi kiểu dữ liệu từ number sang string hoặc ngược lại tùy tiện.
- Không tái sử dụng eventType cho một ý nghĩa nghiệp vụ khác.
- Consumer phải bỏ qua field chưa biết nếu serializer và contract cho phép.
- Producer chỉ phát schema version mà consumer đã hỗ trợ.
- Với thay đổi phá vỡ tương thích, tạo version mới hoặc event type mới và có migration plan.

Ví dụ thêm trường ghi chú:

~~~json
{
  "orderId": "ORD-1042",
  "customerId": "CUS-882",
  "currency": "VND",
  "totalMinor": 259900,
  "customerNote": null
}
~~~

Consumer cũ có thể bỏ qua customerNote. Nhưng nếu đổi totalMinor thành totalAmount dạng decimal, cần thống nhất cách chuyển đổi, làm tròn và currency trước khi phát schema mới.

Có thể quản lý JSON Schema, Avro hoặc Protobuf trong schema registry. Nếu dùng JSON thông thường, cần có contract tests và kiểm soát version trong repository. Chỉ ghi schemaVersion vào envelope mà không kiểm tra nội dung schema thì chưa đủ.

## 5. Phân biệt payload, Kafka key và transport headers

Các thành phần này giải quyết vấn đề khác nhau:

| Thành phần | Dùng cho | Có phải event contract không? |
|---|---|---|
| Envelope payload | Ý nghĩa nghiệp vụ và identity | Có |
| Kafka record key | Partitioning và ordering theo key | Không |
| Kafka headers | Metadata transport bổ sung | Không |
| Rabbit routing key | Định tuyến vào queue | Không |
| AMQP headers | Metadata transport và header exchange | Không |
| Pulsar message key | Phân phối theo key | Không |

Ví dụ Kafka key có thể là orderId để các event cùng đơn hàng vào cùng partition. Rabbit routing key có thể là fulfillment.requested để route vào queue của nhóm fulfillment. Hai giá trị này không nên được coi là eventType hoặc eventId.

Nếu bridge thay đổi Kafka key thành Rabbit routing key, phải có quy tắc ánh xạ được tài liệu hóa. Không tự động sao chép mọi header transport vì có thể mang thuộc tính riêng broker như delivery tag, offset, partition hoặc header nội bộ.

## 6. Cấu trúc ứng dụng bridge

Một cấu trúc package dễ bảo trì:

~~~text
order-fulfillment-bridge/
  src/main/java/com/example/bridge/
    BridgeApplication.java
    config/
      BridgeFunctionConfiguration.java
    contract/
      EventEnvelope.java
      OrderCreated.java
      FulfillmentRequested.java
      OrderItem.java
    mapping/
      FulfillmentMapper.java
    validation/
      OrderCreatedValidator.java
    messaging/
      BridgeHeaders.java
      BridgeFailureHandler.java
    reliability/
      InboxService.java
      OutboxService.java
      OutboxPublisher.java
  src/main/resources/
    application.yml
  src/test/java/com/example/bridge/
    FulfillmentMapperTest.java
    BridgeContractTest.java
    KafkaRabbitBridgeIT.java
~~~

Tách contract khỏi binder config để có thể test mapping mà không cần broker. Tách validation khỏi mapping để lỗi schema và lỗi nghiệp vụ có thể được phân loại riêng. Phần reliability chỉ cần thiết khi yêu cầu giao nhận vượt quá khả năng của bridge trực tiếp.

## 7. Dependency cho Kafka và RabbitMQ Binder

Với Maven, thêm Spring Cloud Stream và hai binder tương ứng. Các phiên bản nên được quản lý bằng Spring Cloud BOM tương thích với Spring Boot của dự án.

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2025.1.3</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-stream-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-stream-rabbit</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Ví dụ này dùng Spring Cloud 2025.1.3, tương thích với Spring Boot 4.0.x và 4.1.x. Nếu dự án đang dùng Spring Boot 3.5.x, hãy chọn release train 2025.0.x tương ứng; luôn kiểm tra compatibility matrix trước khi nâng cấp. Không tự khai báo phiên bản Kafka client hoặc Spring AMQP khác với dependency management nếu chưa có lý do.

Hai binder nằm cùng classpath. Vì vậy, cấu hình mỗi binding phải chỉ rõ binder để tránh output vô tình đi vào Kafka hoặc input vô tình dùng Rabbit.

## 8. Cấu hình hai binder trong application.yml

Ví dụ cấu hình local:

~~~yaml
spring:
  application:
    name: order-fulfillment-bridge
  cloud:
    function:
      definition: bridgeOrder
    stream:
      default-binder: kafka
      bindings:
        bridgeOrder-in-0:
          destination: orders.created
          group: order-fulfillment-bridge
          binder: kafka
          content-type: application/json
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 5000
            back-off-multiplier: 2.0
        bridgeOrder-out-0:
          destination: orders.fulfillment
          binder: rabbit
          content-type: application/json
          producer:
            required-groups:
              - fulfillment-service
      kafka:
        binder:
          brokers: localhost:9092
      rabbit:
        bindings:
          bridgeOrder-out-0:
            producer:
              routing-key: fulfillment.requested
              binding-routing-key: fulfillment.requested
              exchange-type: topic

  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Các ý nghĩa quan trọng:

- bridgeOrder là tên bean Function.
- bridgeOrder-in-0 là Kafka input.
- bridgeOrder-out-0 là Rabbit output.
- order-fulfillment-bridge là Kafka consumer group ổn định.
- orders.created là Kafka topic.
- orders.fulfillment là Rabbit exchange destination.
- fulfillment.requested là routing key.
- required-groups yêu cầu binder chuẩn bị queue/binding cho nhóm downstream theo semantics của Rabbit binder.

Trong môi trường production, thay endpoint và credential bằng secret/config bên ngoài. Không dùng guest/guest hoặc localhost. Nếu dùng TLS/SASL, cấu hình riêng cho Kafka binder và Rabbit connection factory.

## 9. Mô hình dữ liệu Java

Tạo các record biểu diễn hợp đồng:

~~~java
import java.time.Instant;
import java.util.List;

public record EventEnvelope<T>(
    String eventId,
    String eventType,
    int schemaVersion,
    Instant occurredAt,
    String producer,
    String correlationId,
    String causationId,
    String traceparent,
    T payload
) {
}

public record OrderItem(
    String sku,
    int quantity,
    long unitPriceMinor
) {
}

public record OrderCreated(
    String orderId,
    String customerId,
    String currency,
    long totalMinor,
    List<OrderItem> items
) {
}

public record FulfillmentItem(
    String sku,
    int quantity
) {
}

public record FulfillmentRequested(
    String fulfillmentId,
    String orderId,
    String customerId,
    String currency,
    long totalMinor,
    List<FulfillmentItem> items
) {
}
~~~

Các record chỉ mô tả payload. Validation sẽ kiểm tra null, empty, giá trị âm, currency và số lượng trước khi bridge publish.

Dùng Instant để biểu diễn thời điểm UTC. Nếu hợp đồng cần lưu timezone nghiệp vụ gốc, có thể thêm field riêng; không để mỗi service tự diễn giải timestamp theo timezone máy chạy.

## 10. Validation trước khi chuyển đổi

Không publish message downstream nếu input không đủ điều kiện. Ví dụ validator:

~~~java
import java.util.Objects;

public final class OrderCreatedValidator {

    public void validate(EventEnvelope<OrderCreated> envelope) {
        if (envelope == null) {
            throw new InvalidOrderEventException("Envelope is required");
        }
        if (isBlank(envelope.eventId())) {
            throw new InvalidOrderEventException("eventId is required");
        }
        if (!"OrderCreated".equals(envelope.eventType())) {
            throw new InvalidOrderEventException("Unexpected eventType");
        }
        if (envelope.schemaVersion() != 1) {
            throw new UnsupportedSchemaVersionException(
                "Unsupported OrderCreated schemaVersion"
            );
        }

        OrderCreated payload = envelope.payload();
        if (payload == null || isBlank(payload.orderId())) {
            throw new InvalidOrderEventException("orderId is required");
        }
        if (isBlank(payload.customerId()) || isBlank(payload.currency())) {
            throw new InvalidOrderEventException(
                "customerId and currency are required"
            );
        }
        if (payload.totalMinor() < 0) {
            throw new InvalidOrderEventException("totalMinor cannot be negative");
        }
        if (payload.items() == null || payload.items().isEmpty()) {
            throw new InvalidOrderEventException("At least one item is required");
        }

        for (OrderItem item : payload.items()) {
            if (item == null || isBlank(item.sku())
                    || item.quantity() <= 0
                    || item.unitPriceMinor() < 0) {
                throw new InvalidOrderEventException("Invalid order item");
            }
        }
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

Exception types là class ứng dụng tự định nghĩa. Phân biệt lỗi dữ liệu vĩnh viễn (schema sai, thiếu ID) với lỗi tạm thời (database unavailable, broker timeout). Retry liên tục một payload sai không làm nó hợp lệ; loại lỗi này cần error channel/DLQ và quy trình sửa dữ liệu.

## 11. Mapping và event identity ổn định

Mapper chuyển payload nguồn sang payload đích. ID đầu ra được tạo xác định từ source event ID:

~~~java
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.util.UUID;

public final class FulfillmentMapper {

    private final Clock clock;

    public FulfillmentMapper(Clock clock) {
        this.clock = clock;
    }

    public EventEnvelope<FulfillmentRequested> map(
            EventEnvelope<OrderCreated> source) {

        OrderCreated order = source.payload();

        String outputId = UUID.nameUUIDFromBytes(
            ("FulfillmentRequested:v1:" + source.eventId())
                .getBytes(StandardCharsets.UTF_8)
        ).toString();

        var items = order.items().stream()
            .map(item -> new FulfillmentItem(item.sku(), item.quantity()))
            .toList();

        var payload = new FulfillmentRequested(
            outputId,
            order.orderId(),
            order.customerId(),
            order.currency(),
            order.totalMinor(),
            items
        );

        return new EventEnvelope<>(
            outputId,
            "FulfillmentRequested",
            1,
            clock.instant(),
            "order-fulfillment-bridge",
            source.correlationId(),
            source.eventId(),
            source.traceparent(),
            payload
        );
    }
}
~~~

UUID.nameUUIDFromBytes tạo ID xác định từ cùng chuỗi input. Đây là UUID dạng name-based; nếu hệ thống yêu cầu UUIDv5 theo namespace cụ thể, dùng implementation UUIDv5 chuẩn thay vì tự coi UUID mặc định là UUIDv5.

Định danh đầu ra gồm loại event và phiên bản mapping. Nếu logic mapping thay đổi theo cách tạo ra một sự kiện nghiệp vụ khác, cần cân nhắc tăng version hoặc thay idempotency key. Không thay ID một cách ngẫu nhiên mỗi lần Kafka giao lại input.

## 12. Function nhận Kafka message và tạo Rabbit message

Function dùng Spring Message để đọc payload và giữ metadata cần thiết:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
public class BridgeFunctionConfiguration {

    @Bean
    OrderCreatedValidator orderCreatedValidator() {
        return new OrderCreatedValidator();
    }

    @Bean
    FulfillmentMapper fulfillmentMapper() {
        return new FulfillmentMapper(java.time.Clock.systemUTC());
    }

    @Bean
    Function<Message<EventEnvelope<OrderCreated>>,
             Message<EventEnvelope<FulfillmentRequested>>> bridgeOrder(
            OrderCreatedValidator validator,
            FulfillmentMapper mapper) {

        return input -> {
            EventEnvelope<OrderCreated> source = input.getPayload();
            validator.validate(source);

            EventEnvelope<FulfillmentRequested> output = mapper.map(source);

            return MessageBuilder.fromMessage(input)
                .setPayload(output)
                .setHeader("event_id", output.eventId())
                .setHeader("event_type", output.eventType())
                .setHeader("correlation_id", output.correlationId())
                .setHeader("causation_id", output.causationId())
                .build();
        };
    }
}
~~~

MessageBuilder.fromMessage giữ lại các header được phép chuyển tiếp. Cần kiểm soát header nào là transport-specific và header nào thuộc hợp đồng. Không sao chép delivery tag, Kafka offset, partition metadata hoặc Rabbit delivery metadata sang broker đích như thể chúng có cùng ý nghĩa.

Event envelope là nguồn dữ liệu chính cho eventId, eventType và correlationId. Header được sao chép để quan sát hoặc routing; downstream vẫn phải có thể xử lý payload độc lập.

Nếu dùng tracing instrumentation, để Micrometer Tracing/OpenTelemetry quản lý trace context theo phiên bản Spring Boot. Không tự tạo traceparent giả hoặc ghi đè trace ID hiện có.

## 13. Kiểm tra binding name và destination

Với function bridgeOrder:

| Hướng | Binding name | Binder | Destination |
|---|---|---|---|
| Input | bridgeOrder-in-0 | Kafka | orders.created |
| Output | bridgeOrder-out-0 | RabbitMQ | orders.fulfillment |

Một lỗi phổ biến là cấu hình output bằng bridgeOrder-out nhưng function thực tế tạo bridgeOrder-out-0. Khi đó output binding mong muốn không được áp dụng.

Nếu function được đổi tên, binding name mặc định cũng đổi. Khi dùng alias qua spring.cloud.stream.function.bindings, cần cập nhật các extended binder properties theo tên binding đã ánh xạ.

Không chỉ kiểm tra YAML. Dùng startup logs và Actuator bindings để xác nhận binding nào đã được tạo, binder nào được chọn và state là STARTED.

## 14. Kafka topic và key cho sự kiện đơn hàng

Kafka producer nguồn nên chọn key theo orderId để các sự kiện cùng đơn hàng có thể vào cùng partition:

~~~text
Kafka topic: orders.created
Record key:  ORD-1042
Value:       EventEnvelope<OrderCreated>
Headers:     event_id, event_type, correlation_id
~~~

Nếu upstream producer là Spring Cloud Stream, có thể cấu hình partition key expression theo payload hoặc dùng KafkaTemplate/ProducerRecord. Cách cụ thể phụ thuộc producer. Điều quan trọng là key được chọn ổn định và tất cả producer tuân thủ cùng quy tắc.

Bridge không tự động đổi partition key thành Rabbit routing key. Kafka partition giữ ordering trong phạm vi partition; RabbitMQ queue có semantics khác. Nếu cần thứ tự theo orderId downstream, phải thiết kế queue sharding hoặc serialization theo orderId.

Kiểm tra topic có đủ partition, retention, ACL và replication phù hợp. Bridge consumer group cần quyền read topic và commit offsets.

## 15. Rabbit exchange, queue và routing key

Rabbit Binder dùng destination làm exchange name. Với group có tên, binder thường tạo queue theo quy ước destination.group và bind queue vào exchange.

Ví dụ:

~~~text
Exchange: orders.fulfillment
Type:     topic
Queue:    orders.fulfillment.fulfillment-service
Key:      fulfillment.requested
~~~

Downstream consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: receiveFulfillment
    stream:
      bindings:
        receiveFulfillment-in-0:
          destination: orders.fulfillment
          group: fulfillment-service
          binder: rabbit
          content-type: application/json
      rabbit:
        bindings:
          receiveFulfillment-in-0:
            consumer:
              binding-routing-key: fulfillment.requested
~~~

Producer output dùng cùng exchange và routing key. Khi output binding khai báo required-groups, Rabbit Binder có thể provision queue và binding cho từng group trước khi consumer khởi động. Thuộc tính producer binding-routing-key xác định key dùng để bind các queue được tạo theo required-groups; nếu không khai báo, mặc định là #. Vì vậy, ví dụ này đặt producer binding-routing-key cùng giá trị fulfillment.requested với routing-key. Consumer binding-routing-key cũng phải tương thích với topology đó. Nếu queue đã được provision bên ngoài, cấu hình binder phải khớp queue name, exchange declaration và binding policy. Không mặc định một queue cùng tên group là queue mà binder sẽ chọn nếu queueNameGroupOnly chưa bật.

Group có tên giúp queue durable theo semantics binder; anonymous queue có thể auto-delete và không phù hợp để giữ backlog qua thời gian consumer dừng.

## 16. Producer routing key và consumer binding key

RabbitMQ topic exchange đối chiếu routing key của message với binding key của queue:

- routing key producer: fulfillment.requested
- binding key consumer: fulfillment.requested hoặc pattern phù hợp
- exchange: orders.fulfillment

Với exact key, queue nhận đúng loại message. Nếu muốn queue nhận mọi event fulfillment, có thể dùng pattern như fulfillment.# nhưng cần đánh giá phạm vi dữ liệu được route.

Không dùng wildcard rộng như # nếu queue chỉ nên nhận một event type. Một key quá rộng có thể đưa message không mong muốn vào consumer, làm tăng lỗi deserialize hoặc gây xử lý nhầm nghiệp vụ.

Khi queue được provision bởi producer binding thông qua required-groups, producer-side binding-routing-key là thuộc tính riêng để tạo binding cho queue đó. Nó không phải routingKey của message. Một binding key rộng ở queue có thể làm message được route rộng hơn dự định dù producer đã dùng routing key cụ thể; hãy đối chiếu cả hai phía.

Producer confirm và message routing là hai điều khác nhau. Broker có thể xác nhận publish nhưng không có queue nào matching key. Cần cấu hình/quan sát publisher returns hoặc alternate exchange theo yêu cầu, và xác minh queue binding thực tế.

## 17. Content type và JSON conversion

Cả input và output binding khai báo:

~~~yaml
content-type: application/json
~~~

Spring Cloud Stream sử dụng message conversion để chuyển bytes JSON thành kiểu Java và ngược lại. Tuy nhiên, content-type chỉ là một phần hợp đồng:

- Producer phải serialize đúng JSON schema.
- Consumer phải khai báo kiểu payload tương thích.
- Header content type phải đúng.
- Native encoding/decoding không được bật ngoài dự kiến.
- Schema version phải được kiểm tra ở tầng ứng dụng hoặc schema registry.
- Unknown fields và null fields phải có policy rõ ràng.

Nếu upstream dùng Avro nhưng bridge chờ JSON, binder có thể nhận bytes nhưng không tạo được record Java. Không đổi destination để chữa lỗi serialization.

Với generic EventEnvelope<T>, kiểm tra converter của Spring Cloud Stream và Jackson có đủ thông tin kiểu payload trong phiên bản đang dùng. Nếu type erasure hoặc converter không suy ra payload generic, dùng DTO cụ thể hoặc custom converter có test.

## 18. Headers và trace context qua hai broker

Một số metadata nên có mặt ở cả envelope và transport header:

| Metadata | Trong envelope | Header transport |
|---|---|---|
| eventId | Bắt buộc | Nên có |
| eventType | Bắt buộc | Nên có |
| schemaVersion | Bắt buộc | Tùy nhu cầu |
| correlationId | Bắt buộc nếu có workflow | Nên có |
| causationId | Bắt buộc với event dẫn xuất | Nên có |
| traceparent | Tùy tracing policy | Nên propagate |
| Kafka offset/partition | Không | Chỉ log/telemetry nguồn |
| Rabbit deliveryTag | Không | Chỉ metadata xử lý Rabbit |

Không đưa transport metadata vào payload nếu nó không có ý nghĩa nghiệp vụ xuyên broker. Ví dụ Kafka partition 2 không có nghĩa Rabbit queue partition 2.

Khi bridge tạo event mới, causationId nên trỏ event nguồn. CorrelationId giữ workflow ban đầu. Trace context nên được tiếp tục theo tracing instrumentation hoặc được inject theo chuẩn W3C.

## 19. Reliability của bridge trực tiếp: at-least-once và duplicate window

Đường đi đơn giản:

1. Kafka giao OrderCreated cho bridge.
2. Function validate và map.
3. Rabbit Binder publish FulfillmentRequested.
4. Kafka consumer hoàn tất xử lý và offset được commit theo ack/transaction policy.

Có một cửa sổ lỗi:

~~~mermaid
sequenceDiagram
    participant K as Kafka
    participant B as Bridge
    participant R as RabbitMQ

    K->>B: Deliver event E
    B->>R: Publish output E2
    R-->>B: Broker accepts publish
    Note over B: Process crashes before Kafka offset commit
    K->>B: Redeliver event E
    B->>R: Publish E2 again
    R-->>B: Broker accepts duplicate
~~~

Nếu output đã publish nhưng input offset chưa commit, Kafka có thể giao lại input. Bridge sẽ publish output lần nữa. Đây là duplicate hợp lệ trong at-least-once processing.

Ngược lại, nếu input offset được commit trước khi output được lưu bền vững, process crash có thể làm mất output. Vì thế cần hiểu ack mode, transaction và publisher confirm của phiên bản binder đang dùng.

**Không có transaction mặc định bao trùm Kafka offset và Rabbit publish.** Kafka transaction không tự enlist RabbitMQ. Rabbit publisher confirm cũng không commit Kafka offset.

## 20. Idempotency ở downstream

Vì duplicate có thể xảy ra, Fulfillment Service cần deduplicate theo eventId hoặc idempotency key.

Ví dụ bảng inbox:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(80) PRIMARY KEY,
    event_type VARCHAR(120) NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
~~~

Xử lý trong transaction:

~~~java
@Transactional
public void handle(FulfillmentRequestedEvent event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(
        event.eventId(),
        event.eventType()
    );

    if (!firstDelivery) {
        return;
    }

    fulfillmentRepository.createIfAbsent(
        event.payload().fulfillmentId(),
        event.payload()
    );
}
~~~

insertIfAbsent cần được triển khai bằng unique constraint/upsert của database. Không làm kiểu SELECT rồi INSERT mà không có unique constraint, vì hai consumer đồng thời có thể cùng vượt qua bước SELECT.

Nếu xử lý side effect ngoài database (gọi hãng vận chuyển, gửi email), cần truyền idempotency key xuống hệ thống ngoài hoặc lưu trạng thái gửi và xử lý retry có kiểm soát.

## 21. Khi nào cần inbox/outbox ở bridge?

Với luồng quan trọng, bridge trực tiếp có thể chưa đủ khả năng phục hồi. Một kiến trúc bền vững hơn:

~~~mermaid
flowchart TD
    K[Kafka orders.created] --> C[Bridge consumer]
    C --> T[DB transaction]
    T --> I[Inbox: unique source event ID]
    T --> O[Outbox: mapped output event]
    O --> P[Outbox publisher]
    P --> R[RabbitMQ exchange]
    R --> Q[Fulfillment queue]
    Q --> D[Downstream inbox/idempotency]
~~~

Trong một database transaction:

1. Ghi source event vào inbox với unique eventId.
2. Nếu đã tồn tại, không tạo output row lần nữa.
3. Map thành FulfillmentRequested với ID xác định.
4. Ghi output vào outbox.
5. Commit database transaction.
6. Chỉ sau khi function hoàn tất thành công, Kafka binder mới được phép ack/commit input theo cấu hình đã chọn.

Nếu process crash sau DB commit nhưng trước Kafka offset commit, Kafka giao lại event. Unique inbox nhận ra duplicate và không tạo outbox thứ hai. Đây là lý do transaction DB phải commit trước khi handler trả về và offset được xác nhận.

Outbox publisher gửi message RabbitMQ rồi đánh dấu sent sau khi nhận kết quả xác nhận theo chính sách publisher confirm. Nếu crash sau publish nhưng trước khi đánh dấu sent, outbox relay có thể publish lại. Downstream vẫn phải idempotent.

Outbox không tự cung cấp exactly-once xuyên database và RabbitMQ. Nó tạo một chuỗi giao nhận bền vững, có thể retry và deduplicate.

## 22. Schema inbox/outbox tham khảo

~~~sql
CREATE TABLE bridge_inbox (
    source_event_id VARCHAR(80) PRIMARY KEY,
    source_event_type VARCHAR(120) NOT NULL,
    received_at TIMESTAMP NOT NULL
);

CREATE TABLE bridge_outbox (
    event_id VARCHAR(80) PRIMARY KEY,
    event_type VARCHAR(120) NOT NULL,
    schema_version INTEGER NOT NULL,
    destination VARCHAR(200) NOT NULL,
    routing_key VARCHAR(200) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error VARCHAR(1000) NULL
);
~~~

Tên kiểu JSON phụ thuộc database (PostgreSQL JSONB, MySQL JSON hoặc kiểu text có validation). Có thể thêm trạng thái PENDING, IN_FLIGHT, SENT, FAILED, next_attempt_at và lock owner để nhiều relay worker không gửi cùng row một cách vô kiểm soát.

Cần index cho các row chưa publish, giới hạn batch size và dùng lease/locking có thời hạn. Nếu worker chết trong khi giữ lock, row phải có thể được reclaim sau timeout.

## 23. Retry và phân loại lỗi

Không phải lỗi nào cũng nên retry giống nhau.

| Lỗi | Phân loại | Hành động |
|---|---|---|
| Kafka broker timeout | Tạm thời | Retry có backoff |
| Rabbit connection reset | Tạm thời | Reconnect và retry publish |
| Rabbit unroutable message | Cấu hình/topology | Return/alert, không retry vô hạn |
| JSON sai cú pháp | Dữ liệu vĩnh viễn | Error/DLQ và điều tra producer |
| schemaVersion không hỗ trợ | Contract mismatch | Quarantine, phối hợp version |
| thiếu orderId | Validation | DLQ hoặc error store |
| DB deadlock | Tạm thời | Retry transaction giới hạn |
| ACL/authentication denied | Cấu hình/bảo mật | Fail nhanh, cảnh báo |
| quota/resource limit | Hạ tầng | Backoff có giới hạn và alert |

Retry không nên giữ consumer thread vô hạn. Đặt số lần thử, backoff, timeout và giới hạn tổng thời gian. Khi đã hết retry, lưu payload và metadata cần thiết vào error path/DLQ có kiểm soát.

Đừng gửi lại message lỗi bằng một eventId mới để né deduplication. Event identity phải ổn định qua retry.

## 24. Kafka input: group, partition và offset

Bridge cần group ổn định, ví dụ order-fulfillment-bridge. Các replica cùng service dùng chung group để chia partition. Không dùng cùng group với service khác nếu mỗi service cần nhận toàn bộ event.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        bridgeOrder-in-0:
          destination: orders.created
          group: order-fulfillment-bridge
          consumer:
            concurrency: 3
~~~

Concurrency phải phù hợp partition count và năng lực downstream. Nếu topic có 2 partition, tăng concurrency lên 10 không tạo thêm parallelism hữu ích cho cùng group.

Kafka key orderId giúp các event cùng đơn hàng thường vào cùng partition, giữ thứ tự trong partition. Tuy nhiên, RabbitMQ downstream không tự bảo toàn thứ tự đó nếu có nhiều consumer hoặc nhiều queue. Nếu nghiệp vụ phụ thuộc thứ tự, cần thiết kế sharding/serial processing ở phía Rabbit consumer.

Offset commit policy phải được kiểm tra cùng retry và transaction. Khi replay, duplicate có thể xảy ra; không dùng reset offset như công cụ chữa lỗi bridge thông thường.

## 25. Rabbit output: durability, confirms và unroutable messages

Để Rabbit output tồn tại qua broker restart, cần topology bền vững và message delivery mode phù hợp. Rabbit Binder có các thuộc tính producer/consumer riêng; kiểm tra version docs trước khi đặt durable, queue type, TTL, DLX hoặc delivery mode.

Một số thiết lập nền tảng Spring Boot:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Các thuộc tính trên bật cơ chế confirms/returns của Spring AMQP connection factory theo phiên bản Spring Boot. Với Rabbit Binder, có thể cấu hình producer property confirmAckChannel hoặc useConfirmHeader (hai thuộc tính loại trừ lẫn nhau) để nhận publisher confirmation; connection factory phải bật confirms và ứng dụng phải xử lý kết quả đó. Nếu dùng errorChannelEnabled, confirmAckChannel có thể chuyển positive acknowledgement tới channel đã đăng ký. **Publisher confirm xác nhận broker nhận publish, không bảo đảm message được route tới queue mong muốn.** Cần theo dõi returned message hoặc alternate exchange cho trường hợp unroutable.

Nếu không có queue nào matching routing key, mandatory return hoặc alternate exchange cần được cấu hình và quan sát. Không đánh dấu outbox row SENT chỉ vì lời gọi gửi message không ném exception nếu hợp đồng yêu cầu broker confirm.

## 26. DLQ và error path cho hai phía

Có hai loại lỗi độc lập:

- Kafka input không thể deserialize hoặc handler bridge thất bại.
- Rabbit output publish lỗi hoặc không route được.

Không gom chúng thành một DLQ duy nhất mà không phân loại source và stage. Metadata error nên có:

~~~json
{
  "sourceEventId": "source-event-id",
  "stage": "RABBIT_PUBLISH",
  "errorCode": "UNROUTABLE",
  "attempt": 3,
  "failedAt": "2026-11-24T08:20:00Z",
  "destination": "orders.fulfillment",
  "routingKey": "fulfillment.requested"
}
~~~

Không lưu password, token, private key hoặc dữ liệu cá nhân không cần thiết vào error record. Payload có thể chứa PII; áp dụng retention và access policy cho DLQ.

Replay cần giữ eventId đầu ra xác định. Nếu sửa mapping logic, cần ghi rõ replay dùng mapping version nào để không biến một event cũ thành một nội dung khác mà không có audit.

## 27. Consumer downstream của RabbitMQ

Fulfillment Service nhận event:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FulfillmentConsumerConfiguration {

    @Bean
    Consumer<EventEnvelope<FulfillmentRequested>> receiveFulfillment(
            FulfillmentService service) {
        return service::handle;
    }
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: receiveFulfillment
    stream:
      bindings:
        receiveFulfillment-in-0:
          destination: orders.fulfillment
          group: fulfillment-service
          binder: rabbit
          content-type: application/json
      rabbit:
        bindings:
          receiveFulfillment-in-0:
            consumer:
              binding-routing-key: fulfillment.requested
~~~

Rabbit Binder thường tạo queue từ destination và group. Nếu có queue do IaC provision sẵn, cấu hình queueNameGroupOnly/bindQueue/declareExchange phải phù hợp. Đừng giả định tên queue chỉ là group.

Downstream phải ghi inbox/idempotency key trước side effect. Nếu nhận duplicate, trả thành công sau khi xác minh event đã được xử lý, để broker có thể ack message.

## 28. Ordering và parallelism xuyên hai broker

Kafka bảo đảm thứ tự trong một partition. RabbitMQ queue có thứ tự enqueue nhưng với nhiều consumer, prefetch và xử lý song song, thứ tự hoàn tất nghiệp vụ có thể khác thứ tự nhận.

Ví dụ:

~~~text
Kafka partition 0:
  OrderCreated A
  OrderUpdated A
  OrderCancelled A

Bridge publish:
  Rabbit queue:
    A-created
    A-updated
    A-cancelled
~~~

Nếu Rabbit consumer có concurrency 3, A-cancelled có thể hoàn tất trước A-created. Nếu nghiệp vụ cần thứ tự theo orderId:

- Dùng key/shard ổn định.
- Route các event cùng orderId tới cùng queue/partition.
- Đảm bảo một consumer xử lý tuần tự trên shard đó hoặc dùng sequence/version check.
- Dùng optimistic locking hoặc aggregate version ở database.
- Từ chối/hoãn event đến sai thứ tự và có cơ chế replay.

Không giả định routing key đơn thuần tạo ordering nếu exchange route cùng key tới một queue nhưng consumer concurrency lớn hơn một.

## 29. Security và quyền truy cập

Bridge cần quyền khác nhau ở hai broker:

| Thành phần | Quyền tối thiểu gợi ý |
|---|---|
| Kafka bridge principal | Read topic orders.created, join group order-fulfillment-bridge, commit offset |
| Rabbit bridge principal | Write exchange orders.fulfillment và quyền liên quan confirm/return |
| Rabbit fulfillment principal | Read queue fulfillment group, ack/reject |
| Platform provisioner | Tạo topic/exchange/queue/binding theo phạm vi |

Dùng TLS ở cả hai broker. Kafka có thể dùng SASL/SCRAM hoặc mTLS. RabbitMQ dùng TLS và user riêng theo vhost. Không dùng credential production trong application.yml commit vào Git.

Nếu binder tự provision, cần quyền create/describe. Nếu hạ tầng tạo trước, có thể dùng verify-only và giảm quyền runtime. Không cấp quyền admin cluster cho bridge chỉ để tránh lỗi provisioning.

## 30. Observability end-to-end

Mỗi log/trace nên giúp trả lời:

- Event ID nguồn là gì?
- Event ID đầu ra là gì?
- Correlation ID nào?
- Bridge đang ở stage nào?
- Kafka topic/partition/offset nguồn nào?
- Rabbit exchange/routing key nào?
- Publish được confirm hay return?
- Số lần retry và lỗi cuối cùng là gì?

Các metric nên có:

| Metric | Ý nghĩa |
|---|---|
| bridge_events_received_total | Số event đọc từ Kafka |
| bridge_events_validated_total | Số event hợp lệ |
| bridge_events_rejected_total | Event sai contract |
| bridge_publish_success_total | Publish Rabbit thành công theo tiêu chí xác nhận |
| bridge_publish_failure_total | Publish thất bại |
| bridge_unroutable_total | Rabbit message không route |
| bridge_processing_duration | Độ trễ xử lý bridge |
| kafka_consumer_lag | Khả năng theo kịp Kafka |
| bridge_outbox_pending | Số row chưa publish |
| bridge_outbox_oldest_age | Tuổi row pending lâu nhất |
| fulfillment_duplicate_total | Số duplicate bị idempotency loại |

Không đưa eventId, orderId hoặc customerId làm metric label không giới hạn vì cardinality sẽ tăng rất nhanh. Các ID phù hợp cho structured logs/traces; metrics nên dùng binder, destination, errorCode và environment.

## 31. Unit test cho mapper và contract

Test mapping không cần broker:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import org.junit.jupiter.api.Test;

class FulfillmentMapperTest {

    @Test
    void mapsOrderAndKeepsCausationAndCorrelation() {
        Clock clock = Clock.fixed(
            Instant.parse("2026-11-24T08:15:31Z"),
            ZoneOffset.UTC
        );

        FulfillmentMapper mapper = new FulfillmentMapper(clock);

        var order = new OrderCreated(
            "ORD-1042",
            "CUS-882",
            "VND",
            259900,
            List.of(new OrderItem("SKU-CHAIR-01", 1, 259900))
        );

        var source = new EventEnvelope<>(
            "source-event-1042",
            "OrderCreated",
            1,
            Instant.parse("2026-11-24T08:15:30Z"),
            "order-service",
            "checkout-7f13",
            null,
            null,
            order
        );

        var output = mapper.map(source);

        assertThat(output.eventType()).isEqualTo("FulfillmentRequested");
        assertThat(output.schemaVersion()).isEqualTo(1);
        assertThat(output.causationId()).isEqualTo(source.eventId());
        assertThat(output.correlationId()).isEqualTo(source.correlationId());
        assertThat(output.eventId()).isEqualTo(
            mapper.map(source).eventId()
        );
        assertThat(output.payload().orderId()).isEqualTo("ORD-1042");
    }
}
~~~

Ngoài test happy path, cần test null payload, thiếu eventId, schema version không hỗ trợ, total âm, item quantity bằng 0 và danh sách item rỗng.

## 32. Contract test cho JSON

Serialize envelope và kiểm tra field bắt buộc:

~~~java
@Test
void serializesStableEventContract() throws Exception {
    String json = objectMapper.writeValueAsString(envelope);

    JsonNode root = objectMapper.readTree(json);

    assertThat(root.path("eventId").asText()).isNotBlank();
    assertThat(root.path("eventType").asText())
        .isEqualTo("OrderCreated");
    assertThat(root.path("schemaVersion").asInt()).isEqualTo(1);
    assertThat(root.path("payload").path("orderId").asText())
        .isEqualTo("ORD-1042");
}
~~~

Nên giữ các JSON fixture đại diện cho từng schema version để kiểm tra consumer mới đọc được event cũ. Khi producer thêm field optional, test backward compatibility. Khi thay đổi phá vỡ schema, test phải xác minh version routing hoặc migration strategy.

## 33. Integration test với Kafka và RabbitMQ thật

Dùng Testcontainers để khởi động hai broker trong cùng test. Với Testcontainers 2.x, các module tương ứng là kafka và rabbitmq; import/package có thể khác ở Testcontainers 1.x. Dùng BOM/version đồng nhất với dependency management của dự án.

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-kafka</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-rabbitmq</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ví dụ test setup:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.rabbitmq.RabbitMQContainer;
import org.testcontainers.utility.DockerImageName;

import java.nio.charset.StandardCharsets;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class KafkaRabbitBridgeIT {

    @Container
    static final KafkaContainer kafka =
        new KafkaContainer(DockerImageName.parse("apache/kafka-native:3.8.0"));

    @Container
    static final RabbitMQContainer rabbit =
        new RabbitMQContainer(DockerImageName.parse("rabbitmq:4.0-management"));

    @Autowired
    RabbitTemplate rabbitTemplate;

    @DynamicPropertySource
    static void brokerProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.cloud.stream.kafka.binder.brokers",
            kafka::getBootstrapServers
        );
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        registry.add("spring.rabbitmq.username", rabbit::getAdminUsername);
        registry.add("spring.rabbitmq.password", rabbit::getAdminPassword);
    }

    @Test
    void forwardsOrderCreatedToRabbitFulfillmentQueue() throws Exception {
        String json = """
            {
              "eventId": "source-event-1042",
              "eventType": "OrderCreated",
              "schemaVersion": 1,
              "occurredAt": "2026-11-24T08:15:30Z",
              "producer": "order-service",
              "correlationId": "checkout-7f13",
              "causationId": null,
              "traceparent": null,
              "payload": {
                "orderId": "ORD-1042",
                "customerId": "CUS-882",
                "currency": "VND",
                "totalMinor": 259900,
                "items": [
                  {"sku": "SKU-CHAIR-01", "quantity": 1, "unitPriceMinor": 259900}
                ]
              }
            }
            """;

        Properties properties = new Properties();
        properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            kafka.getBootstrapServers()
        );
        properties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        properties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );

        try (Producer<String, String> producer = new KafkaProducer<>(properties)) {
            producer.send(
                new ProducerRecord<>("orders.created", "ORD-1042", json)
            ).get(10, TimeUnit.SECONDS);
        }

        Message message = rabbitTemplate.receive(
            "orders.fulfillment.fulfillment-service",
            10_000
        );
        assertThat(message).isNotNull();

        String output = new String(message.getBody(), StandardCharsets.UTF_8);
        assertThat(output).contains("FulfillmentRequested");
        assertThat(output).contains("source-event-1042");
        assertThat(output).contains("checkout-7f13");
        assertThat(output).contains("ORD-1042");
    }
}
~~~

Ví dụ dùng Kafka Producer gửi JSON string với key orderId, sau đó RabbitTemplate đọc queue đã được required-groups provision. Trong test lớn hơn, có thể dùng Awaitility để chờ điều kiện và deserialize output thành DTO nhằm assert từng field. Timeout ở producer và queue receive giúp test kết thúc hữu hạn khi bridge không chuyển message.

Cấu hình test phải chọn binder thật cho từng binding. Nếu Spring Integration Test Binder có trong test classpath và được chọn thay binder middleware, test có thể pass mà không hề kiểm tra Kafka/Rabbit. Tách source set/module nếu cần.

## 34. Assertion end-to-end quan trọng

Với một source event duy nhất, test nên xác minh:

1. Kafka producer gửi record tới orders.created.
2. Bridge consumer group nhận record.
3. Function được gọi và mapping chính xác.
4. Rabbit exchange orders.fulfillment nhận output.
5. Routing key fulfillment.requested route tới queue fulfillment.
6. Output envelope có eventType FulfillmentRequested và schemaVersion 1.
7. causationId bằng eventId đầu vào.
8. correlationId được giữ.
9. eventId đầu ra ổn định khi cùng input được xử lý lại.
10. Fulfillment consumer lưu idempotency key.
11. Duplicate input không tạo fulfillment thứ hai.
12. Message lỗi được đưa vào error path quan sát được.

Không chỉ assert queue có một message. Hãy đọc và kiểm tra payload/header. Queue có thể chứa message cũ từ lần test trước nếu topology không được cô lập.

## 35. Kiểm thử duplicate window

Một test reliability nên mô phỏng:

~~~text
1. Bridge nhận Kafka event E.
2. Rabbit nhận output E2.
3. Bridge dừng trước khi Kafka offset được commit.
4. Bridge khởi động lại.
5. Kafka giao lại E.
6. Bridge phát lại E2 với cùng eventId.
7. Fulfillment inbox nhận ra duplicate.
8. Chỉ một fulfillment nghiệp vụ được tạo.
~~~

Trong test, có thể inject failure ngay sau khi output publish thành công hoặc trước khi handler hoàn tất. Cách inject phải có test hook riêng; không tạo lỗi bằng cách kill môi trường production.

Nếu dùng outbox, mô phỏng crash sau publish trước khi đánh dấu SENT. Relay sẽ thử lại, downstream idempotency phải bảo đảm side effect chỉ xảy ra một lần.

## 36. Failure matrix cho bridge

| Sự cố | Kết quả mong đợi | Cần kiểm tra |
|---|---|---|
| Kafka tạm down | Consumer reconnect; lag tăng | Reconnect, lag, retry |
| Rabbit tạm down | Output không bị coi là hoàn tất; retry/outbox giữ lại | Publish failure, outbox pending |
| Rabbit exchange tồn tại nhưng không có queue match | Unroutable được phát hiện | Return/alternate exchange |
| Input JSON sai | Không publish output sai | Validation error, DLQ |
| Schema version mới chưa hỗ trợ | Quarantine hoặc DLQ | Version metric |
| Process crash sau Rabbit publish | Có thể duplicate khi Kafka redelivery | Deterministic ID, inbox |
| Process crash trước Rabbit publish | Input được retry nếu chưa ack | Offset/ack policy |
| Fulfillment consumer crash sau side effect | Message có thể redeliver | Downstream idempotency |
| Kafka rebalance | Message đang xử lý có thể redeliver | Graceful shutdown, idempotency |
| Rabbit queue bị xóa | Publish có thể unroutable | Provisioning/required groups |

## 37. Runbook khi bridge không chuyển message

Theo thứ tự:

1. Kiểm tra Kafka input binding STARTED.
2. Xác nhận cluster/topic orders.created.
3. Kiểm tra group order-fulfillment-bridge, member assignment và lag.
4. Xác nhận record mới có eventId và key.
5. Kiểm tra function validation/mapping logs.
6. Kiểm tra Rabbit endpoint, vhost và exchange orders.fulfillment.
7. Kiểm tra queue fulfillment group và binding key.
8. Kiểm tra publisher confirms/returns và error path.
9. Kiểm tra retry/DLQ hoặc outbox pending.
10. Kiểm tra downstream consumer và idempotency.

Không reset Kafka offset hoặc purge Rabbit queue để “thử xem có chạy không”. Trước khi replay, ghi lại source offset, output event ID và side effects đã hoàn tất.

## 38. Triển khai và vận hành

Các bước triển khai:

- Provision Kafka topic, partition, retention và ACL.
- Provision Rabbit exchange, durable queue, binding và DLQ theo policy.
- Cấp credential riêng cho bridge.
- Cấu hình TLS/SASL và secret từ external configuration.
- Đặt group ổn định và concurrency phù hợp partition.
- Đặt timeout/retry có giới hạn.
- Cấu hình readiness/liveness độc lập với broker outage.
- Bật metrics, tracing và structured logging.
- Chạy contract test và broker integration test trước rollout.
- Triển khai canary hoặc rolling update.
- Theo dõi Kafka lag, Rabbit queue depth, publish failure, outbox age và DLQ.
- Chỉ thu hồi credential cũ sau khi xác nhận mọi instance dùng credential mới.

Bridge nên có ít nhất một cảnh báo cho Kafka lag tăng kéo dài, Rabbit publish failure, unroutable count, DLQ tăng và outbox pending quá tuổi. Một Pod Ready không chứng minh end-to-end flow khỏe.

## 39. Các quyết định thiết kế cần ghi vào ADR

Trước production, nhóm nên ghi rõ:

| Quyết định | Câu hỏi phải trả lời |
|---|---|
| Event identity | ID đầu ra được tạo ổn định thế nào? |
| Schema ownership | Ai sở hữu và review event contract? |
| Compatibility | Hỗ trợ schema version cũ trong bao lâu? |
| Kafka group | Group nào chỉ bridge dùng? |
| Partition key | Key nào giữ ordering theo order? |
| Rabbit topology | Exchange, queue, routing key và group naming? |
| Delivery guarantee | At-most-once, at-least-once hay có outbox? |
| Duplicate handling | Inbox/idempotency key nằm ở đâu? |
| Error policy | Retry bao nhiêu lần, lỗi nào DLQ? |
| Replay | Ai được replay, bằng công cụ nào, audit ra sao? |
| Ownership | Ai provision và ai xóa topic/queue? |
| Security | Principal và ACL tối thiểu là gì? |
| Observability | Event ID và correlation được trace ra sao? |

Không dùng cụm “exactly-once” nếu chưa định nghĩa phạm vi. Kafka transaction có thể hỗ trợ exactly-once trong phạm vi Kafka read-process-write khi cấu hình phù hợp; nó không tự tạo một transaction nguyên tử với RabbitMQ và database.

## 40. Checklist nghiệm thu

- [ ] Envelope có eventId, eventType, schemaVersion, occurredAt, producer, correlationId và payload.
- [ ] OrderCreated và FulfillmentRequested có schema/version rõ.
- [ ] Mapping bảo toàn causation/correlation và tạo output event ID ổn định.
- [ ] Function definition và input/output binding names chính xác.
- [ ] Input binder là Kafka; output binder là Rabbit.
- [ ] Kafka topic/group/partition và ACL đúng.
- [ ] Rabbit exchange/queue/group/routing key và ACL đúng.
- [ ] Content type/JSON conversion và schema validation đã test.
- [ ] Producer confirms/returns được hiểu và giám sát đúng.
- [ ] Retry/DLQ có giới hạn và có quy trình replay.
- [ ] Duplicate window được kiểm thử.
- [ ] Downstream idempotency có unique constraint.
- [ ] Outbox/inbox được dùng nếu cần độ tin cậy cao.
- [ ] Testcontainers chạy cả Kafka và Rabbit thật.
- [ ] Metrics/tracing/log không làm lộ dữ liệu nhạy cảm.
- [ ] Runbook có bước điều tra và rollback an toàn.

## 41. Tài liệu tham khảo

- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html): quy ước input/output binding của Supplier, Function và Consumer.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): destination, group, binder, content type, consumer và producer properties.
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html): Kafka topic, consumer group, producer, offset và binder configuration.
- [Spring Cloud Stream — RabbitMQ Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html): exchange, queue, group, routing và producer/consumer properties.
- [Spring Cloud Stream — RabbitMQ Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html): required groups, bindingRoutingKey, confirms và routingKey.
- [Spring Cloud — Supported Versions](https://spring.io/projects/spring-cloud/): chọn release train tương thích với Spring Boot.
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html): retry, error channel và xử lý lỗi.
- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): xác nhận publish và message return.
- [Apache Kafka — Design](https://kafka.apache.org/documentation/#design): partition, ordering, replication và consumer semantics.
- [RabbitMQ — Exchanges](https://www.rabbitmq.com/docs/exchanges): direct, topic, fanout và routing key.
- [RabbitMQ — Publisher Confirms](https://www.rabbitmq.com/docs/confirms): broker confirm, consumer acknowledgement và delivery semantics.
- [Testcontainers — Kafka](https://java.testcontainers.org/modules/kafka/): KafkaContainer cho integration test.
- [Testcontainers — RabbitMQ](https://java.testcontainers.org/modules/rabbitmq/): RabbitMQContainer cho integration test.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): chuẩn traceparent và propagation.

**Kết quả mong đợi:** Kafka và RabbitMQ có thể dùng chung một event contract mà không buộc hai broker phải có cùng mô hình định tuyến. Kafka group/partition quản lý việc đọc nguồn; Rabbit exchange/queue/routing key quản lý phân phối đích. Bridge phải giữ event identity và schema, xử lý duplicate theo at-least-once, và dùng inbox/outbox khi yêu cầu không mất sự kiện quan trọng hơn mức một function trực tiếp có thể bảo đảm.

