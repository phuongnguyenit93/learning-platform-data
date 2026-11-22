# Deserializer và cách đọc ConsumerRecord

Kafka lưu key, value và headers của record dưới dạng byte. Ứng dụng Java thường làm việc với String, JSON object hoặc domain object, vì vậy consumer cần một bước chuyển đổi dữ liệu từ byte sang kiểu Java. Thành phần thực hiện việc này là **Deserializer**.

Sau khi deserialize, Kafka Consumer trả về các đối tượng **ConsumerRecord**. Mỗi record cung cấp không chỉ key và value đã chuyển đổi, mà còn có topic, partition, offset, timestamp, headers và kích thước dữ liệu đã serialize. Đọc đúng các trường này giúp ứng dụng xử lý nghiệp vụ, truy vết sự kiện, kiểm tra thứ tự và chẩn đoán lỗi dữ liệu.

Điểm cần nhớ là Deserializer quyết định cách byte trở thành object Java, còn ConsumerRecord cho biết record đó đến từ đâu và mang metadata gì. Nếu chỉ đọc value mà bỏ qua key, offset, timestamp và headers, ứng dụng có thể mất thông tin quan trọng để xử lý idempotency, ordering và tracing.

## 1. Luồng dữ liệu từ broker đến object Java

Producer serialize key và value thành byte trước khi gửi. Broker lưu record batch trong partition log. Khi consumer fetch dữ liệu, Kafka client nhận byte và gọi Deserializer tương ứng cho key và value.

~~~mermaid
flowchart LR
    A["Producer object"] --> B["Serializer"]
    B --> C["Key/value bytes"]
    C --> D["Kafka topic partition"]
    D --> E["Consumer fetch"]
    E --> F["Key/Value Deserializer"]
    F --> G["ConsumerRecord Java"]
    G --> H["Business handler"]
~~~

Mỗi consumer có thể dùng kiểu Java khác nhau cho cùng một topic, miễn là serializer và deserializer tương thích với định dạng byte đã được ghi.

Ví dụ:

- Producer dùng StringSerializer cho key và JSON serializer cho value.
- Consumer dùng StringDeserializer cho key và một JSON Deserializer cho value.
- Consumer khác có thể dùng Avro hoặc Protobuf deserializer nếu dữ liệu được phát theo schema tương ứng.

Kafka broker không tự hiểu object Java hoặc JSON. Broker lưu byte và metadata của record; quá trình chuyển byte thành object diễn ra trong client.

## 2. Deserializer trong Kafka Java

Kafka cung cấp interface **org.apache.kafka.common.serialization.Deserializer<T>**. Một Deserializer nhận topic và byte array, sau đó trả về object kiểu T.

Hợp đồng cơ bản gồm các phương thức:

| Phương thức | Vai trò |
|---|---|
| configure(configs, isKey) | Nhận cấu hình khi client khởi tạo Deserializer |
| deserialize(topic, data) | Chuyển byte thành object Java |
| deserialize(topic, headers, data) | Phiên bản có headers để xử lý metadata đi kèm record |
| close() | Giải phóng tài nguyên khi Deserializer kết thúc vòng đời |

Trong nhiều implementation, configure và close có thể để mặc định nếu không cần tài nguyên hoặc cấu hình riêng. Phương thức deserialize là phần quan trọng nhất.

### 2.1. Deserializer cho key và value

Consumer có hai cấu hình riêng:

- **key.deserializer:** chuyển key bytes thành kiểu key Java.
- **value.deserializer:** chuyển value bytes thành kiểu value Java.

Ví dụ consumer đọc key là String và value là byte array:

~~~java
Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");
properties.put("group.id", "order-reader");
properties.put("enable.auto.commit", false);
properties.put(
    "key.deserializer",
    StringDeserializer.class.getName()
);
properties.put(
    "value.deserializer",
    ByteArrayDeserializer.class.getName()
);
~~~

Dùng ByteArrayDeserializer hữu ích khi ứng dụng muốn tự kiểm soát bước parse, lưu raw payload hoặc xử lý nhiều phiên bản schema. Khi đó ConsumerRecord có kiểu tương ứng, ví dụ ConsumerRecord<String, byte[]>.

Với StringDeserializer, byte được giải mã thành chuỗi theo encoding mà serializer/deserializer sử dụng. Với JSON, Kafka client thuần không cung cấp một JSON deserializer mặc định; ứng dụng có thể viết custom Deserializer hoặc dùng thư viện tích hợp như Spring Kafka JsonDeserializer.

### 2.2. Cấu hình consumer dùng Deserializer

Ví dụ tạo KafkaConsumer với key và value là String:

~~~java
Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");
properties.put("group.id", "order-reader");
properties.put(
    "key.deserializer",
    StringDeserializer.class.getName()
);
properties.put(
    "value.deserializer",
    StringDeserializer.class.getName()
);
properties.put("auto.offset.reset", "earliest");

try (KafkaConsumer<String, String> consumer =
         new KafkaConsumer<>(properties)) {
    consumer.subscribe(List.of("orders"));
    // Tiếp tục poll và xử lý record.
}
~~~

Consumer khởi tạo Deserializer theo cấu hình. Trong suốt vòng đời consumer, các deserializer này được sử dụng khi poll nhận record. Khi consumer đóng, client giải phóng tài nguyên theo lifecycle của nó; custom Deserializer có tài nguyên riêng cần triển khai close phù hợp.

## 3. Viết custom Deserializer cho JSON

Giả sử producer gửi sự kiện OrderCreated dưới dạng JSON:

~~~json
{
  "orderId": "order-42",
  "customerId": "customer-7",
  "totalAmount": 125000
}
~~~

Ứng dụng cần chuyển byte JSON thành object Java:

~~~java
public record OrderCreated(
    String orderId,
    String customerId,
    long totalAmount
) {}
~~~

Có thể viết custom Deserializer bằng Jackson:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.common.errors.SerializationException;
import org.apache.kafka.common.serialization.Deserializer;

import java.io.IOException;

public class OrderCreatedDeserializer
        implements Deserializer<OrderCreated> {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public OrderCreated deserialize(String topic, byte[] data) {
        if (data == null) {
            return null;
        }

        if (data.length == 0) {
            throw new SerializationException(
                "Empty payload in topic " + topic
            );
        }

        try {
            return objectMapper.readValue(data, OrderCreated.class);
        } catch (IOException exception) {
            throw new SerializationException(
                "Cannot deserialize OrderCreated from topic " + topic,
                exception
            );
        }
    }
}
~~~

Trong ví dụ này:

- Kafka null value được truyền vào Deserializer dưới dạng data null.
- Mảng byte rỗng được xem là payload rỗng và bị từ chối theo quy ước của ứng dụng.
- JSON hợp lệ được chuyển thành OrderCreated.
- JSON sai cấu trúc hoặc không tương thích kiểu dữ liệu tạo SerializationException.

ObjectMapper nên được cấu hình xong trước khi sử dụng. Jackson ObjectMapper có thể được dùng đồng thời sau khi cấu hình hoàn tất, nhưng không nên thay đổi cấu hình mapper trong lúc consumer đang deserialize.

### 3.1. Cấu hình custom Deserializer

~~~java
properties.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class
);
properties.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    OrderCreatedDeserializer.class
);
~~~

Cấu hình này cho biết key là String và value là OrderCreated. Tên class cần nằm trên classpath của ứng dụng consumer.

Với custom Deserializer cần tham số khởi tạo hoặc phụ thuộc bên ngoài, không nên giả định Kafka client sẽ tự inject dependency như Spring bean. Có thể dùng constructor nhận Deserializer instance khi API phù hợp, hoặc dùng cơ chế cấu hình/ủy quyền của framework.

### 3.2. Phân biệt Kafka null, payload rỗng và JSON null

Ba trường hợp sau không giống nhau:

| Dữ liệu trước deserialize | Byte được đưa vào Deserializer | Ý nghĩa |
|---|---|---|
| Kafka null value | null | Record không có payload; trên compacted topic có thể là tombstone nếu key khác null |
| Empty payload | byte array độ dài 0 | Có payload nhưng không có byte |
| JSON literal null | Các byte biểu diễn chữ null | Payload có thật, nội dung JSON biểu diễn giá trị null |

Một JSON deserializer có thể trả về Java null khi nhận byte của JSON literal null. Vì thế, chỉ nhìn vào record.value() sau deserialize chưa đủ để kết luận Kafka record có null value hay không. Có thể kết hợp serializedValueSize() và hợp đồng schema để phân biệt.

Với ConsumerRecord, serializedValueSize() trả -1 nếu serialized value là null; giá trị 0 biểu thị payload có kích thước byte bằng 0. Một JSON literal null có kích thước byte lớn hơn 0 dù deserializer có thể trả Java null.

Nếu topic dùng tombstone để xóa trạng thái, deserializer và consumer phải giữ được ý nghĩa null value. Không tự động chuyển null thành chuỗi rỗng hoặc một object mặc định vì điều đó làm mất tín hiệu xóa.

## 4. Deserialization error và cách xử lý

Deserializer có thể thất bại vì nhiều lý do:

- Byte không đúng định dạng JSON, Avro hoặc Protobuf.
- Payload bị cắt hoặc hỏng.
- Producer và consumer dùng schema không tương thích.
- Field bắt buộc bị thiếu hoặc có kiểu dữ liệu sai.
- Consumer dùng sai deserializer cho topic.
- Schema Registry không truy cập được hoặc không xác thực được.
- Dữ liệu chứa phiên bản schema mà consumer chưa hỗ trợ.

### 4.1. Kafka Consumer thuần

Với KafkaConsumer thuần, lỗi deserialize thường được ném ra trong quá trình poll. Record lỗi có thể không được trả về như một ConsumerRecord bình thường, nên handler nghiệp vụ không thể đơn giản kiểm tra record.value() để xử lý lỗi.

Nếu cần tự kiểm soát raw payload, một lựa chọn là cấu hình ByteArrayDeserializer, sau đó parse trong tầng ứng dụng:

~~~java
ConsumerRecord<String, byte[]> record = ...;

byte[] rawValue = record.value();

try {
    OrderCreated event =
        objectMapper.readValue(rawValue, OrderCreated.class);
    handle(event);
} catch (Exception exception) {
    // Ghi nhận topic, partition, offset và raw payload phù hợp.
    // Chuyển lỗi sang quy trình retry hoặc dead-letter.
}
~~~

Cách này cho phép ứng dụng giữ được ConsumerRecord và metadata khi parse thất bại. Đổi lại, ứng dụng phải tự quản lý việc parse, phân loại lỗi và xử lý dữ liệu không hợp lệ.

### 4.2. Spring Kafka ErrorHandlingDeserializer

Spring Kafka cung cấp **ErrorHandlingDeserializer** để bọc một deserializer thực hiện chuyển đổi thực tế. Khi delegate deserializer ném exception, wrapper ghi thông tin lỗi vào header của record và trả về null để container có thể xử lý theo error handling strategy.

Ví dụ cấu hình:

~~~java
Map<String, Object> properties = new HashMap<>();

properties.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    ErrorHandlingDeserializer.class
);
properties.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    ErrorHandlingDeserializer.class
);

properties.put(
    ErrorHandlingDeserializer.KEY_DESERIALIZER_CLASS,
    StringDeserializer.class
);
properties.put(
    ErrorHandlingDeserializer.VALUE_DESERIALIZER_CLASS,
    OrderCreatedDeserializer.class
);
~~~

Với cấu hình này, ErrorHandlingDeserializer chịu trách nhiệm gọi StringDeserializer cho key và OrderCreatedDeserializer cho value. Khi deserialize thất bại, exception metadata được đưa vào header để Spring Kafka error handler có thể nhận biết và xử lý.

Khi sử dụng DeadLetterPublishingRecoverer, cần cấu hình KafkaTemplate/serializer đủ khả năng gửi cả object đã deserialize lẫn raw byte của record lỗi. Điều này giúp giữ payload gốc khi chuyển record lỗi sang dead-letter topic.

### 4.3. Retry hay dead-letter?

Không phải lỗi deserialize nào cũng nên retry.

| Loại lỗi | Cách xử lý thường phù hợp |
|---|---|
| JSON sai cú pháp | Không retry vô hạn; chuyển DLT để điều tra |
| Schema không tương thích | Kiểm tra schema và phiên bản producer/consumer; thường chuyển DLT hoặc chờ triển khai sửa |
| Schema Registry tạm thời không truy cập được | Retry có giới hạn với backoff nếu lỗi thực sự tạm thời |
| Credential hoặc ACL sai | Sửa cấu hình bảo mật; retry không giải quyết nguyên nhân |
| Payload rỗng trái hợp đồng | Xử lý như dữ liệu không hợp lệ hoặc theo quy ước topic |
| Tombstone hợp lệ | Không xem là lỗi; xử lý thao tác xóa state theo key |

Với Spring Kafka, có thể kết hợp DefaultErrorHandler, backoff hữu hạn và DeadLetterPublishingRecoverer. Lựa chọn retry topic hay DLT phụ thuộc yêu cầu giữ thứ tự, thời gian chờ và cách phát lại record.

## 5. ConsumerRecord chứa những thông tin gì?

ConsumerRecord<K, V> biểu diễn một record mà consumer đọc được. K và V là kiểu Java sau khi Deserializer xử lý key và value.

Các trường quan trọng:

| API | Ý nghĩa |
|---|---|
| topic() | Tên topic chứa record |
| partition() | Partition chứa record |
| offset() | Offset của record trong partition |
| key() | Key sau deserialize |
| value() | Value sau deserialize |
| timestamp() | Timestamp của record theo millisecond |
| timestampType() | Loại timestamp: CreateTime, LogAppendTime hoặc trạng thái không có timestamp |
| headers() | Các header gắn với record |
| serializedKeySize() | Kích thước key đã serialize; -1 nếu key null |
| serializedValueSize() | Kích thước value đã serialize; -1 nếu value null |
| leaderEpoch() | Epoch của leader nếu metadata này có sẵn; API có thể khác theo phiên bản client |

ConsumerRecord không chứa committed offset của consumer group. Offset trong record là vị trí của record trong partition. Tiến độ đã commit của group được quản lý riêng bởi consumer coordinator và internal topic __consumer_offsets.

### 5.1. Topic, partition và offset

Ba trường này xác định vị trí của record trong Kafka:

~~~text
topic     = orders
partition = 2
offset    = 105
~~~

Offset chỉ có ý nghĩa trong một partition. Offset 105 của partition 2 không thể so sánh trực tiếp với offset 105 của partition 0 để suy ra thứ tự toàn topic.

Nếu cần ghi log hoặc lưu dấu vết sự kiện, nên kết hợp topic, partition và offset. Bộ ba này giúp xác định record trong một log cụ thể, miễn là dữ liệu chưa bị thay đổi bởi quy trình migration hoặc topic recreation.

### 5.2. Key và value

Key thường được dùng để:

- Định tuyến record đến partition.
- Nhóm sự kiện theo thực thể như orderId hoặc customerId.
- Xác định state cần cập nhật hoặc xóa.
- Hỗ trợ idempotency khi kết hợp event ID hoặc khóa nghiệp vụ.

Value chứa payload sự kiện hoặc dữ liệu trạng thái. Consumer phải xử lý theo schema và hợp đồng topic, không nên giả định mọi value đều có cùng cấu trúc nếu topic chứa nhiều loại event.

Key null không đồng nghĩa record không tồn tại. Value null cũng không đồng nghĩa không có record. Trên compacted topic, key khác null và value null có thể là tombstone.

### 5.3. Timestamp và timestamp type

ConsumerRecord.timestamp() trả timestamp theo millisecond. ConsumerRecord.timestampType() cho biết timestamp được hiểu là CreateTime hay LogAppendTime; một số record có thể không có timestamp hợp lệ.

- **CreateTime:** do producer cung cấp, thường phản ánh thời điểm nghiệp vụ hoặc thời điểm tạo event.
- **LogAppendTime:** broker gán khi append record, phản ánh thời điểm Kafka tiếp nhận record.
- **Không có timestamp:** ứng dụng cần kiểm tra giá trị sentinel và không tự coi nó là thời gian hợp lệ.

Timestamp hữu ích cho tracing và xử lý event time, nhưng không thay thế offset. Hai record trên các partition khác nhau có timestamp gần nhau không tạo ra thứ tự tổng thể.

### 5.4. Headers

Headers là metadata key/value dạng byte được gắn vào record. Chúng thường được dùng cho:

- Correlation ID hoặc trace ID.
- Event type hoặc schema version.
- Tenant hoặc nguồn phát sự kiện.
- Thông tin tracing và routing ở tầng ứng dụng.
- Metadata phục vụ retry hoặc dead-letter.

Một header value là byte array, nên consumer cần decode theo quy ước encoding đã thống nhất.

Kafka cho phép nhiều header có cùng tên. Vì vậy, không nên giả định mỗi tên header chỉ có đúng một entry. Có thể dùng lastHeader(name) nếu quy ước lấy giá trị cuối, hoặc duyệt toàn bộ headers(name) khi cần xử lý nhiều giá trị.

Không nên đưa mật khẩu, token hoặc dữ liệu cá nhân nhạy cảm vào headers nếu không có yêu cầu và biện pháp bảo vệ phù hợp. Header cũng được lưu cùng record và có thể được chuyển tiếp qua nhiều hệ thống.

## 6. Đọc ConsumerRecord bằng KafkaConsumer

KafkaConsumer.poll() trả về một tập ConsumerRecords. Ứng dụng có thể duyệt từng record để lấy payload và metadata.

~~~java
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.common.header.Header;

ConsumerRecords<String, OrderCreated> records =
    consumer.poll(Duration.ofMillis(500));

for (ConsumerRecord<String, OrderCreated> record : records) {
    String topic = record.topic();
    int partition = record.partition();
    long offset = record.offset();

    String key = record.key();
    OrderCreated event = record.value();

    long timestamp = record.timestamp();
    int keySize = record.serializedKeySize();
    int valueSize = record.serializedValueSize();

    Header traceHeader =
        record.headers().lastHeader("trace-id");

    String traceId = traceHeader == null
        ? null
        : traceHeader.value() == null
            ? null
            : new String(
                traceHeader.value(),
                StandardCharsets.UTF_8
            );

    // Xử lý event và ghi log metadata cần thiết.
}
~~~

Đoạn mã minh họa cách đọc trường. Trong ứng dụng thực tế, cần xử lý null key/value, header value null, lỗi nghiệp vụ và thời điểm commit offset. Không nên log toàn bộ payload nếu dữ liệu có thể chứa thông tin nhạy cảm hoặc có kích thước lớn.

### 6.1. Commit offset sau xử lý

Nếu ứng dụng dùng manual commit, cần xác định rõ thời điểm commit so với xử lý nghiệp vụ. Thông thường, chỉ commit sau khi record đã được xử lý thành công theo yêu cầu.

Trong cấu hình KafkaConsumer, hãy tắt auto commit bằng enable.auto.commit=false để ứng dụng thực sự kiểm soát thời điểm xác nhận tiến độ.

~~~java
for (ConsumerRecord<String, OrderCreated> record : records) {
    process(record.value());
}

consumer.commitSync();
~~~

Ví dụ này giả định toàn bộ batch xử lý thành công. Nếu một record lỗi giữa batch, ứng dụng cần quyết định commit đến offset nào và xử lý retry ra sao. Commit sai thời điểm có thể khiến record bị bỏ qua hoặc xử lý lại.

Offset được commit theo partition. Với xử lý song song trong một batch, cần theo dõi offset hoàn thành liên tục theo từng partition để không commit vượt qua record chưa xử lý xong.

## 7. Đọc ConsumerRecord trong Spring Kafka

Với Spring Kafka, listener có thể nhận trực tiếp ConsumerRecord khi cần truy cập metadata:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        topics = "orders",
        groupId = "order-projection"
    )
    public void listen(
            ConsumerRecord<String, OrderCreated> record) {

        String orderId = record.key();
        OrderCreated event = record.value();

        String topic = record.topic();
        int partition = record.partition();
        long offset = record.offset();

        if (event == null) {
            // Kiểm tra hợp đồng null/tombstone hoặc lỗi deserialize.
            return;
        }

        updateOrderProjection(orderId, event);

        // Có thể ghi topic, partition, offset vào log tracing.
    }

    private void updateOrderProjection(
            String orderId,
            OrderCreated event) {
        // Cập nhật read model theo cách idempotent.
    }
}
~~~

Nếu listener chỉ nhận payload:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-projection"
)
public void listen(OrderCreated event) {
    // Xử lý payload.
}
~~~

Cách nhận payload đơn giản hơn khi không cần metadata. Khi cần partition, offset, headers hoặc timestamp, nhận ConsumerRecord hoặc dùng các tham số listener tương ứng của Spring Kafka.

### 7.1. Xử lý tombstone trong listener

Với compacted topic, null value có thể là tombstone. Listener cần kiểm tra key và hợp đồng topic:

~~~java
@KafkaListener(
    topics = "customer-state",
    groupId = "customer-projection"
)
public void listen(
        ConsumerRecord<String, CustomerState> record) {

    String customerId = record.key();
    CustomerState state = record.value();

    if (state == null) {
        if (customerId != null
                && record.serializedValueSize() == -1) {
            deleteCustomerState(customerId);
        }
        return;
    }

    updateCustomerState(customerId, state);
}
~~~

Điều kiện serializedValueSize bằng -1 giúp nhận diện Kafka null value trong trường hợp deserializer trả null cho dữ liệu đầu vào null. Nếu deserializer cũng có thể trả null cho payload byte hợp lệ, cần kiểm tra thêm exception header hoặc quy tắc schema. Không nên coi mọi Java null là tombstone trong mọi topic.

## 8. Schema, version và tương thích dữ liệu

Deserializer là nơi hợp đồng schema được áp dụng. Nếu producer và consumer không thống nhất schema, record có thể deserialize thất bại hoặc tạo object thiếu dữ liệu.

Một số nguyên tắc:

- Thay đổi schema theo chiến lược tương thích đã thống nhất.
- Thêm field mới nên có default hoặc cách xử lý phù hợp với consumer cũ.
- Không đổi ý nghĩa field đang tồn tại mà không có versioning.
- Nếu topic chứa nhiều event type, cần phân biệt event type bằng schema, header hoặc envelope rõ ràng.
- Với Avro/Protobuf/JSON Schema, dùng serializer/deserializer và schema registry tương ứng.
- Không tin type header từ nguồn không đáng tin cậy nếu nó có thể khiến ứng dụng khởi tạo kiểu class ngoài phạm vi cho phép.

Một envelope sự kiện có thể chứa:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "occurredAt": "2026-11-20T10:30:00Z",
  "payload": {
    "orderId": "order-42",
    "customerId": "customer-7"
  }
}
~~~

Envelope giúp consumer xác định event type, version và metadata nghiệp vụ. Tuy nhiên, các metadata đã có sẵn trong ConsumerRecord như topic, partition, offset và timestamp vẫn cần được giữ khi tracing.

## 9. Log và tracing dựa trên ConsumerRecord

Khi điều tra một sự kiện, nên ghi những trường đủ để định vị record:

~~~text
topic=orders
partition=2
offset=105
key=order-42
timestamp=1795170600000
traceId=trace-abc
eventType=OrderCreated
~~~

Một log như vậy giúp:

- Tìm lại record bằng topic, partition và offset.
- Nối sự kiện giữa nhiều service qua trace ID.
- Phát hiện record đến trễ hoặc sai thứ tự theo timestamp/version.
- Phân biệt lỗi deserialize, lỗi nghiệp vụ và lỗi downstream.
- Điều tra duplicate bằng event ID.

Không nhất thiết log toàn bộ value. Với payload lớn hoặc chứa thông tin nhạy cảm, nên log event ID, key đã được kiểm soát, schema version và metadata cần thiết.

## 10. Những lỗi thường gặp

- **Dùng sai Deserializer:** producer ghi JSON nhưng consumer lại dùng StringDeserializer hoặc Avro deserializer không tương thích.
- **Cho rằng broker chuyển JSON thành object:** broker lưu byte; chuyển đổi diễn ra ở consumer client.
- **Không kiểm tra null trước khi parse:** tombstone hoặc null payload có thể làm phát sinh NullPointerException.
- **Gộp null với empty:** Kafka null value, byte array rỗng và JSON literal null có ý nghĩa khác nhau.
- **Chỉ đọc value mà bỏ qua key:** có thể mất ID thực thể cần để partitioning, idempotency hoặc xóa state.
- **Bỏ qua topic/partition/offset:** khó truy vết record và xác định vị trí lỗi.
- **Giả định offset liên tục trên mọi partition:** offset chỉ có ý nghĩa trong partition cụ thể.
- **Giả định header name luôn duy nhất:** Kafka cho phép nhiều header trùng tên.
- **Retry vô hạn lỗi schema:** lỗi dữ liệu cố định thường không tự hết; cần sửa schema hoặc chuyển DLT.
- **Không giữ raw payload khi cần điều tra:** deserializer có thể làm mất khả năng tái tạo byte gốc nếu chỉ lưu object đã chuyển đổi.
- **Commit offset trước khi xử lý thành công:** có thể khiến record bị bỏ qua sau khi ứng dụng phục hồi.

## 11. Checklist khi triển khai Deserializer và ConsumerRecord

| Câu hỏi | Hướng xử lý |
|---|---|
| Producer serialize key/value bằng gì? | Dùng Deserializer tương thích với byte format |
| Key và value có kiểu riêng không? | Cấu hình key.deserializer và value.deserializer độc lập |
| Payload có schema/version không? | Kiểm tra compatibility và default value |
| Null value có ý nghĩa tombstone không? | Xác định theo hợp đồng topic và kiểm tra key |
| Payload rỗng có hợp lệ không? | Quy định rõ empty payload và xử lý riêng |
| Có cần giữ raw bytes không? | Dùng ByteArrayDeserializer hoặc cơ chế error handling giữ payload |
| Cần metadata nào khi xử lý? | Đọc topic, partition, offset, timestamp và headers |
| Header có thể trùng tên không? | Duyệt tất cả hoặc chọn lastHeader theo quy ước |
| Deserialize lỗi thì sao? | Phân loại lỗi, retry có giới hạn hoặc DLT |
| Commit offset khi nào? | Commit sau khi xử lý thành công theo từng partition |
| Có cần tracing không? | Dùng event ID/correlation ID và ghi metadata record |

## 12. Kết luận

Deserializer chuyển key và value từ byte thành kiểu Java mà ứng dụng có thể xử lý. Nó phải tương thích với serializer và schema của producer, đồng thời cần xử lý rõ null, empty payload và dữ liệu không hợp lệ. Với custom Deserializer, nên giữ implementation đơn giản, không giữ state mutable không an toàn và ném lỗi có ngữ cảnh khi không thể parse dữ liệu.

ConsumerRecord cung cấp vị trí và metadata của record: topic, partition, offset, key, value, timestamp, headers và kích thước dữ liệu đã serialize. Các trường này hỗ trợ xử lý nghiệp vụ, idempotency, ordering, tracing và điều tra sự cố. Khi dùng Spring Kafka, ErrorHandlingDeserializer cùng error handler và dead-letter topic giúp cô lập record không thể deserialize mà vẫn giữ thông tin cần thiết để xử lý sau.

Thiết kế consumer tốt không chỉ lấy được object từ value. Nó cần giữ đúng hợp đồng dữ liệu, đọc metadata đầy đủ, phân biệt tombstone với payload rỗng và chỉ xác nhận tiến độ sau khi xử lý đạt yêu cầu.
