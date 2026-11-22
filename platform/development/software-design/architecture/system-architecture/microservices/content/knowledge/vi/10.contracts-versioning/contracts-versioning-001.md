# Hợp đồng API và thông điệp như ranh giới phối hợp giữa các nhóm

## 1. Vì sao hợp đồng quan trọng hơn sơ đồ mũi tên?

Trong một hệ thống microservices, nhiều nhóm có thể phát triển và triển khai các năng lực khác nhau: Order, Payment, Inventory, Customer, Notification và Reporting. Mỗi nhóm có repository, lịch phát hành, cơ sở dữ liệu và ưu tiên công việc riêng. Khi một service gọi một service khác qua HTTP hoặc nhận sự kiện qua message broker, **điểm phụ thuộc thực sự không chỉ là địa chỉ mạng hay tên topic, mà là một hợp đồng về hành vi có thể quan sát**.

Nếu Order cần Payment trả trạng thái giao dịch, nhóm Order không nên phải đọc mã nguồn Payment để đoán từng giá trị status nghĩa là gì. Nếu Inventory phát sự kiện StockReserved, nhóm Notification cần biết sự kiện được phát vào thời điểm nào, có thể bị gửi trùng không và có những trường nào bảo đảm tồn tại. Nếu Payment đổi tên một trường JSON và buộc tất cả consumer sửa trong một ngày, các nhóm chưa có ranh giới phối hợp ổn định dù phần mềm đã được chia thành nhiều service.

**Hợp đồng API và thông điệp là ranh giới phối hợp giữa các nhóm** vì chúng quy định những gì bên cung cấp cam kết và những gì bên tiêu thụ được phép phụ thuộc. Phần triển khai bên trong có thể thay đổi; các bên khác vẫn hoạt động nếu hành vi nằm trong hợp đồng đã công bố.

Mục tiêu:
- Phân biệt hợp đồng với endpoint, schema, mã nguồn và tài liệu nội bộ.
- Xác định quyền sở hữu, nghĩa vụ của provider và consumer.
- Thiết kế API đồng bộ và thông điệp bất đồng bộ có ngữ nghĩa nghiệp vụ rõ.
- Định nghĩa tính tương thích, phiên bản và quy trình thay đổi không yêu cầu triển khai đồng loạt.
- Áp dụng kiểm thử hợp đồng, catalog, quan sát vận hành và cơ chế phối hợp giữa các nhóm.
- Thực hành với ví dụ thương mại điện tử và tình huống chuyển đổi hợp đồng thực tế.

**Nguyên tắc trọng tâm:** Một hợp đồng tốt cho phép provider sửa cách triển khai mà không phá vỡ consumer; cho phép consumer xây tính năng dựa trên những cam kết có thể kiểm chứng, thay vì dựa vào giả định ngầm.

## 2. Hợp đồng là gì và không phải là gì?

Một hợp đồng tích hợp mô tả **tương tác hợp lệ và kết quả có thể quan sát** giữa các bên. Đối với API, nó thường gồm đường dẫn, phương thức, cấu trúc request/response, trạng thái, lỗi, phân quyền, idempotency, thời gian chờ và ngữ nghĩa nghiệp vụ. Đối với thông điệp, nó còn gồm loại thông điệp, envelope, payload, thời điểm phát, thứ tự, khóa định tuyến, quy tắc giao lại, khả năng phát lại và cách tiến hóa schema.

Một file OpenAPI, AsyncAPI, JSON Schema, Avro schema hoặc protobuf định nghĩa một phần quan trọng của hợp đồng. Tuy nhiên **schema hợp lệ chưa chứng minh hành vi nghiệp vụ đúng**.

Ví dụ một API trả:

~~~json
{
  "paymentId": "pay-77",
  "status": "SUCCESS"
}
~~~

Hai nhóm có thể hiểu khác nhau:
- Nhóm A hiểu SUCCESS nghĩa là nhà cung cấp đã thu tiền và giao dịch được ghi nhận có hiệu lực.
- Nhóm B hiểu SUCCESS chỉ nghĩa là yêu cầu thanh toán đã được xếp hàng xử lý.

JSON giống nhau nhưng hợp đồng nghiệp vụ khác nhau. Không có tài liệu ngữ nghĩa, consumer có thể xác nhận đơn khi Payment chưa hoàn tất.

### 2.1. Phần công khai và phần nội bộ

**Được phép phụ thuộc theo hợp đồng:**
- Tên command, endpoint hoặc event và ngữ nghĩa đã công bố.
- Các trường cần thiết, kiểu và đơn vị.
- Quy tắc retry, lỗi, trạng thái và bảo đảm vận hành được ghi nhận.
- Lịch chuyển đổi/khai tử phiên bản theo cam kết.

**Không được xem là hợp đồng trừ khi đã công bố:**
- Tên bảng, cột, quan hệ database nội bộ của service khác.
- Cấu trúc class JPA, entity domain, phương thức private.
- Thứ tự các hàm trong implementation hoặc tên framework.
- Cách provider bố trí container, queue nội bộ hay cache.
- Một trường tình cờ xuất hiện trong response nhưng không nằm trong hợp đồng được hỗ trợ.

Khi consumer dựa vào chi tiết nội bộ, thay đổi hợp lý của provider trở thành thay đổi liên nhóm, làm mất độc lập phát hành.

### 2.2. Hợp đồng không đồng nghĩa API luôn ổn định vĩnh viễn

Hợp đồng có thể phát triển. Điều quan trọng là các thay đổi được **phân loại, thông báo, kiểm tra tương thích và triển khai theo giai đoạn**. “Chúng tôi có version v1” chưa đủ nếu semantic của v1 âm thầm thay đổi sau mỗi release.

## 3. Hợp đồng là một ranh giới tổ chức và trách nhiệm

Khi các nhóm làm việc độc lập, phải rõ ai quyết định, ai triển khai và ai chịu tác động.

| Vai trò | Trách nhiệm chính |
|---|---|
| **Provider / producer** | Sở hữu hành vi và dữ liệu nguồn, công bố API/event, duy trì cam kết, đánh giá thay đổi |
| **Consumer** | Sử dụng hợp đồng theo cách đã định nghĩa, nêu rõ các giả định cần bảo đảm, chịu được các tình huống được hợp đồng cho phép |
| **Domain owner / product owner** | Giải quyết ý nghĩa nghiệp vụ và các bất biến quan trọng |
| **Platform team** | Cung cấp hạ tầng API gateway, broker, schema registry, quan sát, pipeline; không tự nhận quyền quyết định nghiệp vụ |
| **Security/compliance** | Xác định yêu cầu phân quyền, dữ liệu nhạy cảm, bảo mật và lưu giữ phù hợp |
| **Architecture review / technical lead** | Hỗ trợ kiểm soát phụ thuộc liên miền, rủi ro và phương án tiến hóa khi tác động rộng |

Một nhóm có thể kiêm nhiều vai trò. Mấu chốt là **mỗi hợp đồng có một owner cuối cùng** để giải thích, phê duyệt thay đổi và xử lý sự cố.

### 3.1. Trách nhiệm không chỉ nằm ở provider

Provider phải giữ lời hứa, nhưng consumer cũng phải cư xử đúng hợp đồng.

Ví dụ API thông báo rằng trường middleName là tùy chọn. Consumer không được giả định nó luôn có giá trị rồi crash khi null. Sự kiện có bảo đảm at-least-once thì consumer không được giả định chỉ nhận đúng một lần. API công bố enum có thể mở rộng thì consumer không nên hardcode một exhaustive switch không có nhánh xử lý giá trị chưa biết, nếu hợp đồng yêu cầu chịu được trường hợp đó.

Ngược lại, provider không được dùng chữ “consumer nên linh hoạt” để hợp thức hóa việc xóa một trường bắt buộc đang được sử dụng.

### 3.2. Quyền tự chủ của nhóm được đo bằng khả năng thay đổi

Một câu hỏi thực tế:

> Nếu Payment chuyển từ một nhà cung cấp thanh toán sang nhà cung cấp khác, Order và Notification có cần thay code không?

Nếu Order chỉ phụ thuộc vào ChargePayment, PaymentCaptured và các trạng thái nghiệp vụ đã công bố, thay đổi nội bộ thường không đòi consumer sửa. Nếu Order phụ thuộc trực tiếp vào gatewayTransactionCode của nhà cung cấp cũ, ranh giới hợp đồng đã bị rò rỉ.

Tương tự, nếu Inventory chuyển PostgreSQL sang một datastore khác và chỉ thay repository nội bộ, consumer không nên phải sửa DTO hoặc script query thẳng dữ liệu Inventory.

## 4. Thiết kế hợp đồng từ ngôn ngữ miền

Điểm bắt đầu của hợp đồng không nên là “database có những cột nào”. Hãy hỏi:
- Consumer muốn yêu cầu **hành vi** nào?
- Provider có quyền xác nhận sự thật gì?
- Điều gì tạo thành thành công, từ chối nghiệp vụ và kết quả chưa xác định?
- Dữ liệu nào thực sự cần vượt ranh giới?
- Những trạng thái nào consumer được phép căn cứ để đưa ra quyết định?

Ví dụ trong hệ thống bán hàng, những cụm từ có ý nghĩa:
- ReserveStock: yêu cầu Inventory giữ hàng.
- StockReserved: Inventory xác nhận giữ hàng đã xảy ra.
- CapturePayment: yêu cầu Payment thu tiền theo chính sách.
- PaymentCaptured: Payment xác nhận khoản thu đã có hiệu lực.
- OrderConfirmed: Order xác nhận đơn đáp ứng điều kiện nghiệp vụ.

Không nên dùng tên mơ hồ như UpdateStatus để che giấu một quyết định quan trọng. Một lệnh **yêu cầu** và một sự kiện **đã xảy ra** không thể hoán đổi.

### 4.1. Tránh đưa mô hình nội bộ ra ngoài

Giả sử Payment dùng enum nội bộ:

    GATEWAY_APPROVAL_PENDING
    PROVIDER_AUTHORIZED_3DS
    SETTLEMENT_QUEUE_WAITING
    CAPTURED
    PROVIDER_RETRY_LATER

Order không nhất thiết cần hiểu chi tiết từng trạng thái của provider. Hợp đồng giữa Order và Payment có thể công bố:

    PENDING
    CAPTURED
    DECLINED
    NEEDS_RECONCILIATION

Payment chuyển nghĩa từ các trạng thái nội bộ sang khái niệm miền đủ cho Order. Nếu nhà cung cấp thay đổi, Payment cập nhật adapter, không bắt buộc Order gánh tất cả kiến thức gateway.

### 4.2. Anti-corruption layer

Khi tích hợp legacy hoặc miền có thuật ngữ khác, một lớp chuyển đổi có thể:
- Đổi dữ liệu bên ngoài sang mô hình nội bộ.
- Ánh xạ trạng thái theo ngữ nghĩa được thống nhất.
- Chuyển đơn vị tiền tệ, múi giờ hoặc định danh.
- Bảo vệ các bất biến tại nơi sở hữu.

Lớp này không nên trở thành chỗ cất mọi quy tắc nghiệp vụ; trách nhiệm của nó là bảo vệ ranh giới mô hình, không nhân đôi quyền quyết định.

## 5. Hợp đồng API đồng bộ: nhiều hơn HTTP method

Một API contract thường cần mô tả tối thiểu:

1. **Operation:** mục đích nghiệp vụ và bên có quyền gọi.
2. **Request:** đường dẫn, phương thức, header, body, kiểu, ràng buộc, ý nghĩa giá trị thiếu.
3. **Response:** status code, body, ý nghĩa từng trạng thái và khi nào kết quả có hiệu lực.
4. **Errors:** phân biệt dữ liệu sai, từ chối nghiệp vụ, xung đột, lỗi tạm thời và kết quả không chắc chắn.
5. **Security:** authentication, authorization theo tenant/resource/scope.
6. **Idempotency:** cùng yêu cầu gửi lại có tạo tác động thứ hai không?
7. **Timing:** timeout, deadline, cách xử lý kết quả tới muộn.
8. **Operational behavior:** rate limit, pagination, sorting, retry hints, mức nhất quán đọc khi có cam kết.
9. **Versioning:** những gì có thể thay đổi và chính sách deprecation.
10. **Observability:** requestId, correlationId, dấu vết phục vụ hỗ trợ người dùng.

### 5.1. Ví dụ command có ngữ nghĩa

~~~http
POST /inventory/reservations
Authorization: Bearer <token>
Idempotency-Key: reserve-order-123
Content-Type: application/json

{
  "orderId": "ord-123",
  "items": [
    {"sku": "SKU-7", "quantity": 2}
  ]
}
~~~

Phản hồi minh họa:

~~~http
HTTP/1.1 201 Created
Location: /inventory/reservations/res-456
Content-Type: application/json

{
  "reservationId": "res-456",
  "orderId": "ord-123",
  "status": "RESERVED",
  "expiresAt": "2026-11-12T10:00:00Z",
  "version": 1
}
~~~

Những điều hợp đồng phải nói rõ:
- RESERVED có nghĩa Inventory đã kiểm tra điều kiện và ghi nhận giữ hàng có hiệu lực theo chính sách.
- Hạn expiresAt được tính theo đồng hồ và quy tắc của Inventory, không do client tự quyết định.
- Cùng Idempotency-Key và cùng payload là một ý định; việc thử lại không tạo thêm lần giữ hàng độc lập trong phạm vi lưu key đã định nghĩa.
- Cùng key nhưng payload khác sẽ bị từ chối hoặc báo conflict theo policy.
- Client không được tự sửa quantity reserved bằng thao tác UPDATE lên bảng Inventory.

Đây là một phương án thiết kế, không bắt buộc mọi API phải dùng mã 201. Nếu lệnh chỉ được ghi nhận để xử lý sau, 202 Accepted và operationId thường phản ánh ngữ nghĩa chính xác hơn.

### 5.2. Mã lỗi cần đủ phân biệt

| Tình huống | Ý nghĩa hợp đồng | Cách consumer nên ứng xử |
|---|---|---|
| 400 hoặc validation error | Request không hợp lệ | Sửa dữ liệu, không retry y nguyên |
| 401/403 | Thiếu xác thực hoặc không có quyền | Xử lý danh tính/quyền, không tự bypass |
| Business rejection | Đã kiểm tra nhưng nghiệp vụ từ chối | Hiển thị lý do hợp lệ, có thể đề xuất lựa chọn khác |
| 409 Conflict | Trạng thái/version hoặc idempotency key xung đột | Đọc lại hoặc xử lý theo quy tắc |
| 429 Too Many Requests | Giới hạn tải | Tôn trọng Retry-After khi được cung cấp, retry có kiểm soát |
| 503 | Tạm không phục vụ | Retry khi an toàn, có backoff và deadline |
| Timeout/connection lost | Không quan sát được kết quả trong thời hạn | Tra trạng thái nếu thao tác có tác dụng phụ |

Không phải mọi từ chối nghiệp vụ đều ánh xạ duy nhất vào một HTTP status chuẩn; cần định nghĩa error code có ý nghĩa nghiệp vụ. Không phơi lỗi SQL hoặc stack trace như một phần contract thông thường.

### 5.3. Hợp đồng đọc phải chỉ rõ độ tươi

GET /orders/{id}/summary có thể đọc từ một projection bất đồng bộ. Khi đó:
- Response có thể không phản ánh ngay lệnh vừa được chấp nhận.
- Có thể công bố sourceVersion, projectionUpdatedAt hoặc quy tắc read-your-writes nếu được hỗ trợ.
- Consumer không được dùng dữ liệu cũ từ summary để duyệt hoàn tiền nếu Payment là nguồn quyết định.

Một query nhanh không mặc nhiên là query đủ mạnh để ra quyết định có bất biến. Hợp đồng cần nói **dữ liệu được phép dùng cho mục đích nào**.

## 6. Hợp đồng thông điệp bất đồng bộ

Thông điệp thường được gửi qua Kafka, RabbitMQ, broker khác hoặc một nền tảng sự kiện. Với giao tiếp bất đồng bộ, bên phát và bên nhận có thể không hoạt động cùng thời điểm. Điều này giảm phụ thuộc thời gian thực nhưng tăng nhu cầu định nghĩa vòng đời và bảo đảm giao nhận.

Phải phân biệt:
- **Command message:** yêu cầu một thành phần thực hiện hành động. Bên nhận có thể chấp nhận hoặc từ chối.
- **Event message:** thông báo một sự thật đã xảy ra dưới quyền quyết định của nguồn phát.
- **Integration event:** biểu diễn sự thật để nhóm ngoài bounded context hiểu và sử dụng, không nhất thiết giống domain event nội bộ.
- **Notification message:** thông tin về một trạng thái/sự kiện, chưa chắc tạo nghĩa vụ nghiệp vụ ở bên nhận.
- **Snapshot/update message:** dữ liệu phục vụ đồng bộ projection, có thể yêu cầu version và quy tắc merge rõ.

### 6.1. Ví dụ event envelope

~~~json
{
  "eventId": "evt-inv-9921",
  "eventType": "InventoryReserved",
  "schemaVersion": 1,
  "aggregateId": "res-456",
  "aggregateVersion": 3,
  "occurredAt": "2026-11-12T09:57:00Z",
  "correlationId": "checkout-123",
  "data": {
    "reservationId": "res-456",
    "orderId": "ord-123",
    "expiresAt": "2026-11-12T10:00:00Z"
  }
}
~~~

Ý nghĩa cần thống nhất:
- Inventory là bên có thẩm quyền xác nhận việc giữ hàng.
- eventId là định danh sự kiện, giúp consumer nhận diện phát lại.
- aggregateId/aggregateVersion hỗ trợ xử lý thứ tự và trạng thái của cùng một đối tượng.
- occurredAt mô tả thời điểm sự kiện được xác định theo nghĩa đã công bố; không nên lấy timestamp của consumer làm bằng chứng thứ tự nghiệp vụ toàn cục.
- correlationId phục vụ trace; không thay thế idempotency key của một command.
- Data là payload hợp đồng, không phải bản sao nguyên bảng nội bộ.

### 6.2. Thông điệp cần hợp đồng chuyển phát

Một schema đúng không trả lời được:
- Broker có thể giao lại cùng message không?
- Thứ tự được bảo đảm trong một partition/key, hay không bảo đảm?
- Consumer có thể nhận version 5 trước version 4 không?
- Message được giữ và replay trong bao lâu?
- Khi schema không đọc được hoặc consumer lỗi, message đi đâu?
- Khi producer gửi thành công rồi crash trước đánh dấu, có khả năng phát lại không?
- Khi consumer apply xong nhưng crash trước ACK, xử lý lại như thế nào?

Nhiều hệ thống ứng dụng dùng **at-least-once delivery**, nên consumer phải thiết kế xử lý trùng. “Exactly-once” của một nền tảng có thể chỉ áp dụng trong phạm vi nhất định; không nên suy rằng nó tự bảo đảm một lời gọi thanh toán bên ngoài chỉ diễn ra một lần.

### 6.3. Quy tắc version và ordering

Giả sử consumer nhận:

    OrderStatusChanged(order=123, version=8, status=PAID)
    OrderStatusChanged(order=123, version=7, status=PENDING)

Nếu cập nhật mù theo thứ tự nhận, projection sẽ lùi trạng thái.

Một giải pháp là version guard khi sự kiện mang trạng thái đầy đủ:

~~~sql
UPDATE order_projection
SET status = :incomingStatus,
    source_version = :incomingVersion
WHERE order_id = :orderId
  AND source_version < :incomingVersion;
~~~

Đối với delta event (ví dụ QuantityAdded +1), không thể luôn bỏ qua version thiếu vì cần toàn bộ chuỗi để tính đúng. Khi đó consumer phải replay, chờ phần thiếu hoặc làm mới từ nguồn có thẩm quyền. Hợp đồng phải cho biết sự kiện là **snapshot** hay **delta**.

### 6.4. Không phát sự kiện trước khi sự thật có hiệu lực

Một producer không nên phát PaymentCaptured rồi mới commit Payment ở datastore và giả định tất cả cùng thành công. Nếu transaction rollback nhưng event đã được tiêu thụ, các nhóm có thể thực hiện hành động dựa trên sự thật chưa bao giờ có hiệu lực.

Một cơ chế thường dùng là **transactional outbox**: thay đổi trạng thái và bản ghi outbox được commit trong cùng transaction cục bộ. Publisher gửi event sau đó; consumer vẫn phải chịu trùng khi publisher retry.

Outbox giúp bảo đảm quan hệ giữa trạng thái nguồn và ý định phát thông điệp, không biến nhiều service thành một transaction ACID chung.

## 7. API contract và message contract khác nhau như thế nào?

| Khía cạnh | API đồng bộ | Thông điệp bất đồng bộ |
|---|---|---|
| Thời điểm tương tác | Caller thường chờ phản hồi trong một deadline | Producer/consumer không nhất thiết đồng thời trực tuyến |
| Kết quả | Response/error được quan sát ngay nếu kết nối thành công | Kết quả có thể đến sau qua event, state query hoặc workflow |
| Phụ thuộc khả dụng | Provider không sẵn sàng có thể làm request thất bại tức thời | Broker và buffer có thể tách thời điểm nhưng không xóa yêu cầu phục hồi |
| Ngữ nghĩa lỗi | HTTP/gRPC status, timeout, retry | ACK, redelivery, DLQ, replay, poison message |
| Thứ tự | Theo từng lời gọi và các bảo đảm cụ thể | Phụ thuộc partition, key và giao thức |
| Versioning | Path/header/media type hoặc mô hình được chọn | Event type, schema version, registry, compatibility rules |
| Dữ liệu lặp | Client retry command | Broker redelivery, replay và producer retry |
| Quan sát | Latency/response status theo request | Lag, backlog, thời gian hội tụ, trạng thái consumer |
| Sai lầm phổ biến | Gọi dây chuyền nhiều tầng và timeout không rõ | Event schema nghèo ngữ nghĩa, consumer không idempotent |

**Không có lựa chọn nào luôn tốt hơn.** API đồng bộ phù hợp khi consumer cần câu trả lời tức thời. Sự kiện phù hợp khi các bên có thể phản ứng sau hoặc cần giảm phụ thuộc availability. Một hệ thống thường dùng cả hai; hợp đồng phải mô tả giới hạn riêng.

## 8. Chọn dữ liệu công bố trong hợp đồng

### 8.1. Chỉ công bố thông tin bên ngoài có quyền phụ thuộc

Nếu Inventory có bảng stock với các cột internal_shard, supplier_priority, reservation_lock_version và warehouse_legacy_key, không nên tự động đưa mọi cột vào StockReserved event. Mỗi trường công bố có thể trở thành một nghĩa vụ tương thích lâu dài.

Hãy xuất bản các giá trị mà consumer cần để thực hiện use case được chấp thuận: reservationId, orderId, trạng thái hiệu lực, hạn giữ, version và thông tin tối thiểu liên quan.

### 8.2. Tránh tham chiếu mơ hồ

Những câu hỏi cần trả lời trong schema:
- Amount dùng đơn vị nhỏ nhất hay số thập phân? Currency được biểu diễn ra sao?
- Thời gian dùng UTC và định dạng cụ thể nào? timezone có ý nghĩa nghiệp vụ không?
- ID có duy nhất toàn cục hay trong phạm vi tenant?
- Trường null khác với vắng mặt như thế nào?
- Đối với collection rỗng, có nghĩa không có mục nào hay dữ liệu chưa được nạp?
- Enum có đóng hay chấp nhận giá trị tương lai?
- Boolean archived biểu diễn xóa mềm hay trạng thái nghiệp vụ khác?

Một thay đổi âm thầm từ amount = 12.50 USD sang amount = 1250 cents có thể phá hủy nghiệp vụ dù vẫn là number ở cả hai phía.

### 8.3. Không gửi dữ liệu nhạy cảm không cần thiết

Thông điệp có thể được nhiều consumer, hệ lưu trữ, dashboard hoặc dịch vụ giám sát truy cập. Chỉ công bố dữ liệu phù hợp mục đích và quyền, xác định thời hạn giữ và chính sách xóa nếu có yêu cầu. Không coi mạng nội bộ hoặc broker riêng là lý do để gửi thông tin thẻ, token bí mật hoặc dữ liệu cá nhân ở mức không cần thiết.

Khi một trường phải được bỏ đi vì an toàn hoặc yêu cầu pháp lý, cần một kế hoạch thay đổi có ưu tiên bảo vệ dữ liệu và đánh giá ảnh hưởng consumer; yêu cầu bảo mật có thể buộc thay đổi phá vỡ hợp đồng và cần quy trình khẩn cấp thích hợp.

## 9. Tính tương thích: thiết kế để hai phiên bản cùng tồn tại

Một hệ microservices không nên giả định tất cả service sẽ deploy cùng một thời điểm. Trong rollout, có thể có:
- Producer phiên bản mới, consumer phiên bản cũ.
- Producer cũ, consumer mới.
- Nhiều replica của provider chạy song song hai phiên bản.
- Message cũ được replay sau khi một consumer đã cập nhật code.
- Mobile client chưa nâng cấp trong nhiều tuần.

Vì vậy cần nói rõ **hướng tương thích**.

### 9.1. Tương thích với dữ liệu cũ và dữ liệu mới

- **Backward compatibility** thường được dùng để nói phiên bản reader mới vẫn đọc được dữ liệu được writer cũ tạo ra; nhưng thuật ngữ có thể được một số công cụ định nghĩa theo ngữ cảnh producer/consumer riêng.
- **Forward compatibility** thường là reader cũ vẫn đọc/hiểu được dữ liệu của writer mới trong phạm vi được hỗ trợ.
- **Full compatibility** hướng tới cả hai chiều theo bộ quy tắc của hệ thống.

Khi sử dụng schema registry, hãy đọc định nghĩa chính xác của chế độ BACKWARD/FORWARD/FULL và phạm vi phiên bản được kiểm tra (với phiên bản gần nhất hay toàn bộ lịch sử). Không dựa vào tên chế độ rồi suy luận về ngữ nghĩa nghiệp vụ.

### 9.2. Những thay đổi thường ít rủi ro hơn

Tùy định dạng và cách parser của consumer:
- Bổ sung một trường thực sự tùy chọn với default rõ.
- Bổ sung endpoint mới song song endpoint cũ.
- Công bố một event type mới, tiếp tục giữ event type cũ trong giai đoạn chuyển tiếp.
- Mở rộng khả năng query mà không đổi ý nghĩa của các query cũ.
- Bổ sung giá trị metadata mà consumer được hợp đồng yêu cầu bỏ qua nếu không biết.

**Không mặc nhiên coi bổ sung field/enum là luôn tương thích.** Một consumer dùng strict JSON parser có thể từ chối unknown field; switch exhaustive có thể lỗi với enum mới; một trường optional ở schema có thể trở thành bắt buộc thực tế ở business flow. Tương thích phải được kiểm chứng theo consumer đang chạy.

### 9.3. Các thay đổi có thể phá vỡ

| Thay đổi | Vì sao nguy hiểm |
|---|---|
| Xóa hoặc đổi tên trường đang dùng | Consumer không đọc được hoặc hiểu sai |
| Đổi type string sang number | Parser và logic có thể hỏng |
| Đổi đơn vị amount | Có thể sai tiền mà không có lỗi schema |
| Đổi nghĩa status | Consumer ra quyết định sai dù response vẫn parse được |
| Thêm enum value khi consumer không hỗ trợ mở rộng | Có thể crash hoặc coi là trạng thái sai |
| Biến một command idempotent thành không idempotent | Retry tạo hiệu ứng trùng |
| Đổi thứ tự sự kiện theo cùng aggregate | Projection có thể sai |
| Đổi định nghĩa sự kiện đã xảy ra | Logic orchestration và analytics có thể đổi nghĩa |
| Đổi từ kết quả sync sang nhận yêu cầu async | Caller có thể hiểu 202 như đã hoàn tất |
| Bỏ endpoint hoặc giảm SLA ngoài thỏa thuận | Consumer không còn đáp ứng SLO |

### 9.4. Schema compatibility khác semantic compatibility

Một message PaymentCaptured thêm field providerRef có thể tương thích về cấu trúc. Nhưng nếu producer bắt đầu phát PaymentCaptured từ lúc chỉ mới authorized (chưa capture), đây là thay đổi phá vỡ ngữ nghĩa quan trọng.

Cần có **kiểm thử hành vi, ví dụ nghiệp vụ và quy tắc giải thích trường**, không chỉ chạy schema validator.

## 10. Phiên bản API: chọn một chiến lược dễ duy trì

Các lựa chọn thường gặp:
- Phiên bản trong URL: /v1/orders, /v2/orders.
- Header hoặc media type versioning.
- Phiên bản trường hoặc loại tài nguyên khi thực sự cần.
- Tiến hóa tương thích không đổi major version cho những chỉnh sửa nhỏ.

Không có chiến lược duy nhất đúng cho mọi tổ chức. Cần chọn một cách rõ ràng, nhất quán, có công cụ hỗ trợ và hướng dẫn người tiêu thụ.

### 10.1. Khi nào nên tạo major version?

Thường khi không thể giữ ngữ nghĩa cũ mà consumer đang phụ thuộc:
- Thay đổi ý nghĩa một operation.
- Bỏ trường/cấu trúc không còn cần nhưng consumer cũ vẫn sử dụng.
- Chuyển đổi mô hình đồng bộ thành bất đồng bộ với hành vi quan sát khác hẳn.
- Chuyển đơn vị, quy tắc authorization hoặc trạng thái theo cách không thể ẩn sau tương thích.

Một major version chỉ có ích khi v1 và v2 có chính sách hỗ trợ, thời hạn chuyển đổi và cách đo consumer sử dụng. Nếu v2 phát hành rồi v1 bị tắt ngay mà không thỏa thuận, các nhóm vẫn bị buộc deploy đồng loạt.

### 10.2. SemVer có giúp gì?

Semantic Versioning là một cách truyền đạt thay đổi **tương thích hay phá vỡ** theo phiên bản. Tuy nhiên SemVer cho thư viện không tự giải quyết compatibility của API runtime hay event được lưu trên broker. Phải nêu phạm vi version: phiên bản schema, artifact client, API endpoint, event type hay behavior contract.

“2.1.0” không nói được dữ liệu lịch sử có replay được, lỗi HTTP có đổi nghĩa hay consumer cũ còn được hỗ trợ tới ngày nào nếu tổ chức không định nghĩa thêm chính sách.

## 11. Phiên bản và schema registry cho thông điệp

Một message ecosystem có thể lưu schema theo subject/event type, kiểm tra compatibility và gắn schema ID/version khi serialize. Các lựa chọn như Avro, Protobuf, JSON Schema có quy tắc evolution khác nhau.

### 11.1. Với JSON

Nếu consumer tự parse JSON tùy ý, cần quy tắc rõ về unknown fields, nullability, optional và enum. Việc thêm trường có thể là thay đổi an toàn với một consumer nhưng lại làm lỗi consumer strict.

### 11.2. Với Protobuf

Protobuf có field numbers giữ vai trò quan trọng trong wire compatibility. Khi bỏ field, cần quản trị số và tên reserved theo quy tắc định dạng để không vô tình tái sử dụng cho nghĩa khác. Thêm trường cũng phải xét default/absence và khả năng business logic diễn giải đúng.

### 11.3. Với Avro

Avro có quy tắc writer/reader schema và default values. Cần kiểm tra đúng chế độ tương thích được sử dụng, đặc biệt khi thêm/xóa field hoặc thay kiểu. Không suy rằng một schema “được đăng ký thành công” là toàn bộ sự kiện đã tương thích ngữ nghĩa.

### 11.4. Ghi rõ message retention và replay

Một consumer mới có thể đọc cả sự kiện đã phát từ sáu tháng trước. Vì vậy việc chỉ kiểm tra consumer mới với producer hiện tại là chưa đủ nếu hệ thống hỗ trợ replay dữ liệu cũ. Cần version compatibility với phạm vi retention/replay được cam kết, hoặc cung cấp upcaster/migration có kiểm soát.

## 12. Quy trình thay đổi hợp đồng: expand, migrate, contract

Một quy trình thực tế cho thay đổi có nguy cơ ảnh hưởng nhiều nhóm:

### Giai đoạn A — Expand

Provider mở rộng khả năng nhưng vẫn giữ đường cũ:
- Bổ sung trường hoặc endpoint mới.
- Trong trường hợp đổi event, có thể phát song song event cũ và mới một thời gian.
- Viết schema/example và mô tả ý nghĩa mới.
- Bổ sung kiểm thử hợp đồng tương thích.
- Đo consumer nào đang sử dụng đường cũ.

### Giai đoạn B — Migrate

Consumer cập nhật dần:
- Chạy consumer mới với dữ liệu cũ và dữ liệu mới.
- Triển khai canary hoặc theo nhóm traffic.
- So sánh kết quả trên trường hợp thực tế.
- Giám sát error, DLQ, lag và thay đổi số liệu nghiệp vụ.
- Thỏa thuận thời điểm consumer chuyển đổi.

### Giai đoạn C — Contract

Chỉ khi đủ điều kiện:
- Chấm dứt phần hợp đồng cũ.
- Gỡ field/endpoint/topic không còn được hỗ trợ.
- Cập nhật catalog, thông báo, runbook và schema registry.
- Lưu bằng chứng consumer đã chuyển theo phạm vi cần thiết.

**Không đảo thứ tự:** xóa field trước rồi yêu cầu consumer sửa trong ngày là biến ranh giới hợp đồng thành phụ thuộc phát hành.

### 12.1. Ví dụ đổi thông tin tên khách hàng

Contract cũ:

~~~json
{"customerId":"cus-123","fullName":"Nguyen Van A"}
~~~

Contract mới muốn tách:
 
~~~json
{
  "customerId": "cus-123",
  "givenName": "A",
  "familyName": "Nguyen Van",
  "fullName": "Nguyen Van A"
}
~~~

Ở giai đoạn expand, giữ fullName trong thời hạn hỗ trợ; các trường mới có nghĩa rõ, xử lý được trường hợp tên quốc tế hoặc cấu trúc không khớp mô hình tách đơn giản. Consumer chuyển sang dữ liệu mới; sau đó mới xem xét bỏ fullName nếu thực sự cần và tương thích đã được thỏa thuận.

**Lưu ý:** Ví dụ chỉ minh họa quy trình contract, không nên mặc định mọi tên đều tách chính xác thành givenName/familyName bằng phép cắt chuỗi đơn giản.

## 13. Consumer-driven contract testing

**Consumer-driven contract test** cho phép bên tiêu thụ diễn đạt những tương tác mình thực sự cần; provider kiểm tra rằng các tương tác đã được chấp nhận vẫn hoạt động. Đây là cách phát hiện thay đổi phá vỡ trước khi deploy.

Một consumer Order có thể yêu cầu:
- ReserveStock với quantity hợp lệ trả reservationId và status.
- Không đủ hàng trả lỗi nghiệp vụ rõ.
- Cùng idempotency key và payload được nhận như cùng intent.
- Các trường bắt buộc của phản hồi vẫn có ngữ nghĩa đúng.
- Nếu có API trạng thái, một reservation có thể được truy vấn bằng ID.

### 13.1. Contract test không phải unit test của provider

Unit test kiểm tra implementation và business rule nội bộ. Contract test kiểm tra **giao diện quan sát được** giữa provider và consumer. Integration test end-to-end kiểm tra cả đường triển khai, môi trường và các phụ thuộc, nhưng thường chậm hơn và khó xác định nguyên nhân.

Các loại test hỗ trợ lẫn nhau:
- Schema validation: cấu trúc đúng.
- Provider/consumer contract: tương tác được hứa vẫn đúng.
- Domain behavior test: quy tắc nghiệp vụ đúng.
- Integration test: hạ tầng, serialization, auth, network hoạt động.
- Resilience test: retry, timeout, redelivery và failover an toàn.

### 13.2. Không khóa cứng tất cả trường không liên quan

Nếu consumer chỉ dùng orderId và status, một test so sánh toàn bộ JSON kể cả metadata thay đổi liên tục dễ tạo phụ thuộc giả. Test nên kiểm tra **những gì consumer cần và provider cam kết**, đồng thời kiểm tra trường còn lại theo quy tắc schema chung.

Tuy vậy không dùng nguyên tắc “chỉ test một phần” để bỏ qua amount/currency/authorization hoặc những trường mang bất biến quan trọng.

### 13.3. Event contract testing

Bên nhận sự kiện nên kiểm tra:
- Event type, schema và required fields.
- ID và version phù hợp.
- Xử lý unknown optional fields.
- Xử lý duplicate và out-of-order.
- Replay event cũ.
- Không dùng dữ liệu chưa công bố.
- Trường nhạy cảm được hạn chế theo hợp đồng.

Consumer-driven contracts có thể kiểm tra schema và phần ngữ nghĩa, nhưng cần thêm integration tests với broker thật khi thứ tự, partition và ACK/redelivery quan trọng.

## 14. Hợp đồng và CI/CD giữa các nhóm

Một pipeline có thể hỗ trợ tự động:
1. Validate OpenAPI/AsyncAPI/schema.
2. Phân tích thay đổi giữa nhánh mới và phiên bản đang được hỗ trợ.
3. Kiểm tra breaking change theo quy tắc định dạng.
4. Chạy provider tests và published consumer contracts.
5. Kiểm tra ví dụ và generated client trong trường hợp dùng code generation.
6. Phát hành artifact hợp đồng có version.
7. Chạy canary, theo dõi lỗi và metric ở production.
8. Chỉ cho phép bỏ contract cũ sau khi đủ điều kiện chuyển đổi.

### 14.1. Generated client có ích nhưng không xóa trách nhiệm ngữ nghĩa

Sinh SDK từ OpenAPI/protobuf giúp tránh lỗi kiểu và giảm boilerplate. Nhưng SDK không tự biết:
- Một timeout ChargePayment có thể đã thu tiền.
- Một field status có thể đến từ read model trễ.
- Một event có thể bị gửi lại.
- Một enum mới có thể cần xử lý chưa biết.
- Một khoản hoàn tiền phải tuân thủ bất biến nghiệp vụ.

SDK nên thể hiện contract đúng và cho consumer tiếp cận trạng thái/lỗi rõ ràng, không che giấu những kết quả chưa xác định bằng cách tự retry không an toàn.

### 14.2. Contract artifact là đầu ra có version

Có thể đặt schema ở repository provider hoặc một catalog chung. Điều quan trọng:
- Provider vẫn có thẩm quyền về hành vi.
- Artifact được version và trace tới release.
- Các consumer có cách truy xuất phiên bản đang hỗ trợ.
- Không sửa lén một artifact đã được công bố như immutable nếu quy trình cam kết tính bất biến của artifact.
- Có lịch sử và thông báo khi thay đổi.

Một repository chung chứa schema không có nghĩa mọi team phải cùng release code; nó chỉ là một cơ chế công bố hợp đồng.

## 15. Quy trình phối hợp nhóm trước khi thay đổi lớn

Đối với thay đổi có ảnh hưởng xuyên nhiều năng lực, một **contract change proposal** nên chứa:

- Tên, owner, hệ thống và mục tiêu nghiệp vụ.
- API/event hiện tại và hành vi đang được cam kết.
- Vấn đề cần giải quyết, lựa chọn thay đổi và lý do.
- Phần tương thích và phần phá vỡ.
- Consumer đã biết và phạm vi có thể còn consumer chưa biết.
- Phương án expand/migrate/contract.
- Mốc thời gian và điều kiện bỏ hỗ trợ.
- Bảo mật, dữ liệu cá nhân và tuân thủ.
- Kế hoạch rollout/rollback cùng dữ liệu lịch sử.
- Các test và metric xác nhận.
- Cơ chế liên hệ khi một consumer không thể nâng cấp kịp.

Review nên tập trung vào **ảnh hưởng hợp đồng**, không đòi nhóm ngoài tham gia mọi quyết định implementation. Sự phối hợp đúng mức là một lợi ích kiến trúc.

### 15.1. RACI nhẹ cho một thay đổi

| Công việc | Provider | Consumer | Platform | Product/domain |
|---|---|---|---|---|
| Giải thích ngữ nghĩa nghiệp vụ | Chịu trách nhiệm trong phạm vi service | Nêu nhu cầu | Hỗ trợ | Cùng quyết định những quy tắc liên miền |
| Thiết kế request/event schema | Chủ trì | Góp ý nhu cầu | Hướng dẫn tiêu chuẩn | Thẩm định tác động miền |
| Đánh giá breaking change | Chủ trì | Xác nhận kỳ vọng | Cung cấp công cụ kiểm tra | Đánh giá rủi ro trải nghiệm |
| Triển khai và rollout | Provider quản lý phía mình | Consumer quản lý phía mình | Hỗ trợ pipeline | Chấp thuận thay đổi sản phẩm nếu cần |
| Theo dõi và xử lý lỗi | Theo dõi contract của provider | Theo dõi tác động consumer | Theo dõi hạ tầng | Xử lý hệ quả nghiệp vụ |

Bảng là ví dụ phân công; tổ chức nên chỉ định người chịu trách nhiệm cuối cùng phù hợp thực tế, tránh một nhiệm vụ có nhiều người “cùng chịu trách nhiệm” mà không ai quyết định.

## 16. Chọn kênh giao tiếp như một phần của hợp đồng

Một API đồng bộ và một event bất đồng bộ có thể cùng mô tả một năng lực, nhưng không nên để consumer tự suy rằng chúng tương đương.

Ví dụ:
- ReserveStock là command cần kết quả chấp nhận hoặc từ chối.
- InventoryReserved là sự kiện nói việc giữ hàng đã có hiệu lực.
- GET /reservations/{id} cho phép truy vấn trạng thái.
- InventoryReservationExpired thông báo một reservation không còn hiệu lực theo chính sách.

Hợp đồng phải giải thích quan hệ thời điểm:
- Sau HTTP 202, sự kiện có thể chưa xuất hiện.
- Sau khi nhận InventoryReserved, consumer có bằng chứng đã giữ hàng ở phiên bản tương ứng.
- Sau khi expiration event đến, phải xem phiên bản và trạng thái để tránh xử lý một sự kiện cũ làm sai trạng thái mới.
- Không dùng việc event đến trễ làm bằng chứng rằng producer chưa xử lý.

### 16.1. Tránh chuỗi synchronous call quá dài

Nếu Order gọi Pricing, Pricing gọi Customer, Customer gọi Loyalty, rồi Loyalty gọi Promotion để trả giá, thay đổi nhỏ ở một bên có thể ảnh hưởng latency và availability của toàn chuỗi.

Một hợp đồng QuotePrice đủ ngữ nghĩa có thể che giấu cách phối hợp nội bộ của Pricing hoặc gom những quy tắc cần một quyết định chung. Không phải mọi phụ thuộc đều nên thay bằng event; quan trọng là xác định ranh giới **ai chịu trách nhiệm trả kết quả** và **hệ quả khi dependency chậm**.

### 16.2. Tránh event như lệnh bí mật

Nếu Event PaymentCaptured yêu cầu Inventory tự giải phóng hàng mà không có điều kiện, có thể xảy ra sai nghiệp vụ. Inventory cần biết rõ một **command** ReleaseReservation với thông tin đủ để quyết định, hoặc một saga được định nghĩa cho việc hủy/hoàn tất.

Không nên gửi event có tên “DoPaymentNow” rồi xem nó là một sự thật đã xảy ra. Hợp đồng phải phân biệt intent và fact.

## 17. Ví dụ xuyên suốt: Order và Payment

Giả sử Order tạo đơn và Payment xử lý giao dịch qua nhà cung cấp bên ngoài.

### 17.1. Hợp đồng command từ Order sang Payment

~~~http
POST /payments/operations
Idempotency-Key: charge-order-123-v1
Content-Type: application/json

{
  "orderId": "ord-123",
  "amountMinor": 500000,
  "currency": "VND"
}
~~~

Phản hồi khi chỉ ghi nhận để xử lý:

~~~http
HTTP/1.1 202 Accepted
Location: /payments/operations/pay-op-777
Content-Type: application/json

{
  "operationId": "pay-op-777",
  "status": "PROCESSING"
}
~~~

Hợp đồng nên quy định:
- Payment mới là nơi quyết định khoản thu được xác nhận theo chính sách.
- Order không được tự đổi trạng thái thành PAID chỉ vì nhận HTTP 202.
- Trả timeout có thể xảy ra sau khi Payment nhận hoặc xử lý request.
- Cùng Idempotency-Key và payload phải được nhận diện là cùng một intent.
- Operation được truy vấn theo ID hoặc một khóa tra cứu được công bố.
- Kết quả cuối cùng có thể CAPTURED, DECLINED hoặc NEEDS_RECONCILIATION; các trạng thái cần nghĩa rõ.

### 17.2. Event từ Payment

~~~json
{
  "eventId": "evt-pay-777",
  "eventType": "PaymentCaptured",
  "schemaVersion": 1,
  "aggregateId": "pay-op-777",
  "aggregateVersion": 5,
  "occurredAt": "2026-11-12T10:02:15Z",
  "data": {
    "operationId": "pay-op-777",
    "orderId": "ord-123",
    "amountMinor": 500000,
    "currency": "VND"
  }
}
~~~

Order có thể nhận event để chuyển state machine của mình. Nhưng phải kiểm tra orderId, paymentAttempt có liên quan, phiên bản và điều kiện nghiệp vụ của Order. Một PaymentCaptured cũ không nên xác nhận lại đơn đã hủy theo chính sách; khi cần có thể mở quy trình hoàn tiền hoặc đối soát.

### 17.3. Hai nhóm có thể release độc lập như thế nào?

Payment có thể đổi provider, thêm retry logic, thay schema nội bộ và cải tiến quan sát mà không sửa contract bên ngoài. Order có thể thay giao diện hoặc thêm trạng thái chờ mà không sửa Payment nếu đang dùng những kết quả được hợp đồng công bố.

Khi Payment cần thêm một event type PaymentRefunded, nhóm Payment phải công bố mục đích, schema, hành vi duplicate/ordering và thời điểm hiệu lực. Order chỉ cần nâng cấp nếu muốn xử lý tính năng mới hoặc nếu chức năng cũ chịu ảnh hưởng đã được thỏa thuận; không buộc mọi consumer nâng cấp để những luồng hiện có tiếp tục hoạt động.

## 18. Kết quả chưa xác định và idempotency là một phần hợp đồng

Trong hệ phân tán, timeout không chứng minh receiver đã thất bại. Ví dụ Order gọi ChargePayment, Payment thu tiền thành công nhưng response bị mất.

Nếu hợp đồng chỉ mô tả hai kết quả success/failure và không có operationId, consumer sẽ khó xử lý đúng. Một hợp đồng nên có:
- Idempotency key ổn định cho cùng intent.
- Điều kiện cùng key/cùng payload.
- Trạng thái PENDING/UNKNOWN khi chưa thể kết luận.
- Cách tra cứu operation và đối soát.
- Chính sách retry an toàn, timeout và số lần thử.
- Hành vi khi operation đã commit nhưng caller không nhận response.

Điều này đặc biệt quan trọng với thanh toán, hoàn tiền, cấp vé, đặt chỗ và những API tạo side effect không thể đảo ngược tức thì.

### 18.1. Không nhầm correlationId với idempotency key

Correlation ID phục vụ truy vết một chuỗi xử lý. Idempotency key nhận diện một **ý định có tác động**. Một retry có thể có trace/span mới nhưng phải giữ cùng idempotency key nếu đó là cùng ý định nghiệp vụ.

### 18.2. Hủy một request khác hủy kết quả đã xảy ra

Client ngừng chờ không có nghĩa Payment có thể rollback provider charge. Nếu khoản thu có hiệu lực, việc đảo ngược có thể cần RefundPayment là một nghiệp vụ khác, có quyền và hợp đồng riêng.

## 19. Hợp đồng vận hành và SLO

Ngoài cấu trúc và ngữ nghĩa, nhóm consumer cần biết những đặc tính vận hành có thể dựa vào:
- Mức availability và mục tiêu latency theo loại operation.
- Rate limit, burst, quota và cách phản hồi khi quá tải.
- Retry-After, error classification và giới hạn retry.
- Độ tươi dữ liệu của endpoint đọc hoặc projection nếu được cam kết.
- Thời gian lưu event, khả năng replay, lag được kỳ vọng và giới hạn hỗ trợ.
- Cách liên hệ, hỗ trợ sự cố và lộ trình deprecation.
- Phạm vi bảo đảm bảo mật và xử lý dữ liệu.

**Phân biệt SLO với bảo đảm tuyệt đối.** Ví dụ “p99 độ trễ API dưới 500 ms” là mục tiêu đo trong điều kiện xác định, không chứng minh mọi request luôn trả dưới 500 ms. Một consumer không nên xây quy tắc nghiệp vụ chỉ dựa vào p99 mà không có phương án timeout.

### 19.1. Timeout và deadline

Nếu Checkout có ngân sách 2 giây, consumer nên truyền thời gian còn lại khi gọi phụ thuộc phù hợp; provider cần có giới hạn tin cậy của mình. Không phải mỗi hop tự cấp thêm hai giây. Khi caller timeout, receiver vẫn có thể tiếp tục side effect; hợp đồng cần nói cách giải quyết trạng thái chưa xác định.

### 19.2. Bulkhead, circuit breaker và fallback

Consumer có thể bảo vệ mình trước phụ thuộc chậm bằng timeout, concurrency limit và circuit breaker. Fallback phù hợp với dữ liệu không quan trọng, ví dụ gợi ý sản phẩm. Không được fallback thành “Payment thành công” hoặc “Inventory đã giữ hàng” khi không có bằng chứng từ chủ sở hữu.

## 20. Công bố và khám phá hợp đồng

Khi số service tăng, khó dựa vào lời truyền miệng hoặc chat. Một catalog hợp đồng có thể ghi:
- Tên service/event, bounded context và owner.
- Mục đích, phiên bản đang hỗ trợ.
- Đường dẫn tới OpenAPI/AsyncAPI/JSON Schema/protobuf.
- Ví dụ request/response và event.
- Những consumer đã đăng ký và nguồn liên hệ.
- SLO, auth, rate limit và chính sách dữ liệu.
- Thông báo breaking changes, thời hạn ngừng hỗ trợ.
- Dashboards, runbooks và môi trường test/sandbox.

Catalog không cần trở thành thủ tục duyệt nặng cho mọi commit. Nó nên là nguồn khám phá đáng tin và tự cập nhật từ pipeline khi có thể.

### 20.1. Ai là consumer?

Một topic có thể có consumer từ nhiều nhóm, kho dữ liệu, job batch hoặc dịch vụ thử nghiệm. Nếu producer không biết ai đang phụ thuộc vào event, thay đổi có thể gây lỗi ngoài dự kiến.

Có thể kết hợp:
- Đăng ký consumer và owner trong catalog.
- Metric subscription/consumer group khi thích hợp.
- Contract test từ consumer.
- Thông báo trên kênh thay đổi chung.
- Chính sách ngừng hỗ trợ công bố sớm.

Không nên tin chỉ số consumer group để kết luận tuyệt đối rằng không có ai sử dụng dữ liệu, đặc biệt khi có kết nối bên ngoài, export hoặc hệ thống đọc lại từ lưu trữ.

## 21. Những lỗi phối hợp liên nhóm phổ biến

**Lỗi 1 — Dùng database chung làm API.** Consumer đọc hoặc sửa bảng của provider nên thay đổi cột buộc nhiều nhóm sửa đồng thời. Giải pháp là API/event với quyền sở hữu rõ và migration theo giai đoạn.

**Lỗi 2 — DTO là entity ORM nội bộ.** Consumer phụ thuộc cách lưu và các field vô tình được serialize. Tách contract DTO khỏi persistence model.

**Lỗi 3 — Thay đổi tương thích chỉ xét JSON parse.** Provider đổi nghĩa status hoặc đơn vị tiền mà schema checker không phát hiện. Bổ sung ví dụ và test hành vi.

**Lỗi 4 — Tạo v2 rồi tắt v1 ngay.** Version mới không giải quyết việc consumer chưa kịp chuyển. Cần thời hạn và kế hoạch chuyển đổi.

**Lỗi 5 — Producer phát cả bảng trong event.** Dễ lộ thông tin nhạy cảm và tạo phụ thuộc vào schema. Công bố tối thiểu theo mục đích.

**Lỗi 6 — Consumer giả định event đúng một lần.** Redelivery và replay gây tác động trùng. Dùng eventId, transaction cục bộ, idempotency và quy tắc version.

**Lỗi 7 — Tạo enum dùng chung cho mọi miền.** Một từ như PAID có thể nghĩa khác ở Payment và Order. Tách ngữ nghĩa theo bounded context, chuyển đổi qua contract.

**Lỗi 8 — Có schema registry nhưng không có owner.** Công cụ kiểm tra định dạng không giải quyết tranh chấp về ý nghĩa hay trách nhiệm lỗi.

**Lỗi 9 — Consumer-driven test khóa cứng mọi field.** Thay đổi metadata không quan trọng bị xem là breaking change. Chỉ kiểm tra những cam kết phù hợp, không bỏ qua bất biến cần thiết.

**Lỗi 10 — API chỉ có SUCCESS/FAILED.** Timeout và tác vụ bất đồng bộ cần PENDING/UNKNOWN hoặc status query; nếu không consumer có thể retry gây tác động trùng.

**Lỗi 11 — Mọi message là event.** Lệnh yêu cầu hành động và thông báo sự thật đã xảy ra bị trộn lẫn, gây hiểu nhầm trách nhiệm.

**Lỗi 12 — Xóa trường trước khi consumer nâng cấp.** Provider buộc các nhóm deploy cùng ngày, mất tính độc lập.

**Lỗi 13 — Không kiểm soát retention và replay.** Consumer mới không đọc được message cũ hoặc gặp schema đã bị xóa. Cần chính sách version theo lịch sử dữ liệu.

**Lỗi 14 — Bỏ qua quyền và phạm vi tenant.** Consumer tưởng dữ liệu trên broker nội bộ là an toàn để dùng mọi nơi. Hợp đồng bảo mật và phân quyền vẫn cần áp dụng.

## 22. Quy trình thiết kế một hợp đồng mới

### Bước 1 — Xác định mục tiêu và consumer

Viết một câu: “Order cần yêu cầu Inventory giữ hàng cho một đơn; Inventory có quyền chấp nhận hoặc từ chối”. Không bắt đầu từ tên bảng.

### Bước 2 — Xác định authority

Ai có quyền ra quyết định? Ai quản lý dữ liệu nguồn? Ai phát sự kiện xác nhận? Nếu các câu trả lời khác nhau, phải giải thích ranh giới và quy trình.

### Bước 3 — Định nghĩa trạng thái và kết quả

Viết rõ thành công, từ chối, xung đột, pending, timeout và outcome unknown. Với event, viết rõ sự thật nào đã xảy ra và khi nào được coi có hiệu lực.

### Bước 4 — Thiết kế dữ liệu tối thiểu

Định nghĩa ID, field bắt buộc/tùy chọn, đơn vị, thời gian, enum, nullability, phiên bản và dữ liệu nhạy cảm. Không lấy entity nội bộ làm contract mặc định.

### Bước 5 — Định nghĩa giao nhận

Với API: auth, idempotency, retry, timeout, rate limit. Với event: eventId, ordering, partition key, delivery semantics, DLQ, replay, retention và cách consumer xử lý trùng.

### Bước 6 — Chọn khả năng tiến hóa

Viết quy tắc tương thích, versioning, thời hạn deprecation và kế hoạch chạy song song. Kiểm tra consumer cũ sẽ làm gì khi provider mới được triển khai.

### Bước 7 — Công bố và kiểm thử

Đưa schema vào catalog, xuất bản ví dụ, chạy provider/consumer contract tests và các integration tests quan trọng; có owner để giải quyết thay đổi.

### Bước 8 — Theo dõi và thay đổi theo bằng chứng

Quan sát lỗi parsing, unknown enum, timeout, lag, DLQ, version adoption và business metrics. Chỉ kết thúc hỗ trợ cũ khi điều kiện chuyển đổi thực sự đạt.

## 23. Bài thực hành: thay đổi Payment API và sự kiện

Một tổ chức có ba nhóm:
- **Order Team:** tạo đơn và hiển thị trạng thái.
- **Payment Team:** quản lý thu tiền/hoàn tiền, thay nhà cung cấp khi cần.
- **Notification Team:** gửi xác nhận giao dịch.

Hợp đồng hiện tại của Payment:

~~~http
POST /v1/payments
{"orderId":"ord-7","amount":250000}
~~~

~~~json
{"paymentId":"pay-7","status":"SUCCESS"}
~~~

Một event cũ:

~~~json
{
  "eventType": "PaymentChanged",
  "orderId": "ord-7",
  "status": "SUCCESS"
}
~~~

Payment Team muốn:
- Đổi amount sang amountMinor và thêm currency.
- Phân biệt AUTHORISED, CAPTURED, DECLINED, PENDING.
- Thay PaymentChanged bằng PaymentCaptured và PaymentDeclined.
- Đổi provider và triển khai độc lập với Order Team.
- Dùng event replay để xây lại read model.

**Yêu cầu:**
1. Liệt kê các điểm mơ hồ trong contract cũ: amount, status, kết quả khi timeout, quyền của provider và thời điểm event phát.
2. Xác định owner của trạng thái thanh toán, trạng thái đơn và hành vi gửi email.
3. Đề xuất hợp đồng API mới có operationId, idempotency key, amountMinor, currency và trạng thái trả lời rõ.
4. Viết event envelope mới với eventId, schemaVersion, aggregateId/version, occurredAt và payload tối thiểu.
5. Phân loại thay đổi nào có thể tương thích, thay đổi nào phá vỡ ngữ nghĩa, dù JSON vẫn parse được.
6. Thiết kế kế hoạch expand–migrate–contract cho Order và Notification đang chạy phiên bản cũ.
7. Nêu cơ chế xử lý PaymentCaptured phát lại hai lần và PaymentDeclined đến trễ.
8. Đề xuất tối thiểu bốn consumer-driven contract tests và hai integration tests với broker.
9. Xác định metric để biết còn consumer v1, event nào bị đưa vào DLQ và lag của projection.
10. Viết thông báo thay đổi gửi các nhóm, bao gồm owner, deadline chuyển đổi và kế hoạch khôi phục nếu rollout lỗi.

### Gợi ý đối chiếu

Payment nên sở hữu hiệu lực giao dịch và công bố kết quả. Order sở hữu vòng đời đơn theo những bằng chứng Payment và Inventory cung cấp. Notification gửi thông báo nhưng không được tự khẳng định giao dịch thành công. Đổi SUCCESS thành CAPTURED là thay đổi **ngữ nghĩa** cần lên kế hoạch rõ. Nếu API mới dùng amountMinor, hợp đồng phải ghi đơn vị và currency, không để consumer hiểu mặc định.

Một chiến lược an toàn là cho v1 và v2 cùng hoạt động trong giai đoạn chuyển đổi, hoặc cung cấp lớp ánh xạ tương thích có giới hạn. Các sự kiện cũ cần được xử lý trong chính sách replay/retention. Payment thay provider ở nội bộ mà không thay giao diện ngoài nếu những cam kết nghiệp vụ vẫn đúng.

## 24. Mẫu ADR và checklist bàn giao hợp đồng

~~~text
ADR: Hợp đồng <API / Event / Command> giữa <Provider> và <Consumer>

Bối cảnh và vấn đề nghiệp vụ:
Provider / domain owner:
Các consumer đã biết:
Command, Query hay Event:
Trạng thái và bất biến được công bố:
Schema, ví dụ và quy tắc trường:
  - ID, thời gian, đơn vị, nullability, enum:
  - Dữ liệu nhạy cảm và chính sách truy cập:
  - Ý nghĩa error / status / outcome unknown:
Đường API hoặc topic/event type:
Auth, tenant, rate limit, timeout, deadline:
Idempotency và retry:
Delivery guarantee, ordering, replay, retention:
Nguồn sự thật, độ tươi dữ liệu và điểm commit:
Versioning và tương thích:
Phương án expand/migrate/contract:
Thời hạn hỗ trợ cũ và cách kiểm tra consumer adoption:
Provider và consumer contract tests:
Integration/resilience tests:
Metric, alert, DLQ và đối soát:
Owner xử lý sự cố:
Các phương án thay thế, rủi ro:
Điều kiện review lại:
~~~

### Các câu hỏi bàn giao

- Consumer có thể mô tả **khi nào** một lệnh có hiệu lực không?
- Có trường nào consumer phải đoán đơn vị hoặc nghĩa không?
- Một timeout có thể được xử lý mà không tạo giao dịch trùng không?
- Event có thể bị gửi lại, đến sai thứ tự hoặc replay không?
- Consumer cũ vẫn chạy được khi provider nâng cấp không?
- Quy trình nào cho phép thay đổi phá vỡ tương thích và ai phê duyệt?
- Có cách nào tìm người sở hữu, phiên bản đang chạy, dashboard và kế hoạch deprecation không?
- Quyền truy cập và dữ liệu công bố có phù hợp mục đích không?

## 25. Kết luận

1. **Hợp đồng là đường biên phối hợp**, không chỉ là URL, topic hoặc file schema.
2. **Provider sở hữu hành vi có thẩm quyền và lời hứa công bố**; consumer chịu trách nhiệm dùng đúng những cam kết đó.
3. **API và event cần ngữ nghĩa nghiệp vụ**, đặc biệt là trạng thái, lỗi, idempotency, thời điểm hiệu lực và quyền ra quyết định.
4. **Schema compatibility chưa đủ**: thay đổi đơn vị, status hoặc ý nghĩa một event có thể phá vỡ nghiệp vụ mà parser không báo lỗi.
5. **Thiết kế để nhiều phiên bản cùng tồn tại** giúp nhóm triển khai độc lập; expand–migrate–contract giảm rủi ro thay đổi đột ngột.
6. **Contract tests, catalog và theo dõi consumer** biến phối hợp liên nhóm thành quy trình có thể kiểm chứng thay vì dựa trên trao đổi miệng.
7. **Thông điệp bất đồng bộ không loại bỏ coupling**, mà chuyển một phần phụ thuộc sang schema, ordering, delivery và khả năng hội tụ.
8. **Một ranh giới tốt cho phép thay cách lưu trữ, provider hoặc hạ tầng bên trong mà không ép nhóm ngoài thay đổi**, miễn các cam kết công khai vẫn được giữ.
