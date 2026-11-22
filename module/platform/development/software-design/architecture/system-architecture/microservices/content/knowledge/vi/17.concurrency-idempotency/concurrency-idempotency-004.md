# Thời hạn lưu khóa và hành vi khi dùng lại khóa với nội dung khác

> **Nguyên tắc:** Idempotency key giúp hệ thống nhận biết nhiều lần gửi của **cùng một ý định nghiệp vụ**, đặc biệt khi client timeout, mất phản hồi hoặc tự động retry. Một thiết kế an toàn phải xác định rõ **khóa có hiệu lực trong phạm vi nào, lưu đến khi nào, yêu cầu nào được coi là tương đương, và xử lý thế nào nếu cùng khóa được gửi với nội dung khác**. Không nên im lặng thực hiện yêu cầu thứ hai hoặc trả thành công cũ cho một payload khác. Đồng thời, **khóa hết hạn không có nghĩa hiệu ứng nghiệp vụ trước đó đã biến mất**.

Bài thuộc nhóm **Đồng thời và lặp an toàn** của kiến trúc microservices. Trọng tâm là idempotency cho command ghi dữ liệu (đặt hàng, thanh toán, giữ hàng, hoàn tiền, tạo job), chính sách TTL/retention, request fingerprint, chống race condition và hành vi API có thể dự đoán được.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt idempotent command, idempotency key, request fingerprint, business operation ID và retry.
2. Giải thích tại sao timeout hoặc mất HTTP response không chứng minh request chưa được xử lý.
3. Thiết kế phạm vi khóa theo tenant, principal, API operation và business intent.
4. Chọn retention window/TTL dựa trên **thời gian retry và khả năng tái xuất hiện request**, không chọn tùy tiện.
5. Phân biệt thời hạn lưu **quyết định chống trùng** với thời hạn giữ chỗ, lease xử lý và retention của dữ liệu nghiệp vụ.
6. Định nghĩa hành vi khi cùng khóa + cùng payload, cùng khóa + payload khác, hoặc cùng khóa trong lúc request đầu còn đang xử lý.
7. Thiết kế atomic claim, kết quả lưu bền, cleanup, xử lý crash, race giữa replica và versioning fingerprint.
8. Triển khai mẫu bằng Java/Spring Boot và cơ sở dữ liệu quan hệ, đồng thời đánh giá Redis khi dùng làm cache/lớp hỗ trợ.
9. Kiểm thử concurrency, TTL boundary, request mismatch, rollback, retry storm và thao tác qua nhà cung cấp bên ngoài.
10. Thiết kế API/UX thông báo trạng thái trung thực và bảo vệ khỏi duplicate business effects.

## 2. Tình huống khởi đầu: client timeout nhưng server đã xử lý

Khách nhấn **Thanh toán**. Ứng dụng gửi lệnh:

~~~http
POST /payments
Idempotency-Key: pay-cart-77-attempt-1
Content-Type: application/json

{
  "orderId": "O-77",
  "amountMinorUnits": 390000,
  "currency": "VND"
}
~~~

Payment Service có thể đã ghi giao dịch thành công, nhưng response bị mất:

~~~text
Mobile client                   Payment Service              Payment DB
      |                               |                          |
      |---- POST /payments ---------->|                          |
      |                               |----- transaction ------->|
      |                               |<----- COMMITTED ---------|
      |                               |                          |
      |        X response lost        |                          |
      |                               |                          |
      |---- retry same request ------>|                          |
      |                               |                          |
      |<--- same operation result ----|                          |
~~~

Nếu server nhận retry như một thanh toán mới, khách có thể bị thu hai lần. Nếu server chỉ kiểm tra “body giống nhau” mà không có khóa/uniqueness nguyên tử, hai request cùng đến đồng thời vẫn có thể lọt qua.

**Điều cần bảo đảm:** Trong cửa sổ đã cam kết, cùng một idempotency key trong cùng scope và cùng ý định phải tham chiếu **cùng một operation**. Retry không được sinh thêm hiệu ứng nghiệp vụ tương tự.

### 2.1. Ba tình huống phải tách bạch

| Tình huống | Ví dụ | Hành vi nên được định nghĩa |
| --- | --- | --- |
| Cùng khóa, cùng ý định/payload hợp lệ | Client retry do timeout | Trả kết quả đã lưu hoặc trạng thái đang xử lý; không thực hiện lệnh lần hai |
| Cùng khóa, nội dung có ý nghĩa khác | Cùng key nhưng amount thay từ 390000 sang 490000 | Từ chối mismatch/conflict; **không** xử lý payload mới bằng key cũ |
| Khóa khác, nội dung giống nhau | Khách gửi hai lệnh thanh toán có key khác | Không thể chỉ nhờ idempotency key biết đây là hai ý định khác nhau hay duplicate; cần thêm invariant/business ID phù hợp |

Không đồng nhất “khóa duy nhất” với “chỉ có một giao dịch cho mỗi order” trừ khi có **business uniqueness constraint** tương ứng. Một Order có thể có nhiều payment attempts hợp lệ theo contract; cũng có khi chỉ cho phép một capture. Quy tắc cần thuộc Payment domain.

## 3. Idempotency chính xác là gì?

Một operation **idempotent** khi gọi lặp cùng ý định không làm tăng thêm hiệu ứng nghiệp vụ sau lần thành công đầu, theo contract đã định.

Ví dụ:
- PUT cập nhật một tài nguyên về cùng trạng thái có thể idempotent ở mức trạng thái tài nguyên, tùy các side effect bổ sung.
- POST /orders bình thường có thể tạo hai đơn nếu gọi hai lần.
- POST /orders với idempotency key và server-side dedup có thể cho **một ý định tạo đơn** được xử lý hiệu quả một lần trong một phạm vi/cửa sổ.
- Một webhook event trùng phải không làm cộng doanh thu hoặc gửi thông báo hai lần ngoài chính sách.

### 3.1. Idempotency key không phải operation ID

**Idempotency key** thường do caller sinh để chứng minh hai request là cùng ý định retry. **Operation ID** do server quản lý để tra cứu trạng thái của công việc đã được tiếp nhận. Có thể ánh xạ key → operationId.

Ví dụ:

~~~json
{
  "operationId": "OP-1001",
  "paymentId": "PAY-1001",
  "status": "PROCESSING"
}
~~~

Client có thể retry bằng idempotency key hoặc tra cứu bằng operationId. Không nên bắt client phải giữ HTTP connection mở để biết kết quả một công việc dài.

### 3.2. Key không chứng minh nội dung giống nhau

Hai request có thể cùng key do bug, copy/paste, tái sử dụng object, retry sau khi user sửa form, hoặc tấn công. Vì thế server thường cần **request fingerprint** gắn vào idempotency record.

### 3.3. Key không tự ngăn trùng khi chưa có atomic enforcement

Mẫu code sai:

~~~java
if (!repository.existsByKey(key)) {
    createPayment();        // Hai request có thể cùng vượt qua check
    repository.save(key);
}
~~~

Đây là check-then-act race. Phải dựa vào cơ chế nguyên tử như unique constraint, INSERT ... ON CONFLICT, Redis SET NX với điều kiện durability phù hợp, hoặc transaction/lock do một owner kiểm soát. Khi có side effect bên ngoài, cần thiết kế riêng vì transaction database không bao phủ nhà cung cấp HTTP.

## 4. Định nghĩa scope của khóa

Khóa không nên được coi là định danh toàn cầu nếu không có chủ đích và thiết kế. Một quy tắc thường dùng là:

~~~text
Dedup identity =
  (tenantId, operationType, idempotencyKey)
~~~

Có hệ thống còn dùng:
- Authenticated principal/accountId.
- MerchantId, payment account hoặc region.
- HTTP method + API route phiên bản hợp đồng.
- Business operation category, ví dụ CREATE_ORDER vs REFUND_PAYMENT.

**Scope phải ổn định qua retry**. Nếu client dùng token khác sau khi refresh nhưng vẫn cùng user/tenant, scope theo raw access token có thể khiến cùng ý định thành khóa mới. Nếu scope theo IP hay session ngắn hạn, NAT hoặc reconnect có thể làm thiết kế sai.

### 4.1. Ví dụ scope tách tenant

~~~text
Tenant A / POST /payments / key=abc -> Payment A-001
Tenant B / POST /payments / key=abc -> Payment B-001
~~~

Hai tenant được phép tình cờ dùng cùng chuỗi key nếu policy định danh theo tenant. Nhưng trong một tenant và operationType, key phải có tính duy nhất trong retention window.

### 4.2. Scope theo operationType

Không nên để idempotency key "abc" của CreateOrder gây collision vô tình với CancelOrder nếu contract quy định key độc lập theo loại command. Ngược lại, không nên đổi operationType tùy hứng giữa các lần retry của **cùng một ý định** khiến duplicate lọt qua.

### 4.3. Business ID là lớp bảo vệ bổ sung

Với Payment, ngoài idempotency key còn có thể cần unique constraint trên một business intent ID, chẳng hạn:
- (merchantId, paymentIntentId) là duy nhất.
- Một capture operation gắn với authorizationId và capture sequence theo policy.
- Một refund gắn với refundRequestId ổn định.

Nếu idempotency record đã hết hạn nhưng client gửi lại command cũ, business uniqueness có thể vẫn ngăn duplicate nguy hiểm. **TTL của dedup cache không được là tuyến phòng thủ duy nhất cho tiền hoặc tài nguyên hiếm.**

## 5. Khi dùng lại khóa với payload khác phải làm gì?

Một contract thực tế nên viết rõ:

> Trong cùng idempotency scope và retention window, một khóa chỉ gắn với một request fingerprint. Nếu cùng khóa được gửi lại với fingerprint khác, server từ chối và không tạo thêm operation mới.

Ví dụ lần đầu:

~~~http
POST /payments
Idempotency-Key: K-123

{"orderId":"O-77","amountMinorUnits":390000,"currency":"VND"}
~~~

Lần hai:

~~~http
POST /payments
Idempotency-Key: K-123

{"orderId":"O-77","amountMinorUnits":490000,"currency":"VND"}
~~~

**Kết quả:** Từ chối do key đã gắn với request khác. Không được thực hiện thanh toán 490000 dưới K-123; cũng không được trả kết quả thanh toán 390000 như thể nó đáp ứng payload mới.

### 5.1. Mã HTTP nên dùng

Tùy hợp đồng, có thể dùng:
- **409 Conflict** cho việc key hiện thuộc operation/request khác, hoặc khi operation đang xử lý không cho gọi cạnh tranh.
- **422 Unprocessable Content** trong một số API khi key đã dùng với các tham số không khớp; cần công bố semantics nhất quán.
- **400 Bad Request** cho key thiếu/format sai theo validation.
- **202 Accepted** khi cùng key/payload đang xử lý và API cung cấp operation status.
- **200 OK / 201 Created** hoặc response đã lưu khi cùng key/payload đã hoàn tất.

Không có một HTTP status duy nhất bắt buộc cho mọi API idempotency. Quan trọng là **định nghĩa rõ, ổn định, dễ phân biệt, có test và không làm lệnh thứ hai phát sinh hiệu ứng**.

Một response mismatch minh họa:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://example.invalid/problems/idempotency-key-reused",
  "title": "Idempotency key already belongs to another request",
  "status": 409,
  "code": "IDEMPOTENCY_KEY_REUSED",
  "detail": "Use a new key only for a genuinely new operation."
}
~~~

Không trả toàn bộ body/PII của request cũ để giải thích cho client khác. Có thể cung cấp operationId/statusUrl đã được phân quyền, nhưng không tiết lộ dữ liệu giữa các tenant/principal.

### 5.2. Mismatch trước khi chạy side effect

Thứ tự quan trọng:
1. Xác thực/ủy quyền request theo chính sách.
2. Xác định scope và tính fingerprint theo quy tắc đã chuẩn hóa.
3. Atomic lookup/claim idempotency record.
4. Nếu cùng key mà fingerprint khác: **reject trước khi thực hiện command**.
5. Nếu cùng key và fingerprint giống: trả kết quả hoặc tiến độ cũ.
6. Nếu key chưa từng có: tạo operation mới theo contract.

Nếu kiểm tra mismatch sau khi gọi payment provider, dedup không còn tác dụng.

### 5.3. User sửa nội dung form sau một lỗi mạng

Giả sử khách nhấn thanh toán 390000, bị timeout, sau đó sửa giỏ thành 490000 và nhấn lại. Đây là **ý định mới**, không phải retry của request trước.

Client cần:
- Giữ K-123 cho retry của chính giao dịch 390000.
- Có khả năng tra trạng thái Payment cũ bằng operation ID.
- Sinh key mới K-124 cho một ý định thanh toán 490000 nếu nghiệp vụ cho phép.
- Không tự động bỏ qua giao dịch 390000 còn chưa rõ kết quả.

Hành vi này cần UX hợp lý; hệ thống không được để người dùng vô tình bị trừ hai khoản do “sửa form và thử lại”.

## 6. Request fingerprint là gì?

Fingerprint là đại diện xác định của **những tham số có ý nghĩa đối với một operation**. Nó giúp server nhận biết một key được retry đúng nội dung hay bị dùng lại cho lệnh khác.

Một cách thường dùng:

~~~text
canonicalPayload = canonicalize(relevant fields)
fingerprint = SHA-256(
  method + "\n" +
  operationType + "\n" +
  apiContractVersion + "\n" +
  canonicalPayload
)
~~~

Dấu phân cách, serialization và algorithm phải được định nghĩa không nhập nhằng. Thực tế có thể dùng cấu trúc length-prefix hoặc serialization có chuẩn thay vì nối chuỗi không kiểm soát. Scope tenant/principal phải được gắn với key lookup; không nên tự do thay đổi scope hoặc cách canonicalize giữa các lần retry.

### 6.1. Payload byte-identical hay semantic-equivalent?

Hai JSON có thứ tự field khác nhau:

~~~json
{"orderId":"O-77","quantity":2}
~~~

~~~json
{"quantity":2,"orderId":"O-77"}
~~~

Về mặt dữ liệu JSON, chúng có thể biểu diễn cùng command. Nếu fingerprint là hash raw request bytes, server sẽ xem chúng khác nhau và từ chối dù ý nghĩa giống.

Có thể canonicalize JSON trước khi hash:
- Chuẩn hóa thứ tự key.
- Chuẩn hóa kiểu số theo contract; không tùy tiện coi 1 và 1.0 là bằng nhau nếu semantics khác.
- Chuẩn hóa string/Unicode chỉ khi đã có quy tắc rõ.
- Phân biệt field omitted, null và empty string theo hành vi domain.
- Đưa header mang business semantics vào fingerprint nếu cần (currency, pricing version, locale nếu ảnh hưởng kết quả).
- Không đưa những header biến đổi theo retry nhưng không ảnh hưởng nghiệp vụ (traceId, user-agent, request timestamp kỹ thuật) vào fingerprint.

Không có thuật toán “canonical JSON” mặc định bảo đảm đúng mọi domain. Quan trọng là **định nghĩa tương đương theo hợp đồng nghiệp vụ**.

### 6.2. Trường nào bắt buộc tính vào fingerprint?

Với CapturePayment:
- paymentIntentId/authorizationId.
- amount và currency theo đơn vị đã thống nhất.
- merchant/tenant scope.
- target account hoặc destination khi ảnh hưởng nghiệp vụ.
- command type và điều kiện quan trọng.

Không nên bỏ qua amount hoặc currency; cùng key nhưng số tiền khác phải bị phát hiện.

Với CreateOrder:
- productId/SKU, quantity và thông tin giao hàng nếu quyết định kết quả.
- accepted quoteId hoặc price commitment.
- customer/merchant scope và contract version.
- không nhất thiết tính display-only metadata nếu không ảnh hưởng ý định, nhưng phải có quy tắc rõ.

### 6.3. Fingerprint version cần được giữ ổn định

Khi code v2 thay cách canonicalize, retry của request v1 có thể tạo fingerprint khác dù business request giống. Idempotency record nên lưu **fingerprint version** và server biết cách tái tính/so sánh theo quy tắc đã dùng lúc claim.

Ví dụ:

~~~json
{
  "fingerprintAlgorithm": "semantic-json-v1-sha256",
  "fingerprint": "hex-digest",
  "operationType": "CAPTURE_PAYMENT"
}
~~~

Không đổi fingerprint logic đồng thời với rolling deployment mà không kiểm tra hai version cùng nhận request. Trong rolling window, v1/v2 phải có hành vi so khớp tương thích.

### 6.4. Hash không phải bằng chứng ủy quyền

SHA-256 chỉ là công cụ nhận diện dữ liệu; nó không xác thực caller. Không dùng fingerprint để cấp quyền xem operation người khác.

Nếu payload chứa PII hoặc số tiền dễ đoán, lưu raw body hoặc hash công khai có thể tạo rủi ro nội bộ tùy threat model. Có thể lưu HMAC với khóa server quản lý để tránh lộ pattern của payload có entropy thấp; vẫn phải bảo vệ secret, rotation và metadata phù hợp. Không đưa dữ liệu nhạy cảm vào logs.

## 7. Thời hạn lưu khóa (TTL/retention) là gì?

**Idempotency retention window** là khoảng thời gian hệ thống cam kết còn nhận diện key đã sử dụng và trả hành vi retry đúng.

Một chính sách ví dụ:

~~~text
Idempotency scope: (merchantId, operationType, key)
Retention: at least 72 hours after operation reaches a terminal state
Same key + same fingerprint: replay stored result/status
Same key + different fingerprint: reject
While PROCESSING: never treat as a fresh operation
After retention: behavior explicitly documented
Business uniqueness: may persist longer than idempotency record
~~~

**72 giờ là con số minh họa, không phải quy tắc chung.** Một sản phẩm có thể chọn 24 giờ, nhiều ngày hoặc lâu hơn, nhưng phải dựa vào thời gian retry, hệ thống bên ngoài, workload và mức thiệt hại nếu xử lý trùng.

### 7.1. Tại sao không chọn 5 phút theo cảm tính?

Retry không chỉ đến từ frontend trong vài giây. Một command có thể xuất hiện lại do:
- Mobile offline rồi kết nối lại sau nhiều giờ.
- Gateway/client SDK retry tự động.
- Message queue redelivery sau service restart.
- DLQ replay theo ca vận hành sau vài ngày.
- Batch job hoặc webhook partner gửi lại sau timeout.
- Hệ thống đối tác có policy retry dài hơn backend.
- Người dùng mở lại app và client gửi pending operation.
- Failover vùng/khu vực và chuyển traffic giữa các replica.
- Rollback deployment khôi phục client/server bản cũ có logic retry khác.

Nếu server hết TTL sau 5 phút nhưng client còn retry sau 2 ngày, cùng key có thể bị coi là mới và tạo side effect trùng.

### 7.2. Cửa sổ retention cần cover những gì?

Một cách lập bảng:

| Nguồn request lặp | Retry/replay window cần điều tra |
| --- | --- |
| Browser/client SDK | Deadline, backoff, resume sau mất mạng |
| Mobile offline queue | Thời gian tối đa có thể giữ lệnh chờ |
| API gateway/proxy | Retry và timeout policy |
| Broker/consumer | Message retention, redelivery, replay và DLQ |
| Background job | Lịch retry, manual re-run, batch cadence |
| External provider | Idempotency policy, webhook retry, trạng thái pending |
| Disaster recovery | RPO/RTO, restore snapshot và lịch sử transaction |
| Business operation | Thời hạn hoàn tất, refund window hoặc reconciliation |
| Client version cũ | Khoảng tồn tại các contract retry khác nhau |

Không lấy một số bất kỳ lớn nhất mà bỏ chi phí; cần thống kê theo workload và hợp đồng. Nhưng nếu rủi ro double-charge cao, **business uniqueness** cần sống đủ lâu ngay cả sau khi xóa response cache.

### 7.3. TTL bắt đầu từ khi nào?

Có hai cách mô hình thường gặp:

**Từ lúc nhận key lần đầu**: expiresAt = firstSeenAt + retention. Đơn giản nhưng nguy hiểm nếu operation mất lâu hơn TTL; key có thể hết hạn trong khi request đầu còn PROCESSING.

**Từ khi operation chuyển terminal state**: expiresAt = completedAt + retention. Thường rõ hơn với operation dài, vì record còn được giữ suốt PROCESSING. Cần quy tắc xử lý operation không bao giờ terminal, không để record kẹt vô hạn mà không có recovery.

Một chính sách mạnh thường tách **processing lease timeout** khỏi **idempotency retention**. Khi worker lease hết hạn, hệ thống không xóa danh tính operation ngay; nó chỉ cho phép recovery/reclaim có kiểm soát.

## 8. Phân biệt bốn loại “hết hạn”

Những thời hạn sau không giống nhau:

| Khái niệm | Có nghĩa gì? | Khi hết hạn |
| --- | --- | --- |
| **Request deadline** | Caller đợi kết quả tối đa bao lâu | Caller ngừng chờ; server có thể đã commit |
| **Processing lease** | Worker nào tạm sở hữu xử lý operation | Recovery có thể chiếm quyền; operation không tự biến thành mới |
| **Business reservation TTL** | Ghế/stock được giữ đến thời điểm nào | Owner phải áp policy EXPIRED/CANCELLED/CONFIRMED |
| **Idempotency retention** | Server còn nhớ key gắn với một request/operation | Sau khi xóa, duplicate prevention có thể suy yếu nếu không có business uniqueness |

Ví dụ:

~~~text
00:00   Payment command accepted
00:02   HTTP deadline expires
00:05   Worker lease expires; recovery begins
00:07   Payment reaches CAPTURED
24:07   Idempotency response retention may expire (illustrative)
Days+   Payment ledger/business intent record still exists
~~~

Không dùng processing lease 5 phút làm TTL xóa key. Một worker thứ hai reclaim lease vẫn phải biết operationId, các step đã làm, và cách tra status ở provider.

### 8.1. Thời hạn giữ chỗ không đồng nghĩa key retention

Inventory hold hết hạn sau 10 phút không có nghĩa ReserveStock command key được quên sau 10 phút. Nếu client retry lệnh ReserveStock cũ sau hold expired, hệ thống cần policy rõ: trả trạng thái EXPIRED của cùng reservation hoặc từ chối retry, không âm thầm tạo một hold mới.

### 8.2. Operation đã thất bại có cần giữ key?

Thường có, ít nhất với **kết quả terminal đã được commit** và có thể tái phát retry. Nhưng cần định nghĩa lỗi nào là terminal và lỗi nào là transient:

- Validation fail trước khi claim: có thể không lưu key tùy contract.
- Business rejection như OUT_OF_STOCK: có thể lưu kết quả gắn với key trong retention để retry ổn định.
- Downstream timeout/unknown: không nên lưu “FAILED” terminal khi chưa biết.
- Server 500 xảy ra trước mọi side effect: policy có thể cho retry cùng operation.
- Server 500 sau side effect: cần giữ/tra operation để tránh duplicate.

Không thể có quy tắc “mọi non-2xx đều không cache” hoặc “mọi 500 đều cache” đúng cho tất cả hệ thống. Hãy định nghĩa theo **điểm commit** và trạng thái nghiệp vụ thực.

## 9. Cùng khóa + cùng request: phản hồi như thế nào?

Khi key, scope và fingerprint giống nhau, hệ thống nên không tạo operation mới. Tuy nhiên cách trả về có thể khác theo trạng thái:

| Trạng thái record | Hành vi retry an toàn |
| --- | --- |
| CLAIMED/PROCESSING | Trả 202 với operationId/statusUrl, hoặc 409/425 theo contract nếu yêu cầu chờ; **không** chạy song song một operation mới |
| COMPLETED_SUCCESS | Trả kết quả đã lưu (status/body/location) hoặc tài nguyên authoritative tương đương theo policy |
| COMPLETED_REJECTED | Trả rejection đã được lưu hoặc business state không đổi |
| UNKNOWN/RECONCILING | Trả trạng thái cần xác minh; không tái thực hiện side effect mù |
| COMPENSATING | Trả trạng thái bù trừ và mã tra cứu |
| EXPIRED_RECORD | Hành vi phụ thuộc hợp đồng sau retention; không hứa dedup mãi mãi |

### 9.1. Replay response có cần giống byte-for-byte?

Có API chọn **lưu và trả lại chính status code/body/headers** của request đầu trong retention. API khác trả **trạng thái hiện tại của operation** hoặc URL resource để client query. Cả hai có thể đúng nếu công bố rõ và không làm lặp hiệu ứng.

Nếu response chứa field động như thời gian hiện tại hoặc signed download URL ngắn hạn, lưu nguyên response nhiều ngày có thể sai. Có thể lưu immutable operation result + trạng thái, rồi dựng response phù hợp contract. Không được thay đổi ý nghĩa “đã thành công” giữa các lần retry.

### 9.2. Replay có cần kiểm tra quyền?

Có. Client retry bằng key giống không có nghĩa được xem dữ liệu của một tenant khác. Xác thực/ủy quyền phải diễn ra trước khi lộ kết quả; tránh lookup key toàn cục khiến một client đoán được response của người khác.

### 9.3. “Same body” khác “same business intent”

Hai body giống nhau nhưng user chủ động muốn mua cùng sản phẩm lần hai có thể là **hai ý định hợp lệ**, và dùng hai key khác nhau. Ngược lại, cùng một key với requestBody thay đổi metadata không có ý nghĩa có thể được coi là tương đương nếu fingerprint contract đã định nghĩa điều đó.

## 10. Sau khi key hết hạn thì sao?

Đây là phần dễ bị bỏ sót nhất. Một record bị cleanup có thể khiến server không còn biết key từng được sử dụng. Nếu cùng key được gửi lại:

~~~text
T0: key K-123 -> payment PAY-123 captured
T1: idempotency record expires and is deleted
T2: client retries K-123 due offline queue
T3: key lookup says NOT_FOUND
~~~

Nếu T3 tự gọi provider với paymentId mới, có nguy cơ double charge. Có ba hướng policy, tùy domain:

**Hướng A — Cửa sổ cam kết hữu hạn:** Sau TTL, API công bố rằng key có thể được coi là mới. Phù hợp với operation ít nguy cơ và client được kiểm soát; **không đủ an toàn** cho những side effect có rủi ro cao nếu không có business uniqueness.

**Hướng B — Lưu business identity dài hạn:** Idempotency response cache có thể hết hạn, nhưng orderId/paymentIntentId với unique constraint vẫn tồn tại. Retry cũ được ánh xạ về operation hiện tại hoặc bị từ chối theo business rule.

**Hướng C — Tombstone/digest kéo dài:** Xóa response body lớn nhưng giữ một record nhỏ (scope, key digest, fingerprint, operationId, terminal status) đủ lâu để phát hiện reuse. Thời hạn tombstone cũng phải được xác định dựa trên rủi ro, không tự coi vĩnh viễn.

### 10.1. Không hứa “retry mãi vẫn an toàn” khi chỉ lưu 24 giờ

Tài liệu API nên nêu rõ retention tối thiểu/cửa sổ hỗ trợ và hành vi sau đó. Client phải hiểu khi nào cần GET trạng thái theo operationId thay vì POST lại. Nếu backend muốn bảo đảm không double-charge lâu dài, cần lớp bất biến ở business domain chứ không chỉ TTL cache.

### 10.2. Không tái sử dụng key cũ cho ý định mới

Ngay cả khi key hết hạn, khuyến nghị client **sinh key mới cho operation mới**. Dùng lại key cũ vì “đã quá 24 giờ” gây nhầm với retry đến muộn và làm log/đối soát khó theo dõi.

### 10.3. Cẩn trọng khi thay TTL

Rút TTL từ 7 ngày xuống 1 ngày có thể làm những client cũ còn retry sau ngày thứ nhất gặp duplicate. Tăng TTL cũng thay chi phí lưu trữ và hành vi tái sử dụng key. Đây là **thay đổi hợp đồng**, cần đánh giá compatibility và rollout, không chỉ đổi một constant.

## 11. Một trạng thái idempotency bền vững nên chứa gì?

Một schema minh họa:

~~~text
IdempotencyRecord
  tenant_id
  operation_type
  idempotency_key_digest
  request_fingerprint
  fingerprint_algorithm
  operation_id
  status = PROCESSING | COMPLETED | REJECTED | RECONCILING
  response_status
  response_location
  response_body_or_result_ref
  first_seen_at
  last_attempt_at
  completed_at
  expires_at
  owner_token
  lease_until
  version
~~~

Không phải mọi field đều bắt buộc. Chọn theo contract và recovery model; không lưu response body/PII nếu chỉ cần resource ID.

### 11.1. Unique constraint là điểm quan trọng

Một database quan hệ có thể dùng:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id           VARCHAR(100) NOT NULL,
    operation_type      VARCHAR(80) NOT NULL,
    key_digest          CHAR(64) NOT NULL,
    fingerprint         CHAR(64) NOT NULL,
    fingerprint_version VARCHAR(40) NOT NULL,
    operation_id        UUID NOT NULL,
    status              VARCHAR(30) NOT NULL,
    first_seen_at       TIMESTAMPTZ NOT NULL,
    completed_at        TIMESTAMPTZ NULL,
    expires_at          TIMESTAMPTZ NULL,
    result_ref          VARCHAR(255) NULL,
    lease_until         TIMESTAMPTZ NULL,
    owner_token         UUID NULL,
    version             BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, operation_type, key_digest),
    UNIQUE (operation_id)
);
~~~

Đây là ví dụ PostgreSQL, không phải migration production hoàn chỉnh. Nếu key bị xóa khi hết hạn, unique constraint không còn ngăn key cũ được claim mới; phải có business uniqueness/tombstone khi yêu cầu.

### 11.2. Tách key raw khỏi key digest

Không nhất thiết lưu raw key ở DB/log. Có thể lưu digest/HMAC theo scope để giảm lộ key. Nhưng phải quản lý algorithm/secret rotation; nếu key digest đổi trong rolling deployment mà không giữ cách tra cũ, retry có thể không tìm thấy record.

**Key là định danh chống trùng, không phải secret xác thực.** Dù client sinh chuỗi ngẫu nhiên khó đoán, vẫn cần authn/authz.

### 11.3. Result reference so với response body

Thay vì lưu JSON dài của response, có thể lưu (operationId, resourceId, status) rồi query nguồn có thẩm quyền. Tùy contract, nếu phải replay đúng response đầu, cần lưu status/body/selected headers an toàn. Không lưu token, thông tin thẻ hay signed URL ngắn hạn trong record nhiều ngày.

## 12. Atomic claim: hai request cùng key đến đồng thời

Giả sử hai replica nhận cùng key gần như cùng lúc:

~~~text
Client A ---- key=K-123 ---> API replica 1
Client B ---- key=K-123 ---> API replica 2
                                  |
                     Shared idempotency store
                                  |
                     Exactly one atomic claim
~~~

Không thể chỉ dùng synchronized trong một JVM, vì hệ thống có nhiều process/pod. Cần điểm đồng bộ chung với tính nguyên tử phù hợp.

Một pattern PostgreSQL:

~~~sql
INSERT INTO idempotency_records (
  tenant_id, operation_type, key_digest,
  fingerprint, fingerprint_version,
  operation_id, status, first_seen_at
) VALUES (
  :tenantId, :operationType, :keyDigest,
  :fingerprint, :fingerprintVersion,
  :operationId, 'PROCESSING', CURRENT_TIMESTAMP
)
ON CONFLICT (tenant_id, operation_type, key_digest)
DO NOTHING;
~~~

Ứng dụng kiểm tra affected rows:
- Nếu 1: request này claim được key và có quyền bắt đầu operation.
- Nếu 0: key đã tồn tại; đọc record và so fingerprint/status.
- Nếu fingerprint khác: reject trước side effect.
- Nếu fingerprint giống và PROCESSING: trả trạng thái hoặc chờ có giới hạn.
- Nếu fingerprint giống và COMPLETED: trả kết quả đã lưu/truy vấn.
  
Không thực hiện side effect sau khi INSERT thất bại chỉ vì “cùng payload”.

### 12.1. Claim và business operation có thể cần cùng transaction

Với một command cục bộ CreateOrder, bạn có thể ghi idempotency record, Order và outbox trong **cùng transaction**:

~~~text
BEGIN
  atomic claim key
  create order with business uniqueness
  insert outbox OrderPlaced
  finalize idempotency result reference
COMMIT
~~~

Nếu rollback, cả key claim và Order rollback theo transaction; client có thể retry hợp lệ. Nhưng đây là pattern **chỉ khi các thao tác thuộc cùng database/transaction manager**.

Nếu muốn trả PROCESSING trước khi xử lý lâu, cần commit một operation record bền rồi chạy worker riêng, không giữ database transaction mở suốt một HTTP call tới provider.

### 12.2. External side effect phải có recovery

Nếu tạo idempotency record PROCESSING ở DB rồi gọi payment provider:
- Provider có thể capture trước khi response mất.
- Process có thể crash trước khi cập nhật record COMPLETED.
- Worker phục hồi phải query provider theo **stable payment operation ID**, không tự capture lần hai với ID mới.

Một record PROCESSING “kẹt” cần workflow recovery, không được tự xóa vì lease hết hạn.

## 13. Phân biệt lock/lease và retention

**Lock/lease** giúp giới hạn ai đang chạy một operation, nhưng không thay idempotency record lưu kết quả.

Ví dụ worker W1 nhận lease đến 10:05, crash lúc 10:03. W2 có thể reclaim sau 10:05 nếu quy tắc cho phép, nhưng phải xử lý:
- W1 đã gửi command tới provider chưa?
- Một side effect đã commit nhưng DB nội bộ chưa biết chưa?
- W1 có thể tỉnh lại và xử lý trễ không?
- W2 có thể tiếp tục mà không tạo operation mới không?

Có thể dùng fencing token/version để không cho worker cũ ghi đè trạng thái sau khi worker mới nhận lease. Tuy nhiên fencing token chỉ hiệu quả ở nơi nhận kiểm tra nó; nhà cung cấp payment bên ngoài có thể không hỗ trợ. Khi đó stable provider idempotency key và reconciliation vẫn cần.

### 13.1. Tránh lease-based ABA

Nếu cleanup record ngay khi lease hết, W1/W2 và một retry khác có thể cùng xem key K-123 “chưa từng tồn tại”, dẫn đến nhiều operation. Lease expiry chỉ nên đổi quyền xử lý, không xóa ý nghĩa của key.

## 14. Dùng Redis hay database quan hệ để lưu khóa?

| Đặc tính | Database quan hệ bền vững | Redis/cache |
| --- | --- | --- |
| Unique claim | Unique constraint/transaction | SET NX/Lua tùy mô hình |
| Durability | Phụ thuộc cấu hình DB/replication | Phụ thuộc persistence, failover, eviction policy |
| Transaction với business row | Có thể chung transaction nếu cùng DB | Không atomic cùng PostgreSQL chỉ nhờ Redis |
| TTL cleanup | Job/partition/retention policy | TTL tự động thuận tiện |
| Query/reconciliation | Thuận lợi theo operationId và trạng thái | Cần lưu tham chiếu/dữ liệu phù hợp |
| Tải rất cao | Cần sizing/index/partition | Có thể hiệu quả, nhưng phải xét failure semantics |
| Mất/evict key | Tùy chính sách xóa | Có nguy cơ nếu eviction/failover làm mất dedup record |

Redis hữu ích làm lớp tối ưu hoặc atomic coordination khi được cấu hình phù hợp, nhưng **không nên là nguồn bảo đảm duy nhất chống double-charge** nếu key có thể mất vì eviction, restore hoặc failover và không có business uniqueness bền vững.

### 14.1. Mẫu Redis SET NX chưa đủ cho payment

~~~text
SET idempotency:{tenant}:{key} PROCESSING NX EX 86400
~~~

Có thể giúp một request claim được key trong 24 giờ, nhưng:
- Client timeout sau side effect.
- Process crash và record chỉ còn PROCESSING.
- TTL hết khi operation còn xử lý.
- Redis evict/failover làm mất key.
- Result chưa được persist atomically với payment transaction.
- Same key + different payload chưa được kiểm tra nếu value không chứa fingerprint.

Vì vậy mẫu SET NX đơn lẻ không giải quyết toàn bộ bài toán.

### 14.2. TTL cleanup của database không miễn phí

Một bảng có hàng triệu idempotency records có thể cần index theo expires_at, background cleanup theo batch hoặc partition theo thời gian. Không DELETE khối lượng quá lớn trong một transaction khiến lock/IO tăng và ảnh hưởng command path.

Nếu retention lâu, cân nhắc lưu tombstone nhỏ hơn result body và giảm dữ liệu nhạy cảm; cần chính sách data retention/erasure phù hợp.

## 15. Java/Spring Boot: mô hình request và response

Ví dụ API tạo một payment intent/operation:

~~~java
package example.payment.api;

import java.util.UUID;

public record CapturePaymentRequest(
        UUID paymentIntentId,
        long amountMinorUnits,
        String currency
) {}

public record PaymentOperationView(
        UUID operationId,
        UUID paymentId,
        String status,
        String statusUrl
) {}
~~~

Với nghiệp vụ tiền tệ, amountMinorUnits và currency phải có contract rõ. Không dùng double để biểu diễn số tiền vì lỗi số thực; long minor units hoặc decimal với scale rõ có thể phù hợp hơn.

### 15.1. Phân loại response

- Request mới và đã tiếp nhận bền: 202 PROCESSING + operationId/statusUrl nếu chưa hoàn tất.
- Request mới và đã hoàn tất tại thời điểm response: 201/200 theo semantics của API.
- Retry cùng key/fingerprint khi PROCESSING: 202 và cùng operationId.
- Retry cùng key/fingerprint đã terminal: response/result đã lưu hoặc resource hiện tại theo contract.
- Retry cùng key nhưng fingerprint khác: 409 hoặc 422 theo contract, code lỗi ổn định.
- Key thiếu/không hợp lệ: validation error nếu API yêu cầu khóa.

### 15.2. Key nên sinh thế nào?

Client nên sinh giá trị có entropy đủ và xác suất va chạm thấp, ví dụ UUID ngẫu nhiên dành cho một business attempt. Đừng dùng timestamp giây, userId hoặc "payment" làm key mặc định; nhiều request thật có thể va chạm.

Đồng thời cần giữ **cùng key** khi retry, ngay cả khi app restart; lưu trong pending operation state cục bộ theo khả năng của client. Không sinh key mới mỗi lần HTTP library retry.

## 16. Java: fingerprint với dữ liệu chuẩn hóa

Ví dụ minh họa tính fingerprint từ các field có ý nghĩa. Tránh hash raw JSON vì thứ tự property có thể khác nhau.

~~~java
package example.payment.idempotency;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;

public final class CaptureFingerprint {
    private CaptureFingerprint() {}

    public static String v1(
            UUID paymentIntentId,
            long amountMinorUnits,
            String currency) {
        // Chỉ minh họa command cố định; input đã được validate.
        // Trong production nên dùng serialization chuẩn, length-prefix,
        // HMAC khi threat model yêu cầu và kiểm soát algorithm version.
        String canonical = "capture-payment-v1\n"
                + paymentIntentId + "\n"
                + amountMinorUnits + "\n"
                + currency.toUpperCase(java.util.Locale.ROOT);

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(canonical.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

Đây là ví dụ hash ba field có kiểu rõ, không phải bộ canonical JSON tổng quát. Khi bổ sung trường quan trọng như destinationAccount hoặc captureMode, phải cập nhật fingerprint contract/version và duy trì tương thích với key đã được claim trong rolling window.

### 16.1. Đừng bỏ trường quan trọng khỏi fingerprint

Nếu chỉ hash paymentIntentId mà không hash amount/currency, cùng key + số tiền khác có thể được coi là cùng request. Đây là lỗi business nghiêm trọng.

### 16.2. Không hash các trường kỹ thuật không ổn định

TraceId hoặc retryAttemptCount khác nhau giữa các lần gửi; đưa chúng vào fingerprint sẽ khiến retry hợp lệ bị từ chối. Phân biệt identity nghiệp vụ và metadata của lần vận chuyển request.

## 17. Java/Spring Boot: service phân loại reuse

Một interface repository mô tả atomic claim:

~~~java
package example.payment.idempotency;

import java.util.Optional;
import java.util.UUID;

public interface IdempotencyRepository {
    // Trả true nếu INSERT unique thành công.
    boolean tryClaim(
            String tenantId,
            String operationType,
            String keyDigest,
            String fingerprint,
            String fingerprintVersion,
            UUID operationId);

    Optional<IdempotencyRecord> find(
            String tenantId,
            String operationType,
            String keyDigest);
}

public record IdempotencyRecord(
        String fingerprint,
        String fingerprintVersion,
        UUID operationId,
        String status,
        String resultRef
) {}
~~~

Decision enum:

~~~java
package example.payment.idempotency;

public enum IdempotencyDecision {
    NEW_OPERATION,
    SAME_OPERATION_IN_PROGRESS,
    SAME_OPERATION_COMPLETED,
    KEY_REUSED_WITH_DIFFERENT_REQUEST
}
~~~

Service khái niệm:

~~~java
package example.payment.idempotency;

import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class IdempotencyService {
    private final IdempotencyRepository repository;

    public IdempotencyService(IdempotencyRepository repository) {
        this.repository = repository;
    }

    public IdempotencyDecision classify(
            String tenantId,
            String operationType,
            String keyDigest,
            String fingerprint,
            UUID newOperationId) {

        boolean created = repository.tryClaim(
                tenantId,
                operationType,
                keyDigest,
                fingerprint,
                "capture-v1",
                newOperationId);

        if (created) {
            return IdempotencyDecision.NEW_OPERATION;
        }

        var existing = repository.find(
                tenantId, operationType, keyDigest).orElseThrow();

        if (!existing.fingerprint().equals(fingerprint)) {
            return IdempotencyDecision.KEY_REUSED_WITH_DIFFERENT_REQUEST;
        }

        if ("COMPLETED".equals(existing.status())) {
            return IdempotencyDecision.SAME_OPERATION_COMPLETED;
        }

        return IdempotencyDecision.SAME_OPERATION_IN_PROGRESS;
    }
}
~~~

Mẫu này minh họa logic phân loại. Trong production, cần trả cả existing operationId/resultRef, xử lý race của cleanup, transaction và concurrent update, algorithm version, authn/authz, các trạng thái RECONCILING/REJECTED và error handling.

Đặc biệt, **không tự bắt đầu payment external trong transaction chỉ vì classify trả NEW_OPERATION** nếu chưa có durable operation command/outbox bảo vệ khoảng lỗi giữa claim và gọi provider.

### 17.1. Atomic claim có cần cùng transaction với command?

Với CreateOrder thuần nội bộ, có thể claim key + insert Order + outbox trong một transaction. Nếu transaction rollback, key claim cũng rollback, client retry có thể chạy lại an toàn.

Với Payment qua HTTP external, cần operation record bền, stable provider idempotency key và recovery/query status. Không có transaction Java cục bộ nào rollback được side effect của provider.

### 17.2. Khi result đã có

Không chỉ trả IdempotencyDecision.SAME_OPERATION_COMPLETED mà bỏ qua nội dung; cần dùng operationId/resultRef từ record được bảo vệ để trả đúng kết quả hoặc status URL. Không để client đổi thông tin người dùng rồi đọc response thuộc tenant khác.

## 18. API error contract minh họa

Một enum lỗi ổn định giúp client xử lý đúng:

| Code ứng dụng | Điều kiện | Client nên làm gì? |
| --- | --- | --- |
| IDEMPOTENCY_KEY_REQUIRED | Endpoint yêu cầu key nhưng không có | Sinh key mới cho một ý định mới, không tự gửi lệnh khác |
| IDEMPOTENCY_KEY_INVALID | Key sai format/độ dài | Sửa input theo contract |
| IDEMPOTENCY_KEY_REUSED | Cùng scope/key nhưng fingerprint khác | Không retry cùng key cho payload mới; tra operation cũ nếu outcome chưa rõ |
| OPERATION_PROCESSING | Cùng key/payload còn xử lý | GET statusUrl hoặc retry có kiểm soát bằng cùng key |
| OPERATION_RECONCILING | Side effect chưa xác nhận được | Chờ/tra cứu trạng thái, không tự nhân bản command |
| OPERATION_COMPLETED | Kết quả đã lưu | Hiển thị kết quả; không tạo operation mới |
| IDEMPOTENCY_WINDOW_EXPIRED | Server biết operation nằm ngoài cửa sổ hoặc tombstone | Theo contract; ưu tiên tra business resource, không tự POST lại payment |
| BUSINESS_DUPLICATE | Business intent đã tồn tại dù key khác | Dùng ID của resource hiện có hoặc xử lý conflict nghiệp vụ |

Không phải endpoint nào cũng cần toàn bộ mã; mục tiêu là phân biệt nguyên nhân và hướng tiếp theo của client.

### 18.1. Response khi đang xử lý

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /payment-operations/OP-123

{
  "operationId": "OP-123",
  "status": "PROCESSING",
  "statusUrl": "/payment-operations/OP-123"
}
~~~

### 18.2. Response khi reuse mismatch

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "status": 409,
  "code": "IDEMPOTENCY_KEY_REUSED",
  "title": "The key has already been used for another request",
  "detail": "Check the previous operation, then use a new key for a new intent."
}
~~~

Không trả 200 với result cũ cho một payload khác. Điều đó có thể khiến client tin rằng amount mới đã được xử lý trong khi thực tế amount cũ mới được xử lý.

## 19. Chính sách lưu key phải xét cả yêu cầu đang PROCESSING

Một cleanup job chỉ kiểm tra expiresAt < now mà không xét status có thể xóa key của job còn chạy.

Cách xử lý tốt hơn:
- Record PROCESSING có cơ chế lease/timeout/reconciliation riêng.
- TTL retention của kết quả terminal bắt đầu theo quy tắc rõ.
- Record stuck quá hạn được đánh dấu NEEDS_RECOVERY, không tự coi là NEW.
- Lịch cleanup kiểm tra state và điều kiện business uniqueness.
- Nếu phải lưu rất lâu, rút gọn record thành tombstone/immutable operation ID.
- Việc xóa phải có audit trail/metrics ở mức phù hợp.

Ví dụ pseudocode:

~~~text
for each idempotency record:
    if status is PROCESSING and lease expired:
        schedule reconciliation/recovery
        do not delete business identity

    else if status is TERMINAL
         and expiresAt < now
         and all retention conditions satisfied:
        delete large response payload
        optionally keep durable tombstone/business uniqueness
~~~

Tránh một vòng cleanup xóa cả keys xử lý lâu, khiến retry tạo payment mới. Chỉ sử dụng dấu thời gian từ nguồn có thể tin cậy; clock skew giữa node có thể ảnh hưởng lease/TTL nếu không tính toán.

## 20. Chi phí retention và cách tính cửa sổ phù hợp

### 20.1. Không lấy “thời gian request HTTP” làm retention

HTTP timeout 30 giây không có nghĩa retry chỉ xuất hiện 30 giây. Một mobile app có thể offline vài ngày rồi gửi lại. Broker có thể replay sau incident. Retention phải dựa vào **khả năng xuất hiện lại ý định cũ**, không phải một timeout duy nhất.

### 20.2. Lập bảng kiểm kê nguồn retry

Ví dụ giả định:

~~~text
Frontend SDK automatic retry:     2 minutes
Mobile pending queue:             48 hours
Gateway retry:                    1 minute
Worker/DLQ replay policy:          7 days
Business payment reconciliation:  30 days
External provider idempotency:    provider-specific
~~~

Đây là các giá trị **minh họa**, không phải thực tế của một hệ thống hay chuẩn API nào. Nếu có replay đến 7 ngày, xóa key sau 24 giờ có thể chưa đáp ứng. Nếu payment reconciliation kéo dài 30 ngày, business intent identity hoặc tombstone có thể cần lâu hơn dù response cache chỉ giữ một thời gian ngắn.

### 20.3. Tách full response retention và dedup retention

Một kiến trúc có thể:
- Lưu response payload lớn trong 3 ngày.
- Giữ key/fingerprint/operationId tombstone trong 30 ngày.
- Giữ payment business intent/ledger record theo chính sách dữ liệu và pháp lý riêng.

Các mốc chỉ để minh họa. Quy tắc này giảm chi phí lưu body trong khi duy trì khả năng chống trùng lâu hơn, nhưng không thay quy định retention và deletion của dữ liệu cá nhân.

### 20.4. Ước lượng dung lượng

Giả sử 500.000 operation/ngày, mỗi idempotency record trung bình 1 KiB (giả định chưa gồm index/replica):

~~~text
Raw data per day ~ 500,000 KiB ~ 488 MiB
Raw data in 7 days ~ 3.34 GiB
Raw data in 30 days ~ 14.3 GiB
~~~

Số liệu chỉ là phép tính gần đúng để thấy chi phí tăng theo số operation và retention. Production còn có index, WAL, vacuum/compaction, replication, backup và log. Không chọn TTL chỉ vì bảng quá lớn; có thể tối ưu schema/tombstone/partition và đánh giá rủi ro nghiệp vụ.

## 21. Chính sách reuse sau TTL trong các loại nghiệp vụ

### 21.1. Payment Capture

Rủi ro double-charge cao. Cần stable paymentIntentId/operationId, provider idempotency theo khả năng, unique business constraints và reconciliation. Khi key cache hết hạn, vẫn cần kiểm tra đã capture intent đó chưa trước khi thu tiếp. Không dùng key TTL làm bảo đảm duy nhất.

### 21.2. CreateOrder

Nếu user chủ động đặt hai đơn giống nhau, có thể là hai giao dịch hợp lệ. Dùng key theo từng intent, giữ qua retry. Nếu key hết hạn, có thể dựa vào order creation intent ID hoặc business reference để tránh retry muộn tạo đơn thứ hai; cần contract rõ với client.

### 21.3. ReserveStock

Reservation có thể hết hạn sau vài phút nhưng command idempotency nên phản hồi trạng thái reservation cũ, không tạo hold mới cho retry của lệnh cũ. Nếu muốn giữ chỗ lại sau khi hết hạn, đó là **command mới** với ID mới.

### 21.4. Refund

Refund có thể mất nhiều ngày để hoàn tất tại đối tác. Hệ thống cần refundRequestId và idempotency chống tạo hai lệnh hoàn tiền. Retry timeout không được tạo refund thứ hai. Business ledger/history thường có vòng đời khác TTL response cache.

### 21.5. Tạo báo cáo nền

POST /reports có thể trả 202 và jobId. Cùng key trong retention trả jobId cũ. Nếu người dùng muốn chạy lại cùng bộ lọc cho dữ liệu mới, đó là **ý định mới** với key mới; không dùng lại key cũ để kỳ vọng job mới.

### 21.6. Gửi email/thông báo

Nếu event OrderConfirmed được redeliver, consumer nên dedup theo eventId/business notification ID, không gửi email trùng vô hạn. Nhưng có tình huống người dùng yêu cầu “gửi lại email xác nhận”, đó là command mới có quyền truy cập và ID mới, không phải retry của event gốc.

## 22. Idempotency ở HTTP khác dedup event ở broker

Có hai lớp thường đi cùng nhau:

**HTTP command idempotency:**

~~~text
Client retries POST /orders with K-123
    |
    v
Ordering idempotency record
    |
    v
One Order operation
~~~

**Event consumer idempotency:**

~~~text
OrderCreated event E-456 is delivered twice
    |
    v
Notification processed_events(E-456)
    |
    v
One notification effect per policy
~~~

Idempotency key của HTTP và eventId có thể khác nhau, vì chúng định danh **khác đơn vị xử lý**. Không dùng một khóa duy nhất tùy tiện cho mọi tầng nếu lifecycle và scope khác nhau.

### 22.1. At-least-once không phải lỗi

Broker có thể giao lại event sau khi consumer commit nhưng mất ACK. Consumer phải có unique processed event record, transaction local hoặc business uniqueness phù hợp. Không suy ra “exactly once toàn hệ thống” chỉ vì broker có tính năng delivery nhất định.

### 22.2. Outbox và dedup

Transactional outbox giúp ghi ý định phát event cùng transaction business row. Publisher có thể phát lại nên consumer cần idempotency. Outbox không thay API idempotency của lệnh được client gửi vào.

## 23. Multi-region và failover: cùng key có thể được claim hai nơi

Giả sử API có active-active ở hai vùng, record idempotency chỉ replicate bất đồng bộ:

~~~text
Client sends K-123 to Region A -> A sees NOT_FOUND -> claim
Client retries K-123 to Region B -> B sees NOT_FOUND -> claim
Replication later reveals both operations
~~~

Nếu cả hai có thể tạo payment mới, duplicate đã xảy ra trước khi dữ liệu hội tụ.

Các lựa chọn:
- Định tuyến một business intent về một single writer/partition owner ổn định.
- Sử dụng unique claim store có mô hình consistency đủ mạnh giữa các vùng.
- Dùng provider/business operation ID có uniqueness ở nơi thực thi side effect.
- Có reconciliation khi failover hoặc split brain.
- Đưa thời gian RPO/RTO và replication lag vào phân tích duplicate risk.

**Một cache key ở hai Redis cluster độc lập không tự tạo globally consistent idempotency.** Cần xác định ranh giới bảo đảm và failure mode.

### 23.1. Rollback code có thể thay fingerprint logic

Khi rollback từ v2 về v1, nếu v1 không hiểu fingerprintVersion của record do v2 tạo, retry có thể bị từ chối sai hoặc tệ hơn, được coi như request mới. Cần giữ compatibility của canonicalization, response representation và key lookup qua rolling window.

## 24. Bảo mật và chống lạm dụng

Idempotency key có thể bị khai thác để chiếm dung lượng record hoặc đoán thông tin operation nếu thiết kế kém.

Một số biện pháp:
- Xác thực và phân quyền trước khi cho xem/replay operation result.
- Scope key theo tenant/operation phù hợp.
- Giới hạn độ dài và charset key, từ chối input bất thường.
- Rate limit việc claim key mới theo account/tenant.
- Giới hạn số PROCESSING records và theo dõi stuck operations.
- Không log toàn bộ raw request body hoặc thông tin thẻ.
- Không dùng key làm bearer token để đọc payment của người khác.
- Nếu giữ digest/HMAC, quản lý secret rotation và threat model.
- Có giới hạn retention và quy trình xóa dữ liệu phù hợp.
- Mismatch error không được tiết lộ fingerprint/raw payload cũ.
- Theo dõi tỷ lệ mismatch cao để phát hiện bug client hoặc hành vi bất thường.

### 24.1. Key collisions và key predictability

Client nên dùng key đủ ngẫu nhiên (ví dụ UUID v4 hoặc chuỗi ngẫu nhiên có entropy tương đương). Không tạo key bằng "userId + currentSecond" cho giao dịch có thể xảy ra nhiều lần trong cùng giây.

### 24.2. Quên key sau khi user logout?

Logout không nhất thiết xóa business operation đã bắt đầu. Một thanh toán có thể tiếp tục sau khi browser logout. Client có thể không còn quyền tra do auth thay đổi, nhưng server phải giữ record và workflow theo business policy. Không xóa idempotency record chỉ vì phiên đăng nhập hết hạn.

## 25. Khác biệt giữa idempotency và tính duy nhất nghiệp vụ

Giả sử cùng một người dùng gửi hai request:

~~~text
Request 1:
  key=K-A
  paymentIntentId=P-100
  amount=390000

Request 2:
  key=K-B
  paymentIntentId=P-100
  amount=390000
~~~

Hai key khác nhau nên tầng dedup theo key **không tự nhận biết** hai request là cùng payment intent. Payment domain cần unique constraint hoặc trạng thái capture theo paymentIntentId để chống duplicate trái quy tắc.

Ngược lại:

~~~text
Request 1:
  key=K-A
  orderTemplate=T-1

Request 2:
  key=K-B
  orderTemplate=T-1
~~~

Hai đơn giống nhau về nội dung có thể là hai ý định đặt hàng độc lập và hợp lệ. Không chống trùng bằng cách hash toàn bộ body rồi cấm mọi request cùng body, nếu nghiệp vụ cho phép mua cùng sản phẩm hai lần.

**Idempotency key mô tả retry của một ý định; business uniqueness mô tả điều gì được phép tồn tại trong miền nghiệp vụ.**

## 26. Testing: ma trận hành vi cần có

| Test case | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| First request | Key chưa có | Claim được đúng một operation |
| Same key, same payload | Retry sau thành công | Cùng result/operation; không thêm side effect |
| Same key, different amount | Retry thay tiền | Reject mismatch; không charge mới |
| Same key, different currency | Retry thay currency | Reject mismatch dù amount giữ nguyên |
| Same key while PROCESSING | Concurrent retry | Không tạo operation thứ hai; trả tiến độ theo contract |
| Same key from two pods simultaneously | Race | Unique claim chỉ một winner |
| Different key, same business intent | Hai request có key khác | Business uniqueness ngăn duplicate nếu invariant yêu cầu |
| Same key, different tenant | Scope tách theo tenant | Không tiết lộ hoặc cross-contaminate results |
| Same JSON fields, different order | Canonicalization | Được coi equivalent nếu contract quy định |
| Omitted field vs null | Semantics phụ thuộc contract | Fingerprint đúng điều kiện nghiệp vụ |
| Retry after HTTP timeout | Server đã commit | Trả state/result cũ, không thực hiện lại |
| Worker crash after external side effect | Internal record PROCESSING | Reconcile với provider bằng stable ID |
| Lease expired | Worker khác reclaim | Không xóa idempotency identity |
| Key expiration boundary | TTL sát thời điểm cleanup | Không tạo race làm duplicate khi operation còn active |
| Retry beyond retention | Key record có thể hết | Hành vi đúng contract + business uniqueness |
| Rolling deploy changes fingerprint | v1/v2 cùng chạy | Retry không bị phân loại sai |
| DLQ replay after days | Message cũ được phát lại | Consumer dedup/reconciliation theo retention |
| Storage failover | Redis/DB failover | Không silently tạo operation mới nguy hiểm |
| Response contains expired URL | Retry ngày hôm sau | Contract cung cấp result/status hợp lệ |
| Cache eviction | Record bị loại sớm | Giữ bảo đảm bằng durable store hoặc phát hiện vi phạm |

### 26.1. Kiểm thử đồng thời thật

Không chỉ viết một unit test gọi tuần tự. Dùng nhiều request song song cùng scope/key vào các replica khác nhau và xác nhận:
- Chỉ một lệnh nghiệp vụ được commit.
- Tất cả retry cùng payload tham chiếu cùng operationId.
- Mismatch luôn bị từ chối trước side effect.
- Không có race giữa lookup, claim, finalize và cleanup.

### 26.2. Kiểm thử fault injection

Giả lập:
- Database commit thành công nhưng HTTP response mất.
- Provider capture thành công rồi connection timeout.
- Process chết giữa claim và outbox publish.
- Consumer xử lý xong nhưng ACK bị mất.
- Clock skew giữa node.
- Failover active-active hoặc restore snapshot cũ.
- Cleanup chạy cùng lúc client retry.

Mục tiêu là phát hiện **khoảng lỗi** mà happy-path test không nhìn thấy.

## 27. Quan sát production và cảnh báo

Các metrics nên có:
- Số key claim mới theo operation type.
- Tỷ lệ retry cùng key/fingerprint.
- Tỷ lệ key reuse mismatch.
- Số record PROCESSING quá tuổi.
- Thời gian hoàn tất operation p50/p95/p99.
- Tỷ lệ RECONCILING/UNKNOWN, compensation và manual review.
- Tỷ lệ request sau retention window.
- Duplicate business attempts bị unique constraint chặn.
- Cleanup rate, số record expired, storage footprint.
- Failures của idempotency store và fallback behavior.
- Provider status mismatch / reconciliation backlog.

Không đưa raw idempotency key hoặc payload chứa PII vào metric labels, vì cardinality cực cao và nguy cơ rò rỉ. Có thể dùng operationId/traceId trong logs được bảo vệ theo policy, và lưu các thống kê tổng hợp.

### 27.1. Cảnh báo sai lệch quan trọng hơn metrics HTTP

Một hệ thống có 0 HTTP 500 vẫn có thể double-charge nếu client đổi key sau timeout. Cần đối soát Payment ledger/intent và số side effects theo business IDs, không chỉ quan sát mã HTTP.

### 27.2. Phân biệt lỗi mismatch và lỗi hạ tầng

Mismatched key có thể là bug phía client hoặc một hành vi không hợp lệ theo contract. Không retry tự động 409/422 như thể server bị lỗi tạm thời; điều đó chỉ tăng tải và không sửa payload.

## 28. Quy trình thiết kế một API idempotent

### Bước 1 — Xác định đơn vị ý định

Một key đại diện cho **một ý định** tạo order, capture payment, refund hay job? Có trường hợp một order có nhiều payment attempts hợp lệ không? Business ID nào duy nhất?

### Bước 2 — Chọn scope ổn định

Dùng tenant/merchant, operationType, authenticated business principal theo policy. Đảm bảo retry sau token refresh hoặc app restart vẫn tìm đúng record.

### Bước 3 — Định nghĩa request fingerprint

Chọn những field ảnh hưởng business outcome. Canonicalize nhất quán, quản lý version và không bỏ qua field quan trọng. Test omitted/null/enum/amount/currency.

### Bước 4 — Định nghĩa ba nhóm reuse

- Same key + same fingerprint.
- Same key + different fingerprint.
- Different key + same/related business intent.

Ghi response/status code và side-effect semantics của từng nhóm.

### Bước 5 — Chọn retention dựa trên retry/replay window

Khảo sát client offline, gateway, worker, DLQ, provider, rollback/failover và business lifecycle. Quy định TTL terminal, processing recovery và tombstone/business uniqueness nếu cần.

### Bước 6 — Chọn điểm lưu bền và atomic claim

DB unique constraint/transaction, Redis phối hợp durability hoặc một single-writer model phù hợp. Bảo vệ race giữa nhiều pod và cleanup.

### Bước 7 — Thiết kế hành vi khi crash

Có thể xảy ra crash trước/giữa/sau side effect. Dùng outbox, stable provider operation ID, status lookup, reconciliation và recovery durable; không xóa khóa đang xử lý khi lease hết.

### Bước 8 — Định nghĩa UX

API trả operationId/statusUrl, trạng thái PROCESSING/COMPLETED/UNKNOWN, thông báo mismatch rõ, không khuyến khích tạo key mới khi kết quả cũ chưa rõ.

### Bước 9 — Test kỹ thuật và business invariants

Đo concurrency, retry window, failover, fingerprint migration, unique constraints và bất biến “một capture mỗi payment intent” theo policy.

### Bước 10 — Theo dõi sau triển khai

Monitor mismatches, stale processing, reconciliation, cleanup, duplicate business attempts và feedback người dùng. Khi đổi TTL/fingerprint, coi là thay đổi hợp đồng cần rollout an toàn.

## 29. Những lỗi phổ biến

**“TTL 24 giờ là chuẩn cho mọi API.”** Không. Retention phải dựa trên retry/replay và nguy cơ business; 24 giờ chỉ có thể là policy của một sản phẩm cụ thể.

**“Hết TTL tức là chưa từng xử lý.”** Sai. Resource, payment hoặc hold có thể vẫn tồn tại lâu hơn rất nhiều.

**“Khi lease hết thì xóa key và xử lý lại.”** Sai. Lease chỉ quyết định worker ownership, không xóa business operation.

**“Cùng key luôn trả kết quả cũ, dù body đổi.”** Sai. Cần mismatch rejection để client không tin rằng payload mới đã được thực hiện.

**“Cùng body phải luôn cho cùng kết quả.”** Sai. Hai key khác nhau có thể đại diện hai ý định mua hợp lệ.

**“Hash raw JSON là đủ.”** Có thể sai khi property order, null/default/number format hoặc field nghiệp vụ thay đổi. Cần semantic canonicalization.

**“Redis SET NX giải quyết exactly once.”** Chưa đủ: crash, expiration, eviction, provider side effects và business uniqueness vẫn cần xử lý.

**“Chỉ cần synchronized trong Java.”** Không bảo vệ nhiều replica/pod.

**“Timeout nghĩa server chưa commit.”** Không đúng. Cần tra trạng thái theo ID ổn định và không retry với operation ID mới khi chưa rõ outcome.

**“Lưu mọi response trong DB vĩnh viễn.”** Không cần thiết và có nguy cơ dữ liệu nhạy cảm, dung lượng hoặc signed URL hết hạn. Có thể lưu result reference/tombstone.

**“Thay đổi TTL/canonicalization không ảnh hưởng client.”** Sai. Đây có thể là breaking behavioral change trong rolling deployment.

**“Không cần kiểm tra auth vì đã có idempotency key.”** Sai. Key không phải token ủy quyền.

## 30. Bài tập tình huống

### Bài 1 — Thay số tiền, giữ nguyên key

Client gửi K-1 cho CapturePayment 390000 VND. Sau timeout, client sửa thành 490000 VND nhưng vẫn K-1. Server nên làm gì?

**Gợi ý:** Reject key reuse mismatch trước side effect, trả error code ổn định. Không charge 490000 bằng K-1, không trả 200 cho amount cũ như thể amount mới đã được xử lý. Client phải kiểm tra kết quả cũ trước khi tạo ý định mới.

### Bài 2 — Retry sau 48 giờ

API xóa key sau 24 giờ. Mobile offline 48 giờ rồi gửi lại POST /orders với key cũ; đơn ban đầu đã được tạo.

**Gợi ý:** Nếu không còn key/business uniqueness, có thể tạo đơn trùng. Cần retention phù hợp mobile retry hoặc business intent ID/tombstone, và public contract sau TTL.

### Bài 3 — Hai replica cùng claim

API chạy 10 pods. Hai request có K-2 đến gần như đồng thời; cả hai gọi existsByKey rồi đều thấy false.

**Gợi ý:** Race condition. Cần unique constraint/atomic claim ở store chung; chỉ winner bắt đầu operation.

### Bài 4 — Cùng JSON nhưng đổi thứ tự key

Request lần đầu JSON fields orderId, quantity. Retry có cùng giá trị nhưng đảo thứ tự property. Raw body hash khác.

**Gợi ý:** Nếu contract coi hai JSON semantic-equivalent, canonicalize field order/kiểu theo quy tắc ổn định và lưu algorithm version.

### Bài 5 — Payment captured trước crash

Server ghi record PROCESSING, gọi provider capture thành công, sau đó crash trước khi cập nhật COMPLETED. Worker khởi động lại.

**Gợi ý:** Tra provider bằng paymentIntentId/operationId/idempotency key ổn định, không capture bằng ID mới. Reconcile state và finalize idempotency record.

### Bài 6 — Lease 5 phút, retention 72 giờ

Worker chết phút thứ 3, lease hết phút thứ 5. Một kỹ sư muốn xóa key để job mới chạy.

**Gợi ý:** Không xóa key. Reclaim processing lease có kiểm soát, duy trì operation identity và dùng fencing/reconciliation để tránh double execution.

### Bài 7 — Cache bị eviction

Redis lưu key chống trùng, nhưng khi memory đầy Redis loại bỏ record sớm. Payment retry lại và bị thu lần hai.

**Gợi ý:** Không để cache eviction phá business invariant. Dùng durable uniqueness theo paymentIntentId, Redis policy phù hợp và reconciliation; có thể dùng DB làm source of truth.

### Bài 8 — Khóa giống nhau ở hai tenant

Tenant A và B đều gửi key abc. API dùng bảng unique(key) toàn hệ thống, khiến B nhìn thấy conflict của A.

**Gợi ý:** Scope key theo tenant/operationType theo contract; không tiết lộ kết quả tenant khác. Xác định identity từ auth, không tin tenantId user tự đưa.

### Bài 9 — Client tạo key mới cho mỗi retry

HTTP client interceptor sinh UUID mới cho mỗi attempt. Sau timeout, lần retry dùng key khác.

**Gợi ý:** Không còn liên kết cùng ý định. Sinh key một lần cho operation, giữ qua retry/reconnect và lưu pending state phù hợp.

### Bài 10 — Business duplicate nhưng key khác

Client gửi capture cùng paymentIntentId với hai key ngẫu nhiên khác. Tầng idempotency coi là hai request mới.

**Gợi ý:** Payment domain phải có unique constraint/state machine theo paymentIntentId để ngăn double capture ngoài policy, không dựa key alone.

### Bài 11 — Bỏ fingerprint record sau deploy

v1 canonicalize JSON theo thứ tự field; v2 canonicalize khác. Rolling deployment khiến retry bị từ chối hoặc được coi là mới.

**Gợi ý:** Lưu fingerprint version, giữ adapter/cách so sánh cũ trong retention, kiểm thử cross-version.

### Bài 12 — Result chứa URL đã hết hạn

Request đầu tạo báo cáo và trả signed URL có hiệu lực 15 phút; retry sau 2 giờ.

**Gợi ý:** Không phải replay URL hết hạn như thể còn tải được. Contract có thể lưu jobId/resultRef và cung cấp endpoint authenticated để tạo URL mới, không tạo job mới bằng key cũ.

### Bài 13 — Đơn đã bị hủy nhưng key vẫn còn

Cùng key retry PlaceOrder sau khi đơn gốc đã CANCELLED. Có nên tạo Order mới vì trạng thái cũ không còn CONFIRMED?

**Gợi ý:** Không. Retry cùng ý định phải trỏ về operation cũ và trạng thái chính thức, kể cả đã CANCELLED. Ý định đặt đơn mới cần key mới và nghiệp vụ riêng.

### Bài 14 — Cleanup vượt cửa sổ khi job chưa hoàn tất

Một báo cáo nền xử lý 36 giờ, nhưng TTL tính từ firstSeenAt là 24 giờ. Client retry khi report vẫn đang chạy.

**Gợi ý:** Nếu xóa key sau 24 giờ có thể tạo job thứ hai. Giữ identity khi PROCESSING và chỉ bắt đầu retention terminal sau khi job kết thúc, hoặc chính sách tương đương có recovery rõ.

### Bài 15 — Key reuse mismatch từ cùng user

Client dùng cùng key sau khi đổi địa chỉ giao hàng. Một kỹ sư muốn coi địa chỉ không quan trọng và cho phép đổi vì chỉ là metadata.

**Gợi ý:** Nếu địa chỉ ảnh hưởng shipping cost, tax, fulfillment hoặc business outcome, nó phải nằm trong fingerprint hoặc versioned intent. Không loại field khỏi fingerprint nếu thay đổi ý định.

## 31. Checklist cho API idempotency

### Contract
- [ ] Đã định nghĩa đơn vị một business intent và operation type.
- [ ] Có idempotency scope ổn định theo tenant/principal/operation.
- [ ] Key có format, giới hạn độ dài và entropy phù hợp.
- [ ] Same key + same request trả result/status của cùng operation.
- [ ] Same key + different request bị từ chối trước side effect.
- [ ] Different key + same business ID được bảo vệ theo invariant phù hợp.
- [ ] Mã HTTP/error/status URL được mô tả trong API contract.
- [ ] Có hành vi rõ sau retention window; không hứa dedup vĩnh viễn nếu không bảo đảm.

### Fingerprint
- [ ] Bao gồm đầy đủ field ảnh hưởng business outcome.
- [ ] Canonicalization có quy tắc cho JSON order, number, null/omitted, Unicode, headers.
- [ ] Không đưa traceId/timestamp retry ngẫu nhiên vào fingerprint.
- [ ] Có fingerprint version và tương thích khi rolling deploy.
- [ ] Không log raw payload chứa PII/secret; cân nhắc HMAC khi cần.

### Retention và recovery
- [ ] Đã khảo sát client offline, gateway, broker, DLQ, provider và manual replay.
- [ ] Phân biệt HTTP deadline, processing lease, business TTL và key retention.
- [ ] Không xóa key PROCESSING chỉ vì lease hết.
- [ ] Terminal retention bắt đầu theo quy tắc được công bố.
- [ ] Có tombstone/business uniqueness khi duplicate risk vượt TTL cache.
- [ ] Có cleanup batch, storage monitoring và retention policy dữ liệu nhạy cảm.
- [ ] Có crash recovery và reconciliation với external provider.
- [ ] Có kịch bản rollback/failover/multi-region.

### Atomicity và an toàn
- [ ] Claim key là atomic giữa nhiều replica.
- [ ] Record/key lookup không tạo race với cleanup.
- [ ] Không dùng synchronized JVM làm bảo đảm duy nhất.
- [ ] Command local được ghi với idempotency/outbox trong transaction khi phù hợp.
- [ ] External side effects dùng ID ổn định và status lookup.
- [ ] Authn/authz áp dụng trước khi trả kết quả hoặc dữ liệu của operation.
- [ ] Rate limits và resource quotas bảo vệ khỏi spam key mới.

### Vận hành
- [ ] Có tests cùng key/cùng payload, mismatch và concurrency.
- [ ] Có tests timeout sau commit, provider crash, DLQ replay và expiry boundary.
- [ ] Có metrics mismatch, stale PROCESSING, duplicate business attempt và cleanup.
- [ ] Có alert đối soát sai lệch thực, không chỉ HTTP 500.
- [ ] UX phân biệt đang xử lý, đã hoàn tất, chưa xác định và key mismatch.

## 32. Ghi nhớ

1. **Idempotency key định danh một ý định, không phải một HTTP attempt.** Client phải giữ cùng key qua retry, không sinh key mới cho mỗi lần gửi.
2. **Scope quyết định tính duy nhất:** tenant/principal, operationType và key phải được định nghĩa nhất quán.
3. **Cùng key + cùng payload** phải không tạo side effect mới; trả result/status của cùng operation.
4. **Cùng key + payload khác** phải bị phát hiện bằng fingerprint và từ chối rõ ràng trước khi xử lý, không âm thầm thực hiện hoặc replay kết quả không phù hợp.
5. **Fingerprint phải phản ánh ý nghĩa nghiệp vụ**, có canonicalization và versioning ổn định qua deploy.
6. **Retention là cam kết thiết kế:** tính từ retry/replay window và mức rủi ro, không từ một con số TTL tùy hứng.
7. **HTTP timeout, processing lease, reservation TTL và idempotency retention là bốn thời hạn khác nhau.** Hết lease không xóa ý nghĩa operation.
8. **Sau TTL, side effect vẫn tồn tại.** Business uniqueness, operationId hoặc tombstone có thể cần bảo vệ dài hơn response cache.
9. **Atomic claim và durable recovery quan trọng hơn một câu lệnh SET NX.** External side effects đòi idempotency/reconciliation tại owner hoặc provider.
10. **Thiết kế tốt phải có cả hợp đồng cho client và test sự cố:** rollback, failover, retry, crash sau commit, event trùng và dữ liệu mới–cũ trong rolling deployment.