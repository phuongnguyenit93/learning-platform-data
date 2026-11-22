# RecordMessageConverter

Kafka lưu key và value dưới dạng byte array, trong khi ứng dụng Spring thường làm việc với DTO, object và `Message<?>`. `RecordMessageConverter` là cầu nối giữa hai mô hình này ở tầng Spring Messaging: nó chuyển Kafka record thành Spring `Message` khi consumer nhận dữ liệu, và chuyển Spring `Message` thành Kafka `ProducerRecord` khi producer gửi message.

Điểm quan trọng là `RecordMessageConverter` không thay thế Kafka `Serializer`/`Deserializer`. Serializer và deserializer chịu trách nhiệm chuyển kiểu Java sang byte và ngược lại ở Kafka client. Message converter tổ chức payload cùng metadata thành abstraction của Spring, đồng thời có thể chuyển đổi payload như JSON khi được cấu hình phù hợp.

## 1. RecordMessageConverter nằm ở đâu?

Spring Kafka kết hợp API Kafka client với Spring Messaging. Ở phía nhận, Kafka consumer trả `ConsumerRecord`; listener adapter có thể dùng converter để tạo `Message<?>` rồi gọi phương thức `@KafkaListener`. Ở phía gửi, `KafkaTemplate.send(Message<?>)` dùng converter để tạo `ProducerRecord` trước khi giao cho Kafka producer.

```text
Consumer side
Kafka broker
    |
    v
KafkaConsumer
    |
    v
ConsumerRecord<K, V>
    |
    v
RecordMessageConverter
    |
    v
Spring Message<?>
    |
    v
@KafkaListener

Producer side
Spring Message<?>
    |
    v
KafkaTemplate.send(Message<?>)
    |
    v
RecordMessageConverter
    |
    v
ProducerRecord<K, V>
    |
    v
KafkaProducer + Serializer
    |
    v
Kafka broker
```

Converter có thể tham gia cả hai chiều, nhưng chỉ khi ứng dụng dùng API tương ứng. Ví dụ `KafkaTemplate.send(topic, key, value)` gửi trực tiếp key/value qua Kafka serializer; lời gọi này không cần chuyển `Message<?>` bằng `RecordMessageConverter`.

## 2. Phân biệt Serializer, Deserializer và Message Converter

Ba thành phần thường xuất hiện cùng nhau nhưng giải quyết các lớp khác nhau:

| Thành phần | Đầu vào | Đầu ra | Vai trò |
| --- | --- | --- | --- |
| Kafka `Serializer` | Java key/value | `byte[]` | Mã hóa key/value trước khi producer gửi |
| Kafka `Deserializer` | `byte[]` | Java key/value | Giải mã key/value sau khi consumer nhận |
| Spring `RecordMessageConverter` | Kafka record hoặc Spring `Message<?>` | Spring `Message<?>` hoặc Kafka `ProducerRecord` | Chuyển đổi giữa Kafka record và Spring Messaging abstraction |

Ví dụ thứ nhất dùng `JsonSerializer`/`JsonDeserializer`: producer serialize DTO thành JSON bytes, consumer deserialize JSON bytes thành DTO. Listener có thể nhận DTO trực tiếp; converter mặc định chủ yếu giúp ánh xạ record và metadata sang Spring message nếu listener dùng `Message<?>`.

Ví dụ thứ hai dùng `StringSerializer`/`StringDeserializer` cùng `StringJacksonJsonMessageConverter` trên Spring Kafka 4.x: Kafka client vận chuyển JSON dưới dạng `String`, còn message converter chuyển JSON string thành DTO dựa trên kiểu payload mà listener yêu cầu. Với Spring Kafka 3.x trở xuống, dùng `StringJsonMessageConverter`. Hai cách đều có thể dùng JSON nhưng đặt bước chuyển JSON ở hai lớp khác nhau.

Không cấu hình hai cơ chế JSON một cách chồng chéo mà không hiểu thứ tự chuyển đổi. Nếu `JsonDeserializer` đã trả về `OrderCreatedEvent`, không cần một JSON converter khác để parse lại object đó.

## 3. RecordMessageConverter mặc định

Spring Kafka cung cấp `MessagingMessageConverter` làm converter nền tảng. Nó chuyển `ConsumerRecord` thành Spring `Message<?>`, ánh xạ các metadata quan trọng vào message headers và chuyển Spring message thành `ProducerRecord` khi gửi.

Ở phía nhận, payload thường là value mà Kafka deserializer đã tạo. Converter thêm các header Spring Kafka như:

| Header | Ý nghĩa |
| --- | --- |
| `KafkaHeaders.RECEIVED_TOPIC` | Topic nhận record |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition nhận record |
| `KafkaHeaders.OFFSET` | Offset của record |
| `KafkaHeaders.RECEIVED_KEY` | Key nhận được |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp của record |
| `KafkaHeaders.TIMESTAMP_TYPE` | Loại timestamp |
| `KafkaHeaders.GROUP_ID` | Consumer group của listener container |

Các header cụ thể có thể phụ thuộc phiên bản và loại listener. `RECEIVED_KEY` và `RECEIVED_PARTITION` là tên hiện đại từ Spring Kafka 2.9; các phiên bản cũ dùng `RECEIVED_MESSAGE_KEY` và `RECEIVED_PARTITION_ID`. Khi cần API Kafka đầy đủ, có thể nhận trực tiếp `ConsumerRecord<K, V>` thay vì dựa vào Spring headers.

Trong Spring Kafka 2.5 trở lên, header `RECEIVED_KEY` không được thêm nếu record có key `null`; vì vậy hãy đánh dấu `required = false` hoặc dùng kiểu nullable khi bind key.

## 4. Nhận Spring Message trong @KafkaListener

Thay vì chỉ nhận payload DTO, listener có thể nhận `Message<T>` để truy cập cả payload lẫn headers:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import com.example.messaging.event.OrderCreatedEvent;

@Component
public class OrderMessageListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-projection")
    public void onMessage(Message<OrderCreatedEvent> message) {
        OrderCreatedEvent event = message.getPayload();
        String topic = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders()
                .get(KafkaHeaders.OFFSET, Long.class);

        // Xử lý event và dùng metadata để truy vết.
    }
}
```

Để `Message<OrderCreatedEvent>` có payload là DTO, consumer cần dùng `JsonDeserializer` hoặc cấu hình JSON `RecordMessageConverter` như các phần sau; `MessagingMessageConverter` mặc định chỉ bọc value mà Kafka deserializer đã trả về và ánh xạ metadata. `Message<T>` hữu ích khi phương thức cần payload cùng correlation ID, topic, partition hoặc offset. Nếu chỉ cần payload, nhận thẳng `OrderCreatedEvent` sẽ ngắn gọn hơn. Nếu cần mọi chi tiết của record hoặc API consumer, nhận `ConsumerRecord<K, V>`.

Có thể bind một header riêng bằng `@Header`:

```java
@KafkaListener(topics = "orders.created", groupId = "order-projection")
public void onMessage(
        OrderCreatedEvent event,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {
    // Dùng event, partition và offset.
}
```

Ví dụ cần import `org.springframework.messaging.handler.annotation.Header`. Chọn kiểu dữ liệu header phù hợp với giá trị mà converter cung cấp; nếu header có thể vắng mặt, dùng kiểu nullable như `Integer` hoặc `Long` và kiểm tra null.

## 5. Gửi Spring Message bằng KafkaTemplate

`KafkaTemplate` có overload `send(Message<?>)`. Converter được cấu hình trên template sẽ đọc payload và các header của Spring message để tạo Kafka `ProducerRecord`.

Ví dụ:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String json) {
        Message<String> message = MessageBuilder
                .withPayload(json)
                .setHeader(KafkaHeaders.TOPIC, "orders.created")
                .setHeader(KafkaHeaders.KEY, orderId)
                .setHeader("correlationId", "corr-42")
                .build();

        kafkaTemplate.send(message);
    }
}
```

Trong ví dụ, `KafkaHeaders.TOPIC` xác định topic đích và `KafkaHeaders.KEY` xác định key. Từ Spring Kafka 2.9, `KEY` là tên header hiện đại; các phiên bản cũ dùng `MESSAGE_KEY`. Converter ánh xạ các header được hỗ trợ thành metadata của Kafka record. Header `correlationId` là metadata ứng dụng và cần được header mapper hỗ trợ để chuyển thành Kafka header.

Nếu không có topic trong message header, template phải có default topic phù hợp; nếu cả hai đều không có, không thể xác định nơi gửi. Khi cần kiểm soát partition, timestamp hoặc metadata Kafka cụ thể, có thể tạo `ProducerRecord` trực tiếp hoặc dùng overload `KafkaTemplate.send(topic, partition, key, value)`.

## 6. JSON Message Converter

Khi Kafka client dùng `StringDeserializer` hoặc deserializer byte, payload đến từ Kafka có thể là JSON string/bytes. Spring Kafka cung cấp các JSON message converter để chuyển payload này thành kiểu Java mà listener yêu cầu.

Các converter phổ biến gồm:

| Converter | Kiểu payload JSON ở tầng Kafka client |
| --- | --- |
| `StringJacksonJsonMessageConverter` | `String` |
| `ByteArrayJacksonJsonMessageConverter` | `byte[]` |
| `BytesJacksonJsonMessageConverter` | Kafka `Bytes` |

Với Spring Kafka 4.x, dùng các converter dựa trên Jackson 3. Ví dụ dùng `StringJacksonJsonMessageConverter`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.support.converter.RecordMessageConverter;
import org.springframework.kafka.support.converter.StringJacksonJsonMessageConverter;

@Bean
public RecordMessageConverter recordMessageConverter() {
    return new StringJacksonJsonMessageConverter();
}
```

Khi listener yêu cầu `OrderCreatedEvent`, converter đọc JSON string và chuyển thành DTO. Ở chiều gửi, converter có thể chuyển payload object thành JSON string để `StringSerializer` mã hóa thành bytes.

Các converter JSON dùng Jackson. Trong Spring Kafka 4.0 trở lên, `JacksonJsonMessageConverter` là lớp nền dùng Jackson 3; các lớp `StringJacksonJsonMessageConverter`, `ByteArrayJacksonJsonMessageConverter` và `BytesJacksonJsonMessageConverter` chọn kiểu value phù hợp cho producer. Các tên cũ `StringJsonMessageConverter`, `ByteArrayJsonMessageConverter` và `BytesJsonMessageConverter` thuộc thế hệ Jackson 2 và đã deprecated từ Spring Kafka 4.0 để chuyển sang các lớp mới. Với Spring Kafka 3.x trở xuống, dùng tên converter tương ứng của phiên bản đó.

`byte[]` và Kafka `Bytes` tránh bước chuyển đổi trung gian `String` ↔ `byte[]`, nên có thể hiệu quả hơn khi payload lớn hoặc thông lượng cao. Type payload thường được suy ra từ tham số listener ở method-level `@KafkaListener`. Với class-level `@KafkaListener` dùng nhiều `@KafkaHandler`, payload phải được chuyển đổi đủ sớm để framework chọn đúng handler.

## 7. Cấu hình converter cho listener container

Để listener container sử dụng converter tùy chỉnh, đặt `RecordMessageConverter` trên `ConcurrentKafkaListenerContainerFactory`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.converter.RecordMessageConverter;
import org.springframework.kafka.support.converter.StringJacksonJsonMessageConverter;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public RecordMessageConverter recordMessageConverter() {
        return new StringJacksonJsonMessageConverter();
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    RecordMessageConverter recordMessageConverter) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordMessageConverter(recordMessageConverter);
        return factory;
    }
}
```

Với cấu hình này, `ConsumerFactory<String, String>` phải dùng `StringDeserializer` cho value. Converter nhận String JSON và chuyển thành DTO theo kiểu tham số listener. Khi dùng `JsonDeserializer` đã tạo DTO, cấu hình converter JSON như trên thường không cần thiết; có thể giữ converter mặc định để ánh xạ record thành Spring `Message`.

Nếu ứng dụng dùng Spring Boot auto-configuration, có thể khai báo bean converter rồi cấu hình listener factory được Boot tạo theo cơ chế của phiên bản đang dùng. Khi tự khai báo factory, cần gắn converter trực tiếp như ví dụ để biết chắc listener container nào sử dụng converter đó.

## 8. Cấu hình converter cho KafkaTemplate

`KafkaTemplate` cũng có thể dùng `RecordMessageConverter` để hỗ trợ `send(Message<?>)`:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.converter.RecordMessageConverter;
import org.springframework.kafka.support.converter.StringJacksonJsonMessageConverter;

@Configuration
public class KafkaTemplateConfiguration {

    @Bean
    public RecordMessageConverter outboundMessageConverter() {
        return new StringJacksonJsonMessageConverter();
    }

    @Bean
    public KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory,
            @Qualifier("outboundMessageConverter")
            RecordMessageConverter outboundMessageConverter) {

        KafkaTemplate<String, String> template =
                new KafkaTemplate<>(producerFactory);
        template.setMessageConverter(outboundMessageConverter);
        return template;
    }
}
```

`ProducerFactory<String, String>` trong ví dụ cần dùng `StringSerializer` cho cả key và value vì JSON converter tạo value dạng String. Nếu producer factory dùng `JsonSerializer`, hãy cân nhắc gửi DTO trực tiếp qua `send(topic, key, value)` thay vì serialize JSON thêm lần nữa qua converter.

Trong dự án thực tế, có thể dùng một converter bean chung cho inbound và outbound nếu cùng cấu hình phù hợp. Nếu hai chiều cần cách chuyển đổi khác nhau, khai báo bean riêng và gắn đúng bean vào listener factory hoặc template tương ứng.

## 9. Header mapping giữa Spring Message và Kafka record

Spring `Message<?>` dùng `MessageHeaders`; Kafka record dùng `Headers`, mỗi header có tên và byte value. `MessagingMessageConverter` dùng header mapper để chuyển đổi giữa hai dạng.

Spring Kafka cung cấp các header mapper phổ biến:

- `JsonKafkaHeaderMapper`: header mapper JSON mặc định trong Spring Kafka 4.x, hỗ trợ chuyển đổi kiểu dữ liệu header và type metadata bằng Jackson 3.
- `SimpleKafkaHeaderMapper`: ánh xạ header thô dưới dạng `byte[]`; có thể cấu hình chuyển đổi một số header String theo charset, không dùng JSON để khôi phục kiểu Java phong phú.

Khi Jackson có trên classpath, Spring Kafka 4.x mặc định dùng `JsonKafkaHeaderMapper` trong `MessagingMessageConverter`. Nếu không có header mapper, native Kafka headers có thể được đưa vào message dưới dạng `KafkaHeaders.NATIVE_HEADERS`.

Ví dụ cấu hình mapper:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.support.JsonKafkaHeaderMapper;
import org.springframework.kafka.support.converter.MessagingMessageConverter;

@Bean
public MessagingMessageConverter messagingMessageConverter() {
    MessagingMessageConverter converter =
            new MessagingMessageConverter();
    converter.setHeaderMapper(new JsonKafkaHeaderMapper());
    return converter;
}
```

Trong Spring Kafka 3.x trở xuống, tên mapper JSON tương ứng là `DefaultKafkaHeaderMapper`; lớp này đã deprecated từ 4.0 để chuyển sang `JsonKafkaHeaderMapper`. Khi cần chỉ cho phép một số header đi qua, cấu hình patterns của header mapper theo naming convention. Điều này giúp tránh gửi nhầm header nội bộ của Spring hoặc dữ liệu nhạy cảm sang Kafka.

`JsonKafkaHeaderMapper` dùng JSON để giữ kiểu của các header phức tạp và ghi type metadata vào header đặc biệt. Chỉ tin cậy những package cần thiết khi khôi phục kiểu header; tránh mở wildcard cho mọi package nếu message đến từ nguồn không hoàn toàn tin cậy. Header có kiểu không được tin cậy có thể được trả về dưới dạng thông tin kiểu chưa xác thực thay vì object Java ban đầu.

Không phải mọi Spring message header đều được chuyển thành Kafka header. Một số header nội bộ phục vụ framework, header không serialize được hoặc header bị pattern loại trừ sẽ không được mapping. Hãy kiểm thử các header ứng dụng cần truyền qua broker thay vì giả định toàn bộ `MessageHeaders` được giữ nguyên.

## 10. Header tiêu chuẩn và header nghiệp vụ

Phân biệt metadata do Kafka cung cấp với header nghiệp vụ do ứng dụng tạo:

| Loại | Ví dụ | Nguồn |
| --- | --- | --- |
| Kafka metadata nhận vào | `RECEIVED_TOPIC`, `RECEIVED_PARTITION`, `OFFSET`, `RECEIVED_TIMESTAMP` | Kafka record và listener container |
| Kafka metadata gửi ra | `TOPIC`, `PARTITION`, `KEY`, `TIMESTAMP` | Spring message gửi qua KafkaTemplate |
| Header nghiệp vụ | `correlationId`, `eventType`, `traceId`, `sourceService` | Ứng dụng |

Ví dụ đọc correlation ID:

```java
@KafkaListener(topics = "orders.created", groupId = "order-projection")
public void onMessage(
        OrderCreatedEvent event,
        @Header(name = "correlationId", required = false) String correlationId) {
    // Gắn correlationId vào log hoặc trace.
}
```

Header nghiệp vụ cần có quy ước tên, encoding và ý nghĩa ổn định giữa producer/consumer. Không đặt dữ liệu lớn trong header; payload nên chứa dữ liệu nghiệp vụ chính. Không dùng header để truyền password, token hoặc secret.

## 11. RecordMessageConverter và BatchMessageConverter

`RecordMessageConverter` xử lý một Kafka record tại một thời điểm. Khi listener được cấu hình batch mode và nhận một tập record từ một lần poll, Spring Kafka dùng abstraction `BatchMessageConverter`.

`BatchMessagingMessageConverter` là converter batch phổ biến. Nó có thể dùng một `RecordMessageConverter` để chuyển từng record trong batch trước khi tạo Spring message chứa danh sách payload.

Ví dụ cấu hình:

```java
import org.springframework.kafka.support.converter.BatchMessagingMessageConverter;
import org.springframework.kafka.support.converter.RecordMessageConverter;

var batchConverter =
        new BatchMessagingMessageConverter(recordMessageConverter);
factory.setBatchMessageConverter(batchConverter);
factory.setBatchListener(true);
```

Với batch listener, phương thức có thể nhận `List<OrderCreatedEvent>` hoặc `Message<List<OrderCreatedEvent>>` tùy cấu hình và kiểu converter. Nếu cần metadata từng record, hãy sử dụng chế độ batch converter phù hợp và kiểm tra các header batch mà Spring Kafka cung cấp. Không gắn `RecordMessageConverter` như thể nó tự xử lý toàn bộ batch; listener factory có cấu hình batch converter riêng.

## 12. Khi nào nên dùng RecordMessageConverter?

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Listener cần payload và metadata dưới dạng Spring abstraction | `RecordMessageConverter` mặc định và tham số `Message<T>` |
| Muốn nhận DTO từ JSON String | `StringJacksonJsonMessageConverter` với `StringDeserializer` trên Spring Kafka 4.x; dùng converter tương ứng ở phiên bản cũ |
| Muốn gửi Spring `Message<?>` qua KafkaTemplate | Cấu hình converter trên `KafkaTemplate` |
| Đã dùng `JsonSerializer`/`JsonDeserializer` cho DTO | Dùng serializer/deserializer; converter mặc định chỉ cần khi cần Spring Message/header mapping |
| Cần đọc trực tiếp mọi thuộc tính Kafka record | Nhận `ConsumerRecord<K, V>` |
| Listener nhận danh sách record của một poll | `BatchMessageConverter` và batch listener |
| Chuyển đổi payload theo quy tắc domain riêng | Tùy chỉnh `RecordMessageConverter` hoặc dùng converter chuyên biệt |

Không cần thêm converter JSON nếu serializer/deserializer đã giải quyết payload. Converter hữu ích nhất khi ứng dụng muốn làm việc với Spring `Message<?>`, mapping metadata hoặc chuyển JSON payload ở tầng Spring Messaging.

## 13. Tùy chỉnh RecordMessageConverter

Khi quy tắc chuyển đổi không phù hợp converter có sẵn, có thể mở rộng `MessagingMessageConverter` hoặc triển khai `RecordMessageConverter`. Ví dụ nhu cầu tùy chỉnh:

- Ánh xạ một header riêng thành metadata chuẩn của ứng dụng.
- Chuẩn hóa payload legacy trước khi listener nhận.
- Thêm header correlation hoặc source vào record khi gửi.
- Chuyển payload thành một envelope domain dùng chung.

Khi tùy chỉnh, cần giữ rõ hai chiều chuyển đổi:

1. `ConsumerRecord` sang Spring `Message<?>`: xác định payload type, map metadata và xử lý null.
2. Spring `Message<?>` sang `ProducerRecord`: xác định topic, key, partition, timestamp, payload và headers.

Không nên đặt logic nghiệp vụ như cập nhật database, kiểm tra quyền hay gọi dịch vụ bên ngoài trong converter. Converter nên tập trung vào chuyển đổi biểu diễn dữ liệu; nghiệp vụ thuộc listener hoặc application service. Điều này giúp converter dễ kiểm thử và tái sử dụng.

Nếu tự triển khai converter, cần chú ý payload type có thể là generic hoặc parameterized type, header có thể thiếu hoặc có kiểu không mong đợi, và serializer vẫn phải tương thích với kiểu value mà converter tạo ra.

## 14. SmartMessageConverter và Content-Type

`RecordMessageConverter` có thể ủy quyền phần chuyển đổi payload cho một Spring `SmartMessageConverter`. Cách này hữu ích khi muốn chọn cách đọc payload dựa trên `MessageHeaders.CONTENT_TYPE`, ví dụ JSON hoặc một media type khác, trong khi vẫn dùng cùng cơ chế ánh xạ Kafka record và headers.

Với `KafkaTemplate`, có thể gắn `SmartMessageConverter` bằng `setMessagingConverter(...)`. Với `@KafkaListener`, có thể chỉ định bean converter qua thuộc tính `contentTypeConverter` của annotation:

```java
@KafkaListener(
        id = "content-aware-listener",
        topics = "integration.events",
        contentTypeConverter = "eventContentConverter")
public void listen(OrderCreatedEvent event) {
    // Payload đã được chuyển đổi theo content type phù hợp.
}
```

Bean `eventContentConverter` cần triển khai `SmartMessageConverter` và được đăng ký trong Spring context. Converter phải xử lý đúng kiểu payload và content type mà producer gửi. Nếu converter trả về `null`, Spring Kafka giữ lại message/payload ban đầu theo cơ chế fallback; vì vậy cần kiểm thử cả content type được hỗ trợ lẫn trường hợp không khớp.

## 15. Kiểm thử message conversion

Kiểm thử converter nên xác minh cả payload lẫn metadata ở hai chiều.

### Kiểm thử nhận record thành Spring Message

Tạo `ConsumerRecord` có topic, partition, offset, key, value và header thử nghiệm, sau đó gọi converter để xác minh payload/header. Khi dùng JSON converter, kiểm tra DTO nhận được có đúng các trường.

### Kiểm thử gửi Spring Message thành ProducerRecord

Tạo message bằng `MessageBuilder`, đặt `KafkaHeaders.TOPIC`, key và custom header. Gọi converter và xác minh topic, key, payload cùng headers được ánh xạ như mong đợi.

Ví dụ kiểm thử chiều gửi ở mức khái niệm:

```java
Message<String> message = MessageBuilder
        .withPayload("{\"orderId\":\"ORD-42\"}")
        .setHeader(KafkaHeaders.TOPIC, "orders.created")
        .setHeader(KafkaHeaders.KEY, "ORD-42")
        .build();

ProducerRecord<?, ?> record = converter.fromMessage(message, null);

assertThat(record.topic()).isEqualTo("orders.created");
assertThat(record.key()).isEqualTo("ORD-42");
```

Đoạn kiểm thử cần có converter phù hợp và import `ProducerRecord`, `KafkaHeaders`, `Message`, `MessageBuilder` cùng assertion library. Tùy converter và cấu hình, payload của `ProducerRecord` có thể là String, byte array hoặc object; assertion phải phản ánh kiểu value mà serializer sẽ nhận.

### Integration test với broker

Trong integration test, gửi `Message<?>` qua `KafkaTemplate`, nhận bằng `@KafkaListener` và xác minh:

1. Topic/key/partition được ánh xạ đúng.
2. JSON payload được chuyển thành DTO mong muốn.
3. Custom headers được gửi và nhận đúng encoding.
4. Metadata nhận vào như topic/partition/offset xuất hiện ở Spring Message headers.
5. Lỗi conversion được chuyển đến error handler theo cấu hình.

Kiểm thử cả đường dùng serializer/deserializer trực tiếp và đường dùng message converter nếu ứng dụng hỗ trợ cả hai. Điều này giúp tránh cấu hình trùng lặp khiến payload bị serialize hai lần hoặc converter nhận sai kiểu dữ liệu.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Listener nhận JSON String thay vì DTO | Dùng `StringDeserializer` nhưng chưa cấu hình JSON converter, hoặc method signature không yêu cầu DTO | Cấu hình `StringJacksonJsonMessageConverter` trên Spring Kafka 4.x hoặc dùng `JsonDeserializer` |
| JSON bị parse hai lần hoặc lỗi kiểu | Kết hợp `JsonDeserializer` với JSON message converter không phù hợp | Chọn một lớp chịu trách nhiệm deserialize JSON |
| `KafkaTemplate.send(Message<?>)` báo thiếu topic | Message không có `KafkaHeaders.TOPIC` và template không có default topic | Đặt topic header hoặc default topic |
| Custom header không tới consumer | Header mapper không map tên/kiểu đó | Cấu hình `JsonKafkaHeaderMapper` (Spring Kafka 4.x) hoặc `DefaultKafkaHeaderMapper` (3.x trở xuống), patterns và encoding |
| Header nhận được khác kiểu mong muốn | Kafka header là byte[] hoặc mapper chuyển đổi kiểu | Chuẩn hóa kiểu và encoding giữa producer/consumer |
| Batch listener không chuyển payload như dự kiến | Chưa cấu hình `BatchMessageConverter` hoặc factory chưa bật batch mode | Cấu hình batch converter và `setBatchListener(true)` |
| Converter không chạy với `send(topic, key, value)` | API này dùng serializer trực tiếp, không đi qua `send(Message<?>)` | Dùng `send(Message<?>)` hoặc tự chuyển payload trước khi gọi send |
| Converter chứa logic nghiệp vụ khó kiểm thử | Trộn chuyển đổi dữ liệu với xử lý nghiệp vụ | Đưa nghiệp vụ vào listener/service, giữ converter tập trung vào mapping |

## 17. Kết luận

`RecordMessageConverter` chuyển đổi giữa Kafka record và Spring `Message<?>`. Ở phía consumer, nó giúp listener nhận payload cùng metadata dưới dạng Spring headers. Ở phía producer, nó cho phép `KafkaTemplate.send(Message<?>)` chuyển payload và headers thành `ProducerRecord`.

Hãy phân biệt message converter với Kafka serializer/deserializer: serializer/deserializer làm việc với byte ở Kafka client, còn converter làm việc ở tầng Spring Messaging. Dùng `MessagingMessageConverter` cho mapping record/header thông thường, JSON converter khi muốn chuyển JSON String/bytes thành DTO ở tầng message, và `BatchMessageConverter` cho batch listener. Chọn đúng một lớp chịu trách nhiệm chuyển JSON, cấu hình header mapper có chủ đích và giữ logic nghiệp vụ ngoài converter để luồng Spring Kafka dễ hiểu, kiểm thử và vận hành.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring for Apache Kafka — Kafka Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)
