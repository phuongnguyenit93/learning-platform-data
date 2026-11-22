# Hợp đồng dữ liệu giữa producer và consumer

Trong Kafka, producer và consumer thường được triển khai, mở rộng và phát hành độc lập. Hai phía vẫn phải hiểu cùng một cấu trúc event để trao đổi dữ liệu an toàn. **Hợp đồng dữ liệu (data contract)** xác định payload có những trường nào, kiểu dữ liệu ra sao, trường nào bắt buộc, ý nghĩa nghiệp vụ của từng trường và cách cấu trúc đó được thay đổi theo thời gian.

Hợp đồng không chỉ là một Java DTO. Hợp đồng thực sự là định dạng dữ liệu được serialize và ghi vào Kafka, cùng quy tắc tương thích mà các phiên bản producer/consumer phải tuân thủ. Nếu producer đổi tên trường, đổi kiểu hoặc thay đổi ý nghĩa dữ liệu mà consumer chưa hiểu, ứng dụng có thể deserialize lỗi hoặc xử lý sai nghiệp vụ dù Kafka vẫn nhận record bình thường.

## 1. Vì sao producer và consumer cần chung một hợp đồng?

Kafka lưu key và value dưới dạng byte. Producer quyết định cách chuyển object thành byte; consumer quyết định cách đọc byte thành object. Kafka broker không hiểu ý nghĩa của các trường bên trong payload.

```text
Producer service                         Consumer service
      |                                         |
      v                                         v
OrderCreatedEvent                         OrderCreatedEvent
      |                                         ^
      v                                         |
Serializer ---- bytes ----> Kafka ---- bytes ---- Deserializer
                 topic: orders.created
```

Ví dụ producer gửi event:

```json
{
  "eventId": "evt-1001",
  "orderId": "ord-42",
  "total": 125000,
  "currency": "VND"
}
```

Consumer có thể cần `eventId` để deduplicate, `orderId` để cập nhật projection và `total` để tính doanh thu. Nếu producer đổi `total` từ số nguyên sang chuỗi mà không có thỏa thuận, consumer có thể lỗi khi parse hoặc vô tình diễn giải sai giá trị.

Hợp đồng dữ liệu giúp các nhóm thống nhất trước về:

- Tên trường, kiểu dữ liệu, đơn vị đo và ý nghĩa nghiệp vụ.
- Trường bắt buộc, trường tùy chọn và giá trị mặc định.
- Quy tắc enum, timestamp, tiền tệ, identifier và null.
- Cách thêm, bỏ hoặc thay đổi trường.
- Phiên bản schema và chính sách tương thích.
- Cách xử lý record cũ khi replay từ Kafka.

## 2. Phân biệt schema, event và Java DTO

Ba khái niệm liên quan nhưng không đồng nhất:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Event | Sự kiện nghiệp vụ đã xảy ra | `OrderCreated` |
| Schema | Định nghĩa cấu trúc và kiểu dữ liệu của event | Avro, Protobuf, JSON Schema |
| Java DTO | Kiểu Java dùng trong một ứng dụng để biểu diễn event | `OrderCreatedEvent` |

Một event có thể được biểu diễn bằng Java record ở producer và một class khác ở consumer. Hai class không cần giống hệt nhau nếu cả hai tuân thủ cùng wire contract.

Không nên xem tên class Java hoặc package Java là hợp đồng dùng chung giữa các service. Việc serialize tên class vào Kafka header có thể tiện cho ứng dụng Spring cùng hệ sinh thái, nhưng tạo coupling khi consumer dùng ngôn ngữ khác hoặc package được đổi tên. Hãy phân biệt metadata type của framework với schema nghiệp vụ ổn định.

## 3. Thiết kế event contract

Một event tốt cần mô tả sự kiện đã xảy ra, không chỉ phản ánh cấu trúc database hiện tại. Ví dụ:

```json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "eventVersion": 1,
  "occurredAt": "2026-11-17T09:30:00Z",
  "producer": "order-service",
  "data": {
    "orderId": "ord-42",
    "customerId": "cus-18",
    "totalMinor": 12500000,
    "currency": "VND"
  }
}
```

Envelope minh họa tách metadata chung khỏi dữ liệu nghiệp vụ:

| Trường | Mục đích |
| --- | --- |
| `eventId` | Định danh duy nhất để trace và deduplicate |
| `eventType` | Tên loại sự kiện |
| `eventVersion` | Phiên bản hợp đồng nếu hệ thống dùng version trong payload |
| `occurredAt` | Thời điểm nghiệp vụ xảy ra, nên dùng UTC và định dạng thống nhất |
| `producer` | Service phát sinh event |
| `data` | Payload nghiệp vụ của event |

`totalMinor` minh họa cách lưu tiền theo đơn vị nhỏ nhất để tránh sai số dấu phẩy động; cần quy ước rõ đơn vị theo currency. Với VND, có thể quy định đơn vị là đồng và đặt tên trường dễ hiểu hơn như `totalAmount`. Điều quan trọng là hợp đồng phải nói rõ đơn vị, scale và phạm vi giá trị.

Không phải event nào cũng cần envelope tự thiết kế. Có thể dùng Kafka headers cho correlation ID, trace context hoặc metadata vận chuyển. Hãy chọn một quy ước nhất quán và tránh lặp metadata ở cả payload lẫn header nếu không có lý do.

## 4. Quy tắc thiết kế trường dữ liệu

Khi định nghĩa schema, cần quy định rõ từng thuộc tính:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| Name | Tên trường có ổn định và có ý nghĩa không? |
| Type | String, integer, decimal, boolean, timestamp, object hay array? |
| Required | Consumer có thể xử lý khi trường vắng mặt không? |
| Nullable | Trường có thể hiện diện với giá trị `null` không? |
| Default | Khi record cũ không có trường, giá trị thay thế là gì? |
| Semantics | Giá trị biểu thị gì, đơn vị gì, timezone nào? |
| Constraints | Có giới hạn độ dài, miền giá trị hoặc format không? |

`optional` và `nullable` không phải lúc nào cũng giống nhau. Một trường có thể không xuất hiện trong payload, hoặc xuất hiện nhưng mang `null`; schema format có thể xử lý hai trường hợp này khác nhau. Hãy ghi rõ hành vi mong đợi.

Ví dụ một trường `discount`:

- Không có `discount`: producer cũ chưa cung cấp thông tin giảm giá.
- `discount: null`: producer chủ động biểu thị không xác định hoặc không áp dụng, tùy contract.
- `discount: 0`: có thông tin và giá trị giảm giá bằng 0.

Không tự diễn giải ba trạng thái trên là tương đương.

## 5. Schema compatibility là gì?

Schema compatibility mô tả liệu một phiên bản schema mới có thể đọc hoặc được đọc bởi dữ liệu được tạo từ phiên bản khác hay không. Khả năng tương thích cần được xem xét theo cả hai hướng vì producer và consumer có thể triển khai lệch thời điểm.

Ba hướng phổ biến:

| Chế độ | Câu hỏi | Ý nghĩa triển khai |
| --- | --- | --- |
| Backward compatibility | Consumer/schema mới có đọc được dữ liệu do schema cũ ghi không? | Có thể nâng consumer trước, sau đó mới nâng producer |
| Forward compatibility | Consumer/schema cũ có đọc được dữ liệu do schema mới ghi không? | Có thể nâng producer trước trong phạm vi thay đổi tương thích |
| Full compatibility | Hai phiên bản đọc được dữ liệu của nhau theo cả hai hướng không? | Hỗ trợ rollout lệch phiên bản linh hoạt hơn |

Các thuật ngữ này thường được dùng trong Schema Registry. Quy tắc kiểm tra cụ thể phụ thuộc format schema và cấu hình registry; không nên suy ra chỉ từ tên mode rằng mọi thay đổi đều an toàn.

### Compatibility và transitive compatibility

Compatibility thông thường có thể chỉ kiểm tra schema mới với phiên bản gần nhất. Transitive compatibility kiểm tra với nhiều hoặc toàn bộ phiên bản trước đó theo chính sách registry.

Điều này quan trọng khi Kafka lưu dữ liệu lâu và consumer có thể replay record cũ. Một schema mới tương thích với phiên bản liền trước chưa chắc đọc được dữ liệu từ nhiều năm trước nếu các thay đổi trước đó không được kiểm tra xuyên suốt.

## 6. Những thay đổi thường an toàn và không an toàn

Tính tương thích phụ thuộc schema format, default, nullability và cách consumer được triển khai. Bảng dưới đây là hướng dẫn thiết kế chung, không thay thế compatibility checker của format đang dùng.

| Thay đổi | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Thêm trường optional có default phù hợp | Thường dễ tương thích hơn | Xác định default và ý nghĩa khi record cũ thiếu trường |
| Thêm trường bắt buộc không có default | Consumer mới có thể không đọc được record cũ | Tránh; triển khai theo nhiều bước hoặc cung cấp default |
| Bỏ trường đang được consumer dùng | Consumer cũ có thể lỗi khi field biến mất | Ngừng sử dụng trước, rồi mới loại bỏ ở phiên bản sau |
| Đổi tên trường | Consumer theo tên cũ không tìm thấy field | Thêm field mới, migrate consumer, rồi mới bỏ field cũ |
| Đổi kiểu dữ liệu | Có thể không deserialize hoặc đổi nghĩa | Dùng field mới và chuyển đổi có kiểm soát |
| Thêm enum symbol | Consumer cũ có thể gặp giá trị chưa biết | Thiết kế nhánh `UNKNOWN`/fallback hoặc kiểm soát thứ tự rollout |
| Đổi đơn vị hoặc ý nghĩa trường nhưng giữ tên/kiểu | Deserialize vẫn thành công nhưng nghiệp vụ sai | Xem là thay đổi contract breaking; dùng field/version mới |
| Đổi cấu trúc nested object | Có thể phá reader cũ | Kiểm tra schema resolution và contract test |

Một thay đổi có thể tương thích về mặt cú pháp nhưng phá vỡ semantics. Ví dụ `amount` trước đây là đồng, sau đó producer gửi số tiền theo xu nhưng vẫn dùng integer. Consumer deserialize thành công nhưng tính toán sai. Contract cần quản lý cả ý nghĩa, không chỉ kiểu dữ liệu.

## 7. Ví dụ tiến hóa JSON contract

Giả sử phiên bản 1:

```json
{
  "eventId": "evt-1001",
  "orderId": "ord-42",
  "total": 125000
}
```

Phiên bản 2 muốn thêm `currency`. Một cách triển khai an toàn hơn là coi trường mới là optional hoặc có default rõ ràng trong schema/consumer:

```json
{
  "eventId": "evt-1001",
  "orderId": "ord-42",
  "total": 125000,
  "currency": "VND"
}
```

Consumer mới cần xử lý record cũ không có `currency`. Nếu producer mới gửi trường này, consumer cũ cũng cần bỏ qua field không biết hoặc schema validation phải cho phép thêm property. Với JSON Schema, các keyword như `required`, `properties` và `additionalProperties` ảnh hưởng trực tiếp đến compatibility; không mặc định mọi JSON consumer đều bỏ qua field lạ.

Khi đổi `total` sang kiểu decimal hoặc thay đơn vị, không nên âm thầm thay kiểu/ý nghĩa tại cùng field. Có thể thêm `totalAmount` cùng `currency`, triển khai consumer đọc cả hai dạng, chuyển producer sang field mới, rồi ngừng field cũ sau khi hết thời gian hỗ trợ và replay window.

## 8. Avro và schema evolution

Avro lưu schema cùng dữ liệu theo cơ chế writer schema và reader schema. Khi đọc, Avro thực hiện schema resolution giữa schema lúc ghi và schema consumer mong đợi.

Ví dụ Avro record phiên bản mới thêm field `currency` có default:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "eventId", "type": "string" },
    { "name": "orderId", "type": "string" },
    { "name": "total", "type": "long" },
    { "name": "currency", "type": "string", "default": "VND" }
  ]
}
```

Default của field mới giúp reader schema mới đọc record cũ không có field đó. Nếu thêm field mới mà không có default, reader mới có thể không đọc được record cũ vì không có giá trị để điền.

Một số nguyên tắc Avro quan trọng:

- Thêm field mới nên có default nếu cần đọc dữ liệu cũ.
- Xóa field có thể tương thích theo hướng reader mới bỏ qua field writer cũ.
- Đổi tên field cần cân nhắc `aliases` để schema resolution nhận diện tên cũ.
- Đổi kiểu chỉ an toàn trong các trường hợp promotion được Avro hỗ trợ.
- Thêm enum symbol có thể khiến reader cũ không xử lý được symbol mới; cân nhắc enum default và compatibility mode.

Hãy dùng Avro schema compatibility checker để xác minh chính sách thực tế thay vì chỉ dựa vào bảng hướng dẫn.

## 9. Protobuf và quy tắc field number

Protocol Buffers sử dụng field number làm định danh trên wire format. Tên field có thể đổi mà wire representation vẫn giữ nếu field number và wire type không đổi, nhưng đổi hoặc tái sử dụng field number đã xóa có thể làm dữ liệu bị diễn giải sai.

Ví dụ:

```protobuf
syntax = "proto3";

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  int64 total = 3;
  string currency = 4;
}
```

Nếu bỏ `total = 3`, hãy reserve cả field number và tên nếu phù hợp:

```protobuf
message OrderCreated {
  reserved 3;
  reserved "total";

  string event_id = 1;
  string order_id = 2;
  string currency = 4;
}
```

Không bao giờ tái sử dụng field number đã phát hành. Khi thay đổi kiểu field, cần kiểm tra wire type và quy tắc tương thích Protobuf; hai kiểu cùng biểu diễn wire type không đồng nghĩa cùng ý nghĩa hoặc cùng phạm vi giá trị. Các thay đổi như `string` sang `bytes`, thay đổi cardinality hoặc chuyển scalar sang message cần đánh giá riêng.

## 10. JSON, Avro hay Protobuf?

Không có format duy nhất phù hợp mọi hệ thống:

| Tiêu chí | JSON | Avro | Protobuf |
| --- | --- | --- | --- |
| Dễ đọc thủ công | Cao | Thấp hơn nếu payload binary | Thấp hơn nếu payload binary |
| Schema rõ ràng | JSON Schema cần được quản lý riêng | Có schema định nghĩa rõ | Có `.proto` định nghĩa rõ |
| Payload | Thường lớn hơn binary format | Thường gọn | Thường gọn |
| Code generation | Có thể dùng DTO/validation library | Có generated SpecificRecord | Có generated message classes |
| Schema evolution | Phụ thuộc JSON Schema và policy | Có writer/reader schema resolution | Dựa trên field number và wire rules |
| Phù hợp | Tích hợp đơn giản, debug dễ, nhiều hệ thống web | Event streaming và schema registry | API/event cần schema mạnh, nhiều ngôn ngữ |

Lựa chọn nên dựa trên khả năng tương tác giữa các service, yêu cầu schema governance, hiệu năng, công cụ và kỹ năng đội ngũ. Định dạng binary không tự động làm hệ thống tương thích; schema vẫn cần versioning và compatibility checks.

## 11. Schema Registry quản lý hợp đồng như thế nào?

Schema Registry lưu schema và phiên bản schema theo subject, đồng thời kiểm tra compatibility khi đăng ký schema mới. Serializer/Deserializer tích hợp registry có thể ghi schema ID vào payload format để consumer tìm writer schema tương ứng khi đọc.

Với Confluent Schema Registry, subject mặc định thường dựa trên topic và loại dữ liệu, ví dụ:

- `orders.created-value` cho value schema.
- `orders.created-key` cho key schema.

Subject naming strategy có thể thay đổi phạm vi chia sẻ schema, ví dụ topic-based, record-based hoặc topic-record-based. Chọn strategy có chủ đích vì nó quyết định schema nào được kiểm tra tương thích với schema nào.

Một số cấu hình producer/consumer minh họa với Avro:

```yaml
spring:
  kafka:
    properties:
      "[schema.registry.url]": ${SCHEMA_REGISTRY_URL}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
      properties:
        "[specific.avro.reader]": true
```

Ví dụ giả định project đã thêm dependency serializer/deserializer tương thích với phiên bản Kafka client và Schema Registry đang sử dụng. `specific.avro.reader=true` yêu cầu deserializer tạo generated SpecificRecord khi schema/class phù hợp. Nếu dùng GenericRecord, cách bind payload trong listener sẽ khác.

Schema Registry không nằm trong Kafka broker protocol cốt lõi; đây là dịch vụ riêng mà serializer/deserializer cần truy cập. Cần cấu hình endpoint, TLS/SASL, authentication, timeout và availability cho Registry tương tự một dependency runtime quan trọng.

## 12. Tích hợp Schema Registry với Spring Kafka

Spring Kafka cung cấp abstraction `Serializer`/`Deserializer` của Kafka thông qua `ProducerFactory` và `ConsumerFactory`. Serializer của Schema Registry vẫn hoạt động ở tầng Kafka client; không cần `RecordMessageConverter` để parse lại payload Avro/Protobuf đã được deserializer tạo thành object.

Ví dụ listener dùng generated Avro class:

```java
@KafkaListener(topics = "orders.created", groupId = "order-projection")
public void onMessage(OrderCreated event) {
    orderService.process(
            event.getEventId().toString(),
            event.getOrderId().toString(),
            event.getTotal());
}
```

Producer gửi object generated:

```java
kafkaTemplate.send("orders.created", event.getOrderId().toString(), event);
```

`KafkaAvroSerializer` serialize object theo schema đã đăng ký hoặc theo chính sách đăng ký cấu hình. Consumer dùng writer schema ID trong payload để lấy schema cần thiết và deserialize. Các service cần chia sẻ schema contract qua Registry hoặc artifact/schema repository; không nhất thiết chia sẻ cùng một Java class.

Nếu bật `auto.register.schemas=false`, schema phải được đăng ký trước qua CI/CD hoặc quy trình quản trị. Đây là lựa chọn thường dùng để ngăn producer runtime tự đăng ký schema ngoài quy trình review.

## 13. Versioning: version schema hay version event?

Schema Registry có thể quản lý nhiều phiên bản schema dưới cùng subject. Điều này không nhất thiết yêu cầu đổi tên Kafka topic hoặc thêm trường `version` vào mọi event.

Phân biệt:

- **Schema version:** phiên bản cấu trúc serialize được Registry quản lý.
- **Event type/version:** phiên bản semantics của event theo quy ước domain, nếu ứng dụng cần.
- **Topic version:** thay đổi topic name, ví dụ `orders.created.v2`, thường dùng khi thay đổi không thể tương thích hoặc cần migration lớn.

Không tăng `eventVersion` chỉ vì thêm một trường optional nếu schema compatibility policy đã xử lý được thay đổi và semantics không đổi. Ngược lại, nếu ý nghĩa event thay đổi đáng kể, có thể cần event type/version mới dù cấu trúc trường không đổi.

Chỉ tạo topic mới khi có lý do rõ ràng: breaking contract, thay đổi partitioning/retention/security boundary, hoặc cần chạy song song hai luồng trong giai đoạn migration. Tạo topic version mới cho mọi thay đổi nhỏ sẽ làm tăng chi phí vận hành và đồng bộ consumer.

## 14. Quy trình rollout thay đổi contract an toàn

Với thay đổi tương thích theo hướng mở rộng, dùng chiến lược **expand → migrate → contract**:

1. **Expand schema:** thêm trường mới optional/default, giữ field cũ.
2. **Nâng consumer:** consumer mới đọc được cả record cũ lẫn record mới; triển khai và quan sát.
3. **Nâng producer:** producer bắt đầu gửi trường mới sau khi consumer đã sẵn sàng.
4. **Migrate usage:** consumer chuyển sang dùng trường mới; kiểm tra dữ liệu và metrics.
5. **Contract:** chỉ bỏ field cũ sau khi không còn producer/consumer cũ và hết thời gian replay cần hỗ trợ.

Ví dụ đổi `customerName` sang `displayName`:

```text
Giai đoạn 1: Producer gửi customerName
             Consumer đọc customerName

Giai đoạn 2: Schema thêm displayName (optional)
             Consumer đọc displayName nếu có, fallback customerName

Giai đoạn 3: Producer gửi cả hai field
             Consumer chuyển sang displayName

Giai đoạn 4: Xác nhận mọi consumer đã migrate
             Producer ngừng customerName

Giai đoạn 5: Schema bỏ customerName sau thời gian tương thích/replay
```

Không bỏ field cũ ngay trong cùng release mà producer và consumer được triển khai độc lập. Trong thời gian rolling deployment, phiên bản cũ và mới có thể chạy đồng thời.

## 15. Hợp đồng phải tương thích với dữ liệu lịch sử

Kafka lưu record theo retention của topic. Consumer mới có thể đọc lại dữ liệu cũ khi reset offset, rebuild projection hoặc xử lý sự cố. Vì vậy, schema mới cần được đánh giá với dữ liệu lịch sử mà consumer thực sự có thể gặp, không chỉ với payload producer đang gửi hôm nay.

Hãy xác định:

- Retention của topic và thời gian tối đa có thể replay.
- Consumer có thể bắt đầu từ `earliest` hay chỉ đọc record mới.
- Có lưu archive/backup ngoài Kafka không.
- Có dữ liệu được tạo bởi nhiều phiên bản producer cùng tồn tại không.
- Registry compatibility là latest hay transitive.
- Consumer có fallback cho field/enum mới chưa biết không.

Nếu schema mới chỉ tương thích với phiên bản liền trước nhưng không đọc được record cũ hơn, replay toàn topic có thể thất bại. Dùng transitive compatibility khi yêu cầu phải đọc dữ liệu qua nhiều thế hệ schema, hoặc xây migration/reprocessing plan riêng.

## 16. Schema evolution và partition key

Key Kafka thường quyết định partition và do đó ảnh hưởng ordering. Key cũng là một phần của hợp đồng dữ liệu, dù schema Registry có thể quản lý key và value bằng subject riêng.

Thay đổi key có thể:

- Làm cùng một aggregate được định tuyến sang partition khác.
- Thay đổi ordering tương đối giữa các event.
- Ảnh hưởng compaction nếu topic dùng `cleanup.policy=compact`.
- Làm consumer không còn tìm được dữ liệu theo key cũ.

Không đổi key hoặc thuật toán partitioning một cách âm thầm trong migration schema. Nếu cần đổi key, hãy đánh giá re-key/migration, partition assignment và cách consumer rebuild state.

## 17. Contract testing trong CI/CD

Không nên chờ tới lúc deploy mới phát hiện producer và consumer không tương thích. Có thể kiểm tra hợp đồng ở nhiều lớp:

| Loại kiểm thử | Nội dung |
| --- | --- |
| Schema validation | Payload đúng schema, kiểu, required/default và constraint |
| Compatibility check | Schema mới tuân thủ policy với phiên bản cũ |
| Producer contract test | Producer serialize event đúng wire format và semantics |
| Consumer contract test | Consumer đọc được fixture của các phiên bản được hỗ trợ |
| Cross-language test | Producer/consumer ở ngôn ngữ khác nhau hiểu cùng payload |
| Replay test | Consumer mới xử lý được dữ liệu lịch sử đại diện |
| Integration test | Serializer, Registry, Kafka broker và listener hoạt động cùng nhau |

Ví dụ quy trình CI:

```text
Pull request thay schema
        |
        v
Lint / validate schema
        |
        v
Compatibility check với Registry policy
        |
        v
Generate classes + compile
        |
        v
Producer/consumer contract tests
        |
        v
Replay fixtures từ schema cũ
        |
        v
Cho phép merge và release
```

Với Schema Registry, có thể gọi API compatibility check trong CI hoặc dùng plugin/tooling của nền tảng để chặn schema breaking trước khi deploy. Hãy kiểm tra đúng subject naming strategy và compatibility mode đang áp dụng trong môi trường production.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Consumer mới không đọc được record cũ | Schema mới thiếu default cho field mới hoặc reader không hỗ trợ writer schema | Kiểm tra backward compatibility và fixture lịch sử |
| Consumer cũ lỗi khi producer thêm field | JSON parser/validation từ chối field lạ hoặc schema forward-incompatible | Cho phép field mới, nâng consumer trước hoặc dùng version migration |
| Deserialize lỗi dù tên field đúng | Kiểu dữ liệu, nullability hoặc format không khớp | Kiểm tra wire schema, không chỉ Java DTO |
| Consumer parse thành công nhưng tính sai | Đơn vị hoặc ý nghĩa trường thay đổi | Xem semantics là một phần contract; dùng field/version mới |
| Enum mới làm consumer cũ lỗi | Consumer không xử lý symbol chưa biết | Có fallback/UNKNOWN hoặc rollout consumer trước |
| Avro thêm field bị lỗi đọc dữ liệu cũ | Field mới không có default | Thêm default hợp lệ hoặc migration khác |
| Protobuf payload bị diễn giải sai | Tái sử dụng field number hoặc đổi wire type không tương thích | Reserve tag đã xóa; không tái sử dụng field number |
| Registry từ chối schema mới | Compatibility mode không cho phép thay đổi | Đọc báo cáo compatibility, điều chỉnh schema hoặc migration plan |
| Producer tự đăng ký schema ngoài ý muốn | `auto.register.schemas=true` trong runtime | Tắt auto registration và đăng ký qua CI/CD nếu cần governance |
| Replay topic cũ thất bại | Schema chỉ tương thích với phiên bản gần nhất | Dùng transitive check hoặc kiểm thử toàn bộ lịch sử được hỗ trợ |

## 19. Checklist thiết kế và phát hành contract

- [ ] Event có tên và ý nghĩa nghiệp vụ ổn định.
- [ ] Mỗi field có type, required/optional, nullability và semantics rõ ràng.
- [ ] Timestamp, tiền tệ, đơn vị và timezone được quy ước.
- [ ] Key contract và partitioning được xem xét cùng value schema.
- [ ] Chọn JSON, Avro hoặc Protobuf theo yêu cầu tích hợp.
- [ ] Schema Registry subject naming và compatibility mode được xác định.
- [ ] Kiểm tra backward/forward/full và transitive theo nhu cầu replay.
- [ ] Consumer mới xử lý được record lịch sử trong thời gian hỗ trợ.
- [ ] Thay đổi breaking có migration hoặc topic/event version riêng.
- [ ] Rollout theo expand → migrate → contract.
- [ ] CI chạy schema compatibility và contract tests.
- [ ] Có kế hoạch replay, rollback và xử lý DLT khi contract lỗi.

## 20. Kết luận

Hợp đồng dữ liệu giữa producer và consumer là thỏa thuận về cấu trúc, kiểu, ý nghĩa và quy tắc tiến hóa của event được ghi vào Kafka. Hãy quản lý wire schema thay vì phụ thuộc vào việc các service dùng cùng Java DTO. Thiết kế field rõ ràng, phân biệt optional/null/default, giữ ổn định semantics và xem key/partitioning là một phần của contract.

Với hệ thống nhiều service hoặc nhiều ngôn ngữ, Avro, Protobuf hoặc JSON Schema kết hợp Schema Registry giúp quản lý phiên bản và kiểm tra compatibility. Dùng backward/forward/full và transitive compatibility theo yêu cầu rollout và replay. Triển khai thay đổi theo expand → migrate → contract, kiểm thử schema mới với dữ liệu lịch sử và chặn breaking change ngay trong CI/CD. Một hợp đồng tốt giúp producer và consumer phát hành độc lập mà vẫn trao đổi event đáng tin cậy.

## Tài liệu tham khảo

- [Apache Kafka — Message Serialization](https://kafka.apache.org/documentation/#producerconfigs_key.serializer)
- [Confluent Schema Registry — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
- [Apache Avro — Schema Resolution](https://avro.apache.org/docs/current/specification/)
- [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating)
- [Spring for Apache Kafka — Serialization, Deserialization and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
