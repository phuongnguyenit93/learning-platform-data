# Khi nào nên dùng converter thay vì serializer

Trong Spring Kafka, serializer và message converter đều có thể tham gia chuyển đổi dữ liệu, nhưng chúng làm việc ở hai tầng khác nhau. **Kafka `Serializer`/`Deserializer` chịu trách nhiệm biến key/value thành byte và đọc byte trở lại. Spring `RecordMessageConverter` chuyển đổi giữa Kafka record và Spring `Message<?>`, đồng thời có thể chuyển payload theo kiểu listener yêu cầu.**

Vì vậy, câu hỏi không phải là chọn một trong hai thành phần để thay thế hoàn toàn thành phần còn lại. Kafka producer vẫn cần serializer để ghi byte xuống broker và consumer vẫn cần deserializer để đọc byte. Converter chỉ nên được thêm khi ứng dụng cần chức năng chuyển đổi ở tầng Spring Messaging, chẳng hạn làm việc với `Message<?>`, mapping headers, `Content-Type` hoặc chuyển JSON string thành DTO.

## 1. Hai tầng chuyển đổi khác nhau

Luồng outbound khi gửi Spring `Message<?>`:

```text
Spring Message<OrderCreatedEvent>
          |
          v
RecordMessageConverter
          |
          v
ProducerRecord<String, String>
          |
          v
StringSerializer
          |
          v
Kafka bytes
```

Luồng inbound khi dùng JSON message converter:

```text
Kafka bytes
    |
    v
StringDeserializer
    |
    v
ConsumerRecord<String, String>
    |
    v
StringJacksonJsonMessageConverter
    |
    v
Spring Message<OrderCreatedEvent>
    |
    v
@KafkaListener
```

Ở đây serializer/deserializer làm việc tại ranh giới Kafka protocol. Converter làm việc sau khi Kafka client đã tạo `ProducerRecord` hoặc `ConsumerRecord`, và có thể ánh xạ payload cùng metadata sang abstraction của Spring.

Nếu dùng `JsonSerializer`/`JsonDeserializer`, luồng đơn giản hơn:

```text
Producer DTO -> JsonSerializer -> Kafka bytes
Kafka bytes -> JsonDeserializer -> Consumer DTO
```

Listener có thể nhận DTO trực tiếp mà không cần JSON message converter. Converter mặc định vẫn có thể được listener adapter dùng để ánh xạ record và headers khi phương thức nhận `Message<T>`.

## 2. Bảng so sánh nhanh

| Tiêu chí | Kafka Serializer/Deserializer | Spring RecordMessageConverter |
| --- | --- | --- |
| Tầng hoạt động | Kafka client, ranh giới byte | Spring Messaging, giữa Kafka record và Spring message |
| Đầu vào/đầu ra | Java key/value ↔ `byte[]` | `ConsumerRecord` ↔ `Message<?>`; `Message<?>` ↔ `ProducerRecord` |
| Có bắt buộc không? | Có, producer/consumer phải có cơ chế serialize/deserialize | Không bắt buộc; dùng khi cần chuyển đổi ở tầng Spring |
| Phạm vi sử dụng | Mọi Kafka client, kể cả ứng dụng không dùng Spring | Ứng dụng Spring Kafka |
| Hợp đồng dữ liệu | Quy định format byte thực sự được ghi lên Kafka | Quy định cách Spring biểu diễn payload và metadata |
| Ví dụ | `StringSerializer`, `JsonSerializer`, Avro/Protobuf serializer | `MessagingMessageConverter`, `StringJacksonJsonMessageConverter` |
| Metadata | Thường tập trung vào key/value; Kafka headers được quản lý riêng | Ánh xạ Spring `MessageHeaders` và Kafka headers |

Một converter có thể chuyển DTO thành JSON `String`, nhưng Kafka vẫn cần `StringSerializer` để chuyển string đó thành byte. Tương tự, converter inbound có thể chuyển JSON string thành DTO, nhưng Kafka consumer trước đó vẫn cần `StringDeserializer` để tạo string từ byte.

## 3. Khi nào nên dùng serializer/deserializer trực tiếp?

Ưu tiên serializer/deserializer khi format byte là hợp đồng chính của hệ thống và ứng dụng không cần chuyển đổi bổ sung ở tầng Spring Messaging.

Các tình huống thường gặp:

- Producer gửi DTO và consumer nhận DTO cùng loại bằng `JsonSerializer`/`JsonDeserializer`.
- Nhiều ứng dụng viết bằng Java, Go, Python hoặc .NET cần dùng chung một wire format.
- Hệ thống dùng Avro, Protobuf hoặc schema registry để quản lý schema và compatibility.
- Payload là `String`, `byte[]` hoặc kiểu đơn giản đã có serializer tương ứng.
- Ứng dụng chỉ cần tham số payload trong `@KafkaListener`, không cần `Message<?>` hoặc header mapping tùy chỉnh.
- Muốn lỗi serialize/deserialize xuất hiện rõ tại Kafka client boundary và được xử lý bằng cơ chế Kafka serializer/deserializer hoặc error handler tương ứng.

Ví dụ cấu hình JSON trực tiếp:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.example.events.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.example.events
```

Producer gửi object trực tiếp:

```java
KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

public void publish(OrderCreatedEvent event) {
    kafkaTemplate.send("orders.created", event.orderId(), event);
}
```

Consumer nhận DTO:

```java
@KafkaListener(topics = "orders.created", groupId = "order-projection")
public void onMessage(OrderCreatedEvent event) {
    // Xử lý DTO đã được JsonDeserializer tạo.
}
```

Ở ví dụ này, `JsonSerializer` chịu trách nhiệm tạo JSON bytes và `JsonDeserializer` chịu trách nhiệm tạo DTO. Thêm một JSON message converter nữa thường chỉ làm tăng số bước chuyển đổi và nguy cơ parse/serialize lặp.

## 4. Khi nào nên dùng RecordMessageConverter?

Dùng converter khi ứng dụng cần một lớp chuyển đổi gắn với Spring Messaging hoặc cần điều chỉnh payload theo ngữ cảnh listener.

**Trường hợp 1: Ứng dụng dùng Spring `Message<?>`.**

Service đã xây dựng message bằng `MessageBuilder`, mang payload và headers như topic, key, correlation ID hoặc content type. `KafkaTemplate.send(Message<?>)` dùng converter để chuyển message đó thành `ProducerRecord`.

**Trường hợp 2: Payload Kafka là String hoặc byte nhưng listener cần DTO.**

Producer/consumer dùng serializer/deserializer đơn giản, ví dụ `StringSerializer`/`StringDeserializer`. Converter JSON chuyển object thành string khi gửi và chuyển string thành DTO khi nhận.

**Trường hợp 3: Cần ánh xạ metadata và headers.**

Listener cần `Message<T>` chứa payload cùng topic, partition, offset, key, correlation ID hoặc header nghiệp vụ. `MessagingMessageConverter` và header mapper cung cấp lớp ánh xạ này.

**Trường hợp 4: Chuyển đổi phụ thuộc Content-Type hoặc kiểu tham số listener.**

Ứng dụng nhận nhiều kiểu payload, dùng `SmartMessageConverter` hoặc JSON converter để chọn cách chuyển đổi theo media type và kiểu đích của phương thức listener.

**Trường hợp 5: Tích hợp API Spring Messaging hiện có.**

Nếu các thành phần trong ứng dụng đã trao đổi `Message<?>`, converter giúp kết nối Kafka với mô hình message đó mà không buộc service phải thao tác trực tiếp với `ProducerRecord` và `ConsumerRecord`.

## 5. Ví dụ: cùng một DTO, hai cách cấu hình

Giả sử ứng dụng trao đổi event:

```java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total) {
}
```

### Cách A — JSON serializer/deserializer

```yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.example.events.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.example.events
```

Producer gửi `OrderCreatedEvent`; consumer nhận `OrderCreatedEvent`. Đây là lựa chọn gọn khi payload JSON là hợp đồng và listener chỉ cần DTO.

### Cách B — String serializer/deserializer và JSON message converter

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
```

Với Spring Kafka 4.x, tạo converter:

```java
@Bean
RecordMessageConverter recordMessageConverter() {
    return new StringJacksonJsonMessageConverter();
}
```

Gắn converter vào listener container factory:

```java
factory.setRecordMessageConverter(recordMessageConverter);
```

Gắn converter vào `KafkaTemplate` nếu gửi Spring `Message<?>`:

```java
kafkaTemplate.setMessageConverter(recordMessageConverter);
```

Giờ producer có thể gửi object trong Spring message:

```java
Message<OrderCreatedEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders.created")
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .build();

kafkaTemplate.send(message);
```

Converter chuyển payload DTO thành JSON string; `StringSerializer` biến string thành bytes. Ở chiều nhận, `StringDeserializer` tạo string; converter chuyển string thành DTO dựa trên kiểu listener yêu cầu.

Tên converter phụ thuộc phiên bản: Spring Kafka 4.x dùng `StringJacksonJsonMessageConverter` (Jackson 3); Spring Kafka 3.x trở xuống dùng `StringJsonMessageConverter` (Jackson 2). Không trộn lớp converter của hai thế hệ Jackson.

## 6. Khi nào kết hợp cả serializer và converter?

Trong hầu hết ứng dụng Spring Kafka, hai tầng này cùng tồn tại. Một cấu hình có thể dùng:

- `StringSerializer` để ghi key.
- `StringSerializer` hoặc `JsonSerializer` để ghi value.
- `StringDeserializer` hoặc `JsonDeserializer` để đọc value.
- `MessagingMessageConverter` mặc định để ánh xạ Kafka record thành Spring `Message<?>`.
- JSON `RecordMessageConverter` nếu payload vẫn là String/bytes nhưng Spring listener cần DTO.

Ví dụ, ứng dụng dùng Avro serializer để tạo bytes Avro. Khi consumer đã dùng Avro deserializer để tạo `OrderCreatedEvent`, converter mặc định có thể bọc object đó cùng metadata thành `Message<OrderCreatedEvent>`. Converter JSON không cần tham gia.

Một nguyên tắc hữu ích: **serializer/deserializer quyết định bytes trên Kafka; converter quyết định cách Spring adapter biểu diễn và chuyển payload/metadata cho ứng dụng.**

## 7. API nào thực sự kích hoạt message converter?

Không phải mọi phương thức của KafkaTemplate đều dùng converter.

| API | Converter có được gọi? | Ghi chú |
| --- | --- | --- |
| `KafkaTemplate.send(topic, key, value)` | Không | Key/value đi thẳng qua Kafka serializer |
| `KafkaTemplate.send(ProducerRecord)` | Không | ProducerRecord đã được tạo; producer serializer xử lý bytes |
| `KafkaTemplate.send(Message<?>)` | Có | Template chuyển Spring Message thành ProducerRecord |
| Listener nhận payload qua container | Có bước record-to-message | Container dùng `RecordMessageConverter`; converter tùy chỉnh có thể chuyển payload |
| Listener nhận `ConsumerRecord<K,V>` | Không cần payload conversion cho tham số record | Ứng dụng nhận trực tiếp Kafka record |

Vì vậy, nếu đã cấu hình converter nhưng gọi `send(topic, key, value)`, đừng mong converter tự chuyển DTO thành JSON. Hãy dùng serializer tương ứng hoặc gửi `Message<?>` qua overload hỗ trợ converter.

## 8. Trade-off khi thêm converter

Converter tạo thêm khả năng tích hợp, nhưng cũng thêm một tầng cấu hình và chuyển đổi.

| Khía cạnh | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| Spring Messaging | Dùng `Message<?>` và headers nhất quán | Phụ thuộc abstraction và API Spring Kafka |
| Payload conversion | Chuyển String/bytes thành DTO theo listener | Tốn CPU, cấp phát object và có thể parse JSON thêm một lần |
| Header mapping | Truyền correlation ID, content type và metadata | Cần kiểm soát allowlist, encoding và kiểu header |
| Nhiều kiểu payload | Có thể chọn converter theo content type/target type | Cấu hình phức tạp, lỗi type resolution khó truy vết hơn |
| Tương thích hệ thống | Có thể giữ wire format đơn giản như String/bytes | Cần đồng bộ converter và serializer ở mọi producer/consumer |

Với payload lớn hoặc thông lượng cao, đo CPU, allocation và latency trước khi đưa thêm bước chuyển đổi. Nếu chỉ cần DTO JSON, `JsonSerializer`/`JsonDeserializer` thường đơn giản hơn.

## 9. Chọn theo loại dữ liệu và kiến trúc

| Tình huống | Khuyến nghị |
| --- | --- |
| Một topic JSON, producer/consumer Spring cùng DTO | `JsonSerializer`/`JsonDeserializer` |
| Topic JSON được nhiều ngôn ngữ tiêu thụ | Chọn JSON wire format ổn định; serializer/deserializer theo ngôn ngữ thường là ranh giới chính |
| Service đã dùng `Message<?>` và cần map headers | `RecordMessageConverter` |
| Kafka value là String JSON nhưng listener cần nhiều DTO khác nhau | JSON message converter hoặc `SmartMessageConverter` theo target type/content type |
| Avro/Protobuf với schema registry | Serializer/deserializer chuyên dụng; converter chỉ bổ sung nếu cần Spring Message abstraction |
| Raw bytes, file chunk hoặc binary protocol | Byte-array serializer/deserializer; converter tùy nhu cầu đóng gói metadata |
| Listener cần `topic`, `partition`, `offset`, `key` | `Message<T>` cùng converter mặc định hoặc `ConsumerRecord<K,V>` |
| Chỉ gửi DTO qua `KafkaTemplate.send(topic,key,value)` | Serializer trực tiếp |

Không chọn converter chỉ vì tên gọi nghe tổng quát hơn. Chọn nó khi cần chức năng ở tầng Spring Messaging mà serializer/deserializer không giải quyết.

## 10. Những điều converter không làm thay serializer

Converter không thay đổi yêu cầu cơ bản của Kafka producer/consumer:

- Producer vẫn phải có serializer cho key/value.
- Consumer vẫn phải có deserializer cho key/value.
- Converter không tự cấu hình partitioner, compression, `acks`, retry hoặc transaction.
- Converter không thay thế schema registry hay tự bảo đảm schema compatibility.
- Converter không biến Kafka headers thành nơi lưu payload lớn hoặc secret.
- Converter không bảo đảm exactly-once hoặc idempotency cho nghiệp vụ.

Nếu serializer/deserializer không khớp với kiểu dữ liệu converter tạo ra, lỗi vẫn xảy ra ở Kafka client. Ví dụ converter tạo `String` nhưng producer factory dùng serializer chỉ chấp nhận DTO khác kiểu.

## 11. Kiểm thử khi chọn converter

Khi thêm converter, nên kiểm thử cả bước chuyển đổi lẫn đường gửi/nhận thật.

1. **Converter unit test:** kiểm tra payload DTO thành String/bytes và ngược lại; xác minh null, malformed payload và type mismatch.
2. **Header mapping test:** kiểm tra topic, key, partition, timestamp, correlation ID và custom header được chuyển đúng.
3. **Template test:** xác minh `send(Message<?>)` đi qua converter và tạo đúng `ProducerRecord`; đồng thời xác nhận `send(topic,key,value)` dùng serializer trực tiếp.
4. **Listener integration test:** gửi record bằng broker kiểm thử và xác minh kiểu payload cuối cùng listener nhận được.
5. **Compatibility test:** dùng payload do producer khác ngôn ngữ hoặc phiên bản tạo ra để xác minh wire contract.

Với JSON converter, kiểm tra cả trường hợp producer có/không có `Content-Type`, type header không hợp lệ, field mới và payload cũ. Nếu converter dùng Jackson, kiểm tra module ngày giờ và chính sách unknown properties theo hợp đồng event.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đã cấu hình converter nhưng `send(topic,key,value)` vẫn lỗi serialize | API đó không gọi message converter | Dùng serializer đúng kiểu hoặc `send(Message<?>)` |
| Listener nhận String thay vì DTO | Deserializer trả String và chưa có JSON converter | Cấu hình JSON `RecordMessageConverter` hoặc dùng `JsonDeserializer` |
| JSON bị chuyển đổi hai lần | Vừa dùng `JsonDeserializer` tạo DTO vừa dùng JSON converter parse tiếp | Chỉ định một tầng chịu trách nhiệm JSON payload |
| `Message<?>` gửi đi thiếu topic | Thiếu `KafkaHeaders.TOPIC` và default topic | Đặt topic header hoặc default topic |
| Custom header bị mất | Header mapper không map header hoặc encoding sai | Cấu hình mapper và kiểm thử từng header |
| Producer và consumer không thống nhất kiểu value | Converter tạo String nhưng serializer/deserializer dùng kiểu khác | Đồng bộ generic type và Kafka client configuration |
| Dùng converter Jackson 2 trên Spring Kafka 4.x | Sai thế hệ converter/dependency | Dùng lớp Jackson 3 tương ứng hoặc giữ stack Spring Kafka 3.x đồng bộ |

## 13. Kết luận

Hãy dùng Kafka serializer/deserializer để định nghĩa cách key/value được ghi thành byte và đọc lại từ Kafka. Dùng Spring `RecordMessageConverter` khi cần chuyển Kafka record sang Spring `Message<?>`, ánh xạ headers, chuyển JSON string/bytes thành DTO theo kiểu listener hoặc tích hợp với API Spring Messaging.

Nếu producer và consumer chỉ trao đổi DTO JSON, `JsonSerializer`/`JsonDeserializer` thường là lựa chọn trực tiếp và ít cấu hình. Nếu ứng dụng cần `Message<?>`, content type, header mapping hoặc muốn giữ Kafka client ở kiểu String/bytes rồi chuyển payload ở tầng Spring, converter mang lại giá trị rõ ràng. Trong cả hai trường hợp, serializer/deserializer vẫn chịu trách nhiệm cuối cùng ở ranh giới byte của Kafka.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring for Apache Kafka — Serialization, Deserialization and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html#serdes-json-config)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Apache Kafka — Serializer API](https://kafka.apache.org/documentation/#producerapi)
