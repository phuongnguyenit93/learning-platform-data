# Kiểm soát lược đồ thông điệp và vai trò của Schema Registry

## 1. Vì sao cần kiểm soát lược đồ khi các dịch vụ trao đổi thông điệp?

Trong kiến trúc Microservices, các dịch vụ thường trao đổi sự kiện (events) hoặc lệnh (commands) qua Kafka, RabbitMQ, Pulsar, hệ thống hàng đợi hoặc các bus nội bộ. Một dịch vụ phát thông điệp và nhiều dịch vụ khác có thể tiêu thụ chúng theo lịch triển khai khác nhau.

Ví dụ khi khách tạo đơn hàng:

- Ordering Service phát sự kiện **OrderPlaced**.
- Inventory Service sử dụng dữ liệu đơn để giữ tồn kho.
- Notifications Service dùng thông tin tham chiếu để gửi xác nhận.
- Analytics Service cập nhật báo cáo.
- Một consumer cũ có thể vẫn đang dùng phiên bản chương trình được triển khai từ tháng trước.

Ban đầu producer gửi:

~~~json
{
  "eventId": "evt-100",
  "eventType": "OrderPlaced",
  "orderId": "ORD-1001",
  "customerId": "CUS-17",
  "totalAmount": 500000
}
~~~

Sau đó nhóm Ordering thêm trường currency, đổi totalAmount thành amount, hoặc đổi đơn vị tiền từ VND sang xu. Nếu không có quy ước và công cụ quản lý hợp đồng, một số consumer có thể giải mã lỗi; số khác tiếp tục xử lý nhưng diễn giải sai dữ liệu, thường nguy hiểm hơn lỗi parse.

**Lược đồ (schema)** mô tả hình dạng và kiểu dữ liệu được trao đổi. **Schema Registry** là một thành phần giúp lưu, định danh, phát hành, tra cứu và kiểm tra quy tắc tương thích của các lược đồ theo phiên bản. Nó hỗ trợ producer và consumer triển khai độc lập có kiểm soát.

Nhưng cần phân biệt rõ:

- Schema giúp mô tả **cú pháp và cấu trúc** của message.
- Contract nghiệp vụ còn bao gồm **ý nghĩa, điều kiện phát sinh, quyền sở hữu, thứ tự, khả năng phát lại và cách xử lý lỗi**.
- Registry giúp điều phối schema nhưng **không tự bảo đảm** rằng mọi thay đổi đều đúng nghiệp vụ, mọi client đều tương thích, hoặc message đã được giao/tiêu thụ chính xác một lần.

### Mục tiêu học tập

Sau bài này bạn có thể:

1. Phân biệt schema, message contract, event version, schema ID, subject và schema version.
2. Giải thích vì sao có Schema Registry trong hệ thống bất đồng bộ.
3. Đọc ví dụ Avro, Protobuf, JSON Schema và xác định những thay đổi có thể gây lỗi tương thích.
4. Phân biệt BACKWARD, FORWARD, FULL, NONE và biến thể transitive theo quy định của registry.
5. Lên kế hoạch rollout producer/consumer khi thêm, xóa hoặc đổi trường.
6. Hiểu cách serializer/deserializer phối hợp với registry và schema ID.
7. Thiết kế quản trị schema: ownership, CI, review, compatibility checks, bảo mật, quan sát và xử lý sự cố.
8. Nhận diện giới hạn của Registry với semantic change, idempotency, sự kiện trùng, thứ tự và lịch sử replay.

## 2. Schema là gì, và khác hợp đồng thông điệp thế nào?

### 2.1. Schema: cấu trúc dữ liệu

Schema thường mô tả:

- Tên loại message, namespace và phiên bản quy ước.
- Các field và kiểu dữ liệu: string, integer, decimal, boolean, array, record, enum, union, message.
- Field nào bắt buộc, tùy chọn, có thể null hoặc có default.
- Định danh field trên wire, ví dụ tag number của Protocol Buffers.
- Một số ràng buộc giá trị và định dạng như enum, pattern, giới hạn hoặc logical type.
- Cấu trúc lồng nhau và khả năng tham chiếu tới schema khác.

Ví dụ schema có thể quy định amount là số nguyên kiểu long và currency là chuỗi. Tuy vậy, nếu schema không diễn tả đầy đủ, consumer vẫn có thể không biết amount là **VND, cent hay đơn vị tiền nhỏ nhất**.

### 2.2. Message contract: cấu trúc cộng ngữ nghĩa và vận hành

Một **message contract** có thể bao gồm schema cùng các quy tắc:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Ownership | Ai sở hữu sự kiện, schema và định nghĩa nghiệp vụ? |
| Trigger | Khi nào producer được phép phát sự kiện? |
| Business semantics | OrderPlaced có nghĩa đã ghi đơn, đã thu tiền hay đã chấp nhận xử lý? |
| Payload | Những field nào có nghĩa gì, đơn vị nào, có thể thiếu/null không? |
| Identity | eventId, aggregateId, correlationId và idempotency key dùng thế nào? |
| Ordering | Sự kiện của cùng order có được giữ thứ tự ở phạm vi nào? |
| Delivery | Có thể nhận lặp, đến muộn hoặc mất thứ tự không? |
| Privacy | Dữ liệu nào không được gửi ra bus hoặc log? |
| Compatibility | Thay đổi nào được phép mà consumer cũ vẫn chạy? |
| Lifecycle | Có replay, retention, deprecation và schema sunset không? |

Do đó, một schema registry là công cụ thiết yếu trong nhiều hệ thống nhưng chỉ là **một phần của contract governance**.

### 2.3. Event không giống command

**Event** công bố một sự thật đã xảy ra: OrderPlaced, PaymentSucceeded, StockReserved. Tên thường dùng thì quá khứ và có producer nắm quyền công bố sự thật đó.

**Command** yêu cầu một hành động: ReserveStock, CreateShipment, ChargePayment. Consumer có thể chấp nhận hoặc từ chối; command không chứng minh hành động đã được thực hiện.

Cả event và command đều cần schema rõ ràng. Tuy nhiên, semantics và trách nhiệm xử lý khác nhau. Thay đổi ReserveStock.quantity từ “số lượng sản phẩm” sang “số kiện hàng” có thể gây lỗi nghiệp vụ dù schema vẫn là integer.

## 3. Vì sao hệ thống lớn khó quản lý schema thủ công?

Hãy xét một topic Kafka **orders.events** có các consumer:

~~~mermaid
flowchart LR
    O[Ordering Service Producer] --> T[(orders.events)]
    T --> I[Inventory Consumer]
    T --> N[Notifications Consumer]
    T --> A[Analytics Consumer]
    T --> F[Fraud/Risk Consumer]
~~~

Không phải mọi consumer cập nhật cùng thời điểm. Có consumer đang chạy ổn định phiên bản cũ; có consumer tạm ngừng nhiều ngày rồi replay message từ offset cũ. Một kiểu thay đổi làm consumer mới chạy được có thể khiến consumer cũ gặp lỗi khi đọc message mới; một thay đổi chạy được với dữ liệu mới có thể không đọc nổi lịch sử.

Nếu chỉ gửi một file JSON mẫu qua chat, tổ chức thiếu:

- Danh tính thống nhất cho schema nào đang được sử dụng.
- Phiên bản schema nào đã được chấp thuận.
- Quy tắc tự động ngăn thay đổi phá tương thích.
- Kho tham chiếu để serializer/deserializer tra cứu writer/reader schema.
- Dòng lịch sử và audit ai đăng ký schema, khi nào, trong phạm vi nào.
- Quyền truy cập/ownership rõ ràng cho các schema được nhiều đội dùng.
- Cơ chế liên kết schema cụ thể với dữ liệu message đang chạy thực tế.

Schema Registry giúp giải quyết các nhu cầu này, tùy sản phẩm và mức tích hợp. Một số hệ sinh thái có registry trung tâm; một số dùng versioned schema artifact trong Git cùng CI; các hệ thống lớn thường kết hợp cả hai.

## 4. Schema Registry làm những việc gì?

Một registry điển hình có thể cung cấp:

1. **Lưu schema:** giữ nội dung Avro, Protobuf, JSON Schema hoặc các định dạng được hỗ trợ.
2. **Định danh:** gắn schema với ID hoặc tham chiếu được sử dụng khi mã hóa/giải mã.
3. **Nhóm phiên bản:** quản lý các version của schema theo một subject hoặc cấu trúc tương đương.
4. **Tra cứu:** cho phép client hoặc công cụ lấy schema theo ID, subject/version.
5. **Compatibility rules:** kiểm tra việc đăng ký phiên bản mới có vi phạm chính sách tương thích đã chọn hay không.
6. **Quản lý tham chiếu:** hỗ trợ các schema phụ thuộc lẫn nhau trong một số định dạng/hệ sinh thái.
7. **API quản trị:** cho phép kiểm tra, đăng ký, liệt kê version, cấu hình chính sách và phân quyền tùy sản phẩm.
8. **Tích hợp serializer/deserializer:** thư viện client có thể tự ghi schema reference vào payload hoặc header, tra cứu và cache schema.
9. **Theo dõi vận hành:** audit, metrics, dashboard hoặc thông tin đăng ký tùy triển khai.

Registry **không mặc định** là message broker và thường không lưu từng message nghiệp vụ. Broker giữ dữ liệu message theo retention/partition; Registry giữ **định nghĩa và thông tin quản lý schema**. Tính bền vững của message vẫn phụ thuộc broker và storage tương ứng.

### Sơ đồ vai trò

~~~mermaid
flowchart TB
    D[Git / .avsc .proto .json] --> CI[CI contract validation]
    CI --> R[(Schema Registry)]
    P[Order Producer + Serializer] --> R
    P --> K[(Message Broker)]
    K --> C[Consumers + Deserializers]
    C --> R
~~~

Các mũi tên đến Registry thể hiện đăng ký/tra cứu hoặc đồng bộ schema; **không nhất thiết mỗi message đi qua Registry**. Serializer thường cache schema ID hoặc nội dung schema. Consumer cũng có thể cache schema đã tra, giảm lưu lượng mạng tới registry.

## 5. Phân biệt subject, schema ID, schema version và event version

Các thuật ngữ này có ý nghĩa khác nhau, dễ nhầm khi đọc dashboard.

| Thuật ngữ | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| Message/event type | Loại sự kiện nghiệp vụ | OrderPlaced |
| Schema | Định nghĩa cấu trúc và kiểu dữ liệu | Avro record OrderPlaced |
| Subject (tùy registry) | Không gian quản lý danh sách phiên bản schema | orders.events-value |
| Schema version | Số thứ tự đăng ký lược đồ trong subject | version 3 |
| Schema ID | Định danh registry dùng để tra lược đồ | ID 418 |
| Event contract version | Phiên bản contract do domain/API quy ước | shop.order.v2 |
| Topic/queue | Nơi message được phát và nhận | orders.events |
| Producer version | Phiên bản phần mềm gửi message | ordering-service:2.8 |
| Consumer version | Phiên bản phần mềm đọc message | analytics-service:1.6 |

Ví dụ, cùng một schema ID có thể được tham chiếu ở nhiều nơi tùy thiết kế registry. **Schema version trong một subject không đồng nghĩa eventVersion được ghi trong payload**; hai khái niệm có thể tiến triển theo nhịp khác nhau.

Trong hệ sinh thái Confluent Schema Registry, subject và schema ID có quy ước cụ thể; các hệ sinh thái khác có thể dùng tên, namespace, group, artifact ID hoặc cơ chế reference khác. Khi thiết kế tài liệu, phải chỉ rõ **registry nào, API nào và encoding nào** thay vì giả định mọi sản phẩm giống nhau.

### Vì sao không chỉ ghi eventVersion=2 trong JSON?

Một field như eventVersion giúp ứng dụng hiểu quy tắc nghiệp vụ và định tuyến khi cần. Nhưng nó không tự cung cấp:

- Kho schema tập trung có thể tra theo ID.
- Compatibility check trước khi publish.
- Cơ chế sinh client typed code.
- Quy tắc permission để ai được phát hành schema.
- Lịch sử thay đổi và consumer compatibility tests.

Có thể có hệ thống nhỏ chỉ cần Git + JSON Schema + CI; Registry bổ sung giá trị khi số lượng producer/consumer và sự thay đổi tăng lên.

## 6. Ví dụ schema bằng Apache Avro

Avro là một định dạng dữ liệu nhị phân có mô hình schema. Schema có thể được khai báo bằng JSON; producer và consumer cần tuân thủ quy tắc schema resolution khi đọc/ghi.

Ví dụ OrderPlaced phiên bản ban đầu:

~~~json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "shop.order.events",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "customerId", "type": "string"},
    {"name": "totalAmount", "type": "long"},
    {"name": "occurredAt", "type": "string"}
  ]
}
~~~

Sau đó producer muốn thêm currency. Một cách phổ biến là thêm field có default để **reader mới có thể đọc message cũ** không chứa trường này:

~~~json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "shop.order.events",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "customerId", "type": "string"},
    {"name": "totalAmount", "type": "long"},
    {"name": "occurredAt", "type": "string"},
    {"name": "currency", "type": "string", "default": "VND"}
  ]
}
~~~

Trong Avro schema resolution, việc dùng default giúp **reader** tạo giá trị khi writer schema cũ không có field. Nó không có nghĩa producer tự động sinh giá trị currency cho mọi message hoặc mọi serializer/consumer khác format. Default "VND" chỉ hợp lệ về nghiệp vụ nếu hệ thống thật sự bảo đảm các message lịch sử thuộc đúng loại tiền đó; nếu từng có nhiều đơn vị tiền, gán mặc định VND sẽ làm sai dữ liệu.

Các trường hợp cần chú ý:

- Một reader mới muốn đọc dữ liệu do writer cũ ghi: cần xử lý field mới khi writer chưa có.
- Một reader cũ muốn đọc dữ liệu writer mới: reader có thể bỏ qua những field writer mới thêm theo quy tắc Avro phù hợp.
- Đổi tên field, đổi kiểu không tương thích hoặc thay nghĩa vẫn có thể phá schema resolution hoặc ngữ nghĩa.
- Một field Avro nullable dùng union với null, thường cần khai báo default và thứ tự branch phù hợp với schema.
- Dữ liệu decimal/money nên có representation và precision/scale rõ, tránh tự động dùng floating point cho tiền.

### Ví dụ biến amount thành decimal

Nếu doanh nghiệp cần multi-currency, không nên tự ý hiểu **500000** là VND hay cent. Có thể dùng logical type decimal với precision/scale phù hợp hoặc một kiểu integer đại diện đơn vị nhỏ nhất kèm currency và quy tắc xử lý. Đây là quyết định contract, không phải chỉ thay type.

## 7. Ví dụ schema bằng Protocol Buffers

Protobuf rất phổ biến trong gRPC và cũng có thể dùng mã hóa message trên broker. Với Protobuf, **field number/tag** là một phần cực kỳ quan trọng của wire contract.

~~~proto
syntax = "proto3";
package shop.order.events.v1;

message OrderPlaced {
  string event_id = 1;
  string order_id = 2;
  string customer_id = 3;
  int64 total_amount_minor = 4;
  string currency = 5;
  string occurred_at = 6;
}
~~~

Quy tắc:

- **Không đổi nghĩa field có tag 4** từ số tiền theo đơn vị nhỏ nhất sang số tiền hàng nghìn đơn vị mà giữ nguyên tag và contract.
- **Không tái sử dụng tag đã xóa**. Dùng reserved cho field name/number bị loại bỏ.
- **Không tùy tiện đổi type** vì một số thay đổi có thể đọc sai hoặc làm data mất nghĩa.
- **Không dùng enum giá trị 0** để diễn đạt một trạng thái nghiệp vụ “chắc chắn thành công” khi absence/default có thể dẫn đến 0.
- Khi cần phân biệt field vắng mặt với giá trị mặc định, sử dụng cơ chế presence như optional/oneof khi thích hợp.

Ví dụ khi bỏ một trường cũ:

~~~proto
message OrderPlaced {
  string event_id = 1;
  string order_id = 2;
  reserved 3;
  reserved "customer_id";
  int64 total_amount_minor = 4;
  string currency = 5;
  string occurred_at = 6;
}
~~~

Ví dụ reserved minh họa thao tác bảo vệ tag. Nó **không tự chứng minh** field customer_id đã được phép bỏ: còn phải kiểm tra consumer đang phụ thuộc vào field hay không, nhu cầu audit và chính sách privacy. Tùy quy tắc compatibility của registry, schema mới có thể chưa được chấp nhận vì việc xóa field.

**Protobuf schema compatibility và business compatibility không giống nhau.** Hai codebase cùng compile có thể vẫn xử lý sai khi enum có giá trị mới hoặc một field thay đổi ý nghĩa.

## 8. Ví dụ JSON Schema

Một event JSON cũng có thể được kiểm soát bằng JSON Schema.

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "title": "OrderPlaced",
  "properties": {
    "eventId": {"type": "string", "minLength": 1},
    "orderId": {"type": "string", "minLength": 1},
    "customerId": {"type": "string"},
    "amountMinor": {"type": "integer", "minimum": 0},
    "currency": {"type": "string", "pattern": "^[A-Z]{3}$"}
  },
  "required": ["eventId", "orderId", "amountMinor", "currency"],
  "additionalProperties": false
}
~~~

Đây là ví dụ để giải thích schema validation, không phải quy định duy nhất cho mọi loại OrderPlaced. **additionalProperties: false** cho phép kiểm soát chặt field lạ, nhưng cũng có thể làm consumer/validator cũ từ chối payload khi producer thêm một field mới. Điều kiện này ảnh hưởng khả năng mở rộng hợp đồng.

Tùy registry và implementation, compatibility checking của JSON Schema có thể có các quy tắc riêng về required fields, optional properties, điều kiện phức hợp và keyword. Không áp dụng máy móc kết luận từ Avro hoặc Protobuf sang JSON Schema.

### Lưu ý về JSON Schema và JSON data

- JSON Schema là tài liệu mô tả/kiểm tra dữ liệu; nó không tự thay đổi cách JSON được truyền qua broker.
- Một message JSON thuần có thể không chứa schema ID. Registry integration phải định nghĩa rõ cách client tìm schema.
- Một số serializer kết hợp schema ID với payload JSON bằng framing riêng; đây là quy ước thư viện/sản phẩm, không phải thuộc tính bắt buộc của mọi JSON event.
- Schema validation có thể chặn message không đúng cấu trúc; nhưng không xác minh được một khoản thanh toán thực sự đã thành công nếu chỉ dựa vào field status.

## 9. Compatibility: điều gì cần tương thích với điều gì?

Trong hệ thống bất đồng bộ, luôn có **writer schema** (producer dùng khi ghi) và **reader schema** (consumer dùng khi đọc/diễn giải). Việc nói “schema v2 tương thích với v1” mà không rõ chiều rất dễ dẫn đến rollout sai.

Định nghĩa thực hành:

- **Backward compatibility:** consumer/reader dùng schema mới có khả năng đọc dữ liệu được tạo theo schema cũ. Với một số hệ sinh thái, BACKWARD là chính sách kiểm tra schema mới đối với schema trước.
- **Forward compatibility:** consumer/reader dùng schema cũ có khả năng đọc dữ liệu theo schema mới.
- **Full compatibility:** hỗ trợ cả hai chiều tương thích.
- **None:** registry không bắt các ràng buộc compatibility theo chính sách này. Đây không phải bảo đảm mọi thay đổi đều an toàn.
- **Transitive:** kiểm tra schema mới với **tất cả phiên bản có liên quan trước đó** trong subject, thay vì chỉ một phiên bản trước gần nhất.

Cần đọc tài liệu sản phẩm đang dùng vì cách đánh giá compatibility phụ thuộc **định dạng schema**, phép biến đổi, tên subject và version history.

### Bảng trực giác

| Chế độ | Cặp cần hỗ trợ theo chiều | Hệ quả điển hình |
| --- | --- | --- |
| BACKWARD | Reader mới đọc writer cũ | Tốt cho consumer nâng cấp trước khi replay dữ liệu cũ |
| FORWARD | Reader cũ đọc writer mới | Quan trọng khi producer nâng cấp trước consumer cũ |
| FULL | Cả reader mới/old và writer old/new | Tạo khoảng chuyển giao linh hoạt hơn |
| BACKWARD_TRANSITIVE | Reader mới đọc mọi writer trước được lưu | Hữu ích cho replay lịch sử dài |
| FORWARD_TRANSITIVE | Reader của mọi version cũ đọc writer mới | Hữu ích khi còn consumer rất cũ |
| FULL_TRANSITIVE | Cả hai chiều trên mọi version lịch sử | Khắt khe, dễ giới hạn kiểu thay đổi |
| NONE | Không kiểm tra tương thích theo policy | Chỉ dùng khi có migration/consumer plan cụ thể |

Đây là **ngữ nghĩa mức khái niệm**. Sản phẩm có thể đặt tên hoặc quy tắc thêm khác nhau. Không dùng bảng như cam kết rằng mọi schema thay đổi trên mọi định dạng sẽ được chấp nhận.

### Cách đọc chữ “transitive”

Giả sử có schema v1, v2, v3 và chuẩn bị đăng ký v4:

~~~text
Không transitive:
    v4 được so với v3 theo chính sách.

Transitive:
    v4 được so với v1, v2, v3 theo chính sách.
~~~

Ngay cả khi v4 tương thích với v3, chưa chắc v4 tương thích với v1 đã được dữ liệu hóa trong các log cũ. Nếu consumer có thể replay message nhiều năm trước, transitive thường đáng cân nhắc.

## 10. Ví dụ rollout: thêm trường mới

Hệ thống ban đầu có OrderPlaced v1:

~~~json
{
  "eventId": "evt-1",
  "orderId": "ORD-1001",
  "amountMinor": 500000
}
~~~

Muốn thêm currency và có thể dùng nhiều loại tiền trong tương lai.

### Hướng tiến hóa an toàn

1. **Chốt ngữ nghĩa mới:** amountMinor là giá trị theo đơn vị nhỏ nhất của currency, hoặc đơn vị khác đã được định nghĩa rõ.
2. **Đánh giá lịch sử:** các event cũ có thật sự luôn là VND không? Nếu không, không tự đặt default VND rồi coi dữ liệu chính xác.
3. **Cập nhật contract:** bổ sung field theo cách tương thích với consumer dự kiến.
4. **Kiểm tra registry:** schema mới có đạt compatibility policy với version mục tiêu không?
5. **Cập nhật consumer:** hỗ trợ trường mới và có hành vi hợp lệ với dữ liệu cũ.
6. **Triển khai consumer/adapter cần thiết:** bảo đảm các consumer đang chạy hiểu message sau thay đổi.
7. **Triển khai producer:** phát event theo schema đã đăng ký.
8. **Quan sát:** theo dõi deserialization errors, DLQ, lag và các chỉ số nghiệp vụ.
9. **Migration/backfill:** nếu cần sửa dữ liệu lịch sử, triển khai chiến lược riêng và ghi nhận provenance.

Nếu dùng **BACKWARD** với producer nâng cấp trước, vẫn có thể phá consumer cũ vì backward chỉ nói reader mới có thể đọc writer cũ. Muốn producer mới hoạt động với reader cũ, phải bảo đảm **forward compatibility thực sự** và consumer behavior đã được kiểm chứng.

### Trường hợp phải thay nghĩa tiền

Giả sử totalAmount v1 là “số VND nguyên”, còn v2 muốn dùng “số cent USD”. Đó là **semantic breaking change**. Kể cả tag/kiểu vẫn là long, registry có thể không phát hiện vì dữ liệu cùng cấu trúc. Cách xử lý an toàn là có field và định nghĩa mới, hoặc loại event/contract version mới cùng migration rõ ràng, thay vì âm thầm diễn giải lại dữ liệu cũ.

## 11. Mối quan hệ giữa compatibility mode và trình tự triển khai

Có hai câu hỏi riêng:

1. **Registry cho phép đăng ký schema mới không?**
2. **Các consumer đang chạy có thực sự đọc và xử lý đúng payload mới không?**

Kiểm tra một phần không trả lời thay phần còn lại.

### Mẫu consumer-first

- Đưa các consumer mới có khả năng hiểu schema/field mới vào vận hành.
- Bảo đảm chúng tiếp tục đọc được event cũ.
- Sau đó producer phát message với field mới.
- Giữ hỗ trợ dữ liệu cũ đủ lâu theo retention/replay.

Mẫu này thường thuận lợi khi thay đổi contract dạng mở rộng, nhưng không miễn việc kiểm tra reader cũ còn hoạt động.

### Mẫu producer-first

- Producer mới phát schema mới trong khi consumer cũ vẫn chạy.
- Cần bảo đảm consumer cũ xử lý được message mới.
- Khi an toàn, consumer được cập nhật dần.

Mẫu này đòi hỏi hiểu rõ **forward compatibility** hoặc khả năng consumer cũ bỏ qua field mới, cùng điều kiện không gây semantic break.

### Dual publish / parallel versions

Với thay đổi không thể tương thích, producer có thể tạm phát hai loại event hoặc hai topic/subject version riêng trong giai đoạn chuyển đổi. Điều này có chi phí:

- Cần tránh consumer xử lý trùng hai bản tương đương.
- Phải có kế hoạch ngừng bản cũ, thời hạn duy trì và cách quan sát còn consumer nào đang dùng.
- Cần bảo đảm nguồn dữ liệu tạo cả hai representation nhất quán theo chính sách.
- Có thể cần schema alias/reference hoặc adapter để giữ compatibility tại boundary.

**Đừng coi dual publish là miễn phí.** Nó giảm rủi ro cho consumer cũ nhưng tăng phức tạp vận hành và duplicate handling.

## 12. Schema ID được dùng khi serialize/deserialize như thế nào?

Một luồng điển hình với serializer có tích hợp registry:

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Producer
    participant R as Schema Registry
    participant B as Broker
    participant C as Consumer

    P->>R: Register / Lookup writer schema
    R-->>P: Schema ID
    P->>P: Serialize payload + schema reference
    P->>B: Publish message bytes
    B-->>C: Deliver bytes
    C->>C: Extract schema reference
    C->>R: Fetch schema by ID if not cached
    R-->>C: Writer schema
    C->>C: Decode with reader expectations
~~~

**Broker thường không hỏi Registry cho từng message.** Việc tra cứu có thể nằm ở producer/consumer serializer/deserializer hoặc một pipeline validation khác tùy thiết kế. Nhiều client có cache schema để giảm round trip.

### Ví dụ framing theo hệ sinh thái Confluent

Một số serializer tương thích với **Confluent wire format** dùng cấu trúc có magic byte và schema ID để nhận diện lược đồ; ví dụ phổ biến là byte mở đầu rồi một mã schema ID 4 byte theo thứ tự quy ước của format, sau đó là dữ liệu được mã hóa. Với Protobuf còn có thông tin message indexes theo format tương ứng.

**Không xem đây là chuẩn của Kafka hay của tất cả registry.** Kafka chỉ lưu key/value bytes; các thư viện serializer chọn representation. Registry khác hoặc cấu hình khác có thể dùng encoding, header hoặc ID strategy khác. Consumer phải dùng deserializer tương thích với chính wire format producer đã chọn.

### Registry gặp sự cố thì hệ thống có dừng không?

Phụ thuộc client và cache:

- Producer đã cache schema ID có thể tiếp tục gửi theo chính sách nếu không cần tương tác Registry nữa.
- Consumer đã cache writer schema có thể tiếp tục giải mã những ID đã thấy.
- Producer hoặc consumer gặp schema chưa biết có thể cần truy Registry.
- Việc đăng ký schema mới có thể thất bại khi Registry không khả dụng hoặc thiếu quyền.
- Nếu client cấu hình bắt buộc kiểm tra Registry mọi lần, mức ảnh hưởng lớn hơn.

Không thể kết luận “Registry down thì mọi message đều ngừng” hoặc “Registry down không ảnh hưởng” khi chưa biết serializer, cache, ACL và đường triển khai.

## 13. Subject naming và phạm vi kiểm tra tương thích

Trong các registry có khái niệm **subject**, mỗi subject thường là một dòng phiên bản schema được kiểm tra theo một compatibility policy. Chọn subject đúng quan trọng vì nó xác định **những schema nào phải tương thích với nhau**.

Trong cách dùng Confluent-style, các chiến lược thường gặp gồm:

| Strategy | Ý tưởng | Tình huống |
| --- | --- | --- |
| TopicNameStrategy | Subject dựa vào topic cùng key/value, ví dụ orders.events-value | Một schema family/value contract theo topic |
| RecordNameStrategy | Subject theo fully-qualified record name | Nhiều record type trong topic với quản lý version theo record |
| TopicRecordNameStrategy | Kết hợp topic và fully-qualified record name | Cần tách contract theo record type trong một topic cụ thể |

Đây là **tên chiến lược của một hệ sinh thái cụ thể**, không phải khái niệm bắt buộc trên mọi registry. Khi broker topic chứa nhiều event type, subject-per-topic đơn giản có thể buộc những loại message độc lập vào cùng một compatibility history không mong muốn. Ngược lại, subject theo record làm tăng số dòng contract cần quản lý và yêu cầu consumer hiểu cách định tuyến message type.

### Ví dụ

~~~text
Topic: orders.events
Record A: shop.order.OrderPlaced
Record B: shop.order.OrderCancelled

Topic-oriented subject:
  orders.events-value

Record-oriented subjects:
  shop.order.OrderPlaced
  shop.order.OrderCancelled
~~~

Nếu chủ đề orders.events chứa nhiều loại event, phải quyết định consumer phân biệt loại bằng metadata, fully qualified record name, oneof/union hoặc routing convention nào. Không chỉ đổi subject naming strategy trong production mà chưa kiểm tra wire format, serializers, registry history và downstream dependencies.

### Key schema và value schema

Kafka message có **key** và **value**. Cả hai có thể có schema riêng. Key thường liên quan đến partitioning, ordering và khả năng compact log.

Ví dụ:

~~~text
key   = orderId ("ORD-1001")
value = OrderPlaced(orderId, customerId, amountMinor, ...)
~~~

Đổi kiểu key từ string sang record hoặc đổi ý nghĩa key từ orderId sang customerId có thể khiến message cùng order bị phân phối sang partition khác, làm ảnh hưởng thứ tự xử lý. **Registry kiểm tra schema key không thay thế đánh giá partitioning semantics.**

## 14. Contract version không phải schema version

Một producer có thể bổ sung field tùy chọn vào schema v5 nhưng vẫn giữ cùng contract nghiệp vụ OrderPlaced v1. Ngược lại, một semantic breaking change có thể đòi hỏi event contract v2 dù cấu trúc ít thay đổi.

Hãy phân biệt:

- **Schema version**: một revision được đăng ký trong dòng lịch sử của subject.
- **Event type/version**: danh tính giao tiếp mà các team định nghĩa và cam kết.
- **Software version**: phiên bản triển khai của service.
- **Broker offset**: vị trí message trong partition log, không phải version schema.
- **Database schema version**: cấu trúc lưu trữ nội bộ của producer, không phải contract public của event.

Không nên đặt tên event “OrderPlacedV2” cho mọi lần thêm field nhỏ. Nhưng cũng không ép hai semantics khác nhau vào cùng một event type chỉ vì serializer vẫn giải mã được.

## 15. Tính đúng đắn của dữ liệu: syntax khác semantics

Một schema có thể cho phép:

~~~json
{
  "eventType": "PaymentSucceeded",
  "orderId": "ORD-1001",
  "amountMinor": 0,
  "currency": "VND"
}
~~~

Nếu schema chỉ yêu cầu amountMinor là integer không âm, message này có thể được xem là hợp lệ về cấu trúc. Nhưng liệu PaymentSucceeded với amount=0 có hợp lệ? Nó phụ thuộc **quy tắc thanh toán**: có đơn miễn phí, voucher, hoặc trường hợp không thu tiền; tên event có phản ánh semantics phù hợp không?

Schema Registry thường **không thể xác minh** các vấn đề:

- Tiền đã thực sự được provider xác nhận hay chưa.
- paymentId có thuộc đúng orderId không.
- Event được phát trước hay sau transaction commit.
- Một order có bị gửi PaymentSucceeded hai lần không.
- Reservation còn hiệu lực hay đã hết hạn.
- Số tiền có bằng nghĩa vụ thanh toán theo quote được chốt không.
- User/service có quyền truy cập dữ liệu hay không.

Cần kết hợp domain validation, transaction, authorization, idempotency, event outbox, consumer state machine và monitoring. **Schema validity là điều kiện cần trong nhiều trường hợp, không phải điều kiện đủ cho tính đúng đắn nghiệp vụ.**

## 16. Triển khai pipeline quản lý schema trong CI/CD

Một quy trình có thể đưa schema vào repository cùng mã nguồn hoặc contract repository được quản lý riêng, ví dụ:

~~~text
contracts/
  orders/
    order-placed-v1.avsc
    order-cancelled-v1.avsc
  payments/
    payment-succeeded-v1.proto
  shipping/
    shipment-created.schema.json
~~~

Đường dẫn trên là ví dụ. Dù dùng mono-repo hay multi-repo, nguyên tắc quan trọng là **có bản contract được review và tái tạo được**.

### Pipeline đề xuất

~~~mermaid
flowchart TD
    PR[Pull Request thay schema] --> L[Lint / Parse / Format]
    L --> C[Compatibility Check với registry/baseline]
    C --> T[Producer / Consumer Contract Tests]
    T --> S[Security / PII / Ownership Review]
    S --> M[Merge khi đạt policy]
    M --> D[Register schema theo môi trường]
    D --> R[Deploy consumers/producers theo rollout plan]
    R --> O[Monitor error / lag / business outcomes]
~~~

### Bước 1: Kiểm tra cú pháp

- File Avro/Protobuf/JSON Schema có parse được không?
- Những field/tag number có trùng hoặc trái quy định không?
- Field name, enum, namespace và type có theo convention không?
- Schema reference/dependency có tồn tại không?

### Bước 2: Kiểm tra compatibility

- PR đang sửa subject nào?
- Compatibility mode của subject là gì?
- Kiểm tra với version ngay trước hay toàn lịch sử?
- Các schema cũ còn được replay không?
- Cần migration hay dual format không?

### Bước 3: Contract testing

- Producer có thể tạo message hợp lệ theo schema đã đăng ký không?
- Consumer cũ có đọc đúng message mới không?
- Consumer mới có đọc dữ liệu lịch sử theo writer schema cũ không?
- Có field optional/unknown/default/enum mới nào gây thay đổi logic không?
- Deserializer có xử lý unknown schema ID và lỗi registry đúng cách không?

### Bước 4: Kiểm tra semantics và quyền riêng tư

- Field mới có thông tin cá nhân hay bí mật không?
- Có thay đổi đơn vị tiền hoặc timezone không?
- Tên event còn phản ánh đúng sự thật nghiệp vụ không?
- Field mới có tạo quyền truy cập dữ liệu cho consumer không nên thấy không?
- Ai chịu trách nhiệm phê duyệt nếu contract phục vụ nhiều team?

### Bước 5: Đăng ký và triển khai

- Schema được đăng ký ở registry của môi trường tương ứng qua pipeline có quyền rõ.
- Producer chỉ phát message theo schema đã chấp thuận.
- Consumer/producer được rollout theo hướng tương thích đã kiểm chứng.
- Có quan sát và phương án rollback/forward-fix khi phát hiện sự cố.

**Không nên phụ thuộc chỉ vào auto.register.schemas=true ở production** nếu điều đó cho phép một service vô tình đăng ký schema mới ngoài review. Chính sách cụ thể tùy tổ chức: môi trường dev có thể auto register để thuận tiện; production thường nên quản lý chặt ownership, quyền và version promotion.

## 17. Ví dụ end-to-end: OrderPlaced v1 sang v2

Giả sử có ba consumer:

- Inventory: cần orderId và các dòng hàng.
- Notifications: cần orderId và customerRef.
- Analytics: cần amount và currency để tổng hợp.

Event ban đầu:

~~~json
{
  "eventId": "evt-101",
  "eventType": "OrderPlaced",
  "orderId": "ORD-1001",
  "customerRef": "CUS-17",
  "amountMinor": 500000
}
~~~

Doanh nghiệp muốn đa tiền tệ, cần currencyCode.

### Bước A: xác định ý nghĩa business

Người thiết kế phải trả lời:

- Dữ liệu trước đây có chắc chắn chỉ dùng VND không?
- amountMinor hiện có nghĩa “đơn vị nhỏ nhất của tiền” hay “đồng nguyên”?
- Có trường hợp tiền tệ không có số chữ số thập phân giống nhau không?
- Analytics phải xử lý lịch sử ra sao?
- Price quote được chốt ở đâu và có currency riêng không?

Không giải quyết các câu hỏi này bằng việc thêm một trường string rồi coi nhiệm vụ xong.

### Bước B: thay đổi schema

Trong Avro, trường mới có thể có default **chỉ nếu thật sự hợp lệ**. Nếu không có default đúng cho dữ liệu cũ, cần migration, adapter hoặc quy ước representation mới. Với Protobuf, trường mới nhận tag chưa dùng; consumer vẫn phải kiểm tra absence/default nếu bắt buộc dữ liệu mới có giá trị.

### Bước C: rollout có kiểm soát

1. Cập nhật Analytics để nhận biết currency và cách xử lý lịch sử.
2. Cập nhật Inventory/Notifications để bỏ qua field mới một cách an toàn nếu hợp đồng cho phép.
3. Chạy compatibility check và consumer contract tests.
4. Đăng ký schema mới với subject phù hợp.
5. Deploy Ordering producer phát dữ liệu mới.
6. Theo dõi invalid payload, deserialization errors, tổng tiền bất thường, DLQ.
7. Duy trì khả năng replay dữ liệu cũ theo retention và yêu cầu audit.

### Bước D: xử lý sự cố

Nếu một consumer cũ không đọc được message mới, cần:

- Dừng hoặc giới hạn rollout producer nếu tác động nghiêm trọng và có phương án an toàn.
- Khôi phục consumer bằng bản tương thích hoặc triển khai adapter.
- Bảo đảm offset/retry/DLQ không làm mất dữ liệu ngoài dự kiến.
- Không lén sửa schema ID đã dùng để trỏ đến định nghĩa khác.
- Đối soát kết quả nghiệp vụ nếu có message bị bỏ qua hoặc xử lý sai.

**Rollback phần mềm không có nghĩa dữ liệu trên broker quay về schema cũ.** Những message schema mới đã phát vẫn có thể còn trong log và cần consumer xử lý được hoặc có quy trình chuyển đổi.

## 18. Replay và lưu trữ lịch sử: tại sao transitive quan trọng?

Kafka và một số nền tảng streaming cho phép consumer đọc lại message cũ theo retention hoặc từ kho lưu archive. Consumer mới có thể phải đọc writer schema đã phát từ vài năm trước.

Ví dụ:

~~~text
2024: OrderPlaced writer schema v1
2025: OrderPlaced writer schema v2
2026: OrderPlaced writer schema v3
2027: Analytics rebuild từ log cũ -> cần đọc v1, v2, v3
~~~

Ngay cả khi v3 được kiểm tra với v2 và pass, chưa chắc nó đọc được v1 dưới mọi thay đổi tích lũy. **BACKWARD_TRANSITIVE** có thể hỗ trợ kiểm tra hướng này trên lịch sử subject, nhưng còn phụ thuộc liệu dữ liệu thật sự có đủ để tái tạo semantics.

Một consumer replay có thể:

1. Đọc schema ID của từng message.
2. Tra writer schema tương ứng (hoặc dùng cache).
3. Giải mã message theo writer schema.
4. Chuyển đổi thành domain/read model hiện tại theo migration policy.
5. Xử lý trùng và side effect được kiểm soát để không gửi email/thu tiền lại khi replay.

Không được gắn **replay** với việc chạy lại toàn bộ side effects production. Consumer rebuild read model thường phải tách tác động nghiệp vụ và output side effects theo mục đích.

### Nếu Registry xóa schema cũ

Nếu broker còn message chứa schema ID cũ nhưng registry không còn tra được schema, một consumer mới có thể không giải mã được dữ liệu. Vì vậy chính sách xóa schema, backup/restore, retention và khả năng khôi phục phải được phối hợp. Một số registry phân biệt soft delete và permanent delete; chi tiết phải theo sản phẩm.

## 19. Registry và các vấn đề nó không giải quyết

| Nhu cầu | Registry hỗ trợ gì? | Cần thêm thành phần gì? |
| --- | --- | --- |
| Thống nhất cấu trúc message | Lưu/định danh/kiểm tra schema | Domain contract documentation |
| Thay đổi field an toàn | Compatibility check theo policy | Consumer tests và rollout plan |
| Đọc dữ liệu nhiều version | Tra writer schema theo ID | Deserializer và logic reader phù hợp |
| Message không trùng | Không tự bảo đảm | eventId, idempotent consumer, unique constraints |
| Thứ tự sự kiện | Không tự bảo đảm | Partition key, sequence/version, state machine |
| Giao message bền vững | Registry không lưu message | Broker retention, replication, backups |
| Một transaction xuyên service | Không tự cung cấp | Local transaction, outbox, Saga |
| Quyền xem dữ liệu nhạy cảm | Có thể có RBAC cho schema | Message ACL, encryption, data governance |
| Event đúng nghĩa nghiệp vụ | Schema không đủ | Domain invariants và producer governance |
| Xử lý timeout producer/consumer | Không quyết định retry | Retry, DLQ, reconciliation, observability |
| Dừng breaking change | Ngăn theo quy tắc được cấu hình | Semantic review và dependency inventory |
| Sinh code typed models | Hỗ trợ tùy toolchain | Codegen build pipeline và SDK version |

**Registry không phải người quản lý sự thật nghiệp vụ.** Nếu producer phát PaymentSucceeded trước khi transaction thanh toán thực sự được xác nhận, payload có thể hợp lệ về schema nhưng nghiệp vụ vẫn sai.

## 20. Quản lý producer và consumer ownership

Mỗi sự kiện hoặc contract cần có người chịu trách nhiệm rõ:

~~~text
Event: OrderPlaced
Owner: Ordering Team
Consumers: Inventory, Notifications, Analytics
Schema subject: orders.events-value (ví dụ)
Source schema: contracts/orders/order-placed.avsc
Compatibility policy: BACKWARD_TRANSITIVE (ví dụ)
Semantic definition: đơn đã được ghi và chấp nhận xử lý
Change policy: PR + producer/consumer contract tests
Production registration: CI service account
Deprecation: thông báo, theo dõi consumer, migration
Contact/on-call: Ordering Team
~~~

Đây là mẫu tài liệu, không phải khai báo có thật của một công ty. Giá trị quan trọng là **mỗi contract có owner và consumer map**, để không ai phát hành breaking change mà không biết phía nào bị ảnh hưởng.

### Những câu hỏi khi phê duyệt schema mới

- Producer nào đang phát loại event này?
- Có nhiều producer trên cùng một subject không?
- Consumer nào đang dùng field bị đổi/xóa?
- Có consumer chỉ chạy theo lịch hoặc thường xuyên replay không?
- Policy hiện tại kiểm tra transitive hay chỉ phiên bản trước?
- Có schema reference hay thư viện mã sinh chung gây phụ thuộc không?
- Có buộc consumer nâng cấp đồng thời không? Nếu có, vì sao?
- Rollback cần làm gì với message schema mới đã nằm trên log?
- Ai xử lý khi registry hoặc deserializer gặp lỗi?
- Thay đổi có ảnh hưởng privacy/compliance hoặc giới hạn truy cập không?

## 21. Không để Registry trở thành điểm lỗi chung

Registry là thành phần metadata quan trọng, nên cần xem xét availability và vận hành:

- **Replication/HA:** không để một instance registry duy nhất làm điểm lỗi của hệ thống nếu producer/consumer cần tra cứu schema.
- **Backup/restore:** giữ nội dung schema, subject history và ID mapping có thể khôi phục. Việc khôi phục không được tùy ý thay ID mà dữ liệu lịch sử đã tham chiếu.
- **Cache ở client:** hỗ trợ giảm round trip, nhưng phải hiểu TTL/invalidation và cách xử lý schema mới.
- **Quản lý thay đổi:** version registry service, serializer libraries và wire format phải tương thích.
- **Access control:** phân biệt quyền đọc schema, đăng ký mới, thay policy, xóa schema và quản trị.
- **Rate limits/capacity:** tránh một lỗi client gây flood lookup/register.
- **Network/TLS:** bảo vệ kết nối client-registry, không phát lộ credential.
- **Disaster recovery:** xây kịch bản phục hồi cả broker và registry nếu có phụ thuộc schema ID.
- **Environment isolation:** schema dev/staging/prod không được trộn lẫn tùy tiện; có kế hoạch promotion phù hợp.

Một số môi trường có thể cần Schema Registry hoạt động cùng control plane hoặc service account đặc biệt. Thiết kế cụ thể tùy triển khai; không suy ra mặc định từ một ví dụ.

### Cẩn thận khi cache

Cache tăng hiệu năng nhưng khiến sự cố có vẻ “chỉ một vài instance gặp lỗi”. Một số consumer đã cache schema ID v42 nên vẫn chạy; instance mới khởi động lại phải tra registry và thất bại. Alert nên phân biệt lỗi lookup, lỗi authorization, schema not found và lỗi parse.

## 22. Error handling: schema nào lỗi ở giai đoạn nào?

Có ít nhất ba điểm lỗi:

**1. Build/registration time:** schema không parse được, compatibility policy từ chối, bị thiếu reference hoặc không có quyền đăng ký.

**2. Serialization time:** producer không thể mã hóa payload theo schema, giá trị thiếu, type sai, schema ID chưa đăng ký hoặc registry unavailable khi cần lookup/register.

**3. Deserialization/processing time:** consumer không tìm thấy schema ID, bytes không đúng wire format, reader không tương thích, enum/value không được xử lý hoặc message hợp lệ nhưng domain rule thất bại.

Các điểm lỗi nên có cách xử lý riêng:

| Thời điểm | Ví dụ | Hành động |
| --- | --- | --- |
| CI | Avro field mới phá BACKWARD compatibility | Chặn merge và yêu cầu migration |
| Deploy | Producer auto-register bị 403 | Kiểm tra quyền và pipeline, không vô hiệu ACL bừa |
| Publish | Payload thiếu field bắt buộc | Sửa producer/validation, không retry nguyên payload vô hạn |
| Consume | Unknown schema ID | Kiểm tra registry, serializer, migration, xử lý bảo toàn message |
| Consume | Schema decode được nhưng enum mới không biết | Chuyển trạng thái unknown/alert theo policy, không coi là SUCCESS |
| Replay | Schema cũ bị xóa vĩnh viễn | Khôi phục registry metadata/backup thích hợp |
| Business | Order amount sai đơn vị dù schema hợp lệ | Dừng ảnh hưởng, đối soát, sửa contract semantics |
| Operation | Consumer crash loop với poison message | Quarantine/DLQ có theo dõi, sửa rồi replay an toàn |

### DLQ không phải nơi xóa lỗi

Khi gặp message không thể giải mã hoặc business validation thất bại, một số pipeline chuyển message sang **dead-letter queue** cùng metadata an toàn để xử lý sau. Cần quyết định:

- Giữ raw payload hay reference đến message gốc?
- Giữ topic/partition/offset/schema ID như thế nào?
- Ai có quyền đọc payload, có chứa PII không?
- Khi sửa consumer, replay có gây gửi email/thu tiền/trừ tồn lại không?
- Theo dõi message mắc lỗi đến khi có kết quả đối soát thế nào?

Không nên im lặng skip dữ liệu quan trọng chỉ để consumer lag giảm.

## 23. Thứ tự, key, idempotency và schema evolution

Schema Registry không thay thế các quyết định về phân vùng và thứ tự. Ví dụ một topic Kafka dùng **orderId làm partition key** để các event của cùng order thường được ghi về cùng partition theo key-to-partition mapping được cấu hình.

~~~text
key=ORD-1001, value=OrderPlaced(v1)
key=ORD-1001, value=OrderPaid(v2)
key=ORD-1001, value=OrderCancelled(v2)
~~~

Dù các event theo một order đi cùng partition, consumer vẫn phải xét thứ tự xử lý khi retry, parallelism, rebalancing hoặc có producer không tuân theo key convention. Nếu đổi key sang customerId trong lần nâng schema, các event cùng order có thể chuyển partition, ảnh hưởng giả định ordering của consumer.

Cần bảo đảm:

- **Key contract** được quản lý độc lập với value schema khi cần.
- **eventId** chống xử lý trùng; đừng dùng schema ID thay cho event ID.
- **aggregateVersion/sequence** giúp consumer tránh áp trạng thái lùi khi hợp lý.
- **Idempotency** ngăn side effects lặp khi broker gửi lại hoặc consumer restart.
- **Outbox** giúp gắn DB commit với việc lưu ý định phát event trong transaction cục bộ.
- **Replay controls** tránh thực thi lại tác vụ bên ngoài không mong muốn.

Schema registry chỉ giúp các bên hiểu **hình dạng message**; quy tắc thứ tự và hành động của consumer vẫn là trách nhiệm kiến trúc.

## 24. Bảo mật, PII và schema governance

Bản thân schema cũng có thể lộ **tên field nhạy cảm hoặc cấu trúc dữ liệu nội bộ**, dù không chứa giá trị cụ thể. Quản trị registry nên phù hợp với chính sách bảo mật:

1. Chỉ người/CI account có quyền mới được đăng ký hoặc xóa schema trên subject nhạy cảm.
2. Không gửi passwords, raw payment card data, secret token hay private keys vào event.
3. Hạn chế chia sẻ email/địa chỉ/điện thoại khi một consumer chỉ cần customerId.
4. Dùng cơ chế phân quyền broker/topic để kiểm soát ai có thể đọc message; RBAC của Registry **không thay thế** broker ACL.
5. Áp dụng encryption in transit/at rest theo yêu cầu; schema hợp lệ không có nghĩa payload đã an toàn.
6. Định nghĩa retention, khả năng xóa dữ liệu cá nhân và phương án xử lý event đã được phát ra nhiều hệ thống.
7. Không chèn dữ liệu nhạy cảm vào log của serializer/deserializer khi xảy ra lỗi schema.
8. Khi thêm field về danh tính, cần đánh giá những consumer hiện tại sẽ thấy giá trị mới dù họ chỉ tiêu thụ field cũ.

Ví dụ, thêm **customerEmail** vào OrderPlaced cho tiện Notifications có thể vô tình phân phối email cho Analytics và nhiều consumer khác. Một lựa chọn tốt hơn là truyền customerRef và để consumer được cấp quyền gọi API hoặc dùng event riêng trong phạm vi được phép.

## 25. Các lỗi tư duy phổ biến

### “Có Schema Registry là không bao giờ có breaking change”

Sai. Registry chặn được một số thay đổi cấu trúc theo policy và khả năng phân tích của định dạng. Nó không biết mọi ngữ nghĩa và có thể cấu hình NONE hoặc kiểm tra phạm vi quá hẹp.

### “Schema mới pass BACKWARD nên producer deploy trước là luôn an toàn”

Sai. BACKWARD chủ yếu nói reader mới đọc writer cũ. Producer mới với reader cũ cần kiểm tra chiều ngược lại và hành vi consumer thực tế.

### “Schema version là event version”

Sai. Version đăng ký của subject là metadata registry; event contract version là quyết định ở cấp hợp đồng nghiệp vụ.

### “Field có default nên dữ liệu lịch sử chắc chắn đúng”

Sai. Default chỉ giải quyết một tình huống schema resolution. Nếu lịch sử có nhiều loại tiền, default VND có thể tạo sai lệch nghiệp vụ.

### “Một schema ID mô tả duy nhất cách người dùng phải xử lý message”

Sai. Schema ID chỉ giúp tìm schema/encoding theo hệ sinh thái. Consumer vẫn cần domain semantics, authorization và handling của unknown values.

### “Kafka tự hiểu Avro/Protobuf”

Sai. Kafka broker thường xử lý bytes và metadata của record; chính producer/consumer serializer, schema registry integration hoặc các dịch vụ được cấu hình sẽ xử lý schema cụ thể.

### “Đổi key không liên quan schema”

Sai. Dù value schema không đổi, đổi key hoặc serialization strategy có thể thay partitioning, compaction và thứ tự theo aggregate.

### “Rollback producer là xóa được message theo schema mới”

Sai. Message đã publish có thể còn trong topic và cần được xử lý theo schema đã ghi lúc đó.

### “Registry lỗi thì chắc chắn toàn bộ message bus ngừng”

Sai nếu client còn cache và không cần lookup; cũng sai nếu cho rằng registry hoàn toàn không ảnh hưởng. Phải đánh giá serializer, cache và availability thực tế.

### “Message decode OK nghĩa là nghiệp vụ thành công”

Sai. Parser thành công không chứng minh business invariant và side effects được xử lý đúng.

## 26. Bài thực hành: thiết kế contract cho OrderPlaced

### Bài A — Mô tả contract

Hãy viết contract cho OrderPlaced với ít nhất:

~~~text
eventId          : định danh duy nhất của sự kiện
eventType        : OrderPlaced
aggregateId      : orderId
aggregateVersion : version của Order
occurredAt       : thời điểm sự thật nghiệp vụ xảy ra
customerRef      : tham chiếu khách hàng
lines            : SKU + quantity + giá đã chốt nếu cần
amountMinor      : số tiền với đơn vị được định nghĩa
currency         : mã tiền
correlationId    : mã liên kết checkout
~~~

Sau đó trả lời:

- Event được phát khi Order đã commit hay khi request mới đến?
- Event có chứa PII không cần thiết không?
- Ordering hay Payments có quyền quyết định amount?
- Consumer nào cần từng field?
- Thứ tự event theo orderId được đảm bảo tới đâu?

### Bài B — Thêm field tùy chọn

Từ schema v1 không có currency, bổ sung currency ở v2. Hãy mô tả kế hoạch để consumer mới đọc message cũ và consumer cũ đọc message mới. Giải thích khi nào dùng default có thể hợp lý và khi nào bắt buộc migration.

### Bài C — Xóa field

Một field legacyCustomerId từng được producer phát nhưng hiện không dùng trong client mới. Hãy liệt kê các bước cần làm trước khi xóa, từ inventory consumer, contract tests, deprecation đến cách reserved field number với Protobuf.

### Bài D — Replay ba năm dữ liệu

Analytics cần rebuild projection từ topic có dữ liệu v1, v2, v3. Registry đang dùng BACKWARD không transitive. Hãy giải thích tại sao pass compatibility với v3 không chứng minh reader v4 giải mã/diễn giải đúng v1, và kế hoạch kiểm thử lịch sử.

### Bài E — Schema Registry unavailable

Producer đã biết schema ID v10, consumer mới vừa restart và chưa cache schema tương ứng. Registry bị mất kết nối. Hãy giải thích vì sao hai thành phần có thể bị ảnh hưởng khác nhau, cùng các biện pháp observability và HA.

### Bài F — Consumer xử lý sai ngữ nghĩa

Schema mới giữ amountMinor kiểu long nhưng producer bắt đầu gửi số tiền theo đơn vị khác. Registry pass và JSON/Avro parse vẫn đúng; Analytics báo doanh thu tăng 100 lần. Đây là lỗi gì? Cần quy trình kiểm soát nào ngoài compatibility checker?

### Bài G — Một topic nhiều event type

Topic orders.events chứa OrderPlaced và OrderCancelled. Hãy phân tích khi nào nên dùng subject theo topic, khi nào theo record, và tác động tới schema compatibility, consumer routing và quản trị contract.

### Bài H — Một message không giải mã được

Consumer gặp unknown schema ID trong payload. Nêu quy trình điều tra an toàn: xác định wire format, schema ID, Registry endpoint/quyền, phiên bản serializer, nguồn producer và cách giữ message để replay. Không bỏ qua silent.

## 27. Checklist khi thay đổi schema message trong dự án thật

| Mục | Câu hỏi cần xác nhận |
| --- | --- |
| Contract owner | Team nào sở hữu event/command và schema? |
| Change purpose | Thay đổi vì nghiệp vụ gì, có thể làm không đổi semantics không? |
| Message type | Event, command, snapshot hay CDC record? |
| Schema format | Avro, Protobuf, JSON Schema hoặc loại khác? |
| Subject/artifact | Đăng ký dưới tên nào, version stream nào? |
| Compatibility | BACKWARD/FORWARD/FULL/TRANSITIVE nào đang áp dụng? |
| History | Cần đọc lại những version cũ nào? |
| Producer | Mã serializer và schema ID mới được triển khai thế nào? |
| Consumer | Danh sách consumer và behavior khi unknown field/enum? |
| Field semantics | Đơn vị tiền, thời gian, null/default, quyền sở hữu? |
| Key | Có thay message key/partitioning hoặc compaction không? |
| Privacy | Payload có PII/secret hoặc phân phối dữ liệu rộng hơn không? |
| Validation | Lint, schema parse, compatibility check và domain tests? |
| Deployment | Consumer-first hay producer-first? Có dual publish không? |
| Rollback | Message mới đã ghi vào log sẽ được đọc thế nào? |
| Error handling | Deserialization failure, DLQ, retry, poison message? |
| Observability | Metrics publish/consume errors, registry lookup/lag? |
| Operations | Registry HA, backup/restore, RBAC, secret handling? |
| Deprecation | Khi nào xóa schema/field/type cũ và ai phê duyệt? |
| Documentation | Ai cập nhật event catalog, change notes, consumer instructions? |

### Ví dụ bản ghi thay đổi

~~~yaml
event: OrderPlaced
owner: Ordering Team
format: Avro
subject: orders.events-value
change: add currency field
compatibilityPolicy: BACKWARD_TRANSITIVE
historyAssumption: "All historical records use VND - must be verified"
producerRollout: "after consumer compatibility tests"
consumers:
  - Inventory
  - Notifications
  - Analytics
risk:
  - "Analytics may interpret historical money incorrectly"
  - "Rollback must still decode messages written with new schema"
validation:
  - schema-parse
  - registry-compatibility
  - consumer-contract-tests
  - historical-fixtures
operations:
  - monitor-deserialization-errors
  - monitor-consumer-lag
  - monitor-business-totals
~~~

Đây là mô tả minh họa; **không** khẳng định dữ liệu lịch sử thật chỉ có VND. Một project thực tế cần xác minh giả định trước khi dùng default hoặc xử lý dữ liệu tồn đọng.

## 28. Kiểm tra nhanh cuối bài

1. Schema khác message contract ở điểm nào?
2. Registry lưu message nghiệp vụ hay định nghĩa schema?
3. Schema version trong subject và eventVersion trong payload có bắt buộc giống nhau không?
4. BACKWARD và FORWARD kiểm tra hai chiều reader/writer nào?
5. Transitive bổ sung loại kiểm tra gì khi có nhiều version?
6. Vì sao pass compatibility chưa bảo đảm semantic compatibility?
7. Field number trong Protobuf có thể được tái sử dụng sau khi xóa không?
8. Mục đích của reserved trong Protobuf là gì?
9. Schema ID xuất hiện trong payload có phải thuộc tính bắt buộc của Kafka không?
10. Trong một topic nhiều event type, subject naming ảnh hưởng quản trị schema ra sao?
11. Khi đổi message key từ orderId sang customerId, điều gì có thể xảy ra với partition và ordering?
12. Vì sao consumer mới cần writer schema cũ khi replay?
13. Registry downtime ảnh hưởng client đã cache và chưa cache khác nhau ra sao?
14. Có thể dùng schema validation thay cho idempotency hay không?
15. Khi rollback producer, message đã phát dưới schema mới có tự biến mất không?
16. Khi thêm customerEmail vào event được nhiều team tiêu thụ, cần đánh giá quyền riêng tư thế nào?

## 29. Tổng kết

**Schema** mô tả hình dạng và kiểu dữ liệu của thông điệp; **message contract** mô tả cả cách hiểu và trách nhiệm nghiệp vụ. **Schema Registry** cung cấp nơi quản lý định danh, version và compatibility của schema để producer và consumer có thể tiến hóa có kiểm soát.

Trong Microservices, quản lý schema không kết thúc ở việc tạo file .avsc, .proto hay .json. Cần đặt schema dưới quyền sở hữu rõ ràng, kiểm tra compatibility phù hợp format, thử producer/consumer thực tế, thiết kế rollout/rollback có tính đến dữ liệu đã phát và lịch sử replay, đồng thời kiểm soát ngữ nghĩa, bảo mật, key/partition và side effects.

Một hệ thống vững chắc không chỉ hỏi **“Message này parse được không?”**, mà còn hỏi **“Ai phát thông điệp, tại sao nó đúng, consumer cũ/mới sẽ hiểu thế nào, khi schema thay đổi thì dữ liệu đang nằm trong broker vẫn được xử lý ra sao?”**. Đó là giá trị thật của quản trị lược đồ và Schema Registry trong giao tiếp bất đồng bộ.
