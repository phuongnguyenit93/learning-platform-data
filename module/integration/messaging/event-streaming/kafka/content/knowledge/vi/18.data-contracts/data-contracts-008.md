# Định danh sự kiện, phiên bản hợp đồng và metadata dùng chung

## Mục tiêu

Kafka truyền record giữa các service độc lập. Để producer và consumer hiểu cùng một ý nghĩa, mỗi record cần có hợp đồng dữ liệu rõ ràng: event là gì, ai phát ra, thuộc đối tượng nghiệp vụ nào, được tạo khi nào, phiên bản nào đang được dùng và có thể tương quan với request/trace nào. Nếu thiếu các thông tin này, consumer dễ diễn giải sai payload, xử lý trùng khi replay hoặc không thể truy vết lỗi xuyên qua nhiều service.

Hợp đồng dữ liệu không chỉ là schema của JSON, Avro hay Protobuf. Nó còn bao gồm quy ước định danh, Kafka key, header, timestamp, versioning, compatibility, quyền sở hữu và chính sách thay đổi.

Sau bài học này, bạn có thể:

- Phân biệt event ID, event type, event version, schema version và Kafka offset.
- Thiết kế metadata envelope dùng chung cho các domain event.
- Chọn Kafka key ổn định để giữ ordering theo aggregate.
- Quyết định trường nào thuộc payload, trường nào đặt trong Kafka headers.
- Quản lý schema và thay đổi hợp đồng tương thích với consumer cũ.
- Truyền correlation ID, causation ID và trace context xuyên service.
- Thiết kế idempotency, replay và audit dựa trên event identity.
- Xây dựng checklist và contract test cho producer/consumer.

## 1. Data contract là gì?

Data contract là thỏa thuận giữa bên phát và bên nhận về cấu trúc, ý nghĩa và cách sử dụng dữ liệu. Với Kafka, contract nên mô tả cả phần record và ngữ cảnh vận hành của topic.

Một data contract thực tế thường gồm:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Event type | Sự kiện nghiệp vụ nào đã xảy ra? |
| Event identity | Làm sao nhận biết hai lần nhận là cùng một event? |
| Schema | Payload có cấu trúc và kiểu dữ liệu nào? |
| Version | Consumer hỗ trợ phiên bản nào? Thay đổi có tương thích không? |
| Kafka key | Record được định tuyến tới partition nào và ordering cần giữ theo đối tượng nào? |
| Headers/metadata | Correlation, trace, tenant, source và content type được truyền ra sao? |
| Semantics | Event biểu thị sự thật nào, thời điểm nào và có thể phát lại không? |
| Ownership | Team/service nào sở hữu schema và chịu trách nhiệm thay đổi? |
| Operations | Retention, ACL, retry, DLT, replay và SLO được quy định thế nào? |

Ví dụ, `OrderCreated` cần nói rõ đó là thời điểm đơn hàng được chấp nhận tạo thành công, không phải lúc người dùng nhấn nút đặt hàng. Nếu producer và consumer hiểu khác nhau về ý nghĩa này, schema dù hoàn toàn hợp lệ vẫn tạo ra lỗi nghiệp vụ.

### 1.1. Phân biệt record, event và command

- **Event:** mô tả một sự việc đã xảy ra, thường dùng thì quá khứ như `OrderCreated`, `PaymentCaptured`.
- **Command:** yêu cầu một service thực hiện hành động, như `CapturePayment` hoặc `CreateShipment`.
- **Record:** đơn vị dữ liệu Kafka lưu trong partition, gồm key, value, timestamp và headers. Record có thể mang event, command hoặc dữ liệu khác.

Không dùng tên event như một command nếu consumer có thể hiểu nó là yêu cầu thực hiện lại hành động. Khi replay một event đã xảy ra, consumer nên dựng trạng thái hoặc projection từ sự thật đó, không tự động gọi lại hành động không thể đảo ngược.

## 2. Metadata envelope dùng chung

Một event envelope là lớp bao bên ngoài phần dữ liệu domain. Envelope giúp các service dùng chung cách nhận diện, truy vết và versioning mà không phải định nghĩa lại những trường này trong từng payload.

Ví dụ envelope:

```json
{
  "eventId": "01934d4e-9b6a-7c2f-8b1a-6d3c2a7e1001",
  "eventType": "com.acme.orders.OrderCreated",
  "eventVersion": "1.0",
  "source": "order-service",
  "subject": "order/ORD-1001",
  "tenantId": "tenant-01",
  "occurredAt": "2026-11-20T08:15:30.125Z",
  "publishedAt": "2026-11-20T08:15:30.180Z",
  "correlationId": "req-8f31a2",
  "causationId": "cmd-3a7c11",
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "data": {
    "orderId": "ORD-1001",
    "customerId": "CUS-01",
    "totalAmount": 125000,
    "currency": "VND"
  }
}
```

Đây là một envelope do ứng dụng định nghĩa, không phải schema bắt buộc của Kafka. Có thể dùng CloudEvents làm nền tảng chuẩn hóa metadata, hoặc dùng envelope nội bộ miễn là contract được tài liệu hóa và áp dụng nhất quán.

### 2.1. Các trường metadata cốt lõi

| Trường | Ý nghĩa | Quy tắc khuyến nghị |
|---|---|---|
| `eventId` | Định danh duy nhất của một event logic | Sinh một lần, giữ nguyên khi retry/replay/republish cùng event |
| `eventType` | Tên loại event | Ổn định, có namespace; không dùng tên class Java làm contract nếu class có thể đổi tùy ý |
| `eventVersion` | Phiên bản contract/semantics mà event tuân theo | Dùng quy tắc versioning có tài liệu, không nhầm với schema registry version |
| `source` | Service hoặc hệ thống phát event | Dùng tên logical ổn định, không dùng hostname/pod ID ngắn hạn |
| `subject` | Đối tượng nghiệp vụ mà event nói tới | Ví dụ `order/ORD-1001`; giữ quy ước nhất quán |
| `tenantId` | Phạm vi tenant nếu hệ thống multi-tenant | Bắt buộc nếu cần cô lập dữ liệu theo tenant; xác thực từ nguồn tin cậy |
| `occurredAt` | Thời điểm sự kiện thực sự xảy ra trong domain | UTC, định dạng chuẩn; không thay đổi khi replay |
| `publishedAt` | Thời điểm ứng dụng bắt đầu lần publish đầu tiên của event | Được lưu cùng outbox và giữ nguyên khi retry; có thể khác `occurredAt` |
| `correlationId` | Nhóm các thao tác thuộc cùng một luồng nghiệp vụ/request | Giữ nguyên qua các bước downstream có cùng correlation |
| `causationId` | ID của command/event trực tiếp gây ra event này | Hỗ trợ dựng chuỗi nguyên nhân |
| `traceparent` | W3C Trace Context để liên kết distributed trace | Truyền đúng định dạng và tạo span mới tại mỗi service |

Không phải event nào cũng cần mọi trường. Contract nên chỉ định trường bắt buộc, tùy chọn, nguồn tạo và quy tắc khi thiếu. Ví dụ `tenantId` có thể không cần với hệ thống single-tenant; `correlationId` có thể vắng mặt với event phát sinh từ batch job.

## 3. Phân biệt các loại định danh và version

Các trường sau thường bị gộp nhầm nhưng giải quyết những bài toán khác nhau.

| Giá trị | Định danh điều gì? | Có thay đổi khi replay? |
|---|---|---|
| `eventId` | Một event logic cụ thể | Không; cùng event phải giữ cùng ID |
| `eventType` | Loại sự kiện | Không thay đổi chỉ vì replay |
| `eventVersion` | Phiên bản contract/ý nghĩa event | Không thay đổi chỉ vì replay |
| Schema Registry version | Một phiên bản schema được đăng ký trong registry | Không phải metadata định danh event; schema mới có thể được tạo độc lập |
| Schema ID | Một schema cụ thể trong registry/format wire | Phụ thuộc serializer và schema được dùng khi ghi; không phải event ID |
| Kafka offset | Vị trí record trong một partition | Không ổn định khi copy sang topic khác hoặc ghi lại |
| Kafka key | Giá trị dùng để partition/routing và compaction semantics | Thường ổn định theo aggregate; không thay event ID |
| `correlationId` | Một luồng nghiệp vụ gồm nhiều event/command | Giữ nguyên trong cùng flow, có thể khác giữa flow khác |

Ví dụ một đơn hàng có thể phát nhiều event: `OrderCreated`, `OrderPaid`, `OrderShipped`. Mỗi event có `eventId` khác nhau, nhưng cùng `subject=order/ORD-1001` và có thể cùng correlation ID. Kafka key thường là `ORD-1001` để giữ các event của đơn hàng trên cùng partition.

### 3.1. Event ID không phải aggregate ID

`orderId` nhận diện đơn hàng; `eventId` nhận diện một lần thay đổi/sự kiện. Một aggregate có thể phát hàng trăm event trong vòng đời. Nếu dùng `orderId` làm event ID, inbox/deduplication có thể coi các event hợp lệ tiếp theo là duplicate.

### 3.2. Event version không phải schema version

Schema Registry có thể tăng version khi thêm một field optional mà semantics event không đổi. Ngược lại, cùng schema có thể bị thay đổi ý nghĩa nghiệp vụ nếu team đổi định nghĩa `occurredAt` hoặc `totalAmount` mà không thay cấu trúc.

Hãy quản lý riêng:

- Schema version: do registry quản lý theo subject/schema.
- Event contract version: do domain owner quản lý theo quy tắc thay đổi và semantics.
- Application version: phiên bản triển khai service, không đưa vào event để consumer phụ thuộc vào build cụ thể.

Không dùng một số version duy nhất để thay thế cả ba khái niệm.

## 4. Định danh sự kiện và idempotency

`eventId` phải được tạo tại nguồn phát sinh event và được lưu bền vững cùng event/outbox nếu có. Khi producer retry do timeout, publish lại từ outbox hoặc replay, cùng một event logic phải giữ nguyên ID.

Quy tắc:

1. Sinh ID một lần khi tạo event, không sinh lại trong mỗi lần gọi `send()`.
2. Lưu ID cùng payload/outbox record để process restart vẫn publish cùng event.
3. Consumer dùng ID để deduplicate trong cùng transaction với side effect database khi cần.
4. Khi tạo một event mới do event cũ gây ra, tạo ID mới và đặt `causationId` bằng ID của event/command trước.
5. Khi copy event sang replay topic, giữ `eventId` gốc và thêm `replayRunId`/source coordinates riêng.

Ví dụ:

```text
Command CreateOrder: commandId = CMD-100
  -> OrderCreated: eventId = EVT-501, causationId = CMD-100
  -> PaymentRequested: eventId = EVT-502, causationId = EVT-501
  -> PaymentCaptured: eventId = EVT-503, causationId = EVT-502
```

Nếu `PaymentCaptured` được replay, `eventId` vẫn là `EVT-503`. Consumer đã xử lý event này có thể nhận diện duplicate. Kafka producer idempotence bảo vệ retry ở protocol trong phạm vi producer session; nó không thay thế event ID nghiệp vụ và deduplication ở consumer.

### 4.1. Event ID nên có định dạng nào?

Có thể dùng UUID, ULID hoặc ID duy nhất do hệ thống cấp. Lựa chọn cần đáp ứng:

- Xác suất collision phù hợp quy mô hệ thống.
- Có thể lưu, index và truyền qua các service.
- Không chứa thông tin nhạy cảm hoặc dữ liệu cá nhân.
- Không phụ thuộc vào offset Kafka vì offset chỉ có ý nghĩa trong topic-partition.
- Có quy tắc canonicalization nếu ID được tạo từ nhiều thành phần.

Không nên dùng timestamp đơn lẻ làm ID. Nhiều event có thể được tạo cùng mili giây, clock có thể lệch và timestamp không bảo đảm uniqueness.

## 5. Kafka key và ordering theo aggregate

Kafka key quyết định partition theo partitioner. Nếu cần các event của cùng một aggregate được đọc theo thứ tự trong cùng partition, hãy dùng aggregate ID làm key ổn định.

Ví dụ:

```text
Topic: orders.events
Key: ORD-1001
  offset 100: OrderCreated
  offset 105: OrderPaid
  offset 111: OrderShipped
```

Offset có thể có khoảng trống; thứ tự append trong partition vẫn được giữ. Consumer group chỉ có một member được giao partition đó tại một thời điểm, nên một consumer xử lý tuần tự có thể quan sát thứ tự partition.

Không dùng `eventId` làm key nếu mục tiêu là giữ ordering theo order. Mỗi event ID khác nhau sẽ có thể rơi vào partition khác nhau. Cũng không dùng `correlationId` làm key trừ khi toàn bộ event thuộc correlation thực sự cần cùng partition và phân phối tải chấp nhận được.

### 5.1. Thay đổi partition count có thể thay đổi mapping key

Với partitioner dựa trên key, tăng số partition có thể khiến cùng key được ánh xạ sang partition mới. Event cũ của aggregate có thể ở partition cũ, event mới ở partition khác, khiến không còn một thứ tự log duy nhất xuyên qua thay đổi. Nếu ordering theo aggregate là yêu cầu cứng, phải có kế hoạch migration/versioning và cân nhắc cách partitioning ổn định.

### 5.2. Kafka key không phải unique constraint

Kafka cho phép nhiều record cùng key trong một partition. Key giúp routing và có thể được dùng làm compaction key; nó không tự ngăn duplicate. Muốn ngăn event trùng, dùng `eventId` và cơ chế idempotency của consumer.

## 6. Payload hay Kafka headers?

Kafka record có key, value và headers. Hợp đồng cần chỉ định metadata nào nằm trong value envelope và metadata nào nằm trong header.

| Vị trí | Nên chứa | Lưu ý |
|---|---|---|
| Kafka key | Aggregate ID hoặc routing key | Không thay event ID; quyết định partitioning |
| Value/payload | Event type, event version và dữ liệu domain cốt lõi | Phải tồn tại cùng event khi export, archive hoặc chuyển qua hệ thống khác |
| Headers | Correlation ID, traceparent, content type, tenant hint, source coordinates | Header có thể bị connector/sink/transform bỏ hoặc ánh xạ khác; cần contract và test |
| Schema wire metadata | Schema ID/format marker theo serializer | Phụ thuộc định dạng wire; không nhầm schema ID với event version |

Một quy tắc hữu ích: thông tin cần để hiểu đúng event khi lưu trữ lâu dài hoặc xuất khỏi Kafka nên nằm trong payload/envelope hoặc được đảm bảo bởi một contract vận chuyển rõ ràng. Header phù hợp với metadata xuyên suốt transport như tracing, routing và content type.

Nếu cùng một trường xuất hiện trong payload và header, cần chỉ định nguồn nào là authoritative. Ví dụ `eventId` trong payload và `event-id` header phải giống nhau; producer/consumer nên kiểm tra consistency thay vì âm thầm chọn giá trị bất kỳ.

### 6.1. Tên header và kiểu dữ liệu

Kafka header gồm key dạng string và value dạng byte array. Nên dùng tên lowercase, có quy ước thống nhất như `event-id`, `event-type`, `event-version`, `correlation-id`, `causation-id`, `traceparent`, `content-type`.

Giá trị text nên encode UTF-8. Nếu header chứa binary hoặc nhiều giá trị cùng tên, contract phải mô tả cách diễn giải. Kafka cho phép nhiều header trùng key; `lastHeader()` chỉ lấy giá trị cuối cùng, vì vậy không nên dựa vào hành vi đó nếu producer có thể thêm header lặp.

Không nhét payload lớn, stack trace dài hoặc dữ liệu nhạy cảm vào headers. Header thường được sao chép qua broker/client/connector và có thể xuất hiện trong log hoặc tooling.

## 7. Metadata thời gian: occurred, published và ingested

Một event có thể có nhiều mốc thời gian:

- `occurredAt`: thời điểm sự kiện nghiệp vụ xảy ra tại nguồn.
- `publishedAt`: thời điểm ứng dụng bắt đầu lần publish đầu tiên theo contract này; giữ nguyên khi retry.
- `ingestedAt`: thời điểm hệ thống downstream nhận/ghi nhận event.
- Kafka record timestamp: timestamp do producer hoặc broker ghi theo `message.timestamp.type` của topic/broker.

Các giá trị này không nhất thiết bằng nhau. Producer có thể publish trễ do outbox backlog; consumer có thể xử lý trễ do lag; clock giữa service có thể lệch.

Ví dụ:

| Mốc | Thời điểm | Ý nghĩa |
|---|---|---|
| `occurredAt` | 08:00:00.000Z | Đơn hàng được tạo trong domain |
| `publishedAt` | 08:00:02.300Z | Outbox publisher gửi event sau 2,3 giây |
| `ingestedAt` | 08:00:05.100Z | Projection service xử lý sau khi nhận |

Tính metric đúng mục tiêu:

- Publish delay = `publishedAt - occurredAt`.
- Consumer processing delay = `ingestedAt - publishedAt`.
- End-to-end event age = thời điểm hiện tại - `occurredAt`.

Các phép tính cần cùng timezone/clock discipline và phải chấp nhận clock skew. Không dùng Kafka offset thay timestamp và không giả định timestamp tạo ra thứ tự toàn cục giữa partition.

Chuẩn hóa timestamp về UTC, dùng ISO-8601/RFC 3339 hoặc epoch theo đơn vị được ghi rõ. Tránh field tên `timestamp` chung chung vì consumer không biết đó là thời điểm nghiệp vụ, publish hay ingest.

## 8. Correlation ID, causation ID và distributed tracing

Ba khái niệm này hỗ trợ điều tra luồng xử lý nhưng không thay thế nhau:

| Metadata | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| `correlationId` | Các thao tác nào thuộc cùng một business flow? | Request checkout và các event liên quan |
| `causationId` | Sự kiện/command nào trực tiếp gây ra event này? | `PaymentRequested` gây ra `PaymentCaptured` |
| `traceparent` | Span nào trong distributed trace liên kết các service? | W3C Trace Context |

Một correlation ID có thể bao phủ nhiều trace nếu nghiệp vụ kéo dài qua nhiều request hoặc job. Một trace có thể chứa nhiều span và được tạo mới khi consumer xử lý message. `causationId` thể hiện quan hệ nhân quả ở domain, không phải parent span ID.

### 8.1. Truyền W3C Trace Context

W3C Trace Context định nghĩa header `traceparent` (và tùy chọn `tracestate`). Producer nên inject context hiện tại vào Kafka headers; consumer extract context khi bắt đầu xử lý và tạo span consumer mới có quan hệ phù hợp. Dùng OpenTelemetry instrumentation hoặc propagator thay vì tự nối chuỗi trace ID.

Không dùng `correlationId` làm `traceparent`: hai trường có format và mục đích khác nhau. Không ghi token, session ID hoặc PII vào tracing baggage nếu không có kiểm soát truy cập và chính sách dữ liệu.

## 9. CloudEvents như một quy ước envelope

CloudEvents là đặc tả mở giúp chuẩn hóa metadata của event qua nhiều hệ thống. Một số thuộc tính cốt lõi:

| CloudEvents attribute | Ý nghĩa |
|---|---|
| `specversion` | Phiên bản đặc tả CloudEvents |
| `id` | Định danh event trong phạm vi source |
| `source` | Nguồn phát event |
| `type` | Loại event |
| `subject` | Đối tượng mà event nói tới |
| `time` | Thời điểm event xảy ra |
| `datacontenttype` | Content type của data |
| `dataschema` | URI nhận diện schema của data nếu có |

Ví dụ structured JSON:

```json
{
  "specversion": "1.0",
  "id": "evt-501",
  "source": "/services/order-service",
  "type": "com.acme.orders.OrderCreated",
  "subject": "orders/ORD-1001",
  "time": "2026-11-20T08:15:30Z",
  "datacontenttype": "application/json",
  "dataschema": "https://schemas.acme.example/orders/order-created/1.0.0",
  "correlationid": "req-8f31a2",
  "causationid": "cmd-3a7c11",
  "data": {
    "orderId": "ORD-1001",
    "totalAmount": 125000,
    "currency": "VND"
  }
}
```

`specversion` là phiên bản CloudEvents, không phải phiên bản event domain. `id` là event identity; `type` là event type; `dataschema` định danh schema của phần data. Các extension attributes như `correlationid` và `causationid` cần tuân thủ quy tắc tên thuộc tính CloudEvents.

CloudEvents có thể được biểu diễn theo structured mode trong payload hoặc binary mode với context attributes trong Kafka headers và data trong value. Chọn một mode và ghi rõ trong contract; không trộn hai cách mà không có quy tắc chuyển đổi.

## 10. Schema format và Schema Registry

Kafka broker lưu byte key/value và không tự xác thực JSON/Avro/Protobuf schema theo ý nghĩa domain. Serializer/deserializer và Schema Registry (nếu dùng) giúp producer/consumer trao đổi schema có version và kiểm tra compatibility.

Các format phổ biến:

| Format | Đặc điểm | Cần chú ý |
|---|---|---|
| JSON/JSON Schema | Dễ đọc và debug, phổ biến với API | Cần định nghĩa required/optional, type, additional properties và compatibility rõ |
| Avro | Schema gọn, hỗ trợ schema evolution và default | Reader/writer schema resolution phụ thuộc default và quy tắc compatibility |
| Protobuf | Typed message, field number và generated code | Không tái sử dụng field number đã xóa; reserve field/name khi xóa |

Schema Registry có thể lưu schema theo subject, gán registry version và schema ID, đồng thời áp dụng compatibility policy. Cách đặt subject và wire format phụ thuộc registry/serializer cụ thể. Schema ID trong wire payload không phải `eventId` và cũng không phải `eventVersion`.

### 10.1. Compatibility modes

Các registry như Confluent Schema Registry thường cung cấp các mode tương thích sau; chi tiết chính xác phụ thuộc format và phiên bản registry:

| Mode | Mục tiêu |
|---|---|
| `BACKWARD` | Schema mới có thể đọc dữ liệu được ghi bằng schema trước đó |
| `BACKWARD_TRANSITIVE` | Schema mới có thể đọc dữ liệu từ tất cả version trước trong subject |
| `FORWARD` | Consumer/schema cũ có thể đọc dữ liệu được ghi bằng schema mới theo quy tắc format |
| `FORWARD_TRANSITIVE` | Tương thích forward với tất cả version trước |
| `FULL` | Tương thích backward và forward với version liền trước |
| `FULL_TRANSITIVE` | Tương thích cả hai chiều với toàn bộ version trước |
| `NONE` | Không áp dụng kiểm tra compatibility tự động |

Đừng chọn mode chỉ dựa trên tên. Hãy xác định ai deploy trước, consumer nào có thể còn chạy schema cũ và retention của topic dài bao lâu. Nếu consumer có thể đọc record cũ nhiều tháng, backward-transitive hoặc quy trình tương thích tương đương thường đáng cân nhắc.

Registry compatibility chỉ kiểm tra schema theo format và policy. Nó không xác nhận rằng `totalAmount` vẫn giữ cùng đơn vị tiền, `occurredAt` vẫn cùng ý nghĩa hay event không thay đổi semantics. Cần review domain contract và contract test.

## 11. Quy tắc thay đổi schema an toàn

Thay đổi contract cần tính đến producer mới, consumer cũ, consumer mới và record cũ vẫn còn trong retention.

### 11.1. Thêm field

Thêm field optional hoặc có default an toàn thường dễ tương thích hơn. Consumer cũ thường bỏ qua field mới nếu format/decoder cho phép; consumer mới cần đọc record cũ mà field đó chưa tồn tại.

Ví dụ thêm `deliveryNote`:

```json
{
  "orderId": "ORD-1001",
  "customerId": "CUS-01",
  "totalAmount": 125000,
  "currency": "VND",
  "deliveryNote": null
}
```

Không đặt default giả tạo nếu nó làm thay đổi nghiệp vụ. Ví dụ default `currency=VND` chỉ hợp lệ nếu domain contract bảo đảm mọi record cũ thực sự dùng VND. Nếu không biết currency, biểu diễn trạng thái unknown/absent rõ ràng và xử lý ở consumer.

### 11.2. Xóa hoặc rename field

Rename trực tiếp thường gây lỗi với consumer cũ. Chiến lược an toàn:

1. Thêm field mới, giữ field cũ.
2. Producer ghi cả hai field trong giai đoạn chuyển tiếp nếu cần.
3. Consumer chuyển sang đọc field mới, có fallback phù hợp.
4. Theo dõi consumer version và usage.
5. Chỉ bỏ field cũ sau khi không còn consumer phụ thuộc và compatibility policy cho phép.

### 11.3. Đổi kiểu dữ liệu

Đổi `amount` từ integer sang string, hoặc timestamp từ milliseconds sang seconds, có thể làm consumer diễn giải sai dù payload vẫn parse được. Nên tạo field mới có tên/đơn vị rõ ràng, migrate theo giai đoạn và không đổi nghĩa của field đang tồn tại.

### 11.4. Enum và unknown values

Consumer nên có chiến lược với enum value mới. Nếu consumer fail khi gặp giá trị chưa biết, một event hợp lệ có thể làm partition bị poison. Với enum có thể mở rộng, cân nhắc biểu diễn string và nhánh fallback/unknown có audit; nếu dùng Protobuf/Avro, tuân thủ quy tắc enum evolution của format.

### 11.5. Xóa field Protobuf

Không tái sử dụng field number đã xóa. Đánh dấu số và tên đã xóa là `reserved` để tránh schema tương lai gán nhầm ý nghĩa cho dữ liệu cũ.

## 12. Ví dụ Java: định nghĩa envelope có kiểu

Có thể dùng Java record để mô hình hóa envelope. Ví dụ dưới đây giả định Java 17+:

```java
import java.time.Instant;
import java.util.UUID;

public record EventEnvelope<T>(
        UUID eventId,
        String eventType,
        String eventVersion,
        String source,
        String subject,
        String tenantId,
        Instant occurredAt,
        Instant publishedAt,
        String correlationId,
        String causationId,
        T data) {
}

public record OrderCreated(
        String orderId,
        String customerId,
        long totalAmount,
        String currency) {
}
```

`publishedAt` trong contract này là thời điểm ứng dụng bắt đầu lần publish đầu tiên; `occurredAt` lấy từ domain event. Cả hai được lưu cùng outbox row và giữ nguyên khi retry. Nếu cần đo từng lần thử, ghi `publishAttemptAt` trong log/metric vận hành thay vì ghi đè timestamp của event gốc.

## 13. Java Producer: gửi key, value và headers

Ví dụ dùng Jackson serialize envelope thành JSON và truyền metadata vận chuyển trong Kafka headers:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.Headers;

import java.nio.charset.StandardCharsets;

public void publishOrderCreated(
        KafkaProducer<String, byte[]> producer,
        ObjectMapper objectMapper,
        EventEnvelope<OrderCreated> event,
        String traceparent,
        String orderId) throws Exception {

    byte[] value = objectMapper.writeValueAsBytes(event);
    ProducerRecord<String, byte[]> record = new ProducerRecord<>(
            "orders.events", orderId, value);

    Headers headers = record.headers();
    headers.add("event-id", event.eventId().toString().getBytes(StandardCharsets.UTF_8));
    headers.add("event-type", event.eventType().getBytes(StandardCharsets.UTF_8));
    headers.add("event-version", event.eventVersion().getBytes(StandardCharsets.UTF_8));
    headers.add("content-type", "application/json".getBytes(StandardCharsets.UTF_8));
    if (event.tenantId() != null) {
        headers.add("tenant-id",
                event.tenantId().getBytes(StandardCharsets.UTF_8));
    }
    if (event.correlationId() != null) {
        headers.add("correlation-id",
                event.correlationId().getBytes(StandardCharsets.UTF_8));
    }
    if (traceparent != null) {
        headers.add("traceparent", traceparent.getBytes(StandardCharsets.UTF_8));
    }

    producer.send(record, (metadata, exception) -> {
        if (exception != null) {
            // Log eventId/topic/key; không tạo eventId mới khi retry cùng event.
            logPublishFailure(event.eventId(), orderId, exception);
        } else {
            logPublished(event.eventId(), metadata.topic(),
                    metadata.partition(), metadata.offset());
        }
    });
}
```

Ví dụ minh họa cấu trúc, cần bổ sung imports và cấu hình serializer/producer phù hợp. `EventEnvelope` phải được tạo tại ranh giới phát sinh domain event, với `eventId`, `occurredAt` và `publishedAt` được lưu bền vững cùng outbox record. Hàm publish nhận envelope đã tạo sẵn nên retry không sinh ID mới hoặc thay đổi thời điểm gốc.

Kafka key trong ví dụ là `orderId` để giữ event của cùng đơn hàng trên một partition. Header lặp lại `event-id`, `event-type` và `event-version` để hỗ trợ routing/observability; consumer cần kiểm tra chúng khớp với envelope. Nếu contract chọn payload là nguồn authoritative, không dùng header để ghi đè giá trị payload khi mismatch.

## 14. Java Consumer: đọc và xác thực contract

Consumer nên xác thực metadata trước khi thực hiện side effect:

```java
public void handle(ConsumerRecord<String, byte[]> record) throws Exception {
    String headerEventId = headerUtf8(record, "event-id");
    String headerEventType = headerUtf8(record, "event-type");
    String headerVersion = headerUtf8(record, "event-version");

    EventEnvelope<OrderCreated> event = objectMapper.readValue(
            record.value(), orderCreatedEnvelopeType);

    if (!event.eventId().toString().equals(headerEventId)) {
        throw new InvalidEventContractException("event-id header mismatch");
    }
    if (!event.eventType().equals(headerEventType)) {
        throw new InvalidEventContractException("event-type header mismatch");
    }
    if (!event.eventVersion().equals(headerVersion)) {
        throw new InvalidEventContractException("event-version header mismatch");
    }

    validateRequiredFields(event);
    if (processedEventRepository.exists(event.eventId())) {
        return; // Duplicate event: không lặp side effect.
    }

    applyProjectionAndStoreEventIdAtomically(event);
}
```

Đây là pseudo-code: `orderCreatedEnvelopeType`, `headerUtf8`, repository và transaction logic phụ thuộc implementation. Kiểm tra duplicate bằng `exists()` rồi mới insert có thể race khi nhiều consumer cùng xử lý; nên dùng unique constraint/inbox insert trong cùng transaction với projection update.

Nếu header không tồn tại, consumer cần áp dụng policy rõ: reject/DLT, tương thích legacy hoặc lấy metadata từ payload nếu contract cho phép. Không mặc định chuỗi rỗng hoặc tự suy đoán event type từ topic.

## 15. Spring Kafka: gửi event qua KafkaTemplate

`KafkaTemplate` hỗ trợ gửi `ProducerRecord` để kiểm soát key và headers:

```java
ProducerRecord<String, EventEnvelope<OrderCreated>> record =
        new ProducerRecord<>("orders.events", orderId, event);

record.headers().add("event-id",
        event.eventId().toString().getBytes(StandardCharsets.UTF_8));
record.headers().add("event-type",
        event.eventType().getBytes(StandardCharsets.UTF_8));
record.headers().add("event-version",
        event.eventVersion().getBytes(StandardCharsets.UTF_8));
record.headers().add("correlation-id",
        correlationId.getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(record).whenComplete((result, exception) -> {
    if (exception != null) {
        log.error("Publish event {} failed", event.eventId(), exception);
    } else {
        RecordMetadata metadata = result.getRecordMetadata();
        log.info("Published event {} to {}-{}@{}",
                event.eventId(), metadata.topic(),
                metadata.partition(), metadata.offset());
    }
});
```

Serializer của `KafkaTemplate` phải phù hợp với kiểu value và contract. Nếu dùng Avro/Protobuf với Schema Registry, dùng serializer tương ứng và kiểm tra subject naming strategy. Không serialize object thành JSON rồi đồng thời khai báo content type Avro.

Với tracing, ưu tiên Spring Kafka/OpenTelemetry instrumentation để inject/extract W3C context. Nếu tự truyền header, phải kiểm tra context propagation ở cả producer lẫn consumer và tránh tạo trace mới bằng cách copy nguyên `traceparent` mà không tạo span con đúng cách.

## 16. Tổ chức schema và topic

Schema subject naming phụ thuộc registry và chiến lược đặt subject. Một số chiến lược thường gặp:

- Subject theo topic-value: phù hợp khi một topic có một loại value contract chính.
- Subject theo record: phù hợp khi schema gắn với record type và được tái sử dụng qua topic.
- Subject theo topic-record: kết hợp topic và record name để cô lập compatibility.

Không chọn naming strategy chỉ vì thuận tiện ở producer. Hãy cân nhắc liệu nhiều event type có dùng chung một topic hay mỗi event type một topic, ai sở hữu schema và consumer cần deserialize thế nào.

Một topic contract nên mô tả:

| Thuộc tính | Ví dụ |
|---|---|
| Topic | `orders.events` |
| Owner | Order Platform team |
| Event types | `OrderCreated`, `OrderPaid`, `OrderCancelled` |
| Key | `orderId` |
| Value format | Avro hoặc JSON Schema |
| Schema subject | Theo naming strategy đã chọn |
| Compatibility | Backward transitive hoặc policy đã thống nhất |
| Partition count | Theo throughput và ordering requirement |
| Retention | Theo thời gian replay/audit cần thiết |
| Headers | `event-id`, `event-type`, `event-version`, `traceparent` |
| Security | ACL producer/consumer, data classification |
| Error flow | Retry/DLT và owner xử lý |

## 17. Quy tắc governance và quyền sở hữu

Data contract cần owner rõ ràng. Team sở hữu domain event chịu trách nhiệm định nghĩa semantics, schema, versioning và thông báo thay đổi. Consumer team chịu trách nhiệm nâng cấp decoder, xử lý unknown fields/enum và kiểm thử tương thích.

Một quy trình thay đổi hợp đồng có thể gồm:

1. Mở change proposal mô tả lý do và semantics của thay đổi.
2. Xác định producer, consumer, topic, schema subject và retention liên quan.
3. Kiểm tra compatibility tự động trên Schema Registry hoặc CI.
4. Chạy contract test với payload cũ/mới và consumer version đang được hỗ trợ.
5. Triển khai consumer có khả năng đọc cả format cũ và mới.
6. Triển khai producer phát schema mới.
7. Theo dõi lỗi deserialize, DLT và consumer lag.
8. Chỉ xóa field cũ khi mọi consumer đã migrate và thời gian retention/replay đã được xem xét.

Không dùng Schema Registry như cơ chế phê duyệt nghiệp vụ. Compatibility check pass không chứng minh event vẫn mang cùng ý nghĩa hoặc không làm thay đổi hành vi downstream.

## 18. Bảo mật metadata và dữ liệu nhạy cảm

Metadata thường được log ở nhiều nơi hơn payload vì nó hỗ trợ tracing và routing. Không đưa password, access token, session cookie, số thẻ thanh toán hoặc PII không cần thiết vào headers.

Các nguyên tắc:

- Chỉ truyền `tenantId` hoặc customer reference khi consumer cần và có quyền truy cập.
- Không dùng email/số điện thoại làm Kafka key hoặc event ID nếu không có yêu cầu và kiểm soát rõ.
- Tránh ghi payload đầy đủ hoặc headers nhạy cảm vào log lỗi.
- Dùng ACL cho topic và Schema Registry; chỉ producer owner được đăng ký schema theo subject được cấp quyền.
- Xác định data classification, retention và quy trình xóa/ẩn danh nếu dữ liệu cá nhân nằm trong event.
- Không tin `tenantId` từ header như bằng chứng authorization; xác thực nguồn phát và quyền truy cập độc lập.

## 19. Contract testing

Contract test giúp phát hiện producer và consumer hiểu khác nhau trước khi deploy.

Các nhóm kiểm thử:

| Kiểm thử | Điều cần xác nhận |
|---|---|
| Schema validation | Payload tuân thủ schema và required fields |
| Compatibility test | Schema mới tương thích với version được hỗ trợ |
| Serialization round-trip | Serialize rồi deserialize giữ nguyên dữ liệu có ý nghĩa |
| Header consistency | Header event ID/type/version khớp envelope |
| Unknown field test | Consumer cũ xử lý payload có field mới theo policy |
| Unknown enum/type test | Consumer không crash hoặc skip âm thầm khi gặp giá trị mới |
| Idempotency test | Cùng event ID gửi hai lần chỉ tạo một side effect |
| Replay test | Replay giữ event ID, source metadata và không lặp hành động |
| Partition key test | Cùng aggregate ID được route theo chiến lược đã định |
| Trace propagation test | Trace context được inject/extract và liên kết đúng |

### 19.1. Ví dụ test header và event identity

```java
@Test
void publishesOrderCreatedWithStableIdentityAndAggregateKey() {
    EventEnvelope<OrderCreated> event = fixture.orderCreated();
    ProducerRecord<String, EventEnvelope<OrderCreated>> record =
            publisher.toRecord(event);

    assertThat(record.key()).isEqualTo(event.data().orderId());
    assertThat(headerUtf8(record, "event-id"))
            .isEqualTo(event.eventId().toString());
    assertThat(headerUtf8(record, "event-type"))
            .isEqualTo(event.eventType());
    assertThat(headerUtf8(record, "event-version"))
            .isEqualTo(event.eventVersion());
}
```

Test trên kiểm tra contract ở cấp record trước khi gửi broker. Cần bổ sung integration test với serializer, Schema Registry và consumer thực tế để xác minh wire format và compatibility.

## 20. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng aggregate ID làm event ID | Các event khác nhau của cùng aggregate bị deduplicate nhầm | Mỗi event có ID riêng, aggregate ID dùng làm key/subject |
| Sinh event ID mới mỗi lần retry | Consumer không nhận ra cùng event được publish lại | Lưu ID trong outbox và giữ nguyên khi retry |
| Dùng Kafka offset làm event ID | ID đổi khi copy/replay sang topic khác | Dùng event ID độc lập, giữ source coordinates riêng |
| Gộp event version với schema registry version | Consumer chọn logic sai hoặc khó tương thích | Quản lý version domain và schema độc lập |
| Đổi nghĩa field nhưng giữ schema | Payload parse được nhưng nghiệp vụ sai | Tạo field/version mới và review semantics |
| Dùng event ID làm Kafka key | Event của cùng aggregate có thể nằm ở nhiều partition | Dùng aggregate ID làm key khi cần ordering |
| Chỉ đặt metadata trong headers | Connector/archive có thể làm mất metadata | Đặt thông tin thiết yếu trong envelope hoặc bảo đảm header contract end-to-end |
| Header và payload mâu thuẫn | Consumer không biết giá trị nào đáng tin | Chỉ định authoritative source và validate consistency |
| Timestamp chung chung | Không phân biệt thời điểm xảy ra và publish | Dùng `occurredAt`, `publishedAt`, `ingestedAt` rõ ràng |
| Tin Schema Registry kiểm tra semantics | Thay đổi nghiệp vụ nguy hiểm vẫn có thể pass | Kết hợp review domain và contract tests |
| Đưa PII vào trace/header | Dữ liệu nhạy cảm lan vào log và tooling | Chỉ truyền metadata tối thiểu, phân loại và kiểm soát truy cập |

## 21. Checklist data contract cho production

- [ ] Mỗi event có `eventId` ổn định và duy nhất trong phạm vi được định nghĩa.
- [ ] `eventType` có namespace và semantics rõ ràng.
- [ ] `eventVersion` tách biệt schema registry version và application version.
- [ ] Kafka key phản ánh aggregate/routing requirement, không nhầm với event ID.
- [ ] `source`, `subject`, `occurredAt` và tenant metadata được định nghĩa rõ.
- [ ] Correlation ID, causation ID và trace context có mục đích riêng.
- [ ] Header names, encoding, duplicate-header policy và authoritative source được tài liệu hóa.
- [ ] Value format, schema subject và compatibility policy được chọn.
- [ ] Quy tắc thêm/xóa/rename field, enum và đổi kiểu dữ liệu đã được thống nhất.
- [ ] Consumer có cách xử lý unknown field/type/version và DLT cho payload không hợp lệ.
- [ ] Event ID được giữ nguyên khi retry, outbox republish và replay.
- [ ] Idempotency/deduplication bảo vệ side effect.
- [ ] Contract có owner, quy trình review và contract tests trong CI.
- [ ] Metadata không chứa secret/PII không cần thiết.
- [ ] Retention, replay window, ACL và observability phù hợp với data classification.

## 22. Câu hỏi tự kiểm tra

1. Data contract khác JSON schema ở những điểm nào?
2. Vì sao `eventId` khác `orderId` và Kafka offset?
3. Khi replay cùng một event, trường nào phải giữ nguyên và trường nào có thể được thêm cho replay run?
4. Vì sao event version khác schema registry version?
5. Khi nào nên dùng aggregate ID làm Kafka key?
6. Vì sao Kafka headers không phải nơi duy nhất lưu metadata cốt lõi?
7. `occurredAt` khác `publishedAt` và Kafka record timestamp như thế nào?
8. Correlation ID, causation ID và `traceparent` khác nhau ở đâu?
9. `BACKWARD` khác `BACKWARD_TRANSITIVE` như thế nào?
10. Vì sao schema compatibility pass không chứng minh semantics tương thích?
11. Quy trình rename field an toàn cần những bước nào?
12. Vì sao producer phải lưu event ID cùng outbox record?
13. Làm sao kiểm tra header và payload metadata nhất quán?
14. Vì sao không nên đưa token hoặc PII vào Kafka headers?

## Tài liệu tham khảo

- [Apache Kafka — ProducerRecord and Record Headers](https://kafka.apache.org/documentation/#producerapi): key, value, timestamp và headers của record.
- [Confluent Schema Registry — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html): compatibility modes và quản lý schema version.
- [Confluent Schema Registry — Serdes and Subject Naming Strategies](https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/index.html): serializer/deserializer, schema ID và subject naming.
- [CloudEvents Specification](https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md): event context attributes và structured/binary mode.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): chuẩn `traceparent` và `tracestate`.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): truyền trace context giữa service.

> Một hợp đồng dữ liệu tốt cho phép service hiểu đúng event mà không cần biết code nội bộ của producer. Định danh ổn định, semantics rõ, versioning có quy tắc và metadata được truyền nhất quán là nền tảng để Kafka pipeline có thể mở rộng, replay và vận hành an toàn.
