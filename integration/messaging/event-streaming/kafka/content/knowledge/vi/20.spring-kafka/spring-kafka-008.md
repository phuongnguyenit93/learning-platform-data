# Message converter, JSON và bảo vệ deserialization

Kafka lưu key, value và headers dưới dạng bytes. Khi xây dựng ứng dụng Spring Kafka, dữ liệu có thể đi qua nhiều lớp chuyển đổi: Kafka `Serializer`/`Deserializer` làm việc ở ranh giới byte của Kafka client, còn Spring `RecordMessageConverter` chuyển đổi giữa `ProducerRecord`/`ConsumerRecord` và Spring `Message<?>` hoặc tham số của `@KafkaListener`.

Với JSON, cần chọn rõ nơi thực hiện việc parse: dùng `JsonSerializer`/`JsonDeserializer` để chuyển trực tiếp giữa POJO và bytes, hoặc dùng `StringDeserializer`/`ByteArrayDeserializer` kết hợp JSON message converter. Cấu hình không nhất quán dễ gây lỗi kiểu dữ liệu, mất header hoặc lỗi deserialization ngay trong `poll()`. Vì dữ liệu Kafka có thể đến từ nhiều producer và không phải lúc nào cũng đáng tin, consumer còn cần giới hạn type resolution, validate payload, xử lý record lỗi và bảo vệ dữ liệu gốc khi chuyển sang DLT.

## 1. Hai lớp chuyển đổi trong Spring Kafka

Kafka protocol không truyền Java object. Producer phải serialize key/value thành bytes trước khi gửi; consumer phải deserialize bytes sau khi fetch. Spring Kafka bổ sung message conversion để tích hợp với Spring Messaging và `@KafkaListener`.

| Thành phần | Thời điểm hoạt động | Đầu vào | Đầu ra |
|---|---|---|---|
| Kafka `Serializer` | Trước khi producer gửi record | Key/value Java object | `byte[]` |
| Kafka `Deserializer` | Khi consumer đọc record | `byte[]` | Key/value Java object |
| Spring `RecordMessageConverter` | Giữa Kafka record và Spring `Message<?>` | `ProducerRecord`/`ConsumerRecord` hoặc Spring message | Spring message/record đã ánh xạ |
| JSON message converter | Trong lớp Spring message conversion | JSON dạng `String`, `byte[]` hoặc `Bytes` | POJO/JSON payload và ngược lại |

Luồng producer khi gửi object bằng KafkaTemplate:

1. Ứng dụng tạo POJO hoặc Spring `Message<?>`.
2. Nếu gửi Spring `Message<?>`, `RecordMessageConverter` có thể lấy topic, key, partition, timestamp và headers để tạo `ProducerRecord`.
3. Kafka `Serializer` của `ProducerFactory` chuyển key/value thành bytes.
4. Kafka producer gửi record tới broker.

Luồng consumer:

1. Kafka consumer fetch record bytes từ broker.
2. Kafka `Deserializer` chuyển key/value bytes thành kiểu Java đã cấu hình.
3. Listener container dùng `RecordMessageConverter` để ánh xạ `ConsumerRecord` thành Spring message/đối số listener.
4. `@KafkaListener` nhận payload và headers theo chữ ký method.

```mermaid
flowchart TD
    A[Producer POJO / Spring Message] --> B[RecordMessageConverter]
    B --> C[Kafka Serializer]
    C --> D[Kafka broker: bytes]
    D --> E[Kafka Deserializer]
    E --> F[RecordMessageConverter]
    F --> G[@KafkaListener payload / headers]
```

Điểm cần nhớ: `RecordMessageConverter` không thay thế Kafka serializer/deserializer. Nếu dùng `JsonDeserializer`, payload đã được chuyển thành POJO trước khi listener container xử lý message. Nếu dùng `ByteArrayDeserializer` hoặc `StringDeserializer`, JSON converter có thể đảm nhận bước parse JSON ở lớp Spring.

## 2. Phân biệt `JsonDeserializer` và JSON message converter

Hai cách đều có thể đưa JSON thành POJO nhưng đặt trách nhiệm ở lớp khác nhau.

| Tiêu chí | `JsonSerializer`/`JsonDeserializer` | JSON `RecordMessageConverter` |
|---|---|---|
| Lớp chuyển đổi | Kafka client serialization | Spring Messaging conversion |
| Producer | POJO được serializer chuyển thành JSON bytes | Converter chuyển Spring message/payload thành record; serializer vẫn phải ghi bytes |
| Consumer | Deserializer parse bytes thành POJO trước listener | Consumer thường trả `String`/`byte[]`, converter parse thành POJO cho listener |
| Kiểu dữ liệu Kafka client | Có thể dùng `JsonDeserializer<OrderCreated>` | Thường dùng `StringDeserializer` hoặc `ByteArrayDeserializer` |
| Type metadata | Có thể dùng type headers của Spring JSON serializer/deserializer | Có thể suy luận kiểu từ method listener hoặc converter configuration |
| Phù hợp | Ứng dụng dùng DTO Java thống nhất và muốn deserialization ở client | Ứng dụng cần tận dụng Spring Message conversion hoặc muốn tách bytes khỏi DTO |

Không cấu hình cả `JsonDeserializer` và JSON converter với giả định cả hai đều phải parse cùng một JSON payload. Nếu deserializer đã trả về `OrderCreated`, converter không nên tiếp tục parse object đó như JSON bytes. Hãy chọn một đường đi rõ ràng và kiểm thử bằng record thật.

## 3. Khi nào dùng `MessagingMessageConverter`?

Spring Kafka có `MessagingMessageConverter` làm converter cơ bản giữa Kafka record và Spring `Message<?>`. Converter này ánh xạ payload và metadata như:

- Topic, partition, key và timestamp.
- Kafka headers và Spring message headers.
- Consumer metadata như topic, partition, offset, timestamp và consumer group theo các header tương ứng.

Converter cơ bản không tự động biến mọi JSON string thành POJO. Nếu consumer dùng `StringDeserializer`, listener có thể nhận `String`; muốn nhận DTO, cần JSON converter hoặc tự chuyển đổi trong ứng dụng.

Với `@KafkaListener`, có thể nhận trực tiếp `ConsumerRecord<K,V>` nếu cần truy cập đầy đủ metadata, hoặc nhận payload cùng các tham số `@Header` khi chỉ cần một số header.

```java
@KafkaListener(topics = "orders.events", groupId = "order-handler")
public void listen(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_KEY) String key,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    orderService.handle(event);
}
```

Ví dụ trên giả định consumer/deserializer hoặc message converter đã tạo được `OrderCreated`. Tên header và cách inject có thể khác theo Spring Kafka version; dùng các constant `KafkaHeaders` thay vì tự gõ chuỗi header để giảm lỗi chính tả.

## 4. Gửi JSON bằng `JsonSerializer` và `JsonDeserializer`

Đây là cách phổ biến khi producer và consumer đều là ứng dụng Java/Spring và đã thống nhất DTO.

### Producer configuration

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        "[spring.json.add.type.headers]": false
```

Producer gửi object:

```java
public record OrderCreated(
        String eventId,
        String orderId,
        long amount,
        String currency) {}

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send("orders.events", event.orderId(), event);
    }
}
```

`JsonSerializer` chuyển object thành JSON bytes. `spring.json.add.type.headers=false` tắt việc thêm Java type headers của Spring JSON serializer. Điều này hữu ích khi không muốn ràng buộc contract của event vào fully-qualified class name trong Java producer.

### Consumer configuration với một loại event cố định

```yaml
spring:
  kafka:
    consumer:
      group-id: order-handler
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.example.events.OrderCreated
        "[spring.json.trusted.packages]": com.example.events
        "[spring.json.use.type.headers]": false
```

Consumer dùng `OrderCreated` làm kiểu đích đã biết và không dựa vào type header do producer gửi. `trusted.packages` giới hạn package được phép dùng khi JSON deserializer cần resolve kiểu. Khi đã tắt type headers và dùng default type cố định, package allowlist vẫn nên được giới hạn thay vì dùng wildcard.

Đường đi này phù hợp khi topic chỉ chứa một loại event hoặc mỗi consumer biết rõ kiểu payload. Nếu một topic chứa nhiều loại event, cần một chiến lược type resolution rõ ràng thay vì để dữ liệu tự chọn bất kỳ Java class nào.

## 5. Type headers và type mapping

Spring JSON serializer có thể thêm type metadata vào Kafka headers, thường gồm các header như `__TypeId__`, `__KeyTypeId__` hoặc `__ContentTypeId__` tùy payload. Deserializer có thể dùng metadata này để xác định lớp Java cần tạo.

Type headers tiện lợi trong hệ sinh thái Java, nhưng tạo ra một số rủi ro và phụ thuộc:

- Producer và consumer bị gắn với tên class/package Java.
- Refactor package hoặc đổi class name có thể ảnh hưởng consumer cũ.
- Consumer có thể bị dẫn tới kiểu không mong muốn nếu tin metadata từ producer không đáng tin.
- Hệ thống viết bằng ngôn ngữ khác không biết cách diễn giải Java class name.

Nếu cần nhiều loại event trong một topic, Spring JSON hỗ trợ type mapping để dùng alias thay cho tên class đầy đủ. Ví dụ cấu hình khái niệm:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[spring.json.type.mapping]": orderCreated:com.example.events.OrderCreated,orderCancelled:com.example.events.OrderCancelled
    consumer:
      properties:
        "[spring.json.type.mapping]": orderCreated:com.example.events.OrderCreated,orderCancelled:com.example.events.OrderCancelled
        "[spring.json.trusted.packages]": com.example.events
        "[spring.json.use.type.headers]": true
```

Alias phải được thống nhất giữa producer và consumer. Mapping giúp giảm phụ thuộc vào tên class trên wire, nhưng vẫn là cơ chế của Spring JSON serializer/deserializer; nó không phải schema registry hay hợp đồng đa ngôn ngữ tự mô tả đầy đủ.

Nếu producer không kiểm soát được hoặc record đến từ nhiều nguồn, lựa chọn an toàn hơn thường là một envelope có `eventType` rõ ràng, registry/schema phù hợp và consumer dispatch qua danh sách loại đã cho phép. Không dùng class name tùy ý từ payload hoặc header để gọi `Class.forName()`.

## 6. Dùng JSON message converter với `StringDeserializer` hoặc `ByteArrayDeserializer`

Một lựa chọn khác là để Kafka client chỉ chuyển bytes thành `String`/`byte[]`, sau đó Spring converter parse JSON thành DTO. Spring Kafka cung cấp các converter JSON tương ứng với kiểu đầu vào như byte array, `Bytes` hoặc string; tên class cụ thể tùy phiên bản Spring Kafka.

Ví dụ cấu hình consumer dùng `ByteArrayDeserializer` và `ByteArrayJsonMessageConverter`:

```java
@Bean
RecordMessageConverter orderJsonMessageConverter() {
    return new ByteArrayJsonMessageConverter();
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, byte[]> orderKafkaListenerContainerFactory(
        ConsumerFactory<String, byte[]> consumerFactory,
        RecordMessageConverter orderJsonMessageConverter) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, byte[]>();
    factory.setConsumerFactory(consumerFactory);
    factory.setRecordMessageConverter(orderJsonMessageConverter);
    return factory;
}
```

Consumer factory cần dùng `StringDeserializer` cho key và `ByteArrayDeserializer` cho value. Listener có thể nhận DTO:

```java
@KafkaListener(
        topics = "orders.events",
        groupId = "order-handler",
        containerFactory = "orderKafkaListenerContainerFactory")
public void listen(OrderCreated event) {
    orderService.handle(event);
}
```

Converter sử dụng kiểu tham số listener để hỗ trợ chuyển JSON bytes thành `OrderCreated`. Nếu cần cấu hình `ObjectMapper`, custom module hoặc quy tắc property cụ thể, dùng constructor/API của converter phù hợp với Spring Kafka version đang chạy.

### Khi nào chọn `String` và khi nào chọn `byte[]`?

- `StringDeserializer` phù hợp khi ứng dụng cần xử lý JSON text trực tiếp, ghi log có kiểm soát hoặc dùng `StringJsonMessageConverter`.
- `ByteArrayDeserializer` giữ nguyên bytes gốc, hữu ích khi cần xác minh encoding, xử lý payload không phải UTF-8 hoặc chuyển raw bytes sang DLT.
- `JsonDeserializer` phù hợp khi muốn client deserialize trực tiếp thành DTO và có chiến lược type resolution rõ ràng.

Nếu payload có thể không phải UTF-8 hoặc cần giữ dữ liệu nguyên bản cho điều tra, `byte[]` thường linh hoạt hơn `String`.

## 7. Dùng JSON converter cho `KafkaTemplate` và Spring `Message<?>`

Khi gửi `Message<?>`, `KafkaTemplate` dùng `RecordMessageConverter` để lấy payload và Kafka metadata từ Spring headers. Ví dụ:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders.events")
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .setHeader("event-source", "order-service")
        .build();

kafkaTemplate.send(message);
```

Với cách gửi này, converter giúp ánh xạ `Message<?>` thành `ProducerRecord`. Serializer của producer factory vẫn chịu trách nhiệm serialize key/value thành bytes. Nếu converter tạo JSON bytes, cấu hình serializer phải tương ứng với kiểu bytes đó; nếu serializer là `JsonSerializer`, không serialize JSON bytes lần thứ hai như một object JSON thông thường.

Các header đặc biệt như topic, key, partition và timestamp cần dùng đúng constant `KafkaHeaders` của phiên bản Spring Kafka. Header nghiệp vụ tùy chỉnh nên có tên ổn định, kiểu đơn giản và không chứa secret.

## 8. Chọn kiểu payload và contract rõ ràng

Với topic chỉ có một event type, có thể dùng DTO cụ thể như `OrderCreated`. Với topic nhiều event type, có thể dùng envelope:

```java
public record EventEnvelope<T>(
        String eventId,
        String eventType,
        int eventVersion,
        Instant occurredAt,
        T data) {}
```

Ví dụ JSON:

```json
{
  "eventId": "evt-9012",
  "eventType": "OrderCreated",
  "eventVersion": 1,
  "occurredAt": "2026-11-20T09:15:00Z",
  "data": {
    "orderId": "ORD-2048",
    "amount": 1250000,
    "currency": "VND"
  }
}
```

Consumer đọc envelope, kiểm tra `eventType` trong allowlist rồi dispatch sang DTO handler tương ứng. Không dùng `eventType` làm tên class tùy ý; hãy ánh xạ alias đã đăng ký sang kiểu Java cố định.

Envelope giúp contract tách khỏi tên class, nhưng ứng dụng vẫn phải kiểm tra version, required field, nullability, đơn vị và quy tắc nghiệp vụ. Nếu nhiều ngôn ngữ cùng trao đổi event hoặc cần compatibility check tập trung, cân nhắc Avro/Protobuf/JSON Schema cùng Schema Registry.

## 9. Bảo vệ deserialization: không tin type metadata từ producer

Consumer có thể đọc record do nhiều producer tạo ra, record cũ được replay hoặc dữ liệu bị gửi nhầm topic. Vì vậy, type header và JSON payload phải được xem là input không đáng tin cho tới khi được xác thực.

Các nguyên tắc quan trọng:

- Ưu tiên target type cố định hoặc allowlist type rõ ràng.
- Giới hạn `spring.json.trusted.packages` vào package DTO cần thiết; tránh `*` trong production.
- Nếu topic có một loại event, cân nhắc `spring.json.use.type.headers=false` và cấu hình `spring.json.value.default.type`.
- Nếu có nhiều loại event, dùng alias mapping/allowlist thay vì cho phép class name tùy ý.
- Không bật Jackson default typing rộng cho payload Kafka không đáng tin.
- Không dùng `Class.forName()` trên `eventType`, type header hoặc field do producer kiểm soát.
- Dùng DTO chuyên biệt, không deserialize trực tiếp vào entity chứa method hoặc hành vi nhạy cảm.
- Giới hạn kích thước message, độ sâu JSON, số phần tử collection và độ dài string theo nhu cầu ứng dụng.
- Sau khi parse, vẫn phải validate dữ liệu và business invariant.

`trusted.packages` là một lớp giới hạn class resolution của Spring Kafka JSON deserializer, không thay thế authentication, ACL, schema validation, kiểm tra payload hay cập nhật thư viện Jackson. Không coi một package rộng như `com.example` là allowlist chặt nếu package đó chứa nhiều lớp không liên quan.

## 10. Type header không phải data contract đa ngôn ngữ

Nếu Java producer ghi `__TypeId__=com.example.events.OrderCreated`, một consumer Python/Go không có cùng Java classpath không thể dùng tên đó để deserialize tự động. Nó cần hợp đồng JSON/Avro/Protobuf được công bố độc lập.

Với hệ thống nhiều ngôn ngữ:

- Định nghĩa event schema trong repository/registry dùng chung.
- Dùng field `eventType`/version hoặc schema ID theo contract đã thống nhất.
- Không để package Java trở thành tên event công khai.
- Kiểm tra backward/forward compatibility trong CI.
- Giữ ví dụ payload và contract test cho consumer ở các ngôn ngữ.

Type headers có thể hữu ích trong nội bộ một hệ sinh thái Java được kiểm soát, nhưng không nên là tài liệu hợp đồng duy nhất của event.

## 11. Xử lý lỗi deserialization với `ErrorHandlingDeserializer`

Một lỗi xảy ra trước khi listener được gọi có thể làm poll thất bại. Ví dụ JSON không hợp lệ, enum không nhận diện, field sai kiểu hoặc payload bị cắt. Nếu dùng deserializer thông thường, exception có thể thoát ra từ quá trình `poll()` và container không có đủ thông tin để xử lý record theo cơ chế error handler như một lỗi listener bình thường.

Spring Kafka cung cấp `ErrorHandlingDeserializer` để bọc deserializer thực. Khi delegate deserialize thất bại, wrapper giữ thông tin exception và dữ liệu gốc trong header đặc biệt để container/error handler có thể xử lý.

Ví dụ cấu hình:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.events.OrderCreated
        "[spring.json.trusted.packages]": com.example.events
        "[spring.json.use.type.headers]": false
```

Ở đây cả key và value đều được bọc. Nếu chỉ value có khả năng lỗi deserialize, có thể bọc riêng value; nhưng cần quyết định rõ cách xử lý key lỗi vì key cũng có thể bị hỏng hoặc sai encoding.

Khi delegate thất bại, ứng dụng không nên coi payload `null` là event hợp lệ. Error handler cần kiểm tra deserialization exception header và chuyển record sang quy trình recover/DLT. Header chứa exception và raw data cần được bảo vệ vì có thể chứa payload nhạy cảm.

## 12. Chuyển record lỗi sang DLT và giữ raw bytes

Khi deserialization thất bại, consumer có thể chưa tạo được POJO. DLT cần giữ đủ thông tin để điều tra và replay, bao gồm raw key/value nếu có thể, topic/partition/offset nguồn, exception và event ID nếu trích xuất được an toàn.

Một điểm quan trọng là DLT producer có thể cần serialize cả hai loại value:

- `byte[]` gốc của record deserialize thất bại.
- POJO đã deserialize của record lỗi trong listener/business logic.

Nếu DLT template chỉ dùng `JsonSerializer`, raw `byte[]` có thể bị serialize thành JSON/base64 hoặc sai kiểu so với mong muốn. Hãy cấu hình serializer phù hợp, ví dụ serializer dispatch theo runtime type, hoặc dùng template riêng cho raw bytes và object đã deserialize. Kiểm tra hành vi thực tế của `DeadLetterPublishingRecoverer` và version Spring Kafka.

Ví dụ cấu hình error handler ở mức khái niệm:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(KafkaTemplate<Object, Object> dltTemplate) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    // DeserializationException thường được xem là fatal trong cấu hình mặc định
    // của một số phiên bản; xác minh danh sách exception và retry policy thực tế.
    return new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 2L));
}
```

Đây là ví dụ khung; DLT topic phải tồn tại hoặc được tạo theo policy, template phải serialize được key/value tương ứng và error handler phải được gắn vào listener container factory. Một số lỗi deserialization được mặc định phân loại non-retryable/fatal để chuyển thẳng tới recoverer; không giả định mọi lỗi đều retry hai lần. Kiểm tra danh sách fatal exception trong phiên bản Spring Kafka đang dùng.

Nếu publish DLT thất bại, không đánh dấu record nguồn đã recover thành công. Cần giám sát lỗi publish DLT và bảo đảm retry/recovery không làm mất raw payload.

## 13. Phân biệt lỗi deserialization, message conversion và validation

Các lỗi có thể xảy ra ở các giai đoạn khác nhau:

| Giai đoạn | Ví dụ | Cách xử lý |
|---|---|---|
| Kafka deserialization | JSON bytes không hợp lệ, type header không được chấp nhận | `ErrorHandlingDeserializer`, error handler, DLT |
| Spring message conversion | Payload có kiểu không phù hợp với tham số listener hoặc converter không chuyển được | Sửa converter/target type; phân loại lỗi và recover phù hợp |
| Bean validation | `amount` âm, `orderId` rỗng, field bắt buộc thiếu | Validate sau parse; thường không retry nếu dữ liệu sai vĩnh viễn |
| Business validation | Đơn hàng đã hủy, trạng thái không cho phép | Áp dụng business policy; có thể bỏ qua, reject hoặc phát event lỗi nghiệp vụ |
| Downstream processing | Database timeout, HTTP 503 | Retry có giới hạn nếu lỗi transient và side effect idempotent |

Không dùng retry mạng để chữa JSON sai cú pháp. Một payload hỏng sẽ tiếp tục hỏng sau 10 lần thử; cần chuyển sang DLT/quy trình sửa dữ liệu.

## 14. Validate DTO sau khi deserialize

Deserialization chỉ chứng minh bytes có thể được chuyển thành object theo quy tắc parser. Nó không chứng minh event hợp lệ về nghiệp vụ.

Có thể dùng Bean Validation:

```java
public record OrderCreated(
        @NotBlank String eventId,
        @NotBlank String orderId,
        @Positive long amount,
        @NotBlank String currency) {}
```

Trong listener:

```java
@KafkaListener(topics = "orders.events", groupId = "order-handler")
public void listen(@Valid @Payload OrderCreated event) {
    orderService.handle(event);
}
```

Việc tự động kích hoạt Bean Validation trên listener payload phụ thuộc cách tích hợp method validation và phiên bản Spring; nếu không được kích hoạt tự động, gọi `Validator` hoặc một validation service rõ ràng trong listener/service. Khi validation thất bại, phân loại lỗi là non-retryable trừ khi có điều kiện cụ thể cho thấy dữ liệu sẽ trở nên hợp lệ sau đó.

## 15. Headers, type information và dữ liệu nhạy cảm

Type headers là metadata, nhưng vẫn được lưu cùng Kafka record. Không đưa secret, token xác thực hoặc dữ liệu cá nhân vào header. Tránh ghi toàn bộ headers ra log vì chúng có thể chứa:

- `__TypeId__` hoặc alias nội bộ tiết lộ package/class structure.
- Correlation ID, tenant ID hoặc customer reference.
- Metadata routing và retry.
- Header exception có raw bytes hoặc stack trace.

Khi chuyển record sang DLT, kiểm tra header được sao chép, loại bỏ hoặc bổ sung như thế nào. Redact dữ liệu nhạy cảm theo policy, nhưng giữ lại metadata đủ để truy nguyên topic/partition/offset và event ID. Hạn chế quyền đọc DLT tương đương hoặc chặt hơn topic nguồn nếu DLT chứa raw payload lỗi.

## 16. Cấu hình `ObjectMapper` và giới hạn parser

Nếu ứng dụng cần custom `ObjectMapper`, hãy cấu hình module và naming strategy một cách nhất quán giữa producer và consumer. Tránh bật polymorphic default typing rộng cho JSON nhận từ Kafka.

Các kiểm soát nên cân nhắc:

- Chỉ đăng ký module cần thiết (Java Time, datatype module theo DTO).
- Không bật default typing toàn cục để tự tạo mọi subtype từ metadata trong payload.
- Dùng subtype allowlist nếu polymorphism là yêu cầu thực sự.
- Cấu hình giới hạn độ sâu nesting, độ dài string, số phần tử và kích thước message theo parser/runtime hỗ trợ.
- Xử lý unknown fields theo chiến lược tương thích đã chọn: bỏ qua, giữ lại hoặc từ chối có chủ đích.
- Không cho phép parser tự truy cập URL, file hoặc class tùy ý từ payload.
- Cập nhật Jackson và thư viện liên quan để nhận bản vá bảo mật.

Không nên cấu hình `FAIL_ON_UNKNOWN_PROPERTIES=false` một cách mặc định cho mọi DTO mà không có contract test. Bỏ qua field mới có thể giúp forward compatibility trong một số tình huống, nhưng cũng có thể che giấu lỗi producer gửi sai schema. Chọn policy theo loại event và yêu cầu tương thích.

## 17. Cấu hình theo phiên bản Spring Kafka

Tên class converter, constructor, setter, default type header và cách bind property có thể thay đổi giữa các thế hệ Spring Kafka/Jackson. Khi triển khai:

1. Xác định phiên bản Spring Boot, Spring Kafka, Kafka client và Jackson thực tế.
2. Dùng serializer/deserializer và converter thuộc cùng hệ phiên bản được hỗ trợ.
3. Kiểm tra property metadata/autoconfiguration của đúng Spring Boot version.
4. Không trộn Jackson 2 và Jackson 3 types trong cùng converter/serializer nếu artifact không hỗ trợ.
5. Chạy contract test với record được tạo bởi phiên bản producer cũ và mới.
6. Kiểm thử khi Registry/type metadata không sẵn sàng nếu luồng có dependency tương ứng.

Đặc biệt, các ví dụ `ByteArrayJsonMessageConverter`, `JsonDeserializer` và `ErrorHandlingDeserializer` cần dependency `spring-kafka` phù hợp. Nếu IDE không tìm thấy class hoặc setter, hãy xác minh version API thay vì thay bằng class có tên gần giống.

## 18. Test deserialization và message conversion

Một bộ kiểm thử hữu ích nên bao gồm:

- JSON hợp lệ với đầy đủ field.
- JSON hợp lệ nhưng thiếu optional field.
- JSON có field mới mà consumer cũ chưa biết.
- JSON sai cú pháp hoặc bị cắt giữa chừng.
- Field sai kiểu, ví dụ `amount` là object thay vì số.
- Type header không được cho phép hoặc alias không tồn tại.
- Event type không nằm trong allowlist.
- Payload quá lớn hoặc nesting quá sâu.
- Key deserialize lỗi.
- Registry/schema dependency không truy cập được nếu sử dụng.
- DLT giữ đúng raw bytes, original topic/partition/offset và exception metadata.
- Consumer không commit offset khi record chưa được recover an toàn.

Với Spring Kafka, có thể dùng `spring-kafka-test` và `EmbeddedKafka` hoặc Kafka container test phù hợp với dự án. Test converter riêng với `RecordMessageConverter` cũng hữu ích, nhưng cần ít nhất một integration test để xác minh serializer, broker record, deserializer, listener và DLT phối hợp đúng.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Listener nhận `String` thay vì POJO | Dùng `StringDeserializer` nhưng chưa cấu hình JSON converter | Cấu hình JSON `RecordMessageConverter` hoặc dùng `JsonDeserializer` |
| JSON bị parse hai lần hoặc lỗi kiểu | Vừa dùng `JsonDeserializer` vừa cấu hình converter parse bytes | Chọn một tầng thực hiện JSON deserialization |
| `No type information in headers` hoặc không xác định được target type | Tắt type headers nhưng không đặt default type hoặc listener type | Cấu hình default type cố định hoặc type mapping rõ ràng |
| `ClassNotFoundException` khi đọc record | Producer gửi Java class name mà consumer không có class/package tương ứng | Dùng alias mapping, DTO contract chung hoặc schema đa ngôn ngữ |
| `The class ... is not in the trusted packages` | Type header chỉ tới package chưa được allowlist | Xác minh producer/type header; chỉ thêm package cụ thể nếu tin cậy |
| Consumer có thể deserialize class ngoài mong muốn | Trusted packages quá rộng hoặc bật polymorphic typing không giới hạn | Thu hẹp allowlist, tắt type headers nếu không cần và dùng fixed target type |
| Deserialization exception làm container dừng | Dùng deserializer thường, không có error-handling wrapper hoặc error handler phù hợp | Cấu hình `ErrorHandlingDeserializer` và recoverer |
| DLT value bị đổi thành JSON/base64 thay vì raw bytes | DLT serializer không hỗ trợ đồng thời byte[] và object | Dùng serializer dispatch theo type hoặc template riêng, kiểm thử raw payload |
| DLT publish thất bại | Topic/ACL/serializer không đúng | Kiểm tra DLT topology, quyền ghi, serializer và không đánh dấu recover thành công |
| JSON parse thành công nhưng nghiệp vụ sai | Thiếu Bean Validation hoặc semantic validation | Validate field, đơn vị, version và business invariant sau parse |
| Consumer cũ không đọc được event mới | Schema/type/field evolution không theo compatibility plan | Expand-contract, contract test và rollout consumer trước producer |

## 20. Checklist production

**Chọn đường chuyển đổi:**

- Xác định serializer/deserializer của Kafka client.
- Xác định `RecordMessageConverter` có tham gia hay không.
- Không parse JSON hai lần.
- Dùng kiểu payload cụ thể cho từng topic/listener khi có thể.
- Nếu gửi Spring `Message<?>`, ánh xạ topic/key/partition/timestamp bằng Kafka headers đúng constant.

**Bảo vệ type và payload:**

- Tắt type headers nếu topic có một target type cố định và không cần metadata Java.
- Nếu dùng type headers, dùng alias mapping và allowlist.
- Giới hạn `trusted.packages`; không dùng `*` trong production.
- Không bật Jackson default typing rộng cho payload không đáng tin.
- Validate DTO và business rule sau deserialization.
- Giới hạn kích thước/độ sâu payload và cập nhật thư viện parser.

**Xử lý lỗi:**

- Dùng `ErrorHandlingDeserializer` khi cần error handler xử lý lỗi xảy ra trong poll.
- Phân loại deserialization/validation lỗi vĩnh viễn và lỗi downstream transient.
- Cấu hình DLT serializer giữ được raw `byte[]` và object đã deserialize.
- Bảo đảm publish DLT thành công trước khi xem record đã recover.
- Giữ original topic, partition, offset, event ID và exception metadata cần thiết.
- Không log payload/header nhạy cảm.

**Kiểm thử và vận hành:**

- Kiểm thử payload hợp lệ, malformed, unknown type, missing field và payload quá lớn.
- Kiểm thử record cũ/mới qua schema/type evolution.
- Kiểm tra DLT raw bytes và offset commit behavior.
- Theo dõi deserialization error, conversion error, validation failure và DLT rate.
- Xác minh cấu hình theo đúng Spring Boot/Spring Kafka/Jackson version.

## 21. Ghi nhớ

Kafka `Serializer`/`Deserializer` chuyển key/value giữa Java object và bytes ở ranh giới Kafka client. Spring `RecordMessageConverter` chuyển đổi giữa Kafka record và Spring `Message<?>`/listener payload. Dùng `JsonDeserializer` khi muốn client parse JSON thành DTO; dùng JSON message converter khi consumer nhận `String`/`byte[]` và muốn Spring conversion thực hiện parse. Không cấu hình hai lớp cùng parse một payload.

Type headers và trusted packages cần được giới hạn vì producer không phải nguồn metadata luôn đáng tin. Với topic một loại event, dùng target type cố định và có thể tắt type headers; với nhiều loại event, dùng alias/allowlist hoặc envelope/schema rõ ràng. `ErrorHandlingDeserializer` giúp đưa lỗi phát sinh trong poll vào cơ chế xử lý lỗi của Spring Kafka; DLT cần giữ raw bytes và metadata nguồn. Cuối cùng, deserialize thành công không đồng nghĩa event hợp lệ: vẫn phải validate schema, dữ liệu và business invariant trước khi thực hiện side effect.
