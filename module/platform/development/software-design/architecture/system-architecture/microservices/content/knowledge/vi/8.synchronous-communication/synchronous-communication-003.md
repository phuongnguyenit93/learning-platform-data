# Mã trạng thái, lỗi có cấu trúc và thông tin phục vụ chẩn đoán trong giao tiếp đồng bộ Microservices

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Giao tiếp đồng bộ.  
> **Mục tiêu:** Thiết kế hợp đồng phản hồi lỗi nhất quán và hữu ích cho HTTP API khi nhiều dịch vụ gọi nhau; phân biệt lỗi người gọi, lỗi nghiệp vụ, lỗi hệ thống và lỗi dependency; sử dụng mã trạng thái, tài liệu lỗi có cấu trúc và thông tin tương quan để consumer xử lý đúng và đội vận hành tìm được nguyên nhân.

## 1. Vì sao một mã HTTP chưa đủ?

Trong Microservices, một request từ người dùng có thể đi qua API Gateway, Ordering, Inventory, Payment và một nhà cung cấp bên ngoài. Chỉ nhìn thấy HTTP 500 ở gateway không cho biết yêu cầu thất bại do dữ liệu đầu vào, trạng thái đơn không hợp lệ, thiếu quyền, timeout mạng, hết connection pool hay provider đã thực thi giao dịch nhưng đánh mất response.

Ví dụ:

~~~text
Mobile Client
    |
    v
API Gateway
    |
    v
Ordering Service ------> Inventory Service
    |
    v
Payment Service -------> External Payment Provider
    |
    v
Order Repository
~~~

Một lần gọi Payment có thể trả HTTP 504 ở Ordering vì hết deadline. Nhưng **504 không chứng minh provider chưa thanh toán**. Provider có thể đã xử lý thành công và response bị mất giữa đường. Nếu client tự retry lệnh tạo payment bằng một mã giao dịch mới, người mua có nguy cơ bị tính tiền hai lần.

Hợp đồng lỗi tốt cần trả lời được bốn câu hỏi:

1. **Request có đạt kết quả được cam kết không?** Nếu không, hiện đang là thất bại xác nhận hay kết quả chưa biết?
2. **Nguyên nhân thuộc loại gì?** Input, quyền, xung đột trạng thái, giới hạn tải, lỗi nội bộ, hay dependency?
3. **Consumer nên làm gì tiếp?** Sửa input, đăng nhập, đọc lại resource, dừng thao tác, retry có điều kiện, theo dõi operation hay liên hệ hỗ trợ?
4. **Đội vận hành tìm được dấu vết nào?** Request ID, trace ID, mã lỗi ổn định, route, dependency liên quan, timestamp, log/metric/trace.

Vì vậy, một phản hồi lỗi trong hệ thống phân tán có ba lớp phối hợp:

- **HTTP status**: phân loại kết quả ở mức giao thức.
- **Structured error body**: nêu loại lỗi, mã máy có thể xử lý, ngữ nghĩa và thông tin được phép công khai.
- **Diagnostic context**: giúp nối request bên ngoài với log, trace, metric và operation bên trong.

Không dùng body để che sai HTTP status, cũng không trông chờ duy nhất vào HTTP status để điều khiển mọi nhánh nghiệp vụ.

## 2. Tách lỗi giao thức, lỗi nghiệp vụ và lỗi hạ tầng

| Lớp | Câu hỏi | Ví dụ | Đầu ra mong muốn |
|---|---|---|---|
| **Transport/protocol** | HTTP request có hợp lệ và được hiểu đúng không? | JSON sai cú pháp, Content-Type không hỗ trợ | 400 hoặc 415 với lỗi rõ |
| **Authentication/authorization** | Actor là ai và có quyền thao tác trên resource không? | Token thiếu, tenant không sở hữu đơn | 401, 403 hoặc 404 theo chính sách |
| **Validation/domain rule** | Yêu cầu có ý nghĩa và hợp lệ với trạng thái hiện tại không? | Số lượng âm, đơn đã hủy không thể Submit | 422 hoặc 409 theo quy ước |
| **Concurrency/precondition** | Dữ liệu mà consumer dựa vào còn mới không? | If-Match dùng ETag cũ | 412 hoặc 409 tùy hợp đồng |
| **Capacity/rate limit** | Tại thời điểm này hệ thống còn nhận thêm việc không? | Vượt quota hoặc hệ thống đang giảm tải | 429 hoặc 503, có tín hiệu retry phù hợp |
| **Internal/server failure** | Server không thực hiện được cam kết vì lỗi ngoài dự kiến? | Lỗi code, DB unavailable | 500 hoặc mã 5xx phù hợp |
| **Downstream failure** | Service phụ thuộc không đáp ứng? | Gateway không nhận response đúng hoặc đúng hạn | 502/503/504 theo vị trí và ý nghĩa |
| **Business outcome** | Tác vụ kết thúc với kết quả nghiệp vụ được mô tả hợp lệ? | Thanh toán bị ngân hàng từ chối hợp lệ | Có thể là kết quả nghiệp vụ, không mặc nhiên 500 |

Điểm cuối cần chú ý: **payment declined không tự động là HTTP 500**. Nếu API là “thử thanh toán và nhận quyết định”, kết quả DECLINED có thể là một outcome hợp lệ đã được xử lý, đi kèm HTTP 200 với trạng thái rõ ràng. Nếu API cam kết “tạo resource đã thanh toán” và không đáp ứng điều kiện nghiệp vụ, hợp đồng có thể dùng 409/422. Sự nhất quán của contract quan trọng hơn việc gắn một status máy móc.

Phân biệt tiếp ba trạng thái:

- **Success confirmed:** Hành động được xác nhận hoàn tất theo postcondition.
- **Failure confirmed:** Biết chắc yêu cầu bị từ chối hoặc không hoàn tất theo quy tắc.
- **Outcome unknown:** Request/response bị mất hoặc timeout sau khi có thể đã phát sinh side effect; cần truy vấn trạng thái, idempotency và đối soát.

Trạng thái unknown là đặc trưng quan trọng của giao tiếp đồng bộ qua mạng.

## 3. Bản đồ các nhóm mã trạng thái HTTP

| Nhóm | Ý nghĩa cơ bản | Lưu ý cho Microservices |
|---|---|---|
| 1xx | Thông tin tạm thời ở tầng giao thức | Ít khi là business result |
| 2xx | Request đã được xử lý thành công theo semantics của status | 202 chỉ là accepted, chưa chứng minh workflow hoàn tất |
| 3xx | Chuyển hướng hoặc điều kiện cache | 304 liên quan conditional request, không phải lỗi nghiệp vụ |
| 4xx | Request không thể được đáp ứng theo điều kiện được công bố | Nhiều 4xx là kết quả dự kiến, không nên log như outage |
| 5xx | Server hoặc thành phần đang phục vụ không thể hoàn tất yêu cầu | Nên đo theo endpoint, dependency và tác động người dùng |

**Một status phải diễn giải cùng method, endpoint và hợp đồng.** Ví dụ 404 với GET /orders/{id} có nghĩa resource không tồn tại hoặc đang được che theo policy. Nhưng nếu Ordering gọi Payment rồi Payment trả 404 vì mã giao dịch chưa tồn tại, Ordering không được tự động gửi nguyên 404 đó cho người dùng nếu endpoint ngoài đang xử lý một order có thật.

Status phản ánh **kết quả quan sát ở ranh giới API hiện tại**, không phải chỉ bản sao của status từ dependency sâu nhất.

## 4. Các mã thành công cần chọn đúng

### 200 OK

Phù hợp cho GET thành công, hoặc command đồng bộ đã hoàn tất và trả body kết quả.

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "orderId": "ord-2048",
  "status": "CONFIRMED"
}
~~~

Response này hứa rằng order đã đạt trạng thái CONFIRMED theo hợp đồng. Không được trả status CONFIRMED nếu hệ thống chỉ mới gửi message chưa được xử lý.

### 201 Created

Phù hợp khi request đã tạo resource. Nên trả Location nếu có resource URI để client truy cập.

~~~http
HTTP/1.1 201 Created
Location: /orders/ord-2048
Content-Type: application/json

{
  "id": "ord-2048",
  "status": "DRAFT"
}
~~~

### 202 Accepted

Server đã chấp nhận yêu cầu để xử lý nhưng chưa hoàn thành. Thường dùng với workflow kéo dài, có operation ID và đường theo dõi.

~~~http
HTTP/1.1 202 Accepted
Location: /operations/op-827
Content-Type: application/json

{
  "operationId": "op-827",
  "status": "PENDING",
  "statusUrl": "/operations/op-827"
}
~~~

202 không chứng minh Payment đã capture hay Inventory đã reserve. Cần một API riêng truy vấn kết quả cuối, SLA hoàn tất, retention và retry policy.

### 204 No Content

Phù hợp cho thao tác thành công nhưng không cần body. Không trả JSON body kèm 204. Nếu consumer cần version, operation hoặc trạng thái nghiệp vụ, 200 với body có thể dễ dùng hơn.

### 304 Not Modified

Sử dụng trong conditional GET để tối ưu cache khi representation không thay đổi theo điều kiện request; không coi đây là lỗi business. ETag/If-None-Match và cache semantics phải được triển khai nhất quán.

## 5. Lỗi người gọi: 400, 401, 403, 404, 405, 415, 422

### 400 Bad Request — request không được hiểu hoặc sai quy tắc đầu vào ở tầng cú pháp

Ví dụ JSON hỏng, query parameter không chuyển được kiểu, thiếu cấu trúc bắt buộc theo contract.

~~~http
POST /orders
Content-Type: application/json

{"items": [
~~~

Server có thể trả:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/malformed-request",
  "title": "Malformed request",
  "status": 400,
  "detail": "The JSON request body is not valid.",
  "code": "REQUEST_MALFORMED",
  "requestId": "req-782da"
}
~~~

Không trả nội dung JSON gốc trong lỗi nếu có thông tin cá nhân, token hoặc dữ liệu thanh toán.

### 401 Unauthorized — chưa có authentication hợp lệ

Tên status là Unauthorized nhưng trên HTTP nó thường biểu thị **thiếu hoặc không hợp lệ thông tin xác thực**, không đồng nghĩa đã xác thực nhưng thiếu quyền. Với cơ chế Bearer token, phản hồi và WWW-Authenticate phải theo chuẩn scheme đang dùng.

### 403 Forbidden — đã biết actor nhưng không được phép

Ví dụ nhân viên không có quyền hoàn tiền hoặc customer cố xem đơn ngoài phạm vi. Client không nên tự retry 403 cho đến khi quyền hoặc người dùng thay đổi.

### 404 Not Found — resource không tồn tại hoặc không thể được tiết lộ

GET /orders/ord-does-not-exist có thể trả 404. Một API có thể cố ý trả 404 thay 403 để không tiết lộ sự tồn tại của resource nhạy cảm; policy phải nhất quán và không làm lộ qua thời gian phản hồi hoặc error detail.

### 405 Method Not Allowed

Endpoint tồn tại nhưng method không được hỗ trợ, ví dụ PUT trên resource chỉ cho GET/POST. Response nên công bố Allow header theo HTTP semantics.

### 415 Unsupported Media Type

Dùng khi client gửi Content-Type mà endpoint không hỗ trợ, ví dụ application/xml trong API chỉ chấp nhận JSON.

### 422 Unprocessable Content

Một lựa chọn để diễn tả request có cú pháp hợp lệ nhưng vi phạm quy tắc dữ liệu, chẳng hạn quantity âm hoặc delivery option không hợp lệ. Có tổ chức dùng 400 cho validation; hãy chọn quy ước rõ, áp dụng nhất quán và công bố trong OpenAPI.

Ví dụ:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Validation failed",
  "status": 422,
  "code": "ORDER_INPUT_INVALID",
  "detail": "One or more fields are invalid.",
  "invalidParams": [
    {
      "name": "items[0].quantity",
      "reason": "Quantity must be greater than zero.",
      "code": "POSITIVE_VALUE_REQUIRED"
    }
  ],
  "requestId": "req-782db"
}
~~~

**Không trả 500** cho một validation error đã được dự đoán. Nó sẽ khiến monitoring coi lỗi do người dùng là sự cố server và có thể khiến client retry không cần thiết.

## 6. Trạng thái xung đột: 409 Conflict và 412 Precondition Failed

Hai mã này thường gặp trong những hệ thống có nhiều consumer và có thay đổi đồng thời.

### 409 Conflict — xung đột với trạng thái nghiệp vụ hiện tại

Ví dụ:

- Yêu cầu CancelOrder trong khi order đã FULFILLED.
- SubmitOrder khi cùng một workflow đang chạy và hệ thống không chấp nhận thao tác mới.
- Gửi một idempotency key đã có với payload khác.
- Tạo reservation xung đột điều kiện tồn kho theo contract.

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/order-state-conflict",
  "title": "Order cannot be cancelled",
  "status": 409,
  "code": "ORDER_STATE_CONFLICT",
  "detail": "The order is already fulfilled.",
  "currentStatus": "FULFILLED",
  "requestId": "req-782dc"
}
~~~

Chỉ công bố currentStatus nếu actor có quyền đọc trạng thái đó. 409 thường báo rằng client cần **đọc lại resource hoặc điều chỉnh hành vi**, không phải tự động retry y nguyên nhiều lần.

### 412 Precondition Failed — điều kiện HTTP không còn đúng

Ví dụ client đọc Order version 7, sau đó gửi PATCH hoặc command với If-Match: "7", nhưng order hiện có ETag "8".

~~~http
POST /orders/ord-2048/submit
If-Match: "7"
~~~

Server có thể trả:

~~~http
HTTP/1.1 412 Precondition Failed
ETag: "8"
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/stale-resource",
  "title": "Resource version changed",
  "status": 412,
  "code": "RESOURCE_VERSION_MISMATCH",
  "detail": "Reload the order before submitting it.",
  "requestId": "req-782dd"
}
~~~

Nếu contract dùng expectedVersion trong JSON thay cho điều kiện HTTP, tổ chức có thể dùng 409; hãy nêu rõ sự khác biệt. **Idempotency chống lặp cùng ý định và version check chống xử lý trên trạng thái cũ** là hai cơ chế khác nhau.

Không “sửa” xung đột bằng cách client tự gửi version mới mà không kiểm tra thay đổi nghiệp vụ đã xảy ra.

## 7. 429 Too Many Requests và 503 Service Unavailable

### 429 — giới hạn phía requestor hoặc quota đã được công bố

Khi client, tenant hoặc API key vượt quota, trả 429. Nếu có thể xác định khi nào nên thử lại, dùng Retry-After.

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 20
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/rate-limit",
  "title": "Too many requests",
  "status": 429,
  "code": "RATE_LIMIT_EXCEEDED",
  "detail": "Request rate exceeds the allowed limit.",
  "requestId": "req-782de"
}
~~~

Retry-After có thể là số giây hoặc HTTP-date. Client cần áp giới hạn số lần retry và deadline. Không xem header này là lời đảm bảo request sẽ thành công sau đúng 20 giây.

### 503 — dịch vụ tạm thời không thể phục vụ

Ví dụ maintenance, mất năng lực xử lý, dependency bắt buộc unavailable hoặc quá tải khiến service phải load-shed. Có thể dùng Retry-After nếu có dự báo có cơ sở.

Phân biệt:

- **429:** requestor vượt giới hạn được áp cho requestor/quota.
- **503:** server tại thời điểm đó không đủ năng lực hoặc tạm không thể phục vụ theo hợp đồng.

Lỗi tăng tải có thể cần 503, không ép mọi overload vào 429 nếu không thực sự liên quan quota requestor. Retry 503 không kiểm soát dễ khiến tải tăng hơn; client phải tôn trọng budget, backoff và jitter.

## 8. Lỗi server/gateway: 500, 502 và 504

### 500 Internal Server Error

Thể hiện một lỗi bất ngờ trong service: bug, invariant bị phá do code, transaction thất bại không được chuyển thành lỗi cụ thể hoặc trạng thái nội bộ không xử lý được.

Public response nên ổn định, không chứa stack trace hoặc SQL. Đội vận hành ghi chi tiết trong log có kiểm soát quyền và trace ID.

### 502 Bad Gateway

Một gateway/proxy đóng vai trò trung gian nhận response không hợp lệ hoặc không đáp ứng hợp đồng ở upstream. Ví dụ reverse proxy không thể sử dụng phản hồi từ service phụ thuộc. Không có nghĩa mọi lỗi HTTP từ upstream đều phải map thành 502.

### 504 Gateway Timeout

Một gateway/proxy không nhận response kịp từ upstream. Dùng phù hợp khi server hiện tại đóng vai trò trung gian và đã chờ quá thời hạn. **Timeout của request không chứng minh downstream chưa thực hiện side effect**.

### 408 Request Timeout khác 504

408 thường liên quan server chờ client gửi request đầy đủ nhưng không nhận kịp, trong khi 504 là vấn đề gateway chờ upstream. Không dùng 408 như mã mặc định cho mọi dependency timeout.

### 502/503/504 trong chuỗi call

~~~text
Client -> Gateway -> Ordering -> Inventory

Tình huống A: Inventory trả một business 409.
  Ordering cần kiểm tra contract và map thành outcome đúng của Ordering,
  không bắt buộc sao chép 409 một cách máy móc.

Tình huống B: Inventory unavailable, Ordering không thể hoàn tất.
  Ordering có thể trả 503 với mã DEPENDENCY_UNAVAILABLE.

Tình huống C: Ordering hoạt động bình thường nhưng Gateway hết hạn
  chờ response từ Ordering.
  Gateway có thể trả 504.

Tình huống D: Ordering có bug nội bộ.
  Ordering trả 500, Gateway thường chuyển trạng thái phù hợp
  và gắn correlation context của chính ranh giới.
~~~

Chọn mã dựa trên vai trò và outcome tại **ranh giới đang trả response**, không đơn giản sao chép mã từ lớp sâu nhất. Đảm bảo mã response và body.status thống nhất.

## 9. Thiết kế lỗi có cấu trúc theo Problem Details

Đối với HTTP API, **Problem Details for HTTP APIs (RFC 9457)** là khuôn dạng thông dụng cho lỗi. Media type là **application/problem+json**. Những trường cốt lõi:

| Trường | Vai trò | Ghi chú |
|---|---|---|
| **type** | URI xác định loại vấn đề | Nên ổn định; URI có thể trỏ đến tài liệu |
| **title** | Tóm tắt ngắn, dễ hiểu | Không nên thay đổi tùy từng lần lỗi cùng type |
| **status** | Mã HTTP được mô tả | Đảm bảo nhất quán với status thực trên response |
| **detail** | Mô tả cụ thể lần lỗi này | Không nên chứa secrets/PII hay chi tiết hạ tầng |
| **instance** | URI định danh lần xuất hiện vấn đề | Có thể dùng khi không lộ dữ liệu nhạy cảm |
| **extension members** | Thông tin bổ sung có định nghĩa | Ví dụ code, requestId, invalidParams |

Khuôn dạng này không bắt buộc mọi trường đều xuất hiện. Nếu không cung cấp type thì ngữ nghĩa mặc định là about:blank. Đối với API có taxonomy nghiệp vụ, nên thiết kế type URI và mã ứng dụng ổn định.

Ví dụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
X-Request-ID: req-92a1d

{
  "type": "https://api.example.test/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "detail": "The order is not in a state that allows submission.",
  "instance": "/errors/instances/err-3924",
  "code": "ORDER_NOT_SUBMITTABLE",
  "requestId": "req-92a1d",
  "retryable": false
}
~~~

**type** định danh class của vấn đề; **code** là mã máy có thể xử lý theo taxonomy của sản phẩm; **requestId** giúp hỗ trợ người dùng và truy log. Trường retryable là gợi ý theo hợp đồng, không cho phép client bỏ qua deadline, idempotency hoặc điều kiện tải.

### URI type nên vận hành thế nào?

Một type URI có thể đưa đến tài liệu mô tả:

- Ý nghĩa lỗi và điều kiện phát sinh.
- HTTP status thông thường.
- Có thể retry hay không, sau điều kiện nào.
- Client nên hiển thị gì/khắc phục gì.
- Các extension members và kiểu dữ liệu của chúng.
- Liên hệ với business workflow hoặc version.

Giữ ổn định ngữ nghĩa type; không dùng một URI chung cho mọi lỗi rồi để consumer parse detail string. Có thể chọn type cho nhóm lỗi và code chi tiết, miễn taxonomy được công bố.

### Có cần trường success=false?

Không cần nếu HTTP status và Problem Details đã biểu đạt lỗi. Việc buộc mọi response có success=true/false đôi khi làm 200 bao phủ cả lỗi, gây khó cho gateway, cache, client SDK, tracing và monitoring. Nếu hệ thống đã có envelope chung, vẫn phải giữ nghĩa status và machine-readable code đúng.

## 10. Danh mục lỗi ứng dụng có tên ổn định

HTTP status chỉ có khoảng ý nghĩa chung. Một endpoint có thể có nhiều lỗi 409 khác nhau: ORDER_NOT_SUBMITTABLE, ORDER_ALREADY_CANCELLED, IDEMPOTENCY_KEY_REUSED. Consumer cần phân biệt chúng bằng **code ổn định**, không parse detail viết bằng ngôn ngữ tự nhiên.

Ví dụ một danh mục:

| Code | HTTP | Ý nghĩa | Hành vi client |
|---|---:|---|---|
| REQUEST_MALFORMED | 400 | Body hoặc tham số sai cú pháp | Sửa request |
| INPUT_VALIDATION_FAILED | 422 | Giá trị hợp lệ về cú pháp nhưng vi phạm ràng buộc | Hiển thị lỗi trường |
| UNAUTHENTICATED | 401 | Thiếu xác thực hợp lệ | Vào luồng xác thực |
| RESOURCE_FORBIDDEN | 403 | Không đủ quyền | Dừng, yêu cầu quyền phù hợp |
| ORDER_NOT_FOUND | 404 | Không tìm thấy hoặc không tiết lộ đơn | Thông báo theo policy |
| ORDER_STATE_CONFLICT | 409 | Hành vi không hợp lệ với state hiện tại | Đọc lại state |
| IDEMPOTENCY_CONFLICT | 409 | Key cũ được dùng với payload khác | Không retry cùng key cho intent khác |
| RESOURCE_VERSION_MISMATCH | 412 | ETag/điều kiện phiên bản lỗi thời | Đọc lại và quyết định |
| RATE_LIMIT_EXCEEDED | 429 | Vượt quota giới hạn | Dùng backoff và Retry-After |
| DEPENDENCY_UNAVAILABLE | 503 | Dependency bắt buộc tạm không thể phục vụ | Retry có điều kiện nếu an toàn |
| UPSTREAM_TIMEOUT | 504 | Gateway chờ dependency quá lâu | Kiểm tra unknown outcome và deadline |
| INTERNAL_ERROR | 500 | Lỗi bất ngờ không công bố nội bộ | Ghi requestId, liên hệ hỗ trợ |

Danh mục cần có **owner**, định nghĩa, HTTP status thường dùng, khả năng retry, phạm vi bảo mật và test contract. Không nên dùng exception class name làm mã public vì khi refactor Java class sẽ thay đổi dù nghiệp vụ không đổi.

Một code có thể xuất hiện ở nhiều endpoint, nhưng đừng sử dụng cùng code cho những ý nghĩa khác nhau. Nếu thay đổi nghĩa, cần migration/version có quản trị.

## 11. Mô hình lỗi có cấu trúc cho validation nhiều trường

Một request có thể vi phạm nhiều điều kiện: số lượng bằng 0, mã tiền không hợp lệ, địa chỉ giao hàng thiếu thông tin. Trả một lỗi tổng quát giúp client biết request sai, nhưng để UI sửa được cần thông tin từng trường.

Ví dụ:

~~~json
{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Validation failed",
  "status": 422,
  "code": "INPUT_VALIDATION_FAILED",
  "detail": "The request contains invalid values.",
  "invalidParams": [
    {
      "name": "items[0].quantity",
      "code": "GREATER_THAN_ZERO_REQUIRED",
      "reason": "Quantity must be positive."
    },
    {
      "name": "currency",
      "code": "UNSUPPORTED_CURRENCY",
      "reason": "The requested currency is not supported."
    }
  ],
  "requestId": "req-b2c76"
}
~~~

Thiết kế cần trả lời:

- **name** là JSON path, field name hay business field ID? Cần ổn định để UI mapping.
- **code** của từng field có dùng cho bản địa hóa client không?
- **reason** có thể thay đổi ngôn ngữ và câu chữ hay không?
- Danh sách trả toàn bộ lỗi có thể kiểm tra được hay chỉ lỗi đầu tiên?
- Giới hạn số lỗi để tránh response quá lớn hoặc bị lạm dụng.
- Không echo giá trị nhạy cảm như password, token, số thẻ, thông tin định danh.
- Một số domain rule liên quan nhiều field nên có code ở mức đối tượng, không ép vào field cụ thể.

Đừng dùng thông báo lỗi chi tiết của database hoặc JSON parser nguyên gốc nếu chúng có thể lộ cấu trúc nội bộ. API nên chuẩn hóa thành thông điệp và mã lỗi an toàn.

## 12. Thông tin phục vụ chẩn đoán: requestId, correlationId, traceId và operationId

Các định danh có mục đích khác nhau.

| ID | Ý nghĩa | Nơi thường dùng |
|---|---|---|
| **requestId** | Định danh một HTTP request ở ranh giới ingress | Log, hỗ trợ khách hàng, response header |
| **traceId** | Nối các span trong một distributed trace | Tracing, log correlation |
| **spanId** | Định danh một đoạn xử lý trong trace | Tracing theo từng dependency |
| **correlationId** | Liên hệ nhiều thao tác thuộc một hành trình, nếu tổ chức định nghĩa | Log, sự kiện, workflow |
| **operationId** | Định danh một tác vụ nghiệp vụ có vòng đời riêng | API polling, idempotency/reconciliation |
| **domain object ID** | Định danh order, reservation, payment | Truy vấn nghiệp vụ, audit có quyền |

Không dùng chúng thay thế nhau một cách tùy tiện. Một HTTP request có thể sinh nhiều span. Nhiều lần retry/tra cứu sau đó có requestId khác nhưng cùng business operation ID. Một trace có thể không kéo dài liên tục qua workflow async nhiều ngày; các link hoặc correlation ID bổ sung sẽ giúp nối các mốc.

### Ví dụ luồng qua ba service

~~~text
Request from client:
  X-Request-ID = req-9b10 (do ingress phát hành/xác minh)
  traceId      = 4bf92f3577b34da6a3ce929d0e0e4736
  operationId  = submit-ord-2048-v1

Gateway span:
  traceId      = 4bf92f3577b34da6a3ce929d0e0e4736
  spanId       = 00f067aa0ba902b7

Ordering span:
  same traceId, new spanId

Inventory span:
  same traceId, new spanId

Payment span:
  same traceId, new spanId

Later reconciliation:
  new requestId / possibly new trace
  same operationId or business transaction ID
~~~

**W3C Trace Context** mô tả việc truyền traceparent/tracestate giữa các thành phần tương thích. Không tự thiết kế trace propagation khác biệt ở từng service nếu hạ tầng đã hỗ trợ. Nhưng cần xác thực và giới hạn dữ liệu nhận từ biên ngoài; không cho người gọi bên ngoài kiểm soát tùy ý logging/tracing của hệ thống nội bộ.

### Có nên trả traceId cho client?

Có thể trả requestId an toàn trong header và Problem Details body để hỗ trợ tra cứu. Có tổ chức cũng công bố traceId; điều này tùy threat model và cách kiểm soát truy cập telemetry. Không công bố span nội bộ, URL gọi riêng, tên host, token hoặc topology nhạy cảm. Dữ liệu công khai chỉ nên đủ để hỗ trợ định danh sự cố.

## 13. Log có cấu trúc để tìm cùng một request trên nhiều service

Thay vì ghi câu log tự do “Error processing order”, sử dụng log có trường chuẩn:

~~~json
{
  "timestamp": "2026-11-11T14:10:18.200Z",
  "level": "ERROR",
  "service": "ordering-service",
  "environment": "production",
  "route": "POST /orders/{orderId}/submit",
  "method": "POST",
  "httpStatus": 503,
  "errorCode": "DEPENDENCY_UNAVAILABLE",
  "requestId": "req-9b10",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "dependency": "inventory",
  "dependencyOperation": "reserveStock",
  "durationMs": 348,
  "retryAttempt": 1,
  "message": "Inventory reservation dependency unavailable"
}
~~~

Các trường này cho phép tìm theo request, route template, error code và dependency. Hãy tách hai lớp:

**Public response:** thông điệp ổn định, không rò rỉ cấu trúc nội bộ; cho client biết phải làm gì.

**Internal logs/traces:** nguyên nhân kỹ thuật, lỗi gốc, dependency, stack trace khi phù hợp; chỉ người được quyền mới truy cập.

Một vài nguyên tắc:

- Không log Access Token, Authorization header, cookie, password, mã OTP, số thẻ hoặc payload thanh toán.
- Cẩn thận với email, số điện thoại, địa chỉ, order ID và dữ liệu tenant; áp chính sách mask/hash/truy cập theo quy định.
- Tránh ghi raw request/response body không kiểm soát.
- Dùng route template thay cho raw path chứa userId/orderId làm metric label có cardinality cao.
- Có retention, truy cập, sampling và chính sách redaction cho telemetry.
- Sử dụng UTC hoặc timestamp có offset; đảm bảo clock synchronization đủ cho điều tra.
- Không ghi cùng exception ở mọi layer với stack trace đầy đủ nếu làm nhiễu hoặc nhân chi phí log.

Để truy nguyên lỗi, cần log ở **điểm sở hữu hành động** và **điểm chuyển đổi ranh giới**, không phải spam cùng một exception ở mọi nơi.

## 14. Mẫu phản hồi lỗi an toàn cho người dùng và đội hỗ trợ

Một thông điệp lỗi tốt cần tách thông tin máy và thông tin hiển thị:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
X-Request-ID: req-ef631
Retry-After: 10

{
  "type": "https://api.example.test/problems/dependency-unavailable",
  "title": "Service temporarily unavailable",
  "status": 503,
  "code": "DEPENDENCY_UNAVAILABLE",
  "detail": "The request could not be completed at this time.",
  "requestId": "req-ef631",
  "retryable": true
}
~~~

Client có thể hiển thị “Không thể hoàn tất thao tác lúc này. Vui lòng thử lại sau.” và cung cấp requestId nếu liên hệ hỗ trợ. Không trả:

~~~json
{
  "error": "java.sql.SQLTransientConnectionException at com.example.orders.OrderRepository.save(...)",
  "databaseHost": "db-prod-private-01",
  "connectionString": "jdbc:postgresql://...",
  "sql": "SELECT ..."
}
~~~

Ngay cả khi lỗi kỹ thuật có thật, những chi tiết đó thuộc telemetry nội bộ và có thể tiết lộ hệ thống hoặc dữ liệu nhạy cảm.

### Bản địa hóa nội dung

Nếu API phục vụ nhiều locale, nên giữ **code/type ổn định** và cho client bản địa hóa thông điệp theo code. Detail của server có thể dịch theo Accept-Language khi phù hợp, nhưng client không nên so khớp string tiếng Việt/tiếng Anh để quyết định retry hay điều hướng.

Ví dụ code ORDER_STATE_CONFLICT có thể tương ứng nhiều thông điệp thân thiện, nhưng ngữ nghĩa máy không thay đổi.

## 15. Truyền và chuyển đổi lỗi qua nhiều service

Khi Ordering gọi Inventory, không nên mù quáng chuyển nguyên nội dung lỗi Inventory ra public API. Cần phân tích ranh giới:

~~~text
Client -- POST /orders/{id}/submit --> Ordering
                                         |
                                         +--> Inventory.reserve()
                                                    |
                                                    v
                                              Inventory result
~~~

Các trường hợp:

**Inventory trả 409 OUT_OF_STOCK:** Nếu “hết hàng” là kết quả nghiệp vụ được dự đoán, Ordering có thể chuyển thành ORDER_STOCK_UNAVAILABLE (409/422 theo contract), giữ ý nghĩa không thể submit. Không cần lộ internal stock table hoặc error code không thuộc public domain của Ordering.

**Inventory trả 401 vì credentials nội bộ sai:** Đây là lỗi cấu hình xác thực service-to-service. Client bên ngoài đã đăng nhập đúng không nên nhận 401 như thể cần đăng nhập lại. Ordering nên báo lỗi 5xx phù hợp và ghi log/alert về sự cố auth nội bộ.

**Inventory trả 404 cho reservation ID nội bộ:** Không tự động biến thành 404 của order nếu order có thật. Cần xác định liệu đây là trạng thái workflow, inconsistency hay lỗi vận hành.

**Inventory timeout:** Ordering không chắc request reserve đã xảy ra. Với side effect, có thể chuyển workflow sang trạng thái cần xác minh; response bên ngoài phải phản ánh đúng lời hứa nghiệp vụ.

**Inventory trả 500:** Ordering có thể trả 503 cho một dependency bắt buộc tạm unavailable hoặc 500/502 theo ngữ nghĩa ranh giới, nhưng cần theo dõi nguyên nhân chính trong nội bộ.

Một tầng trung gian nên chuẩn hóa mã lỗi thuộc **contract của chính mình** mà vẫn giữ diagnostic relationship trong log và trace. Cần tránh hai cực đoan: sao chép mọi error body xuyên service, hoặc biến mọi lỗi đã hiểu thành INTERNAL_ERROR khiến client không biết xử lý.

## 16. Error mapping matrix cho chuỗi dịch vụ

| Upstream/downstream condition | Diễn giải ở service hiện tại | Trả cho consumer theo contract |
|---|---|---|
| Request body JSON lỗi | Không parse được request của chính API | 400 REQUEST_MALFORMED |
| Quantity không hợp lệ | Validation/domain input | 422 INPUT_VALIDATION_FAILED |
| Order đã fulfilled nhưng yêu cầu hủy | Domain state conflict | 409 ORDER_STATE_CONFLICT |
| ETag cũ | Conditional request không đạt | 412 RESOURCE_VERSION_MISMATCH |
| Inventory báo OUT_OF_STOCK | Business outcome của ReserveStock | ORDER_STOCK_UNAVAILABLE hoặc outcome được công bố |
| Inventory auth credentials sai | Lỗi service-to-service, không phải client auth | 5xx; log lỗi nội bộ |
| Inventory connection timeout | Dependency chưa có phản hồi trong deadline | 503/504 phù hợp ranh giới; xem unknown side effect |
| Provider trả duplicate transaction | Có thể idempotency replay | Trả kết quả đã có hoặc 409 khi key/payload xung đột |
| Client vượt quota | Rate limit theo client | 429 và Retry-After nếu có |
| Server thiếu capacity | Temporary unavailability | 503 và chính sách retry phù hợp |
| Bug không dự kiến | Internal failure | 500 INTERNAL_ERROR |

Bảng là mô hình khuyến nghị. Contract cụ thể phải thống nhất phương thức, trạng thái, retry semantics và hậu quả nghiệp vụ của từng operation. Đừng chỉ dựa vào mã của một thư viện HTTP hoặc gateway để quyết định.

## 17. Retry phải dựa trên loại lỗi, deadline và tính idempotent

Không có quy tắc “gặp 5xx là retry ngay”. Retry tạo thêm tải đúng lúc dependency có thể đang yếu và gây side effect trùng với POST.

| Kết quả | Hướng xử lý mặc định | Điều kiện đặc biệt |
|---|---|---|
| 400/422 | Không retry tự động | Chỉ sau khi request được sửa |
| 401 | Tổ chức lại authentication | Có thể refresh credential theo flow; không lặp vô hạn |
| 403 | Không retry tự động | Quyền thay đổi mới thử lại |
| 404 | Thường không retry y nguyên | Với eventual consistency có thể có chính sách riêng |
| 409 | Đọc lại trạng thái hoặc xử lý conflict | Idempotency replay có contract riêng |
| 412 | Đọc lại representation/ETag | Không ép version mới thiếu xác minh |
| 429 | Retry có giới hạn, theo Retry-After | Có budget và quota policy |
| 500 | Chỉ retry lỗi transient đã biết an toàn | Phải biết operation có idempotent không |
| 502/503/504 | Có thể retry với backoff/jitter | Phải cân nhắc unknown side effect và deadline |
| Network timeout | Outcome có thể chưa xác định | Tra cứu operation/idempotency trước khi tạo tác dụng mới |

**Retry policy** cần bao gồm:

- Max attempts và total elapsed time.
- Deadline propagation và remaining budget.
- Exponential backoff có jitter.
- Retry budget hoặc rate limiter để tránh retry amplification.
- Điều kiện retry theo status, code và operation.
- Stable idempotency key cho thao tác ghi.
- Stop condition khi request hết deadline hoặc client hủy.
- Telemetry phân biệt original attempt, retry attempt và kết quả cuối.

Ví dụ nếu Gateway, Ordering và Inventory đều retry tối đa ba attempts cùng một thao tác, số call sâu nhất có thể lên tới **3 × 3 × 3 = 27** trong tình huống xấu. Hãy chọn lớp sở hữu retry chính, không nhân retries tự phát qua mỗi hop.

## 18. Timeout không đồng nghĩa giao dịch đã thất bại

Xét lệnh tạo thanh toán:

~~~text
1. Ordering gửi Payment.authorize(operationId=op-827).
2. Payment chuyển request tới Provider.
3. Provider đã authorize thành công.
4. Đường mạng mất response.
5. Ordering hết timeout.
~~~

Nếu Ordering trả “PAYMENT_FAILED” và cho tạo một authorization mới ngay, có thể gây thanh toán hoặc giữ tiền trùng. Hành vi đúng cần phân biệt:

- **Kết quả confirmed success**: giao dịch đã được xác nhận.
- **Confirmed decline/failure**: provider đã từ chối hoặc bảo đảm không xử lý.
- **UNKNOWN/PENDING**: request có thể đã được xử lý; cần tra cứu bằng idempotency key/operation ID.

Hợp đồng có thể cho người dùng tra cứu operation, nhận trạng thái PENDING và cập nhật sau. Nếu API cam kết synchronous final result, cần thiết kế deadline và cách xử lý unknown outcome từ đầu; không thể loại bỏ rủi ro chỉ bằng HTTP status.

**HTTP 504 mô tả ranh giới giao tiếp, không phải kết quả cuối của một giao dịch có side effect.** Structured error có thể đưa operationId hoặc statusUrl nếu đã có bản ghi được lưu bền, giúp consumer không phải đoán.

~~~http
HTTP/1.1 202 Accepted
Location: /operations/op-827
Content-Type: application/json

{
  "operationId": "op-827",
  "status": "PENDING_RECONCILIATION",
  "statusUrl": "/operations/op-827"
}
~~~

Chỉ trả 202 khi server thực sự đã nhận và quản lý operation theo contract; không tùy ý đổi lỗi network thành 202 khi chưa biết yêu cầu đã được lưu.

## 19. Idempotency key và lỗi trùng yêu cầu

Idempotency bảo vệ client trước retry do mất response. Ví dụ:

~~~http
POST /payments
Idempotency-Key: pay-ord-2048-v1
Content-Type: application/json

{
  "orderId": "ord-2048",
  "amount": "850000.00",
  "currency": "VND"
}
~~~

Định nghĩa contract:

1. Scope key theo actor/tenant và operation để tránh collision giữa người dùng.
2. Gắn key với fingerprint của payload có ý nghĩa, không dùng key cũ cho intent mới.
3. Cùng key và cùng payload được replay an toàn: trả kết quả đã có hoặc trạng thái operation tương ứng.
4. Cùng key nhưng payload khác: trả lỗi xung đột, thường 409 IDEMPOTENCY_CONFLICT.
5. Hai request cùng key đến đồng thời phải được điều phối atomic; không chạy hai side effects.
6. Có thời hạn lưu key, mô tả hành vi khi hết hạn và cách client tra cứu trạng thái.
7. Khi downstream có thể xử lý thành công nhưng response mất, cần idempotency/lookup ở provider hoặc reconciliation.

Một mã lỗi cấu trúc cần phân biệt **IDEMPOTENCY_CONFLICT** với **ORDER_STATE_CONFLICT** dù cả hai có thể trả 409. Consumer của hai lỗi này phải xử lý khác nhau.

## 20. Thiết kế Java/Spring Boot: Domain exception thành Problem Details

Ví dụ minh họa dùng Java 21 và Spring Boot 3.x với Spring MVC. Mục tiêu là tách domain exception ra khỏi HTTP layer và giữ phản hồi public an toàn.

~~~java
package com.example.ordering.api;

public final class OrderStateConflictException extends RuntimeException {
    private final String orderId;

    public OrderStateConflictException(String orderId) {
        super("Order is not in a submittable state");
        this.orderId = orderId;
    }

    public String orderId() {
        return orderId;
    }
}
~~~

Trong domain/application service, kiểm tra state trước khi submit:

~~~java
public void submit(String orderId, String actorId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    authorizationPolicy.requireCanSubmit(actorId, order);

    if (!order.canSubmit()) {
        throw new OrderStateConflictException(orderId);
    }

    order.submit();
    orderRepository.save(order);
}
~~~

Tùy yêu cầu concurrency, phải dùng optimistic locking, transaction và idempotency. Đoạn này chỉ trình bày chỗ phát sinh lỗi nghiệp vụ.

### @RestControllerAdvice ánh xạ sang ProblemDetail

~~~java
package com.example.ordering.api;

import jakarta.servlet.http.HttpServletRequest;
import java.net.URI;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public final class ApiErrorHandler {

    @ExceptionHandler(OrderStateConflictException.class)
    public ResponseEntity<ProblemDetail> onOrderStateConflict(
            OrderStateConflictException ex,
            HttpServletRequest request) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.CONFLICT);

        problem.setType(URI.create(
                "https://api.example.test/problems/order-state-conflict"));
        problem.setTitle("Order state conflict");
        problem.setDetail("The order cannot be submitted in its current state.");
        problem.setProperty("code", "ORDER_STATE_CONFLICT");
        putDiagnosticId(problem);

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .contentType(MediaType.valueOf("application/problem+json"))
                .body(problem);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ProblemDetail> onUnexpectedError(
            Exception ex,
            HttpServletRequest request) {

        // Ghi nguyên nhân vào telemetry nội bộ có kiểm soát;
        // không đưa message/stack trace của ex ra public body.
        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);

        problem.setType(URI.create(
                "https://api.example.test/problems/internal-error"));
        problem.setTitle("Internal server error");
        problem.setDetail(
                "The request could not be completed at this time.");
        problem.setProperty("code", "INTERNAL_ERROR");
        putDiagnosticId(problem);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .contentType(MediaType.valueOf("application/problem+json"))
                .body(problem);
    }

    private void putDiagnosticId(ProblemDetail problem) {
        // Chỉ có giá trị khi observability đã cài đặt MDC đúng cách.
        String traceId = MDC.get("traceId");
        if (traceId != null && !traceId.isBlank()) {
            problem.setProperty("traceId", traceId);
        }
    }
}
~~~

Đây là mẫu ánh xạ, **không phải bộ xử lý lỗi production hoàn chỉnh**. Cần bổ sung handler cho validation, authentication/authorization, optimistic lock, rate limit, upstream failure; sử dụng một global logging policy để tránh nuốt lỗi hoặc log lặp; có thể dùng Spring Security exception handling ở đúng tầng của security filter chain. Tham số request trong ví dụ là nơi có thể nhận thông tin đã được gateway/filer chuẩn hóa; có thể bỏ nếu không dùng.

Không gửi trực tiếp **ex.getMessage()** ra public đối với exception chưa được phân loại. Detail của lỗi hệ thống có thể lộ SQL, hostname hoặc tên lớp nội bộ.

### Cân nhắc xử lý lỗi framework

Các lỗi parse JSON, binding và Bean Validation thường được Spring MVC phát sinh trước khi application use case chạy. Có thể xây trên ResponseEntityExceptionHandler và override các phương thức liên quan để giữ cùng Problem Details shape. Không nên bắt Exception rồi trả 500 cho cả MethodArgumentNotValidException nếu cần trả 400/422; đảm bảo exception có handler cụ thể được ưu tiên.

Với Spring WebFlux, dùng kiểu exception handling phù hợp reactive stack; không sao chép trực tiếp Servlet API và HttpServletRequest.

## 21. Ví dụ Java: validation lỗi từng trường

Giả sử dùng Jakarta Bean Validation:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record OrderItemRequest(
        @NotBlank String sku,
        @Min(1) int quantity
) {}
~~~

Controller:

~~~java
@PostMapping("/orders")
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
            .body(createOrderUseCase.execute(request));
}
~~~

Các annotation và type cần được import/cấu hình theo ứng dụng thực tế, ví dụ có dependency validation starter. Khi request không đạt, handler có thể chuyển BindingResult thành invalidParams:

~~~java
@ExceptionHandler(MethodArgumentNotValidException.class)
public ResponseEntity<ProblemDetail> onValidation(
        MethodArgumentNotValidException ex) {

    ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
    problem.setType(URI.create(
            "https://api.example.test/problems/validation-failed"));
    problem.setTitle("Validation failed");
    problem.setDetail("One or more request fields are invalid.");
    problem.setProperty("code", "INPUT_VALIDATION_FAILED");

    var fields = ex.getBindingResult().getFieldErrors().stream()
            .map(error -> Map.of(
                    "name", error.getField(),
                    "code", error.getCode() == null
                            ? "INVALID_VALUE" : error.getCode()))
            .toList();
    problem.setProperty("invalidParams", fields);

    return ResponseEntity.badRequest()
            .contentType(MediaType.valueOf("application/problem+json"))
            .body(problem);
}
~~~

Đoạn minh họa này cần import tương ứng cho **Map**, **MethodArgumentNotValidException**, **ProblemDetail**, **HttpStatus**, **URI**, **MediaType**, **ResponseEntity** và **ExceptionHandler** khi đưa vào code thực. Nó dùng 400 cho lỗi binding/validation; nếu contract chọn 422 cho semantic validation thì phải phân loại rõ parse error (400) và domain rule (422), đồng thời sửa status trong handler phù hợp.

Đừng dùng rejectedValue từ Bean Validation để trả lại cho client khi có thể chứa dữ liệu nhạy cảm. Cũng không nên gửi thông báo raw từ validator nếu nội dung chưa được kiểm soát.

## 22. Thiết kế API client xử lý lỗi có cấu trúc

Caller không nên coi mọi non-2xx là một exception duy nhất không có ngữ nghĩa. Cần tách:

- **HTTP response failure:** server đã phản hồi một status và có thể có Problem Details.
- **Network failure:** không nhận được HTTP response (DNS, connection reset, timeout).
- **Decode/contract failure:** response không parse được, Content-Type không phù hợp.
- **Business result:** response thành công ở HTTP nhưng mô tả DECLINED/PENDING theo workflow.

Pseudocode:

~~~text
response = httpClient.send(request, deadline)

if response.is2xx:
    parse documented success schema
    return business outcome

if content-type is application/problem+json:
    parse safe fields: type, status, code, requestId
else:
    synthesize a local UNKNOWN_REMOTE_ERROR with observed status

switch code/status:
    INPUT_VALIDATION_FAILED -> ask caller to fix input
    RESOURCE_VERSION_MISMATCH -> fetch latest version
    ORDER_STATE_CONFLICT -> show current permitted actions
    RATE_LIMIT_EXCEEDED -> consider bounded wait/retry
    DEPENDENCY_UNAVAILABLE -> retry only if operation is safe
    otherwise -> surface generic failure and diagnostic ID

if no response:
    classify transport failure; for side effect, outcome may be unknown
~~~

**Không parse chuỗi detail** để làm logic. Detail có thể đổi ngôn ngữ hoặc cách diễn đạt. Cũng cần xử lý server cũ chưa hỗ trợ Problem Details; client không được crash chỉ vì body 502 trống hoặc proxy trả HTML error page.

## 23. Retry-After, deadline và thông tin retryable

Một số API bổ sung extension **retryable** hoặc **retryAfterMs**. Khi đã có HTTP Retry-After, nên ưu tiên chuẩn đó cho các status phù hợp. Extension riêng cần định nghĩa và kiểm thử, tránh mâu thuẫn.

Retry là phép quyết định có điều kiện:

~~~text
mayRetry =
    errorIsTransient
    AND operationRetrySafe
    AND idempotencyProtectedIfSideEffect
    AND attemptsRemaining > 0
    AND deadlineRemaining > backoff + expectedCallTime
    AND retryBudgetAvailable
~~~

Trường retryable=true không có nghĩa client chắc chắn nên retry. Ví dụ response 503 có retryable=true nhưng deadline người dùng chỉ còn 50 ms; gọi lại một dependency thường mất 300 ms sẽ làm tình hình tệ hơn.

Đặc biệt với 504, cần biết **lỗi xảy ra ở layer nào** và liệu side effect có thể đã được thực thi. Trong thanh toán, tra cứu kết quả theo stable operation ID có thể an toàn hơn lặp POST.

## 24. Logging và status theo mức độ nghiêm trọng

Không phải mọi status 4xx là lỗi production nghiêm trọng:

| Tình huống | Mức log gợi ý | Lý do |
|---|---|---|
| 400 JSON sai | INFO hoặc metrics | Lỗi request thường gặp, tránh log payload nhạy cảm |
| 401/403 | INFO/WARN theo chính sách an ninh | Cần phát hiện abuse nhưng hạn chế spam |
| 404 resource không tồn tại | DEBUG/INFO | Không phải outage nếu dự kiến |
| 409 state conflict | INFO | Một kết quả nghiệp vụ bình thường |
| 412 stale ETag | INFO hoặc metrics | Concurrent update dự kiến |
| 429 quota | INFO/WARN theo quy mô | Theo dõi limit và retry storm |
| 503 load shedding | WARN/ERROR khi ảnh hưởng SLO | Tín hiệu capacity hoặc dependency |
| 500 bug | ERROR với stack trace nội bộ có kiểm soát | Cần điều tra root cause |
| 504 upstream timeout | WARN/ERROR theo tác động | Phân tích latency, retry và dependency |

Level là policy gợi ý; mức độ nghiêm trọng phải dựa vào SLO, lượng request và tác động người dùng. Một làn sóng 401 bất thường có thể là sự cố authentication, một đợt 404 dồn dập có thể là bot scan, một 409 có thể bình thường trong concurrency. Vì vậy đừng cứng nhắc “mọi 4xx không đáng cảnh báo” hoặc “mọi 5xx đều page lập tức”.

### Không log lặp ở mọi tầng

Khi Inventory thất bại, Inventory nên log nguyên nhân kỹ thuật. Ordering có thể log rằng ReserveStock thất bại với traceId, dependency và mã lỗi đã chuẩn hóa. Gateway có metrics status và request trace. Nếu cả ba log cùng một stack trace đầy đủ cho mỗi retry, dữ liệu trở nên nhiễu và tốn kém.

Dùng một policy sở hữu logging: nơi phát sinh ghi nguyên nhân, nơi chuyển đổi ghi mapping và context; tracing nối chúng lại.

## 25. Metrics, SLI/SLO và error budget

Error body tốt vẫn cần telemetry. Với mỗi API quan trọng nên có:

- Tổng request, kết quả và latency histogram theo route template, method, HTTP status family.
- Tỷ lệ request đạt business success theo định nghĩa SLI, không chỉ tỷ lệ 2xx.
- Tỷ lệ 4xx theo error code để thấy vấn đề UX/consumer nhưng không tự động tính mọi 4xx là platform outage.
- Tỷ lệ 5xx/timeout, availability theo hành trình và dependency.
- Retry attempts, backoff, load shedding, circuit breaker open.
- Upstream latency, connection pool wait, queue time.
- Số operation UNKNOWN/PENDING quá lâu và tỷ lệ reconciliation hoàn tất.
- Số error code mới/bất ngờ sau deploy và breaking contract incidents.

Ví dụ một SLO:

~~~text
SLO: 99.9% checkout requests hợp lệ nhận được kết quả
     đúng hợp đồng trong cửa sổ 30 ngày.

Numerator:
  số request hợp lệ hoàn tất đúng hợp đồng trong deadline.

Denominator:
  toàn bộ request hợp lệ theo chính sách (ghi rõ exclusions).

Error budget:
  0.1% denominator có thể không đạt.
~~~

Nếu có 1.000.000 request hợp lệ, error budget là **1.000 request**. Không thể kết luận “đạt SLO” chỉ vì API trả 200 trong lúc business operation thật sự đang thất bại hoặc bị treo.

**Error budget burn rate** có thể hỗ trợ cảnh báo tốc độ tiêu thụ lỗi. Không nên đưa raw requestId, userId hay orderId vào metric labels vì cardinality cao. Chúng phù hợp log/trace có kiểm soát hơn.

## 26. Security và giới hạn công bố diagnostic data

Thông tin hỗ trợ chẩn đoán vừa hữu ích vừa có thể trở thành kênh rò rỉ thông tin.

**Không công khai**:

- Stack trace, đường dẫn mã nguồn, class name nội bộ, câu SQL.
- Hostname, IP nội bộ, URI database, bucket/path nhạy cảm, thông tin deployment.
- Token, cookie, session ID, API key, password, secret, private key.
- Nội dung thanh toán, số thẻ, PII hoặc thông tin resource tenant khác.
- Toàn bộ payload upstream hay response từ nhà cung cấp.
- Chính sách phân quyền chi tiết đủ để kẻ tấn công suy ra tài nguyên.

**Có thể công khai có kiểm soát**:

- HTTP status, type và code ổn định.
- Title/detail an toàn cho người dùng.
- Request ID để liên hệ hỗ trợ.
- Trường field validation không chứa giá trị nhạy cảm.
- Retry-After với giới hạn hợp lý.
- StatusUrl/operationId nếu actor có quyền tra cứu.

Áp dụng access control và tenancy nhất quán cho API tra cứu operation. Một operationId có entropy cao không tự thay thế authorization. Nếu dùng đường instance URL trong Problem Details, tránh đưa số ID nhạy cảm hoặc query chứa token vào URI công khai.

### Không tin tuyệt đối vào incoming correlation headers

Gateway có thể nhận X-Request-ID/traceparent từ client, nhưng cần validate kích thước, định dạng, mức tin cậy và policy sampling. Nếu cho phép input tùy ý chảy vào log, kẻ tấn công có thể chèn dòng giả, tăng chi phí observability hoặc gây nhầm truy vết. Có thể phát hành ID mới ở ranh giới public và nối với trace context đáng tin sau khi kiểm tra.

## 27. Thiết kế taxonomy lỗi xuyên các service

Tổ chức cần phân biệt hai phạm vi:

1. **Global technical error codes:** ví dụ INTERNAL_ERROR, RATE_LIMIT_EXCEEDED, DEPENDENCY_UNAVAILABLE, REQUEST_MALFORMED.
2. **Domain-specific error codes:** ví dụ ORDER_STATE_CONFLICT, INVENTORY_RESERVATION_REJECTED, PAYMENT_AUTHORIZATION_DECLINED.

Không buộc mọi service đưa toàn bộ enum domain vào một thư viện Java dùng chung vì việc phát hành và triển khai có thể bị coupling. Có thể chuẩn hóa shape và các quy tắc của error codes ở contract/catalog, trong khi mỗi bounded context sở hữu mã nghiệp vụ riêng.

Mỗi error type/code nên có:

| Thuộc tính | Nội dung |
|---|---|
| Code/type | Định danh máy ổn định |
| Owner | Team hoặc bounded context chịu trách nhiệm |
| Meaning | Điều kiện phát sinh cụ thể |
| HTTP status | Giá trị thường dùng và biến thể được phép |
| Retry policy | Không retry / retry điều kiện nào |
| Client guidance | Sửa input, reload, authenticate, poll, contact support |
| Security class | Trường nào có thể công bố |
| Schema | Extension members và kiểu dữ liệu |
| Observability | Log/metric cần ghi |
| Version/deprecation | Quy tắc thay đổi, lịch sunset |

Tài liệu type URI nên dễ tra cứu. Nếu quyết định đổi ý nghĩa của một code, cân nhắc code mới và migration để không phá consumer.

## 28. OpenAPI: công bố response lỗi như một phần contract

OpenAPI cần mô tả status mà endpoint có thể trả, media type và schema lỗi. Ví dụ rút gọn:

~~~yaml
openapi: 3.0.3
info:
  title: Ordering API
  version: 1.0.0
paths:
  /v1/orders/{orderId}/submit:
    post:
      operationId: submitOrder
      summary: Submit an order
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
        - name: Idempotency-Key
          in: header
          required: true
          schema:
            type: string
      responses:
        "202":
          description: Command accepted; track operation status
        "409":
          description: Order state or idempotency conflict
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
        "422":
          description: Invalid business input
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
        "503":
          description: Required dependency unavailable
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
        "500":
          description: Unexpected server error
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
components:
  schemas:
    ApiProblem:
      type: object
      required: [type, title, status, code]
      properties:
        type:
          type: string
          format: uri
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        instance:
          type: string
          format: uri-reference
        code:
          type: string
        requestId:
          type: string
        retryable:
          type: boolean
~~~

Đây là **mẫu rút gọn**, chưa liệt kê hết auth, validation, schema thành công hoặc 404/412/429/502/504. Một API production cần bổ sung những response thật sự có thể xảy ra và ví dụ tương ứng.

Đừng chỉ viết response "default: error" cho tất cả tình huống nếu client có logic khác nhau theo 409, 412, 429 hoặc 503. Contract tests cần xác nhận media type, status, schema và code mapping sau khi triển khai.

## 29. Kiểm thử contract lỗi có hệ thống

Thêm các ca kiểm thử cho endpoint và chuỗi dependency, không chỉ happy path.

| Test | Điều cần xác minh |
|---|---|
| JSON sai cú pháp | 400, Problem Details có code rõ, không lộ parser stack |
| Validation field | 400/422 theo contract, invalidParams đúng schema |
| Không có token | 401 và authentication challenge thích hợp |
| Actor khác tenant | 403/404 theo policy, không tiết lộ dữ liệu |
| Order state xung đột | 409 đúng domain code, không thay đổi dữ liệu |
| ETag cũ | 412 và resource không bị ghi đè |
| Cùng idempotency key cùng payload | Không tạo side effect thứ hai |
| Cùng key khác payload | 409 IDEMPOTENCY_CONFLICT |
| Quota vượt | 429, Retry-After hợp lệ khi được cung cấp |
| Inventory không kết nối được | 5xx đúng mapping, trace/log nối được |
| Inventory trả 401 nội bộ | Không biến thành 401 yêu cầu client login lại |
| Provider timeout sau side effect | UNKNOWN/PENDING hoặc lookup/reconciliation đúng |
| Gateway upstream timeout | 504 và request ID để điều tra |
| Exception bất ngờ | 500, public detail an toàn, log có nguyên nhân |
| Upstream trả HTML error page | Client adapter không crash khi parse JSON |
| Consumer phiên bản cũ | Tolerate extension mới, code không đổi nghĩa |
| Load/retry storm | Retry không vượt deadline/budget; pool không cạn vô hạn |

### Consumer-driven contract testing

Một consumer có thể dựa vào code RESOURCE_VERSION_MISMATCH để tải lại đơn; nếu provider đổi thành INTERNAL_ERROR, client có thể không còn xử lý đúng. Contract tests phải bao phủ cả các error outcomes consumer dùng, không chỉ JSON success schema.

Có thể dùng mock/stub downstream để mô phỏng timeout, 429, 503, 409 hoặc response lỗi hỏng; tích hợp thực tế kiểm tra thêm security, tracing, header propagation và cấu hình gateway.

## 30. Kịch bản thực hành: truy nguyên lỗi SubmitOrder

Giả sử người dùng gọi:

~~~http
POST /orders/ord-2048/submit
Idempotency-Key: submit-ord-2048-v1
X-Request-ID: req-ef631
~~~

Ordering gọi Inventory.reserveStock, rồi Payment.authorize.

### Tình huống A: Inventory hết hàng

Inventory trả 409 INVENTORY_INSUFFICIENT_STOCK. Ordering hiểu đây là kết quả nghiệp vụ và trả mã công khai:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
X-Request-ID: req-ef631

{
  "type": "https://api.example.test/problems/order-stock-unavailable",
  "title": "Order cannot be submitted",
  "status": 409,
  "code": "ORDER_STOCK_UNAVAILABLE",
  "detail": "One or more items are no longer available.",
  "requestId": "req-ef631"
}
~~~

Consumer hiển thị yêu cầu điều chỉnh giỏ. Không retry cùng request vô hạn vì Inventory đã xác nhận không đủ hàng.

### Tình huống B: Payment Provider mất response

Provider có thể đã authorize thành công, nhưng Payment trả timeout hoặc trạng thái UNKNOWN. Ordering không được trả “Payment declined” nếu chưa xác định.

Một phương án là đã lưu bền workflow và trả 202 với statusUrl, rồi hệ thống tiếp tục tra cứu/reconcile. Một phương án khác là trả lỗi tạm với operationId có thể tra cứu theo hợp đồng, nếu server bảo đảm tra cứu được. Điểm quan trọng: **không cho client tạo tác vụ trùng khi outcome chưa rõ**.

### Tình huống C: token service-to-service hết hạn

Ordering gọi Inventory nhưng token nội bộ không hợp lệ. Inventory trả 401. Lỗi thuộc vận hành/identity giữa service; Ordering không trả nguyên 401 cho customer đã xác thực đúng. Ghi dependency, error code, trace ID; trả lỗi 5xx thích hợp và phát cảnh báo nếu ảnh hưởng SLO.

### Tình huống D: user đã submit trên thiết bị khác

Order từ DRAFT chuyển PENDING_PAYMENT. Thiết bị thứ hai gửi submit với version cũ. Ordering trả 412 hoặc 409 theo contract. Client đọc lại order, không tự động submit trên trạng thái mới mà chưa có sự xác nhận người dùng.

### Tình huống E: retry gây timeout hàng loạt

Inventory 503 do quá tải; Ordering retry ba lần, Gateway cũng retry ba lần, và Mobile lại retry ba lần. Một request người dùng có thể làm tăng mạnh lưu lượng. Cần sở hữu retry ở một tầng, có deadline, jitter, retry budget, load shedding và metrics. Status 503 với retryable=true không thay thế chính sách đó.

## 31. Bài tập: phân loại và thiết kế lỗi

**Bối cảnh:** endpoint POST /v1/orders/{id}/cancel có các khả năng:

1. JSON request sai cú pháp.
2. Người dùng chưa đăng nhập.
3. Người dùng biết ID đơn của người khác.
4. Đơn đã giao thành công.
5. Client gửi If-Match của phiên bản cũ.
6. Quá nhiều yêu cầu trong thời gian ngắn.
7. Payment refund provider timeout sau khi có thể hoàn tiền.
8. Code trong Ordering ném NullPointerException bất ngờ.

**Yêu cầu:** chọn status, code, public detail, client action và diagnostic context cho từng case.

### Gợi ý giải

| Tình huống | Mã gợi ý | Code | Client action |
|---|---:|---|---|
| JSON hỏng | 400 | REQUEST_MALFORMED | Sửa request |
| Chưa xác thực | 401 | UNAUTHENTICATED | Thực hiện authentication |
| Đơn người khác | 403 hoặc 404 theo policy | RESOURCE_FORBIDDEN / ORDER_NOT_FOUND | Dừng, không tiết lộ thêm |
| Đơn đã giao | 409 | ORDER_CANCELLATION_NOT_ALLOWED | Hiển thị chính sách return/refund |
| If-Match cũ | 412 | RESOURCE_VERSION_MISMATCH | Đọc lại trạng thái |
| Vượt quota | 429 | RATE_LIMIT_EXCEEDED | Chờ có giới hạn |
| Refund timeout chưa rõ | Không tuyên bố FAILED | REFUND_OUTCOME_UNKNOWN hoặc operation PENDING | Tra cứu/đối soát, tránh hoàn tiền trùng |
| Bug bất ngờ | 500 | INTERNAL_ERROR | Gửi requestId để hỗ trợ |

Dù response public tối giản, nội bộ cần log theo traceId, dependency, operationId, exception class/stack được bảo vệ. Với refund timeout, việc lựa chọn 202 hay 5xx phụ thuộc liệu workflow đã được lưu và được hợp đồng hỗ trợ tra cứu; không được tùy tiện dùng 202.

## 32. Bảng mẫu phân loại và vận hành lỗi cho service

Một error catalog thực hành có thể tổ chức như sau:

| Cột | Diễn giải |
|---|---|
| API | Method và route template |
| Business action | Hành vi và expected outcome |
| HTTP status | Mã theo semantics đã công bố |
| Type URI | Định danh loại vấn đề |
| Stable code | Mã máy phục vụ logic client |
| Detail policy | Thông tin public an toàn |
| Retry guidance | Điều kiện an toàn, attempts và backoff |
| Idempotency | Key, scope, fingerprint, retention |
| Diagnostics | requestId, traceId, operationId, dependency |
| Logging | Level, nơi log root cause, redaction |
| Metrics/SLO | SLI và error budget được ảnh hưởng |
| Test cases | Contract, concurrency, timeout, upstream failure |
| Owner | Team duy trì contract và phản hồi incident |
| Version policy | Nguyên tắc deprecation và migration |

Mỗi khi thêm một mã lỗi mới, cần xác định client sẽ làm gì; không chỉ thêm chuỗi code vào enum để thuận tiện log. Lỗi nào không có tác động consumer có thể giữ hoàn toàn trong log/telemetry nội bộ.

## 33. Checklist trước khi phát hành HTTP API

### HTTP semantics và business contract

- [ ] Mỗi endpoint phân biệt success, accepted, failure và unknown outcome.
- [ ] 201/202/204 được dùng đúng ý nghĩa, không báo thành công khi workflow mới bắt đầu.
- [ ] 400/422/409/412 được phân biệt rõ theo validation, state conflict và precondition.
- [ ] 401 không bị dùng cho lỗi credential của service nội bộ khi client đã xác thực đúng.
- [ ] 404/403 tuân thủ chính sách bảo vệ thông tin resource.
- [ ] 429/503 có retry guidance hợp lý, giới hạn tải và backoff.
- [ ] 502/504 phản ánh lỗi gateway/upstream theo vai trò thực tế.
- [ ] Domain outcome được mô tả riêng, không ép mọi business rejection vào 500.

### Structured error response

- [ ] Dùng application/problem+json hoặc một contract lỗi thống nhất được công bố.
- [ ] type/title/status/detail/instance có semantics ổn định; status body và HTTP khớp nhau.
- [ ] Có code ổn định phục vụ consumer, không parse detail tự do.
- [ ] Validation có field codes/paths an toàn và không echo dữ liệu nhạy cảm.
- [ ] Lỗi bất ngờ không lộ stack trace, DB schema, token hay internal URLs.
- [ ] Tài liệu lỗi và OpenAPI cập nhật, có contract tests.
- [ ] Localization không làm đổi machine-readable codes.
- [ ] Mã lỗi có owner và chính sách version/deprecation.

### Diagnostics, retry và vận hành

- [ ] Có requestId hoặc traceId đủ để nối response với log/trace.
- [ ] Có correlation/operation ID cho workflow dài và trạng thái chưa xác định.
- [ ] Log ghi root cause ở nơi phù hợp, tránh nhân stack trace mọi tầng.
- [ ] Metrics dùng route template/status/code với cardinality được kiểm soát.
- [ ] Có phân loại lỗi theo ảnh hưởng SLO và alert phù hợp.
- [ ] Retry tuân thủ deadline, idempotency, backoff/jitter và retry budget.
- [ ] Timeout sau side effect được xử lý bằng lookup/reconciliation thay vì retry mù.
- [ ] Đã thử upstream 401/404/429/503/504 và malformed error body.
- [ ] Telemetry có redaction, retention và kiểm soát quyền truy cập.
- [ ] Error mapping xuyên service đã được kiểm thử ở gateway và service boundary.

## 34. Kết luận thực hành

Trong giao tiếp đồng bộ của Microservices, **HTTP status phân loại kết quả ở ranh giới API; structured error cho consumer biết lỗi thuộc loại nào và phải xử lý ra sao; diagnostic IDs nối sự cố với log, metrics và traces**. Ba lớp này phải thống nhất nhưng phục vụ những người dùng khác nhau: application client, domain owner và đội vận hành.

Một thiết kế vững cần hiểu business outcome trước khi chọn status, giữ mã lỗi máy ổn định, dùng Problem Details và không để lộ nội bộ. Khi request đi qua nhiều service, cần chuyển đổi lỗi theo trách nhiệm hiện tại; timeout không tự chứng minh side effect đã thất bại; retry phải gắn với deadline và idempotency. Những quy tắc ấy giúp hệ thống vừa dễ tích hợp, vừa an toàn với dữ liệu, vừa có thể điều tra và khôi phục khi lỗi phân tán xảy ra.
