# Avro, Protobuf và JSON Schema

## Mục tiêu của bài học

Trong chương **Schema và tiến hóa dữ liệu**, bài này so sánh ba định dạng schema thường gặp khi trao đổi event qua Kafka: Avro, Protocol Buffers (Protobuf) và JSON Schema. Trọng tâm là cách mô tả cấu trúc dữ liệu, serialize/deserialize, quản lý phiên bản schema và giữ producer/consumer tương thích khi triển khai không đồng thời.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Schema là hợp đồng dữ liệu giữa các producer và consumer; tiến hóa schema có kiểm soát giúp các thành phần messaging phát triển độc lập mà không làm hỏng luồng event đang chạy.

Sau bài học, người học có thể:

- Phân biệt serialization format với schema và schema registry.
- Hiểu vai trò của Avro, Protobuf và JSON Schema.
- Chọn định dạng theo yêu cầu hiệu năng, khả năng đọc, hệ sinh thái và quản trị contract.
- Thiết kế schema có thể tiến hóa.
- Hiểu backward, forward và full compatibility.
- Cấu hình serializer/deserializer trong Spring Kafka.
- Tích hợp Schema Registry để lưu và tra cứu schema version.
- Triển khai thay đổi schema theo thứ tự an toàn.
- Kiểm thử compatibility, dữ liệu cũ và dữ liệu mới.
- Xử lý schema incompatibility trong môi trường production.

## 1. Vì sao Kafka cần schema?

Kafka lưu trữ key và value dưới dạng byte array. Producer chịu trách nhiệm biến object thành byte; consumer chịu trách nhiệm biến byte thành object. Broker không tự hiểu một payload là OrderCreated, PaymentCaptured hay CustomerUpdated.

Nếu producer và consumer tự thỏa thuận cấu trúc dữ liệu mà không có contract, các thay đổi có thể gây lỗi:

- Producer thêm field nhưng consumer cũ từ chối payload.
- Producer đổi kiểu dữ liệu khiến consumer deserialize thất bại.
- Hai service hiểu cùng một field theo hai ý nghĩa khác nhau.
- Consumer mới không đọc được record cũ còn lưu trong topic.
- Một schema thay đổi nhưng retry topic hoặc DLT vẫn giữ dữ liệu theo schema cũ.

Schema mô tả cấu trúc và kiểu dữ liệu của message. Nó giúp producer biết cần ghi gì và consumer biết cách đọc gì.

~~~mermaid
flowchart LR
    A["Producer object"] --> B["Serializer + schema"]
    B --> C["Kafka record bytes"]
    C --> D["Kafka topic"]
    D --> E["Consumer bytes"]
    E --> F["Deserializer + schema"]
    F --> G["Consumer object"]
    H["Schema Registry"] -. "lưu schema versions" .-> B
    H -. "cung cấp schema" .-> F
~~~

Schema không tự bảo đảm nghiệp vụ đúng. Nó có thể xác nhận một field là string, nhưng không thể tự biết orderId có tồn tại trong hệ thống hay không hoặc trạng thái đơn hàng có hợp lệ hay không. Cần kết hợp schema validation với business validation.

## 2. Phân biệt serialization format, schema và Schema Registry

Ba khái niệm này có liên quan nhưng không giống nhau.

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Serialization format | Quy tắc biểu diễn object thành bytes | Avro binary, Protobuf wire format, JSON text |
| Schema | Mô tả cấu trúc dữ liệu và quy tắc kiểu | Avro record, file .proto, JSON Schema |
| Schema Registry | Lưu schema, version và kiểm tra compatibility | Confluent Schema Registry, Apicurio Registry |

Một serializer có thể hoạt động mà không cần Schema Registry. Ví dụ Spring Kafka có JsonSerializer và JsonDeserializer tích hợp cho JSON object. Tuy nhiên, việc serialize thành JSON không tự tạo ra contract versioned hoặc kiểm tra compatibility giữa producer và consumer.

Schema Registry thường cung cấp:

- Đăng ký schema mới.
- Lưu các version của schema theo subject.
- Kiểm tra compatibility trước khi chấp nhận version mới.
- Tra cứu schema theo ID được serializer ghi vào message.
- Quản lý subject naming strategy.
- Áp dụng compatibility policy.

Registry không nằm trên đường đi của mọi record theo nghĩa phải gửi toàn bộ schema cho mỗi message. Serializer thường đăng ký hoặc tra cứu schema, sau đó ghi thông tin nhận diện schema vào framing của payload. Consumer dùng thông tin đó để lấy schema tương ứng và deserialize.

## 3. Ba định dạng nhìn từ góc độ ứng dụng

**Avro** là định dạng dữ liệu có schema, thường dùng binary encoding để truyền dữ liệu gọn. Schema thường được viết bằng JSON. Avro hỗ trợ schema resolution giữa writer schema và reader schema, vì vậy phù hợp với event có nhiều version cần đọc lại.

**Protobuf** dùng file .proto để định nghĩa message, field number và type. Dữ liệu được encode theo wire format nhị phân. Field number là một phần của contract và cần được giữ ổn định qua các version.

**JSON Schema** mô tả cấu trúc JSON bằng các từ khóa như type, properties, required và additionalProperties. Payload vẫn là JSON nên dễ quan sát và debug hơn, nhưng thường lớn hơn định dạng binary tương ứng.

| Tiêu chí | Avro | Protobuf | JSON Schema |
|---|---|---|---|
| Định nghĩa schema | JSON schema document | File .proto | JSON schema document |
| Payload phổ biến | Binary | Binary | JSON text |
| Đọc bằng mắt | Cần schema/tool | Cần schema/tool | Dễ đọc |
| Sinh code | SpecificRecord tùy toolchain | Generated message classes | Có thể dùng POJO/JSON tree |
| Evolution | Reader/writer schema resolution | Field number và wire compatibility | Quy tắc JSON Schema và registry compatibility |
| Kích thước | Thường gọn | Thường gọn | Thường lớn hơn |
| Phù hợp | Event data, data pipeline | API/service contract hiệu quả | Contract cần JSON và khả năng quan sát |

Không có định dạng tốt nhất cho mọi hệ thống. Hãy chọn theo client languages, công cụ hiện có, yêu cầu schema governance, payload size, hiệu năng và khả năng vận hành.

## 4. Compatibility là gì?

Compatibility mô tả liệu schema version mới và cũ có thể cùng hoạt động mà không làm producer hoặc consumer hiện tại lỗi hay không.

Ba hướng chính:

- **Backward compatibility:** consumer dùng schema mới có thể đọc dữ liệu được ghi theo schema cũ.
- **Forward compatibility:** consumer dùng schema cũ có thể đọc dữ liệu được ghi theo schema mới.
- **Full compatibility:** thỏa mãn cả backward và forward.

Ví dụ:

~~~text
Version 1:
OrderCreated {
  orderId: string
}

Version 2:
OrderCreated {
  orderId: string
  source: string
}
~~~

Nếu field source được thêm theo cách có giá trị mặc định phù hợp với định dạng, consumer mới có thể đọc record cũ. Đây là hướng backward.

Nếu consumer cũ cũng phải đọc record mới, định dạng và schema policy cần cho phép consumer cũ bỏ qua hoặc xử lý field bổ sung. Đây là hướng forward.

Full compatibility cần cả hai hướng. Tuy nhiên, compatibility về cấu trúc không chứng minh ý nghĩa nghiệp vụ tương thích. Nếu amount vẫn là decimal nhưng đổi đơn vị từ VND sang USD, schema có thể vẫn tương thích trong khi nghiệp vụ sai nghiêm trọng.

### 4.1. Compatibility theo một version hay tất cả version

Schema Registry thường hỗ trợ các chế độ:

| Policy | Ý nghĩa khái quát |
|---|---|
| BACKWARD | So schema mới với version trước gần nhất theo hướng backward |
| BACKWARD_TRANSITIVE | So schema mới với tất cả version trước theo hướng backward |
| FORWARD | So schema mới với version trước gần nhất theo hướng forward |
| FORWARD_TRANSITIVE | So với tất cả version trước theo hướng forward |
| FULL | Backward và forward với version trước gần nhất |
| FULL_TRANSITIVE | Backward và forward với tất cả version trước |
| NONE | Không áp dụng kiểm tra compatibility tự động |

Policy mặc định và cách áp dụng phụ thuộc registry. Với topic lưu dữ liệu lâu, transitive compatibility thường đáng cân nhắc vì consumer mới có thể phải đọc record từ nhiều version cũ, không chỉ version gần nhất.

## 5. Avro: schema và schema resolution

Avro schema thường được viết bằng JSON. Một record schema có tên, namespace và danh sách field.

Ví dụ schema version đầu:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    {
      "name": "orderId",
      "type": "string"
    },
    {
      "name": "customerId",
      "type": "string"
    },
    {
      "name": "total",
      "type": "double"
    }
  ]
}
~~~

Schema mô tả tên field và type. Avro serializer dùng schema để encode dữ liệu; deserializer cần writer schema và reader schema để giải mã theo resolution rules.

### 5.1. Thêm field trong Avro

Khi thêm field, nên khai báo default nếu muốn reader mới đọc record được ghi bằng schema cũ.

Version mới:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    {
      "name": "orderId",
      "type": "string"
    },
    {
      "name": "customerId",
      "type": "string"
    },
    {
      "name": "total",
      "type": "double"
    },
    {
      "name": "source",
      "type": "string",
      "default": "unknown"
    }
  ]
}
~~~

Khi reader dùng schema mới đọc record cũ không có source, Avro dùng default unknown.

Nếu thêm field không có default, reader schema mới có thể không đọc được record cũ vì writer schema không cung cấp giá trị cho field bắt buộc đó.

### 5.2. Xóa field trong Avro

Khi reader mới không còn khai báo một field có trong writer schema cũ, reader có thể bỏ qua field cũ. Điều này thường hỗ trợ backward compatibility.

Tuy nhiên, consumer cũ đọc record mới đã bỏ field có thể cần default trong reader schema cũ. Vì vậy, xóa field có thể không forward-compatible nếu schema cũ không có default cho field đó.

Đừng xóa field chỉ vì producer hiện tại không còn ghi nó. Topic có thể vẫn chứa record cũ và consumer cũ có thể chưa được nâng cấp.

### 5.3. Đổi tên field và aliases

Đổi tên field cần cẩn trọng. Avro hỗ trợ aliases trên reader schema để ánh xạ tên cũ sang tên mới.

Ví dụ reader schema mới:

~~~json
{
  "name": "orderNumber",
  "type": "string",
  "aliases": ["orderId"]
}
~~~

Khi reader dùng schema mới, alias cho phép nhận field orderId từ writer schema cũ. Nhưng consumer cũ có thể không hiểu tên mới từ producer mới. Do đó, rename không tự động bảo đảm full compatibility.

Một cách triển khai an toàn thường là giữ field cũ trong giai đoạn chuyển tiếp, thêm field mới có default, migrate consumer và chỉ loại bỏ field cũ sau khi xác nhận không còn consumer phụ thuộc.

### 5.4. Thay đổi type trong Avro

Avro hỗ trợ một số type promotion khi reader giải mã writer data, ví dụ int sang long, float hoặc double theo các quy tắc resolution của Avro.

Không nên suy rộng rằng mọi thay đổi type đều an toàn. string sang long, bytes sang record hoặc thay đổi cấu trúc union có thể gây incompatibility. Luôn chạy compatibility check bằng đúng registry và test dữ liệu thật.

### 5.5. Union và nullable field

Field có thể cho phép null bằng union:

~~~json
{
  "name": "note",
  "type": ["null", "string"],
  "default": null
}
~~~

Default của union phải phù hợp với nhánh đầu tiên theo quy tắc Avro. Ví dụ trên đặt null đầu tiên và default là null.

Không nhầm nullable với optional theo nghĩa business. null có thể biểu thị chưa biết, không áp dụng hoặc không được cung cấp; cần quy định semantics trong event contract.

## 6. Protobuf: field number là contract lâu dài

Protobuf định nghĩa message trong file .proto.

Ví dụ:

~~~protobuf
syntax = "proto3";

package com.example.events;

message OrderCreated {
  string order_id = 1;
  string customer_id = 2;
  double total = 3;
}
~~~

Mỗi field có tên, kiểu và field number. Wire format sử dụng field number để nhận diện field, nên field number quan trọng hơn tên field khi dữ liệu được encode.

### 6.1. Thêm field trong Protobuf

Có thể thêm field mới với một field number chưa từng sử dụng:

~~~protobuf
syntax = "proto3";

package com.example.events;

message OrderCreated {
  string order_id = 1;
  string customer_id = 2;
  double total = 3;
  string source = 4;
}
~~~

Consumer cũ thường bỏ qua field chưa biết theo cơ chế Protobuf. Consumer mới đọc record cũ sẽ thấy giá trị mặc định hoặc trạng thái absent tùy kiểu field và cách khai báo presence.

Với proto3, scalar field thông thường có default như 0, false hoặc chuỗi rỗng. Nếu cần phân biệt “không được gửi” với “được gửi giá trị mặc định”, dùng optional hoặc message wrapper/presence phù hợp.

### 6.2. Không tái sử dụng field number

Khi xóa field, hãy reserve cả number và tên để ngăn version tương lai vô tình dùng lại:

~~~protobuf
message OrderCreated {
  reserved 3;
  reserved "total";

  string order_id = 1;
  string customer_id = 2;
  string source = 4;
}
~~~

Không tái sử dụng field number đã phát hành. Một consumer cũ có thể hiểu bytes của field mới theo ý nghĩa field cũ và tạo dữ liệu sai mà không nhất thiết báo lỗi.

Không đổi field number chỉ vì muốn sắp xếp lại file. Không đổi type hoặc wire semantics tùy tiện; một số type có wire encoding tương tự nhưng vẫn có thể thay đổi ý nghĩa hoặc giới hạn giá trị.

### 6.3. Đổi tên field

Đổi tên field mà giữ nguyên field number thường không thay đổi wire format, nhưng có thể ảnh hưởng generated API, JSON mapping và code consumer. Nếu dùng Protobuf JSON mapping, tên field có thể xuất hiện trong JSON representation; cần đánh giá riêng.

Giữ field number ổn định và triển khai code update theo thứ tự phù hợp. Với field đã xóa, dùng reserved để bảo vệ contract.

### 6.4. Enum trong Protobuf

Enum cần giữ ổn định numeric value. Giá trị đầu tiên thường nên là UNSPECIFIED = 0 để có default rõ ràng:

~~~protobuf
enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_CONFIRMED = 2;
  ORDER_STATUS_CANCELLED = 3;
}
~~~

Khi thêm enum value, consumer cũ có thể gặp numeric value mà code chưa biết. Hãy xác định cách xử lý unknown value và không dùng lại numeric value của enum đã xóa. Có thể reserve tên và number đã loại bỏ.

## 7. JSON Schema: cấu trúc JSON và quy tắc validation

JSON Schema mô tả JSON document bằng các keyword. Ví dụ:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "title": "OrderCreated",
  "properties": {
    "orderId": {
      "type": "string"
    },
    "customerId": {
      "type": "string"
    },
    "total": {
      "type": "number"
    }
  },
  "required": [
    "orderId",
    "customerId",
    "total"
  ],
  "additionalProperties": true
}
~~~

properties định nghĩa field và type. required liệt kê field bắt buộc. additionalProperties quyết định có cho phép field chưa được khai báo hay không.

### 7.1. Thêm property

Có thể thêm property không nằm trong required để payload cũ vẫn hợp lệ với schema mới:

~~~json
{
  "type": "object",
  "properties": {
    "orderId": {
      "type": "string"
    },
    "customerId": {
      "type": "string"
    },
    "total": {
      "type": "number"
    },
    "source": {
      "type": "string"
    }
  },
  "required": [
    "orderId",
    "customerId",
    "total"
  ],
  "additionalProperties": true
}
~~~

Nếu đưa source vào required, record cũ thiếu field này sẽ không hợp lệ với schema mới. Đây là lý do field mới thường nên optional trong giai đoạn tiến hóa.

### 7.2. additionalProperties ảnh hưởng compatibility

Nếu schema cũ đặt additionalProperties là false, consumer validate JSON theo schema cũ có thể từ chối payload mới có field bổ sung. Điều này làm thay đổi nhỏ ở producer trở thành breaking change với consumer cũ.

Nếu cho phép additional properties, consumer có thể chấp nhận field mới mà nó chưa biết. Đổi lại, schema không còn nghiêm ngặt với mọi field ngoài danh sách.

Lựa chọn phụ thuộc governance:

- Contract strict: cấm field ngoài schema, cần rollout consumer/producer có kế hoạch.
- Contract extensible: cho phép field bổ sung, consumer cần bỏ qua field chưa biết.
- Có thể dùng policy riêng cho từng subject/event type.

### 7.3. default trong JSON Schema không tự điền dữ liệu

Keyword default của JSON Schema chủ yếu là annotation mô tả giá trị gợi ý. JSON Schema validator thông thường không tự sửa payload để thêm field thiếu chỉ vì schema khai báo default.

Điều này khác với default resolution của Avro. Nếu consumer cần giá trị mặc định, ứng dụng phải áp dụng trong code hoặc dùng một thư viện có hành vi default injection được xác định rõ.

### 7.4. Thay đổi type và required

Đổi field từ string sang number có thể làm payload cũ không hợp lệ. Thu hẹp enum hoặc thêm constraint như minimum, pattern, maxLength cũng có thể khiến dữ liệu trước đây hợp lệ bị từ chối.

Khi tiến hóa schema, không chỉ kiểm tra tên và type. Cần đánh giá:

- required.
- additionalProperties.
- enum.
- oneOf, anyOf, allOf.
- minimum, maximum.
- pattern, minLength, maxLength.
- Format và custom validation.
- Schema references.

## 8. So sánh cách tiến hóa của ba định dạng

| Thay đổi | Avro | Protobuf | JSON Schema |
|---|---|---|---|
| Thêm field tùy chọn | Thường thêm default để reader mới đọc record cũ | Thêm field number mới | Property mới không nằm trong required |
| Xóa field | Reader mới có thể bỏ qua; reader cũ có thể cần default | Xóa và reserve number/name | Xóa property; đánh giá consumer strict/required |
| Đổi tên | Dùng aliases ở reader schema, vẫn cần rollout | Giữ field number nhưng ảnh hưởng code/JSON mapping | Có thể cần dual fields hoặc migration |
| Đổi type | Chỉ một số promotion được hỗ trợ | Phải giữ wire compatibility và semantics | Phải giữ payload hợp lệ với schema consumer |
| Thêm enum value | Kiểm tra enum resolution | Giữ numeric value, consumer xử lý unknown | Kiểm tra enum constraint và consumer |
| Nullable/optional | Union với null và default phù hợp | Presence/optional hoặc message type | Bỏ khỏi required và định nghĩa null nếu cho phép |

Không nên áp dụng một quy tắc chung cho cả ba định dạng. Ví dụ “thêm field luôn an toàn” chỉ đúng khi cách thêm phù hợp với semantics và compatibility policy của định dạng.

## 9. Schema Registry và subject

Schema Registry lưu schema theo subject. Subject naming strategy quyết định schema nào được quản lý cùng nhau.

Các chiến lược thường gặp:

- TopicNameStrategy: subject theo tên topic và key/value, ví dụ orders-value.
- RecordNameStrategy: subject theo fully qualified record/message name.
- TopicRecordNameStrategy: kết hợp topic và record name.

Chiến lược ảnh hưởng phạm vi compatibility. Với TopicNameStrategy, các record value của cùng topic thường tiến hóa dưới cùng subject. Với RecordNameStrategy, các record type khác nhau có thể được quản lý độc lập dù cùng topic.

Chọn strategy theo thiết kế topic:

- Một topic chỉ chứa một event type: TopicNameStrategy thường dễ hiểu.
- Một topic chứa nhiều event type: cân nhắc RecordNameStrategy hoặc TopicRecordNameStrategy.
- Muốn tách compatibility theo domain event: chọn subject boundary phù hợp.

Không đổi naming strategy tùy tiện giữa các version. Producer có thể đăng ký schema vào subject khác và vô tình bỏ qua compatibility history của subject cũ.

## 10. Schema ID trong Kafka record

Với serializer tích hợp Schema Registry, payload thường mang framing chứa magic byte và schema ID; một số format như Protobuf có thêm thông tin message index. Cấu trúc cụ thể phụ thuộc serializer và registry implementation.

Consumer dùng schema ID để lấy schema tương ứng từ registry hoặc cache. Vì vậy:

- Schema Registry cần khả dụng khi serializer/deserializer cần tra cứu schema chưa có trong cache.
- Consumer phải truy cập được registry và schema ID tương ứng.
- Không xóa schema version còn được tham chiếu bởi record lưu trong Kafka.
- Giữ registry data và backup theo chính sách retention.
- Khi replay record cũ, schema ID cũ vẫn phải được giải quyết.

Không được tự parse hoặc sửa framing bytes nếu chưa hiểu serializer contract. Dùng serializer/deserializer chính thức của registry.

## 11. Tích hợp Avro với Spring Kafka

Với Confluent Schema Registry, producer thường dùng KafkaAvroSerializer, consumer dùng KafkaAvroDeserializer.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    properties:
      schema.registry.url: http://localhost:8081
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
      properties:
        specific.avro.reader: true
~~~

specific.avro.reader yêu cầu deserializer trả về generated SpecificRecord class nếu schema và class phù hợp. Nếu dùng GenericRecord, không bật specific reader theo cách này.

Ví dụ producer dùng generated class từ Avro schema:

~~~java
@Service
public class OrderEventProducer {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventProducer(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "commerce.order.created",
            event.getOrderId().toString(),
            event
        );
    }
}
~~~

OrderCreated trong ví dụ là class được sinh từ Avro schema và implement SpecificRecord. Cách gọi accessor có thể phụ thuộc code generation và phiên bản Avro plugin.
Ví dụ dùng API Spring Kafka 3.x, trong đó KafkaTemplate.send trả về CompletableFuture. Với Spring Kafka 2.x, API tương ứng thường trả về ListenableFuture; điều chỉnh kiểu trả về và callback theo phiên bản dự án.

Consumer:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Với generated class, producer và consumer cần dùng schema/class tương thích. Không nên copy class generated thủ công giữa nhiều service nếu schema là nguồn contract chính.

## 12. Tích hợp Protobuf với Spring Kafka

Với Confluent Schema Registry, serializer/deserializer tương ứng là KafkaProtobufSerializer và KafkaProtobufDeserializer.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    properties:
      schema.registry.url: http://localhost:8081
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.protobuf.KafkaProtobufSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.protobuf.KafkaProtobufDeserializer
      properties:
        specific.protobuf.value.type: com.example.events.OrderCreated
~~~

OrderCreated là generated Protobuf message class. Cấu hình specific type giúp deserializer trả về class cụ thể thay vì một dynamic message representation.

Producer:

~~~java
@Service
public class ProtobufOrderProducer {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public ProtobufOrderProducer(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "commerce.order.created",
            event.getOrderId(),
            event
        );
    }
}
~~~

Tùy generated API, accessor của field có thể khác theo kiểu scalar, message hoặc repeated field. Giữ file .proto làm nguồn contract và sinh code bằng đúng compiler/plugin trong build.

## 13. Tích hợp JSON Schema với Spring Kafka

JSON Schema serializer/deserializer của Confluent có thể quản lý JSON payload cùng schema trong registry.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    properties:
      schema.registry.url: http://localhost:8081
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.json.KafkaJsonSchemaSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.json.KafkaJsonSchemaDeserializer
      properties:
        json.value.type: com.example.events.OrderCreated
~~~

json.value.type chỉ định target Java type cho deserializer theo cấu hình Confluent tương ứng. Cần kiểm tra package và serializer version trong ứng dụng.

Producer vẫn có thể dùng KafkaTemplate<String, OrderCreated>:

~~~java
@Service
public class JsonSchemaOrderProducer {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public JsonSchemaOrderProducer(
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

JSON Schema serialization có thể dùng POJO, JSON tree hoặc cấu trúc tương thích với serializer. Đừng nhầm serializer JSON thông thường của Spring Kafka với serializer JSON Schema có Schema Registry: một bên chỉ serialize JSON object, bên kia còn quản lý schema contract và framing.

## 14. Cấu hình Schema Registry và dependency

Các serializer của Confluent được cung cấp trong các artifact tương ứng, ví dụ:

| Định dạng | Serializer/deserializer artifact |
|---|---|
| Avro | kafka-avro-serializer |
| Protobuf | kafka-protobuf-serializer |
| JSON Schema | kafka-json-schema-serializer |

Phiên bản artifact phải tương thích với Kafka client, Spring Kafka và Schema Registry đang triển khai. Quản lý version bằng dependency management/BOM của nền tảng dự án; không tự lấy phiên bản mới nhất cho từng artifact riêng lẻ.

Các thuộc tính thường cần cấu hình:

- schema.registry.url.
- Serializer/deserializer class.
- auto.register.schemas.
- Subject naming strategy.
- Compatibility policy được quản lý phía registry.
- Specific reader/type cho generated class nếu dùng.
- Authentication/TLS nếu registry được bảo vệ.

Trong production, nhiều tổ chức tắt auto-register schema ở runtime và đăng ký schema qua CI/CD để kiểm tra compatibility trước khi deploy. Producer chỉ dùng schema đã được duyệt. Cách này tránh một instance mới tự đăng ký schema ngoài quy trình kiểm soát.

Ví dụ tắt đăng ký tự động ở producer:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        auto.register.schemas: false
~~~

Khi dùng cấu hình này, pipeline phải đăng ký đúng schema vào đúng subject trước khi producer gửi record. Nếu schema chưa tồn tại hoặc subject không khớp naming strategy, producer có thể thất bại khi serialize.

Các khối YAML ở phần Avro, Protobuf và JSON Schema là các cấu hình thay thế cho từng lựa chọn value format. Không cấu hình đồng thời ba serializer cho cùng một producer value.

## 15. Rollout schema an toàn giữa producer và consumer

Producer và consumer thường được deploy độc lập. Một schema mới có thể xuất hiện trong khi consumer cũ vẫn đang chạy.

Với thay đổi backward-compatible như thêm field optional/default:

1. Đăng ký schema mới và chạy compatibility check.
2. Deploy consumer mới có thể đọc cả dữ liệu cũ và dữ liệu mới.
3. Xác nhận consumer mới chạy ổn định.
4. Deploy producer mới bắt đầu ghi field mới.
5. Theo dõi lỗi deserialize, validation và business logic.
6. Chỉ xóa logic tương thích cũ sau thời gian chuyển tiếp phù hợp.

Với thay đổi forward-compatible, producer mới có thể phát dữ liệu mà consumer cũ vẫn đọc được. Tuy nhiên, cần kiểm tra semantics thực tế và thứ tự rollout với từng client.

~~~mermaid
flowchart TD
    A["Thiết kế schema v2"] --> B["Compatibility check"]
    B --> C{"Pass?"}
    C -->|Không| D["Điều chỉnh schema"]
    D --> B
    C -->|Có| E["Đăng ký schema v2"]
    E --> F["Deploy consumer hỗ trợ v1 và v2"]
    F --> G["Deploy producer ghi v2"]
    G --> H["Theo dõi lỗi và metric"]
    H --> I["Loại bỏ hỗ trợ cũ sau migration"]
~~~

Không triển khai producer mới trước consumer nếu consumer cũ không thể đọc payload mới. Một schema registry báo compatible là tín hiệu tốt nhưng vẫn cần integration test với các phiên bản application thật.

## 16. Schema compatibility không thay thế event versioning

Schema version mô tả cấu trúc payload. Event version hoặc event type version có thể mô tả thay đổi contract ở cấp nghiệp vụ.

Ví dụ:

- OrderCreated thêm field source: có thể chỉ là schema evolution.
- OrderCreated đổi semantics từ “đơn đã tạo” thành “đơn đã thanh toán”: đây là thay đổi nghiệp vụ lớn, nên cân nhắc event type mới.
- amount đổi đơn vị hoặc quy tắc làm tròn: cần version/field semantics rõ ràng dù type không đổi.

Không nên dùng một field version để thay thế toàn bộ schema registry. Ngược lại, schema ID cũng không nên được dùng như event version nghiệp vụ.

Một event contract tốt cần mô tả:

- Event name và domain.
- Ý nghĩa từng field.
- Đơn vị đo và timezone.
- Null/absent/default semantics.
- Quy tắc enum và unknown values.
- Producer ownership.
- Consumer expectations.
- Chính sách deprecation và removal.

## 17. Dữ liệu cũ, replay và retention

Kafka topic có thể giữ record lâu hơn vòng đời của một application version. Consumer mới có thể đọc lại record được ghi từ nhiều tháng trước.

Cần xem xét:

- Consumer mới có đọc được schema ID cũ không?
- Registry còn lưu schema version cũ không?
- Generated classes hoặc schema files cũ còn được quản lý?
- Retry topic và DLT có chứa record từ schema version trước?
- Replay có đi qua serializer/deserializer hiện tại không?
- Có migration hoặc adapter cho payload legacy không?

Không xóa schema version cũ chỉ vì producer mới đã ngừng dùng nó. Record cũ vẫn có thể tham chiếu schema ID đó.

Nếu cần thay đổi contract không tương thích, cân nhắc topic mới, event type mới hoặc adapter chuyển đổi version. Giữ consumer cũ và mới cùng chạy trong thời gian migration giúp giảm rủi ro.

## 18. Kiểm thử schema evolution

Một pipeline kiểm thử nên có các lớp:

### 18.1. Schema validation

- Parse schema.
- Kiểm tra schema hợp lệ với định dạng.
- Kiểm tra generated code có build được.
- Kiểm tra subject và naming strategy.
- Đăng ký thử schema với compatibility policy.

### 18.2. Compatibility test

Kiểm tra schema mới với version cũ theo policy thực tế:

- Avro reader schema mới đọc dữ liệu Avro cũ.
- Protobuf consumer cũ đọc message có field mới.
- JSON Schema validator cũ chấp nhận hoặc từ chối payload mới đúng dự kiến.
- Kiểm tra tất cả version trước nếu dùng transitive compatibility.

### 18.3. Serialization round-trip

Với từng định dạng:

1. Tạo object.
2. Serialize thành bytes.
3. Deserialize thành object.
4. So sánh field và semantics.
5. Kiểm tra schema ID/version trong framing nếu dùng registry.

### 18.4. Integration test với Kafka

Dùng EmbeddedKafka hoặc Testcontainers và registry tương ứng để kiểm tra:

- Producer gửi record theo schema mới.
- Consumer mới đọc record mới.
- Consumer mới đọc record cũ.
- Consumer cũ xử lý record mới theo compatibility expectation.
- Record lỗi schema được xử lý qua error handler/DLT.
- Replay record cũ vẫn tra cứu được schema.

Không chỉ mock serializer. Compatibility là tương tác giữa schema, serializer, registry, payload và consumer version.

## 19. Xử lý schema incompatibility trong production

Khi producer hoặc consumer báo lỗi schema, cần phân biệt nguyên nhân:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Schema registration bị từ chối | Vi phạm compatibility policy | Review diff và điều chỉnh schema |
| Consumer không tìm thấy schema ID | Registry thiếu version hoặc không truy cập được | Kiểm tra registry, cache và backup |
| Deserialization error | Payload/schema không khớp hoặc bytes hỏng | Cách ly record, kiểm tra serializer và schema ID |
| Unknown field/type | Consumer code/generated class cũ | Nâng cấp consumer hoặc adapter |
| JSON validation fail | required, type hoặc additionalProperties không phù hợp | Điều chỉnh contract hoặc rollout |
| Protobuf field đọc sai | Field number bị tái sử dụng/thay đổi | Khôi phục numbering contract và phát hành schema đúng |
| Avro missing field | Reader schema thiếu default cho record cũ | Thêm default phù hợp hoặc dùng migration |
| Consumer cũ lỗi sau producer rollout | Thay đổi không tương thích thực tế | Rollback producer hoặc deploy adapter/consumer tương thích |

Đừng xử lý incompatibility bằng cách tắt compatibility check một cách vội vàng. Nếu buộc phải dùng policy NONE cho một migration, cần có kế hoạch cô lập subject/topic, kiểm thử version cụ thể và đường rollback rõ ràng.

## 20. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| Thêm field bắt buộc không default vào Avro | Consumer mới không đọc được record cũ | Thêm field với default |
| Tái sử dụng Protobuf field number | Consumer cũ hiểu sai dữ liệu | Reserve number và tên đã xóa |
| Đổi enum number Protobuf | Thay đổi semantics trên wire | Giữ numeric value ổn định |
| Thêm property vào JSON khi schema cũ cấm additional properties | Consumer cũ từ chối payload | Dùng rollout có kiểm soát hoặc cho phép extension |
| Nghĩ JSON Schema default tự điền giá trị | Ứng dụng nhận field thiếu | Tự áp dụng default trong code |
| Dùng JSON Serializer thường nhưng nghĩ đã có Registry | Không có schema ID/compatibility governance | Chọn đúng Schema Registry serializer |
| Tắt auto-register mà chưa đăng ký schema | Producer không gửi được record | Đăng ký schema trong CI/CD |
| Xóa schema cũ khỏi Registry | Không đọc được record lịch sử | Giữ schema version theo retention/replay needs |
| Đổi subject naming strategy tùy tiện | Bỏ qua compatibility history | Cố định strategy và migration |
| Chỉ test schema mới với producer mới | Bỏ sót record cũ | Test matrix old/new producer/consumer |

## 21. Checklist trước khi phát hành schema mới

- [ ] Đã chọn Avro, Protobuf hay JSON Schema theo nhu cầu?
- [ ] Schema có mô tả rõ field, null, default và semantics?
- [ ] Subject naming strategy đã được xác định?
- [ ] Compatibility policy phù hợp với retention và replay?
- [ ] Schema mới đã được kiểm tra với version trước?
- [ ] Avro field mới có default phù hợp?
- [ ] Protobuf field number chưa từng dùng lại?
- [ ] JSON Schema required/additionalProperties đã được đánh giá?
- [ ] Producer và consumer serializer/deserializer dùng đúng format?
- [ ] Generated code đồng bộ với schema nguồn?
- [ ] Registry version cũ vẫn được giữ?
- [ ] Đã kiểm thử old record/new consumer và new record/old consumer?
- [ ] Rollout order phù hợp với compatibility direction?
- [ ] Có kế hoạch rollback hoặc adapter nếu deploy thất bại?
- [ ] Retry topic, DLT và replay cũng đọc được schema version cũ?

## Kết luận

Avro, Protobuf và JSON Schema đều mô tả contract dữ liệu nhưng có quy tắc tiến hóa khác nhau. Avro dựa vào writer/reader schema resolution và default; Protobuf dựa nhiều vào field number và wire compatibility; JSON Schema dựa vào validation rules như required, properties và additionalProperties. Schema Registry giúp lưu version và kiểm tra compatibility, còn serializer/deserializer tích hợp registry giúp producer và consumer trao đổi payload có schema ID.

Trong Spring Kafka, hãy chọn serializer/deserializer đúng với định dạng, giữ schema version cũ để đọc record lịch sử và kiểm tra compatibility trước khi deploy. Triển khai consumer có khả năng đọc dữ liệu cũ trước khi producer phát cấu trúc mới khi thay đổi yêu cầu backward compatibility. Kết hợp schema tests, round-trip tests, integration tests và rollout có kiểm soát giúp event contract tiến hóa mà không làm gián đoạn luồng messaging.
