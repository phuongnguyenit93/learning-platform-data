# Vai trò của KafkaTemplate

Trong một ứng dụng Spring Kafka, `KafkaTemplate` là thành phần phía producer giúp mã nghiệp vụ gửi bản ghi đến Kafka một cách nhất quán với hệ sinh thái Spring. Service chỉ cần inject template và gọi phương thức `send`; Spring Kafka sẽ phối hợp với `ProducerFactory`, Kafka producer, serializer, partitioner và các cấu hình đã khai báo để thực hiện việc gửi.

`KafkaTemplate` đóng vai trò cầu nối giữa mã ứng dụng Spring và Kafka producer API. Nó giảm phần mã quản lý producer lặp lại, cung cấp các overload gửi record, hỗ trợ callback bất đồng bộ, tích hợp transaction và cho phép truy cập một số thao tác nâng cao khi cần. Tuy nhiên, việc gọi `send` không đồng nghĩa consumer đã xử lý nghiệp vụ thành công; producer và consumer là hai giai đoạn riêng trong luồng messaging.

## 1. KafkaTemplate nằm ở đâu trong kiến trúc?

Một luồng gửi sự kiện điển hình có thể hình dung như sau:

```text
Controller / Application Service
             |
             v
      KafkaTemplate<K, V>
             |
             v
       ProducerFactory
             |
             v
       KafkaProducer
             |
             v
 Serializer -> Partitioner -> Kafka broker
```

Vai trò của từng thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| Application service | Quyết định khi nào phát sự kiện và dữ liệu nghiệp vụ nào cần gửi |
| `KafkaTemplate<K, V>` | Cung cấp API Spring để tạo và gửi record, nhận kết quả, xử lý callback và phối hợp transaction |
| `ProducerFactory<K, V>` | Tạo và quản lý vòng đời Kafka producer theo cấu hình đã cung cấp |
| `KafkaProducer<K, V>` | Thực hiện giao tiếp producer protocol với broker, buffer, retry và xử lý gửi theo cấu hình client |
| Serializer | Chuyển key/value từ kiểu Java sang byte array |
| Partitioner | Chọn partition nếu record không chỉ định partition cụ thể |
| Kafka broker | Nhận, lưu và sao chép record theo cấu hình topic/cluster |

Trong Spring Boot, khi có dependency Spring Kafka và cấu hình phù hợp, auto-configuration có thể tạo `ProducerFactory` và `KafkaTemplate` để ứng dụng inject trực tiếp. Khi cần nhiều producer với serializer, credential hoặc cluster khác nhau, ứng dụng có thể khai báo nhiều factory/template riêng và inject đúng bean bằng `@Qualifier`.

## 2. KafkaTemplate giải quyết vấn đề gì?

Nếu gọi trực tiếp `KafkaProducer`, mỗi thành phần gửi dữ liệu phải quan tâm đến việc tạo producer, cấu hình serializer, quản lý tài nguyên, đóng producer và xử lý callback. Cách làm này có thể phù hợp với ứng dụng Java thuần, nhưng tạo nhiều mã hạ tầng khi tích hợp vào một ứng dụng Spring.

`KafkaTemplate` tập trung các thao tác đó vào một abstraction dùng chung:

- Có thể inject như một Spring bean thay vì tự tạo producer trong mỗi service.
- Dùng chung cấu hình do `ProducerFactory` cung cấp.
- Cung cấp các overload `send` cho topic, key, partition, `ProducerRecord` và Spring `Message`.
- Trả kết quả bất đồng bộ để ứng dụng xử lý metadata hoặc lỗi.
- Hỗ trợ gửi record trong Kafka transaction khi được cấu hình.
- Có các thao tác bổ sung như `flush`, `execute` và `metrics` cho tình huống nâng cao.

Với cách tổ chức này, mã nghiệp vụ tập trung vào việc phát sự kiện. Cấu hình kết nối, serializer, partitioner, retry ở Kafka client và quản lý producer được đặt ở lớp cấu hình messaging.

## 3. Khai báo và inject KafkaTemplate

Với Spring Boot, trước hết thêm dependency Spring Kafka phù hợp với dòng Boot đang sử dụng. Các dòng Boot mới có thể cung cấp Kafka starter; những dòng khác dùng `spring-kafka` và dependency management của Boot. Sau đó cấu hình địa chỉ broker và serializer.

Ví dụ `application.yml` cho key dạng chuỗi và value dạng chuỗi:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
```

Inject `KafkaTemplate` bằng constructor injection:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public NotificationPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }
}
```

Hai kiểu generic `<String, String>` biểu thị kiểu key và value mà code ứng dụng gửi. Chúng cần phù hợp với serializer được cấu hình trong producer factory. Nếu dùng `KafkaTemplate<String, OrderCreatedEvent>`, value serializer phải biết cách chuyển `OrderCreatedEvent` thành byte, chẳng hạn JSON serializer hoặc serializer theo schema.

Thông thường, hãy dùng một bean `KafkaTemplate` đã cấu hình và chia sẻ trong các service. Không tạo một `KafkaTemplate` hoặc `KafkaProducer` mới cho từng HTTP request hay từng message; việc đó làm tăng chi phí khởi tạo, số kết nối và độ phức tạp quản lý tài nguyên.

## 4. Các cách gửi record phổ biến

`KafkaTemplate` cung cấp nhiều overload để phù hợp với nhu cầu định tuyến và metadata.

### Gửi value đến topic

```java
kafkaTemplate.send("notifications", "A new notification");
```

Không truyền key nghĩa là record không có key. Với default partitioner, Kafka dùng sticky partitioning cho record không key. Không nên dùng cách này nếu các sự kiện của cùng một thực thể cần được gom về cùng partition.

### Gửi topic cùng key và value

```java
kafkaTemplate.send("orders.events", orderId, event);
```

Đây là dạng thường dùng trong ứng dụng hướng sự kiện. `orderId` giúp các sự kiện của cùng đơn hàng thường được định tuyến vào cùng partition, miễn là partition count, serializer và partitioner không thay đổi.

### Chỉ định partition cụ thể

```java
kafkaTemplate.send("orders.events", 1, orderId, event);
```

Record được gửi trực tiếp đến partition `1`. Partition đó phải tồn tại trong topic. Khi chỉ định partition, ứng dụng chịu trách nhiệm định tuyến và bảo đảm các record cần cùng thứ tự được gửi vào cùng partition.

### Gửi ProducerRecord

Khi cần kiểm soát đầy đủ hơn các thuộc tính của record, tạo `ProducerRecord`:

```java
import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, String> record = new ProducerRecord<>(
        "orders.events",
        1,
        orderId,
        eventJson);

record.headers().add(
        "event-source",
        "order-service".getBytes(java.nio.charset.StandardCharsets.UTF_8));

kafkaTemplate.send(record);
```

`ProducerRecord` cho phép chỉ định topic, partition, timestamp, key, value và headers. Headers thường dùng để truyền metadata như event type, correlation ID hoặc source service. Không nên đưa password, token hay dữ liệu nhạy cảm vào header.

### Gửi Spring Message

Trong ứng dụng đã sử dụng abstraction `Message<?>` của Spring, có thể gửi message kèm headers:

```java
import org.springframework.messaging.support.MessageBuilder;

var message = MessageBuilder
        .withPayload(eventJson)
        .setHeader("kafka_topic", "orders.events")
        .setHeader("kafka_messageKey", orderId)
        .build();

kafkaTemplate.send(message);
```

Spring Kafka ánh xạ các header được hỗ trợ sang metadata của Kafka record. Tên header đặc biệt và cách mapping phụ thuộc API/version Spring Kafka; với code cần kiểm soát chính xác partition, timestamp hoặc headers, `ProducerRecord` thường rõ ràng hơn.

### Gửi đến default topic

`sendDefault(...)` gửi đến default topic được cấu hình trên template. Cách này hữu ích khi một template được tạo riêng cho một topic. Trong ứng dụng có nhiều topic nghiệp vụ, truyền topic tường minh vào `send` thường giúp code dễ đọc và dễ tìm kiếm hơn.

## 5. Kết quả gửi là bất đồng bộ

Các phương thức `send` trả về `CompletableFuture<SendResult<K, V>>` trong các dòng Spring Kafka hiện đại (Spring Kafka 3.x trở lên). Ứng dụng có thể tiếp tục thực hiện công việc khác trong khi Kafka producer gửi record.

Ví dụ publisher trả future cho tầng gọi:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId,
            String eventJson) {
        return kafkaTemplate.send("orders.events", orderId, eventJson);
    }
}
```

Tầng gọi có thể xử lý kết quả:

```java
publisher.publish(orderId, eventJson)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Publish order event failed: orderId={}",
                        orderId, exception);
                return;
            }

            var metadata = result.getRecordMetadata();
            log.info("Published order event: topic={}, partition={}, offset={}",
                    metadata.topic(), metadata.partition(), metadata.offset());
        });
```

Ví dụ giả định lớp đã có logger `log`. `SendResult` cung cấp record đã gửi và `RecordMetadata` do producer nhận được, gồm topic, partition, offset và timestamp. Metadata giúp xác nhận vị trí record mà broker đã ghi nhận theo cơ chế xác nhận của producer.

Không nên gọi `.get()` hoặc `.join()` một cách mặc định cho mọi message trong request thread. Chờ đồng bộ sẽ làm request bị chặn cho đến khi future hoàn tất, giảm lợi ích của gửi bất đồng bộ và có thể làm tăng độ trễ. Chỉ chờ khi luồng nghiệp vụ thực sự cần kết quả gửi trước khi tiếp tục.

Lưu ý: với `acks=0`, producer không đợi broker xác nhận; future hoàn tất không mang ý nghĩa broker đã xác nhận lưu record. Với `acks=1` hoặc `acks=all`, mức xác nhận phụ thuộc cấu hình broker, replication và `min.insync.replicas`. Cần chọn `acks` theo yêu cầu độ bền dữ liệu.

## 6. Xử lý lỗi khi gửi

Lỗi có thể xảy ra ngay khi gọi `send` hoặc xuất hiện sau đó khi producer thực hiện gửi bất đồng bộ. Ví dụ, lỗi cấu hình hoặc serialize có thể phát sinh trong quá trình chuẩn bị record; lỗi timeout, broker unavailable hoặc authorization có thể xuất hiện khi gửi đến cluster.

Vì vậy, code cần xử lý cả hai dạng:

```java
public CompletableFuture<SendResult<String, String>> publish(
        String orderId,
        String eventJson) {
    try {
        return kafkaTemplate.send("orders.events", orderId, eventJson)
                .whenComplete((result, exception) -> {
                    if (exception != null) {
                        log.error("Kafka send failed for orderId={}",
                                orderId, exception);
                    }
                });
    }
    catch (RuntimeException exception) {
        log.error("Cannot prepare Kafka record for orderId={}",
                orderId, exception);
        throw exception;
    }
}
```

Ví dụ trên log lỗi bất đồng bộ trong callback và ném lại lỗi đồng bộ để tầng gọi quyết định cách phản hồi. Trong code production, cần xác định rõ ai chịu trách nhiệm retry, ghi nhận trạng thái thất bại hoặc chuyển sự kiện vào luồng phục hồi. Không retry mù quáng mọi lỗi; lỗi serialize hoặc authorization thường không tự hết khi gửi lại ngay.

Không nên nuốt exception rồi trả về thành công. Nếu publisher không thông báo thất bại cho tầng gọi, ứng dụng có thể ghi nhận một nghiệp vụ đã phát sự kiện dù record chưa được gửi theo mức xác nhận mong muốn.

## 7. KafkaTemplate và key, partition, headers

`KafkaTemplate` không tự quyết định ý nghĩa nghiệp vụ của key. Ứng dụng phải chọn key phù hợp với thực thể cần giữ thứ tự, ví dụ `orderId` cho sự kiện vòng đời đơn hàng. Khi không chỉ định partition, producer partitioner sử dụng key đã serialize để chọn partition.

Một số nguyên tắc khi gửi:

- Dùng cùng kiểu key và serializer nhất quán giữa các producer ghi vào cùng topic.
- Chọn key theo ranh giới ordering nghiệp vụ, không dùng một UUID khác nhau cho mỗi event nếu cần gom event theo aggregate.
- Dùng `ProducerRecord` hoặc Spring `Message` khi cần metadata bổ sung.
- Không coi headers là nơi lưu payload chính hoặc bí mật xác thực.
- Quan sát partition/offset từ `SendResult` trong log hoặc test để xác minh định tuyến.

Việc tăng partition count có thể làm key được ánh xạ sang partition khác vì số partition tham gia phép tính định tuyến đã thay đổi. Nếu nghiệp vụ phụ thuộc thứ tự theo key qua toàn bộ lịch sử, hãy đánh giá tác động trước khi mở rộng topic.

## 8. KafkaTemplate và transaction

`KafkaTemplate` hỗ trợ gửi record trong Kafka transaction khi producer factory được cấu hình transaction phù hợp. Ứng dụng có thể dùng `executeInTransaction(...)` để nhóm nhiều thao tác gửi trong một transaction Kafka:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.events", orderId, orderCreatedJson);
    operations.send("orders.audit", orderId, auditJson);
    return true;
});
```

Nếu thao tác trong callback thất bại và exception được truyền ra, transaction có thể bị abort theo cơ chế transaction của template. Cần cấu hình transaction ID prefix và producer factory theo hướng dẫn Spring Kafka cho phiên bản đang dùng.

Kafka transaction giúp phối hợp các thao tác ghi Kafka trong cùng transaction. Nó không tự tạo transaction nguyên tử giữa Kafka và cơ sở dữ liệu quan hệ. Nếu một service vừa cập nhật database vừa phát event, hãy xem xét transactional outbox, inbox hoặc idempotency để xử lý khoảng thời gian giữa commit database và commit Kafka.

## 9. `flush`, `execute` và các thao tác nâng cao

### `flush()`

Kafka producer thường gửi bất đồng bộ và có thể gom record thành batch. `KafkaTemplate.flush()` yêu cầu producer đẩy các record đang chờ và chờ việc gửi hoàn tất theo semantics của Kafka client.

```java
kafkaTemplate.send("notifications", "service-started");
kafkaTemplate.flush();
```

Không gọi `flush()` sau mỗi record trong luồng thông lượng cao nếu không có lý do cụ thể. Việc flush liên tục có thể làm giảm batching và throughput. Trong phần lớn code ứng dụng, theo dõi `CompletableFuture` là cách phù hợp hơn để biết kết quả gửi.

### `execute(...)`

`execute(...)` cho phép chạy callback với Kafka `Producer` được quản lý bởi template. Đây là API mức thấp dành cho tình huống cần thao tác producer mà các overload `send` không đáp ứng. Hãy ưu tiên API cấp cao của template; khi dùng `execute`, không tự đóng producer do factory quản lý và cần hiểu rõ vòng đời callback.

### Metrics

`metrics()` cho phép truy cập các metric của producer đang được quản lý. Các metric Kafka client có thể hỗ trợ quan sát tốc độ gửi, batch, request latency và buffer. Khi đưa metric ra hệ thống giám sát, cần chọn các metric phù hợp và tránh tạo cardinality quá cao từ topic, key hoặc client ID động.

## 10. KafkaTemplate có thread-safe không?

Trong cấu hình Spring Kafka thông thường, `KafkaTemplate` được thiết kế để chia sẻ và sử dụng đồng thời từ nhiều service hoặc thread khi được cấu hình đúng. Ứng dụng thường inject một bean singleton thay vì tạo template mới cho mỗi tác vụ.

Khả năng dùng đồng thời còn phụ thuộc producer factory và cách ứng dụng tùy biến. Nếu tạo nhiều `ProducerFactory`, template riêng hoặc custom callback có trạng thái mutable, cần đảm bảo các thành phần đó an toàn với truy cập đồng thời. Không lưu dữ liệu request-specific vào field mutable của một publisher singleton.

## 11. Khi nào dùng KafkaTemplate và khi nào cần API khác?

| Nhu cầu | Cách dùng phù hợp |
| --- | --- |
| Gửi một event nghiệp vụ đến topic | `KafkaTemplate.send(topic, key, value)` |
| Chỉ định partition, timestamp hoặc headers | Tạo `ProducerRecord` rồi gửi |
| Gửi message đã được tổ chức theo abstraction Spring | `KafkaTemplate.send(Message<?>)` |
| Gửi nhiều record trong Kafka transaction | Transaction support của `KafkaTemplate` |
| Truy cập producer cho thao tác đặc biệt | `execute(...)`, chỉ khi API cấp cao không đủ |
| Đọc event từ topic | `@KafkaListener` và listener container, không phải `KafkaTemplate` |
| Xem hoặc thay đổi topic/cluster metadata | `KafkaAdmin` hoặc Kafka `AdminClient` |

`KafkaTemplate` là API gửi dữ liệu. Phần nhận dữ liệu thuộc trách nhiệm của consumer và thường được tổ chức bằng `@KafkaListener`. Tách hai vai trò này giúp service producer và consumer có thể phát triển, mở rộng và vận hành độc lập.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gọi `send` rồi mặc định coi là thành công | Không phát hiện lỗi bất đồng bộ | Theo dõi future và xử lý exception |
| Dùng generic type không khớp serializer | Lỗi serialize hoặc deserialize | Đồng bộ kiểu key/value với serializer và deserializer |
| Tạo template/producer mới cho từng request | Tăng kết nối và chi phí tài nguyên | Inject bean template dùng chung |
| Không truyền key dù cần thứ tự theo entity | Event cùng entity có thể vào nhiều partition | Dùng business key ổn định |
| Chặn `.get()` cho mọi lần gửi | Tăng latency và giảm throughput | Dùng callback/future trừ khi cần kết quả đồng bộ |
| Gọi `flush()` sau mỗi record | Giảm batching và throughput | Để producer batching theo cấu hình thông thường |
| Nuốt exception gửi Kafka | Mất khả năng quan sát thất bại | Ghi nhận và truyền lỗi đến tầng chịu trách nhiệm |
| Cho rằng Kafka transaction bao gồm database | Có thể phát sinh trạng thái lệch giữa DB và Kafka | Dùng outbox/inbox hoặc cơ chế nhất quán phù hợp |

## 13. Kết luận

`KafkaTemplate` là abstraction trung tâm ở phía producer trong Spring Kafka. Nó kết nối mã nghiệp vụ với Kafka producer thông qua `ProducerFactory`, cung cấp các cách gửi record có hoặc không có key, chỉ định partition, gửi headers, theo dõi kết quả bất đồng bộ và phối hợp Kafka transaction.

Trong ứng dụng Spring, hãy inject template dùng chung, chọn kiểu key/value và serializer phù hợp, truyền key theo ranh giới ordering nghiệp vụ, đồng thời theo dõi `CompletableFuture` để biết kết quả gửi. Hiểu rõ giới hạn giữa producer acknowledgement, consumer processing và transaction với database sẽ giúp thiết kế luồng messaging tin cậy hơn.

## Tài liệu tham khảo

- [Spring for Apache Kafka — KafkaTemplate](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
