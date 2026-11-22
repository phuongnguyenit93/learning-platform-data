# Đọc Message<?> trong listener

Trong Spring Kafka, phương thức `@KafkaListener` có thể nhận trực tiếp payload đã deserialize, nhận `ConsumerRecord<K, V>` để truy cập API Kafka cấp thấp, hoặc nhận `Message<?>` của Spring Messaging. `Message<?>` đóng gói payload cùng các header mô tả record như topic, partition, offset, key và timestamp. Cách này giúp listener xử lý dữ liệu và metadata trong cùng một tham số theo abstraction của Spring.

Trong module `SPRING_KAFKA_MESSAGING`, consumer nhận event từ Kafka bằng `@KafkaListener`. Khi cần kiểm tra metadata để ghi log, truy vết hoặc chuyển thông tin đến application use case, `Message<?>` là lựa chọn hữu ích. Cần hiểu rằng dấu `?` biểu thị kiểu payload chưa được khai báo cụ thể ở compile time; kiểu thực tế vẫn do deserializer hoặc message converter quyết định.

## 1. `Message<?>` là gì?

`Message<T>` thuộc Spring Messaging (`org.springframework.messaging.Message`). Một message có hai phần chính:

- `getPayload()`: dữ liệu chính mà listener nhận được.
- `getHeaders()`: tập metadata dạng `MessageHeaders`.

`Message<?>` nghĩa là payload có một kiểu Java nào đó nhưng phương thức listener không khai báo cụ thể kiểu ấy. Khi đọc `message.getPayload()`, compiler xem kết quả là `Object`; ứng dụng cần kiểm tra kiểu trước khi ép kiểu hoặc xử lý.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageListener {

    @KafkaListener(topics = "orders", groupId = "orders-service")
    public void listen(Message<?> message) {
        Object payload = message.getPayload();
        String payloadType = payload == null
                ? "null"
                : payload.getClass().getName();
        System.out.println("Payload type: " + payloadType);
        System.out.println("Payload: " + payload);
        System.out.println("Headers: " + message.getHeaders());
    }
}
```

Spring Kafka chuyển `ConsumerRecord` thành Spring `Message` thông qua message converter của listener container. Vì vậy, `Message<?>` không phải byte record thô từ broker; payload đã đi qua quá trình deserialize và/hoặc convert được cấu hình cho consumer.

## 2. Cấu trúc một Spring `Message`

Một message có thể hình dung như sau:

```text
Message<OrderCreatedEvent>
├── payload
│   └── OrderCreatedEvent(orderId=order-1001, ...)
└── headers (MessageHeaders)
    ├── kafka_receivedTopic      = "orders"
    ├── kafka_receivedPartition  = 2
    ├── kafka_offset              = 184
    ├── kafka_receivedTimestamp  = 1731741000000
    ├── kafka_receivedKey        = "order-1001"
    └── correlation-id           = ...
```

Tên header minh họa ở trên thể hiện ý nghĩa. Trong code, nên dùng hằng số `KafkaHeaders` thay vì gõ chuỗi tên header Kafka trực tiếp. `MessageHeaders` còn có thể chứa các header chuẩn của Spring như `id` và `timestamp`; các header này khác với timestamp Kafka của record.

| Thành phần | API | Mục đích |
|---|---|---|
| Payload | `message.getPayload()` | Event hoặc dữ liệu đã deserialize/convert |
| Headers | `message.getHeaders()` | Metadata Spring và Kafka được ánh xạ vào message |
| Topic | `KafkaHeaders.RECEIVED_TOPIC` | Topic nhận record |
| Partition | `KafkaHeaders.RECEIVED_PARTITION` | Partition chứa record |
| Offset | `KafkaHeaders.OFFSET` | Offset của record trong partition |
| Key | `KafkaHeaders.RECEIVED_KEY` | Key đã được consumer deserialize |
| Timestamp | `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp Kafka nhận được trên record |

`MessageHeaders` là cấu trúc header chỉ đọc. Listener có thể đọc giá trị nhưng không nên coi map này là nơi cập nhật trạng thái nghiệp vụ. Nếu cần tạo một Spring Message mới, dùng `MessageBuilder` ở tầng tạo message thay vì sửa trực tiếp headers nhận vào.

## 3. Đọc metadata Kafka từ `MessageHeaders`

Spring Kafka cung cấp các hằng số trong `org.springframework.kafka.support.KafkaHeaders`. Ví dụ:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.stereotype.Component;

@Component
public class OrderMetadataListener {

    @KafkaListener(topics = "orders", groupId = "orders-observer")
    public void listen(Message<?> message) {
        MessageHeaders headers = message.getHeaders();

        String topic = headers.get(
                KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = headers.get(
                KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = headers.get(KafkaHeaders.OFFSET, Long.class);
        Long timestamp = headers.get(
                KafkaHeaders.RECEIVED_TIMESTAMP, Long.class);
        Object key = headers.get(KafkaHeaders.RECEIVED_KEY);

        System.out.printf(
                "topic=%s partition=%s offset=%s timestamp=%s key=%s%n",
                topic, partition, offset, timestamp, key
        );

        Object payload = message.getPayload();
        // Chuyển payload đến bước xử lý tiếp theo.
    }
}
```

Các header metadata hữu ích khi ghi log và đối chiếu consumer lag. Offset chỉ có ý nghĩa trong phạm vi partition; không dùng riêng offset để định danh duy nhất record trên toàn bộ topic. Nếu cần định danh một record, có thể kết hợp topic, partition và offset.

Header có thể không có trong một số ngữ cảnh hoặc khác kiểu do cấu hình converter/header mapper. Vì vậy, khi metadata không bắt buộc, hãy xử lý trường hợp giá trị `null`. Không ép kiểu tùy tiện khi chưa xác minh kiểu header thực tế.

## 4. Đọc payload có kiểu cụ thể

Nếu listener luôn xử lý một loại event, nên khai báo kiểu payload cụ thể để compiler hỗ trợ kiểm tra:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total,
        Instant occurredAt
) {}
```

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class TypedOrderListener {

    @KafkaListener(topics = "orders", groupId = "orders-projection")
    public void listen(Message<OrderCreatedEvent> message) {
        OrderCreatedEvent event = message.getPayload();
        System.out.println("Order ID: " + event.orderId());
    }
}
```

`Message<OrderCreatedEvent>` vẫn cung cấp đầy đủ headers như `Message<?>`, nhưng payload có kiểu rõ ràng. Kiểu generic này phải phù hợp với dữ liệu mà Kafka deserializer hoặc message converter tạo ra.

Nếu cần đọc nhiều loại event khác nhau trong cùng một listener, có thể nhận `Message<?>`, sau đó phân nhánh dựa trên kiểu payload hoặc header `event-type` đã được quy ước:

```java
@KafkaListener(topics = "domain-events", groupId = "domain-event-router")
public void listen(Message<?> message) {
    Object payload = message.getPayload();

    if (payload == null) {
        throw new IllegalArgumentException("Event payload must not be null");
    } else if (payload instanceof OrderCreatedEvent orderCreated) {
        handleOrderCreated(orderCreated);
    } else if (payload instanceof PaymentCapturedEvent paymentCaptured) {
        handlePaymentCaptured(paymentCaptured);
    } else {
        throw new IllegalArgumentException(
                "Unsupported event payload: " + payload.getClass().getName()
        );
    }
}
```

Ví dụ này giả định deserializer đã chuyển payload thành các kiểu Java tương ứng. Nếu payload luôn là `String` hoặc `byte[]`, cần parse/deserialize theo schema trước khi xử lý. Không nên chỉ dựa vào tên class trong header nếu producer và consumer không có hợp đồng schema tương thích.

## 5. Cấu hình deserialize để `Message<?>` nhận đúng payload

`Message<?>` không tự quyết định payload là JSON, String hay byte array. Payload type phụ thuộc vào Kafka `value.deserializer` và `RecordMessageConverter` được cấu hình trên listener container factory.

Ví dụ consumer dùng `JsonDeserializer` với kiểu đích cố định:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: orders-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.OrderCreatedEvent
        spring.json.trusted.packages: com.example.orders
        spring.json.use.type.headers: false
```

Trong ví dụ này, `JsonDeserializer` tạo payload kiểu `OrderCreatedEvent`. Khi listener nhận `Message<?>`, `getPayload()` trả về object đã deserialize; compiler chỉ nhìn thấy `Object` vì generic là wildcard. Nếu muốn compiler kiểm tra kiểu, dùng `Message<OrderCreatedEvent>`.

Với hệ thống nhiều loại event, cần xác định chiến lược schema/type rõ ràng: type header được quản lý, default type theo topic, converter có target type phù hợp hoặc schema registry. Không mở rộng `trusted.packages` tùy tiện; chỉ tin cậy package cần thiết theo cấu hình serializer/deserializer đang sử dụng.

Nếu dùng `StringDeserializer`, payload thường là `String`; nếu dùng `ByteArrayDeserializer`, payload thường là `byte[]`. Có thể cấu hình `RecordMessageConverter` để chuyển payload sang kiểu ứng dụng, nhưng phải bảo đảm converter có đủ thông tin target type. Wildcard `Message<?>` không cung cấp một kiểu payload cụ thể cho compiler.

## 6. Đọc custom header từ producer

Producer có thể thêm header vào `ProducerRecord`:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;

ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>("orders", event.orderId(), event);

record.headers().add(new RecordHeader(
        "correlation-id",
        correlationId.getBytes(StandardCharsets.UTF_8)
));

kafkaTemplate.send(record);
```

Consumer đọc custom header từ `MessageHeaders`:

```java
import java.nio.charset.StandardCharsets;

byte[] rawCorrelationId = message.getHeaders().get(
        "correlation-id", byte[].class);

String correlationId = rawCorrelationId == null
        ? null
        : new String(rawCorrelationId, StandardCharsets.UTF_8);
```

Kiểu Java mà consumer nhìn thấy cho custom header phụ thuộc `KafkaHeaderMapper` và cấu hình mapping. Ví dụ trên giả định header được giữ dưới dạng `byte[]`. Nếu mapper chuyển thành `String` hoặc kiểu khác, hãy đọc theo kiểu thực tế và thống nhất encoding giữa producer/consumer. Khi cần kiểm soát mapping, có thể cấu hình mapper riêng cho listener container factory.

Không nên đưa dữ liệu nghiệp vụ chính vào custom header. Header thích hợp cho correlation ID, trace context, event type hoặc metadata nhỏ; payload vẫn nên chứa nội dung event cần xử lý.

## 7. Dùng `@Header` khi chỉ cần một vài giá trị

Nếu listener chỉ cần một số metadata, không nhất thiết nhận cả `Message<?>`. Có thể khai báo payload và header thành các tham số riêng:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.stereotype.Component;

@Component
public class OrderHeaderListener {

    @KafkaListener(topics = "orders", groupId = "orders-audit")
    public void listen(
            @Payload OrderCreatedEvent event,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
            @Header(KafkaHeaders.OFFSET) long offset) {

        System.out.printf(
                "Received order=%s from %s-%d offset=%d%n",
                event.orderId(), topic, partition, offset
        );
    }
}
```

`Message<?>` phù hợp khi cần làm việc với payload và nhiều header như một đơn vị. `@Payload` và `@Header` phù hợp khi chữ ký method muốn thể hiện rõ các giá trị cần dùng. Cả hai đều dựa trên cơ chế message conversion và argument resolution của Spring Kafka.

## 8. `Message<?>` hay `ConsumerRecord<K, V>`?

Hai kiểu tham số giải quyết hai nhu cầu khác nhau:

| Tiêu chí | `Message<?>` | `ConsumerRecord<K, V>` |
|---|---|---|
| Abstraction | Spring Messaging | Kafka Java client |
| Payload | `getPayload()` trả về `Object` với wildcard | `value()` trả về `V` |
| Metadata | Qua `MessageHeaders` và `KafkaHeaders` | Qua các method `topic()`, `partition()`, `offset()`, `timestamp()`... |
| Custom headers | Được ánh xạ qua header mapper | Đọc trực tiếp từ `record.headers()` |
| Phù hợp | Tích hợp với Spring Messaging, header mapping và handler method | Cần truy cập Kafka record/metadata đầy đủ hoặc API Kafka cấp thấp |
| Phụ thuộc | Spring Messaging và Spring Kafka converter | Kafka client API |

Nếu application use case chỉ cần event và một vài metadata đã chọn, có thể chuyển những giá trị đó thành command/application input đơn giản. Không cần đưa toàn bộ `Message<?>` hoặc `ConsumerRecord` vào domain layer nếu nghiệp vụ không cần biết chi tiết Kafka.

## 9. Lưu ý về acknowledgment và xử lý lỗi

`Message<?>` có thể chứa header liên quan đến acknowledgment nếu listener container được cấu hình manual acknowledgment. Ví dụ, với `AckMode.MANUAL`, Spring Kafka có thể đưa đối tượng `Acknowledgment` vào header `KafkaHeaders.ACKNOWLEDGMENT`.

```java
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@KafkaListener(topics = "orders", groupId = "orders-manual-ack")
public void listen(Message<?> message) {
    Acknowledgment acknowledgment = message.getHeaders().get(
            KafkaHeaders.ACKNOWLEDGMENT,
            Acknowledgment.class
    );

    process(message.getPayload());

    if (acknowledgment != null) {
        acknowledgment.acknowledge();
    }
}
```

Chỉ dùng ví dụ này khi listener container đã được cấu hình acknowledgment mode phù hợp. Với chế độ ack tự động, header acknowledgment có thể không tồn tại. Trong thực tế, phải chỉ acknowledge sau khi xử lý thành công theo semantics đã chọn; nếu xử lý lỗi, để error handler/retry policy quyết định cách tiếp tục. Không acknowledge sớm trước khi công việc nghiệp vụ hoàn tất.

Nếu method listener ném exception, Spring Kafka xử lý theo error handler, retry và recovery configuration của container. Việc nhận `Message<?>` không thay đổi semantics commit offset. Header chỉ cung cấp dữ liệu cho listener; nó không tự bật manual ack hoặc retry.

## 10. Kiểm thử listener nhận `Message<?>`

Nên kiểm thử cả payload và metadata:

- **Unit test:** tạo Spring `Message` bằng `MessageBuilder.withPayload(...)` và header giả lập, sau đó kiểm tra logic xử lý tách khỏi Kafka.
- **Listener test:** gửi record vào topic test, xác minh payload được deserialize và listener đọc đúng topic, partition, offset, key hoặc custom header.
- **Serialization test:** xác minh producer serializer, consumer deserializer và header mapper tạo ra kiểu dữ liệu mong muốn.
- **Error test:** gửi payload sai schema hoặc thiếu header tùy chọn, xác minh listener không phát sinh lỗi ép kiểu ngoài dự kiến.
- **Acknowledgment test:** nếu dùng manual ack, xác minh acknowledgment chỉ được gọi sau khi xử lý thành công.

Với Embedded Kafka hoặc Testcontainers, hãy tạo topic test riêng và dùng consumer group riêng cho từng test. Khi kiểm tra offset/partition, đọc giá trị từ `KafkaHeaders` hoặc `ConsumerRecord` thay vì giả định record luôn được ghi vào partition `0`.

## 11. Những lỗi thường gặp

- **Cho rằng `Message<?>` chứa byte thô:** payload đã qua deserializer và/hoặc message converter. Kiểm tra cấu hình consumer trước khi ép kiểu.
- **Ép kiểu payload mà không kiểm tra:** wildcard khiến payload có kiểu compile-time là `Object`; dùng `instanceof` hoặc `Message<T>` khi có kiểu cố định.
- **Nhầm `MessageHeaders.TIMESTAMP` với Kafka timestamp:** dùng `KafkaHeaders.RECEIVED_TIMESTAMP` khi cần timestamp của record Kafka.
- **Dùng tên header dạng chuỗi tùy ý cho metadata chuẩn:** ưu tiên hằng số `KafkaHeaders` để tránh sai tên.
- **Giả định custom header luôn là `String`:** header có thể là `byte[]` hoặc kiểu khác tùy mapper; thống nhất encoding và mapping.
- **Coi `MessageHeaders` là map có thể sửa:** headers nhận vào là cấu trúc chỉ đọc; tạo message mới nếu cần biến đổi.
- **Đưa `Message<?>` vào domain layer:** domain nên nhận dữ liệu nghiệp vụ cần thiết, không phụ thuộc abstraction messaging nếu không cần.
- **Nghĩ rằng `Message<?>` tự bật manual ack:** acknowledgment mode phải được cấu hình ở listener container.
- **Dùng `Message<?>` dù cần toàn bộ Kafka API:** nếu cần thao tác record/header ở mức client, nhận `ConsumerRecord<K, V>` phù hợp hơn.

## 12. Checklist khi đọc `Message<?>`

- [ ] Đã xác định kiểu payload do deserializer hoặc message converter tạo ra.
- [ ] Dùng `Message<T>` khi payload có kiểu cố định; dùng `Message<?>` khi cần xử lý linh hoạt.
- [ ] Đọc metadata Kafka bằng hằng số `KafkaHeaders`.
- [ ] Xử lý trường hợp header không có hoặc có kiểu khác dự kiến.
- [ ] Phân biệt Kafka timestamp với Spring message timestamp.
- [ ] Thống nhất mapping và encoding cho custom headers.
- [ ] Chỉ đưa payload/metadata cần thiết sang application use case.
- [ ] Không sửa trực tiếp `MessageHeaders`.
- [ ] Chỉ dùng acknowledgment header khi container được cấu hình manual ack.
- [ ] Có integration test xác minh payload và metadata thực tế.

Nhận `Message<?>` giúp listener đọc payload cùng metadata trong một abstraction nhất quán của Spring. Khi hiểu rõ kiểu payload do deserializer/converter quyết định, sử dụng `KafkaHeaders` đúng cách và chỉ chuyển những thông tin cần thiết vào application layer, consumer sẽ dễ quan sát và bảo trì mà vẫn giữ ranh giới rõ ràng với Kafka client.
