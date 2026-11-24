# Đánh giá thay đổi serialization, header mapper và error handler

## Mục tiêu

Khi nâng cấp Spring Cloud Stream, Spring Boot, binder hoặc thư viện client Kafka, RabbitMQ và Pulsar, ứng dụng có thể vẫn khởi động thành công nhưng **không còn đọc được message cũ**, làm mất custom header hoặc chuyển một lỗi từng được retry sang trạng thái đã ACK. Đây là những thay đổi khó phát hiện bằng unit test chỉ gọi trực tiếp `Function<T, R>`.

Ba thành phần cần xem xét cùng nhau là:

- **Serialization và deserialization:** quy tắc chuyển dữ liệu Java thành bytes trên broker và ngược lại. Thay đổi converter, serializer, deserializer, Serde hoặc schema có thể làm thay đổi wire format.
- **Header mapper:** quy tắc ánh xạ giữa Spring `MessageHeaders` và Kafka record headers, AMQP properties/headers hoặc Pulsar message properties. Thay đổi mapper có thể làm mất metadata, thay đổi kiểu dữ liệu hoặc khiến routing/tracing không còn hoạt động.
- **Error handler:** quy tắc xử lý lỗi ở các giai đoạn đọc bytes, chuyển đổi dữ liệu, gọi function, publish output và ACK/commit. Thay đổi handler, retry hoặc DLQ có thể làm thay đổi bảo đảm giao nhận.

Bài học thuộc chương **Nâng cấp** của module **SPRING_CLOUD_STREAM**. Các ví dụ đặt trong bối cảnh xử lý sự kiện với `Supplier`, `Function`, `Consumer`, binding, Kafka, RabbitMQ, Pulsar và Kafka Streams; trọng tâm là **quy trình đánh giá tính tương thích trước khi triển khai**, không chỉ cách đặt một property.

Sau bài học, bạn có thể:

- Phân loại thay đổi source code, cấu hình và dependency có ảnh hưởng đến wire contract.
- Phân biệt framework message conversion với native serializer/deserializer và Kafka Streams Serde.
- Đánh giá khả năng đọc dữ liệu cũ, bao gồm event được giữ trong topic, DLT hoặc state store.
- Kiểm tra `contentType`, header mapping, Kafka `headerPatterns` và các header bắt buộc.
- Phân biệt lỗi native deserialization với lỗi conversion hoặc handler của function.
- Đánh giá retry, error channel, nack/requeue, DLQ và ACK/offset khi thay handler.
- Xây dựng test matrix cho producer cũ/mới, consumer cũ/mới và các failure window.
- Triển khai tương thích theo giai đoạn, có metric giám sát và kế hoạch rollback.

## 1. Nâng cấp thư viện không chỉ là thay version

Một phiên bản mới có thể ảnh hưởng nhiều điểm xử lý dù business function không đổi.

~~~mermaid
flowchart LR
    P[Producer object] --> S[Serializer / MessageConverter]
    S --> O[(Broker bytes + headers)]
    O --> H[Broker header mapper]
    H --> D[Deserializer / MessageConverter]
    D --> F[Function]
    F --> E{Processing result}
    E -->|Success| A[ACK / commit / output]
    E -->|Failure| R[Retry / error handler / DLT]
~~~

Ba thay đổi có thể gây lỗi độc lập hoặc kết hợp:

| Thay đổi | Triệu chứng | Rủi ro |
|---|---|---|
| JSON converter đổi cấu hình ObjectMapper | Field không parse được | Message cũ trở thành poison message |
| Chuyển từ framework conversion sang native serialization | Wire bytes hoặc payload Java type đổi | Consumer cũ/mới không tương thích |
| Kafka header mapper lọc `x-correlation-id` | Header không còn ở consumer | Mất tracing hoặc sai routing |
| Header `contentType` chuyển từ String sang kiểu khác | Converter chọn sai đường xử lý | Không deserialize được |
| Error handler bắt đầu bỏ qua lỗi deserialize | Không thấy exception ở handler | Message bị skip và không được xử lý |
| Retry count hoặc backoff thay đổi | Số lần gọi service tăng/giảm | Duplicate, tải lên dependency |
| DLQ policy thay đổi | Message lỗi không còn vào DLT cũ | Mất đường điều tra/replay |
| ACK/commit timing đổi | Message bị xác nhận sớm hoặc redelivery | Mất tác vụ hoặc side effect lặp |

Một application có thể báo health `UP` và binding `STARTED` nhưng không xử lý đúng message. Cần xác minh đầu-cuối ở **bytes, headers, status/ack và kết quả nghiệp vụ**, không chỉ khởi động thành công.

## 2. Lập baseline trước khi nâng cấp

Đừng bắt đầu bằng cách sửa YAML. Trước hết, lập bảng thực trạng của phiên bản đang chạy.

| Hạng mục | Điều cần ghi lại |
|---|---|
| Framework | Spring Boot, Spring Cloud Stream, Spring for Apache Kafka/AMQP/Pulsar |
| Binder | Kafka regular, Kafka Streams, RabbitMQ hay Pulsar; artifact/version |
| Broker/client | Kafka client/broker, RabbitMQ broker hoặc Pulsar client/broker version |
| Binding | Function name, binding name, destination, group/subscription |
| Inbound format | JSON/Avro/Protobuf/String/bytes, serializer/Serde, schema ID |
| Outbound format | Actual broker bytes, content type, headers |
| Header policy | Danh sách header quan trọng, type và rule mapping |
| Error policy | Framework retries, binder retries, nack/requeue, DLQ, producer failure |
| Delivery | ACK/offset commit, idempotency key, transaction/outbox nếu có |
| State | Kafka Streams store/changelog Serde nếu topology có trạng thái |

Ví dụ inventory:

~~~text
Binding: processOrders-in-0
Destination: orders.created
Group: inventory-service
Input bytes: UTF-8 JSON object
Key: String orderId
Required headers: x-event-id, x-correlation-id, x-schema-version
Spring contentType: application/json
Retry: 3 attempts, exponential backoff
DLQ: orders.created.dlt
Consumer side effect: inventory reservation in DB transaction
Idempotency: unique event_id in inbox table
~~~

Lưu **fixture message thực tế** từ broker thử nghiệm hoặc từ bộ contract test đã được chuẩn hóa. Fixture phải có key/value bytes, header names, header bytes/typed representation, topic/queue và schema version. Không chỉ lưu JSON được format đẹp rồi bỏ mất thông tin metadata.

### Phân biệt baseline thực tế và ý định trong config

YAML chỉ nói điều ứng dụng được cấu hình. Wire bytes và header mapping cuối cùng còn phụ thuộc binder, serializer, converter, broker và mã producer. Để biết contract thực, hãy publish một event rồi consume bằng client độc lập và kiểm tra record.

Nếu ứng dụng dùng nhiều binder hoặc nhiều producer từ các ngôn ngữ khác nhau, xây baseline riêng cho từng đường dữ liệu.

## 3. Serialization là một hợp đồng trên wire

Serialization biến object thành bytes. Deserialization biến bytes thành object. Broker không biết một byte array là Java record, JSON, Avro hay Protobuf; producer và consumer phải thống nhất cách biểu diễn.

Ví dụ event:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        long amountMinor
) {}
~~~

Payload JSON tương ứng:

~~~json
{
  "eventId": "evt-1042",
  "orderId": "O-1042",
  "amountMinor": 12500
}
~~~

Hai triển khai có thể cùng dùng class `OrderCreated` nhưng tạo bytes khác nhau. Ví dụ một bên dùng JSON, bên kia dùng serializer kiểu nhị phân hoặc Jackson có custom naming strategy. Khi đó signature Java khớp cũng không bảo đảm consumer đọc được.

Một bản nâng cấp phải trả lời cả bốn câu hỏi:

1. **Producer mới → consumer mới**: đường hoạt động mới có đúng không?
2. **Producer cũ → consumer mới**: dữ liệu lịch sử còn trong broker có đọc được không?
3. **Producer mới → consumer cũ**: trong rolling deployment, binary cũ có xử lý được event mới không?
4. **DLQ/replay cũ → consumer mới**: message lưu nhiều ngày/tháng trước vẫn có thể replay không?

Nếu có state store Kafka Streams hoặc retained topic, đánh giá thêm dữ liệu đã materialize. Đổi converter không tự migrate bytes trong state/changelog.

## 4. Framework conversion và native serialization

Trong regular Spring Cloud Stream Kafka/RabbitMQ binder, framework có thể dùng Spring Messaging `MessageConverter` để chuyển payload dựa trên `contentType`. Khi bật native serialization/decoding, client library sử dụng serializer/deserializer mà ứng dụng cấu hình.

| Cơ chế | Chuyển đổi payload | Điều quyết định wire format |
|---|---|---|
| Framework conversion | Spring `MessageConverter` | `contentType`, target type, converter/ObjectMapper |
| Native Kafka producer | `Serializer` của Kafka client | `value.serializer` và `key.serializer` |
| Native Kafka consumer | `Deserializer` của Kafka client | `value.deserializer` và `key.deserializer` |
| Kafka Streams binder | Native `Serde` mặc định; có đường framework conversion cho value khi cấu hình | Key/value Serde hoặc converter theo chế độ được chọn |
| RabbitMQ/Pulsar | Adapter/client và mapping riêng | Converter/schema/client config của binder/version |

Một cách chuyển đổi không tự bảo đảm giống cách khác. Thay đổi từ framework conversion sang native encoding có thể bỏ qua `contentType` của binding đối với marshalling và chuyển trách nhiệm định dạng sang Kafka client serializer. Tương tự, việc bật native decoding làm cho deserializer trả về kiểu Java trước khi framework gửi vào function.

### Ví dụ lựa chọn framework conversion

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.created
          group: order-normalizer
          content-type: application/json
          consumer:
            use-native-decoding: false
        normalizeOrder-out-0:
          destination: orders.normalized
          content-type: application/json
          producer:
            use-native-encoding: false
~~~

Trong ví dụ, framework chịu trách nhiệm conversion phù hợp với binding và function signature. Cần kiểm tra version thực tế vì đường converter có thể phụ thuộc container và binder.

### Ví dụ native Kafka decoding/encoding

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.created
          group: order-normalizer
          consumer:
            use-native-decoding: true
        normalizeOrder-out-0:
          destination: orders.normalized
          producer:
            use-native-encoding: true
      kafka:
        bindings:
          normalizeOrder-in-0:
            consumer:
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: org.apache.kafka.common.serialization.StringDeserializer
          normalizeOrder-out-0:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
                value.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

Ví dụ thứ hai giả định function làm việc với `String`, không phải `OrderCreated` POJO. Nếu function vẫn nhận `OrderCreated`, phải sử dụng deserializer JSON có target type phù hợp hoặc điều chỉnh function. Chỉ bật native decoding không khiến Kafka `StringDeserializer` tự tạo POJO.

Khi đổi chế độ, kiểm thử **actual Java payload type**, key type và **actual bytes** trước/sau. Không dùng mỗi tham số `content-type: application/json` làm bằng chứng rằng native serializer đang phát JSON.

## 5. contentType precedence và sự thay đổi converter

Với framework conversion, thứ tự lựa chọn content type thường là:

1. `contentType` header của message.
2. `content-type` được khai báo trên binding.
3. Default của framework, thường là `application/json`.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.created
          content-type: application/json
~~~

Nếu message nhận có header `contentType=text/plain`, framework có thể chọn đường chuyển đổi khác so với binding JSON, tùy kiểu payload và converter. Đổi header mapper có thể làm mất hoặc thay kiểu `contentType`; vì vậy một thay đổi được tưởng là "chỉ ở header" lại có thể phá vỡ JSON deserialization.

Không giả định mọi header do broker mang theo đều được map thành `MessageHeaders.CONTENT_TYPE` y nguyên. Kiểm tra cả:

- Header có tồn tại trên broker không?
- Binder có map header vào Spring Message không?
- Header có kiểu `String`, `MimeType` hay `byte[]`?
- Converter hiệu lực là converter nào?
- Target type function là POJO, `Message<POJO>`, `String` hay `byte[]`?
- Output message có tự mang contentType mới không?

Với function trả payload thuần, Spring Cloud Stream có thể tạo một message mới và không giữ header contentType từ input, để output binding áp dụng content type riêng. Với function trả `Message<?>` tự tạo, developer có thể điều khiển headers; đừng copy header vào output một cách mù quáng.

## 6. JSON schema và tính tương thích

Thay đổi serialization thường diễn ra qua model Java và ObjectMapper.

| Thay đổi JSON | Mức rủi ro | Cần kiểm tra |
|---|---|---|
| Thêm field optional | Thường thấp nếu consumer bỏ qua unknown fields | Consumer cũ có chấp nhận field lạ không |
| Đổi tên field | Cao | Alias hoặc migration; consumer cũ không còn thấy field |
| Đổi String sang number | Cao | Coercion, validation, số lớn/tràn |
| Thêm field bắt buộc | Cao | Dữ liệu cũ không có field phải dùng default hoặc version |
| Đổi enum value | Cao | Consumer cũ có fallback không |
| Đổi timestamp format/time zone | Cao | Parsing, độ chính xác, UTC |
| Thay decimal/double | Cao | Precision và rounding |
| Đổi null/tombstone semantics | Cao | Xóa dữ liệu hay lỗi schema |
| Thay cách encode binary field | Cao | Base64, raw bytes và schema |

Ví dụ chiến lược backward-compatible với field mới:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderCreatedV2(
        String eventId,
        String orderId,
        long amountMinor,
        String currency
) {}
~~~

Annotation cho phép bỏ qua field không biết; nó **không** tự giải quyết giá trị thiếu của `currency`. Nếu dữ liệu cũ thiếu field này, code cần policy có chủ đích: default hợp lệ, validation hoặc migration. Với record bất biến, kiểm tra constructor/JSON creator và ObjectMapper module tương ứng.

### Version hóa event contract

Nên quy định rõ:

- Event type và schema version.
- Trường bắt buộc, optional, nullable.
- JSON property naming, enum representation và timestamp format.
- Dữ liệu cũ còn trong retention bao lâu.
- Tương thích backward, forward hoặc full tùy luồng rollout.
- Chính sách xử lý unknown fields.
- Trường dùng làm idempotency key.

Với Avro/Protobuf/Schema Registry, kiểm tra schema ID/subject naming, compatibility policy, generated class và deserializer. Không giả định bật schema registry URL là đủ để chuyển từ JSON sang Avro.

## 7. Kafka Streams Serde và state store khi nâng cấp

Kafka Streams binder cần được đánh giá riêng. Kafka Streams xử lý record bằng `KStream`, `KTable` và các `Serde` cho key/value. Tài liệu binder hiện hành nêu native decoding là default cho value, còn key dùng native Serde. Tuy vậy binder cũng có đường framework conversion cho value khi native decoding/encoding bị tắt tường minh.

Ví dụ định nghĩa Serde theo binding:

~~~yaml
spring:
  cloud:
    function:
      definition: aggregateOrders
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: orders.created
        aggregateOrders-out-0:
          destination: orders.aggregated
      kafka:
        streams:
          bindings:
            aggregateOrders-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: orderCreatedSerde
            aggregateOrders-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: orderAggregateSerde
~~~

Các tên `orderCreatedSerde` và `orderAggregateSerde` minh họa bean Serde có kiểu mà ứng dụng đăng ký, nếu release hỗ trợ resolve bean theo cách đó; có thể cần class name/bean configuration theo version. Không giả định mọi version inference Serde theo cùng thứ tự.

Khi thay Serde, đánh giá ba nơi:

1. **Source/sink topic:** đọc record cũ và ghi output đúng contract.
2. **Repartition topic:** topology có thể mã hóa lại key/value nội bộ.
3. **State store/changelog:** dữ liệu RocksDB/changelog cũ cần được deserialize khi restore.

Một topology có thể đọc event mới thành công nhưng thất bại khi restore state store do changelog dùng schema cũ. Nếu state không tương thích, cân nhắc tạo store mới, applicationId mới, backfill hoặc migration có kiểm soát. Không đổi applicationId hoặc xóa changelog chỉ để làm lỗi biến mất mà chưa có kế hoạch replay dữ liệu.

### Error handler deserialization của Kafka Streams

Kafka Streams binder có cấu hình riêng, không giống error handler của regular Kafka binder:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            deserializationExceptionHandler: logAndFail
~~~

Theo release tương ứng, các lựa chọn có thể gồm `logAndFail`, `logAndContinue` hoặc `sendToDlq`. Cấp binding có thể override:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            aggregateOrders-in-0:
              consumer:
                deserializationExceptionHandler: sendToDlq
~~~

Một chính sách `logAndContinue` có thể bỏ qua record lỗi, trong khi `logAndFail` dừng topology. `sendToDlq` chuyển record lỗi sang topic cách ly nếu cấu hình/tài nguyên phù hợp. Đây là **thay đổi về dữ liệu được xử lý**, không đơn thuần về log level.

## 8. Header mapper là lớp chuyển đổi metadata

Header của Spring Message không nhất thiết có biểu diễn giống header của broker:

- **Kafka:** record headers lưu tên và giá trị bytes.
- **RabbitMQ:** AMQP properties (ví dụ content type) và headers table với các kiểu tương ứng.
- **Pulsar:** properties và message metadata; cách ánh xạ phụ thuộc binder/client.

Một header custom `x-correlation-id` có thể là `String` trong Spring Message nhưng thành byte[] ở Kafka. Khi đọc ngược, mapper có thể giải mã thành String hoặc giữ dạng bytes tùy mapping và version.

### Điều gì có thể thay đổi khi nâng mapper?

- Header bị loại theo pattern.
- Header được giữ nhưng chuyển kiểu String ↔ byte[].
- Header JSON type-info xuất hiện hoặc biến mất.
- Header chuẩn từ binder bị đổi tên hoặc cách ánh xạ.
- Metadata như topic, partition, key hoặc message ID được đưa vào header khác.
- Content type không còn được nhận diện.
- Message được bridge giữa Kafka/Rabbit/Pulsar mất custom header.
- Header có kích thước lớn bị hạn chế hoặc bị broker từ chối.

Đừng dùng một Spring Message in-memory làm bằng chứng header sẽ tới consumer khác. Cần đọc record thực tế bằng client độc lập.

## 9. Đánh giá Kafka headerPatterns

Regular Kafka binder có producer property `headerPatterns` để chọn Spring headers được map sang Kafka record headers.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          normalizeOrder-out-0:
            producer:
              headerPatterns: "x-correlation-id,x-event-id,x-schema-version,contentType"
~~~

Theo tài liệu binder hiện hành, pattern dùng wildcard ở đầu/cuối và dấu `!` để phủ định; matching dừng ở rule đầu tiên khớp. Các header `id` và `timestamp` của Spring không được map theo rule này.

Ví dụ rule:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          normalizeOrder-out-0:
            producer:
              headerPatterns: "!x-internal-*,x-*"
~~~

Mục đích là chỉ mang nhóm `x-*` ngoại trừ nhóm nội bộ. Nếu cần giữ `contentType` hoặc header framework bắt buộc, thêm rule phù hợp và kiểm thử; đừng tự cho rằng nó được giữ sau khi dùng allowlist.

### Lỗi nâng cấp điển hình

Bản cũ vận chuyển tất cả custom headers. Bản mới thêm allowlist nhưng quên `x-schema-version`:

~~~text
Producer Spring Message:
  x-event-id       = evt-1042
  x-correlation-id = corr-44
  x-schema-version = 3

Kafka record sau mapper mới:
  x-event-id       = bytes("evt-1042")
  x-correlation-id = bytes("corr-44")
  x-schema-version = MISSING
~~~

Consumer có thể đọc được JSON nhưng không xác định version schema, dẫn tới reject hoặc dùng parser mặc định sai. Điều cần kiểm tra không phải là bean mapper có khởi tạo, mà là **tập header và kiểu giá trị** trên wire.

### Legacy embedded headers

Spring Cloud Stream có thuộc tính `headerMode` với các giá trị như `headers`, `embeddedHeaders` hoặc `none` theo khả năng của binder. Trong môi trường Kafka hiện đại, headers native được hỗ trợ; embedded headers chủ yếu là yếu tố tương thích với các integration/phiên bản cũ.

Thay `headerMode` có thể làm thay đổi bytes của payload, vì embedded headers là một phần của binary framing chứ không chỉ metadata bên ngoài. Consumer cũ và mới cần hiểu cùng protocol. Khi native serialization được bật, `embeddedHeaders` có các giới hạn/được bỏ qua theo binder; hãy kiểm tra reference đúng version.

Không tự chuyển headerMode trong cùng thời điểm đổi JSON schema nếu không có test migration riêng cho mỗi thay đổi.

## 10. Header contract: kiểu, kích thước và độ tin cậy

Một contract header nên có bảng cụ thể:

| Header | Kiểu trên wire | Bắt buộc | Chính sách |
|---|---|---|---|
| `x-event-id` | UTF-8 String bytes | Có | Giữ nguyên qua retry/replay |
| `x-correlation-id` | UTF-8 String bytes | Có | Giữ nguyên qua service chain |
| `x-schema-version` | UTF-8 String bytes | Có | Validate version được hỗ trợ |
| `contentType` | Định dạng framework/binder tương thích | Tùy conversion mode | Phải khớp payload |
| `x-tenant-id` | UTF-8 String bytes | Tùy hệ thống | Chỉ tin sau khi xác thực nguồn |
| `x-internal-*` | Không xuất ra ngoài | Không | Loại khỏi outbound |

Không dùng tên class Java làm wire contract cho client đa ngôn ngữ nếu có thể dùng event type/schema ID độc lập. Một số JSON serializer/deserializer của Spring Kafka có thể thêm/read type headers. Khi tắt type info hoặc thay trusted packages, consumer có thể không còn xác định type đích; hãy cấu hình target type tường minh và test.

Không sử dụng header do producer không đáng tin cậy cung cấp để cấp quyền tenant hoặc vai trò. Header mapper phục vụ truyền metadata, không phải một lớp xác thực bảo mật.

## 11. Error handler có nhiều điểm can thiệp

Một event có thể lỗi ở các giai đoạn sau:

~~~mermaid
flowchart TD
    A[Broker record bytes] --> B{Native deserialize}
    B -->|Lỗi| X[Deserializer error path]
    B -->|OK| C{Framework conversion}
    C -->|Lỗi| Y[Conversion error path]
    C -->|OK| D{Function / business}
    D -->|Lỗi| Z[Handler retry / recoverer]
    D -->|OK| E{Serialize / publish output}
    E -->|Lỗi| W[Producer error path]
    E -->|OK| F[ACK / offset / confirm]
    X --> R[Policy theo binder/version]
    Y --> R
    Z --> R
    W --> R
~~~

**Không có một error handler tự động bắt mọi nhánh trên mọi binder.** Tên exception và khả năng lấy raw payload khác nhau theo đường xử lý.

| Giai đoạn | Ví dụ | Có vào function? | Cần kiểm tra |
|---|---|---|---|
| Native deserialization | Kafka `SerializationException` | Thường chưa | Deserializer/error handling container |
| Framework conversion | JSON không map được POJO | Thường chưa | Converter/error channel của binder |
| Business handler | DB timeout, validation exception | Đã vào | Retry/backoff, recovery |
| Outbound serialization | Serializer không encode được object | Có thể đã hoàn tất business side effect | Producer failure và outbox |
| Broker publish | Kafka auth/timeout; Rabbit return; Pulsar send failure | Function có thể đã chạy | Confirm/callback, retry publishing |
| ACK/commit | Process dừng sau DB commit trước ACK | Business side effect có thể đã commit | Redelivery, idempotency |

Thay một deserializer làm lỗi chuyển từ "conversion error" sang "native deserialization error". Nếu handler cũ chỉ bắt conversion exception, behavior sau nâng cấp có thể khác hoàn toàn.

## 12. Retry của framework và retry của broker

Với functional imperative consumer, Spring Cloud Stream có retry/error handling cấp message handler. Các thuộc tính chung thường dùng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-processing
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
~~~

Theo tài liệu chung, `maxAttempts` bao gồm lần xử lý đầu. Vì vậy 3 attempts không có nghĩa 3 lần retry sau lần đầu; tổng thường là 3 lần gọi handler.

Đừng mặc định các property này có cùng hiệu lực với:

- Native deserialization thất bại trước khi function nhận message.
- Kafka Streams DSL processing.
- Reactive `Function<Flux<T>, Flux<R>>`, nơi retry có thể do Reactor operators quyết định.
- Retry native của Pulsar consumer hoặc redelivery khi nack.
- Broker TTL/DLX hoặc retry topic.

Với reactive function, dùng operators như `retryWhen`, `onErrorResume` hoặc routing theo semantics của Reactor, sau đó kiểm thử lỗi và acknowledgment ở boundary binder.

### Một lỗi, nhiều tầng retry

Ví dụ service có:

- 3 lần gọi handler do framework retry.
- 5 lần redelivery của broker.
- Một HTTP client tự retry 2 lần.

Trong worst case, số lần gọi dependency có thể lớn hơn nhiều so với con số được cấu hình ở một tầng. Không nhân các con số mà thiếu test; hãy đo attempts theo từng tầng và đặt một retry budget tổng có giới hạn.

## 13. Kafka regular binder: DLQ và native deserialization

Regular Kafka binder cung cấp `enableDlq` cho consumer binding. Ví dụ cấu hình tương đối đơn giản khi dùng framework conversion:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: inventory-service
          content-type: application/json
          consumer:
            max-attempts: 3
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.dlt
~~~

Khi message đi qua đường xử lý lỗi được binder hỗ trợ và retry cạn, binder có thể publish tới DLT. Tên topic và partitions cần được provision và cấp ACL phù hợp. Đừng coi việc đặt `enableDlq=true` là bảo đảm mọi native serialization error đều được bắt và ghi vào DLT.

### Native deserializer lỗi trước khi binder gọi handler

Nếu native Kafka deserializer ném exception trong poll, lỗi có thể phát sinh trước khi một Spring Message được tạo. Spring Kafka cung cấp `ErrorHandlingDeserializer` có thể lưu thông tin lỗi vào record header để container error handler có cơ hội xử lý.

Khung cấu hình (kiểu String dùng để minh họa):

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: inventory-service
          consumer:
            use-native-decoding: true
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                spring.deserializer.value.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
~~~

Đây là **một phần** cấu hình cho cơ chế deserialize lỗi. Muốn cách ly record, cần cấu hình error handler/DLQ/producer serializer tương thích với raw data theo tài liệu đúng version. Khi bật native decoding, một số trường hợp cần chỉ rõ `dlqProducerProperties.configuration.key.serializer` và `value.serializer`; serializer DLT không được phép làm hỏng lại raw bytes.

Một record lỗi native có thể không tạo được `OrderCreated`; không được giả định function vẫn được gọi với POJO null rồi tự quyết định retry. Kiểm thử với payload xấu thực tế, xác minh offset đã tiến hay chưa và record gốc có thể recover/replay hay không.

### Khi nâng cấp error handler Kafka

Kiểm tra:

- Số lần thử và backoff cuối cùng.
- Record lỗi có còn raw key/value và headers gốc không.
- Dead-letter topic, partition mapping và required ACL.
- Serializer của DLT có tương thích raw bytes không.
- Offset có được commit sau recover thành công không.
- Handler có vô tình skip record và mất event không.
- Error handler có chạy khi producer send thất bại không.

## 14. RabbitMQ binder: reject, requeue và republish

RabbitMQ binder dùng error semantics khác Kafka. Một consumer có thể nack/reject delivery để broker requeue hoặc đưa vào dead-letter exchange (DLX) theo queue configuration; binder cũng có thể republish message lỗi vào DLQ kèm exception headers.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: inventory-service
          consumer:
            max-attempts: 3
      rabbit:
        bindings:
          processOrders-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
~~~

Các thuộc tính có nghĩa:

- `autoBindDlq`: yêu cầu binder tự khai báo DLQ và DLX liên quan, nếu topology được binder quản lý.
- `republishToDlq`: binder tự publish lại message lỗi với metadata exception bổ sung.
- `requeueRejected`: chính sách requeue delivery bị reject khi binder không republish theo đường tương ứng.
- `max-attempts`: retry cấp framework nếu đường handler tương ứng hỗ trợ.

Nếu thay `republishToDlq` từ false sang true, DLQ consumer có thể thấy header mới như exception message/stack trace và một đường publish khác. Điều này ảnh hưởng kích thước message/header, quyền publish, publisher confirm và logic phân tích DLT.

Nếu DLQ được khai báo ngoài hạ tầng, `autoBindDlq` có thể không phù hợp. Không tự động bật auto-provisioning trên production nếu hạ tầng quản lý queue/DLX bằng IaC.

### Requeue storm

Khi message luôn lỗi, `requeueRejected=true` có thể làm message lặp lại liên tục nếu không có retry delay hoặc hạn mức. Nâng cấp error handler phải kiểm tra poison message có làm queue starvation, tăng unacked count hoặc kéo dài latency của message hợp lệ không.

Thử nghiệm với broker RabbitMQ thật: đọc queue ready/unacked/DLQ và xem AMQP headers nhận được. Test Binder không tái hiện đầy đủ reject/nack/routing và republish semantics.

## 15. Pulsar binder: ack, redelivery, retry letter và DLT

Pulsar quản lý message theo subscription và các cơ chế ACK, negative acknowledgment, acknowledgment timeout, retry letter topic và dead-letter policy. Chính sách có thể khác nhau theo subscription type và Pulsar broker/client version.

Khi thay đổi error handler của Pulsar binder, kiểm tra:

1. Đường function failure có kích hoạt nack hoặc framework retry không?
2. Ack timeout có bị bật/tắt hoặc thay giá trị không?
3. Negative-ack delay và redelivery backoff có thay đổi không?
4. Có dùng retry letter topic và retry enable hay không?
5. Max redelivery count có được theo dõi bền vững qua restart không?
6. Subscription type có hỗ trợ DLQ theo version không?
7. DLT topic/subscription và quyền truy cập có còn đúng không?

Các tài liệu Pulsar gần đây cảnh báo redelivery counter của negative acknowledgment có thể chỉ lưu trong bộ nhớ, khiến giới hạn DLQ không được thực thi nhất quán sau restart/unload. Dùng retry letter topic và retry count được lưu cùng message khi cần giới hạn bền vững, rồi xác minh bằng integration test.

Không sao chép cấu hình `@PulsarListener` ack mode sang functional binder nếu binder version không expose cùng API. Tương tự, không tự giả định `enableDlq` của Kafka binder có thuộc tính tương đương trên Pulsar binder.

## 16. Error policy thay đổi có thể gây mất hoặc trùng event

Một lỗi không còn ném exception có thể làm framework xem message là xử lý thành công. Ví dụ:

~~~java
@Bean
Consumer<OrderCreated> processOrders(OrderService service) {
    return event -> {
        try {
            service.reserveInventory(event);
        }
        catch (Exception ex) {
            log.warn("Reservation failed", ex);
            // SAI: nuốt lỗi và trả về bình thường.
        }
    };
}
~~~

Nếu consumer kết thúc bình thường, binder có thể ack/commit dù reservation chưa thành công. Đây là thay đổi có thể gây **mất xử lý nghiệp vụ**.

Một cách thay thế:

~~~java
@Bean
Consumer<OrderCreated> processOrders(OrderService service) {
    return event -> service.reserveInventory(event);
}
~~~

Cho lỗi đi vào đường retry/recovery đã thiết kế. Tuy nhiên việc ném lỗi cũng có thể tạo redelivery và duplicate. Nếu database đã commit trước khi message được ack, retry có thể lặp side effect. Dùng event ID/inbox unique constraint hoặc handler idempotent.

### Không nhầm exactly-once với một error handler tốt

Retry, DLQ và offset commit không tự bảo đảm exactly-once end-to-end qua Kafka, database, HTTP và RabbitMQ/Pulsar. Khi có transaction ở broker và side effect ngoài broker, vẫn cần thiết kế consistency như outbox/inbox/idempotency.

Khi nâng cấp, test cả trường hợp process dừng **sau DB commit nhưng trước ACK**, không chỉ lỗi trước khi gọi DB.

## 17. Ma trận tương thích trước/sau nâng cấp

Một migration plan nên có bảng không bỏ sót phối hợp old/new:

| Producer | Consumer | Payload bytes | Headers | Error policy | Kết quả cần có |
|---|---|---|---|---|---|
| Cũ | Cũ | Baseline | Baseline | Baseline | Hành vi hiện tại |
| Cũ | Mới | Dữ liệu đã lưu | Header cũ | Handler mới | Backward compatibility |
| Mới | Cũ | Format mới | Header mới | Handler cũ | Rolling-deploy compatibility |
| Mới | Mới | Format mới | Header mới | Handler mới | Happy path sau cutover |
| DLT cũ | Mới | Poison/replayed record | Exception headers cũ | Recovery mới | Replay được |
| Producer mới | Consumer ngoài JVM | Format mới | Metadata bytes | Chính sách riêng | Interoperability |
| Kafka Streams state cũ | Topology mới | Changelog/state bytes cũ | Metadata nội bộ | Restore handler | Khôi phục state |

Đừng chỉ test đôi mới/mới. Khi rolling deployment, old/new thường tồn tại đồng thời. Nếu một version không thể đọc record của version kia, phải dùng topic version mới, schema migration hoặc coordinated cutover.

### Matrix các failure paths

| Test input | Điểm lỗi | Assertion |
|---|---|---|
| JSON hợp lệ | Không lỗi | Function được gọi, ACK/commit đúng, output hợp đồng |
| JSON sai cú pháp | Converter/deserializer | Function không chạy; record không mất âm thầm |
| JSON hợp lệ nhưng schema sai | Conversion/validation | Đúng retry hoặc DLT |
| Thiếu header bắt buộc | Header mapper/validation | Không xử lý sai tenant/schema |
| Header sai kiểu | Mapper/converter | Không ClassCastException lặp vô hạn |
| DB timeout tạm thời | Handler | Backoff và retry budget đúng |
| DB đã commit rồi process chết | ACK boundary | Redelivery idempotent |
| DLT publish thất bại | Recoverer producer | Không xác nhận sai việc recover |
| Output serializer lỗi | Producer | Không ghi nhận thành công giả |
| Kafka Streams restore | State/changelog | Có thể đọc state cũ hoặc migration có chủ đích |

## 18. Ví dụ test contract cho serialization

Bắt đầu với unit test của converter/serializer đã chọn. Ví dụ một fixture JSON được ObjectMapper hiện tại và mới cùng đọc:

~~~java
@Test
void readsHistoricalOrderEvent() throws Exception {
    String historicalJson = """
        {
          "eventId": "evt-1042",
          "orderId": "O-1042",
          "amountMinor": 12500
        }
        """;

    OrderCreated order = objectMapper.readValue(
            historicalJson, OrderCreated.class);

    assertThat(order.eventId()).isEqualTo("evt-1042");
    assertThat(order.amountMinor()).isEqualTo(12500L);
}
~~~

Test này phát hiện một phần vấn đề schema, nhưng chưa chứng minh MessageConverter, header mapping và binder chạy đúng. Test tiếp ở cấp binding.

### Test Binder với InputDestination và OutputDestination

~~~java
@SpringBootTest
@EnableTestBinder
class ConversionContractTest {

    @Autowired InputDestination input;
    @Autowired OutputDestination output;
    @Autowired ObjectMapper mapper;

    @Test
    void convertsJsonAndKeepsCorrelation() throws Exception {
        byte[] raw = """
            {"eventId":"evt-1042",
             "orderId":"O-1042",
             "amountMinor":12500}
            """.getBytes(StandardCharsets.UTF_8);

        input.send(
            MessageBuilder.withPayload(raw)
                .setHeader(
                    MessageHeaders.CONTENT_TYPE,
                    MimeTypeUtils.APPLICATION_JSON)
                .setHeader("x-correlation-id", "corr-44")
                .build(),
            "normalizeOrder-in-0"
        );

        Message<byte[]> result = output.receive(
                3_000, "normalizeOrder-out-0");

        assertThat(result).isNotNull();
        assertThat(mapper.readTree(result.getPayload())
                .path("orderId").asText())
                .isEqualTo("O-1042");
    }
}
~~~

Nếu function trả `Message<?>` và chủ động giữ correlation ID, bổ sung assertion header tương ứng. Nếu function trả payload thuần và framework không truyền một header theo phiên bản đang dùng, test phải phản ánh contract thực tế.

Test Binder có thể không đi qua native Kafka serializer, RabbitMQ message converter hoặc Pulsar schema như production. Vì vậy, đây là **test function/binding**, không phải wire-format test cuối cùng.

## 19. Kiểm thử bytes và headers trên broker thật

Một broker integration test cần dùng Kafka, RabbitMQ hoặc Pulsar thật trong môi trường test, có thể chạy bằng Testcontainers nếu phù hợp với hạ tầng.

Quy trình:

1. Khởi động broker với topic/queue, authentication và schema registry nếu cần.
2. Ghi fixture event bằng producer **phiên bản cũ**.
3. Khởi động consumer **phiên bản mới**.
4. Kiểm tra đúng số event đã xử lý và trạng thái DB/output.
5. Đọc bytes và headers của output bằng client độc lập.
6. Kiểm tra contentType, custom headers, key/partition/routing và schema version.
7. Gửi event mới bằng producer mới; thử đọc bằng consumer cũ.
8. Gửi JSON sai, header sai và poison event; quan sát retry/offset/DLT.
9. Kill consumer giữa DB commit và ACK để kiểm tra idempotency.
10. Kiểm tra DLT còn giữ raw bytes/header đủ để replay.

Ví dụ Java client Kafka kiểm tra header ở mức bytes:

~~~java
ConsumerRecord<String, byte[]> record = kafkaConsumer
        .poll(Duration.ofSeconds(5))
        .records("orders.normalized")
        .iterator()
        .next();

Header h = record.headers().lastHeader("x-correlation-id");

assertThat(h).isNotNull();
assertThat(new String(h.value(), StandardCharsets.UTF_8))
        .isEqualTo("corr-44");
~~~

Đây là đoạn kiểm tra minh họa; fixture producer, consumer config, subscribe/seek, polling timeout và cleanup cần được bổ sung trong integration test thật. Dùng event ID riêng cho từng test và cô lập group/offset để tránh đọc nhầm record cũ.

## 20. Kiểm thử chính sách error handler

Khi thay error handling, không chỉ assert exception được ném. Phải quan sát side effect của broker và trạng thái nghiệp vụ.

~~~text
Test: malformed JSON -> DLT

Given:
  - Consumer sử dụng phiên bản binder mới.
  - Input record có key, bytes, headers đã lưu.
  - DLT topic và ACL sẵn sàng.

When:
  - Publish malformed JSON vào input.
  - Chờ retry/recover hoàn tất.

Then:
  - Function nghiệp vụ không được gọi với dữ liệu sai.
  - Error được ghi nhận một lần theo cơ chế đo.
  - DLT có record phù hợp, giữ event ID/source metadata nếu khả dụng.
  - Input offset/ACK tiến theo policy đã thiết kế.
  - Không tạo vòng lặp retry vô hạn.
~~~

Các tình huống cần thêm:

- Retry tạm thời thành công ở attempt 2.
- Retry hết hạn mức và đi DLT.
- Lỗi không retryable được cách ly sớm.
- DLT publish bị từ chối/timeout.
- Broker bị restart giữa redelivery.
- Producer lỗi sau khi business DB đã commit.
- Schema registry không sẵn sàng.
- Interceptor hoặc header mapper ném exception trước function.

Khi chạy, đếm **handler invocation**, **broker redelivery**, **producer attempts** và **DLT records** riêng. Không mặc định một failure tương ứng một DLT record trong mọi trường hợp, đặc biệt khi có retry/recovery bất đồng bộ.

## 21. Kế hoạch rollout có thể rollback

Nếu wire format không đổi và chỉ nâng thư viện tương thích, có thể dùng rolling deployment sau khi test full matrix. Nếu thay đổi format, nên chia giai đoạn:

### Expand-and-contract

1. Nâng consumer để **đọc được cả format cũ và mới**.
2. Deploy hết consumer mới, xác minh dữ liệu lịch sử và DLT.
3. Nâng producer để phát format mới.
4. Theo dõi serialization errors, header loss, retry và backlog.
5. Chỉ bỏ đường đọc format cũ sau khi retention/replay window đã hết hoặc có migration.
6. Gỡ compatibility code qua release riêng.

Đây là chiến lược ưu tiên khi muốn tránh downtime và có thể tạo deserializer đọc nhiều schema version.

### Topic version mới

Nếu format thay đổi hoàn toàn (ví dụ JSON → Avro hoặc đổi key semantics), có thể tạo topic mới:

~~~text
orders.created.v1 -> consumers cũ
orders.created.v2 -> consumers mới
~~~

Nếu cần dual-write, chú ý duplicate, ordering và transaction boundary; có thể dùng outbox để bảo đảm event cần phát ra cả hai luồng không bị mất. Chỉ chuyển downstream sang v2 khi backfill, consumer readiness và reconciliation đạt điều kiện.

### Rollback

Rollback phải kiểm tra theo hai chiều:

- Binary cũ có đọc được event mà producer mới đã phát không?
- Handler cũ có hiểu DLT/header format mới không?

Nếu câu trả lời là "không", rollback binary đơn thuần có thể làm hệ thống tệ hơn. Hãy giữ topic version, consumer compatibility hoặc phương án khôi phục dữ liệu có kiểm soát.

## 22. Quan sát sau nâng cấp

Theo dõi theo binding, topic, consumer group và version triển khai:

| Metric/log | Vì sao cần |
|---|---|
| Deserialization/conversion error rate | Phát hiện wire format hoặc target type sai |
| Missing/invalid required header count | Phát hiện header mapper hoặc producer contract drift |
| Handler success/failure rate | Phân biệt lỗi nghiệp vụ và lỗi conversion |
| Retry attempts và backoff time | Phát hiện retry amplification |
| Consumer lag/backlog | Theo dõi khả năng xử lý và poison message |
| DLT ingress/rate/oldest age | Theo dõi message cần điều tra/replay |
| Producer send failures | Phát hiện output serializer/broker error |
| ACK/commit/redelivery | Phát hiện mất/duplicate |
| State restoration failures | Cần cho Kafka Streams binder |
| Payload size/header size | Phát hiện bytes hoặc metadata phình to |

Log nên có binding name, event ID, schema version, correlation ID, exception class và build version. Không log raw payload nhạy cảm, access token, password hoặc toàn bộ stacktrace dưới dạng header gửi rộng khắp.

Khi so sánh trước/sau, dùng cùng sample event và tải đại diện. Tránh kết luận một bản nâng cấp an toàn chỉ vì tổng error rate thấp trong vài phút đầu; message cũ có thể chỉ được gặp sau khi partition rebalance hoặc replay.

## 23. Những lỗi đánh giá phổ biến

| Nhận định sai | Điều cần làm |
|---|---|
| "Class Java không đổi nên bytes chắc chắn không đổi" | So sánh serializer và byte fixtures |
| "Đổi contentType không ảnh hưởng native serializer" | Kiểm tra đường native/framework và headers của cả hai phía |
| "Test Binder pass thì Kafka header mapper đúng" | Đọc Kafka record headers bằng client thật |
| "Header là String ở mọi broker" | Chốt kiểu wire và test round-trip |
| "Bật enableDlq là bắt mọi lỗi deserialize" | Tách native polling/deserialization và handler error |
| "Retry 3 nghĩa là ba lần retry cộng lần đầu" | Xác minh total attempts theo framework |
| "Reactive function dùng chung retry của imperative handler" | Test Reactor error operators và binder boundary |
| "Kafka Streams giống regular Kafka binder" | Kiểm tra Serde và deserializationExceptionHandler riêng |
| "DLQ record luôn giữ nguyên payload/header" | Đọc DLT bytes, exception headers và partition |
| "Producer send trả về là đã commit DB và broker" | Kiểm tra callback/confirm và outbox/idempotency |
| "Có thể rollback binary ngay sau schema change" | Test old consumer đọc event mới |
| "LogAndContinue chỉ đổi log" | Kiểm tra record bị skip và tác động nghiệp vụ |
| "Header mapper chỉ ảnh hưởng tracing" | Kiểm tra contentType, key/routing/security metadata |

## 24. Checklist trước khi phê duyệt nâng cấp

### Serialization

- [ ] Đã ghi dependency versions, binder type và function signature.
- [ ] Đã biết chế độ framework conversion hay native encoding/decoding của từng binding.
- [ ] Đã lưu golden fixtures cho key/value bytes và JSON/schema cũ.
- [ ] Đã test cũ→mới, mới→cũ, mới→mới.
- [ ] Đã kiểm tra contentType precedence và target type.
- [ ] Đã kiểm tra schema version, unknown fields, enum/timestamp/null.
- [ ] Nếu dùng Kafka Streams, đã test Serde của source/sink/repartition/state restore.

### Headers

- [ ] Đã có danh sách required/optional/internal headers.
- [ ] Đã kiểm tra Kafka headerPatterns hoặc header mapper tương ứng.
- [ ] Đã kiểm tra kiểu và bytes của header trên broker.
- [ ] Đã kiểm tra `contentType`, event ID, correlation ID, schema version.
- [ ] Đã xác minh header không được phép không rò rỉ ra ngoài.
- [ ] Đã kiểm tra legacy headerMode nếu có.

### Error handling

- [ ] Đã test native deserialization, framework conversion, handler và producer failure.
- [ ] Đã xác định retry budget, backoff và non-retryable exceptions.
- [ ] Đã kiểm tra DLT routing, partitions, ACL, raw bytes và replay.
- [ ] Đã test broker restart, consumer crash và idempotency.
- [ ] Đã xác minh ACK/offset outcome sau recover thành công/thất bại.
- [ ] Đã kiểm tra reactive/Kafka Streams/Pulsar-specific policies riêng.

### Vận hành

- [ ] Có canary hoặc environment thử nghiệm với broker thật.
- [ ] Có dashboard phân tách conversion, header và error-handler failures.
- [ ] Có rollback procedure đã thử và điều kiện dừng rollout.
- [ ] Có owner cho DLT và quy trình replay/reconciliation.
- [ ] Có bản lưu hợp đồng dữ liệu, golden fixtures và kết quả test.
- [ ] Đã chốt thời gian giữ compatibility code theo retention/replay window.

## Kết luận

Đánh giá nâng cấp Spring Cloud Stream phải đi sâu hơn việc so sánh phiên bản thư viện. **Serialization** quyết định bytes mà producer và consumer có thể hiểu; **header mapper** quyết định metadata đến được function và bên nhận theo đúng tên, kiểu và quy tắc; **error handler** quyết định message lỗi được retry, ACK, requeue, skip hay chuyển DLT. Một thay đổi ở lớp này có thể làm thay đổi hành vi của lớp khác.

Hãy lập baseline wire contract, test đầy đủ producer cũ/mới và consumer cũ/mới, bao gồm dữ liệu lịch sử, DLT, Kafka Streams state nếu có. Tách native deserialization, framework conversion, business handler và outbound publishing thành các failure paths riêng để kiểm tra. Triển khai theo expand-and-contract hoặc topic version mới khi wire contract không tương thích; giữ idempotency, quan sát lỗi và kế hoạch rollback.

**Chỉ coi nâng cấp an toàn khi integration test trên đúng binder và broker xác minh bytes, headers, error behavior và kết quả nghiệp vụ**, không chỉ khi application context khởi động được hoặc Test Binder trả output.

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): contentType, native encoding/decoding, headerMode, retry properties.
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html): imperative retries, error channel, reactive function caveats.
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html): headerPatterns, enableDlq, native deserialization, producer/consumer config.
- [Spring Cloud Stream — Kafka Binder Tips, Tricks and Recipes](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_tips.html): handling native deserializer errors and ErrorHandlingDeserializer.
- [Spring Cloud Stream — Kafka Streams Record Serialization and Deserialization](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/record-serialization-and-deserialization.html): Serde inference, native defaults and framework value conversion.
- [Spring Cloud Stream — Kafka Streams Error Handling](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/error-handling.html): logAndFail/logAndContinue/sendToDlq and per-binding control.
- [Spring Cloud Stream — RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html): autoBindDlq, republishToDlq, requeueRejected.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html): property precedence and binder integration.
- [Spring Cloud Stream — Content Type Negotiation](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream.html): contentType header/binding/default precedence and MessageConverter.

Các đường dẫn có thể mở tài liệu nhánh stable hiện hành, không nhất thiết trùng dependency dự án. Trước khi áp dụng một property hoặc dựa vào default cụ thể, luôn đối chiếu release guide và source/Javadoc đúng phiên bản Spring Cloud Stream, binder và broker/client đang triển khai.

