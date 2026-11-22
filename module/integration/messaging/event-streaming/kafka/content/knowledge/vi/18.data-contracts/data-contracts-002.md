# Serializer, deserializer và sự tương thích giữa các ngôn ngữ

## Mục tiêu bài học

Kafka truyền và lưu record dưới dạng byte. Producer phải chuyển key/value từ kiểu dữ liệu của ứng dụng sang byte bằng serializer; consumer phải giải mã byte về kiểu dữ liệu mà ứng dụng hiểu bằng deserializer. Khi nhiều dịch vụ viết bằng Java, Python, Go hoặc .NET cùng trao đổi event, các bên phải thống nhất wire format và data contract. Việc hai ứng dụng cùng đọc được byte chưa đủ để bảo đảm chúng hiểu cùng ý nghĩa nghiệp vụ.

Bài học trình bày vai trò của serializer/deserializer, cách chọn JSON, Avro, Protobuf hoặc JSON Schema, cách dùng Schema Registry để quản lý schema và kiểm tra compatibility, cùng các quy tắc versioning để producer và consumer triển khai độc lập mà không phá vỡ luồng dữ liệu.

Sau bài học, người học có thể:

- Mô tả luồng serialize và deserialize của Kafka producer/consumer.
- Phân biệt wire format, schema và data contract.
- Chọn format phù hợp cho hệ thống nhiều ngôn ngữ.
- Cấu hình serializer/deserializer trong Kafka Java client và Spring Kafka.
- Giải thích Schema Registry, subject, schema version và schema ID.
- Phân biệt backward, forward, full và các chế độ transitive compatibility.
- Thay đổi schema an toàn cho Avro, Protobuf và JSON Schema.
- Kiểm thử contract giữa producer và consumer thuộc nhiều ngôn ngữ.

## 1. Serializer và deserializer nằm ở đâu trong Kafka?

Ứng dụng làm việc với object hoặc kiểu dữ liệu riêng của ngôn ngữ lập trình. Kafka broker không hiểu object Java, class Python hay struct Go. Producer serialize key và value thành byte trước khi gửi; consumer deserialize byte sau khi fetch.

~~~mermaid
flowchart LR
    A[Java / Python / Go object] --> B[Serializer]
    B --> C[Key bytes + Value bytes]
    C --> D[Kafka broker]
    D --> E[Key bytes + Value bytes]
    E --> F[Deserializer]
    F --> G[Consumer object]
~~~

Ví dụ producer có một object OrderCreated. Serializer chuyển object thành byte theo một format đã thống nhất. Kafka lưu và replicate các byte đó. Consumer dùng deserializer tương ứng để đọc lại thành object hoặc cấu trúc dữ liệu.

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| Serializer | Chuyển key/value thành byte trước khi gửi |
| Deserializer | Chuyển byte thành kiểu dữ liệu ứng dụng |
| Schema | Mô tả cấu trúc và kiểu của dữ liệu |
| Schema Registry | Lưu schema, quản lý version/subject và kiểm tra compatibility |
| Kafka broker | Lưu, replicate và phân phối byte record |
| Data contract | Quy định cấu trúc, ý nghĩa, quy tắc tương thích và cách sử dụng event |

Kafka broker thường không deserialize payload để kiểm tra nghiệp vụ. Nếu tổ chức bật broker-side schema ID validation hoặc một cơ chế validation bổ sung, đó là tính năng được cấu hình riêng; không nên mặc định rằng mọi broker đều kiểm tra schema.

## 2. Wire format, schema và data contract

Ba khái niệm này có liên quan nhưng không thay thế cho nhau:

- Wire format xác định byte được mã hóa và truyền trên Kafka như thế nào.
- Schema mô tả field, kiểu dữ liệu, cấu trúc lồng nhau và quy tắc đọc/ghi.
- Data contract bao gồm schema cùng ý nghĩa nghiệp vụ, đơn vị đo, timezone, nullability, quy tắc versioning, ownership và kỳ vọng xử lý.

Ví dụ hai dịch vụ đều đọc được field amount kiểu số nhưng có thể hiểu khác nhau: một bên hiểu là đồng Việt Nam, bên kia hiểu là đơn vị xu. Schema đúng kiểu nhưng data contract vẫn sai.

Một event contract nên xác định ít nhất:

| Thành phần | Ví dụ |
|---|---|
| Event type | OrderCreated |
| Event identity | eventId duy nhất, ổn định |
| Aggregate key | orderId |
| Event time | occurredAt theo UTC |
| Amount | decimal với currency rõ ràng |
| Optional fields | source có thể không có |
| Versioning | schema subject và compatibility mode |
| Semantics | event biểu thị đơn hàng vừa được tạo, không phải trạng thái hiện tại |

Không dùng tên class Java làm hợp đồng duy nhất. Tên class, package và cách biểu diễn decimal/date của một ngôn ngữ không nhất thiết tương ứng trực tiếp với kiểu dữ liệu của ngôn ngữ khác.

## 3. Chọn format dữ liệu

Các format phổ biến:

| Format | Biểu diễn | Điểm mạnh | Cần lưu ý |
|---|---|---|---|
| JSON | Text có cấu trúc | Dễ đọc, phổ biến, hỗ trợ nhiều ngôn ngữ | Payload thường lớn hơn binary; kiểu và schema cần được quản lý rõ |
| Avro | Binary encoding theo schema | Gọn, hỗ trợ schema evolution và reader/writer schema | Cần schema để giải mã; thường dùng Schema Registry |
| Protobuf | Binary message theo field number | Hiệu quả, contract rõ, hỗ trợ nhiều ngôn ngữ | Phải quản lý field number và reserved tag cẩn thận |
| JSON Schema | JSON được mô tả bằng schema | Giữ khả năng đọc của JSON và có validation schema | Quy tắc compatibility phụ thuộc schema và cấu hình validator |

Không nên dùng Java native serialization (ObjectOutputStream) làm wire contract cho topic được chia sẻ giữa nhiều ngôn ngữ. Format này phụ thuộc class Java, package và chi tiết runtime, khó tương thích với Python/Go/.NET và có rủi ro khi deserialize dữ liệu không tin cậy. Hãy chọn một format độc lập ngôn ngữ như JSON, Avro hoặc Protobuf.

### 3.1. Khi nào dùng JSON?

JSON phù hợp khi:

- Payload cần dễ đọc khi debug.
- Nhiều hệ thống tích hợp đã hỗ trợ JSON.
- Lưu lượng và kích thước payload không phải giới hạn chính.
- Nhóm phát triển có quy trình kiểm tra schema riêng.

Chỉ dùng StringSerializer/StringDeserializer không tự tạo ra data contract. Producer và consumer vẫn phải thống nhất field, kiểu, timezone, encoding UTF-8, null/missing semantics và cách xử lý field lạ.

### 3.2. Khi nào dùng Avro?

Avro phù hợp khi:

- Nhiều producer/consumer cùng chia sẻ event schema.
- Muốn payload binary gọn.
- Cần schema evolution được kiểm tra tập trung.
- Có nhiều ngôn ngữ cần dùng cùng schema.

Avro có writer schema và reader schema. Consumer dùng reader schema để diễn giải dữ liệu được ghi bằng writer schema; Avro resolution áp dụng quy tắc tương thích giữa hai schema.

### 3.3. Khi nào dùng Protobuf?

Protobuf phù hợp với hệ thống cần message binary gọn và code generation cho nhiều ngôn ngữ. Field number là một phần của wire contract. Khi xóa field, cần reserve tag/name để tránh tái sử dụng số field cũ cho ý nghĩa khác.

### 3.4. Khi nào dùng JSON Schema?

JSON Schema phù hợp khi muốn payload vẫn là JSON nhưng cấu trúc được định nghĩa và quản lý phiên bản. Cần chú ý các keyword như required, type, enum và additionalProperties. Một schema đặt additionalProperties=false có thể từ chối field mới mà consumer cũ chưa biết.

## 4. Ví dụ data contract cho OrderCreated

Một event có thể được định nghĩa như sau:

~~~json
{
  "eventId": "evt-2026-000042",
  "eventType": "OrderCreated",
  "orderId": "order-42",
  "occurredAt": "2026-11-20T10:15:30Z",
  "amount": {
    "value": "125000.00",
    "currency": "VND"
  },
  "source": "checkout-web"
}
~~~

Contract cần quy định:

- eventId là định danh duy nhất và không đổi khi retry.
- orderId là key phù hợp để giữ thứ tự event theo đơn hàng.
- occurredAt dùng ISO-8601 UTC; không gửi local time không có timezone.
- amount.value là decimal, không dùng floating point cho tiền.
- amount.currency dùng mã tiền tệ đã thống nhất.
- source là field tùy chọn nếu producer không có thông tin nguồn.

Nếu producer Java dùng BigDecimal, Python dùng Decimal và Go dùng một decimal library hoặc chuỗi decimal, contract vẫn thống nhất vì wire representation được quy định độc lập với kiểu nội bộ của từng ngôn ngữ.

## 5. Avro schema và schema evolution

Ví dụ Avro schema cho OrderCreated:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "eventId", "type": "string" },
    { "name": "orderId", "type": "string" },
    {
      "name": "occurredAt",
      "type": { "type": "long", "logicalType": "timestamp-millis" }
    },
    {
      "name": "amount",
      "type": {
        "type": "bytes",
        "logicalType": "decimal",
        "precision": 12,
        "scale": 2
      }
    },
    { "name": "currency", "type": "string" },
    { "name": "source", "type": ["null", "string"], "default": null }
  ]
}
~~~

Trong schema này:

- timestamp-millis biểu diễn thời điểm dưới dạng số mili giây theo epoch.
- decimal xác định precision và scale; mỗi ngôn ngữ cần serializer/deserializer hỗ trợ logical type hoặc chuyển đổi rõ ràng.
- source là union nullable, nhánh null đứng đầu và default là null.

Không suy ra ý nghĩa chỉ từ kiểu Avro. Ví dụ long có thể là số đếm, epoch milliseconds hoặc một đại lượng khác; logical type và data contract giúp xác định cách diễn giải.

### 5.1. Writer schema và reader schema

Producer ghi record theo writer schema. Consumer giải mã với reader schema của nó. Nếu hai schema tương thích, Avro có thể resolve khác biệt như field mới có default hoặc field cũ không còn được reader sử dụng.

Ví dụ schema v1 có eventId và orderId. Schema v2 thêm source nullable với default null. Consumer dùng v2 có thể đọc record cũ v1 vì reader schema có default cho field mới.

~~~mermaid
flowchart TD
    A[Producer dùng writer schema v1] --> B[Avro serializer]
    B --> C[Kafka record bytes + schema ID]
    C --> D[Consumer lấy writer schema v1]
    D --> E[Reader schema v2]
    E --> F[Avro schema resolution]
    F --> G[Object theo schema v2]
~~~

### 5.2. Thay đổi schema cần đánh giá

| Thay đổi | Rủi ro | Hướng thiết kế |
|---|---|---|
| Thêm field nullable có default | Thấp hơn với reader mới | Dùng default hợp lệ và kiểm tra compatibility |
| Thêm field bắt buộc không có default | Reader mới có thể không đọc được record cũ | Tránh hoặc triển khai theo giai đoạn |
| Xóa field | Reader cũ có thể vẫn cần field đó | Đánh giá cả backward và forward compatibility |
| Đổi kiểu field | Có thể không tương thích | Kiểm tra type promotion được format hỗ trợ |
| Đổi tên field | Có thể làm reader không tìm thấy field | Dùng alias nếu format hỗ trợ và kiểm thử thực tế |
| Đổi ý nghĩa nghiệp vụ nhưng giữ nguyên kiểu | Schema checker có thể không phát hiện | Tạo event/field mới hoặc version contract rõ ràng |

Với Avro, thêm field mới có default thường hỗ trợ backward compatibility vì reader mới có thể đọc record cũ. Xóa field có thể hỗ trợ backward compatibility vì reader mới bỏ qua field cũ, nhưng forward compatibility phụ thuộc reader cũ có thể xử lý field bị thiếu hay không. Luôn kiểm tra chiều tương thích đang chọn.

## 6. Schema Registry, subject và schema ID

Schema Registry lưu schema và version, kiểm tra compatibility trước khi đăng ký schema mới, đồng thời cung cấp schema để serializer/deserializer mã hóa và giải mã record.

Với Confluent wire format phổ biến cho Avro và JSON Schema, payload bắt đầu bằng:

~~~text
byte 0: magic byte (0)
byte 1-4: schema ID (big-endian)
remaining bytes: encoded payload
~~~

Với Protobuf, phần sau schema ID còn có message indexes để xác định message type trong file schema trước phần payload Protobuf. Chi tiết wire format cần theo đúng serializer/registry implementation và version đang sử dụng.

Schema ID giúp deserializer tra schema tương ứng. Nó không phải schema version và cũng không phải ID nghiệp vụ của event.

### 6.1. Subject naming

Subject là phạm vi mà Schema Registry dùng để quản lý version và compatibility. Naming strategy cần được producer/consumer và các ngôn ngữ thống nhất.

Các strategy thường gặp:

| Strategy | Subject thường được tạo |
|---|---|
| TopicNameStrategy | orders-value hoặc orders-key |
| RecordNameStrategy | Tên đầy đủ của record/type |
| TopicRecordNameStrategy | Kết hợp topic và record/type |

TopicNameStrategy thường là lựa chọn mặc định trong nhiều tích hợp Confluent. Nếu nhiều loại record cùng nằm trong một topic, cần đánh giá strategy khác và cách consumer phân biệt record. Không thay naming strategy giữa các producer một cách tùy tiện vì có thể tạo subject khác nhau và bỏ qua compatibility history đã có.

### 6.2. Đăng ký và đọc schema

Luồng producer:

1. Serializer xác định schema của object.
2. Serializer tra schema trong cache hoặc hỏi Schema Registry.
3. Nếu cần, schema được đăng ký vào subject theo compatibility policy.
4. Serializer lấy schema ID và mã hóa payload.
5. Producer gửi byte record đến Kafka.

Luồng consumer:

1. Consumer fetch byte record.
2. Deserializer đọc schema ID từ wire format.
3. Deserializer tra schema trong cache hoặc Schema Registry.
4. Deserializer giải mã payload theo writer schema và reader schema.
5. Ứng dụng nhận object/record tương ứng.

Schema Registry availability có thể ảnh hưởng producer/consumer khi cần đăng ký hoặc tra schema chưa có trong cache. Cần cấu hình endpoint, TLS/authentication, timeout và giám sát riêng cho Registry.

## 7. Compatibility modes

Compatibility xác định schema mới có thể làm việc với dữ liệu được ghi theo schema cũ theo chiều nào.

| Mode | Ý nghĩa tổng quát |
|---|---|
| BACKWARD | Consumer dùng schema mới có thể đọc dữ liệu được ghi bằng schema trước đó |
| BACKWARD_TRANSITIVE | Schema mới phải tương thích ngược với tất cả version trước trong subject |
| FORWARD | Consumer dùng schema cũ có thể đọc dữ liệu được ghi bằng schema mới |
| FORWARD_TRANSITIVE | Schema mới phải tương thích xuôi với tất cả version trước |
| FULL | Tương thích cả backward và forward với version trước |
| FULL_TRANSITIVE | Tương thích cả hai chiều với tất cả version trước |
| NONE | Không kiểm tra compatibility khi đăng ký schema |

Ý nghĩa chính xác của phép kiểm tra phụ thuộc format và implementation. Không nên suy luận rằng một thay đổi JSON Schema sẽ có cùng kết quả như Avro hoặc Protobuf.

### 7.1. Chọn mode theo chiến lược triển khai

- BACKWARD phù hợp khi consumer mới được triển khai để đọc dữ liệu cũ; đây là lựa chọn phổ biến khi muốn nâng consumer trước producer.
- FORWARD phù hợp khi producer mới được triển khai nhưng consumer cũ vẫn phải đọc dữ liệu mới.
- FULL phù hợp khi cần hỗ trợ cả consumer mới đọc dữ liệu cũ và consumer cũ đọc dữ liệu mới trong giai đoạn rolling deployment.
- Các mode TRANSITIVE kiểm tra với toàn bộ lịch sử subject, hữu ích khi dữ liệu cũ còn tồn tại lâu hoặc replay từ nhiều version.
- NONE bỏ qua kiểm tra và chỉ nên dùng khi có quy trình kiểm soát khác rõ ràng.

### 7.2. Ví dụ rollout an toàn

Giả sử v1 có eventId và orderId. v2 thêm source là field optional:

1. Đăng ký schema v2 và xác nhận compatibility.
2. Triển khai consumer có thể đọc cả v1 và v2.
3. Theo dõi consumer mới hoạt động ổn định.
4. Triển khai producer bắt đầu ghi source.
5. Giữ khả năng đọc v1 trong thời gian dữ liệu cũ còn tồn tại.
6. Chỉ bỏ hỗ trợ v1 khi retention/replay window và toàn bộ consumer đã được đánh giá.

Quy trình này giúp tránh producer phát field mà consumer cũ không chấp nhận.

## 8. Protobuf: field number là wire contract

Trong Protobuf, tên field có thể thay đổi trong một số tình huống source-level, nhưng field number là định danh trên wire. Không tái sử dụng field number đã xóa vì consumer cũ có thể diễn giải dữ liệu mới thành field cũ.

Ví dụ:

~~~protobuf
syntax = "proto3";

package com.example.events;

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  int64 occurred_at_epoch_ms = 3;
  string currency = 4;
  string source = 5;
}
~~~

Nếu xóa field 4, hãy reserve số 4 và tên cũ:

~~~protobuf
message OrderCreated {
  reserved 4;
  reserved "currency";

  string event_id = 1;
  string order_id = 2;
  int64 occurred_at_epoch_ms = 3;
  string source = 5;
}
~~~

Quy tắc thực hành:

- Không đổi field number đã phát hành.
- Không tái sử dụng tag đã xóa; reserve tag/name.
- Thêm field với số mới.
- Cân nhắc enum unknown value và default semantics.
- Hiểu rõ khác biệt giữa field không xuất hiện, field có giá trị mặc định và field optional có presence.
- Kiểm tra compatibility bằng công cụ/schema Registry phù hợp với Protobuf.

## 9. JSON và JSON Schema: optional, null và missing

Trong JSON, ba trạng thái sau có thể mang ý nghĩa khác nhau:

~~~json
{}
~~~

~~~json
{"source": null}
~~~

~~~json
{"source": ""}
~~~

- Missing: producer không gửi field.
- Null: producer gửi field với giá trị null.
- Empty string: producer gửi chuỗi rỗng.

Data contract phải quy định consumer hiểu từng trường hợp như thế nào. Không phải ngôn ngữ hoặc JSON binding nào cũng ánh xạ missing và null giống nhau.

JSON Schema dùng required để chỉ định field bắt buộc. additionalProperties quyết định có cho phép field chưa khai báo hay không. Nếu đặt false, consumer validator có thể từ chối event khi producer thêm field mới.

Lưu ý: keyword default trong JSON Schema chủ yếu là annotation cho ứng dụng/tooling; validator không tự động chèn giá trị mặc định vào JSON instance chỉ vì schema khai báo default. Nếu muốn áp dụng default, ứng dụng phải thực hiện rõ ràng.

Ví dụ:

~~~json
{
  "type": "object",
  "required": ["eventId", "orderId"],
  "properties": {
    "eventId": { "type": "string" },
    "orderId": { "type": "string" },
    "source": {
      "type": ["string", "null"],
      "default": null
    }
  },
  "additionalProperties": true
}
~~~

Trong ví dụ này source có thể là string hoặc null và không bắt buộc. additionalProperties=true cho phép field khác xuất hiện; nếu contract muốn strict, cần cân nhắc tác động của thay đổi schema đến consumer đang chạy.

## 10. Cấu hình serializer/deserializer trong Kafka Java client

### 10.1. String và JSON

Với JSON text, ứng dụng có thể dùng StringSerializer/StringDeserializer rồi serialize object bằng Jackson hoặc thư viện JSON khác:

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;

Properties producerProps = new Properties();
producerProps.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
producerProps.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
producerProps.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
~~~

Consumer:

~~~java
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;

Properties consumerProps = new Properties();
consumerProps.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
consumerProps.put(ConsumerConfig.GROUP_ID_CONFIG, "order-projection");
consumerProps.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName());
consumerProps.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName());
~~~

Sau khi nhận String, consumer dùng ObjectMapper để parse JSON và validate theo contract. Cần xử lý rõ lỗi JSON malformed, field không hợp lệ, unknown field và version không được hỗ trợ.

### 10.2. Avro với Schema Registry

Ví dụ cấu hình producer:

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;
import org.apache.avro.Schema;
import org.apache.avro.generic.GenericData;
import org.apache.avro.generic.GenericRecord;
import io.confluent.kafka.serializers.KafkaAvroSerializer;

Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    KafkaAvroSerializer.class.getName());
props.put("schema.registry.url", "http://localhost:8081");
~~~

Ví dụ tạo GenericRecord và gửi bằng producer đã cấu hình serializer:

~~~java
Schema schema = new Schema.Parser().parse(
    "{\"type\":\"record\",\"name\":\"OrderCreated\",\"fields\":["
        + "{\"name\":\"eventId\",\"type\":\"string\"},"
        + "{\"name\":\"orderId\",\"type\":\"string\"}]}"
);

GenericRecord event = new GenericData.Record(schema);
event.put("eventId", "evt-2026-000042");
event.put("orderId", "order-42");

try (KafkaProducer<String, GenericRecord> producer = new KafkaProducer<>(props)) {
    producer.send(new ProducerRecord<>("orders", "order-42", event)).get();
}
~~~

Trong ví dụ, schema được khai báo trong code để minh họa. Dự án thực tế nên lưu schema thành file/resource có version và đưa bước kiểm tra compatibility vào CI. Producer gửi GenericRecord; serializer đăng ký hoặc tra schema theo subject, thêm schema ID vào wire format rồi mã hóa Avro payload.

Ví dụ consumer:

~~~java
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import io.confluent.kafka.serializers.KafkaAvroDeserializer;

Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-projection");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    KafkaAvroDeserializer.class.getName());
props.put("schema.registry.url", "http://localhost:8081");
props.put("specific.avro.reader", true);
~~~

specific.avro.reader=true yêu cầu deserializer trả về generated SpecificRecord khi ứng dụng có generated Avro class tương ứng. Nếu dùng GenericRecord, bỏ cấu hình này và xử lý record theo schema động.

Các class serializer/deserializer trên thuộc Confluent serializer library. Dependency version phải tương thích với Kafka client, Schema Registry và Spring Kafka của dự án.

## 11. Spring Kafka và cấu hình nhiều ngôn ngữ

Ví dụ application.yml cho Avro:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
      properties:
        schema.registry.url: http://localhost:8081
    consumer:
      group-id: order-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
      properties:
        schema.registry.url: http://localhost:8081
        specific.avro.reader: true
~~~

Với các ngôn ngữ khác, mỗi client dùng serializer/deserializer tương ứng của hệ sinh thái đó nhưng phải thống nhất:

- Cùng Kafka topic và key strategy.
- Cùng schema format và wire format.
- Cùng Schema Registry endpoint/context và subject naming strategy.
- Cùng authentication/TLS policy.
- Cùng schema compatibility policy.
- Cùng ý nghĩa timestamp, decimal, enum, null và missing field.

Ví dụ Java producer ghi Avro theo subject orders-value. Python consumer cần dùng thư viện tương thích wire format và Schema Registry để đọc schema ID rồi giải mã Avro. Nếu Python chỉ gọi JSON parser trên byte Avro, nó sẽ không thể đọc payload.

Tương tự, một Go producer dùng Protobuf không thể gửi arbitrary Protobuf bytes rồi kỳ vọng Java Avro deserializer đọc được. Các bên phải chọn cùng format và contract.

## 12. Subject naming, schema registration và cấu hình kiểm soát

Schema Registry thường cho phép serializer tự đăng ký schema mới khi gửi. Cách này tiện trong môi trường phát triển, nhưng production nên cân nhắc pipeline quản lý schema rõ ràng.

Một số cấu hình thường gặp của Confluent serializers:

| Cấu hình | Vai trò |
|---|---|
| schema.registry.url | Endpoint của Schema Registry |
| auto.register.schemas | Cho phép serializer tự đăng ký schema mới |
| use.latest.version | Dùng schema version mới nhất theo subject trong các luồng được hỗ trợ |
| value.subject.name.strategy | Cách tạo subject cho value |
| key.subject.name.strategy | Cách tạo subject cho key |
| specific.avro.reader | Trả về generated Avro class thay vì GenericRecord |

Nếu đặt auto.register.schemas=false, schema cần được đăng ký trước hoặc được chọn theo cách cấu hình của serializer. Điều này giúp kiểm soát release schema nhưng đòi hỏi CI/CD có bước publish/validate schema.

Không dùng use.latest.version một cách mù quáng. Producer object cần khớp schema được chọn; schema mới nhất của subject có thể không phải schema mong muốn cho producer version hiện tại.

## 13. Kiểm thử compatibility và contract

Không chỉ kiểm tra code compile. Cần kiểm tra byte thực tế do một ngôn ngữ phát ra có thể được client ngôn ngữ khác giải mã.

Một quy trình kiểm thử nên có:

1. Lưu schema version trong source control.
2. Validate schema syntax và compatibility trong CI.
3. Sinh code cho các ngôn ngữ cần dùng.
4. Tạo golden test fixture được serialize bằng producer chuẩn.
5. Dùng Java, Python, Go hoặc client khác đọc fixture và so sánh giá trị.
6. Kiểm thử ngược: serialize từ client khác rồi consumer chuẩn đọc.
7. Kiểm thử field optional, null, missing, enum unknown, timestamp và decimal.
8. Kiểm thử producer cũ với consumer mới và producer mới với consumer cũ theo compatibility mode đã chọn.
9. Kiểm thử dữ liệu cũ trong thời gian retention/replay window.
10. Chặn release nếu schema incompatible hoặc fixture bị thay đổi ngoài ý muốn.

### 13.1. Golden fixture

Golden fixture là một mẫu byte/message có schema ID hoặc schema đi kèm, được tạo và lưu có chủ đích để các ngôn ngữ cùng kiểm tra. Khi thay serializer version, fixture giúp phát hiện wire format thay đổi.

Không nên chỉ so sánh JSON string theo thứ tự field vì JSON object không yêu cầu thứ tự key. Hãy parse và so sánh cấu trúc/giá trị theo contract. Với binary Avro/Protobuf, kiểm tra semantic result sau deserialize thay vì kỳ vọng byte giống nhau khi encoder có thể biểu diễn hợp lệ theo cách khác.

### 13.2. Kiểm thử contract nghiệp vụ

Ngoài schema validation, hãy kiểm tra:

- eventId có duy nhất và ổn định khi retry không?
- key có đúng aggregate để bảo đảm ordering không?
- timestamp có UTC và đúng đơn vị không?
- amount có chính xác decimal và currency không?
- Enum mới có làm consumer cũ lỗi không?
- Field missing và null có được xử lý như contract quy định không?
- Consumer có bỏ qua field chưa biết hay từ chối message?
- Error có được đưa vào retry/DLQ theo chính sách không?

## 14. Xử lý lỗi serialize và deserialize

| Lỗi | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| SerializationException | Object không khớp schema hoặc serializer không hỗ trợ kiểu | Kiểm tra schema, object và logical type |
| Schema Registry unavailable | Registry không truy cập được hoặc TLS/auth lỗi | Kiểm tra endpoint, network, credential và cache |
| Schema not found | Schema ID không tồn tại trong Registry/context đang dùng | Kiểm tra cluster/context và dữ liệu được publish |
| Incompatible schema | Schema mới không đạt compatibility policy | Sửa schema hoặc thiết kế migration |
| Unknown enum value | Producer gửi enum mới consumer chưa biết | Thiết kế fallback/unknown handling và rollout |
| Malformed JSON | Payload không phải JSON hợp lệ | Validate producer, quarantine/DLQ theo chính sách |
| Protobuf tag bị tái sử dụng | Thay đổi schema phá wire contract | Reserve tag/name, phát hành field mới |
| Decimal/timestamp sai giá trị | Khác scale, precision hoặc time unit giữa ngôn ngữ | Chuẩn hóa contract và thêm cross-language fixture |

Deserializer exception có thể xảy ra trước khi listener nhận được object. Với Spring Kafka, cấu hình ErrorHandlingDeserializer và container error handler phù hợp giúp chuyển lỗi deserialize vào luồng xử lý lỗi có kiểm soát. Không bỏ qua message lỗi một cách im lặng vì có thể làm sai tiến độ consumer.

## 15. Bảo mật và vận hành Schema Registry

Schema Registry là dịch vụ riêng với Kafka broker. Producer/consumer có thể cần credential và TLS riêng để truy cập Registry, kể cả khi Kafka cluster đã xác thực thành công.

Các điểm cần quản lý:

- Endpoint Registry theo môi trường.
- TLS certificate và hostname verification.
- Basic auth, bearer token hoặc cơ chế xác thực mà nền tảng hỗ trợ.
- Quyền đăng ký schema và quyền đọc schema.
- Compatibility mode ở global hoặc subject level.
- Backup/restore và quy trình khôi phục schema metadata.
- Cache và timeout của serializer/deserializer.
- Theo dõi lỗi đăng ký, lookup latency và Registry availability.

Không nhúng password hoặc token vào source control. Dùng secret manager hoặc cơ chế cấp credential của nền tảng triển khai.

## 16. Quy trình phát hành data contract

Một quy trình release có thể gồm:

1. Xác định owner của event và consumer phụ thuộc.
2. Sửa schema cùng mô tả semantics, nullability và ví dụ payload.
3. Chạy syntax validation và compatibility check.
4. Chạy cross-language contract tests.
5. Đăng ký schema version vào đúng subject.
6. Triển khai consumer tương thích trước nếu thay đổi yêu cầu consumer mới đọc dữ liệu cũ.
7. Triển khai producer bắt đầu phát schema mới.
8. Theo dõi deserialization errors, consumer lag và DLQ.
9. Giữ khả năng đọc schema cũ trong toàn bộ retention/replay window.
10. Chỉ loại bỏ field/schema cũ sau khi mọi producer/consumer đã chuyển đổi và replay requirement được xác nhận.

Schema Registry giúp kiểm soát cấu trúc và compatibility; nó không thay thế ownership, tài liệu semantics, testing hoặc rollout coordination.

## 17. Bài tập thực hành

### Bài tập 1: JSON giữa Java và Python

1. Tạo contract OrderCreated với eventId, orderId, occurredAt, amount và source.
2. Viết Java producer dùng JSON serializer.
3. Viết Python consumer parse cùng payload.
4. Kiểm tra timezone, decimal, missing và null.
5. Thêm field optional và xác nhận consumer cũ xử lý được.

### Bài tập 2: Avro và Schema Registry

1. Đăng ký schema v1 cho OrderCreated.
2. Gửi record bằng KafkaAvroSerializer.
3. Đọc record bằng KafkaAvroDeserializer.
4. Thêm source nullable có default null để tạo v2.
5. Chạy compatibility check.
6. Đọc record v1 bằng reader schema v2.

### Bài tập 3: Protobuf field evolution

1. Tạo message OrderCreated với các field number cố định.
2. Gửi record từ Java producer.
3. Đọc bằng client Go hoặc Python có generated code.
4. Thêm field mới với tag chưa dùng.
5. Xóa field cũ và reserve tag/name.
6. Kiểm tra consumer cũ và mới.

### Bài tập 4: Compatibility mode

1. Tạo schema v1 và đăng ký vào subject.
2. Thử thêm field bắt buộc không có default.
3. Kiểm tra BACKWARD.
4. Thử thêm field optional có default.
5. So sánh BACKWARD, FORWARD và FULL.
6. Ghi lại thứ tự deploy producer/consumer phù hợp.

## 18. Câu hỏi tự kiểm tra

1. Vì sao Kafka broker không hiểu object Java hoặc Python?
2. Serializer khác schema và data contract như thế nào?
3. Wire format của Avro/Confluent giúp consumer tìm writer schema ra sao?
4. Schema ID có phải schema version hoặc event ID không?
5. BACKWARD khác FORWARD compatibility như thế nào?
6. Vì sao thêm field có default thường dễ tương thích hơn thêm field bắt buộc?
7. Vì sao Protobuf không được tái sử dụng field number đã xóa?
8. JSON missing, null và empty string có thể mang ý nghĩa khác nhau ra sao?
9. Vì sao Java và Python phải thống nhất decimal và timestamp representation?
10. Golden fixture giúp phát hiện lỗi cross-language nào?
11. Schema Registry unavailable có thể ảnh hưởng serializer/deserializer ra sao?
12. Vì sao cần giữ schema cũ trong thời gian retention/replay window?

Khi serializer, deserializer, schema và data contract được thống nhất, các dịch vụ Java, Python, Go hoặc .NET có thể trao đổi cùng một event một cách ổn định. Compatibility check và contract test giúp phát hiện thay đổi phá vỡ wire format hoặc semantics trước khi đưa producer/consumer mới vào vận hành.
