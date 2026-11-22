# Khai báo key serializer

## Mục tiêu của bài học

Trong chương **Serialization**, bài này hướng dẫn khai báo serializer cho Kafka record key và cấu hình tương ứng trong Spring Kafka. Key serializer chuyển giá trị key trong ứng dụng thành byte để Kafka producer gửi qua mạng và sử dụng khi định tuyến record tới partition.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Key serializer là một phần của hợp đồng dữ liệu giữa producer và consumer, đồng thời ảnh hưởng tới cách các record liên quan được phân phối và đọc trong Kafka.

Sau bài học, người học có thể:

- Giải thích vai trò của key trong Kafka record.
- Phân biệt key serializer với value serializer.
- Khai báo key serializer bằng Spring Boot properties và Java configuration.
- Chọn serializer dựng sẵn phù hợp với kiểu key.
- Viết custom serializer khi kiểu key không có serializer phù hợp.
- Cấu hình key deserializer tương ứng ở consumer.
- Hiểu ảnh hưởng của serialized key tới partitioning, ordering và log compaction.
- Kiểm thử byte representation, tính ổn định và khả năng đọc lại của key.

## 1. Key trong Kafka record là gì?

Một Kafka record có thể chứa các thành phần chính:

- Topic: luồng dữ liệu mà record được gửi tới.
- Partition: nơi record được lưu.
- Key: giá trị dùng để nhận diện hoặc phân nhóm record liên quan.
- Value: payload chính của record.
- Timestamp: thời điểm gắn với record.
- Headers: metadata bổ sung.

Ví dụ một event đơn hàng:

~~~text
Topic: commerce.order.created
Key:   order-10001
Value: {"orderId":"order-10001","customerId":"customer-20001"}
~~~

Trong ví dụ này, key là mã đơn hàng. Nếu producer gửi các event của cùng một đơn hàng với cùng key và partitioner mặc định, Kafka thường định tuyến chúng tới cùng partition. Điều này hữu ích khi cần giữ thứ tự các event của cùng một đơn hàng.

Key không phải là một trường bắt buộc của mọi Kafka record. Producer có thể gửi record không có key. Tuy nhiên, nếu nghiệp vụ cần định tuyến theo thực thể, giữ thứ tự theo key hoặc dùng log compaction, cần lựa chọn key có chủ đích.

## 2. Key serializer làm nhiệm vụ gì?

Kafka lưu key và value dưới dạng byte. Ở phía producer, serializer chuyển kiểu dữ liệu Java thành mảng byte trước khi record được gửi tới broker.

Với key có kiểu String:

~~~text
Java key:        "order-10001"
Key serializer:  StringSerializer
Serialized key:  byte[]
~~~

Ở consumer, key deserializer thực hiện chiều ngược lại, chuyển byte thành kiểu dữ liệu mà ứng dụng sử dụng.

~~~mermaid
flowchart LR
    A["Java key: String"] --> B["Key Serializer"]
    B --> C["Serialized key: byte[]"]
    C --> D["Kafka Producer"]
    D --> E["Kafka Broker"]
    E --> F["Kafka Consumer"]
    F --> G["Key Deserializer"]
    G --> H["Java key: String"]
~~~

Key serializer và value serializer là hai cấu hình riêng:

| Thành phần | Trách nhiệm | Cấu hình producer |
|---|---|---|
| Key serializer | Chuyển key thành byte | `key.serializer` |
| Value serializer | Chuyển value thành byte | `value.serializer` |

Một producer có thể dùng `StringSerializer` cho key và `JsonSerializer` cho value. Không cần key và value có cùng kiểu dữ liệu hoặc cùng serializer.

## 3. Khai báo key serializer bằng Spring Boot

Cách đơn giản nhất là khai báo serializer trong `application.yml`.

Ví dụ ứng dụng dùng String làm key và JSON làm value:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer

    consumer:
      group-id: billing-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
~~~

Ý nghĩa:

- `key-serializer` xác định lớp chuyển key Java thành byte.
- `value-serializer` xác định lớp chuyển payload thành byte.
- `key-deserializer` xác định lớp khôi phục key ở consumer.
- `value-deserializer` xác định lớp khôi phục payload ở consumer.

Trong ví dụ, key là String nên producer dùng `StringSerializer`, consumer dùng `StringDeserializer`. Value là object sự kiện nên dùng JSON serializer/deserializer tương ứng.

Tên class cần khớp với dependency và phiên bản Spring Kafka/Kafka client trong dự án. Nếu dùng Avro, Protobuf hoặc serializer của Schema Registry, cần khai báo thư viện và cấu hình registry tương ứng.

### 3.1. Dùng KafkaTemplate có generic type tương ứng

Khi key là String và value là OrderCreated, khai báo KafkaTemplate với hai kiểu này:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate.send(
            "commerce.order.created",
            event.orderId(),
            event
        );
    }
}
~~~

Generic type giúp thể hiện hợp đồng ở cấp Java:

- `K` là kiểu key.
- `V` là kiểu value.

`KafkaTemplate<String, OrderCreated>` phải đi cùng ProducerFactory có key serializer tương thích với String và value serializer tương thích với OrderCreated.

Generic type không tự chọn serializer. Serializer thực tế vẫn được quyết định bởi cấu hình producer factory.

### 3.2. Gửi key qua Spring Message

Nếu ứng dụng gửi bằng `KafkaTemplate.send(Message<?>)`, key có thể được đặt trong `KafkaHeaders.KEY`:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, "commerce.order.created")
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .build();

kafkaTemplate.send(message);
~~~

Giá trị trong `KafkaHeaders.KEY` phải tương thích với kiểu key mà KafkaTemplate và key serializer đang sử dụng. Nếu template khai báo key là String nhưng header chứa một object khác, quá trình serialize có thể thất bại hoặc phát sinh lỗi kiểu dữ liệu.

## 4. Khai báo key serializer bằng Java configuration

Khi cần tự tạo ProducerFactory, có thể khai báo serializer thông qua producer properties.

~~~java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreated> orderProducerFactory() {
        Map<String, Object> properties = new HashMap<>();

        properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        properties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class
        );

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> orderProducerFactory) {
        return new KafkaTemplate<>(orderProducerFactory);
    }
}
~~~

Hai thuộc tính quan trọng:

- `ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG`: khai báo serializer cho key.
- `ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG`: khai báo serializer cho value.

Có thể truyền serializer instance vào constructor của `DefaultKafkaProducerFactory` nếu cần cấu hình trực tiếp hoặc dùng serializer có trạng thái riêng. Khi tạo serializer instance, cần hiểu cách producer factory quản lý và đóng tài nguyên của serializer theo phiên bản Kafka client.

Không khai báo đồng thời nhiều cấu hình key serializer mâu thuẫn giữa application.yml, producer properties và custom ProducerFactory. Hãy xác định ProducerFactory nào đang được KafkaTemplate sử dụng để biết cấu hình nào thực sự có hiệu lực.

## 5. Các key serializer dựng sẵn thường dùng

Kafka client cung cấp nhiều serializer phổ biến trong package `org.apache.kafka.common.serialization`.

| Kiểu key Java | Serializer | Deserializer tương ứng |
|---|---|---|
| `String` | `StringSerializer` | `StringDeserializer` |
| `Integer` | `IntegerSerializer` | `IntegerDeserializer` |
| `Long` | `LongSerializer` | `LongDeserializer` |
| `Short` | `ShortSerializer` | `ShortDeserializer` |
| `Double` | `DoubleSerializer` | `DoubleDeserializer` |
| `Float` | `FloatSerializer` | `FloatDeserializer` |
| `byte[]` | `ByteArraySerializer` | `ByteArrayDeserializer` |

Ví dụ dùng Long làm key:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.LongSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.LongDeserializer
~~~

KafkaTemplate tương ứng:

~~~java
private final KafkaTemplate<Long, OrderCreated> kafkaTemplate;

public void publish(OrderCreated event) {
    kafkaTemplate.send(
        "commerce.order.created",
        10001L,
        event
    );
}
~~~

Nếu consumer cần đọc key dưới dạng Long, phải dùng `LongDeserializer`. Không dùng `StringDeserializer` để đọc byte được tạo bởi `LongSerializer`, vì hai serializer có biểu diễn byte khác nhau.

### 5.1. Chọn String hay kiểu số?

String là lựa chọn phổ biến cho business key như order ID, customer ID hoặc account ID. String dễ đọc trong công cụ quản trị và log, thuận tiện khi điều tra dữ liệu.

Integer hoặc Long phù hợp khi key thực sự là số và mọi producer/consumer thống nhất cách biểu diễn. Kiểu số thường có biểu diễn nhị phân cố định, không giống chuỗi chữ số.

Ví dụ key `10001`:

- StringSerializer mã hóa chuỗi ký tự `"10001"` thành byte UTF-8.
- LongSerializer mã hóa giá trị số 10001 theo biểu diễn nhị phân của Kafka client.

Hai cách này không tương thích với nhau dù nhìn ở dạng văn bản có cùng chữ số.

### 5.2. Chọn ByteArraySerializer

`ByteArraySerializer` phù hợp khi ứng dụng đã có sẵn byte key theo một format được quy định rõ. Khi đó, producer không cần chuyển đổi kiểu dữ liệu thêm lần nữa.

Tuy nhiên, dùng byte[] làm key khiến hợp đồng key khó đọc hơn trong công cụ quản trị. Cần tài liệu hóa format, encoding và phiên bản byte representation để consumer hoặc công cụ ngoài ứng dụng có thể hiểu được.

## 6. Khi nào cần custom key serializer?

Serializer dựng sẵn đủ cho các kiểu dữ liệu cơ bản. Nếu key là một domain object gồm nhiều thành phần, có thể cần custom serializer.

Ví dụ hệ thống có order key gồm tenant ID và order ID:

~~~java
public record OrderKey(
    String tenantId,
    String orderId
) {
}
~~~

Ứng dụng có thể cần một serializer riêng để chuyển object này thành byte theo format ổn định.

Custom serializer cần triển khai `org.apache.kafka.common.serialization.Serializer<T>`:

~~~java
public class OrderKeySerializer implements Serializer<OrderKey> {

    @Override
    public byte[] serialize(String topic, OrderKey data) {
        if (data == null) {
            return null;
        }

        byte[] tenant = data.tenantId()
            .getBytes(StandardCharsets.UTF_8);

        byte[] order = data.orderId()
            .getBytes(StandardCharsets.UTF_8);

        ByteBuffer buffer = ByteBuffer.allocate(
            Integer.BYTES + tenant.length
                + Integer.BYTES + order.length
        ).order(ByteOrder.BIG_ENDIAN);

        buffer.putInt(tenant.length);
        buffer.put(tenant);
        buffer.putInt(order.length);
        buffer.put(order);

        return buffer.array();
    }
}
~~~

Format minh họa gồm:

1. Độ dài tenant ID dưới dạng integer.
2. Byte của tenant ID theo UTF-8.
3. Độ dài order ID dưới dạng integer.
4. Byte của order ID theo UTF-8.

Cách đóng gói có độ dài rõ ràng tránh nhập nhằng khi một thành phần chứa ký tự phân cách. Ví dụ đặt byte order tường minh là BIG_ENDIAN để format không phụ thuộc giả định ngầm. Trong hệ thống thực tế, cần quy định byte order, giới hạn độ dài, xử lý chuỗi null và chiến lược versioning của format.

### 6.1. Khai báo custom serializer

Trong `application.yml`:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: com.example.kafka.OrderKeySerializer
~~~

Hoặc trong Java configuration:

~~~java
properties.put(
    ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    OrderKeySerializer.class
);
~~~

Kafka client sẽ tạo và sử dụng serializer đã khai báo cho producer key.

Nếu serializer cần tham số cấu hình, có thể triển khai phương thức `configure(Map<String, ?> configs, boolean isKey)` của interface Serializer. Tránh đặt thông tin bí mật hoặc phụ thuộc môi trường trực tiếp trong code serializer.

### 6.2. Custom deserializer phải hiểu cùng format

Consumer cần một `OrderKeyDeserializer` có thể đọc chính xác format do `OrderKeySerializer` tạo ra.

Deserializer phải:

- Kiểm tra dữ liệu đầu vào null.
- Kiểm tra đủ byte trước khi đọc độ dài.
- Từ chối độ dài âm hoặc vượt quá số byte còn lại.
- Khôi phục đúng thứ tự các thành phần.
- Từ chối byte dư hoặc format không được hỗ trợ.
- Báo lỗi serialization rõ ràng khi dữ liệu không hợp lệ.

Không dùng `StringDeserializer` cho custom binary key ở trên. Consumer phải dùng deserializer tương ứng với byte format, nếu không key sẽ không được khôi phục thành OrderKey đúng cách.

### 6.3. Tránh Java native serialization cho key lâu dài

Không nên dùng Java native serialization như hợp đồng key lâu dài giữa nhiều service. Byte representation có thể phụ thuộc class, phiên bản và cách triển khai; khó tương thích khi ứng dụng thay đổi.

Với key nghiệp vụ, ưu tiên format đơn giản và ổn định như String, số nguyên hoặc một binary format có schema và quy tắc versioning rõ ràng.

## 7. Key serializer ảnh hưởng tới partitioning như thế nào?

Kafka partitioner quyết định partition nhận record. Với default partitioner và key khác null, việc lựa chọn partition dựa trên byte của key đã serialize.

Có thể hình dung:

~~~mermaid
flowchart TD
    A["Java key"] --> B["Key serializer"]
    B --> C["Serialized key bytes"]
    C --> D["Partitioner"]
    D --> E["Tính partition"]
    E --> F["Kafka partition"]
~~~

Với default partitioner, Kafka dùng hash của serialized key bytes để chọn partition trong số partition hiện có. Vì vậy:

- Cùng key và cùng serializer thường dẫn tới cùng byte.
- Cùng byte key và cùng số partition thường dẫn tới cùng partition.
- Hai key Java khác nhau nhưng serialize thành cùng byte có thể bị xem như cùng key ở tầng Kafka.
- Thay đổi serializer hoặc format key có thể làm record của cùng entity đi sang partition khác.

Partitioner tùy chỉnh có thể áp dụng quy tắc khác. Vì vậy, không nên suy luận mọi producer đều dùng cùng thuật toán nếu ứng dụng đã cấu hình `partitioner.class` riêng.

### 7.1. Cùng key giúp giữ thứ tự trong partition

Giả sử các event của order-10001:

~~~text
order-10001 -> OrderCreated
order-10001 -> PaymentAuthorized
order-10001 -> OrderCompleted
~~~

Nếu chúng được gửi với cùng key và partitioner định tuyến vào cùng partition, Kafka lưu chúng theo thứ tự ghi trong partition đó. Consumer đọc partition theo thứ tự offset.

Đây là cơ sở để xử lý chuỗi event theo từng aggregate hoặc thực thể nghiệp vụ.

Kafka không bảo đảm thứ tự toàn cục giữa các partition. Nếu event của cùng một order bị định tuyến sang các partition khác nhau, consumer không thể dựa vào thứ tự offset để suy ra thứ tự nghiệp vụ giữa chúng.

### 7.2. Thay đổi số partition có thể đổi vị trí key

Default partitioner sử dụng số partition trong phép chọn partition. Khi tăng số partition, cùng key có thể được ánh xạ sang partition khác.

Điều này có nghĩa:

- Record cũ của một order có thể nằm ở partition 1.
- Sau khi tăng partition, record mới của cùng order có thể được gửi vào partition 4.
- Hai partition được đọc độc lập, nên không có bảo đảm thứ tự giữa record cũ và mới.

Nếu ordering theo key là yêu cầu quan trọng, cần đánh giá kỹ việc tăng partition và chiến lược migration. Không thay đổi số partition chỉ dựa trên nhu cầu throughput mà bỏ qua tác động tới key affinity.

## 8. Key null và record không có key

Kafka cho phép record không có key. Trong trường hợp key null:

- Key serializer nhận giá trị null và cần trả về null.
- Default partitioner không thể hash một key cụ thể để giữ affinity theo entity.
- Record được phân phối theo cơ chế dành cho record không key của partitioner, thường sử dụng sticky partitioning để cải thiện batching.

Nếu ứng dụng cần các event cùng order luôn vào một partition, không nên gửi key null.

Cần phân biệt hai trường hợp:

| Key | Value | Ý nghĩa |
|---|---|---|
| null | Có dữ liệu | Record không có key |
| Có key | Có dữ liệu | Record có định danh/khóa |
| Có key | null | Tombstone trong topic dùng log compaction |
| null | null | Record không mang key và value; không phải tombstone có key |

Trong topic compacted, tombstone là record có key khác null và value null. Tombstone biểu thị việc xóa trạng thái của key đó trong mô hình log compaction. Không nhầm tombstone với record có key null.

## 9. Key serializer và log compaction

Kafka hỗ trợ log compaction để giữ lại trạng thái mới nhất theo key trong từng partition, thay vì giữ mọi phiên bản record mãi mãi. Compaction không hợp nhất cùng một key nằm ở hai partition khác nhau.

Ví dụ topic `customer-profile`:

~~~text
Key: customer-01, Value: {"name":"An"}
Key: customer-02, Value: {"name":"Binh"}
Key: customer-01, Value: {"name":"An Nguyen"}
~~~

Sau compaction trong partition chứa các record này, Kafka có thể giữ bản ghi mới nhất của customer-01 cùng bản ghi customer-02. Cơ chế này dựa trên key bytes; vì vậy key serializer phải tạo ra biểu diễn ổn định cho cùng một thực thể.

Nếu cùng một customer ID lúc được serialize thành byte A, lúc khác thành byte B, Kafka có thể xem chúng là hai key khác nhau và không compact thành cùng một trạng thái.

Tombstone với key cụ thể và value null có thể đánh dấu key cần xóa trong topic compacted. Tombstone được giữ theo chính sách delete retention và compaction của broker/topic.

## 10. Nguyên tắc thiết kế key ổn định

Key serializer không chỉ cần chạy được; nó còn phải tạo byte representation nhất quán trong suốt vòng đời dữ liệu.

Một số nguyên tắc:

- Cùng một thực thể nghiệp vụ phải có key ổn định.
- Cùng một key logic phải tạo ra cùng byte representation.
- Producer và consumer phải thống nhất format.
- Không đưa timestamp hoặc giá trị ngẫu nhiên vào key nếu muốn giữ affinity theo entity.
- Không serialize object bằng cách phụ thuộc vào `toString()` không được quy định.
- Không thay đổi format key tùy tiện khi topic đang có dữ liệu.
- Có chiến lược versioning nếu format key cần thay đổi.
- Chọn key có độ phân bố phù hợp để tránh một partition quá nóng.

Ví dụ key phù hợp:

~~~text
order-10001
customer-20001
account-90001
tenant-01:order-10001
~~~

Key không phù hợp nếu mục tiêu là giữ thứ tự theo order:

~~~text
2026-11-17T10:00:00
random-uuid-per-event
thread-3
~~~

Các giá trị này thay đổi theo từng record hoặc theo cách triển khai, khiến event của cùng một order không còn được định tuyến theo cùng key.

## 11. Key serializer và schema evolution

Nếu key được dùng xuyên nhiều service, format của nó là một phần của hợp đồng tích hợp. Thay đổi kiểu key hoặc byte representation có thể ảnh hưởng tới:

- Partition assignment.
- Khả năng consumer deserialize dữ liệu cũ.
- Log compaction.
- Công cụ truy vấn và xử lý dữ liệu.
- Các hệ thống downstream dùng key để join hoặc phân nhóm.

Ví dụ producer cũ dùng StringSerializer cho order ID, producer mới chuyển sang custom binary serializer. Dù giá trị logic vẫn là order-10001, byte representation đã khác. Các record mới có thể được định tuyến sang partition khác và compaction có thể xem chúng là key khác nhau.

Trước khi thay đổi serializer, cần:

1. Xác định format key đang tồn tại trong topic.
2. Kiểm tra tất cả producer đang ghi vào topic.
3. Kiểm tra consumer và connector đọc key.
4. Đánh giá partition affinity và ordering.
5. Xây dựng kế hoạch migration nếu byte representation thay đổi.
6. Kiểm thử khả năng đọc record cũ và mới trong giai đoạn chuyển đổi.

Với Avro hoặc Protobuf, serializer thường tích hợp schema registry. Khi dùng các format này cho key, cần thống nhất schema, subject naming, compatibility và cách consumer lấy schema để deserialize. Không mặc định rằng đổi schema key sẽ không ảnh hưởng tới partitioning.

## 12. Bảo mật và dữ liệu trong key

Key thường xuất hiện trong công cụ quản trị, log, metric hoặc trace. Vì vậy, không nên đưa thông tin bí mật vào key.

Tránh sử dụng:

- Password hoặc access token.
- API key hoặc session secret.
- Số thẻ thanh toán hoặc dữ liệu nhạy cảm trực tiếp.
- Thông tin cá nhân không cần thiết để định tuyến.

Nếu cần định tuyến theo một định danh nhạy cảm, có thể cân nhắc một mã định danh nội bộ hoặc giá trị hash được thiết kế phù hợp. Tuy nhiên, hash không tự động bảo đảm ẩn danh; giá trị có thể bị dò nếu không gian đầu vào nhỏ.

Key cũng cần có kích thước hợp lý. Key quá lớn làm tăng kích thước record, chi phí truyền tải và lưu trữ, trong khi thường không mang lại lợi ích định tuyến tương xứng.

## 13. Kiểm thử key serializer

Kiểm thử nên bao gồm cả unit test serializer và integration test với Kafka.

### 13.1. Unit test

Với serializer custom, kiểm tra:

- Cùng input tạo ra cùng byte.
- Deserialize byte khôi phục đúng object.
- Giá trị null được xử lý theo hợp đồng.
- Chuỗi rỗng và ký tự Unicode được xử lý đúng.
- Dữ liệu lỗi hoặc thiếu byte bị từ chối.
- Không có collision ngoài ý muốn giữa các cặp key.

Ví dụ kiểm tra StringSerializer:

~~~java
class StringKeySerializerTest {

    private final StringSerializer serializer =
        new StringSerializer();

    @Test
    void shouldSerializeKeyAsUtf8() {
        byte[] bytes = serializer.serialize(
            "commerce.order.created",
            "order-10001"
        );

        assertThat(new String(bytes, StandardCharsets.UTF_8))
            .isEqualTo("order-10001");
    }

    @Test
    void shouldReturnNullForNullKey() {
        assertThat(
            serializer.serialize("commerce.order.created", null)
        ).isNull();
    }
}
~~~

### 13.2. Integration test với Kafka

Kiểm thử tích hợp cần xác nhận producer ghi đúng key và consumer đọc lại đúng kiểu.

Các bước:

1. Khởi động Kafka bằng EmbeddedKafka hoặc Testcontainers.
2. Cấu hình producer key serializer.
3. Gửi record có key.
4. Đọc record bằng consumer với key deserializer tương ứng.
5. Kiểm tra key, value, topic và partition.
6. Gửi nhiều record cùng key để xác nhận chúng được định tuyến nhất quán khi số partition không đổi.

Ví dụ xác nhận key sau khi đọc:

~~~java
ConsumerRecord<String, OrderCreated> record =
    KafkaTestUtils.getSingleRecord(
        consumer,
        "commerce.order.created"
    );

assertThat(record.key()).isEqualTo("order-10001");
assertThat(record.value().orderId()).isEqualTo("order-10001");
~~~

Để kiểm tra partition affinity, gửi nhiều record với cùng key và xác nhận partition giống nhau trong cùng điều kiện topic, partitioner và số partition.

Không dùng unit test serializer để kết luận partitioning đúng. Partitioning cần được kiểm tra với producer và cấu hình partitioner thực tế.

## 14. Các lỗi thường gặp khi khai báo key serializer

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `ClassCastException` khi gửi | Generic key của KafkaTemplate không khớp kiểu dữ liệu thực tế | Kiểm tra `KafkaTemplate<K, V>` và key truyền vào |
| Không tìm thấy serializer | Sai class name hoặc thiếu dependency | Kiểm tra `key-serializer` và thư viện |
| `SerializationException` | Serializer không xử lý được giá trị key | Kiểm tra kiểu dữ liệu và logic serialize |
| Consumer đọc key sai | Key deserializer không tương thích | Dùng deserializer tương ứng với serializer |
| Cùng entity vào nhiều partition | Key thay đổi hoặc byte representation không ổn định | Kiểm tra key và serializer |
| Key chuyển partition sau khi mở rộng | Số partition thay đổi hoặc partitioner thay đổi | Đánh giá ordering và kế hoạch migration |
| Compaction giữ nhiều bản ghi tưởng như cùng key | Serialized key bytes khác nhau | Kiểm tra byte format của key |
| Consumer không đọc được key cũ | Format key đã thay đổi không tương thích | Duy trì deserializer tương thích hoặc migration |
| Record không có partition affinity | Producer gửi key null | Chọn business key ổn định |
| Record quá lớn | Key chứa quá nhiều dữ liệu | Giữ key ngắn, chỉ chứa định danh cần thiết |

## 15. Quy trình thực hành hoàn chỉnh

Giả sử dịch vụ Order gửi event và muốn tất cả event của cùng một đơn hàng được định tuyến theo order ID.

### Bước 1: Chọn kiểu key

Chọn String vì order ID là định danh dạng chuỗi:

~~~java
public record OrderCreated(
    String orderId,
    String customerId,
    long total
) {
}
~~~

### Bước 2: Cấu hình serializer

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

### Bước 3: Khai báo KafkaTemplate

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send(
            "commerce.order.created",
            event.orderId(),
            event
        );
    }
}
~~~

### Bước 4: Cấu hình consumer tương ứng

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
~~~

### Bước 5: Xác nhận partition

Gửi nhiều event cùng order ID và kiểm tra metadata trả về từ producer hoặc đọc record bằng consumer. Các record cùng key nên được định tuyến vào cùng partition khi partition count và partitioner không thay đổi.

~~~mermaid
sequenceDiagram
    participant A as Order Service
    participant S as StringSerializer
    participant P as Kafka Partitioner
    participant K as Kafka Broker
    participant C as Billing Consumer

    A->>S: key = order-10001
    S-->>P: UTF-8 bytes
    P->>K: Chọn partition
    K-->>C: Record có key bytes
    C->>C: StringDeserializer
    C-->>C: key = order-10001
~~~

## 16. Checklist trước khi đưa key serializer vào vận hành

- [ ] Đã xác định key có cần thiết cho định tuyến hoặc compaction không?
- [ ] Kiểu key trong KafkaTemplate có khớp dữ liệu truyền vào?
- [ ] `key.serializer` được khai báo trong đúng ProducerFactory?
- [ ] Key serializer có tạo byte representation ổn định?
- [ ] Consumer dùng key deserializer tương ứng?
- [ ] Producer và consumer thống nhất format key?
- [ ] Đã kiểm tra hành vi khi key null?
- [ ] Key có đủ ngắn và không chứa secret?
- [ ] Cùng một entity có cùng key qua mọi event?
- [ ] Đã đánh giá tác động khi thay đổi serializer hoặc số partition?
- [ ] Nếu dùng log compaction, key có ổn định và tombstone được hiểu đúng?
- [ ] Custom serializer có kiểm tra dữ liệu lỗi và versioning?
- [ ] Đã unit test byte representation và integration test partition affinity?
- [ ] Các producer khác cùng ghi vào topic có dùng chung quy ước key?

## Kết luận

Key serializer chuyển giá trị key trong ứng dụng thành byte để Kafka producer gửi record. Với Spring Kafka, serializer được khai báo qua `spring.kafka.producer.key-serializer` hoặc `ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG`; kiểu key trong KafkaTemplate phải tương thích với serializer đã chọn. Consumer cần key deserializer đọc đúng byte format.

Key serialization còn ảnh hưởng tới partitioning, ordering và log compaction. Vì vậy, hãy chọn key nghiệp vụ ổn định, tạo byte representation nhất quán, giữ producer/consumer tương thích và kiểm thử cả serialization lẫn partition affinity. Khi cần thay đổi format key, phải đánh giá dữ liệu cũ, consumer hiện hữu và tác động tới việc phân phối record trước khi triển khai.
