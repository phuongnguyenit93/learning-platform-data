# ConsumerRecord gồm những thông tin gì

Khi Spring Kafka gọi một phương thức `@KafkaListener`, ứng dụng có thể nhận trực tiếp giá trị đã deserialize hoặc nhận toàn bộ `ConsumerRecord<K, V>`. Dùng `ConsumerRecord` khi cần đọc cả payload lẫn metadata mà Kafka gắn với record: topic, partition, offset, timestamp, key, value, headers, kích thước dữ liệu đã serialize và leader epoch.

Những thông tin này giúp ứng dụng định vị record trong log, theo dõi nguồn gốc sự kiện, ghi log có thể đối chiếu, xử lý tombstone và chẩn đoán consumer. Tuy nhiên, `ConsumerRecord` mô tả một record được đọc; nó không chứa toàn bộ trạng thái của consumer group, chẳng hạn offset đã commit hoặc group ID.

## 1. ConsumerRecord là gì?

`ConsumerRecord<K, V>` là đối tượng Kafka client đại diện cho một record mà consumer nhận được. Hai tham số generic `K` và `V` là kiểu key và value sau khi deserializer chuyển dữ liệu từ byte sang kiểu Java mà ứng dụng sử dụng.

Ví dụ, với `StringDeserializer` cho cả key và value, listener có thể nhận `ConsumerRecord<String, String>`. Nếu value được deserialize thành `OrderEvent`, listener có thể nhận `ConsumerRecord<String, OrderEvent>`.

```text
Kafka partition
      |
      |  record tại offset 42
      v
+-----------------------------------------------+
| ConsumerRecord<String, String>                |
|                                               |
| topic, partition, offset                      |
| timestamp, timestampType, leaderEpoch         |
| key, value                                    |
| headers                                      |
| serializedKeySize, serializedValueSize        |
+-----------------------------------------------+
      |
      v
Spring Kafka @KafkaListener
```

Một record có thể có key hoặc value bằng `null`. Ví dụ, record có key nhưng value `null` thường được dùng làm tombstone trong topic compact. Vì thế, không nên giả định mọi record đều có payload khác null.

## 2. Các trường định vị record trong Kafka

Ba trường `topic()`, `partition()` và `offset()` xác định vị trí của record trong log Kafka.

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `topic()` | `String` | Tên topic chứa record |
| `partition()` | `int` | Số hiệu partition chứa record |
| `offset()` | `long` | Vị trí record trong partition đó |

Ví dụ, record có `topic=orders.events`, `partition=2`, `offset=42` được định vị tại offset 42 của partition 2 thuộc topic `orders.events`.

Hãy dùng bộ ba này khi ghi log, đối chiếu lỗi, lưu dấu vết xử lý hoặc trao đổi với người vận hành. Offset chỉ có ý nghĩa trong một partition; offset 42 ở partition 0 không phải cùng vị trí với offset 42 ở partition 2.

Kafka bảo đảm thứ tự record trong cùng partition. Nếu một topic có nhiều partition, bộ ba định vị không tạo ra thứ tự toàn cục giữa chúng. Khi cần giữ thứ tự theo đơn hàng, producer thường dùng `orderId` làm key để các sự kiện của cùng đơn hàng đi về cùng partition theo partitioner đã cấu hình.

### Offset của record và offset đã commit

`record.offset()` là vị trí của chính record đang được xử lý. Nó không phải offset đã commit của consumer group.

Kafka lưu tiến độ đã commit cho từng cặp consumer group và topic-partition. Giá trị commit biểu diễn vị trí tiếp theo cần đọc. Ví dụ, sau khi xử lý thành công record ở offset `42`, consumer thường commit offset `43` để biểu thị vị trí đọc tiếp theo.

| Giá trị | Ví dụ | Ý nghĩa |
|---|---:|---|
| `record.offset()` | `42` | Offset của record hiện tại |
| Offset commit | `43` | Vị trí tiếp theo consumer group sẽ đọc |

Việc commit do Kafka consumer hoặc Spring Kafka listener container quản lý theo acknowledgement mode. Không thể suy ra trạng thái commit chỉ từ `ConsumerRecord`.

## 3. Timestamp và timestamp type

Hai phương thức sau cung cấp thông tin thời gian của record:

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `timestamp()` | `long` | Timestamp theo epoch milliseconds |
| `timestampType()` | `TimestampType` | Kiểu timestamp mà record đang sử dụng |

Timestamp có thể biểu diễn thời điểm producer tạo record (`CreateTime`) hoặc thời điểm broker append record vào log (`LogAppendTime`), tùy cấu hình topic `message.timestamp.type`. Vì vậy, khi dùng timestamp để đo độ trễ hoặc tổng hợp theo thời gian nghiệp vụ, hãy kiểm tra cả `timestamp()` và `timestampType()`.

Nếu record không có timestamp hợp lệ, Kafka client có thể trả về giá trị sentinel âm (`ConsumerRecord.NO_TIMESTAMP`). Không chuyển giá trị đó thành ngày giờ trước khi kiểm tra.

Ví dụ chuyển timestamp sang `Instant`:

```java
long timestamp = record.timestamp();

if (timestamp >= 0) {
    Instant occurredAt = Instant.ofEpochMilli(timestamp);
    System.out.println("record time=" + occurredAt);
}

System.out.println("timestamp type=" + record.timestampType());
```

Timestamp không thay thế offset. Record có timestamp nhỏ hơn vẫn có thể nằm ở offset lớn hơn nếu sự kiện đến trễ; Kafka không sắp xếp lại log theo timestamp.

## 4. Key và value

Hai trường `key()` và `value()` trả về dữ liệu sau khi consumer deserializer chuyển đổi:

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `key()` | `K` | Key của record sau deserialize |
| `value()` | `V` | Value của record sau deserialize |

Key thường dùng để định tuyến record đến partition và nhận diện thực thể nghiệp vụ. Ví dụ, `order-1001` là key của mọi sự kiện thuộc đơn hàng đó. Value chứa payload, chẳng hạn JSON biểu diễn `OrderCreated` hoặc `OrderPaid`.

Key và value có thể là `null`:

- Record không có key có thể được phân vùng theo chiến lược partitioner của producer.
- Record có key nhưng value `null` thường là tombstone, mang ý nghĩa xóa key trong topic dùng compaction.
- Nếu ứng dụng không xử lý được null, cần kiểm tra trước khi truy cập thuộc tính hoặc deserialize thành đối tượng nghiệp vụ.

Ví dụ listener nhận payload dạng chuỗi:

```java
String orderId = record.key();
String payload = record.value();

if (payload == null) {
    // Xử lý tombstone hoặc quy tắc null của ứng dụng.
    return;
}

process(orderId, payload);
```

Khi dùng JSON deserializer, kiểu generic của listener phải phù hợp với kiểu đối tượng mà consumer factory cấu hình. `ConsumerRecord<String, OrderEvent>` giúp ứng dụng làm việc với `OrderEvent` sau deserialize, nhưng không làm thay đổi byte đã lưu trên Kafka.

## 5. Headers: metadata mở rộng của record

`headers()` trả về tập header của record. Header là cặp tên và giá trị byte, thường dùng để truyền metadata nhỏ xuyên suốt luồng xử lý mà không phải nhúng tất cả vào payload.

Các trường hợp sử dụng phổ biến:

- `trace-id` hoặc `correlation-id` để liên kết log giữa producer, Kafka và consumer.
- `event-type` để nhận diện loại sự kiện.
- `schema-version` để xác định phiên bản cấu trúc payload.
- Metadata định tuyến hoặc nguồn phát sinh sự kiện khi kiến trúc yêu cầu.

Kafka cho phép nhiều header trùng tên trên cùng một record. Có thể dùng `lastHeader(name)` để lấy header cuối cùng có tên đó, hoặc `headers(name)` để duyệt tất cả giá trị cùng tên.

Ví dụ đọc `trace-id`:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Header;

Header traceHeader = record.headers().lastHeader("trace-id");
String traceId = null;

if (traceHeader != null && traceHeader.value() != null) {
    traceId = new String(traceHeader.value(), StandardCharsets.UTF_8);
}
```

Nếu cần đọc nhiều header cùng tên:

```java
for (Header header : record.headers().headers("tag")) {
    byte[] bytes = header.value();
    String tag = bytes == null
            ? null
            : new String(bytes, StandardCharsets.UTF_8);

    System.out.println("tag=" + tag);
}
```

Header value là byte, nên producer và consumer phải thống nhất encoding hoặc định dạng. Không nên giả định mọi header đều là UTF-8. Tránh đưa mật khẩu, token truy cập, dữ liệu cá nhân nhạy cảm hoặc payload lớn vào header; header nên chứa metadata cần thiết và có quy ước rõ ràng.

## 6. Kích thước key và value đã serialize

`ConsumerRecord` cung cấp hai phương thức để quan sát kích thước byte của key và value:

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `serializedKeySize()` | `int` | Kích thước key ở dạng serialized, tính bằng byte |
| `serializedValueSize()` | `int` | Kích thước value ở dạng serialized, tính bằng byte |

Nếu key hoặc value là `null`, kích thước tương ứng có thể là `-1`. Đây là kích thước dữ liệu serialized, không phải kích thước object Java trong heap và cũng không phải toàn bộ kích thước record trên mạng. Nó không bao gồm đầy đủ overhead của protocol, batch, headers và các cấu trúc lưu trữ khác.

Hai giá trị này hữu ích khi điều tra payload tăng bất thường hoặc phân tích phân bố kích thước message. Ví dụ:

```java
int keyBytes = record.serializedKeySize();
int valueBytes = record.serializedValueSize();

if (valueBytes >= 0 && valueBytes > 256 * 1024) {
    log.warn(
            "Large Kafka value: topic={}, partition={}, offset={}, bytes={}",
            record.topic(), record.partition(), record.offset(), valueBytes
    );
}
```

Ngưỡng `256 KiB` chỉ là ví dụ minh họa, không phải giới hạn mặc định của Kafka. Hệ thống cần xác định ngưỡng theo kích thước message cho phép, dung lượng broker, fetch configuration và yêu cầu nghiệp vụ.

## 7. Leader epoch

`leaderEpoch()` cung cấp leader epoch gắn với record dưới dạng `Optional<Integer>` trong các phiên bản Kafka client hỗ trợ API này. Leader epoch là số thế hệ của leader partition, tăng khi partition chuyển sang leader epoch mới. Kafka dùng thông tin này trong các cơ chế quản lý tính nhất quán log và phát hiện tình huống log bị truncate khi leader thay đổi.

Leader epoch không phải offset, timestamp hay consumer group generation. Ứng dụng thông thường ít khi cần dùng trực tiếp trường này trong xử lý nghiệp vụ, nhưng nó hữu ích khi chẩn đoán tình huống failover hoặc đối chiếu metadata ở mức Kafka client.

Ví dụ:

```java
record.leaderEpoch().ifPresent(epoch ->
        log.debug(
                "Kafka record leader epoch: topic={}, partition={}, epoch={}",
                record.topic(), record.partition(), epoch
        )
);
```

Nếu `Optional` rỗng, metadata leader epoch không có sẵn cho record đó. Không nên tự suy ra epoch từ offset hoặc số lần rebalance của consumer group.

## 8. Ví dụ đọc ConsumerRecord trong Spring Kafka

Ví dụ sau kết hợp các trường thường dùng trong một listener. Giả sử producer và consumer đã cấu hình `StringSerializer`/`StringDeserializer` cho key và value.

```java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderConsumer {

    private static final Logger log = LoggerFactory.getLogger(OrderConsumer.class);

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection"
    )
    public void consume(ConsumerRecord<String, String> record) {
        String topic = record.topic();
        int partition = record.partition();
        long offset = record.offset();
        String orderId = record.key();
        String payload = record.value();

        long timestamp = record.timestamp();
        String eventTime = timestamp < 0
                ? "unknown"
                : Instant.ofEpochMilli(timestamp).toString();

        Header traceHeader = record.headers().lastHeader("trace-id");
        String traceId = traceHeader == null || traceHeader.value() == null
                ? "missing"
                : new String(traceHeader.value(), StandardCharsets.UTF_8);

        log.info(
                "Consume Kafka record: topic={}, partition={}, offset={}, "
                        + "key={}, timestamp={}, timestampType={}, "
                        + "keyBytes={}, valueBytes={}, traceId={}",
                topic,
                partition,
                offset,
                orderId,
                eventTime,
                record.timestampType(),
                record.serializedKeySize(),
                record.serializedValueSize(),
                traceId
        );

        if (payload == null) {
            handleTombstone(orderId);
            return;
        }

        processOrderEvent(orderId, payload);
    }

    private void handleTombstone(String orderId) {
        // Xử lý tín hiệu xóa theo quy tắc của ứng dụng.
    }

    private void processOrderEvent(String orderId, String payload) {
        // Deserialize payload nghiệp vụ nếu cần và xử lý sự kiện.
    }
}
```

Đoạn code tập trung vào việc đọc metadata. Trong ứng dụng thật, `log` cần được khai báo bằng logger của dự án, ví dụ SLF4J. Cũng cần cân nhắc mức log và chính sách che dữ liệu: không ghi toàn bộ payload, key nhạy cảm hoặc header chứa thông tin bí mật vào log production.

Nếu muốn đọc leader epoch, có thể thêm:

```java
record.leaderEpoch().ifPresent(epoch ->
        log.debug("leaderEpoch={}", epoch)
);
```

## 9. ConsumerRecord không chứa những thông tin nào?

Một số dữ liệu thường bị nhầm là thuộc tính của record, nhưng thực tế nằm ở consumer, listener container hoặc consumer group:

| Thông tin | Nơi lấy phù hợp |
|---|---|
| Consumer group ID | Cấu hình `group.id`, `@KafkaListener(groupId = ...)` hoặc cấu hình container |
| Offset đã commit của group | Kafka consumer group offset hoặc API quản trị/consumer phù hợp |
| Danh sách partition đang được gán cho consumer | `KafkaConsumer.assignment()` hoặc sự kiện phân công của listener container |
| Thời điểm ứng dụng bắt đầu xử lý | Ghi nhận bằng đồng hồ trong listener |
| Số lần retry/delivery attempt của Spring Kafka | Cơ chế retry và metadata/header do Spring Kafka cung cấp, tùy cấu hình và phiên bản |
| Trạng thái transaction của producer | Cấu hình và trạng thái transaction, không nằm trong `ConsumerRecord` |

Đặc biệt, `record.offset()` không cho biết record đã được commit hay chưa. Việc xử lý thành công và commit offset là hai bước có liên quan nhưng khác nhau. Với acknowledgement mode của Spring Kafka, listener container quyết định thời điểm commit theo cấu hình. Nếu cần manual acknowledgement, hãy acknowledge sau khi nghiệp vụ hoàn thành và hiểu rõ cách container xử lý batch, lỗi và retry.

## 10. Dùng metadata đúng mục đích

| Nhu cầu | Trường nên xem |
|---|---|
| Xác định record trong log | `topic()`, `partition()`, `offset()` |
| Biết thời điểm gắn với record | `timestamp()`, `timestampType()` |
| Định danh thực thể hoặc định tuyến nghiệp vụ | `key()` |
| Đọc nội dung sự kiện | `value()` |
| Truyền trace ID, correlation ID, schema version | `headers()` |
| Điều tra payload có kích thước lớn | `serializedKeySize()`, `serializedValueSize()` |
| Phân tích metadata thế hệ leader partition | `leaderEpoch()` |

Khi ghi log để hỗ trợ vận hành, bộ ba topic-partition-offset thường là thông tin đầu tiên cần có để truy vết một record. Có thể bổ sung key, timestamp type và trace ID nếu chúng hữu ích cho điều tra. Hãy giữ log có cấu trúc, giới hạn kích thước và tránh ghi dữ liệu nhạy cảm.

Hiểu đúng `ConsumerRecord` giúp listener trong Spring Kafka biết record đến từ đâu, đang ở vị trí nào trong log và mang theo metadata gì. Tách biệt metadata của record với trạng thái commit của consumer group sẽ giúp việc xử lý, retry, quan sát và khôi phục luồng sự kiện chính xác hơn.
