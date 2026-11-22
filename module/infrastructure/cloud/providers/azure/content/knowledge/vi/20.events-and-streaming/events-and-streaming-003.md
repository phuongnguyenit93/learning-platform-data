# Thiết kế event schema và sử dụng CloudEvents

Một hệ thống thương mại điện tử có thể phát sinh sự kiện khi đơn hàng được tạo, thanh toán được xác nhận, hàng được xuất kho hoặc một tệp mới được tải lên. Những sự kiện đó được nhiều dịch vụ xử lý độc lập: hóa đơn, kho, email, phân tích và kiểm toán. Nếu mỗi nhóm tự đặt tên trường, định dạng ngày giờ, mã sự kiện và quy tắc tương thích khác nhau, hệ thống nhanh chóng gặp lỗi khi triển khai phiên bản mới hoặc khi cần phát lại dữ liệu.

**Event schema** là hợp đồng mô tả cấu trúc và ý nghĩa của thông điệp sự kiện. **CloudEvents** là đặc tả mở giúp chuẩn hóa *envelope* (metadata ngữ cảnh) của một sự kiện để các hệ thống có thể nhận diện sự kiện đến từ đâu, thuộc loại nào và có ID gì, thay vì phải học một định dạng bao bọc riêng cho mỗi producer.

Bài học thuộc chương **Sự kiện và dữ liệu streaming** của module **CLOUD_PROVIDERS_AZURE**. Nội dung kết nối thiết kế hợp đồng dữ liệu với Azure Event Grid, Event Hubs, Service Bus, Azure Functions, Java, Azure Storage, Microsoft Entra ID, mạng riêng, giám sát, bảo mật và kiểm soát chi phí trong kiến trúc ứng dụng Azure.

> **Phạm vi:** bài sử dụng **CloudEvents 1.0**, JSON Schema và HTTP làm ví dụ minh họa. CloudEvents chuẩn hóa định dạng/ngữ cảnh sự kiện, **không** tự bảo đảm thứ tự, exactly-once delivery, authentication, schema registry hay idempotency. Tính năng và cú pháp Azure CLI/SDK cần được xác minh cho đúng phiên bản, resource type, SKU và region khi triển khai thực tế.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt *event*, *command*, *state snapshot*, message transport và stream.
2. Thiết kế sự kiện có ngữ nghĩa nghiệp vụ rõ ràng, payload gọn, phiên bản và owner.
3. Giải thích các thuộc tính bắt buộc/tùy chọn của CloudEvents 1.0.
4. Đọc và viết CloudEvents theo **JSON structured mode** và **HTTP binary mode**.
5. Phân biệt `data`, `data_base64`, `datacontenttype` và `dataschema`.
6. Dùng **JSON Schema** để định nghĩa/kiểm tra payload, lên kế hoạch tương thích khi schema thay đổi.
7. Thiết kế event ID, correlation ID, idempotent consumer và transactional outbox.
8. Áp dụng CloudEvents phù hợp với Event Grid, Event Hubs và Service Bus mà không nhầm vai trò từng dịch vụ.
9. Viết mẫu Java dùng CloudEvents SDK để tạo/serialize event và lập bộ contract tests.
10. Thiết kế bảo mật, quan sát, replay, chi phí và quy trình quản trị schema production.

## 2. Event-driven architecture cần hợp đồng dữ liệu

Giả sử Order Service xử lý lệnh đặt hàng. Sau khi giao dịch cơ sở dữ liệu được commit, dịch vụ phát sự kiện `OrderCreated`. Billing, Inventory và Notification đều quan tâm tới sự kiện, nhưng không nhất thiết chạy cùng máy hoặc triển khai cùng phiên bản.

~~~mermaid
flowchart LR
  API["Order API"] --> DB["Orders database"]
  DB --> OUT["Transactional outbox"]
  OUT --> PUB["Event publisher"]
  PUB --> BUS["Event Grid / broker / stream"]
  BUS --> B["Billing"]
  BUS --> I["Inventory"]
  BUS --> N["Notification"]
  PUB -.-> REG["Schema contract / catalog"]
~~~

Những phần cần thống nhất giữa producer và consumer gồm:

- **Ý nghĩa:** "Đơn hàng đã được tạo" xảy ra ở thời điểm nào? Sau khi đã lưu bền vững hay chỉ khi API vừa nhận yêu cầu?
- **Nhận diện:** nguồn, loại, ID và thời điểm xảy ra.
- **Payload:** trường nào bắt buộc, đơn vị đo, kiểu dữ liệu và quy tắc null.
- **Tương thích:** producer thêm/xóa trường thì các consumer cũ có còn hoạt động?
- **Giao nhận:** message có thể trùng, chậm hoặc đến sai thứ tự không?
- **Quản trị:** ai chịu trách nhiệm schema, thay đổi, deprecation và xử lý lỗi?

Nếu chỉ có định dạng JSON mà không giải thích nghiệp vụ, các ứng dụng vẫn có thể hiểu sai. Ví dụ `amount: 1200` không nói rõ đó là 1.200 đồng, 12,00 USD hay 1.200 xu. **Hợp đồng schema phải mô tả cả semantics**, không chỉ JSON syntax.

## 3. Phân biệt event, command và snapshot

| Khái niệm | Nghĩa | Ví dụ tên | Consumer |
|---|---|---|---|
| **Event** | Sự thật đã xảy ra trong quá khứ | `OrderCreated`, `PaymentCaptured` | Một hoặc nhiều bên quan tâm |
| **Command** | Yêu cầu thực hiện hành động, có thể thất bại | `CreateInvoice`, `ReserveInventory` | Thường một handler chịu trách nhiệm |
| **State snapshot** | Trạng thái hiện tại tại một thời điểm | `OrderSnapshot` | Đồng bộ trạng thái, cache hoặc projection |
| **Telemetry** | Quan sát kỹ thuật từ hệ thống | `CpuSample`, `HttpRequestTrace` | Monitoring/analytics |

Một sự kiện **`PaymentCaptured`** chỉ được phát khi nghiệp vụ đã thực sự xác nhận tiền được thu. Nếu ứng dụng mới gửi yêu cầu tới cổng thanh toán thì event nên phản ánh đúng trạng thái như `PaymentCaptureRequested`, không được tuyên bố kết quả đã thành công.

### Vì sao event thường dùng thì quá khứ?

Event mô tả fact, vì vậy tên ở dạng quá khứ giúp người nhận không nhầm với command. Nhưng tên chỉ là tín hiệu: hợp đồng vẫn phải giải thích *khi nào sự kiện được phát* và các điều kiện nghiệp vụ liên quan.

### Event khác API response

HTTP response thường dành cho caller hiện tại, có ngữ cảnh yêu cầu/trả lời. Event được gửi để các thành phần **phản ứng sau khi một điều gì đó xảy ra**. Cùng một workflow có thể dùng command API đồng bộ để tiếp nhận yêu cầu và event bất đồng bộ để thông báo kết quả.

## 4. CloudEvents giải quyết phần nào?

**CloudEvents** là đặc tả mở trong hệ sinh thái CNCF. Nó định nghĩa một mô hình sự kiện có **context attributes** và **event data**, cùng các *format/protocol bindings* giúp biểu diễn trên HTTP hoặc các giao thức khác.

CloudEvents giúp:

1. Các producer và consumer dùng chung các trường như `id`, `source`, `type`, `specversion`.
2. Công cụ trung gian phân loại và định tuyến sự kiện mà không nhất thiết giải mã payload nghiệp vụ.
3. Event metadata không bị phụ thuộc hoàn toàn vào tên một Azure service.
4. Có điểm mở rộng cho tracing, correlation hoặc metadata theo quy ước.
5. Thiết kế được contract độc lập với transport khi kiến trúc thay đổi.

CloudEvents **không**:

- Quy định dữ liệu nghiệp vụ của bạn phải có những trường nào.
- Tự xác thực JSON payload bằng schema registry.
- Tự cam kết sự kiện được gửi đúng một lần hoặc đúng thứ tự.
- Cung cấp broker, queue, lưu trữ bền vững hay replay.
- Tự giải quyết auth, encryption và data governance.
- Biến bất kỳ thông điệp JSON nào thành CloudEvent hợp lệ nếu thiếu context bắt buộc.

Một sự kiện đúng CloudEvents có thể được vận chuyển qua Azure Event Grid hoặc nằm trong body của một Service Bus message. Hành vi retry, DLQ và ordering vẫn do dịch vụ truyền tải và ứng dụng quyết định.

## 5. CloudEvents 1.0: cấu trúc và thuộc tính cốt lõi

CloudEvents có **bốn context attributes bắt buộc**:

| Thuộc tính | Bắt buộc | Kiểu/mục đích | Ví dụ |
|---|---|---|---|
| `specversion` | Có | Phiên bản đặc tả CloudEvents | `"1.0"` |
| `id` | Có | ID nhận diện sự kiện trong phạm vi source | `"evt-7f2a"` |
| `source` | Có | URI-reference nhận diện ngữ cảnh nguồn phát | `"https://events.example.org/orders"` |
| `type` | Có | Loại sự kiện, do producer/hệ thống định nghĩa | `"com.example.orders.created.v1"` |

Các thuộc tính **tùy chọn** thường dùng:

| Thuộc tính | Dùng để làm gì | Lưu ý |
|---|---|---|
| `subject` | Phân biệt đối tượng trong cùng source | Ví dụ `"orders/1024"`; không nhất thiết là URL truy cập |
| `time` | Thời điểm xảy ra sự kiện, RFC 3339 | Ưu tiên UTC, không đồng nghĩa thời gian broker nhận |
| `datacontenttype` | Kiểu media của payload | Ví dụ `"application/json"` |
| `dataschema` | URI nhận diện schema của `data` | Không tự kích hoạt validation hay tải schema |
| Extension attributes | Metadata mở rộng đã thống nhất | Ví dụ `traceparent`, `tenantid` khi phù hợp |

Ngoài context, sự kiện có **event data**, ví dụ JSON của đơn hàng. CloudEvents dùng `data` trong JSON event format để biểu diễn payload và có cơ chế `data_base64` khi cần diễn đạt byte data ở dạng Base64.

### Quan hệ giữa source và id

Tổ hợp **`source` + `id`** cần nhận diện duy nhất một sự kiện trong phạm vi do producer chịu trách nhiệm. Hai source độc lập có thể sử dụng cùng chuỗi ID mà không nhất thiết trỏ tới cùng sự kiện. Khi **giao lại chính cùng event do retry**, giữ nguyên `source` và `id` để consumer có thể phát hiện trùng.

Một cập nhật nghiệp vụ mới, dù thuộc cùng một `orderId`, là **một event mới** và nên có event ID mới. Không dùng `orderId` làm `id` cho mọi sự kiện về cùng đơn hàng.

### Source là định danh, không nhất thiết là endpoint

`source` là một **URI-reference**; một absolute URI là lựa chọn dễ đọc và quản trị. Nó không buộc phải là URL HTTP thực sự cho consumer gọi. Ví dụ `https://events.example.org/orders` có thể chỉ dùng như một namespace ổn định, không tồn tại API tại đó.

## 6. Ví dụ CloudEvent dạng JSON structured

Một sự kiện đơn hàng đã được tạo:

~~~json
{
  "specversion": "1.0",
  "id": "evt-20261120-6d8c",
  "source": "https://events.example.org/commerce/orders",
  "type": "com.example.commerce.order.created.v1",
  "subject": "orders/order-1024",
  "time": "2026-11-20T08:15:00Z",
  "datacontenttype": "application/json",
  "dataschema": "https://schemas.example.org/commerce/order-created/v1.json",
  "data": {
    "orderId": "order-1024",
    "customerRef": "cust-90",
    "currency": "VND",
    "totalAmountMinor": 259000,
    "items": [
      {"sku": "SKU-17", "quantity": 2}
    ]
  }
}
~~~

Nhìn từ consumer:

- `type` giúp chọn handler cho loại sự kiện.
- `source` nói ai phát hành.
- `id` giúp chống xử lý trùng.
- `subject` giúp liên hệ tài nguyên nghiệp vụ.
- `time` giúp quan sát độ trễ phát hành.
- `dataschema` cho biết phiên bản hợp đồng **payload**.
- `data` chứa thông tin nghiệp vụ; schema thực tế phải kiểm tra kiểu và ý nghĩa các trường.

`totalAmountMinor` có nghĩa **đơn vị nhỏ nhất** theo quy ước domain đã thống nhất. Với VND, cần mô tả cách quy đổi và làm tròn đúng nghiệp vụ; đừng chỉ dựa trên tên trường mà bỏ qua đặc tính tiền tệ. Khi làm việc với nhiều currency, cần thống nhất currency exponent và quy tắc amount ở tài liệu hợp đồng.

### Hai lớp version khác nhau

`specversion: "1.0"` là **phiên bản CloudEvents**, không phải phiên bản sự kiện OrderCreated. Version nghiệp vụ có thể biểu đạt trong `type`, `dataschema`, danh mục hợp đồng hoặc cách quản trị được tổ chức chọn. Thay đổi payload không có nghĩa tự động tăng `specversion`.

## 7. data, data_base64 và datacontenttype

Trong CloudEvents JSON Event Format:

- `data` diễn đạt dữ liệu có thể biểu diễn trực tiếp bằng kiểu JSON: object, array, string, number, boolean hoặc null tùy nội dung.
- `data_base64` dùng để mang dữ liệu nhị phân hoặc dữ liệu byte đã được Base64 encode trong JSON format.
- `datacontenttype` mô tả media type của dữ liệu; nó **khác** media type của toàn bộ CloudEvent envelope khi truyền theo structured mode.

Ví dụ binary payload trong CloudEvents JSON format:

~~~json
{
  "specversion": "1.0",
  "id": "evt-binary-01",
  "source": "https://events.example.org/files",
  "type": "com.example.file.sampled.v1",
  "datacontenttype": "application/octet-stream",
  "data_base64": "SGVsbG8="
}
~~~

Chuỗi Base64 trên là dữ liệu minh họa `Hello`, không phải file nhị phân sản xuất. **Không khai báo cả `data` và `data_base64` để mô tả hai payload khác nhau trong cùng một CloudEvent JSON**. Chọn một hình thức dữ liệu và cấu hình serializer/consumer cho thống nhất.

### JSON object không phải JSON string lồng nhau

Đối với `datacontenttype: application/json`, hãy ưu tiên:

~~~json
"data": {"orderId": "order-1024", "status": "CREATED"}
~~~

hơn việc biến object thành một chuỗi JSON bị escape trong `data`. Dạng chuỗi làm consumer phải parse hai lần và dễ gây sai khác kiểu dữ liệu.

### Payload lớn

CloudEvents không loại bỏ giới hạn kích thước của Event Grid, Event Hubs, Service Bus hoặc receiver HTTP. Nếu payload là video, ảnh hoặc tài liệu lớn, dùng **claim-check pattern**:

1. Lưu file ở Blob Storage.
2. Tạo event chứa `blobRef`, size/checksum, version hoặc ETag phù hợp.
3. Consumer dùng managed identity/quyền được cấp để đọc.
4. Xác minh file đã sẵn sàng và checksum khớp.
5. Dọn file theo retention sau khi các consumer đã hoàn tất.

Đừng nhúng SAS token dài hạn hoặc credentials vào `data`, `subject` hay các thuộc tính extension.

## 8. Structured mode và binary mode trên HTTP

CloudEvents có nhiều cách ánh xạ lên HTTP. Hai cách quan trọng:

### Structured content mode

Trong **structured mode**, toàn bộ CloudEvent gồm context và data nằm trong body theo một event format, thường dùng JSON Event Format.

~~~http
POST /events HTTP/1.1
Host: receiver.example.org
Content-Type: application/cloudevents+json

{
  "specversion": "1.0",
  "id": "evt-20261120-6d8c",
  "source": "https://events.example.org/commerce/orders",
  "type": "com.example.commerce.order.created.v1",
  "time": "2026-11-20T08:15:00Z",
  "datacontenttype": "application/json",
  "data": {"orderId": "order-1024"}
}
~~~

HTTP `Content-Type: application/cloudevents+json` mô tả **toàn bộ envelope CloudEvents**. Field `datacontenttype: application/json` mô tả **payload**. Hai giá trị này có nhiệm vụ khác nhau.

### Binary content mode

Trong **binary mode**, metadata CloudEvents được ánh xạ sang HTTP headers `ce-*`, còn body chứa dữ liệu nghiệp vụ:

~~~http
POST /events HTTP/1.1
Host: receiver.example.org
ce-specversion: 1.0
ce-id: evt-20261120-6d8c
ce-source: https://events.example.org/commerce/orders
ce-type: com.example.commerce.order.created.v1
ce-time: 2026-11-20T08:15:00Z
Content-Type: application/json

{"orderId": "order-1024"}
~~~

Trong HTTP binary mapping, `Content-Type` của request mô tả `datacontenttype` của **event data**. Đừng đặt `Content-Type: application/cloudevents+json` cho binary body chỉ chứa `{"orderId":...}` rồi mong server hiểu.

### Chọn cách nào?

| Tiêu chí | Structured JSON | Binary HTTP |
|---|---|---|
| Vị trí metadata | Trong JSON body | Trong HTTP `ce-*` headers |
| Kiểu HTTP Content-Type | `application/cloudevents+json` | Media type của event data |
| Khi phù hợp | Lưu/forward nguyên event, broker body, gateway xử lý envelope | Endpoint HTTP muốn đọc context từ header, body trực tiếp |
| Kiểm thử | Validate toàn JSON event | Validate headers và body, normalize thành event |
| Rủi ro | Nhầm `data` với JSON string, thiếu context | Proxy không giữ header, sai mapping Content-Type |

Một producer và consumer phải **thống nhất format và HTTP binding**. Không được giả định một receiver chỉ hỗ trợ structured sẽ tự nhận binary hoặc ngược lại.

## 9. Thiết kế tên loại sự kiện và source

Tên `type` nên ổn định, rõ domain và có owner. Ví dụ:

~~~text
com.example.commerce.order.created.v1
com.example.commerce.order.cancelled.v1
com.example.billing.invoice.issued.v1
com.example.inventory.stock.reserved.v1
~~~

Đây là **quy ước thiết kế**, không phải cú pháp bắt buộc duy nhất của CloudEvents. Hãy dùng tổ chức/namespace mình kiểm soát, tránh tên mơ hồ như `update`, `event1` hoặc `changed` không có bối cảnh.

### Đặt source theo ranh giới producer

Một lựa chọn:

~~~text
source: https://events.example.org/commerce/orders
type:   com.example.commerce.order.created.v1
subject: orders/order-1024
~~~

`source` là nơi phát hành logic; `subject` là đối tượng cụ thể trong nơi đó. Nếu cùng Order Service phát event từ nhiều node, không nên thay `source` bằng hostname pod ngẫu nhiên: điều đó gây khó dedup, catalog và trace sau mỗi lần scale.

### Không đặt type theo tên hạ tầng tạm thời

`aks-node-42.order-event` hay `queue-abc-update` khiến event contract gắn chặt với topology. Loại event nên gắn với **ngữ nghĩa nghiệp vụ**, còn broker queue/topic name và node location là cấu hình vận hành.

### Một event nên mô tả một sự thật nhất quán

Nếu Order và Payment là hai bounded contexts khác nhau, không vội gộp mọi thay đổi vào một event khổng lồ `EverythingChanged`. Sự kiện nhỏ, rõ nghĩa giúp consumer chỉ nhận những gì cần, có owner và kiểm soát version tốt hơn.

## 10. Viết JSON Schema cho payload

CloudEvents xác định envelope; để kiểm tra payload `data`, có thể dùng **JSON Schema**. Ví dụ hợp đồng cho `com.example.commerce.order.created.v1`:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.org/commerce/order-created/v1.json",
  "title": "OrderCreatedV1",
  "type": "object",
  "required": ["orderId", "currency", "totalAmountMinor", "items"],
  "properties": {
    "orderId": {"type": "string", "minLength": 1, "maxLength": 100},
    "customerRef": {"type": "string", "maxLength": 100},
    "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
    "totalAmountMinor": {"type": "integer", "minimum": 0},
    "items": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["sku", "quantity"],
        "properties": {
          "sku": {"type": "string", "minLength": 1},
          "quantity": {"type": "integer", "minimum": 1}
        },
        "additionalProperties": true
      }
    }
  },
  "additionalProperties": true
}
~~~

Điểm cần chú ý:

- `required` định nghĩa trường không thể thiếu theo contract v1.
- `type: integer` ngăn giá trị tiền ở dạng chuỗi không thống nhất.
- `minimum`, `maxLength`, `pattern` cung cấp ràng buộc cơ bản.
- `additionalProperties: true` cho phép bên gửi thêm trường mới mà **validator của schema này** không từ chối ngay. Consumer vẫn phải được viết để chấp nhận trường lạ.
- `$id` được chọn trùng URI trong `dataschema` để dễ truy vết.
- Đây là **schema cho `data`**, không phải schema bao cả bốn context attributes của CloudEvents.

Schema chỉ kiểm tra cấu trúc/kiểu dữ liệu được khai báo. Nó không tự chứng minh `orderId` thực sự tồn tại, `customerRef` có quyền truy cập hoặc `totalAmountMinor` đúng mức tiền đã thanh toán.

### Tránh thắt chặt contract quá sớm

Nếu producer dự kiến tiến hóa bằng cách thêm field, schema đặt `additionalProperties: false` tại mọi mức có thể khiến consumer strict-validation từ chối message mới. Việc cho phép trường lạ cũng có đánh đổi: lỗi đánh máy field mới có thể khó phát hiện. Giải pháp là **producer validation nghiêm ở version hiện tại** và **consumer validation theo quy tắc tương thích đã chọn**, không chỉ chọn một boolean rồi coi vấn đề đã giải quyết.

## 11. dataschema không phải một dịch vụ kiểm chứng tự động

`dataschema` là URI-reference nhằm nhận diện schema của `data`. Khi một CloudEvent chứa:

~~~json
"dataschema": "https://schemas.example.org/commerce/order-created/v1.json"
~~~

nó không tự có nghĩa:

- Endpoint đó công khai truy cập được từ mọi consumer.
- Broker đã tải và xác thực payload trước khi nhận.
- Schema registry của Azure tự đăng ký URI.
- Consumer bắt buộc thực hiện validation.
- Event sẽ bị từ chối nếu schema bị xóa hoặc sửa.

Nhóm phát triển cần tự quyết định **schema catalog/registry, cách version hóa, validation ở producer/consumer và kiểm thử hợp đồng**.

### Azure Schema Registry nằm ở đâu?

**Azure Schema Registry** trong hệ sinh thái Event Hubs có thể giúp quản lý schema/serialization theo các định dạng và SDK được hỗ trợ. Nhưng không nên coi việc điền `dataschema` vào một CloudEvent là đã tự kích hoạt đăng ký, tương thích hoặc xác minh với Azure Schema Registry.

Nếu cần schema registry trong pipeline, phải thiết kế rõ cách lưu schema, mapping từ `dataschema`/schema ID tới artifact, quyền truy cập và cách serializer/consumer lấy schema theo công nghệ cụ thể.

## 12. Tiến hóa schema: compatible và breaking changes

Một event có thể tồn tại lâu trong stream hoặc queue, và các consumer triển khai không đồng thời. Vì vậy cần quy tắc tương thích giữa **producer mới** và **consumer cũ**.

### Thay đổi thường dễ tương thích

- Thêm **field tùy chọn** với default/semantic rõ ràng.
- Thêm metadata tùy chọn không làm thay đổi ý nghĩa field cũ.
- Đổi cách producer tính toán nội bộ mà giữ nguyên hợp đồng công bố.
- Thêm loại event **mới** thay vì sửa nghĩa một loại hiện có.

### Thay đổi có nguy cơ breaking

- Đổi `totalAmountMinor` từ integer sang string.
- Đổi đơn vị tiền tệ của cùng một field mà không đổi tên/contract.
- Xóa hoặc đổi tên trường required.
- Chuyển `orderId` từ một định danh ổn định sang giá trị tạm.
- Thay ý nghĩa `OrderCreated` từ "đã commit" thành "đang chờ commit".
- Thêm giá trị enum mà consumer cũ không nhận nếu consumer validate enum đóng.
- Thay đổi cấu trúc mảng/object gây sai parser cũ.

### Chiến lược versioning

Một phương án rõ ràng là version trong type:

~~~text
com.example.commerce.order.created.v1
com.example.commerce.order.created.v2
~~~

Khi thay đổi không tương thích, producer có thể trong một giai đoạn phát cả v1 và v2 hoặc cung cấp adapter chuyển đổi, **nhưng phải kiểm soát duplicate business effects** nếu consumer đăng ký cả hai. Lưu thời hạn chuyển tiếp và thời điểm ngừng v1 trong catalog.

Nếu chọn version ở schema URI mà giữ type, cần thống nhất consumer xử lý nhiều schema version dưới cùng một type như thế nào. **Không có một quy tắc CloudEvents bắt buộc mọi hệ thống phải dùng cách nào**; sự nhất quán toàn tổ chức quan trọng hơn tên trường/version tự phát.

### Ma trận tương thích minh họa

| Thay đổi | Consumer cũ strict | Consumer cũ tolerant | Khuyến nghị |
|---|---|---|---|
| Thêm `promotionCode` tùy chọn | Có thể lỗi nếu cấm unknown fields | Thường chấp nhận | Kiểm thử trước và công bố |
| Đổi `totalAmountMinor` sang chuỗi | Lỗi | Có thể lỗi hoặc hiểu sai | Version mới |
| Bỏ `currency` required | Lỗi | Có thể thiếu nghĩa | Version mới hoặc migration |
| Thêm enum value `PENDING_REVIEW` | Có thể lỗi | Chỉ an toàn nếu có fallback | Test consumer |
| Thay ý nghĩa `OrderCreated` | Có thể parse vẫn được nhưng **nghiệp vụ sai** | Nghiệp vụ sai | Type/contract mới |

**Khả năng parse thành công không đồng nghĩa tương thích về nghiệp vụ.**

## 13. Thiết kế event ID và idempotent consumer

Trong kiến trúc event-driven, delivery có thể **at least once**. Một consumer có thể nhận cùng sự kiện nhiều lần vì broker retry, timeout hoặc worker chết sau khi ghi kết quả nhưng trước khi ack.

Cách nhận diện event trùng đề xuất:

~~~text
dedupKey = source + "|" + id
~~~

Đây là biểu diễn logic. Trong database nên dùng **khóa tổng hợp có cấu trúc**, hoặc hash có phạm vi/quy tắc rõ ràng; tránh nguy cơ xung đột vì ký tự phân cách hoặc Unicode normalization nếu nối chuỗi tự phát.

Ví dụ bảng xử lý:

| source | id | consumer | trạng thái |
|---|---|---|---|
| `https://events.example.org/commerce/orders` | `evt-6d8c` | billing | COMPLETED |
| `https://events.example.org/commerce/orders` | `evt-6d8c` | notifications | COMPLETED |

Mỗi consumer có thể có trạng thái xử lý riêng. Billing đã hoàn tất không đồng nghĩa Notifications đã gửi email.

### Quy trình idempotency an toàn

1. Nhận event; kiểm tra bốn context attributes và quyền của source.
2. Kiểm tra event schema, type, version và business key.
3. Thử ghi dấu dedup **có điều kiện** trong data store có concurrency control.
4. Thực hiện side effect nghiệp vụ theo cơ chế transaction/unique constraint phù hợp.
5. Ghi trạng thái hoàn tất cùng transaction khi có thể.
6. Chỉ khi kết quả đã được lưu an toàn mới ack/complete delivery.
7. Nếu đã hoàn tất từ trước, không tạo side effect mới; có thể ack sau khi xác minh.

Nếu một consumer tạo side effect ở **hệ thống bên ngoài** không hỗ trợ transaction chung, cần idempotency key phía đối tác hoặc cơ chế bù trừ và reconciliation. CloudEvents không giải quyết atomic commit xuyên dịch vụ.

### Thời hạn giữ dedup data

Không xóa dấu dedup quá sớm nếu broker/stream có thể redeliver hoặc replay dữ liệu cũ. Retention phải xét **message TTL, stream retention, DLQ replay, backup restore và quy trình operator**. Đồng thời phải có lifecycle dọn dữ liệu đã hết hạn theo chính sách.

## 14. Transactional outbox: phát event sau khi commit

Một failure window kinh điển:

1. Order Service ghi đơn hàng thành công vào database.
2. Chưa kịp gửi `OrderCreated` tới Event Grid hoặc Service Bus.
3. Process chết.
4. Dữ liệu đã thay đổi, nhưng consumer không nhận được event.

Nếu gửi event trước commit database, consumer lại có thể nhận một event về dữ liệu chưa tồn tại hoặc đã rollback.

### Mô hình outbox

~~~mermaid
flowchart TD
  API["Create order"] --> TX["Database transaction"]
  TX --> ORDER["Orders table"]
  TX --> OUT["Outbox: eventId + payload"]
  OUT --> PUB["Publisher đọc bản ghi chưa gửi"]
  PUB --> GRID["Event Grid / Event Hubs / Service Bus"]
  GRID --> C["Idempotent consumers"]
  PUB --> MARK["Đánh dấu outbox đã gửi"]
~~~

Order row và outbox row được ghi trong **cùng một transaction database**. Publisher có thể gửi lại nếu response không rõ ràng; consumer phải idempotent. Outbox không tự bảo đảm exactly-once giao nhận, nhưng tránh tình huống **database đã commit mà chưa có bản ghi cần publish**.

Với database không hỗ trợ transaction mong muốn, cần giải pháp tương ứng như change data capture hoặc cơ chế publish đáng tin cậy, và phải phân tích failure modes cụ thể.

### Inbox ở phía consumer

Một số hệ thống dùng **inbox pattern**: lưu `source`, `id` và trạng thái xử lý trong database consumer để chống trùng và hỗ trợ retry. Kết hợp outbox và inbox hữu ích khi có nhiều dịch vụ cùng tham gia một workflow nhưng không chia sẻ distributed transaction.

## 15. CloudEvents và Azure Event Grid

**Azure Event Grid** là dịch vụ event routing giúp đẩy sự kiện tới những subscriber/destination phù hợp. Nó hỗ trợ **CloudEvents 1.0** trong những loại resource/tính năng được hỗ trợ, ngoài những event schema/định dạng khác.

Một mô hình thông thường:

~~~mermaid
flowchart LR
  P["Producer: Order Service"] --> T["Event Grid Topic nhận CloudEvents"]
  T --> SUB["Event Subscriptions + filters"]
  SUB --> F["Azure Functions / webhook"]
  SUB --> Q["Service Bus / destination phù hợp"]
  F --> DB["Business database"]
~~~

### Phân biệt schema CloudEvents và Event Grid schema

- **CloudEvents 1.0:** dùng `specversion`, `id`, `source`, `type` và các thuộc tính tiêu chuẩn.
- **Event Grid event schema:** có cấu trúc và field riêng như `eventType`, `subject`, `eventTime`, `dataVersion` tùy loại event.
- **Custom event schema:** có thể có mapping/config riêng trong những tài nguyên hỗ trợ.

**Không gửi một Event Grid schema event rồi chỉ đổi HTTP Content-Type thành `application/cloudevents+json` và coi nó là CloudEvent.** Phải chuyển đổi context/fields đúng định dạng.

### Input schema và delivery schema

Tùy loại Event Grid topic, subscription và API, producer có thể chọn CloudEvents input schema và consumer nhận event theo delivery schema được cấu hình/hỗ trợ. Không mặc định mọi combination input/output schema hoặc endpoint binding đều hỗ trợ tùy ý.

Hãy kiểm tra thiết kế **custom topic, domain topic, system topic hoặc namespace topic** mà dự án thực sự dùng; API, tính năng, authentication và quota có thể khác nhau.

### Retry và ordering

Event Grid xử lý giao nhận theo cơ chế retry/TTL/delivery policies của dịch vụ và điểm đích; ứng dụng nên thiết kế **at-least-once** và không dựa vào thứ tự toàn cục. Một event có thể đến lại hoặc đến chậm. Nếu có sự kiện `OrderUpdated` và `OrderCancelled`, consumer phải quản lý version/trạng thái để tránh áp dụng update cũ lên trạng thái mới.

### Subscription filtering

Có thể dùng event type, subject hoặc những thuộc tính hỗ trợ để chọn sự kiện. Vì vậy field `type` và `subject` cần nhất quán và tránh dữ liệu nhạy cảm. Filters trên payload data có thể phụ thuộc loại schema/destination và khả năng tính năng; không thiết kế dựa trên feature chưa kiểm chứng.

## 16. Azure CLI: tạo Event Grid topic nhận CloudEvents

Ví dụ dành cho **Azure Cloud Shell Bash** hoặc Azure CLI đã đăng nhập; chỉ thực hiện trên resource group lab đã được phép. Tạo topic có thể phát sinh chi phí.

### Kiểm tra subscription

~~~bash
az account show \
  --query "{subscription:name,id:id,tenantId:tenantId}" \
  --output table
~~~

Khai báo biến:

~~~bash
RG="rg-events-lab"
LOC="southeastasia"
TOPIC="<GLOBALLY_UNIQUE_TOPIC_NAME>"
~~~

**Giả định** resource group đã tồn tại, danh tính có quyền tạo Event Grid topic, tên topic hợp lệ và region hỗ trợ loại resource. Kiểm tra `az eventgrid topic create --help` của phiên bản CLI hiện hành trước khi chạy.

### Tạo custom topic với CloudEvents input schema

~~~bash
az eventgrid topic create \
  --resource-group "$RG" \
  --name "$TOPIC" \
  --location "$LOC" \
  --input-schema CloudEventSchemaV1_0
~~~

Đây là ví dụ cho **Event Grid custom topic** có hỗ trợ schema tương ứng. Không dùng nguyên lệnh này cho Event Grid Namespace topic mà không điều chỉnh theo resource API của loại topic đó.

### Đọc lại cấu hình

~~~bash
az eventgrid topic show \
  --resource-group "$RG" \
  --name "$TOPIC" \
  --query "{name:name,location:location,inputSchema:inputSchema,endpoint:endpoint}" \
  --output json
~~~

Khi publish thật, cần tuân thủ **endpoint, authentication và yêu cầu định dạng HTTP** của Event Grid custom topic đang dùng, đồng thời cấu hình event subscription để có nơi giao nhận. Không lấy một ví dụ HTTP chung rồi giả định endpoint Azure chấp nhận mọi batching/content mode hoặc mọi loại token.

**Không in hoặc lưu Event Grid access key vào log, source code hoặc hướng dẫn công khai.** Ưu tiên phương thức authentication được chính sách tổ chức cho phép và phân quyền tối thiểu.

## 17. CloudEvents trong Event Hubs và Service Bus

CloudEvents là **định dạng dữ liệu**; broker/stream vẫn giữ semantics riêng.

| Dịch vụ | Vai trò | CloudEvents được dùng thế nào | Lưu ý kiến trúc |
|---|---|---|---|
| **Azure Event Grid** | Routing/push event | CloudEvents 1.0 schema trong đường vào/ra được hỗ trợ | Delivery retry, filtering, không giả định FIFO |
| **Azure Event Hubs** | Ingest/streaming dữ liệu lớn | Ứng dụng có thể serialize CloudEvent vào event body và deserialize ở consumer | Partition, offset, consumer groups, retention/replay |
| **Azure Service Bus** | Enterprise message broker, queues/topics | Có thể mang CloudEvent JSON trong message body theo hợp đồng ứng dụng | Peek-Lock, DLQ, sessions, duplicate detection theo entity |
| **Azure Queue Storage** | Simple task queue | Có thể chứa CloudEvent JSON dạng string/bytes theo quy ước ứng dụng | Visibility timeout, pop receipt, không có broker DLQ tương đương |

### Event Hubs: partition và replay

Event Hubs phù hợp khi cần **ingestion throughput cao, nhiều consumer groups và xử lý stream**. Message body có thể chứa serialized CloudEvent để các consumer dùng chung envelope. Nếu cần thứ tự trong một nhóm entity, chọn partition key phù hợp và hiểu rằng thứ tự thường được xét **trong partition**, không phải toàn bộ event hub.

Offsets/checkpoints của consumer group quản lý vị trí đọc. **Checkpoint không đồng nghĩa side effect đã commit chính xác một lần.** Nếu consumer xử lý xong database rồi chết trước khi checkpoint, event có thể được xử lý lại. Vì vậy vẫn cần idempotency.

### Service Bus: routing và workflow

Service Bus Queue/Topic hữu ích khi cần **Peek-Lock, dead-letter, sessions, scheduling hoặc broker workflows**. Một Service Bus message có thể chứa CloudEvents JSON, nhưng SDK Service Bus không tự biến mọi body thành đối tượng CloudEvent nếu app chưa parse hoặc có integration cụ thể.

### Tránh nhầm Event Grid với Event Hubs

Event Grid thích hợp để **đẩy thông báo rời rạc tới subscribers**. Event Hubs thích hợp cho **dòng sự kiện cần lưu theo retention để nhiều consumer đọc/replay**. Một hệ thống có thể dùng cả hai, nhưng phải ghi rõ chặng nào có thể retry, dữ liệu được giữ bao lâu và consumer nào chịu trách nhiệm checkpoint.

## 18. Java CloudEvents SDK: tạo sự kiện có type rõ ràng

Trong ứng dụng Java, có thể dùng **CloudEvents Java SDK** để tránh tự ghép JSON envelope bằng string. Những Maven artifacts thường gặp:

~~~xml
<dependencies>
  <dependency>
    <groupId>io.cloudevents</groupId>
    <artifactId>cloudevents-api</artifactId>
    <version>${cloudevents.version}</version>
  </dependency>
  <dependency>
    <groupId>io.cloudevents</groupId>
    <artifactId>cloudevents-core</artifactId>
    <version>${cloudevents.version}</version>
  </dependency>
  <dependency>
    <groupId>io.cloudevents</groupId>
    <artifactId>cloudevents-json-jackson</artifactId>
    <version>${cloudevents.version}</version>
  </dependency>
</dependencies>
~~~

Phải khai báo `cloudevents.version` bằng **phiên bản nhất quán, được tổ chức kiểm thử**, và kiểm tra tương thích JDK/SDK hiện hành. Đây là một mảnh `pom.xml`, không phải POM hoàn chỉnh.

### Tạo CloudEvent trong Java

~~~java
import io.cloudevents.CloudEvent;
import io.cloudevents.core.builder.CloudEventBuilder;
import io.cloudevents.core.format.EventFormat;
import io.cloudevents.core.provider.EventFormatProvider;
import io.cloudevents.jackson.JsonFormat;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.UUID;

public final class OrderCreatedEventFactory {

    private static final URI SOURCE =
        URI.create("https://events.example.org/commerce/orders");

    public static CloudEvent create(String orderId, String payloadJson) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        return CloudEventBuilder.v1()
            .withId(UUID.randomUUID().toString())
            .withSource(SOURCE)
            .withType("com.example.commerce.order.created.v1")
            .withSubject("orders/" + orderId)
            .withTime(OffsetDateTime.now(ZoneOffset.UTC))
            .withDataSchema(
                URI.create("https://schemas.example.org/commerce/order-created/v1.json")
            )
            .withData(
                "application/json",
                payloadJson.getBytes(StandardCharsets.UTF_8)
            )
            .build();
    }

    public static byte[] toStructuredJson(CloudEvent event) {
        EventFormat format = EventFormatProvider.getInstance()
            .resolveFormat(JsonFormat.CONTENT_TYPE);

        if (format == null) {
            throw new IllegalStateException(
                "CloudEvents JSON format provider is unavailable"
            );
        }
        return format.serialize(event);
    }
}
~~~

Ví dụ minh họa **event creation và structured serialization**; lớp này chưa thực hiện validation JSON Schema, gửi qua Azure hoặc kiểm tra quyền. `UUID.randomUUID()` phù hợp khi **tạo một event mới**; nếu producer retry **chính event đã tạo**, hãy tái dùng event ID đã lưu trong outbox, không gọi lại factory để sinh ID mới.

`payloadJson` phải được tạo bằng JSON serializer an toàn từ dữ liệu đã validate. **Không** nối chuỗi JSON trực tiếp từ input người dùng rồi tin rằng chuỗi đó hợp lệ. Java CloudEvents SDK hỗ trợ model/event formatting, nhưng **không tự thực hiện business validation** chỉ từ một `dataschema` URI.

### Kiểm thử serialize và round-trip

~~~java
CloudEvent event = OrderCreatedEventFactory.create(
    "order-1024",
    "{\"orderId\":\"order-1024\",\"currency\":\"VND\",\"totalAmountMinor\":259000,\"items\":[{\"sku\":\"SKU-17\",\"quantity\":2}]}"
);

byte[] wire = OrderCreatedEventFactory.toStructuredJson(event);

EventFormat format = EventFormatProvider.getInstance()
    .resolveFormat(JsonFormat.CONTENT_TYPE);

CloudEvent restored = format.deserialize(wire);

assert restored.getSpecVersion().toString().equals("1.0");
assert restored.getId().equals(event.getId());
assert restored.getSource().equals(event.getSource());
~~~

Đoạn trên minh họa các khẳng định cần có; khi viết test thật, dùng **JUnit assertions** thay cho `assert` Java mặc định vì JVM có thể không bật assertions. Ngoài round-trip, phải có contract test cho data fields/schema, hành vi consumer với unknown fields và retry trùng.

## 19. Java HTTP receiver: đọc CloudEvent có validation

Một receiver HTTP có thể nhận structured JSON hoặc binary mode theo cấu hình. Logic tối thiểu nên:

1. Xác nhận requester đã vượt qua authentication/authorization theo cơ chế endpoint.
2. Xác định mode qua `Content-Type`/headers, rồi **parse bằng CloudEvents protocol binding** được SDK/gateway hỗ trợ.
3. Kiểm tra `specversion`, `source`, `type`, `id`.
4. Kiểm tra type nằm trong tập contract được hỗ trợ.
5. Kiểm tra `datacontenttype` và deserialize/validate `data` theo JSON Schema.
6. Thực hiện dedup theo `source` + `id`.
7. Đưa công việc vào queue hoặc xử lý ngắn; lưu kết quả trước khi ack.
8. Trả response phù hợp yêu cầu của event delivery system.

### Không phân tích headers bằng cách thủ công nếu SDK hỗ trợ

Một đoạn kiểu `request.getHeader("ce-type")` rồi lấy body có thể phù hợp cho demo binary mode, nhưng sẽ **không parse được structured mode** và dễ xử lý sai MIME type, encoding hoặc extension attributes.

Nếu dùng Java CloudEvents SDK, lựa chọn HTTP binding/transport module phù hợp với framework (Spring, Vert.x, servlet, v.v.) theo phiên bản SDK, và đặt **contract tests cho cả hai mode** nếu endpoint cam kết hỗ trợ cả hai.

### Validation trên data là bước riêng

Pseudo-code nghiệp vụ:

~~~java
void handle(CloudEvent event) {
    validateRequiredContext(event);
    authorizeLogicalSource(event.getSource());
    Contract contract = registry.resolve(
        event.getType(), event.getDataSchema());
    contract.validate(event.getData());

    String dedupKey = event.getSource() + "|" + event.getId();
    if (inbox.alreadyCompleted(dedupKey)) {
        return;
    }

    businessHandler.processIdempotently(event);
    inbox.markCompleted(dedupKey);
}
~~~

Các kiểu `Contract`, `registry`, `inbox`, `businessHandler` là **thành phần kiến trúc minh họa**, không phải lớp SDK có sẵn. Quy trình production cần transaction/concurrency control để tránh hai worker cùng nhìn "chưa hoàn tất" rồi thực hiện side effect trùng.

Đối với HTTP event delivery, ack chỉ khi sự kiện đã được lưu/queue bền vững theo trách nhiệm của receiver. Nếu trả 2xx trước khi ghi bền vững, broker có thể ngừng retry trong khi receiver mất dữ liệu.

## 20. HTTP smoke test cho structured mode

Sau khi xây một **receiver HTTP lab hỗ trợ structured CloudEvents**, lưu mẫu CloudEvent trong file thử nghiệm `event.json` (file riêng của **người học trong lab**, không phải file module bài học cần tạo ở bước này).

Ví dụ Bash gọi receiver thử nghiệm do bạn kiểm soát:

~~~bash
curl --fail-with-body --silent --show-error \
  --request POST "http://localhost:8080/events" \
  --header "Content-Type: application/cloudevents+json" \
  --data-binary @event.json
~~~

`curl --fail-with-body` yêu cầu phiên bản curl hỗ trợ; nếu không có, thay bằng cách xem HTTP status và response body theo công cụ hiện tại.

**Đường `http://localhost:8080/events` chỉ là receiver lab giả định**, không phải Azure Event Grid endpoint mặc định. Khi publish tới Azure Event Grid, phải dùng **topic endpoint, xác thực, request format và batch rules** của tài nguyên thực, không thay host rồi coi toàn bộ giao thức giống nhau.

Một bộ smoke test tốt gồm:

| Test | Input | Kỳ vọng |
|---|---|---|
| Hợp lệ | CloudEvent đủ context, payload đúng schema | Accepted, ghi kết quả |
| Thiếu `id` | Event không có required attribute | Bị từ chối |
| Sai `specversion` | `"2.0"` khi chỉ hỗ trợ 1.0 | Bị từ chối/route rõ ràng |
| Unknown `type` | Contract chưa hỗ trợ | Không silently xử lý sai |
| Payload sai kiểu | `totalAmountMinor: "259000"` | Validation failure |
| Event trùng | Cùng `source` + `id` được giao lại | Không tạo side effect trùng |
| Event đến muộn | `time` cũ hơn event đã áp dụng | Xử lý theo business version |
| JSON binary `data_base64` | Bytes phù hợp media type | Deserialize đúng, không nhầm string |
| Unauthenticated sender | Thiếu/sai credential | Không cho phép xử lý |
| Receiver crash trước ack | Same event delivered again | Idempotency bảo vệ |

## 21. Schema contract testing và CI/CD

Một pipeline tốt không dừng ở việc file JSON Schema parse được. Nó phải thử **producer và consumer dùng cùng ý nghĩa**.

~~~mermaid
flowchart TD
  PR["Thay đổi producer/schema"] --> LINT["Validate schema syntax + conventions"]
  LINT --> COMP["Compatibility check với contract đã publish"]
  COMP --> PTEST["Producer example contract tests"]
  PTEST --> CTEST["Consumer contract tests"]
  CTEST --> STAGE["Staging: publish, deliver, retry, replay"]
  STAGE --> OK{"Đạt tiêu chí?"}
  OK -->|Có| PUB["Đăng ký/phiên bản hóa contract, deploy có kiểm soát"]
  OK -->|Không| FIX["Sửa schema hoặc làm migration"]
~~~

### Những thứ nên lưu trong event catalog

- Event type, source và mô tả nghĩa vụ producer.
- Schema URI/version và nơi lưu artifact bất biến.
- Chủ sở hữu/nhóm hỗ trợ và kênh thông báo thay đổi.
- Danh sách consumer hoặc subscription quan trọng.
- Retention, PII classification, validation rules.
- Compatibility policy: tolerant readers, required fields, enum handling.
- Cách nhận diện event và dedup, các mốc deprecation.
- Ví dụ event hợp lệ và event lỗi.
- SLO freshness, delivery expectation và cách replay.

### Contract tests quan trọng

1. Producer luôn phát bốn context attributes hợp lệ.
2. `source`/ `id` ổn định khi cùng event được retry.
3. `data` hợp schema và không lộ secrets.
4. Type/version chính xác và không đổi nghĩa field cũ.
5. Consumer cũ vẫn parse event có **field tùy chọn mới** nếu policy yêu cầu.
6. Consumer nhận **event type mới** theo cơ chế ignore/DLQ rõ ràng, không làm sập toàn bộ worker.
7. Duplicate delivery không tạo side effect hai lần.
8. Replay event cũ không phá trạng thái mới.
9. HTTP structured/binary được xử lý đúng nếu public contract tuyên bố hỗ trợ cả hai.

## 22. Ordering, late events và replay

CloudEvents có `time`, nhưng **không có thứ tự xử lý toàn cục được bảo đảm bởi bản thân spec**. Truyền qua Event Grid, Event Hubs hoặc Service Bus sẽ có semantics khác nhau.

Ví dụ:

~~~text
T1: OrderCreated
T2: OrderPaid
T3: OrderCancelled

Consumer có thể nhận: OrderPaid -> OrderCreated -> OrderCancelled
hoặc nhận OrderCreated hai lần.
~~~

Nếu consumer dùng last-write-wins theo **thời gian nhận**, nó có thể tạo trạng thái sai. Thay vào đó cân nhắc:

- **Aggregate version** tăng đơn điệu do producer sở hữu, ví dụ `orderVersion: 3`.
- Idempotent state transition, chỉ chấp nhận những chuyển trạng thái hợp lệ.
- Thứ tự theo partition/session key khi broker hỗ trợ và phù hợp.
- Buffer/reorder có timeout cho một số stream processing.
- Event sourcing/replay có version và snapshot khi nghiệp vụ thực sự cần.

### Không dùng time làm khóa thứ tự tuyệt đối

Đồng hồ các máy có thể lệch; hai event có cùng timestamp và delivery có thể đến chậm. `time` hữu ích để đo freshness nhưng **không phải sequence number**. Với domain yêu cầu thứ tự, chọn domain sequence/version có semantics rõ.

### Replay và DLQ

Khi phát lại event từ DLQ hoặc stream retention, nên giữ **ID và source gốc** nếu đó là cùng event, đồng thời lưu replay-attempt metadata riêng trong logging/quy trình. Nếu bạn phát ra một **event nghiệp vụ mới** như `OrderReprocessed`, mới dùng ID/type mới. Tránh vừa giữ ID cũ vừa đổi meaning của data một cách lặng lẽ.

## 23. Bảo mật và bảo vệ dữ liệu

CloudEvents metadata không phải chứng thực identity. Một caller không tin cậy có thể tự gửi:

~~~json
{
  "specversion": "1.0",
  "id": "forged",
  "source": "https://events.example.org/payments",
  "type": "com.example.billing.payment.captured.v1",
  "data": {"orderId": "order-1024"}
}
~~~

**Đừng tin `source` chỉ vì chuỗi đó giống một URL nội bộ.** Receiver/broker phải kiểm tra identity/credential của sender ở transport hoặc gateway, đối chiếu mapping giữa **identity được phép** và **source/type được phép công bố**.

### Các lớp bảo mật

1. **Authentication:** Entra ID, managed identity, workload identity hoặc cơ chế xác thực được Event Grid/receiver hỗ trợ.
2. **Authorization:** chỉ producer được cấp quyền gửi type/source trong phạm vi của mình; consumer chỉ đọc subscription cần thiết.
3. **Network:** Private Endpoint, firewall, VNet integration, DNS và egress controls theo loại dịch vụ/SKU.
4. **Transport security:** TLS, xác minh hostname/cert và chống downgrade khi truyền qua mạng.
5. **Payload protection:** dữ liệu nhạy cảm được phân loại, hạn chế/ẩn danh hóa, mã hóa theo chính sách.
6. **Schema validation:** không nhận event loại lạ hoặc field sai kiểu rồi thực thi nguy hiểm.
7. **Audit:** log event ID, type, source và kết quả, tránh log toàn bộ payload chứa PII.
8. **Retention/deletion:** đáp ứng chính sách lưu trữ, xóa và phát lại của doanh nghiệp.

### Extension attributes

CloudEvents cho phép mở rộng context với các tên/giá trị hợp lệ; ví dụ `traceparent` trong hệ thống tracing có quy ước tương ứng. Nên ưu tiên các extension đã được cộng đồng/công cụ hỗ trợ và không tùy tiện thêm email, số điện thoại hoặc access token vào metadata: attributes có thể bị các broker/gateway ghi log hoặc dùng để filter.

### Multi-tenant

Nếu event chứa `tenantid`, vẫn phải kiểm tra rằng producer **được phép phát hành cho tenant đó** và consumer có quyền xử lý. Một string trong header không thay thế token claims/RBAC và kiểm tra business authorization.

## 24. Observability: đo độ trễ và thành công end-to-end

Cần theo dõi cả đường đi **publish → deliver → process → business effect**.

| Chỉ số | Mục đích |
|---|---|
| Events produced/s | Phát hiện producer tăng/giảm bất thường |
| Publish failure rate | Lỗi authentication, quota, timeout, mạng |
| Broker delivery attempts | Đánh giá retry hoặc endpoint bất ổn |
| Event freshness | Thời gian xử lý trừ `time` event, có xét lệch clock |
| Consumer processing duration | Phát hiện bottleneck business logic |
| Duplicate/drop count | Theo dõi dedup và số event từ chối |
| Dead-letter/unhandled events | Tìm schema lạ, lỗi kéo dài hoặc vượt policy |
| Schema validation failures | Phát hiện producer vi phạm contract |
| End-to-end completed business events | Đo kết quả thật, không chỉ HTTP 2xx |
| Costs | Broker, storage, compute, network và log ingestion |

### Correlation

- `id`: identity của event để dedup.
- `traceparent`/trace context theo chuẩn tracing được triển khai: liên hệ giữa dịch vụ nếu có.
- `correlationId`: ID nghiệp vụ hoặc request-chain theo quy ước của tổ chức.
- `orderId`/subject: business aggregate liên quan, không phải sự kiện duy nhất.

Không dùng cùng một chuỗi cho mọi mục đích mà không phân biệt. Một order có thể có nhiều events, một trace có thể chứa nhiều spans và một event có thể được deliver nhiều lần.

### Alerts có hành động

- Topic publish errors hoặc event delivery failures tăng.
- DLQ/subscription backlog vượt ngưỡng hoặc sự kiện quá tuổi.
- Schema validation failures sau một release mới.
- Consumer latency p95 vượt SLO.
- Tỷ lệ event duplicate tăng bất thường hoặc outbox publish chậm.
- Event type quan trọng có producer ngừng phát trong cửa sổ mong đợi.
- Chi phí operations/logging tăng so với khối lượng nghiệp vụ hoàn tất.

Khi xây dashboard Azure Monitor, lấy **metric definitions của đúng loại Event Grid/Event Hubs/Service Bus resource**; không tự giả định các tên metric giống nhau giữa các dịch vụ.

## 25. Hiệu năng, kích thước sự kiện và chi phí

### Envelope có overhead

CloudEvents bổ sung các thuộc tính metadata, vì vậy message có thể lớn hơn JSON payload thuần. Overhead thường hợp lý cho observability và interoperability, nhưng ở luồng telemetry rất lớn, cần đo kích thước event trung bình, batch strategy và chi phí broker/storage.

### Structured và binary có chi phí thực tế khác nhau?

Khác biệt nằm ở cách biểu diễn metadata và payload; **không thể kết luận mode nào luôn nhanh/rẻ hơn** nếu chưa đo network, serialization, HTTP headers, batching và giới hạn broker/receiver. Tối ưu nên ưu tiên **tính tương thích và dễ vận hành** trước.

### Những nguồn chi phí

- Event Grid events/operations/delivery theo biểu giá và resource type.
- Event Hubs namespace/throughput hoặc capacity, retention và consumer processing.
- Service Bus tier, operations, subscriptions/forwarding và capacity.
- Blob Storage nếu dùng claim-check hoặc giữ payload dài hạn.
- Azure Functions, Container Apps, AKS hoặc VM xử lý sự kiện.
- Application Insights/Log Analytics, distributed tracing và log retention.
- Network transfer, Private Endpoint, Firewall/NAT và cross-region replication.
- Retries, duplicate delivery, schema errors và replay.

Tính **cost per successfully processed business event**, không chỉ giá một request publish. Nếu một lỗi schema tạo hàng nghìn lần retry, compute và log cost có thể vượt chi phí truyền dữ liệu gốc.

## 26. Troubleshooting: lỗi schema hay lỗi transport?

| Triệu chứng | Nguyên nhân khả dĩ | Cách điều tra |
|---|---|---|
| Receiver báo thiếu `specversion` | JSON không phải CloudEvent hoặc parse mode sai | Kiểm tra structured body, binary headers và Content-Type |
| HTTP 415 Unsupported Media Type | Sender dùng Content-Type không phù hợp | `application/cloudevents+json` vs binary body media type |
| HTTP 400 invalid CloudEvent | Thiếu `id`/`source`/`type`, timestamp sai, dữ liệu format lỗi | Validate envelope và JSON serialization |
| Payload hợp JSON nhưng sai nghiệp vụ | Thiếu required fields, sai đơn vị/enum | Kiểm tra JSON Schema và semantic contract |
| Event Grid topic từ chối event | Input schema/resource API/auth không khớp | Topic inputSchema, endpoint, permissions, format |
| Consumer không nhận event | Subscription filter sai hoặc endpoint lỗi | Kiểm tra type/subject, subscription state, delivery metrics |
| Event đến trùng | Retry, timeout, DLQ replay | Dedup `source`+`id`, business idempotency |
| Consumer bỏ sót event sau DB commit | Publish failure window | Transactional outbox + publisher health |
| Event xử lý sai thứ tự | Broker delivery không đảm bảo order toàn cục | Aggregate version, session/partition design |
| Data bị parse thành string | JSON object bị serialize hai lần | Sửa `data` JSON và deserializer |
| Consumer không nhận được binary payload | Sai Base64 hoặc media type | Kiểm tra `data_base64`, datacontenttype và decoded bytes |
| Tracing đứt đoạn | Không truyền trace context hoặc correlation | Kiểm tra extension headers/metadata và sampling |
| Lỗi 403 khi publish | Thiếu quyền, SAS/token hoặc firewall | Identity, RBAC, resource access và error details |
| Event Hubs replay tạo bản ghi trùng | Consumer checkpoint chưa gắn với side effect | Inbox/idempotency, checkpoint strategy |
| Schema URI không truy cập được | Link bị đổi/xóa, DNS/firewall hoặc design registry | Artifact retention, catalog và local schema cache |
| Chi phí tăng sau khi bật debug | Log toàn payload, retries hoặc stream throughput | Cost Management, telemetry sampling và retention |

**Thứ tự điều tra đề xuất:** định dạng CloudEvents → transport/binding → authentication → source/type/schema → broker routing → consumer validation → idempotency/business side effects → monitoring/cost.

## 27. Case study: order lifecycle với CloudEvents

### Bối cảnh

Một hệ thống bán hàng chạy trên Azure có:

- Order API và Orders Database.
- Event Grid để thông báo thay đổi trạng thái đơn.
- Billing, Inventory, Email và Analytics consumers.
- Blob Storage cho dữ liệu lớn hoặc báo cáo.
- Azure Functions Java/Container Apps làm consumer.
- Quyền Entra ID và private networking theo chính sách.

Yêu cầu: sự kiện phải dễ nhận diện, có thể phát lại/kiểm tra và không tạo hóa đơn trùng nếu broker retry.

### Thiết kế contract

| Event | Khi phát | Consumer | Dữ liệu tối thiểu |
|---|---|---|---|
| `OrderCreated.v1` | Đơn hàng đã commit | Billing, Inventory, Analytics | orderId, currency, total, items |
| `PaymentCaptured.v1` | Cổng thanh toán xác nhận thu tiền | Order, Analytics | orderId, paymentRef, amount |
| `InventoryReserved.v1` | Kho giữ hàng thành công | Fulfillment | orderId, reservationRef |
| `OrderCancelled.v1` | Hủy đơn đã commit | Billing, Inventory, Email | orderId, reasonCode, aggregateVersion |

Các tên trong bảng là tên ngắn để dễ đọc; bản wire `type` nên dùng quy ước namespace đầy đủ như `com.example.commerce.order.created.v1`.

### Các lựa chọn quan trọng

1. **Event ID khác order ID:** mọi sự kiện mới có `id` riêng; retry cùng event giữ ID.
2. **Schema bất biến theo version:** `dataschema` trỏ bản hợp đồng v1/v2 không âm thầm thay đổi.
3. **Outbox:** Orders Database và event record được commit cùng transaction.
4. **Independent consumers:** mỗi consumer dedup và quản lý lỗi/timeout riêng.
5. **Không có global FIFO:** `aggregateVersion` giúp chống xử lý update cũ.
6. **Replay:** giữ ID gốc với cùng event, có governance và quan sát.
7. **Security:** Billing không tin mù quáng một `PaymentCaptured` giả; kiểm tra identity nguồn và business state.
8. **SLO:** định nghĩa độ trễ từ lúc commit tới lúc Billing xử lý.
9. **DLQ/runbook:** event không hợp schema hoặc consumer lỗi kéo dài có nơi cách ly và owner.

### Luồng xử lý

~~~mermaid
flowchart LR
  ORDER["Order API"] --> DB["Orders DB + outbox"]
  DB --> PUB["Outbox publisher"]
  PUB --> GRID["Event Grid CloudEvents 1.0"]
  GRID --> SUB1["Billing consumer"]
  GRID --> SUB2["Inventory consumer"]
  GRID --> SUB3["Analytics consumer"]
  SUB1 --> BDB["Billing DB + inbox"]
  SUB2 --> IDB["Inventory DB + inbox"]
  SUB3 --> AD["Analytics store"]
~~~

Đây là sơ đồ logic, không ngầm hứa Event Grid có durable inbox hoặc DLQ giống Service Bus. Cơ chế lưu lỗi/retry phải cấu hình theo destination/delivery features thực sự hỗ trợ, hoặc bổ sung broker/storage phù hợp.

## 28. Bài thực hành tổng hợp

### Phần A — Định nghĩa event

Thiết kế `DocumentProcessed` cho một hệ thống nhận file PDF:

1. Chọn `source` ổn định theo domain, không theo tên VM/pod.
2. Chọn `type` có namespace và chiến lược version.
3. Tạo `id` duy nhất khi phát sự kiện mới.
4. Chọn `subject` là tham chiếu tài liệu, không chứa PII vượt mức cần thiết.
5. Dùng `time` dạng UTC RFC 3339.
6. Dùng `data` gồm documentId, status, outputBlobRef, size, checksum.
7. Viết JSON Schema cho payload; mô tả required/optional fields.
8. Đặt `dataschema` trỏ tới URI schema version tương ứng.
9. Viết một event hợp lệ và ít nhất ba event lỗi.

### Phần B — CloudEvents HTTP

1. Chuyển event sang **structured JSON** với `application/cloudevents+json`.
2. Chuyển cùng event sang **binary HTTP** với `ce-specversion`, `ce-id`, `ce-source`, `ce-type` và body data.
3. Giải thích vì sao `Content-Type` khác nhau giữa hai mode.
4. Tạo receiver lab hoặc dùng một receiver test có quyền truy cập được phép.
5. Xác minh parse được hai mode nếu receiver quảng bá hỗ trợ cả hai.
6. Kiểm thử event thiếu `source`, `time` sai format và payload không đúng schema.
7. Kiểm tra cùng event được giao lại không tạo output trùng.

### Phần C — Tích hợp Azure

1. Kiểm tra subscription/resource group/region được phép.
2. Tạo **Event Grid custom topic** có CloudEvents input schema trong lab nếu phù hợp.
3. Tạo subscription hướng tới endpoint đã hỗ trợ đúng delivery schema/validation/auth.
4. Publish event thử theo đúng cơ chế xác thực của Event Grid resource.
5. Xem delivery success/failure/retry metrics và log consumer.
6. Tạo một biến thể event v1 thêm field tùy chọn; kiểm tra consumer cũ.
7. Tạo biến thể breaking thay kiểu field; chứng minh consumer cũ từ chối hoặc xử lý sai nếu không version.
8. Thực hành outbox/inbox trên database lab hoặc mô hình giả lập có transaction.
9. Đánh giá dùng **Event Hubs** nếu cần replay stream lớn, hoặc **Service Bus** nếu cần DLQ/session/transaction broker.
10. Dọn tài nguyên lab, kiểm tra chi phí và không làm ảnh hưởng subscription dùng chung.

### Câu hỏi tự kiểm tra

**Câu 1.** Bốn thuộc tính CloudEvents 1.0 bắt buộc là gì?

**Câu 2.** `specversion` và `dataschema` thể hiện hai loại phiên bản khác nhau như thế nào?

**Câu 3.** Tại sao `source` không đồng nghĩa với endpoint thực có thể gọi và không phải bằng chứng authentication?

**Câu 4.** Cùng một `orderId` có thể có nhiều event ID hay không? Khi retry cùng event thì dùng ID nào?

**Câu 5.** Sự khác nhau giữa `data`, `data_base64` và `datacontenttype`?

**Câu 6.** Structured mode và HTTP binary mode thể hiện metadata CloudEvents ở đâu? `Content-Type` có vai trò gì?

**Câu 7.** Vì sao JSON Schema cho `data` không thay thế validation của CloudEvents context?

**Câu 8.** Thêm một field tùy chọn luôn tương thích ngược với mọi consumer không? Điều kiện gì cần đúng?

**Câu 9.** Khi thay `totalAmountMinor` từ number sang string, nên xử lý versioning thế nào?

**Câu 10.** CloudEvents có bảo đảm thứ tự hoặc exactly-once delivery không? Nếu không, ứng dụng phải làm gì?

**Câu 11.** Khi database đã commit nhưng producer chết trước publish, pattern nào cần dùng?

**Câu 12.** Event Grid, Event Hubs và Service Bus khác nhau về vai trò transport/broker/stream ra sao?

**Câu 13.** Tại sao `dataschema` không tự làm Azure Schema Registry tải và kiểm tra payload?

**Câu 14.** Khi consumer thấy `PaymentCaptured` với `source` trông giống nội bộ, cần kiểm tra gì trước khi tin?

**Câu 15.** Replay event cũ khác với phát ra một business event mới ở khía cạnh `source`/`id` thế nào?

**Tiêu chí hoàn thành:** người học thiết kế được CloudEvents 1.0 hợp lệ, có JSON Schema và version policy; phân biệt structured/binary HTTP; mô tả được Event Grid/Event Hubs/Service Bus; xây được Java serializer/test; giải thích đúng idempotency, outbox, replay, bảo mật và giám sát.

## Kết luận

**Thiết kế event schema** là xây dựng một hợp đồng nghiệp vụ bền vững giữa producer và consumer, trong khi **CloudEvents** chuẩn hóa cách biểu diễn ngữ cảnh sự kiện bằng những thuộc tính như `specversion`, `id`, `source` và `type`. JSON Schema giúp kiểm tra cấu trúc payload; chiến lược versioning và contract tests bảo vệ các consumer khi hệ thống thay đổi.

Trong Azure, có thể dùng CloudEvents với **Event Grid** để định tuyến sự kiện, hoặc mang CloudEvent serialized qua **Event Hubs/Service Bus** khi cần streaming hay broker features. Tuy nhiên, **CloudEvents không tự cung cấp exactly-once, ordering, authentication hoặc business validation**. Kiến trúc production phải kết hợp **outbox/inbox, idempotent consumers, dữ liệu có version, kiểm soát identity/network, monitoring, replay và quản trị schema**. Làm rõ các yếu tố đó từ đầu giúp hệ thống Azure mở rộng qua nhiều dịch vụ mà vẫn giữ đúng nghĩa dữ liệu, giảm lỗi tích hợp và kiểm soát chi phí vận hành.

