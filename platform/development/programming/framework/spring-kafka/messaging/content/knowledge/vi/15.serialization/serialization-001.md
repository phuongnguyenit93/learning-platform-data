# Serializer và deserializer là gì?

Kafka truyền và lưu record dưới dạng byte. Producer có thể làm việc với object Java, chuỗi hoặc kiểu dữ liệu ứng dụng; consumer cũng muốn nhận lại dữ liệu ở kiểu có ý nghĩa. Serializer và deserializer đảm nhiệm hai chiều chuyển đổi đó:

- **Serializer** chuyển key hoặc value từ kiểu dữ liệu của ứng dụng thành mảng byte trước khi producer gửi record.
- **Deserializer** chuyển mảng byte mà consumer đọc được thành kiểu dữ liệu ứng dụng.

Trong Spring Kafka, serializer được cấu hình cho producer và deserializer được cấu hình cho consumer. Hai phía phải thống nhất định dạng byte, schema và cách diễn giải dữ liệu. Nếu producer gửi JSON nhưng consumer giải mã như Avro, record vẫn có thể được broker lưu thành công nhưng consumer sẽ lỗi khi đọc hoặc chuyển đổi payload.

Serialization vì vậy là một phần của hợp đồng giao tiếp giữa các service. Một thiết kế tốt cần quan tâm cả định dạng dữ liệu, khả năng tương thích khi schema thay đổi, xử lý dữ liệu lỗi và cách quan sát lỗi trong vận hành.

Bài học thuộc chương **Serialization** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Serialization nằm ở đâu trong luồng Kafka?

Một record Kafka có key, value và metadata như timestamp, headers. Broker không cần biết object Java có kiểu gì; nó nhận và lưu các byte của key/value cùng metadata của record.

~~~mermaid
flowchart LR
    A[Object trong ứng dụng] --> B[Serializer]
    B --> C[Key bytes và value bytes]
    C --> D[Kafka Producer]
    D --> E[Kafka Broker và partition]
    E --> F[Kafka Consumer]
    F --> G[Key bytes và value bytes]
    G --> H[Deserializer]
    H --> I[Object trong ứng dụng]
~~~

Ở phía producer:

1. Service tạo event, ví dụ `OrderCreated`.
2. `KafkaTemplate` tạo record với topic, key, value và headers.
3. Producer gọi serializer cho key và value.
4. Kafka client gửi byte tới broker.

Ở phía consumer:

1. Kafka consumer fetch record dạng byte.
2. Consumer gọi deserializer cho key và value.
3. Spring Kafka nhận object đã giải mã và chuyển đến listener.
4. Listener xử lý dữ liệu nghiệp vụ.

Serializer/deserializer không quyết định topic, partition, offset hoặc consumer group. Chúng chỉ chuyển đổi biểu diễn dữ liệu ở biên ứng dụng và Kafka client.

## 2. Serializer và deserializer hoạt động thế nào?

### 2.1. Serializer

Serializer nhận giá trị Java và chuyển thành byte. Với Kafka client, interface cơ bản là `org.apache.kafka.common.serialization.Serializer<T>`.

Ví dụ, `StringSerializer` chuyển chuỗi thành byte theo charset mà implementation sử dụng. `JsonSerializer` của Spring Kafka chuyển object thành JSON byte.

Với event:

~~~java
public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}
~~~

Producer có thể truyền object này vào KafkaTemplate:

~~~java
kafkaTemplate.send("order-events", event.orderId(), event);
~~~

Nếu value serializer là JsonSerializer, object OrderCreated được chuyển thành JSON byte trước khi gửi. Nếu key serializer là StringSerializer, orderId được chuyển thành byte riêng cho key.

### 2.2. Deserializer

Deserializer nhận byte và chuyển thành kiểu ứng dụng. Kafka client định nghĩa `org.apache.kafka.common.serialization.Deserializer<T>`.

Ví dụ:

- `StringDeserializer` chuyển byte thành String.
- `ByteArrayDeserializer` giữ payload ở dạng byte[].
- `JsonDeserializer` của Spring Kafka chuyển JSON byte thành object Java theo cấu hình type/default type hoặc type header.
- Avro/Protobuf deserializer giải mã theo schema và cơ chế tương ứng.

Consumer có thể nhận event trong listener:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "billing-service"
)
public void onOrderCreated(OrderCreated event) {
    billingService.startBilling(event);
}
~~~

Listener nhận được OrderCreated chỉ khi consumer đã giải mã thành công và Spring Kafka có thể chuyển payload đến kiểu tham số. Nếu deserializer lỗi, phương thức listener có thể chưa được gọi; lỗi xảy ra ở giai đoạn poll/deserialization và cần được xử lý theo error handling của container.

### 2.3. Hai chiều phải tương thích

Serializer và deserializer không nhất thiết phải là cùng một class. Điều quan trọng là byte do producer tạo ra phải đúng định dạng mà consumer hiểu.

| Producer serializer | Consumer deserializer | Kết quả |
| --- | --- | --- |
| StringSerializer | StringDeserializer | Tương thích cho chuỗi theo cùng encoding. |
| JsonSerializer | JsonDeserializer | Có thể tương thích nếu payload, type metadata và cấu hình type phù hợp. |
| ByteArraySerializer | ByteArrayDeserializer | Giữ nguyên byte; ứng dụng tự diễn giải payload. |
| Avro serializer | Avro deserializer tương ứng | Cần thống nhất schema và schema identifier/registry. |
| JsonSerializer | Avro deserializer | Không tương thích nếu không có lớp chuyển đổi riêng. |

Một producer gửi JSON hợp lệ không có nghĩa mọi consumer đều hiểu schema đó. Contract cần định nghĩa field, kiểu dữ liệu, quy tắc null, versioning và compatibility.

## 3. Key serializer và value serializer

Mỗi Kafka record có thể có key và value. Kafka client gọi serializer riêng cho từng phần:

- `key.serializer` chuyển key thành byte.
- `value.serializer` chuyển payload thành byte.

Ví dụ Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

Với cấu hình này, key có kiểu String và value là object được serialize thành JSON.

Key có vai trò quan trọng với partitioning. Partitioner thường dùng byte của key để chọn partition. Vì vậy, key serializer phải ổn định giữa các producer cùng gửi một loại key. Nếu hai service serialize cùng giá trị nghiệp vụ theo byte khác nhau, partition mapping có thể khác và ordering theo key có thể bị ảnh hưởng.

Value serializer định dạng payload mà consumer sẽ đọc. Nó không tự biến field bên trong value thành Kafka key. Nếu cần định tuyến theo orderId, producer phải truyền orderId làm key riêng.

Consumer cần cấu hình deserializer tương ứng:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Kiểu key/value ở generic của KafkaTemplate hoặc ConsumerFactory giúp kiểm tra kiểu trong code Java, nhưng không thay thế cấu hình serializer/deserializer. Generic type không tự thay đổi byte trên wire.

## 4. Các serializer/deserializer cơ bản của Kafka

Kafka cung cấp một số implementation phổ biến trong package `org.apache.kafka.common.serialization`:

| Serializer | Deserializer | Kiểu dữ liệu |
| --- | --- | --- |
| StringSerializer | StringDeserializer | `String` |
| IntegerSerializer | IntegerDeserializer | `Integer` |
| LongSerializer | LongDeserializer | `Long` |
| ShortSerializer | ShortDeserializer | `Short` |
| FloatSerializer | FloatDeserializer | `Float` |
| DoubleSerializer | DoubleDeserializer | `Double` |
| ByteArraySerializer | ByteArrayDeserializer | `byte[]` |
| ByteBufferSerializer | ByteBufferDeserializer | `ByteBuffer` |
| UUIDSerializer | UUIDDeserializer | `UUID` |

Chọn serializer theo kiểu dữ liệu và wire format mà hệ thống cần. Với chuỗi hoặc byte[] đơn giản, serializer có sẵn thường đủ dùng. Với object nghiệp vụ, có thể chọn JSON, Avro, Protobuf hoặc định dạng schema-based khác.

Không nên dùng Java native serialization một cách tùy tiện cho event liên dịch vụ. Java serialization gắn chặt payload với cấu trúc class và cơ chế runtime của Java, gây khó tương thích giữa ngôn ngữ, phiên bản và có rủi ro bảo mật khi giải mã dữ liệu không đáng tin cậy. Hãy chọn định dạng có contract rõ ràng và có thể kiểm soát.

## 5. Cấu hình JSON serializer/deserializer của Spring Kafka

Spring Kafka cung cấp `JsonSerializer` và `JsonDeserializer` để làm việc với JSON. Đây là lựa chọn thuận tiện khi ứng dụng Spring trao đổi event có cấu trúc.

### 5.1. Producer cấu hình JsonSerializer

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

Khi gọi:

~~~java
kafkaTemplate.send(
    "order-events",
    event.orderId(),
    new OrderCreated(
        "evt-100",
        "order-100",
        new BigDecimal("125.50"),
        Instant.now()
    )
);
~~~

JsonSerializer chuyển object thành JSON byte. Ví dụ payload có thể biểu diễn tương tự:

~~~json
{
  "eventId": "evt-100",
  "orderId": "order-100",
  "total": 125.50,
  "occurredAt": "2026-11-17T03:00:00Z"
}
~~~

Đây là minh họa dạng JSON; cách biểu diễn thời gian và số thập phân thực tế phụ thuộc Jackson configuration và serializer đang sử dụng.

### 5.2. Consumer cấu hình JsonDeserializer

Consumer cần biết kiểu đích để chuyển JSON byte thành object. Có thể cấu hình default type:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
~~~

Trong ví dụ:

- `spring.json.value.default.type` chỉ định kiểu Java mặc định cho value.
- `spring.json.trusted.packages` giới hạn package mà JsonDeserializer được phép tạo kiểu khi sử dụng type information.
- Package phải khớp với vị trí class thực tế của ứng dụng consumer.

Không nên đặt trusted packages thành `*` chỉ để làm lỗi deserialize biến mất. Hãy giới hạn package được tin cậy theo các event type cần nhận. Type header từ producer cũng cần được kiểm soát vì nó có thể chứa tên class; không nên coi metadata type là contract ổn định giữa các service nếu package nội bộ thay đổi.

### 5.3. Type headers và default type

JsonSerializer của Spring Kafka có thể ghi thông tin kiểu Java vào Kafka headers. JsonDeserializer có thể dùng type header để quyết định class cần tạo. Cách này thuận tiện khi một topic chứa nhiều loại event, nhưng có thể làm consumer phụ thuộc tên package/class của producer.

Một số lựa chọn:

- Dùng type header do Spring Kafka tạo và cấu hình mapping type rõ ràng.
- Tắt type headers nếu consumer đã biết kiểu đích qua default type.
- Dùng type mapping để ánh xạ token ngắn, ổn định sang class cục bộ.
- Dùng envelope chung có trường eventType/version thay vì phụ thuộc tên class Java.

Ví dụ tắt type headers trên producer:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        spring.json.add.type.headers: false
~~~

Khi tắt type header, consumer cần biết kiểu đích qua default type hoặc cơ chế khác. Không nên tắt header rồi bỏ quên cấu hình deserializer, nếu không consumer có thể không xác định được class cần tạo.

Tên property và hành vi cụ thể cần đối chiếu phiên bản Spring Kafka đang dùng. Spring Kafka có thể cấu hình JsonSerializer/JsonDeserializer qua properties hoặc constructor/setter tùy API phiên bản.

## 6. Schema và khả năng tương thích khi dữ liệu thay đổi

Event thường tồn tại lâu hơn một phiên bản ứng dụng. Producer có thể được deploy trước hoặc sau consumer; một consumer cũ có thể đọc record được tạo bởi producer mới. Vì vậy, thay đổi schema cần có quy tắc tương thích.

Ví dụ schema ban đầu:

~~~json
{
  "eventId": "evt-100",
  "orderId": "order-100",
  "total": 125.50
}
~~~

Phiên bản sau thêm field:

~~~json
{
  "eventId": "evt-100",
  "orderId": "order-100",
  "total": 125.50,
  "currency": "VND"
}
~~~

Nếu consumer cũ bỏ qua field không biết, việc thêm field có thể tương thích. Tuy nhiên, compatibility còn phụ thuộc serializer/deserializer, cấu hình Jackson, kiểu dữ liệu, constructor và validation của ứng dụng.

Các nguyên tắc thường dùng:

- Thêm field mới với default hợp lý hoặc cho phép thiếu field khi cần backward compatibility.
- Tránh đổi kiểu field hiện có nếu consumer cũ vẫn đọc dữ liệu.
- Tránh đổi tên hoặc xóa field mà consumer cũ còn phụ thuộc.
- Dùng version/schema identifier khi có thay đổi không tương thích.
- Kiểm thử producer mới với consumer cũ và ngược lại theo chiến lược triển khai.
- Không tái sử dụng cùng một event type cho payload có ý nghĩa khác nhau.

### 6.1. Backward, forward và full compatibility

Các thuật ngữ compatibility thường được dùng trong schema registry:

| Loại | Ý nghĩa khái quát |
| --- | --- |
| Backward | Consumer/schema mới có thể đọc dữ liệu được tạo theo schema cũ. |
| Forward | Consumer/schema cũ có thể đọc dữ liệu được tạo theo schema mới. |
| Full | Đáp ứng cả backward và forward theo quy tắc registry. |

Chính sách cụ thể phụ thuộc định dạng schema và cấu hình registry. JSON không tự có một compatibility guarantee chỉ vì thêm field. Với Avro/Protobuf và schema registry, compatibility có thể được kiểm tra theo schema evolution rules của hệ thống.

### 6.2. Event contract độc lập với class Java

Không nên coi package và tên class Java là contract công khai của event. Nếu producer đổi package từ `com.example.orders` sang `com.example.ordering`, consumer phụ thuộc type header có thể không giải mã được dù JSON field không đổi.

Một contract ổn định nên mô tả:

- Event name và version.
- Field bắt buộc/tùy chọn.
- Kiểu và định dạng field.
- Ý nghĩa nghiệp vụ.
- Quy tắc null/default.
- Tương thích khi thêm/đổi/xóa field.
- Cách định danh event và correlation.

Có thể dùng schema registry hoặc repository contract chung để quản lý schema. Với JSON thuần, cần có quy trình review và kiểm thử compatibility vì broker không tự xác thực schema của payload.

## 7. Avro, Protobuf và các định dạng schema-based

JSON dễ đọc và phổ biến, nhưng với hệ thống nhiều service hoặc yêu cầu schema chặt chẽ, có thể cân nhắc Avro hoặc Protobuf.

| Định dạng | Đặc điểm |
| --- | --- |
| JSON | Dễ đọc, dễ debug, phổ biến; payload thường lớn hơn và schema enforcement phụ thuộc ứng dụng/tooling. |
| Avro | Dựa trên schema, hỗ trợ schema evolution theo quy tắc; thường dùng cùng schema registry. |
| Protobuf | Định dạng nhị phân gọn, có field number và quy tắc tương thích; phù hợp nhiều ngôn ngữ. |
| Thrift/định dạng khác | Có thể phù hợp nếu hệ thống đã có contract và tooling tương ứng. |

Khi dùng schema registry, serializer thường đăng ký hoặc tra schema, sau đó ghi schema identifier cùng payload theo wire format do serializer định nghĩa. Consumer deserializer lấy schema tương ứng để giải mã.

Không thể lấy JsonDeserializer để đọc trực tiếp payload Avro hoặc Protobuf. Mỗi định dạng cần serializer/deserializer tương ứng và cấu hình registry/schema phù hợp.

Lựa chọn định dạng nên dựa trên khả năng tương thích, yêu cầu hiệu năng, dung lượng, khả năng quan sát và năng lực vận hành schema. Định dạng nhị phân không tự làm hệ thống đáng tin cậy nếu không có quy trình quản lý schema.

## 8. Custom serializer và deserializer

Khi định dạng dữ liệu đặc thù, có thể triển khai interface Serializer và Deserializer của Kafka.

Ví dụ custom serializer cho một kiểu đơn giản:

~~~java
public class OrderIdSerializer implements Serializer<OrderId> {

    @Override
    public byte[] serialize(String topic, OrderId data) {
        if (data == null) {
            return null;
        }

        return data.value().getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Deserializer tương ứng:

~~~java
public class OrderIdDeserializer implements Deserializer<OrderId> {

    @Override
    public OrderId deserialize(String topic, byte[] data) {
        if (data == null) {
            return null;
        }

        return new OrderId(
            new String(data, StandardCharsets.UTF_8)
        );
    }
}
~~~

Ví dụ giả định OrderId là value object có constructor và accessor tương ứng. Serializer và deserializer cần thống nhất encoding, null semantics và validation.

Khi viết custom implementation, cần chú ý:

- Xử lý null rõ ràng.
- Dùng encoding xác định, không phụ thuộc charset mặc định của máy.
- Không nuốt exception rồi trả payload giả.
- Không log payload nhạy cảm.
- Đóng tài nguyên nếu serializer/deserializer sở hữu tài nguyên riêng.
- Không giữ mutable state dùng chung giữa nhiều client nếu implementation không thread-safe.
- Kiểm thử round-trip và dữ liệu sai định dạng.

Kafka Serializer/Deserializer có các lifecycle method như configure/close trong interface. Hãy triển khai theo contract của phiên bản Kafka client và cách factory khởi tạo instance. Nếu cần dependency injection phức tạp, có thể dùng cấu hình Spring Kafka hỗ trợ supplier/instance phù hợp.

## 9. Null, empty bytes và tombstone

Cần phân biệt ba trường hợp:

| Trường hợp | Ý nghĩa |
| --- | --- |
| Serializer nhận null và trả null | Kafka record có key/value null tương ứng. |
| Serializer trả byte array rỗng | Payload tồn tại nhưng có độ dài bằng 0. |
| Serializer trả byte array có dữ liệu | Payload có byte cần được deserialize. |

Với compacted topic, record có key khác null và value null được dùng làm tombstone để đánh dấu key cần xóa khỏi trạng thái compacted sau khi compaction xử lý. Record có key null không phải tombstone cho một entity cụ thể.

Deserializer có thể nhận data null và cần xử lý theo semantics của ứng dụng. Không nên tự động coi null, empty string, empty byte[] và JSON literal `null` là cùng một giá trị.

Ví dụ:

- Kafka value null: không có payload byte.
- Empty byte[]: payload dài 0 byte.
- JSON `null`: có bốn byte ký tự null trong JSON UTF-8.
- JSON `{}`: object rỗng, khác hoàn toàn các trường hợp trên.

Phân biệt đúng các trường hợp này rất quan trọng khi xử lý tombstone, compacted topic và dữ liệu tùy chọn.

## 10. Headers và metadata không thay thế payload schema

Kafka record có headers để mang metadata như correlation ID, trace ID, content type hoặc schema version. Headers có thể giúp consumer chọn cách xử lý nhưng không tự đảm bảo payload tương thích.

Ví dụ producer thêm header:

~~~java
ProducerRecord<String, OrderCreated> record =
    new ProducerRecord<>(
        "order-events",
        event.orderId(),
        event
    );

record.headers().add(
    "event-version",
    "2".getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record);
~~~

Consumer có thể đọc header:

~~~java
@KafkaListener(topics = "order-events", groupId = "billing-service")
public void onOrderCreated(
        ConsumerRecord<String, OrderCreated> record) {

    Header versionHeader = record.headers().lastHeader("event-version");
    String version = versionHeader == null
        ? "1"
        : new String(versionHeader.value(), StandardCharsets.UTF_8);

    billingService.process(version, record.value());
}
~~~

Trong ví dụ, header event-version là metadata do ứng dụng quy ước. Consumer cần xử lý trường hợp header thiếu hoặc sai định dạng. Nếu header quyết định schema, phải đảm bảo producer luôn ghi đúng và consumer có mapping rõ ràng.

Không nên dùng header để mang một bản schema tùy ý quá lớn hoặc thay thế schema registry. Header phù hợp với metadata nhỏ, ổn định và có mục đích rõ.

## 11. Cấu hình đầy đủ producer và consumer trong Spring Boot

Ví dụ cấu hình JSON cơ bản:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        spring.json.add.type.headers: false
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
~~~

Các điểm cần chú ý:

- Producer dùng StringSerializer và JsonSerializer.
- Consumer dùng StringDeserializer và JsonDeserializer tương ứng.
- Producer tắt type headers nên consumer được cấu hình default type.
- Trusted packages được giới hạn.
- Auto commit được tắt để listener container quản lý acknowledgement/commit theo cấu hình.

Nếu producer gửi nhiều event type vào cùng topic, một default type duy nhất có thể không đủ. Khi đó cần type mapping, envelope chung, schema registry hoặc deserializer có dispatch theo contract.

Tên class trong default type phải tồn tại trong ứng dụng consumer. Nếu producer và consumer có package khác nhau, không nên phụ thuộc vào type header chứa tên class producer; hãy dùng type mapping hoặc contract trung lập.

## 12. Deserialization error và xử lý lỗi

Lỗi serialization có thể xảy ra ở producer trước khi record được gửi. Lỗi deserialization xảy ra ở consumer khi byte không thể chuyển thành kiểu mong muốn.

Các nguyên nhân thường gặp:

- JSON không hợp lệ hoặc payload bị cắt.
- Producer và consumer dùng định dạng khác nhau.
- Consumer default type sai.
- Type header trỏ tới class không tồn tại hoặc không được tin cậy.
- Schema identifier không được tìm thấy.
- Field có kiểu không tương thích.
- Custom deserializer ném exception khi dữ liệu sai.

Với Spring Kafka, lỗi deserialization có thể xảy ra trước khi listener method được gọi. Để đưa lỗi vào error handling của container, có thể dùng cơ chế như `ErrorHandlingDeserializer` bọc deserializer thực tế. Nó cho phép giữ thông tin lỗi trong header để error handler xử lý record lỗi theo chính sách.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
~~~

ErrorHandlingDeserializer bọc delegate deserializer. Khi delegate lỗi, Spring Kafka có thể đưa thông tin exception vào header để container error handler hoặc dead-letter recoverer xử lý. Cần cấu hình error handler phù hợp; chỉ thêm wrapper không tự động bảo đảm mọi record lỗi được chuyển DLT.

Không nên retry vô hạn một payload sai định dạng. Lỗi schema/format thường không tự hết nếu dữ liệu không thay đổi. Hãy phân biệt lỗi dữ liệu không thể deserialize với lỗi tạm thời như schema registry không truy cập được, rồi chọn retry, DLT hoặc dừng xử lý phù hợp.

## 13. Security và dữ liệu không đáng tin cậy

Deserializer chuyển byte từ broker thành object trong ứng dụng. Vì dữ liệu có thể đến từ producer khác hoặc topic mà nhiều hệ thống ghi, không nên giả định mọi payload đều đáng tin cậy.

Một số nguyên tắc:

- Chỉ cho phép các package/type cần thiết khi dùng JsonDeserializer.
- Tránh Java native deserialization cho dữ liệu bên ngoài.
- Giới hạn kích thước record và độ sâu payload theo nhu cầu.
- Validate field nghiệp vụ sau khi deserialize.
- Không log toàn bộ payload nếu chứa thông tin nhạy cảm.
- Quản lý schema và type mapping rõ ràng.
- Cập nhật dependency serializer/deserializer để nhận bản vá bảo mật.

Trusted packages chỉ là một lớp kiểm soát type của JsonDeserializer; nó không thay thế validation, ACL Kafka hoặc kiểm tra quyền truy cập dữ liệu.

## 14. Kiểm thử serializer và deserializer

Một serializer/deserializer tốt cần được kiểm thử ở nhiều cấp.

### 14.1. Round-trip test

Với cùng định dạng, serialize rồi deserialize phải khôi phục dữ liệu tương đương theo contract:

~~~java
@Test
void shouldRoundTripOrderCreated() {
    JsonSerializer<OrderCreated> serializer = new JsonSerializer<>();
    JsonDeserializer<OrderCreated> deserializer =
        new JsonDeserializer<>(OrderCreated.class);

    OrderCreated event = new OrderCreated(
        "evt-100",
        "order-100",
        new BigDecimal("125.50"),
        Instant.parse("2026-11-17T03:00:00Z")
    );

    byte[] bytes = serializer.serialize("order-events", event);
    OrderCreated restored =
        deserializer.deserialize("order-events", bytes);

    assertThat(restored).isEqualTo(event);
}
~~~

Đây là ví dụ khái quát. Với JsonDeserializer, cấu hình type headers, trusted packages và constructor có thể khác theo phiên bản; test thực tế cần cấu hình serializer/deserializer giống môi trường ứng dụng.

Round-trip không chứng minh producer và consumer độc lập tương thích. Cần thêm test bằng payload fixture đã phát hành hoặc schema version cũ/mới.

### 14.2. Compatibility test

Có thể giữ các JSON fixture đại diện cho phiên bản event cũ và xác nhận consumer hiện tại đọc được. Khi thay schema, kiểm thử:

- Consumer mới đọc payload cũ.
- Consumer cũ đọc payload mới nếu chiến lược triển khai yêu cầu.
- Field thiếu, null hoặc thêm mới được xử lý đúng.
- Payload không hợp lệ được phân loại thành lỗi có thể quan sát.
- Header/type/schema version được ánh xạ đúng.

### 14.3. Integration test với Kafka

Dùng Embedded Kafka hoặc Testcontainers để xác nhận đường đi đầy đủ:

1. KafkaTemplate gửi object.
2. Producer serializer chuyển object thành byte.
3. Broker lưu record.
4. Consumer deserializer khôi phục object.
5. @KafkaListener nhận đúng payload.
6. Lỗi deserialize đi qua ErrorHandlingDeserializer và error handler theo cấu hình.

Mock serializer/deserializer có thể hữu ích cho unit test, nhưng không thay thế integration test khi cần xác nhận wire format giữa producer và consumer.

## 15. Theo dõi serialization trong vận hành

Khi serialization/deserialization gặp lỗi, cần có thông tin để xác định topic, schema và producer/consumer liên quan.

Nên theo dõi:

- Số lỗi serializer theo producer.
- Số lỗi deserializer theo topic và consumer group.
- Tỷ lệ payload không hợp lệ.
- Phiên bản event/schema.
- Kích thước record.
- Tỷ lệ DLT do lỗi dữ liệu.
- Độ trễ gọi schema registry nếu sử dụng.
- Thời gian serialize/deserialize nếu payload lớn hoặc throughput cao.

Log nên có topic, partition, offset, key/event ID nếu an toàn, exception type và schema/version. Không nên ghi toàn bộ payload lỗi vào log mặc định; payload có thể chứa dữ liệu nhạy cảm hoặc quá lớn.

Nếu lỗi chỉ xảy ra sau khi deploy producer mới, hãy so sánh schema/headers/serializer configuration của phiên bản mới với consumer đang chạy. Nếu lỗi xảy ra trên nhiều topic cùng lúc, kiểm tra dependency chung như schema registry, shared serializer hoặc configuration.

## 16. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| Kafka broker lưu object Java. | Broker lưu key/value dưới dạng byte cùng metadata record. |
| Serializer chỉ áp dụng cho value. | Key và value có serializer riêng. |
| Generic type của KafkaTemplate tự chọn serializer. | Generic hỗ trợ kiểu Java; serializer phải được cấu hình. |
| JSON hợp lệ bảo đảm mọi consumer đọc được. | Consumer còn cần schema/type/configuration tương thích. |
| Type header là contract bền vững giữa service. | Header có thể chứa class name nội bộ; nên dùng mapping hoặc schema contract ổn định. |
| Trusted packages thay thế validation. | Đây chỉ là kiểm soát type của JsonDeserializer, không xác thực nghiệp vụ. |
| Key null giống empty byte[]. | Null và payload rỗng có semantics khác nhau; tombstone cần key khác null và value null. |
| Deserialization error luôn gọi được listener. | Lỗi có thể xảy ra trước listener method; cần error handling ở container. |
| Retry luôn sửa được lỗi deserialize. | Payload sai schema thường không tự hết; cần DLT hoặc xử lý dữ liệu. |
| Round-trip test đủ chứng minh compatibility. | Cần test schema/version giữa producer và consumer độc lập. |

## 17. Checklist thiết kế serialization

Trước khi phát hành event contract, hãy kiểm tra:

1. Key và value có định dạng rõ ràng không?
2. Producer serializer và consumer deserializer có tương thích byte format không?
3. Key serializer có ổn định giữa các producer cùng domain không?
4. Consumer có cấu hình type/default type hoặc schema mapping rõ không?
5. Type headers có được dùng có chủ đích và không phụ thuộc package nội bộ không?
6. Schema có quy tắc backward/forward compatibility không?
7. Null, empty bytes, JSON null và tombstone được phân biệt đúng không?
8. Deserialization error có đi qua error handler/DLT theo chính sách không?
9. Trusted packages và validation có giới hạn phù hợp không?
10. Có round-trip, compatibility fixture và integration test với Kafka không?
11. Có metric/log đủ để truy vết lỗi mà không lộ payload nhạy cảm không?

Serializer và deserializer là ranh giới chuyển đổi giữa kiểu dữ liệu ứng dụng và byte format của Kafka. Khi hai phía thống nhất wire format, schema và versioning, producer có thể phát event và consumer có thể giải mã độc lập qua nhiều lần triển khai. Khi có lỗi, cần phân biệt lỗi chuyển đổi ở producer, lỗi giải mã trước listener và lỗi validation nghiệp vụ sau khi đã có object để chọn cách xử lý phù hợp.

