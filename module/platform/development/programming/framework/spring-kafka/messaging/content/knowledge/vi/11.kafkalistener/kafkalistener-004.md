# Đọc ConsumerRecord trong listener

Khi một phương thức `@KafkaListener` chỉ nhận tham số kiểu `String` hoặc một DTO, ứng dụng thường chỉ nhìn thấy value của message. Trong nhiều tình huống, listener còn cần biết record đến từ topic nào, partition nào, offset bao nhiêu, key là gì, được tạo vào thời điểm nào và có những header nào. Spring Kafka cho phép nhận trực tiếp `ConsumerRecord<K, V>` để truy cập toàn bộ thông tin đó.

`ConsumerRecord` là kiểu dữ liệu của Apache Kafka client. Spring Kafka chuyển record do consumer lấy được vào phương thức listener; key và value đã đi qua deserializer được cấu hình. Vì vậy, `ConsumerRecord` giúp mã nghiệp vụ kết hợp payload với metadata của Kafka mà không phải tự tạo một consumer hoặc gọi `poll()`.

## 1. ConsumerRecord là gì?

`ConsumerRecord<K, V>` đại diện cho một bản ghi được consumer đọc từ Kafka. Hai tham số generic biểu thị kiểu key (`K`) và kiểu value (`V`) sau khi deserialization.

Ví dụ:

```java
ConsumerRecord<String, String> record;
```

Trong ví dụ này, key và value mà listener nhìn thấy đều là `String`. Nếu consumer dùng JSON deserializer để chuyển value thành `OrderCreatedEvent`, kiểu có thể là:

```java
ConsumerRecord<String, OrderCreatedEvent> record;
```

Một record chứa các thông tin chính:

| Thành phần | Ý nghĩa |
| --- | --- |
| `topic()` | Tên topic chứa record |
| `partition()` | Số partition chứa record |
| `offset()` | Vị trí của record trong partition đó |
| `key()` | Key sau khi deserialize |
| `value()` | Value sau khi deserialize |
| `timestamp()` | Timestamp gắn với record |
| `timestampType()` | Loại timestamp, ví dụ thời điểm producer tạo hoặc broker append |
| `headers()` | Tập header của record |
| `serializedKeySize()` | Kích thước key đã serialize, tính bằng byte |
| `serializedValueSize()` | Kích thước value đã serialize, tính bằng byte |

Offset chỉ có ý nghĩa trong phạm vi một partition. Ví dụ `(orders.created, partition 1, offset 25)` xác định vị trí record trong partition 1 của topic `orders.created`; offset 25 ở partition khác là một vị trí khác.

## 2. Nhận ConsumerRecord bằng @KafkaListener

Khai báo tham số `ConsumerRecord<K, V>` trong phương thức listener:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-projection")
    public void onMessage(ConsumerRecord<String, String> record) {
        String key = record.key();
        String payload = record.value();

        System.out.printf(
                "topic=%s partition=%d offset=%d key=%s payload=%s%n",
                record.topic(),
                record.partition(),
                record.offset(),
                key,
                payload);

        // Chuyển payload thành dữ liệu nghiệp vụ và xử lý.
    }
}
```

Listener container của Spring Kafka vẫn quản lý consumer và poll loop. Khi có record, container gọi `onMessage` và truyền đối tượng `ConsumerRecord` vào. Ứng dụng không cần tự gọi `KafkaConsumer.poll()`.

Nếu phương thức chỉ khai báo tham số `String payload`, Spring Kafka có thể chuyển value vào tham số đó. Dùng `ConsumerRecord` khi cần cả key, offset, partition, timestamp hoặc headers.

## 3. Đọc topic, partition và offset

Ba thuộc tính này thường được dùng để truy vết một record:

```java
String topic = record.topic();
int partition = record.partition();
long offset = record.offset();

log.info("Received Kafka record: topic={}, partition={}, offset={}",
        topic, partition, offset);
```

Khi điều tra lỗi, bộ ba topic/partition/offset giúp xác định vị trí record để đối chiếu với log broker hoặc đọc lại bằng Kafka CLI. Ví dụ:

```text
topic=orders.created
partition=2
offset=184
```

Offset là vị trí của record trong log partition, không phải số thứ tự toàn cục và cũng không phải offset đã commit của consumer group. Consumer group có tiến độ commit riêng cho từng partition. Việc nhận được record offset 184 không tự chứng minh group đã commit qua record đó.

Không nên tự cộng offset trong listener để suy ra số record đã xử lý. Log compaction, transaction marker và các tình huống khác có thể khiến offset nhìn thấy không liên tục. Nếu cần đo tiến độ group, hãy đọc committed offset và log end offset bằng công cụ quản trị hoặc metric consumer lag.

## 4. Đọc key và value

`key()` và `value()` trả về kiểu generic đã khai báo cho `ConsumerRecord`:

```java
String orderId = record.key();
String eventJson = record.value();
```

Key thường dùng để xác định thực thể nghiệp vụ và partition affinity. Ví dụ, các sự kiện cùng `orderId` thường được producer định tuyến về cùng partition nếu dùng cùng key serializer, partitioner và partition count.

Value là payload đã được deserializer chuyển thành kiểu Java. Với JSON, cấu hình consumer có thể dùng `JsonDeserializer` để chuyển byte thành DTO:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.example.messaging.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.example.messaging
```

Khi đó listener có thể nhận kiểu cụ thể:

```java
@KafkaListener(topics = "orders.created", groupId = "order-projection")
public void onMessage(
        ConsumerRecord<String, OrderCreatedEvent> record) {
    String orderId = record.key();
    OrderCreatedEvent event = record.value();

    // Xử lý event đã được deserialize.
}
```

Tên class trong cấu hình chỉ là ví dụ và cần thay bằng class thực tế của ứng dụng. Chỉ tin cậy package chứa các DTO event mà ứng dụng kiểm soát; không mở trusted packages rộng hơn nhu cầu.

Nếu deserialization thất bại, listener có thể chưa được gọi vì lỗi xảy ra trước khi tạo được value Java hợp lệ. Với ứng dụng cần chuyển lỗi deserialize vào error handler hoặc dead-letter topic, hãy cấu hình `ErrorHandlingDeserializer` và chiến lược xử lý tương ứng.

## 5. Đọc timestamp và timestamp type

`timestamp()` trả về timestamp của record theo metadata Kafka. Ý nghĩa của nó phụ thuộc cấu hình `message.timestamp.type` của topic/broker:

- `CreateTime`: thường là thời điểm producer gắn vào record.
- `LogAppendTime`: broker gắn thời điểm record được append vào log.
- `NO_TIMESTAMP_TYPE`: không có timestamp hợp lệ theo metadata.

Đọc cả giá trị và loại timestamp:

```java
long timestamp = record.timestamp();
var timestampType = record.timestampType();

log.info("Record timestamp={}, type={}", timestamp, timestampType);
```

Timestamp thường được biểu diễn bằng epoch milliseconds. Không nên mặc định timestamp luôn là thời điểm nghiệp vụ xảy ra: producer có thể gửi timestamp do ứng dụng cung cấp, đồng hồ máy có thể lệch, hoặc broker có thể dùng LogAppendTime. Nếu cần thời điểm nghiệp vụ chính xác, nên lưu `occurredAt` trong event payload với quy ước timezone rõ ràng.

## 6. Đọc headers

Kafka record có thể mang nhiều header. Mỗi header gồm tên và giá trị dạng byte array. Header thường dùng cho metadata như event type, correlation ID, trace ID hoặc source service.

Đọc một header:

```java
import java.nio.charset.StandardCharsets;

var header = record.headers().lastHeader("correlation-id");
String correlationId = header == null || header.value() == null
        ? null
        : new String(header.value(), StandardCharsets.UTF_8);
```

Một tên header có thể xuất hiện nhiều lần. `lastHeader(name)` trả về header cuối cùng có tên đó; nếu cần tất cả giá trị, duyệt collection:

```java
import org.apache.kafka.common.header.Header;

for (Header header : record.headers().headers("trace-tag")) {
    byte[] bytes = header.value();
    String value = bytes == null
            ? null
            : new String(bytes, StandardCharsets.UTF_8);
    log.debug("trace-tag={}", value);
}
```

Chỉ chuyển header sang UTF-8 khi producer và consumer thống nhất encoding đó. Một số header có thể chứa dữ liệu nhị phân hoặc format riêng; không nên ép mọi header thành chuỗi.

Ví dụ producer tạo header:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, String> outgoing = new ProducerRecord<>(
        "orders.created", orderId, eventJson);

outgoing.headers().add(
        "correlation-id",
        correlationId.getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(outgoing);
```

Consumer có thể lấy correlation ID từ header để liên kết log giữa nhiều service. Không đưa password, access token hoặc secret vào Kafka headers.

## 7. Đọc kích thước serialized key và value

`serializedKeySize()` và `serializedValueSize()` trả về kích thước key/value sau serialization, tính bằng byte:

```java
int keySize = record.serializedKeySize();
int valueSize = record.serializedValueSize();

log.debug("Record sizes: key={} bytes, value={} bytes",
        keySize, valueSize);
```

Nếu key hoặc value là `null`, kích thước tương ứng có thể là `-1`. Đây là metadata về kích thước đã serialize, không phải kích thước object Java trong heap. Có thể dùng các trường này để quan sát payload lớn, nhưng không nên xem chúng là tổng kích thước record trên wire vì còn có header và overhead của record batch/protocol.

## 8. ConsumerRecord và Spring Message

Spring Kafka hỗ trợ cả hai kiểu nhận dữ liệu:

1. Nhận `ConsumerRecord<K, V>` khi cần truy cập trực tiếp API metadata của Kafka.
2. Nhận Spring `Message<?>` và lấy metadata thông qua các header Spring Kafka.

Ví dụ nhận Spring Message:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageListener {

    @KafkaListener(topics = "orders.created", groupId = "order-message-view")
    public void onMessage(
            Message<String> message,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition) {
        String payload = message.getPayload();
        Object offset = message.getHeaders().get(KafkaHeaders.OFFSET);

        log.info("Received partition={}, offset={}, payloadSize={}",
                partition, offset, payload.length());
    }
}
```

`ConsumerRecord` phù hợp khi cần các API như `headers()`, `timestampType()` hoặc serialized sizes. Spring `Message` phù hợp khi ứng dụng đã dùng message abstraction của Spring và muốn lấy payload cùng các header được ánh xạ. Hãy chọn kiểu tham số theo thông tin listener thực sự cần.

## 9. Dùng metadata để truy vết và xử lý nghiệp vụ

Metadata có thể hỗ trợ nhiều tình huống:

| Nhu cầu | Trường thường dùng |
| --- | --- |
| Xác định record đến từ đâu | `topic()`, `partition()`, `offset()` |
| Liên kết log giữa các service | Header `correlation-id` hoặc `trace-id` |
| Xác định loại sự kiện | Header event type hoặc trường trong payload |
| Kiểm tra key định tuyến | `key()` |
| Phân tích độ trễ ingest | `timestamp()` và `timestampType()` |
| Phát hiện payload lớn | `serializedKeySize()`, `serializedValueSize()` |

Ví dụ log metadata có chọn lọc:

```java
log.info(
        "Kafka event received: topic={}, partition={}, offset={}, key={}, timestampType={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key(),
        record.timestampType());
```

Không nên log toàn bộ value hoặc tất cả headers một cách mặc định. Payload có thể chứa dữ liệu cá nhân, thông tin đơn hàng hoặc dữ liệu nội bộ. Nên log định danh đã được phép, correlation ID và vị trí record; áp dụng masking hoặc bỏ qua trường nhạy cảm.

## 10. ConsumerRecord không điều khiển offset commit

`record.offset()` chỉ cho biết vị trí của record trong partition. Nó không commit offset và cũng không xác nhận rằng nghiệp vụ đã xử lý thành công.

Spring Kafka listener container quản lý commit theo `AckMode` và cấu hình acknowledgement. Nếu listener xử lý xong nhưng ứng dụng dừng trước khi offset được commit, record có thể được giao lại. Nếu commit tiến quá sớm, ứng dụng có thể bỏ qua record chưa xử lý hoàn tất. Vì vậy:

- Không tự coi `record.offset()` là committed offset.
- Không tự cộng offset để theo dõi tiến độ group.
- Dùng acknowledgement và error handler của container theo chính sách đã thiết kế.
- Làm cho xử lý nghiệp vụ idempotent khi có thể nhận lại record.

Nếu cần thao tác commit thủ công, hãy tìm hiểu `Acknowledgment` và `AckMode` của Spring Kafka; không thực hiện commit chỉ dựa trên việc đọc được `ConsumerRecord`.

## 11. Batch listener nhận danh sách ConsumerRecord

Khi listener được cấu hình batch mode, một lần gọi có thể nhận danh sách `ConsumerRecord`:

```java
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderBatchListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-batch-view",
            containerFactory = "batchKafkaListenerContainerFactory")
    public void onMessages(List<ConsumerRecord<String, String>> records) {
        for (ConsumerRecord<String, String> record : records) {
            log.info("topic={}, partition={}, offset={}",
                    record.topic(), record.partition(), record.offset());
            // Xử lý từng record hoặc gom thành batch nghiệp vụ.
        }
    }
}
```

`batchKafkaListenerContainerFactory` cần được cấu hình với `setBatchListener(true)`. Không thể chỉ đổi tham số phương thức từ một `ConsumerRecord` thành `List<ConsumerRecord>` mà không cấu hình listener container tương ứng.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhầm offset của record với offset đã commit | Đánh giá sai tiến độ consumer group | Dùng consumer group tooling/metrics để đọc committed offset |
| Cho rằng value trong ConsumerRecord luôn là byte[] | Ép kiểu sai hoặc deserialize lần hai | Dùng đúng generic type sau deserializer |
| Không kiểm tra key/value null | NullPointerException hoặc lỗi nghiệp vụ | Kiểm tra null, đặc biệt với tombstone hoặc record không key |
| Giả định header chỉ có một giá trị | Bỏ qua metadata trùng tên | Dùng `headers(name)` khi cần tất cả giá trị |
| Luôn hiểu timestamp là thời điểm nghiệp vụ | Tính sai độ trễ hoặc thứ tự nghiệp vụ | Kiểm tra `timestampType()` và dùng `occurredAt` trong payload nếu cần |
| Log toàn bộ payload và headers | Lộ dữ liệu nhạy cảm, log tăng nhanh | Chỉ log metadata cần thiết và masking dữ liệu |
| Cho rằng listener luôn được gọi dù deserialize lỗi | Lỗi xảy ra trước khi có object listener | Cấu hình `ErrorHandlingDeserializer` và error handler |

## 13. Kết luận

`ConsumerRecord<K, V>` cho phép `@KafkaListener` truy cập cả key/value đã deserialize lẫn metadata của Kafka như topic, partition, offset, timestamp, headers và serialized sizes. Đây là lựa chọn phù hợp khi listener cần truy vết record, xử lý theo key, đọc correlation ID hoặc phân tích nguồn gốc dữ liệu.

Hãy phân biệt offset của record với committed offset của consumer group, hiểu timestamp theo loại mà Kafka cung cấp, xử lý header theo đúng encoding và kiểm tra null trước khi dùng payload. Khi chỉ cần payload, tham số DTO hoặc `Message<?>` có thể gọn hơn; khi cần thông tin đầy đủ của record, `ConsumerRecord` cung cấp giao diện trực tiếp và rõ ràng.

## Tài liệu tham khảo

- [Apache Kafka — ConsumerRecord API](https://kafka.apache.org/documentation/#consumerapi)
- [Spring for Apache Kafka — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/annotation-driven.html)
- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
