# MessageConverter cho JSON

## 1. MessageConverter giải quyết việc gì?

Kafka chỉ lưu key và value dưới dạng byte. Ở phía ứng dụng, dữ liệu thường là object Java như `OrderCreatedEvent`. Để trao đổi dữ liệu, producer phải biến object thành định dạng có thể truyền đi và consumer phải chuyển dữ liệu nhận được về kiểu mà listener sử dụng.

Trong Spring Kafka, `MessageConverter` giúp kết nối mô hình `Message<?>` của Spring Messaging với record của Kafka. Converter có thể chuyển payload object thành JSON dạng `String` hoặc `byte[]` khi gửi, rồi chuyển JSON nhận được thành object Java khi listener xử lý.

Ví dụ, ứng dụng muốn gửi một object:

~~~java
import java.time.Instant;

OrderCreatedEvent event = new OrderCreatedEvent(
    "evt-1001",
    "ORD-1001",
    "CUS-42",
    Instant.parse("2025-01-01T10:00:00Z")
);
~~~

Listener muốn nhận trực tiếp object:

~~~java
@KafkaListener(topics = "orders")
public void handle(OrderCreatedEvent event) {
    orderService.apply(event);
}
~~~

`MessageConverter` đảm nhiệm bước chuyển đổi ở ranh giới Spring Messaging/Kafka để mã nghiệp vụ không phải tự gọi Jackson trong mỗi listener hoặc publisher.

Luồng khái quát:

~~~mermaid
flowchart LR
    A["Java object"] --> B["Spring Message<?>"]
    B --> C["RecordMessageConverter"]
    C --> D["Kafka ProducerRecord"]
    D --> E["Kafka serializer"]
    E --> F["Kafka topic: bytes"]
    F --> G["Kafka deserializer"]
    G --> H["ConsumerRecord"]
    H --> I["RecordMessageConverter"]
    I --> J["Spring Message / listener payload"]
    J --> K["Java object"]
~~~

Converter không thay thế hoàn toàn Kafka serializer/deserializer. Hai cơ chế phối hợp với nhau và phải được cấu hình tương thích.

## 2. Phân biệt Serializer/Deserializer và MessageConverter

Đây là điểm quan trọng nhất khi chọn cách chuyển JSON.

| Thành phần | Làm việc ở đâu? | Nhiệm vụ |
|---|---|---|
| `Serializer<K/V>` | Kafka producer client | Chuyển key/value thành byte trước khi ghi |
| `Deserializer<K/V>` | Kafka consumer client | Chuyển byte thành kiểu key/value mà consumer nhận |
| `RecordMessageConverter` | Spring Kafka | Chuyển giữa Spring `Message<?>` và Kafka `ProducerRecord`/`ConsumerRecord` |
| `BatchMessageConverter` | Spring Kafka batch listener | Chuyển đổi dữ liệu cho listener nhận một batch |

Có hai hướng phổ biến để đưa JSON vào/ra Kafka.

**Hướng A — Dùng JsonSerializer/JsonDeserializer**

- Producer truyền object Java trực tiếp vào `KafkaTemplate`.
- `JsonSerializer` chuyển object thành JSON bytes.
- Consumer dùng `JsonDeserializer` để tạo object Java trước khi listener nhận record.
- Không cần JSON `MessageConverter` nếu listener chỉ nhận object đã deserialize.

**Hướng B — Dùng StringJsonMessageConverter**

- `KafkaTemplate.send(Message<?>)` nhận Spring Message có payload là object.
- `StringJsonMessageConverter` chuyển object thành JSON `String`.
- `StringSerializer` chuyển chuỗi JSON thành bytes.
- Consumer dùng `StringDeserializer` nhận lại JSON `String`.
- `StringJsonMessageConverter` chuyển JSON thành object theo kiểu listener yêu cầu.

Bảng so sánh:

| Tiêu chí | JsonSerializer/JsonDeserializer | StringJsonMessageConverter |
|---|---|---|
| Lớp chuyển object thành JSON | Kafka serializer | Spring Kafka message converter |
| Kiểu value giữa converter và Kafka client | JSON bytes | JSON `String` |
| Serializer/deserializer | `JsonSerializer` / `JsonDeserializer` | `StringSerializer` / `StringDeserializer` |
| Gửi bằng `KafkaTemplate` | Có thể dùng `send(topic, key, object)` | Dùng `send(Message<?>)` để converter tham gia |
| Listener nhận object | Deserializer tạo object trước listener | Converter tạo object từ JSON string |
| Phù hợp | Luồng Kafka trực tiếp theo kiểu Java | Tích hợp Spring Messaging và header |

Không nên cấu hình cả hai lớp cùng cố chuyển một JSON payload theo những cách không tương thích. Ví dụ, nếu converter đã tạo JSON String thì producer value serializer phải là `StringSerializer`, không phải `JsonSerializer` đang chờ một object nghiệp vụ.

## 3. Các JSON MessageConverter thường dùng

Spring Kafka cung cấp các converter dựa trên Jackson để làm việc với những kiểu payload khác nhau:

| Converter | Kiểu payload trung gian | Serializer/deserializer tương ứng |
|---|---|---|
| `StringJsonMessageConverter` | `String` chứa JSON | `StringSerializer` / `StringDeserializer` |
| `ByteArrayJsonMessageConverter` | `byte[]` chứa JSON | `ByteArraySerializer` / `ByteArrayDeserializer` |
| `BytesJsonMessageConverter` | Kafka `Bytes` chứa JSON | `BytesSerializer` / `BytesDeserializer` |

Các converter này thường được tạo với `ObjectMapper` của Jackson. Dùng converter String khi cần JSON văn bản dễ quan sát; dùng byte array khi hợp đồng vận chuyển yêu cầu value là byte; dùng `Bytes` khi ứng dụng đang làm việc với kiểu Kafka `Bytes`.

Ví dụ dưới đây sử dụng `StringJsonMessageConverter`, `StringSerializer` và `StringDeserializer`. Đây là một cấu hình dễ đọc khi học cách chuyển đổi JSON qua Spring Messaging.

Tên lớp và constructor có thể thay đổi giữa các major version Spring Kafka. Hãy dùng API tương ứng với phiên bản dependency của dự án; các ví dụ cấu hình trong bài minh họa API Spring Kafka 3.x phổ biến.

## 4. Cấu hình StringJsonMessageConverter trong Spring Boot

Khi dùng converter String, producer và consumer đều làm việc với JSON dưới dạng `String` ở tầng Kafka client:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all

    consumer:
      group-id: order-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest

    listener:
      type: single
      ack-mode: record
~~~

Các thuộc tính serializer/deserializer là `StringSerializer` và `StringDeserializer` vì converter sẽ chuyển payload object thành JSON String trước khi gửi và chuyển JSON String thành object khi listener nhận.

Khai báo converter dùng chung `ObjectMapper` do Spring Boot quản lý:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.converter.RecordMessageConverter;
import org.springframework.kafka.support.converter.StringJsonMessageConverter;

@Configuration
public class KafkaMessageConversionConfiguration {

    @Bean
    RecordMessageConverter jsonRecordMessageConverter(
            ObjectMapper objectMapper) {
        return new StringJsonMessageConverter(objectMapper);
    }
}
~~~

Dùng `ObjectMapper` được inject giúp converter dùng chung cấu hình Jackson của ứng dụng, ví dụ Java Time module, naming strategy hoặc serializer/deserializer tùy chỉnh. Nếu tạo một `ObjectMapper` hoàn toàn riêng, hãy bảo đảm cấu hình của nó tương thích với dữ liệu mà các producer và consumer khác đang trao đổi.

## 5. Gắn converter vào KafkaTemplate để gửi JSON

`KafkaTemplate` hỗ trợ gửi Spring `Message<?>`. Khi gọi overload `send(Message<?>)`, template dùng `RecordMessageConverter` để chuyển Spring Message thành Kafka `ProducerRecord`.

Có thể khai báo template riêng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.converter.RecordMessageConverter;

@Configuration
public class KafkaTemplateConfiguration {

    @Bean
    KafkaTemplate<String, String> jsonKafkaTemplate(
            ProducerFactory<String, String> producerFactory,
            RecordMessageConverter jsonRecordMessageConverter) {

        var template = new KafkaTemplate<>(producerFactory);
        template.setMessageConverter(jsonRecordMessageConverter);
        return template;
    }
}
~~~

Generic của template là `KafkaTemplate<String, String>` vì sau bước chuyển đổi, value được gửi đến Kafka client là JSON String. Producer factory phải dùng `StringSerializer` cho value.

Tạo Spring Message từ object:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public void publish(OrderCreatedEvent event, String correlationId) {
    Message<OrderCreatedEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders")
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .setHeader("correlation-id", correlationId)
        .build();

    jsonKafkaTemplate.send(message);
}
~~~

Ở đây:

- Payload là `OrderCreatedEvent`.
- `KafkaHeaders.TOPIC` xác định topic đích.
- `KafkaHeaders.KEY` đặt key cho record Kafka.
- `correlation-id` là header tùy chỉnh để liên kết log giữa các dịch vụ.
- Converter serialize payload object thành JSON String trước khi template gửi record.

Nếu cần kiểm tra kết quả gửi, có thể quan sát `CompletableFuture` trả về:

~~~java
jsonKafkaTemplate.send(message)
    .whenComplete((result, error) -> {
        if (error != null) {
            log.error("Không gửi được OrderCreated", error);
            return;
        }

        var metadata = result.getRecordMetadata();
        log.info(
            "Đã gửi topic={} partition={} offset={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    });
~~~

Future thành công cho biết producer đã nhận xác nhận theo cấu hình `acks`. Nó không chứng minh consumer đã xử lý xong sự kiện.

**Lưu ý:** overload `send(topic, key, value)` không phải đường gửi Spring `Message<?>`, vì vậy không tự động gọi converter được gắn cho `send(Message<?>)`. Nếu gọi overload này với `KafkaTemplate<String, String>`, value cần là JSON String. Nếu muốn truyền object trực tiếp bằng overload topic/key/value, hãy dùng `JsonSerializer` hoặc tự chuyển object thành JSON trước.

## 6. Gắn converter vào listener container để nhận JSON

Ở phía consumer, deserializer lấy JSON String từ Kafka. Listener container dùng `RecordMessageConverter` để chuyển JSON thành kiểu object mà phương thức listener khai báo.

Khai báo listener container factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.converter.RecordMessageConverter;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    RecordMessageConverter jsonRecordMessageConverter) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setRecordMessageConverter(jsonRecordMessageConverter);
        return factory;
    }
}
~~~

Listener có thể nhận trực tiếp object:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final OrderProjectionService orderProjectionService;

    public OrderCreatedListener(
            OrderProjectionService orderProjectionService) {
        this.orderProjectionService = orderProjectionService;
    }

    @KafkaListener(
        topics = "orders",
        groupId = "order-projection",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void handle(OrderCreatedEvent event) {
        orderProjectionService.apply(event);
    }
}
~~~

Container factory phải dùng `ConsumerFactory<String, String>` vì consumer deserializer trả JSON String. Converter sau đó mới tạo `OrderCreatedEvent` để listener nhận.

Có thể nhận thêm metadata qua annotation:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.Payload;
import org.springframework.kafka.annotation.Header;
import org.springframework.kafka.support.KafkaHeaders;

@KafkaListener(
    topics = "orders",
    groupId = "order-projection",
    containerFactory = "kafkaListenerContainerFactory"
)
public void handle(
        @Payload OrderCreatedEvent event,
        @Header(KafkaHeaders.RECEIVED_KEY) String key,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(name = "correlation-id", required = false) String correlationId) {

    orderProjectionService.apply(event, key, topic, correlationId);
}
~~~

Các header nhận vào có thể gồm key, topic, partition, offset và metadata tùy chỉnh. Dùng `@Payload` cho dữ liệu nghiệp vụ và `@Header` cho metadata giúp chữ ký listener thể hiện rõ trách nhiệm của từng tham số.

## 7. ObjectMapper và định dạng JSON

`StringJsonMessageConverter` dựa trên Jackson để chuyển object thành JSON và ngược lại. Vì vậy, `ObjectMapper` cần hiểu cấu trúc object của producer và consumer.

Ví dụ event:

~~~java
import java.time.Instant;

public record OrderCreatedEvent(
    String eventId,
    String orderId,
    String customerId,
    Instant createdAt
) {}
~~~

Nếu payload có `Instant`, `LocalDate`, `LocalDateTime` hoặc các kiểu ngày giờ Java khác, `ObjectMapper` cần module Java Time phù hợp. Spring Boot thường tự cấu hình mapper với các module có trên classpath. Nếu tự tạo mapper, có thể đăng ký `JavaTimeModule`:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper objectMapper = new ObjectMapper()
    .registerModule(new JavaTimeModule());
~~~

Không nên dùng `new ObjectMapper()` riêng trong từng publisher hoặc listener. Cách đó dễ tạo khác biệt về date format, naming strategy, null handling và custom serializer giữa các thành phần.

Hợp đồng JSON nên quy định rõ:

- Tên field và kiểu dữ liệu.
- Format ngày giờ, timezone và độ chính xác.
- Field bắt buộc, field có thể thiếu và giá trị mặc định.
- Quy tắc tương thích khi thêm hoặc đổi field.
- Phiên bản event và cách xử lý consumer chưa hỗ trợ phiên bản mới.

JSON là định dạng văn bản, nhưng không tự giải quyết schema evolution. Nếu hệ thống cần kiểm soát schema chặt chẽ hoặc tương thích nhiều ngôn ngữ, hãy cân nhắc JSON Schema, Avro hoặc Protobuf cùng quy trình quản lý schema.

## 8. Type headers và lựa chọn kiểu đích

JSON chỉ chứa dữ liệu, không tự mang kiểu Java. Khi chuyển JSON thành object, converter phải biết kiểu đích. Spring Kafka có thể suy luận kiểu từ tham số listener và có thể sử dụng type metadata trong Kafka headers tùy cấu hình type mapper.

Ví dụ listener khai báo rõ kiểu:

~~~java
@KafkaListener(topics = "orders", groupId = "order-projection")
public void handle(OrderCreatedEvent event) {
    orderProjectionService.apply(event);
}
~~~

Kiểu `OrderCreatedEvent` là thông tin đích rõ ràng để converter tạo object. Với listener nhận kiểu interface, abstract class hoặc `Object`, converter có thể cần metadata kiểu hoặc cấu hình type mapping bổ sung.

Một số nguyên tắc:

- Ưu tiên kiểu tham số cụ thể khi listener chỉ xử lý một loại event.
- Nếu sử dụng type headers, thống nhất cách producer tạo và consumer đọc headers.
- Với nhiều ngôn ngữ, tránh phụ thuộc vào tên class Java làm hợp đồng công khai.
- Chỉ tin các package/type đã được cho phép nếu cấu hình deserialization có cơ chế trusted packages.
- Không bật wildcard trusted packages cho dữ liệu từ nguồn không đáng tin nếu không có đánh giá bảo mật.

Type headers giúp chọn kiểu đích nhưng không thay thế versioning của event. Một class Java đổi package hoặc tên có thể làm consumer cũ không đọc được metadata kiểu nếu hệ thống phụ thuộc trực tiếp vào tên class.

## 9. Header mapping và metadata của Spring Message

Spring Message có payload và headers. `RecordMessageConverter` ánh xạ headers phù hợp sang Kafka record headers khi gửi và chuyển headers nhận được sang Spring Message ở phía listener.

Một số header thường dùng:

| Header | Hướng sử dụng | Ý nghĩa |
|---|---|---|
| `KafkaHeaders.TOPIC` | Gửi | Topic đích |
| `KafkaHeaders.KEY` | Gửi | Kafka record key |
| `KafkaHeaders.PARTITION` | Gửi | Partition đích nếu muốn chỉ định |
| `KafkaHeaders.RECEIVED_TOPIC` | Nhận | Topic chứa record |
| `KafkaHeaders.RECEIVED_KEY` | Nhận | Key của record |
| `KafkaHeaders.RECEIVED_PARTITION` | Nhận | Partition nhận được |
| `KafkaHeaders.OFFSET` | Nhận | Offset của record |
| `correlation-id` | Gửi/nhận | Metadata tùy chỉnh của ứng dụng |

Không nên đưa dữ liệu nghiệp vụ quan trọng chỉ vào header nếu consumer cần nó để xử lý khi payload được lưu hoặc chuyển tiếp độc lập. Những dữ liệu đó nên nằm trong payload hoặc trong một hợp đồng sự kiện được mô tả rõ.

Header Kafka là byte array ở tầng broker. Converter có thể ánh xạ một số kiểu header Spring sang giá trị phù hợp, nhưng các header tùy chỉnh nên dùng kiểu đơn giản và thống nhất, chẳng hạn String, byte array hoặc số có quy tắc chuyển đổi rõ ràng.

## 10. Xử lý lỗi chuyển đổi JSON

Lỗi chuyển đổi có thể xảy ra ở hai giai đoạn khác nhau:

| Giai đoạn | Ví dụ | Cách quan sát |
|---|---|---|
| Kafka deserialization | Byte không hợp lệ hoặc deserializer không đọc được | Xảy ra khi consumer poll; thường cần `ErrorHandlingDeserializer` để đưa lỗi vào cơ chế xử lý của Spring Kafka |
| Message conversion | JSON String không hợp lệ hoặc không ánh xạ được sang kiểu listener | Xảy ra ở listener adapter/converter; error handler của container có thể xử lý |
| Validation nghiệp vụ | JSON hợp lệ nhưng thiếu dữ liệu bắt buộc theo quy tắc nghiệp vụ | Xử lý bằng validation hoặc exception nghiệp vụ trong listener/service |

Nếu dùng `StringDeserializer`, Kafka client chỉ chuyển bytes thành String. JSON parse diễn ra ở `StringJsonMessageConverter`; lỗi này xảy ra trong đường xử lý listener và có thể được error handler xử lý theo cấu hình.

Nếu dùng `JsonDeserializer` thay cho `StringJsonMessageConverter`, JSON parse xảy ra trong Kafka deserializer trước khi listener nhận record. Khi đó, nên cân nhắc `ErrorHandlingDeserializer` để Spring Kafka có thể chuyển lỗi deserialization cho error handler và áp dụng retry/recovery phù hợp.

Ví dụ cấu hình consumer theo hướng `JsonDeserializer` được bọc bởi `ErrorHandlingDeserializer` (đây là một chiến lược thay thế, không phải phần cần thêm vào cấu hình String converter ở trên):

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderCreatedEvent
        spring.json.trusted.packages: com.example.events
~~~

Trong cấu hình này, `ErrorHandlingDeserializer` bọc `JsonDeserializer` để lỗi chuyển JSON thành object có thể được chuyển tới cơ chế xử lý lỗi của Spring Kafka. Nếu dùng `StringJsonMessageConverter`, JSON parse vẫn xảy ra ở listener adapter/converter và không cần cấu hình `JsonDeserializer` cho cùng value.

Hãy phân biệt lỗi định dạng JSON, lỗi type mapping và lỗi validation nghiệp vụ. Không retry vô hạn một payload sai định dạng vì cùng một record sẽ tiếp tục thất bại. Có thể dùng `DefaultErrorHandler`, backoff có giới hạn và dead-letter publishing cho record không thể xử lý theo chính sách consumer.

## 11. Batch listener và MessageConverter

Nếu listener nhận nhiều record trong một lần gọi, cần cấu hình batch mode và batch message converter phù hợp. `RecordMessageConverter` phục vụ chuyển đổi record đơn; batch listener sử dụng `BatchMessageConverter` để chuyển đổi danh sách record thành dạng mà phương thức listener nhận.

Ví dụ tạo batch converter từ record converter:

~~~java
import org.springframework.kafka.support.converter.BatchMessagingMessageConverter;
import org.springframework.kafka.support.converter.RecordMessageConverter;

@Bean
BatchMessagingMessageConverter batchMessageConverter(
        RecordMessageConverter jsonRecordMessageConverter) {
    return new BatchMessagingMessageConverter(
        jsonRecordMessageConverter
    );
}
~~~

Gắn converter vào container factory batch theo API của phiên bản Spring Kafka đang dùng, đồng thời bật batch listener. Listener có thể nhận `List<OrderCreatedEvent>` hoặc danh sách `Message<?>` tùy cách cấu hình converter và chữ ký phương thức.

Ví dụ factory batch:

~~~java
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.converter.BatchMessageConverter;

@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
        batchKafkaListenerContainerFactory(
                ConsumerFactory<String, String> consumerFactory,
                BatchMessageConverter batchMessageConverter) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setBatchMessageConverter(batchMessageConverter);
    return factory;
}
~~~

Listener sử dụng factory này có thể nhận danh sách payload đã chuyển đổi:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-projection",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void handleBatch(List<OrderCreatedEvent> events) {
    orderProjectionService.applyBatch(events);
}
~~~


Không dùng một cấu hình batch converter cho record listener nếu factory và chữ ký listener không tương thích. Hãy kiểm thử cả batch có một record, batch có nhiều record và lỗi chuyển đổi ở một phần tử.

## 12. Kiểm thử MessageConverter

Nên kiểm thử riêng ba phần: JSON mapping, đường gửi và đường nhận.

**Unit test converter:** kiểm tra object được chuyển thành JSON hợp lệ và JSON được chuyển về đúng kiểu object. Kiểm tra field ngày giờ, null, enum, nested object và field không tương thích.

**Test publisher:** gửi `Message<?>` qua `KafkaTemplate`, xác minh topic, key, header và JSON value. Nếu mock template, cần xác minh converter đã được cấu hình hoặc kiểm tra riêng kết quả chuyển đổi.

**Integration test:** dùng Embedded Kafka hoặc Testcontainers, gửi một Spring Message có payload object, rồi xác minh listener nhận đúng object và metadata. Dùng timeout có giới hạn thay vì `Thread.sleep()` cố định.

Các tình huống nên kiểm thử:

- JSON hợp lệ và ánh xạ đúng kiểu listener.
- JSON sai cú pháp.
- Thiếu field bắt buộc hoặc kiểu field không tương thích.
- Header type/version thiếu hoặc không hỗ trợ.
- Header correlation ID được giữ nguyên.
- Producer/consumer cấu hình serializer không khớp.
- Nhiều phiên bản event cùng được consumer xử lý theo hợp đồng.

Ví dụ kiểm tra JSON mapping với converter:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.kafka.support.converter.StringJsonMessageConverter;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class JsonMessageConverterTest {

    private final StringJsonMessageConverter converter =
        new StringJsonMessageConverter();

    record TestEvent(String eventId, String orderId) {}

    @Test
    void convertsSpringMessageToKafkaRecordAndBack() {
        var event = new TestEvent("evt-1", "ORD-1");
        Message<TestEvent> outbound = MessageBuilder
            .withPayload(event)
            .setHeader(KafkaHeaders.TOPIC, "orders")
            .setHeader(KafkaHeaders.KEY, "ORD-1")
            .build();

        ProducerRecord<?, ?> kafkaRecord = converter.fromMessage(outbound, null);

        assertThat(kafkaRecord.topic()).isEqualTo("orders");
        assertThat(kafkaRecord.key()).isEqualTo("ORD-1");
        assertThat(kafkaRecord.value()).isInstanceOf(String.class);

        String json = (String) kafkaRecord.value();
        ConsumerRecord<String, String> inbound =
            new ConsumerRecord<>("orders", 0, 0L, "ORD-1", json);

        Message<?> converted = converter.toMessage(
            inbound, null, null, TestEvent.class
        );

        assertThat(converted.getPayload()).isEqualTo(event);
    }
}
~~~

Đây là unit test trực tiếp hai chiều chuyển đổi của `RecordMessageConverter`: Spring Message thành Kafka ProducerRecord và ConsumerRecord thành Spring Message với kiểu payload đích. Integration test qua `KafkaTemplate.send(Message<?>)` và `@KafkaListener` vẫn cần thiết để xác minh serializer, deserializer, container factory và broker cùng hoạt động đúng.

## 13. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Producer báo lỗi kiểu dữ liệu | Converter tạo String nhưng producer dùng serializer cho object khác | Dùng `StringSerializer` với `StringJsonMessageConverter` |
| Listener nhận String thay vì object | Listener factory chưa gắn converter hoặc dùng deserializer/kiểu không phù hợp | Gắn `RecordMessageConverter` vào đúng container factory |
| JSON parse thất bại | Payload sai cú pháp hoặc khác hợp đồng | Kiểm tra JSON, version và cấu hình Jackson |
| Không tìm thấy kiểu đích | Listener nhận `Object` hoặc interface và thiếu type mapping | Dùng kiểu tham số cụ thể hoặc cấu hình type mapper |
| Header bị thiếu | Header không được thêm vào Spring Message hoặc không được map | Kiểm tra header name, kiểu dữ liệu và converter |
| `send(topic, key, object)` không gọi converter | Overload này gửi value trực tiếp qua serializer | Dùng `send(Message<?>)` hoặc JsonSerializer |
| Một số listener convert được, listener khác không | Các listener dùng container factory khác nhau | Gắn converter vào đúng factory được tham chiếu trong `@KafkaListener` |

Khi điều tra, kiểm tra lần lượt kiểu payload trước khi gửi, overload `KafkaTemplate` được gọi, converter được gắn ở template/container factory, serializer/deserializer thực tế và kiểu tham số listener.

## 14. Khi nào nên dùng MessageConverter cho JSON?

Dùng `MessageConverter` khi ứng dụng làm việc nhiều với Spring `Message<?>`, cần ánh xạ payload và headers, hoặc muốn listener nhận trực tiếp object từ JSON String/byte array mà không tự gọi Jackson.

Dùng `JsonSerializer`/`JsonDeserializer` khi muốn Kafka client chịu trách nhiệm chuyển object sang JSON bytes và ứng dụng gửi trực tiếp bằng các overload `KafkaTemplate` thông thường.

Dù chọn cách nào, producer và consumer phải thống nhất JSON contract, kiểu dữ liệu, headers, versioning và chính sách xử lý lỗi. Không để serializer và converter cùng chuyển đổi một payload theo hai hợp đồng khác nhau.

Checklist triển khai:

- [ ] Xác định dùng `JsonSerializer`/`JsonDeserializer` hay `MessageConverter`.
- [ ] Nếu dùng `StringJsonMessageConverter`, cấu hình `StringSerializer` và `StringDeserializer`.
- [ ] Gắn converter vào `KafkaTemplate` cho luồng `send(Message<?>)`.
- [ ] Gắn converter vào đúng listener container factory.
- [ ] Dùng kiểu tham số listener cụ thể khi có thể.
- [ ] Thống nhất `ObjectMapper`, date/time format và JSON contract.
- [ ] Quản lý type headers và trusted packages có chủ đích.
- [ ] Phân biệt lỗi Kafka deserialization, message conversion và validation.
- [ ] Kiểm thử JSON hợp lệ, JSON sai, header và event version.
- [ ] Không nhầm `send(topic, key, value)` với `send(Message<?>)`.

`MessageConverter` giúp Spring Kafka nối mô hình message của Spring với record Kafka và chuyển JSON thành object mà listener có thể xử lý. Cấu hình đúng converter cùng serializer/deserializer tương thích sẽ giúp mã ứng dụng rõ ràng, tận dụng được headers và giảm việc chuyển đổi dữ liệu thủ công trong từng publisher hoặc listener.
