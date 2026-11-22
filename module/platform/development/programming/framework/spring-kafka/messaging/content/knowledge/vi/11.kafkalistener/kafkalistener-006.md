# Đọc key, topic, partition và offset

Trong Spring Kafka, một listener thường cần biết nhiều hơn payload của sự kiện. Khi xử lý record, ứng dụng có thể cần đọc key để xác định thực thể nghiệp vụ, topic để biết nguồn dữ liệu, partition để hiểu luồng xử lý song song và offset để đối chiếu tiến độ đọc. `@KafkaListener` cung cấp những thông tin này qua `ConsumerRecord`, qua các tham số `@Header` hoặc qua đối tượng `Message<?>`.

Bốn thông tin này có vai trò khác nhau. Key thường phục vụ định tuyến và nhận diện thực thể; topic xác định log mà record thuộc về; partition xác định log con có thứ tự; offset xác định vị trí của record bên trong partition đó. Đọc đúng từng trường giúp log, trace và xử lý nghiệp vụ chính xác hơn.

## 1. Nhìn vào một Kafka record

Một Kafka record có thể hình dung bằng các trường sau:

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| Key | Giá trị định danh hoặc khóa phân vùng do producer gửi | `order-1024` |
| Value | Payload của sự kiện | `OrderCreated` |
| Topic | Tên topic chứa record | `orders` |
| Partition | Partition chứa record | `2` |
| Offset | Vị trí của record trong partition | `184` |
| Timestamp | Timestamp gắn với record | `1730000000000` |
| Headers | Metadata bổ sung dạng key/value | `trace-id`, `event-type` |

Ví dụ một record có thể được mô tả như sau:

```text
topic      = orders
partition  = 2
offset     = 184
key        = order-1024
value      = {"orderId":"order-1024","total":250000}
timestamp  = 1730000000000
headers    = trace-id=abc-123, event-type=OrderCreated
```

Key và value là dữ liệu do producer gửi; ứng dụng chọn topic đích. Producer partitioner chọn partition dựa trên key và metadata topic, hoặc ứng dụng có thể chỉ định partition tường minh. Kafka cấp offset khi record được ghi vào log của partition đó. Timestamp có thể do producer cung cấp hoặc broker gán tùy cấu hình. Headers chứa metadata bổ sung, thường dùng để truyền correlation ID, trace ID, event type hoặc thông tin phiên bản schema.

## 2. Đọc toàn bộ metadata bằng ConsumerRecord

Cách trực tiếp nhất khi cần cả payload và metadata là nhận `ConsumerRecord<K, V>` trong listener. `K` là kiểu key sau khi deserialize, `V` là kiểu value sau khi deserialize.

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-reader"
    )
    public void onOrder(ConsumerRecord<String, OrderCreated> record) {
        String key = record.key();
        OrderCreated event = record.value();

        String topic = record.topic();
        int partition = record.partition();
        long offset = record.offset();
        long timestamp = record.timestamp();

        log.info(
                "Received order event: key={}, topic={}, partition={}, offset={}, timestamp={}",
                key,
                topic,
                partition,
                offset,
                timestamp
        );

        orderService.process(event);
    }
}
```

Các accessor thường dùng:

| Method | Giá trị trả về | Ghi chú |
|---|---|---|
| `key()` | Key đã deserialize | Có thể là `null` |
| `value()` | Payload đã deserialize | Có thể là `null`, ví dụ tombstone |
| `topic()` | Tên topic | Không phải tên consumer group |
| `partition()` | Số partition | Kiểu `int` |
| `offset()` | Offset của record hiện tại | Kiểu `long`, có ý nghĩa trong partition |
| `timestamp()` | Timestamp của record | Milliseconds từ epoch hoặc giá trị không hợp lệ nếu không có |
| `timestampType()` | Loại timestamp | `CreateTime`, `LogAppendTime` hoặc `NO_TIMESTAMP_TYPE` nếu record không có timestamp |
| `headers()` | Native Kafka headers | Mỗi header có tên và giá trị byte array |
| `serializedKeySize()` | Kích thước key đã serialize | Không phải độ dài chuỗi sau deserialize |
| `serializedValueSize()` | Kích thước value đã serialize | Có thể không có giá trị nếu value null |

`ConsumerRecord` là lựa chọn phù hợp khi cần đối chiếu dữ liệu với Kafka CLI, ghi log metadata, xử lý header gốc hoặc đưa thông tin partition/offset vào luồng nghiệp vụ.

Không nên giữ toàn bộ `ConsumerRecord` hoặc Kafka headers lâu dài như một object nghiệp vụ. Hãy trích xuất những trường cần thiết sang command hoặc context riêng, tránh phụ thuộc chặt vào Kafka API ở tầng domain.

## 3. Đọc key, topic, partition và offset bằng @Header

Nếu listener chỉ cần payload cùng một vài trường metadata, có thể khai báo tham số riêng và dùng `@Header`. Spring Kafka ánh xạ metadata của record vào các message header tương ứng.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
class OrderHeaderListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-header-reader"
    )
    public void onOrder(
            OrderCreated event,
            @Header(KafkaHeaders.RECEIVED_KEY) String key,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
            @Header(KafkaHeaders.OFFSET) long offset) {

        log.info(
                "Received key={}, topic={}, partition={}, offset={}",
                key,
                topic,
                partition,
                offset
        );

        orderService.process(event);
    }
}
```

Các constant quan trọng:

| Constant | Nội dung |
|---|---|
| `KafkaHeaders.RECEIVED_KEY` | Key của record đã nhận |
| `KafkaHeaders.RECEIVED_TOPIC` | Tên topic |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition number |
| `KafkaHeaders.OFFSET` | Offset của record |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp của record |
| `KafkaHeaders.TIMESTAMP_TYPE` | Loại timestamp |
| `KafkaHeaders.NATIVE_HEADERS` | Native Kafka headers |

Dùng `@Header` làm listener gọn khi chỉ cần vài metadata field. Khi cần nhiều trường, native headers hoặc API của Kafka consumer, `ConsumerRecord` thường dễ đọc và ít tham số hơn.

### Xử lý key có thể null

Kafka cho phép record không có key trong nhiều trường hợp. Nếu listener khai báo key là tham số bắt buộc nhưng record thực tế có key null, ứng dụng cần cân nhắc cách binding và xử lý null. Có thể đánh dấu header không bắt buộc:

```java
@KafkaListener(topics = "orders", groupId = "order-header-reader")
public void onOrder(
        OrderCreated event,
        @Header(value = KafkaHeaders.RECEIVED_KEY, required = false)
        String key,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    if (key == null) {
        log.warn(
                "Received an order event without key: topic={}, partition={}, offset={}",
                topic,
                partition,
                offset
        );
    }

    orderService.process(event);
}
```

Với listener cần xử lý chính xác null key hoặc tombstone, nhận `ConsumerRecord` thường rõ ràng hơn vì có thể kiểm tra trực tiếp `record.key()` và `record.value()`.

## 4. Đọc metadata qua Message<?> và message headers

Spring Kafka có thể chuyển record thành Spring Messaging `Message<?>`. Payload nằm trong `getPayload()`, còn metadata nằm trong `getHeaders()`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
class OrderMessageListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-message-reader"
    )
    public void onOrder(Message<OrderCreated> message) {
        OrderCreated event = message.getPayload();

        Object key = message.getHeaders().get(KafkaHeaders.RECEIVED_KEY);
        String topic = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders()
                .get(KafkaHeaders.OFFSET, Long.class);

        log.info(
                "Received key={}, topic={}, partition={}, offset={}",
                key,
                topic,
                partition,
                offset
        );

        orderService.process(event);
    }
}
```

Cách này hữu ích khi ứng dụng đã dùng Spring Messaging hoặc muốn truyền payload và headers như một message thống nhất. Giá trị trong headers là object; nên đọc bằng kiểu phù hợp và kiểm tra null nếu header không được bảo đảm có mặt.

Không nhầm Spring message headers với native Kafka headers. Các trường `RECEIVED_TOPIC`, `RECEIVED_PARTITION` và `OFFSET` là metadata được Spring ánh xạ. Header do producer tự gửi nằm trong native Kafka headers và có cách đọc riêng.

## 5. Phân biệt key với topic, partition và offset

Bốn trường này thường xuất hiện cạnh nhau trong log nhưng có ý nghĩa khác nhau:

| Trường | Ai quyết định? | Có duy nhất toàn cluster không? | Dùng để làm gì? |
|---|---|---|---|
| Key | Producer | Không | Định danh, partitioning, xử lý theo thực thể |
| Topic | Producer hoặc cấu hình ứng dụng chọn | Không | Chọn luồng dữ liệu |
| Partition | Producer partitioner hoặc producer chỉ định tường minh | Không | Chia log và xử lý song song |
| Offset | Kafka cấp trong partition | Không | Xác định vị trí record trong log |

### Key ảnh hưởng đến partition như thế nào?

Với partitioner mặc định, producer thường hash key để chọn partition. Các record có cùng key thường được gửi đến cùng partition khi số partition và partitioning strategy không đổi. Điều này hỗ trợ giữ thứ tự record theo một thực thể, ví dụ mọi sự kiện của `order-1024` đi cùng partition.

Tuy nhiên:

- Key không phải partition number.
- Key không phải offset.
- Cùng key không đảm bảo cùng partition nếu số partition hoặc partitioner thay đổi.
- Nếu key là null, partitioner có thể chọn partition theo cơ chế phân phối khác.
- Producer có thể chỉ định partition tường minh, khi đó partition được chọn trực tiếp.

Ví dụ gửi record có key:

```java
kafkaTemplate.send(
        "orders",
        order.getOrderId(),
        new OrderCreated(order.getOrderId(), order.getTotal())
);
```

Producer dùng key `order.getOrderId()` để định tuyến theo partitioner. Listener nhận lại key qua `record.key()` hoặc `KafkaHeaders.RECEIVED_KEY`.

## 6. Hiểu offset đúng phạm vi

Offset là vị trí của record trong một partition, không phải số thứ tự toàn topic. Ví dụ:

```text
orders-0: offset 0, 1, 2, 3, 4, ...
orders-1: offset 0, 1, 2, 3, 4, ...
orders-2: offset 0, 1, 2, 3, 4, ...
```

Record `orders-0` offset `15` và record `orders-2` offset `15` là hai record khác nhau. Vì vậy, khi ghi log hoặc lưu checkpoint, phải gắn offset với topic và partition.

Offset có các đặc điểm:

- Kafka cấp offset theo thứ tự ghi trong từng partition.
- Offset của record hiện tại lấy từ `record.offset()`.
- Offset không phải thời gian; dùng `record.timestamp()` nếu cần thời điểm.
- Offset có thể không liên tục trong dữ liệu consumer quan sát, ví dụ compacted topic hoặc transaction bị abort.
- Offset không nên dùng làm ID nghiệp vụ hoặc khóa duy nhất toàn hệ thống.

Nếu cần lưu tiến độ xử lý, một checkpoint tối thiểu phải gắn với consumer group, topic và partition; giá trị offset commit là vị trí tiếp theo cần đọc, trong khi `record.offset()` là offset của record hiện tại.

## 7. Đọc headers gốc của Kafka record

Kafka headers là tập các cặp tên và byte array. Một record có thể có nhiều header cùng tên, vì vậy không nên mặc định mỗi tên chỉ xuất hiện một lần.

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;

void logHeaders(ConsumerRecord<String, OrderCreated> record) {
    Headers headers = record.headers();

    for (Header header : headers) {
        String name = header.key();
        byte[] value = header.value();

        String decoded = value == null
                ? null
                : new String(value, java.nio.charset.StandardCharsets.UTF_8);

        log.debug("Kafka header: name={}, value={}", name, decoded);
    }
}
```

Nếu chỉ cần một header cụ thể, có thể dùng `headers().lastHeader("trace-id")`. Phương thức này trả về header cuối cùng cùng tên hoặc null nếu không tồn tại. Giá trị header vẫn là byte array, cần giải mã theo encoding mà producer đã sử dụng.

Không nên chuyển mọi header sang chuỗi UTF-8 một cách mù quáng: header có thể chứa dữ liệu nhị phân hoặc encoding khác. Hãy quy định encoding và schema cho header do hệ thống tự định nghĩa.

### Lấy trace ID hoặc event type

Producer có thể gửi thêm metadata:

```java
import org.apache.kafka.common.header.internals.RecordHeader;
import org.apache.kafka.clients.producer.ProducerRecord;
import java.nio.charset.StandardCharsets;

ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>("orders", orderId, event);

record.headers().add(
        new RecordHeader(
                "trace-id",
                traceId.getBytes(StandardCharsets.UTF_8)
        )
);

record.headers().add(
        new RecordHeader(
                "event-type",
                "OrderCreated".getBytes(StandardCharsets.UTF_8)
        )
);

kafkaTemplate.send(record);
```

Consumer đọc lại:

```java
Header traceHeader = record.headers().lastHeader("trace-id");

String traceId = traceHeader == null
        ? null
        : new String(
                traceHeader.value(),
                StandardCharsets.UTF_8
        );
```

Với tracing production, nên ưu tiên cơ chế propagation context chuẩn mà hệ thống đang dùng (ví dụ OpenTelemetry instrumentation) thay vì tự tạo header không theo quy ước. Không ghi token hoặc dữ liệu nhạy cảm vào header.

## 8. Đọc metadata trong batch listener

Listener mặc định thường xử lý từng record. Nếu cấu hình container factory ở batch mode, listener có thể nhận danh sách record. Mỗi record có key, topic, partition và offset riêng:

```java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderBatchListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-batch-reader",
            containerFactory = "batchFactory"
    )
    public void onOrders(
            List<ConsumerRecord<String, OrderCreated>> records) {

        for (ConsumerRecord<String, OrderCreated> record : records) {
            log.info(
                    "Batch record key={}, topic={}, partition={}, offset={}",
                    record.key(),
                    record.topic(),
                    record.partition(),
                    record.offset()
            );
        }

        orderService.processBatch(
                records.stream()
                        .map(ConsumerRecord::value)
                        .toList()
        );
    }
}
```

Batch listener cần dùng container factory đã bật batch listener:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated> batchFactory(
        ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    configurer.configure(factory, consumerFactory);
    factory.setBatchListener(true);
    return factory;
}
```

Khi batch có record từ nhiều partition, không được giả định offset liền nhau hoặc mọi record cùng partition. Hãy lấy metadata từ từng record. Nếu batch listener cần xử lý lỗi một phần, phải thiết kế rõ record nào đã xử lý và cách acknowledgement/retry tương ứng.

## 9. Deserializer quyết định kiểu key và value

Kiểu generic của `ConsumerRecord<K, V>` phải phù hợp với key deserializer và value deserializer. Ví dụ key là chuỗi và value là JSON object:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-reader
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.OrderCreated
        spring.json.trusted.packages: com.example.orders
```

Với cấu hình này, listener có thể nhận `ConsumerRecord<String, OrderCreated>`. Nếu deserializer không khớp với dữ liệu thực tế, listener có thể gặp lỗi deserialize trước khi method được gọi. Khi đó, không thể trông chờ `record.value()` để tự xử lý payload lỗi; cần cấu hình error handling/deserialization handling phù hợp.

Một số ứng dụng dùng `ErrorHandlingDeserializer` để chuyển lỗi deserialize vào cơ chế xử lý lỗi của Spring Kafka. Việc chọn kiểu deserializer phải thống nhất giữa producer và consumer, đặc biệt khi nhiều service cùng ghi và đọc một topic.

## 10. Tombstone và null value trong compacted topic

Trong compacted topic, record có key nhưng value null thường được dùng làm tombstone để biểu thị xóa trạng thái của key. Listener phải phân biệt trường hợp này với một payload hợp lệ:

```java
@KafkaListener(topics = "customer-state", groupId = "customer-projection")
public void onCustomerState(
        ConsumerRecord<String, CustomerState> record) {

    String customerId = record.key();

    if (record.value() == null) {
        customerProjection.delete(customerId);
        return;
    }

    customerProjection.upsert(record.value());
}
```

Tombstone vẫn có topic, partition, offset và key; chỉ value là null. Nếu code gọi trực tiếp `record.value().get...()` mà không kiểm tra null, listener có thể ném `NullPointerException` và liên tục retry cùng record.

Null key cũng cần được xử lý riêng. Đối với dữ liệu nghiệp vụ cần định tuyến theo thực thể, nên xác định rõ key có bắt buộc hay không và từ chối/đưa vào luồng lỗi nếu record thiếu key theo hợp đồng dữ liệu.

## 11. Dùng metadata để log, trace và điều tra sự cố

Một log hữu ích nên bao gồm các trường đủ để tìm lại record trong Kafka:

```java
log.info(
        "Consumed event: topic={}, partition={}, offset={}, key={}, eventType={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key(),
        record.value() == null
                ? "tombstone"
                : record.value().getClass().getSimpleName()
);
```

Khi cần đối chiếu một record, dùng ba trường `topic`, `partition` và `offset` làm vị trí. Key giúp nhận diện thực thể nghiệp vụ; timestamp giúp đặt sự kiện vào dòng thời gian. Không dùng riêng offset vì offset chỉ duy nhất trong phạm vi một partition.

Tránh log toàn bộ payload hoặc headers nếu chúng chứa thông tin cá nhân, token hay dữ liệu bí mật. Cũng không nên đưa key có cardinality rất cao vào metric label; log hoặc trace thường phù hợp hơn metric để lưu giá trị cụ thể.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `record.key()` trả về null | Producer gửi record không có key hoặc serializer/deserializer xử lý không như mong đợi | Xác định key có bắt buộc trong hợp đồng event; kiểm tra producer |
| `record.value()` trả về null | Tombstone hoặc record null value | Kiểm tra key và xử lý tombstone trước khi truy cập payload |
| Offset bị trùng giữa nhiều record | So sánh offset mà bỏ qua topic/partition | Luôn đối chiếu topic + partition + offset |
| Offset không tăng liên tục | Compaction, transaction abort hoặc record không được consumer nhìn thấy | Không giả định offset liền kề |
| Partition khác dự kiến | Key, partitioner hoặc số partition đã thay đổi | Kiểm tra producer key, partitioner và topic metadata |
| Header không đọc được | Header là byte array, sai encoding hoặc không tồn tại | Kiểm tra null và giải mã đúng encoding |
| Listener nhận sai kiểu payload | Deserializer hoặc default type không khớp | Kiểm tra consumer properties và schema |
| Batch có nhiều partition | Poll trả record từ các partition được gán | Đọc metadata từng record, không giả định một partition duy nhất |
| Log không tìm thấy client nào từ record | `ConsumerRecord` không cung cấp trực tiếp client ID | Ghi client ID từ cấu hình hoặc logging context riêng |

## 13. Checklist khi viết @KafkaListener

1. Dùng `ConsumerRecord<K, V>` khi cần đầy đủ key, payload, topic, partition, offset, timestamp và native headers.
2. Dùng `@Header` khi chỉ cần một vài metadata field.
3. Dùng `Message<T>` khi ứng dụng muốn payload và Spring message headers trong cùng một abstraction.
4. Chọn generic type khớp với key/value deserializer.
5. Xử lý null key và null value nếu hợp đồng dữ liệu cho phép.
6. Luôn gắn offset với topic và partition khi log hoặc lưu checkpoint.
7. Không giả định batch chỉ chứa record từ một partition.
8. Đọc native header dưới dạng byte array và giải mã theo quy ước.
9. Không xem key là offset hoặc partition; key chỉ ảnh hưởng đến partitioning qua partitioner.
10. Kiểm tra metadata cùng lỗi deserialize, retry và rebalance khi điều tra listener.

Khi listener đọc đúng key, topic, partition và offset, ứng dụng có thể định danh sự kiện, hiểu nguồn dữ liệu và truy vết chính xác vị trí record trong Kafka. `ConsumerRecord` là lựa chọn đầy đủ nhất cho xử lý cần metadata; `@Header` và `Message<?>` giúp listener gọn hơn khi chỉ cần một phần thông tin.
