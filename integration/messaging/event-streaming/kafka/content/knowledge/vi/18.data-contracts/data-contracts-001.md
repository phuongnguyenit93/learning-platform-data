# Chọn String, JSON, Avro, Protobuf hoặc dữ liệu nhị phân

## Mục tiêu bài học

Kafka lưu key và value dưới dạng byte array. Producer chịu trách nhiệm chuyển dữ liệu ứng dụng thành bytes; consumer chịu trách nhiệm giải mã bytes thành kiểu dữ liệu mà ứng dụng hiểu. Vì vậy, lựa chọn format ảnh hưởng đến khả năng tương tác giữa service, kích thước payload, hiệu năng, kiểm tra schema và cách thay đổi hợp đồng dữ liệu theo thời gian.

Sau bài học, bạn có thể:

- Giải thích Kafka chỉ lưu bytes và serializer/deserializer định nghĩa cách diễn giải bytes.
- Phân biệt String, JSON, Avro, Protobuf và binary format tùy chỉnh.
- Chọn format theo yêu cầu tương thích, schema evolution, hiệu năng và hệ sinh thái.
- Hiểu vai trò của schema, Schema Registry, subject và compatibility policy.
- Viết ví dụ Java producer/consumer với String, JSON, Avro và Protobuf.
- Nhận biết những thay đổi schema có thể làm consumer cũ hoặc producer cũ lỗi.
- Phối hợp format với Kafka Connect, Kafka Streams và Spring Kafka.
- Xây dựng data contract có version, quy tắc key/value và quy trình triển khai an toàn.

## 1. Kafka lưu gì trong topic?

Kafka không lưu một đối tượng Java, JSON object hay một class Avro theo cấu trúc ngôn ngữ. Về cơ bản, record Kafka chứa key và value dạng bytes, cùng metadata như topic, partition, offset, timestamp và headers.

```text
Java application
    |
    | OrderCreated object
    v
Serializer / Converter
    |
    | byte[]
    v
Kafka record
  key bytes | value bytes | headers | timestamp
    |
    v
Deserializer / Converter
    |
    | Java object
    v
Consumer application
```

Producer và consumer phải thống nhất cách mã hóa và giải mã. Nếu producer gửi JSON UTF-8 nhưng consumer dùng Avro deserializer, consumer không thể tự hiểu payload chỉ vì cả hai cùng đọc một topic.

Kafka broker thường không cần hiểu cấu trúc business payload để lưu và chuyển tiếp record. Một số hệ thống bổ sung broker-side schema validation hoặc plugin, nhưng đó là tính năng riêng, không phải mặc định của việc ghi record. Vì vậy, data contract cần được quản lý giữa các producer, consumer và công cụ tích hợp.

### 1.1. Serializer và deserializer

- **Serializer:** chuyển key/value của ứng dụng thành bytes trước khi gửi.
- **Deserializer:** chuyển bytes nhận được thành kiểu dữ liệu ứng dụng.
- **Converter:** trong Kafka Connect, chuyển đổi giữa Connect data model và định dạng bytes trên Kafka.
- **Serde:** trong Kafka Streams, cặp serializer/deserializer được dùng khi đọc và ghi dữ liệu.

Key và value có thể dùng format khác nhau. Ví dụ key là String chứa `orderId`, còn value là Avro hoặc Protobuf. Hãy khai báo contract riêng cho key và value, không mặc định chúng phải cùng một format.

### 1.2. Format không thay thế ý nghĩa nghiệp vụ

Avro, Protobuf hay JSON chỉ mô tả cách biểu diễn dữ liệu. Chúng không tự quyết định:

- `orderId` có duy nhất hay không.
- `amount` dùng VND hay USD.
- Timestamp là UTC hay giờ địa phương.
- Event là sự kiện đã xảy ra hay lệnh yêu cầu thực hiện.
- Trường nào bắt buộc theo quy tắc nghiệp vụ.
- Consumer được phép xử lý lại event như thế nào.

Những quy tắc này cần được ghi rõ trong data contract cùng schema kỹ thuật.

## 2. So sánh nhanh các lựa chọn

| Format | Dạng biểu diễn | Điểm mạnh | Đánh đổi chính |
|---|---|---|---|
| String | Văn bản, thường UTF-8 | Đơn giản, dễ debug, tương thích rộng | Không có cấu trúc hoặc schema tự mô tả |
| JSON | Văn bản có cấu trúc | Dễ đọc, hỗ trợ rộng, thuận tiện tích hợp HTTP/web | Payload thường lớn hơn binary; schema và compatibility cần quản lý riêng |
| Avro | Binary có schema | Compact, schema evolution tốt, phổ biến trong data platform | Cần schema và tooling; payload không đọc trực tiếp bằng mắt |
| Protobuf | Binary có message schema | Compact, code generation mạnh, hiệu quả giữa nhiều ngôn ngữ | Cần quản lý field number và quy tắc tương thích |
| Binary tùy chỉnh | Bytes theo giao thức do nhóm định nghĩa | Có thể tối ưu đặc thù và kiểm soát layout | Tự xây dựng versioning, validation, tooling và khả năng tương tác |

Không có format tốt nhất cho mọi topic. Chọn dựa trên số lượng producer/consumer, vòng đời schema, ngôn ngữ triển khai, yêu cầu debug, throughput và khả năng vận hành lâu dài.

## 3. String: lựa chọn đơn giản cho dữ liệu văn bản

### 3.1. Khi nào dùng String?

String phù hợp khi payload thực sự là văn bản đơn giản, ví dụ:

- Mã định danh hoặc trạng thái ngắn.
- Log line hoặc thông điệp text.
- Command đơn giản có grammar ổn định.
- Nội dung đã có format văn bản được quản lý ở tầng khác.

Java Kafka client cung cấp `StringSerializer` và `StringDeserializer`. Chúng chuyển String thành bytes và ngược lại theo encoding UTF-8.

### 3.2. Ví dụ Java producer

```java
Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());

try (KafkaProducer<String, String> producer = new KafkaProducer<>(props)) {
    ProducerRecord<String, String> record = new ProducerRecord<>(
        "order-status",
        "ORD-101",
        "PAID"
    );
    producer.send(record, (metadata, error) -> {
        if (error != null) {
            log.error("Publish failed", error);
        } else {
            log.info("Published to {}-{} offset {}",
                metadata.topic(), metadata.partition(), metadata.offset());
        }
    });
}
```

Consumer dùng `StringDeserializer` cho cả key và value.

### 3.3. String không phải một data contract đầy đủ

Nếu value là `PAID`, consumer cần biết đó là trạng thái đơn hàng, trạng thái thanh toán hay một loại mã khác. Nếu sau này producer gửi `PAID|2026-11-20`, consumer cũ có thể không hiểu.

String vẫn có thể mang JSON hoặc một format khác dưới dạng text. Khi đó serializer ở Kafka có thể vẫn là `StringSerializer`; định dạng business payload là JSON. Cần phân biệt kiểu Java `String` với cấu trúc dữ liệu được biểu diễn bên trong chuỗi.

## 4. JSON: dễ đọc và tích hợp rộng

### 4.1. Đặc điểm

JSON biểu diễn object bằng text, gồm object, array, string, number, boolean và null. Nó được hỗ trợ rộng trong Java, JavaScript, Python, Go, REST API và nhiều công cụ giám sát.

Ví dụ payload:

```json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "occurredAt": "2026-11-20T09:30:00Z",
  "orderId": "ORD-101",
  "customerId": "CUS-42",
  "totalAmount": 250000,
  "currency": "VND"
}
```

JSON thuận tiện cho debug vì có thể đọc trực tiếp trong console hoặc log. Tuy nhiên, JSON thuần không tự cung cấp một schema contract bắt buộc. Hai bên có thể bất đồng về tên field, kiểu dữ liệu, nullability hoặc ý nghĩa đơn vị mà vẫn tạo ra JSON hợp lệ về cú pháp.

### 4.2. Ví dụ Java với Jackson

Có thể serialize object thành JSON String rồi gửi bằng `StringSerializer`:

```java
ObjectMapper mapper = new ObjectMapper();

OrderCreated event = new OrderCreated(
    "evt-1001",
    "ORD-101",
    "CUS-42",
    250000,
    "VND"
);

String json = mapper.writeValueAsString(event);
ProducerRecord<String, String> record = new ProducerRecord<>(
    "orders",
    event.orderId(),
    json
);

producer.send(record);
```

Consumer nhận String rồi parse:

```java
String json = record.value();
OrderCreated event = mapper.readValue(json, OrderCreated.class);
```

Trong ví dụ, Kafka chỉ thấy bytes của chuỗi JSON. Broker không tự kiểm tra JSON có đúng class `OrderCreated` hay không.

### 4.3. JSON Schema

Nếu cần kiểm tra cấu trúc, có thể quản lý JSON Schema cùng payload. Ví dụ schema khái quát:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["eventId", "eventType", "orderId", "currency"],
  "properties": {
    "eventId": {"type": "string"},
    "eventType": {"type": "string"},
    "orderId": {"type": "string"},
    "totalAmount": {"type": "integer", "minimum": 0},
    "currency": {"type": "string", "minLength": 3, "maxLength": 3}
  },
  "additionalProperties": false
}
```

JSON Schema có thể xác định field bắt buộc, kiểu dữ liệu, range và cấu trúc lồng nhau. Producer/consumer hoặc Schema Registry cần được cấu hình để validate và quản lý schema; chỉ đặt một file schema cạnh source code không tự động buộc mọi message trong Kafka tuân thủ schema đó.

### 4.4. Ưu và nhược điểm

Ưu điểm:

- Dễ đọc, debug và kiểm tra thủ công.
- Tương thích với nhiều ngôn ngữ và hệ thống HTTP.
- Có thể thêm field tùy chọn khá thuận tiện nếu consumer cũ bỏ qua field lạ.
- Dễ tích hợp log, data lake và công cụ phổ biến.

Đánh đổi:

- Field name và dấu câu làm payload lớn hơn binary format trong nhiều trường hợp.
- JSON number không tự phân biệt integer width, decimal precision hoặc đơn vị nghiệp vụ.
- Không có validation/compatibility nếu không dùng schema tooling.
- Consumer có thể lỗi khi field đổi kiểu, đổi tên hoặc chuyển từ nullable sang required.

## 5. Avro: binary format có schema

### 5.1. Đặc điểm

Avro là data serialization system dùng schema để mô tả record. Dữ liệu thường được mã hóa thành binary, trong khi schema mô tả tên field, kiểu dữ liệu, record, enum, array, map và union.

Ví dụ Avro schema:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.orders",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "customerId", "type": ["null", "string"], "default": null},
    {"name": "totalAmount", "type": "long"},
    {"name": "currency", "type": "string"}
  ]
}
```

Consumer cần schema writer để diễn giải bytes đã được ghi và có thể dùng reader schema của phiên bản ứng dụng hiện tại để đọc dữ liệu cũ theo quy tắc schema resolution của Avro.

### 5.2. Schema Registry

Trong hệ sinh thái Kafka, Avro thường được dùng cùng Schema Registry. Producer đăng ký hoặc lấy schema, serializer mã hóa payload theo schema và ghi metadata định danh schema vào wire format. Consumer đọc schema ID, lấy schema tương ứng từ registry/cache rồi giải mã.

Luồng khái quát:

```text
Producer object
      |
      v
Avro serializer ----> Schema Registry
      |                    |
      | bytes + schema ID  | schema/version
      v                    v
Kafka topic          Schema metadata
      |
      v
Avro deserializer ---> Schema Registry/cache
      |
      v
Consumer object
```

Schema Registry là dịch vụ quản lý schema/version và compatibility; nó không nằm trong Kafka broker và broker không cần truy cập registry để lưu bytes thông thường. Producer/consumer serializer mới là thành phần tích hợp với registry.

### 5.3. Ví dụ Java producer với Avro GenericRecord

Ví dụ sử dụng Confluent serializer và Schema Registry. Dependency và cấu hình chính xác cần khớp phiên bản client/registry của dự án.

```java
String schemaJson = """
    {
      \"type\": \"record\",
      \"name\": \"OrderCreated\",
      \"namespace\": \"com.example.orders\",
      \"fields\": [
        {\"name\": \"eventId\", \"type\": \"string\"},
        {\"name\": \"orderId\", \"type\": \"string\"},
        {\"name\": \"totalAmount\", \"type\": \"long\"}
      ]
    }
    """;

Schema schema = new Schema.Parser().parse(schemaJson);
GenericRecord value = new GenericData.Record(schema);
value.put("eventId", "evt-1001");
value.put("orderId", "ORD-101");
value.put("totalAmount", 250000L);

Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    "io.confluent.kafka.serializers.KafkaAvroSerializer");
props.put("schema.registry.url", "http://localhost:8081");

try (KafkaProducer<String, GenericRecord> producer = new KafkaProducer<>(props)) {
    producer.send(new ProducerRecord<>("orders", "ORD-101", value));
}
```

Trong ứng dụng lớn, nên đặt schema trong source/version control và dùng generated SpecificRecord nếu muốn kiểm tra kiểu mạnh lúc compile. GenericRecord hữu ích cho ví dụ hoặc pipeline cần xử lý schema động.

### 5.4. Avro object container file khác Kafka wire format

Avro có object container file format để lưu nhiều record cùng schema trong một file, thường có header và block. Khi gửi Avro qua Kafka với serializer tích hợp Schema Registry, payload dùng wire format dành cho message Kafka; không nên nhầm nó với việc gửi nguyên một Avro object container file vào value.

### 5.5. Khi nào dùng Avro?

Avro phù hợp khi:

- Có nhiều producer/consumer cần schema evolution rõ ràng.
- Hệ sinh thái data platform dùng Kafka Connect, Kafka Streams, data lake hoặc công cụ hỗ trợ Avro.
- Cần payload binary tương đối compact.
- Tổ chức có Schema Registry và quy trình quản trị schema.
- Consumer viết bằng nhiều ngôn ngữ cần contract độc lập với class Java.

## 6. Protobuf: message schema và code generation

### 6.1. Đặc điểm

Protocol Buffers (Protobuf) mô tả message bằng file `.proto`. Compiler tạo class cho ngôn ngữ mục tiêu. Mỗi field có số định danh (field number), được mã hóa theo wire type; field name không phải phần định danh chính trong binary encoding.

Ví dụ:

```protobuf
syntax = "proto3";

package com.example.orders;

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  int64 total_amount = 3;
  string currency = 4;
}
```

### 6.2. Field number là một phần của contract

Field number phải ổn định qua các phiên bản. Khi xóa field, không được tái sử dụng số của field đó cho một ý nghĩa khác. Nên đánh dấu số/tên đã xóa bằng `reserved`:

```protobuf
message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  reserved 3;
  reserved "legacy_amount";
  string currency = 4;
  int64 total_amount_minor = 5;
}
```

Đổi field number hoặc tái sử dụng số cũ có thể làm reader diễn giải bytes sai. Việc đổi tên field thường không ảnh hưởng binary wire encoding nếu giữ nguyên số, nhưng có thể ảnh hưởng generated API và JSON mapping.

### 6.3. Ví dụ Java producer

Giả sử Protobuf compiler đã tạo class `OrderCreated`:

```java
OrderCreated value = OrderCreated.newBuilder()
    .setEventId("evt-1001")
    .setOrderId("ORD-101")
    .setTotalAmount(250000L)
    .setCurrency("VND")
    .build();

Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    "io.confluent.kafka.serializers.protobuf.KafkaProtobufSerializer");
props.put("schema.registry.url", "http://localhost:8081");

try (KafkaProducer<String, OrderCreated> producer = new KafkaProducer<>(props)) {
    producer.send(new ProducerRecord<>("orders", "ORD-101", value));
}
```

Protobuf có thể được gửi bằng serializer trực tiếp theo giao thức do ứng dụng định nghĩa, nhưng khi dùng Confluent Protobuf serializer, schema metadata và compatibility được quản lý qua Schema Registry. Producer và consumer phải dùng serializer/deserializer tương ứng.

### 6.4. Khi nào dùng Protobuf?

Protobuf phù hợp khi:

- Cần code generation và kiểu dữ liệu rõ ràng ở nhiều ngôn ngữ.
- Hệ thống service-to-service đã dùng Protobuf/gRPC.
- Payload binary nhỏ và throughput là yếu tố quan trọng.
- Nhóm có kỷ luật quản lý field number, reserved field và schema evolution.

Đánh đổi là payload không đọc trực tiếp bằng mắt, cần compiler/tooling và quy trình quản lý `.proto`. Một schema hợp lệ về cú pháp vẫn có thể thay đổi không tương thích nếu field number hoặc semantics bị thay đổi sai cách.

## 7. Dữ liệu nhị phân tùy chỉnh

### 7.1. Khi nào cần binary format riêng?

Binary format tùy chỉnh có thể phù hợp khi:

- Có giao thức legacy cần giữ nguyên.
- Thiết bị hoặc hệ thống nhúng gửi payload theo layout cố định.
- Dữ liệu có yêu cầu rất đặc thù về kích thước, tốc độ hoặc encoding.
- Nhóm có khả năng duy trì parser/encoder cho nhiều phiên bản và nhiều ngôn ngữ.

Ví dụ payload có thể gồm version byte, flags, timestamp và các trường dữ liệu theo thứ tự đã định nghĩa.

### 7.2. Rủi ro khi tự định nghĩa format

Nếu không có schema registry hoặc contract rõ ràng, mỗi producer/consumer phải tự biết:

- Byte nào biểu diễn field nào.
- Byte order là big-endian hay little-endian.
- Độ dài field cố định hay variable-length.
- Cách biểu diễn null, giá trị mặc định và enum.
- Cách phân biệt version và cách đọc payload cũ.
- Cách phát hiện payload hỏng hoặc bị cắt ngắn.
- Cách thay đổi format mà không làm hỏng consumer đang chạy.

Không nên chọn binary riêng chỉ vì payload nhỏ hơn JSON trong một benchmark ngắn. Chi phí debug, tương thích, bảo trì parser và nâng cấp consumer cũng là một phần của tổng chi phí.

### 7.3. Đặt version và kiểm tra payload

Nếu buộc phải dùng format riêng, hãy đặt version marker rõ ràng và định nghĩa contract ở dạng có thể review:

```text
Byte 0      : format version
Byte 1      : flags
Byte 2..9   : event timestamp (int64, big-endian)
Byte 10..11 : order ID length (uint16)
Byte 12..N  : order ID UTF-8 bytes
```

Đây chỉ là layout minh họa. Cần giới hạn kích thước, kiểm tra length trước khi đọc, từ chối version không hỗ trợ và có test vector dùng chung cho producer/consumer ở các ngôn ngữ.

## 8. Schema evolution và compatibility

Data contract tồn tại lâu hơn một lần deploy. Producer mới có thể chạy đồng thời với consumer cũ; dữ liệu cũ vẫn còn trong Kafka khi consumer mới được triển khai. Vì vậy, schema phải được thiết kế để các phiên bản có thể cùng tồn tại.

### 8.1. Backward compatibility

Schema mới có thể đọc dữ liệu được ghi theo schema cũ. Ví dụ thêm field mới có default hợp lệ có thể cho phép reader mới đọc record cũ mà không có field đó.

### 8.2. Forward compatibility

Schema cũ có thể đọc dữ liệu được ghi theo schema mới. Điều này thường yêu cầu consumer cũ bỏ qua field mới hoặc parser xử lý unknown field an toàn.

### 8.3. Full compatibility

Full compatibility yêu cầu cả backward và forward compatibility giữa các schema theo chính sách registry. Nó hữu ích khi producer và consumer được triển khai lệch phiên bản và dữ liệu của cả hai phiên bản cùng tồn tại.

### 8.4. Transitive compatibility

Compatibility thường được kiểm tra giữa schema mới với phiên bản trước đó; chế độ transitive kiểm tra với nhiều hoặc tất cả phiên bản lịch sử trong subject theo chính sách registry. Transitive check quan trọng khi có nhiều phiên bản producer/consumer đang chạy hoặc topic lưu dữ liệu dài ngày.

Tên mode và chi tiết kiểm tra phụ thuộc Schema Registry. Hãy xác minh mode được cấu hình ở registry/subject thực tế.

### 8.5. Các thay đổi thường an toàn và không an toàn

| Thay đổi | JSON có schema | Avro | Protobuf |
|---|---|---|---|
| Thêm field tùy chọn/default | Thường tương thích nếu consumer xử lý unknown field | Thường tương thích khi reader có default phù hợp | Thường tương thích khi dùng field number mới |
| Xóa field | Consumer mới cần chịu được payload cũ; consumer cũ có thể không hiểu payload mới | Cần cân nhắc reader/writer schema và default | Nên reserve field number và name, không tái sử dụng |
| Đổi tên field | Có thể phá consumer phụ thuộc tên cũ | Thường là thay đổi schema cần kiểm tra resolution/alias | Giữ field number giúp wire tương thích, nhưng generated API/JSON name thay đổi |
| Đổi kiểu dữ liệu | Có thể phá validation và consumer | Chỉ an toàn với một số chuyển đổi được hỗ trợ | Có thể thay đổi wire type và làm sai cách đọc |
| Đổi ý nghĩa nghiệp vụ nhưng giữ tên/kiểu | Cú pháp vẫn hợp lệ nhưng semantics sai | Tương tự | Tương tự |

Compatibility tool không thể phát hiện mọi thay đổi ngữ nghĩa. Ví dụ `amount` đổi từ VND sang USD nhưng vẫn là integer có thể qua kiểm tra schema mà làm sai nghiệp vụ. Hợp đồng cần mô tả đơn vị, timezone, range, enum lifecycle và ý nghĩa field.

## 9. Schema Registry, subject và version

### 9.1. Schema Registry quản lý điều gì?

Schema Registry lưu schema, version, subject và compatibility policy. Serializer có thể đăng ký schema mới hoặc lấy schema đã tồn tại; deserializer lấy schema tương ứng để giải mã payload.

Registry giúp các producer/consumer không cần đóng cứng toàn bộ schema trong từng ứng dụng, đồng thời hỗ trợ kiểm tra compatibility trước khi publish schema mới.

### 9.2. Subject naming strategy

Với Confluent Schema Registry, serializer cần xác định subject mà schema thuộc về. Các naming strategy thường gặp:

- **TopicNameStrategy:** subject dựa trên tên topic và loại key/value, thường là `<topic>-key` hoặc `<topic>-value`.
- **RecordNameStrategy:** subject dựa trên fully qualified record/message name.
- **TopicRecordNameStrategy:** kết hợp topic và record name.

Lựa chọn strategy ảnh hưởng phạm vi schema sharing và compatibility. TopicNameStrategy tạo contract riêng theo topic; RecordNameStrategy có thể dùng chung schema record qua nhiều topic nhưng cần quản lý tương thích cẩn thận. Hãy thống nhất strategy trong toàn hệ thống và tránh để producer/consumer tự cấu hình khác nhau.

### 9.3. Registry là dependency vận hành

Khi dùng serializer tích hợp registry, producer có thể cần registry để đăng ký/lấy schema; consumer cần schema hoặc cache để giải mã. Cần:

- Cấu hình URL, authentication và TLS phù hợp.
- Cấp quyền đọc/ghi schema theo vai trò producer/consumer.
- Theo dõi availability và latency của registry.
- Cache schema ID để tránh request lặp không cần thiết.
- Có quy trình backup, migration và quản lý compatibility policy.
- Không xóa schema/version đang được dữ liệu trên Kafka tham chiếu.

Kafka có thể tiếp tục lưu bytes đã ghi dù Registry tạm thời không truy cập được, nhưng producer/consumer dùng registry có thể không serialize/deserialize được message mới hoặc message cần schema chưa có trong cache.

## 10. Chọn format theo tình huống

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Log line hoặc trạng thái ngắn | String | Đơn giản, dễ quan sát |
| Event giữa nhiều service web, cần debug trực tiếp | JSON + JSON Schema | Dễ đọc, hỗ trợ rộng, có thể quản lý contract |
| Event domain lớn, nhiều consumer và schema evolution thường xuyên | Avro + Schema Registry | Schema resolution và hệ sinh thái Kafka data platform |
| Service đa ngôn ngữ, đã dùng gRPC/Protobuf | Protobuf + Registry hoặc contract `.proto` được quản lý | Code generation và wire format compact |
| Tích hợp hệ thống legacy hoặc thiết bị | Binary format theo contract đã công bố | Giữ tương thích với giao thức hiện có |
| Kafka Connect đưa dữ liệu vào warehouse/lake | Theo converter và format mà connector đích hỗ trợ | Giảm chuyển đổi và giữ schema metadata nhất quán |
| Kafka Streams xử lý typed event | Serde tương ứng với format của topic | Đảm bảo source/sink dùng đúng encoding |

### 10.1. Cân nhắc theo các tiêu chí

Trước khi quyết định, đánh giá:

1. **Interoperability:** producer/consumer viết bằng bao nhiêu ngôn ngữ và framework?
2. **Schema evolution:** producer và consumer có deploy cùng lúc không, hay cần tương thích nhiều phiên bản?
3. **Payload size:** dữ liệu có throughput lớn, network/disk là bottleneck không?
4. **Latency/CPU:** serialization, compression và parsing tiêu tốn bao nhiêu CPU?
5. **Debuggability:** operator có cần đọc trực tiếp payload khi điều tra không?
6. **Tooling:** Kafka Connect, Streams, data lake và BI hỗ trợ format nào?
7. **Governance:** ai sở hữu schema, ai duyệt thay đổi và ai quản lý compatibility?
8. **Retention/replay:** consumer cũ có thể đọc dữ liệu được ghi bởi producer mới trong nhiều ngày/tháng không?
9. **Security:** payload có dữ liệu cá nhân, bí mật hoặc cần mã hóa field không?
10. **Total cost:** chi phí vận hành schema, registry, code generation và migration là bao nhiêu?

Không chọn binary chỉ dựa vào kích thước. Hãy benchmark bằng payload thực, kích thước record thực, compression thực và số partition dự kiến.

## 11. Key, value và headers cũng là một phần của contract

### 11.1. Key cần ổn định

Key thường quyết định partition khi producer dùng partitioner mặc định. Nếu event `OrderCreated`, `OrderPaid` và `OrderCancelled` cùng dùng `orderId` làm key, chúng thường được định tuyến đến cùng partition và giữ thứ tự theo partition.

Ví dụ:

```java
new ProducerRecord<>("orders", event.orderId(), eventValue);
```

Đổi key format hoặc cách normalize key có thể làm event cùng entity rơi vào partition khác, ảnh hưởng ordering và stateful processing. Key vì vậy cũng cần contract rõ ràng, không chỉ value.

### 11.2. Headers mang metadata phụ trợ

Kafka record headers có thể chứa metadata như:

- `content-type`: ví dụ `application/json` hoặc MIME type nội bộ.
- `event-type`: loại event.
- `schema-version`: version logic nếu hệ thống quy định.
- `traceparent`: trace context.
- `correlation-id`: định danh tương quan request.

Ví dụ:

```java
ProducerRecord<String, String> record = new ProducerRecord<>(
    "orders", "ORD-101", jsonPayload
);
record.headers().add("content-type", "application/json".getBytes(UTF_8));
record.headers().add("event-type", "OrderCreated".getBytes(UTF_8));
producer.send(record);
```

Header chỉ là metadata do producer và consumer thống nhất. Kafka không tự động dùng `content-type` để chọn deserializer cho mọi consumer. Ứng dụng vẫn cần cấu hình hoặc routing phù hợp.

### 11.3. Envelope cho event

Một envelope nhất quán có thể chứa metadata chung và payload nghiệp vụ:

```json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "eventVersion": 1,
  "occurredAt": "2026-11-20T09:30:00Z",
  "producer": "order-service",
  "correlationId": "req-abc",
  "data": {
    "orderId": "ORD-101",
    "totalAmount": 250000,
    "currency": "VND"
  }
}
```

Envelope giúp consumer xử lý metadata chung nhất quán. Không lặp lại cùng metadata ở cả header và value nếu chưa xác định nguồn nào là authoritative.

## 12. Spring Kafka, Kafka Connect và Kafka Streams

### 12.1. Spring Kafka

Spring Kafka cho phép cấu hình serializer/deserializer qua producer/consumer factory hoặc `KafkaTemplate`/listener container. Với JSON, có thể dùng `JsonSerializer` và `JsonDeserializer`; với String, dùng serializer/deserializer của Kafka client.

Ví dụ cấu hình ý tưởng:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
```

Tên class và tùy chọn trusted packages/type mapping phụ thuộc phiên bản Spring Kafka. Trong production, nên quản lý type mapping tường minh và không tin cậy package bất kỳ chỉ để giải quyết lỗi deserialization.

### 12.2. Kafka Connect converters

Kafka Connect dùng converter để chuyển đổi giữa Connect data model và bytes trên Kafka. Ví dụ:

```properties
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=io.confluent.connect.avro.AvroConverter
value.converter.schema.registry.url=http://schema-registry:8081
```

`StringConverter`, `JsonConverter`, `AvroConverter` hoặc Protobuf converter có thể được chọn tùy connector/plugin và yêu cầu schema. Converter của Connect là cấu hình riêng của connector/worker; nó cần tương thích với format mà producer và consumer khác dùng trên topic.

### 12.3. Kafka Streams Serdes

Kafka Streams cần Serde để đọc key/value từ source topic và ghi key/value ra sink topic. Ví dụ String:

```java
Consumed.with(Serdes.String(), Serdes.String());
Produced.with(Serdes.String(), Serdes.String());
```

Nếu source topic chứa Avro hoặc Protobuf, hãy dùng Serde tương ứng và cấu hình Schema Registry đúng cách. Một topology có thể dùng format khác nhau giữa source, state store và sink, nhưng mỗi ranh giới cần serializer/deserializer tương ứng.

## 13. Quản lý version và triển khai schema an toàn

Một quy trình thay đổi contract có thể gồm:

1. Xác định owner của topic và producer/consumer đang sử dụng.
2. Cập nhật schema trong source control cùng mô tả field, đơn vị, nullability và semantics.
3. Chạy compatibility check với policy của subject/registry.
4. Sinh code hoặc cập nhật model cho producer/consumer.
5. Kiểm thử producer mới với consumer cũ và consumer mới với dữ liệu cũ.
6. Deploy consumer có khả năng đọc cả dữ liệu cũ và mới trước khi producer phát schema mới, nếu rollout yêu cầu.
7. Deploy producer phát field/format mới.
8. Theo dõi deserialization error, schema lookup failure, DLQ và consumer lag.
9. Chỉ xóa field cũ sau khi mọi consumer không còn phụ thuộc và retention/replay window đã được xem xét.

Đây thường là chiến lược expand-and-contract: mở rộng schema theo hướng tương thích, chuyển dần consumer/producer, rồi mới loại bỏ phần cũ trong một release sau.

## 14. Các lỗi và anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách làm phù hợp |
|---|---|---|
| Nghĩ Kafka tự hiểu JSON/Avro | Broker chỉ lưu bytes, consumer có thể giải mã sai | Cấu hình serializer/deserializer tương thích |
| Producer gửi JSON nhưng consumer dùng Avro deserializer | Deserialization failure | Thống nhất wire format hoặc migrate topic có kế hoạch |
| Dùng String cho JSON mà không công bố schema | Consumer tự suy đoán field và type | Quản lý JSON Schema hoặc contract versioned |
| Đổi field type nhưng giữ tên | Consumer cũ có thể lỗi hoặc diễn giải sai | Compatibility check và rollout có version |
| Tái sử dụng Protobuf field number đã xóa | Reader có thể hiểu bytes sai | Reserve field number và field name |
| Xóa Avro field mà không kiểm tra default/reader schema | Consumer đọc record cũ có thể lỗi | Kiểm tra schema resolution và compatibility mode |
| Đăng ký schema mới nhưng không kiểm tra compatibility | Producer mới có thể làm consumer cũ lỗi | Bật policy phù hợp và kiểm tra trước deploy |
| Xóa schema Registry version đang được message tham chiếu | Consumer không thể lấy schema để giải mã | Giữ schema ID/version trong toàn bộ vòng đời dữ liệu |
| Cho rằng Kafka headers tự chọn deserializer | Consumer vẫn có thể dùng deserializer cố định | Viết routing/config rõ ràng hoặc dùng topic/serde riêng |
| Đổi key encoding hoặc key semantics tùy tiện | Partition mapping và ordering thay đổi | Xem key là một phần contract và version có kế hoạch |
| Dùng binary tùy chỉnh không có version marker | Khó đọc dữ liệu cũ sau nâng cấp | Định nghĩa wire version, test vector và parser tương thích |
| Chỉ benchmark serialization mà bỏ qua vận hành | Format nhanh nhưng khó debug/migrate | Đo cả CPU, bytes, tooling và chi phí schema governance |

## 15. Checklist lựa chọn và công bố data contract

Trước khi tạo topic hoặc triển khai producer, hãy xác nhận:

- Key và value có format được công bố rõ ràng.
- Charset/encoding của text được thống nhất, thường là UTF-8.
- Producer và consumer dùng serializer/deserializer tương thích.
- Schema hoặc payload contract có version và owner.
- Field có tên, kiểu, đơn vị, nullability, range và ý nghĩa nghiệp vụ rõ ràng.
- Quy tắc backward/forward/full compatibility phù hợp vòng đời deploy.
- Avro/Protobuf/JSON Schema được quản lý bằng registry hoặc quy trình version control rõ ràng.
- Subject naming strategy được thống nhất nếu dùng Schema Registry.
- Key ổn định và phù hợp yêu cầu partition ordering.
- Headers chỉ mang metadata phụ trợ và không thay thế schema.
- Kafka Connect converter và Kafka Streams Serde khớp format trên topic.
- Có test producer mới với consumer cũ và dữ liệu cũ với consumer mới.
- Có cách quan sát và xử lý deserialization error/poison message.
- Không xóa schema/version khi record còn có thể được replay.
- Đã đánh giá payload size, CPU, compression, latency và chi phí vận hành.

## 16. Câu hỏi tự kiểm tra

1. Vì sao nói Kafka lưu bytes thay vì lưu object Java hoặc JSON object?
2. Serializer và deserializer có trách nhiệm gì?
3. String chứa JSON khác JSON Schema ở điểm nào?
4. JSON thuần có bảo đảm producer và consumer thống nhất kiểu field không?
5. Avro dùng schema writer và reader schema như thế nào khi đọc dữ liệu cũ?
6. Schema Registry tham gia vào luồng serialize/deserialize ra sao?
7. Avro object container file khác wire format Avro gửi qua Kafka như thế nào?
8. Vì sao Protobuf field number không được tái sử dụng sau khi xóa field?
9. Backward, forward và full compatibility khác nhau ra sao?
10. Vì sao compatibility check không phát hiện được mọi thay đổi semantics nghiệp vụ?
11. Subject naming strategy ảnh hưởng phạm vi quản lý schema như thế nào?
12. Kafka Connect converter và Kafka Streams Serde có vai trò gì?
13. Vì sao key cũng là một phần của data contract?
14. Khi nào nên chọn String/JSON thay vì Avro/Protobuf?
15. Nếu bắt buộc dùng binary tùy chỉnh, cần công bố những thông tin nào để bảo đảm tương thích?

## Kết luận

Kafka lưu key/value dưới dạng bytes; String, JSON, Avro, Protobuf và binary tùy chỉnh là các cách mã hóa và diễn giải bytes khác nhau. String/JSON dễ quan sát và tích hợp, Avro/Protobuf phù hợp với schema rõ ràng và nhiều phiên bản producer/consumer, còn binary riêng chỉ nên dùng khi có lý do kỹ thuật và năng lực duy trì contract. Quyết định format cần đi cùng serializer/serde, schema evolution, key, headers, registry, Connect/Streams và quy trình rollout. Một data contract tốt mô tả cả cấu trúc lẫn ý nghĩa nghiệp vụ, giúp các service Java/Spring Kafka trao đổi event ổn định qua nhiều lần nâng cấp.
