# Tạo `ProducerRecord` với topic, key, headers và partition

Trong Kafka Java Producer, `ProducerRecord` là đối tượng mô tả một bản ghi mà ứng dụng muốn gửi tới Kafka. Nó chứa tên topic, key, value và có thể kèm partition, timestamp cùng headers. Việc tạo record đúng giúp producer định tuyến dữ liệu hợp lý, giữ ordering theo thực thể nghiệp vụ, truyền metadata để truy vết và gửi bản ghi tới đúng partition khi có yêu cầu cụ thể.

`ProducerRecord` chỉ mô tả bản ghi cần gửi. Việc gửi thực tế được thực hiện bởi `KafkaProducer.send(...)` hoặc `KafkaTemplate.send(...)` trong Spring Kafka. Bài viết tập trung vào cách tạo record, chọn constructor, sử dụng key/partition, thêm headers và hiểu những quyết định định tuyến có ảnh hưởng tới hệ thống.

## 1. `ProducerRecord` gồm những thành phần nào?

Một Kafka record thường có các thành phần sau:

| Thành phần | Kiểu dữ liệu trong Java | Vai trò |
|---|---|---|
| `topic` | `String` | Tên topic nhận bản ghi |
| `partition` | `Integer` hoặc `null` | Partition đích; `null` để producer partitioner quyết định |
| `timestamp` | `Long` hoặc `null` | Thời điểm gắn với record, tính bằng milliseconds từ Unix epoch |
| `key` | `K` hoặc `null` | Định danh dùng cho routing, grouping và compaction |
| `value` | `V` hoặc `null` | Payload của bản ghi |
| `headers` | `Headers` | Metadata key-value dạng byte array đi kèm record |

Trong Java, kiểu `K` và `V` được quyết định bởi serializer mà producer sử dụng. Ví dụ `ProducerRecord<String, String>` có key và value là chuỗi; producer cần `StringSerializer` cho cả hai. Nếu value là một object nghiệp vụ, cần serializer phù hợp như JSON, Avro hoặc Protobuf.

Ví dụ record đơn giản:

```java
ProducerRecord<String, String> record =
        new ProducerRecord<>("orders.events", "order-2048", "OrderPlaced");
```

Record trên có topic `orders.events`, key `order-2048` và value `OrderPlaced`. Partition chưa được chỉ định, timestamp cũng chưa được chỉ định và headers ban đầu rỗng.

## 2. Các constructor thường dùng

Kafka Java Client cung cấp nhiều constructor để tạo `ProducerRecord`. Những overload thường dùng gồm:

```java
// Chỉ có topic và value.
new ProducerRecord<>(topic, value);

// Topic, key và value.
new ProducerRecord<>(topic, key, value);

// Chỉ định partition cùng key và value.
new ProducerRecord<>(topic, partition, key, value);

// Chỉ định partition, timestamp, key và value.
new ProducerRecord<>(topic, partition, timestamp, key, value);

// Chỉ định đầy đủ cả headers.
new ProducerRecord<>(topic, partition, timestamp, key, value, headers);
```

Các tham số `partition` và `timestamp` có thể nhận `null` trong những overload tương ứng để producer/broker áp dụng hành vi mặc định. `topic` phải có giá trị hợp lệ; partition được chỉ định phải là số không âm và tồn tại trong topic tại thời điểm gửi.

### Khi nào dùng overload nào?

- Dùng `(topic, value)` khi không cần key và muốn partitioner tự chọn partition.
- Dùng `(topic, key, value)` khi cần routing theo key và ordering theo một thực thể.
- Dùng overload có `partition` khi ứng dụng có quy tắc định tuyến rõ ràng và cần gửi trực tiếp tới partition cụ thể.
- Dùng overload có `timestamp` khi ứng dụng cần cung cấp thời điểm record thay vì để producer gán thời gian gửi.
- Dùng overload có `headers` hoặc thêm headers sau khi tạo record khi cần truyền metadata.

Không nên chỉ chọn constructor dài nhất vì nó có nhiều tham số hơn. Hãy chỉ truyền những metadata mà ứng dụng thực sự cần kiểm soát.

## 3. Topic: nơi lưu và phân loại record

Topic là tên logic của luồng dữ liệu. ProducerRecord phải chỉ rõ topic đích, ví dụ:

```java
String topic = "orders.events";
ProducerRecord<String, String> record =
        new ProducerRecord<>(topic, "order-2048", "OrderPlaced");
```

Topic cần tồn tại trước khi gửi nếu broker không bật cơ chế tự tạo topic hoặc ứng dụng không có quyền tạo topic. Trong môi trường production, nên quản lý topic bằng quy trình provisioning riêng thay vì phụ thuộc auto creation, vì partition count, replication factor và cleanup policy là các quyết định vận hành quan trọng.

Một topic có thể có nhiều partition. Topic xác định luồng logic; partition xác định log cụ thể mà record được ghi vào. ProducerRecord có thể chỉ định topic mà không chỉ định partition, để producer chọn partition theo key hoặc partitioner.

## 4. Key: định danh record và lựa chọn partition

Key thường đại diện cho thực thể nghiệp vụ mà các sự kiện liên quan cần được xử lý theo thứ tự. Ví dụ:

- `orderId` cho các sự kiện của một đơn hàng.
- `accountId` cho các thay đổi của tài khoản.
- `customerId` cho các cập nhật hồ sơ khách hàng.
- `deviceId` cho các sự kiện của một thiết bị.

Ví dụ gửi sự kiện theo `orderId`:

```java
String orderId = "order-2048";
String payload = "{\"status\":\"PLACED\"}";

ProducerRecord<String, String> record =
        new ProducerRecord<>("orders.events", orderId, payload);
```

Khi không chỉ định partition, partitioner sẽ chọn partition. Với partitioner mặc định của Kafka Java Producer, key khác null được dùng để tính partition; cùng key thường được định tuyến vào cùng partition khi partition count và thuật toán partitioning không thay đổi. Điều này giúp các record cùng key nằm trong một log có thứ tự.

Key không phải là một cơ chế bảo đảm thứ tự toàn topic. Kafka bảo đảm thứ tự trong từng partition. Hai key khác nhau có thể cùng partition; hai partition khác nhau không có một thứ tự tổng duy nhất.

### Chọn key theo phạm vi ordering

Nếu nghiệp vụ cần thứ tự theo đơn hàng, dùng `orderId`. Nếu cần thứ tự theo tài khoản, dùng `accountId`. Dùng `customerId` chỉ khi các sự kiện của cùng khách hàng cần được xử lý theo thứ tự. Key cũng ảnh hưởng đến phân phối tải: một key có lưu lượng quá lớn có thể tạo hot partition.

Tránh dùng một hằng số hoặc trường có ít giá trị như `status`, `country` hay `eventType` làm key nếu chúng không phải phạm vi ordering mong muốn. Những key này có thể gom phần lớn record vào một vài partition.

### Record không có key

Key có thể là `null`:

```java
ProducerRecord<String, String> record =
        new ProducerRecord<>("telemetry.events", null, "temperature=28.5");
```

Khi key null và partition không được chỉ định, producer partitioner chọn partition theo chính sách của client. Các phiên bản Kafka Java Producer hiện đại thường dùng sticky partitioning cho record null-key để gom record vào một partition trong một khoảng thời gian/batch, sau đó chuyển partition nhằm cải thiện batching. Hành vi cụ thể phụ thuộc phiên bản và partitioner được cấu hình; không nên giả định mỗi record null-key luôn được round-robin.

Null key phù hợp khi không cần ordering theo một thực thể cụ thể. Nếu cần compact topic để giữ trạng thái mới nhất theo key, record phải có key ổn định.

## 5. Partition: khi nào chỉ định trực tiếp?

Thông thường, nên để partitioner chọn partition dựa trên key. Tuy nhiên, `ProducerRecord` cho phép chỉ định partition cụ thể:

```java
int partition = 2;
String key = "order-2048";
String value = "{\"status\":\"PAID\"}";

ProducerRecord<String, String> record =
        new ProducerRecord<>("orders.events", partition, key, value);
```

Khi `partition` khác null, producer gửi record tới partition đó và không dùng key để chọn partition. Key vẫn được lưu trong record để consumer đọc, nhưng không còn quyết định routing cho lần gửi này.

Chỉ định partition trực tiếp có thể hữu ích khi:

- Ứng dụng có bảng ánh xạ hoặc quy tắc shard riêng đã được quản lý.
- Cần đưa dữ liệu thử nghiệm vào một partition xác định để kiểm tra.
- Một pipeline migration cần kiểm soát vị trí ghi theo kế hoạch.

Không nên hard-code partition ID trong nghiệp vụ thông thường. Nếu topic tăng hoặc thay đổi partition, code có thể gửi tới partition không tồn tại hoặc phá vỡ quy tắc phân phối/ordering mà hệ thống mong đợi. Nếu nhiều producer cùng ghi một key nhưng một số producer chỉ định partition thủ công còn số khác dùng partitioner, cùng key có thể xuất hiện ở các partition khác nhau.

Partition ID bắt đầu từ 0. Ví dụ topic có ba partition thì các ID hợp lệ là 0, 1 và 2. Constructor kiểm tra partition không âm; broker/client còn cần xác định partition đó thực sự tồn tại trong topic.

## 6. Timestamp: thời điểm gắn với record

`timestamp` là thời gian tính bằng milliseconds kể từ Unix epoch. Ứng dụng có thể chỉ định timestamp khi tạo record:

```java
long occurredAt = System.currentTimeMillis();

ProducerRecord<String, String> record =
        new ProducerRecord<>(
                "orders.events",
                null,          // để partitioner chọn
                occurredAt,
                "order-2048",
                "OrderPlaced");
```

Nếu không chỉ định timestamp, producer gán thời gian gửi theo cơ chế của client. Giá trị timestamp cuối cùng được lưu trong record còn phụ thuộc `message.timestamp.type` của topic/broker:

- `CreateTime`: timestamp do producer cung cấp (hoặc producer tự gán nếu ứng dụng không truyền) được sử dụng.
- `LogAppendTime`: broker thay timestamp bằng thời điểm broker append record vào log.

Timestamp không thay thế `occurredAt` trong payload nếu ứng dụng cần lưu chính xác thời điểm nghiệp vụ xảy ra. Khi event được tạo ở một hệ thống rồi gửi trễ, timestamp của Kafka record và thời điểm nghiệp vụ có thể khác nhau. Nên xác định rõ ý nghĩa từng trường thời gian.

## 7. Headers: metadata đi kèm record

Headers là tập cặp key-value mà tên header là chuỗi và value là byte array. Chúng phù hợp cho metadata như:

- `correlation-id`: liên kết các record thuộc cùng quy trình nghiệp vụ.
- `event-type`: loại sự kiện, ví dụ `OrderPlaced`.
- `event-version`: phiên bản hợp đồng dữ liệu.
- `traceparent` và `tracestate`: trace context theo W3C.
- `causation-id`: sự kiện hoặc lệnh trực tiếp gây ra sự kiện hiện tại.

Thêm headers sau khi tạo record:

```java
import java.nio.charset.StandardCharsets;

record.headers().add(
        "correlation-id",
        "checkout-7b91".getBytes(StandardCharsets.UTF_8));

record.headers().add(
        "event-type",
        "OrderPlaced".getBytes(StandardCharsets.UTF_8));

record.headers().add(
        "event-version",
        "1".getBytes(StandardCharsets.UTF_8));
```

Có thể tạo `ProducerRecord` với một tập headers ngay trong constructor cuối cùng bằng `Iterable<Header>`. Cách thêm sau khi tạo record thường dễ đọc hơn khi ứng dụng xây dựng metadata theo từng bước.

### Đọc headers ở consumer

```java
Header header = record.headers().lastHeader("correlation-id");
String correlationId = header == null
        ? null
        : new String(header.value(), StandardCharsets.UTF_8);
```

Một record có thể có nhiều header trùng tên. `lastHeader(name)` trả về header cuối cùng có tên đó; `headers().headers(name)` cho phép duyệt các giá trị cùng tên. Hợp đồng tích hợp cần quy định header nào được phép lặp và consumer chọn giá trị nào.

Kafka không tự diễn giải `correlation-id` hay `event-version`. Broker lưu và chuyển tiếp metadata; ứng dụng producer/consumer phải thống nhất tên, encoding, tính bắt buộc và hành vi khi header thiếu hoặc không hợp lệ. Không đưa mật khẩu, access token, dữ liệu cá nhân nhạy cảm hoặc payload lớn vào headers.

## 8. Ví dụ đầy đủ: tạo record có key, partition và headers

Ví dụ sau cấu hình Kafka Producer với `StringSerializer`, tạo một record cho đơn hàng, gắn correlation ID và event metadata rồi gửi bất đồng bộ:

```java
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

public class OrderEventPublisher {

    public static void main(String[] args) {
        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class.getName());
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class.getName());
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, "true");

        try (KafkaProducer<String, String> producer = new KafkaProducer<>(props)) {
            String topic = "orders.events";
            String orderId = "order-2048";
            String payload = "{\"orderId\":\"order-2048\",\"status\":\"PLACED\"}";

            ProducerRecord<String, String> record =
                    new ProducerRecord<>(topic, orderId, payload);

            record.headers().add("correlation-id",
                    "checkout-7b91".getBytes(StandardCharsets.UTF_8));
            record.headers().add("event-type",
                    "OrderPlaced".getBytes(StandardCharsets.UTF_8));
            record.headers().add("event-version",
                    "1".getBytes(StandardCharsets.UTF_8));

            producer.send(record, (metadata, exception) -> {
                if (exception != null) {
                    System.err.println("Send failed: " + exception.getMessage());
                    return;
                }

                System.out.printf(
                        "Sent topic=%s partition=%d offset=%d key=%s%n",
                        metadata.topic(), metadata.partition(),
                        metadata.offset(), orderId);
            });
        }
    }
}
```

Trong ví dụ, partition không được chỉ định nên producer partitioner chọn partition dựa trên key. `acks=all` và idempotent producer là cấu hình gửi của KafkaProducer; chúng không phải thuộc tính của `ProducerRecord`. Callback nhận kết quả gửi và metadata như topic, partition, offset khi request hoàn tất.

Trong ứng dụng thực tế, cần xử lý lỗi theo loại lỗi, retry/backoff phù hợp và quan sát callback. `send()` là bất đồng bộ; không nên gọi `flush()` sau từng record nếu muốn giữ batching và throughput. Khi đóng producer, `close()` chờ xử lý các request còn lại theo hành vi cấu hình của client.

## 9. Ví dụ chỉ định partition và timestamp

Nếu ứng dụng có yêu cầu gửi trực tiếp tới partition 1 và gắn timestamp nghiệp vụ:

```java
long eventTime = System.currentTimeMillis();

ProducerRecord<String, String> record =
        new ProducerRecord<>(
                "orders.events",
                1,             // partition ID
                eventTime,     // timestamp milliseconds
                "order-2048",  // key
                "OrderPaid"); // value

record.headers().add("event-type",
        "OrderPaid".getBytes(StandardCharsets.UTF_8));

producer.send(record);
```

Ở đây partition 1 được dùng trực tiếp; key `order-2048` không tham gia chọn partition. Chỉ dùng cách này nếu ứng dụng chủ động chịu trách nhiệm duy trì quy tắc định tuyến khi topic thay đổi.

## 10. Gửi `ProducerRecord` bằng Spring Kafka

Spring Kafka `KafkaTemplate` hỗ trợ gửi trực tiếp một `ProducerRecord`:

```java
ProducerRecord<String, String> record =
        new ProducerRecord<>("orders.events", "order-2048", payload);

record.headers().add("correlation-id",
        correlationId.getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(record);
```

`KafkaTemplate` chuyển record tới Kafka Producer bên dưới. Các quy tắc về key, partition, timestamp, serializer và headers vẫn là quy tắc của Kafka client. Kiểu kết quả của `send` phụ thuộc phiên bản Spring Kafka: các phiên bản hiện đại trả `CompletableFuture<SendResult<K,V>>`, còn phiên bản cũ có thể dùng `ListenableFuture`.

Nếu dùng Spring `Message<?>`, Spring Kafka cũng hỗ trợ ánh xạ message headers sang Kafka record headers. Khi cần kiểm soát chính xác partition, timestamp hoặc headers Kafka-specific, tạo `ProducerRecord` tường minh giúp thấy rõ dữ liệu sẽ được gửi.

## 11. Serializer và validation trước khi gửi

`ProducerRecord` giữ key/value ở kiểu Java trước khi serialization. Khi gọi `send`, Kafka Producer dùng:

- `key.serializer` để chuyển key thành byte array.
- `value.serializer` để chuyển value thành byte array.
- Headers đã là byte array nên ứng dụng tự chọn encoding khi thêm chúng.

Ví dụ cấu hình serializer cho chuỗi:

```java
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
```

Trước khi gửi, nên kiểm tra:

1. Topic đúng và đã được provision.
2. Key có đúng phạm vi ordering và partitioning không.
3. Partition được chỉ định có tồn tại không.
4. Serializer tương thích với kiểu key/value thực tế.
5. Header có tên, encoding và giá trị hợp lệ theo hợp đồng.
6. Timestamp có đúng đơn vị milliseconds và đúng ý nghĩa không.
7. Kích thước payload cùng headers không vượt giới hạn record/request của producer và broker.

Key hoặc value có thể là `null` về mặt API. Tuy nhiên, ý nghĩa phụ thuộc topic và ứng dụng. Trong compacted topic, key khác null cùng value null biểu diễn tombstone. Với topic thông thường, null value là payload null; không tự động có nghĩa xóa một entity.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `SerializationException` | Serializer không hỗ trợ kiểu key/value hoặc dữ liệu không hợp lệ | Kiểm tra generic type, serializer và schema/payload |
| `UnknownTopicOrPartitionException` | Topic hoặc partition đích không tồn tại tại thời điểm gửi | Provision topic và xác nhận partition ID |
| Record cùng key xuất hiện ở nhiều partition | Producer chỉ định partition thủ công, custom partitioner khác nhau hoặc partition count thay đổi | Thống nhất chiến lược routing và migration partition |
| Consumer không đọc được correlation ID | Producer không thêm header hoặc encoding/tên header không thống nhất | Kiểm tra `record.headers()` ở hai đầu và chuẩn hóa UTF-8/name |
| Thứ tự nghiệp vụ không như mong đợi | Các record được gửi tới nhiều partition hoặc producer gửi đồng thời không theo thứ tự mong muốn | Chọn key theo entity, giữ partition mapping và kiểm soát thứ tự gửi |
| Timestamp không như mong đợi | Broker dùng `LogAppendTime` hoặc producer truyền sai đơn vị | Kiểm tra `message.timestamp.type` và dùng milliseconds |
| Gửi thành công ở callback nhưng nghiệp vụ downstream chưa hoàn tất | Producer acknowledgement chỉ xác nhận phía Kafka | Theo dõi consumer và trạng thái xử lý ở downstream riêng biệt |

## 13. Ghi nhớ

`ProducerRecord` là hợp đồng dữ liệu ở phía producer: `topic` xác định luồng, `key` hỗ trợ routing và ordering theo entity, `partition` có thể ghi đè lựa chọn của partitioner, `timestamp` gắn mốc thời gian và `headers` mang metadata dạng byte array. `value` chứa payload được serializer chuyển thành bytes.

Trong phần lớn trường hợp, hãy chọn key ổn định theo phạm vi ordering nghiệp vụ và để partitioner chọn partition. Chỉ định partition trực tiếp khi có quy tắc routing được quản lý rõ ràng. Thêm headers cho metadata cần truyền qua pipeline, dùng timestamp đúng ý nghĩa và cấu hình serializer tương thích. Khi record được tạo đúng, Kafka Producer có thể gửi dữ liệu nhất quán, dễ truy vết và mở rộng theo partition.
