# Backward, forward, full compatibility và kiểm tra bắc cầu

Kafka lưu record dưới dạng byte; broker không hiểu cấu trúc Avro, Protobuf hay JSON Schema bên trong payload. Khi nhiều phiên bản producer và consumer cùng hoạt động, hệ thống cần quy tắc xác định schema mới có thể phối hợp với schema cũ hay không. Schema Registry thường cung cấp cơ chế lưu phiên bản schema và kiểm tra compatibility trước khi cho phép đăng ký schema mới.

Ba hướng compatibility thường gặp là **BACKWARD**, **FORWARD** và **FULL**. Từ khóa **TRANSITIVE** cho biết phép kiểm tra được thực hiện với tất cả phiên bản trước đó của subject thay vì chỉ phiên bản mới nhất.

Hiểu đúng hướng reader/writer và phạm vi kiểm tra giúp triển khai schema mới an toàn, đặc biệt khi consumer cần replay dữ liệu lịch sử hoặc có nhiều phiên bản ứng dụng cùng chạy trong giai đoạn rollout.

## 1. Vì sao cần schema compatibility?

Giả sử producer phiên bản 1 ghi event vào topic orders với cấu trúc:

~~~json
{
  "orderId": "order-123",
  "amount": 1250000
}
~~~

Sau đó producer phiên bản 2 bổ sung trường currency:

~~~json
{
  "orderId": "order-123",
  "amount": 1250000,
  "currency": "VND"
}
~~~

Consumer cũ có đọc được event mới không? Consumer mới có đọc được event cũ không? Câu trả lời phụ thuộc vào schema format và compatibility policy.

Nếu không kiểm soát schema evolution, một thay đổi tưởng như nhỏ có thể làm consumer deserialize thất bại, bỏ qua dữ liệu hoặc diễn giải sai ý nghĩa field. Điều này đặc biệt nguy hiểm khi producer và consumer được deploy độc lập.

Schema compatibility giúp phát hiện sớm một số thay đổi cấu trúc không tương thích trước khi schema mới được sử dụng để ghi dữ liệu.

## 2. Reader schema và writer schema

Để hiểu các chế độ compatibility, cần phân biệt hai vai trò:

- **Writer schema:** schema mà producer dùng để serialize record.
- **Reader schema:** schema mà consumer dùng để deserialize record.

Khi consumer đọc dữ liệu lịch sử, writer schema có thể là phiên bản cũ hơn reader schema. Khi consumer cũ đọc dữ liệu mới, writer schema mới hơn reader schema.

~~~mermaid
flowchart LR
    P1["Producer v1<br/>Writer schema v1"] --> K["Kafka topic<br/>serialized records"]
    P2["Producer v2<br/>Writer schema v2"] --> K
    K --> C1["Consumer v1<br/>Reader schema v1"]
    K --> C2["Consumer v2<br/>Reader schema v2"]
    R["Schema Registry"] <--> P1
    R <--> P2
    R <--> C1
    R <--> C2
~~~

Với serializer tích hợp Schema Registry, record thường mang schema ID để consumer tìm writer schema tương ứng. Reader schema có thể được chọn bởi consumer hoặc framework. Compatibility được đánh giá bằng khả năng phân giải giữa writer schema và reader schema theo quy tắc của định dạng.

Cách ghi nhớ:

- Backward: reader mới đọc được dữ liệu cũ.
- Forward: reader cũ đọc được dữ liệu mới.
- Full: cả hai hướng đều đọc được.

## 3. BACKWARD compatibility

**BACKWARD** yêu cầu schema mới có thể đọc dữ liệu được ghi bằng schema phiên bản trước gần nhất.

Nói theo reader/writer:

- Writer: schema cũ.
- Reader: schema mới.

Ví dụ producer đã ghi record bằng schema v1. Consumer được nâng lên schema v2. Nếu schema v2 có thể đọc record cũ thì thay đổi backward-compatible.

### 3.1. Ví dụ Avro: thêm field có default

Schema v1:

~~~json
{
  "type": "record",
  "name": "Order",
  "namespace": "com.example",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amount", "type": "double"}
  ]
}
~~~

Schema v2 thêm currency và khai báo default:

~~~json
{
  "type": "record",
  "name": "Order",
  "namespace": "com.example",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amount", "type": "double"},
    {"name": "currency", "type": "string", "default": "VND"}
  ]
}
~~~

Consumer dùng schema v2 có thể đọc record cũ không chứa currency; Avro reader lấy giá trị default VND. Vì vậy đây là thay đổi backward-compatible theo quy tắc Avro.

Nếu thêm field bắt buộc mà không có default, consumer mới có thể không đọc được record cũ vì writer schema cũ không cung cấp field đó.

### 3.2. Khi nào cần BACKWARD?

Backward phù hợp khi muốn triển khai consumer mới trước producer mới:

1. Deploy consumer mới có thể đọc cả dữ liệu cũ.
2. Xác nhận consumer mới chạy ổn định.
3. Deploy producer mới bắt đầu phát schema mới.
4. Consumer mới tiếp tục đọc cả record cũ lẫn record mới.

Đây là trình tự thường dùng trong rollout không đồng thời.

## 4. FORWARD compatibility

**FORWARD** yêu cầu schema phiên bản trước có thể đọc dữ liệu được ghi bằng schema mới.

Nói theo reader/writer:

- Writer: schema mới.
- Reader: schema cũ.

Điều này hữu ích khi producer được nâng cấp trước, trong khi một số consumer cũ vẫn đang chạy.

### 4.1. Ví dụ Avro: thêm field

Với ví dụ thêm currency ở schema v2, consumer cũ dùng schema v1 có thể bỏ qua field mới mà nó không biết. Vì vậy, thêm field thường tương thích theo hướng forward với Avro.

Tuy nhiên, không phải mọi thay đổi thêm field đều tương thích hai chiều. Nếu schema v2 thêm field không có default, schema v2 có thể không đọc được record v1, dù consumer v1 vẫn đọc được record v2.

### 4.2. Khi nào cần FORWARD?

Forward phù hợp khi muốn triển khai producer mới trước consumer mới:

1. Xác nhận consumer cũ có thể đọc record theo schema mới.
2. Deploy producer mới.
3. Consumer cũ và mới có thể cùng hoạt động trong giai đoạn chuyển tiếp.
4. Sau đó deploy consumer mới theo kế hoạch.

Forward không bảo đảm consumer mới đọc được dữ liệu cũ. Nếu consumer mới cần replay lịch sử, cần kiểm tra thêm backward compatibility.

## 5. FULL compatibility

**FULL** yêu cầu cả hai hướng:

- Schema mới đọc được dữ liệu cũ (backward).
- Schema cũ đọc được dữ liệu mới (forward).

FULL là giao của BACKWARD và FORWARD đối với phiên bản được kiểm tra.

Ví dụ thêm field currency với default trong schema v2 thường tương thích cả hai hướng theo quy tắc Avro:

- Reader v2 đọc record v1: dùng default cho currency.
- Reader v1 đọc record v2: bỏ qua field currency chưa biết.

Vì vậy, thay đổi có thể hỗ trợ cả rollout consumer-first và producer-first.

FULL thường phù hợp khi nhiều phiên bản producer và consumer có thể cùng hoạt động, hoặc thứ tự deploy không thể kiểm soát chặt. Đổi lại, nó hạn chế nhiều kiểu thay đổi schema hơn so với chỉ BACKWARD hoặc FORWARD.

## 6. Bảng so sánh BACKWARD, FORWARD và FULL

| Chế độ | Hướng kiểm tra | Kịch bản được hỗ trợ | Rollout thường dùng |
|---|---|---|---|
| BACKWARD | Schema mới đọc dữ liệu từ schema cũ | Consumer mới đọc record lịch sử | Consumer trước, producer sau |
| FORWARD | Schema cũ đọc dữ liệu từ schema mới | Consumer cũ đọc record mới | Producer trước, consumer sau |
| FULL | Cả hai hướng | Consumer mới đọc dữ liệu cũ và consumer cũ đọc dữ liệu mới | Có thể triển khai hai phía theo nhiều thứ tự hơn |

Một số ví dụ thay đổi Avro điển hình:

| Thay đổi từ v1 sang v2 | BACKWARD | FORWARD | FULL |
|---|---|---|---|
| Thêm field có default | Có | Có | Có |
| Thêm field không có default | Không | Có | Không |
| Xóa field không có default trong v1 | Có thể có | Không | Không |
| Đổi int thành long | Có, nhờ promotion của Avro | Không | Không |
| Đổi tên field không có alias phù hợp | Thường không | Thường không | Không |

Các kết quả trong bảng là ví dụ theo quy tắc resolution của Avro. Với thay đổi xóa field, kết quả forward còn phụ thuộc reader schema cũ có default cho field đó hay không. Các định dạng Protobuf và JSON Schema có quy tắc riêng; không áp dụng máy móc bảng Avro cho mọi format.

## 7. TRANSITIVE nghĩa là gì?

Các chế độ không có hậu tố TRANSITIVE thường kiểm tra schema mới với **phiên bản trước gần nhất** của cùng subject.

Ví dụ subject có lịch sử:

~~~text
v1 -> v2 -> v3
~~~

Khi đăng ký v3:

- BACKWARD kiểm tra v3 với v2.
- FORWARD kiểm tra v2 đọc dữ liệu do v3 ghi.
- FULL kiểm tra cả hai hướng giữa v2 và v3.

Nếu v3 tương thích với v2 nhưng không tương thích với v1, chế độ non-transitive vẫn có thể chấp nhận v3.

Chế độ TRANSITIVE kiểm tra schema mới với **tất cả phiên bản trước đó** của subject:

- BACKWARD_TRANSITIVE: schema mới đọc được dữ liệu từ mọi schema cũ.
- FORWARD_TRANSITIVE: mọi schema cũ đọc được dữ liệu theo schema mới.
- FULL_TRANSITIVE: cả hai hướng được bảo đảm với mọi phiên bản cũ.

### 7.1. Ví dụ vì sao kiểm tra bắc cầu quan trọng

Giả sử:

- v1 có field legacyCode.
- v2 bỏ field legacyCode.
- v3 thay đổi thêm một số field khác.

Nếu v2 có thể đọc v1, nhưng v3 không còn đọc được record v1, thì kiểm tra BACKWARD chỉ với v2 có thể vẫn thành công. Consumer v3 khi replay record lịch sử từ v1 lại thất bại.

BACKWARD_TRANSITIVE kiểm tra v3 với cả v1 và v2, nên có thể phát hiện vấn đề này trước khi đăng ký.

~~~mermaid
flowchart TD
    V1["Schema v1"] --> V2["Schema v2"]
    V2 --> V3["Schema v3"]
    V3 --> L["Non-transitive:<br/>chỉ kiểm tra v2"]
    V3 --> T["Transitive:<br/>kiểm tra v1 và v2"]
    L --> P["Có thể bỏ sót<br/>không tương thích với v1"]
    T --> Q["Phát hiện vấn đề<br/>với lịch sử cũ"]
~~~

### 7.2. Sáu chế độ compatibility có hậu tố transitive

| Chế độ | Kiểm tra |
|---|---|
| BACKWARD | New reader với writer schema của phiên bản trước gần nhất |
| BACKWARD_TRANSITIVE | New reader với mọi writer schema trước đó |
| FORWARD | Reader schema của phiên bản trước gần nhất với new writer |
| FORWARD_TRANSITIVE | Mọi reader schema trước đó với new writer |
| FULL | Backward và forward với phiên bản trước gần nhất |
| FULL_TRANSITIVE | Backward và forward với tất cả phiên bản trước đó |

TRANSITIVE không phải một hướng thứ tư. Nó mở rộng phạm vi phiên bản được kiểm tra cho BACKWARD, FORWARD hoặc FULL.

## 8. Chọn non-transitive hay transitive?

Chọn policy theo thời gian tồn tại của dữ liệu và khả năng consumer phải đọc lại lịch sử.

| Điều kiện vận hành | Gợi ý |
|---|---|
| Consumer chỉ cần đọc dữ liệu tạo bởi phiên bản schema gần nhất | Non-transitive có thể đủ |
| Consumer có thể replay toàn bộ retention | Ưu tiên kiểm tra transitive theo hướng reader cần hỗ trợ |
| Có nhiều phiên bản consumer cùng tồn tại | FULL hoặc policy theo thứ tự rollout |
| Producer mới cần được triển khai trước consumer cũ | Cần FORWARD theo phạm vi phiên bản phù hợp |
| Consumer mới cần đọc toàn bộ lịch sử cũ | Cần BACKWARD_TRANSITIVE |
| Cả producer cũ và consumer mới đều phải hoạt động với mọi dữ liệu lịch sử | Cân nhắc FULL_TRANSITIVE |

Transitive thường chặt hơn và có thể từ chối một thay đổi mà non-transitive cho phép. Đây là chủ đích nếu hệ thống cần replay lâu dài hoặc có consumer cũ còn hoạt động.

Không phải cứ FULL_TRANSITIVE là luôn tốt nhất. Policy quá chặt có thể làm việc tiến hóa schema khó khăn. Hãy xác định rõ consumer nào cần đọc dữ liệu cũ, producer nào còn phát schema cũ và retention/replay horizon của topic.

## 9. Compatibility được áp dụng theo subject

Schema Registry thường quản lý schema theo subject. Với Confluent Schema Registry, naming strategy quyết định subject nào được dùng để lưu version và kiểm tra compatibility.

Các chiến lược phổ biến:

| Strategy | Cách đặt subject | Ý nghĩa |
|---|---|---|
| TopicNameStrategy | orders-key hoặc orders-value | Mỗi topic có subject riêng cho key và value; là mặc định phổ biến |
| RecordNameStrategy | Tên đầy đủ của record/type | Các topic có thể chia sẻ subject theo record name |
| TopicRecordNameStrategy | Kết hợp topic và record name | Cùng record name trên topic khác có subject riêng |

Ví dụ topic orders có hai subject:

- orders-key
- orders-value

Compatibility của key và value có thể được cấu hình riêng. Một thay đổi value schema không nhất thiết ảnh hưởng key subject.

### 9.1. Subject-level và global policy

Schema Registry có thể có cấu hình compatibility mặc định toàn registry và cấu hình override theo subject. Khi điều tra một subject, cần kiểm tra cấu hình hiệu lực của chính subject đó thay vì chỉ xem global default.

Một schema ID có thể được tái sử dụng khi cùng schema được đăng ký ở nhiều subject, nhưng subject version và compatibility policy vẫn là khái niệm riêng. Không nhầm schema ID với version number của subject.

## 10. Compatibility phụ thuộc định dạng schema

Schema Registry hỗ trợ nhiều định dạng; mỗi định dạng có quy tắc tương thích riêng.

### 10.1. Avro

Avro sử dụng writer/reader schema resolution. Một số quy tắc quan trọng:

- Thêm field vào reader schema thường cần default để đọc dữ liệu cũ không có field đó.
- Reader có thể bỏ qua field có trong writer nhưng không có trong reader.
- Avro hỗ trợ một số type promotion, ví dụ int lên long.
- Alias có thể hỗ trợ một số thay đổi tên.
- Enum và union có quy tắc resolution riêng.

Ví dụ thêm field với default là thay đổi phổ biến để đạt backward compatibility.

### 10.2. Protobuf

Protobuf dùng field number trong wire format. Một số nguyên tắc quan trọng:

- Không tái sử dụng field number đã xóa.
- Khi bỏ field, nên đánh dấu field number và tên vào reserved.
- Tránh thay đổi field number.
- Tránh đổi sang wire type không tương thích.
- Thêm field mới với số field mới thường an toàn hơn việc tái sử dụng field cũ.

Ví dụ:

~~~protobuf
message Order {
  string order_id = 1;
  double amount = 2;

  reserved 3;
  reserved "legacy_code";

  string currency = 4;
}
~~~

### 10.3. JSON Schema

JSON Schema compatibility phụ thuộc các keyword và cách validator áp dụng schema, chẳng hạn:

- required
- properties
- additionalProperties
- type
- enum
- oneOf và anyOf

Ví dụ, thêm một property tùy chọn thường ít rủi ro hơn thêm property mới vào danh sách required. Tuy nhiên, additionalProperties: false có thể khiến việc thêm field ảnh hưởng consumer/validator cũ. Cần kiểm tra bằng đúng Schema Registry và phiên bản validator.

Không suy luận compatibility chỉ từ việc JSON vẫn parse được. JSON hợp lệ về cú pháp chưa chắc hợp lệ theo schema hoặc giữ đúng ý nghĩa nghiệp vụ.

## 11. Cấu hình compatibility trong Schema Registry

Có thể đặt policy cho một subject bằng REST API:

~~~bash
curl -X PUT \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  --data '{"compatibility":"BACKWARD_TRANSITIVE"}' \
  http://localhost:8081/config/orders-value
~~~

Đọc cấu hình của subject:

~~~bash
curl -X GET \
  http://localhost:8081/config/orders-value
~~~

Đọc cấu hình mặc định toàn registry:

~~~bash
curl -X GET \
  http://localhost:8081/config
~~~

Endpoint và content type có thể thay đổi theo sản phẩm/phiên bản; kiểm tra tài liệu Schema Registry đang triển khai.

Không đặt policy quá rộng cho toàn registry nếu các subject có yêu cầu khác nhau. Có thể đặt global default an toàn rồi override có chủ đích cho từng subject.

## 12. Kiểm tra compatibility trước khi đăng ký schema mới

Schema Registry cung cấp API kiểm tra compatibility của schema candidate với subject. Ví dụ endpoint kiểm tra với phiên bản latest:

~~~bash
curl -X POST \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  --data @candidate-schema.json \
  http://localhost:8081/compatibility/subjects/orders-value/versions/latest
~~~

File request có thể chứa schema candidate theo format API, ví dụ với Avro:

~~~json
{
  "schemaType": "AVRO",
  "schema": "{\"type\":\"record\",\"name\":\"Order\",\"namespace\":\"com.example\",\"fields\":[{\"name\":\"orderId\",\"type\":\"string\"},{\"name\":\"amount\",\"type\":\"double\"},{\"name\":\"currency\",\"type\":\"string\",\"default\":\"VND\"}]}"
}
~~~

Kết quả thường có trường is_compatible và thông tin lỗi nếu không tương thích. Endpoint kiểm tra với latest không tự thay thế kiểm tra transitive nếu muốn xác minh toàn bộ lịch sử; hãy cấu hình policy transitive hoặc dùng endpoint/option tương ứng với phiên bản Registry để kiểm tra theo phạm vi cần thiết.

Quy trình CI/CD nên:

1. Lấy schema candidate từ source control.
2. Xác định subject chính xác theo naming strategy.
3. Đọc compatibility policy hiệu lực.
4. Gọi API compatibility check.
5. Chặn merge/release nếu schema không tương thích theo policy.
6. Chỉ đăng ký schema sau khi kiểm tra thành công.
7. Chạy contract test với fixture dữ liệu của các phiên bản trước.

Kiểm tra schema trước khi deploy producer giúp phát hiện lỗi sớm, nhưng vẫn cần test serializer/deserializer và ứng dụng thật.

## 13. Quy trình rollout producer và consumer

Compatibility policy quyết định thứ tự rollout an toàn.

### 13.1. Khi dùng BACKWARD

Vì consumer mới đọc được dữ liệu cũ:

1. Deploy consumer mới.
2. Xác nhận consumer mới đọc dữ liệu đang tồn tại.
3. Deploy producer mới phát schema mới.
4. Theo dõi lỗi deserialize và lag.

Đây là chiến lược consumer-first.

### 13.2. Khi dùng FORWARD

Vì consumer cũ đọc được dữ liệu mới:

1. Xác nhận consumer cũ đọc được record theo schema mới.
2. Deploy producer mới.
3. Theo dõi consumer cũ trong giai đoạn chuyển tiếp.
4. Deploy consumer mới sau đó.

Đây là chiến lược producer-first.

### 13.3. Khi dùng FULL

Cả consumer mới đọc dữ liệu cũ và consumer cũ đọc dữ liệu mới. Rollout linh hoạt hơn, nhưng vẫn cần kiểm tra logic nghiệp vụ và các phiên bản thực tế đang chạy.

### 13.4. Khi cần replay lịch sử

Nếu consumer mới có thể replay record từ nhiều phiên bản schema, hãy đánh giá BACKWARD_TRANSITIVE. Nếu cần consumer cũ đọc dữ liệu mới từ producer mới qua nhiều thế hệ, hãy đánh giá FORWARD_TRANSITIVE.

FULL_TRANSITIVE phù hợp khi cần cả hai hướng trên toàn bộ lịch sử, nhưng cũng giới hạn các thay đổi phá vỡ compatibility mạnh hơn.

## 14. Compatibility không bảo đảm đúng nghĩa nghiệp vụ

Một schema có thể tương thích về cấu trúc nhưng thay đổi ý nghĩa field.

Ví dụ:

- amount trước đây là VND, nay lại được ghi bằng USD nhưng vẫn dùng kiểu double.
- status="PAID" được diễn giải thành "đã yêu cầu thanh toán" thay vì "đã thanh toán thành công".
- Timestamp trước đây là milliseconds, nay chuyển thành seconds nhưng vẫn dùng kiểu long.
- customerId giữ nguyên kiểu string nhưng thay đổi namespace hoặc quy tắc định danh.

Schema compatibility có thể không phát hiện các thay đổi ngữ nghĩa này. Cần contract test, tài liệu event, semantic versioning hoặc event type/version mới khi ý nghĩa thay đổi không tương thích.

Không dùng compatibility check như bằng chứng duy nhất rằng release an toàn. Nó kiểm tra khả năng đọc theo quy tắc schema, không xác minh toàn bộ hành vi ứng dụng.

## 15. Khi cần breaking change

Nếu thay đổi không thể giữ backward/forward compatibility, có thể dùng một kế hoạch migration có kiểm soát:

- Tạo event type hoặc subject mới cho hợp đồng mới.
- Có thể tạo topic version mới nếu ranh giới hợp đồng cần tách rõ.
- Triển khai consumer mới đọc cả dữ liệu cũ và mới hoặc chạy hai pipeline song song.
- Nếu cần, dùng adapter/upcaster để chuyển schema cũ sang model nội bộ mới.
- Chuyển producer sang hợp đồng mới sau khi consumer sẵn sàng.
- Theo dõi và dừng luồng cũ sau khi hết retention/replay horizon và các consumer cũ đã được gỡ bỏ.

Không chỉnh sửa lịch sử đã ghi để làm cho schema mới "trông tương thích". Event lịch sử phải được đọc theo writer schema đã dùng khi nó được tạo.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Schema mới bị từ chối | Không tương thích theo policy của subject | Xem lỗi Registry và kiểm tra reader/writer direction |
| CI pass nhưng consumer replay lịch sử lỗi | Chỉ kiểm tra latest, trong khi cần transitive | Dùng BACKWARD_TRANSITIVE hoặc test mọi schema lịch sử |
| Producer mới chạy được nhưng consumer cũ lỗi | Chọn BACKWARD nhưng rollout producer-first | Kiểm tra FORWARD hoặc đổi thứ tự rollout |
| Consumer mới không đọc được record cũ | Chỉ kiểm tra FORWARD | Kiểm tra BACKWARD và writer schema lịch sử |
| Subject có policy khác global | Subject-level override | Đọc cấu hình của đúng subject |
| Key schema thay đổi nhưng value schema không đổi | Đang kiểm tra nhầm subject | Kiểm tra subject key và subject value tương ứng |
| JSON parse được nhưng deserialize/schema validation thất bại | Cú pháp JSON không đồng nghĩa schema-compatible | Kiểm tra JSON Schema và validator |
| Protobuf không tương thích sau khi xóa field | Field number được tái sử dụng hoặc wire type thay đổi | Reserve số và tên field đã xóa |
| Schema tương thích nhưng nghiệp vụ sai | Ý nghĩa field thay đổi mà cấu trúc không đổi | Contract test và version event/semantics |

## 17. Checklist chọn compatibility policy

- [ ] Đã xác định writer schema và reader schema trong từng hướng.
- [ ] Đã phân biệt BACKWARD, FORWARD và FULL.
- [ ] Đã xác định kiểm tra latest hay tất cả phiên bản trước.
- [ ] Policy transitive phù hợp với retention và replay horizon.
- [ ] Đã kiểm tra đúng subject theo naming strategy.
- [ ] Đã kiểm tra subject-level override và global default.
- [ ] Thay đổi Avro có default/alias/type promotion phù hợp.
- [ ] Protobuf không tái sử dụng field number và đã reserve field bị xóa.
- [ ] JSON Schema được kiểm tra với required/properties/additionalProperties thực tế.
- [ ] CI gọi compatibility API trước khi đăng ký hoặc phát schema mới.
- [ ] Đã test consumer với fixture từ các phiên bản schema cũ.
- [ ] Thứ tự rollout producer/consumer phù hợp hướng compatibility.
- [ ] Đã kiểm tra semantic contract, không chỉ cấu trúc schema.
- [ ] Breaking change có kế hoạch migration và replay riêng.

BACKWARD, FORWARD và FULL mô tả hướng reader/writer mà các phiên bản schema hỗ trợ. TRANSITIVE mở rộng phép kiểm tra từ phiên bản gần nhất sang toàn bộ lịch sử của subject. Chọn đúng policy cần dựa trên thứ tự rollout, phiên bản consumer còn hoạt động và thời gian dữ liệu phải replay được. Schema Registry giúp chặn nhiều thay đổi cấu trúc không an toàn, nhưng contract test và kiểm tra ý nghĩa nghiệp vụ vẫn cần thiết để bảo đảm producer, consumer và dữ liệu lịch sử cùng hoạt động đúng.
