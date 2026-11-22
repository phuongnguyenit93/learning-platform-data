# MessagingMessageConverter trong Spring Kafka

`MessagingMessageConverter` là bộ chuyển đổi ở tầng Spring Messaging, giúp kết nối Kafka record với `Message<?>`. Nó chuyển `ConsumerRecord` thành Spring Message khi consumer nhận dữ liệu và chuyển Spring Message thành `ProducerRecord` khi producer gửi dữ liệu bằng API message của `KafkaTemplate`.

Converter này giúp ứng dụng làm việc với payload và header theo mô hình `Message<?>`, thay vì phải tự đọc từng trường của `ConsumerRecord` hoặc tự dựng `ProducerRecord`. Cần phân biệt nó với Kafka serializer/deserializer: serializer và deserializer chịu trách nhiệm chuyển key/value giữa object và byte; message converter chịu trách nhiệm chuyển đổi ở tầng record và Spring Message.

## 1. MessagingMessageConverter nằm ở đâu?

Luồng Kafka có hai ranh giới chuyển đổi riêng:

- **Serialization:** Kafka producer chuyển key/value thành byte; consumer chuyển byte trở lại kiểu dữ liệu Java.
- **Message conversion:** Spring Kafka chuyển record thành Spring `Message<?>` hoặc chuyển Spring Message thành Kafka record.

`MessagingMessageConverter` triển khai `RecordMessageConverter`. Nó làm việc với toàn bộ record và các header, không thay thế `Serializer` hay `Deserializer` của Kafka client.

```mermaid
flowchart LR
    subgraph Producer
      A[Spring Message] --> B[MessagingMessageConverter]
      B --> C[ProducerRecord]
      C --> D[Kafka Serializer]
      D --> E[Kafka bytes]
    end
    subgraph Consumer
      F[Kafka bytes] --> G[Kafka Deserializer]
      G --> H[ConsumerRecord]
      H --> I[MessagingMessageConverter]
      I --> J[Spring Message]
      J --> K[@KafkaListener]
    end
```

Ví dụ: `JsonSerializer` chuyển `OrderCreated` thành JSON bytes. Khi consumer dùng `JsonDeserializer`, payload của `ConsumerRecord` đã là `OrderCreated`; `MessagingMessageConverter` tiếp tục bọc payload và metadata thành `Message<OrderCreated>` để listener nhận.

## 2. Phân biệt các thành phần chuyển đổi

| Thành phần | Đầu vào | Đầu ra | Trách nhiệm |
|---|---|---|---|
| Kafka `Serializer` | Key/value Java | `byte[]` | Mã hóa dữ liệu để gửi qua Kafka protocol |
| Kafka `Deserializer` | `byte[]` | Key/value Java | Giải mã dữ liệu nhận từ Kafka |
| `RecordMessageConverter` | `ConsumerRecord` hoặc Spring `Message<?>` | Spring `Message<?>` hoặc `ProducerRecord` | Chuyển đổi toàn bộ Kafka record và message |
| `MessagingMessageConverter` | Kafka record hoặc Spring Message | Spring Message hoặc Kafka record | Triển khai record conversion, gồm payload và header mapping |
| `SmartMessageConverter` | Payload trong Spring Message | Payload theo kiểu đích hoặc message đã chuyển đổi | Chuyển đổi payload ở tầng Spring Messaging khi được cấu hình |
| `HeaderMapper` | Kafka headers hoặc Spring headers | Spring headers hoặc Kafka headers | Ánh xạ metadata giữa hai hệ header |

Một lỗi thiết kế phổ biến là nghĩ `MessagingMessageConverter` tự biến JSON bytes thành POJO trong mọi trường hợp. Việc giải mã bytes trước hết thuộc về Kafka deserializer. Nếu deserializer trả `String`, record converter có thể bọc chuỗi đó thành Message; muốn chuyển chuỗi JSON thành POJO thì cần thêm payload converter phù hợp hoặc dùng `JsonDeserializer` ngay ở tầng Kafka.

## 3. Chuyển ConsumerRecord thành Spring Message

Ở chiều inbound, converter nhận `ConsumerRecord` do Kafka consumer trả về và tạo Spring Message. Payload thường lấy từ `record.value()` sau khi Kafka deserializer đã xử lý. Các metadata như topic, partition, offset, timestamp và key được đưa vào message headers.

Ví dụ listener nhận `Message<OrderCreated>`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(topics = "orders.created.v1", groupId = "order-projection")
    public void onOrder(Message<OrderCreated> message) {
        OrderCreated event = message.getPayload();

        String topic = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders()
                .get(KafkaHeaders.OFFSET, Long.class);

        // Xử lý event và metadata cần cho trace.
    }
}
```

Các header nhận thường dùng gồm:

| Header Spring Kafka | Ý nghĩa |
|---|---|
| `KafkaHeaders.RECEIVED_TOPIC` | Topic đã nhận record |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition của record |
| `KafkaHeaders.OFFSET` | Offset của record trong partition |
| `KafkaHeaders.RECEIVED_KEY` | Key đã deserialize của record |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp nhận từ record |
| `KafkaHeaders.TIMESTAMP_TYPE` | Loại timestamp của record |
| `KafkaHeaders.GROUP_ID` | Consumer group liên quan tới listener |

Các header bổ sung như acknowledgment hoặc consumer có thể được đưa vào Message tùy cấu hình và ngữ cảnh listener. Chỉ lấy những header cần thiết; không nên truyền toàn bộ đối tượng consumer hoặc acknowledgment qua nhiều tầng nghiệp vụ nếu không có lý do rõ ràng.

## 4. Nhận payload và metadata bằng @Payload, @Header

Nếu phương thức chỉ cần một số trường, có thể khai báo payload và header thành các tham số riêng thay vì nhận toàn bộ `Message<?>`:

```java
@KafkaListener(topics = "orders.created.v1", groupId = "order-projection")
public void onOrder(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    // Xử lý event với tọa độ Kafka.
}
```

Spring Kafka hỗ trợ resolve payload và header từ message được tạo bởi listener adapter. Cách này gọn khi listener chỉ cần một vài metadata.

Chọn cách nhận tham số theo nhu cầu:

- `OrderCreated`: chỉ cần dữ liệu nghiệp vụ.
- `Message<OrderCreated>`: cần nhiều message headers hoặc muốn truyền message envelope sang một thành phần khác.
- `ConsumerRecord<String, OrderCreated>`: cần API Kafka gốc, headers Kafka hoặc thông tin record đầy đủ.
- `@Payload` và `@Header`: muốn khai báo rõ từng giá trị listener sử dụng.

Không phải lúc nào cũng cần `MessagingMessageConverter` chỉ để đọc payload POJO. Nếu listener nhận trực tiếp payload và không cần Spring Message headers, kiểu tham số thông thường có thể đáp ứng nhu cầu.

## 5. Chuyển Spring Message thành ProducerRecord

Ở chiều outbound, `MessagingMessageConverter` đọc payload và các header điều khiển gửi record để tạo `ProducerRecord`. Những header quan trọng có thể gồm topic, partition, key và timestamp.

Ví dụ tạo message:

```java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

OrderCreated event = new OrderCreated("evt-1001", "order-42");

Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders.created.v1")
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .setHeader("event-source", "order-service")
        .build();
```

Sau đó gửi bằng `KafkaTemplate.send(Message<?>)`:

```java
kafkaTemplate.send(message)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                // Xử lý lỗi publish.
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            // Ghi nhận topic, partition và offset.
        });
```

`KafkaHeaders.TOPIC` xác định topic đích. `KafkaHeaders.MESSAGE_KEY` cung cấp key cho record. Có thể truyền thêm `KafkaHeaders.PARTITION` hoặc `KafkaHeaders.TIMESTAMP` khi cần chỉ định partition hoặc timestamp. Nếu không chỉ định partition, Kafka partitioner chọn partition theo key và cấu hình producer.

`send(Message<?>)` sử dụng message converter của `KafkaTemplate` để tạo record. Kafka producer vẫn cần serializer tương thích với kiểu key/value sau conversion.

## 6. Cấu hình MessagingMessageConverter cho listener container

Có thể gắn `MessagingMessageConverter` vào `ConcurrentKafkaListenerContainerFactory` bằng `setRecordMessageConverter`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordMessageConverter(new MessagingMessageConverter());
        return factory;
    }
}
```

Listener chọn factory này:

```java
@KafkaListener(
        topics = "orders.created.v1",
        groupId = "order-projection",
        containerFactory = "ordersListenerContainerFactory"
)
public void onOrder(Message<OrderCreated> message) {
    // Payload và headers đã được chuyển thành Spring Message.
}
```

Factory có thể được dùng cho nhiều listener. Nếu listener nhận trực tiếp `ConsumerRecord` hoặc payload mà không cần Spring Message, cần cân nhắc có thật sự cần custom record converter hay không.

## 7. Cấu hình converter cho KafkaTemplate

`KafkaTemplate` cũng có thể dùng một `RecordMessageConverter` để hỗ trợ API gửi Spring Message:

```java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> producerFactory) {

        var template = new KafkaTemplate<>(producerFactory);
        template.setMessageConverter(new MessagingMessageConverter());
        return template;
    }
}
```

Khi đó có thể gọi:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders.created.v1")
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .build();

orderKafkaTemplate.send(message);
```

Nếu ứng dụng dùng Spring Boot auto-configuration, có thể cấu hình `KafkaTemplate` qua bean tùy chỉnh hoặc cấu hình phù hợp phiên bản. Khi tự tạo template, bảo đảm `ProducerFactory` có key/value serializer đúng với kiểu record được gửi.

## 8. HeaderMapper và ánh xạ header

Kafka headers và Spring `MessageHeaders` không có cùng kiểu dữ liệu. Kafka header là cặp tên và byte array; Spring Message header có thể chứa String, số, object hoặc kiểu metadata khác. `MessagingMessageConverter` sử dụng `HeaderMapper` để ánh xạ giữa hai mô hình.

`DefaultKafkaHeaderMapper` là lựa chọn thường dùng khi cần ánh xạ nhiều kiểu header. Nó có thể chuyển đổi header object sang dạng biểu diễn phù hợp và mang metadata kiểu cho các header không phải byte/string đơn giản. Tùy chọn mapping pattern cho phép giới hạn header được chuyển qua.

Ví dụ một số header ứng dụng:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders.created.v1")
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .setHeader("event-source", "order-service")
        .setHeader("correlation-id", "corr-8f31")
        .build();
```

Header `event-source` và `correlation-id` là metadata ứng dụng. Header `KafkaHeaders.TOPIC` và `KafkaHeaders.MESSAGE_KEY` có ý nghĩa điều khiển việc tạo record. Converter xử lý các header theo vai trò của chúng khi tạo `ProducerRecord`.

Không đưa dữ liệu lớn hoặc object phức tạp không cần thiết vào header. Header cần nhỏ, ổn định và có schema/kiểu rõ ràng. Tránh truyền thông tin bí mật như access token, password hoặc dữ liệu cá nhân nhạy cảm trong header.

## 9. Tùy chỉnh HeaderMapper

Khi chỉ muốn truyền một nhóm header cụ thể, có thể cấu hình mapper tường minh và gắn vào `MessagingMessageConverter`:

```java
@Bean
public RecordMessageConverter orderRecordMessageConverter() {
    var headerMapper = new DefaultKafkaHeaderMapper();
    var converter = new MessagingMessageConverter(headerMapper);
    return converter;
}
```

Sau đó gắn converter vào listener factory hoặc `KafkaTemplate` như các ví dụ trước.

Trong hệ thống có yêu cầu bảo mật hoặc tương thích giữa nhiều ngôn ngữ, nên cấu hình header mapping theo allowlist/pattern phù hợp thay vì chuyển mọi header tùy ý. Tên constructor và phương thức cấu hình pattern của mapper có thể khác theo phiên bản Spring Kafka; hãy đối chiếu API đang dùng trước khi thêm bộ lọc.

Header mapper chỉ ánh xạ metadata. Nó không xác thực người gửi và cũng không bảo đảm giá trị header đúng nghiệp vụ. Consumer vẫn cần kiểm tra dữ liệu đầu vào.

## 10. Dùng SmartMessageConverter để chuyển payload

`MessagingMessageConverter` tập trung vào việc chuyển đổi record và Spring Message. Khi cần chuyển payload từ kiểu này sang kiểu khác, có thể gắn một `SmartMessageConverter` của Spring Messaging qua `setMessagingConverter(...)`.

Ví dụ, nếu consumer dùng `StringDeserializer` và nhận JSON dưới dạng chuỗi, một converter JSON của Spring có thể chuyển chuỗi payload thành DTO khi listener khai báo kiểu đích tương ứng. Cần đặt content type hoặc cấu hình converter phù hợp để nó biết cách diễn giải payload.

Khái niệm:

```text
Kafka bytes
   |
StringDeserializer
   v
String JSON
   |
MessagingMessageConverter
   v
Spring Message<String>
   |
SmartMessageConverter (nếu được cấu hình)
   v
Spring Message<OrderCreated>
```

Ví dụ minh họa cấu hình:

```java
var recordConverter = new MessagingMessageConverter();
recordConverter.setMessagingConverter(new MappingJackson2MessageConverter());
```

`MappingJackson2MessageConverter` thuộc Spring Messaging và cần được cấu hình đúng với content type/target type của ứng dụng. Tên API và khả năng hỗ trợ kiểu đích phụ thuộc phiên bản Spring Framework. Hãy kiểm thử với payload thực tế thay vì giả định mọi chuỗi JSON đều tự chuyển đổi.

Nếu consumer đã dùng Kafka `JsonDeserializer` để tạo `OrderCreated`, thường không cần thêm một JSON message converter để deserialize lần nữa. Chọn một tầng chịu trách nhiệm chuyển JSON thành object để tránh conversion lặp hoặc xung đột kiểu.

## 11. Chọn một chiến lược JSON rõ ràng

Hai cách triển khai thường gặp:

| Chiến lược | Consumer deserializer | Payload sau deserializer | Vai trò message converter |
|---|---|---|---|
| JSON ở tầng Kafka | `JsonDeserializer<OrderCreated>` | `OrderCreated` | Bọc record thành Spring Message và ánh xạ header |
| JSON ở tầng Spring Messaging | `StringDeserializer` | `String` | Có thể dùng `SmartMessageConverter` để chuyển JSON String thành DTO |

### Chiến lược A: Kafka JsonDeserializer

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.acme.orders.events.OrderCreated
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.acme.orders.events
```

Listener nhận `OrderCreated` hoặc `Message<OrderCreated>`. Message converter đảm nhiệm envelope và header mapping.

### Chiến lược B: StringDeserializer và payload conversion

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
```

Record converter nhận payload String; một `SmartMessageConverter` phù hợp có thể chuyển payload thành kiểu listener yêu cầu nếu content type và target type được cung cấp đúng. Cách này hữu ích khi ứng dụng muốn kiểm soát conversion tại tầng Spring Messaging hoặc cần xử lý nhiều định dạng payload.

Không cấu hình `JsonDeserializer` và đồng thời kỳ vọng `SmartMessageConverter` xử lý lại JSON bytes ban đầu. Khi dùng `JsonDeserializer`, converter phía trên nhận object đã deserialize, không còn JSON bytes gốc.

## 12. Xử lý null payload và tombstone

Trong Kafka, record có value `null` thường được dùng làm tombstone trong compacted topic. Đây là record có key nhưng không có value, mang ý nghĩa xóa key khỏi trạng thái compacted sau khi compaction diễn ra.

Spring Kafka cung cấp `KafkaNull` để biểu diễn null payload trong một số API message. Nếu listener nhận tombstone, cần thiết kế phương thức xử lý phù hợp với kiểu payload nullable hoặc nhận `ConsumerRecord` để kiểm tra `value() == null`.

Ví dụ:

```java
@KafkaListener(topics = "customer-state", groupId = "customer-projection")
public void onCustomerRecord(ConsumerRecord<String, CustomerState> record) {
    if (record.value() == null) {
        // Xử lý tombstone: xóa trạng thái theo key.
        return;
    }

    // Cập nhật trạng thái khách hàng.
}
```

Không coi mọi null payload là message lỗi. Trong compacted topic, tombstone có thể là một phần hợp lệ của contract dữ liệu. Hãy thống nhất ngữ nghĩa null giữa producer và consumer.

## 13. Batch listener và batch message conversion

`MessagingMessageConverter` là converter cho từng record. Khi listener nhận theo batch, Spring Kafka dùng cơ chế `BatchMessageConverter`, thường là `BatchMessagingMessageConverter`, để chuyển một danh sách `ConsumerRecord` thành một message batch.

Ví dụ listener nhận danh sách payload:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch",
        containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderCreated> events) {
    // Xử lý batch record.
}
```

Factory cần được cấu hình chế độ batch listener và batch message converter phù hợp. Không gắn `MessagingMessageConverter` cho từng record rồi giả định nó tự chuyển toàn bộ batch thành `List<Message<?>>`; hãy dùng `BatchMessageConverter` cho contract batch.

Khi batch listener cần metadata của từng record, có thể nhận danh sách `ConsumerRecord` hoặc cấu trúc batch message theo API Spring Kafka. Cần thiết kế xử lý lỗi một phần của batch và commit offset phù hợp.

## 14. Những lỗi thường gặp khi dùng MessagingMessageConverter

**Nhầm converter với deserializer:** converter nhận record sau khi Kafka deserializer đã xử lý key/value. Kiểm tra `key-deserializer` và `value-deserializer` trước.

**Payload không đúng kiểu listener mong đợi:** deserializer trả `String` nhưng listener nhận POJO. Dùng `JsonDeserializer` hoặc cấu hình `SmartMessageConverter` đúng target type.

**KafkaTemplate gửi message nhưng thiếu topic header:** `send(Message<?>)` cần biết topic từ `KafkaHeaders.TOPIC` hoặc cấu hình default topic phù hợp.

**Serializer không tương thích payload:** converter tạo `ProducerRecord` chứa POJO nhưng producer factory dùng `StringSerializer`. Chọn serializer phù hợp hoặc chuyển payload sang kiểu mà serializer hỗ trợ.

**Header không xuất hiện ở consumer:** kiểm tra `HeaderMapper`, pattern mapping và tên header. Không phải mọi Spring header đều tự động trở thành Kafka header.

**Đặt metadata Kafka vào sai header:** dùng `KafkaHeaders.MESSAGE_KEY`, `KafkaHeaders.PARTITION`, `KafkaHeaders.TIMESTAMP` và `KafkaHeaders.TOPIC` theo đúng mục đích outbound.

**Dùng JSON conversion hai lần:** `JsonDeserializer` đã tạo POJO nhưng SmartMessageConverter lại cố chuyển đổi payload như chuỗi. Chọn một tầng deserialize JSON.

**Dùng record converter cho batch listener:** batch listener cần `BatchMessageConverter` tương ứng.

**Tombstone bị coi là payload thông thường:** kiểm tra null value và contract compacted topic.

**Header object không tương thích giữa service:** chuẩn hóa kiểu header, dùng mapper có kiểm soát và tránh truyền object Java nội bộ làm contract liên dịch vụ.

## 15. Kiểm thử message conversion

Nên kiểm thử riêng hai chiều inbound và outbound:

- **Outbound:** Spring Message có topic/key/header đúng được chuyển thành ProducerRecord mong muốn.
- **Inbound:** ConsumerRecord có payload và Kafka headers được chuyển thành Spring Message với payload/header đúng.
- **Payload conversion:** String JSON chỉ chuyển thành POJO khi SmartMessageConverter và target type được cấu hình phù hợp.
- **Header mapping:** header được phép đi qua mapper; header không được phép không bị truyền ngoài ý muốn.
- **Serializer/deserializer:** kiểu dữ liệu trước và sau record converter tương thích với Kafka client.
- **Tombstone:** null payload được xử lý theo contract.
- **Batch:** dùng batch converter và xác minh metadata của từng record nếu cần.

Ví dụ integration test nên dùng `@EmbeddedKafka` hoặc Testcontainers để xác minh toàn bộ đường đi: `KafkaTemplate` gửi message, broker lưu record, consumer deserialize, converter tạo message và listener nhận payload. Unit test có thể mock `KafkaTemplate` hoặc kiểm tra converter trực tiếp, nhưng không chứng minh serializer/deserializer và broker hoạt động đúng.

Không nên chỉ assert listener đã được gọi. Hãy kiểm tra topic, key, payload và các header quan trọng. Nếu dùng `KafkaHeaders.OFFSET` hoặc partition trong xử lý, xác minh chúng đến từ record thật.

## 16. Checklist triển khai

- Đã phân biệt Kafka serializer/deserializer với `RecordMessageConverter`.
- Đã xác định listener cần payload trực tiếp, `Message<?>` hay `ConsumerRecord`.
- Listener factory dùng đúng `RecordMessageConverter` khi cần Spring Message conversion.
- `KafkaTemplate` dùng converter phù hợp khi gửi `Message<?>`.
- `KafkaHeaders.TOPIC` và key/partition/timestamp được đặt đúng cho outbound message.
- `HeaderMapper` chỉ truyền những header cần thiết và có contract rõ ràng.
- `SmartMessageConverter` chỉ được thêm khi thực sự cần chuyển payload giữa các kiểu.
- JSON chỉ được deserialize ở một tầng đã chọn và serializer/deserializer tương thích.
- Batch listener dùng `BatchMessageConverter`.
- Tombstone/null payload có ngữ nghĩa xử lý rõ ràng.
- Có integration test cho inbound, outbound, header mapping và payload conversion.
- Log/trace chỉ ghi metadata cần thiết, không ghi bí mật hoặc payload nhạy cảm.

`MessagingMessageConverter` kết nối Kafka record với mô hình `Message<?>` của Spring. Khi giữ ranh giới rõ giữa serializer/deserializer, record converter, payload converter và header mapper, ứng dụng có thể trao đổi event bằng Spring Messaging một cách nhất quán mà vẫn kiểm soát được kiểu dữ liệu, metadata và hành vi listener.
