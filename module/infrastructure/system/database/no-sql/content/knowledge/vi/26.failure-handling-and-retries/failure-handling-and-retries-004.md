# Phân loại lỗi có thể thử lại và lỗi cần sửa đầu vào/quyền

Trong một ứng dụng sử dụng **NoSQL phân tán**, một request ghi dữ liệu có thể thất bại vì vô số nguyên nhân: node leader vừa chuyển quyền, replica chưa bắt kịp, network mất kết nối, transaction bị xung đột, hệ thống đang throttle, token xác thực đã hết hạn, schema đầu vào sai, người dùng không có quyền, hoặc điều kiện nghiệp vụ không còn đúng.

Các lỗi ấy **không nên xử lý bằng cùng một câu lệnh `retry()`**. Nếu một lỗi do mạng tạm thời, thử lại có giới hạn có thể hoàn thành công việc. Nếu dữ liệu gửi lên không hợp lệ, lặp lại nguyên request chỉ làm tốn tài nguyên. Nếu user không có quyền truy cập tenant, tự retry nhiều lần không giúp gì và còn có thể tạo sự cố bảo mật. Nguy hiểm nhất là trường hợp **server đã commit nhưng response bị mất**: client thấy timeout, thử lại một mutation không có idempotency và vô tình ghi lần thứ hai.

Ví dụ một API đặt hàng:

~~~text
POST /reservations
  commandId = reserve-8821
  sku = SKU-A
  quantity = 2

Lần 1:
  Database commit giảm tồn kho 2 đơn vị.
  Leader bị ngắt kết nối trước khi trả response.
  Client thấy timeout.

Lần 2:
  Client gửi lại "giảm tồn kho 2" như lệnh mới.
  Database commit giảm thêm 2 đơn vị.

Một ý định của người dùng => tồn kho bị trừ 4.
~~~

Lỗi trong ví dụ không phải vì NoSQL không đủ mạnh để ghi nguyên tử một document. Lỗi nằm ở **ngữ nghĩa retry của ứng dụng**. Một transaction có thể hoàn toàn đúng và durable, nhưng lời gọi qua mạng vẫn có kết quả **không xác định đối với client**.

Bài học thuộc chương **Lỗi phân tán và retry** sẽ hướng dẫn phân loại lỗi thành nhóm có thể thử lại, nhóm phải sửa đầu vào/quyền hoặc điều kiện nghiệp vụ, và nhóm cần **đối soát trước khi quyết định thử lại**. Chúng ta sẽ xây quy tắc theo thao tác, minh họa qua nhiều API NoSQL, viết Java retry policy có ranh giới rõ và thiết kế kiểm thử lỗi có chủ đích.

> **Giới hạn:** Mã HTTP, gRPC, exception class, error label và cách SDK tự retry khác nhau theo sản phẩm, phiên bản, operation và cấu hình. Các bảng bên dưới là **khung suy luận**, không phải danh sách cho phép retry vô điều kiện. Luôn đối chiếu hợp đồng của API và retry guidance của nhà cung cấp cho deployment thực tế.

## 1. Mục tiêu của phân loại lỗi

Một error handler tốt phải trả lời được:

1. **Có biết request đã được commit hay chưa?**
2. **Nguyên nhân có khả năng tự hết mà không đổi input/quyền không?**
3. **Thao tác có thể thực hiện lại mà không nhân đôi hiệu ứng không?**
4. **Cần retry một RPC, cả transaction, hay phải hỏi lại trạng thái?**
5. **Client còn thời gian và tài nguyên để retry hay không?**
6. **Cần phản hồi gì cho user hoặc workflow?**

### 1.1. Ba nhóm quyết định chính

| Nhóm | Bản chất | Hành động mặc định |
|---|---|---|
| **Có thể thử lại (transient/retryable)** | Một điều kiện tạm thời khiến attempt không hoàn tất; có bằng chứng/cơ chế để retry an toàn | Retry có backoff, jitter, deadline và budget |
| **Phải sửa đầu vào/quyền/điều kiện** | Request sai schema, không có quyền, tiền điều kiện sai, vi phạm business rule | Không retry nguyên request; trả lỗi rõ, sửa nguyên nhân |
| **Không rõ kết quả (ambiguous outcome)** | Server có thể đã commit, client chỉ biết response/ACK mất | Giữ commandId, đối soát tại nguồn có thẩm quyền, không nhân đôi side effect |

Một lỗi còn có thể là **terminal do hệ thống** (ví dụ tài nguyên không hỗ trợ hoặc cấu hình sai) dù input hợp lệ. Khi ấy ứng dụng nên dừng, cảnh báo vận hành và chỉ retry sau khi điều kiện nền thay đổi.

### 1.2. Retryability không chỉ là thuộc tính của mã lỗi

Hai request cùng nhận `503 Service Unavailable`:

~~~text
GET /catalog/item/42
  -> retry bounded có thể an toàn.

POST /payments/capture without idempotency key
  -> có thể charge đã xảy ra; không retry mù.
~~~

**Lỗi** và **thao tác** phải được phân loại cùng nhau. Mã trả về chỉ là một phần bằng chứng.

### 1.3. Retry an toàn không đồng nghĩa retry có ích

Một `GET` thuần đọc có thể gọi lại mà không làm biến đổi dữ liệu, nhưng nếu database mất quorum kéo dài 30 phút, gọi lại 1.000 lần không giúp hệ hồi phục. Cần deadline, backpressure, circuit breaker và quyết định dừng.

### 1.4. Quy tắc tổng quát

~~~text
Retry = lỗi tạm thời hoặc được API đánh dấu retryable
    AND operation an toàn để lặp lại
    AND commit outcome được hiểu/giải quyết đúng
    AND retry budget còn
    AND deadline còn
    AND không vi phạm rate-limit / backpressure
~~~

Chỉ một điều kiện sai là đủ để ngừng tự retry.

## 2. Vì sao phân tán tạo ra lỗi khó phân loại?

Trong một hệ nhiều replica, client có thể nói chuyện qua load balancer, driver, router, coordinator, leader, follower và transaction manager. Một request có thể được xử lý dù một trong các hop thất bại.

~~~mermaid
flowchart LR
    C["Client"] --> LB["Gateway / Load balancer"]
    LB --> DR["Driver / Router"]
    DR --> LE["Leader / Coordinator"]
    LE --> R1["Replica 1"]
    LE --> R2["Replica 2"]
    R1 --> ACK["Commit condition"]
    R2 --> ACK
~~~

### 2.1. Request chưa tới server

Nếu có bằng chứng đáng tin rằng lỗi xảy ra **trước khi request được gửi** (ví dụ local argument validation), chưa có side effect ở server. Tuy nhiên, từ một `SocketException` chung không thể tự suy request chưa rời máy.

### 2.2. Request tới server, response mất

Server có thể commit nhưng connection reset trước khi ACK tới client. Đây là ambiguous outcome.

### 2.3. Server chủ động từ chối

Nếu API trả lời có cấu trúc rằng **condition không thỏa** và operation không được thực hiện, ta có bằng chứng về business rejection. Retry nguyên request thường không phù hợp; có thể cần đọc state mới và đưa ra quyết định nghiệp vụ khác.

### 2.4. Node thay quyền

Client gửi lệnh tới leader cũ; node trả `NOT_LEADER`, `MOVED`, `STALE_EPOCH` hoặc tín hiệu tương đương theo sản phẩm. Có thể refresh topology và retry nếu chưa commit hoặc có idempotency; nhưng response mất đúng lúc chuyển quyền vẫn phải được xem là outcome có thể ambiguous.

### 2.5. Transaction xung đột

Một transaction đọc version 7 nhưng transaction khác commit version 8. Hệ có thể abort để bảo vệ isolation. Với conflict đã xác định **attempt chưa commit**, application có thể retry **toàn read–validate–write unit**, không chỉ lặp lại một lệnh `UPDATE` cũ.

## 3. Phân loại hai chiều: nguyên nhân và trạng thái commit

Không nên gói tất cả vào một enum `isRetryable=true/false`. Tốt hơn là tách **nguyên nhân** và **mức chắc chắn về kết quả**:

| Nguyên nhân | Outcome biết chắc? | Hành động |
|---|---|---|
| Validation sai | Biết bị từ chối trước mutation | Sửa input |
| Permission denied | Biết request bị từ chối theo security contract | Xác thực/cấp quyền hợp lệ |
| Document version không khớp | Biết conditional write không áp dụng | Đọc mới và đánh giá lại ý định |
| Transaction aborted do conflict | Biết attempt đó abort | Retry toàn transaction nếu còn hợp lý |
| Throttling trước khi được chấp nhận | Nếu API cam kết chưa chạy | Backoff theo quota/retry hints |
| Overloaded/temporary unavailable | Có thể được từ chối rõ hoặc không rõ | Phân biệt reject và unknown; retry có điều kiện |
| Connection lost sau khi gửi write | Không biết | Query commandId / reconcile |
| Timeout khi commit | Không biết | Không mặc định abort; tra outcome |
| Storage configuration invalid | Biết cấu hình không hợp lệ | Sửa deployment/config |

### 3.1. Đề xuất mô hình trạng thái

~~~mermaid
flowchart TD
    E["Nhận lỗi / timeout"] --> O{"Đã biết commit outcome?"}
    O -->|"Committed"| RET["Trả kết quả đã commit / dedupe"]
    O -->|"Unknown"| REC["Resolve bằng stable commandId"]
    O -->|"Known abort/reject"| CAUSE{"Nguyên nhân?"}
    CAUSE -->|"Validation / permission / business"| STOP["Dừng và sửa điều kiện"]
    CAUSE -->|"Transient + retryable"| SAFE{"Operation + budget an toàn?"}
    CAUSE -->|"Permanent system/config"| ALERT["Dừng, báo vận hành"]
    SAFE -->|"Có"| BACK["Backoff / jitter / retry đúng scope"]
    SAFE -->|"Không"| PENDING["Trả lỗi hoặc PENDING rõ ràng"]
~~~

### 3.2. `UNKNOWN` là trạng thái tri thức của client

Không có nghĩa database lưu một transaction đang ở trạng thái `UNKNOWN`. Server có thể đã commit dứt khoát; chỉ client mất bằng chứng. Phải truy vấn **nguồn authoritative** hoặc tiếp tục protocol commit của SDK đúng hướng dẫn.

### 3.3. Kết quả có thể đổi theo thời gian

Một retryable `503` có thể là tạm thời khi failover 3 giây, nhưng nếu hệ thiếu quorum nhiều giờ, nó trở thành vấn đề vận hành chứ không phải thứ nên thử mãi. Phân loại retryable là **cho phép thử có giới hạn**, không hứa sẽ thành công.

## 4. Nhóm lỗi cần sửa đầu vào

Những lỗi này thường không tự biến mất khi gửi lại nguyên payload:

- JSON/BSON/document sai cú pháp hoặc kiểu dữ liệu.
- Thiếu field bắt buộc, sai enum hoặc sai schema version.
- ID/partition key không hợp lệ theo API.
- Kích thước document, request hoặc transaction vượt giới hạn.
- TTL, timestamp, index expression hoặc filter không hợp lệ.
- Giá trị không thỏa validation, min/max/range/domain rule.
- Lệnh truy vấn không được hỗ trợ trong loại transaction hiện tại.
- Dữ liệu mã hóa hoặc serializer tạo object không tương thích.

### 4.1. Ví dụ schema

~~~json
{
  "tenantId": "tenant-A",
  "quantity": -3,
  "orderId": "O-100"
}
~~~

Nếu yêu cầu `quantity > 0`, gửi lại cùng payload 5 lần vẫn sai. Handler nên trả lỗi có thông tin field/constraint phù hợp, không tạo retry storm.

### 4.2. Validation cần ở nhiều tầng

Validation ở client giảm request vô ích, nhưng database/service vẫn cần enforce invariant vì client có thể bypass, bị lỗi hoặc gửi dữ liệu độc hại. Không tin rằng request “đã validate ở frontend” thì mọi mutation an toàn.

### 4.3. Một số lỗi “sai đầu vào” cần migration, không sửa request

Nếu schema giữa các phiên bản đã lệch, một request cũ hợp lệ theo API v1 có thể không còn tương thích v2. Khi ấy cần version contract, migration/backward compatibility; lặp lại vẫn vô ích.

### 4.4. Error message phải không làm lộ dữ liệu

Trả `INVALID_FIELD` có thể hữu ích; trả toàn bộ database query, secrets, hash nội bộ hoặc thông tin tài khoản tenant khác có thể gây lộ dữ liệu. Phân loại lỗi rõ nhưng vẫn cần nguyên tắc bảo mật.

## 5. Nhóm lỗi xác thực và phân quyền

**Authentication** xác định ai đang gọi. **Authorization** xác định chủ thể đó được phép thực hiện thao tác nào trên tài nguyên nào.

Ví dụ:

~~~text
UNAUTHENTICATED:
    access token không có / hết hạn / sai.

PERMISSION_DENIED:
    principal hợp lệ nhưng không có quyền WRITE Order.

TENANT_SCOPE_DENIED:
    principal thuộc tenant-A nhưng đang đòi đọc tenant-B.
~~~

### 5.1. Không retry lặp lại cùng credential sai

Nếu token không hợp lệ hoặc user không có quyền, lặp request nguyên trạng không giải quyết. Cần login/refresh token theo quy trình hợp lệ hoặc yêu cầu cấp quyền đúng.

### 5.2. Token hết hạn là ngoại lệ có kiểm soát

Một `401` do token hết hạn có thể xử lý bằng **refresh credential một lần**, rồi thử lại request **nếu request an toàn để retry**. Nếu request mutation đã đến server và outcome không rõ, refresh token không làm mất vấn đề idempotency.

### 5.3. `403` không phải tín hiệu retry cho tới khi được chấp thuận

Không nên tự brute-force bằng cách đổi account, scope hoặc tenantId cho đến khi được phép. Nếu quyền mới được admin cấp, request mới có thể hợp lệ sau cập nhật quyền/cache, nhưng đó là **thay đổi điều kiện quyền**, không phải tự retry lỗi cũ.

### 5.4. Thiếu quyền trên hệ thống nội bộ

Service account bị thiếu role đọc collection hoặc KMS decrypt permission cần được sửa cấu hình quyền theo nguyên tắc tối thiểu. Retrying hàng nghìn lần chỉ gây audit noise và che nguyên nhân.

### 5.5. Khi `404` được dùng để che quyền

Một số API trả `404` cho tài nguyên không được phép xem nhằm tránh tiết lộ sự tồn tại. Không suy từ `404` rằng tài nguyên chắc chắn không tồn tại, càng không tự dò mọi tenant/ID khác.

## 6. Nhóm từ chối do điều kiện nghiệp vụ

Các lỗi business rejection khác lỗi transient:

~~~text
INSUFFICIENT_STOCK
ORDER_ALREADY_CANCELED
USERNAME_ALREADY_EXISTS
SEAT_ALREADY_RESERVED
QUOTA_BUSINESS_LIMIT_REACHED
INVALID_STATE_TRANSITION
~~~

Nếu điều kiện không đổi, tự retry là vô ích hoặc nguy hiểm.

### 6.1. Ví dụ atomic conditional stock

~~~text
IF Inventory.available >= requestedQuantity
THEN decrement available.
ELSE reject.
~~~

`INSUFFICIENT_STOCK` là kết quả đúng của một thao tác atomically rejected. Không tự retry ngay lập tức 20 lần mong “được hàng”; cần hiển thị hết hàng, giảm quantity hoặc chờ một sự kiện bổ sung hàng theo nghiệp vụ.

### 6.2. Business quota khác system throttling

| Tình huống | Loại | Hành động |
|---|---|---|
| Tenant chỉ được tạo 100 users theo gói thuê bao | Business limit | Nâng gói/xóa user/chờ quota reset theo policy |
| Database trả 429 do requests/s vượt capacity tạm thời | Throttling | Giảm tải, backoff, tôn trọng hint |
| Tenant bị khóa do vi phạm chính sách | Permission/policy | Không tự retry hoặc né kiểm soát |
| Storage hết chỗ theo quota cứng | Capacity/config/plan | Mở rộng/hạn chế dữ liệu sau xét duyệt |

Gọi mọi lỗi chứa chữ “quota” là retryable có thể làm chương trình loop vô hạn.

### 6.3. Duplicate request có thể là thành công cũ

Nếu `commandId` đã tồn tại với **cùng payload**, API idempotent có thể trả lại kết quả cũ, không nhất thiết coi đó là lỗi. Nếu `commandId` giống nhưng **payload khác**, phải từ chối `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST`, không áp dụng thao tác mới.

### 6.4. `ALREADY_EXISTS` không tự retry

Một user cố tạo username đã tồn tại cần chọn username khác. Nhưng nếu request bị timeout rồi retry cùng create ID, `ALREADY_EXISTS` có thể có nghĩa lần đầu đã thành công. Cần kiểm tra identity và intent, không máy móc biến duplicate thành success hoặc retry.

## 7. Nhóm lỗi tạm thời thường có thể thử lại

Các loại phổ biến:

- Replica/leader đang election hoặc failover.
- Router topology cũ, lệnh gửi tới owner không còn hợp lệ.
- Transient network error, DNS, TLS handshake hoặc connection pool cần phục hồi, **sau khi phân biệt outcome**.
- Quorum tạm không đủ hoặc service unavailable ngắn.
- Throttling có retry hint.
- Transaction abort do write conflict/serialization conflict.
- Temporary storage busy, coordinator overloaded.
- Retryable lock contention theo API.
- Replica chưa bắt kịp session token/read requirement, nếu client có thể chờ.

### 7.1. Không phải lỗi mạng nào cũng giống nhau

~~~text
Connection refused before request sent:
    likely no mutation reached target, but consider proxy/driver contract.

Connection reset while waiting for write response:
    mutation may already be committed.
~~~

Không nên dựa riêng vào `IOException` để kết luận `safeToRetry=true`.

### 7.2. Không retry vô hạn khi thiếu quorum

Nếu network partition kéo dài, một bên không có quyền commit. Backoff và circuit breaker có thể giảm tải nhưng không khôi phục quorum. Client nên trả `UNAVAILABLE` hoặc `PENDING` theo contract.

### 7.3. Refresh topology có thể là bước cần trước retry

Khi leader chuyển từ A sang B, lặp request tới A 100 lần không hữu ích. SDK cần refresh routing/leader metadata hoặc xử lý redirect theo tài liệu sản phẩm.

### 7.4. Retry không tạo thêm availability của nguồn bị lỗi

Nếu một hot partition bị quá tải, retry đồng loạt từ hàng nghìn clients có thể làm tình hình tệ hơn. Cần client-side rate limit, jitter, queue và xử lý backpressure.

## 8. Bảng mã HTTP: điểm khởi đầu, không phải chính sách hoàn chỉnh

| HTTP status | Thường có nghĩa | Retry mặc định? | Ngoại lệ quan trọng |
|---|---|---|---|
| `400 Bad Request` | Request sai | Không | Sửa payload/schema |
| `401 Unauthorized` | Chưa xác thực | Không retry nguyên credential | Refresh token hợp lệ một lần rồi xét an toàn thao tác |
| `403 Forbidden` | Thiếu quyền | Không | Chỉ làm lại sau khi cấp quyền hợp lệ |
| `404 Not Found` | Không tìm thấy/không được tiết lộ | Thường không | Read-after-write eventual có thể cần chờ theo contract |
| `408 Request Timeout` | Request timeout | Phụ thuộc | Mutation có thể đã được xử lý ở server |
| `409 Conflict` | Xung đột/duplicate/business rule | Không suy từ số mã | OCC conflict có thể cần retry toàn UoW; duplicate có thể terminal |
| `412 Precondition Failed` | ETag/version/predicate sai | Không lặp write cũ | Có thể read state mới và đánh giá lại |
| `413 Payload Too Large` | Payload vượt giới hạn | Không | Chia batch/sửa thiết kế |
| `422 Unprocessable Content` | Dữ liệu hợp cú pháp nhưng sai domain | Không | Sửa input/condition |
| `429 Too Many Requests` | Throttle/rate limit | Có điều kiện | Tôn trọng `Retry-After`, deadline, quota cứng |
| `500 Internal Server Error` | Lỗi server | Có thể | Outcome mutation không chắc; có thể là lỗi code kéo dài |
| `502 Bad Gateway` | Gateway nhận upstream error | Có thể | Write outcome có thể ambiguous |
| `503 Service Unavailable` | Service không sẵn sàng | Có thể | Có thể mất quorum lâu, không retry vô hạn |
| `504 Gateway Timeout` | Gateway chờ upstream quá lâu | Có thể nhưng cần xử lý unknown | Upstream có thể đã commit |

### 8.1. Mã lỗi và response body cùng quan trọng

API có thể gói:

~~~json
{
  "code": "CONDITIONAL_CHECK_FAILED",
  "retryable": false,
  "requestId": "req-123",
  "details": {
    "field": "expectedVersion"
  }
}
~~~

Đây chỉ là ví dụ response structure. `retryable` do server trả là một tín hiệu cần đọc trong phạm vi contract; client vẫn phải bảo đảm idempotency, deadline và không bỏ qua security.

### 8.2. `Retry-After` phải được hiểu đúng

Header có thể là số giây hoặc HTTP-date theo chuẩn HTTP. Client phải parse phù hợp, giới hạn theo deadline, tránh tạo vòng lặp bất tận. Nếu server nói thử sau 30 giây nhưng request deadline còn 2 giây, dừng hoặc chuyển workflow async thay vì sleep bất chấp.

### 8.3. `409` là ví dụ điển hình không thể hardcode

`409` có thể là username đã tồn tại (không retry), OCC conflict (retry sau re-read), hoặc idempotency key đã dùng (tra outcome). Classifier phải đọc **application error code** và **operation intent**.

### 8.4. `404` với eventual reads

Ngay sau khi ghi vào source, search index trễ có thể chưa thấy document. Một số read APIs cho phép bounded retry để chờ projection, nhưng không được dùng `404` từ search như bằng chứng ghi nguồn đã thất bại.

## 9. gRPC status: cách phân biệt

| gRPC status | Hướng hiểu | Chính sách gợi ý |
|---|---|---|
| `UNAVAILABLE` | Service hoặc kết nối tạm unavailable | Có thể retry nếu an toàn |
| `DEADLINE_EXCEEDED` | Client không nhận kết quả trong deadline | Mutation outcome có thể unknown |
| `ABORTED` | Conflict/transaction abort theo contract | Retry cả transaction/higher-level UoW khi được hướng dẫn |
| `RESOURCE_EXHAUSTED` | Rate limit/quota/resource limit | Throttle/backoff hoặc sửa quota/capacity |
| `INVALID_ARGUMENT` | Request sai | Sửa input |
| `FAILED_PRECONDITION` | State/system condition không phù hợp | Sửa điều kiện, chỉ retry sau thay đổi |
| `OUT_OF_RANGE` | Giá trị ngoài khoảng | Sửa input |
| `UNAUTHENTICATED` | Thiếu credential hợp lệ | Login/refresh đúng policy |
| `PERMISSION_DENIED` | Thiếu quyền | Không retry tự động |
| `ALREADY_EXISTS` | Resource đã tồn tại | Xác minh idempotent intent |
| `NOT_FOUND` | Resource không thấy | Xem source/consistency contract |
| `INTERNAL` | Lỗi server | Tùy contract, không mặc định mutation chưa chạy |
| `CANCELLED` | Call bị hủy | Phân biệt local cancellation và server side effect |

Đây là **định hướng** chứ không phải danh sách retry chính thức cho mọi gRPC service. Ngay cả `UNAVAILABLE` cũng không cho phép retry một charge không có idempotency.

### 9.1. `ABORTED` không phải `UNAVAILABLE`

`ABORTED` thường phản ánh xung đột ở cấp transaction; retry **toàn read–modify–write sequence** có thể cần thiết. `UNAVAILABLE` là trạng thái service/transport; có thể chỉ cần retry RPC hoặc chuyển owner sau topology refresh, nếu outcome được hiểu đúng.

### 9.2. `CANCELLED` không nhất thiết rollback server

Client hủy request đang chạy không chứng minh server đã hủy mutation. Nếu server tiếp tục xử lý sau khi client ngắt, cần đối soát như một outcome không rõ.

## 10. Lỗi NoSQL cụ thể: MongoDB

Trong MongoDB, transaction driver có thể gắn **error labels** để hướng dẫn xử lý:

- `TransientTransactionError`: một số lỗi tạm thời có thể yêu cầu retry **toàn transaction**.
- `UnknownTransactionCommitResult`: kết quả `commitTransaction` không xác định; SDK có retry-commit/reconciliation semantics phù hợp.

Các nhãn và driver APIs phải được kiểm tra theo version, topology và transaction guidance hiện hành.

### 10.1. Phân biệt retry transaction với retry commit

~~~text
Attempt T1:
    BEGIN
    read Order v7
    validate transition
    update Order v8

Case A: transaction aborted before successful commit.
    -> open a new transaction
    -> read current state again
    -> validate again
    -> attempt commit again.

Case B: commit result unknown.
    -> follow SDK commit retry/resolve protocol
    -> do not assume T1 aborted.
~~~

### 10.2. Không gọi side effect trong callback

~~~javascript
await session.withTransaction(async () => {
  await orders.updateOne(filter, update, {session});
  await paymentGateway.charge(paymentId); // nguy hiểm
});
~~~

Nếu callback được driver thực thi lại vì conflict, payment có thể bị gọi nhiều lần. Ghi outbox/intent trong transaction, rồi xử lý external call idempotently sau commit.

### 10.3. Duplicate key không tự là retryable

Unique index violation có thể do username bị chiếm, cần user sửa input. Nhưng với create operation theo một `commandId` cố định, duplicate có thể là request đã thành công trước đó; cần tra record và xác định payload/idempotency, không tự coi mọi duplicate là success.

### 10.4. Stale primary/routing

Khi replica set election hoặc sharded router cập nhật topology, một số requests có thể thất bại tạm thời. Dùng driver topology discovery/retry policy được hỗ trợ thay vì tự pin host cũ rồi lặp request.

## 11. Lỗi NoSQL cụ thể: DynamoDB

Một số loại lỗi cần phân biệt theo DynamoDB APIs:

| Tình huống | Hướng xử lý |
|---|---|
| `ThrottlingException` hoặc throughput exceeded theo API | Backoff, jitter, giảm concurrency/cải thiện capacity |
| `ConditionalCheckFailedException` | Điều kiện không đạt; thường cần đọc và đánh giá lại, không lặp nguyên lệnh |
| Transaction cancellation/conflict | Đọc cancellation reasons và retry guidance theo SDK |
| `ValidationException` | Sửa input, expression, size/schema |
| `AccessDeniedException` | Sửa IAM policy/credentials, không retry mù |
| Network timeout sau mutation | Có thể ambiguous; dùng stable commandId/conditional semantics |

### 11.1. Condition failure là kết quả có ý nghĩa

~~~text
Update Inventory
  Condition available >= 3
  Decrement available by 3
~~~

Nếu condition không đạt, lập tức retry 100 lần không tăng tồn kho. Đó là business rejection. Nếu cần chờ hàng về, workflow phải do nghiệp vụ định nghĩa: event notification, reservation waitlist hoặc request mới.

### 11.2. Transaction cancellation không phải một nguyên nhân duy nhất

Một transaction có thể hủy do conflict, condition failure, size/validation hoặc capacity; không được coi mọi `TransactionCanceled` là retryable. Cần dựa trên reasons, request design và contract.

### 11.3. SDK có thể đã retry

AWS SDK có retry strategy; nếu application thêm nhiều tầng retry mà không kiểm soát, một request business có thể tạo hàng chục/hàng trăm attempts. Phải tính **tổng retry budget end-to-end**.

### 11.4. Capacity không phải luôn tự hết

Một hot partition liên tục vượt throughput không được “chữa” bằng backoff vô hạn. Cần thay partition key, xử lý hotspot, queue, capacity hoặc rate shaping.

## 12. Lỗi NoSQL cụ thể: Cosmos DB for NoSQL

Trong Azure Cosmos DB for NoSQL, cần quan sát status/substatus và SDK guidance của từng API:

- `429 Too Many Requests`: throttling, thường có retry-after; cần kiểm soát RU/s và backoff.
- `412 Precondition Failed`: ETag/optimistic concurrency không khớp; đọc lại và quyết định nghiệp vụ, không lặp update với ETag cũ.
- `400`/validation: sửa request, partition key, query hoặc resource configuration.
- `401`/`403`: xác thực hoặc quyền.
- Một số error signals liên quan write contention hoặc retry được tài liệu hóa riêng, cần phân biệt với business failures.
- `408`/`503`/network timeout có thể cần phân tích outcome của mutation và regional failover.

### 12.1. ETag là một điều kiện nghiệp vụ/kỹ thuật

~~~text
GET document -> ETag E7.
Another writer updates -> E8.
PUT If-Match E7 -> 412.
~~~

Lặp lại `PUT If-Match E7` không giải quyết xung đột. Cần đọc v8, tính lại thay đổi và quyết định có hợp lệ không.

### 12.2. Không bỏ điều kiện để “retry thành công”

Một anti-pattern nguy hiểm là gặp 412 rồi PUT không có `If-Match`. Điều đó biến optimistic concurrency thành ghi đè mù và có thể làm mất thay đổi của writer khác.

### 12.3. RU throttling và workload shape

429 có thể xuất hiện vì một tenant/hot partition dùng quá nhiều tài nguyên. Retry phải phù hợp retry-after, nhưng nếu tải liên tục cao hơn capacity, hệ cần admission control hoặc thiết kế partition tốt hơn.

## 13. Lỗi NoSQL cụ thể: Firestore, Cassandra/ScyllaDB và Redis

### 13.1. Firestore transaction

Một số transaction SDK có thể retry callback khi xung đột. Những lỗi dạng conflict/abort có thể cần chạy lại transaction theo tài liệu. Nhưng:

- Validation/permission errors không được retry mù.
- Callback không nên thực hiện external side effect.
- Không giữ transaction dài với HTTP calls.
- Cần kiểm tra transaction read-before-write, scope và retry limits của SDK.

### 13.2. Cassandra/ScyllaDB

Các lỗi như coordinator unavailable, read timeout, write timeout, overloaded hoặc stale topology cần phân loại theo **operation semantics** và **consistency level**. Riêng **write timeout** có thể có tình huống mutation đã tới một số replicas hoặc đạt một phần điều kiện, nên không suy nó chắc chắn chưa xảy ra.

Một CQL mutation dạng:

~~~sql
UPDATE counters
SET total = total + 1
WHERE tenant_id = 'T1';
~~~

không có cùng retry safety với một idempotent set-to-value write hoặc conditional mutation. Hành vi counters/batches/LWT cần đọc theo phiên bản; đừng áp một policy retry chung cho mọi statement.

### 13.3. Redis

Trong Redis/Redis Cluster, một số lỗi định tuyến như `MOVED`/`ASK` có quy trình cập nhật route/redirect; những trạng thái tạm như `TRYAGAIN` có thể cần retry có giới hạn theo tài liệu. Ngược lại:

- Wrong type hoặc syntax error: sửa lệnh/data model.
- `NOAUTH`/ACL denial: sửa credential/quyền.
- Script `INCRBY` đã chạy nhưng response mất: retry lệnh có thể tăng hai lần.
- Follower promotion sau primary failure có thể ảnh hưởng durability; retry không tự khôi phục write bị mất.

### 13.4. Không so exception names bằng chuỗi tùy tiện

Các SDK có error types/labels cụ thể; nên map chúng vào taxonomy nội bộ qua adapter. Không dùng `message.contains("timeout")` vì thông điệp lỗi có thể thay đổi, được dịch hoặc bị wrap.

## 14. Retry ở tầng nào? Driver, repository, service hay workflow

Một application thường có nhiều tầng:

~~~mermaid
flowchart TD
    HTTP["HTTP caller"] --> API["API handler retry?"]
    API --> SVC["Business service retry?"]
    SVC --> REPO["Repository retry?"]
    REPO --> SDK["NoSQL SDK auto-retry?"]
    SDK --> DB["Database cluster"]
~~~

Nếu mỗi tầng retry 3 lần:

~~~text
3 (caller)
× 3 (API)
× 3 (service)
× 3 (repository)
× 3 (SDK)
= 243 database attempts in the worst compounded case.
~~~

Con số chỉ là phép nhân minh họa khi các lớp đều lặp toàn chuỗi. Thực tế còn phụ thuộc retry scopes và dừng sớm, nhưng nguy cơ **retry amplification** là có thật.

### 14.1. Quy định một tầng sở hữu retry

Một hướng thiết kế:

- SDK xử lý những transport/topology retries mà sản phẩm đã tài liệu hóa.
- Repository map error categories và exposed outcome.
- Service sở hữu **transaction UoW retry** và business validation.
- Workflow sở hữu retry kéo dài hàng phút/giờ và reconciliation.
- HTTP handler áp một deadline tổng và trả trạng thái chính xác.

Không phải mọi dự án phải đúng phân công này, nhưng cần biết **tầng nào đang retry cái gì**.

### 14.2. Deadline phải truyền xuyên tầng

Client chỉ chờ 2 giây, nhưng service gọi repository retry trong 30 giây, rồi gateway lại retry, có thể khiến request tiếp tục ghi sau khi user đã bỏ đi. Dùng deadline/cancellation context phù hợp, nhưng nhớ rằng **hủy ở client không đồng nghĩa rollback server**.

### 14.3. Không dùng retry để che thiết kế sai

Một query luôn timeout vì quét 200 triệu documents không có index cần sửa access pattern/index, không phải tăng `maxAttempts` từ 5 lên 500.

## 15. Tính an toàn của thao tác khi thử lại

| Thao tác | Ví dụ | Retry safety |
|---|---|---|
| **Pure read** | GET Order theo ID | Thường an toàn về side effect; vẫn cần deadline/consistency |
| **Set to known value** | Set `status=PENDING` nếu condition hợp lệ | Có thể idempotent khi condition/version phù hợp |
| **Compare-and-set** | Update nếu `version=7` | Có thể retry sau khi xác minh điều kiện/outcome |
| **Create with stable ID** | PUT record keyed by commandId | Có thể idempotent nếu payload collision được kiểm tra |
| **Increment/decrement** | `count += 1` | Không an toàn nếu gửi lại như lệnh mới |
| **Append event** | INSERT event random ID | Có thể duplicate nếu mỗi attempt tạo ID mới |
| **Charge payment** | External API | Cần provider idempotency/reconciliation |
| **Transaction callback** | Read–validate–write | Có thể được gọi lại; phải giữ side effects ngoài callback |
| **Bulk batch** | Một số items thành công | Cần xử lý partial results theo per-item outcomes |

### 15.1. Idempotency là tính chất của ý định và kết quả

Một thao tác idempotent có nghĩa việc áp dụng lại **cùng ý định** có hiệu ứng quan sát tương đương một lần, trong phạm vi contract.

~~~text
Set status = CONFIRMED
    may be idempotent if repeated on same entity/state.

Increment reservedCount by 1
    not idempotent unless command ID is deduplicated.
~~~

Tuy nhiên `Set status=CONFIRMED` có thể sai nếu Order đã `CANCELED` sau request đầu. Cần business state transition rules/expectedVersion, không chỉ nhìn mutation như một phép gán thuần.

### 15.2. Dedupe record và mutation phải cùng atomic boundary

Sai:

~~~text
INSERT processedCommand(commandId)
then decrement stock
~~~

Crash giữa hai lệnh khiến command được đánh dấu processed nhưng stock chưa trừ. Đổi thứ tự thì stock có thể trừ rồi command chưa lưu, dẫn tới double decrement khi retry.

Đúng hướng:

~~~text
Atomically, within supported scope:
    IF commandId not processed AND stock sufficient:
        decrement stock
        record commandId + outcome
        commit
~~~

Nếu NoSQL không hỗ trợ transaction chung, phải thiết kế reservation/ledger protocol có trạng thái, idempotent steps và reconciliation; không gọi hai independent writes là atomic.

### 15.3. Key phải được giữ nguyên qua retry

Nếu mỗi attempt tạo UUID mới cho cùng một Order, unique key không giúp dedupe. `commandId`, `orderId`, `reservationId`, `paymentId` cần ổn định theo ý định người dùng và có quy tắc tenant scope.

### 15.4. Cùng key khác payload

~~~text
commandId=C100, reserve 2 -> first attempt.
commandId=C100, reserve 5 -> later attempt.
~~~

Đây không phải retry hợp lệ của cùng ý định. Nguồn nên từ chối thay vì trả success ngẫu nhiên hoặc áp payload mới. Có thể lưu hash của canonical request cùng commandId.

## 16. Timeout và ACK bị mất: quy trình đối soát

Ví dụ:

~~~mermaid
sequenceDiagram
    participant CL as Client
    participant DB as NoSQL Leader
    participant RP as Replicas
    CL->>DB: Reserve(C-100, SKU-A, qty=2)
    DB->>RP: Replicate / commit
    RP-->>DB: ACK per protocol
    DB--xCL: Success response lost
    Note over CL: DeadlineExceeded: outcome UNKNOWN
    CL->>DB: Resolve C-100 via authoritative read
    DB-->>CL: Previously committed receipt
~~~

### 16.1. Không dùng `GET` qua eventual index để chứng minh absence

Index/search/follower có thể chưa thấy `commandId`. Nếu `GET /commands/C-100` dùng eventual read, trả 404 không chứng minh lệnh chưa commit. Dùng source-of-truth/consistency đáp ứng contract hoặc tiếp tục trạng thái pending.

### 16.2. Hành động theo kết quả

~~~text
COMMITTED:
    return previous receipt, no additional mutation.

REJECTED:
    return known business rejection.

CONFIRMED_NOT_APPLIED:
    retry same stable intent if API contract permits.

UNKNOWN:
    keep pending; do not invent a fresh mutation.
~~~

`CONFIRMED_NOT_APPLIED` chỉ dùng khi **API có bằng chứng đủ mạnh** rằng intent chưa được thực hiện; một query chưa thấy không mặc nhiên đạt điều kiện này.

### 16.3. Retention của idempotency metadata

Nếu dedupe record bị TTL xóa sau 1 giờ nhưng client có thể retry một request 2 ngày sau, cùng `commandId` có thể được nhận lại như mới. Phải xác định **idempotency window**, transaction/business retention và cách xử lý command cũ.

### 16.4. Restore từ backup có thể làm mất dedupe state

Nếu Order đã commit ở một mốc nhưng restore command registry từ backup cũ, hệ có thể quên rằng command đã xử lý. Restore plan phải giữ hoặc reconstruct history/dedupe thích hợp, tránh hồi sinh effect.

## 17. Transaction conflict: khi nào retry toàn đơn vị công việc?

Một transaction đọc Account A và B, xác minh chuyển 100 đồng rồi update cả hai. T2 có thể đã thay đổi A hoặc B trong lúc T1 đang thực hiện.

~~~text
T1 BEGIN
T1 READ A.balance = 500
T1 READ B.balance = 200

T2 changes A.balance and commits.

T1 WRITE A, B.
Database detects conflict and aborts T1.
~~~

Khi database báo **attempt T1 đã abort rõ ràng** theo transaction API:

~~~text
RETRY WHOLE UNIT:
    BEGIN new transaction
    READ A and B again
    VALIDATE A has sufficient funds
    WRITE A and B in supported atomic scope
    COMMIT
~~~

### 17.1. Không retry chỉ câu lệnh thất bại

Nếu giữ giá trị đọc cũ và lặp một `UPDATE B` riêng, kiểm tra số dư có thể không còn đúng. Transaction retry cần tính lại toàn bộ business decision dựa trên snapshot/state mới.

### 17.2. Abort rõ khác unknown commit

Nếu transaction API khẳng định aborted, có thể retry. Nếu `commit` timeout, có thể đã commit; cần follow SDK-specific retry-commit/resolve semantics trước khi lặp business transaction.

### 17.3. Business rejection sau retry

Lần đầu transaction abort vì conflict, lần thứ hai đọc lại A chỉ còn 50. Kết quả đúng là `INSUFFICIENT_FUNDS`, không phải cứ retry tới khi chuyển thành công.

### 17.4. Bounded retry

Một hot key có thể tạo xung đột liên tục. Sau một số attempts hoặc hết deadline, trả conflict/unavailable có ý nghĩa và cải thiện thiết kế hotspot, không loop vô hạn.

### 17.5. Callback phải không có external side effect

Không gửi email, push notification hoặc capture payment trực tiếp trong callback có thể bị driver gọi nhiều lần. Ghi outbox/intent trong cùng atomic boundary nếu hỗ trợ, rồi xử lý external effect idempotently.

## 18. Backoff, exponential delay và jitter

Nếu retry ngay lập tức, nhiều clients gặp cùng sự cố có thể đồng thời gửi lại, tạo **thundering herd**.

Một backoff cơ bản:

\[
d_k = \min(d_{\max},d_{\text{base}}\cdot 2^{k-1})
\]

với \(k=1,2,\ldots\) là thứ tự lần chờ sau failure. Ví dụ `base=100 ms`, `cap=2.000 ms`:

| Retry delay thứ k | Không jitter (ms) | Full jitter có thể chọn trong khoảng |
|---:|---:|---|
| 1 | 100 | [0, 100] ms |
| 2 | 200 | [0, 200] ms |
| 3 | 400 | [0, 400] ms |
| 4 | 800 | [0, 800] ms |
| 5 | 1.600 | [0, 1.600] ms |
| 6 | 2.000 | [0, 2.000] ms |

**Full jitter** chọn một thời gian ngẫu nhiên trong khoảng từ 0 đến cap hiện tại. Mục tiêu là rải attempts của nhiều clients.

### 18.1. Jitter không đảm bảo hết tải

Nếu load liên tục lớn hơn capacity, phân tán thời điểm retry chỉ giảm đồng bộ hóa, không tạo thêm tài nguyên. Cần throttling/admission control hoặc scale/partition fix.

### 18.2. Retry-After là tín hiệu ưu tiên

Nếu API trả wait hint hợp lệ, dùng nó trong giới hạn deadline và policy. Không ngẫu nhiên hóa thành delay **ngắn hơn minimum** mà server yêu cầu.

### 18.3. Không sleep vượt deadline

~~~text
overallDeadlineRemaining = 500 ms
backoff = 1000 ms

=> stop; do not sleep 1000 ms.
~~~

### 18.4. Lấy retry budget theo end-to-end request

Nếu cả gateway và database client đều retry, cần giữ ngân sách tổng. MaxAttempts cục bộ của mỗi tầng không đủ nếu các tầng nhân attempts.

### 18.5. Không dùng delay cố định cho tất cả clients

Hàng nghìn clients cùng đợi 1 giây rồi gửi lại có thể tạo một đợt spike mới. Jitter giúp tránh đồng bộ hóa thời điểm.

## 19. Deadline, max attempts, retry budget và circuit breaker

Ba giới hạn hữu ích:

1. **Max attempts:** số lần thực thi lệnh tối đa cho một ý định.
2. **End-to-end deadline:** thời điểm yêu cầu không còn cần/được phép tiếp tục synchronous processing.
3. **Retry budget:** tỷ lệ hoặc số retries tối đa trên lượng traffic trong một cửa sổ để tránh amplification.

### 19.1. Retry budget theo tỷ lệ

Ví dụ một hệ cho phép **không quá 10 retries bổ sung trên 100 first attempts** trong một khoảng thời gian. Khi hệ hỏng nặng, budget cạn và client fail fast/queue thay vì tạo thêm hàng nghìn requests.

Con số 10% là ví dụ, không phải quy chuẩn.

### 19.2. Circuit breaker

~~~text
CLOSED:
    allow requests, monitor failures.

OPEN:
    reject/queue quickly, avoid hammering unhealthy dependency.

HALF_OPEN:
    allow limited probes, close or reopen based on outcome.
~~~

Circuit breaker không thay thế idempotency. Khi probe là mutation, vẫn cần semantic safety; thường dùng health/read probes phù hợp hơn.

### 19.3. Bulkhead và concurrency limits

Tenant whale có thể gây throttle làm toàn pool retry. Giới hạn concurrent operations theo tenant/partition để một nhóm không lấy hết connections/threads của phần còn lại.

### 19.4. Deadline hết mà outcome unknown

Không giữ HTTP connection mãi. Có thể trả `202 PENDING` hoặc response quy định rõ chưa xác nhận, kèm stable commandId và endpoint theo dõi; backend tiếp tục reconciliation theo workflow bền nếu nghiệp vụ cần.

### 19.5. Cancellation không chứng minh rollback

Client hủy task và nhận `CancellationException`; server có thể đã commit. Với write đã được gửi, cần giữ thông tin reconciliation nếu kết quả chưa rõ.

## 20. Java: taxonomy lỗi tách nguyên nhân khỏi outcome

Đây là mô hình trừu tượng có thể dùng trong adapter Java 17+, không phải exception types của database vendor:

~~~java
public enum FailureKind {
    TRANSIENT_TRANSPORT,
    TRANSIENT_TOPOLOGY,
    THROTTLED,
    TRANSACTION_ABORTED,
    INPUT_INVALID,
    AUTHENTICATION,
    AUTHORIZATION,
    BUSINESS_REJECTED,
    CONDITIONAL_CONFLICT,
    CONFIGURATION,
    UNKNOWN
}

public enum CommitKnowledge {
    DEFINITELY_NOT_COMMITTED,
    COMMITTED,
    UNKNOWN
}

public record ClassifiedFailure(
    FailureKind kind,
    CommitKnowledge commitKnowledge,
    String safeCode,
    Long retryAfterMillis
) {}

public enum RetryAction {
    RETRY_SAME_SAFE_REQUEST,
    RETRY_WHOLE_TRANSACTION,
    REFRESH_TOPOLOGY_THEN_RETRY,
    RESOLVE_COMMIT_OUTCOME,
    REFRESH_CREDENTIAL_THEN_REEVALUATE,
    STOP_FIX_INPUT_OR_PERMISSION,
    STOP_BUSINESS_REJECTION,
    STOP_ESCALATE
}

public record OperationDescriptor(
    String operationName,
    boolean safeToRepeat,
    boolean hasStableIdempotencyKey,
    boolean insideTransaction
) {}
~~~

### 20.1. Phân loại theo nguyên nhân và knowledge

~~~java
public final class RetryClassifier {
    public RetryAction classify(
        OperationDescriptor op, ClassifiedFailure failure
    ) {
        if (failure.commitKnowledge() == CommitKnowledge.COMMITTED) {
            return RetryAction.RESOLVE_COMMIT_OUTCOME;
        }
        if (failure.commitKnowledge() == CommitKnowledge.UNKNOWN) {
            return RetryAction.RESOLVE_COMMIT_OUTCOME;
        }

        return switch (failure.kind()) {
            case INPUT_INVALID, AUTHORIZATION ->
                RetryAction.STOP_FIX_INPUT_OR_PERMISSION;

            case AUTHENTICATION ->
                RetryAction.REFRESH_CREDENTIAL_THEN_REEVALUATE;

            case BUSINESS_REJECTED ->
                RetryAction.STOP_BUSINESS_REJECTION;

            case CONDITIONAL_CONFLICT ->
                RetryAction.STOP_BUSINESS_REJECTION;

            case CONFIGURATION, UNKNOWN ->
                RetryAction.STOP_ESCALATE;

            case TRANSACTION_ABORTED ->
                op.insideTransaction()
                    ? RetryAction.RETRY_WHOLE_TRANSACTION
                    : RetryAction.STOP_ESCALATE;

            case TRANSIENT_TOPOLOGY ->
                repeatable(op)
                    ? RetryAction.REFRESH_TOPOLOGY_THEN_RETRY
                    : RetryAction.STOP_ESCALATE;

            case TRANSIENT_TRANSPORT, THROTTLED ->
                repeatable(op)
                    ? RetryAction.RETRY_SAME_SAFE_REQUEST
                    : RetryAction.STOP_ESCALATE;
        };
    }

    private static boolean repeatable(OperationDescriptor op) {
        return op.safeToRepeat() || op.hasStableIdempotencyKey();
    }
}
~~~

**Giới hạn của ví dụ:** `commitKnowledge=DEFINITELY_NOT_COMMITTED` chỉ được gán khi adapter có bằng chứng/contract thực sự. `hasStableIdempotencyKey=true` cũng chỉ đủ khi **server xử lý key atomically với mutation**. Nếu chỉ client tự tạo ID mà server không dedupe, không được coi operation an toàn.

### 20.2. Conditional conflict có nhiều nghĩa

Mã trên chọn dừng mặc định. Với optimistic concurrency, service có thể đổi kết quả thành `RETRY_WHOLE_TRANSACTION` sau khi thực sự **đọc lại, kiểm tra invariant và xác nhận retry có ý nghĩa**. Đừng tự retry tất cả `412`/`409`.

### 20.3. Phân loại authentication không tự lặp write

`REFRESH_CREDENTIAL_THEN_REEVALUATE` nghĩa là cập nhật credential hợp lệ rồi **đánh giá lại retry safety và commit outcome**. Không đồng nghĩa có thể gửi lại mutation ngay.

### 20.4. Adapter phải dựa vào structured error

MongoDB label, DynamoDB exception type/reasons, Cosmos status/substatus, gRPC status và HTTP application error code cần được map sang taxonomy. Giữ diagnostic IDs, nhưng tránh log toàn bộ secrets/payload.

## 21. Java: bounded retry runner cho thao tác đã biết retry an toàn

Đoạn sau minh họa retry **đúng scope** cho lệnh đã có guarantee `safeToRepeat`. Không dùng trực tiếp cho transaction commit unknown hoặc side effect không idempotent.

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class BoundedRetry {
    @FunctionalInterface
    public interface Attempt<T> {
        T run() throws Exception;
    }

    @FunctionalInterface
    public interface RetryableError {
        boolean test(Exception error);
    }

    public static <T> T execute(
        Attempt<T> attempt,
        RetryableError isSafeRetry,
        int maxAttempts,
        Duration totalTimeout,
        Duration baseDelay,
        Duration maxDelay
    ) throws Exception {
        if (maxAttempts < 1 || totalTimeout.isNegative()
                || baseDelay.isNegative() || maxDelay.isNegative()) {
            throw new IllegalArgumentException("invalid retry policy");
        }

        long deadline = System.nanoTime() + totalTimeout.toNanos();

        for (int count = 1; ; count++) {
            try {
                return attempt.run();
            } catch (Exception error) {
                if (count >= maxAttempts || !isSafeRetry.test(error)) {
                    throw error;
                }

                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) {
                    throw error;
                }

                int shift = Math.min(count - 1, 30);
                long exponential = saturatingMultiply(
                    baseDelay.toNanos(), 1L << shift
                );
                long cap = Math.min(exponential, maxDelay.toNanos());
                long delay = cap <= 0 ? 0
                    : ThreadLocalRandom.current().nextLong(cap + 1);
                if (delay >= remaining) {
                    throw error;
                }

                long ms = delay / 1_000_000L;
                int ns = (int) (delay % 1_000_000L);
                try {
                    Thread.sleep(ms, ns);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw interrupted;
                }
            }
        }
    }

    private static long saturatingMultiply(long a, long b) {
        if (a > 0 && b > Long.MAX_VALUE / a) {
            return Long.MAX_VALUE;
        }
        return a * b;
    }
}
~~~

Đây là **mã mẫu** cho một runner synchronous; production cần thêm request-context cancellation, clock/deadline validation, server retry hints, async scheduler, telemetry, retry budget toàn hệ và xử lý exception theo SDK. `Duration` quá lớn có thể overflow trong chuyển đổi nanoseconds; cần validation nếu cho phép giá trị tùy ý. Không chạy đoạn này như một chính sách retry cho mọi operation mà không có classifier đúng.

### 21.1. Deadline cả attempt đầu

Runner trên kiểm deadline **sau khi một attempt thất bại**; nó không cắt một `attempt.run()` đang treo. Production cần đặt per-attempt RPC timeout và truyền end-to-end deadline xuống SDK để mỗi attempt không vượt ngân sách tổng.

### 21.2. Full jitter với cap

`ThreadLocalRandom.nextLong(cap + 1)` cần tránh overflow nếu cap có thể bằng `Long.MAX_VALUE`. Trong cấu hình thời gian thông thường cap thấp; implementation production phải dùng hàm random xử lý bounds lớn một cách an toàn.

### 21.3. Không ghi log mọi attempt ở mức ERROR

Retry 5 lần rồi thành công không nên tạo 4 cảnh báo nghiêm trọng độc lập. Thu metric attempts/latency và log có sampling/correlation IDs; mức ERROR nên phản ánh **final outcome** hoặc sự cố thật.

### 21.4. Tách retry local khỏi workflow dài

Nếu cần chờ 2 giờ để quota được cấp hoặc cluster phục hồi, không sleep trong một thread HTTP. Dùng durable queue/job có state, deadline, idempotency và dead-letter handling.

## 22. Java: xử lý outcome không rõ thay vì retry mù

Một abstraction an toàn hơn cho mutation:

~~~java
public record ReservationCommand(
    String commandId,
    String tenantId,
    String sku,
    int quantity
) {}

public sealed interface ReservationOutcome
    permits ReservationOutcome.Committed,
            ReservationOutcome.Rejected,
            ReservationOutcome.Pending {

    record Committed(String reservationId)
        implements ReservationOutcome {}
    record Rejected(String reason)
        implements ReservationOutcome {}
    record Pending(String commandId)
        implements ReservationOutcome {}
}

public interface ReservationAuthority {
    ReservationOutcome reserve(ReservationCommand command);
    ReservationOutcome resolveByCommandId(
        String tenantId, String commandId
    );
}
~~~

Một service:

~~~java
public final class ReservationService {
    private final ReservationAuthority authority;

    public ReservationService(ReservationAuthority authority) {
        this.authority = authority;
    }

    public ReservationOutcome execute(ReservationCommand command) {
        if (command.quantity() <= 0) {
            return new ReservationOutcome.Rejected("INVALID_QUANTITY");
        }

        ReservationOutcome outcome = authority.reserve(command);
        if (outcome instanceof ReservationOutcome.Pending) {
            return authority.resolveByCommandId(
                command.tenantId(), command.commandId()
            );
        }
        return outcome;
    }
}
~~~

Ở đây `reserve()` có thể trả `Pending` khi transport ambiguity hoặc cluster không có quorum. `resolveByCommandId()` có thể tiếp tục trả `Pending`; ứng dụng cần lưu trạng thái và đối soát theo workflow nếu request HTTP đã hết deadline.

### 22.1. Phần khó nằm ở implementation

`ReservationAuthority` phải bảo đảm commandId và mutation ở cùng atomic boundary hoặc giao thức tương đương, quyền tenant được kiểm tra, authoritative reads thực sự có consistency phù hợp và kết quả là durable theo failure model.

### 22.2. Không trộn tenant IDs

Idempotency key có thể trùng giữa hai tenant. Registry nên có scope `(tenantId, commandId)` hoặc định danh toàn cục có kiểm soát; không cho lệnh tenant A trả kết quả của tenant B.

### 22.3. Payload mismatch

Nếu hai attempts dùng cùng key nhưng khác `sku`/`quantity`, authoritative store phải từ chối hoặc báo mismatch. Không silently return unrelated receipt.

## 23. Một case study: đặt hàng trong lúc leader failover

Giả sử hệ đặt hàng có `Orders`, `Inventory` và `Outbox`. Client gửi `ConfirmOrder(C-9001)` trong lúc leader đang thay.

### 23.1. Timeline

~~~text
t0 Client sends C-9001 to leader A.
t1 A writes transaction intent.
t2 A replicates/commits transaction per API contract.
t3 A crashes before client receives ACK.
t4 B becomes leader.
t5 Client receives timeout.
~~~

Nếu `C-9001` đã committed ở t2, client cần nhận lại **kết quả cũ**, không gửi lệnh `ConfirmOrder` mới tạo `C-9002`.

### 23.2. Cách phân loại

| Quan sát | Loại lỗi | Hướng xử lý |
|---|---|---|
| A chủ động từ chối `NOT_LEADER` trước accept | Transient topology | Refresh route, retry an toàn |
| Commit transaction abort vì write conflict | Known abort | Retry whole transaction |
| `INVALID_ORDER_STATUS` | Business rejection | Không retry |
| Client timeout lúc commit | Unknown outcome | Resolve C-9001 |
| Authz tenant denied | Permission | Không retry / điều chỉnh quyền hợp lệ |

### 23.3. Outbox

Order và Outbox nên được ghi trong cùng supported transaction nếu cần bảo đảm event intent. Publisher có thể gửi event trùng do ACK broker mất; consumer phải dedupe `eventId`/version.

### 23.4. Không gọi payment trực tiếp trong transaction retry

Nếu retry transaction callback, external payment có thể bị capture hai lần. Payment workflow cần stable `paymentId`, gateway idempotency và reconciliation.

### 23.5. Điều gì là kết quả có thể báo ngay?

Nếu không thể xác minh kết quả trước deadline:

~~~json
{
  "commandId": "C-9001",
  "status": "PENDING",
  "message": "Yêu cầu đang được xác minh; chưa xác nhận hoàn tất"
}
~~~

Không trả `CONFIRMED` dựa trên suy đoán, cũng không báo `FAILED` khi có thể đã commit.

## 24. Case study: API lưu profile với token hết hạn

Client gửi `PATCH /profile`:

~~~json
{
  "displayName": "An",
  "expectedVersion": 7
}
~~~

Có ba lỗi có thể giống nhau về trải nghiệm “không lưu được”:

1. `401`: token hết hạn.
2. `403`: tài khoản không có quyền sửa profile trong tenant.
3. `412`: version 7 cũ vì một thiết bị khác đã cập nhật profile v8.

### 24.1. Với 401

Client có thể refresh token theo policy, rồi xác minh operation retry-safe trước khi gửi lại. Nếu request trước đó được API bảo đảm từ chối trước mutation, risk thấp hơn; nếu chỉ có network timeout thì vẫn phải xét unknown outcome.

### 24.2. Với 403

Không tự đổi tenant/account hoặc liên tục gửi lại. Hiển thị thông báo quyền và hướng xin cấp quyền hợp lệ.

### 24.3. Với 412

Đọc profile v8, quyết định merge, cảnh báo user hoặc yêu cầu xác nhận. Không bỏ `If-Match` chỉ để write thành công bằng cách ghi đè.

### 24.4. Với timeout

Nếu server có thể đã cập nhật v8, thử lại `PATCH` với cùng `expectedVersion=7` có thể trả 412, dù request đầu đã thành công. Cần nhận diện commandId hoặc so sánh trạng thái/payload theo quy tắc phù hợp, không tự thông báo user rằng lần đầu thất bại.

## 25. Case study: import dữ liệu theo batch

Một tenant upload 100.000 records, backend chia thành 200 batches. Trong batch 17, chỉ một số items được ghi thành công; API có thể trả partial failure.

### 25.1. Không retry toàn batch vô điều kiện

Nếu mỗi record có generated ID mới khi retry, những items đã thành công sẽ bị duplicate. Cần stable IDs cho từng record hoặc idempotency key theo item.

### 25.2. Per-item result

~~~json
{
  "batchId": "import-42-b17",
  "results": [
    {"itemId": "r1", "status": "COMMITTED"},
    {"itemId": "r2", "status": "THROTTLED"},
    {"itemId": "r3", "status": "INVALID_FIELD"},
    {"itemId": "r4", "status": "UNKNOWN"}
  ]
}
~~~

Hành động:

- r1: không ghi lại.
- r2: retry sau backoff nếu còn budget.
- r3: đưa vào báo cáo lỗi dữ liệu.
- r4: đối soát bằng itemId/commandId.

### 25.3. Batch-level ACK không đủ

Một số API batch có semantics all-or-nothing; API khác chấp nhận partial successes. Không suy từ tên `BatchWrite` rằng mọi item được commit hoặc rollback cùng nhau.

### 25.4. Checkpoint

Lưu durable checkpoint `importId`, per-item outcome, retries và final counts. Worker crash/restart phải resume mà không duplicate những records đã committed.

## 26. Phân biệt 429 với contention và business limit

Một service trả ba loại “quá tải”:

~~~text
429 DATABASE_THROTTLED
409 TRANSACTION_WRITE_CONFLICT
409 TENANT_PLAN_LIMIT
~~~

Chúng không có cùng remediation:

| Error | Nguyên nhân | Chính sách |
|---|---|---|
| Database throttled | Tài nguyên tạm hết | Backoff, rate shaping, capacity |
| Write conflict | Hai attempts tranh cùng state | Retry toàn UoW có re-read hoặc giảm contention |
| Plan limit | Chính sách tenant không cho thêm | User/admin điều chỉnh plan/usage |

### 26.1. Hot key không chỉ là thiếu retry

Nếu mọi transaction sửa cùng một quota document và conflict rate cao, tăng attempts có thể tăng work wasted. Cân nhắc queue/actor per key, batching, partitioned quota hoặc điều chỉnh invariant owner.

### 26.2. Per-tenant quota và fairness

Không để một tenant tạo retry storm làm toàn cluster ảnh hưởng. Dùng rate limits/budgets theo tenant/tier, nhưng vẫn enforce authorization và tenant isolation.

### 26.3. Retry có thể mất tính công bằng

Client retry mạnh nhất có thể chiếm capacity trong lúc client bình thường bị chậm. Admission control và backpressure nên ưu tiên một chính sách công bằng hơn “ai gửi nhiều lần thì thắng”.

## 27. Những lỗi cấu hình cần sửa thay vì retry

Ví dụ:

- Partition key được chọn sai, khiến mọi request dùng key không tồn tại.
- Table/collection/index chưa tạo.
- Cluster URI/DNS endpoint sai một cách cố định.
- Credential/role/KMS key bị thu hồi.
- TLS certificate trust cấu hình sai.
- Transaction được gọi trên topology/API không hỗ trợ.
- Document size/batch limits liên tục bị vượt.
- Compaction/storage không còn chỗ và cần can thiệp.
- Schema migration không tương thích với client.

### 27.1. Lỗi có thể “hết sau khi sửa config” vẫn không là retry tự động vô hạn

Khi admin sửa IAM, request có thể thành công sau đó. Nhưng trong khoảng chưa sửa, retry liên tục tốn tài nguyên. Handler nên dừng/escalate, một workflow có thể thử lại **sau khi có tín hiệu recovery hoặc cấu hình thay đổi**.

### 27.2. `503` kéo dài có thể là sự cố nền tảng

Ban đầu 503 có thể tạm thời. Sau nhiều failures hoặc vượt SLO, chuyển sang circuit open và alert. Không dùng mã 503 để hợp thức hóa retry vô thời hạn.

### 27.3. Dead-letter queue không là bãi chứa vĩnh viễn

Với messages không xử lý được, DLQ giúp cô lập và triage. Cần owner, retention, khả năng replay idempotent và quy trình phân loại; không chỉ đẩy mọi 4xx vào queue rồi quên.

## 28. HTTP API nên trả lỗi có mã máy đọc được

Ví dụ:

~~~json
{
  "error": {
    "code": "ORDER_VERSION_CONFLICT",
    "category": "PRECONDITION",
    "message": "Đơn hàng đã được thay đổi; hãy tải lại",
    "requestId": "req-8831",
    "commandId": "C-9001"
  }
}
~~~

### 28.1. Tách machine code và message cho user

`ORDER_VERSION_CONFLICT` ổn định cho client logic; message có thể dịch sang tiếng Việt/Anh và thay đổi. Không parse `message.contains("conflict")`.

### 28.2. Retry hint là contract

Có thể đưa `retryAfter`, `retryable`, `outcomeKnown`, nhưng không tuyên bố `retryable=true` cho mọi lỗi network chỉ vì server chưa kịp phân loại. Ứng dụng vẫn phải kiểm tra semantic safety.

### 28.3. Không tiết lộ thông tin quyền

Với tài nguyên thuộc tenant khác, không nên trả chi tiết “Order này thuộc tenant B” nếu caller không có quyền. Hệ thống vẫn cần log requestId và audit đủ để đội vận hành xử lý.

### 28.4. Tránh trả SUCCESS khi chỉ đã queue intent

Nếu downstream NoSQL mất quorum, API có thể nhận command vào durable queue và trả `202 PENDING` theo contract. Điều đó không bằng `201 RESERVATION_CONFIRMED`.

## 29. Observability cho retry

| Metric/tracing field | Giúp trả lời |
|---|---|
| Attempts per business request | Retry amplification có tăng không? |
| Retry success rate | Thử lại có thực sự hữu ích? |
| Final failures by category | Input, permission, throttling hay transient? |
| Unknown commit backlog | Bao nhiêu commands cần đối soát? |
| p95/p99 end-to-end latency | Retry làm chậm user bao nhiêu? |
| Retry sleep time | Tổng backoff tiêu tốn deadline |
| Per-operation retry rate | GET và mutation khác nhau ra sao? |
| Per-tenant retry rate | Noisy neighbor / quota issue |
| Leader/topology changes | Retry do failover tập trung ở đâu? |
| Transaction abort/conflict rate | Hot keys hoặc isolation contention |
| Throttled request rate | Capacity hoặc workload burst |
| Idempotency dedupe hit/mismatch | Retry lặp và key reuse sai |
| Deadline exceeded count | SLO budget có bị vượt? |
| Circuit breaker state | Dependency có đang bị bảo vệ? |
| DLQ/reconciliation lag | Workflows chưa hoàn thành |

### 29.1. Metric per attempt và per business command khác nhau

Một request business có thể tạo 4 DB attempts. Nếu chỉ đo số RPC success, tỷ lệ thành công trông tốt nhưng p99 và load có thể tệ. Cần cả metric final outcome trên **commandId**.

### 29.2. Trace IDs và command IDs

`requestId` có thể thay đổi qua retry, trong khi `commandId` nên ổn định cho một ý định. Trace correlation phải giữ được mối quan hệ cha–con để điều tra lost ACK và dedupe.

### 29.3. Đừng log secret hay PII không cần thiết

Không đưa access token, payment credentials, dữ liệu khách hàng hoặc payload nhạy cảm vào log lỗi chỉ để phân loại retry. Có thể dùng hashed identifiers/metadata đã bảo vệ.

### 29.4. Alert theo final outcomes, không chỉ raw exception counts

Transient error rồi retry thành công có ý nghĩa khác với 10% commands cuối cùng UNKNOWN. Thiết kế alert cho tỷ lệ lỗi cuối, backlog đối soát, retry budget exhaustion và invariant violations.

## 30. Fault injection và kiểm thử chính sách

Thử những tình huống có thể kiểm soát:

| Test | Tín hiệu | Kỳ vọng |
|---|---|---|
| Malformed input | 400/validation | Không retry; báo field |
| Token expired | 401 | Refresh hợp lệ có giới hạn, đánh giá lại safety |
| Permission denied | 403 | Không retry/không đổi tenant để né |
| Business quota exhausted | Domain rejection | Không retry tự động |
| Temporary 429 | Retry-After | Backoff, không vượt deadline |
| Known transaction abort | Retryable conflict label | Chạy lại toàn UoW với fresh read |
| Commit response lost | Timeout after server commit | UNKNOWN -> resolve commandId, không double mutate |
| Leader election | Stale topology | Refresh route và retry an toàn |
| Prolonged quorum loss | Repeated 503 | Dừng theo budget, mở circuit, trả unavailable/pending |
| Partial batch success | Per-item results | Retry chỉ items thích hợp |
| Dedupe key with different payload | Idempotency mismatch | Reject, không ghi |
| SDK retry + app retry | Nested retries | Không vượt global retry budget |

### 30.1. Kiểm thử lost ACK, không chỉ mất request

Giữ request tới DB, cho commit thành công, rồi drop response. Đây là cách phát hiện lỗi double-apply mà mock `throw TimeoutException` **trước khi thực hiện write** không thể bộc lộ.

### 30.2. Kiểm thử response đến sau deadline

Client ngừng chờ nhưng server vẫn commit vài milliseconds sau đó. Application phải đối soát, không để background retry tạo mutation trùng vì đã trả 504.

### 30.3. Kiểm thử retry callback transaction

Ép write conflict sau read để SDK chạy callback nhiều lần. Kiểm tra outbox chỉ chứa intent hợp lệ, không gọi email/payment trực tiếp từ mỗi attempt.

### 30.4. Kiểm thử phân quyền

Dùng token tenant A cố gọi vào tenant B, thiếu role và token hết hạn. Xác minh không tự đổi credential hoặc route qua owner khác để vượt permission denial.

### 30.5. Kiểm thử quota quá tải kéo dài

Giả lập 429 trong vài phút để xác nhận retry budget/circuit breaker và p99 không tăng không giới hạn. Nếu retry-after vượt deadline, caller dừng synchronous wait.

### 30.6. Không fault-inject production tùy tiện

Kill leader, chặn mạng, làm đầy disk hay sửa quyền trên dữ liệu thật cần quyền phê duyệt, guardrails và recovery procedure. Dùng môi trường cô lập với dữ liệu test cho các tình huống phá hủy.

## 31. JUnit: kiểm thử classifier với nhiều loại lỗi

Ví dụ test trên `RetryClassifier` ở mục 20:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RetryClassifierTest {
    private final RetryClassifier classifier = new RetryClassifier();

    private final OperationDescriptor safeRead =
        new OperationDescriptor("get-order", true, false, false);

    private final OperationDescriptor idempotentWrite =
        new OperationDescriptor("reserve", false, true, false);

    @Test
    void validationFailureDoesNotRetry() {
        var failure = new ClassifiedFailure(
            FailureKind.INPUT_INVALID,
            CommitKnowledge.DEFINITELY_NOT_COMMITTED,
            "INVALID_QTY",
            null
        );
        assertEquals(
            RetryAction.STOP_FIX_INPUT_OR_PERMISSION,
            classifier.classify(safeRead, failure)
        );
    }

    @Test
    void permissionFailureDoesNotRetry() {
        var failure = new ClassifiedFailure(
            FailureKind.AUTHORIZATION,
            CommitKnowledge.DEFINITELY_NOT_COMMITTED,
            "DENIED_TENANT",
            null
        );
        assertEquals(
            RetryAction.STOP_FIX_INPUT_OR_PERMISSION,
            classifier.classify(idempotentWrite, failure)
        );
    }

    @Test
    void throttleCanRetryAnIdempotentWrite() {
        var failure = new ClassifiedFailure(
            FailureKind.THROTTLED,
            CommitKnowledge.DEFINITELY_NOT_COMMITTED,
            "RATE_LIMIT",
            1000L
        );
        assertEquals(
            RetryAction.RETRY_SAME_SAFE_REQUEST,
            classifier.classify(idempotentWrite, failure)
        );
    }

    @Test
    void unknownWriteOutcomeRequiresResolution() {
        var failure = new ClassifiedFailure(
            FailureKind.TRANSIENT_TRANSPORT,
            CommitKnowledge.UNKNOWN,
            "TIMEOUT",
            null
        );
        assertEquals(
            RetryAction.RESOLVE_COMMIT_OUTCOME,
            classifier.classify(idempotentWrite, failure)
        );
    }

    @Test
    void knownTransactionAbortRetriesWholeUnit() {
        var failure = new ClassifiedFailure(
            FailureKind.TRANSACTION_ABORTED,
            CommitKnowledge.DEFINITELY_NOT_COMMITTED,
            "WRITE_CONFLICT",
            null
        );
        var tx = new OperationDescriptor(
            "transfer", false, true, true
        );
        assertEquals(
            RetryAction.RETRY_WHOLE_TRANSACTION,
            classifier.classify(tx, failure)
        );
    }
}
~~~

Đây là **unit-test skeleton**, không thay thế integration tests với SDK thật. Adapter từ vendor exception sang `ClassifiedFailure` phải được kiểm chứng riêng; nếu nó gán nhầm UNKNOWN thành `DEFINITELY_NOT_COMMITTED`, classifier sẽ đưa ra quyết định nguy hiểm dù unit tests đều pass.

### 31.1. Test dedupe dưới concurrency

Hai clients gửi cùng `(tenantId, commandId)` đồng thời. Kỳ vọng nguồn có thẩm quyền thực hiện mutation tối đa một lần, còn client còn lại nhận kết quả tương thích hoặc trạng thái chờ.

### 31.2. Test credential refresh

Ép 401, refresh token thành công và sau đó gửi lại **một request an toàn**. Với mutation có unknown outcome, classifier vẫn phải resolve trước khi phát lại.

### 31.3. Test idempotency TTL

Retry cùng commandId sau khi dedupe record hết TTL. Kỳ vọng của business phải được định nghĩa: từ chối command quá cũ, giữ lịch sử lâu hơn hoặc tái dựng từ authoritative ledger; không âm thầm áp lại mutation.

## 32. Quy trình xây retry policy cho một endpoint NoSQL

1. **Viết business intent.** `ReserveStock`, `CreateOrder`, `SetProfile` hoặc `GetCatalog` có semantics khác nhau.
2. **Xác định source of truth** và transaction/partition scope.
3. **Liệt kê side effects.** Database, event outbox, payment, email, cache invalidation.
4. **Xác định trạng thái commit có thể biết được.** Known commit, known reject/abort hay unknown.
5. **Định nghĩa stable commandId** cho những mutation có thể gửi lại.
6. **Bảo vệ dedupe atomically** cùng mutation hoặc bằng workflow có reconciliation.
7. **Map structured vendor errors** vào taxonomy, không parse string message.
8. **Phân loại input/auth/business errors** là terminal cho nguyên request.
9. **Phân biệt transaction abort** với unknown commit.
10. **Chọn retry scope:** một read RPC, whole transaction, route refresh hoặc durable workflow.
11. **Đặt deadline/maxAttempts/retry budget.**
12. **Dùng backoff có jitter**, tôn trọng `Retry-After`.
13. **Kiểm soát nested retries** ở SDK, repository, service và gateway.
14. **Áp dụng circuit breaker và admission control** cho lỗi kéo dài.
15. **Trả kết quả trung thực:** committed, rejected, pending hoặc unavailable.
16. **Bổ sung reconciliation** cho lệnh UNKNOWN sau deadline.
17. **Theo dõi metrics** theo commandId, operation, tenant, category, final outcome.
18. **Fault-inject** timeout sau commit, leader failover, conflicts, throttle, auth deny, partial batches.

### 32.1. Policy mẫu

~~~yaml
operation: reserve-inventory
sourceOfTruth: InventoryAuthority
intentKey: "(tenantId, commandId)"
mutation: "conditional decrement and record command outcome"

retry:
  transient:
    maxAttempts: 4
    baseBackoffMs: 100
    maxBackoffMs: 2000
    jitter: full
  deadline: "end-to-end request budget"
  throttle: "respect service retry hint"
  transactionAbort: "retry whole unit after fresh read"
  unknownCommit: "resolve by commandId; else PENDING"
  inputInvalid: "do not retry"
  permissionDenied: "do not retry"
  businessRejected: "do not retry"

idempotency:
  stableCommandIdRequired: true
  sameKeyDifferentPayload: "reject"
  retentionWindow: "<based on real request retry horizon>"

operational:
  circuitBreaker: "per dependency or partition"
  retryBudget: "<global budget>"
  metrics: "attempts, final outcomes, unknown backlog"
  testEvidence: "<integration fault-injection run>"
~~~

Các tham số số học chỉ để minh họa. Retry window và transaction semantics thực tế phải căn theo SLO, SDK và hợp đồng dữ liệu.

## 33. Những ngộ nhận phổ biến

### “Timeout nghĩa là server chưa ghi”

Sai. Server có thể đã commit trước khi response mất.

### “Hễ HTTP 500/503 thì retry mọi POST”

Không. POST có thể tạo side effect không idempotent hoặc outcome unknown.

### “Lỗi 4xx luôn không retry”

Quy tắc quá thô. 401 có thể cần refresh token đúng policy, 409 có thể là transaction conflict hoặc duplicate command; 429 thường cho phép retry có backoff.

### “429 chỉ cần retry nhanh hơn”

Ngược lại. Cần giảm tải, backoff, đọc retry hint và sửa hotspot/capacity nếu kéo dài.

### “409 Conflict nghĩa là database đã hỏng”

Không. Có thể là kết quả mong đợi của optimistic concurrency hoặc business uniqueness rule.

### “Gặp 412 thì bỏ ETag rồi ghi lại”

Nguy hiểm: mất optimistic concurrency và có thể ghi đè writer khác.

### “Không thấy record trong search index tức ghi thất bại”

Không. Search/projection có thể cập nhật bất đồng bộ.

### “Token hết hạn cứ retry cùng token”

Không. Cần refresh hợp lệ và đánh giá lại quyền/semantic safety.

### “403 sẽ tự hết nếu gửi đủ lần”

Không. Thiếu quyền cần thay đổi quyền hợp lệ, không brute-force.

### “Dùng UUID mới mỗi retry cho chắc”

Sai. Làm mất khả năng dedupe cùng ý định.

### “Có idempotency key trong request là đủ”

Không. Server phải enforce key/payload và mutation trong atomic boundary hoặc protocol tương đương.

### “Dedupe record có thể TTL bao lâu cũng được”

Không. Retry muộn hơn retention có thể tạo side effect lần hai.

### “Một transaction đã bị retry tự động nên callback chỉ chạy một lần”

Sai. Một số SDK có thể thực thi lại callback nhiều attempts.

### “Cứ retry UPDATE cũ khi transaction conflict”

Không. Phải đọc/validate lại toàn unit nếu isolation yêu cầu.

### “Retry count 3 ở mỗi tầng nghĩa tối đa 3 calls”

Không. Nhiều tầng có thể nhân số attempts.

### “Exponential backoff giải quyết mọi overload”

Không. Nếu load vượt capacity kéo dài, cần rate shaping, scale hoặc sửa thiết kế.

### “Read GET không thể gây vấn đề khi retry”

GET có thể tạo tải lớn, lock/read resources hoặc có side effect ngoài contract nếu thiết kế sai; deadline và backpressure vẫn cần.

### “Hủy HTTP request thì database tự rollback”

Không mặc định. Server có thể tiếp tục và commit.

### “Một lỗi đã được SDK đánh dấu retryable là an toàn cho mọi nghiệp vụ”

Không. SDK không nhất thiết biết external payment, quota hoặc command semantics.

### “Retry success rate cao nghĩa là hệ ổn định”

Không. Tỷ lệ retry cao có thể che tail latency, hot partitions và retry amplification.

### “Mọi lỗi permission/config là lỗi dữ liệu người dùng”

Không. Có thể là IAM/KMS/server configuration cần đội vận hành sửa; không trả message đổ trách nhiệm sang user.

### “Có consensus nên retry increment không thể double-apply”

Không. Consensus có thể commit cả hai request riêng biệt nếu application gửi hai command IDs khác nhau.

## 34. Bài tập thực hành

### Bài 1 — Phân loại theo ba nhóm

Cho các lỗi: malformed JSON, leader election, permission denied, transaction aborted, commit timeout, quota business exceeded, throttling 429, `ALREADY_EXISTS`. Hãy phân nhóm retry, sửa điều kiện và unknown outcome; nêu trường hợp phải biết thêm operation semantics.

### Bài 2 — Mất ACK sau commit

Một lệnh `DECR Stock by 2` đã commit nhưng client timeout. Thiết kế stable reservationId, dedupe store và authoritative lookup để không trừ lần hai.

### Bài 3 — 401 và 403

Phân biệt token hết hạn, token hợp lệ nhưng thiếu role và request truy cập tenant khác. Khi nào được refresh token, khi nào phải dừng?

### Bài 4 — 409 khác nhau

Một API trả 409 cho username trùng, một API trả 409 vì OCC conflict, API thứ ba trả 409 vì commandId trùng payload khác. Viết policy riêng cho từng trường hợp.

### Bài 5 — 412 ETag

Client đọc Profile ETag v7, writer khác cập nhật v8. Client update If-Match v7 bị 412. Hãy thiết kế UX merge hoặc re-read + validate; vì sao bỏ If-Match không chấp nhận được?

### Bài 6 — Read-after-write 404

Order đã commit ở primary nhưng search index trả 404. Thiết kế cách phân biệt read model lag với data loss, giới hạn bounded retry của search và nguồn đối soát.

### Bài 7 — Throttling 429

Một tenant tạo 5.000 writes/s vượt quota. Đề xuất backoff/jitter, Retry-After, admission control, per-tenant budget và xử lý workload kéo dài hơn capacity.

### Bài 8 — gRPC DEADLINE_EXCEEDED

Service `ReserveSeat` nhận `DEADLINE_EXCEEDED`. Vì sao không được coi là rollback? Thiết kế endpoint `GetCommandStatus(commandId)` và trạng thái PENDING.

### Bài 9 — MongoDB labels

Phân biệt transaction abort có label transient với unknown commit result. Mô tả retry whole transaction, retry commit theo SDK và lý do không charge payment trong callback.

### Bài 10 — DynamoDB conditional failure

Một conditional stock decrement trả `ConditionalCheckFailed`. Đây có phải signal để retry tức thì không? Nếu tồn kho sau đó tăng, nghiệp vụ nên kích hoạt request mới như thế nào?

### Bài 11 — Cosmos DB 429 và 412

So sánh một response RU throttling với ETag mismatch. Viết hai remediation paths và giải thích tại sao cả hai không được đưa vào cùng một while-loop.

### Bài 12 — Cassandra write timeout

Coordinator trả write timeout sau khi gửi mutation tới một số replicas. Phân tích rủi ro retry counter increment và cách thiết kế intent có commandId/ledger.

### Bài 13 — Redis INCR

Client gọi `INCR` rồi mất connection sau khi server xử lý. Hãy giải thích vì sao retry cùng lệnh có thể tăng hai lần và đề xuất Lua/atomic state với dedupe key trong phạm vi được hỗ trợ.

### Bài 14 — Nhiều tầng retry

Caller, API gateway, service và SDK mỗi tầng retry tối đa 3 attempts. Tính worst-case amplification theo mô hình lặp lồng nhau và đề xuất owner của budget end-to-end.

### Bài 15 — Full jitter

Với base=100 ms, cap=1.600 ms, hãy viết khoảng delay cho retry thứ 1 tới thứ 6. Nếu request deadline còn 250 ms, quyết định có ngủ thêm 400 ms không.

### Bài 16 — Transaction transfer

Transaction chuyển tiền bị serialization conflict đã được xác nhận abort. Viết pseudocode retry toàn UoW, re-read balances, kiểm tra điều kiện và bounded attempts.

### Bài 17 — Idempotency retention

Command dedupe TTL=1 giờ nhưng mobile client có thể retry sau 24 giờ. Phân tích cách duplicate có thể xảy ra và chọn chiến lược retention/old-command rejection.

### Bài 18 — Partial batch

Một import batch trả 3 committed, 2 throttled, 1 validation error, 1 unknown. Hãy thiết kế per-item checkpoint, retry decisions và reconciliation.

### Bài 19 — Circuit breaker

Database không có quorum trong 10 phút. Giải thích vì sao backoff 100 ms–2 s vẫn không đủ và cách dùng circuit breaker + PENDING state để bảo vệ service.

### Bài 20 — Error mapping adapter

Thiết kế Java adapter chuyển HTTP/gRPC/vendor exceptions thành `FailureKind`, `CommitKnowledge` và `RetryAction`. Liệt kê các structured fields phải lưu cho tracing mà không lộ secret.

### Bài 21 — Retry callback side effect

SDK tự retry transaction callback ba lần. Nếu callback gửi email và gọi payment gateway trước commit, chuyện gì có thể xảy ra? Chuyển sang outbox/idempotent consumer.

### Bài 22 — Fault injection

Viết test drop response **sau** database commit, không phải trước gửi request. Assert mutation chỉ xảy ra một lần dù client cố resolve/retry; thu commandId, attempts, committed status.

### Bài 23 — Auth + network ambiguity

Client gửi một write qua token hợp lệ rồi mất kết nối. Sau đó token hết hạn, lần retry thấy 401. Hãy phân biệt **credential refresh** với **resolve outcome của write đầu** và thiết kế thứ tự xử lý an toàn.

### Bài 24 — Review chính sách sai

Một tài liệu đề xuất “retry mọi 5xx, 409, 429 và timeout tối đa 100 lần; bỏ ETag khi conflict; refresh token khi 403; dùng ID mới mỗi attempt”. Hãy liệt kê các nguy cơ về security, data correctness, double write, overload và giới hạn end-to-end deadline.

---

**Kết luận:** Trong NoSQL phân tán, **không có một tập mã lỗi đơn giản nào cho biết cứ retry là đúng**. Cần phân biệt lỗi tạm thời có thể retry, lỗi phải sửa **input/quyền/business precondition**, và **commit outcome không rõ** khi response bị mất. Phân loại phải kết hợp **structured error, operation semantics, transaction scope, idempotency và deadline**. Với known transaction abort, retry toàn read–validate–write unit khi được API hỗ trợ; với validation/permission denial, dừng và sửa điều kiện; với timeout sau mutation, tra `commandId` ở nguồn có thẩm quyền thay vì nhân đôi ghi. Backoff, jitter, retry budgets và circuit breakers giúp bảo vệ hạ tầng, nhưng **chỉ idempotency và reconciliation đúng ranh giới mới bảo vệ tính đúng đắn của nghiệp vụ khi retry**.
