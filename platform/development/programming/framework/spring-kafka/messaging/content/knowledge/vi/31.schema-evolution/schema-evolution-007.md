# Schema Registry và serializer tương ứng

Kafka lưu record dưới dạng key, value và headers. Broker không tự hiểu payload JSON, Avro hay Protobuf có cấu trúc nghiệp vụ như thế nào. Nếu producer và consumer tự thay đổi cấu trúc dữ liệu theo thời gian, hai phía có thể không còn tương thích: producer gửi thêm field mà consumer cũ không xử lý được, hoặc consumer mới yêu cầu field mà record cũ chưa có.

**Schema Registry** quản lý schema tập trung. Producer và consumer dùng serializer/deserializer tương ứng để đăng ký, tra cứu schema và mã hóa/giải mã payload. Với Spring Kafka, có thể cấu hình serializer của Confluent cho Avro, Protobuf hoặc JSON Schema thông qua KafkaTemplate và @KafkaListener.

## 1. Schema Registry giải quyết vấn đề gì?

Schema mô tả cấu trúc và kiểu dữ liệu của một event. Ví dụ, event OrderCreated có thể gồm orderId, customerId, totalAmount và createdAt. Nếu các dịch vụ tự định nghĩa schema riêng, việc thêm field hoặc thay đổi kiểu dữ liệu dễ làm producer và consumer lệch nhau.

Schema Registry cung cấp nơi quản lý schema theo subject và version, đồng thời áp dụng quy tắc compatibility trước khi schema mới được chấp nhận.

```text
                  Schema Registry (HTTP)
                 +------------------------+
                 | Subject: orders-value  |
                 | Version 1, 2, 3 ...    |
                 | Schema ID              |
                 | Compatibility policy  |
                 +------------------------+
                       ^            ^
              register/lookup   lookup by ID
                       |            |
Producer               |            |                 Consumer
KafkaTemplate          |            |                 @KafkaListener
     |                 |            |                       ^
     v                 |            |                       |
Avro/Proto/JSON        |            |             Avro/Proto/JSON
Serializer ------------            -------------- Deserializer
     |                                                    ^
     v                                                    |
Kafka topic: serialized record ---------------------------+
```

Schema Registry là dịch vụ riêng, thường giao tiếp qua HTTP. Nó không phải Kafka broker và không lưu toàn bộ event payload. Kafka vẫn lưu record; Registry lưu schema, subject, version, ID và metadata liên quan.

## 2. Subject, version và schema ID

Schema Registry tổ chức schema theo **subject**. Mỗi subject có thể có nhiều version. Một schema được đăng ký sẽ nhận schema ID để serializer ghi vào wire format; consumer dùng ID này để lấy đúng schema khi deserialize.

| Khái niệm | Ý nghĩa |
|---|---|
| Subject | Nhóm schema được quản lý cùng nhau, thường gắn với key hoặc value của topic |
| Version | Phiên bản schema trong một subject, thường tăng tuần tự |
| Schema ID | Định danh schema dùng trong serialized record |
| Compatibility | Quy tắc xác định schema mới có tương thích với schema cũ hay không |
| Reference | Schema có thể tham chiếu schema khác, tùy format và Registry |

Với TopicNameStrategy, schema value của topic orders.events thường thuộc subject orders.events-value; schema key thuộc subject orders.events-key.

Schema ID không phải version number. Một schema có thể được dùng lại và có cùng ID ở nhiều subject tùy cấu hình Registry; không suy ra version chỉ từ số ID.

## 3. Serializer ghi schema ID vào record như thế nào?

Với wire format của Confluent, serialized payload có phần mở đầu chứa magic byte và schema ID, sau đó là dữ liệu được encode theo format tương ứng. Với Avro, phần dữ liệu tiếp theo được encode theo binary Avro; Protobuf và JSON Schema có phần payload format-specific riêng.

```text
Serialized value
+----------------+-------------------+--------------------------+
| Magic byte     | Schema ID         | Encoded payload          |
| 1 byte         | 4 bytes           | Avro / Protobuf / JSON   |
+----------------+-------------------+--------------------------+
```

Serializer thường tìm schema phù hợp trong Registry hoặc đăng ký schema mới theo cấu hình. Nó ghi schema ID vào payload để deserializer biết phải lấy schema nào. Deserializer có thể cache schema để không gọi Registry cho mỗi record.

Không tự cắt hoặc ghép magic byte/schema ID bằng code nghiệp vụ. Hãy dùng serializer/deserializer cùng format và phiên bản tương thích. Nếu consumer dùng StringDeserializer để đọc payload Avro hoặc Protobuf, dữ liệu nhận được không thể diễn giải như chuỗi JSON thông thường.

## 4. Chọn format: Avro, Protobuf hay JSON Schema

Confluent cung cấp serializer/deserializer cho các format phổ biến:

| Format | Serializer | Deserializer | Đặc điểm |
|---|---|---|---|
| Avro | KafkaAvroSerializer | KafkaAvroDeserializer | Schema gọn, kiểu dữ liệu rõ, thường dùng generated SpecificRecord hoặc GenericRecord |
| Protobuf | KafkaProtobufSerializer | KafkaProtobufDeserializer | Dựa trên .proto, hỗ trợ message lồng nhau và field number |
| JSON Schema | KafkaJsonSchemaSerializer | KafkaJsonSchemaDeserializer | JSON dễ quan sát, schema mô tả cấu trúc và ràng buộc dữ liệu |

Chọn format dựa trên hệ sinh thái và yêu cầu dữ liệu:

- Avro phù hợp với event data có schema rõ và cần payload nhị phân gọn.
- Protobuf phù hợp khi tổ chức đã dùng Protocol Buffers hoặc cần chia sẻ contract giữa nhiều ngôn ngữ.
- JSON Schema phù hợp khi cần payload JSON dễ debug nhưng vẫn muốn quản lý schema/compatibility tập trung.

Không nhầm org.springframework.kafka.support.serializer.JsonSerializer của Spring Kafka với KafkaJsonSchemaSerializer của Confluent. Spring JsonSerializer chuyển object thành JSON và có thể dùng type headers; nó không tự đăng ký hoặc tra cứu schema trong Schema Registry.

## 5. Thêm dependency serializer vào ứng dụng Spring Boot

Spring Kafka không đóng gói sẵn các serializer của Confluent. Cần thêm dependency tương ứng với format sử dụng và quản lý version tương thích giữa Confluent client, Kafka client và Spring Kafka.

Ví dụ Maven cho Avro:

```xml
<repositories>
    <repository>
        <id>confluent</id>
        <url>https://packages.confluent.io/maven/</url>
    </repository>
</repositories>

<dependencies>
    <dependency>
        <groupId>io.confluent</groupId>
        <artifactId>kafka-avro-serializer</artifactId>
        <version>CONFLUENT_VERSION</version>
    </dependency>
</dependencies>
```

Với Protobuf, dependency serializer là kafka-protobuf-serializer; với JSON Schema là kafka-json-schema-serializer. Cần có thêm bước generate Java class từ .proto, .avsc hoặc schema tương ứng nếu ứng dụng dùng generated types.

Không tùy tiện chọn version Confluent bằng version Spring Kafka. Đây là hai bộ thư viện có vòng đời release riêng; hãy quản lý version rõ ràng và kiểm tra dependency convergence trong dự án.

## 6. Cấu hình Avro serializer/deserializer trong Spring Boot

Giả sử Schema Registry chạy tại http://localhost:8081, producer gửi Avro và consumer muốn nhận generated SpecificRecord:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    properties:
      "[schema.registry.url]": http://localhost:8081
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
    consumer:
      group-id: order-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
      properties:
        "[specific.avro.reader]": true
```

schema.registry.url được truyền tới Confluent serializer/deserializer. specific.avro.reader=true yêu cầu Avro deserializer tạo generated class triển khai SpecificRecord nếu class tương ứng có trên classpath. Nếu không bật chế độ specific reader, deserializer thường trả GenericRecord.

Các cấu hình bổ sung như auto.register.schemas, subject naming strategy và authentication có thể đặt ở spring.kafka.producer.properties hoặc spring.kafka.properties tùy phạm vi cần áp dụng. Với Spring Boot, các key có dấu chấm trong map nên được biểu diễn bằng bracket notation như ví dụ để binder giữ nguyên tên property.

## 7. Gửi Avro event bằng KafkaTemplate

Giả sử build đã generate class OrderCreated từ Avro schema. Producer có thể dùng class đó làm value type:

```java
import com.example.avro.OrderCreated;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    OrderEventPublisher(KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String customerId, double totalAmount) {
        OrderCreated event = OrderCreated.newBuilder()
                .setOrderId(orderId)
                .setCustomerId(customerId)
                .setTotalAmount(totalAmount)
                .build();

        kafkaTemplate.send("orders.events", orderId, event);
    }
}
```

KafkaAvroSerializer nhận SpecificRecord, xác định schema của record và dùng Schema Registry để lấy hoặc đăng ký schema theo cấu hình. KafkaTemplate vẫn gửi record qua Kafka producer như bình thường; phần tích hợp Registry nằm trong serializer.

Ví dụ giả định schema Avro có các field orderId, customerId, totalAmount và generated class cung cấp builder tương ứng. KafkaTemplate.send() trả về future; trong ứng dụng production nên quan sát future để xử lý lỗi serialize hoặc publish.

## 8. Nhận Avro event bằng @KafkaListener

Khi consumer dùng KafkaAvroDeserializer và specific.avro.reader=true, listener có thể nhận generated Avro class:

```java
import com.example.avro.OrderCreated;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventListener {

    @KafkaListener(topics = "orders.events", groupId = "order-projection")
    public void consume(OrderCreated event) {
        orderProjection.apply(
                event.getOrderId().toString(),
                event.getCustomerId().toString(),
                event.getTotalAmount()
        );
    }
}
```

Nếu listener dùng GenericRecord, có thể đọc field theo tên:

```java
import org.apache.avro.generic.GenericRecord;

@KafkaListener(topics = "orders.events", groupId = "order-audit")
public void consume(GenericRecord event) {
    String orderId = event.get("orderId").toString();
    log.info("Received orderId={}", orderId);
}
```

Generated SpecificRecord cung cấp API kiểu rõ hơn và thuận tiện refactor trong Java. GenericRecord linh hoạt khi cùng consumer phải xử lý nhiều schema hoặc schema được xác định ở runtime, nhưng cần kiểm tra field và kiểu dữ liệu cẩn thận.

## 9. Cấu hình Protobuf serializer/deserializer

Với Protobuf, schema được định nghĩa trong file .proto và Java class được generate từ Protobuf compiler/plugin. Cấu hình Spring Boot dùng các class của Confluent:

```yaml
spring:
  kafka:
    properties:
      "[schema.registry.url]": http://localhost:8081
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.protobuf.KafkaProtobufSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.protobuf.KafkaProtobufDeserializer
```

Producer gửi generated Protobuf message:

```java
import com.example.events.OrderCreated;

OrderCreated event = OrderCreated.newBuilder()
        .setOrderId("order-1001")
        .setCustomerId("customer-42")
        .build();

kafkaTemplate.send("orders.events", "order-1001", event);
```

Consumer có thể nhận generated Protobuf class hoặc kiểu generic phù hợp với cấu hình deserializer và schema. Với Protobuf, field number là một phần của wire contract; không tái sử dụng field number đã xóa. Hãy giữ các field number/name cũ trong reserved khi thay đổi message để tránh payload cũ bị diễn giải sai.

## 10. Cấu hình JSON Schema serializer/deserializer

Nếu muốn giữ payload JSON nhưng quản lý contract trong Schema Registry, dùng KafkaJsonSchemaSerializer và KafkaJsonSchemaDeserializer:

```yaml
spring:
  kafka:
    properties:
      "[schema.registry.url]": http://localhost:8081
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.json.KafkaJsonSchemaSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.json.KafkaJsonSchemaDeserializer
```

Producer có thể gửi một POJO tương ứng với schema JSON đã thống nhất:

```java
public record OrderCreated(String orderId, String customerId, double totalAmount) {
}

kafkaTemplate.send("orders.events", event.orderId(), event);
```

JSON Schema serializer cần schema tương ứng và có thể đăng ký/tra cứu schema theo subject. Cách suy ra schema từ POJO và các lựa chọn như schema cụ thể hoặc schema suy diễn phụ thuộc cấu hình Confluent serializer. Với contract quan trọng, nên quản lý schema có chủ đích và kiểm thử compatibility thay vì dựa hoàn toàn vào suy luận runtime.

## 11. Subject naming strategy

Subject naming strategy quyết định tên subject được dùng khi serializer đăng ký hoặc tra cứu schema. Lựa chọn này ảnh hưởng phạm vi compatibility và cách các record khác loại chia sẻ schema.

| Strategy | Ví dụ subject cho topic orders.events | Ý nghĩa |
|---|---|---|
| TopicNameStrategy | orders.events-value | Mặc định phổ biến; một subject cho value của topic |
| RecordNameStrategy | com.example.avro.OrderCreated | Subject dựa trên fully qualified record/message name |
| TopicRecordNameStrategy | orders.events-com.example.avro.OrderCreated | Kết hợp topic và record name |

Có thể cấu hình strategy cho value:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[value.subject.name.strategy]": io.confluent.kafka.serializers.subject.TopicRecordNameStrategy
```

TopicNameStrategy phù hợp khi mỗi topic có một schema chính cho key/value. RecordNameStrategy hữu ích khi cùng một loại record được dùng ở nhiều topic và muốn quản lý compatibility theo record name. TopicRecordNameStrategy tách schema theo cả topic và record type.

Không thay subject naming strategy tùy tiện sau khi đã có dữ liệu production. Strategy khác có thể khiến serializer tra cứu một subject mới và đăng ký version độc lập, làm chính sách compatibility trước đó không còn được áp dụng ở phạm vi bạn mong đợi.

## 12. Auto register schema và quản lý schema qua CI/CD

Confluent serializer thường có auto.register.schemas=true mặc định. Khi bật, serializer có thể tự đăng ký schema chưa tồn tại trong subject. Cách này tiện cho local development nhưng production cần kiểm soát ai được phép thay đổi contract.

Ví dụ tắt tự đăng ký:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[auto.register.schemas]": false
```

Khi tắt auto registration, schema phải được đăng ký trước trong Registry bằng pipeline hoặc công cụ quản trị. Serializer cần tìm được schema tương ứng trong subject theo strategy đã chọn; nếu không, việc serialize sẽ thất bại.

Một quy trình CI/CD thường gồm:

1. Developer thay đổi schema trong source control.
2. Pipeline kiểm tra cú pháp và chạy compatibility check với subject hiện tại.
3. Nếu tương thích, pipeline đăng ký schema mới hoặc publish artifact schema theo quy trình tổ chức.
4. Deploy consumer có khả năng đọc dữ liệu theo schema mới/cũ.
5. Deploy producer bắt đầu phát record theo schema mới.
6. Theo dõi lỗi deserialize và rollback/forward-fix nếu cần.

Không để mỗi pod tự đăng ký schema khác nhau trong quá trình deploy đồng thời. Quản lý schema tập trung giúp biết chính xác version nào được chấp nhận và ai đã thay đổi contract.

## 13. Compatibility mode trong Schema Registry

Compatibility quyết định một schema mới có thể làm việc với dữ liệu được ghi theo schema cũ theo chiều nào. Các mode thường gặp:

| Mode | Ý nghĩa khái quát |
|---|---|
| BACKWARD | Consumer dùng schema mới có thể đọc dữ liệu được ghi bằng schema trước đó |
| FORWARD | Consumer dùng schema cũ có thể đọc dữ liệu được ghi bằng schema mới |
| FULL | Đáp ứng cả backward và forward compatibility |
| BACKWARD_TRANSITIVE | Backward compatibility với tất cả version trước đó |
| FORWARD_TRANSITIVE | Forward compatibility với tất cả version trước đó |
| FULL_TRANSITIVE | Full compatibility với tất cả version trước đó |
| NONE | Không áp dụng kiểm tra compatibility |

Registry có thể đặt compatibility ở cấp global hoặc override theo subject. Cần xác định rõ subject nào đang áp dụng policy nào; không giả định mọi topic dùng cùng một mode.

Với Avro, thêm field mới có default thường giúp reader schema mới đọc record cũ. Xóa field hoặc thay đổi kiểu có thể phá compatibility tùy chiều. Với Protobuf, không tái sử dụng field number; dùng reserved cho tag đã xóa. Với JSON Schema, thay đổi required, type hoặc constraint có thể làm producer/consumer cũ không còn tương thích.

Compatibility không thay thế integration test. Schema Registry kiểm tra quy tắc theo format, nhưng không biết toàn bộ ý nghĩa nghiệp vụ, ví dụ field amount đổi đơn vị từ đồng sang xu mà kiểu dữ liệu vẫn là number.

## 14. Schema evolution an toàn

Khi thay đổi event, nên áp dụng quy trình expand-and-contract:

1. Thêm field mới theo cách tương thích, ví dụ Avro field có default hoặc JSON Schema field optional.
2. Deploy consumer có thể đọc cả payload cũ và payload mới.
3. Deploy producer bắt đầu gửi field mới.
4. Theo dõi tỷ lệ record cũ/mới và xác nhận mọi consumer đã nâng cấp.
5. Chỉ loại field cũ sau khi không còn consumer phụ thuộc và policy compatibility cho phép.

Ví dụ Avro thêm field channel có default:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.avro",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "customerId", "type": "string"},
    {"name": "channel", "type": ["null", "string"], "default": null}
  ]
}
```

Consumer mới có thể đọc record cũ không có channel bằng giá trị default. Nhưng producer cũ không tự nhiên biết gửi field mới; consumer phải chấp nhận cả hai trạng thái trong giai đoạn chuyển đổi.

Không đổi ý nghĩa field mà giữ nguyên tên và kiểu. Ví dụ totalAmount vẫn là double nhưng đổi từ VND sang USD là thay đổi semantic breaking mà Schema Registry không thể phát hiện.

## 15. Schema Registry authentication và bảo mật

Trong production, Schema Registry có thể yêu cầu Basic Auth, API key/secret hoặc TLS tùy nền tảng. Serializer/deserializer cần được cấp URL và credential phù hợp.

Ví dụ cấu hình Basic Auth theo property của Confluent client:

```yaml
spring:
  kafka:
    properties:
      "[schema.registry.url]": https://schema-registry.example.com
      "[basic.auth.credentials.source]": USER_INFO
      "[basic.auth.user.info]": SCHEMA_REGISTRY_API_KEY:SCHEMA_REGISTRY_API_SECRET
```

Tên property và cơ chế xác thực phụ thuộc bản phân phối Registry. Với Confluent Cloud, hãy dùng credential được cấp và TLS endpoint tương ứng. Không commit API key/secret vào source control; dùng secret manager hoặc biến môi trường được bảo vệ.

Quyền truy cập Registry nên tách theo nhu cầu: producer có thể cần quyền đăng ký schema trong môi trường development, trong khi production có thể chỉ cần quyền đọc schema nếu pipeline CI/CD là nơi duy nhất được phép đăng ký.

## 16. Những lỗi thường gặp

| Lỗi | Nguyên nhân cần kiểm tra |
|---|---|
| Không kết nối được Schema Registry | URL, DNS, TLS, network hoặc service chưa sẵn sàng |
| Unauthorized/Forbidden | API key, credential hoặc ACL Registry không đúng |
| Schema not found | Schema ID không tồn tại trong Registry mà consumer đang truy cập |
| Incompatible schema | Schema mới vi phạm compatibility policy của subject |
| Subject không như mong đợi | Producer và consumer dùng subject naming strategy khác nhau hoặc đổi strategy giữa các lần deploy |
| ClassCastException/GenericRecord thay vì SpecificRecord | specific.avro.reader chưa bật hoặc generated class không có trên classpath |
| SerializationException | Serializer không nhận đúng kiểu object/schema hoặc Registry không đăng ký/tra cứu được schema |
| Consumer đọc byte/JSON sai | Serializer và deserializer không cùng format hoặc dùng nhầm Spring JsonSerializer với Confluent JSON Schema serializer |

Khi debug, ghi nhận topic, key/value subject, schema ID, serializer class và exception gốc. Tránh log payload nhạy cảm. Có thể dùng Schema Registry API hoặc công cụ quản trị để tra subject/version và compatibility policy.

## 17. Kiểm thử producer và consumer với Schema Registry

Unit test có thể kiểm tra mapping và logic tạo event, nhưng integration test cần xác minh serializer/deserializer thực sự tương tác với Registry.

Một bộ kiểm thử nên bao gồm:

1. Producer đăng ký hoặc tra schema đúng subject.
2. Record được publish có schema ID hợp lệ trong wire format.
3. Consumer dùng đúng deserializer và nhận được generated type hoặc generic type như mong đợi.
4. Consumer mới đọc được record được ghi bằng schema cũ theo compatibility mode đã chọn.
5. Schema không tương thích bị từ chối trước khi deploy producer mới.
6. auto.register.schemas=false hoạt động khi schema đã được đăng ký và thất bại rõ ràng khi schema chưa có.
7. Authentication/TLS hoạt động với credential của môi trường test.
8. Subject naming strategy nhất quán giữa producer và pipeline đăng ký schema.

Có thể dùng Kafka và Schema Registry chạy bằng Testcontainers hoặc môi trường integration riêng. Chỉ mock KafkaTemplate không xác minh được wire format, schema ID hay compatibility check.

## 18. Những nhầm lẫn thường gặp

1. **Cho rằng Schema Registry lưu event payload.** Registry quản lý schema/subject/version; Kafka lưu record.
2. **Cho rằng schema ID chính là version.** ID và version là hai khái niệm khác nhau.
3. **Dùng Spring JsonSerializer và kỳ vọng schema được đăng ký.** Cần dùng serializer tích hợp Registry như KafkaJsonSchemaSerializer nếu muốn JSON Schema.
4. **Dùng serializer Avro nhưng consumer dùng StringDeserializer.** Hai phía phải thống nhất wire format và serializer/deserializer.
5. **Bật auto registration ở production mà không kiểm soát.** Schema có thể được đăng ký ngoài quy trình review/compatibility mong muốn.
6. **Đổi subject naming strategy giữa các lần deploy.** Có thể tạo subject mới và bỏ qua policy đã áp dụng ở subject cũ.
7. **Cho rằng BACKWARD/FULL bảo đảm đúng nghĩa nghiệp vụ.** Registry kiểm tra cấu trúc và quy tắc format, không hiểu ý nghĩa đơn vị hoặc quy tắc domain.
8. **Xóa hoặc tái sử dụng field number Protobuf.** Có thể làm dữ liệu cũ bị diễn giải sai; hãy reserve tag đã xóa.
9. **Cho rằng serializer và Spring Kafka phải cùng version.** Cần quản lý tương thích giữa Confluent client, Kafka client và Spring Kafka, không đồng nhất version một cách máy móc.

Schema Registry giúp các producer và consumer chia sẻ một hợp đồng dữ liệu có version và compatibility policy. Trong Spring Kafka, chọn serializer/deserializer cùng format, cấu hình Registry URL và subject naming strategy nhất quán, quản lý schema qua pipeline và kiểm thử cả record cũ lẫn mới. Khi đó, thay đổi schema có thể được triển khai theo từng bước mà không làm các dịch vụ đang chạy ngừng giao tiếp với nhau.
