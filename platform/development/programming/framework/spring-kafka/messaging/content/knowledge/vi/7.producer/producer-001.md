# ProducerRecord và các trường dữ liệu

Trong Kafka Producer API, `ProducerRecord<K, V>` là đối tượng mô tả một record mà producer muốn gửi vào topic. Nó chứa tên topic, partition tùy chọn, timestamp tùy chọn, key, value và headers. Spring Kafka sử dụng chính đối tượng này khi gọi `KafkaTemplate.send(...)`.

Hiểu rõ từng trường giúp bạn quyết định record sẽ đi đâu, được định tuyến như thế nào, mang dữ liệu gì và consumer có thể đọc metadata nào để xử lý. Trong nhiều trường hợp, chỉ cần gửi topic, key và value; khi cần kiểm soát partition, timestamp hoặc metadata, có thể tạo `ProducerRecord` tường minh.

## 1. ProducerRecord là gì?

`ProducerRecord<K, V>` là một cấu trúc dữ liệu phía producer, trong đó `K` là kiểu key và `V` là kiểu value. Ví dụ:

```java
ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>("orders.events", "O100", event);
```

Record này mô tả dữ liệu gửi vào topic `orders.events`, dùng chuỗi `O100` làm key và object `event` làm value. Producer sẽ serialize key và value thành byte trước khi gửi đến broker. `ProducerRecord` là đối tượng ở phía ứng dụng; nó không phải định dạng byte được lưu trực tiếp trong Kafka.

Các trường chính của `ProducerRecord`:

| Trường | Kiểu | Vai trò |
|---|---|---|
| `topic` | `String` | Tên topic đích. Đây là trường bắt buộc. |
| `partition` | `Integer` | Partition đích do ứng dụng chỉ định; `null` để producer partitioner chọn. |
| `timestamp` | `Long` | Timestamp của record tính bằng mili giây Unix epoch; `null` để producer/broker áp dụng mặc định. |
| `key` | `K` | Key dùng cho partitioning và giúp consumer nhận diện nhóm record liên quan; có thể `null`. |
| `value` | `V` | Payload chính của record; có thể `null`. |
| `headers` | `Headers` | Metadata dạng các header key/value, trong đó value là mảng byte. |

Các trường có thể truy cập qua `topic()`, `partition()`, `timestamp()`, `key()`, `value()` và `headers()`.

## 2. Topic — nơi record được gửi đến

`topic` xác định luồng dữ liệu mà record thuộc về. Ví dụ:

```java
private static final String ORDER_TOPIC = "orders.events";

ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>(ORDER_TOPIC, event.orderId(), event);
```

Tên topic phải khớp với topic mà cluster cho phép producer ghi. Topic có thể được tạo trước bằng công cụ quản trị hoặc được tạo tự động nếu cluster và ứng dụng cho phép auto topic creation. Trong production, thường nên quản lý topic rõ ràng về partition count, replication factor và cấu hình retention/compaction.

Producer gửi record đến một topic cụ thể; consumer group đăng ký topic đó để nhận record. Tên topic là metadata định tuyến, không phải một phần của payload nghiệp vụ.

## 3. Partition — nơi record được append

Trường `partition` cho phép producer chỉ định partition cụ thể. Partition index bắt đầu từ 0 và phải tồn tại trong topic. Nếu chỉ định partition không hợp lệ, thao tác gửi sẽ thất bại.

Thông thường, nên để `partition` là `null` để partitioner chọn dựa trên key hoặc chiến lược phân phối của producer:

```java
// Để partitioner quyết định partition dựa trên key.
ProducerRecord<String, OrderCreatedEvent> byKey =
        new ProducerRecord<>("orders.events", event.orderId(), event);

// Chỉ định rõ partition 2 (index bắt đầu từ 0).
ProducerRecord<String, OrderCreatedEvent> fixedPartition =
        new ProducerRecord<>("orders.events", 2, event.orderId(), event);
```

Khi ứng dụng chỉ định partition, producer sử dụng partition đó thay vì nhờ partitioner chọn. Việc này hữu ích trong một số trường hợp đặc biệt như phân vùng theo quy tắc riêng đã được kiểm soát, nhưng dễ tạo lệch tải hoặc phá vỡ chiến lược ordering nếu dùng tùy tiện.

Nếu không chỉ định partition:

- Khi key khác `null`, partitioner mặc định thường dùng key đã serialize để định tuyến các record có cùng key vào cùng partition, với điều kiện số partition và cách serialize/partitioning ổn định.
- Khi key là `null`, producer dùng chiến lược phân phối không key của client. Chi tiết có thể phụ thuộc phiên bản Kafka client và cấu hình partitioner; không nên dựa vào nó để giữ thứ tự theo một thực thể nghiệp vụ.

Kafka bảo đảm thứ tự append trong một partition. Nếu các event của cùng đơn hàng cần được xử lý theo thứ tự, hãy dùng `orderId` làm key và giữ partitioning strategy ổn định.

## 4. Timestamp — thời điểm gắn với record

`timestamp` là thời gian tính bằng mili giây kể từ Unix epoch (UTC). Có thể chỉ định timestamp khi tạo record:

```java
long eventTime = event.occurredAt().toEpochMilli();

ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>(
                "orders.events",
                null,       // partition: để partitioner chọn
                eventTime,  // timestamp tính bằng milliseconds
                event.orderId(),
                event
        );
```

Nếu không cung cấp timestamp, producer thường gắn thời điểm hiện tại khi gửi record. Timestamp thực tế mà consumer nhìn thấy còn phụ thuộc cấu hình `message.timestamp.type` của topic:

- `CreateTime`: dùng timestamp do producer cung cấp; nếu producer không cung cấp thì client tạo timestamp hiện tại.
- `LogAppendTime`: broker ghi đè timestamp bằng thời điểm broker append record vào log.

Timestamp hữu ích cho xử lý theo thời gian, đo độ trễ hoặc phân tích luồng sự kiện. Nó không thay thế offset và không phải cơ chế đảm bảo thứ tự. Đồng hồ của các producer có thể lệch nhau; hai record ở partition khác nhau cũng không có thứ tự tổng thể chỉ vì timestamp khác nhau.

## 5. Key — khóa định tuyến và liên kết record

`key` là dữ liệu được serialize bằng key serializer. Với partitioner mặc định, key là cơ sở quan trọng để chọn partition. Ví dụ, `orderId` giúp các thay đổi của cùng một đơn hàng đi vào cùng partition:

```java
ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>("orders.events", event.orderId(), event);
```

Key có thể được dùng để:

- Định tuyến các record liên quan về cùng partition.
- Giữ thứ tự các thay đổi của cùng một aggregate trong partition đó.
- Cho phép consumer hoặc stream processor nhóm dữ liệu theo thực thể.
- Làm key cho compaction nếu topic dùng `cleanup.policy=compact`.

Key không nhất thiết là ID duy nhất của từng event. Ví dụ `eventId` định danh một lần phát sinh event, còn `orderId` gom nhiều event thuộc cùng đơn hàng. Chọn key theo yêu cầu partitioning và xử lý nghiệp vụ.

Key có thể là `null`. Khi đó producer vẫn có thể gửi record, nhưng không có key để partitioner định tuyến ổn định theo thực thể. Nếu topic compacted cần cập nhật hoặc xóa trạng thái theo key, record phải có key phù hợp.

## 6. Value — payload của record

`value` là nội dung chính producer gửi đến Kafka. Đây thường là event hoặc message đã được mô hình hóa thành DTO, Java class hoặc Java `record`:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        Instant occurredAt,
        BigDecimal total
) {}
```

Khi gửi object này, producer cần value serializer tương thích. Ví dụ, `StringSerializer` phù hợp với value kiểu `String`; JSON serializer phù hợp với object nếu consumer có deserializer hoặc message converter tương ứng. Producer và consumer phải thống nhất schema, cách mã hóa và phiên bản dữ liệu.

`value` cũng có thể là `null`. Trong topic compacted, record có key khác `null` và value `null` được gọi là **tombstone**, dùng để đánh dấu xóa trạng thái của key đó. Trong topic không compact, null value chỉ là record không có payload; ý nghĩa xóa không tự phát sinh nếu ứng dụng không quy ước như vậy.

Không nhầm Kafka null value với chuỗi JSON `"null"` hoặc một JSON document có nội dung `null`. Hai trường hợp sau là payload byte thông thường sau serialization, không phải null value của Kafka.

## 7. Headers — metadata đi kèm record

`headers` chứa các cặp tên header và giá trị byte. Header phù hợp cho metadata phục vụ vận chuyển hoặc xử lý như:

- `event-type`: loại event, ví dụ `OrderCreated`.
- `correlation-id`: liên kết các message thuộc cùng một luồng xử lý.
- `trace-id`: liên kết log và trace giữa các service.
- `schema-version`: phiên bản hợp đồng dữ liệu.

Ví dụ thêm header:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>("orders.events", event.orderId(), event);

record.headers().add(
        "event-type",
        "OrderCreated".getBytes(StandardCharsets.UTF_8)
);
record.headers().add(
        "schema-version",
        "1".getBytes(StandardCharsets.UTF_8)
);
```

Header value là `byte[]`, do đó producer và consumer cần thống nhất encoding. Với chuỗi thông thường, UTF-8 là lựa chọn phổ biến. Header không thay thế payload: đừng đưa toàn bộ dữ liệu nghiệp vụ vào header hoặc dùng header để mang nội dung lớn.

Consumer có thể đọc header từ `ConsumerRecord`:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.common.header.Header;

Header eventTypeHeader = record.headers().lastHeader("event-type");

if (eventTypeHeader != null) {
    String eventType = new String(
            eventTypeHeader.value(),
            StandardCharsets.UTF_8
    );
}
```

Kafka headers có thể chứa nhiều header trùng tên. `lastHeader(name)` trả về header cuối cùng có tên đó; nếu cần xử lý tất cả giá trị, có thể duyệt `headers().headers(name)`.

## 8. Các constructor thường dùng

`ProducerRecord` có nhiều constructor để tạo record theo mức thông tin cần thiết. Một số dạng thường gặp:

```java
// Topic và value; key để null.
new ProducerRecord<String, OrderCreatedEvent>("orders.events", event);

// Topic, key và value.
new ProducerRecord<String, OrderCreatedEvent>(
        "orders.events", event.orderId(), event);

// Topic, partition, key và value.
new ProducerRecord<String, OrderCreatedEvent>(
        "orders.events", 2, event.orderId(), event);

// Topic, partition, timestamp, key và value.
new ProducerRecord<String, OrderCreatedEvent>(
        "orders.events", 2, System.currentTimeMillis(), event.orderId(), event);
```

Constructor đầy đủ còn cho phép truyền `Iterable<Header>` để tạo record với tập headers ngay từ đầu. Nếu chỉ cần thêm một vài header sau khi tạo, có thể dùng `record.headers().add(...)` như ví dụ ở trên.

| Cách tạo | Khi nên dùng |
|---|---|
| `topic, value` | Payload không cần key và partitioner có thể phân phối record. |
| `topic, key, value` | Trường hợp phổ biến, cần định tuyến theo key. |
| `topic, partition, key, value` | Cần chỉ định partition cụ thể theo chiến lược đã thiết kế. |
| `topic, partition, timestamp, key, value` | Cần kiểm soát timestamp cùng partition. |
| Constructor có headers | Muốn khởi tạo đầy đủ metadata ngay khi tạo record. |

Nếu không có yêu cầu đặc biệt, constructor `topic, key, value` thường là lựa chọn rõ ràng và dễ bảo trì nhất.

## 9. Gửi ProducerRecord bằng KafkaTemplate

Spring Kafka cung cấp `KafkaTemplate` để gửi `ProducerRecord`:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private static final String TOPIC = "orders.events";

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreatedEvent event) {
        ProducerRecord<String, OrderCreatedEvent> record =
                new ProducerRecord<>(TOPIC, event.orderId(), event);

        record.headers().add(
                "event-type",
                "OrderCreated".getBytes(StandardCharsets.UTF_8)
        );

        kafkaTemplate.send(record);
    }
}
```

`KafkaTemplate.send(record)` là thao tác bất đồng bộ. Trong ứng dụng thực tế, hãy quan sát future/callback để biết gửi thành công hay thất bại và ghi nhận metadata trả về khi cần. Việc gọi `send` không đồng nghĩa broker đã xác nhận ghi thành công.

Ví dụ theo dõi kết quả gửi ở các phiên bản Spring Kafka hiện đại trả về `CompletableFuture`:

```java
kafkaTemplate.send(record).whenComplete((result, exception) -> {
    if (exception != null) {
        // Ghi log, retry hoặc chuyển xử lý lỗi theo chính sách ứng dụng.
        return;
    }

    var metadata = result.getRecordMetadata();
    System.out.printf(
            "topic=%s partition=%d offset=%d%n",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
    );
});
```

Metadata kết quả giúp xác định record đã được broker ghi vào partition và offset nào. Đây là thông tin vận hành; không nên dùng offset thay cho ID nghiệp vụ của event.

## 10. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Gửi sai tên topic | Record không đến luồng mà consumer mong đợi hoặc gửi vào topic ngoài ý muốn. | Dùng hằng số/configuration tập trung và kiểm tra topic trong môi trường đích. |
| Chỉ định partition không tồn tại | Broker từ chối gửi record. | Kiểm tra partition count; chỉ định partition khi thật sự cần. |
| Dùng key không ổn định | Event của cùng thực thể có thể vào các partition khác nhau. | Chuẩn hóa key và key serializer ở mọi producer. |
| Key/value serializer không khớp kiểu dữ liệu | Lỗi serialization hoặc consumer không giải mã được payload. | Cấu hình serializer/deserializer và schema tương thích. |
| Gửi chuỗi `"null"` thay vì value `null` | Kafka lưu payload chữ, không tạo tombstone. | Truyền Java `null` nếu cần tombstone trên topic compacted. |
| Đưa payload lớn vào headers | Tăng overhead và khó quản lý metadata. | Giữ headers cho metadata nhỏ, payload nằm trong value. |
| Không theo dõi kết quả `send` | Không phát hiện lỗi gửi bất đồng bộ. | Xử lý future/callback và quan sát lỗi producer. |

## 11. Ghi nhớ

- `ProducerRecord<K, V>` mô tả record phía producer với topic, partition, timestamp, key, value và headers.
- `topic` xác định luồng đích; `partition` có thể chỉ định rõ hoặc để partitioner chọn.
- `key` thường dùng để định tuyến và giữ các record của cùng thực thể trong một partition.
- `value` là payload được serialize; null value trên topic compacted có key là tombstone.
- `timestamp` tính bằng mili giây epoch và chịu ảnh hưởng của `message.timestamp.type`.
- `headers` mang metadata dạng byte, không thay thế payload nghiệp vụ.
- `KafkaTemplate.send(ProducerRecord)` gửi record bất đồng bộ; cần xử lý kết quả để phát hiện lỗi và lấy metadata broker.

Khi tạo một `ProducerRecord`, hãy xác định rõ topic nào nhận dữ liệu, key nào bảo vệ yêu cầu partitioning, value nào là hợp đồng payload, timestamp có ý nghĩa gì và headers cần metadata nào. Khi các trường này được thiết kế nhất quán, producer và consumer sẽ phối hợp dễ dàng hơn và luồng Kafka có thể được vận hành, theo dõi đáng tin cậy.
