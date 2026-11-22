# Kiểm thử schema và khả năng tương thích thông điệp

**Chủ đề:** Chiến lược kiểm thử trong kiến trúc hệ thống và microservices.

Trong kiến trúc microservices, các dịch vụ có thể giao tiếp qua Kafka, RabbitMQ, hệ thống hàng đợi đám mây hoặc các luồng sự kiện khác. Một producer xuất bản thông điệp, còn một hay nhiều consumer đọc và xử lý. Hai phía thường được triển khai độc lập: producer có thể lên phiên bản mới trong khi consumer vẫn chạy bản cũ, hoặc consumer mới phải đọc những thông điệp đã lưu từ nhiều tháng trước.

Ví dụ, Order Service đang phát sự kiện OrderCreated có hai trường orderId và totalAmount. Phiên bản mới thêm currency, đổi tên totalAmount thành amount, rồi thay biểu diễn số tiền từ số thập phân sang số nguyên tính bằng đơn vị nhỏ nhất. Mỗi thay đổi có vẻ nhỏ ở phía producer, nhưng consumer có thể đọc sai, bỏ sự kiện, tính tiền sai hoặc ngừng xử lý cả partition. **Kiểm thử schema và khả năng tương thích thông điệp** giúp phát hiện loại rủi ro này trước khi phát hành và trong suốt vòng đời triển khai.

Bài học đi từ khái niệm đến ví dụ, thiết kế bộ test có chủ đích, tự động hóa trong CI/CD, phương pháp nâng phiên bản an toàn và kiểm chứng sự cố. Các ví dụ minh họa dùng JSON, Avro, Protocol Buffers và Java; nguyên tắc cốt lõi áp dụng cho cả hệ thống truyền sự kiện và hệ thống truyền lệnh bất đồng bộ.

## 1. Mô hình tư duy: thông điệp là hợp đồng giữa các phiên bản phần mềm

Một sự kiện không chỉ là một chuỗi byte trên broker. Nó mang hợp đồng giữa bên tạo và bên sử dụng:

~~~mermaid
flowchart LR
    P1["Producer v1"] --> B[("Broker / Topic")]
    P2["Producer v2"] --> B
    B --> C1["Consumer v1"]
    B --> C2["Consumer v2"]
    B --> R["Consumer phát lại dữ liệu cũ"]
~~~

Tại cùng một thời điểm, hệ thống có thể tồn tại **nhiều phiên bản writer và reader**. Broker thường chỉ lưu hoặc chuyển tiếp byte; broker không tự bảo đảm rằng ứng dụng nhận hiểu đúng nội dung nghiệp vụ.

Hợp đồng thông điệp thường có bốn lớp:

1. **Hình dạng dữ liệu (schema):** những trường nào xuất hiện, kiểu dữ liệu, bắt buộc/tùy chọn, cấu trúc lồng nhau, enum, số hiệu trường và định dạng tuần tự hóa.
2. **Ngữ nghĩa (semantics):** mỗi trường có nghĩa gì, đơn vị đo, trạng thái hợp lệ, quy tắc diễn giải và thời điểm sự kiện được phát.
3. **Giao thức phân phối:** topic/queue, key, routing, consumer group, thứ tự, số lần giao, deadline, retry, DLQ và retention.
4. **Hợp đồng tiến hóa:** phiên bản nào đọc được thông điệp của phiên bản nào, khi nào được bỏ trường cũ, ứng dụng cần triển khai theo thứ tự nào.

Kiểm thử schema chỉ bao phủ tốt lớp thứ nhất. **Tương thích thực tế** còn cần kiểm tra ba lớp còn lại. Schema registry trả kết quả hợp lệ chưa chứng minh business behavior không đổi.

## 2. Phân biệt schema validation, compatibility và contract testing

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Schema validation** | Payload này có khớp định dạng đang khai báo không? | amountMinor phải là số nguyên, orderId phải có |
| **Schema compatibility** | Reader mới/cũ có thể giải mã writer mới/cũ không? | Consumer mới đọc được bản ghi cũ thiếu trường tùy chọn |
| **Contract testing** | Producer có xuất bản đúng điều consumer cần, với ý nghĩa đã thống nhất không? | Sự kiện PaymentCompleted chỉ phát sau khi thanh toán đã xác nhận |
| **Integration testing** | Khi đi qua thư viện, serializer, broker và handler thật, luồng có hoạt động không? | Producer phát Avro; consumer deserialize và commit offset |
| **End-to-end testing** | Một kịch bản nghiệp vụ xuyên các dịch vụ vẫn đúng không? | Tạo đơn → thanh toán → cập nhật trạng thái đơn |

Các mức kiểm thử bổ trợ nhau. Schema test rẻ, nên chạy thường xuyên. Integration test ít trường hợp hơn nhưng bắt được lỗi cấu hình serializer, subject naming, registry và quyền broker. End-to-end test kiểm tra luồng tổng thể nhưng thường không chỉ rõ vị trí lỗi tương thích.

**Đầu ra của bài học:** một ma trận phiên bản có thể chạy tự động, bộ fixture mô tả dữ liệu cũ/mới, kiểm tra ngữ nghĩa nghiệp vụ và phương án triển khai/rollback gắn với loại thay đổi.

## 3. Writer schema và reader schema

Hãy phân biệt:

- **Writer schema:** cách producer tạo byte trên đường truyền hoặc trong bản ghi đã lưu.
- **Reader schema:** cách consumer giải mã và diễn giải những byte đó.

Đối với Avro, quá trình giải mã có thể dùng **schema resolution** giữa writer schema và reader schema. Đối với JSON, parser và validator thường dựa trên schema hoặc DTO do ứng dụng lựa chọn; không có một cơ chế reader/writer resolution phổ quát áp dụng tự động cho mọi thư viện JSON. Đối với Protobuf, việc hiểu trường chủ yếu dựa vào **field number + wire type**, chứ không chỉ dựa vào tên trường trong source code.

Tình huống cần bảo vệ không chỉ là producer v2 gặp consumer v2. Cần xét:

~~~text
                Reader v1        Reader v2
Writer v1       cơ sở            nâng consumer trước
Writer v2       nâng producer    trạng thái mục tiêu
                 trước
~~~

Nếu broker còn giữ dữ liệu do writer v1 tạo, reader v2 cần xử lý được dữ liệu cũ ngay cả khi tất cả producer hiện tại đã nâng lên v2. Nếu triển khai rolling, writer v2 có thể gửi dữ liệu cho reader v1 trong thời gian chuyển đổi.

## 4. Backward, forward, full và khả năng tương thích bắc cầu

Đây là các thuật ngữ dễ bị dùng ngược. Luôn ghi rõ **ai đọc dữ liệu của ai**.

| Chế độ | Ý nghĩa trực tiếp giữa phiên bản mới và trước đó | Tình huống triển khai thường thuận lợi |
|---|---|---|
| **Backward compatible** | **Reader mới** đọc được dữ liệu từ **writer cũ** | Nâng consumer trước, rồi producer |
| **Forward compatible** | **Reader cũ** đọc được dữ liệu từ **writer mới** | Nâng producer trước, nhưng phải xét consumer chưa nâng |
| **Full compatible** | Cả reader mới ↔ writer cũ và reader cũ ↔ writer mới đều hoạt động | Triển khai lệch phiên bản theo nhiều hướng |
| **None** | Không kiểm tra điều kiện tương thích tương ứng | Chỉ dùng khi có kiểm soát thay đổi và phạm vi rủi ro rõ |

Ở nhiều schema registry, tên chế độ không có hậu tố **TRANSITIVE** thường so với phiên bản gần nhất theo quy tắc của công cụ; các chế độ **BACKWARD_TRANSITIVE**, **FORWARD_TRANSITIVE** hoặc **FULL_TRANSITIVE** kiểm tra với nhiều phiên bản trước đó. Cơ chế và tên chế độ thực tế phụ thuộc sản phẩm.

Ví dụ, chuỗi v1 → v2 → v3 có thể vượt qua những lần kiểm tra với phiên bản gần nhất nhưng v3 lại không giải mã được dữ liệu v1 còn trong retention. Vì vậy, quyết định có cần kiểm tra bắc cầu phải dựa trên **thời gian lưu dữ liệu, replay, consumer lâu không nâng cấp và việc tái xử lý từ đầu**.

**Không diễn giải “backward” là rollback code luôn an toàn.** Backward chỉ bảo đảm reader **mới** xử lý writer **cũ** theo phép kiểm tra tương ứng. Nếu rollback consumer về reader cũ sau khi producer mới đã phát dữ liệu, điều kiện cần thường là **forward** hoặc một kế hoạch chuyển đổi khác.

## 5. Ví dụ sự kiện OrderCreated phiên bản đầu

Giả sử nghiệp vụ ban đầu dùng JSON:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "orderId": "ord-123",
  "amountMinor": 125000,
  "currency": "VND",
  "occurredAt": "2026-11-12T02:00:00Z"
}
~~~

Consumer đọc orderId để tìm đơn và amountMinor để tính tổng tiền. amountMinor dùng **đơn vị nhỏ nhất của tiền tệ theo hợp đồng ứng dụng**; ví dụ này biểu diễn giá trị tiền bằng một số nguyên, tránh giả định floating point phù hợp cho mọi phép tính tiền.

Một mô tả hợp đồng phải làm rõ:

- Tên sự kiện **OrderCreated** có nghĩa đơn đã được ghi bền vững ở trạng thái nào?
- eventId duy nhất trong phạm vi nào, dùng để chống xử lý trùng thế nào?
- orderId có được phép null/rỗng không, có giới hạn độ dài không?
- amountMinor có được âm không, có trường hợp hoàn tiền không?
- currency dùng mã tiền tệ nào và có phải luôn là VND không?
- occurredAt là thời điểm nghiệp vụ xảy ra hay thời điểm gửi qua broker?
- Khi hai sự kiện về cùng orderId đến sai thứ tự, consumer xử lý thế nào?

Kiểu dữ liệu hợp lệ là điều kiện cần; một thông điệp có amountMinor = -999999 có thể là JSON đúng kiểu nhưng sai hợp đồng nghiệp vụ.

## 6. Thay đổi schema nào thường an toàn, thay đổi nào có rủi ro?

Bảng dưới đây chỉ là **định hướng ban đầu**. Mức an toàn thực tế phụ thuộc format, serializer, chế độ registry, cách consumer đọc trường lạ và ý nghĩa nghiệp vụ.

| Thay đổi | Rủi ro điển hình | Điều kiện kiểm thử |
|---|---|---|
| Thêm trường tùy chọn có default rõ ràng | Reader cũ từ chối trường lạ; reader mới không có giá trị khi replay cũ | Test cả v1 → v2 và v2 → v1 |
| Thêm trường bắt buộc | Dữ liệu cũ thiếu giá trị; producer cũ không phát được | Cần transition hoặc adapter |
| Xóa trường | Consumer cũ còn sử dụng | Kiểm tra mọi consumer, retention và replay |
| Đổi tên trường | Reader cũ thấy trường biến mất | Alias hoặc giai đoạn dual field nếu format hỗ trợ |
| Đổi kiểu dữ liệu | Deserializer lỗi hoặc mất độ chính xác | Test serializer thực tế và ranh giới giá trị |
| Đổi đơn vị tiền/tốc độ/thời gian | Có thể đọc được nhưng xử lý sai | Kiểm thử ngữ nghĩa và dữ liệu biên |
| Thêm enum value | Consumer cũ không nhận ra trạng thái | Test unknown enum, default và nhánh xử lý |
| Đổi eventType / topic | Consumer không tìm thấy sự kiện | Kiểm tra định tuyến, migration và versioning |
| Đổi key/partition | Thứ tự theo aggregate hoặc độ phân phối bị ảnh hưởng | Integration test về ordering và consumer behavior |
| Đổi thời điểm phát event | Schema không đổi nhưng ý nghĩa khác | Contract test theo trạng thái nghiệp vụ |

**Ví dụ lỗi ngầm:** giữ tên **amount** và kiểu number, nhưng producer thay giá trị từ “đồng” sang “xu”. Schema checker có thể không phát hiện gì. Consumer vẫn parse được nhưng tính phí sai 100 lần. Đó là thay đổi **ngữ nghĩa phá vỡ hợp đồng**, phải được kiểm tra bằng fixture có giá trị cụ thể và một bước đổi tên/phiên bản rõ ràng.

## 7. Avro: ví dụ thêm trường có default và kiểm tra thực tế

Avro mô tả record với schema có kiểu. Phiên bản v1:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "example.orders",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amountMinor", "type": "long"}
  ]
}
~~~

Phiên bản v2 bổ sung nguồn bán hàng:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "example.orders",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amountMinor", "type": "long"},
    {"name": "salesChannel", "type": ["null", "string"], "default": null}
  ]
}
~~~

Ở ví dụ này:

- **Reader v2 + writer v1:** writer cũ không có salesChannel; reader mới có thể dùng default null theo quy tắc schema resolution của Avro. Đây là phép kiểm thử backward quan trọng.
- **Reader v1 + writer v2:** reader cũ có thể bỏ qua trường mới nếu serializer/deserializer thực hiện resolution chuẩn và các trường còn lại tương thích. Đây là hướng forward cần kiểm thử.
- Nếu **salesChannel** mới được thêm mà reader v2 không có default phù hợp, việc giải mã dữ liệu v1 có thể thất bại.
- Với union như **["null","string"]**, default phải tuân thủ quy tắc Avro và khớp nhánh tương ứng; đừng mặc định một null trong JSON đồng nghĩa schema hợp lệ.
- Thay **amountMinor** từ long sang string không phải điều nên coi là tương thích chỉ vì cả hai có thể biểu diễn con số dưới dạng chữ.

**Điểm thường bị hiểu nhầm:** default trong reader schema giúp lấp trường thiếu khi đọc dữ liệu cũ; nó không nhất thiết là “giá trị producer tự gửi” khi producer dùng schema mới. Bằng chứng phải đến từ phép serialize/deserialize bằng thư viện đang chạy, không chỉ nhìn JSON mô tả.

### 7.1. Đổi tên trường trong Avro

Avro hỗ trợ cơ chế alias khi resolution trong những trường hợp phù hợp. Tuy nhiên, khả năng tên cũ được map sang tên mới phụ thuộc vào cách schema reader/writer được cung cấp và thư viện sử dụng. Ngoài ra, đổi tên có thể ảnh hưởng consumer không dùng Avro resolution, hệ thống kiểm toán hoặc pipeline chuyển đổi sang JSON. Vì vậy, đừng xem alias là cách thay thế kiểm thử xuyên phiên bản.

Với dữ liệu quan trọng, có thể dùng giai đoạn trung gian giữ cả trường cũ và mới, rồi từng bước chuyển consumer. Khi hai trường cùng tồn tại, phải kiểm thử chúng luôn phản ánh cùng giá trị và xác định trường nào là nguồn chuẩn trong mỗi giai đoạn.

## 8. Protobuf: field number quan trọng hơn tên

Trong Protocol Buffers, số hiệu trường là một phần cốt lõi của định dạng nhị phân. Ví dụ:

~~~proto
syntax = "proto3";
package example.orders;

message OrderCreated {
  string order_id = 1;
  int64 amount_minor = 2;
}
~~~

Phiên bản sau thêm trường:

~~~proto
syntax = "proto3";
package example.orders;

message OrderCreated {
  string order_id = 1;
  int64 amount_minor = 2;
  optional string sales_channel = 3;
}
~~~

Các nguyên tắc cần ghi nhớ:

1. **Không tái sử dụng field number** cho một ý nghĩa khác. Nếu xóa trường, có thể dùng **reserved** để tránh tái sử dụng số hiệu và tên không phù hợp.
2. **Thêm field number mới** thường cho phép reader cũ bỏ qua trường không biết ở cấp binary wire, nhưng ứng dụng và tuyến chuyển đổi vẫn cần kiểm thử.
3. **Đổi tên nhưng giữ số hiệu** có thể không làm thay đổi wire format nhị phân, song JSON mapping, reflection, code generated và ngữ nghĩa có thể bị ảnh hưởng.
4. **Đổi kiểu** không nhất thiết an toàn; hai kiểu có thể cùng wire type nhưng diễn giải khác, ví dụ signedness, encoding hoặc giới hạn giá trị.
5. **Default và presence trong proto3** cần hiểu rõ: chuỗi rỗng, số 0 và trường không xuất hiện có thể khó phân biệt nếu không dùng cơ chế presence phù hợp.
6. **oneof, enum và repeated field** cần test cụ thể; không giả định đổi cardinality hoặc thêm giá trị enum luôn an toàn với nhánh nghiệp vụ của consumer.
7. **Unknown fields** có thể được giữ qua một số luồng giải mã/serialize nhị phân, nhưng có thể mất khi chuyển sang JSON hoặc khi code chủ động dựng lại message. Hãy thử pipeline thực tế.

Ví dụ khi xóa trường number 3:

~~~proto
message OrderCreated {
  string order_id = 1;
  int64 amount_minor = 2;
  reserved 3;
  reserved "sales_channel";
}
~~~

Với Protobuf, một thay đổi kiểm thử thành công qua binary serializer chưa chắc đúng khi message còn đi qua HTTP JSON transcoding hoặc một data warehouse chỉ đọc tên trường. Phải vẽ rõ tất cả dạng biểu diễn trung gian.

## 9. JSON Schema: required, optional và chính sách trường lạ

Với JSON, có thể khai báo schema:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "eventId": {"type": "string", "minLength": 1},
    "eventType": {"const": "OrderCreated"},
    "orderId": {"type": "string", "minLength": 1},
    "amountMinor": {"type": "integer", "minimum": 0},
    "currency": {"type": "string", "minLength": 3, "maxLength": 3},
    "salesChannel": {"type": ["string", "null"]}
  },
  "required": ["eventId", "eventType", "orderId", "amountMinor", "currency"],
  "additionalProperties": true
}
~~~

Trong schema trên, salesChannel không có trong **required**, nên payload cũ có thể bỏ qua trường này. **additionalProperties: true** cho phép trường lạ qua lớp schema validator, nhưng DTO của consumer vẫn có thể từ chối trường lạ nếu cấu hình deserializer nghiêm ngặt.

Nếu chuyển **additionalProperties** từ true sang false, một consumer có thể bắt đầu từ chối thông điệp có trường ngoài danh sách. Đây là thay đổi cần kiểm tra với dữ liệu thực và các phiên bản producer còn hoạt động.

Lưu ý: quy tắc **default** trong JSON Schema chủ yếu mô tả giá trị mặc định theo đặc tả, không phải cam kết mọi validator sẽ tự thêm trường vào payload. Nếu nghiệp vụ cần lấp mặc định, consumer phải triển khai hành vi đó hoặc dùng công cụ cụ thể có hỗ trợ và kiểm thử nó.

JSON Schema có nhiều draft, quy tắc về nullable, format, unevaluatedProperties và cách xử lý $ref; schema, validator và công cụ registry phải dùng các phiên bản hỗ trợ tương ứng. Đừng trộn cú pháp giữa các draft rồi coi kết quả một validator là chuẩn cho mọi consumer.

## 10. Event envelope: phân biệt metadata của sự kiện và dữ liệu nghiệp vụ

Một envelope nhất quán giúp consumer xác định loại thông điệp, phiên bản và nguồn xử lý:

~~~json
{
  "eventId": "evt-72f1",
  "eventType": "OrderCreated",
  "eventVersion": 2,
  "occurredAt": "2026-11-12T02:00:00Z",
  "producer": "order-service",
  "correlationId": "checkout-991",
  "aggregateId": "ord-991",
  "payload": {
    "orderId": "ord-991",
    "amountMinor": 125000,
    "currency": "VND",
    "salesChannel": "WEB"
  }
}
~~~

Cần định nghĩa rõ:

- **eventVersion** là phiên bản hợp đồng nghiệp vụ hay chỉ phiên bản schema?
- **schema ID** nếu serializer/registry dùng ID nằm trong wire format thì lưu ở đâu?
- **eventId** có ổn định qua retry, redelivery và replay không?
- **aggregateId** có dùng làm partition key để giữ thứ tự theo đơn hàng không?
- **occurredAt** là thời điểm transaction commit, phát sự kiện hay broker nhận?
- **producer** do bên phát tự khai báo hay được ràng buộc bằng danh tính đã xác thực?
- **correlationId/traceId** dùng để nối luồng quan sát, có giới hạn dữ liệu nhạy cảm không?

Không nên tự điền eventVersion=2 rồi bỏ qua việc đăng ký/kiểm tra schema; cũng không nên coi text **producer: order-service** là bằng chứng xác thực. Metadata trợ giúp diễn giải, còn quyền nguồn phát thuộc lớp bảo mật broker và ứng dụng.

Nếu dùng schema ID trong header hoặc payload, consumer phải có cách lấy schema phù hợp ngay cả khi registry gặp sự cố; có thể dùng cache có quản lý, nhưng cần chính sách khi cache thiếu hoặc quá cũ.

## 11. Schema registry: kiểm tra ở cổng công bố, không dừng ở cổng công bố

Schema Registry hoặc một kho contract có phiên bản giúp:

- Lưu schema bất biến hoặc có lịch sử thay đổi theo subject/resource.
- Liên hệ một schema với schema ID, version hoặc nội dung chuẩn hóa.
- Chạy compatibility check khi đăng ký bản mới.
- Giới hạn ai được đăng ký, sửa cấu hình kiểm tra hay xóa schema.
- Cung cấp schema cho serializer/deserializer hoặc công cụ phát lại.

Một luồng thường gặp:

~~~text
Developer thay schema
    |
    v
Kiểm tra cú pháp + generate code
    |
    v
Compatibility check với lịch sử đăng ký
    |
    +-- Bị từ chối -> sửa schema / lên kế hoạch migration
    |
    v
Chạy contract test với fixture producer/consumer
    |
    v
Đăng ký schema theo quy trình có quyền
    |
    v
Canary/rollout producer-consumer + quan sát
~~~

**Điểm cần xác định rõ:** subject naming strategy. Một subject có thể gắn với topic, bản ghi hoặc tổ hợp topic + record, tùy hệ sinh thái và serializer. Nếu đổi chiến lược đặt tên mà không kiểm soát, ứng dụng có thể đăng ký schema mới dưới subject khác và “vượt” kiểm tra lịch sử cũ.

Bộ kiểm tra compatibility ở registry thường xem **cấu trúc schema theo quy tắc của format**; nó không biết producer có đổi đơn vị tiền, bỏ phát một event bắt buộc, đổi thời điểm publish hoặc sửa partition key. Vì vậy phải kết hợp với test ở code.

Bảo vệ API registry giống một phần của hạ tầng quan trọng: TLS, xác thực, RBAC, audit, hạn quyền xóa hoặc thay compatibility mode. Không để mọi ứng dụng tự đổi policy sang NONE chỉ để build qua.

## 12. Ma trận tương thích: biến chữ “compatible” thành bộ ca kiểm thử

Giả sử có writer **W1, W2** và reader **R1, R2**. Tạo ma trận có dữ liệu đầu vào, đường giải mã và kết quả nghiệp vụ.

| Writer | Reader | Ca tối thiểu | Kết quả mong đợi |
|---|---|---|---|
| W1 | R1 | Dữ liệu nền | Đọc và xử lý đúng |
| W1 | R2 | Replay dữ liệu cũ | Reader mới dùng default/adapter đúng |
| W2 | R1 | Consumer chưa nâng | Đọc được hoặc được cô lập theo kế hoạch |
| W2 | R2 | Cùng phiên bản mới | Đọc và xử lý đúng |
| W0 rất cũ | R2 | Retention dài/khôi phục backup | Đọc được khi hợp đồng yêu cầu |
| W2 với dữ liệu không hợp lệ | R2 | Thiếu trường, sai kiểu, sai miền giá trị | Bị từ chối có lý do, không làm kẹt pipeline |

Khi hệ thống còn reader R0 hoặc writer W0, mở rộng ma trận. Không cần lấy tích Descartes của mọi phiên bản đã từng tồn tại nếu chính sách retention và migration chứng minh một số cặp không bao giờ gặp nhau; nhưng điều kiện bỏ một cặp phải được ghi rõ.

Mỗi ô ma trận cần kiểm tra ít nhất:

1. Producer tạo được byte với schema/serializer thực tế.
2. Consumer giải mã và validate được hoặc từ chối đúng theo hợp đồng.
3. Những trường quan trọng giữ đúng giá trị, đơn vị và ý nghĩa.
4. Không có tác dụng phụ lặp khi test redelivery.
5. Lỗi không làm hàng đợi hoặc partition dừng vô thời hạn.
6. Có log/metric đủ nhận biết trường hợp tương thích thất bại.

Khi thêm trường, test đủ ba giá trị: **vắng mặt**, **null nếu được phép**, **giá trị cụ thể**. Một field nullable chưa chắc đồng nghĩa optional trong mọi thư viện hoặc mọi schema.

## 13. Fixture chuẩn: dữ liệu cũ, mới, biên và sai hợp đồng

Các fixture nên là thông điệp thực tế đã serialize bằng writer tương ứng, có thể bổ sung JSON dễ đọc cho người xem. Không chỉ xây fixture bằng object của phiên bản mới rồi giả làm “dữ liệu cũ”, vì serializer mới có thể tự phát những trường mà bản cũ không biết.

Một bộ fixture tối thiểu:

~~~text
fixtures/
  order-created/
    v1/
      valid-basic.json
      valid-zero-amount.json
      valid-old-enum.json
      serialized-event.bin
    v2/
      valid-with-sales-channel.json
      valid-without-optional.json
      valid-unknown-field.json
      serialized-event.bin
    invalid/
      missing-order-id.json
      negative-amount.json
      bad-currency.json
      wrong-event-type.json
      malformed-payload.json
~~~

Fixture nên ghi **writer version, schema ID, thời điểm tạo, ý nghĩa nghiệp vụ**. Với Avro/Protobuf, giữ bản binary đã tạo bằng schema cũ để tránh việc thư viện mới vô tình sửa test data.

Test dữ liệu biên ngoài schema: số nguyên lớn, null, chuỗi Unicode, object lồng nhau, danh sách rỗng, giá trị enum chưa biết, payload quá lớn, timestamp lệch múi giờ, duplicate eventId và message được giao sai thứ tự. Các ranh giới này thường là nơi dữ liệu tương thích về kiểu nhưng hành vi không tương thích.

Với dữ liệu sản xuất được đưa vào fixture, phải khử nhận dạng và loại bí mật. Fixture cần có tính quyết định, có thể chạy offline và phù hợp lưu cùng mã nguồn/test artifact.

## 14. Ví dụ Java: một consumer hiểu cả payload cũ và mới

Một consumer mới cần đọc được event v1 thiếu **salesChannel**, nhưng vẫn từ chối các vi phạm hợp đồng khác. Ví dụ sau dùng Jackson và Java 21; đây là lớp kiểm tra/ánh xạ đơn giản, không phải JSON Schema validator đầy đủ:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Locale;

record OrderCreated(
        String eventId,
        String orderId,
        long amountMinor,
        String currency,
        String salesChannel) {}

final class OrderEventReader {
    private final ObjectMapper mapper = new ObjectMapper();

    OrderCreated read(String rawJson) throws Exception {
        JsonNode root = mapper.readTree(rawJson);

        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("Event must be an object");
        }
        if (!"OrderCreated".equals(text(root, "eventType"))) {
            throw new IllegalArgumentException("Unexpected event type");
        }

        String eventId = requiredText(root, "eventId");
        String orderId = requiredText(root, "orderId");
        String currency = requiredText(root, "currency");

        JsonNode amount = root.get("amountMinor");
        if (amount == null || !amount.isIntegralNumber()
                || !amount.canConvertToLong()) {
            throw new IllegalArgumentException("amountMinor must be int64");
        }
        long amountMinor = amount.longValue();
        if (amountMinor < 0) {
            throw new IllegalArgumentException("amountMinor must be >= 0");
        }
        if (currency.length() != 3
                || !currency.equals(currency.toUpperCase(Locale.ROOT))) {
            throw new IllegalArgumentException("Invalid currency");
        }

        // Trường mới không có ở v1: gán giá trị nghiệp vụ đã quy định.
        String salesChannel = root.hasNonNull("salesChannel")
                ? requiredText(root, "salesChannel")
                : "UNKNOWN";

        return new OrderCreated(
                eventId, orderId, amountMinor, currency, salesChannel);
    }

    private String text(JsonNode root, String field) {
        JsonNode value = root.get(field);
        return value != null && value.isTextual() ? value.textValue() : null;
    }

    private String requiredText(JsonNode root, String field) {
        String value = text(root, field);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing/invalid " + field);
        }
        return value;
    }
}
~~~

Lớp đọc này **chấp nhận trường lạ** vì chỉ lấy các trường đã biết, phù hợp chiến lược mở rộng cấu trúc trong ví dụ. Tuy nhiên, một hệ thống khác có thể chọn từ chối trường lạ vì lý do bảo mật hoặc hợp đồng nghiêm ngặt. Quyết định phải nhất quán với chính sách forward compatibility.

Khi dùng DTO/record và Jackson tự deserialize, cấu hình xử lý trường lạ, constructor và annotation ảnh hưởng kết quả. Do đó, **test lớp đọc thực tế đang sử dụng trong production**, không chỉ test một helper mô phỏng.

### 14.1. Unit test cho dữ liệu v1 và v2

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

final class OrderEventReaderTest {
    private final OrderEventReader reader = new OrderEventReader();

    @Test
    void newReaderReadsOldEventWithoutOptionalField() throws Exception {
        String oldJson = """
            {
              "eventId":"evt-1",
              "eventType":"OrderCreated",
              "orderId":"ord-1",
              "amountMinor":10000,
              "currency":"VND"
            }
            """;

        OrderCreated event = reader.read(oldJson);

        assertEquals("ord-1", event.orderId());
        assertEquals(10000L, event.amountMinor());
        assertEquals("UNKNOWN", event.salesChannel());
    }

    @Test
    void newReaderReadsNewEventWithExtraField() throws Exception {
        String newJson = """
            {
              "eventId":"evt-2",
              "eventType":"OrderCreated",
              "orderId":"ord-2",
              "amountMinor":20000,
              "currency":"VND",
              "salesChannel":"MOBILE",
              "futureMetadata":"ignored"
            }
            """;

        OrderCreated event = reader.read(newJson);

        assertEquals("MOBILE", event.salesChannel());
        assertEquals(20000L, event.amountMinor());
    }

    @Test
    void invalidMonetaryValueIsRejected() {
        String invalid = """
            {
              "eventId":"evt-3",
              "eventType":"OrderCreated",
              "orderId":"ord-3",
              "amountMinor":-100,
              "currency":"VND"
            }
            """;

        assertThrows(
            IllegalArgumentException.class,
            () -> reader.read(invalid));
    }

    @Test
    void missingRequiredOrderIdIsRejected() {
        String invalid = """
            {
              "eventId":"evt-4",
              "eventType":"OrderCreated",
              "amountMinor":100,
              "currency":"VND"
            }
            """;

        assertThrows(
            IllegalArgumentException.class,
            () -> reader.read(invalid));
    }
}
~~~

Đây là các test đi qua đường đọc JSON và quy tắc nghiệp vụ của consumer. Để chứng minh **hai chiều** tương thích, cần chạy reader v1 thật với payload v2; test chỉ sử dụng lớp reader mới không thể chứng minh reader cũ xử lý bản mới.

Nếu dùng Avro hoặc Protobuf, hãy tạo payload binary bằng phiên bản schema writer tương ứng và giải mã bằng version reader được kiểm tra. Không thay phép thử này bằng việc so sánh text của hai schema.

## 15. Contract test giữa producer và consumer độc lập

Một producer có thể thay đổi contract mà vẫn pass unit test của chính nó. Consumer lại sở hữu những kỳ vọng không được ghi trong schema, như:

- **OrderCreated** phải có sau commit đơn hàng, không phát trước khi transaction thành công.
- Một event cùng eventId được redeliver thì không làm trừ tiền hoặc giữ hàng hai lần.
- eventType phải ổn định; amountMinor dùng đơn vị nhỏ nhất và không âm.
- Trường paymentStatus chỉ nhận các trạng thái có hợp đồng xử lý rõ.
- Producer không được tự ý ngừng phát sự kiện mà một consumer vẫn phụ thuộc.

**Consumer-driven contract testing** cho phép consumer công bố những tình huống nó cần: định dạng sự kiện, ví dụ payload và các điều kiện diễn giải. Pipeline producer chạy các kiểm thử để xác minh những kỳ vọng đã được công bố trước khi phát hành.

~~~mermaid
flowchart LR
    C["Consumer định nghĩa kỳ vọng"] --> K[("Kho contract / fixtures")]
    K --> PT["CI của producer"]
    PT --> V{"Producer còn đáp ứng?"}
    V -->|Có| D["Cho phép tiến hành rollout"]
    V -->|Không| F["Sửa contract hoặc phối hợp nâng phiên bản"]
~~~

Một contract test đáng giá cần có cả **cấu trúc** và **hành vi**. Ví dụ consumer hợp đồng rằng amountMinor là số nguyên không âm và OrderCreated chỉ phát một lần theo eventId logic; nếu producer đổi sang amountDecimal dạng string, sự thay đổi phải làm test thất bại trước khi deploy.

Công cụ như Pact hoặc một bộ test fixture tự xây có thể hỗ trợ kiểm thử hợp đồng bất đồng bộ. Tên API của từng công cụ thay đổi theo bản phát hành; mục tiêu không phụ thuộc sản phẩm là **kỳ vọng của consumer được kiểm tra trên output do producer thực sự tạo**.

## 16. Integration test: thử cả serializer, registry, broker và handler

Một test chỉ gọi trực tiếp hàm **handle(orderCreated)** không mô phỏng đầy đủ môi trường. Trong hệ thống chạy thực, lỗi có thể nằm ở định dạng wire, schema ID, subject naming, authentication, routing, offset hoặc cơ chế retry.

Một integration test điển hình:

~~~text
1. Khởi tạo broker thử nghiệm và schema registry nếu sản phẩm cần.
2. Tạo topic/queue, ACL/config cần thiết bằng fixture kiểm thử.
3. Khởi động producer dùng serializer/version thật.
4. Phát dữ liệu fixture của writer cũ và writer mới.
5. Khởi động consumer dùng deserializer và group thật.
6. Chờ bằng điều kiện có giới hạn, không ngủ cứng theo thời gian.
7. Xác minh side effect, metric và offset/ack sau xử lý.
8. Thử payload sai, registry unreachable, duplicate delivery, retry và DLQ.
9. Dọn tài nguyên test đã tạo và cô lập giữa các lần chạy.
~~~

Có thể dùng Testcontainers hoặc môi trường thử nghiệm có vòng đời riêng. Với Kafka, kiểm tra cả consumer group, partition và offset; với RabbitMQ, kiểm tra exchange/binding/routing key và ACK/NACK; với dịch vụ hàng đợi quản lý, kiểm tra IAM và các giới hạn cụ thể của sản phẩm.

Ví dụ kế hoạch kiểm thử:

| Tình huống | Kỳ vọng |
|---|---|
| Producer v2 phát message với schema đã đăng ký | Consumer v2 giải mã và xử lý đúng |
| Consumer v2 đọc binary từ writer v1 | Tương thích backward hoặc từ chối có lý do theo chính sách |
| Consumer v1 đọc binary từ writer v2 | Phát hiện đúng mức forward compatibility |
| Consumer nhận schema ID chưa có trong cache | Tải schema hợp lệ hoặc xử lý lỗi có chính sách |
| Registry tạm không truy cập được | Không tạo vòng retry vô tận; cache/failure policy rõ |
| Message sai schema hoặc sai nghiệp vụ | Không tạo side effect, chuyển luồng lỗi đúng |
| Consumer restart trước ACK/commit | Event có thể redeliver nhưng side effect không nhân đôi |
| Message v1 được replay sau khi rollout xong | Reader hiện tại vẫn hiểu theo hợp đồng retention |

Dùng test data nằm trong môi trường thử riêng; không phát fixture có tác dụng phụ sang queue/topic production.

## 17. Định nghĩa chiến lược thay đổi: expand → migrate → contract

Khi phải thêm trường hoặc đổi định dạng, ưu tiên chuyển đổi nhiều bước thay vì cập nhật đồng loạt producer và consumer.

### 17.1. Ví dụ đổi amount từ số thập phân sang amountMinor

Ban đầu producer gửi:

~~~json
{
  "eventType": "OrderCreated",
  "orderId": "ord-1",
  "amount": 1250.50
}
~~~

Nhóm muốn chuyển sang số nguyên trong đơn vị nhỏ nhất. Nếu thay trực tiếp **amount** bằng **amountMinor** trong một lần deploy, consumer cũ có thể không đọc được hoặc âm thầm tính sai.

**Giai đoạn 1 — Expand consumer:**

- Phát hành consumer hiểu cả amount cũ và amountMinor mới.
- Kiểm tra rõ cách làm tròn, đơn vị và các loại tiền tệ.
- Đảm bảo consumer đọc được dữ liệu cũ trong retention và có định nghĩa ưu tiên khi cả hai trường xuất hiện.

**Giai đoạn 2 — Expand producer:**

- Producer tạm phát cả hai trường nếu hợp đồng và định dạng cho phép.
- Nếu hai trường cùng tồn tại, test ràng buộc **amountMinor phản ánh amount theo quy tắc chuyển đổi đã duyệt**.
- Theo dõi lượng consumer còn phụ thuộc trường cũ.

**Giai đoạn 3 — Migrate:**

- Nâng những consumer còn lại, job batch, dashboard và công cụ replay.
- Chạy compatibility matrix, consumer contract tests và thử phát lại dữ liệu cũ.

**Giai đoạn 4 — Contract:**

- Khi không còn consumer cần trường cũ và các điều kiện retention/replay đã được xử lý, loại trường cũ bằng bản schema/phát hành có kiểm soát.
- Đánh giá lại khả năng rollback về consumer cũ: nếu không thể đọc sự kiện mới, rollback code cũ cần được ngăn hoặc có adapter.

Tên trường mới giúp ngăn diễn giải nhầm đơn vị. Nếu việc đổi không thể diễn đạt tương thích qua cùng message, cân nhắc loại sự kiện hoặc topic version mới cùng kế hoạch chuyển đổi.

### 17.2. Thay đổi không tương thích phải xử lý thế nào?

Khi cần thay đổi cấu trúc lớn hoặc ý nghĩa event:

- Tạo event type mới như OrderCreatedV2 hoặc định danh schema/contract version mới theo quy ước.
- Tạm chạy producer hai dạng nếu dữ liệu và chi phí cho phép, hoặc có bridge chuyển đổi.
- Chạy consumer phiên bản mới song song; xác định ranh giới cắt chuyển và cách chống xử lý trùng.
- Xác định lúc nào có thể ngừng version cũ dựa trên consumer thực tế, retention và backlog.
- Thử đường rollback trước khi bật gửi version mới.
- Có thể cần migration dữ liệu hoặc công cụ upcaster để replay lịch sử.

**Đừng tự động version topic cho mọi thay đổi nhỏ.** Topic mới mang chi phí vận hành, quyền, consumer group, monitoring và migration. Chọn cách version dựa trên mức tương thích và yêu cầu phân tách ngữ nghĩa.

## 18. Replay: dữ liệu cũ là một phần của hợp đồng còn sống

Kafka hoặc event store có thể giữ dữ liệu lâu; RabbitMQ, DLQ hay lưu trữ ngoài có thể chứa thông điệp chờ xử lý từ nhiều phiên bản. Một consumer mới khởi động lại từ offset đầu phải gặp **writer schema cũ**, không chỉ schema hiện tại.

Test replay cần xét:

1. **Dải phiên bản:** tất cả writer version còn khả năng gặp trong retention, backup hoặc DLQ.
2. **Định dạng:** binary từ serializer cũ, header/schema ID cũ và trường bị xóa.
3. **Ngữ nghĩa thời gian:** trạng thái nghiệp vụ cũ có còn được chấp nhận không?
4. **Thứ tự:** liệu event cũ được xử lý sau event mới có làm trạng thái lùi lại không?
5. **Idempotency:** replay một event đã xử lý không gây side effect lần hai.
6. **Thông lượng:** replay lượng dữ liệu lớn không làm nghẽn DB/API downstream.
7. **Quan sát:** phân biệt replay với traffic mới, biết tỉ lệ lỗi theo schema version.

**Ví dụ:** Consumer mới hiểu schema v3 và v2 nhưng không hiểu v1. Nếu topic retention chỉ 7 ngày và không có snapshot, DLQ hay backup cũ, nhóm có thể chấp nhận giới hạn đó sau khi đánh giá. Nếu doanh nghiệp cần phát lại 2 năm dữ liệu, phải giữ khả năng đọc v1, xây upcaster hoặc chuẩn bị migration lịch sử. Điều kiện phải được ghi trong hợp đồng hệ thống.

**Upcaster** là bộ chuyển đổi sự kiện cũ sang mô hình hiện tại ở thời điểm đọc. Nó không nên tùy tiện bịa ra dữ liệu lịch sử chưa từng tồn tại; với trường mới không suy ra được, cần default có ý nghĩa, biểu diễn unknown hoặc quy tắc loại/đánh dấu rõ.

## 19. Tương thích schema không bảo đảm xử lý sự kiện đúng một lần

Broker có thể giao lại cùng message sau consumer restart, timeout hoặc lỗi ACK/commit. Nếu eventId không ổn định qua retry, consumer khó phát hiện bản lặp. Nếu schema mới thêm trường nhưng consumer kiểm tra sai idempotency key, tác dụng phụ có thể nhân đôi.

Các test cần bổ sung:

- Một eventId được xử lý hai lần: chỉ tạo một tác dụng phụ nghiệp vụ theo hợp đồng.
- Hai event khác eventId nhưng cùng business command: xem có cần khóa idempotency nghiệp vụ hay không.
- Consumer crash sau khi ghi DB nhưng trước commit offset: redelivery không ghi trùng.
- Event đến lệch thứ tự: aggregateVersion/sequence bảo vệ trạng thái không bị lùi.
- Event bị poison: retry hữu hạn rồi DLQ, không làm dừng toàn bộ topic hoặc queue.
- Consumer schema mới vẫn hiểu trường idempotency cũ; không vô tình đổi ý nghĩa eventId khi nâng phiên bản.

“Exactly-once” do một nền tảng cung cấp chỉ có hiệu lực trong phạm vi giao dịch/cơ chế được mô tả. Nó không tự bảo đảm mọi side effect bên ngoài như HTTP gọi cổng thanh toán hoặc một DB độc lập chỉ xảy ra một lần.

## 20. Kịch bản lỗi và cách kiểm thử phản ứng

### 20.1. Thiếu trường bắt buộc

Payload thiếu orderId. Schema validator hoặc reader phải từ chối trước khi gọi DB hoặc publish sự kiện tiếp. Ghi mã lỗi phân loại như **MISSING_REQUIRED_FIELD** và route vào luồng xử lý lỗi theo chính sách.

### 20.2. Có giá trị enum chưa biết

Producer thêm trạng thái ORDER_ON_HOLD. Consumer cũ parse được chuỗi nhưng switch-case không có nhánh. Test cần xác định **unknown state** được ghi nhận, bỏ qua có kiểm soát hay đưa DLQ; không mặc định “unknown = completed”.

### 20.3. Thay đổi đơn vị hoặc miền giá trị

Trường amount chuyển từ đồng sang đơn vị nhỏ nhất nhưng vẫn là integer. Schema test có thể pass. Contract test với đơn hàng 12.500 đơn vị tiền và kết quả mong đợi phải phát hiện sai khác.

### 20.4. Registry không sẵn sàng

Deserializer gặp schema ID chưa có cache và registry timeout. Consumer nên có chính sách retry có ngân sách, quan sát và xử lý lỗi tránh vòng lặp vô hạn. Nếu chỉ thiếu schema tạm thời, đưa ngay vào DLQ có thể gây lượng lỗi không cần thiết; cần phân loại lỗi schema thực sự không hợp lệ và lỗi hạ tầng tạm thời.

### 20.5. Thông điệp độc hại hoặc quá lớn

Payload được nén với tỷ lệ bất thường, mảng quá lớn hoặc cấu trúc lồng nhau sâu có thể tiêu thụ CPU/RAM. Đặt giới hạn kích thước và độ sâu ở nơi phù hợp; kiểm thử với dữ liệu gần ngưỡng chấp nhận. Schema hợp lệ không đồng nghĩa payload an toàn về tài nguyên.

### 20.6. Producer đổi cách định tuyến

Event vẫn đúng schema nhưng publish sang topic khác hoặc đổi partition key. Consumer có thể không thấy dữ liệu hoặc mất thứ tự theo orderId. Integration test phải xác minh tên topic, routing key, partition và consumer group thực tế.

### 20.7. Dữ liệu hợp lệ nhưng xảy ra sai tác dụng phụ

Event PaymentCompleted được phát trước khi commit DB. Payload đúng schema, nhưng consumer cập nhật đơn hàng thành PAID khi giao dịch thật thất bại. Contract test cần kiểm tra **điều kiện phát sự kiện**, dùng outbox hoặc cơ chế tin cậy phù hợp.

## 21. DLQ và quan sát lỗi schema

DLQ là nơi cách ly thông điệp không thể xử lý sau chính sách retry, không phải thùng chứa để bỏ quên lỗi. Một message khi vào DLQ nên có dữ liệu chẩn đoán **không tiết lộ bí mật**:

~~~json
{
  "failureType": "SCHEMA_VALIDATION",
  "reasonCode": "INVALID_AMOUNT_MINOR",
  "sourceTopic": "orders.created",
  "sourcePartition": 2,
  "sourceOffset": 91832,
  "eventId": "evt-981",
  "writerSchemaVersion": 3,
  "consumerVersion": "checkout-reader-7",
  "firstSeenAt": "2026-11-12T02:00:00Z",
  "attempts": 3
}
~~~

Ví dụ metadata này cần điều chỉnh theo broker thực tế: RabbitMQ không có offset kiểu Kafka; thông tin route sẽ là queue/exchange/routing key và delivery metadata. Thông điệp gốc chỉ nên lưu kèm khi chính sách dữ liệu và quyền cho phép, với mã hóa và retention phù hợp.

Các metric hữu ích:

| Nhóm | Chỉ số gợi ý | Ý nghĩa |
|---|---|---|
| Phân loại phiên bản | events_received_total theo eventType/schemaVersion | Đang thấy những phiên bản writer nào? |
| Lỗi giải mã | deserialization_failures_total | Lỗi serializer, schema ID hay wire format? |
| Lỗi validate | contract_rejections_total theo reasonCode | Trường nào/luật nghiệp vụ nào sai? |
| Độ trễ xử lý | consumer_processing_duration | Thay đổi schema có làm xử lý chậm đi? |
| Tồn đọng | consumer_lag / queue_age | Message lỗi có làm ùn tắc? |
| Retry và DLQ | retries_total, dlq_messages_total | Lỗi lặp lại và lượng bị cách ly |
| Tác dụng phụ | duplicate_suppressed_total | Idempotency có hoạt động? |
| Triển khai | producer_version, consumer_version | Có tổ hợp phiên bản chưa kiểm thử không? |

Metric labels không nên chứa eventId, orderId hoặc payload tùy ý vì làm tăng cardinality và có thể lộ dữ liệu. Dùng reasonCode có tập giá trị kiểm soát.

Cảnh báo cần phân biệt một lỗi fixture đơn lẻ với tỷ lệ lỗi schema tăng sau deployment. Khi số sự kiện bị lỗi tăng, rollback không được thực hiện mù nếu producer mới đã phát dữ liệu mà consumer cũ không hiểu.

## 22. CI/CD: đặt kiểm tra tại những điểm thay đổi hợp đồng

Một pipeline có thể tổ chức theo lớp:

~~~mermaid
flowchart TD
    S["Thay schema, producer hoặc consumer"] --> V["Syntax + schema validation"]
    V --> G["Compatibility check với registry/lịch sử"]
    G --> F["Fixture matrix và semantic contract tests"]
    F --> I["Integration test broker + serializer + handler"]
    I --> R{"Đạt điều kiện phát hành?"}
    R -->|Không| B["Chặn phát hành và nêu cặp version lỗi"]
    R -->|Có| C["Canary / rolling deploy"]
    C --> M["Quan sát lỗi schema + DLQ + nghiệp vụ"]
    M --> O["Mở rộng rollout hoặc phục hồi có kiểm soát"]
~~~

**Ở pull request của schema:**
- Parse và lint schema; generate code đúng plugin/version.
- Kiểm tra compatibility với schema đã phát hành trong registry.
- Chạy fixture reader/writer matrix cho những phiên bản còn hỗ trợ.
- Chạy semantic assertions về miền giá trị, đơn vị và business meaning.

**Ở pull request producer:**
- Xuất bản một sự kiện thực bằng serializer đang dùng, đối chiếu contract consumers.
- Kiểm tra event được phát đúng thời điểm và không mất event khi giao dịch DB thành công.
- Kiểm tra message key, topic, header, schema ID và định tuyến.

**Ở pull request consumer:**
- Đọc fixture cũ/mới, malformed và dữ liệu biên.
- Kiểm tra handler, side effect, retry, idempotency, DLQ và đo lỗi.
- Thử version skew tối thiểu giữa bản hiện tại và bản đang phát trong production.

**Trước rollout production:**
- Xác định thứ tự deploy thích hợp với backward/forward/full.
- Đọc số lượng producer/consumer thực đang chạy và cửa sổ compatibility.
- Chọn canary, metric guardrail và điều kiện dừng.
- Chuẩn bị đường khôi phục nếu đã gửi thông điệp mới.

Pipeline nên báo lỗi theo ngữ cảnh như **Writer v3 → Reader v1, field salesChannel, enum unsupported**, thay vì chỉ thông báo chung “contract failed”. Không tự đổi compatibility mode sang NONE trong CI để giải quyết lỗi khó.

## 23. Rollout và rollback khi đã có thông điệp mới trong broker

Một khác biệt lớn với thay đổi HTTP đồng bộ là: **thông điệp đã phát có thể còn nằm trong broker sau khi producer được rollback**. Vì vậy, rollback ứng dụng không luôn đủ.

Tình huống:

~~~text
T0: Writer v1 + Reader v1
T1: Reader v2 được triển khai, đọc được cả v1 và v2
T2: Writer v2 phát dữ liệu mới
T3: Phát hiện lỗi nghiệp vụ, muốn rollback
T4: Broker còn thông điệp v2 chưa được xử lý
~~~

Nếu rollback reader về v1 trong khi v1 không hiểu v2, consumer sẽ lỗi ngay sau khi khởi động. Hướng xử lý:

1. **Dừng mở rộng rollout**, xác định phiên bản message đã phát và thời gian/offset.
2. **Giữ một reader tương thích** hoặc adapter/upcaster đủ khả năng đọc dữ liệu đã tồn tại.
3. **Rollback producer** nếu hành vi phát mới là nguyên nhân, đồng thời không phá đường đọc của message đang tồn tại.
4. Xử lý backlog, DLQ và các tác dụng phụ đã xảy ra theo chính sách nghiệp vụ.
5. Chỉ rollback consumer về bản cũ khi đã chứng minh nó xử lý được dữ liệu còn lại hoặc cô lập dữ liệu không tương thích bằng phương án được duyệt.
6. Xác nhận consumer lag/queue age, tỷ lệ lỗi và business state trở về mức bình thường.

Với schema thay đổi phá vỡ hợp đồng, có thể cần **forward-compatible reader**, một topic khác, hoặc kế hoạch nâng cấp lại thay vì cố lùi tất cả service cùng lúc.

Quyết định rollback phải xét **code, schema, dữ liệu trên broker và side effect**, không chỉ ảnh container.

## 24. Tình huống tổng hợp: thêm mã kênh bán vào sự kiện đơn hàng

**Bối cảnh:** Order Service hiện gửi OrderCreated v1. Billing và Inventory đọc; Analytics muốn bổ sung salesChannel để phân tích web/mobile. Các nhóm deploy độc lập, topic giữ sự kiện 30 ngày và một job định kỳ có thể replay từ đầu.

**Kế hoạch:**

1. Định nghĩa schema v2 thêm salesChannel với cách biểu diễn optional/default phù hợp format.
2. Kiểm tra Reader v2 đọc được Writer v1 trong 30 ngày lịch sử. Tạo fixture nhị phân từ schema v1.
3. Kiểm tra Reader v1 đọc được Writer v2 nếu producer dự định deploy trước khi tất cả consumer nâng; đặc biệt kiểm tra xử lý unknown fields.
4. Ghi rõ ngữ nghĩa UNKNOWN hoặc null: đó là dữ liệu lịch sử thiếu thông tin hay lỗi producer mới? Không trộn lẫn hai trường hợp.
5. Đăng ký schema trong subject đúng, dùng compatibility mode phù hợp khoảng phiên bản cần hỗ trợ.
6. Nâng và chạy canary Billing/Inventory/Analytics theo thứ tự tương thích đã xác định.
7. Nâng producer Order Service, phát v2; đo error rate, deserialize failure, consumer lag và thống kê salesChannel.
8. Thử replay dữ liệu v1 bằng reader hiện tại, xác nhận không phá logic thống kê.
9. Khi cần rollback producer, tiếp tục giữ reader hiểu v2 vì broker vẫn còn message v2.
10. Chỉ khi retention, replay và inventory consumer chứng minh đủ điều kiện mới xem xét bỏ hỗ trợ v1.

**Điểm đặc biệt:** trường thêm có thể được chấp nhận về schema nhưng làm sai báo cáo nếu Analytics xem UNKNOWN là WEB. Contract test cần kiểm tra giá trị lịch sử được phân nhóm UNKNOWN rõ ràng, không tự đoán thành một kênh bán.

## 25. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Chỉ kiểm tra JSON/Avro có parse được | Bỏ sót thay đổi ngữ nghĩa | Test giá trị và side effect nghiệp vụ |
| Hiểu nhầm backward với forward | Chọn sai thứ tự deploy | Viết rõ Reader mới ← Writer cũ và Reader cũ ← Writer mới |
| Chỉ so với schema gần nhất | Replay dữ liệu rất cũ thất bại | Kiểm tra transitive khi cần |
| Thêm optional mà không test missing/null | Consumer v1/v2 xử lý khác nhau | Fixture vắng, null, có giá trị |
| Đổi đơn vị nhưng giữ tên/kiểu | Tính toán sai âm thầm | Đổi tên/phiên bản và assert chuyển đổi |
| Protobuf tái sử dụng field number | Đọc byte cũ thành ý nghĩa khác | reserved number/name, review schema |
| Nhầm default JSON Schema là tự điền field | Runtime thiếu trường | Test validator và deserializer thực tế |
| Để producer tự phát schema mới không qua registry check | Vượt quy trình compatibility | Kiểm tra trước khi đăng ký/phát |
| Consumer chỉ test object trong memory | Không bắt lỗi wire format và header | Integration test serializer + broker |
| Rollback cả producer lẫn reader về cũ | Reader cũ không hiểu message mới còn trong broker | Giữ reader tương thích và xử lý backlog |
| DLQ không có owner và replay policy | Message lỗi tích lũy hoặc bị phát lại nguy hiểm | Phân quyền, retention, audit và replay có giới hạn |
| Dùng fixtures tạo bằng serializer mới cho v1 | Không đại diện dữ liệu lịch sử | Giữ binary fixture của writer cũ |
| Chỉ test happy path | Poison message làm kẹt partition/queue | Test malformed, retry, DLQ, idempotency |
| Bỏ qua đối tác ngoài hệ thống | Consumer thứ ba vỡ contract | Inventory consumer và công bố vòng đời hỗ trợ |
| Cho schema registry là nguồn duy nhất của sự thật | Không thấy thay đổi thời điểm phát event, partition key | Kết hợp contract/integration/semantic tests |

## 26. Bài tập thực hành

**Bài A — ma trận phiên bản:** Một topic có Writer v1/v2/v3, Consumer v2/v3 và dữ liệu v1 vẫn trong retention. Hãy lập ma trận reader/writer cần chạy trong CI. Chọn backward hay backward transitive, giải thích bằng điều kiện replay thực tế.

**Bài B — Avro:** Một schema v1 có orderId và amountMinor. Phiên bản v2 thêm salesChannel. Thiết kế schema và các fixture cho trường thiếu, null và có giá trị. Viết điều kiện kỳ vọng cho Reader v2 đọc Writer v1 và Reader v1 đọc Writer v2.

**Bài C — Protobuf:** Một message có field number 1=order_id, 2=amount_minor. Nhóm muốn đổi tên amount_minor thành total và thêm trường status. Hãy chỉ ra điều gì giữ tương thích binary, điều gì có thể phá semantic/JSON contract; xây phương án không tái sử dụng field number và bộ test cho enum chưa biết.

**Bài D — ngữ nghĩa:** Producer giữ kiểu số nguyên nhưng đổi amount từ đồng sang đơn vị nhỏ nhất. Tại sao schema registry có thể chấp nhận? Hãy viết fixture có số tiền cụ thể để test consumer tính đúng, đồng thời lên kế hoạch chuyển hai giai đoạn.

**Bài E — rollback:** Writer v2 đã phát 100.000 thông điệp; Reader v2 lỗi hiệu năng, Reader v1 không hiểu v2. Bạn sẽ dừng rollout, giữ reader nào, xử lý backlog và rollback producer ra sao? Liệt kê điều kiện để khẳng định hệ thống phục hồi.

**Bài F — integration test:** Dùng broker thử nghiệm, producer Avro v2 và consumer Java. Viết kịch bản kiểm tra schema ID, subject, serialization, routing, consumer group, retry, DLQ và idempotency. Nêu cách cô lập test data khỏi production.

**Bài G — hợp đồng nghiệp vụ:** PaymentCompleted có schema hoàn toàn hợp lệ nhưng được publish trước khi DB xác nhận thanh toán. Hãy thiết kế producer-side test phát hiện, thay đổi cơ chế ghi event cho đáng tin và consumer-side test chống xử lý trùng.

## 27. Cách ghi lại một hợp đồng để nhóm khác có thể kiểm thử

Một tài liệu contract mẫu nên có:

~~~yaml
contract:
  eventType: OrderCreated
  owner: order-service
  destination: orders.created
  format: avro
  schemaSubject: orders.created-value
  compatibilityRequirement: BACKWARD_TRANSITIVE
  retainedWriterVersions: [1, 2, 3]
  fields:
    orderId:
      type: string
      required: true
      meaning: "Mã đơn đã được tạo và ghi nhận bền vững"
    amountMinor:
      type: long
      required: true
      meaning: "Giá trị đơn theo đơn vị nhỏ nhất"
      constraints: ">= 0"
    salesChannel:
      type: "nullable string"
      required: false
      meaning: "Nguồn tạo đơn, UNKNOWN khi dữ liệu lịch sử thiếu"
  delivery:
    orderingKey: orderId
    duplicateHandling: "consumer idempotent by eventId"
  tests:
    - "writer v1 -> reader v3"
    - "writer v2 -> reader v3"
    - "writer v3 -> reader v3"
    - "malformed payload -> explicit rejection"
    - "duplicate eventId -> no duplicate side effect"
~~~

Đây là mẫu mô tả bằng YAML, không phải file cấu hình Schema Registry có thể chạy trực tiếp. Tên subject và compatibilityRequirement phải khớp cách triển khai thực tế; đặc biệt nếu retention/replay yêu cầu các phiên bản xa hơn, danh sách test cũng phải được mở rộng.

Người sở hữu contract cần biết những consumer nào phụ thuộc nó, ai được quyền duyệt phá vỡ tương thích, lịch trình ngừng hỗ trợ phiên bản và cách thông báo trước cho các nhóm liên quan.

## 28. Ghi nhớ

- **Schema validation** hỏi payload có hợp lệ theo schema; **compatibility** hỏi phiên bản reader/writer nào đọc được nhau; **contract testing** hỏi ý nghĩa nghiệp vụ và kỳ vọng consumer có còn đúng không.
- **Backward:** reader mới đọc writer cũ. **Forward:** reader cũ đọc writer mới. **Full:** cả hai. **Transitive:** phải xét thêm các phiên bản lịch sử theo cấu hình và hợp đồng.
- Các format có luật riêng: **Avro** dựa vào writer/reader resolution; **Protobuf** cần giữ field number và wire semantics; **JSON Schema** cần kiểm tra required/unknown fields và hành vi validator thực tế.
- Schema đúng kiểu không ngăn lỗi **đơn vị tiền, enum mới, thời điểm phát sự kiện, thứ tự, routing hoặc side effect**.
- Kiểm thử phải gồm **fixture do writer cũ tạo, ma trận reader/writer, contract của consumer, integration test broker/serializer và replay**.
- Thay đổi lớn nên theo lộ trình **expand → migrate → contract**, có thứ tự triển khai và thời gian hỗ trợ phiên bản được công bố.
- **Rollback producer không xóa message mới đã có trong broker**; phải giữ reader tương thích hoặc đường chuyển đổi/khôi phục phù hợp.
- Retry, DLQ, idempotency, quan sát theo schema version và bảo mật registry giúp sự cố tương thích không lan thành lỗi hệ thống.

Một hợp đồng thông điệp đáng tin là hợp đồng được **kiểm thử qua nhiều phiên bản và kiểm chứng bằng hành vi thực tế**. Khi producer, consumer và pipeline triển khai cùng chia sẻ ma trận tương thích và lịch sử dữ liệu, hệ thống microservices có thể phát triển độc lập mà không vô tình làm mất hoặc hiểu sai thông điệp của nhau.
