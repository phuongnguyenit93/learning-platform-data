# Không thay đổi payload ngoài dự kiến

Trong Spring Kafka, interceptor có thể quan sát hoặc can thiệp vào record trước khi listener xử lý. Một số interceptor còn cho phép trả về record mới hoặc sửa key, value và header. Khả năng này hữu ích cho tracing, audit hoặc gắn metadata, nhưng cũng tạo rủi ro: một thay đổi tưởng như nhỏ có thể làm payload gửi lên Kafka khác với dữ liệu ứng dụng tạo ra, hoặc làm listener nhận một object đã bị sửa ngoài dự kiến.

Muốn giữ payload ổn định, trước hết cần phân biệt đúng các điểm mở rộng: `ProducerInterceptor` chạy ở phía producer trước serialization; `RecordInterceptor` của Spring Kafka chạy trước listener; `ConsumerInterceptor` chạy bên trong Kafka consumer trước khi `poll()` trả record; còn `RecordFilterStrategy` dùng để loại record khỏi listener. Mỗi cơ chế có tác động và trách nhiệm khác nhau.

## 1. Payload có thể thay đổi ở những giai đoạn nào?

Một luồng gửi/nhận điển hình có các bước:

```mermaid
flowchart LR
    A[Application tạo event] --> B[ProducerInterceptor]
    B --> C[Serializer]
    C --> D[Kafka broker: bytes]
    D --> E[Deserializer]
    E --> F[ConsumerInterceptor]
    F --> G[Spring RecordInterceptor]
    G --> H[Message converter]
    H --> I[@KafkaListener]
```

Mỗi bước có thể làm thay đổi cách dữ liệu được nhìn thấy:

- **Producer interceptor:** có thể thay key/value hoặc header trước khi serializer chuyển object thành bytes. Nếu key/value bị thay đổi, dữ liệu thực sự ghi vào Kafka cũng thay đổi.
- **Serializer:** quyết định cách object được mã hóa thành bytes. Đây là nơi chuyển đổi wire format có chủ đích.
- **Consumer interceptor:** có thể thay đổi hoặc lọc `ConsumerRecords` trước khi Kafka client trả chúng cho ứng dụng.
- **Spring record interceptor:** chạy trước listener; có thể kiểm tra, trả về record khác hoặc bỏ qua listener bằng cách trả `null`.
- **Message converter:** chuyển dữ liệu đã deserialize thành payload phù hợp với chữ ký listener. Đây là nơi chuyển đổi kiểu dữ liệu có chủ đích.
- **Listener/application service:** nơi thực hiện biến đổi nghiệp vụ. Các thay đổi domain nên được viết rõ trong logic này để có thể review và kiểm thử.

Một interceptor không tự động bảo đảm payload bất biến. Hợp đồng của API cho phép một số loại interceptor sửa record; trách nhiệm giữ dữ liệu đúng thuộc về implementation và cấu hình của ứng dụng.

## 2. Phân biệt các cơ chế

| Cơ chế | Vị trí chạy | Có thể thay đổi payload? | Mục đích phù hợp |
|---|---|---|---|
| Kafka `ProducerInterceptor` | Trước serialization và trước khi producer xác định partition nếu record chưa chỉ định partition. | Có; trả về `ProducerRecord` mới hoặc thay đổi header/key/value. | Gắn metadata producer, tracing, đo lường gửi. |
| Kafka `ConsumerInterceptor` | Trước khi `KafkaConsumer.poll()` trả records cho ứng dụng. | Có; có thể biến đổi hoặc lọc tập record. | Quan sát consumer ở tầng Kafka client. |
| Spring `RecordInterceptor` | Trong listener container, trước khi gọi record listener. | Có; trả về record khác hoặc `null` để bỏ qua listener. | Quan sát record, ghi log, gắn thông tin cục bộ cho lần xử lý. |
| Spring `BatchInterceptor` | Trước khi gọi batch listener. | Có thể kiểm tra hoặc trả về batch phù hợp theo API. | Quan sát batch listener. |
| Spring `RecordFilterStrategy` | Trong adapter trước khi listener được gọi. | Không nhằm sửa payload; quyết định record có bị discard hay không. | Bỏ qua duplicate hoặc record không cần xử lý. |
| Serializer/message converter | Ở ranh giới chuyển đổi dữ liệu. | Có; đây là chức năng chính của chúng. | Chuyển DTO thành bytes/JSON và ngược lại theo hợp đồng. |

Không dùng `RecordInterceptor` như một bộ lọc nghiệp vụ nếu `RecordFilterStrategy` diễn đạt đúng ý định hơn. Không dùng interceptor để âm thầm đổi event thành một loại event khác; hãy thực hiện chuyển đổi trong application service hoặc mapper có tên gọi rõ ràng.

## 3. ProducerInterceptor có thể làm thay đổi dữ liệu đã gửi

Kafka `ProducerInterceptor.onSend()` được gọi khi ứng dụng gọi `KafkaProducer.send()`, trước khi key/value được serialize. Interceptor có thể trả về một `ProducerRecord` khác. Vì vậy, nếu sửa key hoặc value tại đây, serializer sẽ nhận dữ liệu đã sửa và bytes được lưu trong Kafka phản ánh thay đổi đó.

Ví dụ một interceptor chỉ bổ sung header nguồn gửi, không chạm vào key/value:

```java
import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerInterceptor;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.header.internals.RecordHeader;

public class ProducerSourceInterceptor
        implements ProducerInterceptor<String, OrderEvent> {

    @Override
    public ProducerRecord<String, OrderEvent> onSend(
            ProducerRecord<String, OrderEvent> record) {

        record.headers().add(new RecordHeader(
                "producer-service",
                "order-api".getBytes(StandardCharsets.UTF_8)
        ));

        // Giữ nguyên topic, partition, key và value.
        return record;
    }

    @Override
    public void onAcknowledgement(RecordMetadata metadata, Exception exception) {
        // Chỉ ghi metric/log ngắn gọn; không thực hiện I/O chậm.
    }

    @Override
    public void configure(Map<String, ?> configs) {
        // Đọc cấu hình nếu interceptor cần.
    }

    @Override
    public void close() {
        // Giải phóng tài nguyên riêng nếu có.
    }
}
```

Đăng ký interceptor bằng producer property:

```yaml
spring:
  kafka:
    producer:
      properties:
        interceptor.classes: com.example.kafka.ProducerSourceInterceptor
```

Trong ví dụ, header được bổ sung để truy vết nguồn gửi. Payload `OrderEvent` và key vẫn giữ nguyên. Nếu producer gửi nhiều loại value, generic type của interceptor phải phù hợp với record thực tế; nếu không, lỗi kiểu có thể chỉ được ghi log bởi Kafka interceptor mà không chặn việc gửi.

### Vì sao không nên sửa key/value trong interceptor?

Giả sử ứng dụng tạo event:

```java
OrderEvent event = new OrderEvent("E100", "O100", 125_000);
kafkaTemplate.send("orders.events", event.orderId(), event);
```

Nếu `onSend()` sửa `event.amount()` hoặc thay key, Kafka nhận một payload khác với object caller đưa vào. Điều này có thể làm sai chữ ký event, partition routing, log compaction hoặc kết quả đối soát giữa ứng dụng và Kafka.

Nếu cần chuẩn hóa dữ liệu trước khi gửi, hãy tạo một object mới trong application layer:

```java
OrderEvent normalized = orderEventMapper.normalize(event);
kafkaTemplate.send("orders.events", normalized.orderId(), normalized);
```

Tên hàm `normalize` cho biết rõ có biến đổi dữ liệu. Có thể unit test mapper và so sánh object đầu vào/đầu ra mà không cần phụ thuộc vòng đời producer interceptor.

### Lưu ý về lỗi và đa luồng

Kafka gọi producer interceptor từ nhiều thread. Implementation phải thread-safe nếu có state dùng chung. Ngoài ra, exception ném ra từ callback của `ProducerInterceptor` được Kafka bắt và ghi log, không truyền ngược về caller như một cơ chế validation đáng tin cậy. Vì vậy:

- Không dùng `onSend()` để từ chối payload không hợp lệ.
- Validate event trước `KafkaTemplate.send()`.
- Không giữ một `StringBuilder`, `HashMap` mutable hoặc buffer dùng chung mà không đồng bộ.
- Giữ callback nhanh; `onAcknowledgement()` có thể chạy trên I/O thread của producer.
- Tránh xây dựng chuỗi interceptor cùng sửa payload phụ thuộc kết quả của nhau.

## 4. ConsumerInterceptor có thể thay đổi records trước ứng dụng

Kafka `ConsumerInterceptor.onConsume()` được gọi trước khi `KafkaConsumer.poll()` trả `ConsumerRecords` cho code gọi. API cho phép interceptor trả về tập record mới, lọc record hoặc tạo record. Exception từ callback được Kafka bắt và ghi log, không truyền cho caller.

Điểm nguy hiểm là consumer đã poll và cập nhật vị trí đọc trước khi ứng dụng xử lý tập record đã qua interceptor. Nếu interceptor âm thầm loại một record, ứng dụng có thể không bao giờ thấy record đó trong khi consumer position vẫn tiến lên. Khi offset được commit, record đã bị bỏ qua ở cấp ứng dụng.

Do đó, không nên dùng Kafka `ConsumerInterceptor` để loại event nghiệp vụ hoặc thay payload. Nếu cần bỏ record có chủ đích trong Spring listener, dùng `RecordFilterStrategy` và xác định rõ chính sách acknowledgement/commit. Nếu cần kiểm tra dữ liệu, trả nguyên tập record và chỉ ghi metric/log.

Ví dụ cấu hình consumer interceptor ở Kafka client:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;

Map<String, Object> consumerProperties = new HashMap<>();
consumerProperties.put(
        ConsumerConfig.INTERCEPTOR_CLASSES_CONFIG,
        ConsumerAuditInterceptor.class.getName()
);
```

Với Spring Boot có thể đặt `spring.kafka.consumer.properties.interceptor.classes`. Lưu ý các interceptor của Kafka được Kafka client tạo và quản lý; chúng không tự động trở thành Spring bean để nhận constructor injection. Nếu cần phụ thuộc Spring, phải cấu hình thủ công theo cơ chế `configure()` hoặc cân nhắc Spring `RecordInterceptor`.

## 5. Spring RecordInterceptor: quan sát trước listener

`RecordInterceptor<K,V>` được Spring Kafka gọi trước khi record listener xử lý. Với API hiện đại, method `intercept()` nhận cả `ConsumerRecord` và `Consumer`; có thể trả về record ban đầu, một record khác hoặc `null` để bỏ qua listener.

Ví dụ chỉ ghi log metadata, không thay đổi payload:

```java
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.RecordInterceptor;
import org.springframework.stereotype.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Component
public class OrderAuditRecordInterceptor
        implements RecordInterceptor<String, OrderEvent> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderAuditRecordInterceptor.class);

    @Override
    public ConsumerRecord<String, OrderEvent> intercept(
            ConsumerRecord<String, OrderEvent> record,
            Consumer<String, OrderEvent> consumer) {

        log.debug("Receiving topic={}, partition={}, offset={}, key={}",
                record.topic(), record.partition(), record.offset(), record.key());

        // Trả lại chính record; không sửa key, value hoặc headers.
        return record;
    }
}
```

Gắn interceptor vào listener container factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        OrderAuditRecordInterceptor auditInterceptor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setRecordInterceptor(auditInterceptor);
    return factory;
}
```

Với `@KafkaListener`, chọn factory:

```java
@KafkaListener(
        topics = "orders.events",
        groupId = "order-projection",
        containerFactory = "orderListenerFactory"
)
public void listen(OrderEvent event) {
    orderService.apply(event);
}
```

### Những nguyên tắc bắt buộc khi trả record khác

Spring Kafka cho phép `RecordInterceptor` trả về một `ConsumerRecord` khác. Nếu làm vậy, **topic, partition và offset phải được giữ nguyên**. Thay đổi các trường định vị này có thể làm container xử lý hoặc commit offset sai, dẫn đến bỏ sót hoặc xử lý lặp record.

Ngoài ba trường trên, nếu tạo record mới, hãy giữ nguyên timestamp, timestamp type, serialized key/value size, headers và leader epoch khi phiên bản Kafka API hỗ trợ. Không dùng constructor đơn giản rồi vô tình làm mất metadata mà listener, tracing hoặc dead-letter recoverer cần.

Không sửa object `record.value()` tại chỗ. `ConsumerRecord` không cho phép thay reference value sau khi tạo, nhưng object value có thể mutable. Ví dụ `OrderEvent` có setter vẫn có thể bị sửa:

```java
// Không nên: object được listener nhận đã bị sửa ngay trong interceptor.
record.value().setAmount(0);
return record;
```

Nếu thực sự cần tạo một view đã chuẩn hóa, hãy tạo object mới một cách tường minh và chỉ thay payload khi hợp đồng listener cho phép. Với mục tiêu giữ payload nguyên vẹn, lựa chọn an toàn là trả về đúng record đầu vào.

## 6. Các callback sau khi listener chạy

Từ Spring Kafka 2.7, `RecordInterceptor` có thêm callback `success()` và `failure()`; từ 2.8 có `afterRecord()`. Chúng giúp ghi nhận kết quả xử lý mà không phải bọc toàn bộ listener method.

```java
@Override
public void success(ConsumerRecord<String, OrderEvent> record,
        Consumer<String, OrderEvent> consumer) {
    metrics.increment("orders.listener.success");
}

@Override
public void failure(ConsumerRecord<String, OrderEvent> record,
        Exception exception,
        Consumer<String, OrderEvent> consumer) {
    metrics.increment("orders.listener.failure");
}

@Override
public void afterRecord(ConsumerRecord<String, OrderEvent> record,
        Consumer<String, OrderEvent> consumer) {
    // Dọn state theo thread nếu interceptor đã tạo state tạm.
}
```

Callback này phù hợp cho metric và cleanup. Không sửa payload trong `success()` hoặc `failure()` với kỳ vọng thay đổi dữ liệu listener đã xử lý. Nếu cần truyền thông tin qua các callback, chỉ lưu metadata tối thiểu theo thread và dọn trong `afterRecord()`/`clearThreadState()`.

### Interceptor và transaction

Mặc định interceptor được gọi trước khi transaction bắt đầu (`interceptBeforeTx=true`). Có thể đặt `interceptBeforeTx=false` nếu interceptor cần chạy bên trong transaction của container. Khi dùng transaction, nếu `intercept()` có thể ném exception thì không được kết hợp với `interceptBeforeTx=true` theo hợp đồng API hiện hành; hãy kiểm tra cấu hình transaction và vị trí interceptor trước khi cho phép lỗi từ interceptor đi ra.

Không gọi các method làm thay đổi consumer position hoặc committed offsets từ interceptor. Listener container quản lý poll, seek, acknowledgement và commit; can thiệp trực tiếp có thể phá vỡ semantics xử lý.

## 7. Dùng RecordFilterStrategy khi mục tiêu là loại record

Nếu mục tiêu là không gọi listener cho một record cụ thể, dùng `RecordFilterStrategy`. Method `filter()` trả `true` khi record cần bị discard; trả `false` để listener tiếp tục nhận record. Cơ chế này diễn đạt ý định lọc rõ ràng hơn việc trả `null` từ interceptor.

Ví dụ bỏ qua event đã được đánh dấu không cần xử lý:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.listener.adapter.RecordFilterStrategy;

@Bean
RecordFilterStrategy<String, OrderEvent> ignoredOrderFilter() {
    return record -> record.value().isIgnored();
}
```

Gắn filter vào factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.adapter.RecordFilterStrategy;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> filteredOrderFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        RecordFilterStrategy<String, OrderEvent> ignoredOrderFilter) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setRecordFilterStrategy(ignoredOrderFilter);
    factory.setAckDiscarded(true);
    return factory;
}
```

Hoặc từ Spring Kafka 2.8.4, chọn filter riêng cho listener bằng thuộc tính `filter`:

```java
@KafkaListener(
        id = "orderListener",
        topics = "orders.events",
        filter = "ignoredOrderFilter"
)
public void listen(OrderEvent event) {
    orderService.apply(event);
}
```

`ackDiscarded` mặc định là `false`. Khi dùng manual acknowledgement, đặt `true` nếu record bị discard phải được acknowledge/commit theo chính sách của ứng dụng. Với các AckMode khác, cần hiểu cách container commit offset và kiểm thử rằng record đã lọc không bị đọc lặp vô hạn hoặc bị bỏ qua ngoài ý muốn. Không dùng filter cho một lỗi tạm thời cần retry; hãy để exception đi qua error handler.

Với batch listener, Spring Kafka cung cấp `FilteringBatchMessageListenerAdapter`. Khi override `filterBatch()`, trả danh sách record còn lại; nếu muốn loại toàn bộ batch, trả list rỗng thay vì `null`. Từ Spring Kafka 3.3, `ignoreEmptyBatch()` cho phép bỏ qua lời gọi listener khi batch sau lọc rỗng; nếu bật, container vẫn thực hiện commit theo cấu hình.

## 8. Producer/consumer interceptor không phải nơi validate dữ liệu

Một điểm dễ nhầm là interceptor callback của Kafka client không phải cổng kiểm tra có thể từ chối record. Exception trong `ProducerInterceptor` và `ConsumerInterceptor` được Kafka bắt, log và không truyền cho ứng dụng gọi API như một lỗi validation thông thường.

Nếu payload không hợp lệ, hãy kiểm tra trước khi gửi:

```java
public void publish(OrderEvent event) {
    validator.validate(event); // Ném exception nếu payload không hợp lệ.
    kafkaTemplate.send("orders.events", event.orderId(), event);
}
```

Nếu dữ liệu nhận được không hợp lệ, hãy để deserializer, message converter hoặc listener phát sinh exception phù hợp để `DefaultErrorHandler`, retry và DLT xử lý theo chính sách. Đừng âm thầm sửa payload trong interceptor để che lỗi producer hoặc schema.

## 9. Mutable payload và defensive copy

Kafka record được truyền qua các lớp trong cùng process. Nếu value là object mutable, nhiều thành phần có thể giữ cùng một reference. Sửa object ở một interceptor hoặc helper có thể làm listener nhìn thấy dữ liệu đã đổi.

Các lựa chọn để tránh thay đổi ngoài dự kiến:

- Dùng DTO bất biến, chẳng hạn Java `record`, với field không mutable.
- Dùng `final` cho field và không cung cấp setter.
- Với collection, dùng bản sao không thể sửa (`List.copyOf`, `Map.copyOf`) khi tạo event.
- Nếu cần biến đổi, tạo object mới thay vì sửa object đầu vào.
- Không chia sẻ buffer, byte array hoặc collection mutable giữa các thread nếu không có defensive copy.
- Không tái sử dụng object event rồi sửa field sau khi gọi `KafkaTemplate.send()`; serializer có thể chạy bất đồng bộ sau lời gọi đó.

Ví dụ DTO bất biến:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal amount,
        Instant occurredAt
) {}
```

`record` giúp field không thể gán lại sau khi tạo. Nếu record chứa `byte[]`, `List` hoặc object mutable khác, cần copy dữ liệu đó khi nhận vào và khi trả ra; Java record không tự biến object lồng bên trong thành immutable.

## 10. Headers cũng có thể bị thay đổi

`ProducerRecord` và `ConsumerRecord` có thể cung cấp `Headers` mutable. Thêm hoặc xóa header không trực tiếp thay payload value, nhưng vẫn thay đổi metadata mà downstream có thể sử dụng.

Ví dụ, một interceptor xóa `event-type` có thể khiến consumer không xác định được loại event; xóa `correlation-id` làm mất khả năng trace; ghi đè `schema-version` có thể khiến deserializer chọn sai schema.

Các nguyên tắc nên áp dụng:

- Chỉ thêm header có namespace rõ, ví dụ `x-producer-service` hoặc `x-trace-id`.
- Không ghi đè header nghiệp vụ hoặc header do framework quản lý nếu không có hợp đồng.
- Khi cần thay giá trị, xác định rõ header có thể lặp hay chỉ được có một giá trị; Kafka cho phép nhiều header trùng tên.
- Không đưa token, credential hoặc dữ liệu nhạy cảm vào header chỉ để tiện logging.
- Kiểm tra header trước/sau interceptor trong test.

## 11. Thread safety và dependency injection

`ProducerInterceptor` có thể được gọi đồng thời từ nhiều thread của producer. `ConsumerInterceptor` được Kafka quản lý cùng consumer instance. Spring `RecordInterceptor` có thể được dùng bởi nhiều child container khi listener concurrency lớn hơn một. Vì vậy, không giữ mutable state dùng chung trong interceptor nếu không có cơ chế bảo vệ.

Kafka client tự tạo producer/consumer interceptor theo cấu hình `interceptor.classes`; chúng không mặc nhiên là Spring bean. Nếu cần inject service Spring, tài liệu Spring Kafka hướng dẫn truyền dependency qua `configure()` hoặc tùy chỉnh factory. Với logic chỉ dành cho Spring listener, `RecordInterceptor` là lựa chọn tự nhiên hơn vì có thể khai báo bean và inject dependency theo constructor.

Không thực hiện truy vấn database hoặc HTTP chậm trong producer interceptor. `onSend()` nằm trên đường gửi record và có thể làm tăng latency; `onAcknowledgement()` có thể chạy trên I/O thread. Với consumer interceptor, callback nằm trong luồng poll. Với Spring record interceptor, xử lý chậm cũng kéo dài thời gian consumer thread không poll broker.

## 12. Composite interceptor và thứ tự chạy

Spring Kafka có `CompositeRecordInterceptor` và `CompositeBatchInterceptor` để chạy nhiều interceptor. Kafka producer cũng cho phép đăng ký nhiều `ProducerInterceptor`; chúng được gọi theo thứ tự cấu hình và interceptor tiếp theo nhận record do interceptor trước trả về.

Nếu nhiều interceptor cùng sửa payload hoặc headers, kết quả phụ thuộc thứ tự và trạng thái mà interceptor trước để lại. Điều này khiến việc tìm nguyên nhân dữ liệu bị thay đổi khó hơn.

Nên tổ chức pipeline như sau:

1. Interceptor quan sát/log/metric, trả nguyên record.
2. Nếu cần thêm metadata, mỗi interceptor chỉ sở hữu một nhóm header riêng.
3. Chuyển đổi payload được thực hiện trong một mapper/service có tên gọi rõ ràng, không chia nhỏ thành nhiều interceptor ẩn.
4. Có test xác nhận thứ tự callback và output cuối cùng khi composite được dùng.

Từ Spring Kafka 4.0, container factory/container cung cấp getter cho record/batch interceptor; nếu đang dùng composite, có thể thêm interceptor vào composite sau khi container được tạo. Với các phiên bản cũ, hãy cấu hình toàn bộ chuỗi trước khi tạo container.

## 13. Kiểm thử để chứng minh payload không bị đổi

Kiểm thử nên xác minh dữ liệu ở cả hai phía của interceptor thay vì chỉ kiểm tra listener có được gọi.

### Unit test cho ProducerInterceptor

- Tạo một `ProducerRecord` có key/value/header đã biết.
- Gọi `onSend()`.
- So sánh topic, partition, key và value trước/sau.
- Xác minh chỉ header được phép thêm xuất hiện.
- Xác minh không có header nghiệp vụ bị xóa hoặc ghi đè.

### Unit test cho Spring RecordInterceptor

- Truyền một `ConsumerRecord` mẫu vào `intercept()`.
- Xác minh cùng record được trả về nếu interceptor chỉ quan sát.
- Nếu trả record mới, xác minh topic/partition/offset và metadata cần thiết được giữ nguyên.
- Xác minh value object không bị mutate.
- Xác minh callback `success`, `failure` và `afterRecord` không sửa payload.

### Integration test với Kafka

1. Gửi event có `eventId`, key, value và headers xác định.
2. Consumer nhận record qua đúng listener container factory.
3. Listener ghi nhận payload và metadata nhận được.
4. So sánh payload listener nhận với payload gốc.
5. Kiểm tra filter chỉ discard record được chọn; record còn lại được xử lý đúng.
6. Kiểm tra offset/acknowledgement sau khi filter, đặc biệt với `MANUAL` hoặc `MANUAL_IMMEDIATE`.
7. Chạy với concurrency lớn hơn một nếu interceptor có state dùng chung.

Ví dụ assertion cho interceptor chỉ quan sát:

```java
ConsumerRecord<String, OrderEvent> before = createRecord(event);
ConsumerRecord<String, OrderEvent> after = interceptor.intercept(before, consumer);

assertThat(after).isSameAs(before);
assertThat(after.value()).isEqualTo(event);
assertThat(after.topic()).isEqualTo(before.topic());
assertThat(after.partition()).isEqualTo(before.partition());
assertThat(after.offset()).isEqualTo(before.offset());
```

Nếu event là object mutable, thêm assertion cho các field lồng nhau hoặc dùng immutable DTO để so sánh. Không chỉ so sánh reference vì cùng một object có thể đã bị mutate tại chỗ.

## 14. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Consumer nhận amount khác với object ban đầu | Producer interceptor hoặc mapper đã sửa mutable value trước serialization. | Kiểm tra `onSend()`, tạo DTO mới trong application layer và test payload trước/sau. |
| Listener nhận object đã bị thay đổi | Spring `RecordInterceptor` sửa `record.value()` tại chỗ. | Dùng DTO immutable và trả lại record ban đầu. |
| Record bị mất hoặc offset xử lý sai | Interceptor trả record mới với topic/partition/offset khác. | Giữ nguyên ba trường định vị; tốt nhất không thay record nếu không cần. |
| Event bị bỏ qua ngoài dự kiến | `RecordInterceptor` trả `null` hoặc `ConsumerInterceptor` lọc record. | Dùng `RecordFilterStrategy` với chính sách acknowledgement rõ ràng. |
| Filtered record bị đọc lại | `ackDiscarded`/AckMode không phù hợp với cách ứng dụng quản lý acknowledgement. | Xác định semantics commit và kiểm thử với group thật. |
| Lỗi validation không chặn được producer send | `ProducerInterceptor` ném exception nhưng Kafka chỉ log exception. | Validate trong application service trước `KafkaTemplate.send()`. |
| Trace header biến mất | Interceptor xóa hoặc ghi đè header do framework/ứng dụng quản lý. | Quy định namespace header và test header sau pipeline. |
| Kết quả thay đổi khi tăng concurrency | Interceptor giữ mutable state không thread-safe. | Dùng interceptor stateless hoặc cấu trúc concurrent phù hợp. |
| Spring dependency trong Kafka interceptor bị null | Kafka client tự tạo interceptor, không dùng Spring bean lifecycle. | Wire qua `configure()`/factory hoặc dùng Spring `RecordInterceptor`. |
| Batch listener không được lọc như dự kiến | Dùng sai adapter hoặc listener nhận raw `ConsumerRecords`. | Dùng batch filter phù hợp; lưu ý `ConsumerRecords` là immutable và adapter batch không áp dụng cho kiểu này. |

## 15. Checklist trước khi đưa interceptor vào production

- Interceptor có mục đích rõ: quan sát, thêm metadata, filtering hay biến đổi dữ liệu.
- Không sửa key/value nếu không có yêu cầu và hợp đồng dữ liệu được version hóa.
- Nếu thêm header, chỉ dùng tên header thuộc phạm vi của interceptor.
- Nếu trả record khác từ `RecordInterceptor`, topic/partition/offset vẫn giữ nguyên.
- Không gọi consumer seek/commit hoặc thay đổi position từ interceptor.
- Không dùng exception trong Kafka producer/consumer interceptor như validation gate.
- State trong interceptor thread-safe và callback không làm I/O chậm.
- Filter dùng `RecordFilterStrategy`, có chính sách `ackDiscarded`/AckMode rõ ràng.
- DTO payload bất biến hoặc có defensive copy cho collection/array lồng nhau.
- Có unit test và integration test xác minh payload/header trước-sau.

## 16. Ghi nhớ

- `ProducerInterceptor` chạy trước serialization; sửa key/value làm thay đổi bytes được ghi lên Kafka.
- `ConsumerInterceptor` chạy trước khi `poll()` trả record; lọc record ở đây có thể khiến ứng dụng bỏ qua dữ liệu trong khi consumer position đã tiến.
- Spring `RecordInterceptor` chạy trước listener; có thể trả record khác hoặc `null`, nhưng record mới phải giữ topic, partition và offset.
- Dùng `RecordFilterStrategy` khi muốn discard record, không dùng interceptor để lọc nghiệp vụ một cách ẩn.
- Exception trong Kafka `ProducerInterceptor`/`ConsumerInterceptor` được bắt và log; không dùng chúng để chặn dữ liệu không hợp lệ.
- Payload mutable có thể bị sửa qua reference dù `ConsumerRecord`/`ProducerRecord` không cho thay trực tiếp reference value.
- Kafka headers mutable; chỉ thêm/xóa header theo hợp đồng rõ ràng.
- Interceptor có thể chạy đồng thời; tránh mutable state dùng chung và callback chậm.
- Dùng serializer/converter/mapper cho chuyển đổi payload có chủ đích, đặt logic nghiệp vụ ở application layer.
- Kiểm thử payload, key, metadata và headers trước/sau interceptor để chứng minh không có thay đổi ngoài dự kiến.

Để payload không bị thay đổi ngoài dự kiến, hãy để interceptor chủ yếu quan sát và bổ sung metadata có phạm vi rõ ràng. Nếu cần biến đổi dữ liệu, thực hiện ở application mapper hoặc serializer/converter được kiểm thử riêng. Khi cần bỏ record, dùng `RecordFilterStrategy` và xác định chính sách commit; khi cần trả record mới từ `RecordInterceptor`, giữ nguyên vị trí Kafka. Những ranh giới rõ ràng này giúp event đến consumer giữ đúng nội dung mà producer đã công bố.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Filtering Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/filtering.html)
- [Spring for Apache Kafka — Wiring Spring Beans into Producer/Consumer Interceptors](https://docs.spring.io/spring-kafka/reference/kafka/interceptors.html)
- [Spring Kafka — RecordInterceptor API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/RecordInterceptor.html)
- [Apache Kafka — ProducerInterceptor API](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/producer/ProducerInterceptor.html)
- [Apache Kafka — ConsumerInterceptor API](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/consumer/ConsumerInterceptor.html)
