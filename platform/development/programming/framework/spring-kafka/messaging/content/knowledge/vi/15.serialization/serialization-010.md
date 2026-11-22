# Deserializer cho nhiều kiểu payload

Một Kafka topic có thể chứa nhiều loại event, chẳng hạn `OrderCreatedEvent` và `PaymentCapturedEvent`. Consumer cần xác định kiểu Java phù hợp cho từng record trước khi listener xử lý. Spring Kafka hỗ trợ nhiều chiến lược: dùng type header cùng `JsonDeserializer`, dùng `@KafkaHandler` để dispatch theo kiểu payload, đóng gói event trong một envelope có trường phân biệt loại event, hoặc tách topic/listener theo từng schema.

Trong module `SPRING_KAFKA_MESSAGING`, producer gửi record bằng `KafkaTemplate`, consumer nhận record bằng `@KafkaListener`. Serialization là hợp đồng giữa hai phía: producer biến object thành byte, consumer biến byte trở lại kiểu dữ liệu ứng dụng hiểu. Khi một topic chứa nhiều kiểu payload, hợp đồng phải cho biết record thuộc loại nào và cách xử lý khi consumer gặp loại chưa biết.

## 1. Vì sao consumer cần nhận diện nhiều kiểu payload?

Giả sử topic `domain-events` nhận các event từ nhiều nghiệp vụ:

```text
domain-events
├── OrderCreatedEvent
├── PaymentCapturedEvent
├── OrderCancelledEvent
└── ShipmentDispatchedEvent
```

Tất cả record đều là byte khi lưu trong Kafka. Broker không lưu object Java và không tự biết một JSON document là `OrderCreatedEvent` hay `PaymentCapturedEvent`. Consumer phải dựa vào metadata hoặc cấu trúc payload để chọn kiểu deserialize.

Nếu consumer luôn deserialize mọi record thành một class cố định, record thuộc kiểu khác có thể bị lỗi, mất trường hoặc trở thành object không đúng với nghiệp vụ. Vì vậy, trước khi chọn deserializer, cần xác định:

- Một topic có thật sự cần chứa nhiều loại event hay có thể tách theo topic?
- Producer có gửi metadata nhận diện kiểu event không?
- Producer và consumer có dùng chung Java class hay chỉ chia sẻ schema độc lập ngôn ngữ?
- Consumer phải làm gì khi gặp event type hoặc schema version chưa biết?

## 2. Các chiến lược deserialize nhiều kiểu

| Chiến lược | Cách nhận diện kiểu | Phù hợp khi |
|---|---|---|
| JSON type headers | Header do `JsonSerializer` ghi vào record | Producer/consumer dùng Spring Kafka JSON serializer và deserializer |
| Type mapping | Token ổn định trong type header ánh xạ tới class ở mỗi service | Producer và consumer có package/class khác nhau |
| Event envelope | Trường `eventType` trong payload JSON | Muốn hợp đồng độc lập với tên class Java và hỗ trợ nhiều ngôn ngữ |
| Một topic cho mỗi loại payload | Topic xác định schema; listener/factory có kiểu cố định | Các event có vòng đời, quyền truy cập hoặc retention khác nhau |
| Custom deserializer/converter | Logic ứng dụng hoặc schema registry xác định kiểu | Có yêu cầu schema/format đặc thù |

Không có chiến lược nào phù hợp với mọi hệ thống. Nếu chỉ có một kiểu payload trên mỗi topic, dùng listener có kiểu cụ thể thường đơn giản nhất. Nếu nhiều event có chủ đích nằm chung một topic, type header hoặc envelope giúp consumer định tuyến rõ ràng.

## 3. Dùng JSON type headers với `JsonDeserializer`

Spring Kafka `JsonSerializer` có thể thêm type information vào Kafka headers. `JsonDeserializer` đọc type information đó để tạo đúng class payload. Đây là cách thuận tiện khi producer và consumer cùng dùng Spring Kafka và đã thống nhất quy ước type header.

Ví dụ hai kiểu event:

Mỗi record được đặt trong một file Java riêng trong dự án:

```java
import java.math.BigDecimal;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total
) {}

public record PaymentCapturedEvent(
        String eventId,
        String paymentId,
        String orderId,
        BigDecimal amount
) {}
```

Producer có thể gửi hai loại object qua cùng một `KafkaTemplate<String, Object>` nếu serializer được cấu hình để serialize các kiểu đó:

Ví dụ giả định ứng dụng đã khai báo `ProducerFactory<String, Object>` và `KafkaTemplate<String, Object>` dùng `StringSerializer` cho key cùng `JsonSerializer` cho value. Kiểu `Object` cho phép gửi nhiều class nhưng làm giảm kiểm tra kiểu ở compile time; chỉ dùng ở adapter có chủ đích.

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class DomainEventPublisher {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public DomainEventPublisher(KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishOrderCreated(OrderCreatedEvent event) {
        kafkaTemplate.send("domain-events", event.orderId(), event);
    }

    public void publishPaymentCaptured(PaymentCapturedEvent event) {
        kafkaTemplate.send("domain-events", event.orderId(), event);
    }
}
```

Với JSON serializer mặc định của Spring Kafka, type header được thêm vào record. Consumer dùng `JsonDeserializer` để đọc type header và tạo instance của class tương ứng. Cấu hình minh họa:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: domain-event-router
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.use.type.headers: true
        spring.json.trusted.packages: com.acme.events
```

`spring.json.use.type.headers: true` yêu cầu deserializer sử dụng type header để xác định class. Đây là hành vi mặc định phổ biến của `JsonDeserializer`, nhưng khai báo rõ trong cấu hình giúp ý định dễ đọc. `trusted.packages` giới hạn package mà deserializer được phép tạo object; hãy chỉ tin cậy package event cần thiết.

Type header chứa thông tin kiểu do producer cung cấp. Nếu consumer không có class tương ứng, package không được tin cậy hoặc token không ánh xạ được, quá trình deserialize có thể thất bại trước khi listener được gọi. Cần quản lý classpath và mapping giữa các service.

## 4. Dùng type mapping để không phụ thuộc package Java của producer

Mặc định, type header JSON có thể chứa tên class đầy đủ. Điều này tạo liên kết giữa producer và consumer: đổi package hoặc đổi tên class có thể làm consumer cũ không resolve được type.

Spring Kafka hỗ trợ `spring.json.type.mapping` để ánh xạ một token ngắn tới class cụ thể. Producer và consumer dùng cùng token nhưng có thể ánh xạ sang class ở package riêng của mỗi service.

Ví dụ producer:

```yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: "orderCreated:com.acme.orders.contract.OrderCreatedEvent,paymentCaptured:com.acme.payments.contract.PaymentCapturedEvent"
```

Consumer có thể ánh xạ các token đó sang class contract của chính nó:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.use.type.headers: true
        spring.json.trusted.packages: com.acme.billing.contract
        spring.json.type.mapping: "orderCreated:com.acme.billing.contract.OrderCreated,paymentCaptured:com.acme.billing.contract.PaymentCaptured"
```

Ví dụ giả định consumer có hai class `OrderCreated` và `PaymentCaptured` với cấu trúc tương thích payload producer. Token `orderCreated` và `paymentCaptured` là phần hợp đồng được hai phía thống nhất; package Java không cần giống nhau.

Khi đổi class nội bộ, giữ token ổn định nếu schema vẫn tương thích. Không tái sử dụng một token cho hai schema không tương thích. Mapping cần được triển khai đồng bộ với consumer versions đang chạy; nếu producer phát token mới trước khi consumer hỗ trợ, record có thể thất bại khi deserialize.

## 5. Dispatch payload theo kiểu bằng `@KafkaHandler`

Khi `JsonDeserializer` đã tạo đúng class, có thể dùng class-level `@KafkaListener` và nhiều method `@KafkaHandler`. Spring Kafka chọn method dựa trên kiểu payload thực tế.

```java
import org.springframework.kafka.annotation.KafkaHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
@KafkaListener(
        id = "domainEventListener",
        topics = "domain-events",
        groupId = "domain-event-router"
)
public class DomainEventListener {

    @KafkaHandler
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Order created: " + event.orderId());
    }

    @KafkaHandler
    public void onPaymentCaptured(PaymentCapturedEvent event) {
        System.out.println("Payment captured: " + event.paymentId());
    }

    @KafkaHandler(isDefault = true)
    public void onUnknownEvent(Object payload) {
        String payloadType = payload == null
                ? "null"
                : payload.getClass().getName();
        throw new IllegalArgumentException(
                "Unsupported event payload: " + payloadType
        );
    }
}
```

Mỗi method `@KafkaHandler` xử lý một kiểu payload. Method `isDefault = true` là nhánh dự phòng khi không có handler cụ thể phù hợp. Trong ví dụ, nhánh dự phòng ném exception để error handler có thể retry hoặc chuyển record sang dead-letter topic theo chính sách.

Không nên chỉ log event không hỗ trợ rồi trả về nếu hệ thống cần bảo đảm không bỏ mất loại event mới. Listener trả về bình thường thường được xem là xử lý thành công và offset có thể được commit. Hãy quyết định rõ unknown event là lỗi cần recovery, loại event được phép bỏ qua, hay sự kiện cần lưu lại để xử lý sau.

`@KafkaHandler` dispatch theo kiểu Java đã deserialize. Nó không tự đọc JSON field `eventType` để quyết định class. Nếu deserializer luôn tạo `Map` hoặc `JsonNode`, các handler nhận `OrderCreatedEvent` sẽ không tự được chọn.

## 6. Dùng event envelope khi muốn hợp đồng độc lập với class Java

Một cách khác là bọc mọi loại event trong một cấu trúc chung. Envelope chứa loại event, phiên bản schema và payload:

```json
{
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "payload": {
    "eventId": "evt-1001",
    "orderId": "order-1001",
    "total": 1250000
  }
}
```

Java model:

```java
import com.fasterxml.jackson.databind.JsonNode;

public record EventEnvelope(
        String eventType,
        int schemaVersion,
        JsonNode payload
) {}
```

Các handler mà listener sử dụng có thể có contract như sau:

```java
public interface OrderEventHandler {
    void handle(OrderCreatedEvent event);
}

public interface PaymentEventHandler {
    void handle(PaymentCapturedEvent event);
}
```

Consumer deserialize mọi record thành `EventEnvelope`, sau đó định tuyến theo `eventType`:

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class EnvelopeEventListener {

    private final ObjectMapper objectMapper;
    private final OrderEventHandler orderHandler;
    private final PaymentEventHandler paymentHandler;

    public EnvelopeEventListener(
            ObjectMapper objectMapper,
            OrderEventHandler orderHandler,
            PaymentEventHandler paymentHandler) {
        this.objectMapper = objectMapper;
        this.orderHandler = orderHandler;
        this.paymentHandler = paymentHandler;
    }

    @KafkaListener(topics = "domain-events", groupId = "envelope-router")
    public void listen(EventEnvelope envelope) throws JsonProcessingException {
        if (envelope == null || envelope.eventType() == null
                || envelope.payload() == null) {
            throw new IllegalArgumentException("Event envelope is incomplete");
        }
        if (envelope.schemaVersion() != 1) {
            throw new IllegalArgumentException(
                    "Unsupported schema version: " + envelope.schemaVersion());
        }

        switch (envelope.eventType()) {
            case "OrderCreated" -> orderHandler.handle(
                    objectMapper.treeToValue(
                            envelope.payload(), OrderCreatedEvent.class));
            case "PaymentCaptured" -> paymentHandler.handle(
                    objectMapper.treeToValue(
                            envelope.payload(), PaymentCapturedEvent.class));
            default -> throw new IllegalArgumentException(
                    "Unsupported event type: " + envelope.eventType());
        }
    }
}
```

Trong cách này, `JsonDeserializer` chỉ cần tạo `EventEnvelope`; payload bên trong được chuyển sang kiểu cụ thể sau khi đọc `eventType`. Cấu hình consumer có thể đặt default type và bỏ qua type header:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.acme.messaging.EventEnvelope
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.acme.messaging
```

Envelope có ưu điểm là hợp đồng rõ ràng, dễ dùng với nhiều ngôn ngữ và không cần consumer biết tên class của producer. Đổi lại, ứng dụng phải quản lý danh sách event type, schema version và logic chuyển đổi payload. Hãy kiểm tra `schemaVersion` và từ chối hoặc chuyển recovery đối với version không hỗ trợ; không mặc định mọi payload cùng `eventType` luôn có cấu trúc giống nhau.

## 7. Khi mỗi topic chỉ có một kiểu payload

Nếu event có vòng đời, quyền truy cập, retention hoặc tốc độ phát triển schema khác nhau, tách topic thường đơn giản hơn việc đặt nhiều kiểu payload trong cùng một topic.

Ví dụ mỗi topic có listener kiểu cụ thể:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final OrderEventHandler orderHandler;

    public OrderCreatedListener(OrderEventHandler orderHandler) {
        this.orderHandler = orderHandler;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-projection",
            containerFactory = "orderEventListenerContainerFactory"
    )
    public void onOrderCreated(OrderCreatedEvent event) {
        orderHandler.handle(event);
    }
}

@Component
class PaymentCapturedListener {

    private final PaymentEventHandler paymentHandler;

    public PaymentCapturedListener(PaymentEventHandler paymentHandler) {
        this.paymentHandler = paymentHandler;
    }

    @KafkaListener(
            topics = "payments.captured",
            groupId = "payment-projection",
            containerFactory = "paymentEventListenerContainerFactory"
    )
    public void onPaymentCaptured(PaymentCapturedEvent event) {
        paymentHandler.handle(event);
    }
}
```

Mỗi container factory có thể dùng `JsonDeserializer` với target type riêng. Khi đó, consumer không cần polymorphic deserialization hoặc dispatch theo type header. Cấu trúc này dễ quan sát và cho phép cấu hình retry/DLT, concurrency, ACL và retention riêng theo topic.

Không nên tách topic chỉ vì hai event có class khác nhau nếu chúng thực sự thuộc cùng một luồng logic và cần cùng partition ordering. Quyết định nên dựa vào hợp đồng, quyền sở hữu, cách tiêu thụ và vận hành.

## 8. Xử lý payload không hợp lệ hoặc type chưa biết

Deserialization xảy ra trước khi method listener được gọi. Vì vậy, lỗi JSON malformed, type header không resolve được hoặc package không được tin cậy có thể không đi vào `try/catch` bên trong listener. Cần cấu hình error handling ở tầng container.

Spring Kafka cung cấp `ErrorHandlingDeserializer` để bọc deserializer thật. Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.use.type.headers: true
        spring.json.trusted.packages: com.acme.billing.contract
        spring.json.type.mapping: "orderCreated:com.acme.billing.contract.OrderCreated,paymentCaptured:com.acme.billing.contract.PaymentCaptured"
```

`ErrorHandlingDeserializer` bắt lỗi từ delegate và chuyển thông tin lỗi theo cơ chế Spring Kafka để error handler/recoverer xử lý. Hãy cấu hình `DefaultErrorHandler` và dead-letter publishing phù hợp nếu muốn lưu record lỗi. Cần kiểm thử riêng trường hợp lỗi deserialize vì listener method có thể không nhận được payload bình thường.

Với event type hợp lệ nhưng ứng dụng chưa hỗ trợ, nhánh default của `@KafkaHandler` hoặc `switch` trên envelope phải quyết định rõ retry, DLT hoặc bỏ qua có chủ đích. Không retry vô hạn một type mà consumer không thể hiểu; đó thường là lỗi hợp đồng cần cảnh báo và recovery.

## 9. An toàn khi deserialize nhiều kiểu

Type header ảnh hưởng đến class được tạo từ byte không tin cậy. Vì vậy, không nên mở rộng phạm vi type có thể khởi tạo quá mức cần thiết.

- Chỉ cấu hình `trusted.packages` cho package chứa event contract cần thiết.
- Tránh `*` hoặc trusted package quá rộng trong môi trường production.
- Dùng type mapping token ổn định thay vì để producer quyết định tùy ý tên class Java ở consumer.
- Không bật Jackson default typing rộng cho payload Kafka không đáng tin cậy.
- Xác thực dữ liệu sau deserialize; một object deserialize thành công chưa chắc hợp lệ về nghiệp vụ.
- Không đưa thông tin bí mật hoặc dữ liệu cá nhân không cần thiết vào type header/custom header.
- Có chính sách rõ cho event type lạ, schema version mới và payload sai định dạng.

Type mapping giúp giảm phụ thuộc package nhưng không thay thế kiểm soát schema hoặc xác thực payload. Consumer vẫn cần giới hạn class được phép ánh xạ và kiểm tra dữ liệu đầu vào.

## 10. Schema evolution khi topic có nhiều event type

Khi nhiều loại event dùng chung topic, consumer cần tương thích với các phiên bản producer đang triển khai song song. Một số nguyên tắc:

- Dùng tên event ổn định như `OrderCreated` thay vì tên class nội bộ làm hợp đồng duy nhất.
- Định nghĩa schema và ý nghĩa từng field; tránh đổi nghĩa field mà giữ nguyên tên.
- Ưu tiên thay đổi tương thích, ví dụ thêm field optional có default phù hợp.
- Không xóa hoặc đổi kiểu field khi consumer cũ vẫn có thể đọc record mới.
- Dùng `schemaVersion` khi envelope hoặc schema registry yêu cầu quản lý version rõ ràng.
- Có kiểm thử compatibility giữa producer và consumer version đang hỗ trợ.
- Quy định thời gian hỗ trợ event type cũ và quy trình ngừng phát type cũ.

Nếu dùng Schema Registry với Avro, Protobuf hoặc JSON Schema, schema registry quản lý schema/version và serializer/deserializer tương ứng. Type mapping trong Spring Kafka JSON là cơ chế ánh xạ class/token; nó không thay thế đầy đủ các chức năng kiểm tra compatibility của schema registry.

## 11. Kiểm thử deserializer cho nhiều kiểu payload

Nên kiểm thử ở cả mức cấu hình và luồng Kafka thực tế:

- **Type header test:** gửi từng event bằng `JsonSerializer`, xác minh `JsonDeserializer` tạo đúng class.
- **Type mapping test:** producer và consumer dùng package/class khác nhau nhưng cùng token; xác minh consumer resolve đúng local class.
- **Handler dispatch test:** xác minh `@KafkaHandler` gọi đúng method cho từng payload type.
- **Envelope test:** xác minh `eventType` và `schemaVersion` chọn đúng handler, payload được convert đúng class.
- **Unknown type test:** gửi token hoặc event type chưa hỗ trợ, xác minh nhánh default/error handler/DLT hoạt động theo chính sách.
- **Malformed JSON test:** gửi payload sai định dạng và xác minh `ErrorHandlingDeserializer` cùng error handler xử lý.
- **Compatibility test:** kiểm tra consumer cũ đọc payload được producer version mới phát hành.
- **Security test:** xác minh class ngoài trusted packages không được deserialize.

Embedded Kafka hoặc Testcontainers phù hợp cho integration test. Hãy dùng topic và consumer group riêng cho từng test để tránh offset cũ làm sai kết quả.

## 12. Lựa chọn chiến lược theo tình huống

| Tình huống | Lựa chọn gợi ý |
|---|---|
| Cùng một topic chứa nhiều POJO Java, producer và consumer đều dùng Spring Kafka | JSON type headers + `JsonDeserializer` |
| Hai service dùng package Java khác nhau nhưng thống nhất event schema | Type mapping với token ổn định |
| Producer đa ngôn ngữ hoặc không muốn phụ thuộc Java class name | Event envelope có `eventType` và `schemaVersion` |
| Mỗi loại event có retention, ACL hoặc retry policy khác nhau | Tách topic và listener factory theo loại |
| Dùng Avro/Protobuf/JSON Schema với quản lý compatibility | Serializer/deserializer và Schema Registry tương ứng |
| Cần kiểm soát đặc biệt cách chuyển byte thành object | Custom deserializer hoặc message converter |

Không chọn `KafkaTemplate<String, Object>` chỉ để làm code ngắn hơn nếu producer thực tế chỉ phát một loại event. Kiểu cụ thể giúp compiler kiểm tra payload và làm hợp đồng dễ hiểu hơn. Chỉ dùng template đa kiểu khi đó là một luồng có chủ đích và serializer hỗ trợ các loại event được công bố.

## 13. Những lỗi thường gặp

- **Tắt type headers nhưng vẫn mong `JsonDeserializer` tự nhận nhiều class:** khi không có type metadata, consumer cần default type hoặc envelope/custom resolver.
- **Dùng `Object` rồi nghĩ payload luôn là POJO cụ thể:** nếu không có type header hoặc target type, JSON object có thể được deserialize thành `Map`.
- **Producer và consumer không thống nhất type mapping token:** token không resolve được hoặc ánh xạ nhầm schema.
- **Trusted packages quá rộng:** tăng rủi ro deserialize class không mong muốn.
- **`@KafkaHandler` không được gọi:** payload thực tế không có kiểu phù hợp vì deserializer tạo `Map`, `JsonNode` hoặc class khác.
- **Unknown event bị bỏ qua âm thầm:** listener trả về bình thường có thể khiến offset được commit dù event chưa được xử lý.
- **Bắt lỗi trong listener nhưng lỗi xảy ra trước listener:** lỗi deserialize cần error handler/recoverer ở container.
- **Dùng type mapping như một schema registry:** token-to-class mapping không tự kiểm tra schema compatibility.
- **Tách quá nhiều topic hoặc gộp mọi event vào một topic:** cả hai đều có chi phí; quyết định theo hợp đồng và vận hành.
- **Không kiểm thử consumer cũ:** producer mới có thể phát type hoặc schema mà consumer đang chạy chưa hỗ trợ.

## 14. Checklist trước khi triển khai multi-type deserialization

- [ ] Đã chọn rõ type headers, type mapping, envelope hay topic riêng.
- [ ] Producer serializer và consumer deserializer thống nhất format.
- [ ] Type token/event type là hợp đồng ổn định, không phụ thuộc tên class nội bộ.
- [ ] `trusted.packages` chỉ chứa package cần thiết.
- [ ] `@KafkaHandler` có handler cho từng type và chính sách cho type chưa biết.
- [ ] Envelope kiểm tra `eventType`, `schemaVersion` và payload.
- [ ] Lỗi deserialize được xử lý ở container qua error handler/recoverer.
- [ ] Retry/DLT không lặp vô hạn với event type không được hỗ trợ.
- [ ] Schema evolution tương thích với producer/consumer đang triển khai song song.
- [ ] Integration test bao gồm payload hợp lệ, type lạ, malformed JSON và schema version mới.

Deserializer cho nhiều kiểu payload cần một hợp đồng nhận diện event rõ ràng. Type headers và mapping phù hợp với hệ thống Spring Kafka dùng JSON; envelope phù hợp khi muốn độc lập với class Java; topic riêng phù hợp khi mỗi loại event có cách vận hành khác nhau. Kết hợp chiến lược đã chọn với kiểm soát trusted packages, schema compatibility và error handling giúp consumer xử lý nhiều event type an toàn và có thể mở rộng.
