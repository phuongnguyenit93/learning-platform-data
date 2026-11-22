# Converter, serializer và ranh giới của schema

Kafka chỉ lưu key và value dưới dạng byte array. Broker không hiểu một byte array đang biểu diễn JSON, Avro, Protobuf, chuỗi hay một object nghiệp vụ. Muốn các hệ thống trao đổi dữ liệu có cấu trúc, producer và consumer phải thống nhất cách mã hóa và giải mã.

Trong ứng dụng Kafka thông thường, Kafka client dùng Serializer và Deserializer. Kafka Connect có thêm một lớp riêng gọi là Converter để chuyển đổi giữa mô hình dữ liệu nội bộ của Connect và byte array được lưu trong Kafka. Hai khái niệm có liên quan nhưng không thay thế trực tiếp cho nhau.

Schema cũng có ranh giới rõ ràng. Một schema có thể chỉ tồn tại trong bộ nhớ của Kafka Connect, được nhúng trong payload JSON, hoặc được lưu trong Schema Registry và tham chiếu từ payload Avro/Protobuf/JSON Schema. Nếu schema không được truyền hoặc lưu ở một nơi mà consumer có thể truy cập, consumer chỉ nhận được dữ liệu mà không có đầy đủ thông tin kiểu.

Bài học này giải thích cách chọn converter, serializer và schema phù hợp cho source connector, sink connector và các ứng dụng Kafka khác; cách cấu hình key/value/header converter; cách quản lý schema evolution; và cách chẩn đoán lỗi do định dạng dữ liệu không tương thích.

## 1. Phân biệt Serializer, Deserializer và Converter

### 1.1. Serializer và Deserializer của Kafka client

Kafka producer cần chuyển object Java thành byte array trước khi gửi record đến broker. Interface **Serializer<T>** thực hiện công việc này. Ở phía consumer, **Deserializer<T>** chuyển byte array nhận được thành object Java.

Luồng ứng dụng thông thường:

~~~mermaid
flowchart LR
    A["Java object"] --> B["Serializer"]
    B --> C["byte[]"]
    C --> D["Kafka broker"]
    D --> E["byte[]"]
    E --> F["Deserializer"]
    F --> G["Java object"]
~~~

Ví dụ:

~~~java
props.put(
    ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName()
);
props.put(
    ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName()
);

props.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName()
);
props.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName()
);
~~~

Producer và consumer phải thống nhất wire format. Nếu producer dùng Avro serializer mà consumer dùng String deserializer, consumer sẽ nhận các byte Avro như thể đó là UTF-8 text và có thể lỗi hoặc tạo ra nội dung không có ý nghĩa.

### 1.2. Converter của Kafka Connect

Kafka Connect không đưa dữ liệu connector trực tiếp qua Kafka client Serializer/Deserializer của ứng dụng. Connector làm việc với mô hình dữ liệu nội bộ của Connect, gồm **Schema** và **Object**. Converter chuyển đổi giữa mô hình đó và byte array.

Hai method chính của interface **Converter**:

- **fromConnectData(topic, schema, value):** chuyển dữ liệu Connect thành byte array để ghi vào Kafka.
- **toConnectData(topic, value):** chuyển byte array đọc từ Kafka thành **SchemaAndValue** cho Connect.

Luồng source connector:

~~~mermaid
flowchart LR
    A["Source system"] --> B["SourceTask"]
    B --> C["SourceRecord: Schema + Object"]
    C --> D["Converter.fromConnectData"]
    D --> E["byte[] key/value"]
    E --> F["Kafka topic"]
~~~

Luồng sink connector:

~~~mermaid
flowchart LR
    A["Kafka topic"] --> B["byte[] key/value"]
    B --> C["Converter.toConnectData"]
    C --> D["SchemaAndValue"]
    D --> E["SinkRecord"]
    E --> F["SinkTask"]
    F --> G["Destination system"]
~~~

Converter là cầu nối giữa mô hình dữ liệu Connect và định dạng byte trên Kafka. Nó không phải là serializer của Kafka client được đổi tên.

### 1.3. Khác biệt quan trọng

| Khái niệm | Serializer/Deserializer | Kafka Connect Converter |
|---|---|---|
| Thành phần sử dụng | Kafka producer/consumer application | Kafka Connect runtime |
| Đầu vào khi encode | Object của ứng dụng | Connect Schema và Object |
| Đầu ra khi encode | byte array | byte array |
| Đầu vào khi decode | byte array | byte array |
| Đầu ra khi decode | Object của ứng dụng | SchemaAndValue |
| Schema | Do serializer/ứng dụng quản lý | Là một phần của Connect data model và có thể được converter biểu diễn trong wire format |
| Cấu hình | key.serializer, value.serializer, key.deserializer, value.deserializer | key.converter, value.converter, header.converter |

Một ứng dụng Java có thể dùng **KafkaAvroSerializer** và **KafkaAvroDeserializer**, trong khi Kafka Connect dùng **AvroConverter**. Cả hai có thể tích hợp với cùng một Schema Registry và cùng một định dạng dữ liệu, nhưng chúng triển khai các interface khác nhau và có trách nhiệm ở các ranh giới khác nhau.

Không thể lấy class KafkaAvroSerializer rồi gán cho value.converter; Kafka Connect yêu cầu class triển khai **org.apache.kafka.connect.storage.Converter**.

## 2. Mô hình dữ liệu nội bộ của Kafka Connect

Converter làm việc với Schema và Object, vì vậy cần hiểu Connect data model trước khi chọn định dạng.

### 2.1. Schema mô tả kiểu dữ liệu

Connect Schema có thể mô tả:

- Kiểu nguyên thủy: boolean, int8, int16, int32, int64, float32, float64, string và bytes.
- Array: danh sách các phần tử cùng schema.
- Map: khóa và giá trị có schema riêng.
- Struct: bản ghi có các field được định danh.
- Optional: field hoặc giá trị có thể vắng mặt/null.
- Default value: giá trị mặc định nếu dữ liệu không cung cấp field.
- Metadata: name, version, doc và parameters.

Ví dụ schema cho order:

~~~java
Schema orderSchema = SchemaBuilder.struct()
    .name("com.example.orders.Order")
    .version(2)
    .doc("Order event")
    .field("orderId", Schema.STRING_SCHEMA)
    .field("customerId", Schema.STRING_SCHEMA)
    .field("amount", Decimal.schema(2))
    .field("note", Schema.OPTIONAL_STRING_SCHEMA)
    .build();
~~~

Schema cho biết orderId và customerId là chuỗi bắt buộc, amount là logical decimal với scale 2, còn note có thể null.

### 2.2. Struct chứa dữ liệu có schema

Với schema kiểu Struct, dữ liệu được tạo theo schema đã khai báo:

~~~java
Struct order = new Struct(orderSchema)
    .put("orderId", "ORD-1001")
    .put("customerId", "CUS-42")
    .put("amount", new BigDecimal("125000.00"))
    .put("note", null);
~~~

Tên field và kiểu dữ liệu phải phù hợp với schema. Nếu gọi put("amount", "125000") trong khi schema yêu cầu Decimal, Connect có thể ném DataException hoặc lỗi kiểu dữ liệu.

### 2.3. Schema và value là hai phần riêng

**SchemaAndValue** gói schema và giá trị tương ứng. Một giá trị có thể tồn tại mà không có schema. Điều này rất quan trọng với JSON schema-less.

| Schema | Value | Ý nghĩa |
|---|---|---|
| String schema | "hello" | Chuỗi có kiểu |
| Struct schema | Struct order | Bản ghi có field và kiểu rõ ràng |
| null schema | Map hoặc primitive | Dữ liệu không kèm schema Connect |
| Optional schema | null | Giá trị vắng mặt nhưng schema cho phép null |
| null schema, null value | null | Tombstone hoặc null payload tùy ngữ cảnh |

Không được đánh đồng optional field với null Kafka record. Optional field là một phần của schema bên trong record; tombstone là Kafka record có key nhưng value bằng null.

### 2.4. Logical types

Một số dữ liệu có kiểu vật lý đơn giản nhưng mang ý nghĩa nghiệp vụ cụ thể:

| Logical type | Kiểu vật lý thường dùng | Ý nghĩa |
|---|---|---|
| Decimal | bytes | Số thập phân chính xác với scale |
| Date | int32 | Số ngày tính từ Unix epoch |
| Time | int32 | Millisecond kể từ nửa đêm |
| Timestamp | int64 | Millisecond kể từ Unix epoch |

Logical type giúp converter và connector giữ được ngữ nghĩa. Nếu một converter hoặc connector chỉ nhìn kiểu vật lý mà bỏ qua schema name/parameters, dữ liệu có thể bị diễn giải sai, ví dụ timestamp thành một số nguyên không có đơn vị.

## 3. Converter nằm ở đâu trong Kafka Connect pipeline?

Connect xử lý key, value và headers độc lập. Ngoài converter còn có Single Message Transform (SMT), nhưng SMT có nhiệm vụ khác.

### 3.1. Source connector pipeline

~~~mermaid
flowchart LR
    A["SourceTask.poll()"] --> B["SourceRecord"]
    B --> C["Source SMT chain"]
    C --> D["Key/Value Converter"]
    D --> E["Kafka Producer"]
    E --> F["Kafka topic"]
~~~

Source task tạo **SourceRecord** chứa key/value schema và object. Source SMT có thể đổi topic, thêm field, lọc hoặc thay đổi record. Sau đó converter serialize key và value thành byte array để Kafka Connect ghi vào topic.

### 3.2. Sink connector pipeline

~~~mermaid
flowchart LR
    A["Kafka topic"] --> B["Kafka Consumer"]
    B --> C["Key/Value Converter"]
    C --> D["SinkRecord"]
    D --> E["Sink SMT chain"]
    E --> F["SinkTask.put()"]
    F --> G["Destination"]
~~~

Sink connector đọc byte array từ Kafka, converter tạo schema/value nội bộ, sau đó SMT xử lý record và SinkTask ghi vào đích.

### 3.3. Converter không phải SMT

| Converter | SMT |
|---|---|
| Chuyển Connect data sang byte array và ngược lại | Biến đổi record sau khi đã ở Connect data model |
| Quyết định wire format | Quyết định thay đổi nội dung/route của record |
| Áp dụng ở ranh giới Kafka bytes ↔ Connect | Áp dụng trong pipeline source hoặc sink |
| Ví dụ JsonConverter, StringConverter, AvroConverter | Ví dụ ReplaceField, MaskField, ExtractField, RegexRouter |

Nếu cần đổi JSON thành Avro, converter là lựa chọn ở ranh giới serialize. Nếu cần bỏ một field, đổi tên topic hoặc mask field, SMT có thể phù hợp hơn.

Không dùng SMT để thay thế schema registry hoặc wire format. SMT thường không tự đảm bảo schema evolution giữa các hệ thống.

## 4. Key converter, value converter và header converter

Kafka Connect cho phép chọn converter riêng cho key và value. Header có một cấu hình converter riêng.

| Cấu hình | Vai trò |
|---|---|
| key.converter | Định dạng key |
| value.converter | Định dạng value |
| header.converter | Định dạng giá trị của record headers |

Ví dụ dùng key dạng chuỗi và value dạng JSON:

~~~properties
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
value.converter.schemas.enable=false
header.converter=org.apache.kafka.connect.storage.SimpleHeaderConverter
~~~

Cách này hữu ích khi key là một ID đơn giản, còn value là object có nhiều field.

### 4.1. Worker-level và connector-level configuration

Worker có thể khai báo converter mặc định cho các connector trong cluster:

~~~properties
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
value.converter.schemas.enable=true
~~~

Một connector có thể override converter riêng nếu cần:

~~~json
{
  "name": "orders-sink",
  "config": {
    "connector.class": "com.example.OrdersSinkConnector",
    "tasks.max": "2",
    "topics": "orders",
    "key.converter": "org.apache.kafka.connect.storage.StringConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter.schemas.enable": "true"
  }
}
~~~

Worker configuration là mặc định chung. Connector configuration có thể ghi đè cho connector đó. Khi điều tra một record, hãy kiểm tra cả worker config và connector config để biết converter cuối cùng được dùng.

### 4.2. Converter key và value không cần giống nhau

Một lựa chọn phổ biến:

~~~properties
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=io.confluent.connect.avro.AvroConverter
value.converter.schema.registry.url=http://schema-registry:8081
~~~

Key dùng chuỗi đơn giản, value dùng Avro với Schema Registry. Hai converter hoạt động độc lập; không bắt buộc key cũng phải Avro.

### 4.3. Header converter là một ranh giới riêng

**header.converter** chuyển đổi giá trị header giữa Connect header và byte array. Kafka header có tên và byte value; Connect header có tên, schema và object value.

Kafka 4.4 cung cấp **SimpleHeaderConverter** để chuyển header value và suy luận một số kiểu như số, boolean, array hoặc map khi đọc. **StringConverter** cũng triển khai HeaderConverter, nhưng chỉ hỗ trợ chuỗi.

Nếu header chứa một cấu trúc phức tạp hoặc cần schema rõ ràng, cần chọn header converter phù hợp. Không giả định key/value converter cũng tự động quyết định cách mã hóa header.

## 5. Các converter phổ biến

### 5.1. JsonConverter của Apache Kafka

Class:

~~~text
org.apache.kafka.connect.json.JsonConverter
~~~

**JsonConverter** thuộc Apache Kafka và có thể biểu diễn dữ liệu Connect bằng JSON.

Có hai chế độ chính:

- **schemas.enable=true:** JSON chứa cả schema và payload.
- **schemas.enable=false:** JSON chỉ chứa dữ liệu, không chứa schema Connect.

Ví dụ cấu hình schema-aware:

~~~properties
key.converter=org.apache.kafka.connect.json.JsonConverter
key.converter.schemas.enable=true
value.converter=org.apache.kafka.connect.json.JsonConverter
value.converter.schemas.enable=true
~~~

Payload có schema thường có dạng:

~~~json
{
  "schema": {
    "type": "struct",
    "name": "com.example.orders.Order",
    "fields": [
      {"type": "string", "field": "orderId"},
      {"type": "string", "field": "customerId"},
      {"type": "string", "optional": true, "field": "note"}
    ],
    "optional": false
  },
  "payload": {
    "orderId": "ORD-1001",
    "customerId": "CUS-42",
    "note": null
  }
}
~~~

Đây là JSON envelope chứa schema và payload. Nó không phải JSON object nghiệp vụ thuần.

Khi **schemas.enable=false**, payload chỉ còn dữ liệu:

~~~json
{
  "orderId": "ORD-1001",
  "customerId": "CUS-42",
  "note": null
}
~~~

Schema Connect không còn được mang trong envelope. Sink connector nhận dữ liệu có thể chỉ có Map hoặc giá trị không kèm schema. Một số connector cần schema để tạo bảng hoặc ánh xạ kiểu cột, do đó schema-less JSON có thể không đáp ứng được yêu cầu của sink.

Không nên bật/tắt **schemas.enable** tùy tiện trên topic đang có dữ liệu. Thay đổi này thay đổi wire format và có thể khiến consumer cũ không đọc được record mới.

### 5.2. StringConverter

Class:

~~~text
org.apache.kafka.connect.storage.StringConverter
~~~

**StringConverter** chỉ hỗ trợ chuỗi. Khi serialize, nó bỏ qua schema và dùng Object.toString() để tạo nội dung chuỗi. Khi deserialize, nó trả về optional string schema và chuỗi hoặc null.

Cấu hình:

~~~properties
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=org.apache.kafka.connect.storage.StringConverter
~~~

Phù hợp khi:

- Key là ID hoặc tên đơn giản.
- Value là text, log line hoặc chuỗi thuần.
- Ứng dụng đích tự chịu trách nhiệm parse nội dung.

Không dùng StringConverter cho Struct/Map với kỳ vọng nó tạo JSON có field. toString() không phải JSON serializer và không bảo đảm format ổn định giữa các class.

### 5.3. ByteArrayConverter

Class:

~~~text
org.apache.kafka.connect.converters.ByteArrayConverter
~~~

**ByteArrayConverter** là converter pass-through cho dữ liệu byte array. Nó phù hợp khi payload đã được mã hóa bởi một hệ thống khác và Connect chỉ cần chuyển tiếp byte mà không diễn giải cấu trúc.

Cấu hình:

~~~properties
key.converter=org.apache.kafka.connect.converters.ByteArrayConverter
value.converter=org.apache.kafka.connect.converters.ByteArrayConverter
~~~

Phù hợp với:

- Binary payload.
- Dữ liệu đã được serialize trước.
- Pipeline cần giữ nguyên byte representation.

Đánh đổi là Connect không hiểu schema hoặc field bên trong payload. SMT yêu cầu Struct/field schema sẽ không thể thao tác trực tiếp trên nội dung byte chưa decode thành Connect data model.

### 5.4. AvroConverter, ProtobufConverter và JsonSchemaConverter

Các converter này thường được cung cấp bởi Confluent Platform hoặc plugin tương ứng, không phải các converter mặc định có sẵn trong Apache Kafka distribution.

| Converter | Định dạng | Schema Registry |
|---|---|---|
| io.confluent.connect.avro.AvroConverter | Avro | Có |
| io.confluent.connect.protobuf.ProtobufConverter | Protobuf | Có |
| io.confluent.connect.json.JsonSchemaConverter | JSON Schema | Có |

Các converter này chuyển Connect Schema sang định dạng schema tương ứng và đăng ký hoặc tra cứu schema trong Schema Registry.

Ví dụ Avro value và String key:

~~~properties
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=io.confluent.connect.avro.AvroConverter
value.converter.schema.registry.url=http://schema-registry:8081
~~~

JSON Schema converter:

~~~properties
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=io.confluent.connect.json.JsonSchemaConverter
value.converter.schema.registry.url=http://schema-registry:8081
~~~

Protobuf converter:

~~~properties
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=io.confluent.connect.protobuf.ProtobufConverter
value.converter.schema.registry.url=http://schema-registry:8081
~~~

Worker phải có đúng converter plugin và các dependency cần thiết trên mọi worker có thể chạy connector task. Chỉ khai báo class name trong config không tự cài plugin vào Connect runtime.

### 5.5. So sánh nhanh

| Converter | Schema trong Connect | Schema trên wire | Dùng khi |
|---|---|---|---|
| JsonConverter + schemas=true | Có | Schema và payload trong JSON envelope | Cần JSON dễ quan sát và giữ schema |
| JsonConverter + schemas=false | Có thể có trong source, nhưng không truyền qua wire | Chỉ JSON data | Hệ thống chấp nhận schema-less JSON |
| StringConverter | Bỏ qua schema khi encode | Text bytes | Text thuần |
| ByteArrayConverter | Không diễn giải nội dung | Giữ byte payload | Binary pass-through |
| AvroConverter | Có | Avro data với schema reference | Contract có schema và Schema Registry |
| ProtobufConverter | Có | Protobuf data với schema reference | Contract Protobuf |
| JsonSchemaConverter | Có | JSON theo schema format và schema reference | JSON có contract/schema registry |

## 6. Schema Registry và ranh giới schema

Schema Registry lưu trữ schema version và metadata tương ứng với subject. Converter dùng registry để đăng ký hoặc tra cứu schema khi serialize/deserialize.

### 6.1. Converter không phải Schema Registry

Hai thành phần có nhiệm vụ khác nhau:

- Converter chuyển Connect data thành byte array và ngược lại.
- Schema Registry lưu trữ schema, version và compatibility policy.
- Broker lưu byte array; broker không tự hiểu hoặc kiểm tra nội dung schema trong payload.

Một Kafka topic có thể chứa byte Avro, JSON, Protobuf hoặc bất kỳ format nào. Broker không xác nhận schema có đúng với payload hoặc consumer có hiểu format hay không.

### 6.2. Wire format có thể chứa schema ID

Với Confluent Schema Registry SerDes, record thường mang schema ID trong framing của payload. Converter dùng ID đó để tìm schema trong Registry và tái tạo Connect Schema/value.

Do đó, việc consumer đọc được record phụ thuộc vào:

- Converter đúng định dạng.
- Schema Registry có thể truy cập.
- Schema ID tồn tại và được phép đọc.
- Converter/plugin có version tương thích.
- Subject/schema mapping phù hợp.

Nếu copy raw bytes sang một cluster khác nhưng không replicate Schema Registry subject/version tương ứng, consumer có thể gặp lỗi không tìm thấy schema ID.

### 6.3. Cấu hình schema registration

Ví dụ:

~~~properties
value.converter=io.confluent.connect.avro.AvroConverter
value.converter.schema.registry.url=http://schema-registry:8081
value.converter.auto.register.schemas=false
~~~

**auto.register.schemas=false** tắt việc tự đăng ký schema mới. Khi đó schema cần thiết phải được đăng ký qua quy trình quản lý schema trước.

Một số converter hỗ trợ thêm:

- **use.latest.version:** dùng schema mới nhất của subject thay vì tự suy ra schema mới từ object.
- **latest.compatibility.strict:** kiểm tra compatibility trước khi dùng schema mới nhất trong một số cấu hình.
- Subject naming strategy: xác định cách key/value ánh xạ vào subject.

Các property cụ thể tùy converter/plugin. Không áp dụng một property của AvroConverter cho JsonConverter của Apache Kafka nếu tài liệu plugin không hỗ trợ.

### 6.4. Key và value có thể có subject riêng

Schema của key và value thường được quản lý độc lập. Ví dụ topic orders có subject cho key và subject cho value. Thay đổi schema value không nhất thiết đồng nghĩa schema key phải thay đổi.

Subject naming strategy ảnh hưởng cách schema được đăng ký và chia sẻ giữa các topic. Chọn strategy phù hợp với yêu cầu chia sẻ record type và quy trình versioning của tổ chức.

## 7. Schema evolution

Schema evolution là quá trình thay đổi cấu trúc event qua thời gian mà producer và consumer vẫn tương thích trong phạm vi đã cam kết.

### 7.1. Những thay đổi thường gặp

| Thay đổi | Rủi ro | Hướng xử lý |
|---|---|---|
| Thêm field optional | Thường dễ tương thích hơn | Đặt optional/default phù hợp |
| Thêm field required | Consumer cũ có thể không hiểu hoặc producer cũ không cung cấp | Kiểm tra compatibility trước |
| Xóa field | Consumer cũ có thể vẫn cần field | Giữ field deprecated qua giai đoạn chuyển tiếp |
| Đổi tên field | Có thể được xem như xóa + thêm | Dùng migration/versioned field |
| Đổi kiểu dữ liệu | Có thể không tương thích | Dùng field mới và transform |
| Đổi logical type | Có thể đổi ngữ nghĩa dù kiểu vật lý giống nhau | Kiểm tra connector và downstream mapping |
| Đổi key schema | Có thể ảnh hưởng partitioning và ordering | Lập kế hoạch migration riêng |

### 7.2. Optional và default không giống nhau

Optional cho phép giá trị null hoặc field không hiện diện tùy format. Default cung cấp giá trị thay thế theo schema khi dữ liệu không có field, tùy converter và connector xử lý.

Ví dụ:

~~~java
Schema orderSchema = SchemaBuilder.struct()
    .field("orderId", Schema.STRING_SCHEMA)
    .field("comment", SchemaBuilder.string().optional().build())
    .field("source", SchemaBuilder.string()
        .defaultValue("web")
        .build())
    .build();
~~~

comment có thể null. source có default "web" nếu dữ liệu không cung cấp giá trị. Không nên dùng default để che giấu dữ liệu bắt buộc bị thiếu nếu nghiệp vụ cần phân biệt “không biết” và “mặc định”.

### 7.3. Compatibility policy phải được chọn theo consumer

Một schema mới có thể tương thích với consumer cũ nhưng không tương thích với dữ liệu cũ hoặc ngược lại. Schema Registry thường hỗ trợ các policy như BACKWARD, FORWARD, FULL và các biến thể transitive.

| Policy | Ý nghĩa tổng quát |
|---|---|
| BACKWARD | Consumer dùng schema mới có thể đọc dữ liệu được ghi bằng schema trước |
| FORWARD | Consumer dùng schema cũ có thể đọc dữ liệu được ghi bằng schema mới |
| FULL | Cả backward và forward |
| Transitive | Kiểm tra với nhiều version trước đó thay vì chỉ version gần nhất |

Chọn policy theo cách triển khai producer/consumer và thời gian lưu dữ liệu. Nếu consumer có thể lag nhiều ngày hoặc replay dữ liệu lịch sử, compatibility transitive có thể quan trọng hơn kiểm tra chỉ với version gần nhất.

### 7.4. Compatibility không thay thế contract test

Schema Registry có thể kiểm tra compatibility về cấu trúc, nhưng không hiểu mọi invariant nghiệp vụ. Ví dụ amount vẫn là decimal nhưng đơn vị đổi từ VND sang USD; schema có thể không thay đổi mà ý nghĩa nghiệp vụ đã đổi.

Cần contract test, kiểm thử dữ liệu mẫu và quản lý version event. Đừng coi một schema đăng ký thành công là bằng chứng event có ý nghĩa đúng.

## 8. Key converter ảnh hưởng partitioning và ordering

Kafka producer thường chọn partition dựa trên serialized key bytes khi không chỉ định partition thủ công. Vì vậy converter key không chỉ ảnh hưởng format; nó có thể ảnh hưởng cách record được phân vùng.

Ví dụ hai phiên bản converter biểu diễn cùng logical key khác byte:

- Converter cũ serialize ID 42 thành chuỗi UTF-8 "42".
- Converter mới serialize ID thành Avro hoặc một envelope khác.
- Hash của byte key có thể khác.
- Record cùng entity có thể rơi vào partition khác sau khi đổi converter.

Hệ quả:

- Ordering theo key có thể bị phá vỡ giữa các record cũ và mới.
- Consumer xử lý cùng entity có thể nhận dữ liệu ở nhiều partition.
- Compaction theo key có thể giữ các key byte khác nhau như hai key riêng biệt.
- Join giữa topic dựa trên serialized key có thể không khớp.

Trước khi đổi key converter, cần kiểm tra dữ liệu key hiện có, partitioner, compaction và consumer downstream. Đôi khi nên tạo topic mới và migration có kiểm soát thay vì thay đổi converter tại chỗ.

Value converter cũng ảnh hưởng schema và consumer compatibility, nhưng key converter có tác động trực tiếp đến partition mapping khi producer partition theo key.

## 9. Null value, tombstone và compacted topic

Với topic bật log compaction, record có key và value null có thể là tombstone để đánh dấu key đã bị xóa.

Tombstone khác với JSON string "null":

| Payload | Ý nghĩa |
|---|---|
| Kafka value = null | Tombstone/null payload |
| Bytes chứa chuỗi null | Một chuỗi JSON/text có nội dung null |
| JSON object có field value: null | Record có object, một field bên trong null |
| Optional field null trong Connect Struct | Record vẫn tồn tại, field có giá trị null |

Nếu converter biến tombstone thành chuỗi "null" hoặc object rỗng, compacted topic có thể không xóa key như mong muốn. Hãy kiểm thử rõ null behavior của converter và connector khi dùng compacted topic hoặc CDC delete events.

Với CDC, một số connector biểu diễn delete bằng tombstone hoặc bằng envelope có operation code. Đừng giả định mọi connector đều dùng cùng một quy ước.

## 10. Cấu hình thực tế cho các tình huống thường gặp

### 10.1. Key chuỗi, value JSON có schema

~~~properties
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
value.converter.schemas.enable=true
~~~

Dùng khi muốn payload JSON có schema envelope và key là chuỗi.

### 10.2. Key chuỗi, value JSON thuần

~~~properties
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
value.converter.schemas.enable=false
~~~

Dùng khi hệ thống downstream cần JSON object thuần và không cần Connect Schema từ payload. Kiểm tra connector đích có chấp nhận schema-less data hay không.

### 10.3. Key chuỗi, value Avro

~~~properties
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=io.confluent.connect.avro.AvroConverter
value.converter.schema.registry.url=http://schema-registry:8081
value.converter.auto.register.schemas=false
~~~

Dùng khi schema được quản lý tập trung và đăng ký theo release process. Đảm bảo plugin AvroConverter có trên tất cả worker.

### 10.4. Binary pass-through

~~~properties
key.converter=org.apache.kafka.connect.converters.ByteArrayConverter
value.converter=org.apache.kafka.connect.converters.ByteArrayConverter
~~~

Dùng khi dữ liệu đã được serialize và Connect chỉ cần chuyển tiếp byte. SMT thao tác trên field sẽ bị giới hạn nếu payload chưa được decode thành Connect data model.

## 11. Quản lý converter plugin trên worker

Converter bên thứ ba cần được cài đặt và phát hiện bởi Kafka Connect runtime.

Cần kiểm tra:

- JAR converter có trong plugin.path của worker hay không.
- Tất cả worker trong distributed cluster có cùng plugin và version hay không.
- Converter có dependency transitive cần thêm vào plugin directory hay không.
- Connector task được phân công sang worker khác có thể load cùng class hay không.
- Class name trong config có đúng package và tên class hay không.
- Nếu runtime hỗ trợ plugin version isolation, plugin version được khai báo đúng theo chính sách triển khai hay không.

Lỗi class not found có thể chỉ xảy ra khi task được chuyển sang worker khác nếu plugin cài không đồng nhất. Không chỉ kiểm tra worker đang giữ connector lúc đầu.

Ví dụ cấu hình plugin path:

~~~properties
plugin.path=/usr/share/java,/opt/kafka-connect-plugins
~~~

Sau khi cài plugin mới, thực hiện quy trình restart/rollout worker theo kiến trúc triển khai và kiểm tra plugin được phát hiện qua REST endpoint của Connect.

Không chép thư viện plugin vào thư mục Kafka client của ứng dụng rồi giả định Connect sẽ tự nhận. Connect worker có classloader và plugin discovery riêng.

## 12. Lỗi thường gặp khi converter hoặc schema không khớp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| DataException khi serialize | Value không khớp Connect Schema | Field type, required/optional, Struct schema |
| Unknown magic byte | Dùng converter không đúng wire format hoặc bytes không có framing mong đợi | Kiểm tra producer serializer và Connect converter |
| Không tìm thấy schema ID | Registry không có schema hoặc URL/credential sai | Schema Registry URL, schema replication và access |
| JSON parse error | Payload không phải JSON hợp lệ hoặc schema envelope không đúng chế độ | schemas.enable, raw payload |
| Sink không nhận được Struct | JSON converter chạy schema-less | Kiểm tra schemas.enable và connector yêu cầu schema |
| ClassNotFoundException converter | Plugin không có trên worker hoặc class name sai | plugin.path, plugin JAR và mọi worker |
| Value bị thành chuỗi Java object | Dùng StringConverter cho Map/Struct | Chọn Json/Avro/Protobuf converter |
| Key rơi sang partition khác | Serialized key bytes thay đổi | Key converter, partitioner, key encoding |
| Tombstone không xóa dữ liệu | Null bị chuyển thành chuỗi hoặc object | Null handling và converter |
| Decimal/date/time sai | Logical type hoặc scale/units bị bỏ qua | Schema parameters, converter và sink mapping |
| Một worker chạy, worker khác lỗi | Plugin/dependency không đồng nhất | Plugin inventory trên toàn cluster |
| Header bị mất kiểu | HeaderConverter không hỗ trợ kiểu dữ liệu | header.converter và header schema |

### 12.1. Quy trình chẩn đoán

1. Xác định record đến từ source connector hay topic được sink connector đọc.
2. Xác định converter hiệu lực cho key, value và header.
3. Đọc byte payload bằng consumer phù hợp hoặc công cụ kiểm tra raw bytes.
4. Xác định producer ban đầu dùng Serializer nào và wire format gì.
5. Kiểm tra schema envelope hoặc schema ID trong payload.
6. Nếu dùng Schema Registry, kiểm tra URL, subject, schema ID, authentication và compatibility.
7. Kiểm tra schema/value nội bộ có đúng kiểu mà connector yêu cầu không.
8. Kiểm tra converter plugin có trên tất cả worker.
9. Kiểm thử với một record mẫu trước khi chạy lại backlog lớn.

Đừng sửa lỗi bằng cách đổi converter ngẫu nhiên trên production. Thay đổi converter có thể làm toàn bộ record mới có wire format khác với dữ liệu đã tồn tại.

## 13. Lab: kiểm tra JSON converter và schema boundary

Mục tiêu: quan sát sự khác nhau giữa JSON có schema envelope, JSON thuần và StringConverter.

### Bước 1: Cấu hình worker

Ví dụ worker properties:

~~~properties
bootstrap.servers=localhost:9092
group.id=connect-lab

key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
value.converter.schemas.enable=true
header.converter=org.apache.kafka.connect.storage.SimpleHeaderConverter

config.storage.topic=connect-lab-configs
offset.storage.topic=connect-lab-offsets
status.storage.topic=connect-lab-status

plugin.path=/usr/share/java,/opt/kafka-connect-plugins
~~~

Dùng topic internal riêng cho lab. Trong production, các internal topic phải được cấu hình replication, partition và ACL phù hợp.

### Bước 2: Tạo connector source có dữ liệu dạng Connect Struct

Dùng một source connector tạo record có schema và Struct, ví dụ connector mẫu hoặc connector JDBC/CDC trong môi trường lab. Xác nhận record được publish vào topic với key/value converter đã cấu hình.

Nếu dùng FileStreamSourceConnector, cần nhớ nó phát nội dung dòng dưới dạng String; nó không tự tạo một Struct từ JSON text. Để thử JSON schema envelope, hãy dùng source connector phát dữ liệu có schema hoặc một connector test có khả năng tạo Struct.

### Bước 3: Quan sát JSON có schema

Giữ value.converter.schemas.enable=true. Đọc record và kiểm tra payload có hai phần schema và payload.

Xác nhận schema mô tả đúng field, type, optional và logical type.

### Bước 4: Thử JSON schema-less

Trong môi trường lab riêng, đặt:

~~~properties
value.converter.schemas.enable=false
~~~

Khởi động lại worker hoặc cập nhật cấu hình tương ứng theo cách triển khai. Quan sát payload chỉ còn JSON data. Kiểm tra sink connector có tiếp tục hoạt động nếu nó cần schema hay không.

Không đổi cấu hình này trên topic production có consumer phụ thuộc wire format cũ.

### Bước 5: Thử StringConverter

Đổi value converter sang StringConverter và dùng source record có value dạng String. Xác nhận byte payload là text. Thử gửi Struct và quan sát vì sao toString() không tạo JSON contract.

### Bước 6: Thử Schema Registry converter

Nếu lab có Confluent Schema Registry và AvroConverter plugin:

~~~properties
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=io.confluent.connect.avro.AvroConverter
value.converter.schema.registry.url=http://localhost:8081
~~~

Tạo record có schema. Kiểm tra schema được đăng ký, subject/version và schema ID. Thử sink converter đọc record đó để xác nhận schema được khôi phục.

### Bước 7: Kiểm thử schema evolution

Thêm một field optional vào schema mới. Kiểm tra compatibility policy và consumer cũ. Sau đó thử đổi kiểu field hoặc xóa field trong lab để quan sát Registry từ chối hay chấp nhận theo policy.

### Bước 8: Ghi kết quả

Ghi lại:

- Converter class cho key/value/header.
- Worker hay connector đang override config.
- Wire format thực tế.
- Schema có nằm trong payload hay Registry.
- Schema subject/version.
- Kết quả sink connector.
- Hành vi với null/tombstone.

## 14. Checklist trước production

- [ ] Đã phân biệt Kafka client Serializer/Deserializer với Kafka Connect Converter.
- [ ] Đã xác định source và sink pipeline.
- [ ] Đã chọn riêng key.converter và value.converter.
- [ ] Đã xác định header.converter khi record có headers quan trọng.
- [ ] Đã kiểm tra worker-level và connector-level override.
- [ ] Đã chọn schema-aware hay schema-less JSON có chủ đích.
- [ ] Đã xác định nơi schema được lưu: envelope, Schema Registry hay không có schema.
- [ ] Đã kiểm tra converter hỗ trợ logical types, optional fields và default values.
- [ ] Avro/Protobuf/JSON Schema converter plugin có trên mọi worker.
- [ ] Schema Registry URL, authentication, subject strategy và compatibility policy đã được xác minh.
- [ ] Key serialization không làm thay đổi partition mapping ngoài kế hoạch.
- [ ] Tombstone/null payload được giữ đúng semantics.
- [ ] Sink connector được kiểm thử với đúng Connect Schema/value.
- [ ] Có test contract cho producer, Connect và consumer downstream.
- [ ] Có quy trình rollout khi thay đổi wire format hoặc schema.
- [ ] Có log/metric để nhận diện lỗi converter, schema và plugin.

## 15. Tài liệu tham khảo

- [Apache Kafka 4.4 – Converter API](https://kafka.apache.org/44/javadoc/org/apache/kafka/connect/storage/Converter.html)
- [Apache Kafka 4.4 – StringConverter API](https://kafka.apache.org/44/javadoc/org/apache/kafka/connect/storage/StringConverter.html)
- [Apache Kafka 4.4 – HeaderConverter API](https://kafka.apache.org/44/javadoc/org/apache/kafka/connect/storage/HeaderConverter.html)
- [Apache Kafka 4.4 – Connect Schema API](https://kafka.apache.org/44/javadoc/org/apache/kafka/connect/data/Schema.html)
- [Apache Kafka 4.4 – Kafka Connect Configs](https://kafka.apache.org/44/configuration/kafka-connect-configs/)
- [Apache Kafka 4.4 – Kafka Connect User Guide](https://kafka.apache.org/44/kafka-connect/user-guide/)
- [Apache Kafka 4.4 – SourceRecord API](https://kafka.apache.org/44/javadoc/org/apache/kafka/connect/source/SourceRecord.html)
- [Apache Kafka 4.4 – SinkRecord API](https://kafka.apache.org/44/javadoc/org/apache/kafka/connect/sink/SinkRecord.html)
- [Confluent – Integrate Schemas from Kafka Connect](https://docs.confluent.io/platform/current/schema-registry/connect.html)
- [Confluent – Kafka Connect User Guide: Converters](https://docs.confluent.io/platform/current/connect/userguide.html)

Converter quyết định cách dữ liệu Connect được biểu diễn thành byte array; serializer của ứng dụng quyết định cách object ứng dụng được mã hóa. Consumer chỉ có thể diễn giải schema khi schema được truyền cùng dữ liệu, tra cứu qua registry hoặc chia sẻ qua một contract ngoài băng thông được quản lý thống nhất. Hãy chọn converter theo contract dữ liệu, kiểm tra key/value/header riêng và kiểm thử schema evolution trước khi thay đổi định dạng trên topic đang có consumer production.
