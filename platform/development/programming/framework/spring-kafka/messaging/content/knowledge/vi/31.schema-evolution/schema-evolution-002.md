# JSON schema và versioning

JSON rất linh hoạt, nhưng nếu producer và consumer tự do thay đổi cấu trúc payload thì contract giữa các service dễ bị phá vỡ. Một producer có thể đổi `amount` từ number sang string, xóa một field hoặc thêm field bắt buộc mà consumer cũ chưa biết. Message vẫn là JSON hợp lệ về cú pháp, nhưng không còn hợp lệ với ứng dụng đang đọc nó.

JSON Schema mô tả cấu trúc và các ràng buộc của một JSON document. Khi kết hợp với Schema Registry, mỗi subject có lịch sử schema version và chính sách compatibility để kiểm tra thay đổi trước khi producer/consumer triển khai. Trong Spring Kafka, có thể dùng Jackson `JsonSerializer`/`JsonDeserializer` để truyền JSON đơn thuần, hoặc dùng Confluent `KafkaJsonSchemaSerializer`/`KafkaJsonSchemaDeserializer` để tích hợp JSON Schema với Schema Registry. Hai cách này có mục tiêu khác nhau và không nên nhầm lẫn.

## 1. JSON document, JSON Schema và Schema Registry

Ba khái niệm cần phân biệt:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| JSON document | Dữ liệu thực tế được gửi trong Kafka record | `{"orderId":"O-42","amount":120000}` |
| JSON Schema | Mô tả kiểu dữ liệu, field bắt buộc và ràng buộc | `orderId` là string, `amount` là number |
| Schema Registry | Lưu schema theo subject/version, cấp schema ID và kiểm tra compatibility | Subject `orders-value`, version 2 |

JSON Schema không phải một JSON message mẫu. Nó là contract để kiểm tra message. Schema Registry cũng không thay Kafka broker; Registry quản lý schema và metadata, còn Kafka lưu record. Serializer/deserializer kết nối hai thành phần này bằng schema ID.

Nếu chỉ dùng `org.springframework.kafka.support.serializer.JsonSerializer`, Spring Kafka dùng Jackson để chuyển object thành JSON bytes. Serializer đó không tự đăng ký JSON Schema, không cấp schema ID và không kiểm tra compatibility trong Schema Registry. Muốn có các khả năng đó, cần serializer/deserializer tương thích với Registry, ví dụ Confluent JSON Schema SerDes.

## 2. JSON Schema mô tả dữ liệu như thế nào?

JSON Schema sử dụng các keyword để định nghĩa loại dữ liệu và quy tắc. Các keyword thường gặp:

| Keyword | Ý nghĩa |
|---|---|
| `$schema` | URI xác định dialect/draft của JSON Schema |
| `$id` | URI định danh schema và làm base URI khi resolve reference |
| `type` | Kiểu dữ liệu như `object`, `array`, `string`, `integer`, `number`, `boolean`, `null` |
| `properties` | Schema của từng property trong object |
| `required` | Danh sách property phải xuất hiện |
| `additionalProperties` | Quy định property không được khai báo có được phép hay không |
| `items` | Schema của phần tử trong array |
| `enum` | Tập giá trị được phép |
| `minimum`, `maximum` | Giới hạn số |
| `minLength`, `maxLength` | Giới hạn độ dài chuỗi |
| `pattern` | Biểu thức regular expression cho chuỗi |
| `oneOf`, `anyOf`, `allOf` | Kết hợp nhiều schema theo các quy tắc khác nhau |
| `$ref` | Tham chiếu schema khác hoặc một phần schema hiện tại |

Ví dụ, schema cho event `OrderCreated`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.com/orders/order-created.json",
  "title": "OrderCreated",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "eventId": { "type": "string", "minLength": 1 },
    "orderId": { "type": "string", "minLength": 1 },
    "occurredAt": { "type": "string", "format": "date-time" },
    "amount": { "type": "number", "minimum": 0 },
    "currency": { "type": "string", "enum": ["VND", "USD"] }
  },
  "required": ["eventId", "orderId", "occurredAt", "amount", "currency"]
}
```

Schema này yêu cầu payload là object có đủ năm property. `amount` phải là number không âm; `currency` chỉ được nhận `VND` hoặc `USD`; property chưa khai báo bị từ chối do `additionalProperties: false`.

Ví dụ dùng Draft 2020-12. Confluent Platform trước 7.6.0 hỗ trợ đầy đủ Draft 04, 06 và 07; từ 7.6.0 trở lên hỗ trợ thêm Draft 2020-12. Nếu Registry của dự án cũ hơn, đổi `$schema` sang draft được hỗ trợ (thường là Draft 07) và kiểm tra lại các keyword đang dùng.

`format: date-time` mô tả định dạng chuỗi ngày giờ, nhưng việc kiểm tra `format` có được thực thi hay chỉ được xem là annotation phụ thuộc draft và validator. Nếu format là điều kiện bắt buộc, hãy xác minh validator đang dùng có bật format assertion và bổ sung kiểm thử dữ liệu sai.

## 3. Phân biệt `$schema`, `$id` và version

Ba loại thông tin này giải quyết ba vấn đề khác nhau:

- `$schema` xác định phiên bản đặc tả JSON Schema, ví dụ Draft 07 hoặc Draft 2020-12. Nó không phải version của event.
- `$id` định danh schema và hỗ trợ resolve `$ref`. Nó không tự tăng khi đăng ký schema mới.
- Schema Registry subject version biểu thị thứ tự schema được đăng ký trong một subject, ví dụ version 1, 2, 3.

Ngoài ra, Schema Registry cấp schema ID để serializer ghi vào wire format. Schema ID và subject version không phải cùng một khái niệm. Một schema ID xác định schema trong Registry; version xác định vị trí của schema trong lịch sử một subject. Không dùng schema ID làm event version trong nghiệp vụ.

Nếu event cần version để xử lý logic, có thể đưa field riêng như `eventVersion` hoặc `eventTypeVersion` vào payload. Field này mô tả phiên bản contract nghiệp vụ, còn Registry version phục vụ quản lý schema. Hai con số có thể trùng tình cờ nhưng không có nghĩa vụ phải trùng.

## 4. Field vắng mặt khác với field có giá trị null

Trong JSON Schema, `required` quy định property phải xuất hiện. Nó không có nghĩa property phải khác null. Kiểu của property mới quyết định null có hợp lệ hay không.

Ví dụ property `note` được phép vắng mặt, nhưng nếu xuất hiện thì phải là string:

```json
{
  "type": "object",
  "properties": {
    "note": { "type": "string" }
  }
}
```

Các payload sau có ý nghĩa khác nhau:

```json
{}
```

```json
{"note": "Giao giờ hành chính"}
```

```json
{"note": null}
```

Payload thứ nhất hợp lệ vì `note` không required. Payload thứ hai hợp lệ vì giá trị là string. Payload thứ ba không hợp lệ vì schema không cho phép null.

Nếu property được phép nhận cả string và null, khai báo union type theo draft đang dùng:

```json
{
  "type": "object",
  "properties": {
    "note": {
      "type": ["string", "null"]
    }
  }
}
```

`nullable: true` là cách viết thường thấy trong OpenAPI 3.0, không phải keyword chuẩn của JSON Schema. Khi viết JSON Schema thuần, dùng type union hoặc `oneOf` phù hợp với draft.

## 5. Open, closed và partially open content model

`additionalProperties` có ảnh hưởng lớn tới schema evolution:

| Content model | Cấu hình | Ý nghĩa |
|---|---|---|
| Open | Bỏ `additionalProperties` hoặc đặt `true` | Cho phép property chưa khai báo |
| Closed | Đặt `additionalProperties: false` | Từ chối property chưa khai báo |
| Partially open | Đặt `additionalProperties` thành một schema | Cho phép property bổ sung nhưng phải thỏa kiểu/ràng buộc |

Open model:

```json
{
  "type": "object",
  "properties": {
    "orderId": { "type": "string" }
  }
}
```

Schema trên vẫn chấp nhận `{"orderId":"O-42","source":"mobile"}` vì `additionalProperties` mặc định là true.

Closed model:

```json
{
  "type": "object",
  "properties": {
    "orderId": { "type": "string" }
  },
  "additionalProperties": false
}
```

Schema này từ chối property `source` nếu chưa khai báo trong `properties`.

Partially open model:

```json
{
  "type": "object",
  "properties": {
    "orderId": { "type": "string" }
  },
  "additionalProperties": { "type": "string" }
}
```

Schema cho phép property mở rộng, nhưng value của property bổ sung phải là string. Đây là cách giữ khả năng mở rộng trong khi vẫn kiểm soát kiểu dữ liệu.

Open model linh hoạt với field mới nhưng có thể che giấu typo hoặc field sai kiểu. Closed model phát hiện property không được khai báo sớm, nhưng làm thay đổi field trở nên nhạy cảm hơn với consumer cũ. Hãy chọn content model theo contract và compatibility policy thực tế, không chỉ theo sở thích cá nhân.

## 6. Schema versioning trong Schema Registry

Schema Registry quản lý schema theo subject. Với chiến lược mặc định `TopicNameStrategy`, subject cho value thường có tên `<topic>-value`, còn subject cho key thường là `<topic>-key`.

Ví dụ topic `orders`:

```text
orders-key
  version 1: schema của key

orders-value
  version 1: OrderCreated schema v1
  version 2: OrderCreated schema v2
  version 3: OrderCreated schema v3
```

Mỗi lần đăng ký schema mới cho cùng subject, Registry kiểm tra compatibility theo chính sách đã cấu hình. Nếu hợp lệ, schema được thêm vào lịch sử subject. Nếu không hợp lệ, đăng ký bị từ chối, trừ khi người quản trị chủ động thay đổi policy hoặc dùng cơ chế force phù hợp.

Subject là ranh giới kiểm tra compatibility. Nếu đổi subject naming strategy, cùng một payload có thể được quản lý dưới subject khác và không còn được so sánh với lịch sử cũ như trước. Vì vậy, thay đổi subject strategy cũng là một thay đổi kiến trúc cần review.

## 7. Các compatibility mode

Compatibility mô tả schema mới và cũ có thể được dùng cùng nhau trong giai đoạn rollout hay không.

| Mode | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| `BACKWARD` | Consumer dùng schema mới đọc được data được ghi theo schema ngay trước đó | Consumer mới có đọc được record cũ không? |
| `BACKWARD_TRANSITIVE` | Consumer mới đọc được data từ mọi schema version trước đó | Consumer mới có replay được toàn bộ lịch sử không? |
| `FORWARD` | Consumer dùng schema cũ đọc được data theo schema mới nhất | Consumer cũ có đọc được record mới không? |
| `FORWARD_TRANSITIVE` | Mọi schema cũ đều đọc được data theo schema mới | Consumer cũ nhất còn chạy có đọc được record mới không? |
| `FULL` | Backward và forward compatible với schema ngay trước đó | Hai phía có thể đọc chéo version liền kề không? |
| `FULL_TRANSITIVE` | Backward và forward compatible với tất cả version trước | Mọi client còn tồn tại có thể đọc dữ liệu của nhau không? |
| `NONE` | Không kiểm tra compatibility | Tổ chức chấp nhận tự chịu rủi ro breaking change |

Confluent Schema Registry mặc định dùng `BACKWARD` và kiểm tra với version gần nhất, không phải toàn bộ lịch sử. Nếu consumer cần replay từ đầu topic hoặc dữ liệu cũ có thể còn tồn tại lâu, cân nhắc `BACKWARD_TRANSITIVE` để kiểm tra schema mới với mọi version trước đó.

Không có mode nào thay thế việc kiểm thử nghiệp vụ. Hai schema có thể pass compatibility nhưng thay đổi ý nghĩa field, đơn vị tiền tệ hoặc cách diễn giải timestamp khiến consumer xử lý sai.

## 8. Compatibility của JSON Schema phụ thuộc content model

JSON Schema có các quy tắc tương thích phức tạp hơn việc chỉ thêm hoặc xóa property. Với Confluent Schema Registry, dưới compatibility policy `STRICT`, kết quả còn phụ thuộc schema là open hay closed. Bảng dưới đây tóm tắt các thay đổi thường gặp; phải kiểm tra lại trên đúng phiên bản Registry và policy đang chạy.

### Open content model (`additionalProperties` true hoặc không khai báo)

| Thay đổi | Backward | Forward | Full |
|---|:---:|:---:|:---:|
| Thêm optional property |  | Có |  |
| Xóa optional property | Có |  |  |
| Thêm required property |  | Có |  |
| Xóa required property | Có |  |  |
| Thêm variant vào `oneOf`/union | Có |  |  |
| Xóa variant khỏi `oneOf`/union |  | Có |  |
| Nới lỏng scalar type (ví dụ `integer` → `number`) | Có |  |  |
| Siết chặt scalar type |  | Có |  |

### Closed content model (`additionalProperties: false`)

| Thay đổi | Backward | Forward | Full |
|---|:---:|:---:|:---:|
| Thêm optional property | Có |  |  |
| Xóa optional property |  | Có |  |
| Thêm required property |  |  |  |
| Xóa required property |  |  |  |
| Thêm variant vào `oneOf`/union | Có |  |  |
| Xóa variant khỏi `oneOf`/union |  | Có |  |
| Nới lỏng scalar type (ví dụ `integer` → `number`) | Có |  |  |
| Siết chặt scalar type |  | Có |  |

Các bảng này mô tả các quy tắc của Confluent Registry dưới strict policy, không phải lời khẳng định rằng mọi JSON Schema validator đều triển khai compatibility theo cùng một cách. `LENIENT` policy có thể áp dụng quy tắc khác. Các thay đổi phức tạp như `patternProperties`, `dependencies`, `$ref`, `oneOf`, `enum`, `minimum` hoặc `format` cần được kiểm tra bằng Registry API thay vì suy luận chỉ từ tên thay đổi.

Một điểm quan trọng: nếu writer schema cũ là open, nó có thể đã phát ra property chưa khai báo với bất kỳ kiểu nào. Khi reader schema mới khai báo property đó với kiểu cụ thể, dữ liệu cũ có thể không thỏa kiểu mới. Đây là lý do thêm field đôi khi không backward compatible với open model.

## 9. Thêm optional field an toàn như thế nào?

Giả sử schema v1 của `OrderCreated` có `eventId`, `orderId` và `amount`. Ứng dụng muốn thêm `source` để biết đơn hàng đến từ web hay mobile.

Schema v1:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.com/orders/order-created.json",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "eventId": { "type": "string" },
    "orderId": { "type": "string" },
    "amount": { "type": "number" }
  },
  "required": ["eventId", "orderId", "amount"]
}
```

Schema v2 thêm `source` nhưng không đưa nó vào `required`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.com/orders/order-created.json",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "eventId": { "type": "string" },
    "orderId": { "type": "string" },
    "amount": { "type": "number" },
    "source": { "type": "string", "enum": ["web", "mobile", "store"] }
  },
  "required": ["eventId", "orderId", "amount"]
}
```

Consumer v2 có thể đọc record cũ vì `source` không bắt buộc. Tuy nhiên, consumer v1 dùng closed schema sẽ từ chối record mới có `source`. Với chiến lược backward-compatible rollout, triển khai consumer hỗ trợ v2 trước, sau đó mới triển khai producer bắt đầu ghi `source`.

Nếu dùng open model, consumer v1 có thể chấp nhận property mới chưa biết, nhưng compatibility check của Registry vẫn cần được chạy theo policy cụ thể. Đừng tự kết luận chỉ vì `additionalProperties` mặc định là true.

## 10. Vì sao không nên thêm required field ngay?

Giả sử v2 đưa `source` vào `required`. Consumer mới cần field này để đọc dữ liệu, nhưng record cũ chưa có `source`. Consumer v2 có thể không đọc được lịch sử đã tồn tại. Với open model, producer cũ vẫn có thể gửi payload thiếu field mới; với closed model, việc thêm required field còn có thể bị Registry từ chối theo strict policy.

Quy trình an toàn thường là:

1. Thêm property dưới dạng optional.
2. Triển khai consumer đọc được cả record cũ thiếu property và record mới có property.
3. Triển khai producer bắt đầu ghi property.
4. Theo dõi dữ liệu cũ và xác định thời điểm tất cả record/consumer đã chuyển đổi.
5. Chỉ khi có kế hoạch major version rõ ràng mới cân nhắc bắt buộc property hoặc chuyển sang topic/version contract mới.

Nếu nghiệp vụ yêu cầu property mới luôn có giá trị, có thể đặt default ở tầng ứng dụng. JSON Schema keyword `default` là annotation mô tả giá trị mặc định; validator thông thường không tự chèn giá trị đó vào payload. Producer hoặc consumer phải chủ động áp dụng default.

## 11. Thay đổi type và constraint

Đổi type có thể là breaking change:

```json
{"amount": 120000}
```

```json
{"amount": "120000"}
```

JSON number và string không tương đương. Consumer parse `amount` thành `BigDecimal` có thể thất bại khi producer chuyển sang string. Không dùng thay đổi type để sửa cách format dữ liệu trong một lần deploy.

Các constraint cũng ảnh hưởng compatibility:

- Tăng `minimum` có thể loại bỏ dữ liệu trước đó vốn hợp lệ.
- Giảm `maximum` có thể làm record cũ không còn hợp lệ.
- Tăng `minLength` hoặc giảm `maxLength` có thể từ chối payload cũ.
- Thu hẹp `enum` có thể khiến giá trị đã tồn tại không còn hợp lệ.
- Chuyển từ `integer` sang `number` là nới lỏng kiểu trong một số quy tắc JSON Schema; chiều ngược lại là siết chặt.

Nếu cần đổi đơn vị, ví dụ `amount` từ VND sang USD, giữ nguyên tên và type vẫn chưa đủ. Nên thêm field/currency rõ ràng, định nghĩa semantics, hoặc tạo event contract mới. Compatibility kỹ thuật không thể phát hiện mọi thay đổi ngữ nghĩa.

## 12. Versioning bằng expand-migrate-contract

Với thay đổi lớn, áp dụng ba giai đoạn:

```text
EXPAND
  Thêm field mới hoặc schema mới theo cách có thể coexist
       |
       v
MIGRATE
  Deploy consumer hỗ trợ cả hai dạng, sau đó migrate producer/data
       |
       v
CONTRACT
  Ngừng field cũ khi không còn producer/consumer phụ thuộc
```

Ví dụ muốn đổi `customerName` thành object `customer`:

1. Expand: thêm `customer` optional, giữ `customerName`.
2. Migrate: consumer đọc `customer` nếu có, fallback `customerName`; producer ghi cả hai trong giai đoạn chuyển đổi nếu cần.
3. Contract: sau khi xác nhận mọi consumer đã dùng `customer`, ngừng ghi và loại bỏ `customerName` trong một schema version được kiểm tra compatibility.

Không xóa field cũ ngay trong lần deploy đầu tiên. Nếu field đã tồn tại trong Kafka retention, consumer replay hoặc batch job có thể vẫn cần đọc record cũ trong nhiều ngày/tháng.

## 13. Subject naming strategy và ranh giới compatibility

Subject name strategy quyết định schema được đăng ký dưới subject nào. Mặc định `TopicNameStrategy` dùng tên topic, ví dụ `orders-value` và `orders-key`.

Các chiến lược thường gặp:

| Strategy | Ranh giới subject | Khi phù hợp |
|---|---|---|
| `TopicNameStrategy` | Một subject key/value cho mỗi topic | Topic có một contract chính và muốn kiểm tra compatibility theo topic |
| `RecordNameStrategy` | Subject theo tên record/type | Nhiều topic dùng chung một event type và cần cùng lịch sử schema |
| `TopicRecordNameStrategy` | Kết hợp topic và record/type | Một topic có nhiều event type nhưng muốn compatibility riêng cho từng type trong topic |

Với JSON Schema, cách đặt subject cần thống nhất giữa producer, consumer và quy trình đăng ký schema. Thay strategy có thể làm Registry tạo subject mới, khiến compatibility history cũ không còn được kiểm tra theo ranh giới trước đó. Hãy xem đây là migration, không phải một thay đổi cấu hình vô hại.

## 14. Schema ID và wire format

Confluent JSON Schema serializer không mặc định nhúng toàn bộ schema vào mỗi Kafka record. Wire format thông thường gồm:

```text
+----------------+----------------------+----------------------+
| Magic byte     | Schema ID            | JSON payload         |
| 1 byte         | 4 bytes              | JSON bytes           |
+----------------+----------------------+----------------------+
```

Deserializer đọc schema ID, tra schema tương ứng trong Schema Registry rồi deserialize payload. Vì vậy:

- Producer và consumer phải truy cập được Schema Registry.
- Schema ID được ghi trong record phải còn tra cứu được.
- Không xóa schema/version đang được record còn retention tham chiếu.
- Khi archive/di chuyển record sang hệ thống khác, cần lưu ý record phụ thuộc Registry để giải mã.

Định dạng wire cụ thể thuộc serializer của Confluent; Kafka broker chỉ lưu bytes và không tự kiểm tra JSON Schema.

## 15. Dùng JSON Schema SerDes với Spring Kafka

Nếu ứng dụng dùng Confluent Schema Registry, thêm dependency JSON Schema serializer tương thích với Confluent Platform/Schema Registry đang chạy. Ví dụ Maven:

```xml
<dependency>
    <groupId>io.confluent</groupId>
    <artifactId>kafka-json-schema-serializer</artifactId>
    <version>${confluent.version}</version>
</dependency>
```

Đảm bảo Maven đã khai báo Confluent repository và chọn version tương thích với Kafka client/Spring Boot của dự án. Không lấy version mới nhất tùy ý nếu nó kéo theo Kafka client không tương thích với dependency management hiện có.

Cấu hình producer/consumer trong Spring Boot:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.json.KafkaJsonSchemaSerializer
      properties:
        "[schema.registry.url]": http://localhost:8081
        "[auto.register.schemas]": false
        "[json.fail.invalid.schema]": true
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.json.KafkaJsonSchemaDeserializer
      properties:
        "[schema.registry.url]": http://localhost:8081
        "[json.value.type]": com.example.orders.OrderCreated
        "[json.fail.invalid.schema]": true
```

`json.value.type` cho deserializer biết kiểu Java đích. Nếu không cấu hình kiểu cụ thể, deserializer có thể trả `LinkedHashMap` cho JSON object hoặc `JsonNode` nếu cấu hình tương ứng. Với nhiều event type trong cùng topic, cần thiết kế type resolution/`oneOf`/schema references thay vì ép mọi record vào một class.

`json.fail.invalid.schema=true` yêu cầu serializer/deserializer báo lỗi khi payload không hợp lệ với schema; tài liệu Confluent ghi mặc định của thuộc tính này là `false`. Hãy bật rõ ràng nếu cần validation ở client và kiểm thử cả đường lỗi. Schema Registry compatibility check khi đăng ký schema và payload validation khi serialize là hai bước khác nhau.

## 16. Phân biệt Jackson JsonSerializer với KafkaJsonSchemaSerializer

| Tiêu chí | Spring Kafka `JsonSerializer` | Confluent `KafkaJsonSchemaSerializer` |
|---|---|---|
| Chuyển Java object thành JSON | Có | Có |
| Dùng Jackson | Có | Có thể dùng Jackson để ánh xạ object |
| Đăng ký/tra schema trong Schema Registry | Không tự động | Có |
| Schema ID trong wire format | Không | Có |
| Compatibility check khi đăng ký schema | Không | Có thể dùng Schema Registry |
| JSON Schema validation | Cần validator riêng nếu muốn | Có thể bật qua cấu hình JSON Schema SerDes |
| Phụ thuộc Schema Registry | Không | Có |

Nếu dự án chỉ cần JSON payload và contract được quản lý bằng code/test riêng, Jackson serializer có thể đủ. Nếu cần Registry quản lý schema version, schema ID và compatibility giữa nhiều service, dùng Registry-aware serializer/deserializer.

Không cấu hình `KafkaJsonSchemaSerializer` rồi giả định mọi payload đều tự động được validate nghiêm ngặt. Hãy kiểm tra `json.fail.invalid.schema`, auto registration, subject strategy và schema thực tế mà serializer đang dùng.

## 17. Auto registration và quy trình phát hành schema

`auto.register.schemas` quyết định serializer có tự đăng ký schema khi gặp schema chưa có trong subject hay không.

| Cấu hình | Hành vi |
|---|---|
| `auto.register.schemas=true` | Serializer có thể đăng ký schema được suy ra từ object; tiện cho local/dev nhưng producer runtime có thể tạo version ngoài quy trình release |
| `auto.register.schemas=false` | Schema phải được đăng ký trước hoặc serializer phải được cấu hình dùng schema version có sẵn |
| `use.latest.version=true` | Khi auto registration tắt, serializer có thể dùng schema version mới nhất của subject; cần bảo đảm object phù hợp với schema đó |
| `latest.compatibility.strict=true` | Khi dùng latest version, kiểm tra compatibility giữa schema latest và schema suy ra từ object trước khi serialize |

Trong production, thường nên đăng ký schema trong CI/CD trước khi rollout producer, sau đó tắt auto registration để tránh mỗi instance tự tạo version. Tuy nhiên, cách dùng `use.latest.version` cần được thiết kế cẩn thận: serializer có thể dùng latest schema thay cho schema suy ra từ object, nên model Java và schema Registry phải đồng bộ.

Không bật `latest.compatibility.strict=false` chỉ để bỏ qua lỗi. Chỉ dùng khi đã có schema references hoặc khác biệt được hiểu rõ và có test chứng minh payload hợp lệ.

## 18. Compatibility check trong CI/CD

Trước khi merge hoặc phát hành schema mới, gọi compatibility API của Schema Registry. Ví dụ kiểm tra schema ứng viên với version mới nhất của subject `orders-value`:

```bash
curl -X POST \
  http://localhost:8081/compatibility/subjects/orders-value/versions/latest \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  -d '{
    "schemaType": "JSON",
    "schema": "{\"type\":\"object\",\"additionalProperties\":false,\"properties\":{\"orderId\":{\"type\":\"string\"},\"amount\":{\"type\":\"number\"},\"source\":{\"type\":\"string\"}},\"required\":[\"orderId\",\"amount\"]}"
  }'
```

Kết quả `{"is_compatible":true}` cho biết schema ứng viên tương thích với version được kiểm tra theo policy hiện tại. Nếu là `false`, pipeline nên dừng và yêu cầu review. Với `BACKWARD` thông thường, API so với version mới nhất; nếu cần kiểm tra lịch sử, cấu hình transitive compatibility hoặc chạy kiểm tra phù hợp với từng version.

Sau khi pass, pipeline có thể đăng ký schema bằng endpoint subject version tương ứng. Chỉ producer được phát hành sau khi schema đã tồn tại và consumer đã được triển khai theo thứ tự rollout đã chọn.

## 19. Schema references và nhiều event type trong một topic

Nếu một topic chứa nhiều loại event, có thể dùng `oneOf` để mô tả tập schema được chấp nhận và `$ref` để tái sử dụng schema đã đăng ký:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "OrderEvents",
  "oneOf": [
    { "$ref": "OrderCreated.schema.json" },
    { "$ref": "OrderCancelled.schema.json" }
  ]
}
```

Với Confluent Schema Registry, schema reference phải được đăng ký và khai báo trong request đăng ký schema. `$ref` tới Registry reference cần khớp tên reference đã đăng ký; không giả định mọi HTTP URL bên ngoài đều được Registry resolve tự động.

Trong mô hình nhiều event type, serializer có thể cần tắt `auto.register.schemas` và bật `use.latest.version` để dùng schema union `oneOf` đã đăng ký thay vì tự đăng ký schema riêng của từng class và ghi đè subject version mới nhất. Hãy làm theo hướng dẫn của Registry đúng phiên bản và kiểm thử từng event type.

Nếu topic chỉ có một event type, schema/subject riêng cho event thường đơn giản hơn. Không thêm `oneOf` nếu không có nhu cầu thực tế.

## 20. Rollout producer và consumer theo compatibility

Với backward-compatible change, cách triển khai thường dùng là consumer trước, producer sau:

```text
1. Register schema v2
2. Deploy consumer có thể đọc v1 và v2
3. Xác nhận consumer mới chạy ổn định
4. Deploy producer ghi payload theo v2
5. Theo dõi validation, deserialize và business metrics
6. Ngừng hỗ trợ field cũ sau khi hết thời gian migration
```

Với forward-compatible change, có thể cần producer trước hoặc consumer cũ phải được bảo đảm đọc được payload mới. Hãy xác định rõ định nghĩa backward/forward của Registry và deployment topology thực tế; không dùng thứ tự rollout chung cho mọi mode.

Nếu producer và consumer được deploy độc lập, duy trì giai đoạn coexist là bắt buộc. Với breaking change, cân nhắc topic mới như `orders.v2` hoặc event type/version mới thay vì sửa contract tại chỗ rồi hy vọng mọi consumer được nâng cấp đồng thời.

## 21. Kiểm thử schema evolution

Kiểm thử cần bao phủ schema, payload và các phiên bản ứng dụng:

| Trường hợp | Kiểm tra |
|---|---|
| Payload đúng schema hiện tại | Serialize/deserialize thành công |
| Thiếu required property | Validation thất bại rõ ràng |
| Property sai type | Validation thất bại, không ép kiểu âm thầm |
| Property bổ sung với closed model | Payload bị từ chối nếu field chưa khai báo |
| Property bổ sung với open model | Payload được chấp nhận theo schema và policy |
| Optional field mới vắng mặt | Consumer mới vẫn đọc được record cũ |
| Optional field mới có mặt | Consumer cũ xử lý theo content model/compatibility đã chọn |
| Enum/type/constraint thay đổi | Registry compatibility check trả kết quả đúng kỳ vọng |
| Schema mới với mọi schema lịch sử | Kiểm tra transitive khi replay lịch sử là yêu cầu |
| Schema ID không tồn tại | Deserializer báo lỗi Registry rõ ràng |
| Registry unavailable | Producer/consumer xử lý lỗi dependency theo chính sách |
| Record cũ sau rollout | Consumer mới đọc được record trong retention |

Nên dùng Schema Registry thử nghiệm qua Testcontainers hoặc môi trường CI riêng để kiểm tra cả compatibility API và serializer/deserializer. Unit test validator không thay thế Registry compatibility check vì Registry có policy và thuật toán compatibility riêng.

## 22. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Message là JSON hợp lệ nhưng deserialize thất bại | JSON không thỏa schema hoặc type Java không khớp | Kiểm tra schema ID, schema version, required/type và `json.value.type` |
| Registry từ chối đăng ký schema | Thay đổi không tương thích với subject policy | Chạy compatibility check, xem open/closed model và chọn migration phù hợp |
| Consumer không tìm thấy schema ID | Schema bị xóa hoặc Registry không có schema tương ứng | Khôi phục schema, kiểm tra retention/cleanup và Registry endpoint |
| Serializer tự tạo nhiều schema version | `auto.register.schemas=true` trong nhiều runtime | Đăng ký schema qua release pipeline và cân nhắc tắt auto registration |
| Consumer nhận `LinkedHashMap` thay vì POJO | Không cấu hình JSON value type | Đặt `json.value.type` hoặc nhận `JsonNode`/Map có chủ đích |
| Field mới bị consumer cũ từ chối | Consumer dùng closed schema | Triển khai consumer tương thích trước khi producer phát field mới |
| Field mới vắng mặt gây lỗi | Field bị thêm vào `required` hoặc code không có fallback | Để optional trong giai đoạn migration và xử lý default ở ứng dụng |
| `format` không phát hiện ngày giờ sai | Validator không bật format assertion | Cấu hình validator hoặc kiểm tra format ở tầng ứng dụng |
| Thay subject strategy tạo version history khác | Subject name thay đổi | Review migration subject và đăng ký schema cho subject mới có chủ đích |
| Schema Registry không truy cập được | URL, TLS, credential hoặc network sai | Kiểm tra `schema.registry.url`, security properties và connectivity |

## 23. Quy trình quản lý schema version

1. Định nghĩa event contract và JSON Schema trong source control.
2. Gắn `$schema` đúng dialect được Schema Registry hỗ trợ.
3. Đặt `$id` ổn định và dùng `$ref` cho cấu trúc tái sử dụng khi cần.
4. Chọn open/closed/partially open model theo yêu cầu kiểm soát payload.
5. Xác định subject naming strategy và compatibility mode.
6. Viết payload fixture cho schema cũ và schema mới.
7. Chạy validator và Schema Registry compatibility API trong CI.
8. Đăng ký schema mới qua pipeline có kiểm soát.
9. Rollout consumer/producer theo hướng backward hoặc forward đã chọn.
10. Theo dõi lỗi serialize, deserialize, schema lookup và business validation.
11. Chỉ xóa field/schema cũ khi retention, replay job và consumer cũ không còn phụ thuộc.
12. Lưu lịch sử schema và quyết định migration để có thể audit/reproduce.

## 24. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| `$schema` là version của event | `$schema` xác định dialect JSON Schema |
| `$id` tự tăng theo lần đăng ký | `$id` định danh schema; Registry quản lý subject version riêng |
| Schema ID bằng subject version | Schema ID và version là hai loại định danh khác nhau |
| JSON parse được nghĩa là đúng contract | JSON có thể hợp cú pháp nhưng sai type, required hoặc constraint |
| Thêm field luôn backward compatible | Kết quả phụ thuộc content model và Registry policy |
| Optional nghĩa là chấp nhận null | Optional là được phép vắng mặt; null cần khai báo type rõ ràng |
| `default` tự chèn giá trị khi validate | `default` thường là annotation; ứng dụng phải áp dụng nếu cần |
| Jackson `JsonSerializer` tự dùng Schema Registry | Jackson serializer không tự đăng ký JSON Schema hoặc ghi schema ID |
| `BACKWARD` kiểm tra mọi schema cũ | `BACKWARD` mặc định chỉ so với version gần nhất; transitive mới kiểm tra toàn lịch sử |
| Compatibility pass bảo đảm nghiệp vụ đúng | Cần kiểm tra semantics, ordering, đơn vị, enum và rollout thực tế |

## Checklist trước khi phát hành JSON Schema mới

- `$schema` trỏ đúng draft được Registry và validator hỗ trợ.
- `$id` ổn định, không nhầm với schema version hoặc event version.
- `type`, `properties`, `required`, `enum`, `format` và numeric/string constraints phản ánh đúng contract.
- Đã quyết định property vắng mặt và null có ý nghĩa gì.
- `additionalProperties` được chọn có chủ đích; hiểu tác động của open/closed model.
- Subject naming strategy và compatibility mode đã được thống nhất.
- Đã chạy compatibility check trên Registry thật hoặc môi trường tương đương.
- Đã kiểm tra transitive nếu consumer cần replay toàn bộ lịch sử.
- Schema được đăng ký trước khi producer phát payload theo version mới.
- Consumer được rollout theo đúng backward/forward strategy.
- `auto.register.schemas` phù hợp với quy trình release; production không tạo version ngoài kiểm soát.
- Confluent JSON Schema SerDes và Schema Registry URL/type mapping được cấu hình đúng trong Spring Kafka.
- Đã test payload hợp lệ, thiếu field, null, sai type, field bổ sung và schema cũ.
- Không xóa schema ID/version còn được record trong Kafka retention tham chiếu.
- Có log/metric cho schema lookup failure, validation failure và compatibility rejection.

JSON Schema giúp mô tả contract của event; Schema Registry giúp quản lý lịch sử và kiểm tra khả năng tương thích khi contract thay đổi. Khi phân biệt đúng dialect, `$id`, subject version và schema ID, chọn content model phù hợp, kiểm tra compatibility trong CI và rollout consumer/producer có thứ tự, các service Spring Kafka có thể cùng đọc dữ liệu qua nhiều phiên bản mà không phải triển khai đồng thời.

## Tài liệu tham khảo

- [JSON Schema – Understanding JSON Schema](https://json-schema.org/understanding-json-schema/)
- [Confluent – JSON Schema Serializer and Deserializer](https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/serdes-json.html)
- [Confluent – Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
- [Confluent – Formats, Serializers, and Deserializers](https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/index.html)
