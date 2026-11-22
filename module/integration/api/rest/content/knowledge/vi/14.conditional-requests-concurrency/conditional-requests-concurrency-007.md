# 428 Precondition Required và chính sách bắt buộc điều kiện

## 1. Vì sao REST API phải yêu cầu điều kiện khi cập nhật?

Giả sử hai nhân viên cùng sửa đơn hàng **ord-123**:

~~~text
09:00  Cả A và B đọc đơn, version = 7, note = "Giao giờ hành chính"
09:01  A đổi note thành "Liên hệ trước 30 phút"
09:02  B đổi note thành "Để tại lễ tân" dựa trên dữ liệu cũ
~~~

Nếu server chấp nhận mọi PATCH mà không kiểm tra phiên bản, chỉnh sửa của B sẽ **ghi đè âm thầm** chỉnh sửa của A. Đây là **lost update**, một lỗi cạnh tranh phổ biến giữa nhiều client HTTP.

Giải pháp quen thuộc là **optimistic concurrency control**: server trả một validator đại diện phiên bản tài nguyên; client phải gửi lại validator đó dưới dạng điều kiện; server chỉ ghi khi tài nguyên vẫn phù hợp với điều kiện tại thời điểm ghi. Nhưng nếu một client cũ **không gửi điều kiện**, quy tắc chống ghi đè sẽ bị bỏ qua.

**428 Precondition Required** là mã trạng thái giúp server **từ chối request chưa mang điều kiện bắt buộc**. Khi kết hợp với **If-Match**, **412 Precondition Failed** và thao tác ghi nguyên tử, API có thể ngăn client sửa trên một phiên bản đã cũ.

Bài thuộc chương **Điều kiện và đồng thời** của module **INTEGRATION_API_REST**. Kiến thức này nối thiết kế resource, URI, phương thức và mã HTTP với hợp đồng ETag, PUT/PATCH/DELETE, cache, idempotency, OpenAPI, xác thực, phân quyền và kiểm thử Java/Spring.

Sau bài học, bạn có thể:

- Giải thích vì sao **428** khác **412**, **409**, **400**, **404**, **304**.
- Xây chính sách bắt buộc **If-Match** cho cập nhật/xóa và **If-None-Match: \*** cho thao tác chỉ tạo mới.
- Hiểu strong/weak ETag và mối quan hệ giữa validator của representation với version nội bộ.
- Triển khai so sánh phiên bản và ghi **nguyên tử trong database**, không chỉ kiểm tra trước bằng SELECT.
- Thiết kế Problem Details, OpenAPI, xử lý client, bảo mật và bài kiểm thử cạnh tranh.

## 2. Định nghĩa 428 theo HTTP

**RFC 6585** định nghĩa **428 Precondition Required**: origin server yêu cầu request phải có điều kiện. Một trường hợp điển hình là chính sách từ chối cập nhật không được ràng buộc với phiên bản hiện hành, để tránh lost update.

~~~http
PATCH /orders/ord-123 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json

{"note":"Gọi trước khi giao"}
~~~

Endpoint đã công bố bắt buộc **If-Match**, nhưng request thiếu header:

~~~http
HTTP/1.1 428 Precondition Required
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/precondition-required",
  "title": "Precondition required",
  "status": 428,
  "detail": "Cần đọc ETag hiện hành và gửi If-Match khi sửa đơn.",
  "code": "IF_MATCH_REQUIRED"
}
~~~

**Đặc điểm quan trọng:**

1. **428** cho biết request **chưa thỏa chính sách yêu cầu điều kiện**; không nói rằng một ETag cụ thể đã sai.
2. **428** có thể dùng cho PUT, PATCH, DELETE hoặc một request khác khi hợp đồng đòi precondition; không phải mọi method unsafe tự động cần 428.
3. **428 không tự chống lost update** nếu server không kiểm tra điều kiện đúng lúc ghi dữ liệu.
4. **Response 428 MUST NOT được lưu bởi cache** theo RFC 6585. Header **Cache-Control: no-store** trong ví dụ nhấn mạnh yêu cầu này.
5. Body có thể hướng dẫn cách sửa request. **Problem Details theo RFC 9457** là định dạng hữu ích nhưng không bắt buộc để phát 428.

### 2.1. Các chuẩn liên quan

| Chuẩn | Phạm vi |
| --- | --- |
| **RFC 6585** | Định nghĩa 428 và quy tắc response 428 không được cache lưu trữ. |
| **RFC 9110** | HTTP semantics, ETag, If-Match, If-None-Match, 304, 412 và đánh giá điều kiện. |
| **RFC 9457** | Problem Details cho phản hồi lỗi có cấu trúc. |
| **OpenAPI 3.1** | Công bố header bắt buộc và các response có thể xuất hiện. |

Chuẩn định nghĩa ý nghĩa giao thức; việc **endpoint nào bắt buộc điều kiện** vẫn là chính sách của ứng dụng.

## 3. ETag, strong validator và version nội bộ

GET một resource có thể trả ETag:

~~~http
GET /orders/ord-123 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v7"
Cache-Control: private, no-store

{"id":"ord-123","status":"PENDING","note":"Giao giờ hành chính"}
~~~

**ETag** là validator của **representation được chọn**, không nhất thiết là khóa chính hay một version database được lộ trực tiếp. Chuỗi **"order-v7"** chỉ là cách đặt tên minh họa, client phải coi nó là giá trị opaque và gửi lại nguyên vẹn.

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Resource** | Tài nguyên logic, ví dụ đơn hàng. |
| **Representation** | Biểu diễn trả qua HTTP, như JSON ứng với một thời điểm và biến thể. |
| **ETag** | Validator cho representation, có thể được so sánh ở conditional request. |
| **Version trong CSDL** | Dữ liệu nội bộ phục vụ optimistic locking; có thể dùng để phát ETag nếu giữ đúng semantics. |

### 3.1. Strong và weak ETag

~~~http
ETag: "order-v7"
~~~

Đây là dạng **strong entity tag**. Trong khi:

~~~http
ETag: W/"order-v7"
~~~

là **weak entity tag**.

**If-Match dùng phép so sánh mạnh (strong comparison)**. Một ETag yếu có tiền tố **W/** không thỏa phép so sánh mạnh với ETag strong, kể cả khi nội dung chuỗi giống nhau. Với chính sách chống ghi đè phiên bản cũ, nên cung cấp strong ETag mà server có thể xác minh đúng.

**If-None-Match dùng phép so sánh yếu (weak comparison)**, thường phù hợp cho xác thực cache trên GET. Không được giả định validator dùng được cho conditional GET cũng đủ chặt cho optimistic update.

### 3.2. Strong ETag phải phản ánh representation thật

Phát **"order-v7"** như strong ETag chỉ đúng khi server bảo đảm các thay đổi cần phân biệt ở representation đều dẫn tới validator tương ứng khác. Ví dụ nếu JSON có trường **status** nhưng service đổi status mà không tăng version, một ETag sinh từ version đó không còn đáp ứng đúng nghĩa strong validator.

Khi có nhiều biến thể (JSON đầy đủ/rút gọn, ngôn ngữ, content coding), cần thiết kế validator theo representation đã chọn. Không mặc nhiên phát một strong ETag chung cho các byte representation khác nhau.

### 3.3. Last-Modified có thay If-Match được không?

HTTP còn có **If-Unmodified-Since**, ví dụ:

~~~http
If-Unmodified-Since: Wed, 18 Nov 2026 10:00:00 GMT
~~~

Nhưng độ phân giải của HTTP-date thường tính theo giây; nhiều thay đổi có thể xảy ra trong một giây. Với ghi cạnh tranh nhạy cảm, **If-Match + strong ETag** thường phù hợp hơn. Nếu chính sách yêu cầu If-Match, đừng chấp nhận một header thời gian bất kỳ như cơ chế tương đương mà chưa đánh giá độ an toàn.

## 4. Luồng GET → If-Match → PATCH

### 4.1. Bước đọc

~~~http
GET /orders/ord-123 HTTP/1.1

HTTP/1.1 200 OK
ETag: "order-v7"
Content-Type: application/json

{"id":"ord-123","status":"PENDING","note":"Giao giờ hành chính"}
~~~

### 4.2. Bước cập nhật thành công

~~~http
PATCH /orders/ord-123 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "order-v7"

{"note":"Liên hệ trước 30 phút"}

HTTP/1.1 200 OK
ETag: "order-v8"
Content-Type: application/json

{"id":"ord-123","status":"PENDING","note":"Liên hệ trước 30 phút"}
~~~

Các khối trên minh họa request và response nối tiếp. Server kiểm tra version 7 và ghi cập nhật đồng thời đổi validator lên 8. Nếu không cần trả body, API có thể dùng **204 No Content** khi thành công, nhưng không được mang JSON trong body 204.

### 4.3. Bước cập nhật từ client khác đã lỗi thời

Client B trước đó cũng đọc v7 nhưng gửi sau khi A đã cập nhật:

~~~http
PATCH /orders/ord-123 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "order-v7"

{"note":"Để tại lễ tân"}

HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type":"https://api.example.com/problems/stale-representation",
  "title":"Precondition failed",
  "status":412,
  "detail":"Đơn đã thay đổi; hãy đọc lại trước khi sửa.",
  "code":"RESOURCE_VERSION_MISMATCH"
}
~~~

Client nên tải lại dữ liệu và **xem xét/hoà giải** thay đổi của A. Nếu client tự động tải bản mới rồi ghi lại payload cũ mà không kiểm tra, nó có thể tái tạo mất cập nhật **ở cấp nghiệp vụ**, dù thao tác giao thức đã dùng đúng ETag.

### 4.4. Minh họa cạnh tranh

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant API as Orders API
    participant DB as Database
    A->>API: GET /orders/123
    API-->>A: 200 ETag v7
    B->>API: GET /orders/123
    API-->>B: 200 ETag v7
    A->>API: PATCH If-Match v7
    API->>DB: UPDATE WHERE version=7
    DB-->>API: 1 row updated, version=8
    API-->>A: 200 ETag v8
    B->>API: PATCH If-Match v7
    API->>DB: UPDATE WHERE version=7
    DB-->>API: 0 rows updated
    API-->>B: 412 Precondition Failed
~~~

## 5. Phân biệt 428, 412, 409, 400, 404 và 304

| Tình huống | Status | Giải thích |
| --- | --- | --- |
| PATCH endpoint bắt buộc If-Match, nhưng request không gửi. | **428** | Thiếu loại điều kiện bắt buộc. |
| PATCH gửi If-Match hợp lệ nhưng validator cũ. | **412** | Precondition đã được đánh giá nhưng không thỏa. |
| PUT create-only có If-None-Match: * nhưng resource đã tồn tại. | **412** | Điều kiện “chưa tồn tại” không đúng. |
| If-Match khớp nhưng đơn đã SHIPPED và không được hủy. | **409** | Xung đột luật nghiệp vụ, không phải ETag cũ. |
| Giá trị If-Match sai cú pháp hoặc trái hợp đồng parser đã công bố. | **400** | Header không hợp lệ. |
| Request tới resource không tồn tại hoặc không được tiết lộ. | **404** | Kết quả tùy thứ tự kiểm tra và chính sách quyền. |
| GET có If-None-Match khớp bản cache. | **304** | Không gửi lại body representation; không phải lỗi ghi. |
| Thiếu hoặc không hợp lệ credentials. | **401** | Lỗi xác thực, không tự thay bằng 428. |
| Client không được phép thay đổi resource. | **403** hoặc **404** để che tồn tại | Bảo vệ ranh giới quyền trước khi để lộ tình trạng phiên bản. |

Tóm tắt:

~~~text
Thiếu điều kiện mà endpoint bắt buộc -> 428 Precondition Required
Có điều kiện nhưng đánh giá false    -> 412 Precondition Failed
Điều kiện đúng, business state cấm   -> 409 Conflict
~~~

### 5.1. Resource không tồn tại: 404 hay 412?

Không có một câu trả lời cố định cho mọi method và header. Với If-Match chỉ rõ một entity tag mà resource không có representation hiện hành, điều kiện không thể khớp và có thể dẫn đến **412** khi server đánh giá precondition. Nhưng server còn phải kiểm tra authentication, authorization, điều kiện request thông thường và chính sách không tiết lộ; **404/403** có thể được trả trước theo ngữ nghĩa và thứ tự kiểm tra.

Không nên ép mọi tình huống ID không tồn tại thành 412 hay 404 một cách máy móc; hãy kiểm thử thứ tự xử lý và ghi tài liệu rõ ràng.

### 5.2. If-Match: * có giống strong ETag không?

**Không.** Header:

~~~http
If-Match: *
~~~

chỉ yêu cầu có representation hiện hành; nó không chứng minh client vừa đọc một phiên bản cụ thể. Nếu chính sách là “chỉ sửa đúng version đã đọc”, cần một **strong ETag cụ thể**. Server phải từ chối wildcard theo hợp đồng đó thay vì xem * như validator đúng cho mọi version. Có thể dùng 428 khi chưa đáp ứng loại điều kiện bắt buộc, hoặc 400 nếu chính sách định dạng header được tài liệu hóa theo hướng đó; quan trọng là không âm thầm bỏ qua bảo vệ.

Theo HTTP, If-Match còn cho phép **danh sách entity tag**; ví dụ sau chỉ minh họa một tag cụ thể. Hệ thống công bố hỗ trợ đầy đủ HTTP conditional semantics phải dùng parser và phép so sánh tuân chuẩn.

## 6. Ma trận chính sách theo loại thao tác

| Endpoint | Điều kiện nên yêu cầu | Thiếu điều kiện | Điều kiện không thỏa |
| --- | --- | --- | --- |
| **GET /orders/{id}** | If-None-Match tùy chọn cho cache. | GET bình thường, thường **200**. | ETag trùng có thể **304**, không phải 428. |
| **PATCH /orders/{id}** | **If-Match** với strong ETag cụ thể. | **428** | **412** |
| **PUT /orders/{id}** khi thay thế | **If-Match** khi thay thế resource hiện hành. | **428** | **412** |
| **DELETE /orders/{id}** nhạy cảm | **If-Match** khi yêu cầu xác nhận phiên bản muốn xóa. | **428** | **412** |
| **PUT /draft-orders/{clientId}** chỉ tạo | **If-None-Match: \***. | **428** | **412** nếu đã có. |
| **POST /orders** server cấp ID | Idempotency-Key khi nghiệp vụ cần chống tạo trùng; không tự yêu cầu If-Match. | Không mặc định 428. | Xử lý theo cơ chế idempotency/xung đột riêng. |
| **POST /orders/{id}/cancel** | Có thể yêu cầu If-Match cho hành động dựa trên version. | **428** nếu chính sách bắt buộc. | **412** nếu version sai; **409** nếu version đúng nhưng nghiệp vụ cấm hủy. |

Đây là chính sách **minh họa**, không bắt mọi API phải áp dụng đúng cùng các endpoint. Middleware áp dụng 428 cho **mọi POST/PUT/PATCH/DELETE** sẽ sai với nhiều thao tác tạo, upload, callback hoặc command có quy tắc concurrency khác.

### 6.1. If-Match và If-None-Match giải quyết hai việc khác nhau

- **If-Match: "order-v7"**: chỉ thực hiện khi representation hiện hành phù hợp validator đã đọc.
- **If-None-Match: \***: chỉ thực hiện nếu resource chưa có representation hiện hành; thường dùng cho PUT **create-only**.

Không dùng If-None-Match: * cho một cập nhật resource đã tồn tại, và không yêu cầu client biết ETag của một đơn hoàn toàn chưa được tạo khi gọi POST collection.

### 6.2. PUT create-only với ID client chọn

~~~http
PUT /draft-orders/0c48ec7a-8a14-4a71-ac0a-b8dd06dd0f88 HTTP/1.1
Content-Type: application/json

{"note":"Đơn nháp tạo khi ngoại tuyến"}

HTTP/1.1 428 Precondition Required
Cache-Control: no-store
~~~

Client gửi điều kiện:

~~~http
PUT /draft-orders/0c48ec7a-8a14-4a71-ac0a-b8dd06dd0f88 HTTP/1.1
If-None-Match: *
Content-Type: application/json

{"note":"Đơn nháp tạo khi ngoại tuyến"}

HTTP/1.1 201 Created
Location: /draft-orders/0c48ec7a-8a14-4a71-ac0a-b8dd06dd0f88
~~~

Nếu URI đã có resource, cùng If-None-Match: * sẽ thất bại và trả **412**. Đặc biệt, khi request đầu đã tạo thành công nhưng client mất response, retry có thể nhận 412. Client phải GET và đối chiếu resource theo ID và quyền, **không suy ra request đầu thất bại rồi cấp ID khác ngay**.

### 6.3. 428 không phải biện pháp chống POST bị lặp

Khi POST tạo thanh toán hoặc đơn hàng với ID do server cấp, client chưa có ETag của resource mới. Để retry sau timeout mà không phát sinh hai tác dụng phụ, nên thiết kế **Idempotency-Key**, khóa nghiệp vụ, transaction và cách tra cứu kết quả. Bắt gửi If-Match vô nghĩa cho POST tạo resource mới không thay thế được cơ chế đó.

## 7. Kiểm tra precondition phải nguyên tử với thao tác ghi

Mẫu sai:

~~~text
1. SELECT version FROM orders WHERE id = 123;  // v7
2. So If-Match với v7, kết luận hợp lệ
3. Request khác ghi version thành v8
4. UPDATE orders SET note = ... WHERE id = 123; // ghi đè vô điều kiện
~~~

Đây là lỗi *time-of-check to time-of-use* (TOCTOU). Đọc và kiểm tra trước chưa đủ.

### 7.1. Compare-and-swap bằng SQL

~~~sql
UPDATE orders
SET note = :note,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :order_id
  AND tenant_id = :tenant_id
  AND version = :expected_version;
~~~

Nếu **1 dòng** được cập nhật, yêu cầu đã ghi lên version mong đợi. Nếu **0 dòng**, có thể version thay đổi, resource không tồn tại hoặc không thuộc tenant được phép. Cần phân loại an toàn theo quyền và kết quả hiện hành, không tự động trả 412 cho mọi trường hợp.

PostgreSQL có thể trả dữ liệu mới bằng **RETURNING**:

~~~sql
UPDATE orders
SET note = :note,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :order_id
  AND tenant_id = :tenant_id
  AND version = :expected_version
RETURNING id, note, status, version, updated_at;
~~~

**Version check và UPDATE nằm trong cùng câu SQL**, giúp hai request cùng version không thể đồng thời sửa thành công một hàng. Khi dùng JPA/Hibernate, **@Version** có thể hỗ trợ optimistic locking, nhưng application vẫn phải kiểm tra HTTP precondition và ánh xạ kết quả đúng, không trả 500 cho cạnh tranh hợp lệ.

### 7.2. Không bỏ sót trường và đường cập nhật

Nếu một endpoint PATCH cập nhật note và tăng version nhưng một batch job lại sửa status mà không tăng version, strong ETag dựa trên version không còn phản ánh đúng representation. Cần cơ chế thống nhất cho **mọi đường ghi** và định nghĩa ETag phù hợp từng representation.

### 7.3. Cross-resource và side effect

If-Match bảo vệ điều kiện trên resource được đánh giá, nhưng không tự bảo đảm tính đúng của:

- Tồn kho ở resource khác.
- Thanh toán qua dịch vụ bên ngoài.
- Queue/event phát sau cập nhật.
- Các điều kiện nghiệp vụ phân tán.

Cần thêm transaction, ràng buộc dữ liệu, transactional outbox, idempotency và quy tắc phục hồi khi phù hợp. **428 là cổng bắt buộc điều kiện, không phải toàn bộ chiến lược đồng thời.**

## 8. Thiết kế body lỗi nhất quán với Problem Details

**Problem Details theo RFC 9457** cung cấp cấu trúc lỗi có thể tái sử dụng cho 428/412/409, với media type **application/problem+json**. Ví dụ cho request thiếu If-Match:

~~~http
HTTP/1.1 428 Precondition Required
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-7af1

{
  "type": "https://api.example.com/problems/precondition-required",
  "title": "Precondition required",
  "status": 428,
  "detail": "Endpoint này yêu cầu strong ETag trong If-Match.",
  "instance": "/problems/occurrences/req-7af1",
  "requiredHeaders": ["If-Match"],
  "code": "IF_MATCH_REQUIRED",
  "requestId": "req-7af1"
}
~~~

Các trường **type**, **title**, **status**, **detail**, **instance** thuộc mô hình chuẩn. **requiredHeaders**, **code** và **requestId** là **extension do API tự định nghĩa**. Không dùng chuỗi ngôn ngữ tự nhiên của detail/title làm khóa logic client; **type/code** nên ổn định.

Một phản hồi 412:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/precondition-failed",
  "title": "Precondition failed",
  "status": 412,
  "detail": "Dữ liệu đã thay đổi từ lần đọc trước.",
  "code": "STALE_RESOURCE_VERSION"
}
~~~

Khi client không có quyền xem bản mới, không trả toàn bộ dữ liệu hiện tại hoặc ETag mới trong body để “giúp sửa lỗi”. Cần bảo vệ tenant, tài khoản và quyền ngay trong các nhánh lỗi.

### 8.1. Khi nào nên trả 409 thay vì 412?

Giả sử client đọc **"order-v8"** và gửi hành động hủy đơn:

~~~http
POST /orders/ord-123/cancel HTTP/1.1
If-Match: "order-v8"
~~~

Nếu version vẫn là 8 nhưng trạng thái đã là SHIPPED (và validator thật sự phản ánh trạng thái được dùng), thao tác bị từ chối do **luật nghiệp vụ**:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "code": "ORDER_ALREADY_SHIPPED"
}
~~~

Trong thực tế, nếu SHIPPED vừa được ghi sau lúc client đọc, validator đúng lẽ ra cũng phải đổi và client cũ nhận 412. Ví dụ 409 hợp lý khi client **thực sự đang dùng phiên bản hiện hành**, nhưng hành động vẫn không được phép theo trạng thái nghiệp vụ. Phân biệt này giúp SDK đưa ra hướng khắc phục đúng.

## 9. Java/Spring: bắt buộc If-Match ở lớp API

Ví dụ dùng **Spring Boot 3 / Spring Framework 6**, Spring MVC và database có cột version. Tất cả class/service dưới đây minh họa contract; production phải bổ sung validation, security, repository và transaction cụ thể.

### 9.1. DTO và service interface

~~~java
import java.util.UUID;

record OrderView(
        UUID id,
        String status,
        String note,
        long version) {}

record ChangeNoteRequest(String note) {}

interface OrderCommandService {
    OrderView getAuthorized(UUID id);
    OrderView updateNoteIfVersion(
            UUID id, long expectedVersion, String note);
}

class PreconditionRequiredException extends RuntimeException {}
class PreconditionFailedException extends RuntimeException {}
class InvalidConditionalHeaderException extends RuntimeException {}
~~~

Trong ví dụ này, **getAuthorized** và **updateNoteIfVersion** phải xác định tenant/actor từ danh tính đã xác thực ở server, không tin chỉ một UUID do client gửi. Những thay đổi làm đổi representation phải làm version thay đổi nhất quán.

Ví dụ PATCH chỉ xử lý một trường note và giả định request luôn chứa giá trị hợp lệ cho trường này. Với **application/merge-patch+json** đúng nghĩa, việc **thiếu trường** khác với việc **gửi null để xóa trường**; một DTO đơn giản có thể không phân biệt được hai trường hợp. Hệ thống thật cần validate cấu trúc patch và cài đặt đầy đủ JSON Merge Patch theo hợp đồng trước khi ghi.

### 9.2. Codec cho một strong ETag có định dạng cố định

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class OrderEtags {
    private static final Pattern SINGLE_TAG =
            Pattern.compile("\"order-v([1-9][0-9]*)\"");

    private OrderEtags() {}

    static String fromVersion(long version) {
        return "\"order-v" + version + "\"";
    }

    static long requireSingleVersion(String ifMatch) {
        if (ifMatch == null || ifMatch.isBlank()) {
            throw new PreconditionRequiredException();
        }

        Matcher matcher = SINGLE_TAG.matcher(ifMatch.trim());
        if (!matcher.matches()) {
            throw new InvalidConditionalHeaderException();
        }
        try {
            return Long.parseLong(matcher.group(1));
        } catch (NumberFormatException ex) {
            throw new InvalidConditionalHeaderException();
        }
    }
}
~~~

**Giới hạn có chủ ý:** codec này chỉ chấp nhận **một strong tag** theo định dạng riêng của Orders API, không phải parser tổng quát cho mọi giá trị If-Match hợp lệ của HTTP. HTTP hỗ trợ danh sách entity tag và wildcard; nếu API tuyên bố hỗ trợ đầy đủ, phải dùng parser/strong comparison đúng chuẩn. Nếu chính sách ngăn lost update yêu cầu validator cụ thể, hệ thống có thể **từ chối wildcard và weak validator theo contract được công bố**, nhưng không được âm thầm xem chúng là phiên bản hợp lệ.

Đừng chỉ thay version số bằng chuỗi rồi tự nhận đã có strong ETag. Việc phiên bản tăng trên **mọi thay đổi làm representation cần được phân biệt** là một điều kiện tiên quyết.

### 9.3. Controller phát ETag và trả 428 khi thiếu

~~~java
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/orders")
class OrderConcurrencyController {
    private final OrderCommandService service;

    OrderConcurrencyController(OrderCommandService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> get(@PathVariable UUID id) {
        OrderView value = service.getAuthorized(id);
        return ResponseEntity.ok()
                .eTag(OrderEtags.fromVersion(value.version()))
                .body(value);
    }

    @PatchMapping(
            path = "/{id}",
            consumes = "application/merge-patch+json")
    ResponseEntity<OrderView> patch(
            @PathVariable UUID id,
            @RequestHeader(
                    value = HttpHeaders.IF_MATCH,
                    required = false)
            String ifMatch,
            @RequestBody ChangeNoteRequest body) {

        long version = OrderEtags.requireSingleVersion(ifMatch);
        OrderView changed = service.updateNoteIfVersion(
                id, version, body.note());

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .eTag(OrderEtags.fromVersion(changed.version()))
                .body(changed);
    }
}
~~~

**Điểm quan trọng của required = false:** nếu để **@RequestHeader** tự từ chối khi thiếu, Spring MVC thường sinh **400 Bad Request** ở bước binding, trước khi chính sách 428 của controller được áp dụng. Bằng cách tự kiểm tra thiếu header, server có thể trả đúng status **428** theo hợp đồng.

Phần kiểm tra If-Match nên được dùng thống nhất qua những endpoint ghi cần bảo vệ, nhưng **không áp middleware bắt điều kiện cho mọi POST**.

### 9.4. ControllerAdvice ánh xạ 428, 412, 400

~~~java
import java.net.URI;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ConcurrencyProblemHandler {

    @ExceptionHandler(PreconditionRequiredException.class)
    ResponseEntity<ProblemDetail> required() {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.PRECONDITION_REQUIRED,
                "Cần gửi strong ETag trong If-Match.");
        problem.setTitle("Precondition required");
        problem.setType(URI.create(
                "https://api.example.com/problems/precondition-required"));
        problem.setProperty("code", "IF_MATCH_REQUIRED");

        return ResponseEntity
                .status(HttpStatus.PRECONDITION_REQUIRED)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(problem);
    }

    @ExceptionHandler(PreconditionFailedException.class)
    ResponseEntity<ProblemDetail> failed() {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.PRECONDITION_FAILED,
                "Resource đã thay đổi; hãy đọc lại trước khi sửa.");
        problem.setTitle("Precondition failed");
        problem.setType(URI.create(
                "https://api.example.com/problems/precondition-failed"));
        problem.setProperty("code", "STALE_RESOURCE_VERSION");

        return ResponseEntity
                .status(HttpStatus.PRECONDITION_FAILED)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(problem);
    }

    @ExceptionHandler(InvalidConditionalHeaderException.class)
    ResponseEntity<ProblemDetail> invalid() {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "If-Match không đúng định dạng được API hỗ trợ.");
        problem.setTitle("Invalid conditional header");
        problem.setType(URI.create(
                "https://api.example.com/problems/invalid-precondition"));

        return ResponseEntity
                .status(HttpStatus.BAD_REQUEST)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~

Trong dự án thật, **401/403 từ Spring Security** có thể phát sinh trước controller/advice; 404 khi không tìm thấy resource và 409 khi vi phạm luật nghiệp vụ cũng cần handler riêng. Handler chung không được bắt mọi exception rồi biến thành 428.

## 10. Triển khai atomic update và xử lý race

Với **NamedParameterJdbcTemplate**, có thể triển khai thao tác ghi chính như sau:

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

class OrderWriteRepository {
    private final NamedParameterJdbcTemplate jdbc;

    OrderWriteRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    int changeNote(
            UUID id,
            long tenantId,
            long expectedVersion,
            String note) {

        var params = new MapSqlParameterSource()
                .addValue("id", id)
                .addValue("tenantId", tenantId)
                .addValue("expectedVersion", expectedVersion)
                .addValue("note", note);

        return jdbc.update("""
            UPDATE orders
               SET note = :note,
                   version = version + 1
             WHERE id = :id
               AND tenant_id = :tenantId
               AND version = :expectedVersion
            """, params);
    }
}
~~~

Service gọi repository và phân loại kết quả:

~~~text
validate authenticated principal and tenant permission
parse strong If-Match from request
perform UPDATE with tenant_id + id + expected_version
if affected rows == 1:
    read updated representation consistently
    return 200/204 and valid new ETag when appropriate
else:
    if resource not visible/does not exist:
        return 404 or 403 according to policy
    return 412 Precondition Failed
~~~

**Ví dụ code mới thể hiện phần update**, còn service phải kiểm tra quyền, ánh xạ 404/403, đọc lại representation trong giao dịch phù hợp và tránh trả ETag không đúng dữ liệu. Nếu có nhiều câu lệnh nghiệp vụ hoặc gửi event, cần transaction/outbox hoặc một cơ chế bảo đảm nhất quán tương đương.

### 10.1. Tại sao không chỉ SELECT rồi mới UPDATE?

Hai request có thể cùng SELECT thấy v7, cùng đánh giá If-Match đúng và sau đó cùng ghi nếu UPDATE không giới hạn theo version. Cần đặt **version = :expectedVersion** trong điều kiện SQL ghi, hoặc sử dụng optimistic locking thật sự ở ORM.

### 10.2. Nếu dùng JPA/Hibernate

Một entity có **@Version** có thể giúp phát hiện cập nhật đồng thời; framework sẽ cập nhật có điều kiện theo version/giám sát dirty state. Nhưng API vẫn phải:

- Yêu cầu header If-Match theo chính sách.
- Ánh xạ validator sang version/representation đúng.
- Chuyển lỗi optimistic locking thành **412** nếu đúng là HTTP precondition thất bại.
- Bảo đảm mọi đường ghi, kể cả batch update, không bỏ qua cơ chế version.

**@Version không tự thêm 428 vào hợp đồng HTTP**, và ETag cũng không tự sinh một cách đúng semantics chỉ nhờ annotation đó.

## 11. OpenAPI 3.1: công bố header và mã lỗi

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders/{id}:
    get:
      summary: Đọc tài nguyên và strong ETag
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string, format: uuid}
      responses:
        '200':
          description: Trả đơn hàng kèm validator
          headers:
            ETag:
              description: Validator của representation trả về
              schema: {type: string}
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Order'}
        '304':
          description: Conditional GET không có thay đổi
        '404':
          description: Không tìm thấy đơn
    patch:
      summary: Cập nhật ghi chú bằng optimistic concurrency
      description: >
        Bắt buộc strong If-Match. Thiếu điều kiện trả 428,
        stale ETag trả 412, xung đột nghiệp vụ trả 409.
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string, format: uuid}
        - in: header
          name: If-Match
          required: true
          description: Strong ETag đã nhận từ GET
          schema: {type: string}
          example: '"order-v7"'
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema: {$ref: '#/components/schemas/ChangeNote'}
      responses:
        '200':
          description: Đã cập nhật và trả representation mới
          headers:
            ETag:
              description: Validator mới nếu có thể cấp hợp lệ
              schema: {type: string}
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Order'}
        '400':
          description: Header điều kiện hoặc request không hợp lệ
        '401':
          description: Chưa xác thực hợp lệ
        '403':
          description: Không có quyền sửa đơn
        '404':
          description: Không tìm thấy resource theo chính sách
        '409':
          description: Xung đột trạng thái nghiệp vụ
        '412':
          description: Validator đã gửi không còn khớp
          content:
            application/problem+json:
              schema: {$ref: '#/components/schemas/Problem'}
        '428':
          description: Thiếu điều kiện bắt buộc
          headers:
            Cache-Control:
              description: No-store; cache không được lưu 428
              schema: {type: string}
          content:
            application/problem+json:
              schema: {$ref: '#/components/schemas/Problem'}
components:
  schemas:
    Order:
      type: object
      required: [id, status, note]
      properties:
        id: {type: string, format: uuid}
        status: {type: string}
        note: {type: string}
    ChangeNote:
      type: object
      properties:
        note: {type: string}
    Problem:
      type: object
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
        code: {type: string}
      additionalProperties: true
~~~

OpenAPI **required: true** cho header không bảo đảm server tự trả 428. Nếu framework từ chối thiếu header bằng 400 hoặc gateway bỏ qua header, contract runtime sẽ không giống tài liệu; cần cấu hình và kiểm thử đến tầng HTTP thực.

Trích đoạn trên mới mô tả GET/PATCH. Endpoint **PUT create-only** phải có **If-None-Match**, 201/412/428 và schema riêng; **POST** tạo thanh toán cần công bố Idempotency-Key nếu hỗ trợ.

## 12. An toàn khi dùng precondition với cache, replica và gateway

### 12.1. GET có điều kiện và 304 không thay thế 428

~~~http
GET /orders/ord-123 HTTP/1.1
If-None-Match: "order-v7"

HTTP/1.1 304 Not Modified
ETag: "order-v7"
~~~

**304 không có body** và được dùng cho truy xuất có điều kiện theo semantics HTTP. **PATCH/PUT/DELETE** với If-Match sai trả **412**, không trả 304.

Một response 428 **không được cache lưu trữ**. Các lỗi chứa dữ liệu người dùng/tenant nên có chính sách Cache-Control thích hợp, thường dùng **no-store** nếu không muốn lưu. ETag không tự khiến nội dung an toàn để cache công khai; Authorization và quyền từng tenant vẫn phải được tôn trọng.

### 12.2. Đọc từ replica có độ trễ

Giả sử GET tới read replica cho ETag **"order-v7"**, nhưng primary đã commit **"order-v8"**. Client PATCH theo v7 đến primary phải nhận **412**. Không được bỏ kiểm tra vì client “vừa mới lấy ETag”; trong kiến trúc eventual consistency, bản đọc có thể đã cũ.

Ứng dụng có thể cần cơ chế read-your-writes, đọc primary khi cần hợp nhất, hoặc hiển thị trạng thái cập nhật lại. Điều kiện cuối cùng phải được kiểm tra ở nơi có quyền quyết định **commit**.

### 12.3. Gateway và security filters

Một reverse proxy có thể phát lỗi trước khi request đến controller. Spring Security có thể trả **401/403** trước khi chạy ControllerAdvice. Hãy xác định:

- Nơi kiểm tra authentication và quyền tài nguyên.
- Nơi yêu cầu If-Match/If-None-Match theo từng endpoint.
- Nơi đánh giá validator và cập nhật nguyên tử.
- Nơi ánh xạ 400/401/403/404/409/412/428 sang Problem Details.
- Header nào gateway được phép chuyển hoặc sửa.

Đừng để gateway chỉ kiểm tra sự có mặt của If-Match rồi mặc nhiên tin controller sẽ cập nhật an toàn: database vẫn phải đánh giá điều kiện ngay khi ghi.

## 13. Client phải xử lý 428, 412 và retry ra sao?

### 13.1. Khi nhận 428

428 thường báo **client chưa tuân thủ hợp đồng** của endpoint. Hành động phù hợp:

1. Đọc mã HTTP và Problem Details để biết cần header nào.
2. GET tài nguyên nếu được phép và lấy strong ETag hiện hành.
3. Đọc/hiển thị nội dung mới cho người dùng, nhất là khi đang cập nhật một biểu mẫu.
4. Xây request mới dựa trên trạng thái đã được xem xét và gửi If-Match đúng.

**Không tự bịa ETag** bằng cách tăng version dự đoán, và không chỉ gửi một chuỗi bất kỳ cho đủ điều kiện.

### 13.2. Khi nhận 412

412 cho biết điều kiện được gửi **không thỏa**. Client có thể GET lại, hiển thị thay đổi của người khác, hòa giải dữ liệu hoặc hủy thao tác. Tự động lấy ETag mới rồi retry cùng payload mà không xem dữ liệu mới có thể tạo ra tình trạng ghi đè ở **cấp quyết định nghiệp vụ**.

Ví dụ, B muốn sửa ghi chú từ “Giao giờ hành chính” sang “Để tại lễ tân”, nhưng A đã đổi thành “Liên hệ trước 30 phút”. Sau 412, B cần quyết định liệu ghi đè thông điệp của A có hợp lý hay không; không chỉ sửa header rồi tiếp tục.

### 13.3. Khi nhận 409

409 thường cần một giải pháp **nghiệp vụ**: trạng thái SHIPPED không cho hủy, số lượng hàng không đủ hoặc resource đang ở trạng thái không cho thao tác. Dù client lấy ETag mới, lặp lại yêu cầu chưa chắc giúp gì. Dùng **problem type/code** ổn định để hiển thị hướng dẫn phù hợp.

### 13.4. Khi mất phản hồi

Nếu PATCH đã commit nhưng response bị mất, lần retry cùng If-Match cũ có thể nhận 412. **412 không chứng minh thao tác đầu thành công hay thất bại**: client phải đọc trạng thái để xác minh, hoặc dựa vào cơ chế idempotency/operation ID khi có tác dụng phụ cần biết kết quả duy nhất.

Đối với **POST /payments**, ETag không thay thế **Idempotency-Key**. Khi gateway trả 504, backend có thể đã trừ tiền; retry phải dùng cùng khóa và hệ thống phía server phải thực thi chống trùng. **Conditional request và idempotency giải quyết các vấn đề có liên quan nhưng không giống nhau**.

## 14. Kiểm thử hợp đồng và tính nguyên tử

### 14.1. Ma trận kiểm thử

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| T01 | GET resource hợp lệ | **200**, strong ETag và body đúng. |
| T02 | PATCH thiếu If-Match khi policy bắt buộc | **428**, no-store, Problem Details; **DB không thay đổi**. |
| T03 | PATCH strong If-Match khớp | **200/204** theo hợp đồng; version thay đổi và dữ liệu mới đúng. |
| T04 | PATCH dùng ETag cũ | **412**, không ghi đè bất kỳ trường nào. |
| T05 | Hai PATCH đồng thời cùng ETag | Chỉ một request thắng; request còn lại **412**; không lost update. |
| T06 | PATCH dùng weak ETag | Không được xem là strong match; xử lý theo chính sách/HTTP, không ghi vô điều kiện. |
| T07 | PATCH dùng giá trị If-Match sai định dạng | **400** theo contract parser ví dụ, không ghi dữ liệu. |
| T08 | PATCH dùng If-Match: * dù policy yêu cầu version cụ thể | Bị từ chối theo hợp đồng, không bypass chống mất cập nhật. |
| T09 | GET với If-None-Match trùng ETag | **304**, không có body. |
| T10 | PUT create-only thiếu If-None-Match: * | **428**, không tạo. |
| T11 | PUT create-only đủ điều kiện, resource chưa có | **201**, Location phù hợp, chỉ một resource. |
| T12 | PUT create-only đủ điều kiện, resource đã có | **412**, resource cũ không đổi. |
| T13 | DELETE bắt buộc If-Match nhưng thiếu | **428**, không xóa. |
| T14 | DELETE với ETag cũ | **412**, không xóa. |
| T15 | Precondition khớp nhưng nghiệp vụ cấm hủy | **409**, không thực hiện command. |
| T16 | Không đăng nhập hoặc truy cập tenant khác | 401/403/404 theo chính sách; không lộ ETag/data. |
| T17 | Response 428 đi qua cache/gateway | Cache không lưu response 428; status/header/body đúng. |
| T18 | Client retry sau timeout | Không tạo tác dụng phụ trùng; kết quả được xác minh. |

### 14.2. MockMvc: thiếu điều kiện phải trả 428

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

mockMvc.perform(
        patch("/orders/{id}", orderId)
            .contentType("application/merge-patch+json")
            .content("{\"note\":\"Gọi trước khi giao\"}"))
    .andExpect(status().isPreconditionRequired())
    .andExpect(header().string("Cache-Control", "no-store"))
    .andExpect(content().contentTypeCompatibleWith(
            org.springframework.http.MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(jsonPath("$.status").value(428))
    .andExpect(jsonPath("$.code").value("IF_MATCH_REQUIRED"));
~~~

Ví dụ giả định ứng dụng có controller/handler ở phần trước, **orderId** tồn tại và request đã có danh tính hợp lệ nếu endpoint bảo vệ bằng Spring Security. Test cần bổ sung xác minh service không bị gọi để ghi hoặc query lại DB trước/sau. Chỉ kiểm tra response status chưa đủ để chứng minh **không có tác dụng phụ**.

### 14.3. MockMvc: stale ETag phải trả 412

~~~java
mockMvc.perform(
        patch("/orders/{id}", orderId)
            .header("If-Match", "\"order-v7\"")
            .contentType("application/merge-patch+json")
            .content("{\"note\":\"Để tại lễ tân\"}"))
    .andExpect(status().isPreconditionFailed())
    .andExpect(jsonPath("$.status").value(412));
~~~

Kỳ vọng này chỉ phù hợp khi DB đã ở version khác 7 nhưng request có đủ quyền; test phải xác nhận **note và version vẫn nguyên**. Nếu không có quyền, lỗi quyền có thể phải được trả trước thay vì 412.

### 14.4. Race test với database thật

Một test tích hợp nên tạo **version = 7**, rồi cho hai request đồng thời dùng cùng ETag:

~~~text
Seed: id=123, version=7, note=old
Start barrier: A và B đồng thời PATCH If-Match "order-v7"
Expected:
  Exactly one write commits
  One HTTP result = 200/204
  Other HTTP result = 412
  Final version = 8
  Final note = value of winner
  No duplicate business side-effect
~~~

Với code chỉ SELECT rồi UPDATE vô điều kiện, cả hai có thể thành công; test sẽ phát hiện. Dùng transaction phù hợp và database thật (ví dụ PostgreSQL chạy trong Testcontainers) để kiểm tra isolation, constraint và affected row count. Các test mock service không thể chứng minh đầy đủ tính nguyên tử của transaction.

### 14.5. Vòng đời validator cần được kiểm thử

1. GET trả strong ETag v7.
2. PATCH với If-Match v7 thành công, version lên v8.
3. GET mới trả ETag v8 và representation thay đổi.
4. GET với If-None-Match v8 có thể trả 304.
5. PATCH với If-Match v7 không được ghi, trả 412.
6. Mọi thay đổi ảnh hưởng tới representation phải làm validator thay đổi phù hợp.
7. Các biến thể representation không được tái dùng strong validator sai ngữ nghĩa.
8. Lỗi không được cấp quyền không làm lộ ETag hiện hành của tenant khác.

## 15. Case study: nâng cấp REST API đơn hàng đang chạy

### 15.1. Bối cảnh

Hệ thống bán hàng có các endpoint:

- **GET /orders/{id}** đọc đơn.
- **PATCH /orders/{id}** sửa ghi chú.
- **POST /orders/{id}/cancel** hủy đơn nếu chưa giao.
- **PUT /draft-orders/{clientId}** tạo nháp từ thiết bị có thể ngoại tuyến.
- **POST /payments** thu tiền và server cấp ID thanh toán.

Ứng dụng dùng PostgreSQL có cột **version**, nhưng hiện mọi PATCH đều chấp nhận request không điều kiện. Web mới và ứng dụng di động phiên bản cũ đang cùng truy cập; có nhiều phản ánh ghi chú bị mất khi hai nhân viên cùng sửa. Hệ thống multi-tenant và có proxy phía trước Spring.

### 15.2. Yêu cầu người học

1. Chọn endpoint nào cần If-Match, If-None-Match hoặc Idempotency-Key.
2. Xác định status khi PATCH thiếu điều kiện, PATCH có ETag cũ, hủy đơn bị cấm bởi trạng thái.
3. Đề xuất câu lệnh SQL ngăn hai người cùng ghi thành công từ version 7.
4. Giải thích cách tránh lộ dữ liệu tenant khác qua lỗi 428/412.
5. Thiết kế phương án rollout cho ứng dụng di động cũ.
6. Đề xuất ít nhất sáu phép kiểm thử và metric theo dõi sau triển khai.

### 15.3. Một phương án giải

| Endpoint | Chính sách |
| --- | --- |
| GET /orders/{id} | Phát strong ETag khi đáp ứng đúng representation; có thể hỗ trợ If-None-Match cho cache. |
| PATCH /orders/{id} | Bắt buộc **If-Match strong cụ thể**; thiếu **428**, stale **412**. |
| POST /orders/{id}/cancel | Có thể bắt buộc If-Match nếu command phụ thuộc version; version đúng nhưng trạng thái SHIPPED → **409**. |
| PUT /draft-orders/{clientId} | Chỉ tạo mới, bắt buộc **If-None-Match: \***; thiếu **428**, URI đã tồn tại **412**. |
| POST /payments | **Idempotency-Key** và cơ chế bền vững ngăn thu tiền trùng; không bịa ETag của resource chưa có. |

SQL chính là **UPDATE ... WHERE id = :id AND tenant_id = :tenant AND version = :expectedVersion** và **version = version + 1**. Số dòng cập nhật bằng 1 nghĩa là thắng; số dòng bằng 0 yêu cầu phân loại stale/missing/not authorized trước khi phản hồi.

Về bảo mật, **tenant phải lấy từ identity**, và server không được trả current ETag hoặc dữ liệu của người khác trong 412. Nếu chính sách che sự tồn tại, cần thống nhất cách trả 404 cho resource ngoài quyền.

**Lộ trình rollout có kiểm soát:**

1. Trước tiên phát ETag trên GET và hoàn thiện mapping ở database.
2. Cập nhật web/SDK để lưu ETag và gửi If-Match; thêm hướng dẫn xử lý 412.
3. Đo tỷ lệ request thiếu điều kiện theo phiên bản client, thử nghiệm canary và integration test.
4. Thông báo kế hoạch nâng cấp ứng dụng cũ; nếu cần hỗ trợ tương thích, thiết kế một endpoint/version với chính sách rõ, không âm thầm bỏ bảo vệ trên endpoint nghiệp vụ quan trọng.
5. Bật 428 cho các endpoint đã được chuẩn bị; theo dõi 428, 412, 409 và lỗi ở transaction.

Các phép thử ưu tiên: PATCH thiếu header không ghi; PATCH đúng ETag cập nhật; stale ETag không ghi; hai PATCH song song chỉ một thắng; PUT create-only không ghi đè; POST payment retry cùng key chỉ một giao dịch; tenant khác không đọc/sửa được; response 428 không được cache lưu trữ.

### 15.4. Ba biến thể nâng cao

**A. Transaction rollback:** A bắt đầu sửa version 7 nhưng transaction rollback. B gửi If-Match v7; nếu version trong DB vẫn v7, B có thể thành công. Không báo 412 chỉ vì một transaction khác từng bắt đầu.

**B. Read replica trễ:** Client đọc v7 từ replica sau khi primary đã commit v8. PATCH tới primary với v7 phải nhận 412; có thể cần chiến lược read-your-writes hoặc đọc từ nguồn nhất quán hơn khi hòa giải.

**C. Response mất sau commit:** B retry PATCH v7 và nhận 412. Điều này không chứng minh PATCH đầu do B thực hiện đã thành công hay thất bại; phải đối soát trạng thái, request ID hoặc cơ chế idempotency nếu cần.

## 16. Những phản mẫu phổ biến

| Phản mẫu | Tác hại | Cách sửa |
| --- | --- | --- |
| Tài liệu yêu cầu If-Match nhưng server vẫn chấp nhận khi thiếu | Chỉ một client cũ có thể phá bảo vệ đồng thời. | Thực thi **428** theo route/policy. |
| Trả 428 khi ETag đã gửi nhưng không còn khớp | Nhầm thiếu điều kiện với điều kiện sai. | Dùng **412** cho precondition false. |
| Dùng 409 cho mọi ETag cũ | Mất ngữ nghĩa If-Match/412 chuẩn HTTP. | Dùng **409** cho conflict nghiệp vụ. |
| Cho If-Match: * vượt qua policy version cụ thể | Không chống lost update. | Yêu cầu strong ETag của phiên bản đã đọc. |
| Dùng weak ETag như một strong match | Vi phạm ngữ nghĩa so sánh mạnh. | Phát và kiểm tra strong validator hợp lệ. |
| SELECT kiểm tra version rồi UPDATE không điều kiện | Race giữa kiểm tra và ghi. | Atomic compare-and-swap hoặc optimistic locking thật. |
| Một số đường cập nhật không tăng version | ETag không còn phản ánh representation. | Thống nhất cơ chế version trên mọi đường ghi. |
| Cache response 428 | Trái yêu cầu RFC 6585, làm hỏng hành vi client. | Không lưu 428, bổ sung no-store. |
| Bắt If-Match cho mọi POST tạo resource | Resource chưa có ETag để client cung cấp. | Chọn chính sách theo thao tác, cân nhắc Idempotency-Key. |
| Tự động retry sau 412 mà không đối soát | Về nghiệp vụ vẫn có thể ghi đè thay đổi của người khác. | GET và hòa giải có chủ đích. |
| Coi ETag như token quyền | Lộ dữ liệu khi biết URL và validator. | Xác thực/phân quyền theo resource và tenant. |
| Tin ETag sẽ chống thanh toán trùng hoặc event trùng | Conditional write của resource không bao trùm tác dụng phụ phân tán. | Idempotency, transaction/outbox và ràng buộc nghiệp vụ. |

## 17. Checklist trước khi triển khai 428

### Hợp đồng giao thức

- [ ] Định nghĩa endpoint/method nào bắt buộc điều kiện và loại header nào được phép.
- [ ] GET/HEAD có khả năng trả ETag đúng representation; strong ETag dùng cho If-Match khi phù hợp.
- [ ] Thiếu điều kiện bắt buộc trả **428**, điều kiện false trả **412**, conflict nghiệp vụ trả **409**.
- [ ] PUT create-only dùng **If-None-Match: \*** nếu chính sách yêu cầu; không ghi đè URI đang có.
- [ ] Không dùng 428 cho mọi POST hoặc mọi GET.
- [ ] Response 428 **không được cache lưu trữ**; có thể phát Cache-Control: no-store.
- [ ] Problem Details có type/code ổn định, body không lộ chi tiết nhạy cảm.

### Dữ liệu và bảo mật

- [ ] So sánh version và ghi diễn ra nguyên tử trong database hoặc optimistic locking tương đương.
- [ ] Validator được cập nhật phù hợp khi representation thay đổi; không bỏ qua các job cập nhật nền.
- [ ] Không coi weak ETag hoặc If-Match: * là version match cụ thể.
- [ ] Tenant/owner lấy từ identity; mọi lệnh ghi có điều kiện phân quyền rõ ràng.
- [ ] Đánh giá read replica/cache và nguồn ghi để không xác nhận validator stale một cách vô điều kiện.
- [ ] Có idempotency và xử lý tác dụng phụ đa resource riêng khi cần.

### Tích hợp và kiểm thử

- [ ] OpenAPI mô tả header If-Match/If-None-Match cùng 428, 412, 409 và 200/204/201 phù hợp.
- [ ] Spring Security, controller, exception handler và gateway có mapping nhất quán.
- [ ] Client hiểu 428 cần bổ sung điều kiện, 412 cần đọc lại và hòa giải, 409 cần xử lý nghiệp vụ.
- [ ] Test thiếu điều kiện và stale ETag xác minh **DB không đổi**, không chỉ kiểm tra mã số.
- [ ] Race test chạy database thật: hai request cùng version chỉ một thành công.
- [ ] Kiểm thử strong/weak ETag, wildcard, quyền tenant, cache 428 và GET 304.
- [ ] Retry sau timeout không phát sinh tác dụng phụ trùng.
- [ ] Có kế hoạch nâng cấp SDK cũ và metric 428/412 để theo dõi rollout.

**Kết luận:** **428 Precondition Required** bảo vệ **chính sách phải cung cấp điều kiện**; **412 Precondition Failed** bảo vệ **điều kiện phải đúng tại thời điểm thực thi**; và chỉ **thao tác ghi nguyên tử có kiểm tra điều kiện** mới thực sự ngăn lost update. Kết hợp strong ETag, If-Match/If-None-Match, phân quyền, OpenAPI, cách xử lý ở client và kiểm thử đồng thời sẽ giúp REST API từ chối cập nhật lỗi thời một cách rõ ràng, thay vì âm thầm ghi đè dữ liệu của người khác.
